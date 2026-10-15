"""One shared decision for whether a signed approval is still valid when it is about to be used.

A signed approval carries an expiry. Judged on the bare wall clock, an expiry reopens when the clock steps back, and
it can be reached between a check and the effect the check was meant to guard. This module is the single place that
decides, and every authorization store consumes it rather than copying it:

1. The store's root directory is locked first. It is opened and verified by device and inode, so no deletion or
   replacement of a state file can hand a second process a different lock for the same store.
2. Then the recorded-time lock (clock.Floor) and a SQLite write transaction (BEGIN IMMEDIATE), in that order.
3. The window is judged on the effective time (never back), this process's monotonic deadline and an earlier expiry
   record. A reached expiry is recorded in the store's own expiry table (capped, so the caller must have authenticated
   the receipt first) and refused. A backward step is held, with the recovery words. Otherwise the open transaction is
   handed to the caller, who commits its consumption or dispatch insert inside it, so no other process can latch the
   expiry between the judgment and the effect.

The store is a parameter (Store: root directory, connection factory, expiry table, refusal function and codes).
clock.py owns the window rule and the recorded time; this module only composes them.
"""
import fcntl
import os
import re
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import clock
from .io import AppError
from .protected import _path, _sync

MAX_EXPIRED = 100000
_TABLE = re.compile(r'^[a-z][a-z_]{0,63}$')

OPEN, CLOSED, HELD = 'open', 'closed', 'clock_moved_backward'


def table_sql(table):
    """The statement that creates an expiry table. The name is a source literal checked here, never input."""
    if type(table) is not str or not _TABLE.fullmatch(table):
        raise ValueError('An expiry table name is a short lowercase identifier.')
    return ('CREATE TABLE IF NOT EXISTS ' + table + ' (issuer TEXT NOT NULL, nonce TEXT NOT NULL, operation_id TEXT NOT NULL, '
            'request_sha256 TEXT NOT NULL, expires_at INTEGER NOT NULL, judged_at INTEGER NOT NULL, wall INTEGER NOT NULL, '
            'PRIMARY KEY(issuer,nonce))')


@dataclass(frozen=True)
class Store:
    """The authorization store one critical section runs on.

    root: the store's private directory (the lock directory; clock.json and clock.lock live in it).
    connect: () -> context manager yielding a sqlite3 connection with isolation_level=None and timeout=0.
    table: its expiry table, created by table_sql.
    fail: the store's own refusal function (code -> raises).
    capacity: the most expiry rows it keeps; at the cap the store fails closed with capacity_code.
    create: create the expiry table inside the section when it is missing, for a store made before the table existed.
    """
    root: Path
    connect: Callable
    table: str
    fail: Callable
    capacity: int = MAX_EXPIRED
    capacity_code: str = 'approval_store_capacity'
    private_code: str = 'approval_store_not_private'
    create: bool = False

    def __post_init__(self):
        table_sql(self.table)


def judge(reading, expires_at, deadline, latched):
    """The pure judgment: CLOSED, HELD (validity cannot be established) or OPEN.

    A reached expiry outranks a hold: the effective time never goes back, so a window that closed stays closed while
    the wall clock reads earlier. The window rule itself is clock.window_state."""
    state = clock.window_state(reading, 0, expires_at)
    if (latched or state == 'closed' or reading['wall'] >= expires_at
            or (deadline is not None and time.monotonic() >= deadline)):
        return CLOSED
    return HELD if state == 'clock_moved_backward' else OPEN


def peek(root, expires_at, deadline, latched):
    """The judgment for a periodic check, without the critical section: it takes no lock, begins no transaction and
    persists nothing. Returns (state, reading). The reading is clock.Floor.peek: the effective time from the recorded
    high-water mark and this process's carried time (this process's anchor is updated, which is fine for a permit
    that belongs to the running process). The caller reads whether an expiry record exists with a plain SELECT and
    passes it as latched. A CLOSED state is then recorded through critical, and a HELD state is refused, by the caller."""
    reading = clock.Floor(Path(root) / 'clock.json').peek(time.time())
    return judge(reading, expires_at, deadline, latched), reading


