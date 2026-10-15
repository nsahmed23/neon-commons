"""Readiness by operation: a pure model over the facts the product already gathers.

Inputs here are plain dictionaries, either written by hand in the shapes of
entry.survey, host_capabilities.report and doctor, or produced by those real
functions against temporary directories only. Nothing touches a real workspace,
a home directory, the network, a credential or the project records.
"""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TENANT = '11111111-1111-4111-8111-111111111111'
OTHER_TENANT = '44444444-4444-4444-8444-444444444444'
FAKE_SECRET = 'FAKE-SECRET-VALUE-8f3a91c2d47e5b60a1c9'
OPERATIONS = ('inspect', 'prepare', 'adopt', 'change')
ROW_IDS = ('mode_goal', 'tools_host', 'repository', 'integration_service', 'iac_target', 'backend',
           'execution_route', 'secret_input')
NEEDS = {
    'inspect': {'mode_goal', 'tools_host'},
    'prepare': {'mode_goal', 'tools_host', 'integration_service', 'secret_input'},
    'adopt': {'mode_goal', 'tools_host', 'repository', 'integration_service', 'iac_target', 'backend', 'secret_input'},
    'change': set(ROW_IDS),
}
CREDENTIAL_ROWS = ('integration_service', 'backend', 'execution_route', 'secret_input')


def states(authenticated='no_live_connection', configured=True):
    return {'discovered': True, 'configured': configured, 'authenticated': authenticated, 'qualified': 'not_qualified'}


def survey_of(*items, connection='offline'):
    return {'schema_version': 'workbench-start/1', 'directory': '/work/here', 'connection': connection, 'items': list(items),
            'next_actions': [], 'missing': [], 'skipped_links': [], 'truncated': False,
            'execution_authorized': False, 'cloud_authority': False}


def repository_item(stack='orgs/reference/dev', component='intune-reference', revision='a' * 40, path='repository'):
    return {'kind': 'repository', 'path': path, 'status': 'discovered', 'stacks': [stack],
            'components': [{'stack': stack, 'component': component}], 'git_revision': revision, 'blockers': [],
            'states': states()}


def context_item(stack='orgs/reference/dev', component='intune-reference', tenant=TENANT):
    return {'kind': 'context', 'path': 'context.json', 'tenant_id': tenant, 'stack': stack, 'component': component,
            'synthetic': True, 'states': states()}


def export_item(tenant=TENANT):
    return {'kind': 'export', 'path': 'export.json', 'synthetic': True, 'tenant_id': tenant, 'policies': [],
            'states': states('source_asserted_not_authenticated')}


def host_report(unsupported=()):
    profiles = {}
    for name in ('workbench_store', 'graph_observer', 'protected_worker', 'artifact_vault', 'visual_workspace'):
        bad = name in unsupported
        profiles[name] = {'status': 'UNSUPPORTED' if bad else 'IMPLEMENTED', 'missing_primitives': ['linux'] if bad else [],
                          'required_implementation': ['x'] if bad else [], 'platform_qualified': False}
    return {'schema_version': 'intune-host-capabilities/1',
            'host': {'os_name': 'posix', 'sys_platform': 'linux', 'machine': 'x86_64', 'python_version': '3.12.3'},
            'primitives': {'posix': True}, 'profiles': profiles, 'native_windows_qualified': False,
            'platform_qualified': False, 'production_approved': False}


def doctor_report(missing_packages=(), executables=None, cloud_apply='unavailable', production_capture='explicit_read_only_credentials_required'):
    dependencies = {name: {'available': name not in missing_packages, 'version': '1.0'} for name in ('jsonschema', 'PyYAML', 'python-hcl2')}
    return {'version': '0', 'status': 'missing_dependencies' if missing_packages else 'ready', 'dependencies': dependencies,
            'capabilities': {'wizard': 'missing_dependencies' if missing_packages else 'available', 'cloud_apply': cloud_apply,
                             'production_capture': production_capture},
            'executables': executables if executables is not None else {'atmos': True, 'tofu': True, 'pwsh': False, 'codex': False, 'claude': False},
            'route_scope': {'adoption': {'native_service_preparation': 'durable_manifest_preparation_and_review_cli',
                                         'live_qualified': False, 'platform_qualified': False}},
            'live_qualified': False, 'native_host_qualified': False}


