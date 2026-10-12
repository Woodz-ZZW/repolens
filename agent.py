import json
from pathlib import Path

from openai import omit

from app import agentLLM
from tools import list_files, search_code, read_file

from datetime import datetime
from time import perf_counter

from hashlib import sha256

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出当前仓库中的 Python 文件相对路径，无需参数",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "在当前仓库的 Python 文件中搜索关键词，忽略大小写。"
                "最多返回 15 处匹配，每处包含文件路径，行号和代码原文。"
                "truncated 为 true 表示还有未返回的匹配。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜索的非空关键词，由你根据用户问题选择。",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                    "读取当前仓库中指定 Python 文件的一段代码，行号从 1 开始，"
                    "结束行不能小于开始行。每次最多实际读取 80 行，"
                    "超长请求先返回前 80 行。"
                    "返回对象中的 content 是带行号原文，"
                    "start_line 和 end_line 是实际读取范围，"
                    "requested_end_line 是原请求的结束行。"
                    "next_start_line 非空时，需要后续内容可尝试从该行继续读取。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "当前仓库中 Python 文件的相对路径，例如 tools.py。",
                    },
                    "start_line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "开始行号，包含这一行。",
                    },
                    "end_line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "结束行号，包含这一行。",
                    },
                },
                "required": ["relative_path", "start_line", "end_line"],
                "additionalProperties": False,
            },
        },
    },
]

def parse_report(text: str) -> dict:
    report = json.loads(text)

    field_types = {
        "status": str,
        "summary": str,
        "root_cause": str,
        "evidence": list,
        "suggestion": str,
        "verification": list,
        "missing_information": list,
    }

    if not isinstance(report, dict) or set(report) != set(field_types):
        raise ValueError("报告必须包含且只能包含规定的七个字段")
    for name, expected_type in field_types.items():
        if not isinstance(report[name], expected_type):
            raise ValueError(f"字段 {name} 的类型不正确")

    if report["status"] not in ("hypothesis", "insufficient_evidence"):
        raise ValueError("status 的值不正确")

    if report["status"] == "hypothesis" and not report["root_cause"].strip():
        raise ValueError("hypothesis 必须填写 root_cause")

    for name in ("verification", "missing_information"):
        if any(not isinstance(item, str) for item in report[name]):
            raise ValueError(f"字段 {name} 必须是字符串数组")

    for item in report["evidence"]:
        expected_keys = {"path", "start_line", "end_line", "code"}
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise ValueError("每条证据必须包含 path、start_line、end_line、code")

        if not isinstance(item["path"], str) or not isinstance(item["code"], str):
            raise ValueError("证据的 path 和 code 必须是字符串")

        start_line = item["start_line"]
        end_line = item["end_line"]
        if type(start_line) is not int or type(end_line) is not int:
            raise ValueError("证据的 start_line 和 end_line 必须是整数")

        if start_line <1 or end_line < start_line:
            raise ValueError("证据行号必须从 1 开始，结束行不能小于开始行")

    return report

def validate_evidence(report: dict, read_evidence: dict) -> None:
    if report["status"] == "hypothesis" and not report["evidence"]:
        raise ValueError("根因假设必须包含代码证据")

    for item in report["evidence"]:
        path = item["path"]
        start_line = item["start_line"]
        end_line = item["end_line"]
        lines = []

        for line_number in range(start_line, end_line +1):
            location = (path, line_number)
            if location not in read_evidence:
                raise ValueError(f"证据引用了未读取的代码：{path}:{line_number}")
            lines.append(read_evidence[location])

        if item["code"] != "\n".join(lines):
            raise ValueError(f"证据原文不一致：{path}:{start_line}-{end_line}")

def repo_fingerprint(repo_dir: str) -> str:
    root = Path(repo_dir).resolve()
    fingerprint = sha256()

    for relative_path in sorted(list_files(repo_dir)):
        file_path = root / relative_path

        fingerprint.update(relative_path.encode("utf-8"))
        fingerprint.update(b"\0")
        fingerprint.update(sha256(file_path.read_bytes()).digest())
    return fingerprint.hexdigest()

