#!/usr/bin/env python3
"""Read-only native qualification of operator-prepared disposable SQLite fixtures.

No fixture, ACL, sidecar or database is changed. Only a NEW evidence directory is
written. A separate native helper requests write/delete access but never writes
or deletes. Failed and recovery-required fixtures remain intact.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from intune_iac.io import AppError, parse_json
from intune_iac import windows_sqlite as product, windows_directory as wd

ORACLE = r'''$ErrorActionPreference='Stop'
$manifest=Get-Content -LiteralPath $env:INTUNE_SQLITE_FIXTURES -Raw | ConvertFrom-Json
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rows=@()
foreach ($name in @('clean','hot_journal','wal','hardlink')) {
  $root=[string]$manifest.$name
  foreach ($kind in @('root','database')) {
    $path=if($kind -eq 'root'){$root}else{Join-Path $root 'observations.sqlite3'}
    $acl=Get-Acl -LiteralPath $path
    $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]) | ForEach-Object {
      [ordered]@{sid=$_.IdentityReference.Value;type=$_.AccessControlType.ToString();inherited=$_.IsInherited}
    })
    $rows += [pscustomobject]@{case=$name;kind=$kind;owner_sid=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value;
      protected=$acl.AreAccessRulesProtected;aces=$rules}
  }
}
[ordered]@{schema='independent-windows-sqlite-acl/1';current_sid=$sid;powershell_major=$PSVersionTable.PSVersion.Major;
  entries=$rows} | ConvertTo-Json -Compress -Depth 8
'''


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def independent_acl(value):
    if (type(value) is not dict or value.get('schema') != 'independent-windows-sqlite-acl/1' or
            type(value.get('powershell_major')) is not int or value['powershell_major'] < 7):
        return False
    sid = value.get('current_sid'); rows = value.get('entries')
    expected = {(case, kind) for case in ('clean', 'hot_journal', 'wal', 'hardlink') for kind in ('root', 'database')}
    if not isinstance(sid, str) or not re.fullmatch(r'S-1-(?:[0-9]+-)*[0-9]+', sid) or type(rows) is not list or len(rows) != 8:
        return False
    if any(type(row) is not dict for row in rows) or {(row.get('case'), row.get('kind')) for row in rows} != expected:
        return False
    for row in rows:
        if row.get('owner_sid') != sid or row.get('protected') is not True or type(row.get('aces')) is not list or not row['aces']:
            return False
        for ace in row['aces']:
            if type(ace) is not dict or ace.get('sid') != sid or ace.get('type') != 'Allow' or ace.get('inherited') is not False:
                return False
    return True


def probe(path, access, hold=False):
    """Native access-open only: never write, truncate, rename or delete."""
    if sys.platform != 'win32' or os.name != 'nt':
        return 3
    kernel = C.WinDLL('kernel32.dll', use_last_error=True, winmode=0x800)
    kernel.CreateFileW.argtypes = [C.c_wchar_p, C.c_uint32, C.c_uint32, C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p]
    kernel.CreateFileW.restype = C.c_void_p
    kernel.CloseHandle.argtypes = [C.c_void_p]; kernel.CloseHandle.restype = C.c_int32
    handle = kernel.CreateFileW(path, access, 3, None, 3, 0x00200000, None)
    error = C.get_last_error()
    if handle in (None, C.c_void_p(-1).value):
        print(json.dumps({'opened': False, 'winerror': error}), flush=True)
        return 2
    try:
        print(json.dumps({'opened': True, 'winerror': 0}), flush=True)
        if hold:
            sys.stdin.buffer.read(1)
    finally:
        if not kernel.CloseHandle(handle):
            return 4
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures'); parser.add_argument('--output')
    parser.add_argument('--powershell'); parser.add_argument('--powershell-sha256')
    parser.add_argument('--module-sha256'); parser.add_argument('--source-commit')
    parser.add_argument('--_probe', nargs=2, help=argparse.SUPPRESS)
    parser.add_argument('--_hold-writer', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args._probe:
        return probe(args._probe[0], {'write': 0x40000000, 'delete': 0x10000}[args._probe[1]])
    if args._hold_writer:
        return probe(args._hold_writer, 0x40000000, True)
    if not args.output or not args.fixtures:
        parser.error('fixtures_and_output_required')
    output = Path(args.output).absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(ROOT) or any(parent.is_symlink() for parent in output.parents):
        parser.error('new_output_outside_package_required')
    output.mkdir(mode=0o700, parents=True)
    files = [Path(product.__file__), ROOT/'intune_iac/windows_storage.py', Path(wd.__file__), ROOT/'intune_iac/io.py', Path(__file__)]
    result = {'schema_version': 'intune-windows-sqlite-qualification/1', 'status': 'BLOCKED', 'checks': [], 'commands': [],
        'source_files': {path.name: sha(path) for path in files}, 'declared_source_commit': args.source_commit,
        'source_linkage_assurance': 'Caller-declared commit; exact files must match independently verified release.',
        'environment': {'platform': sys.platform, 'python': sys.version, 'executable': sys.executable, 'python_sha256': sha(sys.executable)},
        'scope': 'Inactive read-only rollback-mode snapshot and negative controls; no Workbench writes, migration, restoration or native power-loss acceptance.',
        'blockers': [], 'workbench_profile_enabled': False, 'platform_qualified': False, 'production_approved': False}
    def finish(code):
        result['source_files_after'] = {path.name: sha(path) for path in files}
        result['source_stable'] = result['source_files_after'] == result['source_files']
        if not result['source_stable']:
            result['status'] = 'FAIL'; code = 1
        with (output/'RESULT.json').open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, ensure_ascii=True); stream.write('\n')
        print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'platform_qualified': False}))
        return code
    if sys.platform != 'win32' or os.name != 'nt':
        result['blockers'].append({'code': 'native_windows_host_required', 'owner': 'Windows endpoint/runner owner'})
        return finish(3)
    def check(ident, passed, **detail):
        result['checks'].append({'id': ident, 'pass': bool(passed), **detail})
    def run(ident, command, env=None):
        try:
            child = subprocess.run(command, capture_output=True, timeout=20, env=env, shell=False)
        except subprocess.TimeoutExpired as error:
            (output/(ident+'.stdout.raw')).write_bytes(error.stdout or b'')
            (output/(ident+'.stderr.raw')).write_bytes(error.stderr or b'')
            result['commands'].append({'id':ident,'argv':command,'exit':None,'timed_out':True})
            raise
        for name, data in [('stdout', child.stdout), ('stderr', child.stderr)]:
            (output/(ident+'.'+name+'.raw')).write_bytes(data)
        result['commands'].append({'id': ident, 'argv': command, 'exit': child.returncode})
        return child
    try:
        if sys.version_info[:2] != (3,12) or C.sizeof(C.c_void_p) != 8:
            raise ValueError('native_cpython_312_64bit_required')
        if args.module_sha256 != result['source_files']['windows_sqlite.py'] or not re.fullmatch('[a-f0-9]{40}', args.source_commit or ''):
            raise ValueError('exact_source_pins_required')
        pwsh = Path(args.powershell or '')
        if not pwsh.is_absolute() or not pwsh.is_file() or pwsh.is_symlink() or sha(pwsh) != args.powershell_sha256:
            raise ValueError('pinned_native_powershell_required')
        with pwsh.open('rb') as stream:
            if stream.read(2) != b'MZ' or pwsh.suffix.lower() != '.exe':
                raise ValueError('native_powershell_required')
        raw = Path(args.fixtures).read_bytes()
        if len(raw) > 1024*1024:
            raise ValueError('fixture_manifest_limit')
        fixture = parse_json(raw)
        if set(fixture) != {'clean','hot_journal','wal','hardlink','expected'}:
            raise ValueError('fixture_manifest_invalid')
        expected = fixture['expected']
        if (set(expected) != {'database_sha256','tenant_id','user_version'} or
                not re.fullmatch('[a-f0-9]{64}', expected['database_sha256']) or
                not re.fullmatch('[a-f0-9-]{36}', expected['tenant_id']) or expected['user_version'] != 2):
            raise ValueError('fixture_expectations_invalid')
        roots = [Path(fixture[key]) for key in ('clean','hot_journal','wal','hardlink')]
        if len({str(path).lower() for path in roots}) != 4:
            raise ValueError('distinct_fixture_roots_required')
        before = {}
        for path in roots:
            wd._components(str(path))
            if output.resolve().is_relative_to(path.resolve()):
                raise ValueError('evidence_outside_fixtures_required')
            for entry in path.iterdir():
                if entry.is_symlink() or entry.is_junction() or not entry.is_file():
                    raise ValueError('only_regular_fixture_entries_required')
                before[str(entry)] = sha(entry)
            if sha(path/'observations.sqlite3') != expected['database_sha256']:
                raise ValueError('fixture_database_pin_mismatch')
        (output/'fixture-manifest.json').write_bytes(raw)
        (output/'oracle.ps1').write_text(ORACLE, encoding='utf-8')
        environment = dict(os.environ); environment['INTUNE_SQLITE_FIXTURES'] = str((output/'fixture-manifest.json').absolute())
        oracle = run('independent-acl', [str(pwsh), '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(output/'oracle.ps1')], environment)
        check('independent-owner-only-acls', oracle.returncode == 0 and independent_acl(parse_json(oracle.stdout)))
        clean = fixture['clean']; database = str(Path(clean)/'observations.sqlite3')
        command = [sys.executable, '-B', str(Path(__file__).absolute())]
        with product.read_snapshot(clean) as view:
            check('exact-database-bytes', view.receipt()['database_sha256'] == expected['database_sha256'], receipt=view.receipt())
            check('known-tenant', view.query("SELECT value FROM metadata WHERE key='tenant_id'") == [(expected['tenant_id'],)])
            check('schema-version', view.query('PRAGMA user_version') == [(2,)])
            check('sqlite-quick-check', view.query('PRAGMA quick_check') == [('ok',)])
            for access in ('write','delete'):
                child = run('held-guard-'+access, command+['--_probe', database, access])
                check('held-guard-'+access+'-denied', child.returncode == 2 and parse_json(child.stdout) == {'opened':False,'winerror':32})
            try:
                view.query("UPDATE metadata SET value='forbidden' WHERE key='tenant_id'")
            except AppError as error:
                check('mutating-query-denied', error.code == 'windows_sqlite_query_rejected')
            else:
                check('mutating-query-denied', False)
        for access in ('write','delete'):
            child = run('released-guard-'+access, command+['--_probe',database,access])
            check('released-guard-'+access+'-available', child.returncode == 0 and parse_json(child.stdout) == {'opened':True,'winerror':0})
        # The helper only holds an ordinary write-access handle. It never writes
        # database bytes, and no machine or unrelated process is terminated.
        writer_command = command+['--_hold-writer',database]
        writer = subprocess.Popen(writer_command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=False)
        first = b''; remaining = b''; errors = b''; forced_stop = False
        try:
            ready = queue.Queue()
            threading.Thread(target=lambda:ready.put(writer.stdout.readline()),daemon=True).start()
            first = ready.get(timeout=10)
            if parse_json(first) != {'opened':True,'winerror':0}:
                raise ValueError('native_writer_fixture_not_acquired')
            try:
                with product.read_snapshot(clean):
                    pass
            except AppError as error:
                check('existing-writer-rejected',error.code=='windows_sqlite_read_guard_failed',observed=error.code)
            else:
                check('existing-writer-rejected',False)
        finally:
            try:
                remaining,errors = writer.communicate(b'x',timeout=10)
            except subprocess.TimeoutExpired:
                forced_stop = True; writer.kill(); remaining,errors = writer.communicate(timeout=10)
            (output/'existing-writer.stdout.raw').write_bytes(first+remaining)
            (output/'existing-writer.stderr.raw').write_bytes(errors)
            result['commands'].append({'id':'existing-writer','argv':writer_command,'exit':writer.returncode,'forced_stop':forced_stop})
            check('owned-writer-helper-closed',writer.returncode==0 and not forced_stop)
        for case, error_code in [('hot_journal','windows_sqlite_recovery_required'),('wal','windows_sqlite_wal_sidecar_unsupported'),('hardlink','windows_storage_file_type_or_links')]:
            try:
                with product.read_snapshot(fixture[case]):
                    pass
            except AppError as error:
                check(case+'-rejected', error.code == error_code, observed=error.code)
            else:
                check(case+'-rejected', False)
        after = {str(entry): sha(entry) for path in roots for entry in path.iterdir() if entry.is_file()}
        check('all-fixture-names-and-bytes-preserved', before == after)
        result['fixture_before'] = before; result['fixture_after'] = after
        result['status'] = 'PASS' if all(row['pass'] for row in result['checks']) else 'FAIL'
        return finish(0 if result['status'] == 'PASS' else 1)
    except (Exception, KeyboardInterrupt) as error:
        result['status'] = 'FAIL'
        result['failure'] = {'type': type(error).__name__, 'code': error.code if isinstance(error, AppError) else 'native_qualification_incomplete'}
        return finish(1)


if __name__ == '__main__':
    raise SystemExit(main())
