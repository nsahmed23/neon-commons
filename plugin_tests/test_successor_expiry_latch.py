"""An expired successor transfer approval stays expired, and a stale preimage cannot become fresh again
(PKG-TIME-AUTHZ-C, worker_successor).

execute_transfer judged the signed transfer approval's expiry on the bare wall clock in _verify and again inside the
transaction that moves ownership to the successor, and it judged the 30 second age of the service preimage on the wall
clock. A refusal at or after the expiry recorded nothing, so a clock step back before the expiry and a restart reopened the
same approval; a wall clock stepped back after the preimage went stale made it fresh again.

The approval is judged by the shared decision (intune_iac.validity) on the original job's store, in the successor_expired
table: _verify authenticates it and then judges it in the critical section, the ownership transfer is the second consumer,
and a refusal for the manifest's, the transfer's or its age's bare-clock window records the expiry of an approval that
authenticates. The preimage is a process-held capture with no store: its age is carried on the monotonic clock from this
process's first sight of it, so only the process, never the wall clock, can make it younger.

Each test drives the public call (execute_transfer) against a real service store and a real signature with injected clocks.
Only the controller seams that need live evidence are modeled: the transfer preparation, the recovery completion and the
original job's facts. The existing test_worker_successor_r4 needs the pinned container client and is not run here.
"""
import base64
import copy
import sqlite3
import subprocess
import tempfile
import time
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock
from intune_iac import observation_reader as reader_api
from intune_iac import worker_service as service
from intune_iac import worker_successor as successor
from intune_iac.io import AppError, canonical, digest
from plugin_tests import test_worker_adoption_reconcile_r4 as old_contracts
from plugin_tests.test_adoption_expiry_latch import RECOVERY_WORDS, inject
from plugin_tests.test_clock_authority import Clocks

LIFETIME = 60
EXPIRED = 'successor_signature_expired'


