"""Real local SQLite plus recorded Win32 calls; no native Windows evidence."""
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import windows_sqlite as subject
from intune_iac.io import AppError
from plugin_tests.test_windows_storage_r4 import RecordedStorage, ROOT, CANONICAL


class API(RecordedStorage):
    def open_read_guard(self,path,*,optional=False):
        self.events.append(('read-guard',path,optional))
        if path not in self.files:
            if optional:return None
            raise AppError('windows_sqlite_read_guard_failed','fixture')
        if self.failure=='writer':raise AppError('windows_sqlite_read_guard_failed','fixture')
        return self._open(path,'file')


class WindowsSQLiteContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'source.sqlite3'
        db=sqlite3.connect(self.path)
        db.executescript("CREATE TABLE facts(id INTEGER PRIMARY KEY,value TEXT); INSERT INTO facts VALUES(1,'snow 雪'); PRAGMA user_version=2;")
        db.close();self.bytes=self.path.read_bytes();self.api=API();self.name=CANONICAL+'\\observations.sqlite3'
        self.api.files[self.name]={'data':self.bytes,'id':11};self.calls=[]

    def connect(self,database,**kwargs):
        self.calls.append((database,kwargs))
        return sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',**kwargs)

    def snapshot(self):return subject._snapshot(ROOT,'observations.sqlite3',self.api,self.connect)

    def test_real_sqlite_reads_exact_bytes_and_keeps_runtime_profile_disabled(self):
        with self.snapshot() as view:
            self.assertEqual(view.query('SELECT id,value FROM facts'),[(1,'snow 雪')])
            self.assertEqual(view.query('PRAGMA user_version'),[(2,)])
            receipt=view.receipt();self.assertEqual(receipt['database_sha256'],hashlib.sha256(self.bytes).hexdigest())
            self.assertFalse(receipt['workbench_profile_enabled']);self.assertFalse(receipt['platform_qualified'])
            receipt['database_identity']['bytes']=0;self.assertGreater(view.receipt()['database_identity']['bytes'],0)
        self.assertEqual(self.path.read_bytes(),self.bytes);self.assertEqual(self.api.handles,{})
        self.assertIn('%5C%5C%3F%5CVolume',self.calls[0][0]);self.assertTrue(self.calls[0][0].endswith('?mode=ro&immutable=1'))

    def test_write_pragma_attach_extension_and_mutating_sql_are_denied(self):
        statements=["UPDATE facts SET value='bad'",'DROP TABLE facts','PRAGMA query_only=OFF',
            'PRAGMA writable_schema=ON','PRAGMA user_version=4',"ATTACH ':memory:' AS bad", "SELECT load_extension('bad')",
            'VACUUM',"SELECT randomblob(100)"]
        with self.snapshot() as view:
            for statement in statements:
                with self.subTest(sql=statement),self.assertRaises(AppError) as caught:view.query(statement)
                self.assertEqual(caught.exception.code,'windows_sqlite_query_rejected')
            self.assertEqual(view.query('SELECT value FROM facts'),[('snow 雪',)])
        self.assertEqual(self.path.read_bytes(),self.bytes)

    def test_existing_writer_rejected_before_sqlite_dispatch(self):
        self.api.failure='writer'
        with self.assertRaises(AppError) as caught:
            with self.snapshot():pass
        self.assertEqual(caught.exception.code,'windows_sqlite_read_guard_failed');self.assertEqual(self.calls,[])
        self.assertEqual(self.api.handles,{})

    def test_hot_journal_requires_recovery_without_modifying_any_file(self):
        self.api.files[self.name+'-journal']={'id':12,'data':b'\xd9\xd5\x05\xf9\x20\xa1\x63\xd7'+b'\x00'*504}
        before={key:dict(value) for key,value in self.api.files.items()}
        with self.assertRaises(AppError) as caught:
            with self.snapshot():pass
        self.assertEqual(caught.exception.code,'windows_sqlite_recovery_required')
        self.assertEqual(self.api.files,before);self.assertEqual(self.calls,[]);self.assertEqual(self.api.handles,{})

    def test_empty_and_persist_zero_header_journals_are_read_only_observations(self):
        for payload in (b'',b'\x00'*28+b'retained prior pages'):
            self.api.files[self.name+'-journal']={'id':12,'data':payload}
            with self.snapshot() as view:self.assertEqual(view.receipt()['sidecars']['-journal']['sha256'],hashlib.sha256(payload).hexdigest())
            self.assertEqual(self.api.files[self.name+'-journal']['data'],payload)

    def test_any_wal_or_shm_sidecar_denies_snapshot_even_empty(self):
        for suffix in ('-wal','-shm'):
            with self.subTest(suffix=suffix):
                self.api.files[self.name+suffix]={'id':12,'data':b''}
                with self.assertRaises(AppError) as caught:
                    with self.snapshot():pass
                self.assertEqual(caught.exception.code,'windows_sqlite_wal_sidecar_unsupported')
                self.assertEqual(self.calls,[]);del self.api.files[self.name+suffix]

    def test_bad_header_page_size_and_wal_format_deny_before_connect(self):
        for offset,value,code in [(0,b'BAD!', 'windows_sqlite_header_invalid'),
            (16,b'\x02\x01','windows_sqlite_header_invalid'),(18,b'\x02\x02','windows_sqlite_wal_or_format_unsupported')]:
            data=bytearray(self.bytes);data[offset:offset+len(value)]=value;self.api.files[self.name]['data']=bytes(data)
            with self.subTest(offset=offset),self.assertRaises(AppError) as caught:
                with self.snapshot():pass
            self.assertEqual(caught.exception.code,code);self.assertEqual(self.calls,[])

    def test_bad_link_and_owner_are_rejected(self):
        for value in ({'links':2},{'owner_sid':'S-1-0-0'},{'volume_serial':88}):
            self.api.bad_file=value
            with self.subTest(value=value),self.assertRaises(AppError):
                with self.snapshot():pass
            self.assertEqual(self.calls,[]);self.assertEqual(self.api.handles,{})

    def test_changed_database_identity_or_bytes_prevents_successful_exit(self):
        for field in ('data','id'):
            self.api.files[self.name]={'data':self.bytes,'id':11}
            with self.subTest(field=field),self.assertRaises(AppError) as caught:
                with self.snapshot():self.api.files[self.name][field]=b'changed' if field=='data' else 88
            self.assertEqual(caught.exception.code,'windows_sqlite_bytes_changed');self.assertEqual(self.api.handles,{})

    def test_new_sidecar_is_retained_and_prevents_successful_exit(self):
        with self.assertRaises(AppError) as caught:
            with self.snapshot():self.api.files[self.name+'-wal']={'id':12,'data':b'preserved'}
        self.assertEqual(caught.exception.code,'windows_sqlite_sidecar_appeared')
        self.assertEqual(self.api.files[self.name+'-wal']['data'],b'preserved');self.assertEqual(self.api.handles,{})

    def test_primary_cancellation_retained_when_revalidation_fails(self):
        with self.assertRaises(KeyboardInterrupt) as caught:
            with self.snapshot():
                self.api.files[self.name]['data']=b'changed'
                raise KeyboardInterrupt('primary')
        self.assertEqual(str(caught.exception),'primary')
        self.assertIn('windows_sqlite_bytes_changed',caught.exception.snapshot_cleanup_failures)
        self.assertEqual(self.api.handles,{})

    def test_closed_snapshot_rejects_query_and_receipt(self):
        with self.snapshot() as view:pass
        for call in (lambda:view.query('SELECT 1'),view.receipt):
            with self.assertRaises(AppError) as caught:call()
            self.assertEqual(caught.exception.code,'windows_sqlite_snapshot_closed')

    def test_bounded_rows_and_instruction_budget_without_partial_results(self):
        with self.snapshot() as view:
            with self.assertRaises(AppError) as caught:
                view.query('WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<1001) SELECT n FROM x')
            self.assertEqual(caught.exception.code,'windows_sqlite_query_limit')
            with patch.object(subject,'MAX_STEPS',1000),self.assertRaises(AppError) as caught:
                view.query('WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<1000000) SELECT sum(n) FROM x')
            self.assertEqual(caught.exception.code,'windows_sqlite_query_rejected')

    def test_linux_public_entrypoint_rejects_before_opening_files(self):
        import sys
        if sys.platform=='win32':return
        with self.assertRaises(AppError) as caught:
            with subject.read_snapshot(ROOT):pass
        self.assertEqual(caught.exception.code,'windows_directory_platform_unsupported')


if __name__=='__main__':unittest.main()
