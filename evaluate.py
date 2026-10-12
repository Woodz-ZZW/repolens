from pathlib import Path
from agent import run_agent

import json
from datetime import datetime

repo_dir = Path(__file__).resolve().parent / "demo_repo"

cases = [
    {
        "name": "Shipping boundary bug",
        "question": (
            "The business rule is free shipping for orders of 50 or more, "
            "but an order of exactly 50 is still charged 8. "
            "Inspect the code and give a root-cause hypothesis, evidence, and verification steps."
        ),
        "expected_status": "hypothesis",
        "expected_path": "checkout.py",
        "expected_line": 5,
    },
    {
        "name": "Missing login code",
        "question": (
            "Users are logged out right after logging in. Investigate why the login session becomes invalid. "
            "If the current repository lacks the relevant code, explain what materials are needed."
        ),
        "expected_status": "insufficient_evidence",
    },
    {
        "name": "Problem described with numbers",
        "question": (
            "An order of 49 is charged 8 for shipping, 50 is also charged 8, and 60 ships free. "
            "The business requires free shipping from 50. "
            "Locate the code causing the boundary error at 50 and give evidence and verification steps."
        ),
        "expected_status": "hypothesis",
        "expected_path": "checkout.py",
        "expected_line": 5,
    },
    {
        "name": "Shipping problem described in Chinese",
        "question": (
            "业务规则是满50元免运费，"
            "但订单金额正好为50元时仍收取8元。"
            "请检查代码，给出根因假设、证据和验证步骤。"
        ),
        "expected_status": "hypothesis",
        "expected_path": "checkout.py",
        "expected_line": 5,
    },
    {
        "name": "Missing inventory code",
        "question": (
            "Stock does not decrease after an item is purchased. Investigate why the inventory deduction fails. "
            "If the current repository lacks the relevant code, explain what materials are needed."
        ),
        "expected_status": "insufficient_evidence",
    },
]

passed = 0
results = []
started_at = datetime.now().astimezone()

for case in cases:
    print(f"\nEvaluating: {case['name']}")

    run = run_agent(str(repo_dir), case["question"])
    report = run["report"]

    case_result = {
        "case": case,
        "report": report,
        "run": {
            key: value for key, value in run.items()
            if key not in ("trace", "report")
        },
        "checks": {"valid report": report is not None},
        "passed": False,
    }
    results.append(case_result)

    if report is None:
        print("Automatic checks failed: no valid report")
        continue
    checks = {
        "status matches": report["status"] == case["expected_status"],
    }

    if case["expected_status"] == "hypothesis":
        checks["cites key code line"] = any(
            item["path"] == case["expected_path"]
            and item["start_line"] <= case["expected_line"] <= item["end_line"]
            for item in report["evidence"]
        )
        checks["lists verification steps"] = bool(report["verification"])
    else:
        checks["lists missing information"] = bool(report["missing_information"])

    for name, result in checks.items():
        print(f"{name}: {'PASS' if result else 'FAIL'}")

    case_result["checks"].update(checks)
    case_result["passed"] = all(case_result["checks"].values())

    if case_result["passed"]:
        passed += 1

print(f"\nAutomatic checks passed: {passed}/{len(cases)}")

summary = {
    "started_at": started_at.isoformat(),
    "passed": passed,
    "total": len(cases),
    "results": results,
}

output_dir = Path(__file__).resolve().parent / "eval_results"
output_dir.mkdir(exist_ok=True)

output_path = output_dir / started_at.strftime(
     "%Y%m%d_%H%M%S_%f.json"
)

output_path.write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding = "utf-8"
)

print(f"Evaluation results saved: {output_path}")