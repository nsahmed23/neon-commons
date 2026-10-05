"""Offline byte-backed resume store. Consistency evidence is never execution authority.

All verification lists are constructed here from reread files. No public API accepts
caller-supplied verified milestones or fingerprints. Unsupported report formats fail
closed. Local reports do not authenticate a service or approver.
"""
from __future__ import annotations
import hashlib, json, os, re, tempfile, uuid
from pathlib import Path, PurePosixPath
from jsonschema import Draft202012Validator, FormatChecker
from corrections.models.contract_model import resume_decision, capture_errors
R=Path(__file__).resolve().parents[1]
MAP=json.loads((R/'corrections/contracts/resume-stage-map.json').read_text())
STAGES=MAP['stages'];FP=MAP['invalidation_frontier']
class StoreError(ValueError):pass

def sha(data):return hashlib.sha256(data).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def parse(data):
 def pairs(items):
  result={}
  for key,value in items:
   if key in result:raise StoreError('duplicate_json_key')
   result[key]=value
  return result
 try:return json.loads(data,object_pairs_hook=pairs,parse_float=lambda _: (_ for _ in ()).throw(StoreError('floating_json_unsupported')),parse_constant=lambda _: (_ for _ in ()).throw(StoreError('nonfinite_json')))
 except (UnicodeError,json.JSONDecodeError):raise StoreError('invalid_json') from None

def _path(root,relative,exists=True):
 root=Path(root).absolute()
 if not root.is_dir():raise StoreError('evidence_root_missing')
 # Reject symlinks at every level, including the approved root itself.
 for p in [root,*root.parents]:
  if p.is_symlink():raise StoreError('symlink_path')
 if not isinstance(relative,str) or not re.fullmatch(r'[A-Za-z0-9_.\-/]+',relative):raise StoreError('unsafe_path')
 parts=PurePosixPath(relative).parts
 if not parts or relative!=PurePosixPath(relative).as_posix() or relative.startswith('/') or any(p in ('.','..') for p in parts):raise StoreError('unsafe_path')
 target=root
 for part in parts:
  target=target/part
  if target.is_symlink():raise StoreError('symlink_path')
 if exists and not target.is_file():raise StoreError('missing_artifact')
 return target

def read_bytes(root,relative):
 p=_path(root,relative)
 # O_NOFOLLOW protects the final component; parent inode races remain a native-host gate.
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  with os.fdopen(fd,'rb') as stream:
   data=stream.read(16*1024*1024+1)
   if len(data)>16*1024*1024:raise StoreError('artifact_size_limit')
   return data
 except OSError:raise StoreError('artifact_read_error') from None

def _write(root,relative,value):
 p=_path(root,relative,False);p.parent.mkdir(parents=True,exist_ok=True)
 data=canonical(value)+b'\n';fd,tmp=tempfile.mkstemp(prefix='.session-',dir=p.parent)
 try:
  with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
  _path(root,relative,False);os.replace(tmp,p)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 return sha(data)

def _validate(schema,value):
 if list(Draft202012Validator(schema,format_checker=FormatChecker()).iter_errors(value)):raise StoreError('artifact_schema_invalid')

