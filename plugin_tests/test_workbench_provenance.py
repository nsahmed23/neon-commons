"""Independent source/dictionary facts; invented local fixtures, no GPL payload."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from intune_iac.io import AppError
from intune_iac import workbench_provenance as provenance

TENANT = '11111111-1111-4111-8111-111111111111'
OBJECT = '22222222-2222-4222-8222-222222222222'
EXPORTED = '33333333-3333-4333-8333-333333333333'
OIB = '44444444-4444-4444-8444-444444444444'
DEFINITION = 'device_vendor_msft_policy_config_privacy_letappsaccesslocation'


def instance(value=2, identifier=DEFINITION):
    return {'@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance',
            'settingDefinitionId': identifier, 'settingInstanceTemplateReference': None,
            'choiceSettingValue': {'@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingValue',
                                   'value': value, 'children': [], 'settingValueTemplateReference': None}}


def policy(value=2):
    return {'id': EXPORTED, 'name': 'Invented reference', 'description': 'OIBID:' + OIB,
            'platforms': 'windows10', 'technologies': 'mdm', 'settingCount': 1,
            'settings': [{'id': '0', 'settingInstance': instance(value)}]}


class MemoryStore:
    tenant_id = TENANT

    def __init__(self):
        self.rows = []
        self.body = {'name': 'Observed company policy', 'settings': {'settings': [{'id': '0', 'settingInstance': instance(2)}]},
                     'assignments': [], 'platforms': 'windows10', 'technologies': ['mdm'], 'role_scope_tag_ids': ['0'], 'description': None}

    def record_artifact(self, kind, object_id, data):
        artifact_id = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        row = {'artifact_id': artifact_id, 'kind': kind, 'object_id': object_id,
               'tenant_id': self.tenant_id, 'data': copy.deepcopy(data), 'sequence': len(self.rows)+1}
        if not any(r['artifact_id'] == artifact_id for r in self.rows): self.rows.append(row)
        return {**row, 'created': True}

    def artifacts(self, kind=None, object_id=None, **kwargs):
        return copy.deepcopy([r for r in self.rows if kind is None or r['kind'] == kind])

    def inspect(self, object_id):
        if object_id != OBJECT: raise AppError('missing', 'No object.')
        return {'object_id': OBJECT, 'tenant_id': TENANT, 'body': copy.deepcopy(self.body),
                'snapshot_id': 'f'*64, 'observed_at': '2026-10-05T00:00:00Z', 'coverage': 'complete',
                'freshness': 'fresh', 'evidence_class': 'synthetic'}

    def overview(self):
        return {'objects': [self.inspect(OBJECT)], 'freshness': 'fresh'}


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.store = MemoryStore(); self.path = self.root/'reference.json'

    def save(self, value):
        self.path.write_text(json.dumps(value)); return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def import_ref(self, value=None, **kwargs):
        sha = self.save(policy() if value is None else value)
        options = dict(expected_sha256=sha, source_revision='a'*40,
                       source_url='https://example.invalid/blob/'+'a'*40+'/policy.json', license_id='GPL-3.0')
        options.update(kwargs)
        return provenance.reference_import(self.store, self.path, **options)

    def test_exact_provenance_preserves_raw_unknowns_without_adoption(self):
        value = policy(); value['unknownVendorProperty'] = {'bool': True, 'null': None}
        row = self.import_ref(value)
        data = row['data']
        self.assertEqual(data['raw_source'], value)
        self.assertEqual(data['source_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(data['upstream_oib_id'], OIB.lower())
        self.assertEqual(data['upstream_export_id'], EXPORTED)
        self.assertIsNone(row['object_id'])
        self.assertFalse(data['execution_authorized']); self.assertFalse(data['source_authenticity_verified'])
        self.assertIn('unknownVendorProperty', data['unknown_fields'])
        self.assertEqual(data['assignment_coverage'], 'unknown')

    def test_wrong_hash_rejects_without_artifact(self):
        with self.assertRaises(AppError): self.import_ref(expected_sha256='0'*64)
        self.assertEqual(self.store.rows, [])

    def test_duplicate_oib_token_is_rejected(self):
        value = policy(); value['description'] += ' OIBID:' + OIB
        with self.assertRaises(AppError): self.import_ref(value)

    def test_duplicate_json_properties_are_rejected(self):
        self.path.write_bytes(b'{"name":"first","name":"second"}')
        with self.assertRaises(AppError):
            provenance.reference_import(self.store, self.path, hashlib.sha256(self.path.read_bytes()).hexdigest(), 'a'*40,
                                        'https://example.invalid/policy', 'GPL-3.0')

    def test_symlink_directory_and_hardlink_inputs_are_rejected(self):
        sha = self.save(policy()); linked = self.root/'link'; linked.symlink_to(self.root, target_is_directory=True)
        for path in (linked/'reference.json',):
            with self.assertRaises(AppError): provenance.reference_import(self.store,path,sha,'a'*40,'https://example.invalid/p','GPL-3.0')
        os.link(self.path, self.root/'hardlink')
        with self.assertRaises(AppError): provenance.reference_import(self.store,self.path,sha,'a'*40,'https://example.invalid/p','GPL-3.0')

    def test_invalid_reference_bindings_and_vendor_claim_rejected(self):
        for override in ({'source_revision':'main'}, {'source_url':'http://example.invalid/p'},
                         {'source_url':'https://user:secret@example.invalid/p'}, {'source_url':'https://example.invalid/p?token=x'},
                         {'license_id':''}, {'assertion_class':'vendor_fact'}):
            with self.subTest(override=override), self.assertRaises(AppError): self.import_ref(**override)

    def test_dictionary_keeps_observed_local_and_community_facts_separate(self):
        row = self.import_ref(policy(0)); result = provenance.dictionary(self.store, DEFINITION)
        entry = next(e for e in result['entries'] if e['identifier'] == DEFINITION)
        self.assertEqual(entry['meaning'], 'unknown'); self.assertEqual(entry['vendor_dictionary'], 'unresolved')
        self.assertEqual(entry['actual_uses'][0]['object_id'], OBJECT)
        self.assertEqual(entry['actual_uses'][0]['value'], entry['actual_uses'][0]['instance'])
        self.assertEqual(entry['actual_uses'][0]['name'], 'Observed company policy')
        self.assertIn('source', entry['actual_uses'][0])
        self.assertEqual(entry['actual_uses'][0]['ownership'], 'unknown')
        self.assertEqual(entry['references'][0]['reference_id'], row['artifact_id'])
        self.assertEqual(entry['references'][0]['assertion_class'], 'community_reference')
        self.assertEqual(entry['local_mapping'][0]['qualification'], 'bounded_offline_mapping_only')

    def test_unknown_setting_is_retained_in_dictionary(self):
        value = policy(); value['settings'][0]['settingInstance'] = instance('opaque', 'future_setting')
        self.import_ref(value)
        entry = next(e for e in provenance.dictionary(self.store)['entries'] if e['identifier'] == 'future_setting')
        self.assertEqual(entry['local_mapping'], [])
        self.assertEqual(entry['references'][0]['instance']['choiceSettingValue']['value'], 'opaque')

    def test_without_company_input_comparison_does_not_invent_approval(self):
        row = self.import_ref(policy(0)); result = provenance.compare_reference(self.store, OBJECT, row['artifact_id'])
        self.assertEqual(result['comparisons']['upstream_vs_observed']['status'], 'different')
        self.assertEqual(result['comparisons']['company_vs_observed']['status'], 'unknown')
        self.assertFalse(result['automatic_overwrite']); self.assertFalse(result['execution_authorized'])

    def test_three_way_preserves_company_exception_and_typed_difference(self):
        row = self.import_ref(policy(True)); company = self.root/'company.json'
        company.write_text(json.dumps({'tenant_id': TENANT, 'object_id': OBJECT, 'settings': [{'settingInstance': instance(1)}]}))
        result = provenance.compare_reference(self.store, OBJECT, row['artifact_id'], company)
        self.assertEqual(result['company']['assertion_class'], 'caller_asserted_company_desired')
        self.assertEqual(result['comparisons']['upstream_vs_company']['status'], 'different')
        self.assertEqual(result['comparisons']['company_vs_observed']['status'], 'different')
        self.assertFalse(result['drift_established'])

    def test_company_wrong_identity_rejected(self):
        row = self.import_ref(); company = self.root/'company.json'
        company.write_text(json.dumps({'object_id':EXPORTED,'settings':[]}))
        with self.assertRaises(AppError): provenance.compare_reference(self.store, OBJECT, row['artifact_id'], company)

    def test_ambiguous_setting_ids_preserved_but_comparison_unknown(self):
        value = policy(); value['settings'].append({'id':'1','settingInstance':instance(9)}); value['settingCount']=2
        row = self.import_ref(value); result = provenance.compare_reference(self.store, OBJECT, row['artifact_id'])
        self.assertEqual(len(row['data']['raw_source']['settings']), 2)
        self.assertEqual(result['comparisons']['upstream_vs_observed']['status'], 'unknown')

    def test_same_display_name_does_not_establish_lineage(self):
        first = self.import_ref(); second = policy(); second['id']='55555555-5555-4555-8555-555555555555'; second['description']=''
        row = self.import_ref(second, source_revision='b'*40)
        result = provenance.compare_reference(self.store, OBJECT, row['artifact_id'])
        self.assertFalse(any(r['reference_id']==first['artifact_id'] for r in result['reference_history']))

    def test_history_recognizes_name_metadata_change_with_unchanged_settings(self):
        first = self.import_ref(); second = policy(); second['name']='Renamed reference'; second['lastModifiedDateTime']='2026-10-05T01:00:00Z'
        row = self.import_ref(second, source_revision='b'*40)
        previous = next(r for r in provenance.compare_reference(self.store, OBJECT, row['artifact_id'])['reference_history'] if r['reference_id']==first['artifact_id'])
        self.assertEqual(previous['change_class'], 'name_or_metadata_only')
        self.assertFalse(previous['tenant_identity_established'])

    def test_unrecognized_setting_alongside_known_setting_keeps_comparison_unknown(self):
        value = policy(); value['settings'].append({'id':'future', 'opaqueValue':42}); value['settingCount']=2
        row = self.import_ref(value)
        self.assertEqual(provenance.compare_reference(self.store,OBJECT,row['artifact_id'])['comparisons']['upstream_vs_observed']['status'],'unknown')

    def test_assignment_change_is_not_mislabeled_rename_only(self):
        first = self.import_ref(); value=policy(); value['assignments']=[{'unknownTarget':'keep'}]
        row=self.import_ref(value,source_revision='b'*40)
        previous=next(r for r in provenance.compare_reference(self.store,OBJECT,row['artifact_id'])['reference_history'] if r['reference_id']==first['artifact_id'])
        self.assertEqual(previous['change_class'],'non_setting_fields_changed')

    def test_stored_reference_hash_and_decoded_facts_are_rechecked(self):
        row=self.import_ref(); self.store.rows[0]['data']['raw_source']['name']='Forged'
        with self.assertRaises(AppError): provenance.dictionary(self.store)

    def test_known_reference_without_observed_usage_still_exposes_local_mapping(self):
        self.store.body['settings']={'settings':[]}; self.import_ref()
        entry=provenance.dictionary(self.store,DEFINITION)['entries'][0]
        self.assertEqual(len(entry['local_mapping']),1)

    def test_stored_claim_cannot_be_promoted_to_vendor_authority(self):
        self.import_ref(); self.store.rows[0]['data']['assertion_class']='vendor_fact'
        with self.assertRaises(AppError): provenance.dictionary(self.store)

    def test_duplicate_setting_row_ids_keep_comparison_unknown(self):
        value=policy(); value['settings'].append({'id':'0','settingInstance':instance(3,'other_definition')}); value['settingCount']=2
        row=self.import_ref(value)
        self.assertEqual(provenance.compare_reference(self.store,OBJECT,row['artifact_id'])['comparisons']['upstream_vs_observed']['status'],'unknown')

    def test_stored_name_cannot_disagree_with_raw_reference(self):
        self.import_ref(); self.store.rows[0]['data']['name']='Forged display'
        with self.assertRaises(AppError): provenance.dictionary(self.store)

    def test_oversized_input_rejected_before_import(self):
        self.path.write_bytes(b' '* (provenance.MAX_REFERENCE_BYTES+1))
        with self.assertRaises(AppError):
            provenance.reference_import(self.store,self.path,hashlib.sha256(self.path.read_bytes()).hexdigest(),'a'*40,'https://example.invalid/p','GPL-3.0')


if __name__ == '__main__': unittest.main()
