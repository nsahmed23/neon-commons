"""Persistent local workbench presentation over the existing Intune engine.

The supported execution adapter is explicitly synthetic. Neither this terminal
nor its approval digest confers Graph, provider, or organizational authority.
All imported strings are rendered as ASCII JSON; original values stay in the
observation store. The line terminal also works over redirected stdin.
"""
from __future__ import annotations

import json
import shlex
import shutil
import textwrap

from .io import AppError, load_json


def add_parser(commands):
    group = commands.add_parser('workbench', help='Persistent inspection, collection, history and explicitly synthetic maintenance')
    sub = group.add_subparsers(dest='workbench_command', required=True)
    init = sub.add_parser('init', help='Create a private tenant-scoped observation store; no IaC required')
    init.add_argument('--root', required=True)
    init.add_argument('--tenant', required=True)
    backup = sub.add_parser('backup', help='Create a new private SQLite backup; retain its receipt independently')
    backup.add_argument('--root', required=True)
    backup.add_argument('--output', required=True)
    restore = sub.add_parser('restore', help='Restore validated local observations to a new private root; not remote infrastructure')
    restore.add_argument('--input', required=True)
    restore.add_argument('--root', required=True)
    restore.add_argument('--tenant', required=True)
    lab = sub.add_parser('lab-create', aliases=['lab-init'], help='Create the existing local synthetic service from a synthetic capture')
    lab.add_argument('--service-root', '--root', dest='service_root', required=True)
    lab.add_argument('--input', required=True)
    lab.add_argument('--object', '--policy', dest='object', action='append', required=True)
    collect = sub.add_parser('collect', help='Collect independently of the terminal into persistent observations')
    collect.add_argument('--root', required=True)
    collect.add_argument('--service-root', required=True)
    collect.add_argument('--observed-at')
    collect.add_argument('--deployment', help='Synthetic deployment observation JSON file')
    collect.add_argument('--source', help='Declared source/repository provenance JSON file; not authenticated authority')
    collect.add_argument('--repo', help='Explicit local Atmos repository to inspect read-only with the existing literal resolver')
    collect.add_argument('--stack', help='Physical manifest selector for --repo')
    collect.add_argument('--component', help='Component selector for --repo')
    collect.add_argument('--fault', choices=['deny', 'throttle', 'cross-origin', 'loop'])
    for name in ('overview', 'health', 'queue', 'dictionary', 'search', 'inspect', 'settings', 'relationships', 'history', 'compare', 'operations', 'terminal'):
        item = sub.add_parser(name)
        item.add_argument('--root', required=True)
        if name in ('inspect', 'settings', 'relationships', 'history', 'compare'):
            item.add_argument('--object', required=True, help='Exact immutable object ID, never a display name')
        if name in ('search', 'dictionary'): item.add_argument('--query', default='')
        if name == 'operations': item.add_argument('--object')
        if name in ('history', 'operations'):
            item.add_argument('--limit', type=int, help='Explicit bounded page size, 1 through 1000')
            item.add_argument('--offset', type=int, default=0)
        if name == 'compare':
            item.add_argument('--before', required=True)
            item.add_argument('--after', required=True)
        if name == 'terminal': item.add_argument('--service-root')
    propose = sub.add_parser('propose', help='Prepare a bounded correction with existing engine evidence; synthetic service only')
    for name in ('root', 'service-root', 'object', 'desired', 'output'):
        propose.add_argument('--' + name, required=True)
    propose.add_argument('--context')
    restore_proposal = sub.add_parser('restore-propose', help='Propose historical restoration as a new change requiring independent fresh review')
    restore_proposal.add_argument('--operation', required=True)
    restore_proposal.add_argument('--output', required=True)
    for name in ('review', 'execute', 'reconcile'):
        item = sub.add_parser(name)
        item.add_argument('--operation', required=True)
        if name == 'execute':
            item.add_argument('--approve-digest', required=True, help='Explicit digest from fresh review; local synthetic approval only')
            item.add_argument('--fault', choices=['lost-response', 'after-policy', 'deny', 'throttle'])


def _store(root):
    from .workbench_store import WorkbenchStore
    return WorkbenchStore(root)


def _source_metadata(args):
    value = load_json(args.source) if args.source else {}
    if not isinstance(value, dict): raise AppError('workbench_source_invalid', 'Source metadata must be a JSON object.')
    if any((args.repo, args.stack, args.component)):
        if not all((args.repo, args.stack, args.component)):
            raise AppError('workbench_repository_selection_required', 'Supply --repo, --stack and --component together.')
        from .repository import public_resolution, resolve_component
        report = public_resolution(resolve_component(args.repo, args.stack, args.component))
        value.update(repository_path=report['root'], atmos_stack=args.stack, component=args.component,
                     source_path=report.get('implementation_path'), repository_resolution=report,
                     inheritance=report.get('provenance', {}), repository_assurance='local_literal_inspection_only')
    return value


