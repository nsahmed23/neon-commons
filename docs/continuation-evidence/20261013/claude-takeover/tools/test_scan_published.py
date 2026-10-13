import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "scan_published.py"
RULES = HERE / "publish-scan-rules.txt"
FAKE_TOKEN = "ghp_" + "TESTONLY" * 4 + "abcd"
MEMORY_LINE = "see ~/.claude/pro" + "jects/C--Users-~/memory/project_z.md now"  # split: keeps this file clean for the scan


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ScanPublishedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.tree = self.base / "tree"
        self.tree.mkdir()

    def write(self, rel, data):
        path = self.tree / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    def scan(self, *extra, rules=RULES):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), str(self.tree), "--rules", str(rules), *extra],
                              capture_output=True, text=True)

    def allow_file(self, rule, rel, line):
        path = self.base / "allow.txt"
        path.write_text(f"# allow\n{rule}\t{rel}\t{sha(line.encode('utf-8'))}\n", encoding="utf-8")
        return path

    def test_planted_token_is_high_and_masked(self):
        self.write("docs/a.md", f"ok\ntoken = {FAKE_TOKEN}\n")
        result = self.scan()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("HIGH github-token docs/a.md:2 ghp_TE***", result.stdout)
        self.assertNotIn(FAKE_TOKEN, result.stdout)
        self.assertNotIn(FAKE_TOKEN, result.stderr)

    def test_clean_tree_exits_zero_and_json_shape(self):
        self.write("docs/a.md", "nothing here\n")
        out = self.base / "scan.json"
        result = self.scan("--json-out", str(out))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["files"], {"docs/a.md": {"bytes": 13, "sha256": sha(b"nothing here\n")}})
        self.assertEqual(data["hits"], [])
        self.assertEqual(data["high"], 0)
        self.assertEqual(data["rules"], 20)

    def test_truncated_rules_exit_two(self):
        self.write("a.md", "clean\n")
        lines = [ln for ln in RULES.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
        short = self.base / "short.txt"
        short.write_text("\n".join(lines[:14]) + "\n", encoding="utf-8")
        self.assertEqual(self.scan(rules=short).returncode, 2)

    def test_allow_entry_suppresses_exact_line_only(self):
        self.write("docs/m.md", MEMORY_LINE + "\n")
        allow = self.allow_file("memory-file-name", "docs/m.md", MEMORY_LINE)
        self.assertEqual(self.scan().returncode, 1)
        suppressed = self.scan("--allow", str(allow))
        self.assertEqual(suppressed.returncode, 0, suppressed.stdout)
        self.assertNotIn("memory-file-name", suppressed.stdout)
        self.write("docs/m.md", MEMORY_LINE.replace("project_z", "project_q") + "\n")
        self.assertEqual(self.scan("--allow", str(allow)).returncode, 1)
        self.write("docs/m.md", MEMORY_LINE + "\n" + MEMORY_LINE + "\n")
        self.write("docs/other.md", MEMORY_LINE + "\n")
        result = self.scan("--allow", str(allow))
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/other.md:1", result.stdout)

    def test_binary_files_hashed_not_scanned(self):
        data = b"PK\x03\x04 " + FAKE_TOKEN.encode("ascii")
        self.write("pack/a.zip", data)
        self.write("img/b.png", data)
        out = self.base / "scan.json"
        result = self.scan("--json-out", str(out))
        self.assertEqual(result.returncode, 0, result.stdout)
        files = json.loads(out.read_text(encoding="utf-8"))["files"]
        self.assertEqual(files["pack/a.zip"], {"bytes": len(data), "sha256": sha(data)})
        self.assertIn("img/b.png", files)


if __name__ == "__main__":
    unittest.main()
