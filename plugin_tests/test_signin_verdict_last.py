"""PKG-CATALOG-5 item 8: `signin status` repeats each provider's verdict as the last line before the exit-code line.

The provider blocks are longer than a 20-row pane, which then shows only their tail (journey 32 run 4, frames 21 to 23: the
verdict scrolled off). One summary line per provider, built from the same judgment as the verdict line that opens its block and
never wrapped, closes the screen. The `--json` form is frozen (test_signin_golden); every fake sign-in is a stand-in.
"""
import re
import unittest

from intune_iac import signin, signin_facts
from plugin_tests.signin_fakes import TENANT_A, TENANT_B, azure_account, azure_list, github_hosts
from plugin_tests.test_signin_readable import ReadableBase

VERDICT = re.compile(r'^(AZURE|GITHUB): (READY|REPORTED|BLOCKED)')
PANE = 18  # a 20-row pane keeps 18 rows of output and the exit and prompt rows


class VerdictLastTests(ReadableBase):
    def screen(self, *argv, columns=60):
        code, out, err = self.run_cli(*argv, columns=columns)
        self.assertEqual(err, '')
        return code, out.rstrip('\n').split('\n')

    def check(self, argv, expected, columns=60):
        code, lines = self.screen(*argv, columns=columns)
        verdicts = [line for line in lines if VERDICT.match(line)]
        self.assertEqual(verdicts, expected + expected, (argv, 'each verdict opens its block and closes the screen once'))
        self.assertTrue(lines[-1].startswith('Exit code %d: ' % code), lines[-1])
        closing = lines[-1 - len(expected):-1]
        self.assertEqual(closing, expected, 'the verdict lines are the last lines before the exit-code line, never wrapped')
        for line in expected:
            self.assertIn(line, lines[-PANE:], 'every provider verdict is in the last 18 rows')
        return code, lines

    def test_a_usable_sign_in_closes_with_its_verdict(self):
        self.check(['signin', 'status', '--tenant', TENANT_A], ['AZURE: READY'])

    def test_a_sign_in_in_another_tenant_closes_with_its_verdict(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(tenant=TENANT_B)))
        self.check(['signin', 'status', '--tenant', TENANT_A], ['AZURE: BLOCKED (wrong_tenant)'])

    def test_several_accounts_close_with_the_verdict_journey_32_frame_21_lost(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(
            azure_account(user='alex@example.test', tenant=TENANT_A, sub='s1'),
            azure_account(user='sam@example.test', tenant=TENANT_A, default=False, sub='s2')))
        code, lines = self.check(['signin', 'status', '--tenant', TENANT_A], ['AZURE: BLOCKED (several_accounts)'])
        self.assertEqual(code, 2)
        # the long blocks still scroll the first verdict off a 20-row pane; the closing line is what the pane shows
        self.assertNotIn('AZURE: BLOCKED (several_accounts)', lines[-PANE:-2])

    def test_the_finer_text_codes_close_the_screen_too(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(), azure_account(user='sam@example.test', default=True)))
        self.check(['signin', 'status', '--tenant', TENANT_A], ['AZURE: BLOCKED (two_defaults)'])
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='ghp_abc1234')))
        _, lines = self.check(['signin', 'status', '--tenant', TENANT_A], ['AZURE: BLOCKED (credential_shaped_name)'])
        self.assertNotIn('ghp_', '\n'.join(lines))
        self.fakes.answer('az', 'account', 'list', out='{not json')
        self.check(['signin', 'status', '--tenant', TENANT_A], ['AZURE: BLOCKED (unknown: malformed_answer)'])

    def test_a_report_without_a_tenant_closes_with_its_verdict(self):
        self.check(['signin', 'status'], ['AZURE: REPORTED (no tenant was given to compare)'], columns=40)

    def test_two_providers_close_with_both_verdicts_in_order_journey_32_frame_23(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'octo-user', 'error', True)), code=1)
        code, lines = self.check(['signin', 'status', '--tenant', TENANT_A, '--provider', 'all'],
                                 ['AZURE: READY', 'GITHUB: BLOCKED (invalid)'])
        self.assertEqual(code, 2)
        self.assertEqual(lines[-3:], ['AZURE: READY', 'GITHUB: BLOCKED (invalid)', 'Exit code 2: blocked (0 means ready).'])

    def test_every_width_keeps_the_closing_lines_whole(self):
        self.fakes.answer('gh', 'auth', 'status', out=github_hosts(('github.com', 'octo-user', 'error', True)), code=1)
        for columns in (40, 60, 80, 120):
            self.check(['signin', 'status', '--tenant', TENANT_A, '--provider', 'all'], ['AZURE: READY', 'GITHUB: BLOCKED (invalid)'],
                       columns=columns)

    def test_the_json_form_has_no_verdict_line(self):
        code, out, _ = self.run_cli('signin', 'status', '--tenant', TENANT_A, '--json')
        self.assertEqual(code, 0)
        self.assertNotRegex(out, r'(AZURE|GITHUB): ')
        self.assertEqual(out.count('\n'), 1)


class FromTheSameJudgmentTests(ReadableBase):
    def view(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(), azure_account(user='sam@example.test', default=True)))
        return signin.status_view(TENANT_A, None, 'azure', 5)

    def test_the_closing_line_is_the_opening_line_built_once(self):
        report, shown = self.view()
        lines = signin_facts.status_lines(report, 60, 2, shown)
        self.assertEqual(lines[0], 'AZURE: BLOCKED (two_defaults)')
        self.assertEqual(lines[-2], lines[0])
        self.assertEqual(lines[-1], 'Exit code 2: blocked (0 means ready).')

    def test_without_a_presentation_both_lines_use_the_canonical_status(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(), azure_account(user='sam@example.test', default=True)))
        report = signin.status_report(TENANT_A, None, 'azure', 5)
        lines = signin_facts.status_lines(report, 60, 2)
        self.assertEqual(lines[0], 'AZURE: BLOCKED (several_accounts)')
        self.assertEqual(lines[-2], lines[0])


if __name__ == '__main__':
    unittest.main()
