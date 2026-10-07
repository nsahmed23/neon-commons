#!/usr/bin/env python3
"""Build a new, deterministic, typed R4 evidence supplement from a frozen epoch.

Adapted from retained build_r3_evidence.py, SHA-256
1589a992f076e13025cb10325380255a8ebe0b4efe16ef33a0b368171a525752.
No evidence is executed, followed, deleted or silently excluded. Explicit pinned
socket/FIFO omissions preserve metadata, not their unarchivable IPC endpoints.
This is packaging, not public-suitability clearance or qualification promotion.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import zipfile

SCHEMA = 'intune-r4-evidence-supplement/1'
MANIFEST = 'R4-EVIDENCE-MANIFEST.json'
ARCHIVE_ROOT = 'Intune_R4_Evidence_20261007'
CHUNK = 1024 * 1024
MAX_ENTRIES = 199990
MAX_TOTAL = 32 * 1024**3
MAX_FILE = 16 * 1024**3
MAX_JSON = 64 * CHUNK
HEX = re.compile(r'[0-9a-f]{64}\Z')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + '\n').encode('ascii')


def loads(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def safe(path):
    require(isinstance(path, str) and path and '\\' not in path and '\x00' not in path,
            'Invalid archive path')
    require(len(path.encode('utf-8')) <= 4096, 'Archive path too long')
    parts = path.split('/')
    require(len(parts) <= 128 and all(p not in ('', '.', '..') for p in parts), 'Unsafe path components')
    for part in parts:
        require(':' not in part and not part.endswith((' ', '.')) and
                not re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part),
                'Unsupported archive filename')
    return parts


def absolute(path):
    path = Path(path)
    require('..' not in path.parts, 'Traversal in local path')
    return Path(os.path.abspath(path))


def signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def open_dir(path):
    require(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW') and os.listdir in os.supports_fd,
            'POSIX directory-descriptor/no-follow host required')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute(path).parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def descend(rootfd, parts):
    fd = os.dup(rootfd)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def read_pinned_document(path, expected):
    require(isinstance(expected, str) and HEX.fullmatch(expected), 'Document SHA-256 required')
    path = absolute(path)
    parent = open_dir(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as source:
            before = os.fstat(source.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_JSON, 'Invalid document type/size')
            raw = source.read(MAX_JSON + 1)
            require(len(raw) <= MAX_JSON and sha(raw) == expected, 'Document integrity failed')
            require(signature(os.fstat(source.fileno())) == signature(before) ==
                    signature(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'Document changed')
    finally:
        os.close(parent)
    value = loads(raw)
    require(isinstance(value, dict), 'Document must be an object')
    return value


def omission_index(document):
    if document is None:
        return {}
    require(set(document) == {'schema_version', 'entries'} and
            document['schema_version'] == 'intune-r4-ipc-omissions/1', 'Invalid IPC omission document')
    result = {}
    require(isinstance(document['entries'], list), 'Invalid IPC omission entries')
    for entry in document['entries']:
        require(isinstance(entry, dict) and set(entry) == {'path', 'type', 'reason'}, 'Invalid IPC omission entry')
        safe(entry['path'])
        require(entry['path'] not in result and entry['type'] in ('socket', 'fifo') and
                isinstance(entry['reason'], str) and 1 <= len(entry['reason']) <= 4096,
                'Only explicitly justified, unique socket/FIFO omissions are supported')
        result[entry['path']] = entry
    return result


def scan(rootfd, omissions):
    entries = {}
    total = 0
    def visit(fd, prefix, depth):
        nonlocal total
        require(depth <= 128, 'Evidence depth limit exceeded')
        directory_before = signature(os.fstat(fd))
        for name in sorted(os.listdir(fd)):
            relative = prefix + name
            safe(relative)
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            require(len(entries) < MAX_ENTRIES, 'Evidence entry limit exceeded')
            entries[relative] = signature(info)
            mode = info.st_mode
            if stat.S_ISDIR(mode):
                require(relative not in omissions, 'A directory cannot be omitted')
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    require(signature(os.fstat(child)) == signature(info), 'Directory changed before census')
                    visit(child, relative + '/', depth + 1)
                finally:
                    os.close(child)
            elif stat.S_ISREG(mode):
                require(relative not in omissions and info.st_size <= MAX_FILE, 'Regular file omission/size rejected')
                total += info.st_size
                require(total <= MAX_TOTAL, 'Evidence byte limit exceeded')
            elif stat.S_ISLNK(mode):
                require(relative not in omissions, 'A literal link cannot be omitted')
            else:
                kind = 'socket' if stat.S_ISSOCK(mode) else 'fifo' if stat.S_ISFIFO(mode) else 'unsupported'
                require(relative in omissions and omissions[relative]['type'] == kind,
                        'Unlisted/unsupported special entry preserved at source: ' + relative)
            require(signature(os.stat(name, dir_fd=fd, follow_symlinks=False)) == signature(info), 'Entry changed in census')
        require(signature(os.fstat(fd)) == directory_before, 'Directory changed in census')
    visit(rootfd, '', 0)
    require(set(omissions) <= set(entries), 'An explicit IPC omission is absent')
    return dict(sorted(entries.items()))


def info_for(name, mode):
    item = zipfile.ZipInfo(name, date_time=(2026, 10, 7, 0, 0, 0))
    item.create_system = 3
    item.external_attr = mode << 16
    if stat.S_ISDIR(mode):
        item.external_attr |= 0x10
    item.compress_type = (zipfile.ZIP_STORED if name.lower().endswith(
        ('.zip', '.whl', '.gz', '.xz', '.png', '.jpg', '.zst', '.7z')) else zipfile.ZIP_DEFLATED)
    return item


def verify(stream, manifest, raw_manifest):
    inventory = {ARCHIVE_ROOT + '/' + item['path'] + ('/' if item['type'] == 'directory' else ''): item
                 for item in manifest['entries']}
    manifest_name = ARCHIVE_ROOT + '/' + MANIFEST
    stream.seek(0)
    with zipfile.ZipFile(stream) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        require(len(names) == len(set(names)) and set(names) == set(inventory) | {manifest_name},
                'ZIP/manifest file-set mismatch')
        require(archive.read(manifest_name) == raw_manifest, 'Manifest bytes changed')
        for info in infos:
            require(info.orig_filename == info.filename and not info.flag_bits & 1, 'ZIP filename/encryption mismatch')
            if info.filename == manifest_name:
                continue
            expected = inventory[info.filename]
            digest, count = hashlib.sha256(), 0
            with archive.open(info) as member:
                while data := member.read(CHUNK):
                    count += len(data)
                    require(count <= expected['bytes'], 'ZIP member exceeds declared size')
                    digest.update(data)
            require((count, digest.hexdigest()) == (expected['bytes'], expected['sha256']), 'Payload integrity mismatch')
            mode = info.external_attr >> 16
            kind = ('symlink' if stat.S_ISLNK(mode) else 'directory' if stat.S_ISDIR(mode)
                    else 'file' if stat.S_ISREG(mode) else 'unsupported')
            require(kind == expected['type'] and info.is_dir() == (kind == 'directory'), 'ZIP type mismatch')
    return {'verified_entries': len(inventory), 'all_zip_crc_verified': True,
            'all_payload_sha256_verified': True, 'exact_member_set_verified': True}


def build(epoch, output, provenance, *, provenance_sha256=None, omissions=None, omissions_sha256=None):
    epoch, output = absolute(epoch), absolute(output)
    require(epoch != output and epoch not in output.parents, 'Output must be outside input epoch')
    require(isinstance(provenance, dict), 'Provenance object required')
    omitted = omission_index(omissions)
    safe(epoch.name)
    rootfd, parent = open_dir(epoch), None
    receipt = None
    primary_error = None
    try:
        root_identity = signature(os.fstat(rootfd))
        before = scan(rootfd, omitted)
        parent = open_dir(output.parent)
        parent_identity = signature(os.fstat(parent))[:2]
        partial, receipt_name = output.name + '.partial', output.name + '.receipt.json'
        require(all(not exists(parent, name) for name in (output.name, partial, receipt_name)), 'Destination already exists')
        receipt = {'status': 'RUNNING', 'input_epoch': str(epoch), 'archive': str(output), 'started_unix': time.time()}
        fd = os.open(partial, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'w+b') as destination:
            entries, links, hardlinks, omitted_metadata = [], [], {}, []
            prefix = 'work/evidence/' + epoch.name
            for name in ('work', 'work/evidence', prefix):
                entries.append({'path': name, 'type': 'directory', 'mode': 0o700, 'bytes': 0,
                                'sha256': sha(b''), 'structural_parent': True})
            with zipfile.ZipFile(destination, 'w', allowZip64=True, compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
                for item in entries:
                    archive.writestr(info_for(ARCHIVE_ROOT + '/' + item['path'] + '/', stat.S_IFDIR | 0o700), b'')
                for relative, expected in before.items():
                    mode = expected[2]
                    name = prefix + '/' + relative
                    item = {'path': name, 'mode': stat.S_IMODE(mode), 'mtime_ns': expected[4]}
                    parts = safe(relative)
                    with descend(rootfd, parts[:-1]) as held:
                        base = parts[-1]
                        require(signature(os.stat(base, dir_fd=held, follow_symlinks=False)) == expected,
                                'Source changed before archive: ' + relative)
                        if relative in omitted:
                            omitted_metadata.append(dict(omitted[relative], path=name, mode=stat.S_IMODE(mode),
                                source_bytes=expected[3], mtime_ns=expected[4], payload_archived=False,
                                source_preserved=True, ipc_endpoint_recreated=False))
                        elif stat.S_ISDIR(mode):
                            item.update(type='directory', bytes=0, sha256=sha(b''))
                            archive.writestr(info_for(ARCHIVE_ROOT + '/' + name + '/', mode), b'')
                        elif stat.S_ISLNK(mode):
                            target = os.readlink(base, dir_fd=held)
                            raw = os.fsencode(target)
                            require(len(raw) <= 65536, 'Link target exceeds bound')
                            archive.writestr(info_for(ARCHIVE_ROOT + '/' + name, mode), raw)
                            item.update(type='symlink', bytes=len(raw), sha256=sha(raw), link_target=target,
                                        link_not_dereferenced=True)
                            links.append({'path': name, 'target': target})
                        else:
                            fd = os.open(base, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=held)
                            digest, count = hashlib.sha256(), 0
                            with os.fdopen(fd, 'rb') as source:
                                require(signature(os.fstat(source.fileno())) == expected, 'Source identity changed at open')
                                with archive.open(info_for(ARCHIVE_ROOT + '/' + name, mode), 'w', force_zip64=True) as member:
                                    while data := source.read(CHUNK):
                                        count += len(data)
                                        require(count <= expected[3], 'Source grew during archive')
                                        digest.update(data)
                                        member.write(data)
                                require(signature(os.fstat(source.fileno())) == expected, 'Source changed during archive')
                            require(count == expected[3], 'Source size changed')
                            item.update(type='file', bytes=count, sha256=digest.hexdigest())
                            if expected[6] > 1:
                                hardlinks.setdefault(expected[:2], []).append(name)
                        require(signature(os.stat(base, dir_fd=held, follow_symlinks=False)) == expected,
                                'Source changed after archive: ' + relative)
                    if relative not in omitted:
                        entries.append(item)
                manifest = {'schema': SCHEMA, 'complete_repository': False, 'complete_evidence_epoch': not bool(omitted),
                    'complete_archivable_evidence_epoch': True, 'epoch': epoch.name, 'provenance': provenance,
                    'provenance_document_sha256': provenance_sha256, 'entries': entries, 'link_inventory': links,
                    'hardlink_groups': [{'group': 'hardlink-%d' % (i + 1), 'paths': paths}
                        for i, paths in enumerate(hardlinks.values()) if len(paths) > 1],
                    'explicit_ipc_omissions': omitted_metadata, 'ipc_omissions_document_sha256': omissions_sha256,
                    'manifest_excluded_from_own_inventory': True,
                    'extraction_policy': 'Pinned no-follow POSIX helper; verify exact regular bytes first, create literal links last; never execute nested repositories or recreate IPC endpoints.',
                    'public_suitability_approved': False, 'historical_R2_three_file_discrepancy_closed': False}
                raw_manifest = canonical(manifest)
                require(len(raw_manifest) <= MAX_JSON, 'Manifest exceeds restore bound')
                archive.writestr(info_for(ARCHIVE_ROOT + '/' + MANIFEST, stat.S_IFREG | 0o600), raw_manifest)
            destination.flush()
            os.fsync(destination.fileno())
            verification = verify(destination, manifest, raw_manifest)
            require(scan(rootfd, omitted) == before and signature(os.fstat(rootfd)) == root_identity,
                    'Source epoch changed; partial preserved')
            reopened = open_dir(epoch)
            try:
                require(signature(os.fstat(reopened)) == root_identity, 'Source root path identity changed')
            finally:
                os.close(reopened)
            reopened = open_dir(output.parent)
            try:
                require(signature(os.fstat(reopened))[:2] == parent_identity, 'Output parent path identity changed')
            finally:
                os.close(reopened)
            final_info = os.fstat(destination.fileno())
            require(signature(os.stat(partial, dir_fd=parent, follow_symlinks=False)) == signature(final_info),
                    'Partial output path identity changed')
            destination.seek(0)
            digest = hashlib.sha256()
            while data := destination.read(CHUNK):
                digest.update(data)
            require(signature(os.fstat(destination.fileno())) == signature(final_info), 'Partial archive changed during hash')
            os.link(partial, output.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            # Publication is a distinct trust boundary: a pathname may have
            # changed after the preceding held-descriptor checks. Validate the
            # final name and exact bytes without following it before accepting
            # publication or unlinking any partial name. A substituted artifact
            # stays preserved as a failed output, never a successful archive.
            published_fd = os.open(output.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(published_fd, 'rb') as published:
                published_info = os.fstat(published.fileno())
                expected_identity = (final_info.st_dev, final_info.st_ino, final_info.st_mode,
                                     final_info.st_size, final_info.st_mtime_ns)
                require((published_info.st_dev, published_info.st_ino, published_info.st_mode,
                         published_info.st_size, published_info.st_mtime_ns) == expected_identity,
                        'Published archive identity changed; all outputs preserved')
                published_digest, published_count = hashlib.sha256(), 0
                while data := published.read(CHUNK):
                    published_count += len(data)
                    require(published_count <= final_info.st_size, 'Published archive grew')
                    published_digest.update(data)
                require((published_count, published_digest.hexdigest()) == (final_info.st_size, digest.hexdigest()),
                        'Published archive bytes changed; all outputs preserved')
                require(signature(os.fstat(published.fileno())) == signature(published_info) ==
                        signature(os.stat(output.name, dir_fd=parent, follow_symlinks=False)),
                        'Published archive changed during readback')
                require(signature(os.stat(partial, dir_fd=parent, follow_symlinks=False)) == signature(published_info),
                        'Partial output name changed after publication; all outputs preserved')
            os.unlink(partial, dir_fd=parent)
            os.fsync(parent)
        receipt.update(status='PASS', bytes=final_info.st_size, sha256=digest.hexdigest(),
            manifest_sha256=sha(raw_manifest), manifest=MANIFEST, snapshot_root=ARCHIVE_ROOT, schema=SCHEMA,
            regular_files=sum(x['type'] == 'file' for x in entries),
            regular_bytes=sum(x['bytes'] for x in entries if x['type'] == 'file'),
            directories=sum(x['type'] == 'directory' for x in entries), literal_symlinks=len(links),
            explicit_ipc_omissions=omitted_metadata, complete_repository=False,
            complete_evidence_epoch=not bool(omitted), complete_archivable_evidence_epoch=True,
            input_epoch_unchanged=True, public_suitability_approved=False,
            historical_R2_three_file_discrepancy_closed=False, published_readback_verified=True, **verification)
    except BaseException as error:
        primary_error = error
        if receipt is not None:
            receipt.update(status='FAIL', error_type=type(error).__name__, error=str(error),
                           partial_preserved=str(output.with_name(output.name + '.partial')))
        raise
    finally:
        try:
            try:
                if receipt is not None:
                    receipt['finished_unix'] = time.time()
                    fd = os.open(receipt_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(canonical(receipt))
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.fsync(parent)
            except BaseException as recording_error:
                if primary_error is None:
                    raise
                # Keep the original failure/cancellation as the raised cause;
                # the independently escaped secondary diagnostic remains visible
                # even when no durable receipt could be written.
                print('EVIDENCE RECEIPT RECORDING FAILED: ' + json.dumps(
                    {'type': type(recording_error).__name__, 'error': str(recording_error),
                     'primary_error_type': type(primary_error).__name__, 'primary_error_preserved': True},
                    ensure_ascii=True), file=sys.stderr)
        finally:
            os.close(rootfd)
            if parent is not None:
                os.close(parent)
    return receipt


def exists(fd, name):
    try:
        os.stat(name, dir_fd=fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--epoch', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--provenance', required=True)
    parser.add_argument('--provenance-sha256', required=True)
    parser.add_argument('--ipc-omissions')
    parser.add_argument('--ipc-omissions-sha256')
    args = parser.parse_args(argv)
    try:
        require(bool(args.ipc_omissions) == bool(args.ipc_omissions_sha256), 'IPC document and SHA-256 must be supplied together')
        provenance = read_pinned_document(args.provenance, args.provenance_sha256)
        omissions = read_pinned_document(args.ipc_omissions, args.ipc_omissions_sha256) if args.ipc_omissions else None
        result = build(args.epoch, args.output, provenance, provenance_sha256=args.provenance_sha256,
                       omissions=omissions, omissions_sha256=args.ipc_omissions_sha256)
        print(canonical(result).decode('ascii'), end='')
        return 0
    except BaseException as error:
        print('EVIDENCE BUILD FAILED: ' + json.dumps({'type': type(error).__name__, 'error': str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
