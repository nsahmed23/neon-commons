"""Finite local scheduling through actual guarded headless CLI processes."""
import copy
import fcntl
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from intune_iac import workbench_scheduler as scheduler
from intune_iac.io import AppError, load_json, write_json
from intune_iac.modeled_service import BASE, ModeledService
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore


class WorkbenchSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        estate = generate_estate(seed=710, policy_count=3)
        self.tenant = estate['truth']['tenant_id']
        self.ids = [p['id'] for p in estate['truth']['policies']]
        self.service = ModeledService.create(self.root / 'service', estate['capture'], self.ids)
        self.store = WorkbenchStore.create(self.root / 'store', self.tenant)
        self.job = self.root / 'schedule'

    def create(self, interval=0.1):
        return scheduler.create_schedule(self.store, self.service.root, interval, self.job)

    def rows(self):
        with sqlite3.connect(self.store.path) as db:
            return db.execute('SELECT run_id,status,observed_at FROM collection_runs ORDER BY run_id').fetchall()

    def test_finite_real_subprocesses_collect_with_terminal_closed_and_link_history(self):
        created = self.create()
        self.assertEqual(self.rows(), [])
        result = scheduler.run_schedule(self.job, max_runs=3, max_duration_seconds=5)
        self.assertEqual(result['runs_executed'], 3)
        self.assertEqual(result['success_count'], 3)
        self.assertEqual(len(self.rows()), 3)
        self.assertTrue(all(row[1] == 'complete' for row in self.rows()))
        self.assertTrue(all(row['method'] == 'GET' for row in self.service.snapshot()['requests']))
        self.assertEqual(len(self.store.history(self.ids[0])), 3)
        artifacts = self.store.artifacts(kind='schedule')
        success = [row for row in artifacts if row['data'].get('status') == 'complete']
        self.assertEqual(len(success), 3)
        self.assertEqual({row['data']['collection_run_id'] for row in success}, {1, 2, 3})
        status = scheduler.schedule_status(self.job)
        self.assertEqual(status['job_id'], created['job_id'])
        self.assertIsNotNone(status['last_success'])
        self.assertFalse(status['cloud_authority'])
        self.assertFalse(status['daemon_installed'])

    def test_service_revision_change_is_collected_without_changing_job_identity(self):
        self.create(); scheduler.run_schedule(self.job, 1, 3)
        body = copy.deepcopy(self.service.snapshot()['current']['objects'][self.ids[0]])
        body['description'] = 'A separate explicitly authorized modeled change'
        self.service.request('PATCH', BASE + '/' + self.ids[0], tenant_id=self.tenant, body=body, if_match='1')
        scheduler.run_schedule(self.job, 1, 3)
        self.assertEqual(self.store.inspect(self.ids[0])['body'], body)
        self.assertEqual(len(self.store.history(self.ids[0])), 2)

    def test_overlap_is_rejected_before_any_collection(self):
        self.create()
        fd = os.open(self.job / 'schedule.lock', os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(AppError) as raised: scheduler.run_schedule(self.job, 1, 3)
        finally: os.close(fd)
        self.assertEqual(raised.exception.code, 'scheduler_already_running')
        self.assertEqual(self.rows(), [])

    def test_target_and_config_substitution_are_rejected(self):
        self.create()
        state = self.service.snapshot(); state['source_sha256'] = '0' * 64
        write_json(self.service.path, state)
        with self.assertRaises(AppError) as raised: scheduler.run_schedule(self.job, 1, 3)
        self.assertEqual(raised.exception.code, 'scheduler_source_changed')
        self.assertEqual(self.rows(), [])
        config = load_json(self.job / 'config.json'); config['interval_seconds'] = 100
        write_json(self.job / 'config.json', config)
        with self.assertRaises(AppError) as raised: scheduler.run_schedule(self.job, 1, 3)
        self.assertEqual(raised.exception.code, 'scheduler_config_changed')

    def test_boundaries_reject_nonfinite_unbounded_and_boolean_inputs(self):
        for interval in (0, 0.01, 86401, True, float('inf')):
            with self.subTest(interval=interval), self.assertRaises(AppError): self.create(interval)
        self.create()
        for count, duration in ((0, 3), (1001, 3), (True, 3), (1, 0.1), (1, 3601), (1, float('nan'))):
            with self.subTest(count=count, duration=duration), self.assertRaises(AppError):
                scheduler.run_schedule(self.job, count, duration)
        self.assertEqual(self.rows(), [])

    def test_missed_cycles_are_counted_without_unbounded_catch_up(self):
        self.create(0.1)
        time.sleep(0.45)
        result = scheduler.run_schedule(self.job, 1, 3)
        self.assertEqual(result['runs_executed'], 1)
        self.assertGreaterEqual(result['missed_cycles'], 4)
        self.assertEqual(len(self.rows()), 1)

    def test_duration_stops_waiting_without_background_daemon(self):
        self.create(60)
        scheduler.run_schedule(self.job, 1, 3)
        started = time.monotonic()
        result = scheduler.run_schedule(self.job, 10, 1)
        self.assertLess(time.monotonic() - started, 1.7)
        self.assertEqual(result['runs_executed'], 0)
        self.assertEqual(result['stop_reason'], 'duration_limit')
        self.assertEqual(len(self.rows()), 1)

    def test_collection_failure_preserves_last_success_and_can_resume_readonly(self):
        self.create(); scheduler.run_schedule(self.job, 1, 3)
        previous = scheduler.schedule_status(self.job)['last_success']
        fd = os.open(self.service.root / 'service.lock', os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = scheduler.run_schedule(self.job, 1, 3)
        finally: os.close(fd)
        self.assertEqual(result['runs_executed'], 1)
        self.assertEqual(result['failure_count'], 1)
        self.assertEqual(result['last_success'], previous)
        self.assertEqual(result['consecutive_failures'], 1)
        resumed = scheduler.run_schedule(self.job, 1, 3)
        self.assertEqual(resumed['success_count'], 2)
        self.assertEqual(resumed['consecutive_failures'], 0)
        self.assertTrue(all(r['method'] == 'GET' for r in self.service.snapshot()['requests']))

    def _runner(self):
        code = ('import sys\nfrom intune_iac.workbench_scheduler import run_schedule\n'
                'run_schedule(sys.argv[1],100,20)\n')
        return subprocess.Popen([sys.executable, '-B', '-c', code, str(self.job)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _active_child(self, runner):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if runner.poll() is not None:
                self.fail('Runner ended before collection dispatch: ' + runner.stderr.read().decode())
            # Observe the atomically replaced state directly; this independent
            # test reader may retain an unlinked old inode during a rename.
            state = json.loads((self.job / 'state.json').read_text())
            children = []
            for path in Path('/proc').iterdir():
                if not path.name.isdigit(): continue
                try: fields = (path / 'stat').read_bytes().rsplit(b') ', 1)[1].split()
                except (FileNotFoundError, ProcessLookupError): continue
                if int(fields[1]) == runner.pid: children.append(int(path.name))
            if state.get('active_run') and children:
                return children[0]
            time.sleep(0.001)
        self.fail('No actual collector process observed')

    def test_real_sigint_cleans_child_and_preserves_interrupted_run(self):
        self.create(); runner = self._runner()
        try:
            child = self._active_child(runner)
            os.kill(runner.pid, signal.SIGINT)
            runner.communicate(timeout=5)
            self.assertNotEqual(runner.returncode, 0)
            observed = Path('/proc') / str(child) / 'stat'
            if observed.exists(): self.assertIn(observed.read_bytes().rsplit(b') ', 1)[1].split()[0], (b'Z', b'X'))
            result = scheduler.run_schedule(self.job, 1, 3)
            self.assertGreaterEqual(result['interrupted_count'], 1)
            self.assertEqual(result['success_count'], 1)
        finally:
            if runner.poll() is None: runner.kill(); runner.communicate(timeout=5)

    def test_sigkill_parent_keeps_child_lock_then_recovers_without_operation_replay(self):
        self.create(); runner = self._runner(); child = None
        try:
            child = self._active_child(runner)
            os.kill(child, signal.SIGSTOP)
            runner.kill(); runner.communicate(timeout=5)
            with self.assertRaises(AppError) as raised: scheduler.run_schedule(self.job, 1, 3)
            self.assertEqual(raised.exception.code, 'scheduler_already_running')
            os.kill(child, signal.SIGCONT)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    result = scheduler.run_schedule(self.job, 1, 3)
                    break
                except AppError as error:
                    if error.code != 'scheduler_already_running': raise
                    time.sleep(0.01)
            else: self.fail('Orphan collector did not release inherited lock')
            self.assertEqual(result['interrupted_count'], 1)
            self.assertTrue(all(r['method'] == 'GET' for r in self.service.snapshot()['requests']))
            interrupted = [p for p in (self.job / 'runs').glob('*.json')
                           if not p.name.endswith('.source.json') and load_json(p).get('status') == 'interrupted']
            self.assertEqual(len(interrupted), 1)
        finally:
            if runner.poll() is None: runner.kill(); runner.communicate(timeout=5)
            if child is not None:
                try: os.kill(child, signal.SIGKILL)
                except ProcessLookupError: pass


if __name__ == '__main__': unittest.main()