def save_run(run_data: dict, started: float) -> None:
    run_data["elapsed_seconds"] = round(perf_counter() - started, 3)
    run_data["trace"] = [
        item if isinstance(item, dict)
        else item.model_dump(mode="json", exclude_none=True)
        for item in run_data["trace"]
    ]

    output_dir = Path(__file__).resolve().parent / "runs"
    output_dir.mkdir(exist_ok=True)

    filename = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json"
    output_path = output_dir / filename
    run_data["run_file"] = str(output_path)
    output_path.write_text(
        json.dumps(run_data, ensure_ascii=False, indent=2),
        encoding = "utf-8"
    )
    print(f"\n运行记录已保存：{output_path}")

def run_agent(repo_dir: str, question: str):
    started = perf_counter()
    started_at = datetime.now().astimezone().isoformat()
    llmClient = agentLLM()

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个仓库阅读助手。查询文件列表时调用 list_files。"
                "查找代码时调用 search_code，自行根据问题选择搜索关键词。"
                "搜索结果最多包含 15 处匹配，truncated 为 true 时换更具体的关键词继续搜索。"
                "解释函数实现前，必须根据搜索结果调用 read_file，"
                "读取函数的完整代码；若没有读全，继续读取。"
                "只根据工具结果回答，引用文件路径、行号和代码原文，"
                "没有足够结果时如实说明，不要猜测未读取的代码。"
                "工具只扫描部分 Python 文件，回答必须注明检查范围。"
                "搜索无匹配只代表本次搜索未找到，不能证明整个仓库不存在相关内容。"
                "最终回答必须是合法的 JSON 对象，不要代码块或额外文字。"
                "必须且只能包含以下七个字段："
                "status、summary、root_cause、evidence、suggestion、verification、missing_information。"
                "status 只能是 hypothesis（有代码支持的根因假设）"
                "或 insufficient_evidence（证据不足）。"
                "summary 和 suggestion 必须是字符串，summary 要说明检查范围。"
                "root_cause 是字符串，写由证据推断出的根因假设；证据不足时为空字符串。"
                "evidence 必须是数组，每项必须且只能包含 path、start_line、end_line、code。"
                "path 是文件相对路径字符串，start_line 和 end_line 是正整数行号。"
                "起始行和结束行都包含，结束行不能小于开始行。"
                "单行证据的起始行和结束行相同。"
                "code 是对应行段的连续原文，各行用换行符连接，保留缩进和空行。"
                "解释判断分支时，优先引用包含条件和返回值的连续代码片段。"
                "证据只引用本次成功调用 read_file 返回的代码，原文不含行号前缀。"
                "hypothesis 必须提供至少一条代码证据。"
                "没有代码证据时使用空数组，并将状态设为 insufficient_evidence。"
                "verification 和 missing_information 必须是字符串数组。"
                "verification 写尚未执行的验证步骤。"
                "missing_information 写继续调查所需的材料，没有则为空数组。"
                "证据不足时，suggestion 不得提出没有依据的代码修复。"
            ),
        },
        {
            "role": "user",
            "content": question,
        },
    ] 

    max_steps = 6
    max_tool_calls = 8
    tool_calls_used = 0
    read_evidence = {}
    report_error = None
    run_data = {
        "started_at": started_at,
        "question": question,
        "repo_dir": str(Path(repo_dir).resolve()),
        "repo_fingerprint": repo_fingerprint(repo_dir),
        "model": llmClient.model,
        "model_calls": 0,
        "tool_calls_used": 0,
        "usage": [],
        "trace": messages,
        "report": None,
        "error": None,
    }
    for step in range(1, max_steps + 1):
        print(f"\n---第 {step} 轮模型调用---")

        is_final_step = step == max_steps or tool_calls_used >= max_tool_calls

        if is_final_step:
            messages.append({
                "role": "user",
                "content": (
                    "本次调查已达到模型轮数或工具次数上限。"
                    "请根据已有工具结果输出 JSON 诊断报告。"
                    "证据不足时明确说明无法定位根因，"
                    "并列出需要补充的材料"
                    "不要猜测，也不要声称执行过测试。"
                ),
            })

        run_data["model_calls"] = step

        try:
            response = llmClient.client.chat.completions.create(
                model = llmClient.model,
                messages = messages,
                tools = TOOLS,
                tool_choice = "none" if is_final_step else "auto",
                reasoning_effort = llmClient.reasoning_effort or omit,
                stream = False,
            )
        except Exception as error:
            run_data["usage"].append(None)
            run_data["error"] = f"{type(error).__name__}: {error}"
            save_run(run_data, started)
            return run_data

        message = response.choices[0].message
        run_data["usage"].append(
            response.usage.model_dump(mode="json", exclude_none=True)
            if response.usage is not None else None
        )
        messages.append(message)

        if not message.tool_calls:
            try:
                report = parse_report(message.content or "")
                validate_evidence(report, read_evidence)
            except ValueError as error:
                report_error = str(error)
                print(f"\n报告校验不合格：{error}")
                print(message.content or "模型没有返回文本。")
                messages.append({
                    "role": "user",
                    "content": (
                        f"报告校验不合格：{error}。"
                        "请修正后重新输出完整的 JSON 报告，不要代码块或额外文字。"
                    ),
                })
                continue

            run_data["report"] = report
            print("\n---诊断报告---")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            save_run(run_data, started)
            return run_data

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            print(f"模型请求工具：{tool_name}")

            try:
                if tool_calls_used >= max_tool_calls:
                    raise ValueError("工具调用次数已达上限，本次工具未执行")
                
                tool_calls_used += 1
                run_data["tool_calls_used"] = tool_calls_used
                print(f"工具调用次数：{tool_calls_used}/{max_tool_calls}")
                
                arguments = json.loads(tool_call.function.arguments)
                print(f"工具参数：{arguments}")

                if not isinstance(arguments, dict):
                    raise ValueError("工具参数必须是一个 JSON 对象")

                if tool_name == "list_files":
                    if arguments != {}:
                        raise ValueError("list_files 不需要模型提供参数")

                    result = list_files(repo_dir)

                elif tool_name == "search_code":
                    if set(arguments) != {"query"}:
                        raise ValueError("search_code 必须且只能提供 query 参数")

                    query = arguments["query"]

                    if not isinstance(query, str):
                        raise ValueError("query 必须是字符串")

                    result = search_code(repo_dir, query)

                elif tool_name == "read_file":
                    if set(arguments) != {"relative_path", "start_line", "end_line"}:
                        raise ValueError(
                            "read_file 必须且只能提供 relative_path、start_line、end_line 参数"
                        )

                    relative_path = arguments["relative_path"]
                    start_line = arguments["start_line"]
                    end_line = arguments["end_line"]

                    if not isinstance(relative_path, str):
                        raise ValueError("relative_path 必须是字符串")

                    if type(start_line) is not int or type(end_line) is not int:
                        raise ValueError("start_line 和 end_line 必须是整数")

                    safe_end_line = min(end_line, start_line + 79)
                    content = read_file(
                        repo_dir, relative_path, start_line, safe_end_line
                    )

                    numbered_lines = content.splitlines()
                    for numbered_line in numbered_lines:
                        number, code = numbered_line.split(": ", 1)
                        read_evidence[(relative_path, int(number))] = code

                    actual_end_line = int(
                        numbered_lines[-1].split(": ", 1)[0]
                    )

                    next_start_line = (
                        actual_end_line + 1
                        if safe_end_line < end_line
                        and actual_end_line == safe_end_line
                        else None
                    )

                    result = {
                        "path": relative_path,
                        "content": content,
                        "start_line": start_line,
                        "end_line": actual_end_line,
                        "requested_end_line": end_line,
                        "next_start_line": next_start_line,
                    }

                else:
                    raise ValueError(f"未知工具：{tool_name}")
            except (ValueError, TypeError, OSError) as error:
                result = {
                    "error": type(error).__name__,
                    "message": str(error)
                }
            result_text = json.dumps(result, ensure_ascii=False)

            print(f"工具结果：{result_text}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_text,
            })

    print(f"\n达到 {max_steps} 轮调用上限，尚未得到最终回答。")
    run_data["error"] = "达到模型调用轮数上限，尚未得到最终答案"
    if report_error:
        run_data["error"] += f"；最后一次报告校验错误：{report_error}"
    save_run(run_data, started)
    return run_data

if __name__ == "__main__":
    repo_dir = "/Users/wz/repolens-case-more-itertools"
    question = (
        "执行 list(windowed([], 2)) 得到 [(None, None)]，"
        "但要求空输入时不产生窗口，结果应为 []。"
        "请用工具检查当前仓库，定位原因，"
        "提供代码证据、修复建议和验证步骤。"
        "修复应保留非空输入不足窗口宽度时的填充行为。"
    )

    run_agent(repo_dir, question)
