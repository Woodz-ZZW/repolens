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
- Run records saved to PostgreSQL (`runs` and `evidence` tables) as well as JSON files.
- A REST API (`/api/runs`) to create, list, retrieve, and delete runs, with validated inputs, API-key roles, and integration tests against PostgreSQL.

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
REPOLENS_USER_KEY=your-user-key
REPOLENS_ADMIN_KEY=your-admin-key
```

The model must support tool calling. Keep `.env` local and do not commit it to Git.
`LLM_REASONING_EFFORT` is optional. Set it only if your provider supports the `reasoning_effort` parameter; when it is unset, the parameter is not sent.

The two `REPOLENS_*_KEY` values protect the REST API. The user key can create runs; the admin key can also delete them.
Generate each key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Database (PostgreSQL)

Each run is also saved to PostgreSQL. If the database is not running, a command-line run still completes and is saved only to `runs/`.
The web demo and REST API need the database and return `503` when it is unavailable.

Install and start PostgreSQL on macOS:

```bash
brew install postgresql@18
brew services start postgresql@18
echo 'export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
createdb repolens
```

Create the tables and import existing run records (safe to run again):

```bash
python -B db.py
```

The connection defaults to `dbname=repolens`. Set `DATABASE_URL` to use another database.

Tables:

- `runs`: one row per diagnosis, with the full report and trace stored as JSONB.
- `evidence`: one row per evidence item, linked to `runs` by a foreign key.

Example queries:

```bash
psql repolens -e -f sql/step6_queries.sql
```

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

Open http://127.0.0.1:8000, enter a problem and your user API key, and view the diagnostic report.
Expand "Tool calls" to see the arguments and result of each tool call. If the diagnosis fails, the page shows why.

The web demo always analyzes the bundled `demo_repo`.
Use the command line to analyze other repositories.

Health check: http://127.0.0.1:8000/health

## REST API

The web demo server also serves a REST API for diagnosis runs.
Interactive docs: http://127.0.0.1:8000/docs (click **Authorize** to enter a key).

| Method | Path | Key required | Success | Errors |
|---|---|---|---|---|
| `POST` | `/api/runs` | user or admin | `201` with a `Location` header | `401`, `422`, `503` |
| `GET` | `/api/runs` | none | `200` | `422`, `503` |
| `GET` | `/api/runs/{id}` | none | `200` | `404`, `422`, `503` |
| `DELETE` | `/api/runs/{id}` | admin | `204` | `401`, `403`, `404`, `503` |

- Send the key in the `X-API-Key` header.
- `POST` takes `{"question": "..."}` (1–4000 characters, no other fields), diagnoses `demo_repo` with the real model, and returns the saved run.
- `GET /api/runs` returns the newest runs first. `limit` is 1–100 (default 10); `status` is `hypothesis` or `insufficient_evidence`.

Error codes:

- `401`: the key is missing or invalid.
- `403`: the key is valid but not allowed to do this (deleting needs the admin key).
- `404`: no run has that id.
- `422`: the input is invalid; the response names the field and the rule it broke.
- `503`: the database is unavailable.

Examples:

```bash
export $(grep '^REPOLENS_' .env | xargs)
curl -s 'http://127.0.0.1:8000/api/runs?limit=5&status=hypothesis'
curl -s http://127.0.0.1:8000/api/runs/1
curl -i -X POST http://127.0.0.1:8000/api/runs \
  -H "X-API-Key: $REPOLENS_USER_KEY" -H "Content-Type: application/json" \
  -d '{"question": "Orders of 50 or more should ship free, but an order of exactly 50 is still charged 8."}'
curl -i -X DELETE http://127.0.0.1:8000/api/runs/1 -H "X-API-Key: $REPOLENS_ADMIN_KEY"
```

## Tests and evaluation

Unit tests use mocked model responses and do not call a real model.
The API integration tests send real HTTP requests to the app and use a separate `repolens_test` database, which they empty before each test:

```bash
createdb repolens_test
python -B -m unittest test_tools test_report test_agent test_api -v
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

Run records are saved in `runs/` and in the PostgreSQL `runs` table; evaluation results are saved in `eval_results/`.
Each case in an evaluation result records its run file, model, call counts, and elapsed time.

## Limitations

- Only checks Python files the tools are allowed to access.
- Reads at most 80 lines per call; longer requests return the first part and where to continue.
- Each investigation makes at most 6 model calls and 8 tool calls.
- When a report fails validation, the error is sent back to the model to fix; retries count toward the 6-call limit.
- Reads code and makes suggestions; it does not modify the analyzed repository or run its tests.
- Citation checks prove the code was actually read; the root cause and the fix still need to be verified in practice.
- API keys are fixed values in `.env`; there are no user accounts or login sessions.
- `POST /api/runs` responds only after the whole diagnosis finishes.
