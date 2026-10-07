"""Actual independent-process reader job routing and durable failure recovery."""
import copy
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from intune_iac.io import AppError, canonical, digest, load_json, write_json
from intune_iac.observation_jobs import create_job, job_status, run_due, scheduler_artifacts
from intune_iac.observation_reader import ReaderSpec
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore
from plugin_tests.test_observation_reader_r4 import CLIENT, PRINCIPAL, SECRET, TOKEN, fixture_for

PROJECT = Path(__file__).resolve().parents[1]
ENV_KEY = 'INTUNE_R4_SYNTHETIC_READER_SECRET'


class ObservationJobsR4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.estate = generate_estate(seed=846, policy_count=1)
        self.tenant = self.estate['truth']['tenant_id']
        self.oid = self.estate['truth']['policies'][0]['id']
        self.spec = ReaderSpec(self.tenant, CLIENT, PRINCIPAL, (self.oid,))
        self.store = WorkbenchStore.create(self.root / 'store', self.tenant)
        self.fixture = self.root / 'fixture.json'
        write_json(self.fixture, fixture_for(self.estate))
        self.job = self.root / 'job'

    def create(self, laboratory=True):
        return create_job(self.store, self.spec, output=self.job, secret_env=ENV_KEY, interval_seconds=60,
                          laboratory_fixture=self.fixture if laboratory else None)

    def cli(self, *args, secret=True):
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
        if secret:
            env[ENV_KEY] = SECRET
        result = subprocess.run([sys.executable, '-I', '-B', str(PROJECT / 'scripts/intune-iac.py'),
            'workbench', *map(str, args)], cwd=self.root, env=env, capture_output=True, timeout=15)
        value = json.loads(result.stdout or result.stderr)
        return result, value

    def due(self):
        state = load_json(self.job / 'state.json')
        state['next_due'] = '2026-01-01T00:00:00Z'
        write_json(self.job / 'state.json', state)

    def test_cli_complete_cycle_with_no_terminal_and_reopened_persistence(self):
        created = self.create()
        self.assertEqual(self.store.collection_history(), [])
        result, value = self.cli('observer-run', '--job', self.job)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(value['status'], 'complete')
        self.assertEqual(value['success_count'], 1)
        self.assertEqual(len(self.store.history(self.oid)), 1)
        result, status = self.cli('observer-status', '--job', self.job)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(status['job_id'], created['job_id'])
        self.assertEqual(status['status'], 'idle')
        self.assertEqual(status['freshness'], 'fresh')
        receipt = load_json(value['attempt_receipt'])
        self.assertEqual(receipt['profile'], 'laboratory_recorded_responses')
        self.assertFalse(receipt['source_authenticity_verified'])
        self.assertEqual(receipt['laboratory_unconsumed_responses'], 0)

    def test_not_due_does_not_read_missing_credentials_or_add_history(self):
        self.create()
        result, value = self.cli('observer-run', '--job', self.job)
        self.assertEqual(result.returncode, 0)
        result, second = self.cli('observer-run', '--job', self.job, secret=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(second['status'], 'not_due')
        self.assertFalse(second['network_attempted'])
        self.assertEqual(len(self.store.collection_history()), 1)

    def test_live_missing_secret_fails_before_network_and_records_unknown_scope(self):
        self.create(laboratory=False)
        result, value = self.cli('observer-run', '--job', self.job, secret=False)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(value['last_error'], 'observer_credential_missing')
        self.assertEqual(value['failure_count'], 1)
        self.assertIsNone(value['last_success'])
        record = self.store.collection_history()[0]
        self.assertEqual(record['evidence_class'], 'graph_reader_attempt')
        self.assertFalse(record['assurance']['source_authenticity_verified'])
        self.assertIsNone(self.store.inspect(self.oid)['body'])
        self.assertEqual(self.store.inspect(self.oid)['evidence_class'], 'graph_reader_attempt')

    def test_wrong_identity_fixture_is_not_promoted_to_authenticated_collection(self):
        fixture = load_json(self.fixture)
        fixture['responses'][1]['body']['id'] = CLIENT
        write_json(self.fixture, fixture)
        self.create()
        result, value = self.cli('observer-run', '--job', self.job)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(value['last_error'], 'reader_principal_mismatch')
        receipt = load_json(value['attempt_receipt'])
        self.assertEqual(len(receipt['laboratory_requests']), 2)
        self.assertEqual(self.store.history(self.oid), [])

    def test_concurrent_invocation_rejected_without_an_attempt(self):
        self.create()
        fd = os.open(self.job / 'schedule.lock', os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result, value = self.cli('observer-run', '--job', self.job)
        finally:
            os.close(fd)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(value['error']['code'], 'scheduler_already_running')
        self.assertEqual(job_status(self.job)['run_count'], 0)
        self.assertEqual(self.store.collection_history(), [])

    def test_config_and_fixture_changes_are_not_silently_accepted(self):
        self.create()
        write_json(self.fixture, {**load_json(self.fixture), 'unauthorized': True})
        result, value = self.cli('observer-run', '--job', self.job)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(value['last_error'], 'observer_fixture_changed')
        config = load_json(self.job / 'config.json')
        config['identity']['tenant_id'] = CLIENT
        write_json(self.job / 'config.json', config)
        result, value = self.cli('observer-run', '--job', self.job)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(value['error']['code'], 'observer_config_changed')

    def test_interrupted_record_is_recovered_without_reimporting_staged_bytes(self):
        self.create()
        state = load_json(self.job / 'state.json')
        config = load_json(self.job / 'config.json')
        attempt = 'c' * 32
        record = {'job_id': config['job_id'], 'attempt_id': attempt, 'status': 'collecting',
                  'started_at': state['next_due'], 'next_due': '2099-01-01T00:00:00Z', 'capture_bytes': 0}
        state.update(active_attempt=attempt, active_record=record, run_count=1)
        write_json(self.job / 'state.json', state)
        result, value = self.cli('observer-run', '--job', self.job, secret=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(value['status'], 'not_due')
        self.assertEqual(value['interrupted_count'], 1)
        restored = load_json(self.job / 'runs' / (attempt + '.json'))
        self.assertEqual(restored['status'], 'interrupted')
        self.assertEqual(restored['persisted_collection_run_ids'], [1])
        self.assertFalse(restored['publication_found_before_recovery'])
        self.assertEqual(self.store.collection_history()[0]['evidence_class'], 'graph_reader_attempt')
        self.assertEqual(self.store.history(self.oid), [])

    def test_killed_separate_collector_releases_lock_and_recovers_unknown_scope(self):
        self.create()
        marker = self.root / 'collector-entered-read'
        # Explicit laboratory instrumentation delays a read before response;
        # the actual CLI owns its persisted attempt and process-held flock.
        program = '''import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from intune_iac import observation_jobs as jobs
original=jobs._Fixture.__call__
def paused(self,request,**kwargs):
    if request.path.endswith('/configurationPolicies'):
        Path(sys.argv[3]).write_text('waiting')
        time.sleep(30)
    return original(self,request,**kwargs)
jobs._Fixture.__call__=paused
from intune_iac.cli import main
raise SystemExit(main(['workbench','observer-run','--job',sys.argv[2]]))
'''
        process = subprocess.Popen([sys.executable, '-I', '-B', '-c', program, str(PROJECT), str(self.job), str(marker)],
            cwd=self.root, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', ENV_KEY: SECRET},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists())
            self.assertTrue(job_status(self.job)['lock_held'])
            process.kill()
            process.communicate(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
        self.assertEqual(process.returncode, -9)
        self.assertFalse(job_status(self.job)['lock_held'])
        self.assertEqual(job_status(self.job)['status'], 'interrupted_or_unconfirmed')
        result, value = self.cli('observer-run', '--job', self.job, secret=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(value['status'], 'not_due')
        self.assertEqual(value['interrupted_count'], 1)
        self.assertEqual(self.store.collection_history()[0]['source']['error_code'], 'observer_previous_runner_interrupted')
        self.assertEqual(self.store.history(self.oid), [])

    def test_partial_database_publication_keeps_old_values_and_staged_capture(self):
        self.create()
        with patch.dict(os.environ, {ENV_KEY: SECRET}), patch(
                'intune_iac.observation_jobs.publish_batch', side_effect=AppError('deliberate_write_failure', 'test')):
            value = run_due(self.job)
        self.assertEqual(value['status'], 'failed')
        self.assertEqual(self.store.collection_history(), [])
        self.assertTrue(list((self.job / 'captures').glob('*/' + self.oid + '/capture-receipt.json')))
        self.assertEqual(job_status(self.job)['failure_count'], 1)

    def test_scheduler_units_are_inactive_and_bind_exact_argv(self):
        self.create()
        result, value = self.cli('observer-scheduler', '--job', self.job, '--output', self.root / 'units')
        self.assertEqual(result.returncode, 0)
        self.assertFalse(value['installed'])
        self.assertFalse(value['activated'])
        self.assertIn('--job', value['argv'])
        self.assertIn(str(self.job), value['argv'])
        text = (self.root / 'units/intune-observer.service').read_text()
        self.assertIn('EnvironmentFile=/REPLACE/', text)
        self.assertIn('KillMode=control-group', text)
        self.assertEqual(job_status(self.job)['run_count'], 0)

    def test_unit_quoting_and_unsupported_host_are_explicit(self):
        self.job = self.root / 'job %name "quoted"'
        self.create()
        result = scheduler_artifacts(self.job, self.root / 'escaped-units')
        service = (self.root / 'escaped-units/intune-observer.service').read_text()
        self.assertIn('%%name', service)
        self.assertIn('\\"quoted\\"', service)
        self.assertEqual(result['argv'][-1], str(self.job))
        with patch('intune_iac.observation_jobs.sys.platform', 'win32'), self.assertRaises(AppError) as raised:
            job_status(self.job)
        self.assertEqual(raised.exception.code, 'observer_platform_unsupported')

    def test_source_change_after_reads_blocks_publication(self):
        self.create()
        with patch.dict(os.environ, {ENV_KEY: SECRET}), patch(
                'intune_iac.observation_jobs.common._validate_runtime',
                side_effect=[None, AppError('scheduler_runtime_changed', 'test')]):
            value = run_due(self.job)
        self.assertEqual(value['status'], 'failed')
        self.assertEqual(value['last_error'], 'scheduler_runtime_changed')
        self.assertEqual(self.store.collection_history(), [])
        self.assertTrue(list((self.job / 'captures').glob('*/' + self.oid + '/capture-receipt.json')))

    def test_status_exposes_stale_runtime_binding_without_modifying_job(self):
        self.create()
        before = (self.job / 'state.json').read_bytes()
        with patch('intune_iac.observation_jobs.common._validate_runtime',
                   side_effect=AppError('scheduler_runtime_changed', 'test')):
            status = job_status(self.job)
        self.assertEqual(status['status'], 'blocked')
        self.assertFalse(status['source_and_store_binding_valid'])
        self.assertEqual(status['binding_error'], 'scheduler_runtime_changed')
        self.assertEqual((self.job / 'state.json').read_bytes(), before)

    def test_secrets_absent_from_job_artifacts_and_database(self):
        self.create()
        result, value = self.cli('observer-run', '--job', self.job)
        self.assertEqual(result.returncode, 0)
        for path in [self.store.path, *(path for path in self.job.rglob('*') if path.is_file())]:
            raw = path.read_bytes()
            self.assertNotIn(SECRET.encode(), raw, str(path))
            self.assertNotIn(TOKEN.encode(), raw, str(path))

    def test_stale_job_health_never_reports_endpoint_health(self):
        self.create()
        with patch.dict(os.environ, {ENV_KEY: SECRET}):
            value = run_due(self.job)
        self.assertEqual(value['status'], 'complete')
        state = load_json(self.job / 'state.json')
        state['last_success'] = '2026-01-01T00:00:00Z'
        write_json(self.job / 'state.json', state)
        status = job_status(self.job)
        self.assertEqual(status['freshness'], 'stale')
        self.assertFalse(status['production_qualified'])
        self.assertFalse(status['mutation_authorized'])

    def test_future_last_success_cannot_claim_freshness_after_clock_regression(self):
        self.create()
        state = load_json(self.job / 'state.json')
        state['last_success'] = '2099-01-01T00:00:00Z'
        write_json(self.job / 'state.json', state)
        self.assertEqual(job_status(self.job)['freshness'], 'stale')


if __name__ == '__main__':
    unittest.main()
