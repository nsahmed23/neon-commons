"""Actual subprocess terminal and headless collection integration contracts."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from intune_iac.synthetic import generate_estate
from intune_iac.modeled_service import BASE, ModeledService
from intune_iac.workbench import _render


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'


class WorkbenchCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.estate = generate_estate(seed=501, policy_count=2)
        self.tenant = self.estate['truth']['tenant_id']
        self.ids = [p['id'] for p in self.estate['truth']['policies']]
        self.store = self.root / 'memory'
        self.service = self.root / 'service'
        self.capture = self.root / 'capture.json'
        self.capture.write_text(json.dumps(self.estate['capture']))
        self.call('init', '--root', self.store, '--tenant', self.tenant)
        self.call('lab-create', '--service-root', self.service, '--input', self.capture,
                  '--object', self.ids[0], '--object', self.ids[1])

    def process(self, *args, input=None, columns=None):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        if columns is not None: env['COLUMNS'] = str(columns)
        return subprocess.run([sys.executable, '-B', str(CLI), 'workbench', *map(str, args)],
                              input=input, text=True, capture_output=True, cwd='/tmp', timeout=30, env=env)

    def call(self, *args):
        result = self.process(*args)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def collect(self, *args):
        return self.call('collect', '--root', self.store, '--service-root', self.service, *args)

    def test_commands_discoverable_and_store_usable_without_repository(self):
        help_result = self.process('--help')
        self.assertEqual(help_result.returncode, 0)
        for name in ('terminal', 'collect', 'inspect', 'history', 'compare', 'propose', 'execute', 'reconcile'):
            self.assertIn(name, help_result.stdout)
        empty = self.call('overview', '--root', self.store)
        self.assertEqual(empty['objects'], [])
        self.assertEqual(empty['freshness'], 'unknown')
        self.assertFalse(empty['cloud_authority'])

    def test_closed_terminal_collection_reopen_and_denied_retains_values(self):
        closed = self.process('terminal', '--root', self.store, input='quit\n')
        self.assertEqual(closed.returncode, 0, closed.stderr)
        self.assertEqual(self.collect()['status'], 'complete')
        before = self.call('inspect', '--root', self.store, '--object', self.ids[0])
        denied = self.process('collect', '--root', self.store, '--service-root', self.service, '--fault', 'deny')
        self.assertNotEqual(denied.returncode, 0)
        self.assertEqual(json.loads(denied.stdout)['status'], 'denied')
        after = self.call('inspect', '--root', self.store, '--object', self.ids[0])
        self.assertEqual(after['body'], before['body'])
        self.assertEqual(after['last_attempt']['status'], 'denied')
        reopened = self.process('terminal', '--root', self.store,
                                input=f'select {self.ids[0]}\nsettings\nrelationships\nhistory\nhealth\nback\nquit\n')
        self.assertEqual(reopened.returncode, 0, reopened.stderr)
        self.assertIn('exclusionGroupAssignmentTarget', reopened.stdout)
        self.assertIn('workbench_collection_denied', reopened.stdout)
        self.assertIn('selection_cleared', reopened.stdout)

    def test_duplicate_names_require_exact_identity_and_preserve_source(self):
        source = self.root / 'source.json'
        source.write_text(json.dumps({'repository_path': '/declared/repo', 'source_path': 'stacks/lab.yaml',
                                      'atmos_stack': 'lab', 'inheritance': ['defaults', 'lab']}))
        self.collect('--source', source)
        found = self.call('search', '--root', self.store, '--query', 'Privacy')
        self.assertEqual(len(found['objects']), 2)
        result = self.process('terminal', '--root', self.store,
                              input=f'select "{found["objects"][0]["name"]}"\nselect {self.ids[0]}\nrelationships\nquit\n')
        self.assertIn('workbench_identity_invalid', result.stdout)
        self.assertIn('source_repository_path', result.stdout)
        self.assertIn('stacks/lab.yaml', result.stdout)

    def test_history_compare_survives_new_process_and_reports_typed_change(self):
        self.collect()
        old = self.call('inspect', '--root', self.store, '--object', self.ids[0])
        service = ModeledService(self.service)
        desired = copy.deepcopy(old['body'])
        desired['description'] = 'An intentional lab correction'
        response = service.request('PATCH', BASE + '/' + self.ids[0], tenant_id=self.tenant,
                                   body=desired, if_match=str(service.snapshot()['revision']))
        self.assertEqual(response['status'], 200)
        self.collect()
        history = self.call('history', '--root', self.store, '--object', self.ids[0])['history']
        self.assertEqual(len(history), 2)
        page = self.call('history', '--root', self.store, '--object', self.ids[0], '--limit', 1, '--offset', 1)
        self.assertEqual(page['history'], history[1:])
        compared = self.call('compare', '--root', self.store, '--object', self.ids[0],
                             '--before', history[0]['snapshot_id'], '--after', history[1]['snapshot_id'])
        self.assertEqual([c['field'] for c in compared['changes']], ['description'])
        self.assertIsNone(compared['changed_at'])

    def test_health_does_not_turn_eight_reporting_successes_into_fleet_success(self):
        deployment = self.root / 'deployment.json'
        deployment.write_text(json.dumps({'targeted': 100, 'reporting': 8, 'successful': 8}))
        self.collect('--deployment', deployment)
        health = self.call('health', '--root', self.store)['health']
        self.assertEqual(health['reporting_success_percent'], 100)
        self.assertEqual(health['targeted_success_percent'], 8)
        self.assertEqual(health['unknown_or_stale'], 92)
        self.assertFalse(health['rollout_ready'])
        self.assertEqual(health['endpoint_health'], 'unknown')

    def test_no_tty_narrow_terminal_escape_safety_raw_value_preserved(self):
        self.collect()
        service = ModeledService(self.service)
        desired = copy.deepcopy(service.snapshot()['current']['objects'][self.ids[0]])
        hostile = 'Policy\x1b]52;c;canary\x07\rFORGED\b\u202e approval'
        desired['name'] = hostile
        service.request('PATCH', BASE + '/' + self.ids[0], tenant_id=self.tenant,
                        body=desired, if_match=str(service.snapshot()['revision']))
        self.collect()
        result = self.process('terminal', '--root', self.store, input=f'select {self.ids[0]}\nquit\n', columns=32)
        self.assertEqual(result.returncode, 0, result.stderr)
        for unsafe in ('\x1b', '\x07', '\r', '\b', '\u202e'):
            self.assertNotIn(unsafe, result.stdout)
        self.assertIn('\\u001b', result.stdout)
        original = self.call('inspect', '--root', self.store, '--object', self.ids[0])
        self.assertEqual(original['body']['name'], hostile)
        # Final CLI result is automation JSON, while terminal presentation wraps.
        terminal_lines = result.stdout.splitlines()[:-1]
        self.assertTrue(all(len(line) <= 32 or line.startswith('workbench> ') for line in terminal_lines))

    def test_eof_and_cancel_do_not_dispatch_model_mutation(self):
        self.collect()
        initial = ModeledService(self.service).snapshot()['current']
        result = self.process('terminal', '--root', self.store, '--service-root', self.service,
                              input=f'select {self.ids[0]}\ncancel\ninspect\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('selection_required', result.stdout)
        self.assertEqual(ModeledService(self.service).snapshot()['current'], initial)

    def test_dictionary_and_queue_use_observations_without_inventing_authority(self):
        self.collect()
        setting_id = self.estate['truth']['policies'][0]['settings']['settings'][0]['settingInstance']['settingDefinitionId']
        dictionary = self.call('dictionary', '--root', self.store, '--query', setting_id)
        self.assertEqual(len(dictionary['entries']), 1)
        entry = dictionary['entries'][0]
        self.assertEqual(entry['meaning'], 'unknown')
        self.assertEqual({use['object_id'] for use in entry['actual_uses']}, set(self.ids))
        self.assertEqual(entry['actual_uses'][0]['value']['settingDefinitionId'], setting_id)
        self.assertEqual(len(self.call('search', '--root', self.store, '--query', setting_id)['objects']), 2)
        queue = self.call('queue', '--root', self.store)
        self.assertEqual({row['finding'] for row in queue['findings']}, {'reporting_incomplete', 'ownership_unknown'})
        self.assertTrue(all(row['action_state'] == 'review_required' and not row['automatic_remediation'] for row in queue['findings']))
        self.assertFalse(queue['cloud_authority'])

    def test_explicit_repository_collection_retains_actual_literal_inheritance(self):
        repo = self.root / 'repo'
        (repo / 'stacks/deploy').mkdir(parents=True)
        (repo / 'components/terraform/app').mkdir(parents=True)
        (repo / 'atmos.yaml').write_text('stacks:\n  base_path: stacks\n  included_paths: ["deploy/**/*"]\ncomponents:\n  terraform:\n    base_path: components/terraform\n    command: tofu\n')
        (repo / 'stacks/base.yaml').write_text('vars:\n  region: inherited\n')
        (repo / 'stacks/deploy/dev.yaml').write_text('import: [base]\ncomponents:\n  terraform:\n    app:\n      vars:\n        enabled: true\n')
        self.collect('--repo', repo, '--stack', 'deploy/dev', '--component', 'app')
        source = self.call('inspect', '--root', self.store, '--object', self.ids[0])['source']
        self.assertEqual(source['repository_resolution']['status'], 'resolved')
        self.assertIn('/vars/region', source['inheritance'])
        self.assertNotIn('effective', source['repository_resolution'])
        self.assertFalse(source['repository_resolution']['execution_authorized'])

    def test_terminal_connected_proposal_exact_review_execution_readback(self):
        self.collect()
        before = ModeledService(self.service).snapshot()['current']
        desired = copy.deepcopy(before['objects'][self.ids[0]])
        desired['description'] = 'Reviewed synthetic maintenance'
        desired_path = self.root / 'desired.json'
        desired_path.write_text(json.dumps(desired))
        operation = self.root / 'operation'
        proposed = self.process('terminal', '--root', self.store, '--service-root', self.service,
            input=f'select {self.ids[0]}\npropose {desired_path} {operation}\nquit\n')
        self.assertEqual(proposed.returncode, 0, proposed.stderr)
        self.assertTrue((operation / 'plan.json').exists(), proposed.stdout)
        review = self.call('review', '--operation', operation)
        self.assertFalse(review['native_provider_qualified'])
        executed = self.process('terminal', '--root', self.store, '--service-root', self.service,
            input=f'review {operation}\nexecute {operation} {review["approval_digest"]}\nreconcile {operation}\ncollect\nquit\n')
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertIn('succeeded_verified', executed.stdout)
        self.assertIn('no_change', executed.stdout)
        observed = ModeledService(self.service).snapshot()['current']
        self.assertEqual(observed['objects'][self.ids[0]], desired)
        self.assertEqual(observed['objects'][self.ids[1]], before['objects'][self.ids[1]])
        self.assertEqual(len(self.call('history', '--root', self.store, '--object', self.ids[0])['history']), 2)
        restore = self.call('restore-propose', '--operation', operation, '--output', self.root / 'restore-operation')
        self.assertNotEqual(restore['operation_id'], review['operation_id'])
        self.assertNotEqual(restore['approval_digest'], review['approval_digest'])
        self.assertEqual(restore['desired'], before['objects'][self.ids[0]])
        self.assertEqual(ModeledService(self.service).snapshot()['current'], observed)

    @unittest.skipUnless(os.name == 'posix', 'Actual PTY requires a supported Unix host; Windows qualification remains external.')
    def test_actual_pty_keyboard_navigation_and_resize(self):
        import fcntl
        import pty
        import select
        import struct
        import termios
        self.collect()
        master, slave = pty.openpty()
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
            process = subprocess.Popen([sys.executable, '-B', str(CLI), 'workbench', 'terminal', '--root', str(self.store)],
                stdin=slave, stdout=slave, stderr=slave, cwd='/tmp', env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
            os.close(slave); slave = None
            received = bytearray()
            deadline = time.monotonic() + 10
            sent = False
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try: data = os.read(master, 65536)
                    except OSError: break
                    if not data: break
                    received.extend(data)
                    if b'workbench> ' in received and not sent:
                        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 40, 0, 0))
                        os.write(master, f'search Privacy\nselect {self.ids[0]}\nhistory\nback\nquit\n'.encode())
                        sent = True
                if process.poll() is not None and not ready: break
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
                self.fail('Workbench terminal did not stop within the PTY deadline.')
            self.assertEqual(process.wait(timeout=5), 0, received.decode(errors='replace'))
            transcript = received.decode('utf-8')
            self.assertIn('selection_cleared', transcript)
            self.assertIn('history_persisted', transcript)
            self.assertIn(self.ids[0], transcript)
            self.assertNotIn('Traceback', transcript)
        finally:
            os.close(master)
            if slave is not None: os.close(slave)

    def test_backup_restore_commands_preserve_history_without_remote_action(self):
        self.collect()
        backup = self.root / 'memory.sqlite3'
        receipt = self.call('backup', '--root', self.store, '--output', backup)
        self.assertEqual(len(receipt['sha256']), 64)
        restored_root = self.root / 'restored'
        restored = self.call('restore', '--input', backup, '--root', restored_root, '--tenant', self.tenant)
        self.assertFalse(restored['remote_infrastructure_restored'])
        self.assertEqual(len(self.call('history', '--root', restored_root, '--object', self.ids[0])['history']), 1)

    def test_local_capture_import_and_collection_details_remain_unverified(self):
        from intune_iac.capture import capture as capture_pages
        capture = self.root / 'single-capture'
        source = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        original_id = source['collections'][1]['owner_id']
        responses = {}
        for collection in source['collections']:
            for page in collection['pages']:
                body = copy.deepcopy(page['body'])
                if collection['kind'] == 'policies': body['value'][0]['id'] = self.ids[0]
                if collection['kind'] == 'assignments':
                    for assignment in body['value']: assignment.update(source='direct', sourceId=None)
                responses[page['request_url'].replace(original_id, self.ids[0])] = (page['http_status'], json.dumps(body).encode())
        capture_pages(self.tenant, self.ids[0], capture, transport=lambda url: responses[url])
        before = ModeledService(self.service).snapshot()
        run = self.call('import-capture', '--root', self.store, '--capture', capture)
        self.assertEqual(run['status'], 'complete')
        self.assertEqual(run['evidence_class'], 'graph_capture_unverified')
        self.assertFalse(run['assurance']['source_authenticity_verified'])
        self.assertEqual(self.call('collection', '--root', self.store, '--run', run['run_id']), run)
        history = self.call('collection-history', '--root', self.store, '--object', self.ids[0])
        self.assertEqual(history['collections'], [run])
        result = self.process('terminal', '--root', self.store,
            input=f'select {self.ids[0]}\ncollection-history\ncollection {run["run_id"]}\nsettings\nquit\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('graph_capture_unverified', result.stdout)
        self.assertEqual(ModeledService(self.service).snapshot(), before)

    def test_device_evidence_health_and_workflow_lineage_are_policy_bound(self):
        from plugin_tests.test_workbench_health import document
        self.collect()
        observed = self.call('inspect', '--root', self.store, '--object', self.ids[0])
        evidence = document(); stamp = datetime.now(timezone.utc).isoformat()
        evidence['as_of'] = stamp
        for row in evidence['rows']: row['observed_at'] = stamp
        envelope = {'schema_version': 'workbench-device-evidence/1', 'tenant_id': self.tenant,
                    'object_id': self.ids[0], 'evidence': evidence}
        path = self.root / 'device.json'; path.write_text(json.dumps(envelope))
        imported = self.call('device-evidence-import', '--root', self.store, '--input', path)
        self.assertEqual(imported['data']['source_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        health = self.call('health', '--root', self.store, '--object', self.ids[0])
        self.assertEqual(health['stages']['execution']['reporting_success_percent'], 100)
        self.assertEqual(health['stages']['execution']['targeted_success_percent'], 8)
        self.assertEqual(health['stages']['effective_state']['unknown'], 100)
        self.assertFalse(health['rollout_ready'])
        other = self.call('health', '--root', self.store, '--object', self.ids[1])
        self.assertEqual(other['evidence_class'], 'unknown')
        self.assertIsNone(other['stages']['execution']['targeted'])
        workflow = {'schema_version': 'workbench-workflow-run/1', 'tenant_id': self.tenant,
            'object_id': self.ids[0], 'run_url': 'https://github.com/example/repo/actions/runs/42',
            'repository_revision': 'b' * 40, 'run_id': '42', 'status': 'success',
            'observed_at': datetime.now(timezone.utc).isoformat(), 'observed_after': observed['snapshot_id']}
        path = self.root / 'workflow.json'; path.write_text(json.dumps(workflow))
        self.call('workflow-import', '--root', self.store, '--input', path)
        lineage = self.call('workflows', '--root', self.store, '--object', self.ids[0])
        self.assertEqual(len(lineage['runs']), 1)
        self.assertFalse(lineage['external_execution_verified'])
        result = self.process('terminal', '--root', self.store,
            input=f'select {self.ids[0]}\nhealth\nworkflows\nrelationships\nquit\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('caller_asserted_time_order', result.stdout)
        envelope['tenant_id'] = self.ids[0]; path.write_text(json.dumps(envelope))
        self.assertNotEqual(self.process('device-evidence-import', '--root', self.store, '--input', path).returncode, 0)

    def test_reference_import_comparison_and_terminal_preserve_exact_ids(self):
        self.collect()
        policy = self.estate['truth']['policies'][0]
        reference = {'id': self.ids[1], 'name': 'Community reference',
                     'settings': policy['settings']['settings']}
        path = self.root / 'reference.json'; path.write_text(json.dumps(reference))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        imported = self.call('reference-import', '--root', self.store, '--input', path, '--sha256', sha,
            '--revision', 'b' * 40, '--source-url', 'https://example.invalid/pinned/reference.json', '--license', 'MIT')
        reference_id = imported['artifact_id']
        compared = self.call('reference-compare', '--root', self.store, '--object', self.ids[0], '--reference', reference_id)
        self.assertIn('upstream_vs_observed', compared['comparisons'])
        self.assertFalse(compared['execution_authorized'])
        references = self.call('references', '--root', self.store)['references']
        self.assertEqual(references[0]['artifact_id'], reference_id)
        result = self.process('terminal', '--root', self.store,
            input=f'select {self.ids[0]}\nreferences\nreference-compare {reference_id}\ndictionary\nquit\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('community_reference', result.stdout)

    def test_explicit_migration_backups_legacy_store_before_mutation(self):
        import sqlite3
        from intune_iac.workbench_store import _SCHEMA_SQL_V1
        root = self.root / 'legacy'; root.mkdir(mode=0o700)
        path = root / 'observations.sqlite3'
        with sqlite3.connect(path) as db:
            db.executescript(_SCHEMA_SQL_V1)
            db.execute('INSERT INTO metadata VALUES (?,?)', ('tenant_id', self.tenant))
        path.chmod(0o600)
        backup = self.root / 'legacy-backup.sqlite3'
        with sqlite3.connect(path) as db: before = list(db.iterdump())
        migrated = self.call('migrate', '--root', root, '--backup', backup)
        self.assertEqual((migrated['from_version'], migrated['to_version']), (1, 2))
        with sqlite3.connect(backup) as db:
            self.assertEqual(list(db.iterdump()), before)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
        self.assertEqual(hashlib.sha256(backup.read_bytes()).hexdigest(), migrated['backup']['sha256'])
        self.assertEqual(self.call('overview', '--root', root)['objects'], [])

    def test_explicit_bounded_schedule_runs_after_terminal_closes(self):
        job = self.root / 'job'
        self.call('schedule-create', '--root', self.store, '--service-root', self.service,
                  '--interval-seconds', 0.1, '--output', job)
        self.process('terminal', '--root', self.store, input='quit\n')
        result = self.call('schedule-run', '--job', job, '--max-runs', 1, '--max-duration-seconds', 5)
        self.assertFalse(result.get('cloud_authority', False))
        self.assertEqual(len(self.call('collection-history', '--root', self.store)['collections']), 1)
        status = self.call('schedule-status', '--job', job)
        self.assertIsInstance(status, dict)
        history = self.call('history', '--root', self.store, '--object', self.ids[0])['history']
        self.assertEqual(len(history), 1)


if __name__ == '__main__': unittest.main()
