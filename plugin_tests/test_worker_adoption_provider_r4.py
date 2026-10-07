"""Closed adoption controls; no real service/host assertion from these tests."""
import json
import os
import subprocess
import unittest
from unittest.mock import patch

from intune_iac import worker_adoption_provider as adoption
from intune_iac import worker_provider, worker_broker, identity_binding
from intune_iac.io import AppError
from plugin_tests.test_worker_provider_r4 import adapter
from plugin_tests.test_identity_binding_v5 import config, RecordedServices


class AdoptionProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = identity_binding.ClientSecretHandle('synthetic-provider-secret')
        self.backend = identity_binding.ClientSecretHandle('synthetic-backend-secret')
        self.binding = identity_binding.bind_laboratory(config(), provider_credential=self.provider,
            backend_credential=self.backend, transport=RecordedServices())
        self.credentials = worker_broker.broker_credentials(binding=self.binding,
            backend_credential=self.backend, execution_binding_sha256='a' * 64)
        self.value = adoption.NativeAdoptionProviderAdapter(adapter())
        self.addCleanup(self.provider.close); self.addCleanup(self.backend.close)
        self.addCleanup(self.credentials.close)

    def rejected(self, code, action):
        with self.assertRaises(AppError) as caught: action()
        self.assertEqual(caught.exception.code, code)

    def test_import_exact_observed_atmos_route_and_one_init(self):
        files = self.value.control_files('import', credentials=self.credentials)
        commands = json.loads(files['operation.json'])['commands']
        self.assertEqual(commands[1], ['/tools/atmos', 'terraform', 'import', 'intune-policy',
            '-s', 'worker', 'microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json.selected',
            self.value.provider.spec.object_id, '-input=false', '-no-color',
            '--process-functions=false', '--process-templates=false'])
        self.assertEqual(len(commands), 2); self.assertEqual(commands[0], list(worker_provider.native_command('init')))
        self.assertNotIn(b'terraform apply ', files['worker.sh']); self.assertNotIn(b'terraform plan ', files['worker.sh'])
        self.assertNotIn('approved.plan', files)
        subprocess.run(['/bin/sh', '-n'], input=files['worker.sh'], check=True, capture_output=True)

    def test_ordinary_import_is_still_rejected(self):
        self.rejected('worker_provider_operation_unsupported', lambda: worker_provider.native_command('import'))
        for value in ['apply', 'destroy', 'import /other', 'refresh', None, {}, []]:
            self.rejected('adoption_provider_operation_unsupported', lambda value=value:self.value.control_files(value,credentials=self.credentials))

    def test_noncanonical_zero_and_shell_object_ids_denied(self):
        for value in ['00000000-0000-0000-0000-000000000000', '$(touch /tmp/never)',
                      '../policy', '33333333-3333-4333-8333-333333333333\n', None]:
            self.rejected('adoption_provider_object_invalid', lambda value=value:adoption.import_command(value))

    def test_plan_keeps_exit2_and_json_without_apply_or_replacement(self):
        files = self.value.control_files('first-plan', credentials=self.credentials)
        commands = json.loads(files['operation.json'])['commands']
        self.assertEqual(len(commands), 3)
        self.assertIn('-out=adoption-initial.plan',commands[1]);self.assertIn('-detailed-exitcode',commands[1])
        self.assertNotIn('-refresh-only',commands[1]);self.assertNotIn('--init-mode=never',commands[2])
        self.assertIn(b'case "$adoption_plan_code" in 0|2)',files['worker.sh'])
        self.assertIn(b'exit "$adoption_plan_code"',files['worker.sh']);self.assertNotIn(b'terraform apply ',files['worker.sh'])
        self.assertFalse(json.loads(files['operation.json'])['no_change_claimed'])
        subprocess.run(['/bin/sh','-n'],input=files['worker.sh'],check=True,capture_output=True)

    def test_credentials_and_environment_not_caller_strings(self):
        for value in [None, {}, {'client_secret':'canary'}]:
            self.rejected('adoption_provider_credentials_required',lambda value=value:self.value.control_files('import',credentials=value))
        with patch.dict(os.environ,{'M365_CLIENT_SECRET':'ambient-real-canary'}):
            files=self.value.control_files('import',credentials=self.credentials)
        self.assertNotIn(b'ambient-real-canary',files['worker.sh']);self.assertNotIn(b'synthetic-provider-secret',files['worker.sh'])
        self.assertIn(b'intune-worker-placeholder-'+b'a'*64+b'-provider',files['worker.sh'])
        self.assertIn(b'trap cleanup EXIT',files['worker.sh']);self.assertIn(b'/job/relay.ready',files['worker.sh'])

    def test_changed_source_and_foreign_adapter_denied(self):
        self.rejected('adoption_provider_adapter_required',lambda:adoption.NativeAdoptionProviderAdapter({}))
        self.value.provider.spec.desired['name']='changed'
        self.rejected('worker_provider_input_changed',self.value.binding)
        self.rejected('worker_provider_input_changed',lambda:self.value.control_files('import',credentials=self.credentials))

    def test_binding_preserves_provider_identity_backend_and_coverage_limits(self):
        value=self.value.binding();self.assertEqual(value['backend'],self.value.provider.binding()['backend']);self.assertEqual(value['source_sha256'],self.value.provider.binding()['source_sha256']);self.assertEqual(value['adoption_operation'],'native_state_only_import')
        self.assertEqual(value['tenant_id'],config().provider.tenant_id)
        self.assertFalse(value['execution_authorized']);self.assertFalse(value['platform_qualified'])
        files=self.value.source_files();self.assertEqual(json.loads(files['adoption-provider-binding.json']),value)
        self.assertEqual(files['project/atmos.yaml'],self.value.provider.source_files()['project/atmos.yaml'])


if __name__ == '__main__':unittest.main()
