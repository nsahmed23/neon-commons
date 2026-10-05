"""Modeled lifecycle failures plus native process isolation; no tenant calls."""
import copy
import json
import os
import socket
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import zipfile

from intune_iac import provider_execution as pe
from intune_iac.io import AppError, canonical, digest, load_json, write_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'labs/provider-contract/synthetic-rpc/main.tf.json.txt').read_text())['resource'][pe.RESOURCE]['fixture']
OBJECT_ID = json.loads((ROOT / 'labs/provider-contract/synthetic-rpc/fixture.json').read_text())['id']
SCHEMA = {'version': 0, 'block': {'attributes': {}}}


def values(configuration):
    return dict(copy.deepcopy(configuration), id=OBJECT_ID, created_date_time='2026-01-01T00:00:00Z',
                last_modified_date_time='2026-01-01T00:00:00Z', is_assigned=True, settings_count=1,
                settings_catalog_template_type=None, timeouts=None)


def raw_state(configuration, serial=1, lineage='12345678-1234-4234-8234-123456789012'):
    return {'version': 4, 'terraform_version': '1.10.0', 'serial': serial, 'lineage': lineage, 'outputs': {},
            'resources': [{'mode': 'managed', 'type': pe.RESOURCE, 'name': 'selected',
                           'provider': 'provider["' + pe.SOURCE + '"]',
                           'instances': [{'schema_version': 0, 'attributes': values(configuration), 'sensitive_attributes': []}]}]}


def shown(configuration):
    return {'format_version': '1.0', 'terraform_version': '1.10.0', 'values': {'root_module': {'resources': [
        {'address': pe.ADDRESS, 'mode': 'managed', 'type': pe.RESOURCE, 'name': 'selected',
         'provider_name': pe.SOURCE, 'schema_version': 0, 'values': values(configuration), 'sensitive_values': {}}]}}}


def plan(before, after, *, refresh=False):
    document = {'format_version': '1.2', 'terraform_version': '1.10.0', 'errored': False,
                'prior_state': shown(before), 'planned_values': {'root_module': {}}, 'configuration': {}}
    if not refresh:
        document['planned_values'] = shown(after)['values']
        document['resource_changes'] = [{'address': pe.ADDRESS, 'mode': 'managed', 'type': pe.RESOURCE,
            'name': 'selected', 'provider_name': pe.SOURCE,
            'change': {'actions': ['no-op' if before == after else 'update'], 'before': values(before), 'after': values(after),
                       'after_unknown': {}, 'before_sensitive': {}, 'after_sensitive': {}}}]
    return document


class ModeledExecutor(pe.ProviderExecutor):
    """Test double only. These observations are explicitly not native evidence."""
    def __init__(self, root):
        super().__init__(root)
        self.remote = copy.deepcopy(self.manifest['initial']); self.commands = []; self.documents = {}
        self.failure = None

    def _run(self, name, *, plan_sha=None):
        self._integrity(); self.commands.append(name)
        if name == 'init': (self.work / '.terraform.lock.hcl').write_text('fixed offline test lock')
        elif name == 'schema': return {'provider_schemas': {pe.SOURCE: {'resource_schemas': {pe.RESOURCE: SCHEMA}}}}
        elif name == 'validate': return {'valid': True}
        elif name == 'import': write_json(self.work / 'terraform.tfstate', raw_state(self.remote))
        elif name == 'state': return shown(load_json(self.work / 'terraform.tfstate')['resources'][0]['instances'][0]['attributes'])
        elif name in ('refresh', 'ordinary', 'readback', 'second'):
            refresh = name in ('refresh', 'readback')
            self.documents[name] = plan(self.remote, self.manifest['desired'], refresh=refresh)
            local = pe._configuration({key: load_json(self.work / 'terraform.tfstate')['resources'][0]['instances'][0]['attributes'][key]
                                       for key in pe.ATTRIBUTES})
            if local != self.remote:
                self.documents[name]['resource_drift'] = plan(local, self.remote)['resource_changes']
            with zipfile.ZipFile(self.work / (name + '.plan'), 'w') as archive:
                archive.writestr('tfstate', canonical(raw_state(self.remote)))
                archive.writestr('tfplan', canonical(self.documents[name]))
        elif name.endswith('_show'): return copy.deepcopy(self.documents[name.removesuffix('_show')])
        elif name == 'apply':
            self.assert_marker()
            if self.failure == 'before': raise AppError('fixture_before', 'Modeled provider rejected write.')
            self.remote = copy.deepcopy(self.manifest['desired'])
            if self.failure == 'partial':
                self.remote['assignments'] = copy.deepcopy(self.manifest['initial']['assignments'])
                raise AppError('fixture_partial', 'Modeled assignments rejected after policy update.')
            if self.failure in ('lost_response', 'state_write'):
                raise AppError('fixture_unknown', 'Modeled service changed without confirmed state write.')
            write_json(self.work / 'terraform.tfstate', raw_state(self.remote, serial=2))

    def assert_marker(self):
        if load_json(self.root / 'operation.json')['status'] != 'mutation_started':
            raise AssertionError('write dispatched before durable journal')


