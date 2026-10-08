"""Common domains over recorded Win32 persistence with real SQLite/signatures."""
import importlib.util,unittest
from pathlib import Path
from intune_iac import worker_evidence as c,workbench_evidence_views as views
from intune_iac.io import digest
STAGE=Path(c.__file__).parents[1]
def loaded(name,filename):
 spec=importlib.util.spec_from_file_location(name,STAGE/'plugin_tests'/filename);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
domain=loaded('native_domain_fixture','test_worker_evidence_domains_r4.py');received=loaded('native_domain_received','test_windows_worker_evidence_store_r4.py')
class NativeDomainTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):domain.DomainEvidenceTests.setUpClass();received.NativeReceivedEvidenceTests.f=domain.DomainEvidenceTests.f
 @classmethod
 def tearDownClass(cls):domain.DomainEvidenceTests.tearDownClass()
 def setUp(self):
  self.d=domain.DomainEvidenceTests();self.d.setUp();self.n=received.NativeReceivedEvidenceTests();self.n.setUp();self.addCleanup(self.n.doCleanups)
 def exercise(self,recovery):
  envelope,req=self.d.bundle(recovery);n=self.n;n.replace('envelope.json',envelope);n.replace('request.json',req);n.replace('trust.json',self.d.policy)
  first=n.ingest();opened=n.reopen(req);self.assertFalse(opened['baseline_admissible']);self.assertFalse(opened['graph_deployment']);self.assertEqual(opened['operation_kind'],'adoption_recovery_plan' if recovery else 'state_adoption')
  from unittest.mock import patch
  receiver=received.receiver
  def reopen(root,request,trust,pin,scratch,historical=False):return receiver._reopen(n.store,request,trust,pin,scratch,n.api,historical=historical)
  with patch.object(receiver,'reopen_windows_evidence',side_effect=reopen):
   linked=views.link(n.store,req['object_id'],n.root,digest(req),n.input+'\\trust.json',n.input+'\\pin.json',n.scratch);history=views.history(n.store,req['object_id'])
  self.assertFalse(linked['data']['execution_authorized']);self.assertEqual(history['entries'][0]['evidence']['bundle_sha256'],first['bundle_sha256']);self.assertEqual(history['entries'][0]['review']['manifest']['schema_version'],domains_version(recovery));self.assertFalse(history['entries'][0]['evidence']['baseline_admissible'])
 def test_adoption_native_received_shared_history(self):self.exercise(False)
 def test_recovery_plan_native_received_shared_history(self):self.exercise(True)
def domains_version(recovery):return 'native-adoption-recovery-plan/1' if recovery else 'native-state-adoption/1'
