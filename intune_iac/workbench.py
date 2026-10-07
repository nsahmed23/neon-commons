"""Persistent local workbench presentation over the existing Intune engine.

Local maintenance execution is explicitly synthetic; protected service routes
prepare or observe the separate host contract. Neither this terminal nor its
approval digest confers Graph, provider, or organizational authority.
All imported strings are rendered as ASCII JSON; original values stay in the
observation store. The line terminal also works over redirected stdin.
"""
from __future__ import annotations

import json
import shlex
import shutil
import signal
import textwrap
import threading

from .io import AppError, load_json


def add_parser(commands):
    group = commands.add_parser('workbench', help='Persistent inspection, collection, history and explicitly synthetic maintenance')
    sub = group.add_subparsers(dest='workbench_command', required=True)
    from .workbench_parsers import add_observer_parser
    add_observer_parser(sub)
    from .workbench_views import add_parser as add_views_parser
    add_views_parser(sub)
    from .workbench_queue import add_parser as add_queue_parser
    add_queue_parser(sub)
    workspace = sub.add_parser('workspace', help='Visual workspace over the complete text command engine; text fallback without a supported TTY')
    workspace.add_argument('--root', required=True)
    workspace.add_argument('--service-root')
    workspace.add_argument('--theme', choices=('dark', 'light'), default='dark')
    workspace.add_argument('--no-color', action='store_true')
    workspace.add_argument('--reduced-motion', action='store_true', default=True,
                           help='Keep all information without animation; also the default')
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
    migrate = sub.add_parser('migrate', help='Back up and explicitly migrate the observation schema')
    migrate.add_argument('--root', required=True)
    migrate.add_argument('--backup', required=True)
    for name in ('adoption-preview', 'adopt'):
        item = sub.add_parser(name, help='Reconstruct a completed local wizard and connect a separate synthetic maintenance model')
        item.add_argument('--root', required=True)
        item.add_argument('--session', required=True)
        if name == 'adopt': item.add_argument('--output', required=True, help='New private handoff directory; partial state is preserved for explicit resume')
    capture = sub.add_parser('import-capture', help='Import an existing Graph capture directory and its raw-page receipts without network access')
    capture.add_argument('--root', required=True)
    capture.add_argument('--capture', required=True)
    for name in ('device-evidence-import', 'workflow-import'):
        item = sub.add_parser(name, help='Import inert tenant/object-bound local evidence')
        item.add_argument('--root', required=True)
        item.add_argument('--input', required=True)
    reference = sub.add_parser('reference-import', help='Record exact pinned local reference bytes without adoption authority')
    for name in ('root', 'input', 'sha256', 'revision', 'source-url', 'license'):
        reference.add_argument('--' + name, required=True)
    reference.add_argument('--assertion-class', choices=['community_reference', 'organization_annotation'], default='community_reference')
    reference_compare = sub.add_parser('reference-compare')
    for name in ('root', 'object', 'reference'):
        reference_compare.add_argument('--' + name, required=True)
    reference_compare.add_argument('--company')
    schedule = sub.add_parser('schedule-create', help='Create a bounded local synthetic collection schedule; installs no daemon')
    for name in ('root', 'service-root', 'output'):
        schedule.add_argument('--' + name, required=True)
    schedule.add_argument('--interval-seconds', type=float, required=True)
    run = sub.add_parser('schedule-run', help='Run an explicit finite local collection window')
    run.add_argument('--job', required=True)
    run.add_argument('--max-runs', type=int, required=True)
    run.add_argument('--max-duration-seconds', type=float, required=True)
    status = sub.add_parser('schedule-status')
    status.add_argument('--job', required=True)
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
    for name in ('overview', 'health', 'queue', 'dictionary', 'references', 'workflows', 'collection-history', 'collection', 'search', 'inspect', 'settings', 'relationships', 'lineage', 'adoption-lineage', 'history', 'history-recent', 'compare', 'operations', 'terminal'):
        item = sub.add_parser(name)
        item.add_argument('--root', required=True)
        if name in ('inspect', 'settings', 'relationships', 'lineage', 'adoption-lineage', 'history', 'history-recent', 'compare', 'workflows'):
            item.add_argument('--object', required=True, help='Exact immutable object ID, never a display name')
        if name in ('search', 'dictionary'): item.add_argument('--query', default='')
        if name in ('operations', 'health', 'collection-history', 'dictionary'): item.add_argument('--object')
        if name in ('history', 'history-recent', 'operations', 'collection-history', 'references', 'overview', 'search', 'dictionary', 'queue', 'health'):
            item.add_argument('--limit', type=int, help='Explicit bounded page size, 1 through 1000')
            item.add_argument('--offset', type=int, default=0)
        if name == 'history-recent': item.set_defaults(limit=10)
        if name == 'compare':
            item.add_argument('--before', required=True)
            item.add_argument('--after', required=True)
        if name == 'collection': item.add_argument('--run', type=int, required=True)
        if name == 'lineage': item.add_argument('--pointer', help='Exact literal JSON pointer for a repository value')
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
            item.add_argument('--visibility-delay-reads', type=int, default=0, help='Local model only: 0 through 16 public GETs serving the previous committed estate')


