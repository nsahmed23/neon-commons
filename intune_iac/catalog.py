"""The integration catalog: what this build holds, built from recorded facts only.

One record per integration in the capability manifest (today one: Intune). For each goal the record keeps six states
apart, because a fresh engineer must be able to tell them apart:

    available        this build implements the goal for the integration (the manifest lists its operations)
    configured       the local inputs the goal needs are present (readiness rows for mode, tools, repository, IaC target
                     and backend); the service, execution route and secret rows are not "configuration" and stay out
    authenticated    a usable existing sign-in, only when the engineer asked for the check (signin verdict); otherwise
                     "not checked". A sign-in is never permission for an operation.
    operation-ready  the readiness model's status for the goal is ready
    blocked          the first prerequisite the readiness model reports as not ready, with its next action
    unsupported      an operation the manifest does not list

The screen adds a seventh row, `live`: the live status and the live blockers as recorded. They belong to the product, not to the
goal, so they stay apart from blocked (this goal, here) and unsupported (what the manifest does not list); the JSON form keeps
them under `unsupported`. The JSON form is a frozen compatibility form (test_catalog_json_golden): the screen's own wording,
such as the verdict beside each next action, lives in catalog_lines only.

An object kind shows a qualification word only where the manifest's level record establishes it; otherwise it reads
"unknown (no record establishes it)". Nothing is inferred from a family name, and nothing the manifest does not hold is
listed. The module reads no network, no credential and no environment value; the sign-in verdict is given to it.

Two builds of the same catalog come out of build(): the JSON build (the dict itself, a frozen form) and, as the attribute text_build
of that dict, the text build a screen prints. They hold the same states and verdicts; only the strings that carry paths differ,
because the text build writes each command from its path operands (entry.text_paths): a directory the screen may not show is
DIRECTORY plus the remainder, an operand it cannot show faithfully is PATH, and nothing is patched into rendered text.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import integration_manifest, readiness as readiness_model
from .entry import STATE_LEGEND, STATE_WORDS, screen_words

VERSION = 'integration-catalog/1'
STATES = ('available', 'configured', 'authenticated', 'operation_ready', 'blocked', 'unsupported')
UNKNOWN_LEVEL = 'unknown (no record establishes it)'
NO_OTHERS = 'No other integration is available in this build.'
# The product's own reading of each goal as manifest operation names. It is a mapping of words, not a claim about
# qualification; a goal whose operations the manifest does not list is reported unsupported.
GOAL_OPERATIONS = {
    'inspect': ('inventory', 'selection', 'validation'),
    'discover': ('discovery',),
    'adopt': ('ownership', 'mapping', 'adoption'),
    'change': ('plan', 'approval', 'execute', 'reconcile'),
}
# Readiness rows that are local inputs; the service, execution route and secret rows are not configuration.
CONFIGURATION_ROWS = ('mode_goal', 'tools_host', 'repository', 'iac_target', 'backend')
SIGNIN_CHECK = ('Sign-in is not checked. Run: intune-iac catalog %s--check-signin azure (it runs az account list '
                '--output json and nothing else, and reads no token).')
# A screen that may not show the directory prints no command for it: a stand-in such as DIRECTORY is a valid relative path, so a
# copied command would address that folder. It says what is missing, in the words the workflow layer uses.
DIRECTORY_CANNOT_BE_SHOWN = 'the directory cannot be shown here'
DIRECTORY_NOT_KNOWN = 'the directory is not known here'
COMMAND_NOT_SHOWN = 'the command names a path whose name is not shown here'
SIGNIN_CHECK_HIDDEN = ('Sign-in is not checked. To look for an existing Azure sign-in, run the catalog command with %s '
                       '(%s; it runs az account list --output json and nothing else, and reads no token).')
NOT_PERMISSION = 'A sign-in is not permission for any operation; access to Graph, Intune and state storage is not established.'
# The manifest's evidence class of an operation that runs only as a bounded local process against the modeled service, and the
# live blocker it records for the missing cloud route.
MODELED_ONLY = 'synthetic_local_process_only'
NO_CLOUD_ROUTE = 'cloud_executor_unavailable'
RESUME_BASE = 'Resume commands are typed from the directory this catalog was run in; a path outside it is printed in full.'


def _available(manifest, goal):
    listed = {}
    for kind in manifest['object_kinds']:
        for operation in kind['operations']:
            listed.setdefault(operation['name'], set()).add(operation['evidence_class'])
    wanted = GOAL_OPERATIONS[goal]
    present = [name for name in wanted if name in listed]
    missing = [name for name in wanted if name not in listed]
    classes = sorted({cls for name in present for cls in listed[name]})
    kinds = [kind['id'] for kind in manifest['object_kinds']
             if any(operation['name'] in wanted for operation in kind['operations'])]
    state = 'available' if wanted and not missing else 'not_available'
    return {'state': state, 'operations': present, 'missing_operations': missing, 'evidence_classes': classes,
            'object_kinds': kinds}


def _configured(operation):
    rows = [row for row in operation['rows'] if row['needed'] and row['id'] in CONFIGURATION_ROWS]
    lacking = [row['label'] for row in rows if row['state'] != 'ready']
    if any(row['state'] == 'missing' for row in rows):
        state = 'no'
    elif lacking:
        state = 'unknown'
    else:
        state = 'yes'
    return {'state': state, 'inputs_checked': [row['label'] for row in rows], 'not_ready': lacking}


def _authenticated(signin, goal_flag):
    verdict = (signin or {}).get('azure')
    if not verdict:
        return {'state': 'not_checked', 'message': SIGNIN_CHECK % goal_flag, 'permission': NOT_PERMISSION}
    status = verdict.get('status')
    if verdict.get('usable') is True:
        state = 'authenticated'
    elif status == 'unknown':
        state = 'unknown'
    else:
        state = 'not_authenticated'
    return {'state': state, 'status': status, 'message': verdict.get('message'), 'next_step': verdict.get('next_step'),
            'permission': NOT_PERMISSION}


def _blocked(operation):
    for row in operation['rows']:
        if row['needed'] and row['state'] != 'ready':
            return {'state': 'blocked', 'row': row['label'], 'row_state': row['state'],
                    'missing': row['missing'][0] if row['missing'] else None, 'next_action': row['next_action']}
    return {'state': 'not_blocked', 'row': None, 'row_state': None, 'missing': None, 'next_action': None}


def _unsupported(available, manifest):
    reasons = ['The manifest lists no %s operation for any object kind.' % name for name in available['missing_operations']]
    return {'state': 'unsupported' if reasons else 'none_recorded', 'reasons': reasons,
            'live_blockers': list(manifest['live_blockers'])}


def _goal(manifest, model, signin, goal, flag):
    operation = model['operations'][goal]
    available = _available(manifest, goal)
    return {'goal': goal, 'available': available, 'configured': _configured(operation),
            'authenticated': _authenticated(signin, flag),
            'operation_ready': {'state': 'yes' if operation['status'] == 'ready' else 'no', 'status': operation['status']},
            'blocked': _blocked(operation), 'unsupported': _unsupported(available, manifest),
            'next_action': _blocked(operation)['next_action'] or 'No action needed.'}


def _kind(manifest, kind):
    classes = sorted({operation['evidence_class'] for operation in kind['operations']})
    record = kind['level_record']
    return {'id': kind['id'], 'label': kind['label'], 'family': kind['family'],
            'level': kind['level'] if record else UNKNOWN_LEVEL, 'level_record': record['path'] if record else None,
            'scope': kind['level_note'], 'evidence_classes': classes,
            'operations': [operation['name'] for operation in kind['operations']]}


def _family(entry):
    live = entry['live']
    return {'family': entry['family'], 'release_stage': entry['release_stage'] or 'not recorded',
            'live': 'not run' if live == 'not_run' else (live.replace('_', ' ') if live else 'not recorded'),
            'object_kind': entry['object_kind']}


def _state_words(item):
    states = item['states']
    configured = 'usable here' if states.get('configured') else 'not usable here: %s' % str(
        states.get('configured_reason', 'incomplete')).replace('_', ' ')
    return ' | '.join(['discovered', configured, STATE_WORDS.get(states['authenticated'], states['authenticated']),
                       STATE_WORDS.get(states['qualified'], states['qualified'])])


def _resume(item, items, q):
    """(command, note) to pick the project up again. A project with nothing to resume says so; no command is invented.
    q writes a path operand as a command argument (entry.json_paths for the JSON form, entry.text_paths for a screen)."""
    kind = item['kind']
    path = item['path']
    stores = [s for s in items if s['kind'] == 'store' and (s['states']['configured'] or s.get('tenant_id'))]
    if kind == 'wizard_session' and item.get('valid'):
        if item.get('step') != 'complete':
            return 'intune-iac wizard --session %s' % q(path), None
        return None, 'complete; nothing to resume'
    if kind == 'journey_session' and item.get('valid'):
        if item.get('lifecycle') != 'complete_simulation':
            return 'intune-iac wizard --journey --session %s' % q(path), None
        return None, 'complete; nothing to resume'
    if kind == 'guided_session' and item.get('valid'):
        if item.get('lifecycle') != 'complete_local':
            return 'intune-iac wizard --guided --session %s' % q(path), None
        return None, 'complete; nothing to resume'
    if kind == 'store':
        service = next((s for s in items if s['kind'] == 'modeled_service' and s.get('tenant_id') == item.get('tenant_id')), None)
        return 'intune-iac workbench workspace --root %s%s' % (q(path), ' --service-root ' + q(service['path']) if service else ''), None
    if kind == 'repository':
        if stores:
            return 'intune-iac workbench repository-entry --root %s --repo %s' % (q(stores[0]['path']), q(path)), None
        return 'intune-iac workbench init --root STORE --tenant TENANT_ID', None
    if kind == 'operation':
        return 'intune-iac workbench delivery --operation %s' % q(path), None
    if kind == 'export':
        context = next((s for s in items if s['kind'] == 'context'), None)
        return ('intune-iac wizard --session NEW_SESSION.json --input %s --context %s --output NEW_OUTPUT_DIR' % (
            q(path), q(context['path']) if context else 'CONTEXT_JSON')), None
    if item.get('valid') is False or item['states'].get('configured_reason') in (
            'session_invalid', 'service_unreadable', 'repository_unreadable'):
        return None, 'unreadable; nothing to resume'
    return None, 'nothing to resume from here'


def projects(survey, relative_to=None, paths=None):
    """The surveyed directory's stores, sessions, repositories and operations with state and one resume command each.
    paths is (show, q) from entry.json_paths (the default, the JSON form) or entry.text_paths (a screen)."""
    from . import entry
    items = survey.get('items') or []
    show, q = paths if paths is not None else entry.json_paths(Path(survey['directory']) if survey.get('directory') else None,
                                                               relative_to)
    rows = []
    for item in items:
        command, note = _resume(item, items, q)
        rows.append({'kind': item['kind'], 'label': entry.LABELS.get(item['kind'], item['kind']), 'path': item['path'],
                     'summary': entry._summary(item), 'state': _state_words(item), 'command': command, 'note': note})
    return rows


def _signin_flag(operand, goal):
    """The words that name the directory (and the goal) in the sign-in check command. operand is the directory as a command
    argument, written by a path writer (entry.json_paths for the JSON form, entry.text_paths for a screen); None without one."""
    where = operand + ' ' if operand else ''
    return where + ('' if goal is None else '--goal %s ' % goal)


def _signin_message(operand, goal, hidden):
    """The unchecked sign-in message as a screen says it. With a directory operand the screen may show, the command; where the
    directory is refused, the same instruction in words, with no command and no stand-in operand."""
    if hidden:
        options = ['this directory'] + (['--goal %s' % goal] if goal else []) + ['--check-signin azure']
        return SIGNIN_CHECK_HIDDEN % (', '.join(options[:-1]) + ' and ' + options[-1], DIRECTORY_CANNOT_BE_SHOWN)
    return SIGNIN_CHECK % _signin_flag(operand, goal)


def build(survey, doctor=None, signin=None, manifest=None, goal=None, relative_to=None):
    """The catalog as plain data. `survey` is entry.survey's result; `doctor` the doctor result (default: the offline
    one that looks up no executable); `signin` the detect result when the engineer asked for the check; `relative_to` the
    directory the commands run from."""
    manifest = manifest if manifest is not None else integration_manifest.load()
    if doctor is None:
        from . import cli
        doctor = cli.doctor(executables=False)
    model = readiness_model.readiness(survey, doctor.get('host_capabilities'), doctor, signin=signin)
    from .entry import json_paths
    directory = survey.get('directory') if isinstance(survey, dict) else None
    # the JSON form writes the directory as it always has: in full, quoted for the shell (the JSON writer, with no relative_to)
    flag = _signin_flag(json_paths(Path(directory), None)[1](directory) if directory else None, goal)
    goals = [goal] if goal else list(readiness_model.OPERATIONS)
    integration = manifest['integration']
    record = {'id': integration['id'], 'label': integration['label'], 'product': integration['product'],
              'product_version': integration['product_version'],
              'goals': [_goal(manifest, model, model.get('signin'), name, flag) for name in goals],
              'object_kinds': [_kind(manifest, kind) for kind in manifest['object_kinds']],
              'families': [_family(entry) for entry in manifest['families']],
              'live_blockers': list(manifest['live_blockers'])}
    result = Catalog({'schema_version': VERSION, 'directory': survey.get('directory') if isinstance(survey, dict) else None,
                      'integrations': [record], 'other_integrations': NO_OTHERS, 'signin_checked': bool(model.get('signin')),
                      'projects': projects(survey, relative_to) if isinstance(survey, dict) else [],
                      'execution_authorized': False, 'cloud_authority': False})
    result.text_build, result.text_placeholders = _text_build(result, survey, goal, relative_to)
    return result


class Catalog(dict):
    """The catalog the JSON form prints, and beside it (as attributes, which no JSON form carries) text_build: the same catalog
    with the strings that carry paths written for a screen from their operands, and text_placeholders: which placeholders that
    wrote. catalog_lines prints from text_build; the JSON form keeps the recorded strings."""
    text_build = None
    text_placeholders = frozenset()

    def __reduce_ex__(self, protocol):
        # Persistence (pickle, shelve, copy) keeps the catalog the JSON form prints and nothing else; see entry.Survey.
        return dict, (dict(self),)


def _text_build(result, survey, goal, relative_to):
    """(the catalog as a screen prints it, the placeholders written). Every state and verdict is the JSON build's; only the
    strings that carry paths differ: each resume command (projects[].command) and the sign-in command of an unchecked
    authenticated state (authenticated.message), both written from their path operands with the relative_to the builder was
    given, never patched into rendered text."""
    from . import entry
    data = copy.deepcopy(dict(result))
    if not isinstance(survey, dict):
        return data, frozenset()
    root = Path(survey['directory']) if survey.get('directory') else None
    show, q, placeholders, directory = entry.text_paths(root, relative_to)
    for row, item in zip(data['projects'], survey.get('items') or []):
        # Each resume command is written by a path writer of its own: when it had to write DIRECTORY (or DIRECTORY/store), which a
        # shell takes for a real folder, because the surveyed directory may not be shown, the command is not printed. (A surveyed
        # file whose own name is refused is still PATH in its command, as before; the sentence under the header says what it is.)
        _, own, stood_in, _ = entry.text_paths(root, relative_to)
        command, note = _resume(item, survey['items'], own)
        row['command'], row['note'] = (None, COMMAND_NOT_SHOWN) if entry.DIRECTORY_PLACEHOLDER in stood_in else (command, note)
        row['path'] = entry.screen_path(row['path'], placeholders)
    # the directory as a screen says it, and as the path writer writes it in a command (the refused name is not kept here)
    data.update(entry.screen_directory(survey.get('directory'), directory()))
    hidden = data['directory_hidden']
    for item in data['integrations'][0]['goals']:
        if item['authenticated']['state'] == 'not_checked':
            item['authenticated']['message'] = _signin_message(data['directory_operand'], goal, hidden)
    _shown_goal_steps(data['integrations'][0]['goals'], data['directory_operand'], hidden)
    return data, frozenset(placeholders)


def _shown_goal_steps(goals, operand, hidden=False):
    """The steps and the note each goal recorded, as a screen prints them: as recorded when no word in them is refused, otherwise
    the fixed explanation without a command (entry.shown_step). The recorded no-sign-in-check note is written by screen_note,
    with the directory operand the screen's path writer wrote. Where the directory is refused (hidden), a recorded step that
    says `start DIRECTORY` is said in words instead (readiness.without_stand_in): DIRECTORY would be a real folder to a shell."""
    from . import entry
    for item in goals:
        for holder in (item, item['blocked']):
            if holder.get('next_action'):
                holder['next_action'] = entry.shown_step(holder['next_action'])
                if hidden:
                    holder['next_action'] = readiness_model.without_stand_in(holder['next_action'])
        missing = item['blocked'].get('missing')
        if missing:
            written = readiness_model.screen_note(missing, operand, hidden=hidden)
            item['blocked']['missing'] = written if written != missing else entry.shown_step(missing)
            if hidden:
                item['blocked']['missing'] = readiness_model.without_stand_in(item['blocked']['missing'])


def _plain_text_build(value):
    """The screen's catalog for plain data that this module did not build (for example a result that crossed a JSON boundary):
    its recorded strings, except that a directory the screen may not show is not written in any of them. The operands are not at
    hand here, so a resume command is shown as recorded only when the directory is shown and no word in it is refused; the sign-in
    command is written again from the directory."""
    from . import entry
    data = copy.deepcopy(dict(value))
    data.update(entry.plain_screen_directory(data.get('directory')))
    hidden = data['directory_hidden']
    placeholders = set()
    for row in data.get('projects') or []:
        row['path'] = entry.screen_path(row['path'], placeholders)
        if row['command'] and entry.recorded_step_for_screen(row['command'], hidden) is None:
            row['command'] = None
            row['note'] = COMMAND_NOT_SHOWN
    goals = data['integrations'][0]['goals']
    # every unchecked sign-in message is written again from the directory, shown or not: a recorded one may name anything
    for item in goals:
        if item['authenticated']['state'] == 'not_checked':
            item['authenticated']['message'] = _signin_message(data['directory_operand'],
                                                               goals[0]['goal'] if len(goals) == 1 else None, hidden)
    _shown_goal_steps(goals, data['directory_operand'], hidden)
    return data, frozenset(placeholders)


# -- text ----------------------------------------------------------------------------------------------------------
LABEL = 17
LEVEL_PREFIX = 'qualification '


def _ready_words(goal):
    """The words of the operation-ready row; the verdict that closes the screen says them again from here."""
    ready = goal['operation_ready']
    return '%s (readiness status: %s)' % (ready['state'], ready['status'])


def _blocked_words(goal):
    """The first words of the blocked row: whether a prerequisite blocks the goal and which one first."""
    blocked = goal['blocked']
    if blocked['state'] == 'blocked':
        return 'yes, by %s (%s)' % (blocked['row'], blocked['row_state'])
    return 'no prerequisite is reported as not ready'


def _modeled_only_words(goal):
    """For a goal whose operations are all recorded as a synthetic local process only: that they run against the modeled
    service, and (when the manifest records the cloud executor as unavailable) that no cloud route exists. Said in the
    available row itself, because `execute` listed beside `available: yes` reads as a route to the cloud."""
    if goal['available']['evidence_classes'] != [MODELED_ONLY]:
        return ''
    words = ', against the modeled service only'
    if NO_CLOUD_ROUTE in goal['unsupported']['live_blockers']:
        words += '; no cloud route exists'
    return words


def verdict_words(goal):
    """One goal's verdict in the words of its state rows (operation-ready and blocked), for the last screen."""
    return 'operation-ready: %s; blocked: %s' % (_ready_words(goal), _blocked_words(goal))


