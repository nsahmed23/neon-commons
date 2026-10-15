"""Four evidence-scoped views over existing repository, store and plan engines.

Repository and imported ownership/refresh records are assertions with exact
source bytes, never cloud authority. Only reconstructed local execution and
readback may establish a local deployment baseline. External worker integration
must add an independently validated capability, not a caller 'verified' flag.
"""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import difflib
import hashlib
import math
import os
from pathlib import Path
import re
import time
from uuid import UUID

from .io import AppError, canonical, digest, parse_json, write_json, sync_directory
from .repository import resolve_component, public_resolution, discover_repository
from .workbench_provenance import _read
from . import workbench_semantics as semantics

COMMANDS=frozenset({'repository-entry','repository-import','repository-status','repository-refresh','propose-from-intent','ownership-scan','ownership-import','provider-refresh-import','deployment-import','deployment-record','service-link','evidence-link','evidence-history','adoption-link','adoption-history','views','source-acceptance-propose','field-semantics'})
SCOPE_FIELDS=frozenset({'repository','stack','component','backend'})
MAX_OBJECTS=1000
MAX_ESTATE_ARTIFACTS=10000
MAX_ESTATE_BYTES=128*1024*1024
OWNERSHIP_FILTERS=('owned_here','owned_elsewhere','conflicting_claims','no_ownership_found_in_declared_scope','unknown')
COVERAGE_FILTERS=('complete_fresh','stale_or_incomplete','unknown')
HEALTH_FILTERS=('fresh_failure','fresh_success','reporting_incomplete','unknown')


def _fail(code):raise AppError(code,'Workbench evidence is missing, changed, unsupported or outside the declared comparison scope.')


def _identity(value):
    try:
        if type(value) is not str or str(UUID(value))!=value:_fail('workbench_view_identity')
    except (ValueError,TypeError,AttributeError):_fail('workbench_view_identity')
    return value


def _text(value,maximum=4096):
    if type(value) is not str or not 1<=len(value)<=maximum or any(ord(c)<32 or ord(c)==127 for c in value):_fail('workbench_view_text')
    return value


def _scope(value):
    if type(value) is not dict or set(value)!=SCOPE_FIELDS:_fail('workbench_view_scope')
    return {key:_text(value[key]) for key in sorted(SCOPE_FIELDS)}


def _time(value):
    if isinstance(value,str):
        try:
            dt=datetime.fromisoformat(value.replace('Z','+00:00'))
            if dt.tzinfo is None:raise ValueError()
            value=dt.timestamp()
        except ValueError:_fail('workbench_view_time')
    if type(value) not in (float,int) or not math.isfinite(value) or value<0:_fail('workbench_view_time')
    return float(value)


def _fresh(stamp,age,now,effective=None,hold=()):
    """Within its age at the effective time and not stamped ahead of the raw wall `now`; never under a clock hold,
    where the age is not established (the same judgement store.inspect makes). With no effective time, `now` is both."""
    if hold or not (type(age) in (int,float) and math.isfinite(age) and 0<age<=86400):return False
    stamp=_time(stamp);effective=now if effective is None else effective
    return 0<=now-stamp and effective-stamp<=age


def _reading(store,now):
    """(raw wall, effective time, clock reasons) for one views call. Without an explicit now it is the reading
    store.inspect would make (read-only: nothing is recorded); an explicit now is judged as given."""
    if now is None:return store._clock_reading(bind=False)
    now=_time(now);return now,now,()


