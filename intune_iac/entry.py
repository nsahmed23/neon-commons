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


def _next_actions(items, root=None, relative_to=None):
    show = _shower(root, relative_to)
    # In a command a path with a space is quoted for the shell, as the rest of the product quotes one.
    q = lambda rel: shlex.quote(show(rel))
    kinds = {}
    for item in items:
        kinds.setdefault(item['kind'], []).append(item)
    actions = []
    conflicts = {'repository_owned_edit': 'Review the repository-owned edit, or hand it off to the repository workflow',
                 'output_changed': 'Resolve the changed output (new-path, review or cancel)',
                 'output_conflict': 'Resolve the output conflict (new-path, review or cancel)',
                 'outcome_unknown': 'Review the uncertain generation outcome before any retry'}
    for item in kinds.get('wizard_session', []):
        if item.get('valid') and item.get('step') != 'complete':
            lead = conflicts.get(item.get('conflict_reason'), 'Resume the wizard session') if item.get('step') == 'conflict' else 'Resume the wizard session'
            actions.append('%s: %s wizard --session %s' % (lead, PROGRAM, q(item['path'])))
    for item in kinds.get('journey_session', []):
        if item.get('valid') and item.get('lifecycle') not in ('complete_simulation',):
            actions.append('Resume the journey: %s wizard --journey --session %s' % (PROGRAM, q(item['path'])))
    for item in kinds.get('guided_session', []):
        if item.get('valid') and item.get('lifecycle') != 'complete_local':
            actions.append('Resume the guided session: %s wizard --guided --session %s' % (PROGRAM, q(item['path'])))
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
            actions.append('Collect into %s: %s workbench collect --root %s --service-root %s' % (
                show(store['path']), PROGRAM, q(store['path']), q(service['path']) if service else 'SERVICE_ROOT'))
        actions.append('Open the workspace: %s workbench workspace --root %s%s' % (
            PROGRAM, q(store['path']), ' --service-root ' + q(service['path']) if service else ''))
    if kinds.get('repository') and not stores:
        # repository-entry reads a store; there is none here to name.
        actions.append('Create a store first: %s workbench init --root STORE --tenant TENANT_ID' % PROGRAM)
    for repository in kinds.get('repository', []):
        recorded =[(store, intent) for store in stores for intent in store.get('intents', [])
                    if intent.get('repository') and Path(intent['repository']).name == _name(root, repository['path'])]
        if recorded:
            store, intent = recorded[-1]
            actions.append('Check the repository against its recorded intent: %s workbench repository-status --root %s --object %s' % (
                PROGRAM, q(store['path']), intent['object_id']))
            continue
        actions.append('See the policies the repository %s holds and the exact command to record each: %s workbench '
                       'repository-entry --root %s --repo %s (in the workspace: :repository-entry %s)' % (
                           show(repository['path']), PROGRAM, q(stores[0]['path']) if stores else 'STORE', q(repository['path']),
                           q(repository['path'])))
    used = {item.get('input') for item in kinds.get('wizard_session', [])}
    contexts = kinds.get('context', [])
    for export in kinds.get('export', []):
        if export['path'] not in used:
            actions.append('Start from the export %s: %s wizard --session NEW_SESSION.json --input %s --context %s --output NEW_OUTPUT_DIR' % (
                show(export['path']), PROGRAM, q(export['path']), q(contexts[0]['path']) if contexts else 'CONTEXT_JSON'))
    for operation in kinds.get('operation', []):
        actions.append('Follow the operation: %s workbench delivery --operation %s' % (PROGRAM, q(operation['path'])))
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
    return {'schema_version': VERSION, 'directory': str(root), 'connection': 'offline', 'items': items,
            'next_actions': _next_actions(items, root, relative_to),'missing': _missing(items), 'skipped_links': links,
            'truncated': truncated, 'execution_authorized': False, 'cloud_authority': False}


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
_TOKEN = re.compile(r"(?:'[^']*'|[^\s'])+")
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


