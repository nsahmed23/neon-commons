"""Selfcontained local Git/v2 rejection tests; no host or cloud execution.

Uses installed Git/OpenSSL and the standard pinned approval-validator test
prerequisite. All source, authority and plans are disposable test inputs.
"""
import copy
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import pickle
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from intune_iac import worker_source_intent as source, worker_service as service
from intune_iac import worker_host as host, worker_provider as provider
from intune_iac.io import AppError, canonical, digest, write_json, parse_json
from intune_iac.workbench_store import WorkbenchStore
from intune_iac.workbench_views import import_repository
from plugin_tests.signing_fixture import verifier_pin
from plugin_tests.test_worker_provider_r4 import adapter as fixture_adapter


class SourceIntentR4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='intune-source-contract-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repository'
        (self.repo / provider.PROJECT).mkdir(parents=True)
        (self.repo / 'stacks').mkdir()
        # Explicit reviewed host prerequisite; do not select an ambient shim.
        self.git = Path(os.environ.get('INTUNE_TEST_GIT_EXECUTABLE', '/usr/bin/git'))
        self.git_sha = hashlib.sha256(self.git.read_bytes()).hexdigest()
        initial = fixture_adapter()
        generated = initial.source_files()['project/' + provider.PROJECT + '/main.tf.json']
        document = json.loads(generated)
        document['variable']['native_policy'] = {'type': 'any'}
        document['resource'][provider.pe.RESOURCE]['selected'] = {
            key: '${var.native_policy.' + key + '}' for key in initial.spec.desired}
        (self.repo / provider.PROJECT / 'main.tf.json').write_bytes(canonical(document))
        (self.repo / provider.PROJECT / '.terraform.lock.hcl').write_bytes(initial.lockfile)
        (self.repo / 'atmos.yaml').write_text(
            'stacks:\n  base_path: stacks\n  included_paths: [worker]\n'
            'components:\n  terraform:\n    base_path: components/terraform\n    command: tofu\n')
        (self.repo / 'stacks/worker.yaml').write_bytes(canonical({'vars': {'stage': 'worker'},
            'components': {'terraform': {'intune-policy': {'vars': {'native_policy': initial.spec.desired}}}}}))
        self.command('init', '-b', 'fixture')
        self.command('add', '--all')
        self.command('commit', '-m', 'Literal disposable source')
        revision = self.command('rev-parse', 'HEAD').decode().strip()
        self.adapter = provider.WorkerProviderAdapter(replace(initial.spec,
            source_revision=revision, source_sha256=hashlib.sha256(generated).hexdigest()),
            lockfile=initial.lockfile)
        binding = self.adapter.binding()
        self.store = WorkbenchStore.create(self.root / 'store', binding['provider_identity']['tenant_id'])
        self.intent = import_repository(self.store, self.repo, 'worker', 'intune-policy',
            binding['object_id'], '/vars/native_policy', revision, binding['backend']['state_blob'],
            provider.pe.RESOURCE + '.selected', git_executable=str(self.git), git_sha256=self.git_sha)
        self.cap = source.bind_source_intent(store=self.store, intent_id=self.intent['artifact_id'],
            adapter=self.adapter, logical_repository='https://github.com/fixture/intent',
            git_executable=str(self.git), git_sha256=self.git_sha)
        self.run = service.trusted_run_binding({'schema_version': 'service-run-context/1',
            'repository': 'https://github.com/fixture/intent', 'source_revision': revision,
            'source_sha256': binding['source_sha256'], 'workflow_revision': '5' * 40,
            'verifier_revision': '6' * 40, 'run_id': 'selfcontained-source', 'run_attempt': 1,
            'protected_ref': 'refs/heads/fixture', 'effective_inputs_sha256': binding['effective_input_sha256'],
            'provider_lock_sha256': binding['lockfile_sha256'], 'stack': 'worker', 'component': 'intune-policy'},
            recheck=lambda: None)
        self.storage = service.trusted_storage_binding({'profile': 'local-test-no-dispatch'}, recheck=lambda: None)
        operation = str(uuid.uuid4()); expires = int(time.time()) + 300
        policy = {'schema_version': 'protected-egress-policy/1.0', 'profile': 'laboratory_native_protocol',
            'operation_id': operation, 'execution_binding_sha256': 'a' * 64, 'expires_at': expires,
            'worker_uid': 1000, 'identities': {'provider': {
                'tenant_id': binding['provider_identity']['tenant_id'], 'client_id': binding['provider_identity']['client_id']}},
            'routes': [{'id': 'read-only-fixture', 'host': 'graph.microsoft.com', 'method': 'GET',
                'path': '/beta/deviceManagement/configurationPolicies/' + binding['object_id'],
                'query': {}, 'headers': {}, 'body_sha256': hashlib.sha256(b'').hexdigest(),
                'role': 'provider', 'audience': 'graph', 'effect': 'readonly', 'max_attempts': 1}]}
        # Preparation only: none of these host paths is executed by this suite.
        spec = host.HostSpec('/never/dispatched', str(self.root / 'native-source'), 'b' * 64,
            str(self.root / 'control'), 'c' * 64, str(self.root / 'job'),
            broker_root=str(self.root / 'broker'), broker_ca_sha256='d' * 64)
        self.kwargs = dict(operation_id=operation, profile='native_docker_laboratory_protocol',
            expires_at=expires, execution_binding_sha256='a' * 64, host_spec=spec, broker_policy=policy,
            run_binding_sha256=self.run.sha256, run_context=self.run.facts,
            storage_binding_sha256=self.storage.sha256, tenant_id=binding['provider_identity']['tenant_id'],
            object_ids=[binding['object_id']], backend_scope_sha256=digest(binding['backend']),
            provider_binding=binding, saved_plan_sha256='e' * 64, precondition_binding={})
        self.manifest = service.make_intent_manifest(source_intent=self.cap, **self.kwargs)

    def command(self, *args):
        return subprocess.run([str(self.git), '-c', 'core.hooksPath=/dev/null', '-c',
            'user.name=Local test', '-c', 'user.email=fixture@example.invalid', *args],
            cwd=self.repo, check=True, capture_output=True, timeout=20).stdout

    def assert_code(self, code, action):
        with self.assertRaises(AppError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)

    def runtime(self, cap):
        # Identity, receiving transport and native host deliberately unavailable.
        return service.laboratory_runtime(native_protocol=True, run=self.run, storage=self.storage,
            upstream=None, certificate=None, private_key=None, prewrite=lambda: None, source_intent=cap)

    def test_actual_git_import_matches_materialization_and_thread_recheck(self):
        self.assertTrue(self.intent['data']['revision_content_verified'])
        self.assertEqual(self.cap.check()['resolved_inputs_sha256'], digest(self.adapter.spec.desired))
        observed = []
        def check():
            try: observed.append(self.cap.check())
            except BaseException as error: observed.append(error)
        thread = threading.Thread(target=check); thread.start(); thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(observed, [self.cap.binding()])
        self.assertFalse(observed[0]['remote_origin_authenticated'])

    def test_json_and_serialization_cannot_mint_capability(self):
        self.assert_code('service_source_capability_required',
            lambda: service.make_intent_manifest(source_intent=self.cap.binding(), **self.kwargs))
        self.assert_code('service_source_capability_required', lambda: self.runtime(self.cap.binding()).check(self.manifest))
        self.assert_code('worker_source_capability_not_serializable', lambda: pickle.dumps(self.cap))

    def test_closed_v2_rejects_missing_extra_cross_target_and_remote_claim(self):
        for field, value in [('logical_repository', 'https://github.com/other/repo'),
                ('object_id', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
                ('provider_lock_sha256', '0' * 64), ('remote_origin_authenticated', True)]:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.manifest); changed['source_authoring_binding'][field] = value
                self.assert_code('worker_source_operation_binding', lambda: service.validate_manifest(changed))
        missing = copy.deepcopy(self.manifest); del missing['source_authoring_binding']
        extra = copy.deepcopy(self.manifest); extra['source_approved'] = True
        for value in (missing, extra):
            self.assert_code('service_manifest_invalid', lambda: service.validate_manifest(value))

    def test_v1_keeps_original_shape_and_cannot_claim_optional_bridge(self):
        old = service.make_manifest(**self.kwargs)
        self.assertEqual(old['schema_version'], 'worker-service-operation/1')
        self.assertNotIn('source_authoring_binding', old)
        self.assertEqual(service.SIGNATURE_DOMAIN, b'intune-workbench:worker-service-approval:v1\x00')
        self.assert_code('service_source_capability_unexpected', lambda: self.runtime(self.cap).check(old))

    def test_denied_git_subtree_is_not_silently_omitted(self):
        real_walk = os.walk
        def denied(*args, **kwargs):
            kwargs['onerror'](PermissionError('modeled unreadable Git subtree'))
            yield from real_walk(*args, **kwargs)
        with patch.object(source.os, 'walk', side_effect=denied):
            self.assert_code('worker_source_git_storage_unreadable', self.cap.check)
        self.assertEqual(self.cap.check(), self.cap.binding())

    def test_filesystem_ids_are_lossless_canonical_uint64_strings(self):
        for value in (0, 1, 9007199254740992, 9223372036854775909, (1 << 64) - 1):
            self.assertEqual(source._filesystem_id(value), str(value))
        for bad in (True, 1.0, '1', -1, 1 << 64):
            self.assert_code('worker_source_filesystem_identity', lambda: source._filesystem_id(bad))
        facts = self.cap.binding()
        self.assertEqual(facts['schema_version'], 'worker-source-authoring-binding/2')
        self.assertEqual(facts['git_storage_binding']['schema_version'], 'worker-source-git-storage/2')
        for rows in (facts['local_root_identity'], facts['git_storage_binding']['directories'], facts['git_storage_binding']['files']):
            self.assertTrue(all(type(row[key]) is str for row in rows for key in ('device', 'inode')))
        large = copy.deepcopy(facts); large['local_root_identity'][0]['inode'] = '9223372036854775909'
        self.assertEqual(parse_json(canonical(large)), large)
        self.assert_code('invalid_json', lambda: parse_json(canonical({'inode': 9223372036854775909})))
        for bad in (1, True, 1.0, '01', '-1', '+1', '1.0', '18446744073709551616'):
            changed = copy.deepcopy(facts); changed['local_root_identity'][0]['inode'] = bad
            self.assert_code('worker_source_filesystem_identity', lambda: source._validate_filesystem_ids(changed))

    def test_historical_integer_binding_is_readable_but_not_current_capability(self):
        old = copy.deepcopy(self.manifest)
        facts = old['source_authoring_binding']; facts['schema_version'] = 'worker-source-authoring-binding/1'
        facts['git_storage_binding']['schema_version'] = 'worker-source-git-storage/1'
        for rows in (facts['local_root_identity'], facts['git_storage_binding']['directories'], facts['git_storage_binding']['files']):
            for row in rows:
                for key in ('device', 'inode'): row[key] = int(row[key])
        self.assertEqual(service.validate_manifest(old), old)
        self.assert_code('service_source_binding_changed', lambda: self.runtime(self.cap).check(old))

    def test_actual_prepared_job_rejects_source_lock_and_json_before_dispatch(self):
        trust = self.root / 'trust'; trust.mkdir(mode=0o700)
        jobs = self.root / 'jobs'; jobs.mkdir(mode=0o700)
        openssl = Path('/usr/bin/openssl'); key = trust / 'synthetic.pem'
        subprocess.run([str(openssl), 'genpkey', '-algorithm', 'ED25519', '-out', str(key)], check=True, capture_output=True)
        public = subprocess.run([str(openssl), 'pkey', '-in', str(key), '-pubout', '-outform', 'DER'],
            check=True, capture_output=True).stdout[-32:]
        pin = verifier_pin(openssl, hashlib.sha256(openssl.read_bytes()).hexdigest())
        policy = {'schema_version': 'worker-service-policy/1', 'authority_root': str(trust / 'authority'),
            'jobs_root': str(jobs), 'verifier': {k: str(v) if isinstance(v, Path) else v for k,v in asdict(pin).items()},
            'approvers': [{'issuer': 'fixture', 'key_id': 'key', 'approver_id': 'local-test',
                'public_key_hex': public.hex(), 'profiles': ['native_docker_laboratory_protocol']}],
            'admitted_manifest_sha256': [digest(self.manifest)]}
        path = trust / 'policy.json'; write_json(path, policy)
        service.prepare_job(jobs / 'prepared', manifest=self.manifest, policy_path=path)
        job = service.ServiceJob(jobs / 'prepared', path)
        # Signature verification cannot be reached until runtime source matches.
        with patch.object(host, 'launch', side_effect=AssertionError('must never dispatch')) as dispatch:
            self.assert_code('service_source_capability_required', lambda: job.run({}, runtime=self.runtime(self.cap.binding())))
            for name in ('stacks/worker.yaml', provider.PROJECT + '/.terraform.lock.hcl'):
                with self.subTest(name=name):
                    target = self.repo / name; raw = target.read_bytes(); target.write_bytes(raw + b'\n# unreviewed\n')
                    try:
                        self.assert_code('worker_source_resolution_changed', lambda: job.run({}, runtime=self.runtime(self.cap)))
                    finally: target.write_bytes(raw)
            dispatch.assert_not_called()
        self.assertEqual(job.status()['dispatches'], 0)
        with sqlite3.connect(trust / 'authority/service.sqlite3') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0], 'prepared')
        self.assertEqual(self.cap.check(), self.cap.binding())


if __name__ == '__main__': unittest.main()
