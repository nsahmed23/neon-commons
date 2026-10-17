"""Guided entry: what already exists in a working directory, and what to do next.

Read-only and offline. Before asking anything, it inspects what the engineer
already has: wizard, journey and guided sessions; workbench stores; Atmos
repositories; supported exports and contexts; generated projects; modeled
services; and maintenance operations. Each item is reported with distinct
states (discovered, configured, authenticated, qualified) and the next concrete
command. A missing live connection never hides what offline inspection and
preparation can still do, and synthetic evidence stays labelled synthetic.

The walk is bounded (depth, entries, file size), skips version-control,
environment and evidence directories, never follows symbolic links, and reads
through the product's own loaders. Opening a store uses the store's normal
open, which may roll back an interrupted SQLite journal (engine crash recovery);
nothing else is written.
"""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

VERSION = 'workbench-start/1'
MAX_DEPTH = 4
MAX_ENTRIES = 5000
MAX_JSON_BYTES = 16 * 1024 * 1024
SKIP_DIRS = {'.git', '.venv', 'venv', '.tox', '.mypy_cache', '.pytest_cache', '.terraform', 'node_modules',
             '__pycache__', 'attempts'}
CONTEXT_KEYS = {'tenant_id', 'cloud', 'stack', 'component'}
PROGRAM = 'intune-iac'
OFFLINE = 'no_live_connection'
ORDER = ('store', 'repository', 'wizard_session', 'journey_session', 'guided_session', 'generated_project', 'operation',
         'modeled_service', 'export', 'context', 'session_backup')


def _walk(root):
    """JSON files and directories under root, bounded, never following links."""
    files, dirs, links, pending, seen = [], [], [], [(root, 0)], 0
    while pending:
        directory, depth = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in entries:
            seen += 1
            if seen > MAX_ENTRIES:
                return files, dirs, links, True
            path = Path(entry.path)
            if entry.is_symlink():
                links.append(path.relative_to(root).as_posix())
            elif entry.is_dir(follow_symlinks=False):
                if entry.name in SKIP_DIRS or entry.name.endswith(('.journey', '.evidence')):
                    continue
                dirs.append(path)
                if depth + 1 < MAX_DEPTH:
                    pending.append((path, depth + 1))
            elif entry.is_file(follow_symlinks=False) and entry.name.endswith('.json'):
                files.append(path)
    return sorted(files), sorted(dirs), sorted(links), False


def _states(configured, authenticated=OFFLINE, qualified='not_qualified', reason=None):
    value = {'discovered': True, 'configured': configured, 'authenticated': authenticated, 'qualified': qualified}
    return dict(value, configured_reason=reason) if reason else value


def _git_revision(directory):
    """The checked-out commit read from .git files; None when it is not a Git repository or cannot be read."""
    import re
    git = directory / '.git'
    try:
        head = (git / 'HEAD').read_text(encoding='ascii').strip()
        if head.startswith('ref: '):
            ref = head[5:]
            if not re.fullmatch(r'refs/[A-Za-z0-9._/-]{1,200}', ref) or '..' in ref:
                return None
            path = git / ref
            if path.is_file():
                head = path.read_text(encoding='ascii').strip()
            else:
                packed = (git / 'packed-refs').read_text(encoding='ascii').splitlines()
                head = next((line.split()[0] for line in packed if line.endswith(' ' + ref)), '')
        return head if re.fullmatch(r'[0-9a-f]{40}', head) else None
    except (OSError, UnicodeError):
        return None


def _json_item(root, path, rel):
    from .io import load_json
    from reference.validation import schema_errors
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            return None
        value = load_json(path)
    except Exception:
        return None
    if not isinstance(value, dict):
        return None
    import re
    kept = re.fullmatch(r'(.+)\.restart-(\d+)\.json', path.name)
    if kept and {'step', 'paths'} <= set(value):
        # Kept by the wizard's restart; an earlier state to read, not a session to resume.
        return {'kind': 'session_backup', 'path': rel, 'session': Path(rel).with_name(kept.group(1)).as_posix(),
                'number': int(kept.group(2)), 'step': value.get('step'), 'states': _states(True)}
    if value.get('schema_version') == '1.0.0' and {'step', 'paths', 'fingerprints', 'generated', 'conflict_reason'} <= set(value):
        from .wizard import _session
        try:
            state = _session(path)
        except Exception:
            return {'kind': 'wizard_session', 'path': rel, 'valid': False, 'states': _states(False, reason='session_invalid')}
        paths = {name: _relative(root, state['paths'].get(name)) for name in ('input', 'context', 'output')}
        return {'kind': 'wizard_session', 'path': rel, 'valid': True, 'step': state['step'],
                'conflict_reason': state.get('conflict_reason'), 'generated': state.get('generated') is not None,
                'repository_mode': 'repository' in state, **paths,
                'states': _states(all(state['paths'].get(name) for name in ('input', 'context', 'output')))}
    if {'lifecycle', 'mode', 'selected_ids', 'in_flight'} <= set(value):
        from . import journey
        try:
            state = journey._load(path)
            progress = journey.reconstruct_progress(path)
        except Exception:
            return {'kind': 'journey_session', 'path': rel, 'valid': False, 'states': _states(False, reason='session_invalid')}
        return {'kind': 'journey_session', 'path': rel, 'valid': True, 'lifecycle': state['lifecycle'], 'mode': state['mode'],
                'next_state': progress['next_state'], 'verified': len(progress['verified_completed']),
                'output': _relative(root, state['paths']['output']), 'states': _states(True, qualified='synthetic_only' if state['mode'] == 'simulation' else 'not_qualified')}
    from .workflow import SESSION_KEYS
    if set(value) == SESSION_KEYS:
        from . import workflow
        try:
            state = workflow._load(path)
        except Exception:
            return {'kind': 'guided_session', 'path': rel, 'valid': False, 'states': _states(False, reason='session_invalid')}
        return {'kind': 'guided_session', 'path': rel, 'valid': True, 'saved_state': state['saved_state'],
                'lifecycle': state['lifecycle'], 'output': _relative(root, state['paths'].get('output')), 'states': _states(True)}
    try:
        is_export = not schema_errors('export-intake', value)
    except Exception:
        is_export = False
    if is_export:
        from .wizard import _policy_ids
        try:
            policies = sorted(_policy_ids(path))
        except Exception:
            policies = []
        synthetic = value.get('synthetic') is True
        return {'kind': 'export', 'path': rel, 'synthetic': synthetic, 'tenant_id': value.get('tenant_id'), 'policies': policies,
                'states': _states(True, 'source_asserted_not_authenticated', 'synthetic_only' if synthetic else 'not_qualified')}
    if CONTEXT_KEYS <= set(value) and 'collections' not in value:
        return {'kind': 'context', 'path': rel, 'tenant_id': value.get('tenant_id'), 'stack': value.get('stack'),
                'component': value.get('component'), 'synthetic': value.get('source_is_synthetic') is True, 'states': _states(True)}
    return None


