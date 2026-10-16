"""PKG-SETUP-5C item 4: `start` says which sign-in is which, says once that it is a report, and prints no empty heading.

The Azure CLI is a fake on a temporary search path; the working directory holds only the example context.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import cli, entry
from plugin_tests.signin_fakes import FakeClis, azure_account, azure_list

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_TENANT = json.loads((ROOT / 'examples/context.json').read_text())['tenant_id']
PRODUCT_WORDS = 'this product has no live connection (not authenticated)'
CLI_LABEL = "Azure CLI sign-in (the Azure CLI's own, not a connection of this product): Signed in to tenant"
REPORT_SENTENCE = ('This screen is a report and exits 0 whatever it finds; for a pass or fail exit code run: '
                   'intune-iac signin status --tenant %s' % CONTEXT_TENANT)  # a command row carries no closing full stop


class StartWordingTests(unittest.TestCase):
    def setUp(self):
        self.fakes = FakeClis()
        self.addCleanup(self.fakes.cleanup)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        shutil.copyfile(ROOT / 'examples/context.json', self.directory / 'context.json')
        patcher = patch.dict(os.environ, {'PATH': self.fakes.path_entry() + os.pathsep + os.environ.get('PATH', '')})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(tenant=CONTEXT_TENANT)))

    def start(self, *extra, columns=100):
        out, err = io.StringIO(), io.StringIO()
        with patch('shutil.get_terminal_size', return_value=os.terminal_size((columns, 40))), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(['start', str(self.directory), *extra])
        return code, out.getvalue(), err.getvalue()

    def flat(self, *extra):
        code, out, err = self.start(*extra)
        self.assertEqual((code, err), (0, ''))
        return ' '.join(out.split())

    def test_the_products_own_connection_and_the_azure_cli_sign_in_are_told_apart(self):
        text = self.flat('--goal', 'discover', '--check-signin', 'azure')
        self.assertIn(PRODUCT_WORDS, text)
        self.assertNotIn('not authenticated (no live connection)', text)
        self.assertIn(CLI_LABEL + ' ' + CONTEXT_TENANT, text)
        # the same label in the Found row of the integration, never the bare lower-case "azure sign in"
        self.assertNotIn('azure sign in:', text)
        self.assertIn('Azure CLI sign-in (the Azure CLI\'s own, not a connection of this product): Signed in', text)

    def test_the_report_exit_and_the_pass_or_fail_command_are_said_once(self):
        text = self.flat('--goal', 'discover', '--check-signin', 'azure')
        self.assertEqual(text.count(REPORT_SENTENCE), 1)
        self.assertEqual(text.count('exits 0'), 1)

    def test_the_command_it_names_is_one_the_parser_accepts(self):
        args = cli.parser().parse_args(['signin', 'status', '--tenant', CONTEXT_TENANT])
        self.assertEqual((args.command, args.signin_command, args.tenant), ('signin', 'status', CONTEXT_TENANT))

    def test_without_a_sign_in_check_the_screen_makes_no_claim_about_the_exit_code(self):
        text = self.flat('--goal', 'discover')
        self.assertNotIn('exits 0', text)
        self.assertNotIn('Azure CLI sign-in', text)

    def test_a_survey_with_no_next_action_prints_no_empty_next_heading(self):
        code, out, _ = self.start('--json')
        self.assertEqual(json.loads(out)['next_actions'], [])
        lines = self.start()[1].splitlines()
        self.assertNotIn('NEXT', lines)
        self.assertIn('MISSING', lines)

    def test_a_survey_with_a_next_action_still_prints_the_heading(self):
        value = {'directory': '/work', 'items': [], 'next_actions': ['Start from a supported export: intune-iac wizard'],
                 'missing': ['x'], 'skipped_links': [], 'truncated': False}
        self.assertIn('NEXT', entry.start_lines(value, 80))
        self.assertNotIn('NEXT', entry.start_lines(dict(value, next_actions=[]), 80))


if __name__ == '__main__':
    unittest.main()
