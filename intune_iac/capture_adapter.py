"""Bound existing GET-only capture bytes to inert, single-policy observations.

Hashes establish a consistent local capture, not authenticated Graph identity.
This importer performs no network calls and grants no execution authority.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
import hashlib
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
            if (source.get('schema_version')!='1.0.0' or context.get('schema_version')!='1.0.0' or receipt.get('schema_version')!='1.0.0'
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
                    'capture_sha256':capture_sha,'mapping_blockers':blockers,'raw_observed':raw_observed}}
    except OSError:_fail('workbench_capture_file')
