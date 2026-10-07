"""Same resolver on held recorded Win32 boundaries; never native qualification."""
import copy
import hashlib
import json
from pathlib import Path,PureWindowsPath
import sys
import tempfile
import unittest
from unittest.mock import patch
from intune_iac import windows_repository as subject,windows_storage as ws,repository,windows_workbench,workbench_views,workbench
from intune_iac.io import AppError,digest
from plugin_tests.test_windows_workbench_r4 import FilesystemAPI,TENANT
from plugin_tests.test_windows_storage_r4 import ROOT,CANONICAL

OID='22222222-2222-4222-8222-222222222222'
NS='#microsoft.graph.deviceManagementConfiguration'
POLICY={'name':'Exact policy','description':None,'platforms':'windows10','technologies':['mdm'],'role_scope_tag_ids':['0'],
    'assignments':[],'settings':{'settings':[{'id':'7','settingInstance':{'@odata.type':NS+'SimpleSettingCollectionInstance',
    'settingDefinitionId':'literal_definition','simpleSettingCollectionValue':[{'@odata.type':NS+'StringSettingValue','value':'first'},
    {'@odata.type':NS+'StringSettingValue','value':'second'}]}}]}}

class RepositoryAPI(FilesystemAPI):
    def open_directory(self,path):
        if self.real(path).is_file():self._sync(path);return self._open(path,'file')
        return super().open_directory(path)
    def repository_entry_type(self,handle,sid):
        kind,path=self.handles[handle]
        return (kind,self.file_metadata(handle,sid) if kind=='file' else self.metadata(handle,private=True))

class NativeRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.api=RepositoryAPI(Path(self.temp.name)/'files');self.root=ROOT+'\\Repository 雪 - x';ws._create_directory(ROOT,'Repository 雪 - x',self.api)
        self.real=self.api.real(CANONICAL+'\\Repository 雪 - x')
        self.put('atmos.yaml',b'stacks: {base_path: stacks, included_paths: ["deploy/**/*"]}\r\ncomponents: {terraform: {base_path: components/terraform, command: tofu}}\r\n')
        self.put('stacks/defaults.yaml',json.dumps({'vars':{'policy':POLICY,'shared_flag':False,'secret':'never-output'}}).encode())
        self.put('stacks/deploy/pilot.yaml',b'import: [defaults]\ncomponents: {terraform: {intune: {}}}\n')
        self.put('stacks/deploy/other.yaml',b'import: [defaults]\ncomponents: {terraform: {intune: {}}}\n')
        self.put('components/terraform/intune/main.tf',b'# literal source\r\n')
        self.put('components/terraform/intune/.terraform.lock.hcl',b'# exact lock\r\n')
    def put(self,name,data):
        path=PureWindowsPath(self.root);parts=name.split('/')
        for part in parts[:-1]:
            next_path=path/part
            if not self.api.real(CANONICAL+'\\Repository 雪 - x\\'+'\\'.join(next_path.relative_to(PureWindowsPath(self.root)).parts)).exists():ws._create_directory(str(path),part,self.api)
            path=next_path
        real=self.real.joinpath(*parts)
        if real.exists():real.write_bytes(data)
        else:ws._create_file(str(path),parts[-1],data,self.api)
    def resolve(self):return subject._resolve(self.root,'deploy/pilot','intune',self.api)
    def record(self):
        report=self.resolve();self.assertEqual(report['status'],'resolved',report)
        return {'schema_version':'workbench-repository-intent/1','tenant_id':TENANT,'target_object_id':OID,
            'scope':{'repository':self.root,'stack':'deploy/pilot','component':'intune','backend':'declared-backend'},
            'effective_pointer':'/vars/policy','source_revision':'a'*40,'revision_assurance':'caller_asserted_revision_actual_working_source_hashes',
            'resolution':repository.public_resolution(report),'desired':copy.deepcopy(POLICY),'collected_at':1,
            'evidence_class':'local_literal_repository_read','cloud_authority':False,'execution_authorized':False}
    def test_same_engine_literal_independent_types_order_crlf_and_shared_inheritance(self):
        report=self.resolve();self.assertEqual(report['effective']['vars']['policy'],POLICY)
        self.assertIs(report['effective']['vars']['shared_flag'],False)
        self.assertEqual(report['provenance']['/vars/policy/description']['winner']['path'],'stacks/defaults.yaml')
        self.assertEqual(report['effective'],repository.resolve_component(self.real,'deploy/pilot','intune')['effective'])
        sources={v['path']:v['sha256'] for v in report['sources']}
        self.assertEqual(sources['atmos.yaml'],hashlib.sha256((self.real/'atmos.yaml').read_bytes()).hexdigest())
        other=subject._resolve(self.root,'deploy/other','intune',self.api)
        self.assertEqual(other['provenance']['/vars/policy/description']['winner']['path'],'stacks/defaults.yaml')
        self.assertEqual(self.api.handles,{})
    def test_exact_readback_current_changed_and_shared_source_impacts(self):
        record=self.record();equal=subject._readback(record,self.api)
        self.assertTrue(equal['source_hashes_equal']);self.assertEqual(equal['policy_comparison']['status'],'equal')
        changed=copy.deepcopy(POLICY);changed['description']='Reviewed current edit'
        self.put('stacks/defaults.yaml',json.dumps({'vars':{'policy':changed,'shared_flag':False,'secret':'never-output'}}).encode())
        out=subject._readback(record,self.api);self.assertFalse(out['source_hashes_equal']);self.assertEqual(out['policy_comparison']['changed_fields'],['description'])
        self.assertEqual(out['source_file_changes']['changed'],['stacks/defaults.yaml']);self.assertEqual(out['current_policy'],changed)
        self.assertNotIn('never-output',json.dumps(out));self.assertFalse(out['git_revision_verified']);self.assertFalse(out['prior_native_root_identity_available'])
        self.assertGreaterEqual(out['read_completed_at'],out['read_started_at']);self.assertEqual(self.api.handles,{})
    def test_new_source_is_visible_even_when_effective_values_unchanged(self):
        record=self.record();self.put('components/terraform/intune/new.tf',b'# new\n');out=subject._readback(record,self.api)
        self.assertEqual(out['policy_comparison']['status'],'equal');self.assertFalse(out['source_hashes_equal'])
        self.assertEqual(out['source_file_changes']['added'],['components/terraform/intune/new.tf'])
    def test_recorded_manifest_and_pointer_cannot_escape_or_disclose_arbitrary_vars(self):
        record=self.record()
        for rows in ([{'path':'../outside','sha256':'b'*64}],[{'path':'stacks/a','sha256':False}],
                [{'path':'a','sha256':'b'*64},{'path':'A','sha256':'c'*64}]):
            bad=copy.deepcopy(record);bad['resolution']['sources']=rows
            with self.subTest(rows=rows),self.assertRaises(AppError):subject._readback(bad,self.api)
        record['effective_pointer']='/vars/secret'
        with self.assertRaises(AppError) as caught:subject._readback(record,self.api)
        self.assertEqual(caught.exception.code,'windows_repository_current_policy_unsupported');self.assertEqual(self.api.handles,{})
    def test_no_posix_path_open_or_revision_subprocess(self):
        record=self.record()
        with patch.object(repository.os,'open',side_effect=AssertionError('POSIX open')):
            out=subject._readback(record,self.api)
        self.assertEqual(out['current_policy']['settings']['settings'][0]['id'],'7');self.assertFalse(out['publisher_authenticated'])
    def test_unselected_dynamic_input_case_collision_and_path_escape_reject(self):
        self.put('stacks/deploy/pilot.yaml',b'import: [../../outside]\ncomponents: {terraform: {intune: {}}}\n')
        self.assertEqual(self.resolve()['status'],'blocked')
        self.put('stacks/Defaults.yaml',b'vars: {}\n')
        blocked=self.resolve();self.assertEqual(blocked['status'],'blocked');self.assertNotIn('effective',blocked)
        self.assertEqual(self.api.handles,{})
    def test_source_byte_and_namespace_changes_fail_before_return(self):
        record=self.record();original=subject._Access.revalidate
        for mutation in ('bytes','namespace'):
            def changed(access):
                path=self.real/'stacks/defaults.yaml' if mutation=='bytes' else self.real/'stacks/late.yaml'
                path.write_bytes(path.read_bytes()+b' ' if mutation=='bytes' else b'vars: {}\n')
                return original(access)
            with self.subTest(mutation=mutation),patch.object(subject._Access,'revalidate',changed),self.assertRaises(AppError):subject._readback(record,self.api)
            self.assertEqual(self.api.handles,{})
    def test_same_store_views_and_actual_terminal_keep_current_vs_recorded_separate(self):
        record=self.record();store=windows_workbench.WindowsWorkbenchStore._create(ROOT+'\\viewstore',TENANT,windows_workbench._Filesystem(self.api,self.api.connect))
        from intune_iac import capture,windows_capture_writer
        from plugin_tests.test_capture_adapter import ROOT as PROJECT
        fixture=json.loads((PROJECT/'examples/supported/input/export.json').read_text())
        responses={p['request_url']:(p['http_status'],json.dumps(p['body']).encode()) for c in fixture['collections'] for p in c['pages']}
        for url,(status,raw) in list(responses.items()):
            if url.endswith('/assignments'):
                body=json.loads(raw)
                for row in body['value']:row.update(source='direct',sourceId=None)
                responses[url]=(status,json.dumps(body).encode())
        capture._capture(TENANT,OID,ROOT+'\\observed',transport=lambda url:responses[url],source_is_synthetic=True,
            output_factory=lambda dest:windows_capture_writer._output(dest,self.api))
        store.import_capture(ROOT+'\\observed');store.record_artifact('repository_intent',None,record)
        before=self.api.real(CANONICAL+'\\viewstore\\observations.sqlite3').read_bytes();results=[]
        with patch.object(subject,'_NativeAPI',return_value=self.api):
            inputs=iter(['select '+OID,'views','quit']);out=workbench.run_terminal(str(store.root),input_fn=lambda _:next(inputs),result_fn=results.append,_store_capability=store)
        view=next(v for v in results if v.get('schema_version')=='workbench-four-views/1')
        self.assertEqual(view['repository']['current_working_source_readback']['policy_comparison']['status'],'equal')
        self.assertEqual(view['observed']['status'],'recorded');self.assertEqual(view['deployment']['status'],'unknown');self.assertEqual(out['status'],'closed')
        self.assertEqual(self.api.real(CANONICAL+'\\viewstore\\observations.sqlite3').read_bytes(),before);self.assertEqual(self.api.handles,{})
    def test_ordered_array_change_is_not_set_equal_and_wrong_type_stays_unknown(self):
        record=self.record();changed=copy.deepcopy(POLICY)
        changed['settings']['settings'][0]['settingInstance']['simpleSettingCollectionValue'].reverse()
        self.put('stacks/defaults.yaml',json.dumps({'vars':{'policy':changed}}).encode())
        out=subject._readback(record,self.api)
        self.assertEqual(out['policy_comparison']['changed_fields'],['settings'])
        self.assertEqual(out['current_policy']['settings']['settings'][0]['settingInstance']['simpleSettingCollectionValue'][0]['value'],'second')
        changed['description']=True;self.put('stacks/defaults.yaml',json.dumps({'vars':{'policy':changed}}).encode())
        with self.assertRaises(AppError) as caught:subject._readback(record,self.api)
        self.assertEqual(caught.exception.code,'windows_repository_current_policy_unsupported');self.assertEqual(self.api.handles,{})
    def test_hardlink_and_foreign_owner_sources_cannot_resolve(self):
        for invalid in ({'links':2},{'owner_sid':'S-1-5-18'}):
            self.api.bad_file=invalid
            with self.subTest(invalid=invalid):
                blocked=self.resolve();self.assertEqual(blocked['status'],'blocked');self.assertNotIn('effective',blocked)
            self.assertEqual(self.api.handles,{})
        self.api.bad_file={}
    def test_failed_final_validation_preserves_primary_across_every_close(self):
        record=self.record();primary=AppError('independent_final_guard_failure','literal')
        self.api.close_fail=True
        # Flip cleanup fault only after normal acquisition, then fail revalidation.
        self.api.close_fail=False
        def fail(access):self.api.close_fail=True;raise primary
        with patch.object(subject._Access,'revalidate',fail),self.assertRaises(AppError) as caught:subject._readback(record,self.api)
        self.assertIs(caught.exception,primary);self.assertEqual(self.api.handles,{})
    def test_wrong_scope_and_case_alias_never_silently_remap_source(self):
        record=self.record();record['scope']['repository']='/old/posix/source'
        opened=len(self.api.events)
        with self.assertRaises(AppError):subject._readback(record,self.api)
        self.assertEqual(len(self.api.events),opened)
        record=self.record();record['scope']['stack']='deploy/Pilot'
        out=subject._readback(record,self.api)
        self.assertEqual(out['status'],'unknown');self.assertNotIn('current_policy',out);self.assertEqual(self.api.handles,{})

    def test_linux_public_route_refuses_before_any_native_io(self):
        if sys.platform=='win32':self.skipTest('Linux-only unsupported-host negative control')
        with self.assertRaises(AppError) as caught:subject.resolve_windows_component(self.root,'deploy/pilot','intune')
        self.assertEqual(caught.exception.code,'windows_directory_platform_unsupported')

if __name__=='__main__':unittest.main()
