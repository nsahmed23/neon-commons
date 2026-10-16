"""POSIX adapter for signed read-only worker evidence; no source-store recovery.

Trusted cooperative worker filesystem, not immunity to a hostile same-UID process.
New output/ingestion persistence is distinct from read-only source inspection.
"""
from __future__ import annotations
import base64
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time
import uuid
from . import worker_evidence as contract
from .io import canonical,digest,parse_json,AppError
from .provider_journey import _private,_absolute,_outside_repository
from . import approval_authority as aa,protected


def read(path,limit=contract.MAX_BYTES):
    path=_private(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK);primary=None
    try:
        before=os.fstat(fd)
        def private(value):return stat.S_ISREG(value.st_mode) and value.st_nlink==1 and value.st_uid==os.geteuid() and not value.st_mode&0o077 and 0<value.st_size<=limit
        if not private(before):contract.fail('worker_evidence_private_file')
        chunks=[];total=0
        while total<=limit:
            chunk=os.read(fd,min(1024*1024,limit+1-total))
            if not chunk:break
            chunks.append(chunk);total+=len(chunk)
        raw=b''.join(chunks);after=os.fstat(fd);named=os.lstat(path)
        signature=lambda i:(i.st_dev,i.st_ino,i.st_size,i.st_mtime_ns,i.st_ctime_ns,i.st_mode,i.st_uid,i.st_nlink)
        if not private(after) or not private(named) or len(raw)!=before.st_size or signature(before)!=signature(after) or signature(before)!=signature(named):contract.fail('worker_evidence_source_changed')
        return raw
    except BaseException as error:primary=error;raise
    finally:
        try:os.close(fd)
        except BaseException as closing:
            if primary is None:raise
            if isinstance(closing,(KeyboardInterrupt,SystemExit)):raise closing from primary
            primary.add_note('Secondary received-evidence file close: '+type(closing).__name__)


def load(path,limit=contract.MAX_BYTES):return parse_json(read(path,limit))
def write_new(path,value):
    path=Path(path);_private(path.parent,directory=True)
    protected._exclusive(path,canonical(value));protected._sync(path.parent)


def new_directory(path):
    path=_absolute(str(path));_private(path.parent,directory=True);path.mkdir(mode=0o700)
    protected._sync(path.parent);return _private(path,directory=True)


def _no_sidecars(path):
    for suffix in ('-journal','-wal','-shm'):
        candidate=Path(str(path)+suffix)
        if candidate.exists() or candidate.is_symlink():contract.fail('worker_evidence_source_recovery_required')


@contextmanager
def readonly_database(path):
    path=_private(path);_no_sidecars(path);before=read(path,64*1024*1024)
    connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=0,isolation_level=None)
    started=time.monotonic();ticks=[0];primary=None
    def progress():
        ticks[0]+=1
        return int(ticks[0]>10000 or time.monotonic()-started>5)
    try:
        connection.execute('PRAGMA query_only=ON');connection.execute('PRAGMA trusted_schema=OFF')
        if connection.execute('PRAGMA journal_mode').fetchone()[0]!='delete':contract.fail('worker_evidence_source_recovery_required')
        connection.set_progress_handler(progress,1000)
        connection.execute('BEGIN');connection.execute('SELECT count(*) FROM sqlite_schema').fetchone()
        _no_sidecars(path)
        if connection.execute("SELECT 1 FROM sqlite_schema WHERE type IN ('view','trigger') LIMIT 1").fetchone():contract.fail('worker_evidence_source_schema')
        yield connection,hashlib.sha256(before).hexdigest()
        _no_sidecars(path)
        if read(path,64*1024*1024)!=before:contract.fail('worker_evidence_source_changed')
    except BaseException as error:
        primary=error
        if isinstance(error,sqlite3.Error):
            primary=AppError('worker_evidence_source_unavailable','The existing source journal cannot be read without recovery or exceeds its bounded query.')
            raise primary from error
        raise
    finally:
        try:connection.close()
        except BaseException as closing:
            if primary is None:raise
            if isinstance(closing,(KeyboardInterrupt,SystemExit)):raise closing from primary
            if hasattr(primary,'add_note'):primary.add_note('Read-only source close also failed: '+type(closing).__name__)


