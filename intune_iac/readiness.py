"""Readiness by operation for guided setup: a pure model over facts the product already gathers.

Inputs are plain dictionaries: the result of entry.survey, host_capabilities.report
and the doctor result (cli.doctor, which also carries the host report). The
function reads no network, no credential and no environment variable value, and
writes nothing. Every value copied into the result passes an allow-list of plain
shapes, so a field the model does not name, or a value that looks like a secret,
never reaches the output.

Operations, mapped from the four goals of the owner's setup guide (12.3, mode and goal):

  inspect  offline sample or capture: the product's start, inspect, wizard and simulated journey.
           Needs no service credential.
  discover read-only discovery of the live service: explicit read-only capture (capture, target
           collect). It gathers evidence; it changes nothing. It is called discover, not prepare,
           because the product already uses preparation for offline work and for adoption preparation.
  adopt    adoption preparation: the state-only native import prepared and reviewed with the
           adoption commands. Preparing does not need an execution route; approving the import
           later does.
  change   approved managed change: the product has no route for it yet (doctor reports
           cloud_apply as unavailable); the model says so instead of inventing one.

Rows are the eight items of the 12.3 table. A row is ready only when the inputs establish it;
anything they do not establish is unknown, never ready. A working sign-in never implies
permission for a change. Where the product has no implementation (sign-in reuse, OIDC,
per-operation scopes, CI identity), the row says so in words.
"""
from __future__ import annotations

import re

VERSION = 'workbench-readiness/1'
PROGRAM = 'intune-iac'
OPERATIONS = ('inspect', 'discover', 'adopt', 'change')
ROWS = (('mode_goal', 'Mode and goal'), ('tools_host', 'Tools and host'), ('repository', 'Repository'),
        ('integration_service', 'Integration and service'), ('iac_target', 'IaC target'), ('backend', 'Backend'),
        ('execution_route', 'Execution route'), ('secret_input', 'Exceptional secret input'))
NEEDS = {
    'inspect': frozenset({'mode_goal', 'tools_host'}),
    'discover': frozenset({'mode_goal', 'tools_host', 'integration_service', 'secret_input'}),
    'adopt': frozenset({'mode_goal', 'tools_host', 'repository', 'integration_service', 'iac_target', 'backend',
                        'secret_input'}),
    'change': frozenset(row for row, _ in ROWS),
}
# Host profiles each operation needs. Inspect and discover need none: capture and target collect have no profile gate
# (only the workbench observer needs graph_observer), so those two need Python packages only.
PROFILES = {'inspect': (), 'discover': (), 'adopt': ('protected_worker',), 'change': ('protected_worker',)}
# Executables looked up on the search path. Absence is a fact, never a missing tool: adoption takes its pins from the
# manifest, so a tool absent from the search path may still be supplied by an explicit pinned path.
EXECUTABLES = {'inspect': (), 'discover': (), 'adopt': ('atmos', 'tofu'), 'change': ('atmos', 'tofu')}
PINNED_ROUTE = ('If you rely on a pinned executable, pass it with %s wizard --session SESSION --journey --repo REPOSITORY '
                '--atmos-executable PATH --tofu-executable PATH, or %s repository native --root REPOSITORY --stack STACK '
                '--component COMPONENT --executable PATH; then run: %s doctor')
GIT_HOSTING = 'Git hosting and review identity are not checked by the product (it never invokes gh or a remote).'
KNOWN_EVIDENCE = ('no_live_connection', 'source_asserted_not_authenticated', 'modeled_service_no_authentication')
IDENTITY_KINDS = ('context', 'export', 'store', 'modeled_service')
NOT_NEEDED = 'Not needed for this operation.'
NO_ACTION = 'No action needed.'

NOT_ESTABLISHED = (
    'Working-directory access is not probed by the product.',
    'Git transport, GitHub host, organization, repository, branch, SSO, API and Actions access are not checked; '
    'the product never invokes gh or a remote.',
    'Environment variables and credential stores are not read, so token presence and credential expiry are unknown.',
    'Installed tool versions are not read; executables are only looked up on the search path.',
    'A source-asserted tenant is not checked against any sign-in.',
)

