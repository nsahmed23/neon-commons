#!/usr/bin/env python3
"""Qualify bounded native Windows launch routes, or retain an explicit BLOCKED receipt.

This does not install software, contact services, or approve the Windows pilot.
The native shell checks and required interactive/device/service checks are separate.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
import zipfile

MAX_OUTPUT = 4 * 1024 * 1024
TENANT = '11111111-1111-4111-8111-111111111111'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write('\n')


def git_bash_path(value):
    """Only explicit local Windows drives; UNC/MSYS filesystem claims stay unqualified."""
    value = str(value)
    p = PureWindowsPath(value)
    if not p.is_absolute() or not re.fullmatch('[A-Za-z]:', p.drive):
        raise ValueError('local_windows_drive_required')
    return '/' + p.drive[0].lower() + '/' + '/'.join(p.parts[1:])


def package_identity(root, archive, expected):
    if not archive or not expected or not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('exact_package_and_digest_required')
    archive = Path(archive)
    if not archive.is_file() or sha(archive) != expected:
        raise ValueError('package_digest_mismatch')
    seen = set(); files = {}
    with zipfile.ZipFile(archive) as zipped:
        members = zipped.infolist()
        if len(members) > 10000 or sum(item.file_size for item in members) > 1024 * 1024 * 1024:
            raise ValueError('package_expansion_limit')
        for item in members:
            parts = PurePosixPath(item.filename).parts
            if (not parts or parts[0] not in ('intune-iac', 'intune-iac-source') or
                PurePosixPath(item.filename).is_absolute() or '..' in parts or
                '\\' in item.filename or ':' in item.filename):
                raise ValueError('unsafe_package_member')
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError('unsupported_package_type')
            if item.is_dir(): continue
            name = '/'.join(parts[1:])
            if not name or name.casefold() in seen: raise ValueError('package_collision')
            seen.add(name.casefold())
            path = root / name
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('package_file_missing_or_link')
            if any(parent.is_symlink() for parent in path.parents if parent != root.parent):
                raise ValueError('package_ancestor_link')
            # Reading the complete member also verifies ZIP CRC without extraction.
            h = hashlib.sha256()
            with zipped.open(item) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
            digest = h.hexdigest()
            if path.stat().st_size != item.file_size or sha(path) != digest:
                raise ValueError('package_file_mismatch')
            files[name] = {'sha256': digest, 'bytes': item.file_size}
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(files): raise ValueError('package_file_set_mismatch')
    return {'sha256': expected, 'bytes': archive.stat().st_size, 'files': files}


def procedure_manifest(root):
    return {
        'schema_version': 'intune-windows-procedures/1',
        'profile': 'Native Windows, pinned CPython 3.12, Git Bash, PowerShell 7, mintty and chosen terminal',
        'authorization': 'Local disposable qualification only; no service credentials, installation, registry change or production write.',
        'automated_scope': ['Exact package file map and tool hashes', 'Git Bash native argument transport including MSYS Graph versus filesystem conversion',
                            'PowerShell .NET ArgumentList and native exit propagation', 'Harmless literal hostile strings and CRLF byte preservation',
                            'Actual help/doctor and explicit host implementation gate',
                            'When native storage is implemented: store-init/overview/text-terminal and independent SQLite assertions; otherwise exact unsupported rejections and no-created-store assertions'],
        'required_implementation_gate': {'profile': 'workbench_store',
            'discovery': 'Read host_capabilities from the exact package doctor entrypoint before attempting storage.',
            'current_native_windows_status': 'UNSUPPORTED',
            'meaning': 'Current private store uses POSIX primitives. A valid unsupported rejection is a negative control and cannot pass native functional qualification.',
            'next_implementation': 'Reviewed SID/DACL, reparse-safe handle, native locking and durable SQLite storage adapter; see docs/HOST-CAPABILITIES-R4.md.'},
        'required_interactive_cases': [
            {'id': 'WIN-MINTTY', 'procedure': 'Launch the verified Bash wrapper from actual mintty with --python ABSOLUTE_NATIVE_PYTHON -- workbench terminal --root PRIVATE_STORE; record terminal/version, actual key stream, raw capture and independent before/after store facts.'},
            {'id': 'WIN-CHOSEN-TERMINAL', 'procedure': 'Repeat in the organizationally chosen terminal; exercise narrow width, resize, Unicode width, non-color cues, reduced motion, back/edit/cancel/resume and terminal restoration. Use the actual visual command discovered in this candidate help.'},
            {'id': 'WIN-RECOVERY', 'procedure': 'Interrupt acquisition/read/write/receipt boundaries only in the disposable local fixture; independently enumerate remaining processes, journal states and permitted recovery. Do not infer this from a helper exit test.'},
            {'id': 'WIN-FILESYSTEM', 'procedure': 'Use actual Windows ACL/reparse and same-volume identity fixtures under disposable roots; retain denial and no-outside-write assertions. Linux inode/mode tests are not substitutes.'},
        ],
        'external_separate_gates': ['Authenticated Graph/provider/backend/CI evidence', 'Actual enrolled device cohort', 'Host crash/power-loss/hostile process boundary', 'Organizational AppSec and release/pilot decision'],
        'unsupported': ['Windows PowerShell 5.1 .NET argument transport', 'UNC paths in this initial qualifier'],
        'reference_launcher': str(root / 'scripts/intune-iac.py'),
    }


def store_profile_gate(document):
    """Read the candidate's explicit implementation contract; never infer support."""
    try:
        report = document['host_capabilities']
        profile = report['profiles']['workbench_store']
        status = profile['status']
        missing = profile['missing_primitives']
        if (report['schema_version'] != 'intune-host-capabilities/1' or
                status not in ('IMPLEMENTED', 'UNSUPPORTED') or type(missing) is not list or
                any(type(item) is not str for item in missing) or
                (status == 'IMPLEMENTED') != (not missing)):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError('host_capability_report_required') from None
    return {'profile': 'workbench_store', 'implementation_status': status,
            'status': 'UNSUPPORTED' if status == 'UNSUPPORTED' else 'IMPLEMENTED',
            'functional_qualification': 'BLOCKED' if status == 'UNSUPPORTED' else 'NOT_STARTED',
            'missing_primitives': missing,
            'qualification_scope': 'Negative rejection is not functional native Windows evidence.'}


