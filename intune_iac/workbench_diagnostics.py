"""Diagnostics: what needs attention for one policy, as observed facts with their evidence and next step.

Read-only. It composes what the store, the operation journals, the recorded
repository intent and the imported device evidence already say. Each signal
separates the observed fact and its evidence from the next step; nothing is
inferred beyond the records, and no hypothesis is presented as a conclusion.
Areas with nothing to report are listed as checked, so silence is never
mistaken for "not looked at"; an area that could not be read, or was read only
up to its bound, says so instead of reading as clear.
"""
from __future__ import annotations

import shlex

VERSION = 'workbench-diagnostics/1'
AREAS = ('collection', 'freshness', 'operations', 'repository', 'device_evidence')
OPERATION_PAGE = 200
MAX_OPERATION_RECORDS = 5000
MAX_JOURNALS = 200
# Store statuses whose journal is read. A stop between the journal's dispatch_started and the
# store's registration leaves the store at prepared while the journal says outcome_unknown.
JOURNAL_CHECKED = ('prepared', 'outcome_unknown', 'reconciled')
UNAVAILABLE_STEPS = {'workbench_query_limit': 'too many records for one bounded read; the records themselves are intact.'}


def _signal(area, code, observed, next_step, evidence=None):
    return {'area': area, 'code': code, 'observed': observed, 'evidence': evidence or {}, 'next_step': next_step}


def _collection(observed):
    """This policy's own collection attempts, as inspect reports them; never the estate's newest run."""
    attempt = observed.get('last_attempt') if isinstance(observed.get('last_attempt'), dict) else None
    success = observed.get('last_success') if isinstance(observed.get('last_success'), dict) else None
    if attempt is None or attempt.get('status') == 'complete':
        return [], False
    from .io import readable_time
    # Sentences give times to the second with their zone; the exact values stay here, in the evidence.
    evidence = {'run_id': attempt.get('run_id'), 'status': attempt.get('status'), 'error_code': attempt.get('error_code'),
                'last_success_run_id': success.get('run_id') if success else None,
                'started_at': attempt.get('started_at'), 'completed_at': attempt.get('completed_at')}
    if attempt.get('status') == 'collecting':
        return [_signal('collection', 'collection_not_finished',
                        'Collection run %s for this policy started at %s and has not recorded an end.' % (
                            attempt.get('run_id'), readable_time(attempt.get('started_at')) or 'a time not recorded'),
                        'If no collector is running now, the run was interrupted: collect again (:collect).', evidence)], False
    kept = (' The last-good observation of this policy (run %s) is kept, now marked %s.' % (
        success.get('run_id'), observed.get('freshness')) if success and observed.get('retained_last_good') else '')
    # The observed sentence already says the last-good observation is kept and how it is labelled.
    step = ('Collect again (:collect) when the source is reachable.' if kept else
            'Collect again (:collect) when the source is reachable; until then views use the last-good observation of this policy '
            '(run %s), labelled %s.' % (success.get('run_id'), observed.get('freshness')) if success else
            'Collect again (:collect) when the source is reachable; no complete observation of this policy exists yet.')
    return [_signal('collection', 'collection_failed',
                    'The last collection of this policy (run %s, %s) ended %s: %s.%s' % (
                        attempt.get('run_id'), readable_time(attempt.get('completed_at') or attempt.get('started_at'))
                        or 'time not recorded',
                        attempt.get('status'), attempt.get('error_code') or 'no error recorded', kept),
                    step, evidence)], True


# The store's own reasons for a stale observation, in words. A later incomplete collection is explained by the
# collection signal itself, so it never reaches the freshness sentence.
FRESHNESS_WORDS = {'older_than_window': 'older than the freshness window of %(window)s seconds',
                   'stamped_after_now': "stamped later than this host's clock read when it was checked (%(checked)s)"}


