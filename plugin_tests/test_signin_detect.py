"""Item 1: an existing sign-in is detected from the documented CLI listings, with fake az and gh, and no secret is read.

The fakes are shell scripts on a temporary search path; they print canned answers and record their arguments, so the tests
assert exactly which commands ran. No real az or gh, no browser, no network client and no credential cache is touched.
"""
import os
import unittest
from unittest.mock import patch

from intune_iac import signin, signin_facts
from plugin_tests.signin_fakes import FakeClis, TENANT_A, azure_account, azure_list, github_hosts

POISON = "TESTONLY-poison-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1"


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.fakes = FakeClis()
        self.addCleanup(self.fakes.cleanup)
        environment = {"PATH": self.fakes.path_entry() + os.pathsep + os.environ.get("PATH", "")}
        patcher = patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)

    def azure(self, **kwargs):
        self.fakes.answer("az", "account", "list", **kwargs)

    def test_azure_signed_in_reports_tenant_account_cloud_and_runs_only_the_listing(self):
        self.azure(out=azure_list(azure_account()))
        facts = signin.detect_azure(deadline=5)
        self.assertEqual(facts["state"], "signed_in")
        self.assertEqual(facts["accounts"], [{"tenant": TENANT_A, "account": "alex@example.test", "cloud": "AzureCloud",
                                              "default": True, "listing_state": "Enabled"}])
        self.assertEqual(self.fakes.calls(), ["account list --output json"])

    def test_azure_empty_listing_is_not_signed_in(self):
        self.azure(out="[]")
        self.assertEqual(signin.detect_azure(deadline=5)["state"], "not_signed_in")

    def test_azure_session_that_reports_itself_expired_is_expired(self):
        self.azure(out=azure_list(azure_account(state="Expired")))
        facts = signin.detect_azure(deadline=5)
        self.assertEqual(facts["state"], "expired")
        self.assertEqual(facts["accounts"][0]["listing_state"], "Expired")

    def test_azure_repeated_subscriptions_of_one_account_are_one_sign_in(self):
        self.azure(out=azure_list(azure_account(sub="s1"), azure_account(sub="s2", default=False)))
        self.assertEqual(len(signin.detect_azure(deadline=5)["accounts"]), 1)

    def test_azure_malformed_answers_are_unknown_with_a_reason_and_never_echoed(self):
        for text in ("not json " + POISON, '{"accounts": 1}', '[{"tenantId": "%s"}]' % POISON, "[1, 2]", "[]x"):
            self.azure(out=text)
            facts = signin.detect_azure(deadline=5)
            self.assertEqual(facts["state"], "unknown", text)
            self.assertEqual(facts["reason"], "malformed_answer", text)
            self.assertNotIn(POISON, repr(facts))

    def test_azure_unlisted_session_state_is_unknown_not_signed_in(self):
        self.azure(out=azure_list(azure_account(state="Warned")))
        facts = signin.detect_azure(deadline=5)
        self.assertEqual((facts["state"], facts["reason"]), ("unknown", "account_state_unrecognized"))

    def test_azure_slow_answer_stops_at_the_deadline(self):
        self.azure(out="[]", sleep=30)
        facts = signin.detect_azure(deadline=0.5)
        self.assertEqual((facts["state"], facts["reason"]), ("unknown", "deadline"))

    def test_azure_command_failure_and_missing_cli_are_unknown(self):
        self.azure(out="", err="boom " + POISON, code=1)
        facts = signin.detect_azure(deadline=5)
        self.assertEqual((facts["state"], facts["reason"]), ("unknown", "command_failed"))
        self.assertNotIn(POISON, repr(facts))
        with patch.dict(os.environ, {"PATH": "/nonexistent-dir-for-test"}):
            facts = signin.detect_azure(deadline=5)
        self.assertEqual((facts["state"], facts["reason"]), ("unknown", "cli_not_found"))

    def test_azure_oversized_answer_is_refused(self):
        self.azure(out="[" + " " * (signin.OUTPUT_LIMIT + 10) + "]")
        self.assertEqual(signin.detect_azure(deadline=5)["reason"], "output_too_large")

    def test_a_poisoned_account_name_is_not_displayable(self):
        self.azure(out=azure_list(azure_account(user=POISON)))
        facts = signin.detect_azure(deadline=5)
        # Shown as "<not shown>", never dropped, and a sign-in whose account cannot be shown is not usable.
        self.assertEqual(facts["accounts"][0]["account"], signin_facts.NOT_SHOWN)
        self.assertNotIn(POISON, repr(facts))
        self.assertFalse(signin_facts.evaluate(facts, TENANT_A)["usable"])

    def test_github_signed_in_reports_host_and_account(self):
        self.fakes.answer("gh", "auth", "status", out=github_hosts(("github.com", "octo-user", "success", True)))
        facts = signin.detect_github(deadline=5)
        self.assertEqual(facts["state"], "signed_in")
        self.assertEqual(facts["accounts"], [{"host": "github.com", "account": "octo-user", "active": True,
                                              "listing_state": "success"}])
        self.assertEqual(self.fakes.calls(), ["auth status --json hosts"])

    def test_github_not_signed_in_and_invalid_session(self):
        self.fakes.answer("gh", "auth", "status", out="", err="You are not logged into any GitHub hosts.", code=1)
        self.assertEqual(signin.detect_github(deadline=5)["state"], "not_signed_in")
        self.fakes.answer("gh", "auth", "status", out=github_hosts(("github.com", "octo-user", "error", True)), code=1)
        facts = signin.detect_github(deadline=5)
        self.assertEqual(facts["state"], "invalid")

    def test_github_malformed_and_slow(self):
        self.fakes.answer("gh", "auth", "status", out="{" + POISON)
        facts = signin.detect_github(deadline=5)
        self.assertEqual((facts["state"], facts["reason"]), ("unknown", "malformed_answer"))
        self.assertNotIn(POISON, repr(facts))
        self.fakes.answer("gh", "auth", "status", out="{}", sleep=30)
        self.assertEqual(signin.detect_github(deadline=0.5)["reason"], "deadline")

    def test_the_child_environment_is_scrubbed_and_no_token_command_runs(self):
        seen = {}
        real = signin.subprocess.Popen

        class Spy(real):
            def __init__(self, argv, *a, **kwargs):
                seen["env"], seen["argv"], seen["shell"] = kwargs["env"], list(argv), kwargs.get("shell", False)
                super().__init__(argv, *a, **kwargs)

        self.azure(out="[]")
        with patch.dict(os.environ, {"GH_TOKEN": POISON, "GITHUB_TOKEN": POISON, "AZURE_CLIENT_SECRET": POISON,
                                     "INTUNE_GRAPH_TOKEN": POISON, "ACCESS_TOKEN": POISON}):
            with patch("intune_iac.signin.subprocess.Popen", Spy):
                signin.detect_azure(deadline=5)
        self.assertNotIn(POISON, repr(seen["env"]))
        self.assertLessEqual(set(seen["env"]), set(signin.ENVIRONMENT_ALLOWED))
        self.assertFalse(seen["shell"])
        self.assertNotIn("get-access-token", " ".join(seen["argv"]))

    def test_facts_parse_functions_are_pure_and_tolerate_nonsense(self):
        for value in (None, b"", "", "null", "[[]]", "[{}]", "\x00"):
            self.assertIn(signin_facts.parse_azure(value)["state"], ("unknown", "not_signed_in"))
            self.assertIn(signin_facts.parse_github(value, 0, "")["state"], ("unknown", "not_signed_in"))


if __name__ == "__main__":
    unittest.main()
