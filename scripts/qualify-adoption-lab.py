#!/usr/bin/env python3
"""Run the reviewed local Atmos/OpenTofu adoption lab; no external providers.

Pinned Linux amd64 binaries, self-authored fixtures, a fresh output directory,
explicit environment, and a child-only seccomp network denial are mandatory.
This is a qualification tool, not an executor for a user's repository.
"""
import argparse
import ctypes
import hashlib
import json
import os
import shutil
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'labs/atmos-adoption/fixture'
NETWORK_DENIED_SYSCALLS = ('socket', 'socketpair', 'connect')
BINARY_DIGESTS = {
    'tofu': '0a9eda0f0898896969492504a6ce778f310675e8a1eb960434c26806cd252627',
    'atmos': '8e4b057f0cf38686c5eb61db57c8291027a22dfc4ce54a806dc83b34aa96757b',
}
FIXTURE_DIGESTS = {
    'atmos.yaml': '3b1d069b97f13d31d2ff811ed72ebea98dfc7438e8663ad98d6748e11f56b420',
    'components/terraform/policy/main.tf': '56882ebef8ce789ab8f5dc4f11388001108433bdd5c8bd291c990c7dd88c412a',
    'components/terraform/identity/main.tf': '2e25698cdaa922415f2ef8202f604ddc5f5e37ea00c653dfa3e88909c0416e67',
    'stacks/catalog/policy.yaml': '668326ad62b05c2065bc0a697c4da34a18bf16310a2311720185c7541676049c',
    'stacks/deploy/dev.yaml': 'ab3a375ae5689ba38c5b399532a98b74e921b86c2f5d447a5b1fde6e1d58262e',
    'stacks/deploy/prod.yaml': 'aaa13cdbb1d10c116c9949978c2c66716696fbe7e83c5e606007bf03db14d1b3',
    'stacks/deploy/import.yaml': 'a5858a2d7a35911536bc4e61051f16587b95f4e2c70023a3eacda2f5813b287f',
}
ADDRESSES = ('terraform_data.policy', 'terraform_data.targeting')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def validate_fixture(path):
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise ValueError('fixture root must be an ordinary directory')
    expected_dirs = {str(parent) for name in FIXTURE_DIGESTS for parent in Path(name).parents if str(parent) != '.'}
    files = {}
    pending = [path]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                relative = Path(entry.path).relative_to(path).as_posix()
                if entry.is_symlink():
                    raise ValueError('fixture contains a symlink')
                if relative in expected_dirs and entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif relative in FIXTURE_DIGESTS and entry.is_file(follow_symlinks=False):
                    if entry.stat(follow_symlinks=False).st_size > 16384:
                        raise ValueError('fixture member exceeds the fixed size bound')
                    files[relative] = Path(entry.path)
                else:
                    raise ValueError('fixture has an unexpected member')
    if set(files) != set(FIXTURE_DIGESTS):
        raise ValueError('fixture has missing members')
    actual = {}
    for relative, member in files.items():
        with member.open('rb') as stream:
            data = stream.read(16385)
        if len(data) > 16384:
            raise ValueError('fixture member exceeds the fixed size bound')
        actual[relative] = hashlib.sha256(data).hexdigest()
    if actual != FIXTURE_DIGESTS:
        raise ValueError('fixture bytes differ from the reviewed lab')
    return actual


def verify_binary(path, name):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f'{name} must be an executable regular file')
    if sha256(path) != BINARY_DIGESTS[name]:
        raise ValueError(f'{name} digest does not match the qualified Linux amd64 binary')
    return path


def prepare_output(path):
    path = Path(path).absolute()
    resolved = path.resolve()
    if resolved == ROOT or ROOT in resolved.parents or resolved in ROOT.parents:
        raise ValueError('output must be outside and must not contain the plugin source')
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('output path may not traverse a symlink')
    path.mkdir(mode=0o700, parents=False, exist_ok=False)
    return path


def clean_environment(root):
    root = Path(root)
    return {
        'PATH': str(root / 'runtime-bin'), 'LANG': 'C.UTF-8', 'TZ': 'UTC',
        'XDG_CONFIG_HOME': str(root / 'fixture-home/config'),
        'XDG_CACHE_HOME': str(root / 'fixture-home/cache'),
        'XDG_DATA_HOME': str(root / 'fixture-home/data'),
        'TMPDIR': str(root / 'fixture-home/tmp'),
        'ATMOS_TELEMETRY_ENABLED': 'false', 'ATMOS_VERSION_CHECK_ENABLED': 'false',
        'CHECKPOINT_DISABLE': '1', 'TF_IN_AUTOMATION': '1',
        'TF_CLI_CONFIG_FILE': str(root / 'empty.tofurc'),
    }


