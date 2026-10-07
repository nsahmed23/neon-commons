"""Inactive native Windows Workbench persistence seam.

The existing schema and query engine are reused. No CLI/host profile selects
this component. Native namespace barriers, SQLite VFS behavior and recovery
remain required qualification gates. All failed/uncertain artifacts are kept.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import hashlib
import os
from pathlib import PureWindowsPath
import sqlite3
import time
from urllib.parse import quote
from uuid import uuid4

from .io import AppError, canonical, parse_json
from . import windows_directory as wd, windows_storage as ws, windows_sqlite as ro
from .workbench_schema import _SCHEMA_SQL, _validate_schema, SCHEMA_VERSION
from .workbench_store import WorkbenchStore, _identity, _migrate_v1_to_v2

SCHEMA = 'intune-windows-workbench-storage/1'
DATABASE = 'observations.sqlite3'
MAX_RECEIPTS = 1000


def _fail(code):
    raise AppError(code, 'The inactive native Workbench storage contract was not established.') from None


def _sha(data):
    return hashlib.sha256(data).hexdigest()


@contextmanager
def _memory_database(db):
    """Preserve the primary validation/cancellation if an owned close fails."""
    primary = None
    try:
        yield db
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            db.close()
        except BaseException as cleanup:
            if primary is not None:
                primary.sqlite_cleanup_failures = [type(cleanup).__name__]
                if hasattr(primary, 'add_note'):
                    primary.add_note('Owned SQLite cleanup also failed; preserve the primary error and any staged artifacts.')
            elif isinstance(cleanup, (KeyboardInterrupt, SystemExit)):
                raise
            else:
                _fail('windows_workbench_close_failed')


def _uri(path, mode, immutable=False):
    return 'file:' + quote(path, safe='') + '?mode=' + mode + ('&immutable=1' if immutable else '')


def _authorizer(write):
    def authorize(action, first, second, database, source):
        if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and (second or '').lower() in ('load_extension', 'readfile', 'writefile'):
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_PRAGMA and second is not None:
            # Schema migration is the only PRAGMA write admitted after setup.
            if write and (first or '').lower() == 'user_version' and second in ('1', '2'):
                return sqlite3.SQLITE_OK
            if (first or '').lower() in ('table_info', 'table_xinfo', 'index_info', 'index_list', 'foreign_key_list', 'foreign_key_check'):
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return authorize


def _configure(db, *, write):
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA trusted_schema=OFF')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA temp_store=MEMORY')
    db.enable_load_extension(False)
    db.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
    db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 16 * 1024 * 1024)
    if write:
        if db.execute('PRAGMA journal_mode=PERSIST').fetchone()[0].lower() != 'persist':
            _fail('windows_workbench_persist_required')
        db.execute('PRAGMA synchronous=FULL')
        if db.execute('PRAGMA synchronous').fetchone()[0] != 2:
            _fail('windows_workbench_full_sync_required')
    else:
        db.execute('PRAGMA query_only=ON')
    db.set_authorizer(_authorizer(write))


class _NativeAPI(ro._Win32Snapshot):
    def names(self, path):
        # The native private directory namespace is held by the caller. Each
        # selected file is separately opened no-follow and checked by handle.
        with os.scandir(path) as entries:
            names = []
            for entry in entries:
                if len(names) >= MAX_RECEIPTS * 2 + 16:
                    _fail('windows_workbench_receipt_limit')
                names.append(entry.name)
            return names


class _Filesystem:
    def __init__(self, api=None, connect=None):
        self.api = _NativeAPI() if api is None else api
        self.connect = sqlite3.connect if connect is None else connect
        self.last_receipt = None

    @contextmanager
    def _files(self, root, *, write=False, allow_hot=False):
        wd._components(root)
        with wd._pin(root, self.api) as pin, ExitStack() as handles:
            path = pin._identities[-1]['final_path'].rstrip('\\')
            namespace = None
            if write:
                namespace = handles.enter_context(ws._owned_handle(self.api, self.api.mutable_directory(path)))
                observed = self.api.metadata(namespace, private=True)
                wd._admit_private(observed, pin._sid)
                if any(observed[key] != pin._identities[-1][key] for key in ('volume_serial', 'file_id', 'final_path')):
                    _fail('windows_workbench_root_changed')
            files = {}
            for suffix in ('', '-journal', '-wal', '-shm'):
                full = path + '\\' + DATABASE + suffix
                if write and suffix in ('', '-journal'):
                    handle = self.api.open_file(full, pin._sid, lock=True)
                else:
                    handle = self.api.open_read_guard(full, optional=bool(suffix))
                if handle is None:
                    files[suffix] = None
                    continue
                handles.enter_context(ws._owned_handle(self.api, handle))
                identity = ws._bound_file(self.api, handle, pin)
                data = self.api.read(handle)
                if len(data) != identity['bytes']:
                    _fail('windows_workbench_bytes_changed')
                files[suffix] = {'handle': handle, 'identity': identity, 'data': data, 'sha256': _sha(data)}
                if suffix in ('-wal', '-shm'):
                    _fail('windows_workbench_wal_unsupported')
                if suffix == '-journal' and data and (len(data) < 28 or any(data[:28])) and not allow_hot:
                    _fail('windows_workbench_recovery_required')
                if not suffix:
                    ro._header(data)
            pin.revalidate()
            yield pin, path, namespace, files
            for suffix, before in files.items():
                if before is None:
                    unexpected = self.api.open_read_guard(path+'\\'+DATABASE+suffix, optional=True)
                    if unexpected is not None:
                        with ws._owned_handle(self.api, unexpected):
                            _fail('windows_workbench_sidecar_appeared')
                    continue
                after = ws._bound_file(self.api, before['handle'], pin)
                if any(after[key] != before['identity'][key] for key in ('volume_serial', 'file_id', 'owner_sid', 'links')):
                    _fail('windows_workbench_file_changed')
                if not write and (after != before['identity'] or _sha(self.api.read(before['handle'])) != before['sha256']):
                    _fail('windows_workbench_bytes_changed')
            pin.revalidate()

    def create(self, root, data):
        wd._components(root)
        parent = str(PureWindowsPath(root).parent); name = PureWindowsPath(root).name
        ws._create_directory(parent, name, self.api)
        ws._create_file(root, DATABASE, data, self.api)
        ws._create_file(root, DATABASE+'-journal', b'', self.api)

    def _record(self, root, name, record):
        ws._create_file(root, name, canonical(record)+b'\n', self.api)

    @contextmanager
    def connection(self, root, *, write=False):
        operation = uuid4().hex
        intent_name = 'store-intent-'+operation+'.json'
        outcome_name = 'store-outcome-'+operation+'.json'
        phase = 'before_open'; primary = None; db = None
        try:
            with self._files(root, write=write) as (pin, path, namespace, files):
                if write:
                    phase = 'before_intent'
                    self._record(root, intent_name, {'schema_version':SCHEMA, 'operation_id':operation,
                        'kind':'sqlite_connection', 'phase':'prepared', 'database_sha256_observed_before_open':files['']['sha256'],
                        'baseline_scope':'Pre-session observation, not an attribution or compare-and-swap claim across concurrent transactions.',
                        'automatic_retry_permitted':False})
                phase = 'sqlite_open'
                db = self.connect(_uri(path+'\\'+DATABASE, 'rw' if write else 'ro', not write), uri=True, timeout=5)
                try:
                    _configure(db, write=write)
                    phase = 'sqlite_session'
                    yield db
                except BaseException as error:
                    primary = error
                    raise
                finally:
                    if db is not None:
                        try:
                            db.close()
                        except BaseException as cleanup:
                            if primary is not None:
                                primary.sqlite_cleanup_failures = [type(cleanup).__name__]
                                primary.add_note('SQLite close failed; preserve the primary error and inspect retained intent.')
                            else:
                                _fail('windows_workbench_close_failed')
                        db = None
                if write:
                    phase = 'sqlite_closed_barriers_pending'
                    for value in files.values():
                        if value is not None:
                            self.api.flush_file(value['handle'])
                    self.api.flush_namespace(namespace)
                    phase = 'barriers_completed_guard_cleanup_pending'
                    receipt = {'schema_version':SCHEMA, 'operation_id':operation, 'kind':'sqlite_connection',
                        'status':'IMPLEMENTED', 'phase':'connection_and_guards_closed_barriers_completed',
                        'database_sha256_observed_after_close':_sha(self.api.read(files['']['handle'])),
                        'attribution':'No exclusive attribution across other connections; SQLite VFS provides transaction locking.',
                        'native_power_loss_qualified':False, 'platform_qualified':False, 'production_approved':False,
                        'workbench_profile_enabled':False, 'automatic_retry_permitted':False,
                        'receipt_scope':'Database connection, preexisting file guards and barriers; this record cannot prove its own later handle cleanup or host power-loss durability.'}
            # The file identity checks, directory revalidation and ALL database
            # guard cleanup must complete before a durable outcome is written.
            if write:
                phase = 'guards_closed_outcome_pending'
                self._record(root, outcome_name, receipt)
                self.last_receipt = receipt
                phase = 'outcome_recorded'
        except BaseException as error:
            if write and phase not in ('before_open','before_intent'):
                ws._uncertain(error, 'workbench_sqlite_connection', phase, [DATABASE,DATABASE+'-journal',intent_name,outcome_name])
            raise

    def read_file(self, root, name):
        name = ws._leaf(name)
        with wd._pin(root, self.api) as pin:
            path = pin._identities[-1]['final_path'].rstrip('\\')+'\\'+name
            with ws._owned_handle(self.api, self.api.open_read_guard(path)) as handle:
                before = ws._bound_file(self.api, handle, pin); data = self.api.read(handle)
                after = ws._bound_file(self.api, handle, pin)
                if before != after or len(data) != before['bytes'] or self.api.read(handle) != data:
                    _fail('windows_workbench_bytes_changed')
                return data

    def publish(self, root, destination, data):
        stage = 'store-backup-'+uuid4().hex+'.sqlite3'
        ws._create_file(root, stage, data, self.api)
        result = ws._publish(root, stage, ws._leaf(destination), _sha(data), self.api)
        return {**result, 'retained_on_failure':True}

    def status(self, root):
        with wd._pin(root, self.api) as pin:
            path = pin._identities[-1]['final_path'].rstrip('\\')
            names = self.api.names(path)
            intents = {}; outcomes = {}
            for name in names:
                if not (name.startswith('store-intent-') or name.startswith('store-outcome-')):
                    continue
                ws._leaf(name)
                value = parse_json(self.read_file(root, name))
                if value.get('schema_version') != SCHEMA or type(value.get('operation_id')) is not str:
                    _fail('windows_workbench_receipt_invalid')
                expected = ('store-intent-' if name.startswith('store-intent-') else 'store-outcome-')+value['operation_id']+'.json'
                if expected != name:
                    _fail('windows_workbench_receipt_invalid')
                target = intents if name.startswith('store-intent-') else outcomes
                target[value['operation_id']] = value
                if len(target) > MAX_RECEIPTS:
                    _fail('windows_workbench_receipt_limit')
            return {'schema_version':SCHEMA, 'outcomes':list(outcomes.values()),
                'unresolved_intents':[value for key,value in intents.items() if key not in outcomes],
                'automatic_retry_permitted':False, 'platform_qualified':False, 'workbench_profile_enabled':False}

    def recovery_copy(self, source, destination, expected_database, expected_journal):
        ws._digest(expected_database); ws._digest(expected_journal)
        with self._files(source, allow_hot=True) as (_, _, _, files):
            journal = files['-journal']
            if journal is None or files['']['sha256'] != expected_database or journal['sha256'] != expected_journal:
                _fail('windows_workbench_recovery_pin_mismatch')
            if not journal['data'] or len(journal['data']) < 28 or not any(journal['data'][:28]):
                _fail('windows_workbench_hot_journal_required')
            database_bytes = files['']['data']; journal_bytes = journal['data']
        # Source bytes remain untouched. All native rollback occurs only inside
        # a newly created private copy and is an explicit caller-selected action.
        parent = str(PureWindowsPath(destination).parent); name = PureWindowsPath(destination).name
        ws._create_directory(parent, name, self.api)
        ws._create_file(destination, DATABASE, database_bytes, self.api)
        ws._create_file(destination, DATABASE+'-journal', journal_bytes, self.api)
        self._record(destination, 'recovery-input.json', {'schema_version':SCHEMA,
            'source_database_sha256':expected_database, 'source_journal_sha256':expected_journal,
            'original_preserved':True, 'automatic_retry_permitted':False})
        phase = 'private_recovery_copy_prepared'
        try:
            with ws._root(destination, self.api) as (pin, namespace, path):
                # The copied journal was checked and preserved above. During
                # explicit recovery SQLite may remove that copied sidecar; no
                # write/delete handle from this adapter inhibits its VFS here.
                with ws._owned_handle(self.api, self.api.open_file(path+'\\'+DATABASE,pin._sid,lock=True)) as database:
                    before = ws._bound_file(self.api,database,pin)
                    phase = 'native_recovery_dispatched'
                    db = self.connect(_uri(path+'\\'+DATABASE,'rw'),uri=True,timeout=5)
                    primary = None
                    try:
                        _configure(db,write=True)
                        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                            _fail('windows_workbench_recovery_invalid')
                        _validate_schema(db)
                    except BaseException as error:
                        primary = error
                        raise
                    finally:
                        try:
                            db.close()
                        except BaseException as cleanup:
                            if primary is not None:
                                primary.recovery_cleanup_failures = [type(cleanup).__name__]
                                if hasattr(primary,'add_note'):
                                    primary.add_note('Recovery SQLite close failed; preserve the primary failure and every original/copied artifact.')
                            else:
                                _fail('windows_workbench_close_failed')
                    after = ws._bound_file(self.api,database,pin)
                    if any(after[key] != before[key] for key in ('volume_serial','file_id','owner_sid','links')):
                        _fail('windows_workbench_file_changed')
                    self.api.flush_file(database)
                    phase = 'recovered_namespace_pending'
                    self.api.flush_namespace(namespace)
                # Reestablish an explicit protected empty PERSIST journal only
                # if native recovery removed the copied one. Never truncate it.
                existing = self.api.open_read_guard(path+'\\'+DATABASE+'-journal',optional=True)
                if existing is None:
                    ws._create_file(destination,DATABASE+'-journal',b'',self.api)
                else:
                    with ws._owned_handle(self.api,existing):
                        ws._bound_file(self.api,existing,pin)
                        data=self.api.read(existing)
                        if data and (len(data)<28 or any(data[:28])):
                            _fail('windows_workbench_recovery_incomplete')
            result = {'schema_version':SCHEMA,'original_preserved':True,'recovered_copy':destination,
                'source_database_sha256':expected_database,'source_journal_sha256':expected_journal,
                'native_power_loss_qualified':False,'platform_qualified':False,'workbench_profile_enabled':False}
            self._record(destination,'recovery-outcome.json',result)
            return result
        except BaseException as error:
            ws._uncertain(error,'workbench_recovery_copy',phase,[DATABASE,DATABASE+'-journal','recovery-input.json'])
            raise


def _image(db):
    if not callable(getattr(db, 'serialize', None)):
        _fail('windows_workbench_sqlite_serialization_required')
    target = sqlite3.connect(':memory:')
    started = time.monotonic()
    with _memory_database(target):
        def progress(status, remaining, total):
            if time.monotonic()-started > 10 or total * db.execute('PRAGMA page_size').fetchone()[0] > ws.MAX_BYTES:
                _fail('windows_workbench_backup_limit')
        db.backup(target, pages=64, progress=progress)
        if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            _fail('windows_workbench_backup_invalid')
        result = target.serialize()
        if len(result) > ws.MAX_BYTES:
            _fail('windows_workbench_backup_limit')
        return result


def _validate_image(data, tenant=None):
    ro._header(data)
    db = sqlite3.connect(':memory:')
    with _memory_database(db):
        db.deserialize(data)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA trusted_schema=OFF'); db.execute('PRAGMA query_only=ON')
        version = _validate_schema(db)
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
            _fail('windows_workbench_backup_invalid')
        row = db.execute("SELECT value FROM metadata WHERE key='tenant_id'").fetchone()
        actual = _identity(row[0]) if row is not None else None
        if actual is None or tenant is not None and _identity(tenant) != actual:
            _fail('workbench_wrong_tenant')
        return actual, version


class WindowsWorkbenchStore(WorkbenchStore):
    """Inactive native adapter; ordinary Workbench host gates stay unsupported."""
    def __init__(self, root, tenant_id=None):
        self._initialize(root, tenant_id, _Filesystem())

    def _initialize(self, root, tenant, filesystem):
        wd._components(str(root)); self.root=PureWindowsPath(root); self.path=self.root/DATABASE; self._filesystem=filesystem
        with self._connection() as db:
            self.schema_version=_validate_schema(db)
            row=db.execute("SELECT value FROM metadata WHERE key='tenant_id'").fetchone()
            if row is None:_fail('workbench_schema_invalid')
            self.tenant_id=_identity(row[0])
            if tenant is not None and _identity(tenant)!=self.tenant_id:_fail('workbench_wrong_tenant')

    @classmethod
    def _open(cls,root,tenant,filesystem):
        result=cls.__new__(cls);result._initialize(root,tenant,filesystem);return result

    @classmethod
    def create(cls,root,tenant_id):
        return cls._create(root,tenant_id,_Filesystem())

    @classmethod
    def _create(cls,root,tenant,filesystem):
        tenant=_identity(tenant);db=sqlite3.connect(':memory:')
        with _memory_database(db):
            db.executescript(_SCHEMA_SQL)
            with db:db.execute('INSERT INTO metadata VALUES(?,?)',('tenant_id',tenant))
            data=db.serialize()
        filesystem.create(str(root),data)
        return cls._open(root,tenant,filesystem)

    @contextmanager
    def _connection(self,write=False,recovery=False):
        if recovery:_fail('windows_workbench_explicit_recovery_required')
        with self._filesystem.connection(str(self.root),write=write) as db:yield db

    def collect(self,*args,**kwargs):_fail('windows_workbench_model_collection_unsupported')
    def import_capture(self,*args,**kwargs):_fail('windows_workbench_capture_reader_unsupported')
    def raw_capture_observation(self,*args,**kwargs):_fail('windows_workbench_capture_reader_unsupported')

    def backup(self,destination):
        destination=str(destination);wd._components(destination)
        with self._connection() as db:data=_image(db)
        tenant,version=_validate_image(data,self.tenant_id)
        publication=self._filesystem.publish(str(PureWindowsPath(destination).parent),PureWindowsPath(destination).name,data)
        return {'path':destination,'sha256':_sha(data),'tenant_id':tenant,'schema_version':version,
            'evidence_class':'local_sqlite_backup','cloud_authority':False,'publication':publication}

    @classmethod
    def restore(cls,backup,root,tenant_id=None,*,expected_sha256):
        return cls._restore(backup,root,tenant_id,expected_sha256,_Filesystem())

    @classmethod
    def _restore(cls,backup,root,tenant,expected,filesystem):
        ws._digest(expected);backup=str(backup);wd._components(backup)
        data=filesystem.read_file(str(PureWindowsPath(backup).parent),PureWindowsPath(backup).name)
        if _sha(data)!=expected:_fail('windows_workbench_backup_pin_mismatch')
        actual,_=_validate_image(data,tenant)
        filesystem.create(str(root),data)
        return cls._open(root,actual,filesystem)

    def migrate(self,backup_path):
        if self.schema_version==SCHEMA_VERSION:
            return {'status':'already_current','from_version':SCHEMA_VERSION,'to_version':SCHEMA_VERSION,'backup':None}
        backup=self.backup(backup_path)
        with self._connection(True) as db,db:
            db.execute('BEGIN IMMEDIATE')
            if _validate_schema(db)!=1:_fail('workbench_migration_changed')
            _migrate_v1_to_v2(db);_validate_schema(db)
        self.schema_version=SCHEMA_VERSION
        return {'status':'migrated','from_version':1,'to_version':SCHEMA_VERSION,'backup':backup}

    def storage_status(self):return self._filesystem.status(str(self.root))

    @classmethod
    def storage_status_at(cls,root):return _Filesystem().status(str(root))

    @classmethod
    def recover_into_new(cls,source_root,new_root,tenant_id,*,database_sha256,journal_sha256):
        return cls._recover(source_root,new_root,tenant_id,database_sha256,journal_sha256,_Filesystem())

    @classmethod
    def _recover(cls,source,new,tenant,database_sha,journal_sha,filesystem):
        tenant=_identity(tenant)
        receipt=filesystem.recovery_copy(str(source),str(new),database_sha,journal_sha)
        result=cls._open(new,tenant,filesystem);result.recovery_receipt=receipt;return result
