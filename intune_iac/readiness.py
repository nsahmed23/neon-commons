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
# What each placeholder in a printed step stands for. The meaning goes in a legend in brackets after the command, never inside it:
# a command is read up to its first opening bracket (start's screen and its tests do), so a bracket inside would cut it in two.
PLACEHOLDER_MEANINGS = {
    'TENANT_ID': 'the tenant id the context names',
    'POLICY': 'the policy id, a GUID',
    'NEW_DIR': 'a folder that does not exist yet',
    'TOKEN_VARIABLE_NAME': 'the name of the environment variable that holds your read token',
    'TARGET_JSON': 'the path of your target JSON file',
    'FD': 'a file descriptor number your shell has open on the secret',
}


def with_legend(command, note=''):
    """The command followed by one bracket: what each placeholder in it stands for (in order of appearance), then the note."""
    found = sorted((match.start(), name) for name in PLACEHOLDER_MEANINGS
                   for match in [re.search(r'(?<![A-Z_])%s(?![A-Z_])' % name, command)] if match)
    parts = ['%s is %s' % (name, PLACEHOLDER_MEANINGS[name]) for _, name in found] + ([note] if note else [])
    return '%s (%s)' % (command, '; '.join(parts)) if parts else command


# What the capture command does with the token, read from capture.py: it sends it to the host of capture.GRAPH_ROOT in GET requests
# and writes what it read into the one new folder it is given. The legend a step records says only that it reads the named variable
# (that wording is part of the JSON forms and stays); a screen adds this sentence after the step.
CAPTURE_CONTACT = ('The capture command sends the token to %s in GET requests only (it reads, and changes nothing in the tenant) '
                   'and writes what it reads into NEW_DIR.')


# A word as the shell reads it: a run of characters, or a quoted run (a path with a space in it is one word).
_WORD = re.compile(r"(?:'[^']*'|[^\s'])+")


def command_names(text):
    """The subcommand of each `intune-iac` command a printed step holds, read where a command stands: the program word first, or
    after a lead-in word that ends in a colon ("Run:", "Then:", "command:"). A program name inside a quoted path, inside a longer
    word or in the middle of a sentence is not a command, so no step is taken to run a command because of a path in it."""
    words = _WORD.findall(text)
    return [words[index + 1] for index, word in enumerate(words[:-1])
            if word == PROGRAM and (index == 0 or words[index - 1].endswith(':'))]


# Words that end a command: a lowercase word after the program word that is prose, not a subcommand.
_PROSE = frozenset(('and', 'or', 'then', 'from', 'with', 'to', 'for', 'in', 'as', 'the', 'a', 'is', 'it', 'its', 'pass', 'shows',
                    'see', 'run', 'of', 'on', 'by', 'when', 'that', 'this', 'at'))
_SUBCOMMAND = re.compile(r'[a-z][a-z-]*\Z')


def commands_in(step):
    """Each `intune-iac` command a printed step holds, as (begin, end, head, operands): where it starts and ends in the text, its
    subcommand words (at most two) and its operands (the values of flags and a lone positional operand, in order). A command runs
    from the program word, as a word of its own, to the last word that belongs to it: a flag, the value after a flag, a positional
    operand that is a placeholder, a quoted path or a path, or a leading subcommand word; the first prose word, an opening
    parenthesis or a word that ends in sentence punctuation (which that word still belongs to) ends it. The reading is for the
    steps the product records, not for a shell."""
    from .entry import is_fill_in
    words = list(_WORD.finditer(step))
    found, index = [], 0
    while index < len(words):
        if words[index].group() != PROGRAM:
            index += 1
            continue
        begin, end, head, operands, after_flag = words[index].start(), words[index].end(), [], [], False
        index += 1
        while index < len(words):
            raw = words[index].group()
            word = raw.rstrip(',;.:') if len(raw) > 1 else raw
            if not word or word.startswith('('):
                break
            if word.startswith('-'):
                take, after_flag = True, True
            elif after_flag:
                take, after_flag = True, False
                operands.append(word)
            elif not operands and len(head) < 2 and _SUBCOMMAND.match(word) and word not in _PROSE:
                take = True
                head.append(word)
            elif is_fill_in(word) or word.startswith("'") or '/' in word:
                take = True
                operands.append(word)
            else:
                break
            end = words[index].start() + len(word)
            index += 1
            if word != raw:
                break                                    # the sentence ends with this word
        found.append((begin, end, head, operands))
    return found


def command_operands(step):
    """The operands of every command in a printed step (see commands_in)."""
    return [operand for _, _, _, operands in commands_in(step) for operand in operands]


