"""Inactive native, private, no-follow readers for inert observation evidence.

The existing capture/reference validators decide meaning. Held Win32 handles
and bounded revalidation establish byte consistency, never Graph authenticity.
Ordinary Windows Workbench support remains disabled pending native gates.
"""
from contextlib import contextmanager, ExitStack
import hashlib
import os
from pathlib import PureWindowsPath

from .io import AppError
from . import windows_directory as wd, windows_storage as ws, windows_sqlite as ro
from .capture_adapter import _load_capture, MAX_BYTES

MAX_NAMES = 10004


def _fail(code):
    raise AppError(code, 'Native evidence bytes or their private namespace could not be established.')


class _NativeAPI(ro._Win32Snapshot):
    def names(self, path):
        with os.scandir(path) as entries:
            result = []
            for entry in entries:
                if len(result) >= MAX_NAMES: _fail('windows_capture_limit')
                result.append(entry.name)
            return result


class _Directory:
    def __init__(self, root, api, stack, directories):
        wd._components(str(root))
        self.api, self.stack, self.directories = api, stack, directories
        self.pin = stack.enter_context(wd._pin(str(root), api))
        self.root = PureWindowsPath(root)
        self.native = PureWindowsPath(self.pin._identities[-1]['final_path'])
        self.files, self.initial_names = {}, None
        directories.append(self)

    def names(self):
        names = self.api.names(str(self.native))
        if len(names) > MAX_NAMES or len(set(names)) != len(names): _fail('windows_capture_limit')
        for name in names: ws._leaf(name)
        if self.initial_names is None: self.initial_names = set(names)
        elif set(names) != self.initial_names: _fail('windows_capture_namespace_changed')
        return names

    def read(self, name, limit=MAX_BYTES):
        name = ws._leaf(name)
        if type(limit) is not int or not 0 <= limit <= MAX_BYTES: _fail('windows_capture_limit')
        if name in self.files:
            before = self.files[name]
            if len(before['data']) > limit: _fail('windows_capture_limit')
            return before['data']
        handle = self.stack.enter_context(ws._owned_handle(self.api,
            self.api.open_read_guard(str(self.native / name))))
        identity = ws._bound_file(self.api, handle, self.pin)
        if identity['bytes'] > limit: _fail('windows_capture_limit')
        data = self.api.read(handle)
        if type(data) is not bytes or len(data) != identity['bytes'] or len(data) > limit:
            _fail('windows_capture_bytes_changed')
        self.files[name] = {'handle':handle, 'identity':identity, 'data':data,
            'sha256':hashlib.sha256(data).hexdigest()}
        return data

    @contextmanager
    def raw(self):
        # This pin and every file handle stay in the outer stack through ALL
        # semantic validation, including checks after the raw iteration ends.
        yield _Directory(self.root / 'raw', self.api, self.stack, self.directories)

    def revalidate(self):
        if self.initial_names is not None: self.names()
        for before in self.files.values():
            after = ws._bound_file(self.api, before['handle'], self.pin)
            if after != before['identity'] or hashlib.sha256(self.api.read(before['handle'])).hexdigest() != before['sha256']:
                _fail('windows_capture_bytes_changed')
        self.pin.revalidate()


@contextmanager
def _directory(root, api):
    with ExitStack() as stack:
        directories = []
        access = _Directory(root, api, stack, directories)
        yield access
        for directory in directories: directory.revalidate()


def _load(path, tenant_id, api):
    return _load_capture(path, tenant_id=tenant_id,
        directory=lambda root: _directory(root, api))


def load_windows_capture(path, *, tenant_id):
    return _load(path, tenant_id, _NativeAPI())


def _reference_bytes(path, api, maximum):
    wd._components(str(path))
    path = PureWindowsPath(path)
    with _directory(path.parent, api) as access:
        return access.read(path.name, maximum)


def _reference_import(store, path, expected_sha256, source_revision, source_url,
                      license_id, assertion_class, api):
    from .workbench_provenance import _metadata, _reference_import_bytes, MAX_REFERENCE_BYTES
    _metadata(expected_sha256, source_revision, source_url, license_id, assertion_class)
    raw = _reference_bytes(path, api, MAX_REFERENCE_BYTES)
    return _reference_import_bytes(store, raw, expected_sha256, source_revision,
        source_url, license_id, assertion_class)


def reference_import_windows(store, path, expected_sha256, source_revision,
                             source_url, license_id, assertion_class='community_reference'):
    return _reference_import(store, path, expected_sha256, source_revision,
        source_url, license_id, assertion_class, _NativeAPI())