def _store(root):
    from .host_capabilities import require_profile
    require_profile('workbench_store')
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


def _page_metadata(value):
    return {key: value[key] for key in ('pagination', 'total_inventory_objects') if key in value}


def _search(store, query, *, limit=None, offset=0):
    overview = store.overview(query=query, limit=limit, offset=offset)
    return {'evidence_class': overview.get('evidence_class', 'unknown'), 'query': query,
            'objects': overview.get('objects', []), 'pending_observations': overview.get('pending_observations', []),
            'freshness': overview.get('freshness'), 'last_attempt': overview.get('last_attempt'),
            **_page_metadata(overview),
            'selection': 'Use an exact immutable object_id; duplicate names are not identities.'}


def _health(store, object_id=None, *, limit=None, offset=0):
    from .workbench_health import device_health
    if object_id is not None:
        if limit is not None or offset: raise AppError('workbench_query_invalid', 'Choose one object or an observation page.')
        return device_health(store, object_id)
    value = store.overview(limit=limit, offset=offset)
    return {key: item for key, item in value.items() if key != 'objects'} | {
        'collection_health': value.get('health'),
        'objects': [{**{key: row.get(key) for key in ('object_id', 'name', 'observed_at', 'coverage')},
                     'health': device_health(store, row['object_id'])} for row in value.get('objects', [])],
        'qualification': 'Collection aggregates and policy-bound imported device evidence are separate; neither grants rollout approval.'}


def _queue(store, *, limit=None, offset=0):
    """Evidence gaps are review findings, never inferred authorization to fix."""
    from .workbench_health import device_health
    from .workbench_views import _ownership_result
    import time
    overview = store.overview(limit=limit, offset=offset)
    # One bounded artifact read per kind, not per object/finding. Ownership is
    # an immutable-object/assignment writer claim; a human owner label from a
    # capture or review annotation must not establish that writer relationship.
    ownership_rows = store.artifacts(kind='ownership_index')
    ownership_index = max(ownership_rows, key=lambda item: item['sequence']) if ownership_rows else None
    intents = {}
    for item in store.artifacts(kind='repository_intent'):
        intents[item['data']['target_object_id']] = item
    claims = {}
    if ownership_index:
        for source in ownership_index['data']['document']['sources']:
            for claim in source['claims']:
                claims.setdefault(claim['object_id'], []).append(dict(claim, scope=source['scope'],
                    observed_at=source['observed_at'], coverage=source['coverage']))
    ownership_now = time.time()
    findings = []
    for row in overview.get('objects', []) + overview.get('pending_observations', []):
        reasons = []
        if row.get('freshness') != 'fresh':
            reasons.append(('observation_stale', 'A current complete observation is required before assessing changes.'))
        attempt = row.get('last_attempt', overview.get('last_attempt'))
        if attempt and attempt.get('status') != 'complete':
            reasons.append(('collection_incomplete', 'Last collection did not complete; preserved values are last-good evidence.'))
        health = device_health(store, row['object_id'])
        reporting = health['stages']['execution']
        if (reporting.get('targeted') is None or reporting.get('reporting') is None or
                reporting.get('unknown') is None or reporting['unknown'] > 0 or
                reporting['reporting'] < reporting['targeted']):
            reasons.append(('reporting_incomplete', 'Missing or stale reporting cannot establish rollout readiness or endpoint success.'))
        source = row.get('source') or {}
        intent = intents.get(row['object_id'])
        selected_scope = intent['data']['scope'] if intent else None
        writer = _ownership_result(ownership_index, row['object_id'], selected_scope, ownership_now, claims)
        writer_status = writer['status']
        if writer_status == 'conflicting_claims':
            reasons.append(('ownership_conflicting_claims', 'Multiple declared state addresses claim the same object or assignment writer; resolve the conflict before preparing execution.'))
        elif writer_status == 'no_ownership_found_in_declared_scope':
            reasons.append(('ownership_unclaimed', 'No writer was found in the complete fresh declared scopes; this does not prove absence of writers outside those scopes.'))
        elif writer_status == 'owned_elsewhere':
            reasons.append(('ownership_elsewhere', 'The declared writer belongs to another selected stack/component/backend scope; coordinate its owner before proposing a change.'))
        elif writer_status == 'unknown':
            if ownership_index is not None and not writer['fresh']:
                reasons.append(('ownership_stale', 'Declared ownership evidence is stale or future-dated; collect every scope again before assessing the writer.'))
            else:
                reasons.append(('ownership_unknown', 'Writer ownership is unknown because the index, selected scope, complete scope coverage, or object and assignment writer evidence is missing.'))
        writer_evidence = {key: writer[key] for key in ('status', 'claims', 'conflicting_parts', 'scope',
            'declared_scope_complete', 'fresh', 'evidence_class', 'artifact_id', 'reason') if key in writer}
        writer_evidence.update(cloud_authority=False, execution_authorized=False,
            selected_repository_intent_id=intent['artifact_id'] if intent else None)
        related = store.operations(object_id=row['object_id'])
        for finding, rationale in reasons:
            findings.append({'tenant_id': overview['tenant_id'], 'object_id': row['object_id'],
                'owner': None, 'owner_assertion': 'unknown', 'owner_role': 'human_review_assignee',
                'source_owner_claim': {'value': source.get('owner'), 'assertion_class': 'source_declared'},
                'writer_ownership': writer_evidence,
                'finding': finding, 'evidence': {'snapshot_id': row['snapshot_id'], 'observed_at': row['observed_at'],
                    'last_attempt': attempt, 'evidence_class': row.get('evidence_class', 'unknown'),
                    'policy_reporting': {'artifact_id': health.get('artifact_id'), 'evidence_class': health['evidence_class'],
                        'stage': 'execution', **{key: reporting.get(key) for key in ('targeted', 'reporting', 'unknown')},
                        'endpoint_effectiveness_established': False}},
                'freshness': row.get('freshness'), 'priority': 'review', 'priority_rationale': rationale,
                'review_due': None, 'related_proposals': related, 'exception_expiry': None,
                'compatibility': {'profile': 'synthetic_windows_settings_catalog', 'native_provider_qualified': False},
                'action_state': 'review_required', 'automatic_remediation': False})
    if overview.get('pagination', {}).get('total_objects', len(overview.get('objects', []))) == 0:
        findings.append({'tenant_id': overview['tenant_id'], 'object_id': None, 'owner': None,
                         'finding': 'no_complete_observations', 'evidence': {'last_attempt': overview.get('last_attempt')},
                         'freshness': 'unknown', 'priority': 'review', 'priority_rationale': 'Collect before assessing policy state.',
                         'review_due': None, 'related_proposals': [], 'exception_expiry': None,
                         'compatibility': 'unqualified', 'action_state': 'collection_required', 'automatic_remediation': False})
    from .workbench_queue import decorate_findings
    findings = decorate_findings(store, findings)
    return {'evidence_class': overview.get('evidence_class', 'unknown'), 'cloud_authority': False, 'findings': findings,
            **_page_metadata(overview), 'findings_scope': 'observation_page' if limit is not None else 'all_admitted_observations'}


