import json
from pathlib import Path

from openai import omit

from app import agentLLM
from tools import list_files, search_code, read_file

from datetime import datetime
from time import perf_counter

from hashlib import sha256

import psycopg
from db import init_db, insert_run

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List the relative paths of Python files in the current repository. Takes no arguments.",
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
                "Search Python files in the current repository for a keyword, case-insensitively. "
                "Returns at most 15 matches, each with the file path, line number, and original line. "
                "truncated is true when more matches were not returned."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A non-empty keyword to search for, chosen by you based on the user's question.",
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
                    "Read a range of lines from a Python file in the current repository. "
                    "Line numbers start at 1, and the end line cannot be less than the start line. "
                    "At most 80 lines are read per call; longer requests return the first 80 lines. "
                    "In the result, content is the original text with line numbers, "
                    "start_line and end_line are the range actually read, "
                    "and requested_end_line is the end line originally requested. "
                    "When next_start_line is not null, you can continue reading from that line if you need more."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Relative path of a Python file in the current repository, e.g. tools.py.",
                    },
                    "start_line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Start line number, inclusive.",
                    },
                    "end_line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "End line number, inclusive.",
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
        raise ValueError("The report must contain exactly the seven required fields")
    for name, expected_type in field_types.items():
        if not isinstance(report[name], expected_type):
            raise ValueError(f"Field {name} has the wrong type")

    if report["status"] not in ("hypothesis", "insufficient_evidence"):
        raise ValueError("Invalid status value")

    if report["status"] == "hypothesis" and not report["root_cause"].strip():
        raise ValueError("hypothesis requires a non-empty root_cause")

    for name in ("verification", "missing_information"):
        if any(not isinstance(item, str) for item in report[name]):
            raise ValueError(f"Field {name} must be an array of strings")

    for item in report["evidence"]:
        expected_keys = {"path", "start_line", "end_line", "code"}
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise ValueError("Each evidence item must contain path, start_line, end_line, and code")

        if not isinstance(item["path"], str) or not isinstance(item["code"], str):
            raise ValueError("Evidence path and code must be strings")

        start_line = item["start_line"]
        end_line = item["end_line"]
        if type(start_line) is not int or type(end_line) is not int:
            raise ValueError("Evidence start_line and end_line must be integers")

        if start_line <1 or end_line < start_line:
            raise ValueError("Evidence line numbers must start at 1, and the end line cannot be less than the start line")

    return report

def validate_evidence(report: dict, read_evidence: dict) -> None:
    if report["status"] == "hypothesis" and not report["evidence"]:
        raise ValueError("A root-cause hypothesis must include code evidence")

    for item in report["evidence"]:
        path = item["path"]
        start_line = item["start_line"]
        end_line = item["end_line"]
        lines = []

        for line_number in range(start_line, end_line +1):
            location = (path, line_number)
            if location not in read_evidence:
                raise ValueError(f"Evidence cites code that was not read: {path}:{line_number}")
            lines.append(read_evidence[location])

        if item["code"] != "\n".join(lines):
            raise ValueError(f"Evidence code does not match the source: {path}:{start_line}-{end_line}")

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
        item if isinstance(item , dict)
        else item.model_dump(mode = "json", exclude_none = True)
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
    print(f"\nRun record saved: {output_path}")

    try:
        init_db()
        run_id = insert_run(run_data)
        print(f"Run saved to database: id={run_id}")
    except psycopg.Error as exc:
        print(f"Warning: run not saved to database: {exc}")