_GUID = re.compile(r'[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}')
_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_./@:+-]{0,119}')
_PATH = re.compile(r'[^\x00-\x1f\x7f]{1,300}')
_REVISION = re.compile(r'[0-9a-f]{40}')
_SECRETISH = re.compile(r'secret|token|passw|bearer|api[_-]?key|authorization|credential|=', re.I)
# An underscore or hyphen breaks a run, so long snake_case names pass while an unbroken token-like run is dropped.
_LONG_RUN = re.compile(r'[A-Za-z0-9+/]{32,}')


def _text(value, pattern=_NAME):
    """The string when it has a plain, bounded shape and does not look like a secret; otherwise None."""
    if (isinstance(value, str) and pattern.fullmatch(value) and not _SECRETISH.search(value)
            and not _LONG_RUN.search(value)):
        return value
    return None


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _row(operation, row_id, label, state, detected, missing, next_action, owner_role):
    """One row. A state of ready needs a displayable supporting fact; a row the operation does not need is not_needed.

    States follow one rule on every row: missing means the inputs establish an absence; unknown means they do not
    establish the item either way.
    """
    if row_id not in NEEDS[operation]:
        state, missing, next_action = 'not_needed', [], NOT_NEEDED
    elif state == 'ready' and not any(detected.values()):
        state, missing = 'unknown', list(missing) + ['No supporting fact could be displayed by this check.']
    return {'id': row_id, 'label': label, 'needed': row_id in NEEDS[operation], 'state': state,
            'detected': detected, 'missing': list(missing), 'next_action': next_action, 'owner_role': owner_role}


def _facts(survey, host, doctor, signin=None):
    """Allow-listed, validated facts from the three inputs; nothing else is read."""
    survey = _dict(survey)
    usable = isinstance(survey.get('items'), list)
    doctor = _dict(doctor)
    host = _dict(host) or _dict(doctor.get('host_capabilities'))
    items = [item for item in _list(survey.get('items')) if isinstance(item, dict)]
    repositories, targets, identities = [], [], []
    for item in items:
        kind, states = item.get('kind'), _dict(item.get('states'))
        if kind == 'repository':
            repositories.append(_repository(item, states))
        if kind == 'context':
            targets.append({'stack': _text(item.get('stack')), 'component': _text(item.get('component'))})
        if kind in IDENTITY_KINDS:
            evidence = states.get('authenticated')
            tenant = _text(item.get('tenant_id'), _GUID)
            identities.append({'kind': kind, 'tenant': tenant, 'named': item.get('tenant_id') not in (None, ''),
                               'evidence': evidence if evidence in KNOWN_EVIDENCE else 'unrecognized'})
    return {'survey': usable, 'host': bool(host), 'doctor': bool(doctor), 'items': items, 'repositories': repositories,
            'targets': targets, 'identities': identities, 'hostreport': host, 'doctorreport': doctor,
            'connection': survey.get('connection') if survey.get('connection') == 'offline' else None,
            'connection_unrecognized': usable and 'connection' in survey and survey['connection'] != 'offline',
            'directory': _text(survey.get('directory'), _PATH) if usable else None,
            'signin': signin if isinstance(signin, dict) and signin else None}


def _repository(item, states):
    revision = item.get('git_revision')
    raw = [c for c in _list(item.get('components')) if isinstance(c, dict)]
    shown = [{'stack': _text(c.get('stack')), 'component': _text(c.get('component'))} for c in raw]
    components = [c for c in shown if c['stack'] and c['component']]
    revision = revision if isinstance(revision, str) and _REVISION.fullmatch(revision) else None
    configured = states.get('configured') is True
    ready = configured and bool(components) and revision is not None
    return {'path': _text(item.get('path'), _PATH), 'components': components, 'revision': revision,
            'reason': _text(states.get('configured_reason')), 'hidden': len(raw) - len(components), 'ready': ready,
            # The product called it configured but this check cannot display what it needs: not the product's reason.
            'gap': configured and not ready}


# Mode and goal ---------------------------------------------------------------------------------------------------

