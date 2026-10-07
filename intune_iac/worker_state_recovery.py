"""Narrow description-only repair after independently explained provider drift.

The ordinary computed-state contract remains unchanged. This profile retains
three explicit baselines and never grants execution authority or pushes state.
"""
from __future__ import annotations
from datetime import datetime
import hashlib,os,re,time
from intune_iac.io import AppError,canonical,digest,parse_json
from intune_iac import worker_state as state,worker_precondition as pc
from intune_iac.observation_reader import CapturedObservation

VERSION='settings-catalog-description-recovery/1'
ATTRIBUTES=frozenset({'assignments','created_date_time','description','id','is_assigned','last_modified_date_time','name','platforms','role_scope_tag_ids','settings','settings_catalog_template_type','settings_count','technologies','timeouts'})
DRIFT=frozenset({'description','last_modified_date_time'})

def _fail(code):raise AppError(code,'The bounded description-recovery state could not be independently matched to persisted state, provider refresh and the observed object.') from None

def _copy(value):return parse_json(canonical(value))
def _equal(a,b):return canonical(a)==canonical(b)
def _time(value):
 if type(value) is not str:_fail('recovery_state_timestamp')
 try:
  stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
  if stamp.tzinfo is None:raise ValueError()
 except ValueError:_fail('recovery_state_timestamp')
 return stamp.replace(microsecond=0).isoformat(timespec='seconds').replace('+00:00','Z')

