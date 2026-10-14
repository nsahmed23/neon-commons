"""Entering an existing Atmos repository: the policies it holds and the exact way to record each.

Read-only. The repository is discovered, and each selectable component resolved,
under the same literal rules as ``repository-import``. Every entry of a
component's ``vars.policies`` becomes a candidate carrying what the repository
itself determines: stack, component and pointer; the object identity encoded in
a stable import key; the checked-out commit read from ``.git``; the backend the
component's files declare; and the resource address when the generated
reference component's consumer contract is verified. Its state in this store
follows (ready, recorded, refused, or the one choice still missing).

No configuration value is returned, because stack values may hold secrets:
names come only from the store's own observations. Nothing is imported, no file
is written and no layout is changed. The exact command is offered for the
engineer to review and run.
"""
from __future__ import annotations

from pathlib import Path
import re
import shlex
from uuid import UUID

VERSION = 'workbench-repository-entry/1'
PROGRAM = 'intune-iac'
STABLE_KEY = re.compile(r'p_([0-9a-f]{32})_([0-9a-f]{32})')
RESOURCE = 'microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json'
BACKEND = re.compile(r'\bbackend\s+"([A-Za-z0-9_-]+)"')
COMMENTS = re.compile(r'/\*.*?\*/|#[^\n]*|//[^\n]*', re.S)
REASONS = {
    'policy_keys_not_exactly_adopted': 'the component holds more than this one policy (one policy per stack and component)',
    'policy_key_identity': "the key does not encode this store's tenant and this policy",
    'qualification_guard_changed': 'live_qualification_ack is no longer false',
    'component_unresolved': 'the component does not resolve',
    'component_files_unreadable_or_unbounded': 'the component files are unreadable or too large',
    'generated_import_identity_changed': "the component's import block does not name this policy",
    'generated_resource_address_changed': 'the resource address differs from the generated component',
    'generated_input_binding_changed': 'the component no longer reads var.policies as generated',
    'generated_hcl_blocks_changed': "the component's blocks differ from the generated ones",
    'generated_resource_field_changed': 'a resource field differs from the generated component',
    'generated_provider_changed': 'the provider requirement differs from the generated one',
    'generated_guard_changed': 'the qualification guard in the component changed',
    'generated_hcl_json_unqualified': 'the component uses HCL JSON, which is not qualified',
    'hcl_parser_unavailable': 'the HCL parser is not available here',
}
MISSING = {
    'revision': 'no commit could be read from .git, and repository-import records a commit: commit the repository first',
    'backend': "the component's files declare more than one backend, or cannot be read: state the backend it uses",
    'resource_address': ('this is not the generated reference component, so the workbench cannot tell which OpenTofu '
                         'resource manages this policy: state its address (tofu state list shows it)'),
}
PLACEHOLDERS = {'object_id': 'OBJECT_ID', 'revision': 'COMMIT', 'backend': 'BACKEND', 'resource_address': 'RESOURCE_ADDRESS'}


def _quote(values):
    return ' '.join(shlex.quote(str(value)) for value in values)


def _import_commands(store, repository, candidate):
    values = {name: candidate[name] or PLACEHOLDERS[name] for name in PLACEHOLDERS}
    terminal = _quote(['repository-import', repository, candidate['stack'], candidate['component'], values['object_id'],
                       candidate['pointer'], values['revision'], values['backend'], values['resource_address']])
    cli = _quote([PROGRAM, 'workbench', 'repository-import', '--root', store.root, '--repo', repository,
                  '--stack', candidate['stack'], '--component', candidate['component'], '--object', values['object_id'],
                  '--pointer', candidate['pointer'], '--revision', values['revision'], '--backend', values['backend'],
                  '--resource-address', values['resource_address']])
    return terminal, cli


def _backend(report):
    """The backend type the component's files declare; OpenTofu keeps local state when none is declared."""
    from .workbench_repository import _component_sources
    try:
        sources = _component_sources(report['root'], report)
    except (OSError, UnicodeError, ValueError, KeyError):
        sources = None
    if sources is None:
        return None, 'component_unreadable'
    found = sorted({match.group(1) for text in sources.values() for match in BACKEND.finditer(COMMENTS.sub('', text))})
    if not found:
        return 'local', 'none_declared'
    return (found[0], 'component_declared') if len(found) == 1 else (None, 'ambiguous')


