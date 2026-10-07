"""Inactive adapter contracts: real Linux SQLite with recorded Win32 effects."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote
from unittest.mock import patch

from intune_iac.io import AppError
from intune_iac import windows_workbench as subject
from intune_iac.workbench_schema import _SCHEMA_SQL_V1
from intune_iac.workbench_store import WorkbenchStore
from plugin_tests.test_windows_storage_r4 import RecordedStorage,VOLUME,ROOT,CANONICAL

TENANT='11111111-1111-4111-8111-111111111111'


class FilesystemAPI(RecordedStorage):
    def __init__(self,base):
        super().__init__();self.base=base;self.flush_count=0;self.fail_at_flush=None;self.fail_creation=None
        for name in self.directories:self.real(name).mkdir(parents=True,exist_ok=True)
    def real(self,path):
        assert path.startswith(VOLUME),path
        return self.base.joinpath(*path[len(VOLUME):].split('\\'))
    def create_directory(self,path,sid):
        super().create_directory(path,sid);self.real(path).mkdir()
    def _sync(self,path):
        real=self.real(path)
        if real.is_file():self.files[path]={'data':real.read_bytes(),'id':real.stat().st_ino}
        else:self.files.pop(path,None)
    def open_file(self,path,sid,*,create=False,lock=False):
        if create:
            if self.fail_creation and self.fail_creation in path:raise AppError('fixture_disk_full','fixture')
            if self.real(path).exists():raise AppError('windows_storage_destination_exists','fixture')
            self.real(path).write_bytes(b'')
        self._sync(path)
        return super().open_file(path,sid,create=False,lock=lock)
    def open_read_guard(self,path,*,optional=False):
        self._sync(path)
        if path not in self.files:
            if optional:return None
            raise AppError('windows_sqlite_read_guard_failed','fixture')
        return self._open(path,'file')
    def file_metadata(self,handle,sid):
        self._sync(self.handles[handle][1]);return super().file_metadata(handle,sid)
    def write(self,handle,data):
        super().write(handle,data);self.real(self.handles[handle][1]).write_bytes(data)
    def read(self,handle):return self.real(self.handles[handle][1]).read_bytes()
    def flush_namespace(self,handle):
        self.flush_count+=1
        if self.flush_count==self.fail_at_flush:raise AppError('windows_storage_namespace_flush_unavailable','fixture')
        super().flush_namespace(handle)
    def rename_new(self,handle,root_handle,name):
        original=self.real(self.handles[handle][1]);destination=self.real(self.handles[root_handle][1])/name
        if destination.exists():raise AppError('windows_storage_destination_exists','fixture')
        super().rename_new(handle,root_handle,name);original.rename(destination)
    def names(self,path):return [p.name for p in self.real(path).iterdir()]
    def connect(self,database,**kwargs):
        path,query=database[5:].split('?',1);real=self.real(unquote(path))
        return sqlite3.connect(real.as_uri()+'?'+query,**kwargs)


class WindowsWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.api=FilesystemAPI(self.base/'files')
        self.fs=subject._Filesystem(self.api,self.api.connect);self.root=ROOT+'\\store'
        self.store=subject.WindowsWorkbenchStore._create(self.root,TENANT,self.fs)
        self.database=self.api.real(CANONICAL+'\\store\\observations.sqlite3')
    def reopen(self):return subject.WindowsWorkbenchStore._open(self.root,TENANT,self.fs)
    def direct(self,sql):
        with sqlite3.connect(self.database) as db:return db.execute(sql).fetchall()

    def test_real_sqlite_create_record_reopen_query_and_persist_journal(self):
        result=self.store.record_operation('observed-only',{'object_id':'22222222-2222-4222-8222-222222222222','phase':'review'})
        self.assertEqual(result,{'sequence':1,'operation_id':'observed-only'})
        self.assertEqual(self.direct('SELECT operation_id FROM operations'),[('observed-only',)])
        reopened=self.reopen();self.assertEqual(reopened.operations()[0]['phase'],'review')
        journal=Path(str(self.database)+'-journal');self.assertTrue(journal.exists());self.assertFalse(any(journal.read_bytes()[:28]))
        status=reopened.storage_status();self.assertEqual(len(status['outcomes']),1);self.assertEqual(status['unresolved_intents'],[])
        self.assertFalse(status['workbench_profile_enabled']);self.assertEqual(self.api.handles,{})

    def test_wrong_tenant_rejected_without_mutating_database(self):
        before=self.database.read_bytes()
        with self.assertRaises(AppError) as caught:subject.WindowsWorkbenchStore._open(self.root,'33333333-3333-4333-8333-333333333333',self.fs)
        self.assertEqual(caught.exception.code,'workbench_wrong_tenant');self.assertEqual(self.database.read_bytes(),before)

    def test_native_model_and_unported_capture_routes_are_explicitly_unsupported(self):
        for call,code in [(lambda:self.store.collect(object()),'windows_workbench_model_collection_unsupported'),
            (lambda:self.store.import_capture('not-opened'),'windows_workbench_capture_reader_unsupported'),
            (lambda:self.store.raw_capture_observation('not-opened'),'windows_workbench_capture_reader_unsupported')]:
            with self.assertRaises(AppError) as caught:call()
            self.assertEqual(caught.exception.code,code)

    def test_transaction_failure_preserves_atomic_rollback_and_unresolved_intent(self):
        with self.assertRaises(RuntimeError):
            with self.store._connection(True) as db,db:
                db.execute("INSERT INTO operations VALUES(1,'partial',NULL,'{}',1)")
                raise RuntimeError('deliberate interruption')
        self.assertEqual(self.direct('SELECT * FROM operations'),[])
        self.assertEqual(len(self.reopen().storage_status()['unresolved_intents']),1)
        self.assertEqual(self.api.handles,{})

    def test_committed_bytes_with_failed_namespace_flush_are_uncertain_not_success(self):
        self.api.fail_at_flush=self.api.flush_count+2
        with self.assertRaises(AppError) as caught:self.store.record_operation('possible-commit',{'phase':'record'})
        self.assertEqual(caught.exception.code,'windows_storage_namespace_flush_unavailable')
        self.assertTrue(caught.exception.storage_outcome['outcome_uncertain'])
        self.assertEqual(self.direct('SELECT operation_id FROM operations'),[('possible-commit',)])
        status=self.reopen().storage_status();self.assertEqual(len(status['unresolved_intents']),1);self.assertEqual(status['outcomes'],[])

    def test_failed_outcome_record_preserves_successful_commit_and_intent(self):
        self.api.fail_creation='store-outcome-'
        with self.assertRaises(AppError) as caught:self.store.record_operation('commit-retained',{'phase':'record'})
        self.assertEqual(caught.exception.code,'fixture_disk_full');self.assertTrue(caught.exception.storage_outcome['outcome_uncertain'])
        self.assertEqual(self.direct('SELECT operation_id FROM operations'),[('commit-retained',)])
        self.assertEqual(len(self.reopen().storage_status()['unresolved_intents']),1)

    def test_missing_intent_durability_prevents_sqlite_mutation(self):
        self.api.fail_at_flush=self.api.flush_count+1
        before=self.database.read_bytes()
        with self.assertRaises(AppError):self.store.record_operation('must-not-execute',{'phase':'record'})
        self.assertEqual(self.database.read_bytes(),before);self.assertEqual(self.direct('SELECT * FROM operations'),[])

    def test_attaches_and_journal_mode_overrides_are_denied_inside_write_session(self):
        with self.store._connection(True) as db,db:
            for sql in ("ATTACH ':memory:' AS extra",'PRAGMA journal_mode=OFF','PRAGMA synchronous=OFF','PRAGMA writable_schema=ON'):
                with self.subTest(sql=sql),self.assertRaises(sqlite3.DatabaseError):db.execute(sql)
            db.execute("INSERT INTO operations VALUES(1,'allowed',NULL,'{}',1)")
        self.assertEqual(self.direct('SELECT operation_id FROM operations'),[('allowed',)])

    def test_backup_restore_exact_pin_tenant_and_no_overwrite(self):
        self.store.record_operation('retained',{'phase':'history'})
        backup=ROOT+'\\backup.sqlite3';receipt=self.store.backup(backup)
        bytes_=self.api.real(CANONICAL+'\\backup.sqlite3').read_bytes()
        self.assertEqual(hashlib.sha256(bytes_).hexdigest(),receipt['sha256'])
        restored=subject.WindowsWorkbenchStore._restore(backup,ROOT+'\\restored',TENANT,receipt['sha256'],self.fs)
        self.assertEqual(restored.operations()[0]['operation_id'],'retained')
        self.assertEqual(restored.schema_version,2)
        for digest,tenant,code in [('0'*64,TENANT,'windows_workbench_backup_pin_mismatch'),
            (receipt['sha256'],'33333333-3333-4333-8333-333333333333','workbench_wrong_tenant')]:
            with self.assertRaises(AppError) as caught:subject.WindowsWorkbenchStore._restore(backup,ROOT+'\\must-not-create',tenant,digest,self.fs)
            self.assertEqual(caught.exception.code,code);self.assertFalse(self.api.real(CANONICAL+'\\must-not-create').exists())
        with self.assertRaises(AppError):self.store.backup(backup)
        self.assertEqual(self.api.real(CANONICAL+'\\backup.sqlite3').read_bytes(),bytes_)
        self.assertTrue(list(self.api.real(CANONICAL).glob('store-backup-*.sqlite3')))

    def test_v1_migration_reuses_exact_schema_and_preserves_v1_backup(self):
        legacy=sqlite3.connect(':memory:');legacy.executescript(_SCHEMA_SQL_V1)
        with legacy:legacy.execute('INSERT INTO metadata VALUES(?,?)',('tenant_id',TENANT))
        data=legacy.serialize();legacy.close();legacy_root=ROOT+'\\legacy';self.fs.create(legacy_root,data)
        store=subject.WindowsWorkbenchStore._open(legacy_root,TENANT,self.fs)
        self.assertEqual(store.schema_version,1);result=store.migrate(ROOT+'\\v1.sqlite3')
        self.assertEqual(result['status'],'migrated');self.assertEqual(store.schema_version,2)
        with sqlite3.connect(self.api.real(CANONICAL+'\\v1.sqlite3')) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
        reopened=subject.WindowsWorkbenchStore._open(legacy_root,TENANT,self.fs);self.assertEqual(reopened.schema_version,2)

    def test_actual_sqlite_writer_contention_preserves_primary_busy_and_no_partial_row(self):
        blocker=sqlite3.connect(self.database);blocker.execute('BEGIN IMMEDIATE')
        original=self.fs.connect
        def quick(database,**kwargs):kwargs['timeout']=0.01;return original(database,**kwargs)
        self.fs.connect=quick
        try:
            with self.assertRaises(sqlite3.OperationalError):self.store.record_operation('contending',{'phase':'record'})
        finally:blocker.rollback();blocker.close();self.fs.connect=original
        self.assertEqual(self.direct('SELECT * FROM operations'),[])
        self.store.record_operation('after-release',{'phase':'record'})
        self.assertEqual(self.direct('SELECT operation_id FROM operations'),[('after-release',)])

    def test_public_native_constructor_rejects_linux_before_creating_store(self):
        if sys.platform=='win32':return
        with self.assertRaises(AppError) as caught:subject.WindowsWorkbenchStore.create(ROOT+'\\must-not-exist',TENANT)
        self.assertEqual(caught.exception.code,'windows_directory_platform_unsupported')

    def test_actual_owned_process_interruption_recovers_only_into_new_pinned_copy(self):
        child_code="""import os,sqlite3,sys
