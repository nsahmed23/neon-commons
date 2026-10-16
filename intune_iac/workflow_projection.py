"""The workflow map's projection: one selected policy's change path as fixed stages, each with a recorded basis.

Pure. The read model's own values go in (the Inspector's states, its diagnostics and proposal check, the policy's adoption
records and, for its newest operation, that operation's review and delivery); one projection comes out. Nothing here asks
the engine, opens a file, decides what may be done or invents a step: a stage's state is read from a named record and
field (its `basis`), its `reason` is a code those records hold, and its `continuation` is the one step the existing
screens already give for that state (`lifecycle_next`, the reconcile step, Delivery's own next step, the recorded
diagnostics step), never a sentence written here.

Rules the stages keep:
  * No state without a recorded basis. An absent record is `not_recorded`, never "not started".
  * An unknown outcome is never `done`.
  * A stale observation and a changed repository intent are two stages with two states.
  * The reconcile stage is a branch of readback. It is always in the list (so a drawing never changes shape with a state)
    and is `not_applicable` unless the operation's outcome was unknown or it was reconciled.
  * `position` is the last stage, in order, that has a recorded state: where the records say the policy has got to.

The revision is the digest of the projection's canonical form, so it changes exactly when a stage, a basis, a reason, a
recorded fact or a step changes; it does not change with the clock reading of a later read of the same records.
"""
from __future__ import annotations

import hashlib
import json

from .io import AppError

SCHEMA = 'workflow-map/1'
# The fixed stage ids, in order. `reconcile` is a branch of `readback`.
STAGE_IDS = ('observe', 'adopt', 'intent', 'propose', 'review', 'approve_execute', 'readback', 'reconcile', 'record',
             'observed_after', 'maintain')
BRANCH_OF = {'reconcile': 'readback'}
# The closed set of states. Each is a statement about a record, never a guess.
STATES = ('done', 'current', 'waiting', 'blocked', 'refused', 'unknown', 'not_recorded', 'not_applicable')
# A state with no recorded stage behind it; the position is the last stage that has neither.
NOT_REACHED = ('not_recorded', 'not_applicable')
# The surface Enter opens for a stage: a tab number as its key says it, or v for Delivery. Stages read from an operation
# open nothing while the policy has none.
OPENS = {'observe': '2', 'adopt': '3', 'intent': '9', 'propose': '5', 'review': '5', 'approve_execute': 'v',
         'readback': 'v', 'reconcile': 'v', 'record': 'v', 'observed_after': 'v', 'maintain': '7'}
OPERATION_STAGES = ('approve_execute', 'readback', 'reconcile', 'record', 'observed_after')
# The recorded diagnostics code behind each repository intent status that is not current.
INTENT_REASONS = {'changed': 'repository_stale', 'consumer_changed': 'repository_consumer_mismatch',
                  'unreadable': 'repository_unavailable'}
OBSERVATION_SIGNALS = ('collection_failed', 'collection_not_finished', 'observation_stale')
REPOSITORY_SIGNALS = ('repository_stale', 'repository_consumer_mismatch', 'repository_unavailable',
                      'workbench_repository_scope_ambiguous')


def _fail(message):
    raise AppError('workflow_projection_invalid', message)


def _dict(value):
    return value if isinstance(value, dict) else {}


def _text(value):
    return value if isinstance(value, str) and value else None


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False, default=str)


def _facts(source, names):
    """The recorded values a stage shows beside its state: the named fields of one record, those it holds."""
    return {name: source[name] for name in names if source.get(name) is not None}


def _row(state, basis, reason=None, facts=None):
    return {'state': state, 'basis': basis, 'reason': reason, 'facts': facts or {}}


# ---- the stages that read the policy's own records -------------------------------------------------------------------

def _observe(states, service_checked=None):
    from .workbench_diagnostics import clock_hold
    observation = states.get('observation')
    if not isinstance(observation, dict):
        return _row('not_recorded', 'states.observation')
    reasons = [item for item in observation.get('freshness_reasons') or [] if isinstance(item, str)]
    facts = _facts(observation, ('run_id', 'observed_at', 'coverage', 'freshness'))
    if isinstance(service_checked, bool):
        # Without a modeled service only the age is judged: a source that moved on is not known, so it is not claimed.
        facts['proposal_check'] = 'made against the service' if service_checked else 'not made: no service root'
    freshness = observation.get('freshness')
    if freshness == 'fresh':
        # Fresh by age is not current: the source can have moved on since (the proposal's own check says so).
        eligibility = _text(_dict(observation.get('eligibility')).get('reason'))
        if eligibility:
            return _row('blocked', 'states.observation.eligibility.reason', eligibility, facts)
        return _row('done', 'states.observation.freshness', None, facts)
    # An age that cannot be established (a clock hold, a stamp ahead of this host's clock) is unknown, never stale.
    unestablished = clock_hold(reasons) or ('stamped_after_now' if 'stamped_after_now' in reasons else None)
    if unestablished:
        return _row('unknown', 'states.observation.freshness_reasons', unestablished, facts)
    if freshness == 'stale':
        return _row('blocked', 'states.observation.freshness', reasons[0] if reasons else 'stale', facts)
    return _row('unknown', 'states.observation.freshness', None, facts)


