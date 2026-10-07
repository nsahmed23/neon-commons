"""Original native description contract linkage; no recovery authority or network."""
import copy
import hashlib
import unittest
from intune_iac import worker_committed_description as proof
from intune_iac.io import AppError,canonical,digest
from plugin_tests import test_worker_state_recovery_r4 as description_fixture

class CommittedDescriptionLinkageTests(unittest.TestCase):
 def setUp(self):
  self.fixture=description_fixture.DescriptionRecoveryTests('test_exact_native_plan_and_independent_capture_admit_restoration')
  self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  gate,captured,_,_=self.fixture.gate();self.gate=gate.binding()
  self.binding=self.fixture.contract(gate,captured).binding()
  self.before=canonical(self.fixture.before);self.plan=canonical(self.fixture.plan)
  self.preimage=canonical(captured.verified()[0]['source']['raw_observed'])
 def run_proof(self,**changes):
  values={'contract':self.binding,'baseline_raw':self.before,'plan_json_raw':self.plan,'preimage_raw':self.preimage,'gate':self.gate};values.update(changes)
  return proof.validate_description_linkage(**values)
 def deny(self,**changes):
  with self.assertRaises(AppError):self.run_proof(**changes)
 def test_retained_native_three_baselines_have_exact_closed_linkage(self):
  value=self.run_proof()
  self.assertEqual(value['inner_contract_sha256'],self.binding['inner_contract_sha256'])
  self.assertEqual(self.binding['admitted_drift_attributes'],['description','last_modified_date_time'])
  self.assertNotEqual(self.binding['persisted_attributes_sha256'],self.binding['provider_refreshed_attributes_sha256'])
  self.assertFalse(value['execution_authorized'])
 def test_each_of_ten_original_linkage_fields_is_required(self):
  self.assertEqual(len(proof.EXTENSION_FIELDS),10)
  for field in sorted(proof.EXTENSION_FIELDS):
   with self.subTest(field=field):
    value=copy.deepcopy(self.binding);value[field]=['different'] if isinstance(value[field],list) else '0'*64;self.deny(contract=value)
 def test_unknown_schema_or_field_cannot_select_generic_fallback(self):
  for field,value in [('schema_version','arbitrary-recovery/1'),('profile','computed-native-state-write-contract/1.0'),('extra',True)]:
   with self.subTest(field=field):changed=copy.deepcopy(self.binding);changed[field]=value;self.deny(contract=changed)
 def test_original_raw_baseline_plan_and_preimage_must_be_exact(self):
  for field in ('baseline_raw','plan_json_raw','preimage_raw'):
   with self.subTest(field=field):self.deny(**{field:b'{}'})
 def mutate_plan(self,mutate):
  value=copy.deepcopy(self.fixture.plan);mutate(value);raw=canonical(value);contract=copy.deepcopy(self.binding);contract['plan_json_sha256']=hashlib.sha256(raw).hexdigest();self.deny(contract=contract,plan_json_raw=raw)
 def test_new_identity_or_additional_resource_drift_remains_denied(self):
  self.mutate_plan(lambda v:v['resource_drift'].append(copy.deepcopy(v['resource_drift'][0])))
  self.mutate_plan(lambda v:v['resource_drift'][0]['change']['after_identity'].update(id='foreign'))
 def test_unknown_drift_and_non_description_change_remain_denied(self):
  self.mutate_plan(lambda v:v['resource_drift'][0]['change'].update(after_unknown={'description':True}))
  self.mutate_plan(lambda v:v['resource_changes'][0]['change']['after'].update(name='Unapproved'))
 def test_prior_state_cannot_substitute_another_native_engine(self):
  self.mutate_plan(lambda v:v['prior_state'].update(terraform_version='0.0.0'))
 def test_current_reader_preimage_cannot_replace_the_original(self):
  changed=copy.deepcopy(self.fixture.graph);changed['policy']['description']='Unapproved portal edit'
  self.deny(preimage_raw=canonical(changed))
 def test_signed_original_template_remains_an_exact_inner_link(self):
  value=copy.deepcopy(self.binding);value['admission_template_sha256']='0'*64;self.deny(contract=value)

if __name__=='__main__':unittest.main()
