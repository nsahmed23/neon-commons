"""Bounded JSON and atomic local persistence; diagnostics never echo input."""
from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import tempfile
from pathlib import Path

MAX_BYTES = 16 * 1024 * 1024


class AppError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_bytes(path):
    try:
        # Nonblocking open lets us reject pipes/devices without waiting on them.
        fd = os.open(Path(path), os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise AppError('invalid_file', 'Input must be a regular local file.')
            if info.st_nlink != 1:
                raise AppError('unsafe_file_identity', 'Hard-linked input files are not supported.')
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise AppError('input_too_large', 'Input exceeds the 16 MiB limit.')
        return data
    except OSError:
        raise AppError('unreadable_file', 'A required local file could not be read.') from None


def file_sha(path):
    return hashlib.sha256(read_bytes(path)).hexdigest()


def parse_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('nonfinite')
    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
        stack = [(value, 0)]
        while stack:
            item, depth = stack.pop()
            if depth > 64: raise ValueError('depth')
            if isinstance(item, float) and not math.isfinite(item): raise ValueError('number')
            if isinstance(item, int) and not isinstance(item, bool) and abs(item) > 9007199254740991:
                raise ValueError('integer')
            if isinstance(item, dict): stack.extend((v, depth + 1) for v in item.values())
            elif isinstance(item, list): stack.extend((v, depth + 1) for v in item)
        canonical(value)  # Reject unpaired Unicode surrogates before persistence.
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise AppError('invalid_json', 'JSON must have unique keys, bounded depth, and finite values.') from None


def load_json(path):
    return parse_json(read_bytes(path))


def sync_directory(path):
    """Persist a namespace change; failure must prevent a durable acknowledgement."""
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def mkdir_durable(path, *, mode=0o700):
    """Create missing directories and persist their entries before continuing."""
    path = Path(path)
    created = []; parent = path
    while not parent.exists():
        created.append(parent); parent = parent.parent
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    for directory in created:
        sync_directory(directory)
        sync_directory(directory.parent)


def write_json(path, value):
    destination = Path(path).absolute()
    data = canonical(value) + b'\n'
    if len(data) > MAX_BYTES: raise AppError('output_too_large', 'JSON output exceeds the size limit.')
    if any(p.is_symlink() for p in [destination, *destination.parents]):
        raise AppError('unsafe_path', 'Symlinked persistence paths are not supported.')
    temporary = None
    try:
        # Record newly created directory entries as well as the file rename.
        # fsync(file) alone cannot make either namespace operation durable.
        created = []
        parent = destination.parent
        while not parent.exists():
            created.append(parent)
            parent = parent.parent
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix='.intune-write-', dir=destination.parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, destination)
        for directory in dict.fromkeys([destination.parent, *(path.parent for path in created)]):
            sync_directory(directory)
    except OSError:
        raise AppError('write_failed', 'Local JSON persistence failed.') from None
    finally:
        if temporary: Path(temporary).unlink(missing_ok=True)
