#!/usr/bin/env python3
"""Verify a bounded release ZIP and optionally extract into a new directory.

SHA256SUMS proves consistency, not publisher identity. Supply --sha256 from an
independently trusted receipt when checking archive identity. No archive code is
executed. Extraction assumes the caller controls the destination parent.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import unicodedata
import zipfile


def verify(archive, expected=None, destination=None):
    archive=Path(archive)
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size>256*1024**2:
        raise ValueError('Archive must be a bounded regular file.')
    raw=archive.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if expected is not None and sha!=expected:raise ValueError('Archive hash mismatch.')
    content={};seen=set();total=0
    reserved={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
    with zipfile.ZipFile(archive) as bundle:
        members=bundle.infolist()
        if not 1<=len(members)<=20000:raise ValueError('Invalid member count.')
        for item in members:
            name=item.filename;parts=name.split('/');mode=(item.external_attr>>16)&0xffff
            if (not name or '\\' in name or ':' in name or len(name)>2048 or len(parts)>32
                or any(part in {'','.','..'} or part.rstrip(' .')!=part or any(ord(c)<32 or ord(c)==127 for c in part)
                       or part.split('.')[0].upper() in reserved for part in parts)
                or PurePosixPath(name).is_absolute() or not stat.S_ISREG(mode)
                or item.flag_bits&1):raise ValueError('Unsafe or unsupported member.')
            folded=unicodedata.normalize('NFC',name).casefold()
            if folded in seen:raise ValueError('Duplicate/colliding archive name.')
            seen.add(folded);total+=item.file_size
            if item.file_size>32*1024**2 or total>512*1024**2:raise ValueError('Expanded archive exceeds bounds.')
            with bundle.open(item) as stream:data=stream.read(32*1024**2+1)
            if len(data)!=item.file_size:raise ValueError('Member size mismatch.')
            content[name]=data
    roots={name.split('/')[0] for name in content}
    if len(roots)!=1:raise ValueError('Expected one archive root.')
    root=next(iter(roots));manifest=content.get(root+'/SHA256SUMS')
    if manifest is None:raise ValueError('Missing integrity manifest.')
    listed={}
    for line in manifest.decode('utf-8').splitlines():
        if not re.fullmatch(r'[0-9a-f]{64}  .+',line):raise ValueError('Malformed integrity manifest.')
        value,name=line.split('  ',1)
        if name in listed:raise ValueError('Duplicate manifest member.')
        listed[name]=value
    actual={name[len(root)+1:]:hashlib.sha256(data).hexdigest() for name,data in content.items() if name!=root+'/SHA256SUMS'}
    if listed!=actual:raise ValueError('Manifest does not cover exact archive contents.')
    if destination is not None:
        destination=Path(destination).absolute()
        if destination.exists() or any(p.is_symlink() for p in (destination,*destination.parents)):
            raise ValueError('Extraction requires a fresh path with no symlink ancestors.')
        destination.mkdir(mode=0o700)
        for name,data in content.items():
            target=destination/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(descriptor,'wb') as stream:stream.write(data)
    return {'status':'PASS','archive':archive.name,'sha256':sha,'members':len(content),
            'manifest_entries':len(listed),'expanded_bytes':total,'root':root,
            'extracted_to':str(destination) if destination is not None else None,
            'publisher_authenticated':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True);parser.add_argument('--sha256');parser.add_argument('--extract')
    args=parser.parse_args()
    try:result=verify(args.archive,args.sha256,args.extract)
    except (OSError,ValueError,UnicodeError,zipfile.BadZipFile):
        print(json.dumps({'status':'FAIL','reason':'Archive integrity, bounds or safe path checks failed.'}));return 1
    print(json.dumps(result,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
