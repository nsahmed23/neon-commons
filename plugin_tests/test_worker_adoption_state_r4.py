"""Adoption content contracts; actual reader/capture interface, recorded responses.
Native expected successor was captured from unchanged pinned ToFu/provider import;
Graph fixture is a separate literal original input. Neither proves Azure service.
"""
import base64,copy,hashlib,importlib.util,json,os,pickle,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from intune_iac.io import AppError,canonical,digest
from intune_iac import observation_reader as rd,identity_binding as ib
from intune_iac.azure_backend import StateRevision
try:from intune_iac import worker_adoption_state as ad
except ImportError:
    spec=importlib.util.spec_from_file_location('intune_iac.worker_adoption_state',Path(__file__).with_name('worker_adoption_state.py'));ad=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ad;spec.loader.exec_module(ad)
NATIVE=b'{"version":4,"terraform_version":"1.13.1","serial":13,"lineage":"77777777-7777-7777-7777-777777777777","outputs":{},"resources":[{"mode":"managed","type":"microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json","name":"selected","provider":"provider[\\"registry.terraform.io/deploymenttheory/microsoft365\\"]","instances":[{"schema_version":0,"attributes":{"assignments":[{"filter_id":"00000000-0000-0000-0000-000000000000","filter_type":"none","group_id":"22222222-2222-4222-8222-222222222222","type":"exclusionGroupAssignmentTarget"},{"filter_id":"44444444-4444-4444-8444-444444444444","filter_type":"include","group_id":"11111111-1111-4111-8111-111111111111","type":"groupAssignmentTarget"}],"created_date_time":"2026-09-30T12:00:00Z","description":"Fixture only","id":"33333333-3333-4333-8333-333333333333","is_assigned":true,"last_modified_date_time":"2026-09-30T12:00:00Z","name":"Synthetic existing Intune policy","platforms":"windows10","role_scope_tag_ids":["0"],"settings":"{\\"settings\\":[{\\"@odata.type\\":\\"#microsoft.graph.deviceManagementConfigurationSetting\\",\\"id\\":\\"37\\",\\"settingInstance\\":{\\"@odata.type\\":\\"#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance\\",\\"choiceSettingValue\\":{\\"@odata.type\\":\\"#microsoft.graph.deviceManagementConfigurationChoiceSettingValue\\",\\"children\\":[],\\"settingValueTemplateReference\\":null,\\"value\\":\\"device_vendor_msft_policy_config_privacy_letappsaccesslocation_2\\"},\\"settingDefinitionId\\":\\"device_vendor_msft_policy_config_privacy_letappsaccesslocation\\",\\"settingInstanceTemplateReference\\":null}}]}","settings_catalog_template_type":"","settings_count":1,"technologies":["mdm"],"timeouts":null},"sensitive_attributes":[],"identity":{"id":"33333333-3333-4333-8333-333333333333"},"identity_schema_version":0}]}],"check_results":null}\n'
GRAPH={'policy': {'id': '33333333-3333-4333-8333-333333333333', 'name': 'Synthetic existing Intune policy', 'description': 'Fixture only', 'platforms': 'windows10', 'technologies': 'mdm', 'roleScopeTagIds': ['0'], 'settingCount': 1, 'isAssigned': True, 'createdDateTime': '2026-09-30T12:00:00Z', 'lastModifiedDateTime': '2026-09-30T12:00:00Z', '@odata.type': '#microsoft.graph.deviceManagementConfigurationPolicy'}, 'settings': [{'id': '37', '@odata.type': '#microsoft.graph.deviceManagementConfigurationSetting', 'settingInstance': {'@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance', 'settingDefinitionId': 'device_vendor_msft_policy_config_privacy_letappsaccesslocation', 'settingInstanceTemplateReference': None, 'choiceSettingValue': {'@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingValue', 'value': 'device_vendor_msft_policy_config_privacy_letappsaccesslocation_2', 'settingValueTemplateReference': None, 'children': []}}}], 'assignments': [{'id': 'assignment-a', 'target': {'@odata.type': '#microsoft.graph.groupAssignmentTarget', 'groupId': '11111111-1111-4111-8111-111111111111', 'deviceAndAppManagementAssignmentFilterId': '44444444-4444-4444-8444-444444444444', 'deviceAndAppManagementAssignmentFilterType': 'include'}, '@odata.type': '#microsoft.graph.deviceManagementConfigurationPolicyAssignment', 'source': 'direct', 'sourceId': None}, {'id': 'assignment-b', 'target': {'@odata.type': '#microsoft.graph.exclusionGroupAssignmentTarget', 'groupId': '22222222-2222-4222-8222-222222222222', 'deviceAndAppManagementAssignmentFilterId': '00000000-0000-0000-0000-000000000000', 'deviceAndAppManagementAssignmentFilterType': 'none'}, '@odata.type': '#microsoft.graph.deviceManagementConfigurationPolicyAssignment', 'source': 'direct', 'sourceId': None}]}
TENANT='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';CLIENT='88888888-8888-4888-8888-888888888888';PRINCIPAL='99999999-9999-4999-8999-999999999999';OID=GRAPH['policy']['id'];BLOB='recordedstate.blob.core.windows.net'
class Transport:
 def __init__(self,graph):self.graph=copy.deepcopy(graph);self.calls=[];self.deny=False
 def __call__(self,request,**kwargs):
  self.calls.append((request.method,request.host,request.path));status=200
  if request.method=='POST':body={'token_type':'Bearer','access_token':'SYNTHETIC-ADOPTION-READER-ONLY','expires_in':3600}
  elif request.path.startswith('/v1.0/servicePrincipals'):body={'id':PRINCIPAL,'appId':CLIENT,'accountEnabled':True}
  elif request.path.endswith('/settings'):body={'value':self.graph['settings']}
  elif request.path.endswith('/assignments'):
   if self.deny:status=403;body={'error':{'code':'Denied'}}
   else:body={'value':self.graph['assignments']}
  else:body={'value':[self.graph['policy']]}
  return ib.ServiceResponse(status,(('content-type','application/json'),),canonical(body))