# What each placeholder in a printed command asks the person to name, for a screen that says the command in words. One table for the
# start screen and the catalog; entry.FILL_IN_TEMPLATES has an entry here for every placeholder (a test checks it).
TEMPLATE_WORDS = {
    'DIRECTORY': 'the directory to survey',
    'PATH': 'the path of the executable',
    'ROOT': 'the folder',
    'ID': 'the id',
    'SERVICE_ROOT': 'your service folder',
    'TENANT_ID': 'your tenant id',
    'STORE': 'your store folder',
    'CONTEXT_JSON': 'your context file',
    'EXPORT_JSON': 'your export file',
    'REPOSITORY': 'your repository folder',
    'NEW_OUTPUT_DIR': 'a new output folder',
    'NEW_SESSION': 'a new session file',
    'POLICY': 'the policy id (a GUID)',
    'NEW_DIR': 'a new folder for the output',
    'TOKEN_VARIABLE_NAME': 'the name of the environment variable that holds the token',
    'TARGET_JSON': 'the path of your target JSON file',
    'FD': 'a file descriptor number your shell has open on the secret',
    'REPOSITORY_DIRECTORY': 'the folder of your Git checkout',
    'SESSION': 'a session file',
    'STACK': 'the stack name',
    'COMPONENT': 'the component name',
}
_PLACEHOLDER_NAME = re.compile(r'[A-Z][A-Z0-9_]*[A-Z0-9]')
_LEGEND = re.compile(r' \(([^()]*)\)')
_WORKSPACE_ENTRY = re.compile(r'(:repository-entry) ([A-Z][A-Z0-9_]*[A-Z0-9])(?=\)|\s|\Z)')


def _described(operands):
    """The descriptions of the placeholders among the operands, each once, as one phrase."""
    from .entry import is_fill_in
    said = []
    for operand in operands:
        if is_fill_in(operand):
            text = TEMPLATE_WORDS[_PLACEHOLDER_NAME.match(operand).group()]
            if text not in said:
                said.append(text)
    if len(said) < 2:
        return said[0] if said else ''
    return ', '.join(said[:-1]) + ' and ' + said[-1]


def placeholders_in_words(step):
    """A recorded step as a human text form prints it: every command of it that has a placeholder as an operand (entry.
    FILL_IN_TEMPLATES) is said in words, because a placeholder in a command is a name to a shell (STORE or POLICY is a valid
    relative path) or makes the command fail when it is copied. The step's own lead stays; the command becomes "the <command>
    command, naming" and one description per placeholder (TEMPLATE_WORDS); the legend after it that only explained the placeholders
    goes, because the descriptions carry it, and anything else in that legend stays. A command with no placeholder, and every
    other part of the step, is unchanged. The machine forms (the JSON of start and the catalog) keep the recorded step: this is
    for the human text only, and it is applied after without_stand_in, which says a command for a hidden directory."""
    if not step:
        return step
    out, at = [], 0
    for begin, end, head, operands in commands_in(step):
        said = _described(operands)
        if not said or begin < at:
            continue
        out += [step[at:begin], 'the %s command, naming %s' % (' '.join(head) or 'named', said)]
        at = end
        legend = _LEGEND.match(step, at)
        if legend:
            parts = legend.group(1).split('; ')
            kept = [part for part in parts if not re.match(r'(?:%s) is ' % '|'.join(PLACEHOLDER_MEANINGS), part)]
            if len(kept) < len(parts):
                if kept:
                    out.append(' (%s)' % '; '.join(kept))
                at = legend.end()
        if re.match(r' [a-z]', step[at:]):
            out.append(',')
    out.append(step[at:])
    return _WORKSPACE_ENTRY.sub(lambda m: 'the %s command, naming %s' % (m.group(1), _described([m.group(2)])) if m.group(2) in TEMPLATE_WORDS
                                else m.group(0), ''.join(out))


def capture_contact(text):
    """The sentence that says where capture sends the token, for a printed step that runs the capture command (as command_names
    reads it, never a substring of the text); '' for any other step."""
    if 'capture' not in command_names(text) and 'the capture command, naming' not in text:    # as printed, or said in words
        return ''
    from urllib.parse import urlsplit
    from .capture import GRAPH_ROOT
    return CAPTURE_CONTACT % urlsplit(GRAPH_ROOT).netloc


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
# The note the model records when no sign-in check was run. The JSON forms (start --json, catalog --json) carry it as recorded, so
# it is frozen; a screen says it through screen_note instead, in two sentences with the command on its own rows.
NO_CHECK_RECORDED = ('No verified sign-in, and no sign-in check was run: start with --goal %s --check-signin azure looks '
                     'for an existing Azure sign-in (it runs az account list --output json and nothing else).')
NO_CHECK_SCREEN = ('No sign-in check was run. To look for an existing Azure sign-in, run: %s start %s--goal %s --check-signin azure '
                   '(%sit runs az account list --output json and nothing else).')