class SuccessorFixture(unittest.TestCase):
    def setUp(self):
        self.start = int(time.time())
        self.clocks = Clocks(self.start)
        inject(self, self.clocks)
        old_contracts.RecoveryPlanContracts.setUp(self)  # the service store (self.policy) and a signing key (self.key)
        self.expires = self.start + LIFETIME
        self.original_id, self.successor_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.original_job = object.__new__(service.ServiceJob)
        self.original_job.policy, self.original_job.identifier = self.policy, self.original_id
        self.original_job.sha256, self.original_job.root = 'o' * 64, self.root / 'jobs' / 'original'
        self.successor_manifest = {'operation_id': self.successor_id, 'profile': 'native_docker_laboratory_protocol',
                                   'host_spec': {'modeled': True}, 'expires_at': self.expires}
        self.transfer = {'schema_version': successor.VERSION, 'transfer_id': str(uuid.uuid4()), 'prepared_at': self.start,
            'expires_at': self.expires, 'authority': {}, 'original': {'operation_id': self.original_id, 'scopes': ['scope']},
            'successor': {'operation_id': self.successor_id, 'manifest_sha256': digest(self.successor_manifest),
                          'job_root': str(self.root / 'jobs' / 'successor')},
            'recovery_completion': {'recovery_operation_id': str(uuid.uuid4())},
            'recovery_kind': 'explicit_original_state_lease_release', 'service_preimage': {'fixture': True},
            'implementation_sha256': 'i' * 64, 'operation_dispatch_authorized': False}
        with self.policy.connection() as db:
            db.execute('INSERT INTO jobs(id,root,manifest_sha256,status,dispatches) VALUES (?,?,?,?,1)',
                       (self.original_id, str(self.original_job.root), 'o' * 64, 'outcome_unknown'))
            db.execute('INSERT INTO ownership VALUES (?,?)', ('scope', self.original_id))
        self.window_rule = False  # the bare-clock window refusals of the preparation, when a test turns them on
        spec = types.SimpleNamespace(source_root=str(self.root / 's'), control_root=str(self.root / 'c'),
                                     job_root=str(self.root / 'j'), broker_root=str(self.root / 'b'))
        for patcher in (patch.object(successor.service, 'validate_manifest', side_effect=lambda value, **kw: copy.deepcopy(value)),
                        patch.object(successor, 'prepare_transfer', side_effect=self.prepare),
                        patch.object(successor, '_completion', side_effect=lambda *args: self.transfer['recovery_completion']),
                        patch.object(successor, '_service_preimage', side_effect=lambda *args: self.transfer['service_preimage']),
                        patch.object(successor, '_original', side_effect=lambda job, db: self.transfer['original']),
                        patch.object(successor, '_recovery_record_matches', return_value=True),
                        patch.object(successor.service, '_host_spec', return_value=spec),
                        patch.object(successor.service, 'ServiceJob',
                                     side_effect=lambda root, path: types.SimpleNamespace(status=lambda: {'status': 'prepared'}))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def prepare(self, **kwargs):
        """The transfer preparation, with the bare-clock window rule it applies when a test turns it on."""
        if self.window_rule and not int(time.time()) < self.transfer['expires_at']:
            raise AppError('successor_transfer_scope', 'The transfer window is closed.')
        return copy.deepcopy(self.transfer)

    def approval(self, **changes):
        payload = {'schema_version': 'signed-worker-service-successor/2', 'issuer': 'fixture', 'key_id': 'key',
                   'approver_id': 'reviewer', 'transfer_id': self.transfer['transfer_id'],
                   'transfer_manifest_sha256': digest(self.transfer), 'issued_at': self.start, 'expires_at': self.expires,
                   'nonce': uuid.uuid4().hex}
        payload.update(changes)
        message, signature = self.root / 'trust' / 'message', self.root / 'trust' / 'signature'
        message.write_bytes(successor.SIGNATURE_DOMAIN + canonical(payload))
        subprocess.run(['/usr/bin/openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(self.key), '-in', str(message),
                        '-out', str(signature)], check=True, capture_output=True)
        return {'payload': payload, 'signature': base64.b64encode(signature.read_bytes()).decode()}

    def execute(self, signed):
        return successor.execute_transfer(self.transfer, signed, original_job=self.original_job,
                                          successor_manifest=self.successor_manifest, recovery_completion=object(),
                                          service_preimage=object())

    def rows(self, sql):
        connection = sqlite3.connect(self.policy.database)
        try:
            return connection.execute(sql).fetchall()
        finally:
            connection.close()

    def latched(self):
        try:
            return self.rows('SELECT issuer, nonce, operation_id, expires_at FROM successor_expired_v2')
        except sqlite3.OperationalError:
            return []

    def refused(self, call):
        with self.assertRaises(AppError) as raised:
            call()
        return raised.exception

    def restart(self):
        clock.reset_process_anchor()
        self.policy = service.ServicePolicy(self.policy_path, initialize=False)
        self.original_job.policy = self.policy

    def assert_nothing_happened(self):
        self.assertEqual(self.rows('SELECT job FROM ownership'), [(self.original_id,)])
        self.assertEqual(self.rows('SELECT id FROM jobs'), [(self.original_id,)])
        self.assertFalse((self.root / 'jobs' / 'successor').exists())


class ApprovalLatchTests(SuccessorFixture):
    def test_an_expired_approval_stays_refused_after_a_backward_step_and_a_restart(self):
        signed = self.approval()
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.clocks.wall = self.expires - 10  # the wall clock now reads ten seconds before the expiry
        self.restart()
        self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.assert_nothing_happened()
        self.assertEqual(len(self.latched()), 1)

    def test_an_approval_judged_open_and_then_refused_for_another_reason_is_not_reopened_by_a_restart(self):
        signed = self.approval()
        self.clocks.wall = self.start + 30
        with patch.object(successor, '_completion', side_effect=AppError('modeled_completion_unavailable', 'x')):
            self.refused(lambda: self.execute(signed))  # _verify judged it open at T30, then a later check failed
        self.restart()
        self.clocks.elapse(40)  # true time T70, past the approval's expiry at T60
        self.clocks.step(-30)  # the wall is set to T40: above the mark, inside the window
        self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.assertEqual(self.rows('SELECT job FROM ownership'), [(self.original_id,)])

    def test_the_latch_alone_refuses_when_the_recorded_time_is_gone(self):
        signed = self.approval()
        self.clocks.elapse(LIFETIME + 1)
        self.refused(lambda: self.execute(signed))
        (self.policy.root / 'clock.json').unlink(missing_ok=True)
        self.clocks.wall = self.expires - 30
        self.restart()
        self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.assert_nothing_happened()

    def test_an_expiry_reached_between_the_verification_and_the_transfer_is_refused_with_nothing_moved(self):
        signed = self.approval()
        self.clocks.wall = self.start + 10
        with patch.object(successor, '_completion',
                          side_effect=lambda *args: self.clocks.elapse(LIFETIME) or self.transfer['recovery_completion']):
            self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.assert_nothing_happened()  # not even the successor directory exists: effects start after the judgment
        self.assertEqual(len(self.latched()), 1)

    def test_a_refusal_for_the_transfers_own_window_still_records_the_approvals_expiry(self):
        self.window_rule = True
        signed = self.approval()
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.execute(signed)).code, 'successor_transfer_scope')
        self.assertEqual(len(self.latched()), 1)
        self.clocks.wall = self.expires - 20
        self.restart()
        self.assertEqual(self.refused(lambda: self.execute(signed)).code, EXPIRED)
        self.assert_nothing_happened()

    def test_a_backward_step_before_the_expiry_holds_the_transfer_and_says_how_to_recover(self):
        signed = self.approval()
        self.clocks.wall = self.start + 30
        with patch.object(successor, '_completion', side_effect=AppError('modeled_completion_unavailable', 'x')):
            self.refused(lambda: self.execute(signed))  # the judgment recorded T+30 before the completion failed
        self.clocks.step(-20)  # reads T+10, earlier than the recorded T+30
        for attempt in range(2):
            error = self.refused(lambda: self.execute(signed))
            self.assertEqual(error.code, 'clock_moved_backward')
            self.assertIn(RECOVERY_WORDS, error.message)
            self.restart()
        self.assertEqual(self.latched(), [])
        self.assertEqual(self.rows('SELECT job FROM ownership'), [(self.original_id,)])

    def test_a_backward_step_to_before_the_issue_time_reports_the_hold_through_the_window_refusal(self):
        self.window_rule = True
        signed = self.approval()
        self.clocks.wall = self.start + 30
        with patch.object(successor, '_completion', side_effect=AppError('modeled_completion_unavailable', 'x')):
            self.refused(lambda: self.execute(signed))
        self.clocks.wall = self.start - 10
        self.restart()
        self.assertEqual(self.refused(lambda: self.execute(signed)).code, 'clock_moved_backward')

    def test_an_approval_that_does_not_authenticate_records_nothing(self):
        forged = self.approval()
        forged['signature'] = forged['signature'][:-4] + 'AAAA'
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.execute(forged)).code, EXPIRED)
        self.assertEqual(self.latched(), [])
        self.assertFalse((self.policy.root / 'clock.json').exists())

    def test_an_approval_that_reuses_an_expired_approvals_issuer_and_nonce_is_judged_on_its_own(self):
        nonce = uuid.uuid4().hex
        early = self.approval(nonce=nonce, expires_at=self.start + 30)
        self.clocks.wall = self.start + 40
        self.assertEqual(self.refused(lambda: self.execute(early)).code, EXPIRED)
        self.assertEqual(len(self.latched()), 1)
        self.transfer = dict(self.transfer, transfer_id=str(uuid.uuid4()))  # another transfer, same issuer and nonce
        self.assertEqual(self.execute(self.approval(nonce=nonce))['status'], 'prepared')

    def test_an_open_window_transfers_ownership_once_and_records_no_expiry(self):
        self.clocks.wall = self.start + 10
        self.assertEqual(self.execute(self.approval())['status'], 'prepared')
        self.assertEqual(self.rows('SELECT job FROM ownership'), [(self.successor_id,)])
        self.assertEqual(self.latched(), [])


