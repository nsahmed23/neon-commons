#!/usr/bin/env python3
"""Qualify inactive native storage primitives in a NEW disposable child directory.

Existing parent contents are never replaced or removed. Every test file, failed
stage and intentional hard link remains for inspection. No Workbench host profile
is enabled, and process interruption is not a host power-loss qualification.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from intune_iac.io import AppError
from intune_iac import windows_storage as ws,windows_directory as wd

PAYLOAD=b'Intune native storage fixture\r\n\x00\xff\r\n'
ORACLE=r'''$ErrorActionPreference='Stop'
$paths=Get-Content -LiteralPath $env:INTUNE_STORAGE_PATHS -Raw | ConvertFrom-Json
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rows=@()
foreach ($name in @('root','file','lock')) {
  $path=[string]$paths.$name; $acl=Get-Acl -LiteralPath $path
  $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]) | ForEach-Object {
    [ordered]@{sid=$_.IdentityReference.Value;type=$_.AccessControlType.ToString();inherited=$_.IsInherited;rights=[long]$_.FileSystemRights}
  })
  $rows += [pscustomobject]@{name=$name;owner_sid=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value;
    protected=$acl.AreAccessRulesProtected;aces=$rules}
}
[ordered]@{schema='independent-windows-storage-acl/1';current_sid=$sid;powershell_major=$PSVersionTable.PSVersion.Major;
 entries=$rows;file_sha256=(Get-FileHash -LiteralPath $paths.file -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress -Depth 8
'''


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def independent_acl(value,expected_sha):
    if (type(value) is not dict or value.get('schema')!='independent-windows-storage-acl/1' or
            type(value.get('powershell_major')) is not int or value['powershell_major']<7 or
            value.get('file_sha256')!=expected_sha):return False
    sid=value.get('current_sid');rows=value.get('entries')
    if type(sid) is not str or not re.fullmatch(r'S-1-(?:[0-9]+-)*[0-9]+',sid) or type(rows) is not list or len(rows)!=3:
        return False
    if any(type(row) is not dict for row in rows) or {row.get('name') for row in rows}!={'root','file','lock'}:return False
    for row in rows:
        if row.get('owner_sid')!=sid or row.get('protected') is not True or type(row.get('aces')) is not list or not row['aces']:
            return False
        for ace in row['aces']:
            if type(ace) is not dict or ace.get('sid')!=sid or ace.get('type')!='Allow' or ace.get('inherited') is not False:
                return False
    return True


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-parent',help='Existing owner-only private NTFS parent; only a new child is written')
    parser.add_argument('--output',help='New evidence directory outside the disposable parent')
    parser.add_argument('--powershell');parser.add_argument('--powershell-sha256')
    parser.add_argument('--storage-sha256');parser.add_argument('--directory-sha256');parser.add_argument('--source-commit')
    parser.add_argument('--_probe-lock',nargs=2,help=argparse.SUPPRESS)
    parser.add_argument('--_hold-lock',nargs=2,help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    if args._probe_lock or args._hold_lock:
        root,name=args._probe_lock or args._hold_lock
        try:
            with ws.exclusive_lock(root,name):
                print(json.dumps({'status':'acquired'}),flush=True)
                if args._hold_lock:sys.stdin.buffer.read(1)
            return 0
        except AppError as error:
            print(json.dumps({'error':error.code}),flush=True)
            return 2 if error.code=='windows_storage_lock_busy' else 3
    if not args.disposable_parent or not args.output:parser.error('disposable_parent_and_output_required')
    output=Path(args.output).absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(ROOT) or any(parent.is_symlink() for parent in output.parents):
        parser.error('new_non_symlink_output_required')
    output.mkdir(parents=True,mode=0o700)
    result={'schema_version':'intune-windows-storage-qualification/1','status':'BLOCKED','checks':[],'commands':[],
        'environment':{'platform':sys.platform,'os_name':os.name,'python':sys.version,'executable':sys.executable,'python_sha256':sha(sys.executable)},
        'source_files':{'windows_storage.py':sha(Path(ws.__file__)),'windows_directory.py':sha(Path(wd.__file__)),
            'qualify-windows-storage.py':sha(Path(__file__)),'io.py':sha(ROOT/'intune_iac/io.py')},
        'declared_source_commit':args.source_commit,'source_linkage_assurance':'Caller-declared commit; match exact files to the independently verified release.',
        'scope':'Private creation, byte preservation, exclusive handle-relative publication and cooperative named locks; no SQLite or native power-loss qualification.',
        'blockers':[],'retained_fixture':None,'workbench_profile_enabled':False,'platform_qualified':False,'production_approved':False}
    def finish(code):
        after={'windows_storage.py':sha(Path(ws.__file__)),'windows_directory.py':sha(Path(wd.__file__)),
            'qualify-windows-storage.py':sha(Path(__file__)),'io.py':sha(ROOT/'intune_iac/io.py')}
        result['source_files_after']=after;result['source_stable']=after==result['source_files']
        if not result['source_stable']:
            result['status']='FAIL';code=1
            result['blockers'].append({'code':'qualification_source_changed','owner':'Qualification operator',
                'next_action':'Retain this run and qualify immutable exact reviewed package bytes in a new directory.'})
        with (output/'RESULT.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,ensure_ascii=True);stream.write('\n')
        print(json.dumps({'status':result['status'],'checks':len(result['checks']),'platform_qualified':False}));return code
    if sys.platform!='win32' or os.name!='nt':
        result['blockers'].append({'code':'native_windows_host_required','owner':'Windows endpoint/runner owner'})
        return finish(3)
    def check(ident,passed,**detail):result['checks'].append({'id':ident,'pass':bool(passed),**detail})
    def run(ident,command,expected=0,environment=None):
        try:child=subprocess.run(command,capture_output=True,timeout=20,env=environment,shell=False)
        except subprocess.TimeoutExpired as error:
            (output/(ident+'.stdout.raw')).write_bytes(error.stdout or b'')
            (output/(ident+'.stderr.raw')).write_bytes(error.stderr or b'')
            result['commands'].append({'id':ident,'argv':command,'exit':None,'expected_exit':expected,'timed_out':True,
                'stdout_sha256':sha(output/(ident+'.stdout.raw')),'stderr_sha256':sha(output/(ident+'.stderr.raw')),
                'cleanup_scope':'Subprocess timeout; descendant/host cleanup is not inferred.'})
            raise
        (output/(ident+'.stdout.raw')).write_bytes(child.stdout);(output/(ident+'.stderr.raw')).write_bytes(child.stderr)
        result['commands'].append({'id':ident,'argv':command,'exit':child.returncode,'expected_exit':expected,
            'stdout_sha256':sha(output/(ident+'.stdout.raw')),'stderr_sha256':sha(output/(ident+'.stderr.raw'))})
        check(ident+'-exit',child.returncode==expected)
        return child
    try:
        if sys.version_info[:2]!=(3,12) or ctypes.sizeof(ctypes.c_void_p)!=8:raise ValueError('native_cpython_312_64bit_required')
        if (args.storage_sha256!=result['source_files']['windows_storage.py'] or
                args.directory_sha256!=result['source_files']['windows_directory.py'] or
                not re.fullmatch('[a-f0-9]{40}',args.source_commit or '')):raise ValueError('exact_source_pins_required')
        pwsh=Path(args.powershell or '')
        if not pwsh.is_absolute() or not pwsh.is_file() or pwsh.is_symlink() or sha(pwsh)!=args.powershell_sha256:
            raise ValueError('pinned_native_powershell_required')
        with pwsh.open('rb') as stream:
            if stream.read(2)!=b'MZ' or pwsh.suffix.lower()!='.exe':raise ValueError('native_powershell_required')
        parent=Path(args.disposable_parent)
        wd._components(str(parent))
        if output.resolve().is_relative_to(parent.resolve()):raise ValueError('output_outside_disposable_parent_required')
        child_name='intune-storage-'+uuid.uuid4().hex;workspace=parent/child_name
        result['retained_fixture']=str(workspace)
        with (output/'planned-fixture.json').open('x',encoding='utf-8') as stream:
            json.dump({'root':str(workspace),'parent':str(parent),'source_files':result['source_files']},stream,indent=2)
            stream.flush();os.fsync(stream.fileno())
        created=ws.create_private_directory(str(parent),child_name)
        check('private-directory-created',workspace.is_dir(),receipt=created)
        stage=ws.create_new_file(str(workspace),'stage.bin',PAYLOAD)
        check('binary-create-exact',(workspace/'stage.bin').read_bytes()==PAYLOAD,receipt=stage)
        digest=hashlib.sha256(PAYLOAD).hexdigest()
        try:ws.create_new_file(str(workspace),'stage.bin',b'forbidden replacement')
        except AppError as error:check('create-new-rejects-existing',error.code=='windows_storage_destination_exists')
        else:check('create-new-rejects-existing',False)
        check('existing-stage-unchanged',(workspace/'stage.bin').read_bytes()==PAYLOAD)
        published=ws.publish_new(str(workspace),'stage.bin','final.bin',digest)
        check('exclusive-publication-readback',not (workspace/'stage.bin').exists() and (workspace/'final.bin').read_bytes()==PAYLOAD,receipt=published)
        ws.create_new_file(str(workspace),'second-stage.bin',b'different candidate')
        try:ws.publish_new(str(workspace),'second-stage.bin','final.bin',hashlib.sha256(b'different candidate').hexdigest())
        except AppError as error:check('publication-no-replace',error.code=='windows_storage_destination_exists')
        else:check('publication-no-replace',False)
        check('publication-conflict-preserves-both',(workspace/'final.bin').read_bytes()==PAYLOAD and
            (workspace/'second-stage.bin').read_bytes()==b'different candidate')
        lock_name='scope.lock';probe=[sys.executable,'-I','-B',str(Path(__file__)),'--_probe-lock',str(workspace),lock_name]
        with ws.exclusive_lock(str(workspace),lock_name):
            refused=run('concurrent-lock',probe,2)
            check('concurrent-lock-specific-rejection',json.loads(refused.stdout).get('error')=='windows_storage_lock_busy')
        run('lock-reacquired',probe)
        # Owned child process only: abrupt process termination is a narrower
        # native crash/release check, never a power-loss or hostile escape claim.
        holder_command=[sys.executable,'-I','-B',str(Path(__file__)),'--_hold-lock',str(workspace),lock_name]
        holder=subprocess.Popen(holder_command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=False)
        channel=queue.Queue();thread=threading.Thread(target=lambda:channel.put(holder.stdout.readline()),daemon=True);thread.start()
        try:
            ready=channel.get(timeout=10)
            check('owned-holder-acquired',json.loads(ready).get('status')=='acquired')
        finally:
            if holder.poll() is None:holder.terminate()
            stdout,stderr=holder.communicate(timeout=5)
            (output/'holder.stdout.raw').write_bytes(locals().get('ready',b'')+stdout)
            (output/'holder.stderr.raw').write_bytes(stderr)
            result['commands'].append({'id':'owned-holder-terminated','argv':holder_command,'exit':holder.returncode,
                'scope':'This exact child terminated; no descendant or host-power-loss claim.'})
        run('lock-after-owned-process-termination',probe)
        paths={'root':str(workspace),'file':str(workspace/'final.bin'),'lock':str(workspace/lock_name)}
        (output/'oracle-paths.json').write_text(json.dumps(paths),encoding='utf-8')
        (output/'oracle.ps1').write_text(ORACLE,encoding='utf-8',newline='\n')
        oracle=run('independent-dotnet-acl',[str(pwsh),'-NoLogo','-NoProfile','-NonInteractive','-File',str(output/'oracle.ps1')],
            environment=dict(os.environ,INTUNE_STORAGE_PATHS=str(output/'oracle-paths.json')))
        check('native-created-owner-only-acls',independent_acl(json.loads(oracle.stdout.decode('utf-8-sig')),digest))
        os.link(workspace/'final.bin',workspace/'intentional-hardlink.bin')
        try:ws.publish_new(str(workspace),'final.bin','forbidden-linked-move.bin',digest)
        except AppError as error:check('native-hardlink-rejected',error.code=='windows_storage_file_type_or_links')
        else:check('native-hardlink-rejected',False)
        check('hardlink-failure-preserves-originals',(workspace/'final.bin').read_bytes()==PAYLOAD and
            (workspace/'intentional-hardlink.bin').read_bytes()==PAYLOAD and not (workspace/'forbidden-linked-move.bin').exists())
        result['status']='PASS' if all(row['pass'] for row in result['checks']) else 'FAIL'
        result['blockers'].append({'code':'sqlite_namespace_power_loss_and_full_profile_remain','owner':'Native storage maintainer, Windows qualification and AppSec owners',
            'next_action':'Qualify root/sidecar SQLite integration, rollback/migration/restore and real host-crash/power-loss durability on the exact released profile before activation.'})
        return finish(0 if result['status']=='PASS' else 1)
    except (AppError,OSError,ValueError,subprocess.TimeoutExpired,queue.Empty) as error:
        code=error.code if isinstance(error,AppError) else type(error).__name__
        result['status']='UNSUPPORTED' if code=='windows_storage_namespace_flush_unavailable' else 'FAIL'
        result['blockers'].append({'code':code,'owner':'Native storage/Windows qualification owner',
            'storage_outcome':getattr(error,'storage_outcome',None),
            'next_action':'Retain the recorded fixture and stages. Inspect exact paths and native barrier support; do not delete, overwrite or silently retry an uncertain operation.'})
        return finish(3 if result['status']=='UNSUPPORTED' else 1)


if __name__=='__main__':raise SystemExit(main())
