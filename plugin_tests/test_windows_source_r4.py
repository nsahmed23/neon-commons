"""Native local source commands with real resolver/files/SQLite, recorded Win32."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import unittest
from unittest.mock import patch
import yaml
from intune_iac import windows_source as subject,windows_repository,windows_workbench,workbench_views,workbench,capture,windows_capture_writer
from intune_iac.io import AppError,canonical,digest
from plugin_tests import test_windows_repository_r4 as repository_fixture
from plugin_tests.test_windows_storage_r4 import ROOT,CANONICAL
from plugin_tests.test_windows_workbench_r4 import TENANT
from plugin_tests.test_capture_adapter import ROOT as PROJECT
OID=repository_fixture.OID

class NativeSourceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=repository_fixture.NativeRepositoryTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.api=self.fixture.api;self.root=self.fixture.root;self.real=self.fixture.real
        self.store=windows_workbench.WindowsWorkbenchStore._create(ROOT+'\\store',TENANT,windows_workbench._Filesystem(self.api,self.api.connect))
        fixture=json.loads((PROJECT/'examples/supported/input/export.json').read_text())
        responses={p['request_url']:(p['http_status'],json.dumps(p['body']).encode()) for c in fixture['collections'] for p in c['pages']}
        for url,(status,raw) in list(responses.items()):
            if url.endswith('/assignments'):
                body=json.loads(raw)
                for row in body['value']:row.update(source='direct',sourceId=None)
                responses[url]=(status,json.dumps(body).encode())
        capture._capture(TENANT,OID,ROOT+'\\capture',transport=lambda url:responses[url],source_is_synthetic=True,
            output_factory=lambda output:windows_capture_writer._output(output,self.api))
        self.store.import_capture(ROOT+'\\capture');self.output=ROOT+'\\proposal';self.database=self.api.real(CANONICAL+'\\store\\observations.sqlite3')
    def arguments(self):return [self.root,'deploy/pilot','intune',OID,'/vars/policy','a'*40,'declared-backend','policy.one']
    def imp(self):
        with patch.object(windows_repository,'_NativeAPI',return_value=self.api):return workbench_views.import_repository(self.store,*self.arguments())
    def propose(self,field='/description'):
        with patch.object(windows_repository,'_NativeAPI',return_value=self.api):return workbench_views.propose_source_acceptance(self.store,OID,field,self.output)
    def test_real_application_import_binds_current_snapshot_without_git_claim(self):
        out=self.imp();record=self.store.artifacts(kind='repository_intent')[0]['data']
        self.assertEqual(record['desired'],repository_fixture.POLICY);self.assertFalse(record['revision_content_verified']);self.assertFalse(record['revision_authenticated'])
        self.assertTrue(record['native_source_snapshot']['source_bytes_verified_at_read']);self.assertEqual(self.api.handles,{})
        with patch.object(windows_repository,'_NativeAPI',return_value=self.api):view=workbench_views.views(self.store,OID)
        current=view['repository']['current_working_source_readback'];self.assertTrue(current['prior_native_root_identity_available']);self.assertFalse(current['historical_root_binding_authenticated'])
        self.assertEqual(current['policy_comparison']['status'],'equal');self.assertEqual(view['deployment']['status'],'unknown')
    def test_late_source_validation_failure_creates_no_intent(self):
        primary=AppError('injected_final_source_failure','literal')
        with patch.object(windows_repository._Access,'revalidate',side_effect=primary),self.assertRaises(AppError):self.imp()
        self.assertEqual(self.store.artifacts(kind='repository_intent'),[]);self.assertEqual(self.api.handles,{})
    def test_unsupported_pointer_git_route_and_foreign_store_reject(self):
        args=self.arguments();args[4]='/vars/secret'
        with patch.object(windows_repository,'_NativeAPI',return_value=self.api),self.assertRaises(AppError):workbench_views.import_repository(self.store,*args)
        with self.assertRaises(AppError) as caught:subject.import_repository(self.store,*self.arguments(),git_executable='unknown',git_sha256='0'*64)
        self.assertEqual(caught.exception.code,'windows_source_git_verification_unsupported')
        with self.assertRaises(AppError):subject._import(object(),*self.arguments(),self.api)
        self.assertEqual(self.store.artifacts(kind='repository_intent'),[])
    def test_immutable_proposal_preserves_source_and_exact_shared_inheritance(self):
        self.imp();before=(self.real/'stacks/defaults.yaml').read_bytes();db_before=self.database.read_bytes();result=self.propose()
        self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),before);self.assertEqual(self.database.read_bytes(),db_before)
        out=self.api.real(CANONICAL+'\\proposal');self.assertEqual((out/'source.before.yaml').read_bytes(),before)
        changed=yaml.safe_load((out/'source.after.yaml').read_bytes());self.assertEqual(changed['vars']['policy']['description'],self.store.inspect(OID)['body']['description'])
        self.assertEqual(changed['vars']['policy']['settings'],repository_fixture.POLICY['settings'])
        self.assertEqual([item['stack'] for item in result['shared_inheritance_impact']],['deploy/other','deploy/pilot'])
        self.assertFalse(result['source_modified']);self.assertFalse(result['no_resource_changes_established']);self.assertTrue(result['fresh_plan_required'])
        self.assertEqual(digest({key:value for key,value in result.items() if key!='proposal_sha256'}),result['proposal_sha256'])
        self.assertEqual(set(p.name for p in out.iterdir()),{'proposal.json','source.before.yaml','source.after.yaml','change.patch'});self.assertEqual(self.api.handles,{})
    def test_stale_source_wrong_root_binding_and_output_inside_repo_fail_before_output(self):
        self.imp();original=(self.real/'stacks/defaults.yaml').read_bytes();(self.real/'stacks/defaults.yaml').write_bytes(original+b' ')
        with self.assertRaises(AppError) as caught:self.propose()
        self.assertEqual(caught.exception.code,'workbench_source_acceptance_stale');self.assertFalse(self.api.real(CANONICAL+'\\proposal').exists())
        (self.real/'stacks/defaults.yaml').write_bytes(original);self.output=self.root+'\\forbidden'
        with self.assertRaises(AppError):self.propose()
        self.assertFalse((self.real/'forbidden').exists())
    def test_denied_or_partial_observation_does_not_make_proposal(self):
        self.imp()
        with patch.object(self.store,'inspect',side_effect=AppError('workbench_object_missing','literal')),self.assertRaises(AppError):self.propose()
        self.assertFalse(self.api.real(CANONICAL+'\\proposal').exists())
    def test_partial_output_is_retained_and_primary_storage_uncertainty_is_exposed(self):
        self.imp();before=(self.real/'stacks/defaults.yaml').read_bytes();self.api.fail_creation='source.after.yaml'
        with self.assertRaises(AppError) as caught:self.propose()
        self.assertEqual(caught.exception.code,'fixture_disk_full');self.assertEqual(caught.exception.source_proposal_outcome['source_modified'],False)
        self.assertTrue(self.api.real(CANONICAL+'\\proposal\\source.before.yaml').exists());self.assertFalse(self.api.real(CANONICAL+'\\proposal\\proposal.json').exists())
        self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),before);self.assertEqual(self.api.handles,{})
    def test_shared_terminal_import_proposal_views_and_no_execution_route(self):
        args=' '.join(shlex.quote(arg) for arg in self.arguments());lines=iter(['select '+OID,'repository-import '+args,'views','source-acceptance-propose /description '+shlex.quote(self.output),'quit']);results=[]
        with patch.object(windows_repository,'_NativeAPI',return_value=self.api):
            value=workbench.run_terminal(str(self.store.root),input_fn=lambda _:next(lines),result_fn=results.append,_store_capability=self.store)
        self.assertEqual(value['status'],'closed');self.assertEqual(len(self.store.artifacts(kind='repository_intent')),1)
        proposals=[row for row in results if row.get('schema_version')=='workbench-source-acceptance-proposal/1'];self.assertEqual(len(proposals),1)
        self.assertFalse(proposals[0]['source_modified']);self.assertEqual(self.api.handles,{})
    def test_actual_source_cli_uses_same_engine_and_explicit_local_only_labels(self):
        script=Path(subject.__file__).parents[1]/'scripts/intune-windows-source.py';spec=importlib.util.spec_from_file_location('native_source_cli',script);app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
        argv=['--qualification-only','--store',str(self.store.root),'--tenant',TENANT,'repository-import']
        for name,value in zip(('repo','stack','component','object','pointer','revision','backend','resource-address'),self.arguments()):argv+=['--'+name,value]
        stdout=io.StringIO()
        with patch.object(app,'WindowsWorkbenchStore',return_value=self.store),patch.object(windows_repository,'_NativeAPI',return_value=self.api),patch('sys.stdout',stdout):code=app.main(argv)
        out=json.loads(stdout.getvalue());self.assertEqual(code,0);self.assertFalse(out['source_modified']);self.assertFalse(out['tenant_mutation']);self.assertFalse(out['platform_qualified'])

if __name__=='__main__':unittest.main()
