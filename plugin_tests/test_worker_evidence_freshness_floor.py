"""A non-historical worker-evidence read judges expiry and snapshot age on a durable clock floor, never the bare wall.

The signature, snapshot and approval collaborators are replaced by trivial stand-ins (the real signed fixtures need the
G2 Docker prerequisite); request binding, trust shape, expiry and snapshot-age logic of verify_envelope run unchanged.
The wall is injected through time.time; the host clock is never changed. A restart is a real second process, with its
process state clear and the boot session unavailable, so only what the first process durably recorded can carry.
The Windows readers' tests live in test_windows_worker_evidence_freshness_floor and share this module's helpers.
"""
import base64
import contextlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock, windows_workbench as win
from intune_iac import windows_worker_evidence as native, windows_worker_evidence_store as receiver
from intune_iac import worker_evidence as contract, worker_evidence_posix as host
from intune_iac.io import AppError, digest
from plugin_tests.test_windows_storage_r4 import ROOT
from plugin_tests.test_windows_workbench_r4 import FilesystemAPI

TREE = str(Path(__file__).resolve().parents[1])
T = 1_800_000_000
TENANT = '11111111-1111-4111-8111-111111111111'
OBJECT = '22222222-2222-4222-8222-222222222222'
OPERATION = '33333333-3333-4333-8333-333333333333'
PROFILE = 'native_docker_laboratory_tls'
OK = lambda key, message, signature: None
OK.metadata = {'platform_qualified': False}


def REJECT(key, message, signature):
    raise AppError('worker_evidence_signature_invalid', 'rejected')


def make_policy():
    scope = {'profiles': [PROFILE], 'tenant_ids': [TENANT], 'object_ids': [OBJECT]}
    return {'schema_version': 'worker-evidence-trust/1',
            'publishers': [dict(scope, issuer='lab-export', key_id='publisher', publisher_id='fixture', public_key_hex='a' * 64)],
            'approvers': [dict(scope, issuer='lab-export', key_id='approver', approver_id='fixture-approver', public_key_hex='b' * 64)],
            'revoked': [], 'max_age_seconds': 200, 'max_lifetime_seconds': 900, 'clock_skew_seconds': 5}


def make_request(policy, nonce='7' * 32):
    return contract.request({'schema_version': 'worker-evidence-request/1', 'nonce': nonce, 'tenant_id': TENANT,
        'object_id': OBJECT, 'operation_id': OPERATION, 'manifest_sha256': 'c' * 64, 'saved_plan_sha256': 'd' * 64,
        'execution_binding_sha256': 'e' * 64, 'run_binding_sha256': 'f' * 64, 'source_revision': '9' * 40,
        'source_sha256': '1' * 64, 'run_id': 'run-1', 'run_attempt': 1, 'trust_sha256': digest(policy)})


def make_envelope(req, *, issued_at, expires_at, read_at, sequence=1):
    snapshot = {'read_at': read_at, 'manifest': {'profile': PROFILE, 'run_context': {}},
                'journal': {'last_sequence': sequence, 'events_sha256': 'a' * 64}, 'events': [], 'approval': None,
                'job': {'status': 'prepared', 'cancel_requested': False, 'outcome': None}}
    publisher = {'issuer': 'lab-export', 'key_id': 'publisher', 'publisher_id': 'fixture', 'purpose': 'read_only_worker_evidence',
                 'source_revision': '9' * 40, 'implementation_sha256': '2' * 64}
    payload = {'schema_version': 'worker-evidence-statement/1', 'publisher': publisher, 'request_sha256': digest(req),
               'request_nonce': req['nonce'], 'issued_at': issued_at, 'expires_at': expires_at, 'snapshot': snapshot}
    return {'schema_version': 'signed-worker-evidence/1', 'payload': payload, 'signature': base64.b64encode(bytes(64)).decode()}


def expiring(req):
    # Valid at T, closes at T+10.
    return make_envelope(req, issued_at=T, expires_at=T + 10, read_at=T - 5)


def aging(req, sequence=1):
    # Fresh at T, older than max_age (200 s) from T+150 on; still inside its own lifetime.
    return make_envelope(req, issued_at=T, expires_at=T + 500, read_at=T - 100, sequence=sequence)


def stand_ins():
    patch.object(contract, 'validate_snapshot', return_value=None).start()
    patch.object(contract, 'approval_proof', return_value='none').start()
    patch.object(contract, 'baseline', side_effect=lambda *a: {'reasons': [], 'baseline_admissible': True,
        'worker_status': 'prepared', 'current_status': 'prepared'}).start()


def wall(value):
    return patch.object(time, 'time', return_value=float(value))


