import os
import tempfile
import unittest
from pathlib import Path

from tools import list_files, read_file, search_code


DEMO_REPO = str(Path(__file__).resolve().parent / "demo_repo")


class ToolTests(unittest.TestCase):
    def test_list_only_python_files(self):
        self.assertEqual(list_files(DEMO_REPO), ["checkout.py"])

    def test_read_exact_lines(self):
        self.assertEqual(
            read_file(DEMO_REPO, "checkout.py", 5, 6),
            "5:     if total > FREE_SHIPPING_THRESHOLD:\n6:         return 0",
        )

    def test_reject_paths_outside_repo(self):
        for path in ["../tools.py", "/etc/hosts", "missing.py"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                read_file(DEMO_REPO, path, 1, 1)

    def test_reject_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            outside = Path(tmp, "outside")
            repo.mkdir()
            outside.mkdir()
            Path(outside, "secret.py").write_text("KEY = 1\n", encoding="utf-8")
            os.symlink(outside / "secret.py", repo / "link.py")
            os.symlink(outside, repo / "linkdir")

            self.assertEqual(list_files(str(repo)), [])
            with self.assertRaises(ValueError):
                read_file(str(repo), "link.py", 1, 1)

    def test_search(self):
        result = search_code(DEMO_REPO, "shipping_fee")
        self.assertEqual([item["line"] for item in result["matches"]], [2, 4, 7])
        self.assertFalse(result["truncated"])

        self.assertEqual(
            search_code(DEMO_REPO, "payment"),
            {"matches": [], "truncated": False},
        )
        with self.assertRaises(ValueError):
            search_code(DEMO_REPO, "  ")

    def test_search_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp, "many.py")

            file_path.write_text("x = 1\n" * 15, encoding="utf-8")
            self.assertFalse(search_code(tmp, "x")["truncated"])

            file_path.write_text("x = 1\n" * 16, encoding="utf-8")
            result = search_code(tmp, "x")
            self.assertEqual(len(result["matches"]), 15)
            self.assertTrue(result["truncated"])


if __name__ == "__main__":
    unittest.main()
