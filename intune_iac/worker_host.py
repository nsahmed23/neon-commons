"""Pinned local Docker worker boundary; no approval or cloud authority.

The trusted host admits exact code/data/tool digests. The container receives
neither the Docker socket nor a network interface. Native service egress, when
admitted, can only use the separately controlled Unix broker.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import hashlib
import io
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import threading
import time
from uuid import uuid4

from . import protected, provider_execution
from .io import AppError, canonical, digest, load_json, parse_json, sync_directory, write_json

VERSION = 'intune-worker-host/1'
DOCKER_SHA256 = '27f239f97492c434e091a70b41b8796c698f0aa2b6052c6f9c28da4ee7ae888b'
IMAGE = 'alpine@sha256:3e9b4b680bfc9fb5269227cffbd6d42be39fbf7c0b908123913864aa4447e764'
IMAGE_ID = 'sha256:c83674e1999044d33d751661371b873539f47e5b5c5ca3320c7e0377acca6238'
MAX_FILES = 10000
MAX_DIRECTORY_BYTES = 128 * 1024 * 1024
MAX_TOOL_BYTES = 768 * 1024 * 1024
MEMORY_BYTES = 1024 * 1024 * 1024
PIDS = 128
_HASH = re.compile('[0-9a-f]{64}')


def _fail(code):
    raise AppError(code, 'The pinned worker host, payload or cleanup boundary is unavailable, changed or outside its admitted profile.')


def _path(value, *, directory=False, private=False):
    path = Path(value).absolute()
    if '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        _fail('worker_host_unsafe_path')
    info = path.stat()
    if ((not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
            or not directory and info.st_nlink != 1 or info.st_uid not in (0, os.geteuid())
            or info.st_mode & 0o022 or private and (info.st_uid != os.geteuid() or info.st_mode & 0o077)):
        _fail('worker_host_file_identity')
    return path


def _hash_file(path, maximum):
    path = _path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > maximum:
            _fail('worker_host_input_limit')
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(stream.fileno())
    if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns, before.st_size) != (
            after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns, after.st_size):
        _fail('worker_host_input_changed')
    return value


def directory_binding(path):
    """Hash every declared RO directory entry; no implicit exclusions or links."""
    root = _path(path, directory=True)
    files, total = {}, 0
    for current, directories, names in os.walk(root, followlinks=False):
        for name in sorted(directories):
            _path(Path(current) / name, directory=True)
        for name in sorted(names):
            child = _path(Path(current) / name)
            info = child.stat()
            total += info.st_size
            if len(files) >= MAX_FILES or total > MAX_DIRECTORY_BYTES:
                _fail('worker_host_input_limit')
            files[str(child.relative_to(root))] = {'sha256': _hash_file(child, MAX_DIRECTORY_BYTES),
                                                  'bytes': info.st_size, 'mode': stat.S_IMODE(info.st_mode)}
    return {'sha256': digest(files), 'files': files, 'bytes': total}


@dataclass(frozen=True)
class PinnedTool:
    role: str
    path: str
    sha256: str


@dataclass(frozen=True)
class HostSpec:
    docker_path: str
    source_root: str
    source_sha256: str
    control_root: str
    control_sha256: str
    job_root: str
    tools: tuple[PinnedTool, ...] = ()
    broker_root: str | None = None
    broker_ca_sha256: str | None = None
    timeout_seconds: int = 60
    output_limit: int = 1024 * 1024
    uid: int = 1000
    gid: int = 1000


def _validate(spec):
    if sys.platform != 'linux' or os.uname().machine != 'x86_64':
        _fail('worker_host_platform_unsupported')
    if threading.current_thread() is not threading.main_thread():
        _fail('worker_host_main_thread_required')
    if type(spec) is not HostSpec or type(spec.tools) is not tuple:
        _fail('worker_host_spec_invalid')
    if (type(spec.uid) is not int or type(spec.gid) is not int or not 1 <= spec.uid <= 65534
            or spec.uid != os.geteuid() or spec.gid != os.getegid()
            or type(spec.timeout_seconds) is not int or not 1 <= spec.timeout_seconds <= 300
            or type(spec.output_limit) is not int or not 1024 <= spec.output_limit <= 16 * 1024 * 1024):
        _fail('worker_host_profile_invalid')
    docker = _path(spec.docker_path)
    if _hash_file(docker, 128 * 1024 * 1024) != DOCKER_SHA256:
        _fail('worker_host_docker_changed')
    roots = [_path(spec.source_root, directory=True), _path(spec.control_root, directory=True),
             _path(spec.job_root, directory=True, private=True)]
    for index, root in enumerate(roots):
        if any(root == other or root in other.parents or other in root.parents for other in roots[index + 1:]):
            _fail('worker_host_mount_overlap')
    if roots[2] in docker.parents:
        _fail('worker_host_writable_executable')
    for path, expected in ((roots[0], spec.source_sha256), (roots[1], spec.control_sha256)):
        if type(expected) is not str or not _HASH.fullmatch(expected) or directory_binding(path)['sha256'] != expected:
            _fail('worker_host_input_changed')
    _path(roots[1] / 'worker.sh')
    roles = []
    for tool in spec.tools:
        if type(tool) is PinnedTool and roots[2] in Path(tool.path).absolute().parents:
            _fail('worker_host_writable_executable')
        if (type(tool) is not PinnedTool or tool.role not in ('tofu', 'provider', 'atmos', 'relay')
                or tool.role in roles or type(tool.sha256) is not str or not _HASH.fullmatch(tool.sha256)
                or _hash_file(tool.path, MAX_TOOL_BYTES) != tool.sha256):
            _fail('worker_host_tool_changed')
        roles.append(tool.role)
    if spec.broker_root is not None:
        broker = _path(spec.broker_root, directory=True, private=True)
        if any(broker == root or broker in root.parents or root in broker.parents for root in roots):
            _fail('worker_host_mount_overlap')
        entries = list(broker.iterdir())
        sock = broker / 'egress.sock'
        info = sock.lstat()
        if (entries != [sock] or not stat.S_ISSOCK(info.st_mode) or info.st_uid != spec.uid
                or info.st_nlink != 1 or info.st_mode & 0o077 or 'relay' not in roles):
            _fail('worker_host_broker_invalid')
        if (type(spec.broker_ca_sha256) is not str or not _HASH.fullmatch(spec.broker_ca_sha256)
                or _hash_file(roots[1] / 'broker-ca.pem', 1024 * 1024) != spec.broker_ca_sha256):
            _fail('worker_host_broker_ca_changed')
    elif spec.broker_ca_sha256 is not None:
        _fail('worker_host_broker_invalid')
    return {'source': directory_binding(roots[0]), 'control': directory_binding(roots[1]),
            'tools': {tool.role: tool.sha256 for tool in spec.tools}}


def _bytes(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(Path(path).parent)


class _Docker:
    def __init__(self, spec, output):
        self.spec, self.output = spec, output
        self.commands = []
        self.config = output / 'docker-config'
        if not self.config.exists():
            self.config.mkdir(mode=0o700)
            _bytes(self.config / 'config.json', b'{"auths":{}}\n')
        if (self.config / 'config.json').read_bytes() != b'{"auths":{}}\n':
            _fail('worker_host_docker_config_changed')

    def run(self, label, arguments, *, timeout=15, output_limit=1024 * 1024):
        if _hash_file(self.spec.docker_path, 128 * 1024 * 1024) != DOCKER_SHA256:
            _fail('worker_host_docker_changed')
        argv = [self.spec.docker_path, '--config', str(self.config), '--host', 'unix:///var/run/docker.sock', *arguments]
        stem = f'{len(list(self.output.glob("command-*.json"))):03d}-{label}'
        evidence, cleanup, process = {}, {}, None
        selector = selectors.DefaultSelector()
        output, errors, total = bytearray(), bytearray(), 0
        release = lambda: None
        descriptor = None
        primary = None
        try:
            descriptor = os.open(_path(self.spec.docker_path), os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(os.dup(descriptor), 'rb') as opened:
                if hashlib.file_digest(opened, 'sha256').hexdigest() != DOCKER_SHA256:
                    _fail('worker_host_docker_changed')
            guard, release = provider_execution._network_guard()
            with protected._defer_spawn_interrupt(guard) as child_guard:
                process = subprocess.Popen(argv, executable='/proc/self/fd/' + str(descriptor), pass_fds=(descriptor,),
                    cwd=self.output, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'},
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    close_fds=True, shell=False, start_new_session=True, umask=0o077, preexec_fn=child_guard)
            for pipe in (process.stdout, process.stderr):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ)
            deadline = time.monotonic() + timeout
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _fail('worker_host_process_timeout')
                for key, _ in selector.select(min(0.1, remaining)):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    allowed = max(0, output_limit - total)
                    (output if key.fileobj is process.stdout else errors).extend(data[:allowed])
                    total += len(data)
                    if total > output_limit:
                        _fail('worker_host_output_limit')
            code = protected._wait_process_exit(process, deadline=deadline,
                timeout_code='worker_host_process_timeout')
            return {'code': code, 'stdout': bytes(output), 'stderr': bytes(errors)}
        except BaseException as error:
            primary = error
            raise
        finally:
            cleanup_error = None
            try:
                if process is not None:
                    protected._cleanup_process_group(process, evidence=cleanup)
            except BaseException as error:
                cleanup_error = error
            resources = protected._release_process_resources(process, selector, release)
            if descriptor is not None:
                os.close(descriptor)
            _bytes(self.output / (stem + '.stdout'), bytes(output))
            _bytes(self.output / (stem + '.stderr'), bytes(errors))
            record = {'argv': argv, 'timeout_seconds': timeout, 'output_limit': output_limit,
                'exit_code': process.returncode if process is not None else None,
                'primary_error': getattr(primary, 'code', type(primary).__name__) if primary else None,
                'cleanup_error': getattr(cleanup_error, 'code', type(cleanup_error).__name__) if cleanup_error else None,
                'stdout': stem + '.stdout', 'stderr': stem + '.stderr', 'observed_bytes': total,
                'output_truncated': total > output_limit, 'process_cleanup': cleanup, 'resource_errors': resources}
            write_json(self.output / ('command-' + stem + '.json'), record)
            self.commands.append('command-' + stem + '.json')
            if cleanup_error is not None:
                raise cleanup_error from primary
            if resources and primary is None:
                _fail('worker_host_process_cleanup_failed')


def _mount(source, target, readonly):
    if any(ord(c) < 32 for c in str(source)):
        _fail('worker_host_mount_path_invalid')
    stream = io.StringIO()
    fields = ['type=bind', 'source=' + str(source), 'target=' + target]
    if readonly:
        fields.append('readonly')
    csv.writer(stream, lineterminator='').writerow(fields)
    return stream.getvalue()


def _creation(spec, name, run_id, manifest_sha):
    args = ['create', '--pull=never', '--platform=linux/amd64', '--name', name,
        '--label', 'intune.workbench.host-run=' + run_id,
        '--label', 'intune.workbench.manifest-sha256=' + manifest_sha,
        '--log-driver', 'none',
        '--network', 'none', '--ipc', 'private', '--cgroupns', 'private', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--read-only', '--user', f'{spec.uid}:{spec.gid}',
        '--pids-limit', str(PIDS), '--memory', str(MEMORY_BYTES), '--memory-swap', str(MEMORY_BYTES),
        '--cpus', '1', '--ulimit', 'nofile=256:256', '--ulimit', 'core=0:0',
        '--ulimit', 'fsize=268435456:268435456', '--workdir', '/job',
        '--env', 'HOME=/home/workbench', '--env', 'LANG=C.UTF-8', '--env', 'LC_ALL=C.UTF-8',
        '--tmpfs', f'/home/workbench:rw,nosuid,nodev,size=33554432,uid={spec.uid},gid={spec.gid},mode=0700',
        '--tmpfs', f'/tmp:rw,noexec,nosuid,nodev,size=67108864,uid={spec.uid},gid={spec.gid},mode=0700',
        '--mount', _mount(spec.source_root, '/source', True),
        '--mount', _mount(spec.control_root, '/control', True),
        '--mount', _mount(spec.job_root, '/job', False)]
    for tool in spec.tools:
        args.extend(['--mount', _mount(tool.path, '/tools/' + tool.role, True)])
    if spec.broker_root is not None:
        args.extend(['--mount', _mount(spec.broker_root, '/broker', True),
                     '--env', 'HTTPS_PROXY=http://127.0.0.1:18080',
                     '--env', 'HTTP_PROXY=http://127.0.0.1:18080', '--env', 'NO_PROXY=',
                     '--env', 'SSL_CERT_FILE=/control/broker-ca.pem'])
    args.extend([IMAGE, '/bin/sh', '/control/worker.sh'])
    return args


def _inspect(docker, name, label):
    result = docker.run(label, ['container', 'inspect', name])
    if result['code'] != 0:
        missing = (b'No such container: ' + name.encode()) in result['stderr'] or (b'No such object: ' + name.encode()) in result['stderr']
        if result['code'] == 1 and missing:
            return None
        _fail('worker_host_inspect_failed')
    value = parse_json(result['stdout'])
    if type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
        _fail('worker_host_inspect_invalid')
    return value[0]


def _owned(inspect, run_id, manifest_sha):
    if (inspect is None or inspect.get('Config', {}).get('Labels', {}).get('intune.workbench.host-run') != run_id
            or inspect.get('Config', {}).get('Labels', {}).get('intune.workbench.manifest-sha256') != manifest_sha):
        _fail('worker_host_container_identity')


def _boundary(inspect, spec, run_id, manifest_sha):
    _owned(inspect, run_id, manifest_sha)
    config, host = inspect.get('Config', {}), inspect.get('HostConfig', {})
    expected_mounts = {'/source': (str(Path(spec.source_root).absolute()), False),
                       '/control': (str(Path(spec.control_root).absolute()), False),
                       '/job': (str(Path(spec.job_root).absolute()), True)}
    expected_mounts.update({'/tools/' + tool.role: (str(Path(tool.path).absolute()), False) for tool in spec.tools})
    if spec.broker_root is not None:
        expected_mounts['/broker'] = (str(Path(spec.broker_root).absolute()), False)
    environment = {'HOME=/home/workbench', 'LANG=C.UTF-8', 'LC_ALL=C.UTF-8',
                   'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'}
    if spec.broker_root is not None:
        environment.update({'HTTPS_PROXY=http://127.0.0.1:18080', 'HTTP_PROXY=http://127.0.0.1:18080',
                            'NO_PROXY=', 'SSL_CERT_FILE=/control/broker-ca.pem'})
    tmpfs = {'/home/workbench': f'rw,nosuid,nodev,size=33554432,uid={spec.uid},gid={spec.gid},mode=0700',
             '/tmp': f'rw,noexec,nosuid,nodev,size=67108864,uid={spec.uid},gid={spec.gid},mode=0700'}
    limits = {item.get('Name'): (item.get('Soft'), item.get('Hard')) for item in host.get('Ulimits') or []}
    mounts = {item.get('Destination'): (item.get('Source'), item.get('RW')) for item in inspect.get('Mounts', []) if item.get('Type') == 'bind'}
    if (inspect.get('Image') != IMAGE_ID or config.get('User') != f'{spec.uid}:{spec.gid}'
            or config.get('Entrypoint') not in (None, []) or config.get('Cmd') != ['/bin/sh', '/control/worker.sh']
            or config.get('WorkingDir') != '/job' or host.get('NetworkMode') != 'none'
            or set(config.get('Env') or []) != environment or len(config.get('Env') or []) != len(environment)
            or config.get('Tty') is not False or config.get('OpenStdin') is not False
            or host.get('IpcMode') != 'private' or host.get('PidMode') not in ('', None)
            or host.get('UTSMode') not in ('', None) or host.get('CgroupnsMode') != 'private'
            or host.get('Privileged') is not False or host.get('ReadonlyRootfs') is not True
            or host.get('PidsLimit') != PIDS or host.get('Memory') != MEMORY_BYTES
            or host.get('MemorySwap') != MEMORY_BYTES or host.get('NanoCpus') != 1000000000
            or host.get('LogConfig', {}).get('Type') != 'none'
            or host.get('Tmpfs') != tmpfs or limits != {'core': (0, 0), 'fsize': (268435456, 268435456), 'nofile': (256, 256)}
            or host.get('CapDrop') != ['ALL'] or host.get('CapAdd')
            or host.get('SecurityOpt') not in (['no-new-privileges'], ['no-new-privileges:true'])
            or host.get('RestartPolicy') != {'Name': 'no', 'MaximumRetryCount': 0}
            or mounts != expected_mounts or len(inspect.get('Mounts', [])) != len(expected_mounts)
            or any(item.get('Propagation') != 'rprivate' for item in inspect.get('Mounts', []))
            or host.get('Devices') or host.get('DeviceRequests') or host.get('DeviceCgroupRules')
            or host.get('Binds') or host.get('VolumesFrom')):
        _fail('worker_host_boundary_mismatch')


def _cleanup(docker, name, run_id, manifest_sha):
    current = _inspect(docker, name, 'cleanup-inspect')
    if current is None:
        return {'removed': True, 'already_absent': True}
    _owned(current, run_id, manifest_sha)
    if current.get('State', {}).get('Running'):
        killed = docker.run('kill', ['kill', '--signal', 'KILL', name])
        current = _inspect(docker, name, 'inspect-stopped')
        if current is None or current.get('State', {}).get('Running'):
            _fail('worker_host_container_stop_unconfirmed')
    removed = docker.run('remove', ['rm', '--force', name])
    if removed['code'] != 0 or _inspect(docker, name, 'inspect-removed') is not None:
        _fail('worker_host_container_removal_unconfirmed')
    return {'removed': True, 'stopped_state': current.get('State'), 'container_id': current.get('Id')}


def launch(spec, output):
    """Launch exact pinned control code in the bounded container; never approve it."""
    inputs = _validate(spec)
    target = Path(output).absolute()
    if target.exists() or any(path.is_symlink() for path in (target, *target.parents)) or not target.parent.is_dir():
        _fail('worker_host_fresh_output_required')
    roots = [Path(spec.source_root).absolute(), Path(spec.control_root).absolute(), Path(spec.job_root).absolute()]
    if any(target == root or target in root.parents or root in target.parents for root in roots):
        _fail('worker_host_output_overlap')
    target.mkdir(mode=0o700)
    run_id, name = uuid4().hex, 'intune-worker-' + uuid4().hex
    manifest = {'schema_version': VERSION, 'host_spec': asdict(spec), 'run_id': run_id,
                'container_name': name, 'image_reference': IMAGE, 'image_id': IMAGE_ID,
                'docker_sha256': DOCKER_SHA256, 'inputs': inputs}
    manifest_sha = digest(manifest)
    write_json(target / 'manifest.json', manifest)
    record = {'schema_version': VERSION, 'status': 'prepared', 'run_id': run_id,
              'manifest_sha256': manifest_sha, 'container_name': name,
              'execution_authorized': False, 'production_qualified': False,
              'evidence_class': 'native_local_docker_worker_boundary', 'container_exit_code': None}
    write_json(target / 'journal.json', record)
    docker = _Docker(spec, target)
    primary, cleanup_error = None, None
    try:
        version = docker.run('version', ['version', '--format', '{{json .}}'])
        if version['code'] != 0:
            _fail('worker_host_daemon_unavailable')
        versions = parse_json(version['stdout'])
        server = versions.get('Server', {})
        if (server.get('Version') != '28.4.0' or server.get('Os') != 'linux'
                or server.get('Arch') != 'amd64'):
            _fail('worker_host_daemon_unqualified')
        record['daemon_version'] = '28.4.0'
        image = docker.run('image-inspect', ['image', 'inspect', IMAGE])
        if image['code'] != 0:
            _fail('worker_host_image_unavailable')
        image_info = parse_json(image['stdout'])
        if len(image_info) != 1 or image_info[0].get('Id') != IMAGE_ID or IMAGE not in image_info[0].get('RepoDigests', []):
            _fail('worker_host_image_changed')
        record['status'] = 'creating'
        write_json(target / 'journal.json', record)
        created = docker.run('create', _creation(spec, name, run_id, manifest_sha))
        if created['code'] != 0:
            _fail('worker_host_create_failed')
        before = _inspect(docker, name, 'inspect-before')
        _boundary(before, spec, run_id, manifest_sha)
        record.update(status='running', container_id=before['Id'], boundary_before_verified=True)
        write_json(target / 'journal.json', record)
        started = docker.run('start', ['start', '--attach', name], timeout=spec.timeout_seconds, output_limit=spec.output_limit)
        after = _inspect(docker, name, 'inspect-after')
        _boundary(after, spec, run_id, manifest_sha)
        if after['State']['Running']:
            _fail('worker_host_container_exit_unconfirmed')
        record.update(container_exit_code=after['State']['ExitCode'], boundary_after_verified=True,
            status='complete' if started['code'] == 0 and after['State']['ExitCode'] == 0 else 'failed')
        if _validate(spec) != inputs:
            _fail('worker_host_input_changed')
    except BaseException as error:
        primary = error
        record.update(status='cancelled' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed',
                      primary_error=getattr(error, 'code', type(error).__name__))
    finally:
        handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            record['cleanup'] = _cleanup(docker, name, run_id, manifest_sha)
        except BaseException as error:
            cleanup_error = error
            record.update(status='cleanup_unconfirmed', cleanup_error=getattr(error, 'code', type(error).__name__))
        finally:
            signal.signal(signal.SIGINT, handler)
        record['commands'] = docker.commands
        write_json(target / 'journal.json', record)
        write_json(target / 'receipt.json', record)
    if isinstance(primary, (KeyboardInterrupt, SystemExit)):
        raise primary
    return {**record, 'receipt': str(target / 'receipt.json')}


def recover(output):
    """Only inspect/stop/remove the exact labeled container from a saved journal."""
    target = _path(output, directory=True, private=True)
    manifest = load_json(_path(target / 'manifest.json', private=True))
    journal = load_json(_path(target / 'journal.json', private=True))
    if (manifest.get('schema_version') != VERSION or digest(manifest) != journal.get('manifest_sha256')
            or manifest.get('run_id') != journal.get('run_id')
            or manifest.get('container_name') != journal.get('container_name')
            or not re.fullmatch('intune-worker-[0-9a-f]{32}', manifest.get('container_name', ''))):
        _fail('worker_host_recovery_changed')
    value = dict(manifest['host_spec'])
    value['tools'] = tuple(PinnedTool(**item) for item in value['tools'])
    spec = HostSpec(**value)
    docker = _Docker(spec, target)
    result = _cleanup(docker, manifest['container_name'], manifest['run_id'], journal['manifest_sha256'])
    recovery = {'schema_version': VERSION, 'status': 'recovered', 'cleanup': result,
                'previous_status': journal.get('status'), 'operation_outcome': 'unchanged_or_unknown',
                'commands': docker.commands, 'mutation_replayed': False}
    path = target / ('recovery-' + uuid4().hex + '.json')
    write_json(path, recovery)
    return {**recovery, 'receipt': str(path)}
