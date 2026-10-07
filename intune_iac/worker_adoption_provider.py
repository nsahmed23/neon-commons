"""Fixed native state-only adoption payloads; preparation grants no authority.

This adapter reuses the existing provider source and isolated worker setup. It
adds no operation to the ordinary saved-plan apply adapter and never accepts a
caller command, environment, output path or binary plan.
"""
from __future__ import annotations

import uuid

from intune_iac import worker_provider as provider, provider_execution
from intune_iac.io import AppError, canonical, digest

VERSION = 'worker-adoption-provider/1'
PLAN_NAME = 'adoption-initial.plan'
PLAN_PATH = '/job/' + provider.PROJECT + '/' + PLAN_NAME
PLAN_JSON_PATH = '/job/adoption-initial-plan.json'
PLAN_EXIT_PATH = '/job/adoption-initial-plan-exit-code'


def _fail(code):
    raise AppError(code, 'The fixed native adoption payload could not be verified.') from None


def import_command(object_id):
    if type(object_id) is not str:
        _fail('adoption_provider_object_invalid')
    try:
        identity = uuid.UUID(object_id)
    except (ValueError, AttributeError):
        _fail('adoption_provider_object_invalid')
    if identity.int == 0 or str(identity) != object_id:
        _fail('adoption_provider_object_invalid')
    # Exact Atmos 1.230.1 argv retained in native-service-prepare-01.
    return ('/tools/atmos', 'terraform', 'import', 'intune-policy', '-s', 'worker',
            provider_execution.ADDRESS, object_id, '-input=false', '-no-color',
            '--process-functions=false', '--process-templates=false')


def first_plan_command():
    # Existing qualified ordinary-plan flags; the new fixed output basename is
    # private to this evidence operation. It is never used by apply.
    return tuple('-out=' + PLAN_NAME if token == '-out=ordinary.plan' else token
                 for token in provider.native_command('ordinary'))


def show_first_plan_command():
    return ('/tools/atmos', 'terraform', 'show', 'intune-policy', '-s', 'worker',
            '-json', PLAN_PATH, '--process-functions=false', '--process-templates=false')


class NativeAdoptionProviderAdapter:
    def __init__(self, adapter):
        if type(adapter) is not provider.WorkerProviderAdapter:
            _fail('adoption_provider_adapter_required')
        adapter._integrity()
        import_command(adapter.spec.object_id)
        self.provider = adapter
        self._provider_sha256 = digest(adapter.binding())

    def _integrity(self):
        if type(self.provider) is not provider.WorkerProviderAdapter:
            _fail('adoption_provider_changed')
        self.provider._integrity()
        if digest(self.provider.binding()) != self._provider_sha256:
            _fail('adoption_provider_changed')

    def binding(self):
        self._integrity()
        base = self.provider.binding()
        return {**base, 'schema_version': VERSION, 'provider_schema_version': base['schema_version'],
                'adoption_operation': 'native_state_only_import',
                'provider_binding_sha256': self._provider_sha256,
                'tenant_id': self.provider.spec.identity.tenant_id,
                'object_id': self.provider.spec.object_id,
                'resource_address': provider_execution.ADDRESS,
                'import_argv': list(import_command(self.provider.spec.object_id)),
                'first_plan_argv': list(first_plan_command()),
                'show_first_plan_argv': list(show_first_plan_command()),
                'execution_authorized': False, 'graph_mutation_authorized': False,
                'platform_qualified': False}

    def source_files(self):
        self._integrity()
        return {**self.provider.source_files(),
                'adoption-provider-binding.json': canonical(self.binding())}

    def control_files(self, operation, *, credentials):
        self._integrity()
        if operation not in ('import', 'first-plan'):
            _fail('adoption_provider_operation_unsupported')
        from intune_iac.worker_broker import BrokerCredentials
        if type(credentials) is not BrokerCredentials:
            _fail('adoption_provider_credentials_required')
        files = self.provider.control_files('init', credentials=credentials)
        script = files['worker.sh'].decode('utf-8')
        init = provider.native_command('init')
        lines = [line for line in script.splitlines() if line.startswith('env -i ')]
        suffix = ' '.join(init)
        if len(lines) != 1 or not lines[0].endswith(suffix):
            _fail('adoption_provider_initializer_changed')
        environment = lines[0][:-len(suffix)]
        if operation == 'import':
            command = import_command(self.provider.spec.object_id)
            commands = [init, command]
            script += environment + ' '.join(command) + '\n'
        else:
            command, show = first_plan_command(), show_first_plan_command()
            commands = [init, command, show]
            # Retain both exit2 and its exact plan for review. Never relabel an
            # unexpected difference as no-change or execute the generated plan.
            script += ('set +e\n' + environment + ' '.join(command) + '\n'
                       'adoption_plan_code=$?\nset -e\n'
                       'printf "%s\\n" "$adoption_plan_code" > ' + PLAN_EXIT_PATH + '\n'
                       'case "$adoption_plan_code" in 0|2) ;; *) exit "$adoption_plan_code";; esac\n'
                       + environment + ' '.join(show) + ' > ' + PLAN_JSON_PATH + '\n'
                       'exit "$adoption_plan_code"\n')
        files['worker.sh'] = script.encode('utf-8')
        files['operation.json'] = canonical({'schema_version': VERSION,
            'operation': operation, 'commands': [list(value) for value in commands],
            'binding_sha256': digest(self.binding()),
            'credential_placeholder_binding_sha256': credentials.execution_binding_sha256,
            'graph_mutation_authorized': False, 'execution_authorized': False,
            'state_content_write_requested': operation == 'import',
            'no_change_claimed': False,
            'artifacts': [] if operation == 'import' else [PLAN_PATH, PLAN_JSON_PATH, PLAN_EXIT_PATH]})
        return files
