import json
import os
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

DATABASE_URL = os.getenv("DATABASE_URL", "dbname=repolens")
RUNS_DIR = Path(__file__).resolve().parent / "runs"

def init_db() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                started_at       TIMESTAMPTZ NOT NULL,
                question         TEXT NOT NULL,
                repo_dir         TEXT NOT NULL,
                repo_fingerprint TEXT NOT NULL,
                model            TEXT NOT NULL,
                model_calls      INTEGER NOT NULL CHECK (model_calls >= 0),
                tool_calls_used  INTEGER NOT NULL CHECK (tool_calls_used >= 0),
                elapsed_seconds  DOUBLE PRECISION NOT NULL,
                report           JSONB,
                status           TEXT GENERATED ALWAYS AS (report->>'status') STORED,
                error            TEXT,
                trace            JSONB NOT NULL,
                usage            JSONB NOT NULL,
                run_file        TEXT NOT NULL UNIQUE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS evidence (
                id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                run_id     BIGINT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                path       TEXT NOT NULL,
                start_line INTEGER NOT NULL CHECK (start_line >= 1),
                end_line   INTEGER NOT NULL,
                code       TEXT NOT NULL,
                CHECK (end_line >= start_line)

            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS evidence_run_id_idx ON evidence (run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS runs_started_at_idx ON runs (started_at)")

def insert_run(run: dict) -> int | None:
    params = {
        **run,
        "started_at": datetime.fromisoformat(run["started_at"]),
        "report":     Jsonb(run["report"]) if run["report"] is not None else None,
        "trace":      Jsonb(run["trace"]),
        "usage":      Jsonb(run["usage"]),
    }
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            """
            INSERT INTO runs (
                started_at, question, repo_dir, repo_fingerprint, model,
                model_calls, tool_calls_used, elapsed_seconds,
                report, error, trace, usage, run_file
            )
            VALUES (
                %(started_at)s, %(question)s, %(repo_dir)s, %(repo_fingerprint)s, %(model)s,
                %(model_calls)s, %(tool_calls_used)s, %(elapsed_seconds)s,
                %(report)s, %(error)s, %(trace)s, %(usage)s, %(run_file)s
            )
            ON CONFLICT (run_file) DO NOTHING
            RETURNING id
            """,
            params,
        ).fetchone()
        if row is None:
            return None

        run_id = row[0]
        evidence = (run["report"] or {}).get("evidence", [])
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO evidence (run_id, path, start_line, end_line, code)
                VALUES (%(run_id)s, %(path)s, %(start_line)s, %(end_line)s, %(code)s)
                """,
                [{**item, "run_id": run_id} for item in evidence],
            )
    return run_id

def import_json_runs() -> int:
    inserted = 0
    for path in sorted(RUNS_DIR.glob("*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        if insert_run(run) is not None:
            inserted += 1
    return inserted

def list_runs(limit: int = 10) -> list[tuple]:
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(
            """
            SELECT id, started_at, model, status, elapsed_seconds, question
            FROM runs
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

if __name__ == "__main__":
    init_db()
    print(f"Imported {import_json_runs()} new runs")
    assert import_json_runs() == 0

    bad_run = {
        **json.loads(next(RUNS_DIR.glob("*.json")).read_text(encoding='utf-8')),
        "run_file": "rollback-test",
        "report": {"evidence": [{"path": "x.py", "start_line": 5, "end_line": 1, "code": "x"}]},

    }
    try:
        insert_run(bad_run)
    except psycopg.errors.CheckViolation:
        pass
    else:
        raise AssertionError("bad evidence was accepted")
    with psycopg.connect(DATABASE_URL) as conn:
        leftover = conn.execute("SELECT count(*) FROM runs WHERE run_file = 'rollback-test'").fetchone()[0]
    

    for row in list_runs():
        print(row)