"""Where one intentional change stands, stage by stage, from its durable records.

Read-only. The operation is loaded through the maintenance engine's own
integrity checks (plan, hash-chained journal, desired body, engine request and
executor). The view reads the operation directory and the store; it never
contacts the service, dispatches, approves, reconciles or writes. Each stage
says what its records show and names the evidence it rests on.

Whether an observation came after the change is decided by the service
revision the collector recorded, never by comparing clock times: a host clock
can step backwards. The approval window is the engine request's own
[created_at, expires_at) interval, which approval enforces.
"""
from __future__ import annotations

from datetime import datetime, timezone
import shlex
import time

from .workbench_diagnostics import CLOCK_HOLD_CAUSES, CLOCK_HOLD_REASONS, CLOCK_HOLD_WORDS, clock_hold

VERSION = 'workbench-delivery/1'
STAGES = ('proposal', 'review', 'approval', 'execution', 'readback', 'reconciliation', 'deployment_record', 'observed_after')
MAX_RECEIPTS = 100


def _utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _events(journal, kind):
    return [event for event in journal['events'] if event['kind'] == kind]


def _receipts(root, kind):
    """The operation's readback or reconciliation files, in the order the engine numbered them."""
    from .io import load_json
    from .maintenance import _fail
    paths = []
    for path in root.glob(kind + '-*.json'):
        number = path.stem[len(kind) + 1:]
        if not number.isdigit() or len(paths) >= MAX_RECEIPTS:
            _fail('maintenance_evidence_changed')
        paths.append((int(number), path))
    return [(path, load_json(path)) for _, path in sorted(paths)]


def _readback_fields(path, value):
    visibility = value.get('visibility') if isinstance(value.get('visibility'), dict) else {}
    second = value.get('second_plan') if isinstance(value.get('second_plan'), dict) else {}
    return {'path': str(path), 'classification': value.get('classification'), 'visibility_pending': visibility.get('pending'),
            'committed_revision': visibility.get('committed_revision'), 'second_plan': second.get('status'),
            'mismatch_count': len(value.get('mismatches') or [])}


def _approval(journal, request, now, judged=None):
    """judged: the window as execute judges it (maintenance.approval_window). A recorded expiry, a held window and
    an unreadable time record come from it; its effective time stands in for the wall clock."""
    window = {'opens_at': request['created_at'], 'closes_at': request['expires_at']}
    judged = judged if isinstance(judged, dict) else {}
    dispatches = _events(journal, 'dispatch_started')
    if dispatches:
        return {'stage': 'approval', 'status': 'done', 'approval_digest': dispatches[0].get('approval_digest'), **window}
    if journal['status'] == 'rejected':
        return {'stage': 'approval', 'status': 'rejected', **window}
    if judged.get('state') == 'closed_recorded':
        return {'stage': 'approval', 'status': 'expired', 'recorded': True, **window}
    if judged.get('state') == 'unknown':
        return {'stage': 'approval', 'status': 'clock_unreadable', **window}
    if judged.get('state') == 'clock_moved_backward':
        return {'stage': 'approval', 'status': 'clock_uncertain', **window}
    if now < request['created_at']:
        return {'stage': 'approval', 'status': 'not_open', **window}
    return {'stage': 'approval', 'status': 'waiting' if now < request['expires_at'] else 'expired', **window}


def _execution(journal, times):
    if not _events(journal, 'dispatch_started'):
        return {'stage': 'execution', 'status': 'not_started'}
    engine, responses = _events(journal, 'engine_result'), _events(journal, 'service_response')
    uncertain = _events(journal, 'uncertain')
    result = engine[-1].get('result') if engine and isinstance(engine[-1].get('result'), dict) else {}
    response = responses[-1].get('response') if responses and isinstance(responses[-1].get('response'), dict) else {}
    no_change = bool(_events(journal, 'service_no_change'))
    # A recorded service answer shows the change was sent; a recorded no-change shows nothing was. Otherwise, after
    # dispatch started (a lost response, an interrupt), whether the change reached the service is not established.
    dispatched = True if responses else False if no_change else None
    return {'stage': 'execution', 'status': 'done' if _events(journal, 'verified') else 'unknown',
            'engine_status': result.get('status'), 'service_status': response.get('status'),
            'mutation_dispatched': dispatched, 'no_change_dispatch': no_change,
            'error_code': uncertain[-1].get('error_code') if uncertain else None,
            'recorded_at': times.get('succeeded_verified') or times.get('outcome_unknown')}