def _contract(name):return parse((R/'corrections/contracts'/f'{name}.schema.json').read_bytes())
def _obj(properties,required=None):return {'type':'object','properties':properties,'required':list(properties) if required is None else required,'additionalProperties':False}
S={'type':'string','minLength':1};PATH={'type':'string','pattern':r'^[A-Za-z0-9_.\-/]+$'};GUID={'type':'string','format':'uuid','minLength':36,'maxLength':36};ARR={'type':'array','items':PATH,'uniqueItems':True}
REPORTS={
 'repository_context':_obj({'repository_path':PATH,'inputs':ARR}),
 'decisions':_obj({'source_kind':{'const':'local_export'},'source_path':PATH,'tenant_id':GUID,'cloud':{'const':'public'},'selected_policy_id':GUID,'selected_ids':{'type':'array','items':GUID,'uniqueItems':True},'ownership':{'type':'array','items':_obj({'object_id':GUID,'writer':S,'owner':S})}}),
 'provider_evidence':_obj({**{k:S for k in ['provider_source','provider_version','api_version','engine_version','atmos_version']},**{k:PATH for k in ['lock_path','schema_path','engine_path','atmos_path']},**{k:{'type':'string','pattern':'^[0-9a-f]{64}$'} for k in ['engine_sha256','atmos_sha256']}}),
 'effective_config':_obj({'component':S,'stack':S,'inputs':ARR,'resolved_inputs':{'type':'object','additionalProperties':{'type':['string','integer','boolean','null']}},'closed':{'const':True}}),
 'review':_obj({'cohort_path':PATH,'plan_path':PATH}),
 'validation':_obj({'oracle_version':{'const':'independent-v2'}}),
}
SCHEMAS={'source':'export-intake','normalized':'observed-inventory','generation':'generated-files'}
REQUIRED={'repository':['repository_context'],'source':['source','decisions'],'inventory':['source','decisions'],'selection':['source','decisions'],'ownership':['decisions'],'mapping':['provider_evidence','normalized','source','decisions'],'generation':['generation','effective_config','identity_context','provider_evidence','normalized','source','decisions'],'validation':['validation','generation','normalized','source','decisions'],'review':['review','effective_config','identity_context','generation','validation','normalized','source','decisions']}

def _artifact_value(kind,data):
 value=parse(data)
 if kind in REPORTS:
  _validate(_obj({'schema_version':{'const':'2.0.0'},'kind':{'const':kind},'payload':REPORTS[kind]}),value);return value['payload']
 if kind=='identity_context':
  _validate(_contract('approval-context')['properties']['binding'],value);return value
 if kind in SCHEMAS:
  _validate(parse((R/'contracts'/f'{SCHEMAS[kind]}.schema.json').read_bytes()),value);return value
 raise StoreError('unknown_artifact_kind')

def _manifest_bytes(root,paths):
 return [{'path':p,'byte_sha256':sha(read_bytes(root,p))} for p in sorted(paths)]

def _inventory(source,decision):
 if source['tenant_id']!=decision['tenant_id'] or source['cloud']!=decision['cloud']:raise StoreError('source_context_mismatch')
 if source['exporter']!={'id':'appendix-b-graph-snapshot','version':'1.0.0'}:raise StoreError('unqualified_exporter_adapter')
 chosen=decision['selected_policy_id'];seen=set();policy=None;settings=None
 for c in source['collections']:
  key=(c['kind'],c['owner_id'])
  if key in seen:raise StoreError('duplicate_collection')
  seen.add(key)
  if c['kind'] not in ['policies','settings','assignments']:continue
  if c['kind']!='policies' and c['owner_id']!=chosen:continue
  base='https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'
  expected=base if c['kind']=='policies' else base+'/'+chosen+'/'+c['kind']
  if capture_errors(c,expected):raise StoreError('capture_invalid')
  records=[r for p in c['pages'] for r in p['body']['value']]
  ids=[r.get('id') for r in records]
  if len(set(ids))!=len(ids):raise StoreError('duplicate_observation')
  name={'policies':'observed-policy','settings':'observed-setting','assignments':'observed-assignment'}[c['kind']]
  for r in records:_validate(_contract(name),r)
  if c['kind']=='policies':policy=next((r for r in records if r['id']==chosen),None)
  if c['kind']=='settings':settings=records
 if not {('policies',None),('settings',chosen),('assignments',chosen)}<=seen or policy is None or settings is None:raise StoreError('capture_missing')
 if policy['settingCount']!=len(settings):raise StoreError('setting_count_mismatch')
 return policy

def _oracle(source,normalized,decision,files=None,extra=None):
 from reference.invariants import compare
 ctx={'tenant_id':decision['tenant_id'],'selected_policy_id':decision['selected_policy_id'],**(extra or {})}
 if compare(source,normalized,files=files,context=ctx):raise StoreError('independent_oracle_rejected')