def _relative(root, value):
    if not value:
        return None
    path = Path(value)
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _store_item(root, directory, rel):
    from .workbench_store import WorkbenchStore
    try:
        store = WorkbenchStore(directory)
        overview = store.overview(limit=1)
        intents = store.artifacts(kind='repository_intent')
        operations = store.operations()
    except Exception as error:
        return {'kind': 'store', 'path': rel, 'states': _states(False, reason=getattr(error, 'code', 'store_unreadable'))}
    total = (overview.get('pagination') or {}).get('total_objects', 0)
    return {'kind': 'store', 'path': rel, 'tenant_id': store.tenant_id, 'objects': total,
            'freshness': overview.get('freshness'), 'coverage': overview.get('coverage'),
            'intents': [{'object_id': row['data'].get('target_object_id'), 'repository': row['data'].get('scope', {}).get('repository'),
                         'artifact_id': row['artifact_id']} for row in intents],
            # Operations, not their journal records (item 17).
            'operations': len({row.get('operation_id') for row in operations}),
            'states': _states(total > 0, qualified='synthetic_only' if overview.get('evidence_class') in (None, 'synthetic') else 'not_qualified',
                              reason=None if total else 'no_observations')}


def _service_item(directory, rel):
    from .io import load_json
    try:
        value = load_json(directory / 'service.json')
        current = value['current']
        return {'kind': 'modeled_service', 'path': rel, 'tenant_id': current.get('tenant_id'), 'objects': sorted(current.get('objects', {})),
                'revision': value.get('revision'), 'states': _states(True, 'modeled_service_no_authentication', 'synthetic_only')}
    except Exception:
        return {'kind': 'modeled_service', 'path': rel, 'states': _states(False, reason='service_unreadable')}


def _repository_item(directory, rel):
    from .repository import discover_repository
    try:
        report = discover_repository(directory)
    except Exception:
        return {'kind': 'repository', 'path': rel, 'states': _states(False, reason='repository_unreadable')}
    stacks = [item.get('stack') for item in report.get('stacks', [])]
    components = sorted({(item.get('stack'), component.get('name')) for item in report.get('stacks', [])
                         for component in item.get('components', []) if component.get('selectable')})
    revision = _git_revision(directory)
    reason = None if report.get('status') == 'discovered' and components else 'no_selectable_component'
    if revision is None:
        reason = reason or 'not_a_git_repository'
    return {'kind': 'repository', 'path': rel, 'status': report.get('status'), 'stacks': stacks,
            'components': [{'stack': stack, 'component': name} for stack, name in components], 'git_revision': revision,
            'blockers': [blocker.get('code') for blocker in report.get('blockers', [])],
            'states': _states(reason is None, reason=reason)}


def _operation_item(directory, rel):
    from . import maintenance
    try:
        _, plan, journal, _, _ = maintenance._load(directory)
    except Exception as error:
        return {'kind': 'operation', 'path': rel, 'states': _states(False, reason=getattr(error, 'code', 'operation_unreadable'))}
    return {'kind': 'operation', 'path': rel, 'object_id': plan['object_id'], 'status': journal['status'],
            'changes': plan['changes'], 'states': _states(True, qualified='synthetic_only')}


def _staged_classification(root, session, directory):
    """Classify one policy's output written by a journey or guided session (output/<policy id>)."""
    policy_id = directory.name
    if session['kind'] == 'journey_session':
        from . import journey
        path = root / session['path']
        state = journey._load(path)
        if policy_id not in state['selected_ids']:
            return None
        return journey._classify_selected(state, journey._observe(path, state), policy_id)
    from . import workflow
    path = root / session['path']
    state = workflow._load(path)
    if policy_id not in state['selected_ids']:
        return None
    return workflow._classify_one(state, workflow._observe(path, state)['context'], policy_id)


def _generated_item(root, directory, rel, sessions):
    """A generated project, classified against the session that produced it when one is found."""
    from .output_edit import classify
    parent = Path(rel).parent.as_posix()
    for session in sessions:
        if session.get('kind') in ('journey_session', 'guided_session') and session.get('valid') and session.get('output') == parent:
            try:
                edit = _staged_classification(root, session, directory)
            except Exception:
                edit = None
            if edit is not None:
                return _classified(rel, session['path'], edit)
    for session in sessions:
        if session.get('kind') == 'wizard_session' and session.get('valid') and session.get('output') == rel:
            try:
                edit = classify(root / session['input'] if not Path(session['input']).is_absolute() else session['input'],
                                root / session['context'] if not Path(session['context']).is_absolute() else session['context'],
                                directory)
            except Exception:
                return {'kind': 'generated_project', 'path': rel, 'session': session['path'], 'classification': 'source_unavailable',
                        'states': _states(False, reason='source_unavailable')}
            return _classified(rel, session['path'], edit)
    return {'kind': 'generated_project', 'path': rel, 'session': None, 'classification': 'source_unknown',
            'states': _states(False, reason='source_unknown')}


def _classified(rel, session_path, edit):
    item = {'kind': 'generated_project', 'path': rel, 'session': session_path, 'classification': edit['classification'],
            'states': _states(edit['classification'] == 'unchanged', qualified='synthetic_only',
                              reason=None if edit['classification'] == 'unchanged' else 'verification_stale')}
    if edit['classification'] == 'repository_owned_policy_edit':
        item.update(pointer=edit['pointer'], field_changes=len((edit['field_changes'] or {}).get('changes', [])))
    elif edit['classification'] == 'other_change':
        item.update(reason=edit.get('reason'))
    return item


def _name(root, rel):
    """The directory name a surveyed path ends in; the surveyed directory itself (a dot) has its own name."""
    return (Path(root) / rel).name if root is not None else Path(rel).name