def network_guard(argv):
    if sys.platform != 'linux':
        raise RuntimeError('This qualified native runner requires Linux and libseccomp')
    lib = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_rule_add.restype = ctypes.c_int
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_load.restype = ctypes.c_int
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = lib.seccomp_init(0x7fff0000)
    if not ctx:
        raise RuntimeError('seccomp initialization failed')
    try:
        for name in NETWORK_DENIED_SYSCALLS:
            number = lib.seccomp_syscall_resolve_name(name.encode())
            if number < 0 or lib.seccomp_rule_add(ctx, 0x00050001, number, 0) != 0:
                raise RuntimeError('seccomp rule failed')
        if lib.seccomp_load(ctx) != 0:
            raise RuntimeError('seccomp load failed')
    finally:
        lib.seccomp_release(ctx)
    os.umask(0o077)
    os.execve(argv[0], argv, dict(os.environ))


def require_actions(plan, expected):
    rows = plan.get('resource_changes', [])
    actual = {row['address']: row['change']['actions'] for row in rows}
    if len(actual) != len(rows) or actual != expected:
        raise AssertionError(f'unexpected resource actions: {actual!r}; expected {expected!r}')


def require_same_state(before, after):
    for key in ('lineage', 'serial', 'resources', 'outputs'):
        if before.get(key) != after.get(key):
            raise AssertionError(f'adoption changed state field {key}')


def resource_ids(state):
    return {f"{row['type']}.{row['name']}": row['instances'][0]['attributes']['id']
            for row in state['resources'] if row['mode'] == 'managed'}


class OutputLimitExceeded(RuntimeError):
    pass


def drain_process(proc, timeout, buffers):
    """Drain both pipes to EOF, including inherited descendant descriptors."""
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout, selectors.EVENT_READ, 'stdout')
        selector.register(proc.stderr, selectors.EVENT_READ, 'stderr')
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(proc.args, timeout)
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                capacity = 2097152 - sum(len(value) for value in buffers.values())
                buffers[key.data].extend(chunk[:capacity])
                if len(chunk) > capacity:
                    raise OutputLimitExceeded('native command output limit exceeded (2 MiB)')
    return proc.wait(timeout=max(0.001, deadline - time.monotonic()))