def inspect(root,index_path='receipt-index.json'):
 """Reconstruct current facts; malformed receipts invalidate dependent milestones."""
 index=parse(read_bytes(root,index_path));_validate(_contract('receipt-index'),index)
 artifacts={};values={};data={};errors=[];seen_kinds=set()
 for a in index['artifacts']:
  if a['artifact_id'] in artifacts:raise StoreError('duplicate_artifact_id')
  if a['kind'] in seen_kinds:raise StoreError('duplicate_artifact_kind')
  seen_kinds.add(a['kind']);artifacts[a['artifact_id']]=a
 for d in index['decisions']:
  if any(x not in artifacts for x in d['source_artifact_ids']):raise StoreError('decision_source_missing')
 visiting=set();valid=set()
 def verify(key):
  if key in valid:return
  if key in visiting:raise StoreError('dependency_cycle')
  if key not in artifacts:raise StoreError('missing_dependency')
  visiting.add(key);a=artifacts[key]
  if a['producer_version']!='offline-workflow/2.0.0' or a['schema_id']!=a['kind']+'/2.0.0':raise StoreError('unknown_artifact_version')
  raw=read_bytes(root,a['relative_path'])
  if sha(raw)!=a['byte_sha256']:raise StoreError('artifact_hash_changed')
  value=_artifact_value(a['kind'],raw)
  expected_upstream={x for x,b in artifacts.items() if min(STAGES.index(s) for s,n in REQUIRED.items() if b['kind'] in n)<min(STAGES.index(s) for s,n in REQUIRED.items() if a['kind'] in n)}
  if not expected_upstream<=set(d['artifact_id'] for d in a['dependencies']):raise StoreError('missing_prerequisite_dependency')
  for dep in a['dependencies']:
   verify(dep['artifact_id'])
   if artifacts[dep['artifact_id']]['byte_sha256']!=dep['byte_sha256']:raise StoreError('dependency_hash_changed')
  if a['kind'] in values:raise StoreError('duplicate_artifact_kind')
  # Publish trust only after every validation and dependency check succeeds.
  visiting.remove(key);values[a['kind']]=value;data[a['kind']]=raw;valid.add(key)
 for key in artifacts:
  try:verify(key)
  except (StoreError,OSError,KeyError,TypeError):errors.append('artifact_unverified');visiting.clear()
 if len({r['milestone'] for r in index['milestone_receipts']})!=len(index['milestone_receipts']):raise StoreError('duplicate_milestone_receipt')
 current={k:None for k in FP};verified=[];mapping='unknown'
 # Derive each milestone independently, using only valid current bytes.
 for milestone in STAGES:
  try:
   if any(k not in values for k in REQUIRED[milestone]):raise StoreError('required_artifact_missing')
   if milestone=='repository':
    v=values['repository_context'];head=read_bytes(root,v['repository_path']+'/.git/HEAD').decode().strip()
    if head.startswith('ref: '):head=read_bytes(root,v['repository_path']+'/.git/'+head[5:]).decode().strip()
    if not re.fullmatch('[0-9a-f]{40}',head):raise StoreError('repository_head_invalid')
    repo=_path(root,v['repository_path']+'/.git/HEAD').parents[1]
    actual=set()
    for child in repo.rglob('*'):
     if '.git' in child.relative_to(repo).parts:continue
     if child.is_symlink():raise StoreError('symlink_repository_input')
     if child.is_file():actual.add(child.relative_to(Path(root).absolute()).as_posix())
    if set(v['inputs'])!=actual:raise StoreError('repository_input_closure_changed')
    current['repository_revision']=head;current['dirty_files_digest']=sha(canonical(_manifest_bytes(root,v['inputs'])))
   elif milestone=='source':
    d=values['decisions'];s=values['source']
    if read_bytes(root,d['source_path'])!=data['source'] or s['tenant_id']!=d['tenant_id'] or s['cloud']!=d['cloud']:raise StoreError('source_context_mismatch')
    current.update(source_kind=d['source_kind'],source_locator_digest=sha(canonical({'path':d['source_path']})),tenant_id=d['tenant_id'],cloud=d['cloud'])
   elif milestone=='inventory':
    _inventory(values['source'],values['decisions']);current['source_digest']=sha(canonical(values['source']))
    current['capture_contract_digest']=sha(canonical(_contract('capture')))
    current['exporter_contract_digest']=sha(canonical({'exporter':values['source']['exporter'],'contract':_contract('capture')}))
   elif milestone=='selection':
    d=values['decisions'];policy=_inventory(values['source'],d)
    if d['selected_ids']!=[policy['id']]:raise StoreError('selection_missing_or_mismatched')
    current['selected_ids_digest']=sha(canonical([{'tenant_id':d['tenant_id'],'family':'configurationPolicies','object_id':x} for x in sorted(d['selected_ids'])]))
   elif milestone=='ownership':
    d=values['decisions'];records=d['ownership']
    if {r['object_id'] for r in records}!=set(d['selected_ids']) or len(records)!=len(d['selected_ids']) or any(r['writer']!='this_repository' for r in records):raise StoreError('ownership_unknown_or_conflicting')
    current['ownership_digest']=sha(canonical(sorted(records,key=lambda r:r['object_id'])))
   elif milestone=='mapping':
    p=values['provider_evidence'];_oracle(data['source'],values['normalized'],values['decisions'])
    if (p['provider_source'],p['provider_version'],p['api_version'],p['engine_version'],p['atmos_version'])!=('deploymenttheory/microsoft365','1.0.0','beta','1.10.0','1.199.0'):raise StoreError('unqualified_provider_tool_contract')
    import hcl2
    from lark.exceptions import LarkError
    try:lock=hcl2.loads(read_bytes(root,p['lock_path']).decode())
    except LarkError:raise StoreError('provider_lock_parse_rejected') from None
    entries=[v for item in lock.get('provider',[]) for name,v in item.items() if name.strip(chr(34)).removeprefix('registry.terraform.io/')==p['provider_source']]
    if len(entries)!=1 or str(entries[0].get('version','')).strip(chr(34))!=p['provider_version']:raise StoreError('provider_lock_binding_mismatch')
    schema=parse(read_bytes(root,p['schema_path']))
    _validate(_obj({'schema_version':{'const':'2.0.0'},'provider_source':S,'provider_version':S,'api_version':{'const':'beta'},'qualification':{'const':'offline_configuration_only'},'contract_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'}}),schema)
    if any(schema[k]!=p[k] for k in ['provider_source','provider_version','api_version']) or schema['contract_sha256']!=sha(canonical(_contract('provider-settings'))):raise StoreError('provider_schema_binding_mismatch')
    current.update({k:p[k] for k in ['provider_source','provider_version','api_version','engine_version','atmos_version']})
    current['provider_lock_digest']=sha(read_bytes(root,p['lock_path']));current['provider_schema_digest']=sha(read_bytes(root,p['schema_path']))
    for name in ['engine','atmos']:
     if sha(read_bytes(root,p[name+'_path']))!=p[name+'_sha256']:raise StoreError('binary_changed')
    normalized=values['normalized'];mapping='complete' if normalized['offline_mapping_complete'] else 'partial'
   elif milestone in ['generation','validation','review']:
    manifest=values['generation'];files={}
    declared=set(manifest['files'])
    tops={PurePosixPath(p).parts[0] for p in declared if len(PurePosixPath(p).parts)>1}
    for top in tops:
     directory=Path(root).absolute()/top
     if directory.is_symlink():raise StoreError('symlink_generated_directory')
     if directory.exists():
      for child in directory.rglob('*'):
       if child.is_symlink():raise StoreError('symlink_generated_input')
       if child.is_file() and child.relative_to(Path(root).absolute()).as_posix() not in declared:raise StoreError('unowned_generated_input')
    protected={p for p in Path(root).glob('*') if p.is_file() and (p.name.endswith(('.tf','.tf.json','.tfvars','.tfvars.json','.hcl')) or p.name in ['.terraformrc','terraform.rc'])}
    allowed_root=set(declared)
    if 'provider_evidence' in values:allowed_root.add(values['provider_evidence']['lock_path'])
    if any(p.name not in allowed_root for p in protected):raise StoreError('unowned_root_configuration')
    for path,digest in manifest['files'].items():
     raw=read_bytes(root,path)
     if sha(raw)!=digest:raise StoreError('generated_file_changed')
     files[path]=raw.decode('utf-8')
    extra={}
    if 'provider_evidence' in values:extra.update({k:values['provider_evidence'][k] for k in ['provider_source','provider_version','engine_version','atmos_version']})
    if 'effective_config' in values:extra.update({k:values['effective_config'][k] for k in ['component','stack']})
    extra.update(cloud=values['decisions']['cloud'],engine='tofu')
    _oracle(data['source'],values['normalized'],values['decisions'],files,extra)
    current['generated_files_digest']=sha(canonical({'manifest_byte_sha256':sha(data['generation']),'files':_manifest_bytes(root,list(files))}))
    if milestone=='generation':
     e=values['effective_config'];b=values['identity_context'];current.update(component=e['component'],stack=e['stack'],backend_identity_digest=sha(canonical(b['backend'])),identity_digest=sha(canonical(b['identity'])))
     if e['component']!=b['component'] or e['stack']!=b['stack'] or b['tenant_id']!=current['tenant_id'] or b['cloud']!=current['cloud']:raise StoreError('target_mismatch')
     if b['git_revision']!=current['repository_revision'] or b['relevant_dirty_files_digest']!=current['dirty_files_digest']:raise StoreError('repository_binding_mismatch')
     for key in ['source_digest','selected_ids_digest','ownership_digest','provider_source','provider_version','provider_lock_digest','engine_version','atmos_version']:
      if current[key] is None or b[key]!=current[key]:raise StoreError('binding_input_mismatch')
     p=values['provider_evidence']
     if b['engine_binary_sha256']!=p['engine_sha256'] or b['atmos_binary_sha256']!=p['atmos_sha256']:raise StoreError('binding_binary_mismatch')
     must_include={a['relative_path'] for a in artifacts.values() if a['kind'] not in ['identity_context','effective_config','review','validation']}|set(files)|set(values['repository_context']['inputs'])|{p['lock_path'],p['schema_path'],p['engine_path'],p['atmos_path']}
     if not must_include<=set(e['inputs']):raise StoreError('effective_input_closure_incomplete')
     target={k:b[k] for k in ['cloud','tenant_id','subscription_id','service_endpoint','identity','backend','component','stack']}
     closure={'files':_manifest_bytes(root,e['inputs']),'resolved_inputs':e['resolved_inputs'],'target':target,'schema_version':'2.0.0'};current['configuration_digest']=sha(canonical(closure))
     if b['configuration_digest']!=current['configuration_digest']:raise StoreError('configuration_binding_mismatch')
    if milestone=='review':
     review=values['review'];cohort=parse(read_bytes(root,review['cohort_path']))
     # Cohort has explicit collection scope and capture expiry, not a digest-only assertion.
     _validate(_obj({'schema_version':{'const':'2.0.0'},'tenant_id':GUID,'object_id':GUID,'captured_at':{'type':'string','format':'date-time'},'expires_at':{'type':'string','format':'date-time'},'members':{'type':'array','items':GUID,'uniqueItems':True}}),cohort)
     from datetime import datetime,timezone
     if datetime.now(timezone.utc)>=datetime.fromisoformat(cohort['expires_at'].replace('Z','+00:00')):raise StoreError('cohort_expired')
     if cohort['tenant_id']!=current['tenant_id'] or cohort['object_id']!=values['decisions']['selected_policy_id']:raise StoreError('cohort_target_mismatch')
     current['cohort_digest']=sha(canonical(cohort));current['plan_digest']=sha(read_bytes(root,review['plan_path']))
     b=values['identity_context']
     if b['cohort_digest']!=current['cohort_digest'] or b['plan_digest']!=current['plan_digest']:raise StoreError('review_binding_mismatch')
   # Facts at this frontier and every earlier one must exist, never null.
   if any(current[k] is None for k,i in FP.items() if i<=STAGES.index(milestone)):raise StoreError('unknown_prerequisite_fact')
   # Every required artifact must be named by the receipt, with dependency edges
   # closing over earlier prerequisite artifacts. A matching string is insufficient.
   if any(s not in verified for s in STAGES[:STAGES.index(milestone)]):raise StoreError('prerequisite_receipt_unverified')
   receipt=next((r for r in index['milestone_receipts'] if r['milestone']==milestone),None)
   required={k for k,a in artifacts.items() if a['kind'] in REQUIRED[milestone]}
   if receipt is None or not required<=set(receipt['artifact_ids']) or any(x not in valid for x in receipt['artifact_ids']):raise StoreError('milestone_receipt_missing')
   if any(receipt['fingerprints'][k]!=current[k] for k,i in FP.items() if i<=STAGES.index(milestone)):raise StoreError('receipt_fingerprint_changed')
   verified.append(milestone)
  except (StoreError,OSError,ValueError,KeyError,TypeError,ImportError):errors.append('milestone_unverified:'+milestone)
 return {'fingerprints':current,'verified_completed':verified,'mapping_status':mapping,'errors':sorted(set(errors)),'lifecycle':index['lifecycle'],'last_stable_state':index['last_stable_state'],'external_execution':False,'authorization_reused':False}

