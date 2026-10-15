"""Persistent local workbench presentation over the existing Intune engine.

Local maintenance execution is explicitly synthetic; protected service routes
prepare or observe the separate host contract. Neither this terminal nor its
approval digest confers Graph, provider, or organizational authority.
All imported strings are rendered as ASCII JSON; original values stay in the
observation store. The line terminal also works over redirected stdin.
"""
from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil
import signal
import threading

from .companion_page import COMPANION_WRITE
from .io import AppError, load_json
from .workbench_diagnostics import CLOCK_HOLD_CAUSES, CLOCK_HOLD_REASONS, CLOCK_HOLD_WORDS, clock_hold, with_clock_times


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
    workspace.add_argument('--theme', choices=('dark', 'light', 'blueprint', 'high-contrast'), default='dark')
    workspace.add_argument('--ascii', action='store_true', help='Draw ASCII rules even on a UTF-8 terminal')
    workspace.add_argument('--no-color', action='store_true')
    workspace.add_argument('--reduced-motion', action='store_true', default=True,
                           help='Keep all information without animation; also the default')
    companion = sub.add_parser('companion', help='The read-only isometric companion page for one policy: write it to a file or serve it on this '
                                                 'machine only; never launches a browser')
    companion.add_argument('--root', required=True)
    companion.add_argument('--object', required=True, help='Exact immutable object ID, never a display name')
    way = companion.add_mutually_exclusive_group(required=True)
    way.add_argument('--out', help='File to write; it shows one snapshot and does not update itself')
    way.add_argument('--serve', action='store_true',
                     help='Serve the page and its current snapshot on 127.0.0.1 only, under a secret path; stops on Ctrl+C or when idle')
    companion.add_argument('--idle-seconds', type=int, default=1800, help='With --serve: stop after this long without a page request')
    overview = sub.add_parser('estate-overview', help='Groups, filters, scope tags and settings the observed policies share, and what was not established (read-only)')
    overview.add_argument('--root', required=True); overview.add_argument('--limit', type=int, default=200)
    sub.add_parser('families', help='Every policy, application and script family with its support disposition (read-only)')
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
    for name in ('overview', 'health', 'diagnostics', 'queue', 'dictionary', 'references', 'workflows', 'collection-history', 'collection', 'search', 'inspect', 'settings', 'relationships', 'lineage', 'adoption-lineage', 'history', 'history-recent', 'compare', 'operations', 'terminal'):
        item = sub.add_parser(name)
        item.add_argument('--root', required=True)
        if name in ('inspect', 'settings', 'relationships', 'lineage', 'adoption-lineage', 'history', 'history-recent', 'compare', 'workflows', 'diagnostics'):
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
    for name in ('review', 'execute', 'reconcile', 'delivery'):
        item = sub.add_parser(name, **({'help': 'Read-only delivery stages of one operation'} if name == 'delivery' else {}))
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


def _clock_hold_facts(observed):
    """The clock hold an observation carries, as the queue's evidence says it; {} when it carries none."""
    reasons = [reason for reason in observed.get('freshness_reasons') or [] if reason in CLOCK_HOLD_REASONS]
    if not reasons or not isinstance(observed.get('freshness_clock'), dict):
        return {}
    return {'freshness_reasons': reasons, 'freshness_clock': dict(observed['freshness_clock'])}


def _queue(store, *, limit=None, offset=0):
    """Evidence gaps are review findings, never inferred authorization to fix."""
    from .workbench_health import device_health
    from .workbench_views import _ownership_result
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
    # Ownership freshness is judged on the reading every other surface makes (effective time, clock reasons), not on
    # the bare wall; reading it records nothing.
    ownership_now, ownership_effective, ownership_hold = store._clock_reading(bind=False)
    findings = []
    held = {}  # the clock hold is the store's, not one policy's: it is read once, from the first observation that is not fresh
    for row in overview.get('objects', []) + overview.get('pending_observations', []):
        reasons = []
        hold = {}
        if row.get('freshness') != 'fresh':
            reasons.append(('observation_stale', 'A current complete observation is required before assessing changes.'))
            if not row.get('pending_observation'):
                # The overview row carries the hold it was judged on, the same reading the Inspector makes; only a row
                # that is stale for another reason falls back to reading the observation.
                hold = _clock_hold_facts(row)
                if not hold:
                    if 'read' not in held:
                        held.update(read=True, value=_clock_hold_facts(_read_observation(store, row['object_id'])))
                    hold = held['value']
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
        writer = _ownership_result(ownership_index, row['object_id'], selected_scope, ownership_now, claims,
                                   ownership_effective, ownership_hold)
        writer_status = writer['status']
        if writer_status == 'conflicting_claims':
            reasons.append(('ownership_conflicting_claims', 'Multiple declared state addresses claim the same object or assignment writer; resolve the conflict before preparing execution.'))
        elif writer_status == 'no_ownership_found_in_declared_scope':
            reasons.append(('ownership_unclaimed', 'No writer was found in the complete fresh declared scopes; this does not prove absence of writers outside those scopes.'))
        elif writer_status == 'owned_elsewhere':
            reasons.append(('ownership_elsewhere', 'The declared writer belongs to another selected stack/component/backend scope; coordinate its owner before proposing a change.'))
        elif writer_status == 'unknown':
            if ownership_index is not None and not writer['fresh']:
                held = clock_hold(ownership_hold)
                if held:
                    # Collecting again is judged against the same recorded time, so it is not the way out of a clock hold.
                    reasons.append(('ownership_stale', 'The age of the declared ownership evidence cannot be established '
                                    '(%s); collecting again does not clear this: %s.' % (OWNERSHIP_HOLD_CAUSE[held],
                                                                                   CLOCK_HOLD_RECOVERY[held])))
                else:
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
                        'endpoint_effectiveness_established': False}, **hold},
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


def _attention(store, object_id):
    """What the diagnostics records say needs attention, for the Inspector; read-only. An unreadable result is stated."""
    from .workbench_diagnostics import diagnostics
    try:
        value = diagnostics(store, object_id)
    except AppError as error:
        return {'status': 'unavailable', 'error_code': error.code, 'signals': [], 'checked': {}}
    partial = any(state in ('partly_checked', 'unavailable') for state in value['checked'].values())
    return {'status': 'attention' if value['signals'] else 'partly_checked' if partial else 'clear',
            'signals': [{**{key: signal[key] for key in ('area', 'code', 'observed', 'next_step')},
                         'evidence': signal.get('evidence') if isinstance(signal.get('evidence'), dict) else {}}
                        for signal in value['signals']],
            'checked': value['checked'], 'newest_operation': value.get('newest_operation')}


