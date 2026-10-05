"""Pinned, network-denied native comparison for the inert Atmos subset.

Configuration identity is observed here. Tenant authentication is never inferred
from Atmos labels. Arbitrary runtime layers, hooks and dynamic functions remain
unsupported; rejected repositories are never handed to the native executable.
"""
from __future__ import annotations

import hashlib
import base64
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

import yaml

from .io import AppError, digest, parse_json, read_bytes, write_json
from .repository import (resolve_component, _Repository, _Blocked, _empty,
                         _check_keys, _mapping, _literal_path)

from .native_pins import ATMOS_CURRENT_SHA256, ATMOS_PINS
ATMOS_SHA256=ATMOS_CURRENT_SHA256
ATMOS_VERSION=ATMOS_PINS[ATMOS_SHA256]['version']
_SELECTOR=re.compile(r'[A-Za-z0-9][A-Za-z0-9_./-]{0,255}\Z')
_GUARD=r'''import ctypes,os,resource,sys
def limit(kind,ceiling):
 hard=resource.getrlimit(kind)[1]
 if hard!=resource.RLIM_INFINITY:ceiling=min(ceiling,hard)
 resource.setrlimit(kind,(ceiling,ceiling))
limit(resource.RLIMIT_CPU,40)
limit(resource.RLIMIT_AS,4*1024**3)
limit(resource.RLIMIT_CORE,0)
limit(resource.RLIMIT_FSIZE,32*1024**2)
lib=ctypes.CDLL('libseccomp.so.2',use_errno=True)
lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_release.argtypes=[ctypes.c_void_p]
ctx=lib.seccomp_init(0x7fff0000)
if not ctx:sys.exit(91)
for name in (b'socket',b'socketpair',b'connect'):
 n=lib.seccomp_syscall_resolve_name(name)
 if n<0 or lib.seccomp_rule_add(ctx,0x00050001,n,0)!=0:sys.exit(92)
if lib.seccomp_load(ctx)!=0:sys.exit(93)
lib.seccomp_release(ctx);os.umask(0o077)
os.execve(sys.argv[1],sys.argv[1:],dict(os.environ))
'''


def _fail(code):
    raise AppError(code,'Native Atmos context could not be verified.')


def _admit_all_sources(root):
    """Admit the entire staged stack tree, including excluded/import-only files.

    Selection-level resolution alone does not constrain native discovery, which
    can parse unrelated manifests. Reuse the bounded inert parser but require
    each manifest and every component to satisfy its contract before dispatch.
    """
    repository = _Repository(root)
    if repository.blockers:
        return False
    try:
        paths = [repository.root / name for name in repository.sources
                 if (repository.root / name).is_relative_to(repository.stack_base)
                 and name.endswith(('.yaml', '.yml', '.yaml.tmpl', '.yml.tmpl'))]
        for path in paths:
            doc = repository.manifest(path)
            components = doc.value.get('components', _empty())
            _check_keys(components, {'terraform', 'helmfile'}, 'unsupported_component_kind')
            for kind in ('terraform', 'helmfile'):
                scope = doc.value.get(kind, _empty())
                _check_keys(scope, {'vars', 'env', 'settings', 'command'} |
                            ({'providers'} if kind == 'terraform' else set()),
                            'unsupported_type_global_field')
                repository._direct_sections(doc, kind)
                repository._direct_sections(scope, kind)
            selector = path.relative_to(repository.stack_base).as_posix()
            selector = re.sub(r'\.(?:yaml|yml)$', '', selector)
            repository.selected[selector] = path
            for kind, entries in components.value.items():
                for name in _mapping(entries):
                    if not _literal_path(name) or repository.resolve(selector, name)['status'] != 'resolved':
                        return False
        return True
    except (_Blocked, OSError, ValueError, RecursionError):
        return False


def expected_logical_stack(root, resolution):
    """Independent bounded name_pattern model; no Entra mapping is implied."""
    config=yaml.safe_load(read_bytes(Path(root)/'atmos.yaml'))
    pattern=config.get('stacks',{}).get('name_pattern')
    if not isinstance(pattern,str) or not pattern or len(pattern)>256:
        _fail('unsupported_stack_name_pattern')
    variables=resolution.get('effective',{}).get('vars',{})
    def replace(match):
        key=match.group(1);value=variables.get(key)
        if key not in {'namespace','tenant','environment','stage'} or not isinstance(value,str) or not _SELECTOR.fullmatch(value) or '/' in value:
            _fail('unresolved_logical_stack')
        return value
    result=re.sub(r'\{([a-z_]+)\}',replace,pattern)
    if not _SELECTOR.fullmatch(result) or '/' in result or '{' in result or '}' in result:
        _fail('unsupported_stack_name_pattern')
    return result


