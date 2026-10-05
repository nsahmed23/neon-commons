"""Completion candidate staging and evidence cannot promote a provider gate."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import copy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('provider_completion_runner', ROOT/'scripts/qualify-provider-contract.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ProviderCompletionTests(unittest.TestCase):
    def test_native_fixture_oracle_rejects_semantic_losses(self):
        fixture_dir=ROOT/'labs/provider-contract/synthetic-rpc'
        spec=importlib.util.spec_from_file_location('native_fixture_oracle',fixture_dir/'run.py')
        oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
        fixture=json.loads((fixture_dir/'fixture.json').read_text())
        evidence=ROOT/'research/provider-qualification/completion-20261002/evidence/synthetic-rpc-omitted-filter-green'
        values=oracle.resource_values(json.loads((evidence/'state.stdout').read_text()))
        oracle.oracle(values,fixture)
        oracle.oracle(oracle.saved_snapshot(evidence/'refresh.plan'),fixture)
        for loss in ('renumber','null','empty','drop_assignment','erase_filter','change_target'):
            damaged=copy.deepcopy(values)
            settings=json.loads(damaged['settings'])
            if loss=='renumber':settings['settings'][0]['id']='0'
            if loss=='null':settings['settings'][0]['settingInstance']['settingInstanceTemplateReference']={}
            if loss=='empty':settings['settings'][0]['settingInstance']['choiceSettingValue']['children']=None
            if loss=='drop_assignment':damaged['assignments'].pop()
            if loss=='erase_filter':damaged['assignments'][0]['filter_id']=None
            if loss=='change_target':damaged['assignments'][0]['type']='groupAssignmentTarget'
            damaged['settings']=json.dumps(settings)
            with self.subTest(loss=loss),self.assertRaises(ValueError):oracle.oracle(damaged,fixture)

    def test_completion_staging_is_atomic_on_bad_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)/'work';work.mkdir()
            candidate=Path(directory)/'candidate';candidate.mkdir()
            (work/'a.go').write_bytes(b'original-a')
            (work/'b.go').write_bytes(b'original-b')
            (candidate/'a.go').write_bytes(b'candidate-a')
            (candidate/'b.go').write_bytes(b'tampered-b')
            digest=lambda b:hashlib.sha256(b).hexdigest()
            rows=[{'path':name+'.go','original_sha256':digest(('original-'+name).encode()),'candidate_sha256':digest(('candidate-'+name).encode())} for name in ('a','b')]
            with self.assertRaisesRegex(ValueError,'candidate'):
                runner.apply_completion_candidate(work,candidate,rows)
            self.assertEqual((work/'a.go').read_bytes(),b'original-a')

    def test_completion_staging_rejects_escape_and_existing_addition(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)/'work';work.mkdir();candidate=Path(directory)/'candidate';candidate.mkdir()
            for name in ('../escape','/absolute','a/../b'):
                with self.assertRaises(ValueError):runner.apply_completion_candidate(work,candidate,[{'path':name}])
            (work/'new.go').write_bytes(b'unexpected');(candidate/'new.go').write_bytes(b'candidate')
            row={'path':'new.go','original_sha256':None,'candidate_sha256':hashlib.sha256(b'candidate').hexdigest()}
            with self.assertRaisesRegex(ValueError,'already exists'):runner.apply_completion_candidate(work,candidate,[row])

    def test_completion_staging_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);work=root/'work';work.mkdir();candidate=root/'candidate';candidate.mkdir();(work/'nested').symlink_to(root,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'symlink'):runner.apply_completion_candidate(work,candidate,[{'path':'nested/file.go'}])

    def test_completion_stages_exact_bytes_and_addition(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)/'work';work.mkdir();candidate=Path(directory)/'candidate';candidate.mkdir()
            (work/'a.go').write_bytes(b'a');(candidate/'a.go').write_bytes(b'b');(candidate/'new.go').write_bytes(b'c')
            sha=lambda b:hashlib.sha256(b).hexdigest()
            rows=[{'path':'a.go','original_sha256':sha(b'a'),'candidate_sha256':sha(b'b')},{'path':'new.go','original_sha256':None,'candidate_sha256':sha(b'c')}]
            runner.apply_completion_candidate(work,candidate,rows)
            self.assertEqual((work/'a.go').read_bytes(),b'b');self.assertEqual((work/'new.go').read_bytes(),b'c')

    def test_candidate_manifest_and_gate_are_explicit(self):
        manifest=json.loads((ROOT/'labs/provider-contract/completion-manifest.json').read_text())
        self.assertFalse(manifest['production_qualified'])
        self.assertEqual(manifest['provider_commit'],'1718c946b3ae111bb44c7c1d925b3e35b708cb0a')
        for row in manifest['files']:
            path=ROOT/'labs/provider-contract/completion'/row['path']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),row['candidate_sha256'])

    def test_legacy_entrypoints_preserved_and_selected_resource_uses_strict_apis(self):
        def function(source, signature):
            start=source.index(signature)
            return source[start:source.index('\n}\n',start)+3]
        pairs=[
            ('internal/services/common/constructors/graph_beta/device_management/configuration_policy_settings.go','func ConstructSettingsCatalogSettings('),
            ('internal/services/common/state/graph_beta/device_management/configuration_policy_settings.go','func StateConfigurationPolicySettings('),
            ('internal/services/common/validate/graph_beta/device_management/settings_catalog_json_settings.go','func (v settingsCatalogJSONValidator) ValidateString('),
        ]
        for name, signature in pairs:
            original=(ROOT/'research/provider-qualification/raw/provider'/name).read_text()
            candidate=(ROOT/'labs/provider-contract/completion'/name).read_text()
            self.assertEqual(function(original,signature),function(candidate,signature),name)
        selected=ROOT/'labs/provider-contract/completion/internal/services/resources/device_management/graph_beta/settings_catalog_configuration_policy_json'
        self.assertIn('ConstructSettingsCatalogSettingsStrict(', (selected/'construct.go').read_text())
        self.assertIn('StrictSettingsCatalogJSONValidator()', (selected/'resource.go').read_text())
        read=(selected/'crud.go').read_text()
        self.assertIn('StateConfigurationPolicySettingsStrict(',read)
        self.assertIn('StateConfigurationPolicyAssignmentsStrict(',read)
        self.assertEqual(read.count('customrequest.GetConfigurationPolicyCollection('),2)
        self.assertNotIn('customrequest.GetRequestByResourceId(',read)
