"""Portable, non-mutating host prerequisites for existing bounded adapters.

This report inventories required implementation primitives. It is not a native
qualification, filesystem probe, security approval or substitute for adapter
runtime checks. Missing primitives fail before importing POSIX-only adapters.
"""
from __future__ import annotations

import importlib
import os
import sys

from .io import AppError

SCHEMA = 'intune-host-capabilities/1'

_PROFILE_REQUIREMENTS = {
    'workbench_store': ('posix', 'effective_uid', 'nofollow_open', 'directory_open', 'descriptor_relative_open', 'fsync', 'fcntl_lock'),
    'graph_observer': ('posix', 'linux', 'effective_uid', 'nofollow_open', 'directory_open', 'descriptor_relative_open',
                       'fsync', 'fcntl_lock', 'procfs', 'waitid_wnowait'),
    'protected_worker': ('posix', 'linux', 'x86_64', 'effective_uid', 'nofollow_open', 'directory_open',
                        'descriptor_relative_open', 'fsync', 'fcntl_lock', 'procfs', 'waitid_wnowait'),
    'artifact_vault': ('posix', 'linux', 'effective_uid', 'nofollow_open', 'directory_open',
                       'descriptor_relative_open', 'fsync', 'fcntl_lock'),
    'visual_workspace': ('posix', 'effective_uid', 'nofollow_open', 'directory_open',
                         'descriptor_relative_open', 'fsync', 'fcntl_lock', 'termios'),
}

_MISSING_IMPLEMENTATION = {
    'posix': 'A reviewed native Windows private-filesystem and process adapter is not implemented.',
    'linux': 'This adapter is implemented for Linux; an equivalent native host adapter is not implemented.',
    'x86_64': 'The protected native tool/provider profile is pinned for Linux x86_64.',
    'effective_uid': 'Windows token/SID ownership and DACL checks must replace POSIX effective-UID/mode checks.',
    'nofollow_open': 'Handle-relative Windows opens must reject reparse traversal and verify final file identity.',
    'directory_open': 'A Windows directory-handle implementation with equivalent validation is required.',
    'descriptor_relative_open': 'Descriptor-relative no-follow traversal needs a reviewed native equivalent.',
    'fsync': 'The host requires verified file/namespace durability and failure propagation.',
    'fcntl_lock': 'LockFileEx or an equivalent reviewed native locking adapter is not implemented.',
    'procfs': 'Windows process/job ownership and descendant census require a separate native implementation.',
    'waitid_wnowait': 'Native process-handle retention, descendant termination and independent cleanup observation are required.',
    'termios': 'Native console/mintty input, mode restoration and visual interaction are not implemented or qualified here.',
}


def _module_has(name, attributes):
    try:
        module = importlib.import_module(name)
        return all(hasattr(module, key) for key in attributes)
    except (ImportError, OSError, ValueError):
        return False


def _machine():
    # platform.machine() may fall back to a shell 'ver' command on Windows.
    # Discovery must not spawn anything. Non-POSIX architecture stays unknown
    # until a separately reviewed native adapter provides it.
    native = getattr(os, 'uname', None)
    if callable(native):
        try: return native().machine
        except OSError: pass
    return 'unknown'


def _facts():
    """Symbol/discovery checks only; never create files, launch tools or read secrets."""
    posix = os.name == 'posix'
    linux = sys.platform == 'linux'
    return {'posix': posix, 'linux': linux,
        'x86_64': _machine().lower() in ('x86_64', 'amd64'),
        'effective_uid': posix and callable(getattr(os, 'geteuid', None)),
        'nofollow_open': posix and bool(getattr(os, 'O_NOFOLLOW', 0)),
        'directory_open': posix and bool(getattr(os, 'O_DIRECTORY', 0)),
        'descriptor_relative_open': posix and os.open in getattr(os, 'supports_dir_fd', ()),
        'fsync': callable(getattr(os, 'fsync', None)),
        'fcntl_lock': posix and _module_has('fcntl', ('flock', 'LOCK_EX', 'LOCK_NB')),
        'procfs': linux and os.path.isdir('/proc/self/fd') and os.path.isfile('/proc/self/stat'),
        'waitid_wnowait': linux and callable(getattr(os, 'waitid', None)) and all(hasattr(os, key) for key in ('WNOWAIT', 'WEXITED', 'WNOHANG', 'P_PID')),
        'termios': posix and _module_has('termios', ('tcgetattr', 'tcsetattr', 'TCSANOW'))}


def _profiles(facts):
    values = {}
    for name, required in _PROFILE_REQUIREMENTS.items():
        missing = [key for key in required if facts.get(key) is not True]
        values[name] = {'status': 'IMPLEMENTED' if not missing else 'UNSUPPORTED',
            'meaning': 'Host prerequisites discovered; actual adapter/runtime qualification remains required.' if not missing else
                       'Required native implementation primitives are unavailable; this route must not dispatch.',
            'required_primitives': list(required), 'missing_primitives': missing,
            'required_implementation': [_MISSING_IMPLEMENTATION[key] for key in missing],
            'platform_qualified': False, 'production_approved': False}
    return values


def report():
    facts = _facts()
    return {'schema_version': SCHEMA,
        'host': {'os_name': os.name, 'sys_platform': sys.platform, 'machine': _machine(),
                 'python_version': '.'.join(map(str, sys.version_info[:3]))},
        'probe_scope': 'Read-only discovery of platform, standard-library symbols and procfs paths; no native lifecycle or filesystem qualification.',
        'primitives': facts, 'profiles': _profiles(facts),
        'portable_routes': ['CLI help and parser discovery', 'doctor capability report'],
        'limitations': ['A discovered symbol does not prove that a particular filesystem, ACL, runner or terminal satisfies the contract.',
                       'Existing adapters still verify exact files, identities, locks, tool pins, network policy and cleanup at dispatch.',
                       'libseccomp, native provider/tool pins, real CI/backend/service/device behavior and organizational approval require their own evidence.',
                       'Native Windows private workbench storage, protected execution and observation are implementation gaps, not merely missing test receipts.',
                       'No-tty text presentation cannot make an unsupported private store or worker portable.'],
        'native_windows_qualified': False, 'platform_qualified': False, 'production_approved': False}


def require_profile(profile):
    """Reject absent implementations before imports/opening stores or credentials."""
    if profile not in _PROFILE_REQUIREMENTS:
        raise AppError('host_profile_unknown', 'The requested host capability profile is not declared.')
    value = report()
    selected = value['profiles'][profile]
    if selected['status'] == 'UNSUPPORTED':
        error = AppError('host_profile_unsupported',
            'The ' + profile + ' route is unsupported on this host; missing primitives: ' +
            ', '.join(selected['missing_primitives']) + '. A reviewed native adapter is required; no fallback has been enabled.')
        error.details = {'schema_version': SCHEMA, 'profile': profile, 'status': 'UNSUPPORTED',
                         'host': value['host'], **selected}
        raise error
    return selected