def _dictionary(store, query='', *, object_id=None, limit=None, offset=0):
    """Observed setting identifiers and exact uses, without invented vendor facts."""
    from .windows_workbench import WindowsWorkbenchStore
    if type(store) is WindowsWorkbenchStore:
        return store.dictionary(query, object_id=object_id, limit=limit, offset=offset)
    from .workbench_provenance import dictionary
    return dictionary(store, query, object_id=object_id, limit=limit, offset=offset)


def _inspection(store, object_id):
    """Combine an exact observed object with the current declared writer evidence.

    The raw observation remains unchanged. Selected repository intent and state
    claims are distinct management evidence, never authenticated cloud ownership.
    """
    from .workbench_views import _intents, _latest, ownership
    value = store.inspect(object_id)
    raw_capture = store.raw_capture_observation(object_id)
    intent = _latest(_intents(store, object_id, None))
    scope = intent['data']['scope'] if intent else None
    writer = ownership(store, object_id, scope)
    return {**value, 'raw_capture_observation': raw_capture,
            'ownership': writer['status'], 'ownership_evidence': writer,
            'selected_repository': None if intent is None else {
                'artifact_id': intent['artifact_id'], 'scope': scope,
                'source_revision': intent['data'].get('source_revision'),
                'evidence_class': intent['data'].get('evidence_class'),
                'selection_basis': 'latest_recorded_repository_intent_for_immutable_object'},
            'management_coverage': {'declared_scope_complete': writer['declared_scope_complete'],
                                    'fresh': writer['fresh'], 'cloud_authority': False}}


