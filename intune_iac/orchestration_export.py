"""The loop-export adapter: reads DIR/header.json and DIR/events.jsonl (orchestration-export/1) into orchestration-record/1.

Reading never writes, never follows a symbolic link, opens the records directory once and bounds every file and line. The result is a plain dict:

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

import collections
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


# How a file is opened without trusting a name twice. On POSIX the records directory is opened once (O_NOFOLLOW |
# O_DIRECTORY, then compared by device and inode with what lstat said) and header.json and events.jsonl are opened by
# name relative to that descriptor (dir_fd), so replacing the directory or one of its parents afterwards changes
# nothing that is read. Each file is checked with lstat, opened with O_NOFOLLOW | O_NONBLOCK and compared by device and
# inode after the open, so a file swapped for a link or a pipe between the two steps is refused. On Windows
# O_NOFOLLOW, O_DIRECTORY and dir_fd do not exist: names are joined to the path, a symbolic link or reparse point
# (junction) is refused by lstat, the device and inode are compared after the open and the directory is compared again
# after each file opens. The check there is narrower (a parent component swapped in the instant between the directory
# check and the open is not covered by a handle) and it refuses whenever the two stat results disagree.
_REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
_DIR_FD = (all(hasattr(os, name) for name in ('O_DIRECTORY', 'O_NOFOLLOW'))
           and os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
           and os.stat in os.supports_follow_symlinks)


def _is_link(info):
    return stat.S_ISLNK(info.st_mode) or bool(_REPARSE and getattr(info, 'st_file_attributes', 0) & _REPARSE)


def _same(first, second):
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def _open_checked(name, dir_fd=None):
    """A binary file object for a regular file `name` (relative to `dir_fd` when given), or ExportUnreadable."""
    shown = os.path.basename(name)
    extra = {} if dir_fd is None else {'dir_fd': dir_fd}
    try:
        before = os.stat(name, follow_symlinks=False, **extra)  # before any open: a pipe or device can block
    except OSError as error:
        raise ExportUnreadable('cannot open %s' % shown) from error
    if _is_link(before):
        raise ExportUnreadable('%s is a symbolic link' % shown)
    if not stat.S_ISREG(before.st_mode):
        raise ExportUnreadable('%s is not a regular file' % shown)
    # O_NONBLOCK guards a swap for a FIFO after the stat above: a read-only open would wait for a writer forever.
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0)
    try:
        descriptor = os.open(name, flags, **extra)
    except OSError as error:
        raise ExportUnreadable('cannot open %s' % shown) from error
    try:
        after = os.fstat(descriptor)
        if not stat.S_ISREG(after.st_mode):
            raise ExportUnreadable('%s is not a regular file' % shown)
        if not _same(before, after):
            raise ExportUnreadable('%s changed while it was being opened' % shown)
        return os.fdopen(descriptor, 'rb')
    except BaseException:
        os.close(descriptor)
        raise


def open_regular(path):
    """A binary file object for the regular file at `path`; a link, pipe, device or file that changes is refused."""
    return _open_checked(os.fspath(path))


class RecordsDirectory:
    """The records directory, validated once; its children are opened through it (see the note above)."""

    def __init__(self, path):
        self.path, self.fd = os.fspath(path), None
        self._before = self._stat_directory()
        if _DIR_FD:
            try:
                self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            except OSError as error:
                raise ExportUnreadable('the records path is not a directory') from error
            try:
                if not _same(self._before, os.fstat(self.fd)):
                    raise ExportUnreadable('the records directory changed while it was being opened')
            except BaseException:
                self.close()
                raise

    def _stat_directory(self):
        try:
            info = os.stat(self.path, follow_symlinks=False)
        except OSError as error:
            raise ExportUnreadable('the records path is not a directory') from error
        if _is_link(info) or not stat.S_ISDIR(info.st_mode):
            raise ExportUnreadable('the records path is not a directory')
        return info

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def exists(self, name):
        try:
            if self.fd is None:
                os.stat(os.path.join(self.path, name), follow_symlinks=False)
            else:
                os.stat(name, follow_symlinks=False, dir_fd=self.fd)
        except FileNotFoundError:
            return False
        except OSError:
            return True  # something is there that cannot be examined; opening it will refuse it
        return True

    def open(self, name):
        if self.fd is not None:
            return _open_checked(name, self.fd)
        handle = _open_checked(os.path.join(self.path, name))
        try:
            if not _same(self._before, self._stat_directory()):
                raise ExportUnreadable('the records directory changed while %s was being opened' % name)
        except BaseException:
            handle.close()
            raise
        return handle


def _read_header(records_dir):
    """(header or None, reason or None, fault or None)."""
    if not records_dir.exists('header.json'):
        return None, 'there is no header.json', None
    try:
        with records_dir.open('header.json') as handle:
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
    roots = normalize_roots(roots)
    with RecordsDirectory(directory) as records_dir:
        return _read_records(records_dir, roots)


def _read_records(records_dir, roots):
    header, reason, header_fault = _read_header(records_dir)
    faults = [header_fault] if header_fault else []
    if not records_dir.exists('events.jsonl'):
        raise ExportUnreadable('the records directory has no events.jsonl')

    seen = {}        # event id -> digest of the first body seen
    records = {}     # event id -> accepted record
    by_seq = {}      # sequence -> event id that holds it
    claimed_by = collections.defaultdict(set)  # event id -> every sequence a line with that id named
    conflicted, contested, duplicates, rejected, lines = set(), set(), 0, 0, 0
    last_seq = 0
    with records_dir.open('events.jsonl') as handle:
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
            # Every sequence an id names is recorded as soon as its key is read, whether or not the body parses, so a
            # later conflict contests all of them.
            claimed_by[event_id].add(seq)
            if event_id in seen:
                if seen[event_id] == digest:
                    duplicates += 1
                    continue
                records.pop(event_id, None)
                if event_id not in conflicted:
                    conflicted.add(event_id)
                    faults.append({'code': 'event_conflict', 'line': number, 'event_id': event_id,
                                   'detail': 'the same event id appears with different bodies'})
                # No copy is kept, but every sequence the id named stays claimed: another id on any of them is not
                # folded, and one already holding it is dropped.
                for claimed in sorted(claimed_by[event_id]):
                    contested.add(claimed)
                    other = by_seq.pop(claimed, None)
                    if other is not None and other != event_id:  # its own entry is just released
                        records.pop(other, None)
                        faults.append({'code': 'seq_reused', 'line': number, 'event_id': event_id,
                                       'detail': 'event %s and event %s claim sequence %d; neither is kept'
                                                 % (escape_text(other), escape_text(event_id), claimed)})
                continue
            seen[event_id] = digest
            try:
                record, refused = parse_event(body, roots)
            except ContractFault as fault:
                faults.append({'code': fault.code, 'line': number, 'event_id': event_id, 'detail': fault.detail})
                continue
            rejected += refused
            if seq in contested or seq in by_seq:
                other = by_seq.pop(seq, None)
                if other is not None:
                    records.pop(other, None)
                contested.add(seq)  # a third claimant is refused too, never kept because the first two were dropped
                faults.append({'code': 'seq_reused', 'line': number, 'event_id': event_id,
                               'detail': 'event %s and event %s claim sequence %d; neither is kept'
                                         % (escape_text(other) if other else 'an earlier event',
                                            escape_text(event_id), seq)})
                continue
            records[event_id] = record
            by_seq[seq] = event_id
    ordered = sorted(records.values(), key=lambda item: item['seq'])
    return {'contract': RECORD_CONTRACT, 'header': header, 'check': _check(header, reason, len(seen), last_seq),
            'events': ordered, 'faults': faults, 'lines': lines, 'duplicate_lines': duplicates,
            'rejected_evidence': rejected}

