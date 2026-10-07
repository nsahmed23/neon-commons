"""Process-held local Git/intent evidence for an explicitly associated repository.

This capability proves exact local source materialization, not remote origin,
actor identity, source approval or execution authority. An intent-aware service
manifest must bind its facts under the existing exact-operation approval.
"""
from __future__ import annotations
import copy
import hashlib
import os
from pathlib import Path
import re
import stat

from .io import AppError, canonical, digest, parse_json
from .repository import resolve_component, public_resolution
from .workbench_provenance import _read
from .workbench_revision import verify_revision
from .workbench_store import WorkbenchStore
from .workbench_views import _pointer
from .worker_provider import WorkerProviderAdapter, PROJECT
from .worker_host import _hash_file

_SEAL = object()
_HASH = re.compile(r'[0-9a-f]{64}')
_REPOSITORY = re.compile(r'https://github\.com/[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*')


def _fail(code):
    raise AppError(code, 'The reviewed local source, intent and native materialization binding was not established.') from None


def _root_identity(path):
    root = Path(path)
    if not root.is_absolute() or str(root) != str(root.absolute()):
        _fail('worker_source_root')
    rows = []
    for candidate in (root, *root.parents):
        info = candidate.lstat()
        if not stat.S_ISDIR(info.st_mode) or candidate.is_symlink():
            _fail('worker_source_root')
        rows.append({'path': str(candidate), 'device': info.st_dev, 'inode': info.st_ino})
    return rows


def _git_storage(root, git_executable, git_sha256):
    """Recheck exact verified Git storage without launching from a watchdog."""
    gitdir = root / '.git'; objects = gitdir / 'objects'
    _root_identity(gitdir); _root_identity(objects)
    for name in ('commondir', 'shallow', 'objects/info/alternates', 'objects/info/http-alternates'):
        if (gitdir/name).exists() or (gitdir/name).is_symlink():
            _fail('worker_source_git_indirection')
    if _hash_file(Path(git_executable), 32 * 1024 * 1024) != git_sha256:
        _fail('worker_source_git_pin_changed')
    directories = []; files = []; total = 0
    def unreadable(error):
        _fail('worker_source_git_storage_unreadable')
    for current, children, names in os.walk(objects, followlinks=False, onerror=unreadable):
        directory = Path(current); info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or directory.is_symlink():
            _fail('worker_source_git_storage_type')
        directories.append({'path': str(directory.relative_to(gitdir)), 'device': info.st_dev, 'inode': info.st_ino})
        if len(directories) > 1024:
            _fail('worker_source_git_storage_limit')
        for child in children:
            if (directory/child).is_symlink(): _fail('worker_source_git_storage_type')
        for name in sorted(names):
            path = directory/name; info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or path.is_symlink():
                _fail('worker_source_git_storage_type')
            total += info.st_size
            if len(files) >= 1024 or total > 32 * 1024 * 1024:
                _fail('worker_source_git_storage_limit')
            files.append({'path': str(path.relative_to(gitdir)), 'sha256': _hash_file(path, 32 * 1024 * 1024),
                'bytes': info.st_size, 'device': info.st_dev, 'inode': info.st_ino})
    return {'schema_version': 'worker-source-git-storage/1', 'files': sorted(files, key=lambda row: row['path']),
        'directories': sorted(directories, key=lambda row: row['path']), 'total_bytes': total,
        'configuration_sha256': hashlib.sha256(_read(gitdir/'config')).hexdigest(),
        'git_sha256': git_sha256, 'scope': 'exact bounded object-store bytes independently interpreted by pinned Git at capability creation'}