def _state_lines(goal, width):
    from .entry import _flow
    rest = ' ' * (4 + LABEL)

    def row(name, text):
        if width < 90:
            # A narrow window: the state word on its own row, the text indented under it, so a command still fits.
            return ['    %s:' % name] + _flow(text, width, '      ', '      ', commands=True)
        return _flow(text, width, '    ' + ('%s:' % name).ljust(LABEL), rest, commands=True)

    available, configured = goal['available'], goal['configured']
    auth, ready, blocked, unsupported = goal['authenticated'], goal['operation_ready'], goal['blocked'], goal['unsupported']
    if available['state'] == 'available':
        text = 'yes%s (operations: %s; evidence: %s)' % (_modeled_only_words(goal), ', '.join(available['operations']),
                                                         ', '.join(c.replace('_', ' ') for c in available['evidence_classes']))
    else:
        text = 'no (the manifest lists no %s operation)' % ', '.join(available['missing_operations'])
    lines = row('available', text)
    text = configured['state'] + (' (not ready: %s)' % ', '.join(configured['not_ready']) if configured['not_ready'] else
                                  ' (checked: %s)' % ', '.join(configured['inputs_checked']))
    lines += row('configured', text)
    if auth['state'] == 'not_checked':
        text = 'not checked; ' + auth['message'].replace('Sign-in is not checked. ', '', 1)
    else:
        text = '%s (Azure CLI sign-in: %s)' % (auth['state'].replace('_', ' '), auth.get('message') or auth.get('status'))
        text += ' ' + auth['permission']
    lines += row('authenticated', text)
    lines += row('operation-ready', _ready_words(goal))
    if blocked['state'] == 'blocked':
        # the note is already as the screen says it (the text build wrote it); a refused directory is said not to be shown once,
        # under the screen's header, not again in each note
        text = '%s. %s Next action: %s' % (_blocked_words(goal), blocked['missing'] or '', blocked['next_action'])
        contact = readiness_model.capture_contact(blocked['next_action'])
        if contact:
            # The step ends in the closing bracket of its legend (no full stop): end that sentence before the next begins.
            text += ('' if text.endswith('.') else '.') + ' ' + contact
    else:
        text = _blocked_words(goal)
    lines += row('blocked', text)
    if unsupported['state'] == 'unsupported':
        text = 'yes: ' + ' '.join(unsupported['reasons'])
    else:
        text = 'nothing recorded as unsupported in this build.'
    lines += row('unsupported', text)
    # The live state and what a live run is blocked by are recorded for the product, not for this goal: their own row, so
    # that blocked stays about this goal here and unsupported about what the manifest does not list.
    lines += row('live', 'not run; recorded blockers for a live run: %s.' % ', '.join(
        b.replace('_', ' ') for b in unsupported['live_blockers']))
    return lines