def _columns(db,table,names):
    actual=db.execute('PRAGMA table_info('+table+')').fetchall()
    if [r[1] for r in actual]!=names:contract.fail('worker_evidence_source_schema')


def _capture(root,tenant):
    from .capture_adapter import _posix_capture_directory,_load_capture
    _private(root,directory=True)
    members={}
    with _posix_capture_directory(root) as access:
        if set(access.names())!={'export.json','context.json','capture-receipt.json','raw'}:contract.fail('worker_evidence_capture')
        for name in ('export.json','context.json','capture-receipt.json'):members[name]=read(Path(root)/name)
        with access.raw() as raw:
            names=raw.names()
            if len(names)>10000:contract.fail('worker_evidence_limit')
            for name in names:
                if not __import__('re').fullmatch('page-[0-9]{6}\\.json',name):contract.fail('worker_evidence_member_path')
                members['raw/'+name]=read(Path(root)/'raw'/name,4*1024*1024)
    result={name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'base64':base64.b64encode(data).decode()} for name,data in members.items()}
    captured=contract.capture_members(result,tenant)
    return result,captured


def _capture_source(store_root,req,captured):
    from .workbench_schema import _validate_schema
    root=_private(store_root,directory=True)
    with readonly_database(root/'observations.sqlite3') as (db,_):
        if _validate_schema(db)!=2:contract.fail('worker_evidence_observation_schema')
        tenant=db.execute("SELECT value FROM metadata WHERE key='tenant_id'").fetchone()
        if tenant!=(req['tenant_id'],):contract.fail('worker_evidence_capture_identity')
        rows=db.execute("""SELECT d.source_json,r.observed_at FROM run_details d
            JOIN collection_runs r USING(run_id) JOIN run_scope_objects s USING(run_id)
            WHERE r.tenant_id=? AND s.object_id=? AND json_extract(d.source_json,'$.capture_sha256')=?
            ORDER BY r.observed_at DESC,r.run_id DESC LIMIT 2""",(req['tenant_id'],req['object_id'],captured['capture_sha256'])).fetchall()
        if not rows:contract.fail('worker_evidence_capture_provenance')
        source=parse_json(rows[0][0])
        if canonical(source.get('raw_observed'))!=canonical(captured['source']['raw_observed']) or rows[0][1]!=captured['observed_at']:contract.fail('worker_evidence_capture_provenance')
        return {'evidence_class':source.get('evidence_class'),'capture_sha256':captured['capture_sha256'],
            'raw_observed_sha256':digest(source['raw_observed']),'observed_at':captured['observed_at'],
            'source_record_sha256':digest(source),'assurance':'publisher_checked_registered_local_observation_not_remote_reauthentication'}