def _facet(store, object_id, facet):
    value = _inspection(store, object_id)
    body = value.get('body') or {}
    capture = value.get('raw_capture_observation')
    integrity = capture.get('capture_integrity', {}) if capture else {}
    raw = capture['source'].get('raw_observed', {}) if capture and integrity.get('status') == 'verified_local_bytes' else {}
    raw_scope = {'raw_capture_observation': capture, 'raw_evidence_integrity': integrity,
        'name': value.get('name'), 'observed_at': value.get('observed_at'),
        'raw_mapping_status': capture['status'] if capture else 'unknown',
        'raw_collection_coverage': capture['collections'] if capture else [],
        'raw_mapping_blockers': capture['source'].get('mapping_blockers', []) if capture else [],
        'normalized_value_scope': 'retained_mapped_snapshot' if value.get('snapshot_id') else 'unavailable'}
    if facet == 'settings':
        return {**raw_scope, 'object_id': object_id, 'snapshot_id': value.get('snapshot_id'),
                'raw_observed_settings': raw.get('settings'),
                'settings': body.get('settings'), 'source': value.get('source'), 'coverage': value.get('coverage'),
                'ownership': value['ownership'], 'ownership_evidence': value['ownership_evidence'],
                'dictionary': _dictionary(store, object_id=object_id)}
    from .workbench_health import workflow_lineage
    lineage = workflow_lineage(store, object_id)
    from .workbench_adoption import lineage as adoption_lineage
    adoptions = adoption_lineage(store, object_id)
    adoption_edges = [{'relation': 'generated_from', 'target_id': row['data']['binding']['generated'][object_id]['path'],
                       'details': {'binding_sha256': row['data']['binding_sha256'], 'artifact_id': row['artifact_id']},
                       'assertion_class': 'historical_local_adoption'} for row in adoptions['adoptions']]
    return {**raw_scope, 'object_id': object_id, 'snapshot_id': value.get('snapshot_id'),
            'raw_observed_assignments': raw.get('assignments'),
            'relationships': value.get('relationships', []) + adoption_edges + [edge for row in lineage['runs'] for edge in row['data'].get('relationships', [])],
            'source': value.get('source'), 'workflows': lineage, 'coverage': value.get('coverage'),
            'adoption_lineage': adoptions,
            'assignments': body.get('assignments'),
            'ownership': value['ownership'], 'ownership_evidence': value['ownership_evidence'],
            'selected_repository': value['selected_repository']}


def command(args):
    name = args.workbench_command
    from .host_capabilities import require_profile
    from . import workbench_views
    if name == 'field-semantics':
        return workbench_views.command(args)
    require_profile('workbench_store')
    if name.startswith('observer-') or name.startswith('schedule-'):
        require_profile('graph_observer')
    from . import workbench_queue
    if name in workbench_queue.COMMANDS:
        return workbench_queue.command(args)
    from . import observation_jobs
    if name in observation_jobs.COMMANDS:
        return observation_jobs.command(args)
    if name in workbench_views.COMMANDS:
        return workbench_views.command(args)
    if name == 'workspace':
        from .workbench_tui import run_workspace
        return run_workspace(args.root, service_root=args.service_root, theme=args.theme,
                             no_color=args.no_color, reduced_motion=args.reduced_motion)
    if name == 'init':
        from .workbench_store import WorkbenchStore
        store = WorkbenchStore.create(args.root, args.tenant)
        return {'status': 'created', 'evidence_class': 'synthetic', 'overview': store.overview(),
                'external_execution': False}
    if name == 'backup':
        return dict(_store(args.root).backup(args.output),
                    integrity_limit='Retain and compare the backup receipt independently; a self-supplied digest does not authenticate provenance.')
    if name == 'migrate': return _store(args.root).migrate(args.backup)
    if name in ('adoption-preview', 'adopt'):
        from . import workbench_adoption
        store = _store(args.root)
        if name == 'adoption-preview': return workbench_adoption.preview(store, args.session)
        return workbench_adoption.adopt(store, args.session, args.output)
    if name in ('schedule-create', 'schedule-run', 'schedule-status'):
        from . import workbench_scheduler as scheduler
        if name == 'schedule-create': return scheduler.create_schedule(_store(args.root), args.service_root, args.interval_seconds, args.output)
        if name == 'schedule-run': return scheduler.run_schedule(args.job, args.max_runs, args.max_duration_seconds)
        return scheduler.schedule_status(args.job)
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
        if name == 'execute': return maintenance.execute(args.operation, approve_digest=args.approve_digest, fault=args.fault,
                                                          visibility_delay_reads=args.visibility_delay_reads)
        if name == 'reconcile': return maintenance.reconcile(args.operation)
        return maintenance.propose(args.root, args.service_root, args.object, args.desired, args.output, context_path=args.context)
    if name == 'terminal': return run_terminal(args.root, service_root=args.service_root)
    store = _store(args.root)
    if name == 'import-capture': return store.import_capture(args.capture)
    if name == 'collection-history': return {'collections': store.collection_history(args.object, limit=args.limit, offset=args.offset), 'limit': args.limit, 'offset': args.offset}
    if name == 'collection': return store.collection_detail(args.run)
    if name == 'device-evidence-import':
        from .workbench_health import import_device_evidence
        return import_device_evidence(store, args.input)
    if name == 'workflow-import':
        from .workbench_health import import_workflow_run
        return import_workflow_run(store, args.input)
    if name == 'workflows':
        from .workbench_health import workflow_lineage
        return workflow_lineage(store, args.object)
    if name == 'reference-import':
        from .workbench_provenance import reference_import
        return reference_import(store, args.input, args.sha256, args.revision, args.source_url, args.license, args.assertion_class)
    if name == 'reference-compare':
        from .workbench_provenance import compare_reference
        return compare_reference(store, args.object, args.reference, args.company)
    if name == 'references': return {'references': store.artifacts(kind='source_reference', limit=args.limit, offset=args.offset)}
    if name == 'collect':
        from .modeled_service import ModeledService
        return store.collect(ModeledService(args.service_root), observed_at=args.observed_at, fault=args.fault,
                             deployment=load_json(args.deployment) if args.deployment else None,
                             source=_source_metadata(args))
    if name == 'overview': return store.overview(limit=args.limit, offset=args.offset)
    if name == 'health': return _health(store, args.object, limit=args.limit, offset=args.offset)
    if name == 'queue': return _queue(store, limit=args.limit, offset=args.offset)
    if name == 'dictionary': return _dictionary(store, args.query, object_id=args.object, limit=args.limit, offset=args.offset)
    if name == 'search': return _search(store, args.query, limit=args.limit, offset=args.offset)
    if name == 'inspect': return _inspection(store, args.object)
    if name == 'adoption-lineage':
        from .workbench_adoption import lineage
        return lineage(store, args.object)
    if name == 'lineage':
        from .workbench_provenance import repository_lineage
        return repository_lineage(store, args.object, args.pointer)
    if name in ('settings', 'relationships'): return _facet(store, args.object, name)
    if name == 'history': return {'object_id': args.object, 'history': store.history(args.object, limit=args.limit, offset=args.offset),
                                  'limit': args.limit, 'offset': args.offset}
    if name == 'history-recent': return store.recent_history_page(args.object, limit=args.limit, offset=args.offset)
    if name == 'compare': return store.compare(args.object, args.before, args.after)
    if name == 'operations': return {'operations': store.operations(object_id=args.object, limit=args.limit, offset=args.offset),
                                     'limit': args.limit, 'offset': args.offset}
    raise AppError('unknown_workbench_command', 'Unknown workbench command.')


