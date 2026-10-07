"""Closed native worker preparation; no live service or device assertions."""
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import worker_provider as wp, azure_backend as ab, provider_execution as pe
from intune_iac.io import AppError
from plugin_tests.test_identity_binding_v5 import config, RecordedServices
from plugin_tests.test_provider_execution_v5 import FIXTURE, OBJECT_ID

LOCK = b'''provider "registry.terraform.io/deploymenttheory/microsoft365" {
  version = "1.0.0"
  constraints = "1.0.0"
  hashes = ["h1:c3ludGhldGlj",]
}
'''


def adapter():
    cfg = config()
    return wp.WorkerProviderAdapter(wp.ProviderSpec(cfg.provider,
        ab.AzureBackendSpec(cfg.backend_identity, cfg.backend, 'coordination/selected.lock'),
        OBJECT_ID, '2' * 40, '3' * 64, '4' * 64, FIXTURE), lockfile=LOCK)


class WorkerProviderTests(unittest.TestCase):
    def assert_code(self, code, action):
        with self.assertRaises(AppError) as caught: action()
        self.assertEqual(caught.exception.code, code)

    def test_typed_backend_source_principal_and_toolchain_binding(self):
        value = adapter(); actual = value.binding()
        self.assertEqual(actual['provider_identity']['client_id'], '22222222-2222-2222-2222-222222222222')
        self.assertEqual(actual['backend']['native_state_lock_owner'], 'opentofu_azurerm_backend')
        self.assertEqual(actual['pins']['engine_version'], '1.13.1')
        self.assertEqual(actual['pins']['atmos_sha256'], 'f3b5b42e897a2778678cc1231e7a4e2476773bc61ea2af225586dc4e96408802')
        self.assertFalse(actual['execution_authorized']); self.assertFalse(actual['platform_qualified'])

    def test_wrong_tenant_shared_principal_and_injected_source_rejected(self):
        good = adapter().spec
        for spec in [dict(identity=replace(good.identity, tenant_id='99999999-9999-9999-9999-999999999999')),
                     dict(identity=replace(good.identity, client_id=good.backend.identity.client_id)),
                     dict(source_revision='$(touch /tmp/never)'), dict(object_id='../../foreign')]:
            with self.subTest(spec=spec): self.assert_code('worker_provider_spec_invalid', lambda: replace(good, **spec))

    def test_generated_project_has_exact_backend_one_resource_and_no_secret(self):
        value = adapter(); files = value.source_files()
        doc = json.loads(files['project/' + wp.PROJECT + '/main.tf.json'])
        self.assertEqual(list(doc['resource']), [pe.RESOURCE])
        self.assertEqual(list(doc['resource'][pe.RESOURCE]), ['selected'])
        backend = doc['terraform']['backend']['azurerm']
        self.assertEqual(backend['key'], 'intune.tfstate'); self.assertFalse(backend['use_cli'])
        self.assertNotIn('client_secret', doc['provider']['microsoft365']['entra_id_options'])
        self.assertNotIn('client_secret', backend)
        self.assertIn(b'command: /tools/tofu', files['project/atmos.yaml'])
        self.assertIn(b'terraform_workspace: default', files['project/stacks/worker.yaml'])
        self.assertEqual(doc['provider']['microsoft365']['client_options']['enable_redirect'], False)

    def test_exact_saved_plan_command_cannot_be_replaced_with_automatic_apply(self):
        command = wp.native_command('apply')
        self.assertEqual(command[:5], ('/tools/atmos', 'terraform', 'apply', 'intune-policy', '-s'))
        self.assertIn('--from-plan', command)
        self.assertEqual(command[command.index('--planfile') + 1], '/control/approved.plan')
        self.assertNotIn('-auto-approve', command)
        self.assertFalse(any(token.startswith('--from-plan=') for token in command))
        for op in ('destroy', 'import', 'plan -target=foreign', 'force-unlock', 'state push'):
            self.assert_code('worker_provider_operation_unsupported', lambda: wp.native_command(op))

    def test_plan_commands_are_distinct_and_show_omits_unsupported_init_flag(self):
        self.assertIn('-refresh-only', wp.native_command('refresh'))
        self.assertNotIn('-refresh-only', wp.native_command('ordinary'))
        self.assertIn('-out=second.plan', wp.native_command('second'))
        self.assertNotIn('--init-mode=never', wp.native_command('show'))

    def test_fresh_apply_initializes_only_then_consumes_exact_plan(self):
        payload = adapter().control_files('apply', saved_plan=b'closed-native-plan')
        script = payload['worker.sh'].decode()
        commands = [line for line in script.splitlines() if line.startswith('env -i ')]
        self.assertEqual(len(commands), 2)
        self.assertIn('/tools/atmos terraform init ', commands[0])
        self.assertIn('-lockfile=readonly', commands[0])
        self.assertIn('/tools/atmos terraform apply ', commands[1])
        self.assertIn('--from-plan --planfile /control/approved.plan', commands[1])
        self.assertNotIn('/tools/atmos terraform plan ', script)
        self.assertEqual(json.loads(payload['operation.json'])['commands'],
                         [list(wp.native_command('init')), list(wp.native_command('apply'))])

    def test_plan_binary_exact_bytes_hash_and_no_caller_environment(self):
        with patch.dict(os.environ, {'M365_CLIENT_SECRET': 'real-canary-never-in-payload', 'ATMOS_BASE_PATH': '/wrong'}):
            files = adapter().control_files('apply', saved_plan=b'PK\x00\r\nplan\xff')
        self.assertEqual(files['approved.plan'], b'PK\x00\r\nplan\xff')
        meta = json.loads(files['operation.json'])
        self.assertEqual(meta['saved_plan_sha256'], hashlib.sha256(files['approved.plan']).hexdigest())
        self.assertIn(b'env -i ', files['worker.sh'])
        self.assertIn(b'trap cleanup EXIT', files['worker.sh'])
        self.assertIn(b'/job/relay.ready', files['worker.sh'])
        self.assertIn(meta['saved_plan_sha256'].encode(), files['worker.sh'])
        self.assertNotIn(b'real-canary-never-in-payload', files['worker.sh'])
        self.assert_code('worker_provider_saved_plan_required', lambda: adapter().control_files('apply'))
        self.assert_code('worker_provider_unexpected_plan', lambda: adapter().control_files('ordinary', saved_plan=b'wrong'))

    def test_dictionary_secret_injection_is_not_a_credential_capability(self):
        self.assert_code('worker_provider_credential_capability', lambda: adapter().control_files('init', credentials={'M365_CLIENT_SECRET': 'canary'}))

    def test_lock_scope_rejects_additional_provider_hooks_and_invalid_utf8(self):
        for raw in [LOCK + b'provider "other" {}', LOCK.replace(b'1.0.0', b'1.0.1'), b'\xff',
                    LOCK.replace(b'c3ludGhldGlj', b'${file("/secret")}')]:
            self.assert_code('worker_provider_lock_invalid', lambda: wp.WorkerProviderAdapter(adapter().spec, lockfile=raw))

    def test_external_mutation_cannot_change_admitted_source(self):
        value = adapter(); value.spec.desired['name'] = 'substituted'
        for operation in (value.binding, value.source_files, lambda: value.control_files('init')):
            self.assert_code('worker_provider_input_changed', operation)

    def test_lock_substitution_after_admission_is_rejected(self):
        value = adapter(); value.lockfile = value.lockfile.replace(b'c3ludGhldGlj', b'b3RoZXI=')
        self.assert_code('worker_provider_input_changed', value.binding)

    def test_same_client_label_does_not_override_authenticated_principal_or_state(self):
        from intune_iac import worker_broker as wb, identity_binding as ib
        provider = ib.ClientSecretHandle('synthetic-provider-secret')
        backend = ib.ClientSecretHandle('synthetic-backend-secret')
        bound = ib.bind_laboratory(config(), provider_credential=provider, backend_credential=backend, transport=RecordedServices())
        credentials = wb.broker_credentials(binding=bound, backend_credential=backend, execution_binding_sha256='a' * 64)
        original = adapter()
        for spec in [replace(original.spec, identity=replace(original.spec.identity, principal_object_id='99999999-9999-9999-9999-999999999999')),
                     replace(original.spec, backend=replace(original.spec.backend, backend=replace(original.spec.backend.backend, state_serial=13)))]:
            value = wp.WorkerProviderAdapter(spec, lockfile=LOCK)
            self.assert_code('worker_provider_credential_capability', lambda: value.control_files('init', credentials=credentials))

    def test_private_exact_publication_preserves_collision_and_literal_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'new'; raw = b'PK\x00\r\n\xff'
            receipt = wp.publish_files(root, {'approved.plan': raw, 'worker.sh': b'closed'})
            self.assertEqual((root / 'approved.plan').read_bytes(), raw)
            self.assertEqual(receipt['files']['approved.plan']['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual((root / 'approved.plan').stat().st_mode & 0o777, 0o600)
            self.assert_code('worker_provider_output_exists', lambda: wp.publish_files(root, {'unexpected': b'no'}))
            self.assertEqual((root / 'approved.plan').read_bytes(), raw)
            self.assert_code('worker_provider_artifact_invalid', lambda: wp.publish_files(Path(temp) / 'bad', {'../escape': b'no'}))

    def test_symlink_output_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'alias').symlink_to(root, target_is_directory=True)
            self.assert_code('worker_provider_unsafe_path', lambda: wp.publish_files(root / 'alias' / 'new', {'closed': b'yes'}))

    def test_placeholder_capability_contains_no_real_client_secret(self):
        from intune_iac import worker_broker as wb, identity_binding as ib
        provider = ib.ClientSecretHandle('synthetic-provider-secret')
        backend = ib.ClientSecretHandle('synthetic-backend-secret')
        bound = ib.bind_laboratory(config(), provider_credential=provider, backend_credential=backend, transport=RecordedServices())
        credentials = wb.broker_credentials(binding=bound, backend_credential=backend, execution_binding_sha256='a' * 64)
        files = adapter().control_files('init', credentials=credentials)
        self.assertIn(b'intune-worker-placeholder-' + b'a' * 64 + b'-provider', files['worker.sh'])
        self.assertNotIn(b'synthetic-provider-secret', files['worker.sh'])
        self.assertNotIn(b'synthetic-backend-secret', files['worker.sh'])
        credentials.close()
        with self.assertRaises(AppError): adapter().control_files('init', credentials=credentials)


if __name__ == '__main__': unittest.main()
