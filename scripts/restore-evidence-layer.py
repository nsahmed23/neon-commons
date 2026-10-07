#!/usr/bin/env python3
"""Verify a pinned evidence ZIP before extracting into a NEW private directory.

Adapted from the independently qualified R2 restoration helper. No archive
content is executed. Literal negative-test links are created last and are never
traversed. A failed partial extraction stays available for investigation.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

CHUNK = 1024 * 1024
MAX_JSON = 64 * CHUNK
MAX_ENTRIES = 200000
MAX_TOTAL = 32 * 1024**3
MAX_PATH_DEPTH = 128
HEX = re.compile(r'[0-9a-f]{64}\Z')
SCHEMAS = ('complete-continuation-snapshot/2', 'intune-r3-evidence-supplement/1', 'intune-r4-evidence-supplement/1')
R2_HELPER_SHA256 = 'd073a532a5d89bda9fe682269dae64526d1749ded0c9972323c6f4d569919dcb'

class RestoreError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise RestoreError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def platform_check():
    require(os.name == 'posix' and hasattr(os, 'O_DIRECTORY') and hasattr(os, 'O_NOFOLLOW')
            and all(call in os.supports_dir_fd for call in (os.open, os.mkdir, os.symlink, os.readlink))
            and os.listdir in os.supports_fd,
            'POSIX directory-descriptor/no-follow extraction host required')

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
    # Valid POSIX control/format filenames occur in retained negative evidence.
    # Preserve those exact bytes; all diagnostics/receipts use escaped JSON.
    # NUL, path separators, traversal and device/stream aliases remain rejected.
    require(len(path.encode('utf-8')) <= 4096, 'Archive path length limit exceeded')
    require(not path.startswith('/') and not re.match(r'^[A-Za-z]:', path), 'Absolute archive path')
    pieces = path.split('/')
    require(len(pieces) <= MAX_PATH_DEPTH, 'Archive path depth limit exceeded')
    require(all(p not in ('', '.', '..') for p in pieces), 'Traversal/empty path component')
    # Windows device aliases and alternate streams must not change interpretation.
    for piece in pieces:
        require(':' not in piece and not piece.endswith((' ', '.')), 'Nonportable archive path')
        require(not re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', piece),
                'Reserved archive filename')
    return pieces

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

def inspect_archive(archive, snapshot):
    """Read only metadata first; exact typed inventory is required before writes."""
    infos = archive.infolist()
    require(len(infos) <= MAX_ENTRIES, 'Archive entry limit exceeded')
    mapping = {}
    for info in infos:
        require(info.orig_filename == info.filename, 'ZIP filename was truncated or aliased')
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
    require(document['schema'] == snapshot['schema'] and snapshot['schema'] in SCHEMAS, 'Unsupported snapshot inventory schema')
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
    require(sum(entry['bytes'] for entry in inventory.values()) <= MAX_TOTAL, 'Total payload limit exceeded')
    require(snapshot['manifest'] not in inventory, 'Manifest cannot inventory itself')
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
    hardlinks = document.get('hardlink_groups', [])
    require(isinstance(hardlinks, list), 'Invalid hardlink metadata')
    group_names, linked_paths = set(), set()
    for group in hardlinks:
        require(isinstance(group, dict) and isinstance(group.get('group'), str)
                and group['group'] and group['group'] not in group_names, 'Invalid/duplicate hardlink group')
        group_names.add(group['group'])
        paths = group.get('paths')
        require(isinstance(paths, list) and len(paths) >= 2 and all(isinstance(p, str) for p in paths),
                'Invalid hardlink paths')
        require(len(set(paths)) == len(paths) and not linked_paths.intersection(paths), 'Duplicate hardlink path')
        require(all(p in inventory and inventory[p]['type'] == 'file' for p in paths), 'Hardlink path is not a declared file')
        require(len({(inventory[p]['bytes'], inventory[p]['sha256']) for p in paths}) == 1, 'Hardlink bytes differ')
        linked_paths.update(paths)
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
            output.flush()
            os.fsync(output.fileno())
        os.fsync(parent)
        return count

def file_chunks(stream):
    while True:
        data = stream.read(CHUNK)
        if not data:
            break
        yield data


def verify_output(rootfd, expected):
    """Check physical names/types and read bytes back without following links.

    Unexpected entries remain in place. This is an observed final check, never
    a claim about the cause of the earlier workspace's unexplained files.
    """
    actual = {}
    def visit(directory, prefix, depth):
        require(depth <= MAX_PATH_DEPTH + 1, 'Extracted path depth exceeds bound')
        for name in os.listdir(directory):
            path = prefix + name
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            kind = ('directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode)
                    else 'symlink' if stat.S_ISLNK(info.st_mode) else 'unsupported')
            actual[path] = kind
            require(len(actual) <= MAX_ENTRIES + 2, 'Extracted entry count exceeds bound')
            entry = expected.get(path)
            if kind == 'directory':
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                try:
                    held = os.fstat(fd)
                    require((held.st_dev, held.st_ino) == (info.st_dev, info.st_ino), 'Extracted directory changed')
                    visit(fd, path + '/', depth + 1)
                finally:
                    os.close(fd)
            elif entry is not None and kind == entry['type'] == 'file':
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                with os.fdopen(fd, 'rb') as source:
                    held = os.fstat(source.fileno())
                    require(stat.S_ISREG(held.st_mode) and held.st_nlink == 1 and
                            (held.st_dev, held.st_ino, held.st_size) == (info.st_dev, info.st_ino, entry['bytes']),
                            'Extracted file identity/size changed: ' + path)
                    digest, count = hashlib.sha256(), 0
                    for chunk in file_chunks(source):
                        count += len(chunk)
                        require(count <= entry['bytes'], 'Extracted file grew: ' + path)
                        digest.update(chunk)
                    after = os.fstat(source.fileno())
                    require((count, digest.hexdigest()) == (entry['bytes'], entry['sha256'])
                            and (held.st_size, held.st_mtime_ns, held.st_ctime_ns) ==
                            (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'Extracted bytes changed: ' + path)
            elif entry is not None and kind == entry['type'] == 'symlink':
                require(os.readlink(name, dir_fd=directory) == entry['link_target'], 'Extracted literal link changed: ' + path)
    visit(rootfd, '', 0)
    require(set(actual) == set(expected), 'Extracted physical file set differs; unexpected/missing entries preserved: ' +
            repr({'unexpected': sorted(set(actual) - set(expected))[:20], 'missing': sorted(set(expected) - set(actual))[:20]}))
    require(all(actual[path] == entry['type'] for path, entry in expected.items()), 'Extracted physical type map differs')


def extract(archive_path, *, archive_bytes, archive_sha256, snapshot, output):
    require(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW'), 'POSIX no-follow extraction host required')
    require(type(archive_bytes) is int and 0 < archive_bytes <= MAX_TOTAL and HEX.fullmatch(archive_sha256 or ''), 'Invalid archive pin')
    require(len(safe_parts(snapshot['root'])) == 1 and snapshot['root'] != 'EXTRACTION-RECEIPT.json', 'Invalid snapshot root')
    require(len(safe_parts(snapshot['manifest'])) == 1 and HEX.fullmatch(snapshot['manifest_sha256']), 'Invalid manifest pin')
    source_path, output = Path(archive_path).absolute(), Path(output).absolute()
    require('..' not in source_path.parts and '..' not in output.parts, 'Ambiguous filesystem path')
    parent = open_dir(source_path.parent)
    try:
        fd = os.open(source_path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size == archive_bytes, 'Archive size/type mismatch before extraction')
        digest = hashlib.sha256()
        for chunk in file_chunks(source):
            digest.update(chunk)
        require(digest.hexdigest() == archive_sha256, 'Archive SHA-256 mismatch before extraction')
        source.seek(0)
        with zipfile.ZipFile(source) as archive:
            document, inventory, mapping, raw_manifest = inspect_archive(archive, snapshot)
            parent = open_dir(output.parent)
            try:
                os.mkdir(output.name, mode=0o700, dir_fd=parent)
                rootfd = os.open(output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                os.fsync(parent)
            finally:
                os.close(parent)
            prefix = snapshot['root'] + '/'
            links, files, directories = [], 0, 0
            try:
                write_new(rootfd, prefix + snapshot['manifest'], [raw_manifest])
                for path, entry in inventory.items():
                    info = mapping[prefix + path]
                    if entry['type'] == 'directory':
                        require(archive.read(info) == b'', 'Nonempty directory data')
                        with descend(rootfd, safe_parts(prefix + path), create=True) as directory:
                            os.fsync(directory)
                        directories += 1
                    elif entry['type'] == 'symlink':
                        raw = archive.read(info)
                        require((len(raw), sha(raw)) == (entry['bytes'], entry['sha256']), 'Link payload integrity failed')
                        require(raw == entry['link_target'].encode('utf-8') and b'\0' not in raw, 'Link literal target mismatch')
                        links.append({'path': prefix + path, 'target': entry['link_target'], 'sha256': sha(raw)})
                    else:
                        with archive.open(info) as stream:
                            write_new(rootfd, prefix + path, file_chunks(stream), entry,
                                      0o700 if entry.get('mode', 0) & 0o111 else 0o600)
                        files += 1
                # No later archive member can traverse a recreated negative-test
                # link. All parents were required to be declared directories.
                for link in links:
                    pieces = safe_parts(link['path'])
                    with descend(rootfd, pieces[:-1]) as directory:
                        os.symlink(link['target'], pieces[-1], dir_fd=directory)
                        require(os.readlink(pieces[-1], dir_fd=directory) == link['target'], 'Link publication mismatch')
                        os.fsync(directory)
                after = os.fstat(source.fileno())
                signature = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                require(signature(before) == signature(after), 'Archive changed; partial extraction preserved')
                physical = {prefix + path: entry for path, entry in inventory.items()}
                physical[snapshot['root']] = {'type': 'directory'}
                physical[prefix + snapshot['manifest']] = {'type': 'file', 'bytes': len(raw_manifest), 'sha256': sha(raw_manifest)}
                verify_output(rootfd, physical)
                require(signature(before) == signature(os.fstat(source.fileno())), 'Archive changed during readback; partial extraction preserved')
                receipt = {'schema': 'intune-typed-evidence-extraction/1', 'status': 'PASS',
                    'archive_bytes': archive_bytes, 'archive_sha256': archive_sha256,
                    'manifest_sha256': sha(raw_manifest), 'snapshot_schema': document['schema'],
                    'regular_files_verified': files, 'directories_verified': directories,
                    'literal_links_created_last': links, 'links_followed': 0,
                    'hardlink_groups_preserved_as_separate_regular_files': document.get('hardlink_groups', []),
                    'mode_policy': 'private 0700 directories; regular0600 or0700 when original execute bits set; original metadata retained in manifest',
                    'all_payload_sha256_and_zip_crc_verified': True, 'exact_archive_manifest_member_set': True,
                    'physical_file_set_and_types_checked_before_receipt': True,
                    'regular_bytes_read_back_after_extraction': True,
                    'content_executed': False, 'historical_three_unexpected_files_closed': False}
                write_new(rootfd, 'EXTRACTION-RECEIPT.json', [json.dumps(receipt, indent=2).encode() + b'\n'])
                os.fsync(rootfd)
                return receipt
            finally:
                os.close(rootfd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--bytes', type=int, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--snapshot-root', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--schema', choices=SCHEMAS, required=True)
    parser.add_argument('--output', required=True, help='NEW extraction directory; existing paths are never replaced')
    args = parser.parse_args(argv)
    try:
        result = extract(args.archive, archive_bytes=args.bytes, archive_sha256=args.sha256,
            snapshot={'root': args.snapshot_root, 'manifest': args.manifest,
                      'manifest_sha256': args.manifest_sha256, 'schema': args.schema}, output=args.output)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile) as error:
        # Filesystem and ZIP exceptions may contain hostile literal names.
        # Preserve inspectable diagnostics without emitting terminal controls.
        print('EXTRACTION FAILED: %s. Archive and partial output are preserved.' %
              json.dumps(str(error), ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
