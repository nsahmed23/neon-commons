"""The loop-export adapter: reads DIR/header.json and DIR/events.jsonl (orchestration-export/1) into orchestration-record/1.

Reading never writes, never follows a symbolic link and bounds every file and line. The result is a plain dict:

    header           the six header fields, or None
    check            {state: ok | mismatch | no_header, header_count, header_last_seq, read_count, read_last_seq,
                      message}; a header that disagrees with what was read says the export was truncated or changed
    events           the accepted records, ordered by sequence, identical lines folded into one
    faults           contract faults: {code, detail, line?, event_id?}; never the offending text
    lines, duplicate_lines, rejected_evidence   counters

An event id seen twice with the same body is one record. The same id with a different body, or two ids on one
sequence number, is shown as a fault and neither copy is kept: a source that contradicts itself is not folded.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat

from .orchestration_contract import (ContractFault, RECORD_CONTRACT, escape_text, event_key, normalize_roots,
                                     parse_event, parse_header)

MAX_HEADER_BYTES = 64 * 1024
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_LINES = 1_000_000


class ExportUnreadable(ValueError):
    """The records path cannot be read as an export at all (missing, not a directory, a link, no events file)."""


def open_regular(path):
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ExportUnreadable('cannot open %s' % os.path.basename(path)) from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ExportUnreadable('%s is not a regular file' % os.path.basename(path))
        return os.fdopen(descriptor, 'rb')
    except BaseException:
        os.close(descriptor)
        raise


def _read_header(directory):
    """(header or None, reason or None, fault or None)."""
    path = os.path.join(directory, 'header.json')
    if not os.path.lexists(path):
        return None, 'there is no header.json', None
    try:
        with open_regular(path) as handle:
            raw = handle.read(MAX_HEADER_BYTES + 1)
    except ExportUnreadable:
        return None, 'header.json cannot be read', {'code': 'invalid_header', 'detail': 'header.json is not a readable file'}
    if len(raw) > MAX_HEADER_BYTES:
        return None, 'header.json is too large', {'code': 'invalid_header', 'detail': 'header.json is too large'}
    try:
        return parse_header(json.loads(raw.decode('utf-8'))), None, None
    except ContractFault as fault:
        return None, 'header.json is not an orchestration-export/1 header', {'code': fault.code, 'detail': fault.detail}
    except (ValueError, RecursionError):
        return None, 'header.json is not JSON', {'code': 'invalid_header', 'detail': 'header.json is not JSON'}


def iter_lines(handle):
    """(number, bytes, problem). problem is None for a usable line. A line longer than MAX_LINE_BYTES has its remainder
    skipped unread, and reading stops after MAX_LINES lines."""
    number = 0
    while number < MAX_LINES:
        raw = handle.readline(MAX_LINE_BYTES + 1)
        if not raw:
            return
        number += 1
        if len(raw) > MAX_LINE_BYTES and not raw.endswith(b'\n'):
            while True:
                rest = handle.readline(MAX_LINE_BYTES)
                if not rest or rest.endswith(b'\n'):
                    break
            yield number, b'', 'line longer than %d bytes' % MAX_LINE_BYTES
        else:
            yield number, raw, None
    if handle.readline(1):
        yield number + 1, b'', 'more than %d lines' % MAX_LINES


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def _check(header, reason, read_count, read_last):
    if header is None:
        return {'state': 'no_header', 'header_count': None, 'header_last_seq': None, 'read_count': read_count,
                'read_last_seq': read_last,
                'message': 'no usable header (%s): without it a truncated export cannot be told from a quiet system'
                           % reason}
    state = 'ok' if (header['count'], header['last_seq']) == (read_count, read_last) else 'mismatch'
    if state == 'ok':
        message = 'the header agrees with what was read (%d events, last sequence %d)' % (read_count, read_last)
    else:
        message = ('the header says %d events ending at sequence %d but the export holds %d ending at sequence %d: '
                   'the export was truncated or changed after its header was written'
                   % (header['count'], header['last_seq'], read_count, read_last))
    return {'state': state, 'header_count': header['count'], 'header_last_seq': header['last_seq'],
            'read_count': read_count, 'read_last_seq': read_last, 'message': message}


def read_export(directory, roots=()):
    """Read one export directory. `roots` are the configured evidence roots (none means no evidence path is shown)."""
    directory = os.fspath(directory)
    if os.path.islink(directory) or not os.path.isdir(directory):
        raise ExportUnreadable('the records path is not a directory')
    roots = normalize_roots(roots)
    header, reason, header_fault = _read_header(directory)
    faults = [header_fault] if header_fault else []
    events_path = os.path.join(directory, 'events.jsonl')
    if not os.path.lexists(events_path):
        raise ExportUnreadable('the records directory has no events.jsonl')

    seen = {}        # event id -> digest of the first body seen
    records = {}     # event id -> accepted record
    by_seq = {}      # sequence -> event id that holds it
    conflicted, duplicates, rejected, lines = set(), 0, 0, 0
    last_seq = 0
    with open_regular(events_path) as handle:
        if os.fstat(handle.fileno()).st_size > MAX_FILE_BYTES:
            raise ExportUnreadable('events.jsonl is too large')
        for number, raw, problem in iter_lines(handle):
            lines = number
            if problem:
                faults.append({'code': 'invalid_line', 'line': number, 'detail': problem})
                continue
            if not raw.strip():
                continue
            try:
                body = json.loads(raw.decode('utf-8'))
                digest = _digest(body)
            except (ValueError, RecursionError):
                body = None
            if not isinstance(body, dict):
                faults.append({'code': 'invalid_line', 'line': number, 'detail': 'the line is not a JSON object'})
                continue
            try:
                event_id, seq = event_key(body)
            except ContractFault as fault:
                faults.append({'code': fault.code, 'line': number, 'detail': fault.detail})
                continue
            last_seq = max(last_seq, seq)
            if event_id in seen:
                if seen[event_id] == digest:
                    duplicates += 1
                elif event_id not in conflicted:
                    conflicted.add(event_id)
                    records.pop(event_id, None)
                    by_seq = {s: i for s, i in by_seq.items() if i != event_id}
                    faults.append({'code': 'event_conflict', 'line': number, 'event_id': event_id,
                                   'detail': 'the same event id appears with different bodies'})
                continue
            seen[event_id] = digest
            try:
                record, refused = parse_event(body, roots)
            except ContractFault as fault:
                faults.append({'code': fault.code, 'line': number, 'event_id': event_id, 'detail': fault.detail})
                continue
            rejected += refused
            if seq in by_seq:
                other = by_seq.pop(seq)
                records.pop(other, None)
                faults.append({'code': 'seq_reused', 'line': number, 'event_id': event_id,
                               'detail': 'event %s and event %s claim sequence %d; neither is kept'
                                         % (escape_text(other), escape_text(event_id), seq)})
                continue
            records[event_id] = record
            by_seq[seq] = event_id
    ordered = sorted(records.values(), key=lambda item: item['seq'])
    return {'contract': RECORD_CONTRACT, 'header': header, 'check': _check(header, reason, len(seen), last_seq),
            'events': ordered, 'faults': faults, 'lines': lines, 'duplicate_lines': duplicates,
            'rejected_evidence': rejected}

