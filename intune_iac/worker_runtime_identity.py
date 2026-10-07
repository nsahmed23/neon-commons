"""Exact local controller source/runtime inventory, not remote CI attestation."""
from __future__ import annotations

import hashlib
import ctypes
import importlib.util
import os
from pathlib import Path
import stat
import sys
import sysconfig
import threading

from .io import AppError

_CACHE = {}
_SECCOMP = None
_LOCK = threading.RLock()


def _hash(path):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_size > 256 * 1024 * 1024:
        raise AppError('service_runtime_file_invalid', 'A declared controller runtime file is unsafe or exceeds its bound.')
    metadata = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    previous = _CACHE.get(str(path))
    if previous is not None and previous[0] == metadata: return previous[1]
    with path.open('rb') as stream: value = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    if metadata != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise AppError('service_runtime_file_changed', 'A controller runtime file changed during hashing.')
    _CACHE[str(path)] = (metadata, value)
    return value


def inventory():
    """Bind all package Python, stdlib Python/extensions and loaded native files.

    The entire standard library is bound; any already loaded external Python
    module is also bound. New lazy imports outside that inventory invalidate
    subsequent checks. Only exact deleted private
    validator paths registered by the pinned authority verifier are excluded because their copied contents are validated
    against the authority's explicit libsodium pin. Future imports can change
    the loaded-native inventory and consequently invalidate reviewed execution.
    Cache reuse requires unchanged inode/device/size/mtime/ctime; directory file
    sets are enumerated again, so additions/removals invalidate the binding.
    """
    global _SECCOMP
    with _LOCK:
        # Verification/host supervision uses this existing library later. Load
        # it before preparing an inventory, without installing a filter here.
        if _SECCOMP is None: _SECCOMP = ctypes.CDLL('libseccomp.so.2', use_errno=True)
        paths = {}
        package = Path(__file__).parent
        for path in package.rglob('*.py'):
            if path.is_symlink(): raise AppError('service_runtime_symlink', 'Controller source links are not admitted.')
            paths['package/' + str(path.relative_to(package))] = path
        stdlib = Path(sysconfig.get_path('stdlib')).resolve()
        for current, directories, names in os.walk(stdlib):
            directories[:] = [name for name in directories if name not in ('site-packages', '__pycache__')]
            for name in names:
                if name.endswith(('.py', '.so')):
                    path = Path(current) / name
                    if path.is_symlink(): raise AppError('service_runtime_symlink', 'Controller standard-library links are not admitted.')
                    paths['stdlib/' + str(path.relative_to(stdlib))] = path
        for module in list(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if type(name) is not str: continue
            path = Path(name)
            if path.suffix == '.pyc':
                try: path = Path(importlib.util.source_from_cache(str(path)))
                except ValueError: pass
            if path.is_file():
                path = path.resolve(strict=True)
                if not path.is_relative_to(stdlib) and not path.is_relative_to(package):
                    paths['loaded-python/' + str(path)] = path
        executable = Path(sys.executable).resolve(strict=True)
        paths['interpreter/' + str(executable)] = executable
        # Parse the fixed Linux procfs map format, without invoking a shell or
        # executing loaders/ldd against untrusted binaries.
        for line in Path('/proc/self/maps').read_text().splitlines():
            fields = line.split(None, 5)
            if len(fields) != 6: continue
            name = fields[5]
            if not name.startswith('/'): continue
            if name.endswith(' (deleted)'):
                from . import approval_authority
                known = {str(library._name) for library in approval_authority._VALIDATORS.values()}
                if name[:-10] not in known:
                    raise AppError('service_runtime_deleted_mapping', 'An unbound deleted native mapping is present in the controller.')
                continue
            path = Path(name).resolve(strict=True)
            if path != executable and not path.is_relative_to(stdlib):
                paths['loaded-native/' + str(path)] = path
        if not 1 <= len(paths) <= 4096:
            raise AppError('service_runtime_inventory_limit', 'Controller runtime inventory is outside the declared profile.')
        result = {name: _hash(path) for name, path in sorted(paths.items())}
        active = {str(path) for path in paths.values()}
        for key in list(_CACHE):
            if key not in active: _CACHE.pop(key)
        return result