HELP = {
    'navigation': ['overview [LIMIT [OFFSET]]', 'next', 'previous', 'search TEXT', 'search-page LIMIT OFFSET TEXT', 'select EXACT_OBJECT_ID', 'inspect', 'settings',
                   'relationships', 'lineage [JSON_POINTER]', 'adoption-lineage', 'dictionary [SETTING_ID_QUERY]', 'references', 'reference-compare REFERENCE_ID [COMPANY_JSON]',
                   'dictionary-page LIMIT OFFSET [SETTING_ID_QUERY]', 'workflows', 'history [LIMIT [OFFSET]]', 'history-recent [LIMIT [OFFSET]] (newest first, default 10)', 'compare BEFORE_SNAPSHOT AFTER_SNAPSHOT',
                   'health [LIMIT [OFFSET]]', 'queue [LIMIT [OFFSET]]', 'operations [LIMIT [OFFSET]]',
                   'views [OPERATION_DIR]', 'views-page LIMIT OFFSET [QUERY [OWNERSHIP [COVERAGE [HEALTH]]]] (- means no filter)',
                   'field-semantics', 'back', 'cancel', 'quit'],
    'maintenance': ['propose DESIRED_JSON OUTPUT_DIR [CONTEXT_JSON]', 'review OPERATION_DIR',
                    'execute OPERATION_DIR EXPLICIT_REVIEW_DIGEST [FAULT [VISIBILITY_DELAY_READS]]', 'reconcile OPERATION_DIR',
                    'restore-propose PREVIOUS_OPERATION_DIR NEW_OUTPUT_DIR (fresh review required)'],
    'adoption': ['adoption-preview COMPLETED_JOURNEY_JSON', 'adopt COMPLETED_JOURNEY_JSON NEW_HANDOFF_DIR (separate local maintenance model)'],
    'protected_service': ['service-link JOB_ROOT POLICY_PATH (link selected object to persistent four views)',
                          'service-review JOB_ROOT POLICY_PATH', 'service-status JOB_ROOT POLICY_PATH',
                          'service-attach JOB_ROOT POLICY_PATH (read-only; no dispatch or replay)',
                          'service-cancel JOB_ROOT POLICY_PATH (request only; inspect resulting state)',
                          'service-recover JOB_ROOT POLICY_PATH (explicit recovery; no mutation replay)'],
    'collection': ['collect (requires --service-root; also runs as a separate headless command)',
                   'import-capture CAPTURE_DIRECTORY', 'collection-history [LIMIT [OFFSET]]', 'collection RUN_ID',
                   'migrate NEW_BACKUP_PATH', 'schedule-create NEW_JOB_DIR INTERVAL_SECONDS (requires --service-root)',
                   'schedule-run JOB_DIR MAX_RUNS MAX_DURATION_SECONDS', 'schedule-status JOB_DIR'],
    'evidence': ['device-evidence-import ENVELOPE_JSON', 'workflow-import ENVELOPE_JSON',
                 'reference-import JSON SHA256 FULL_REVISION HTTPS_SOURCE_URL LICENSE_ID [ASSERTION_CLASS]'],
    'limits': 'Terminal estate views default to 10 observations per page; totals and continuation are explicit. Imported captures and reports remain unverified local evidence. Local maintenance is synthetic. Protected service observation grants no execution or rollout authority.',
}