# --- the restart: a second process -------------------------------------------------------------------------------------

def child(spec):
    """Runs in a fresh process: no process anchors, no boot session; prints the outcome as JSON."""
    stand_ins()
    patch.object(clock, 'session', return_value=None).start()
    policy = make_policy(); req = make_request(policy)
    try:
        with wall(spec['wall']):
            if spec['kind'] == 'posix':
                value = host.reopen(Path(spec['root']), digest(req), policy, OK, historical=spec['historical'])
            else:
                api = FilesystemAPI(Path(spec['root']))
                api.directories.update(spec['directories'])  # the directories the first process created, with their ids
                store = win.WindowsWorkbenchStore._open(ROOT + '\\received', TENANT, win._Filesystem(api, api.connect))
                inp = ROOT + '\\input'

                @contextlib.contextmanager
                def checked(pin, scratch, api):
                    yield OK
                patch.object(native, '_verifier', side_effect=checked).start()
                value = receiver._reopen(store, digest(req), inp + '\\trust.json', inp + '\\pin.json', ROOT + '\\scratch', api,
                                         historical=spec['historical'])
        print(json.dumps({'ok': True, 'baseline_admissible': value['baseline_admissible']}))
    except AppError as error:
        print(json.dumps({'ok': False, 'code': error.code}))


