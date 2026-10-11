"""New attributable qualifier for a /1 Plan after uncertain import recovery.

Replacement for unavailable qualifier bytes, never a historical restoration.
Uses the existing engine, independently released synthetic receiving fixture,
fresh sealed completion and separately signed Plan-only operation. State bytes
are exact; Graph parity compares the complete typed fixture snapshot. Separately
retained raw service captures do not turn that comparison into HTTP byte equality.
No apply, import or lease-recovery replay. Native execution requires coordinator GO.
"""
from pathlib import Path
from dataclasses import replace
import base64
import copy
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
import time
import uuid

from qualification_context import profile
Q = profile()
SOURCE = Q.project

from intune_iac import worker_service as service, worker_adoption as adoption
from intune_iac import worker_adoption_recovery as recovery, worker_adoption_reconcile as bridge
from intune_iac import worker_provider as wp, worker_host as wh, worker_broker as broker
from intune_iac import identity_binding as ib, azure_backend as ab, observation_reader as rd
from intune_iac.worker_adoption_provider import NativeAdoptionProviderAdapter
from intune_iac.workbench_store import WorkbenchStore
from intune_iac.io import AppError, canonical, digest, write_json
from native_service_fixture_strict_metadata import StrictMetadataFixture
from native_service_fixture import ACCOUNT, STATE_PATH
from native_adoption_policy import build_first_plan_policy
from native_adoption_journey import signed
from native_phase_plan_oracle import assert_import_convergence


def _require(condition, message):
    if not condition:
        raise AssertionError(message)


