"""A non-historical worker-evidence read judges expiry and snapshot age on the store's clock floor, never the bare wall.

The signature, snapshot and approval collaborators are replaced by trivial stand-ins (the real signed fixtures need the
G2 Docker prerequisite); request binding, trust shape, expiry and snapshot-age logic of verify_envelope run unchanged.
The wall is injected through time.time; the host clock is never changed.
"""
import base64
import contextlib
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock, windows_storage as storage, windows_workbench as win
from intune_iac import windows_worker_evidence as native, windows_worker_evidence_store as receiver
from intune_iac import worker_evidence as contract, worker_evidence_posix as host
from intune_iac.io import AppError, canonical, digest
from plugin_tests.test_windows_storage_r4 import CANONICAL, ROOT
from plugin_tests.test_windows_workbench_r4 import FilesystemAPI

T = 1_800_000_000
TENANT = '11111111-1111-4111-8111-111111111111'
OBJECT = '22222222-2222-4222-8222-222222222222'
OPERATION = '33333333-3333-4333-8333-333333333333'
PROFILE = 'native_docker_laboratory_tls'
OK = lambda key, message, signature: None


def make_policy():
    scope = {'profiles': [PROFILE], 'tenant_ids': [TENANT], 'object_ids': [OBJECT]}
    return {'schema_version': 'worker-evidence-trust/1',
            'publishers': [dict(scope, issuer='lab-export', key_id='publisher', publisher_id='fixture', public_key_hex='a' * 64)],
            'approvers': [dict(scope, issuer='lab-export', key_id='approver', approver_id='fixture-approver', public_key_hex='b' * 64)],
            'revoked': [], 'max_age_seconds': 200, 'max_lifetime_seconds': 900, 'clock_skew_seconds': 5}


def make_request(policy):
    return contract.request({'schema_version': 'worker-evidence-request/1', 'nonce': '7' * 32, 'tenant_id': TENANT,
        'object_id': OBJECT, 'operation_id': OPERATION, 'manifest_sha256': 'c' * 64, 'saved_plan_sha256': 'd' * 64,
        'execution_binding_sha256': 'e' * 64, 'run_binding_sha256': 'f' * 64, 'source_revision': '9' * 40,
        'source_sha256': '1' * 64, 'run_id': 'run-1', 'run_attempt': 1, 'trust_sha256': digest(policy)})


def make_envelope(req, *, issued_at, expires_at, read_at):
    snapshot = {'read_at': read_at, 'manifest': {'profile': PROFILE, 'run_context': {}},
                'journal': {'last_sequence': 1, 'events_sha256': 'a' * 64}, 'events': [], 'approval': None,
                'job': {'status': 'prepared', 'cancel_requested': False, 'outcome': None}}
    publisher = {'issuer': 'lab-export', 'key_id': 'publisher', 'publisher_id': 'fixture', 'purpose': 'read_only_worker_evidence',
                 'source_revision': '9' * 40, 'implementation_sha256': '2' * 64}
    payload = {'schema_version': 'worker-evidence-statement/1', 'publisher': publisher, 'request_sha256': digest(req),
               'request_nonce': req['nonce'], 'issued_at': issued_at, 'expires_at': expires_at, 'snapshot': snapshot}
    return {'schema_version': 'signed-worker-evidence/1', 'payload': payload, 'signature': base64.b64encode(bytes(64)).decode()}

def stand_ins():
    patch.object(contract, 'validate_snapshot', return_value=None).start()
    patch.object(contract, 'approval_proof', return_value='none').start()
    patch.object(contract, 'baseline', side_effect=lambda *a: {'reasons': [], 'baseline_admissible': True,
        'worker_status': 'prepared', 'current_status': 'prepared'}).start()


def wall(value):
    return patch.object(time, 'time', return_value=float(value))


class Shape:
    """Both freshness cases, each built from one envelope; a subclass supplies publish/read/seed."""

    def setUp(self):
        self.addCleanup(clock.reset_process_anchor)
        clock.reset_process_anchor()
        self.addCleanup(patch.stopall)
        stand_ins()
        self.policy = make_policy()
        self.req = make_request(self.policy)

    def expiring(self):
        # Valid at T, closes at T+10.
        return make_envelope(self.req, issued_at=T, expires_at=T + 10, read_at=T - 5)

    def aging(self):
        # Fresh at T, older than max_age (200 s) from T+150 on; still inside its own lifetime.
        return make_envelope(self.req, issued_at=T, expires_at=T + 500, read_at=T - 100)

    def check(self, envelope, late_code, late_wall):
        self.publish(envelope)
        self.seed_floor(late_wall)
        with wall(late_wall), self.assertRaises(AppError) as control:
            self.read()
        self.assertEqual(control.exception.code, late_code)
        clock.reset_process_anchor()  # a new process
        with wall(T + 5):
            with self.assertRaises(AppError) as stepped:
                self.read()
            self.assertIn(stepped.exception.code, (late_code, 'clock_moved_backward'))
            history = self.read(historical=True)
        self.assertFalse(history['baseline_admissible'])
        self.assertEqual(history['worker_status'], 'unknown')

    def test_expired_envelope_not_admissible_after_a_wall_step_back(self):
        self.check(self.expiring(), 'worker_evidence_expired', T + 20)

    def test_stale_snapshot_not_admissible_after_a_wall_step_back(self):
        self.check(self.aging(), 'worker_evidence_stale_snapshot', T + 150)

    def test_unexpired_fresh_read_is_unchanged(self):
        self.publish(self.expiring())
        with wall(T + 5):
            self.assertTrue(self.read()['baseline_admissible'])


