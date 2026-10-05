"""Independent local approval adversarial checks; all signing keys are disposable.

These assertions exercise the actual Ed25519 verifier and durable store. They do
not establish resistance to a compromised interpreter, operator, or verifier.
"""
import base64
import copy
import ctypes
import hashlib
import multiprocessing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from intune_iac import approval_authority as api
from intune_iac.io import AppError, canonical, digest


def _race_enter(root, verifier, approver, request, receipt, start, results):
    try:
        authority = api.ApprovalAuthority(root, verifier, [approver])
        guard = api.make_laboratory_guard(request, lambda: None)
        auth = authority.authorize(request, receipt, guard=guard)
        start.wait(5)
        with auth:
            results.put('entered')
            time.sleep(0.15)
    except AppError as exc:
        results.put(exc.code)
    except Exception as exc:
        results.put(type(exc).__name__)


class IndependentApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.openssl = Path('/usr/bin/openssl')
        self.pin = api.VerifierPin(self.openssl, hashlib.sha256(self.openssl.read_bytes()).hexdigest())
        self.key = self.root / 'private.pem'
        subprocess.run([str(self.openssl), 'genpkey', '-algorithm', 'ED25519', '-out', str(self.key)], check=True, capture_output=True)
        public = subprocess.run([str(self.openssl), 'pkey', '-in', str(self.key), '-pubout', '-outform', 'DER'], check=True, capture_output=True).stdout[-32:]
        self.approver = api.TrustedApprover('issuer', 'key-1', 'reviewer', public.hex(),
            frozenset({'laboratory'}), frozenset({'provider_update', 'provider_no_change'}))
        self.authority = api.ApprovalAuthority(self.root / 'store', self.pin, [self.approver])
        self.request = {'version': 'provider-operation/1.0', 'operation_id': str(uuid.uuid4()),
            'action': 'provider_update', 'mode': 'laboratory', 'laboratory': True,
            'prepared_at': int(time.time()), 'execution_authorized': False,
            'bindings': {'scope_sha256': '1'*64, 'target_sha256': '2'*64, 'binary_plan_sha256': '3'*64}}

    def sign(self, request=None, *, private_key=None, domain=None, **fields):
        request = request or self.request
        payload = {'schema_version': 'signed-operation-approval/1.0', 'issuer': 'issuer',
            'key_id': 'key-1', 'approver_id': 'reviewer', 'operation_id': request['operation_id'],
            'request_sha256': digest(request), 'issued_at': int(time.time()),
            'expires_at': int(time.time()) + 120, 'nonce': uuid.uuid4().hex}
        payload.update(fields)
        message, signature = self.root / 'message', self.root / 'signature'
        message.write_bytes((api.SIGNATURE_DOMAIN if domain is None else domain) + canonical(payload))
        subprocess.run([str(self.openssl), 'pkeyutl', '-sign', '-rawin', '-inkey', str(private_key or self.key),
            '-in', str(message), '-out', str(signature)], check=True, capture_output=True)
        return {'payload': payload, 'signature': base64.b64encode(signature.read_bytes()).decode()}

    def authorize(self, receipt=None, request=None, check=lambda: None):
        request = request or self.request
        return self.authority.authorize(request, receipt or self.sign(request),
            guard=api.make_laboratory_guard(request, check))

    def test_real_signature_from_different_private_key_rejected(self):
        second = self.root / 'other.pem'
        subprocess.run([str(self.openssl), 'genpkey', '-algorithm', 'ED25519', '-out', str(second)], check=True, capture_output=True)
        with self.assertRaises(AppError) as caught: self.authorize(self.sign(private_key=second))
        self.assertEqual(caught.exception.code, 'approval_invalid_signature')

    def test_low_order_identity_public_key_cannot_authorize_static_forgery(self):
        # The compressed identity is a syntactically 32-byte value, but never a
        # usable issuer key. Some OpenSSL Ed25519 verifiers accept R=identity,S=0
        # under A=identity for every message; installation must reject that key.
        identity = bytes.fromhex('01' + '00'*31)
        trusted = api.TrustedApprover('issuer', 'key-1', 'reviewer', identity.hex(),
            frozenset({'laboratory'}), frozenset({'provider_update'}))
        receipt = self.sign()
        receipt['signature'] = base64.b64encode(identity + bytes(32)).decode()
        with self.assertRaises(AppError):
            authority = api.ApprovalAuthority(self.root / 'weak-key-store', self.pin, [trusted])
            with authority.authorize(self.request, receipt,
                    guard=api.make_laboratory_guard(self.request, lambda: None)):
                pass

    def test_signature_from_wrong_domain_rejected(self):
        with self.assertRaises(AppError): self.authorize(self.sign(domain=b'other-system\x00'))

    def test_signature_noncanonical_scalar_rejected(self):
        receipt = self.sign(); signature = base64.b64decode(receipt['signature'])
        subgroup_order = 2**252 + 27742317777372353535851937790883648493
        scalar = int.from_bytes(signature[32:], 'little') + subgroup_order
        receipt['signature'] = base64.b64encode(signature[:32] + scalar.to_bytes(32, 'little')).decode()
        with self.assertRaises(AppError): self.authorize(receipt)

    def test_validator_rejects_weak_noncanonical_and_mixed_order_points(self):
        # Generate a mixed-order point by adding the order-two point to an
        # independently generated legitimate public key, using the native API.
        library = ctypes.CDLL(str(self.pin.validator_library))
        library.crypto_core_ed25519_add.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        library.crypto_core_ed25519_add.restype = ctypes.c_int
        order_two = (2**255 - 20).to_bytes(32, 'little')
        mixed = ctypes.create_string_buffer(32)
        self.assertEqual(library.crypto_core_ed25519_add(mixed,
            bytes.fromhex(self.approver.public_key_hex), order_two), 0)
        for label, point in [('zero', bytes(32)), ('identity', b'\x01'+bytes(31)),
                             ('order-two', order_two), ('noncanonical-identity', (2**255-18).to_bytes(32, 'little')),
                             ('mixed-order', mixed.raw)]:
            with self.subTest(point=label), self.assertRaises(AppError):
                api._valid_public_key(self.pin, point)
        api._valid_public_key(self.pin, bytes.fromhex(self.approver.public_key_hex))

    def test_validator_wrong_pin_and_missing_dependency_fail_closed(self):
        wrong = api.VerifierPin(self.pin.executable, self.pin.sha256,
            self.pin.validator_library, '0'*64)
        missing = api.VerifierPin(self.pin.executable, self.pin.sha256,
            self.root / 'missing-validator.so', self.pin.validator_sha256)
        for label, pin in [('wrong-hash', wrong), ('missing-file', missing)]:
            with self.subTest(variant=label), self.assertRaises(AppError):
                api.ApprovalAuthority(self.root / label, pin, [self.approver])

    def test_validator_dlopen_does_not_reuse_a_recycled_descriptor_path(self):
        # Prime the dlopen cache at the next available descriptor number, then
        # select another genuinely hashed system library without crypto symbols.
        # Merely reopening /proc/self/fd/N must not return the old native image.
        api._valid_public_key(self.pin, bytes.fromhex(self.approver.public_key_hex))
        libc = Path('/usr/lib/x86_64-linux-gnu/libc.so.6')
        other = api.VerifierPin(self.pin.executable, self.pin.sha256,
            libc, hashlib.sha256(libc.read_bytes()).hexdigest())
        with self.assertRaises(AppError):
            api.ApprovalAuthority(self.root / 'wrong-native-library', other, [self.approver])

    def test_full_request_fields_are_signed_not_only_selected_bindings(self):
        receipt = self.sign()
        for modify in (lambda r: r.update(action='provider_no_change'),
                       lambda r: r['bindings'].update(scope_sha256='4'*64),
                       lambda r: r['bindings'].update(target_sha256='4'*64),
                       lambda r: r.update(extra={'instruction': 'different request'})):
            changed = copy.deepcopy(self.request); modify(changed)
            with self.subTest(changed=changed), self.assertRaises(AppError):
                self.authorize(receipt, changed)

    def test_independent_processes_cannot_both_consume_same_approval(self):
        receipt = self.sign(); context = multiprocessing.get_context('fork')
        start, results = context.Event(), context.Queue()
        children = [context.Process(target=_race_enter, args=(self.authority.root, self.pin,
            self.approver, self.request, receipt, start, results)) for _ in range(2)]
        for child in children: child.start()
        start.set()
        for child in children:
            child.join(5)
            if child.is_alive(): child.kill(); child.join(); self.fail('race subprocess did not stop')
            self.assertEqual(child.exitcode, 0)
        outcomes = [results.get(timeout=2) for _ in children]
        self.assertEqual(outcomes.count('entered'), 1, outcomes)
        self.assertTrue(all(o in {'entered', 'approval_scope_busy', 'approval_already_consumed',
            'approval_store_unavailable', 'approval_consumption_not_durable'} for o in outcomes), outcomes)

    def test_real_signed_approval_reaches_modeled_provider_lifecycle_only(self):
        # Actual signature/store/permit integration; the provider is explicitly
        # the existing modeled fixture, never a native or tenant result.
        from intune_iac import provider_execution as pe
        from plugin_tests.test_provider_execution_v5 import ModeledExecutor, FIXTURE, OBJECT_ID, SCHEMA
        binary = self.root / 'modeled-binary'; binary.write_bytes(b'not-an-executable-provider')
        sha = hashlib.sha256(binary.read_bytes()).hexdigest()
        pins = pe.ProviderPins(sha, sha, digest(SCHEMA), 'independent-modeled-fixture', '1.10.0')
        desired = copy.deepcopy(FIXTURE); desired['name'] = 'Independent local review fixture'
        created = pe.create_laboratory_executor(self.root / 'executor', pins=pins, tofu=binary, provider=binary,
            initial_configuration=FIXTURE, admitted_configuration=desired, object_id=OBJECT_ID,
            source_sha256='5'*64, admission_sha256='6'*64, target_sha256='7'*64)
        executor = ModeledExecutor(created.root); request = executor.prepare()
        result = executor.apply(request, authorization=self.authorize(self.sign(request), request))
        self.assertEqual(result['status'], 'verified')
        self.assertFalse(result['production_qualified'])
        self.assertEqual(executor.commands.count('apply'), 1)

    def test_fsync_failure_after_commit_blocks_dispatch_and_stays_spent(self):
        receipt = self.sign(); auth = self.authorize(receipt)
        with patch.object(api, '_sync', side_effect=OSError('injected durability fault')):
            with self.assertRaises(AppError):
                with auth: self.fail('entered despite durability fault')
        with self.assertRaises(AppError) as caught:
            with self.authorize(receipt): self.fail('replayed committed approval')
        self.assertEqual(caught.exception.code, 'approval_already_consumed')

    def test_replaced_database_symlink_and_hardlink_are_rejected(self):
        receipt = self.sign(); database = self.authority.database
        backup = self.root / 'database-copy'; database.rename(backup)
        for kind in ('symlink', 'hardlink'):
            with self.subTest(kind=kind):
                if kind == 'symlink': database.symlink_to(backup)
                else: os.link(backup, database)
                try:
                    with self.assertRaises(AppError): self.authorize(receipt)
                finally: database.unlink()
        backup.rename(database)

    def test_expiry_during_guard_recheck_denies_context_entry(self):
        receipt = self.sign(); expiry = receipt['payload']['expires_at']
        clock = [float(receipt['payload']['issued_at'])]
        def crosses_expiry(): clock[0] = float(expiry + 1)
        with patch.object(api.time, 'time', side_effect=lambda: clock[0]):
            auth = self.authorize(receipt, check=crosses_expiry)
            with self.assertRaises(AppError):
                with auth: pass

    def test_expiry_during_active_guard_recheck_denies_active_permit(self):
        receipt = self.sign(); expiry = receipt['payload']['expires_at']
        clock = [float(receipt['payload']['issued_at'])]; calls = []
        def recheck():
            calls.append('check')
            if len(calls) > 1: clock[0] = float(expiry + 1)
        with patch.object(api.time, 'time', side_effect=lambda: clock[0]):
            with self.authorize(receipt, check=recheck) as permit:
                with self.assertRaises(AppError): permit.check_active()

    def test_guard_predicate_results_are_not_silently_treated_as_success(self):
        receipt = self.sign()
        for result in (False, True, 'approved'):
            with self.subTest(result=result), self.assertRaises(AppError):
                with self.authorize(receipt, check=lambda: result): pass
        # Failed guard checks did not spend the receipt; returning None is the
        # documented successful host-checker contract for the same binding.
        with self.authorize(receipt, check=lambda: None) as permit:
            permit.check_active()

    def test_native_launcher_checks_authority_before_spawning(self):
        from intune_iac import provider_execution as pe
        marker = self.root / 'child-dispatched'
        def reject():
            # Wait only to make preexisting denial versus dispatch ordering
            # observable. The callback denies on every call; no external action.
            deadline = time.monotonic() + 0.25
            while not marker.exists() and time.monotonic() < deadline: time.sleep(0.005)
            raise AppError('independent_review_denied', 'Synthetic denial.')
        with self.assertRaises(AppError):
            pe._supervise([sys.executable, '-I', '-S', '-c',
                'from pathlib import Path;Path(' + repr(str(marker)) + ').write_text("dispatched")'],
                cwd=self.root, env={'PATH': '/usr/bin:/bin'}, executable=sys.executable,
                pass_fds=(), active_check=reject)
        self.assertFalse(marker.exists(), 'child performed a local side effect before first authority check')


if __name__ == '__main__': unittest.main()
