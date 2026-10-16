"""Fix round 2 for PKG-SETUP-4 (Sol's verification of round 1): five items, each with its own tests.

1 closed enums for the collector result   2 one normalised opaque check   3 duplicate default rows
4 an escaped descendant                   5 deeply nested collector JSON
"""
import json
import os
from pathlib import Path
import signal
import time
import unittest

from intune_iac import signin, signin_facts
from plugin_tests.signin_fakes import TENANT_A, azure_account, azure_list
from plugin_tests.test_signin_fix1 import Base, LISTING, POLICY, token_answer

TOKEN_UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWX'
MARGIN = 4.0  # seconds beyond a deadline within which a call must return


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # a zombie is gone for our purposes
        return 'Z' not in Path('/proc/%d/stat' % pid).read_text().rsplit(')', 1)[1].split()[0]
    except OSError:
        return False


def good(**more):
    value = {'status': 'captured', 'page_count': 1, 'attempt_count': 1, 'retry_count': 0, 'cancelled': False,
             'coverage': [{'kind': 'policies', 'coverage': 'complete', 'reason': None}]}
    value.update(more)
    return value


class EnumTests(Base):  # item 1
    def use_token(self, token):
        self.token = token
        self.fakes.answer('az', 'account', 'get-access-token', out=token_answer(token))

    def test_a_lower_cased_token_in_a_coverage_field_is_refused(self):
        self.use_token(TOKEN_UPPER)
        self.mode = 'lowercase'
        result = self.collect()
        self.assertEqual(result['status'], 'failed')
        self.assertIn(result['error_code'], ('collector_output_withheld', 'collector_output_invalid'))
        self.assertNotIn(TOKEN_UPPER.lower(), json.dumps(result).lower())

    def test_a_hex_encoded_token_split_across_codes_is_refused(self):
        self.use_token(TOKEN_UPPER)
        self.mode = 'hexsplit'
        result = self.collect()
        self.assertEqual(result['status'], 'failed')
        self.assertIn(result['error_code'], ('collector_output_withheld', 'collector_output_invalid'))
        self.assertNotIn(TOKEN_UPPER.encode().hex()[:10], json.dumps(result))

    def test_the_schema_accepts_only_the_values_the_capture_command_can_produce(self):
        for kind in ('policies', 'settings', 'assignments'):
            for state in ('complete', 'partial', 'access_denied'):
                for reason in (None, 'byte_limit', 'time_limit', 'page_limit', 'cancelled', 'token_expired', 'token_wrong_tenant',
                               'access_denied', 'http_error', 'selected_policy_missing', 'collection_count_mismatch'):
                    shown = signin.collector_schema(good(coverage=[{'kind': kind, 'coverage': state, 'reason': reason}]))
                    self.assertEqual(shown['coverage'], [{'kind': kind, 'coverage': state, 'reason': reason}])
        for status in ('captured', 'partial'):
            self.assertEqual(signin.collector_schema(good(status=status))['status'], status)

    def test_anything_outside_an_enum_is_invalid(self):
        for bad in (good(status='abcdefghijklmnopqrst'), good(status='Captured'),
                    good(coverage=[{'kind': 'abcdefghijklmnopqrst', 'coverage': 'complete', 'reason': None}]),
                    good(coverage=[{'kind': 'policies', 'coverage': 'abcdefghijklmnopqrst', 'reason': None}]),
                    good(coverage=[{'kind': 'policies', 'coverage': 'complete', 'reason': 'abcdefghijklmnopqrst'}]),
                    good(coverage=[{'kind': 'policies', 'coverage': 'complete', 'reason': 'Byte_limit'}]),
                    good(page_count=-1), good(page_count=signin.COUNT_BOUND + 1), good(retry_count=1.5), good(attempt_count=True)):
            self.assertIsNone(signin.collector_schema(bad), bad)

    def test_a_credential_problem_outside_the_two_codes_is_dropped(self):
        shown = signin.collector_schema(good(credential_problem={'code': 'abcdefghijklmnopqrst'}))
        self.assertNotIn('credential_problem', shown)

    def test_the_watch_is_case_insensitive_and_sees_hex(self):
        watch = signin._Watch(TOKEN_UPPER)
        self.assertTrue(watch.hit('xx ' + TOKEN_UPPER.lower() + ' xx'))
        self.assertTrue(watch.hit('h' + TOKEN_UPPER.encode().hex()[:16]))
        self.assertFalse(watch.hit('policies complete byte_limit'))


