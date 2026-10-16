"""Windows worker-evidence readers: a durable store-wide mark, real restarts, and no loose-file current admissibility.

Shares the stand-ins and the restart child of test_worker_evidence_freshness_floor (no Docker import).
"""
import contextlib
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock, windows_storage as storage, windows_workbench as win
from intune_iac import windows_worker_evidence as native, windows_worker_evidence_store as receiver
from intune_iac import worker_evidence as contract
from intune_iac.io import AppError, canonical, digest
from plugin_tests.test_windows_storage_r4 import CANONICAL, ROOT
from plugin_tests.test_windows_workbench_r4 import FilesystemAPI
from plugin_tests.test_worker_evidence_freshness_floor import (make_envelope, OK, REJECT, T, TENANT, Shape, aging, expiring, make_policy, make_request,
                                                               restart, stand_ins, wall)


def ticking_wall(value):
    """The wall at `value` now, advancing with real time (a frozen wall during a 5 s busy wait is a backward step)."""
    start = time.monotonic()
    return patch.object(time, 'time', side_effect=lambda: float(value) + (time.monotonic() - start))


class WindowsStoreReaderTests(Shape, unittest.TestCase):
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
        self.verifier = OK

        @contextlib.contextmanager
        def checked(pin, scratch, api):
            yield self.verifier
        patch.object(native, '_verifier', side_effect=checked).start()

    def ingest(self):
        return receiver._ingest(self.store, self.input + '\\envelope.json', self.input + '\\request.json',
                                self.input + '\\trust.json', self.input + '\\pin.json', self.scratch, self.api)

    def publish(self, envelope):
        storage._create_file(self.input, 'envelope.json', canonical(envelope), self.api)
        with wall(T + 1):
            self.ingest()

    def read(self, historical=False):
        return receiver._reopen(self.store, digest(self.req), self.input + '\\trust.json', self.input + '\\pin.json',
                                self.scratch, self.api, historical=historical)

    def restart_read(self, at, historical):
        return restart(kind='windows', root=self.temp.name, wall=at, historical=historical, directories=self.api.directories)

    def rows(self):
        with self.store._connection() as db:
            return db.execute("SELECT key FROM metadata WHERE key LIKE 'worker_evidence_%'").fetchall()

    def mark(self):
        with self.store._connection() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='worker_evidence_clock'").fetchone()
        return None if row is None else json.loads(row[0])['high_water']

    def test_ingest_records_one_store_wide_mark(self):
        self.publish(expiring(self.req))
        self.assertGreaterEqual(self.mark(), T + 1)
        self.assertEqual(len(self.rows()), 3)  # received, head and the one clock key

    def test_forward_step_with_an_invalid_signature_leaves_the_mark_alone(self):
        self.publish(expiring(self.req))
        before = self.mark()
        self.assertGreaterEqual(before, T + 1)
        self.verifier = REJECT
        with wall(T + 500), self.assertRaises(AppError) as raised:
            self.read()
        self.assertEqual(raised.exception.code, 'worker_evidence_signature_invalid')
        self.assertEqual(self.mark(), before)

    def test_an_unrecordable_time_refuses_admission(self):
        calls = []
        real = receiver._mark

        def failing(db):
            calls.append(1)
            if len(calls) > 1:
                raise sqlite3.OperationalError('disk full')
            return real(db)

        storage._create_file(self.input, 'envelope.json', canonical(expiring(self.req)), self.api)
        with patch.object(receiver, '_mark', side_effect=failing), wall(T + 1), self.assertRaises(AppError) as raised:
            self.ingest()
        self.assertEqual(raised.exception.code, 'worker_evidence_clock_unrecorded')
        self.assertEqual(self.rows(), [])

    def failing_clock_write(self):
        real = receiver.canonical

        def canonical_or_fail(value):
            if isinstance(value, dict) and 'high_water' in value:
                raise OSError('disk full')
            return real(value)
        return patch.object(receiver, 'canonical', side_effect=canonical_or_fail)

    def test_a_temporal_refusal_keeps_its_code_when_its_closure_cannot_be_recorded(self):
        self.publish(expiring(self.req))
        with self.failing_clock_write(), wall(T + 20), self.assertRaises(AppError) as raised:
            self.read()
        self.assertEqual(raised.exception.code, 'worker_evidence_expired')
        self.assertIs(raised.exception.closure_recorded, False)
        self.assertIn('worker_evidence_clock_unrecorded', ''.join(raised.exception.__notes__))

    def test_an_admission_is_refused_when_the_time_cannot_be_recorded_by_the_write(self):
        storage._create_file(self.input, 'envelope.json', canonical(expiring(self.req)), self.api)
        with self.failing_clock_write(), wall(T + 1), self.assertRaises(AppError) as raised:
            self.ingest()
        self.assertEqual(raised.exception.code, 'worker_evidence_clock_unrecorded')
        self.assertEqual(self.rows(), [])

    def test_an_invalid_input_poisons_neither_the_process_floor_nor_the_durable_mark(self):
        self.publish(expiring(self.req))
        self.verifier = REJECT
        with wall(T + 500), self.assertRaises(AppError):
            self.read()
        self.verifier = OK
        with wall(T + 5):  # the true wall again and a valid verifier
            self.assertTrue(self.read()['baseline_admissible'])
        self.assertLess(self.mark(), T + 500)

    def hold_write_lock(self):
        holder = sqlite3.connect(self.api.real(CANONICAL + '\\received\\observations.sqlite3'), timeout=0, isolation_level=None)
        holder.execute('BEGIN IMMEDIATE')
        self.addCleanup(holder.close)

    def test_a_busy_write_lock_keeps_the_temporal_code_with_the_note(self):
        self.publish(expiring(self.req))
        self.hold_write_lock()
        with wall(T + 20), self.assertRaises(AppError) as raised:
            self.read()
        self.assertEqual(raised.exception.code, 'worker_evidence_expired')
        self.assertIs(raised.exception.closure_recorded, False)

    def test_a_busy_write_lock_is_unrecorded_for_an_admissible_read(self):
        self.publish(aging(self.req))
        self.hold_write_lock()
        with ticking_wall(T + 70), self.assertRaises(AppError) as raised:  # beyond the 60 s step: the mark must be recorded
            self.read()
        self.assertEqual(raised.exception.code, 'worker_evidence_clock_unrecorded')

    def read_historical(self):
        with wall(T + 10):
            return self.read(historical=True)

    def root_names(self):
        return sorted(self.api.names(CANONICAL + '\\received'))

    def test_repeated_current_reopens_within_the_step_leave_the_root_unchanged(self):
        self.publish(expiring(self.req))
        before = self.root_names()
        for at in (T + 2, T + 3, T + 5, T + 5, T + 6):
            with wall(at):
                self.assertTrue(self.read()['baseline_admissible'])
        self.assertEqual(self.root_names(), before)
        self.assertEqual(self.mark(), T + 1)  # nothing was written

    def test_a_read_beyond_the_step_records_the_mark_once(self):
        self.publish(aging(self.req))
        with wall(T + 70):  # a frozen wall plus the process carry drifts by real seconds: keep clear of the staleness edge
            self.assertTrue(self.read()['baseline_admissible'])
        self.assertGreaterEqual(self.mark(), T + 70)
        settled = self.root_names()
        with wall(T + 80):
            self.read()
        self.assertEqual(self.root_names(), settled)

    def test_a_closed_window_is_recorded_once_and_then_read_without_a_write(self):
        self.publish(expiring(self.req))
        with wall(T + 20), self.assertRaises(AppError):
            self.read()
        self.assertGreaterEqual(self.mark(), T + 20)
        settled = self.root_names()
        for _ in range(3):
            with wall(T + 20), self.assertRaises(AppError) as raised:
                self.read()
            self.assertEqual(raised.exception.code, 'worker_evidence_expired')
        self.assertEqual(self.root_names(), settled)


    def raw_mark(self):
        db = sqlite3.connect(self.api.real(CANONICAL + '\\received\\observations.sqlite3'), timeout=0)
        try:
            row = db.execute("SELECT value FROM metadata WHERE key='worker_evidence_clock'").fetchone()
        finally:
            db.close()
        return 0 if row is None else json.loads(row[0])['high_water']

    def test_a_closure_committed_between_decision_and_receipt_check_is_not_read_past(self):
        """A decides at T+5 (admissible); before A checks the stored receipt, B reads at T+20 and tries to record the closure.
        A's mark, decision and receipt check are one read transaction, so B cannot commit in between: A is serialized before
        B's closure. (Without it A would admit on a mark older than a closure already committed.)"""
        self.publish(expiring(self.req))
        real_verify, real_metadata = contract.verify_envelope, receiver._metadata
        seen = {}

        def hooked(*args, **kwargs):
            outcome = real_verify(*args, **kwargs)
            if not kwargs.get('historical') and 'closer' not in seen:
                seen['closer'] = None
                with wall(T + 20):
                    try:
                        self.read()
                    except AppError as error:
                        seen['closer'] = error
                seen['closer_done'] = True
            return outcome

        def watching(db, key):
            if key.startswith(receiver.RECEIVED) and seen.get('closer_done') and 'mark_at_check' not in seen:
                seen['mark_at_check'] = self.raw_mark()
            return real_metadata(db, key)

        with patch.object(contract, 'verify_envelope', side_effect=hooked), \
                patch.object(receiver, '_metadata', side_effect=watching), wall(T + 5):
            try:
                admitted = self.read()['baseline_admissible']
            except AppError as error:
                admitted = error.code
        self.assertEqual(seen['closer'].code, 'worker_evidence_expired')
        # The reader returns the closure, or an admission serialized before the closure's commit; never a bare refusal that is
        # neither, and never an admission past a committed closure.
        self.assertIn(admitted, ('worker_evidence_expired', True))
        self.assertFalse(admitted is True and seen['mark_at_check'] >= T + 20, (admitted, seen))

    def every_commit_fails(self):
        """Every COMMIT raises, and so does the connection's own context exit (a second commit attempt)."""
        real = sqlite3.connect

        class Proxy:
            def __init__(self, inner):
                object.__setattr__(self, 'inner', inner)

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def __setattr__(self, name, value):
                setattr(self.inner, name, value)

            def execute(self, sql, *args):
                if sql == 'COMMIT':
                    raise sqlite3.OperationalError('disk I/O error')
                return self.inner.execute(sql, *args)

            def __enter__(self):
                return self

            def __exit__(self, kind, value, trace):
                if kind is None:
                    raise sqlite3.OperationalError('disk I/O error')
                return False
        return patch.object(sqlite3, 'connect', side_effect=lambda *a, **k: Proxy(real(*a, **k)))

    def test_persistent_commit_failure_keeps_the_temporal_code_through_context_exit(self):
        self.publish(expiring(self.req))
        with self.every_commit_fails(), wall(T + 20), self.assertRaises(AppError) as raised:
            self.read()
        self.assertEqual(raised.exception.code, 'worker_evidence_expired')
        self.assertIs(raised.exception.closure_recorded, False)

    def test_persistent_commit_failure_is_unrecorded_for_an_admissible_ingest(self):
        storage._create_file(self.input, 'envelope.json', canonical(expiring(self.req)), self.api)
        with self.every_commit_fails(), wall(T + 1), self.assertRaises(AppError) as raised:
            self.ingest()
        self.assertEqual(raised.exception.code, 'worker_evidence_clock_unrecorded')
        self.assertEqual(self.rows(), [])


    def with_a_time_dependent_judgment(self, at):
        """No field of a real successful judgment depends on the time (only the two terminal refusals do), so stand one in:
        from `at` on the successful result reads as no longer a baseline, as a future aging field would."""
        real = contract.verify_envelope

        def transitioning(*args, **kwargs):
            verified = real(*args, **kwargs)
            if kwargs.get('historical') or kwargs['now'] < at:
                return verified
            result = verified.result()
            result.update(baseline_admissible=False, current_status='aged')
            return contract.VerifiedEvidence(contract._SEAL, verified._raw, result)
        return patch.object(contract, 'verify_envelope', side_effect=transitioning)

    def test_a_transition_first_observed_inside_the_step_is_recorded(self):
        self.publish(aging(self.req))  # mark T+1
        before = self.root_names()
        with self.with_a_time_dependent_judgment(T + 30), wall(T + 40):  # 39 s ahead of the mark: inside the 60 s step
            self.assertFalse(self.read()['baseline_admissible'])
        self.assertGreaterEqual(self.mark(), T + 40)  # recorded at its first observation
        self.assertNotEqual(self.root_names(), before)

    def test_after_a_wall_step_back_an_observed_transition_does_not_return(self):
        self.publish(aging(self.req))
        with self.with_a_time_dependent_judgment(T + 30), wall(T + 40):
            self.assertFalse(self.read()['baseline_admissible'])
        clock.reset_process_anchor()  # a restart
        with self.with_a_time_dependent_judgment(T + 30), wall(T + 10), self.assertRaises(AppError) as held:
            self.read()  # the wall stepped back before the transition: judged at the mark, so the earlier admission cannot return
        self.assertEqual(held.exception.code, 'worker_evidence_clock_moved_backward')
        self.assertFalse(self.read_historical()['baseline_admissible'])

    def test_an_unchanged_judgment_inside_the_step_is_not_recorded(self):
        self.publish(aging(self.req))
        before = self.root_names()
        with wall(T + 40):
            self.assertTrue(self.read()['baseline_admissible'])
        self.assertEqual(self.root_names(), before)
        self.assertEqual(self.mark(), T + 1)


    def put_and_ingest(self, request, envelope, at):
        """Ingest under fresh file names (the native fixture never overwrites an input file)."""
        self.puts = getattr(self, 'puts', 0) + 1
        names = ('request-%d.json' % self.puts, 'envelope-%d.json' % self.puts)
        storage._create_file(self.input, names[0], canonical(request), self.api)
        storage._create_file(self.input, names[1], canonical(envelope), self.api)
        with wall(at):
            return receiver._ingest(self.store, self.input + '\\' + names[1], self.input + '\\' + names[0],
                                    self.input + '\\trust.json', self.input + '\\pin.json', self.scratch, self.api)

    def store_a_and_b(self):
        """The reviewer's input: mark 100 (T+100), envelope A read unchanged at T+160 (not recorded), B expiring at T+130."""
        self.b_request = make_request(self.policy, '8' * 32)
        self.put_and_ingest(self.b_request, make_envelope(self.b_request, issued_at=T, expires_at=T + 130, read_at=T - 5), T + 1)
        self.put_and_ingest(self.req, make_envelope(self.req, issued_at=T, expires_at=T + 500, read_at=T - 5), T + 100)

    def read_b(self, at):
        with wall(at):
            return receiver._reopen(self.store, digest(self.b_request), self.input + '\\trust.json', self.input + '\\pin.json',
                                    self.scratch, self.api)

    def test_current_admission_is_held_while_the_wall_is_behind_the_recorded_time(self):
        self.store_a_and_b()
        self.assertEqual(self.mark(), T + 100)
        with wall(T + 160):  # an unchanged judgment inside the step: not recorded
            self.assertTrue(self.read()['baseline_admissible'])
        self.assertEqual(self.mark(), T + 100)
        clock.reset_process_anchor()  # a restart, the wall far behind the mark
        names = self.root_names()
        with self.assertRaises(AppError) as held:
            self.read_b(T - 1000)
        self.assertEqual(held.exception.code, 'worker_evidence_clock_moved_backward')
        self.assertEqual(self.mark(), T + 100)  # a held read records nothing
        self.assertEqual(self.root_names(), names)
        self.assertTrue(self.read_b(T + 99)['baseline_admissible'])  # within the tolerance of the mark: admitted

    def test_an_expired_envelope_read_while_the_wall_is_behind_is_still_expired(self):
        c = make_request(self.policy, '9' * 32)
        self.put_and_ingest(c, make_envelope(c, issued_at=T, expires_at=T + 10, read_at=T - 5), T + 1)
        self.store_a_and_b()  # the mark becomes T+100
        clock.reset_process_anchor()
        with wall(T - 1000), self.assertRaises(AppError) as closed:
            receiver._reopen(self.store, digest(c), self.input + '\\trust.json', self.input + '\\pin.json', self.scratch, self.api)
        self.assertEqual(closed.exception.code, 'worker_evidence_expired')  # a closed window still wins over the hold
        with self.assertRaises(AppError) as held:  # while a still-open envelope is held
            self.read_b(T - 1000)
        self.assertEqual(held.exception.code, 'worker_evidence_clock_moved_backward')

    def test_ingest_is_held_while_the_wall_is_behind(self):
        self.store_a_and_b()
        clock.reset_process_anchor()
        d = make_request(self.policy, 'a' * 32)
        with self.assertRaises(AppError) as held:
            self.put_and_ingest(d, make_envelope(d, issued_at=T, expires_at=T + 400, read_at=T - 5), T - 1000)
        self.assertEqual(held.exception.code, 'worker_evidence_clock_moved_backward')


    def slow_wall(self):
        """A process anchored at wall T+100 whose monotonic clock then runs 70 s while the wall reads T+90 (effective T+170)."""
        self.mono = [0.0]
        patch.object(clock, 'monotonic', side_effect=lambda: self.mono[0]).start()
        a = make_envelope(self.req, issued_at=T, expires_at=T + 500, read_at=T - 5)
        self.put_and_ingest(self.req, a, T + 100)  # the mark is T+100 and the process anchor is taken at T+100
        self.assertEqual(self.mark(), T + 100)
        self.mono[0] = 70.0

    def test_a_held_admission_never_raises_the_mark_on_any_path(self):
        self.slow_wall()
        d = make_request(self.policy, 'b' * 32)
        for _ in range(2):
            with self.assertRaises(AppError) as held:  # ingest: the write path (_judge)
                self.put_and_ingest(d, make_envelope(d, issued_at=T, expires_at=T + 400, read_at=T - 5), T + 90)
            self.assertEqual(held.exception.code, 'worker_evidence_clock_moved_backward')
            with wall(T + 90), self.assertRaises(AppError) as reopened:  # reopen: the read path
                self.read()
            self.assertEqual(reopened.exception.code, 'worker_evidence_clock_moved_backward')
            self.assertEqual(self.mark(), T + 100)
        clock.reset_process_anchor()  # a restart
        self.assertEqual(self.mark(), T + 100)

    def test_a_fresh_process_admits_after_a_slow_wall_held_one(self):
        self.slow_wall()
        with wall(T + 110), self.assertRaises(AppError) as held:  # the wall passed the mark, but this process floor leads it
            self.read()
        self.assertEqual(held.exception.code, 'worker_evidence_clock_moved_backward')
        clock.reset_process_anchor()  # a new process: a fresh anchor, and the held read never raised the mark
        with wall(T + 110):
            self.assertTrue(self.read()['baseline_admissible'])


