#!/usr/bin/env python3
"""Copy explicit frozen evidence roots into a NEW private single-epoch snapshot.

No payload execution, link traversal, source deletion, automatic exclusion,
publication clearance or claim that these selected roots are the full corpus.
"""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time

HERE=Path(__file__).absolute().parent

def _module(name,filename):
    spec=importlib.util.spec_from_file_location(name,HERE/filename)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
B=_module('snapshot_existing_producer','build-evidence-layer.py')
R=_module('snapshot_existing_restorer','restore-evidence-layer.py')
META='_snapshot'
SCHEMA='intune-evidence-root-map/1'
require=B.require


@contextmanager
def _handles():
    handles=[];primary=None
    try:yield handles
    except BaseException as error:primary=error;raise
    finally:
        failures=[]
        for fd in reversed(handles):
            try:os.close(fd)
            except BaseException as error:failures.append(error)
        if failures:
            if primary is None:raise failures[0]
            primary.snapshot_cleanup_failures=[type(error).__name__ for error in failures]
            if hasattr(primary,'add_note'):primary.add_note('Evidence snapshot descriptor cleanup also failed; retained output is not accepted.')


def _document(document,output):
    require(type(document) is dict and set(document)=={'schema_version','roots'} and document['schema_version']==SCHEMA,'Invalid explicit roots document')
    require(type(document['roots']) is list and 1<=len(document['roots'])<=512,'Invalid root count')
    roots=[];prefixes=[]
    for row in document['roots']:
        require(type(row) is dict and set(row)=={'source','prefix','type','owner','reason'},'Invalid root record')
        require(type(row['source']) is str and Path(row['source']).is_absolute(),'Source must be absolute')
        source=B.absolute(row['source']);prefix='/'.join(B.safe(row['prefix']))
        require(prefix.split('/')[0].casefold()!=META and row['type'] in ('directory','file','symlink'),'Invalid root type/reserved prefix')
        require(all(type(row[k]) is str and 1<=len(row[k])<=4096 for k in ('owner','reason')),'Root attribution required')
        require(source!=output and source not in output.parents and output not in source.parents,'Input/output overlap')
        for existing in roots:require(source!=existing['source_path'] and source not in existing['source_path'].parents and existing['source_path'] not in source.parents,'Overlapping source roots')
        folded=prefix.casefold()
        for prior in prefixes:require(folded!=prior and not folded.startswith(prior+'/') and not prior.startswith(folded+'/'),'Overlapping/case-aliased destination prefixes')
        prefixes.append(folded);roots.append(dict(row,source_path=source))
    return roots


def _kind(mode):
    return 'directory' if stat.S_ISDIR(mode) else 'file' if stat.S_ISREG(mode) else 'symlink' if stat.S_ISLNK(mode) else 'socket' if stat.S_ISSOCK(mode) else 'fifo' if stat.S_ISFIFO(mode) else 'unsupported'


def _read_entry(fd,leaf,signature):
    kind=_kind(signature[2]);require(kind!='file' or signature[3]<=B.MAX_FILE,'Root/file byte bound');entry={'type':kind,'source_signature':list(signature),'original_mode':stat.S_IMODE(signature[2])}
    if kind=='file':
        handle=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        with os.fdopen(handle,'rb') as source:
            require(B.signature(os.fstat(source.fileno()))==signature,'Source file identity changed')
            count=0;digest=hashlib.sha256()
            for raw in R.file_chunks(source):
                count+=len(raw);require(count<=signature[3],'Source grew during census');digest.update(raw)
            require(count==signature[3] and B.signature(os.fstat(source.fileno()))==signature,'Source changed during census')
        entry.update(bytes=count,sha256=digest.hexdigest())
    elif kind=='symlink':
        target=os.readlink(leaf,dir_fd=fd);raw=os.fsencode(target);require(len(raw)<=65536,'Literal target bound')
        entry.update(bytes=len(raw),sha256=B.sha(raw),link_target=target,link_not_dereferenced=True)
    elif kind=='directory':entry.update(bytes=0,sha256=B.sha(b''))
    else:entry.update(source_bytes=signature[3],payload_copied=False,ipc_endpoint_recreated=False)
    require(B.signature(os.stat(leaf,dir_fd=fd,follow_symlinks=False))==signature,'Source entry changed after read')
    return entry


