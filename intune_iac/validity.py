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

4. An open judgment is a durable row too (the open table, keyed like the version 2 expiry table, with the expiry, the
   boot session and the effective time at the judgment). It is committed in its own transaction while the locks are held and
   before the caller is handed its transaction, so a later failure, rollback or process death cannot erase it. A process
   that finds one from a session it cannot verify (another boot or clock domain, a boot time that went back, no readable
   boot source, a different process on a host that has none) holds that artifact until the wall clock passes its expiry,
   when it is closed and latched, or until it is prepared anew. Within the same verified session the row carries elapsed
   boot time, so it is a floor of its own even when the recorded time is gone.

The store is a parameter (Store: root directory, connection factory, expiry table, refusal function and codes).
clock.py owns the window rule, the recorded time and the boot session; this module only composes them.
"""
import fcntl
import math
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
_TABLE = re.compile(r'^[a-z][a-z0-9_]{0,63}$')

OPEN, CLOSED, HELD = 'open', 'closed', 'clock_moved_backward'
LOST = 'continuity_lost'


def table_sql(table):
    """The statement that creates a (version 1) expiry table. The name is a source literal checked here, never input.

    Version 1 is keyed by (issuer, nonce) alone, so it cannot tell two artifacts apart that reuse the pair. It is legacy
    only: rows made before the upgrade are never deleted or rewritten and are consulted permanently (matched on the full
    identity they store, in every domain), and nothing writes a new one. The judgment's own key is the version 2 table."""
    if type(table) is not str or not _TABLE.fullmatch(table):
        raise ValueError('An expiry table name is a short lowercase identifier.')
    return ('CREATE TABLE IF NOT EXISTS ' + table + ' (issuer TEXT NOT NULL, nonce TEXT NOT NULL, operation_id TEXT NOT NULL, '
            'request_sha256 TEXT NOT NULL, expires_at INTEGER NOT NULL, judged_at INTEGER NOT NULL, wall INTEGER NOT NULL, '
            'PRIMARY KEY(issuer,nonce))')


def v2_table(table):
    return table + '_v2'


def table_v2_sql(table):
    """The version 2 expiry table: one row per exact authorization artifact. The key is the family's domain, the issuer,
    the nonce, the operation and the request digest, the same key for insert and lookup, so an artifact that reuses
    another's (issuer, nonce) in the same store, in another family or for another job, is judged on its own."""
    table_sql(table)
    return ('CREATE TABLE IF NOT EXISTS ' + v2_table(table) + ' (domain TEXT NOT NULL, issuer TEXT NOT NULL, nonce TEXT NOT NULL, '
            'operation_id TEXT NOT NULL, request_sha256 TEXT NOT NULL, expires_at INTEGER NOT NULL, judged_at INTEGER NOT NULL, '
            'wall INTEGER NOT NULL, PRIMARY KEY(domain,issuer,nonce,operation_id,request_sha256))')


def open_table(table):
    return table + '_open'


def table_open_sql(table):
    """The open-judgment table: one row per artifact judged open, keyed like the version 2 expiry table. It is never
    deleted from; a later open judgment in the same session replaces the row, and one from a lost session never does."""
    table_sql(table)
    return ('CREATE TABLE IF NOT EXISTS ' + open_table(table) + ' (domain TEXT NOT NULL, issuer TEXT NOT NULL, nonce TEXT NOT NULL, '
            'operation_id TEXT NOT NULL, request_sha256 TEXT NOT NULL, expires_at INTEGER NOT NULL, boot_id TEXT, '
            'session_domain TEXT, boottime REAL, effective REAL NOT NULL, wall REAL NOT NULL, judged_at INTEGER NOT NULL, '
            'process TEXT NOT NULL, PRIMARY KEY(domain,issuer,nonce,operation_id,request_sha256))')


# Every authorization family's base expiry table, one per validity.Store construction in the package. History for the migration
# cutoff is any row in one of these (or its _v2 or _open table); a new family must be added here
# (plugin_tests/test_validity_registry.py fails otherwise).
FAMILIES = (
    'expired',            # approval_authority.py: the approval authority's store
    'adoption_expired',   # worker_adoption.py: adoption and recovery-plan approvals (_EXPIRED_TABLE)
    'service_expired',    # worker_service.py: service approvals (_EXPIRED_TABLE)
    'recovery_expired',   # worker_service.py: lease, committed-state, adoption and plan recovery (RECOVERY_EXPIRED_TABLE)
    'successor_expired',  # worker_successor.py: successor transfers (EXPIRED_TABLE)
    'broker_window',      # worker_broker.py: the broker's policy window
)
# The canonical cutoff table. Its leading underscore is the point: a family's base name must start with a letter (_TABLE), so no
# base, base_v2, base_open or base_cutoff (the name the per-family code gave its cutoff table) can ever equal it.
CUTOFF_TABLE = '_validity_cutoff'
_CUTOFF_COLUMNS = ['id', 'cutoff', 'written_wall', 'boot_id']


