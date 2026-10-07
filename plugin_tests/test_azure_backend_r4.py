"""Backend contract acceptance: real private files and independent state facts.

No test is an Azure service observation or permission grant.
"""
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import pickle
import tempfile
import threading
import unittest
from unittest.mock import patch

from intune_iac import azure_backend as ab
from intune_iac import identity_binding as ib
from intune_iac.io import AppError
from plugin_tests.test_identity_binding_v5 import config, RecordedServices, STATE


class AzureBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.spec = ab.AzureBackendSpec(config().backend_identity, config().backend,
                                       'coordination/selected-policy.lock')
        self.adapter = ab.AzureBackendAdapter(self.spec)

    def assert_code(self, expected, function):
        with self.assertRaises(AppError) as error:
            function()
        self.assertEqual(error.exception.code, expected)

    def state(self, *, serial=12, lineage=None, resource_id='policy-one', spacing=False):
        value = {'version': 4, 'lineage': lineage or config().backend.state_lineage,
                 'serial': serial, 'resources': [{'type': 'independent_resource',
                                                'instances': [{'attributes': {'id': resource_id}}]}]}
        return json.dumps(value, indent=2 if spacing else None).encode()

    def metadata(self):
        return {'version': 3, 'serial': 1, 'lineage': config().backend.state_lineage,
                'backend': {'type': 'azurerm', 'config': self.adapter.configuration(), 'hash': 42}}

    def test_configuration_has_exact_target_and_disables_other_identity_routes(self):
        actual = self.adapter.configuration()
        self.assertEqual(actual['storage_account_name'], 'recordedstate')
        self.assertEqual(actual['resource_group_name'], 'state-rg')
        self.assertEqual(actual['container_name'], 'tfstate')
        self.assertEqual(actual['key'], 'intune.tfstate')
        self.assertEqual(actual['tenant_id'], '11111111-1111-1111-1111-111111111111')
        self.assertEqual(actual['client_id'], '44444444-4444-4444-4444-444444444444')
        self.assertTrue(actual['use_azuread_auth'])
        for name in ('use_cli', 'use_msi', 'use_oidc', 'use_aks_workload_identity', 'snapshot'):
            self.assertIs(actual[name], False)
        self.assertNotIn('client_secret', actual)
        actual['key'] = 'caller-mutation'
        self.assertEqual(self.adapter.configuration()['key'], 'intune.tfstate')

    def test_wrong_subscription_endpoint_workspace_and_identity_are_rejected(self):
        variants = [replace(config().backend, subscription_id='99999999-9999-9999-9999-999999999999'),
                    replace(config().backend, blob_endpoint='https://attacker.invalid'),
                    replace(config().backend, workspace='production'),
                    replace(config().backend, state_serial=True)]
        for backend in variants:
            with self.subTest(backend=backend):
                self.assert_code('azure_backend_spec_invalid', lambda: ab.AzureBackendSpec(
                    config().backend_identity, backend, 'coordination/selected-policy.lock'))
        self.assert_code('azure_backend_spec_invalid', lambda: ab.AzureBackendSpec(
            replace(config().backend_identity, auth_method='azure_cli'), config().backend, 'coordination/a.lock'))

    def test_coordination_blob_must_be_separate_and_paths_cannot_escape(self):
        for key in ('intune.tfstate', '../outside', '/absolute', 'a//b', 'a/%2f/b', 'a?comp=lease', '${x}', 'a\\b'):
            with self.subTest(key=key):
                self.assert_code('azure_backend_spec_invalid', lambda: ab.AzureBackendSpec(
                    config().backend_identity, config().backend, key))
        receipt = self.adapter.binding()
        self.assertFalse(receipt['graph_fencing'])
        self.assertEqual(receipt['native_state_lock_owner'], 'opentofu_azurerm_backend')
        self.assertNotEqual(receipt['state_blob'], receipt['coordination_blob'])

    def test_metadata_checks_native_type_target_flags_and_rejects_secret_material(self):
        result = self.adapter.verify_metadata(self.metadata(), workspace='default')
        self.assertEqual(result['status'], 'matched')
        for field, value in [('key', 'other.tfstate'), ('use_cli', True),
                             ('client_secret', 'synthetic-secret-canary'),
                             ('access_key', 'synthetic-key'), ('endpoint', 'https://foreign.invalid'),
                             ('new_unreviewed_field', False)]:
            bad = self.metadata(); bad['backend']['config'][field] = value
            self.assert_code('azure_backend_metadata_mismatch', lambda: self.adapter.verify_metadata(bad, workspace='default'))
        bad = self.metadata(); bad['backend']['type'] = 'local'
        self.assert_code('azure_backend_metadata_mismatch', lambda: self.adapter.verify_metadata(bad, workspace='default'))
        self.assert_code('azure_backend_metadata_mismatch', lambda: self.adapter.verify_metadata(self.metadata(), workspace='other'))

    def test_optional_empty_metadata_is_accepted_but_false_is_not_an_empty_secret(self):
        value = self.metadata()
        value['backend']['config'].update(client_secret=None, access_key='', oidc_token=None)
        self.adapter.verify_metadata(value, workspace='default')
        value['backend']['config']['client_secret'] = False
        self.assert_code('azure_backend_metadata_mismatch', lambda: self.adapter.verify_metadata(value, workspace='default'))

    def test_missing_metadata_does_not_become_local_backend(self):
        for value in ({}, {'backend': None}, {'version': 3, 'backend': {'type': 'azurerm'}}, []):
            self.assert_code('azure_backend_metadata_mismatch', lambda: self.adapter.verify_metadata(value, workspace='default'))

    def test_state_precondition_binds_exact_bytes_etag_lineage_and_serial(self):
        revision = ab.StateRevision.observe(STATE, etag='"etag-one"')
        self.adapter.verify_precondition(revision, expected_etag='"etag-one"')
        self.assert_code('azure_backend_state_changed', lambda: self.adapter.verify_precondition(revision, expected_etag='"etag-two"'))
        changed = ab.StateRevision.observe(self.state(serial=13), etag='"etag-one"')
        self.assert_code('azure_backend_state_changed', lambda: self.adapter.verify_precondition(changed, expected_etag='"etag-one"'))

    def test_state_revision_keeps_raw_bytes_distinct_from_structured_state(self):
        first = ab.StateRevision.observe(self.state(), etag='"one"')
        second = ab.StateRevision.observe(self.state(spacing=True), etag='"two"')
        self.assertNotEqual(first.sha256, second.sha256)
        self.assertEqual(first.semantic_sha256, second.semantic_sha256)
        self.assertEqual(first.sha256, hashlib.sha256(self.state()).hexdigest())
        self.assert_code('azure_backend_state_same_serial_changed', lambda: ab.verify_transition(first, second))

    def test_authorized_state_advance_is_separate_from_identity_or_execution_proof(self):
        before = ab.StateRevision.observe(self.state(), etag='"one"')
        after = ab.StateRevision.observe(self.state(serial=13), etag='"two"')
        result = ab.verify_transition(before, after)
        self.assertEqual(result['state_change'], 'advanced')
        self.assertFalse(result['execution_confirmed'])
        self.assertFalse(result['service_convergence_confirmed'])
        self.assertEqual(result['before']['serial'], 12)
        self.assertEqual(result['after']['serial'], 13)
        self.assertEqual(ab.verify_transition(before, before)['state_change'], 'unchanged')

    def test_wrong_lineage_rollback_and_reused_etag_are_rejected(self):
        before = ab.StateRevision.observe(self.state(), etag='"one"')
        for kwargs, etag, code in [({'serial': 11}, '"two"', 'azure_backend_state_serial_regressed'),
                ({'serial': 13, 'lineage': '99999999-9999-9999-9999-999999999999'}, '"two"', 'azure_backend_state_lineage_changed'),
                ({'serial': 13}, '"one"', 'azure_backend_state_etag_reused')]:
            after = ab.StateRevision.observe(self.state(**kwargs), etag=etag)
            self.assert_code(code, lambda: ab.verify_transition(before, after))

    def test_missing_partial_duplicate_weak_etag_and_invalid_state_are_rejected(self):
        for raw in (b'', b'{', b'{"version":4,"version":4}', b'null', b'[]',
                    self.state().replace(b'"serial": 12', b'"serial": true')):
            self.assert_code('azure_backend_state_invalid', lambda: ab.StateRevision.observe(raw, etag='"one"'))
        for etag in ('W/"one"', 'one', '"one\r\nInjected: yes"', ''):
            self.assert_code('azure_backend_state_invalid', lambda: ab.StateRevision.observe(self.state(), etag=etag))

    def test_private_publication_is_new_only_exact_and_secret_free(self):
        destination = self.root / 'admitted backend'
        receipt = self.adapter.publish(destination)
        self.assertEqual(set(p.name for p in destination.iterdir()), {'backend.tf.json', 'backend-binding.json', 'backend-manifest.json'})
        self.assertEqual(destination.stat().st_mode & 0o777, 0o700)
        for path in destination.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.adapter.verify_published(destination), receipt)
        self.assert_code('azure_backend_output_exists', lambda: self.adapter.publish(destination))
        self.assertEqual(self.adapter.verify_published(destination), receipt)

    def test_published_substitution_extra_file_hardlink_and_symlink_are_rejected(self):
        for attack in ('replace', 'extra', 'hardlink', 'symlink'):
            with self.subTest(attack=attack):
                destination = self.root / attack
                self.adapter.publish(destination)
                path = destination / 'backend.tf.json'
                if attack == 'replace': path.write_text('{}')
                elif attack == 'extra': (destination / 'unexpected.tmp').write_text('preserve me')
                elif attack == 'hardlink': os.link(path, self.root / 'outside-link')
                else:
                    path.unlink(); path.symlink_to(self.root / 'absent-target')
                self.assert_code('azure_backend_artifact_mismatch', lambda: self.adapter.verify_published(destination))
                if attack == 'extra': self.assertTrue((destination / 'unexpected.tmp').exists())

    def test_publication_rejects_unsafe_parent_and_preserves_partial_on_failure(self):
        public = self.root / 'public'; public.mkdir(mode=0o755); public.chmod(0o755)
        self.assert_code('azure_backend_private_path_required', lambda: self.adapter.publish(public / 'output'))
        alias = self.root / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        self.assert_code('azure_backend_private_path_required', lambda: self.adapter.publish(alias / 'output'))
        destination = self.root / 'partial'
        real_fsync = os.fsync
        calls = []
        def fail_second(fd):
            calls.append(fd)
            if len(calls) == 2: raise OSError('injected disk failure')
            return real_fsync(fd)
        with patch('intune_iac.azure_backend.os.fsync', side_effect=fail_second):
            self.assert_code('azure_backend_publication_incomplete', lambda: self.adapter.publish(destination))
        self.assertTrue(destination.exists())
        self.assertTrue(any(destination.iterdir()))
        self.assert_code('azure_backend_artifact_mismatch', lambda: self.adapter.verify_published(destination))

    def test_concurrent_publication_has_one_winner_without_overwrite(self):
        barrier = threading.Barrier(2); outcomes = []
        def run():
            barrier.wait()
            try: outcomes.append(self.adapter.publish(self.root / 'concurrent')['status'])
            except AppError as error: outcomes.append(error.code)
        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(3)
        self.assertCountEqual(outcomes, ['published', 'azure_backend_output_exists'])
        self.adapter.verify_published(self.root / 'concurrent')

    def binding(self):
        provider = ib.ClientSecretHandle('synthetic-provider-secret')
        backend = ib.ClientSecretHandle('synthetic-backend-secret')
        self.addCleanup(provider.close); self.addCleanup(backend.close)
        binding = ib.bind_laboratory(config(), provider_credential=provider,
                                    backend_credential=backend, transport=RecordedServices())
        return binding, provider, backend

    def test_credentials_use_exact_bound_backend_handle_and_no_ambient_fallback(self):
        binding, provider, backend = self.binding()
        with patch.dict(os.environ, {'ARM_CLIENT_SECRET': 'ambient-canary', 'M365_CLIENT_SECRET': 'ambient-provider',
                                    'ARM_ACCESS_KEY': 'ambient-key', 'ARM_USE_MSI': 'true'}):
            with self.adapter.credential_environment(binding, backend) as credentials:
                value = credentials.environment()
                self.assertEqual(value['ARM_CLIENT_SECRET'], 'synthetic-backend-secret')
                self.assertEqual(value['ARM_CLIENT_ID'], '44444444-4444-4444-4444-444444444444')
                self.assertNotIn('M365_CLIENT_SECRET', value)
                self.assertNotIn('ARM_ACCESS_KEY', value)
                self.assertEqual(value['ARM_USE_CLI'], 'false')
                self.assertEqual(value['ARM_USE_AKS_WORKLOAD_IDENTITY'], 'false')
                self.assertNotIn('synthetic-backend-secret', repr(credentials))
                with self.assertRaises(TypeError): pickle.dumps(credentials)
        self.assert_code('azure_backend_credentials_closed', credentials.environment)
        self.assert_code('identity_backend_handle_mismatch', lambda: self.adapter.credential_environment(binding, provider))
        replacement = ib.ClientSecretHandle('synthetic-backend-secret'); self.addCleanup(replacement.close)
        self.assert_code('identity_backend_handle_mismatch', lambda: self.adapter.credential_environment(binding, replacement))

    def test_closed_or_changed_binding_cannot_supply_credentials(self):
        binding, provider, backend = self.binding()
        changed = ab.AzureBackendAdapter(ab.AzureBackendSpec(config().backend_identity,
            replace(config().backend, key='different.tfstate'), 'coordination/selected-policy.lock'))
        self.assert_code('azure_backend_identity_mismatch', lambda: changed.credential_environment(binding, backend))
        credentials = self.adapter.credential_environment(binding, backend)
        backend.close()
        self.assert_code('identity_credential_unavailable', credentials.environment)
        self.assert_code('azure_backend_identity_required', lambda: self.adapter.credential_environment({}, backend))

    def test_native_commands_are_closed_and_never_disable_lock_or_replan_apply(self):
        self.assertEqual(self.adapter.native_command('init'),
            ('init', '-input=false', '-no-color', '-get=false', '-lockfile=readonly', '-lock-timeout=0s'))
        self.assertEqual(self.adapter.native_command('state'), ('state', 'pull'))
        self.assertEqual(self.adapter.native_command('workspace'), ('workspace', 'show'))
        self.assertEqual(self.adapter.native_command('apply', plan_descriptor=9),
            ('apply', '-input=false', '-no-color', '-lock-timeout=0s', '/proc/self/fd/9'))
        for operation in ('destroy', 'force-unlock', 'state-push', 'init -migrate-state'):
            self.assert_code('azure_backend_command_not_admitted', lambda: self.adapter.native_command(operation))
        for descriptor in (None, True, 0, -1, '9'):
            self.assert_code('azure_backend_sealed_plan_required', lambda: self.adapter.native_command('apply', plan_descriptor=descriptor))


