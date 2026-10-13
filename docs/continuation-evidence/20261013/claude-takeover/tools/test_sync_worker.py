import pathlib
import subprocess
import sys
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "sync_worker.py"


class SyncWorkerTests(unittest.TestCase):
    def test_push_flag_is_rejected_by_argparse(self):
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--transcript", "x.jsonl", "--push", "--once"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments: --push", result.stderr)

    def test_source_has_no_push_path(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn('"--push"', text)
        self.assertNotIn("args.push", text)

    def test_dry_run_publish_does_not_fetch(self):
        # Local-only means no remote reads either; a reviewed manual publish fetches for itself.
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn('"--fetch"', text)


if __name__ == "__main__":
    unittest.main()