def _create(root,saved_state='repository_inspection',artifacts=(),lifecycle='suspended',decisions=()):
 """Record local artifact bytes and compute eligible completion receipts.

Artifacts are (kind, relative_path) pairs; dependencies are generated from the
fixed prerequisite graph. Existing session/index bytes are never overwritten.
"""
 root=Path(root);root.mkdir(parents=True,exist_ok=True)
 if saved_state not in MAP['state_frontier']:raise StoreError('unstable_or_unknown_saved_state')
 if lifecycle not in ['active','suspended','cancelled']:raise StoreError('invalid_lifecycle')
 if any((root/p).exists() or (root/p).is_symlink() for p in ['session.json','receipt-index.json']):raise StoreError('session_already_exists')
 rows=[];kinds=set()
 for kind,path in artifacts:
  if kind in kinds:raise StoreError('duplicate_artifact_kind')
  kinds.add(kind);raw=read_bytes(root,path);_artifact_value(kind,raw)
  rows.append({'artifact_id':kind,'kind':kind,'relative_path':path,'byte_sha256':sha(raw),'schema_id':kind+'/2.0.0','producer_version':'offline-workflow/2.0.0','dependencies':[],'assurance':'observed_local'})
 rank={k:min(STAGES.index(s) for s,needed in REQUIRED.items() if k in needed) for k in kinds}
 for a in rows:
  a['dependencies']=[{'artifact_id':b['artifact_id'],'byte_sha256':b['byte_sha256']} for b in rows if rank[b['kind']]<rank[a['kind']]]
 if not decisions and 'decisions' in kinds:
  d=_artifact_value('decisions',read_bytes(root,next(a['relative_path'] for a in rows if a['kind']=='decisions')))
  decisions=[{'question_id':'input_source','choice_id':d['source_kind'],'selected_object_ids':d['selected_ids'],'source_artifact_ids':['source'],'record_kind':'developer_supplied'}]
 idx={'schema_version':'2.0.0','lifecycle':lifecycle,'last_stable_state':saved_state,'artifacts':rows,'decisions':list(decisions),'milestone_receipts':[]}
 _validate(_contract('receipt-index'),idx);_write(root,'receipt-index.json',idx)
 try:
  facts=inspect(root);current=facts['fingerprints']
  idx['milestone_receipts']=[{'milestone':s,'artifact_ids':[a['artifact_id'] for a in rows if a['kind'] in REQUIRED[s]],'fingerprints':current.copy(),'assurance':'observed_local'} for s in STAGES if all(k in kinds for k in REQUIRED[s])]
  _write(root,'receipt-index.json',idx);verified=inspect(root)
  idx['milestone_receipts']=[r for r in idx['milestone_receipts'] if r['milestone'] in verified['verified_completed']]
  digest=_write(root,'receipt-index.json',idx)
  session={'schema_version':'2.0.0','session_id':str(uuid.uuid4()),'saved_state':saved_state,'completed':verified['verified_completed'],'fingerprints':current,'mapping_status':verified['mapping_status'],'in_flight_outcome':'none','authorization_persisted':False,'artifact_index':{'relative_path':'receipt-index.json','byte_sha256':digest}}
  _validate(_contract('session-state'),session);_write(root,'session.json',session);return session
 except Exception:
  # Remove only our newly created metadata; input/output artifacts are untouched.
  (root/'receipt-index.json').unlink(missing_ok=True);raise

