#!/usr/bin/env python3
"""Reassemble a separately pinned R3 evidence ZIP from public byte chunks.

Python 3.10+ on POSIX is required. No credentials or third-party packages.
Requires independently supplied final byte count and SHA-256; no fixed R2 pins.
Does not extract any ZIP member, create links, or execute archive content.
Interrupted downloads retain OUTPUT.partial and may be resumed. Existing final
ZIP output is never replaced. This is a supplement, not a full repository.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

SCHEMA = 'intune-r3-evidence-split-release/1'
MAX_ARCHIVE_BYTES = 64 * 1024**3
CHUNK = 1024 * 1024
MAX_JSON = 64 * CHUNK
HEX = re.compile(r'[0-9a-f]{64}\Z')


class RestoreError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise RestoreError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def loads(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, 'Duplicate JSON key: ' + key)
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=unique)


def safe_parts(path):
    require(isinstance(path, str) and path and '\\' not in path and '\x00' not in path,
            'Invalid portable archive path')
    require(not path.startswith('/') and not re.match(r'^[A-Za-z]:', path), 'Absolute archive path')
    pieces = path.split('/')
    require(all(p not in ('', '.', '..') for p in pieces), 'Traversal/empty path component')
    # Windows device aliases and alternate streams must not change interpretation.
    for piece in pieces:
        require(':' not in piece and not piece.endswith((' ', '.')), 'Nonportable archive path')
        require(not re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', piece),
                'Reserved archive filename')
    return pieces


def platform_check():
    require(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY'),
            'Safe extraction/output requires POSIX O_NOFOLLOW and directory descriptors')


def open_dir(path):
    """Anchor every existing ancestor without resolving or following symlinks."""
    platform_check()
    absolute = os.path.abspath(os.fspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.split('/')[1:]:
            if part:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextlib.contextmanager
def input_stream(location, start=0):
    parsed = urllib.parse.urlsplit(location)
    if parsed.scheme:
        require(parsed.scheme == 'https' and parsed.netloc and not parsed.username and not parsed.password
                and not parsed.fragment, 'Only unauthenticated HTTPS URLs are accepted')
        headers = {'User-Agent': 'Intune-R3-Evidence-Restore/1'}
        if start:
            headers['Range'] = 'bytes=%d-' % start
        response = urllib.request.urlopen(urllib.request.Request(location, headers=headers), timeout=60)
        try:
            require(urllib.parse.urlsplit(response.geturl()).scheme == 'https', 'HTTPS downgrade rejected')
            if start:
                if response.status == 206:
                    require(response.headers.get('Content-Range', '').startswith('bytes %d-' % start), 'Incorrect HTTP range response')
                else:
                    require(response.status == 200, 'Unexpected HTTP response for resume')
                    remaining = start
                    while remaining:
                        chunk = response.read(min(CHUNK, remaining))
                        require(bool(chunk), 'HTTP source shorter than resume offset')
                        remaining -= len(chunk)
            yield response
        finally:
            response.close()
    else:
        path = Path(location).absolute()
        parent = open_dir(path.parent)
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            with os.fdopen(fd, 'rb') as stream:
                require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Input must be a regular file')
                stream.seek(start)
                yield stream
        finally:
            os.close(parent)


def read_limited(location, limit):
    with input_stream(location) as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, 'Input exceeds bounded document size')
    return data


def validate_distribution(manifest, expected_bytes, expected_sha256):
    require(manifest.get('schema_version') == SCHEMA, 'Unsupported distribution manifest schema')
    archive = manifest['archive']
    require(type(expected_bytes) is int and 0 < expected_bytes <= MAX_ARCHIVE_BYTES, 'Invalid caller size pin')
    require(isinstance(expected_sha256, str) and HEX.fullmatch(expected_sha256), 'Invalid caller SHA-256 pin')
    require((archive['bytes'], archive['sha256']) == (expected_bytes, expected_sha256),
            'Distribution does not match caller-supplied complete evidence ZIP pins')
    for obj in [archive] + manifest['parts']:
        require(type(obj['bytes']) is int and 0 < obj['bytes'] <= MAX_ARCHIVE_BYTES, 'Invalid part/archive size')
        require(isinstance(obj['sha256'], str) and HEX.fullmatch(obj['sha256']), 'Invalid SHA-256')
        require(len(safe_parts(obj['name'])) == 1, 'Asset name must be a basename')
    require(1 <= len(manifest['parts']) <= 1000, 'Invalid number of parts')
    require(len({p['name'] for p in manifest['parts']}) == len(manifest['parts']), 'Duplicate part names')
    require(sum(p['bytes'] for p in manifest['parts']) == archive['bytes'], 'Part sizes do not equal archive size')


def resolve_part(location, manifest_location):
    if urllib.parse.urlsplit(manifest_location).scheme:
        resolved = urllib.parse.urljoin(manifest_location, location)
        require(urllib.parse.urlsplit(resolved).scheme == 'https', 'Remote manifest requires HTTPS parts')
        return resolved
    if urllib.parse.urlsplit(location).scheme or os.path.isabs(location):
        return location
    return str(Path(manifest_location).absolute().parent / location)


def reassemble(manifest, manifest_location, output):
    """Keep failure bytes at OUTPUT.partial; atomically publish without replacement."""
    output = Path(output).absolute()
    parent = open_dir(output.parent)
    partial = output.name + '.partial'
    try:
        try:
            os.stat(output.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise RestoreError('Output already exists: ' + str(output))
        try:
            fd = os.open(partial, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        except FileExistsError:
            fd = os.open(partial, os.O_RDWR | os.O_NOFOLLOW, dir_fd=parent)
        whole = hashlib.sha256()
        total = 0
        with os.fdopen(fd, 'r+b') as destination:
            fcntl.flock(destination, fcntl.LOCK_EX | fcntl.LOCK_NB)
            metadata = os.fstat(destination.fileno())
            require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1, 'Partial must be a single-link regular file')
            require(metadata.st_size <= manifest['archive']['bytes'], 'Partial exceeds complete ZIP size')
            initial_size = metadata.st_size
            for index, part in enumerate(manifest['parts'], 1):
                print('Downloading/verifying part %d/%d: %s' % (index, len(manifest['parts']), part['name']), file=sys.stderr, flush=True)
                digest = hashlib.sha256()
                count = 0
                existing = min(part['bytes'], max(0, initial_size - total))
                while count < existing:
                    data = destination.read(min(CHUNK, existing - count))
                    require(bool(data), 'Partial changed while resuming')
                    count += len(data)
                    digest.update(data)
                    whole.update(data)
                    total += len(data)
                if count < part['bytes']:
                    # Resume bytes remain provisional until the entire part matches its pin.
                    destination.seek(total)
                    with input_stream(resolve_part(part['url'], manifest_location), count) as source:
                        while True:
                            data = source.read(min(CHUNK, part['bytes'] - count + 1))
                            if not data:
                                break
                            count += len(data)
                            require(count <= part['bytes'], 'Part exceeds declared size: ' + part['name'])
                            destination.write(data)
                            digest.update(data)
                            whole.update(data)
                            total += len(data)
                    destination.flush()
                    os.fsync(destination.fileno())
                require((count, digest.hexdigest()) == (part['bytes'], part['sha256']),
                        'Part integrity failed: ' + part['name'])
            require((total, whole.hexdigest()) == (manifest['archive']['bytes'], manifest['archive']['sha256']),
                    'Complete archive integrity failed')
            destination.flush()
            os.fsync(destination.fileno())
            os.link(partial, output.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            os.unlink(partial, dir_fd=parent)
            os.fsync(parent)
    finally:
        os.close(parent)
    return {'archive': str(output), 'bytes': total, 'sha256': whole.hexdigest()}



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, help='Distribution JSON: HTTPS URL or local path')
    parser.add_argument('--output', required=True, help='New ZIP path; completed output is never replaced')
    parser.add_argument('--bytes', required=True, type=int, help='Independent published complete ZIP byte count')
    parser.add_argument('--sha256', required=True, help='Independent published complete ZIP SHA-256')
    args = parser.parse_args(argv)
    try:
        manifest = loads(read_limited(args.manifest, 1024 * 1024))
        validate_distribution(manifest, args.bytes, args.sha256)
        result = reassemble(manifest, args.manifest, args.output)
        result.update(status='PASS', extraction_performed=False, complete_repository=False,
                      scope='Exact R3 evidence supplement ZIP; complete R2 base is separately required')
        print(json.dumps(result, indent=2))
        return 0
    except (RestoreError, OSError, ValueError, KeyError, TypeError) as error:
        print('RESTORE FAILED: %s. Any partial ZIP is preserved; investigate before retrying.' % error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
