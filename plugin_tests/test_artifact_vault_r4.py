"""Actual archival CLI, exact bytes, tamper controls and separate-key recovery."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from intune_iac import artifact_vault as vault
from intune_iac.io import AppError

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = Path(os.environ.get('INTUNE_TEST_VALIDATOR_LIBRARY', '/usr/lib/x86_64-linux-gnu/libsodium.so.23.3.0'))
LIBRARY_SHA = 'fe00408090ea084504d7cb0130af56a22554fe299034b864551b65a64ca8a7b5'


@unittest.skipUnless(sys.platform == 'linux', 'Pinned native Linux libsodium route')
class ArtifactVaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.key = bytes(range(32))  # Disposable known laboratory key, never production.
        self.context = hashlib.sha256(b'operation-123:tenant-laboratory').hexdigest()
        self.data = b'\x00binary-plan\r\n\xffprivate-value\x00' + bytes(range(256))
        self.source = self.write('source.bin', self.data)
        self.keyfile = self.write('laboratory-key', self.key)
        self.params = {'key': self.key, 'kind': 'binary_plan', 'context_sha256': self.context,
                       'library': str(LIBRARY), 'library_sha256': LIBRARY_SHA}

    def write(self, name, value):
        path = self.root / name
        path.write_bytes(value)
        path.chmod(0o600)
        return path

    def seal(self, name='sealed.bin', **overrides):
        output = self.root / name
        params = dict(self.params, key_id='laboratory-key-1', retain_until=int(time.time()) + 86400)
        params.update(overrides)
        return output, vault.seal(self.source, output, **params)

    def test_exact_binary_recovery_from_independent_archive_and_key_backup(self):
        archive, receipt = self.seal()
        backup = self.root / 'backup'; backup.mkdir(mode=0o700)
        shutil.copyfile(archive, backup / 'archive'); (backup / 'archive').chmod(0o600)
        shutil.copyfile(self.keyfile, backup / 'key'); (backup / 'key').chmod(0o600)
        self.assertNotIn(b'private-value', archive.read_bytes())
        params = dict(self.params, key=(backup / 'key').read_bytes())
        result = vault.restore(backup / 'archive', backup / 'restored', **params)
        self.assertEqual((backup / 'restored').read_bytes(), self.data)
        self.assertEqual(result['artifact_sha256'], receipt['artifact_sha256'])
        self.assertTrue(result['metadata_authenticated'])
        self.assertEqual((backup / 'restored').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_nonce_is_random_and_inspection_does_not_authenticate(self):
        first, _ = self.seal('one')
        second, _ = self.seal('two')
        self.assertNotEqual(first.read_bytes(), second.read_bytes())
        self.assertFalse(vault.inspect(first)['metadata_authenticated'])

    def test_corruption_wrong_key_type_context_and_truncation_never_publish(self):
        archive, _ = self.seal()
        raw = archive.read_bytes()
        cases = [(raw, {'key': b'x' * 32}), (raw, {'kind': 'state'}),
                 (raw, {'context_sha256': '1' * 64}), (raw[:-1], {}),
                 (raw[:-1] + bytes([raw[-1] ^ 1]), {}), (raw + b'x', {})]
        marker = raw.index(b'laboratory-key-1')
        cases.append((raw[:marker] + b'Laboratory-key-1' + raw[marker+16:], {}))
        for index, (contents, changed) in enumerate(cases):
            source = self.write(f'bad-{index}', contents)
            destination = self.root / f'restored-{index}'
            with self.assertRaises(AppError):
                vault.restore(source, destination, **dict(self.params, **changed))
            self.assertFalse(destination.exists())

    def test_no_overwrite_symlink_or_public_plaintext(self):
        archive, _ = self.seal()
        existing = self.write('existing', b'keep')
        with self.assertRaises(AppError): vault.restore(archive, existing, **self.params)
        self.assertEqual(existing.read_bytes(), b'keep')
        link = self.root / 'link'; link.symlink_to(existing)
        with self.assertRaises(AppError): vault.restore(archive, link, **self.params)
        self.source.chmod(0o644)
        with self.assertRaises(AppError): self.seal('public-source-denied')
        archive.chmod(0o644)
        with self.assertRaises(AppError): vault.inspect(archive)

    def test_size_and_library_pin_fail_closed(self):
        with self.assertRaises(AppError): self.seal(library_sha256='0' * 64)
        with self.source.open('wb') as output: output.truncate(vault.MAX_BYTES + 1)
        with self.assertRaises(AppError): self.seal()
        self.assertFalse((self.root / 'sealed.bin').exists())

    def test_real_cli_every_kind_exact_restore_and_no_key_in_output(self):
        for kind in vault.KINDS:
            archive = self.root / f'{kind}.sealed'
            restored = self.root / f'{kind}.restored'
            for action, source, destination in [('seal', self.source, archive), ('restore', archive, restored)]:
                with self.keyfile.open('rb') as key:
                    argv = [sys.executable, '-B', str(ROOT / 'scripts/intune-iac.py'), 'artifact', action,
                        '--input', str(source), '--output', str(destination), '--key-fd', str(key.fileno()),
                        '--kind', kind, '--context-sha256', self.context, '--library', str(LIBRARY),
                        '--library-sha256', LIBRARY_SHA]
                    if action == 'seal': argv += ['--key-id', 'laboratory-key-1', '--retain-until', str(int(time.time())+86400)]
                    result = subprocess.run(argv, pass_fds=(key.fileno(),), capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn(self.key, result.stdout + result.stderr)
                self.assertNotIn(b'private-value', result.stdout + result.stderr)
                self.assertIn(json.loads(result.stdout)['status'], ('sealed', 'restored'))
            self.assertEqual(restored.read_bytes(), self.data)

    def test_key_descriptors_reject_extra_bytes_and_standard_input(self):
        with self.assertRaises(AppError): vault.read_key_fd(0)
        bad = self.write('long-key', self.key+b'x')
        with bad.open('rb') as descriptor, self.assertRaises(AppError):
            vault.read_key_fd(descriptor.fileno())

    def test_native_initialization_failure_prevents_cipher_use_and_publication(self):
        from intune_iac.approval_authority import VerifierPin, _validator
        library = _validator(VerifierPin(Path(sys.executable), '', LIBRARY, LIBRARY_SHA))
        class FailedInitialization:
            def __getattr__(self, name):
                if name == 'sodium_init':
                    return lambda: -1
                return getattr(library, name)
        with patch('intune_iac.approval_authority._validator', return_value=FailedInitialization()):
            with self.assertRaises(AppError): self.seal('initialization-denied')
        self.assertFalse((self.root / 'initialization-denied').exists())


if __name__ == '__main__': unittest.main()
