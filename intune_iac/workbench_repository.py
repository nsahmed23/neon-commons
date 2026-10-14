"""Repository-owned desired policy for the generated reference component.

A generated project's only desired source is the stack input
``components.terraform.intune-reference.vars.policies.<import key>``. Before
the workbench treats a repository intent as the engineer's desired policy it
checks that the component still consumes exactly that input for exactly that
object (the structural contract the oracle applies to generated output), that
no sibling policy rides in the same map, and that the qualification guard is
unchanged. Nothing here executes Atmos, OpenTofu, Git or a provider, and no
result grants execution authority.
"""
from __future__ import annotations

from pathlib import Path
import re

from .workbench_provenance import _read

CONTRACT = 'workbench-reference-consumer/1'
COMPONENT = 'intune-reference'
POINTER = re.compile(r'/vars/policies/(p_[0-9a-f]{32}_[0-9a-f]{32})')
MAX_COMPONENT_FILES = 16
MAX_COMPONENT_BYTES = 256 * 1024


def _logical_stack(root, variables):
    """`{tenant}-{stage}` when atmos.yaml declares exactly that name pattern."""
    import yaml
    try:
        config = yaml.safe_load(_read(Path(root) / 'atmos.yaml'))
    except Exception:
        return 'unknown'
    pattern = config.get('stacks', {}).get('name_pattern') if isinstance(config, dict) and isinstance(config.get('stacks'), dict) else None
    if pattern != '{tenant}-{stage}' or not isinstance(variables, dict):
        return 'unknown'
    tenant, stage = variables.get('tenant'), variables.get('stage')
    return tenant + '-' + stage if isinstance(tenant, str) and isinstance(stage, str) and tenant and stage else 'unknown'


def _component_sources(root, report):
    directory = Path(root) / report.get('implementation_path', '')
    names = sorted(p.name for p in directory.iterdir() if p.name.endswith(('.tf', '.tf.json')))
    if len(names) > MAX_COMPONENT_FILES:
        return None
    sources = {}
    for name in names:
        data = _read(directory / name)
        if len(data) > MAX_COMPONENT_BYTES:
            return None
        sources[name] = data.decode('utf-8')
    return sources


def consumer_contract(report, pointer, tenant_id, object_id):
    """Classify whether a resolved reference component consumes exactly this policy input."""
    from reference.core import stable_key
    from reference.invariants import component_errors
    result = {'contract': CONTRACT, 'status': 'not_applicable', 'reasons': [], 'policy_key': None,
              'logical_stack': 'unknown', 'execution_authorized': False}
    match = POINTER.fullmatch(pointer) if isinstance(pointer, str) else None
    if report.get('component') != COMPONENT or match is None:
        return result
    key = match.group(1)
    reasons = []
    if key != stable_key(tenant_id, object_id):
        reasons.append('policy_key_identity')
    effective = report.get('effective')
    variables = effective.get('vars') if isinstance(effective, dict) else None
    policies = variables.get('policies') if isinstance(variables, dict) else None
    if not isinstance(policies, dict) or set(policies) != {key}:
        reasons.append('policy_keys_not_exactly_adopted')
    if not isinstance(variables, dict) or variables.get('live_qualification_ack') is not False:
        reasons.append('qualification_guard_changed')
    if report.get('status') != 'resolved' or not report.get('implementation_exists'):
        reasons.append('component_unresolved')
    else:
        try:
            sources = _component_sources(report['root'], report)
        except (OSError, UnicodeError, ValueError):
            sources = None
        if sources is None:
            reasons.append('component_files_unreadable_or_unbounded')
        else:
            reasons.extend(component_errors(sources, key, object_id, allow_backend=True))
    result.update(status='mismatch' if reasons else 'verified', reasons=sorted(set(reasons)), policy_key=key,
                  logical_stack=_logical_stack(report.get('root', ''), variables))
    return result