def _render(value, output_fn):
    # Match the existing CLI's safe JSON presentation. Escaping all non-ASCII
    # also neutralizes bidi/C1/OSC controls without destroying stored evidence.
    width = max(16, min(160, shutil.get_terminal_size(fallback=(80, 24)).columns))
    for line in json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False).splitlines():
        for part in textwrap.wrap(line, width=width, replace_whitespace=False, drop_whitespace=False) or ['']:
            output_fn(part)


def run_terminal(root, *, service_root=None, input_fn=None, output_fn=None, result_fn=None, _store_capability=None):
    """Retain interrupt intent even when a native callback translates its exception.

    SQLite can turn KeyboardInterrupt from a progress callback into OperationalError.
    A pending signal must therefore be checked outside that callback before rendering
    a recoverable error or accepting another command. Native execution may install
    its own cleanup handler temporarily; the existing handler is always delegated to
    and restored. No signal handler is installed from non-main threads.
    """
    pending = False
    installed = threading.current_thread() is threading.main_thread()
    previous = signal.getsignal(signal.SIGINT) if installed else None

    def receive_interrupt(signum, frame):
        nonlocal pending
        pending = True
        if callable(previous):
            previous(signum, frame)
        elif previous != signal.SIG_IGN:
            raise KeyboardInterrupt

    def check_interrupt():
        if pending:
            raise KeyboardInterrupt

    if installed:
        signal.signal(signal.SIGINT, receive_interrupt)
    try:
        return _run_terminal(root, service_root=service_root, input_fn=input_fn,
                             output_fn=output_fn, result_fn=result_fn, interrupt_check=check_interrupt, _store_capability=_store_capability)
    except KeyboardInterrupt:
        value = {'status': 'interrupted', 'recovery': 'Inspect persisted operations and reconcile before retrying any uncertain execution.'}
        if result_fn is None:
            _render(value, print if output_fn is None else output_fn)
        else:
            result_fn(value)
        return {'status': 'interrupted', 'evidence_class': 'local_interface_result'}
    finally:
        if installed:
            signal.signal(signal.SIGINT, previous)


