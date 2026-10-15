"""Repository-owned desired policy: the reference consumer contract.

A copy of a generated project stands in for the engineer's repository. The
expected outcomes are written by hand.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

from intune_iac.engine import generate
from intune_iac.repository import resolve_component
from intune_iac.workbench_repository import consumer_contract

ROOT = Path(__file__).resolve().parents[1]
NORMALIZED = json.loads((ROOT / 'examples/supported/expected/normalized.json').read_text())
TENANT, OBJECT, KEY = NORMALIZED['tenant_id'], NORMALIZED['object_id'], NORMALIZED['key']
STACK = 'stacks/orgs/reference/dev.yaml'
MAIN = 'components/terraform/intune-reference/main.tf'


class ConsumerContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        generated = Path(temp.name) / 'generated'
        generate(ROOT / 'examples/supported/input/export.json', ROOT / 'examples/context.json', generated)
        # Generated output stays adoption evidence; the engineer maintains a copy.
        self.repo = Path(temp.name) / 'repository'
        shutil.copytree(generated, self.repo)

    def contract(self, pointer='/vars/policies/' + KEY, object_id=OBJECT, component='intune-reference'):
        report = resolve_component(self.repo, 'orgs/reference/dev', component)
        return consumer_contract(report, pointer, TENANT, object_id)

    def edit_stack(self, change):
        document = yaml.safe_load((self.repo / STACK).read_text())
        change(document['components']['terraform']['intune-reference']['vars'])
        (self.repo / STACK).write_text(yaml.safe_dump(document))

    def test_generated_copy_is_a_verified_consumer(self):
        result = self.contract()
        self.assertEqual(result['status'], 'verified', result['reasons'])
        self.assertEqual(result['reasons'], [])
        self.assertEqual(result['policy_key'], KEY)
        self.assertEqual(result['logical_stack'], 'reference-dev')
        self.assertFalse(result['execution_authorized'])

    def test_an_added_backend_block_is_accepted(self):
        (self.repo / 'components/terraform/intune-reference/backend.tf').write_text(
            'terraform {\n  backend "azurerm" {\n    use_azuread_auth = true\n  }\n}\n')
        self.assertEqual(self.contract()['status'], 'verified')

    def test_a_value_edit_keeps_the_consumer_verified(self):
        self.edit_stack(lambda v: v['policies'][KEY].update(description='Edited in the repository.'))
        self.assertEqual(self.contract()['status'], 'verified')

    def test_mismatches_are_named(self):
        cases = {
            'policy_keys_not_exactly_adopted': lambda: self.edit_stack(
                lambda v: v['policies'].update(p_sibling=v['policies'][KEY])),
            'qualification_guard_changed': lambda: self.edit_stack(lambda v: v.update(live_qualification_ack=True)),
            'generated_resource_field_changed': lambda: (self.repo / MAIN).write_text(
                (self.repo / MAIN).read_text().replace('name               = each.value.name', 'name               = "fixed"')),
            'generated_input_binding_changed': lambda: (self.repo / MAIN).write_text(
                (self.repo / MAIN).read_text().replace('resource "', 'locals {\n  hidden = 1\n}\nresource "', 1)),
            'generated_hcl_json_unqualified': lambda: (self.repo / 'components/terraform/intune-reference/extra.tf.json').write_text('{}'),
        }
        for reason, apply in cases.items():
            with self.subTest(reason=reason):
                self.setUp()
                apply()
                result = self.contract()
                self.assertEqual(result['status'], 'mismatch')
                self.assertIn(reason, result['reasons'])

    def test_a_pointer_for_another_object_is_a_key_identity_mismatch(self):
        other = '33333333-3333-4333-8333-333333333333'
        result = self.contract(object_id=other)
        self.assertEqual(result['status'], 'mismatch')
        self.assertIn('policy_key_identity', result['reasons'])

    def test_other_layouts_are_not_applicable(self):
        self.assertEqual(self.contract(pointer='/vars/native_policy')['status'], 'not_applicable')
        self.assertEqual(self.contract(pointer='/vars/policies/' + OBJECT)['status'], 'not_applicable')


class RepositoryOwnedChangeTests(unittest.TestCase):
    """Edit the maintained copy, see the intent go stale, refresh, propose, and recheck at execute."""
    RESOURCE_ADDRESS = 'microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json.policy["' + KEY + '"]'

    def setUp(self):
        from intune_iac.modeled_service import ModeledService
        from intune_iac.workbench_store import WorkbenchStore
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        generate(ROOT / 'examples/supported/input/export.json', ROOT / 'examples/context.json', self.root / 'generated')
        self.repo = self.root / 'repository'; shutil.copytree(self.root / 'generated', self.repo)
        capture = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        self.service = ModeledService.create(self.root / 'service', capture, [OBJECT])
        self.store = WorkbenchStore.create(self.root / 'store', TENANT)
        self.store.collect(self.service)

    def import_intent(self):
        from intune_iac import workbench_views as views
        return views.import_repository(self.store, self.repo, 'orgs/reference/dev', 'intune-reference', OBJECT,
                                       '/vars/policies/' + KEY, 'a' * 40, 'local', self.RESOURCE_ADDRESS)

    def edit_description(self, text):
        document = yaml.safe_load((self.repo / STACK).read_text())
        document['components']['terraform']['intune-reference']['vars']['policies'][KEY]['description'] = text
        (self.repo / STACK).write_text(yaml.safe_dump(document))

    def test_a_secret_in_the_stack_is_refused_at_import_and_never_recorded_or_echoed(self):
        from intune_iac.io import AppError
        cases = ({'@odata.type': '#microsoft.graph.deviceManagementConfigurationSecretSettingValue',
                  'value': 'hunter2-secret', 'valueState': 'notEncrypted'}, {'password': 'hunter2-secret'})
        original = (self.repo / STACK).read_text()
        for probe in cases:
            document = yaml.safe_load(original)
            document['components']['terraform']['intune-reference']['vars']['policies'][KEY]['settings']['probe'] = probe
            (self.repo / STACK).write_text(yaml.safe_dump(document))
            before = len(self.store.artifacts())
            with self.assertRaises(AppError) as caught:
                self.import_intent()
            self.assertEqual(caught.exception.code, 'workbench_repository_secret_value')
            self.assertNotIn('hunter2', str(caught.exception))
            self.assertEqual(len(self.store.artifacts()), before)

    def test_import_records_the_consumer_contract(self):
        intent = self.import_intent()
        self.assertEqual(intent['data']['consumer']['status'], 'verified')
        self.assertEqual(intent['data']['consumer']['logical_stack'], 'reference-dev')

    def test_lineage_follows_the_recorded_intent_through_atmos_inheritance(self):
        from intune_iac.workbench_provenance import repository_lineage
        before = repository_lineage(self.store, OBJECT)
        self.assertEqual((before['status'], before['reason']), ('unknown', 'repository_resolution_not_collected'))
        intent = self.import_intent()
        value = repository_lineage(self.store, OBJECT)
        self.assertEqual(value['status'], 'available')
        self.assertEqual(value['provenance_origin']['kind'], 'repository_intent')
        self.assertEqual(value['provenance_origin']['artifact_id'], intent['artifact_id'])
        self.assertEqual(value['freshness'], 'recorded_intent_not_revalidated')
        self.assertEqual(value['repository']['stack'], 'orgs/reference/dev')
        fields = {row['effective_pointer']: row for row in value['fields']}
        description = fields['/vars/policies/' + KEY + '/description']
        self.assertEqual(description['winner']['path'], STACK)
        self.assertEqual(description['winner']['pointer'], '/components/terraform/intune-reference/vars/policies/' + KEY + '/description')
        command = fields['/command']
        self.assertEqual([origin['path'] for origin in command['history']], ['atmos.yaml', STACK])
        self.assertEqual(command['earlier_origins'][0]['path'], 'atmos.yaml')
        only = repository_lineage(self.store, OBJECT, '/vars/policies/' + KEY + '/description')
        self.assertEqual([row['effective_pointer'] for row in only['fields']], ['/vars/policies/' + KEY + '/description'])

    def test_edit_makes_the_intent_stale_and_names_what_changed(self):
        from intune_iac.workbench_repository import intent_freshness
        intent = self.import_intent()
        self.assertEqual(intent_freshness(intent['data'])['status'], 'current')
        self.edit_description('Edited in the repository.')
        fresh = intent_freshness(intent['data'])
        self.assertEqual(fresh['status'], 'stale')
        self.assertEqual(fresh['sources']['changed'], [STACK])
        self.assertEqual((fresh['sources']['added'], fresh['sources']['removed']), ([], []))
        self.assertTrue(fresh['desired_changed'])
        self.assertEqual([(c['field'], c['before'], c['after']) for c in fresh['field_changes']['changes']],
                         [('description', NORMALIZED['desired']['description'], 'Edited in the repository.')])
        (self.repo / 'components/terraform/intune-reference/override.tf').write_text('output "x" {\n  value = 1\n}\n')
        fresh = intent_freshness(intent['data'])
        self.assertEqual(fresh['sources']['added'], ['components/terraform/intune-reference/override.tf'])
        self.assertEqual(fresh['consumer']['status'], 'mismatch')
        shutil.rmtree(self.repo)
        self.assertEqual(intent_freshness(intent['data'])['status'], 'unavailable')

    def test_refresh_records_a_new_current_intent_and_keeps_the_old_one(self):
        from intune_iac.workbench_repository import intent_freshness, refresh_intent
        first = self.import_intent()
        self.edit_description('Edited in the repository.')
        second = refresh_intent(self.store, OBJECT, 'b' * 40)
        self.assertNotEqual(second['artifact_id'], first['artifact_id'])
        self.assertEqual(second['data']['desired']['description'], 'Edited in the repository.')
        self.assertEqual(second['data']['effective_pointer'], first['data']['effective_pointer'])
        self.assertEqual(second['data']['scope'], first['data']['scope'])
        self.assertEqual(intent_freshness(second['data'])['status'], 'current')
        self.assertEqual(len(self.store.artifacts(kind='repository_intent')), 2)

    def test_propose_from_intent_prepares_the_exact_reviewed_change(self):
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        output = self.root / 'operation'
        review = propose_from_intent(self.store.root, self.service.root, OBJECT, output)
        self.assertEqual((review['status'], review['changes']), ('prepared', [OBJECT + ':description_changed']))
        self.assertEqual(review['desired']['description'], 'Edited in the repository.')
        self.assertTrue(Path(str(output) + '.intent-desired.json').is_file())
        context = json.loads(Path(str(output) + '.intent-context.json').read_text())
        self.assertEqual(set(context), {'tenant_id', 'cloud', 'repository_intent_id', 'scope'})

    def test_propose_from_intent_refuses_a_stale_or_mismatched_intent(self):
        from intune_iac.io import AppError
        from intune_iac.workbench_repository import propose_from_intent
        self.import_intent()
        self.edit_description('Edited but not refreshed.')
        with self.assertRaises(AppError) as caught:
            propose_from_intent(self.store.root, self.service.root, OBJECT, self.root / 'stale')
        self.assertEqual(caught.exception.code, 'workbench_repository_stale')
        self.assertFalse((self.root / 'stale').exists())
        self.assertFalse(Path(str(self.root / 'stale') + '.intent-desired.json').exists())

    def test_propose_from_intent_refuses_a_value_outside_the_capability_map(self):
        from intune_iac.io import AppError
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        document = yaml.safe_load((self.repo / STACK).read_text())
        instance = document['components']['terraform']['intune-reference']['vars']['policies'][KEY]['settings']['settings'][0]['settingInstance']
        instance['choiceSettingValue']['value'] = instance['settingDefinitionId'] + '_1'
        (self.repo / STACK).write_text(yaml.safe_dump(document))
        refresh_intent(self.store, OBJECT, 'b' * 40)
        with self.assertRaises(AppError) as caught:
            propose_from_intent(self.store.root, self.service.root, OBJECT, self.root / 'unsupported')
        self.assertEqual(caught.exception.code, 'workbench_desired_capability')
        self.assertFalse((self.root / 'unsupported').exists())

    def test_execute_refuses_when_the_repository_changed_after_the_proposal(self):
        from intune_iac import maintenance
        from intune_iac.io import AppError
        from intune_iac.workbench_repository import propose_from_intent
        self.import_intent()
        review = propose_from_intent(self.store.root, self.service.root, OBJECT, self.root / 'operation')
        self.edit_description('Changed after the proposal was prepared.')
        with self.assertRaises(AppError) as caught:
            maintenance.execute(self.root / 'operation', approve_digest=review['approval_digest'])
        self.assertEqual(caught.exception.code, 'maintenance_repository_stale')
        journal = json.loads((self.root / 'operation/journal.json').read_text())
        self.assertEqual(journal['status'], 'prepared')
        self.assertEqual(self.service.snapshot()['revision'], 1)


if __name__ == '__main__':
    unittest.main()


class CapabilityWordsTests(unittest.TestCase):
    """A capability refusal names the setting and value that the map does not support (journey 28 review S5)."""
    RESOURCE_ADDRESS = RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = RepositoryOwnedChangeTests.setUp
    import_intent = RepositoryOwnedChangeTests.import_intent

    def unsupported(self):
        from intune_iac.workbench_repository import refresh_intent
        self.import_intent()
        document = yaml.safe_load((self.repo / STACK).read_text())
        instance = document['components']['terraform']['intune-reference']['vars']['policies'][KEY]['settings']['settings'][0]['settingInstance']
        instance['choiceSettingValue']['value'] = instance['settingDefinitionId'] + '_1'
        (self.repo / STACK).write_text(yaml.safe_dump(document))
        refresh_intent(self.store, OBJECT, 'b' * 40)
        return instance['settingDefinitionId']

    def test_the_refusal_names_the_setting_and_the_value(self):
        from intune_iac.io import AppError
        from intune_iac.workbench_repository import propose_from_intent
        definition = self.unsupported()
        with self.assertRaises(AppError) as caught:
            propose_from_intent(self.store.root, self.service.root, OBJECT, self.root / 'unsupported')
        message = caught.exception.message
        self.assertIn(definition, message)
        self.assertIn(definition + '_1', message)
        self.assertIn('is not a supported value for this setting', message)

    def test_the_blocked_action_names_them_too(self):
        from intune_iac.workbench import _inspection
        definition = self.unsupported()
        value = _inspection(self.store, OBJECT, attention=True, service_available=True, service_root=self.service.root)
        blocked = {action['kind']: action for action in value['actions']}['propose-from-intent']['blocked']
        self.assertIn(definition + '_1', blocked['message'])

    def test_the_findings_keep_the_old_contract(self):
        from reference.validation import capability_errors, capability_findings
        self.assertEqual(capability_findings([], 'windows10', 'mdm')[0]['reason'], 'no_settings')
        self.assertEqual(capability_errors([], 'windows10', 'mdm'), ['unqualified_setting_capability'])