def _readback(root, journal):
    from .io import digest
    from .maintenance import _fail
    verified = _events(journal, 'verified')
    readbacks = _receipts(root, 'readback')
    if verified:
        matched = [item for item in readbacks if digest(item[1]) == verified[-1].get('readback_sha256')]
        if len(matched) != 1:
            _fail('maintenance_evidence_changed')
        return {'stage': 'readback', 'status': 'done', **_readback_fields(*matched[0])}
    if readbacks:
        fields = _readback_fields(*readbacks[-1])
        return {'stage': 'readback', 'status': 'pending' if fields['visibility_pending'] else 'failed', **fields}
    return {'stage': 'readback', 'status': 'not_recorded' if _events(journal, 'dispatch_started') else 'not_started'}


def _reconciliation(root, journal, times):
    events = _events(journal, 'reconciled')
    if events:
        last = events[-1]
        visibility = last.get('visibility') if isinstance(last.get('visibility'), dict) else {}
        files = _receipts(root, 'reconciliation')
        return {'stage': 'reconciliation', 'status': 'pending' if visibility.get('pending') else 'done',
                'classification': last.get('classification'), 'previous_status': last.get('previous_status'),
                'count': len(events), 'path': str(files[-1][0]) if files else None, 'recorded_at': times.get('reconciled')}
    return {'stage': 'reconciliation', 'status': 'required' if journal['status'] == 'outcome_unknown' else 'not_needed'}


def _deployment(store, plan, journal, repository):
    receipts = [row for row in store.artifacts(kind='deployment_receipt')
                if isinstance(row['data'].get('proof'), dict) and row['data']['proof'].get('operation_id') == plan['operation_id']]
    if receipts:
        latest = receipts[-1]['data']
        return {'stage': 'deployment_record', 'status': 'done', 'artifact_id': receipts[-1]['artifact_id'],
                'intent_id': latest.get('intent_id'), 'recorded_at': receipts[-1]['recorded_at'],
                'evidence_class': latest.get('evidence_class'), 'baseline_admissible': latest.get('baseline_admissible'),
                'platform_qualified': latest.get('platform_qualified'),
                # The views recheck the bound context bytes, so a record whose context changed is no longer admitted.
                **({'context_changed': True} if repository.get('context_changed') else {})}
    if repository.get('context_changed'):
        # deployment-record checks the bound context bytes; a changed file can never pass.
        return {'stage': 'deployment_record', 'status': 'not_available', 'reason': 'context_changed'}
    if not repository.get('cited'):
        return {'stage': 'deployment_record', 'status': 'not_applicable', 'reason': 'no_repository_intent_cited'}
    # These are the conditions deployment-record checks first; it still performs every check itself.
    if journal['status'] in ('succeeded_verified', 'reconciled') and len(_events(journal, 'verified')) == 1:
        return {'stage': 'deployment_record', 'status': 'available', 'intent_id': repository['repository_intent_id']}
    if journal['status'] == 'reconciled':
        return {'stage': 'deployment_record', 'status': 'not_available', 'reason': 'no_verified_readback'}
    return {'stage': 'deployment_record', 'status': 'not_yet'}