def _parsed(raw):
    """Retain exact JSON types; duplicate keys/nonfinite numbers are invalid."""
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise AssertionError('nonfinite JSON value: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def file_tree(root):
    """No-follow typed snapshot; failed traversal cannot produce a partial oracle."""
    result = {}
    def denied(error):
        raise error
    for current, dirs, files in os.walk(root, followlinks=False, onerror=denied):
        for name in sorted(dirs + files):
            path = Path(current) / name
            info = path.lstat()
            relative = str(path.relative_to(root))
            if stat.S_ISLNK(info.st_mode):
                result[relative] = {'type': 'literal_link', 'target': os.readlink(path)}
            elif stat.S_ISDIR(info.st_mode):
                result[relative] = {'type': 'directory'}
            elif stat.S_ISREG(info.st_mode):
                raw = path.read_bytes()
                result[relative] = {'type': 'file', 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            else:
                raise AssertionError('Unexpected selected evidence type: ' + relative)
    return result


def preserved_authority_rows(path):
    tables = ('consumed', 'approval_transcripts', 'events', 'native_lease_recoveries',
              'adoption_plan_successors', 'adoption_recovery_plans', 'adoption_operations',
              'adoption_plan_unacquired_observations', 'adoption_plan_observation_successors')
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        present = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {name: list(db.execute('SELECT * FROM ' + name + ' ORDER BY rowid'))
                if name in present else [] for name in tables}


def assert_import_release(manifest, *, original_id, verification_id, original_sha256):
    """Independent literal release-kind/identity oracle before fixture startup."""
    _require(type(manifest) is dict, 'release must be a JSON object')
    _require(manifest.get('schema_version') == 'adoption-native-lease-recovery-operation/1',
             'only original import /1 lease release is selected')
    _require(manifest.get('action') == 'release_exact_original_adoption_lease',
             'release action differs')
    _require(manifest.get('metadata_clear_authorized') is False and
             manifest.get('ownership_release_authorized') is False,
             'release grants unsupported authority')
    operation = manifest.get('operation_id')
    _require(type(operation) is str and str(uuid.UUID(operation)) == operation and
             operation not in (original_id, verification_id), 'release operation is not distinct')
    facts = manifest.get('observation')
    _require(type(facts) is dict and type(facts.get('original')) is dict,
             'release original facts missing')
    original = facts['original']
    _require(original.get('operation_id') == original_id and
             original.get('verification_operation_id') == verification_id and
             original.get('manifest_sha256') == original_sha256,
             'release original identity differs')
    _require('phase_operation_id' not in original and 'phase_kind' not in original,
             'a stopped Plan release is not original import recovery')
    proof = facts.get('adoption_state_proof')
    _require(type(proof) is dict and proof.get('classification') == 'approved_adoption_successor'
             and proof.get('graph_unchanged') is True, 'exact imported successor proof missing')
    return operation


def _safe_paths(seed, released, output):
    inputs = (Path(seed).absolute(), Path(released).absolute(), Path(SOURCE).absolute())
    target = Path(output).absolute()
    for path in (*inputs, target):
        _require('..' not in path.parts and not any(node.is_symlink() for node in (path, *path.parents)),
                 'literal no-link qualifier paths required')
    _require(all(stat.S_ISDIR(path.lstat().st_mode) for path in inputs), 'existing literal inputs required')
    _require(target.parent.is_dir() and not target.exists(), 'fresh output with existing parent required')
    _require(all(target != path and path not in target.parents and target not in path.parents for path in inputs),
             'qualifier output overlaps selected source or original evidence')
    return inputs[0], inputs[1], target


def run(seed, released, output):
    os.umask(0o077)
    seed, released, root = _safe_paths(seed, released, output)
    original_manifest = _parsed((seed / 'jobs/adoption/manifest.json').read_bytes())
    release_manifest = _parsed((released / 'selected-manifest.json').read_bytes())
    release_receipt = _parsed((released / 'receipt.json').read_bytes())
    _require(release_receipt.get('status') == 'PASS', 'qualified separate recovery required')
    release_id = assert_import_release(release_manifest,
        original_id=original_manifest['operation_id'],
        verification_id=original_manifest['verification_operation_id'],
        original_sha256=digest(original_manifest))
    _require(release_receipt.get('original_operation_id') == original_manifest['operation_id']
             and release_receipt.get('recovery_manifest_sha256') == digest(release_manifest),
             'selected release receipt differs from exact manifest')
    root.mkdir(mode=0o700)
    fixture = None
    handles = []
    receipt = {'schema_version': 'native-import-recovery-plan-replacement-journey/1',
        'status': 'STARTED', 'qualifier_revision': 'replacement-20261011-01',
        'historical_helper_restored': False, 'original_seed': str(seed),
        'scope': 'Actual existing engine and tools against a nonforwarding synthetic Graph/Azure receiving fixture. New /1 Plan-only operation after separately approved original-import lease recovery. State content is byte-exact; Graph parity is complete typed snapshot equality, with raw captures retained separately. No import, apply, recovery release or consumed operation replay.',
        'platform_qualified': False, 'production_approved': False}
    write_json(root / 'receipt.json', receipt)
    try:
        fixture = StrictMetadataFixture(released / 'fixture').start()
        receipt['receiving_fixture'] = str(fixture.root)
        starting_policy = seed / 'trust/policy.json'
        original = adoption.AdoptionJob(seed / 'jobs/adoption', starting_policy)
        native = original.manifest['provider_binding']
        old_outcome = original.status()
        _require(old_outcome['dispatches'] == 1, 'exact stopped import must remain once dispatched')
        write_json(root / 'original-before.json', old_outcome)
        authority_path = seed / 'trust/authority/service.sqlite3'
        historical_authority = preserved_authority_rows(authority_path)
        write_json(root / 'historical-authority-before.json', historical_authority)
        before_state = fixture.state_bytes()
        before_graph = fixture.graph_snapshot()
        before_original_fixture = file_tree(seed / 'fixture')
        released_original_files = file_tree(released / 'trust')
        released_manifest_raw = (released / 'selected-manifest.json').read_bytes()
        initial_calls = len(fixture.requests)
        _require(fixture.blobs[STATE_PATH]['lease'] is None, 'receiving state must be independently unlocked')
        initial_state = _parsed(before_state)
        _require(type(initial_state['serial']) is int and initial_state['serial'] == 13,
                 'literal imported state13 required')
        secrets = [ib.ClientSecretHandle('SYNTHETIC-import-recovery-plan-' + role)
                   for role in ('provider', 'backend', 'reader')]
        handles.extend(secrets)
        storage = service.trusted_storage_binding({'profile': 'laboratory_private_plaintext',
            'production_encryption': False, 'quota_qualified': False}, recheck=lambda: None)
        upstream = broker.LaboratoryUpstream(fixture.port, fixture.certificate)
        release_policy = recovery.AdoptionRecoveryPolicy(released / 'trust/policy.json')

        def fresh(current_policy, label):
            selected = adoption.AdoptionJob(seed / 'jobs/adoption', current_policy)
            state_raw = fixture.state_bytes()
            state = _parsed(state_raw)
            target = ib.BackendSpec(**{**native['backend']['backend'], 'state_serial': state['serial'],
                'state_sha256': hashlib.sha256(state_raw).hexdigest()})
            binding = ib.bind_laboratory(ib.BindingConfig(ib.IdentitySpec(**native['provider_identity']),
                ib.IdentitySpec(**native['backend']['identity']), target), provider_credential=secrets[0],
                backend_credential=secrets[1], transport=fixture.transport, max_age=120)
            identity = copy.deepcopy(original.manifest['state_contract']['reader_identity'])
            identity['object_ids'] = tuple(identity['object_ids'])
            collector = rd.bind_laboratory_reader(rd.ReaderSpec(**identity), credential=secrets[2],
                transport=fixture.transport, max_duration_seconds=120)
            handles.append(collector)
            context = recovery.laboratory_context(job=selected, binding=binding, backend_credential=secrets[1],
                storage=storage, reader=collector, baseline_raw=(seed / 'initial-state.json').read_bytes(),
                original_capture_root=seed / 'preimage', source_root=seed / 'source', upstream=upstream)
            complete = recovery.completion(release_manifest, context=context, policy=release_policy, output=root / label)
            write_json(root / (label + '-facts.json'), complete.verified())
            return binding, target, context, complete

        binding, target, context, complete = fresh(starting_policy, 'pre-plan-completion')
        original = context.job
        desired = _parsed((seed / 'source/project' / wp.PROJECT / 'main.tf.json').read_bytes())['resource'][wp.pe.RESOURCE]['selected']
        _require(desired['description'] == 'Fixture only', 'literal original source description required')
        spec = wp.ProviderSpec(ib.IdentitySpec(**native['provider_identity']),
            ab.AzureBackendSpec(ib.IdentitySpec(**native['backend']['identity']), target, 'coordination/selected.lock'),
            native['object_id'], native['source_revision'], native['source_sha256'], native['admission_sha256'], desired)
        inner = wp.WorkerProviderAdapter(spec, lockfile=(seed / 'source/project' / wp.PROJECT / '.terraform.lock.hcl').read_bytes())
        provider = NativeAdoptionProviderAdapter(inner)
        identifier = str(uuid.uuid4())
        expires = int(time.time()) + 300
        execution = digest({'operation_id': identifier, 'provider': provider.binding(),
            'recovery_manifest_sha256': digest(release_manifest), 'action': 'native_first_plan_only'})
        credentials = broker.broker_credentials(binding=binding, backend_credential=secrets[1], execution_binding_sha256=execution)
        handles.append(credentials)
        wp.publish_files(root / 'source', provider.source_files())
        controls = provider.control_files('first-plan', credentials=credentials)
        controls['broker-ca.pem'] = fixture.certificate.read_bytes()
        wp.publish_files(root / 'control', controls)
        (root / 'job').mkdir(mode=0o700)
        proxy = Q.scratch / ('import-recovery-plan-' + uuid.uuid4().hex[:12])
        proxy.mkdir(mode=0o700)
        oldhost = service._host_spec(original.manifest['host_spec'])
        host = replace(oldhost, source_root=str(root / 'source'), source_sha256=wh.directory_binding(root / 'source')['sha256'],
            control_root=str(root / 'control'), control_sha256=wh.directory_binding(root / 'control')['sha256'],
            job_root=str(root / 'job'), broker_root=str(proxy), broker_ca_sha256=hashlib.sha256(fixture.certificate.read_bytes()).hexdigest())
        broker_policy = build_first_plan_policy(operation_id=identifier, execution_binding_sha256=execution,
            expires_at=expires, object_id=native['object_id'], credentials=credentials)
        facts = {**original.manifest['run_context'], 'run_id': 'import-recovery-plan-' + identifier,
            'run_attempt': 1, 'workflow_revision': Q.source_revision, 'verifier_revision': Q.source_revision}
        run_binding = service.trusted_run_binding(facts, recheck=lambda: None)
        manifest = bridge.make_manifest(original=original, completion=complete, operation_id=identifier, expires_at=expires,
            execution_binding_sha256=execution, host_spec=host, broker_policy=broker_policy, provider_binding=provider.binding(),
            run_context=facts, storage_binding_sha256=storage.sha256, identity_binding_sha256=binding.evidence()['binding_sha256'])
        _require(manifest['schema_version'] == 'native-adoption-recovery-plan/1', 'original import needs /1 Plan contract')
        _require(manifest['recovery_binding']['recovery_operation_id'] == release_id,
                 'new Plan must bind the selected exact import release')
        write_json(root / 'manifest.json', manifest)
        policy = _parsed(starting_policy.read_bytes())
        policy['admitted_manifest_sha256'].append(digest(manifest))
        policy_path = seed / 'trust' / ('policy-import-recovery-plan-' + identifier + '.json')
        write_json(policy_path, policy)
        job_root = seed / 'jobs' / ('import-recovery-plan-' + identifier)
        receipt.update(job_root=str(job_root), policy_path=str(policy_path), operation_id=identifier,
            original_operation_id=original.identifier, recovery_operation_id=release_id, manifest_sha256=digest(manifest))

        def cli(action, *extra):
            argv = [sys.executable, '-B', str(SOURCE / 'scripts/intune-iac.py'), 'adoption',
                'recovery-plan-' + action, '--job-root', str(job_root), '--policy', str(policy_path), *extra]
            value = subprocess.run(argv, cwd=SOURCE, capture_output=True, timeout=30)
            (root / ('cli-' + action + '.stdout')).write_bytes(value.stdout)
            (root / ('cli-' + action + '.stderr')).write_bytes(value.stderr)
            write_json(root / ('cli-' + action + '.json'), {'argv': argv, 'exit_code': value.returncode})
            _require(value.returncode == 0, 'CLI failed: ' + action)
            return _parsed(value.stdout)

        cli('prepare', '--manifest', str(root / 'manifest.json'), '--original-job-root', str(original.root))
        cli('review')
        job = bridge.RecoveryPlanJob(job_root, policy_path)
        runtime = bridge.laboratory_runtime(run=run_binding, storage=storage, binding=binding,
            credentials=credentials, upstream=upstream, certificate=fixture.certificate,
            private_key=fixture.root / 'private-key.pem', provider=provider)
        payload = {'schema_version': 'signed-native-adoption-recovery-plan-approval/1',
            'issuer': 'local-native-adoption', 'key_id': 'local-key', 'approver_id': 'independent-synthetic-signer',
            'operation_id': identifier, 'manifest_sha256': digest(manifest), 'issued_at': int(time.time()),
            'expires_at': expires, 'nonce': uuid.uuid4().hex}
        _require(bridge.SIGNATURE_DOMAIN == b'intune-workbench:native-adoption-recovery-plan-approval:v1\x00',
                 'exact /1 signature domain required')
        approval = signed(root, seed / 'trust/synthetic-approver.pem', payload,
            bridge.SIGNATURE_DOMAIN, 'new-import-recovery-plan')
        write_json(root / 'signed-approval.json', approval)
        negative = {}
        before_negative_calls = len(fixture.requests)

        def denied(label, action, code):
            try:
                action()
            except AppError as error:
                negative[label] = error.code
                _require(error.code == code, 'unexpected negative code: ' + label)
            else:
                raise AssertionError('Known-bad control accepted: ' + label)
            _require(job.status()['dispatches'] == 0 and len(fixture.requests) == before_negative_calls,
                     'negative control dispatched or accessed fixture: ' + label)

        wrong_payload = {**payload, 'schema_version': 'signed-native-adoption-recovery-plan-approval/2', 'nonce': uuid.uuid4().hex}
        wrong_domain = signed(root, seed / 'trust/synthetic-approver.pem', wrong_payload,
            bridge.PHASE_SIGNATURE_DOMAIN, 'wrong-phase-domain')
        write_json(root / 'wrong-domain-approval.json', wrong_domain)
        denied('wrong_phase_domain_rejected', lambda: job.run(wrong_domain, runtime=runtime, completion=complete),
               'adoption_recovery_signature_binding')
        forged = copy.deepcopy(approval)
        signature = bytearray(base64.b64decode(forged['signature'], validate=True))
        signature[0] ^= 1
        forged['signature'] = base64.b64encode(signature).decode()
        write_json(root / 'forged-approval.json', forged)
        denied('forged_signature_rejected', lambda: job.run(forged, runtime=runtime, completion=complete),
               'adoption_recovery_signature_invalid')
        denied('json_completion_rejected', lambda: job.run(approval, runtime=runtime, completion=complete.verified()),
               'adoption_recovery_completion_required')
        result = job.run(approval, runtime=runtime, completion=complete)
        write_json(root / 'after-native-plan.json', result)
        _require(result['status'] == 'plan_host_completed_unverified', 'native host did not complete')
        _, _, _, post = fresh(policy_path, 'post-plan-completion')
        post_facts = post.verified()
        native_json = (job.root / 'plan-output/plan.json').read_bytes()
        native_binary = (job.root / 'plan-output/plan.bin').read_bytes()
        native_exit = (job.root / 'plan-output/exit.txt').read_bytes()
        _require(native_exit == b'0\n' and hashlib.sha256(native_binary).hexdigest() ==
                 result['outcome']['plan_output_capture']['artifacts']['plan.bin']['sha256'],
                 'native no-change output bytes differ')
        literal = assert_import_convergence(fixture.state_bytes(), native_json, fixture.graph_snapshot(),
            description='Fixture only', serial=13)
        write_json(root / 'INDEPENDENT-CONVERGENCE.json', literal)
        final = job.reconcile(post)
        write_json(root / 'reconciled.json', final)
        capture = job.captured_observation()
        capture_sha = capture.verified()[0]['capture_sha256']
        store = WorkbenchStore.create(root / 'store', native['tenant_id'])
        publication = rd.publish_batch(store, [capture], job_id=uuid.UUID(identifier).hex, attempt_id=uuid.uuid4().hex)
        write_json(root / 'observation-publication.json', publication)
        reopened = cli('attach')
        cli('status')
        for action in ('adoption-link', 'adoption-history', 'views'):
            argv = [sys.executable, '-B', str(SOURCE / 'scripts/intune-iac.py'), 'workbench', action,
                '--root', str(root / 'store'), '--object', native['object_id']]
            if action == 'adoption-link':
                argv += ['--job-root', str(seed / 'jobs/adoption'), '--policy', str(policy_path)]
            value = subprocess.run(argv, cwd=SOURCE, capture_output=True, timeout=30)
            (root / ('workbench-' + action + '.stdout')).write_bytes(value.stdout)
            (root / ('workbench-' + action + '.stderr')).write_bytes(value.stderr)
            write_json(root / ('workbench-' + action + '.json'), {'argv': argv, 'exit_code': value.returncode})
            _require(value.returncode == 0, 'workbench CLI failed: ' + action)
        calls = fixture.requests[initial_calls:]
        puts = [row for row in calls if row['method'] == 'PUT']
        final_authority = preserved_authority_rows(authority_path)
        write_json(root / 'historical-authority-after.json', final_authority)
        with sqlite3.connect(authority_path.as_uri() + '?mode=ro', uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            old = db.execute('SELECT status,dispatches,outcome FROM jobs WHERE id=?', (original.identifier,)).fetchone()
            plan = db.execute('SELECT status,dispatches FROM adoption_recovery_plans WHERE operation_id=?', (identifier,)).fetchone()
            owners = db.execute('SELECT COUNT(*) FROM ownership WHERE job=?', (original.identifier,)).fetchone()[0]
            consumed = db.execute('SELECT COUNT(*) FROM consumed WHERE operation_id=?', (identifier,)).fetchone()[0]
            old_consumed = db.execute('SELECT COUNT(*) FROM consumed WHERE operation_id=?', (original.identifier,)).fetchone()[0]
            once = db.execute('SELECT recovery_operation,manifest_sha256,status FROM native_lease_recoveries WHERE original_operation=?', (original.identifier,)).fetchone()
            verification = db.execute('SELECT verification_dispatches,verification_status FROM adoption_operations WHERE operation_id=?', (original.identifier,)).fetchone()
        views = _parsed((root / 'workbench-views.stdout').read_bytes())
        checks = {
            'new_plan_only_approval_once': plan == ('reconciled', 1) and consumed == 1,
            'original_import_never_replayed': old[:2] == ('adopted_verified_execution_unknown', 1) and old_consumed == 1,
            'original_unknown_outcome_retained': canonical(_parsed(old[2])['previous_import_outcome']) == canonical(old_outcome['outcome']),
            'unused_original_verification_preserved': verification == (0, 'not_started'),
            'released_original_reservations': owners == 0,
            'original_release_once_unchanged': once is not None and once[0:2] == (release_id, digest(release_manifest)) and once[2] in ('release_observed', 'release_observed_execution_unknown'),
            'receiving_state_byte_exact': fixture.state_bytes() == before_state,
            'receiving_graph_typed_exact': canonical(fixture.graph_snapshot()) == canonical(before_graph),
            'no_graph_writes': not any(row['host'] == 'graph.microsoft.com' and row['method'] in ('PUT', 'POST', 'PATCH', 'DELETE') for row in calls),
            'no_state_content_writes': not any(row['host'] == ACCOUNT and row['path'] == STATE_PATH for row in puts),
            'native_plan_lock_cycle_only': len([row for row in puts if row['headers'].get('x-ms-lease-action') == 'acquire']) == 1 and len([row for row in puts if row['headers'].get('x-ms-lease-action') == 'release']) == 1,
            'lease_and_metadata_clean': fixture.blobs[STATE_PATH]['lease'] is None and fixture.blobs[STATE_PATH]['metadata'] == {},
            'independent_complete_state_and_noop': literal['resource_count'] == 1 and literal['instance_count'] == 1,
            'actual_no_change_proof': final['outcome']['native_first_plan']['first_plan_no_change'] is True,
            'native_host_removed': final['outcome']['first_plan_outcome']['host']['cleanup']['removed'] is True,
            'new_identity_after_etag': post_facts['etag_changed_since_release'] is True,
            'prior_consumption_release_outcome_events_preserved': all(all(row in final_authority[table] for row in rows) for table, rows in historical_authority.items()),
            'release_manifest_exact': (released / 'selected-manifest.json').read_bytes() == released_manifest_raw,
            'release_original_trust_files_exact': file_tree(released / 'trust') == released_original_files,
            'original_receiving_snapshot_unchanged': file_tree(seed / 'fixture') == before_original_fixture,
            'actual_cli_reopen_reconciled': reopened['status'] == 'reconciled',
            'unsupported_mapping_retained': views['coverage']['latest_capture_status'] == 'unsupported',
            'exact_capture_published': type(publication) is list and len(publication) == 1 and publication[0]['source']['capture_sha256'] == capture_sha and publication[0]['coverage'] == 'complete' and publication[0]['status'] == 'unsupported',
        }
        receipt.update(status='PASS' if all(checks.values()) else 'FAIL', checks=checks, negative_codes=negative,
            new_fixture_calls=len(calls), state_sha256=hashlib.sha256(before_state).hexdigest(),
            plan_binary_sha256=final['outcome']['native_first_plan']['binary_sha256'], endpoint_effectiveness='unestablished')
        write_json(root / 'receipt.json', receipt)
        _require(all(checks.values()), 'independent final assertion failed')
        return receipt
    except BaseException as error:
        receipt.update(status='FAIL', error=getattr(error, 'code', type(error).__name__),
            fixture_requests=len(fixture.requests) if fixture is not None else 0)
        try:
            write_json(root / 'receipt.json', receipt)
        except BaseException as secondary:
            error.add_note('Secondary failure receipt error: ' + type(secondary).__name__)
        raise
    finally:
        primary = sys.exception()
        cleanup = []
        first = None
        actions = [('close_' + type(handle).__name__, handle.close) for handle in reversed(handles)]
        if fixture is not None:
            actions.append(('fixture_close', fixture.close))
        for label, action in actions:
            try:
                action()
            except BaseException as error:
                cleanup.append({'phase': label, 'error': getattr(error, 'code', type(error).__name__)})
                if first is None:
                    first = error
                if primary is not None:
                    primary.add_note('Secondary ' + label + ': ' + type(error).__name__)
        try:
            write_json(root / 'FINAL-QUALIFICATION.json', {'status': 'PASS' if receipt.get('status') == 'PASS' and primary is None and not cleanup else 'INCOMPLETE',
                'primary_error': getattr(primary, 'code', type(primary).__name__) if primary else None,
                'cleanup': cleanup, 'platform_qualified': False, 'historical_raw_evidence_loss_closed': False})
        except BaseException as error:
            if first is None:
                first = error
            if primary is not None:
                primary.add_note('Secondary final qualification recording: ' + type(error).__name__)
        if primary is None and first is not None:
            raise first


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seed')
    parser.add_argument('released')
    parser.add_argument('output')
    args = parser.parse_args()
    result = run(args.seed, args.released, args.output)
    print(json.dumps({'status': result['status'], 'checks': len(result.get('checks', {})), 'root': args.output}))
