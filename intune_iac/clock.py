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

4. The store also records, in the same write as the mark, the host's boot session: the boot identity
   (/proc/sys/kernel/random/boot_id, read fresh at every observation, never cached), the clock domain (the time-namespace
   offset line, where the kernel has one) and CLOCK_BOOTTIME at the reading that set the mark. Within the same boot and
   clock domain the floor also includes the mark plus the boot time elapsed since it was recorded, which a wall clock
   cannot move, so a new process carries the time that passed while no process ran. A different boot, a different
   domain, a boot time that went backward, or no readable boot source is lost continuity: the carried part is dropped
   (the mark alone remains) and the caller, which knows whether it had judged something open, holds it.

The stored boot time is a coordinate paired with its boot identity and used only as a difference within that boot; it is
never compared across boots and never derived into a floor from a mismatched identity.

This detects a backward step between any two readings this store recorded or this process made, and, within one boot,
across processes. It cannot detect skew between hosts that never shared a recorded time, a snapshot restore that brings
back both clocks and the records, or a stall of the boot clock that the kernel does not count (a paused virtual machine
may not): there the protection falls back to the mark, which is the safe direction. It claims nothing about those.
"""
import json
import math
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .io import AppError, write_json

TOLERANCE_SECONDS = 2
SCHEMA_1 = 'intune-clock-floor/1'
SCHEMA = 'intune-clock-floor/2'
_SCHEMAS = (SCHEMA_1, SCHEMA)

# Injectable for tests; the process floor uses it only for elapsed time within this process.
monotonic = time.monotonic


def _read_boot_id():
    """The kernel's identity of this boot, read fresh every time (a cached value would let a restored or forked process
    compare against a foreign boot). None when the host has no readable one."""
    try:
        with open('/proc/sys/kernel/random/boot_id') as stream:
            value = stream.read(128).strip()
    except OSError:
        return None
    return value if 32 <= len(value) <= 36 and all(c in '0123456789abcdefABCDEF-' for c in value) else None


def _read_domain():
    """The clock domain: the time-namespace offset line for CLOCK_BOOTTIME. A kernel without time namespaces has none,
    which is a domain of its own (the empty string); an unreadable one is None (unverified)."""
    try:
        with open('/proc/self/timens_offsets') as stream:
            for line in stream.read(4096).splitlines():
                parts = line.split()
                if parts and parts[0] == 'boottime':
                    return ' '.join(parts)
        return ''
    except FileNotFoundError:
        return ''
    except OSError:
        return None


def _read_boottime():
    try:
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    except (AttributeError, OSError):
        return None


# Injectable for tests, the way monotonic is. Each is called at every observation.
boot_id = _read_boot_id
clock_domain = _read_domain
boottime = _read_boottime


def session():
    """The boot session now, {'boot_id', 'domain', 'boottime'}, or None when any part is missing or unusable."""
    identity, domain, elapsed = boot_id(), clock_domain(), boottime()
    if (type(identity) is not str or not identity or type(domain) is not str
            or type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0):
        return None
    return {'boot_id': identity, 'domain': domain, 'boottime': float(elapsed)}


def same_session(recorded, now):
    """Whether a recorded session and the current one share a boot and clock domain, and the boot time did not go back.
    The one rule the file and the open-judgment rows share."""
    return (recorded is not None and now is not None and recorded['boot_id'] == now['boot_id']
            and recorded['domain'] == now['domain'] and now['boottime'] >= recorded['boottime'])

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


def window_state(reading, created_at, expires_at):
    """The approval window's state for one reading (Floor.observe or Floor.peek): the one rule execution and views
    share. 'closed' when the effective time reached the expiry (it never goes back, so this comes first, even
    while the wall clock reads earlier); 'clock_moved_backward' when validity cannot be established (a backward
    step, or a time before creation); otherwise 'open'. Pure: callers commit effects (execution records the
    expiry and refuses) or render it (views record nothing)."""
    if reading['effective'] >= expires_at:
        return 'closed'
    if reading['backward'] or reading['effective'] < created_at:
        return 'clock_moved_backward'
    return 'open'


class Floor:
    """The durable high-water mark of wall time for one guarded thing (one file)."""

    def __init__(self, path):
        self.path = Path(path)

    def record(self):
        """The recorded floor, {'high_water', 'session'}, or None when nothing was recorded yet. 'session' is None for a
        schema 1 file or a record made without a boot source. A damaged record, including a schema 2 record whose session
        is malformed, fails closed."""
        if not self.path.exists():
            return None
        invalid = AppError('clock_floor_invalid', 'The recorded time for this operation cannot be read.')
        try:
            value = json.loads(self.path.read_bytes())
        except (OSError, ValueError) as error:
            raise invalid from error
        seconds = value.get('high_water') if isinstance(value, dict) and value.get('schema_version') in _SCHEMAS else None
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise invalid
        if value['schema_version'] == SCHEMA_1:
            return {'high_water': seconds, 'session': None}
        parts = (value.get('boot_id'), value.get('domain'), value.get('boottime'))
        if all(part is None for part in parts):
            return {'high_water': seconds, 'session': None}
        if (type(parts[0]) is not str or not parts[0] or type(parts[1]) is not str
                or type(parts[2]) not in (int, float) or not math.isfinite(parts[2]) or parts[2] < 0):
            raise invalid
        return {'high_water': seconds, 'session': {'boot_id': parts[0], 'domain': parts[1], 'boottime': float(parts[2])}}

    def high_water(self):
        """The recorded high-water mark, or None when nothing was recorded yet. A damaged record fails closed."""
        recorded = self.record()
        return None if recorded is None else recorded['high_water']

    def carried(self, recorded=None, now=None):
        """The recorded mark carried forward by the boot time elapsed since it was recorded, when the boot and clock domain
        are the same and the boot time did not go back; otherwise None. Reads only; takes no lock."""
        recorded = self.record() if recorded is None else recorded
        if recorded is None or recorded['session'] is None:
            return None
        now = session() if now is None else now
        if not same_session(recorded['session'], now):
            return None
        return recorded['high_water'] + (now['boottime'] - recorded['session']['boottime'])

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
        recorded = self.record()
        mark = None if recorded is None else recorded['high_water']
        now = session()
        carried = self.carried(recorded, now)
        # Lost continuity: a session was recorded and cannot be verified now (another boot or domain, a boot time that went
        # back, no readable boot source). The carried part is then unknown, and holders of open judgments hold them.
        lost = recorded is not None and recorded['session'] is not None and carried is None
        process = _process_floor(str(self.path), wall)
        floor = max(value for value in (mark, process, carried) if value is not None)
        backward = wall < floor - TOLERANCE_SECONDS
        effective = max(wall, floor)
        # The effective time, not the bare reading: a restart must keep what this process knew (temporal gate S7). It is
        # paired in the same write with the boot session sampled for this observation, so the stored pair is one instant.
        rises = mark is None or effective > mark
        if persist and (rises or (recorded is not None and recorded['session'] is None and now is not None)):
            write_json(self.path, {'schema_version': SCHEMA, 'high_water': max(effective, mark or 0),
                                   'boot_id': None if now is None else now['boot_id'],
                                   'domain': None if now is None else now['domain'],
                                   'boottime': None if now is None else now['boottime']})
        return {'wall': wall, 'floor': floor, 'effective': effective, 'backward': backward, 'mark': mark,
                'carried': carried, 'continuity_lost': lost, 'session': now}

    def peek(self, wall):
        """observe without recording anything: for read-only views."""
        return self.observe(wall, persist=False)