def _mode_goal(operation, f):
    doctor = _dict(f['doctorreport'])
    capabilities = _dict(doctor.get('capabilities'))
    role, detected, missing, action = 'engineer', {}, [], NO_ACTION
    if operation == 'inspect':
        wizard = capabilities.get('wizard')
        if wizard == 'missing_dependencies':
            state, missing, action = 'missing', ['The local wizard reports missing Python packages.'], 'Run: %s doctor' % PROGRAM
        elif f['survey'] or wizard == 'available':
            state = 'ready'
            detected = {'goal': 'offline sample or capture', 'service_credential_needed': False}
            if f['connection']:
                detected['connection'] = f['connection']
        else:
            state, missing, action = 'unknown', ['Neither a survey nor the doctor result was provided.'], 'Run: %s start DIRECTORY' % PROGRAM
    elif operation == 'discover':
        route = capabilities.get('production_capture')
        if route == 'explicit_read_only_credentials_required':
            state, detected = 'ready', {'goal': 'read-only discovery', 'route': 'explicit read-only capture, credentials required'}
        elif route == 'unavailable_on_platform':
            state, missing = 'missing', ['Read-only production capture is unavailable on this platform.']
            action = 'Run on a POSIX host (for example Linux or WSL2); the product has no native Windows route for capture yet.'
        else:
            state, missing, action = 'unknown', ['The doctor result does not say whether read-only capture is available.'], 'Run: %s doctor' % PROGRAM
    elif operation == 'adopt':
        route = _text(_dict(_dict(doctor.get('route_scope')).get('adoption')).get('native_service_preparation'))
        if route:
            state, detected = 'ready', {'goal': 'adoption preparation', 'route': route, 'qualified_live': False}
        else:
            state, missing, action = 'unknown', ['The doctor result does not name an adoption preparation route.'], 'Run: %s doctor' % PROGRAM
    else:
        role = 'organization'
        if capabilities.get('cloud_apply') == 'unavailable':
            state, missing = 'missing', ['The doctor result reports cloud_apply as unavailable.']
            action = 'The product has no route yet for an approved managed change to the cloud.'
        else:
            state, missing, action = 'unknown', ['The doctor result does not establish a managed change route.'], 'Run: %s doctor' % PROGRAM
    return _row(operation, 'mode_goal', 'Mode and goal', state, detected, missing, action, role)


# Tools and host --------------------------------------------------------------------------------------------------

def _tools_host(operation, f):
    doctor, host = f['doctorreport'], f['hostreport']
    detected, missing, unknown, actions = {}, [], [], []
    facts = _dict(host.get('host'))
    for key in ('os_name', 'sys_platform', 'machine'):
        if _text(facts.get(key)):
            detected[key] = facts[key]
    if _text(facts.get('python_version')):
        detected['python_version'] = facts['python_version']
    if not doctor:
        unknown.append('The doctor result was not provided, so Python packages and tools are not established.')
    else:
        bad = sorted(name for name, entry in _dict(doctor.get('dependencies')).items()
                     if _text(name) and _dict(entry).get('available') is not True)
        if doctor.get('status') != 'ready' or bad:
            missing.append('Python packages not available: %s.' % (', '.join(bad) or 'see doctor'))
            actions.append('Install the pinned runtime requirements (requirements-runtime.txt) in your Python environment, '
                           'then run: %s doctor' % PROGRAM)
        else:
            detected['python_packages'] = 'available'
    for name in PROFILES[operation]:
        entry = _dict(_dict(host.get('profiles')).get(name))
        if entry.get('status') == 'IMPLEMENTED':
            detected.setdefault('profiles', {})[name] = 'IMPLEMENTED'
        elif entry.get('status') == 'UNSUPPORTED':
            gaps = [g for g in (_text(p) for p in _list(entry.get('missing_primitives'))) if g]
            missing.append('Host profile %s is unsupported here; missing primitives: %s.' % (name, ', '.join(gaps) or 'not named'))
            actions.append('Run on a Linux host (for example WSL2 Ubuntu); the product has no native Windows route for this '
                           'operation yet.')
        else:
            unknown.append('The host report does not establish the %s profile.' % name)
    found, absent = _dict(doctor.get('executables')), []
    for name in EXECUTABLES[operation]:
        if found.get(name) is True:
            detected.setdefault('executables_on_search_path', []).append(name)
        elif found.get(name) is False:
            detected.setdefault('executables_not_on_search_path', []).append(name)
            unknown.append('%s was not found on the search path; adoption takes its pinned tools from the manifest, so this does '
                           'not establish that a tool is missing.' % name)
            absent.append(name)
        else:
            unknown.append('The doctor result does not say whether %s is installed.' % name)
    if absent:
        actions.append(PINNED_ROUTE % (PROGRAM, PROGRAM, PROGRAM))
    if missing:
        state = 'missing'
    elif unknown:
        state = 'unknown'
    else:
        state = 'ready'
    # With a doctor result in hand, the gap is a fact it did not report (for example the tool lookup, which a caller may
    # leave out because it reads the search path): the engineer's step is to run doctor, not to pass a result anywhere.
    action = ' '.join(dict.fromkeys(actions)) or (NO_ACTION if state == 'ready' else
        'Run: %s doctor to see the host profiles and which tools are on the search path.' % PROGRAM if doctor else
        'Run %s doctor and pass its result, with the host report, to this check.' % PROGRAM)
    return _row(operation, 'tools_host', 'Tools and host', state, detected, missing + unknown, action, 'engineer')


