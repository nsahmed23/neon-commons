#!/usr/bin/env python3
"""Restore an explicitly pinned complete continuation from ordered LOCAL parts.

No download, glob, overlay, archive execution or production authority is provided.
Every required layer must have final pins before any output is created. Failed
partials remain in the new private destination for independent investigation.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types
import zipfile

SCHEMA='intune-complete-continuation-layers/1'
RETURN_SCHEMA='intune-local-layer-parts/1'
BASE_COMMIT='289ee9477372825aad848f4482cf681c2ff43b02'
R2_COMMIT='74130d0db99febf2f41cf4f4ebe2920a5d4dffb7'
LAYER_IDS=('r2-complete','r3-source','r3-runtime','r3-evidence','r4-source','r4-runtime','r4-evidence','r4-external-evidence','r4-provider-candidate')
EVIDENCE_IDS={'r2-complete','r3-evidence','r4-evidence','r4-external-evidence','r4-provider-candidate'}
TOOLS=('restore-evidence-layer.py','verify-release-artifact.py')
HEX=re.compile(r'[0-9a-f]{64}\Z')
COMMIT=re.compile(r'[0-9a-f]{40}\Z')
CHUNK=1024*1024
MAX_JSON=4*CHUNK
MAX_TOTAL=128*1024**3


def require(value,message):
    if not value:raise ValueError(message)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def pin(value):return isinstance(value,str) and bool(HEX.fullmatch(value)) and value!='0'*64


def absolute(value):
    require(isinstance(value,(str,Path)),'Local path required')
    path=Path(value)
    require(path.is_absolute() and '..' not in path.parts,'Explicit absolute local path without traversal required')
    return path


def parent_fd(path):
    require(os.name=='posix' and hasattr(os,'O_NOFOLLOW') and hasattr(os,'O_DIRECTORY'),'POSIX no-follow host required')
    path=absolute(path);fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for name in path.parts[1:-1]:
            child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        return fd,path.name
    except BaseException:os.close(fd);raise


@contextlib.contextmanager
def local_stream(path):
    parent,name=parent_fd(path)
    try:fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    finally:os.close(parent)
    with os.fdopen(fd,'rb') as source:
        before=os.fstat(source.fileno());require(stat.S_ISREG(before.st_mode),'Input must be a regular file')
        yield source,before
        after=os.fstat(source.fileno())
        require(signature(before)==signature(after),'Input changed while being read; partial preserved')


def signature(info):return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def bounded(path,maximum=MAX_JSON):
    with local_stream(path) as (source,info):
        require(info.st_size<=maximum,'Input document exceeds bound')
        raw=source.read(maximum+1);require(len(raw)<=maximum,'Input document grew past bound')
        return raw


def loads(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:require(key not in result,'Duplicate JSON key');result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique)


def basename(value):
    require(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,200}',value)
            and value not in ('.','..'),'Asset/helper name must be a bounded basename')
    return value


def validate(manifest,returned,manifest_sha256):
    require(isinstance(manifest,dict) and manifest.get('schema_version')==SCHEMA,'Unsupported complete layer manifest')
    require(manifest.get('status')=='ready','Complete layer manifest is not finalized; unresolved pins BLOCK restoration')
    require(manifest.get('continuation_from')==BASE_COMMIT,'Wrong verified continuation baseline')
    require(manifest.get('historical_three_unexpected_files_closed') is False,'Historical discrepancy closure cannot be inferred')
    require(isinstance(manifest.get('tooling'),dict) and set(manifest['tooling'])==set(TOOLS)
            and all(pin(value) for value in manifest['tooling'].values()),'Exact reviewed helper pins required')
    layers=manifest.get('layers')
    require(isinstance(layers,list) and all(isinstance(layer,dict) for layer in layers)
            and tuple(layer.get('id') for layer in layers)==LAYER_IDS,'All required layers must appear exactly once in declared order')
    require(isinstance(returned,dict) and set(returned)=={'schema_version','manifest_sha256','layers'}
            and returned['schema_version']==RETURN_SCHEMA and returned['manifest_sha256']==manifest_sha256,
            'Returned local parts must bind this exact outer manifest')
    local_layers=returned['layers']
    require(isinstance(local_layers,list) and all(isinstance(layer,dict) for layer in local_layers)
            and tuple(layer.get('id') for layer in local_layers)==LAYER_IDS,
            'Returned part layers must match exact declared order; no discovery fallback')
    names,paths=set(),set();total=0;r4_commits=set()
    for layer,local in zip(layers,local_layers):
        identity=layer['id'];archive=layer['archive'];extract=layer['extract']
        require(isinstance(archive,dict) and isinstance(extract,dict),'Archive and extraction contracts must be objects')
        name=basename(archive['name']);require(name not in names,'Duplicate archive name');names.add(name)
        require(type(archive['bytes']) is int and 0<archive['bytes']<=32*1024**3 and pin(archive['sha256']),
                'Missing/invalid final archive pin: '+identity)
        total+=archive['bytes'];require(total<=MAX_TOTAL,'Complete layer size exceeds bound')
        require(extract.get('directory')==identity,'Each layer requires its own fixed new directory')
        kind='typed_evidence' if identity in EVIDENCE_IDS else 'application'
        require(extract.get('kind')==kind,'Wrong extraction contract for layer: '+identity)
        if kind=='typed_evidence':
            snapshot=extract['snapshot'];basename(snapshot['root']);basename(snapshot['manifest'])
            require(pin(snapshot['manifest_sha256']),'Missing exact inner manifest pin: '+identity)
            expected_schema=('complete-continuation-snapshot/2' if identity=='r2-complete' else
                             'intune-r3-evidence-supplement/1' if identity=='r3-evidence' else 'intune-r4-evidence-supplement/1')
            require(snapshot['schema']==expected_schema,'Wrong evidence schema')
        commit=layer.get('source_commit')
        if identity=='r4-provider-candidate':
            require(layer.get('qualification')=='preserved_unqualified_stopped_candidate','Stopped candidate must remain explicitly unqualified')
        else:
            require(isinstance(commit,str) and COMMIT.fullmatch(commit) and commit!='0'*40,'Exact source commit linkage required')
            if identity=='r2-complete':require(commit==R2_COMMIT,'R2 must retain its verified complete checkpoint identity')
            if identity.startswith('r3-'):require(commit==BASE_COMMIT,'R3 must retain the verified 0.8.0 identity')
            if identity.startswith('r4-'):r4_commits.add(commit)
        parts=archive.get('parts');local_parts=local.get('parts')
        require(set(local)=={'id','parts'} and isinstance(parts,list) and 1<=len(parts)<=1000
                and isinstance(local_parts,list) and len(local_parts)==len(parts),'Exact ordered returned part paths required')
        part_names=set();part_bytes=0
        for part,path in zip(parts,local_parts):
            part_name=basename(part['name']);require(part_name not in part_names,'Duplicate part name');part_names.add(part_name)
            require(type(part['bytes']) is int and 0<part['bytes']<=archive['bytes'] and pin(part['sha256']),'Missing/invalid part pin')
            part_bytes+=part['bytes'];literal=str(absolute(path));require(literal not in paths,'A returned path cannot stand in for multiple parts/layers');paths.add(literal)
        require(part_bytes==archive['bytes'],'Part sizes do not sum to declared archive size')
    require(len(r4_commits)==1,'R4 source/runtime/evidence must share one exact frozen source commit')


def load_helpers(manifest):
    result={}
    for name in TOOLS:
        path=Path(__file__).absolute().parent/name;raw=bounded(path,CHUNK)
        require(digest(raw)==manifest['tooling'][name],'Helper source differs from reviewed outer manifest: '+name)
        module=types.ModuleType(name);module.__file__=str(path)
        exec(compile(raw,str(path),'exec'),module.__dict__)
        result[name]=module
    return result['restore-evidence-layer.py'],result['verify-release-artifact.py']


def assemble(layer,local,archives,evidence):
    archive=layer['archive'];parent=evidence.open_dir(archives)
    partial=archive['name']+'.partial'
    def chunks():
        for part,path in zip(archive['parts'],local['parts']):
            with local_stream(path) as (source,info):
                require(info.st_size==part['bytes'],'Part size mismatch: '+part['name'])
                total=0;sha=hashlib.sha256()
                while data:=source.read(CHUNK):
                    total+=len(data);require(total<=part['bytes'],'Part grew beyond pin')
                    sha.update(data);yield data
                require((total,sha.hexdigest())==(part['bytes'],part['sha256']),'Part hash mismatch: '+part['name'])
    try:
        evidence.write_new(parent,partial,chunks(),archive)
        os.link(partial,archive['name'],src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False)
        os.unlink(partial,dir_fd=parent);os.fsync(parent)
    finally:os.close(parent)
    return archives/archive['name']


def extract_application(archive,layer,output,evidence,release):
    verified=release.verify(archive,layer['archive']['sha256'])
    parent=evidence.open_dir(output.parent)
    try:
        os.mkdir(output.name,mode=0o700,dir_fd=parent)
        rootfd=os.open(output.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.fsync(parent)
    finally:os.close(parent)
    try:
        physical={}
        with local_stream(archive) as (source,before):
            with zipfile.ZipFile(source) as bundle:
                root=verified['root'];raw=bundle.read(root+'/SHA256SUMS')
                listed={name:checksum for checksum,name in (line.split('  ',1) for line in raw.decode().splitlines())}
                for info in bundle.infolist():
                    expected={'type':'file','bytes':info.file_size,'sha256':digest(raw) if info.filename==root+'/SHA256SUMS' else listed[info.filename[len(root)+1:]]}
                    with bundle.open(info) as stream:evidence.write_new(rootfd,info.filename,evidence.file_chunks(stream),expected)
                    physical[info.filename]=expected
                    components=info.filename.split('/')[:-1]
                    for depth in range(1,len(components)+1):physical['/'.join(components[:depth])]={'type':'directory'}
        evidence.verify_output(rootfd,physical)
        result=dict(verified,extracted_to=str(output),physical_file_set_and_types_verified=True,regular_bytes_read_back=True,
                    content_executed=False,historical_three_unexpected_files_closed=False)
        evidence.write_new(rootfd,'EXTRACTION-RECEIPT.json',[json.dumps(result,indent=2).encode()+b'\n'])
        return result
    finally:os.close(rootfd)



def verify_complete_output(rootfd, physical, evidence):
    """Compose unchanged bounded per-layer readbacks with exact outer closure.

    The full continuation exceeds one archive's entry budget. Each independently
    pinned layer retains that budget; no payload, unknown outer path or extra
    layer is skipped to fit. Held directory identities bind every readback.
    """
    require(len(physical)<=len(LAYER_IDS)*(evidence.MAX_ENTRIES+4)+16,
            'Combined continuation physical map exceeds declared layer budget')
    def shallow(directory, expected):
        require(set(os.listdir(directory))==set(expected),'Complete outer namespace differs')
        signatures={}
        for name,item in expected.items():
            info=os.stat(name,dir_fd=directory,follow_symlinks=False)
            kind='directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else 'unsupported'
            require(kind==item['type'],'Complete outer type differs: '+name)
            signatures[name]=signature(info)+(info.st_mode,info.st_nlink)
            if kind=='file':
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
                with os.fdopen(fd,'rb') as source:
                    held=os.fstat(source.fileno())
                    require(signature(held)+(held.st_mode,held.st_nlink)==signatures[name]
                            and held.st_nlink==1 and held.st_size==item['bytes'],'Complete outer file identity differs')
                    count=0;sha=hashlib.sha256()
                    for raw in evidence.file_chunks(source):
                        count+=len(raw);require(count<=item['bytes'],'Complete outer file grew');sha.update(raw)
                    require((count,sha.hexdigest())==(item['bytes'],item['sha256']),'Complete outer file bytes differ')
                    require(signature(os.fstat(source.fileno()))+(held.st_mode,held.st_nlink)==signatures[name],
                            'Complete outer file changed during readback')
        require(set(os.listdir(directory))==set(expected),'Complete outer namespace changed')
        for name,prior in signatures.items():
            current=os.stat(name,dir_fd=directory,follow_symlinks=False)
            require(signature(current)+(current.st_mode,current.st_nlink)==prior,'Complete outer entry changed')
        return signatures
    root_expected={name:item for name,item in physical.items() if '/' not in name}
    require(set(root_expected)=={'archives','layers','PINNED-LAYER-MANIFEST.json','EXACT-RETURNED-PART-PATHS.json'},
            'Invalid complete root inventory')
    initial=shallow(rootfd,root_expected)
    handles=[]
    primary=None
    try:
        for name in ('archives','layers'):
            fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=rootfd);handles.append(fd)
            held=os.fstat(fd)
            require(signature(held)+(held.st_mode,held.st_nlink)==initial[name],'Complete directory replaced')
        archives,layers=handles
        archive_expected={name[len('archives/'):]:item for name,item in physical.items() if name.startswith('archives/')}
        require(all('/' not in name for name in archive_expected),'Unexpected archive nesting')
        evidence.verify_output(archives,archive_expected)
        layer_expected={name:{'type':'directory'} for name in LAYER_IDS}
        layer_initial=shallow(layers,layer_expected)
        for identity in LAYER_IDS:
            fd=os.open(identity,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=layers)
            layer_primary=None
            try:
                held=os.fstat(fd)
                require(signature(held)+(held.st_mode,held.st_nlink)==layer_initial[identity],'Complete layer replaced')
                prefix='layers/'+identity+'/'
                expected={name[len(prefix):]:item for name,item in physical.items() if name.startswith(prefix)}
                require(expected and len(expected)<=evidence.MAX_ENTRIES+2,'Layer physical map exceeds unchanged bound')
                evidence.verify_output(fd,expected)
                current=os.stat(identity,dir_fd=layers,follow_symlinks=False)
                require(signature(current)+(current.st_mode,current.st_nlink)==layer_initial[identity],
                        'Complete layer changed during final readback')
            except BaseException as error:layer_primary=error;raise
            finally:
                try:os.close(fd)
                except BaseException:
                    if layer_primary is None:raise
                    if hasattr(layer_primary,'add_note'):layer_primary.add_note('Layer descriptor cleanup also failed; original cause preserved.')
        require(shallow(layers,layer_expected)==layer_initial,'Complete layer namespace changed')
        require(shallow(rootfd,root_expected)==initial,'Complete root changed during final readback')
    except BaseException as error:primary=error;raise
    finally:
        failures=[]
        for fd in reversed(handles):
            try:os.close(fd)
            except BaseException as error:failures.append(error)
        if failures:
            if primary is None:raise failures[0]
            if hasattr(primary,'add_note'):primary.add_note('Complete output directory cleanup also failed; PASS withheld.')


def restore(manifest_path,manifest_sha256,parts_path,output):
    require(pin(manifest_sha256),'Independent outer manifest SHA-256 pin required')
    raw=bounded(manifest_path);require(digest(raw)==manifest_sha256,'Outer manifest SHA-256 mismatch')
    manifest=loads(raw);returned=loads(bounded(parts_path));validate(manifest,returned,manifest_sha256)
    evidence,release=load_helpers(manifest);output=absolute(output)
    parent,name=parent_fd(output)
    try:os.mkdir(name,mode=0o700,dir_fd=parent);os.fsync(parent)
    finally:os.close(parent)
    root=evidence.open_dir(output)
    try:
        for directory in ('archives','layers'):os.mkdir(directory,mode=0o700,dir_fd=root)
        returned_raw=json.dumps(returned,indent=2).encode()+b'\n'
        evidence.write_new(root,'PINNED-LAYER-MANIFEST.json',[raw])
        evidence.write_new(root,'EXACT-RETURNED-PART-PATHS.json',[returned_raw])
        physical={'archives':{'type':'directory'},'layers':{'type':'directory'},
                  'PINNED-LAYER-MANIFEST.json':{'type':'file','bytes':len(raw),'sha256':digest(raw)},
                  'EXACT-RETURNED-PART-PATHS.json':{'type':'file','bytes':len(returned_raw),'sha256':digest(returned_raw)}}
        assembled=[]
        # Verify every ordered part and final archive before extracting any layer.
        for layer,local in zip(manifest['layers'],returned['layers']):
            assembled.append(assemble(layer,local,output/'archives',evidence))
        results=[]
        for layer,archive in zip(manifest['layers'],assembled):
            destination=output/'layers'/layer['id']
            physical['archives/'+layer['archive']['name']]=dict(layer['archive'],type='file')
            prefix='layers/'+layer['id']+'/'
            physical[prefix[:-1]]={'type':'directory'}
            if layer['extract']['kind']=='typed_evidence':
                result=evidence.extract(archive,archive_bytes=layer['archive']['bytes'],archive_sha256=layer['archive']['sha256'],
                                        snapshot=layer['extract']['snapshot'],output=destination)
                with local_stream(archive) as (source,info):
                    with zipfile.ZipFile(source) as bundle:
                        document,inventory,mapping,inner_raw=evidence.inspect_archive(bundle,layer['extract']['snapshot'])
                inner_root=layer['extract']['snapshot']['root'];physical[prefix+inner_root]={'type':'directory'}
                for name,entry in inventory.items():physical[prefix+inner_root+'/'+name]=entry
                physical[prefix+inner_root+'/'+layer['extract']['snapshot']['manifest']]={
                    'type':'file','bytes':len(inner_raw),'sha256':digest(inner_raw)}
            else:
                result=extract_application(archive,layer,destination,evidence,release)
                with local_stream(archive) as (source,info):
                    with zipfile.ZipFile(source) as bundle:
                        inner_root=result['root'];inner_raw=bundle.read(inner_root+'/SHA256SUMS')
                        listed={name:checksum for checksum,name in (line.split('  ',1) for line in inner_raw.decode().splitlines())}
                        for item in bundle.infolist():
                            physical[prefix+item.filename]={'type':'file','bytes':item.file_size,
                                'sha256':digest(inner_raw) if item.filename==inner_root+'/SHA256SUMS' else listed[item.filename[len(inner_root)+1:]]}
                            pieces=item.filename.split('/')[:-1]
                            for depth in range(1,len(pieces)+1):physical[prefix+'/'.join(pieces[:depth])]={'type':'directory'}
            receipt_raw=json.dumps(result,indent=2).encode()+b'\n'
            physical[prefix+'EXTRACTION-RECEIPT.json']={'type':'file','bytes':len(receipt_raw),'sha256':digest(receipt_raw)}
            results.append({'id':layer['id'],'archive':str(archive),'extraction':str(destination),'receipt':result,
                            'source_commit':layer.get('source_commit'),'qualification':layer.get('qualification')})
        receipt={'schema_version':'intune-complete-layer-restoration/1','status':'PASS','manifest_sha256':manifest_sha256,
                 'layers':results,'required_layers_present':list(LAYER_IDS),'downloaded':False,'overlay_performed':False,
                 'ordered_returned_paths_only':True,'all_archives_verified_before_first_extraction':True,
                 'complete_physical_file_set_and_type_map_verified':True,
                 'final_readback_scope':'exact outer namespaces plus each unchanged bounded layer and archives',
                 'per_layer_entry_limit':evidence.MAX_ENTRIES,
                 'candidate_executed':False,'content_executed':False,'historical_three_unexpected_files_closed':False,
                 'platform_qualified':False,'production_approved':False}
        verify_complete_output(root,physical,evidence)
        evidence.write_new(root,'COMPLETE-LAYER-RECEIPT.json',[json.dumps(receipt,indent=2).encode()+b'\n']);os.fsync(root)
        return receipt
    finally:os.close(root)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True);parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--returned-parts',required=True,help='JSON containing exactly the ordered local paths returned by prior transfer')
    parser.add_argument('--output',required=True,help='New private root; every layer restored into its own new directory')
    args=parser.parse_args(argv)
    try:
        result=restore(args.manifest,args.manifest_sha256,args.returned_parts,args.output)
        print(json.dumps(result,indent=2));return 0
    except (OSError,ValueError,KeyError,TypeError,RuntimeError,zipfile.BadZipFile) as error:
        print(json.dumps({'status':'FAIL','error':str(error),'archives_and_partials_preserved':True},ensure_ascii=True),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