def _observed(store, object_id):
    from .io import AppError
    if object_id is None:
        return {'present': False}
    try:
        value = store.inspect(object_id)
    except AppError:
        return {'present': False}
    return {'present': True, 'name': value.get('name'), 'freshness': value.get('freshness')}


def _recorded(store, intents, report, candidate):
    """Recorded intents for this object: here (same repository, stack and component) or from elsewhere."""
    from .workbench_repository import intent_freshness
    rows = [row for row in intents if row['data'].get('target_object_id') == candidate['object_id']]
    if not rows:
        return candidate
    here = {'repository': str(report['root']), 'stack': candidate['stack'], 'component': candidate['component']}
    elsewhere = [row for row in rows if any(row['data'].get('scope', {}).get(k) != v for k, v in here.items())]
    if elsewhere:
        scope = max(elsewhere, key=lambda row: row['sequence'])['data'].get('scope', {})
        return dict(candidate, state='recorded_elsewhere', recorded={'scope': scope},
                    explanation=('Already recorded for this policy from %s (stack %s, component %s). Recording it from here '
                                 'too would leave two sources for one policy, which status, refresh and proposals refuse. '
                                 'Keep one repository as the source of this policy.'
                                 % (scope.get('repository'), scope.get('stack'), scope.get('component'))))
    latest = max(rows, key=lambda row: row['sequence'])
    freshness = intent_freshness(latest['data'])['status']
    recorded = {'intent_id': latest['artifact_id'], 'freshness': freshness,
                'source_revision': latest['data'].get('source_revision')}
    short = latest['artifact_id'][:12]
    if freshness == 'current':
        return dict(candidate, state='recorded', recorded=recorded,
                    explanation=('Recorded as intent %s and still current. Select the policy in Estate and press 9 for its '
                                 'status; propose-from-intent prepares a proposal from it for review.' % short))
    if freshness == 'stale':
        command = (None if candidate['revision'] is None else _quote([
            PROGRAM, 'workbench', 'repository-refresh', '--root', store.root, '--object', candidate['object_id'],
            '--revision', candidate['revision']]))
        step = ('repository-refresh %s records the current source' % candidate['revision'] if candidate['revision']
                else 'commit the change, then repository-refresh COMMIT records it')
        return dict(candidate, state='recorded', recorded=recorded, command=command,
                    explanation=('Recorded as intent %s; the repository has changed since. Select the policy in Estate and '
                                 'press 9 to see the difference, then %s.' % (short, step)))
    return dict(candidate, state='recorded', recorded=recorded,
                explanation='Recorded as intent %s, but the repository cannot be resolved now.' % short)


def _candidate(store, repository, report, stack, component, key, revision, backend, intents):
    from .workbench_repository import consumer_contract
    match = STABLE_KEY.fullmatch(key)
    key_tenant = str(UUID(match.group(1))) if match else None
    object_id = str(UUID(match.group(2))) if match else None
    candidate = {'stack': stack, 'component': component, 'policy_key': key, 'pointer': '/vars/policies/' + key,
                 'object_id': object_id, 'key_tenant_id': key_tenant, 'revision': revision,
                 'backend': backend[0], 'backend_source': backend[1], 'observed': _observed(store, object_id),
                 'consumer': None, 'resource_address': None, 'recorded': None, 'missing': [],
                 'command': None, 'terminal_command': None, 'template': None}
    if object_id is None:
        terminal, _ = _import_commands(store, repository, candidate)
        return dict(candidate, state='needs_object', missing=['object_id'], template=terminal,
                    explanation=("This key does not encode the policy's identity (generated projects use p_<tenant>_<object>), "
                                 'so its object ID cannot be read from the repository. Supply the Intune object ID it '
                                 'manages; Estate lists the observed policies.'))
    if key_tenant != store.tenant_id:
        return dict(candidate, state='other_tenant',
                    explanation=('The key encodes tenant %s; this store holds tenant %s. Record it into a store for that '
                                 'tenant (workbench init --root STORE --tenant %s).' % (key_tenant, store.tenant_id, key_tenant)))
    consumer = consumer_contract(report, candidate['pointer'], store.tenant_id, object_id)
    candidate['consumer'] = {key_: consumer[key_] for key_ in ('status', 'reasons', 'logical_stack')}
    if consumer['status'] == 'verified':
        candidate['resource_address'] = '%s.policy["%s"]' % (RESOURCE, key)
    recorded = _recorded(store, intents, report, candidate)
    if recorded is not candidate:
        return recorded
    if consumer['status'] == 'mismatch':
        reasons = '; '.join(REASONS.get(reason, reason) for reason in consumer['reasons'])
        return dict(candidate, state='blocked_by_component',
                    explanation=('Recording it would give an intent that proposals refuse: %s. Make the component consume '
                                 'exactly this policy, then survey the repository again.' % reasons))
    missing = [name for name in ('revision', 'backend', 'resource_address') if candidate[name] is None]
    terminal, cli = _import_commands(store, repository, candidate)
    if missing:
        return dict(candidate, state='needs_choice', missing=missing, template=terminal,
                    explanation='Missing before it can be recorded: ' + '; '.join(MISSING[name] for name in missing) + '.')
    return dict(candidate, state='ready', terminal_command=terminal, command=cli,
                explanation=('Ready to record: every value comes from the repository, and the component consumes exactly '
                             'this policy. The commit is recorded as stated; add --git-executable and --git-sha256 to the '
                             'command to verify it against the files.'))


