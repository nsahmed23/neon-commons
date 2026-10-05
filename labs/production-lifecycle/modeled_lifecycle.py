#!/usr/bin/env python3
"""Modeled provider failures with real external-signature verification and locks.

Provider commands/service responses are test doubles. Ed25519 signing and the
host verifier, durable consumption, typed permit and adapter state machine run
for real. This evidence cannot qualify provider RPC, Configure, or a live tenant.
"""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from intune_iac import approval_authority as authority
from intune_iac import provider_execution as pe
from intune_iac.io import AppError, canonical, digest, write_json
from plugin_tests.test_provider_execution_v5 import FIXTURE, OBJECT_ID, SCHEMA, ModeledExecutor


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    report = {'version': 'provider-lifecycle-modeled/1.0', 'evidence_kind': 'modeled_provider_real_approval',
              'production_qualified': False, 'live_service_qualified': False, 'production_configure_qualified': False,
              'native_provider_rpc_qualified': False, 'harness_sha256': pe._sha(Path(__file__)), 'cases': {}}
    openssl = Path('/usr/bin/openssl')
    with tempfile.TemporaryDirectory(prefix='provider-lifecycle-') as directory:
        base = Path(directory); key = base / 'independent-issuer.pem'
        subprocess.run([str(openssl), 'genpkey', '-algorithm', 'ED25519', '-out', str(key)], check=True, capture_output=True)
        pub = subprocess.run([str(openssl), 'pkey', '-in', str(key), '-pubout', '-outform', 'DER'], check=True, capture_output=True).stdout
        signer = authority.TrustedApprover('lab-issuer', 'fixture-key', 'fixture-reviewer', pub[-32:].hex(),
            frozenset({'laboratory'}), frozenset({'provider_update', 'provider_no_change'}))
        host = authority.ApprovalAuthority(base / 'operator-authority',
            authority.VerifierPin(openssl, hashlib.sha256(openssl.read_bytes()).hexdigest()), [signer])
        binary = base / 'modeled-binary'; binary.write_bytes(b'not-a-native-provider')
        pins = pe.ProviderPins(pe._sha(binary), pe._sha(binary), digest(SCHEMA), 'modeled', '1.10.0')
        initial = pe._configuration(FIXTURE); desired = copy.deepcopy(initial)
        desired['name'] = 'Reviewed synthetic policy change'; desired['assignments'].pop()
        for case, failure, expected in [('success', None, 'verified'), ('rejected_before_write', 'before', 'partial_or_divergent'),
                ('policy_assignment_partial', 'partial', 'partial_or_divergent'),
                ('lost_response', 'lost_response', 'service_converged_state_unreconciled'),
                ('state_write_failure', 'state_write', 'service_converged_state_unreconciled')]:
            created = pe.create_laboratory_executor(base / case, pins=pins, tofu=binary, provider=binary,
                initial_configuration=initial, admitted_configuration=desired, object_id=OBJECT_ID,
                source_sha256=digest({'source': 'immutable synthetic fixture'}),
                admission_sha256=digest({'admitted': desired}), target_sha256=digest({'tenant': 'none', 'fixture': OBJECT_ID}))
            executor = ModeledExecutor(created.root); request = executor.prepare(); executor.failure = failure
            payload = {'schema_version': 'signed-operation-approval/1.0', 'issuer': signer.issuer,
                'key_id': signer.key_id, 'approver_id': signer.approver_id, 'operation_id': request['operation_id'],
                'request_sha256': digest(request), 'issued_at': int(time.time()), 'expires_at': int(time.time())+120,
                'nonce': uuid.uuid4().hex}
            message = base / 'message'; signature = base / 'signature'
            message.write_bytes(authority.SIGNATURE_DOMAIN + canonical(payload))
            subprocess.run([str(openssl), 'pkeyutl', '-sign', '-rawin', '-inkey', str(key),
                            '-in', str(message), '-out', str(signature)], check=True, capture_output=True)
            signed = {'payload': payload, 'signature': base64.b64encode(signature.read_bytes()).decode()}
            guard = authority.make_laboratory_guard(request, executor._integrity)
            first = executor.apply(request, authorization=host.authorize(request, signed, guard=guard))
            result = executor.reconcile(request, authority=host)
            if result['status'] != expected or executor.commands.count('apply') != 1:
                raise AssertionError('modeled lifecycle outcome mismatch')
            try:
                with host.authorize(request, signed, guard=guard): pass
            except AppError: replay_rejected = True
            else: raise AssertionError('approval replay accepted')
            try: executor.apply(request, authorization=host.authorize(request, signed, guard=guard))
            except AppError: retry_rejected = True
            else: raise AssertionError('provider mutation retry accepted')
            report['cases'][case] = {'initial_status': first['status'], 'reconciled_status': result['status'],
                'provider_mutation_attempts': 1, 'approval_replay_rejected': replay_rejected,
                'mutation_retry_rejected': retry_rejected, 'request_sha256': digest(request),
                'binary_plan_sha256': request['bindings']['binary_plan_sha256'], 'receipt_sha256': digest(signed),
                'commands': executor.commands, 'preserved_policy_id_sha256': digest(OBJECT_ID),
                'reconciliation': result}
    report['status'] = 'passed-modeled-lifecycle-with-real-signed-authority'
    write_json(args.receipt, report)
    print(json.dumps({'status': report['status'], 'cases': len(report['cases']), 'native_provider_rpc_qualified': False}))

if __name__ == '__main__': main()
