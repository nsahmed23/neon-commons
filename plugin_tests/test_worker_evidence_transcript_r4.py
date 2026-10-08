"""Original approval retention, real signature verification, no native dispatch."""
import copy
import sqlite3
import unittest
from unittest.mock import patch
from plugin_tests import test_worker_service_r4 as service_tests
from intune_iac import worker_service as service
from intune_iac.io import AppError,canonical,digest,parse_json

class TranscriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):service_tests.WorkerServiceR4Tests.setUpClass()
    @classmethod
    def tearDownClass(cls):service_tests.WorkerServiceR4Tests.tearDownClass()
    def setUp(self):
        self.f=service_tests.WorkerServiceR4Tests('test_actual_signed_native_container_tls_mutation_and_literal_readback');self.f.setUp();self.addCleanup(self.f.doCleanups);self.f.prepare()
    def test_original_verified_snapshot_survives_caller_mutation(self):
        receipt=self.f.receipt();original=canonical(receipt);job=self.f.job();verify=job.policy.verify
        def mutate(manifest,value):
            result=verify(manifest,value);receipt['payload']['nonce']='f'*32;return result
        with patch.object(job.policy,'verify',side_effect=mutate),patch.object(service,'ServicePermit',side_effect=AppError('test_stop_before_dispatch','test')):
            with self.assertRaises(AppError):job.run(receipt,runtime=self.f.runtime())
        with sqlite3.connect(job.policy.database) as db:
            row=db.execute('SELECT receipt_json,receipt_sha256,consumed_at FROM approval_transcripts WHERE operation_id=?',(job.identifier,)).fetchone()
            consumed=db.execute('SELECT nonce FROM consumed WHERE operation_id=?',(job.identifier,)).fetchone()
        self.assertEqual(row[0].encode(),original);self.assertEqual(row[1],digest(parse_json(original)))
        self.assertEqual(consumed[0],parse_json(original)['payload']['nonce']);self.assertNotEqual(receipt['payload']['nonce'],consumed[0]);self.assertEqual(self.f.fixture.calls,[])
    def test_transcript_recording_failure_rolls_back_consumption_before_dispatch(self):
        job=self.f.job()
        with sqlite3.connect(job.policy.database) as db:db.execute("CREATE TRIGGER reject_transcript BEFORE INSERT ON approval_transcripts BEGIN SELECT RAISE(ABORT,'injected'); END")
        with patch.object(service,'ServicePermit') as permit:
            with self.assertRaises((AppError,sqlite3.Error)):job.run(self.f.receipt(),runtime=self.f.runtime())
            permit.assert_not_called()
        with sqlite3.connect(job.policy.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM approval_transcripts').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT status,dispatches FROM jobs').fetchone(),('prepared',0))
        self.assertEqual(self.f.fixture.calls,[])
