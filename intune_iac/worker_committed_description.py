"""Closed linkage proof for the original signed description-recovery contract."""
import hashlib
from . import worker_state as state,worker_precondition as pc
from .worker_state_recovery import VERSION,ATTRIBUTES,DRIFT,_copy,_equal,_time,_project,_attributes_match,_fail
from .io import AppError,canonical,digest,parse_json
import time

EXTENSION_FIELDS=frozenset({'persisted_attributes_sha256','provider_refreshed_attributes_sha256','provider_resource_drift_sha256','provider_prior_state_sha256','checked_refreshed_state_sha256','checked_derived_plan_sha256','admitted_drift_attributes','approved_changed_attributes','inner_contract_sha256','normalization_profile'})
BASE_FIELDS=frozenset({'schema_version','profile','execution_binding_sha256','baseline_sha256','plan_json_sha256','saved_plan_sha256','admission_template_sha256','resource_address','tenant_id','object_id','reader_identity_sha256','preimage_capture_sha256','precondition_binding_sha256','computed_attributes','source_evidence_class','management_mapping_status','management_mapping_blockers','execution_authorized','service_freshness_atomic'})

def validate_description_linkage(*,contract,baseline_raw,plan_json_raw,preimage_raw,gate):
  if (type(contract) is not dict or set(contract)!=BASE_FIELDS|EXTENSION_FIELDS or contract['schema_version']!='description-recovery-native-state-contract/1'
      or contract['profile']!=VERSION or contract['normalization_profile']!=VERSION or contract['computed_attributes']!=sorted(state.COMPUTED)
      or contract['approved_changed_attributes']!=['description']):_fail('committed_description_contract_schema')
  for raw,expected in ((baseline_raw,contract['baseline_sha256']),(plan_json_raw,contract['plan_json_sha256']),(preimage_raw,gate['preimage_raw_sha256'])):
    if type(raw) is not bytes or not 0<len(raw)<=16*1024*1024 or hashlib.sha256(raw).hexdigest()!=expected:_fail('committed_description_original_artifact')
  before,plan=parse_json(baseline_raw),parse_json(plan_json_raw)
  batch={'source':{'raw_observed':parse_json(preimage_raw)}}
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
  projected=_copy(before);projected['resources'][0]['instances'][0]['attributes']=_copy(refreshed)
  checked_plan=_copy(plan);checked_plan.pop('resource_drift')
  expected={'persisted_attributes_sha256':digest(persisted),'provider_refreshed_attributes_sha256':digest(refreshed),
      'provider_resource_drift_sha256':digest(drift),'provider_prior_state_sha256':digest(prior),
      'checked_refreshed_state_sha256':digest(projected),'checked_derived_plan_sha256':digest(checked_plan),
      'admitted_drift_attributes':sorted(changed),'approved_changed_attributes':['description'],'normalization_profile':VERSION}
  if any(contract[key]!=value for key,value in expected.items()):_fail('committed_description_linkage_mismatch')
  inner={key:_copy(value) for key,value in contract.items() if key not in EXTENSION_FIELDS}
  inner.update(schema_version='computed-native-state-write-contract/1.0',profile='pinned_settings_catalog_update_with_two_independent_computed_fields',
      baseline_sha256=digest(projected),plan_json_sha256=digest(checked_plan))
  if digest(inner)!=contract['inner_contract_sha256']:_fail('committed_description_inner_binding_mismatch')
  return {'schema_version':'committed-description-contract-proof/1','original_contract_sha256':digest(contract),
      'inner_contract_sha256':digest(inner),'original_template_sha256':contract['admission_template_sha256'],
      'persisted_baseline_sha256':contract['baseline_sha256'],'checked_refreshed_state_sha256':digest(projected),
      'checked_derived_plan_sha256':digest(checked_plan),'original_native_plan_sha256':contract['saved_plan_sha256'],
      'original_plan_json_sha256':contract['plan_json_sha256'],'execution_authorized':False}
