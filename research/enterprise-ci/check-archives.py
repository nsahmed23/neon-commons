#!/usr/bin/env python3
"""Verify release-candidate archive integrity before clean extraction; never approve release."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


def _safe_name(name):
    return (isinstance(name, str) and bool(name) and not name.startswith('/') and
            not any(c in name for c in ('\\', ':', '\x00')) and
            all(part not in ('', '.', '..') for part in name.split('/')))


def verify_archive(path, prefix):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError('Archive must be a bounded regular file.')
    files = {}; total = 0
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if not 1 <= len(members) <= 10000: raise ValueError('Archive entry count is outside the supported limit.')
        for member in members:
            name = member.filename
            if not _safe_name(name) or not name.startswith(prefix + '/'):
                raise ValueError('Unsafe archive member path.')
            relative = name[len(prefix) + 1:]
            mode = member.external_attr >> 16
            if relative in files or member.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                raise ValueError('Duplicate or nonregular archive member.')
            total += member.file_size
            if member.file_size > MAX_MEMBER_BYTES or total > MAX_TOTAL_BYTES:
                raise ValueError('Archive expands beyond its supported limit.')
            files[relative] = archive.read(member)  # Also verifies ZIP CRC.
    if 'SHA256SUMS' not in files: raise ValueError('Missing member digest manifest.')
    expected = {}
    for line in files['SHA256SUMS'].decode('utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if match is None or not _safe_name(match[2]) or match[2] in expected or match[2] == 'SHA256SUMS':
            raise ValueError('Malformed member digest manifest.')
        expected[match[2]] = match[1]
    if set(expected) != set(files) - {'SHA256SUMS'}:
        raise ValueError('Archive digest manifest does not cover every member.')
    if any(hashlib.sha256(files[name]).hexdigest() != sha for name, sha in expected.items()):
        raise ValueError('Archive member digest mismatch.')
    return files


IDENTITY = 'BUILD-IDENTITY.json'
LISTING = 'SHA256SUMS'
# The fields that name the build: the runtime and the source record of one build hold the same value for each.
SHARED_FIELDS = ('built_at', 'commit', 'dirty', 'product_version', 'schema_version', 'tree')
OTHER = {'runtime': 'source', 'source': 'runtime'}


def _record(kind, files):
    if IDENTITY not in files:
        raise ValueError(f'The {kind} archive has no {IDENTITY}.')
    try:
        record = json.loads(files[IDENTITY].decode('utf-8'))
    except ValueError:  # Also an UnicodeDecodeError.
        raise ValueError(f'The {kind} {IDENTITY} is not valid JSON.') from None
    if not isinstance(record, dict):
        raise ValueError(f'The {kind} {IDENTITY} is not a JSON object.')
    return record


def _content(files):
    """The member count and content digest that an archive's own identity record must state: every member except the record and
    the digest list, as sorted `sha256  name` lines. intune_iac.build_identity.content_digest does the same; this checker does not
    import the product it checks."""
    digests = {name: hashlib.sha256(data).hexdigest() for name, data in files.items() if name not in (LISTING, IDENTITY)}
    lines = ''.join(f'{digest}  {name}\n' for name, digest in sorted(digests.items()))
    return len(digests), hashlib.sha256(lines.encode()).hexdigest()


def check_identity_records(archives):
    """Refuse, naming the field, unless the two identity records belong together. `archives` maps 'runtime' and 'source' to
    {'files': the verified members, 'sha256': the archive file's digest}. In this order: both archives hold a record; the fields that
    name the build agree; each record's companion names the other archive as it is (its kind, and its archive and content digests where
    the companion carries them); each record describes its own archive (kind, member count, content digest)."""
    records = {kind: _record(kind, archive['files']) for kind, archive in archives.items()}
    content = {kind: _content(archive['files']) for kind, archive in archives.items()}
    for field in SHARED_FIELDS:
        values = [json.dumps(record[field], sort_keys=True) for record in records.values() if field in record]
        if len(values) != 2 or values[0] != values[1]:
            raise ValueError(f'The runtime and source {IDENTITY} records do not agree on {field}.')
    for kind, other in OTHER.items():
        companion = records[kind].get('companion')
        if not isinstance(companion, dict):
            raise ValueError(f'The {kind} {IDENTITY} has no companion naming the {other} archive.')
        named = {'archive_kind': other}
        named.update({key: value for key, value in (('archive_sha256', archives[other]['sha256']),
                                                    ('content_sha256', content[other][1])) if key in companion})
        for key, value in named.items():
            if companion.get(key) != value:
                raise ValueError(f'The {kind} {IDENTITY} field companion.{key} does not name the {other} archive.')
    for kind, record in records.items():
        for field, value in (('archive_kind', kind), ('file_count', content[kind][0]), ('content_sha256', content[kind][1])):
            held = record.get(field)
            if held != value or type(held) is not type(value):  # A boolean is not a count.
                raise ValueError(f'The {kind} {IDENTITY} field {field} does not match the {kind} archive.')


def check_release(directory, output):
    root = Path(directory).absolute(); destination = Path(output).absolute()
    if any(p.is_symlink() for p in [root, *root.parents, destination, *destination.parents]):
        raise ValueError('Symlinked archive or extraction roots are unsupported.')
    if destination == root or root in destination.parents or destination in root.parents:
        raise ValueError('Archive and extraction directories must not overlap.')
    receipt_path = root / 'Intune_IaC_Plugin_Archive_Receipt.json'
    if receipt_path.is_symlink() or not receipt_path.is_file() or receipt_path.stat().st_size > 1024 * 1024:
        raise ValueError('Invalid archive receipt.')
    receipt = json.loads(receipt_path.read_text())
    version = receipt.get('version')
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('Unsupported release version.')
    expected = {f'Intune_IaC_Plugin_{version}.zip': 'intune-iac',
                f'Intune_IaC_Plugin_{version}_Source.zip': 'intune-iac-source'}
    rows = receipt.get('archives')
    if not isinstance(rows, list) or len(rows) != 2 or {r.get('filename') for r in rows if isinstance(r, dict)} != set(expected):
        raise ValueError('Expected exactly one runtime and one source archive.')
    snapshots = {}; digests = {}; reports = []
    for row in rows:
        name = row['filename']; path = root / name
        files = verify_archive(path, expected[name]); data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row.get('sha256') or len(data) != row.get('bytes'):
            raise ValueError('Archive differs from its build receipt.')
        if len(files) != row.get('files') or len(files) - 1 != row.get('listed_hashes'):
            raise ValueError('Archive count differs from its build receipt.')
        snapshots[expected[name]] = files; digests[expected[name]] = row['sha256']
        reports.append({'archive': name, 'files': len(files), 'listed_hashes': len(files) - 1})
    runtime = snapshots['intune-iac']; source = snapshots['intune-iac-source']
    # Each archive's SHA256SUMS lists its own members and its BUILD-IDENTITY.json describes that archive (its kind and its companion),
    # so those two differ between the archives by design; verify_archive has already matched every member, the record included, to its own list.
    own_to_each_archive = ('SHA256SUMS', 'BUILD-IDENTITY.json')
    if any(name not in source or data != source[name] for name, data in runtime.items() if name not in own_to_each_archive):
        raise ValueError('Runtime bytes differ from source release bytes.')
    check_identity_records({'runtime': {'files': runtime, 'sha256': digests['intune-iac']},
                            'source': {'files': source, 'sha256': digests['intune-iac-source']}})
    destination.mkdir(mode=0o700)  # A previous extraction must not be reused.
    for prefix, files in snapshots.items():
        for name, data in files.items():
            path = destination / prefix / name; path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream: stream.write(data)
    return {'success': True, 'archives': reports, 'shared_runtime_bytes_verified': True, 'identity_records_verified': True,
            'production_approved': False, 'scope': 'Candidate archive integrity and clean local extraction only.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = check_release(args.directory, args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__': main()
