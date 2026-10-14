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
import time

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


def _approval(journal, request, now):
    window = {'opens_at': request['created_at'], 'closes_at': request['expires_at']}
    dispatches = _events(journal, 'dispatch_started')
    if dispatches:
        return {'stage': 'approval', 'status': 'done', 'approval_digest': dispatches[0].get('approval_digest'), **window}
    if journal['status'] == 'rejected':
        return {'stage': 'approval', 'status': 'rejected', **window}
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
    return {'stage': 'execution', 'status': 'done' if _events(journal, 'verified') else 'unknown',
            'engine_status': result.get('status'), 'service_status': response.get('status'),
            'mutation_dispatched': bool(responses), 'no_change_dispatch': bool(_events(journal, 'service_no_change')),
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
                'platform_qualified': latest.get('platform_qualified')}
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
    return {'stage': 'observed_after', 'status': status, 'field_changes': changes, **found}


def _workflow_runs(store, plan, repository):
    """Imported CI workflow runs tied to this operation, or unlinked runs for the repository revision its intent cites.

    A run linked to another operation belongs to that operation only. Runs are caller-asserted claims kept apart
    from the stages: an imported "success" never verifies delivery.
    """
    revision = None
    if repository.get('cited'):
        rows = [row for row in store.artifacts(kind='repository_intent') if row['artifact_id'] == repository.get('repository_intent_id')]
        revision = rows[0]['data'].get('source_revision') if len(rows) == 1 else None
    runs = []
    for row in store.artifacts(kind='workflow_run', object_id=plan['object_id']):
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
    return runs


def _next_action(stages):
    approval, readback, reconciliation = stages['approval'], stages['readback'], stages['reconciliation']
    record, observed = stages['deployment_record'], stages['observed_after']
    if approval['status'] == 'waiting':
        return ('Review the change, then approve it with execute OPERATION_DIR EXACT_REVIEW_DIGEST before %s.'
                % _utc(approval['closes_at']))
    if approval['status'] == 'expired':
        return 'The approval window closed at %s; prepare a new proposal from the current intent.' % _utc(approval['closes_at'])
    if approval['status'] == 'not_open':
        return ('The local clock reads earlier than this plan was prepared; approval is refused until it passes %s.'
                % _utc(approval['opens_at']))
    if approval['status'] == 'rejected':
        return 'This operation was rejected; prepare a new proposal.'
    if reconciliation['status'] == 'required':
        return 'The outcome is unknown. Reconcile with reconcile OPERATION_DIR before any retry; execution is never replayed.'
    if 'pending' in (readback['status'], reconciliation['status']):
        return 'The service has not yet shown the change; reconcile again later with reconcile OPERATION_DIR.'
    if record['status'] == 'available':
        return 'Record the deployment: workbench deployment-record --root STORE --operation OPERATION_DIR --intent %s' % record['intent_id']
    if record['status'] == 'not_available':
        return ('Reconciled as %s. This operation cannot become a deployment record because its own readback was never '
                'verified; collect to observe the policy.' % reconciliation.get('classification'))
    if observed['status'] == 'not_yet':
        return 'Collect to observe the policy after the change.'
    if observed['status'] == 'differs':
        return 'The latest observation differs from the desired configuration; review the differences before any new change.'
    if observed['status'] == 'unknown':
        return 'The latest observation cannot be compared with this change; see the observed-after stage.'
    if record['status'] == 'done':
        return 'Nothing pending: the change is recorded and observed as desired.'
    if observed['status'] == 'not_applicable':
        return 'Nothing pending: the plan had no configuration change to dispatch.'
    return 'Nothing pending: the change is observed as desired; no repository intent was cited, so there is no deployment record.'


def delivery(operation_root, *, now=None):
    """The delivery stages of one maintenance operation; read-only."""
    from . import maintenance
    from .io import digest
    review = maintenance.review(operation_root)
    root, plan, journal, desired, request = maintenance._load(review['operation_root'])
    if digest(plan) != review['approval_digest']:
        maintenance._fail('maintenance_evidence_changed')
    now = time.time() if now is None else now
    store = maintenance._store(plan['store_root'])
    times = {}
    for record in store.operations(object_id=plan['object_id']):
        if record['operation_id'] == plan['operation_id']:
            times.setdefault(record['status'], record['recorded_at'])
    repository = review['repository']
    stages = [
        {'stage': 'proposal', 'status': 'done', 'recorded_at': times.get('prepared'), 'object_id': plan['object_id'],
         'desired_sha256': plan['desired_sha256'], 'repository_intent_id': repository.get('repository_intent_id'),
         'intent_freshness': repository.get('freshness') if repository.get('cited') else None},
        {'stage': 'review', 'status': 'done', 'changes': plan['changes'], 'no_configuration_change': review['no_configuration_change'],
         'field_changes': review['field_changes'], 'approval_digest': review['approval_digest'],
         'saved_plan_sha256': review['saved_plan_sha256']},
        _approval(journal, request, now),
        _execution(journal, times),
        _readback(root, journal),
        _reconciliation(root, journal, times),
        _deployment(store, plan, journal, repository),
        _observed_after(store, plan, desired, journal),
    ]
    named = {stage['stage']: stage for stage in stages}
    return {'schema_version': VERSION, 'operation_id': plan['operation_id'], 'operation_root': str(root),
            'tenant_id': plan['tenant_id'], 'object_id': plan['object_id'], 'journal_status': journal['status'],
            'stages': stages, 'next_action': _next_action(named), 'viewed_at': _utc(now) if now >= 0 else None,
            'workflow_runs': _workflow_runs(store, plan, repository),
            'evidence_class': review['evidence_class'], 'native_provider_qualified': False,
            'execution_authorized': False, 'cloud_authority': False}
