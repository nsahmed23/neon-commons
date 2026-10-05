"""Durable native configuration comparison for the connected wizard.

This is cooperative local evidence, not an authenticated append-only ledger and
never Entra authentication or execution authority. A same-user host attacker can
rewrite it; resume detects source/tool/evidence inconsistency within that scope.
"""
from pathlib import Path
import base64
import hashlib
import os
import re
import stat

from .io import AppError, digest, load_json, parse_json, read_bytes, write_json
from .native_atmos import ATMOS_SHA256, ATMOS_VERSION, expected_logical_stack, resolve_native_atmos
from .repository import resolve_component
from .native_pins import ATMOS_PINS

SECTIONS = ('vars', 'env', 'settings', 'providers')
HEX = re.compile(r'[0-9a-f]{64}\Z')

def _fail(code='journey_native_atmos_evidence_invalid'):
    raise AppError(code, 'Native Atmos evidence is missing, changed, or inconsistent; rerun the Atmos stage.')

def _implementation():
    root = Path(__file__).resolve().parent
    return {name: hashlib.sha256(read_bytes(root/name)).hexdigest()
            for name in ('journey_native_atmos.py', 'native_atmos.py', 'repository.py', 'protected.py', 'io.py', 'native_pins.py')}

def _tool(executable):
    path = Path(executable).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        _fail('unqualified_atmos_executable')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size not in {p['bytes'] for p in ATMOS_PINS.values()}:
                _fail('unqualified_atmos_executable')
            value = hashlib.file_digest(stream, 'sha256').hexdigest()
    except OSError:
        _fail('unqualified_atmos_executable')
    profile = ATMOS_PINS.get(value)
    if profile is None or info.st_size != profile['bytes']:
        _fail('unqualified_atmos_executable')
    return {'version': profile['version'], 'sha256': value}

def execute(root, stack, component, executable, receipt_path):
    _tool(executable)
    raw_path = Path(receipt_path).with_name(Path(receipt_path).name+'.stdout.json')
    report = resolve_native_atmos(root, stack, component, executable=executable,evidence_path=raw_path)
    if report.get('status') != 'verified' or report.get('native_executed') is not True:
        # Preserve mismatch/rejection evidence without claiming completion.
        write_json(receipt_path, {'schema':'journey-native-atmos/1', 'status':'blocked', 'report':report})
        _fail('journey_native_atmos_comparison_failed')
    evidence = {'schema':'journey-native-atmos/1', 'status':'verified', 'repository':str(Path(root).absolute()),
                'executable_path':str(Path(executable).absolute()),
                'stack':stack, 'component':component, 'implementation':_implementation(), 'report':report,
                'assurance':'cooperative_local_configuration_evidence_only'}
    evidence['evidence_sha256'] = digest(evidence)
    write_json(receipt_path, evidence)
    return reconstruct(root, stack, component, executable, receipt_path)

def reconstruct(root, stack, component, executable, receipt_path):
    tool = _tool(executable)
    try:
        evidence = load_json(receipt_path)
        expected = resolve_component(root, stack, component)
        if expected.get('status') != 'resolved' or expected.get('abstract'):
            _fail()
        wanted = {'schema','status','repository','executable_path','stack','component','implementation','report','assurance','evidence_sha256'}
        if type(evidence) is not dict or set(evidence) != wanted:
            _fail()
        document = {k:v for k,v in evidence.items() if k != 'evidence_sha256'}
        if evidence['evidence_sha256'] != digest(document):
            _fail()
        if (evidence['schema'] != 'journey-native-atmos/1' or evidence['status'] != 'verified'
            or evidence['repository'] != str(Path(root).absolute()) or evidence['stack'] != stack
            or evidence['executable_path'] != str(Path(executable).absolute())
            or evidence['component'] != component or evidence['implementation'] != _implementation()
            or evidence['assurance'] != 'cooperative_local_configuration_evidence_only'):
            _fail()
        report = evidence['report']
        if type(report) is not dict:
            _fail()
        raw_path = Path(receipt_path).with_name(Path(receipt_path).name+'.stdout.json')
        raw_evidence = load_json(raw_path)
        if (type(raw_evidence) is not dict or set(raw_evidence) !=
            {'schema','stdout_base64','stderr_base64','exit_code','output_truncated'}
            or raw_evidence.get('schema') != 'native-atmos-raw/1'):
            _fail()
        raw = base64.b64decode(raw_evidence['stdout_base64'],validate=True)
        stderr = base64.b64decode(raw_evidence['stderr_base64'],validate=True)
        native = parse_json(raw)
        if type(native) is not dict:
            _fail()
        if (hashlib.sha256(raw).hexdigest() != report.get('stdout_sha256')
            or hashlib.sha256(stderr).hexdigest() != report.get('stderr_sha256')
            or type(raw_evidence.get('exit_code')) is not int or raw_evidence['exit_code'] != 0
            or raw_evidence.get('output_truncated') is not False
            or digest(native) != report.get('native_configuration_sha256')
            or digest(native.get('workspace')) != report.get('workspace_sha256')
            or digest({'type':native.get('backend_type'),'config':native.get('backend')}) != report.get('backend_sha256')):
            _fail()
        comparisons = {k:True for k in (*SECTIONS, 'logical_stack', 'physical_manifest', 'implementation')}
        section_digests = {k:{'expected':digest(expected['effective'].get(k)),
                              'observed':digest(expected['effective'].get(k))} for k in SECTIONS}
        if (report.get('status') != 'verified' or report.get('native_executed') is not True
            or report.get('execution_authorized') is not False or report.get('tenant_authenticated') is not False
            or report.get('source_fingerprint') != expected['source_fingerprint'] or report.get('tool') != tool
            or report.get('logical_stack') != expected_logical_stack(root, expected)
            or report.get('physical_manifest') != stack or digest(report.get('comparisons')) != digest(comparisons)
            or report.get('comparison_sha256') != section_digests):
            _fail()
        if any(digest(native.get(k)) != section_digests[k]['expected'] for k in SECTIONS):
            _fail()
        if (native.get('atmos_stack') != expected_logical_stack(root, expected)
            or native.get('atmos_manifest') != stack or native.get('component') != expected['implementation']):
            _fail()
        for key in ('stdout_sha256','stderr_sha256','native_configuration_sha256','workspace_sha256','backend_sha256'):
            if type(report.get(key)) is not str or not HEX.fullmatch(report[key]):
                _fail()
        return {'status':'verified', 'native_executed':True, 'execution_authorized':False,
                'tenant_authenticated':False, 'source_fingerprint':expected['source_fingerprint'],
                'evidence_sha256':evidence['evidence_sha256'], 'tool':tool,
                'executable_path':evidence['executable_path'],
                'comparison_sha256':section_digests, 'stdout_sha256':report['stdout_sha256'],
                'stderr_sha256':report.get('stderr_sha256'),
                'assurance':'cooperative_local_configuration_evidence_only'}
    except (OSError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, AppError):
            raise
        _fail()