def hold(reading):
    """The refusal for a backward step: the approval is held, not judged, and it says how to recover."""
    return AppError('clock_moved_backward',
                    "Approval held: this host's clock reads %d, earlier than the time %d this approval store recorded, "
                    'so whether the approval is still valid cannot be established. Correct the host clock, or wait until '
                    'it reads at or after the recorded time, then restart; verifying again does not clear this.'
                    % (reading['wall'], reading['floor']))


def hold_if_clock_behind(root):
    """Explain a backward step before an unauthenticated input is refused for its wall-relative time.

    This runs before authentication, so it only reads the persisted high-water mark (a rename replaces the file, so a
    lockless read is whole) and records nothing: not the file, not this process's anchor. A damaged or unreadable
    record falls through to the caller's original refusal, never to acceptance. The recorded time is written only
    inside critical, after authentication."""
    try:
        recorded = clock.Floor(Path(root) / 'clock.json').high_water()
    except AppError:
        return
    wall = time.time()
    if recorded is None or type(wall) not in (int, float):
        return
    reading = {'wall': wall, 'floor': recorded, 'effective': max(wall, recorded),
               'backward': wall < recorded - clock.TOLERANCE_SECONDS}
    if reading['backward']:
        raise hold(reading)


def _private_directory(store):
    path = _path(store.root)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        store.fail(store.private_code)


@contextmanager
def critical(store, payload, request_sha256, deadline=None, expired_code='approval_expired'):
    """The critical section for an approval's validity. Lock order: the store directory, the recorded-time lock, then
    a SQLite write transaction; none is released between the final window judgment and the caller's commit. A reached
    expiry (the effective time, this process's monotonic deadline, or an earlier record) is recorded and refused here
    with expired_code; a backward step is held. Otherwise it yields the open transaction and the caller commits its
    insert inside it.

    payload needs issuer, nonce, operation_id and expires_at, and must come from a receipt that authenticated: an
    expiry row is written for it."""
    floor = clock.Floor(store.root / 'clock.json')
    # The recorded-time lock is per inode, so deleting clock.lock would let a second process lock a new file; the
    # directory is the one object that cannot be replaced under a running critical section.
    directory = os.open(store.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        opened, current = os.fstat(directory), os.stat(store.root)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            store.fail(store.private_code)
        _private_directory(store)
        fcntl.flock(directory, fcntl.LOCK_EX)
        closed = yield from _judged(store, floor, payload, request_sha256, deadline)
    finally:
        os.close(directory)
    if closed:
        store.fail(expired_code)


def _judged(store, floor, payload, request_sha256, deadline):
    closed = False
    with floor.locked():
        reading = floor.observe_locked(time.time())
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if store.create:
                db.execute(table_sql(store.table))
            latched = db.execute('SELECT 1 FROM ' + store.table + ' WHERE issuer=? AND nonce=?',
                                 (payload['issuer'], payload['nonce'])).fetchone()
            state = judge(reading, payload['expires_at'], deadline, bool(latched))
            if state == CLOSED:
                if db.execute('SELECT count(*) FROM ' + store.table).fetchone()[0] >= store.capacity:
                    store.fail(store.capacity_code)
                db.execute('INSERT OR IGNORE INTO ' + store.table + ' VALUES (?,?,?,?,?,?,?)',
                           (payload['issuer'], payload['nonce'], payload['operation_id'], request_sha256,
                            payload['expires_at'], int(reading['effective']), int(reading['wall'])))
                db.execute('COMMIT')
                _sync(store.root)
                closed = True
            elif state == HELD:
                raise hold(reading)
            else:
                yield db
    return closed
