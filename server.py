from pathlib import Path

from fastapi.responses import FileResponse
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from agent import run_agent

app = FastAPI(title="RepoLens")

REPO_DIR = Path(__file__).resolve().parent / "demo_repo"

class DiagnoseRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )
    question: str = Field(min_length=1, max_length=4000)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/diagnose")
def diagnose(request: DiagnoseRequest):
    run = run_agent(str(REPO_DIR), request.question)

    return {
        "report": run["report"],
        "error": run["error"],
        "trace": run["trace"],
    }

@app.get("/")
def home():
    html_path = Path(__file__).resolve().parent / "index.html"
    return FileResponse(html_path, media_type="text/html")