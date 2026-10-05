#!/usr/bin/env python3
"""Build a deterministic source ZIP and SHA-256 manifests; never executes commands.

Run after tools/verify-materials.py. The output must be outside this source tree.
The resulting ZIP still needs verification after clean extraction.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {'__pycache__', '.pytest_cache'}


def included(path):
    relative = path.relative_to(ROOT)
    return relative.parts[0] != '.git' and not EXCLUDE.intersection(relative.parts) and path.suffix != '.pyc'


def paths():
    result = []
    for path in sorted(ROOT.rglob('*')):
        if not included(path):
            continue
        if path.is_symlink():
            raise ValueError('Symlink in distribution')
        if path.is_file():
            result.append(path)
    return result


def manifest(base):
    selected = [p for p in paths() if p.is_relative_to(base) and p != base / 'SHA256SUMS.txt']
    (base / 'SHA256SUMS.txt').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(base).as_posix() + '\n'
        for p in selected), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    output = parser.parse_args().output.absolute()
    if output.is_relative_to(ROOT):
        raise ValueError('ZIP output must be outside the source tree')
    manifest(ROOT / 'corrections')
    manifest(ROOT)
    output.parent.mkdir(parents=True, exist_ok=True)
    files = paths()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            entry = zipfile.ZipInfo('intune-iac-offline-repair/' + path.relative_to(ROOT).as_posix(),
                                    date_time=(2026, 9, 30, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, path.read_bytes())
    print(json.dumps({'files': len(files), 'bytes': output.stat().st_size,
                      'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                      'clean_extraction_verification': 'required'}))


if __name__ == '__main__':
    main()
