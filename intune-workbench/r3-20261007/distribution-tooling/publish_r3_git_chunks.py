#!/usr/bin/env python3
"""Stage/publish exact evidence ZIP chunks without duplicate chunk worktree files.

Uses a fresh bare Git repository and the existing Git transport. No credentials,
privileges, force pushes, existing branch checkout, or main-branch mutations.
Without --push, performs local staging/commit only. Archive and output metadata
stay separate from the immutable evidence epoch.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

from build_r3_evidence import require, safe

CHUNK_BYTES=96000000
CHUNK_PATH='intune-workbench/r3-evidence-20261007/'
ORIGIN='https://github.com/nsahmed23/neon-commons.git'
BRANCH='intune-r3-evidence-data-20261007'


def publish(archive,receipt_path,repository,manifest_output,*,push=False):
    archive=Path(archive).absolute();repository=Path(repository).absolute();manifest_output=Path(manifest_output).absolute()
    require(not os.path.lexists(repository),'Bare data repository destination already exists')
    require(not os.path.lexists(manifest_output),'Distribution manifest destination already exists')
    receipt=json.loads(Path(receipt_path).read_text());require(receipt['status']=='PASS','Builder receipt did not pass')
    require(archive.stat().st_size==receipt['bytes'],'Archive size differs from receipt')
    repository.mkdir(mode=0o700)
    environment={**os.environ,'GIT_INDEX_FILE':str(repository/'publication.index'),
        'GIT_AUTHOR_NAME':'Codex','GIT_AUTHOR_EMAIL':'codex@openai.com',
        'GIT_COMMITTER_NAME':'Codex','GIT_COMMITTER_EMAIL':'codex@openai.com'}
    def git(*args,input=None):
        command=['git','--git-dir',str(repository),*args]
        result=subprocess.run(command,input=input,capture_output=True,env=environment,timeout=300)
        require(result.returncode==0,'Git command failed (%s): %s'%(args[0],result.stderr.decode(errors='replace')[-2000:]))
        return result.stdout.decode().strip()
    subprocess.run(['git','init','--bare',str(repository)],check=True,capture_output=True,env=environment)
    git('config','gc.auto','0');git('remote','add','origin',ORIGIN)
    parts=[];whole=hashlib.sha256();total=0
    with archive.open('rb') as source:
        for number in range(1,math.ceil(receipt['bytes']/CHUNK_BYTES)+1):
            name=archive.name+'.part%02d'%number;path=CHUNK_PATH+safe(name)
            expected=min(CHUNK_BYTES,receipt['bytes']-total);count=0;digest=hashlib.sha256()
            child=subprocess.Popen(['git','--git-dir',str(repository),'hash-object','-w','--stdin'],stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment)
            try:
                while count<expected:
                    data=source.read(min(1024*1024,expected-count));require(bool(data),'Archive became shorter during staging')
                    child.stdin.write(data);digest.update(data);whole.update(data);count+=len(data);total+=len(data)
                child.stdin.close();child.stdin=None
                stdout,stderr=child.communicate(timeout=120)
                require(child.returncode==0,'Git blob write failed: '+stderr.decode(errors='replace')[-2000:])
                blob=stdout.decode().strip();require(len(blob)==40,'Unexpected Git object format')
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=5)
            git('update-index','--add','--cacheinfo','100644',blob,path)
            parts.append({'name':name,'bytes':count,'sha256':digest.hexdigest(),'git_blob':blob,'repository_path':path})
            print('Staged %d/%d exact chunks without chunk files'%(number,math.ceil(receipt['bytes']/CHUNK_BYTES)),flush=True)
        require(source.read(1)==b'','Archive became larger during staging')
    require((total,whole.hexdigest())==(receipt['bytes'],receipt['sha256']),'Whole archive integrity failed during Git staging')
    metadata={'scope':'Entire R3 evidence epoch supplement; complete immutable R2 repository remains separately required',
        'archive':{'name':archive.name,'bytes':total,'sha256':whole.hexdigest()},'provenance':receipt.get('provenance'),
        'chunk_bytes':CHUNK_BYTES,'part_count':len(parts),'symlinks_are_literal_zip_entries':True,'automatic_extraction':False}
    for path,data in [('.gitattributes',b'* -text -filter\n'),(CHUNK_PATH+'DATA-RECEIPT.json',json.dumps(metadata,indent=2).encode()+b'\n')]:
        blob=git('hash-object','-w','--stdin',input=data);git('update-index','--add','--cacheinfo','100644',blob,path)
    tree=git('write-tree');commit=git('commit-tree',tree,input=b'Preserve complete R3 raw evidence as byte-exact public chunks\n')
    git('update-ref','refs/heads/'+BRANCH,commit)
    for part in parts:part['url']='https://raw.githubusercontent.com/nsahmed23/neon-commons/'+commit+'/'+part['repository_path']
    manifest={'schema_version':'intune-r3-evidence-split-release/1',**metadata,'parts':parts,
        'data_commit':commit,'data_branch':BRANCH,'source_commit':receipt.get('provenance',{}).get('r3_source_commit'),
        'download_helper':'restore_r3_evidence.py requires independently published final size and SHA-256; no extraction',
        'complete_repository':False,'complete_evidence_epoch':True}
    with manifest_output.open('x') as stream:json.dump(manifest,stream,indent=2);stream.write('\n')
    report={'status':'LOCAL_STAGED','data_commit':commit,'branch':BRANCH,'part_count':len(parts),'archive_bytes':total,
        'archive_sha256':whole.hexdigest(),'manifest':str(manifest_output),'bare_repository':str(repository),
        'duplicate_chunk_worktree_files_created':False}
    if push:
        existing=git('ls-remote','--heads','origin','refs/heads/'+BRANCH)
        require(not existing,'Remote data branch already exists; never force or replace')
        git('push','origin',commit+':refs/heads/'+BRANCH)
        remote=git('ls-remote','--heads','origin','refs/heads/'+BRANCH)
        require(remote.split()[0]==commit,'Remote data branch commit mismatch')
        report.update(status='PUBLISHED',remote_commit=commit)
    with manifest_output.with_name(manifest_output.name+'.publication-receipt.json').open('x') as stream:
        json.dump(report,stream,indent=2);stream.write('\n')
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','receipt','repository','manifest-output'):p.add_argument('--'+name,required=True)
    p.add_argument('--push',action='store_true');a=p.parse_args(argv)
    print(json.dumps(publish(a.archive,a.receipt,a.repository,a.manifest_output,push=a.push),indent=2))

if __name__=='__main__':main()
