# RepoLens

English | [简体中文](README.zh-CN.md)

An AI agent that diagnoses problems in local Python repositories.

Give it a repository path and a problem description. The agent picks its own search keywords,
reads the code, and returns a root-cause hypothesis, code evidence, a fix suggestion, and verification steps.

## Features

- Tools to list files, search by keyword, and read code with line numbers.
- An investigation loop in which the model chooses its own tools.
- A structured JSON diagnostic report.
- Citation checks: evidence must come from code actually read in the current run and match the source exactly.
- Limits on model calls, tool calls, and lines per read.
- A command-line entry point, a web demo, unit tests, and fixed-case evaluation.
- Saved investigation traces and final reports.

Core flow:

question → model picks a tool → tool runs → result returns → investigation continues → report is validated

## Installation

Developed with Python 3.13.9. Run these commands from the project root on macOS/Linux:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create a `.env` file in the project root and replace the placeholders with your provider's settings:

```dotenv
LLM_MODEL_ID=your-model-name
LLM_API_KEY=your-api-key
LLM_BASE_URL=your-openai-compatible-api-url
LLM_TIMEOUT=60
# LLM_REASONING_EFFORT=none
```

The model must support tool calling. Keep `.env` local and do not commit it to Git.
`LLM_REASONING_EFFORT` is optional. Set it only if your provider supports the `reasoning_effort` parameter; when it is unset, the parameter is not sent.

## Command-line diagnosis

```bash
python -B diagnose.py demo_repo \
  "Orders of 50 or more should ship free, but an order of exactly 50 is still charged 8. Find the cause and provide code evidence."
```

The first argument is the repository directory and the second is the problem description.
Change them to diagnose another local Python repository.

Show help:

```bash
python -B diagnose.py --help
```

## Web demo

```bash
python -m uvicorn server:app --reload --port 8000
```

Open http://127.0.0.1:8000, enter a problem, and view the diagnostic report.
Expand "Tool calls" to see the arguments and result of each tool call. If the diagnosis fails, the page shows why.

The web demo always analyzes the bundled `demo_repo`.
Use the command line to analyze other repositories.

Health check: http://127.0.0.1:8000/health

## Tests and evaluation

Unit tests use mocked model responses and do not call a real model:

```bash
python -B -m unittest test_tools test_report test_agent -v
```

Fixed-case evaluation calls the real model:

```bash
python -B evaluate.py
```

The evaluation checks report status, key evidence, and required fields.
Passing these checks does not prove the root-cause judgment is correct.

## Output

The diagnostic report has seven fields:

- `status`: a root-cause hypothesis, or insufficient evidence.
- `summary`: the diagnosis and the scope that was checked.
- `root_cause`: the root-cause hypothesis inferred from the evidence; empty when evidence is insufficient.
- `evidence`: file path, line numbers, and original code.
- `suggestion`: the direction of the fix.
- `verification`: verification steps that have not been run yet.
- `missing_information`: what is needed to continue the investigation.

Run records are saved in `runs/` and evaluation results in `eval_results/`.
Each case in an evaluation result records its run file, model, call counts, and elapsed time.

## Limitations

- Only checks Python files the tools are allowed to access.
- Reads at most 80 lines per call; longer requests return the first part and where to continue.
- Each investigation makes at most 6 model calls and 8 tool calls.
- When a report fails validation, the error is sent back to the model to fix; retries count toward the 6-call limit.
- Reads code and makes suggestions; it does not modify the analyzed repository or run its tests.
- Citation checks prove the code was actually read; the root cause and the fix still need to be verified in practice.
