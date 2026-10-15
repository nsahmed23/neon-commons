"""Time authority for validity windows, such as an approval's expiry.

Wall time (seconds since the epoch) is the only portable timestamp: it is what gets persisted and compared across
processes. A wall clock can step backward (this project's host steps by 266 seconds every few seconds), so a validity
window judged on the bare wall clock could reopen after it closed. Three rules prevent that:

1. A durable high-water mark, kept in a small JSON file beside what it guards, records the latest effective time any
   check saw (the wall clock or this process's carried reading, whichever was later). It only rises.
2. Within one process, monotonic time carries the latest wall time this process saw for the same guarded thing forward
   by the elapsed time. It is never persisted and never compared across processes or guarded things.
3. The effective time is the greatest of the wall clock, the high-water mark and the process floor, so it never goes
   back. A wall clock reading earlier than that floor by more than TOLERANCE_SECONDS is a backward step: the true time
   cannot be established, so a guarded mutation is held (the caller refuses it) until the clock reads at or after the
   floor again, or the guarded thing is prepared anew.

This detects a backward step between any two readings this store recorded or this process made. It cannot detect skew
between hosts that never shared a recorded time, and claims nothing about it.
"""
import json
import math
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .io import AppError, write_json

TOLERANCE_SECONDS = 2
SCHEMA = 'intune-clock-floor/1'

# Injectable for tests; the process floor uses it only for elapsed time within this process.
monotonic = time.monotonic

# Per guarded thing: the (wall, monotonic) pair of the latest wall time this process saw for it. Keyed by the guarded
# file, so one operation's readings never judge another's, and kept only in memory.
_ANCHORS = {}


def reset_process_anchor():
    """Forget this process's floors (tests use it to stand for a new process)."""
    _ANCHORS.clear()


def _process_floor(key, wall):
    """The latest wall time this process saw for key, carried forward by monotonic time; updated with this reading."""
    now = monotonic()
    anchor = _ANCHORS.get(key)
    carried = None if anchor is None else anchor[0] + (now - anchor[1])
    if carried is None or wall > carried:
        _ANCHORS[key] = (wall, now)
        return wall
    return carried


class Floor:
    """The durable high-water mark of wall time for one guarded thing (one file)."""

    def __init__(self, path):
        self.path = Path(path)

    def high_water(self):
        """The recorded high-water mark, or None when nothing was recorded yet. A damaged record fails closed."""
        if not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_bytes())
        except (OSError, ValueError) as error:
            raise AppError('clock_floor_invalid', 'The recorded time for this operation cannot be read.') from error
        seconds = value.get('high_water') if isinstance(value, dict) and value.get('schema_version') == SCHEMA else None
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise AppError('clock_floor_invalid', 'The recorded time for this operation cannot be read.')
        return seconds

    @contextmanager
    def locked(self):
        """Hold the floor's lock (clock.lock beside it), so the read, comparison and write of the high-water mark, and
        anything a caller decides from them, are one step no other process can interleave with."""
        try:
            import fcntl
        except ImportError as error:
            raise AppError('clock_lock_unavailable', 'The recorded time cannot be locked on this host.') from error
        fd = os.open(self.path.with_name(self.path.stem + '.lock'),
                     os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield self
        finally:
            os.close(fd)

    def observe(self, wall, *, persist=True):
        """Judge one wall-clock reading against the floor; record it, under the lock, when it is the latest seen.

        Returns {'wall', 'floor', 'effective', 'backward'}: effective never goes back; backward is true when the
        reading is earlier than the floor by more than TOLERANCE_SECONDS.
        """
        if not persist:
            return self.observe_locked(wall, persist=False)
        with self.locked():
            return self.observe_locked(wall)

    def observe_locked(self, wall, *, persist=True):
        """observe, for a caller that already holds locked(), or that records nothing."""
        if type(wall) not in (int, float) or not math.isfinite(wall) or wall < 0:
            raise AppError('clock_reading_invalid', 'The host clock returned an unusable time.')
        recorded = self.high_water()
        process = _process_floor(str(self.path), wall)
        floor = max(value for value in (recorded, process) if value is not None)
        backward = wall < floor - TOLERANCE_SECONDS
        effective = max(wall, floor)
        # The effective time, not the bare reading: a restart must keep what this process knew (temporal gate S7).
        if persist and (recorded is None or effective > recorded):
            write_json(self.path, {'schema_version': SCHEMA, 'high_water': effective})
        return {'wall': wall, 'floor': floor, 'effective': effective, 'backward': backward}

    def peek(self, wall):
        """observe without recording anything: for read-only views."""
        return self.observe(wall, persist=False)