def _states(observation, intent, attention, eligibility):
    """The observation, the repository intent and the newest operation as three states, each from its own records.

    The observation's freshness is its age; the proposal's own check against the service is reported beside it, not
    folded into it. The intent's state is diagnostics' repository check. The operation's is its journal.
    """
    checked = attention.get('checked') if isinstance(attention.get('checked'), dict) else {}
    signals = {signal.get('code'): signal for signal in attention.get('signals') or [] if isinstance(signal, dict)}
    observed = {key: observation.get(key) for key in ('evidence_class', 'run_id', 'observed_at', 'coverage', 'freshness')}
    observed['freshness_reasons'] = list(observation.get('freshness_reasons') or [])
    # The reading of this host's clock when the age was judged, so a row can name it beside the stamp.
    observed['freshness_checked_at'] = observation.get('freshness_checked_at')
    if isinstance(observation.get('freshness_clock'), dict):
        observed['freshness_clock'] = dict(observation['freshness_clock'])
    observed['eligibility'] = eligibility if isinstance(eligibility, dict) and eligibility.get('reason') else None
    if intent is None:
        intended = {'status': 'none'}
    else:
        data, area = intent['data'], checked.get('repository')
        codes = [code for code in ('repository_stale', 'repository_consumer_mismatch', 'repository_unavailable') if code in signals]
        status = {'repository_stale': 'changed', 'repository_consumer_mismatch': 'consumer_changed',
                  'repository_unavailable': 'unreadable'}.get(codes[0]) if codes else (
            'current' if area == 'clear' else 'unreadable' if area == 'unavailable' else 'not_checked')
        intended = {'status': status, 'artifact_id': intent['artifact_id'], 'scope': data.get('scope'),
                    'source_revision': data.get('source_revision'),
                    'revision_content_verified': data.get('revision_content_verified'),
                    'recorded_at': intent.get('recorded_at'), 'reason': signals[codes[0]].get('observed') if codes else None}
    operation = attention.get('newest_operation')
    return {'observation': observed, 'intent': intended, 'operation': operation if isinstance(operation, dict) else None}


# The Inspector names at most this many next steps and says how many more diagnostics holds.
NEXT_STEPS = 3


def _next_actions(value, attention, service_available):
    """What the engineer can do next: the recorded next steps first, otherwise the change route that exists.

    Every step names a real command; preparing a change always ends in a review that needs the exact digest.
    """
    steps = [{'source': signal['code'], 'step': signal['next_step']} for signal in attention.get('signals', [])]
    if attention.get('status') in ('unavailable', 'partly_checked'):
        # Whether anything needs attention is not established, so no change is offered yet.
        steps.insert(0, {'source': 'diagnostics_' + attention['status'], 'step': 'i shows what could not be read and why; '
                         'until it is read, whether anything needs attention is not established.'})
    elif not steps:
        needs = '' if service_available else ' (needs --service-root: a modeled service)'
        prepared = ', with the digest that review shows and execute requires%s.' % needs
        if value.get('selected_repository'):
            steps.append({'source': 'repository_intent', 'step': 'Prepare a proposal from the recorded intent' + prepared
                          + ' Command:\n  propose-from-intent NEW_OPERATION_DIR'})
        else:
            steps.append({'source': 'no_repository_intent', 'step': 'To see how to record where this policy is maintained, run:\n'
                          '  repository-entry REPOSITORY\nTo Prepare a local proposal from a desired file' + prepared + ' Command:\n'
                          '  propose DESIRED_JSON NEW_OPERATION_DIR'})
    if len(steps) > NEXT_STEPS:
        more = len(steps) - NEXT_STEPS
        steps = steps[:NEXT_STEPS] + [{'source': 'more', 'step': '%d more %s under i (diagnostics).' % (
            more, 'step' if more == 1 else 'steps')}]
    return steps


# What each guided action does, said once and shown wherever it is offered. Reading the service still records
# local evidence, so "reads" never stands for "changes nothing".
ACTION_EFFECTS = {
    'reconcile': 'Reads the modeled service on its own, then records a reconciliation receipt and a journal entry for '
                 'this operation and records the operation in this store. It never replays the write.',
    'collect': 'Reads the configured modeled service and records a new collection run in the store, including a denied '
               'or partial result.',
    'repository-refresh': 'Shows the source difference first (Repository surface) and binds the command to it. Then reads '
                          "the repository's current files and records them as a new intent, refusing if they changed since "
                          'the difference was shown; the earlier intent is kept. It is not a Git commit, an approval or an '
                          'apply.',
    'propose-from-intent': 'Checks the recorded intent, then writes two input files beside a new operation directory '
                           'before checking the observation; if that check refuses, the two files stay. Otherwise it '
                           'writes the directory and records the operation in this store.',
    'propose': 'Checks the desired file and the observation, then writes a new operation directory and records the '
               'operation in this store.',
    'repository-entry': 'Reads the repository and lists its policies with the exact command to record each. It writes '
                        'nothing.',
    'diagnostics': 'Shows the diagnostics records for this policy, including what could not be read and why. It '
                   'records nothing.',
    'deployment-record': 'Rechecks the operation, its engine receipt, its one verified readback and the context bytes '
                         'its plan bound against the cited repository intent, then records a deployment receipt in '
                         "this store: a verified local modeled baseline for that intent, not platform qualified. It "
                         'sends nothing to the service.',
    'companion': 'Reads this policy and its relationships and writes only the file you name: an isometric page that shows '
                 'one snapshot and does not update itself. It records nothing in the store, can approve or run nothing and '
                 'never opens a browser; the notice names the path. From a shell the same command is ' + COMPANION_WRITE +
                 '; with --serve instead of --out FILE it serves the page on this machine only, and the product prints its '
                 'secret address (anyone on the same machine who has it can read the page).',
}


# One essential effect per action, shown for every action in the list; the full effects above are for the focused one.
ACTION_SUMMARY = {
    'reconcile': "Checks the operation's outcome and records the result; it never replays the change.",
    'collect': 'Reads the modeled service and records a collection run; it changes no policy.',
    'repository-refresh': 'Shows the changes first, then records them as a new intent: no Git commit, approval or apply.',
    'propose-from-intent': 'Creates a local proposal for review; nothing is approved or sent.',
    'propose': 'Creates a local proposal for review; nothing is approved or sent.',
    # The same sentence as its effect, so the focused action prints it once. "Writes nothing" is the claim the code proves
    # (the survey reads the repository and the store and writes neither), and it covers "records nothing".
    'repository-entry': ACTION_EFFECTS['repository-entry'],
    'diagnostics': 'Shows what diagnostics recorded, including what it could not read; it records nothing.',
    'deployment-record': 'Records a deployment receipt in this store; it sends nothing.',
    'companion': 'Writes one read-only page for this policy to a file you name; it records nothing and opens no browser.',
}


def _collect_cures(facts, service_root):
    """Whether collecting now from this session's service makes a new observation current, from the store's own
    ordering fact (next_collection_replaces); the one judgement the band, the actions and the refusals read."""
    kind = facts.get('next_collection_replaces') if isinstance(facts, dict) else None
    if service_root is None or kind not in ('same_service', 'any_collection'):
        return False
    if kind == 'any_collection':
        return True
    return str(Path(str(facts.get('ordering_service_root'))).absolute()) == str(Path(str(service_root)).absolute())


def _with_collect_cures(attention, service_root):
    """A copy of the attention whose stale-observation signal says whether collecting now cures it."""
    signals = []
    for signal in attention.get('signals') or []:
        if isinstance(signal, dict) and signal.get('code') == 'observation_stale':
            evidence = dict(signal.get('evidence') or {})
            evidence['collect_cures'] = _collect_cures(evidence, service_root)
            signal = dict(signal, evidence=evidence)
        signals.append(signal)
    return dict(attention, signals=signals)


def _stamped_ahead_only(reasons):
    """Whether staleness comes only from a stamp ahead of this host's clock, which collecting again cannot cure."""
    return isinstance(reasons, list) and bool(reasons) and set(reasons) == {'stamped_after_now'}


def _fresh_operation(store, object_id):
    """A new operation directory beside the store; neither it nor its sibling input files exist yet.

    The name carries a random part, never only a time or a policy name, so a stepping clock or a duplicate name cannot
    collide with earlier work; propose refuses an existing path in any case.
    """
    import uuid
    parent = Path(store.root).absolute().parent
    for _ in range(16):
        candidate = parent / ('operation-%s-%s' % (str(object_id)[:8], uuid.uuid4().hex[:12]))
        paths = (candidate, Path(str(candidate) + '.intent-desired.json'), Path(str(candidate) + '.intent-context.json'))
        if not any(path.exists() or path.is_symlink() for path in paths):
            return str(candidate)
    return None


