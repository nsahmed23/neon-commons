"""Inactive native receipt persistence using the existing guarded Workbench store.

Exact received bytes are retained before verification. The same pure publisher
ordering predicate as POSIX runs inside the native store's SQLite transaction.
Metadata is only an index: reopening always verifies bytes, signatures and trust.
"""
from pathlib import PureWindowsPath
import hashlib
import re
import sqlite3
import time
from uuid import uuid4
from . import windows_worker_evidence as native, windows_capture as capture, windows_storage as storage
from . import clock, worker_evidence as contract
from .io import canonical,digest,parse_json,AppError
from .workbench_schema import _validate_schema
from .windows_workbench import WindowsWorkbenchStore

RECEIVED='worker_evidence_received:'
HEAD='worker_evidence_head:'


def _store(value):
    if type(value) is not WindowsWorkbenchStore:contract.fail('native_workspace_store_capability_required')
    return value


def _metadata(db,key):
    row=db.execute('SELECT value FROM metadata WHERE key=?',(key,)).fetchone()
    if row is None:return None
    if type(row[0]) is not str or len(row[0].encode('utf-8'))>65536:contract.fail('worker_evidence_index_invalid')
    return parse_json(row[0])


def _record(value):
    contract.shape(value,'schema_version request_sha256 bundle_sha256 envelope_byte_sha256 request_byte_sha256 attempt')
    if value['schema_version']!='worker-evidence-received/1' or type(value['attempt']) is not str or not re.fullmatch('evidence-attempt-[a-f0-9]{32}',value['attempt']):contract.fail('worker_evidence_index_invalid')
    for key in ('request_sha256','bundle_sha256','envelope_byte_sha256','request_byte_sha256'):contract.hashed(value[key])
    return value


CLOCK='worker_evidence_clock'
MARK_STEP=60  # seconds the observed time may run ahead of the stored mark before a read records it


def _mark(db):
    """The store-wide high-water mark of authenticated reads (one metadata key, like the POSIX store's clock.json)."""
    value=_metadata(db,CLOCK)
    if value is None:return 0
    contract.shape(value,'high_water')
    if type(value['high_water']) is not int or not 1<=value['high_water']<=9007199254740991:contract.fail('worker_evidence_index_invalid')
    return value['high_water']


def _effective(store,mark,*,anchor=True):
    """max(wall, durable mark, the process monotonic carry of the wall): the process floor is the secondary floor."""
    wall=time.time()
    if not anchor:return max(int(wall),mark)
    return max(int(wall),mark,int(clock._process_floor('worker-evidence-store:'+str(store.root),wall)))


def _peek(store):
    """Reading for the authenticating pass: max(wall, durable mark), no process anchor touched. An input that fails
    authentication has no clock effect; the anchor moves only in the authenticated phase (_judge)."""
    with store._connection() as db:
        _validate_schema(db);return _effective(store,_mark(db),anchor=False)