def _observed_after(store, plan, desired, journal):
    from .workbench_diff import field_changes
    if not _events(journal, 'dispatch_started'):
        return {'stage': 'observed_after', 'status': 'not_yet'}
    if not plan['changes']:
        return {'stage': 'observed_after', 'status': 'not_applicable', 'reason': 'no_configuration_change'}
    page = store.recent_history_page(plan['object_id'], limit=1)
    latest = page['history'][0] if page['history'] else None
    if latest is None:
        return {'stage': 'observed_after', 'status': 'not_yet'}
    source = latest.get('source') if isinstance(latest.get('source'), dict) else {}
    found = {'observed_at': latest.get('observed_at'), 'snapshot_id': latest.get('snapshot_id'),
             'service_revision': source.get('service_revision'), 'before_revision': plan['before_revision']}
    if source.get('service_root') != plan['service_root'] or type(source.get('service_revision')) is not int:
        return {'stage': 'observed_after', 'status': 'unknown', 'reason': 'latest_observation_from_another_source', **found}
    if source['service_revision'] <= plan['before_revision']:
        return {'stage': 'observed_after', 'status': 'not_yet', **found}
    changes = field_changes(desired, latest.get('body'))
    status = {'no_change': 'matches_desired', 'changed': 'differs'}.get(changes.get('status'), 'unknown')
    # Whether the observation that shows it still reads fresh, so a settled verdict is never drawn from a stale one.
    current = store.inspect(plan['object_id'])
    clock_fact = ({'observation_freshness_clock': dict(current['freshness_clock'])}
                  if isinstance(current.get('freshness_clock'), dict) else {})
    return {'stage': 'observed_after', 'status': status, 'field_changes': changes, **found,
            'observation_freshness': current.get('freshness'),
            'observation_freshness_reasons': list(current.get('freshness_reasons') or []), **clock_fact}


RUN_PAGE = 200
MAX_RUN_RECORDS = 2000


def _workflow_runs(store, plan, repository):
    """Imported CI workflow runs tied to this operation, or unlinked runs for the repository revision its intent cites.

    A run linked to another operation belongs to that operation only. Runs are caller-asserted claims kept apart
    from the stages: an imported "success" never verifies delivery. They are optional evidence, so they are read in
    bounded pages, and a failure to read them is reported beside the stages, never instead of them. Returns the runs
    and how completely they were read.
    """
    from .io import AppError
    try:
        intent = (store.artifact(repository.get('repository_intent_id'), kind='repository_intent')
                  if repository.get('cited') else None)
        revision = intent['data'].get('source_revision') if intent else None
        rows, complete = [], False
        while len(rows) < MAX_RUN_RECORDS:
            page = store.artifacts(kind='workflow_run', object_id=plan['object_id'], limit=RUN_PAGE, offset=len(rows))
            rows.extend(page)
            if len(page) < RUN_PAGE:
                complete = True
                break
    except AppError as error:
        return [], {'status': 'unavailable', 'error_code': error.code}
    runs = []
    for row in rows:
        data = row['data']
        relation = ('related_operation' if data.get('related_operation') == plan['operation_id'] else
                    'cited_revision' if 'related_operation' not in data and revision
                    and data.get('repository_revision') == revision else None)
        if relation:
            runs.append({'relation': relation, 'workflow': data.get('workflow'), 'run_id': data.get('run_id'),
                         'status': data.get('status'), 'run_url': data.get('run_url'),
                         'repository_revision': data.get('repository_revision'), 'observed_at': data.get('observed_at'),
                         'artifact_id': row['artifact_id'], 'evidence_class': 'caller_asserted',
                         'external_execution_verified': False})
    read = {'status': 'complete' if complete else 'partial', 'records_read': len(rows)}
    if repository.get('context_changed'):
        # Without the bound citation the cited revision is unknown, so its runs cannot be matched.
        read['cited_revision'] = 'unknown'
    return runs, read


def _when(epoch):
    """A time for a sentence: to the second with its zone, as the stage lines give it."""
    from .io import readable_time
    return readable_time(_utc(epoch))