def _shower(root, relative_to):
    """Paths for the next steps: a path that works from relative_to (relative to it when inside it, absolute otherwise).

    Without relative_to a path stays relative to the surveyed directory, as the survey records it.
    """
    def show(rel):
        if relative_to is None or root is None:
            return rel
        target, base = Path(os.path.normpath(Path(root) / rel)), Path(os.path.normpath(relative_to))
        try:
            return target.relative_to(base).as_posix()
        except ValueError:
            return target.as_posix()
    return show


DIRECTORY_PLACEHOLDER = 'DIRECTORY'
PATH_PLACEHOLDER = 'PATH'
PATH_NOT_SHOWN_SENTENCE = PATH_PLACEHOLDER + ' is a path in this directory whose name is not shown here.'

# The fill-in templates: a word that stands where the person must put a real value (a folder, a file, a tenant id). The start screen
# never prints one as the operand of a command, because a shell takes it for a real name (STORE or SERVICE_ROOT is a valid relative
# path) or the command fails; it says the step in words instead. One set, used by the product (has_fill_in) and by the tests: the
# placeholders this module writes for a path it may not show (DIRECTORY, PATH), the generic names ROOT and ID, and every fixed
# placeholder of the next steps below. A test walks this module's command strings and fails when one holds a name that is not here.
FILL_IN_TEMPLATES = frozenset((DIRECTORY_PLACEHOLDER, PATH_PLACEHOLDER, 'ROOT', 'ID', 'SERVICE_ROOT', 'TENANT_ID', 'STORE',
                               'CONTEXT_JSON', 'EXPORT_JSON', 'REPOSITORY', 'NEW_OUTPUT_DIR', 'NEW_SESSION'))
_FILL_IN = re.compile(r'(?:%s)(?:[/.].*)?\Z' % '|'.join(sorted(FILL_IN_TEMPLATES, key=len, reverse=True)), re.DOTALL)


def is_fill_in(token):
    """True when the operand is a fill-in template or starts one (DIRECTORY/store, NEW_SESSION.json)."""
    return bool(_FILL_IN.match(token))


def has_fill_in(step):
    """True when a command in the step has a fill-in template as an operand. A command runs from the program name to the end of its
    sentence (a full stop, semicolon or colon before a space, or an opening parenthesis)."""
    for command in step.split(PROGRAM + ' ')[1:]:
        command = re.split(r'\s\(|[.;:](?:\s|\Z)', command)[0]
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        if any(is_fill_in(token) for token in tokens):
            return True
    return False


def json_paths(root, relative_to):
    """(show, q): how the JSON forms write the path operands of a command. show is a path as a sentence says it; q is the same
    as a command argument (a path with a space is quoted for the shell, as the rest of the product quotes one)."""
    show = _shower(root, relative_to)
    return show, (lambda rel: shlex.quote(show(rel)))


def text_paths(root, relative_to):
    """(show, q, placeholders, directory): how a screen writes the same path operands, built from the operand and never patched
    into rendered text. For an operand at or under a surveyed directory that display_refused refuses, the directory is not
    written: the operand is DIRECTORY plus the remainder inside it, and quoting (q) applies to that. An operand that
    display_refused refuses (a credential shape, a character that terminal escaping would change) is the placeholder PATH.
    Any other operand is written as the JSON forms write it, with the same relative_to. placeholders collects the
    placeholders written, so the screen can say once what they stand for. directory() is the surveyed directory itself as a
    command argument, written by the same writer: DIRECTORY when it is refused, relative to relative_to when there is one, in
    full when there is not (None when there is no directory)."""
    from .readiness import display_refused
    show = _shower(root, relative_to)
    hidden = root is not None and display_refused(str(root))
    placeholders = set()

    def text(rel):
        if hidden:
            tail = '' if rel in ('.', '') else rel
            if tail and display_refused(tail):
                placeholders.add(PATH_PLACEHOLDER)
                return PATH_PLACEHOLDER
            placeholders.add(DIRECTORY_PLACEHOLDER)
            return DIRECTORY_PLACEHOLDER + ('/' + tail if tail else '')
        shown = show(rel)
        if display_refused(shown):
            placeholders.add(PATH_PLACEHOLDER)
            return PATH_PLACEHOLDER
        return shown

    def q(rel):
        return shlex.quote(text(rel))

    def directory():
        if root is None:
            return None
        return q('.' if relative_to is not None or hidden else str(root))
    return text, q, placeholders, directory


def screen_directory(directory, operand):
    """The directory fields of a text build: directory (as a sentence says it: DIRECTORY when display_refused refuses it),
    directory_hidden, and directory_operand (the directory as a command argument, written by the path writer). A screen reads
    these; the refused name itself is not kept in a text build."""
    from .readiness import display_refused
    hidden = bool(directory) and display_refused(directory)
    return {'directory': DIRECTORY_PLACEHOLDER if hidden else directory, 'directory_hidden': hidden,
            'directory_operand': operand}


def plain_screen_directory(directory):
    """screen_directory for plain data: no relative_to is known, so the operand is the directory in full (the JSON forms' own
    writer, json_paths, quotes it), or DIRECTORY when it is refused."""
    from .readiness import display_refused
    if not directory:
        return screen_directory(directory, None)
    hidden = display_refused(directory)
    operand = DIRECTORY_PLACEHOLDER if hidden else json_paths(Path(directory), None)[1](directory)
    return screen_directory(directory, operand)


def screen_path(rel, placeholders):
    """A surveyed path as a screen's sentence says it (a row of FOUND or SAVED PROJECTS, a skipped link): as recorded, or the
    placeholder PATH when display_refused refuses it, so that a name a command shows as PATH is not shown in a sentence either."""
    from .readiness import display_refused
    if display_refused(rel):
        placeholders.add(PATH_PLACEHOLDER)
        return PATH_PLACEHOLDER
    return rel


def screen_survey(value, next_actions, placeholders):
    """The survey as a screen prints it: the given next steps, and every surveyed path in its rows written by screen_path."""
    return dict(value, next_actions=next_actions,
                items=[dict(item, path=screen_path(item['path'], placeholders)) for item in value['items']],
                skipped_links=[screen_path(link, placeholders) for link in value.get('skipped_links') or []])


def _in_words(lead, kind, step):
    """A next step that would have to write a stand-in (DIRECTORY, PATH) for a path it may not show, said in words: what it does,
    which command it is and what that is run on, and never an operand, because a stand-in is a valid relative path to a shell and
    a copied command would run on another folder. The wording is the catalog's own for a resume command that it may not print
    (catalog._resume_words): 'Resume with the workbench workspace command using this saved store; its path cannot be shown here.'"""
    from .catalog import RESUME_NOUNS
    words = step[step.index(PROGRAM + ' '):].split()[1:]
    head = words[:next((index for index, word in enumerate(words) if word.startswith('-')), len(words))]
    flags = [word for word in words if word in ('--journey', '--guided')]
    return '%s the %s command using this %s; its path cannot be shown here.' % (
        lead, ' '.join(head + flags), RESUME_NOUNS.get(kind, 'saved item'))