class NormalisedFilterTests(unittest.TestCase):  # item 2
    def test_separators_are_removed_before_the_checks(self):
        self.assertEqual(signin_facts.shown_name('abcdefghijkl.mnopqrstuvwx'), signin_facts.NOT_SHOWN)
        self.assertEqual(signin_facts.shown_name('abcdefghijkl@mnopqrstuvwx'), signin_facts.NOT_SHOWN)
        self.assertEqual(signin_facts.shown_name('abcdefgh-ijklmnop_qrstuvwx'), signin_facts.NOT_SHOWN)
        self.assertEqual(signin_facts.shown_host('abcdefghijkl.mnopqrstuvwx.com'), signin_facts.NOT_SHOWN)
        self.assertEqual(signin_facts.shown_name('ABCDEFGHIJKL.1234'), signin_facts.NOT_SHOWN)

    def test_a_token_shaped_word_is_not_a_code(self):
        self.assertIsNone(signin_facts.shown_code('abcdefghijklmnopqrst'))
        self.assertIsNone(signin_facts.shown_code('abcdefghijklmnop_qrstuvwx'))

    def test_known_codes_and_plain_names_are_still_shown(self):
        for code in ('collector_failed', 'collector_output_withheld', 'identity_credential_fd_limit', 'capture_write_failed'):
            self.assertEqual(signin_facts.shown_code(code), code)
        for name in ('alex@example.test', 'octo-user', 'alexander.morgan@contoso.com'):
            self.assertEqual(signin_facts.shown_name(name), name)
        self.assertEqual(signin_facts.shown_host('github.com'), 'github.com')

    def test_one_helper_serves_names_hosts_and_codes(self):
        self.assertTrue(signin_facts.opaque('abcdefghijkl.mnopqrstuvwx'))
        self.assertFalse(signin_facts.opaque('octo-user'))


class CollectorCodeTests(Base):
    def test_an_unknown_error_code_from_the_collector_is_not_shown(self):
        self.mode, self.extra = 'failcode', ['--code', 'abcdefghijklmnopqrst']
        result = self.collect()
        self.assertEqual((result['status'], result['error_code']), ('failed', 'collector_failed'))


class DuplicateDefaultTests(Base):  # item 3
    def test_two_identical_default_rows_are_ambiguous_and_no_token_command_runs(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(), azure_account()))
        for account in (None, 'alex@example.test'):
            (self.fakes.directory / 'calls.log').unlink(missing_ok=True)
            result = self.collect(account=account)
            self.assertEqual((result['status'], result['signin']['status']), ('blocked', 'several_accounts'))
            self.assertEqual(self.fakes.calls(), [LISTING])
        self.assertEqual(self.collectors(), [])

    def test_one_default_row_among_subscriptions_still_works(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(sub='s1'), azure_account(sub='s2', default=False)))
        self.assertEqual(self.collect()['status'], 'collected')


class EscapedDescendantTests(Base):  # item 4
    def test_a_collector_grandchild_that_leaves_the_session_is_not_waited_for_and_the_result_is_refused(self):
        self.mode = 'escape'
        pidfile = self.box / 'grandchild.pid'
        self.extra = ['--pidfile', str(pidfile)]
        started = time.monotonic()
        result = self.collect(collect_deadline=2)
        elapsed = time.monotonic() - started
        pid = int(pidfile.read_text()) if pidfile.exists() else None
        if pid:
            self.addCleanup(lambda: alive(pid) and os.kill(pid, signal.SIGKILL))
        self.assertLess(elapsed, 2 + MARGIN)
        self.assertEqual((result['status'], result['error_code']), ('failed', 'cleanup_unconfirmed'))
        self.assertNotIn('result', result)
        self.assertIsNotNone(self.collectors()[0].returncode)

    def test_an_az_listing_whose_descendant_escapes_is_refused_not_trusted(self):
        self.fakes.escape('az', 'account', 'list')
        started = time.monotonic()
        facts = signin.detect_azure(deadline=1)
        elapsed = time.monotonic() - started
        pid = self.fakes.escaped_pid()
        if pid:
            self.addCleanup(lambda: alive(pid) and os.kill(pid, signal.SIGKILL))
        self.assertLess(elapsed, 1 + MARGIN)
        self.assertEqual((facts['state'], facts['reason']), ('unknown', 'cleanup_unconfirmed'))

    def test_a_token_request_whose_descendant_escapes_is_refused(self):
        self.fakes.escape('az', 'account', 'get-access-token', out=token_answer(self.token))
        with self.assertRaises(Exception) as caught:
            signin.obtain_token(TENANT_A, deadline=1)
        pid = self.fakes.escaped_pid()
        if pid:
            self.addCleanup(lambda: alive(pid) and os.kill(pid, signal.SIGKILL))
        self.assertEqual(getattr(caught.exception, 'code', None), 'signin_cleanup_unconfirmed')
        self.assertNotIn(self.token, str(caught.exception))


class DeepNestingTests(Base):  # item 5
    def test_deeply_nested_collector_json_is_the_fixed_invalid_result(self):
        for self.mode in ('deep1500', 'deep'):
            result = self.collect()
            self.assertEqual((result['status'], result['error_code']), ('failed', 'collector_output_invalid'), self.mode)

    def test_deeply_nested_stderr_and_token_answers_do_not_escape_handling(self):
        self.assertEqual(signin._error_code('[' * 100000 + ']' * 100000), 'collector_failed')
        self.fakes.answer('az', 'account', 'get-access-token', out='[' * 100000 + ']' * 100000)
        with self.assertRaises(Exception) as caught:
            signin.obtain_token(TENANT_A, deadline=5)
        self.assertEqual(getattr(caught.exception, 'code', None), 'signin_token_malformed')


if __name__ == '__main__':
    unittest.main()
