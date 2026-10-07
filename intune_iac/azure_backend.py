"""Closed Azure backend admission and state evidence for the protected worker.

This module performs no network IO or subprocess dispatch and grants no write
authority. Configuration, observed state and authentication are separate inputs.
The original network-denied provider executor and identity/lease contracts are
unchanged. Native state locking belongs to OpenTofu; operation coordination uses
a different existing blob and never claims to fence Microsoft Graph writers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import re
import stat

from . import identity_binding as ib
from .io import AppError, canonical, digest, parse_json

_MAX_BYTES = 16 * 1024 * 1024
_GUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
_HASH = re.compile(r'^[0-9a-f]{64}$')
_RESOURCE = re.compile(r'^/subscriptions/([0-9a-f-]{36})/resourceGroups/([A-Za-z0-9_().-]{1,90})/providers/Microsoft.Storage/storageAccounts/([a-z0-9]{3,24})$')
_ETAG = re.compile(r'^"[\x21\x23-\x7e]{1,256}"$')
_EMPTY_METADATA = frozenset({'access_key', 'sas_token', 'client_secret', 'client_secret_file_path',
    'client_id_file_path', 'client_certificate', 'client_certificate_password', 'client_certificate_path',
    'oidc_token', 'oidc_token_file_path', 'oidc_request_url', 'oidc_request_token',
    'ado_service_connection_id', 'endpoint', 'metadata_host', 'msi_endpoint',
    'customer_provided_key', 'encryption_scope'})


def _fail(code):
    raise AppError(code, 'The closed Azure backend contract could not be verified.') from None


def _guid(value):
    return type(value) is str and _GUID.fullmatch(value) is not None


def _blob_key(value):
    return (type(value) is str and 1 <= len(value) <= 512 and
            all(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', part) is not None
                and part not in ('.', '..') for part in value.split('/')))


@dataclass(frozen=True)
class AzureBackendSpec:
    """A declaration, not an authenticated capability or permission grant."""
    identity: ib.IdentitySpec
    backend: ib.BackendSpec
    coordination_key: str

    def __post_init__(self):
        identity, backend = self.identity, self.backend
        if type(identity) is not ib.IdentitySpec or type(backend) is not ib.BackendSpec:
            _fail('azure_backend_spec_invalid')
        resource = _RESOURCE.fullmatch(backend.storage_account_resource_id) if type(backend.storage_account_resource_id) is str else None
        if (identity.auth_method != 'client_secret' or
                not all(_guid(value) for value in (identity.tenant_id, identity.client_id, identity.principal_object_id,
                                                   backend.subscription_id, backend.state_lineage)) or
                not resource or resource[1] != backend.subscription_id or
                backend.blob_endpoint != 'https://' + resource[3] + '.blob.core.windows.net' or
                type(backend.container) is not str or not 3 <= len(backend.container) <= 63 or
                re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', backend.container) is None or
                backend.workspace != 'default' or not _blob_key(backend.key) or
                not _blob_key(self.coordination_key) or self.coordination_key == backend.key or
                type(backend.state_serial) is not int or not 0 <= backend.state_serial <= 9007199254740991 or
                type(backend.state_sha256) is not str or not _HASH.fullmatch(backend.state_sha256)):
            _fail('azure_backend_spec_invalid')


@dataclass(frozen=True)
class StateRevision:
    """Parsed bytes and revision facts; caller must establish service authenticity."""
    lineage: str
    serial: int
    sha256: str
    semantic_sha256: str
    etag: str
    bytes: int

    def __post_init__(self):
        if (not _guid(self.lineage) or type(self.serial) is not int or not 0 <= self.serial <= 9007199254740991 or
                any(type(value) is not str or not _HASH.fullmatch(value) for value in (self.sha256, self.semantic_sha256)) or
                type(self.etag) is not str or not _ETAG.fullmatch(self.etag) or
                type(self.bytes) is not int or not 0 < self.bytes <= _MAX_BYTES):
            _fail('azure_backend_state_invalid')

    @classmethod
    def observe(cls, raw, *, etag):
        if type(raw) is not bytes or not 0 < len(raw) <= _MAX_BYTES:
            _fail('azure_backend_state_invalid')
        try:
            state = parse_json(raw)
            if (type(state) is not dict or type(state.get('version')) is not int or state['version'] != 4 or
                    type(state.get('resources')) is not list):
                _fail('azure_backend_state_invalid')
            return cls(state.get('lineage'), state.get('serial'), hashlib.sha256(raw).hexdigest(),
                       digest(state), etag, len(raw))
        except (AppError, ValueError, TypeError):
            _fail('azure_backend_state_invalid')


def verify_transition(before, after):
    """Check state evolution only; never conclude that a plan or Graph write ran."""
    if type(before) is not StateRevision or type(after) is not StateRevision:
        _fail('azure_backend_state_invalid')
    if after.lineage != before.lineage: _fail('azure_backend_state_lineage_changed')
    if after.serial < before.serial: _fail('azure_backend_state_serial_regressed')
    if after.serial == before.serial and after.sha256 != before.sha256:
        _fail('azure_backend_state_same_serial_changed')
    if after.sha256 != before.sha256 and after.etag == before.etag:
        _fail('azure_backend_state_etag_reused')
    return {'schema_version': 'azure-backend-state-transition/1.0',
            'state_change': 'unchanged' if after.sha256 == before.sha256 else 'advanced',
            'before': asdict(before), 'after': asdict(after),
            'execution_confirmed': False, 'service_convergence_confirmed': False,
            'authentication': 'not_established_by_state_bytes'}


def _safe(path):
    if not isinstance(path, (str, Path)):
        _fail('azure_backend_private_path_required')
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        _fail('azure_backend_private_path_required')
    return path


def _private_directory(path):
    path = _safe(path)
    try:
        info = path.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            _fail('azure_backend_private_path_required')
    except OSError:
        _fail('azure_backend_private_path_required')
    return path


def _directory_fd(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(descriptor)
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        os.close(descriptor); _fail('azure_backend_private_path_required')
    return descriptor


class BackendCredentialEnvironment:
    """Process-held secret material; never serialize, log or merge ambient env."""
    def __init__(self, adapter, binding, credential):
        if type(binding) not in (ib.LiveIdentityBinding, ib.LaboratoryIdentityBinding):
            _fail('azure_backend_identity_required')
        identity, backend = binding.backend_configuration(credential)
        if identity != adapter.spec.identity or backend != adapter.spec.backend:
            _fail('azure_backend_identity_mismatch')
        self._adapter, self._binding, self._credential = adapter, binding, credential
        self._closed = False

    def __repr__(self): return '<BackendCredentialEnvironment redacted>'
    def __reduce_ex__(self, protocol): raise TypeError('Backend credentials cannot be serialized.')

    def environment(self):
        if self._closed: _fail('azure_backend_credentials_closed')
        identity, backend = self._binding.backend_configuration(self._credential)
        if identity != self._adapter.spec.identity or backend != self._adapter.spec.backend:
            _fail('azure_backend_identity_mismatch')
        return {'ARM_TENANT_ID': identity.tenant_id, 'ARM_CLIENT_ID': identity.client_id,
                'ARM_CLIENT_SECRET': self._credential._get(), 'ARM_SUBSCRIPTION_ID': backend.subscription_id,
                'ARM_ENVIRONMENT': 'public', 'ARM_USE_AZUREAD': 'true', 'ARM_USE_CLI': 'false',
                'ARM_USE_MSI': 'false', 'ARM_USE_OIDC': 'false', 'ARM_USE_AKS_WORKLOAD_IDENTITY': 'false'}

    def close(self): self._closed = True
    def __enter__(self):
        self.environment()
        return self
    def __exit__(self, *ignored): self.close()


class AzureBackendAdapter:
    def __init__(self, spec):
        if type(spec) is not AzureBackendSpec: _fail('azure_backend_spec_invalid')
        self.spec = spec

    def configuration(self):
        resource = _RESOURCE.fullmatch(self.spec.backend.storage_account_resource_id)
        return {'storage_account_name': resource[3], 'resource_group_name': resource[2],
                'container_name': self.spec.backend.container, 'key': self.spec.backend.key,
                'subscription_id': self.spec.backend.subscription_id,
                'tenant_id': self.spec.identity.tenant_id, 'client_id': self.spec.identity.client_id,
                'environment': 'public', 'use_azuread_auth': True, 'use_cli': False,
                'use_msi': False, 'use_oidc': False, 'use_aks_workload_identity': False,
                'snapshot': False, 'timeout_seconds': 10}

    def binding(self):
        return {'schema_version': 'azure-backend-binding/1.0',
                'profile': 'linux_opentofu_1.13.1_public_existing_default_workspace',
                'configuration_sha256': digest(self.configuration()), 'spec_sha256': digest(asdict(self.spec)),
                'identity': asdict(self.spec.identity), 'backend': asdict(self.spec.backend),
                'state_blob': self.spec.backend.blob_endpoint + '/' + self.spec.backend.container + '/' + self.spec.backend.key,
                'coordination_blob': self.spec.backend.blob_endpoint + '/' + self.spec.backend.container + '/' + self.spec.coordination_key,
                'native_state_lock_owner': 'opentofu_azurerm_backend',
                'coordination_lease_owner': 'protected_execution_service',
                'graph_fencing': False, 'execution_authorized': False,
                'required_before_init': 'authenticated_existing_state_and_coordination_blob_read',
                'platform_qualified': False}

    def credential_environment(self, binding, credential):
        return BackendCredentialEnvironment(self, binding, credential)

    def verify_precondition(self, observed, *, expected_etag):
        if type(observed) is not StateRevision or type(expected_etag) is not str or not _ETAG.fullmatch(expected_etag):
            _fail('azure_backend_state_invalid')
        expected = self.spec.backend
        if ((observed.lineage, observed.serial, observed.sha256, observed.etag) !=
                (expected.state_lineage, expected.state_serial, expected.state_sha256, expected_etag)):
            _fail('azure_backend_state_changed')
        return {'schema_version': 'azure-backend-precondition/1.0', 'status': 'matched',
                'revision': asdict(observed), 'backend_sha256': digest(asdict(expected)),
                'execution_authorized': False}

    def verify_metadata(self, document, *, workspace):
        """Verify actual .terraform/terraform.tfstate metadata, not its filename.

        Native metadata defaults may be absent/null/empty; nonempty secret,
        endpoint and alternate-identity fields are rejected without disclosure.
        """
        if type(document) is bytes:
            try: document = parse_json(document)
            except AppError: _fail('azure_backend_metadata_mismatch')
        if (type(document) is not dict or document.get('version') != 3 or
                type(document.get('version')) is not int or workspace != 'default' or
                type(document.get('backend')) is not dict or
                set(document['backend']) != {'type', 'config', 'hash'} or
                document['backend']['type'] != 'azurerm' or type(document['backend']['hash']) is not int):
            _fail('azure_backend_metadata_mismatch')
        actual = document['backend']['config']; expected = self.configuration()
        if type(actual) is not dict or set(actual) - set(expected) - _EMPTY_METADATA:
            _fail('azure_backend_metadata_mismatch')
        for key, value in expected.items():
            if type(actual.get(key)) is not type(value) or actual[key] != value:
                _fail('azure_backend_metadata_mismatch')
        for key in _EMPTY_METADATA & set(actual):
            if actual[key] is not None and not (type(actual[key]) is str and actual[key] == ''):
                _fail('azure_backend_metadata_mismatch')
        return {'schema_version': 'azure-backend-metadata/1.0', 'status': 'matched',
                'configuration_sha256': digest(expected), 'metadata_sha256': digest(document),
                'workspace': workspace, 'authentication': 'not_established_by_metadata'}

    def _artifacts(self):
        artifacts = {
            'backend.tf.json': canonical({'terraform': {'backend': {'azurerm': self.configuration()}}}) + b'\n',
            'backend-binding.json': canonical(self.binding()) + b'\n'}
        manifest = {'schema_version': 'azure-backend-artifacts/1.0', 'spec_sha256': digest(asdict(self.spec)),
                    'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                              for name, data in sorted(artifacts.items())}}
        artifacts['backend-manifest.json'] = canonical(manifest) + b'\n'
        return artifacts

    def publish(self, directory):
        """New private directory only; retain partial/extra files after failures."""
        directory = _safe(directory); parent = _private_directory(directory.parent)
        parent_fd = root_fd = None
        try:
            parent_fd = _directory_fd(parent)
            try: os.mkdir(directory.name, mode=0o700, dir_fd=parent_fd)
            except FileExistsError: _fail('azure_backend_output_exists')
            root_fd = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
            for name, data in self._artifacts().items():
                descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root_fd)
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.fsync(root_fd); os.fsync(parent_fd)
            # Detect a replaced directory before acknowledging the path.
            if os.stat(directory, follow_symlinks=False).st_ino != os.fstat(root_fd).st_ino:
                _fail('azure_backend_publication_incomplete')
        except OSError:
            _fail('azure_backend_publication_incomplete')
        finally:
            if root_fd is not None: os.close(root_fd)
            if parent_fd is not None: os.close(parent_fd)
        return self.verify_published(directory)

    def verify_published(self, directory):
        directory_fd = None
        try:
            directory = _private_directory(directory)
            directory_fd = _directory_fd(directory)
            expected = self._artifacts()
            if set(os.listdir(directory_fd)) != set(expected): _fail('azure_backend_artifact_mismatch')
            for name, data in expected.items():
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
                with os.fdopen(descriptor, 'rb') as stream:
                    info = os.fstat(stream.fileno())
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or
                            info.st_mode & 0o077 or info.st_size != len(data) or stream.read(_MAX_BYTES + 1) != data):
                        _fail('azure_backend_artifact_mismatch')
            return {'schema_version': 'azure-backend-publication/1.0', 'status': 'published',
                    'manifest_sha256': hashlib.sha256(expected['backend-manifest.json']).hexdigest(),
                    'spec_sha256': digest(asdict(self.spec)), 'execution_authorized': False}
        except (OSError, AppError):
            _fail('azure_backend_artifact_mismatch')
        finally:
            if directory_fd is not None: os.close(directory_fd)

    def native_command(self, operation, *, plan_descriptor=None):
        """Closed argv suffixes; dispatch and sealed descriptor ownership are host duties.

        Init can write missing remote state. A worker must verify existing state
        before init and apply an independently enforced endpoint/method policy.
        No migration, unlock, state push, destroy or implicit replacement plan.
        """
        commands = {
            'init': ('init', '-input=false', '-no-color', '-get=false', '-lockfile=readonly', '-lock-timeout=0s'),
            'workspace': ('workspace', 'show'), 'state': ('state', 'pull'),
            'plan': ('plan', '-input=false', '-no-color', '-lock-timeout=0s', '-out=ordinary.plan'),
            'refresh': ('plan', '-refresh-only', '-input=false', '-no-color', '-lock-timeout=0s', '-out=refresh.plan'),
            'readback': ('plan', '-refresh-only', '-input=false', '-no-color', '-lock-timeout=0s', '-out=readback.plan'),
            'second': ('plan', '-input=false', '-no-color', '-lock-timeout=0s', '-out=second.plan')}
        if operation == 'apply':
            if type(plan_descriptor) is not int or not 3 <= plan_descriptor <= 1048576:
                _fail('azure_backend_sealed_plan_required')
            return ('apply', '-input=false', '-no-color', '-lock-timeout=0s', '/proc/self/fd/' + str(plan_descriptor))
        if operation not in commands or plan_descriptor is not None:
            _fail('azure_backend_command_not_admitted')
        return commands[operation]


class NativeStateWriteContract:
    """Closed, fully known existing-resource state projection from a saved plan.

    This validates a generated state PUT; it does not authorize that PUT or
    authenticate the input plan. The controller must bind all input hashes to
    the independently signed manifest. Unknown/computed values, drift, creates,
    deletes, moves, imports, modules and indexed instances are unsupported.
    Metadata/private provider bytes are preserved exactly. No field is ignored.
    """
    def __init__(self, *, baseline_raw, plan_json_raw, saved_plan_sha256, schema_versions):
        if (type(saved_plan_sha256) is not str or not _HASH.fullmatch(saved_plan_sha256) or
                type(schema_versions) is not dict or len(schema_versions) > 32 or
                any(type(k) is not str or not re.fullmatch(r'[a-z][a-z0-9_]{0,127}', k) or
                    type(v) is not int or not 0 <= v <= 100000 for k, v in schema_versions.items())):
            _fail('azure_state_contract_invalid')
        if any(type(v) is not bytes or not 0 < len(v) <= _MAX_BYTES for v in (baseline_raw, plan_json_raw)):
            _fail('azure_state_contract_invalid')
        baseline, plan = parse_json(baseline_raw), parse_json(plan_json_raw)
        StateRevision.observe(baseline_raw, etag='"projection-input-only"')
        if (set(baseline) - {'version', 'terraform_version', 'serial', 'lineage', 'outputs', 'resources', 'check_results'} or
                baseline.get('terraform_version') != '1.13.1' or type(baseline.get('outputs')) is not dict or
                baseline.get('check_results') not in (None, []) or baseline['serial'] >= 9007199254740991 or
                type(plan) is not dict or plan.get('format_version') != '1.2' or plan.get('terraform_version') != '1.13.1' or
                plan.get('errored', False) is not False or plan.get('resource_drift') not in (None, []) or
                plan.get('deferred_changes') not in (None, []) or plan.get('complete', True) is not True or
                type(plan.get('planned_values')) is not dict):
            _fail('azure_state_contract_unsupported')
        expected = parse_json(canonical(baseline)); expected['serial'] += 1
        resources = {}
        for resource in expected['resources']:
            if (type(resource) is not dict or set(resource) != {'mode', 'type', 'name', 'provider', 'instances'} or
                    resource['mode'] != 'managed' or resource['type'] not in schema_versions or
                    type(resource['name']) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,127}', resource['name']) or
                    type(resource['provider']) is not str or not re.fullmatch(r'provider\["[^"\r\n]{1,256}"\]', resource['provider']) or
                    type(resource['instances']) is not list or len(resource['instances']) != 1):
                _fail('azure_state_contract_unsupported')
            instance = resource['instances'][0]
            if (type(instance) is not dict or set(instance) - {'schema_version', 'attributes', 'sensitive_attributes', 'private', 'dependencies'} or
                    instance.get('schema_version') != schema_versions[resource['type']] or
                    type(instance.get('schema_version')) is not int or type(instance.get('attributes')) is not dict or
                    type(instance['attributes'].get('id')) is not str or not instance['attributes']['id']):
                _fail('azure_state_contract_unsupported')
            address = resource['type'] + '.' + resource['name']
            if address in resources: _fail('azure_state_contract_invalid')
            resources[address] = instance
        changes = plan.get('resource_changes', [])
        if type(changes) is not list or len(changes) != len(resources): _fail('azure_state_contract_unsupported')
        seen = set()
        for change in changes:
            if (type(change) is not dict or change.get('address') not in resources or change['address'] in seen or
                    change.get('mode') != 'managed' or change.get('previous_address') is not None or
                    change.get('deposed') is not None or change.get('index') is not None or
                    type(change.get('change')) is not dict):
                _fail('azure_state_contract_unsupported')
            address = change['address']; action = change['change']; instance = resources[address]
            if (action.get('actions') not in (['no-op'], ['update']) or action.get('importing') is not None or
                    not self._known(action.get('after_unknown', {})) or
                    canonical(action.get('before')) != canonical(instance['attributes']) or
                    type(action.get('after')) is not dict or set(action['after']) != set(instance['attributes']) or
                    action['after'].get('id') != instance['attributes']['id']):
                _fail('azure_state_contract_unsupported')
            instance['attributes'] = parse_json(canonical(action['after'])); seen.add(address)
        values = plan['planned_values']; root = values.get('root_module', {})
        if type(root) is not dict or set(root) - {'resources'}: _fail('azure_state_contract_unsupported')
        planned_resources = root.get('resources', [])
        if type(planned_resources) is not list or len(planned_resources) != len(resources): _fail('azure_state_contract_unsupported')
        seen = set()
        for resource in planned_resources:
            if (type(resource) is not dict or resource.get('address') not in resources or resource['address'] in seen or
                    canonical(resource.get('values')) != canonical(resources[resource['address']]['attributes']) or
                    resource.get('schema_version') != resources[resource['address']]['schema_version']):
                _fail('azure_state_contract_unsupported')
            seen.add(resource['address'])
        outputs = values.get('outputs', {}); changes = plan.get('output_changes', {})
        if (type(outputs) is not dict or type(changes) is not dict or set(outputs) != set(expected['outputs']) or
                set(changes) != set(outputs)):
            _fail('azure_state_contract_unsupported')
        for name, output in outputs.items():
            before = expected['outputs'][name]; change = changes[name]
            if (type(output) is not dict or set(output) != {'sensitive', 'type', 'value'} or
                    type(before) is not dict or set(before) - {'sensitive', 'type', 'value'} or
                    type(change) is not dict or change.get('actions') not in (['no-op'], ['update']) or
                    change.get('after_unknown') is not False or
                    canonical(change.get('before')) != canonical(before.get('value')) or
                    canonical(change.get('after')) != canonical(output['value']) or
                    canonical(before.get('type')) != canonical(output['type']) or
                    before.get('sensitive', False) is not output['sensitive']):
                _fail('azure_state_contract_unsupported')
            before['value'] = parse_json(canonical(output['value']))
        self._expected = canonical(expected)
        self._binding = {'schema_version': 'native-state-write-contract/1.0',
            'profile': 'opentofu_1.13.1_existing_root_known_update_only',
            'baseline_sha256': hashlib.sha256(baseline_raw).hexdigest(),
            'plan_json_sha256': hashlib.sha256(plan_json_raw).hexdigest(),
            'saved_plan_sha256': saved_plan_sha256, 'schema_versions': dict(schema_versions),
            'lineage': baseline['lineage'], 'before_serial': baseline['serial'],
            'after_serial': expected['serial'], 'expected_semantic_sha256': hashlib.sha256(self._expected).hexdigest(),
            'resource_addresses': sorted(resources), 'execution_authorized': False,
            'service_freshness_atomic': False}

    @staticmethod
    def _known(value):
        if value is False: return True
        if type(value) is dict: return all(NativeStateWriteContract._known(v) for v in value.values())
        if type(value) is list: return all(NativeStateWriteContract._known(v) for v in value)
        return False

    def binding(self): return parse_json(canonical(self._binding))

    def admit(self, candidate_raw):
        if type(candidate_raw) is not bytes or not 0 < len(candidate_raw) <= _MAX_BYTES:
            _fail('azure_state_write_not_admitted')
        if canonical(parse_json(candidate_raw)) != self._expected: _fail('azure_state_write_not_admitted')
        return {'schema_version': 'native-state-write-admission/1.0', 'status': 'content_matched',
                'contract_sha256': digest(self._binding), 'body_sha256': hashlib.sha256(candidate_raw).hexdigest(),
                'bytes': len(candidate_raw), 'execution_authorized': False, 'service_convergence_confirmed': False}