def qualification_status(assertions, gates):
    """A passed negative control cannot satisfy the required functional route."""
    if not assertions or any(row.get('passed') is not True for row in assertions):
        return 'FAIL'
    if not gates or any(gate.get('status') not in ('PASS', 'UNSUPPORTED') for gate in gates):
        return 'FAIL'
    if any(gate['status'] == 'UNSUPPORTED' for gate in gates):
        return 'UNSUPPORTED'
    return 'PASS' if all(gate.get('functional_qualification') == 'PASS' for gate in gates) else 'FAIL'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin', required=True)
    parser.add_argument('--output', required=True, help='NEW evidence directory outside the exact package')
    parser.add_argument('--python', dest='python_executable')
    parser.add_argument('--python-sha256')
    parser.add_argument('--bash')
    parser.add_argument('--bash-sha256')
    parser.add_argument('--powershell')
    parser.add_argument('--powershell-sha256')
    parser.add_argument('--package-zip')
    parser.add_argument('--package-sha256')
    parser.add_argument('--source-commit', help='Declared linkage; exact package/file hashes are independently checked')
    args = parser.parse_args(argv)
    root = Path(args.plugin).resolve()
    output = Path(args.output).absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(root):
        parser.error('new_output_outside_package_required')
    if any(p.is_symlink() for p in output.parents): parser.error('output_symlink_ancestor_rejected')
    output.mkdir(parents=True, mode=0o700)
    receipt = {'schema_version': 'intune-native-windows/1', 'status': 'BLOCKED',
               'native_windows_qualified': False, 'platform_qualified': False, 'production_approved': False,
               'scope': 'Bounded native shell argument transport and local application smoke only; interactive/ACL/cleanup/live routes remain separate.',
               'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'environment': {'sys_platform': sys.platform, 'platform': platform.platform(), 'python': sys.version},
               'declared_source_commit': args.source_commit, 'source_linkage_assurance': 'Caller-declared until matched by independent release receipt; package bytes checked separately.',
               'package': None, 'tools': {}, 'commands': [], 'assertions': [], 'blockers': [], 'implementation_gates': [],
               'limitations': ['No installed service, cloud call or credential activation.', 'No native mintty/ConPTY interaction inferred from piped subprocesses.',
                               'PowerShell injected cleanup failure is a local contract control, not observed OS cleanup failure.',
                               'A timeout records uncertain descendant cleanup; this qualifier is not the protected process supervisor.']}
    write(output / 'procedure-manifest.json', procedure_manifest(root))

    def finish(code):
        receipt['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write(output / 'receipt.json', receipt)
        # Fixed compact metadata only; raw captures remain files and never print controls.
        print(json.dumps({'status': receipt['status'], 'native_windows_qualified': False,
                          'commands': len(receipt['commands']), 'assertions': len(receipt['assertions'])}))
        return code

    if sys.platform != 'win32' or os.name != 'nt':
        receipt['blockers'].append({'code': 'native_windows_host_required', 'owner': 'Windows host owner',
                                    'next_action': 'Run this exact procedure on an authorized disposable native Windows host with pinned tools and exact package.'})
        return finish(3)
    try:
        if not args.source_commit or not re.fullmatch('[0-9a-f]{40}', args.source_commit):
            raise ValueError('exact_source_commit_required')
        for name, value, digest in [('python', args.python_executable, args.python_sha256),
                                    ('bash', args.bash, args.bash_sha256),
                                    ('powershell', args.powershell, args.powershell_sha256)]:
            if not value or not PureWindowsPath(value).is_absolute() or not digest or not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError(name + '_absolute_path_and_digest_required')
            executable = Path(value)
            if not executable.is_file() or executable.is_symlink() or sha(executable) != digest:
                raise ValueError(name + '_digest_mismatch')
            with executable.open('rb') as stream:
                if executable.suffix.lower() != '.exe' or stream.read(2) != b'MZ':
                    raise ValueError(name + '_native_executable_required')
            git_bash_path(value)  # Initial supported host procedure is drive-local.
            receipt['tools'][name] = {'path': value, 'sha256': digest}
        receipt['package'] = package_identity(root, args.package_zip, args.package_sha256)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        receipt['blockers'].append({'code': str(error) if isinstance(error, ValueError) else type(error).__name__,
                                    'owner': 'Qualification operator', 'next_action': 'Supply exact reviewed package, commit and tool pins; do not install or silently substitute tools.'})
        return finish(3)

    commands = output / 'commands'; commands.mkdir()
    env = dict(os.environ)
    # No secret environment values are recorded. Avoid Python and Bash startup injection.
    for key in list(env):
        if key in ('BASH_ENV', 'ENV', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP') or key.startswith('BASH_FUNC_'):
            env.pop(key, None)

    def check(ident, value, detail=None):
        receipt['assertions'].append({'id': ident, 'passed': bool(value), 'detail': detail})

    def run(ident, command, expected=0, child_env=None, input_bytes=None):
        directory = commands / ident; directory.mkdir()
        start = time.monotonic(); code = None; timed_out = False
        with (directory / 'stdout.raw').open('xb') as stdout, (directory / 'stderr.raw').open('xb') as stderr:
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                           cwd=output, env=child_env or env, shell=False)
                try:
                    process.communicate(input=input_bytes, timeout=45)
                except subprocess.TimeoutExpired:
                    timed_out = True; process.kill(); process.communicate(timeout=5)
                code = process.returncode
            except OSError as error:
                code = 125
                stderr.write(type(error).__name__.encode('ascii'))
        outputs = {name: {'bytes': (directory / name).stat().st_size, 'sha256': sha(directory / name)}
                   for name in ('stdout.raw', 'stderr.raw')}
        record = {'id': ident, 'argv': command, 'expected_exit': expected, 'exit': code, 'timed_out': timed_out,
                  'elapsed_seconds': time.monotonic()-start, 'outputs': outputs}
        receipt['commands'].append(record)
        check(ident+'-exit', code == expected and not timed_out and all(v['bytes'] <= MAX_OUTPUT for v in outputs.values()))
        if timed_out: receipt['blockers'].append({'code': 'timeout_descendant_cleanup_uncertain', 'owner': 'Windows host owner', 'next_action': 'Inspect task-owned processes and preserve evidence before any cleanup/retry.'})
        return record

    def bash_command(wrapper, arguments):
        return [args.bash, '--noprofile', '--norc', git_bash_path(wrapper), '--python',
                git_bash_path(args.python_executable), '--', *arguments]

    def powershell_command(wrapper, arguments):
        return [args.powershell, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(wrapper),
                '-PythonExecutable', args.python_executable, *arguments]

    version = run('python-version', [args.python_executable,'-I','-B','-c',
        'import json,platform,sys;print(json.dumps({"version":list(sys.version_info[:3]),"platform":sys.platform,"machine":platform.machine()}))'])
    try:
        reported = json.loads((commands/'python-version/stdout.raw').read_text(encoding='utf-8'))
        check('native-python-312', reported['platform']=='win32' and reported['version'][:2]==[3,12], reported)
    except (OSError,ValueError,KeyError): check('native-python-312',False)
    run('bash-version', [args.bash,'--noprofile','--norc','--version'])
    run('powershell-version',[args.powershell,'-NoLogo','-NoProfile','-NonInteractive','-Command',
        '[Console]::Out.WriteLine($PSVersionTable.PSVersion.ToString()); if ($PSVersionTable.PSVersion.Major -lt 7) { exit 64 }'])

    # The exact wrapper runs against a deliberately small native argv fixture.
    # It is separate from application behavior and from Windows shell qualification.
    fixture = output / "- argv space 雪 'single'"; fixture.mkdir()
    payload = fixture / '- exact payload 雪.bin'; payload.write_bytes(b'line1\r\nline2\x00\xff\r\n')
    probe = ('import hashlib,json,os,pathlib,sys\n'
             'payload=pathlib.Path(os.environ["INTUNE_HOST_PAYLOAD"]).read_bytes()\n'
             'pathlib.Path(os.environ["INTUNE_HOST_PROBE"]).write_text(json.dumps({"argv":sys.argv[1:],'
             '"isolated":sys.flags.isolated,"payload_sha256":hashlib.sha256(payload).hexdigest(),'
             '"exclusions":os.environ.get("MSYS2_ARG_CONV_EXCL"),"global_disable":os.environ.get("MSYS_NO_PATHCONV")}),encoding="utf-8")\n'
             'sys.exit(int(os.environ.get("INTUNE_HOST_EXIT","0")))\n')
    (fixture / 'intune-iac.py').write_bytes(probe.replace('\n','\r\n').encode('utf-8'))
    for name in ('intune-workbench.sh','intune-workbench.ps1'): shutil.copyfile(root/'scripts'/name,fixture/name)
    literal = ['/beta/deviceManagement/configurationPolicies', '/v1.0/groups', '-leading',
               'spaces and "double" quotes', "single ' quote", '雪', 'CR\r\nLF',
               '$(touch SYNTHETIC-CANARY)', '`literal`', '\x1b]52;c;SYNTHETIC\x07']
    for shell, builder, suffix in [('bash',bash_command,'sh'),('powershell',powershell_command,'ps1')]:
        capture = fixture / (shell+'-argv.json')
        child_env = dict(env, INTUNE_HOST_PROBE=str(capture), INTUNE_HOST_PAYLOAD=str(payload))
        if shell == 'bash': child_env.update(MSYS2_ARG_CONV_EXCL='*',MSYS_NO_PATHCONV='1')
        filesystem_argument = git_bash_path(payload) if shell == 'bash' else str(payload)
        run(shell+'-literal-argv',builder(fixture/f'intune-workbench.{suffix}',[*literal,filesystem_argument]), child_env=child_env)
        try:
            actual = json.loads(capture.read_text(encoding='utf-8'))
            check(shell+'-literal-values', actual['argv'][:-1] == literal)
            check(shell+'-filesystem-conversion', Path(actual['argv'][-1]).resolve() == payload.resolve())
            check(shell+'-isolated',actual['isolated'] == 1)
            check(shell+'-binary-exact',actual['payload_sha256'] == sha(payload))
            if shell == 'bash': check('bash-scoped-exclusions',actual['exclusions']=='/beta/;/v1.0/' and actual['global_disable'] is None)
        except (OSError, ValueError, KeyError, IndexError): check(shell+'-probe-readable',False)
        run(shell+'-native-exit',builder(fixture/f'intune-workbench.{suffix}',[]),expected=37,
            child_env=dict(child_env,INTUNE_HOST_EXIT='37'))
        run(shell+'-help',builder(root/'scripts'/f'intune-workbench.{suffix}',['workbench','--help']))
        run(shell+'-doctor',builder(root/'scripts'/f'intune-workbench.{suffix}',['doctor']))
        run(shell+'-invalid-command',builder(root/'scripts'/f'intune-workbench.{suffix}',['invalid-synthetic-command']),expected=2)
        store = output / (shell+' private store 雪')
        try:
            gate = store_profile_gate(json.loads((commands/(shell+'-doctor')/'stdout.raw').read_text(encoding='utf-8')))
            check(shell+'-host-capability-contract', True)
        except (OSError, ValueError):
            check(shell+'-host-capability-contract', False)
            receipt['implementation_gates'].append({'shell': shell, 'profile': 'workbench_store', 'status': 'FAIL',
                'functional_qualification': 'BLOCKED', 'reason': 'Missing or inconsistent capability contract; no storage probe dispatched.'})
            continue
        gate['shell'] = shell
        receipt['implementation_gates'].append(gate)
        unsupported = gate['status'] == 'UNSUPPORTED'
        expected_store_exit = 2 if unsupported else 0
        run(shell+'-store-init',builder(root/'scripts'/f'intune-workbench.{suffix}', ['workbench','init','--root',str(store),'--tenant',TENANT]),expected=expected_store_exit)
        run(shell+'-store-overview',builder(root/'scripts'/f'intune-workbench.{suffix}', ['workbench','overview','--root',str(store)]),expected=expected_store_exit)
        run(shell+'-text-terminal',builder(root/'scripts'/f'intune-workbench.{suffix}', ['workbench','terminal','--root',str(store)]),expected=expected_store_exit,input_bytes=b'help\nquit\n')
        if unsupported:
            for operation in ('store-init', 'store-overview', 'text-terminal'):
                try:
                    error = json.loads((commands/(shell+'-'+operation)/'stderr.raw').read_text(encoding='utf-8'))['error']
                    detail = error['details']
                    valid = (error['code'] == 'host_profile_unsupported' and detail['profile'] == 'workbench_store'
                             and detail['status'] == 'UNSUPPORTED' and detail['platform_qualified'] is False)
                    check(shell+'-'+operation+'-unsupported-contract', valid)
                except (OSError, ValueError, KeyError, TypeError):
                    check(shell+'-'+operation+'-unsupported-contract', False)
            check(shell+'-unsupported-no-store-created', not store.exists() and not store.is_symlink())
            receipt['blockers'].append({'code': 'native_store_implementation_required', 'owner': 'Workbench native host adapter maintainer',
                'next_action': 'Implement and review the native private storage contract before native functional qualification; preserve these rejection controls.'})
            continue
        try:
            with sqlite3.connect((store/'observations.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
                tenant = db.execute("SELECT value FROM metadata WHERE key='tenant_id'").fetchone()
                observations = db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
                operations = db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]
            independent_store = tenant==(TENANT,) and observations==0 and operations==0
            check(shell+'-independent-store',independent_store,
                  {'tenant':tenant,'observations':observations,'operations':operations})
        except (OSError,sqlite3.Error):
            independent_store = False
            check(shell+'-independent-store',False)
        store_commands = [row for row in receipt['commands'] if row['id'] in
                          {shell+'-store-init', shell+'-store-overview', shell+'-text-terminal'}]
        passed = independent_store and len(store_commands)==3 and all(row['exit']==0 and not row['timed_out'] for row in store_commands)
        gate['functional_qualification'] = 'PASS' if passed else 'FAIL'
        gate['status'] = gate['functional_qualification']
    check('no-command-canary',not (output/'SYNTHETIC-CANARY').exists() and not (fixture/'SYNTHETIC-CANARY').exists())
    check('payload-still-byte-exact',payload.read_bytes()==b'line1\r\nline2\x00\xff\r\n')

    # Exercise the actual process helper with a harmless injected cleanup fault.
    cleanup_script = output/'cleanup-contract.ps1'
    cleanup_script.write_text(". $env:INTUNE_WRAPPER_TO_TEST\n"
        "$fake = [pscustomobject]@{ ExitCode = 37 }\n"
        "$fake | Add-Member ScriptMethod Start { return $true }\n"
        "$fake | Add-Member ScriptMethod WaitForExit { }\n"
        "$fake | Add-Member ScriptMethod Dispose { throw 'synthetic-cleanup-failure' }\n"
        "$code = Invoke-WorkbenchProcess -Process $fake\n"
        "if ($code -ne 37) { exit 1 }\n"
        "if ((Resolve-WorkbenchExitCode -PrimaryExit 0 -CleanupFailed $true) -ne 126) { exit 1 }\n"
        "exit 0\n", encoding='utf-8')
    run('powershell-primary-before-cleanup', [args.powershell,'-NoLogo','-NoProfile','-NonInteractive','-File',str(cleanup_script)],
        child_env=dict(env,INTUNE_WRAPPER_TO_TEST=str(root/'scripts/intune-workbench.ps1')))
    try:
        after=package_identity(root,args.package_zip,args.package_sha256)
        check('exact-package-unchanged',after==receipt['package'])
    except (ValueError,OSError,zipfile.BadZipFile): check('exact-package-unchanged',False)
    receipt['automated_assertions_status']='PASS' if all(row['passed'] for row in receipt['assertions']) else 'FAIL'
    receipt['status'] = qualification_status(receipt['assertions'], receipt['implementation_gates'])
    receipt['blockers'].append({'code':'required_interactive_and_platform_routes_remain','owner':'Windows, tenant, identity, backend, CI, device and approval owners','next_action':'Run procedure-manifest.json interactive cases, then separately authorized service/CI/backend/device procedures. This scoped PASS cannot approve the declared pilot.'})
    return finish(0 if receipt['status']=='PASS' else (3 if receipt['status']=='UNSUPPORTED' else 1))


if __name__ == '__main__':
    raise SystemExit(main())
