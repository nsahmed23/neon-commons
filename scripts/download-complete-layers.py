#!/usr/bin/env python3
"""Fetch exactly pinned, ordered public continuation parts without extraction.

The optional pinned local fixture map is an explicitly labelled laboratory
transport. It cannot produce an anonymous-public-readback receipt. Archives,
partials and unexpected files are preserved on failure; no glob is consulted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types
import urllib.parse
import urllib.request

CHUNK=1024*1024
MAX_DOCUMENT=4*CHUNK
ORIGIN='https://raw.githubusercontent.com/nsahmed23/neon-commons/'


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def load_validator(expected):
    path=Path(__file__).absolute().with_name('restore-complete-layers.py')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        info=os.fstat(source.fileno());require(stat.S_ISREG(info.st_mode) and info.st_size<=CHUNK,'Validator must be a bounded regular file')
        raw=source.read(CHUNK+1)
    require(re.fullmatch('[0-9a-f]{64}',expected or '') and sha(raw)==expected,'Validator differs from independent pin')
    module=types.ModuleType('qualified_complete_layer_validator');module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def public_url(value):
    require(isinstance(value,str) and value.startswith(ORIGIN),'Only the declared public repository raw origin is supported')
    parsed=urllib.parse.urlsplit(value);tail=value[len(ORIGIN):]
    require(not parsed.query and not parsed.fragment and not parsed.username and not parsed.password
        and re.fullmatch(r'[0-9a-f]{40}/intune-workbench/[A-Za-z0-9._/-]+',tail),'Immutable commit URL without credentials/query required')
    require(all(part not in ('','.','..') for part in tail.split('/')),'Unsafe public URL path')
    return value


def new_directory(validator,path):
    path=validator.absolute(path);parent,name=validator.parent_fd(path)
    try:
        os.mkdir(name,0o700,dir_fd=parent)
        fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
        os.fchmod(fd,0o700);os.fsync(parent)
        return fd
    finally:os.close(parent)


def same_name(fd,name,opened):
    observed=os.stat(name,dir_fd=fd,follow_symlinks=False)
    require(stat.S_ISREG(observed.st_mode) and (observed.st_dev,observed.st_ino)==(opened.st_dev,opened.st_ino),'Output pathname changed; preserve all artifacts')


def write_verified(fd,name,chunks,expected):
    """Publish only a held, independently read-back regular file, never replace."""
    partial=name+'.partial';handle=os.open(partial,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
    try:
        total=0;digest=hashlib.sha256()
        for raw in chunks:
            total+=len(raw);require(total<=expected['bytes'],'Download exceeds pinned byte length')
            digest.update(raw);offset=0
            while offset<len(raw):offset+=os.write(handle,raw[offset:])
        require((total,digest.hexdigest())==(expected['bytes'],expected['sha256']),'Downloaded bytes differ from exact pin')
        os.fsync(handle);opened=os.fstat(handle);os.lseek(handle,0,os.SEEK_SET);verified=hashlib.sha256()
        while raw:=os.read(handle,CHUNK):verified.update(raw)
        require(verified.hexdigest()==expected['sha256'],'Written bytes failed independent readback')
        same_name(fd,partial,opened)
        os.link(partial,name,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
        final=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            require((os.fstat(final).st_dev,os.fstat(final).st_ino)==(opened.st_dev,opened.st_ino),'Published pathname changed; preserve both names')
            digest=hashlib.sha256()
            while raw:=os.read(final,CHUNK):digest.update(raw)
            require(digest.hexdigest()==expected['sha256'],'Published bytes differ; preserve all names')
        finally:os.close(final)
        same_name(fd,partial,opened);same_name(fd,name,opened)
        os.unlink(partial,dir_fd=fd);os.fsync(fd)
    finally:os.close(handle)


def document(fd,name,value):
    raw=(json.dumps(value,sort_keys=True,ensure_ascii=True,indent=2)+'\n').encode()
    write_verified(fd,name,[raw],{'bytes':len(raw),'sha256':sha(raw)})


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Public part redirect refused; retain partial output')


def download(manifest_path,manifest_sha256,validator_sha256,output,*,fixture_map=None,fixture_sha256=None):
    v=load_validator(validator_sha256);raw=v.bounded(manifest_path,MAX_DOCUMENT)
    require(v.pin(manifest_sha256) and sha(raw)==manifest_sha256,'Outer manifest differs from independent pin')
    manifest=v.loads(raw);require(isinstance(manifest,dict),'Outer manifest must be an object');output=v.absolute(output)
    layers=manifest.get('layers',[])
    require(isinstance(layers,list) and all(isinstance(layer,dict)for layer in layers),'Ordered layer objects required')
    returned={'schema_version':v.RETURN_SCHEMA,'manifest_sha256':manifest_sha256,'layers':[
        {'id':layer['id'],'parts':[str(output/'parts'/layer['id']/part['name']) for part in layer['archive']['parts']]} for layer in layers]}
    v.validate(manifest,returned,manifest_sha256)
    urls=[public_url(part.get('url')) for layer in layers for part in layer['archive']['parts']]
    require(len(urls)==len(set(urls)),'A public URL cannot stand in for more than one ordered part')
    local=None
    if fixture_map is not None:
        data=v.bounded(fixture_map,MAX_DOCUMENT);require(v.pin(fixture_sha256) and sha(data)==fixture_sha256,'Local transport map differs from independent pin')
        local=v.loads(data);require(isinstance(local,dict) and set(local)==set(urls),'Fixture map must declare exactly the manifest URLs')
        for value in local.values():v.absolute(value)
    else:require(fixture_sha256 is None,'Fixture pin without fixture map refused')
    rootfd=new_directory(v,output);expected_root={'OUTER-MANIFEST.json','parts','RETURNED-PARTS.json','DOWNLOAD-RECEIPT.json'}
    opener=urllib.request.build_opener(NoRedirect()) if local is None else None
    receipt={'schema_version':'intune-complete-layer-download/1','status':'RUNNING','manifest_sha256':manifest_sha256,
        'validator_sha256':validator_sha256,'transport':'anonymous_public_https' if local is None else 'pinned_local_fixture_no_network',
        'authentication_supplied':False,'authentication_scope':'origin request headers only; proxy authentication not inspected',
        'origin_authentication_supplied':False,'existing_proxy_configuration_inherited':local is None,
        'proxy_credential_values_inspected':False,'network_attempted':False,'archives':[],
        'extraction_performed':False,'production_approved':False,'historical_three_unexpected_files_closed':False}
    try:
        write_verified(rootfd,'OUTER-MANIFEST.json',[raw],{'bytes':len(raw),'sha256':manifest_sha256})
        os.mkdir('parts',0o700,dir_fd=rootfd);partsfd=os.open('parts',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=rootfd)
        try:
            for layer in layers:
                identity=layer['id'];os.mkdir(identity,0o700,dir_fd=partsfd);layerfd=os.open(identity,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=partsfd)
                whole=hashlib.sha256();count=0;part_records=[]
                try:
                    for part in layer['archive']['parts']:
                        url=part['url'];record={'name':part['name'],'bytes':part['bytes'],'sha256':part['sha256'],'url':url}
                        def chunks():
                            nonlocal count
                            if local is not None:
                                with v.local_stream(local[url]) as (stream,before):
                                    require(before.st_size==part['bytes'],'Local fixture length differs from exact pin')
                                    while block:=stream.read(CHUNK):whole.update(block);count+=len(block);yield block
                            else:
                                receipt['network_attempted']=True
                                request=urllib.request.Request(url,headers={'User-Agent':'Intune-Complete-Layers/1','Accept-Encoding':'identity'})
                                with opener.open(request,timeout=45) as response:
                                    require(response.status==200 and response.geturl()==url,'Public response status or URL changed')
                                    require(response.headers.get('Content-Encoding','identity')=='identity','Encoded public response refused')
                                    length=response.headers.get('Content-Length')
                                    if length is not None:require(length==str(part['bytes']),'HTTP byte length differs from pin')
                                    while block:=response.read(CHUNK):whole.update(block);count+=len(block);yield block
                        write_verified(layerfd,part['name'],chunks(),part);part_records.append(record)
                    require((count,whole.hexdigest())==(layer['archive']['bytes'],layer['archive']['sha256']),'Concatenated ordered archive bytes differ from exact pin')
                    require(set(os.listdir(layerfd))=={part['name']for part in layer['archive']['parts']},'Unexpected layer file retained; closure refused')
                    receipt['archives'].append({'id':identity,'bytes':count,'sha256':whole.hexdigest(),'parts':part_records})
                finally:os.close(layerfd)
            require(set(os.listdir(partsfd))==set(v.LAYER_IDS),'Unexpected parts directory retained; closure refused')
        finally:os.close(partsfd)
        # A previously written part may have changed while a later part was
        # fetched. Reopen every exact returned pathname without following any
        # ancestor, and independently rehash the final ordered physical files.
        for layer,paths in zip(layers,returned['layers']):
            whole=hashlib.sha256();total=0
            for part,path in zip(layer['archive']['parts'],paths['parts']):
                digest=hashlib.sha256();count=0
                with v.local_stream(path) as (stream,before):
                    require(before.st_size==part['bytes'],'Final part size changed')
                    while block:=stream.read(CHUNK):digest.update(block);whole.update(block);count+=len(block);total+=len(block)
                require((count,digest.hexdigest())==(part['bytes'],part['sha256']),'Final part bytes changed; preserve them')
            require((total,whole.hexdigest())==(layer['archive']['bytes'],layer['archive']['sha256']),'Final archive byte stream changed')
        # Repeat the typed name census after all transfers. An extra file in
        # the first layer must not be hidden by its earlier successful check.
        partsfd=os.open('parts',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=rootfd)
        try:
            require(set(os.listdir(partsfd))==set(v.LAYER_IDS),'Unexpected final layer directory retained')
            for layer in layers:
                layerfd=os.open(layer['id'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=partsfd)
                try:require(set(os.listdir(layerfd))=={p['name']for p in layer['archive']['parts']},'Unexpected final layer file retained; closure refused')
                finally:os.close(layerfd)
        finally:os.close(partsfd)
        document(rootfd,'RETURNED-PARTS.json',returned)
        require(set(os.listdir(rootfd))==expected_root-{'DOWNLOAD-RECEIPT.json'},'Unexpected top-level output retained; closure refused')
        parent,name=v.parent_fd(output)
        try:
            observed=os.stat(name,dir_fd=parent,follow_symlinks=False);held=os.fstat(rootfd)
            require(stat.S_ISDIR(observed.st_mode) and (observed.st_dev,observed.st_ino)==(held.st_dev,held.st_ino),'Output directory identity changed')
        finally:os.close(parent)
        receipt['status']='PASS_ANONYMOUS_PUBLIC_READBACK'if local is None else'PASS_LOCAL_FIXTURE_ONLY'
        receipt['returned_parts']=str(output/'RETURNED-PARTS.json');receipt['complete_ordered_byte_streams_verified']=True
        receipt['final_part_readback_verified']=True
        document(rootfd,'DOWNLOAD-RECEIPT.json',receipt)
        return receipt
    except BaseException as error:
        receipt.update(status='FAIL',error_type=type(error).__name__,error=str(error))
        try:document(rootfd,'DOWNLOAD-FAILURE.json',receipt)
        except BaseException as secondary:print(json.dumps({'secondary_receipt_failure':type(secondary).__name__},ensure_ascii=True),file=sys.stderr)
        raise
    finally:os.close(rootfd)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','manifest-sha256','validator-sha256','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--local-fixture-map');parser.add_argument('--local-fixture-sha256');args=parser.parse_args(argv)
    try:
        result=download(args.manifest,args.manifest_sha256,args.validator_sha256,args.output,
            fixture_map=args.local_fixture_map,fixture_sha256=args.local_fixture_sha256)
        print(json.dumps(result,ensure_ascii=True));return 0
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({'status':'FAIL','error_type':type(error).__name__,'error':str(error)},ensure_ascii=True),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
