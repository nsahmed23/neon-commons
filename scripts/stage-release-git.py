#!/usr/bin/env python3
"""Stage exact finalized R4 archive parts in a fresh bare Git repository.

Default is offline staging and raw Git blob readback. --push is an explicit
separate action using the existing pinned Git/gh transport, only for a new R4
branch and unchanged Neon main. It never provisions credentials or overwrites
an existing remote ref; publication uses an exact expected-absent ref lease.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import types

ORIGIN='https://github.com/nsahmed23/neon-commons.git'
NEW_LAYERS=('r4-source','r4-runtime','r4-evidence','r4-external-evidence','r4-provider-candidate')
PREFIX='intune-workbench/r4-evidence-20261007/'
CHUNK=1024*1024


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def finish_child(child):
    primary=sys.exc_info()[1];failures=[]
    try:
        if child.poll() is None:child.kill();child.wait(timeout=5)
    except BaseException as error:failures.append(type(error).__name__)
    for stream in (child.stdin,child.stdout,child.stderr):
        if stream is not None:
            try:stream.close()
            except BaseException as error:failures.append(type(error).__name__)
    if failures:
        if primary is not None:primary.add_note('Owned Git process cleanup also failed: '+','.join(failures))
        else:raise ValueError('Owned Git process cleanup failed: '+','.join(failures))


def helper(expected):
    path=Path(__file__).absolute().with_name('download-complete-layers.py')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        info=os.fstat(source.fileno());require(stat.S_ISREG(info.st_mode) and info.st_size<=CHUNK,'Transfer helper must be a bounded regular file')
        raw=source.read(CHUNK+1)
    require(re.fullmatch('[a-f0-9]{64}',expected or '') and sha(raw)==expected,'Transfer helper differs from independent pin')
    module=types.ModuleType('qualified_layer_transfer');module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module


def tool(v,path,expected):
    with v.local_stream(path) as (stream,info):
        require(0<info.st_size<=128*CHUNK and info.st_mode&0o111,'Bounded executable required')
        observed=hashlib.file_digest(stream,'sha256').hexdigest()
    require(v.pin(expected) and observed==expected,'Executable differs from independent pin')
    return str(v.absolute(path))


def stage(manifest_path,manifest_sha256,inputs_path,inputs_sha256,repository,branch,
          git_executable,git_sha256,validator_sha256,helper_sha256,*,push=False,
          expected_remote_main=None,gh_executable=None,gh_sha256=None):
    h=helper(helper_sha256);v=h.load_validator(validator_sha256)
    raw=v.bounded(manifest_path);require(v.pin(manifest_sha256) and sha(raw)==manifest_sha256,'Outer manifest differs from independent pin')
    manifest=v.loads(raw);require(isinstance(manifest,dict),'Outer manifest must be an object');repository=v.absolute(repository)
    require(isinstance(manifest.get('layers'),list) and all(isinstance(x,dict)for x in manifest['layers']),'Ordered layer objects required')
    returned={'schema_version':v.RETURN_SCHEMA,'manifest_sha256':manifest_sha256,'layers':[
        {'id':x['id'],'parts':[str(repository/'unused'/x['id']/p['name'])for p in x['archive']['parts']]}for x in manifest.get('layers',[])]}
    v.validate(manifest,returned,manifest_sha256)
    raw_inputs=v.bounded(inputs_path);require(v.pin(inputs_sha256) and sha(raw_inputs)==inputs_sha256,'Archive input map differs from independent pin')
    inputs=v.loads(raw_inputs);require(isinstance(inputs,dict) and set(inputs)=={'schema_version','manifest_sha256','layers'}
        and inputs['schema_version']=='intune-release-git-inputs/1' and inputs['manifest_sha256']==manifest_sha256,'Wrong exact input-map contract')
    require(isinstance(inputs['layers'],list) and all(isinstance(x,dict)for x in inputs['layers']) and tuple(x.get('id')for x in inputs['layers'])==NEW_LAYERS,'All five new layers required in exact declared order')
    require(re.fullmatch(r'intune-r4-[a-z0-9-]{1,64}',branch or ''),'A new bounded R4 branch name is required')
    layers=manifest['layers'][4:];source_paths=[]
    for layer,local in zip(layers,inputs['layers']):
        require(set(local)=={'id','archive'},'Only exact archive paths are accepted')
        path=v.absolute(local['archive']);require(not path.is_relative_to(repository),'Input archives must be outside the new bare repository')
        with v.local_stream(path) as (stream,info):
            require(info.st_size==layer['archive']['bytes'],'Archive size differs from final pin')
            require(hashlib.file_digest(stream,'sha256').hexdigest()==layer['archive']['sha256'],'Archive bytes differ from final pin')
        source_paths.append(path)
    require(len(set(source_paths))==len(source_paths),'Archive path reuse refused')
    git=tool(v,git_executable,git_sha256)
    gh=None
    if push:
        require(isinstance(expected_remote_main,str) and re.fullmatch('[0-9a-f]{40}',expected_remote_main),'Expected unrelated main pin required before push')
        gh=tool(v,gh_executable,gh_sha256)
    else:require(expected_remote_main is None and gh_executable is None and gh_sha256 is None,'Publication arguments require explicit --push')
    rootfd=h.new_directory(v,repository)
    env={'PATH':'/usr/bin:/bin:/usr/local/bin','LC_ALL':'C','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_SYSTEM':'/dev/null',
        'GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0','GIT_ATTR_NOSYSTEM':'1',
        'GIT_AUTHOR_NAME':'Intune Workbench Delivery','GIT_AUTHOR_EMAIL':'delivery@example.invalid',
        'GIT_COMMITTER_NAME':'Intune Workbench Delivery','GIT_COMMITTER_EMAIL':'delivery@example.invalid',
        'GIT_AUTHOR_DATE':'2000-01-01T00:00:00Z','GIT_COMMITTER_DATE':'2000-01-01T00:00:00Z'}
    base=[git,'--git-dir='+str(repository),'-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
        '-c','core.attributesFile=/dev/null','-c','gc.auto=0','-c','protocol.file.allow=never']
    calls=[]
    def root_guard():
        parent,name=v.parent_fd(repository)
        try:
            observed=os.stat(name,dir_fd=parent,follow_symlinks=False);held=os.fstat(rootfd)
            require(stat.S_ISDIR(observed.st_mode) and (observed.st_dev,observed.st_ino)==(held.st_dev,held.st_ino),'Bare repository directory identity changed')
        finally:os.close(parent)
    def run(*args,data=None,network=False):
        root_guard();tool(v,git,git_sha256);environment=dict(env);command=list(base)
        if network:
            require(push and gh is not None,'Network dispatch requires explicit publication mode')
            tool(v,gh,gh_sha256)
            # Existing transport only. Values are never inspected, serialized,
            # printed, or inserted into arguments/URLs/committed data.
            for key in ('GH_TOKEN','GITHUB_TOKEN','HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','NO_PROXY','https_proxy','http_proxy','all_proxy','no_proxy'):
                if key in os.environ:environment[key]=os.environ[key]
            command+=['-c','credential.helper=!'+shlex.quote(gh)+' auth git-credential']
        command+=list(args);result=subprocess.run(command,input=data,capture_output=True,env=environment,timeout=120)
        calls.append({'operation':args[0],'network':network,'exit_code':result.returncode,'stdout_sha256':sha(result.stdout),'stderr_sha256':sha(result.stderr)})
        require(result.returncode==0,'Git operation failed: '+args[0]+'; no automatic retry')
        require(len(result.stdout)<=4*CHUNK and len(result.stderr)<=CHUNK,'Git diagnostic/output bound exceeded')
        return result.stdout.decode().strip()
    report={'schema_version':'intune-r4-git-delivery/1','status':'RUNNING','manifest_sha256':manifest_sha256,
        'input_map_sha256':inputs_sha256,'source_commit':layers[0]['source_commit'],'branch':branch,'origin':ORIGIN,
        'git_sha256':git_sha256,'helper_sha256':helper_sha256,'validator_sha256':validator_sha256,
        'duplicate_chunk_worktree_files_created':False,'remote_mutation_requested':push,'archive_inputs_modified':False,
        'credentials_provisioned_or_disclosed':False,'production_approved':False,'commands':calls}
    try:
        run('init','--bare','--template=','--object-format=sha1',str(repository))
        records=[]
        for layer,path in zip(layers,source_paths):
            parts=[];whole=hashlib.sha256();total=0
            with v.local_stream(path) as (stream,before):
                for part in layer['archive']['parts']:
                    root_guard();tool(v,git,git_sha256);child=subprocess.Popen(base+['hash-object','-w','--stdin'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
                    count=0;digest=hashlib.sha256()
                    try:
                        while count<part['bytes']:
                            data=stream.read(min(CHUNK,part['bytes']-count));require(bool(data),'Archive truncated while streaming')
                            child.stdin.write(data);digest.update(data);whole.update(data);count+=len(data);total+=len(data)
                        child.stdin.close();child.stdin=None;stdout,stderr=child.communicate(timeout=60)
                        require(child.returncode==0 and re.fullmatch(b'[a-f0-9]{40}\n',stdout),'Git part blob staging failed')
                        require(digest.hexdigest()==part['sha256'],'Exact ordered part boundary/hash differs')
                        blob=stdout.decode().strip()
                    finally:
                        finish_child(child)
                    target=PREFIX+layer['id']+'/'+part['name'];run('update-index','--add','--cacheinfo','100644',blob,target)
                    # Independent readback from Git's actual stored blob, not
                    # the input stream or the returned hash-object text.
                    child=subprocess.Popen(base+['cat-file','blob',blob],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
                    check=hashlib.sha256();size=0
                    try:
                        while block:=child.stdout.read(CHUNK):
                            size+=len(block);require(size<=part['bytes'],'Stored Git blob exceeds part length');check.update(block)
                        stderr=child.stderr.read(CHUNK+1);child.wait(timeout=30)
                        require(child.returncode==0 and (size,check.hexdigest())==(part['bytes'],part['sha256']),'Stored Git blob readback differs from exact part')
                    finally:
                        finish_child(child)
                    parts.append({**{key:part[key]for key in ('name','bytes','sha256')},'git_blob':blob,'repository_path':target})
                require(not stream.read(1) and (total,whole.hexdigest())==(layer['archive']['bytes'],layer['archive']['sha256']),'Whole streamed archive differs from final pin')
            records.append({'id':layer['id'],'archive':{k:layer['archive'][k]for k in ('name','bytes','sha256')},'parts':parts})
        for layer,path in zip(layers,source_paths):
            with v.local_stream(path) as (stream,info):
                require(info.st_size==layer['archive']['bytes'] and hashlib.file_digest(stream,'sha256').hexdigest()==layer['archive']['sha256'],'Archive input changed after streaming; preserve staging')
        metadata={'schema_version':'intune-r4-git-data/1','source_commit':report['source_commit'],
            'outer_manifest_input_sha256':manifest_sha256,'layers':records,
            'scope':'Five exact new continuation layers; unchanged complete R2 and R3 layers remain required.',
            'complete_repository':False,'historical_three_unexpected_files_closed':False}
        for path,raw in (('.gitattributes',b'* -text -filter\n'),(PREFIX+'DATA-RECEIPT.json',(json.dumps(metadata,sort_keys=True,indent=2)+'\n').encode())):
            blob=run('hash-object','-w','--stdin',data=raw);run('update-index','--add','--cacheinfo','100644',blob,path)
        tree=run('write-tree');commit=run('commit-tree',tree,data=b'Preserve exact R4 continuation layers with immutable part pins\n')
        require(re.fullmatch('[a-f0-9]{40}',commit),'Unexpected Git commit identity');run('update-ref','refs/heads/'+branch,commit)
        for layer in records:
            for part in layer['parts']:part['url']='https://raw.githubusercontent.com/nsahmed23/neon-commons/'+commit+'/'+part['repository_path']
        report.update(status='LOCAL_STAGED_AND_BLOB_READBACK_VERIFIED',data_commit=commit,data_tree=tree,layers=records)
        if push:
            remote=run('ls-remote',ORIGIN,'refs/heads/main','refs/heads/'+branch,network=True).splitlines()
            require(remote==[expected_remote_main+'\trefs/heads/main'],'Main changed or proposed branch already exists; refuse publication')
            report['publication_phase']='push_requested'
            target='refs/heads/'+branch
            pushed=run('push','--porcelain','--no-verify','--force-with-lease='+target+':',ORIGIN,commit+':'+target,network=True)
            # Git reports success/up-to-date if another writer created the same
            # root commit after ls-remote, even with an expected-absent lease.
            # Require its exact new-ref result as well as atomic ref admission.
            statuses=[line for line in pushed.splitlines() if '\t' in line]
            require(statuses==['*\t'+commit+':'+target+'\t[new branch]'],
                'Git did not report exactly the requested new branch; preserve uncertain publication outcome')
            remote=run('ls-remote',ORIGIN,'refs/heads/main','refs/heads/'+branch,network=True).splitlines()
            require(set(remote)=={expected_remote_main+'\trefs/heads/main',commit+'\trefs/heads/'+branch},'Publication remote identity verification failed')
            report.update(status='PUBLISHED_COMMIT_VERIFIED',remote_main_unchanged=True,remote_commit=commit,
                expected_absent_ref_lease=True,new_branch_porcelain_verified=True)
        root_guard();h.document(rootfd,'STAGING-RECEIPT.json',report);return report
    except BaseException as error:
        report.update(status='FAIL_PRESERVED',error_type=type(error).__name__,error=str(error),remote_outcome_uncertain=report.get('publication_phase')=='push_requested')
        try:h.document(rootfd,'STAGING-FAILURE.json',report)
        except BaseException as secondary:print(json.dumps({'secondary_receipt_failure':type(secondary).__name__},ensure_ascii=True),file=sys.stderr)
        raise
    finally:os.close(rootfd)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','manifest-sha256','inputs','inputs-sha256','repository','branch','git-executable','git-sha256','validator-sha256','helper-sha256'):p.add_argument('--'+name,required=True)
    p.add_argument('--push',action='store_true')
    for name in ('expected-remote-main','gh-executable','gh-sha256'):p.add_argument('--'+name)
    a=p.parse_args(argv)
    try:
        result=stage(a.manifest,a.manifest_sha256,a.inputs,a.inputs_sha256,a.repository,a.branch,a.git_executable,a.git_sha256,
            a.validator_sha256,a.helper_sha256,push=a.push,expected_remote_main=a.expected_remote_main,gh_executable=a.gh_executable,gh_sha256=a.gh_sha256)
        print(json.dumps(result,ensure_ascii=True));return 0
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        print(json.dumps({'status':'FAIL','error_type':type(error).__name__,'error':str(error)},ensure_ascii=True),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