class PreimageFixture(unittest.TestCase):
    """A sealed service preimage capture and a manifest that binds it, under injected clocks."""

    def setUp(self):
        self.start = time.time()
        self.clocks = Clocks(self.start)
        for target, name, function in ((time, 'time', self.clocks.time), (time, 'monotonic', self.clocks.monotonic)):
            patcher = patch.object(target, name, side_effect=function)
            patcher.start()
            self.addCleanup(patcher.stop)
        capture = 'c' * 64
        self.manifest = {'profile': 'native_docker_laboratory_protocol', 'tenant_id': 't', 'object_ids': ['o'],
            'precondition_binding': {'preimage_capture_sha256': capture, 'identity': {'who': 'reader'},
                                     'identity_observation_sha256': 'i' * 64, 'preimage_raw_sha256': digest({'raw': 1})}}
        self.batch = {'observed_at': self.start, 'tenant_id': 't', 'object_id': 'o', 'capture_sha256': capture,
            'collections': [{'kind': kind, 'coverage': 'complete', 'reason': None} for kind in ('policies', 'settings', 'assignments')],
            'source': {'raw_observed': {'raw': 1}}}
        self.source = {'evidence_class': 'graph_reader_laboratory', 'source_authenticity_verified': False,
                       'identity': {'who': 'reader'}, 'identity_observation_sha256': 'i' * 64}
        patcher = patch.object(reader_api.CapturedObservation, 'verified', lambda captured: (self.batch, self.source))
        patcher.start()
        self.addCleanup(patcher.stop)

    def capture(self):
        """A capability made by this process now, as the reader makes one (the constructor is sealed)."""
        return reader_api.CapturedObservation(reader_api._CAPTURE, 'capture.json', self.batch, self.source, False)


