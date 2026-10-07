#!/usr/bin/env python3
"""Preregistered, independent local Workbench CLI capacity qualification.

No product modules are imported. All product operations use fresh CLI processes;
raw SQLite/JSON assertions are authored independently. The history query fixture
is explicitly SQL-seeded after one real collection, not an ingestion benchmark.
Process cold start is measured; operating-system caches are not flushed. This is
one Linux host, synthetic/caller-asserted inputs, no live service or fleet SLA.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import sqlite3
import statistics
import subprocess
import sys
import time
import traceback

PROJECT = Path(__file__).resolve().parents[1]
TENANT = '11111111-1111-4111-8111-111111111111'
POLICY = '22222222-2222-4222-8222-222222222222'
GRAPH = 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'
DEFINITION = 'device_vendor_msft_policy_config_privacy_letappsaccesslocation'
PLAN = {
    'schema_version': 'workbench-performance-preregistration/1',
    'evidence_class': 'local_linux_process_and_persistence_qualification',
    'repetitions': 3,
    'workloads': {
        'startup': 'Fresh actual CLI workbench --help; three processes.',
        'modeled': 'One-policy and maximum admitted eight-policy actual lab-create/collect.',
        'imported': '100 then 1000 distinct caller-asserted captures, each imported by a fresh CLI process; one setting and three assignments each.',
        'history': '1000 observations of one object, independently SQL-seeded from one real CLI collection; does not qualify 1000 ingestions.',
        'durability': 'Independent raw SQLite field/count checks after process exit, byte-bound backup, restore and fresh CLI inspection.',
        'overlimit': '1001 unpaged history observations; explicit limit 1001; ninth selected modeled object; source document exceeding 2 MiB.',
    },
    'thresholds': {
        'startup': {'wall_seconds': 2.0, 'cpu_seconds': 1.5, 'peak_rss_kib': 262144},
        'ordinary': {'wall_seconds': 5.0, 'cpu_seconds': 4.0, 'peak_rss_kib': 524288},
        'capacity': {'wall_seconds': 15.0, 'cpu_seconds': 12.0, 'peak_rss_kib': 786432},
    },
    'threshold_policy': 'Every measured sample must satisfy every preregistered threshold; maximum and median reported, no outlier removal or post-hoc threshold change.',
    'declared_bounds': {'model_objects': 8, 'query_rows': 1000, 'document_bytes': 2097152, 'query_bytes': 16777216},
    'capacity_policy': '100-object imported overview must return all exact objects. At 1000 imported objects, exact complete return or explicit workbench_query_limit is acceptable containment; rejection is recorded as a product capacity limitation, never a successful 1000-object inventory claim.',
    'measurement': 'Linux wait4 per-child user+system CPU and ru_maxrss KiB; parent monotonic wall time includes interpreter startup, output serialization, durable I/O and process reap. Fresh process each time; filesystem/page caches remain uncontrolled.',
    'concurrency': 'Run only after coordinator confirms no competing heavy qualification job. Record load average and visible processes before/after; background host activity cannot be excluded.',
    'limitations': ['No live Graph/service latency, production tenant, device evidence or organizational SLA.', 'No native Windows/macOS qualification or hostile-host/power-loss durability.', 'Raw synthetic Graph-shaped captures establish no authenticated platform authority.', 'Eight-object ModeledService limit does not describe imported observation capacity.', 'Three samples are descriptive, not percentile/confidence or enterprise fleet claims.'],
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def dump(path, value):
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b'\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact(expected, actual):
    if type(expected) is not type(actual):
        raise AssertionError('Type differs: ' + type(expected).__name__ + '/' + type(actual).__name__)
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            raise AssertionError('Object field set differs')
        for key in expected:
            exact(expected[key], actual[key])
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            raise AssertionError('List length differs')
        for first, second in zip(expected, actual):
            exact(first, second)
    elif expected != actual:
        raise AssertionError('Literal expected value differs')


def expected_body(name='Windows Privacy Pilot'):
    return {'name': name, 'description': 'Synthetic reference; not production advice.',
        'platforms': 'windows10', 'technologies': ['mdm'], 'role_scope_tag_ids': ['0'],
        'settings': {'settings': [{'id': '0', 'settingInstance': {
            '@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance',
            'settingDefinitionId': DEFINITION, 'settingInstanceTemplateReference': None,
            'choiceSettingValue': {'@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingValue',
                'settingValueTemplateReference': None, 'value': DEFINITION + '_2', 'children': []}}}]},
        'assignments': [
            {'type': 'groupAssignmentTarget', 'group_id': '44444444-4444-4444-8444-444444444444', 'filter_type': 'include', 'filter_id': '77777777-7777-4777-8777-777777777777'},
            {'type': 'groupAssignmentTarget', 'group_id': '55555555-5555-4555-8555-555555555555', 'filter_type': 'none'},
            {'type': 'exclusionGroupAssignmentTarget', 'group_id': '66666666-6666-4666-8666-666666666666', 'filter_type': 'none'}]}


def object_id(index):
    return '90000000-0000-4000-8000-' + f'{index:012x}'


def source_map():
    paths = [PROJECT/'scripts/intune-iac.py', Path(__file__).resolve(), PROJECT/'examples/supported/input/export.json']
    paths += sorted((PROJECT/'intune_iac').glob('*.py'))
    return {str(p.relative_to(PROJECT)): sha(p) for p in paths}


def prepare(output):
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    registration = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'plan': PLAN,
        'plan_sha256': hashlib.sha256(canonical(PLAN)).hexdigest(), 'grader_sha256': sha(Path(__file__)),
        'source_at_registration': source_map(), 'timings_started': False}
    dump(output/'preregistration.json', registration)
    return registration


class Run:
    def __init__(self, output, python, quiet_window):
        self.root = output
        self.python = str(Path(python).absolute())
        self.registration = json.loads((output/'preregistration.json').read_text())
        exact(PLAN, self.registration['plan'])
        exact(sha(Path(__file__)), self.registration['grader_sha256'])
        if (output/'receipt.json').exists():
            raise ValueError('An attempted run must be preserved; prepare a new output directory.')
        self.result = {'schema_version': 'workbench-performance-receipt/1', 'status': 'RUNNING',
            'preregistration_sha256': sha(output/'preregistration.json'), 'plan_sha256': self.registration['plan_sha256'],
            'quiet_window_attestation': quiet_window, 'started_at': datetime.now(timezone.utc).isoformat(),
            'environment': {'platform': platform.platform(), 'python': self.python, 'python_sha256': sha(Path(self.python)),
                'load_average': os.getloadavg(), 'cpu_count': os.cpu_count()},
            'source_before': source_map(), 'commands': [], 'checks': [], 'capacity_limits': [],
            'not_established': PLAN['limitations']}
        self.save()
        self.snapshot_processes('processes-before.txt')

    def snapshot_processes(self, name):
        # Do not record full argv or environment, which could contain credentials.
        completed = subprocess.run(['ps', '-eo', 'pid,ppid,comm,pcpu,pmem'], capture_output=True, check=True)
        (self.root/name).write_bytes(completed.stdout)

    def save(self):
        dump(self.root/'receipt.json', self.result)

    def check(self, name, predicate):
        self.result['checks'].append({'id': name, 'passed': bool(predicate)})
        self.save()
        if not predicate:
            raise AssertionError(name)

    def cli(self, label, *args, category=None, expected_error=None, may_limit=False):
        number = len(self.result['commands']) + 1
        base = self.root/f'{number:04d}-{label}'
        stdout, stderr = base.with_suffix('.stdout'), base.with_suffix('.stderr')
        command = [self.python, '-B', str(PROJECT/'scripts/intune-iac.py'), 'workbench', *map(str, args)]
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(self.root), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'}
        started = time.monotonic()
        timed_out = False
        with stdout.open('wb') as out, stderr.open('wb') as err:
            child = subprocess.Popen(command, cwd=PROJECT, env=env, stdout=out, stderr=err, start_new_session=True)
            while True:
                waited, status, usage = os.wait4(child.pid, os.WNOHANG)
                if waited:
                    break
                if time.monotonic()-started > 60:
                    timed_out = True
                    os.killpg(child.pid, signal.SIGKILL)
                    waited, status, usage = os.wait4(child.pid, 0)
                    break
                time.sleep(.002)
            child.returncode = os.waitstatus_to_exitcode(status)
        elapsed = time.monotonic()-started
        row = {'number': number, 'label': label, 'command': command, 'cwd': str(PROJECT), 'category': category,
            'fresh_process': True, 'exit_code': child.returncode, 'timed_out': timed_out,
            'wall_seconds': elapsed, 'cpu_user_seconds': usage.ru_utime, 'cpu_system_seconds': usage.ru_stime,
            'cpu_seconds': usage.ru_utime+usage.ru_stime, 'peak_rss_kib': usage.ru_maxrss,
            'stdout': {'path': stdout.name, 'bytes': stdout.stat().st_size, 'sha256': sha(stdout)},
            'stderr': {'path': stderr.name, 'bytes': stderr.stat().st_size, 'sha256': sha(stderr)}}
        self.result['commands'].append(row)
        if category:
            row['thresholds'] = PLAN['thresholds'][category]
            row['within_thresholds'] = all(row[key] <= ceiling for key, ceiling in row['thresholds'].items())
        self.save()
        if timed_out:
            raise AssertionError(label + ' timed out')
        if category and not row['within_thresholds']:
            raise AssertionError(label + ' exceeded preregistered performance threshold')
        if args == ('--help',):
            self.check(label + '_help', child.returncode == 0 and b'import-capture' in stdout.read_bytes())
            return None
        if child.returncode:
            error = json.loads(stderr.read_bytes())
            code = error.get('error', {}).get('code') if isinstance(error.get('error'), dict) else error.get('error')
            row['error_code'] = code
            self.save()
            wanted = expected_error or ('workbench_query_limit' if may_limit else None)
            if code != wanted:
                raise AssertionError(label + ' unexpected error: ' + str(code))
            return {'bounded_rejection': code}
        if expected_error:
            raise AssertionError(label + ' did not reject overlimit input')
        return json.loads(stdout.read_bytes())

    def raw_store(self, root):
        with sqlite3.connect((root/'observations.sqlite3').as_uri()+'?mode=ro', uri=True) as db:
            count = db.execute('SELECT count(*) FROM object_heads WHERE present=1').fetchone()[0]
            bodies = {oid: json.loads(body) for oid, body in db.execute('SELECT h.object_id,s.body_json FROM object_heads h JOIN observations o USING(observation_id) JOIN snapshots s USING(snapshot_id) WHERE h.present=1')}
            return {'objects': count, 'bodies': bodies,
                'observations': db.execute('SELECT count(*) FROM observations').fetchone()[0],
                'runs': db.execute('SELECT count(*) FROM collection_runs').fetchone()[0],
                'complete_runs': db.execute("SELECT count(*) FROM collection_runs WHERE status='complete'").fetchone()[0],
                'integrity': db.execute('PRAGMA integrity_check').fetchone()[0],
                'foreign_key_errors': db.execute('PRAGMA foreign_key_check').fetchall()}

    def assert_bodies(self, store, expected):
        raw = self.raw_store(store)
        exact(expected, raw['bodies'])
        self.check('raw_store_'+store.name, raw['objects'] == len(expected) and raw['integrity'] == 'ok' and raw['foreign_key_errors'] == [])
        dump(self.root/(store.name+'-independent-sqlite.json'), raw)

    def fixture_capture(self, directory, oid, name, template):
        """Write consistent synthetic raw GET evidence, without product exporters."""
        directory.mkdir(mode=0o700); (directory/'raw').mkdir(mode=0o700)
        source = copy.deepcopy(template)
        source.update(synthetic=False, exporter={'id':'intune-iac-settings-catalog-graph','version':'1.0.0'}, references=[], ownership=[])
        policy_collection = source['collections'][0]
        policy = policy_collection['pages'][0]['body']['value'][0]
        policy.update(id=oid, name=name)
        policy_collection['pages'][0]['body']['value'] = [policy]
        source['collections'] = [policy_collection] + [copy.deepcopy(c) for c in source['collections'] if c.get('owner_id') == POLICY]
        receipts = []
        for collection in source['collections']:
            kind = collection['kind']; owner = None if kind == 'policies' else oid
            collection['owner_id'] = owner
            for page in collection['pages']:
                page['request_url'] = GRAPH + ('/'+oid+'/'+kind if owner else '')
                if kind == 'assignments':
                    for assignment in page['body']['value']:
                        assignment.update(source='direct', sourceId=None)
                raw = canonical(page['body']) + b'\n'; raw_name = f'raw/page-{len(receipts):06d}.json'
                (directory/raw_name).write_bytes(raw)
                receipts.append({'kind':kind,'owner_id':owner,**{key:page[key] for key in ('request_url','method','http_status','captured_at')},
                    'raw_path':raw_name,'source_bytes':len(raw),'source_byte_sha256':hashlib.sha256(raw).hexdigest(),'raw_capture_complete':True})
        context = {'schema_version':'1.0.0','tenant_id':TENANT,'selected_policy_id':oid,'cloud':'public',
            'provider_source':'deploymenttheory/microsoft365','provider_version':'1.0.0','engine':'tofu','engine_version':'1.10.0',
            'atmos_version':'1.199.0','component':'intune-reference','stack':'reference-dev','authorization':'emit_only','source_is_synthetic':False}
        export_bytes, context_bytes = canonical(source)+b'\n', canonical(context)+b'\n'
        (directory/'export.json').write_bytes(export_bytes); (directory/'context.json').write_bytes(context_bytes)
        receipt = {'schema_version':'1.0.0','adapter':source['exporter'],'tenant_id':TENANT,'selected_policy_id':oid,
            'cloud':'public','api_version':'beta','tenant_assurance':'caller_asserted','started_at':source['captured_at'],'finished_at':source['captured_at'],
            'target_assurance':'proposed_reference_labels_only','limits':{'max_pages':1000,'max_page_bytes':4194304,'max_total_bytes':8388608,'request_timeout_seconds':30,'max_elapsed_seconds':120},
            'pages':receipts,'attempt_count':len(receipts),'export_byte_sha256':hashlib.sha256(export_bytes).hexdigest(),
            'context_byte_sha256':hashlib.sha256(context_bytes).hexdigest(),'source_authenticity_verified':False,'provider_qualified':False,'execution_authorized':False}
        dump(directory/'capture-receipt.json', receipt)

    def modeled(self, count, template):
        capture = copy.deepcopy(template)
        seed_policy = copy.deepcopy(capture['collections'][0]['pages'][0]['body']['value'][0])
        seed_collections = [copy.deepcopy(c) for c in capture['collections'] if c.get('owner_id') == POLICY]
        ids = [object_id(2000+i) for i in range(count)]
        capture['collections'] = [capture['collections'][0]]
        capture['collections'][0]['pages'][0]['body']['value'] = [dict(seed_policy, id=oid) for oid in ids]
        for oid in ids:
            for original in seed_collections:
                collection = copy.deepcopy(original); collection['owner_id'] = oid
                for page in collection['pages']:
                    page['request_url'] = GRAPH+'/'+oid+'/'+collection['kind']
                capture['collections'].append(collection)
        path = self.root/f'model-{count}.json'; dump(path, capture)
        service, store = self.root/f'service-{count}', self.root/f'model-store-{count}'
        args = ['lab-create','--service-root',str(service),'--input',str(path)]
        for oid in ids:
            args.extend(['--object',oid])
        if count > 8:
            self.cli('ninth-object-rejection', *args, category='ordinary', expected_error='model_selection_invalid')
            self.check('ninth_object_creates_no_service', not service.exists())
            return None
        self.cli('lab-create', *args, category='ordinary')
        self.cli('init-model', 'init','--root',store,'--tenant',TENANT)
        result = self.cli('model-collect','collect','--root',store,'--service-root',service,category='ordinary')
        self.check(f'model_{count}_complete', result['status'] == 'complete' and result['object_count'] == count)
        self.assert_bodies(store, {oid:expected_body() for oid in ids})
        for repeat in range(PLAN['repetitions']):
            result = self.cli(f'model-{count}-overview','overview','--root',store,category='ordinary')
            exact({oid:expected_body() for oid in ids}, {row['object_id']:row['body'] for row in result['objects']})
        return store, service, ids

    def seed_history(self, store, total):
        """Independent fixture construction only; no claim of product ingestion."""
        with sqlite3.connect(store/'observations.sqlite3') as db:
            db.execute('PRAGMA foreign_keys=ON')
            original = db.execute('SELECT * FROM collection_runs WHERE run_id=1').fetchone()
            observation = db.execute('SELECT * FROM observations WHERE run_id=1').fetchone()
            detail = db.execute('SELECT * FROM run_details WHERE run_id=1').fetchone()
            coverage = db.execute('SELECT * FROM collection_coverage WHERE run_id=1').fetchall()
            first = db.execute('SELECT count(*) FROM collection_runs').fetchone()[0] + 1
            for index in range(first, total+1):
                run = list(original); run[0] = index; run[3] = original[3] + index/10000
                db.execute('INSERT INTO collection_runs VALUES(?,?,?,?,?,?,?,?,?)', run)
                obs = list(observation); obs[0] = index; obs[1] = index; obs[5] = run[3]
                db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?)', obs)
                details = list(detail); details[0] = index
                db.execute('INSERT INTO run_details VALUES(?,?,?,?,?)', details)
                db.execute('INSERT INTO run_scope_objects VALUES(?,?)',(index,observation[4]))
                for row in coverage:
                    item = list(row); item[0] = index
                    db.execute('INSERT INTO collection_coverage VALUES(?,?,?,?,?,?)',item)
            db.execute('UPDATE object_heads SET run_id=?,observation_id=?,observed_at=?',(total,total,original[3]+total/10000))
        self.check('seeded_history_count_'+str(total), self.raw_store(store)['observations'] == total)

    def execute(self):
        template = json.loads((PROJECT/'examples/supported/input/export.json').read_text())
        # Oracle rejects value, identity and bool/int corruption before product data.
        for wrong in (True, 'unexpected', None):
            try:
                exact(1, wrong)
            except AssertionError:
                continue
            raise AssertionError('Independent oracle accepts corrupted literal')
        self.check('oracle_negative_controls', True)
        for _ in range(PLAN['repetitions']):
            self.cli('startup','--help',category='startup')
        one, service, ids = self.modeled(1, template)
        self.modeled(8, template); self.modeled(9, template)
        large_source = self.root/'overlimit-source.json'; dump(large_source, {'notes':'x'*(2097152+1)})
        before = self.raw_store(one)
        self.cli('source-byte-limit','collect','--root',one,'--service-root',service,'--source',large_source,category='ordinary',expected_error='workbench_document_limit')
        exact(before, self.raw_store(one)); self.check('overlimit_source_no_published_attempt', True)
        self.seed_history(one, 1000)
        for _ in range(PLAN['repetitions']):
            history = self.cli('history-1000','history','--root',one,'--object',ids[0],'--limit','1000',category='capacity')['history']
            exact(list(range(1,1001)), [row['run_id'] for row in history])
            for row in history:
                exact(expected_body(),row['body'])
            collections = self.cli('collection-history-1000','collection-history','--root',one,'--limit','1000',category='capacity')['collections']
            exact(list(range(1,1001)),[row['run_id'] for row in collections])
        self.seed_history(one, 1001)
        before = self.raw_store(one)
        self.cli('history-unpaged-overlimit','history','--root',one,'--object',ids[0],category='capacity',expected_error='workbench_query_limit')
        self.cli('history-page-overlimit','history','--root',one,'--object',ids[0],'--limit','1001',category='ordinary',expected_error='workbench_query_invalid')
        last = self.cli('history-explicit-last-page','history','--root',one,'--object',ids[0],'--limit','1','--offset','1000',category='ordinary')['history']
        exact([1001],[row['run_id'] for row in last]); exact(before,self.raw_store(one))
        store = self.root/'imported-store'; captures = self.root/'captures'; captures.mkdir(mode=0o700)
        self.cli('init-imported','init','--root',store,'--tenant',TENANT)
        expected = {}
        for index in range(1,1001):
            oid = object_id(index); name = f'Performance capture {index:04d}'; path = captures/f'{index:04d}'
            self.fixture_capture(path,oid,name,template)
            result = self.cli('import-capture','import-capture','--root',store,'--capture',path,category='ordinary' if index in (1,100,1000) else None)
            if result['status'] != 'complete' or result['object_count'] != 1:
                raise AssertionError('Scoped capture import did not complete')
            expected[oid] = expected_body(name)
            if index in (100,1000):
                self.assert_bodies(store,expected)
                for _ in range(PLAN['repetitions']):
                    overview = self.cli(f'imported-{index}-overview','overview','--root',store,category='capacity',may_limit=index==1000)
                    if 'bounded_rejection' in overview:
                        self.result['capacity_limits'].append({'objects':index,'route':'overview','reason':'workbench_query_limit','qualified_complete_inventory':False})
                    else:
                        exact(expected,{row['object_id']:row['body'] for row in overview['objects']})
                        self.check(f'imported_{index}_authority_not_promoted',overview['cloud_authority'] is False and overview['execution_authorized'] is False and all(row['source']['source_authenticity_verified'] is False for row in overview['objects']))
                self.save()
                if index == 100:
                    selected = self.cli('imported-100-inspect','inspect','--root',store,'--object',object_id(50),category='capacity')
                    exact(expected[object_id(50)], selected['body'])
                    dictionary = self.cli('imported-100-dictionary','dictionary','--root',store,'--query',DEFINITION,category='capacity')
                    dump(self.root/'dictionary-100-observation.json',dictionary)
                    # The dictionary retains every observed object; use exact immutable IDs.
                    entries = dictionary.get('settings', dictionary.get('entries', []))
                    uses = [use for entry in entries for use in entry.get('actual_uses', [])]
                    exact(sorted(expected), sorted(use['object_id'] for use in uses))
                    backup = self.root/'imported-100-backup.sqlite3'
                    backup_result = self.cli('backup-100','backup','--root',store,'--output',backup,category='capacity')
                    self.check('backup_file_exists',backup.is_file())
                    restored = self.root/'imported-100-restored'
                    self.cli('restore-100','restore','--input',backup,'--root',restored,'--tenant',TENANT,category='capacity')
                    self.assert_bodies(restored,expected)
                    self.check('backup_bytes_unchanged_after_restore',sha(backup)==backup_result.get('sha256',backup_result.get('database_sha256')))
        self.check('all_1000_imports_durably_recorded', self.raw_store(store)['complete_runs']==1000)
        self.result['source_after'] = source_map()
        exact(self.result['source_before'],self.result['source_after'])
        self.check('source_unchanged_during_final_run',True)
        self.snapshot_processes('processes-after.txt')
        self.result['load_average_after'] = os.getloadavg()
        groups = {}
        for row in self.result['commands']:
            if row['category']:
                groups.setdefault(row['label'],[]).append(row)
        self.result['measurements'] = {label:{'samples':len(rows),**{metric:{'median':statistics.median(row[metric] for row in rows),'maximum':max(row[metric] for row in rows)} for metric in ('wall_seconds','cpu_seconds','peak_rss_kib')}} for label,rows in groups.items()}
        self.result['status'] = 'PASS_SCOPED'
        self.result['finished_at'] = datetime.now(timezone.utc).isoformat()
        self.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--python',default=sys.executable)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare',action='store_true')
    action.add_argument('--run',action='store_true')
    parser.add_argument('--quiet-window',help='Coordinator attestation: no competing heavy qualification job; required for measurement.')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.output); print(str(args.output/'preregistration.json')); return 0
    if sys.platform != 'linux' or not hasattr(os,'wait4'):
        parser.error('This measurement profile requires Linux wait4 RSS semantics.')
    if not args.quiet_window:
        parser.error('--quiet-window is required; coordinate before collecting timings.')
    run = Run(args.output,args.python,args.quiet_window)
    try:
        run.execute()
    except Exception as error:
        run.result.update(status='FAIL_PRESERVED',error_type=type(error).__name__,error=str(error),finished_at=datetime.now(timezone.utc).isoformat())
        (args.output/'failure-traceback.txt').write_text(traceback.format_exc())
        run.save(); print(str(args.output/'receipt.json')); return 1
    print(str(args.output/'receipt.json')); return 0


if __name__ == '__main__':
    raise SystemExit(main())