def _next_actions(items, root=None, relative_to=None, paths=None, fresh=None):
    """The next steps for what the survey found; paths is (show, q) from json_paths (the default) or text_paths.

    fresh, for a screen, is a function that returns the writer of text_paths for this survey. Each next step is then written by a
    writer of its own, and a step that had to write a stand-in for any operand (DIRECTORY for a directory the screen may not show,
    PATH for a path it may not show) is not printed as a command: it is said in words (_in_words). The JSON form has no fresh and
    keeps the recorded commands."""
    show, q = paths if paths is not None else json_paths(root, relative_to)
    kinds = {}
    for item in items:
        kinds.setdefault(item['kind'], []).append(item)
    actions = []

    def step(lead, kind, build):
        """One next step, built from the writer (show, q) it is given; said in words when its own writer wrote a stand-in."""
        if fresh is None:
            actions.append(build(show, q))
            return
        own_show, own_q, stood_in, _ = fresh()
        text = build(own_show, own_q)
        actions.append(_in_words(lead, kind, text) if stood_in else text)

    conflicts = {'repository_owned_edit': 'Review the repository-owned edit, or hand it off to the repository workflow',
                 'output_changed': 'Resolve the changed output (new-path, review or cancel)',
                 'output_conflict': 'Resolve the output conflict (new-path, review or cancel)',
                 'outcome_unknown': 'Review the uncertain generation outcome before any retry'}
    for item in kinds.get('wizard_session', []):
        if item.get('valid') and item.get('step') != 'complete':
            said = conflicts.get(item.get('conflict_reason'), 'Resume the wizard session') if item.get('step') == 'conflict' else 'Resume the wizard session'
            step('Resume with', 'wizard_session',
                 lambda show, q, item=item, said=said: '%s: %s wizard --session %s' % (said, PROGRAM, q(item['path'])))
    for item in kinds.get('journey_session', []):
        if item.get('valid') and item.get('lifecycle') not in ('complete_simulation',):
            step('Resume with', 'journey_session',
                 lambda show, q, item=item: 'Resume the journey: %s wizard --journey --session %s' % (PROGRAM, q(item['path'])))
    for item in kinds.get('guided_session', []):
        if item.get('valid') and item.get('lifecycle') != 'complete_local':
            step('Resume with', 'guided_session',
                 lambda show, q, item=item: 'Resume the guided session: %s wizard --guided --session %s' % (PROGRAM, q(item['path'])))
    for item in kinds.get('generated_project', []):
        if item.get('classification') == 'repository_owned_policy_edit':
            actions.append('The generated project %s holds a repository-owned policy edit: reopen its session and use handoff, '
                           'or copy it into your repository and record it with repository-import.' % show(item['path']))
    stores = [item for item in kinds.get('store', []) if item['states']['configured'] or item.get('tenant_id')]
    services = kinds.get('modeled_service', [])
    for store in stores:
        service = next((s for s in services if s.get('tenant_id') == store.get('tenant_id')), None)
        if not store['states']['configured']:
            # An empty store shows nothing until something is collected into it.
            step('Collect into this store with', 'store',
                 lambda show, q, store=store, service=service: 'Collect into %s: %s workbench collect --root %s --service-root %s' % (
                     show(store['path']), PROGRAM, q(store['path']), q(service['path']) if service else 'SERVICE_ROOT'))
        step('Open the workspace with', 'store',
             lambda show, q, store=store, service=service: 'Open the workspace: %s workbench workspace --root %s%s' % (
                 PROGRAM, q(store['path']), ' --service-root ' + q(service['path']) if service else ''))
    if kinds.get('repository') and not stores:
        # repository-entry reads a store; there is none here to name.
        actions.append('Create a store first: %s workbench init --root STORE --tenant TENANT_ID' % PROGRAM)
    for repository in kinds.get('repository', []):
        recorded =[(store, intent) for store in stores for intent in store.get('intents', [])
                    if intent.get('repository') and Path(intent['repository']).name == _name(root, repository['path'])]
        if recorded:
            store, intent = recorded[-1]
            step('Check the repository against its recorded intent with', 'store',
                 lambda show, q, store=store, intent=intent:
                 'Check the repository against its recorded intent: %s workbench repository-status --root %s --object %s' % (
                     PROGRAM, q(store['path']), intent['object_id']))
            continue
        step('See the policies the repository holds with', 'repository',
             lambda show, q, repository=repository:
             'See the policies the repository %s holds and the exact command to record each: %s workbench '
             'repository-entry --root %s --repo %s (in the workspace: :repository-entry %s)' % (
                 show(repository['path']), PROGRAM, q(stores[0]['path']) if stores else 'STORE', q(repository['path']),
                 q(repository['path'])))
    used = {item.get('input') for item in kinds.get('wizard_session', [])}
    contexts = kinds.get('context', [])
    for export in kinds.get('export', []):
        if export['path'] not in used:
            step('Start from this export with', 'export',
                 lambda show, q, export=export:
                 'Start from the export %s: %s wizard --session NEW_SESSION.json --input %s --context %s --output NEW_OUTPUT_DIR' % (
                     show(export['path']), PROGRAM, q(export['path']), q(contexts[0]['path']) if contexts else 'CONTEXT_JSON'))
    for operation in kinds.get('operation', []):
        step('Follow the operation with', 'operation',
             lambda show, q, operation=operation: 'Follow the operation: %s workbench delivery --operation %s' % (
                 PROGRAM, q(operation['path'])))
    if not items:
        actions = ['Start from a supported export: %s wizard --session session.json --input EXPORT_JSON --context CONTEXT_JSON '
                   '--output NEW_OUTPUT_DIR' % PROGRAM,
                   'Or start from an Atmos repository you maintain, beginning with a store: %s workbench init --root STORE '
                   '--tenant TENANT_ID' % PROGRAM,
                   'Then list the policies it holds and the exact command to record each: %s workbench repository-entry '
                   '--root STORE --repo REPOSITORY' % PROGRAM]
    return actions


