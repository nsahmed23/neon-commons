"""Windows worker-evidence readers: a durable store-wide mark, real restarts, and no loose-file current admissibility.

Shares the stand-ins and the restart child of test_worker_evidence_freshness_floor (no Docker import).
"""
import contextlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock, windows_storage as storage, windows_workbench as win
from intune_iac import windows_worker_evidence as native, windows_worker_evidence_store as receiver
from intune_iac.io import AppError, canonical, digest
from plugin_tests.test_windows_storage_r4 import CANONICAL, ROOT
from plugin_tests.test_windows_workbench_r4 import FilesystemAPI
from plugin_tests.test_worker_evidence_freshness_floor import (OK, REJECT, T, TENANT, Shape, expiring, make_policy, make_request,
                                                               restart, stand_ins, wall)


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
        self.publish(expiring(self.req))
        self.hold_write_lock()
        with wall(T + 5), self.assertRaises(AppError) as raised:
            self.read()
        self.assertEqual(raised.exception.code, 'worker_evidence_clock_unrecorded')


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
