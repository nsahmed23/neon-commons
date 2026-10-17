"""PKG-SETUP-5C item 3: `signin status` prints a readable text screen by default; --json keeps the data form.

Every fake sign-in is a stand-in on a temporary search path; no account name, token or tenant here is real.
"""
import contextlib
import io
import json
import os
import re
import unittest
from unittest.mock import patch

from intune_iac import cli, signin
from plugin_tests.signin_fakes import FakeClis, TENANT_A, TENANT_B, azure_account, azure_list, github_hosts

ACCESS_LINE = 'Graph, Intune and state-storage access are unknown until a read is attempted.'
GUIDS = re.compile(r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}')


class ReadableBase(unittest.TestCase):
    def setUp(self):
        self.fakes = FakeClis()
        self.addCleanup(self.fakes.cleanup)
        patcher = patch.dict(os.environ, {'PATH': self.fakes.path_entry() + os.pathsep + os.environ.get('PATH', '')})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account()))

    def run_cli(self, *argv, columns=None):
        out, err = io.StringIO(), io.StringIO()
        environment = {} if columns is None else {'COLUMNS': str(columns)}
        with patch.dict(os.environ, environment), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()


class TextByDefaultTests(ReadableBase):
    def test_a_usable_sign_in_prints_a_verdict_line_first_then_the_facts_and_the_exit_meaning(self):
        code, out, err = self.run_cli('signin', 'status', '--tenant', TENANT_A)
        lines = out.splitlines()
        self.assertEqual((code, err), (0, ''))
        with self.assertRaises(ValueError):
            json.loads(out)
        self.assertEqual(lines[0], 'AZURE: READY')
        self.assertIn('Tenant wanted: ' + TENANT_A, out)
        self.assertIn('Tenant found: ' + TENANT_A, out)
        self.assertIn('Account: alex@example.test (default)', out)
        self.assertIn('Next step:', lines)
        self.assertIn('    No sign-in step is needed.', lines)
        self.assertEqual(out.count(ACCESS_LINE), 1)
        self.assertIn('Exit code 0: ready (2 means blocked).', out)

    def test_a_blocked_sign_in_says_blocked_with_the_reason_code_and_exit_2(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(tenant=TENANT_B)))
        code, out, _ = self.run_cli('signin', 'status', '--tenant', TENANT_A)
        self.assertEqual(code, 2)
        self.assertEqual(out.splitlines()[0], 'AZURE: BLOCKED (wrong_tenant)')
        self.assertIn('Tenant wanted: ' + TENANT_A, out)
        self.assertIn('Tenant found: ' + TENANT_B, out)
        self.assertIn('Exit code 2: blocked (0 means ready).', out)
        self.assertEqual(out.count(ACCESS_LINE), 1)

    def test_without_a_tenant_the_sign_in_is_reported_never_called_ready(self):
        code, out, _ = self.run_cli('signin', 'status')
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], 'AZURE: REPORTED (no tenant was given to compare)')
        self.assertIn('Tenant wanted: none given', out)
        self.assertIn('Exit code 0: reported (2 means blocked).', out)

    def test_every_provider_gets_its_own_verdict_line_first(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'octo-user', 'error', True)), code=1)
        code, out, _ = self.run_cli('signin', 'status', '--tenant', TENANT_A, '--provider', 'all')
        verdict_lines = [line for line in out.splitlines() if re.match(r'(AZURE|GITHUB): ', line)]
        self.assertEqual(code, 2)
        self.assertEqual(out.splitlines()[0], 'AZURE: READY')
        self.assertIn('GITHUB: BLOCKED (invalid)', out)
        self.assertIn('github.com as octo-user (gh state: error)', ' '.join(out.split()))
        self.assertIn('Account: none usable', out)
        # each provider's verdict opens its block and, since PKG-CATALOG-5 item 8, is repeated as the last lines before the exit code
        self.assertEqual(verdict_lines, ['AZURE: READY', 'GITHUB: BLOCKED (invalid)'] * 2)

    def test_an_undetermined_sign_in_names_the_reason_code(self):
        self.fakes.answer('az', 'account', 'list', out='{not json')
        code, out, _ = self.run_cli('signin', 'status', '--tenant', TENANT_A)
        self.assertEqual((code, out.splitlines()[0]), (2, 'AZURE: BLOCKED (unknown: malformed_answer)'))