def catalog_lines(value, width):
    """The catalog as plain lines: ASCII words for every state, wrapped to the width. The screen prints from the catalog's text
    build, whose commands are written from their path operands (a refused directory is DIRECTORY plus the remainder, an operand
    that cannot be shown is PATH); every row passes the control-character guard (entry.guard_rows)."""
    from .entry import PATH_NOT_SHOWN_SENTENCE, PATH_PLACEHOLDER, _flow, guard_rows
    from .workbench_screens import word_wrap
    built = getattr(value, 'text_build', None)
    if built is not None:
        value, placeholders = built, value.text_placeholders
    else:  # plain data (for example a result that crossed a JSON boundary)
        value, placeholders = _plain_text_build(value)
    lines = ['INTEGRATION CATALOG']
    # The directory is user input: the text build holds it as a screen says it (a name the output-path rule of signin collect
    # refuses is DIRECTORY), and the screen says once, under its header, that the name is not shown.
    hidden = value.get('directory_hidden', False)
    lines += word_wrap('%s | offline | this lists only what this build holds' % (value.get('directory') or 'no directory'), width)
    if hidden:
        lines += word_wrap(readiness_model.DIRECTORY_NOT_SHOWN_SENTENCE, width)
    if PATH_PLACEHOLDER in placeholders:
        lines += word_wrap(PATH_NOT_SHOWN_SENTENCE, width)
    lines += word_wrap(value['other_integrations'], width)
    for record in value['integrations']:
        lines.append('')
        lines += word_wrap('%s (id %s, build %s)' % (record['label'], record['id'], record['product_version']), width)
        lines.append('GOALS')
        for goal in record['goals']:
            lines.append('  GOAL ' + goal['goal'])
            lines += _state_lines(goal, width)
        lines += _flow('An object kind or goal not listed here is unsupported; a level word appears only where a record '
                       'establishes it.', width, '', '')
        lines.append('OBJECT KINDS')
        for kind in record['object_kinds']:
            level = kind['level'] if kind['level_record'] is None else '%s (record: %s)' % (kind['level'], kind['level_record'])
            classes = ', '.join(c.replace('_', ' ') for c in kind['evidence_classes']) or 'no operation listed'
            lines += _flow('%s (family %s): %s%s | evidence: %s | scope: %s' % (
                kind['label'], kind['family'], LEVEL_PREFIX, level, classes, kind['scope']), width, '  ', '    ')
        lines.append('FAMILIES')
        for family in record['families']:
            lines += _flow('%s: release stage %s; live: %s' % (family['family'], family['release_stage'], family['live']),
                           width, '  ', '    ')
    lines.append('')
    lines.append('SAVED PROJECTS')
    if value['projects']:
        if any(project['command'] for project in value['projects']):
            # The paths in a resume command are written for the directory the catalog was run in (build's relative_to), and
            # that directory is not in the data: say once, above the commands, where they are typed.
            lines += _flow(RESUME_BASE, width, '  ', '  ')
        for project in value['projects']:
            lines += _flow('%s %s: %s | %s' % (project['label'], project['path'], project['summary'], screen_words(project['state'])),
                           width, '  ', '    ')
            if project['command']:
                lines += _flow('Resume: ' + project['command'], width, '    ', '    ', commands=True)
            else:
                lines += _flow('Resume: no command (%s)' % project['note'], width, '    ', '    ')
        # What the state words mean, once, under the projects they describe.
        lines += _flow(STATE_LEGEND, width, '  ', '  ')
    else:
        lines += word_wrap('Nothing recognized here yet.', width)
    lines.append('NEXT ACTION')
    for record in value['integrations']:
        for goal in record['goals']:
            lines.append('  %s:' % goal['goal'])
            # A 40-row pane shows only the last rows: the verdict that justifies the next action stands beside it, in the
            # words of the goal's state rows (one source), so the pane never shows an action without its reason.
            lines += _flow('Verdict: ' + verdict_words(goal), width, '    ', '      ')
            lines += _flow(goal['next_action'], width, '    ', '    ', commands=True)
            contact = readiness_model.capture_contact(goal['next_action'])
            if contact:
                lines += _flow(contact, width, '    ', '    ')
    return guard_rows(lines)
