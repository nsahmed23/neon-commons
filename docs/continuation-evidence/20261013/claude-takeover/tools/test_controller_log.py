import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "controller_log.py"
FAKE_ID = "ccar" + "env_TESTONLY0001"  # split so the published test file itself does not trip the id rule
REDACTED = "[posture redacted]"


class ControllerLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.entries = []
        self.n = 0

    def add(self, entry_type, **fields):
        self.n += 1
        entry = {"type": entry_type, "timestamp": f"2026-10-13T01:00:{self.n:02d}Z"}
        entry.update(fields)
        self.entries.append(entry)

    def user(self, text):
        self.add("user", message={"content": text})

    def queued(self, text):
        self.add("attachment", attachment={"type": "queued_command", "prompt": text})

    def assistant(self, *blocks):
        self.add("assistant", message={"content": list(blocks)})

    def run_log(self):
        transcript = self.base / "t.jsonl"
        transcript.write_text("\n".join(json.dumps(e) for e in self.entries) + "\n", encoding="utf-8")
        out = self.base / "out.md"
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--transcript", str(transcript), "--out", str(out)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return out.read_text(encoding="ascii")

    def long_text(self):
        return ("source reply " + FAKE_ID + " ") + ("filler words here " * 200)

    def expected_marker(self, text):
        collapsed = " ".join(text.split())
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return (f"[owner relay withheld from the published log: {len(collapsed)} chars, sha256 {digest}; "
                "full text kept in the local transcript]")

    def test_long_owner_user_message_withheld(self):
        text = self.long_text()
        self.assertGreater(len(" ".join(text.split())), 2000)
        self.user(text)
        out = self.run_log()
        self.assertNotIn(FAKE_ID, out)
        self.assertNotIn("filler words", out)
        self.assertIn(self.expected_marker(text), out)

    def test_long_owner_queued_command_withheld(self):
        text = self.long_text()
        self.queued(text)
        out = self.run_log()
        self.assertNotIn(FAKE_ID, out)
        self.assertIn(self.expected_marker(text), out)

    def test_short_owner_message_verbatim(self):
        self.user("please   run the tests")
        self.queued("and then report")
        out = self.run_log()
        self.assertIn("| owner | please run the tests |", out)
        self.assertIn("| owner | and then report |", out)
        self.assertNotIn("withheld", out)

    def test_boundary_2000_chars_kept(self):
        text = "a" * 2000
        self.user(text)
        self.assertIn("a" * 1500, self.run_log())
        self.assertNotIn("withheld", self.run_log())

    def test_posture_terms_redacted_in_all_rows(self):
        terms = ['danger-full-access', 'Approval Never', 'approval_policy = "never"', 'approval_policy="never"',
                 'approval_policy', 'dangerously-skip-permissions', 'Bypass Permissions', 'bypassPermissions']
        self.assistant({"type": "text", "text": "mode is " + " and ".join(terms)})
        self.assistant({"type": "tool_use", "name": "Bash", "input": {"command": "codex --sandbox danger-full-access "
                                                                      "--dangerously-skip-permissions"}})
        self.user("owner says bypassPermissions is on")
        out = self.run_log()
        for term in ("danger-full-access", "dangerously-skip-permissions", "bypassPermissions", "approval_policy"):
            self.assertNotIn(term.lower(), out.lower())
        self.assertNotIn("approval never", out.lower())
        self.assertNotIn("bypass permissions", out.lower())
        self.assertNotIn('"never"', out)
        self.assertGreaterEqual(out.count(REDACTED), 10)

    def test_owner_replay_deduped(self):
        self.user("do the thing")
        self.queued("do the thing")
        self.user("do the thing")
        out = self.run_log()
        self.assertEqual(out.count("| owner | do the thing |"), 1)

    def test_repeated_agent_messages_kept(self):
        msg = '<agent-message from="lane-a">status ok</agent-message>'
        self.user(msg)
        self.user(msg)
        out = self.run_log()
        self.assertEqual(out.count("| agent:lane-a | status ok |"), 2)


if __name__ == "__main__":
    unittest.main()
