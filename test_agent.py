import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent import run_agent


DEMO_REPO = str(Path(__file__).resolve().parent / "demo_repo")

FINAL_REPORT = {
    "status": "insufficient_evidence",
    "summary": "模拟调查的证据不足。",
    "root_cause": "",
    "evidence": [],
    "suggestion": "请补充相关代码。",
    "verification": [],
    "missing_information": ["相关代码"],
}


def response(tool_calls=None, content=json.dumps(FINAL_REPORT)):
    message = SimpleNamespace(
        content=None if tool_calls else content,
        tool_calls=tool_calls,
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def tool_call(name, arguments, number):
    return SimpleNamespace(
        id=f"call_{number}",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


class AgentTests(unittest.TestCase):
    def run_case(self, responses):
        llm = Mock()
        llm.model = "test-model"
        llm.reasoning_effort = None
        llm.client.chat.completions.create.side_effect = responses

        with (
            patch("agent.agentLLM", return_value=llm),
            patch("agent.repo_fingerprint", return_value="test-fingerprint"),
            patch("agent.save_run") as save,
            patch("agent.list_files", return_value=["checkout.py"]) as list_tool,
            patch("agent.search_code") as search_tool,
            patch("builtins.print"),
        ):
            run_agent(DEMO_REPO, "测试问题")

        save.assert_called_once()
        record = save.call_args.args[0]
        self.assertIsNone(record["error"])
        tool_results = [
            json.loads(item["content"])
            for item in record["trace"]
            if isinstance(item, dict) and item.get("role") == "tool"
        ]
        return SimpleNamespace(
            llm=llm,
            record=record,
            list_tool=list_tool,
            search_tool=search_tool,
            tool_results=tool_results,
        )

    def test_invalid_arguments(self):
        call = tool_call("search_code", {}, 1)
        result = self.run_case([response([call]), response()])
        result.search_tool.assert_not_called()
        self.assertEqual(result.tool_results[0]["error"], "ValueError")
        self.assertEqual(result.record["report"], FINAL_REPORT)

    def test_tool_limit(self):
        calls = [tool_call("list_files", {}, i) for i in range(9)]
        result = self.run_case([response(calls), response()])
        self.assertEqual(result.list_tool.call_count, 8)
        self.assertEqual(result.record["tool_calls_used"], 8)
        self.assertEqual(result.tool_results[-1]["error"], "ValueError")
        request = result.llm.client.chat.completions.create.call_args
        self.assertEqual(request.kwargs["tool_choice"], "none")

    def test_model_limit(self):
        responses = [
            response([tool_call("list_files", {}, i)])
            for i in range(5)
        ]
        responses.append(response())
        result = self.run_case(responses)
        self.assertEqual(result.record["model_calls"], 6)
        self.assertEqual(result.llm.client.chat.completions.create.call_count, 6)
        request = result.llm.client.chat.completions.create.call_args
        self.assertEqual(request.kwargs["tool_choice"], "none")

    def test_unknown_usage(self):
        result = self.run_case([response()])
        self.assertEqual(result.record["usage"], [None])
        self.assertEqual(result.record["report"], FINAL_REPORT)

    def test_report_cites_read_lines(self):
        report = {
            "status": "hypothesis",
            "summary": "检查了 checkout.py 的运费判断。",
            "root_cause": "条件使用 >，金额正好 50 时不免运费。",
            "evidence": [{
                "path": "checkout.py",
                "start_line": 5,
                "end_line": 6,
                "code": "    if total > FREE_SHIPPING_THRESHOLD:\n        return 0",
            }],
            "suggestion": "把 > 改为 >=。",
            "verification": ["调用 shipping_fee(50)，预期返回 0。"],
            "missing_information": [],
        }
        call = tool_call(
            "read_file",
            {"relative_path": "checkout.py", "start_line": 1, "end_line": 7},
            1,
        )
        result = self.run_case([
            response([call]),
            response(content=json.dumps(report, ensure_ascii=False)),
        ])
        self.assertEqual(result.record["report"], report)

    def test_invalid_report_is_retried(self):
        result = self.run_case([response(content="不是 JSON"), response()])
        self.assertEqual(result.llm.client.chat.completions.create.call_count, 2)
        self.assertEqual(result.record["report"], FINAL_REPORT)
        self.assertTrue(any(
            "报告校验不合格" in item["content"]
            for item in result.record["trace"]
            if isinstance(item, dict) and item["role"] == "user"
        ))


if __name__ == "__main__":
    unittest.main()