def _refusal(code):
    """The engine's own code and message for a refusal it would raise."""
    from . import maintenance
    try:
        maintenance._fail(code)
    except AppError as error:
        return {'code': error.code, 'message': error.message}


# Areas that must be read completely before a change is offered; device evidence is reported apart.
REQUIRED_AREAS = ('collection', 'freshness', 'operations', 'repository')
# Signals that offer reconcile, in the band's order.
RECONCILE_CODES = ('operation_outcome_unknown', 'operation_diverged', 'operation_record_disagrees')
_UNREAD = object()


def _attention_established(attention):
    """Whether diagnostics read every area a change depends on; findings in a partly read area do not count."""
    checked = attention.get('checked') if isinstance(attention.get('checked'), dict) else {}
    return (attention.get('status') not in ('unavailable', 'partly_checked')
            and not any(checked.get(area) in ('unavailable', 'partly_checked') for area in REQUIRED_AREAS))


def _eligibility(store, object_id, service_root, observation=None):
    """The observation check a proposal makes: None when it passes or no service is configured.

    Given the observation a screen already shows, it judges that one, so the screen never disagrees with itself.
    """
    from . import maintenance
    if service_root is None:
        return None
    try:
        problem = maintenance.proposal_eligibility(store.root, service_root, object_id, observation=observation)
    except AppError as error:
        return {'code': error.code, 'reason': None, 'message': error.message}
    if problem and problem.get('reason') == 'not_fresh' and clock_hold(problem.get('freshness_reasons')):
        # The hold's times belong to the observation that was judged; the engine's check does not carry them.
        shown = observation if isinstance(observation, dict) else _read_observation(store, object_id)
        if isinstance(shown.get('freshness_clock'), dict):
            problem = dict(problem, freshness_clock=dict(shown['freshness_clock']))
    return problem


def _read_observation(store, object_id):
    """The observation as the store reports it now, or {} when it cannot be read."""
    try:
        return store.inspect(object_id)
    except AppError:
        return {}


def _intent_blocker(attention, intent):
    """The first check on the recorded repository intent that a proposal from it would fail; None when all pass."""
    import copy
    from . import maintenance
    from .workbench_repository import _usable_intent, capability_problems
    try:
        _usable_intent(intent, code_prefix='workbench')
    except AppError as error:
        # One code covers several causes; diagnostics records which one, with the changed paths.
        found = {signal.get('code'): signal for signal in attention.get('signals') or [] if isinstance(signal, dict)}
        for code, reason in REPOSITORY_REASONS:
            if found.get(code, {}).get('observed'):
                return {'code': error.code, 'reason': reason, 'message': str(found[code]['observed']).rstrip('.')}
        return {'code': error.code, 'message': error.message}
    # The checks propose_from_intent and propose make on the desired body, in their order.
    if intent['data'].get('consumer', {}).get('status') == 'verified' and capability_problems(intent['data']['desired']):
        from .workbench_repository import capability_explanation
        return {'code': 'workbench_desired_capability',
                'message': '%s The reference component cannot propose it.' % capability_explanation(intent['data']['desired'])}
    try:
        maintenance._desired(copy.deepcopy(intent['data']['desired']))
    except AppError as error:
        return {'code': error.code, 'message': error.message}
    return None


def _observation_blocker(problem):
    """The proposal's own observation check as a blocker; None when it passes."""
    if problem is None:
        return None
    if not problem.get('reason'):
        return {'code': problem['code'], 'message': problem.get('message') or _refusal(problem['code'])['message']}
    blocker = {'code': problem['code'], 'reason': problem['reason'], 'message': _reason_words(problem)}
    if problem['reason'] == 'not_fresh':
        # The compact blocked line words an unknown age as unknown, so it needs the recorded reasons.
        blocker['freshness_reasons'] = list(problem.get('freshness_reasons') or [])
    hold = clock_hold(problem.get('freshness_reasons')) if problem['reason'] == 'not_fresh' else None
    if hold:
        blocker['clock_hold'] = hold  # the workspace words a clock hold by its recovery, not by the engine's code
    return blocker


def _proposal_blocker(store, object_id, attention, intent, service_root, eligibility=_UNREAD):
    """Why a proposal cannot be prepared now, from the same checks the proposal makes; None when nothing blocks it.

    Every reason that blocks it is listed: the first is the blocker, the others follow under "also". A clock hold
    comes first, because it blocks every proposal and nothing in the workbench clears it.
    """
    if service_root is None:
        return {'code': 'service_required', 'message': 'needs --service-root (a modeled service) to prepare a proposal'}
    if not _attention_established(attention):
        # The Inspector's own rule: until diagnostics are read, whether anything needs attention is not established,
        # so no change is offered. The engine would still accept the command typed by hand.
        return {'code': 'workbench_attention_not_established',
                'message': 'not offered until diagnostics are read: whether anything needs attention is not established'}
    repository = _intent_blocker(attention, intent) if intent is not None else None
    problem = _eligibility(store, object_id, service_root) if eligibility is _UNREAD else eligibility
    observation = _observation_blocker(problem)
    ordered = [observation, repository] if (observation or {}).get('clock_hold') else [repository, observation]
    reasons = [item for item in ordered if item]
    if not reasons:
        return None
    return dict(reasons[0], also=reasons[1:]) if len(reasons) > 1 else reasons[0]


# The recorded repository signal that names which cause a repository refusal had.
REPOSITORY_REASONS = (('repository_stale', 'repository_changed'), ('repository_consumer_mismatch', 'consumer_changed'),
                      ('repository_unavailable', 'repository_unreadable'))
# Freshness reasons the store records, in plain words.
FRESHNESS_REASON_WORDS = {'later_collection_not_complete': 'a later collection did not complete',
                          'older_than_window': 'older than the freshness window',
                          'stamped_after_now': "stamped after this host's clock", **CLOCK_HOLD_WORDS}
# What a clock hold's refusal says is the way out; collecting again is never it.
# Why ownership evidence cannot be judged under a clock hold, in words.
OWNERSHIP_HOLD_CAUSE = {'clock_moved_backward': "this host's clock reads earlier than a time this workspace recorded",
                        'clock_floor_invalid': 'the time this workspace recorded cannot be read'}
CLOCK_HOLD_RECOVERY = {
    'clock_moved_backward': ('correct the host clock, or wait until it reads at or after the time this workspace '
                             'recorded, then restart the workbench'),
    'clock_floor_invalid': ("changes stay held until the workspace's recorded time can be read again (Diagnostics shows "
                            'where it is kept)')}
# Which observation check a proposal fails; collecting again answers all but another tenant.
RECOLLECT_REASONS = frozenset({'coverage_incomplete', 'last_attempt_incomplete', 'not_fresh', 'source_mismatch',
                               'service_changed', 'policy_changed'})