def _next_action(stages, operation_root, store_root):
    """The one step that moves the change forward, with the real paths. The review digest is never filled in: the
    engineer copies it from the review they approve."""
    approval, readback, reconciliation = stages['approval'], stages['readback'], stages['reconciliation']
    record, observed = stages['deployment_record'], stages['observed_after']
    operation, store = shlex.quote(str(operation_root)), shlex.quote(str(store_root))
    if approval['status'] == 'waiting' and stages['proposal'].get('context_changed'):
        return ('The context file this proposal bound changed after it was prepared, so execute refuses it '
                '(maintenance_source_changed); prepare a new proposal.')
    if approval['status'] == 'waiting':
        return ('Review the change (5), then approve it with execute %s EXACT_REVIEW_DIGEST before %s; the digest is the '
                'one on the review, never filled in for you.' % (operation, _when(approval['closes_at'])))
    if approval['status'] == 'expired':
        return 'The approval window closed at %s; prepare a new proposal from the current intent.' % _when(approval['closes_at'])
    if approval['status'] == 'clock_uncertain':
        return ("This host's clock reads earlier than a time this operation recorded, so execute holds it. Correct "
                'the clock and restart the workbench, or wait until the clock passes the recorded time; or prepare a '
                'new proposal.')
    if approval['status'] == 'clock_unreadable':
        return "This operation's recorded time cannot be read, so execute refuses it; prepare a new proposal."
    if approval['status'] == 'not_open':
        return ('The local clock reads earlier than this plan was prepared; approval is refused until it passes %s.'
                % _when(approval['opens_at']))
    if approval['status'] == 'rejected':
        return 'This operation was rejected; prepare a new proposal.'
    if reconciliation['status'] == 'required':
        return 'The outcome is unknown. Reconcile with reconcile %s before any retry; execution is never replayed.' % operation
    if 'pending' in (readback['status'], reconciliation['status']):
        return 'The service has not yet shown the change; reconcile again later with reconcile %s.' % operation
    if record['status'] == 'available':
        return ('Record the deployment: in the workspace, deployment-record %s %s (a lists it); from a shell, '
                'workbench deployment-record --root %s --operation %s --intent %s'
                % (operation, record['intent_id'], store, operation, record['intent_id']))
    if record['status'] == 'done' and record.get('context_changed'):
        return ('The deployment was recorded, but the context file this operation bound has changed since, so the '
                'record no longer passes its own check (the views reread those bytes); prepare a new proposal to '
                'record a baseline again.')
    if record['status'] == 'not_available' and record.get('reason') == 'context_changed':
        return ('The context file this operation bound changed after it was prepared, so it cannot become a deployment '
                'record; collect to observe the policy.')
    if record['status'] == 'not_available':
        # Reconcile's readback is said once, in its own stage above; this step names what follows from it.
        return ('This operation cannot become a deployment record because its own readback was never verified; '
                'collect to observe the policy.')
    if observed['status'] == 'not_yet':
        return 'Collect to observe the policy after the change.'
    if observed['status'] == 'differs':
        return 'The latest observation differs from the desired configuration; review the differences before any new change.'
    if observed['status'] == 'unknown':
        return 'The latest observation cannot be compared with this change; see the observed-after stage.'
    if record['status'] == 'done':
        return 'Nothing pending: the change is recorded and observed as desired.' + _stale_note(observed)
    if observed['status'] == 'not_applicable':
        return 'Nothing pending: the plan had no configuration change to dispatch.'
    return ('Nothing pending: the change is observed as desired; no repository intent was cited, so there is no deployment '
            'record.' + _stale_note(observed))


def _stale_note(observed):
    """A qualifier when the observation behind 'observed as desired' now reads stale; empty when it is fresh."""
    if observed.get('observation_freshness') in (None, 'fresh'):
        return ''
    words = {'stamped_after_now': "stamped after this host's clock", 'older_than_window': 'older than the freshness window',
             'later_collection_not_complete': 'a later collection did not complete', **CLOCK_HOLD_WORDS}
    held = clock_hold(observed.get('observation_freshness_reasons'))
    if held:
        # Unknown stays unknown: the age of this observation is not established, so the note does not say stale.
        causes = [CLOCK_HOLD_CAUSES[held]] + [words.get(item, str(item)) for item in observed.get('observation_freshness_reasons') or []
                                               if item not in CLOCK_HOLD_REASONS]
        return (' But the age of the observation that shows it is not known (%s); judge it again once its age is known.'
                % '; '.join(causes))
    reasons = '; '.join(words.get(item, str(item)) for item in observed.get('observation_freshness_reasons') or [])
    return (' But the observation that shows it now reads stale (%s); judge it again once a fresh observation exists.'
            % (reasons or 'no reason recorded'))


