"""PKG-EVIDENCE-FRESH-2: evidence views fall back, loose-file inspect, POSIX boot continuity, Windows read-first reopen.

Shares the stand-ins of test_worker_evidence_freshness_floor (no Docker import); the wall is injected through time.time.
"""
import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from intune_iac import worker_evidence as contract
from intune_iac import workbench_evidence_views as views
from intune_iac import worker_evidence_posix as host
from intune_iac.io import AppError


class ViewFallbackTests(unittest.TestCase):
    def read_with(self, code):
        calls = []

        def reopen(root, request_sha256, policy, verifier, historical=False):
            calls.append(historical)
            if not historical:
                raise AppError(code, 'refused')
            return {'tenant_id': 'tenant', 'object_id': 'object', 'baseline_admissible': False, 'historical_only': True}

        store = SimpleNamespace(tenant_id='tenant')
        with patch.object(host, 'load', return_value={}), patch.object(host, 'DetachedVerifier', return_value=None), \
                patch.object(host, 'reopen', side_effect=reopen):
            result = views._read(store, 'object', '/evidence', 'a' * 64, '/trust', '/verifier', '/scratch')
        return result, calls

    def test_an_unrecordable_time_falls_back_to_the_historical_read(self):
        result, calls = self.read_with('worker_evidence_clock_unrecorded')
        self.assertEqual(calls, [False, True])
        self.assertFalse(result['baseline_admissible'])

    def test_an_unrelated_refusal_still_propagates(self):
        with self.assertRaises(AppError) as raised:
            self.read_with('worker_evidence_signature_invalid')
        self.assertEqual(raised.exception.code, 'worker_evidence_signature_invalid')


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'intune-worker-evidence.py'


def run_cli(*argv):
    spec = importlib.util.spec_from_file_location('worker_evidence_cli_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out, err = io.StringIO(), io.StringIO()
    with patch.object(sys, 'argv', ['intune-worker-evidence.py', *argv]), redirect_stdout(out), redirect_stderr(err):
        code = module.main()
    return code, out.getvalue(), err.getvalue()


class LooseFileInspectTests(unittest.TestCase):
    COMMON = ['--trust', 'trust.json', '--verifier', 'verifier.json', '--scratch', 'scratch']

    def test_non_historical_inspect_requires_a_store(self):
        code, out, err = run_cli('inspect', '--envelope', 'e.json', '--request', 'r.json', *self.COMMON)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(err)['code'], 'worker_evidence_inspect_requires_store')

    def test_historical_inspect_is_still_offered(self):
        with patch.object(host, 'load', return_value={}), patch.object(host, 'DetachedVerifier', return_value=None), \
                patch.object(contract, 'verify_envelope') as verify:
            verify.return_value.result.return_value = {'historical_only': True}
            code, out, err = run_cli('inspect', '--historical', '--envelope', 'e.json', '--request', 'r.json', *self.COMMON)
        self.assertEqual(code, 0, err)
        self.assertIs(verify.call_args.kwargs['historical'], True)

    def test_the_post_assembly_check_is_historical(self):
        with patch.object(host, 'load', return_value={}), patch.object(host, 'DetachedVerifier', return_value=None), \
                patch.object(host, 'read', return_value=bytes(64)), patch.object(host, 'write_new'), \
                patch.object(contract, 'verify_envelope') as verify:
            verify.return_value.result.return_value = {'historical_only': True}
            code, out, err = run_cli('assemble', '--statement', 's.json', '--signature', 'sig', '--request', 'r.json',
                                     '--output', 'out.json', *self.COMMON)
        self.assertEqual(code, 0, err)
        self.assertIs(verify.call_args.kwargs['historical'], True)


if __name__ == '__main__':
    unittest.main()