def _adopt(adoptions):
    rows = [row for row in adoptions or [] if isinstance(row, dict)]
    if not rows:
        return _row('not_recorded', 'adoption records for this policy')
    newest = max(rows, key=lambda row: row.get('sequence') if isinstance(row.get('sequence'), int) else 0)
    return _row('done', 'adoption record %s' % str(newest.get('artifact_id') or '')[:8], None,
                _facts(newest, ('recorded_at',)))


def _intent(states):
    intent = states.get('intent')
    status = intent.get('status') if isinstance(intent, dict) else None
    if status in (None, 'none'):
        return _row('not_recorded', 'states.intent.status')
    facts = _facts(intent, ('recorded_at', 'source_revision'))
    scope = _dict(intent.get('scope'))
    facts.update({key: scope[key] for key in ('stack', 'component') if scope.get(key) is not None})
    if status == 'current':
        return _row('done', 'states.intent.status', None, facts)
    state = 'blocked' if status in ('changed', 'consumer_changed') else 'unknown'
    return _row(state, 'states.intent.status', INTENT_REASONS.get(status), facts)


# ---- the stages that read the newest operation ----------------------------------------------------------------------

def _operation_tag(operation, prefixes):
    from .workbench_screens import short_id
    return 'operation %s' % short_id(operation.get('operation_id'), prefixes)


def _by_stage(delivery):
    stages = [stage for stage in _dict(delivery).get('stages') or [] if isinstance(stage, dict)]
    return {stage.get('stage'): stage for stage in stages}


def _refusals(delivery):
    """The approval refusals the journal recorded, in order, with their codes."""
    events = [event for event in _dict(_dict(delivery).get('history')).get('events') or [] if isinstance(event, dict)]
    return [_text(_dict(event.get('fields')).get('code')) for event in events if event.get('kind') == 'approval_refused']


def _proposal(operation, by, tag):
    stage = by.get('proposal') or {}
    facts = _facts(stage, ('recorded_at', 'repository_intent_id', 'intent_freshness'))
    if stage.get('context_changed'):
        facts['context_changed'] = True
    if not facts and operation.get('recorded_at'):
        facts['recorded_at'] = operation['recorded_at']
    return _row('done', '%s delivery stage proposal' % tag if stage else '%s status' % tag, None, facts)


def _review(by, tag, error):
    stage = by.get('review')
    if not stage:
        return _row('unknown', '%s delivery' % tag, error)
    return _row('done' if stage.get('status') == 'done' else 'unknown', '%s delivery stage review' % tag,
                'no_configuration_change' if stage.get('no_configuration_change') else None,
                {'field_changes': len(stage.get('changes') or [])})


def _approve_execute(by, delivery, tag, error):
    approval, execution = by.get('approval'), by.get('execution')
    if not approval or not execution:
        return _row('unknown', '%s delivery' % tag, error)
    status = approval.get('status')
    refusals = _refusals(delivery)
    facts = {}      # the window's close is the one time a reader needs: when it closes, or when it closed
    window = approval.get('closes_at')
    basis = '%s delivery stage approval' % tag
    if status == 'done':
        if execution.get('status') == 'done':
            return _row('done', '%s delivery stage execution' % tag, None, facts)
        # Dispatch started and no verified result: whether the change reached the service is not established.
        return _row('unknown', '%s journal_status' % tag, _text(execution.get('error_code')) or 'outcome_unknown', facts)
    if status == 'waiting':
        if _by_stage(delivery).get('proposal', {}).get('context_changed'):
            return _row('blocked', basis, 'context_changed', dict(facts, closes_at=window))
        return _row('waiting', basis, None, dict(facts, closes_at=window))
    if status == 'rejected':
        return _row('refused', '%s journal_status' % tag, 'rejected', facts)
    closed = {'expired': 'closed_recorded' if approval.get('recorded') else 'closed', 'clock_uncertain': 'clock_moved_backward',
              'clock_unreadable': 'clock_unreadable', 'not_open': 'not_open'}.get(status)
    if closed is None:
        return _row('unknown', basis, _text(status), facts)
    if refusals:
        # The journal holds the refusal itself: execute was tried and refused, with the code it recorded.
        return _row('refused', '%s journal approval_refused' % tag, refusals[-1], dict(facts, closed_at=window))
    if status == 'clock_unreadable':
        return _row('unknown', basis, closed, facts)
    return _row('blocked', basis, closed, dict(facts, closed_at=window) if status != 'not_open' else facts)