def rows_of(value, operation):
    rows = value['operations'][operation]['rows']
    return {row['id']: row for row in rows}


class ReadinessTests(unittest.TestCase):
    def model(self, survey=None, host=None, doctor=None):
        from intune_iac.readiness import readiness
        return readiness(survey, host, doctor)

    def full(self, *items, **kwargs):
        return self.model(survey_of(*items), kwargs.get('host', host_report()), kwargs.get('doctor', doctor_report()))

    # shape and vocabulary

    def test_every_operation_has_the_eight_rows_with_the_required_fields(self):
        value = self.full(repository_item(), context_item())
        self.assertEqual(tuple(value['operations']), OPERATIONS)
        for operation in OPERATIONS:
            rows = value['operations'][operation]['rows']
            self.assertEqual(tuple(row['id'] for row in rows), ROW_IDS)
            for row in rows:
                self.assertEqual(set(row), {'id', 'label', 'needed', 'state', 'detected', 'missing', 'next_action', 'owner_role'})
                self.assertIn(row['state'], ('ready', 'missing', 'unknown', 'not_needed'))
                self.assertIn(row['owner_role'], ('engineer', 'administrator', 'organization'))
                self.assertIsInstance(row['needed'], bool)
                self.assertIsInstance(row['detected'], dict)
                self.assertIsInstance(row['missing'], list)
                self.assertTrue(isinstance(row['next_action'], str) and row['next_action'])
            self.assertIn(value['operations'][operation]['status'], ('ready', 'missing', 'unknown'))

    def test_each_operation_needs_exactly_its_rows(self):
        value = self.full(repository_item(), context_item())
        for operation in OPERATIONS:
            needed = {row_id for row_id, row in rows_of(value, operation).items() if row['needed']}
            self.assertEqual(needed, NEEDS[operation], operation)
            for row_id, row in rows_of(value, operation).items():
                if not row['needed']:
                    self.assertEqual(row['state'], 'not_needed')
                    self.assertEqual(row['missing'], [])
                else:
                    self.assertNotEqual(row['state'], 'not_needed')

    def test_the_model_never_grants_authority(self):
        value = self.full(repository_item(), context_item())
        self.assertFalse(value['execution_authorized'])
        self.assertFalse(value['cloud_authority'])
        self.assertEqual(value['schema_version'], 'workbench-readiness/1')

    # the five situations the brief names

    def test_an_offline_directory_with_no_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            from intune_iac.entry import survey
            value = self.model(survey(temp), host_report(), doctor_report())
        inspect = rows_of(value, 'inspect')
        self.assertEqual(inspect['mode_goal']['state'], 'ready')
        self.assertEqual(inspect['tools_host']['state'], 'ready')
        self.assertEqual(inspect['repository']['state'], 'not_needed')
        self.assertEqual(value['operations']['inspect']['status'], 'ready')
        adopt = rows_of(value, 'adopt')
        self.assertEqual(adopt['repository']['state'], 'missing')
        self.assertIn('atmos.yaml', ' '.join(adopt['repository']['missing']))
        self.assertIn('intune-iac start', adopt['repository']['next_action'])
        self.assertIn('repository-entry', adopt['repository']['next_action'])
        self.assertEqual(adopt['iac_target']['state'], 'missing')
        self.assertEqual(value['operations']['adopt']['status'], 'missing')

    def test_a_repository_with_a_selectable_component(self):
        value = self.full(repository_item(), context_item())
        adopt = rows_of(value, 'adopt')
        self.assertEqual(adopt['repository']['state'], 'ready')
        repositories = adopt['repository']['detected']['repositories']
        self.assertEqual(repositories[0]['git_revision'], 'a' * 12)
        self.assertEqual(repositories[0]['components'], [{'stack': 'orgs/reference/dev', 'component': 'intune-reference'}])
        self.assertEqual(adopt['iac_target']['state'], 'ready')
        self.assertEqual(adopt['iac_target']['detected']['effective_configuration'], 'not_resolved_by_this_check')
        self.assertIn('intune-iac repository resolve', adopt['iac_target']['next_action'])
        # Ready repository and target do not make the operation ready: the service and backend are not established.
        self.assertEqual(value['operations']['adopt']['status'], 'missing')

    def test_a_repository_that_is_not_a_git_checkout_is_not_ready(self):
        broken = repository_item(revision=None)
        broken['states'] = states(configured=False)
        broken['states']['configured_reason'] = 'not_a_git_repository'
        value = self.full(broken, context_item())
        row = rows_of(value, 'adopt')['repository']
        self.assertEqual(row['state'], 'missing')
        self.assertIn('Git', ' '.join(row['missing']))
        self.assertEqual(rows_of(value, 'adopt')['iac_target']['state'], 'missing')

    def test_a_stack_named_differently_from_the_repository_is_unknown_not_ready(self):
        # The real wizard output lists orgs/reference/dev while the context says reference-dev.
        value = self.full(repository_item(), context_item(stack='reference-dev'))
        row = rows_of(value, 'adopt')['iac_target']
        self.assertEqual(row['state'], 'unknown')
        self.assertIn('reference-dev', ' '.join(row['missing']))

    def test_a_host_missing_a_required_tool(self):
        value = self.full(repository_item(), context_item(),
                          doctor=doctor_report(executables={'atmos': False, 'tofu': True, 'pwsh': False, 'codex': False, 'claude': False}))
        adopt = rows_of(value, 'adopt')['tools_host']
        self.assertEqual(adopt['state'], 'missing')
        self.assertIn('atmos', ' '.join(adopt['missing']))
        self.assertNotIn('tofu', ' '.join(adopt['missing']))
        self.assertIn('intune-iac doctor', adopt['next_action'])
        # The offline route does not need Atmos.
        self.assertEqual(rows_of(value, 'inspect')['tools_host']['state'], 'ready')

    def test_missing_python_packages_stop_every_operation(self):
        value = self.full(doctor=doctor_report(missing_packages=('jsonschema',)))
        for operation in OPERATIONS:
            row = rows_of(value, operation)['tools_host']
            self.assertEqual(row['state'], 'missing', operation)
            self.assertIn('jsonschema', ' '.join(row['missing']))
            self.assertIn('requirements-runtime.txt', row['next_action'])
        self.assertEqual(rows_of(value, 'inspect')['mode_goal']['state'], 'missing')

    def test_an_unsupported_host_profile_names_the_gap_and_has_no_native_route(self):
        value = self.full(host=host_report(unsupported=('protected_worker', 'graph_observer')))
        for operation in ('prepare', 'adopt', 'change'):
            row = rows_of(value, operation)['tools_host']
            self.assertEqual(row['state'], 'missing', operation)
            self.assertIn('linux', ' '.join(row['missing']))
            self.assertIn('no native Windows route', row['next_action'])
        self.assertEqual(rows_of(value, 'inspect')['tools_host']['state'], 'ready')

    def test_a_live_looking_context_with_no_authentication(self):
        value = self.full(context_item())
        for operation in ('prepare', 'adopt', 'change'):
            row = rows_of(value, operation)['integration_service']
            self.assertTrue(row['needed'])
            self.assertEqual(row['state'], 'missing', operation)
            self.assertEqual(row['detected']['tenants'], [TENANT])
            self.assertEqual(row['detected']['identity_evidence'], ['no_live_connection'])
            self.assertIn('No verified sign-in', ' '.join(row['missing']))
        change = rows_of(value, 'change')['integration_service']
        joined = ' '.join(change['missing'])
        self.assertIn('never implies permission for a change', joined)
        self.assertIn('no route yet for sign-in reuse', joined)
        self.assertIn('OIDC', joined)
        self.assertEqual(value['operations']['change']['status'], 'missing')

    def test_the_same_with_a_source_asserted_identity(self):
        value = self.full(context_item(), export_item())
        row = rows_of(value, 'prepare')['integration_service']
        self.assertEqual(row['state'], 'missing')
        self.assertEqual(row['detected']['identity_evidence'], ['no_live_connection', 'source_asserted_not_authenticated'])
        self.assertIn('asserted by a file', ' '.join(row['missing']))
        self.assertNotEqual(value['operations']['prepare']['status'], 'ready')

    def test_no_tenant_at_all_asks_the_engineer_for_a_context(self):
        row = rows_of(self.full(), 'prepare')['integration_service']
        self.assertEqual(row['state'], 'missing')
        self.assertEqual(row['owner_role'], 'engineer')
        self.assertIn('context JSON', row['next_action'])
        self.assertIn('No tenant', ' '.join(row['missing']))

    def test_a_sign_in_word_the_product_never_produces_is_not_trusted(self):
        item = context_item(); item['states'] = states('authenticated')
        value = self.full(item)
        for operation in ('prepare', 'adopt', 'change'):
            self.assertEqual(rows_of(value, operation)['integration_service']['state'], 'unknown', operation)

    # the inspect operation and truthfulness

    def test_inspect_needs_no_service_credential(self):
        for survey in (None, survey_of(), survey_of(export_item(), context_item())):
            value = self.model(survey, host_report(), doctor_report())
            rows = rows_of(value, 'inspect')
            for row_id in ('repository', 'integration_service', 'iac_target') + CREDENTIAL_ROWS:
                self.assertFalse(rows[row_id]['needed'], row_id)
                self.assertEqual(rows[row_id]['state'], 'not_needed', row_id)
            self.assertEqual(value['operations']['inspect']['status'], 'ready')

    def test_nothing_is_ready_without_supporting_facts(self):
        for args in ((None, None, None), ({}, {}, {}), ('text', 5, [])):
            value = self.model(*args)
            for operation in OPERATIONS:
                self.assertEqual(value['operations'][operation]['status'], 'unknown', (args, operation))
                for row in rows_of(value, operation).values():
                    self.assertNotEqual(row['state'], 'ready', (operation, row['id']))
                    if row['needed']:
                        self.assertEqual(row['state'], 'unknown', (operation, row['id']))
                    for key in row['missing']:
                        self.assertIsInstance(key, str)

    def test_every_ready_row_carries_detected_facts(self):
        value = self.full(repository_item(), context_item(), export_item())
        ready = 0
        for operation in OPERATIONS:
            for row in rows_of(value, operation).values():
                if row['state'] == 'ready':
                    ready += 1
                    self.assertTrue(row['detected'], (operation, row['id']))
        self.assertGreater(ready, 0)

    def test_no_service_credential_row_is_ready_from_any_survey(self):
        surveys = (survey_of(), survey_of(context_item()), survey_of(export_item(), context_item(), repository_item()))
        for survey in surveys:
            value = self.model(survey, host_report(), doctor_report())
            for operation in OPERATIONS:
                rows = rows_of(value, operation)
                for row_id in ('integration_service', 'backend', 'execution_route', 'secret_input'):
                    self.assertNotEqual(rows[row_id]['state'], 'ready', (operation, row_id))

    def test_a_working_sign_in_does_not_imply_change_permission(self):
        value = self.full(context_item(), repository_item())
        change = value['operations']['change']
        self.assertNotEqual(change['status'], 'ready')
        self.assertIn('mode_goal', change['blocking'])
        self.assertIn('execution_route', change['blocking'])
        self.assertEqual(rows_of(value, 'change')['mode_goal']['state'], 'missing')
        self.assertIn('no route yet', rows_of(value, 'change')['mode_goal']['next_action'])

    def test_where_the_product_has_no_route_the_row_says_so_in_words(self):
        value = self.full(repository_item(), context_item())
        execution = rows_of(value, 'change')['execution_route']
        self.assertEqual(execution['state'], 'missing')
        self.assertEqual(execution['owner_role'], 'organization')
        self.assertIn('No route yet', execution['next_action'])
        self.assertIn('CI identity', ' '.join(execution['missing']))
        secret = rows_of(value, 'adopt')['secret_input']
        self.assertEqual(secret['state'], 'unknown')
        self.assertIn('--provider-secret-fd', secret['next_action'])
        self.assertIn('no secure-reference', secret['next_action'])
        backend = rows_of(value, 'adopt')['backend']
        self.assertEqual(backend['state'], 'unknown')
        self.assertIn('target authenticate', backend['next_action'])
        prepare = rows_of(value, 'prepare')['secret_input']
        self.assertIn('--token-env', prepare['next_action'])
        self.assertIn('never on a command line', prepare['next_action'])

    def test_blockers_name_the_row_the_command_and_the_role(self):
        value = self.full(repository_item(), context_item())
        blockers = value['operations']['adopt']['blockers']
        self.assertEqual([item['row'] for item in blockers], value['operations']['adopt']['blocking'])
        for item in blockers:
            self.assertIn(item['state'], ('missing', 'unknown'))
            self.assertTrue(item['next_action'])
            self.assertIn(item['owner_role'], ('engineer', 'administrator', 'organization'))
        self.assertIn('integration_service', value['operations']['adopt']['blocking'])

    def test_prepare_depends_on_the_platform_for_read_only_capture(self):
        value = self.full(doctor=doctor_report(production_capture='unavailable_on_platform'))
        row = rows_of(value, 'prepare')['mode_goal']
        self.assertEqual(row['state'], 'missing')
        self.assertIn('POSIX', row['next_action'])

    # secrets, purity

    def test_no_secret_looking_value_in_an_input_reaches_the_output(self):
        repository = repository_item(); repository['note'] = FAKE_SECRET; repository['states']['label'] = FAKE_SECRET
        repository['components'][0]['hint'] = FAKE_SECRET
        context = context_item(); context['comment'] = 'Bearer ' + FAKE_SECRET
        export = export_item(); export['description'] = FAKE_SECRET
        survey = survey_of(repository, context, export); survey['note'] = FAKE_SECRET
        host = host_report(); host['host']['label'] = FAKE_SECRET; host['extra'] = {'token': FAKE_SECRET}
        doctor = doctor_report(); doctor['capabilities']['label'] = FAKE_SECRET; doctor['extra'] = FAKE_SECRET
        doctor['executables']['custom'] = FAKE_SECRET
        text = json.dumps(self.model(survey, host, doctor), sort_keys=True)
        self.assertNotIn(FAKE_SECRET, text)
        self.assertNotIn('Bearer', text)

    def test_a_secret_in_a_named_field_is_dropped_not_echoed(self):
        context = context_item(tenant=FAKE_SECRET, stack=FAKE_SECRET, component='token=' + FAKE_SECRET)
        repository = repository_item(stack=FAKE_SECRET, component=FAKE_SECRET, revision=FAKE_SECRET)
        survey = survey_of(context, repository, export_item(tenant='sk-' + FAKE_SECRET))
        survey['directory'] = '/work/' + FAKE_SECRET
        doctor = doctor_report(); doctor['executables'] = {'atmos': FAKE_SECRET, 'tofu': True}
        value = self.model(survey, host_report(), doctor)
        text = json.dumps(value, sort_keys=True)
        self.assertNotIn(FAKE_SECRET, text)
        self.assertEqual(rows_of(value, 'adopt')['integration_service']['detected'].get('tenants', []), [])

    def test_an_unbroken_token_shaped_value_is_dropped_but_long_snake_case_names_pass(self):
        token = 'ghp_' + 'a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8'
        value = self.full(repository_item(stack='orgs/' + token, component=token), context_item())
        self.assertNotIn(token, json.dumps(value))
        self.assertEqual(rows_of(value, 'adopt')['repository']['state'], 'missing')
        ready = rows_of(self.full(), 'adopt')['mode_goal']
        self.assertEqual(ready['state'], 'ready')
        self.assertEqual(ready['detected']['route'], 'durable_manifest_preparation_and_review_cli')

    def test_environment_variables_are_never_read_and_inputs_are_not_changed(self):
        class Forbidden(dict):
            def _refuse(self, *args, **kwargs): raise AssertionError('the environment was read')
            __getitem__ = get = __iter__ = __contains__ = keys = items = values = copy = _refuse
        inputs = (survey_of(repository_item(), context_item(), export_item()), host_report(), doctor_report())
        before = copy.deepcopy(inputs)
        with patch.dict(os.environ, {'INTUNE_GRAPH_TOKEN': FAKE_SECRET, 'INTUNE_MANAGEMENT_TOKEN': FAKE_SECRET}):
            with patch.object(os, 'environ', Forbidden()):
                value = self.model(*inputs)
        self.assertEqual(inputs, before)
        self.assertNotIn(FAKE_SECRET, json.dumps(value))

    def test_the_result_is_json_serializable_and_stable(self):
        inputs = (survey_of(repository_item(), context_item()), host_report(), doctor_report())
        first = json.dumps(self.model(*inputs), sort_keys=True, allow_nan=False)
        second = json.dumps(self.model(*inputs), sort_keys=True, allow_nan=False)
        self.assertEqual(first, second)

    def test_the_doctor_carries_the_host_report_when_none_is_passed_separately(self):
        doctor = doctor_report(); doctor['host_capabilities'] = host_report(unsupported=('protected_worker',))
        value = self.model(survey_of(), None, doctor)
        self.assertEqual(rows_of(value, 'adopt')['tools_host']['state'], 'missing')
        self.assertEqual(rows_of(value, 'inspect')['tools_host']['state'], 'ready')

    def test_what_the_product_cannot_check_is_listed(self):
        text = ' '.join(self.full()['not_established'])
        for phrase in ('Working-directory access', 'GitHub', 'Environment variables', 'expiry'):
            self.assertIn(phrase, text)

    # the real producers

    def test_the_real_producers_feed_the_model(self):
        import plugin_tests.test_entry as entry_tests
        from intune_iac import cli, host_capabilities
        from intune_iac.entry import survey

        class Holder: pass
        holder = Holder()
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        holder.root = Path(temp.name) / 'work'; holder.root.mkdir()
        entry_tests.EntryTests.build(holder)
        value = self.model(survey(holder.root), host_capabilities.report(), cli.doctor())
        adopt = rows_of(value, 'adopt')
        self.assertEqual(adopt['repository']['state'], 'ready')
        self.assertEqual(adopt['repository']['detected']['repositories'][0]['git_revision'], 'a' * 12)
        self.assertEqual(adopt['mode_goal']['state'], 'ready')
        # The context says reference-dev; discovery lists orgs/reference/dev: not decidable here.
        self.assertEqual(adopt['iac_target']['state'], 'unknown')
        self.assertEqual(adopt['integration_service']['state'], 'missing')
        self.assertEqual(adopt['integration_service']['detected']['tenants'], [TENANT])
        self.assertIn('source_asserted_not_authenticated', adopt['integration_service']['detected']['identity_evidence'])
        self.assertIn('modeled_service_no_authentication', adopt['integration_service']['detected']['identity_evidence'])
        inspect = rows_of(value, 'inspect')
        self.assertEqual(inspect['mode_goal']['state'], 'ready')
        self.assertEqual(inspect['tools_host']['state'], 'ready')
        self.assertNotIn(str(holder.root.parent), json.dumps(value['operations']['inspect']['rows'][2]))


if __name__ == '__main__':
    unittest.main()
