"""Separately signed same-authority succession after an observed lease recovery.

This module never dispatches an engine operation or changes a remote service.
An old consumed approval remains consumed; the new job needs its own approval.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import re
import tempfile
import time

from . import approval_authority as aa, observation_reader as reader_api, protected, validity
from . import worker_service as service
from .io import AppError, canonical, digest, parse_json

VERSION = 'worker-service-successor-transfer/2'
SIGNATURE_DOMAIN = b'intune-workbench:worker-service-successor-transfer:v2\x00'
DOMAIN = SIGNATURE_DOMAIN.rstrip(b'\x00').decode()  # the transfer approval's domain, part of its expiry key
EXPIRED_TABLE = 'successor_expired'  # in the original job's store, beside successor_transfers
PREIMAGE_FRESH_SECONDS = 30


def _fail(code):
    raise AppError(code, 'The separately approved same-authority successor transfer was not established.')


def _copy(value):
    return parse_json(canonical(value))


def _authority(policy):
    return {'authority_root': str(policy.root), 'jobs_root': str(policy.jobs_root),
            'policy_path': str(policy.path), 'policy_sha256': policy.sha256}


def _original(job, db):
    row = db.execute('SELECT status,cancelled,dispatches,outcome,controller_pid,controller_start FROM jobs WHERE id=?',
                     (job.identifier,)).fetchone()
    consumed = db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?', (job.identifier,)).fetchone()
    owners = sorted(r[0] for r in db.execute('SELECT scope FROM ownership WHERE job=?', (job.identifier,)))
    if (row is None or row[0] not in ('outcome_unknown', 'host_completed_service_unverified') or row[2] != 1
            or row[4] is not None or row[5] is not None or consumed != (job.sha256,)
            or owners != service._scopes(job.manifest)):
        _fail('successor_original_active_or_unowned')
    outcome = parse_json(row[3]) if row[3] else None
    cleanup = outcome.get('host', {}).get('cleanup', {}) if type(outcome) is dict else {}
    if cleanup.get('removed') is not True or cleanup.get('stopped_state', {}).get('Running') is not False:
        _fail('successor_original_cleanup_unconfirmed')
    return {'operation_id': job.identifier, 'manifest_sha256': job.sha256, 'status': row[0],
            'cancelled': bool(row[1]), 'outcome_sha256': digest(outcome), 'scopes': owners}


def _preimage_age(captured, batch):
    """The age of a process-held capture: the wall age, or the capture's own carried age (its age when this process made
    it plus the monotonic time since), whichever is older. A wall clock that steps back, however long after, cannot make it
    fresh again, and no bounded map decides it; a capture from another process is refused. A capture dated ahead of the
    wall clock has a negative wall age and is refused by the caller."""
    wall_age = time.time() - batch['observed_at']
    return wall_age if wall_age < 0 else max(wall_age, captured.carried_age())


def _service_preimage(captured, manifest):
    if type(captured) is not reader_api.CapturedObservation:
        _fail('successor_service_preimage_required')
    batch, source = captured.verified()
    expected = manifest['precondition_binding']
    live = manifest['profile'] == 'azure_public_pilot'
    expected_class = 'graph_authenticated_observation' if live else 'graph_reader_laboratory'
    if (captured.cancelled or type(batch.get('observed_at')) not in (int, float)
            or not 0 <= _preimage_age(captured, batch) <= PREIMAGE_FRESH_SECONDS
            or batch.get('tenant_id') != manifest['tenant_id'] or [batch.get('object_id')] != manifest['object_ids']
            or batch.get('capture_sha256') != expected.get('preimage_capture_sha256')
            or source.get('evidence_class') != expected_class or source.get('source_authenticity_verified') is not live
            or canonical(source.get('identity')) != canonical(expected.get('identity'))
            or source.get('identity_observation_sha256') != expected.get('identity_observation_sha256')):
        _fail('successor_service_preimage_binding')
    coverage = batch.get('collections')
    if (type(coverage) is not list or len(coverage) != 3
            or {item.get('kind') for item in coverage} != {'policies', 'settings', 'assignments'}
            or any(item.get('coverage') != 'complete' or item.get('reason') is not None for item in coverage)):
        _fail('successor_service_preimage_incomplete')
    if digest(batch['source']['raw_observed']) != expected.get('preimage_raw_sha256'):
        _fail('successor_service_preimage_binding')
    return {'capture_sha256': batch['capture_sha256'], 'raw_sha256': expected['preimage_raw_sha256'],
            'tenant_id': batch['tenant_id'], 'object_id': batch['object_id'], 'observed_at': batch['observed_at'],
            'identity_observation_sha256': source['identity_observation_sha256'], 'evidence_class': expected_class}


def _released_completion(value, job, manifest):
    from . import worker_lease_recovery as recovery
    expected = recovery.LiveRecoveryCompletion if manifest['profile'] == 'azure_public_pilot' else recovery.LaboratoryRecoveryCompletion
    if type(value) is not expected:
        _fail('successor_recovery_completion_required')
    facts = value.verified()
    # The recovery module owns authenticated observation and its durable
    # release record; this module owns exact successor/context linkage.
    if (facts.get('original', {}).get('operation_id') != job.identifier
            or facts.get('original', {}).get('manifest_sha256') != job.sha256
            or facts.get('service_authority_root') != str(job.policy.root)
            or facts.get('current_service_policy_sha256') != job.policy.sha256
            or facts.get('profile') != ('azure_public_native_lease_recovery' if manifest['profile'] == 'azure_public_pilot'
                                       else 'laboratory_native_lease_recovery')):
        _fail('successor_recovery_binding')
    observation = facts.get('fresh_observation')
    if (type(observation) is not dict or observation.get('locked') is not False
            or facts.get('lease_independently_unlocked') is not True):
        _fail('successor_recovery_not_observed')
    backend = manifest['provider_binding']['backend']
    target, state = backend['backend'], observation.get('state', {})
    if (backend['identity'] != observation.get('identity')
            or any(target.get(key) != observation.get('backend_target', {}).get(key) for key in
                   ('subscription_id', 'storage_account_resource_id', 'blob_endpoint', 'container', 'key', 'workspace'))
            or any(target.get(key) != state.get(other) for key, other in
                   [('state_lineage', 'lineage'), ('state_serial', 'serial'), ('state_sha256', 'sha256')])):
        _fail('successor_state_preimage_binding')
    return facts


def _recovery_kind(value, manifest):
    from . import worker_lease_recovery as released, worker_partial_recovery as observed
    live = manifest['profile'] == 'azure_public_pilot'
    if type(value) is (released.LiveRecoveryCompletion if live else released.LaboratoryRecoveryCompletion):
        return 'explicit_original_state_lease_release'
    if type(value) is (observed.LivePartialRecoveryAttestation if live else observed.LaboratoryPartialRecoveryAttestation):
        return 'already_unlocked_original_state_observed'
    _fail('successor_recovery_completion_required')


def _completion(value, job, manifest):
    kind = _recovery_kind(value, manifest)
    if kind == 'explicit_original_state_lease_release':
        return _released_completion(value, job, manifest)
    facts = value.verified()
    if (facts.get('schema_version') != 'unlocked-original-state-attestation/1'
            or facts.get('recovery_kind') != kind
            or facts.get('original', {}).get('operation_id') != job.identifier
            or facts.get('original', {}).get('manifest_sha256') != job.sha256
            or facts.get('service_authority_root') != str(job.policy.root)
            or facts.get('current_service_policy_sha256') != job.policy.sha256
            or facts.get('lease_release_performed') is not False
            or facts.get('metadata_mutation_performed') is not False
            or facts.get('scope_released') is not False):
        _fail('successor_partial_attestation_binding')
    observation = facts['backend_observation']
    backend = manifest['provider_binding']['backend']
    target, state = backend['backend'], observation['state']
    preimage = manifest['precondition_binding']
    if (observation.get('locked') is not False or backend['identity'] != observation.get('identity')
            or any(target.get(key) != observation.get('backend_target', {}).get(key) for key in
                   ('subscription_id', 'storage_account_resource_id', 'blob_endpoint', 'container', 'key', 'workspace'))
            or any(target.get(key) != state.get(other) for key, other in
                   [('state_lineage', 'lineage'), ('state_serial', 'serial'), ('state_sha256', 'sha256')])
            or facts['service_preimage']['capture_sha256'] != preimage['preimage_capture_sha256']
            or facts['service_preimage']['raw_sha256'] != preimage['preimage_raw_sha256']
            or canonical(facts['service_preimage']['reader_identity']) != canonical(preimage['identity'])
            or facts['service_preimage']['identity_observation_sha256'] != preimage['identity_observation_sha256']):
        _fail('successor_partial_preimage_binding')
    return facts


def _recovery_record_matches(db, original_job, transfer):
    evidence = transfer['recovery_completion']
    if transfer['recovery_kind'] == 'explicit_original_state_lease_release':
        recorded = db.execute('SELECT recovery_operation,manifest_sha256,status,observed_sha256 '
                              'FROM native_lease_recoveries WHERE original_operation=?', (original_job.identifier,)).fetchone()
        return recorded == (evidence['recovery_operation_id'], evidence['recovery_manifest_sha256'],
                            evidence['recovery_status'], evidence['recovery_observation_sha256'])
    if transfer['recovery_kind'] == 'already_unlocked_original_state_observed':
        recorded = db.execute('SELECT original_operation,original_manifest_sha256,facts_sha256 '
                              'FROM partial_recovery_observations WHERE observation_id=?', (evidence['observation_id'],)).fetchone()
        return recorded == (original_job.identifier, original_job.sha256, digest(evidence))
    return False


def prepare_transfer(*, original_job, successor_manifest, successor_job_root, recovery_completion,
                     service_preimage, transfer_id, expires_at):
    if type(original_job) is not service.ServiceJob:
        _fail('successor_original_job_required')
    original_job._check(expiry=False)
    manifest = service.validate_manifest(successor_manifest, require_implementation=False)
    root = service._absolute(str(successor_job_root))
    now = int(time.time())
    if (manifest['action'] != 'apply_saved_plan' or manifest['profile'] == 'native_docker_laboratory_tls'
            or manifest['profile'] != original_job.manifest['profile'] or manifest['operation_id'] == original_job.identifier
            or root.parent != original_job.policy.jobs_root or digest(manifest) not in original_job.policy.admitted
            or service._scopes(manifest) != service._scopes(original_job.manifest)
            or type(transfer_id) is not str or not service._UUID.fullmatch(transfer_id)
            or transfer_id in (original_job.identifier, manifest['operation_id'])
            or type(expires_at) is not int or not now < expires_at <= min(now + 300, manifest['expires_at'])):
        _fail('successor_transfer_scope')
    with original_job.policy.connection() as db:
        original = _original(original_job, db)
    completion = _completion(recovery_completion, original_job, manifest)
    preimage = _service_preimage(service_preimage, manifest)
    return {'schema_version': VERSION, 'transfer_id': transfer_id, 'prepared_at': now, 'expires_at': expires_at,
            'authority': _authority(original_job.policy), 'original': original,
            'successor': {'operation_id': manifest['operation_id'], 'manifest_sha256': digest(manifest), 'job_root': str(root)},
            'recovery_completion': completion, 'recovery_kind': _recovery_kind(recovery_completion, manifest),
            'service_preimage': preimage,
            'implementation_sha256': protected._sha(Path(__file__)), 'operation_dispatch_authorized': False}


def _authenticated(transfer, signed, policy, manifest, now):
    """Every check of the signed transfer approval except the one that its window is still open at the clock's time:
    now is the time the shape checks are made at (the real time, or the approval's own issue time when an expiry is
    being recorded after a refusal)."""
    policy.check()
    if type(signed) is not dict or set(signed) != {'payload', 'signature'}:
        _fail('successor_signature_shape')
    payload = signed['payload']
    fields = {'schema_version', 'issuer', 'key_id', 'approver_id', 'transfer_id', 'transfer_manifest_sha256',
              'issued_at', 'expires_at', 'nonce'}
    if (type(payload) is not dict or set(payload) != fields or payload['schema_version'] != 'signed-worker-service-successor/2'
            or payload['transfer_id'] != transfer['transfer_id'] or payload['transfer_manifest_sha256'] != digest(transfer)
            or type(payload['nonce']) is not str or not re.fullmatch(r'[0-9a-f]{32}', payload['nonce'])):
        _fail('successor_signature_binding')
    if (type(payload['issued_at']) is not int or type(payload['expires_at']) is not int
            or not transfer['prepared_at'] <= payload['issued_at'] <= now + 5
            or not payload['expires_at'] <= transfer['expires_at']):
        _fail('successor_signature_expired')
    if any(type(payload[key]) is not str for key in ('issuer', 'key_id', 'approver_id')):
        _fail('successor_signer_invalid')
    signer = policy.approvers.get((payload['issuer'], payload['key_id']))
    if not signer or signer['approver_id'] != payload['approver_id'] or manifest['profile'] not in signer['profiles']:
        _fail('successor_signer_invalid')
    with policy.connection() as db:
        if db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?', (payload['issuer'], payload['key_id'])).fetchone():
            _fail('successor_signer_revoked')
    try:
        signature = base64.b64decode(signed['signature'], validate=True)
    except (TypeError, ValueError):
        _fail('successor_signature_invalid')
    if len(signature) != 64 or base64.b64encode(signature).decode() != signed['signature']:
        _fail('successor_signature_invalid')
    descriptor = os.open(protected._path(policy.verifier.executable), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(os.dup(descriptor), 'rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != policy.verifier.sha256:
                _fail('successor_verifier_changed')
        with tempfile.TemporaryDirectory(prefix='successor-verify-', dir=policy.root) as temporary:
            directory = Path(temporary)
            for name, data in [('key.der', aa._SPKI + bytes.fromhex(signer['public_key_hex'])),
                               ('message', SIGNATURE_DOMAIN + canonical(payload)), ('signature', signature)]:
                protected._exclusive(directory / name, data)
            protected._supervise([str(policy.verifier.executable), 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER',
                                  '-inkey', str(directory / 'key.der'), '-rawin', '-in', str(directory / 'message'),
                                  '-sigfile', str(directory / 'signature')], cwd=directory,
                                 env={'PATH': '/usr/bin:/bin', 'HOME': str(directory), 'OPENSSL_CONF': '/dev/null'},
                                 pass_fds=(descriptor,), executable='/proc/self/fd/' + str(descriptor), timeout=5, output_limit=4096)
    except AppError:
        _fail('successor_signature_invalid')
    finally:
        os.close(descriptor)
    return payload


def _verify(transfer, signed, policy, manifest):
    """Authenticate the approval, then judge its window in the shared critical section on the original job's store: a
    reached expiry is recorded there and refused, so it stays closed after a backward clock step and a restart. An
    approval that does not authenticate records nothing."""
    now = int(time.time())
    issued = signed.get('payload', {}).get('issued_at') if type(signed) is dict and type(signed.get('payload')) is dict else None
    if type(issued) is int and issued > now + 5: validity.hold_if_clock_behind(policy.root)
    try:
        payload = _authenticated(transfer, signed, policy, manifest, now)
    except AppError:
        expires = signed.get('payload', {}).get('expires_at') if type(signed) is dict and type(signed.get('payload')) is dict else None
        if type(expires) is int and now >= expires: _fail('successor_signature_expired')
        raise
    with _critical(policy, payload, transfer, service._deadline(payload, policy)): pass
    return payload


def _artifact(payload, transfer):
    """The payload as the shared section keys it: a transfer approval names its transfer, which is its operation."""
    return dict(payload, operation_id=transfer['transfer_id'])


def _critical(policy, payload, transfer, deadline):
    return service._critical(policy, _artifact(payload, transfer), digest(transfer), deadline, table=EXPIRED_TABLE, fail=_fail,
                             expired_code='successor_signature_expired', domain=DOMAIN)


def _record_expiry_of(policy, transfer, signed, successor_manifest):
    """Record the reached expiry of a transfer approval whose execution was refused before the approval was judged (the
    manifest window, the transfer's own window and its age are checked on the bare clock first). The approval is
    authenticated with the clock pinned to its issue time; the writing section is entered only when its expiry may have
    been reached, and a backward step is reported as the hold it is. One that does not authenticate records nothing."""
    try:
        transfer, manifest = _copy(transfer), _copy(successor_manifest)
        payload = _authenticated(transfer, signed, policy, manifest, signed['payload']['issued_at'])
    except (AppError, OSError, KeyError, TypeError, AttributeError): return
    if service._expiry_may_be_reached(policy.root, payload):
        service._record_expiry(policy, _artifact(payload, transfer), digest(transfer), None, table=EXPIRED_TABLE, fail=_fail,
                               expired_code='successor_signature_expired', domain=DOMAIN)
    else:
        validity.hold_if_clock_behind(policy.root)


def execute_transfer(transfer, signed, *, original_job, successor_manifest, recovery_completion, service_preimage):
    try:
        return _execute_transfer(transfer, signed, original_job, successor_manifest, recovery_completion, service_preimage)
    except AppError as error:
        # The early refusals judge the manifest, the transfer's window and its age on the bare clock. Record the reached
        # expiry of an approval that authenticates, or a rollback after the refusal would reopen it.
        policy = getattr(original_job, 'policy', None)
        if policy is not None and error.code not in ('successor_signature_expired', validity.HELD):
            _record_expiry_of(policy, transfer, signed, successor_manifest)
        raise


def _execute_transfer(transfer, signed, original_job, successor_manifest, recovery_completion, service_preimage):
    transfer, manifest = _copy(transfer), service.validate_manifest(successor_manifest)
    if type(transfer) is not dict or type(transfer.get('successor')) is not dict:
        _fail('successor_transfer_invalid')
    current = prepare_transfer(original_job=original_job, successor_manifest=manifest,
        successor_job_root=transfer.get('successor', {}).get('job_root'), recovery_completion=recovery_completion,
        service_preimage=service_preimage, transfer_id=transfer.get('transfer_id'), expires_at=transfer.get('expires_at'))
    if (set(current) != set(transfer) or type(transfer['prepared_at']) is not int
            or not 0 <= int(time.time()) - transfer['prepared_at'] <= 300
            or any(current[key] != transfer[key] for key in current if key != 'prepared_at')):
        _fail('successor_transfer_changed')
    policy = original_job.policy
    payload = _verify(transfer, signed, policy, manifest)
    deadline = service._deadline(payload, policy)
    root = Path(transfer['successor']['job_root'])
    spec = service._host_spec(manifest['host_spec'])
    if any(policy.root == Path(path) or policy.root in Path(path).parents or Path(path) in policy.root.parents
           for path in (spec.source_root, spec.control_root, spec.job_root, spec.broker_root)):
        _fail('successor_authority_overlap')
    # Recheck sealed observations after signature verification and preparation, before any effect.
    if (_completion(recovery_completion, original_job, manifest) != transfer['recovery_completion']
            or _service_preimage(service_preimage, manifest) != transfer['service_preimage']):
        _fail('successor_preimage_changed')
    policy.check()
    # The final judgment is the dispatch-start judgment: the window is judged in the critical section, and the successor's
    # directory and artifacts are created only after it judged the window open, while its lock is held. Nothing refuses
    # for expiry after the first effect.
    with _critical(policy, payload, transfer, deadline) as db:
        if _original(original_job, db) != transfer['original']:
            _fail('successor_original_changed')
        if not _recovery_record_matches(db, original_job, transfer):
            _fail('successor_recovery_record_changed')
        if db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?', (payload['issuer'], payload['key_id'])).fetchone():
            _fail('successor_signer_revoked')
        if db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= 10000:
            _fail('successor_store_capacity')
        root.mkdir(mode=0o700, exist_ok=False)
        for name, value in [('manifest.json', manifest), ('policy-binding.json', {'policy_sha256': policy.sha256}),
                            ('successor-transfer.json', transfer), ('successor-transfer-approval.json', signed)]:
            protected._exclusive(root / name, canonical(value))
        db.execute('CREATE TABLE IF NOT EXISTS successor_transfers (original_operation TEXT NOT NULL, '
                   'successor_operation TEXT UNIQUE NOT NULL, transfer_id TEXT PRIMARY KEY, issuer TEXT NOT NULL, '
                   'nonce TEXT NOT NULL, transfer_sha256 TEXT NOT NULL, recovery_completion_sha256 TEXT NOT NULL, '
                   'status TEXT NOT NULL, UNIQUE(issuer,nonce))')
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS successor_active_original ON successor_transfers(original_operation) WHERE status='active'")
        db.execute('INSERT INTO successor_transfers VALUES (?,?,?,?,?,?,?,?)',
                   (original_job.identifier, manifest['operation_id'], transfer['transfer_id'], payload['issuer'],
                    payload['nonce'], digest(transfer), digest(transfer['recovery_completion']), 'active'))
        db.execute('INSERT INTO jobs(id,root,manifest_sha256,status) VALUES (?,?,?,?)',
                   (manifest['operation_id'], str(root), digest(manifest), 'prepared'))
        changed = db.execute('UPDATE ownership SET job=? WHERE job=?',
                             (manifest['operation_id'], original_job.identifier)).rowcount
        if changed != len(transfer['original']['scopes']):
            _fail('successor_ownership_changed')
        event = {'transfer_sha256': digest(transfer), 'transfer_id': transfer['transfer_id'],
                 'original_operation_id': original_job.identifier, 'successor_operation_id': manifest['operation_id'],
                 'successor_manifest_sha256': digest(manifest), 'recovery_completion_sha256': digest(transfer['recovery_completion']),
                 'original_manifest_sha256': original_job.sha256,
                 'recovery_operation_id': (transfer['recovery_completion']['recovery_operation_id'] if
                     transfer['recovery_kind'] == 'explicit_original_state_lease_release' else
                     transfer['recovery_completion']['observation_id']),
                 'recovery_kind': transfer['recovery_kind'],
                 'transfer_artifact': str(root / 'successor-transfer.json'),
                 'transfer_approval_artifact': str(root / 'successor-transfer-approval.json'),
                 'old_failure_preserved': True, 'mutation_replayed': False, 'new_apply_approval_required': True}
        policy.event(db, original_job.identifier, 'successor_ownership_transferred', event)
        policy.event(db, manifest['operation_id'], 'prepared_from_explicit_successor', event)
        db.execute('COMMIT')
    protected._sync(policy.root)
    try:
        protected._exclusive(root / 'successor-transfer-receipt.json', canonical(event))
    except OSError as error:
        with policy.connection() as db:
            policy.event(db, manifest['operation_id'], 'successor_transfer_archive_failed',
                         {'error': type(error).__name__, 'known_transfer_preserved': True, 'retry_authorized': False})
    return service.ServiceJob(root, policy.path).status()


def restore_undispatched_owner(job, db):
    """Called within service cancellation's existing SQLite transaction.

    Cancellation of a prepared recovery successor must not erase the failed
    predecessor's outstanding ownership. A new approved successor may follow
    only through a newly signed transfer; this nonce/history stays consumed.
    """
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='successor_transfers'").fetchone():
        return False
    row = db.execute("SELECT original_operation,transfer_id,transfer_sha256 FROM successor_transfers "
                     "WHERE successor_operation=? AND status='active'", (job.identifier,)).fetchone()
    if row is None:
        return False
    state = db.execute('SELECT dispatches FROM jobs WHERE id=?', (job.identifier,)).fetchone()
    if state != (0,):
        return False
    transfer = service._bounded_private_json(job.root / 'successor-transfer.json')
    if (digest(transfer) != row[2] or transfer['transfer_id'] != row[1]
            or transfer['successor']['operation_id'] != job.identifier
            or transfer['successor']['manifest_sha256'] != job.sha256
            or transfer['authority']['authority_root'] != str(job.policy.root)
            or transfer['original']['operation_id'] != row[0]):
        _fail('successor_cancel_linkage_changed')
    original = db.execute('SELECT manifest_sha256,status,dispatches,outcome,controller_pid,controller_start '
                          'FROM jobs WHERE id=?', (row[0],)).fetchone()
    expected = transfer['original']
    if (original is None or original[0] != expected['manifest_sha256'] or original[1] != expected['status']
            or original[2] != 1 or original[4:] != (None, None)
            or digest(parse_json(original[3])) != expected['outcome_sha256']
            or db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?', (row[0],)).fetchone() != (original[0],)):
        _fail('successor_cancel_original_changed')
    scopes = sorted(r[0] for r in db.execute('SELECT scope FROM ownership WHERE job=?', (job.identifier,)))
    if scopes != expected['scopes'] or scopes != service._scopes(job.manifest):
        _fail('successor_cancel_ownership_changed')
    changed = db.execute('UPDATE ownership SET job=? WHERE job=?', (row[0], job.identifier)).rowcount
    if changed != len(scopes):
        _fail('successor_cancel_ownership_changed')
    db.execute("UPDATE successor_transfers SET status='returned_without_dispatch' WHERE transfer_id=?", (row[1],))
    event = {'transfer_id': row[1], 'transfer_sha256': row[2], 'original_operation_id': row[0],
             'cancelled_successor_operation_id': job.identifier, 'scope_released': False,
             'original_failure_preserved': True, 'mutation_replayed': False, 'new_transfer_approval_required': True}
    job.policy.event(db, row[0], 'successor_cancelled_ownership_returned', event)
    job.policy.event(db, job.identifier, 'successor_cancelled_ownership_returned', event)
    return True
