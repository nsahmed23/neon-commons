"""PKG-EVIDENCE-FRESH-2: evidence views fall back, loose-file inspect, POSIX boot continuity, Windows read-first reopen.

Shares the stand-ins of test_worker_evidence_freshness_floor (no Docker import); the wall is injected through time.time.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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


if __name__ == '__main__':
    unittest.main()
