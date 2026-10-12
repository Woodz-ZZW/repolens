from pathlib import Path

from fastapi.responses import FileResponse
from fastapi import FastAPI, HTTPException
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
    report = run_agent(str(REPO_DIR), request.question)

    if report is None:
        raise HTTPException(
            status_code=502,
            detail="未得到合格报告，请检查服务端运行记录",
        )

    return report

@app.get("/")
def home():
    html_path = Path(__file__).resolve().parent / "index.html"
    return FileResponse(html_path, media_type="text/html")