"""Signed real service/TLS/SQLite setup with injected shutdown fault boundaries.

No native container or external mutation is performed by these tests. Assertions
read independent durable rows and retained receipts, including failed recording.
"""
from contextlib import contextmanager
import json
import sqlite3
import unittest
from unittest.mock import patch

from intune_iac import worker_service as service, worker_broker as broker
from intune_iac.io import AppError
from plugin_tests import test_worker_service_r4 as fixture_module


class ServiceShutdownR4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_module.WorkerServiceR4Tests.setUpClass()
        cls.probe = fixture_module.WorkerServiceR4Tests.probe

    @classmethod
    def tearDownClass(cls):
        fixture_module.WorkerServiceR4Tests.tearDownClass()

    setUp = fixture_module.WorkerServiceR4Tests.setUp
    prepare = fixture_module.WorkerServiceR4Tests.prepare
    job = fixture_module.WorkerServiceR4Tests.job
    runtime = fixture_module.WorkerServiceR4Tests.runtime
    receipt = fixture_module.WorkerServiceR4Tests.receipt

    def rows(self):
        with sqlite3.connect(self.root / 'trust/authority/service.sqlite3') as db:
            row = db.execute('SELECT status,dispatches,outcome FROM jobs WHERE id=?', (self.identifier,)).fetchone()
            owners = db.execute('SELECT COUNT(*) FROM ownership WHERE job=?', (self.identifier,)).fetchone()[0]
        return row, owners

    def test_primary_host_failure_survives_broker_close_failure(self):
        self.prepare()
        close = broker.UnixBrokerServer.close
        def failing_close(server):
            close(server)
            raise OSError('injected secondary close failure')
        with patch.object(service.host, 'launch', side_effect=AppError('literal_primary_host', 'primary')), \
                patch.object(broker.UnixBrokerServer, 'close', failing_close):
            result = self.job().run(self.receipt(), runtime=self.runtime())
        row, owners = self.rows()
        self.assertEqual(row[:2], ('outcome_unknown', 1))
        self.assertEqual(owners, 2)
        self.assertEqual(result['outcome']['primary_error'], 'literal_primary_host')
        self.assertIn({'phase': 'broker_close', 'error': 'OSError'}, result['outcome']['shutdown_failures'])
        self.assertEqual(self.fixture.calls, [])

    def test_original_interrupt_survives_close_failure(self):
        self.prepare()
        original = KeyboardInterrupt('literal original interruption')
        close = broker.UnixBrokerServer.close
        def failing_close(server):
            close(server)
            raise OSError('secondary')
        with patch.object(service.host, 'launch', side_effect=original), \
                patch.object(broker.UnixBrokerServer, 'close', failing_close), \
                self.assertRaises(KeyboardInterrupt) as caught:
            self.job().run(self.receipt(), runtime=self.runtime())
        self.assertIs(caught.exception, original)
        row, owners = self.rows()
        self.assertEqual(row[:2], ('outcome_unknown', 1))
        self.assertEqual(owners, 2)
        self.assertEqual(json.loads(row[2])['primary_error'], 'KeyboardInterrupt')

    def test_outcome_database_failure_preserves_primary_and_fallback(self):
        self.prepare()
        job = self.job()
        original = AppError('literal_primary_host', 'primary')
        connection = job.policy.connection
        stopped = False
        def fail_host(*args):
            nonlocal stopped
            stopped = True
            raise original
        @contextmanager
        def fail_recording():
            if stopped:
                raise sqlite3.OperationalError('injected durable outcome failure')
            with connection() as db:
                yield db
        with patch.object(service.host, 'launch', fail_host), patch.object(job.policy, 'connection', fail_recording), \
                self.assertRaises(AppError) as caught:
            job.run(self.receipt(), runtime=self.runtime())
        self.assertIs(caught.exception, original)
        row, owners = self.rows()
        self.assertEqual(row[:2], ('running', 1))
        self.assertEqual(owners, 2)
        receipt = json.loads((self.job_root / 'service-receipt.json').read_bytes())
        self.assertEqual(receipt['primary_error'], 'literal_primary_host')
        self.assertEqual(receipt['authority_recording'], 'failed_or_uncertain')
        self.assertIn({'phase': 'authority_outcome', 'error': 'OperationalError'}, receipt['recording_failures'])

    def test_postcommit_recording_failure_does_not_replay_or_invent_rollback(self):
        self.prepare()
        job = self.job()
        original = AppError('literal_primary_host', 'primary')
        connection = job.policy.connection
        stopped = False
        def fail_host(*args):
            nonlocal stopped
            stopped = True
            raise original
        @contextmanager
        def fail_after_commit():
            with connection() as db:
                yield db
            if stopped:
                raise OSError('injected lost acknowledgement after actual commit')
        with patch.object(service.host, 'launch', fail_host), patch.object(job.policy, 'connection', fail_after_commit), \
                self.assertRaises(AppError) as caught:
            job.run(self.receipt(), runtime=self.runtime())
        self.assertIs(caught.exception, original)
        row, owners = self.rows()
        self.assertEqual(row[:2], ('outcome_unknown', 1))
        self.assertEqual(owners, 2)
        receipt = json.loads((self.job_root / 'service-receipt.json').read_bytes())
        self.assertEqual(receipt['authority_recording'], 'failed_or_uncertain')
        with self.assertRaises(AppError):
            self.job().run(self.receipt(), runtime=self.runtime())
        self.assertEqual(self.rows()[0][1], 1)

    def test_secondary_shutdown_interrupt_is_not_absorbed(self):
        self.prepare()
        original = AppError('literal_primary_host', 'primary')
        interrupt = KeyboardInterrupt('literal shutdown interruption')
        close = broker.UnixBrokerServer.close
        def interrupted_close(server):
            close(server)
            raise interrupt
        with patch.object(service.host, 'launch', side_effect=original), \
                patch.object(broker.UnixBrokerServer, 'close', interrupted_close), \
                self.assertRaises(KeyboardInterrupt) as caught:
            self.job().run(self.receipt(), runtime=self.runtime())
        self.assertIs(caught.exception, interrupt)
        self.assertIs(caught.exception.__cause__, original)
        row, owners = self.rows()
        self.assertEqual(row[:2], ('outcome_unknown', 1))
        self.assertEqual(owners, 2)
        self.assertEqual(json.loads(row[2])['primary_error'], 'literal_primary_host')

    def test_host_success_with_failed_cleanup_cannot_be_completed(self):
        self.prepare()
        close = broker.UnixBrokerServer.close
        def failing_close(server):
            close(server)
            raise OSError('injected cleanup failure')
        # This literal result isolates finalization; it is not native-host proof.
        with patch.object(service.host, 'launch', return_value={'status': 'complete', 'cleanup': {'removed': True}}), \
                patch.object(broker.UnixBrokerServer, 'close', failing_close):
            result = self.job().run(self.receipt(), runtime=self.runtime())
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(result['outcome']['primary_error'], 'OSError')
        self.assertEqual(self.rows()[1], 2)

    def test_archive_and_failure_event_errors_preserve_primary(self):
        self.prepare()
        job = self.job()
        primary = AppError('literal_primary_host', 'primary')
        exclusive = service.protected._exclusive
        event = job.policy.event
        def fail_archive(path, data):
            if path.name == 'service-receipt.json': raise OSError('archive')
            return exclusive(path, data)
        def fail_failure_event(db, identifier, kind, payload):
            if kind == 'receipt_archive_failed': raise sqlite3.OperationalError('event')
            return event(db, identifier, kind, payload)
        with patch.object(service.host, 'launch', side_effect=primary), \
                patch.object(service.protected, '_exclusive', fail_archive), \
                patch.object(job.policy, 'event', fail_failure_event), self.assertRaises(AppError) as caught:
            job.run(self.receipt(), runtime=self.runtime())
        self.assertIs(caught.exception, primary)
        self.assertEqual(self.rows()[0][:2], ('outcome_unknown', 1))
        self.assertEqual(self.rows()[1], 2)
        self.assertEqual([x['phase'] for x in primary.service_failure_record['recording_failures']],
                         ['service_receipt_archive', 'receipt_failure_event'])

    def test_final_status_failure_cannot_hide_primary(self):
        self.prepare()
        job = self.job()
        primary = AppError('literal_primary_host', 'primary')
        with patch.object(service.host, 'launch', side_effect=primary), \
                patch.object(job, 'status', side_effect=sqlite3.OperationalError('injected last read')), \
                self.assertRaises(AppError) as caught:
            job.run(self.receipt(), runtime=self.runtime())
        self.assertIs(caught.exception, primary)
        self.assertEqual(self.rows()[0][:2], ('outcome_unknown', 1))
        self.assertEqual(primary.service_failure_record['recording_failures'][-1],
                         {'phase': 'final_status_read', 'error': 'OperationalError'})

    def test_receipt_interruption_preserves_unknown_and_interrupt(self):
        self.prepare()
        primary = AppError('literal_primary_host', 'primary')
        interruption = KeyboardInterrupt('receipt interruption')
        exclusive = service.protected._exclusive
        def fail_archive(path, data):
            if path.name == 'service-receipt.json': raise interruption
            return exclusive(path, data)
        with patch.object(service.host, 'launch', side_effect=primary), \
                patch.object(service.protected, '_exclusive', fail_archive), self.assertRaises(KeyboardInterrupt) as caught:
            self.job().run(self.receipt(), runtime=self.runtime())
        self.assertIs(caught.exception, interruption)
        self.assertIs(caught.exception.__cause__, primary)
        self.assertEqual(self.rows()[0][:2], ('outcome_unknown', 1))
        self.assertEqual(self.rows()[1], 2)


if __name__ == '__main__':
    unittest.main()
