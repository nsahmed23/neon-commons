#!/usr/bin/env python3
"""Read-only native directory qualification against operator-prepared fixtures.

No ACL, file, registry, tenant or service mutation is performed in fixtures.
Evidence goes to a NEW output directory. Fixtures must be disposable and their
actual properties are independently observed using pinned PowerShell/.NET.
"""
import argparse
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from intune_iac.io import AppError
from intune_iac import windows_directory as wd

ORACLE=r'''$ErrorActionPreference = 'Stop'
$manifest = Get-Content -LiteralPath $env:INTUNE_DIRECTORY_FIXTURES -Raw | ConvertFrom-Json
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rows = @()
foreach ($name in @('private','broad_acl','reparse','reparse_ancestor','foreign_owner')) {
  $path = [string]$manifest.$name
  $item = Get-Item -LiteralPath $path -Force
  $isReparse = ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
  $ancestors = @(); $parent = [IO.Path]::GetDirectoryName($path)
  while ($parent) {
    $parentItem = Get-Item -LiteralPath $parent -Force
    if (($parentItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { $ancestors += $parent }
    $next = [IO.Path]::GetDirectoryName($parent)
    if ($next -eq $parent) { break }; $parent = $next
  }
  $row = [ordered]@{case=$name; directory=$item.PSIsContainer; reparse=$isReparse; reparse_ancestors=$ancestors}
  if (-not $isReparse) {
    $acl = Get-Acl -LiteralPath $path
    $owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
    $aces = @($acl.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]) | ForEach-Object {
      [ordered]@{sid=$_.IdentityReference.Value; type=$_.AccessControlType.ToString(); inherited=$_.IsInherited;
        rights=[long]$_.FileSystemRights; inheritance=$_.InheritanceFlags.ToString(); propagation=$_.PropagationFlags.ToString()}
    })
    $row.owner_sid=$owner; $row.protected=$acl.AreAccessRulesProtected; $row.aces=$aces
  }
  $rows += [pscustomobject]$row
}
[ordered]@{schema='independent-dotnet-directory-oracle/1'; powershell_major=$PSVersionTable.PSVersion.Major;
 current_sid=$current; fixtures=$rows} | ConvertTo-Json -Depth 8 -Compress
'''


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def expected_fixtures(value):
    """Independent oracle expectations; never use the product ACL normalizer."""
    if (type(value) is not dict or value.get('schema')!='independent-dotnet-directory-oracle/1' or
            type(value.get('powershell_major')) is not int or value['powershell_major']<7):
        return False
    sid=value.get('current_sid');rows=value.get('fixtures')
    if type(sid) is not str or not re.fullmatch(r'S-1-(?:[0-9]+-)*[0-9]+',sid) or type(rows) is not list:
        return False
    if len(rows)!=5 or any(type(row) is not dict for row in rows) or {row.get('case') for row in rows}!={'private','broad_acl','reparse','reparse_ancestor','foreign_owner'}:
        return False
    items={row['case']:row for row in rows}
    if any(row.get('directory') is not True for row in rows):return False
    private=items['private'];broad=items['broad_acl'];foreign=items['foreign_owner']
    if any(type(row.get('aces')) is not list or any(type(ace) is not dict or type(ace.get('rights')) is not int for ace in row['aces'])
           for row in (private,broad,foreign)):return False
    if (private.get('reparse') is not False or private.get('owner_sid')!=sid or private.get('protected') is not True
            or not private.get('aces') or any(ace.get('sid')!=sid or ace.get('type')!='Allow' for ace in private['aces'])):
        return False
    if (broad.get('reparse') is not False or broad.get('owner_sid')!=sid or not broad.get('aces') or
            not any(ace.get('sid')!=sid and ace.get('type')=='Allow' and ace.get('rights',0)>0 for ace in broad['aces'])):
        return False
    return (items['reparse'].get('reparse') is True and items['reparse_ancestor'].get('reparse') is False and
            type(items['reparse_ancestor'].get('reparse_ancestors')) is list and bool(items['reparse_ancestor']['reparse_ancestors']) and
            foreign.get('reparse') is False and foreign.get('owner_sid') not in (None,sid))


