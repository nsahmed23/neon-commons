"""An expired adoption approval stays expired across a backward clock step and a restart (PKG-TIME-AUTHZ-B, item 2).

The adoption dispatch judged its receipt's expiry on the bare wall clock in _verify, then made a backend observation,
then consumed the approval in a separate transaction with no expiry check. A rollback before consumption reopened it.
The consumption is now the second consumer of the shared critical section (intune_iac.validity) on the adoption
policy's own store. AdoptionPermit.check_active (the authorization check) enters the same section and commits a
marker; poll_active (the watchdog) judges read-only.

Each test drives the public call (AdoptionJob.run, verify_first_plan, the permit's check_active) against a real
ServicePolicy store and a real signature, with injected wall and monotonic clocks. Only the controller seams that need a
live backend or container are modeled: the runtime and input checks, the backend observation and the dispatch itself.
A refusal must leave the right records: nothing consumed, no dispatch, and the expiry recorded.
"""
import contextlib
import multiprocessing
import sqlite3
import threading
import time
import types
import unittest
import uuid
from unittest.mock import patch

from intune_iac import clock, validity
from intune_iac import worker_adoption as adoption
from intune_iac import worker_service as service
from intune_iac.io import AppError, canonical, digest
from plugin_tests import test_worker_adoption_reconcile_r4 as old_contracts
from plugin_tests.test_clock_authority import Clocks

LIFETIME = 60
FORK = multiprocessing.get_context('fork')
BOUND = 30
RECOVERY_WORDS = 'Correct the host clock, or wait until it reads at or after the recorded time'


def inject(test, clocks):
    for target, name, function in ((time, 'time', clocks.time), (clock, 'monotonic', clocks.monotonic)):
        patcher = patch.object(target, name, side_effect=function)
        patcher.start()
        test.addCleanup(patcher.stop)
    clocks.install_session(test)
    clock.reset_process_anchor()
    test.addCleanup(clock.reset_process_anchor)


def watchdog_refusals(test, database, check, *, attempts=300, tick=lambda: None):
    """Run check() in a tight loop in this process, as the watchdog does, while a forked process asks for the write
    reservation (BEGIN IMMEDIATE, then ROLLBACK: the first step of cancel and recover) over and over. Returns the
    refusals the other process saw and the errors the loop saw. The child is forked before the loop thread starts."""
    go, queue, errors, stop = FORK.Event(), FORK.Queue(), [], threading.Event()

    def other_process():
        refused = []
        go.wait(BOUND)
        for _ in range(attempts):
            connection = sqlite3.connect(database, timeout=0, isolation_level=None)
            try:
                connection.execute('BEGIN IMMEDIATE')
                connection.execute('ROLLBACK')
            except sqlite3.OperationalError as error:
                refused.append(str(error))
            finally:
                connection.close()
            time.sleep(0.001)
        queue.put(refused)

    def loop():
        while not stop.is_set():
            try:
                tick()
                check()
            except BaseException as error:
                errors.append(getattr(error, 'code', repr(error)))
                return
    process = FORK.Process(target=other_process, daemon=True)
    process.start()
    test.addCleanup(lambda: process.is_alive() and process.terminate())
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    go.set()
    try:
        refused = queue.get(timeout=BOUND * 2)
    finally:
        stop.set()
        thread.join(BOUND)
    process.join(BOUND)
    return refused, errors


def latch_by_deadline(test, permit):
    """Latch the permit's expiry from this process without moving the recorded time: its monotonic deadline passes while
    the wall clock still reads inside the window. The recorded time stays before the expiry, so a process that reads
    only the recorded time and its own clock cannot tell; only the expiry record says so. Returns the refusal."""
    real = time.monotonic
    with patch.object(time, 'monotonic', side_effect=lambda: real() + 3600):
        return test.refused(permit.check_active)