# Repository and IaC target ---------------------------------------------------------------------------------------

REPOSITORY_ACTION = ('Run %s start REPOSITORY_DIRECTORY from a Git checkout that holds atmos.yaml with at least one selectable '
                     'stack and component; to enter a repository you maintain, run: %s workbench repository-entry --root STORE '
                     '--repo REPOSITORY (in the workspace: :repository-entry REPOSITORY)' % (PROGRAM, PROGRAM))


def _gap_text(repository):
    """Why a repository the product called configured cannot be used by this check; never a reason the product did not give."""
    name = repository['path'] or 'unnamed'
    if repository['hidden']:
        return 'Repository %s is configured, but component or stack names are not displayable by this check.' % name
    return 'Repository %s is configured, but this check cannot display a Git revision or a component for it.' % name


def _repository_row(operation, f):
    repositories = f['repositories']
    ready = [r for r in repositories if r['ready']]
    gaps = [r for r in repositories if r['gap']]
    shown = [dict({'path': r['path'], 'git_revision': (r['revision'] or '')[:12] or None, 'components': r['components']},
                  **({'components_not_displayed': r['hidden']} if r['hidden'] else {})) for r in repositories if r['path']]
    detected = {'repositories': shown} if shown else {}
    if not f['survey']:
        return _row(operation, 'repository', 'Repository', 'unknown', {}, ['No survey was provided.'],
                    'Run: %s start DIRECTORY and pass its result to this check.' % PROGRAM, 'engineer')
    action, missing = REPOSITORY_ACTION, []
    if ready:
        state, action = 'ready', NO_ACTION
    elif gaps:
        state, missing = 'unknown', [_gap_text(r) for r in gaps]
        action = 'Run: %s repository inspect --root REPOSITORY to see the stacks and components as the product lists them.' % PROGRAM
    elif not repositories:
        state, missing = 'missing', ['No Atmos repository (atmos.yaml) was found under the surveyed directory.']
    else:
        state = 'missing'
        missing = ['Repository %s is not usable: %s.%s' % (
            r['path'] or 'unnamed', (r['reason'] or 'the survey gives no displayable reason').replace('_', ' '),
            ' A Git checkout (a .git directory) is required.' if r['reason'] == 'not_a_git_repository' else '')
            for r in repositories]
    if operation == 'change':
        # The guide puts Git hosting and review identity in this row; the product checks neither.
        missing.append(GIT_HOSTING)
        if state == 'ready':
            state, action = 'unknown', 'The product has no route yet to check Git hosting or review identity.'
    return _row(operation, 'repository', 'Repository', state, detected, missing, action, 'engineer')