class JsonFormTests(ReadableBase):
    def test_json_keeps_todays_fields_for_scripts(self):
        code, out, _ = self.run_cli('signin', 'status', '--tenant', TENANT_A, '--json')
        value = json.loads(out)
        expected = signin.status_report(TENANT_A, None, 'azure', 5)
        self.assertEqual(code, 0)
        self.assertEqual(value, expected)
        self.assertEqual(value['status'], 'ready')
        self.assertEqual(len(out.splitlines()), 1)

    def test_json_exit_code_matches_the_text_exit_code(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(tenant=TENANT_B)))
        text_code, _, _ = self.run_cli('signin', 'status', '--tenant', TENANT_A)
        json_code, out, _ = self.run_cli('signin', 'status', '--tenant', TENANT_A, '--json')
        self.assertEqual((text_code, json_code, json.loads(out)['status']), (2, 2, 'blocked'))


class WrappingTests(ReadableBase):
    def setUp(self):
        super().setUp()
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(user='alex@example.test', tenant=TENANT_A, sub='s1'),
            azure_account(user='second.person@example.test', tenant=TENANT_B, default=False, sub='s2')))

    def test_no_identifier_is_split_across_rows_at_60_80_and_120_columns(self):
        report = signin.status_report(TENANT_A, None, 'azure', 5)
        from intune_iac.readiness import placeholders_in_words
        # the screen says a command with a placeholder in words (PKG-TEMPLATE-WORDS), so the words to find are those of the rendered text
        words = set(placeholders_in_words(report['azure']['next_step']).split()) | set(placeholders_in_words(report['azure']['message']).split())
        for width in (60, 80, 120):
            code, out, _ = self.run_cli('signin', 'status', '--tenant', TENANT_A, columns=width)
            rows = out.splitlines()
            tokens = {token for row in rows for token in row.split()}
            self.assertEqual(code, 2, width)
            for guid in (TENANT_A, TENANT_B):
                self.assertIn(guid, tokens, width)
            self.assertLessEqual(words, tokens, width)
            for row in rows:
                self.assertTrue(len(row) <= width or len(row.split()) == 1, (width, row))
            # the identifiers that appear anywhere are whole GUIDs, never a part of one
            self.assertEqual(len(GUIDS.findall(out)), len(re.findall(r'[0-9a-f]{8}-', out)), width)

    def test_the_next_step_sits_on_its_own_row_under_its_label(self):
        code, out, _ = self.run_cli('signin', 'status', '--tenant', TENANT_A, columns=60)
        rows = out.splitlines()
        label = rows.index('Next step:')
        self.assertTrue(rows[label + 1].startswith('    '))
        self.assertTrue(all(not row.strip().startswith(('Next step', 'Tenant', 'Account')) for row in rows[label + 1:label + 3]))


class SafetyTests(ReadableBase):
    def test_a_hidden_name_prints_as_not_shown_and_nothing_of_it(self):
        hidden = 'alexander.morgan@contoso.onmicrosoft.com'
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=hidden)))
        code, out, err = self.run_cli('signin', 'status', '--tenant', TENANT_A)
        self.assertEqual(code, 0)
        self.assertIn('Account: <not shown> (default)', out)
        self.assertNotIn('alexander', out + err)
        self.assertNotIn('contoso', out + err)

    def test_the_output_holds_no_control_byte_even_for_a_name_that_carries_one(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='alex\x1b[31m@example.test')))
        _, out, _ = self.run_cli('signin', 'status', '--tenant', TENANT_A)
        self.assertNotIn('\x1b', out)
        self.assertTrue(all(ch == '\n' or ch.isprintable() for ch in out), repr(out))

    def test_a_credential_shaped_name_is_neither_shown_nor_in_the_verdict_code(self):
        secret = 'ghp_' + 'Q' * 30
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user=secret)))
        code, out, err = self.run_cli('signin', 'status', '--tenant', TENANT_A)
        self.assertEqual(code, 2)
        self.assertNotIn('QQQQ', out + err)
        self.assertNotIn('ghp_', out + err)
        self.assertTrue(out.splitlines()[0].startswith('AZURE: BLOCKED ('))


if __name__ == '__main__':
    unittest.main()