def _census(root):
    fd=root['fd'];entries={}
    if root['type']=='directory':
        source=B.scan(fd,root['omissions'])
        for name,signature in source.items():
            parts=B.safe(name)
            with B.descend(fd,parts[:-1]) as parent:entries[name]=_read_entry(parent,parts[-1],signature)
        require(B.scan(fd,root['omissions'])==source,'Source namespace changed during census')
    else:
        signature=B.signature(os.stat(root['source_path'].name,dir_fd=fd,follow_symlinks=False))
        entries['']=_read_entry(fd,root['source_path'].name,signature)
    return entries


def _mapped(root,name):return root['prefix']+('/'+name if name else '')


def _parents(path):
    parts=B.safe(path)
    return ['/'.join(parts[:i]) for i in range(1,len(parts))]


def _copy_file(sourcefd,leaf,expected,outfd,path):
    handle=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=sourcefd)
    with os.fdopen(handle,'rb') as source:
        signature=tuple(expected['source_signature']);require(B.signature(os.fstat(source.fileno()))==signature,'Source changed before copy')
        R.write_new(outfd,path,R.file_chunks(source),expected,mode=0o700 if expected['original_mode']&0o111 else 0o600)
        require(B.signature(os.fstat(source.fileno()))==signature==B.signature(os.stat(leaf,dir_fd=sourcefd,follow_symlinks=False)),'Source changed while copying')


def _receipt(parent_path,name,parent_identity,value):
    with _handles() as handles:
        parent=B.open_dir(parent_path);handles.append(parent)
        require(B.signature(os.fstat(parent))[:2]==parent_identity,'Receipt parent identity changed')
        R.write_new(parent,name,[B.canonical(value)])


