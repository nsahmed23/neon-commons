"""Inactive, target-bound native observation route over the existing reader/store.

Capabilities are cooperative in-process integrity, not a hostile-Python boundary.
Native storage does not promote laboratory service evidence. No ordinary host
profile, scheduler, credential or cloud write is enabled by this module.
"""
from contextlib import contextmanager
import os
from pathlib import PureWindowsPath
from uuid import uuid4

from .io import AppError, digest
from . import windows_storage as ws, windows_workbench as ww
from .observation_reader import (CapturedObservation, LaboratoryGraphReader,
    LiveGraphReader, _publish_batch)
from .workbench_schema import _validate_schema

_NATIVE = object()
_LAB = object()
_STORAGE = object()


def _fail(code):
    raise AppError(code, 'The native observation target, storage or captured source binding changed or is unavailable.')


def _identity(value):
    return {key:value[key] for key in ('volume_serial','file_id','owner_sid')} | {key:value[key] for key in ('final_path','links') if key in value}


class _Storage:
    __slots__ = ('_target','_seal')
    def __init__(self,seal,target):
        if seal is not _STORAGE:_fail('windows_observer_constructor_forbidden')
        self._target,self._seal=target,seal
    def __reduce_ex__(self,protocol):raise TypeError('Observation storage capabilities cannot be serialized.')
    def path(self,path):return PureWindowsPath(path)
    def capture(self,*args,**kwargs):
        _admit_storage(self)
        from .capture import _capture
        from .windows_capture_writer import _output
        return _capture(*args,**kwargs,output_factory=lambda destination:_output(destination,self._target._api))
    def load(self,path,tenant):
        _admit_storage(self)
        if tenant!=self._target._tenant:_fail('windows_observer_wrong_tenant')
        from .windows_capture import _load
        return _load(path,tenant,self._target._api)


def _admit_storage(storage,reader=None):
    if type(storage) is not _Storage or storage._seal is not _STORAGE:
        _fail('windows_observer_storage_required')
    target=storage._target
    if type(target) not in (NativeWindowsObservationTarget,LaboratoryWindowsObservationTarget):
        _fail('windows_observer_target_required')
    target._fresh()
    if storage is not target._storage:_fail('windows_observer_storage_changed')
    if reader is not None:
        if type(reader) not in (LiveGraphReader,LaboratoryGraphReader):_fail('windows_observer_reader_required')
        if reader._spec.tenant_id!=target._tenant:_fail('windows_observer_wrong_tenant')
        if type(target) is LaboratoryWindowsObservationTarget and type(reader) is LiveGraphReader:
            _fail('windows_observer_live_to_laboratory_forbidden')