class AdoptionContracts(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.sequence=0
 def contract(self,*,mutate_graph=None,mutate_baseline=None,change_kwargs=None):
  self.sequence+=1;root=self.root/str(self.sequence);root.mkdir();g=copy.deepcopy(GRAPH)
  if mutate_graph:mutate_graph(g)
  transport=Transport(g);secret=ib.ClientSecretHandle('SYNTHETIC-READER-ONLY');self.addCleanup(secret.close)
  reader=rd.bind_laboratory_reader(rd.ReaderSpec(TENANT,CLIENT,PRINCIPAL,(OID,)),credential=secret,transport=transport);self.addCleanup(reader.close);preimage=reader.capture(OID,root/'preimage')
  before={'version':4,'terraform_version':'1.13.1','lineage':'77777777-7777-7777-7777-777777777777','serial':12,'outputs':{},'resources':[]}
  if mutate_baseline:mutate_baseline(before)
  raw=canonical(before);revision=StateRevision.observe(raw,etag='"fixture-1"');backend=ib.BackendSpec('11111111-1111-4111-8111-111111111111','/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/fixture/providers/Microsoft.Storage/storageAccounts/recordedstate','https://'+BLOB,'tfstate','intune.tfstate','default',revision.lineage,revision.serial,revision.sha256)
  kwargs=dict(baseline_raw=raw,baseline_revision=revision,backend=backend,reader=reader,preimage=preimage,execution_binding_sha256='a'*64,source_sha256='b'*64,effective_inputs_sha256='c'*64,locks_sha256='d'*64,evidence_root=root/'admission')
  if change_kwargs:change_kwargs(kwargs)
  return ad.NativeAdoptionStateContract(**kwargs),transport,kwargs
 def code(self,name,fn):
  with self.assertRaises(AppError) as got:fn()
  self.assertEqual(got.exception.code,name)
 def test_retained_native_import_matches_independent_graph_projection(self):
  contract,transport,_=self.contract();self.assertEqual(hashlib.sha256(NATIVE).hexdigest(),'64589b745c85615f67d689cc918765f7aca6254dd7965c5067bb824824304aa8');result=contract.admit(NATIVE)
  self.assertEqual(result['body_sha256'],hashlib.sha256(NATIVE).hexdigest());self.assertEqual((self.root/'1/admission/candidate-state.json').read_bytes(),NATIVE);self.assertFalse(result['backend_state_authenticated']);self.assertFalse(result['execution_authorized']);self.assertEqual(len(transport.calls),8)
  self.assertEqual(contract.binding()['management_mapping_status'],'unsupported');self.assertTrue(contract.binding()['management_mapping_blockers'])
 def test_admission_consumed_after_success_and_after_rejected_body(self):
  contract,_,_=self.contract();contract.admit(NATIVE);self.code('adoption_admission_spent',lambda:contract.admit(NATIVE))
  contract,_,_=self.contract();changed=json.loads(NATIVE);changed['serial']=14;self.code('adoption_state_mismatch',lambda:contract.admit(canonical(changed)));self.code('adoption_admission_spent',lambda:contract.admit(NATIVE))
 def test_extra_resource_private_sensitive_outputs_lineage_serial_and_bool_rejected(self):
  edits=[lambda s:s['resources'].append(copy.deepcopy(s['resources'][0])),lambda s:s['resources'][0]['instances'][0].update(private='secret'),lambda s:s.update(outputs={'token':'secret'}),lambda s:s.update(lineage='88888888-8888-4888-8888-888888888888'),lambda s:s.update(serial=12),lambda s:s.update(version=True),lambda s:s['resources'][0]['instances'][0].update(schema_version=False),lambda s:s['resources'][0]['instances'][0].update(sensitive_attributes=['secret']),lambda s:s['resources'][0]['instances'][0]['attributes'].update(settings_count=True)]
  for edit in edits:
   contract,_,_=self.contract();changed=json.loads(NATIVE);edit(changed);self.code('adoption_state_mismatch',lambda:contract.admit(canonical(changed)))
 def test_settings_identity_order_filter_and_null_are_not_normalized_away(self):
  edits=[lambda a:a.update(id='44444444-4444-4444-8444-444444444444'),lambda a:a.update(settings=a['settings'].replace('"37"','"0"')),lambda a:a['assignments'].reverse(),lambda a:a['assignments'][0].update(filter_id=None),lambda a:a.update(description=None),lambda a:a.update(role_scope_tag_ids=[])]
  for edit in edits:
   contract,_,_=self.contract();changed=json.loads(NATIVE);edit(changed['resources'][0]['instances'][0]['attributes']);self.code('adoption_state_mismatch',lambda:contract.admit(canonical(changed)))
 def test_baseline_existing_resource_extra_fields_or_outputs_reject(self):
  for edit in [lambda s:s.update(resources=json.loads(NATIVE)['resources']),lambda s:s.update(outputs={'x':{}}),lambda s:s.update(unknown=True),lambda s:s.update(check_results=[]),lambda s:s.update(terraform_version='1.10.0')]:
   self.code('adoption_baseline_not_empty',lambda:self.contract(mutate_baseline=edit))
 def test_baseline_revision_or_backend_substitution_rejects(self):
  self.code('adoption_baseline_mismatch',lambda:self.contract(change_kwargs=lambda k:k.update(baseline_revision=StateRevision.observe(k['baseline_raw']+b' ',etag='"fixture-1"'))))
  self.code('adoption_backend_binding',lambda:self.contract(change_kwargs=lambda k:k.update(backend=ib.BackendSpec(**{**k['backend'].__dict__,'state_serial':13}))))
 def test_unknown_settings_secret_and_assignment_metadata_remain_unsupported(self):
  for edit,code in [(lambda g:g['settings'][0].update(extra='unmapped'),'adoption_settings_unsupported'),(lambda g:g['settings'][0]['settingInstance'].update(**{'@odata.type':'#microsoft.graph.deviceManagementConfigurationSecretSettingInstance'}),'adoption_settings_unsupported'),(lambda g:g['assignments'][0].update(extra='unmapped'),'adoption_assignments_unsupported')]:
   self.code(code,lambda:self.contract(mutate_graph=edit))
 def test_fresh_portal_change_blocks_state_without_graph_write(self):
  contract,transport,_=self.contract();transport.graph['policy']['description']='changed';self.code('adoption_graph_changed',lambda:contract.admit(NATIVE));self.assertTrue(all(method=='GET' for method,_,_ in transport.calls[1:]));self.code('adoption_admission_spent',lambda:contract.admit(NATIVE))
 def test_denied_fresh_assignments_do_not_authorize_state(self):
  contract,transport,_=self.contract();transport.deny=True;self.code('precondition_coverage_incomplete',lambda:contract.admit(NATIVE));self.assertTrue(list(self.root.glob('*/admission/observation-*/raw')))
 def test_json_reader_wrong_identity_and_fork_do_not_mint_authority(self):
  self.code('adoption_contract_invalid',lambda:self.contract(change_kwargs=lambda k:k.update(reader={'authenticated':True})))
  contract,_,_=self.contract()
  with patch.object(ad.os,'getpid',return_value=-1):self.code('adoption_contract_changed',contract.binding)
  with self.assertRaises(TypeError):pickle.dumps(contract)
 def test_other_legitimate_reader_cannot_replace_original_process_capability(self):
  contract,_,_=self.contract();other,_,kwargs=self.contract();contract._reader=kwargs['reader']
  self.code('adoption_reader_or_preimage_changed',lambda:contract.admit(NATIVE))
 def test_other_legitimate_capture_cannot_replace_original_capture_hash(self):
  contract,_,_=self.contract();other,_,kwargs=self.contract();contract._preimage=kwargs['preimage']
  self.code('adoption_reader_or_preimage_changed',lambda:contract.admit(NATIVE))
 def test_readonly_successor_is_not_backend_reconciliation_or_release_authority(self):
  contract,_,_=self.contract();proof=contract.observe_successor(NATIVE,revision=StateRevision.observe(NATIVE,etag='"current"'));facts=proof.verified()
  self.assertIs(type(proof),ad.AdoptionStateObservation);self.assertEqual(facts['state_raw'],NATIVE)
  for key in ('backend_state_authenticated','execution_authorized','reconciliation_authorized','lease_release_authorized'):self.assertFalse(facts[key])
  with self.assertRaises(TypeError):pickle.dumps(proof)
if __name__=='__main__':unittest.main()