def _reason_words(problem):
    """The failed observation check in plain words, from the recorded facts; the code stays the engine's own."""
    reason = problem.get('reason')
    if reason == 'service_changed':
        return ('the source changed since this observation was captured (revision %s, now %s); collect again'
                % (problem.get('observed_revision'), problem.get('service_revision')))
    if reason == 'not_fresh':
        hold = clock_hold(problem.get('freshness_reasons'))
        if hold:
            # The clock is named first: nothing else clears while it holds, and a new collection is judged against the
            # same recorded time. The recorded reasons follow with the clock's own first.
            recorded = sorted(problem.get('freshness_reasons') or [], key=lambda item: item not in CLOCK_HOLD_REASONS)
            # The verdict is said once, in front of the causes; the times the clock and the record gave close it.
            return ("the newest observation's age cannot be established (%s); collecting again does not clear this: %s"
                    % ('; '.join(CLOCK_HOLD_CAUSES.get(item) or FRESHNESS_REASON_WORDS.get(item, item) for item in recorded),
                       with_clock_times(CLOCK_HOLD_RECOVERY[hold], problem.get('freshness_clock'))))
        reasons = [FRESHNESS_REASON_WORDS.get(item, item) for item in problem.get('freshness_reasons') or []]
        if 'stamped_after_now' in (problem.get('freshness_reasons') or []):
            # A stamp ahead of this host's clock leaves the age unknown: the record establishes only that, so the
            # sentence says "not known to be fresh", and gives the stamp reason once (as a clause, not also a bracket).
            others = [FRESHNESS_REASON_WORDS.get(item, item) for item in problem['freshness_reasons']
                      if item != 'stamped_after_now']
            head = 'the newest observation is not known to be fresh' + (' (%s)' % '; '.join(others) if others else '')
            if problem.get('next_collection_replaces') in ('same_service', 'any_collection'):
                # The store orders its own collections by run, and a capture stamped ahead of its import gives way.
                return ('%s: it is stamped after this host\'s clock, and a new collection%s becomes current; '
                        'collect again' % (head, ' from the service it came from'
                                           if problem.get('next_collection_replaces') == 'same_service' else ''))
            # An imported capture is ordered by its capture time, so a new collection would not replace this one.
            return ('%s: it is stamped after this host\'s clock, and collecting again now would not replace it'
                    % head)
        return 'the newest observation is not fresh (%s); collect again' % ('; '.join(reasons) or 'no reason recorded')
    if reason == 'last_attempt_incomplete':
        return 'the last collection attempt ended %s; collect again' % (problem.get('last_attempt_status') or 'without a status')
    words = {'tenant_mismatch': 'the newest observation is for another tenant',
             'coverage_incomplete': 'the newest observation does not cover the whole estate; collect again',
             'source_mismatch': 'the newest observation came from another service; collect again from this one',
             'policy_changed': 'this policy changed in the modeled service after this observation was collected; collect again'}
    return words.get(reason) or _refusal(problem['code'])['message']


def _record_offer(attention):
    """The newest operation and its cited intent when Delivery's deployment-record stage says it is available."""
    operation = attention.get('newest_operation') if isinstance(attention.get('newest_operation'), dict) else {}
    if operation.get('journal_status') not in ('succeeded_verified', 'reconciled') or not operation.get('operation_root'):
        return None
    from .workbench_delivery import deployment_stage
    try:
        stage = deployment_stage(operation['operation_root'])
    except AppError:
        return None  # Delivery itself names what is wrong with this operation's evidence.
    if stage.get('status') != 'available':
        return None
    return {'operation_id': operation.get('operation_id'), 'operation_root': operation['operation_root'],
            'intent_id': stage['intent_id']}


def _short(store, prefixes, operation_id):
    """An operation's unique prefix as the read model gives it; looked up when the read model has none."""
    operation_id = str(operation_id)
    known = prefixes.get(operation_id) if isinstance(prefixes, dict) else None
    return known or store.identity_prefixes(operations=[operation_id]).get(operation_id, operation_id[:8])


def _referenced_operations(found, states):
    """The operations the attention signals and the operation state name, for their unique prefixes."""
    named = {str(signal['evidence']['operation_id']) for signal in (found or {}).get('signals') or []
             if isinstance(signal, dict) and isinstance(signal.get('evidence'), dict)
             and signal['evidence'].get('operation_id')}
    operation = (states or {}).get('operation') if isinstance((states or {}).get('operation'), dict) else {}
    if operation.get('operation_id'):
        named.add(str(operation['operation_id']))
    return sorted(named)


def _actions(store, object_id, attention, intent, service_root, *, eligibility=_UNREAD, evidence_class=None,
             prefixes=None):
    """The guided actions for one policy, built from structured evidence, never parsed from prose.

    Each has the exact command where every argument is known (or the cursor where a missing input goes), the inputs
    still missing, what it does, whether it is available now and the context it is bound to. Submission rechecks
    everything; these only say earlier what the action itself would say.
    """
    binding = {'tenant_id': store.tenant_id, 'object_id': object_id}
    if evidence_class:
        binding['evidence_class'] = evidence_class
    signals = [signal for signal in attention.get('signals') or [] if isinstance(signal, dict)]
    found = {signal.get('code'): signal for signal in signals}
    actions = []

    def offer(kind, label, command, *, cursor=None, needs=(), blocked=None, extra=None, show_first=None):
        actions.append({'kind': kind, 'label': label, 'command': command, 'cursor': cursor, 'needs': list(needs),
                        'summary': ACTION_SUMMARY[kind], 'effects': ACTION_EFFECTS[kind], 'available': blocked is None,
                        'blocked': blocked,
                        'show_first': show_first, 'binding': dict(binding, **(extra or {}))})

    if not _attention_established(attention):
        offer('diagnostics', 'Show what diagnostics could not read', 'diagnostics')
    # One reconcile per operation, in the band's order, so the band and the list name the same operation first.
    seen = set()
    for signal in sorted((item for item in signals if item.get('code') in RECONCILE_CODES),
                         key=lambda item: RECONCILE_CODES.index(item['code'])):
        evidence = signal.get('evidence') if isinstance(signal.get('evidence'), dict) else {}
        operation_root = evidence.get('operation_root')
        if not operation_root or operation_root in seen:
            continue
        seen.add(operation_root)
        short = _short(store, prefixes, evidence.get('operation_id'))
        label = ('Reconcile operation %s again (reads only; a divergence needs a reviewed change)' % short
                 if signal['code'] == 'operation_diverged' else 'Reconcile operation %s' % short)
        offer('reconcile', label, 'reconcile ' + shlex.quote(str(operation_root)),
              extra={'operation_id': evidence.get('operation_id'), 'operation_root': operation_root})
    no_service = None if service_root else {'code': 'service_required', 'message': 'needs --service-root (a modeled '
                                            'service); a headless or scheduled collector can collect instead'}
    stale = found.get('observation_stale') or {}
    # Staleness only from a stamp ahead of the clock is cured by collecting only where the store's ordering fact says
    # a new collection from this session's service becomes current (judged once, in _with_collect_cures).
    stamped_ahead = (_stamped_ahead_only((stale.get('evidence') or {}).get('freshness_reasons'))
                     and not (stale.get('evidence') or {}).get('collect_cures'))
    # A clock hold on the age is not cured by collecting either: a new observation is judged against the same time.
    held = clock_hold((stale.get('evidence') or {}).get('freshness_reasons')) is not None
    record = _record_offer(attention)

    def offer_record():
        offer('deployment-record', 'Record the deployment of operation %s' % _short(store, prefixes, record['operation_id']),
              'deployment-record %s %s' % (shlex.quote(str(record['operation_root'])), record['intent_id']),
              extra={'operation_id': record['operation_id'], 'operation_root': record['operation_root'],
                     'intent_id': record['intent_id']})

    if (any(code in found for code in ('collection_failed', 'collection_not_finished'))
            or ('observation_stale' in found and not stamped_ahead and not held)):
        # One first action: the record comes before the collection whenever both are offered, as the band and Delivery
        # say (the order the change moves in: record the deployment, then collect to observe the policy after it).
        if record:
            offer_record()
        offer('collect', 'Collect again', 'collect', blocked=no_service)
    if any(code in found for code in ('repository_stale', 'repository_consumer_mismatch')):
        offer('repository-refresh', 'Refresh the repository intent',
              'repository-refresh ', cursor=len('repository-refresh '), show_first='repository-status',
              needs=['REVISION: the full 40-character commit ID; without a pinned git it is recorded as '
                     'stated, not checked against the files'])
    if record and not any(action['kind'] == 'deployment-record' for action in actions):
        offer_record()
    blocked = _proposal_blocker(store, object_id, attention, intent, service_root, eligibility)
    # A stamp ahead that collecting cannot cure, or a clock hold: the proposal's own check does not make collecting the fix.
    ahead = ((_stamped_ahead_only(eligibility.get('freshness_reasons')) and not _collect_cures(eligibility, service_root))
             or clock_hold(eligibility.get('freshness_reasons')) is not None
             if isinstance(eligibility, dict) else False)
    if ((blocked or {}).get('reason') in RECOLLECT_REASONS and not ahead
            and not any(action['kind'] == 'collect' for action in actions)):
        # The proposal's own check names collecting again as the fix, even when nothing recorded says so yet.
        offer('collect', 'Collect again', 'collect', blocked=no_service)
    target = _fresh_operation(store, object_id)
    if target is None:
        blocked = blocked or {'code': 'workbench_fresh_output_required', 'message': 'no fresh operation directory could be chosen'}
    if intent is not None:
        offer('propose-from-intent', 'Prepare a proposal from the recorded intent',
              'propose-from-intent ' + shlex.quote(target or ''), blocked=blocked)
    else:
        offer('repository-entry', 'Find where this policy is maintained', 'repository-entry ', cursor=len('repository-entry '),
              needs=['REPOSITORY: the repository directory to survey'])
        offer('propose', 'Prepare a local proposal from a desired file', 'propose  ' + shlex.quote(target or ''),
              cursor=len('propose '), needs=['DESIRED_JSON: a file holding the desired policy body'], blocked=blocked)
    # Last, so every other action keeps its place: a view of this policy, not a step of the work.
    offer('companion', 'Write the read-only isometric page for this policy', 'companion ', cursor=len('companion '),
          needs=['FILE: where to write the page; you supply the path of a file, not an address'])
    return actions