def _freshness(observed, failed):
    if observed.get('freshness') == 'fresh':
        return [], 'clear'
    # A failed collection already explains a retained last-good observation; say it once.
    if failed:
        return [], 'explained_by_collection'
    reasons = [reason for reason in observed.get('freshness_reasons') or [] if reason in FRESHNESS_WORDS]
    from .io import readable_time
    because = '; '.join(FRESHNESS_WORDS[reason] % {'window': observed.get('freshness_window_seconds'),
                                                   'checked': readable_time(observed.get('freshness_checked_at'))}
                        for reason in reasons)
    sentence = ('The newest observation (%s) is %s%s.' % (readable_time(observed['observed_at']), observed.get('freshness'),
                                                         ': ' + because if because else '')
                if observed.get('observed_at') else
                'No complete observation of this policy exists yet (freshness %s).' % observed.get('freshness'))
    step = 'Collect again (:collect) before preparing or judging a change.'
    replaces = observed.get('next_collection_replaces')
    if 'stamped_after_now' in reasons and replaces == 'same_service':
        # The store orders its own collections from one service by run, not by stamp (workbench_store).
        step = ('Collect again (:collect) from the modeled service it came from (%s): the store orders its own '
                'collections by run, so the new one becomes current. Or correct the host clock.'
                % observed.get('ordering_service_root'))
    elif 'stamped_after_now' in reasons and replaces == 'any_collection':
        step = ('Collect again (:collect): this capture was stamped later than the store\'s clock when it was '
                'imported, so the next collection becomes current. Or correct the host clock.')
    elif 'stamped_after_now' in reasons:
        # An imported capture is ordered by its capture time, so a new collection would not replace it.
        step = ("It stays stale until this host's clock passes %s; collecting again now would not replace it as the "
                'newest. Wait, or correct the host clock.' % readable_time(observed.get('observed_at')))
    return [_signal('freshness', 'observation_stale', sentence, step,
                    {'snapshot_id': observed.get('snapshot_id'), 'observed_at': observed.get('observed_at'),
                     'freshness_checked_at': observed.get('freshness_checked_at'), 'freshness_reasons': reasons,
                     'next_collection_replaces': replaces,
                     'ordering_service_root': observed.get('ordering_service_root')})], 'attention'


def _operation_records(store, object_id):
    """Every operation record for the object, read in bounded pages; False when the bound stopped the read."""
    records = []
    while len(records) < MAX_OPERATION_RECORDS:
        page = store.operations(object_id=object_id, limit=OPERATION_PAGE, offset=len(records))
        records.extend(page)
        if len(page) < OPERATION_PAGE:
            return records, True
    return records, False


def unknown_outcome_words(code):
    """An unknown outcome's recorded error in words where they are known, the code kept in brackets."""
    from .workbench_screens import EXECUTION_ERROR_WORDS
    return '%s (%s)' % (EXECUTION_ERROR_WORDS[code], code) if code in EXECUTION_ERROR_WORDS else str(code)


def _newest_operation(records):
    """The policy's newest operation as its records and journal say: store status, journal status, readback.

    The store registers an operation again at each later event (a refused execute, a reconcile), so the newest is
    the one whose first registration is the latest (the one prepared last), in the state of its latest
    registration; a later event on an older operation does not make that one the newest.
    """
    from . import maintenance
    if not records:
        return None
    first, latest = {}, {}
    for position, item in enumerate(records):
        first.setdefault(item['operation_id'], position)
        latest[item['operation_id']] = item
    record = latest[max(first, key=first.get)]
    state = {'operation_id': record['operation_id'], 'status': record.get('status'), 'journal_status': None,
             'classification': None, 'recorded_at': record.get('recorded_at'), 'operation_root': record.get('operation_root')}
    try:
        _, _, journal, _, _ = maintenance._load(record.get('operation_root'))
    except Exception:
        return state
    reconciled = [event for event in journal['events'] if event['kind'] == 'reconciled']
    state.update(journal_status=journal['status'],
                 classification=reconciled[-1].get('classification') if reconciled else None)
    if journal['status'] == 'prepared':
        # The approval window as execute would judge it now (the one rule, read-only; nothing is recorded).
        try:
            root, _, _, _, request = maintenance._load(record.get('operation_root'))
            state['approval_window'] = maintenance.approval_window(root, request)['state']
        except Exception:
            state['approval_window'] = 'unknown'
    return state


