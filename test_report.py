import json
import unittest

from agent import parse_report, validate_evidence


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.read_evidence = {
            ("checkout.py", 5): "    if total > FREE_SHIPPING_THRESHOLD:",
            ("checkout.py", 6): "        return 0",
            ("checkout.py", 7): "    return SHIPPING_FEE",
        }
        self.report = {
            "status": "hypothesis",
            "summary": "检查 checkout.py 中的运费判断。",
            "root_cause": "条件使用 >，金额正好 50 时不免运费。",
            "evidence": [{
                "path": "checkout.py",
                "start_line": 5,
                "end_line": 7,
                "code": (
                    "    if total > FREE_SHIPPING_THRESHOLD:\n"
                    "        return 0\n"
                    "    return SHIPPING_FEE"
                ),
            }],
            "suggestion": "比较条件改为 >=。",
            "verification": ["尚未执行测试。"],
            "missing_information": [],
        }

    def check_report(self):
        report = parse_report(json.dumps(self.report, ensure_ascii=False))
        validate_evidence(report, self.read_evidence)
        return report

    def test_valid_multiline(self):
        self.assertEqual(self.check_report(), self.report)

    def test_unread_middle_line(self):
        del self.read_evidence[("checkout.py", 6)]
        with self.assertRaisesRegex(ValueError, "未读取的代码"):
            self.check_report()
    def test_changed_code(self):
        evidence = self.report["evidence"][0]
        evidence["code"] = evidence["code"].replace(">", ">=")
        with self.assertRaisesRegex(ValueError, "原文不一致"):
            self.check_report()

    def test_invalid_line_range(self):
        for start, end in [(0, 7), (7, 5), (5, True), (5, "7"), (5, 7.0), (True, 7)]:
            with self.subTest(start=start, end=end):
                evidence = self.report["evidence"][0]
                evidence["start_line"] = start
                evidence["end_line"] = end
                with self.assertRaises(ValueError):
                    self.check_report()

    def test_hypothesis_without_evidence(self):
        self.report["evidence"] = []
        with self.assertRaisesRegex(ValueError, "必须包含代码证据"):
            self.check_report()

    def test_hypothesis_without_root_cause(self):
        self.report["root_cause"] = " "
        with self.assertRaisesRegex(ValueError, "root_cause"):
            self.check_report()

    def test_insufficient_evidence(self):
        self.report["status"] = "insufficient_evidence"
        self.report["root_cause"] = ""
        self.report["evidence"] = []
        self.report["suggestion"] = "请补充相关代码。"
        self.report["missing_information"] = ["相关业务代码"]
        self.assertEqual(self.check_report()["status"], "insufficient_evidence")

    def test_missing_report_field(self):
        del self.report["summary"]
        with self.assertRaisesRegex(ValueError, "七个字段"):
            self.check_report()

if __name__ == "__main__":
    unittest.main()