def _missing(items):
    kinds = {item['kind'] for item in items}
    notes = ['No live discovery connection is configured: offline inspection and preparation remain available.']
    if 'export' in kinds and 'context' not in kinds:
        notes.append('An export needs a bounded context JSON (tenant, cloud, stack and component) before the wizard can '
                     'generate; examples/context.json shows the shape.')
    if 'store' in kinds and 'modeled_service' not in kinds:
        notes.append('No modeled service or capture was found to collect from; the store keeps what it already observed.')
    return notes


def survey(directory, relative_to=None):
    """What already exists under a directory, with states and next actions; read-only.

    The paths in the next steps are relative to the surveyed directory unless relative_to (the directory the command runs
    in) is given; then they work from there.
    """
    root = Path(directory).absolute()
    files, dirs, links, truncated = _walk(root)
    items = []
    for path in files:
        item = _json_item(root, path, path.relative_to(root).as_posix())
        if item:
            items.append(item)
    sessions = list(items)
    # The surveyed directory itself is examined too (its own path is "."), so start on a repository, a store or an
    # operation sees it; _walk lists subdirectories only.
    for directory_path in [root, *dirs]:
        rel = directory_path.relative_to(root).as_posix()
        if (directory_path / 'observations.sqlite3').is_file():
            items.append(_store_item(root, directory_path, rel))
        if (directory_path / 'service.json').is_file():
            items.append(_service_item(directory_path, rel))
        if (directory_path / 'plan.json').is_file() and (directory_path / 'journal.json').is_file():
            items.append(_operation_item(directory_path, rel))
        # A generated project committed to Git is the engineer's repository, no longer generated output.
        git = (directory_path / '.git').exists()
        generated = (directory_path / 'generated-files.json').is_file() and not git
        if generated:
            items.append(_generated_item(root, directory_path, rel, sessions))
        if (directory_path / 'atmos.yaml').is_file() and not generated:
            items.append(_repository_item(directory_path, rel))
    items.sort(key=lambda item: (ORDER.index(item['kind']) if item['kind'] in ORDER else len(ORDER), item['path']))
    result = Survey({'schema_version': VERSION, 'directory': str(root), 'connection': 'offline', 'items': items,
                     'next_actions': _next_actions(items, root, relative_to), 'missing': _missing(items), 'skipped_links': links,
                     'truncated': truncated, 'execution_authorized': False, 'cloud_authority': False})
    # The same next steps, built from the same items and the same relative_to with the screen's path operands (text_paths).
    show, q, placeholders, directory = text_paths(root, relative_to)
    built = screen_survey(result, _next_actions(items, root, relative_to, (show, q), lambda: text_paths(root, relative_to)),
                          placeholders)
    built.update(screen_directory(str(root), directory()))
    result.text_build = built
    result.text_placeholders = frozenset(placeholders)
    return result


class Survey(dict):
    """The survey the JSON form prints, and beside it (as attributes, which no JSON form carries) text_build: the same survey
    with its next steps written for a screen, and text_placeholders: which placeholders that wrote. start_lines reads the
    screen's steps from text_build; the JSON form keeps the recorded steps."""
    text_build = None
    text_placeholders = frozenset()

    def __reduce_ex__(self, protocol):
        # Persistence (pickle, shelve, copy) keeps the survey the JSON form prints and nothing else: the text build holds what a
        # screen may print and is made again by survey(), never stored. What comes back is a plain dict, which a screen prints
        # through the plain-data path (recorded strings only where nothing in them is refused).
        return dict, (dict(self),)


LABELS = {'wizard_session': 'Wizard session', 'journey_session': 'Journey', 'guided_session': 'Guided session',
          'export': 'Export', 'context': 'Context', 'generated_project': 'Generated', 'store': 'Store',
          'repository': 'Repository', 'modeled_service': 'Service', 'operation': 'Operation',
          'session_backup': 'Kept session'}
# The product's own connection (none, offline) is told apart from the sign-in an Azure or GitHub CLI holds: the two are separate facts.
PRODUCT_CONNECTION_WORDS = 'this product has no live connection (not authenticated)'
SIGNIN_LABELS = {'azure': "Azure CLI sign-in (the Azure CLI's own, not a connection of this product)",
                 'github': "GitHub CLI sign-in (the GitHub CLI's own, not a connection of this product)"}
FOUND_LABELS = {'azure_sign_in': SIGNIN_LABELS['azure'], 'github_sign_in': SIGNIN_LABELS['github']}
STATE_WORDS = {OFFLINE: PRODUCT_CONNECTION_WORDS, 'source_asserted_not_authenticated': 'source-asserted, not authenticated',
               'modeled_service_no_authentication': 'modeled service, no authentication', 'synthetic_only': 'synthetic only',
               'not_qualified': 'not qualified'}


# STATE_WORDS are the words the JSON forms record (catalog --json carries them in each project's state), so they are frozen. Two of
# them read as a flat negative where the goal rows of the catalog say that authentication is not checked: a screen says them that
# way, through screen_words.
SCREEN_WORDS = {PRODUCT_CONNECTION_WORDS: 'this product has no live connection (authentication not checked)',
                STATE_WORDS['source_asserted_not_authenticated']: 'source-asserted, authentication not checked'}
STATE_LEGEND = ('Legend: discovered = found in this directory; usable here = the product can use it from here, offline; '
                'no live connection = this product holds none, so authentication is not checked; source-asserted = the file '
                'names the tenant and nothing checks it; synthetic only = modeled data, not a live tenant; not qualified = no '
                'record qualifies it for live use.')


def screen_words(words):
    """The ' | ' separated state words of one item as a screen says them (see SCREEN_WORDS)."""
    return ' | '.join(SCREEN_WORDS.get(part, part) for part in words.split(' | '))


def _count(number, noun, plural=None):
    return '%d %s' % (number, noun if number == 1 else plural or noun + 's')


def _v(value):
    """A value for a summary; a value the survey did not get is said in words, never printed as Python's None."""
    return 'not known' if value is None or value == '' else value


