"""Closed native Settings Catalog execution, with durable uncertain-outcome handling.

This adapter owns a generated, single-resource, local-state directory. It does
not execute a repository, accept backend/HCL/command options, authenticate a
principal, or grant approval. The host supplies credentials and an independently
authenticated, one-shot authorization context. Local fixture qualification is
separate from live service qualification; neither is inferred from this API.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time
import uuid
import zipfile

from .io import AppError, canonical, digest, load_json, parse_json, write_json
from .production import RESOURCE, _setting, _uuid
from .native_pins import OPENTOFU_CURRENT_SHA256, OPENTOFU_PINS

SOURCE = 'registry.terraform.io/deploymenttheory/microsoft365'
ADDRESS = RESOURCE + '.selected'
VERSION = '1.0.0'
MAX_BYTES = 16 * 1024 * 1024
MAX_BINARY = 1024 * 1024 * 1024
HASH = re.compile(r'^[0-9a-f]{64}$')
ATTRIBUTES = frozenset({'name', 'description', 'platforms', 'technologies',
                        'role_scope_tag_ids', 'settings', 'assignments'})
COMPUTED = frozenset({'id', 'created_date_time', 'last_modified_date_time',
                     'is_assigned', 'settings_count', 'settings_catalog_template_type', 'timeouts'})


@dataclass(frozen=True)
class ProviderPins:
    tofu_sha256: str
    provider_sha256: str
    selected_schema_sha256: str
    source_revision: str
    engine_version: str


PRODUCTION_PINS = ProviderPins(
    OPENTOFU_CURRENT_SHA256,
    # Exact unpublished epoch build; build success does not qualify provider RPC.
    '415097131c64a47c8435ce9528d050382996cfa4bed38d0960548f160a0b0dd3',
    'e081e5bf4c7e8ea2c599ef1c65c73bb525a8f9a2d98b66baed6cc1243a91aef3',
    '1718c946b3ae111bb44c7c1d925b3e35b708cb0a',
    '1.13.1')


def _fail(code):
    raise AppError(code, 'Bounded provider execution could not be verified.')


def _admitted_engine_version(value):
    if type(value) is not str or value not in {p['version'] for p in OPENTOFU_PINS.values()}:
        _fail('provider_engine_version')
    return value


def _engine_version(pins, *, laboratory):
    """Bind a version to immutable pins; legacy versions require explicit labs."""
    if (type(laboratory) is not bool or type(pins) is not dict or
            set(pins) != {'tofu_sha256','provider_sha256','selected_schema_sha256','source_revision','engine_version'} or
            any(type(pins[key]) is not str or not HASH.fullmatch(pins[key])
                for key in ('tofu_sha256','provider_sha256','selected_schema_sha256')) or
            type(pins['source_revision']) is not str or not 1 <= len(pins['source_revision']) <= 512):
        _fail('provider_toolchain_pin')
    version = _admitted_engine_version(pins['engine_version'])
    known = OPENTOFU_PINS.get(pins['tofu_sha256'])
    if known is not None and known['version'] != version:
        _fail('provider_engine_pin_mismatch')
    if not laboratory and (pins != asdict(PRODUCTION_PINS) or pins['tofu_sha256'] != OPENTOFU_CURRENT_SHA256 or
                           version != OPENTOFU_PINS[OPENTOFU_CURRENT_SHA256]['version']):
        _fail('provider_toolchain_pin')
    return version


def _safe(path):
    path = Path(path).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        _fail('provider_unsafe_path')
    return path


def _sha(path, maximum=MAX_BYTES):
    path = _safe(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            _fail('provider_invalid_file')
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _snapshot(value):
    data = canonical(value)
    if len(data) > MAX_BYTES:
        _fail('provider_document_limit')
    return parse_json(data)


def _implementation():
    directory = Path(__file__).resolve().parent
    return {name: _sha(directory / name) for name in
            ('provider_execution.py', 'approval_authority.py', 'io.py', 'production.py', 'protected.py', 'native_pins.py')}


def _sealed_plan(path, expected):
    """Snapshot exact approved bytes in a write-sealed Linux anonymous file."""
    if type(expected) is not str or not HASH.fullmatch(expected): _fail('provider_unbound_plan')
    source_fd = os.open(_safe(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(source_fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
            _fail('provider_invalid_plan_file')
        data = source.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != expected:
        _fail('provider_plan_changed')
    descriptor = None
    try:
        descriptor = os.memfd_create('intune-approved-plan', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        with os.fdopen(os.dup(descriptor), 'wb') as destination:
            destination.write(data); destination.flush()
        # Linux UAPI values (linux/fcntl.h): some Python builds omit these
        # symbolic constants even though memfd and kernel sealing are available.
        seals = 0x0008 | 0x0004 | 0x0002 | 0x0001
        fcntl.fcntl(descriptor, 1033, seals)  # F_ADD_SEALS
        if fcntl.fcntl(descriptor, 1034) & seals != seals:  # F_GET_SEALS
            _fail('provider_immutable_plan_unavailable')
        os.lseek(descriptor, 0, os.SEEK_SET)
        result, descriptor = descriptor, None
        return result
    except (AttributeError, OSError):
        _fail('provider_immutable_plan_unavailable')
    finally:
        if descriptor is not None: os.close(descriptor)


def _literal(value):
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict): pending.extend(item.values())
        elif isinstance(item, list): pending.extend(item)
        elif isinstance(item, str) and ('${' in item or '%{' in item or '\x00' in item):
            _fail('provider_nonliteral_configuration')


def _configuration(value):
    value = _snapshot(value)
    if type(value) is not dict or set(value) != ATTRIBUTES:
        _fail('provider_configuration_shape')
    _literal(value)
    if not isinstance(value['name'], str) or not 1 <= len(value['name']) <= 512:
        _fail('provider_configuration_shape')
    if value['description'] is not None and (not isinstance(value['description'], str) or len(value['description']) > 1500):
        _fail('provider_configuration_shape')
    if value['platforms'] != 'windows10' or value['technologies'] != ['mdm']:
        _fail('provider_configuration_scope')
    tags = value['role_scope_tag_ids']
    if type(tags) is not list or not tags or any(type(x) is not str or not re.fullmatch(r'[0-9]{1,12}', x) for x in tags) or len(set(tags)) != len(tags):
        _fail('provider_scope_tags')
    settings = value['settings']
    if isinstance(settings, str): settings = parse_json(settings)
    if type(settings) is not dict or set(settings) != {'settings'} or type(settings['settings']) is not list or not 1 <= len(settings['settings']) <= 100:
        _fail('provider_settings_scope')
    if not all(_setting(row) for row in settings['settings']) or len({row['id'] for row in settings['settings']}) != len(settings['settings']):
        _fail('provider_settings_scope')
    _literal(settings)
    value['settings'] = canonical(settings).decode()
    assignments = value['assignments']
    if type(assignments) is not list or len(assignments) > 100:
        _fail('provider_assignments_scope')
    normalized = []
    for row in assignments:
        if type(row) is not dict or set(row) - {'type', 'group_id', 'filter_id', 'filter_type'} or not {'type', 'group_id'} <= set(row):
            _fail('provider_assignment_shape')
        if row['type'] not in ('groupAssignmentTarget', 'exclusionGroupAssignmentTarget') or not _uuid(row['group_id']):
            _fail('provider_assignment_identity')
        mode = row.get('filter_type', 'none'); fid = row.get('filter_id')
        if mode not in ('none', 'include', 'exclude') or (row['type'] == 'exclusionGroupAssignmentTarget' and mode != 'none'):
            _fail('provider_assignment_filter')
        if mode == 'none':
            if fid not in (None, '00000000-0000-0000-0000-000000000000'):
                _fail('provider_assignment_filter')
            fid = '00000000-0000-0000-0000-000000000000'
        elif not _uuid(fid): _fail('provider_assignment_filter')
        normalized.append({'type': row['type'], 'group_id': row['group_id'], 'filter_id': fid, 'filter_type': mode})
    if len({canonical(row) for row in normalized}) != len(normalized):
        _fail('provider_duplicate_assignment')
    value['assignments'] = sorted(normalized, key=canonical)
    value['role_scope_tag_ids'] = sorted(tags)
    return value


def _resource_values(document, key='values', *, engine_version):
    if type(document) is not dict or document.get('terraform_version') != _admitted_engine_version(engine_version):
        _fail('provider_output_version')
    values = document.get(key, {})
    if type(values) is not dict or set(values) - {'root_module'}:
        _fail('provider_unexpected_outputs')
    root = values.get('root_module', {})
    if type(root) is not dict or set(root) != {'resources'} or type(root['resources']) is not list or len(root['resources']) != 1:
        _fail('provider_resource_denominator')
    row = root['resources'][0]
    if any(row.get(k) != v for k, v in {'address': ADDRESS, 'mode': 'managed', 'type': RESOURCE,
                                      'name': 'selected', 'provider_name': SOURCE, 'schema_version': 0}.items()) or any(k in row for k in ('index', 'deposed', 'module_address')):
        _fail('provider_resource_identity')
    return row.get('values')


def _observe(values, object_id):
    if type(values) is not dict or values.get('id') != object_id or set(values) - ATTRIBUTES - COMPUTED or not ATTRIBUTES <= set(values):
        _fail('provider_readback_identity')
    return _configuration({key: values[key] for key in ATTRIBUTES})


def _raw_state(path, object_id):
    state = load_json(_safe(path))
    if type(state) is not dict or state.get('version') != 4 or not _uuid(state.get('lineage')) or type(state.get('serial')) is not int or state['serial'] < 0 or state.get('outputs', {}) != {}:
        _fail('provider_state_header')
    rows = state.get('resources')
    if type(rows) is not list or len(rows) != 1:
        _fail('provider_state_denominator')
    row = rows[0]
    if set(row) - {'mode', 'type', 'name', 'provider', 'instances'} or any(row.get(k) != v for k, v in {'mode': 'managed', 'type': RESOURCE, 'name': 'selected', 'provider': 'provider["' + SOURCE + '"]'}.items()):
        _fail('provider_state_identity')
    instances = row.get('instances')
    if type(instances) is not list or len(instances) != 1 or instances[0].get('schema_version') != 0 or any(k in instances[0] for k in ('index_key', 'deposed', 'status')):
        _fail('provider_state_identity')
    return {'lineage': state['lineage'], 'serial': state['serial'], 'sha256': _sha(path),
            'observed': _observe(instances[0].get('attributes'), object_id)}


def _saved_snapshot(path, object_id):
    with zipfile.ZipFile(_safe(path)) as archive:
        rows = [row for row in archive.infolist() if row.filename == 'tfstate']
        if len(rows) != 1 or not 0 < rows[0].file_size <= MAX_BYTES:
            _fail('provider_saved_snapshot_missing')
        document = parse_json(archive.read(rows[0]))
    rows = document.get('resources', [])
    if len(rows) != 1 or rows[0].get('type') != RESOURCE or rows[0].get('name') != 'selected' or rows[0].get('mode') != 'managed' or rows[0].get('module') is not None:
        _fail('provider_saved_snapshot_identity')
    instances = rows[0].get('instances', [])
    if len(instances) != 1 or instances[0].get('schema_version') != 0 or any(k in instances[0] for k in ('deposed', 'index_key')):
        _fail('provider_saved_snapshot_identity')
    return _observe(instances[0].get('attributes'), object_id)


def _contains_true(value):
    if type(value) is bool: return value
    if type(value) is dict: return any(_contains_true(v) for v in value.values())
    if type(value) is list: return any(_contains_true(v) for v in value)
    _fail('provider_invalid_mask')


def _drift(document, object_id, observed):
    rows = document.get('resource_drift', [])
    if type(rows) is not list or len(rows) > 1: _fail('provider_drift_denominator')
    for row in rows:
        if any(row.get(k) != v for k, v in {'address': ADDRESS, 'mode': 'managed', 'type': RESOURCE,
                'name': 'selected', 'provider_name': SOURCE}.items()) or any(k in row for k in ('index', 'deposed', 'previous_address', 'module_address')):
            _fail('provider_drift_identity')
        change = row.get('change', {})
        if change.get('actions') not in (['update'], ['no-op']) or change.get('importing') or change.get('replace_paths'):
            _fail('provider_drift_effect')
        _observe(change.get('before'), object_id)
        if _observe(change.get('after'), object_id) != observed:
            _fail('provider_drift_observation_mismatch')


def _plan(document, object_id, desired, baseline=None, *, engine_version, no_change=False, refresh=False, allow_drift=False):
    if type(document) is not dict or document.get('terraform_version') != _admitted_engine_version(engine_version) or document.get('format_version') != '1.2' or document.get('errored') is not False:
        _fail('provider_plan_header')
    if 'prior_state' in document and (type(document['prior_state']) is not dict or
            document['prior_state'].get('terraform_version') != engine_version):
        _fail('provider_output_version')
    if document.get('output_changes') or document.get('deferred_changes') or (document.get('resource_drift') and not (refresh or allow_drift)) or document.get('checks') or document.get('complete') is False:
        _fail('provider_plan_unreviewed_effect')
    changes = document.get('resource_changes', [])
    if refresh:
        if changes: _fail('provider_refresh_effect')
        actual = _observe(_resource_values(document['prior_state'], engine_version=engine_version), object_id)
        _drift(document, object_id, actual)
        if baseline is not None and actual != baseline: _fail('provider_observation_changed')
        return actual
    if type(changes) is not list or len(changes) != 1:
        _fail('provider_plan_denominator')
    row = changes[0]
    if any(row.get(k) != v for k, v in {'address': ADDRESS, 'mode': 'managed', 'type': RESOURCE, 'name': 'selected', 'provider_name': SOURCE}.items()) or any(k in row for k in ('index', 'deposed', 'previous_address', 'module_address')):
        _fail('provider_plan_identity')
    change = row.get('change', {})
    if change.get('actions') not in ([['no-op']] if no_change else [['no-op'], ['update']]) or change.get('importing') is not None or change.get('replace_paths') or change.get('generated_config'):
        _fail('provider_plan_destructive_or_unexpected')
    unknown = change.get('after_unknown', {})
    # These two fields are computed-only without UseStateForUnknown in the
    # pinned schema. Every desired attribute and immutable ID must be known.
    if type(unknown) is not dict or set(k for k, v in unknown.items() if _contains_true(v)) - {'last_modified_date_time', 'settings_count'}:
        _fail('provider_unknown_planned_value')
    if _contains_true(change.get('before_sensitive', {})) or _contains_true(change.get('after_sensitive', {})):
        _fail('provider_sensitive_plan')
    before = _observe(change.get('before'), object_id)
    after = _observe(change.get('after'), object_id)
    if baseline is not None and before != baseline: _fail('provider_observation_changed')
    if after != desired or _observe(_resource_values(document, 'planned_values', engine_version=engine_version), object_id) != desired:
        _fail('provider_plan_preservation_mismatch')
    if no_change and before != desired: _fail('provider_false_noop')
    if allow_drift: _drift(document, object_id, after)
    return change['actions'][0]


def _copy_pin(source, destination, expected):
    source = _safe(source)
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as inp:
        info = os.fstat(inp.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BINARY:
            _fail('provider_invalid_binary')
        hasher = hashlib.sha256()
        with destination.open('xb') as out:
            while block := inp.read(1024 * 1024): hasher.update(block); out.write(block)
            out.flush(); os.fsync(out.fileno())
        if hasher.hexdigest() != expected:
            destination.unlink(); _fail('provider_binary_pin_mismatch')
    destination.chmod(0o500)


def create_provider_executor(root, *, tofu, provider, initial_configuration, admitted_configuration,
                             object_id, source_sha256, admission_sha256, target_sha256,
                             credential_environment=None):
    """Create the exact production-candidate adapter; no caller-selectable pins."""
    return _create(root, tofu=tofu, provider=provider, initial_configuration=initial_configuration,
                   admitted_configuration=admitted_configuration, object_id=object_id,
                   source_sha256=source_sha256, admission_sha256=admission_sha256,
                   target_sha256=target_sha256, credential_environment=credential_environment,
                   pins=PRODUCTION_PINS, laboratory=False)


def create_laboratory_executor(root, *, pins, **kwargs):
    """Explicit lab-only binary pin injection; can never report production assurance."""
    return _create(root, pins=pins, laboratory=True, **kwargs)


def _create(root, *, tofu, provider, initial_configuration, admitted_configuration, object_id,
            source_sha256, admission_sha256, target_sha256, credential_environment=None, pins, laboratory):
    initial = _configuration(initial_configuration); desired = _configuration(admitted_configuration)
    if not _uuid(object_id) or not all(type(v) is str and HASH.fullmatch(v) for v in (source_sha256, admission_sha256, target_sha256)) or type(pins) is not ProviderPins:
        _fail('provider_admission_binding')
    engine_version = _engine_version(asdict(pins), laboratory=laboratory)
    root = _safe(root); root.mkdir(mode=0o700, parents=False, exist_ok=False)
    (root / 'work').mkdir(mode=0o700); (root / 'home').mkdir(mode=0o700)
    binary = root / 'mirror' / SOURCE / VERSION / 'linux_amd64' / 'terraform-provider-microsoft365_v1.0.0'
    binary.parent.mkdir(mode=0o700, parents=True)
    _copy_pin(tofu, root / 'tofu', pins.tofu_sha256)
    _copy_pin(provider, binary, pins.provider_sha256)
    config = {'terraform': {'required_version': '= ' + engine_version, 'required_providers': {'microsoft365': {'source': SOURCE, 'version': '= ' + VERSION}}},
              'provider': {'microsoft365': {} if laboratory else {'cloud': 'public'}},
              'resource': {RESOURCE: {'selected': desired}}}
    write_json(root / 'work/main.tf.json', config)
    rc = 'provider_installation { filesystem_mirror { path = ' + canonical(str(root / 'mirror')).decode() + ' include = ["' + SOURCE + '"] } }\ndisable_checkpoint = true\n'
    (root / 'tofu.rc').write_text(rc); (root / 'tofu.rc').chmod(0o400)
    manifest = {'version': 'provider-executor/1.0', 'laboratory': laboratory, 'pins': asdict(pins),
                'object_id': object_id, 'initial': initial, 'desired': desired, 'source_sha256': source_sha256,
                'admission_sha256': admission_sha256, 'target_sha256': target_sha256,
                'configuration_sha256': _sha(root / 'work/main.tf.json'), 'cli_sha256': _sha(root / 'tofu.rc'),
                'implementation_files': _implementation()}
    write_json(root / 'executor.json', manifest)
    return ProviderExecutor(root, credential_environment=credential_environment)


class ProviderExecutor:
    """No arbitrary commands, repositories, HCL, provider sources or ambient env."""
    def __init__(self, root, *, credential_environment=None):
        self.root = _safe(root)
        self.manifest = load_json(self.root / 'executor.json')
        if type(self.manifest) is not dict: _fail('provider_toolchain_pin')
        _engine_version(self.manifest.get('pins'), laboratory=self.manifest.get('laboratory'))
        self._manifest_sha = digest(self.manifest)
        self._active_check = None
        self._credentials = dict(credential_environment or {})
        # Exact provider-native variable names only; never PATH, TF_*, proxies,
        # CLI/config/cache injection, debug logs, or arbitrary endpoint controls.
        allowed = {'M365_TENANT_ID', 'M365_CLIENT_ID', 'M365_CLIENT_SECRET', 'M365_AUTH_METHOD'}
        if set(self._credentials) - allowed or any(type(v) is not str or not v or len(v) > 16384 or '\x00' in v for v in self._credentials.values()):
            _fail('provider_credential_environment')
        if self._credentials and self._credentials.get('M365_AUTH_METHOD') != 'client_secret':
            _fail('provider_credential_method')
        if self.manifest.get('laboratory') is not True and self.manifest.get('pins') != asdict(PRODUCTION_PINS):
            _fail('provider_toolchain_pin')

    @property
    def work(self): return self.root / 'work'

    @property
    def engine_version(self):
        return _engine_version(self.manifest['pins'], laboratory=self.manifest['laboratory'])

    @contextmanager
    def _lock(self):
        path = _safe(self.root / 'operation.lock')
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: _fail('provider_writer_busy')
            yield
        finally: os.close(fd)

    def _integrity(self):
        for directory in (self.root, self.work, self.root / 'home'):
            info = _safe(directory).stat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                _fail('provider_private_workspace_required')
        if digest(load_json(self.root / 'executor.json')) != self._manifest_sha:
            _fail('provider_manifest_changed')
        if self.manifest.get('implementation_files') != _implementation():
            _fail('provider_implementation_changed')
        config = load_json(self.work / 'main.tf.json')
        if (type(config) is not dict or type(config.get('terraform')) is not dict or
                config['terraform'].get('required_version') != '= ' + self.engine_version):
            _fail('provider_configuration_engine_mismatch')
        mirror = self.root / 'mirror' / SOURCE / VERSION / 'linux_amd64'
        if {path.name for path in mirror.iterdir()} != {'terraform-provider-microsoft365_v1.0.0'}:
            _fail('provider_unexpected_plugin_binary')
        for path, expected, maximum in ((self.root / 'tofu', self.manifest['pins']['tofu_sha256'], MAX_BINARY),
                (self.root / 'mirror' / SOURCE / VERSION / 'linux_amd64' / 'terraform-provider-microsoft365_v1.0.0', self.manifest['pins']['provider_sha256'], MAX_BINARY),
                (self.work / 'main.tf.json', self.manifest['configuration_sha256'], MAX_BYTES),
                (self.root / 'tofu.rc', self.manifest['cli_sha256'], MAX_BYTES)):
            if _sha(path, maximum) != expected: _fail('provider_evidence_changed')
        allowed = {'main.tf.json', '.terraform', '.terraform.lock.hcl', 'terraform.tfstate', 'terraform.tfstate.backup',
                   '.terraform.tfstate.lock.info', 'ordinary.plan', 'refresh.plan', 'readback.plan', 'second.plan', 'errored.tfstate'}
        for path in self.work.iterdir():
            if path.name not in allowed or path.is_symlink(): _fail('provider_unexpected_workspace_file')
        installed = self.work / '.terraform'
        if installed.exists():
            relative = Path('providers') / SOURCE / VERSION
            directories = {Path('.'), *relative.parents, relative}
            leaf = relative / 'linux_amd64'
            for base, dirs, files in os.walk(installed, followlinks=False):
                parent = Path(base).relative_to(installed)
                if parent not in directories: _fail('provider_unexpected_plugin_path')
                for name in dirs + files:
                    path = Path(base) / name; rel = path.relative_to(installed)
                    if rel == leaf:
                        expected = self.root / 'mirror' / SOURCE / VERSION / 'linux_amd64'
                        if not path.is_symlink() or os.readlink(path) != str(expected):
                            _fail('provider_plugin_path_changed')
                    elif rel == relative / 'linux_amd64.lock':
                        if path.is_symlink() or not path.is_file(): _fail('provider_plugin_path_changed')
                    elif path.is_symlink() or not path.is_dir() or rel not in directories:
                        _fail('provider_unexpected_plugin_path')
        lock = self.root / 'lock.sha256'
        if lock.exists() and _sha(self.work / '.terraform.lock.hcl') != lock.read_text():
            _fail('provider_lock_changed')

    def _environment(self):
        return {'PATH': '/usr/bin:/bin', 'HOME': str(self.root / 'home'),
                'TF_CLI_CONFIG_FILE': str(self.root / 'tofu.rc'), 'TF_IN_AUTOMATION': '1',
                'CHECKPOINT_DISABLE': '1', 'TF_INPUT': '0',
                'M365_TELEMETRY_OPTOUT': 'true', 'M365_DEBUG_MODE': 'false', **self._credentials}

    def _run(self, name, *, plan_sha=None):
        self._integrity()
        commands = {'init': ['init', '-input=false', '-no-color', '-backend=false'],
                    'schema': ['providers', 'schema', '-json'], 'validate': ['validate', '-json'],
                    'import': ['import', '-input=false', '-no-color', '-lock-timeout=0s', ADDRESS, self.manifest['object_id']],
                    'state': ['show', '-json'],
                    'refresh': ['plan', '-refresh-only', '-input=false', '-no-color', '-lock-timeout=0s', '-out=refresh.plan'],
                    'ordinary': ['plan', '-input=false', '-no-color', '-lock-timeout=0s', '-out=ordinary.plan'],
                    'readback': ['plan', '-refresh-only', '-input=false', '-no-color', '-lock-timeout=0s', '-out=readback.plan'],
                    'second': ['plan', '-input=false', '-no-color', '-lock-timeout=0s', '-out=second.plan'],
                    **{key + '_show': ['show', '-json', key + '.plan'] for key in ('refresh', 'ordinary', 'readback', 'second')}}
        descriptors = []
        try:
            if name not in commands and name != 'apply': _fail('provider_command_not_admitted')
            fd = os.open(_safe(self.root / 'tofu'), os.O_RDONLY | os.O_NOFOLLOW); descriptors.append(fd)
            with os.fdopen(os.dup(fd), 'rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != self.manifest['pins']['tofu_sha256']: _fail('provider_binary_pin_mismatch')
            if name == 'apply' or name.endswith('_show'):
                saved = self.work / ('ordinary.plan' if name == 'apply' else name.removesuffix('_show') + '.plan')
                if name != 'apply' and plan_sha is None: plan_sha = _sha(saved)
                plan_fd = _sealed_plan(saved, plan_sha); descriptors.append(plan_fd)
                if name == 'apply': tail = ['apply', '-input=false', '-no-color', '-lock-timeout=0s', '/proc/self/fd/' + str(plan_fd)]
                else: tail = ['show', '-json', '/proc/self/fd/' + str(plan_fd)]
            else:
                if name not in commands: _fail('provider_command_not_admitted')
                tail = commands[name]
            result = _supervise([str(self.root / 'tofu'), *tail], cwd=self.work, env=self._environment(),
                                executable='/proc/self/fd/' + str(fd), pass_fds=tuple(descriptors), active_check=self._active_check)
            if result['code'] != 0: _fail('provider_command_failed')
            return parse_json(result['stdout']) if name in ('schema', 'validate', 'state') or name.endswith('_show') else None
        finally:
            for fd in descriptors: os.close(fd)

    def prepare(self):
        """Read service through import/refresh, and bind an ordinary saved plan."""
        with self._lock():
            if (self.root / 'operation.json').exists() or (self.root / 'prepared.json').exists():
                _fail('provider_operation_already_prepared')
            self._run('init')
            (self.root / 'lock.sha256').write_text(_sha(self.work / '.terraform.lock.hcl'))
            schema = self._run('schema')
            try: selected = schema['provider_schemas'][SOURCE]['resource_schemas'][RESOURCE]
            except (KeyError, TypeError): _fail('provider_schema_missing')
            if digest(selected) != self.manifest['pins']['selected_schema_sha256']: _fail('provider_schema_pin_mismatch')
            if self._run('validate').get('valid') is not True: _fail('provider_configuration_invalid')
            if (self.work / 'terraform.tfstate').exists(): _fail('provider_unexpected_existing_state')
            self._run('import')
            initial = self.manifest['initial']; object_id = self.manifest['object_id']
            if _observe(_resource_values(self._run('state'), engine_version=self.engine_version), object_id) != initial: _fail('provider_import_preservation_mismatch')
            state = _raw_state(self.work / 'terraform.tfstate', object_id)
            if state['observed'] != initial: _fail('provider_state_preservation_mismatch')
            self._run('refresh')
            _plan(self._run('refresh_show'), object_id, initial, initial, engine_version=self.engine_version, refresh=True)
            if _saved_snapshot(self.work / 'refresh.plan', object_id) != initial: _fail('provider_refresh_snapshot_mismatch')
            self._run('ordinary'); plan_sha = _sha(self.work / 'ordinary.plan')
            plan = self._run('ordinary_show', plan_sha=plan_sha)
            if _sha(self.work / 'ordinary.plan') != plan_sha: _fail('provider_plan_changed')
            action = _plan(plan, object_id, self.manifest['desired'], initial, engine_version=self.engine_version)
            bindings = {'binary_plan_sha256': plan_sha, 'plan_json_sha256': digest(plan),
                        'configuration_sha256': self.manifest['configuration_sha256'], 'target_sha256': self.manifest['target_sha256'],
                        'toolchain_sha256': digest(self.manifest['pins']), 'provider_schema_sha256': digest(selected),
                        'provider_lock_sha256': _sha(self.work / '.terraform.lock.hcl'), 'state_sha256': state['sha256'],
                        'state_lineage_sha256': digest(state['lineage']), 'state_serial': state['serial'],
                        'source_sha256': self.manifest['source_sha256'], 'admission_sha256': self.manifest['admission_sha256'],
                        'object_id_sha256': digest(object_id), 'executor_sha256': self._manifest_sha,
                        'implementation_sha256': digest(self.manifest['implementation_files'])}
            bindings['scope_sha256'] = digest({'target_sha256': self.manifest['target_sha256'], 'object_id_sha256': digest(object_id)})
            request = {'version': 'provider-operation/1.0', 'operation_id': str(uuid.uuid4()),
                       'action': 'provider_update' if action == 'update' else 'provider_no_change',
                       'mode': 'laboratory' if self.manifest['laboratory'] else 'native_provider_network_denied',
                       'bindings': bindings, 'prepared_at': int(time.time()), 'laboratory': self.manifest['laboratory'],
                       'execution_authorized': False}
            write_json(self.root / 'prepared.json', request)
            return request

    def _request(self, request, *, original_state=False):
        self._integrity()
        if _snapshot(request) != load_json(self.root / 'prepared.json'): _fail('provider_request_changed')
        if _sha(self.work / 'ordinary.plan') != request['bindings']['binary_plan_sha256']: _fail('provider_plan_changed')
        if original_state and _sha(self.work / 'terraform.tfstate') != request['bindings']['state_sha256']:
            _fail('provider_state_changed')

    def apply(self, request, *, authorization=None):
        """Authorize exact bytes once, journal before mutation; never retry a write.

        Only the host's typed external-approval context is accepted. Its lock,
        identity freshness and fencing checks span dispatch and readback.
        """
        with self._lock():
            self._request(request, original_state=True)
            if (self.root / 'operation.json').exists(): _fail('provider_mutation_already_attempted')
            from .approval_authority import ApprovedExecution, ExecutionPermit
            if type(authorization) is not ApprovedExecution: _fail('provider_host_authority_required')
            with authorization as permit:
                if type(permit) is not ExecutionPermit: _fail('provider_host_authority_required')
                if permit.request_sha256 != digest(request) or permit.mode != request['mode']:
                    _fail('provider_authorization_binding')
                self._request(request, original_state=True)
                permit.check_active()
                operation = {'operation_id': request['operation_id'], 'request_sha256': digest(request),
                             'status': 'mutation_started', 'mutation_attempts': 1, 'production_qualified': False}
                write_json(self.root / 'operation.json', operation)
                # A durable marker precedes every provider write, including
                # when writing the final result subsequently fails.
                directory_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(directory_fd)
                finally: os.close(directory_fd)
                try:
                    permit.check_active()
                    permit.mark_dispatch()
                    self._active_check = permit.check_active
                    self._run('apply', plan_sha=request['bindings']['binary_plan_sha256'])
                    permit.check_active()
                    operation['status'] = 'apply_returned'
                    write_json(self.root / 'operation.json', operation)
                except Exception:
                    operation['status'] = 'outcome_unknown'
                    try: write_json(self.root / 'operation.json', operation)
                    except (AppError, OSError): pass
                    report = {'status': 'outcome_unknown', 'operation_id': request['operation_id'],
                              'mutation_attempts': 1, 'retry_authorized': False, 'production_qualified': False,
                              'exact_plan_returned': False}
                    self._record_outcome(permit, report)
                    return report
                finally:
                    self._active_check = None
                try:
                    permit.check_active()
                    self._active_check = permit.check_active
                    result = self._reconcile(request, exact_plan_returned=True)
                    permit.check_active()
                except Exception:
                    report = {'status': 'outcome_unknown', 'operation_id': request['operation_id'],
                              'mutation_attempts': 1, 'retry_authorized': False, 'production_qualified': False,
                              'exact_plan_returned': False}
                    self._record_outcome(permit, report)
                    return report
                finally:
                    self._active_check = None
                if not self._record_outcome(permit, result):
                    return {'status': 'outcome_unknown', 'operation_id': request['operation_id'],
                            'mutation_attempts': 1, 'retry_authorized': False, 'production_qualified': False,
                            'exact_plan_returned': False}
                return result

    def _record_outcome(self, permit, report):
        try:
            permit.record_outcome(report)
            operation = load_json(self.root / 'operation.json')
            operation['execution_outcome'] = report
            write_json(self.root / 'operation.json', operation)
            return True
        except (AppError, OSError):
            return False

    def reconcile(self, request, *, authority=None):
        """Fresh provider readback and second plan only; never import/apply."""
        with self._lock():
            confirmed = False
            if authority is not None:
                from .approval_authority import ApprovalAuthority
                if type(authority) is not ApprovalAuthority: _fail('provider_host_authority_required')
                operation = load_json(self.root / 'operation.json')
                prior = operation.get('execution_outcome')
                if type(prior) is dict:
                    try:
                        authority.assert_outcome(request, prior)
                        confirmed = prior.get('exact_plan_returned') is True
                    except AppError:
                        pass
            return self._reconcile(request, exact_plan_returned=confirmed)

    def _reconcile(self, request, *, exact_plan_returned=False):
        self._request(request)
        operation = load_json(self.root / 'operation.json')
        if operation.get('operation_id') != request['operation_id'] or operation.get('request_sha256') != digest(request) or operation.get('mutation_attempts') != 1:
            _fail('provider_operation_binding')
        report = {'operation_id': request['operation_id'], 'mutation_attempts': 1, 'retry_authorized': False,
                  'production_qualified': False, 'exact_plan_returned': exact_plan_returned,
                  'assurance': 'native_provider_local_state' if not self.manifest['laboratory'] else 'laboratory_only'}
        try:
            self._run('readback'); observed_plan = self._run('readback_show')
            observed = _plan(observed_plan, self.manifest['object_id'], self.manifest['desired'], engine_version=self.engine_version, refresh=True)
            if _saved_snapshot(self.work / 'readback.plan', self.manifest['object_id']) != observed:
                _fail('provider_readback_snapshot_mismatch')
            report['readback_sha256'] = digest(observed)
            if observed != self.manifest['desired']:
                report['status'] = 'partial_or_divergent'; report['requires_new_review'] = True
            else:
                self._run('second'); second = self._run('second_show')
                _plan(second, self.manifest['object_id'], self.manifest['desired'], engine_version=self.engine_version, no_change=True, allow_drift=True)
                report['second_plan_json_sha256'] = digest(second)
                state = _raw_state(self.work / 'terraform.tfstate', self.manifest['object_id'])
                if digest(state['lineage']) != request['bindings']['state_lineage_sha256'] or state['serial'] < request['bindings']['state_serial']:
                    _fail('provider_state_lineage_changed')
                report['state_sha256'] = state['sha256']
                report['status'] = 'verified' if state['observed'] == observed else 'service_converged_state_unreconciled'
                if report['status'] == 'verified' and not exact_plan_returned:
                    report['status'] = 'desired_state_observed_execution_unconfirmed'
        except (AppError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
            report['status'] = 'readback_unresolved'
        operation.update(status=report['status'], reconciliation=report)
        write_json(self.root / 'operation.json', operation)
        return report


def _supervise(argv, *, cwd, env, executable, pass_fds, timeout=60, output_limit=MAX_BYTES, active_check=None):
    """Fixed argv, no shell/stdin, bounded pipes, deadline, descendant cleanup."""
    process = None; selector = selectors.DefaultSelector(); output = bytearray(); total = 0
    guard, release = _network_guard()
    try:
        if active_check is not None: active_check()
        process = subprocess.Popen(argv, cwd=cwd, env=env, executable=executable, pass_fds=pass_fds,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   close_fds=True, shell=False, start_new_session=True, umask=0o077, preexec_fn=guard)
        for pipe in (process.stdout, process.stderr):
            os.set_blocking(pipe.fileno(), False); selector.register(pipe, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        while selector.get_map():
            if active_check is not None: active_check()
            if time.monotonic() >= deadline: _fail('provider_process_timeout')
            for key, _ in selector.select(min(0.1, deadline - time.monotonic())):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk: selector.unregister(key.fileobj); continue
                total += len(chunk)
                if total > output_limit: _fail('provider_process_output_limit')
                if key.fileobj is process.stdout: output.extend(chunk)
        # A child may close both output pipes while it continues running. Keep
        # checking authority and the deadline until the process itself exits.
        while process.poll() is None:
            if active_check is not None: active_check()
            if time.monotonic() >= deadline: _fail('provider_process_timeout')
            time.sleep(min(0.05, max(0.001, deadline - time.monotonic())))
        code = process.returncode
        if active_check is not None: active_check()
        return {'code': code, 'stdout': bytes(output)}
    finally:
        release()
        selector.close()
        if process is not None:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait()
            process.stdout.close(); process.stderr.close()


def _network_guard():
    """Local engineering mode: permit plugin AF_UNIX RPC, deny every IP socket.

    This is deliberately not an origin allowlist. A live origin-bound network
    broker remains a host deployment requirement. There is no opt-out switch in
    the production or laboratory factories.
    """
    import ctypes
    import resource
    import sys
    if sys.platform != 'linux' or os.uname().machine != 'x86_64': _fail('provider_platform_unqualified')
    lib = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]; lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]; lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_load.argtypes = [ctypes.c_void_p]; lib.seccomp_load.restype = ctypes.c_int
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    class Comparison(ctypes.Structure):
        _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_int), ('a', ctypes.c_uint64), ('b', ctypes.c_uint64)]
    lib.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(Comparison)]
    lib.seccomp_rule_add_array.restype = ctypes.c_int
    context = lib.seccomp_init(0x7fff0000)
    if not context: _fail('provider_network_guard_unavailable')
    try:
        for name in ('socket', 'socketpair'):
            number = lib.seccomp_syscall_resolve_name(name.encode())
            comparison = Comparison(0, 1, 1, 0)  # SCMP_CMP_NE, AF_UNIX.
            if number < 0 or lib.seccomp_rule_add_array(context, 0x00050001, number, 1, ctypes.byref(comparison)) != 0:
                _fail('provider_network_guard_unavailable')
        # Popen establishes the supervised session before this filter loads.
        # Descendants must remain in that group: otherwise setsid/setpgid lets
        # them survive the finally-block killpg after cancellation or success.
        for name in ('io_uring_setup', 'ptrace', 'setsid', 'setpgid'):
            number = lib.seccomp_syscall_resolve_name(name.encode())
            if number < 0 or lib.seccomp_rule_add_array(context, 0x00050001, number, 0, None) != 0:
                _fail('provider_network_guard_unavailable')
    except BaseException:
        lib.seccomp_release(context); raise
    limits = ((resource.RLIMIT_AS, 4 * 1024 ** 3), (resource.RLIMIT_CPU, 60),
              (resource.RLIMIT_FSIZE, 64 * 1024 ** 2), (resource.RLIMIT_NOFILE, 256), (resource.RLIMIT_CORE, 0))
    limits = tuple((kind, min(value, hard) if hard != resource.RLIM_INFINITY else value)
                   for kind, value in limits for _, hard in (resource.getrlimit(kind),))
    def child():
        try:
            for kind, value in limits: resource.setrlimit(kind, (value, value))
            if lib.seccomp_load(context) != 0: os._exit(125)
        except (OSError, ValueError): os._exit(125)
    return child, lambda: lib.seccomp_release(context)
