"""Bounded encrypted archival, distinct from plaintext execution and authority.

Uses the already admitted, explicitly pinned libsodium implementation of
XChaCha20-Poly1305. This module never generates/provisions keys. A host supplies
32 bytes through an inherited descriptor and retains recovery copies separately.
An archive authenticates bytes and context, not tenant truth or permission to act.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import re
import select
import stat
import struct
import sys
import tempfile
import time

from .io import AppError, canonical, parse_json

MAGIC = b'INTUNE-ARCHIVE\x00\x01'
MAX_BYTES = 64 * 1024 * 1024
MAX_HEADER = 4096
KINDS = ('state', 'binary_plan', 'plan_json', 'raw_capture', 'receipt', 'observation_backup')
HASH = re.compile(r'^[a-f0-9]{64}$')
FIELDS = {'schema', 'algorithm', 'kind', 'context_sha256', 'plaintext_sha256',
          'plaintext_bytes', 'created_at', 'retain_until', 'key_id'}


def _fail(code):
    raise AppError(code, 'Encrypted artifact could not be admitted. Original inputs are unchanged.')


def _private_path(value, *, directory=False):
    path = Path(value).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        _fail('artifact_unsafe_path')
    if path.exists():
        info = path.stat()
        expected = stat.S_ISDIR if directory else stat.S_ISREG
        if not expected(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            _fail('artifact_private_path_required')
    elif directory:
        _fail('artifact_directory_missing')
    return path


def _read(value, maximum):
    path = _private_path(value)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > maximum:
            _fail('artifact_input_limit_or_permissions')
        contents = source.read(maximum + 1)
    if len(contents) > maximum:
        _fail('artifact_input_limit')
    return contents


def _write_new(value, data):
    path = _private_path(value)
    _private_path(path.parent, directory=True)
    if path.exists():
        _fail('artifact_output_exists')
    fd, temporary = tempfile.mkstemp(prefix='.artifact-stage-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        # link is exclusive; never replace a preexisting destination or symlink.
        os.link(temporary, path, follow_symlinks=False)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        os.unlink(temporary)


def _library(path, sha256):
    if sys.platform != 'linux' or not HASH.fullmatch(sha256 or ''):
        _fail('artifact_native_platform_or_pin')
    from .approval_authority import VerifierPin, _validator
    lib = _validator(VerifierPin(Path(sys.executable), '', Path(path), sha256))
    try:
        encrypt = lib.crypto_aead_xchacha20poly1305_ietf_encrypt
        decrypt = lib.crypto_aead_xchacha20poly1305_ietf_decrypt
        encrypt.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulonglong), ctypes.c_char_p,
                            ctypes.c_ulonglong, ctypes.c_char_p, ctypes.c_ulonglong,
                            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        decrypt.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulonglong), ctypes.c_void_p,
                            ctypes.c_char_p, ctypes.c_ulonglong, ctypes.c_char_p,
                            ctypes.c_ulonglong, ctypes.c_char_p, ctypes.c_char_p]
        encrypt.restype = decrypt.restype = ctypes.c_int
        return encrypt, decrypt
    except AttributeError:
        _fail('artifact_algorithm_unavailable')


def _key(key):
    if type(key) is not bytes or len(key) != 32:
        _fail('artifact_key_length')


def read_key_fd(fd):
    """Bounded descriptor read; keys never enter argument strings or receipts."""
    if type(fd) is not int or fd < 3:
        _fail('artifact_inherited_key_descriptor_required')
    info = os.fstat(fd)
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISFIFO(info.st_mode)):
        _fail('artifact_key_descriptor_type')
    if stat.S_ISREG(info.st_mode) and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
        _fail('artifact_private_key_required')
    end = time.monotonic() + 2
    value = bytearray()
    while len(value) <= 32:
        remaining = end - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            _fail('artifact_key_descriptor_timeout')
        block = os.read(fd, 33 - len(value))
        if not block:
            break
        value.extend(block)
    result = bytes(value)
    value[:] = bytes(len(value))
    _key(result)
    return result


def _header(raw):
    if not raw.startswith(MAGIC) or len(raw) < len(MAGIC) + 4:
        _fail('artifact_format')
    length = struct.unpack('>I', raw[len(MAGIC):len(MAGIC)+4])[0]
    start = len(MAGIC) + 4
    if not 1 <= length <= MAX_HEADER or len(raw) < start + length + 24 + 16:
        _fail('artifact_format')
    encoded = raw[start:start+length]
    try:
        header = parse_json(encoded)
        if type(header) is not dict or set(header) != FIELDS or canonical(header) != encoded:
            _fail('artifact_header')
        if header['schema'] != 'intune-encrypted-artifact/1' or header['algorithm'] != 'XChaCha20-Poly1305-IETF':
            _fail('artifact_algorithm')
        if header['kind'] not in KINDS or any(type(header[x]) is not str or not HASH.fullmatch(header[x]) for x in ('context_sha256', 'plaintext_sha256')):
            _fail('artifact_header')
        if any(type(header[x]) is not int for x in ('plaintext_bytes', 'created_at', 'retain_until')) or not 0 <= header['plaintext_bytes'] <= MAX_BYTES or header['created_at'] < 0 or header['retain_until'] < header['created_at']:
            _fail('artifact_header')
        if not isinstance(header['key_id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', header['key_id']):
            _fail('artifact_header')
    except (ValueError, TypeError, KeyError, UnicodeError):
        _fail('artifact_header')
    end = start + length
    if len(raw) != end + 24 + header['plaintext_bytes'] + 16:
        _fail('artifact_length')
    return header, raw[:end], raw[end:end+24], raw[end+24:]


def seal(source, output, *, key, kind, context_sha256, key_id, retain_until,
         library, library_sha256, now=None):
    _key(key)
    created = int(time.time()) if now is None else now
    data = _read(source, MAX_BYTES)
    header = {'schema': 'intune-encrypted-artifact/1', 'algorithm': 'XChaCha20-Poly1305-IETF',
              'kind': kind, 'context_sha256': context_sha256, 'plaintext_sha256': hashlib.sha256(data).hexdigest(),
              'plaintext_bytes': len(data), 'created_at': created, 'retain_until': retain_until, 'key_id': key_id}
    encoded = canonical(header)
    prefix = MAGIC + struct.pack('>I', len(encoded)) + encoded
    nonce = os.urandom(24)
    # Validate the exact schema before handing any content to native cryptography.
    _header(prefix + nonce + bytes(len(data) + 16))
    encrypt, _ = _library(library, library_sha256)
    buffer = ctypes.create_string_buffer(len(data) + 16)
    length = ctypes.c_ulonglong()
    if encrypt(buffer, ctypes.byref(length), data, len(data), prefix, len(prefix), None, nonce, key) != 0 or length.value != len(data) + 16:
        _fail('artifact_encrypt_failed')
    archive = prefix + nonce + buffer.raw
    _write_new(output, archive)
    return {'status': 'sealed', 'artifact_sha256': hashlib.sha256(archive).hexdigest(), 'artifact_bytes': len(archive),
            'metadata': header, 'plaintext_source_retained': True, 'cloud_authority': False}


def restore(source, output, *, key, kind, context_sha256, library, library_sha256):
    _key(key)
    raw = _read(source, MAX_BYTES + MAX_HEADER + 128)
    header, associated, nonce, ciphertext = _header(raw)
    if header['kind'] != kind or header['context_sha256'] != context_sha256:
        _fail('artifact_context_mismatch')
    _, decrypt = _library(library, library_sha256)
    buffer = ctypes.create_string_buffer(max(1, len(ciphertext) - 16))
    length = ctypes.c_ulonglong()
    if decrypt(buffer, ctypes.byref(length), None, ciphertext, len(ciphertext), associated, len(associated), nonce, key) != 0:
        _fail('artifact_authentication_failed')
    data = buffer.raw[:length.value]
    if len(data) != header['plaintext_bytes'] or hashlib.sha256(data).hexdigest() != header['plaintext_sha256']:
        _fail('artifact_plaintext_mismatch')
    _write_new(output, data)
    return {'status': 'restored', 'artifact_sha256': hashlib.sha256(raw).hexdigest(), 'metadata': header,
            'metadata_authenticated': True, 'plaintext_output_private': True, 'cloud_authority': False}


def inspect(source):
    raw = _read(source, MAX_BYTES + MAX_HEADER + 128)
    header, _, _, _ = _header(raw)
    return {'status': 'unverified_metadata', 'metadata': header, 'artifact_sha256': hashlib.sha256(raw).hexdigest(),
            'metadata_authenticated': False, 'cloud_authority': False}


def add_parser(commands):
    group = commands.add_parser('artifact', help='Private encrypted archival; no key provisioning or execution authority')
    sub = group.add_subparsers(dest='artifact_command', required=True)
    for name in ('seal', 'restore', 'inspect'):
        item = sub.add_parser(name)
        item.add_argument('--input', required=True)
        if name == 'inspect':
            continue
        item.add_argument('--output', required=True)
        item.add_argument('--key-fd', type=int, required=True)
        item.add_argument('--kind', choices=KINDS, required=True)
        item.add_argument('--context-sha256', required=True)
        item.add_argument('--library', required=True)
        item.add_argument('--library-sha256', required=True)
        if name == 'seal':
            item.add_argument('--key-id', required=True)
            item.add_argument('--retain-until', type=int, required=True)


def command(args):
    if args.artifact_command == 'inspect':
        return inspect(args.input)
    parameters = {'key': read_key_fd(args.key_fd), 'kind': args.kind, 'context_sha256': args.context_sha256,
                  'library': args.library, 'library_sha256': args.library_sha256}
    if args.artifact_command == 'seal':
        parameters.update(key_id=args.key_id, retain_until=args.retain_until)
        return seal(args.input, args.output, **parameters)
    return restore(args.input, args.output, **parameters)