class IndependentHandleOracle:
    """Separate OS assertions; no product metadata/ACL helper is reused."""
    def __init__(self):
        self.kernel=ctypes.WinDLL('kernel32.dll',use_last_error=True,winmode=0x800)
        self.security=ctypes.WinDLL('advapi32.dll',use_last_error=True,winmode=0x800)
        P=ctypes.c_void_p;D=ctypes.c_uint32;B=ctypes.c_int32
        for name,arguments,result in [('GetCurrentProcess',[],P),('GetCurrentThread',[],P),('GetProcessHandleCount',[P,ctypes.POINTER(D)],B),
                ('CreateFileW',[ctypes.c_wchar_p,D,D,P,D,D,P],P),('CloseHandle',[P],B)]:
            function=getattr(self.kernel,name);function.argtypes=arguments;function.restype=result
        for name,arguments,result in [('ImpersonateSelf',[ctypes.c_int],B),('RevertToSelf',[],B),
                                      ('OpenThreadToken',[P,D,B,ctypes.POINTER(P)],B)]:
            function=getattr(self.security,name);function.argtypes=arguments;function.restype=result
    def count(self):
        count=ctypes.c_uint32()
        if not self.kernel.GetProcessHandleCount(self.kernel.GetCurrentProcess(),ctypes.byref(count)):raise ValueError('handle_count_unavailable')
        return count.value
    def delete_access(self,path):
        handle=self.kernel.CreateFileW(path,0x10000,7,None,3,0x02000000,None)
        if handle in (None,ctypes.c_void_p(-1).value):return ctypes.get_last_error()
        if not self.kernel.CloseHandle(handle):raise ValueError('oracle_close_failed')
        return 0
    @contextmanager
    def impersonate_self(self):
        if not self.security.ImpersonateSelf(2):raise ValueError('self_impersonation_unavailable')
        primary=None
        try:
            token=ctypes.c_void_p()
            if not self.security.OpenThreadToken(self.kernel.GetCurrentThread(),8,True,ctypes.byref(token)):
                raise ValueError('independent_thread_token_absent')
            if not self.kernel.CloseHandle(token):raise ValueError('oracle_close_failed')
            yield
        except BaseException as error:primary=error;raise
        finally:
            if not self.security.RevertToSelf():
                if primary is not None:primary.add_note('Native self-impersonation restoration failed; stop this process.')
                else:raise ValueError('self_impersonation_restoration_failed')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures',required=True,help='Reviewed JSON with private/broad_acl/reparse/reparse_ancestor/foreign_owner directory paths')
    parser.add_argument('--output',required=True,help='New evidence directory outside all fixture directories')
    parser.add_argument('--powershell',help='Pinned native PowerShell 7 executable; no installation or PATH discovery')
    parser.add_argument('--powershell-sha256')
    parser.add_argument('--module-sha256',help='Exact reviewed intune_iac/windows_directory.py hash')
    parser.add_argument('--source-commit',help='Declared linkage; match independently to the release receipt')
    args=parser.parse_args(argv)
    output=Path(args.output).absolute()
    if output.exists() or output.is_symlink() or any(parent.is_symlink() for parent in output.parents):
        parser.error('new_non_symlink_evidence_directory_required')
    output.mkdir(parents=True,mode=0o700)
    result={'schema_version':'intune-windows-directory-qualification/1','status':'BLOCKED',
            'module_sha256':sha(Path(wd.__file__)),'declared_source_commit':args.source_commit,
            'environment':{'sys_platform':sys.platform,'os_name':os.name,'python_version':sys.version,
                'python_executable':sys.executable,'python_sha256':sha(sys.executable),'pointer_bits':ctypes.sizeof(ctypes.c_void_p)*8},
            'source_files':{'windows_directory.py':sha(Path(wd.__file__)),'io.py':sha(ROOT/'intune_iac/io.py'),
                'qualify-windows-directory.py':sha(Path(__file__))},
            'source_linkage_assurance':'Caller-declared commit; exact module bytes bound independently.',
            'scope':'Read-only native private-directory handles and independent ACL/identity fixture controls; no SQLite, creation, restore, process or terminal qualification.',
            'commands':[],'checks':[],'blockers':[], 'native_windows_workbench_qualified':False,
            'platform_qualified':False,'production_approved':False}
    def finish(code):
        with (output/'RESULT.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,ensure_ascii=True);stream.write('\n')
        print(json.dumps({'status':result['status'],'checks':len(result['checks']),'platform_qualified':False}))
        return code
    if sys.platform!='win32' or os.name!='nt':
        result['blockers'].append({'code':'native_windows_host_required','owner':'Windows endpoint/runner owner'})
        return finish(3)
    try:
        if sys.version_info[:2]!=(3,12) or ctypes.sizeof(ctypes.c_void_p)!=8:raise ValueError('native_cpython_312_64bit_required')
        if (args.module_sha256!=result['module_sha256'] or not re.fullmatch('[a-f0-9]{64}',args.module_sha256 or '') or
                not re.fullmatch('[a-f0-9]{40}',args.source_commit or '')):raise ValueError('reviewed_module_and_commit_required')
        pwsh=Path(args.powershell or '')
        if not pwsh.is_absolute() or not pwsh.is_file() or pwsh.is_symlink() or sha(pwsh)!=args.powershell_sha256:
            raise ValueError('pinned_native_powershell_required')
        with pwsh.open('rb') as stream:
            if stream.read(2)!=b'MZ' or pwsh.suffix.lower()!='.exe':raise ValueError('native_powershell_required')
        fixture_file=Path(args.fixtures).absolute()
        with fixture_file.open('rb') as stream:fixture_bytes=stream.read(65537)
        if len(fixture_bytes)>65536:raise ValueError('fixture_manifest_limit')
        fixtures=json.loads(fixture_bytes.decode('utf-8'))
        if type(fixtures) is not dict or set(fixtures)!={'private','broad_acl','reparse','reparse_ancestor','foreign_owner'}:
            raise ValueError('fixture_manifest_invalid')
        for path in fixtures.values():
            wd._components(path)
            if output.resolve().is_relative_to(Path(path).resolve()):raise ValueError('evidence_must_be_outside_fixtures')
        (output/'fixtures.json').write_bytes(fixture_bytes)
        result['fixture_manifest_sha256']=hashlib.sha256(fixture_bytes).hexdigest()
        (output/'oracle.ps1').write_text(ORACLE,encoding='utf-8',newline='\n')
        command=[str(pwsh),'-NoLogo','-NoProfile','-NonInteractive','-File',str(output/'oracle.ps1')]
        environment=dict(os.environ,INTUNE_DIRECTORY_FIXTURES=str(output/'fixtures.json'))
        run=subprocess.run(command,capture_output=True,timeout=30,env=environment,shell=False)
        (output/'oracle.stdout.raw').write_bytes(run.stdout);(output/'oracle.stderr.raw').write_bytes(run.stderr)
        result['commands'].append({'argv':command,'exit_code':run.returncode,'executable_sha256':sha(pwsh),
            'stdout_sha256':sha(output/'oracle.stdout.raw'),'stderr_sha256':sha(output/'oracle.stderr.raw')})
        if run.returncode or len(run.stdout)>65536 or len(run.stderr)>65536:raise ValueError('independent_oracle_failed')
        oracle=json.loads(run.stdout.decode('utf-8-sig'))
        if not expected_fixtures(oracle):raise ValueError('independent_fixture_properties_not_established')
        result['checks'].append({'id':'independent-native-fixture-properties','pass':True})
        native=IndependentHandleOracle()
        for name,expected in [('private',None),('broad_acl','windows_directory_dacl_unsupported'),
                              ('reparse','windows_directory_reparse_or_type'),('reparse_ancestor','windows_directory_reparse_or_type'),
                              ('foreign_owner','windows_directory_owner_or_dacl')]:
            error=None;receipt=None;before=native.count()
            try:
                with wd.pin_private_directory(fixtures[name]) as pinned:
                    receipt=pinned.revalidate()
                    if receipt['owner_sid']!=oracle['current_sid']:raise AssertionError('independent_identity_mismatch')
                    if name=='private':
                        denial=native.delete_access(fixtures[name])
                        result['checks'].append({'id':'delete-access-denied-while-pinned','pass':denial==32,'winerror':denial})
            except AppError as caught:error=caught.code
            result['checks'].append({'id':name,'pass':error==expected,'expected_error':expected,'observed_error':error,'receipt':receipt})
            after=native.count()
            result['checks'].append({'id':name+'-handle-restoration','pass':before==after,'before':before,'after':after})
            if name=='private':
                released=native.delete_access(fixtures[name])
                result['checks'].append({'id':'delete-access-available-after-release','pass':released==0,'winerror':released})
        before=native.count()
        with native.impersonate_self():
            with wd.pin_private_directory(fixtures['private']) as pinned:
                result['checks'].append({'id':'effective-self-thread-token','pass':pinned.revalidate()['owner_sid']==oracle['current_sid']})
        after=native.count()
        result['checks'].append({'id':'impersonation-handle-restoration','pass':before==after,'before':before,'after':after})
        # Force an actual invalid-handle cleanup on this process's own pin. No
        # filesystem object is removed and no other process handle is touched.
        before=native.count();error=None;notes=[]
        try:
            with wd.pin_private_directory(fixtures['private']) as pinned:
                if not native.kernel.CloseHandle(pinned._handles[-1]):raise ValueError('owned_handle_fault_injection_failed')
        except AppError as caught:error=caught.code;notes=getattr(caught,'__notes__',[])
        result['checks'].append({'id':'actual-close-failure-preserves-primary','pass':error=='windows_directory_identity_unavailable' and
            any('cleanup failed' in note for note in notes),'observed_error':error,'cleanup_note_present':bool(notes)})
        after=native.count()
        result['checks'].append({'id':'fault-handle-restoration','pass':before==after,'before':before,'after':after})
        result['status']='PASS' if all(row['pass'] for row in result['checks']) else 'FAIL'
        result['blockers'].append({'code':'native_store_and_full_profile_unimplemented_or_unqualified',
            'owner':'Workbench host-adapter maintainer and organizational qualification owners',
            'next_action':'Implement guarded file creation, SQLite namespace/sidecar integration, locking/durability/backup and native UI; qualify their exact artifacts separately.'})
        return finish(0 if result['status']=='PASS' else 1)
    except (AppError,ValueError,OSError,subprocess.TimeoutExpired,AssertionError) as error:
        result['status']='FAIL';result['blockers'].append({'code':error.code if isinstance(error,AppError) else type(error).__name__,
            'owner':'Native qualification operator','next_action':'Preserve this attempt and correct exact fixture/pin/oracle failure in a new evidence directory.'})
        return finish(1)


if __name__=='__main__':raise SystemExit(main())
