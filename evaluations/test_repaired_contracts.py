"""Actual shared contract APIs. No provider/service/host qualification claims."""
import copy
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from reference.validation import (
    ContractViolation, capability_errors, capture_errors, provider_settings,
    reference_errors, schema_errors, validate_executable,
)
from corrections.models.contract_model import approval_mismatches

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'corrections' / 'fixtures'
def fixture(name):
    return json.loads((FIXTURES / name).read_text())


class RepairedContractTests(unittest.TestCase):
    def test_guid_predicates_every_schema_copy(self):
        """Real validator must reject whitespace for every GUID predicate."""
        nodes = []
        def walk(node, label):
            if isinstance(node, dict):
                if node.get('format') == 'uuid' or node.get('pattern', '').startswith('^[0-9a-fA-F]{8}-'):
                    nodes.append((node,label))
                for key, child in node.items():
                    walk(child, label + '/' + key)
            elif isinstance(node, list):
                for index, child in enumerate(node):
                    walk(child, label + '/' + str(index))
        for directory in [ROOT / 'contracts', ROOT / 'corrections' / 'contracts']:
            for path in directory.glob('*.schema.json'):
                walk(json.loads(path.read_text()), str(path.relative_to(ROOT)))
        self.assertGreater(len(nodes), 12)
        valid = '44444444-4444-4444-8444-444444444444'
        for node, label in nodes:
            validator = Draft202012Validator(node, format_checker=FormatChecker())
            with self.subTest(schema=label):
                self.assertEqual(node.get('minLength'), 36)
                self.assertEqual(node.get('maxLength'), 36)
                self.assertFalse(list(validator.iter_errors(valid)))
                for value in [valid+'\n', valid+'\r', valid+' ', ' '+valid, valid+'\t', valid[:-1]]:
                    self.assertTrue(list(validator.iter_errors(value)), repr(value))

    def test_projection_preserves_null_absent_and_order(self):
        setting = fixture('observed-setting.json')
        result = provider_settings([setting])
        self.assertEqual(result, fixture('provider-settings.corrected.json'))
        self.assertIsNot(result['settings'][0]['settingInstance'],setting['settingInstance'])
        instance = setting['settingInstance']
        del instance['settingInstanceTemplateReference']
        del instance['choiceSettingValue']['settingValueTemplateReference']
        child = copy.deepcopy(instance)
        child['settingDefinitionId'] = 'child-first'
        other = copy.deepcopy(child);other['settingDefinitionId'] = 'child-second'
        instance['choiceSettingValue']['children'] = [child,other]
        result = provider_settings([setting])
        self.assertEqual(result['settings'][0]['settingInstance'],instance)
        self.assertNotIn('settingInstanceTemplateReference',result['settings'][0]['settingInstance'])
        self.assertEqual(capability_errors([setting]),['unqualified_setting_capability'])

    def test_projection_ids_never_canonicalized_or_renumbered(self):
        for bad_id in ['0\n','00','1','-1',None,False]:
            setting=fixture('observed-setting.json');setting['id']=bad_id
            with self.subTest(id=bad_id),self.assertRaises(ContractViolation):
                provider_settings([setting])

    def test_description_local_boundaries_and_unicode(self):
        policy=fixture('observed-policy.json')
        for value in ['', 'x'*1500, '✓'*1500, '😀'*1500]:
            policy['description']=value
            self.assertEqual(schema_errors('observed-policy',policy),[])
        for value in ['x'*1501,'😀'*1501,None,False,{}]:
            policy['description']=value
            self.assertTrue(schema_errors('observed-policy',policy))
        # Codepoint length is our local boundary; a real provider's Unicode
        # validator/SDK behavior is deferred and cannot be proved here.

    def test_template_values_null_or_absent_only(self):
        for reference in ['settingInstanceTemplateReference','settingValueTemplateReference']:
            for bad_value in [{}, {'templateId':'CANARY-NONNULL'},'',False]:
                setting=fixture('observed-setting.json')
                node=setting['settingInstance']
                if reference=='settingValueTemplateReference':node=node['choiceSettingValue']
                node[reference]=bad_value
                self.assertTrue(schema_errors('observed-setting',setting))

    def test_policy_none_template_requires_explicit_observation(self):
        policy=fixture('observed-policy.json');del policy['templateReference']
        self.assertTrue(schema_errors('observed-policy',policy))

    def test_pipeline_missing_policy_template_is_review_only(self):
        from reference.core import normalize, generate_files
        source=fixture('source-export.json')
        policy=source['collections'][0]['pages'][0]['body']['value'][0]
        del policy['templateReference']
        normalized=normalize(source,policy['id'],source['tenant_id'])
        self.assertFalse(normalized['offline_mapping_complete'])
        self.assertTrue(normalized['blockers'])
        context=json.loads((ROOT/'examples/context.json').read_text())
        generated=generate_files(normalized,context)
        self.assertFalse(any(path.endswith(('.tf','.tf.json')) for path in generated))
        self.assertEqual(json.loads(generated['commands/command-cards.json'])['cards'],[])

    def test_capture_rejects_any_error_member_at_http_200(self):
        for error in [{},None,False,'',[],{'code':'SYNTHETIC-ERROR'}]:
            captured=fixture('capture.json')
            captured['pages'][0]['body']['error']=error
            root=captured['pages'][0]['request_url']
            with self.subTest(error=error):
                self.assertIn('error_page',capture_errors(captured,root))

    def test_pipeline_empty_error_page_is_review_only(self):
        from reference.core import normalize, generate_files
        source=json.loads((ROOT/'examples/supported/input/export.json').read_text())
        context=json.loads((ROOT/'examples/context.json').read_text())
        collection=next(c for c in source['collections'] if c['kind']=='assignments' and c['owner_id']==context['selected_policy_id'])
        collection['pages'][0]['body']['error']={}
        normalized=normalize(source,context['selected_policy_id'],context['tenant_id'])
        self.assertFalse(normalized['offline_mapping_complete'])
        self.assertTrue(normalized['blockers'])
        generated=generate_files(normalized,context)
        self.assertFalse(any(path.endswith(('.tf','.tf.json')) for path in generated))
        self.assertEqual(json.loads(generated['commands/command-cards.json'])['cards'],[])

    def test_capability_map_is_concrete_bounded_and_review_default(self):
        mapping=json.loads((ROOT/'corrections/contracts/capability-map.json').read_text())
        self.assertEqual(mapping['default_status'],'review_only')
        self.assertEqual(mapping['qualification'],'bounded_offline_mapping_only')
        self.assertEqual(len(mapping['entries']),1)
        setting=fixture('observed-setting.json')
        self.assertEqual(capability_errors([setting]),[])
        for change in ['definition','value','platform','technology','simple']:
            candidate=copy.deepcopy(setting);platform='windows10';technology='mdm'
            if change=='definition':candidate['settingInstance']['settingDefinitionId']='unmapped'
            if change=='value':candidate['settingInstance']['choiceSettingValue']['value']='unmapped'
            if change=='platform':platform='macOS'
            if change=='technology':technology='configManager'
            if change=='simple':
                candidate['settingInstance']={'@odata.type':'#microsoft.graph.deviceManagementConfigurationSimpleSettingInstance','settingDefinitionId':'unmapped','simpleSettingValue':{'@odata.type':'#microsoft.graph.deviceManagementConfigurationStringSettingValue','value':'shape-valid'}}
            self.assertEqual(schema_errors('observed-setting',candidate),[])
            self.assertEqual(capability_errors([candidate],platform,technology),['unqualified_setting_capability'])
        for key in ['setting_fixture','policy_fixture','provider_configuration_fixture','source_ledger']:
            self.assertTrue((ROOT/mapping['entries'][0]['provenance'][key]).is_file())

    def test_field_rules_explicit_metadata_null_reference_and_containers(self):
        with (ROOT/'corrections/contracts/field-rules.csv').open() as stream:
            rows=list(csv.DictReader(stream))
        for scope,field in [('policy','@odata.type'),('setting_instance','settingInstanceTemplateReference'),('setting_value','settingValueTemplateReference')]:
            self.assertTrue(any(r['scope']==scope and field in r['source_fields'].split(',') for r in rows))
        self.assertTrue(any(r['scope']=='accounting' and 'container' in r['source_fields'] for r in rows))

    def test_capture_chain_projections_and_unsafe_urls(self):
        captured=fixture('capture.json')
        root=captured['pages'][0]['request_url']
        self.assertEqual(capture_errors(captured,root),[])
        for suffix in ['?$filter=id%20ne%20null','?$select=id','?$search=text','?$expand=children','?$top=1','?$skip=1']:
            candidate=copy.deepcopy(captured)
            candidate['pages'][0]['body']['@odata.nextLink']=root+suffix
            next_page=copy.deepcopy(candidate['pages'][0]);next_page['request_url']=root+suffix
            next_page['body'].pop('@odata.nextLink');candidate['pages'].append(next_page)
            self.assertIn('unsupported_query',capture_errors(candidate,root))
        for url in [root+'#fragment',root.replace('https://','https://user:secret@'),root+'\n']:
            candidate=copy.deepcopy(captured);candidate['pages'][0]['request_url']=url
            self.assertTrue(capture_errors(candidate,root))
        self.assertEqual(capture_errors(captured,root+'?$top=1'),['invalid_adapter_boundary'])

    def test_duplicate_reference_case_insensitive_rejection(self):
        records=[{'kind':'group','id':'44444444-AAAA-4444-8444-444444444444'}]
        self.assertEqual(reference_errors(records),[])
        records.append({'kind':'group','id':records[0]['id'].lower()})
        self.assertEqual(reference_errors(records),['duplicate_reference'])

    def test_valid_auth_object_null_transitions(self):
        federated=fixture('approval-context.json')
        for kind in ['managed_identity','application_certificate']:
            other=copy.deepcopy(federated);other['binding']['identity'].update(auth_kind=kind,federation=None)
            self.assertEqual(schema_errors('approval-context',other),[])
            for expected,observed in [(federated,other),(other,federated)]:
                self.assertEqual(approval_mismatches(expected,observed['binding'],'2026-09-30T12:30:00Z'),['binding/identity/auth_kind','binding/identity/federation'])

    def test_registry_blocks_builtins_keywords_assignments_and_absent_tools(self):
        for token in ['exit','printf','read','set','eval','command','true','false','for','if','AUDIT=probe','-tofu','tofu\n','unregistered-missing-tool','/tmp/tofu','']:
            with self.subTest(token=token),self.assertRaises(ContractViolation):validate_executable(token)
        for token in ['atmos','tofu','python',sys.executable]:
            self.assertEqual(validate_executable(token),token)

    def test_safe_schema_diagnostics_never_echo_rejected_payload(self):
        marker='CANARY-UNKNOWN-KEY-PRIVATE'
        policy=fixture('observed-policy.json');policy[marker]={marker:marker}
        errors=schema_errors('observed-policy',policy)
        self.assertTrue(errors);self.assertNotIn(marker,json.dumps(errors))
        with self.assertRaises(ContractViolation):schema_errors('../private',{})

    def test_package_import_and_fixture_validation_from_other_cwd(self):
        env=dict(os.environ);env['PYTHONPATH']=str(ROOT)+os.pathsep+env.get('PYTHONPATH','')
        env['PYTHONDONTWRITEBYTECODE']='1'
        code='import json;from pathlib import Path;from reference.validation import schema_errors;assert not schema_errors("observed-setting",json.loads(Path('+repr(str(FIXTURES/'observed-setting.json'))+').read_text()))'
        with tempfile.TemporaryDirectory() as cwd:
            run=subprocess.run([sys.executable,'-c',code],cwd=cwd,env=env,text=True,capture_output=True)
        self.assertEqual(run.returncode,0,run.stderr)


if __name__=='__main__':
    unittest.main()