def _readback(by, journal_status, tag, error):
    readback, execution = by.get('readback'), by.get('execution')
    if not readback or not execution:
        return _row('unknown', '%s delivery' % tag, error)
    status = readback.get('status')
    facts = _facts(readback, ('classification', 'second_plan', 'mismatch_count'))
    if status == 'not_started':
        return _row('not_recorded', '%s delivery stage readback' % tag)
    if status == 'pending':
        # The readback is recorded and the service has not yet shown the change: the stage waits, whatever the journal
        # says of the outcome meanwhile.
        return _row('waiting', '%s delivery stage readback' % tag, 'visibility_pending', facts)
    if execution.get('status') == 'unknown' or status in ('not_recorded', 'failed'):
        # Dispatch is recorded and a verified readback of its own is not: the outcome stays unknown, whatever a later
        # reconcile found.
        return _row('unknown', '%s journal_status' % tag, _text(execution.get('error_code')) or journal_status)
    if status == 'done':
        return _row('done', '%s delivery stage readback' % tag, _text(readback.get('classification')), facts)
    return _row('unknown', '%s delivery stage readback' % tag, _text(status), facts)


def _reconcile(by, journal_status, tag, error):
    stage = by.get('reconciliation')
    if not stage:
        return _row('unknown', '%s delivery' % tag, error)
    basis = '%s delivery stage reconciliation' % tag
    status = stage.get('status')
    facts = _facts(stage, ('classification', 'previous_status', 'count', 'recorded_at'))
    if status == 'required':
        return _row('current', basis, journal_status, facts)
    if status == 'pending':
        return _row('waiting', basis, 'visibility_pending', facts)
    if status == 'done':
        classification = _text(stage.get('classification'))
        return _row('blocked' if classification == 'diverged' else 'done', basis, classification, facts)
    if status == 'not_needed':
        return _row('not_applicable', '%s journal_status' % tag, None, {'journal_status': journal_status})
    return _row('unknown', basis, _text(status), facts)


def _record(by, tag, error):
    stage = by.get('deployment_record')
    if not stage:
        return _row('unknown', '%s delivery' % tag, error)
    basis = '%s delivery stage deployment_record' % tag
    status = stage.get('status')
    facts = _facts(stage, ('recorded_at', 'intent_id', 'baseline_admissible'))
    if status == 'done':
        # A recorded deployment whose bound context changed no longer passes its own check.
        return _row('blocked', basis, 'context_changed', facts) if stage.get('context_changed') else _row('done', basis, None, facts)
    if status == 'available':
        return _row('current', basis, None, facts)
    if status == 'not_available':
        reason = _text(stage.get('reason'))
        return _row('blocked' if reason == 'context_changed' else 'not_applicable', basis, reason, facts)
    if status == 'not_applicable':
        return _row('not_applicable', basis, _text(stage.get('reason')), facts)
    if status == 'not_yet':
        return _row('not_recorded', basis)
    return _row('unknown', basis, _text(status), facts)


def _observed_after(by, tag, error):
    stage = by.get('observed_after')
    if not stage:
        return _row('unknown', '%s delivery' % tag, error)
    basis = '%s delivery stage observed_after' % tag
    status = stage.get('status')
    facts = _facts(stage, ('observed_at', 'service_revision', 'before_revision'))
    if status == 'not_yet':
        return _row('not_recorded', basis)
    if status == 'matches_desired':
        freshness = stage.get('observation_freshness')
        if freshness not in (None, 'fresh'):
            # A settled verdict is never drawn from an observation that now reads stale (Delivery says the same).
            reasons = [item for item in stage.get('observation_freshness_reasons') or [] if isinstance(item, str)]
            return _row('unknown', basis, reasons[0] if reasons else _text(freshness), facts)
        return _row('done', basis, None, facts)
    if status == 'differs':
        return _row('blocked', basis, 'differs', facts)
    if status == 'not_applicable':
        return _row('not_applicable', basis, _text(stage.get('reason')), facts)
    return _row('unknown', basis, _text(stage.get('reason')) or _text(status), facts)


