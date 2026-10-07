"""Fresh-process recovery content proof through real reader/capture interfaces."""
import copy,hashlib,os,pickle,unittest
from pathlib import Path
from unittest.mock import patch
from intune_iac import worker_adoption_projection as projection,observation_reader as rd,identity_binding as ib
from intune_iac.io import canonical,digest,AppError
try:from plugin_tests import test_worker_adoption_state_r4 as fixture
except ImportError:import test_worker_adoption_state_r4 as fixture
NATIVE,GRAPH,TENANT,CLIENT,PRINCIPAL,OID,Transport=(fixture.NATIVE,fixture.GRAPH,fixture.TENANT,fixture.CLIENT,fixture.PRINCIPAL,fixture.OID,fixture.Transport)

class RecoveryProjectionTests(unittest.TestCase):
 setUp=fixture.AdoptionContracts.setUp
 contract=fixture.AdoptionContracts.contract
 code=fixture.AdoptionContracts.code
 def observer(self,*,binding_edit=None,baseline_edit=None):
  contract,oldtransport,kwargs=self.contract();binding=contract.binding();baseline=kwargs['baseline_raw']
  if binding_edit:binding_edit(binding)
  if baseline_edit:baseline=baseline_edit(baseline)
  # Deliberately discard old process-held reader, never mint authority from it.
  kwargs['reader'].close()
  transport=Transport(GRAPH);secret=ib.ClientSecretHandle('SYNTHETIC-FRESH-RECOVERY-READER');self.addCleanup(secret.close)
  reader=rd.bind_laboratory_reader(rd.ReaderSpec(TENANT,CLIENT,PRINCIPAL,(OID,)),credential=secret,transport=transport);self.addCleanup(reader.close)
  observer=projection.AdoptionRecoveryProjection(contract=binding,baseline_raw=baseline,original_capture_root=self.root/str(self.sequence)/'preimage',reader=reader)
  return observer,transport,baseline,binding
 def test_fresh_reader_accepts_original_capture_only_as_historical_content(self):
  observer,transport,_,binding=self.observer();facts,capture=observer.observe(NATIVE,self.root/'fresh',state_write_attempts=1)
  self.assertEqual(facts['classification'],'approved_adoption_successor');self.assertTrue(facts['graph_unchanged']);self.assertEqual(facts['original_preimage_capture_sha256'],binding['preimage_capture_sha256'])
  self.assertNotEqual(facts['fresh_capture_sha256'],binding['preimage_capture_sha256'])
  for key in ('historical_capture_authenticated','backend_state_authenticated','execution_authorized'):self.assertFalse(facts[key])
 def test_baseline_and_unexpected_state_classified_without_authorizing_release(self):
  observer,_,baseline,_=self.observer();facts,_=observer.observe(baseline,self.root/'baseline',state_write_attempts=0);self.assertEqual(facts['classification'],'original_baseline')
  changed=__import__('json').loads(NATIVE);changed['serial']=14
  facts,_=observer.observe(canonical(changed),self.root/'unexpected',state_write_attempts=1);self.assertEqual(facts['classification'],'unexpected_state')
 def test_successor_requires_original_state_write_and_no_multiple_attempts(self):
  observer,_,_,_=self.observer();facts,_=observer.observe(NATIVE,self.root/'no-attempt',state_write_attempts=0);self.assertEqual(facts['classification'],'unexpected_state')
  for count in (True,-1,2):self.code('adoption_recovery_state_write_ambiguous',lambda:observer.observe(NATIVE,self.root/'bad',state_write_attempts=count))
 def test_exact_historical_hashes_and_schema(self):
  for key in ('baseline_sha256','preimage_capture_sha256','preimage_raw_sha256','expected_semantic_sha256','reader_identity_sha256'):
   with self.subTest(key=key),self.assertRaises(AppError):self.observer(binding_edit=lambda b:b.update({key:'f'*64}))
  for edit in (lambda b:b.update(extra=True),lambda b:b.update(schema_version='unknown'),lambda b:b.update(execution_authorized=True)):
   self.code('adoption_recovery_original_contract_unsupported',lambda:self.observer(binding_edit=edit))
 def test_old_baseline_bytes_not_replaced_with_equivalent_serialized_content(self):
  self.code('adoption_recovery_baseline_substitution',lambda:self.observer(baseline_edit=lambda b:b+b' '))
 def test_projection_private_or_unknown_values_are_not_learned_from_candidate(self):
  for key,value in [('private','unknown'),('identity_schema_version',False)]:
   observer,_,_,_=self.observer();candidate=__import__('json').loads(NATIVE);candidate['resources'][0]['instances'][0][key]=value
   facts,_=observer.observe(canonical(candidate),self.root/('bad-'+key),state_write_attempts=1);self.assertEqual(facts['classification'],'unexpected_state')
 def test_fresh_graph_change_retained_but_not_equal(self):
  observer,transport,_,_=self.observer();transport.graph['assignments'][0]['target']['groupId']='66666666-6666-4666-8666-666666666666'
  facts,_=observer.observe(NATIVE,self.root/'changed',state_write_attempts=1);self.assertFalse(facts['graph_unchanged']);self.assertEqual(facts['classification'],'approved_adoption_successor')
 def test_denied_fresh_capture_and_capability_substitution_fail(self):
  observer,transport,_,_=self.observer();transport.deny=True
  self.code('precondition_coverage_incomplete',lambda:observer.observe(NATIVE,self.root/'denied',state_write_attempts=1))
  other,_,_,_=self.observer();observer.reader=other.reader;self.code('adoption_recovery_projection_changed',observer.check)
 def test_fork_and_serialization_do_not_rehydrate_reader(self):
  observer,_,_,_=self.observer()
  with patch.object(projection.os,'getpid',return_value=-1):self.code('adoption_recovery_projection_changed',observer.check)
  with self.assertRaises(TypeError):pickle.dumps(observer)

if __name__=='__main__':unittest.main()