def intent_freshness(data):
    """Compare a recorded intent with a fresh complete resolution; never re-import.

    ``current`` means every resolved source and the effective configuration are
    byte-identical to what the intent recorded. ``stale`` names the added,
    removed and changed sources and the desired difference at the intent's
    pointer. ``unavailable`` means the repository cannot be resolved now.
    """
    from .io import AppError, canonical, digest
    from .repository import public_resolution, resolve_component
    from .workbench_diff import field_changes
    from .workbench_views import _pointer
    result = {'status': 'unavailable', 'execution_authorized': False}
    scope = data.get('scope') if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get('schema_version') != 'workbench-repository-intent/1' or not isinstance(scope, dict):
        return dict(result, reason='intent_shape_unsupported')
    try:
        report = resolve_component(scope['repository'], scope['stack'], scope['component'])
    except (AppError, OSError, KeyError, TypeError, ValueError):
        return dict(result, reason='repository_unreadable')
    if report.get('status') != 'resolved' or report.get('abstract') or not report.get('implementation_exists'):
        return dict(result, reason='repository_unresolved', blockers=report.get('blockers', []))
    fresh, recorded = public_resolution(report), data.get('resolution') or {}
    before = {row['path']: row['sha256'] for row in recorded.get('sources', [])}
    after = {row['path']: row['sha256'] for row in fresh.get('sources', [])}
    try:
        desired_now = _pointer(report['effective'], data['effective_pointer'])
    except AppError:
        desired_now = None
    result.update(
        status='current' if canonical(fresh) == canonical(recorded) else 'stale',
        # What a reader is shown; a refresh bound to it refuses a repository that moved on since.
        resolution_sha256=digest(fresh),
        sources={'added': sorted(set(after) - set(before)), 'removed': sorted(set(before) - set(after)),
                 'changed': sorted(path for path in set(before) & set(after) if before[path] != after[path])},
        pointer_present=desired_now is not None,
        desired_changed=desired_now is None or canonical(desired_now) != canonical(data['desired']),
        field_changes=field_changes(data['desired'], desired_now) if desired_now is not None else None,
        consumer=consumer_contract(report, data['effective_pointer'], data['tenant_id'], data['target_object_id']))
    return result


def latest_intent(store, object_id):
    """The newest repository intent for an object, refusing a choice between scopes."""
    from .io import AppError, digest
    rows = [row for row in store.artifacts(kind='repository_intent') if row['data'].get('target_object_id') == object_id]
    if not rows:
        raise AppError('workbench_repository_intent_missing', 'Import the repository for this object before using its intent.')
    if len({digest(row['data'].get('scope')) for row in rows}) > 1:
        raise AppError('workbench_repository_scope_ambiguous', 'Intents for this object come from more than one '
                       'repository scope. The workbench will not choose between them, and a further import does not '
                       'resolve this in this store.')
    return max(rows, key=lambda row: row['sequence'])


NEXT_ACTIONS = {
    'current': 'The repository still matches this intent. propose-from-intent NEW_OPERATION_DIR prepares a proposal for review.',
    'stale': 'The repository changed since this intent was recorded. Review the difference, then repository-refresh REVISION '
             'records the current source as a new intent; earlier reviews of the old intent are no longer current.',
    'unavailable': 'The repository cannot be resolved now. Restore it, or import it again with repository-import.',
}


def status(store, object_id):
    """The latest intent for an object: what it recorded, whether it is still current, and the next step."""
    intent = latest_intent(store, object_id)
    data = intent['data']
    freshness = intent_freshness(data)
    return {'schema_version': 'workbench-repository-status/1', 'object_id': object_id,
            'repository_intent_id': intent['artifact_id'], 'recorded_at': intent['recorded_at'],
            'scope': data['scope'], 'effective_pointer': data['effective_pointer'],
            'source_revision': data['source_revision'], 'revision_content_verified': data.get('revision_content_verified'),
            'consumer': data.get('consumer', {'status': 'not_recorded'}), 'freshness': freshness,
            'next_action': NEXT_ACTIONS[freshness['status']], 'execution_authorized': False, 'cloud_authority': False}