def _iac_target_row(operation, f):
    if not f['survey']:
        return _row(operation, 'iac_target', 'IaC target', 'unknown', {}, ['No survey was provided.'],
                    'Run: %s start DIRECTORY and pass its result to this check.' % PROGRAM, 'engineer')
    ready = [r for r in f['repositories'] if r['ready']]
    gaps = [r for r in f['repositories'] if r['gap']]
    if not ready and gaps:
        return _row(operation, 'iac_target', 'IaC target', 'unknown', {},
                    [_gap_text(r) + ' No target can be matched.' for r in gaps],
                    'Run: %s repository inspect --root REPOSITORY to see the stacks and components as the product lists them.' % PROGRAM,
                    'engineer')
    if not ready:
        return _row(operation, 'iac_target', 'IaC target', 'missing', {},
                    ['No repository with a selectable component was found, so no stack or component can be resolved.'],
                    REPOSITORY_ACTION, 'engineer')
    available = [(c['stack'], c['component']) for r in ready for c in r['components']]
    detected = {'selectable': [{'stack': s, 'component': c} for s, c in sorted(set(available))]}
    named = [(t['stack'], t['component']) for t in f['targets'] if t['stack'] and t['component']]
    exact = sorted({pair for pair in named if pair in available})
    if exact:
        detected = {'targets': [{'stack': s, 'component': c} for s, c in exact],
                    'effective_configuration': 'not_resolved_by_this_check'}
        action = '%s repository resolve --root REPOSITORY --stack %s --component %s (shows the effective configuration)' % (
            PROGRAM, exact[0][0], exact[0][1])
        return _row(operation, 'iac_target', 'IaC target', 'ready', detected, [], action, 'engineer')
    components = {c for _, c in available}
    near = [pair for pair in named if pair[1] in components]
    if near:
        text = ('A context names stack %s for component %s, but discovery lists %s; discovery alone cannot tell whether they are '
                'the same stack.' % (near[0][0], near[0][1], ', '.join(sorted({s for s, c in available if c == near[0][1]}))))
        return _row(operation, 'iac_target', 'IaC target', 'unknown', detected, [text],
                    '%s repository resolve --root REPOSITORY --stack STACK --component %s with the stack as the repository names it'
                    % (PROGRAM, near[0][1]), 'engineer')
    missing = ['The intended stack and component are not named by a context, or the context names none of the selectable ones.']
    state = 'missing'
    if any(r['hidden'] for r in ready):
        # Some component names were not displayable, so the context may name one of those.
        state = 'unknown'
        missing.append('Some component or stack names are not displayable by this check, so a match cannot be ruled out.')
    return _row(operation, 'iac_target', 'IaC target', state, detected, missing,
                'Put one selectable stack and component from "selectable" into the context JSON (examples/context.json shows the '
                'shape), then run: %s start DIRECTORY' % PROGRAM, 'engineer')


# Integration, backend, execution route, secret input ------------------------------------------------------------

NO_SIGN_IN_ROUTE = ('The product has no route yet for device-code or browser sign-in, OIDC, managed identity or '
                    'per-operation scopes.')
NOT_ACCESS = ('A signed-in account does not establish Graph, Intune or state-storage access; those stay unknown until a read '
              'actually succeeds.')
ACCESS_UNKNOWN = {'graph_access': 'unknown', 'intune_access': 'unknown', 'state_storage_access': 'unknown'}
# Verdicts after which the row is blocked on the sign-in itself (missing), and those that replace its next action.
SIGNIN_BLOCKS = ('wrong_tenant', 'not_signed_in', 'expired')
SIGNIN_STEPS = SIGNIN_BLOCKS + ('several_accounts', 'account_mismatch', 'unknown')


def _single_tenant(f):
    """The one displayed tenant the surveyed inputs name, or None when none, several, or one that cannot be shown."""
    identities = f['identities']
    tenants = sorted({i['tenant'] for i in identities if i['tenant']})
    hidden = any(i['named'] and not i['tenant'] for i in identities)
    return tenants[0] if len(tenants) == 1 and not hidden else None


def _signin_verdicts(f, single):
    """Verdicts (signin_facts.evaluate, pure) for the az and gh facts the caller supplied; empty when none were given."""
    from . import signin_facts
    given = f['signin'] or {}
    verdicts = {}
    if 'azure' in given:
        verdicts['azure'] = signin_facts.evaluate(given['azure'], single)
    if 'github' in given:
        verdicts['github'] = signin_facts.evaluate(given['github'])
    return verdicts