def _load(path):
    raw=_read(path);return parse_json(raw),{'path':str(Path(path).absolute()),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def _pointer(value,pointer):
    if type(pointer) is not str or not pointer.startswith('/') or len(pointer)>4096:_fail('workbench_view_pointer')
    current=value
    try:
        for raw in pointer.split('/')[1:]:
            if re.search(r'~(?![01])',raw):_fail('workbench_view_pointer')
            token=raw.replace('~1','/').replace('~0','~')
            if isinstance(current,list):
                if not re.fullmatch('0|[1-9][0-9]*',token):_fail('workbench_view_pointer')
                current=current[int(token)]
            elif type(current) is dict:current=current[token]
            else:_fail('workbench_view_pointer')
    except (KeyError,IndexError,ValueError,TypeError):_fail('workbench_view_pointer')
    return current


def _set_pointer(value,pointer,replacement):
    parent,_,leaf=pointer.rpartition('/')
    target=value if not parent else _pointer(value,parent)
    token=leaf.replace('~1','/').replace('~0','~')
    if isinstance(target,list):target[int(token)]=copy.deepcopy(replacement)
    elif type(target) is dict and token in target:target[token]=copy.deepcopy(replacement)
    else:_fail('workbench_source_acceptance_origin')


def _rows(store,kind):return store.artifacts(kind=kind)


def _latest(rows):return max(rows,key=lambda row:row['sequence']) if rows else None


def _intents(store,object_id=None,scope=None):
    return [r for r in _rows(store,'repository_intent') if (object_id is None or r['data']['target_object_id']==object_id)
            and (scope is None or r['data']['scope']==scope)]


def _refuse_secret_values(value):
    """Generation never writes secret values (it keeps them in the restricted original), so one in the stack was
    written by hand; it is refused before anything is recorded or shown, and the error never echoes it."""
    from reference.core import SECRET_KEYS
    if isinstance(value,dict):
        secret_type='SecretSettingValue' in str(value.get('@odata.type',''))
        for key,item in value.items():
            if str(key).lower().replace('_','') in SECRET_KEYS or (secret_type and key=='value'):
                raise AppError('workbench_repository_secret_value','The desired policy in the repository holds a secret value '
                    '(a secret setting or a credential-named field). Secret values are never recorded or shown; keep them out '
                    'of the repository and manage them outside the workbench.')
            _refuse_secret_values(item)
    elif isinstance(value,list):
        for item in value:_refuse_secret_values(item)


def import_repository(store,repo,stack,component,object_id,pointer,revision,backend,resource_address,*,git_executable=None,git_sha256=None):
    """Read effective policy from actual supported literal Atmos source files."""
    from .windows_workbench import WindowsWorkbenchStore
    if type(store) is WindowsWorkbenchStore:
        from .windows_source import import_repository as native_import
        return native_import(store,repo,stack,component,object_id,pointer,revision,backend,resource_address,
            git_executable=git_executable,git_sha256=git_sha256)
    _identity(object_id)
    if type(revision) is not str or not re.fullmatch('[0-9a-f]{40}',revision):_fail('workbench_repository_revision')
    report=resolve_component(repo,_text(stack),_text(component))
    if report.get('status')!='resolved' or report.get('abstract') or not report.get('implementation_exists'):_fail('workbench_repository_unresolved')
    body=copy.deepcopy(_pointer(report['effective'],pointer));_refuse_secret_values(body);analysis=semantics.analyze(body)
    # Capture every selected source hash again after resolution; a racing edit
    # cannot silently turn a mixed snapshot into one revision claim.
    root=Path(report['root'])
    for item in report['sources']:
        if hashlib.sha256(_read(root/item['path'])).hexdigest()!=item['sha256']:_fail('workbench_repository_changed')
    revision_evidence=None
    if (git_executable is None)!=(git_sha256 is None):_fail('workbench_git_pin_required')
    if git_executable is not None:
        from .workbench_revision import verify_revision
        revision_evidence=verify_revision(root,revision,report['sources'],git_executable=git_executable,git_sha256=git_sha256)
    scope=_scope({'repository':str(root),'stack':stack,'component':component,'backend':backend})
    data=_repository_intent(store,object_id,scope,revision,resource_address,pointer,body,report,analysis,revision_evidence)
    from .workbench_repository import consumer_contract
    data['consumer']=consumer_contract(report,pointer,store.tenant_id,object_id)
    # Global record permits repository-only objects absent from discovery/state.
    return store.record_artifact('repository_intent',None,data)


def _repository_intent(store,object_id,scope,revision,resource_address,pointer,body,report,analysis,revision_evidence=None):
    data={'schema_version':'workbench-repository-intent/1','tenant_id':store.tenant_id,'target_object_id':object_id,
          'scope':scope,'source_revision':revision,'revision_authenticated':False,'revision_assurance':'caller_asserted_revision_actual_working_source_hashes',
          'revision_evidence':revision_evidence,'revision_content_verified':bool(revision_evidence and revision_evidence['working_sources_match_revision']),
          'resource_address':_text(resource_address),'effective_pointer':pointer,'desired':body,
          'resolution':public_resolution(report),'semantics':analysis,'collected_at':time.time(),
          'evidence_class':'local_literal_repository_read','cloud_authority':False,'execution_authorized':False}
    return data



def import_ownership(store,path):
    document,source=_load(path)
    required={'schema_version','tenant_id','max_age_seconds','declared_scopes','sources'}
    if type(document) is not dict or set(document)!=required or document['schema_version']!='workbench-ownership-index/1' or document['tenant_id']!=store.tenant_id:_fail('workbench_ownership_shape')
    age=document['max_age_seconds']
    if type(age) not in (int,float) or not math.isfinite(age) or not 0<age<=86400:_fail('workbench_ownership_age')
    declared=document['declared_scopes'];sources=document['sources']
    if type(declared) is not list or not 1<=len(declared)<=100 or type(sources) is not list or len(sources)>100:_fail('workbench_ownership_scope')
    scopes=[_scope(v) for v in declared]
    if len({digest(s) for s in scopes})!=len(scopes):_fail('workbench_ownership_duplicate_scope')
    seen=set();count=0
    for row in sources:
        if type(row) is not dict or set(row)!={'scope','coverage','observed_at','claims'}:_fail('workbench_ownership_shape')
        scope=_scope(row['scope']);key=digest(scope)
        if key in seen or scope not in scopes:_fail('workbench_ownership_scope')
        seen.add(key);_time(row['observed_at'])
        if row['coverage'] not in ('complete','partial','denied','unknown') or type(row['claims']) is not list:_fail('workbench_ownership_coverage')
        claims=set()
        for claim in row['claims']:
            count+=1
            if count>10000 or type(claim) is not dict or set(claim)!={'object_id','resource_address','parts'}:_fail('workbench_ownership_claim')
            _identity(claim['object_id']);_text(claim['resource_address']);parts=claim['parts']
            if type(parts) is not list or not parts or any(type(x) is not str for x in parts) or len(set(parts))!=len(parts) or not set(parts)<={'object','assignments'}:_fail('workbench_ownership_claim')
            key=digest(claim)
            if key in claims:_fail('workbench_ownership_duplicate_claim')
            claims.add(key)
    return store.record_artifact('ownership_index',None,{'schema_version':'workbench-ownership-record/1','tenant_id':store.tenant_id,
        'document':document,'source':source,'evidence_class':'declared_ownership_index','external_verification':False,
        'cloud_authority':False,'execution_authorized':False})


def scan_ownership(store,path):
    """Scan actual bounded native state files across every declared scope.

    This records local state-file claims; it does not authenticate remote
    backends/tenants or prove the absence of undeclared/external writers.
    """
    from .production import RESOURCE
    manifest,manifest_source=_load(path)
    if (type(manifest) is not dict or set(manifest)!={'schema_version','tenant_id','max_age_seconds','sources'}
            or manifest['schema_version']!='workbench-ownership-scan/1' or manifest['tenant_id']!=store.tenant_id):_fail('workbench_ownership_scan_shape')
    age=manifest['max_age_seconds'];sources=manifest['sources']
    if type(age) not in (float,int) or not math.isfinite(age) or not 0<age<=86400 or type(sources) is not list or not 1<=len(sources)<=100:_fail('workbench_ownership_scan_bound')
    declared=[];rows=[];evidence=[];total=0
    for spec in sources:
        if type(spec) is not dict or set(spec)!={'scope','state_path'}:_fail('workbench_ownership_scan_shape')
        scope=_scope(spec['scope']);state_path=Path(_text(spec['state_path']))
        if not state_path.is_absolute():_fail('workbench_ownership_scan_path')
        if scope in declared:_fail('workbench_ownership_duplicate_scope')
        declared.append(scope);stamp=time.time();claims=[];issues=[]
        details={'scope':scope,'state_path':str(state_path),'read_at':stamp,'tenant_binding':'caller_declared_scope_only',
                 'backend_authenticated':False,'state_revision':None}
        try:
            state,source=_load(state_path);details['source']=source
            if (type(state) is not dict or state.get('version')!=4 or type(state.get('serial')) is not int or state['serial']<0
                    or type(state.get('lineage')) is not str or not state['lineage'] or type(state.get('resources')) is not list):_fail('workbench_ownership_state_shape')
            details['state_revision']={'lineage':state['lineage'],'serial':state['serial'],'sha256':source['sha256']}
            addresses=set()
            for resource in state['resources']:
                total+=1
                if total>10000:_fail('workbench_ownership_scan_bound')
                if type(resource) is not dict:issues.append('unsupported_resource_shape');continue
                if resource.get('mode')=='data':continue
                if (resource.get('mode')!='managed' or resource.get('type')!=RESOURCE
                        or not re.fullmatch(r'provider\["registry\.terraform\.io/deploymenttheory/microsoft365"\](?:\.[A-Za-z_][A-Za-z0-9_]*)?',str(resource.get('provider')))
                        or type(resource.get('instances')) is not list):issues.append('unsupported_writer_resource');continue
                name=_text(resource.get('name'),256)
                if not re.fullmatch('[A-Za-z_][A-Za-z0-9_-]*',name):issues.append('unsupported_resource_address');continue
                module=resource.get('module','')
                if type(module) is not str or len(module)>2048 or (module and not module.startswith('module.')):issues.append('unsupported_module_address');continue
                address=(module+'.' if module else '')+RESOURCE+'.'+name
                for instance in resource['instances']:
                    total+=1
                    if total>10000:_fail('workbench_ownership_scan_bound')
                    if type(instance) is not dict or type(instance.get('attributes')) is not dict:issues.append('missing_instance_attributes');continue
                    oid=instance['attributes'].get('id')
                    try:_identity(oid)
                    except AppError:issues.append('unresolved_object_identity');continue
                    suffix=''
                    if 'index_key' in instance:
                        index=instance['index_key']
                        if type(index) not in (str,int) or (type(index) is int and index<0):issues.append('unsupported_instance_index');continue
                        suffix='['+canonical(index).decode()+']'
                    full=address+suffix
                    if full in addresses:issues.append('duplicate_resource_address')
                    addresses.add(full)
                    if instance.get('deposed') is not None:issues.append('deposed_instance_requires_review')
                    claims.append({'object_id':oid,'resource_address':full,'parts':['object','assignments']})
            coverage='partial' if issues else 'complete'
        except AppError as exc:
            coverage='unknown';issues.append(exc.code)
        details['issues']=issues;evidence.append(details)
        rows.append({'scope':scope,'coverage':coverage,'observed_at':stamp,'claims':claims})
    document={'schema_version':'workbench-ownership-index/1','tenant_id':store.tenant_id,'max_age_seconds':age,
              'declared_scopes':declared,'sources':rows}
    return store.record_artifact('ownership_index',None,{'schema_version':'workbench-ownership-record/1','tenant_id':store.tenant_id,
        'document':document,'source':manifest_source,'state_evidence':evidence,'evidence_class':'local_native_state_file_scan',
        'external_verification':False,'cloud_authority':False,'execution_authorized':False})


def ownership(store,object_id,scope=None,now=None):
    now,effective,hold=_reading(store,now);row=_latest(_rows(store,'ownership_index'))
    return _ownership_result(row,object_id,scope,now,effective=effective,hold=hold)


def _ownership_result(row,object_id,scope,now,claims_by_id=None,effective=None,hold=()):
    result={'status':'unknown','claims':[],'conflicting_parts':[],'scope':scope,'declared_scope_complete':False,
            'fresh':False,'evidence_class':'declared_ownership_index','execution_authorized':False,'cloud_authority':False}
    if row is None:return result|{'reason':'ownership_index_missing'}
    doc=row['data']['document'];result['artifact_id']=row['artifact_id'];result['declared_scopes']=doc['declared_scopes']
    result['evidence_class']=row['data']['evidence_class'];result['state_evidence']=row['data'].get('state_evidence',[])
    complete=len(doc['sources'])==len(doc['declared_scopes']) and all(s['coverage']=='complete' for s in doc['sources'])
    fresh=all(_fresh(s['observed_at'],doc['max_age_seconds'],now,effective,hold) for s in doc['sources'])
    result.update(declared_scope_complete=complete,fresh=fresh)
    claims=(claims_by_id.get(object_id,[]) if claims_by_id is not None else [dict(c,scope=s['scope'],observed_at=s['observed_at'],coverage=s['coverage']) for s in doc['sources'] for c in s['claims'] if c['object_id']==object_id])
    result['claims']=claims
    conflicts=[part for part in ('object','assignments') if len({digest({'scope':c['scope'],'address':c['resource_address']}) for c in claims if part in c['parts']})>1]
    result['conflicting_parts']=conflicts
    if not fresh or not complete:return result|{'reason':'stale_or_incomplete_declared_scope'}
    if conflicts:result['status']='conflicting_claims'
    elif not claims:result['status']='no_ownership_found_in_declared_scope'
    elif scope is None:result['reason']='selected_scope_required'
    elif scope not in doc['declared_scopes']:result['reason']='selected_scope_not_searched'
    elif any(c['scope']==scope for c in claims):
        own={p for c in claims if c['scope']==scope for p in c['parts']}
        result['status']='owned_here' if own=={'object','assignments'} else 'unknown'
        if own!={'object','assignments'}:result['reason']='object_and_assignment_writer_not_established'
    else:result['status']='owned_elsewhere'
    return result


def import_provider_refresh(store,path):
    doc,source=_load(path)
    required={'schema_version','tenant_id','object_id','state_revision','state_body','refreshed_body','observed_at','max_age_seconds','scope'}
    if type(doc) is not dict or set(doc)!=required or doc['schema_version']!='workbench-provider-refresh/1' or doc['tenant_id']!=store.tenant_id:_fail('workbench_refresh_shape')
    _identity(doc['object_id']);_scope(doc['scope']);_time(doc['observed_at'])
    state=doc['state_revision']
    if type(state) is not dict or set(state)!={'lineage','serial','sha256'} or type(state['serial']) is not int or state['serial']<0 or not re.fullmatch('[0-9a-f]{64}',str(state['sha256'])):_fail('workbench_refresh_state')
    _text(state['lineage'])
    if type(doc['max_age_seconds']) not in (int,float) or not math.isfinite(doc['max_age_seconds']) or not 0<doc['max_age_seconds']<=86400:_fail('workbench_refresh_age')
    for key in ('state_body','refreshed_body'):
        if doc[key] is not None:semantics.analyze(doc[key])
    return store.record_artifact('provider_refresh',None,{'schema_version':'workbench-provider-refresh-record/1','tenant_id':store.tenant_id,
        'document':doc,'source':source,'evidence_class':'caller_asserted_provider_refresh','cloud_authority':False,'execution_authorized':False})


def import_deployment(store,path):
    doc,source=_load(path)
    if type(doc) is not dict or doc.get('schema_version')!='workbench-deployment-claim/1' or doc.get('tenant_id')!=store.tenant_id:_fail('workbench_deployment_claim')
    _identity(doc.get('object_id'))
    return store.record_artifact('deployment_receipt',None,{'schema_version':'workbench-deployment-record/1','tenant_id':store.tenant_id,
        'target_object_id':doc['object_id'],'claim':doc,'source':source,'evidence_class':'caller_asserted_deployment',
        'baseline_admissible':False,'cloud_authority':False,'execution_authorized':False})


def _local_proof(store,operation,intent):
    from . import maintenance,protected
    root,plan,journal,desired,request=maintenance._load(operation)
    if str(store.root)!=plan['store_root'] or store.tenant_id!=plan['tenant_id'] or intent['data']['target_object_id']!=plan['object_id']:_fail('workbench_deployment_identity')
    try:
        cited=maintenance._bound_context(plan)
    except AppError as error:
        if error.code!='maintenance_source_changed':raise
        cited=None  # A changed context file is refused below with workbench_deployment_context_mismatch.
    if isinstance(cited,dict) and isinstance(cited.get('repository_intent_id'),str) and cited['repository_intent_id']!=intent['artifact_id']:
        # Name the intent this operation cites, so the engineer can record it with the right one.
        raise AppError('workbench_deployment_intent_not_cited','This operation cites repository intent %s, not the '
                       'intent given; record the deployment with the intent it cites.'%cited['repository_intent_id'])
    if journal['status'] not in ('succeeded_verified','reconciled') or semantics.compare(intent['data']['desired'],desired)['status']!='equal':_fail('workbench_deployment_unverified')
    context_binding=plan.get('context')
    if type(context_binding) is not dict:_fail('workbench_deployment_context_missing')
    context,context_source=_load(context_binding['path'])
    if context_source['sha256']!=context_binding['sha256'] or context.get('repository_intent_id')!=intent['artifact_id'] or context.get('scope')!=intent['data']['scope'] or context.get('tenant_id')!=store.tenant_id or context.get('cloud')!='public':_fail('workbench_deployment_context_mismatch')
    receipt=protected.read_native_operation(request['operation_id'],root/'engine-receipts')
    if receipt['status']!='succeeded_verified' or digest(receipt['request'])!=digest(request):_fail('workbench_deployment_engine_receipt')
    verified=[e for e in journal['events'] if e['kind']=='verified']
    if len(verified)!=1:_fail('workbench_deployment_unverified')
    matched=[]
    for i,path in enumerate(sorted(root.glob('readback-*.json'))):
        if i>=100:_fail('workbench_deployment_limit')
        rb,_=_load(path)
        if digest(rb)==verified[0].get('readback_sha256'):matched.append((path,rb))
    if len(matched)!=1:_fail('workbench_deployment_readback')
    path,rb=matched[0]
    if (rb.get('operation_id')!=plan['operation_id'] or rb.get('classification')!='desired_state_observed'
            or rb.get('visibility',{}).get('pending') is not False or rb.get('second_plan',{}).get('status')!='no_change'
            or digest(rb.get('observed_estate'))!=digest(plan['desired_estate'])):_fail('workbench_deployment_readback')
    return {'operation_root':str(root),'operation_id':plan['operation_id'],'plan_sha256':digest(plan),
            'engine_request_sha256':digest(request),'engine_receipt_sha256':receipt['receipt_sha256'],
            'journal_sha256':digest({'operation_id':journal['operation_id'],'plan_sha256':journal['plan_sha256'],'events':journal['events'][:verified[0]['sequence']+1]}),'readback_sha256':digest(rb),'readback_path':str(path),
            'desired':copy.deepcopy(desired),'object_id':plan['object_id'],'observed_estate_sha256':digest(rb['observed_estate'])}


def record_local_deployment(store,operation,intent_id):
    # Recording is the last step and one transaction, so any refusal recorded nothing.
    try:
        return _record_local_deployment(store,operation,intent_id)
    except AppError as error:
        error.effects=dict(error.effects or {},deployment_recorded=False)
        raise


def _record_local_deployment(store,operation,intent_id):
    matches=[r for r in _intents(store) if r['artifact_id']==intent_id]
    if len(matches)!=1:_fail('workbench_deployment_intent')
    intent=matches[0];proof=_local_proof(store,operation,intent)
    return store.record_artifact('deployment_receipt',None,{'schema_version':'workbench-deployment-record/1','tenant_id':store.tenant_id,
        'target_object_id':proof['object_id'],'intent_id':intent_id,'scope':intent['data']['scope'],'proof':proof,
        'recorded_at':time.time(),'evidence_class':'verified_local_modeled_deployment','baseline_admissible':True,
        'platform_qualified':False,'cloud_authority':False,'execution_authorized':False},
        # Every refusal above has already passed. The same proof for the same intent is the same deployment, so the store
        # returns the record it holds; recorded_at differs on every call and is not part of that identity.
        once_by=('$.proof.operation_id',proof['operation_id'],('recorded_at',)))


def _deployment(store,object_id,scope,*,_native_reader=None):
    from . import workbench_service_views as service_views, workbench_evidence_views as received_views
    candidates=[r for r in _rows(store,'deployment_receipt') if r['data'].get('target_object_id')==object_id and
        (scope is None or r['data'].get('scope')==scope or r['data'].get('evidence_class') in (service_views.KIND,received_views.KIND))]
    for row in sorted(candidates,key=lambda r:r['sequence'],reverse=True):
        data=row['data']
        if _native_reader is not None and data.get('evidence_class')!=received_views.KIND:
            _native_reader.reject('deployment',row=row)
            continue
        if data.get('evidence_class')==received_views.KIND:
            try:return received_views.deployment(store,row)
            except (AppError,OSError,KeyError,TypeError):continue
        if data.get('evidence_class')==service_views.KIND:
            try:return service_views.deployment(store,row)
            except (AppError,OSError,KeyError):continue
        if data.get('evidence_class')!='verified_local_modeled_deployment':continue
        intents=[r for r in _intents(store,object_id) if r['artifact_id']==data.get('intent_id')]
        if len(intents)!=1:continue
        try:proof=_local_proof(store,data['proof']['operation_root'],intents[0])
        except (AppError,OSError,KeyError):continue
        if digest(proof)!=digest(data['proof']):continue
        return dict(data,artifact_id=row['artifact_id'])
    return None


def _unknown(reason,**extra):return {'status':'unknown','reason':reason,**extra}


def _comparison(left,right,**extra):
    result=semantics.compare(left,right)
    return {key:result[key] for key in ('status','changed_fields','raw_changed','semantics_version')}|extra|{
        'unsupported':[{'side':side,'blockers':result[side]['blockers']} for side in ('left','right') if result[side]['blockers']]}


def _definition_ids(body):
    values=[];pending=[body.get('settings',{})] if type(body) is dict else []
    while pending:
        value=pending.pop()
        if type(value) is dict:
            if type(value.get('settingDefinitionId')) is str:values.append(value['settingDefinitionId'])
            pending.extend(value.values())
        elif type(value) is list:pending.extend(value)
    return values


def _estate_health(row,now,effective=None,hold=()):
    result={'status':'unknown','stage':'execution','evidence_class':'unknown','targeted':None,'reporting':None,
            'successful':None,'failed':None,'unknown':None,'endpoint_health':'unknown','endpoint_outcome':'unknown',
            'rollout_ready':False,'external_execution_verified':False,'cloud_authority':False}
    if row is None:return result
    from .workbench_health import summarize_evidence
    summary=summarize_evidence(row['data']['evidence'],now=now,effective=effective,clock_reasons=hold);stage=summary['stages']['execution']
    # A fresh failure remains discoverable even when other targeted devices
    # have no report. Success requires every targeted device's fresh success.
    status=('fresh_failure' if stage['failed'] else 'fresh_success' if stage['targeted']>0 and
            stage['successful']==stage['targeted'] and not stage['unknown'] else 'reporting_incomplete')
    result.update({key:stage[key] for key in ('targeted','reporting','successful','failed','pending','unknown','reporting_success_percent','targeted_success_percent','stale','partial','conflicting','missing','future','access_denied','membership_conflicts','age_unknown') if key in stage})
    return result|{'status':status,'evidence_class':summary['evidence_class'],'artifact_id':row['artifact_id'],
                  'source_sha256':row['data']['source_sha256'],'as_of':summary['as_of']}


def _estate_views(store,scope,now,limit,offset,query,ownership_filter,coverage_filter,health_filter,effective=None,hold=()):
    if type(limit) is not int or not 1<=limit<=100 or type(offset) is not int or offset<0:_fail('workbench_views_page')
    if type(query) is not str or len(query)>4096 or any(ord(c)<32 or ord(c)==127 for c in query):_fail('workbench_views_query')
    for value,allowed in ((ownership_filter,OWNERSHIP_FILTERS),(coverage_filter,COVERAGE_FILTERS),(health_filter,HEALTH_FILTERS)):
        if value is not None and (type(value) is not str or value not in allowed):_fail('workbench_views_filter')
    observations={};intents={};devices={};own=None;size=0;artifact_count=0
    # Inventory, repository claims, ownership and device evidence are selected
    # within ONE SQLite read snapshot. Filtering must never operate on one
    # already-paginated page, or mix changing pages from concurrent collectors.
    with store._connection() as db,store._query_budget(db) as charge:
        db.execute('BEGIN');attempt,success=store._latest(db)
        inventory,parameters=store._inventory_sql(db,success,attempt,charge)
        sql=inventory+"""SELECT i.*,s.body_json,d.source_json AS pending_source
             FROM inventory i LEFT JOIN snapshots s ON s.snapshot_id=i.snapshot_id
             LEFT JOIN run_details d ON d.run_id=i.attempt_id ORDER BY i.object_id LIMIT :bound"""
        if store.schema_version==1:
            sql=inventory+"""SELECT i.*,s.body_json,NULL AS pending_source FROM inventory i
                 LEFT JOIN snapshots s ON s.snapshot_id=i.snapshot_id ORDER BY i.object_id LIMIT :bound"""
        parameters['bound']=MAX_OBJECTS+1
        for row in db.execute(sql,parameters):
            if len(observations)>=MAX_OBJECTS:_fail('workbench_views_bound')
            raw=row['body_json'];source=row['pending_source'] if row['pending'] else None
            size+=len((raw or '').encode())+len((source or '').encode())
            if size>MAX_ESTATE_BYTES:_fail('workbench_views_bound')
            body=parse_json(raw) if raw is not None else None
            raw_policy=parse_json(source).get('raw_observed',{}).get('policy',{}) if source else {}
            if type(raw_policy) is list:raw_policy=raw_policy[0] if raw_policy else {}
            name=body.get('name') if type(body) is dict else raw_policy.get('name') if type(raw_policy) is dict else None
            fresh=(not row['pending'] and row['attempt_status']=='complete' and _fresh(row['observed_at'],3600,now,effective,hold))
            observations[row['object_id']]={'body':body,'name':name,'snapshot_id':row['snapshot_id'],
                'observed_at':row['observed_at'],'observation':'complete_fresh' if fresh else 'stale_or_incomplete' if body is not None else 'unknown',
                'freshness':'fresh' if fresh else 'stale' if body is not None else 'unknown','evidence_class':row['evidence_class'],
                'pending_observation':bool(row['pending']),'attempt_id':row['attempt_id'],'attempt_status':row['attempt_status']}
        if store.schema_version==2:
            rows=db.execute("SELECT * FROM artifacts WHERE tenant_id=? AND kind IN ('repository_intent','device_evidence','ownership_index') ORDER BY sequence LIMIT ?",(store.tenant_id,MAX_ESTATE_ARTIFACTS+1))
            for rawrow in rows:
                artifact_count+=1
                if artifact_count>MAX_ESTATE_ARTIFACTS:_fail('workbench_views_bound')
                size+=len(rawrow['data_json'].encode())
                if size>MAX_ESTATE_BYTES:_fail('workbench_views_bound')
                row=store._artifact(rawrow);data=row['data']
                if row['kind']=='ownership_index':own=row
                elif row['kind']=='device_evidence':devices[row['object_id']]=row
                elif scope is None or data['scope']==scope:intents[data['target_object_id']]=row
    ids=set(observations)|set(intents)
    if len(ids)>MAX_OBJECTS:_fail('workbench_views_bound')
    claims={}
    if own:
        for source in own['data']['document']['sources']:
            for claim in source['claims']:
                claims.setdefault(claim['object_id'],[]).append(dict(claim,scope=source['scope'],observed_at=source['observed_at'],coverage=source['coverage']))
    match=[];folded=query.casefold();snapshot=[]
    for oid in sorted(ids):
        observed=observations.get(oid,{});intent=intents.get(oid);desired=intent['data']['desired'] if intent else None
        selected_scope=scope or (intent['data']['scope'] if intent else None)
        own_result=_ownership_result(own,oid,selected_scope,now,claims,effective,hold)
        health=_estate_health(devices.get(oid),now,effective,hold)
        coverage=observed.get('observation','unknown')
        name=observed.get('name') or (desired.get('name') if type(desired) is dict else None)
        fields=[oid]+[value for value in (observed.get('name'),desired.get('name') if type(desired) is dict else None) if type(value) is str]
        fields+=_definition_ids(observed.get('body'))+_definition_ids(desired)
        snapshot.append({'object_id':oid,'snapshot_id':observed.get('snapshot_id'),'attempt_id':observed.get('attempt_id'),'attempt_status':observed.get('attempt_status'),'observed_at':observed.get('observed_at'),'repository_intent_id':intent['artifact_id'] if intent else None,
                         'device_evidence_id':devices[oid]['artifact_id'] if oid in devices else None})
        if folded and not any(folded in value.casefold() for value in fields):continue
        if ownership_filter is not None and own_result['status']!=ownership_filter:continue
        if coverage_filter is not None and coverage!=coverage_filter:continue
        if health_filter is not None and health['status']!=health_filter:continue
        # Full state-file/source evidence stays in selected-object inspection;
        # estate summaries expose its exact immutable artifact identifier.
        compact_ownership={key:own_result[key] for key in ('status','fresh','declared_scope_complete','artifact_id','reason','conflicting_parts','evidence_class') if key in own_result}
        match.append({'object_id':oid,'name':name,'scope':selected_scope,'freshness':observed.get('freshness','unknown'),
            'repository_status':'recorded' if intent else 'unknown','observed_status':'recorded' if oid in observations else 'unknown',
            'observed_at':observed.get('observed_at'),'snapshot_id':observed.get('snapshot_id'),
            'pending_observation':observed.get('pending_observation',False),'health':health,
            'coverage':{'observation':coverage,'management':own_result['status'],'ownership':compact_ownership,
                        'discovery_includes_objects_absent_from_state':True,'platform_qualified':False},
            'comparisons':{'status':'not_evaluated','reason':'Select an object for distinct baseline comparisons.'}})
        # A clock hold says which reason holds and what the clock read against the time recorded, as the Inspector's
        # row does; with no hold neither key is present.
        if hold and observed.get('body') is not None:
            match[-1]['freshness_reasons']=list(hold)
            match[-1]['freshness_clock']={'reads':now,'recorded':effective if 'clock_moved_backward' in hold else None}
    selected=match[offset:offset+limit];has_more=offset+len(selected)<len(match)
    result={'schema_version':'workbench-four-views/1','tenant_id':store.tenant_id,'objects':selected,
        'query':query,'filters':{'query':query,'ownership':ownership_filter,'coverage':coverage_filter,'health':health_filter},
        'total_inventory_objects':len(ids),'inventory_scope':'current_or_pending_observations_and_selected_scope_repository_intents',
        'inventory_complete_within_bound':True,'snapshot_sha256':digest({'objects':snapshot,'ownership_index_id':own['artifact_id'] if own else None}),
        'evaluated_at':now,'filter_scope':'full_bounded_inventory_before_pagination','health_filter_stage':'execution',
        'pagination':{'limit':limit,'offset':offset,'total_objects':len(match),'returned_objects':len(selected),
            'has_more':has_more,'next_offset':offset+len(selected) if has_more else None,'complete':offset==0 and len(selected)==len(match),'scope':'page'},
        'bounds':{'inventory_objects':MAX_OBJECTS,'artifact_records':MAX_ESTATE_ARTIFACTS,'decoded_bytes':MAX_ESTATE_BYTES},
        'cloud_authority':False,'execution_authorized':False,'limitations':[
            'Local stored inventory and declared ownership scopes do not prove global tenant discovery or absence of other writers.',
            'Health filters classify imported execution-stage reports; endpoint effectiveness, outcome and rollout approval remain unknown.',
            'Same-user local storage is not a protected audit anchor. Selected-object views verify distinct deployment baselines.']}
    if len(canonical(result))>16*1024*1024:_fail('workbench_views_bound')
    return result


def views(store,object_id=None,*,scope=None,operation=None,intent_id=None,now=None,limit=100,offset=0,
          query='',ownership_filter=None,coverage_filter=None,health_filter=None):
    # One reading for the whole call (see _reading): estate rows, ownership and provider-refresh freshness are judged on
    # it. The selected object's own observation freshness comes from the read model (store.inspect) instead.
    explicit=now is not None
    now,effective,hold=_reading(store,now)
    from .windows_views import _reader_for
    native_reader=_reader_for(store)
    if scope is not None:scope=_scope(scope)
    if object_id is None:
        if operation is not None or intent_id is not None:_fail('workbench_views_object_required')
        result=_estate_views(store,scope,now,limit,offset,query,ownership_filter,coverage_filter,health_filter,effective,hold)
        return native_reader.decorate(result) if native_reader is not None else result
    if query or any(value is not None for value in (ownership_filter,coverage_filter,health_filter)):_fail('workbench_views_filters_estate_only')
    _identity(object_id)
    choices=_intents(store,object_id,scope)
    if intent_id is not None:
        choices=[r for r in choices if r['artifact_id']==intent_id]
        if len(choices)!=1:_fail('workbench_repository_intent_missing')
    intent=_latest(choices);repo=_unknown('repository_intent_missing')
    if intent:
        repo={'status':'recorded',**intent['data'],'object_id':object_id,'artifact_id':intent['artifact_id']}
        if intent['data'].get('schema_version')=='workbench-repository-intent/1':
            # Read-only: compares the recorded intent with a fresh resolution; never re-imports.
            from .workbench_repository import intent_freshness
            repo['freshness']=intent_freshness(intent['data'])
        if scope is None:scope=repo['scope']
    try:observed=store.inspect(object_id);observed=dict(observed,status='recorded')
    except AppError as exc:
        if exc.code!='workbench_object_missing':raise
        observed=_unknown('object_not_collected',object_id=object_id,body=None)
    # Unsupported mapping must not hide complete literal service observations.
    # Preserve the mapped last-good body separately from the latest raw attempt.
    raw_observation=store.raw_capture_observation(object_id)
    if raw_observation is not None:observed['raw_capture_observation']=raw_observation
    coverage_ok=(observed.get('coverage')=='complete' and observed.get('freshness')=='fresh'
        and observed.get('last_attempt',{}).get('status')=='complete'
        # The read model's freshness (above) already carries the effective time and any clock hold; the stamp is
        # recomputed here only for a caller that passed its own now, so that now still decides.
        and (not explicit or _fresh(observed.get('observed_at'),3600,now)))
    deployment=_deployment(store,object_id,scope,_native_reader=native_reader)
    comparisons={name:_unknown('baseline_missing_or_incomplete') for name in ('collector_snapshot_delta','provider_refresh_vs_state','repository_vs_deployment','observed_vs_deployment','repository_vs_observed')}
    if observed.get('body') is not None:
        history=list(reversed(store.recent_history(object_id,limit=2)))
        if coverage_ok and len(history)>=2:
            before,after=history[-2:]
            if all(after.get(key)==observed.get(key) for key in ('snapshot_id','run_id','observed_at')):
                comparisons['collector_snapshot_delta']=_comparison(before['body'],after['body'],
                    baseline={'kind':'prior_collector_snapshot','snapshot_id':before['snapshot_id'],'observed_at':before['observed_at']},
                    current={'snapshot_id':after['snapshot_id'],'observed_at':after['observed_at']},attribution='unknown',change_time='unknown')
            else:
                comparisons['collector_snapshot_delta']=_unknown('history_current_observation_mismatch')
        if intent and coverage_ok:
            comparisons['repository_vs_observed']=_comparison(repo['desired'],observed['body'],classification='desired_observed_difference',drift_established=False)
            from .workbench_diff import field_changes
            # Exact before (observed) and after (repository) values, under the plan's equality.
            comparisons['repository_vs_observed']['field_changes']=field_changes(observed['body'],repo['desired'])
    refresh=_latest([r for r in _rows(store,'provider_refresh') if r['data']['document']['object_id']==object_id and (scope is None or r['data']['document']['scope']==scope)])
    state_present=None
    if refresh:
        doc=refresh['data']['document'];state_present=doc['state_body'] is not None
        if _fresh(doc['observed_at'],doc['max_age_seconds'],now,effective,hold) and state_present and doc['refreshed_body'] is not None:
            comparisons['provider_refresh_vs_state']=_comparison(doc['state_body'],doc['refreshed_body'],
                baseline={'kind':'persisted_state_revision_used',**doc['state_revision']},observed_at=doc['observed_at'],
                evidence_class='caller_asserted_provider_refresh',independently_authenticated=False)
        else:comparisons['provider_refresh_vs_state']=_unknown('state_absent_or_refresh_stale_or_missing',baseline=doc['state_revision'])
    if deployment:
        baseline={'kind':deployment.get('baseline_kind','verified_local_modeled_deployment'),'evidence_class':deployment['evidence_class'],'artifact_id':deployment['artifact_id'],'operation_id':deployment['proof']['operation_id'],
                  'recorded_at':deployment['recorded_at'],'plan_sha256':deployment['proof']['plan_sha256']}
        mapped=deployment.get('normalized_comparison_available',True)
        if not mapped:
            for name in ('repository_vs_deployment','observed_vs_deployment'):
                comparisons[name]=_unknown('deployment_mapping_unsupported',baseline=baseline,raw_observation_available=True)
        if intent and mapped:comparisons['repository_vs_deployment']=_comparison(deployment['proof']['desired'],repo['desired'],baseline=baseline,classification='pending_repository_change')
        if coverage_ok and mapped:comparisons['observed_vs_deployment']=_comparison(deployment['proof']['desired'],observed['body'],baseline=baseline,
                classification='difference_since_verified_deployment' if deployment.get('baseline_kind') else 'difference_since_verified_local_deployment',actor='unknown',live_drift_established=False)
    proposed=_unknown('operation_not_selected')
    if operation is None:
        from . import workbench_service_views as service_views, workbench_evidence_views as received_views
        links=[r for r in _rows(store,'deployment_receipt') if r['data'].get('target_object_id')==object_id and r['data'].get('evidence_class') in (service_views.KIND,received_views.KIND)]
        if links:
            selected_link=max(links,key=lambda r:r['sequence'])
            if native_reader is not None and selected_link['data'].get('evidence_class')!=received_views.KIND:
                proposed=native_reader.reject('proposed_service',row=selected_link)
            else:
                try:proposed=(received_views if selected_link['data'].get('evidence_class')==received_views.KIND else service_views).proposed(store,selected_link)
                except (AppError,OSError,KeyError) as exc:
                    proposed=_unknown('linked_service_unavailable_or_changed',error_code=getattr(exc,'code',type(exc).__name__),link_artifact_id=selected_link['artifact_id'])
    if operation is not None and native_reader is not None:
        proposed=native_reader.reject('proposed_operation')
    elif operation is not None:
        from . import maintenance
        root,plan,journal,desired,request=maintenance._load(operation)
        if plan['object_id']!=object_id or plan['tenant_id']!=store.tenant_id:_fail('workbench_proposed_identity')
        saved=root/'executor/work/saved.tfplan';raw=_read(saved)
        # The existing engine validates the exact saved bytes, configuration and
        # request bindings in its public review route; never trust plan labels.
        review=maintenance.review(root)
        proposed={'status':'recorded','review':review,'operation_id':plan['operation_id'],'desired':desired,
            'saved_plan_sha256':hashlib.sha256(raw).hexdigest(),'target':{'tenant_id':store.tenant_id,'object_id':object_id},
            'scope':scope,'approval_digest':digest(plan),'journal_status':journal['status'],'provider_principal':'not_applicable_local_model',
            'backend_principal':'not_applicable_local_model','unresolved_risks':['Local modeled operation; no platform authority.'],
            'evidence_class':plan['evidence_class']}
    from . import workbench_adoption_views as adoption_views
    adoption_history=adoption_views.history(store,object_id,native_reader=native_reader)
    adoption_links=adoption_views.rows(store,object_id)
    if operation is None and adoption_links and (not links or adoption_links[0]['sequence']>max(r['sequence'] for r in links)):
        proposed=adoption_history['operations'][0]
    own=_ownership_result(_latest(_rows(store,'ownership_index')),object_id,scope,now,effective=effective,hold=hold)
    semantic=semantics.analyze(observed['body']) if observed.get('body') is not None else None
    coverage={'observation':'complete_fresh' if coverage_ok else 'stale_or_incomplete' if observed.get('body') is not None else 'unknown',
        'collections':observed.get('collections',[]),'ownership':own,'management':own['status'],'state_tracked':state_present,
        'discovery_includes_objects_absent_from_state':True,'mapping':'supported_comparison_only' if semantic and not semantic['blockers'] else 'unknown_or_unsupported',
        'mapping_blockers':semantic['blockers'] if semantic else [],'native_provider_lifecycle_qualified':False,'platform_qualified':False}
    if raw_observation is not None:
        coverage.update(latest_capture_status=raw_observation['status'],
            latest_capture_collection_coverage=raw_observation['coverage'],
            latest_capture_mapping_blockers=raw_observation['source'].get('mapping_blockers',[]),
            normalized_mapping_refers_to='retained_normalized_snapshot')
    result={'schema_version':'workbench-four-views/1','tenant_id':store.tenant_id,'object_id':object_id,'scope':scope,
        'repository':repo,'observed':observed,'proposed':proposed,'coverage':coverage,'comparisons':comparisons,
        'adoption_history':adoption_history,
        'deployment':deployment or _unknown('verified_deployment_missing'),'field_semantics':semantics.contract(),
        'cloud_authority':False,'execution_authorized':False,'limitations':['Cooperative same-user evidence is not a protected audit anchor.',
        'Declared ownership and imported refresh/deployment claims are not authenticated external authority.']}
    if native_reader is not None:result=native_reader.decorate(result)
    if len(canonical(result))>16*1024*1024:_fail('workbench_views_bound')
    return result


def _render_source_proposal(raw,origin,old_value,new_value):
    import yaml
    try:document=yaml.safe_load(raw)
    except yaml.YAMLError:_fail('workbench_source_acceptance_yaml')
    # Confirm the origin pointer truly represents the selected effective field.
    if canonical(_pointer(document,origin['pointer']))!=canonical(old_value):_fail('workbench_source_acceptance_merged_field')
    changed=copy.deepcopy(document);_set_pointer(changed,origin['pointer'],new_value)
    rendered=yaml.safe_dump(changed,allow_unicode=False,sort_keys=False).encode()
    if len(rendered)>512*1024:_fail('workbench_source_acceptance_bound')
    return rendered


def _source_impact(root,origin,*,discover=None,resolve=None):
    if discover is None:discover=discover_repository
    if resolve is None:resolve=resolve_component
    discovered=discover(root);impact=[]
    if discovered['status']!='discovered' or len(discovered['stacks'])>100:_fail('workbench_source_acceptance_scope_incomplete')
    for stack in discovered['stacks']:
        if stack['status']!='discovered':_fail('workbench_source_acceptance_scope_incomplete')
        for component in stack['components']:
            if not component['selectable']:continue
            resolved=resolve(root,stack['stack'],component['name'])
            if resolved['status']!='resolved':_fail('workbench_source_acceptance_scope_incomplete')
            fields=[p for p,info in resolved['provenance'].items() if any(h.get('path')==origin['path'] and
                    (h.get('pointer')==origin['pointer'] or h.get('pointer','').startswith(origin['pointer']+'/')) for h in info.get('history',[]))]
            if fields:impact.append({'stack':stack['stack'],'component':component['name'],'effective_fields':sorted(fields),
                                    'impact':'source_dependency_requires_fresh_resolution_and_plan'})
    return impact


def _source_proposal_document(store,object_id,field,repo,observed,origin,raw,rendered,impact):
    result={'schema_version':'workbench-source-acceptance-proposal/1','tenant_id':store.tenant_id,'object_id':object_id,
        'field':field,'repository_intent_id':repo['artifact_id'],'observation_snapshot_id':observed['snapshot_id'],
        'authoritative_source':{'path':origin['path'],'pointer':origin['pointer'],'before_sha256':hashlib.sha256(raw).hexdigest(),'after_sha256':hashlib.sha256(rendered).hexdigest()},
        'shared_inheritance_impact':impact,'fresh_plan_required':True,'normal_change_review_required':True,
        'no_resource_changes_established':False,'source_modified':False,'refresh_only_apply_performed':False,
        'formatting':'YAML rendering may change formatting/comments; complete byte diff requires review.',
        'cloud_authority':False,'execution_authorized':False}
    return result


def propose_source_acceptance(store,object_id,field,output,*,scope=None):
    """Emit a bounded patch to the winning source, never apply or refresh state."""
    from .windows_workbench import WindowsWorkbenchStore
    if type(store) is WindowsWorkbenchStore:
        from .windows_source import propose_source_acceptance as native_propose
        return native_propose(store,object_id,field,output,scope=scope)
    import yaml
    value=views(store,object_id,scope=scope);repo=value['repository'];observed=value['observed']
    if repo['status']!='recorded' or value['coverage']['observation']!='complete_fresh':_fail('workbench_source_acceptance_incomplete')
    # One top-level semantic field is the bounded review unit, including an exact
    # complete assignments/settings subtree. No partial list index inference.
    if field not in {'/'+k for k in semantics.FIELDS}:_fail('workbench_source_acceptance_field')
    new_value=_pointer(observed['body'],field);old_value=_pointer(repo['desired'],field)
    if canonical(new_value)==canonical(old_value):_fail('workbench_source_acceptance_no_change')
    root=Path(repo['scope']['repository'])
    fresh=resolve_component(root,repo['scope']['stack'],repo['scope']['component'])
    if digest(public_resolution(fresh))!=digest(repo['resolution']):_fail('workbench_source_acceptance_stale')
    pointer=repo['effective_pointer']+field;origin=fresh['provenance'].get(pointer,{}).get('winner')
    if type(origin) is not dict or not {'path','pointer'}<=set(origin):_fail('workbench_source_acceptance_origin')
    source_path=root/origin['path'];raw=_read(source_path)
    if hashlib.sha256(raw).hexdigest()!=next((s['sha256'] for s in fresh['sources'] if s['path']==origin['path']),None):_fail('workbench_source_acceptance_stale')
    rendered=_render_source_proposal(raw,origin,old_value,new_value)
    impact=_source_impact(root,origin)
    patch=''.join(difflib.unified_diff(raw.decode('utf-8').splitlines(True),rendered.decode().splitlines(True),
        fromfile='a/'+origin['path'],tofile='b/'+origin['path']))
    # Recheck selected source snapshot after impact discovery before publishing.
    for item in fresh['sources']:
        if hashlib.sha256(_read(root/item['path'])).hexdigest()!=item['sha256']:_fail('workbench_source_acceptance_stale')
    destination=Path(output).absolute()
    if any(p.is_symlink() for p in (destination,*destination.parents)) or destination.exists() or not destination.parent.is_dir():_fail('workbench_source_acceptance_output')
    if destination==root or root in destination.parents:_fail('workbench_source_acceptance_output')
    result=_source_proposal_document(store,object_id,field,repo,observed,origin,raw,rendered,impact)
    destination.mkdir(mode=0o700)
    for name,data in (('source.before.yaml',raw),('source.after.yaml',rendered),('change.patch',patch.encode())):
        fd=os.open(destination/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
    write_json(destination/'proposal.json',result);sync_directory(destination);sync_directory(destination.parent)
    return result


def add_parser(sub):
    p=sub.add_parser('repository-entry',help='List the policies an existing Atmos repository holds and the exact command to record each; read-only')
    for name in ('root','repo'):p.add_argument('--'+name,required=True)
    p=sub.add_parser('repository-import',help='Capture actual bounded literal Atmos intent; no provider or Git hooks execute')
    for name in ('root','repo','stack','component','object','pointer','revision','backend','resource-address'):p.add_argument('--'+name,required=True)
    p.add_argument('--git-executable');p.add_argument('--git-sha256')
    p=sub.add_parser('repository-status',help='Compare the latest repository intent with a fresh resolution; never re-imports')
    for name in ('root','object'):p.add_argument('--'+name,required=True)
    p=sub.add_parser('repository-refresh',help='Re-import the latest intent with its recorded stack, component, pointer, backend and address')
    for name in ('root','object','revision'):p.add_argument('--'+name,required=True)
    p.add_argument('--git-executable');p.add_argument('--git-sha256')
    p=sub.add_parser('propose-from-intent',help='Prepare a proposal for review from the current repository intent; nothing is approved')
    for name in ('root','service-root','object','output'):p.add_argument('--'+name,required=True)
    for name in ('ownership-import','ownership-scan','provider-refresh-import','deployment-import'):
        p=sub.add_parser(name,help='Record explicitly declared evidence without execution authority');p.add_argument('--root',required=True);p.add_argument('--input',required=True)
    p=sub.add_parser('deployment-record',help='Reconstruct a successful local operation and readback as a scoped baseline')
    for name in ('root','operation','intent'):p.add_argument('--'+name,required=True)
    p=sub.add_parser('service-link',help='Link a registered protected service operation into persistent views; does not execute')
    for name in ('root','object','job-root','policy'):p.add_argument('--'+name,required=True)
    p=sub.add_parser('evidence-link',help='Link exact signed received worker evidence; every read revalidates bytes and trust')
    for name in ('root','object','evidence-store','request-sha256','trust','verifier','scratch'):p.add_argument('--'+name,required=True)
    p=sub.add_parser('evidence-history',help='Reverify received signed evidence and show historical/expired scope explicitly')
    for name in ('root','object'):p.add_argument('--'+name,required=True)
    p=sub.add_parser('adoption-link',help='Link a protected state-only adoption; never promote a Graph deployment baseline')
    for name in ('root','object','job-root','policy'):p.add_argument('--'+name,required=True)
    p=sub.add_parser('adoption-history',help='Read linked protected adoption journals; no import or replay')
    for name in ('root','object'):p.add_argument('--'+name,required=True)
    p=sub.add_parser('views',help='Repository, observed, proposed and coverage with distinct evidence baselines')
    p.add_argument('--root',required=True);p.add_argument('--object');p.add_argument('--scope');p.add_argument('--operation');p.add_argument('--intent')
    p.add_argument('--limit',type=int,default=100);p.add_argument('--offset',type=int,default=0)
    p.add_argument('--query',default='');p.add_argument('--ownership',choices=OWNERSHIP_FILTERS);p.add_argument('--coverage',choices=COVERAGE_FILTERS);p.add_argument('--health',choices=HEALTH_FILTERS)
    p=sub.add_parser('source-acceptance-propose',help='Write a reviewed source patch; does not edit source or run refresh/apply')
    for name in ('root','object','field','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--scope');sub.add_parser('field-semantics',help='Show versioned collection/type rules')


def command(args):
    name=args.workbench_command
    if name=='field-semantics':return semantics.contract()
    from .workbench_store import WorkbenchStore
    store=WorkbenchStore(args.root)
    if name=='repository-entry':
        from .repository_entry import entry
        return entry(store,args.repo)
    if name=='repository-import':return import_repository(store,args.repo,args.stack,args.component,args.object,args.pointer,args.revision,args.backend,args.resource_address,git_executable=args.git_executable,git_sha256=args.git_sha256)
    if name in ('repository-status','repository-refresh','propose-from-intent'):
        from . import workbench_repository as repository
        if name=='repository-status':return repository.status(store,args.object)
        if name=='repository-refresh':return repository.refresh_intent(store,args.object,args.revision,git_executable=args.git_executable,git_sha256=args.git_sha256)
        return repository.propose_from_intent(store.root,args.service_root,args.object,args.output)
    if name=='ownership-import':return import_ownership(store,args.input)
    if name=='ownership-scan':return scan_ownership(store,args.input)
    if name=='provider-refresh-import':return import_provider_refresh(store,args.input)
    if name=='deployment-import':return import_deployment(store,args.input)
    if name=='deployment-record':return record_local_deployment(store,args.operation,args.intent)
    if name=='service-link':
        from .workbench_service_views import link
        return link(store,args.object,args.job_root,args.policy)
    if name in ('evidence-link','evidence-history'):
        from . import workbench_evidence_views as received_views
        if name=='evidence-link':return received_views.link(store,args.object,args.evidence_store,args.request_sha256,args.trust,args.verifier,args.scratch)
        return received_views.history(store,args.object)
    if name in ('adoption-link','adoption-history'):
        from . import workbench_adoption_views as adoption_views
        if name=='adoption-link':return adoption_views.link(store,args.object,args.job_root,args.policy)
        return adoption_views.history(store,args.object)
    scope=_load(args.scope)[0] if args.scope else None
    if name=='views':return views(store,args.object,scope=scope,operation=args.operation,intent_id=args.intent,limit=args.limit,offset=args.offset,query=args.query,ownership_filter=args.ownership,coverage_filter=args.coverage,health_filter=args.health)
    if name=='source-acceptance-propose':return propose_source_acceptance(store,args.object,args.field,args.output,scope=scope)
    _fail('workbench_view_command')