def _project(raw):
 """Versioned pinned native attribute projection, with all source bytes retained."""
 normalized=pc._lossless(raw);policy=raw['policy'];assignments=[]
 for row in raw['assignments']:
  if row.get('source')!='direct' or row.get('sourceId') is not None:_fail('recovery_state_assignment_unsupported')
  target=row['target'];kind=target.get('@odata.type')
  if set(target)!={'@odata.type','groupId','deviceAndAppManagementAssignmentFilterId','deviceAndAppManagementAssignmentFilterType'} or kind not in ('#microsoft.graph.groupAssignmentTarget','#microsoft.graph.exclusionGroupAssignmentTarget'):
   _fail('recovery_state_assignment_unsupported')
  if any(type(target[key]) is not str for key in target):_fail('recovery_state_assignment_unsupported')
  if target['deviceAndAppManagementAssignmentFilterType'] not in ('none','include','exclude') or any(not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',target[key]) for key in ('groupId','deviceAndAppManagementAssignmentFilterId')):_fail('recovery_state_assignment_unsupported')
  assignments.append({'type':kind.removeprefix('#microsoft.graph.'),'group_id':target['groupId'],'filter_id':target['deviceAndAppManagementAssignmentFilterId'],'filter_type':target['deviceAndAppManagementAssignmentFilterType']})
 if type(policy.get('isAssigned')) is not bool or policy['isAssigned']!=bool(assignments):_fail('recovery_state_projection_invalid')
 if 'templateReference' in policy:_fail('recovery_state_template_unsupported')
 # This projection does not drop unknown settings, alter IDs, omit nulls, or sort
 # ordered arrays. The separate gate preserves all raw policy/assignment fields.
 return {'id':policy['id'],'name':policy['name'],'description':policy['description'],'platforms':policy['platforms'],'technologies':[policy['technologies']],
  'created_date_time':_time(policy['createdDateTime']),'last_modified_date_time':_time(policy['lastModifiedDateTime']),
  'is_assigned':policy['isAssigned'],'role_scope_tag_ids':sorted(policy['roleScopeTagIds']),'settings_count':policy['settingCount'],
  'settings':{'settings':raw['settings']},'assignments':sorted(assignments,key=canonical),'settings_catalog_template_type':'','timeouts':None}

def _attributes_match(actual,expected):
 if type(actual) is not dict or set(actual)!=ATTRIBUTES:_fail('recovery_state_attribute_schema')
 value=_copy(actual)
 if type(value['settings']) is not str:_fail('recovery_state_settings_type')
 try:value['settings']=parse_json(value['settings'].encode())
 except AppError:_fail('recovery_state_settings_type')
 if type(value['assignments']) is not list or type(value['role_scope_tag_ids']) is not list:_fail('recovery_state_attribute_schema')
 value['assignments']=sorted(value['assignments'],key=canonical);value['role_scope_tag_ids']=sorted(value['role_scope_tag_ids'])
 if not _equal(value,expected):_fail('recovery_state_refresh_not_observed')

class DescriptionRecoveryStateWriteContract:
 """One existing object; description/timestamp drift; description-only repair."""
 def __init__(self,*,baseline_raw,plan_json_raw,saved_plan_sha256,execution_binding_sha256,preimage,precondition):
  if type(baseline_raw) is not bytes or type(plan_json_raw) is not bytes or not 0<len(baseline_raw)<=16*1024*1024 or not 0<len(plan_json_raw)<=16*1024*1024:_fail('recovery_state_input')
  if type(preimage) is not CapturedObservation or type(precondition) not in (pc.LiveGraphPrecondition,pc.LaboratoryGraphPrecondition):_fail('recovery_state_capture_required')
  batch,source=state._capture(preimage);gate=precondition.binding()
  if gate['execution_binding_sha256']!=execution_binding_sha256 or gate['preimage_capture_sha256']!=batch['capture_sha256'] or canonical(gate['identity'])!=canonical(source['identity']):_fail('recovery_state_capture_binding')
  if not 0<=time.time()-batch['observed_at']<=30:_fail('recovery_state_capture_stale')
  before,plan=parse_json(baseline_raw),parse_json(plan_json_raw)
  try:
   if len(before['resources'])!=1 or len(before['resources'][0]['instances'])!=1 or len(plan['resource_changes'])!=1 or len(plan['resource_drift'])!=1:_fail('recovery_state_scope')
   resource=before['resources'][0];instance=resource['instances'][0];persisted=instance['attributes'];change=plan['resource_changes'][0];drift=plan['resource_drift'][0];action=change['change'];dc=drift['change'];refreshed=dc['after']
   address=state.RESOURCE+'.'+resource['name']
   for item in (change,drift):
    if item.get('address')!=address or item.get('mode')!='managed' or item.get('type')!=state.RESOURCE or item.get('name')!=resource['name'] or item.get('provider_name')!=state.PROVIDER or any(item.get(k) is not None for k in ('previous_address','deposed','index','module_address')):_fail('recovery_state_scope')
   if dc.get('actions')!=['update'] or dc.get('importing') is not None or not _equal(dc.get('before'),persisted) or not state.NativeStateWriteContract._known(dc.get('after_unknown',{})):_fail('recovery_state_drift_before')
   if type(refreshed) is not dict or set(refreshed)!=set(persisted) or set(persisted)!=ATTRIBUTES:_fail('recovery_state_attribute_schema')
   if not _equal(action.get('before'),refreshed):_fail('recovery_state_refresh_mismatch')
   changed={k for k in persisted if not _equal(persisted[k],refreshed[k])}
   if 'description' not in changed or not changed<=DRIFT:_fail('recovery_state_drift_not_bounded')
   if type(persisted['description']) not in (str,type(None)) or type(refreshed['description']) not in (str,type(None)) or type(action['after'].get('description')) not in (str,type(None)):_fail('recovery_state_description_type')
   if _time(refreshed['last_modified_date_time'])!=refreshed['last_modified_date_time'] or not pc._timestamp(persisted['last_modified_date_time'])<=pc._timestamp(refreshed['last_modified_date_time'])<=time.time()+60:_fail('recovery_state_timestamp')
   for key in ('before_identity','after_identity'):
    if dc.get(key)!=instance['identity']:_fail('recovery_state_identity')
   prior=plan['prior_state']
   if prior.get('format_version')!='1.0' or prior.get('terraform_version')!='1.13.1' or set(prior['values'])!={'root_module'} or set(prior['values']['root_module'])!={'resources'} or len(prior['values']['root_module']['resources'])!=1:_fail('recovery_state_prior')
   pr=prior['values']['root_module']['resources'][0]
   if (pr.get('address')!=address or pr.get('mode')!='managed' or pr.get('type')!=state.RESOURCE or pr.get('name')!=resource['name'] or pr.get('provider_name')!=state.PROVIDER or pr.get('identity')!=instance['identity'] or type(pr.get('identity_schema_version')) is not int or pr['identity_schema_version']!=0 or type(pr.get('schema_version')) is not int or pr['schema_version']!=0 or not _equal(pr.get('values'),refreshed)):_fail('recovery_state_prior')
   _attributes_match(refreshed,_project(batch['source']['raw_observed']))
   after=action['after']
   if set(after)!=ATTRIBUTES-state.COMPUTED or after['description']==refreshed['description'] or any(not _equal(after[k],refreshed[k]) for k in after if k!='description'):_fail('recovery_state_change_not_description_only')
   # The approved Graph payload must describe exactly the plan's one change.
   desired_raw=_copy(batch['source']['raw_observed']);desired_raw['policy']['description']=after['description']
   expected_policy={k:desired_raw['policy'][k] for k in ('name','description','platforms','technologies','roleScopeTagIds')};expected_policy['settings']=desired_raw['settings']
   expected_assign={'assignments':[{'target':{'@odata.type':'#microsoft.graph.'+row['type'],'groupId':row['group_id'],'deviceAndAppManagementAssignmentFilterId':row['filter_id'],'deviceAndAppManagementAssignmentFilterType':row['filter_type']}} for row in after['assignments']]}
   if digest({'policy':expected_policy,'assignments':expected_assign})!=gate['approved_projection_sha256']:_fail('recovery_state_approved_projection')
  except (KeyError,TypeError,IndexError,AttributeError):_fail('recovery_state_schema')
  # Validate the existing fully constrained native renderer with a recorded
  # refreshed projection. The original plan/drift is retained and bound below;
  # this derived input is never serialized as a replacement saved plan.
  projected=_copy(before);projected['resources'][0]['instances'][0]['attributes']=_copy(refreshed)
  checked_plan=_copy(plan);checked_plan.pop('resource_drift')
  self._inner=state.ComputedNativeStateWriteContract(baseline_raw=canonical(projected),plan_json_raw=canonical(checked_plan),saved_plan_sha256=saved_plan_sha256,execution_binding_sha256=execution_binding_sha256,preimage=preimage,precondition=precondition)
  binding=self._inner.binding();binding.update(schema_version='description-recovery-native-state-contract/1',profile=VERSION,
   baseline_sha256=hashlib.sha256(baseline_raw).hexdigest(),plan_json_sha256=hashlib.sha256(plan_json_raw).hexdigest(),
   persisted_attributes_sha256=digest(persisted),provider_refreshed_attributes_sha256=digest(refreshed),
   provider_resource_drift_sha256=digest(drift),provider_prior_state_sha256=digest(prior),
   checked_refreshed_state_sha256=digest(projected),checked_derived_plan_sha256=digest(checked_plan),
   admitted_drift_attributes=sorted(changed),approved_changed_attributes=['description'],
   inner_contract_sha256=digest(self._inner.binding()),normalization_profile=VERSION)
  self._binding=binding;self._digest=digest(binding);self.pid=os.getpid();self.execution_binding_sha256=execution_binding_sha256
 def binding(self):
  if self.pid!=os.getpid() or digest(self._binding)!=self._digest or digest(self._inner.binding())!=self._binding['inner_contract_sha256'] or self.execution_binding_sha256!=self._binding['execution_binding_sha256']:_fail('recovery_state_contract_changed')
  return _copy(self._binding)
 def admit(self,candidate_raw,*,completion):
  binding=self.binding();result=self._inner.admit(candidate_raw,completion=completion)
  result.update(schema_version='description-recovery-native-state-admission/1',contract_sha256=digest(binding),profile=VERSION,
   persisted_baseline_sha256=binding['baseline_sha256'],provider_refreshed_attributes_sha256=binding['provider_refreshed_attributes_sha256'],provider_resource_drift_sha256=binding['provider_resource_drift_sha256'])
  return result