class PreimageFreshnessTests(PreimageFixture):
    """The 30 second age of the service preimage is carried by the capture itself, on the monotonic clock."""

    def test_a_fresh_preimage_is_admitted(self):
        self.clocks.elapse(10)
        self.assertEqual(successor._service_preimage(self.capture(), self.manifest)['capture_sha256'], 'c' * 64)

    def test_a_stale_preimage_stays_stale_after_the_wall_clock_steps_back(self):
        self.clocks.elapse(10)
        captured = self.capture()  # ten seconds old when made
        successor._service_preimage(captured, self.manifest)
        self.clocks.elapse(100)  # real time passes: the capture is now 110 seconds old
        self.clocks.step(-100)  # the wall clock claims it is 10 seconds old again
        with self.assertRaises(AppError) as raised:
            successor._service_preimage(captured, self.manifest)
        self.assertEqual(raised.exception.code, 'successor_service_preimage_binding')

    def test_a_preimage_stays_stale_however_long_it_is_kept(self):
        # No bounded process map decides freshness: the age is on the capture, so a long wait cannot forget it.
        self.clocks.elapse(10)
        captured = self.capture()
        successor._service_preimage(captured, self.manifest)
        self.clocks.elapse(301)
        self.clocks.step(-301)
        with self.assertRaises(AppError) as raised:
            successor._service_preimage(captured, self.manifest)
        self.assertEqual(raised.exception.code, 'successor_service_preimage_binding')
        self.clocks.elapse(3000)
        self.clocks.step(-3000)
        with self.assertRaises(AppError):
            successor._service_preimage(captured, self.manifest)

    def test_a_capture_that_another_process_made_is_refused_whatever_the_wall_clock_says(self):
        self.clocks.elapse(10)
        captured = self.capture()
        object.__setattr__(captured, '_pid', captured._pid + 1)  # as a copy carried into a restarted process would be
        with self.assertRaises(AppError):
            successor._service_preimage(captured, self.manifest)

    def test_a_preimage_dated_ahead_of_the_clock_is_refused(self):
        self.clocks.step(-5)
        with self.assertRaises(AppError):
            successor._service_preimage(self.capture(), self.manifest)


class PreimageStoreTimeTests(PreimageFixture):
    """A capture made after a restart takes its first age from the policy store's effective time, not the bare wall clock:
    the born age of a new capture is the wall clock's, and a wall clock set back after the store recorded a later time would
    otherwise make an old observation look new."""

    def setUp(self):
        super().setUp()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.policy = types.SimpleNamespace(root=self.root)
        self.clocks.install_session(self)
        clock.reset_process_anchor()
        self.addCleanup(clock.reset_process_anchor)
        patcher = patch.object(clock, 'monotonic', side_effect=self.clocks.monotonic)
        patcher.start()
        self.addCleanup(patcher.stop)

    def record_floor(self):
        clock.Floor(self.root / 'clock.json').observe(self.clocks.time())

    def refused(self, captured):
        with self.assertRaises(AppError) as raised:
            successor._service_preimage(captured, self.manifest, self.policy)
        self.assertEqual(raised.exception.code, 'successor_service_preimage_binding')

    def test_a_new_capture_of_an_old_observation_is_stale_after_a_restart_with_the_wall_set_back(self):
        self.record_floor()  # the store recorded T0 (the observation was made at T0)
        self.clocks.elapse(70)  # real time: the store's floor now stands at T0 plus 70 seconds of boot time
        clock.reset_process_anchor()  # the process restarted
        self.clocks.step(-60)  # the wall clock was set back to 10 seconds after the observation
        captured = self.capture()  # a new capture of the old observation: by the bare wall clock it is ten seconds old
        self.assertLess(captured.carried_age(), 30)
        self.refused(captured)

    def test_a_new_capture_stays_fresh_when_the_store_time_agrees(self):
        self.record_floor()
        self.clocks.elapse(10)
        clock.reset_process_anchor()
        self.assertEqual(successor._service_preimage(self.capture(), self.manifest, self.policy)['capture_sha256'], 'c' * 64)

    def test_a_store_that_has_recorded_nothing_leaves_the_wall_age(self):
        self.clocks.elapse(10)
        self.assertEqual(successor._service_preimage(self.capture(), self.manifest, self.policy)['capture_sha256'], 'c' * 64)

    def test_the_process_checks_still_apply_with_a_store(self):
        self.record_floor()
        self.clocks.elapse(10)
        captured = self.capture()
        object.__setattr__(captured, '_pid', captured._pid + 1)
        with self.assertRaises(AppError):
            successor._service_preimage(captured, self.manifest, self.policy)
        fresh = self.capture()
        self.clocks.elapse(100)
        self.clocks.step(-100)
        self.refused(fresh)  # the monotonic age still decides when the store knows nothing more


if __name__ == '__main__':
    unittest.main()