class _Target:
    __slots__=('_store','_filesystem','_api','_connect','_root','_tenant','_binding','_binding_digest',
               '_storage','_pid','_closed','_seal')
    def __init__(self,seal,store):
        if not ((type(self) is NativeWindowsObservationTarget and seal is _NATIVE)
                or (type(self) is LaboratoryWindowsObservationTarget and seal is _LAB)):
            _fail('windows_observer_constructor_forbidden')
        if type(store) is not ww.WindowsWorkbenchStore or type(store._filesystem) is not ww._Filesystem:
            _fail('windows_observer_store_required')
        self._store,self._filesystem=store,store._filesystem
        self._api,self._connect=self._filesystem.api,self._filesystem.connect
        self._root,self._tenant=str(store.root),store.tenant_id
        self._pid,self._closed,self._seal=os.getpid(),False,seal
        with self._filesystem._files(self._root) as (pin,path,namespace,files):
            tenant,version=ww._validate_image(files['']['data'],self._tenant)
            if version!=2:_fail('workbench_migration_required')
            self._binding={'root':self._root,'tenant_id':tenant,'directory':_identity(pin._identities[-1]),
                'database':_identity(files['']['identity'])}
        self._binding_digest=digest(self._binding)
        self._storage=_Storage(_STORAGE,self)
    def __repr__(self):return '<'+type(self).__name__+' inactive, source authority unchanged>'
    def __reduce_ex__(self,protocol):raise TypeError('Observation targets cannot be serialized.')
    def _fresh(self):
        if self._closed or self._pid!=os.getpid():_fail('windows_observer_closed')
        expected=_NATIVE if type(self) is NativeWindowsObservationTarget else _LAB
        if (self._seal is not expected or digest(self._binding)!=self._binding_digest
                or self._root!=self._binding['root'] or self._tenant!=self._binding['tenant_id']
                or str(self._store.root)!=self._root or self._store.tenant_id!=self._tenant
                or self._store.path!=PureWindowsPath(self._root)/ww.DATABASE
                or self._store._filesystem is not self._filesystem
                or self._filesystem.api is not self._api or self._filesystem.connect is not self._connect):
            _fail('windows_observer_target_changed')
    def _check(self,pin,files):
        self._fresh()
        if (_identity(pin._identities[-1])!=self._binding['directory']
                or _identity(files['']['identity'])!=self._binding['database']):
            _fail('windows_observer_target_changed')
    def _snapshot(self):
        self._fresh()
        with self._filesystem._files(self._root) as (pin,path,namespace,files):
            self._check(pin,files)
            tenant,version=ww._validate_image(files['']['data'],self._tenant)
            if version!=2:_fail('workbench_migration_required')
    def capture(self,reader,object_id,output,*,max_elapsed_seconds=120):
        _admit_storage(self._storage,reader)
        self._snapshot()
        return reader._capture_with_storage(object_id,output,max_elapsed_seconds=max_elapsed_seconds,storage=self._storage)
    def _validate_transaction(self,db):
        self._fresh()
        if _validate_schema(db)!=2:_fail('workbench_migration_required')
        row=db.execute("SELECT value FROM metadata WHERE key='tenant_id'").fetchone()
        if row is None or row[0]!=self._tenant:_fail('windows_observer_wrong_tenant')
    @contextmanager
    def _transaction(self,write):
        if write is not True:_fail('windows_observer_transaction_invalid')
        self._fresh();operation=uuid4().hex;phase='before_target_open'
        intent='store-intent-'+operation+'.json';outcome='store-outcome-'+operation+'.json'
        try:
            with self._filesystem._files(self._root,write=True) as (pin,path,namespace,files):
                self._check(pin,files)
                phase='recording_target_intent'
                self._filesystem._record(self._root,intent,{'schema_version':ww.SCHEMA,'operation_id':operation,
                    'kind':'observation_publication','target':self._binding,'phase':'prepared',
                    'automatic_retry_permitted':False})
                phase='sqlite_publication'
                with self._store._connection(True) as db:yield db
                self._check(pin,files)
                phase='target_guard_cleanup'
            phase='recording_target_outcome'
            self._filesystem._record(self._root,outcome,{'schema_version':ww.SCHEMA,'operation_id':operation,
                'kind':'observation_publication','target':self._binding,'status':'IMPLEMENTED',
                'phase':'database_connection_and_target_guards_closed',
                'receipt_scope':'Database publication only; later result delivery and this receipt cleanup are separate.',
                'platform_qualified':False,'production_approved':False,'workbench_profile_enabled':False,
                'automatic_retry_permitted':False})
        except BaseException as error:
            if phase!='before_target_open':
                error.observation_outcome={'outcome_uncertain':True,'phase':phase,
                    'retained_artifacts':[intent,outcome,ww.DATABASE,ww.DATABASE+'-journal'],
                    'automatic_retry_permitted':False}
            raise
    def publish(self,captures,*,job_id,attempt_id,failures=()):
        self._snapshot()
        if type(captures) not in (list,tuple):_fail('reader_publication_invalid')
        for item in captures:
            if type(item) is not CapturedObservation or item._storage is not self._storage:
                _fail('windows_observer_capture_target_mismatch')
        return _publish_batch(self._store,captures,job_id=job_id,attempt_id=attempt_id,failures=failures,
            _transaction=self._transaction,_validate_transaction=self._validate_transaction)
    def close(self):self._closed=True


class NativeWindowsObservationTarget(_Target):
    """Actual native filesystem constructor; still requires native qualification."""
    __slots__=()


class LaboratoryWindowsObservationTarget(_Target):
    """Recorded native effects only; no live-reader admission or live assurance."""
    __slots__=()


def bind_native_target(root,tenant_id):
    return NativeWindowsObservationTarget(_NATIVE,ww.WindowsWorkbenchStore(root,tenant_id))


def _bind_laboratory_target(store):
    return LaboratoryWindowsObservationTarget(_LAB,store)
