"""Maintenance controls assert independently observed whole-estate values."""
import copy
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from intune_iac import maintenance
from intune_iac.io import AppError, digest, load_json, write_json
from intune_iac.modeled_service import BASE, ModeledService
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = generate_estate(seed=510, policy_count=3)
        self.tenant = self.fixture['truth']['tenant_id']
        self.ids = [p['id'] for p in self.fixture['truth']['policies']]
        self.service = ModeledService.create(self.root / 'service', self.fixture['capture'], self.ids)
        self.store = WorkbenchStore.create(self.root / 'store', self.tenant)
        self.store.collect(self.service)
        self.before = self.service.snapshot()['current']
        self.desired = copy.deepcopy(self.before['objects'][self.ids[0]])
        self.desired['description'] = 'Reviewed synthetic correction'
        self.desired_path = self.root / 'desired.json'
        write_json(self.desired_path, self.desired)
        self.operation = self.root / 'operation'

    def propose(self, **kw):
        return maintenance.propose(self.root / 'store', self.root / 'service', self.ids[0],
                                   self.desired_path, self.operation, **kw)

    def patches(self):
        return [r for r in self.service.snapshot()['requests'] if r['method'] == 'PATCH']

    def execute(self, proposal, **kw):
        return maintenance.execute(self.operation, approve_digest=proposal['approval_digest'], **kw)

    def test_connected_exact_plan_readback_preserves_all_unrelated_values(self):
        proposal = self.propose()
        self.assertFalse(proposal['cloud_authority'])
        result = self.execute(proposal)
        self.assertEqual(result['status'], 'succeeded_verified', result)
        expected = copy.deepcopy(self.before); expected['objects'][self.ids[0]] = self.desired
        # Raw persisted model state is independent of the product comparator.
        self.assertEqual(load_json(self.root / 'service' / 'service.json')['current'], expected)
        self.assertEqual(result['readback']['second_plan']['status'], 'no_change')
        self.assertEqual(len(self.patches()), 1)
        self.assertFalse(result['native_provider_qualified'])
        self.store.collect(self.service)
        self.assertEqual(self.store.inspect(self.ids[0])['body'], self.desired)
        self.assertEqual(len(self.store.history(self.ids[0])), 2)

    def test_explicit_approval_digest_is_required_before_any_mutation(self):
        self.propose()
        with self.assertRaises(AppError) as raised:
            maintenance.execute(self.operation, approve_digest='0' * 64)
        self.assertEqual(raised.exception.code, 'maintenance_approval_required')
        self.assertEqual(self.patches(), [])
        self.assertFalse((self.operation / 'executor' / 'consumed.json').exists())

    def test_stale_whole_estate_rejects_even_when_selected_object_unchanged(self):
        proposal = self.propose()
        other = copy.deepcopy(self.before['objects'][self.ids[1]]); other['description'] = 'External writer'
        self.service.request('PATCH', BASE + '/' + self.ids[1], tenant_id=self.tenant, body=other, if_match='1')
        with self.assertRaises(AppError) as raised: self.execute(proposal)
        self.assertEqual(raised.exception.code, 'maintenance_plan_stale')
        self.assertEqual(len(self.patches()), 1)
        self.assertEqual(self.service.snapshot()['current']['objects'][self.ids[0]], self.before['objects'][self.ids[0]])

    def test_desired_source_bytes_substitution_rejected(self):
        proposal = self.propose()
        self.desired_path.write_text(self.desired_path.read_text() + ' ')
        with self.assertRaises(AppError) as raised: self.execute(proposal)
        self.assertEqual(raised.exception.code, 'maintenance_source_changed')
        self.assertEqual(self.patches(), [])

    def test_saved_desired_or_plan_substitution_rejected(self):
        proposal = self.propose()
        changed = dict(self.desired, name='Unreviewed')
        write_json(self.operation / 'desired.json', changed)
        with self.assertRaises(AppError): self.execute(proposal)
        self.assertEqual(self.patches(), [])

    def test_exact_engine_saved_bytes_substitution_rejected(self):
        proposal = self.propose()
        saved = self.operation / 'executor' / 'work' / 'saved.tfplan'
        data = load_json(saved); data['value']['objects'][self.ids[0]]['name'] = 'Unreviewed'
        write_json(saved, data)
        with self.assertRaises(AppError): self.execute(proposal)
        self.assertEqual(self.patches(), [])

    def test_semantically_equal_saved_plan_byte_substitution_rejected(self):
        proposal = self.propose()
        saved = self.operation / 'executor' / 'work' / 'saved.tfplan'
        saved.write_bytes(saved.read_bytes() + b'\n')
        with self.assertRaises(AppError): self.execute(proposal)
        self.assertEqual(self.patches(), [])

    def test_approval_digest_is_rechecked_after_writer_lock_acquired(self):
        proposal = self.propose()
        original_lock = maintenance._lock
        @contextmanager
        def substitute(root):
            with original_lock(root):
                plan = load_json(self.operation / 'plan.json')
                plan['observation_sha256'] = '0' * 64
                write_json(self.operation / 'plan.json', plan)
                journal = load_json(self.operation / 'journal.json')
                journal['plan_sha256'] = digest(plan)
                write_json(self.operation / 'journal.json', journal)
                yield
        with patch('intune_iac.maintenance._lock', substitute), self.assertRaises(AppError) as raised:
            self.execute(proposal)
        self.assertEqual(raised.exception.code, 'maintenance_approval_required')
        self.assertEqual(self.patches(), [])

    def test_context_bytes_substitution_rejected(self):
        context = self.root / 'context.json'; write_json(context, {'tenant_id': self.tenant})
        proposal = self.propose(context_path=context)
        write_json(context, {'tenant_id': self.ids[0]})
        with self.assertRaises(AppError) as raised: self.execute(proposal)
        self.assertEqual(raised.exception.code, 'maintenance_source_changed')
        self.assertEqual(self.patches(), [])

    def test_context_wrong_tenant_rejected_before_proposal(self):
        context = self.root / 'context.json'; write_json(context, {'tenant_id': self.ids[0]})
        with self.assertRaises(AppError) as raised: self.propose(context_path=context)
        self.assertEqual(raised.exception.code, 'maintenance_context_target_mismatch')
        self.assertFalse(self.operation.exists())

    def test_old_collection_rejected_even_if_current_values_unchanged(self):
        old_store = WorkbenchStore.create(self.root / 'old-store', self.tenant)
        old_store.collect(self.service, observed_at=time.time() - 7200)
        with self.assertRaises(AppError) as raised:
            maintenance.propose(self.root / 'old-store', self.root / 'service', self.ids[0],
                                self.desired_path, self.operation)
        self.assertEqual(raised.exception.code, 'maintenance_observation_stale')
        self.assertFalse(self.operation.exists())

    def test_other_service_identical_values_do_not_supply_provenance(self):
        other = ModeledService.create(self.root / 'other-service', self.fixture['capture'], self.ids)
        self.store.collect(other)
        with self.assertRaises(AppError) as raised: self.propose()
        self.assertEqual(raised.exception.code, 'maintenance_observation_source_mismatch')
        self.assertFalse(self.operation.exists())

    def test_incomplete_latest_collection_cannot_authorize_proposal(self):
        self.store.collect(self.service, fault='deny')
        with self.assertRaises(AppError) as raised: self.propose()
        self.assertEqual(raised.exception.code, 'maintenance_observation_incomplete')
        self.assertFalse(self.operation.exists())

    def test_lost_response_recovery_keeps_identity_and_never_replays(self):
        proposal = self.propose(); result = self.execute(proposal, fault='lost-response')
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(result['operation_id'], proposal['operation_id'])
        with self.assertRaises(AppError): self.execute(proposal)
        recovered = maintenance.reconcile(self.operation)
        self.assertEqual(recovered['classification'], 'desired_state_observed')
        self.assertFalse(recovered['replay_authorized'])
        with self.assertRaises(AppError): self.execute(proposal)
        self.assertEqual(len(self.patches()), 1)
        self.assertEqual(set(self.service.snapshot()['current']['objects']), set(self.ids))
        self.assertEqual(load_json(self.operation / 'journal.json')['events'][-2]['kind'], 'uncertain')

    def test_policy_success_assignment_failure_remains_diverged(self):
        self.desired['assignments'] = self.desired['assignments'][:1]
        write_json(self.desired_path, self.desired)
        proposal = self.propose(); result = self.execute(proposal, fault='after-policy')
        self.assertEqual(result['status'], 'outcome_unknown')
        observed = self.service.snapshot()['current']['objects'][self.ids[0]]
        self.assertEqual(observed['description'], self.desired['description'])
        self.assertEqual(observed['assignments'], self.before['objects'][self.ids[0]]['assignments'])
        self.assertEqual(maintenance.reconcile(self.operation)['classification'], 'diverged')
        self.assertEqual(len(self.patches()), 1)

    def test_denied_and_throttled_service_requests_do_not_mutate(self):
        proposal = self.propose(); result = self.execute(proposal, fault='deny')
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(self.service.snapshot()['current'], self.before)
        self.assertEqual(maintenance.reconcile(self.operation)['classification'], 'matches_precondition')
        with self.assertRaises(AppError): self.execute(proposal)
        self.assertFalse(self.patches()[0]['mutation_committed'])

    def test_journal_failure_prevents_engine_and_service_dispatch(self):
        proposal = self.propose()
        with patch('intune_iac.maintenance.write_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.execute(proposal)
        self.assertEqual(self.patches(), [])
        self.assertFalse((self.operation / 'executor' / 'consumed.json').exists())

    def test_single_writer_contention_rejects_before_dispatch(self):
        proposal = self.propose()
        fd = os.open(self.root / 'service' / 'maintenance.lock', os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(AppError) as raised: self.execute(proposal)
            self.assertEqual(raised.exception.code, 'maintenance_writer_busy')
        finally: os.close(fd)
        self.assertEqual(self.patches(), [])

    def test_two_prepared_operations_cannot_overwrite_each_other(self):
        first = self.propose()
        second_path = self.root / 'second-operation'
        second = maintenance.propose(self.root / 'store', self.root / 'service', self.ids[0],
                                     self.desired_path, second_path)
        self.assertEqual(self.execute(first)['status'], 'succeeded_verified')
        with self.assertRaises(AppError) as raised:
            maintenance.execute(second_path, approve_digest=second['approval_digest'])
        self.assertEqual(raised.exception.code, 'maintenance_plan_stale')
        self.assertEqual(len(self.patches()), 1)

    def test_no_change_operation_never_dispatches_service_mutation(self):
        write_json(self.desired_path, self.before['objects'][self.ids[0]])
        proposal = self.propose(); self.assertEqual(proposal['changes'], [])
        self.assertEqual(self.execute(proposal)['status'], 'succeeded_verified')
        self.assertEqual(self.patches(), [])
        self.assertEqual(self.service.snapshot()['revision'], 1)

    def test_restore_is_fresh_reviewed_operation_not_original_replay(self):
        proposal = self.propose(); self.execute(proposal)
        original_plan = (self.operation / 'plan.json').read_bytes()
        self.store.collect(self.service)
        restore = maintenance.propose_restore(self.operation, self.root / 'restore')
        self.assertNotEqual(restore['operation_id'], proposal['operation_id'])
        self.assertNotEqual(restore['approval_digest'], proposal['approval_digest'])
        result = maintenance.execute(self.root / 'restore', approve_digest=restore['approval_digest'])
        self.assertEqual(result['status'], 'succeeded_verified')
        self.assertEqual(self.service.snapshot()['current'], self.before)
        self.assertEqual((self.operation / 'plan.json').read_bytes(), original_plan)

    def test_abrupt_process_exit_after_committed_patch_reconciles_without_replay(self):
        proposal = self.propose()
        script = '''import os,sys
from intune_iac import maintenance
maintenance._readback=lambda *a,**kw: os._exit(29)
maintenance.execute(sys.argv[1],approve_digest=sys.argv[2])
'''
        proc = subprocess.run([sys.executable, '-B', '-c', script, str(self.operation), proposal['approval_digest']], capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 29, proc.stderr.decode())
        self.assertEqual(load_json(self.operation / 'journal.json')['status'], 'outcome_unknown')
        self.assertEqual(maintenance.reconcile(self.operation)['classification'], 'desired_state_observed')
        with self.assertRaises(AppError): self.execute(proposal)
        self.assertEqual(len(self.patches()), 1)

    def test_missing_fields_and_null_assignments_rejected(self):
        for field in ('settings', 'assignments', 'role_scope_tag_ids'):
            invalid = copy.deepcopy(self.desired); del invalid[field]
            write_json(self.desired_path, invalid)
            with self.subTest(field=field), self.assertRaises(AppError): self.propose()
        invalid = copy.deepcopy(self.desired); invalid['assignments'] = None
        write_json(self.desired_path, invalid)
        with self.assertRaises(AppError): self.propose()


if __name__ == '__main__': unittest.main()
