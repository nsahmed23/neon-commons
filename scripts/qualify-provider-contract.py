#!/usr/bin/env python3
"""Exercise pinned, unchanged provider source with an in-memory HTTP transport.

This is characterization, not provider/service qualification. Dependency acquisition
is separate; this runner disables module downloads and never accepts cloud tokens.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'labs' / 'provider-contract'
MAX_SOURCE = 4 * 1024 * 1024
MAX_LOG = 4 * 1024 * 1024
GO_SHA256 = "d9a2fa19c7ef8b57f420012c21f49f235c46f08a68c12077d9c753dbb6ccdc34"
GO_PROFILES = {
    "current": ("1.26.8", GO_SHA256),
    "legacy-1.25.8": ("1.25.8", "46a07f77bf5b080799416d80759feadd8edecc21c26aad81bbcdbc3b4d865f7c"),
}


def verify_go(path, profile="current"):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("invalid Go executable")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if profile not in GO_PROFILES or digest != GO_PROFILES[profile][1]:
        raise ValueError("Go executable differs from the explicitly pinned toolchain profile")
    return digest


def verify_sources(root, records):
    root = Path(root).resolve(strict=True)
    observed = []
    seen = set()
    for row in records:
        name = row['path']
        rel = PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or str(rel) != name or name in seen:
            raise ValueError('unsafe or duplicate source path')
        seen.add(name)
        p = root
        for part in rel.parts:
            p = p / part
            if p.is_symlink():
                raise ValueError('symlink in source path')
        if not p.is_file() or p.stat().st_size > MAX_SOURCE:
            raise ValueError('source absent or too large')
        data = p.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != row['sha256']:
            raise ValueError('source hash mismatch: ' + name)
        observed.append({'path':name, 'sha256':digest, 'size_bytes':len(data)})
    return observed


def apply_patch_candidate(work, data, original_sha256, candidate_sha256):
    target = Path(work) / "internal/services/common/custom_requests/get_request.go"
    if hashlib.sha256(target.read_bytes()).hexdigest() != original_sha256:
        raise ValueError("patch base source mismatch")
    if hashlib.sha256(data).hexdigest() != candidate_sha256:
        raise ValueError("patch candidate source mismatch")
    target.write_bytes(data)


def apply_completion_candidate(work, candidate, records):
    """Validate every original/candidate before applying an exact local patch set."""
    work, candidate = Path(work), Path(candidate)
    staged, seen = [], set()
    for row in records:
        name = row['path']
        rel = PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or str(rel) != name or name in seen:
            raise ValueError('unsafe or duplicate completion source path')
        seen.add(name)
        paths = []
        for root in (work, candidate):
            target = root
            for part in rel.parts:
                target = target / part
                if target.is_symlink():
                    raise ValueError('symlink in completion source path')
            paths.append(target)
        target, source = paths
        original = row['original_sha256']
        if original is None:
            if target.exists():
                raise ValueError('completion addition already exists')
        elif not target.is_file() or target.stat().st_size > MAX_SOURCE or hashlib.sha256(target.read_bytes()).hexdigest() != original:
            raise ValueError('completion patch base source mismatch')
        if not source.is_file() or source.stat().st_size > MAX_SOURCE:
            raise ValueError('completion candidate absent or too large')
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != row['candidate_sha256']:
            raise ValueError('completion candidate source mismatch')
        staged.append((target, data))
    for target, data in staged:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def summarize_go_tests(output, returncode):
    passed, failed, skipped, running = set(), set(), set(), set()
    package_pass = False
    malformed = False
    for line in output.splitlines():
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError('event must be object')
        except (ValueError, TypeError):
            malformed = True
            continue
        action, test = event.get('Action'), event.get('Test')
        if test:
            if action == 'run': running.add(test)
            if action == 'pass': passed.add(test)
            if action == 'fail': failed.add(test)
            if action == 'skip': skipped.add(test)
        elif action == 'pass':
            package_pass = True
    complete = running == passed and bool(passed)
    ok = returncode == 0 and package_pass and complete and not (failed or skipped or malformed)
    return {'status':'passed-characterization' if ok else 'failed',
            'returncode':returncode, 'tests_passed':sorted(passed),
            'tests_failed':sorted(failed), 'tests_skipped':sorted(skipped),
            'tests_top_level_passed':sorted(t for t in passed if '/' not in t),
            'tests_top_level_failed':sorted(t for t in failed if '/' not in t),
            'incomplete_tests':sorted(running - passed - failed - skipped),
            'malformed_event_output':malformed, 'production_qualified':False}


def run_logged(command, cwd, env, output, timeout=600):
    """Bounded, deadline-enforced process output; no shell execution."""
    import selectors
    proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    streams = {'stdout':bytearray(), 'stderr':bytearray()}
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ, 'stdout')
    selector.register(proc.stderr, selectors.EVENT_READ, 'stderr')
    deadline = time.monotonic() + timeout
    try:
        while selector.get_map():
            if time.monotonic() >= deadline:
                raise TimeoutError(f'Go execution exceeded {timeout} seconds')
            for key, _ in selector.select(0.2):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                streams[key.data].extend(data)
                if sum(map(len, streams.values())) > MAX_LOG:
                    raise ValueError('Go characterization log bound exceeded')
        code = proc.wait(timeout=5)
    finally:
        # Descendants can retain our pipes after the session leader has exited.
        # Clean up the owned group even when poll() would report a finished leader.
        try:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)
        finally:
            selector.close()
            proc.stdout.close()
            proc.stderr.close()
            for stream, data in streams.items():
                (output / ('go-test.' + stream)).write_bytes(data)
    return code, bytes(streams['stdout']).decode('utf-8', errors='strict')


def qualify(args):
    source = Path(args.upstream).resolve(strict=True)
    go = Path(args.go).resolve(strict=True)
    cache = Path(args.module_cache).resolve(strict=True)
    output = Path(args.output).absolute()
    for protected in (source, ROOT, cache):
        if output.resolve().is_relative_to(protected):
            raise ValueError('output must be outside source, plugin and module cache')
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    receipt = {'status':'started', 'production_qualified':False,
               'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'scope':'unchanged selected provider source; synthetic in-memory HTTP responses'}
    result_path = output / 'result.json'
    result_path.write_text(json.dumps(receipt, indent=2) + '\n')
    try:
        manifest = json.loads((LAB / 'source-manifest.json').read_text())
        completion_profile = getattr(args, 'completion_profile', 'none')
        full_build = getattr(args, 'full_build', False)
        inprocess_lifecycle = getattr(args, 'inprocess_lifecycle', False)
        if inprocess_lifecycle and (full_build or completion_profile != 'patched'):
            raise ValueError('in-process lifecycle requires the patched completion profile, separately from full build')
        if completion_profile != 'none':
            if args.schema or args.with_sdk or args.patch_profile != 'none':
                raise ValueError('completion profile must run separately')
            completion = json.loads((LAB / 'completion-manifest.json').read_text())
            extra = [{'path':r['path'], 'sha256':r['original_sha256']}
                     for r in completion['files'] if r['original_sha256'] is not None]
            sources = {r['path']:r for r in manifest['files'] + extra}
            manifest['files'] = list(sources.values())
        if full_build or inprocess_lifecycle:
            if completion_profile == 'none':
                raise ValueError('full build requires an explicit completion profile')
            full = json.loads((LAB / 'full-source-manifest.json').read_text())
            manifest['files'] = full['files']
        receipt['sources'] = verify_sources(source, manifest['files'])
        if args.schema:
            if args.with_sdk or args.patch_profile != 'none':
                raise ValueError('extracted Schema profile must run separately')
            schema_manifest = json.loads((LAB / 'schema-source-manifest.json').read_text())
            extra = verify_sources(source, schema_manifest['files'])
            by_path = {row['path']:row for row in receipt['sources'] + extra}
            receipt['sources'] = list(by_path.values())
        receipt['provider_commit'] = manifest['provider_commit']
        work = output / 'module'
        work.mkdir()
        for row in receipt['sources']:
            target = work / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            data = (source / row['path']).read_bytes()
            if hashlib.sha256(data).hexdigest() != row['sha256']:
                raise ValueError('source changed while staging')
            target.write_bytes(data)
        test = (LAB / 'contract_test.go').read_bytes()
        (work / 'contract_test.go').write_bytes(test)
        receipt['test_sha256'] = hashlib.sha256(test).hexdigest()
        receipt['profile'] = 'core-and-sdk' if args.with_sdk else 'core'
        if args.patch_profile != 'none':
            if args.with_sdk:
                raise ValueError('SDK characterization and paging repair profiles are separate')
            regression = (LAB / 'patch_contract_test.go').read_bytes()
            (work / 'patch_contract_test.go').write_bytes(regression)
            receipt['patch_test_sha256'] = hashlib.sha256(regression).hexdigest()
            receipt['profile'] = 'paging-regressions-' + args.patch_profile
            if args.patch_profile == 'patched':
                patch_info = json.loads((LAB / 'patch-manifest.json').read_text())
                candidate = (LAB / 'patched/get_request.go').read_bytes()
                apply_patch_candidate(work, candidate, patch_info['original_sha256'], patch_info['candidate_sha256'])
                receipt['patch'] = patch_info
                receipt['scope'] = 'Locally modified custom GET helper with unchanged dependencies; synthetic in-memory HTTP responses'
        if args.with_sdk:
            sdk_test = (LAB / 'sdk_contract_test.go').read_bytes()
            (work / 'sdk_contract_test.go').write_bytes(sdk_test)
            receipt['sdk_test_sha256'] = hashlib.sha256(sdk_test).hexdigest()
        if completion_profile != 'none':
            for name in ('sdk_contract_test.go', 'completion_contract_test.go', 'completion_paging_test.go'):
                data = (LAB / name).read_bytes()
                (work / name).write_bytes(data)
                receipt[name + '_sha256'] = hashlib.sha256(data).hexdigest()
            adapter_name = 'completion_api_' + completion_profile + '_test.go'
            adapter_source = (LAB / adapter_name).read_bytes()
            (work / adapter_name).write_bytes(adapter_source)
            receipt['completion_entrypoint_adapter_sha256'] = hashlib.sha256(adapter_source).hexdigest()
            receipt['completion_patch'] = completion
            receipt['profile'] = 'completion-' + completion_profile
            if completion_profile == 'patched':
                apply_completion_candidate(work, LAB / 'completion', completion['files'])
                assignment_test = (LAB / 'completion_assignment_state_test.go').read_bytes()
                (work / 'completion_assignment_state_test.go').write_bytes(assignment_test)
                receipt['assignment_state_test_sha256'] = hashlib.sha256(assignment_test).hexdigest()
            receipt['scope'] = 'Actual selected provider source and real SDK/adapter; synthetic in-memory requests, not resource lifecycle'
        toolchain_profile = getattr(args, 'toolchain_profile', 'current')
        receipt['go_sha256'] = verify_go(go, toolchain_profile)
        receipt['go_toolchain_profile'] = toolchain_profile
        receipt['legacy_toolchain_reproduction_only'] = toolchain_profile != 'current'
        env = {'PATH':str(go.parent) + ':/usr/bin:/bin', 'GOENV':'off', 'GOPATH':str(output / 'go-path'),
               'GOMODCACHE':str(cache), 'GOCACHE':str(Path(args.build_cache).resolve(strict=True) if args.build_cache else output / 'build-cache'),
               'GOTOOLCHAIN':'local', 'GOPROXY':'off', 'GOSUMDB':'off',
               'GOTELEMETRY':'off', 'CGO_ENABLED':'0', 'GOMAXPROCS':'1',
               'GOGC':'20', 'GOMEMLIMIT':'5GiB'}
        version = subprocess.run([str(go),'version'],env=env,capture_output=True,
                                 text=True,check=True,timeout=10).stdout.strip()
        if version != 'go version go' + GO_PROFILES[toolchain_profile][0] + ' linux/amd64':
            raise ValueError('requires the pinned Linux amd64 Go version for this profile')
        receipt['go_version'] = version
        if args.schema:
            extractor_source = (LAB / 'schema/extract.go').read_bytes()
            extractor = output / 'extract.go'
            extractor.write_bytes(extractor_source)
            executable = output / 'extract-schema'
            subprocess.run([str(go),'build','-o',str(executable),str(extractor)],
                           env=env,cwd=output,check=True,capture_output=True,timeout=60)
            resource_path = work / 'internal/services/resources/device_management/graph_beta/settings_catalog_configuration_policy_json/resource.go'
            extraction = subprocess.run([str(executable),str(resource_path),str(work / 'extracted_schema.go')],
                                         env=env,check=True,capture_output=True,text=True,timeout=10)
            receipt['schema_extraction'] = json.loads(extraction.stdout)
            receipt['extractor_sha256'] = hashlib.sha256(extractor_source).hexdigest()
            schema_test = (LAB / 'schema/schema_contract_test.go').read_bytes()
            (work / 'schema_contract_test.go').write_bytes(schema_test)
            receipt['schema_test_sha256'] = hashlib.sha256(schema_test).hexdigest()
            receipt['profile'] = 'AST-extracted-Schema'
            receipt['scope'] = 'Exact upstream Schema method bytes with minimal inert receiver and unchanged helpers; no full provider resource'
        command = [str(go),'test','-json','-count=1','-p=1','-timeout=90s','-mod=readonly','.']
        if completion_profile != 'none':
            command.insert(-1, '-run=^TestCompletion')
        if args.schema:
            command.insert(-1, '-run=^TestSchema')
        if args.patch_profile != 'none':
            command.insert(-1, '-run=^TestPatch')
        receipt['staged_sources'] = [{'path':row['path'],'sha256':hashlib.sha256((work / row['path']).read_bytes()).hexdigest()}
                                     for row in receipt['sources']]
        if full_build:
            # Root helper tests use package contract; they do not belong beside
            # the actual provider main package in a full-source build.
            for harness_name in ('contract_test.go', 'sdk_contract_test.go', 'completion_contract_test.go', 'completion_paging_test.go', 'completion_assignment_state_test.go', 'completion_api_original_test.go', 'completion_api_patched_test.go'):
                (work / harness_name).unlink(missing_ok=True)
            workers = getattr(args, 'native_build_workers', 1)
            command = [str(go), 'build', '-buildvcs=false', '-p=' + str(workers), '-mod=readonly', '-o', str(output / 'terraform-provider-microsoft365'), '.']
            # Test harness files are not included in go build. This compiles the
            # complete source inventory, including the real resource and client.
            receipt['profile'] = 'native-full-build-' + completion_profile
            receipt['scope'] = 'Complete pinned provider source plus explicit candidate patch; native build only'
        if inprocess_lifecycle:
            # Import the actual resource, not an extracted method. No socket or
            # provider authentication is involved in the authored transport.
            for harness_name in ('contract_test.go', 'sdk_contract_test.go', 'completion_contract_test.go', 'completion_paging_test.go', 'completion_assignment_state_test.go', 'completion_api_original_test.go', 'completion_api_patched_test.go'):
                (work / harness_name).unlink(missing_ok=True)
            harness = work / 'internal' / 'epoch_lifecycle'
            harness.mkdir()
            receipt['lifecycle_inputs'] = []
            for name in ('lifecycle_test.go', 'fixture.json'):
                data = (LAB / 'inprocess-lifecycle' / name).read_bytes()
                (harness / name).write_bytes(data)
                receipt['lifecycle_inputs'].append({'path': name, 'sha256': hashlib.sha256(data).hexdigest()})
            receipt['unused_helper_template_sha256'] = receipt['test_sha256']
            receipt['test_sha256'] = receipt['lifecycle_inputs'][0]['sha256']
            command = [str(go), 'test', '-json', '-count=1', '-p=1', '-timeout=60s', '-mod=readonly', './internal/epoch_lifecycle']
            env['GOMEMLIMIT'] = '5GiB'
            receipt['profile'] = 'actual-resource-inprocess-lifecycle'
            receipt['scope'] = 'Real patched resource Configure/Schema/Import/Read/Create/Update/Delete; injected stateful HTTP transport, no provider RPC or live service'
        receipt['command'] = command
        code, log = run_logged(command, work, env, output, 1800 if (full_build or inprocess_lifecycle) else 600)
        if full_build:
            binary = output / 'terraform-provider-microsoft365'
            receipt.update(status='passed-native-build' if code == 0 and binary.is_file() else 'failed', returncode=code)
            if binary.is_file():
                receipt['binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
            receipt['resource_lifecycle_qualified'] = False
        else:
            receipt.update(summarize_go_tests(log, code))
        receipt['boundaries'] = [('Native binary build only; schema RPC and lifecycle require separate execution' if full_build else
                                  'Not the full provider binary or schema RPC'),
                                 'No cloud or authenticated identity',
                                 'No assignment service replacement/merge evidence',
                                 ('Candidate source only; registry release unchanged' if completion_profile == 'patched' else
                                  'Passing tests characterize the local patch only' if args.patch_profile == 'patched' else
                                  'Exact extracted Schema only; lifecycle and full resource are absent' if args.schema else
                                  'Passing baseline tests reproduce known hazards; original provider unchanged')]
        if inprocess_lifecycle:
            receipt['boundaries'] = ['Not full provider RPC, provider authentication or live Graph behavior',
                                     'Stateful fixture behavior is authored; no Azure backend or approval qualification',
                                     'Repeated resource Read equality is not a second OpenTofu plan']
            if receipt['status'] == 'passed-characterization':
                receipt['status'] = 'passed-inprocess-lifecycle'
    except Exception as exc:
        receipt.update(status='failed',error=type(exc).__name__ + ': ' + str(exc))
    receipt['artifacts'] = [{'path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                            for p in sorted(output.glob('go-test.*'))]
    result_path.write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream',required=True)
    parser.add_argument('--go',required=True)
    parser.add_argument('--toolchain-profile', choices=tuple(GO_PROFILES), default='current',
                        help='current pinned toolchain; legacy is offline historical reproduction only')
    parser.add_argument('--module-cache',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--schema',action='store_true',help='execute exact AST-extracted Schema with inert receiver')
    parser.add_argument('--build-cache',help='optional existing trusted Go build cache')
    parser.add_argument('--patch-profile',choices=['none','original','patched'],default='none')
    parser.add_argument('--completion-profile', choices=['none', 'original', 'patched'], default='none')
    parser.add_argument('--full-build', action='store_true', help='compile full pinned provider; does not qualify RPC or service')
    parser.add_argument('--inprocess-lifecycle', action='store_true', help='real resource lifecycle with an injected in-memory transport; requires patched completion profile')
    parser.add_argument('--native-build-workers', type=int, choices=(1, 2), default=1,
                        help='bounded native compile workers; use 2 only after large SDK packages are cached')
    parser.add_argument('--with-sdk',action='store_true',help='also compile the large real SDK models and provider constructor')
    args=parser.parse_args()
    try:
        result=qualify(args)
    except Exception as exc:
        print(json.dumps({'status':'failed','error':str(exc),'production_qualified':False}))
        return 1
    print(json.dumps({k:v for k,v in result.items() if k in ('status','error','production_qualified','tests_passed','tests_failed')}))
    return 0 if result['status'] in ('passed-characterization', 'passed-native-build', 'passed-inprocess-lifecycle') else 1

if __name__=='__main__':
    sys.exit(main())