# What a screen says, in the same words whatever the reason a directory was refused, when it prints DIRECTORY in the directory's
# place: on its own line under the header (the screen says it once), or inside a note's bracket when the note stands alone.
DIRECTORY_NOT_SHOWN_STEM = 'DIRECTORY is the directory this screen is about; its name is not shown here'
DIRECTORY_NOT_SHOWN = DIRECTORY_NOT_SHOWN_STEM + '; '
DIRECTORY_NOT_SHOWN_SENTENCE = DIRECTORY_NOT_SHOWN_STEM + '.'


def display_refused(value):
    """True when a screen must not print a path operand: the rule that guards the output path of signin collect refuses it
    (signin_facts.output_display: printable, within its limit, and not credential-shaped as a whole or in any piece), or terminal
    escaping would change it (workbench_tui.safe_text(value) != value: a combining mark, a format character and the like), which
    would make a command shown for copying address another path. The value is user input and may be anything. Nothing to show
    (an empty value) has nothing to hide."""
    if not value:
        return False
    from .signin_facts import OUTPUT_NOT_SHOWN, output_display
    if output_display(value) == OUTPUT_NOT_SHOWN:
        return True
    from .workbench_tui import safe_text
    return safe_text(value) != value


# The surveyed directory is one path operand like the others.
directory_hidden = display_refused


NO_CHECK_HIDDEN = ('No sign-in check was run. To look for an existing Azure sign-in, run the start command with this directory, '
                    '--goal %s and --check-signin azure (the directory cannot be shown here; it runs az account list '
                    '--output json and nothing else).')
# What a screen that may not show the directory says in place of a recorded step that names it: words, not a command (DIRECTORY is
# a valid relative path, so a copied command would address that folder).
IN_WORDS = 'the %s command with this directory (the directory cannot be shown here)'
NO_NAME_WORDS = 'this step names the directory, which cannot be shown here'
MAY_NAME_WORDS = 'this step may name the directory, which cannot be shown here'
DIRECTORY_COMMANDS = ('start', 'catalog')
_SEPARATOR = re.compile(r'( && | \|\| | \| |; )')
# Characters with which bash can produce text that is not in its input: expansions ($ and the backtick), tilde, braces, globs,
# history and redirections; and the extended-glob openers @( and +( (the others, ?( *( !(, hold a character above).
_GENERATING = frozenset('$`~{}*?[]!^<>')
_EXTGLOB = ('@(', '+(')
_TOKEN = re.compile(r'(?<![A-Za-z0-9_])DIRECTORY(?![A-Za-z0-9_])')
_COMMAND = re.compile(r'%s[ \t]+(%s)\b' % (re.escape(PROGRAM), '|'.join(DIRECTORY_COMMANDS)))


def without_stand_in(step):
    """A recorded step as a screen that may not show the directory prints it. Safety does not depend on parsing the shell.

    The producers are the product's own recorded steps: the readiness rows' notes and next actions in this module and the
    catalog's own sentences in catalog.py. A line is cut into parts only at ' && ', ' || ', ' | ' and '; ', and each part is
    judged alone by two rules.
    1. A part holding a GENERATING character ($ ` ~ { } * ? [ ] ! ^ < >) or an extended-glob opener (@( or +(; ?( *( !( hold a
       character above) becomes words: with one, bash can produce text that is not in the input (an expansion, a glob, an
       extended glob matching a directory named DIRECTORY, a tilde, a brace), so nothing about the input can be said.
    2. Otherwise bash can only DELETE characters (quote removal, backslash removal, comments, word splitting), so every letter it
       outputs appears in the input, in order. The part becomes words if the uppercase letters D I R E C T O R Y appear in it in
       order (case-sensitive, anything between them ignored), which any DIRECTORY bash outputs would require.
    Every other part stays byte for byte, prose with parentheses, double quotes and semicolons included. A replaced part that holds
    a start or catalog command is the sentence for it; any other replaced part is a generic sentence (it says the step names the
    directory when the word is there, and that it may name it when only a generating character or the letters in order are).

    The cost is over-replacement: a part is replaced when the letters happen to appear in order or a generating character is
    present, though it need not name the directory. It can never under-replace.

    Both rules read the part with every backslash-newline pair removed, as bash joins them before it tokenizes (so a continuation
    cannot split an opener such as plus and an opening parenthesis, or the letters of DIRECTORY).

    Scope of the guarantee: bash reading the product's text as written. It assumes that no user alias or function redefines a
    command word (an alias is the user's own shell configuration, outside the product's text, and is NOT covered), and it holds
    with or without extglob and globbing. The test_shell_differential module checks the argument against bash, part by part:
    safety is exact (also with $0 and the positional parameters set to DIRECTORY, and with extglob on and globbing enabled in a
    directory that holds a directory named DIRECTORY), no part without a generating character or the letters in order ever has
    DIRECTORY among bash's words, and the implementation equals the rule."""
    if not step:
        return step
    pieces = _SEPARATOR.split(step)
    for index in range(0, len(pieces), 2):
        part = pieces[index]
        # bash joins a backslash-newline before it tokenizes, so the tests read a copy without the pairs
        joined = part.replace('\\\n', '')
        letters = iter(joined)
        if not (any(char in _GENERATING for char in joined) or any(opener in joined for opener in _EXTGLOB)
                or all(letter in letters for letter in 'DIRECTORY')):
            continue
        # the wording (not the decision) is chosen on a copy with quotes and backslashes removed, so intune-"iac" and a tab count
        plain = re.sub(r'''['"\\]''', '', joined)
        command = _COMMAND.search(plain)
        said = (IN_WORDS % command.group(1) if command else
                NO_NAME_WORDS if _TOKEN.search(plain) else MAY_NAME_WORDS)
        pieces[index] = part[:len(part) - len(part.lstrip(' '))] + said + part[len(part.rstrip(' ')):]
    return ''.join(pieces)


