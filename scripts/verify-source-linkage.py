#!/usr/bin/env python3
"""Bind every selected release source byte to an exact local Git commit.

This offline release gate reads raw Git objects; it never checks out content or
runs hooks, filters, helpers or a remote. It is a cooperative private-workspace
check, not protection against a hostile process rewriting the repository.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
INVENTORY = 'release-source-files.txt'


def fail(message):
    raise ValueError(message)


def safe_path(value):
    if (type(value) is not str or not value or len(value) > 2048
            or '\\' in value or ':' in value or any(ord(c) < 32 for c in value)
            or any(part in ('', '.', '..') for part in value.split('/'))):
        fail('Unsafe source inventory path.')
    return value


@contextlib.contextmanager
def source_reader(root):
    if os.name != 'posix' or not hasattr(os, 'O_NOFOLLOW'):
        fail('This release verifier requires POSIX no-follow directory handles.')
    root = Path(root).absolute()
    if any(path.is_symlink() for path in (root, *root.parents)):
        fail('Source root has a symbolic-link ancestor.')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    anchor = os.open(root, flags)
    def read(name):
        parts = safe_path(name).split('/'); directory = os.dup(anchor)
        try:
            for part in parts[:-1]:
                child = os.open(part, flags, dir_fd=directory)
                os.close(directory); directory = child
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, 'rb') as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_FILE:
                    fail('Source must be a bounded regular file with one link.')
                raw = stream.read(MAX_FILE + 1); after = os.fstat(stream.fileno())
                fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink')
                if len(raw) != before.st_size or any(getattr(before, f) != getattr(after, f) for f in fields):
                    fail('Source changed during verification.')
                return raw
        finally:
            os.close(directory)
    try:
        yield read
    finally:
        os.close(anchor)


def verify(repository, source, revision, *, git_executable, git_sha256):
    if not re.fullmatch(r'[0-9a-f]{40}', revision) or not re.fullmatch(r'[0-9a-f]{64}', git_sha256):
        fail('Require exact SHA-1 commit and SHA-256 Git executable pins.')
    repository = Path(repository).absolute(); source = Path(source).absolute()
    gitdir = repository / '.git'; tool = Path(git_executable).absolute()
    if not gitdir.is_dir() or any(p.is_symlink() for p in (gitdir, *gitdir.parents, tool, *tool.parents)):
        fail('Require a direct local repository and executable without symbolic links.')
    for name in ('commondir', 'shallow', 'objects/info/alternates', 'objects/info/http-alternates'):
        if (gitdir/name).exists() or (gitdir/name).is_symlink():
            fail('Git indirection is not supported by this release gate.')
    with source_reader(repository) as read_repository:
        config = read_repository('.git/config')
    if len(config) > 1024*1024 or re.search(rb'(?im)^\s*\[\s*(include|includeif|extensions)\b', config) or re.search(
            rb'(?im)^\s*(worktree|alternateRefsCommand|promisor|partialclonefilter)\s*=', config):
        fail('Git configuration indirection is not supported.')
    for directory in (gitdir/'objects', gitdir/'objects/pack', gitdir/'objects/info'):
        if directory.is_symlink() or not directory.is_dir(): fail('Unsafe Git object directory.')
    for index, path in enumerate((gitdir/'objects/pack').iterdir()):
        info = path.lstat()
        if index >= 1000 or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or path.suffix == '.promisor':
            fail('Unsafe or remote-promised Git object pack.')
    descriptor = os.open(tool, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE:
            fail('Git executable is not a bounded ordinary file.')
        with os.fdopen(os.dup(descriptor), 'rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != git_sha256: fail('Git executable pin mismatch.')
        env = {'PATH':'/usr/bin:/bin', 'HOME':'/nonexistent', 'LANG':'C', 'LC_ALL':'C',
            'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_SYSTEM':'/dev/null', 'GIT_CONFIG_GLOBAL':'/dev/null',
            'GIT_CONFIG_COUNT':'0', 'GIT_NO_REPLACE_OBJECTS':'1', 'GIT_TERMINAL_PROMPT':'0',
            'GIT_OPTIONAL_LOCKS':'0', 'GIT_NO_LAZY_FETCH':'1', 'GIT_ATTR_NOSYSTEM':'1'}
        argv = [str(tool), '--no-pager', '--literal-pathspecs', '--git-dir='+str(gitdir),
            '-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false', '-c','protocol.allow=never',
            '-c','core.attributesFile=/dev/null','-c','core.preloadIndex=false']
        start = time.monotonic(); cache = {}; total = 0; object_records = []
        def command(arguments):
            if time.monotonic()-start > 600: fail('Release object-read deadline exceeded.')
            run = subprocess.run(argv+arguments, cwd=repository, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False,
                pass_fds=(descriptor,), executable='/proc/self/fd/'+str(descriptor))
            if run.returncode or len(run.stderr) > 8192: fail('Pinned Git object read failed.')
            return run.stdout
        def object_bytes(kind, oid):
            nonlocal total
            key = (kind, oid)
            if key in cache: return cache[key]
            if not re.fullmatch(r'[0-9a-f]{40}', oid) or len(cache) >= 20000:
                fail('Invalid or excessive Git object selection.')
            loose = gitdir/'objects'/oid[:2]/oid[2:]
            if loose.parent.is_symlink() or loose.is_symlink(): fail('Symbolic Git object is forbidden.')
            if loose.exists():
                value = loose.stat()
                if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1: fail('Unsafe loose Git object.')
            size = command(['cat-file', '-s', oid])
            if not re.fullmatch(rb'[0-9]+\n', size) or int(size) > MAX_FILE: fail('Git object exceeds bound.')
            raw = command(['cat-file', kind, oid]); total += len(raw)
            if len(raw) != int(size) or total > MAX_TOTAL: fail('Git object size or aggregate bound failed.')
            if hashlib.sha1(kind.encode()+b' '+str(len(raw)).encode()+b'\0'+raw).hexdigest() != oid:
                fail('Raw Git object digest mismatch.')
            object_records.append({'kind':kind, 'object_id':oid, 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()})
            cache[key] = raw; return raw
        commit = object_bytes('commit', revision)
        first = commit.split(b'\n',1)[0]
        if not re.fullmatch(rb'tree [0-9a-f]{40}', first): fail('Commit tree is malformed.')
        tree = first[5:].decode(); trees = {}
        def entries(oid):
            if oid in trees: return trees[oid]
            raw = object_bytes('tree', oid); position = 0; rows = {}
            while position < len(raw):
                space = raw.find(b' ',position); zero = raw.find(b'\0',space+1)
                if space < position or zero < space or zero+21 > len(raw): fail('Malformed Git tree.')
                mode = raw[position:space]; name = raw[space+1:zero]
                if (mode not in (b'40000',b'100644',b'100755',b'120000',b'160000')
                        or not name or name in rows or name in (b'.',b'..') or b'/' in name): fail('Malformed Git tree entry.')
                rows[name] = (mode,raw[zero+1:zero+21].hex()); position = zero+21
            trees[oid] = rows; return rows
        def blob(name):
            parts = safe_path(name).split('/'); oid = tree
            for index, part in enumerate(parts):
                item = entries(oid).get(part.encode())
                if item is None: fail('Selected path is absent from the exact commit.')
                mode, oid = item
                if mode not in ((b'40000',) if index < len(parts)-1 else (b'100644',b'100755')):
                    fail('Selected source is a link, submodule or non-regular object.')
            return oid, object_bytes('blob',oid)
        with source_reader(source) as read:
            inventory = read(INVENTORY); _, committed_inventory = blob(INVENTORY)
            if inventory != committed_inventory: fail('Source inventory differs from the exact commit.')
            names = [safe_path(line) for line in inventory.decode('utf-8').splitlines() if line and not line.startswith('#')]
            if INVENTORY not in names or not 1 <= len(names) <= 10000 or len(set(names)) != len(names):
                fail('Invalid complete release inventory.')
            rows = []
            for name in sorted(names):
                oid, committed = blob(name); actual = read(name)
                if actual != committed: fail('Selected source bytes differ from the exact commit: '+name)
                rows.append({'path':name,'blob_id':oid,'bytes':len(actual),'sha256':hashlib.sha256(actual).hexdigest()})
            for row in rows:
                actual = read(row['path'])
                if len(actual) != row['bytes'] or hashlib.sha256(actual).hexdigest() != row['sha256']:
                    fail('Source changed before verification completed.')
        with source_reader(repository) as read_repository:
            if read_repository('.git/config') != config: fail('Git configuration changed during verification.')
        return {'schema_version':'release-source-linkage/1', 'status':'PASS', 'source_commit':revision,
            'tree_object':tree, 'commit_sha256':hashlib.sha256(commit).hexdigest(),
            'repository':str(repository), 'source':str(source), 'git_executable':str(tool), 'git_sha256':git_sha256,
            'inventory_sha256':hashlib.sha256(inventory).hexdigest(), 'files':rows,
            'objects':object_records, 'publisher_authenticated':False, 'repository_modified':False,
            'scope':'Every explicit selected source byte, including inventory, matches independently rehashed raw commit/tree/blob objects. Unselected files and organizational approvals are not certified.'}
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repository','source','commit','git-executable','git-sha256','output'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    output = Path(args.output).absolute()
    if output.exists() or output.is_symlink() or any(p.is_symlink() for p in output.parents):
        parser.error('Output must be a new path without symbolic-link ancestors.')
    try:
        result = verify(args.repository,args.source,args.commit,git_executable=args.git_executable,git_sha256=args.git_sha256)
    except (ValueError, OSError, subprocess.SubprocessError, UnicodeError) as error:
        result = {'schema_version':'release-source-linkage/1','status':'FAIL','error_type':type(error).__name__,
            'error':str(error),'source_commit':args.commit}
    fd = os.open(output, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(result,stream,indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({'status':result['status'],'receipt':str(output),'files':len(result.get('files',[]))}))
    return 0 if result['status']=='PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
