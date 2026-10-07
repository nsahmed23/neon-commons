#!/usr/bin/env python3
"""Fetch a pinned helper unauthenticated; reassemble and independently hash R2."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

HELPER_SHA256 = 'd073a532a5d89bda9fe682269dae64526d1749ded0c9972323c6f4d569919dcb'
ARCHIVE_SHA256 = '7117ab67ce6ae1912aa2c984774e6370216f3eb28be1510d0c6814cb4c295d0b'
ARCHIVE_BYTES = 2289864715
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--manifest-url', required=True)
parser.add_argument('--helper-url', required=True)
parser.add_argument('--directory', default='/workspace/intune-publication/public-download')
args = parser.parse_args()
root = Path(args.directory)
root.mkdir(mode=0o700)
started = time.time()
receipt = {'status': 'IN_PROGRESS', 'started_unix': started, 'manifest_url': args.manifest_url,
           'helper_url': args.helper_url, 'authentication_supplied': False}

def document(name, value):
    (root / name).write_text(json.dumps(value, indent=2) + '\n')

def fetch(url, limit):
    if not url.startswith('https://'):
        raise ValueError('HTTPS required')
    request = urllib.request.Request(url, headers={'User-Agent': 'Intune-R2-Public-Qualification/1'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Public document exceeds limit')
        return data, {'url': url, 'final_url': response.geturl(), 'http_status': response.status,
                      'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

try:
    helper, receipt['helper_download'] = fetch(args.helper_url, 1024 * 1024)
    if hashlib.sha256(helper).hexdigest() != HELPER_SHA256:
        raise ValueError('Public helper differs from qualified helper SHA-256')
    with (root / 'restore_r2.py').open('xb') as out:
        out.write(helper)
    manifest_raw, receipt['manifest_download'] = fetch(args.manifest_url, 1024 * 1024)
    manifest = json.loads(manifest_raw)
    (root / 'R2-DISTRIBUTION-MANIFEST.json').write_bytes(manifest_raw)
    if (manifest['archive']['bytes'], manifest['archive']['sha256']) != (ARCHIVE_BYTES, ARCHIVE_SHA256):
        raise ValueError('Public manifest changed complete ZIP pins')
    archive = root / 'Intune_Atmos_Wally_Continuation_20261005_R2.zip'
    command = [sys.executable, '-B', str(root / 'restore_r2.py'), '--manifest', args.manifest_url,
               '--output', str(archive)]
    document('command.json', {'argv': command, 'cwd': str(root), 'authentication_supplied': False})
    with (root / 'stdout.json').open('xb') as stdout, (root / 'stderr.log').open('xb') as stderr:
        completed = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr)
    receipt['return_code'] = completed.returncode
    if completed.returncode:
        raise ValueError('Public reassembly command failed; raw stderr/partial bytes preserved')
    h = hashlib.sha256()
    count = 0
    with archive.open('rb') as stream:
        while data := stream.read(1024 * 1024):
            count += len(data)
            h.update(data)
    receipt['reassembled_archive'] = {'path': str(archive), 'bytes': count, 'sha256': h.hexdigest()}
    if (count, h.hexdigest()) != (ARCHIVE_BYTES, ARCHIVE_SHA256):
        raise ValueError('Independent complete archive verification failed')
    receipt.update(status='PASS', part_count=len(manifest['parts']), fresh_downloaded_helper_verified=True,
                   archive_byte_identity_verified=True, extraction_repeated=False,
                   note='Exact ZIP and unchanged helper already passed full extraction; public transfer is independently verified here.')
except BaseException as error:
    receipt.update(status='FAIL', error_type=type(error).__name__, error=str(error))
    raise
finally:
    receipt.update(finished_unix=time.time(), seconds=time.time() - started)
    document('PUBLIC-DOWNLOAD-RECEIPT.json', receipt)