def race_with_a_latch(test, permit, child_permit, *, hook, poll_first=False, around=None):
    """Process A pauses at hook (owner, attribute, 'before' or 'after' the real call); this process latches the expiry;
    A resumes. A then asks for authority (check_active) and, only if it gets it, calls a modeled service. Returns
    (what the latch refusal said, A's poll result or None, A's authorization result, A's service calls). around is a
    context manager factory entered in A around its whole body (a permit that is bound to the creating process's id)."""
    paused, release, queue = FORK.Event(), FORK.Event(), FORK.Queue()
    owner, name, when = hook

    def process_a():
        test.clocks.wall = test.start + 10  # this process reads a time inside the window throughout
        with (around or contextlib.nullcontext)():
            report, calls = run_a()
        queue.put((report[0], report[1], calls))

    def run_a():
        mine, real, report, calls = child_permit(), getattr(owner, name), [None, None], []

        def paused_call(*args, **kwargs):
            result = real(*args, **kwargs) if when == 'after' else None
            paused.set()
            release.wait(BOUND)
            return result if when == 'after' else real(*args, **kwargs)
        with patch.object(owner, name, paused_call):
            try:
                if poll_first:
                    mine.poll_active()
                    report[0] = 'poll_returned'
                mine.check_active()
                calls.append('service')
                report[1] = 'authorized'
            except AppError as error:
                report[1] = error.code
        return report, calls
    process = FORK.Process(target=process_a, daemon=True)
    process.start()
    test.addCleanup(lambda: process.is_alive() and process.terminate())
    test.assertTrue(paused.wait(BOUND))
    latched = latch_by_deadline(test, permit).code
    release.set()
    result = queue.get(timeout=BOUND)
    process.join(BOUND)
    return (latched,) + result


class AdoptionFixture(unittest.TestCase):
    def setUp(self):
        self.start = int(time.time())
        self.clocks = Clocks(self.start)
        inject(self, self.clocks)
        old_contracts.RecoveryPlanContracts.setUp(self)
        self.expires = self.start + LIFETIME
        self.manifest = {'schema_version': adoption.VERSION, 'operation_id': str(uuid.uuid4()),
                         'verification_operation_id': str(uuid.uuid4()), 'profile': 'native_docker_laboratory_protocol',
                         'action': 'native_state_only_import', 'prepared_at': self.start, 'expires_at': self.expires,
                         'implementation_files': {'fixture/controller.py': 'a' * 64}}
        self.controller_files = dict(self.manifest['implementation_files'])  # what the controller is now
        adoption._tables(self.policy)
        self.job_root = self.root / 'jobs' / 'adoption-job'
        self.job_root.mkdir(mode=0o700)
        self.job = object.__new__(adoption.AdoptionJob)
        self.job.policy, self.job.root, self.job.manifest = self.policy, self.job_root, self.manifest
        self.job.sha256, self.job.identifier, self.job._completion = digest(self.manifest), self.manifest['operation_id'], None
        with self.policy.connection() as db:
            db.execute('INSERT INTO jobs(id,root,manifest_sha256,status) VALUES (?,?,?,?)',
                       (self.job.identifier, str(self.job_root), self.job.sha256, 'prepared'))
            db.execute('INSERT INTO ownership VALUES (?,?)', ('scope', self.job.identifier))
            db.execute('INSERT INTO adoption_operations(operation_id,manifest_sha256,verification_id) VALUES (?,?,?)',
                       (self.job.identifier, self.job.sha256, self.manifest['verification_operation_id']))
        self.observations, self.dispatched, self.permits, self.on_observe = [], [], [], lambda: None
        self.manifest_time_rule = False
        self.runtime = object.__new__(adoption.AdoptionRuntime)
        for patcher in (patch.object(adoption.AdoptionJob, '_check', self.check),
                        patch.object(adoption.AdoptionRuntime, 'check', return_value=None),
                        patch.object(adoption, '_inputs', return_value=types.SimpleNamespace()),
                        patch.object(adoption, '_backend_observation', self.observe),
                        patch.object(adoption.AdoptionJob, '_dispatch', self.dispatch),
                        patch.object(service, '_scopes', return_value=['scope']),
                        patch.object(service, 'implementation_binding', side_effect=lambda: dict(self.controller_files)),
                        patch.object(service, '_controller_identity', return_value='controller-start')):
            patcher.start()
            self.addCleanup(patcher.stop)

    # The controller seams that need a live backend or container.
    def check(self, *, expiry=True):
        """AdoptionJob._check models the manifest's own time rule (validate_manifest) when a test turns it on."""
        now = int(time.time())
        if expiry and self.manifest_time_rule and not self.manifest['prepared_at'] <= now + 5 < self.manifest['expires_at']:
            raise AppError('adoption_expired', 'The manifest window is closed.')

    def observe(self, job, runtime, output, *, baseline):
        self.observations.append('baseline' if baseline else 'successor')
        self.on_observe()
        return types.SimpleNamespace(facts=lambda: {'modeled': True})

    def dispatch(self, payload, runtime, spec, *, verification):
        self.dispatched.append('verification' if verification else 'import')
        self.permits.append(adoption.AdoptionPermit(adoption._SEAL, self.job, payload, runtime, verification))
        return {'status': 'modeled-dispatch'}

    # Records.
    def rows(self, sql):
        connection = sqlite3.connect(self.policy.database)
        try:
            return connection.execute(sql).fetchall()
        finally:
            connection.close()

    def consumed(self):
        return self.rows('SELECT operation_id FROM consumed')

    def latched(self):
        return self.rows('SELECT issuer, nonce, operation_id, expires_at FROM adoption_expired_v2')

    def job_row(self):
        return self.rows('SELECT status, cancelled, dispatches FROM jobs')[0]

    def assert_nothing_happened(self):
        self.assertEqual(self.consumed(), [])
        self.assertEqual(self.rows('SELECT * FROM approval_transcripts'), [])
        self.assertEqual(self.job_row(), ('prepared', 0, 0))
        self.assertEqual(self.dispatched, [])
        self.assertFalse((self.job_root / 'approval.json').exists())

    # Actions.
    def receipt(self, **changes):
        return old_contracts.RecoveryPlanContracts.signed(
            self, adoption.SIGNATURE_DOMAIN, schema_version=adoption.APPROVAL_VERSION,
            issued_at=changes.pop('issued_at', self.start), expires_at=changes.pop('expires_at', self.expires), **changes)

    def run_job(self, receipt):
        return self.job.run(receipt, runtime=self.runtime)

    def refused(self, call):
        with self.assertRaises(AppError) as raised:
            call()
        return raised.exception

    def restart(self):
        clock.reset_process_anchor()
        self.job.policy = self.policy = service.ServicePolicy(self.policy_path, initialize=False)

    def dispatch_running(self, at=None):
        """Run the import at a given time and return the permit the dispatch would hold."""
        if at is not None:
            self.clocks.wall = at
        self.assertEqual(self.run_job(self.receipt())['status'], 'modeled-dispatch')
        return self.permits[-1]


