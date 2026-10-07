"""Independent expected values and known-bad controls for exact native drift plan."""
import copy,hashlib,json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from intune_iac import worker_state_recovery as recovery
from intune_iac import observation_reader as rd,worker_precondition as pc,worker_state as ordinary
from intune_iac.observation_jobs import _Fixture
from intune_iac.identity_binding import ClientSecretHandle
from intune_iac.io import AppError,canonical,digest
FIXTURE=Path(__file__).resolve().parents[1]/'labs/worker-recovery/description-native-fixture'
TENANT='11111111-1111-1111-1111-111111111111';OID='33333333-3333-4333-8333-333333333333';CLIENT='88888888-8888-4888-8888-888888888888';PRINCIPAL='99999999-9999-4999-8999-999999999999'

class DescriptionRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.before=json.loads((FIXTURE/'persisted-state.json').read_bytes());self.plan=json.loads((FIXTURE/'native-plan.json').read_bytes());self.graph=json.loads((FIXTURE/'observed-graph.json').read_bytes())
 def gate(self,mutate=None):
  graph=copy.deepcopy(self.graph)
  if mutate:mutate(graph)
  completed=copy.deepcopy(graph);completed['policy']['description']='Fixture only'
  prefix=[{'method':'POST','host':'login.microsoftonline.com','path':'/'+TENANT+'/oauth2/v2.0/token','status':200,'body':{'token_type':'Bearer','expires_in':3600,'access_token':'SYNTHETIC-READER-ONLY'}},{'method':'GET','host':'graph.microsoft.com','path':"/v1.0/servicePrincipals(appId='"+CLIENT+"')?$select=id,appId,accountEnabled",'status':200,'body':{'id':PRINCIPAL,'appId':CLIENT,'accountEnabled':True}}]
  for capture in (graph,graph,completed,completed):
   for path,body in [('/beta/deviceManagement/configurationPolicies',{'value':[capture['policy']]}),('/beta/deviceManagement/configurationPolicies/'+OID+'/settings',capture['settings']),('/beta/deviceManagement/configurationPolicies/'+OID+'/assignments',{'value':capture['assignments']})]:prefix.append({'method':'GET','host':'graph.microsoft.com','path':path,'status':200,'body':body})
  transport=_Fixture(canonical({'schema_version':'intune-observer-fixture/1','responses':prefix}));secret=ClientSecretHandle('SYNTHETIC-COLLECTOR-SECRET');self.addCleanup(secret.close)
  reader=rd.bind_laboratory_reader(rd.ReaderSpec(TENANT,CLIENT,PRINCIPAL,(OID,)),credential=secret,transport=transport);self.addCleanup(reader.close)
  captured=reader.capture(OID,self.root/'capture');put=json.loads((FIXTURE/'approved-policy.json').read_bytes());assign=(FIXTURE/'approved-assignments.json').read_bytes()
  gate=pc.create_laboratory_precondition(reader=reader,preimage=captured,execution_binding_sha256='a'*64,approved_policy_body=canonical(put),approved_assignment_body=assign,evidence_root=self.root/'gate');self.addCleanup(gate.close)
  return gate,captured,canonical(put),assign
 def contract(self,gate,captured):return recovery.DescriptionRecoveryStateWriteContract(baseline_raw=canonical(self.before),plan_json_raw=canonical(self.plan),saved_plan_sha256=json.loads((FIXTURE/'manifest.json').read_bytes())['saved_plan_sha256'],execution_binding_sha256='a'*64,preimage=captured,precondition=gate)
 def reject(self,action):
  with self.assertRaises(AppError):action()
 def complete(self,gate,put,assign):
  gate.check_before_mutation(stage='policy',request_body=put);gate.check_before_mutation(stage='assignments',request_body=assign);return gate.completion()
 def candidate(self):
  value=copy.deepcopy(self.before);value['serial']=14;value['resources'][0]['instances'][0]['attributes']['description']='Fixture only';value['resources'][0]['instances'][0]['attributes']['last_modified_date_time']='2026-10-07T20:52:15Z'
  value['check_results']=[{'object_kind':'var','config_addr':'var.'+name,'status':'pass','objects':[{'object_addr':'var.'+name,'status':'pass'}]} for name in ['stage']]
  return value
 def test_exact_native_plan_and_independent_capture_admit_restoration(self):
  gate,captured,put,assign=self.gate();contract=self.contract(gate,captured);done=self.complete(gate,put,assign)
  # Native plan variables come from the retained actual plan; expected checks
  # use its exact independently inspected names, not the product projection.
  self.assertEqual([r['address']['name'] for r in self.plan['checks']],['stage'])
  result=contract.admit(canonical(self.candidate()),completion=done);binding=contract.binding()
  self.assertEqual(binding['admitted_drift_attributes'],['description','last_modified_date_time']);self.assertEqual(binding['baseline_sha256'],digest(self.before));self.assertNotEqual(binding['persisted_attributes_sha256'],binding['provider_refreshed_attributes_sha256']);self.assertFalse(result['execution_authorized'])
 def test_ordinary_profile_still_rejects_same_native_drift(self):
  gate,captured,_,_=self.gate();self.reject(lambda:ordinary.ComputedNativeStateWriteContract(baseline_raw=canonical(self.before),plan_json_raw=canonical(self.plan),saved_plan_sha256='b'*64,execution_binding_sha256='a'*64,preimage=captured,precondition=gate))
 def test_drift_before_must_match_persisted_bytes(self):
  gate,captured,_,_=self.gate();self.plan['resource_drift'][0]['change']['before']['description']='fabricated';self.reject(lambda:self.contract(gate,captured))
 def test_drift_after_must_match_resource_before(self):
  gate,captured,_,_=self.gate();self.plan['resource_drift'][0]['change']['after']['description']='fabricated';self.reject(lambda:self.contract(gate,captured))
 def test_provider_prior_state_must_match_same_refreshed_object(self):
  gate,captured,_,_=self.gate();self.plan['prior_state']['values']['root_module']['resources'][0]['values']['id']='foreign';self.reject(lambda:self.contract(gate,captured))
 def test_native_schema_version_preserves_integer_type(self):
  gate,captured,_,_=self.gate();self.plan['prior_state']['values']['root_module']['resources'][0]['schema_version']=False;self.reject(lambda:self.contract(gate,captured))
 def test_refreshed_id_and_native_identity_cannot_change(self):
  gate,captured,_,_=self.gate();self.plan['resource_drift'][0]['change']['after_identity']['id']='foreign';self.reject(lambda:self.contract(gate,captured))
 def test_new_resource_or_untargeted_drift_cannot_enter_profile(self):
  gate,captured,_,_=self.gate();self.plan['resource_drift'].append(copy.deepcopy(self.plan['resource_drift'][0]));self.reject(lambda:self.contract(gate,captured))
 def test_settings_drift_is_not_admitted_as_description_repair(self):
  gate,captured,_,_=self.gate();self.plan['resource_drift'][0]['change']['after']['settings']='{}';self.plan['resource_changes'][0]['change']['before']['settings']='{}';self.reject(lambda:self.contract(gate,captured))
 def test_capture_setting_id_is_independently_compared(self):
  gate,captured,_,_=self.gate(lambda g:g['settings']['value'][0].update(id='0'));self.reject(lambda:self.contract(gate,captured))
 def test_capture_null_and_absent_are_distinct(self):
  gate,captured,_,_=self.gate(lambda g:g['settings']['value'][0]['settingInstance'].pop('settingInstanceTemplateReference'));self.reject(lambda:self.contract(gate,captured))
 def test_capture_setting_type_is_independently_compared(self):
  gate,captured,_,_=self.gate(lambda g:g['settings']['value'][0]['settingInstance']['choiceSettingValue'].update(value=2));self.reject(lambda:self.contract(gate,captured))
 def test_capture_assignment_filter_is_independently_compared(self):
  gate,captured,_,_=self.gate(lambda g:g['assignments'][0]['target'].update(deviceAndAppManagementAssignmentFilterType='exclude'));self.reject(lambda:self.contract(gate,captured))
 def test_capture_exclusion_is_independently_compared(self):
  gate,captured,_,_=self.gate(lambda g:g['assignments'][1]['target'].update({'@odata.type':'#microsoft.graph.groupAssignmentTarget'}));self.reject(lambda:self.contract(gate,captured))
 def test_capture_scope_tags_are_independently_compared(self):
  gate,captured,_,_=self.gate(lambda g:g['policy'].update(roleScopeTagIds=['1']));self.reject(lambda:self.contract(gate,captured))
 def test_description_numeric_value_rejected(self):
  gate,captured,_,_=self.gate();self.plan['resource_changes'][0]['change']['after']['description']=1;self.reject(lambda:self.contract(gate,captured))
 def test_extra_desired_assignment_change_rejected(self):
  gate,captured,_,_=self.gate();self.plan['resource_changes'][0]['change']['after']['assignments'][0]['filter_type']='exclude';self.reject(lambda:self.contract(gate,captured))
 def test_extra_computed_unknown_rejected(self):
  gate,captured,_,_=self.gate();self.plan['resource_changes'][0]['change']['after_unknown']['description']=True;self.reject(lambda:self.contract(gate,captured))
 def test_raw_json_cannot_supply_capture(self):
  gate,captured,_,_=self.gate();self.reject(lambda:self.contract(gate,captured.verified()[0]))
 def test_final_metadata_lineage_serial_and_settings_remain_exact(self):
  gate,captured,put,assign=self.gate();contract=self.contract(gate,captured);done=self.complete(gate,put,assign)
  edits=[lambda v:v.update(lineage='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'),lambda v:v.update(serial=15),lambda v:v['resources'][0]['instances'][0].update(private='fake'),lambda v:v['resources'][0]['instances'][0]['attributes'].update(settings='{}'),lambda v:v['resources'][0]['instances'][0].update(identity={'id':'foreign'})]
  for edit in edits:
   with self.subTest(edit=edit):value=self.candidate();edit(value);self.reject(lambda:contract.admit(canonical(value),completion=done))
 def test_unsealed_completion_is_not_readback(self):
  gate,captured,_,_=self.gate();contract=self.contract(gate,captured);self.reject(lambda:contract.admit(canonical(self.candidate()),completion={'verified':True}))
 def test_stale_capture_is_rejected(self):
  gate,captured,_,_=self.gate()
  with patch('intune_iac.worker_state_recovery.time.time',return_value=time.time()+31):self.reject(lambda:self.contract(gate,captured))
 def test_malformed_prior_returns_domain_error(self):
  gate,captured,_,_=self.gate();self.plan['prior_state']=None;self.reject(lambda:self.contract(gate,captured))
 def test_contract_tamper_is_rejected(self):
  gate,captured,_,_=self.gate();contract=self.contract(gate,captured);contract._binding['baseline_sha256']='0'*64;self.reject(contract.binding)
if __name__=='__main__':unittest.main()