db=sqlite3.connect(sys.argv[1]);db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA cache_size=1');db.execute('BEGIN IMMEDIATE')
for number in range(100): db.execute('INSERT INTO operations(operation_id,data_json,recorded_at) VALUES(?,?,?)',('uncommitted-'+str(number),'x'*4000,1))
os._exit(23)
"""
        child=subprocess.run([sys.executable,'-B','-c',child_code,str(self.database)],capture_output=True,timeout=10)
        self.assertEqual(child.returncode,23,child.stderr)
        database_bytes=self.database.read_bytes();journal=Path(str(self.database)+'-journal');journal_bytes=journal.read_bytes()
        self.assertTrue(any(journal_bytes[:28]));database_sha=hashlib.sha256(database_bytes).hexdigest();journal_sha=hashlib.sha256(journal_bytes).hexdigest()
        with self.assertRaises(AppError) as caught:self.reopen()
        self.assertEqual(caught.exception.code,'windows_workbench_recovery_required')
        with self.assertRaises(AppError) as caught:
            subject.WindowsWorkbenchStore._recover(self.root,ROOT+'\\wrong-pin',TENANT,'0'*64,journal_sha,self.fs)
        self.assertEqual(caught.exception.code,'windows_workbench_recovery_pin_mismatch')
        self.assertFalse(self.api.real(CANONICAL+'\\wrong-pin').exists())
        recovered=subject.WindowsWorkbenchStore._recover(self.root,ROOT+'\\recovered',TENANT,database_sha,journal_sha,self.fs)
        self.assertEqual(recovered.operations(),[])
        recovered.record_operation('after-recovery',{'phase':'recovered'})
        self.assertEqual(recovered.operations()[0]['operation_id'],'after-recovery')
        self.assertEqual(self.database.read_bytes(),database_bytes);self.assertEqual(journal.read_bytes(),journal_bytes)
        self.assertTrue(recovered.recovery_receipt['original_preserved'])
        self.assertTrue(self.api.real(CANONICAL+'\\recovered\\recovery-input.json').is_file())
        self.assertTrue(self.api.real(CANONICAL+'\\recovered\\recovery-outcome.json').is_file())

    def test_existing_history_health_and_relationship_queries_reuse_same_engine(self):
        from intune_iac.synthetic import generate_estate
        from intune_iac.modeled_service import ModeledService
        estate=generate_estate(seed=104,policy_count=3);ids=[value['id'] for value in estate['truth']['policies']]
        tenant=estate['truth']['tenant_id'];original_root=self.base/'original-linux-store'
        original=WorkbenchStore.create(original_root,tenant)
        service=ModeledService.create(self.base/'model',estate['capture'],ids)
        original.collect(service,observed_at=100,deployment={'targeted':100,'reporting':8,'successful':8})
        image=original.path.read_bytes();copied_root=ROOT+'\\history';self.fs.create(copied_root,image)
        copied=subject.WindowsWorkbenchStore._open(copied_root,tenant,self.fs)
        for policy in estate['truth']['policies']:
            expected={key:value for key,value in policy.items() if key!='id'}
            self.assertEqual(copied.inspect(policy['id'])['body'],expected)
            self.assertEqual(len(copied.history(policy['id'])),1)
            self.assertEqual(copied.history(policy['id'])[0]['object_id'],policy['id'])
        overview=copied.overview(now=120)
        self.assertEqual(len(overview['objects']),3)
        self.assertEqual(overview['health']['targeted_success_percent'],8)
        self.assertEqual(overview['health']['unknown_or_stale'],92)
        self.assertIn('exclusion',{edge['relation'] for edge in copied.inspect(ids[0])['relationships']})


class PortableSchemaTests(unittest.TestCase):
    def test_public_base_restore_rejects_unsupported_host_before_private_path_dispatch(self):
        from intune_iac import workbench_store as module
        with (patch.object(module,'require_profile',side_effect=AppError('host_profile_unsupported','fixture')) as guard,
                patch.object(module,'_private') as filesystem):
            with self.assertRaises(AppError) as caught:module.WorkbenchStore.restore('not-opened','not-created',TENANT)
            self.assertEqual(caught.exception.code,'host_profile_unsupported')
            guard.assert_called_once_with('workbench_store');filesystem.assert_not_called()

    def test_no_fcntl_import_before_posix_store_dispatch(self):
        code="""import importlib.abc,sys
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if name=='fcntl':raise ImportError('deliberately unavailable')
sys.meta_path.insert(0,Deny())
from intune_iac import workbench_schema,workbench_store,windows_workbench
assert 'fcntl' not in sys.modules
from intune_iac.io import AppError
try:workbench_store.WorkbenchStore('MUST_NOT_OPEN')
except AppError as error:assert error.code=='host_profile_unsupported'
else:raise AssertionError('unsupported dispatch admitted')
print('portable-import-and-denial')
"""
        child=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,timeout=10)
        self.assertEqual(child.returncode,0,child.stderr);self.assertIn(b'portable-import-and-denial',child.stdout)

    def test_schema_and_field_reexports_remain_identical(self):
        from intune_iac import workbench_store as store,workbench_schema as schema,modeled_service as model,observation_contract as fields
        self.assertIs(store._SCHEMA_SQL,schema._SCHEMA_SQL)
        self.assertIs(store._expected_schema,schema._expected_schema)
        self.assertIs(store.FIELDS,fields.FIELDS);self.assertIs(model.FIELDS,fields.FIELDS)
        self.assertEqual(fields.BASE,'https://intune-model.invalid/policies');self.assertEqual(fields.MAX_OBJECTS,8)


class HelperPrimaryFailureTests(unittest.TestCase):
    def test_memory_helpers_preserve_primary_validation_or_cancellation_through_close_failure(self):
        original_connect=sqlite3.connect
        for helper in ('image','validate','create'):
            with self.subTest(helper=helper):
                primary=KeyboardInterrupt('primary cancellation') if helper=='create' else AppError('primary_validation','fixture')
                source=original_connect(':memory:');source.execute('CREATE TABLE fixture(value)')
                payload=source.serialize()
                class BrokenClose(sqlite3.Connection):
                    def execute(self,sql,*args,**kwargs):
                        if helper=='image' and sql=='PRAGMA quick_check':raise primary
                        return super().execute(sql,*args,**kwargs)
                    def deserialize(self,*args,**kwargs):
                        if helper=='validate':raise primary
                        return super().deserialize(*args,**kwargs)
                    def executescript(self,*args,**kwargs):
                        if helper=='create':raise primary
                        return super().executescript(*args,**kwargs)
                    def close(self):
                        super().close();raise RuntimeError('secondary close failure')
                def connect(*args,**kwargs):return original_connect(*args,factory=BrokenClose,**kwargs)
                try:
                    with patch.object(subject.sqlite3,'connect',side_effect=connect):
                        try:
                            if helper=='image':subject._image(source)
                            elif helper=='validate':subject._validate_image(payload,TENANT)
                            else:subject.WindowsWorkbenchStore._create(ROOT,TENANT,object())
                        except BaseException as observed:self.assertIs(observed,primary)
                        else:self.fail('primary failure disappeared')
                finally:source.close()


if __name__=='__main__':unittest.main()
