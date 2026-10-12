import argparse
from pathlib import Path

from agent import run_agent


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="RepoLens: diagnose a local Python repository"
    )

    parser.add_argument(
        "repo_dir",
        type=Path,
        help="Repository directory to inspect",
    )
    parser.add_argument(
        "question",
        help="Problem description",
    )

    args = parser.parse_args()

    repo_dir = args.repo_dir.expanduser().resolve()

    if not repo_dir.is_dir():
        parser.error("repo_dir must be an existing directory")

    run = run_agent(str(repo_dir), args.question)

    if run["report"] is None:
        raise SystemExit(f"No valid report: {run['error']}")