def cutoff_sql():
    """The canonical migration cutoff table: one database-level row, written once (a BEFORE INSERT trigger refuses a second
    row, which also stops INSERT OR REPLACE), never updated or deleted (triggers refuse both). Every family in the database
    reads this row. It lives in the store's own database, so removing the recorded-time file cannot erase it."""
    return ('CREATE TABLE IF NOT EXISTS ' + CUTOFF_TABLE + ' (id INTEGER PRIMARY KEY CHECK (id = 1), cutoff REAL NOT NULL, '
            'written_wall REAL NOT NULL, boot_id TEXT)')


def _freeze_cutoff(db):
    for action in ('UPDATE', 'DELETE'):
        db.execute('CREATE TRIGGER IF NOT EXISTS ' + CUTOFF_TABLE + '_no_' + action.lower() + ' BEFORE ' + action + ' ON ' +
                   CUTOFF_TABLE + " BEGIN SELECT RAISE(ABORT, 'the migration cutoff is never changed'); END")
    # Runs before conflict resolution, so INSERT OR REPLACE cannot replace the row even with recursive triggers off.
    db.execute('CREATE TRIGGER IF NOT EXISTS ' + CUTOFF_TABLE + '_no_second_row BEFORE INSERT ON ' + CUTOFF_TABLE +
               " WHEN EXISTS (SELECT 1 FROM " + CUTOFF_TABLE + ") BEGIN SELECT RAISE(ABORT, 'the migration cutoff is written once'); END")


def _read_cutoff(db):
    """The canonical cutoff, validated: None when the table does not exist or is empty (not yet written). A table with another
    schema, or anything but exactly one row with id 1 and a finite, non-negative cutoff, refuses judgment: it is the one record
    that decides which approvals are legacy, so a damaged one fails closed."""
    def invalid():
        return AppError('validity_cutoff_invalid', 'The migration cutoff record of this authorization store is not valid.')
    if not _has(db, CUTOFF_TABLE):
        return None
    if [column[1] for column in db.execute('PRAGMA table_info(' + CUTOFF_TABLE + ')').fetchall()] != _CUTOFF_COLUMNS:
        raise invalid()
    rows = db.execute('SELECT id, cutoff FROM ' + CUTOFF_TABLE).fetchall()
    if not rows:
        return None
    if len(rows) != 1 or rows[0][0] != 1 or type(rows[0][1]) not in (int, float) or not math.isfinite(rows[0][1]) or rows[0][1] < 0:
        raise invalid()
    return float(rows[0][1])