def restart(**spec):
    code = ('import sys,json;sys.path.insert(0,%r);from plugin_tests.test_worker_evidence_freshness_floor import child;'
            'child(json.loads(sys.argv[1]))' % TREE)
    done = subprocess.run([sys.executable, '-B', '-c', code, json.dumps(spec)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


class Shape:
    """The freshness cases through one reader; a subclass supplies publish/read/restart_read."""

    def setUp(self):
        self.addCleanup(clock.reset_process_anchor)
        clock.reset_process_anchor()
        self.addCleanup(patch.stopall)
        stand_ins()
        self.policy = make_policy()
        self.req = make_request(self.policy)

    def check(self, envelope, late_code, late_wall):
        self.publish(envelope)
        # The control is the only late observation: nothing seeds the floor by hand.
        with wall(late_wall), self.assertRaises(AppError) as control:
            self.read()
        self.assertEqual(control.exception.code, late_code)
        self.assertEqual(self.restart_read(T + 5, historical=False), {'ok': False, 'code': late_code})
        self.assertEqual(self.restart_read(T + 5, historical=True), {'ok': True, 'baseline_admissible': False})

    def test_expired_envelope_not_admissible_after_a_restart_and_wall_step_back(self):
        self.check(expiring(self.req), 'worker_evidence_expired', T + 20)

    def test_stale_snapshot_not_admissible_after_a_restart_and_wall_step_back(self):
        self.check(aging(self.req), 'worker_evidence_stale_snapshot', T + 150)

    def test_unexpired_fresh_read_is_unchanged(self):
        self.publish(expiring(self.req))
        with wall(T + 5):
            self.assertTrue(self.read()['baseline_admissible'])


class PosixStoreReaderTests(Shape, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'store'; self.root.mkdir(mode=0o700)

    def publish(self, envelope, req=None, at=T + 1, verifier=OK):
        with wall(at):
            return host.ingest(self.root, envelope, req or self.req, self.policy, verifier)

    def read(self, historical=False, verifier=OK):
        return host.reopen(self.root, digest(self.req), self.policy, verifier, historical=historical)

    def restart_read(self, at, historical):
        return restart(kind='posix', root=str(self.root), wall=at, historical=historical)

    def mark(self):
        record = clock.Floor(self.root / 'clock.json').record()
        return None if record is None else record['high_water']

    def test_ingest_records_the_floor_it_judged_on(self):
        self.publish(expiring(self.req))
        self.assertGreaterEqual(self.mark(), T + 1)

    def test_ingest_refuses_an_expired_envelope_after_a_wall_step_back(self):
        other = make_request(self.policy, '8' * 32)
        self.publish(aging(other), req=other, at=T + 20)  # a later authenticated ingest moves the floor
        with wall(T + 5), self.assertRaises(AppError) as raised:
            host.ingest(self.root, expiring(self.req), self.req, self.policy, OK)
        self.assertEqual(raised.exception.code, 'worker_evidence_expired')

    def test_an_authenticated_reopen_that_saw_the_window_closed_persists_it(self):
        self.publish(expiring(self.req))
        with wall(T + 20), self.assertRaises(AppError):
            self.read()
        self.assertGreaterEqual(self.mark(), T + 20)

    def test_forward_step_with_an_invalid_signature_leaves_the_floor_alone(self):
        self.publish(expiring(self.req))
        before = self.mark()
        self.assertGreaterEqual(before, T + 1)
        other = make_request(self.policy, '8' * 32)
        with wall(T + 500), self.assertRaises(AppError) as ingest:
            host.ingest(self.root, aging(other), other, self.policy, REJECT)
        self.assertEqual(ingest.exception.code, 'worker_evidence_signature_invalid')
        with wall(T + 500), self.assertRaises(AppError) as reopen:
            self.read(verifier=REJECT)
        self.assertEqual(reopen.exception.code, 'worker_evidence_signature_invalid')
        self.assertEqual(self.mark(), before)

    def test_a_writer_that_advances_the_floor_between_sample_and_acceptance_wins(self):
        # A authenticates at T+5 and pauses inside its verifier; B ingests at T+20 meanwhile; A must then be refused.
        other = make_request(self.policy, '8' * 32)
        other_envelope = aging(other)
        paused = []

        def pausing(key, message, signature):
            if not paused:
                paused.append(True)
                with wall(T + 20):
                    host.ingest(self.root, other_envelope, other, self.policy, OK)
            return None

        with wall(T + 5), self.assertRaises(AppError) as raised:
            host.ingest(self.root, expiring(self.req), self.req, self.policy, pausing)
        self.assertEqual(raised.exception.code, 'worker_evidence_expired')
        with self.assertRaises(AppError) as stored:  # and nothing of A was admitted
            self.read()
        self.assertEqual(stored.exception.code, 'worker_evidence_not_stored')

    def test_a_temporal_refusal_keeps_its_code_when_its_closure_cannot_be_recorded(self):
        self.publish(expiring(self.req))
        with patch.object(clock, 'write_json', side_effect=OSError('disk full')), wall(T + 20), self.assertRaises(AppError) as raised:
            self.read()
        self.assertEqual(raised.exception.code, 'worker_evidence_expired')
        self.assertIs(raised.exception.closure_recorded, False)
        self.assertIn('worker_evidence_clock_unrecorded', ''.join(raised.exception.__notes__))

    def test_an_admission_is_refused_when_the_time_cannot_be_recorded(self):
        with patch.object(clock, 'write_json', side_effect=OSError('disk full')), wall(T + 1), self.assertRaises(AppError) as raised:
            host.ingest(self.root, expiring(self.req), self.req, self.policy, OK)
        self.assertEqual(raised.exception.code, 'worker_evidence_clock_unrecorded')
        self.assertFalse((self.root / 'evidence.sqlite3').exists())  # nothing was admitted

    def test_an_invalid_input_poisons_neither_the_process_floor_nor_the_durable_one(self):
        self.publish(expiring(self.req))
        other = make_request(self.policy, '8' * 32)
        with wall(T + 500), self.assertRaises(AppError):
            host.ingest(self.root, aging(other), other, self.policy, REJECT)
        with wall(T + 500), self.assertRaises(AppError):
            self.read(verifier=REJECT)
        with wall(T + 5):  # the true wall again, a valid verifier, a current read and a current ingest
            self.assertTrue(self.read()['baseline_admissible'])
            self.assertFalse(host.ingest(self.root, aging(other), other, self.policy, OK)['idempotent'])
        self.assertLess(self.mark(), T + 500)

    def failing_commit(self):
        real = host.sqlite3.connect

        class Proxy:
            def __init__(self, inner):
                self.inner = inner

            def __enter__(self):
                self.inner.__enter__()
                return self

            def __exit__(self, *exc):
                return self.inner.__exit__(*exc)

            def execute(self, sql, *args):
                if sql == 'COMMIT':
                    raise host.sqlite3.OperationalError('disk I/O error')
                return self.inner.execute(sql, *args)

        return patch.object(host.sqlite3, 'connect', side_effect=lambda *a, **k: Proxy(real(*a, **k)))

    def test_an_acceptance_commit_failure_is_unrecorded_for_an_admissible_read(self):
        with self.failing_commit(), wall(T + 1), self.assertRaises(AppError) as raised:
            host.ingest(self.root, expiring(self.req), self.req, self.policy, OK)
        self.assertEqual(raised.exception.code, 'worker_evidence_clock_unrecorded')

    def test_an_acceptance_commit_failure_keeps_the_temporal_code_for_an_expired_read(self):
        with self.failing_commit(), wall(T + 20), self.assertRaises(AppError) as raised:
            host.ingest(self.root, expiring(self.req), self.req, self.policy, OK)
        self.assertEqual(raised.exception.code, 'worker_evidence_expired')


if __name__ == '__main__':
    unittest.main()
