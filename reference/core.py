"""Original offline reference algorithms for Appendix B, not a deployed plugin.

No authentication, network I/O, engine invocation, or cloud mutations. Only
write_project writes local output. Source payloads remain in the caller's input.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import sys
import tempfile
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

PROVIDER = 'deploymenttheory/microsoft365'
PROVIDER_VERSION = '1.0.0'
RESOURCE = 'microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json'
ODATA = '#microsoft.graph.'
KNOWN_TYPES = {ODATA+x for x in [
    'deviceManagementConfigurationSetting',
    'deviceManagementConfigurationChoiceSettingInstance',
    'deviceManagementConfigurationChoiceSettingValue',
    'deviceManagementConfigurationSimpleSettingInstance',
    'deviceManagementConfigurationIntegerSettingValue',
    'deviceManagementConfigurationStringSettingValue',
    'deviceManagementConfigurationGroupSettingCollectionInstance',
    'deviceManagementConfigurationGroupSettingValue',
]}
SETTING_KEYS = {'@odata.type','id','settingInstance','settingDefinitionId',
    'settingInstanceTemplateReference','settingInstanceTemplateId',
    'choiceSettingValue','simpleSettingValue','groupSettingCollectionValue',
    'settingValueTemplateReference','settingValueTemplateId','useTemplateDefault',
    'value','children'}
POLICY_KEYS = {'@odata.type','id','name','description','platforms','technologies',
    'roleScopeTagIds','createdDateTime','lastModifiedDateTime','settingCount',
    'isAssigned','templateReference'}
TARGET_KEYS = {'@odata.type','groupId','deviceAndAppManagementAssignmentFilterId',
    'deviceAndAppManagementAssignmentFilterType'}
SECRET_KEYS = {'clientsecret','accesstoken','refreshtoken','password','privatekey',
    'authorization','recoverykey','secret'}
STAGES = ['inventory','mapping','generation','review','qualification']

def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',',':'), allow_nan=False)

def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode('utf-8')).hexdigest()

def _escape(key: str) -> str:
    return key.replace('~','~0').replace('/','~1')

def all_pointers(obj: Any, pointer: str='') -> list[str]:
    """Account for EVERY node, including containers, root, null and empty arrays."""
    out=[pointer]
    if isinstance(obj,dict):
        for k,v in obj.items(): out += all_pointers(v,pointer+'/'+_escape(k))
    elif isinstance(obj,list):
        for i,v in enumerate(obj): out += all_pointers(v,pointer+'/'+str(i))
    return out

def _walk(obj: Any, p: str=''):
    yield p,obj
    if isinstance(obj,dict):
        for k,v in obj.items(): yield from _walk(v,p+'/'+_escape(k))
    elif isinstance(obj,list):
        for i,v in enumerate(obj): yield from _walk(v,p+'/'+str(i))

def stable_key(tenant: str, object_id: str) -> str:
    return 'p_'+UUID(tenant).hex+'_'+UUID(object_id).hex

def _uuid_comparison_key(value):
    """Canonicalize only UUID-shaped identities for comparison, never output."""
    if isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', value):
        return str(UUID(value))
    return value

def _control_free(value: str) -> str:
    if not isinstance(value,str): raise ValueError('Arguments must be strings')
    if any(ord(c)<32 or 127<=ord(c)<160 or ord(c) in {0x202a,0x202b,0x202c,0x202d,0x202e,0x2066,0x2067,0x2068,0x2069} for c in value):
        raise ValueError('Control characters/newlines are unsupported in command values')
    return value

def render_bash(executable: str, arguments: list[str]) -> str:
    from .validation import validate_executable
    executable=validate_executable(executable)
    # The harmless argv test uses the current trusted absolute interpreter.
    if executable=='python':executable=sys.executable
    values=[_control_free(v) for v in [executable,*arguments]]
    return '#!/usr/bin/env bash\nset -o pipefail\n'+' '.join(shlex.quote(v) for v in values)+'\nstatus=$?\nexit "$status"\n'

def render_powershell(executable: str, arguments: list[str]) -> str:
    from .validation import validate_executable
    executable=validate_executable(executable)
    # The harmless argv test uses the current trusted absolute interpreter.
    if executable=='python':executable=sys.executable
    values=[_control_free(v) for v in [executable,*arguments]]
    # PowerShell consumes this exact reserved token even when it is a quoted
    # element of a splatted Standard-mode native argument array. Fail before
    # emitting an inaccurate command preview; never silently drop the value.
    if '--%' in values[1:]:
        raise ValueError('PowerShell preview cannot preserve reserved argument --%; use an approved structured execution path')
    # PowerShell recognizes these Unicode characters as single-quote delimiters.
    # Reject them before preview emission rather than treating them as inert text.
    if any(any(0x2018 <= ord(c) <= 0x201b for c in value) for value in values):
        raise ValueError('PowerShell preview does not support Unicode single-quote delimiters U+2018 through U+201B; use an approved structured execution path')
    def quote(x): return "'"+x.replace("'","''")+"'"
    return ("#requires -Version 7.3\n$ErrorActionPreference = 'Stop'\n"
      "$PSNativeCommandArgumentPassing = 'Standard'\n"
      + '$exe = '+quote(values[0])+'\n'
      + '$nativeArgs = @('+', '.join(quote(x) for x in values[1:])+')\n'
      + '& $exe @nativeArgs\n$nativeStatus = $LASTEXITCODE\nexit $nativeStatus\n')

def invalidated(changed: set[str]) -> list[str]:
    triggers={
      'source_digest':0, 'tenant_id':0, 'cloud':0, 'selected_ids':0,
      'provider_lock_digest':1, 'provider_version':1, 'api_version':1,
      'engine_version':1, 'ownership':1,
      'atmos_version':2, 'component':2, 'stack':2, 'generated_file_edit':2,
      'repository_revision':2, 'dirty_digest':2,
      'cohort_digest':3, 'plan_digest':3, 'identity':3,
    }
    if not changed:return []
    # Unknown provenance changes conservatively invalidate everything.
    return STAGES[min(triggers.get(k,0) for k in changed):]

def _redact(obj: Any):
    if isinstance(obj,dict):
        secret_type='SecretSettingValue' in str(obj.get('@odata.type',''))
        return {k:('[LOCAL_ONLY]' if k.lower().replace('_','') in SECRET_KEYS or (secret_type and k=='value') else _redact(v)) for k,v in obj.items()}
    if isinstance(obj,list): return [_redact(v) for v in obj]
    return obj

def normalize(bundle: dict, policy_id: str, expected_tenant: str) -> dict:
    """Validate the bounded capture and project only explicitly classified fields.

    Unsupported source values and key names stay in restricted input. Every
    emitted source node has either a reviewed mapping rule or opaque retention.
    """
    from .validation import schema_errors, provider_settings, capability_errors, capture_errors, reference_errors
    from .field_accounting import records, opaque, under
    if not isinstance(bundle,dict):raise ValueError('Input must be an object')
    b=copy.deepcopy(bundle)
    if any(isinstance(value,float) or (isinstance(value,int) and not isinstance(value,bool) and not -(2**63)<=value<2**63) for _,value in _walk(b)):
        raise ValueError('Unsupported numeric encoding')
    source_digest=digest(b)
    try:
        key=stable_key(b['tenant_id'],policy_id)
        if not UUID(b['tenant_id']).int or not UUID(policy_id).int or not UUID(expected_tenant).int:raise ValueError()
    except (KeyError,ValueError,TypeError,AttributeError):raise ValueError('Valid nonzero tenant and object UUIDs required')
    blockers=[];retained=set();sensitive=set()
    def safe_pointer(path):return 'opaque:'+opaque(path) if under(path,retained|sensitive) else path
    def block(code,path):
        row={'code':code,'source_pointer':safe_pointer(path)}
        if row not in blockers:blockers.append(row)
    def retain(path,secret=False):
        (sensitive if secret else retained).add(path)
        block('sensitive_local_only' if secret else 'unsupported_source_field',path)
    # Structural key classification is explicit at each object boundary. Unknown
    # keys themselves may be secrets, so never put them in a visible pointer.
    top={'schema_version','synthetic','tenant_id','cloud','captured_at','exporter','collections','references','ownership'}
    def scrub(obj,p='',role='root'):
        if isinstance(obj,list):return [scrub(v,p+'/'+str(i),role) for i,v in enumerate(obj)]
        if not isinstance(obj,dict):return copy.deepcopy(obj)
        allowed={'root':top,'exporter':{'id','version'},'collection':{'kind','owner_id','coverage','reason','pages'},'page':{'request_url','method','http_status','captured_at','body'},'body':{'value','@odata.nextLink','@odata.context','@odata.count','error'},'reference':{'kind','id','ownership','coverage','captured_at'},'ownership':{'object_id','current_writer','adoption_intent'},'policy':POLICY_KEYS,'template':{'@odata.type','templateId','templateFamily','templateDisplayName','templateDisplayVersion'},'setting':SETTING_KEYS,'assignment':{'id','@odata.type','target'},'target':TARGET_KEYS,'error':set()}.get(role,set())
        output={}
        for k,v in obj.items():
            pp=p+'/'+_escape(k)
            secret=k.lower().replace('_','') in SECRET_KEYS or ('SecretSettingValue' in str(obj.get('@odata.type','')) and k=='value')
            if secret or k not in allowed:
                retain(pp,secret);continue
            if k=='@odata.type':
                accepted=(KNOWN_TYPES-{ODATA+'deviceManagementConfigurationGroupSettingCollectionInstance',ODATA+'deviceManagementConfigurationGroupSettingValue'})|{ODATA+'deviceManagementConfigurationPolicy',ODATA+'deviceManagementConfigurationPolicyAssignment',ODATA+'groupAssignmentTarget',ODATA+'exclusionGroupAssignmentTarget'}
                if not isinstance(v,str) or v not in accepted:
                    retain(pp);continue
            childrole=role
            if role=='root':childrole={'exporter':'exporter','collections':'collection','references':'reference','ownership':'ownership'}.get(k,role)
            elif role=='collection' and k=='pages':childrole='page'
            elif role=='page' and k=='body':childrole='body'
            elif role=='body' and k=='value':childrole=collection_kind.get(p.split('/pages/')[0],'policy')
            elif role=='body' and k=='error':childrole='error'
            elif role=='policy' and k=='templateReference':childrole='template'
            elif role=='assignment' and k=='target':childrole='target'
            output[k]=scrub(v,pp,childrole)
        return output
    collection_kind={f'/collections/{i}':{'policies':'policy','settings':'setting','assignments':'assignment'}.get(c.get('kind'),'error') for i,c in enumerate(b.get('collections',[])) if isinstance(c,dict)}
    clean=scrub(b)
    if b.get('schema_version')!='1.0.0':block('unsupported_export_version','/schema_version')
    if b.get('tenant_id','').lower()!=expected_tenant.lower():block('wrong_tenant','/tenant_id')
    if b.get('cloud')!='public':block('cloud_not_qualified','/cloud')
    if b.get('synthetic') is not True:block('reference_generator_accepts_synthetic_only','/synthetic')
    if b.get('exporter')!={'id':'appendix-b-graph-snapshot','version':'1.0.0'}:block('unqualified_exporter_adapter','/exporter')
    if schema_errors('export-intake',b):block('invalid_capture_schema','')
    cols={};collection_results=[]
    root='https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'
    for ci,c in enumerate(b.get('collections',[])):
        cp=f'/collections/{ci}'
        if not isinstance(c,dict):block('invalid_collection',cp);continue
        kind=c.get('kind');owner=c.get('owner_id')
        if kind=='policies' and owner is not None:
            block('invalid_collection_owner',cp+'/owner_id');continue
        if not isinstance(kind,str) or kind not in {'policies','settings','assignments'}:block('invalid_collection_kind',cp+'/kind');continue
        if kind!='policies' and owner!=policy_id:
            block('unselected_collection_owner',cp+'/owner_id');continue
        ident=(kind,owner)
        if ident in cols:block('duplicate_collection',cp)
        values=[];valid=c.get('coverage')=='complete';pages=c.get('pages',[])
        expected=root if kind=='policies' else root+'/'+policy_id+'/'+kind
        if capture_errors(c,expected):valid=False;block('capture_contract_violation',cp)
        path=urlparse(expected).path;seen=set();declared_counts=[]
        if not isinstance(pages,list) or not pages:valid=False;block('missing_pages',cp+'/pages');pages=[]
        for pi,page in enumerate(pages):
            pp=cp+f'/pages/{pi}'
            if not isinstance(page,dict):valid=False;block('invalid_page',pp);continue
            url=page.get('request_url');body=page.get('body')
            if url!=expected:valid=False;block('broken_page_chain' if pi else 'invalid_initial_collection_boundary',pp+'/request_url')
            def trusted_url(value):
                if not isinstance(value,str) or any(ord(x)<32 or ord(x)==127 for x in value):return False
                try:
                    u=urlparse(value)
                    from urllib.parse import parse_qsl
                    prohibited={'$filter','$search','$select','$top','$expand','$skip'}
                    return u.scheme=='https' and u.netloc=='graph.microsoft.com' and u.path==path and not u.username and not u.password and not u.fragment and not any(k.lower() in prohibited for k,_ in parse_qsl(u.query,keep_blank_values=True))
                except ValueError:return False
            if not trusted_url(url):valid=False;block('untrusted_page_url',pp+'/request_url')
            if isinstance(url,str) and url in seen:valid=False;block('duplicate_or_looped_page',pp+'/request_url')
            if isinstance(url,str):seen.add(url)
            if page.get('method')!='GET' or page.get('http_status')!=200 or not isinstance(page.get('captured_at'),str):valid=False;block('invalid_page_provenance',pp)
            if not isinstance(body,dict) or not isinstance(body.get('value'),list):valid=False;block('missing_value_collection',pp+'/body');expected=None;continue
            if '@odata.count' in body:declared_counts.append(body['@odata.count'])
            sanitized=clean.get('collections',[])[ci].get('pages',[])[pi].get('body',{}).get('value',[])
            for i,v in enumerate(body['value']):
                if not isinstance(v,dict):valid=False;block('invalid_collection_record',pp+f'/body/value/{i}');continue
                values.append((v,pp+f'/body/value/{i}',sanitized[i] if i<len(sanitized) else {}))
            expected=body.get('@odata.nextLink')
            if expected is not None and not trusted_url(expected):valid=False;block('untrusted_next_link',pp+'/body/@odata.nextLink')
        if expected is not None:valid=False;block('unfetched_next_page',cp)
        observed_ids=set()
        for record,rp,_ in values:
            record_id=record.get('id')
            identity=record_id if kind=='settings' else _uuid_comparison_key(record_id)
            if not isinstance(identity,str) or identity in observed_ids:
                valid=False;block('duplicate_or_missing_source_identity',rp+'/id')
            if isinstance(identity,str):observed_ids.add(identity)
        if any(type(count) is not int or count<0 or count!=len(values) for count in declared_counts):
            valid=False;block('collection_count_mismatch',cp)
        if not valid:block('incomplete_collection',cp)
        cols.setdefault(ident,(values,valid))
        collection_results.append({'kind':kind,'owner_id':owner,'complete':valid,'page_count':len(pages),'source_pointer':cp})
    # The separate capture validator is also a generation gate; producer checks
    # above retain actionable safe pointers for review.
    policies,pcomplete=cols.get(('policies',None),([],False))
    policy_ids=set()
    for row,pp,_ in policies:
        identity=_uuid_comparison_key(row.get('id'))
        if isinstance(identity,str):
            if identity in policy_ids:block('duplicate_policy_identity',pp+'/id')
            policy_ids.add(identity)
    matches=[x for x in policies if isinstance(x[0].get('id'),str) and x[0]['id'].lower()==policy_id.lower()]
    if len(matches)!=1:block('missing_or_duplicate_object_id','/collections')
    policy,policy_pointer,policy_clean=matches[0] if matches else ({},'/collections',{})
    settings,scomplete=cols.get(('settings',policy_id),([],False));assignments,acomplete=cols.get(('assignments',policy_id),([],False))
    for name,complete in [('policies',pcomplete),('settings',scomplete),('assignments',acomplete)]:
        if not complete:block('required_'+name+'_incomplete','/collections')
    if policy.get('@odata.type')!=ODATA+'deviceManagementConfigurationPolicy':block('missing_or_invalid_policy_discriminator',policy_pointer)
    if schema_errors('observed-policy',policy):block('invalid_observed_policy',policy_pointer)
    if scomplete and policy.get('settingCount')!=len(settings):block('setting_count_mismatch',policy_pointer+'/settingCount')
    if acomplete and 'isAssigned' in policy and policy['isAssigned']!=bool(assignments):block('assignment_flag_mismatch',policy_pointer+'/isAssigned')
    # Invalid known values are not supported retention in visible observations.
    policy_properties=json.loads((Path(__file__).resolve().parents[1]/'corrections/contracts/observed-policy.schema.json').read_text())['properties']
    from jsonschema import Draft202012Validator,FormatChecker
    for k,v in list(policy_clean.items()):
        fragment=policy_properties.get(k)
        if fragment and list(Draft202012Validator(fragment,format_checker=FormatChecker()).iter_errors(v)):
            retain(policy_pointer+'/'+_escape(k));policy_clean.pop(k)
    settings_out=[];observed_settings=[];seen_ids=set()
    for i,(setting,sp,sc) in enumerate(settings):
        sid=setting.get('id')
        if isinstance(sid,str) and sid in seen_ids:block('duplicate_setting_identity',sp+'/id')
        if isinstance(sid,str):seen_ids.add(sid)
        if sid!=str(i):block('nonsequential_setting_id',sp+'/id')
        if setting.get('@odata.type')!=ODATA+'deviceManagementConfigurationSetting':block('missing_or_invalid_setting_discriminator',sp)
        if schema_errors('observed-setting',setting):block('invalid_observed_setting',sp)
        if schema_errors('observed-setting',sc) or capability_errors([sc],policy.get('platforms'),policy.get('technologies')):
            retain(sp);observed_settings.append({});continue
        observed_settings.append(sc);settings_out.append({'id':sc['id'],'settingInstance':sc['settingInstance']})
    projected={'settings':settings_out}
    try:provider_settings([sc for sc in observed_settings if sc])
    except ValueError:block('invalid_provider_settings','/collections')
    if capability_errors([sc for sc in observed_settings if sc],policy.get('platforms'),policy.get('technologies')):block('unqualified_setting_capability','/collections')
    desired_assign=[];observed_assign=[];seen_assign=set();target_tuples=set()
    refs=[]
    ref_schema=json.loads((Path(__file__).resolve().parents[1]/'contracts/observed-inventory.schema.json').read_text())['properties']['references']['items']
    source_refs=clean.get('references',[])
    if not isinstance(source_refs,list):source_refs=[]
    for ri,rr in enumerate(source_refs):
        invalid=list(Draft202012Validator(ref_schema,format_checker=FormatChecker()).iter_errors(rr))
        if not invalid and rr.get('kind') in {'group','filter'}:
            try:
                rid=rr['id'];invalid=not re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',rid) or not UUID(rid).int
            except (ValueError,TypeError):invalid=True
        if invalid:retain(f'/references/{ri}');continue
        refs.append(rr)
    if reference_errors(b.get('references')):block('invalid_or_duplicate_reference','/references')
    ref_index={}
    for rr in refs:
        if isinstance(rr,dict):ref_index.setdefault((rr.get('kind'),_uuid_comparison_key(rr.get('id')) if rr.get('kind') in {'group','filter'} else rr.get('id')),[]).append(rr)
    def reference(kind,rid,path):
        matches=ref_index.get((kind,_uuid_comparison_key(rid) if kind in {'group','filter'} else rid),[])
        if len(matches)!=1 or matches[0].get('coverage')!='complete' or matches[0].get('ownership')!='external':block('reference_missing_or_not_external',path)
    for i,(a,ap,ac) in enumerate(assignments):
        aid=a.get('id')
        identity=_uuid_comparison_key(aid)
        if isinstance(identity,str) and identity in seen_assign:block('duplicate_assignment_identity',ap+'/id')
        if isinstance(identity,str):seen_assign.add(identity)
        if a.get('@odata.type')!=ODATA+'deviceManagementConfigurationPolicyAssignment':block('missing_or_invalid_assignment_discriminator',ap)
        if schema_errors('observed-assignment',a):block('invalid_observed_assignment',ap)
        if schema_errors('observed-assignment',ac):retain(ap);observed_assign.append({});continue
        target=ac['target'];ty=target['@odata.type'].removeprefix(ODATA);group=target['groupId'];mode=target['deviceAndAppManagementAssignmentFilterType'];fid=target.get('deviceAndAppManagementAssignmentFilterId')
        if ty=='exclusionGroupAssignmentTarget' and mode!='none':block('filtered_exclusion_not_qualified',ap+'/target')
        reference('group',group,ap+'/target/groupId')
        if mode!='none':reference('filter',fid,ap+'/target/deviceAndAppManagementAssignmentFilterId')
        tup=(ty,_uuid_comparison_key(group),mode,_uuid_comparison_key(fid) if mode!='none' else None)
        if tup in target_tuples:block('duplicate_assignment_target',ap)
        target_tuples.add(tup);d={'type':ty,'group_id':group,'filter_type':mode}
        if mode!='none':d['filter_id']=fid
        desired_assign.append(d);observed_assign.append(ac)
    for tag in policy_clean.get('roleScopeTagIds',[]):reference('scope_tag',tag,policy_pointer+'/roleScopeTagIds')
    owners=[o for o in b.get('ownership',[]) if isinstance(o,dict) and o.get('object_id')==policy_id]
    if len(owners)!=1:block('ownership_unknown','/ownership')
    elif owners[0].get('current_writer') not in {None,'this-repository'}:block('writer_conflict','/ownership')
    result={'schema_version':'1.0.0','object_id':policy_id,'tenant_id':b['tenant_id'],'key':key,'source_canonical_sha256':source_digest,
      'observed':{'policy':policy_clean,'settings':observed_settings,'assignments':observed_assign},
      'desired':{'name':policy_clean.get('name'),'description':policy_clean.get('description'),'platforms':policy_clean.get('platforms'),'technologies':[policy_clean['technologies']] if 'technologies' in policy_clean else [],'role_scope_tag_ids':policy_clean.get('roleScopeTagIds'),'settings':projected,'assignments':desired_assign if acomplete or assignments else None},
      'references':refs,'coverage':collection_results,'blockers':blockers,
      'field_accounting':records(b,policy_pointer,[(v,p) for v,p,_ in settings],[(v,p) for v,p,_ in assignments],retained,sensitive,source_digest),
      'offline_mapping_complete':not blockers,'live_qualification':'not_run','execution_authorized':False}
    # Fail closed before any active emission when output contracts are invalid.
    errors=schema_errors('observed-inventory',result)
    if errors:raise ValueError('Normalized output contract violation')
    return result

def _json(x):return json.dumps(x,indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n'

def generate_files(normalized: dict, context: dict) -> dict[str,str]:
    from .validation import schema_errors,provider_settings,capability_errors
    n=copy.deepcopy(normalized);c=context
    if not isinstance(c,dict) or c.get('schema_version')!='1.0.0' or c.get('selected_policy_id')!=n.get('object_id') or c.get('engine_version')!='1.10.0' or c.get('atmos_version')!='1.199.0':raise ValueError('Unqualified context version or selection')
    if schema_errors('observed-inventory',n):raise ValueError('Normalized output contract violation')
    if n.get('execution_authorized') is not False or n.get('live_qualification')!='not_run' or n.get('offline_mapping_complete')!= (not n.get('blockers')):raise ValueError('Inconsistent normalized guard record')
    if n.get('key')!=stable_key(n['tenant_id'],n['object_id']):raise ValueError('Invalid normalized identity')
    if not n['blockers']:
        projected=provider_settings(n['observed']['settings'])
        if projected!=n['desired']['settings'] or capability_errors(n['observed']['settings'],n['desired']['platforms'],','.join(n['desired']['technologies'])):raise ValueError('Invalid normalized provider projection')
    if c.get('engine')!='tofu' or c.get('provider_source')!=PROVIDER or c.get('provider_version')!=PROVIDER_VERSION:raise ValueError('Unqualified engine/provider context')
    if c.get('tenant_id')!=n['tenant_id'] or c.get('cloud')!='public':raise ValueError('Target mismatch')
    if c.get('stack')!='reference-dev' or c.get('component')!='intune-reference':raise ValueError('Reference generator only accepts the synthetic target')
    if c.get('authorization')!='emit_only' or not c.get('source_is_synthetic'):raise ValueError('This reference generator is synthetic and emit-only')
    active=not n['blockers'];p='components/terraform/intune-reference/'
    files={
      'README.md':'# Generated offline reference project\n\nSynthetic input. NOT tenant-validated, provider-tested, or organization-approved.\nNo authentication, plan, import or apply was executed.\n'+('All input fields are accounted for in this bounded mapping.\n' if active else '**BLOCKED:** review-only output; no active IaC or import command is emitted.\n'),
      'adoption/field-accounting.json':_json({'schema_version':'1.0.0','records':n['field_accounting']}),
      'adoption/coverage.json':_json({'schema_version':'1.0.0','collections':n['coverage']}),
      'adoption/capability.json':_json({'schema_version':'1.0.0','provider':PROVIDER,'version':PROVIDER_VERSION,'offline_mapping_complete':active,'live_qualified':False,'execution_authorized':False,'blockers':n['blockers']}),
      'adoption/object-map.json':_json({'schema_version':'1.0.0','objects':[{'tenant_id':n['tenant_id'],'object_id':n['object_id'],'resource_family':'settings_catalog_policy','address':RESOURCE+'.policy["'+n['key']+'"]','provider_source':PROVIDER,'provider_version':PROVIDER_VERSION,'import_id':n['object_id'],'referenced_objects_owner':'external','import_status':'not_run'}]}),
      'adoption/unresolved-paths.json':_json({'schema_version':'1.0.0','source_canonical_sha256':n['source_canonical_sha256'],'raw_values_location':'original restricted input; not copied here','blockers':n['blockers']}),
    }
    declaration='''# Synthetic source-qualified reference only. No provider or tenant execution.
terraform {
  required_version = ">= 1.10.0, < 1.11.0"
  required_providers {
    microsoft365 = { source = "deploymenttheory/microsoft365", version = "1.0.0" }
  }
}
variable "live_qualification_ack" {
  type = bool
  default = false
  description = "Must remain false until independent qualification and approval."
}
locals {
  adoption = jsondecode(file("${path.module}/adoption-input.json"))
}
resource "microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json" "policy" {
  for_each           = { (local.adoption.key) = local.adoption.desired }
  name               = each.value.name
  description        = each.value.description
  platforms          = each.value.platforms
  technologies       = each.value.technologies
  role_scope_tag_ids = each.value.role_scope_tag_ids
  settings           = jsonencode(each.value.settings)
  assignments        = each.value.assignments
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = var.live_qualification_ack
      error_message = "Reference materials only: qualify provider, target and authorization before execution."
    }
  }
}
output "adoption_object_ids" {
  description = "Provider-returned policy IDs; not proof of endpoint success."
  value = { for k, v in microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json.policy : k => v.id }
}
'''
    if not active:
        files['review/proposed-component.tf.txt']=declaration
        files['review/adoption-input.json']=_json({'key':n['key'],'desired':n['desired']})
        files['BLOCKED.json']=_json({'schema_version':'1.0.0','execution_allowed':False,'blockers':n['blockers']})
        files['commands/command-cards.json']=_json({'schema_version':'1.0.0','cards':[]})
        return files
    files[p+'main.tf']=declaration
    files[p+'imports.tf']='# ID passthrough importer in pinned resource.go. Execution is not authorized.\nimport {\n  to = '+RESOURCE+'.policy["'+n['key']+'"]\n  id = "'+n['object_id']+'"\n}\n'
    files[p+'adoption-input.json']=_json({'key':n['key'],'desired':n['desired']})
    files['atmos.yaml']='''base_path: "."
components:
  terraform:
    base_path: components/terraform
    command: tofu
    apply_auto_approve: false
    auto_generate_backend_file: false
stacks:
  base_path: stacks
  included_paths: ["orgs/**/*"]
  name_pattern: "{tenant}-{stage}"
'''
    files['.tool-versions']='opentofu 1.10.0\natmos 1.199.0\n'
    files['stacks/orgs/reference/dev.yaml']='''vars:
  tenant: reference
  stage: dev
components:
  terraform:
    intune-reference:
      command: tofu
      vars:
        live_qualification_ack: false
'''
    files['.gitignore']='.terraform/\n*.tfstate\n*.tfstate.*\n*.plan\n*.planfile\n*.tfplan\n# Keep .terraform.lock.hcl after independently approved provider initialization.\n'
    address=RESOURCE+'.policy["'+n['key']+'"]'
    args=['terraform','import','intune-reference','-s','reference-dev',address,n['object_id']]
    card={'id':'propose-import','purpose':'Attach existing policy ID through the pinned importer; not execute here','executable':'atmos','arguments':args,'working_directory':'.','effect_class':'state_mutation','effects':{'local_write':True,'network':True,'state_write':True,'cloud_write':'provider_path_requires_qualification'},'authorization':'protected_ci_required','execution_allowed':False,'expected_exit_codes':[0],'provider_source':PROVIDER,'provider_version':PROVIDER_VERSION}
    files['commands/command-cards.json']=_json({'schema_version':'1.0.0','cards':[card]})
    files['commands/PROPOSED-import.ps1.txt']=render_powershell('atmos',args)
    files['commands/PROPOSED-import.sh.txt']=render_bash('atmos',args)
    files['commands/README.md']='# Proposals, not executable launchers\n\nCLI import and declarative import are alternative authorized workflows, not an instruction to run both. Confirm exact Atmos pass-through arguments using pinned CLI help before execution. No credential acquisition is provided. The declarative import path remains in imports.tf.\n'
    return files

def _safe_relative(name: str):
    p=PurePosixPath(name)
    if not isinstance(name,str) or str(p)!=name or not name or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or any(x in {'','.'} for x in p.parts):raise ValueError('Unsafe output path')
    for piece in p.parts:
        if piece.endswith((' ','.')) or piece.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:raise ValueError('Unsafe platform filename')

def _write_private_project_file(stage: Path, name: str, text: str):
    """Publish source-derived material with private POSIX creation modes."""
    parent = stage
    for part in PurePosixPath(name).parts[:-1]:
        parent = parent / part
        parent.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(stage / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())

def write_project(files: dict[str,str], destination: Path) -> str:
    """New-directory transaction only; reruns verify generated hashes, never merge."""
    dest=Path(destination).absolute()
    for p in [dest,*dest.parents]:
        if p.is_symlink():
            if dest.exists() or dest.is_symlink():raise FileExistsError('Symlink in existing output ownership path; preserve output')
            raise ValueError('Symlink in destination path')
    for name,text in files.items():
        _safe_relative(name)
        if name=='generated-files.json':raise ValueError('Reserved output ownership manifest path')
        text.encode('utf-8')
    if not dest.parent.is_dir():raise ValueError('Destination parent must already exist')
    hashes={n:hashlib.sha256(v.encode('utf-8')).hexdigest() for n,v in sorted(files.items())}
    lock=dest.parent/('.intune-iac-lock-'+hashlib.sha256(str(dest).encode()).hexdigest()[:20])
    try:fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:raise FileExistsError('Concurrent generation or abandoned lock; inspect before manual recovery')
    os.close(fd)
    try:
        if dest.exists():
            mf=dest/'generated-files.json'
            if not mf.is_file() or mf.is_symlink():raise FileExistsError('Existing directory is not an owned reference output')
            try:
                manifest_bytes=mf.read_bytes()
                def unique_manifest_keys(pairs):
                    result={}
                    for key,value in pairs:
                        if key in result:raise ValueError('Duplicate manifest field')
                        result[key]=value
                    return result
                previous=json.loads(manifest_bytes,object_pairs_hook=unique_manifest_keys)
                if not isinstance(previous,dict) or set(previous)!={'schema_version','files'} or previous['schema_version']!='1.0.0' or not isinstance(previous['files'],dict):raise ValueError('Invalid ownership manifest')
                for owned_name,owned_hash in previous['files'].items():
                    _safe_relative(owned_name)
                    if not isinstance(owned_hash,str) or not re.fullmatch(r'[0-9a-f]{64}',owned_hash):raise ValueError('Invalid ownership digest')
            except (ValueError,TypeError,UnicodeError,OSError):
                raise FileExistsError('Malformed or invalid output ownership manifest; preserve output and use a new directory') from None
            if previous.get('files')!=hashes:raise FileExistsError('Changed generation; use a new staging directory and review differences')
            def verify_output_closure():
                # The manifest is an ownership claim for the complete project,
                # including files that an infrastructure engine might discover.
                # Empty directories carry no configuration and are harmless.
                actual=set()
                def inaccessible(_error):
                    raise FileExistsError('Output file closure cannot be verified; preserve output')
                for directory,dirs,names in os.walk(dest,followlinks=False,onerror=inaccessible):
                    for entry in [*dirs,*names]:
                        candidate=Path(directory)/entry
                        if candidate.is_symlink():raise FileExistsError('Symlink in output file closure; preserve output')
                    for name in names:
                        candidate=Path(directory)/name
                        if not candidate.is_file():raise FileExistsError('Nonregular output file; preserve output')
                        actual.add(candidate.relative_to(dest).as_posix())
                if actual!=set(previous['files'])|{'generated-files.json'}:
                    raise FileExistsError('Unowned or missing output file; preserve output and use a new directory')
            verify_output_closure()
            for name,h in hashes.items():
                p=dest/name
                for parent in [p,*p.parents]:
                    if parent==dest.parent:break
                    if parent.is_symlink():raise FileExistsError('Symlink in existing output; preserve output')
                try:
                    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise FileExistsError('User-edited or missing generated file; refusing overwrite')
                except OSError:
                    raise FileExistsError('Existing generated file ownership cannot be verified; preserve output') from None
            verify_output_closure()
            try:
                if mf.read_bytes()!=manifest_bytes:raise FileExistsError('Output ownership changed during verification; preserve output')
            except OSError:
                raise FileExistsError('Output ownership cannot be verified; preserve output') from None
            return 'unchanged'
        with tempfile.TemporaryDirectory(prefix='.intune-iac-stage-',dir=dest.parent) as tmp:
            stage=Path(tmp)/'project';stage.mkdir(mode=0o700)
            for name,text in files.items():
                _write_private_project_file(stage,name,text)
            _write_private_project_file(stage,'generated-files.json',_json({'schema_version':'1.0.0','files':hashes}))
            if dest.exists():raise FileExistsError('Destination appeared during staging')
            os.replace(stage,dest)
        return 'created'
    finally:lock.unlink(missing_ok=True)

def evidence_summary(targeted: int, rows: list[dict]) -> dict:
    if isinstance(targeted,bool) or not isinstance(targeted,int) or targeted<0:raise ValueError('Invalid targeted denominator')
    ids=[r['id'] for r in rows]
    if len(ids)!=len(set(ids)) or len(ids)>targeted:raise ValueError('Duplicate or out-of-cohort evidence')
    valid={'success','failure','pending','unknown'}
    if any(r.get('status') not in valid or not isinstance(r.get('fresh'),bool) for r in rows):raise ValueError('Unsupported evidence status')
    fresh=[r for r in rows if r['fresh']];success=sum(r['status']=='success' for r in fresh);failure=sum(r['status']=='failure' for r in fresh);pending=sum(r['status']=='pending' for r in fresh)
    return {'targeted':targeted,'reporting':len(fresh),'successful':success,'failed':failure,'pending':pending,'unknown':targeted-success-failure-pending,'success_per_target':success/targeted if targeted else None,'success_per_reporter':success/len(fresh) if fresh else None,'promotion_proven':False,'reason':'Promotion needs organization thresholds, freshness and independent evidence; arithmetic alone is insufficient'}

def classify_plan(actions: list[str], contract: str|None) -> str:
    if actions==['no-op']:return 'no_remote_change_by_plan_only'
    if 'create' in actions or 'delete' in actions:return 'remote_change'
    if actions==['update'] and contract=='msgraph-0.5.0-ref-update-state-only':return 'state_only_by_pinned_source_not_live_proven'
    if actions==['update']:return 'requires_effect_evidence'
    if actions==['read']:return 'provider_read'
    return 'unsupported_action_shape'