class DispatchLatchTests(AdoptionFixture):
    def test_a_restart_with_the_wall_set_back_above_the_mark_cannot_reopen_a_receipt_that_has_expired(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 30
        adoption._verify(self.policy, self.manifest, signed)  # judged open at T30: the mark and an open row
        self.restart()
        self.clocks.elapse(40)  # true time T70, past the receipt's expiry at T60
        self.clocks.step(-30)  # the wall is set to T40: above the mark, inside the window
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_signature_expired')
        self.assert_nothing_happened()
    def test_a_receipt_that_reuses_an_expired_receipts_issuer_and_nonce_is_judged_on_its_own(self):
        nonce = uuid.uuid4().hex
        early = self.receipt(nonce=nonce, expires_at=self.start + 30)
        self.clocks.wall = self.start + 40
        self.assertEqual(self.refused(lambda: self.run_job(early)).code, 'adoption_signature_expired')
        self.assertEqual(len(self.latched()), 1)
        # A second job of the same store: another operation and manifest, the same issuer and nonce.
        self.manifest = dict(self.manifest, operation_id=str(uuid.uuid4()), verification_operation_id=str(uuid.uuid4()))
        second_root = self.root / 'jobs' / 'adoption-job-2'
        second_root.mkdir(mode=0o700)
        self.job = object.__new__(adoption.AdoptionJob)
        self.job.policy, self.job.root, self.job.manifest = self.policy, second_root, self.manifest
        self.job.sha256, self.job.identifier, self.job._completion = digest(self.manifest), self.manifest['operation_id'], None
        with self.policy.connection() as db:
            db.execute('INSERT INTO jobs(id,root,manifest_sha256,status) VALUES (?,?,?,?)',
                       (self.job.identifier, str(second_root), self.job.sha256, 'prepared'))
            db.execute('UPDATE ownership SET job=?', (self.job.identifier,))
            db.execute('INSERT INTO adoption_operations(operation_id,manifest_sha256,verification_id) VALUES (?,?,?)',
                       (self.job.identifier, self.job.sha256, self.manifest['verification_operation_id']))
        self.assertEqual(self.run_job(self.receipt(nonce=nonce))['status'], 'modeled-dispatch')
        self.assertEqual(self.dispatched, ['import'])

    def test_an_expired_receipt_stays_refused_after_a_backward_step_and_a_restart(self):
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_signature_expired')
        self.assertEqual(len(self.latched()), 1)
        self.clocks.wall = self.expires - 10  # the wall clock now reads ten seconds before the expiry
        self.restart()
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_signature_expired')
        self.assert_nothing_happened()
        self.assertEqual(self.observations, [])  # the backend was not even read for an expired receipt
        self.assertEqual(len(self.latched()), 1)

    def test_the_latch_alone_refuses_when_the_recorded_time_is_gone(self):
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        self.refused(lambda: self.run_job(signed))
        (self.policy.root / 'clock.json').unlink()
        self.clocks.wall = self.expires - 30
        self.restart()
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_signature_expired')
        self.assert_nothing_happened()

    def test_an_expiry_reached_during_the_backend_observation_is_refused_with_nothing_consumed(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 10
        self.on_observe = lambda: self.clocks.elapse(LIFETIME)  # the observation takes the clock past the expiry
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_signature_expired')
        self.assertEqual(self.observations, ['baseline'])
        self.assert_nothing_happened()
        self.assertEqual(len(self.latched()), 1)

    def test_a_monotonic_deadline_reached_during_the_observation_is_an_expiry_too(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 10
        real, jump = time.monotonic, [0]
        self.on_observe = lambda: jump.__setitem__(0, 3600)  # the observation outlasts the receipt, the wall clock is stuck
        with patch.object(time, 'monotonic', side_effect=lambda: real() + jump[0]):
            self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_signature_expired')
        self.assert_nothing_happened()

    def test_a_backward_step_before_the_expiry_holds_the_dispatch_and_says_how_to_recover(self):
        signed = self.receipt()
        self.clocks.wall = self.start + 30
        self.on_observe = lambda: (_ for _ in ()).throw(AppError('adoption_backend_unavailable_locked_or_metadata', 'x'))
        self.refused(lambda: self.run_job(signed))  # the first judgment recorded T+30 before the observation failed
        self.on_observe = lambda: None
        self.clocks.step(-20)  # reads T+10, earlier than the recorded T+30
        for attempt in range(2):
            error = self.refused(lambda: self.run_job(signed))
            self.assertEqual(error.code, 'clock_moved_backward')
            self.assertIn('reads %d' % (self.start + 10), error.message)
            self.assertIn('time %d' % (self.start + 30), error.message)
            self.assertIn(RECOVERY_WORDS, error.message)
            self.assertIn('restart', error.message)
            self.restart()  # the hold survives a restart: it comes from the recorded time
        self.assert_nothing_happened()
        self.assertEqual(self.latched(), [])
        self.clocks.wall = self.start + 31  # recovery: the clock reads at or after the recorded time
        self.assertEqual(self.run_job(signed)['status'], 'modeled-dispatch')
        self.assertEqual(self.job_row(), ('running', 0, 1))

    def stepped_back_after_the_receipt_was_issued(self):
        """A receipt issued at T+30, a store that recorded T+30, then a clock that reads T: the receipt is dated ahead."""
        signed = self.receipt(issued_at=self.start + 30)
        self.clocks.wall = self.start + 30
        self.on_observe = lambda: (_ for _ in ()).throw(AppError('adoption_backend_unavailable_locked_or_metadata', 'x'))
        self.refused(lambda: self.run_job(signed))  # the first judgment recorded T+30 before the observation failed
        self.on_observe = lambda: None
        self.clocks.step(-30)
        return signed

    def test_a_receipt_issued_ahead_of_a_stepped_back_clock_names_the_hold_and_how_to_recover(self):
        signed = self.stepped_back_after_the_receipt_was_issued()
        for attempt in range(2):
            error = self.refused(lambda: self.run_job(signed))
            self.assertEqual(error.code, 'clock_moved_backward')
            self.assertIn('reads %d' % self.start, error.message)
            self.assertIn('time %d' % (self.start + 30), error.message)
            self.assertIn(RECOVERY_WORDS, error.message)
            self.assertIn('restart', error.message)
            self.restart()  # the hold comes from the recorded time, so it survives a restart
        self.assert_nothing_happened()
        self.assertEqual(self.latched(), [])

    def test_the_hold_precedence_is_read_only_and_applies_to_input_that_does_not_authenticate(self):
        forged = self.stepped_back_after_the_receipt_was_issued()
        forged = dict(forged, signature=forged['signature'][:-4] + 'AAAA')
        floor = self.policy.root / 'clock.json'
        before, anchors = floor.read_bytes(), dict(clock._ANCHORS)
        self.assertEqual(self.refused(lambda: self.run_job(forged)).code, 'clock_moved_backward')
        self.assertEqual(floor.read_bytes(), before)
        self.assertEqual(dict(clock._ANCHORS), anchors)

    def test_a_damaged_recorded_time_falls_through_to_the_original_refusal(self):
        signed = self.stepped_back_after_the_receipt_was_issued()
        (self.policy.root / 'clock.json').write_bytes(b'not json')
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_signature_expired')

    def test_a_receipt_issued_ahead_with_no_backward_step_keeps_its_original_refusal(self):
        self.clocks.wall = self.start + 30
        self.assertEqual(self.refused(lambda: self.run_job(self.receipt(issued_at=self.start + 60))).code,
                         'adoption_signature_expired')

    def test_the_manifest_expiry_refusal_still_records_the_receipts_expiry(self):
        # validate_manifest (AdoptionJob._check) refuses on the bare wall clock before anything else; the receipt's
        # expiry must be recorded there too, or a rollback after that first refusal reopens the receipt.
        self.manifest_time_rule = True
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_expired')
        self.assertEqual(len(self.latched()), 1)
        self.clocks.wall = self.expires - 20
        self.restart()
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_signature_expired')
        self.assert_nothing_happened()

    def test_a_manifest_refusal_does_not_record_anything_for_a_receipt_that_does_not_authenticate(self):
        self.manifest_time_rule = True
        forged = self.receipt()
        forged['signature'] = forged['signature'][:-4] + 'AAAA'
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.run_job(forged)).code, 'adoption_expired')
        self.assertEqual(self.latched(), [])
        self.assertFalse((self.policy.root / 'clock.json').exists())

    def test_an_open_window_dispatches_once_and_records_no_expiry(self):
        self.dispatch_running(self.start + 10)
        self.assertEqual(self.job_row(), ('running', 0, 1))
        self.assertEqual(len(self.consumed()), 1)
        self.assertEqual(self.latched(), [])
        self.assertEqual(self.dispatched, ['import'])
        self.assertTrue((self.job_root / 'approval.json').exists())

    def test_a_store_prepared_before_the_expiry_table_existed_gets_it_on_first_use(self):
        with self.policy.connection() as db:
            db.execute('DROP TABLE adoption_expired')
        signed = self.receipt()
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_signature_expired')
        self.assertEqual(len(self.latched()), 1)


class PermitLatchTests(AdoptionFixture):
    def test_the_inflight_check_runs_the_runtime_check_without_the_window_after_the_expiry(self):
        # The runtime check re-validates the broker policy through the host-held credentials; its window bounds judge when a
        # dispatch may start, so once the response is back (the window is over) it must be asked without them.
        permit = self.dispatch_running(self.start + 10)
        check = adoption.AdoptionRuntime.check
        self.clocks.elapse(LIFETIME + 1)
        check.reset_mock()
        permit.inflight_active()
        check.assert_called_once_with(self.job.manifest, verification=False, check_window=False)
        check.reset_mock()
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_signature_expired')  # the next dispatch is judged
        check.assert_called_once_with(self.job.manifest, verification=False)

    def test_check_active_refuses_after_the_expiry_and_after_a_backward_step_that_follows_it(self):
        permit = self.dispatch_running(self.start + 10)
        permit.check_active()  # open: authorized, and a marker committed
        self.clocks.elapse(LIFETIME)
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_signature_expired')
        self.clocks.wall = self.expires - 10
        (self.policy.root / 'clock.json').unlink()
        clock.reset_process_anchor()
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_signature_expired')
        self.assertEqual(len(self.latched()), 1)

    def authorizations(self):
        return self.rows('SELECT operation_id, phase, authorizations FROM adoption_authorizations')

    def test_the_authorization_check_enters_the_section_and_commits_a_marker_before_the_call(self):
        permit = self.dispatch_running(self.start + 10)
        before = {name: self.rows('SELECT * FROM ' + name) for name in ('jobs', 'consumed', 'ownership', 'events', 'revoked')}
        with patch.object(validity, 'critical', wraps=validity.critical) as section:
            permit.check_active()
            permit.check_active()
        self.assertEqual(section.call_count, 2)
        self.assertEqual(self.authorizations(), [(self.job.identifier, 'import', 2)])
        self.assertEqual({name: self.rows('SELECT * FROM ' + name) for name in before}, before)

    def test_the_watchdog_poll_never_commits_a_marker_or_enters_the_section(self):
        permit = self.dispatch_running(self.start + 10)
        with patch.object(validity, 'critical', side_effect=AssertionError('the section was entered')):
            for _ in range(5):
                permit.poll_active()
        self.assertEqual(self.authorizations(), [])

    def test_a_refused_authorization_commits_no_marker(self):
        permit = self.dispatch_running(self.start + 10)
        with self.policy.connection() as db:
            db.execute('INSERT INTO revoked VALUES (?,?)', ('fixture', 'key'))
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_permit_inactive')
        self.assertEqual(self.authorizations(), [])

    def test_an_expiry_latched_before_the_authorization_section_refuses_the_service_call(self):
        permit = self.dispatch_running(self.start + 10)
        child = lambda: adoption.AdoptionPermit(adoption._SEAL, self.job, permit.payload, self.runtime)
        latched, polled, checked, calls = race_with_a_latch(self, permit, child, hook=(adoption, '_critical', 'before'))
        self.assertEqual(latched, 'adoption_signature_expired')
        self.assertEqual((polled, checked, calls), (None, 'adoption_signature_expired', []))
        self.assertEqual(self.authorizations(), [])
        self.assertEqual(len(self.latched()), 1)

    def test_a_poll_that_passed_on_a_stale_read_never_authorizes_the_service_call(self):
        # The poll read no expiry record, then another process latched one, then the poll decided: it may return (it
        # authorizes nothing, the watchdog repeats it every 0.2 s), but the authorization that follows must refuse.
        permit = self.dispatch_running(self.start + 10)
        child = lambda: adoption.AdoptionPermit(adoption._SEAL, self.job, permit.payload, self.runtime)
        latched, polled, checked, calls = race_with_a_latch(self, permit, child, hook=(adoption, '_latched', 'after'),
                                                            poll_first=True)
        self.assertEqual(latched, 'adoption_signature_expired')
        self.assertEqual((polled, checked, calls), ('poll_returned', 'adoption_signature_expired', []))
        self.assertEqual(self.authorizations(), [])

    def test_the_open_path_of_poll_active_takes_no_lock_and_persists_nothing(self):
        permit = self.dispatch_running(self.start + 10)
        floor, database = self.policy.root / 'clock.json', self.policy.database
        before = (floor.read_bytes(), floor.stat().st_mtime_ns, database.read_bytes(), database.stat().st_mtime_ns)
        with patch.object(validity.fcntl, 'flock', side_effect=AssertionError('a lock was taken')), \
                patch.object(validity, 'critical', side_effect=AssertionError('the section was entered')):
            for _ in range(100):
                self.clocks.elapse(0.2)  # the effective time rises on every call; none of it is persisted
                permit.poll_active()
        self.assertEqual((floor.read_bytes(), floor.stat().st_mtime_ns, database.read_bytes(), database.stat().st_mtime_ns), before)
        self.assertEqual(sorted(path.name for path in self.policy.root.iterdir() if 'journal' in path.name), [])

    def test_a_write_reservation_from_another_process_is_never_refused_during_a_watchdog_loop(self):
        permit = self.dispatch_running(self.start + 10)
        refused, errors = watchdog_refusals(self, self.policy.database, permit.poll_active,
                                            tick=lambda: self.clocks.elapse(0.01))
        self.assertEqual(errors, [])
        self.assertEqual(refused, [])

    def test_a_cancel_from_another_process_during_a_watchdog_loop_is_not_refused(self):
        permit = self.dispatch_running(self.start + 10)
        other = object.__new__(adoption.AdoptionJob)
        other.policy, other.root, other.manifest, other.identifier = self.policy, self.job_root, self.manifest, 'second-job'
        other.sha256, other._completion = 'b' * 64, None
        with self.policy.connection() as db:
            db.execute('INSERT INTO jobs(id,root,manifest_sha256,status) VALUES (?,?,?,?)',
                       ('second-job', str(self.root / 'second'), 'b' * 64, 'prepared'))
        idle, resume, stop, queue, errors = FORK.Event(), threading.Event(), threading.Event(), FORK.Queue(), []

        def cancel_once():
            idle.wait(BOUND)
            try:
                with patch.object(adoption.AdoptionJob, 'status', return_value={}):
                    other.cancel()
                queue.put('cancelled')
            except AppError as error:
                queue.put(error.code)
        process = FORK.Process(target=cancel_once, daemon=True)
        process.start()
        self.addCleanup(lambda: process.is_alive() and process.terminate())

        def loop():  # the watchdog: a check, then a pause, until the other process is done
            try:
                while not stop.is_set():
                    permit.poll_active()
                    idle.set()
                    stop.wait(0.3)
            except BaseException as error:
                errors.append(getattr(error, 'code', repr(error)))
        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        try:
            self.assertEqual(queue.get(timeout=BOUND), 'cancelled')
        finally:
            stop.set()
            thread.join(BOUND)
        process.join(BOUND)
        self.assertEqual(errors, [])

    def test_a_closed_window_refuses_even_when_the_store_is_busy_and_latches_on_a_later_call(self):
        permit = self.dispatch_running(self.start + 10)
        self.clocks.elapse(LIFETIME)
        holder = sqlite3.connect(self.policy.database, timeout=0, isolation_level=None)
        self.addCleanup(holder.close)
        holder.execute('BEGIN IMMEDIATE')  # another writer holds the reservation: the latch cannot be written now
        self.assertEqual(self.refused(permit.poll_active).code, 'adoption_signature_expired')
        self.assertEqual(self.refused(permit.check_active).code, 'service_store_unavailable')  # no authority either
        holder.execute('ROLLBACK')
        self.assertEqual(self.latched(), [])
        self.assertEqual(self.refused(permit.poll_active).code, 'adoption_signature_expired')
        self.assertEqual(len(self.latched()), 1)

    def test_check_active_refuses_after_an_expiry_reached_in_another_process(self):
        permit = self.dispatch_running(self.start + 10)
        queue = FORK.Queue()

        def other_process():
            self.clocks.wall = self.expires + 1  # that process reads a time after the expiry
            try:  # it holds its own permit: a permit is bound to the process that made it
                adoption.AdoptionPermit(adoption._SEAL, self.job, permit.payload, self.runtime).check_active()
                queue.put(('ok', None))
            except AppError as error:
                queue.put(('refused', error.code))
        process = FORK.Process(target=other_process, daemon=True)
        process.start()
        self.addCleanup(lambda: process.is_alive() and process.terminate())
        self.assertEqual(queue.get(timeout=BOUND), ('refused', 'adoption_signature_expired'))
        process.join(BOUND)
        self.assertEqual(self.clocks.now(), self.start + 10)  # this process still reads a time before the expiry
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_signature_expired')
        (self.policy.root / 'clock.json').unlink()
        clock.reset_process_anchor()
        self.clocks.wall = self.expires - 30  # a backward step after the other process latched it
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_signature_expired')
        self.assertEqual(len(self.latched()), 1)

    def test_check_active_is_held_by_a_backward_step_before_the_expiry(self):
        permit = self.dispatch_running(self.start + 30)
        self.clocks.step(-20)
        error = self.refused(permit.check_active)
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertIn(RECOVERY_WORDS, error.message)
        self.assertEqual(self.latched(), [])
        self.clocks.wall = self.start + 31
        permit.check_active()

    def test_poll_active_inserts_nothing_when_the_window_is_open(self):
        permit = self.dispatch_running(self.start + 10)
        tables = ('jobs', 'consumed', 'ownership', 'events', 'approval_transcripts', 'adoption_operations', 'revoked',
                  'adoption_expired')
        before = [self.rows('SELECT * FROM ' + name) for name in tables]
        self.clocks.elapse(5)
        permit.poll_active()
        self.assertEqual([self.rows('SELECT * FROM ' + name) for name in tables], before)

    def test_the_manifest_expiry_refusal_in_check_active_records_the_expiry_before_refusing(self):
        permit = self.dispatch_running(self.start + 10)
        self.manifest_time_rule = True
        self.clocks.elapse(LIFETIME)
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_expired')
        self.assertEqual(len(self.latched()), 1)
        self.manifest_time_rule = False
        self.clocks.wall = self.expires - 20
        clock.reset_process_anchor()
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_signature_expired')

    def test_a_signer_revoked_after_dispatch_is_still_refused_inside_the_section(self):
        permit = self.dispatch_running(self.start + 10)
        with self.policy.connection() as db:
            db.execute('INSERT INTO revoked VALUES (?,?)', ('fixture', 'key'))
        self.assertEqual(self.refused(permit.check_active).code, 'adoption_permit_inactive')


class UnauthenticatedInputTests(AdoptionFixture):
    """Input that does not authenticate writes no expiry row and no recorded time, and keeps its original refusal."""

    def assert_untouched(self):
        self.assertEqual(self.latched(), [])
        self.assertFalse((self.policy.root / 'clock.json').exists())
        self.assertEqual(clock._ANCHORS, {})
        self.assert_nothing_happened()

    def test_a_forged_expired_receipt_is_refused_as_before_and_records_nothing(self):
        forged = self.receipt()
        forged['signature'] = forged['signature'][:-4] + 'AAAA'
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.run_job(forged)).code, 'adoption_signature_expired')
        self.assert_untouched()

    def test_a_forged_receipt_inside_its_window_is_refused_as_before_and_records_nothing(self):
        forged = self.receipt()
        forged['signature'] = forged['signature'][:-4] + 'AAAA'
        self.assertEqual(self.refused(lambda: self.run_job(forged)).code, 'adoption_signature_invalid')
        self.assert_untouched()

    def test_an_expired_receipt_from_an_unknown_signer_is_refused_as_before_and_records_nothing(self):
        unknown = self.receipt(key_id='unknown-key')
        self.clocks.elapse(LIFETIME + 1)
        self.assertEqual(self.refused(lambda: self.run_job(unknown)).code, 'adoption_signature_expired')
        self.assert_untouched()

    def test_a_revoked_signer_cannot_write_expiry_records(self):
        with self.policy.connection() as db:
            db.execute('INSERT INTO revoked VALUES (?,?)', ('fixture', 'key'))
        self.assertEqual(self.refused(lambda: self.run_job(self.receipt())).code, 'adoption_key_revoked')
        self.assert_untouched()
        for signed in (self.receipt(), self.receipt()):
            self.clocks.elapse(LIFETIME + 1)
            self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_signature_expired')
        self.assert_untouched()

    def test_a_future_issued_receipt_is_refused_as_before_and_records_nothing(self):
        self.assertEqual(self.refused(lambda: self.run_job(self.receipt(issued_at=self.start + 30))).code,
                         'adoption_signature_expired')
        self.assert_untouched()

    def test_the_expiry_table_is_capped_like_the_consumed_table(self):
        first, second = self.receipt(), self.receipt()
        self.assertNotEqual(first['payload']['nonce'], second['payload']['nonce'])
        self.clocks.elapse(LIFETIME + 1)
        with patch.object(adoption, 'MAX_EXPIRED', 1):
            self.assertEqual(self.refused(lambda: self.run_job(first)).code, 'adoption_signature_expired')
            self.assertEqual(self.refused(lambda: self.run_job(second)).code, 'adoption_store_capacity')
        self.assertEqual(len(self.latched()), 1)


