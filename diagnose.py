import argparse
from pathlib import Path

from agent import run_agent


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="RepoLens：诊断本地 Python 仓库"
    )

    parser.add_argument(
        "repo_dir",
        type=Path,
        help="要检查的仓库目录",
    )
    parser.add_argument(
        "question",
        help="问题描述",
    )

    args = parser.parse_args()

    repo_dir = args.repo_dir.expanduser().resolve()

    if not repo_dir.is_dir():
        parser.error("repo_dir 必须是一个存在的目录")

    report = run_agent(str(repo_dir), args.question)

    if report is None:
        raise SystemExit("未得到合格报告，请检查运行记录")