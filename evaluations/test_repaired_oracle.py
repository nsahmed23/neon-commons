"""Executable independent preservation and emitted-artifact mutations."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import unittest

from reference.core import normalize, generate_files
from reference import invariants

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = json.loads((ROOT / 'examples/context.json').read_text())
RAW = (ROOT / 'examples/supported/input/export.json').read_bytes()
SOURCE = json.loads(RAW)


def record(source, collection):
    return source['collections'][collection]['pages'][0]['body']['value'][0]


class RepairedOracle(unittest.TestCase):
    def setUp(self):
        self.source = copy.deepcopy(SOURCE)
        self.normalized = normalize(self.source, CONTEXT['selected_policy_id'], CONTEXT['tenant_id'])
        self.files = generate_files(self.normalized, CONTEXT)

    def check(self, source=None, normalized=None, files=None, context=None):
        return invariants.compare(self.source if source is None else source,
                                  self.normalized if normalized is None else normalized,
                                  self.files if files is None else files,
                                  CONTEXT if context is None else context)

    def test_four_real_fixture_positive_and_two_argument_api(self):
        for name in ['supported', 'partial', 'access-denied', 'missing-page']:
            with self.subTest(name=name):
                raw = (ROOT / 'examples' / name / 'input/export.json').read_bytes()
                source = json.loads(raw)
                normalized = normalize(source, CONTEXT['selected_policy_id'], CONTEXT['tenant_id'])
                files = generate_files(normalized, CONTEXT)
                files['adoption/source-receipt.json'] = json.dumps({
                    'schema_version': '1.0.0', 'source_byte_sha256': hashlib.sha256(raw).hexdigest(),
                    'source_canonical_sha256': normalized['source_canonical_sha256']})
                self.assertEqual(invariants.compare(raw, normalized, files, CONTEXT), [])
                self.assertEqual(invariants.compare(source, normalized), [])

    def test_oracle_has_no_producer_imports(self):
        tree = ast.parse((ROOT / 'reference/invariants.py').read_text())
        forbidden = {'core', 'validation', 'field_accounting', 'contract_model'}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertFalse(set((node.module or '').split('.')) & forbidden)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(set(alias.name.split('.')) & forbidden)

    def test_identity_key_digest_tenant_mutations(self):
        for field, code, value in [
            ('key', 'resource_key_changed', self.normalized['key'] + '_changed'),
            ('object_id', 'selected_id_not_present', '33333333-3333-4333-8333-333333333333'),
            ('tenant_id', 'tenant_changed', '33333333-3333-4333-8333-333333333333'),
            ('source_canonical_sha256', 'source_digest_changed', '0' * 64)]:
            with self.subTest(field=field):
                normalized = copy.deepcopy(self.normalized)
                normalized[field] = value
                self.assertIn(code, self.check(normalized=normalized))

    def test_technology_scope_policy_observed_mutations(self):
        for field, value, code in [('technologies', ['microsoftSense'], 'technologies'),
                                   ('role_scope_tag_ids', [], 'roleScopeTagIds'),
                                   ('description', 'changed', 'description')]:
            normalized = copy.deepcopy(self.normalized)
            normalized['desired'][field] = value
            self.assertIn('policy_field_changed:' + code, self.check(normalized=normalized))
        normalized = copy.deepcopy(self.normalized)
        normalized['observed']['policy']['id'] = '33333333-3333-4333-8333-333333333333'
        self.assertIn('observed_records_changed', self.check(normalized=normalized))

    def test_settings_id_value_type_child_order_and_wrapper(self):
        mutations = [lambda s: s.update(id='1'),
                     lambda s: s.update(**{'@odata.type': '#microsoft.graph.deviceManagementConfigurationSetting'}),
                     lambda s: s['settingInstance']['choiceSettingValue'].update(value='CHANGED'),
                     lambda s: s['settingInstance']['choiceSettingValue'].update(value=2),
                     lambda s: s['settingInstance']['choiceSettingValue'].update(children=[{'a': 1}, {'b': 2}]),
                     lambda s: s['settingInstance'].update(**{'@odata.type': '#microsoft.graph.deviceManagementConfigurationSimpleSettingInstance'})]
        for mutate in mutations:
            normalized = copy.deepcopy(self.normalized)
            mutate(normalized['desired']['settings']['settings'][0])
            self.assertIn('settings_subtree_changed', self.check(normalized=normalized))

    def test_assignment_deletion_addition_type_filter_mode_and_id(self):
        mutations = [lambda a: a.pop(), lambda a: a.append(copy.deepcopy(a[0])),
                     lambda a: a[2].update(type='groupAssignmentTarget'),
                     lambda a: a[0].update(filter_type='exclude'),
                     lambda a: a[0].update(filter_id='88888888-8888-4888-8888-888888888888'),
                     lambda a: a[1].update(filter_id=None)]
        for mutate in mutations:
            normalized = copy.deepcopy(self.normalized)
            mutate(normalized['desired']['assignments'])
            self.assertIn('assignment_multiset_changed', self.check(normalized=normalized))
        normalized = copy.deepcopy(self.normalized)
        normalized['desired']['assignments'].reverse()
        self.assertNotIn('assignment_multiset_changed', self.check(normalized=normalized))

    def test_reference_removal_duplicate_contradiction_and_absent(self):
        for mutate in [lambda n: n['references'].pop(),
                       lambda n: n['references'].append(copy.deepcopy(n['references'][0])),
                       lambda n: n['references'][0].update(ownership='managed'),
                       lambda n: n.update(references=[]), lambda n: n.pop('references')]:
            normalized = copy.deepcopy(self.normalized)
            mutate(normalized)
            self.assertIn('references_changed', self.check(normalized=normalized))

    def test_every_disposition_and_loss_flag_mutation(self):
        for index in range(len(self.normalized['field_accounting'])):
            for field, value in [('disposition', 'unsupported'), ('loss_blocking', True)]:
                with self.subTest(index=index, field=field):
                    normalized = copy.deepcopy(self.normalized)
                    normalized['field_accounting'][index][field] = value
                    self.assertIn('source_field_accounting_changed', self.check(normalized=normalized))

    def test_accounting_destination_rule_reason_and_missing_container(self):
        for field, value in [('destination_pointers', ['/desired/WRONG']), ('rule_id', 'WRONG'),
                             ('rule_version', 'WRONG'), ('kind', 'null'), ('reason', 'WRONG')]:
            normalized = copy.deepcopy(self.normalized)
            normalized['field_accounting'][0][field] = value
            self.assertIn('source_field_accounting_changed', self.check(normalized=normalized))
        normalized = copy.deepcopy(self.normalized)
        normalized['field_accounting'].pop(0)
        self.assertIn('source_field_accounting_not_closed', self.check(normalized=normalized))

    def test_generated_hcl_import_address_and_id_mutations(self):
        name = 'components/terraform/intune-reference/imports.tf'
        for old, new in [(CONTEXT['selected_policy_id'], '33333333-3333-4333-8333-333333333333'),
                         (self.normalized['key'], self.normalized['key'] + '_different'),
                         ('.policy[', '.other[')]:
            files = dict(self.files)
            files[name] = files[name].replace(old, new)
            self.assertIn('generated_import_identity_changed', self.check(files=files))

    def test_generated_actual_resource_and_settings_json_mutations(self):
        files = dict(self.files)
        name = 'components/terraform/intune-reference/main.tf'
        files[name] = files[name].replace('settings           = jsonencode(each.value.settings)',
                                         'settings           = jsonencode({settings = []})')
        self.assertIn('generated_resource_field_changed', self.check(files=files))
        for field, value in [('id', '1'), ('value', 'CHANGED')]:
            files = dict(self.files)
            path = 'components/terraform/intune-reference/adoption-input.json'
            adoption = json.loads(files[path])
            setting = adoption['desired']['settings']['settings'][0]
            if field == 'id':
                setting['id'] = value
            else:
                setting['settingInstance']['choiceSettingValue']['value'] = value
            files[path] = json.dumps(adoption)
            self.assertIn('generated_desired_changed', self.check(files=files))

    def test_generated_object_map_and_extra_active_resource(self):
        files = dict(self.files)
        path = 'adoption/object-map.json'
        obj = json.loads(files[path]); obj['objects'][0]['import_id'] = '33333333-3333-4333-8333-333333333333'
        files[path] = json.dumps(obj)
        self.assertIn('generated_object_map_changed', self.check(files=files))
        files = dict(self.files)
        files['components/terraform/intune-reference/extra.tf'] = 'resource "null_resource" "extra" {}'
        self.assertIn('generated_resource_address_changed', self.check(files=files))
        files = dict(self.files)
        files['components/terraform/intune-reference/extra.tf'] = 'data "external" "extra" { program = ["bad"] }'
        self.assertIn('generated_hcl_blocks_changed', self.check(files=files))

    def test_review_proven_generated_guard_and_command_bypasses(self):
        main = 'components/terraform/intune-reference/main.tf'
        imports = 'components/terraform/intune-reference/imports.tf'
        mutations = [
            (imports, lambda text: text.replace('import {', 'import {\n provider = microsoft365.wrong'), 'generated_import_identity_changed'),
            (main, lambda text: text.replace('prevent_destroy = true', 'prevent_destroy = true\n ignore_changes = all'), 'generated_guard_changed'),
            ('commands/command-cards.json', lambda text: text.replace('"executable": "atmos"', '"executable": "evil"'), 'generated_command_contract_changed'),
            ('stacks/orgs/reference/dev.yaml', lambda text: text.replace('live_qualification_ack: false', 'live_qualification_ack: true'), 'generated_stack_guard_changed'),
            ('atmos.yaml', lambda text: text.replace('command: tofu', 'command: evil'), 'generated_stack_guard_changed'),
            ('commands/PROPOSED-import.sh.txt', lambda text: text.replace('atmos terraform', 'evil terraform'), 'generated_command_preview_changed'),
            ('commands/PROPOSED-import.ps1.txt', lambda text: text.replace("$exe = 'atmos'", "$exe = 'evil'"), 'generated_command_preview_changed')]
        for path, mutate, code in mutations:
            with self.subTest(path=path, code=code):
                files = dict(self.files); files[path] = mutate(files[path])
                self.assertIn(code, self.check(files=files))
        for path in [main, imports]:
            files = dict(self.files); files['review/' + Path(path).name] = files.pop(path)
            self.assertIn('generated_component_paths_changed', self.check(files=files))
        files = dict(self.files); files['commands/run.sh'] = 'atmos terraform apply'
        self.assertIn('generated_active_script_unqualified', self.check(files=files))
        for path, value in [('components/terraform/intune-reference/override.auto.tfvars', 'live_qualification_ack = true'),
                            ('components/terraform/intune-reference/terraform.tfvars.json', '{"live_qualification_ack":true}'),
                            ('stacks/orgs/extra/override.yaml', 'vars: {live_qualification_ack: true}')]:
            files = dict(self.files); files[path] = value
            self.assertIn('generated_config_path_unqualified', self.check(files=files))

    def test_incomplete_chain_cannot_claim_complete(self):
        for mutate in [lambda s: s['collections'][2]['pages'][0].update(request_url=s['collections'][2]['pages'][0]['request_url'] + '?$skiptoken=second'),
                       lambda s: s['collections'][2]['pages'][0]['body'].update(**{'@odata.nextLink': s['collections'][2]['pages'][0]['request_url'] + '?$skiptoken=second'}),
                       lambda s: s['collections'][2]['pages'][0]['body'].update(error={})]:
            source = copy.deepcopy(self.source); mutate(source)
            normalized = copy.deepcopy(self.normalized)
            normalized['source_canonical_sha256'] = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            self.assertIn('mapping_status_changed', self.check(source=source, normalized=normalized))

    def test_safe_partial_projection_supported_malformed_known_and_canaries(self):
        mutations = [lambda s: record(s, 0).update(technologies='unsupported'),
                     lambda s: record(s, 0).update(description='x' * 1501),
                     lambda s: record(s, 1).update(id='01'),
                     lambda s: record(s, 1)['settingInstance'].update(settingDefinitionId='unmapped_definition'),
                     lambda s: record(s, 2)['target'].update(groupId='invalid'),
                     lambda s: s['references'][0].update(id='invalid'),
                     lambda s: s['references'].append(copy.deepcopy(s['references'][0])),
                     lambda s: record(s, 1)['settingInstance'].update(KEY_CANARY_9172={'payload': 'VALUE_CANARY_9172'}),
                     lambda s: record(s, 1)['settingInstance']['choiceSettingValue'].update(**{'@odata.type': '#microsoft.graph.deviceManagementConfigurationSecretSettingValue', 'value': 'SECRET_CANARY_9172'})]
        for mutate in mutations:
            source = copy.deepcopy(self.source); mutate(source)
            normalized = normalize(source, CONTEXT['selected_policy_id'], CONTEXT['tenant_id'])
            files = generate_files(normalized, CONTEXT)
            self.assertFalse(normalized['offline_mapping_complete'])
            self.assertEqual(self.check(source, normalized, files), [])

    def test_partial_no_active_files_cards_or_raw_canaries(self):
        source = copy.deepcopy(self.source)
        record(source, 1)['settingInstance']['KEY_CANARY_9172'] = {'payload': 'VALUE_CANARY_9172'}
        normalized = normalize(source, CONTEXT['selected_policy_id'], CONTEXT['tenant_id'])
        files = generate_files(normalized, CONTEXT)
        for path, value, code in [('evil.tf', 'resource "null_resource" "bad" {}', 'partial_has_active_infrastructure'),
                                  ('review/extra.txt', 'VALUE_CANARY_9172', 'restricted_raw_canary_exposed'),
                                  ('commands/command-cards.json', json.dumps({'schema_version': '1.0.0', 'cards': [{'execution_allowed': False}]}), 'partial_has_command_cards')]:
            mutated = dict(files); mutated[path] = value
            self.assertIn(code, self.check(source, normalized, mutated))
        row = next(r for r in normalized['field_accounting'] if r['loss_blocking'])
        row['retention_locator'] = 'public-copy'
        self.assertIn('source_field_accounting_changed', self.check(source, normalized, files))

    def test_raw_digest_receipt_and_strict_byte_parser(self):
        self.assertIn('raw_source_receipt_missing', self.check(source=RAW))
        files = dict(self.files)
        receipt = {'schema_version': '1.0.0', 'source_byte_sha256': hashlib.sha256(RAW).hexdigest(),
                   'source_canonical_sha256': self.normalized['source_canonical_sha256']}
        files['adoption/source-receipt.json'] = json.dumps(receipt)
        self.assertEqual(self.check(source=RAW, files=files), [])
        receipt['source_byte_sha256'] = '0' * 64
        files['adoption/source-receipt.json'] = json.dumps(receipt)
        self.assertIn('raw_source_digest_changed', self.check(source=RAW, files=files))
        for raw, expected in [(b'{"tenant_id":1,"tenant_id":2}', 'duplicate_json_key'),
                              (b'{"value":NaN}', 'unsupported_numeric_encoding'),
                              (b'{"value":1.1}', 'unsupported_numeric_encoding'),
                              (b'{"value":9007199254740992}', 'unsupported_numeric_encoding'),
                              (b'{' + b'"x":[' * 70 + b'0' + b']}' * 70, 'source_parse_failed')]:
            self.assertIn(expected, self.check(source=raw))

    def test_blanket_refusal_is_not_success_and_false_authority_detected(self):
        normalized = copy.deepcopy(self.normalized)
        normalized.update(offline_mapping_complete=False, blockers=[{'code': 'refusal', 'source_pointer': ''}])
        self.assertIn('mapping_status_changed', self.check(normalized=normalized))
        normalized = copy.deepcopy(self.normalized)
        normalized['execution_authorized'] = True
        self.assertIn('false_execution_authority', self.check(normalized=normalized))


if __name__ == '__main__':
    unittest.main()
