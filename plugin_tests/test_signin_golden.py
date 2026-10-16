"""PKG-SETUP-5C round 3: `signin status --json` and the `signin collect` refusal print exactly the form of 5404dd5.

The golden files were captured from the real CLI at 5404dd5. The whole JSON document must be equal, key for key and value for
value: no new key at all. The finer code, the one rule and the readable sentence are for the text view only, built from a
separate presentation of the verdict (signin_facts.presentation) and never serialized.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import cli, signin_facts
from plugin_tests.signin_fakes import FakeClis
from plugin_tests.signin_golden_cases import CASES, OUT

GOLDEN = Path(__file__).resolve().parent / 'fixtures' / 'signin_golden'
CANONICAL_KEYS = {'provider', 'status', 'usable', 'tenant_wanted', 'signed_in', 'message', 'next_step'}


def run_case(name):
    answers, argv = CASES[name]
    fakes = FakeClis()
    for tool, first, second, out in answers:
        fakes.answer(tool, first, second, out=out)
    with tempfile.TemporaryDirectory() as scratch:
        args = [a.replace(OUT, str(Path(scratch) / 'out')) for a in argv]
        if args[1] == 'status':
            args.append('--json')
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {'PATH': fakes.path_entry() + os.pathsep + os.environ['PATH']}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(args)
    fakes.cleanup()
    return code, out.getvalue()


class GoldenTests(unittest.TestCase):
    def test_every_case_has_a_golden_file_and_no_golden_file_is_orphaned(self):
        self.assertEqual({p.stem for p in GOLDEN.glob('*.json')}, set(CASES))

    def test_the_whole_json_document_equals_the_5404dd5_document_for_every_case(self):
        for name in CASES:
            golden = json.loads((GOLDEN / (name + '.json')).read_text())
            code, text = run_case(name)
            self.assertEqual(code, golden['exit'], name)
            self.assertEqual(json.loads(text), golden['output'], name)

    def test_no_additive_key_appears_anywhere_in_any_document(self):
        for name in CASES:
            text = run_case(name)[1]
            for key in ('detail_code', 'readable_message', '"rule"', 'presentation', 'notes'):
                self.assertNotIn(key, text, (name, key))

    def test_the_former_inner_codes_are_the_status_values(self):
        for name, status in (('two_defaults', 'several_accounts'), ('two_default_rows_one_account', 'several_accounts'),
                             ('cred_token_prefix', 'unknown'),
                             ('cred_unbroken_run', 'unknown')):
            self.assertEqual(json.loads(run_case(name)[1])['azure']['status'], status, name)
        self.assertEqual(json.loads(run_case('cred_github')[1])['github']['status'], 'unknown')

    def test_the_verdicts_carry_only_the_canonical_keys(self):
        from intune_iac import signin
        answers, _ = CASES['cred_token_prefix']
        fakes = FakeClis()
        for tool, first, second, out in answers:
            fakes.answer(tool, first, second, out=out)
        with patch.dict(os.environ, {'PATH': fakes.path_entry() + os.pathsep + os.environ['PATH']}):
            report = signin.status_report('11111111-1111-4111-8111-111111111111', None, 'azure', 5)
        fakes.cleanup()
        self.assertEqual(set(report['azure']), CANONICAL_KEYS)
        self.assertEqual(set(report['azure']), set(json.loads(json.dumps(report))['azure']))
        # the presentation is separate, and reaches the text view only
        self.assertEqual(signin_facts.presentation(report['azure'])['code'], 'credential_shaped_name')

    def test_the_golden_files_hold_no_token_or_hidden_name(self):
        blob = ''.join(p.read_text() for p in GOLDEN.glob('*.json'))
        for secret in ('ghp_', 'alexander', 'contoso.onmicrosoft', 'AAAAAAAA', 'eyJ', 'sigsig', 'alex.password'):
            self.assertNotIn(secret, blob)


if __name__ == '__main__':
    unittest.main()