class PosixStoreReaderTests(Shape, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'store'; self.root.mkdir(mode=0o700)

    def publish(self, envelope):
        self.envelope = envelope
        with wall(T + 1):
            host.ingest(self.root, envelope, self.req, self.policy, OK)

    def seed_floor(self, at):
        clock.Floor(self.root / 'clock.json').observe(at)

    def read(self, historical=False):
        return host.reopen(self.root, digest(self.req), self.policy, OK, historical=historical)

    def test_ingest_records_the_floor_it_judged_on(self):
        self.publish(self.expiring())
        self.assertGreaterEqual(clock.Floor(self.root / 'clock.json').high_water(), T + 1)

    def test_ingest_refuses_an_expired_envelope_after_a_wall_step_back(self):
        self.seed_floor(T + 20)
        with wall(T + 5), self.assertRaises(AppError) as raised:
            host.ingest(self.root, self.expiring(), self.req, self.policy, OK)
        self.assertEqual(raised.exception.code, 'worker_evidence_expired')


class WindowsStoreReaderTests(Shape, unittest.TestCase):
    """The native store has no floor file the portable Floor can open, so the monotonic process floor stands in."""

    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.api = FilesystemAPI(Path(self.temp.name)); fs = win._Filesystem(self.api, self.api.connect)
        self.store = win.WindowsWorkbenchStore._create(ROOT + '\\received', TENANT, fs)
        storage._create_directory(ROOT, 'input', self.api); storage._create_directory(ROOT, 'scratch', self.api)
        self.input = ROOT + '\\input'; self.scratch = ROOT + '\\scratch'
        for name, value in (('request.json', self.req), ('trust.json', self.policy)):
            storage._create_file(self.input, name, canonical(value), self.api)
        storage._create_file(self.input, 'pin.json', b'{}', self.api)

        @contextlib.contextmanager
        def checked(pin, scratch, api):
            OK.metadata = {'platform_qualified': False}
            yield OK
        patch.object(native, '_verifier', side_effect=checked).start()

    def publish(self, envelope):
        storage._create_file(self.input, 'envelope.json', canonical(envelope), self.api)
        with wall(T + 1):
            receiver._ingest(self.store, self.input + '\\envelope.json', self.input + '\\request.json',
                             self.input + '\\trust.json', self.input + '\\pin.json', self.scratch, self.api)

    def seed_floor(self, at):
        pass  # the floor is this process's own reading of the late wall, taken by the control read

    def read(self, historical=False):
        return receiver._reopen(self.store, digest(self.req), self.input + '\\trust.json', self.input + '\\pin.json',
                                self.scratch, self.api, historical=historical)

    def check(self, envelope, late_code, late_wall):
        # Same process: there is no persisted floor to carry a restart, so the process floor must hold across the step back.
        self.publish(envelope)
        with wall(late_wall), self.assertRaises(AppError) as control:
            self.read()
        self.assertEqual(control.exception.code, late_code)
        with wall(T + 5):
            with self.assertRaises(AppError) as stepped:
                self.read()
            self.assertEqual(stepped.exception.code, late_code)
            history = self.read(historical=True)
        self.assertFalse(history['baseline_admissible'])


class WindowsInspectReaderTests(Shape, unittest.TestCase):
    """windows_worker_evidence.inspect reads loose files, so it has no store; the monotonic process floor applies."""

    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.api = FilesystemAPI(Path(self.temp.name))
        storage._create_directory(ROOT, 'input', self.api); storage._create_directory(ROOT, 'scratch', self.api)
        self.input = ROOT + '\\input'; self.scratch = ROOT + '\\scratch'
        for name, value in (('request.json', self.req), ('trust.json', self.policy)):
            storage._create_file(self.input, name, canonical(value), self.api)
        storage._create_file(self.input, 'pin.json', b'{}', self.api)

        @contextlib.contextmanager
        def checked(pin, scratch, api):
            OK.metadata = {'platform_qualified': False}
            yield OK
        patch.object(native, '_verifier', side_effect=checked).start()

    def publish(self, envelope):
        storage._create_file(self.input, 'envelope.json', canonical(envelope), self.api)

    def seed_floor(self, at):
        pass

    def read(self, historical=False):
        return native._inspect(self.input + '\\envelope.json', self.input + '\\request.json', self.input + '\\trust.json',
                               self.input + '\\pin.json', self.scratch, self.api, historical=historical)

    check = WindowsStoreReaderTests.check

    def test_unexpired_fresh_read_is_unchanged(self):
        self.publish(self.expiring())
        with wall(T + 5):
            self.assertIn('baseline_admissible', self.read())


if __name__ == '__main__':
    unittest.main()