if __name__ == '__main__':
    unittest.main()


class NativeStateWriteTests(unittest.TestCase):
    def setUp(self):
        self.before = {'version': 4, 'terraform_version': '1.13.1', 'serial': 8,
            'lineage': '11111111-1111-1111-1111-111111111111', 'outputs': {}, 'check_results': None,
            'resources': [{'mode': 'managed', 'type': 'catalog_policy', 'name': 'selected',
                'provider': 'provider["registry.fixture.invalid/org/provider"]', 'instances': [{'schema_version': 0,
                    'attributes': {'id': 'immutable-policy', 'settings': ['old'], 'unknown_field': None},
                    'sensitive_attributes': [], 'private': 'retained-exact', 'dependencies': []}]}]}
        attrs = copy.deepcopy(self.before['resources'][0]['instances'][0]['attributes']); attrs['settings'] = ['new']
        self.plan = {'format_version': '1.2', 'terraform_version': '1.13.1', 'errored': False,
            'resource_changes': [{'address': 'catalog_policy.selected', 'mode': 'managed', 'change': {
                'actions': ['update'], 'before': copy.deepcopy(self.before['resources'][0]['instances'][0]['attributes']),
                'after': attrs, 'after_unknown': {}}}],
            'planned_values': {'outputs': {}, 'root_module': {'resources': [
                {'address': 'catalog_policy.selected', 'schema_version': 0, 'values': copy.deepcopy(attrs)}]}}, 'output_changes': {}}
        self.expected = copy.deepcopy(self.before); self.expected['serial'] = 9
        self.expected['resources'][0]['instances'][0]['attributes'] = copy.deepcopy(attrs)

    def contract(self):
        return ab.NativeStateWriteContract(baseline_raw=json.dumps(self.before).encode(),
            plan_json_raw=json.dumps(self.plan).encode(), saved_plan_sha256='a' * 64, schema_versions={'catalog_policy': 0})

    def test_exact_projection_preserves_metadata_and_admits_native_whitespace(self):
        raw = json.dumps(self.expected, indent=2).encode(); result = self.contract().admit(raw)
        self.assertEqual(result['body_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertFalse(result['execution_authorized']); self.assertFalse(result['service_convergence_confirmed'])

    def test_id_scope_serial_lineage_and_private_changes_fail(self):
        for field, value in [('serial', 10), ('lineage', '22222222-2222-2222-2222-222222222222')]:
            candidate = copy.deepcopy(self.expected); candidate[field] = value
            with self.assertRaises(AppError): self.contract().admit(json.dumps(candidate).encode())
        for field, value in [('private', 'new-private'), ('dependencies', ['other_policy.unapproved'])]:
            candidate = copy.deepcopy(self.expected); candidate['resources'][0]['instances'][0][field] = value
            with self.assertRaises(AppError): self.contract().admit(json.dumps(candidate).encode())
        candidate = copy.deepcopy(self.expected); candidate['resources'][0]['instances'][0]['attributes']['id'] = 'foreign-policy'
        with self.assertRaises(AppError): self.contract().admit(json.dumps(candidate).encode())

    def test_unknown_computed_value_or_dropped_unknown_field_is_not_ignored(self):
        self.plan['resource_changes'][0]['change']['after_unknown'] = {'unknown_field': True}
        with self.assertRaises(AppError): self.contract()
        self.plan['resource_changes'][0]['change']['after_unknown'] = {}
        self.plan['resource_changes'][0]['change']['after'].pop('unknown_field')
        with self.assertRaises(AppError): self.contract()

    def test_refresh_drift_import_move_create_and_delete_require_new_profile(self):
        for key, value in [('resource_drift', [{}]), ('deferred_changes', [{}]), ('complete', False)]:
            self.plan[key] = value
            with self.assertRaises(AppError): self.contract()
            del self.plan[key]
        change = self.plan['resource_changes'][0]
        for action in (['create'], ['delete'], ['delete', 'create']):
            change['change']['actions'] = action
            with self.assertRaises(AppError): self.contract()
        change['change']['actions'] = ['update']; change['previous_address'] = 'catalog_policy.previous'
        with self.assertRaises(AppError): self.contract()

    def test_extra_resource_or_changed_attributes_fail(self):
        candidate = copy.deepcopy(self.expected); candidate['resources'].append(copy.deepcopy(candidate['resources'][0]))
        with self.assertRaises(AppError): self.contract().admit(json.dumps(candidate).encode())
        candidate = copy.deepcopy(self.expected); candidate['resources'][0]['instances'][0]['attributes']['settings'] = ['new', 'unauthorized']
        with self.assertRaises(AppError): self.contract().admit(json.dumps(candidate).encode())

    def test_mismatched_plan_values_beforestate_or_schema_version_fail(self):
        self.plan['planned_values']['root_module']['resources'][0]['values']['settings'] = ['different']
        with self.assertRaises(AppError): self.contract()
        self.plan['planned_values']['root_module']['resources'][0]['values']['settings'] = ['new']
        self.before['resources'][0]['instances'][0]['schema_version'] = 1
        with self.assertRaises(AppError): self.contract()
