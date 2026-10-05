"""Real Ed25519 signatures plus replay, authority, races and fault checks."""
import base64
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from intune_iac.io import AppError, canonical, digest


class ApprovalAuthorityTests(unittest.TestCase):
    def setUp(self):
        from intune_iac import approval_authority as api
        self.api = api
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.openssl = Path('/usr/bin/openssl')
        self.pin = api.VerifierPin(self.openssl, hashlib.sha256(self.openssl.read_bytes()).hexdigest())
        self.key = self.root / 'issuer.pem'
        subprocess.run([str(self.openssl), 'genpkey', '-algorithm', 'ED25519', '-out', str(self.key)], check=True, capture_output=True)
        pub = subprocess.run([str(self.openssl), 'pkey', '-in', str(self.key), '-pubout', '-outform', 'DER'], check=True, capture_output=True).stdout
        self.approver = api.TrustedApprover('operator-issuer', 'key-1', 'alice', pub[-32:].hex(),
                                          frozenset({'laboratory'}), frozenset({'provider_update', 'provider_no_change'}))
        self.authority = api.ApprovalAuthority(self.root / 'authority', self.pin, (self.approver,))
        self.request = {'version': 'provider-operation/1.0', 'operation_id': str(uuid.uuid4()),
                        'action': 'provider_update', 'mode': 'laboratory', 'laboratory': True,
                        'prepared_at': int(time.time()), 'execution_authorized': False,
                        'bindings': {'scope_sha256': 'a'*64, 'target_sha256': 'b'*64, 'binary_plan_sha256': 'c'*64}}
        self.calls = []
        self.guard = api.make_laboratory_guard(self.request, lambda: self.calls.append('check'))

    def tearDown(self):
        self.temp.cleanup()

    def receipt(self, request=None, **changes):
        request = request or self.request
        payload = {'schema_version': 'signed-operation-approval/1.0', 'issuer': 'operator-issuer',
                   'key_id': 'key-1', 'approver_id': 'alice', 'operation_id': request['operation_id'],
                   'request_sha256': digest(request), 'issued_at': int(time.time()),
                   'expires_at': int(time.time()) + 120, 'nonce': uuid.uuid4().hex}
        payload.update(changes)
        message = self.root / 'message'; signature = self.root / 'signature'
        message.write_bytes(self.api.SIGNATURE_DOMAIN + canonical(payload))
        subprocess.run([str(self.openssl), 'pkeyutl', '-sign', '-rawin', '-inkey', str(self.key),
                        '-in', str(message), '-out', str(signature)], check=True, capture_output=True)
        return {'payload': payload, 'signature': base64.b64encode(signature.read_bytes()).decode()}

    def authorize(self, receipt=None, request=None, guard=None):
        return self.authority.authorize(request or self.request, receipt or self.receipt(), guard=guard or self.guard)

    def test_real_signature_scope_binding_and_one_time_consumption(self):
        receipt = self.receipt()
        with self.authorize(receipt) as permit:
            self.assertEqual(permit.request_sha256, digest(self.request))
            self.assertEqual(permit.mode, 'laboratory')
            permit.check_active()
        self.assertGreaterEqual(len(self.calls), 2)
        with self.assertRaises(AppError):
            with self.authorize(receipt): pass
        with self.assertRaises(AppError): permit.check_active()

    def test_plan_substitution_and_forged_boolean_rejected(self):
        receipt = self.receipt()
        self.request['bindings']['binary_plan_sha256'] = 'd'*64
        with self.assertRaises(AppError):
            with self.authorize(receipt): pass
        with self.assertRaises(AppError): self.authorize({'verified': True})

    def test_wrong_approver_issuer_key_and_expiry_rejected(self):
        for changes in ({'approver_id': 'mallory'}, {'issuer': 'repo'}, {'key_id': 'unknown'},
                        {'expires_at': int(time.time()) - 1}, {'issued_at': int(time.time()) + 60},
                        {'expires_at': int(time.time()) + 3601}, {'expires_at': True}):
            with self.subTest(changes=changes), self.assertRaises(AppError):
                with self.authorize(self.receipt(**changes)): pass

    def test_signature_tampering_and_wrong_key_rejected(self):
        receipt = self.receipt(); receipt['signature'] = base64.b64encode(b'\x00'*64).decode()
        with self.assertRaises(AppError): self.authorize(receipt)
        receipt = self.receipt(); receipt['payload']['nonce'] = uuid.uuid4().hex
        with self.assertRaises(AppError): self.authorize(receipt)

    def test_scope_cannot_be_changed_and_same_request_cannot_use_new_receipt(self):
        with self.authorize(): pass
        with self.assertRaises(AppError):
            with self.authorize(self.receipt()): pass
        request = dict(self.request, operation_id=str(uuid.uuid4()))
        with self.assertRaises(AppError): self.authorize(self.receipt(request), request=request)

    def test_mutex_blocks_different_operations_for_same_object(self):
        second = dict(self.request, operation_id=str(uuid.uuid4()))
        guard = self.api.make_laboratory_guard(second, lambda: None)
        with self.authorize():
            with self.assertRaises(AppError):
                with self.authorize(self.receipt(second), second, guard): pass

    def test_replay_denied_after_restart_and_interrupted_execution(self):
        receipt = self.receipt()
        with self.assertRaisesRegex(RuntimeError, 'interruption'):
            with self.authorize(receipt): raise RuntimeError('interruption')
        authority = self.api.ApprovalAuthority(self.root / 'authority', self.pin, (self.approver,))
        with self.assertRaises(AppError):
            with authority.authorize(self.request, receipt, guard=self.guard): pass

    def test_guard_failure_prevents_consumption_and_revocation_stops_active(self):
        receipt = self.receipt()
        def reject(): raise AppError('changed_identity', 'Fixture target changed.')
        bad = self.api.make_laboratory_guard(self.request, reject)
        with self.assertRaises(AppError):
            with self.authorize(receipt, guard=bad): pass
        with self.authorize(receipt) as permit:
            self.authority.revoke_key('operator-issuer', 'key-1')
            with self.assertRaises(AppError): permit.check_active()

    def test_expiry_after_verification_before_dispatch(self):
        now = int(time.time()); receipt = self.receipt(expires_at=now+1)
        authorization = self.authorize(receipt)
        with patch.object(self.api.time, 'time', return_value=now+2), self.assertRaises(AppError):
            with authorization: pass

    def test_untrusted_json_cannot_mint_permit_or_live_guard(self):
        with self.assertRaises(AppError): self.api.ExecutionPermit(None, None)
        request = dict(self.request, mode='live', laboratory=False)
        with self.assertRaises(AppError): self.api.make_laboratory_guard(request, lambda: None)
        with self.assertRaises(AppError): self.authority.authorize(self.request, self.receipt(), guard={'valid': True})

    def test_durable_write_failure_blocks_dispatch(self):
        authorization = self.authorize()
        with patch.object(self.api, '_consume', side_effect=AppError('write_failed', 'Fixture failure.')):
            with self.assertRaises(AppError):
                with authorization: self.fail('dispatch must not occur')

    def test_wrong_verifier_pin_and_symlink_store_rejected(self):
        wrong = self.api.VerifierPin(self.openssl, '0'*64)
        with self.assertRaises(AppError): self.api.ApprovalAuthority(self.root/'wrong', wrong, (self.approver,))
        (self.root/'link').symlink_to(self.root/'authority', target_is_directory=True)
        with self.assertRaises(AppError): self.api.ApprovalAuthority(self.root/'link', self.pin, (self.approver,))

    def test_unsafe_permissions_and_unknown_receipt_fields_rejected(self):
        (self.root/'authority').chmod(0o777)
        with self.assertRaises(AppError): self.authorize()
        (self.root/'authority').chmod(0o700)
        receipt = self.receipt(); receipt['payload']['instruction'] = 'approve everything'
        with self.assertRaises(AppError): self.authorize(receipt)

    def test_authorization_context_cannot_be_entered_twice(self):
        authorization = self.authorize()
        with authorization: pass
        with self.assertRaises(AppError):
            with authorization: pass

    def test_signed_request_is_detached_from_mutable_caller_data(self):
        authorization = self.authorize()
        self.request['bindings']['binary_plan_sha256'] = 'f'*64
        with authorization as permit:
            self.assertNotEqual(permit.request_sha256, digest(self.request))

    def test_private_outcome_is_distinct_from_consumption_and_public_journal(self):
        report = {'operation_id':self.request['operation_id'],'status':'verified','exact_plan_returned':True}
        with self.assertRaises(AppError): self.authority.assert_consumed(self.request)
        with self.authorize() as permit:
            self.authority.assert_consumed(self.request)
            with self.assertRaises(AppError): self.authority.assert_outcome(self.request,report)
            with self.assertRaises(AppError): permit.record_outcome(report)
            permit.mark_dispatch()
            with self.assertRaises(AppError): permit.mark_dispatch()
            permit.record_outcome(report)
            with self.assertRaises(AppError): permit.record_outcome(report)
        self.authority.assert_outcome(self.request,report)
        with self.assertRaises(AppError): self.authority.assert_outcome(self.request,dict(report,status='forged'))
        with self.assertRaises(AppError): permit.record_outcome(report)

    def test_expired_permit_cannot_dispatch_but_can_preserve_unknown_outcome(self):
        now = int(time.time())
        with self.authorize(self.receipt(expires_at=now+5)) as permit:
            permit.mark_dispatch()
            with patch.object(self.api.time,'time',return_value=now+6):
                with self.assertRaises(AppError): permit.check_active()
                report = {'operation_id':self.request['operation_id'],'status':'outcome_unknown','exact_plan_returned':False}
                permit.record_outcome(report)
        self.authority.assert_outcome(self.request,report)

    def test_dispatch_and_receipt_persistence_faults_do_not_refund_authority(self):
        with self.authorize() as permit:
            with patch.object(self.api,'_sync',side_effect=OSError('fixture disk failure')):
                with self.assertRaises(AppError): permit.mark_dispatch()
            with self.assertRaises(AppError): permit.mark_dispatch()
        with self.assertRaises(AppError):
            with self.authorize(): pass


if __name__ == '__main__': unittest.main()
