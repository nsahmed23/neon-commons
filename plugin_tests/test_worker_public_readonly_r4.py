"""Real public readers/SQLite locks; constructed journals, no worker dispatch.

Policies use real validated Ed25519 keys. Durable rows are explicit local test
fixtures, not authenticated native execution or provider/service evidence.
"""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from intune_iac import worker_service as service, worker_adoption as adoption
from intune_iac.io import AppError, digest, write_json
from plugin_tests.signing_fixture import verifier_pin


class PublicReadonlyTests(unittest.TestCase):
    def setUp(self):
        retain = os.environ.get('INTUNE_PUBLIC_READONLY_EVIDENCE')
        if retain:
            self.root = Path(retain) / self._testMethodName
            self.root.mkdir(parents=True, mode=0o700)
        else:
            tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
            self.root = Path(tmp.name)
        for name in ('trust', 'jobs'): (self.root / name).mkdir(mode=0o700)
        key = self.root / 'trust/key.pem'
        subprocess.run(['/usr/bin/openssl', 'genpkey', '-algorithm', 'ED25519', '-out', str(key)], check=True, capture_output=True)
        public = subprocess.check_output(['/usr/bin/openssl', 'pkey', '-in', str(key), '-pubout', '-outform', 'DER'])[-32:]
        pin = verifier_pin(Path('/usr/bin/openssl'), hashlib.sha256(Path('/usr/bin/openssl').read_bytes()).hexdigest())
        self.policy_path = self.root / 'trust/policy.json'
        self.policy_value = {'schema_version':'worker-service-policy/1', 'authority_root':str(self.root / 'trust/authority'),
            'jobs_root':str(self.root / 'jobs'), 'verifier':{k:str(v) if isinstance(v,Path) else v for k,v in asdict(pin).items()},
            'approvers':[{'issuer':'fixture','key_id':'key','approver_id':'reader-test','public_key_hex':public.hex(),
                'profiles':['native_docker_laboratory_protocol']}], 'admitted_manifest_sha256':['0'*64]}
        write_json(self.policy_path, self.policy_value)
        self.policy = service.ServicePolicy(self.policy_path)
        adoption._tables(self.policy)
        self.paths = {}
        for name, version in [('service',service.VERSION),('adoption',adoption.VERSION)]:
            root = self.root / 'jobs' / name; root.mkdir(mode=0o700)
            manifest = {'schema_version':version, 'operation_id':str(uuid.uuid4()), 'profile':'native_docker_laboratory_protocol',
                'tenant_id':'11111111-1111-4111-8111-111111111111', 'object_ids':['22222222-2222-4222-8222-222222222222'],
                'saved_plan_sha256':None, 'expires_at':int(time.time())+90, 'verification_operation_id':str(uuid.uuid4())}
            write_json(root / 'manifest.json', manifest); write_json(root / 'policy-binding.json', {'policy_sha256':self.policy.sha256})
            with self.policy.connection() as db:
                db.execute('INSERT INTO jobs(id,root,manifest_sha256,status) VALUES (?,?,?,?)',
                    (manifest['operation_id'],str(root),digest(manifest),'prepared'))
                if name == 'adoption': db.execute('INSERT INTO adoption_operations(operation_id,manifest_sha256,verification_id) VALUES (?,?,?)',
                    (manifest['operation_id'],digest(manifest),manifest['verification_operation_id']))
            self.paths[name] = root

    def inventory(self):
        return {str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.root.rglob('*') if p.is_file()}

    def held_writer_reads(self, name, *, cli=False):
        before = self.inventory()
        writer = sqlite3.connect(self.policy.database, timeout=0, isolation_level=None)
        try:
            writer.execute('BEGIN IMMEDIATE')
            writer.execute('UPDATE jobs SET cancelled=1')  # readers must see the committed zero, not this pending write.
            for action in ('status','attach'):
                if cli:
                    run = subprocess.run([sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'scripts/intune-iac.py'),
                        name,action,'--job-root',str(self.paths[name]),'--policy',str(self.policy_path)],
                        capture_output=True, timeout=15)
                    (self.root / (name+'-'+action+'.stdout')).write_bytes(run.stdout)
                    (self.root / (name+'-'+action+'.stderr')).write_bytes(run.stderr)
                    self.assertEqual(run.returncode,0,run.stderr.decode())
                    result=json.loads(run.stdout)
                else:
                    kind=service.ServiceJob if name=='service' else adoption.AdoptionJob
                    result=getattr(kind(self.paths[name],self.policy_path),action)()
                self.assertEqual(result['status'],'prepared'); self.assertEqual(result['dispatches'],0)
                self.assertFalse(result['cancel_requested'])
        finally:
            writer.execute('ROLLBACK'); writer.close()
        after=self.inventory()
        for relative,value in before.items():self.assertEqual(after[relative],value,relative)
        self.assertEqual(set(after)-set(before), {name+'-'+a+s for a in ('status','attach') for s in ('.stdout','.stderr')} if cli else set())

    def test_service_public_status_attach_under_reserved_writer(self): self.held_writer_reads('service')
    def test_adoption_public_status_attach_under_reserved_writer(self): self.held_writer_reads('adoption')
    def test_service_actual_cli_status_attach_under_reserved_writer(self): self.held_writer_reads('service',cli=True)
    def test_adoption_actual_cli_status_attach_under_reserved_writer(self): self.held_writer_reads('adoption',cli=True)

    def test_readonly_connection_is_query_only_uri_mode_ro(self):
        calls=[]; connect=sqlite3.connect
        def trace(*args,**kwargs):
            db=connect(*args,**kwargs); statements=[];db.set_trace_callback(statements.append)
            calls.append((args,kwargs,statements));return db
        before=self.inventory()
        with patch.object(service.sqlite3,'connect',side_effect=trace):service.ServicePolicy(self.policy_path,initialize=False)
        self.assertEqual(len(calls),1)
        args,kwargs,statements=calls[0]
        self.assertTrue(args[0].endswith('?mode=ro'));self.assertIs(kwargs['uri'],True);self.assertEqual(kwargs['timeout'],0)
        self.assertIn('PRAGMA query_only=ON',statements)
        self.assertFalse(any(s.startswith(('CREATE','ALTER','INSERT','UPDATE','DELETE','BEGIN IMMEDIATE')) for s in statements))
        self.assertEqual(before,self.inventory())

    def test_missing_authority_is_not_created(self):
        shutil.rmtree(self.policy.root);before=self.inventory()
        with self.assertRaises(AppError) as e:service.ServicePolicy(self.policy_path,initialize=False)
        self.assertEqual(e.exception.code,'service_store_missing');self.assertEqual(before,self.inventory())
        self.assertFalse(self.policy.root.exists())

    def test_missing_database_is_not_created(self):
        self.policy.database.unlink();before=self.inventory()
        with self.assertRaises(AppError) as e:service.ServicePolicy(self.policy_path,initialize=False)
        self.assertEqual(e.exception.code,'service_store_missing');self.assertEqual(before,self.inventory())

    def test_incomplete_schema_is_not_upgraded(self):
        with self.policy.connection() as db:db.execute('DROP TABLE approval_transcripts')
        before=self.inventory()
        with self.assertRaises(AppError) as e:service.ServicePolicy(self.policy_path,initialize=False)
        self.assertEqual(e.exception.code,'service_store_schema_required');self.assertEqual(before,self.inventory())
        # Explicit preparation remains the owner of initialization/migration.
        initialized=service.ServicePolicy(self.policy_path)
        with initialized.connection() as db:self.assertEqual(db.execute("SELECT type FROM sqlite_master WHERE name='approval_transcripts'").fetchone(),('table',))

    def test_missing_controller_columns_fail_readonly_then_explicit_migration(self):
        with self.policy.connection() as db:
            db.execute('ALTER TABLE jobs DROP COLUMN controller_start');db.execute('ALTER TABLE jobs DROP COLUMN controller_pid')
        before=self.inventory()
        with self.assertRaises(AppError) as e:service.ServicePolicy(self.policy_path,initialize=False)
        self.assertEqual(e.exception.code,'service_store_schema_required');self.assertEqual(before,self.inventory())
        service.ServicePolicy(self.policy_path)
        service.ServicePolicy(self.policy_path,initialize=False)

    def test_view_cannot_substitute_for_authority_table(self):
        with self.policy.connection() as db:
            db.execute('ALTER TABLE revoked RENAME TO previous_revoked')
            db.execute('CREATE VIEW revoked AS SELECT issuer,key_id FROM previous_revoked')
        before=self.inventory()
        with self.assertRaises(AppError) as e:service.ServicePolicy(self.policy_path,initialize=False)
        self.assertEqual(e.exception.code,'service_store_schema_required');self.assertEqual(before,self.inventory())

    def test_missing_unique_constraint_rejects(self):
        with self.policy.connection() as db:
            db.execute('DROP TABLE consumed');db.execute('CREATE TABLE consumed (issuer TEXT,nonce TEXT,operation_id TEXT,manifest_sha256 TEXT,PRIMARY KEY(issuer,nonce))')
        before=self.inventory()
        with self.assertRaises(AppError) as e:service.ServicePolicy(self.policy_path,initialize=False)
        self.assertEqual(e.exception.code,'service_store_schema_required');self.assertEqual(before,self.inventory())

    def test_private_policy_key_and_database_checks_remain_required(self):
        for change in ('key','mode'):
            with self.subTest(change=change):
                before=self.policy_path.read_bytes()
                if change=='key':
                    bad=json.loads(before);bad['verifier']['sha256']='0'*64;write_json(self.policy_path,bad)
                else:self.policy.database.chmod(0o644)
                with self.assertRaises(AppError):service.ServicePolicy(self.policy_path,initialize=False)
                self.policy_path.write_bytes(before);self.policy.database.chmod(0o600)

    def test_initialize_flag_does_not_coerce_integers_or_strings(self):
        before=self.inventory()
        for value in (0,1,None,'false'):
            with self.assertRaises(AppError) as e:service.ServicePolicy(self.policy_path,initialize=value)
            self.assertEqual(e.exception.code,'service_initialization_mode_invalid')
        self.assertEqual(before,self.inventory())

    def _close_fault(self, *, readonly, secondary, interrupt=False):
        real_connect=sqlite3.connect
        class CloseFault(sqlite3.Connection):
            def close(self):
                super().close()
                raise secondary
        def connect(*args,**kwargs):return real_connect(*args,**kwargs,factory=CloseFault)
        with patch.object(service.sqlite3,'connect',side_effect=connect):
            if readonly:service.ServicePolicy(self.policy_path,initialize=False)
            else:
                with self.policy.connection() as db:
                    if interrupt:raise KeyboardInterrupt('fixture primary cancellation')
                    db.execute('SELECT no_such_field FROM jobs')

    def test_readonly_primary_schema_failure_survives_close_error(self):
        with self.policy.connection() as db:db.execute('DROP TABLE revoked')
        before=self.inventory()
        with self.assertRaises(AppError) as e:self._close_fault(readonly=True,secondary=OSError('fixture close'))
        self.assertEqual(e.exception.code,'service_store_schema_required')
        self.assertTrue(any('OSError' in note for note in e.exception.__notes__))
        self.assertEqual(before,self.inventory())

    def test_shared_connection_primary_sql_failure_survives_close_error(self):
        before=self.inventory()
        with self.assertRaises(AppError) as e:self._close_fault(readonly=False,secondary=OSError('fixture close'))
        self.assertEqual(e.exception.code,'service_store_unavailable')
        self.assertTrue(any('OSError' in note for note in e.exception.__notes__))
        self.assertEqual(before,self.inventory())

    def test_shared_connection_primary_interrupt_survives_close_error(self):
        before=self.inventory()
        with self.assertRaises(KeyboardInterrupt) as e:self._close_fault(readonly=False,secondary=OSError('fixture close'),interrupt=True)
        self.assertEqual(str(e.exception),'fixture primary cancellation')
        self.assertTrue(any('OSError' in note for note in e.exception.__notes__))
        self.assertEqual(before,self.inventory())

    def test_shared_connection_secondary_interrupt_retains_sql_primary(self):
        before=self.inventory()
        with self.assertRaises(KeyboardInterrupt) as e:self._close_fault(readonly=False,secondary=KeyboardInterrupt('fixture secondary'))
        self.assertIsInstance(e.exception.__cause__,AppError)
        self.assertEqual(e.exception.__cause__.code,'service_store_unavailable')
        self.assertEqual(before,self.inventory())

    def test_conflict_policy_is_not_hidden_by_matching_pragma_shape(self):
        with self.policy.connection() as db:
            db.execute('DROP TABLE consumed')
            db.execute('CREATE TABLE consumed (issuer TEXT, nonce TEXT, operation_id TEXT UNIQUE, manifest_sha256 TEXT, PRIMARY KEY(issuer,nonce) ON CONFLICT REPLACE)')
        before=self.inventory()
        with self.assertRaises(AppError) as e:service.ServicePolicy(self.policy_path,initialize=False)
        self.assertEqual(e.exception.code,'service_store_schema_required');self.assertEqual(before,self.inventory())


if __name__=='__main__':unittest.main()