def snapshot(job_root,policy_path,req,*,capture_root=None,store_root=None,state_raw=None):
    if req.get('schema_version')=='worker-evidence-request/2':
        from .worker_evidence_domain_posix import snapshot as domain_snapshot
        return domain_snapshot(job_root,policy_path,req,capture_root=capture_root,store_root=store_root,state_raw=state_raw)
    if state_raw is not None:contract.fail('worker_evidence_action_unsupported')
    req=contract.request(req);policy_path=_private(policy_path);_outside_repository(policy_path)
    policy=load(policy_path,256*1024)
    contract.shape(policy,'schema_version authority_root jobs_root verifier approvers admitted_manifest_sha256')
    if policy['schema_version']!='worker-service-policy/1':contract.fail('worker_evidence_worker_policy')
    root=_private(job_root,directory=True);authority=_private(policy['authority_root'],directory=True)
    jobs=_private(policy['jobs_root'],directory=True)
    if root.parent!=jobs or authority==jobs or authority in jobs.parents or jobs in authority.parents:contract.fail('worker_evidence_worker_policy')
    original_manifest=read(root/'manifest.json',256*1024);manifest=parse_json(original_manifest)
    binding=load(root/'policy-binding.json',256*1024)
    if digest(manifest)!=req['manifest_sha256'] or digest(manifest) not in policy['admitted_manifest_sha256'] or binding!={'policy_sha256':digest(policy)}:contract.fail('worker_evidence_worker_binding')
    with readonly_database(authority/'service.sqlite3') as (db,dbsha):
        _columns(db,'jobs',['id','root','manifest_sha256','status','cancelled','dispatches','outcome','controller_pid','controller_start'])
        _columns(db,'consumed',['issuer','nonce','operation_id','manifest_sha256'])
        _columns(db,'events',['sequence','job','kind','payload','created_at'])
        row=db.execute('SELECT root,manifest_sha256,status,cancelled,dispatches,outcome FROM jobs WHERE id=?',(req['operation_id'],)).fetchone()
        if row is None or row[:2]!=(str(root),req['manifest_sha256']):contract.fail('worker_evidence_job_registration')
        rows=db.execute('SELECT sequence,kind,payload,created_at FROM events WHERE job=? ORDER BY sequence LIMIT 1001',(req['operation_id'],)).fetchall()
        if not rows or len(rows)>1000:contract.fail('worker_evidence_event_limit')
        events=[{'sequence':r[0],'kind':r[1],'payload':parse_json(r[2]),'created_at':r[3]} for r in rows]
        consumed=db.execute('SELECT issuer,nonce,operation_id,manifest_sha256 FROM consumed WHERE operation_id=?',(req['operation_id'],)).fetchone()
        transcript=None
        if db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='approval_transcripts'").fetchone():
            _columns(db,'approval_transcripts',['operation_id','receipt_json','receipt_sha256','consumed_at'])
            approval=db.execute('SELECT receipt_json,receipt_sha256,consumed_at FROM approval_transcripts WHERE operation_id=?',(req['operation_id'],)).fetchone()
            if approval:
                transcript={'receipt':parse_json(approval[0]),'receipt_sha256':approval[1],'consumed_at':approval[2]}
                if db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?',(transcript['receipt']['payload']['issuer'],transcript['receipt']['payload']['key_id'])).fetchone():contract.fail('worker_evidence_revoked')
        # Read-at is the actual coherent read time, never a later signing time.
        at=int(time.time())
        value={'schema_version':'worker-evidence-snapshot/1','read_at':at,'manifest':manifest,'policy_sha256':digest(policy),
            'journal':{'database_sha256':dbsha,'selected_event_count':len(events),'first_sequence':events[0]['sequence'],
                'last_sequence':events[-1]['sequence'],'events_sha256':digest(events)},
            'job':{'status':row[2],'cancel_requested':bool(row[3]),'dispatches':row[4],'outcome':parse_json(row[5]) if row[5] else None},
            'events':events,'approval':transcript,'consumed':dict(zip(('issuer','nonce','operation_id','manifest_sha256'),consumed)) if consumed else None,
            'capture_provenance':None,'capture':None}
        if capture_root is not None:
            if store_root is None:contract.fail('worker_evidence_observation_required')
            value['capture'],captured=_capture(capture_root,req['tenant_id'])
            value['capture_provenance']=_capture_source(store_root,req,captured)
        elif store_root is not None:contract.fail('worker_evidence_capture_required')
        if read(root/'manifest.json',256*1024)!=original_manifest or digest(load(policy_path,256*1024))!=digest(policy):contract.fail('worker_evidence_source_changed')
        contract.validate_snapshot(value,req)
        return value


