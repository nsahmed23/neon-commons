"""Fold orchestration-record/1 events into one row per task, with the loop's own semantics and no more.

The fold is a pure function of the ordered events: no clock, no I/O, nothing inferred from timing. Each word it
prints is a fact the records support and no stronger one:

    queued                 a queue record exists
    started                "started, no news since T": a started record from an export is not a running process
    timed out / cancel     cancellation pending, never cancelled
    completed              "completed, unverified": the result passed the loop's schema, nothing has verified it
    verified               only a passing verification that names this task and the exact tree it completed with,
                           and that no correction has withdrawn
    cancelled              only with cleanup confirmed; "(attested by the controller)" when the controller said so
    unknown, failed        as recorded; blocked is unavailable or refused, with the reason beside it
    later terminal event   an annotation ("unknown; later cancelled ..."), never a state change
    late result            an annotation on the task, never a state change

An attempt comes only from an explicit attempt id. A task whose events name none has one implicit attempt. When a
task has two explicit attempts, an event that names no attempt is not applied to either: it is shown as an annotation,
because a missing correlation stays missing and the fold never infers one from chronology. The process that recorded
an event (the incarnation) is not an attempt and is never used to group events.
"""
from __future__ import annotations

ATTESTED = 'controller attested'
FINAL = ('completed', 'verified', 'failed', 'cancelled', 'unknown', 'blocked')
# Events that change or annotate a task's state; an unattributed one on a multi-attempt task is not applied.
ATTRIBUTED = frozenset(('dispatch.queued', 'dispatch.refused', 'dispatch.started', 'dispatch.timed_out',
                        'dispatch.cancel_requested', 'dispatch.cancelled', 'dispatch.completed', 'dispatch.failed',
                        'dispatch.unknown', 'dispatch.unavailable', 'advisor.late_result', 'repair.reported'))
# Only these may open a new explicit attempt; any other event naming an unopened attempt is not attributed.
OPENING = frozenset(('dispatch.queued', 'dispatch.started'))
# What an attempt that is no longer current may say about the task: nothing, only an annotation.
ENDINGS = frozenset(('dispatch.cancelled', 'dispatch.completed', 'dispatch.failed', 'dispatch.unknown',
                     'dispatch.unavailable', 'advisor.late_result'))


def _attempt(attempt_id):
    return {'id': attempt_id, 'started': False, 'timed_out': False, 'cancel_requested': False,
            'cleanup_unconfirmed': False, 'terminal': None, 'tree': None, 'last': None}


def _new(event):
    return {'task': event['task'], 'kind': None, 'role': event['role'], 'queued': False, 'adoptions': 0,
            'incarnation': None, 'late': False, 'evidence': None, 'last': None, 'notes': [],
            'attempts': {None: _attempt(None)}, 'explicit': [], 'current': None}


def _end(attempt, event, outcome):
    if attempt['terminal'] is None:
        attempt['terminal'] = {'outcome': outcome, 'seq': event['seq'], 'reason': event['data'].get('reason'),
                               'attested': event['data'].get('reason') == ATTESTED}
        return True
    return False


def _later(event):
    """The annotation for a terminal event that arrives after the attempt already ended."""
    kind, data = event['event_type'], event['data']
    if kind == 'dispatch.cancelled':
        if not data.get('cleanup_confirmed'):
            return 'later cancel recorded, cleanup not confirmed'
        return 'later cancelled' + (' (attested by the controller)' if data.get('reason') == ATTESTED else '')
    return 'later ' + ('blocked' if kind in ('dispatch.unavailable', 'dispatch.refused') else kind.split('.')[1])


def _later_or_end(task, attempt, event, outcome):
    """End the attempt with this event, or annotate it when the attempt already ended. True when it ended."""
    if _end(attempt, event, outcome):
        return True
    task['notes'].append(_later(event))
    return False


def _choose(task, event):
    """(attempt, is_current) for the event, or (None, False) when it must not be applied to any attempt."""
    wanted = event['attempt']
    if wanted is None:
        if len(task['attempts']) >= 2:  # an unnamed attempt that ended, then a named retry, is two attempts too
            if event['event_type'] in ATTRIBUTED:  # other types (claims) say nothing about an attempt; nothing to show
                task['notes'].append('%s recorded without an attempt after attempt %s started: not attributed' % (
                    event['event_type'], task['current']))
            return None, False
        return task['attempts'][task['current']], True
    if wanted not in task['attempts']:
        if event['event_type'] not in OPENING:
            task['notes'].append('%s names attempt %s, which no started record opened: not attributed' % (
                event['event_type'], wanted))
            return None, False
        implicit = task['attempts'].get(None)
        if implicit is not None and not task['explicit'] and implicit['terminal'] is None:
            task['attempts'][wanted] = dict(implicit, id=wanted)  # the one logical attempt, now named
            del task['attempts'][None]
        else:
            task['attempts'][wanted] = _attempt(wanted)
        task['explicit'].append(wanted)
        task['current'] = wanted
    return task['attempts'][wanted], wanted == task['current']