def _service_row(operation, f):
    if not f['survey']:
        return _row(operation, 'integration_service', 'Integration and service', 'unknown', {},
                    ['No survey was provided, so no tenant or connection is established.'],
                    'Run: %s start DIRECTORY and pass its result to this check.' % PROGRAM, 'engineer')
    identities = f['identities']
    tenants = sorted({i['tenant'] for i in identities if i['tenant']})
    evidence = sorted({i['evidence'] for i in identities})
    detected = {}
    if tenants:
        detected['tenants'] = tenants
    if evidence:
        detected['identity_evidence'] = evidence
    if f['connection']:
        detected['connection'] = f['connection']
    named_hidden = any(i['named'] and not i['tenant'] for i in identities)
    missing = []
    if not tenants and not named_hidden:
        missing.append('No tenant or cloud is selected (no context or export names one).')
    if named_hidden:
        missing.append('A tenant is named but not in GUID form; this check does not display it.')
    # A tenant that is named but not displayable still counts as a tenant: it may differ from the one shown.
    named = len(tenants) + (1 if named_hidden else 0)
    ambiguous = named >= 2
    if named == 2:
        missing.append('Two tenants are named by the surveyed inputs; choose one.')
    elif named > 2:
        missing.append('Several tenants are named by the surveyed inputs; choose one.')
    # Only a single, displayed tenant is compared with a sign-in; an ambiguous selection is never decided by the sign-in.
    single = _single_tenant(f)
    verdicts = _signin_verdicts(f, single)
    if verdicts:
        for name, label in (('azure', 'Azure'), ('github', 'GitHub')):
            if name in verdicts:
                detected['%s_sign_in' % name] = verdicts[name]['message']
                if verdicts[name]['status'] != 'signed_in':
                    missing.append('%s: %s' % (label, verdicts[name]['message']))
        detected.update(ACCESS_UNKNOWN)
        missing.append(NOT_ACCESS)
    else:
        missing.append('No verified sign-in, and no sign-in check was run: start with --goal %s --check-signin azure looks '
                       'for an existing Azure sign-in (it runs az account list --output json and nothing else).' % operation)
    if 'source_asserted_not_authenticated' in evidence:
        missing.append('The tenant is asserted by a file; nothing checks it against a sign-in.')
    missing.append(NO_SIGN_IN_ROUTE)
    if operation == 'change':
        missing.append('A working sign-in never implies permission for a change; the product records only observed reads.')
    else:
        missing.append('Read access for this operation is not checked per operation or scope.')
    # Missing only when nothing is selected. A tenant that is selected, named but not shown, or ambiguous is not an
    # absence, and neither is evidence or a connection kind the product never produces.
    absent = not tenants and not named_hidden
    state = 'missing' if absent and 'unrecognized' not in evidence and not f['connection_unrecognized'] else 'unknown'
    # Only a single, displayed tenant is filled into a command; any ambiguity keeps the placeholder (no silent pick).
    tenant = single or 'TENANT_ID'
    if operation == 'discover':
        action = ('%s capture --tenant %s --policy POLICY --output NEW_DIR --token-env TOKEN_VARIABLE_NAME (reads the named '
                  'variable; one of the explicit-token routes, target collect is another)' % (PROGRAM, tenant))
    else:
        action = ('%s target authenticate --input TARGET_JSON --provider-secret-fd FD --backend-secret-fd FD (read-only identity '
                  'binding with a client secret, Unix hosts only)' % PROGRAM)
    role = 'administrator'
    if absent:
        action = ('Provide a bounded context JSON (tenant, cloud, stack and component; examples/context.json shows the shape), '
                  'then run: %s start DIRECTORY' % PROGRAM)
        role = 'engineer'
    elif ambiguous:
        action = ('Choose one tenant by making the surveyed inputs name the same one, as a GUID, then run: %s start DIRECTORY. '
                  'Then: ' % PROGRAM) + action
        role = 'engineer'
    elif named_hidden:
        action = ('Name the tenant as a GUID in the context or export JSON, then run: %s start DIRECTORY' % PROGRAM)
        role = 'engineer'
    azure = verdicts.get('azure')
    if azure and single and azure['status'] in SIGNIN_STEPS:
        # The sign-in itself is the blocker, so its exact next step comes first. The row is never ready, whatever the sign-in.
        action, role = azure['next_step'], 'engineer'
        if azure['status'] in SIGNIN_BLOCKS:
            state = 'missing'
    return _row(operation, 'integration_service', 'Integration and service', state, detected, missing, action, role)