def _summary(item):
    kind = item['kind']
    if not item['states'].get('configured') and item['states'].get('configured_reason') in ('session_invalid', 'service_unreadable', 'repository_unreadable'):
        return 'unreadable: ' + item['states']['configured_reason'].replace('_', ' ')
    if kind == 'wizard_session':
        return 'step %s%s | output %s' % (_v(item.get('step')), ' (' + item['conflict_reason'] + ')' if item.get('conflict_reason') else '', _v(item.get('output')))
    if kind == 'journey_session':
        words = lambda value: str(_v(value)).replace('_', ' ')
        state = words(item.get('lifecycle')) + ('' if item.get('next_state') in (None, item.get('lifecycle'))
                                              else ' | next ' + words(item.get('next_state')))
        return '%s | %s of 17 stages verified as completed' % (state, _v(item.get('verified')))
    if kind == 'guided_session':
        return '%s | %s' % (_v(item.get('lifecycle')), _v(item.get('saved_state')))
    if kind == 'export':
        return '%s | tenant %s | %s' % ('synthetic' if item.get('synthetic') else 'not synthetic', _v(item.get('tenant_id')), _count(len(item.get('policies', [])), 'policy', 'policies'))
    if kind == 'context':
        return 'tenant %s | %s / %s' % (_v(item.get('tenant_id')), _v(item.get('stack')), _v(item.get('component')))
    if kind == 'generated_project':
        text = item.get('classification', 'unknown').replace('_', ' ')
        return text + (' at ' + item['pointer'] if item.get('pointer') else '') + (' | session ' + item['session'] if item.get('session') else '')
    if kind == 'store':
        return 'tenant %s | %s | %s | %s | %s' % (
            _v(item.get('tenant_id')), _count(item.get('objects') or 0, 'object'), _v(item.get('freshness')),
            _count(len(item.get('intents', [])), 'repository intent'), _count(item.get('operations', 0), 'operation'))
    if kind == 'repository':
        return 'Git %s | %s' % ((item.get('git_revision') or 'none')[:12], ', '.join('%s / %s' % (c['stack'], c['component']) for c in item.get('components', [])) or 'no selectable component')
    if kind == 'modeled_service':
        return 'tenant %s | %s | revision %s' % (_v(item.get('tenant_id')), _count(len(item.get('objects', [])), 'object'), _v(item.get('revision')))
    if kind == 'session_backup':
        return 'kept by restart %d of %s | step %s' % (item.get('number'), _v(item.get('session')), _v(item.get('step')))
    if kind == 'operation':
        changes = item.get('changes')
        if item.get('status') is None:
            # The operation record could not be read, so neither its status nor its changes are known.
            return 'status not known | changes not known'
        return '%s | %s' % (item['status'], ', '.join(changes or []) or ('changes not known' if changes is None else 'no configuration change'))
    return ''


GOAL_HINT = 'Add --goal inspect, discover, adopt or change to see what that goal needs.'
# Facts the readiness model could use but start does not gather, with the reason; shown on the screen and in the JSON.
OMITTED_FACTS = ('Executables on the search path (atmos, tofu, pwsh, codex, claude) are not looked up here, because a lookup '
                 'reads an environment value (the search path); the doctor command lists them.',)
# A word as the shell reads it: single-quoted runs, double-quoted runs (shlex.quote writes an apostrophe as '"'"'), a backslash and
# the character it escapes, and plain characters. A quote that never closes is a plain character, as it was.
_TOKEN = re.compile(r"""(?:'[^']*'|"(?:[^"\\]|\\.)*"|\\.|[^\s'])+""")
_COMMAND_STOP = frozenset({'and', 'then', 'or', 'from', 'to', 'with', 'for', 'as', 'that', 'is', 'the', 'in', 'on', 'by'})


def goal_readiness(value, goal, signin=None):
    """The readiness of one goal on the survey plus the host and doctor facts that need no process and no environment value.

    Left out of the doctor facts: the executables lookup (it reads the search path). Everything else it reports is read from
    package metadata, import specs and the platform, none of which starts a process.
    """
    from . import cli, readiness
    doctor = cli.doctor(executables=False)
    host = doctor['host_capabilities']
    model = readiness.readiness(value, host, doctor, signin=signin)
    operation = model['operations'][goal]
    profiles = host.get('profiles', {})
    facts = host.get('host', {})
    service = next((row for row in operation['rows'] if row['id'] == 'integration_service'), {})
    view = {'schema_version': model['schema_version'], 'goal': goal, 'status': operation['status'], 'directory': value['directory'],
            'host': {'os_name': facts.get('os_name'), 'sys_platform': facts.get('sys_platform'), 'machine': facts.get('machine'),
                     'python_version': facts.get('python_version'),
                     'supported_profiles': [name for name, entry in profiles.items() if entry.get('status') == 'IMPLEMENTED'],
                     'unsupported_profiles': [name for name, entry in profiles.items() if entry.get('status') != 'IMPLEMENTED']},
            'tenants': list(service.get('detected', {}).get('tenants', [])), 'rows': operation['rows'],
            'blocking': operation['blocking'], 'blockers': operation['blockers'], 'inputs': model['inputs'],
            'not_established': model['not_established'], 'omitted_facts': list(OMITTED_FACTS),
            'execution_authorized': False, 'cloud_authority': False}
    if 'signin' in model:
        # The judgement of each supplied sign-in (az, gh); present only when start was asked to look (--check-signin).
        view['signin'] = model['signin']
    return view


def _segments(text):
    """Text and commands of one sentence: ('text', str) or ('command', [arguments]). A command ends at a stop word, an opening
    parenthesis or a token that ends in sentence punctuation, which stays in the text after it."""
    pieces = text.split('intune-iac ')
    segments = [('text', pieces[0])] if pieces[0].strip() else []
    for chunk in pieces[1:]:
        tokens, end, tail = [], 0, ''
        # A quoted argument (a path with a space) is one token.
        for match in _TOKEN.finditer(chunk):
            word = match.group()
            if word.lower() in _COMMAND_STOP or word.startswith('('):
                break
            end = match.end()
            if set(word) == {'.'}:
                # A path such as . or .. is an argument, not sentence punctuation.
                tokens.append(word)
                continue
            tokens.append(word.rstrip('.,;:'))
            if word[-1:] in '.,;:)':
                tail = word[len(tokens[-1]):]
                break
        segments.append(('command', tokens))
        rest = chunk[end:].strip()
        if tail in (';', '.') and rest:
            # The sentence the command ended starts a new one.
            rest = rest[:1].upper() + rest[1:]
        if rest.strip():
            segments.append(('text', rest))
    return segments


def _command_rows(tokens, width, indent):
    """A command that fits stays whole; a wider one breaks between its arguments, every row but the last ending with a
    backslash, so copying the rows runs the one command."""
    head = ' ' * indent
    rows, row = [], head + 'intune-iac ' + tokens[0] if tokens else head + 'intune-iac'
    for token in tokens[1:]:
        if len(row) + 1 + len(token) + 2 <= width:
            row += ' ' + token
        else:
            rows.append(row + ' \\')
            row = head + '    ' + token
    return rows + [row]