def _run_terminal(root, *, service_root=None, input_fn=None, output_fn=None, result_fn=None, interrupt_check=lambda: None, _store_capability=None):
    """Accessible line terminal; no shell invocation, animation, or hidden approval.

    The store, not the process, owns history. Closing this interface never stops
    another process's collector. EOF and back/cancel cannot dispatch mutation.
    """
    input_fn = input if input_fn is None else input_fn
    output_fn = print if output_fn is None else output_fn
    # A presentation adapter receives the same typed results and returns ordinary
    # command input. It never owns another approval or execution implementation.
    def present(value):
        interrupt_check()
        if result_fn is None:
            _render(value, output_fn)
        else:
            result_fn(value)
    if _store_capability is None:
        store = _store(root)
    else:
        from .windows_workspace_binding import admit_store
        store = admit_store(root, _store_capability)
    selected = None
    page = {'kind': 'overview', 'limit': 10, 'offset': 0, 'query': ''}
    def show_page(specification=None):
        target = page if specification is None else specification
        if target['kind'] == 'history-recent':
            return store.recent_history_page(target['object_id'], limit=target['limit'], offset=target['offset'])
        if target['kind'] == 'views':
            from .workbench_views import views
            return views(store, limit=target['limit'], offset=target['offset'], query=target['query'],
                         ownership_filter=target.get('ownership'), coverage_filter=target.get('coverage'),
                         health_filter=target.get('health'))
        if target['kind'] == 'search': return _search(store, target['query'], limit=target['limit'], offset=target['offset'])
        if target['kind'] == 'dictionary': return _dictionary(store, target['query'], limit=target['limit'], offset=target['offset'])
        if target['kind'] == 'health': return _health(store, limit=target['limit'], offset=target['offset'])
        if target['kind'] == 'queue': return _queue(store, limit=target['limit'], offset=target['offset'])
        return store.overview(limit=target['limit'], offset=target['offset'])
    def set_page(kind, limit=10, offset=0, query=''):
        candidate = {'kind': kind, 'limit': limit, 'offset': offset, 'query': query}
        result = show_page(candidate)
        page.update(candidate)
        return result
    initial_overview = show_page()
    present({'title': 'Intune Workbench', 'evidence_class': initial_overview.get('evidence_class', 'unknown'), 'commands': HELP})
    present(initial_overview)
    while True:
        try:
            interrupt_check()
            line = input_fn('workbench> ')
            interrupt_check()
            if len(line) > 16384: raise ValueError('command too long')
            parts = shlex.split(line)
            if not parts: continue
            name, values = parts[0].lower(), parts[1:]
            if _store_capability is not None:
                from .windows_workspace_binding import require_command
                require_command(name)
            if name in ('quit', 'exit') and not values:
                return {'status': 'closed', 'evidence_class': 'local_interface_result', 'history_persisted': True}
            if name == 'help' and not values: result = HELP
            elif name == 'views' and len(values) <= 1:
                from .workbench_views import views
                if values and selected is None:
                    raise AppError('selection_required', 'Select an exact immutable object ID first.')
                result = views(store, selected, operation=values[0] if values else None, limit=10)
            elif name == 'service-link' and len(values) == 2:
                if selected is None:
                    raise AppError('selection_required', 'Select an exact immutable object ID first.')
                from .workbench_service_views import link
                result = link(store, selected, values[0], values[1])
            elif name == 'views-page' and 2 <= len(values) <= 6:
                filters = [None if value == '-' else value for value in values[2:]]
                filters += [None] * (4 - len(filters))
                candidate = {'kind': 'views', 'limit': int(values[0]), 'offset': int(values[1]),
                             'query': filters[0] or '', 'ownership': filters[1],
                             'coverage': filters[2], 'health': filters[3]}
                result = show_page(candidate)
                page.clear()
                page.update(candidate)
                selected = None
            elif name == 'field-semantics' and not values:
                from .workbench_semantics import contract
                result = contract()
            elif name in ('back', 'cancel') and not values:
                selected = None
                if page['kind'] == 'history-recent':
                    page.clear(); page.update(kind='overview', limit=10, offset=0, query='')
                result = {'status': 'selection_cleared', 'mutation_dispatched': False}
            elif name == 'overview' and len(values) <= 2:
                result = set_page('overview', int(values[0]) if values else 10, int(values[1]) if len(values) == 2 else 0)
            elif name in ('next', 'previous') and not values:
                if name == 'previous': page['offset'] = max(0, page['offset'] - page['limit'])
                else:
                    current = show_page()
                    pagination = current.get('pagination', current.get('observation_scope', {}).get('pagination', {}))
                    if pagination.get('next_offset') is None:
                        present({'status': 'end_of_observation_pages', 'pagination': pagination})
                        continue
                    page['offset'] = pagination['next_offset']
                selected = page.get('object_id') if page['kind'] == 'history-recent' else None
                result = show_page()
            elif name == 'search': result = set_page('search', query=' '.join(values))
            elif name == 'search-page' and len(values) >= 3:
                result = set_page('search', int(values[0]), int(values[1]), ' '.join(values[2:]))
            elif name == 'select' and len(values) == 1:
                result = _inspection(store, values[0])
                selected = values[0]
            elif name == 'health' and len(values) <= 2:
                result = (_health(store, selected) if selected is not None and not values else
                          set_page('health', int(values[0]) if values else 10, int(values[1]) if len(values) == 2 else 0))
            elif name == 'queue' and len(values) <= 2:
                result = set_page('queue', int(values[0]) if values else 10, int(values[1]) if len(values) == 2 else 0)
            elif name == 'dictionary':
                result = (_dictionary(store, ' '.join(values), object_id=selected) if selected is not None else
                          set_page('dictionary', query=' '.join(values)))
            elif name == 'dictionary-page' and len(values) >= 2:
                result = set_page('dictionary', int(values[0]), int(values[1]), ' '.join(values[2:]))
            elif name == 'references' and not values: result = {'references': store.artifacts(kind='source_reference')}
            elif name == 'collection-history' and len(values) <= 2:
                result = {'collections': store.collection_history(selected, limit=int(values[0]) if values else None,
                          offset=int(values[1]) if len(values) == 2 else 0)}
            elif name == 'collection' and len(values) == 1: result = store.collection_detail(int(values[0]))
            elif name == 'import-capture' and len(values) == 1: result = store.import_capture(values[0])
            elif name == 'migrate' and len(values) == 1: result = store.migrate(values[0])
            elif name == 'adoption-preview' and len(values) == 1:
                from .workbench_adoption import preview
                result = preview(store, values[0])
            elif name == 'adopt' and len(values) == 2:
                from .workbench_adoption import adopt
                result = adopt(store, *values)
                service_root = result['service_root']
                selected = None
            elif name == 'device-evidence-import' and len(values) == 1:
                from .workbench_health import import_device_evidence
                result = import_device_evidence(store, values[0])
            elif name == 'workflow-import' and len(values) == 1:
                from .workbench_health import import_workflow_run
                result = import_workflow_run(store, values[0])
            elif name == 'reference-import' and len(values) in (5, 6):
                from .workbench_provenance import reference_import
                result = reference_import(store, *values)
            elif name in ('schedule-create', 'schedule-run', 'schedule-status'):
                from . import workbench_scheduler as scheduler
                if name == 'schedule-create' and len(values) == 2:
                    if service_root is None: raise AppError('service_required', 'Supply --service-root for synthetic collection.')
                    result = scheduler.create_schedule(store, service_root, float(values[1]), values[0])
                elif name == 'schedule-run' and len(values) == 3:
                    result = scheduler.run_schedule(values[0], int(values[1]), float(values[2]))
                elif name == 'schedule-status' and len(values) == 1: result = scheduler.schedule_status(values[0])
                else: raise ValueError('invalid command arguments')
            elif name == 'operations' and len(values) <= 2:
                result = {'operations': store.operations(object_id=selected, limit=int(values[0]) if values else None,
                          offset=int(values[1]) if len(values) == 2 else 0)}
            elif name in ('inspect', 'settings', 'relationships', 'lineage', 'adoption-lineage', 'history', 'history-recent', 'compare', 'propose', 'workflows', 'reference-compare'):
                if selected is None: raise AppError('selection_required', 'Select an exact immutable object ID first.')
                if name == 'inspect' and not values: result = _inspection(store, selected)
                elif name in ('settings', 'relationships') and not values: result = _facet(store, selected, name)
                elif name == 'adoption-lineage' and not values:
                    from .workbench_adoption import lineage
                    result = lineage(store, selected)
                elif name == 'lineage' and len(values) <= 1:
                    from .workbench_provenance import repository_lineage
                    result = repository_lineage(store, selected, values[0] if values else None)
                elif name == 'workflows' and not values:
                    from .workbench_health import workflow_lineage
                    result = workflow_lineage(store, selected)
                elif name == 'reference-compare' and len(values) in (1, 2):
                    from .workbench_provenance import compare_reference
                    result = compare_reference(store, selected, *values)
                elif name == 'history' and len(values) <= 2:
                    result = {'object_id': selected, 'history': store.history(selected,
                              limit=int(values[0]) if values else None, offset=int(values[1]) if len(values) == 2 else 0)}
                elif name == 'history-recent' and len(values) <= 2:
                    candidate = {'kind':'history-recent','object_id':selected,
                                 'limit':int(values[0]) if values else 10,
                                 'offset':int(values[1]) if len(values)==2 else 0,'query':''}
                    result = show_page(candidate)
                    page.clear(); page.update(candidate)
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
                elif name == 'execute' and len(values) in (2, 3, 4):
                    result = maintenance.execute(values[0], approve_digest=values[1], fault=values[2] if len(values) >= 3 else None,
                                                 visibility_delay_reads=int(values[3]) if len(values) == 4 else 0)
                else: raise ValueError('invalid command arguments')
            elif name in ('service-review', 'service-status', 'service-attach', 'service-cancel', 'service-recover') and len(values) == 2:
                from .service_cli import invoke
                result = invoke(name.removeprefix('service-'), *values, tenant_id=store.tenant_id, object_id=selected)
            elif name == 'collect' and not values:
                if service_root is None: raise AppError('service_required', 'Supply --service-root for synthetic collection.')
                from .modeled_service import ModeledService
                result = store.collect(ModeledService(service_root))
            else: raise ValueError('unknown command')
            present(result)
        except EOFError:
            return {'status': 'closed', 'evidence_class': 'local_interface_result', 'history_persisted': True}
        except KeyboardInterrupt:
            present({'status': 'interrupted', 'recovery': 'Inspect persisted operations and reconcile before retrying any uncertain execution.'})
            return {'status': 'interrupted', 'evidence_class': 'local_interface_result'}
        except AppError as error:
            present({'status': 'error', 'error': {'code': error.code, 'message': error.message}})
        except (ValueError, TypeError, KeyError, OSError):
            present({'status': 'error', 'error': {'code': 'invalid_workbench_request',
                     'message': 'Command or local input is invalid. Enter help for exact syntax.'}})
