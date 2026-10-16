"""PKG-SETUP-5C round 2: `signin status --json` (and the collect refusal) keep every former key and value.

The golden files were captured from the CLI at 5404dd5. The head may add only the keys in ADDITIVE_KEYS (detail_code, rule,
readable_message); every key the golden has keeps its value exactly, so a script that branches on status or reads message sees
no change. The readable text view renders from the additive keys.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import cli
from plugin_tests.signin_fakes import FakeClis
from plugin_tests.signin_golden_cases import ADDITIVE_KEYS, CASES, OUT

GOLDEN = Path(__file__).resolve().parent / 'fixtures' / 'signin_golden'
# The cases whose new distinction travels in additive keys, and the key values they must carry.
ADDED = {
    'two_defaults': {'detail_code': 'two_defaults'},
    'two_default_rows_one_account': {'detail_code': 'two_defaults'},
    'cred_token_prefix': {'detail_code': 'credential_shaped_name', 'rule': 'token_prefix'},
    'cred_jwt_prefix': {'detail_code': 'credential_shaped_name', 'rule': 'token_prefix'},
    'cred_unbroken_run': {'detail_code': 'credential_shaped_name', 'rule': 'unbroken_run'},
    'cred_prefix_and_run': {'detail_code': 'credential_shaped_name', 'rule': 'token_prefix'},
    'hidden_capitals_and_bang_usable': {'rule': 'shape'},
    'hidden_long_usable': {'rule': 'length'},
    'cred_github': {'detail_code': 'credential_shaped_name', 'rule': 'token_prefix'},
}


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
    return code, json.loads(out.getvalue())


def additions(old, new, path=''):
    """Compare a head value with the golden one: every golden key keeps its value; returns {path: value} of the keys that are new."""
    found = {}
    if isinstance(old, dict):
        assert isinstance(new, dict), path
        for key, value in old.items():
            assert key in new, '%s: former key %r is gone' % (path, key)
            found.update(additions(value, new[key], '%s/%s' % (path, key)))
        for key in new:
            if key not in old:
                found['%s/%s' % (path, key)] = new[key]
    elif isinstance(old, list):
        assert isinstance(new, list) and len(old) == len(new), path
        for index, (a, b) in enumerate(zip(old, new)):
            found.update(additions(a, b, '%s[%d]' % (path, index)))
    else:
        assert old == new, '%s: former value %r is now %r' % (path, old, new)
    return found


class GoldenTests(unittest.TestCase):
    def test_every_case_has_a_golden_file_and_no_golden_file_is_orphaned(self):
        self.assertEqual({p.stem for p in GOLDEN.glob('*.json')}, set(CASES))

    def test_every_former_key_and_value_is_unchanged_and_only_the_listed_keys_are_new(self):
        for name in CASES:
            golden = json.loads((GOLDEN / (name + '.json')).read_text())
            code, value = run_case(name)
            self.assertEqual(code, golden['exit'], name)
            added = additions(golden['output'], value)
            self.assertTrue({p.rsplit('/', 1)[1] for p in added} <= ADDITIVE_KEYS, (name, sorted(added)))

    def test_the_new_distinctions_ride_in_the_additive_keys(self):
        for name, expected in ADDED.items():
            added = additions(json.loads((GOLDEN / (name + '.json')).read_text())['output'], run_case(name)[1])
            seen = {}
            for path, value in added.items():
                seen.setdefault(path.rsplit('/', 1)[1], value)
            for key, value in expected.items():
                self.assertEqual(seen.get(key), value, (name, key, added))

    def test_the_former_inner_codes_are_still_the_status_values(self):
        for name, status in (('two_defaults', 'several_accounts'), ('two_default_rows_one_account', 'several_accounts'),
                             ('cred_token_prefix', 'unknown'), ('cred_unbroken_run', 'unknown')):
            self.assertEqual(run_case(name)[1]['azure']['status'], status, name)
        self.assertEqual(run_case('cred_github')[1]['github']['status'], 'unknown')
        self.assertEqual(run_case('collect_opaque_token')[1]['signin']['status'], 'account_binding_unavailable')

    def test_the_golden_files_hold_no_token_or_hidden_name(self):
        blob = ''.join(p.read_text() for p in GOLDEN.glob('*.json'))
        for secret in ('ghp_', 'alexander', 'contoso.onmicrosoft', 'AAAAAAAA', 'eyJ', 'sigsig'):
            self.assertNotIn(secret, blob)


if __name__ == '__main__':
    unittest.main()
