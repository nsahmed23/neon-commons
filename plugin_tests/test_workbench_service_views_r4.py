"""Real CLI/store links; explicit interrupted/completed journal contract fixtures.

These tests do not claim that the host/provider executed. The composed native
service journey qualifies execution separately using the same entrypoints.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from intune_iac import observation_reader as reader, workbench_service_views as links
from intune_iac import workbench_views as views
from intune_iac.io import AppError
from intune_iac.workbench_store import WorkbenchStore
from plugin_tests import test_worker_service_readback_r4 as fixtures

ROOT = Path(__file__).resolve().parents[1]


class ServiceViewsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixtures.ServiceReadbackTests.setUpClass()
    @classmethod
    def tearDownClass(cls): fixtures.ServiceReadbackTests.tearDownClass()

    def setUp(self):
        self.fixture = fixtures.ServiceReadbackTests('test_actual_tls_state_and_sealed_graph_completion_release_only_converged_scope')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.tenant = self.fixture.manifest['tenant_id']; self.oid = self.fixture.manifest['object_ids'][0]
        self.store = WorkbenchStore.create(self.root / 'workbench', self.tenant)

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/intune-iac.py'), 'workbench', *args],
            capture_output=True, text=True, timeout=25)
        if ok: self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else: self.assertNotEqual(result.returncode, 0)
        return json.loads(result.stdout)

    def link(self):
        return self.cli('service-link', '--root', str(self.store.root), '--object', self.oid,
            '--job-root', str(self.fixture.fixture.job_root), '--policy', str(self.fixture.fixture.policy_path))

    def view(self):
        return self.cli('views', '--root', str(self.store.root), '--object', self.oid)

    def publish(self):
        capture = self.fixture.completion.verified()['capture']
        return reader.publish_batch(self.store, [capture], job_id='1' * 32, attempt_id='2' * 32)

    def reconcile_fixture(self, known):
        job = self.fixture.consumed_interruption()
        if known:
            # This is a journal-boundary fixture, explicitly not a native run.
            with job.policy.connection() as db:
                db.execute("UPDATE jobs SET status='host_completed_service_unverified' WHERE id=?", (job.identifier,))
        job.reconcile(self.fixture.collect())
        return job

    def test_actual_cli_persistent_proposal_never_dispatches_and_checks_tenant(self):
        self.fixture.fixture.prepare(); record = self.link(); result = self.view()
        self.assertEqual(result['proposed']['saved_plan_sha256'], 'b' * 64)
        self.assertEqual(result['proposed']['approval_digest'], record['data']['manifest_sha256'])
        self.assertEqual(result['proposed']['service_journal']['dispatches'], 0)
        self.assertEqual(result['proposed']['run_context']['protected_ref'], 'refs/heads/pilot')
        self.assertEqual(result['deployment']['status'], 'unknown')
        wrong = WorkbenchStore.create(self.root / 'wrong-tenant', '12345678-1234-4234-8234-123456789012')
        with self.assertRaises(AppError):
            links.link(wrong, self.oid, self.fixture.fixture.job_root, self.fixture.fixture.policy_path)
        self.assertEqual(wrong.artifacts(kind='deployment_receipt'), [])

    def test_exact_independent_published_capture_establishes_scoped_baseline(self):
        job = self.reconcile_fixture(known=True); self.publish(); self.link(); result = self.view()
        baseline = result['deployment']
        self.assertEqual(baseline['evidence_class'], 'laboratory_service_state_convergence')
        self.assertEqual(baseline['proof']['backend_state']['serial'], 3)
        self.assertEqual(baseline['proof']['desired']['description'], 'Reviewed correction')
        self.assertEqual(baseline['proof']['plan_sha256'], 'b' * 64)
        self.assertEqual(baseline['second_plan_convergence'], 'separate_native_plan_evidence_required')
        self.assertFalse(baseline['platform_qualified']); self.assertEqual(baseline['endpoint_effectiveness'], 'unestablished')
        self.assertEqual(result['comparisons']['observed_vs_deployment']['status'], 'equal')
        self.assertEqual(result['comparisons']['observed_vs_deployment']['baseline']['kind'], 'verified_protected_service_deployment')
        self.assertEqual(job.attach()['dispatches'], 1)

    def test_unknown_execution_keeps_convergence_and_provenance_separate(self):
        self.reconcile_fixture(known=False); self.publish(); self.link(); result = self.view()
        self.assertEqual(result['proposed']['journal_status'], 'service_state_converged_execution_unknown')
        self.assertEqual(result['deployment']['status'], 'unknown')
        self.assertEqual(result['comparisons']['observed_vs_deployment']['status'], 'unknown')

    def test_missing_or_substituted_capture_cannot_supply_baseline(self):
        self.reconcile_fixture(known=True); self.link()
        self.assertEqual(self.view()['deployment']['status'], 'unknown')
        self.publish()
        with self.store._connection(True) as db:
            db.execute("UPDATE observations SET source_json=json_set(source_json,'$.capture_sha256',?)", ('0' * 64,))
            db.execute("UPDATE run_details SET source_json=json_set(source_json,'$.capture_sha256',?)", ('0' * 64,))
            db.commit()
        self.assertEqual(self.view()['deployment']['status'], 'unknown')

    def test_changed_journal_or_snapshot_cannot_supply_baseline(self):
        job = self.reconcile_fixture(known=True); self.publish(); record = self.link()
        with self.store._connection(True) as db:
            db.execute("UPDATE snapshots SET body_json=json_set(body_json,'$.description','substituted')")
            db.commit()
        with self.assertRaises(AppError): links.deployment(self.store, record)
        self.assertEqual(self.view()['deployment']['status'], 'unknown')
        with job.policy.connection() as db:
            db.execute("UPDATE events SET payload='{}' WHERE kind='independent_state_reconciled'")
        with self.assertRaises(AppError): links.deployment(self.store, record)


class RawUnsupportedViewsTests(unittest.TestCase):
    def test_real_capture_cli_views_retains_unsupported_raw_and_last_good(self):
        from intune_iac.capture import capture
        tenant = '11111111-1111-4111-8111-111111111111'
        oid = '22222222-2222-4222-8222-222222222222'
        document = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        responses = {p['request_url']: (p['http_status'], json.dumps(p['body']).encode())
            for c in document['collections'] for p in c['pages']}
        for url, (status, body) in list(responses.items()):
            if url.endswith('/assignments'):
                value = json.loads(body)
                for row in value['value']: row.update(source='direct', sourceId=None)
                responses[url] = (status, json.dumps(value).encode())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); store = WorkbenchStore.create(root / 'store', tenant)
            capture(tenant, oid, root / 'good', transport=lambda url: responses[url]); store.import_capture(root / 'good')
            last_good = store.inspect(oid)
            url = next(url for url in responses if url.endswith('/settings'))
            status, body = responses[url]; body = json.loads(body)
            body['value'][0]['settingInstance']['choiceSettingValue']['value'] = 'future-choice'
            responses[url] = (status, json.dumps(body).encode())
            capture(tenant, oid, root / 'unsupported', transport=lambda url: responses[url])
            run = store.import_capture(root / 'unsupported'); self.assertEqual(run['status'], 'unsupported')
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/intune-iac.py'), 'workbench',
                'views', '--root', str(store.root), '--object', oid], capture_output=True, text=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            shown = json.loads(result.stdout)['observed']; raw = shown['raw_capture_observation']
            self.assertEqual(raw['status'], 'unsupported'); self.assertEqual(raw['coverage'], 'complete')
            self.assertIn('future-choice', json.dumps(raw['source']['raw_observed']))
            self.assertTrue(raw['source']['mapping_blockers'])
            self.assertEqual(shown['body'], last_good['body']); self.assertEqual(shown['snapshot_id'], last_good['snapshot_id'])
            self.assertFalse(raw['cloud_authority'])


class RawUnsupportedCaptureViewTests(unittest.TestCase):
    def test_real_reader_keeps_unsupported_raw_identity_and_last_good_separate(self):
        from plugin_tests import test_observation_reader_r4 as observation_fixtures
        fixture = observation_fixtures.ObservationReaderR4Tests('test_laboratory_capability_has_no_route_to_live_or_json_authority')
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        good, _, _ = fixture.captured('good'); fixture.publish(good)
        original = fixture.store.inspect(fixture.oid)
        responses = observation_fixtures.fixture_for(fixture.estate)
        for response in responses['responses']:
            if '/settings' in response['path']:
                response['body']['value'][0]['id'] = '37'
        captured, _, _ = fixture.captured('unsupported-id', fixture=responses)
        batch, _ = captured.verified()
        self.assertEqual(batch['status'], 'unsupported')
        self.assertTrue(all(c['coverage'] == 'complete' for c in batch['collections']))
        fixture.publish(captured, attempt='c' * 32)
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/intune-iac.py'),
            'workbench', 'views', '--root', str(fixture.store.root), '--object', fixture.oid],
            capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        value = json.loads(result.stdout)
        self.assertEqual(value['observed']['snapshot_id'], original['snapshot_id'])
        raw = value['observed']['raw_capture_observation']
        self.assertEqual(raw['status'], 'unsupported'); self.assertEqual(raw['coverage'], 'complete')
        self.assertEqual(raw['source']['raw_observed']['settings'][0]['id'], '37')
        self.assertTrue(raw['source']['mapping_blockers'])
        self.assertEqual(raw['capture_integrity']['status'], 'verified_local_bytes')
        self.assertEqual(value['coverage']['observation'], 'stale_or_incomplete')
        self.assertEqual(value['coverage']['latest_capture_status'], 'unsupported')
        self.assertEqual(value['coverage']['latest_capture_collection_coverage'], 'complete')
        self.assertTrue(value['coverage']['latest_capture_mapping_blockers'])
        self.assertIsNone(fixture.store.observation_for_capture(fixture.oid, batch['capture_sha256']))
        self.assertIsNotNone(fixture.store.raw_capture_observation(fixture.oid, batch['capture_sha256']))
        self.assertEqual(len(fixture.store.history(fixture.oid)), 1)


if __name__ == '__main__': unittest.main()