class Lab:
    def __init__(self, root, binaries):
        self.root = root
        self.deadline = time.monotonic() + 300
        self.environment = clean_environment(root)
        self.checks = []
        self.commands = []
        for directory in ('runtime-bin', 'logs', 'evidence', 'fixture-home/config',
                          'fixture-home/cache', 'fixture-home/data', 'fixture-home/tmp'):
            (root / directory).mkdir(parents=True, exist_ok=True, mode=0o700)
        (root / 'empty.tofurc').write_text('disable_checkpoint = true\n', encoding='utf-8')
        # Atmos uses getent for homedir fallback when HOME is deliberately absent.
        # The shell helper has no variable interpolation or subprocess expansion.
        import shlex
        account = f'fixture:x:{os.getuid()}:{os.getgid()}:fixture:{root / "fixture-home"}:/bin/false'
        helper = root / 'runtime-bin/getent'
        helper.write_text('#!/bin/sh\nprintf "%s\\n" ' + shlex.quote(account) + '\n', encoding='utf-8')
        helper.chmod(0o700)
        for name, source in binaries.items():
            destination = root / 'runtime-bin' / name
            shutil.copyfile(source, destination)
            destination.chmod(0o700)
            verify_binary(destination, name)
        self.repository = root / 'repository'
        shutil.copytree(FIXTURE, self.repository)
        validate_fixture(self.repository)

    def check(self, name, condition, details=None):
        if not condition:
            raise AssertionError(name)
        self.checks.append({'name': name, 'passed': True, 'details': details})

    def native(self, name, tool, args, cwd=None, expected=(0,)):
        if tool not in BINARY_DIGESTS or not name.replace('-', '').isalnum():
            raise ValueError('unknown native tool or receipt name')
        cwd = (cwd or self.repository).resolve()
        if self.root not in cwd.parents:
            raise ValueError('native commands must remain inside the fresh lab')
        remaining = min(45, self.deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError('lab deadline exceeded')
        binary = self.root / 'runtime-bin' / tool
        command = [sys.executable, str(Path(__file__).resolve()), '--guarded-exec', str(binary), *args]
        stdout_path, stderr_path = [self.root / 'logs' / (name + '.' + stream) for stream in ('stdout', 'stderr')]
        failure = None
        outcome = 'completed'
        buffers = {'stdout': bytearray(), 'stderr': bytearray()}
        with stdout_path.open('xb') as stdout, stderr_path.open('xb') as stderr:
            proc = subprocess.Popen(command, cwd=cwd, env=self.environment, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    close_fds=True, start_new_session=True)
            try:
                code = drain_process(proc, remaining, buffers)
            except BaseException as exc:
                failure = exc
                outcome = ('timeout' if isinstance(exc, subprocess.TimeoutExpired) else
                           'output_limit' if isinstance(exc, OutputLimitExceeded) else 'interrupt')
                # Kill only the process group created for this owned command.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                code = proc.wait()
            finally:
                proc.stdout.close()
                proc.stderr.close()
            # Only this parent writes transcripts, once all captured pipe bytes
            # are final. Descendants cannot retain writable transcript handles.
            for stream, key in ((stdout, 'stdout'), (stderr, 'stderr')):
                stream.write(buffers[key])
                stream.flush()
                os.fsync(stream.fileno())
        receipt = {'name': name, 'tool': tool, 'argv': args, 'cwd': str(cwd.relative_to(self.root)),
                   'exit_code': code, 'expected_exit_codes': list(expected), 'outcome': outcome,
                   'transcript_complete': failure is None, 'output_capture_limit_bytes': 2097152,
                   'stdout_sha256': hashlib.sha256(buffers['stdout']).hexdigest(),
                   'stderr_sha256': hashlib.sha256(buffers['stderr']).hexdigest()}
        self.commands.append(receipt)
        write_json(self.root / 'logs' / (name + '.json'), receipt)
        if failure is not None:
            if outcome == 'timeout':
                raise TimeoutError(f'{name}: command deadline exceeded') from failure
            raise failure
        if code not in expected:
            raise AssertionError(f'{name}: exit {code}, expected {expected}; inspect logs')
        return buffers['stdout'].decode('utf-8'), buffers['stderr'].decode('utf-8'), code

    def plan(self, name, stack, component='policy', extra=(), expected=0):
        filename = name + '.tfplan'
        self.native(name, 'atmos', ['terraform', 'plan', component, '-s', stack,
                    '-input=false', '-no-color', '-detailed-exitcode', '-out=' + filename, *extra], expected=(expected,))
        directory = self.repository / 'components/terraform' / component
        stdout, _, _ = self.native(name + '-json', 'tofu', ['show', '-json', filename], cwd=directory)
        plan = json.loads(stdout)
        write_json(self.root / 'evidence' / (name + '.json'), plan)
        return plan

    def state(self, stack, component='policy'):
        path = self.repository / 'components/terraform' / component / 'terraform.tfstate.d' / stack / 'terraform.tfstate'
        return json.loads(path.read_text(encoding='utf-8'))

    def describe(self, stack, component='policy'):
        out, _, _ = self.native('describe-' + stack, 'atmos', ['describe', 'component', component, '-s', stack, '--format', 'json'])
        return json.loads(out)

    def perform(self):
        self.native('tofu-version', 'tofu', ['version'])
        self.native('atmos-version', 'atmos', ['version'])
        dev = self.describe('dev')
        prod = self.describe('prod')
        self.check('logical-and-physical-selection', dev['atmos_stack'] == 'dev' and dev['atmos_manifest'] == 'deploy/dev'
                   and dev['workspace'] == 'dev' and prod['workspace'] == 'prod')
        sys.path.insert(0, str(ROOT))
        from intune_iac.repository import resolve_component
        for stack, native in (('dev', dev), ('prod', prod)):
            result = resolve_component(self.repository, 'deploy/' + stack, 'policy')
            write_json(self.root / 'evidence' / ('plugin-resolution-' + stack + '.json'), result)
            self.check('plugin-native-vars-' + stack, result['status'] == 'resolved' and
                       result['effective']['vars'] == native['vars'], {'physical_selector': 'deploy/' + stack, 'native_logical_stack': stack})
        original = self.root / 'original'
        original.mkdir(mode=0o700)
        shutil.copyfile(self.repository / 'components/terraform/policy/main.tf', original / 'main.tf')
        write_json(original / 'inputs.tfvars.json', dev['vars'])
        self.native('original-init', 'tofu', ['init', '-input=false', '-no-color'], cwd=original)
        self.native('original-apply', 'tofu', ['apply', '-input=false', '-no-color', '-auto-approve', '-var-file=inputs.tfvars.json'], cwd=original)
        before = json.loads((original / 'terraform.tfstate').read_text())
        write_json(self.root / 'evidence/original-state.json', before)
        initial_hash = sha256(original / 'terraform.tfstate')
        destination = self.repository / 'components/terraform/policy/terraform.tfstate.d/dev/terraform.tfstate'
        destination.parent.mkdir(parents=True)
        (original / 'terraform.tfstate').rename(destination)
        self.check('state-relocated-byte-for-byte', not (original / 'terraform.tfstate').exists() and sha256(destination) == initial_hash)
        no_change = self.plan('adopt-no-change', 'dev')
        require_actions(no_change, {address: ['no-op'] for address in ADDRESSES})
        require_same_state(before, self.state('dev'))
        self.apply_saved('adopt-no-change-apply', 'dev', 'adopt-no-change.tfplan')
        require_same_state(before, self.state('dev'))
        self.check('saved-no-change-plan-applied-without-state-change', True)
        self.check('existing-identities-lineage-serial-preserved', True, {'lineage': before['lineage'], 'serial': before['serial'], 'ids': resource_ids(before)})
        attrs = {r['name']: r['instances'][0]['attributes'] for r in before['resources']}
        self.check('targeting-relationship-preserved', attrs['targeting']['input']['value']['policy_id'] == attrs['policy']['id']
                   and attrs['targeting']['input']['value']['excluded_groups'] == dev['vars']['excluded_groups'])
        prod_plan = self.plan('prod-isolated-plan', 'prod', expected=2)
        require_actions(prod_plan, {address: ['create'] for address in ADDRESSES})
        self.native('prod-apply', 'atmos', ['terraform', 'apply', 'policy', '-s', 'prod', '-input=false', '-no-color', '-auto-approve'])
        prod_state = self.state('prod')
        self.check('stack-state-isolation', prod_state['lineage'] != before['lineage'] and
                   set(resource_ids(prod_state).values()).isdisjoint(resource_ids(before).values()))
        require_same_state(before, self.state('dev'))
        changed = self.plan('desired-change', 'dev', extra=('-var=setting=deny',), expected=2)
        require_actions(changed, {'terraform_data.policy': ['update'], 'terraform_data.targeting': ['no-op']})
        policy = next(row for row in changed['resource_changes'] if row['address'] == 'terraform_data.policy')['change']
        self.check('desired-change-observed-without-replacement', policy['before']['input']['setting'] == 'allow'
                   and policy['after']['input']['setting'] == 'deny' and policy['before']['id'] == policy['after']['id'])
        # Progress the same local state after saving the old plan. The old plan
        # must be rejected even though both plans concern the same local IDs.
        intervening = self.plan('intervening-plan', 'dev', extra=('-var=setting=ask',), expected=2)
        require_actions(intervening, {'terraform_data.policy': ['update'], 'terraform_data.targeting': ['no-op']})
        self.apply_saved('intervening-apply', 'dev', 'intervening-plan.tfplan')
        after = self.state('dev')
        self.check('intervening-change-preserves-identity', resource_ids(after) == resource_ids(before)
                   and after['lineage'] == before['lineage'] and after['serial'] > before['serial'])
        component = self.repository / 'components/terraform/policy'
        stdout, stderr, _ = self.native('stale-plan-rejected', 'tofu', ['apply', '-input=false', '-no-color', 'desired-change.tfplan'], cwd=component, expected=(1,))
        self.check('stale-saved-plan-rejected', 'Saved plan is stale' in stdout + stderr)
        require_same_state(after, self.state('dev'))
        require_same_state(prod_state, self.state('prod'))
        self.check('rejected-plan-has-no-state-effects', True)
        self.import_exercise(resource_ids(before)['terraform_data.policy'])
        # Exit state leaves a deliberate desired difference (ask vs allow),
        # recorded rather than hidden by cleanup or a misleading all-clear.
        final = self.plan('final-drift-visible', 'dev', expected=2)
        require_actions(final, {'terraform_data.policy': ['update'], 'terraform_data.targeting': ['no-op']})
        self.check('final-desired-difference-remains-visible', True)

    def apply_saved(self, name, stack, filename):
        path = self.repository / 'components/terraform/policy' / filename
        before = sha256(path)
        self.native(name, 'atmos', ['terraform', 'apply', 'policy', '-s', stack,
                    '--from-plan', '--planfile', filename, '-input=false', '-no-color'])
        self.check(name + '-uses-named-saved-plan', before == sha256(path),
                   {'path': str(path.relative_to(self.root)), 'sha256': before,
                    'evidence': 'Exact native argv and stdout are retained in logs.'})

    def import_exercise(self, identity):
        self.native('identity-import', 'atmos', ['terraform', 'import', 'identity', '-s', 'import', '-input=false', '-no-color', 'terraform_data.identity', identity])
        state = self.state('import', 'identity')
        attrs = state['resources'][0]['instances'][0]['attributes']
        self.check('native-import-preserves-bare-id', attrs['id'] == identity and attrs.get('input') is None)
        # Identity-only import is deliberately distinct from populated input.
        imported = self.plan('import-identity-no-change', 'import', component='identity', expected=0)
        require_actions(imported, {'terraform_data.identity': ['no-op']})
        self.check('identity-only-import-no-change', all(row['actions'] == ['no-op'] for row in imported.get('output_changes', {}).values()))
        main = self.repository / 'components/terraform/identity/main.tf'
        main.write_text(main.read_text().replace('resource "terraform_data" "identity" {}',
                        'resource "terraform_data" "identity" { input = { setting = "allow" } }'))
        populated = self.plan('import-populated-input-change', 'import', component='identity', expected=2)
        require_actions(populated, {'terraform_data.identity': ['update']})
        self.check('import-does-not-recover-configuration-values', True)

    def report(self, status, error=None):
        for command in self.commands:
            for stream in ('stdout', 'stderr'):
                path = self.root / 'logs' / (command['name'] + '.' + stream)
                if not path.is_file() or sha256(path) != command[stream + '_sha256']:
                    status = 'failed'
                    error = 'command transcript hash mismatch: ' + path.relative_to(self.root).as_posix()
        result = {'version': 1, 'status': status, 'checks_passed': len(self.checks), 'checks': self.checks,
                  'commands': self.commands, 'binary_sha256': BINARY_DIGESTS, 'fixture_sha256': FIXTURE_DIGESTS,
                  'runner_sha256': sha256(Path(__file__)),
                  'environment': self.environment, 'network': {'denied_syscalls': NETWORK_DENIED_SYSCALLS, 'filter_required': True},
                  'scope': 'Native Atmos and OpenTofu built-in terraform_data, local disposable state only.',
                  'external_provider_calls': 0, 'cloud_calls': 0, 'filesystem_isolated': False,
                  'limitations': ['No Intune provider or service lifecycle evidence.', 'No authenticated approvals, remote locking, or protected executor qualification.',
                                  'No filesystem sandbox; only the reviewed fixed fixture and pinned tools are accepted.',
                                  'Output contains synthetic local state and intentionally unapplied desired changes.']}
        if error is not None:
            result['error'] = error
        write_json(self.root / 'result.json', result)
        hashes = {p.relative_to(self.root).as_posix(): sha256(p) for p in sorted(self.root.rglob('*'))
                  if p.is_file() and not p.is_symlink() and 'runtime-bin' not in p.relative_to(self.root).parts}
        write_json(self.root / 'artifact-hashes.json', hashes)
        return result


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ['--guarded-exec']:
        network_guard(args[1:])
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tofu', required=True, type=Path)
    parser.add_argument('--atmos', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    opts = parser.parse_args(args)
    validate_fixture(FIXTURE)
    binaries = {name: verify_binary(getattr(opts, name), name) for name in ('tofu', 'atmos')}
    if sys.platform != 'linux':
        parser.error('This runner requires Linux and libseccomp')
    old_mask = os.umask(0o077)
    try:
        out = prepare_output(opts.output)
        lab = Lab(out, binaries)
        try:
            lab.perform()
        except BaseException as exc:
            interrupted = isinstance(exc, KeyboardInterrupt)
            print(json.dumps(lab.report('interrupted' if interrupted else 'failed', f'{type(exc).__name__}: {exc}'), indent=2))
            return 130 if interrupted else 1
        report = lab.report('passed')
        print(json.dumps(report, indent=2))
        return 0 if report['status'] == 'passed' else 1
    finally:
        os.umask(old_mask)


if __name__ == '__main__':
    raise SystemExit(main())