class QualificationScriptTests(unittest.TestCase):
    """The native harness judges current admissibility, so it must do so through a store, never a loose-file inspect."""

    def test_script_does_not_inspect_a_loose_file_non_historically(self):
        import ast
        path = Path(__file__).resolve().parents[1] / 'scripts' / 'qualify-windows-worker-evidence.py'
        calls = [n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.Call)
                 and getattr(n.func, 'attr', None) == '_inspect']
        self.assertEqual(calls, [])
        self.assertIn('reopen_windows_evidence(args.evidence_store,native.contract.digest', path.read_text())


class WindowsInspectReaderTests(unittest.TestCase):
    """Loose files have no store to hold a durable mark: only the historical inspection is offered."""

    def setUp(self):
        self.addCleanup(clock.reset_process_anchor)
        self.addCleanup(patch.stopall)
        stand_ins()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.api = FilesystemAPI(Path(self.temp.name))
        policy = make_policy(); req = make_request(policy)
        storage._create_directory(ROOT, 'input', self.api); storage._create_directory(ROOT, 'scratch', self.api)
        self.input = ROOT + '\\input'
        for name, value in (('request.json', req), ('trust.json', policy), ('envelope.json', expiring(req))):
            storage._create_file(self.input, name, canonical(value), self.api)
        storage._create_file(self.input, 'pin.json', b'{}', self.api)

        @contextlib.contextmanager
        def checked(pin, scratch, api):
            yield OK
        patch.object(native, '_verifier', side_effect=checked).start()

    def inspect(self, **kw):
        return native._inspect(self.input + '\\envelope.json', self.input + '\\request.json', self.input + '\\trust.json',
                               self.input + '\\pin.json', ROOT + '\\scratch', self.api, **kw)

    def test_non_historical_inspection_requires_a_store(self):
        with wall(T + 5), self.assertRaises(AppError) as raised:
            self.inspect()
        self.assertEqual(raised.exception.code, 'worker_evidence_inspect_requires_store')

    def test_historical_inspection_still_works(self):
        with wall(T + 20):
            self.assertFalse(self.inspect(historical=True)['baseline_admissible'])


if __name__ == '__main__':
    unittest.main()
