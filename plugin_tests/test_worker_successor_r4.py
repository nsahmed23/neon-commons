"""Real signature/SQLite/cancel APIs over explicitly modeled transfer records.

The separate native recovery journey qualifies sealed observation and actual
transfer execution. These tests do not label seeded SQL as a native dispatch.
"""
import base64
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import unittest
from unittest.mock import patch
import uuid

from intune_iac import worker_service as service, worker_successor as successor
from intune_iac.io import AppError, canonical, digest, write_json
from plugin_tests import test_worker_service_r4 as services


class WorkerSuccessorR4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        services.WorkerServiceR4Tests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        services.WorkerServiceR4Tests.tearDownClass()

    def setUp(self):
        self.fixture = services.WorkerServiceR4Tests('test_cancel_before_dispatch_and_restart_cannot_start')
        with patch.dict(os.environ):
            os.environ.pop('INTUNE_WORKER_SERVICE_TEST_EVIDENCE', None)
            self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.fixture.prepare()
        self.old = self.fixture.job()
        self.outcome = {'operation_outcome': 'outcome_unknown', 'primary_error': 'modeled_partial_failure',
                        'host': {'cleanup': {'removed': True, 'stopped_state': {'Running': False}}}}
        with self.old.policy.connection() as db:
            db.execute("UPDATE jobs SET status='outcome_unknown',dispatches=1,outcome=? WHERE id=?",
                       (canonical(self.outcome).decode(), self.old.identifier))
            db.execute('INSERT INTO consumed VALUES (?,?,?,?)',
                       ('modeled-fixture', uuid.uuid4().hex, self.old.identifier, self.old.sha256))
        write_json(self.root / 'LABORATORY-STATE.json', {'native_dispatch_performed': False,
                   'scope': 'modeled stopped/consumed transaction rows for signature and cancellation assertions'})
        retained = os.environ.get('INTUNE_SUCCESSOR_TEST_EVIDENCE')
        if retained:
            def preserve():
                shutil.copytree(self.root, Path(retained) / self._testMethodName,
                                ignore=lambda root, names: [name for name in names if (Path(root) / name).is_socket()])
            self.addCleanup(preserve)

    def _signature(self, transfer, *, domain=successor.SIGNATURE_DOMAIN, **changes):
        payload = {'schema_version': 'signed-worker-service-successor/1', 'issuer': 'fixture', 'key_id': 'key',
                   'approver_id': 'independent-lab-reviewer', 'transfer_id': transfer['transfer_id'],
                   'transfer_manifest_sha256': digest(transfer), 'issued_at': int(time.time()),
                   'expires_at': transfer['expires_at'], 'nonce': uuid.uuid4().hex}
        payload.update(changes)
        label = uuid.uuid4().hex
        message, signature = self.root / (label + '.message'), self.root / (label + '.signature')
        message.write_bytes(domain + canonical(payload))
        subprocess.run(['/usr/bin/openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(self.fixture.key),
                        '-in', str(message), '-out', str(signature)], check=True, capture_output=True)
        return {'payload': payload, 'signature': base64.b64encode(signature.read_bytes()).decode()}

    def test_real_signature_domain_expiry_revocation_and_binding(self):
        transfer = {'transfer_id': str(uuid.uuid4()), 'prepared_at': int(time.time()), 'expires_at': int(time.time()) + 60}
        signed = self._signature(transfer)
        self.assertEqual(successor._verify(transfer, signed, self.old.policy, self.old.manifest), signed['payload'])
        for rejected in (self._signature(transfer, domain=service.SIGNATURE_DOMAIN),
                         self._signature(transfer, expires_at=int(time.time()) - 1),
                         self._signature(transfer, transfer_manifest_sha256='0' * 64)):
            with self.assertRaises(AppError): successor._verify(transfer, rejected, self.old.policy, self.old.manifest)
        with self.old.policy.connection() as db: db.execute('INSERT INTO revoked VALUES (?,?)', ('fixture', 'key'))
        with self.assertRaises(AppError): successor._verify(transfer, signed, self.old.policy, self.old.manifest)

    def test_terminal_owner_and_cleanup_guards_use_current_sql(self):
        with self.old.policy.connection() as db:
            facts = successor._original(self.old, db)
            self.assertEqual(facts['outcome_sha256'], digest(self.outcome))
            db.execute('UPDATE jobs SET controller_pid=? WHERE id=?', (os.getpid(), self.old.identifier))
            with self.assertRaises(AppError): successor._original(self.old, db)
            db.execute('UPDATE jobs SET controller_pid=NULL WHERE id=?', (self.old.identifier,))
            changed = copy.deepcopy(self.outcome); changed['host']['cleanup']['removed'] = False
            db.execute('UPDATE jobs SET outcome=? WHERE id=?', (canonical(changed).decode(), self.old.identifier))
            with self.assertRaises(AppError): successor._original(self.old, db)

    def _modeled_successor(self):
        manifest = copy.deepcopy(self.old.manifest)
        manifest['operation_id'] = str(uuid.uuid4()); manifest['broker_policy']['operation_id'] = manifest['operation_id']
        policy = copy.deepcopy(self.fixture.policy); policy['admitted_manifest_sha256'].append(digest(manifest))
        policy_path = self.root / 'trust/current-policy.json'; write_json(policy_path, policy)
        old_binding = (self.old.root / 'policy-binding.json').read_bytes()
        original = service.ServiceJob(self.old.root, policy_path)
        self.assertFalse(original.status()['policy_matches_reviewed'])
        self.assertEqual((self.old.root / 'policy-binding.json').read_bytes(), old_binding)
        root = self.root / 'jobs/modeled-successor'; root.mkdir(mode=0o700)
        write_json(root / 'manifest.json', manifest)
        write_json(root / 'policy-binding.json', {'policy_sha256': original.policy.sha256})
        with original.policy.connection() as db:
            original_facts = successor._original(original, db)
            transfer = {'transfer_id': str(uuid.uuid4()), 'authority': {'authority_root': str(original.policy.root)},
                        'original': original_facts,
                        'successor': {'operation_id': manifest['operation_id'], 'manifest_sha256': digest(manifest)}}
            db.execute('CREATE TABLE successor_transfers (original_operation TEXT,successor_operation TEXT UNIQUE,'
                       'transfer_id TEXT PRIMARY KEY,issuer TEXT,nonce TEXT,transfer_sha256 TEXT,'
                       'recovery_completion_sha256 TEXT,status TEXT,UNIQUE(issuer,nonce))')
            db.execute("CREATE UNIQUE INDEX successor_active_original ON successor_transfers(original_operation) WHERE status='active'")
            db.execute('INSERT INTO successor_transfers VALUES (?,?,?,?,?,?,?,?)',
                       (original.identifier, manifest['operation_id'], transfer['transfer_id'], 'modeled-fixture',
                        uuid.uuid4().hex, digest(transfer), 'e' * 64, 'active'))
            db.execute('INSERT INTO jobs(id,root,manifest_sha256,status) VALUES (?,?,?,?)',
                       (manifest['operation_id'], str(root), digest(manifest), 'prepared'))
            db.execute('UPDATE ownership SET job=? WHERE job=?', (manifest['operation_id'], original.identifier))
        write_json(root / 'successor-transfer.json', transfer)
        return original, service.ServiceJob(root, policy_path), transfer

    def _assert_returned(self, original, new, transfer):
        with original.policy.connection() as db:
            self.assertEqual(db.execute('SELECT status,dispatches,outcome FROM jobs WHERE id=?', (original.identifier,)).fetchone(),
                             ('outcome_unknown', 1, canonical(self.outcome).decode()))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ownership WHERE job=?', (original.identifier,)).fetchone(), (2,))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ownership WHERE job=?', (new.identifier,)).fetchone(), (0,))
            self.assertEqual(db.execute('SELECT status FROM successor_transfers WHERE transfer_id=?',
                                        (transfer['transfer_id'],)).fetchone(), ('returned_without_dispatch',))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM consumed WHERE operation_id=?', (original.identifier,)).fetchone(), (1,))
        self.assertEqual(new.status()['dispatches'], 0)
        self.assertTrue(any(e['kind'] == 'successor_cancelled_ownership_returned' for e in original.attach()['events']))

    def test_actual_cancel_returns_recovery_owner_without_erasing_original(self):
        original, new, transfer = self._modeled_successor()
        new.cancel(); self._assert_returned(original, new, transfer)
        new.cancel(); self._assert_returned(original, new, transfer)

    def test_actual_recover_returns_owner_and_preserves_no_replay(self):
        original, new, transfer = self._modeled_successor()
        new.recover(); self._assert_returned(original, new, transfer)

    def test_changed_transfer_artifact_rolls_back_entire_cancel(self):
        original, new, transfer = self._modeled_successor()
        transfer['original']['outcome_sha256'] = '0' * 64
        write_json(new.root / 'successor-transfer.json', transfer)
        with self.assertRaises(AppError): new.cancel()
        with original.policy.connection() as db:
            self.assertEqual(db.execute('SELECT cancelled,status FROM jobs WHERE id=?', (new.identifier,)).fetchone(), (0, 'prepared'))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ownership WHERE job=?', (new.identifier,)).fetchone(), (2,))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ownership WHERE job=?', (original.identifier,)).fetchone(), (0,))

    def test_dispatched_successor_cannot_return_owner_on_cancel(self):
        original, new, transfer = self._modeled_successor()
        with original.policy.connection() as db: db.execute('UPDATE jobs SET dispatches=1 WHERE id=?', (new.identifier,))
        new.cancel()
        with original.policy.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ownership WHERE job=?', (new.identifier,)).fetchone(), (2,))
            self.assertEqual(db.execute('SELECT status FROM successor_transfers WHERE transfer_id=?',
                                        (transfer['transfer_id'],)).fetchone(), ('active',))
