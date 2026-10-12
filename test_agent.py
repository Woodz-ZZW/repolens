import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent import run_agent


FINAL_REPORT = {
    "status": "insufficient_evidence",
    "summary": "模拟调查的证据不足。",
    "evidence": [],
    "suggestion": "请补充相关代码。",
    "verification": [],
    "missing_information": ["相关代码"],
}


def response(tool_calls=None):
    message = SimpleNamespace(
        content=None if tool_calls else json.dumps(FINAL_REPORT),
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
        llm.client.chat.completions.create.side_effect = responses

        with (
            patch("agent.agentLLM", return_value=llm),
            patch("agent.repo_fingerprint", return_value="test-fingerprint"),
            patch("agent.save_run") as save,
            patch("agent.list_files", return_value=["checkout.py"]) as list_tool,
            patch("agent.search_code") as search_tool,
            patch("builtins.print"),
        ):
            run_agent("demo_repo", "测试问题")

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


if __name__ == "__main__":
    unittest.main()