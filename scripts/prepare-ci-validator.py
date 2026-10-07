#!/usr/bin/env python3
"""Recover the already qualified Linux validator from its exact public package.

No installation, maintainer script or library execution occurs. The package is
checked before dpkg-deb parses it; tar members are read, never extracted by path.
This prepares a local CI dependency, not a new cryptographic or host approval.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile

PACKAGE_BYTES = 161290
PACKAGE_SHA256 = '74d6f8fbd65f7f71b6f4f4223bef5fb57c1c14cd4e9ce788ead2b88e8c3ee236'
LIBRARY_BYTES = 355040
LIBRARY_SHA256 = 'fe00408090ea084504d7cb0130af56a22554fe299034b864551b65a64ca8a7b5'
LIBRARY_MEMBER = './usr/lib/x86_64-linux-gnu/libsodium.so.23.3.0'
COPYRIGHT_MEMBER = './usr/share/doc/libsodium23/copyright'
TOOL = Path('/usr/bin/dpkg-deb')


def read_package(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size != PACKAGE_BYTES:
            raise ValueError('validator_package_size_or_type')
        data = source.read(PACKAGE_BYTES + 1)
        after = os.fstat(source.fileno())
    identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if identity(before) != identity(after) or len(data) != PACKAGE_BYTES or hashlib.sha256(data).hexdigest() != PACKAGE_SHA256:
        raise ValueError('validator_package_digest')
    return data


def prepare(package, output):
    data = read_package(package)
    if sys.platform != 'linux' or not TOOL.is_file() or TOOL.is_symlink():
        raise ValueError('validator_preparation_host_unavailable')
    tool_sha = hashlib.sha256(TOOL.read_bytes()).hexdigest()
    # Feed the already checked bytes, not the potentially replaced input path.
    result = subprocess.run([str(TOOL), '--fsys-tarfile', '-'], input=data,
                            capture_output=True, timeout=30, check=True,
                            env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
    if hashlib.sha256(TOOL.read_bytes()).hexdigest() != tool_sha or len(result.stdout) > 2 * 1024 * 1024:
        raise ValueError('validator_package_tool_or_output_changed')
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode='r:') as archive:
        members = archive.getmembers()
        if len(members) > 1000:
            raise ValueError('validator_package_member_bound')
        values = {}
        for name in (LIBRARY_MEMBER, COPYRIGHT_MEMBER):
            selected = [member for member in members if member.name == name]
            if len(selected) != 1 or not selected[0].isreg() or not 0 < selected[0].size <= 512 * 1024:
                raise ValueError('validator_package_member_type_or_identity')
            with archive.extractfile(selected[0]) as stream:
                values[name] = stream.read(512 * 1024 + 1)
            if len(values[name]) != selected[0].size:
                raise ValueError('validator_package_member_size')
    library = values[LIBRARY_MEMBER]
    if len(library) != LIBRARY_BYTES or hashlib.sha256(library).hexdigest() != LIBRARY_SHA256:
        raise ValueError('validator_library_digest')
    output = Path(output).absolute()
    if '..' in output.parts or any(parent.is_symlink() for parent in (output, *output.parents)):
        raise ValueError('validator_output_path')
    output.mkdir(mode=0o700)
    receipt = {'schema': 'intune-ci-validator-preparation/1', 'package_sha256': PACKAGE_SHA256,
               'package_bytes': PACKAGE_BYTES, 'library_sha256': LIBRARY_SHA256,
               'library_bytes': LIBRARY_BYTES, 'dpkg_deb_sha256': tool_sha,
               'copyright_sha256': hashlib.sha256(values[COPYRIGHT_MEMBER]).hexdigest(),
               'system_installation': False, 'library_executed': False,
               'scope': 'Exact existing dependency bytes; observed extraction tool, not a qualified CI image.'}
    for name, contents in [('libsodium.so.23.3.0', library), ('copyright', values[COPYRIGHT_MEMBER]),
                           ('receipt.json', (json.dumps(receipt, indent=2) + '\n').encode())]:
        fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(contents); stream.flush(); os.fsync(stream.fileno())
    if (output / 'libsodium.so.23.3.0').read_bytes() != library:
        raise ValueError('validator_output_readback')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        receipt = prepare(args.package, args.output)
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'FAIL', 'error_type': type(error).__name__,
                          'preserve_partial_output': True}), file=sys.stderr)
        return 2
    print(json.dumps(dict(receipt, status='PASS')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
