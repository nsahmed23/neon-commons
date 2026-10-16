"""Hand-written orchestration-export/1 directories for the engineering view tests.

An event is a plain dict with the fields the loop's export writes (`loopctl export`): seq, event_id, event_type, role,
task, attempt, incarnation, wall_utc, evidence and data. The header is computed from the events unless a test
overrides it, so a test states only what it wants to differ.
"""
import datetime
import hashlib
import json
from pathlib import Path

BASE = datetime.datetime(2026, 10, 15, 6, 0, 0, tzinfo=datetime.timezone.utc)
DIGEST = 'f' * 64
RUNNER_A = 'a1a1a1a1a1a1'
RUNNER_B = 'b2b2b2b2b2b2'


def eid(token):
    """A valid event id (32 lower-case hex, the length of the loop uuid4().hex ids) for a readable token."""
    return hashlib.sha256(token.encode()).hexdigest()[:32]


def attempt_id(token):
    """A valid attempt id (32 lower-case hex, as attempt.py writes) for a readable token."""
    return hashlib.sha256(('attempt:' + token).encode()).hexdigest()[:32]


def wall(seq):
    stamp = BASE + datetime.timedelta(minutes=seq)
    return stamp.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def event(seq, event_type, task=None, *, attempt=None, incarnation=RUNNER_A, role='runner', evidence=(), **data):
    return {'seq': seq, 'event_id': eid('ev-%d' % seq), 'event_type': event_type, 'role': role, 'task': task,
            'attempt': attempt, 'incarnation': incarnation, 'wall_utc': wall(seq), 'evidence': list(evidence),
            'data': data}


def header_for(events, **override):
    ids = {item['event_id'] for item in events}
    header = {'contract': 'orchestration-export/1', 'source_id': 'c' * 64, 'exported_utc': wall(500),
              'count': len(ids), 'last_seq': max((item['seq'] for item in events), default=0), 'state_digest': DIGEST}
    header.update(override)
    return header


def write_export(directory, events, *, header=None, extra_lines=(), raw_lines=None):
    """Write DIR/header.json and DIR/events.jsonl. header=False omits the header file; raw_lines replaces the event
    lines wholesale (a test of malformed input); extra_lines are appended verbatim (a duplicated or altered line)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if header is not False:
        (directory / 'header.json').write_text(json.dumps(header if header is not None else header_for(events)),
                                               encoding='utf-8', newline='\n')
    lines = raw_lines if raw_lines is not None else [json.dumps(item, sort_keys=True) for item in events]
    (directory / 'events.jsonl').write_text(''.join(line + '\n' for line in list(lines) + list(extra_lines)),
                                            encoding='utf-8', newline='\n')
    return directory


def lifecycle(task, *, start=1, kind='advisor', terminal=None, **terminal_data):
    """queued (seq start), started (start + 1) and, when named, one terminal event (start + 2)."""
    events = [event(start, 'dispatch.queued', task, kind=kind), event(start + 1, 'dispatch.started', task, adopted=False)]
    if terminal:
        events.append(event(start + 2, terminal, task, **terminal_data))
    return events