class TestPermit:
    def __init__(self, request):
        self.request_sha256 = digest(request); self.mode = request['mode']; self.checks = 0; self.active = True
    def check_active(self):
        self.checks += 1
        if not self.active: raise AppError('expired', 'Test authority expired.')
    def mark_dispatch(self):
        self.check_active()
        if getattr(self, 'dispatched', False): raise AppError('spent', 'Test dispatch already marked.')
        self.dispatched = True
    def record_outcome(self, report):
        if not getattr(self, 'dispatched', False): raise AppError('not_dispatched', 'Test dispatch missing.')
        self.outcome = copy.deepcopy(report)


class TestAuthorization:
    def __init__(self, request): self.permit = TestPermit(request); self.entered = False; self.closed = False
    def __enter__(self): self.entered = True; return self.permit
    def __exit__(self, *args): self.closed = True; self.permit.active = False


class ProviderLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.binary = self.base / 'binary'; self.binary.write_bytes(b'modeled-executable-not-native')
        sha = pe._sha(self.binary)
        self.pins = pe.ProviderPins(sha, sha, digest(SCHEMA), 'modeled-source', '1.10.0')
        self.initial = pe._configuration(FIXTURE)
        self.desired = copy.deepcopy(self.initial); self.desired['name'] = 'Changed controlled policy'; self.desired['assignments'].pop()
        created = pe.create_laboratory_executor(self.base / 'executor', pins=self.pins,
            tofu=self.binary, provider=self.binary, initial_configuration=self.initial, admitted_configuration=self.desired,
            object_id=OBJECT_ID, source_sha256='1'*64, admission_sha256='2'*64, target_sha256='3'*64)
        self.executor = ModeledExecutor(created.root)
        self.authorities = patch.dict(sys.modules, {'intune_iac.approval_authority': types.SimpleNamespace(
            ApprovedExecution=TestAuthorization, ExecutionPermit=TestPermit)})
        self.authorities.start(); self.addCleanup(self.authorities.stop)

    def prepare(self): return self.executor.prepare()
    def authorize(self, request): return TestAuthorization(request)

    def test_success_binds_native_artifacts_and_keeps_authority_through_readback(self):
        request = self.prepare(); authorization = self.authorize(request)
        self.assertEqual(request['action'], 'provider_update')
        self.assertEqual(request['bindings']['binary_plan_sha256'], pe._sha(self.executor.work / 'ordinary.plan'))
        result = self.executor.apply(request, authorization=authorization)
        self.assertEqual(result['status'], 'verified'); self.assertFalse(result['production_qualified'])
        self.assertEqual(self.executor.commands, ['init', 'schema', 'validate', 'import', 'state', 'refresh', 'refresh_show',
            'ordinary', 'ordinary_show', 'apply', 'readback', 'readback_show', 'second', 'second_show'])
        self.assertTrue(authorization.closed); self.assertGreaterEqual(authorization.permit.checks, 5)

    def test_partial_policy_assignment_write_is_not_retried(self):
        request = self.prepare(); self.executor.failure = 'partial'
        self.assertEqual(self.executor.apply(request, authorization=self.authorize(request))['status'], 'outcome_unknown')
        result = self.executor.reconcile(request)
        self.assertEqual(result['status'], 'partial_or_divergent'); self.assertFalse(result['retry_authorized'])
        with self.assertRaises(AppError): self.executor.apply(request, authorization=self.authorize(request))
        self.assertEqual(self.executor.commands.count('apply'), 1)

    def test_lost_response_does_not_claim_success(self):
        self._unconfirmed_write('lost_response')

    def test_state_write_failure_does_not_claim_success(self):
        self._unconfirmed_write('state_write')

    def _unconfirmed_write(self, failure):
        request = self.prepare(); self.executor.failure = failure
        self.assertEqual(self.executor.apply(request, authorization=self.authorize(request))['status'], 'outcome_unknown')
        self.assertEqual(self.executor.reconcile(request)['status'], 'service_converged_state_unreconciled')
        self.assertEqual(self.executor.commands.count('apply'), 1)

    def test_before_failure_remains_divergent_and_does_not_auto_retry(self):
        request = self.prepare(); self.executor.failure = 'before'
        self.executor.apply(request, authorization=self.authorize(request))
        self.assertEqual(self.executor.reconcile(request)['status'], 'partial_or_divergent')
        self.assertEqual(self.executor.commands.count('apply'), 1)

    def test_wrong_approval_request_cannot_dispatch(self):
        request = self.prepare(); wrong = copy.deepcopy(request); wrong['bindings']['target_sha256'] = '9'*64
        with self.assertRaisesRegex(AppError, 'Bounded provider'): self.executor.apply(request, authorization=self.authorize(wrong))
        self.assertNotIn('apply', self.executor.commands)

    def test_json_and_callable_approval_cannot_dispatch(self):
        request = self.prepare()
        for approval in (True, {'verified': True}, lambda: True, None):
            with self.subTest(approval=type(approval).__name__), self.assertRaises(AppError):
                self.executor.apply(request, authorization=approval)
        self.assertNotIn('apply', self.executor.commands)

    def test_mutated_saved_plan_cannot_dispatch(self):
        request = self.prepare(); (self.executor.work / 'ordinary.plan').write_bytes(b'other saved plan')
        with self.assertRaises(AppError): self.executor.apply(request, authorization=self.authorize(request))
        self.assertNotIn('apply', self.executor.commands)

    def test_state_changes_between_approval_and_dispatch_are_refused(self):
        request = self.prepare(); write_json(self.executor.work / 'terraform.tfstate', raw_state(self.initial, serial=2))
        with self.assertRaises(AppError): self.executor.apply(request, authorization=self.authorize(request))
        self.assertNotIn('apply', self.executor.commands)

    def test_journal_write_failure_prevents_provider_write(self):
        request = self.prepare(); original = pe.write_json
        def fail(path, value):
            if Path(path).name == 'operation.json': raise AppError('write_failed', 'Modeled failed persistence.')
            return original(path, value)
        with patch.object(pe, 'write_json', side_effect=fail), self.assertRaises(AppError):
            self.executor.apply(request, authorization=self.authorize(request))
        self.assertNotIn('apply', self.executor.commands)

    def test_final_journal_failure_retains_attempt_marker(self):
        request = self.prepare(); original = pe.write_json
        def fail(path, value):
            if Path(path).name == 'operation.json' and value['status'] != 'mutation_started':
                raise AppError('write_failed', 'Modeled failed final persistence.')
            return original(path, value)
        with patch.object(pe, 'write_json', side_effect=fail):
            result = self.executor.apply(request, authorization=self.authorize(request))
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(load_json(self.executor.root / 'operation.json')['status'], 'mutation_started')
        self.assertEqual(self.executor.reconcile(request)['status'], 'desired_state_observed_execution_unconfirmed')
        with self.assertRaises(AppError): self.executor.apply(request, authorization=self.authorize(request))

    def test_config_hook_extra_provider_and_interpolation_rejected(self):
        for key, value in [('provisioner', {}), ('provider', 'evil'), ('lifecycle', {}), ('name', '${file("/etc/passwd")}')]:
            damaged = copy.deepcopy(self.initial); damaged[key] = value
            with self.subTest(key=key), self.assertRaises(AppError): pe._configuration(damaged)

    def test_configuration_symlink_and_foreign_hcl_cannot_run(self):
        extra = self.executor.work / 'arbitrary.tf'; extra.write_text('resource "local_file" "x" {}')
        with self.assertRaises(AppError): self.prepare()
        extra.unlink(); config = self.executor.work / 'main.tf.json'; data = config.read_bytes(); config.unlink()
        outside = self.base / 'outside'; outside.write_bytes(data); config.symlink_to(outside)
        with self.assertRaises(AppError): self.prepare()

    def test_workspace_must_remain_private_to_host_owner(self):
        self.executor.root.chmod(0o777)
        with self.assertRaises(AppError): self.prepare()
        self.assertEqual(self.executor.commands, [])

    def test_wrong_selected_schema_is_refused_before_import(self):
        self.executor.manifest['pins']['selected_schema_sha256'] = '0'*64
        write_json(self.executor.root / 'executor.json', self.executor.manifest)
        self.executor._manifest_sha = digest(self.executor.manifest)
        with self.assertRaises(AppError): self.prepare()
        self.assertNotIn('import', self.executor.commands)

    def test_changed_provider_binary_is_refused(self):
        binary = self.executor.root / 'mirror' / pe.SOURCE / pe.VERSION / 'linux_amd64' / 'terraform-provider-microsoft365_v1.0.0'
        binary.chmod(0o600); binary.write_bytes(b'tampered provider executable')
        with self.assertRaises(AppError): self.prepare()
        self.assertEqual(self.executor.commands, [])

    def test_extra_provider_binary_or_installed_path_cannot_override_pin(self):
        mirror = self.executor.root / 'mirror' / pe.SOURCE / pe.VERSION / 'linux_amd64'
        extra = mirror / 'terraform-provider-microsoft365_v1.0.0_x5'; extra.write_bytes(b'foreign')
        with self.assertRaises(AppError): self.prepare()
        extra.unlink()
        installed = self.executor.work / '.terraform/providers' / pe.SOURCE / pe.VERSION
        installed.mkdir(parents=True); (installed / 'linux_amd64').symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(AppError): self.prepare()

    def test_provider_lock_change_cannot_dispatch(self):
        request = self.prepare(); (self.executor.work / '.terraform.lock.hcl').write_text('foreign provider hashes')
        with self.assertRaises(AppError): self.executor.apply(request, authorization=self.authorize(request))
        self.assertNotIn('apply', self.executor.commands)

    def test_foreign_state_lineage_after_apply_cannot_verify(self):
        request = self.prepare(); self.executor.apply(request, authorization=self.authorize(request))
        write_json(self.executor.work / 'terraform.tfstate', raw_state(self.desired, serial=2,
                   lineage='99999999-9999-4999-8999-999999999999'))
        self.assertEqual(self.executor.reconcile(request)['status'], 'readback_unresolved')

    def test_credentials_are_not_inherited_or_arbitrary(self):
        with patch.dict(os.environ, {'TF_CLI_ARGS': '-target=evil', 'HTTPS_PROXY': 'http://evil', 'M365_CLIENT_SECRET': 'ambient'}):
            env = self.executor._environment()
        self.assertNotIn('TF_CLI_ARGS', env); self.assertNotIn('HTTPS_PROXY', env); self.assertNotIn('M365_CLIENT_SECRET', env)
        with self.assertRaises(AppError): pe.ProviderExecutor(self.executor.root, credential_environment={'TF_CLI_ARGS': 'evil'})

    def test_raw_state_rejects_foreign_identity_and_lineage(self):
        self.prepare(); raw = raw_state(self.initial); raw['resources'][0]['instances'][0]['attributes']['id'] = '11111111-1111-4111-8111-111111111111'
        write_json(self.executor.work / 'terraform.tfstate', raw)
        with self.assertRaises(AppError): pe._raw_state(self.executor.work / 'terraform.tfstate', OBJECT_ID)

    def test_plan_rejects_replacement_unknown_settings_and_extra_resources(self):
        for mutation in ('replace', 'unknown', 'extra', 'id', 'wrapper', 'null', 'assignment', 'output'):
            document = plan(self.initial, self.desired); change = document['resource_changes'][0]['change']
            if mutation == 'replace': change['actions'] = ['delete', 'create']
            elif mutation == 'unknown': change['after_unknown'] = {'settings': True}
            elif mutation == 'extra': document['resource_changes'].append(copy.deepcopy(document['resource_changes'][0]))
            elif mutation == 'id': change['after']['id'] = '11111111-1111-4111-8111-111111111111'
            elif mutation in ('wrapper', 'null'):
                s = json.loads(change['after']['settings'])
                if mutation == 'wrapper': s['settings'][0]['id'] = '0'
                else: s['settings'][0]['settingInstance']['choiceSettingValue']['children'] = None
                change['after']['settings'] = json.dumps(s)
            elif mutation == 'assignment': change['after']['assignments'] = []
            elif mutation == 'output': document['output_changes'] = {'secret': {}}
            with self.subTest(mutation=mutation), self.assertRaises(AppError): pe._plan(document, OBJECT_ID, self.desired, self.initial, engine_version='1.10.0')

    def test_reconcile_never_runs_import_or_apply(self):
        request = self.prepare(); self.executor.apply(request, authorization=self.authorize(request)); self.executor.commands.clear()
        self.assertEqual(self.executor.reconcile(request)['status'], 'desired_state_observed_execution_unconfirmed')
        self.assertEqual(self.executor.commands, ['readback', 'readback_show', 'second', 'second_show'])

    def test_forged_operation_journal_cannot_prove_exact_plan_returned(self):
        request = self.prepare(); self.executor.remote = copy.deepcopy(self.desired)
        write_json(self.executor.work / 'terraform.tfstate', raw_state(self.desired, serial=2))
        write_json(self.executor.root / 'operation.json', {'operation_id': request['operation_id'],
            'request_sha256': digest(request), 'mutation_attempts': 1, 'status': 'verified',
            'execution_outcome': {'status': 'verified', 'exact_plan_returned': True}})
        report = self.executor.reconcile(request)
        self.assertEqual(report['status'], 'desired_state_observed_execution_unconfirmed')
        self.assertIs(report['exact_plan_returned'], False)
        self.assertNotIn('apply', self.executor.commands)

    def test_changed_implementation_invalidates_prepared_approval(self):
        request = self.prepare()
        with patch.object(pe, '_implementation', return_value={'provider_execution.py': '0'*64}), self.assertRaises(AppError):
            self.executor.apply(request, authorization=self.authorize(request))
        self.assertNotIn('apply', self.executor.commands)


