from pathlib import Path
from agent import run_agent

import json
from datetime import datetime

repo_dir = Path(__file__).resolve().parent / "demo_repo"

cases = [
    {
        "name": "运费边界错误",
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
        "name": "缺少登录代码",
        "question": (
            "用户登录后立即退出，请调查登录会话失效的原因。"
            "如果当前仓库缺少相关代码，请说明需要补充什么材料。"
        ),
        "expected_status": "insufficient_evidence",
    },
    {
        "name": "通过数值对比描述问题",
        "question": (
            "订单49元收8元运费，50元也收8元，60元免运费。"
            "业务要求满50元免运费。"
            "请定位造成50元边界错误的代码，给出证据和验证步骤。"
        ),
        "expected_status": "hypothesis",
        "expected_path": "checkout.py",
        "expected_line": 5,
    },
    {
        "name": "英文描述运费问题",
        "question": (
            "Shipping should be free for orders totaling 50 or more. "
            "An order totaling exactly 50 is charged a shipping fee of 8. "
            "Inspect the repository and provide a root-cause hypothesis, "
            "code evidence, and verification steps."
        ),
        "expected_status": "hypothesis",
        "expected_path": "checkout.py",
        "expected_line": 5,
    },
    {
        "name": "缺少库存代码",
        "question": (
            "购买商品后库存没有减少，请调查库存扣减失败的原因。"
            "如果当前仓库缺少相关代码，请说明需要补充什么材料。"
        ),
        "expected_status": "insufficient_evidence",
    },
]

passed = 0
results = []
started_at = datetime.now().astimezone()

for case in cases:
    print(f"\n开始评估: {case['name']}")

    run = run_agent(str(repo_dir), case["question"])
    report = run["report"]

    case_result = {
        "case": case,
        "report": report,
        "run": {
            key: value for key, value in run.items()
            if key not in ("trace", "report")
        },
        "checks": {"得到合格报告": report is not None},
        "passed": False,
    }
    results.append(case_result)

    if report is None:
        print("自动检查未通过：没有得到合格报告")
        continue
    checks = {
        "状态符合预期": report["status"] == case["expected_status"],
    }

    if case["expected_status"] == "hypothesis":
        checks["引用关键代码行"] = any(
            item["path"] == case["expected_path"]
            and item["start_line"] <= case["expected_line"] <= item["end_line"]
            for item in report["evidence"]
        )
        checks["列出验证步骤"] = bool(report["verification"])
    else:
        checks["列出待补充信息"] = bool(report["missing_information"])

    for name, result in checks.items():
        print(f"{name}: {'通过' if result else '未通过'}")

    case_result["checks"].update(checks)
    case_result["passed"] = all(case_result["checks"].values())

    if case_result["passed"]:
        passed += 1

print(f"\n自动检查通过：{passed}/{len(cases)}")

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

print(f"评估结果已保存：{output_path}")