class VerificationDispatchTests(AdoptionFixture):
    """verify_first_plan spends the same receipt on a second dispatch; its marker is a consumer of the section too."""

    def ready(self):
        self.dispatch_running(self.start + 10)
        with self.policy.connection() as db:
            db.execute("UPDATE jobs SET status='import_host_completed_unverified', controller_pid=NULL, controller_start=NULL, outcome=?",
                       (canonical({'host': {'cleanup': {'removed': True}}}).decode(),))
        self.observations.clear()

    def phase(self):
        return self.rows('SELECT verification_dispatches, verification_status FROM adoption_operations')[0]

    def verify(self):
        return self.job.verify_first_plan(runtime=self.runtime)

    def test_an_open_window_marks_the_verification_dispatch(self):
        self.ready()
        self.assertEqual(self.verify()['status'], 'modeled-dispatch')
        self.assertEqual(self.phase(), (1, 'running'))
        self.assertEqual(self.dispatched, ['import', 'verification'])

    def test_an_expired_stored_receipt_is_latched_and_refused_before_anything_is_observed(self):
        self.ready()
        self.clocks.elapse(LIFETIME)
        self.assertEqual(self.refused(self.verify).code, 'adoption_signature_expired')
        self.assertEqual(self.phase(), (0, 'not_started'))
        self.assertEqual(self.observations, [])
        self.assertEqual(len(self.latched()), 1)
        self.clocks.wall = self.expires - 20
        self.restart()
        self.assertEqual(self.refused(self.verify).code, 'adoption_signature_expired')
        self.assertEqual(self.phase(), (0, 'not_started'))

    def test_an_expiry_reached_during_the_observation_refuses_the_marker(self):
        self.ready()
        self.on_observe = lambda: self.clocks.elapse(LIFETIME)
        self.assertEqual(self.refused(self.verify).code, 'adoption_signature_expired')
        self.assertEqual(self.observations, ['successor'])
        self.assertEqual(self.phase(), (0, 'not_started'))
        self.assertEqual(self.dispatched, ['import'])
        self.assertEqual(self.job_row()[0], 'import_host_completed_unverified')


