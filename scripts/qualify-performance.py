#!/usr/bin/env python3
"""Evaluator-owned local CLI measurements. Read the preregistration before use.

No production imports, requests, credentials, timing hooks, or hidden holdout.
All measured operations are fresh CLI processes over disposable synthetic data.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import pty
import resource
import select
import signal
import statistics
import subprocess
import sys
import termios
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'
PROMPT = b'Journey [continue/UUIDs/generate/plan/approve/execute/reconcile/finish/back STAGE/edit FIELD VALUE/resume/save/cancel]: '
MAX_OUTPUT = 16 * 1024 * 1024
MAX_SECONDS = 120
SAMPLE_PROCESS_TREE = False


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot():
    paths = sorted([*ROOT.glob('intune_iac/*.py'), *ROOT.glob('reference/*.py'),
                    ROOT / 'scripts/intune-iac.py', ROOT / 'scripts/qualify-performance.py',
                    ROOT / 'dependency-lock.json', *ROOT.glob('contracts/*.json')])
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def nodes(value):
    count = 0
    pending = [value]
    while pending:
        item = pending.pop(); count += 1
        if isinstance(item, dict): pending.extend(item.values())
        elif isinstance(item, list): pending.extend(item)
    return count


def uid(kind, n):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'performance-20261004/{kind}/{n}'))


def inventory_fixture(count):
    """Independent authored estate, never a production-normalizer result."""
    source = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
    context = json.loads((ROOT / 'examples/context.json').read_text())
    original_id = context['selected_policy_id']
    first = copy.deepcopy(source['collections'][0]['pages'][0]['body']['value'][0])
    children = [c for c in source['collections'] if c['owner_id'] == original_id]
    ownership = source['ownership'][0]
    policies, collections, owners, identities = [], [], [], []
    for i in range(count):
        oid = uid('policy', i); identities.append(oid)
        policy = copy.deepcopy(first); policy['id'] = oid
        policy['name'] = 'Synthetic privacy ' + str(i)
        policies.append(policy)
        for item in children:
            child = json.loads(json.dumps(item).replace(original_id, oid))
            if child['kind'] == 'assignments':
                for j, record in enumerate(child['pages'][0]['body']['value']):
                    record['id'] = uid('assignment-' + str(i), j)
            collections.append(child)
        owner = copy.deepcopy(ownership); owner['object_id'] = oid; owners.append(owner)
    collection = copy.deepcopy(source['collections'][0])
    collection['pages'][0]['body']['value'] = policies
    source['collections'] = [collection, *collections]
    source['ownership'] = owners
    context['selected_policy_id'] = identities[0]
    return source, context, identities


def production_fixture(assignments):
    source, context, identities = inventory_fixture(1)
    source['synthetic'] = False
    source['exporter'] = {'id': 'intune-iac-settings-catalog-graph', 'version': '1.0.0'}
    source['references'] = []; source['ownership'] = []
    context['source_is_synthetic'] = False
    policy = source['collections'][0]['pages'][0]['body']['value'][0]
    policy.update(creationSource='portal', priorityMetaData=None, templateReference=None,
                  disableEntraGroupPolicyAssignment=False)
    records = []
    for i in range(assignments):
        excluded = i % 3 == 2
        filtered = i % 3 == 0
        target = {'@odata.type': '#microsoft.graph.' + ('exclusionGroupAssignmentTarget' if excluded else 'groupAssignmentTarget'),
                  'groupId': uid('group', i), 'deviceAndAppManagementAssignmentFilterType': 'include' if filtered else 'none',
                  'deviceAndAppManagementAssignmentFilterId': uid('filter', i) if filtered else None}
        records.append({'id': uid('large-assignment', i), 'source': 'direct', 'sourceId': None,
                        '@odata.type': '#microsoft.graph.deviceManagementConfigurationPolicyAssignment', 'target': target})
    source['collections'][2]['pages'][0]['body']['value'] = records
    return source, context, identities


def expected_assignments(source):
    result = []
    for collection in source['collections']:
        if collection['kind'] != 'assignments': continue
        for page in collection['pages']:
            for row in page['body']['value']:
                t = row['target']
                item = {'type': t['@odata.type'].split('.')[-1], 'group_id': t['groupId'],
                        'filter_type': t['deviceAndAppManagementAssignmentFilterType']}
                if item['filter_type'] != 'none': item['filter_id'] = t['deviceAndAppManagementAssignmentFilterId']
                result.append(item)
    return result


def assert_configuration(config, source):
    setting = source['collections'][1]['pages'][0]['body']['value'][0]
    policy = source['collections'][0]['pages'][0]['body']['value'][0]
    expected = {'name': policy['name'], 'description': policy.get('description'),
                'platforms': policy['platforms'], 'technologies': [policy['technologies']],
                'role_scope_tag_ids': policy['roleScopeTagIds'],
                'settings': {'settings': [{k: v for k, v in setting.items() if k != '@odata.type'}]},
                'assignments': expected_assignments(source)}
    assert config == expected, 'configuration fields/identity/target/filter/setting semantics changed'


def assert_manifest(output):
    manifest = json.loads((output / 'generated-files.json').read_text())['files']
    actual = {str(p.relative_to(output)) for p in output.rglob('*') if p.is_file()}
    assert actual == set(manifest) | {'generated-files.json'}, 'output closure changed'
    assert all(sha(output / name) == digest for name, digest in manifest.items()), 'manifest/hash mismatch'


def env():
    return {'PATH': str(Path(sys.executable).parent) + ':/usr/bin:/bin', 'LANG': 'C.UTF-8',
            'LC_ALL': 'C.UTF-8', 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONUNBUFFERED': '1', 'ATMOS_CHECK_UPDATES': 'false', 'CHECKPOINT_DISABLE': '1'}


def wait_child(process):
    pid, status, usage = os.wait4(process.pid, os.WNOHANG)
    if not pid: return None
    process.returncode = os.waitstatus_to_exitcode(status)
    return usage


class ProcessTreeSampler:
    """Read-only /proc telemetry, rooted in an exact owned-child pidfd."""
    def __init__(self, root_pid):
        self.namespace_root_pid = root_pid; self.root_pid = None; self.start = time.perf_counter(); self.last = 0
        self.known = {}; self.samples = []; self.denied = 0; self.missing = 0; self.mapping_attempts = 0
        self.cpu_ticks = {}; self.ticks = os.sysconf('SC_CLK_TCK'); self.page_kib = os.sysconf('SC_PAGE_SIZE') / 1024
        self.max_scan_entries = 0; self.truncated_scans = 0

    @staticmethod
    def stat(pid):
        raw = Path(f'/proc/{pid}/stat').read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        return {'pid': pid, 'ppid': int(fields[1]), 'start_ticks': int(fields[19]),
                'rss_pages': max(0, int(fields[21])), 'cpu_ticks': int(fields[11]) + int(fields[12])}

    def resolve_owned_root(self):
        # Namespace Popen PID need not name the same process in mounted /proc.
        # A pidfd binds the exact launched child without guessing an outer PID.
        self.mapping_attempts += 1
        descriptor = os.pidfd_open(self.namespace_root_pid, 0)
        try: info = Path(f'/proc/self/fdinfo/{descriptor}').read_text()
        finally: os.close(descriptor)
        metadata = dict(line.split(':', 1) for line in info.splitlines() if ':' in line)
        proc_pid = int(metadata['Pid'].strip())
        ns_pids = [int(value) for value in metadata['NSpid'].split()]
        parent_pid = int(Path('/proc/self/stat').read_text().split(' ', 1)[0])
        row = self.stat(proc_pid)
        if proc_pid > 0 and ns_pids[-1] == self.namespace_root_pid and row['ppid'] == parent_pid:
            self.root_pid = proc_pid; self.known[proc_pid] = row['start_ticks']

    def sample(self, force=False):
        begin = time.perf_counter()
        if not force and begin - self.last < .01: return
        self.last = begin
        if self.root_pid is None:
            try: self.resolve_owned_root()
            except PermissionError: self.denied += 1
            except (FileNotFoundError, ProcessLookupError): self.missing += 1
        snapshot_rows = {}
        if self.root_pid is not None:
            scanned = 0
            # This kernel does not expose task/children. Read numeric stat files
            # only to establish ancestry; retain/output only owned-tree records.
            for entry in Path('/proc').iterdir():
                if not entry.name.isdigit(): continue
                scanned += 1
                if scanned > 16384:
                    self.truncated_scans += 1; break
                try: snapshot_rows[int(entry.name)] = self.stat(int(entry.name))
                except (FileNotFoundError, ProcessLookupError): self.missing += 1
                except PermissionError: self.denied += 1
            self.max_scan_entries = max(self.max_scan_entries, min(scanned, 16384))
        owned = {pid for pid, start in self.known.items() if pid in snapshot_rows and snapshot_rows[pid]['start_ticks'] == start}
        added = True
        while added:
            added = False
            for pid, row in snapshot_rows.items():
                if pid not in owned and row['ppid'] in owned and row['start_ticks'] >= self.known[self.root_pid]:
                    if pid in self.known and self.known[pid] != row['start_ticks']: continue
                    self.known[pid] = row['start_ticks']; owned.add(pid); added = True
        rows = []
        for pid in sorted(owned):
            row = snapshot_rows[pid]
            key = (pid, row['start_ticks']); self.cpu_ticks[key] = max(row['cpu_ticks'], self.cpu_ticks.get(key, 0))
            rows.append({'pid': pid, 'start_ticks': row['start_ticks'], 'ppid': row['ppid'],
                         'rss_kib': row['rss_pages'] * self.page_kib, 'cpu_ticks': row['cpu_ticks']})
        self.samples.append({'since_start_seconds': begin - self.start, 'sampling_seconds': time.perf_counter() - begin,
                             'rss_sum_kib': sum(row['rss_kib'] for row in rows), 'processes': rows})

    def result(self):
        gaps = [b['since_start_seconds'] - a['since_start_seconds'] for a, b in zip(self.samples, self.samples[1:])]
        return {'method': 'Linux /proc stat; owned root bound via pidfd/NSpid; observed descendant ancestry; target interval 10ms',
                'namespace_root_pid': self.namespace_root_pid, 'proc_root_pid': self.root_pid,
                'identity_mapping_valid': self.root_pid is not None, 'mapping_attempts': self.mapping_attempts,
                'max_stat_entries_scanned': self.max_scan_entries, 'truncated_scans': self.truncated_scans,
                'samples': len(self.samples), 'unique_observed_processes': len(self.cpu_ticks),
                'max_observed_process_count': max((len(s['processes']) for s in self.samples), default=0),
                'sampled_peak_summed_rss_kib': max((s['rss_sum_kib'] for s in self.samples), default=0) if self.cpu_ticks else None,
                'sampled_cpu_seconds': sum(self.cpu_ticks.values()) / self.ticks if self.cpu_ticks else None,
                'sampler_cpu_scope': 'CPU counters of each observed PID/starttime, last observed value; missed lifetime tails possible',
                'sampling_wall_seconds': sum(s['sampling_seconds'] for s in self.samples),
                'max_sample_gap_seconds': max(gaps, default=None), 'permission_denied': self.denied,
                'disappeared_proc_reads': self.missing,
                'limits': ['Sampled peak is a lower bound; unseen transient descendants can be missed.',
                           'Summed RSS double counts shared pages and is not PSS or physical memory allocation.',
                           'Sampler work runs outside child; elapsed work and scheduling interference are reported, not subtracted.',
                           'Unbound or unobserved processes have null telemetry; scanned unrelated stat metadata is not retained.']}


class TimedProcess:
    def __init__(self, command, cwd, terminal=False):
        self.command = command; self.cwd = cwd; self.buffer = bytearray(); self.total = bytearray()
        self.events = []; self.terminal = terminal; self.start = time.perf_counter(); self.usage = None
        self.limit_reason = None; self.finished = None; self.output_events = []
        if terminal:
            master, slave = pty.openpty()
            attrs = termios.tcgetattr(slave); attrs[3] &= ~termios.ECHO; termios.tcsetattr(slave, termios.TCSANOW, attrs)
            self.process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave,
                                            cwd=cwd, env=env(), start_new_session=True)
            os.close(slave); self.fd = master
        else:
            self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, cwd=cwd, env=env(), start_new_session=True)
            self.fd = self.process.stdout.fileno()
        os.set_blocking(self.fd, False)
        self.tree = ProcessTreeSampler(self.process.pid) if SAMPLE_PROCESS_TREE else None
        if self.tree: self.tree.sample(force=True)

    def pump(self):
        if self.tree: self.tree.sample()
        if len(self.total) > MAX_OUTPUT or time.perf_counter() - self.start > MAX_SECONDS:
            self.limit_reason = 'output_limit' if len(self.total) > MAX_OUTPUT else 'time_limit'
            self.kill()
        ready, _, _ = select.select([self.fd], [], [], .01)
        if ready:
            try: chunk = os.read(self.fd, 65536)
            except (BlockingIOError, OSError): chunk = b''
            if chunk: self.output_events.append((time.perf_counter(), len(chunk)))
            self.buffer.extend(chunk); self.total.extend(chunk)
        if self.usage is None: self.usage = wait_child(self.process)

    def prompt(self, since=None):
        start = self.start if since is None else since
        while PROMPT not in self.buffer and self.usage is None: self.pump()
        if PROMPT not in self.buffer: raise AssertionError('process exited before complete prompt: ' + self.total[-700:].decode(errors='replace'))
        end = self.buffer.index(PROMPT) + len(PROMPT)
        chunk = bytes(self.buffer[:end]); del self.buffer[:end]
        return time.perf_counter() - start, chunk.decode(errors='replace')

    def send(self, value):
        start = time.perf_counter(); os.write(self.fd, value.encode() + b'\n'); return start

    def finish(self):
        if self.finished is not None: return dict(self.finished)
        while self.usage is None: self.pump()
        # Drain bytes written immediately before exit.
        while True:
            try: chunk = os.read(self.fd, 65536)
            except (BlockingIOError, OSError): break
            if not chunk: break
            self.buffer.extend(chunk); self.total.extend(chunk)
        if self.terminal: os.close(self.fd)
        else: self.process.stdout.close()
        self.finished = {'command': self.command, 'cwd': str(self.cwd), 'wall_seconds': time.perf_counter() - self.start,
                'cpu_user_seconds': self.usage.ru_utime, 'cpu_system_seconds': self.usage.ru_stime,
                'rss_kib': self.usage.ru_maxrss, 'exit_code': self.process.returncode,
                'output_bytes': len(self.total), 'limit_reason': self.limit_reason,
                'cpu_scope': 'kernel wait4 rusage of the launched child; separate from evaluator and sampled tree telemetry'}
        if self.tree:
            self.tree.sample(force=True)
            dump(self.cwd / 'process-tree.json', {'summary': self.tree.result(), 'samples': self.tree.samples})
            self.finished['process_tree'] = self.tree.result()
            self.finished['process_tree_raw'] = str(self.cwd / 'process-tree.json')
        return dict(self.finished)

    def kill(self):
        try: os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError: pass


class Evaluator:
    def __init__(self, output, prereg, scope='all'):
        self.output = output; self.records = []; self.total_output = 0
        self.prereg = {'path': str(prereg), 'sha256': sha(prereg)}
        self.before = snapshot(); self.scope = scope

    def record(self, case, repetition, metrics, checks, budget, raw):
        self.total_output += len(raw)
        if self.total_output > 512 * 1024 * 1024:
            dump(self.output / 'controller-limit.json', {'status': 'INFRA_ERROR', 'reason': 'aggregate_output_limit',
                                                       'observed_bytes': self.total_output, 'last_case': case})
            raise RuntimeError('512 MiB aggregate output cap reached; previous outcomes retained')
        folder = self.output / 'samples'; folder.mkdir(exist_ok=True)
        stem = case + '-' + str(repetition)
        (folder / (stem + '.stdout.txt')).write_bytes(raw)
        rec = dict(case=case, repetition=repetition, metrics=metrics, checks=checks,
                   budget=budget, output_sha256=hashlib.sha256(raw).hexdigest(),
                   status='PASS' if all(checks.values()) and metrics.get('limit_reason') is None else 'FAIL')
        dump(folder / (stem + '.json'), rec); self.records.append(rec)
        dump(self.output / 'checkpoint.json', {'preregistration': self.prereg, 'records': self.records})

    def command(self, case, repetition, args, expected_exit, budget, checker=None):
        run = self.output / 'runtime' / (case + '-' + str(repetition)); run.mkdir(parents=True)
        proc = TimedProcess([sys.executable, str(CLI), *args], run)
        metrics = proc.finish(); checks = {'expected_exit': metrics['exit_code'] == expected_exit}
        try:
            if checker: checker(bytes(proc.total))
            checks['independent_output'] = True
        except Exception as error:
            checks['independent_output'] = False; metrics['assertion_error'] = str(error)
        self.record(case, repetition, metrics, checks, budget, bytes(proc.total))


def fixtures(output):
    directory = output / 'fixtures'; directory.mkdir()
    rows = []
    for count in [1, 8, 1000, 1001]:
        source, context, ids = inventory_fixture(count)
        case = 'inventory-' + str(count); loc = directory / case; loc.mkdir()
        dump(loc / 'source.json', source); dump(loc / 'context.json', context)
        dump(loc / 'truth.json', {'policy_ids': ids})
        rows.append({'case': case, 'policy_count': count, 'nodes': nodes(source), 'bytes': (loc / 'source.json').stat().st_size})
    lo, hi = 1, 2000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if nodes(production_fixture(mid)[0]) <= 10000: lo = mid
        else: hi = mid - 1
    for label, count in [('small', 3), ('representative', 100), ('maximum', lo), ('over-limit', lo + 1)]:
        source, context, ids = production_fixture(count)
        # Reach the exact node boundary with inert optional wrapper annotation removal
        # on the rejected input; removing optional fields never changes assignment truth.
        if label == 'over-limit':
            for record in source['collections'][2]['pages'][0]['body']['value']:
                if nodes(source) <= 10001: break
                record.pop('@odata.type', None)
            assert nodes(source) == 10001
        case = 'production-' + label; loc = directory / case; loc.mkdir()
        dump(loc / 'source.json', source); dump(loc / 'context.json', context)
        dump(loc / 'truth.json', {'policy_ids': ids, 'assignments': expected_assignments(source)})
        rows.append({'case': case, 'assignment_count': count, 'nodes': nodes(source), 'bytes': (loc / 'source.json').stat().st_size})
    dump(output / 'workloads.json', rows)
    return rows


def output_json(raw):
    return json.loads(raw.decode())


def run_pipe_cases(evaluator):
    for repetition in range(7):
        evaluator.command('startup-help', repetition, ['--help'], 0,
                          {'median_seconds': .5, 'max_seconds': 1, 'rss_mib': 128},
                          lambda raw: 'wizard' in raw.decode() or (_ for _ in ()).throw(AssertionError('help missing wizard')))
    for label, median, rss in [('small', 1, 128), ('representative', 2, 256), ('maximum', 5, 512)]:
        fixture = evaluator.output / 'fixtures' / ('production-' + label)
        source = json.loads((fixture / 'source.json').read_text())
        count = len(expected_assignments(source))
        for rep in range(3 if label == 'maximum' else 5):
            def inspect(raw):
                result = output_json(raw)
                assert result['preservation_verified'] is True
                assert result['execution_authorized'] is False
                assert result['normalized']['candidate_mapping_complete'] is True
                assert_configuration(result['normalized']['configuration'], source)
            evaluator.command('inspect-' + label, rep, ['inspect', '--input', str(fixture / 'source.json'), '--context', str(fixture / 'context.json')],
                              2, {'median_seconds': median, 'max_seconds': median * 2, 'rss_mib': rss, 'work_count': count}, inspect)
            generated = evaluator.output / 'runtime' / ('generated-' + label + '-' + str(rep))
            state = evaluator.output / 'runtime' / ('generation-state-' + label + '-' + str(rep))
            def generated_check(raw):
                assert_manifest(generated)
                config = next(generated.rglob('configuration.json'))
                assert_configuration(json.loads(config.read_text()), source)
                assert not list(generated.rglob('*.tf')) and not list(generated.rglob('*.tf.json')), 'inactive production proposal became executable'
            gen_budget = {'median_seconds': {'small': 2, 'representative': 5, 'maximum': 10}[label],
                          'max_seconds': {'small': 4, 'representative': 10, 'maximum': 20}[label], 'rss_mib': rss, 'work_count': count}
            evaluator.command('generate-' + label, rep, ['generate', '--input', str(fixture / 'source.json'), '--context', str(fixture / 'context.json'),
                              '--output', str(generated), '--state-dir', str(state)], 2, gen_budget, generated_check)
            evaluator.command('verify-' + label, rep, ['verify', '--input', str(fixture / 'source.json'), '--context', str(fixture / 'context.json'),
                              '--output', str(generated)], 0, gen_budget,
                              lambda raw: output_json(raw)['preservation_verified'] is True or (_ for _ in ()).throw(AssertionError('verification false')))
    over = evaluator.output / 'fixtures/production-over-limit'
    for rep in range(3):
        evaluator.command('reject-node-limit', rep, ['inspect', '--input', str(over / 'source.json'), '--context', str(over / 'context.json')], 3,
                          {'median_seconds': 2, 'max_seconds': 5, 'rss_mib': 256},
                          lambda raw: output_json(raw)['error']['code'] == 'capture_node_limit' or (_ for _ in ()).throw(AssertionError('wrong rejection')))


def wizard_command(session, fixture, output):
    return [sys.executable, str(CLI), 'wizard', '--journey', '--journey-mode', 'simulation', '--session', str(session),
            '--input', str(fixture / 'source.json'), '--context', str(fixture / 'context.json'), '--output', str(output)]


def inventory_assert(session, identities):
    receipt = json.loads(Path(str(session) + '.journey/receipts/inventory.json').read_text())
    assert receipt['payload']['observed_policy_ids'] == sorted(identities), 'inventory receipt missing or altered IDs'


def run_pty_cases(evaluator):
    for count, median, rss in [(1, 1, 128), (8, 2, 256), (1000, 5, 512)]:
        fixture = evaluator.output / 'fixtures' / ('inventory-' + str(count))
        identities = json.loads((fixture / 'truth.json').read_text())['policy_ids']
        for rep in range(3):
            loc = evaluator.output / 'runtime' / ('journey-' + str(count) + '-' + str(rep)); loc.mkdir(parents=True)
            session = loc / 'session.json'; command = wizard_command(session, fixture, loc / 'output')
            proc = TimedProcess(command, loc, terminal=True); events = []; checks = {}
            try:
                elapsed, display = proc.prompt(); events.append({'operation': 'first_prompt', 'seconds': elapsed})
                assert 'Journey discovery' in display
                for action in range(3):
                    elapsed, display = proc.prompt(proc.send('continue'))
                    events.append({'operation': 'inventory_continue', 'seconds': elapsed})
                inventory_assert(session, identities); checks['complete_inventory'] = True
                start = proc.send('save'); metrics = proc.finish()
                events.append({'operation': 'save_acknowledgment', 'seconds': time.perf_counter() - start})
                checks['suspended'] = json.loads(session.read_text())['lifecycle'] == 'suspended'
            except Exception as error:
                checks['journey'] = False; proc.kill(); metrics = proc.finish(); metrics['assertion_error'] = str(error)
            metrics['events'] = events
            metrics['completed_inventory_seconds'] = sum(e['seconds'] for e in events if e['operation'] in {'first_prompt', 'inventory_continue'})
            evaluator.record('inventory-' + str(count), rep, metrics, checks,
                             {'median_seconds': median, 'max_seconds': median * 2, 'rss_mib': rss, 'work_count': count, 'timing_scope': 'first_prompt'}, bytes(proc.total))
            resume = TimedProcess(command, loc, terminal=True); checks = {}
            try:
                elapsed, display = resume.prompt()
                checks['reconstructed_selection'] = 'Journey selection' in display
                inventory_assert(session, identities); checks['durable_inventory'] = True
                resume.send('save'); resumed = resume.finish(); resumed['resume_seconds'] = elapsed
            except Exception as error:
                resume.kill(); resumed = resume.finish(); checks['resume'] = False; resumed['assertion_error'] = str(error)
            evaluator.record('resume-' + str(count), rep, resumed, checks,
                             {'median_seconds': median, 'max_seconds': median * 2, 'rss_mib': rss, 'timing_scope': 'resume_seconds'}, bytes(resume.total))
    fixture = evaluator.output / 'fixtures/inventory-1001'
    for rep in range(3):
        loc = evaluator.output / 'runtime' / ('inventory-rejection-' + str(rep)); loc.mkdir(parents=True)
        proc = TimedProcess(wizard_command(loc / 'session.json', fixture, loc / 'output'), loc)
        metrics = proc.finish()
        checks = {'rejected': metrics['exit_code'] == 2 and b'workflow_inventory_limit' in proc.total,
                  'no_generated_output': not (loc / 'output').exists()}
        evaluator.record('reject-inventory-limit', rep, metrics, checks, {'median_seconds': 2, 'max_seconds': 5, 'rss_mib': 256}, bytes(proc.total))
    for kind in ['cancel', 'interrupt']:
        for rep in range(3):
            loc = evaluator.output / 'runtime' / (kind + '-' + str(rep)); loc.mkdir(parents=True)
            session = loc / 'session.json'; fixture = evaluator.output / 'fixtures/inventory-1'
            proc = TimedProcess(wizard_command(session, fixture, loc / 'output'), loc, terminal=True)
            checks = {}
            try:
                proc.prompt(); start = time.perf_counter()
                if kind == 'cancel': proc.send('cancel')
                else: os.kill(proc.process.pid, signal.SIGINT)
                metrics = proc.finish(); metrics['cancellation_seconds'] = time.perf_counter() - start
                checks = {'durable_state': json.loads(session.read_text())['lifecycle'] == ('cancelled' if kind == 'cancel' else 'suspended'),
                          'process_exited': metrics['exit_code'] == 0, 'no_output_mutation': not (loc / 'output').exists()}
            except Exception as error:
                proc.kill(); metrics = proc.finish(); checks['cancellation'] = False; metrics['assertion_error'] = str(error)
            evaluator.record(kind, rep, metrics, checks, {'median_seconds': .5, 'max_seconds': 2, 'rss_mib': 128, 'timing_scope': 'cancellation_seconds'}, bytes(proc.total))


def run_connected(evaluator, policy_count=1, progress=False):
    case = 'connected-' + str(policy_count)
    loc = evaluator.output / ('runtime/' + case); loc.mkdir(parents=True)
    fixture = evaluator.output / ('fixtures/inventory-' + str(policy_count)); session = loc / 'session.json'
    identities = json.loads((fixture / 'truth.json').read_text())['policy_ids']
    answers = ['continue'] * 3 + [','.join(identities)] + ['continue'] * 4 + ['generate', 'continue', 'continue', 'plan', 'approve', 'execute', 'reconcile', 'continue', 'finish']
    proc = TimedProcess(wizard_command(session, fixture, loc / 'output'), loc, terminal=True)
    events = []; checks = {}
    try:
        elapsed, display = proc.prompt(); events.append({'operation': 'first_prompt', 'seconds': elapsed})
        for index, answer in enumerate(answers):
            start = proc.send(answer)
            if index + 1 < len(answers):
                elapsed, display = proc.prompt(start)
                first = next((when - start for when, _ in proc.output_events if when >= start), None)
                events.append({'operation': answer, 'seconds': elapsed, 'first_output_seconds': first,
                               'progress_present': 'Working:' in display})
        metrics = proc.finish()
        state = json.loads(session.read_text()); receipts = Path(str(session) + '.journey/receipts')
        checks = {'complete': state['lifecycle'] == 'complete_simulation', 'all_receipts': len(list(receipts.glob('*.json'))) == 17,
                  'exit_zero': metrics['exit_code'] == 0}
        for oid in identities: assert_manifest(loc / 'output' / oid)
        checks['closed_output'] = True
        # The complete route must retain the authored semantic projection; IDs alone
        # are insufficient. Never use the application's normalizer to establish truth.
        service = loc / 'session.json.journey/modeled-service'
        capture = json.loads((fixture / 'source.json').read_text())
        model = json.loads((service / 'service.json').read_text())
        readback = json.loads((loc / 'session.json.journey/modeled-readback.json').read_text())
        for estate in (model['initial'], model['current'], readback['estate']):
            assert estate['tenant_id'] == capture['tenant_id'] and estate['cloud'] == capture['cloud']
            assert set(estate['objects']) == set(identities), 'immutable policy IDs changed'
            for oid in identities:
                # Independent per-owner oracle view leaves the actual CLI capture
                # complete. Only evaluator expectations are projected here.
                single = copy.deepcopy(capture)
                single['collections'] = [c for c in single['collections'] if c['owner_id'] in (None, oid)]
                single['collections'][0]['pages'][0]['body']['value'] = [p for p in single['collections'][0]['pages'][0]['body']['value'] if p['id'] == oid]
                assert_configuration(estate['objects'][oid], single)
        checks['full_model_semantics_preserved'] = True
        checks['model_readback_requests'] = bool(model['requests']) and all(
            row['method'] == 'GET' and row['status'] == 200 and not row['mutation_committed'] for row in model['requests'])
        checks['model_readback_bound'] = readback['revision'] == model['revision'] and readback['request_count'] == len(model['requests'])
        checks['model_no_remote_mutation'] = model['revision'] == 1
    except Exception as error:
        proc.kill(); metrics = proc.finish(); checks['connected'] = False; metrics['assertion_error'] = str(error)
    metrics['events'] = events
    if SAMPLE_PROCESS_TREE:
        tree = metrics.get('process_tree', {})
        checks['process_tree_root_bound'] = tree.get('identity_mapping_valid') and tree.get('unique_observed_processes', 0) >= 1
        checks['process_tree_access_complete_for_samples'] = tree.get('permission_denied') == 0 and tree.get('truncated_scans') == 0
    artifact_rows = []
    for path in sorted(loc.rglob('*')):
        if not path.is_file() or path.is_symlink() or path.name == 'process-tree.json': continue
        rel = path.relative_to(loc).as_posix()
        kind = 'generated' if rel.startswith('output/') else ('receipt' if '/receipts/' in rel else ('journal' if 'journal' in path.name.lower() else 'other_evidence'))
        artifact_rows.append({'path': rel, 'bytes': path.stat().st_size, 'kind': kind})
    metrics['artifact_bytes'] = sum(row['bytes'] for row in artifact_rows)
    metrics['artifact_count'] = len(artifact_rows)
    metrics['artifact_bytes_by_kind'] = {kind: sum(row['bytes'] for row in artifact_rows if row['kind'] == kind) for kind in sorted({row['kind'] for row in artifact_rows})}
    metrics['logging_scope'] = 'Actual console bytes and mandatory evidence artifact volume; no supported optional log level/toggle; marginal causal logging cost not measured.'
    dump(loc / 'artifact-volume.json', {'files': artifact_rows, 'console_bytes': metrics['output_bytes'], 'scope': metrics['logging_scope']})
    evaluator.record(case, 0, metrics, checks, {'median_seconds': None, 'max_seconds': 120, 'rss_mib': 512}, bytes(proc.total))
    if progress:
        accepted = [event for event in events if event['operation'] in {'continue', 'generate', 'plan', 'approve', 'execute', 'reconcile'}]
        feedback = [event['first_output_seconds'] for event in accepted if event.get('first_output_seconds') is not None]
        feedback_checks = {'all_expected_commands_observed': len(accepted) == 15,
                           'every_command_has_progress': all(event.get('progress_present') for event in accepted),
                           'connected_semantics_pass': all(checks.values()),
                           'every_command_has_first_output': len(feedback) == len(accepted)}
        metrics = dict(metrics, progress_median_seconds=statistics.median(feedback) if feedback else MAX_SECONDS,
                       progress_max_seconds=max(feedback) if feedback else MAX_SECONDS, progress_samples=feedback)
        feedback_checks['observed_max_within_budget'] = metrics['progress_max_seconds'] <= 1
        evaluator.record('progress-feedback-' + str(policy_count), 0, metrics, feedback_checks,
                         {'median_seconds': .5, 'max_seconds': 1, 'rss_mib': 512, 'timing_scope': 'progress_median_seconds'}, bytes(proc.total))


def run_native_versions(evaluator, tools):
    """Known read-only version invocations; not native lifecycle throughput."""
    for item in tools:
        name, path, expected_hash = item.split('=', 2)
        if name not in {'tofu', 'atmos'}: raise ValueError('Only preregistered tofu/atmos version commands are allowed')
        executable = Path(path).absolute()
        if sha(executable) != expected_hash: raise ValueError('Native pin mismatch')
        command = [str(executable), 'version'] + (['-json'] if name == 'tofu' else [])
        for rep in range(5):
            loc = evaluator.output / 'runtime' / ('native-' + name + '-' + str(rep)); loc.mkdir(parents=True)
            proc = TimedProcess(command, loc); metrics = proc.finish()
            metrics['binary_sha256'] = expected_hash
            text = proc.total.decode(errors='replace')
            checks = {'exit_zero': metrics['exit_code'] == 0, 'pin_unchanged': sha(executable) == expected_hash,
                      'version_identified': ('1.10.0' if name == 'tofu' else '1.199.0') in text}
            evaluator.record('native-version-' + name, rep, metrics, checks,
                             {'median_seconds': None, 'max_seconds': 10, 'rss_mib': 512}, bytes(proc.total))


def calibration(output):
    source, _, _ = production_fixture(3)
    config = {'assignments': expected_assignments(source),
              'settings': {'settings': [{k: v for k, v in source['collections'][1]['pages'][0]['body']['value'][0].items() if k != '@odata.type'}]},
              'role_scope_tag_ids': ['0'], 'name': 'Synthetic privacy 0',
              'description': source['collections'][0]['pages'][0]['body']['value'][0]['description'],
              'platforms': 'windows10', 'technologies': ['mdm']}
    assert_configuration(config, source)
    corrupt = copy.deepcopy(config); corrupt['assignments'].pop()
    rejected = False
    try: assert_configuration(corrupt, source)
    except AssertionError: rejected = True
    loc = output / 'oracle-mutation'; loc.mkdir(); (loc / 'a').write_text('legitimate')
    dump(loc / 'generated-files.json', {'files': {'a': sha(loc / 'a')}}); assert_manifest(loc)
    (loc / 'a').write_text('corrupt')
    manifest_rejected = False
    try: assert_manifest(loc)
    except AssertionError: manifest_rejected = True
    field_controls = {}
    for field in config:
        corrupt = copy.deepcopy(config); del corrupt[field]
        try: assert_configuration(corrupt, source)
        except AssertionError: field_controls[field + '_omitted_rejected'] = True
        else: field_controls[field + '_omitted_rejected'] = False
    corrupt = copy.deepcopy(config); corrupt['extra'] = 'unsupported'
    try: assert_configuration(corrupt, source)
    except AssertionError: field_controls['extra_field_rejected'] = True
    else: field_controls['extra_field_rejected'] = False
    assert rejected and manifest_rejected and all(field_controls.values())
    dump(output / 'oracle-controls.json', {'legitimate_accepted': True, 'dropped_assignment_rejected': rejected,
                                         'changed_manifest_payload_rejected': manifest_rejected, **field_controls})


def summary(evaluator):
    groups = {}
    for rec in evaluator.records: groups.setdefault(rec['case'], []).append(rec)
    results = []
    for case, records in groups.items():
        budget = records[0]['budget']; values = []
        for rec in records:
            m = rec['metrics']; scope = budget.get('timing_scope', 'wall_seconds')
            if scope == 'first_prompt':
                values.extend(e['seconds'] for e in m.get('events', []) if e['operation'] == 'first_prompt')
            elif scope in m: values.append(m[scope])
        valid = len(values) == len(records) and all(r['status'] == 'PASS' for r in records)
        p = {'case': case, 'samples': len(records), 'observed_seconds': values, 'budget': budget,
             'median_seconds': statistics.median(values) if values else None, 'min_seconds': min(values) if values else None,
             'max_seconds': max(values) if values else None, 'max_rss_mib': max(r['metrics']['rss_kib'] for r in records) / 1024,
             'functional_failures': sum(r['status'] != 'PASS' for r in records)}
        timing_pass = bool(values) and (budget['median_seconds'] is None or p['median_seconds'] <= budget['median_seconds']) and p['max_seconds'] <= budget['max_seconds']
        p['status'] = 'PASS' if valid and timing_pass and p['max_rss_mib'] <= budget['rss_mib'] else 'FAIL'
        if budget.get('work_count') and values:
            completed = [r['metrics']['completed_inventory_seconds'] for r in records] if case.startswith('inventory-') else values
            p['median_work_units_per_second'] = budget['work_count'] / statistics.median(completed)
            p['throughput_wall_scope'] = 'fresh process through independently checked inventory receipt' if case.startswith('inventory-') else 'completed CLI command'
        results.append(p)
        if case.startswith('inventory-'):
            control = [e['seconds'] for r in records for e in r['metrics'].get('events', []) if e['operation'] == 'inventory_continue']
            control_budget = .5 if case == 'inventory-1' else budget['median_seconds']
            results.append({'case': case + '-controls', 'samples': len(control), 'observed_seconds': control,
                            'median_seconds': statistics.median(control) if control else None,
                            'max_seconds': max(control) if control else None,
                            'budget': {'median_seconds': control_budget, 'max_seconds': control_budget * 2},
                            'status': 'PASS' if valid and len(control) == len(records) * 3 and statistics.median(control) <= control_budget and max(control) <= control_budget * 2 else 'FAIL'})
    after = snapshot()
    changed_paths = sorted(p for p in set(evaluator.before) | set(after) if evaluator.before.get(p) != after.get(p))
    pipe_modules = {'__init__.py', 'cli.py', 'io.py', 'engine.py', 'runner.py', 'production.py', 'production_oracle.py'}
    relevant_changes = [p for p in changed_paths if evaluator.scope != 'pipe' or not p.startswith('intune_iac/') or Path(p).name in pipe_modules]
    report = {'schema': 'intune-cli-performance/1.0', 'preregistration': evaluator.prereg,
              'source_before': evaluator.before, 'source_after': after, 'source_unchanged': not relevant_changes,
              'all_source_changed_paths': changed_paths, 'measured_dependency_changed_paths': relevant_changes,
              'source_scope': evaluator.scope, 'pipe_dependency_modules': sorted(pipe_modules) if evaluator.scope == 'pipe' else None,
              'status': 'INVALID_RUN' if relevant_changes else ('PASS' if all(p['status'] == 'PASS' for p in results) else 'FAIL'),
              'groups': results, 'platform': platform.platform(), 'python': sys.version,
              'scope': 'Linux fresh CLI processes, uncontrolled/warm filesystem cache, synthetic fixtures; observed samples only; no tail or live throughput claims.',
              'missing': ['Native Windows/macOS', 'Live Graph network throughput', 'Active provider cancellation process-tree RSS', 'Private holdout separation']}
    dump(evaluator.output / 'summary.json', report)
    return report


def main():
    global SAMPLE_PROCESS_TREE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True); parser.add_argument('--preregistration', required=True)
    parser.add_argument('--mode', choices=['prepare', 'run'], required=True)
    parser.add_argument('--only', choices=['all', 'pipe', 'pty', 'connected', 'progress'], default='all')
    parser.add_argument('--sample-process-tree', action='store_true', help='Descriptive evaluator /proc sampling; see preregistration.')
    parser.add_argument('--native-tool', action='append', default=[], metavar='NAME=PATH=SHA256')
    args = parser.parse_args(); SAMPLE_PROCESS_TREE = args.sample_process_tree
    output = Path(args.output).absolute(); prereg = Path(args.preregistration).absolute()
    if not prereg.is_file(): parser.error('Existing preregistration is required.')
    if output.exists(): parser.error('Fresh evidence directory required; keep previous outcomes.')
    output.mkdir(parents=True, mode=0o700)
    evaluator = Evaluator(output, prereg, args.only); workloads = fixtures(output); calibration(output)
    dump(output / 'environment.json', {'platform': platform.platform(), 'python': sys.version,
         'load_average_before': os.getloadavg(), 'cpu_count': os.cpu_count(), 'preregistration': evaluator.prereg,
         'source_before': evaluator.before, 'mode': args.mode, 'only': args.only,
         'clock': vars(time.get_clock_info('perf_counter')), 'created_unix': time.time(), 'process_tree_sampling': args.sample_process_tree})
    if args.mode == 'prepare':
        print(json.dumps({'status': 'PREPARED_NOT_TIMED', 'workloads': workloads, 'output': str(output)})); return 0
    if args.only in ['all', 'pipe']: run_pipe_cases(evaluator)
    if args.only in ['all', 'pty']: run_pty_cases(evaluator)
    if args.only in ['all', 'connected']:
        run_connected(evaluator, 1)
        run_connected(evaluator, 8)
    if args.only == 'progress': run_connected(evaluator, 8, progress=True)
    if args.native_tool: run_native_versions(evaluator, args.native_tool)
    report = summary(evaluator)
    print(json.dumps({'status': report['status'], 'groups': len(report['groups']), 'failed_groups': [g['case'] for g in report['groups'] if g['status'] != 'PASS'], 'output': str(output)}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