def _operations(store, object_id, newest=None):
    from . import maintenance
    records, complete = _operation_records(store, object_id)
    newest_state = _newest_operation(records)
    if newest is not None:
        # The newest record, read in the same pass, for the Inspector's operation state.
        newest['operation'] = newest_state
    latest = {}
    for position, record in enumerate(records):
        latest[record['operation_id']] = (position, record)
    # Newest first, so a bound leaves out the oldest operations, never the newest.
    candidates = [record for _, record in sorted(latest.values(), key=lambda item: item[0], reverse=True)
                  if record.get('status') in JOURNAL_CHECKED]
    complete = complete and len(candidates) <= MAX_JOURNALS
    signals = []
    for record in candidates[:MAX_JOURNALS]:
        root, status = record.get('operation_root'), record.get('status')
        evidence = {'operation_id': record['operation_id'], 'operation_root': root, 'status': status,
                    'recorded_at': record.get('recorded_at')}
        try:
            _, _, journal, _, _ = maintenance._load(root)
        except Exception as error:
            # A prepared proposal whose directory was removed was never dispatched; nothing to report.
            if status != 'prepared':
                signals.append(_signal('operations', 'operation_unreadable',
                                       'Operation %s is recorded as %s, but its journal cannot be read: %s.' % (
                                           record['operation_id'], status, getattr(error, 'code', 'unreadable')),
                                       'Preserve the operation directory and inspect it; nothing is replayed.', evidence))
            continue
        journal_status, events = journal['status'], journal['events']
        evidence['journal_status'] = journal_status
        if journal_status == 'outcome_unknown':
            uncertain = [event for event in events if event['kind'] == 'uncertain']
            code = uncertain[-1].get('error_code') if uncertain else 'no error recorded'
            observed = ('Operation %s was dispatched and its outcome is unknown: %s.' % (record['operation_id'],
                                                                                      unknown_outcome_words(code))
                        if status != 'prepared' else
                        'Operation %s started dispatch (its journal records dispatch_started), but the result was never '
                        'registered: the store still says prepared.' % record['operation_id'])
            signals.append(_signal('operations', 'operation_outcome_unknown', observed,
                                   'reconcile %s reads the service independently; execution is never replayed.'
                                   % shlex.quote(str(root)), dict(evidence, error_code=code)))
        elif journal_status != status:
            signals.append(_signal('operations', 'operation_record_disagrees',
                                   'Operation %s: its journal says %s, but the store record says %s.' % (
                                       record['operation_id'], journal_status, status),
                                   "The journal is the operation's own record and Delivery (v) reads it; preserve the "
                                   'operation directory.', evidence))
        elif journal_status == 'reconciled':
            reconciled = [event for event in events if event['kind'] == 'reconciled']
            classification = reconciled[-1].get('classification') if reconciled else None
            if classification == 'diverged':
                signals.append(_signal('operations', 'operation_diverged',
                                       'Operation %s was reconciled and the service matches neither the plan nor its starting point.' % record['operation_id'],
                                       'Review the latest observation against the desired body before any new change.',
                                       dict(evidence, classification=classification)))
    # A prepared proposal whose approval execute would hold now: the engineer meets the hold only on submitting,
    # unless it is said here (journey 28 run 3: Delivery said held while this area read clear).
    window = (newest_state or {}).get('approval_window')
    if window in ('clock_moved_backward', 'unknown'):
        why = ("this host's clock reads earlier than a time the operation recorded, so whether its approval window "
               'is still open cannot be established' if window == 'clock_moved_backward' else
               "the operation's recorded time cannot be read, so its approval window cannot be judged")
        signals.append(_signal('operations', 'operation_approval_held',
                               'Operation %s is prepared, but execute would hold it now: %s.' % (
                                   newest_state['operation_id'], why),
                               'Correct the host clock, or wait until it reads at or after the recorded time, then '
                               'execute again; a new proposal also works (a lists it).',
                               {'operation_id': newest_state['operation_id'],
                                'operation_root': newest_state.get('operation_root'), 'approval_window': window}))
    return signals, complete


