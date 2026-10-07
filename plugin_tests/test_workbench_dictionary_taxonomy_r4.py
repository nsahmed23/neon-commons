"""Actual dictionary routes and independent provenance-category expectations."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from intune_iac.io import AppError
from intune_iac.workbench_store import WorkbenchStore
from intune_iac import workbench_provenance as provenance
from intune_iac.synthetic import generate_estate

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'
SETTING = 'device_vendor_msft_policy_config_privacy_letappsaccesslocation'
VENDOR_SHA = 'c758641e932f85014e5ec3451073828ad0f04a20fb850196ae6bb1b0f699bcd8'


def reference(identifier=SETTING):
    return {'id': '81111111-1111-4111-8111-111111111111', 'name': 'Literal external advice',
            'platforms': 'windows10', 'technologies': 'mdm', 'settingCount': 1, 'assignments': [],
            'settings': [{'id': '0', 'settingInstance': {'@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance',
                'settingDefinitionId': identifier, 'choiceSettingValue': {'value': 'literal_reference_value', 'children': []}}}]}


class DictionaryTaxonomyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.estate = generate_estate(seed=815, policy_count=1)
        self.store = self.root / 'store'
        self.call('init', '--root', self.store, '--tenant', self.estate['truth']['tenant_id'])
        self.reference = self.root / 'reference.json'
        self.reference.write_text(json.dumps(reference()) + '\n')

    def process(self, *args):
        return subprocess.run([sys.executable, '-B', str(CLI), 'workbench', *map(str,args)],
                              cwd='/tmp', text=True, capture_output=True, timeout=15)

    def call(self, *args):
        result = self.process(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def import_reference(self, assertion_class):
        return self.call('reference-import', '--root', self.store, '--input', self.reference,
            '--sha256', hashlib.sha256(self.reference.read_bytes()).hexdigest(), '--revision', 'a'*40,
            '--source-url', 'https://learn.microsoft.com/example/unverified-reference', '--license', 'LicenseRef-Fixture',
            '--assertion-class', assertion_class)

    def dictionary(self, query=SETTING):
        return self.call('dictionary', '--root', self.store, '--query', query)

    def test_empty_dictionary_declares_absence_and_unsupported_ai_ingestion(self):
        value = self.dictionary()
        self.assertEqual(value['entries'], [])
        contract = value['fact_provenance_contract']
        self.assertEqual(contract['schema_version'], 'workbench-dictionary-provenance/1')
        self.assertEqual(set(contract['categories']), {'vendor_documentation', 'observed_value', 'community_advice',
            'company_annotation', 'local_mapping', 'ai_interpretation'})
        self.assertFalse(contract['source_authenticity_from_category'])
        self.assertFalse(contract['organizational_approval_from_category'])
        self.assertFalse(contract['execution_authorized'])
        self.assertEqual(contract['categories']['ai_interpretation']['origin'], 'not_implemented')
        self.assertFalse(contract['categories']['ai_interpretation']['caller_import_allowed'])

    def test_actual_cli_keeps_six_categories_and_per_record_observation_scope(self):
        community = self.import_reference('community_reference')
        company = self.import_reference('organization_annotation')
        capture = self.root / 'capture.json'; capture.write_text(json.dumps(self.estate['capture']))
        object_id = self.estate['truth']['policies'][0]['id']
        service = self.root / 'service'
        self.call('lab-create', '--service-root', service, '--input', capture, '--object', object_id)
        self.call('collect', '--root', self.store, '--service-root', service)
        entry = self.dictionary()['entries'][0]
        groups = entry['fact_provenance']['categories']
        self.assertEqual({k:v['record_count'] for k,v in groups.items()}, {
            'vendor_documentation': 1, 'observed_value': 1, 'community_advice': 1,
            'company_annotation': 1, 'local_mapping': 1, 'ai_interpretation': 0})
        for kind, assertion_class in [('community_advice','community_reference'),('company_annotation','organization_annotation')]:
            pointer = groups[kind]['record_pointers'][0].split('/')
            item = entry[pointer[1]][int(pointer[2])]
            self.assertEqual(item['assertion_class'], assertion_class)
            self.assertFalse(item['source_authenticity_verified'])
            self.assertEqual(item['reference_id'], community['artifact_id'] if kind=='community_advice' else company['artifact_id'])
        self.assertEqual(entry['actual_uses'][0]['object_id'], object_id)
        self.assertEqual(entry['actual_uses'][0]['evidence_class'], 'synthetic')
        self.assertEqual(entry['meaning'], 'unknown')
        self.assertEqual(entry['vendor_dictionary'], 'unresolved')
        self.assertEqual(groups['ai_interpretation']['availability'], 'not_implemented')
        self.assertEqual(groups['ai_interpretation']['record_pointers'], [])
        self.assertFalse(entry['fact_provenance']['cross_category_promotion'])

    def test_raw_claims_and_official_looking_url_cannot_install_vendor_facts(self):
        value = reference(); value['vendor_documentation'] = [{'meaning':'FORGED_VENDOR_FACT'}]
        value['ai_interpretation'] = {'assertion_class':'observed_value','value':'FORGED_SERVICE_FACT'}
        self.reference.write_text(json.dumps(value)+'\n')
        raw = self.reference.read_bytes()
        imported = self.import_reference('community_reference')
        entry = self.dictionary()['entries'][0]
        self.assertNotIn('FORGED_VENDOR_FACT', json.dumps(entry['vendor_documentation']))
        self.assertEqual(entry['actual_uses'], [])
        self.assertEqual(entry['fact_provenance']['categories']['observed_value']['availability'], 'absent')
        self.assertEqual(entry['fact_provenance']['categories']['ai_interpretation']['record_count'], 0)
        data = imported['data']
        self.assertEqual(base64.b64decode(data['raw_bytes_base64']), raw)
        self.assertEqual(data['raw_source'], value)
        self.assertIn('vendor_documentation', data['unknown_fields'])
        self.assertIn('ai_interpretation', data['unknown_fields'])
        self.assertEqual(hashlib.sha256((ROOT/'corrections/contracts/vendor-documentation.json').read_bytes()).hexdigest(), VENDOR_SHA)

    def test_unknown_identifier_has_explicit_absent_vendor_and_mapping(self):
        self.reference.write_text(json.dumps(reference('unrecognized_setting_with_vendor_label')))
        self.import_reference('organization_annotation')
        entry = self.dictionary('unrecognized_setting')['entries'][0]
        groups = entry['fact_provenance']['categories']
        self.assertEqual(groups['vendor_documentation']['availability'], 'absent')
        self.assertEqual(groups['local_mapping']['availability'], 'absent')
        self.assertEqual(groups['observed_value']['availability'], 'absent')
        self.assertEqual(groups['company_annotation']['record_count'], 1)
        self.assertEqual(groups['community_advice']['record_count'], 0)

    def test_cli_and_function_reject_ai_vendor_service_claim_import_classes(self):
        sha = hashlib.sha256(self.reference.read_bytes()).hexdigest()
        for claim in ('ai_interpretation', 'vendor_documentation', 'observed_value', 'service_fact', 'vendor_fact'):
            with self.subTest(claim=claim):
                result = self.process('reference-import', '--root', self.store, '--input', self.reference,
                    '--sha256', sha, '--revision', 'a'*40, '--source-url', 'https://example.invalid/reference',
                    '--license', 'LicenseRef-Fixture', '--assertion-class', claim)
                self.assertNotEqual(result.returncode, 0)
                with self.assertRaises(AppError):
                    provenance.reference_import(WorkbenchStore(self.store),self.reference,sha,'a'*40,
                                                'https://example.invalid/reference','LicenseRef-Fixture',claim)
        self.assertEqual(WorkbenchStore(self.store).artifacts(kind='source_reference'), [])

    def test_contract_returned_values_do_not_mutate_future_taxonomy(self):
        value = provenance.fact_taxonomy()
        value['categories']['ai_interpretation']['caller_import_allowed'] = True
        value['admitted_reference_assertion_classes'].append('vendor_documentation')
        fresh = provenance.fact_taxonomy()
        self.assertFalse(fresh['categories']['ai_interpretation']['caller_import_allowed'])
        self.assertEqual(fresh['admitted_reference_assertion_classes'], ['community_reference','organization_annotation'])


if __name__ == '__main__': unittest.main()
