"""Independent documentation facts and persisted repository navigation assertions."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import workbench_provenance as provenance
from intune_iac.io import AppError
from plugin_tests.test_workbench_provenance import MemoryStore, OBJECT, DEFINITION

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'


def hashed(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def report():
    first = {'path': 'stacks/base.yaml', 'pointer': '/vars/region', 'line': 2, 'column': 11}
    second = {'path': 'stacks/dev.yaml', 'pointer': '/components/terraform/app/vars/region', 'line': 9, 'column': 17}
    sources = [{'path': 'stacks/base.yaml', 'sha256': 'a' * 64}, {'path': 'stacks/dev.yaml', 'sha256': 'b' * 64}]
    return {'schema_version': '1.0', 'adapter': 'atmos-literal/1.0', 'status': 'resolved',
        'evaluation_scope': 'repository_local_literal_configuration', 'execution_authorized': False,
        'root': '/declared/repo', 'stack': 'dev', 'component': 'app', 'implementation_path': 'components/terraform/app',
        'sources': sources, 'source_fingerprint': hashed({'adapter': 'atmos-literal/1.0', 'sources': sources}),
        'configuration_sha256': 'c' * 64, 'effective_fields': ['/vars/region'], 'blockers': [],
        'provenance': {'/vars/region': {'winner': second, 'history': [first, second]}}}


class SourceStore(MemoryStore):
    def __init__(self, source=None):
        super().__init__()
        self.source = {} if source is None else source

    def inspect(self, object_id):
        return {**super().inspect(object_id), 'source': copy.deepcopy(self.source)}


class VendorLineageTests(unittest.TestCase):
    def test_official_csp_facts_remain_separate_from_graph_value_mapping(self):
        row = provenance.dictionary(MemoryStore(), DEFINITION)['entries'][0]
        vendor = row['vendor_documentation'][0]
        self.assertEqual(vendor['csp_uri'], './Device/Vendor/MSFT/Policy/Config/Privacy/LetAppsAccessLocation')
        self.assertEqual(vendor['data_type'], 'int')
        self.assertEqual(vendor['allowed_values'], [{'value': 0, 'meaning': 'User in control'},
            {'value': 1, 'meaning': 'Force allow'}, {'value': 2, 'meaning': 'Force deny'}])
        self.assertEqual(vendor['default_value'], 0)
        self.assertEqual(vendor['applicability']['scope'], 'device')
        self.assertEqual(vendor['applicability']['minimum_windows_version'], '10.0.14393')
        self.assertEqual(vendor['assertion_class'], 'vendor_documentation')
        self.assertEqual(vendor['documentation']['source_date'], '2026-09-10')
        self.assertFalse(vendor['graph_value_translation_verified'])
        self.assertFalse(vendor['applies_to_observed_device_verified'])
        self.assertEqual(row['meaning'], 'unknown')
        self.assertEqual(row['actual_uses'][0]['value']['choiceSettingValue']['value'], 2)
        self.assertFalse(provenance.dictionary(MemoryStore())['execution_authorized'])

    def test_documented_alias_search_is_case_insensitive(self):
        found = provenance.dictionary(MemoryStore(), 'WINDOWS APPS ACCESS LOCATION')['entries']
        self.assertEqual([r['identifier'] for r in found], [DEFINITION])
        self.assertEqual(provenance.dictionary(MemoryStore(), 'Privacy/LetAppsAccessLocation')['entries'][0]['identifier'], DEFINITION)

    def test_unknown_and_similar_identifiers_do_not_inherit_vendor_facts(self):
        store = MemoryStore()
        store.body['settings']['settings'][0]['settingInstance']['settingDefinitionId'] = DEFINITION + '_spoof'
        row = provenance.dictionary(store)['entries'][0]
        self.assertEqual(row['vendor_documentation'], [])
        self.assertEqual(row['meaning'], 'unknown')

    def test_builtin_documentation_pin_rejects_modified_data(self):
        original = provenance._read
        def altered(path):
            raw = original(path)
            if str(path).endswith('vendor-documentation.json'): return raw.replace(b'Force deny', b'Force help')
            return raw
        with patch.object(provenance, '_read', side_effect=altered), self.assertRaises(AppError) as error:
            provenance.dictionary(MemoryStore())
        self.assertEqual(error.exception.code, 'workbench_vendor_documentation_changed')

    def test_missing_repository_evidence_remains_unknown(self):
        result = provenance.repository_lineage(SourceStore(), OBJECT)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['fields'], [])
        self.assertFalse(result['native_atmos_qualified'])

    def test_lineage_winning_and_earlier_sources_and_hashes_are_retained(self):
        result = provenance.repository_lineage(SourceStore({'repository_resolution': report()}), OBJECT, '/vars/region')
        self.assertEqual(result['status'], 'available')
        self.assertEqual(len(result['fields']), 1)
        field = result['fields'][0]
        self.assertEqual(field['effective_pointer'], '/vars/region')
        self.assertEqual(field['winner']['path'], 'stacks/dev.yaml')
        self.assertEqual(field['winner']['sha256'], 'b' * 64)
        self.assertEqual(field['earlier_origins'][0]['path'], 'stacks/base.yaml')
        self.assertEqual(field['earlier_origins'][0]['line'], 2)
        self.assertFalse(result['effective_values_included'])
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['source_authenticity_verified'])

    def test_malformed_and_unknown_field_selectors_rejected(self):
        store = SourceStore({'repository_resolution': report()})
        for pointer in ('vars/region', '/vars/~2bad', '/vars/\x1b', '/' + 'x' * 1024):
            with self.subTest(pointer=pointer), self.assertRaises(AppError):
                provenance.repository_lineage(store, OBJECT, pointer)
        with self.assertRaises(AppError) as error: provenance.repository_lineage(store, OBJECT, '/absent')
        self.assertEqual(error.exception.code, 'workbench_lineage_field_unknown')

    def test_unknown_source_and_inconsistent_winner_do_not_become_lineage(self):
        for change in ('path', 'winner', 'source_hash', 'fingerprint', 'effective_values', 'authority'):
            item = report()
            if change == 'path': item['provenance']['/vars/region']['history'][0]['path'] = '../escape'
            if change == 'winner': item['provenance']['/vars/region']['winner'] = item['provenance']['/vars/region']['history'][0]
            if change == 'source_hash': item['sources'][0]['sha256'] = 'wrong'
            if change == 'fingerprint': item['source_fingerprint'] = 'f' * 64
            if change == 'effective_values': item['effective'] = {'secret': 'inert canary'}
            if change == 'authority': item['execution_authorized'] = True
            with self.subTest(change=change), self.assertRaises(AppError):
                provenance.repository_lineage(SourceStore({'repository_resolution': item}), OBJECT)

    def test_missing_fields_cannot_silently_truncate_lineage(self):
        item = report(); item['effective_fields'].append('/vars/unknown')
        with self.assertRaises(AppError): provenance.repository_lineage(SourceStore({'repository_resolution': item}), OBJECT)

    def test_lineage_limits_are_explicit_failures(self):
        item = report(); store = SourceStore({'repository_resolution': item})
        with patch.object(provenance, 'MAX_LINEAGE_ORIGINS', 1), self.assertRaises(AppError) as error:
            provenance.repository_lineage(store, OBJECT)
        self.assertEqual(error.exception.code, 'workbench_lineage_limit')

    def test_blocked_literal_resolution_remains_blocked(self):
        item = report(); item.update(status='blocked', provenance={}, effective_fields=[], blockers=[{'code': 'inheritance_cycle', 'status': 'unknown'}])
        result = provenance.repository_lineage(SourceStore({'repository_resolution': item}), OBJECT)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['blockers'][0]['code'], 'inheritance_cycle')
        self.assertEqual(result['fields'], [])

    def test_adoption_fallback_is_historical_and_bound_to_exact_object(self):
        store = SourceStore()
        binding = {'schema_version': 'workbench-adoption/1', 'tenant_id': store.tenant_id,
                   'object_ids': [OBJECT], 'repository': report(), 'execution_authorized': False}
        row = store.record_artifact('adoption', OBJECT, {'schema_version': 'workbench-adoption/1',
            'tenant_id': store.tenant_id, 'object_id': OBJECT, 'binding': binding,
            'binding_sha256': hashed(binding), 'execution_authorized': False, 'cloud_authority': False})
        result = provenance.repository_lineage(store, OBJECT, '/vars/region')
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['freshness'], 'historical_not_revalidated')
        self.assertEqual(result['provenance_origin']['artifact_id'], row['artifact_id'])
        self.assertFalse(result['repository']['current_source_bytes_verified'])
        store.rows[0]['data']['binding_sha256'] = '0' * 64
        with self.assertRaises(AppError): provenance.repository_lineage(store, OBJECT)

    def test_current_resolution_wins_over_historical_adoption(self):
        store = SourceStore({'repository_resolution': report()})
        store.record_artifact('adoption', OBJECT, {'untrusted': 'not consulted when current observation is available'})
        result = provenance.repository_lineage(store, OBJECT)
        self.assertEqual(result['provenance_origin']['kind'], 'current_observation')
        self.assertEqual(result['freshness'], 'fresh')

    def test_adoption_wrong_object_cannot_supply_repository_lineage(self):
        store = SourceStore()
        binding = {'schema_version': 'workbench-adoption/1', 'tenant_id': store.tenant_id,
                   'object_ids': ['33333333-3333-4333-8333-333333333333'], 'repository': report(), 'execution_authorized': False}
        store.record_artifact('adoption', OBJECT, {'schema_version': 'workbench-adoption/1',
            'tenant_id': store.tenant_id, 'object_id': OBJECT, 'binding': binding,
            'binding_sha256': hashed(binding), 'execution_authorized': False, 'cloud_authority': False})
        with self.assertRaises(AppError): provenance.repository_lineage(store, OBJECT)

    def test_dictionary_advertises_navigation_without_hiding_historical_fallback(self):
        store = SourceStore()
        binding = {'schema_version': 'workbench-adoption/1', 'tenant_id': store.tenant_id,
                   'object_ids': [OBJECT], 'repository': report(), 'execution_authorized': False}
        store.record_artifact('adoption', OBJECT, {'schema_version': 'workbench-adoption/1',
            'tenant_id': store.tenant_id, 'object_id': OBJECT, 'binding': binding,
            'binding_sha256': hashed(binding), 'execution_authorized': False, 'cloud_authority': False})
        navigation = provenance.dictionary(store, DEFINITION)['entries'][0]['actual_uses'][0]['repository_lineage']
        self.assertTrue(navigation['navigation_supported'])
        self.assertFalse(navigation['current_resolution_recorded'])
        self.assertEqual(navigation['historical_resolution_status'], 'query_required')
        self.assertNotIn('available', navigation)
        result = provenance.repository_lineage(store, OBJECT)
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['freshness'], 'historical_not_revalidated')

    def test_non_mapping_adoption_data_has_a_safe_error(self):
        store = SourceStore()
        store.rows.append({'kind': 'adoption', 'tenant_id': store.tenant_id, 'object_id': OBJECT, 'data': []})
        with self.assertRaises(AppError) as error: provenance.repository_lineage(store, OBJECT)
        self.assertEqual(error.exception.code, 'workbench_lineage_adoption_invalid')


class VendorLineageCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store, self.service, self.repo = [self.root / name for name in ('store', 'service', 'repo')]
        self.call('init', '--root', self.store, '--tenant', '11111111-1111-4111-8111-111111111111')
        self.call('lab-create', '--service-root', self.service, '--input', ROOT / 'examples/supported/input/export.json', '--object', OBJECT)
        (self.repo / 'stacks/deploy').mkdir(parents=True)
        (self.repo / 'components/terraform/app').mkdir(parents=True)
        (self.repo / 'atmos.yaml').write_text('stacks:\n  base_path: stacks\n  included_paths: ["deploy/**/*"]\ncomponents:\n  terraform:\n    base_path: components/terraform\n    command: tofu\n')
        (self.repo / 'stacks/base.yaml').write_text('vars:\n  region: inherited\n  secret: inert-canary-value\n')
        (self.repo / 'stacks/deploy/dev.yaml').write_text('import: [base]\ncomponents:\n  terraform:\n    app:\n      vars:\n        region: intentional-override\n')
        self.call('collect', '--root', self.store, '--service-root', self.service, '--repo', self.repo, '--stack', 'deploy/dev', '--component', 'app')

    def call(self, *args, input=None):
        done = subprocess.run([sys.executable, '-B', str(CLI), 'workbench', *map(str, args)],
            capture_output=True, text=True, input=input, timeout=30, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        return done.stdout if input is not None else json.loads(done.stdout)

    def test_real_cli_alias_facts_and_source_navigation(self):
        result = self.call('dictionary', '--root', self.store, '--query', 'Let Windows apps access location')
        self.assertEqual(result['entries'][0]['vendor_documentation'][0]['data_type'], 'int')
        result = self.call('lineage', '--root', self.store, '--object', OBJECT, '--pointer', '/vars/region')
        field = result['fields'][0]
        self.assertEqual(field['winner']['path'], 'stacks/deploy/dev.yaml')
        self.assertEqual(field['earlier_origins'][0]['path'], 'stacks/base.yaml')
        self.assertEqual(field['winner']['sha256'], hashlib.sha256((self.repo / 'stacks/deploy/dev.yaml').read_bytes()).hexdigest())
        self.assertNotIn('inert-canary-value', json.dumps(result))
        self.assertNotIn('intentional-override', json.dumps(result))

    def test_reopened_terminal_lineage_is_inert_and_selection_bound(self):
        result = self.call('terminal', '--root', self.store,
            input=f'lineage\nselect {OBJECT}\nlineage /vars/region\nback\nlineage\nquit\n')
        self.assertIn('selection_required', result)
        self.assertIn('stacks/deploy/dev.yaml', result)
        self.assertIn('earlier_origins', result)
        self.assertNotIn('inert-canary-value', result)


if __name__ == '__main__': unittest.main()
