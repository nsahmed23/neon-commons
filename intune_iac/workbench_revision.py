"""Bounded Linux Git object reading for an explicitly pinned local repository.

No checkout, hooks, filters, credential helper, remote or revision expression is
executed. Commit/tree/blob bytes are independently rehashed. This verifies a
selected object and working bytes, not publisher identity or branch protection.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time
from .io import AppError
from .workbench_provenance import _read
from . import protected


def _fail(code):raise AppError(code,'Selected Git revision cannot be verified under the bounded read-only profile.')


def verify_revision(repo,revision,sources,*,git_executable,git_sha256):
    if not re.fullmatch('[0-9a-f]{40}',str(revision)) or not re.fullmatch('[0-9a-f]{64}',str(git_sha256)):_fail('workbench_git_pin')
    root=Path(repo).absolute();gitdir=root/'.git';tool=Path(git_executable).absolute()
    if not gitdir.is_dir() or any(p.is_symlink() for p in (gitdir,*gitdir.parents,tool,*tool.parents)):_fail('workbench_git_path')
    if any((gitdir/name).exists() or (gitdir/name).is_symlink() for name in ('commondir','shallow','objects/info/alternates','objects/info/http-alternates')):_fail('workbench_git_indirection')
    # Includes and worktree/extension routing expand file access beyond this
    # declared repository; reject instead of trusting command-line overrides.
    config=_read(gitdir/'config')
    if re.search(rb'(?im)^\s*\[\s*(include|includeif|extensions)\b',config) or re.search(rb'(?im)^\s*(worktree|alternateRefsCommand|promisor|partialclonefilter)\s*=',config):_fail('workbench_git_config_indirection')
    if type(sources) is not list or not 1<=len(sources)<=100:_fail('workbench_git_sources_bound')
    objects=gitdir/'objects'
    for directory in (objects,objects/'pack',objects/'info'):
        if directory.is_symlink() or not directory.is_dir():_fail('workbench_git_object_store')
    for index,path in enumerate((objects/'pack').iterdir()):
        if index>=1000:_fail('workbench_git_object_store_bound')
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or path.suffix=='.promisor':_fail('workbench_git_object_store')
    descriptor=os.open(tool,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>32*1024*1024:_fail('workbench_git_pin')
        with os.fdopen(os.dup(descriptor),'rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=git_sha256:_fail('workbench_git_pin')
        executable='/proc/self/fd/'+str(descriptor)
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C','LC_ALL':'C','GIT_CONFIG_NOSYSTEM':'1',
             'GIT_CONFIG_SYSTEM':'/dev/null','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_COUNT':'0','GIT_NO_REPLACE_OBJECTS':'1',
             'GIT_TERMINAL_PROMPT':'0','GIT_OPTIONAL_LOCKS':'0','GIT_NO_LAZY_FETCH':'1','GIT_PAGER':'cat','GIT_ATTR_NOSYSTEM':'1'}
        argv=[str(tool),'--no-pager','--literal-pathspecs','--git-dir='+str(gitdir),'-c','core.hooksPath=/dev/null',
              '-c','core.fsmonitor=false','-c','core.pager=cat','-c','core.attributesFile=/dev/null','-c','core.preloadIndex=false']
        cache={};total=0;started=time.monotonic();commands=[]
        def read(kind,oid):
            nonlocal total
            if (kind,oid) in cache:return cache[(kind,oid)]
            if not re.fullmatch('[0-9a-f]{40}',oid) or len(commands)>=300 or time.monotonic()-started>30:_fail('workbench_git_bound')
            loose=objects/oid[:2]/oid[2:]
            if loose.parent.is_symlink() or loose.is_symlink():_fail('workbench_git_object_store')
            if loose.exists():
                info=loose.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:_fail('workbench_git_object_store')
            command=argv+['cat-file',kind,oid]
            raw=protected._supervise(command,cwd=root,env=env,pass_fds=(descriptor,),timeout=10,
                                     output_limit=2*1024*1024,executable=executable)
            total+=len(raw)
            if total>16*1024*1024:_fail('workbench_git_bound')
            actual=hashlib.sha1(kind.encode()+b' '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            if actual!=oid:_fail('workbench_git_object_mismatch')
            commands.append({'kind':kind,'object_id':oid,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
            cache[(kind,oid)]=raw;return raw
        commit=read('commit',revision)
        first=commit.split(b'\n',1)[0]
        if not re.fullmatch(rb'tree [0-9a-f]{40}',first):_fail('workbench_git_commit')
        tree=first[5:].decode();parsed={}
        def entries(oid):
            if oid in parsed:return parsed[oid]
            raw=read('tree',oid);rows={};pos=0
            while pos<len(raw):
                space=raw.find(b' ',pos);zero=raw.find(b'\0',space+1)
                if space<pos or zero<space or zero+21>len(raw):_fail('workbench_git_tree')
                mode=raw[pos:space];name=raw[space+1:zero]
                if mode not in (b'40000',b'100644',b'100755',b'120000',b'160000') or name in rows or not name or b'/' in name or name in (b'.',b'..'):_fail('workbench_git_tree')
                rows[name]=(mode,raw[zero+1:zero+21].hex());pos=zero+21
                if len(rows)>10000:_fail('workbench_git_tree_bound')
            parsed[oid]=rows;return rows
        records=[];mismatches=[]
        for source in sources:
            path=source['path'];parts=PurePosixPath(path).parts
            if not parts or PurePosixPath(path).is_absolute() or '..' in parts or len(parts)>64:_fail('workbench_git_source_path')
            oid=tree;missing=False
            for index,part in enumerate(parts):
                item=entries(oid).get(part.encode('utf-8'))
                if item is None:missing=True;break
                mode,oid=item
                if index<len(parts)-1 and mode!=b'40000':missing=True;break
                if index==len(parts)-1 and mode not in (b'100644',b'100755'):missing=True;break
            if missing:
                mismatches.append({'path':path,'reason':'absent_or_not_regular_in_selected_revision'});continue
            blob=read('blob',oid);current=_read(root/path)
            if hashlib.sha256(current).hexdigest()!=source['sha256']:_fail('workbench_git_working_source_changed')
            equal=blob==current
            record={'path':path,'blob_id':oid,'committed_sha256':hashlib.sha256(blob).hexdigest(),'working_sha256':source['sha256'],'equal':equal}
            records.append(record)
            if not equal:mismatches.append({'path':path,'reason':'working_bytes_differ_from_selected_revision'})
        if _read(gitdir/'config')!=config:_fail('workbench_git_config_changed')
        return {'schema_version':'workbench-git-revision/1','selected_revision':revision,'commit_object_verified':True,
                'working_sources_match_revision':not mismatches,'mismatches':mismatches,'sources':records,
                'git_executable':str(tool),'git_sha256':git_sha256,'object_reads':commands,'publisher_authenticated':False,
                'scope':'selected literal resolver sources only; implementation/provider/state files are not certified',
                'network':'denied_by_existing_protected_supervisor','repository_modified':False}
    finally:os.close(descriptor)