def _collect(store, intent_id, adapter, repository, git_executable, git_sha256, *, verified_reference=None):
    if (type(store) is not WorkbenchStore or type(adapter) is not WorkerProviderAdapter or
            type(intent_id) is not str or not _HASH.fullmatch(intent_id) or
            type(repository) is not str or not _REPOSITORY.fullmatch(repository)):
        _fail('worker_source_capability_inputs')
    provider = adapter.binding()
    rows = [row for row in store.artifacts(kind='repository_intent') if row['artifact_id'] == intent_id]
    if len(rows) != 1:
        _fail('worker_source_intent_missing')
    row = rows[0]; data = row['data']; scope = data['scope']
    target = provider['object_id']; tenant = provider['provider_identity']['tenant_id']
    if (data['schema_version'] != 'workbench-repository-intent/1' or
            data['tenant_id'] != tenant or store.tenant_id != tenant or data['target_object_id'] != target or
            data['source_revision'] != provider['source_revision'] or
            data['resource_address'] != 'microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json.selected' or
            data['effective_pointer'] != '/vars/native_policy' or scope['stack'] != 'worker' or
            scope['component'] != 'intune-policy' or scope['backend'] != provider['backend']['state_blob']):
        _fail('worker_source_target')
    matches = [item for item in store.artifacts(kind='repository_intent') if
               item['data']['target_object_id'] == target and item['data']['scope'] == scope]
    if not matches or max(matches, key=lambda item: item['sequence'])['artifact_id'] != intent_id:
        _fail('worker_source_intent_stale')
    root = Path(scope['repository']); roots = _root_identity(root)
    git_storage = _git_storage(root, git_executable, git_sha256)
    if verified_reference is not None and git_storage != verified_reference['git_storage_binding']:
        _fail('worker_source_git_storage_changed')
    report = resolve_component(root, 'worker', 'intune-policy')
    if (report.get('status') != 'resolved' or report.get('abstract') or not report.get('implementation_exists') or
            canonical(public_resolution(report)) != canonical(data['resolution'])):
        _fail('worker_source_resolution_changed')
    desired = _pointer(report['effective'], '/vars/native_policy')
    if canonical(desired) != canonical(data['desired']) or canonical(desired) != canonical(adapter.spec.desired):
        _fail('worker_source_desired_changed')
    # The currently reviewed source profile is one fixed JSON component reading
    # one literal Atmos variable. Arbitrary expressions or extra resources cannot
    # be hidden behind a matching desired-input record.
    files = adapter.source_files()
    main_name = 'project/' + PROJECT + '/main.tf.json'
    generated = files[main_name]
    if hashlib.sha256(generated).hexdigest() != provider['source_sha256']:
        _fail('worker_source_generated_digest')
    expected = parse_json(generated)
    expected['variable']['native_policy'] = {'type': 'any'}
    resource = 'microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json'
    expected['resource'][resource]['selected'] = {key: '${var.native_policy.' + key + '}' for key in desired}
    authored = _read(root / PROJECT / 'main.tf.json')
    lock = _read(root / PROJECT / '.terraform.lock.hcl')
    if canonical(parse_json(authored)) != canonical(expected) or lock != adapter.lockfile:
        _fail('worker_source_component_changed')
    sources = report['sources']
    paths = [item['path'] for item in sources]
    if len(set(paths)) != len(paths) or not {PROJECT + '/main.tf.json', PROJECT + '/.terraform.lock.hcl'} <= set(paths):
        _fail('worker_source_incomplete_sources')
    revision = (verify_revision(root, data['source_revision'], sources,
        git_executable=git_executable, git_sha256=git_sha256) if verified_reference is None
        else copy.deepcopy(verified_reference['revision_evidence']))
    if not revision['working_sources_match_revision']:
        _fail('worker_source_revision_mismatch')
    # Re-resolve/read after Git inspection. This is a bounded preparation check,
    # not an OS snapshot or a promise of atomicity against a hostile filesystem.
    if (_root_identity(root) != roots or
            _git_storage(root, git_executable, git_sha256) != git_storage or
            canonical(public_resolution(resolve_component(root, 'worker', 'intune-policy'))) != canonical(data['resolution']) or
            _read(root / PROJECT / 'main.tf.json') != authored or
            _read(root / PROJECT / '.terraform.lock.hcl') != lock):
        _fail('worker_source_changed_during_check')
    return {'schema_version': 'worker-source-authoring-binding/1',
        'local_scope': copy.deepcopy(scope), 'logical_repository': repository,
        'repository_association': 'explicit_operation_manifest_declaration',
        'local_root_identity': roots, 'tenant_id': tenant, 'object_id': target,
        'resource_address': data['resource_address'], 'intent_artifact_id': intent_id,
        'intent_data_sha256': digest(data), 'source_revision': data['source_revision'],
        'revision_evidence': revision, 'git_storage_binding': git_storage, 'resolved_inputs_sha256': digest(desired),
        'materialized_configuration_sha256': hashlib.sha256(generated).hexdigest(),
        'materialized_source_manifest': {key: hashlib.sha256(value).hexdigest() for key,value in sorted(files.items())},
        'provider_binding_sha256': digest(provider), 'provider_lock_sha256': hashlib.sha256(lock).hexdigest(),
        'authored_component_sha256': hashlib.sha256(authored).hexdigest(),
        'management_mapping_status': data['semantics']['status'],
        'source_evidence_class': 'pinned_local_git_and_literal_materialization',
        'remote_origin_authenticated': False, 'commit_actor_authenticated': False,
        'execution_authorized': False, 'platform_qualified': False,
        'limitations': ['Logical repository association is explicitly reviewed in the signed operation, not inferred from git remote.',
            'The existing literal and native profiles remain bounded; unsupported mapping is not promoted.',
            'Rechecks detect selected-source changes; hostile host/filesystem atomicity remains a separate qualification gate.']}