def _inspection(store, object_id, *, attention=False, service_available=False, service_root=None):
    """Combine an exact observed object with the current declared writer evidence.

    The raw observation remains unchanged. Selected repository intent and state
    claims are distinct management evidence, never authenticated cloud ownership.
    With attention, the Inspector's read model adds what diagnostics records as
    needing attention and the next steps, so the screen states them instead of
    inferring them.
    """
    from .workbench_views import _intents, _latest, ownership
    value = store.inspect(object_id)
    raw_capture = store.raw_capture_observation(object_id)
    intent = _latest(_intents(store, object_id, None))
    scope = intent['data']['scope'] if intent else None
    writer = ownership(store, object_id, scope)
    if attention:
        service = None if service_root is None else str(service_root)
        found = _with_collect_cures(_attention(store, object_id), service)
        eligibility = _eligibility(store, object_id, service, observation=value)
        states = _states(value, intent, found, eligibility)
        # Shortened identities on every surface use these, never an assumed-unique first eight characters.
        prefixes = store.identity_prefixes(objects=[object_id], operations=_referenced_operations(found, states),
                                           artifacts=[intent['artifact_id']] if intent else [])
        value = {**value, 'attention': found, 'observation_eligibility': eligibility, 'states': states,
                 'identity_prefixes': prefixes,
                 'next_actions': _next_actions({'selected_repository': intent}, found, service_available or service_root is not None),
                 'actions': _actions(store, object_id, found, intent, service, eligibility=eligibility,
                                     evidence_class=value.get('evidence_class'), prefixes=prefixes)}
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


