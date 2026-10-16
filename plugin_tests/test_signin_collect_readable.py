"""PKG-SETUP-5D item 2: `signin collect` prints a readable text screen by default; --json keeps the frozen JSON.

The screen is built the way `signin status` is (PKG-SETUP-5C): one judgment (signin.collect), a text-only presentation made
beside the result (signin.collect_view) and rendered by signin_facts.collect_lines. Nothing of the presentation reaches the
returned object, JSON, readiness or the catalog. The cases are the golden cases (plugin_tests/signin_golden_cases.py); the
collecting child is the stand-in (plugin_tests/signin_collector.py).
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import cli, signin
from plugin_tests.signin_fakes import FakeClis, TENANT_A
from plugin_tests.signin_golden_cases import CASES, CHILD, OUT, PREEXISTING, POLICY
from plugin_tests.test_signin_golden import COLLECTOR, GOLDEN, ROOT, run_case_full

COLLECT_CASES = sorted(name for name in CASES if CASES[name][1][1] == 'collect')


def run_text(name, mode=None, made=False, width=100, extra=(), output=None):
    """(exit code, stdout, stderr) of the default (text) form of a golden case; the scratch output path is written back as OUT.

    output, when given, is a function of the scratch directory that returns the --output value to use instead; the text is then
    returned exactly as printed (nothing is written back), so a leak of that value would show.
    """
    answers, argv = CASES[name]
    fakes = FakeClis()
    for tool, first, second, out in answers:
        fakes.answer(tool, first, second, out=out)
    with tempfile.TemporaryDirectory() as scratch:
        path = str(Path(scratch) / 'out') if output is None else output(scratch)
        if name in PREEXISTING:
            Path(path).mkdir()
        args = [a.replace(OUT, path) for a in argv] + list(extra)

        def command(tenant, policy, output, descriptor):
            more = ['--made-output', output] if made else []
            return [sys.executable, '-I', COLLECTOR, str(ROOT), '--token-fd', str(descriptor), '--mode', mode or CHILD[name]] + more

        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {'PATH': fakes.path_entry() + os.pathsep + os.environ['PATH']}), \
                patch('intune_iac.signin.collector_command', command), \
                patch('shutil.get_terminal_size', return_value=os.terminal_size((width, 40))), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(args)
    fakes.cleanup()
    if output is not None:
        return code, out.getvalue(), err.getvalue()
    return code, out.getvalue().replace(path, OUT), err.getvalue().replace(path, OUT)


def rows(text):
    return text.split('\n')


def next_step(text):
    """The rows under 'Next step:' up to the blank row that ends the block."""
    lines = rows(text)
    start = lines.index('Next step:')
    block = []
    for line in lines[start + 1:]:
        if not line.strip():
            break
        block.append(line)
    return block


class DefaultFormTests(unittest.TestCase):
    def test_the_default_is_text_and_json_flag_is_the_frozen_json(self):
        for name in COLLECT_CASES:
            golden = json.loads((GOLDEN / (name + '.json')).read_text())
            code, text, err = run_case_full(name, json_flag=True)
            self.assertEqual((code, text, json.loads(err) if err else None), (golden['exit'], golden['stdout'], golden.get('stderr')), name)

    def test_the_text_form_is_not_json_and_exits_as_the_json_does(self):
        for name in COLLECT_CASES:
            golden = json.loads((GOLDEN / (name + '.json')).read_text())
            code, text, err = run_text(name)
            self.assertEqual(code, golden['exit'], name)
            if golden['output'] is None:
                self.assertEqual(text, '', name)  # an early refusal stays a JSON error on stderr
                self.assertEqual(json.loads(err), golden['stderr'], name)
                continue
            self.assertEqual(err, '', name)
            self.assertFalse(text.lstrip().startswith('{'), name)
            self.assertTrue(rows(text)[0].startswith('COLLECT: '), name)

    def test_the_verdict_line_is_first_and_names_the_reason(self):
        expected = {'collect_ok': 'COLLECT: COLLECTED', 'collect_withheld_full_token': 'COLLECT: FAILED (collector_output_withheld)',
                    'collect_withheld_shape': 'COLLECT: FAILED (collector_output_withheld)',
                    'collect_partial_expired': 'COLLECT: PARTIAL (token_expired)',
                    'collect_partial_denied': 'COLLECT: PARTIAL (access_denied)',
                    'collect_child_fails': 'COLLECT: FAILED (collector_failed)',
                    'collect_expired_token': 'COLLECT: BLOCKED (expired)', 'collect_not_signed_in': 'COLLECT: BLOCKED (not_signed_in)',
                    'collect_wrong_tenant_listing': 'COLLECT: BLOCKED (wrong_tenant)',
                    'collect_opaque_token': 'COLLECT: BLOCKED (account_binding_unavailable)',
                    'collect_token_without_account_claim': 'COLLECT: BLOCKED (account_binding_unavailable)'}
        for name, line in expected.items():
            self.assertEqual(rows(run_text(name)[1])[0], line, name)

    def test_no_text_carries_a_token_or_a_key_of_the_json(self):
        for name in COLLECT_CASES:
            text = run_text(name)[1]
            for secret in ('eyJ', 'sigsig', 'ghp_', 'accessToken'):
                self.assertNotIn(secret, text, (name, secret))
            for key in ('"status"', '"next_step"', 'collector_started'):
                self.assertNotIn(key, text, (name, key))


class SectionTests(unittest.TestCase):
    def test_a_collected_result_says_whether_the_output_folder_exists(self):
        absent = run_text('collect_ok')[1]
        self.assertIn('Output folder: %s (not present after this run)' % OUT, rows(absent))
        present = run_text('collect_ok', made=True)[1]
        self.assertIn('Output folder: %s (exists after this run)' % OUT, rows(present))

    def test_the_childs_exit_and_the_coverage_per_section_have_their_own_rows(self):
        text = run_text('collect_partial_expired')[1]
        self.assertIn('Collecting command: exit 2', rows(text))
        self.assertIn('Coverage:', rows(text))
        self.assertIn('    policies: complete', rows(text))
        self.assertIn('    settings: partial (token_expired)', rows(text))
        self.assertIn('Collecting command: exit 0', rows(run_text('collect_ok')[1]))

    def test_a_blocked_result_says_no_collecting_command_started(self):
        text = run_text('collect_not_signed_in')[1]
        self.assertIn('Collecting command: not started', rows(text))
        self.assertNotIn('Coverage:', rows(text))

    def test_the_exit_code_row_says_what_the_code_means(self):
        self.assertIn('Exit code 2: partial', run_text('collect_partial_expired')[1])
        self.assertIn('Exit code 2: blocked', run_text('collect_not_signed_in')[1])
        self.assertIn('Exit code 0: collected', run_text('collect_ok')[1])
        self.assertIn('Exit code 3: failed', run_text('collect_child_fails')[1])


class WordingTests(unittest.TestCase):
    def test_a_printed_token_leads_with_stop_and_report_before_any_rerun(self):
        block = next_step(run_text('collect_withheld_full_token')[1])
        joined = '\n'.join(block)
        self.assertTrue(block[0].lstrip('0123456789. ').startswith('Stop and report'), block[0])
        self.assertIn('printed the access token', block[0])
        self.assertLess(joined.index('Stop and report'), joined.index('intune-iac signin collect'))
        self.assertNotIn('then run', joined)

    def test_text_that_is_not_the_whole_token_does_not_claim_the_token_was_printed(self):
        text = run_text('collect_withheld_shape')[1]
        self.assertNotIn('Stop and report', text)
        self.assertNotIn('printed the access token', text)
        self.assertIn('intune-iac signin collect', text)

    def test_a_partial_result_attributes_the_expiry_to_the_collecting_command_without_a_joined_sentence(self):
        text = run_text('collect_partial_expired')[1]
        self.assertIn('The collecting command reported the token as expired', text)
        self.assertNotIn('The service said', text)
        self.assertNotIn('then To', text)
        self.assertNotIn('; then ', ' '.join(next_step(text)).replace('; then run', ''))
        block = next_step(text)
        self.assertTrue(any(row.lstrip('0123456789. ').startswith('To collect again, run:') for row in block), block)
        self.assertIn('az login --tenant %s' % TENANT_A, ' '.join(text.split()))

    def test_a_partial_denied_result_says_the_collecting_command_reported_it(self):
        text = run_text('collect_partial_denied')[1]
        self.assertIn('The collecting command reported that a read was denied', text)
        self.assertNotIn('The service denied', text)
        self.assertNotIn('then To', text)

    def test_the_rerun_names_a_new_folder_and_the_account_only_when_one_was_given(self):
        rerun = 'intune-iac signin collect --tenant %s --policy %s --output NEW_DIR' % (TENANT_A, POLICY)
        self.assertIn(rerun + ' (a folder that does not exist yet)', ' '.join(run_text('collect_partial_expired')[1].split()))
        text = ' '.join(run_text('collect_partial_expired', extra=['--account', 'alex@example.test'])[1].split())
        self.assertIn('--account NAME (the account you named)', text)
        self.assertNotIn('alex@example.test', text)

    def test_the_binding_refusal_names_which_reason_applied(self):
        opaque = ' '.join(run_text('collect_opaque_token')[1].split())
        self.assertIn('the token is opaque', opaque)
        self.assertNotIn('carries none of', opaque)
        self.assertNotIn('or carries', opaque)
        none = ' '.join(run_text('collect_token_without_account_claim')[1].split())
        self.assertIn('it carries none of the upn, unique_name or appid claims', none)
        self.assertNotIn('is opaque', none)

    def test_a_blocked_sign_in_keeps_its_next_step_and_never_weakens_the_refusal(self):
        for name in ('collect_not_signed_in', 'collect_expired_token', 'collect_wrong_tenant_listing', 'collect_opaque_token'):
            text = run_text(name)[1]
            self.assertIn('az login --tenant %s' % TENANT_A, ' '.join(text.split()), name)
            self.assertNotIn('COLLECTED', text, name)

    def test_long_rows_wrap_to_the_width(self):
        for name in ('collect_partial_expired', 'collect_withheld_full_token', 'collect_opaque_token'):
            for line in rows(run_text(name, width=60)[1]):
                words = line.split()
                self.assertTrue(len(line) <= 60 or len(words) <= 2 or max(map(len, words)) > 40, (name, line))


class RouteTests(unittest.TestCase):
    def test_the_judgment_returns_the_plain_result_and_the_presentation_is_beside_it(self):
        self.assertTrue(hasattr(signin, 'collect_view'))
        answers, argv = CASES['collect_ok']
        fakes = FakeClis()
        for tool, first, second, out in answers:
            fakes.answer(tool, first, second, out=out)
        with tempfile.TemporaryDirectory() as scratch, \
                patch.dict(os.environ, {'PATH': fakes.path_entry() + os.pathsep + os.environ['PATH']}), \
                patch('intune_iac.signin.collector_command',
                      lambda t, p, o, d: [sys.executable, '-I', COLLECTOR, str(ROOT), '--token-fd', str(d), '--mode', 'ok']):
            output = str(Path(scratch) / 'out')
            plain = signin.collect(TENANT_A, POLICY, output, deadline=5, collect_deadline=20)
            viewed, presentation = signin.collect_view(TENANT_A, POLICY, output, deadline=5, collect_deadline=20)
        fakes.cleanup()
        self.assertIs(type(plain), dict)
        self.assertEqual(viewed, plain)
        self.assertEqual(json.dumps(viewed, sort_keys=True), json.dumps(plain, sort_keys=True))
        self.assertIsInstance(presentation, dict)
        for key in presentation:
            self.assertNotIn(key, plain)

    def test_only_the_text_route_of_collect_asks_for_a_presentation(self):
        calls = []
        real = signin.collect_view

        def spy(*a, **k):
            calls.append(1)
            return real(*a, **k)

        with patch('intune_iac.signin.collect_view', spy):
            run_text('collect_ok')
            self.assertEqual(len(calls), 1)
            run_case_full('collect_ok', json_flag=True)
            self.assertEqual(len(calls), 1)


class OutputPathDisplayTests(unittest.TestCase):
    """Round 2: the output path is user input; the text screen shows it only when it is safe to, else a fixed placeholder."""

    def shown(self, path_of, name='collect_ok', **kw):
        code, text, err = run_text(name, output=path_of, **kw)
        return code, text, err

    def test_the_delivered_access_token_used_as_the_output_path_is_never_printed(self):
        from plugin_tests.signin_golden_cases import _token
        canary = _token(upn='alex@example.test', tid=TENANT_A)
        for name in ('collect_ok', 'collect_partial_expired', 'collect_withheld_full_token', 'collect_child_fails'):
            code, text, err = self.shown(lambda scratch: canary, name)
            self.assertNotIn(canary, text + err, name)
            self.assertNotIn(canary[:30], text + err, name)
            self.assertIn('<the output path is not shown: it is shaped like a credential>', ' '.join(text.split()), name)
        # the rerun command never held the path: it names a placeholder folder
        self.assertIn('--output NEW_DIR', ' '.join(self.shown(lambda scratch: canary, 'collect_partial_expired')[1].split()))

    def test_a_credential_shaped_component_or_prefix_is_not_shown(self):
        for path in ('ghp_abc1234', 'a1' * 20, 'eyJhbGciOiJub25lIn0'):
            text = self.shown(lambda scratch, p=path: scratch + '/' + p if p != 'eyJhbGciOiJub25lIn0' else p)[1]
            self.assertNotIn(path, text)
            self.assertIn('is shaped like a credential', ' '.join(text.split()))

    def test_a_newline_cannot_forge_a_row_or_a_verdict(self):
        path = lambda scratch: scratch + '/out\nCOLLECT: COLLECTED\nNext step:'
        code, text, err = self.shown(path, 'collect_partial_expired')
        lines = rows(text)
        self.assertEqual(lines[0], 'COLLECT: PARTIAL (token_expired)')
        self.assertEqual(sum(1 for line in lines if line.startswith('COLLECT: ')), 1)
        self.assertEqual(lines.count('Next step:'), 1)
        self.assertIn('<the output path is not shown: it holds characters that are not printable>', ' '.join(text.split()))

    def test_a_terminal_escape_or_c1_character_is_not_printed(self):
        for bad in ('\x1b[2J', '\x7f', '\x85', '\r'):
            text = self.shown(lambda scratch, b=bad: scratch + '/out' + b)[1]
            for char in ('\x1b', '\x7f', '\x85', '\r'):
                self.assertNotIn(char, text, repr(bad))
            self.assertIn('it holds characters that are not printable', ' '.join(text.split()))

    def test_a_path_past_the_display_limit_is_not_shown(self):
        text = self.shown(lambda scratch: scratch + '/' + 'ab-' * 80)[1]
        self.assertIn('<the output path is not shown: it is longer than this display allows>', ' '.join(text.split()))

    def test_an_ordinary_path_prints_exactly_as_before(self):
        code, text, err = run_text('collect_ok')
        self.assertEqual(rows(text)[1], 'Output folder: %s (not present after this run)' % OUT)
        scratchy = self.shown(lambda scratch: scratch + '/my-folder.v2')[1]
        self.assertRegex(rows(scratchy)[1], r'^Output folder: /.*/my-folder\.v2 \(not present after this run\)$')

    def test_the_json_form_still_prints_the_path_json_escaped(self):
        # A recorded limit, not part of this fix: --json is frozen byte for byte and keeps the path as given.
        code, text, err = run_case_full('collect_ok', json_flag=True)
        self.assertIn('"output": "{OUT}"', text)


class BindingKindTests(unittest.TestCase):
    def kind(self, **claims):
        from plugin_tests.signin_golden_cases import _token
        return signin._binding_kind(_token(**claims))

    def test_a_present_claim_is_unusable_whatever_its_value(self):
        for claims in ({'upn': 123}, {'upn': ''}, {'appid': None}, {'unique_name': ['x']}, {'unique_name': ''}, {'appid': False}):
            self.assertEqual(self.kind(tid=TENANT_A, **claims), 'unusable_claim', claims)

    def test_no_claim_only_when_all_three_are_absent(self):
        self.assertEqual(self.kind(tid=TENANT_A), 'no_claim')
        self.assertEqual(self.kind(tid=TENANT_A, oid='x'), 'no_claim')

    def test_a_token_that_is_not_a_jwt_is_opaque(self):
        self.assertEqual(signin._binding_kind('opaque-' + 'A' * 40), 'opaque')


if __name__ == '__main__':
    unittest.main()
