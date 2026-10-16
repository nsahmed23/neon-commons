"""`intune-iac engineering`: the engineering orchestration records as plain, read-only text (or JSON).

It reads a directory written by `loopctl export`, checks the header against what it read, folds the events by task
(orchestration_reducer) and prints the source header, any contract faults and one line per task. It confers no
dispatch, approval or cancellation authority and writes nothing. With no records path it says so and exits 0, and the
rest of the product works as before.

The optional controller log is not a state source: its lines are free text without task ids or terminal events. It is
only counted, so a view of the loop alone never looks like the whole of the project's activity.
"""
from __future__ import annotations

import json
import os

from .io import AppError
from .orchestration_contract import RECORD_CONTRACT, InvalidRoot, escape_text, normalize_roots
from .orchestration_export import ExportUnreadable, iter_lines, open_regular, read_export
from .orchestration_reducer import reduce_events

NOT_CONFIGURED = ('Engineering records are not configured: pass --records DIR, a directory written by `loopctl export`. '
                  'Nothing is shown here; the rest of the product works as before.')
MAX_LOG_BYTES = 64 * 1024 * 1024
MAX_FAULTS_SHOWN = 20


class ControllerLogUnreadable(ValueError):
    """The controller log path cannot be read as a file of JSON lines."""


def controller_log_counts(path):
    """(dispatch lines, unreadable lines) of a controller log. Only `kind == "dispatch"` lines are counted."""
    dispatches = unreadable = 0
    try:
        with open_regular(os.fspath(path)) as handle:
            if os.fstat(handle.fileno()).st_size > MAX_LOG_BYTES:
                raise ControllerLogUnreadable('the controller log is too large')
            for _, raw, problem in iter_lines(handle):
                if problem:
                    unreadable += 1
                    continue
                if not raw.strip():
                    continue
                try:
                    row = json.loads(raw.decode('utf-8'))
                except (ValueError, RecursionError):
                    row = None
                if not isinstance(row, dict):
                    unreadable += 1
                elif row.get('kind') == 'dispatch':
                    dispatches += 1
    except ExportUnreadable as error:
        raise ControllerLogUnreadable('the controller log cannot be read as a file') from error
    return dispatches, unreadable


def build_view(records, evidence_roots=(), controller_log=None):
    """The whole view as plain data. Every string in it is either a validated identifier or already escaped."""
    export = read_export(records, roots=evidence_roots)
    reduced = reduce_events(export['events'])
    tasks = reduced['tasks']
    log = None
    if controller_log is not None:
        dispatches, unreadable = controller_log_counts(controller_log)
        log = {'dispatch_lines': dispatches, 'loop_tasks': len(tasks),
               'only_in_controller_log': max(0, dispatches - len(tasks)), 'unreadable_lines': unreadable}
    return {'contract': RECORD_CONTRACT, 'read_only': True,
            'source': {'header': export['header'], 'check': export['check']},
            'read': {'events': len(export['events']), 'lines': export['lines'],
                     'duplicate_lines': export['duplicate_lines'], 'rejected_evidence': export['rejected_evidence']},
            'faults': export['faults'], 'tasks': tasks, 'verifications': reduced['verifications'],
            'notes': reduced['notes'], 'controller_log': log}


def _fault_line(fault):
    where = ''.join(', %s %s' % (key, escape_text(fault[key])) for key in ('line', 'event_id') if key in fault)
    return '  %s%s: %s' % (escape_text(fault['code']), ' (%s)' % where[2:] if where else '', escape_text(fault['detail'], 300))


def _task_line(row):
    incarnation = ', incarnation %s' % row['incarnation'] if row['adoptions'] and row['incarnation'] else ''
    reason = 'reason recorded (free text, not shown) | ' if row['reason_recorded'] else ''
    parts = ['%s  %s  %s  %s' % (row['task'], row['kind'] or 'kind not recorded', row['role'], row['words']),
             'last %s seq %d' % (row['last_event_type'], row['last_seq']),
             'adoptions %d%s' % (row['adoptions'], incarnation),
             '%sevidence %s' % (reason, row['evidence'] or 'none')]
    return escape_text(' | '.join(parts), 600)


def _verification_lines(counts):
    """A verification record that names no task cannot verify one, so the count is said out loud."""
    if not counts['records']:
        return []
    if counts['unattached'] == counts['records']:
        return ['%d verification records, none attached to a task; no task reads verified from them' % counts['records']]
    if counts['unattached']:
        return ['%d verification records, %d not attached to a task' % (counts['records'], counts['unattached'])]
    return []


def render_lines(view):
    header, check = view['source']['header'], view['source']['check']
    out = ['Engineering view (read-only): what the orchestration records say. It cannot dispatch, approve or cancel anything.']
    if header:
        out.append('Source: %s, source %s (a digest of the store path), exported %s' % (
            header['contract'], header['source_id'][:12], header['exported_utc']))
        out.append('Header: %d events, last sequence %d, state digest %s' % (
            header['count'], header['last_seq'], header['state_digest'][:12]))
    else:
        out.append('Source: no usable header')
    out.append('Read: %d events, last sequence %d' % (check['read_count'], check['read_last_seq']))
    label = {'ok': 'OK', 'mismatch': 'MISMATCH', 'no_header': 'NO HEADER'}[check['state']]
    out.append('Export check: %s, %s' % (label, escape_text(check['message'], 400)))
    if view['read']['rejected_evidence']:
        out.append('Evidence references outside the configured roots: %d (not shown)' % view['read']['rejected_evidence'])
    faults = view['faults']
    if faults:
        out.append('Contract faults (%d); the lines they name are not folded:' % len(faults))
        out += [_fault_line(fault) for fault in faults[:MAX_FAULTS_SHOWN]]
        if len(faults) > MAX_FAULTS_SHOWN:
            out.append('  ... and %d more' % (len(faults) - MAX_FAULTS_SHOWN))
    tasks = view['tasks']
    out.append('Tasks (%d):' % len(tasks) if tasks else 'Tasks: none recorded in this export.')
    out += [_task_line(row) for row in tasks]
    out += [escape_text(note, 400) for note in view['notes']]
    out += _verification_lines(view['verifications'])
    log = view['controller_log']
    if log:
        out.append('Controller log: %d dispatches recorded only in the controller log; not modelled '
                   '(%d dispatch lines in the log, %d tasks in the loop export; counted by difference, '
                   'no line is matched to a task)%s' % (
                       log['only_in_controller_log'], log['dispatch_lines'], log['loop_tasks'],
                       '; %d unreadable lines' % log['unreadable_lines'] if log['unreadable_lines'] else ''))
    return out


def command(args):
    """The data form. Raises AppError for an unreadable path; with no --records the answer is a sentence, not an error."""
    if not args.records:
        return {'engineering': 'not_configured', 'message': NOT_CONFIGURED}
    try:
        normalize_roots(args.evidence_root)
        return build_view(args.records, args.evidence_root, args.controller_log)
    except InvalidRoot as error:
        raise AppError('engineering_root_invalid', str(error)) from error
    except ExportUnreadable as error:
        raise AppError('engineering_records_unreadable', 'Cannot read the records: %s.' % error) from error
    except ControllerLogUnreadable as error:
        raise AppError('engineering_controller_log_unreadable', 'Cannot read the controller log: %s.' % error) from error


def lines_for(result):
    """The text form of whatever `command` returned."""
    return [result['message']] if result.get('engineering') == 'not_configured' else render_lines(result)
