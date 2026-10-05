#!/usr/bin/env python3
"""Exact native candidate init/schema/validation with IP network denied.

This does not configure credentials or call a tenant. Host AF_UNIX permission is
required for Terraform provider RPC. A failed prerequisite is evidence, never a
qualification pass. The binary-bearing work directory is outside this repository.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from intune_iac import provider_execution as pe
from intune_iac.io import AppError, digest, write_json


def _raw(path, data):
    """Private, exclusive lab artifact; never overwrite an earlier observation."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


class _Proxy:
    def __init__(self, original, **overrides):
        self._original = original; self._overrides = overrides
    def __getattr__(self, name):
        return self._overrides[name] if name in self._overrides else getattr(self._original, name)


@contextmanager
def observe_supervisor(log_directory, name, observation, *, provider_trace=False):
    """Lab-only tee of bytes already read by the unchanged runtime supervisor.

    This standalone harness is single-threaded. Proxies replace only the two
    module references inside provider_execution, never the global os/subprocess
    modules. The original Popen, read, guard, argv, environment, descriptors,
    limits and supervisor return/exception behavior are preserved.
    """
    if name not in ('init', 'schema', 'validate'): raise ValueError('unsupported smoke observation')
    if type(provider_trace) is not bool: raise ValueError('invalid diagnostic profile')
    original_supervise = pe._supervise
    def wrapped(*args, **kwargs):
        original_os, original_subprocess = pe.os, pe.subprocess
        streams = {}; buffers = {'stdout': bytearray(), 'stderr': bytearray()}
        process = None; result = None; error = None
        limit = kwargs.get('output_limit', pe.MAX_BYTES)
        def popen(*p_args, **p_kwargs):
            nonlocal process
            observation['environment_delta'] = {}
            if provider_trace:
                # The diagnostic profile is restricted to this no-credential
                # fixture. It never changes runtime credential admission.
                allowed = {'PATH','HOME','TF_CLI_CONFIG_FILE','TF_IN_AUTOMATION',
                           'CHECKPOINT_DISABLE','TF_INPUT','M365_TELEMETRY_OPTOUT','M365_DEBUG_MODE'}
                env = p_kwargs.get('env')
                if type(env) is not dict or set(env) - allowed:
                    raise AppError('lab_trace_environment_rejected', 'Diagnostic trace requires the fixed no-credential fixture.')
                p_kwargs = dict(p_kwargs, env={**env, 'TF_LOG_PROVIDER': 'TRACE'})
                observation['environment_delta'] = {'TF_LOG_PROVIDER':'TRACE'}
            process = original_subprocess.Popen(*p_args, **p_kwargs)
            streams[process.stdout.fileno()] = 'stdout'; streams[process.stderr.fileno()] = 'stderr'
            observation['argv'] = list(p_args[0] if p_args else p_kwargs['args'])
            observation['cwd'] = str(p_kwargs.get('cwd'))
            observation['executable'] = p_kwargs.get('executable')
            observation['pass_fds'] = list(p_kwargs.get('pass_fds', ()))
            return process
        def read(fd, length):
            data = original_os.read(fd, length)
            if fd in streams:
                remaining = max(0, limit - sum(len(b) for b in buffers.values()))
                buffers[streams[fd]].extend(data[:remaining])
                if len(data) > remaining: observation['capture_truncated'] = True
            return data
        pe.os = _Proxy(original_os, read=read)
        pe.subprocess = _Proxy(original_subprocess, Popen=popen)
        try:
            result = original_supervise(*args, **kwargs)
            return result
        except BaseException as exc:
            error = {'type': type(exc).__name__, 'code': getattr(exc, 'code', None)}
            raise
        finally:
            pe.os, pe.subprocess = original_os, original_subprocess
            observation.update(exit_code=(result['code'] if result is not None else process.returncode if process is not None else None),
                               supervisor_error=error, capture_limit_bytes=limit)
            observation.setdefault('capture_truncated', False)
            observation['capture_complete'] = error is None and not observation['capture_truncated']
            observation['return_stdout_matches_capture'] = (result['stdout'] == bytes(buffers['stdout']) if result is not None else None)
            for channel, data in buffers.items():
                path = log_directory / (name + '.' + channel)
                _raw(path, data)
                observation[channel] = {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    pe._supervise = wrapped
    try:
        yield
    finally:
        pe._supervise = original_supervise


def unix_socket_eperm(stdout, stderr):
    """Require a Unix-socket operation and EPERM within one observed diagnostic."""
    # OpenTofu may encode provider stderr inside a JSON diagnostic string.
    # Decode JSON string leaves to inspect the actual diagnostic, not escaped
    # presentation. This never executes or interprets commands in the text.
    texts = []
    for data in (stdout, stderr):
        text = data.decode('utf-8', errors='replace'); texts.append(text)
        try: pending = [json.loads(text)]
        except (ValueError, TypeError, RecursionError): continue
        while pending:
            item = pending.pop()
            if isinstance(item, str): texts.append(item)
            elif isinstance(item, dict): pending.extend(item.values())
            elif isinstance(item, list): pending.extend(item)
    pattern = re.compile(r'\b(?:listen|dial)\s+unix(?:packet)?\s+[^\r\n]{1,512}:\s*(?:socket|bind|connect|listen):\s*operation not permitted\b', re.IGNORECASE)
    return any(pattern.search(text) is not None for text in texts)


def classify_failure(name, code, observation):
    supported = False
    if (name in ('schema', 'validate') and code == 'provider_command_failed' and
            observation.get('capture_complete') is True and observation.get('exit_code') not in (None, 0)):
        supported = unix_socket_eperm(Path(observation['stdout']['path']).read_bytes(),
                                      Path(observation['stderr']['path']).read_bytes())
    return {'status': 'blocked' if supported else 'failed', 'code': code,
            'restriction_evidence': 'observed_unix_socket_eperm' if supported else 'not_substantiated_by_command_output'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tofu', required=True); parser.add_argument('--provider', required=True)
    parser.add_argument('--work', required=True); parser.add_argument('--receipt', required=True)
    parser.add_argument('--provider-trace', action='store_true',
                        help='Lab-only no-credential diagnostic profile: add only TF_LOG_PROVIDER=TRACE; keep private bounded logs.')
    args = parser.parse_args()
    log_directory = pe._safe(Path(args.receipt).with_suffix('.logs'))
    log_directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    fixture_root = ROOT / 'labs/provider-contract/synthetic-rpc'
    configuration = json.loads((fixture_root / 'main.tf.json.txt').read_text())['resource'][pe.RESOURCE]['fixture']
    object_id = json.loads((fixture_root / 'fixture.json').read_text())['id']
    report = {'version': 'provider-native-smoke/1.1', 'evidence_kind': 'native_tool',
              'production_qualified': False, 'live_service_qualified': False,
              'production_configure_qualified': False, 'resource_lifecycle_qualified': False,
              'network': 'AF_UNIX only; all IP sockets denied by inherited adapter seccomp',
              'commands': {}, 'pins': pe.asdict(pe.PRODUCTION_PINS), 'harness_sha256': pe._sha(Path(__file__)),
              'adapter_sha256': pe._sha(Path(pe.__file__)), 'implementation_files': pe._implementation(),
              'instrumentation': {'scope': 'lab harness only; no runtime source change',
                  'mechanism': 'module-local proxies tee original supervisor reads and record original Popen descriptors; dispatch/guard/return behavior unchanged',
                  'fixture_credentials': 'none', 'raw_output_limit_bytes': pe.MAX_BYTES,
                  'diagnostic_profile': 'provider_trace_no_credentials' if args.provider_trace else 'default',
                  'environment_delta': {'TF_LOG_PROVIDER':'TRACE'} if args.provider_trace else {}}}
    try:
        probe = socket.socket(socket.AF_UNIX); probe.close(); report['host_unix_socket'] = 'available'
    except OSError as exc:
        report['host_unix_socket'] = {'status': 'blocked', 'errno': exc.errno}
    executor = pe.create_provider_executor(args.work, tofu=args.tofu, provider=args.provider,
        initial_configuration=configuration, admitted_configuration=configuration, object_id=object_id,
        source_sha256=digest({'fixture': 'existing immutable source IDs'}),
        admission_sha256=digest({'scope': 'schema-validation-only'}), target_sha256=digest({'target': 'no-tenant'}))
    for name in ('init', 'schema', 'validate'):
        observation = {}
        try:
            with observe_supervisor(log_directory, name, observation, provider_trace=args.provider_trace):
                output = executor._run(name)
            if name == 'schema':
                selected = output['provider_schemas'][pe.SOURCE]['resource_schemas'][pe.RESOURCE]
                if digest(selected) != pe.PRODUCTION_PINS.selected_schema_sha256:
                    raise AppError('provider_schema_pin_mismatch', 'Selected schema differs.')
            if name == 'validate' and output.get('valid') is not True:
                raise AppError('provider_configuration_invalid', 'Configuration rejected.')
            report['commands'][name] = {'status': 'passed', 'output_sha256': digest(output)}
        except AppError as exc:
            report['commands'][name] = classify_failure(name, exc.code, observation)
        report['commands'][name]['observation'] = observation
    report['schema_validation_qualified'] = all(row['status'] == 'passed' for row in report['commands'].values())
    report['status'] = ('native-schema-validation-passed' if report['schema_validation_qualified']
                        else 'native-schema-validation-failed' if any(row['status'] == 'failed' for row in report['commands'].values())
                        else 'native-prerequisite-blocked')
    report['provider_lock_sha256'] = pe._sha(executor.work / '.terraform.lock.hcl') if (executor.work / '.terraform.lock.hcl').exists() else None
    write_json(args.receipt, report)
    print(json.dumps(report, indent=2))
    return 0 if report['schema_validation_qualified'] else 1

if __name__ == '__main__': raise SystemExit(main())