def _apply(task, event):
    kind, data = event['event_type'], event['data']
    task['last'] = event
    if event['evidence']:
        task['evidence'] = event['evidence'][-1]['path']
    attempt, current = _choose(task, event)
    if attempt is None:
        return
    if not current:
        if kind in ENDINGS:
            task['notes'].append('attempt %s recorded %s after attempt %s started: not applied to the current attempt' % (
                attempt['id'], kind, task['current']))
        return
    attempt['last'] = event
    if kind == 'dispatch.queued':
        task['kind'] = data.get('kind') or task['kind']
        task['queued'] = True
    elif kind == 'dispatch.refused':
        task['kind'] = data.get('kind') or task['kind']
        _later_or_end(task, attempt, event, 'blocked')
    elif kind == 'dispatch.started':
        if attempt['terminal'] is None:
            attempt.update(started=True, timed_out=False, cancel_requested=False, cleanup_unconfirmed=False)
        else:  # the state stays as the terminal event left it; the later start is shown, not dropped
            task['notes'].append('later started (adopted)' if data.get('adopted') else 'later started')
        task['adoptions'] += 1 if data.get('adopted') else 0
        task['incarnation'] = event['incarnation']
    elif kind == 'dispatch.timed_out':
        attempt['timed_out'] = True
    elif kind == 'dispatch.cancel_requested':
        attempt['cancel_requested'] = True
    elif kind == 'dispatch.cancelled':
        if attempt['terminal'] is not None:
            task['notes'].append(_later(event))
        elif data.get('cleanup_confirmed'):
            _end(attempt, event, 'cancelled')
        else:
            attempt['cleanup_unconfirmed'] = True
    elif kind in ('dispatch.completed', 'dispatch.failed', 'dispatch.unknown'):
        if _later_or_end(task, attempt, event, kind.split('.')[1]) and kind == 'dispatch.completed':
            attempt['tree'] = data.get('tree') or attempt['tree']
    elif kind == 'repair.reported':
        if attempt['terminal'] is None:
            attempt['tree'] = data.get('tree') or attempt['tree']
        else:  # the completion already recorded its tree; a later report never changes it
            task['notes'].append('later repair reported')
    elif kind == 'dispatch.unavailable':
        _later_or_end(task, attempt, event, 'blocked')
    elif kind == 'advisor.late_result':
        if not task['late']:
            task['notes'].append('late result recorded')
        task['late'] = True


def _pending(attempt):
    return [word for flag, word in ((attempt['timed_out'], 'timed out'), (attempt['cancel_requested'], 'cancel requested'),
                                     (attempt['cleanup_unconfirmed'], 'cancel recorded, cleanup not confirmed')) if flag]


def _state(task, attempt, proof):
    """(state, phrase) from what the records hold."""
    ended = attempt['terminal']
    if ended:
        outcome = ended['outcome']
        if outcome == 'completed':
            if proof:
                return 'verified', 'completed, verified by %s on tree %s' % (proof['gate'] or 'a gate', attempt['tree'][:12])
            return 'completed', 'completed, unverified'
        if outcome == 'cancelled':
            return 'cancelled', 'cancelled (attested by the controller)' if ended['attested'] else 'cancelled'
        return outcome, outcome
    since = ', no news since ' + (attempt['last'] or task['last'])['wall_utc']
    parts = _pending(attempt)
    if parts:
        return 'cancel_pending', 'cancellation pending (%s)' % '; '.join(parts) + since
    if attempt['started']:
        return 'started', 'started' + since
    return 'queued', 'queued' + since


def _proof(task, attempt, verifications, corrected):
    """The latest passing verification that names this task and the exact tree it completed with, or None."""
    ended = attempt['terminal']
    if not (ended and ended['outcome'] == 'completed' and attempt['tree']):
        return None
    found = [item for item in verifications if item['task'] == task['task'] and item['data'].get('outcome') == 'pass'
             and item['data'].get('tree') == attempt['tree'] and item['event_id'] not in corrected]
    return {'gate': found[-1]['data'].get('gate'), 'seq': found[-1]['seq']} if found else None


def _row(task, verifications, corrected):
    attempt = task['attempts'][task['current']]
    state, phrase = _state(task, attempt, _proof(task, attempt, verifications, corrected))
    last, notes = task['last'], task['notes']
    clock = (attempt['last'] or last)['wall_utc']
    return {'task': task['task'], 'kind': task['kind'], 'role': task['role'], 'state': state, 'state_words': phrase,
            'words': '; '.join([phrase] + notes), 'notes': list(notes),
            'reason': attempt['terminal']['reason'] if attempt['terminal'] else None,
            'last_event_type': last['event_type'], 'last_seq': last['seq'], 'last_wall_utc': last['wall_utc'],
            'no_news_since': None if state in FINAL else clock, 'adoptions': task['adoptions'],
            'incarnation': task['incarnation'], 'late_result': task['late'], 'evidence': task['evidence']}


def reduce_events(events):
    """events: accepted records ordered by sequence. Returns the rows in order of first appearance, the verification
    counts and the notes that belong to no task."""
    tasks, verifications, corrections, held = {}, [], [], set()
    for event in events:
        held.add(event['event_id'])
        kind = event['event_type']
        if kind == 'verification.completed':
            verifications.append(event)
        elif kind == 'verification.corrected':
            corrections.append(event)
        elif event['task'] is not None:
            _apply(tasks.setdefault(event['task'], _new(event)), event)
    corrected = {item['data'].get('corrects') for item in corrections}
    notes = ['correction at sequence %d names verification %s, which this export does not hold' % (
        item['seq'], item['data']['corrects']) for item in corrections
        if item['data'].get('corrects') and item['data']['corrects'] not in held]
    return {'tasks': [_row(task, verifications, corrected) for task in tasks.values()],
            'verifications': {'records': len(verifications),
                              'unattached': sum(1 for item in verifications if item['task'] is None)},
            'notes': notes}
