"""Literal state/index oracles; no live-backend or native-import claim."""
import copy
import hashlib
from pathlib import Path
import pickle
import tempfile
import time
import unittest

from intune_iac import workbench_views as views
from intune_iac.worker_adoption_ownership import admit_ownership, OwnershipAdmission
from intune_iac.workbench_store import WorkbenchStore
from intune_iac.io import AppError, canonical, write_json


class AdoptionOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.tenant = '11111111-1111-4111-8111-111111111111'
        self.oid = '33333333-3333-4333-8333-333333333333'
        self.store = WorkbenchStore.create(self.root / 'store', self.tenant)
        self.state = {'version': 4, 'terraform_version': '1.13.1', 'serial': 12,
            'lineage': '77777777-7777-4777-8777-777777777777', 'outputs': {}, 'resources': []}
        self.raw = canonical(self.state); self.sha = hashlib.sha256(self.raw).hexdigest()
        (self.root / 'state.json').write_bytes(self.raw)
        self.scope = {'repository': 'https://github.com/example/reviewed', 'stack': 'worker',
            'component': 'intune-policy', 'backend': 'https://recordedstate.blob.core.windows.net/tfstate/intune.tfstate'}
        self.scan = {'schema_version': 'workbench-ownership-scan/1', 'tenant_id': self.tenant,
            'max_age_seconds': 60, 'sources': [{'scope': self.scope, 'state_path': str(self.root / 'state.json')}]}
        self.scan_now()
    def scan_now(self):
        write_json(self.root / 'scan.json', self.scan); return views.scan_ownership(self.store, self.root / 'scan.json')
    def admit(self): return admit_ownership(self.store, object_id=self.oid, selected_scope=self.scope, baseline_sha256=self.sha)
    def test_actual_empty_state_and_declared_scope_only(self):
        proof = self.admit(); facts = proof.binding()
        self.assertEqual(facts['baseline_sha256'], self.sha)
        self.assertEqual(facts['result'], 'no_owner_in_completely_searched_declared_scope')
        self.assertFalse(facts['backend_authenticated']); self.assertFalse(facts['global_tenant_ownership_established'])
        self.assertFalse(facts['execution_authorized']); self.assertEqual(facts['declared_scopes'], [self.scope])
    def test_plain_index_label_cannot_mint(self):
        write_json(self.root / 'plain.json', {'schema_version': 'workbench-ownership-index/1', 'tenant_id': self.tenant,
            'max_age_seconds': 60, 'declared_scopes': [self.scope], 'sources': [{'scope': self.scope,
            'coverage': 'complete', 'observed_at': time.time(), 'claims': []}]})
        views.import_ownership(self.store, self.root / 'plain.json')
        with self.assertRaisesRegex(AppError, 'complete current'): self.admit()
    def test_stale_scan_rejected(self):
        self.scan['max_age_seconds'] = 0.000001; self.scan_now()
        with self.assertRaises(AppError): self.admit()
    def test_second_declared_backend_is_not_dropped(self):
        other = dict(self.scope, stack='other'); self.scan['sources'].append({'scope': other, 'state_path': str(self.root / 'state.json')})
        self.scan_now()
        with self.assertRaises(AppError): self.admit()
    def test_additional_repository_scope_not_silently_ignored(self):
        self.store.record_artifact('repository_intent', None, {'scope': dict(self.scope, stack='other'),
            'cloud_authority': False, 'execution_authorized': False})
        with self.assertRaises(AppError): self.admit()
    def test_state_changed_after_scan(self):
        proof = self.admit(); (self.root / 'state.json').write_bytes(self.raw + b'\n')
        with self.assertRaises(AppError): proof.check()
    def test_source_declaration_changed_after_scan(self):
        proof = self.admit(); (self.root / 'scan.json').write_bytes((self.root / 'scan.json').read_bytes() + b'\n')
        with self.assertRaises(AppError): proof.check()
    def test_latest_index_replacement_revokes_old_capability(self):
        proof = self.admit(); self.scan_now()
        with self.assertRaises(AppError): proof.check()
    def test_owned_policy_is_not_importable(self):
        from intune_iac.production import RESOURCE
        self.state['resources'] = [{'mode': 'managed', 'type': RESOURCE, 'name': 'existing',
            'provider': 'provider["registry.terraform.io/deploymenttheory/microsoft365"]',
            'instances': [{'attributes': {'id': self.oid}}]}]
        (self.root / 'state.json').write_bytes(canonical(self.state)); self.scan_now()
        with self.assertRaises(AppError): self.admit()
    def test_unsupported_partial_source_rejected(self):
        self.state['resources'] = [{'mode': 'managed', 'type': 'other_provider_resource', 'instances': []}]
        (self.root / 'state.json').write_bytes(canonical(self.state)); self.scan_now()
        with self.assertRaises(AppError): self.admit()
    def test_no_dictionary_or_pickle_authority(self):
        with self.assertRaises(AppError): OwnershipAdmission(None, self.store, self.oid, self.scope, self.sha)
        with self.assertRaises(TypeError): pickle.dumps(self.admit())
        with self.assertRaises(AppError): admit_ownership({'authenticated': True}, object_id=self.oid, selected_scope=self.scope, baseline_sha256=self.sha)


if __name__ == '__main__': unittest.main()