def _search(store, query):
    overview = store.overview()
    rows = overview.get('objects', [])
    matched = [row for row in rows if query.casefold() in str(row.get('name', '')).casefold()
               or query.casefold() in row['object_id'].casefold()
               or any(query.casefold() in str(edge.get('target_id', '')).casefold()
                      for edge in row.get('relationships', []) if edge.get('relation') == 'setting')]
    return {'evidence_class': 'synthetic', 'query': query, 'objects': matched,
            'freshness': overview.get('freshness'), 'last_attempt': overview.get('last_attempt'),
            'selection': 'Use an exact immutable object_id; duplicate names are not identities.'}


def _health(store):
    value = store.overview()
    return {key: item for key, item in value.items() if key != 'objects'} | {
        'objects': [{key: row.get(key) for key in ('object_id', 'name', 'observed_at', 'coverage', 'health')}
                    for row in value.get('objects', [])],
        'qualification': 'Synthetic observations only; service acceptance is not endpoint success.'}


def _queue(store):
    """Evidence gaps are review findings, never inferred authorization to fix."""
    overview = store.overview()
    findings = []
    operations = store.operations()
    for row in overview.get('objects', []):
        reasons = []
        if row.get('freshness') != 'fresh':
            reasons.append(('observation_stale', 'A current complete observation is required before assessing changes.'))
        attempt = overview.get('last_attempt')
        if attempt and attempt.get('status') != 'complete':
            reasons.append(('collection_incomplete', 'Last collection did not complete; preserved values are last-good evidence.'))
        health = row.get('health', {})
        if health.get('report_freshness') != 'fresh' or health.get('unknown_or_stale'):
            reasons.append(('reporting_incomplete', 'Missing or stale reporting cannot establish rollout readiness or endpoint success.'))
        source = row.get('source') or {}
        if not source.get('owner'):
            reasons.append(('ownership_unknown', 'An observed policy does not establish repository or team ownership.'))
        related = [operation for operation in operations if operation.get('object_id') == row['object_id']]
        for finding, rationale in reasons:
            findings.append({'tenant_id': overview['tenant_id'], 'object_id': row['object_id'],
                'owner': source.get('owner'), 'owner_assertion': 'source_declared' if source.get('owner') else 'unknown',
                'finding': finding, 'evidence': {'snapshot_id': row['snapshot_id'], 'observed_at': row['observed_at'],
                    'last_attempt': attempt, 'evidence_class': 'synthetic'},
                'freshness': row.get('freshness'), 'priority': 'review', 'priority_rationale': rationale,
                'review_due': None, 'related_proposals': related, 'exception_expiry': None,
                'compatibility': {'profile': 'synthetic_windows_settings_catalog', 'native_provider_qualified': False},
                'action_state': 'review_required', 'automatic_remediation': False})
    if not overview.get('objects'):
        findings.append({'tenant_id': overview['tenant_id'], 'object_id': None, 'owner': None,
                         'finding': 'no_complete_observations', 'evidence': {'last_attempt': overview.get('last_attempt')},
                         'freshness': 'unknown', 'priority': 'review', 'priority_rationale': 'Collect before assessing policy state.',
                         'review_due': None, 'related_proposals': [], 'exception_expiry': None,
                         'compatibility': 'unqualified', 'action_state': 'collection_required', 'automatic_remediation': False})
    return {'evidence_class': 'synthetic', 'cloud_authority': False, 'findings': findings}


def _dictionary(store, query=''):
    """Observed setting identifiers and exact uses, without invented vendor facts."""
    entries = {}
    for row in store.overview().get('objects', []):
        pending = [row['body'].get('settings')]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                identifier = value.get('settingDefinitionId')
                if isinstance(identifier, str) and query.casefold() in identifier.casefold():
                    entry = entries.setdefault(identifier, {'identifier': identifier, 'name': None, 'aliases': [],
                        'meaning': 'unknown', 'applicability': 'Vendor applicability unqualified',
                        'assertion_class': 'observed', 'vendor_dictionary': 'unresolved', 'actual_uses': []})
                    entry['actual_uses'].append({'object_id': row['object_id'], 'name': row['name'],
                        'type': value.get('@odata.type'), 'value': value, 'snapshot_id': row['snapshot_id'],
                        'observed_at': row['observed_at'], 'source': row.get('source'), 'ownership': 'unknown'})
                pending.extend(value.values())
            elif isinstance(value, list): pending.extend(value)
    return {'evidence_class': 'synthetic', 'query': query, 'entries': [entries[key] for key in sorted(entries)],
            'qualification': 'Observed IDs and values only; vendor meaning, applicability and recommendations remain unresolved.'}


