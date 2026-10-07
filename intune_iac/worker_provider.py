"""Closed native Atmos payload for the separately protected worker host.

Preparation is neither approval nor an identity capability. No subprocess or
network dispatch happens here. Live credentials are deliberately not serialized;
the host-held broker credential capability remains a separate mandatory gate.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import re

from . import azure_backend, identity_binding, provider_execution as pe
from .io import AppError, canonical, digest, sync_directory
from .native_pins import ATMOS_CURRENT_SHA256

VERSION = 'worker-provider/1'
COMPONENT = 'intune-policy'
STACK = 'worker'
PROJECT = 'components/terraform/' + COMPONENT
PLAN = '/control/approved.plan'
_HASH = re.compile(r'[0-9a-f]{64}')
_GUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
MAX_BYTES = 16 * 1024 * 1024


def _fail(code):
    raise AppError(code, 'The closed native worker payload could not be verified.') from None


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _hash(value):
    return type(value) is str and _HASH.fullmatch(value) is not None


@dataclass(frozen=True)
class ProviderSpec:
    identity: identity_binding.IdentitySpec
    backend: azure_backend.AzureBackendSpec
    object_id: str
    source_revision: str
    source_sha256: str
    admission_sha256: str
    desired: dict

    def __post_init__(self):
        if (type(self.identity) is not identity_binding.IdentitySpec or
                type(self.backend) is not azure_backend.AzureBackendSpec or
                self.identity.auth_method != 'client_secret' or
                any(type(v) is not str or not _GUID.fullmatch(v) for v in
                    (self.identity.tenant_id, self.identity.client_id,
                     self.identity.principal_object_id, self.object_id)) or
                self.identity.tenant_id != self.backend.identity.tenant_id or
                self.identity.client_id == self.backend.identity.client_id or
                self.identity.principal_object_id == self.backend.identity.principal_object_id or
                type(self.source_revision) is not str or not re.fullmatch('[0-9a-f]{40}', self.source_revision) or
                not _hash(self.source_sha256) or not _hash(self.admission_sha256)):
            _fail('worker_provider_spec_invalid')
        # Existing admitted narrow Settings Catalog mapping; no broadened HCL.
        object.__setattr__(self, 'desired', pe._configuration(self.desired))


def native_command(operation):
    """Exact Atmos 1.230.1 route; no caller command/selector/path override.

    --from-plan=PATH did not use the saved plan in the retained native probe.
    The separate --from-plan and --planfile tokens are independently qualified.
    """
    common = ['intune-policy', '-s', 'worker']
    if operation == 'init':
        args = ['init', *common, '-input=false', '-no-color', '-get=false', '-lockfile=readonly', '-lock-timeout=0s']
    elif operation in ('ordinary', 'refresh', 'readback', 'second'):
        args = ['plan', *common, '-input=false', '-no-color', '-lock-timeout=0s',
                '-out=' + operation + '.plan', '-detailed-exitcode', '--init-mode=never']
        if operation in ('refresh', 'readback'): args.append('-refresh-only')
    elif operation == 'apply':
        args = ['apply', *common, '--from-plan', '--planfile', PLAN,
                '-input=false', '-no-color', '-lock-timeout=0s', '--init-mode=never']
    elif operation == 'show':
        args = ['show', *common, '-json', PLAN]
    elif operation == 'workspace':
        args = ['workspace', *common, 'show']
    else:
        _fail('worker_provider_operation_unsupported')
    return tuple(['/tools/atmos', 'terraform', *args,
                  '--process-functions=false', '--process-templates=false'])


class WorkerProviderAdapter:
    def __init__(self, spec, *, lockfile):
        if type(spec) is not ProviderSpec or type(lockfile) is not bytes or not 1 <= len(lockfile) <= 65536:
            _fail('worker_provider_lock_invalid')
        # Native lock contents are not executable HCL configuration; still require
        # a single exact provider/version and deny arbitrary blocks/options.
        try: text = lockfile.decode('utf-8')
        except UnicodeError: _fail('worker_provider_lock_invalid')
        expected = r'provider\s+"registry\.terraform\.io/deploymenttheory/microsoft365"\s*\{\s*version\s*=\s*"1\.0\.0"\s*(?:constraints\s*=\s*"(?:=\s*)?1\.0\.0"\s*)?hashes\s*=\s*\[\s*(?:"(?:h1:[A-Za-z0-9+/=]+|zh:[0-9a-f]{64})"\s*,?\s*)+\]\s*\}\s*'
        clean = re.sub(r'^\s*#.*$', '', text, flags=re.MULTILINE)
        if not re.fullmatch(expected, clean.strip()): _fail('worker_provider_lock_invalid')
        self.spec = ProviderSpec(**{**asdict(spec), 'identity': spec.identity, 'backend': spec.backend})
        self.lockfile = bytes(lockfile)
        self._spec_hash = digest(asdict(self.spec))
        self._lock_sha = _sha(self.lockfile)

    def _integrity(self):
        if digest(asdict(self.spec)) != self._spec_hash or _sha(self.lockfile) != self._lock_sha:
            _fail('worker_provider_input_changed')

    def binding(self):
        self._integrity()
        return {'schema_version': VERSION, 'source_revision': self.spec.source_revision,
            'source_sha256': self.spec.source_sha256, 'admission_sha256': self.spec.admission_sha256,
            'object_id': self.spec.object_id, 'provider_identity': asdict(self.spec.identity),
            'backend': azure_backend.AzureBackendAdapter(self.spec.backend).binding(),
            'effective_input_sha256': digest(self.spec.desired), 'lockfile_sha256': _sha(self.lockfile),
            'pins': {**asdict(pe.PRODUCTION_PINS), 'atmos_sha256': ATMOS_CURRENT_SHA256},
            'execution_authorized': False, 'live_credentials_available': False,
            'platform_qualified': False, 'environment': 'prepared_linux_amd64_worker',
            'required_gates': ['signed_exact_operation_approval', 'authenticated_identity_capability',
                'host_broker_credential_capability', 'active_broker_guard', 'native_backend_lease_qualification',
                'native_provider_service_qualification']}

    def source_files(self):
        self._integrity()
        backend = azure_backend.AzureBackendAdapter(self.spec.backend)
        provider = {'cloud': 'public', 'tenant_id': self.spec.identity.tenant_id,
            'auth_method': 'client_secret', 'entra_id_options': {'client_id': self.spec.identity.client_id,
                'additionally_allowed_tenants': []},
            'client_options': {'enable_headers_inspection': False, 'enable_retry': False,
                'enable_redirect': False, 'enable_compression': False, 'use_proxy': True,
                'proxy_url': 'http://127.0.0.1:18080', 'timeout_seconds': 30},
            'telemetry_optout': True, 'debug_mode': False}
        configuration = {'terraform': {'required_version': '= 1.13.1',
            'required_providers': {'microsoft365': {'source': pe.SOURCE, 'version': '= 1.0.0'}},
            'backend': {'azurerm': backend.configuration()}},
            'provider': {'microsoft365': provider},
            'variable': {'stage': {'type': 'string', 'validation': {'condition': '${var.stage == "worker"}',
                          'error_message': 'Closed worker stack only.'}}},
            'resource': {pe.RESOURCE: {'selected': self.spec.desired}}}
        atmos = ('base_path: .\ncomponents:\n  terraform:\n    base_path: components/terraform\n'
            '    command: /tools/tofu\n    auto_generate_backend_file: false\n'
            '    apply_auto_approve: false\n    init:\n      mode: never\nstacks:\n  base_path: stacks\n'
            '  included_paths: [worker]\n  name_pattern: "{stage}"\n').encode()
        stack = ('vars:\n  stage: worker\ncomponents:\n  terraform:\n    intune-policy:\n'
                 '      metadata:\n        terraform_workspace: default\n      vars: {}\n').encode()
        return {'project/atmos.yaml': atmos, 'project/stacks/worker.yaml': stack,
            'project/' + PROJECT + '/main.tf.json': canonical(configuration),
            'project/' + PROJECT + '/.terraform.lock.hcl': self.lockfile,
            'provider-binding.json': canonical(self.binding())}

    def control_files(self, operation, *, saved_plan=None, credentials=None):
        self._integrity()
        command = native_command(operation)
        if operation in ('apply', 'show'):
            if type(saved_plan) is not bytes or not 1 <= len(saved_plan) <= MAX_BYTES:
                _fail('worker_provider_saved_plan_required')
        elif saved_plan is not None: _fail('worker_provider_unexpected_plan')
        placeholders = {}
        if credentials is not None:
            from .worker_broker import BrokerCredentials
            if type(credentials) is not BrokerCredentials:
                _fail('worker_provider_credential_capability')
            expected_binding = identity_binding.BindingConfig(
                self.spec.identity, self.spec.backend.identity, self.spec.backend.backend)
            if credentials.binding.evidence()['configuration_sha256'] != digest(asdict(expected_binding)):
                _fail('worker_provider_credential_capability')
            placeholders = credentials.worker_environment()
            expected = {'M365_TENANT_ID': self.spec.identity.tenant_id, 'M365_CLIENT_ID': self.spec.identity.client_id,
                'M365_AUTH_METHOD': 'client_secret', 'ARM_TENANT_ID': self.spec.backend.identity.tenant_id,
                'ARM_CLIENT_ID': self.spec.backend.identity.client_id, 'ARM_SUBSCRIPTION_ID': self.spec.backend.backend.subscription_id,
                'ARM_ENVIRONMENT': 'public', 'ARM_USE_AZUREAD': 'true', 'ARM_USE_CLI': 'false',
                'ARM_USE_MSI': 'false', 'ARM_USE_OIDC': 'false', 'ARM_USE_AKS_WORKLOAD_IDENTITY': 'false'}
            if (set(placeholders) != set(expected) | {'M365_CLIENT_SECRET', 'ARM_CLIENT_SECRET'} or
                    any(placeholders.get(k) != v for k, v in expected.items()) or
                    any(placeholders.get(key) != 'intune-worker-placeholder-' + credentials.execution_binding_sha256 + '-' + role
                        for key, role in [('M365_CLIENT_SECRET', 'provider'), ('ARM_CLIENT_SECRET', 'backend')])):
                _fail('worker_provider_credential_capability')
        # All words are constants or UUID/hash placeholders admitted above; no
        # real secret or caller shell fragment enters this control payload.
        script = '#!/bin/sh\nset -eu\numask 077\ncp -R /source/project/. /job/\n'
        mirror = '/job/mirror/' + pe.SOURCE + '/1.0.0/linux_amd64'
        script += 'mkdir -p /job/home ' + mirror + '\n'
        script += 'ln -s /tools/provider ' + mirror + '/terraform-provider-microsoft365_v1.0.0\n'
        script += ('cd /job\n[ ! -e /job/relay.ready ] && [ ! -L /job/relay.ready ] || exit 70\n/tools/relay &\nrelay_pid=$!\n'
            'cleanup() { primary=$?; trap - EXIT INT TERM; cleanup_code=0; '
            'kill "$relay_pid" 2>/dev/null || cleanup_code=95; '
            'wait "$relay_pid" 2>/dev/null || true; '
            'if [ "$primary" -ne 0 ]; then exit "$primary"; fi; exit "$cleanup_code"; }\n'
            "trap cleanup EXIT\ntrap 'exit 130' INT\ntrap 'exit 143' TERM\n"
            'ready_attempt=0\nwhile [ ! -f /job/relay.ready ]; do\n'
            '  kill -0 "$relay_pid" 2>/dev/null || exit 70\n'
            '  ready_attempt=$((ready_attempt + 1))\n'
            '  [ "$ready_attempt" -le 100 ] || exit 70\n  sleep 0.01\ndone\n'
            '[ "$(cat /job/relay.ready)" = READY ] || exit 70\n')
        if saved_plan is not None:
            script += 'printf "%s  %s\\n" ' + _sha(saved_plan) + ' /control/approved.plan | sha256sum -c - >/dev/null\n'
        # Credentials cannot enter this payload. A reviewed host capability is a
        # prerequisite for activating live execution, never a free env map.
        script += ('env -i HOME=/job/home PATH=/usr/bin:/bin LANG=C.UTF-8 '
                   'ATMOS_CLI_CONFIG_PATH=/job ATMOS_VERSION_CHECK_ENABLED=false ATMOS_TELEMETRY_ENABLED=false '
                   'CHECKPOINT_DISABLE=1 TF_IN_AUTOMATION=1 TF_INPUT=0 TF_CLI_CONFIG_FILE=/control/tofu.rc '
                   'HTTP_PROXY=http://127.0.0.1:18080 HTTPS_PROXY=http://127.0.0.1:18080 NO_PROXY= '
                   'SSL_CERT_FILE=/control/broker-ca.pem ' +
                   ''.join(key + '=' + placeholders[key] + ' ' for key in sorted(placeholders)) +
                   ' '.join(command) + '\n')
        rc = ('provider_installation { filesystem_mirror { path = "/job/mirror" include = ["' + pe.SOURCE + '"] } }\ndisable_checkpoint = true\n').encode()
        files = {'worker.sh': script.encode(), 'tofu.rc': rc,
                 'operation.json': canonical({'schema_version': VERSION, 'operation': operation,
                    'argv': list(command), 'binding_sha256': digest(self.binding()),
                    'saved_plan_sha256': _sha(saved_plan) if saved_plan is not None else None,
                    'execution_authorized': False,
                    'credential_placeholder_binding_sha256': credentials.execution_binding_sha256 if credentials is not None else None})}
        if saved_plan is not None: files['approved.plan'] = saved_plan
        return files


def publish_files(directory, files):
    """New private directory only; retain failed partial publication verbatim."""
    root = Path(directory).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)) or '..' in root.parts:
        _fail('worker_provider_unsafe_path')
    if (type(files) is not dict or not files or len(files) > 32 or
            any(type(name) is not str or not name or name.startswith('/') or '\\' in name or
                any(p in ('', '.', '..') or not re.fullmatch(r'[A-Za-z0-9_.-]{1,255}', p) for p in name.split('/')) or type(raw) is not bytes
                or len(raw) > MAX_BYTES for name, raw in files.items())):
        _fail('worker_provider_artifact_invalid')
    try: root.mkdir(mode=0o700)
    except FileExistsError: _fail('worker_provider_output_exists')
    for name, raw in sorted(files.items()):
        target = root / name; target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        sync_directory(target.parent)
    sync_directory(root)
    return {'files': {name: {'sha256': _sha(raw), 'bytes': len(raw)} for name, raw in sorted(files.items())},
            'execution_authorized': False}
