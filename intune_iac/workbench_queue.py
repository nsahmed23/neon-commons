"""Immutable, versioned maintenance-review annotations; never execution approval."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json,math,re,time
from pathlib import Path
from uuid import UUID
from .io import AppError,canonical,digest,parse_json
from .workbench_provenance import _read

COMMANDS=frozenset({'queue-amend','queue-review','queue-review-history','queue-review-template'})
FINDINGS=frozenset({'observation_stale','collection_incomplete','reporting_incomplete','ownership_unknown','ownership_conflicting_claims','ownership_stale','ownership_unclaimed','ownership_elsewhere','no_complete_observations'})
SCHEMA='workbench-queue-review-input/1'
RECORD_SCHEMA='workbench-queue-review/1'
_FIELDS={'schema_version','tenant_id','object_id','finding','owner','rationale','review_due','exception_expiry','linked_proposals'}
_HASH=re.compile(r'[0-9a-f]{64}\Z')


def _fail(code='workbench_queue_invalid'):
    raise AppError(code,'Queue review metadata is invalid, stale, unbound or outside the bounded local annotation profile.')


def _text(value,limit):
    if type(value) is not str or not 0<len(value)<=limit or any(ord(c)<32 or 127<=ord(c)<160 for c in value):_fail()
    return value


def _identity(value):
    try:
        if type(value) is not str or str(UUID(value))!=value or not UUID(value).int:_fail('workbench_queue_identity')
    except (ValueError,TypeError,AttributeError):_fail('workbench_queue_identity')
    return value


def _target(tenant,object_id,finding):
    _identity(tenant)
    if object_id is not None:_identity(object_id)
    if type(finding) is not str or finding not in FINDINGS:_fail('workbench_queue_finding')
    if (object_id is None)!=(finding=='no_complete_observations'):_fail('workbench_queue_target')
    return digest({'tenant_id':tenant,'object_id':object_id,'finding':finding})


def _date(value):
    if value is None:return None
    if type(value) is not str or len(value)>64:_fail('workbench_queue_date')
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None or parsed.timestamp()<0:_fail('workbench_queue_date')
        return parsed.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
    except (ValueError,OverflowError,TypeError):_fail('workbench_queue_date')


def _stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


def _rows(store,object_id=None):
    # The existing API fails on more than 1000 rows, never silently truncates.
    return [r for r in store.artifacts(kind='queue_review',object_id=object_id) if r['object_id']==object_id] if object_id is not None else store.artifacts(kind='queue_review')


def _chain(store,object_id,finding,rows=None):
    key=_target(store.tenant_id,object_id,finding)
    selected=[r for r in (_rows(store,object_id) if rows is None else rows) if r['data'].get('queue_key')==key]
    prior=None;version=0
    for row in selected:
        data=row['data'];version+=1
        if (data.get('schema_version')!=RECORD_SCHEMA or data.get('tenant_id')!=store.tenant_id or row['object_id']!=object_id
            or data.get('object_id')!=object_id or data.get('finding')!=finding or type(data.get('version')) is not int or data.get('version')!=version
            or data.get('previous_artifact_id')!=prior or data.get('execution_authorized') is not False
            or data.get('cloud_authority') is not False or data.get('exception_authorized') is not False):_fail('workbench_queue_chain_changed')
        if data.get('owner') is not None:_text(data['owner'],256)
        _text(data.get('rationale'),8192)
        if 'review_due' not in data or 'exception_expiry' not in data:_fail('workbench_queue_chain_changed')
        if _date(data['review_due'])!=data['review_due'] or _date(data['exception_expiry'])!=data['exception_expiry']:_fail('workbench_queue_chain_changed')
        if type(data.get('linked_proposals')) is not list or len(data['linked_proposals'])>32:_fail('workbench_queue_chain_changed')
        prior=row['artifact_id']
    return key,selected


def _links(store,object_id,links):
    if type(links) is not list or len(links)>32 or (object_id is None and links):_fail('workbench_queue_links')
    seen=set();result=[]
    operations=store.operations(object_id=object_id) if links else []
    for link in links:
        if (type(link) is not dict or set(link)!={'kind','operation_id','approval_digest'} or link['kind']!='maintenance_operation'
            or type(link['approval_digest']) is not str or not _HASH.fullmatch(link['approval_digest'])):_fail('workbench_queue_links')
        _text(link['operation_id'],128)
        if link['operation_id'] in seen:_fail('workbench_queue_duplicate_link')
        seen.add(link['operation_id'])
        matching=[r for r in operations if r['operation_id']==link['operation_id'] and r.get('approval_digest')==link['approval_digest']]
        if not matching:_fail('workbench_queue_proposal_missing')
        latest=max(matching,key=lambda row:row['sequence'])
        from .maintenance import _load
        try:root,plan,journal,desired,request=_load(latest['operation_root'])
        except (KeyError,AppError,OSError):_fail('workbench_queue_proposal_missing')
        if (plan['tenant_id']!=store.tenant_id or plan['object_id']!=object_id or plan['operation_id']!=link['operation_id']
            or digest(plan)!=link['approval_digest'] or str(store.root)!=plan['store_root']):_fail('workbench_queue_proposal_identity')
        result.append({**link,'relation':'related_proposal','local_binding_verified_at_recording':True,
                       'operation_root':str(root),'operation_record_sequence':latest['sequence'],
                       'assertion_class':'local_operation_reference','execution_authorized':False})
    return result


def amend(store,path,*,expected_prior):
    if expected_prior is not None and (type(expected_prior) is not str or not _HASH.fullmatch(expected_prior)):_fail('workbench_queue_expected_prior')
    source_path=str(Path(path).absolute());_text(source_path,4096)
    raw=_read(path);doc=parse_json(raw)
    if type(doc) is not dict or set(doc)!=_FIELDS or doc['schema_version']!=SCHEMA:_fail('workbench_queue_shape')
    if doc['tenant_id']!=store.tenant_id:_fail('workbench_wrong_tenant')
    key,chain=_chain(store,doc['object_id'],doc['finding'])
    previous=chain[-1]['artifact_id'] if chain else None
    if previous!=expected_prior:_fail('workbench_queue_conflict')
    if doc['owner'] is not None:_text(doc['owner'],256)
    _text(doc['rationale'],8192)
    review_due=_date(doc['review_due']);expiry=_date(doc['exception_expiry'])
    if expiry is not None and (review_due is None or _stamp(review_due)>_stamp(expiry)):_fail('workbench_queue_date_order')
    links=_links(store,doc['object_id'],doc['linked_proposals'])
    data={'schema_version':RECORD_SCHEMA,'tenant_id':store.tenant_id,'object_id':doc['object_id'],'finding':doc['finding'],
          'queue_key':key,'version':len(chain)+1,'previous_artifact_id':expected_prior,'owner':doc['owner'],
          'owner_assertion':'organization_annotation_unverified' if doc['owner'] else 'unknown','rationale':doc['rationale'],
          'review_due':review_due,'exception_expiry':expiry,'linked_proposals':links,
          'source':{'path':source_path,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},
          'recorded_by':'local_caller_identity_not_authenticated','evidence_class':'local_review_annotation',
          'exception_authorized':False,'cloud_authority':False,'execution_authorized':False,'automatic_remediation':False}
    # The store rechecks expected_prior under BEGIN IMMEDIATE. The earlier read
    # only constructs the proposed next version; it is not the concurrency gate.
    return store.record_artifact('queue_review',doc['object_id'],data,expected_prior=expected_prior)


def template(store,object_id,finding,output):
    """Write the review form for one finding with its identities filled in; never overwrite a file.

    The rationale is left empty, so recording refuses the form until a person writes one.
    """
    key,chain=_chain(store,object_id,finding)
    path=Path(output).absolute()
    if path.exists() or path.is_symlink() or not path.parent.is_dir():_fail('workbench_queue_fresh_output_required')
    form={'schema_version':SCHEMA,'tenant_id':store.tenant_id,'object_id':object_id,'finding':finding,'owner':None,
          'rationale':'','review_due':None,'exception_expiry':None,'linked_proposals':[]}
    with open(path,'x',encoding='utf-8',newline='\n') as handle:
        handle.write(json.dumps(form,indent=1,sort_keys=True)+'\n')
    return {'status':'review_form_written','path':str(path),'tenant_id':store.tenant_id,'object_id':object_id,
            'finding':finding,'queue_key':key,'expected_prior':chain[-1]['artifact_id'] if chain else None,
            'cloud_authority':False,'execution_authorized':False,'exception_authorized':False}


def current(store,object_id,finding,*,now=None,_records=None):
    key,chain=_chain(store,object_id,finding,_records)
    if not chain:return {'status':'unknown','queue_key':key,'tenant_id':store.tenant_id,'object_id':object_id,'finding':finding,
                          'reason':'review_not_recorded','cloud_authority':False,'execution_authorized':False,'exception_authorized':False}
    now=time.time() if now is None else now
    if type(now) not in (int,float) or not math.isfinite(now) or now<0:_fail('workbench_queue_date')
    row=chain[-1];data=row['data']
    return {**data,'status':'recorded','artifact_id':row['artifact_id'],'recorded_at':row['recorded_at'],
            'review_overdue':None if data['review_due'] is None else now>_stamp(data['review_due']),
            'exception_expired':None if data['exception_expiry'] is None else now>_stamp(data['exception_expiry']),
            'evaluated_at':now,'annotation_only':True,'finding_resolution_established':False,
            'limitations':['Owner/review/exception metadata is a local unverified annotation, not organizational approval.',
                           'Proposal identity was verified at recording; linking does not approve, execute, extend expiry or suppress findings.',
                           'Same-user local history is not an independently protected audit anchor.']}


def history(store,object_id,finding):
    key,chain=_chain(store,object_id,finding)
    return {'schema_version':'workbench-queue-history/1','tenant_id':store.tenant_id,'object_id':object_id,'finding':finding,
            'queue_key':key,'amendments':chain,'immutable_appends':True,'cloud_authority':False,'execution_authorized':False}


def decorate_findings(store,findings,*,now=None):
    records=_rows(store);result=[]
    for finding in findings:
        row=dict(finding);review=current(store,row['object_id'],row['finding'],now=now,_records=records)
        row['review_record']=review
        if review['status']=='recorded':
            for key in ('owner','owner_assertion','review_due','exception_expiry','review_overdue','exception_expired','exception_authorized','linked_proposals'):
                row[key]=review[key]
            row['review_rationale']=review['rationale']
        result.append(row)
    return result


def add_parser(sub):
    p=sub.add_parser('queue-amend',help='Append inert review metadata with an exact expected prior artifact')
    p.add_argument('--root',required=True);p.add_argument('--input',required=True);p.add_argument('--expected-prior',required=True)
    p=sub.add_parser('queue-review-template',help='Write the review form for one finding; never overwrites a file')
    for name in ('root','finding','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--object')
    for name in ('queue-review','queue-review-history'):
        p=sub.add_parser(name,help='Inspect current or historical maintenance review annotations')
        p.add_argument('--root',required=True);p.add_argument('--object');p.add_argument('--finding',required=True,choices=sorted(FINDINGS))


def command(args):
    from .workbench_store import WorkbenchStore
    store=WorkbenchStore(args.root)
    if args.workbench_command=='queue-amend':return amend(store,args.input,expected_prior=None if args.expected_prior=='none' else args.expected_prior)
    if args.workbench_command=='queue-review':return current(store,args.object,args.finding)
    if args.workbench_command=='queue-review-history':return history(store,args.object,args.finding)
    if args.workbench_command=='queue-review-template':return template(store,args.object,args.finding,args.output)
    _fail('workbench_queue_command')
