import os
from pathlib import Path

def read_readme(repo_dir: str) -> str:
    readme_path = Path(repo_dir)/ "README.md"
    return readme_path.read_text(encoding="utf-8")

def list_files(repo_dir: str) -> list[str]:
    root = Path(repo_dir).resolve()

    if not root.is_dir():
        raise ValueError("repo_dir must be an existing directory")

    ignored_dirs = {"venv", "__pycache__", "node_modules"}
    result = []

    for current_dir, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [
            name for name in dirs
            if not name.startswith(".")
            and name not in ignored_dirs
            and not (Path(current_dir) / name).is_symlink()
        ]

        for name in files:
            file_path = Path(current_dir) / name

            if name.startswith(".") or file_path.suffix != ".py":
                continue

            if file_path.is_symlink():
                continue

            relative_path = file_path.relative_to(root).as_posix()
            result.append(relative_path)

    return sorted(result)

def read_file(
        repo_dir: str,
        relative_path: str,
        start_line: int,
        end_line: int,
) -> str:
    if start_line < 1 or end_line < start_line:
        raise ValueError("Line numbers start at 1, and the end line cannot be less than the start line")

    if end_line - start_line + 1 > 80:
        raise ValueError("At most 80 lines can be read per call")

    root = Path(repo_dir).resolve()

    if relative_path not in list_files(str(root)):
        raise ValueError("Only Python files listed by list_files can be read")

    file_path = root / relative_path
    lines = file_path.read_text(encoding="utf-8").splitlines()

    if start_line > len(lines):
        raise ValueError("start_line is beyond the end of the file, or the file is empty")

    actual_end = min(end_line, len(lines))
    result = []

    for line_number in range(start_line, actual_end +1):
        result.append(f"{line_number}: {lines[line_number - 1]}")

    return "\n".join(result)

def search_code(repo_dir: str, query: str) -> dict:
    keyword = query.strip().casefold()

    if not keyword:
        raise ValueError("The search keyword cannot be empty")

    root = Path(repo_dir).resolve()
    result = []

    for relative_path in list_files(str(root)):
        file_path = root / relative_path
        lines = file_path.read_text(encoding="utf-8").splitlines()

        for line_number, line in enumerate(lines, start=1):
            if keyword in line.casefold():
                if len(result) >= 15:
                    return {"matches": result, "truncated": True}

                result.append({
                    "path": relative_path,
                    "line": line_number,
                    "text": line,
                })

    return {"matches": result, "truncated": False}


if __name__ == "__main__":
    repo_dir = str(Path(__file__).resolve().parent)

    content = read_readme(repo_dir)
    print(content)

    print("\n--- Python files in the repository ---")
    for file_name in list_files(repo_dir):
        print(file_name)

    print("\n--- Lines 1-10 of tools.py ---")
    print (read_file(repo_dir, "tools.py", 1, 10))

    print("\n--- Search for read_readme ---")
    matches = search_code(repo_dir, "read_readme")["matches"]

    for match in matches:
        print(f"{match['path']}:{match['line']}{match['text']}")