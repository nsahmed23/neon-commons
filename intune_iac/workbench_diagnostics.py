"""Diagnostics: what needs attention for one policy, as observed facts with their evidence and next step.

Read-only. It composes what the store, the operation journals, the recorded
repository intent and the imported device evidence already say. Each signal
separates the observed fact and its evidence from the next step; nothing is
inferred beyond the records, and no hypothesis is presented as a conclusion.
Areas with nothing to report are listed as checked, so silence is never
mistaken for "not looked at".
"""
from __future__ import annotations

VERSION = 'workbench-diagnostics/1'
AREAS = ('collection', 'freshness', 'operations', 'repository', 'device_evidence')
MAX_OPERATIONS = 50


def _signal(area, code, observed, next_step, evidence=None):
    return {'area': area, 'code': code, 'observed': observed, 'evidence': evidence or {}, 'next_step': next_step}


def _collection(store, observed):
    overview = store.overview(limit=1)
    attempt = overview.get('last_attempt') if isinstance(overview.get('last_attempt'), dict) else None
    success = overview.get('last_success') if isinstance(overview.get('last_success'), dict) else None
    if attempt is None or attempt.get('status') == 'complete':
        return [], False
    kept = ' The store keeps the last good observation (run %s), now marked %s.' % (
        success.get('run_id'), observed.get('freshness')) if success and overview.get('retained_last_good') else ''
    return [_signal('collection', 'collection_failed',
                    'The last collection (run %s, %s) ended %s: %s.%s' % (attempt.get('run_id'), attempt.get('completed_at') or attempt.get('started_at'),
                                                                   attempt.get('status'), attempt.get('error_code') or 'no error recorded', kept),
                    'Collect again when the source is reachable; until then every view uses the last-good observation, labelled stale.',
                    {'run_id': attempt.get('run_id'), 'status': attempt.get('status'), 'error_code': attempt.get('error_code'),
                     'last_success_run_id': success.get('run_id') if success else None})], True


def _operations(store, object_id):
    from . import maintenance
    latest = {}
    for record in store.operations(object_id=object_id):
        latest[record['operation_id']] = record
    signals = []
    for record in list(latest.values())[-MAX_OPERATIONS:]:
        root, status = record.get('operation_root'), record.get('status')
        evidence = {'operation_id': record['operation_id'], 'operation_root': root, 'status': status, 'recorded_at': record.get('recorded_at')}
        if status not in ('outcome_unknown', 'reconciled'):
            continue
        try:
            _, _, journal, _, _ = maintenance._load(root)
        except Exception as error:
            signals.append(_signal('operations', 'operation_unreadable',
                                   'Operation %s is recorded as %s, but its journal cannot be read: %s.' % (record['operation_id'], status, getattr(error, 'code', 'unreadable')),
                                   'Preserve the operation directory and inspect it; nothing is replayed.', evidence))
            continue
        events = journal['events']
        if journal['status'] == 'outcome_unknown':
            uncertain = [event for event in events if event['kind'] == 'uncertain']
            code = uncertain[-1].get('error_code') if uncertain else 'no error recorded'
            signals.append(_signal('operations', 'operation_outcome_unknown',
                                   'Operation %s was dispatched and its outcome is unknown: %s.' % (record['operation_id'], code),
                                   'reconcile %s reads the service independently; execution is never replayed.' % root,
                                   dict(evidence, error_code=code)))
        elif journal['status'] == 'reconciled':
            reconciled = [event for event in events if event['kind'] == 'reconciled']
            classification = reconciled[-1].get('classification') if reconciled else None
            if classification == 'diverged':
                signals.append(_signal('operations', 'operation_diverged',
                                       'Operation %s was reconciled and the service matches neither the plan nor its starting point.' % record['operation_id'],
                                       'Review the latest observation against the desired body before any new change.',
                                       dict(evidence, classification=classification)))
    return signals