def _step_words(text):
    """Every word of a step as the display rule must see it: each argument of a command as the shell reads it (so that its
    quoting hides nothing), and the words of the text around the commands (a name with an apostrophe in a sentence is not a
    quote). None when a command's quoted argument never closes."""
    words = []
    for kind, part in _segments(text):
        for token in part if kind == 'command' else _TOKEN.findall(part):
            try:
                words += shlex.split(token)
            except ValueError:
                if kind == 'command':
                    return None
                words.append(token)
        if kind == 'text':
            words += part.split()
    return words


def recorded_step_for_screen(text, hidden):
    """A recorded step that this module's builders did not write (plain data, for example a result that crossed a JSON
    boundary) as a screen may show it: as it is only when the directory is shown and every word of it passes display_refused
    (with and without the punctuation a sentence puts around a word); otherwise None, because the paths in it cannot be
    rewritten from their operands here."""
    from .readiness import display_refused
    words = None if hidden else _step_words(text)
    if words is None:
        return None
    if any(display_refused(word) or display_refused(word.strip('()[].,;:')) for word in words):
        return None
    return text


UNSHOWN_STEP = 'A next step names a path whose name is not shown here.'


def shown_step(text, hidden=False):
    """A recorded step or note as a screen prints it: as recorded, or the fixed explanation (UNSHOWN_STEP, which holds no command)
    when it names a path the screen may not show. Nothing to say (an empty value) stays as it is."""
    return (recorded_step_for_screen(text, hidden) or UNSHOWN_STEP) if text else text


def recorded_text(text, hidden):
    """A recorded step or note as a screen prints it: shown_step (as recorded, or the fixed explanation when it names a path the
    screen may not show) and, where the directory may not be shown (hidden), readiness.without_stand_in on top, the CATALOG-6 rule
    the catalog applies to the same strings: a part of it that could name the directory (DIRECTORY would be a real folder to a
    shell) is said in words. The rule is that function's; this module writes no second one."""
    from .readiness import without_stand_in
    step = shown_step(text)
    return without_stand_in(step) if hidden else step


def guard_rows(rows):
    """Every row that leaves a text form passes the product's own escape for control characters (workbench_tui.safe_text, which
    the workspace and word_wrap use): no C0 character other than the newline that ends a row, no DEL and no C1 character reaches
    the terminal from any recorded or user-supplied string; each is shown as a \\u escape instead."""
    from .workbench_tui import safe_text
    return [safe_text(row) for row in rows]


def _flow(text, width, first, rest, commands=False):
    """Wrap text at spaces to the width; with commands, each command in it goes on its own rows (see _command_rows)."""
    from .workbench_screens import word_wrap
    from .workbench_tui import safe_text
    text = safe_text(text)  # before the layout, so that the widths are those of what is printed (a command row too)
    lines, lead = [], first
    for kind, body in (_segments(text) if commands else [('text', text)]):
        if kind == 'command':
            lines += _command_rows(body, width, len(rest) + 2)
            lead = rest
            continue
        for part in word_wrap(body.strip(), max(10, width - len(rest))):
            lines.append(lead + part)
            lead = rest
    return lines or [first.rstrip()]


