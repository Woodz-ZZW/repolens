import os
import secrets
from pathlib import Path
from typing import Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Response, Security
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field

import db
from agent import run_agent

app = FastAPI(title="RepoLens")

REPO_DIR = Path(__file__).resolve().parent / "demo_repo"

class DiagnoseRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )
    question: str = Field(min_length=1, max_length=4000)

@app.exception_handler(psycopg.OperationalError)
def database_unavailable(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def current_role(api_key: str | None = Security(api_key_header)) -> str:
    for role in ("admin", "user"):
        expected = os.getenv(f"REPOLENS_{role.upper()}_KEY")
        if api_key and expected and secrets.compare_digest(api_key, expected):
            return role
    raise HTTPException(status_code=401, detail="Missing or invalid API key")

def require_admin(role: str = Depends(current_role)) -> None:
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin API key required")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/runs", status_code=201, dependencies=[Depends(current_role)])
def create_run(request: DiagnoseRequest, response: Response):
    run = run_agent(str(REPO_DIR), request.question)
    if run["id"] is None:
        raise HTTPException(status_code=503, detail="Run finished but was not saved to the database")

    response.headers["Location"] = f"/api/runs/{run['id']}"
    return db.get_run(run["id"])

@app.get("/api/runs")
def list_runs(
    limit: int = Query(default=10, ge=1, le=100),
    status: Literal["hypothesis", "insufficient_evidence"] | None = None,
):
    return db.list_runs(limit, status)

@app.get("/api/runs/{run_id}")
def get_run(run_id: int):
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run

@app.delete("/api/runs/{run_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_run(run_id: int):
    if not db.delete_run(run_id):
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

@app.get("/")
def home():
    html_path = Path(__file__).resolve().parent / "index.html"
    return FileResponse(html_path, media_type="text/html")