"""Relocatable qualification inputs with unchanged independently reviewed pins.

No download, ambient executable search, caller-supplied digest, installation or
host-profile change. These inputs support tests; they grant no worker authority.
Path validation assumes a cooperative trusted user; it is not hostile namespace
isolation. The held parent/name is revalidated, not every ancestor after lookup.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat

CHUNK=1024*1024
PINNED={
    'docker':{'environment':'INTUNE_QUALIFICATION_DOCKER','version':'28.4.0',
        'bytes':43556144,'sha256':'27f239f97492c434e091a70b41b8796c698f0aa2b6052c6f9c28da4ee7ae888b',
        'default':'/usr/local/bin/docker'},
    'tofu':{'environment':'INTUNE_QUALIFICATION_TOFU','version':'1.13.1',
        'bytes':114188448,'sha256':'a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a',
        'default':'/workspace/intune-recovery/native-reprobe/tools/tofu'},
    'relay_v2':{'environment':'INTUNE_QUALIFICATION_RELAY_V2','version':'relay-v2-half-close-repair',
        'bytes':888056,'sha256':'2e321b0efa62fcd710401b814a18b8afd3140ea0202fd1b516875bd814564697',
        'default':'/workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-broker/relay/intune-worker-relay-v2'},
    'relay_v3':{'environment':'INTUNE_QUALIFICATION_RELAY_V3','version':'relay-v3-exclusive-readiness',
        'bytes':888088,'sha256':'4255592e3b477d9c7fba06a59536d07effaa2a54e9e848f4908fecae672a25a0',
        'default':'/workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-broker/relay/intune-worker-relay-v3'}}

def require(ok,message):
    if not ok:raise ValueError(message)

def absolute(value):
    require(isinstance(value,(str,Path)),'An explicit local path is required')
    text=str(value);path=Path(text)
    require(path.is_absolute() and len(text)<=4096 and not any(ord(c)<32 or ord(c)==127 for c in text)
        and all(part not in ('','.','..') for part in text.split('/')[1:]),'A bounded absolute literal path is required')
    return path

@contextmanager
def parent(path):
    path=absolute(path);fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        yield fd,path.name
    finally:os.close(fd)

def signature(info):return (info.st_dev,info.st_ino,info.st_mode,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)

@contextmanager
def opened(path,*,maximum=128*CHUNK,executable=False):
    path=absolute(path)
    with parent(path) as (directory,name):
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=maximum
                and before.st_uid in (0,os.geteuid()) and not before.st_mode&0o022
                and (not executable or bool(before.st_mode&0o111)), 'A bounded single-link protected regular input is required')
            yield stream,before
            require(signature(os.fstat(stream.fileno()))==signature(before)
                and signature(os.stat(name,dir_fd=directory,follow_symlinks=False))==signature(before),'Qualification input changed while reading')

def check(path,*,expected,size=None,executable=False):
    with opened(path,executable=executable) as (stream,before):
        require(size is None or before.st_size==size,'Qualification input length differs from its fixed pin')
        value=hashlib.file_digest(stream,'sha256').hexdigest()
        require(value==expected,'Qualification input differs from its fixed pin')
    return absolute(path)

def reference(role,environ=None):
    require(role in PINNED,'Unknown qualification tool role')
    item=PINNED[role];environment=os.environ if environ is None else environ
    path=environment.get(item['environment'],item['default'])
    return check(path,expected=item['sha256'],size=item['bytes'],executable=True)

def records(environ=None):
    return {role:{**{k:item[k]for k in ('environment','version','bytes','sha256')},'path':str(reference(role,environ))}
        for role,item in PINNED.items()}