def _backend_row(operation, f):
    missing = ['Subscription, storage account, container and state key are in none of the inputs; the product reads them only '
               'from a target JSON the caller writes.',
               'State-backend principal access and locking are probed only inside target authenticate, not by this check.']
    action = ('Write the backend declaration into the target JSON and run: %s target authenticate --input TARGET_JSON '
              '--provider-secret-fd FD --backend-secret-fd FD; the product does not yet discover the backend from approved '
              'configuration.' % PROGRAM)
    return _row(operation, 'backend', 'Backend', 'unknown', {}, missing, action, 'administrator')


def _execution_row(operation, f):
    cloud_apply = _dict(_dict(f['doctorreport']).get('capabilities')).get('cloud_apply')
    missing = ['No approved repository workflow, environment or execution identity is read by the product.',
               'Local rights are not told apart from a CI identity, and protected approvals are not checked.']
    action = 'No route yet: the product cannot read a repository workflow or a CI identity'
    if cloud_apply == 'unavailable':
        state = 'missing'
        missing.append('The doctor result reports cloud_apply as unavailable.')
        action += ', and the doctor result reports cloud_apply as unavailable'
    else:
        state = 'unknown'
    action += '. A managed change needs an execution route and approvals from your organization.'
    return _row(operation, 'execution_route', 'Execution route', state, {}, missing, action, 'organization')


def _secret_row(operation, f):
    missing = ['This check does not read environment variables or credential stores, so it cannot say whether a token is present.',
               'There is no insecure-storage detection, expiry, renewal or revocation display, and no secure-reference adapter '
               '(for example 1Password) yet.']
    if operation == 'discover':
        action = ('Provide the read token only to this one command: %s capture --tenant TENANT_ID --policy POLICY --output NEW_DIR '
                  '--token-env TOKEN_VARIABLE_NAME (through the environment variable that flag names, from your approved secret '
                  'manager; never on a command line, because the flag takes the name, not the value).' % PROGRAM)
    else:
        action = ('Use the inherited file-descriptor route: %s target authenticate --input TARGET_JSON --provider-secret-fd FD '
                  '--backend-secret-fd FD (a secret is never accepted as an argument); there is no secure-reference route yet.'
                  % PROGRAM)
    return _row(operation, 'secret_input', 'Exceptional secret input', 'unknown', {}, missing, action, 'administrator')


BUILDERS = (_mode_goal, _tools_host, _repository_row, _service_row, _iac_target_row, _backend_row, _execution_row, _secret_row)


def _operation(operation, f):
    rows = [build(operation, f) for build in BUILDERS]
    blocking = [row for row in rows if row['needed'] and row['state'] != 'ready']
    if any(row['state'] == 'missing' for row in blocking):
        status = 'missing'
    elif blocking:
        status = 'unknown'
    else:
        status = 'ready'
    return {'status': status, 'rows': rows, 'blocking': [row['id'] for row in blocking],
            'blockers': [{'row': row['id'], 'state': row['state'], 'next_action': row['next_action'],
                          'owner_role': row['owner_role']} for row in blocking]}


def readiness(survey=None, host=None, doctor=None, signin=None):
    """Readiness by operation and row from entry.survey, host_capabilities.report and doctor facts; pure and offline."""
    f = _facts(survey, host, doctor, signin)
    result = {'schema_version': VERSION, 'inputs': {'survey': f['survey'], 'host': f['host'], 'doctor': f['doctor']},
              'directory': f['directory'], 'operations': {operation: _operation(operation, f) for operation in OPERATIONS},
              'not_established': list(NOT_ESTABLISHED), 'execution_authorized': False, 'cloud_authority': False}
    if f['signin']:
        result['signin'] = _signin_verdicts(f, _single_tenant(f))
    return result