def _repository(store, object_id):
    from .io import AppError
    from .workbench_repository import intent_freshness, latest_intent
    try:
        intent = latest_intent(store, object_id)
    except AppError as error:
        if error.code == 'workbench_repository_intent_missing':
            return [], 'not_recorded'
        if error.code == 'workbench_repository_scope_ambiguous':
            return [_signal('repository', error.code,
                            'Intents for this policy come from more than one repository scope. Status, refresh and proposals '
                            'refuse it, and a further import does not resolve this in this store.',
                            'Keep one repository as the source of this policy; choosing between recorded scopes is not '
                            'supported yet. :repository-entry REPOSITORY shows where a policy is already recorded.')], 'attention'
        raise
    freshness = intent_freshness(intent['data'])
    evidence = {'repository_intent_id': intent['artifact_id'], 'scope': intent['data'].get('scope')}
    signals = []
    if freshness['status'] == 'stale':
        sources = freshness.get('sources') or {}
        signals.append(_signal('repository', 'repository_stale',
                               'The repository changed since its recorded intent: %s.' % ', '.join(
                                   '%s %s' % (kind, ', '.join(sources.get(kind) or [])) for kind in ('changed', 'added', 'removed') if sources.get(kind)),
                               'Review the difference on the Repository surface, then repository-refresh REVISION records the current source.',
                               dict(evidence, **{kind: sources.get(kind) or [] for kind in ('changed', 'added', 'removed')})))
    elif freshness['status'] == 'unavailable':
        return [_signal('repository', 'repository_unavailable',
                        'The recorded repository cannot be resolved now: %s.' % freshness.get('reason', 'unknown'),
                        'Restore the repository, or import it again with repository-import.', evidence)], 'attention'
    consumer = freshness.get('consumer') or {}
    recorded = intent['data'].get('consumer') or {}
    # The component as it is now decides; a mismatch recorded on a still-current intent is the same component.
    if consumer.get('status') == 'mismatch' or (freshness['status'] == 'current' and recorded.get('status') == 'mismatch'):
        reasons = consumer.get('reasons') or recorded.get('reasons') or []
        signals.append(_signal('repository', 'repository_consumer_mismatch',
                               'The component does not consume exactly this policy: %s.' % ', '.join(reasons or ['reason not recorded']),
                               'Proposals and execution refuse this intent until the component consumes exactly this policy; '
                               'fix the component, then repository-refresh REVISION.', dict(evidence, reasons=reasons)))
    return signals, 'attention' if signals else 'clear'


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


def _area(signals, checked, area, read):
    """Read one area; one that cannot be read is reported as such, and the other areas still show."""
    from .io import AppError
    try:
        found, state = read()
    except AppError as error:
        found, state = [_signal(area, area + '_unavailable', 'This area could not be read: %s.' % error.code,
                                'The rest of this view is unaffected; ' + UNAVAILABLE_STEPS.get(
                                    error.code, 'the engine message names the cause.'), {'error_code': error.code})], 'unavailable'
    signals.extend(found)
    checked[area] = state


def diagnostics(store, object_id):
    """What needs attention for one policy; read-only."""
    observed = store.inspect(object_id)
    checked = dict.fromkeys(AREAS, 'clear')
    signals, failed = _collection(observed)
    checked['collection'] = 'attention' if signals else 'clear'
    # A failed collection, or one with no end, already explains a kept observation; its one step says collect again.
    unfinished = any(signal.get('code') == 'collection_not_finished' for signal in signals)
    found, checked['freshness'] = _freshness(observed, failed or unfinished)
    signals += found
    limitations = ['Read from local records only; nothing was collected, reconciled or refreshed to produce this view.',
                   'Synthetic and caller-asserted evidence stays labelled as such in each source record.']

    newest = {}

    def operations():
        found, complete = _operations(store, object_id, newest)
        if not complete:
            limitations.append('Operation records for this policy exceed the read bound; the oldest were not checked.')
        # An incomplete read stays partly checked even when it found something: what it did not read is unknown.
        return found, 'partly_checked' if not complete else 'attention' if found else 'clear'

    _area(signals, checked, 'operations', operations)
    _area(signals, checked, 'repository', lambda: _repository(store, object_id))
    _area(signals, checked, 'device_evidence', lambda: _device_evidence(store, object_id))
    return {'schema_version': VERSION, 'object_id': object_id, 'name': observed.get('name'), 'signals': signals,
            'checked': checked, 'limitations': limitations, 'newest_operation': newest.get('operation'),
            'execution_authorized': False, 'cloud_authority': False}
