#!/usr/bin/env python3
"""Reassemble the exact complete R2 snapshot; optionally extract with inert links.

Python 3.10+ on POSIX with dir_fd/O_NOFOLLOW is required for safe output.
All operations are local except downloading explicitly listed HTTPS assets.
No archive content is executed. Failed partials/extractions are preserved.
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

SCHEMA = 'intune-r2-split-release/1'
ARCHIVE_BYTES = 2289864715
ARCHIVE_SHA256 = '7117ab67ce6ae1912aa2c984774e6370216f3eb28be1510d0c6814cb4c295d0b'
MANIFEST_SHA256 = '71a06930122bbed74a17b0d49f149b210fb84b5d6a5d5217de9710d0f61c23ef'
ROOT = 'Intune_Atmos_Wally_Continuation_R2'
MANIFEST_NAME = 'CONTINUATION-SNAPSHOT-R2-MANIFEST.json'
CHUNK = 1024 * 1024
MAX_JSON = 64 * CHUNK
MAX_ENTRIES = 200000
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
        headers = {'User-Agent': 'Intune-R2-Restore/1'}
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


def validate_distribution(manifest, pinned=True):
    require(manifest.get('schema_version') == SCHEMA, 'Unsupported distribution manifest schema')
    archive = manifest['archive']
    snapshot = manifest['snapshot']
    for obj in [archive] + manifest['parts']:
        require(type(obj['bytes']) is int and 0 < obj['bytes'] <= ARCHIVE_BYTES, 'Invalid part/archive size')
        require(isinstance(obj['sha256'], str) and HEX.fullmatch(obj['sha256']), 'Invalid SHA-256')
        require(len(safe_parts(obj['name'])) == 1, 'Asset name must be a basename')
    require(1 <= len(manifest['parts']) <= 32, 'Invalid number of parts')
    require(len({p['name'] for p in manifest['parts']}) == len(manifest['parts']), 'Duplicate part names')
    require(sum(p['bytes'] for p in manifest['parts']) == archive['bytes'], 'Part sizes do not equal archive size')
    require(len(safe_parts(snapshot['root'])) == 1 and len(safe_parts(snapshot['manifest'])) == 1,
            'Invalid snapshot root/manifest')
    require(isinstance(snapshot['manifest_sha256'], str) and HEX.fullmatch(snapshot['manifest_sha256']),
            'Invalid snapshot manifest SHA-256')
    if pinned:
        require((archive['bytes'], archive['sha256']) == (ARCHIVE_BYTES, ARCHIVE_SHA256),
                'Distribution does not match the independently supplied R2 archive pins')
        require((snapshot['root'], snapshot['manifest'], snapshot['manifest_sha256']) ==
                (ROOT, MANIFEST_NAME, MANIFEST_SHA256), 'Unexpected R2 snapshot manifest pins')


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


def inspect_archive(archive, snapshot):
    """Read only metadata first; exact typed inventory is required before writes."""
    infos = archive.infolist()
    require(len(infos) <= MAX_ENTRIES, 'Archive entry limit exceeded')
    mapping = {}
    for info in infos:
        name = info.filename[:-1] if info.is_dir() else info.filename
        safe_parts(name)
        require(name not in mapping, 'Duplicate archive path: ' + name)
        require(not info.flag_bits & 1, 'Encrypted archive member rejected')
        mapping[name] = info
    prefix = snapshot['root'] + '/'
    manifest_name = prefix + snapshot['manifest']
    require(manifest_name in mapping and mapping[manifest_name].file_size <= MAX_JSON, 'Missing/oversize archive manifest')
    raw = archive.read(mapping[manifest_name])
    require(sha(raw) == snapshot['manifest_sha256'], 'Archive manifest integrity failed')
    document = loads(raw)
    require(document['schema'] == 'complete-continuation-snapshot/2', 'Unsupported snapshot inventory schema')
    entries = document['entries']
    require(isinstance(entries, list) and len(entries) < MAX_ENTRIES, 'Invalid inventory entries')
    inventory = {}
    for entry in entries:
        path = entry['path']
        safe_parts(path)
        require(path not in inventory, 'Duplicate manifest path: ' + path)
        require(entry['type'] in ('file', 'directory', 'symlink'), 'Unsupported manifest entry type')
        require(type(entry['bytes']) is int and 0 <= entry['bytes'] <= 16 * 1024**3, 'Invalid payload size')
        require(isinstance(entry['sha256'], str) and HEX.fullmatch(entry['sha256']), 'Invalid payload SHA-256')
        inventory[path] = entry
    expected = {prefix + path for path in inventory} | {manifest_name}
    require(set(mapping) == expected, 'Archive/manifest file sets differ')
    for path, entry in inventory.items():
        parent = path.rpartition('/')[0]
        while parent:
            require(parent in inventory and inventory[parent]['type'] == 'directory', 'Missing/non-directory parent: ' + parent)
            parent = parent.rpartition('/')[0]
        info = mapping[prefix + path]
        mode = info.external_attr >> 16
        actual = 'directory' if stat.S_ISDIR(mode) else 'symlink' if stat.S_ISLNK(mode) else 'file' if stat.S_ISREG(mode) else 'unknown'
        require(actual == entry['type'], 'Archive/manifest type mismatch: ' + path)
        require(info.is_dir() == (actual == 'directory') and info.file_size == entry['bytes'], 'Archive metadata mismatch: ' + path)
        if actual == 'directory':
            require(entry['bytes'] == 0 and entry['sha256'] == sha(b''), 'Nonempty directory payload')
        if actual == 'symlink':
            require(isinstance(entry.get('link_target'), str) and entry['bytes'] <= 65536, 'Invalid symlink evidence')
    link_inventory = document.get('link_inventory', [])
    require(len(link_inventory) == len({x['path'] for x in link_inventory}), 'Duplicate link inventory path')
    require({x['path']: x['target'] for x in link_inventory} ==
            {p: e['link_target'] for p, e in inventory.items() if e['type'] == 'symlink'}, 'Link inventory mismatch')
    manifest_mode = mapping[manifest_name].external_attr >> 16
    # zipfile.writestr creates this pinned manifest with permission bits only.
    require(not mapping[manifest_name].is_dir() and stat.S_IFMT(manifest_mode) in (0, stat.S_IFREG),
            'Snapshot manifest must be regular or an untyped ZIP data entry')
    return document, inventory, mapping, raw


@contextlib.contextmanager
def descend(rootfd, parts, create=False):
    fd = os.dup(rootfd)
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def write_new(rootfd, path, chunks, expected=None, mode=0o600):
    pieces = safe_parts(path)
    with descend(rootfd, pieces[:-1], create=True) as parent:
        fd = os.open(pieces[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
        digest, count = hashlib.sha256(), 0
        with os.fdopen(fd, 'wb') as output:
            for data in chunks:
                count += len(data)
                require(expected is None or count <= expected['bytes'], 'Decompressed payload exceeds manifest size')
                digest.update(data)
                output.write(data)
            if expected:
                require((count, digest.hexdigest()) == (expected['bytes'], expected['sha256']), 'Payload integrity failed: ' + path)
        return count


def file_chunks(stream):
    while True:
        data = stream.read(CHUNK)
        if not data:
            break
        yield data


def extract_snapshot(archive_path, snapshot, output):
    """Extract files under root and links under sibling LINK-QUARANTINE, inert."""
    output = Path(output).absolute()
    # Open the ZIP via an anchored no-follow descriptor; do not execute its contents.
    with input_stream(str(archive_path)) as source, zipfile.ZipFile(source) as archive:
        document, inventory, mapping, raw_manifest = inspect_archive(archive, snapshot)
        parent = open_dir(output.parent)
        try:
            os.mkdir(output.name, mode=0o700, dir_fd=parent)  # fails if anything already exists
            rootfd = os.open(output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        finally:
            os.close(parent)
        prefix = snapshot['root'] + '/'
        links = []
        files = directories = 0
        try:
            write_new(rootfd, prefix + snapshot['manifest'], [raw_manifest])
            for path, entry in inventory.items():
                info = mapping[prefix + path]
                if entry['type'] == 'directory':
                    # Read to EOF even zero-byte directory entries, verifying ZIP CRC.
                    require(archive.read(info) == b'', 'Nonempty directory data')
                    with descend(rootfd, safe_parts(prefix + path), create=True):
                        pass
                    directories += 1
                elif entry['type'] == 'symlink':
                    raw = archive.read(info)
                    require((len(raw), sha(raw)) == (entry['bytes'], entry['sha256']), 'Link payload integrity failed')
                    require(raw == entry['link_target'].encode('utf-8'), 'Link literal target mismatch')
                    quarantine = 'LINK-QUARANTINE/%06d.target.txt' % len(links)
                    write_new(rootfd, quarantine, [raw], entry)
                    links.append({'archive_path': prefix + path, 'quarantine_path': quarantine,
                                  'literal_target': entry['link_target'], 'bytes': len(raw), 'sha256': sha(raw)})
                else:
                    with archive.open(info) as stream:
                        # Preserve ordinary execute bits, but never setuid/setgid/sticky or global write.
                        file_mode = 0o700 if entry.get('mode', 0) & 0o111 else 0o600
                        write_new(rootfd, prefix + path, file_chunks(stream), entry, file_mode)
                    files += 1
            receipt = {'schema': 'intune-r2-safe-extraction/1', 'status': 'PASS', 'archive': str(archive_path),
                       'source_revision': document.get('source_revision'), 'regular_files_verified': files,
                       'directories_verified': directories, 'quarantined_symlinks': links,
                       'hardlink_groups_preserved_as_independent_regular_files': document.get('hardlink_groups', []),
                       'archive_manifest_sha256': sha(raw_manifest), 'snapshot_root': snapshot['root'],
                       'all_zip_entry_crc_verified': True, 'all_payload_sha256_verified': True,
                       'archive_manifest_member_sets_equal': True,
                       'restored_mode_policy': 'private directories 0700; files 0600 or 0700 when original execute bits set; no special bits',
                       'no_archive_content_executed': True, 'historical_file_set_discrepancy_closed': False,
                       'warning': 'Literal symlink targets are inert evidence. No links recreated. Hardlink fixture semantics require deliberate isolated reconstruction.'}
            write_new(rootfd, 'EXTRACTION-RECEIPT.json', [json.dumps(receipt, indent=2).encode() + b'\n'])
            os.fsync(rootfd)
            return receipt
        finally:
            os.close(rootfd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, help='Distribution JSON: HTTPS URL or local path')
    outputs = parser.add_mutually_exclusive_group(required=True)
    outputs.add_argument('--output', help='New complete ZIP path; existing files are never replaced')
    outputs.add_argument('--archive-input', help='Verify this existing full ZIP without downloading/reassembling')
    parser.add_argument('--extract', help='Optional NEW directory, with quarantined literal link evidence')
    args = parser.parse_args(argv)
    try:
        manifest = loads(read_limited(args.manifest, 1024 * 1024))
        validate_distribution(manifest)
        if args.archive_input:
            digest, total = hashlib.sha256(), 0
            with input_stream(args.archive_input) as stream:
                for chunk in file_chunks(stream):
                    total += len(chunk)
                    require(total <= ARCHIVE_BYTES, 'Existing archive exceeds pinned size')
                    digest.update(chunk)
            require((total, digest.hexdigest()) == (ARCHIVE_BYTES, ARCHIVE_SHA256), 'Existing archive integrity failed')
            result = {'archive': args.archive_input, 'bytes': total, 'sha256': digest.hexdigest()}
        else:
            result = reassemble(manifest, args.manifest, args.output)
        if args.extract:
            result['extraction'] = extract_snapshot(result['archive'], manifest['snapshot'], args.extract)
        print(json.dumps(result, indent=2))
        return 0
    except (RestoreError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print('RESTORE FAILED: %s. Any partial ZIP or extraction is preserved; use a new destination after investigation.' % error,
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