def _companion_read(store, object_id):
    """The one read the companion page makes, afresh each time: the engine's own relationships result for the object
    (with the selected repository), the policy's recorded operation word and the observation's freshness as the
    terminal's strip reads them, the evidence class and the tenant. Raises AppError for an object it cannot read."""
    def read():
        from .workbench_screens import _operation_from_states, observation_word
        found = _inspection(store, object_id, attention=True)
        operation = _operation_from_states(found)
        freshness = found.get('freshness')
        return {'value': _facet(store, object_id, 'relationships'), 'mode_class': found.get('evidence_class'),
                'tenant': store.tenant_id, 'states': {object_id: operation} if operation else {},
                'freshness': observation_word(freshness, found.get('freshness_reasons')) if isinstance(freshness, str) else None}
    return read


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
                             no_color=args.no_color, reduced_motion=args.reduced_motion, rules='ascii' if args.ascii else 'auto')
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
    if name == 'delivery':
        from .workbench_delivery import delivery
        return delivery(args.operation)
    if name in ('review', 'execute', 'reconcile', 'propose', 'restore-propose'):
        from . import maintenance
        if name == 'restore-propose': return maintenance.propose_restore(args.operation, args.output)
        if name == 'review': return maintenance.review(args.operation)
        if name == 'execute': return maintenance.execute(args.operation, approve_digest=args.approve_digest, fault=args.fault,
                                                          visibility_delay_reads=args.visibility_delay_reads)
        if name == 'reconcile': return maintenance.reconcile(args.operation)
        return maintenance.propose(args.root, args.service_root, args.object, args.desired, args.output, context_path=args.context)
    if name == 'estate-overview':
        from .workbench_overview import estate_overview
        return estate_overview(_store(args.root), limit=args.limit)
    if name == 'companion':
        from .companion import run_companion
        read = _companion_read(_store(args.root), args.object)
        read()  # an object that cannot be read is an error now, before a file is written or a port is bound
        # The address goes out before the command blocks; the result (how it ended) follows as the one JSON document.
        return run_companion(read, out=args.out, serve=args.serve, announce=lambda text: print(text, flush=True),
                             idle_seconds=args.idle_seconds)
    if name == 'families':
        from .families import families
        return families()
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
    if name == 'diagnostics':
        from .workbench_diagnostics import diagnostics
        return diagnostics(store, args.object)
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
    'navigation': ['start [DIRECTORY] (what exists beside the store and the next step; read-only)', 'diagnostics (selected object: what needs attention, with evidence and next steps)', 'families (every policy, application and script family with its support disposition)', 'overview [LIMIT [OFFSET]]', 'next', 'previous', 'search TEXT', 'search-page LIMIT OFFSET TEXT', 'select EXACT_OBJECT_ID', 'inspect', 'settings',
                   'relationships', 'lineage [JSON_POINTER]', 'adoption-lineage', 'dictionary [SETTING_ID_QUERY]', 'references', 'reference-compare REFERENCE_ID [COMPANY_JSON]',
                   'dictionary-page LIMIT OFFSET [SETTING_ID_QUERY]', 'workflows', 'history [LIMIT [OFFSET]]', 'history-recent [LIMIT [OFFSET]] (newest first, default 10)', 'compare BEFORE_SNAPSHOT AFTER_SNAPSHOT',
                   'health [LIMIT [OFFSET]]', 'queue [LIMIT [OFFSET]]', 'operations [LIMIT [OFFSET]]',
                   'estate-overview (groups, filters, scope tags and settings the observed policies share)',
                   'companion FILE | serve | stop (selected policy: write the read-only isometric page to FILE, or serve it on '
                   'this machine only under a secret address; never opens a browser; use ./serve for a file of that name)',
                   'repository-entry REPOSITORY (the policies a repository holds and the exact command to record each)',
                   'repository-import REPO STACK COMPONENT OBJECT POINTER REVISION BACKEND RESOURCE_ADDRESS',
                   'repository-status (selected object: is its latest repository intent still current?)',
                   'repository-refresh REVISION [RESOLUTION_SHA256] (selected object: record the current source as a new '
                   'intent; with the digest the Repository surface showed, refused if the source changed since)',
                   'source-review PROPOSAL_DIR DIGEST',
                   'source-edit PROPOSAL_DIR DIGEST EXPIRY ACK-LOCAL-FILE-EDIT',
                   'source-edit-status SOURCE_ROOT OPERATION_ID',
                   'source-edit-recover SOURCE_ROOT OPERATION_ID complete|rollback|abort EXPIRY ACK-LOCAL-FILE-EDIT',
                   'source-acceptance-propose FIELD NEW_OUTPUT_DIR', 'views [OPERATION_DIR]', 'views-page LIMIT OFFSET [QUERY [OWNERSHIP [COVERAGE [HEALTH]]]] (- means no filter)',
                   'field-semantics', 'clear-selection (clears the selected policy; in the text interface back and cancel do the same, nothing else is undone or cancelled; in the workspace :back returns to the previous view and :cancel cancels nothing)', 'back', 'cancel', 'quit or exit (exits; the last read-only view is kept for the next start)'],
    'maintenance': ['propose-from-intent NEW_OPERATION_DIR (selected object; desired body and citation from the current repository intent)',
                    'propose DESIRED_JSON OUTPUT_DIR [CONTEXT_JSON]', 'review OPERATION_DIR',
                    'delivery OPERATION_DIR (read-only: proposal, approval, execution, readback, reconciliation, deployment record, observation)',
                    'execute OPERATION_DIR EXPLICIT_REVIEW_DIGEST [FAULT [VISIBILITY_DELAY_READS]]', 'reconcile OPERATION_DIR',
                    'restore-propose PREVIOUS_OPERATION_DIR NEW_OUTPUT_DIR (fresh review required)',
                    'deployment-record OPERATION_DIR INTENT_ID (records a verified local operation as the deployment of '
                    'the intent it cites; sends nothing)',
                    'queue-review-template FINDING NEW_JSON (selected object: writes the review form to fill; never '
                    'overwrites)', 'queue-amend REVIEW_JSON PRIOR|none (records a review annotation; never approval)',
                    'queue-review FINDING', 'queue-review-history FINDING'],
    'adoption': ['adoption-preview COMPLETED_JOURNEY_JSON', 'adopt COMPLETED_JOURNEY_JSON NEW_HANDOFF_DIR (separate local maintenance model)'],
    'received_worker_evidence': ['evidence-link EVIDENCE_STORE REQUEST_SHA256 TRUST_PATH VERIFIER_PATH PRIVATE_SCRATCH',
                                 'evidence-history (selected object; every read rechecks signed bytes/current trust)'],
    'protected_service': ['service-link JOB_ROOT POLICY_PATH (link selected object to persistent four views)',
                          'service-review JOB_ROOT POLICY_PATH', 'service-status JOB_ROOT POLICY_PATH',
                          'service-attach JOB_ROOT POLICY_PATH (read-only; no dispatch or replay)',
                          'service-cancel JOB_ROOT POLICY_PATH (request only; inspect resulting state)',
                          'service-recover JOB_ROOT POLICY_PATH (explicit recovery; no mutation replay)'],
    'protected_adoption': ['adoption-link JOB_ROOT POLICY_PATH (state-only; no Graph deployment baseline)',
                 'adoption-history (selected object)', 'adoption-review JOB_ROOT POLICY_PATH',
                 'adoption-status JOB_ROOT POLICY_PATH', 'adoption-attach JOB_ROOT POLICY_PATH (no dispatch)',
                 'adoption-cancel JOB_ROOT POLICY_PATH', 'adoption-recover JOB_ROOT POLICY_PATH (no import replay)'],
    'adoption_recovery_plan': ['adoption-plan-review JOB_ROOT POLICY_PATH', 'adoption-plan-status JOB_ROOT POLICY_PATH',
                              'adoption-plan-attach JOB_ROOT POLICY_PATH (read-only)',
                              'adoption-plan-cancel JOB_ROOT POLICY_PATH', 'adoption-plan-recover JOB_ROOT POLICY_PATH (no replay)'],
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
    # Never hard-wrap: a terminal soft-wraps a long line itself, and a pipe must get every value, command and
    # path whole on its own line.
    for line in json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False).splitlines():
        output_fn(line)


# What an interrupt means and what to do next. The workspace clears its frame when it restores the terminal, so the
# returned result carries this too, not only the result drawn before it.
def _interrupted_during(current):
    """What was running when the interrupt arrived, from the command the terminal loop recorded; None at the prompt."""
    name, values = current.get('name'), current.get('values') or []
    if not name:
        return None
    if name in ('execute', 'reconcile') and values:
        return {'command': name, 'operation_root': str(Path(values[0]).absolute())}
    if name == 'collect':
        return {'command': 'collect', 'service_root': current.get('service_root')}
    return {'command': name}


def interrupted_lines(result):
    """The interrupted session's result as sentences for a person: what was running, what the interrupt left, and the
    exact next step. Scripts read the same facts as JSON."""
    import shlex
    during = result.get('interrupted_during') if isinstance(result.get('interrupted_during'), dict) else None
    # Paths are shell-quoted so the printed command runs as shown when pasted, spaces and quotes included.
    store = shlex.quote(str(result['store_root'])) if result.get('store_root') else 'STORE'
    others = 'Other processes, such as a scheduled collector, were not stopped.'
    # Each command stands on its own line, indented by two spaces, so a terminal's soft wrap copies it whole.
    if during and during.get('command') == 'execute':
        operation = during.get('operation_root')
        # Quoted as the command below it is, so a path with spaces reads as one path in both.
        return ['Interrupted while executing operation %s.' % shlex.quote(str(operation)),
                'Its outcome is unknown: the change may or may not have reached the service. Nothing retries it.',
                'Next: reconcile it before anything else. Reconcile reads the service and never replays the change. '
                'Run:',
                '  intune-iac workbench reconcile --operation %s' % shlex.quote(str(operation)),
                'or reopen the workspace and choose Reconcile with a.', others]
    if during and during.get('command') == 'reconcile':
        return ['Interrupted while reconciling operation %s.' % shlex.quote(str(during.get('operation_root'))),
                'Reconcile only reads the service, so running it again is safe. Run:',
                '  intune-iac workbench reconcile --operation %s' % shlex.quote(str(during.get('operation_root'))),
                others]
    if during and during.get('command') == 'collect':
        return ['Interrupted during a collection.',
                'That run records no end; the newest complete observation is kept and is labelled as such.',
                'Next: collect again. Run:',
                '  intune-iac workbench collect --root %s --service-root %s' % (
                    store, shlex.quote(str(during['service_root'])) if during.get('service_root') else 'SERVICE'),
                'or reopen the workspace and choose Collect again with a.', others]
    if during:
        return ['Interrupted while running %s.' % during.get('command'),
                'Next: diagnostics name anything it left unfinished. Run:',
                '  intune-iac workbench diagnostics --root %s --object ID' % store, others]
    return ['Interrupted while waiting for a command. Nothing was running.', others]