def _history(journal, records):
    """The journal's events in their chained order, each with what it recorded, and when the store registered it.

    The journal records no times. After each engine action the store registers the journal's status with the
    journal's digest. A registration is paired with an event only when the journal cut after that event, carrying
    the registered status, has exactly the registered digest; every other event's time stays unrecorded.
    """
    from .io import digest
    paired = {}
    for record in records:
        for count in range(1, len(journal['events']) + 1):
            state = dict(journal, status=record.get('status'), events=journal['events'][:count])
            if digest(state) == record.get('journal_sha256'):
                paired.setdefault(count - 1, record)
                break
    events = [{'sequence': event['sequence'], 'kind': event['kind'],
               'fields': {key: value for key, value in event.items() if key not in ('sequence', 'kind', 'previous_sha256')},
               'store_status': paired[index]['status'] if index in paired else None,
               'store_recorded_at': paired[index]['recorded_at'] if index in paired else None}
              for index, event in enumerate(journal['events'])]
    return {'events': events, 'chain': 'verified when the operation was loaded', 'registrations': len(records),
            'paired': len(paired)}


def deployment_stage(operation_root):
    """The deployment-record stage of one operation, exactly as Delivery shows it; for the guided action."""
    from . import maintenance
    review = maintenance.review(operation_root)
    _, plan, journal, _, _ = maintenance._load(review['operation_root'])
    return _deployment(maintenance._store(plan['store_root']), plan, journal, review['repository'])


def delivery(operation_root, *, now=None):
    """The delivery stages of one maintenance operation; read-only."""
    from . import maintenance
    from .io import digest
    review = maintenance.review(operation_root)
    root, plan, journal, desired, request = maintenance._load(review['operation_root'])
    if digest(plan) != review['approval_digest']:
        maintenance._fail('maintenance_evidence_changed')
    judged = review.get('approval_window') if isinstance(review.get('approval_window'), dict) else {}
    if now is None:
        # The window's effective time, as execute judges it.
        now = judged['judged_at'] if isinstance(judged.get('judged_at'), (int, float)) else time.time()
    elif judged.get('state') not in ('closed_recorded', 'unknown'):
        # A caller's own now judges the window; only durable records still apply.
        judged = {}
    store = maintenance._store(plan['store_root'])
    records = [record for record in store.operations(object_id=plan['object_id'])
               if record['operation_id'] == plan['operation_id']]
    times = {}
    for record in records:
        times.setdefault(record['status'], record['recorded_at'])
    repository = review['repository']
    stages = [
        {'stage': 'proposal', 'status': 'done', 'recorded_at': times.get('prepared'), 'object_id': plan['object_id'],
         'desired_sha256': plan['desired_sha256'], 'repository_intent_id': repository.get('repository_intent_id'),
         'intent_freshness': repository.get('freshness') if repository.get('cited') else None,
         **({'context_changed': True} if repository.get('context_changed') else {})},
        {'stage': 'review', 'status': 'done', 'changes': plan['changes'], 'no_configuration_change': review['no_configuration_change'],
         'field_changes': review['field_changes'], 'approval_digest': review['approval_digest'],
         'saved_plan_sha256': review['saved_plan_sha256']},
        _approval(journal, request, now, judged),
        _execution(journal, times),
        _readback(root, journal),
        _reconciliation(root, journal, times),
        _deployment(store, plan, journal, repository),
        _observed_after(store, plan, desired, journal),
    ]
    named = {stage['stage']: stage for stage in stages}
    runs, runs_read = _workflow_runs(store, plan, repository)
    return {'schema_version': VERSION, 'operation_id': plan['operation_id'], 'operation_root': str(root),
            'tenant_id': plan['tenant_id'], 'object_id': plan['object_id'], 'journal_status': journal['status'],
            'stages': stages, 'next_action': _next_action(named, root, plan['store_root']), 'viewed_at': _utc(now) if now >= 0 else None,
            'workflow_runs': runs, 'workflow_runs_read': runs_read, 'history': _history(journal, records),
            'evidence_class': review['evidence_class'], 'native_provider_qualified': False,
            'execution_authorized': False, 'cloud_authority': False}