def _maintain(rows, attention, has_operation):
    """The policy's maintenance: reached only when the newest operation's path is complete (executed and read back, its
    deployment recorded or not applicable, its observation after the change read), then what diagnostics says needs
    attention."""
    complete = (has_operation and rows['approve_execute']['state'] == 'done' and rows['readback']['state'] == 'done'
                and rows['record']['state'] in ('done', 'not_applicable')
                and rows['observed_after']['state'] in ('done', 'not_applicable'))
    if not complete:
        return _row('not_recorded', 'the newest operation path (record and observed_after)')
    status = _text(attention.get('status'))
    signals = [item for item in attention.get('signals') or [] if isinstance(item, dict)]
    if status == 'clear':
        return _row('current', 'attention.status', None)
    if status == 'attention' and signals:
        return _row('blocked', 'attention.signals', _text(signals[0].get('code')))
    return _row('unknown', 'attention.status', status)


# ---- the continuation: the step the existing screens already give ---------------------------------------------------

def _delivery_owner(by):
    """The stage Delivery's own next step belongs to, in the order Delivery's `_next_step` chooses it."""
    approval, readback, reconciliation = by.get('approval', {}), by.get('readback', {}), by.get('reconciliation', {})
    record, observed = by.get('deployment_record', {}), by.get('observed_after', {})
    if approval.get('status') in ('waiting', 'expired', 'clock_uncertain', 'clock_unreadable', 'not_open', 'rejected'):
        return 'approve_execute'
    if reconciliation.get('status') == 'required':
        return 'reconcile'
    if 'pending' in (readback.get('status'), reconciliation.get('status')):
        return 'reconcile' if reconciliation.get('status') == 'pending' else 'readback'
    if (record.get('status') == 'available' or (record.get('status') == 'not_available' and record.get('reason') == 'context_changed')
            or (record.get('status') == 'done' and record.get('context_changed'))):
        return 'record'
    if observed.get('status') in ('not_yet', 'differs', 'unknown'):
        return 'observed_after'
    return None


def _signal_step(signals, codes):
    """The step diagnostics recorded for the first signal of these codes; None when it recorded none."""
    found = next((item for item in signals if item.get('code') in codes and _text(item.get('next_step'))), None)
    return found['next_step'] if found else None


def _continuations(rows, read, by, delivery):
    """stage id -> the one step the existing logic gives for that stage's state. A stage with no such step has none."""
    from .workbench_screens import RECONCILE_NEXT, lifecycle_next
    states, attention = _dict(read.get('states')), _dict(read.get('attention'))
    signals = [item for item in attention.get('signals') or [] if isinstance(item, dict)]
    eligibility = read.get('eligibility') if isinstance(read.get('eligibility'), dict) else None
    now = read.get('now') if isinstance(read.get('now'), (int, float)) and not isinstance(read.get('now'), bool) else 0.0
    steps = {}
    if rows['observe']['state'] in ('blocked', 'unknown'):
        steps['observe'] = _signal_step(signals, OBSERVATION_SIGNALS)
    status = _dict(states.get('intent')).get('status')
    if rows['intent']['state'] in ('blocked', 'unknown'):
        steps['intent'] = (lifecycle_next(8, {'freshness': {'status': 'stale'}}, now, eligibility)
                           if status in ('changed', 'consumer_changed') else _signal_step(signals, REPOSITORY_SIGNALS))
    if rows['propose']['state'] == 'not_recorded' and rows['intent']['state'] == 'done':
        # The Repository surface's own step for a current intent: prepare a proposal, or say a proposal is blocked now.
        steps['propose'] = lifecycle_next(8, {'freshness': {'status': 'current'}}, now, eligibility)
    review = read.get('review') if isinstance(read.get('review'), dict) and 'error_code' not in read['review'] else None
    journal = _text(_dict(states.get('operation')).get('journal_status')) or _text(_dict(delivery).get('journal_status'))
    if (review is not None and review.get('status') in ('prepared', 'outcome_unknown')
            and rows['approve_execute']['state'] in ('waiting', 'blocked', 'refused', 'unknown')):
        # A reconciled or verified operation has no step here: lifecycle_next would only point at Delivery.
        steps['approve_execute'] = lifecycle_next(4, review, now, eligibility)
    if journal == 'outcome_unknown':
        # The one step the screens give for an unknown outcome (Plan, Execution and Delivery word it the same way).
        for stage in ('readback', 'reconcile'):
            if rows[stage]['state'] in ('unknown', 'current', 'waiting'):
                steps[stage] = RECONCILE_NEXT
    owner = _delivery_owner(by)
    next_action = _text(_dict(delivery).get('next_action'))
    if owner and next_action and owner not in steps and rows[owner]['state'] not in ('done', 'not_applicable'):
        steps[owner] = next_action
    if rows['maintain']['state'] == 'blocked' and signals:
        # The step of the very signal whose code is the stage's reason, never another signal's.
        steps['maintain'] = signals[0].get('next_step')
    return {stage: step for stage, step in steps.items() if _text(step)}