def interrupted_text(result, width):
    """interrupted_lines for a terminal: sentences wrapped at spaces to the width; command lines left whole."""
    import textwrap
    lines = []
    for line in interrupted_lines(result):
        lines += _wrap_command(line, width) if line.startswith('  ') else textwrap.wrap(
            line, max(20, width), break_long_words=False, break_on_hyphens=False) or ['']
    return lines


def _wrap_command(line, width):
    """A command line that fits stays whole. A wider one breaks between its arguments, never inside a quoted path, and
    each row but the last ends with a backslash, so pasting the rows runs the one command."""
    import re
    if len(line) <= width:
        return [line]
    # Arguments, a single-quoted one (a path with spaces) kept as one piece.
    pieces = re.findall(r"(?:'[^']*'|[^\s'])+", line)
    rows, row = [], '  ' + pieces[0]
    for piece in pieces[1:]:
        if len(row) + 1 + len(piece) + 2 <= width:
            row += ' ' + piece
        else:
            rows.append(row + ' \\')
            row = '    ' + piece
    return rows + [row]


INTERRUPTED_RECOVERY = ('Other processes, such as a scheduled collector, were not stopped. diagnostics names anything this '
                        'interrupt left unfinished, such as a collection with no end or an execution whose outcome is '
                        'unknown; reconcile before retrying any uncertain execution.')


def run_terminal(root, *, service_root=None, input_fn=None, output_fn=None, result_fn=None, _store_capability=None):
    """Retain interrupt intent even when a native callback translates its exception.

    SQLite can turn KeyboardInterrupt from a progress callback into OperationalError.
    A pending signal must therefore be checked outside that callback before rendering
    a recoverable error or accepting another command. Native execution may install
    its own cleanup handler temporarily; the existing handler is always delegated to
    and restored. No signal handler is installed from non-main threads.
    """
    pending = False
    current = {}  # the command in flight, recorded by the loop; empty at the prompt
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
                             output_fn=output_fn, result_fn=result_fn, interrupt_check=check_interrupt, _store_capability=_store_capability,
                             _current=current)
    except KeyboardInterrupt:
        during = _interrupted_during(current)
        result = {'status': 'interrupted', 'evidence_class': 'local_interface_result', 'interrupted_during': during,
                  'store_root': str(Path(root).absolute())}
        result['recovery'] = ' '.join(interrupted_lines(result))
        value = {key: result[key] for key in ('status', 'interrupted_during', 'recovery')}
        if result_fn is None:
            _render(value, print if output_fn is None else output_fn)
        else:
            result_fn(value)
        return result
    finally:
        if installed:
            signal.signal(signal.SIGINT, previous)


def _adopted_service(store):
    """The modeled service named by the store's latest adoption record: None without an adoption, and a problem
    when that service cannot be opened for this tenant (never an older adoption's service instead).

    After adopt, the normal journey continues against the handoff's modeled service; reopening the store must not
    need --service-root to find it again (owner directive inbox/PRODUCT-TASK-12.md, section 4).
    """
    from .modeled_service import ModeledService
    row = store.latest_artifact('adoption')
    if row is None:
        return None
    data = row['data'] if isinstance(row.get('data'), dict) else {}
    candidate = data.get('maintenance_service_root')
    origin = {'root': candidate if isinstance(candidate, str) else None, 'source': 'adoption',
              'artifact_id': row['artifact_id']}
    try:
        if not isinstance(candidate, str) or ModeledService(candidate).snapshot()['current']['tenant_id'] != store.tenant_id:
            return dict(origin, problem='service_unavailable')
    except (AppError, OSError, KeyError, TypeError, ValueError):
        return dict(origin, problem='service_unavailable')
    return origin


