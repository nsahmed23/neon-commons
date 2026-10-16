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

import sqlite3
import tempfile
from intune_iac import clock
from intune_iac import worker_evidence as contract
from intune_iac import workbench_evidence_views as views
from intune_iac import worker_evidence_posix as host
from intune_iac.io import AppError, digest
from plugin_tests.test_worker_evidence_freshness_floor import OK, T, expiring, make_policy, make_request, restart, stand_ins, wall


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

    def test_a_backward_wall_hold_falls_back_to_the_historical_read(self):
        result, calls = self.read_with('worker_evidence_clock_moved_backward')
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


class PosixBootContinuityTests(unittest.TestCase):
    """A receipt admitted in one boot is not current in another until its window closes; a closed window still wins."""

    def setUp(self):
        self.addCleanup(clock.reset_process_anchor)
        clock.reset_process_anchor()
        self.addCleanup(patch.stopall)
        stand_ins()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'store'; self.root.mkdir(mode=0o700)
        self.policy = make_policy(); self.req = make_request(self.policy)
        with wall(T + 1):
            host.ingest(self.root, expiring(self.req), self.req, self.policy, OK)

    def later(self, at, session, historical=False):
        return restart(kind='posix', root=str(self.root), wall=at, historical=historical, session=session)

    def test_another_boot_holds_current_status_until_the_window_closes(self):
        self.assertEqual(self.later(T + 5, 'other'), {'ok': False, 'code': 'worker_evidence_clock_continuity_lost'})

    def test_a_closed_window_still_wins_over_the_hold(self):
        self.assertEqual(self.later(T + 20, 'other'), {'ok': False, 'code': 'worker_evidence_expired'})

    def test_another_boot_still_reads_history(self):
        self.assertEqual(self.later(T + 5, 'other', historical=True), {'ok': True, 'baseline_admissible': False})

    def test_a_new_process_in_the_same_boot_is_unchanged(self):
        self.assertEqual(self.later(T + 5, 'real'), {'ok': True, 'baseline_admissible': True})

    def test_a_receipt_with_no_recorded_session_cannot_be_carried(self):
        with sqlite3.connect(self.root / 'evidence.sqlite3') as db:
            db.execute('DROP TABLE IF EXISTS received_session')
        self.assertEqual(self.later(T + 5, 'real'), {'ok': False, 'code': 'worker_evidence_clock_continuity_lost'})

    OTHER_BOOT = {'boot_id': 'another-boot', 'domain': 'd', 'boottime': 5.0}

    def session_rows(self):
        with sqlite3.connect(self.root / 'evidence.sqlite3') as db:
            return db.execute('SELECT * FROM received_session').fetchall()

    def test_a_re_ingest_in_another_boot_cannot_erase_the_boot_boundary(self):
        before = self.session_rows()
        self.assertEqual(len(before), 1)
        with patch.object(clock, 'session', return_value=self.OTHER_BOOT), wall(T + 5):
            with self.assertRaises(AppError) as held:
                host.reopen(self.root, digest(self.req), self.policy, OK)
            self.assertEqual(held.exception.code, 'worker_evidence_clock_continuity_lost')
            with self.assertRaises(AppError) as refused:  # the identical evidence, ingested again in the new boot
                host.ingest(self.root, expiring(self.req), self.req, self.policy, OK)
            self.assertEqual(refused.exception.code, 'worker_evidence_clock_continuity_lost')
            self.assertEqual(self.session_rows(), before)  # no row changed
            with self.assertRaises(AppError) as still:
                host.reopen(self.root, digest(self.req), self.policy, OK)
            self.assertEqual(still.exception.code, 'worker_evidence_clock_continuity_lost')

    def test_an_identical_re_ingest_in_the_admitting_boot_stays_idempotent(self):
        before = self.session_rows()
        with wall(T + 5):
            again = host.ingest(self.root, expiring(self.req), self.req, self.policy, OK)
        self.assertTrue(again['idempotent'])
        self.assertEqual(self.session_rows(), before)

    def test_a_re_ingest_over_a_receipt_with_no_session_is_refused(self):
        with sqlite3.connect(self.root / 'evidence.sqlite3') as db:
            db.execute('DROP TABLE received_session')
        with wall(T + 5), self.assertRaises(AppError) as refused:
            host.ingest(self.root, expiring(self.req), self.req, self.policy, OK)
        self.assertEqual(refused.exception.code, 'worker_evidence_clock_continuity_lost')


if __name__ == '__main__':
    unittest.main()
