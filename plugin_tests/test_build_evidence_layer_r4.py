"""Literal archive oracles and actual CLI controls for the R4 evidence producer."""
import hashlib
import importlib.util
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/build-evidence-layer.py'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class BuildEvidenceLayerR4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.epoch = self.root / 'epoch-fixture'
        self.epoch.mkdir()
        (self.epoch / 'nested/.git').mkdir(parents=True)
        (self.epoch / 'nested/.git/config').write_bytes(b'[core]\n hooksPath=/NEVER-RUN\n')
        (self.epoch / 'exact').write_bytes(b'\x00exact\r\n\xff')
        (self.epoch / 'executable').write_bytes(b'#!/bin/sh\nexit 73\n')
        (self.epoch / 'executable').chmod(0o700)
        os.link(self.epoch / 'exact', self.epoch / 'hardlink')
        self.sentinel = self.root / 'sentinel'
        self.sentinel.write_bytes(b'OUTSIDE MUST STAY UNCHANGED')
        (self.epoch / 'absolute-link').symlink_to(self.sentinel)
        (self.epoch / 'relative-link').symlink_to('../../outside')
        self.provenance = self.root / 'provenance.json'
        self.provenance.write_text(json.dumps({'fixture': True, 'source_commit': 'a' * 40}))
        self.output = self.root / 'output.zip'
        self.calls = []
        evidence = os.environ.get('INTUNE_BUILD_EVIDENCE_TEST_OUTPUT')
        self.evidence = Path(evidence) / self._testMethodName if evidence else None
        if self.evidence:
            self.evidence.mkdir(parents=True, exist_ok=False)
            self.addCleanup(self.preserve)

    def preserve(self):
        (self.evidence / 'commands.json').write_text(json.dumps(self.calls, indent=2, ensure_ascii=True) + '\n')
        shutil.copytree(self.epoch, self.evidence / 'source', symlinks=True,
                        ignore=lambda directory, names: [name for name in names if
                            stat.S_ISFIFO(os.lstat(Path(directory) / name).st_mode) or
                            stat.S_ISSOCK(os.lstat(Path(directory) / name).st_mode)])
        for path in self.root.iterdir():
            if path.is_file() and not path.is_symlink():
                shutil.copyfile(path, self.evidence / path.name)

    def invoke(self, *, output=None, epoch=None, omissions=None, **overrides):
        values = {'epoch': str(epoch or self.epoch), 'output': str(output or self.output),
                  'provenance': str(self.provenance), 'provenance-sha256': digest(self.provenance.read_bytes())}
        if omissions is not None:
            value = self.root / 'omissions.json'
            value.write_text(json.dumps(omissions))
            values.update({'ipc-omissions': str(value), 'ipc-omissions-sha256': digest(value.read_bytes())})
        values.update(overrides)
        argv = [sys.executable, '-B', str(SCRIPT)]
        for key, value in values.items():
            argv.extend(['--' + key, str(value)])
        result = subprocess.run(argv, capture_output=True, timeout=15, cwd='/tmp')
        self.calls.append({'argv': argv, 'returncode': result.returncode,
                          'stdout': result.stdout.decode(), 'stderr': result.stderr.decode()})
        return result

    def module(self):
        spec = importlib.util.spec_from_file_location('build_evidence_tested', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def rejected(self, result):
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(b'EVIDENCE BUILD FAILED:', result.stderr)
        self.assertNotIn(b'"status": "PASS"', result.stdout)
        self.assertEqual(self.sentinel.read_bytes(), b'OUTSIDE MUST STAY UNCHANGED')

    def test_actual_cli_typed_exact_payload_git_literal_links_hardlinks_and_reproducibility(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        archive_bytes = self.output.read_bytes()
        self.assertEqual(receipt['sha256'], digest(archive_bytes))
        prefix = 'Intune_R4_Evidence_20261007/work/evidence/epoch-fixture/'
        with zipfile.ZipFile(self.output) as archive:
            document = json.loads(archive.read('Intune_R4_Evidence_20261007/R4-EVIDENCE-MANIFEST.json'))
            self.assertEqual(archive.read(prefix + 'exact'), b'\x00exact\r\n\xff')
            self.assertEqual(archive.read(prefix + 'nested/.git/config'), b'[core]\n hooksPath=/NEVER-RUN\n')
            self.assertEqual(archive.read(prefix + 'relative-link'), b'../../outside')
            self.assertTrue(stat.S_ISLNK(archive.getinfo(prefix + 'absolute-link').external_attr >> 16))
            self.assertEqual(document['hardlink_groups'][0]['paths'],
                             ['work/evidence/epoch-fixture/exact', 'work/evidence/epoch-fixture/hardlink'])
            self.assertFalse(document['public_suitability_approved'])
            self.assertFalse(document['historical_R2_three_file_discrepancy_closed'])
            expected = {'Intune_R4_Evidence_20261007/' + entry['path'] +
                        ('/' if entry['type'] == 'directory' else '') for entry in document['entries']}
            expected.add('Intune_R4_Evidence_20261007/R4-EVIDENCE-MANIFEST.json')
            self.assertEqual(set(archive.namelist()), expected)
        second = self.root / 'second.zip'
        again = self.invoke(output=second)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(second.read_bytes(), archive_bytes)
        self.assertEqual(self.sentinel.read_bytes(), b'OUTSIDE MUST STAY UNCHANGED')

    def test_actual_cli_built_archive_restores_through_pinned_existing_helper(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        argv = [sys.executable, '-B', str(ROOT / 'scripts/restore-evidence-layer.py'),
                '--archive', str(self.output), '--output', str(self.root / 'restored'),
                '--bytes', str(receipt['bytes']), '--sha256', receipt['sha256'],
                '--snapshot-root', receipt['snapshot_root'], '--manifest', receipt['manifest'],
                '--manifest-sha256', receipt['manifest_sha256'], '--schema', receipt['schema']]
        restored = subprocess.run(argv, capture_output=True, timeout=15)
        self.calls.append({'argv': argv, 'returncode': restored.returncode,
                          'stdout': restored.stdout.decode(), 'stderr': restored.stderr.decode()})
        self.assertEqual(restored.returncode, 0, restored.stderr)
        base = self.root / 'restored/Intune_R4_Evidence_20261007/work/evidence/epoch-fixture'
        self.assertEqual((base / 'exact').read_bytes(), b'\x00exact\r\n\xff')
        self.assertEqual(os.readlink(base / 'relative-link'), '../../outside')
        self.assertNotEqual((base / 'exact').stat().st_ino, (base / 'hardlink').stat().st_ino)

    def test_actual_cli_control_and_bidi_names_are_literal_and_diagnostics_escaped(self):
        hostile = 'literal-\x1b]52;c;AAAA\x07-\u202e.txt'
        (self.epoch / hostile).write_bytes(b'literal negative filename')
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(b'\x1b', result.stdout + result.stderr)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.read('Intune_R4_Evidence_20261007/work/evidence/epoch-fixture/' + hostile),
                             b'literal negative filename')
        fifo = self.epoch / ('fifo-\x1b]52;c;AAAA\x07')
        os.mkfifo(fifo)
        result = self.invoke(output=self.root / 'rejected.zip')
        self.rejected(result)
        self.assertNotIn(b'\x1b', result.stderr)
        self.assertNotIn(b'\x07', result.stderr)
        self.assertTrue(stat.S_ISFIFO(fifo.lstat().st_mode))

    def test_actual_cli_unlisted_fifo_and_socket_preserved_without_output(self):
        fifo = self.epoch / 'pipe'
        os.mkfifo(fifo)
        self.rejected(self.invoke())
        self.assertFalse(self.output.exists())
        sock = socket.socket(socket.AF_UNIX)
        try:
            sock.bind(str(self.epoch / 'socket'))
            self.rejected(self.invoke(omissions={'schema_version': 'intune-r4-ipc-omissions/1',
                'entries': [{'path': 'pipe', 'type': 'fifo', 'reason': 'Discarded transient fixture transport, retain metadata.'}]}))
            self.assertTrue(stat.S_ISSOCK((self.epoch / 'socket').lstat().st_mode))
        finally:
            sock.close()

    def test_actual_cli_explicit_ipc_omissions_are_metadata_not_false_complete_epoch(self):
        os.mkfifo(self.epoch / 'pipe')
        result = self.invoke(omissions={'schema_version': 'intune-r4-ipc-omissions/1',
            'entries': [{'path': 'pipe', 'type': 'fifo', 'reason': 'Transient IPC endpoint has no transferable payload.'}]})
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(self.output) as archive:
            document = json.loads(archive.read('Intune_R4_Evidence_20261007/R4-EVIDENCE-MANIFEST.json'))
            self.assertFalse(document['complete_evidence_epoch'])
            self.assertTrue(document['complete_archivable_evidence_epoch'])
            self.assertEqual(document['explicit_ipc_omissions'][0]['type'], 'fifo')
            self.assertFalse(any(name.endswith('/pipe') for name in archive.namelist()))
        self.assertTrue(stat.S_ISFIFO((self.epoch / 'pipe').lstat().st_mode))

    def test_actual_cli_wrong_pin_duplicate_json_and_regular_omission_refused(self):
        self.rejected(self.invoke(**{'provenance-sha256': '0' * 64}))
        self.provenance.write_bytes(b'{"same":1,"same":2}')
        self.rejected(self.invoke())
        self.provenance.write_text('{}')
        self.rejected(self.invoke(omissions={'schema_version': 'intune-r4-ipc-omissions/1',
            'entries': [{'path': 'exact', 'type': 'fifo', 'reason': 'Must not exclude regular evidence.'}]}))
        self.assertFalse(self.output.exists())

    def test_actual_cli_missing_traversal_duplicate_and_wrong_type_omissions_refused(self):
        for entries in ([{'path': '../escape', 'type': 'fifo', 'reason': 'no'}],
                        [{'path': 'absent', 'type': 'fifo', 'reason': 'no'}],
                        [{'path': 'exact', 'type': 'file', 'reason': 'no'}],
                        [{'path': 'pipe', 'type': 'fifo', 'reason': 'x'}] * 2):
            with self.subTest(entries=entries):
                self.rejected(self.invoke(omissions={'schema_version': 'intune-r4-ipc-omissions/1', 'entries': entries}))
        self.assertFalse(self.output.exists())

    def test_actual_cli_symlink_source_output_document_and_ancestors_refused(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        self.rejected(self.invoke(epoch=alias / self.epoch.name))
        self.rejected(self.invoke(output=alias / 'output.zip'))
        self.rejected(self.invoke(**{'provenance': str(alias / self.provenance.name)}))
        linked = self.root / 'linked-epoch'
        linked.symlink_to(self.epoch, target_is_directory=True)
        self.rejected(self.invoke(epoch=linked))
        self.assertFalse(self.output.exists())

    def test_actual_cli_no_overwrite_any_existing_output_partial_receipt_or_input_tree(self):
        self.rejected(self.invoke(output=self.epoch / 'must-not-build.zip'))
        for suffix in ('', '.partial', '.receipt.json'):
            output = self.root / ('existing' + str(len(suffix)) + '.zip')
            existing = output.with_name(output.name + suffix)
            existing.write_bytes(b'PRESERVE')
            self.rejected(self.invoke(output=output))
            self.assertEqual(existing.read_bytes(), b'PRESERVE')

    def test_changed_source_after_archive_keeps_partial_and_failed_receipt(self):
        module = self.module()
        original = module.verify
        def changed(*args):
            result = original(*args)
            (self.epoch / 'unexpected').write_bytes(b'PRESERVED UNEXPECTED FILE')
            return result
        with patch.object(module, 'verify', changed):
            with self.assertRaisesRegex(ValueError, 'epoch changed'):
                module.build(self.epoch, self.output, {'fixture': True})
        self.assertFalse(self.output.exists())
        self.assertTrue(self.output.with_name('output.zip.partial').is_file())
        self.assertEqual(json.loads(self.output.with_name('output.zip.receipt.json').read_text())['status'], 'FAIL')
        self.assertEqual((self.epoch / 'unexpected').read_bytes(), b'PRESERVED UNEXPECTED FILE')

    def test_changed_source_identity_at_open_is_refused_without_following_replacement(self):
        module = self.module()
        original = module.info_for
        def changed(name, mode):
            if name.endswith('/exact'):
                # Source has already been opened; this replacement must fail the
                # post-read identity assertion without dereferencing the link.
                (self.epoch / 'exact').unlink()
                (self.epoch / 'exact').symlink_to(self.sentinel)
            return original(name, mode)
        with patch.object(module, 'info_for', changed):
            with self.assertRaisesRegex(ValueError, 'Source changed'):
                module.build(self.epoch, self.output, {'fixture': True})
        self.assertFalse(self.output.exists())
        self.assertEqual(self.sentinel.read_bytes(), b'OUTSIDE MUST STAY UNCHANGED')

    def test_published_name_substitution_is_preserved_and_cannot_return_pass(self):
        module = self.module()
        original = module.os.link
        def substitute(source, destination, **kwargs):
            self.output.with_name('output.zip.partial').rename(self.root / 'retained-written.zip')
            self.output.with_name('output.zip.partial').write_bytes(b'SUBSTITUTED FINAL BYTES')
            return original(source, destination, **kwargs)
        with patch.object(module.os, 'link', substitute):
            with self.assertRaisesRegex(ValueError, 'Published archive identity changed'):
                module.build(self.epoch, self.output, {'fixture': True})
        self.assertEqual(self.output.read_bytes(), b'SUBSTITUTED FINAL BYTES')
        self.assertEqual(self.output.with_name('output.zip.partial').read_bytes(), b'SUBSTITUTED FINAL BYTES')
        self.assertTrue(zipfile.is_zipfile(self.root / 'retained-written.zip'))
        self.assertEqual(json.loads(self.output.with_name('output.zip.receipt.json').read_text())['status'], 'FAIL')

    def test_failed_receipt_does_not_mask_primary_verification_failure(self):
        module = self.module()
        original = module.os.open
        def fail_receipt(path, *args, **kwargs):
            if path == 'output.zip.receipt.json':
                raise OSError('SECONDARY \x1b]52;c;AAAA\x07')
            return original(path, *args, **kwargs)
        stderr = io.StringIO()
        with (patch.object(module, 'verify', side_effect=ValueError('PRIMARY VERIFICATION FAILURE')),
              patch.object(module.os, 'open', fail_receipt), redirect_stderr(stderr)):
            with self.assertRaisesRegex(ValueError, 'PRIMARY VERIFICATION FAILURE'):
                module.build(self.epoch, self.output, {'fixture': True})
        self.assertFalse(self.output.exists())
        self.assertTrue(self.output.with_name('output.zip.partial').exists())
        self.assertIn('primary_error_preserved', stderr.getvalue())
        self.assertNotIn('\x1b', stderr.getvalue())
        self.assertNotIn('\x07', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