class ConcurrentLatchTests(AdoptionFixture):
    """Two real processes. The window judgment, the recorded time, the expiry record and the consumption are one
    critical section, so no interleaving lets an approval act after another process latched it."""

    def start_process(self, body):
        queue = FORK.Queue()

        def main():
            try:
                body()
                result = ('ok', None)
            except AppError as error:
                result = ('refused', error.code)
            except BaseException as error:
                result = ('error', repr(error))
            queue.put(result)
        process = FORK.Process(target=main, daemon=True)
        process.start()
        self.addCleanup(lambda: process.is_alive() and process.terminate())
        return process, queue

    def test_an_expiry_latched_between_the_observation_and_the_consumption_refuses_the_consumption(self):
        paused, release = FORK.Event(), FORK.Event()
        signed = self.receipt()

        def process_a():
            self.clocks.wall = self.start + 10  # this process reads a time inside the window throughout
            self.on_observe = lambda: (paused.set(), release.wait(BOUND))
            self.run_job(signed)

        a_process, a_queue = self.start_process(process_a)
        self.assertTrue(paused.wait(BOUND))
        self.clocks.elapse(LIFETIME + 1)  # process B reaches the expiry and latches it
        self.assertEqual(self.refused(lambda: self.run_job(signed)).code, 'adoption_signature_expired')
        self.assertEqual(len(self.latched()), 1)
        release.set()
        self.assertEqual(a_queue.get(timeout=BOUND), ('refused', 'adoption_signature_expired'))
        a_process.join(BOUND)
        self.assert_nothing_happened()


if __name__ == '__main__':
    unittest.main()
