"""The build identity of an installed copy: which build it came from, and whether its files still match.

`scripts/build-release.py` writes BUILD-IDENTITY.json into every archive it produces. `doctor` prints the report
below so that a person who reports a problem can name the exact build. The report is read-only: it hashes the files
the archive's own SHA256SUMS lists, looks for files under the unpacked folder that it does not list, and changes nothing.

A checkout has no identity record; that is reported as such, never guessed from the surrounding folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

SCHEMA = 'build-identity/1'
IDENTITY_FILE = 'BUILD-IDENTITY.json'
LISTING_FILE = 'SHA256SUMS'
PACKAGE_ROOT = Path(__file__).resolve().parents[1]

MAX_RECORD_BYTES = 64 * 1024
MAX_LISTING_BYTES = 8 * 1024 * 1024
MAX_LISTED_FILES = 20000
MAX_NAMED_FILES = 20
MAX_WALKED_FILES = 200000
# What the unlisted-file look does not count, named in every report so nobody has to guess: the two folders the candidate guide
# itself creates at the top of the unpacked folder (the environment that holds the dependencies, and the demonstration folder).
# A bytecode cache elsewhere is counted: Python runs cached bytecode in place of the source it was made from, so a cache that no
# SHA256SUMS line covers can change what a listed module does while the listed source stays intact.
NOT_COUNTED_AT_TOP = ('.venv', 'demo')
NOT_COUNTED = ['.venv (the top-level folder)', 'demo (the top-level folder)']
_LINE = re.compile(r'^([0-9a-f]{64})  (\S[^\n]*)$')
_GIT_ID = re.compile(r'^[0-9a-f]{40}$')
_KINDS = ('runtime', 'source')


def content_digest(digests):
    """Digest of an archive's files: every listed member except the identity record, sorted, as SHA256SUMS lines.

    The record cannot hold a digest that includes itself, so it holds this one; the record's own bytes are covered
    by its line in SHA256SUMS.
    """
    lines = ''.join(f'{digest}  {name}\n' for name, digest in sorted(digests.items()) if name != IDENTITY_FILE)
    return hashlib.sha256(lines.encode()).hexdigest()


def _unusable(status, note):
    return {'status': status, 'note': note}


def _read_limited(path, limit):
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('too large')
    return data


def _safe_name(name):
    return (bool(name) and '\\' not in name and ':' not in name and not name.startswith('/')
            and all(part not in {'', '.', '..'} for part in name.split('/')))


def _listing(root):
    digests = {}
    for line in _read_limited(root / LISTING_FILE, MAX_LISTING_BYTES).decode('utf-8').splitlines():
        match = _LINE.match(line)
        if not match or not _safe_name(match.group(2)) or match.group(2) in digests or len(digests) >= MAX_LISTED_FILES:
            raise ValueError('malformed listing')
        digests[match.group(2)] = match.group(1)
    return digests


def _record(data):
    value = json.loads(data.decode('utf-8'))
    ok = (isinstance(value, dict) and value.get('schema_version') == SCHEMA and value.get('archive_kind') in _KINDS
          and all(isinstance(value.get(key), str) for key in ('product_version', 'built_at', 'content_sha256'))
          and isinstance(value.get('file_count'), int) and not isinstance(value.get('file_count'), bool)
          and all(value.get(key) is None or (isinstance(value.get(key), str) and _GIT_ID.match(value[key]))
                  for key in ('commit', 'tree'))
          and value.get('dirty') in (True, False, None) and isinstance(value.get('companion'), (dict, type(None))))
    if not ok:
        raise ValueError('malformed record')
    return value


def _modified(root, digests):
    names = []
    for name, expected in sorted(digests.items()):
        path = root.joinpath(*name.split('/'))
        try:
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                names.append(name)
        except OSError:
            names.append(name)
    return names


def _unlisted(root, digests):
    """Paths under `root` that the listing does not name, sorted. A link is an entry and is not followed; the folders in
    NOT_COUNTED are skipped. The walk stops after MAX_WALKED_FILES files, so a huge tree cannot make `doctor` hang."""
    names, walked = [], 0
    for folder, dirs, files in os.walk(root, followlinks=False):
        here = Path(folder)
        top = here == root
        kept = []
        for name in sorted(dirs):
            if top and name in NOT_COUNTED_AT_TOP:
                continue
            if (here / name).is_symlink():
                files.append(name)
            else:
                kept.append(name)
        dirs[:] = kept
        for name in files:
            walked += 1
            relative = (here / name).relative_to(root).as_posix()
            if relative not in digests and relative != LISTING_FILE:
                names.append(relative)
        if walked > MAX_WALKED_FILES:
            break
    return sorted(names)


def report(root=None):
    """The build identity of the copy at `root` (default: the copy this module belongs to), as plain data."""
    root = Path(PACKAGE_ROOT if root is None else root)
    record_path = root / IDENTITY_FILE
    if not record_path.is_file():
        return _unusable('not_a_release_build', 'This is a source checkout or an unpacked tree without '
                         + IDENTITY_FILE + '; only a release archive carries a build identity.')
    try:
        record = _record(_read_limited(record_path, MAX_RECORD_BYTES))
        digests = _listing(root)
    except (OSError, ValueError, UnicodeDecodeError):
        return _unusable('unreadable', IDENTITY_FILE + ' or ' + LISTING_FILE + ' cannot be read as a build record.')
    others = {name for name in digests if name != IDENTITY_FILE}
    if (IDENTITY_FILE not in digests or record['content_sha256'] != content_digest(digests)
            or record['file_count'] != len(others)):
        return dict(_unusable('inconsistent', LISTING_FILE + ' does not match the build identity record; '
                              'the copy was changed after the build or assembled from different builds.'),
                    **{key: record[key] for key in ('archive_kind', 'product_version', 'commit', 'tree', 'built_at')})
    modified = _modified(root, digests)
    unlisted = _unlisted(root, digests)
    if modified:
        note = 'Listed files are missing or differ from the build; this is not the build named above.'
    elif unlisted:
        note = ('Files that ' + LISTING_FILE + ' does not list are present; this is not the build named above. '
                'Not counted: ' + ', '.join(NOT_COUNTED) + '.')
    else:
        note = ('Every file listed in ' + LISTING_FILE + ' is present and unchanged, and no other file is present. '
                'Not counted: ' + ', '.join(NOT_COUNTED) + '.')
    if any('__pycache__' in name.split('/') for name in unlisted):
        note += (' A bytecode cache counts: Python runs cached bytecode in place of its source. Delete the __pycache__ folders; the '
                 'commands in the candidate guide start Python with -B and write none.')
    return {'status': 'modified' if modified or unlisted else 'identified', 'archive_kind': record['archive_kind'],
            'product_version': record['product_version'], 'commit': record['commit'], 'tree': record['tree'],
            'dirty': record['dirty'], 'built_at': record['built_at'], 'file_count': record['file_count'],
            'content_sha256': record['content_sha256'], 'companion': record['companion'],
            'modified_files': modified[:MAX_NAMED_FILES], 'modified_count': len(modified),
            'unlisted_files': unlisted[:MAX_NAMED_FILES], 'unlisted_count': len(unlisted),
            'unlisted_not_counted': list(NOT_COUNTED), 'note': note}
