"""Fold orchestration-record/1 events into one row per task, with the loop's own semantics and no more.

The fold is a pure function of the ordered events: no clock, no I/O, nothing inferred from timing. Each word it
prints is a fact the records support and no stronger one:

    queued                 a queue record exists
    started                "started, no news since T": a started record from an export is not a running process
    timed out / cancel     cancellation pending, never cancelled
    completed              "completed, unverified": the result passed the loop's schema, nothing has verified it
    cancelled              only with cleanup confirmed; "(attested by the controller)" when the controller said so
    unknown, failed        as recorded; blocked is unavailable or refused, with the reason beside it
    late result            an annotation on the task, never a state change
"""
from __future__ import annotations

ATTESTED = 'controller attested'
FINAL = ('completed', 'failed', 'cancelled', 'unknown', 'blocked')


def _new(event):
    return {'task': event['task'], 'kind': None, 'role': event['role'], 'queued': False, 'started': False,
            'timed_out': False, 'cancel_requested': False, 'cleanup_unconfirmed': False, 'terminal': None,
            'adoptions': 0, 'incarnation': None, 'late': False, 'evidence': None, 'last': None}


def _end(task, event, outcome):
    if task['terminal'] is None:
        task['terminal'] = {'outcome': outcome, 'seq': event['seq'], 'reason': event['data'].get('reason'),
                            'attested': event['data'].get('reason') == ATTESTED}


def _apply(task, event):
    kind, data = event['event_type'], event['data']
    task['last'] = event
    if event['evidence']:
        task['evidence'] = event['evidence'][-1]['path']
    if kind == 'dispatch.queued':
        task['kind'] = data.get('kind') or task['kind']
        task['queued'] = True
    elif kind == 'dispatch.refused':
        task['kind'] = data.get('kind') or task['kind']
        _end(task, event, 'blocked')
    elif kind == 'dispatch.started':
        if task['terminal'] is None:
            task.update(started=True, timed_out=False, cancel_requested=False, cleanup_unconfirmed=False)
            task['adoptions'] += 1 if data.get('adopted') else 0
            task['incarnation'] = event['incarnation']
    elif kind == 'dispatch.timed_out':
        task['timed_out'] = True
    elif kind == 'dispatch.cancel_requested':
        task['cancel_requested'] = True
    elif kind == 'dispatch.cancelled':
        if data.get('cleanup_confirmed'):
            _end(task, event, 'cancelled')
        else:
            task['cleanup_unconfirmed'] = True
    elif kind in ('dispatch.completed', 'dispatch.failed', 'dispatch.unknown'):
        _end(task, event, kind.split('.')[1])
    elif kind == 'dispatch.unavailable':
        _end(task, event, 'blocked')
    elif kind == 'advisor.late_result':
        task['late'] = True


def _pending(task):
    parts = [word for flag, word in ((task['timed_out'], 'timed out'), (task['cancel_requested'], 'cancel requested'),
                                      (task['cleanup_unconfirmed'], 'cancel recorded, cleanup not confirmed')) if flag]
    return parts


def _state(task):
    """(state, phrase) from what the records hold."""
    ended = task['terminal']
    if ended:
        outcome = ended['outcome']
        if outcome == 'completed':
            return 'completed', 'completed, unverified'
        if outcome == 'cancelled':
            return 'cancelled', 'cancelled (attested by the controller)' if ended['attested'] else 'cancelled'
        return outcome, outcome
    since = ', no news since ' + task['last']['wall_utc']
    parts = _pending(task)
    if parts:
        return 'cancel_pending', 'cancellation pending (%s)' % '; '.join(parts) + since
    if task['started']:
        return 'started', 'started' + since
    return 'queued', 'queued' + since


def _row(task):
    state, phrase = _state(task)
    last, notes = task['last'], []
    if task['late']:
        notes.append('late result recorded')
    return {'task': task['task'], 'kind': task['kind'], 'role': task['role'], 'state': state, 'state_words': phrase,
            'words': '; '.join([phrase] + notes), 'notes': notes,
            'reason': task['terminal']['reason'] if task['terminal'] else None,
            'last_event_type': last['event_type'], 'last_seq': last['seq'], 'last_wall_utc': last['wall_utc'],
            'no_news_since': None if state in FINAL else last['wall_utc'], 'adoptions': task['adoptions'],
            'incarnation': task['incarnation'], 'late_result': task['late'], 'evidence': task['evidence']}


def reduce_events(events):
    """events: accepted records ordered by sequence. Returns {'tasks': [row, ...]} in order of first appearance."""
    tasks = {}
    for event in events:
        if event['task'] is None:
            continue
        _apply(tasks.setdefault(event['task'], _new(event)), event)
    return {'tasks': [_row(task) for task in tasks.values()]}