def resume(root,local_resume=False):
 """Revalidate on explicit local intent. Never persists or reuses an approval."""
 def blocked(reason):return {'next_state':MAP['fallback'],'milestone_index':0,'reasons':[reason],'external_execution':False,'authorization_reused':False}
 try:
  session=parse(read_bytes(root,'session.json'));_validate(_contract('session-state'),session)
  locator=session['artifact_index']
  if locator is None:return blocked('receipt_index_missing')
  raw=read_bytes(root,locator['relative_path'])
  if sha(raw)!=locator['byte_sha256']:return blocked('receipt_index_hash_changed')
  idx=parse(raw)
  if idx['last_stable_state']!=session['saved_state']:return blocked('stable_state_mismatch')
  if idx['lifecycle']=='cancelled' and not local_resume:return {'next_state':'cancelled','milestone_index':MAP['state_frontier'][session['saved_state']],'reasons':['explicit_local_resume_required'],'external_execution':False,'authorization_reused':False}
  if not local_resume:return {'next_state':'suspended','milestone_index':MAP['state_frontier'][session['saved_state']],'reasons':['explicit_local_resume_required'],'external_execution':False,'authorization_reused':False}
  facts=inspect(root,locator['relative_path'])
  result=resume_decision(session,facts['fingerprints'],facts['verified_completed'],facts['mapping_status'])
  result['receipt_errors']=facts['errors'];return result
 except (StoreError,OSError,ValueError,KeyError,TypeError):return blocked('session_or_receipt_corrupt')