def snapshot(document,output,*,document_sha256=None,omissions=None,omissions_sha256=None):
    """Copy a parsed map whose raw-byte pin the caller already validated.

    The CLI supplies read_pinned_document outputs. Direct Python callers must
    establish that each supplied digest belongs to its parsed document; this
    function validates the shape/pin format, not unavailable original JSON bytes.
    """
    output=B.absolute(output);require(B.HEX.fullmatch(document_sha256 or ''),'Pinned root map required');roots=_document(document,output);omitted=B.omission_index(omissions)
    require(not omitted or B.HEX.fullmatch(omissions_sha256 or ''),'Pinned explicit IPC omissions required')
    receipt={'schema_version':'intune-evidence-snapshot-receipt/1','status':'RUNNING','output':str(output),'started_unix':time.time(),
        'roots_document_sha256':document_sha256,'ipc_omissions_document_sha256':omissions_sha256,
        'source_deletion_performed':False,'public_suitability_approved':False,'complete_original_corpus_established':False,
        'historical_three_unexpected_files_closed':False}
    parent_identity=None;created=False;primary=None
    try:
        with _handles() as handles:
            parent=B.open_dir(output.parent);handles.append(parent);parent_identity=B.signature(os.fstat(parent))[:2]
            require(not B.exists(parent,output.name) and not B.exists(parent,output.name+'.snapshot-receipt.json'),'Destination/receipt already exists')
            claimed=set();identities=set();before=[]
            for root in roots:
                path=root['source_path'];root['omissions']={}
                for name,item in omitted.items():
                    if name.startswith(root['prefix']+'/'):
                        relative=name[len(root['prefix'])+1:];root['omissions'][relative]=dict(item,path=relative);claimed.add(name)
                require(root['type']=='directory' or not root['omissions'],'IPC omission cannot replace a selected root')
                fd=B.open_dir(path if root['type']=='directory' else path.parent);handles.append(fd);root['fd']=fd
                info=os.fstat(fd) if root['type']=='directory' else os.stat(path.name,dir_fd=fd,follow_symlinks=False)
                require(_kind(info.st_mode)==root['type'],'Source root type mismatch')
                root['identity']=B.signature(info)
                if root['type']=='directory':
                    require(root['identity'][:2] not in identities,'Duplicate physical directory root');identities.add(root['identity'][:2])
                entries=_census(root);root['before']=entries
                before.append({'source':str(path),'prefix':root['prefix'],'type':root['type'],'owner':root['owner'],'reason':root['reason'],'root_signature':list(root['identity']),'entries':entries})
            require(claimed==set(omitted),'IPC omission is outside selected roots')
            expected={};links=[];total=0;casefolded={}
            def admit(path,entry):
                B.safe(B.ARCHIVE_ROOT+'/work/evidence/'+output.name+'/'+path)
                folded=path.casefold();require(folded not in casefolded or casefolded[folded]==path,'Destination case alias')
                casefolded[folded]=path
                if path in expected:require(expected[path]['type']==entry['type']=='directory','Destination collision')
                else:expected[path]=entry
                require(len(expected)<=B.MAX_ENTRIES,'Combined entry bound')
            for root in roots:
                if root['type']=='directory':
                    for directory in _parents(root['prefix']):admit(directory,{'type':'directory','bytes':0,'sha256':B.sha(b'')})
                    admit(root['prefix'],{'type':'directory','bytes':0,'sha256':B.sha(b'')})
                for name,entry in root['before'].items():
                    path=_mapped(root,name)
                    for directory in _parents(path):admit(directory,{'type':'directory','bytes':0,'sha256':B.sha(b'')})
                    if path in omitted:continue
                    require(entry['type'] in ('file','directory','symlink'),'Unlisted special source entry')
                    admit(path,{key:entry[key] for key in ('type','bytes','sha256') if key in entry}|({'link_target':entry['link_target']} if entry['type']=='symlink' else {}))
                    total+=entry['bytes'];require(total<=B.MAX_TOTAL,'Combined byte bound')
            require(len(expected)+6<=B.MAX_ENTRIES,'Snapshot metadata exceeds combined entry bound')
            os.mkdir(output.name,0o700,dir_fd=parent);created=True
            outfd=os.open(output.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);handles.append(outfd);out_identity=B.signature(os.fstat(outfd))[:2]
            for path,entry in sorted(expected.items(),key=lambda item:(item[0].count('/'),item[0])):
                if entry['type']=='directory':
                    with R.descend(outfd,B.safe(path),create=True) as directory:os.fsync(directory)
            # All ordinary payloads precede literal symlinks. None is executed.
            for root in roots:
                for name,entry in root['before'].items():
                    path=_mapped(root,name)
                    if path in omitted or entry['type']=='directory':continue
                    if entry['type']=='symlink':links.append((path,entry['link_target']));continue
                    parts=B.safe(name) if name else [root['source_path'].name]
                    with B.descend(root['fd'],parts[:-1]) as held:_copy_file(held,parts[-1],entry,outfd,path)
            after=[]
            for root in roots:
                census=_census(root);require(census==root['before'],'Source exact census changed; partial retained')
                current=B.signature(os.fstat(root['fd'])) if root['type']=='directory' else B.signature(os.stat(root['source_path'].name,dir_fd=root['fd'],follow_symlinks=False))
                require(current==root['identity'],'Source root changed')
                reopened=B.open_dir(root['source_path'] if root['type']=='directory' else root['source_path'].parent)
                handles.append(reopened)
                identity=B.signature(os.fstat(reopened)) if root['type']=='directory' else B.signature(os.stat(root['source_path'].name,dir_fd=reopened,follow_symlinks=False))
                require(identity==root['identity'],'Source root pathname changed')
                after.append({'source':str(root['source_path']),'prefix':root['prefix'],'root_signature':list(identity),'entries':census})
            metadata={'roots.json':document,'source-before.json':{'roots':before},'source-after.json':{'roots':after},
                'ipc-omissions.json':{'schema_version':'intune-r4-ipc-omissions/1','entries':list(omitted.values())},
                'snapshot.json':{'schema_version':'intune-evidence-snapshot/1','roots_document_sha256':document_sha256,
                    'ipc_omissions_document_sha256':omissions_sha256,'source_exact_censuses_equal':True,
                    'complete_selected_archivable_roots':True,'complete_selected_roots':not bool(omitted),
                    'complete_original_corpus_established':False,'explicit_ipc_omissions':list(omitted.values()),
                    'original_metadata':'Original modes, stat identities, hard-link relationships and literal targets are retained in source censuses.',
                    'mode_policy':'private0700 directories; files0600/0700 based only on original execute bits; no setid bits',
                    'hardlink_policy':'Separate identical ordinary byte copies; original dev/inode/link count retained as evidence.',
                    'public_suitability_approved':False,'original_sources_preserved':True}}
            require(total+sum(len(B.canonical(value)) for value in metadata.values())<=B.MAX_TOTAL,'Snapshot metadata exceeds combined byte bound')
            expected[META]={'type':'directory','bytes':0,'sha256':B.sha(b'')}
            for name,value in metadata.items():
                raw=B.canonical(value);require(len(raw)<=B.MAX_JSON,'Snapshot census metadata bound');path=META+'/'+name
                R.write_new(outfd,path,[raw]);expected[path]={'type':'file','bytes':len(raw),'sha256':B.sha(raw)}
            for path,target in links:
                parts=B.safe(path)
                with B.descend(outfd,parts[:-1]) as directory:os.symlink(target,parts[-1],dir_fd=directory);os.fsync(directory)
            os.fsync(outfd);R.verify_output(outfd,expected)
            reopened=B.open_dir(output);handles.append(reopened);require(B.signature(os.fstat(reopened))[:2]==out_identity,'Snapshot output path identity changed')
            require(B.signature(os.stat(output.name,dir_fd=parent,follow_symlinks=False))[:2]==out_identity,'Snapshot output identity changed')
            for root in roots:
                final=B.scan(root['fd'],root['omissions']) if root['type']=='directory' else {'':B.signature(os.stat(root['source_path'].name,dir_fd=root['fd'],follow_symlinks=False))}
                require(final=={name:tuple(entry['source_signature']) for name,entry in root['before'].items()},'Source changed during output readback')
            os.fsync(parent)
            receipt.update(status='PASS',expected_payload_entries=len(expected),selected_payload_bytes=total,literal_symlinks=len(links),
                explicit_ipc_omissions=list(omitted.values()),source_censuses_equal=True,output_physical_readback_verified=True,
                metadata_sha256={name:B.sha(B.canonical(value)) for name,value in metadata.items()},
                next_command='Run build-evidence-layer.py --epoch on this frozen snapshot only after provenance/public review.',
                disposal='Only this attributable duplicate snapshot may later be reclaimed after independently verified archive readback and an explicit receipt; original roots remain retained.')
        # Successful descriptor cleanup precedes a PASS receipt.
    except BaseException as error:
        primary=error;receipt.update(status='FAIL',error_type=type(error).__name__,error=str(error),partial_preserved=created)
        raise
    finally:
        receipt['finished_unix']=time.time()
        if parent_identity is not None:
            try:_receipt(output.parent,output.name+'.snapshot-receipt.json',parent_identity,receipt)
            except BaseException as recording:
                if primary is None:raise
                print('SNAPSHOT RECEIPT FAILED: '+json.dumps({'primary':type(primary).__name__,'secondary':type(recording).__name__,'error':str(recording)},ensure_ascii=True),file=sys.stderr)
    return receipt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for name in ('roots','roots-sha256','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--ipc-omissions');parser.add_argument('--ipc-omissions-sha256');args=parser.parse_args(argv)
    try:
        require(bool(args.ipc_omissions)==bool(args.ipc_omissions_sha256),'Omission document/pin must be paired')
        roots=B.read_pinned_document(args.roots,args.roots_sha256)
        omissions=B.read_pinned_document(args.ipc_omissions,args.ipc_omissions_sha256) if args.ipc_omissions else None
        value=snapshot(roots,args.output,document_sha256=args.roots_sha256,omissions=omissions,omissions_sha256=args.ipc_omissions_sha256)
        print(B.canonical(value).decode('ascii'),end='');return 0
    except BaseException as error:
        print('SNAPSHOT FAILED: '+json.dumps({'type':type(error).__name__,'error':str(error)},ensure_ascii=True),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
