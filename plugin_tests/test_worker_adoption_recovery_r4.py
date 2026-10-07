"""Recovery approval and hostile response contracts; TLS/native probes are separate."""
import base64
import copy
from dataclasses import asdict
import hashlib
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import uuid

from intune_iac import identity_binding as ib, worker_service as service, worker_adoption_recovery as recovery
from intune_iac.io import AppError, canonical, digest
from plugin_tests.signing_fixture import verifier_pin


class AdoptionRecoveryContracts(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='iw-lease-recovery-');self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.key=self.root/'key.pem'
        subprocess.run(['/usr/bin/openssl','genpkey','-algorithm','ED25519','-out',str(self.key)],check=True,capture_output=True)
        public=subprocess.run(['/usr/bin/openssl','pkey','-in',str(self.key),'-pubout','-outform','DER'],check=True,capture_output=True).stdout[-32:]
        verifier=verifier_pin(Path('/usr/bin/openssl'),hashlib.sha256(Path('/usr/bin/openssl').read_bytes()).hexdigest())
        self.policy_path=self.root/'policy.json'
        self.policy_value={'schema_version':'adoption-native-lease-recovery-policy/1','authority_root':str(self.root/'authority'),
            'verifier':{k:str(v) if isinstance(v,Path) else v for k,v in asdict(verifier).items()},
            'approvers':[{'issuer':'test-recovery','key_id':'key-1','approver_id':'independent-reviewer','public_key_hex':public.hex(),'profiles':['laboratory_adoption_native_lease_recovery']}],
            'admitted_manifest_sha256':['a'*64]}
        self.save_policy();recovery.AdoptionRecoveryPolicy(self.policy_path)
        now=int(time.time())
        self.manifest={'schema_version':'adoption-native-lease-recovery-operation/1','operation_id':str(uuid.uuid4()),'prepared_at':now,'expires_at':now+120,
            'profile':'laboratory_adoption_native_lease_recovery','action':'release_exact_original_adoption_lease','observation':{'scope':'signature-only fixture; cannot create a sealed execution context'},
            'implementation_files':service.implementation_binding(),'recovery_implementation_sha256':hashlib.sha256(Path(recovery.__file__).read_bytes()).hexdigest(),
            'metadata_clear_authorized':False,'ownership_release_authorized':False}
        self.policy_value['admitted_manifest_sha256']=[digest(self.manifest)];self.save_policy();self.policy=recovery.AdoptionRecoveryPolicy(self.policy_path)
        self.payload={'schema_version':'signed-adoption-native-lease-recovery-approval/1','issuer':'test-recovery','key_id':'key-1','approver_id':'independent-reviewer',
            'operation_id':self.manifest['operation_id'],'manifest_sha256':digest(self.manifest),'issued_at':now,'expires_at':now+120,'nonce':uuid.uuid4().hex}
    def save_policy(self):
        self.policy_path.write_bytes(canonical(self.policy_value));self.policy_path.chmod(0o600)
    def sign(self,domain=None,payload=None):
        value=payload or self.payload;message=self.root/'message';signature=self.root/'signature'
        message.write_bytes((recovery.SIGNATURE_DOMAIN if domain is None else domain)+canonical(value))
        subprocess.run(['/usr/bin/openssl','pkeyutl','-sign','-rawin','-inkey',str(self.key),'-in',str(message),'-out',str(signature)],check=True,capture_output=True)
        return {'payload':copy.deepcopy(value),'signature':base64.b64encode(signature.read_bytes()).decode()}
    def test_real_recovery_signature_verifies_but_does_not_mint_context(self):
        signed=self.sign();self.assertEqual(self.policy.verify(self.manifest,signed),self.payload)
        with self.assertRaises(AppError):recovery.execute(self.manifest,signed,context={'approved':True},policy=self.policy,output=self.root/'attempt')
        self.assertFalse((self.root/'attempt').exists())
    def test_old_worker_domain_cannot_approve_recovery(self):
        with self.assertRaises(AppError) as error:self.policy.verify(self.manifest,self.sign(service.SIGNATURE_DOMAIN))
        self.assertEqual(error.exception.code,'lease_recovery_signature_invalid')
    def test_domain_is_actual_nul_and_other_recovery_domains_reject(self):
        self.assertTrue(recovery.SIGNATURE_DOMAIN.endswith(b'\x00'))
        for domain in (b'intune-workbench:native-state-adoption-approval:v1\x00',b'intune-workbench:native-lease-recovery-approval:v1\x00',b'intune-workbench:committed-state-lease-recovery-approval:v1\x00'):
            with self.subTest(domain=domain),self.assertRaises(AppError):self.policy.verify(self.manifest,self.sign(domain))
    def test_verified_payload_is_not_mutable_caller_receipt(self):
        signed=self.sign();verified=self.policy.verify(self.manifest,signed);signed['payload']['nonce']='0'*32
        self.assertEqual(verified['nonce'],self.payload['nonce']);self.assertNotEqual(verified['nonce'],signed['payload']['nonce'])
    def test_unsigned_boolean_cannot_approve_recovery(self):
        with self.assertRaises(AppError):self.policy.verify(self.manifest,{'approved':True})
    def test_expired_real_signature_denied(self):
        payload=copy.deepcopy(self.payload);payload['expires_at']=int(time.time())-1
        with self.assertRaises(AppError):self.policy.verify(self.manifest,self.sign(payload=payload))
    def test_separate_lease_operation_cannot_substitute_into_signed_payload(self):
        signed=self.sign();changed=copy.deepcopy(self.manifest);changed['operation_id']=str(uuid.uuid4())
        with self.assertRaises(AppError):self.policy.verify(changed,signed)
    def test_metadata_clear_or_scope_release_cannot_be_added(self):
        for field in ('metadata_clear_authorized','ownership_release_authorized'):
            changed=copy.deepcopy(self.manifest);changed[field]=True
            with self.subTest(field=field),self.assertRaises(AppError):self.policy.verify(changed,self.sign())
    def test_recovery_source_substitution_denied(self):
        changed=copy.deepcopy(self.manifest);changed['recovery_implementation_sha256']='b'*64
        with self.assertRaises(AppError):self.policy.verify(changed,self.sign())
    def test_external_policy_rewrite_revokes_prepared_authority(self):
        self.policy_value['approvers'][0]['approver_id']='different-reviewer';self.save_policy()
        with self.assertRaises(AppError) as error:self.policy.verify(self.manifest,self.sign())
        self.assertEqual(error.exception.code,'lease_recovery_policy_changed')
    def test_duplicate_response_headers_cannot_select_favorable_etag(self):
        self.assertEqual(recovery._response(ib.ServiceResponse(200,(('ETag','"one"'),),b'{}')),{'etag':'"one"'})
        with self.assertRaises(AppError):recovery._response(ib.ServiceResponse(200,(('ETag','"one"'),('etag','"two"')),b'{}'))
    def test_encoded_or_malformed_response_is_not_state_evidence(self):
        for response in (ib.ServiceResponse(True,(),b'{}'),ib.ServiceResponse(200,(('content-encoding','gzip'),),b'{}'),ib.ServiceResponse(200,(('etag','bad\nvalue'),),b'{}')):
            with self.subTest(response=response),self.assertRaises(AppError):recovery._response(response)
    def test_arbitrary_json_cannot_mint_observation_or_completion(self):
        with self.assertRaises(AppError):recovery.prepare({'approved':True},operation_id=str(uuid.uuid4()),expires_at=int(time.time())+60)
        with self.assertRaises(AppError):recovery.completion({},context={'approved':True},policy=self.policy,output=self.root/'fake')
    def test_token_cleanup_preserves_primary_and_secondary_interruption(self):
        class Token:
            def __init__(self,error):self.error=error
            def close(self):raise self.error
        primary=AppError('primary','synthetic primary')
        with self.assertRaises(AppError) as result:
            try:raise primary
            finally:recovery._close_token(Token(RuntimeError('secondary')))
        self.assertIs(result.exception,primary);self.assertTrue(primary.__notes__)
        for secondary in (KeyboardInterrupt(),SystemExit(4)):
            with self.assertRaises(type(secondary)) as result:
                try:raise primary
                finally:recovery._close_token(Token(secondary))
            self.assertIs(result.exception.__cause__,primary)
        with self.assertRaises(RuntimeError):recovery._close_token(Token(RuntimeError('no primary')))