# ---- the projection -------------------------------------------------------------------------------------------------

def project(read):
    """The workflow map of one policy.

    read: the read model's values for the policy, as `workbench._workflow_read` collects them:
      object_id, tenant_id, name; states (observation, intent, newest operation); attention (diagnostics: status, signals);
      eligibility (the proposal's observation check, or None); adoptions (the policy's adoption records); review and
      delivery (the newest operation's, or {'error_code': ...} when its evidence cannot be read, or None when there is
      none); identity_prefixes; now (only a fallback for a window no record has judged).
    """
    read = _dict(read)
    object_id = read.get('object_id')
    if not isinstance(object_id, str) or not object_id:
        _fail('A workflow map needs a result that names its policy by identifier.')
    states, attention = _dict(read.get('states')), _dict(read.get('attention'))
    operation = states.get('operation') if isinstance(states.get('operation'), dict) else None
    delivery = read.get('delivery') if isinstance(read.get('delivery'), dict) else None
    rows = {'observe': _observe(states, read.get('service_checked')), 'adopt': _adopt(read.get('adoptions')),
            'intent': _intent(states)}
    if operation is None:
        absent = _row('not_recorded', 'states.operation')
        rows.update({stage: dict(absent) for stage in ('propose', 'review', 'approve_execute', 'readback', 'reconcile',
                                                         'record', 'observed_after')})
        by, tag = {}, None
    else:
        tag = _operation_tag(operation, read.get('identity_prefixes'))
        by = _by_stage(delivery)
        error = _text(_dict(delivery).get('error_code')) or _text(_dict(read.get('review')).get('error_code'))
        journal = _text(operation.get('journal_status')) or _text(_dict(delivery).get('journal_status'))
        rows.update(propose=_proposal(operation, by, tag), review=_review(by, tag, error),
                    approve_execute=_approve_execute(by, delivery, tag, error),
                    readback=_readback(by, journal, tag, error), reconcile=_reconcile(by, journal, tag, error),
                    record=_record(by, tag, error), observed_after=_observed_after(by, tag, error))
    rows['maintain'] = _maintain(rows, attention, operation is not None)
    steps = _continuations(rows, read, by, delivery)
    opens = {stage: (None if stage in OPERATION_STAGES and operation is None else key) for stage, key in OPENS.items()}
    stages = [{'id': stage, 'state': rows[stage]['state'], 'basis': rows[stage]['basis'], 'reason': rows[stage]['reason'],
               'facts': rows[stage]['facts'], 'opens': opens[stage], 'continuation': steps.get(stage),
               'branch_of': BRANCH_OF.get(stage)} for stage in STAGE_IDS]
    # A stage read from an operation whose evidence could not be read (its basis ends in plain `delivery`) says unknown and
    # why, but it is not a place the records put the policy at, so the position stops at the last stage that was read.
    unread = {stage for stage, row in rows.items() if row['basis'].endswith(' delivery')}
    reached = [item['id'] for item in stages if item['state'] not in NOT_REACHED and item['id'] not in unread]
    observation = _dict(states.get('observation'))
    body = {'schema_version': SCHEMA, 'object_id': object_id, 'tenant_id': read.get('tenant_id'),
            'name': read.get('name') if isinstance(read.get('name'), str) else None,
            'evidence_class': _text(observation.get('evidence_class')) or _text(read.get('evidence_class')),
            'position': reached[-1] if reached else None, 'stages': stages,
            'operation': None if operation is None else {key: operation.get(key) for key in
                                                          ('operation_id', 'operation_root', 'journal_status') if key in operation},
            'read_only': True, 'execution_authorized': False, 'cloud_authority': False}
    revision = hashlib.sha256(_canonical(body).encode('utf-8')).hexdigest()
    return dict(body, revision=revision)
