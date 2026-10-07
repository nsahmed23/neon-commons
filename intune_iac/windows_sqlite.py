"""Inactive native Windows read-only SQLite snapshot boundary.

Held native handles deny ordinary writes/deletion while SQLite reads immutable
rollback-mode bytes. WAL, hot journals and unsupported paths fail closed. This
does not enable Workbench storage, perform recovery, or prove native behavior.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import ctypes as C
import hashlib
import sqlite3
from urllib.parse import quote

from .io import AppError
from . import windows_directory as wd, windows_storage as ws

SCHEMA = 'intune-windows-sqlite-snapshot/1'
MAX_ROWS = 1000
MAX_RESULT_BYTES = 16 * 1024 * 1024
MAX_STEPS = 10000000
_READ_PRAGMAS = frozenset({'user_version', 'schema_version', 'application_id',
    'table_info', 'table_xinfo', 'index_list', 'index_info', 'foreign_key_list',
    'foreign_key_check', 'quick_check', 'integrity_check', 'query_only'})
_ARGUMENT_PRAGMAS = frozenset({'table_info', 'table_xinfo', 'index_list', 'index_info',
    'foreign_key_list', 'foreign_key_check'})
_FUNCTIONS = frozenset({'count', 'sum', 'min', 'max', 'avg', 'total', 'coalesce',
    'ifnull', 'nullif', 'length', 'lower', 'upper', 'substr', 'substring', 'typeof',
    'abs', 'round', 'hex', 'quote', 'iif'})


def _fail(code):
    raise AppError(code, 'The inactive native SQLite snapshot contract was not established.') from None


class _Win32Snapshot(ws._Win32Storage):
    def open_read_guard(self, path, *, optional=False):
        # GENERIC_READ | READ_CONTROL; FILE_SHARE_READ only. Ordinary existing
        # writers cause a sharing violation, and new write/delete opens fail
        # while this handle remains held. No ACL changes or privilege expansion.
        handle = self.k.CreateFileW(path, 0x80020000, 1, None, 3, 0x08200000, None)
        error = C.get_last_error()
        if handle in (None, C.c_void_p(-1).value):
            if optional and error in (2, 3):
                return None
            _fail('windows_sqlite_read_guard_failed')
        return handle


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _header(data):
    if len(data) < 100 or data[:16] != b'SQLite format 3\x00':
        _fail('windows_sqlite_header_invalid')
    if data[18:20] != b'\x01\x01':
        _fail('windows_sqlite_wal_or_format_unsupported')
    page_size = int.from_bytes(data[16:18], 'big')
    if page_size == 1:
        page_size = 65536
    if page_size < 512 or page_size > 65536 or page_size & (page_size - 1) or len(data) % page_size:
        _fail('windows_sqlite_header_invalid')


def _authorizer(action, first, second, database, source):
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (second or '').lower() in _FUNCTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA:
        name = (first or '').lower()
        if name in _READ_PRAGMAS and (second is None or name in _ARGUMENT_PRAGMAS):
            return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class _Snapshot:
    def __init__(self, connection, receipt):
        self._connection = connection
        self._receipt = receipt
        self._active = True

    def receipt(self):
        if not self._active:
            _fail('windows_sqlite_snapshot_closed')
        # Detached plain values cannot mutate the capability's observation.
        import copy
        return copy.deepcopy(self._receipt)

    def query(self, sql, parameters=()):
        if not self._active:
            _fail('windows_sqlite_snapshot_closed')
        if type(sql) is not str or len(sql.encode('utf-8')) > 1024 * 1024 or type(parameters) not in (tuple, list):
            _fail('windows_sqlite_query_invalid')
        steps = 0
        def progress():
            nonlocal steps
            steps += 1000
            return int(steps > MAX_STEPS)
        self._connection.set_progress_handler(progress, 1000)
        cursor = None
        try:
            cursor = self._connection.execute(sql, parameters)
            result = []
            size = 0
            for row in cursor:
                if len(result) >= MAX_ROWS:
                    _fail('windows_sqlite_query_limit')
                row = tuple(row)
                for value in row:
                    size += len(value) if type(value) is bytes else len(str(value).encode('utf-8'))
                if size > MAX_RESULT_BYTES:
                    _fail('windows_sqlite_query_limit')
                result.append(row)
            return result
        except AppError:
            raise
        except (sqlite3.Error, ValueError, TypeError, UnicodeError, OverflowError):
            _fail('windows_sqlite_query_rejected')
        finally:
            if cursor is not None:
                cursor.close()
            self._connection.set_progress_handler(None, 0)


@contextmanager
def _snapshot(root, name, api, connect):
    name = ws._leaf(name)
    wd._components(root + '\\' + name)
    # Validate all possible suffix lengths before any filesystem dispatch.
    for suffix in ('-journal', '-wal', '-shm'):
        ws._leaf(name + suffix)
        wd._components(root + '\\' + name + suffix)
    with wd._pin(root, api) as pin, ExitStack() as handles:
        canonical = pin._identities[-1]['final_path'].rstrip('\\') + '\\' + name
        snapshots = {}
        for suffix in ('', '-journal', '-wal', '-shm'):
            handle = api.open_read_guard(canonical + suffix, optional=bool(suffix))
            if handle is None:
                snapshots[suffix] = None
                continue
            handles.enter_context(ws._owned_handle(api, handle))
            identity = ws._bound_file(api, handle, pin)
            data = api.read(handle)
            if len(data) != identity['bytes']:
                _fail('windows_sqlite_bytes_changed')
            snapshots[suffix] = (handle, identity, _sha(data))
            if suffix in ('-wal', '-shm'):
                _fail('windows_sqlite_wal_sidecar_unsupported')
            if suffix == '-journal' and data and (len(data) < 28 or any(data[:28])):
                _fail('windows_sqlite_recovery_required')
            if not suffix:
                _header(data)
        pin.revalidate()
        # Percent-encode the complete native volume-GUID filename as a URI path
        # (not a URI authority). Actual Windows SQLite VFS admission is a gate.
        uri = 'file:' + quote(canonical, safe='') + '?mode=ro&immutable=1'
        connection = None
        snapshot = None
        primary = None
        try:
            connection = connect(uri, uri=True, timeout=5)
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('PRAGMA query_only=ON')
            if connection.execute('PRAGMA query_only').fetchone() != (1,):
                _fail('windows_sqlite_read_only_required')
            connection.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
            connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 1024 * 1024)
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_RESULT_BYTES)
            connection.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100)
            connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 1000)
            connection.enable_load_extension(False)
            connection.set_authorizer(_authorizer)
            snapshot = _Snapshot(connection, {'schema_version': SCHEMA, 'status': 'IMPLEMENTED',
                'database_sha256': snapshots[''][2], 'database_identity': snapshots[''][1],
                'sidecars': {key: None if value is None else {'identity': value[1], 'sha256': value[2]}
                    for key, value in snapshots.items() if key},
                'sqlite_version': sqlite3.sqlite_version, 'read_only': True,
                'recovery_performed': False, 'workbench_profile_enabled': False,
                'platform_qualified': False, 'production_approved': False,
                'scope': 'Pinned rollback-mode database bytes only; not complete Workbench integration or host power-loss qualification.'})
            yield snapshot
        except BaseException as error:
            primary = error
            raise
        finally:
            if snapshot is not None:
                snapshot._active = False
            cleanup_failures = []
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    cleanup_failures.append('windows_sqlite_close_failed')
            try:
                for suffix, before in snapshots.items():
                    if before is None:
                        unexpected = api.open_read_guard(canonical + suffix, optional=True)
                        if unexpected is not None:
                            with ws._owned_handle(api, unexpected):
                                _fail('windows_sqlite_sidecar_appeared')
                    else:
                        handle, identity, digest = before
                        if ws._bound_file(api, handle, pin) != identity or _sha(api.read(handle)) != digest:
                            _fail('windows_sqlite_bytes_changed')
                pin.revalidate()
            except Exception as error:
                cleanup_failures.append(error.code if isinstance(error, AppError) else 'windows_sqlite_revalidation_failed')
            if cleanup_failures:
                if primary is not None:
                    primary.snapshot_cleanup_failures = cleanup_failures
                    if hasattr(primary, 'add_note'):
                        primary.add_note('Native snapshot close or revalidation failed; preserve the primary failure and all files.')
                else:
                    _fail(cleanup_failures[0])


@contextmanager
def read_snapshot(root, name='observations.sqlite3'):
    """Inactive component; never selected by current Workbench host profiles."""
    with _snapshot(root, name, _Win32Snapshot(), sqlite3.connect) as snapshot:
        yield snapshot