def _plain(value):
    """A detected fact as words: no brackets, no booleans as True or False."""
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if value is None or value == '':
        return 'none'
    if isinstance(value, dict):
        return ', '.join('%s %s' % (str(key).replace('_', ' '), _plain(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return '; '.join(_plain(item) for item in value) or 'none'
    return screen_words(STATE_WORDS.get(value, str(value))) if isinstance(value, str) else str(value)


_CLOSING_FULL_STOP = re.compile(r'(?<=[A-Za-z0-9)])\.$')
# The detected facts whose value is a sentence: the sign-in messages (FOUND_LABELS names exactly those). Every other fact is a
# value, a name or a list of them, and keeps the punctuation it carries.
SENTENCE_FACTS = frozenset(FOUND_LABELS)


def _fact(key, item):
    """One detected fact as 'label: value'. A fact that is a sentence (the sign-in message) ends in a full stop; the semicolon that
    joins the facts takes its place, so no '.;' stands in the row. No other value is touched: a name such as graph.example. ends
    in a dot of its own."""
    text = _plain(item)
    if str(key) in SENTENCE_FACTS:
        text = _CLOSING_FULL_STOP.sub('', text)
    return '%s: %s' % (FOUND_LABELS.get(str(key), str(key).replace('_', ' ')), text)


def goal_summary(view):
    """The one-line verdict of a goal. The heading of the goal block and the closing line of the screen are both this, from the
    same status, so the two cannot differ."""
    return 'GOAL READINESS: %s (status: %s)' % (view['goal'], view['status'])


def _goal_lines(view, width, operand=None):
    """The goal's readiness: its status, the selected directory, host and tenant, the needed rows and what is not checked.
    operand is the surveyed directory as a command argument, as the path writer wrote it for this screen."""
    from .readiness import capture_contact, directory_hidden, screen_note, without_stand_in
    from .workbench_screens import word_wrap
    host = view['host']
    hidden = directory_hidden(view['directory'])
    lines = [goal_summary(view)]
    # A refused name prints as DIRECTORY; start_lines said once, under its header, that the name is not shown.
    lines += _flow('Directory: %s' % ('DIRECTORY' if hidden else view['directory']), width, '', '    ')
    lines += _flow('Host: os %s, platform %s, machine %s, Python %s' % (host['os_name'], host['sys_platform'], host['machine'],
                                                                       host['python_version']), width, '', '    ')
    lines += _flow('Supported profiles: %s' % (', '.join(host['supported_profiles']) or 'none'), width, '', '    ')
    lines += _flow('Unsupported profiles: %s' % (', '.join(host['unsupported_profiles']) or 'none'), width, '', '    ')
    lines += _flow('Tenant named by the surveyed inputs: %s' % (', '.join(view['tenants']) or 'none named in GUID form'),
                   width, '', '    ')
    shown_signin = False
    for name in ('azure', 'github'):
        verdict = view.get('signin', {}).get(name)
        if verdict:
            lines += _flow('%s: %s' % (SIGNIN_LABELS[name], verdict['message']), width, '', '    ')
            shown_signin = True
    if shown_signin:
        # Said once, where a sign-in is shown: this screen reports and exits 0; the status command is the one that passes or fails.
        tenants = view['tenants']
        flag = ' --tenant %s' % tenants[0] if len(tenants) == 1 else ''
        lines += _flow('This screen is a report and exits 0 whatever it finds; for a pass or fail exit code run: '
                       'intune-iac signin status%s.' % flag, width, '', '    ', commands=True)
    lines.append('NEEDED FOR THIS GOAL')
    for row in (row for row in view['rows'] if row['needed']):
        lines.append('  %s: %s' % (row['label'], row['state']))
        found = '; '.join(_fact(key, item) for key, item in row['detected'].items())
        lines += _flow('Found: %s' % (found or 'nothing'), width, '    ', '      ')
        if row['state'] == 'ready' and not row['missing']:
            lines.append('    Missing: nothing')
        else:
            lines.append('    %s:' % ('Could not check' if row['state'] == 'unknown' else 'Missing'))
            for note in row['missing']:
                said = screen_note(note, operand, hidden=hidden)
                # a recorded note (one screen_note did not write) is printed only when no word in it is refused
                lines += _flow(said if said != note else recorded_text(note, hidden), width, '      - ', '        ', commands=True)
        lines.append('    Next action (%s):' % row['owner_role'])
        step = recorded_text(row['next_action'], hidden)
        lines += _flow(step, width, '      ', '      ', commands=True)
        contact = capture_contact(step)
        if contact:
            lines += _flow(contact, width, '      ', '      ')
    others = [row['label'] for row in view['rows'] if not row['needed']]
    if others:
        lines += _flow('Not needed for this goal: %s.' % ', '.join(others), width, '', '    ')
    if view['goal'] != 'inspect':
        lines.append('NOT CHECKED HERE')
        for note in list(view['not_established']) + list(view['omitted_facts']):
            for index, part in enumerate(word_wrap(without_stand_in(note) if hidden else note, width - 4)):
                lines.append(('  - ' if index == 0 else '    ') + part)
    return lines


def start_lines(value, width, goal=None, goal_hint=False):
    """The survey as a readable screen: what was found, each item's states, the next steps and what is missing.

    goal is the result of goal_readiness and adds that goal's readiness after the survey; goal_hint adds the one closing line
    that names the goals and the flag. The workspace screen passes neither.
    """
    from .readiness import DIRECTORY_NOT_SHOWN_SENTENCE, IN_WORDS, without_stand_in
    from .workbench_screens import word_wrap
    lines = ['INTUNE WORKBENCH: START']
    # The directory is user input: a name the output-path rule of signin collect refuses prints as DIRECTORY, here, in the
    # Directory: line, in a note's command and in the catalog pointer, and the screen says once, under its header, that it is not shown.
    # The next steps and the directory operand for the screen are built from the operands (Survey.text_build); a survey that this
    # module did not build (plain data) has only the recorded steps, shown only when they name nothing the screen may not show.
    built = getattr(value, 'text_build', None)
    if built is not None:
        value, placeholders = built, set(value.text_placeholders)
    else:
        fields = plain_screen_directory(value.get('directory'))
        placeholders = set()
        value = screen_survey(value, [shown_step(action, fields['directory_hidden']) for action in value['next_actions']],
                              placeholders)
        value.update(fields)
    hidden, operand = value['directory_hidden'], value['directory_operand']
    actions = value['next_actions']
    lines += word_wrap('%s | offline (no live connection) | synthetic evidence stays labelled synthetic' % value['directory'], width)
    if hidden:
        lines += word_wrap(DIRECTORY_NOT_SHOWN_SENTENCE, width)
    if PATH_PLACEHOLDER in placeholders:
        lines += word_wrap(PATH_NOT_SHOWN_SENTENCE, width)
    if value['items']:
        lines.append('FOUND')
        for item in value['items']:
            label = '  %-16s' % LABELS.get(item['kind'], item['kind'])
            text = item['path'] + '  ' + _summary(item)
            for index, part in enumerate(word_wrap(text, max(10, width - len(label)))):
                lines.append((label if index == 0 else ' ' * len(label)) + part)
            states = item['states']
            # Usable here, offline; "configured" read as if a live connection were set up (item 15).
            configured = 'usable here' if states.get('configured') else 'not usable here: ' + str(states.get('configured_reason', 'incomplete')).replace('_', ' ')
            words = screen_words(' | '.join(['discovered', configured, STATE_WORDS.get(states['authenticated'], states['authenticated']),
                                             STATE_WORDS.get(states['qualified'], states['qualified'])]))
            for part in word_wrap(words, max(10, width - len(label))):
                lines.append(' ' * len(label) + part)
    else:
        lines += word_wrap('Nothing recognized here yet.', width)
    if actions:
        # No heading over nothing: an empty NEXT promised steps that were not there.
        lines.append('NEXT')
    for number, action in enumerate(actions, 1):
        prefix = '  %d. ' % number
        lines += _flow(action, width, prefix, ' ' * len(prefix), commands=True)
    lines.append('MISSING')
    for note in value['missing']:
        for index, part in enumerate(word_wrap(without_stand_in(note) if hidden else note, width - 4)):
            lines.append(('  - ' if index == 0 else '    ') + part)
    if value.get('skipped_links'):
        lines += word_wrap('Symbolic links not followed: ' + ', '.join(value['skipped_links']), width)
    if value.get('truncated'):
        lines += word_wrap('The walk stopped at %d entries; narrow the directory to see everything.' % MAX_ENTRIES, width)
    if goal:
        lines += _goal_lines(goal, width, operand)
    elif goal_hint:
        lines += word_wrap(GOAL_HINT, width)
    if goal or goal_hint:
        # One pointer, not a copy: the catalog holds what each goal needs and the saved projects. Its directory is the path
        # writer's operand (a refused name is DIRECTORY there), like every other command on the screen.
        # A directory the screen may not show is said in words, as the catalog says its own start command: DIRECTORY would be a
        # real folder to a shell.
        where = IN_WORDS % 'catalog' if hidden else 'intune-iac catalog%s' % (' ' + operand if operand else '')
        lines += _flow('Catalog of what this build supports and where each goal stands: ' + where, width, '', '    ', commands=True)
    if goal:
        # The goal block is longer than a 40-row pane, which then shows only the tail of the screen: the verdict closes the
        # screen too. It is a short fixed line and is never wrapped, so a pane always shows it whole.
        lines.append(goal_summary(goal))
    return guard_rows(lines)