def _next_action(status, blockers, candidates, repository):
    if status != 'discovered':
        return ('This is not a repository the literal Atmos reader can resolve (%s). It needs an atmos.yaml and stack '
                'manifests under its stacks base path.' % (', '.join(blockers) or 'unreadable'))
    if not candidates:
        return ('No component here holds a vars.policies input. Generate a project with the wizard and copy it into this '
                'repository, or add the reference component.')
    ready = sum(1 for item in candidates if item['state'] == 'ready')
    return ('%d %s found, %d ready to record. Each ready policy carries its exact repository-import command.'
            % (len(candidates), 'policy' if len(candidates) == 1 else 'policies', ready))


def entry(store, repository):
    """Survey ``repository`` for policies this store could record, with each one's exact command; read-only."""
    from .entry import _git_revision
    from .io import AppError
    from .repository import discover_repository, resolve_component
    base = {'schema_version': VERSION, 'repository': str(repository), 'tenant_id': store.tenant_id,
            'evidence_class': 'local_repository_files', 'execution_authorized': False, 'cloud_authority': False}
    try:
        report = discover_repository(repository)
    except (AppError, OSError, ValueError):
        report = {'status': 'blocked', 'blockers': [{'code': 'repository_unreadable'}]}
    blockers = sorted({item.get('code', 'unknown') for item in report.get('blockers', [])}
                      | {item.get('code', 'unknown') for stack in report.get('stacks', []) for item in stack.get('blockers', [])})
    revision = _git_revision(Path(repository))
    status = report.get('status', 'blocked')
    components, candidates = [], []
    if status == 'discovered':
        intents = store.artifacts(kind='repository_intent')
        for stack in report.get('stacks', []):
            for component in stack.get('components', []):
                row = {'stack': stack['stack'], 'manifest': stack.get('manifest'), 'component': component['name'],
                       'selectable': bool(component.get('selectable'))}
                if not row['selectable']:
                    components.append(dict(row, policies=0, reason='not_selectable'))
                    continue
                resolved = resolve_component(repository, stack['stack'], component['name'])
                variables = (resolved.get('effective') or {}).get('vars')
                policies = variables.get('policies') if isinstance(variables, dict) else None
                if not isinstance(policies, dict):
                    components.append(dict(row, policies=0, reason='no_policies_input'))
                    continue
                components.append(dict(row, policies=len(policies)))
                backend = _backend(resolved)
                candidates.extend(_candidate(store, str(repository), resolved, stack['stack'], component['name'], key,
                                             revision, backend, intents) for key in sorted(policies))
    for number, candidate in enumerate(candidates, 1):
        candidate['number'] = number
    return dict(base, status=status, blockers=blockers, revision=revision, components=components, candidates=candidates,
                next_action=_next_action(status, blockers, candidates, repository))