class RepositoryExecutionIntent:
    __slots__ = ('_seal', '_store', '_intent_id', '_adapter', '_repository', '_git', '_git_sha', '_facts', '_facts_sha', '_pid')

    def __init__(self, seal, store, intent_id, adapter, repository, git, git_sha, facts):
        if seal is not _SEAL:
            _fail('worker_source_capability_required')
        self._seal = seal; self._store = store; self._intent_id = intent_id; self._adapter = adapter
        self._repository = repository; self._git = git; self._git_sha = git_sha
        self._facts = copy.deepcopy(facts); self._facts_sha = digest(self._facts); self._pid = os.getpid()

    def _integrity(self):
        if self._seal is not _SEAL or self._pid != os.getpid() or digest(self._facts) != self._facts_sha:
            _fail('worker_source_capability_changed')

    def binding(self):
        self._integrity()
        return copy.deepcopy(self._facts)

    def check(self):
        self._integrity()
        current = _collect(self._store, self._intent_id, self._adapter, self._repository, self._git, self._git_sha, verified_reference=self._facts)
        if digest(current) != self._facts_sha:
            _fail('worker_source_binding_changed')
        return copy.deepcopy(current)

    def __reduce__(self):
        _fail('worker_source_capability_not_serializable')


def bind_source_intent(*, store, intent_id, adapter, logical_repository, git_executable, git_sha256):
    facts = _collect(store, intent_id, adapter, logical_repository, git_executable, git_sha256)
    return RepositoryExecutionIntent(_SEAL, store, intent_id, adapter, logical_repository, git_executable, git_sha256, facts)


def validate_operation_binding(facts, *, provider_binding, run_context, tenant_id, object_ids, backend_scope_sha256):
    """Closed cross-check of signed review facts; this alone is not a capability."""
    fields = {'schema_version', 'local_scope', 'logical_repository', 'repository_association',
        'local_root_identity', 'tenant_id', 'object_id', 'resource_address', 'intent_artifact_id',
        'intent_data_sha256', 'source_revision', 'revision_evidence', 'git_storage_binding',
        'resolved_inputs_sha256', 'materialized_configuration_sha256', 'materialized_source_manifest',
        'provider_binding_sha256', 'provider_lock_sha256', 'authored_component_sha256',
        'management_mapping_status', 'source_evidence_class', 'remote_origin_authenticated',
        'commit_actor_authenticated', 'execution_authorized', 'platform_qualified', 'limitations'}
    if (type(facts) is not dict or set(facts) != fields or
            facts['schema_version'] != 'worker-source-authoring-binding/1' or
            type(provider_binding) is not dict or type(run_context) is not dict or
            run_context.get('schema_version') != 'service-run-context/1'):
        _fail('worker_source_operation_shape')
    scope = facts['local_scope']; provider = provider_binding
    if (type(scope) is not dict or set(scope) != {'repository','stack','component','backend'} or
            facts['logical_repository'] != run_context['repository'] or
            facts['tenant_id'] != tenant_id or object_ids != [facts['object_id']] or
            provider.get('object_id') != facts['object_id'] or
            provider.get('provider_identity',{}).get('tenant_id') != tenant_id or
            scope['stack'] != run_context['stack'] or scope['component'] != run_context['component'] or
            scope['backend'] != provider.get('backend',{}).get('state_blob') or
            digest(provider.get('backend')) != backend_scope_sha256 or
            facts['source_revision'] != run_context['source_revision'] or
            facts['source_revision'] != provider.get('source_revision') or
            facts['resolved_inputs_sha256'] != run_context['effective_inputs_sha256'] or
            facts['resolved_inputs_sha256'] != provider.get('effective_input_sha256') or
            facts['materialized_configuration_sha256'] != run_context['source_sha256'] or
            facts['materialized_configuration_sha256'] != provider.get('source_sha256') or
            facts['provider_lock_sha256'] != run_context['provider_lock_sha256'] or
            facts['provider_lock_sha256'] != provider.get('lockfile_sha256') or
            facts['provider_binding_sha256'] != digest(provider) or
            facts['remote_origin_authenticated'] is not False or facts['commit_actor_authenticated'] is not False or
            facts['execution_authorized'] is not False or facts['platform_qualified'] is not False or
            facts['repository_association'] != 'explicit_operation_manifest_declaration'):
        _fail('worker_source_operation_binding')
    for field in ('intent_artifact_id','intent_data_sha256','resolved_inputs_sha256','materialized_configuration_sha256',
                  'provider_binding_sha256','provider_lock_sha256','authored_component_sha256'):
        if type(facts[field]) is not str or not _HASH.fullmatch(facts[field]):
            _fail('worker_source_operation_hash')
    return copy.deepcopy(facts)