class NativeSupervisorTests(unittest.TestCase):
    def test_plan_snapshot_survives_source_overwrite_and_cannot_be_written(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan'; path.write_bytes(b'approved immutable plan')
            descriptor = pe._sealed_plan(path, pe._sha(path))
            try:
                path.write_bytes(b'substituted plan')
                self.assertEqual(os.read(descriptor, 100), b'approved immutable plan')
                with self.assertRaises(PermissionError): os.write(descriptor, b'evil')
                with self.assertRaises(PermissionError):
                    with open('/proc/self/fd/' + str(descriptor), 'wb') as changed: changed.write(b'evil')
                with self.assertRaises(PermissionError): os.ftruncate(descriptor, 0)
            finally: os.close(descriptor)

    def test_immutable_plan_snapshot_unavailable_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan'; path.write_bytes(b'approved immutable plan')
            with patch.object(os, 'memfd_create', side_effect=OSError('unavailable')), self.assertRaises(AppError):
                pe._sealed_plan(path, pe._sha(path))

    def test_network_denied_but_plugin_unix_socket_and_child_process_allowed(self):
        try:
            probe = socket.socket(socket.AF_UNIX); probe.close()
        except PermissionError:
            self.skipTest('Host sandbox denies AF_UNIX before adapter guard; provider RPC cannot be qualified here.')
        script = ('import socket,subprocess,sys\n'
                  's=socket.socket(socket.AF_UNIX);s.close()\n'
                  'for family in (socket.AF_INET,socket.AF_INET6):\n'
                  ' try: socket.socket(family)\n'
                  ' except PermissionError: pass\n'
                  ' else: sys.exit(9)\n'
                  'subprocess.run([sys.executable,"-c","pass"],check=True)\n'
                  'print("isolated")\n')
        result = pe._supervise([sys.executable, '-c', script], cwd=ROOT, env={'PATH': '/usr/bin:/bin'}, executable=sys.executable, pass_fds=())
        self.assertEqual(result, {'code': 0, 'stdout': b'isolated\n'})

    def test_output_and_deadline_are_bounded(self):
        for script, kw in [('print("x"*100000)', {'output_limit': 100}), ('import time;time.sleep(5)', {'timeout': 0.1})]:
            with self.subTest(script=script), self.assertRaises(AppError):
                pe._supervise([sys.executable, '-c', script], cwd=ROOT, env={}, executable=sys.executable, pass_fds=(), **kw)

    def test_expiring_host_permit_stops_running_process(self):
        count = []
        def check():
            count.append(1)
            if len(count) > 2: raise AppError('expired', 'Modeled authority expired.')
        with self.assertRaises(AppError):
            pe._supervise([sys.executable, '-c', 'import time;time.sleep(10)'], cwd=ROOT, env={},
                          executable=sys.executable, pass_fds=(), active_check=check)
        self.assertEqual(len(count), 3)

    def test_closed_output_pipes_do_not_disable_authority_watchdog(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'unapproved-write'
            started = time.monotonic()
            def check():
                if time.monotonic() - started > 0.15: raise AppError('expired', 'Modeled authority expired.')
            script = 'import os,time,pathlib;os.close(1);os.close(2);time.sleep(0.5);pathlib.Path(' + repr(str(marker)) + ').write_text("write")'
            with self.assertRaises(AppError):
                pe._supervise([sys.executable, '-c', script], cwd=ROOT, env={}, executable=sys.executable,
                              pass_fds=(), active_check=check)
            self.assertFalse(marker.exists())


class IndependentPreservationFacts(unittest.TestCase):
    """Hand-authored facts from the existing fixture; no shared normalizer oracle."""
    def assert_facts(self, attributes):
        self.assertEqual(attributes['name'], 'Synthetic existing Intune policy')
        self.assertEqual(attributes['description'], 'Fixture only')
        self.assertEqual(attributes['platforms'], 'windows10')
        self.assertEqual(attributes['technologies'], ['mdm'])
        self.assertEqual(attributes['role_scope_tag_ids'], ['0'])
        self.assertEqual(json.loads(attributes['settings']), {'settings': [{
            '@odata.type': '#microsoft.graph.deviceManagementConfigurationSetting', 'id': '37',
            'settingInstance': {
                '@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance',
                'settingDefinitionId': 'device_vendor_msft_policy_config_privacy_letappsaccesslocation',
                'settingInstanceTemplateReference': None,
                'choiceSettingValue': {
                    '@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingValue',
                    'value': 'device_vendor_msft_policy_config_privacy_letappsaccesslocation_2',
                    'settingValueTemplateReference': None, 'children': []}}}]})
        self.assertEqual(sorted((x['type'], x['group_id'], x['filter_id'], x['filter_type']) for x in attributes['assignments']), [
            ('exclusionGroupAssignmentTarget', '22222222-2222-4222-8222-222222222222', '00000000-0000-0000-0000-000000000000', 'none'),
            ('groupAssignmentTarget', '11111111-1111-4111-8111-111111111111', '44444444-4444-4444-8444-444444444444', 'include')])

    def test_actual_historical_resource_values_match_independent_facts_and_mutations_fail(self):
        # These are historical native RPC values, not evidence of a new native
        # lifecycle. The facts above are independent of _configuration().
        path = ROOT / 'research/provider-qualification/completion-20261002/evidence/synthetic-rpc-omitted-filter-green/state.stdout'
        original = json.loads(path.read_text())['values']['root_module']['resources'][0]['values']
        self.assertEqual(original['id'], '33333333-3333-4333-8333-333333333333')
        self.assert_facts(pe._observe(original, '33333333-3333-4333-8333-333333333333'))
        for mutation in ('wrong_policy_id', 'renumber_setting', 'omit_null', 'null_children', 'omit_wrapper',
                         'lost_exclusion', 'wrong_filter_id', 'wrong_setting_value', 'empty_settings', 'description_null'):
            damaged = copy.deepcopy(original); settings = json.loads(damaged['settings'])
            if mutation == 'wrong_policy_id': damaged['id'] = '99999999-9999-4999-8999-999999999999'
            elif mutation == 'renumber_setting': settings['settings'][0]['id'] = '0'
            elif mutation == 'omit_null': del settings['settings'][0]['settingInstance']['settingInstanceTemplateReference']
            elif mutation == 'null_children': settings['settings'][0]['settingInstance']['choiceSettingValue']['children'] = None
            elif mutation == 'omit_wrapper': del settings['settings'][0]['@odata.type']
            elif mutation == 'lost_exclusion': damaged['assignments'] = [x for x in damaged['assignments'] if x['type'] != 'exclusionGroupAssignmentTarget']
            elif mutation == 'wrong_filter_id':
                next(x for x in damaged['assignments'] if x['type'] == 'groupAssignmentTarget')['filter_id'] = '55555555-5555-4555-8555-555555555555'
            elif mutation == 'wrong_setting_value': settings['settings'][0]['settingInstance']['choiceSettingValue']['value'] = 'device_vendor_msft_policy_config_privacy_letappsaccesslocation_1'
            elif mutation == 'empty_settings': settings['settings'] = []
            elif mutation == 'description_null': damaged['description'] = None
            damaged['settings'] = json.dumps(settings)
            with self.subTest(mutation=mutation), self.assertRaises((AppError, AssertionError)):
                self.assert_facts(pe._observe(damaged, '33333333-3333-4333-8333-333333333333'))