def _has(db, table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def latched(db, table, domain, payload, request_sha256):
    """Whether the exact artifact has an expiry record: plain reads, no write. A version 2 row must carry this domain and
    the artifact's issuer, nonce, operation and request digest. A version 1 row is a pre-upgrade record: it stores no
    domain, so it latches the artifact whose full stored identity (the same four fields) it carries, in every domain,
    permanently. Nothing writes version 1 rows any more, so every one of them is pre-upgrade and none can be mistaken for
    a mirror of a later judgment."""
    table_sql(table)
    identity = (payload['issuer'], payload['nonce'], payload['operation_id'], request_sha256)
    if _has(db, v2_table(table)) and db.execute(
            'SELECT 1 FROM ' + v2_table(table) + ' WHERE domain=? AND issuer=? AND nonce=? AND operation_id=? AND request_sha256=?',
            (domain,) + identity).fetchone():
        return True
    return _has(db, table) and bool(db.execute(
        'SELECT 1 FROM ' + table + ' WHERE issuer=? AND nonce=? AND operation_id=? AND request_sha256=?', identity).fetchone())


def _recorded(db, table):
    """How many records the store holds: the version 2 expiry rows, the open-judgment rows and the pre-upgrade version 1 rows
    (an artifact that was judged open and later closed counts in both: conservative, never a way round the cap)."""
    count = db.execute('SELECT count(*) FROM ' + v2_table(table)).fetchone()[0]
    count += db.execute('SELECT count(*) FROM ' + open_table(table)).fetchone()[0]
    if _has(db, table):
        count += db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
    return count


@dataclass(frozen=True)
class Store:
    """The authorization store one critical section runs on.

    root: the store's private directory (the lock directory; clock.json and clock.lock live in it).
    connect: () -> context manager yielding a sqlite3 connection with isolation_level=None and timeout=0.
    table: its expiry table, created by table_sql.
    fail: the store's own refusal function (code -> raises).
    capacity: the most expiry rows it keeps; at the cap the store fails closed with capacity_code.
    create: create the expiry tables inside the section when they are missing, for a store made before the tables existed.
    domain: the authorization family the store judges (for example the signature domain of the approval); it is part of
    the expiry key. Defaults to the table name. The version 2 table is always created inside the section.
    """
    root: Path
    connect: Callable
    table: str
    fail: Callable
    capacity: int = MAX_EXPIRED
    capacity_code: str = 'approval_store_capacity'
    private_code: str = 'approval_store_not_private'
    create: bool = False
    domain: str = None

    def __post_init__(self):
        table_sql(self.table)
        if self.table not in FAMILIES:
            # The migration cutoff counts history only in registered families' tables, so a family that is not registered
            # cannot be judged at all. The message names the field, not the value.
            raise AppError('validity_family_unregistered',
                           'The expiry table of this authorization store is not a registered family (validity.FAMILIES).')
        if self.domain is None:
            object.__setattr__(self, 'domain', self.table)


def judge(reading, expires_at, deadline, latched):
    """The pure judgment: CLOSED, HELD (validity cannot be established) or OPEN.

    A reached expiry outranks a hold: the effective time never goes back, so a window that closed stays closed while
    the wall clock reads earlier. The window rule itself is clock.window_state. Expiry compares against the effective
    time with no added tolerance; the tolerance only classifies backward steps."""
    state = clock.window_state(reading, 0, expires_at)
    if (latched or state == 'closed' or reading['wall'] >= expires_at
            or (deadline is not None and time.monotonic() >= deadline)):
        return CLOSED
    return HELD if state == 'clock_moved_backward' else OPEN


def peek(root, expires_at, deadline, latched):
    """The judgment for a periodic check, without the critical section: it takes no lock, begins no transaction and
    persists nothing. Returns (state, reading). The reading is clock.Floor.peek: the effective time from the recorded
    high-water mark, the boot time carried since it was recorded and this process's carried time (this process's anchor is
    updated, which is fine for a permit that belongs to the running process). The caller reads whether an expiry record
    exists with a plain SELECT and passes it as latched. A CLOSED state is then recorded through critical, and a HELD state
    is refused, by the caller."""
    reading = clock.Floor(Path(root) / 'clock.json').peek(time.time())
    return judge(reading, expires_at, deadline, latched), reading


def effective_now(root):
    """The effective time now from the store's recorded floor: the wall clock, the mark, and the mark carried by the boot
    time elapsed since it was recorded. Reads only; a damaged or unreadable record falls back to the wall clock, because the
    section that judges will refuse it."""
    wall = time.time()
    try:
        floor = clock.Floor(Path(root) / 'clock.json')
        recorded = floor.record()
    except AppError:
        return wall
    carried = floor.carried(recorded)
    return max(value for value in (wall, None if recorded is None else recorded['high_water'], carried) if value is not None)


def deadline(root, expires_at):
    """This process's monotonic deadline for an expiry, armed from the effective time, not the bare wall clock: a wall clock
    set back, in this process or before it started, cannot give the artifact more time than the floor says is left."""
    return time.monotonic() + max(0, expires_at - effective_now(root))


def hold(reading):
    """The refusal for a backward step: the approval is held, not judged, and it says how to recover. When the floor the
    clock reads behind includes boot time carried since it was recorded, only two exits work (a new boot of the host, or the
    host clock set to at least the recorded time): waiting, restarting and a new approval are all held the same way for the
    rest of the boot, so that case does not offer them."""
    carried = reading.get('carried')
    if carried is not None and carried > (reading.get('mark') or 0):
        return AppError('clock_moved_backward',
            "Approval held: this host's clock reads %d, earlier than the time %d this approval store recorded, so whether "
            'the approval is still valid cannot be established. The recorded time includes the time this host has run since '
            'it was recorded, so restarting does not clear this, and neither does a new approval or verifying again. Either '
            'start a new boot of this host (for example wsl --shutdown), or set the host clock to at least the recorded '
            'time %d.' % (reading['wall'], reading['floor'], reading['floor']))
    return AppError('clock_moved_backward',
        "Approval held: this host's clock reads %d, earlier than the time %d this approval store recorded, so whether the "
        'approval is still valid cannot be established. Correct the host clock, or wait until it reads at or after the '
        'recorded time, then restart; verifying again does not clear this.' % (reading['wall'], reading['floor']))


def hold_lost(expires_at, legacy=False):
    """The refusal for lost continuity: the artifact was judged open in a session that cannot be verified now, so how much
    of its time has passed since cannot be established. Distinct from the backward-clock message; it names both exits. A
    legacy artifact (issued before this store recorded the boot session, with no record of being judged since) is held for the
    same reason."""
    if legacy:
        reason = ('it was issued before this store began recording the time that passes across restarts and nothing shows '
                  'whether it was judged open since')
    else:
        reason = ('it was judged open in an earlier session of this host (another boot or clock domain, or one that cannot be '
                  'verified now)')
    return AppError('clock_moved_backward',
                    'Approval held: %s, so how much of its time has passed since cannot be established. It stays held until '
                    'the host clock reads at or after its expiry at %d, when it is closed, or until it is prepared anew; '
                    'verifying again does not clear this.' % (reason, expires_at))


def hold_if_clock_behind(root):
    """Explain a backward step before an unauthenticated input is refused for its wall-relative time.

    This runs before authentication, so it only reads the persisted record (a rename replaces the file, so a lockless read
    is whole), applies the boot floor from it, and records nothing: not the file, not this process's anchor. A damaged or
    unreadable record falls through to the caller's original refusal, never to acceptance. The recorded time is written only
    inside critical, after authentication."""
    try:
        floor = clock.Floor(Path(root) / 'clock.json')
        recorded = floor.record()
        carried = floor.carried(recorded)
    except AppError:
        return
    wall = time.time()
    if recorded is None or type(wall) not in (int, float):
        return
    mark = recorded['high_water']
    top = max(mark, mark if carried is None else carried)
    reading = {'wall': wall, 'floor': top, 'effective': max(wall, top), 'backward': wall < top - clock.TOLERANCE_SECONDS,
               'mark': mark, 'carried': carried}
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


def _open_row(db, store, payload, request_sha256):
    row = db.execute('SELECT boot_id, session_domain, boottime, effective, process FROM ' + open_table(store.table) +
                     ' WHERE domain=? AND issuer=? AND nonce=? AND operation_id=? AND request_sha256=?',
                     (store.domain, payload['issuer'], payload['nonce'], payload['operation_id'], request_sha256)).fetchone()
    if row is None:
        return None
    session = None if row[0] is None else {'boot_id': row[0], 'domain': row[1], 'boottime': row[2]}
    return {'session': session, 'effective': row[3], 'process': row[4]}


def _view(reading, row):
    """The reading as an earlier open judgment of the same artifact sees it: (view, lost). In the same verified session the
    row carries its effective time forward by the boot time elapsed since, a floor of its own. In any other session it
    cannot be carried and the artifact is lost to this process; on a host with no boot source only the process that
    wrote the row is still its session."""
    if row is None:
        return reading, False
    now = reading['session']
    if row['session'] is None:
        return reading, not (now is None and row['process'] == clock.process_token())
    if not clock.same_session(row['session'], now):
        return reading, True
    carried = row['effective'] + (now['boottime'] - row['session']['boottime'])
    if carried <= reading['floor']:
        return reading, False
    view = dict(reading, floor=carried, effective=max(reading['effective'], carried), carried=carried)
    view['backward'] = view['wall'] < carried - clock.TOLERANCE_SECONDS
    return view, False


def _quoted(name):
    return '"' + name.replace('"', '""') + '"'


def _first_cutoff(db, floor, wall):
    """The canonical cutoff's first value, computed once under the locks: the migration time now when the store has any
    history, which is a recorded time or any row, whatever its columns, in a registered family's base, version 2 or open table
    (FAMILIES: nothing outside the registry counts, so registry rows such as jobs and ownership, which every live store has
    before its first judgment, are not history); otherwise 0. Older per-family cutoff tables are never read: holding more
    approvals as legacy is the recoverable direction."""
    recorded = floor.record()
    existing = {name for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    populated = any(
        name in existing and db.execute('SELECT 1 FROM ' + _quoted(name) + ' LIMIT 1').fetchone()
        for family in FAMILIES for name in (family, v2_table(family), open_table(family)))
    if recorded is None and not populated:
        return 0.0
    carried = floor.carried(recorded)
    return float(max(v for v in (wall, None if recorded is None else recorded['high_water'], carried) if v is not None))


def _ensure_cutoff(store, floor, wall):
    """Write the database's canonical migration cutoff if it has none: once, at the first judgment of any family under the boot
    session, in a transaction of its own that commits before the recorded time is touched. A refusal that follows cannot roll
    it back, and a failed first attempt cannot make the store look as if it had a history, because the clock record is still as
    the old code left it. An artifact issued at or before the cutoff that has no open row was judged, if at all, by code that
    kept no record, and is held."""
    with store.connect() as db:
        if _read_cutoff(db) is not None:
            return
        db.execute('BEGIN IMMEDIATE')
        if _read_cutoff(db) is not None:  # another process wrote it while this one waited for the write reservation
            db.execute('COMMIT')
            return
        existing = {name for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if any(open_table(family) in existing and db.execute('SELECT 1 FROM ' + _quoted(open_table(family)) + ' LIMIT 1').fetchone()
               for family in FAMILIES):
            # An open judgment is only ever written under a canonical cutoff, so a populated open table with no cutoff means the
            # record was lost (dropped, or recreated empty). Writing a new, later one would re-hold approvals that were current.
            raise AppError('validity_cutoff_invalid',
                           'The migration cutoff record of this authorization store is missing, so it cannot establish which '
                           'approvals predate its migration. Start a new store, or restore the record from a backup.')
        db.execute(cutoff_sql())
        _freeze_cutoff(db)
        value = _first_cutoff(db, floor, wall)
        session = clock.session()
        db.execute('INSERT INTO ' + CUTOFF_TABLE + ' VALUES (1, ?, ?, ?)', (value, wall, None if session is None else session['boot_id']))
        db.execute('COMMIT')
        _sync(store.root)


def _judged(store, floor, payload, request_sha256, deadline):
    closed = False
    with floor.locked():
        wall = time.time()
        _ensure_cutoff(store, floor, wall)
        reading = floor.observe_locked(wall)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if store.create:
                db.execute(table_sql(store.table))
            else:
                db.execute('SELECT 1 FROM ' + store.table + ' LIMIT 0')  # the store made its table; a missing one is an error
            db.execute(table_v2_sql(store.table))
            db.execute(table_open_sql(store.table))
            cutoff = _read_cutoff(db)
            if cutoff is None:
                raise AppError('validity_cutoff_invalid', 'The migration cutoff record of this authorization store is not valid.')
            row = _open_row(db, store, payload, request_sha256)
            view, lost = _view(reading, row)
            issued = payload.get('issued_at')
            legacy = (row is None and cutoff > 0 and type(issued) in (int, float) and issued <= cutoff)
            lost = lost or legacy
            state = judge(view, payload['expires_at'], deadline,
                          latched(db, store.table, store.domain, payload, request_sha256))
            if state == OPEN and lost:
                state = LOST
            if state == CLOSED:
                if _recorded(db, store.table) >= store.capacity:
                    store.fail(store.capacity_code)
                values = (payload['issuer'], payload['nonce'], payload['operation_id'], request_sha256,
                          payload['expires_at'], int(reading['effective']), int(reading['wall']))
                db.execute('INSERT OR IGNORE INTO ' + v2_table(store.table) + ' VALUES (?,?,?,?,?,?,?,?)', (store.domain,) + values)
                db.execute('COMMIT')
                _sync(store.root)
                closed = True
            elif state == HELD:
                raise hold(view)
            elif state == LOST:
                raise hold_lost(payload['expires_at'], legacy=legacy)
            else:
                # The open judgment is durable before the caller is handed its transaction: committed on its own, under the
                # locks, so the caller's later failure or rollback, or the process dying, cannot erase it.
                if row is None and _recorded(db, store.table) >= store.capacity:
                    store.fail(store.capacity_code)
                session = reading['session']
                db.execute('INSERT OR REPLACE INTO ' + open_table(store.table) + ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (store.domain, payload['issuer'], payload['nonce'], payload['operation_id'], request_sha256,
                            payload['expires_at'], None if session is None else session['boot_id'],
                            None if session is None else session['domain'], None if session is None else session['boottime'],
                            reading['effective'], reading['wall'], int(reading['wall']), clock.process_token()))
                db.execute('COMMIT')
                _sync(store.root)
                db.execute('BEGIN IMMEDIATE')
                yield db
    return closed