def resolve_native_atmos(root,stack,component,*,executable,evidence_path=None):
    """Read/compare configuration via exact Atmos Linux AMD64 pin.

    Public output contains digests and structural labels, never effective values.
    The temporary snapshot contains only independently admitted source files.
    """
    report={'schema_version':'native-atmos/1','status':'blocked','native_executed':False,
            'execution_authorized':False,'tenant_authenticated':False,
            'assurance':'native_configuration_only','blockers':[]}
    if not all(isinstance(x,str) and _SELECTOR.fullmatch(x) and '..' not in Path(x).parts for x in (stack,component)):
        report['blockers']=['invalid_selector'];return report
    root=Path(root).absolute();expected=resolve_component(root,stack,component)
    if expected['status']!='resolved' or expected.get('abstract') or not _admit_all_sources(root):
        report['blockers']=['repository_outside_inert_profile'];return report
    if sys.platform!='linux' or os.uname().machine!='x86_64':_fail('native_atmos_platform_unavailable')
    logical=expected_logical_stack(root,expected)
    binary=Path(executable).absolute()
    if any(p.is_symlink() for p in (binary,*binary.parents)):_fail('unqualified_atmos_executable')
    fd=os.open(binary,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size not in {p['bytes'] for p in ATMOS_PINS.values()}:_fail('unqualified_atmos_executable')
        h=hashlib.sha256()
        while data:=os.read(fd,1024*1024):h.update(data)
        tool_sha=h.hexdigest();profile=ATMOS_PINS.get(tool_sha)
        if profile is None or info.st_size != profile['bytes']:_fail('unqualified_atmos_executable')
        from .protected import _supervise
        with tempfile.TemporaryDirectory(prefix='intune-atmos-') as temporary:
            base=Path(temporary);snapshot=base/'repo';snapshot.mkdir();home=base/'home';home.mkdir()
            for source in expected['sources']:
                data=read_bytes(root/source['path'])
                if hashlib.sha256(data).hexdigest()!=source['sha256']:_fail('repository_changed')
                path=snapshot/source['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            env={'HOME':str(home),'XDG_CONFIG_HOME':str(home),'XDG_CACHE_HOME':str(home),
                 'PATH':str(home),'TMPDIR':str(home),'LANG':'C','LC_ALL':'C','GOMAXPROCS':'2',
                 'ATMOS_CLI_CONFIG_PATH':str(snapshot),'ATMOS_VERSION_CHECK_ENABLED':'false',
                 'ATMOS_TELEMETRY_ENABLED':'false','CHECKPOINT_DISABLE':'1'}
            args=['describe','component',component,'--stack',logical,'--format','json',
                  '--process-functions=false','--process-templates=false','--mask=false','--logs-level','Off']
            if profile['version']=='1.230.1':
                env['ATMOS_DESCRIBE_COMPONENT_FILTER']='full'
                args.extend(['--provenance=false','--error-mode','strict'])
            trace={}
            try:
                raw=_supervise([sys.executable,'-I','-S','-c',_GUARD,f'/proc/self/fd/{fd}',*args],
                               cwd=snapshot,env=env,pass_fds=(fd,),timeout=45,evidence=trace)
            finally:
                if evidence_path is not None and trace:
                    write_json(evidence_path, {'schema':'native-atmos-raw/1',
                        'stdout_base64':base64.b64encode(trace['stdout_bytes']).decode('ascii'),
                        'stderr_base64':base64.b64encode(trace['stderr_bytes']).decode('ascii'),
                        'exit_code':trace['exit_code'],'output_truncated':trace['output_truncated']})
            native=parse_json(raw)
            if not isinstance(native,dict):_fail('invalid_native_context')
            comparisons={key:digest(native.get(key))==digest(expected['effective'].get(key)) for key in ('vars','env','settings','providers')}
            comparisons.update(logical_stack=native.get('atmos_stack')==logical,
                               physical_manifest=native.get('atmos_manifest')==stack,
                               implementation=native.get('component')==expected['implementation'])
            if resolve_component(root,stack,component)['source_fingerprint']!=expected['source_fingerprint']:_fail('repository_changed')
            report.update(native_executed=True,status='verified' if all(comparisons.values()) else 'mismatch',
                comparisons=comparisons,source_fingerprint=expected['source_fingerprint'],
                comparison_sha256={key:{'expected':digest(expected['effective'].get(key)),
                                        'observed':digest(native.get(key))}
                                   for key in ('vars','env','settings','providers')},
                stdout_sha256=hashlib.sha256(raw).hexdigest(),
                stderr_sha256=hashlib.sha256(trace['stderr_bytes']).hexdigest(),
                native_argv=args,executable_path=str(binary),
                native_configuration_sha256=digest(native),tool={'version':profile['version'],'sha256':tool_sha},toolchain_profile=profile['profile'],
                logical_stack=logical,physical_manifest=stack,
                workspace_sha256=digest(native.get('workspace')),
                backend_sha256=digest({'type':native.get('backend_type'),'config':native.get('backend')}),
                restrictions=['inert literal repository subset','no ambient runtime configuration','no tenant or backend authentication',
                              'Linux AMD64 and libseccomp','no filesystem isolation from trusted process owner'],
                network_denied_syscalls=['socket','socketpair','connect'])
            return report
    finally:os.close(fd)
