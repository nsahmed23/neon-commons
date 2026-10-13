import pathlib
import subprocess
import sys
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "sync_worker.py"


class SyncWorkerTests(unittest.TestCase):
    def test_push_flag_is_not_offered(self):
        # Only --help is executed: the worker's ROOT is the real workspace, so a test must never let it run a
        # cycle. (An earlier version ran it with --push --once; before --push was removed that executed one
        # real cycle, which the review gate refused with exit 5.)
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--transcript", result.stdout)
        self.assertNotIn("--push", result.stdout)

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