def screen_note(note, operand=None, legend='', hidden=False):
    """A recorded note as a screen says it: the recorded no-sign-in-check note in two grammatical sentences, the command on its
    own rows (a screen puts every printed command there); any other note as it is.

    The command names the surveyed directory, so that it runs on what the screen is about and not on the directory it is typed
    in. operand is that directory as a command argument, already written by the screen's path writer (entry.text_paths: DIRECTORY
    for a name the screen may not show, otherwise a quoted path relative to where the command runs); this function neither
    quotes nor decides. legend is what the note says in its bracket when it stands alone and its operand is DIRECTORY (the
    DIRECTORY_NOT_SHOWN words, the same whatever the reason a name was refused); a screen that has said it under its header passes
    nothing, so that the screen says it once. hidden: the screen may not show the directory and prints no command for it (the
    catalog; DIRECTORY would be a real folder to a shell): the note then says the instruction in words (NO_CHECK_HIDDEN)."""
    where = operand + ' ' if operand else ''
    for operation in OPERATIONS:
        if note == NO_CHECK_RECORDED % operation:
            if hidden:
                return NO_CHECK_HIDDEN % operation
            return NO_CHECK_SCREEN % (PROGRAM, where, operation, legend)
    return note


NOT_ACCESS = ('A signed-in account does not establish Graph, Intune or state-storage access; those stay unknown until a read '
              'actually succeeds.')
ACCESS_UNKNOWN = {'graph_access': 'unknown', 'intune_access': 'unknown', 'state_storage_access': 'unknown'}
# Verdicts after which the row is blocked on the sign-in itself (missing), and those that replace its next action.
SIGNIN_BLOCKS = ('wrong_tenant', 'not_signed_in', 'expired', 'subscription_expired')
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
        missing.append(NO_CHECK_RECORDED % operation)
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
        action = with_legend('%s capture --tenant %s --policy POLICY --output NEW_DIR --token-env TOKEN_VARIABLE_NAME'
                             % (PROGRAM, tenant), 'reads the named variable; one of the explicit-token routes, target collect is another')
    else:
        action = with_legend('%s target authenticate --input TARGET_JSON --provider-secret-fd FD --backend-secret-fd FD' % PROGRAM,
                             'read-only identity binding with a client secret, Unix hosts only')
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
    if azure and single and azure['usable'] and operation == 'discover':
        # Offered, never run: the engineer asks for it. Usable means only that the sign-in is in the right tenant.
        action = with_legend('%s signin collect --tenant %s --policy POLICY --output NEW_DIR' % (PROGRAM, single),
                             'the Azure CLI gives a short-lived read token to the collecting command on an inherited file '
                             'descriptor; whether it can read is known only after it does')
        role = 'engineer'
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
    action = ('Write the backend declaration into the target JSON and run: %s; the product does not yet discover the backend '
              'from approved configuration.'
              % with_legend('%s target authenticate --input TARGET_JSON --provider-secret-fd FD --backend-secret-fd FD' % PROGRAM))
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
        # Only a single, displayed tenant is filled into a command (as in the integration row); otherwise the marked placeholder.
        tenant = _single_tenant(f) or 'TENANT_ID'
        action = ('Provide the read token only to this one command: %s.'
                  % with_legend('%s capture --tenant %s --policy POLICY --output NEW_DIR --token-env TOKEN_VARIABLE_NAME'
                                % (PROGRAM, tenant), 'through the environment variable that flag names, from your approved secret '
                                'manager; never on a command line, because the flag takes the name, not the value'))
    else:
        action = ('Use the inherited file-descriptor route: %s; there is no secure-reference route yet.'
                  % with_legend('%s target authenticate --input TARGET_JSON --provider-secret-fd FD --backend-secret-fd FD'
                                % PROGRAM, 'a secret is never accepted as an argument'))
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