def _facet(store, object_id, facet):
    value = store.inspect(object_id)
    if facet == 'settings':
        return {'object_id': object_id, 'snapshot_id': value.get('snapshot_id'),
                'settings': value.get('body', {}).get('settings'), 'source': value.get('source'),
                'dictionary': {'status': 'unresolved', 'reason': 'No authenticated setting-definition dictionary was collected.'}}
    return {'object_id': object_id, 'snapshot_id': value.get('snapshot_id'),
            'relationships': value.get('relationships', []), 'source': value.get('source'),
            'assignments': value.get('body', {}).get('assignments'),
            'ownership': 'Source-declared only; an observation does not establish managed ownership.'}


def command(args):
    name = args.workbench_command
    if name == 'init':
        from .workbench_store import WorkbenchStore
        store = WorkbenchStore.create(args.root, args.tenant)
        return {'status': 'created', 'evidence_class': 'synthetic', 'overview': store.overview(),
                'external_execution': False}
    if name == 'backup':
        return dict(_store(args.root).backup(args.output),
                    integrity_limit='Retain and compare the backup receipt independently; a self-supplied digest does not authenticate provenance.')
    if name == 'restore':
        from .workbench_store import WorkbenchStore
        store = WorkbenchStore.restore(args.input, args.root, tenant_id=args.tenant)
        return {'status': 'restored', 'evidence_class': 'local_sqlite_backup', 'overview': store.overview(),
                'external_execution': False, 'remote_infrastructure_restored': False}
    if name in ('lab-create', 'lab-init'):
        from .modeled_service import ModeledService
        service = ModeledService.create(args.service_root, load_json(args.input), args.object)
        snapshot = service.snapshot()
        return {'status': 'created', 'evidence_class': 'synthetic', 'external_execution': False,
                'tenant_id': snapshot['current']['tenant_id'], 'object_ids': sorted(snapshot['current']['objects'])}
    if name in ('review', 'execute', 'reconcile', 'propose', 'restore-propose'):
        from . import maintenance
        if name == 'restore-propose': return maintenance.propose_restore(args.operation, args.output)
        if name == 'review': return maintenance.review(args.operation)
        if name == 'execute': return maintenance.execute(args.operation, approve_digest=args.approve_digest, fault=args.fault)
        if name == 'reconcile': return maintenance.reconcile(args.operation)
        return maintenance.propose(args.root, args.service_root, args.object, args.desired, args.output, context_path=args.context)
    if name == 'terminal': return run_terminal(args.root, service_root=args.service_root)
    store = _store(args.root)
    if name == 'collect':
        from .modeled_service import ModeledService
        return store.collect(ModeledService(args.service_root), observed_at=args.observed_at, fault=args.fault,
                             deployment=load_json(args.deployment) if args.deployment else None,
                             source=_source_metadata(args))
    if name == 'overview': return store.overview()
    if name == 'health': return _health(store)
    if name == 'queue': return _queue(store)
    if name == 'dictionary': return _dictionary(store, args.query)
    if name == 'search': return _search(store, args.query)
    if name == 'inspect': return store.inspect(args.object)
    if name in ('settings', 'relationships'): return _facet(store, args.object, name)
    if name == 'history': return {'object_id': args.object, 'history': store.history(args.object, limit=args.limit, offset=args.offset),
                                  'limit': args.limit, 'offset': args.offset}
    if name == 'compare': return store.compare(args.object, args.before, args.after)
    if name == 'operations': return {'operations': store.operations(object_id=args.object, limit=args.limit, offset=args.offset),
                                     'limit': args.limit, 'offset': args.offset}
    raise AppError('unknown_workbench_command', 'Unknown workbench command.')


HELP = {
    'navigation': ['overview', 'search TEXT', 'select EXACT_OBJECT_ID', 'inspect', 'settings',
                   'relationships', 'dictionary [SETTING_ID_QUERY]', 'history [LIMIT [OFFSET]]', 'compare BEFORE_SNAPSHOT AFTER_SNAPSHOT', 'health', 'queue', 'operations [LIMIT [OFFSET]]', 'back', 'cancel', 'quit'],
    'maintenance': ['propose DESIRED_JSON OUTPUT_DIR [CONTEXT_JSON]', 'review OPERATION_DIR',
                    'execute OPERATION_DIR EXPLICIT_REVIEW_DIGEST [FAULT]', 'reconcile OPERATION_DIR',
                    'restore-propose PREVIOUS_OPERATION_DIR NEW_OUTPUT_DIR (fresh review required)'],
    'collection': ['collect (requires --service-root; also runs as a separate headless command)'],
    'limits': 'Local synthetic service only. No native provider, GitHub, Azure, Intune or endpoint qualification.',
}