def _repository(store, object_id):
    from .io import AppError
    from .workbench_repository import intent_freshness, latest_intent
    try:
        intent = latest_intent(store, object_id)
    except AppError as error:
        if error.code == 'workbench_repository_intent_missing':
            return [], 'not_recorded'
        return [_signal('repository', error.code, 'The repository intent cannot be chosen: %s.' % error.code,
                        'Import or refresh one repository scope explicitly with repository-import.')], 'attention'
    freshness = intent_freshness(intent['data'])
    evidence = {'repository_intent_id': intent['artifact_id'], 'scope': intent['data'].get('scope')}
    if freshness['status'] == 'stale':
        sources = freshness.get('sources') or {}
        return [_signal('repository', 'repository_stale',
                        'The repository changed since its recorded intent: %s.' % ', '.join(
                            '%s %s' % (kind, ', '.join(sources.get(kind) or [])) for kind in ('changed', 'added', 'removed') if sources.get(kind)),
                        'Review the difference on the Repository surface, then repository-refresh REVISION records the current source.',
                        dict(evidence, **{kind: sources.get(kind) or [] for kind in ('changed', 'added', 'removed')}))], 'attention'
    if freshness['status'] == 'unavailable':
        return [_signal('repository', 'repository_unavailable',
                        'The recorded repository cannot be resolved now: %s.' % freshness.get('reason', 'unknown'),
                        'Restore the repository, or import it again with repository-import.', evidence)], 'attention'
    return [], 'clear'


def _device_evidence(store, object_id):
    from .workbench_health import device_health
    health = device_health(store, object_id)
    if health.get('as_of') is None:
        return [], 'not_imported'
    signals = []
    capture = health.get('capture') if isinstance(health.get('capture'), dict) else {}
    evidence = {'artifact_id': health.get('artifact_id'), 'as_of': health.get('as_of'), 'source_sha256': health.get('source_sha256')}
    if capture.get('truncated') or capture.get('access_errors'):
        parts = (['the capture was truncated'] if capture.get('truncated') else []) + [
            'access error: %s' % error for error in capture.get('access_errors') or []]
        signals.append(_signal('device_evidence', 'device_capture_incomplete',
                               'The imported device evidence is incomplete: %s.' % '; '.join(parts),
                               'Treat missing devices as unknown, not as failures; import a complete capture before judging rollout.',
                               dict(evidence, truncated=bool(capture.get('truncated')), access_errors=list(capture.get('access_errors') or []))))
    if health.get('membership_conflicts'):
        signals.append(_signal('device_evidence', 'device_membership_conflicts',
                               '%d targeted devices are also excluded or not eligible.' % len(health['membership_conflicts']),
                               'Resolve the cohort membership before reading success rates.', dict(evidence, devices=health['membership_conflicts'][:20])))
    return signals, 'attention' if signals else 'clear'


def diagnostics(store, object_id):
    """What needs attention for one policy; read-only."""
    observed = store.inspect(object_id)
    signals = []
    checked = dict.fromkeys(AREAS, 'clear')
    collection, failed = _collection(store, observed)
    signals += collection
    if collection:
        checked['collection'] = 'attention'
    if observed.get('freshness') != 'fresh':
        # A failed collection already explains a retained last-good observation; say it once.
        checked['freshness'] = 'explained_by_collection' if failed else 'attention'
        if not failed:
            signals.append(_signal('freshness', 'observation_stale',
                                   'The newest observation (%s) is %s.' % (observed.get('observed_at'), observed.get('freshness')),
                                   'Collect again before preparing or judging a change.',
                                   {'snapshot_id': observed.get('snapshot_id'), 'observed_at': observed.get('observed_at')}))
    operations = _operations(store, object_id)
    signals += operations
    if operations:
        checked['operations'] = 'attention'
    repository, checked['repository'] = _repository(store, object_id)
    signals += repository
    device, checked['device_evidence'] = _device_evidence(store, object_id)
    signals += device
    return {'schema_version': VERSION, 'object_id': object_id, 'name': observed.get('name'), 'signals': signals,
            'checked': checked, 'limitations': [
                'Read from local records only; nothing was collected, reconciled or refreshed to produce this view.',
                'Synthetic and caller-asserted evidence stays labelled as such in each source record.'],
            'execution_authorized': False, 'cloud_authority': False}