def _flow(text, width, first, rest, commands=False):
    """Wrap text at spaces to the width; with commands, each command in it goes on its own rows (see _command_rows)."""
    from .workbench_screens import word_wrap
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
    return STATE_WORDS.get(value, str(value)) if isinstance(value, str) else str(value)


def _goal_lines(view, width):
    """The goal's readiness: its status, the selected directory, host and tenant, the needed rows and what is not checked."""
    from .workbench_screens import word_wrap
    host = view['host']
    lines = ['GOAL READINESS: %s (status: %s)' % (view['goal'], view['status'])]
    lines += _flow('Directory: %s' % view['directory'], width, '', '    ')
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
        found = '; '.join('%s: %s' % (FOUND_LABELS.get(str(key), str(key).replace('_', ' ')), _plain(item))
                          for key, item in row['detected'].items())
        lines += _flow('Found: %s' % (found or 'nothing'), width, '    ', '      ')
        if row['state'] == 'ready' and not row['missing']:
            lines.append('    Missing: nothing')
        else:
            lines.append('    %s:' % ('Could not check' if row['state'] == 'unknown' else 'Missing'))
            for note in row['missing']:
                lines += _flow(note, width, '      - ', '        ', commands=True)
        lines.append('    Next action (%s):' % row['owner_role'])
        lines += _flow(row['next_action'], width, '      ', '      ', commands=True)
    others = [row['label'] for row in view['rows'] if not row['needed']]
    if others:
        lines += _flow('Not needed for this goal: %s.' % ', '.join(others), width, '', '    ')
    if view['goal'] != 'inspect':
        lines.append('NOT CHECKED HERE')
        for note in list(view['not_established']) + list(view['omitted_facts']):
            for index, part in enumerate(word_wrap(note, width - 4)):
                lines.append(('  - ' if index == 0 else '    ') + part)
    return lines


def start_lines(value, width, goal=None, goal_hint=False):
    """The survey as a readable screen: what was found, each item's states, the next steps and what is missing.

    goal is the result of goal_readiness and adds that goal's readiness after the survey; goal_hint adds the one closing line
    that names the goals and the flag. The workspace screen passes neither.
    """
    from .workbench_screens import word_wrap
    lines = ['INTUNE WORKBENCH: START']
    lines += word_wrap('%s | offline (no live connection) | synthetic evidence stays labelled synthetic' % value['directory'], width)
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
            words = ' | '.join(['discovered', configured, STATE_WORDS.get(states['authenticated'], states['authenticated']),
                                STATE_WORDS.get(states['qualified'], states['qualified'])])
            for part in word_wrap(words, max(10, width - len(label))):
                lines.append(' ' * len(label) + part)
    else:
        lines += word_wrap('Nothing recognized here yet.', width)
    if value['next_actions']:
        # No heading over nothing: an empty NEXT promised steps that were not there.
        lines.append('NEXT')
    for number, action in enumerate(value['next_actions'], 1):
        prefix = '  %d. ' % number
        lines += _flow(action, width, prefix, ' ' * len(prefix), commands=True)
    lines.append('MISSING')
    for note in value['missing']:
        for index, part in enumerate(word_wrap(note, width - 4)):
            lines.append(('  - ' if index == 0 else '    ') + part)
    if value.get('skipped_links'):
        lines += word_wrap('Symbolic links not followed: ' + ', '.join(value['skipped_links']), width)
    if value.get('truncated'):
        lines += word_wrap('The walk stopped at %d entries; narrow the directory to see everything.' % MAX_ENTRIES, width)
    if goal:
        lines += _goal_lines(goal, width)
    elif goal_hint:
        lines += word_wrap(GOAL_HINT, width)
    if goal or goal_hint:
        # One pointer, not a copy: the catalog holds what each goal needs and the saved projects.
        directory = value['directory']
        # A name with a control character is never echoed into a command; the placeholder stands for it.
        shown = shlex.quote(directory) if directory.isprintable() else 'DIRECTORY'
        lines += _flow('Catalog of what this build supports and where each goal stands: intune-iac catalog %s' % shown,
                       width, '', '    ', commands=True)
    return lines