def _render(value, output_fn):
    # Match the existing CLI's safe JSON presentation. Escaping all non-ASCII
    # also neutralizes bidi/C1/OSC controls without destroying stored evidence.
    width = max(16, min(160, shutil.get_terminal_size(fallback=(80, 24)).columns))
    for line in json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False).splitlines():
        for part in textwrap.wrap(line, width=width, replace_whitespace=False, drop_whitespace=False) or ['']:
            output_fn(part)


def run_terminal(root, *, service_root=None, input_fn=None, output_fn=None):
    """Accessible line terminal; no shell invocation, animation, or hidden approval.

    The store, not the process, owns history. Closing this interface never stops
    another process's collector. EOF and back/cancel cannot dispatch mutation.
    """
    input_fn = input if input_fn is None else input_fn
    output_fn = print if output_fn is None else output_fn
    store = _store(root)
    selected = None
    _render({'title': 'Intune Workbench', 'evidence_class': 'synthetic', 'commands': HELP}, output_fn)
    _render(store.overview(), output_fn)
    while True:
        try:
            line = input_fn('workbench> ')
            if len(line) > 16384: raise ValueError('command too long')
            parts = shlex.split(line)
            if not parts: continue
            name, values = parts[0].lower(), parts[1:]
            if name in ('quit', 'exit') and not values:
                return {'status': 'closed', 'evidence_class': 'synthetic', 'history_persisted': True}
            if name == 'help' and not values: result = HELP
            elif name in ('back', 'cancel') and not values:
                selected = None
                result = {'status': 'selection_cleared', 'mutation_dispatched': False}
            elif name == 'overview' and not values: result = store.overview()
            elif name == 'search': result = _search(store, ' '.join(values))
            elif name == 'select' and len(values) == 1:
                result = store.inspect(values[0])
                selected = values[0]
            elif name == 'health' and not values: result = _health(store)
            elif name == 'queue' and not values: result = _queue(store)
            elif name == 'dictionary': result = _dictionary(store, ' '.join(values))
            elif name == 'operations' and len(values) <= 2:
                result = {'operations': store.operations(object_id=selected, limit=int(values[0]) if values else None,
                          offset=int(values[1]) if len(values) == 2 else 0)}
            elif name in ('inspect', 'settings', 'relationships', 'history', 'compare', 'propose'):
                if selected is None: raise AppError('selection_required', 'Select an exact immutable object ID first.')
                if name == 'inspect' and not values: result = store.inspect(selected)
                elif name in ('settings', 'relationships') and not values: result = _facet(store, selected, name)
                elif name == 'history' and len(values) <= 2:
                    result = {'object_id': selected, 'history': store.history(selected,
                              limit=int(values[0]) if values else None, offset=int(values[1]) if len(values) == 2 else 0)}
                elif name == 'compare' and len(values) == 2: result = store.compare(selected, *values)
                elif name == 'propose' and len(values) in (2, 3):
                    if service_root is None: raise AppError('service_required', 'Supply --service-root for synthetic maintenance.')
                    from .maintenance import propose
                    result = propose(root, service_root, selected, values[0], values[1], context_path=values[2] if len(values) == 3 else None)
                else: raise ValueError('invalid command arguments')
            elif name in ('review', 'execute', 'reconcile', 'restore-propose'):
                from . import maintenance
                if name == 'review' and len(values) == 1: result = maintenance.review(values[0])
                elif name == 'reconcile' and len(values) == 1: result = maintenance.reconcile(values[0])
                elif name == 'restore-propose' and len(values) == 2: result = maintenance.propose_restore(*values)
                elif name == 'execute' and len(values) in (2, 3):
                    result = maintenance.execute(values[0], approve_digest=values[1], fault=values[2] if len(values) == 3 else None)
                else: raise ValueError('invalid command arguments')
            elif name == 'collect' and not values:
                if service_root is None: raise AppError('service_required', 'Supply --service-root for synthetic collection.')
                from .modeled_service import ModeledService
                result = store.collect(ModeledService(service_root))
            else: raise ValueError('unknown command')
            _render(result, output_fn)
        except EOFError:
            return {'status': 'closed', 'evidence_class': 'synthetic', 'history_persisted': True}
        except KeyboardInterrupt:
            _render({'status': 'interrupted', 'recovery': 'Inspect persisted operations and reconcile before retrying any uncertain execution.'}, output_fn)
            return {'status': 'interrupted', 'evidence_class': 'synthetic'}
        except AppError as error:
            _render({'status': 'error', 'error': {'code': error.code, 'message': error.message}}, output_fn)
        except (ValueError, TypeError, KeyError, OSError):
            _render({'status': 'error', 'error': {'code': 'invalid_workbench_request',
                     'message': 'Command or local input is invalid. Enter help for exact syntax.'}}, output_fn)
