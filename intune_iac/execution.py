"""Conservative plan inspection and a fixed, local-only recovery protocol.

No cloud adapter is shipped. Caller-provided JSON is never authorization.
The fixture adapter exercises actual local writes and independent readback, not
provider/service semantics. Receipts contain hashes, never plan or policy values.
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from .io import AppError, canonical, digest, file_sha, load_json, parse_json, write_json

FORMAT_VERSIONS = frozenset({'1.0', '1.1', '1.2'})
ENGINE_VERSIONS = frozenset({'1.10.0'})
TOP_KEYS = frozenset({'format_version', 'terraform_version', 'planned_values', 'resource_changes',
    'resource_drift', 'output_changes', 'prior_state', 'configuration', 'variables',
    'relevant_attributes', 'checks', 'timestamp', 'errored', 'applyable', 'complete', 'deferred_changes'})
CHANGE_KEYS = frozenset({'actions', 'before', 'after', 'after_unknown', 'before_sensitive',
    'after_sensitive', 'importing', 'generated_config', 'replace_paths'})
RESOURCE_KEYS = frozenset({'address', 'previous_address', 'module_address', 'mode', 'type',
    'name', 'index', 'provider_name', 'deposed', 'action_reason', 'change'})
ACTIONS = frozenset({('no-op',), ('create',), ('read',), ('update',), ('delete',),
                    ('delete', 'create'), ('create', 'delete'), ('forget',), ('create', 'forget')})
FACETS = ('policy', 'assignments')
BINDINGS = frozenset({'plan_sha256', 'config_sha256', 'tool_sha256', 'target_sha256'})
HASH = re.compile(r'^[0-9a-f]{64}$')
MAX_NODES = 50000
MAX_LOCAL_BYTES = 1024 * 1024


def _bounded(value, limit=MAX_LOCAL_BYTES):
    """Bound direct Python input too; callers need not have used load_json."""
    pending = [(value, 0)]; nodes = 0
    while pending:
        item, depth = pending.pop(); nodes += 1
        if nodes > MAX_NODES or depth > 48:
            raise AppError('invalid_document', 'Document exceeds supported limits.')
        if isinstance(item, dict):
            if not all(isinstance(k, str) and len(k) <= 4096 for k in item):
                raise AppError('invalid_document', 'Invalid JSON object keys.')
            pending.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            pending.extend((v, depth + 1) for v in item)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise AppError('invalid_document', 'Document must contain JSON values.')
    data = canonical(value)
    if len(data) > limit:
        raise AppError('invalid_document', 'Document exceeds supported limits.')
    return parse_json(data)


def _mask(value):
    if type(value) is bool: return value
    if isinstance(value, dict): return any([_mask(v) for v in value.values()])
    if isinstance(value, list): return any([_mask(v) for v in value])
    raise AppError('invalid_mask', 'Unknown and sensitive masks must contain booleans.')


def _text(value):
    return isinstance(value, str) and 0 < len(value) <= 4096 and '\x00' not in value


def review_plan(document: dict) -> dict:
    """Review the historical general plan profile; versions are not widened."""
    return _review_plan(document, ENGINE_VERSIONS)


def review_local_output_plan(document: dict, *, engine_version: str) -> dict:
    """Current exact-version review restricted to resource-free local outputs.

    This changes parser version admission only. The protected executor separately
    verifies the binary pin, exact configuration, output semantics and authority.
    """
    if type(engine_version) is not str or engine_version not in {'1.10.0', '1.13.1'}:
        raise AppError('unqualified_engine_version', 'Unsupported local output engine.')
    value = _bounded(document, 16 * MAX_LOCAL_BYTES)
    try:
        valid = (type(value) is dict and value.get('terraform_version') == engine_version
            and value.get('resource_changes') == []
            and value.get('planned_values', {}).get('root_module') == {}
            and set(value.get('configuration', {})) == {'root_module'}
            and set(value['configuration']['root_module']) == {'outputs'}
            and value.get('prior_state', {}).get('values', {}).get('root_module') == {})
    except (AttributeError, TypeError, KeyError):
        valid = False
    if not valid:
        raise AppError('native_output_plan_shape', 'Only a resource-free output plan is admitted.')
    return _review_plan(value, frozenset({engine_version}))


def _review_plan(document: dict, engine_versions) -> dict:
    """Inspect pinned show-JSON semantics; never authorize or echo input values."""
    report = {'version': '1.0.0', 'status': 'blocked', 'execution_authorized': False,
              'assurance': 'offline_plan_review_only', 'blockers': [], 'changes': [],
              'counts': {k: 0 for k in ('no-op', 'create', 'read', 'update', 'delete',
                                      'replacement', 'forget', 'import', 'drift', 'output_changes')}}
    def block(code, location='plan'):
        issue = {'code': code, 'location': location}
        if issue not in report['blockers']: report['blockers'].append(issue)
    try:
        document = _bounded(document, 16 * MAX_LOCAL_BYTES)
        if not isinstance(document, dict): raise ValueError()
        report['plan_json_sha256'] = digest(document)
        _review_header(document, block, engine_versions)
        _review_configuration(document.get('configuration'), block)
        _review_checks(document.get('checks', []), block)
        _review_resource_changes(document, report, block)
        _review_planned_values(document.get('planned_values'), document.get('resource_changes'), block)
        _review_output_changes(document.get('output_changes', {}), report, block)
        _review_planned_outputs(document.get('planned_values'), document.get('output_changes', {}), block)
        _review_prior_state(document, block, engine_versions)
        _finish_review(document, report, block)
    except (ValueError, TypeError, RecursionError, UnicodeError, OverflowError):
        block('invalid_plan_document')
    return report


def _review_header(document, block, engine_versions=ENGINE_VERSIONS):
    required = {'format_version', 'terraform_version', 'planned_values', 'resource_changes', 'configuration'}
    if not required <= document.keys(): block('missing_plan_fields')
    if document.keys() - TOP_KEYS: block('unknown_plan_fields')
    if document.get('format_version') not in FORMAT_VERSIONS: block('unsupported_format_version')
    if document.get('terraform_version') not in engine_versions: block('unqualified_engine_version')
    for key in ('planned_values', 'configuration'):
        if not isinstance(document.get(key), dict): block('invalid_' + key)
    for key, kind in (('prior_state', dict), ('variables', dict), ('relevant_attributes', list)):
        if key in document and not isinstance(document[key], kind): block('invalid_plan_metadata')
    for key in ('errored', 'applyable', 'complete'):
        if key in document and type(document[key]) is not bool: block('invalid_plan_flag')
    if document.get('errored') is True: block('errored_plan')
    if document.get('complete') is False: block('incomplete_plan')
    if 'deferred_changes' in document:
        if not isinstance(document['deferred_changes'], list) or document['deferred_changes']:
            block('deferred_effects')


def _review_resource_changes(document, report, block):
    for section in ('resource_changes', 'resource_drift'):
        changes = document.get(section, [])
        if not isinstance(changes, list): block('invalid_change_collection'); continue
        identities = set()
        for index, resource in enumerate(changes):
            location = section + '/' + str(index)
            identity = _resource_identity(resource, location, block)
            if identity is None: continue
            if identity in identities: block('duplicate_resource_identity', location)
            identities.add(identity)
            entry = _review_change(resource.get('change'), location, report, block)
            if entry:
                entry['reference_sha256'] = digest(identity); entry['section'] = section
                report['changes'].append(entry)
            if section == 'resource_drift':
                report['counts']['drift'] += 1; block('observed_drift', location)


def _resource_identity(resource, location, block):
    if not isinstance(resource, dict) or resource.keys() - RESOURCE_KEYS:
        block('invalid_resource_change', location); return None
    required = {'address', 'mode', 'type', 'name', 'provider_name', 'change'}
    if not required <= resource.keys() or not all(_text(resource.get(k)) for k in ('address', 'type', 'name', 'provider_name')):
        block('invalid_resource_identity', location); return None
    if resource.get('mode') not in ('managed', 'data'): block('unknown_resource_mode', location)
    if resource.get('deposed') is not None and not _text(resource['deposed']):
        block('invalid_deposed_identity', location); return None
    if resource.get('previous_address') is not None: block('state_move_requires_qualification', location)
    if resource.get('deposed') is not None: block('deposed_object_requires_review', location)
    return resource['address'], resource.get('deposed')


def _review_output_changes(outputs, report, block):
    if not isinstance(outputs, dict): block('invalid_output_changes'); return
    for index, (name, change) in enumerate(outputs.items()):
        entry = _review_change(change, 'output_changes/' + str(index), report, block, output=True)
        if entry:
            entry['reference_sha256'] = digest(name); entry['section'] = 'output_changes'
            report['changes'].append(entry)
            if entry['actions'] != ['no-op']: report['counts']['output_changes'] += 1


def _finish_review(document, report, block):
    if report['blockers']: return
    changed = any(x['actions'] != ['no-op'] or x.get('import_id_sha256') for x in report['changes'])
    if document.get('applyable') is False and changed: block('plan_not_applyable')
    else: report['status'] = 'changes_require_review' if changed else 'no_change'


def _review_change(change, location, report, block, output=False):
    if not isinstance(change, dict) or change.keys() - CHANGE_KEYS:
        block('invalid_change_fields', location); return None
    required = {'actions', 'before', 'after_unknown', 'before_sensitive', 'after_sensitive'}
    if not required <= change.keys(): block('missing_change_fields', location)
    actions = _review_actions(change.get('actions'), location, report, block, output)
    if actions is None: return None
    entry = {'actions': actions}
    unknown = _review_masks(change, location, block)
    if 'after' not in change and not unknown: block('missing_after_value', location)
    _review_change_metadata(change, location, block)
    _review_import(change, entry, location, report, block, output)
    if actions == ['no-op'] and canonical(change.get('before')) != canonical(change.get('after')):
        if change.get('importing') is None or change.get('before') is not None:
            block('inconsistent_noop', location)
    return entry


def _review_actions(actions, location, report, block, output):
    if not isinstance(actions, list) or not all(isinstance(x, str) for x in actions) or tuple(actions) not in ACTIONS:
        block('unknown_actions', location); return None
    if not output:
        if len(actions) > 1: report['counts']['replacement'] += 1
        else: report['counts'][actions[0]] += 1
    if 'delete' in actions or 'forget' in actions: block('destructive_effect', location)
    return actions


def _review_masks(change, location, block):
    unknown = False
    for key in ('after_unknown', 'before_sensitive', 'after_sensitive'):
        try: active = _mask(change.get(key))
        except AppError: block('invalid_value_mask', location); active = True
        if key == 'after_unknown':
            unknown = active
            if active: block('unknown_planned_values', location)
        elif active: block('sensitive_values_require_protected_review', location)
    return unknown


def _review_change_metadata(change, location, block):
    if change.get('generated_config') is not None: block('generated_configuration_requires_review', location)
    if 'replace_paths' not in change: return
    paths = change['replace_paths']
    if not isinstance(paths, list) or any(not isinstance(path, list) or not path or
            any(type(part) not in (str, int) for part in path) for path in paths):
        block('invalid_replacement_paths', location)
    elif paths: block('replacement_paths', location)


def _review_import(change, entry, location, report, block, output):
    if 'importing' not in change: return
    importing = change['importing']
    if output or not isinstance(importing, dict) or set(importing) != {'id'} or not _text(importing.get('id')):
        block('unresolved_import_identity', location); return
    report['counts']['import'] += 1; entry['import_id_sha256'] = digest(importing['id'])
    after = change.get('after')
    if not isinstance(after, dict) or after.get('id') != importing['id']:
        block('import_identity_mismatch', location)


def _collect_resources(values, block, boundary):
    if not isinstance(values, dict):
        block('invalid_' + boundary + '_values'); return {}
    if values.keys() - {'outputs', 'root_module'}: block('unknown_' + boundary + '_value_fields')
    resources = {}; pending = [values.get('root_module', {})]
    while pending:
        module = pending.pop()
        if not isinstance(module, dict) or module.keys() - {'resources', 'child_modules', 'address'}:
            block('invalid_' + boundary + '_module'); continue
        members = module.get('resources', []); children = module.get('child_modules', [])
        if not isinstance(members, list) or not isinstance(children, list):
            block('invalid_' + boundary + '_module'); continue
        pending.extend(children)
        for resource in members:
            allowed = {'address', 'mode', 'type', 'name', 'index', 'provider_name', 'schema_version', 'values', 'sensitive_values', 'depends_on'}
            if not isinstance(resource, dict) or resource.keys() - allowed or not _text(resource.get('address')):
                block('invalid_' + boundary + '_resource'); continue
            address = resource['address']
            if address in resources: block('duplicate_' + boundary + '_resource')
            resources[address] = resource
    return resources


def _known_after(change):
    try: return not _mask(change.get('after_unknown'))
    except AppError: return False


def _compare_resource_values(observed, resource, value, block, boundary):
    for field in ('mode', 'type', 'name', 'provider_name'):
        if observed.get(field) != resource.get(field): block(boundary + '_identity_mismatch')
    if canonical(observed.get('values')) != canonical(value): block(boundary + '_value_mismatch')
    try:
        if _mask(observed.get('sensitive_values', {})): block('sensitive_values_require_protected_review')
    except AppError: block('invalid_value_mask')


def _usable_change(resource):
    return (isinstance(resource, dict) and _text(resource.get('address')) and
            resource.get('deposed') is None and isinstance(resource.get('change'), dict))


def _review_planned_values(values, changes, block):
    """Cross-check the after-side resource denominator and known values."""
    if not isinstance(values, dict) or not isinstance(changes, list): return
    resources = _collect_resources(values, block, 'planned'); expected = set()
    for resource in changes:
        if not _usable_change(resource): continue
        change = resource['change']
        if change.get('actions') in (['delete'], ['forget']): continue
        address = resource['address']; expected.add(address)
        if address in resources and _known_after(change):
            _compare_resource_values(resources[address], resource, change.get('after'), block, 'planned')
    if set(resources) != expected: block('planned_resource_denominator_mismatch')


def _review_prior_state(document, block, engine_versions=ENGINE_VERSIONS):
    changes = document.get('resource_changes'); outputs = document.get('output_changes', {})
    if not isinstance(changes, list) or not isinstance(outputs, dict): return
    prior = document.get('prior_state')
    if prior is None:
        _review_absent_prior(changes, outputs, block); return
    if not isinstance(prior, dict) or set(prior) != {'format_version', 'terraform_version', 'values'}:
        block('invalid_prior_state'); return
    if prior['format_version'] not in FORMAT_VERSIONS or prior['terraform_version'] not in engine_versions:
        block('unqualified_prior_state_version')
    values = prior['values']
    if not isinstance(values, dict): block('invalid_prior_values'); return
    resources = _collect_resources(values, block, 'prior'); expected = set()
    for resource in changes:
        if not _usable_change(resource): continue
        change = resource['change']; address = resource['address']
        if change.get('before') is None: continue
        # An import can obtain before values from a remote read without prior
        # managed state. This allowance does not grant import execution authority.
        if change.get('importing') is not None and address not in resources: continue
        expected.add(address)
        if address in resources:
            _compare_resource_values(resources[address], resource, change['before'], block, 'prior')
    if set(resources) != expected: block('prior_resource_denominator_mismatch')
    _review_prior_outputs(values.get('outputs', {}), outputs, block)


def _review_absent_prior(changes, outputs, block):
    for resource in changes:
        if not _usable_change(resource): continue
        change = resource['change']
        if change.get('before') is not None and change.get('importing') is None:
            block('missing_prior_state')
    if any(isinstance(change, dict) and change.get('before') is not None for change in outputs.values()):
        block('missing_prior_state')


def _review_prior_outputs(outputs, changes, block):
    if not isinstance(outputs, dict): block('invalid_prior_outputs'); return
    expected = {name for name, change in changes.items()
                if isinstance(change, dict) and change.get('before') is not None}
    if set(outputs) != expected: block('prior_output_denominator_mismatch')
    for name, output in outputs.items():
        if not isinstance(output, dict) or set(output) != {'value', 'sensitive', 'type'} or type(output.get('sensitive')) is not bool:
            block('invalid_prior_output'); continue
        if output['sensitive']: block('sensitive_values_require_protected_review')
        change = changes.get(name)
        if isinstance(change, dict) and canonical(output['value']) != canonical(change.get('before')):
            block('prior_output_value_mismatch')


def _review_configuration(configuration, block):
    pending = [configuration]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if item.get('provisioners'): block('executable_provisioners')
            pending.extend(item.values())
        elif isinstance(item, list): pending.extend(item)


def _review_planned_outputs(values, changes, block):
    if not isinstance(values, dict) or not isinstance(changes, dict): return
    outputs = values.get('outputs', {})
    if not isinstance(outputs, dict): block('invalid_planned_outputs'); return
    expected = {name for name, change in changes.items()
                if isinstance(change, dict) and change.get('actions') != ['delete']}
    if set(outputs) != expected: block('planned_output_denominator_mismatch')
    for name, output in outputs.items():
        if not isinstance(output, dict) or output.keys() - {'value', 'sensitive', 'type'} or type(output.get('sensitive')) is not bool:
            block('invalid_planned_output'); continue
        if output['sensitive']: block('sensitive_values_require_protected_review')
        change = changes.get(name)
        if not isinstance(change, dict): continue
        try: unknown = _mask(change.get('after_unknown'))
        except AppError: unknown = True
        if not unknown and ('value' not in output or canonical(output['value']) != canonical(change.get('after'))):
            block('planned_output_value_mismatch')


def _review_checks(checks, block):
    if not isinstance(checks, list): block('invalid_checks'); return
    for check in checks:
        if not isinstance(check, dict) or set(check) - {'address', 'status', 'instances'} or check.get('status') != 'pass':
            block('unpassed_check'); continue
        instances = check.get('instances', [])
        if not isinstance(instances, list): block('invalid_checks'); continue
        if any(not isinstance(x, dict) or x.get('status') != 'pass' for x in instances): block('unpassed_check')


def _path(value):
    path = Path(value).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise AppError('unsafe_path', 'Symlinked paths are unsupported.')
    return path.resolve()


def _read_local(path):
    path = _path(path)
    if not path.is_file() or path.stat().st_size > MAX_LOCAL_BYTES:
        raise AppError('invalid_fixture', 'Invalid bounded local fixture file.')
    return _bounded(load_json(path))


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(fd)
    finally: os.close(fd)


def _exclusive_json(path, value):
    path = _path(path); data = canonical(value) + b'\n'
    if len(data) > MAX_LOCAL_BYTES: raise AppError('invalid_document', 'Receipt limit exceeded.')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    _sync_dir(path.parent)


class LocalFixtureAdapter:
    """The sole shipped adapter. Only fixed files under a private local fixture."""
    assurance = 'local_simulation_only'

    def __init__(self, root):
        self.root = _path(root)
        manifest = _read_local(self.root / 'fixture.json')
        if not isinstance(manifest, dict) or set(manifest) != {'version', 'kind', 'identity'} or manifest.get('version') != '1.0.0' or manifest.get('kind') != 'local_execution_fixture':
            raise AppError('invalid_fixture', 'Invalid local fixture manifest.')
        _operation_id(manifest['identity'])
        self.lock_path = self.root / '.operation-lock'

    def binding(self):
        return {'plan_sha256': file_sha(self.root / 'plan.json'),
                'config_sha256': file_sha(self.root / 'config.json'),
                'tool_sha256': digest({name: file_sha(Path(__file__).with_name(name)) for name in ('execution.py', 'reconciliation.py')}),
                'target_sha256': digest([str(self.root), _read_local(self.root / 'fixture.json')])}

    def definition(self):
        plan = _read_local(self.root / 'plan.json')
        if not isinstance(plan, dict) or set(plan) != {'version', 'before', 'desired'} or plan['version'] != '1.0.0':
            raise AppError('invalid_fixture', 'Invalid local fixture plan.')
        _facet_hashes(plan['before'])
        if not isinstance(plan['desired'], dict) or set(plan['desired']) != set(FACETS):
            raise AppError('invalid_fixture', 'Both desired facets are required.')
        if not isinstance(plan['desired']['policy'], dict) or not isinstance(plan['desired']['assignments'], list):
            raise AppError('invalid_fixture', 'Invalid desired facets.')
        policy = _read_local(self.root / 'policy.json')
        if not isinstance(policy, dict) or not _text(policy.get('id')) or plan['desired']['policy'].get('id') != policy['id']:
            raise AppError('identity_changed', 'Fixture policy identity must be preserved.')
        return plan

    def readback(self):
        # Independent file reads; adapter responses are never the preservation oracle.
        return {name: digest(_read_local(self.root / (name + '.json'))) for name in FACETS}

    def execute_step(self, step, desired_sha256):
        if step not in FACETS: raise AppError('unknown_step', 'Unknown fixed operation step.')
        desired = self.definition()['desired'][step]
        # The value actually written comes from this verified snapshot. A change
        # after the write-ahead receipt cannot substitute unreviewed values.
        if digest(desired) != desired_sha256:
            raise AppError('plan_changed', 'Desired values changed before dispatch.')
        write_json(self.root / (step + '.json'), desired)
        _sync_dir(self.root)


def create_local_fixture(root, *, policy, assignments, desired_policy, desired_assignments):
    """Create a new disposable fixture, never overwrite an existing directory."""
    if os.name != 'posix': raise AppError('adapter_unavailable', 'Local receipt adapter requires POSIX directory fsync.')
    values = _bounded({'policy': policy, 'assignments': assignments, 'desired_policy': desired_policy, 'desired_assignments': desired_assignments})
    if not isinstance(policy, dict) or not isinstance(desired_policy, dict) or not isinstance(assignments, list) or not isinstance(desired_assignments, list):
        raise AppError('invalid_fixture', 'Policy objects and assignment arrays are required.')
    if not _text(policy.get('id')) or desired_policy.get('id') != policy['id']:
        raise AppError('identity_changed', 'Fixture policy identity must be preserved.')
    root = _path(root); root.mkdir(mode=0o700)
    documents = {'fixture': {'version': '1.0.0', 'kind': 'local_execution_fixture', 'identity': str(uuid.uuid4())},
        'policy': values['policy'], 'assignments': values['assignments'],
        'plan': {'version': '1.0.0', 'before': {name: digest(values[name]) for name in FACETS},
                 'desired': {name: values['desired_' + name] for name in FACETS}},
        'config': {'version': '1.0.0', 'steps': list(FACETS), 'external_execution': False}}
    for name, value in documents.items(): _exclusive_json(root / (name + '.json'), value)
    return LocalFixtureAdapter(root)


def _operation_id(value):
    if not isinstance(value, str): raise AppError('invalid_operation', 'Invalid operation identity.')
    try: parsed = uuid.UUID(value)
    except (ValueError, AttributeError): raise AppError('invalid_operation', 'Invalid operation identity.') from None
    if str(parsed) != value: raise AppError('invalid_operation', 'Operation identity must be canonical.')
    return value


def _facet_hashes(value):
    if not isinstance(value, dict) or set(value) != set(FACETS) or not all(isinstance(v, str) and HASH.fullmatch(v) for v in value.values()):
        raise AppError('invalid_operation', 'Both facet hashes are required.')


def prepare_operation(adapter, operation_id=None):
    if type(adapter) is not LocalFixtureAdapter:
        raise AppError('adapter_unavailable', 'No qualified external adapter is shipped.')
    plan = adapter.definition()
    return {'version': '1.0.0', 'action': 'local_fixture_update', 'operation_id': _operation_id(operation_id or str(uuid.uuid4())),
            'binding': adapter.binding(), 'before': plan['before'],
            'after': {name: digest(plan['desired'][name]) for name in FACETS}}


def _validate_request(request):
    request = _bounded(request)
    if not isinstance(request, dict) or set(request) != {'version', 'action', 'operation_id', 'binding', 'before', 'after'} or request['version'] != '1.0.0':
        raise AppError('invalid_operation', 'Invalid operation request.')
    _operation_id(request['operation_id']); _facet_hashes(request['before']); _facet_hashes(request['after'])
    if not isinstance(request['binding'], dict) or set(request['binding']) != BINDINGS or not all(isinstance(v, str) and HASH.fullmatch(v) for v in request['binding'].values()):
        raise AppError('invalid_operation', 'Complete binding hashes are required.')
    return request


def _append_event(directory, event):
    paths = _journal_paths(directory)
    if paths: read_operation(directory.name, directory.parent)
    previous = file_sha(paths[-1]) if paths else None
    record = dict(event, sequence=len(paths), previous_sha256=previous)
    _exclusive_json(directory / f'{len(paths):06d}.json', record)


def read_operation(operation_id, state_dir):
    """Validate a bounded append-only chain; this proves consistency, not origin."""
    directory = _path(state_dir) / _operation_id(operation_id)
    if not directory.is_dir() or directory.is_symlink(): raise AppError('invalid_receipt', 'Operation receipt unavailable.')
    paths = _journal_paths(directory)
    if not 1 <= len(paths) <= 32: raise AppError('invalid_receipt', 'Incomplete operation journal.')
    events = []; previous = None
    for index, path in enumerate(paths):
        if path.name != f'{index:06d}.json': raise AppError('invalid_receipt', 'Noncontiguous journal.')
        record = _read_local(path)
        if not isinstance(record, dict) or type(record.get('sequence')) is not int or record.get('sequence') != index or record.get('previous_sha256') != previous or record.get('operation_id') != operation_id:
            raise AppError('invalid_receipt', 'Invalid operation journal chain.')
        if record.get('event') not in {'prepared', 'step_started', 'step_verified', 'completed'}:
            raise AppError('invalid_receipt', 'Unknown operation event.')
        events.append(record); previous = file_sha(path)
    if events[0]['event'] != 'prepared': raise AppError('invalid_receipt', 'Missing operation preparation.')
    _validate_events(events)
    return {'version': '1.0.0', 'assurance': 'local_consistency_only', 'events': events, 'journal_sha256': previous}


def _journal_paths(directory):
    paths = []
    for path in directory.iterdir():
        if len(paths) >= 32: raise AppError('invalid_receipt', 'Operation journal is over its limit.')
        paths.append(path)
    return sorted(paths)


def _validate_events(events):
    base = {'event', 'operation_id', 'sequence', 'previous_sha256'}
    expected_order = ('prepared', 'step_started', 'step_verified', 'step_started', 'step_verified', 'completed')
    if len(events) > len(expected_order): raise AppError('invalid_receipt', 'Too many operation events.')
    prepared = events[0]
    prepared_keys = base | {'binding', 'initial_hashes', 'desired_hashes', 'request_sha256', 'assurance'}
    if set(prepared) != prepared_keys or prepared.get('assurance') != 'local_simulation_only':
        raise AppError('invalid_receipt', 'Invalid preparation receipt.')
    request = _validate_request({'version': '1.0.0', 'action': 'local_fixture_update',
        'operation_id': prepared['operation_id'], 'binding': prepared['binding'],
        'before': prepared['initial_hashes'], 'after': prepared['desired_hashes']})
    if prepared['request_sha256'] != digest(request): raise AppError('invalid_receipt', 'Invalid request binding.')
    observed = dict(request['before'])
    for index, event in enumerate(events):
        kind = expected_order[index]
        if event['event'] != kind: raise AppError('invalid_receipt', 'Impossible operation transition.')
        if index == 0: continue
        keys = base | ({'observed_hashes'} if kind == 'completed' else {'step'})
        if kind == 'step_verified': keys.add('observed_hashes')
        if set(event) != keys: raise AppError('invalid_receipt', 'Unexpected event fields.')
        if kind != 'completed':
            step = FACETS[(index - 1) // 2]
            if event['step'] != step: raise AppError('invalid_receipt', 'Incorrect operation facet.')
            if kind == 'step_verified': observed[step] = request['after'][step]
        if 'observed_hashes' in event and event['observed_hashes'] != observed:
            raise AppError('invalid_receipt', 'Incorrect observed boundary hashes.')


def _result(status, operation_id=None, code=None):
    result = {'status': status, 'assurance': 'local_simulation_only', 'external_execution_available': False,
              'retry_authorized': False}
    if operation_id is not None: result['operation_id'] = operation_id
    if code: result['reason'] = code
    return result


def _validate_target(request, adapter):
    if adapter.binding() != request['binding']:
        raise AppError('binding_changed', 'Bound plan, configuration, tools or target changed.')
    if prepare_operation(adapter, request['operation_id']) != request:
        raise AppError('plan_changed', 'Operation no longer matches the local fixture plan.')


def _lock_owner(request, state):
    return {'operation_id': request['operation_id'], 'request_sha256': digest(request),
            'state_path_sha256': digest(str(state))}


def _check_lock(request, state, adapter):
    if _read_local(adapter.lock_path / 'owner.json') != _lock_owner(request, state):
        raise AppError('lock_owner_changed', 'The target lock no longer belongs to this operation.')


def execute_operation(request, state_dir, *, adapter=None):
    """Execute two local fixture steps with write-ahead receipts and no replay.

    An unavailable adapter returns before touching disk. Python-injected adapters
    are accepted only when they are the shipped concrete local implementation.
    This deliberately cannot be promoted to cloud execution with a JSON claim.
    """
    if type(adapter) is not LocalFixtureAdapter:
        return _result('unavailable', code='qualified_external_adapter_absent')
    operation_id = None; locked = False
    try:
        request = _validate_request(request); operation_id = request['operation_id']
        if request['action'] != 'local_fixture_update': return _result('unavailable', operation_id, 'external_action_unavailable')
        state = _path(state_dir)
        if state == adapter.root or state in adapter.root.parents or adapter.root in state.parents:
            raise AppError('unsafe_path', 'Fixture and journal scopes overlap.')
        if adapter.lock_path.exists(): return _result('locked', operation_id, 'target_lock_present')
        _validate_target(request, adapter)
        if adapter.readback() != request['before']: raise AppError('precondition_changed', 'Initial readback changed.')
        directory = state / operation_id
        if directory.exists(): raise AppError('operation_exists', 'Operation identities cannot be replayed.')
        try: adapter.lock_path.mkdir(mode=0o700)
        except FileExistsError: return _result('locked', operation_id, 'target_lock_present')
        locked = True
        _sync_dir(adapter.root)
        _exclusive_json(adapter.lock_path / 'owner.json', _lock_owner(request, state))
        state.mkdir(parents=True, exist_ok=True, mode=0o700); directory.mkdir(mode=0o700); _sync_dir(state)
        # Names initial/desired avoid giving an apparent historic outcome to callers.
        _append_event(directory, {'event': 'prepared', 'operation_id': operation_id,
            'binding': request['binding'], 'initial_hashes': request['before'], 'desired_hashes': request['after'],
            'request_sha256': digest(request), 'assurance': 'local_simulation_only'})
        expected = dict(request['before'])
        for step in FACETS:
            _check_lock(request, state, adapter)
            _validate_target(request, adapter)
            if adapter.readback() != expected: raise AppError('readback_changed', 'Readback changed between steps.')
            _append_event(directory, {'event': 'step_started', 'operation_id': operation_id, 'step': step})
            adapter.execute_step(step, request['after'][step])
            expected[step] = request['after'][step]
            if adapter.readback() != expected: raise AppError('readback_mismatch', 'Readback does not match expected facets.')
            _append_event(directory, {'event': 'step_verified', 'operation_id': operation_id, 'step': step,
                                      'observed_hashes': expected.copy()})
        _validate_target(request, adapter)
        if adapter.readback() != request['after']: raise AppError('readback_mismatch', 'Final readback differs.')
        _append_event(directory, {'event': 'completed', 'operation_id': operation_id, 'observed_hashes': expected})
        _check_lock(request, state, adapter)
        (adapter.lock_path / 'owner.json').unlink(); adapter.lock_path.rmdir(); _sync_dir(adapter.root)
        return _result('succeeded_verified', operation_id)
    except (AppError, OSError, ValueError, TypeError, RuntimeError):
        # Once a target lock exists, never convert uncertainty into "failed safely".
        # KeyboardInterrupt/SystemExit intentionally propagate with durable lock.
        return _result('reconciliation_required' if locked else 'rejected', operation_id,
                       'outcome_requires_independent_readback' if locked else 'preflight_rejected')