def set_lifecycle(root,lifecycle):
 if lifecycle not in ['active','suspended','cancelled']:raise StoreError('invalid_lifecycle')
 session=parse(read_bytes(root,'session.json'));_validate(_contract('session-state'),session)
 if session['saved_state'] not in MAP['state_frontier']:raise StoreError('transient_state_not_progress')
 locator=session['artifact_index']
 if locator is None:raise StoreError('receipt_index_missing')
 raw=read_bytes(root,locator['relative_path'])
 if sha(raw)!=locator['byte_sha256']:raise StoreError('receipt_index_hash_changed')
 idx=parse(raw);_validate(_contract('receipt-index'),idx)
 if idx['last_stable_state']!=session['saved_state']:raise StoreError('stable_state_mismatch')
 idx['lifecycle']=lifecycle;idx['last_stable_state']=session['saved_state'];session['authorization_persisted']=False
 locator['byte_sha256']=_write(root,locator['relative_path'],idx);_write(root,'session.json',session)


def create(root,saved_state='repository_inspection',artifacts=(),lifecycle='suspended',decisions=()):
 """Exclusive local creation; a concurrent creator cannot replace our metadata."""
 root=Path(root);root.mkdir(parents=True,exist_ok=True)
 lock=_path(root,'.workflow-create.lock',False)
 try:fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 except OSError:raise StoreError('session_creation_in_progress') from None
 try:
  os.close(fd)
  return _create(root,saved_state,artifacts,lifecycle,decisions)
 finally:lock.unlink(missing_ok=True)
