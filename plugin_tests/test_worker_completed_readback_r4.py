"""Known-completion restart contract tests, not native integration evidence.

Actual product ServicePolicy/ServiceJob SQLite authority is reopened, and actual
CapturedObservation/RecoveryObservation validators and the new factory execute.
The observation context is explicitly controlled: it does not perform native
container inspection, authenticated backend GET, provider application or CI.
Positive fixtures model a previously completed host; they cannot qualify it.
"""
import copy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import pickle
import shutil
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from intune_iac import approval_authority as aa, protected, worker_service as service
from intune_iac import worker_committed_recovery as recovery, worker_completed_readback as completed
from intune_iac import worker_state as ws
from intune_iac.io import AppError, canonical, digest, write_json
from plugin_tests import test_worker_state_r4 as state_fixtures


class KnownCompletedReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='iw-known-completion-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        self.graph = state_fixtures.WorkerStateTests('test_complete_matches_independent_reader_fields_and_preserves_native_metadata')
        self.graph.setUp()
        self.addCleanup(self.graph.doCleanups)
        _, gate, self.transport, kwargs, baseline, plan = self.graph.contract()
        self.saved = b'controlled-unit-fixture-plan-not-a-native-plan'
        saved_sha = hashlib.sha256(self.saved).hexdigest()
        contract = ws.ComputedNativeStateWriteContract(baseline_raw=canonical(baseline), plan_json_raw=canonical(plan),
            saved_plan_sha256=saved_sha, execution_binding_sha256='a' * 64,
            preimage=kwargs['preimage'], precondition=gate)
        completion, candidate = self.graph.complete(gate, kwargs, baseline, plan)
        captured = completion.verified()['capture']
        batch, source = captured.verified()
        self.reader = kwargs['reader']
        self.jobs = self.root / 'jobs'
        self.jobs.mkdir(mode=0o700)
        self.job_root = self.jobs / 'original'
        self.job_root.mkdir(mode=0o700)
        self.authority = self.root / 'authority'
        self.identifier = str(uuid.uuid4())
        target = {'subscription_id': 'controlled-subscription', 'storage_account_resource_id': 'controlled-account',
            'blob_endpoint': 'https://controlled.blob.core.windows.net', 'container': 'state', 'key': 'policy.tfstate',
            'workspace': 'default', 'state_lineage': baseline['lineage'], 'state_serial': baseline['serial'],
            'state_sha256': digest(baseline)}
        backend = {'identity': {'tenant_id': batch['tenant_id'], 'client_id': 'controlled-client', 'object_id': 'controlled-principal'},
            'backend': target, 'state_blob': 'https://controlled.blob.core.windows.net/state/policy.tfstate'}
        provider = {'backend': backend, 'source_revision': '1' * 40, 'source_sha256': '2' * 64,
            'effective_input_sha256': '3' * 64, 'lockfile_sha256': '4' * 64}
        self.manifest = {'schema_version': 'worker-service-operation/1', 'profile': 'native_docker_laboratory_protocol',
            'operation_id': self.identifier, 'execution_binding_sha256': 'a' * 64, 'tenant_id': batch['tenant_id'],
            'object_ids': [batch['object_id']], 'saved_plan_sha256': saved_sha,
            'state_contracts': {'state-write': contract.binding()}, 'precondition_binding': gate.binding(),
            'provider_binding': provider, 'backend_scope_sha256': digest(backend), 'storage_binding_sha256': '5' * 64,
            'run_context': {'source_revision': '1' * 40, 'source_sha256': '2' * 64,
                'effective_inputs_sha256': '3' * 64, 'provider_lock_sha256': '4' * 64},
            'implementation_files': {'explicit-unit-fixture': '6' * 64}}
        self.manifest_sha = digest(self.manifest)
        self.policy_path = self.root / 'policy.json'
        executable = Path('/usr/bin/openssl')
        validator = Path(os.environ.get('INTUNE_TEST_VALIDATOR_LIBRARY', '/usr/lib/x86_64-linux-gnu/libsodium.so.23.3.0'))
        verifier = aa.VerifierPin(executable, hashlib.sha256(executable.read_bytes()).hexdigest(),
            validator, hashlib.sha256(validator.read_bytes()).hexdigest())
        policy_value = {'schema_version': 'worker-service-policy/1', 'authority_root': str(self.authority),
            'jobs_root': str(self.jobs), 'verifier': {key: str(value) if isinstance(value, Path) else value for key, value in asdict(verifier).items()},
            'approvers': [{'issuer': 'unit-fixture', 'key_id': 'rfc-key', 'approver_id': 'unit-fixture-reviewer',
                'public_key_hex': 'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a',
                'profiles': ['native_docker_laboratory_protocol']}], 'admitted_manifest_sha256': [self.manifest_sha]}
        write_json(self.policy_path, policy_value)
        self.policy_path.chmod(0o600)
        policy = service.ServicePolicy(self.policy_path)
        write_json(self.job_root / 'manifest.json', self.manifest)
        write_json(self.job_root / 'policy-binding.json', {'policy_sha256': policy.sha256})
        self.outcome = {'operation_outcome': 'host_completed_service_unverified',
            'host': {'status': 'complete', 'container_exit_code': 0,
                'cleanup': {'removed': True, 'stopped_state': {'Running': False}}},
            'fixture_scope': 'Controlled known-host outcome; no host was executed.'}
        with policy.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO jobs(id,root,manifest_sha256,status,dispatches,outcome) VALUES (?,?,?,?,?,?)',
                (self.identifier, str(self.job_root), self.manifest_sha, 'host_completed_service_unverified', 1, canonical(self.outcome).decode()))
            for scope in service._scopes(self.manifest):
                db.execute('INSERT INTO ownership VALUES (?,?)', (scope, self.identifier))
            db.execute('INSERT INTO consumed VALUES (?,?,?,?)', ('unit-fixture', 'already-consumed-fixture', self.identifier, self.manifest_sha))
            db.execute('COMMIT')
        self.job = service.ServiceJob(self.job_root, self.policy_path)
        original = {'operation_id': self.identifier, 'manifest_sha256': self.manifest_sha,
            'policy_sha256': policy.sha256, 'status': 'host_completed_service_unverified', 'cancelled': False,
            'outcome_sha256': digest(self.outcome), 'scopes': service._scopes(self.manifest)}
        raw = canonical(candidate)
        revision = {'lineage': candidate['lineage'], 'serial': candidate['serial'], 'sha256': hashlib.sha256(raw).hexdigest(), 'etag': '"controlled-current"'}
        proof = {'original_operation_id': self.identifier, 'original_manifest_sha256': self.manifest_sha,
            'original_contract_sha256': digest(contract.binding()), 'original_saved_plan_sha256': saved_sha,
            'original_template_sha256': contract.binding()['admission_template_sha256'],
            'original_preimage_raw_sha256': gate.binding()['preimage_raw_sha256'],
            'state_sha256': revision['sha256'], 'state_lineage': revision['lineage'], 'state_serial': revision['serial'],
            'desired_raw_sha256': digest(batch['source']['raw_observed']), 'reader_identity_sha256': digest(source['identity'])}
        self.observed = {'original': original, 'state': revision, 'committed_state_proof': proof,
            'committed_capture': {'capture_sha256': batch['capture_sha256']}, 'identity': backend['identity'],
            'backend_target': {**target, 'state_serial': candidate['serial'], 'state_sha256': revision['sha256']},
            'storage_binding_sha256': self.manifest['storage_binding_sha256'], 'state_artifact_sha256': revision['sha256'],
            'locked': False, 'metadata': {}, 'observed_at': int(time.time())}
        self.observation_root = self.root / 'controlled-observation'
        self.observation_root.mkdir(mode=0o700)
        protected._exclusive(self.observation_root / 'state.raw', raw)
        protected._exclusive(self.observation_root / 'observation.json', canonical(self.observed))
        # Explicit modeled boundary: no native context constructor/host/storage
        # request is run. Actual opaque observation/capture validators still run.
        context = object.__new__(recovery.LaboratoryCommittedRecoveryContext)
        context.job = self.job
        context.observer = SimpleNamespace(reader=self.reader)
        context.check = lambda: None
        self.observation = recovery.RecoveryObservation(recovery._SEAL, context, self.observed,
            self.observation_root, captured)
        self.inventory = patch.object(service, 'implementation_binding', return_value={'controlled-current-observer': '7' * 64})
        self.inventory.start()
        self.addCleanup(self.inventory.stop)
        retained = os.environ.get('INTUNE_COMPLETED_READBACK_TEST_EVIDENCE')
        if retained:
            def preserve():
                target = Path(retained) / self._testMethodName
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copytree(self.root, target, symlinks=True)
                shutil.copytree(self.graph.root, target / 'captured-graph', symlinks=True)
            self.addCleanup(preserve)

    def collect(self, name='readback', **changes):
        values = {'job_root': self.job_root, 'policy_path': self.policy_path,
            'observation': self.observation, 'output': self.root / name}
        values.update(changes)
        return completed.collect(**values)

    def snapshot(self):
        with self.job.policy.connection() as db:
            return {table: db.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall()
                for table in ('jobs', 'ownership', 'consumed', 'events')}

    def reject(self, action, code=None):
        before = self.snapshot()
        with self.assertRaises(AppError) as error:
            action()
        if code:
            self.assertEqual(error.exception.code, code)
        self.assertEqual(self.snapshot(), before)

    def change_observation(self, mutate):
        value = copy.deepcopy(self.observed)
        mutate(value)
        self.observation.facts = value
        self.observation.sha256 = digest(value)
        protected._exclusive(self.observation_root / ('retained-' + uuid.uuid4().hex + '.json'), canonical(self.observed))
        (self.observation_root / 'observation.json').write_bytes(canonical(value))

    def test_actual_factory_reopens_authority_and_reconciles_known_provenance(self):
        before = self.snapshot()
        capability = self.collect()
        self.assertIs(type(capability), completed.LaboratoryKnownCompletedServiceReadback)
        facts = capability.verified(self.manifest)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(facts['recovery_kind'], completed.KIND)
        self.assertFalse(facts['exceptional_lease_release_performed'])
        self.assertEqual((self.root / 'readback/observed-state.raw').read_bytes(), (self.observation_root / 'state.raw').read_bytes())
        # This is actual product reconciliation against the reopened local DB,
        # not a modeled return value from ServiceJob.reconcile.
        reopened = service.ServiceJob(self.job_root, self.policy_path)
        result = reopened.reconcile(capability)
        self.assertEqual(result['status'], 'service_state_converged')
        self.assertEqual(result['outcome']['execution_provenance'], 'host_completed')
        self.assertEqual(result['outcome']['previous_outcome'], self.outcome)
        self.assertEqual(result['dispatches'], 1)
        self.assertEqual(result['outcome']['endpoint_effectiveness'], 'unestablished')
        self.assertFalse(result['outcome']['mutation_replayed'])
        self.assertFalse(result['outcome']['production_approved'])
        after = self.snapshot()
        self.assertEqual(after['ownership'], [])
        self.assertEqual(after['consumed'], before['consumed'])
        self.assertEqual([row[2] for row in after['events']], ['independent_state_reconciled'])
        with reopened.policy.connection() as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='native_lease_recoveries'").fetchone())
        self.assertEqual(reopened.attach()['status'], 'service_state_converged')

    def test_json_arbitrary_context_and_unsealed_constructor_are_rejected(self):
        for fake in (self.observed, {'approved': True}, lambda: True, None):
            self.reject(lambda: self.collect(observation=fake), 'completed_readback_observation_required')
        with self.assertRaises(AppError):
            completed.LaboratoryKnownCompletedServiceReadback(None, original=self.job,
                observation=self.observation, facts={}, root=self.root)
        original = self.observation.context
        self.observation.context = SimpleNamespace(job=self.job)
        self.reject(self.collect, 'completed_readback_context_required')
        self.observation.context = original

    def test_unknown_dispatch_active_unconsumed_and_unowned_authority_rejected(self):
        edits = ["UPDATE jobs SET status='outcome_unknown'", "UPDATE jobs SET dispatches=2",
            'UPDATE jobs SET controller_pid=123', "UPDATE jobs SET controller_start='other'",
            'DELETE FROM consumed', 'DELETE FROM ownership']
        baseline = self.snapshot()
        for index, sql in enumerate(edits):
            with self.job.policy.connection() as db:
                db.execute(sql)
            self.reject(lambda: self.collect(name='bad-authority-' + str(index)), 'completed_readback_known_host_authority_required')
            with self.job.policy.connection() as db:
                for table, rows in baseline.items():
                    db.execute('DELETE FROM ' + table)
                    if rows:
                        db.executemany('INSERT INTO ' + table + ' VALUES (' + ','.join('?' for _ in rows[0]) + ')', rows)

    def test_noncomplete_failed_unremoved_or_malformed_host_result_rejected(self):
        edits = [lambda host: host.update(status='failed'), lambda host: host.update(container_exit_code=1),
            lambda host: host.update(container_exit_code=False), lambda host: host['cleanup'].update(removed=False),
            lambda host: host['cleanup']['stopped_state'].update(Running=True)]
        for index, edit in enumerate(edits):
            value = copy.deepcopy(self.outcome)
            edit(value['host'])
            with self.job.policy.connection() as db:
                db.execute('UPDATE jobs SET outcome=?', (canonical(value).decode(),))
            self.reject(lambda: self.collect(name='bad-host-' + str(index)), 'completed_readback_known_host_result_required')

    def test_authority_change_after_observation_is_not_favorable_label(self):
        with self.job.policy.connection() as db:
            db.execute('UPDATE jobs SET cancelled=1')
        self.reject(self.collect, 'completed_readback_authority_observation_binding')

    def test_original_plan_template_contract_and_preimage_substitution_rejected(self):
        fields = ('original_operation_id', 'original_manifest_sha256', 'original_contract_sha256',
            'original_saved_plan_sha256', 'original_template_sha256', 'original_preimage_raw_sha256')
        for index, field in enumerate(fields):
            self.change_observation(lambda value, field=field: value['committed_state_proof'].update({field: '0' * 64}))
            self.reject(lambda: self.collect(name='bad-proof-' + str(index)), 'completed_readback_original_approval_binding')

    def test_wrong_identity_backend_revision_and_storage_rejected(self):
        edits = [lambda value: value['identity'].update(client_id='foreign'),
            lambda value: value['backend_target'].update(key='other.tfstate'),
            lambda value: value['state'].update(serial=100), lambda value: value['state'].update(serial=3.0),
            lambda value: value['state'].update(lineage='foreign'),
            lambda value: value.update(storage_binding_sha256='0' * 64)]
        for index, edit in enumerate(edits):
            self.change_observation(edit)
            self.reject(lambda: self.collect(name='bad-backend-' + str(index)), 'completed_readback_backend_binding')

    def test_held_lease_and_nonempty_metadata_are_rejected_without_release(self):
        for index, edit in enumerate((lambda value: value.update(locked=True),
            lambda value: value.update(metadata={'x-ms-meta-terraformlockid': 'retained'}))):
            self.change_observation(edit)
            self.reject(lambda: self.collect(name='bad-lock-' + str(index)), 'completed_readback_backend_lock_remaining')

    def test_stale_or_tampered_observation_and_raw_state_rejected(self):
        self.observation.created -= 31
        self.reject(self.collect, 'lease_recovery_observation_changed_or_stale')
        self.observation.created = time.monotonic()
        raw = self.observation_root / 'state.raw'
        raw.write_bytes(raw.read_bytes() + b'\n')
        self.reject(self.collect, 'lease_recovery_observation_changed_or_stale')

    def test_wrong_capture_proof_is_rejected(self):
        self.change_observation(lambda value: value['committed_capture'].update(capture_sha256='0' * 64))
        self.reject(self.collect, 'committed_state_capture_changed')

    def test_different_registered_job_cannot_use_original_observation(self):
        other_root = self.jobs / 'different'
        other_root.mkdir(mode=0o700)
        changed = copy.deepcopy(self.manifest)
        changed['operation_id'] = str(uuid.uuid4())
        write_json(other_root / 'manifest.json', changed)
        write_json(other_root / 'policy-binding.json', {'policy_sha256': self.job.policy.sha256})
        with self.job.policy.connection() as db:
            db.execute('INSERT INTO jobs(id,root,manifest_sha256,status) VALUES (?,?,?,?)',
                (changed['operation_id'], str(other_root), digest(changed), 'prepared'))
        self.reject(lambda: self.collect(job_root=other_root), 'completed_readback_original_job_binding')

    def test_actual_denied_assignment_capture_cannot_be_labeled_complete(self):
        # Remaining recorded GET responses are from a fresh desired-state read.
        # Deny an assignment page through the actual reader interface.
        self.transport.rows[self.transport.position + 2].update(status=403, body={'error': {'code': 'Denied'}})
        partial = self.reader.capture(self.manifest['object_ids'][0], self.root / 'denied-graph')
        batch, _ = partial.verified()
        self.assertNotEqual(batch['status'], 'observed')
        self.assertTrue(any(row['coverage'] != 'complete' for row in batch['collections']))
        self.observation.captured = partial
        self.change_observation(lambda value: value['committed_capture'].update(capture_sha256=batch['capture_sha256']))
        self.reject(self.collect, 'precondition_coverage_incomplete')

    def test_source_revision_locks_inputs_and_backend_scope_substitution_rejected(self):
        for field in ('source_revision', 'source_sha256', 'effective_inputs_sha256', 'provider_lock_sha256'):
            changed = copy.deepcopy(self.manifest)
            changed['run_context'][field] = '0' * 64
            # Update the local authority atomically as a deliberately bad
            # historical fixture, retaining a hash-bound actual reopened job.
            write_json(self.job_root / 'manifest.json', changed)
            new_sha = digest(changed)
            with self.job.policy.connection() as db:
                db.execute('UPDATE jobs SET manifest_sha256=?', (new_sha,))
                db.execute('UPDATE consumed SET manifest_sha256=?', (new_sha,))
            other = service.ServiceJob(self.job_root, self.policy_path)
            self.observation.context.job = other
            self.change_observation(lambda value: value['original'].update(manifest_sha256=new_sha))
            self.observation.facts['committed_state_proof']['original_manifest_sha256'] = new_sha
            self.observation.sha256 = digest(self.observation.facts)
            (self.observation_root / 'observation.json').write_bytes(canonical(self.observation.facts))
            self.job = other
            self.reject(lambda: self.collect(name='bad-source-' + field), 'completed_readback_source_binding')

    def test_tampered_readback_bytes_retain_reservations(self):
        capability = self.collect()
        raw = self.root / 'readback/observed-state.raw'
        raw.write_bytes(raw.read_bytes() + b'\n')
        self.reject(lambda: self.job.reconcile(capability), 'completed_readback_artifact_changed')

    def test_changed_manifest_json_and_stale_readback_do_not_reconcile(self):
        capability = self.collect()
        changed = copy.deepcopy(self.manifest)
        changed['saved_plan_sha256'] = '0' * 64
        self.reject(lambda: capability.verified(changed), 'completed_readback_changed_or_stale')
        self.reject(lambda: self.job.reconcile(capability.facts), 'service_readback_capability_required')
        capability.created -= 31
        self.reject(lambda: self.job.reconcile(capability), 'completed_readback_changed_or_stale')

    def test_changed_current_observer_inventory_keeps_authority_reserved(self):
        capability = self.collect()
        facts = capability.verified(self.manifest)
        self.assertNotEqual(facts['original_implementation_sha256'], facts['observing_implementation_sha256'])
        with patch.object(service, 'implementation_binding', return_value={'changed-current-observer': '8' * 64}):
            self.reject(lambda: capability.verified(self.manifest), 'completed_readback_observer_implementation_changed')
            self.reject(lambda: self.job.reconcile(capability), 'completed_readback_observer_implementation_changed')
        self.assertEqual(capability.verified(self.manifest)['observing_implementation_sha256'], facts['observing_implementation_sha256'])

    def test_transaction_rechecks_known_outcome_and_never_turns_it_into_unknown(self):
        capability = self.collect()
        verified = capability.verified
        def after_validation(manifest):
            facts = verified(manifest)
            with self.job.policy.connection() as db:
                db.execute("UPDATE jobs SET status='outcome_unknown'")
            return facts
        before = self.snapshot()
        with patch.object(capability, 'verified', side_effect=after_validation), self.assertRaises(AppError) as error:
            self.job.reconcile(capability)
        self.assertEqual(error.exception.code, 'service_known_completed_outcome_changed')
        after = self.snapshot()
        self.assertEqual(after['ownership'], before['ownership'])
        self.assertEqual(after['consumed'], before['consumed'])
        self.assertEqual(after['events'], before['events'])
        self.assertEqual(after['jobs'][0][3], 'outcome_unknown')

    def test_transaction_rechecks_exact_known_outcome_bytes(self):
        capability = self.collect()
        verified = capability.verified
        changed = copy.deepcopy(self.outcome)
        changed['fixture_scope'] = 'A different known result appeared after verification.'
        def after_validation(manifest):
            facts = verified(manifest)
            with self.job.policy.connection() as db:
                db.execute('UPDATE jobs SET outcome=?', (canonical(changed).decode(),))
            return facts
        before = self.snapshot()
        with patch.object(capability, 'verified', side_effect=after_validation), self.assertRaises(AppError) as error:
            self.job.reconcile(capability)
        self.assertEqual(error.exception.code, 'service_known_completed_outcome_changed')
        after = self.snapshot()
        self.assertEqual(after['ownership'], before['ownership'])
        self.assertEqual(after['consumed'], before['consumed'])
        self.assertEqual(after['events'], before['events'])
        self.assertEqual(json.loads(after['jobs'][0][6]), changed)

    def test_serialization_fork_wrong_profile_and_output_link_are_rejected(self):
        capability = self.collect()
        with self.assertRaises(TypeError):
            pickle.dumps(capability)
        with patch.object(completed.os, 'getpid', return_value=-1):
            self.reject(lambda: capability.verified(self.manifest), 'completed_readback_changed_or_stale')
        # Live and laboratory capability classes remain different.
        with self.assertRaises(AppError):
            completed.LiveKnownCompletedServiceReadback(completed._SEAL, original=self.job,
                observation=self.observation, facts={}, root=self.root)
        link = self.root / 'link'
        link.symlink_to(self.root / 'outside')
        self.reject(lambda: self.collect(output=link))


if __name__ == '__main__':
    unittest.main()
