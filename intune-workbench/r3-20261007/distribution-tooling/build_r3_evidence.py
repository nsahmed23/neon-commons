#!/usr/bin/env python3
"""Archive a frozen entire R3 evidence epoch, including literal symlink entries.

This produces an explicit evidence supplement, not a replacement repository.
No link is followed; all entries are verified before a new ZIP is published.
Output and receipts must be outside the input epoch. Failed partials are kept.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import zipfile

SCHEMA='intune-r3-evidence-supplement/1'
MANIFEST='R3-EVIDENCE-MANIFEST.json'
ARCHIVE_ROOT='Intune_R3_Evidence_20261007'
CHUNK=1024*1024


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def safe(path):
    require(path and not path.startswith('/') and '\\' not in path and '\x00' not in path,'Unsafe archive name')
    require(all(p not in ('','.','..') for p in path.split('/')),'Unsafe archive path components')
    return path


def signature(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_nlink)


def scan(root):
    require(root.is_dir() and not root.is_symlink(),'Evidence root must be a real directory')
    entries={}
    for here,dirs,files in os.walk(root,followlinks=False):
        for name in sorted(dirs+files):
            path=Path(here)/name;relative=safe(path.relative_to(root).as_posix());info=path.lstat()
            require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode),
                    'Unsupported special entry preserved at source: '+relative)
            entries[relative]=signature(info)
    return dict(sorted(entries.items()))


@contextmanager
def parent_fd(path):
    path=Path(path).absolute();fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for name in path.parts[1:-1]:
            child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        yield fd,path.name
    finally:os.close(fd)


def info_for(name,mode):
    item=zipfile.ZipInfo(name,date_time=(2026,10,7,0,0,0))
    item.create_system=3;item.external_attr=mode<<16
    if stat.S_ISDIR(mode):item.external_attr|=0x10
    item.compress_type=zipfile.ZIP_STORED if name.lower().endswith(('.zip','.whl','.gz','.xz','.png','.jpg','.zst','.7z')) else zipfile.ZIP_DEFLATED
    return item


def file_hash(path):
    h=hashlib.sha256()
    with open(path,'rb') as stream:
        while data:=stream.read(CHUNK):h.update(data)
    return h.hexdigest()


def verify(archive_path,manifest):
    inventory={ARCHIVE_ROOT+'/'+item['path']+('/' if item['type']=='directory' else ''):item for item in manifest['entries']}
    manifest_name=ARCHIVE_ROOT+'/'+MANIFEST
    with zipfile.ZipFile(archive_path) as archive:
        infos=archive.infolist();names=[item.filename for item in infos]
        require(len(names)==len(set(names)),'Duplicate ZIP entries')
        require(set(names)==set(inventory)|{manifest_name},'ZIP/manifest file-set mismatch')
        expected_manifest=json.dumps(manifest,indent=2,sort_keys=True).encode()+b'\n'
        require(archive.read(manifest_name)==expected_manifest,'Manifest bytes changed')
        for info in infos:
            if info.filename==manifest_name:continue
            expected=inventory[info.filename];h=hashlib.sha256();count=0
            with archive.open(info) as stream:
                while data:=stream.read(CHUNK):count+=len(data);h.update(data)
            require((count,h.hexdigest())==(expected['bytes'],expected['sha256']),'Payload integrity mismatch: '+info.filename)
            mode=info.external_attr>>16
            kind='symlink' if stat.S_ISLNK(mode) else 'directory' if stat.S_ISDIR(mode) else 'file' if stat.S_ISREG(mode) else 'special'
            require(kind==expected['type'],'ZIP type mismatch: '+info.filename)
    return {'verified_entries':len(inventory),'all_zip_crc_verified':True,'all_payload_sha256_verified':True,'exact_member_set_verified':True}


def build(epoch,output,provenance):
    epoch=Path(epoch).absolute();output=Path(output).absolute();started=time.time()
    require(output!=epoch and epoch not in output.parents,'Output must be outside epoch')
    partial=output.with_name(output.name+'.partial');receipt_path=output.with_name(output.name+'.receipt.json')
    with parent_fd(output):pass  # Reject symlinked output ancestors before any write.
    require(not os.path.lexists(output) and not os.path.lexists(partial) and not os.path.lexists(receipt_path),'Destination already exists')
    before=scan(epoch);entries=[];hardlinks={};links=[]
    prefix='work/evidence/'+epoch.name
    # Explicit structural parents make the inventory complete and portable.
    for name in ('work','work/evidence',prefix):
        entries.append({'path':name,'type':'directory','mode':0o700,'bytes':0,'sha256':sha(b''),'structural_parent':True})
    receipt={'status':'RUNNING','input_epoch':str(epoch),'archive':str(output),'started_unix':started}
    try:
        with parent_fd(partial) as (parent,name):
            fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        with os.fdopen(fd,'w+b') as destination,zipfile.ZipFile(destination,'w',allowZip64=True,compression=zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
            for item in entries:archive.writestr(info_for(ARCHIVE_ROOT+'/'+item['path']+'/',stat.S_IFDIR|item['mode']),b'')
            for index,(relative,expected_signature) in enumerate(before.items(),1):
                path=epoch/relative;mode=expected_signature[2];name=prefix+'/'+relative
                item={'path':name,'mode':stat.S_IMODE(mode),'mtime_ns':expected_signature[4]}
                with parent_fd(path) as (parent,base):
                    require(signature(os.stat(base,dir_fd=parent,follow_symlinks=False))==expected_signature,'Source entry changed before archive: '+relative)
                    if stat.S_ISDIR(mode):
                        item.update(type='directory',bytes=0,sha256=sha(b''));archive.writestr(info_for(ARCHIVE_ROOT+'/'+name+'/',mode),b'')
                    elif stat.S_ISLNK(mode):
                        target=os.readlink(base,dir_fd=parent);raw=os.fsencode(target)
                        archive.writestr(info_for(ARCHIVE_ROOT+'/'+name,mode),raw)
                        item.update(type='symlink',bytes=len(raw),sha256=sha(raw),link_target=target,link_not_dereferenced=True)
                        links.append({'path':name,'target':target})
                    else:
                        fd=os.open(base,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
                        h=hashlib.sha256();count=0
                        with os.fdopen(fd,'rb') as source:
                            require(signature(os.fstat(source.fileno()))==expected_signature,'Source identity changed at open: '+relative)
                            with archive.open(info_for(ARCHIVE_ROOT+'/'+name,mode),'w',force_zip64=True) as member:
                                while data:=source.read(CHUNK):count+=len(data);h.update(data);member.write(data)
                            require(signature(os.fstat(source.fileno()))==expected_signature,'Source bytes changed during archive: '+relative)
                        require(count==expected_signature[3],'Source size changed: '+relative)
                        item.update(type='file',bytes=count,sha256=h.hexdigest())
                        if expected_signature[6]>1:hardlinks.setdefault(expected_signature[:2],[]).append(name)
                    require(signature(os.stat(base,dir_fd=parent,follow_symlinks=False))==expected_signature,'Source entry changed after archive: '+relative)
                entries.append(item)
                if index%5000==0:print('Archived %d/%d entries'%(index,len(before)),flush=True)
            manifest={'schema':SCHEMA,'complete_repository':False,'complete_evidence_epoch':True,
                'epoch':epoch.name,'provenance':provenance,'entries':entries,'link_inventory':links,
                'hardlink_groups':[{'group':'hardlink-%d'%(i+1),'paths':paths} for i,paths in enumerate(hardlinks.values()) if len(paths)>1],
                'manifest_excluded_from_own_inventory':True,
                'extraction_policy':'Do not use blanket extractall/unzip. Preserve the ZIP unchanged; validate all paths, types and exact manifest entries; quarantine symlink payloads as inert literal targets outside executable source. The distributed helper only downloads/reassembles and performs no extraction.',
                'historical_R2_three_file_discrepancy_closed':False}
            raw_manifest=json.dumps(manifest,indent=2,sort_keys=True).encode()+b'\n'
            archive.writestr(info_for(ARCHIVE_ROOT+'/'+MANIFEST,stat.S_IFREG|0o600),raw_manifest)
        verification=verify(partial,manifest)
        require(scan(epoch)==before,'Source epoch file set or metadata changed; failed partial preserved')
        checksum=file_hash(partial);size=partial.stat().st_size
        with parent_fd(output) as (parent,name):
            os.link(partial.name,name,src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False)
            os.unlink(partial.name,dir_fd=parent);os.fsync(parent)
        receipt.update(status='PASS',bytes=size,sha256=checksum,manifest_sha256=sha(raw_manifest),
            regular_files=sum(x['type']=='file' for x in entries),regular_bytes=sum(x['bytes'] for x in entries if x['type']=='file'),
            directories=sum(x['type']=='directory' for x in entries),symlinks=links,
            hardlink_groups=manifest['hardlink_groups'],input_epoch_unchanged=True,complete_repository=False,
            complete_evidence_epoch=True,provenance=provenance,**verification)
    except BaseException as error:
        receipt.update(status='FAIL',error_type=type(error).__name__,error=str(error),partial_preserved=str(partial));raise
    finally:
        receipt.update(finished_unix=time.time(),seconds=time.time()-started)
        with parent_fd(receipt_path) as (parent,name):
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        with os.fdopen(fd,'w') as out:json.dump(receipt,out,indent=2);out.write('\n')
    return receipt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--epoch',required=True);parser.add_argument('--output',required=True);parser.add_argument('--provenance',required=True)
    args=parser.parse_args(argv);provenance=json.loads(Path(args.provenance).read_text())
    print(json.dumps(build(args.epoch,args.output,provenance),indent=2))

if __name__=='__main__':main()