class DetachedVerifier:
    def __init__(self,path,scratch):
        self.root=_private(scratch,directory=True);value=load(path,65536)
        contract.shape(value,'executable sha256 validator_library validator_sha256')
        self.pin=aa.VerifierPin(_absolute(value['executable']),contract.hashed(value['sha256']),
            _absolute(value['validator_library']),contract.hashed(value['validator_sha256']))
        # Preserve the qualified strict point validator pin; no caller repin.
        if self.pin.validator_sha256!=aa.VerifierPin(Path('/unused'),'0'*64).validator_sha256:contract.fail('worker_evidence_validator_pin')
    def __call__(self,key,message,signature):
        aa._valid_public_key(self.pin,bytes.fromhex(contract.hashed(key)))
        fd=os.open(protected._path(self.pin.executable),os.O_RDONLY|os.O_NOFOLLOW);primary=None
        try:
            with os.fdopen(os.dup(fd),'rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=self.pin.sha256:contract.fail('worker_evidence_verifier_changed')
            with tempfile.TemporaryDirectory(prefix='worker-evidence-verify-',dir=self.root) as temporary:
                root=Path(temporary)
                for name,data in [('key.der',aa._SPKI+bytes.fromhex(key)),('message',message),('signature',signature)]:protected._exclusive(root/name,data)
                protected._supervise([str(self.pin.executable),'pkeyutl','-verify','-pubin','-keyform','DER','-inkey',str(root/'key.der'),
                    '-rawin','-in',str(root/'message'),'-sigfile',str(root/'signature')],cwd=root,
                    env={'PATH':'/usr/bin:/bin','HOME':str(root),'OPENSSL_CONF':'/dev/null'},pass_fds=(fd,),executable='/proc/self/fd/'+str(fd),timeout=5,output_limit=4096)
        except BaseException as error:
            primary=error
            if isinstance(error,AppError):
                primary=AppError('worker_evidence_signature_invalid','The pinned verifier rejected the detached signature.')
                raise primary from error
            raise
        finally:
            try:os.close(fd)
            except BaseException as closing:
                if primary is None:raise
                if isinstance(closing,(KeyboardInterrupt,SystemExit)):raise closing from primary
                if hasattr(primary,'add_note'):primary.add_note('Owned verifier descriptor close also failed: '+type(closing).__name__)


def prepare(req,trust_policy,publisher,job_root,policy_path,*,capture_root=None,store_root=None,state_raw=None):
    policy=contract.trust(trust_policy);req=contract.request(req)
    if digest(policy)!=req['trust_sha256']:contract.fail('worker_evidence_trust_changed')
    captured=snapshot(job_root,policy_path,req,capture_root=capture_root,store_root=store_root,state_raw=state_raw)
    issued=int(time.time())
    return {'schema_version':'worker-evidence-statement/1','publisher':publisher,'request_sha256':digest(req),
        'request_nonce':req['nonce'],'issued_at':issued,'expires_at':issued+policy['max_lifetime_seconds'],'snapshot':captured}


def ingest(store_root,envelope,req,policy,verifier):
    return ingest_raw(store_root,canonical(contract.bounded(envelope)),canonical(contract.bounded(req)),policy,verifier)


def ingest_raw(store_root,envelope_raw,request_raw,policy,verifier):
    if any(type(raw) is not bytes or len(raw)>contract.MAX_BYTES for raw in (envelope_raw,request_raw)):contract.fail('worker_evidence_limit')
    root=_private(store_root,directory=True);_outside_repository(root/'evidence.sqlite3')
    attempt=new_directory(root/('attempt-'+uuid.uuid4().hex))
    # Preserve failed received bytes and exact local request before validation.
    protected._exclusive(attempt/'envelope.json',envelope_raw);protected._exclusive(attempt/'request.json',request_raw);protected._sync(attempt)
    try:
        frozen_envelope=load(attempt/'envelope.json');req=load(attempt/'request.json')
        verified=contract.verify_envelope(frozen_envelope,req,policy,verifier,now=contract.fresh_now(floor=root/'clock.json',persist=True))
        # Only process-owned parsed persisted bytes and verified content feed the ledger.
        result=verified.result();binding=contract.received_binding(verified,digest(req))
        result.update(received_byte_sha256=hashlib.sha256(envelope_raw).hexdigest(),request_byte_sha256=hashlib.sha256(request_raw).hexdigest())
        database=root/'evidence.sqlite3'
        try:protected._exclusive(database,b'')
        except FileExistsError:pass
        _private(database);_no_sidecars(database)
        with sqlite3.connect(database,timeout=0,isolation_level=None) as db:
            db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA trusted_schema=OFF')
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS received(request_sha256 TEXT PRIMARY KEY,bundle_sha256 TEXT NOT NULL,envelope_byte_sha256 TEXT NOT NULL,request_byte_sha256 TEXT NOT NULL,attempt TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS heads(scope TEXT PRIMARY KEY,sequence INTEGER NOT NULL,event_sha256 TEXT NOT NULL)')
            prior=db.execute('SELECT bundle_sha256,attempt FROM received WHERE request_sha256=?',(digest(req),)).fetchone()
            scope=binding['scope'];sequence=binding['sequence'];events=binding['event_sha256']
            head=db.execute('SELECT sequence,event_sha256 FROM heads WHERE scope=?',(scope,)).fetchone()
            contract.admit_received(binding,prior[0] if prior else None,dict(zip(('sequence','event_sha256'),head)) if head else None)
            if prior is None:db.execute('INSERT INTO received VALUES (?,?,?,?,?)',(digest(req),result['bundle_sha256'],result['received_byte_sha256'],result['request_byte_sha256'],attempt.name))
            db.execute('INSERT INTO heads VALUES (?,?,?) ON CONFLICT(scope) DO UPDATE SET sequence=excluded.sequence,event_sha256=excluded.event_sha256',(scope,sequence,events))
            db.execute('COMMIT')
        protected._sync(root)
        write_new(attempt/'result.json',result)
        return dict(result,stored_attempt=attempt.name,idempotent=prior is not None)
    except BaseException as error:
        try:write_new(attempt/'failure.json',{'status':'FAIL','code':getattr(error,'code',type(error).__name__),'evidence_preserved':True,'baseline_admissible':False})
        except BaseException as recording:
            if isinstance(recording,(KeyboardInterrupt,SystemExit)):raise recording from error
            if hasattr(error,'add_note'):error.add_note('Worker evidence failure recording also failed: '+type(recording).__name__)
        raise


def reopen(store_root,request_sha256,policy,verifier,*,historical=False):
    root=_private(store_root,directory=True);contract.hashed(request_sha256)
    with readonly_database(root/'evidence.sqlite3') as (db,_):
        row=db.execute('SELECT bundle_sha256,attempt,envelope_byte_sha256,request_byte_sha256 FROM received WHERE request_sha256=?',(request_sha256,)).fetchone()
    if not row or not __import__('re').fullmatch('attempt-[a-f0-9]{32}',row[1]):contract.fail('worker_evidence_not_stored')
    attempt=_private(root/row[1],directory=True);envelope_raw=read(attempt/'envelope.json');request_raw=read(attempt/'request.json')
    envelope=parse_json(envelope_raw);req=parse_json(request_raw)
    if digest(envelope)!=row[0] or digest(req)!=request_sha256 or hashlib.sha256(envelope_raw).hexdigest()!=row[2] or hashlib.sha256(request_raw).hexdigest()!=row[3]:contract.fail('worker_evidence_stored_bytes_changed')
    now=int(time.time()) if historical else contract.fresh_now(floor=root/'clock.json')
    verified=contract.verify_envelope(envelope,req,policy,verifier,now=now,historical=historical)
    binding=contract.received_binding(verified,request_sha256)
    with readonly_database(root/'evidence.sqlite3') as (db,_):
        current=db.execute('SELECT bundle_sha256,attempt,envelope_byte_sha256,request_byte_sha256 FROM received WHERE request_sha256=?',(request_sha256,)).fetchone()
        if current!=row:contract.fail('worker_evidence_stored_bytes_changed')
        head=db.execute('SELECT sequence,event_sha256 FROM heads WHERE scope=?',(binding['scope'],)).fetchone()
    return contract.stored_result(verified,dict(zip(('sequence','event_sha256'),head)) if head else None)