def _judge(store,db,decide,apply):
    """Inside the open BEGIN IMMEDIATE transaction: resample the wall, raise the mark, decide admission on the effective
    time with decide(now), and (only if admitted and the mark was written) apply(verified); then commit. A refusal still
    commits the raised mark (a closed window stays closed). A temporal refusal keeps its code even when the mark could not be
    written or committed (it then says closure_recorded=false); an admission whose time was not recorded is refused with
    worker_evidence_clock_unrecorded. Returns the pending refusal or None."""
    recorded=True
    try:
        db.execute('BEGIN IMMEDIATE')
        now=_effective(store,_mark(db))
        db.execute('INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(CLOCK,canonical({'high_water':now}).decode()))
    except BaseException as error:
        if isinstance(error,(KeyboardInterrupt,SystemExit)):raise
        recorded=False
        try:now=_effective(store,_mark(db))  # a read is allowed beside another writer
        except BaseException as reading:
            if isinstance(reading,(KeyboardInterrupt,SystemExit)):raise
            now=_effective(store,0)
    pending=verified=None
    try:verified=decide(now)
    except AppError as error:pending=error
    if recorded and pending is None:
        try:apply(db,verified)
        except AppError as error:pending=error
        except sqlite3.Error:
            recorded=False  # the receipt write failed: roll back whatever it wrote, nothing is admitted
            try:db.execute('ROLLBACK')
            except sqlite3.Error:pass
    if recorded:
        try:db.execute('COMMIT')
        except BaseException as error:
            if isinstance(error,(KeyboardInterrupt,SystemExit)):raise
            recorded=False
            try:db.execute('ROLLBACK')
            except BaseException as rolling:
                if isinstance(rolling,(KeyboardInterrupt,SystemExit)):raise
    elif db.in_transaction:
        try:db.execute('ROLLBACK')
        except BaseException as rolling:
            if isinstance(rolling,(KeyboardInterrupt,SystemExit)):raise
    if not recorded:
        if pending is None:contract.unrecorded()
        contract.mark_unrecorded(pending)
    return pending


def _transaction(store,hint,decide,apply):
    """The one owner of the write transaction on a judged path: connection entry, schema validation, BEGIN IMMEDIATE,
    COMMIT, ROLLBACK and connection exit. The connection's own commit-on-exit is never used. Any storage failure is
    normalized: a temporally refused read keeps its code with closure_recorded=False, an otherwise admissible one is
    worker_evidence_clock_unrecorded. Returns the pending refusal or None."""
    pending=None;judged=False
    try:
        with store._connection(True) as db:
            _validate_schema(db)
            pending=_judge(store,db,decide,apply);judged=True
    except (sqlite3.Error,OSError):
        if not judged:
            # Entry or schema failed before anything was decided: decide on what the authenticated reading already gives.
            try:decide(_effective(store,hint))
            except AppError as error:pending=error
        if pending is None:contract.unrecorded()
        contract.mark_unrecorded(pending)
    return pending


def _read(path,api):return capture._reference_bytes(str(path),api,contract.MAX_BYTES)


def _ingest(store,envelope_path,request_path,trust_path,pin_path,scratch,api):
    store=_store(store);raw_envelope=_read(envelope_path,api);raw_request=_read(request_path,api)
    attempt='evidence-attempt-'+uuid4().hex;root=str(store.root/attempt)
    storage._create_directory(str(store.root),attempt,api)
    # Even malformed documents keep their original serialization and byte hash.
    storage._create_file(root,'envelope.json',raw_envelope,api)
    storage._create_file(root,'request.json',raw_request,api)
    try:
        envelope=parse_json(raw_envelope);request=parse_json(raw_request)
        policy=parse_json(_read(trust_path,api));pin=parse_json(_read(pin_path,api))
        with native._verifier(pin,scratch,api) as verify:
            # Authenticate first on a read-only reading; a rejected input leaves no clock effect.
            auth_time=_peek(store);auth=contract.verify_envelope(envelope,request,policy,verify,now=auth_time,historical=True).result()
            if auth['tenant_id']!=store.tenant_id:contract.fail('workbench_evidence_identity')
            holder={}
            def decide(now):return contract.verify_envelope(envelope,request,policy,verify,now=now)
            def apply(db,verified):
                result=verified.result();binding=contract.received_binding(verified,digest(request))
                result['native_verifier']=verify.metadata
                record={'schema_version':'worker-evidence-received/1','request_sha256':binding['request_sha256'],
                    'bundle_sha256':binding['bundle_sha256'],'envelope_byte_sha256':hashlib.sha256(raw_envelope).hexdigest(),
                    'request_byte_sha256':hashlib.sha256(raw_request).hexdigest(),'attempt':attempt}
                prior=_metadata(db,RECEIVED+binding['request_sha256'])
                if prior is not None:
                    _record(prior)
                    if prior['request_sha256']!=binding['request_sha256']:contract.fail('worker_evidence_index_invalid')
                head=_metadata(db,HEAD+binding['scope'])
                holder['repeated']=contract.admit_received(binding,prior['bundle_sha256'] if prior else None,head)
                if prior is None:db.execute('INSERT INTO metadata VALUES (?,?)',(RECEIVED+binding['request_sha256'],canonical(record).decode()))
                value=canonical({'sequence':binding['sequence'],'event_sha256':binding['event_sha256']}).decode()
                db.execute('INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(HEAD+binding['scope'],value))
                holder['result']=result;holder['record']=record
            # Both indexes and the mark commit together under the existing native storage barriers.
            pending=_transaction(store,auth_time,decide,apply)
            if pending is not None:raise pending
        result,record,repeated=holder['result'],holder['record'],holder['repeated']
        result.update(received_byte_sha256=record['envelope_byte_sha256'],request_byte_sha256=record['request_byte_sha256'],
            stored_attempt=attempt,idempotent=repeated,workbench_profile_enabled=False,platform_qualified=False)
        storage._create_file(root,'result.json',canonical(result),api)
        return result
    except BaseException as error:
        try:storage._create_file(root,'failure.json',canonical({'status':'FAIL','code':getattr(error,'code',type(error).__name__),
            'evidence_preserved':True,'baseline_admissible':False,'automatic_retry_permitted':False}),api)
        except BaseException as recording:
            if isinstance(recording,(KeyboardInterrupt,SystemExit)):raise recording from error
            if hasattr(error,'add_note'):error.add_note('Native received evidence failure recording also failed: '+type(recording).__name__)
        raise


def _reopen(store,request_sha256,trust_path,pin_path,scratch,api,*,historical=False):
    store=_store(store);contract.hashed(request_sha256)
    with store._connection() as db:
        _validate_schema(db);record=_metadata(db,RECEIVED+request_sha256)
    if record is None:contract.fail('worker_evidence_not_stored')
    record=_record(record)
    if record['request_sha256']!=request_sha256:contract.fail('worker_evidence_index_invalid')
    root=store.root/record['attempt'];raw_envelope=_read(root/'envelope.json',api);raw_request=_read(root/'request.json',api)
    if hashlib.sha256(raw_envelope).hexdigest()!=record['envelope_byte_sha256'] or hashlib.sha256(raw_request).hexdigest()!=record['request_byte_sha256']:contract.fail('worker_evidence_stored_bytes_changed')
    envelope=parse_json(raw_envelope);request=parse_json(raw_request)
    if digest(envelope)!=record['bundle_sha256'] or digest(request)!=request_sha256:contract.fail('worker_evidence_stored_bytes_changed')
    policy=parse_json(_read(trust_path,api));pin=parse_json(_read(pin_path,api))
    with native._verifier(pin,scratch,api) as verify:
        holder={}
        def finish(db,verified):
            binding=contract.received_binding(verified,request_sha256)
            if _metadata(db,RECEIVED+request_sha256)!=record:contract.fail('worker_evidence_stored_bytes_changed')
            head=_metadata(db,HEAD+binding['scope'])
            result=contract.stored_result(verified,head)
            if result['tenant_id']!=store.tenant_id:contract.fail('workbench_evidence_identity')
            result['native_verifier']=verify.metadata;holder['result']=result
        if historical:
            verified=contract.verify_envelope(envelope,request,policy,verify,now=int(time.time()),historical=True)
            with store._connection() as db:
                _validate_schema(db);finish(db,verified)
        else:
            # Authenticate on a read-only reading (no clock effect), then judge on the read connection. The write connection (and
            # the two permanent root receipts each one leaves) is opened only to record something: a closed window not yet
            # covered by the mark, or an observed time more than MARK_STEP ahead of it. Within the step the read is admitted on
            # the read connection; the expiry slack that allows is bounded by the step.
            auth_time=_peek(store);auth=contract.verify_envelope(envelope,request,policy,verify,now=auth_time,historical=True).result()
            if auth['tenant_id']!=store.tenant_id:contract.fail('workbench_evidence_identity')
            decide=lambda now:contract.verify_envelope(envelope,request,policy,verify,now=now)
            # The mark, the effective time, the decision and the receipt check are ONE read transaction: a SHARED lock is held
            # from the first read, so a closure writer cannot commit between the decision and the receipt check (the read is
            # serialized before it). The transaction ends before any write connection is opened.
            for attempt_number in (1,2):
                write=False
                try:
                    with store._connection() as db:
                        _validate_schema(db);db.execute('BEGIN')
                        try:
                            mark=_mark(db);now=_effective(store,mark)
                            try:verified=decide(now)
                            except AppError as refusal:
                                if refusal.code not in ('worker_evidence_expired','worker_evidence_stale_snapshot') or mark>=now:raise
                                write=True  # a closure the mark does not yet cover: record it
                            if not write and now-mark>MARK_STEP:write=True
                            if not write:finish(db,verified)
                        finally:
                            if db.in_transaction:db.execute('ROLLBACK')  # nothing was written here
                except AppError as changed:
                    # The native store saw its database change under the read (a writer committed, for example a closure):
                    # the read's judgment is void. Judge once more on the new state, never return the stale one.
                    if changed.code!='windows_workbench_bytes_changed' or attempt_number==2:raise
                    continue
                break
            if write:
                # The judgment is made again inside the write transaction, against the mark read there.
                pending=_transaction(store,auth_time,decide,finish)
                if pending is not None:raise pending
        result=holder['result']
    return result


def ingest_windows_evidence(store_root,envelope_path,request_path,trust_path,pin_path,scratch):
    return _ingest(WindowsWorkbenchStore(store_root),envelope_path,request_path,trust_path,pin_path,scratch,native._NativeAPI())


def reopen_windows_evidence(store_root,request_sha256,trust_path,pin_path,scratch,*,historical=False):
    return _reopen(WindowsWorkbenchStore(store_root),request_sha256,trust_path,pin_path,scratch,native._NativeAPI(),historical=historical)


_COPY_FILES=re.compile(r'(?:store-(?:intent|outcome)-[a-f0-9]{32}\.json|evidence-copy-[a-f0-9]{32}\.json)\Z')
_ATTEMPT=re.compile(r'evidence-attempt-[a-f0-9]{32}\Z')


def _copy_store(store,destination,api):
    """Copy a bounded dedicated evidence store; originals/partial copies remain.

    This is a recoverable logical SQLite image plus every receiver attempt and
    original native storage receipt, not a copy of an obsolete rollback journal.
    Current trust and verifier material must be supplied separately at reopen.
    """
    from . import windows_workbench as win
    store=_store(store);destination=str(PureWindowsPath(destination));capture.wd._components(destination)
    total=0;manifest={};files={};attempt_sets={}
    def retain(name,data):
        nonlocal total
        total+=len(data)
        if total>64*1024*1024:contract.fail('worker_evidence_backup_limit')
        files[name]=data;manifest[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    with capture.wd._pin(str(store.root),api) as directory,capture.wd._pin(str(PureWindowsPath(destination).parent),api) as destination_parent,store._connection() as db:
        source_id=directory._identities[-1]
        if any(all(item[key]==source_id[key] for key in ('volume_serial','file_id')) for item in destination_parent._identities):contract.fail('worker_evidence_backup_overlap')
        _validate_schema(db)
        root=directory._identities[-1]['final_path'];names=api.names(root)
        if type(names) is not list or len(names)!=len(set(names)) or len(names)>2048:contract.fail('worker_evidence_backup_namespace')
        attempt_names=sorted(name for name in names if _ATTEMPT.fullmatch(name))
        receipts=sorted(name for name in names if _COPY_FILES.fullmatch(name))
        if len(attempt_names)>256 or set(names)-set(attempt_names)-set(receipts)-{'observations.sqlite3','observations.sqlite3-journal'}:
            contract.fail('worker_evidence_backup_unsupported_member')
        data=win._image(db);retain('observations.sqlite3',data)
        rows=db.execute("SELECT key,value FROM metadata WHERE key LIKE 'worker_evidence_received:%' OR key LIKE 'worker_evidence_head:%' ORDER BY key LIMIT 1001").fetchall()
        if len(rows)>1000:contract.fail('worker_evidence_backup_limit')
        for name in receipts:retain(name,store._filesystem.read_file(str(store.root),name))
        for name in attempt_names:
            with capture._directory(store.root/name,api) as attempt:
                children=attempt.names()
                attempt_sets[name]=sorted(children)
                if set(children)-{'envelope.json','request.json','result.json','failure.json'}:contract.fail('worker_evidence_backup_unsupported_member')
                for child in sorted(children):retain(name+'/'+child,attempt.read(child,contract.MAX_BYTES))
                attempt.revalidate()
        for key,text in rows:
            if type(text) is not str or len(text.encode())>65536:contract.fail('worker_evidence_index_invalid')
            value=parse_json(text)
            if key.startswith(RECEIVED):
                _record(value)
                if key!=RECEIVED+value['request_sha256']:contract.fail('worker_evidence_index_invalid')
                for name,field in (('envelope.json','envelope_byte_sha256'),('request.json','request_byte_sha256')):
                    entry=manifest.get(value['attempt']+'/'+name)
                    if entry is None or entry['sha256']!=value[field]:contract.fail('worker_evidence_stored_bytes_changed')
                envelope=parse_json(files[value['attempt']+'/envelope.json']);request=parse_json(files[value['attempt']+'/request.json'])
                if digest(envelope)!=value['bundle_sha256'] or digest(request)!=value['request_sha256']:contract.fail('worker_evidence_stored_bytes_changed')
            else:
                contract.hashed(key[len(HEAD):]);contract.shape(value,'sequence event_sha256');contract.number(value['sequence'],1,9007199254740991);contract.hashed(value['event_sha256'])
        # Copy only after the complete original namespace has been admitted.
        store._filesystem.create(destination,data)
        for name in attempt_names:storage._create_directory(destination,name,api)
        for name,raw in files.items():
            if name=='observations.sqlite3':continue
            relative=PureWindowsPath(name);storage._create_file(str(PureWindowsPath(destination)/relative.parent),relative.name,raw,api)
        for name,raw in files.items():
            if name=='observations.sqlite3':continue
            relative=PureWindowsPath(name)
            if store._filesystem.read_file(str(store.root/relative.parent),relative.name)!=raw:contract.fail('worker_evidence_source_changed')
        for name,expected_children in attempt_sets.items():
            with capture._directory(store.root/name,api) as attempt:
                if sorted(attempt.names())!=expected_children:contract.fail('worker_evidence_source_changed')
                attempt.revalidate()
        if sorted(api.names(root))!=sorted(names):contract.fail('worker_evidence_source_changed')
        directory.revalidate();destination_parent.revalidate()
    copied=WindowsWorkbenchStore._open(destination,store.tenant_id,store._filesystem)
    with copied._connection() as db:
        _validate_schema(db)
        if hashlib.sha256(win._image(db)).hexdigest()!=manifest['observations.sqlite3']['sha256']:contract.fail('worker_evidence_backup_readback')
    for name,entry in manifest.items():
        if name=='observations.sqlite3':continue
        relative=PureWindowsPath(name);raw=store._filesystem.read_file(str(PureWindowsPath(destination)/relative.parent),relative.name)
        if len(raw)!=entry['bytes'] or hashlib.sha256(raw).hexdigest()!=entry['sha256']:contract.fail('worker_evidence_backup_readback')
    with capture.wd._pin(destination,api) as destination_pin:
        expected={'observations.sqlite3','observations.sqlite3-journal'}|set(receipts)|set(attempt_names)
        if set(api.names(destination_pin._identities[-1]['final_path']))!=expected:contract.fail('worker_evidence_backup_file_set')
        for name,expected_children in attempt_sets.items():
            with capture._directory(PureWindowsPath(destination)/name,api) as attempt:
                if sorted(attempt.names())!=expected_children:contract.fail('worker_evidence_backup_file_set')
                attempt.revalidate()
        destination_pin.revalidate()
    # Preserve a prior copy receipt as data; each new copy has a unique receipt.
    receipt={'schema_version':'native-worker-evidence-copy/1','source':str(store.root),'destination':destination,'tenant_id':store.tenant_id,
        'files':manifest,'attempt_directories':attempt_names,'current_trust_and_verifier_included':False,
        'sqlite_scope':'Logical rollback-mode SQLite image; new empty PERSIST sidecar, original source sidecar untouched.',
        'received_indexes_and_replay_heads_preserved':True,'failed_attempts_preserved':True,'original_preserved':True,
        'explicit_relink_required':True,'execution_authorized':False,'platform_qualified':False,'workbench_profile_enabled':False}
    receipt_name='evidence-copy-'+uuid4().hex+'.json'
    storage._create_file(destination,receipt_name,canonical(receipt),api)
    return dict(receipt,receipt_file=receipt_name)


def copy_windows_evidence_store(store_root,destination):
    store=WindowsWorkbenchStore(store_root)
    return _copy_store(store,destination,store._filesystem.api)
