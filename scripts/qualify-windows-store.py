#!/usr/bin/env python3
"""Qualify the inactive Windows store adapter on a NEW disposable native root.

No host profile is enabled, no service is contacted, and every created database,
backup, interrupted journal and failed stage remains available for inspection.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from intune_iac.io import AppError,parse_json
from intune_iac.windows_workbench import WindowsWorkbenchStore,_Filesystem
from intune_iac.workbench_schema import _SCHEMA_SQL_V1
from intune_iac import windows_directory as wd

TENANT='11111111-1111-4111-8111-111111111111'
REQUIRED_FILES=('intune_iac/windows_workbench.py','intune_iac/workbench_store.py',
    'intune_iac/workbench_schema.py','intune_iac/observation_contract.py','intune_iac/windows_sqlite.py',
    'intune_iac/windows_storage.py','intune_iac/windows_directory.py','intune_iac/io.py',
    'intune_iac/host_capabilities.py','scripts/qualify-windows-store.py')
ORACLE=r'''$ErrorActionPreference='Stop'
$paths=Get-Content -LiteralPath $env:INTUNE_STORE_PATHS -Raw | ConvertFrom-Json
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rows=@()
foreach($path in $paths){
 $acl=Get-Acl -LiteralPath $path
 $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]) | ForEach-Object {
  [ordered]@{sid=$_.IdentityReference.Value;type=$_.AccessControlType.ToString();inherited=$_.IsInherited}
 })
 $rows += [pscustomobject]@{path=$path;owner_sid=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value;
  protected=$acl.AreAccessRulesProtected;aces=$rules}
}
[ordered]@{schema='independent-windows-store-acl/1';current_sid=$sid;powershell_major=$PSVersionTable.PSVersion.Major;entries=$rows} |
 ConvertTo-Json -Compress -Depth 8
'''


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-parent');parser.add_argument('--output')
    parser.add_argument('--source-pins');parser.add_argument('--source-pins-sha256')
    parser.add_argument('--powershell');parser.add_argument('--powershell-sha256')
    parser.add_argument('--_crash-database',help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    if args._crash_database:
        if sys.platform!='win32' or os.name!='nt':return 3
        # Owned fixture process: deliberately exit before commit. No network,
        # child processes, credentials or production target are involved.
        db=sqlite3.connect(args._crash_database)
        db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA cache_size=1');db.execute('BEGIN IMMEDIATE')
        for number in range(100):
            db.execute('INSERT INTO operations(operation_id,data_json,recorded_at) VALUES(?,?,?)',
                ('uncommitted-'+str(number),'x'*4000,1))
        os._exit(23)
    if not args.output or not args.disposable_parent:parser.error('disposable_parent_and_output_required')
    output=Path(args.output).absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(ROOT) or any(parent.is_symlink() for parent in output.parents):
        parser.error('new_output_outside_package_required')
    output.mkdir(mode=0o700,parents=True)
    sources={name:sha(ROOT/name) for name in REQUIRED_FILES}
    result={'schema_version':'intune-windows-store-qualification/1','status':'BLOCKED','checks':[],'commands':[],
        'source_files':sources,'environment':{'platform':sys.platform,'python':sys.version,'executable':sys.executable,
            'python_sha256':sha(sys.executable),'sqlite_version':sqlite3.sqlite_version},
        'blockers':[],'retained_fixture':None,'platform_qualified':False,'production_approved':False,'workbench_profile_enabled':False,
        'scope':'Inactive native store component through create/record/query/backup/restore/migrate/recover APIs; no supported Windows CLI, capture reader, real service or host power-loss claim.'}
    def finish(code):
        result['source_files_after']={name:sha(ROOT/name) for name in REQUIRED_FILES}
        result['source_stable']=result['source_files_after']==sources
        if not result['source_stable']:result['status']='FAIL';code=1
        with (output/'RESULT.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
        print(json.dumps({'status':result['status'],'checks':len(result['checks']),'platform_qualified':False}));return code
    if sys.platform!='win32' or os.name!='nt':
        result['blockers'].append({'code':'native_windows_host_required','owner':'Windows endpoint/runner owner'})
        return finish(3)
    def check(ident,passed,**detail):result['checks'].append({'id':ident,'pass':bool(passed),**detail})
    def run(ident,command,env=None):
        try:child=subprocess.run(command,capture_output=True,timeout=30,env=env,shell=False)
        except subprocess.TimeoutExpired as error:
            (output/(ident+'.stdout.raw')).write_bytes(error.stdout or b'');(output/(ident+'.stderr.raw')).write_bytes(error.stderr or b'')
            result['commands'].append({'id':ident,'argv':command,'exit':None,'timed_out':True});raise
        (output/(ident+'.stdout.raw')).write_bytes(child.stdout);(output/(ident+'.stderr.raw')).write_bytes(child.stderr)
        result['commands'].append({'id':ident,'argv':command,'exit':child.returncode});return child
    try:
        if sys.version_info[:2]!=(3,12) or ctypes.sizeof(ctypes.c_void_p)!=8:raise ValueError('native_cpython_312_64bit_required')
        pins_path=Path(args.source_pins or '')
        if sha(pins_path)!=args.source_pins_sha256:raise ValueError('source_pin_manifest_mismatch')
        raw=pins_path.read_bytes()
        if len(raw)>1024*1024:raise ValueError('source_pin_manifest_limit')
        pins=parse_json(raw)
        if (set(pins)!={'source_commit','files'} or not re.fullmatch('[a-f0-9]{40}',pins['source_commit']) or
                pins['files']!=sources):raise ValueError('exact_source_files_required')
        result['declared_source_commit']=pins['source_commit'];result['source_pin_manifest_sha256']=sha(pins_path)
        result['source_linkage_assurance']='Exact file pins checked; independently verify the declared commit/release before executing this procedure.'
        (output/'source-pins.json').write_bytes(raw)
        pwsh=Path(args.powershell or '')
        if not pwsh.is_absolute() or not pwsh.is_file() or pwsh.is_symlink() or sha(pwsh)!=args.powershell_sha256:
            raise ValueError('pinned_native_powershell_required')
        with pwsh.open('rb') as stream:
            if stream.read(2)!=b'MZ' or pwsh.suffix.lower()!='.exe':raise ValueError('native_powershell_required')
        parent=Path(args.disposable_parent);wd._components(str(parent))
        if output.resolve().is_relative_to(parent.resolve()):raise ValueError('output_outside_parent_required')
        root=parent/('intune-workbench-'+uuid.uuid4().hex);result['retained_fixture']=str(root)
        with (output/'planned-fixture.json').open('x',encoding='utf-8') as stream:
            json.dump({'root':str(root),'parent':str(parent),'tenant_id':TENANT,'source_files':sources},stream);stream.flush();os.fsync(stream.fileno())
        # Directory/file barriers remain mandatory. An unsupported barrier stops
        # here with all created artifacts retained and no invented native pass.
        store=WindowsWorkbenchStore.create(str(root),TENANT)
        check('native-create-exact-schema',store.schema_version==2 and store.tenant_id==TENANT)
        store.record_operation('native-readonly-review',{'phase':'review','cloud_authority':False})
        reopened=WindowsWorkbenchStore(str(root),TENANT)
        check('native-record-reopen-history',reopened.operations()[0]['operation_id']=='native-readonly-review')
        with sqlite3.connect(root/'observations.sqlite3') as db:
            check('independent-sqlite-row',db.execute('SELECT operation_id FROM operations').fetchall()==[('native-readonly-review',)])
            check('independent-sqlite-tenant',db.execute("SELECT value FROM metadata WHERE key='tenant_id'").fetchone()[0]==TENANT)
        journal=root/'observations.sqlite3-journal'
        check('persist-journal-retained-inactive',journal.is_file() and not any(journal.read_bytes()[:28]))
        backup=parent/(root.name+'-backup.sqlite3');receipt=store.backup(str(backup))
        check('backup-exact-byte-pin',sha(backup)==receipt['sha256'],receipt=receipt)
        restored_root=parent/(root.name+'-restored')
        restored=WindowsWorkbenchStore.restore(str(backup),str(restored_root),TENANT,expected_sha256=receipt['sha256'])
        check('restored-history',restored.operations()[0]['operation_id']=='native-readonly-review')
        before_backup=sha(backup)
        try:store.backup(str(backup))
        except AppError as error:check('backup-no-overwrite',error.code=='windows_storage_destination_exists' and sha(backup)==before_backup)
        else:check('backup-no-overwrite',False)
        absent_root=parent/(root.name+'-wrong-pin')
        try:WindowsWorkbenchStore.restore(str(backup),str(absent_root),TENANT,expected_sha256='0'*64)
        except AppError as error:check('wrong-backup-pin-before-create',error.code=='windows_workbench_backup_pin_mismatch' and not absent_root.exists())
        else:check('wrong-backup-pin-before-create',False)
        legacy_root=parent/(root.name+'-legacy');legacy=sqlite3.connect(':memory:')
        try:
            legacy.executescript(_SCHEMA_SQL_V1)
            with legacy:legacy.execute('INSERT INTO metadata VALUES(?,?)',('tenant_id',TENANT))
            _Filesystem().create(str(legacy_root),legacy.serialize())
        finally:legacy.close()
        legacy_store=WindowsWorkbenchStore(str(legacy_root),TENANT);legacy_backup=parent/(root.name+'-v1.sqlite3')
        migration=legacy_store.migrate(str(legacy_backup))
        check('v1-migration-new-schema',migration['status']=='migrated' and WindowsWorkbenchStore(str(legacy_root),TENANT).schema_version==2)
        with sqlite3.connect(legacy_backup) as db:check('v1-backup-preserved',db.execute('PRAGMA user_version').fetchone()[0]==1)
        child=run('owned-process-interruption',[sys.executable,'-B',str(Path(__file__).absolute()),'--_crash-database',str(root/'observations.sqlite3')])
        check('owned-process-interrupted-before-commit',child.returncode==23)
        database_sha=sha(root/'observations.sqlite3');journal_sha=sha(journal)
        try:WindowsWorkbenchStore(str(root),TENANT)
        except AppError as error:check('implicit-recovery-denied',error.code=='windows_workbench_recovery_required')
        else:check('implicit-recovery-denied',False)
        recovery_root=parent/(root.name+'-recovery')
        recovered=WindowsWorkbenchStore.recover_into_new(str(root),str(recovery_root),TENANT,
            database_sha256=database_sha,journal_sha256=journal_sha)
        check('only-committed-history-recovered',[row['operation_id'] for row in recovered.operations()]==['native-readonly-review'])
        check('original-interrupted-bytes-preserved',sha(root/'observations.sqlite3')==database_sha and sha(journal)==journal_sha)
        recovered.record_operation('native-recovery-observed',{'phase':'readback'})
        check('recovered-copy-remains-writable',len(WindowsWorkbenchStore(str(recovery_root),TENANT).operations())==2)
        paths=[str(recovery_root),str(recovery_root/'observations.sqlite3'),str(recovery_root/'observations.sqlite3-journal'),str(backup)]
        (output/'acl-paths.json').write_text(json.dumps(paths),encoding='utf-8');(output/'oracle.ps1').write_text(ORACLE,encoding='utf-8')
        env=dict(os.environ);env['INTUNE_STORE_PATHS']=str((output/'acl-paths.json').absolute())
        oracle=run('independent-native-acls',[str(pwsh),'-NoLogo','-NoProfile','-NonInteractive','-File',str(output/'oracle.ps1')],env)
        value=parse_json(oracle.stdout);sid=value.get('current_sid');rows=value.get('entries',[])
        correct=(oracle.returncode==0 and value.get('schema')=='independent-windows-store-acl/1' and value.get('powershell_major',0)>=7 and
            type(sid)is str and len(rows)==len(paths) and {row.get('path') for row in rows}==set(paths))
        for row in rows:
            correct=correct and row.get('owner_sid')==sid and row.get('protected')is True and bool(row.get('aces'))
            for ace in row.get('aces',[]):correct=correct and ace.get('sid')==sid and ace.get('type')=='Allow' and ace.get('inherited')is False
        check('independent-protected-owner-only-acls',correct)
        result['status']='PASS' if all(row['pass'] for row in result['checks']) else 'FAIL'
        return finish(0 if result['status']=='PASS' else 1)
    except (Exception,KeyboardInterrupt) as error:
        result['failure']={'type':type(error).__name__,'code':error.code if isinstance(error,AppError) else 'native_qualification_incomplete',
            'storage_outcome':getattr(error,'storage_outcome',None)}
        if isinstance(error,AppError) and error.code=='windows_storage_namespace_flush_unavailable':
            result['status']='UNSUPPORTED';result['blockers'].append({'code':error.code,'owner':'Windows storage adapter and host qualification owners',
                'next_action':'Preserve created artifacts; establish a reviewed native namespace durability protocol. Do not waive the barrier.'})
            return finish(3)
        result['status']='FAIL';return finish(1)


if __name__=='__main__':raise SystemExit(main())
