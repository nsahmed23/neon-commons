"""Expired journal inspection remains read-only and cannot mint lease authority."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from intune_iac.io import AppError,canonical,digest
from intune_iac.worker_recovery import inspect_native_recovery


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.journal=self.root/'journal.sqlite3';self.lease='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        self.policy={'schema_version':'protected-egress-policy/1.0','profile':'laboratory_tls_fixture','operation_id':'a'*32,
            'execution_binding_sha256':'b'*64,'expires_at':int(time.time())-100,'worker_uid':os.geteuid(),
            'identities':{'backend':{'tenant_id':'11111111-1111-4111-8111-111111111111','client_id':'22222222-2222-4222-8222-222222222222'}},
            'routes':[{'id':'acquire','host':'blob.fixture.invalid','method':'PUT','path':'/tfstate/exact.tfstate','query':{'comp':'lease'},
                'headers':{'x-ms-lease-action':'acquire','x-ms-lease-duration':'-1'},'dynamic_headers':{'x-ms-proposed-lease-id':'native_lease_proposal'},
                'body_sha256':hashlib.sha256(b'').hexdigest(),'role':'backend','audience':'storage','effect':'lease','max_attempts':1}]}
        with sqlite3.connect(self.journal) as db:
            db.execute('CREATE TABLE binding(digest TEXT)');db.execute('INSERT INTO binding VALUES (?)',(digest(self.policy),))
            db.execute('CREATE TABLE attempts(sequence INTEGER,route TEXT,request_sha256 TEXT,status TEXT,response_code INTEGER,response_sha256 TEXT)')
            db.execute('INSERT INTO attempts VALUES (1,?,?,?,?,?)',('acquire','c'*64,'dispatch_started',None,None))
            db.execute('CREATE TABLE native_lease_requests(sequence INTEGER,host TEXT,path TEXT,action TEXT,lease_id TEXT,lock_metadata TEXT)')
            db.execute('INSERT INTO native_lease_requests VALUES (1,?,?,?,?,NULL)',('blob.fixture.invalid','/tfstate/exact.tfstate','acquire',self.lease))
        self.journal.chmod(0o600)

    def test_expired_dispatch_is_inspected_without_lease_release_or_journal_change(self):
        before=self.journal.read_bytes();result=inspect_native_recovery(self.journal,policy=self.policy)
        self.assertTrue(result['expired']);self.assertTrue(result['journal_unchanged'])
        self.assertEqual(result['entries'][0]['lease_id'],self.lease)
        self.assertEqual(result['write_attempts'][0]['status'],'dispatch_started')
        self.assertFalse(result['automatic_release_authorized']);self.assertFalse(result['remote_lease_observed'])
        self.assertEqual(before,self.journal.read_bytes())

    def test_cli_writes_private_exclusive_receipt_and_only_sanitized_summary(self):
        policy=self.root/'policy.json';policy.write_bytes(canonical(self.policy));policy.chmod(0o600)
        output=self.root/'report.json';command=[sys.executable,'-B','-m','intune_iac.worker_recovery','inspect','--journal',str(self.journal),
            '--policy',str(policy),'--output',str(output)]
        result=subprocess.run(command,capture_output=True);self.assertEqual(result.returncode,0,result.stdout)
        self.assertNotIn(self.lease.encode(),result.stdout);self.assertEqual(output.stat().st_mode&0o777,0o600)
        first=output.read_bytes();again=subprocess.run(command,capture_output=True)
        self.assertEqual(again.returncode,1);self.assertEqual(output.read_bytes(),first)

    def test_policy_swap_fails_without_modifying_journal(self):
        changed=copy.deepcopy(self.policy);changed['execution_binding_sha256']='d'*64;before=self.journal.read_bytes()
        with self.assertRaises(AppError) as raised:inspect_native_recovery(self.journal,policy=changed)
        self.assertEqual(raised.exception.code,'recovery_policy_mismatch');self.assertEqual(before,self.journal.read_bytes())

    def test_hot_journal_is_preserved_instead_of_implicitly_recovered(self):
        sidecar=Path(str(self.journal)+'-journal');sidecar.write_bytes(b'preserved-interrupted-sidecar')
        with self.assertRaises(AppError) as raised:inspect_native_recovery(self.journal,policy=self.policy)
        self.assertEqual(raised.exception.code,'recovery_journal_not_quiescent');self.assertEqual(sidecar.read_bytes(),b'preserved-interrupted-sidecar')

    def test_foreign_recorded_lease_target_cannot_be_treated_as_bound_recovery(self):
        with sqlite3.connect(self.journal) as db:db.execute("UPDATE native_lease_requests SET path='/tfstate/foreign.tfstate'")
        with self.assertRaises(AppError) as raised:inspect_native_recovery(self.journal,policy=self.policy)
        self.assertEqual(raised.exception.code,'recovery_journal_route_mismatch')