def run_agent(repo_dir: str, question: str):
    started = perf_counter()
    started_at = datetime.now().astimezone().isoformat()
    llmClient = agentLLM()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a repository reading assistant. Call list_files to list files. "
                "Call search_code to find code, choosing search keywords yourself based on the question. "
                "Search results contain at most 15 matches; when truncated is true, search again with a more specific keyword. "
                "Before explaining a function's implementation, you must call read_file based on the search results "
                "to read the function's complete code; if you have not read all of it, keep reading. "
                "Answer only from tool results, citing file paths, line numbers, and the original code. "
                "If the results are insufficient, say so honestly and do not guess about code you have not read. "
                "The tools only scan some Python files, so the answer must state the scope that was checked. "
                "No search matches only means this search found nothing; it does not prove the repository lacks related content. "
                "The final answer must be a valid JSON object, with no code fences or extra text. "
                "It must contain exactly these seven fields: "
                "status, summary, root_cause, evidence, suggestion, verification, missing_information. "
                "status must be either hypothesis (a root-cause hypothesis supported by code) "
                "or insufficient_evidence. "
                "summary and suggestion must be strings; summary must state the scope that was checked. "
                "root_cause is a string with the root-cause hypothesis inferred from the evidence; it is an empty string when evidence is insufficient. "
                "evidence must be an array; each item must contain exactly path, start_line, end_line, and code. "
                "path is the file's relative path as a string; start_line and end_line are positive integer line numbers. "
                "Both the start line and the end line are inclusive, and the end line cannot be less than the start line. "
                "For single-line evidence, the start line and the end line are the same. "
                "code is the contiguous original text of those lines, joined with newlines, preserving indentation and blank lines. "
                "When explaining a conditional branch, prefer citing a contiguous snippet that includes the condition and the return value. "
                "Evidence may only cite code returned by successful read_file calls in this session, without line-number prefixes. "
                "hypothesis requires at least one piece of code evidence. "
                "If there is no code evidence, use an empty array and set status to insufficient_evidence. "
                "verification and missing_information must be arrays of strings. "
                "verification lists verification steps that have not been run yet. "
                "missing_information lists the materials needed to continue the investigation, or is an empty array if none are needed. "
                "When evidence is insufficient, suggestion must not propose code fixes without supporting evidence."
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
        print(f"\n--- Model call {step} ---")

        is_final_step = step == max_steps or tool_calls_used >= max_tool_calls

        if is_final_step:
            messages.append({
                "role": "user",
                "content": (
                    "The investigation has reached the model-call or tool-call limit. "
                    "Output the JSON diagnostic report based on the existing tool results. "
                    "If the evidence is insufficient, state clearly that the root cause cannot be located "
                    "and list the materials needed. "
                    "Do not guess, and do not claim to have run any tests."
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
                print(f"\nReport validation failed: {error}")
                print(message.content or "The model returned no text.")
                messages.append({
                    "role": "user",
                    "content": (
                        f"Report validation failed: {error}. "
                        "Fix it and output the complete JSON report again, with no code fences or extra text."
                    ),
                })
                continue

            run_data["report"] = report
            print("\n--- Diagnostic report ---")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            save_run(run_data, started)
            return run_data

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            print(f"Model requested tool: {tool_name}")

            try:
                if tool_calls_used >= max_tool_calls:
                    raise ValueError("Tool call limit reached; this tool was not run")

                tool_calls_used += 1
                run_data["tool_calls_used"] = tool_calls_used
                print(f"Tool calls: {tool_calls_used}/{max_tool_calls}")

                arguments = json.loads(tool_call.function.arguments)
                print(f"Tool arguments: {arguments}")

                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must be a JSON object")

                if tool_name == "list_files":
                    if arguments != {}:
                        raise ValueError("list_files takes no arguments")

                    result = list_files(repo_dir)

                elif tool_name == "search_code":
                    if set(arguments) != {"query"}:
                        raise ValueError("search_code requires exactly one argument: query")

                    query = arguments["query"]

                    if not isinstance(query, str):
                        raise ValueError("query must be a string")

                    result = search_code(repo_dir, query)

                elif tool_name == "read_file":
                    if set(arguments) != {"relative_path", "start_line", "end_line"}:
                        raise ValueError(
                            "read_file requires exactly these arguments: relative_path, start_line, end_line"
                        )

                    relative_path = arguments["relative_path"]
                    start_line = arguments["start_line"]
                    end_line = arguments["end_line"]

                    if not isinstance(relative_path, str):
                        raise ValueError("relative_path must be a string")

                    if type(start_line) is not int or type(end_line) is not int:
                        raise ValueError("start_line and end_line must be integers")

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
                    raise ValueError(f"Unknown tool: {tool_name}")
            except (ValueError, TypeError, OSError) as error:
                result = {
                    "error": type(error).__name__,
                    "message": str(error)
                }
            result_text = json.dumps(result, ensure_ascii=False)

            print(f"Tool result: {result_text}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_text,
            })

    print(f"\nReached the limit of {max_steps} model calls without a final answer.")
    run_data["error"] = "Reached the model call limit without a final answer"
    if report_error:
        run_data["error"] += f"; last report validation error: {report_error}"
    save_run(run_data, started)
    return run_data

if __name__ == "__main__":
    repo_dir = "/Users/wz/repolens-case-more-itertools"
    question = (
        "Running list(windowed([], 2)) returns [(None, None)], "
        "but an empty input should produce no windows, so the result should be []. "
        "Use the tools to inspect the current repository, locate the cause, "
        "and provide code evidence, a fix suggestion, and verification steps. "
        "The fix should keep the padding behavior for non-empty inputs shorter than the window size."
    )

    run_agent(repo_dir, question)