def refresh_intent(store, object_id, revision, *, expected_resolution=None, git_executable=None, git_sha256=None):
    """Re-import the latest intent's exact repository, stack, component, pointer, backend and address.

    With expected_resolution (the resolution_sha256 of the difference that was shown), a repository that changed
    again since is refused, so a refresh never records a difference nobody was shown.
    """
    from .io import AppError
    from .workbench_views import import_repository
    data = latest_intent(store, object_id)['data']
    if expected_resolution is not None and intent_freshness(data).get('resolution_sha256') != expected_resolution:
        raise AppError('workbench_difference_changed', 'The repository changed again after its difference was shown; '
                       'review the difference again before recording it.')
    scope = data['scope']
    return import_repository(store, scope['repository'], scope['stack'], scope['component'], object_id,
                             data['effective_pointer'], revision, scope['backend'], data['resource_address'],
                             git_executable=git_executable, git_sha256=git_sha256)


def _usable_intent(intent, *, code_prefix):
    """Refuse an intent whose repository moved on or whose component no longer consumes it."""
    from .io import AppError
    data = intent['data']
    recorded = data.get('consumer', {}).get('status', 'not_applicable')
    freshness = intent_freshness(data)
    if freshness['status'] == 'unavailable':
        raise AppError(code_prefix + '_repository_unavailable', 'The repository behind this intent cannot be resolved now; '
                       'restore it or import the repository again before continuing.')
    if (freshness['status'] != 'current' or recorded == 'mismatch'
            or freshness['consumer']['status'] == 'mismatch'):
        raise AppError(code_prefix + '_repository_stale', 'The repository changed since this intent was recorded, or its '
                       'component no longer consumes exactly this policy. Refresh the intent, review the difference and '
                       'prepare a new proposal.')
    return freshness


def propose_from_intent(store_root, service_root, object_id, output):
    """Prepare a proposal whose desired body and citation come from the current repository intent.

    The inputs are written beside the operation directory, never inside it, and
    the existing ``propose`` applies every observation, plan and citation check.
    """
    from . import maintenance
    from .io import AppError, write_json
    from .workbench_store import WorkbenchStore
    store = WorkbenchStore(store_root)
    intent = latest_intent(store, object_id)
    _usable_intent(intent, code_prefix='workbench')
    if intent['data'].get('consumer', {}).get('status') == 'verified' and capability_problems(intent['data']['desired']):
        raise AppError('workbench_desired_capability', 'The desired settings include a definition or value outside the '
                       'supported offline capability map, so the reference component cannot propose them.')
    output = Path(output).absolute()
    desired_path, context_path = Path(str(output) + '.intent-desired.json'), Path(str(output) + '.intent-context.json')
    if any(path.exists() or path.is_symlink() for path in (output, desired_path, context_path)) or not output.parent.is_dir():
        raise AppError('workbench_fresh_output_required', 'Choose a new operation directory; its sibling input files must not exist.')
    data = intent['data']
    write_json(desired_path, data['desired'])
    write_json(context_path, {'tenant_id': store.tenant_id, 'cloud': 'public',
                              'repository_intent_id': intent['artifact_id'], 'scope': data['scope']})
    return maintenance.propose(store_root, service_root, object_id, desired_path, output, context_path=context_path)


def capability_problems(desired):
    """The capability map the generator enforces, applied to a repository desired body."""
    from reference.validation import capability_errors
    settings = desired.get('settings', {}).get('settings') if isinstance(desired, dict) else None
    technologies = desired.get('technologies') if isinstance(desired, dict) else None
    if not isinstance(settings, list) or not isinstance(technologies, list):
        return ['unqualified_setting_capability']
    records = [dict(row, **{'@odata.type': '#microsoft.graph.deviceManagementConfigurationSetting'})
               if isinstance(row, dict) else row for row in settings]
    return capability_errors(records, desired.get('platforms'), ','.join(t for t in technologies if isinstance(t, str)))


def require_current_intent(store, intent_id):
    """Execute-time recheck: the cited intent must still describe the repository exactly."""
    from .io import AppError
    row = store.artifact(intent_id, kind='repository_intent')
    rows = [row] if row is not None else []
    if len(rows) != 1:
        raise AppError('maintenance_repository_unavailable', 'The cited repository intent is no longer in this store.')
    return _usable_intent(rows[0], code_prefix='maintenance')