def _run_terminal(root, *, service_root=None, input_fn=None, output_fn=None, result_fn=None, interrupt_check=lambda: None, _store_capability=None,
                  _current=None):
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
    # Which modeled service this session uses, and why: --service-root, else the latest adoption record's.
    service_origin = None if service_root is None else {'root': str(service_root), 'source': 'command line'}
    if service_root is None and _store_capability is None:
        service_origin = _adopted_service(store)
        if service_origin is not None and not service_origin.get('problem'):
            service_root = service_origin['root']
    page = {'kind': 'overview', 'limit': 10, 'offset': 0, 'query': ''}
    held = []  # the loopback listeners this session started; the session ends them, and each ends itself when idle
    def stop_companions():
        for listener in held:
            listener.stop()
        held.clear()
    def show_page(specification=None):
        target = page if specification is None else specification
        if target['kind'] == 'history-recent':
            return store.recent_history_page(target['object_id'], limit=target['limit'], offset=target['offset'])
        if target['kind'] == 'views':
            from .workbench_views import views
            return dict(views(store, limit=target['limit'], offset=target['offset'], query=target['query'],
                              ownership_filter=target.get('ownership'), coverage_filter=target.get('coverage'),
                              health_filter=target.get('health')), modeled_service=service_origin)
        if target['kind'] == 'search': return _search(store, target['query'], limit=target['limit'], offset=target['offset'])
        if target['kind'] == 'dictionary': return _dictionary(store, target['query'], limit=target['limit'], offset=target['offset'])
        if target['kind'] == 'health': return _health(store, limit=target['limit'], offset=target['offset'])
        if target['kind'] == 'queue': return _queue(store, limit=target['limit'], offset=target['offset'])
        return dict(store.overview(limit=target['limit'], offset=target['offset']), modeled_service=service_origin)
    def set_page(kind, limit=10, offset=0, query=''):
        candidate = {'kind': kind, 'limit': limit, 'offset': offset, 'query': query}
        result = show_page(candidate)
        page.update(candidate)
        return result
    try:
        initial_overview = show_page()
        present({'title': 'Intune Workbench', 'evidence_class': initial_overview.get('evidence_class', 'unknown'), 'commands': HELP})
        present(initial_overview)
        current = {} if _current is None else _current
        while True:
            try:
                current.clear()  # back at the prompt: nothing is in flight
                interrupt_check()
                line = input_fn('workbench> ')
                interrupt_check()
                if len(line) > 16384: raise ValueError('command too long')
                parts = shlex.split(line)
                if not parts: continue
                name, values = parts[0].lower(), parts[1:]
                current.update(name=name, values=values, service_root=None if service_root is None else str(service_root))
                if _store_capability is not None:
                    from .windows_workspace_binding import require_command
                    require_command(name)
                if name in ('quit', 'exit') and not values:
                    stop_companions()
                    return {'status': 'closed', 'evidence_class': 'local_interface_result', 'history_persisted': True}
                if name == 'help' and not values: result = HELP
                elif name == 'views' and len(values) <= 1:
                    from .workbench_views import views
                    if values and selected is None:
                        raise AppError('selection_required', 'Select an exact immutable object ID first.')
                    result = views(store, selected, operation=values[0] if values else None, limit=10)
                elif name == 'estate-overview' and not values:
                    from .workbench_overview import estate_overview
                    result = estate_overview(store)
                elif name == 'companion' and len(values) == 1:
                    if selected is None:
                        raise AppError('selection_required', 'Select an exact immutable object ID first.')
                    from .companion import start_live, write_static
                    read = _companion_read(store, selected)
                    if values[0] == 'serve':
                        if held: raise AppError('companion_running', 'A companion listener is already running; "companion stop" ends it.')
                        read()
                        listener = start_live(read)
                        held.append(listener)
                        result = {'mode': 'live', 'address': listener.address, 'notice': listener.notice}
                    elif values[0] == 'stop':
                        stop_companions()
                        result = {'mode': 'live', 'stopped': 'stopped'}
                    else: result = write_static(read, values[0])
                elif name == 'repository-entry' and len(values) == 1:
                    from .repository_entry import entry
                    result = entry(store, values[0])
                elif name == 'repository-import' and len(values) == 8:
                    from .workbench_views import import_repository
                    result = import_repository(store,*values)
                elif name in ('repository-status', 'repository-refresh', 'propose-from-intent'):
                    from . import workbench_repository as repository
                    if selected is None:
                        raise AppError('selection_required', 'Select an exact immutable object ID first.')
                    if name == 'repository-status' and not values: result = repository.status(store, selected)
                    elif name == 'repository-refresh' and len(values) in (1, 2):
                        result = repository.refresh_intent(store, selected, values[0],
                                                           expected_resolution=values[1] if len(values) == 2 else None)
                    elif name == 'propose-from-intent' and len(values) == 1:
                        if service_root is None: raise AppError('service_required', 'Supply --service-root for synthetic maintenance.')
                        result = repository.propose_from_intent(root, service_root, selected, values[0])
                    else: raise ValueError('invalid command arguments')
                elif name in ('source-review', 'source-edit', 'source-edit-status', 'source-edit-recover'):
                    if _store_capability is None:
                        raise AppError('source_edit_native_capability_required','This route requires the explicit inactive native store capability.')
                    from .windows_source_edit import review_source_proposal, apply_source_proposal, inspect_source_edit, recover_source_edit
                    if name == 'source-review' and len(values) == 2:
                        result = review_source_proposal(store,*values)
                    elif name == 'source-edit' and len(values) == 4 and values[3] == 'ACK-LOCAL-FILE-EDIT':
                        result = apply_source_proposal(store,values[0],values[1],float(values[2]),acknowledged=True)
                    elif name == 'source-edit-status' and len(values) == 2:
                        result = inspect_source_edit(store,*values)
                    elif name == 'source-edit-recover' and len(values) == 5 and values[4] == 'ACK-LOCAL-FILE-EDIT':
                        result = recover_source_edit(store,values[0],values[1],values[2],float(values[3]),acknowledged=True)
                    else:
                        raise AppError('source_edit_arguments','Use help; an exact local file-edit acknowledgment and bounded expiry are required.')
                elif name == 'source-acceptance-propose' and len(values) == 2:
                    if selected is None:
                        raise AppError('selection_required', 'Select an exact immutable object ID first.')
                    from .workbench_views import propose_source_acceptance
                    result = propose_source_acceptance(store,selected,*values)
                elif name in ('adoption-link', 'adoption-history') and len(values) == (2 if name == 'adoption-link' else 0):
                    if selected is None:
                        raise AppError('selection_required', 'Select an exact immutable object ID first.')
                    from . import workbench_adoption_views as adoption_views
                    result = adoption_views.link(store, selected, values[0], values[1]) if name == 'adoption-link' else adoption_views.history(store, selected)
                elif name in ('adoption-review', 'adoption-status', 'adoption-attach', 'adoption-cancel', 'adoption-recover') and len(values) == 2:
                    if selected is None:
                        raise AppError('selection_required', 'Select an exact immutable object ID first.')
                    from .adoption_cli import invoke
                    result = invoke(name.removeprefix('adoption-'), values[0], values[1], tenant_id=store.tenant_id, object_id=selected)
                elif name in ('adoption-plan-review', 'adoption-plan-status', 'adoption-plan-attach', 'adoption-plan-cancel', 'adoption-plan-recover') and len(values) == 2:
                    if selected is None:
                        raise AppError('selection_required', 'Select an exact immutable object ID first.')
                    from .adoption_cli import invoke_plan
                    result = invoke_plan(name.removeprefix('adoption-plan-'), values[0], values[1], tenant_id=store.tenant_id, object_id=selected)
                elif name in ('evidence-link','evidence-history') and len(values) == (5 if name == 'evidence-link' else 0):
                    if selected is None:
                        raise AppError('selection_required', 'Select an exact immutable object ID first.')
                    from . import workbench_evidence_views as received_views
                    result = received_views.link(store,selected,*values) if name == 'evidence-link' else received_views.history(store,selected)
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
                elif name in ('back', 'cancel', 'clear-selection') and not values:
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
                    result = _inspection(store, values[0], attention=True, service_available=service_root is not None, service_root=service_root)
                    selected = values[0]
                elif name == 'health' and len(values) <= 2:
                    result = (_health(store, selected) if selected is not None and not values else
                              set_page('health', int(values[0]) if values else 10, int(values[1]) if len(values) == 2 else 0))
                elif name == 'families' and not values:
                    from .families import families
                    result = families()
                elif name == 'diagnostics' and not values:
                    from .workbench_diagnostics import diagnostics
                    if selected is None:
                        raise AppError('selection_required', 'Select an exact immutable object ID first.')
                    result = diagnostics(store, selected)
                elif name == 'start' and len(values) <= 1:
                    from .entry import survey
                    # What exists beside the store (or in DIRECTORY) and the next step; read-only, offline.
                    result = survey(values[0] if values else Path(store.root).parent)
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
                    latest = store.latest_artifact('adoption')
                    service_origin = {'root': service_root, 'source': 'adoption',
                                      'artifact_id': None if latest is None else latest['artifact_id']}
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
                    if name == 'inspect' and not values: result = _inspection(store, selected, attention=True, service_available=service_root is not None, service_root=service_root)
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
                elif name == 'delivery' and len(values) == 1:
                    from .workbench_delivery import delivery
                    result = delivery(values[0])
                elif name in ('queue-review', 'queue-review-history', 'queue-review-template') and len(values) == (2 if name == 'queue-review-template' else 1):
                    from . import workbench_queue as queue
                    if selected is None:
                        raise AppError('selection_required', 'Select an exact immutable object ID first.')
                    result = (queue.current(store, selected, values[0]) if name == 'queue-review' else
                              queue.history(store, selected, values[0]) if name == 'queue-review-history' else
                              queue.template(store, selected, values[0], values[1]))
                elif name == 'queue-amend' and len(values) == 2:
                    from . import workbench_queue as queue
                    result = queue.amend(store, values[0], expected_prior=None if values[1] == 'none' else values[1])
                elif name == 'deployment-record' and len(values) == 2:
                    from .workbench_views import record_local_deployment
                    result = record_local_deployment(store, values[0], values[1])
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
                stop_companions()
                return {'status': 'closed', 'evidence_class': 'local_interface_result', 'history_persisted': True}
            except KeyboardInterrupt:
                stop_companions()
                # The same result as run_terminal's outer handler: what was running, what it left, the next step.
                during = _interrupted_during(current)
                result = {'status': 'interrupted', 'evidence_class': 'local_interface_result',
                          'interrupted_during': during, 'store_root': str(Path(root).absolute())}
                result['recovery'] = ' '.join(interrupted_lines(result))
                present({key: result[key] for key in ('status', 'interrupted_during', 'recovery')})
                return result
            except AppError as error:
                effects = getattr(error, 'effects', None)
                present({'status': 'error', 'error': dict({'code': error.code, 'message': error.message},
                                                        **({'effects': effects} if isinstance(effects, dict) else {}))})
            except (ValueError, TypeError, KeyError, OSError):
                present({'status': 'error', 'error': {'code': 'invalid_workbench_request',
                         'message': 'Command or local input is invalid. Enter help for exact syntax.'}})
    finally:
        # However the session ends (a return, an error in the input or in the presentation), the
        # listeners it started do not outlive it.
        stop_companions()
