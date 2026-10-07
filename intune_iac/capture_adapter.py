"""Bound existing GET-only capture bytes to inert, single-policy observations.

Hashes establish a consistent local capture, not authenticated Graph identity.
This importer performs no network calls and grants no execution authority.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
import hashlib
import math
import os
from pathlib import Path
import re
import stat
from uuid import UUID
from .io import AppError, canonical, digest, parse_json
from . import production

MAX_BYTES=16*1024*1024
KINDS=('policies','settings','assignments')
HASH=re.compile(r'[0-9a-f]{64}')
RAW=re.compile(r'raw/page-[0-9]{6}\.json')


def _fail(code='workbench_capture_invalid'):
    raise AppError(code,'Capture evidence is incomplete, changed, or outside the admitted local import contract.')


def _uuid(value):
    try:
        if not isinstance(value,str) or not UUID(value).int:raise ValueError()
        result=str(UUID(value))
        if value.lower()!=result:raise ValueError()
        return result
    except (ValueError,AttributeError):_fail('workbench_capture_identity')


def _time(value):
    try:
        if type(value) is not str:raise ValueError()
        stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
        if stamp.tzinfo is None:raise ValueError()
        return stamp.timestamp()
    except (ValueError,OverflowError):_fail('workbench_capture_timestamp')


@contextmanager
def _directory(path):
    path=Path(path).absolute()
    if '..' in path.parts:_fail('workbench_capture_path')
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    fd=os.open('/',flags)
    try:
        for part in path.parts[1:]:
            child=os.open(part,flags,dir_fd=fd);os.close(fd);fd=child
        yield path,fd
    except OSError:_fail('workbench_capture_path')
    finally:os.close(fd)


def _read(fd,name,limit=MAX_BYTES):
    descriptor=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    with os.fdopen(descriptor,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>limit:_fail('workbench_capture_file')
        data=stream.read(limit+1);after=os.fstat(stream.fileno())
        if len(data)>limit or len(data)!=before.st_size or (before.st_mtime_ns,before.st_ctime_ns,before.st_size)!=(after.st_mtime_ns,after.st_ctime_ns,after.st_size):_fail('workbench_capture_changed')
    return data


def _sha(data):return hashlib.sha256(data).hexdigest()


def _attempt_chain(receipt, raw_pages, collections, started, finished):
    """Validate retry evidence independently of successful collection pages.

    A skipped raw response is not permission to omit an arbitrary response from
    coverage. Only a bounded declared transient retry can be excluded, and its
    successor must be the same admitted GET, with a completed wait.
    """
    schema = receipt['schema_version']
    if schema == '1.0.0':
        if 'attempts' in receipt or 'cancelled' in receipt or any('attempt_number' in row or 'export_page' in row for row,_ in raw_pages):
            _fail('workbench_capture_retry_binding')
        return raw_pages, {'receipt_schema':schema,'attempt_count':receipt['attempt_count'],'retry_count':None,'attempts':[]}
    limits=receipt['limits']; attempts=receipt.get('attempts')
    def number(value, low, high):
        return type(value) in (int,float) and low <= value <= high and math.isfinite(value)
    if (type(attempts) is not list or len(attempts)!=receipt['attempt_count']
            or type(receipt.get('cancelled')) is not bool
            or type(limits.get('max_attempts_per_page')) is not int or not 1<=limits['max_attempts_per_page']<=10
            or not number(limits.get('max_retry_delay_seconds'),0,30)
            or not number(limits.get('max_elapsed_seconds'),0,120) or limits['max_elapsed_seconds']==0
            or limits.get('request_timeout_seconds')!=20):_fail('workbench_capture_retry_binding')
    keys={'number','kind','owner_id','request_url','method','attempt_in_page','captured_at','http_status','raw_path','error','retry','retry_delay_seconds','retry_delay_source','wait_completed'}
    raw_offset=0; exported=[]; safe=[]; previous={}; expected={}; last_kind=-1; total_delay=0
    for collection,kind in zip(collections,KINDS):
        if kind!='policies':_uuid(collection.get('owner_id'))
        expected[kind]=production.ROOT + ('/'+collection['owner_id']+'/'+kind if kind!='policies' else '')
    for index,event in enumerate(attempts,1):
        if type(event) is not dict or set(event)!=keys or type(event['number']) is not int or event['number']!=index:_fail('workbench_capture_retry_binding')
        kind=event['kind']
        if kind not in KINDS or KINDS.index(kind)<last_kind:_fail('workbench_capture_retry_binding')
        last_kind=KINDS.index(kind);collection=collections[last_kind]
        owner=collection['owner_id'];root=production.ROOT+('/'+owner+'/'+kind if kind!='policies' else '')
        if event['owner_id']!=owner or event['method']!='GET' or not production._trusted(event['request_url'],root):_fail('workbench_capture_retry_binding')
        if not started<=_time(event['captured_at'])<=finished:_fail('workbench_capture_timestamp')
        prior=previous.get(kind)
        if prior and prior['retry']:
            if prior['wait_completed'] is not True or event['request_url']!=prior['request_url'] or event['attempt_in_page']!=prior['attempt_in_page']+1:_fail('workbench_capture_retry_binding')
        elif event['request_url']!=expected[kind] or event['attempt_in_page']!=1:_fail('workbench_capture_retry_binding')
        if type(event['attempt_in_page']) is not int or not 1<=event['attempt_in_page']<=limits['max_attempts_per_page']:_fail('workbench_capture_retry_binding')
        if type(event['retry']) is not bool or type(event['wait_completed']) is not bool:_fail('workbench_capture_retry_binding')
        rec=None;parsed={}
        if event['error'] is None:
            if raw_offset>=len(raw_pages):_fail('workbench_capture_retry_binding')
            rec,parsed=raw_pages[raw_offset];raw_offset+=1
            if (type(event['http_status']) is not int or not 100<=event['http_status']<=599
                    or any(event[k]!=rec.get(k) for k in ('kind','owner_id','request_url','method','captured_at','http_status','raw_path'))
                    or rec.get('attempt_number')!=index or type(rec.get('attempt_number')) is not int
                    or type(rec.get('export_page')) is not bool or rec['export_page']==event['retry']):_fail('workbench_capture_retry_binding')
        elif event['error'] not in ('transport_failed','invalid_transport_response','cancelled') or event['http_status'] is not None or event['raw_path'] is not None:
            _fail('workbench_capture_retry_binding')
        if event['retry']:
            if (event['http_status'] not in (429,502,503,504) and event['error']!='transport_failed'
                    or rec is not None and rec['raw_capture_complete'] is not True
                    or event['attempt_in_page']>=limits['max_attempts_per_page']
                    or not number(event['retry_delay_seconds'],0,limits['max_retry_delay_seconds'])
                    or event['retry_delay_source'] not in ('retry_after_seconds','retry_after_date','backoff')):_fail('workbench_capture_retry_binding')
            total_delay+=event['retry_delay_seconds']
            if total_delay>=limits['max_elapsed_seconds'] or event['error'] is not None and event['retry_delay_source']!='backoff':_fail('workbench_capture_retry_binding')
            if not event['wait_completed'] and collection.get('reason') not in ('cancelled','progress_failed'):_fail('workbench_capture_retry_binding')
        else:
            if event['retry_delay_seconds'] is not None or event['retry_delay_source'] is not None or event['wait_completed'] is not False:_fail('workbench_capture_retry_binding')
            expected[kind]=parsed.get('@odata.nextLink') if event['http_status']==200 else None
            if rec is not None:exported.append((rec,parsed))
        previous[kind]=event
        safe.append({k:event[k] for k in ('number','kind','attempt_in_page','http_status','error','retry','retry_delay_seconds','retry_delay_source','wait_completed')})
    if raw_offset!=len(raw_pages):_fail('workbench_capture_retry_binding')
    for kind,event in previous.items():
        collection=collections[KINDS.index(kind)]
        if event['retry'] and collection.get('coverage')=='complete':_fail('workbench_capture_false_complete')
    cancelled=any(c.get('reason')=='cancelled' for c in collections) or any(e['error']=='cancelled' for e in attempts)
    if receipt['cancelled']!=cancelled or cancelled and not any(c.get('reason')=='cancelled' and c.get('coverage')=='partial' for c in collections):_fail('workbench_capture_retry_binding')
    return exported, {'receipt_schema':schema,'attempt_count':len(attempts),'retry_count':sum(e['retry'] for e in attempts),'cancelled':receipt['cancelled'],'attempts':safe}


def load_capture(path,tenant_id):
    """Return a validated in-memory batch; retain raw incomplete/mapping evidence.

    The current mapping profile remains production.normalize's narrow profile.
    Unknown mapping data is retained for inspection and never becomes desired
    state. A capture contains one selected policy, never a full-estate claim.
    """
    tenant_id=_uuid(tenant_id)
    try:
        with _directory(path) as (root,fd):
            expected_names={'export.json','context.json','capture-receipt.json','raw'}
            if set(os.listdir(fd))!=expected_names:_fail('workbench_capture_file_set')
            raw_documents={name:_read(fd,name) for name in sorted(expected_names-{'raw'})}
            if sum(map(len,raw_documents.values()))>MAX_BYTES:_fail('workbench_capture_limit')
            source=parse_json(raw_documents['export.json']);context=parse_json(raw_documents['context.json']);receipt=parse_json(raw_documents['capture-receipt.json'])
            if any(type(v) is not dict for v in (source,context,receipt)):_fail()
            oid=_uuid(receipt.get('selected_policy_id'))
            if any(_uuid(v.get('tenant_id'))!=tenant_id for v in (source,context,receipt)) or _uuid(context.get('selected_policy_id'))!=oid:_fail('workbench_capture_identity')
            if any(v.get('cloud')!='public' for v in (source,context,receipt)):_fail('workbench_capture_identity')
            if (source.get('schema_version')!='1.0.0' or context.get('schema_version')!='1.0.0' or receipt.get('schema_version') not in ('1.0.0','1.1.0')
                or source.get('exporter')!=production.EXPORTER or receipt.get('adapter')!=production.EXPORTER
                or source.get('synthetic') is not False or context.get('source_is_synthetic') is not False
                or context.get('authorization')!='emit_only' or receipt.get('api_version')!='beta'
                or receipt.get('tenant_assurance')!='caller_asserted'
                or receipt.get('target_assurance')!='proposed_reference_labels_only'
                or any(receipt.get(k) is not False for k in ('source_authenticity_verified','provider_qualified','execution_authorized'))):_fail('workbench_capture_assurance')
            if source.get('references')!=[] or source.get('ownership')!=[]:_fail('workbench_capture_assurance')
            for name,key in (('export.json','export_byte_sha256'),('context.json','context_byte_sha256')):
                if receipt.get(key)!=_sha(raw_documents[name]):_fail('workbench_capture_digest')
            started=_time(receipt.get('started_at'));observed_at=_time(receipt.get('finished_at'))
            if observed_at<started or _time(source.get('captured_at'))!=started:_fail('workbench_capture_timestamp')
            collections=source.get('collections');pages=receipt.get('pages')
            if type(collections) is not list or len(collections)!=3 or type(pages) is not list or len(pages)>10000:_fail()
            if [c.get('kind') for c in collections if type(c) is dict]!=list(KINDS):_fail('workbench_capture_collection_set')
            attempts=receipt.get('attempt_count');limits=receipt.get('limits')
            if type(limits) is not dict or type(attempts) is not int or not len(pages)<=attempts<=10000:_fail()
            if type(limits.get('max_pages')) is not int or not max(1,attempts)<=limits['max_pages']<=10000:_fail()
            if limits.get('max_page_bytes')!=4*1024*1024 or limits.get('max_total_bytes')!=8*1024*1024:_fail('workbench_capture_limit')
            rawfd=os.open('raw',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            try:
                expected_raw={f'page-{index:06d}.json' for index in range(len(pages))}
                if set(os.listdir(rawfd))!=expected_raw:_fail('workbench_capture_file_set')
                raw_pages=[];raw_total=0
                for index,row in enumerate(pages):
                    if type(row) is not dict or row.get('raw_path')!=f'raw/page-{index:06d}.json':_fail('workbench_capture_path')
                    data=_read(rawfd,f'page-{index:06d}.json',4*1024*1024+1);raw_total+=len(data)
                    if raw_total>8*1024*1024 or type(row.get('source_bytes')) is not int or len(data)!=row['source_bytes'] or row.get('source_byte_sha256')!=_sha(data):_fail('workbench_capture_digest')
                    if type(row.get('raw_capture_complete')) is not bool:_fail()
                    parsed={}
                    if row['raw_capture_complete']:
                        if len(data)>4*1024*1024:_fail('workbench_capture_limit')
                        try:
                            value=parse_json(data)
                            if type(value) is dict:parsed=value
                        except AppError:pass
                    raw_pages.append((row,parsed))
            finally:os.close(rawfd)
            artifacts={name:{'path':str(root/name),'bytes':len(data),'sha256':_sha(data)} for name,data in raw_documents.items()}
            artifacts['raw_pages']=[{'path':str(root/r['raw_path']),'bytes':r['source_bytes'],'sha256':r['source_byte_sha256']} for r,_ in raw_pages]
            raw_pages,capture_attempts=_attempt_chain(receipt,raw_pages,collections,started,observed_at)
            rows={};coverage=[];offset=0
            for collection,kind in zip(collections,KINDS):
                owner=None if kind=='policies' else oid
                source_owner=collection.get('owner_id')
                if (source_owner is not None if owner is None else _uuid(source_owner)!=owner):_fail('workbench_capture_identity')
                declared=collection.get('coverage');reason=collection.get('reason');items=collection.get('pages')
                if reason is not None and (type(reason) is not str or len(reason)>128):_fail()
                if declared not in ('complete','partial','access_denied','not_observed') or type(items) is not list:_fail()
                if declared=='complete' and (reason is not None or not items):_fail('workbench_capture_false_complete')
                expected=production.ROOT+(('/'+source_owner+'/'+kind) if owner else '')
                route=expected;seen=set();ids=set();records=[];counts=[];complete=bool(items)
                for page in items:
                    if offset>=len(raw_pages) or type(page) is not dict:_fail('workbench_capture_page_binding')
                    rec,parsed=raw_pages[offset];offset+=1
                    if any(page.get(k)!=rec.get(k) for k in ('request_url','method','http_status','captured_at')) or canonical(page.get('body'))!=canonical(parsed):_fail('workbench_capture_page_binding')
                    if rec.get('kind')!=kind or rec.get('owner_id')!=source_owner or rec.get('method')!='GET' or type(rec.get('http_status')) is not int:_fail('workbench_capture_page_binding')
                    url=rec['request_url'];stamp=_time(rec.get('captured_at'))
                    if not started<=stamp<=observed_at or url!=expected or url in seen or not production._trusted(url,route):_fail('workbench_capture_page_binding')
                    seen.add(url)
                    ok=rec['raw_capture_complete'] and rec['http_status']==200 and type(parsed.get('value')) is list and 'error' not in parsed
                    if not ok:complete=False
                    else:
                        if set(parsed)-{'value','@odata.context','@odata.count','@odata.nextLink'}:complete=False
                        if '@odata.count' in parsed:
                            count=parsed['@odata.count']
                            if type(count) is not int or count<0:complete=False
                            else:counts.append(count)
                        for value in parsed['value']:
                            if type(value) is not dict:complete=False;continue
                            rid=value.get('id')
                            if type(rid) is not str or not rid:complete=False;continue
                            comparison=rid.lower() if kind!='settings' else rid
                            if comparison in ids:complete=False
                            ids.add(comparison);records.append(value)
                    expected=parsed.get('@odata.nextLink')
                    if '@odata.nextLink' in parsed and (type(expected) is not str or not expected or not production._trusted(expected,route)):complete=False
                complete=complete and expected is None and all(c==len(records) for c in counts)
                if kind=='policies' and len([r for r in records if str(r.get('id','')).lower()==oid])!=1:complete=False
                if declared=='complete' and not complete:_fail('workbench_capture_false_complete')
                rows[kind]=records
                coverage.append({'kind':kind,'owner_id':owner,'coverage':declared,'reason':reason,'page_count':len(items)})
            if offset!=len(raw_pages):_fail('workbench_capture_page_binding')
            # The raw record is kept even if the existing narrow mapper rejects
            # a setting value/type. No new provider mapping is inferred here.
            selected=[r for r in rows['policies'] if str(r.get('id','')).lower()==oid]
            raw_observed={'policy':selected[0] if len(selected)==1 else None,'settings':rows['settings'],'assignments':rows['assignments']}
            configuration=None;blockers=[]
            try:
                mapped=production.normalize(source,context);configuration=mapped['configuration'];blockers=mapped['blockers']
            except (AppError,KeyError,TypeError,ValueError) as error:
                blockers=[{'code':getattr(error,'code','capture_mapping_unsupported')}]
            status='complete'
            if any(c['coverage']=='access_denied' for c in coverage):status='denied'
            elif any(c['coverage']!='complete' for c in coverage):status='partial'
            elif configuration is None:status='unsupported'
            if status!='complete':configuration=None
            capture_sha=digest({'documents':{k:v['sha256'] for k,v in artifacts.items() if k!='raw_pages'},'raw_pages':[r['sha256'] for r in artifacts['raw_pages']]})
            return {'tenant_id':tenant_id,'object_id':oid,'observed_at':observed_at,'status':status,
                    'collections':coverage,'body':configuration,'scope':{'kind':'policy','object_ids':[oid]},
                    'capture_sha256':capture_sha,'source':{'evidence_class':'graph_capture_unverified',
                    'tenant_assurance':'caller_asserted','source_authenticity_verified':False,'provider_qualified':False,
                    'execution_authorized':False,'adapter':production.EXPORTER,'artifacts':artifacts,
                    'capture_sha256':capture_sha,'capture_attempts':capture_attempts,
                    'mapping_blockers':blockers,'raw_observed':raw_observed}}
    except OSError:_fail('workbench_capture_file')
