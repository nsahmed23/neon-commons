import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

import restore_r2 as r


def digest(data):
    return hashlib.sha256(data).hexdigest()


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, mutate=None, extra=None):
        payloads = [('dir', 'directory', b''), ('dir/file.txt', 'file', b'original evidence\x00\xff'),
                    ('dir/original-link', 'symlink', b'/untrusted/absolute/target')]
        entries = []
        for path, typ, raw in payloads:
            e = {'path': path, 'type': typ, 'bytes': len(raw), 'sha256': digest(raw), 'mode': 0o600}
            if typ == 'symlink':
                e['link_target'] = raw.decode()
            entries.append(e)
        document = {'schema': 'complete-continuation-snapshot/2', 'source_revision': 'a' * 40,
                    'entries': entries, 'link_inventory': [{'path': 'dir/original-link', 'target': '/untrusted/absolute/target'}],
                    'hardlink_groups': []}
        if mutate:
            mutate(document)
        raw_manifest = json.dumps(document).encode()
        snapshot = {'root': 'snapshot', 'manifest': 'manifest.json', 'manifest_sha256': digest(raw_manifest)}
        archive = self.root / 'fixture.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for path, typ, raw in payloads:
                info = zipfile.ZipInfo('snapshot/' + path + ('/' if typ == 'directory' else ''))
                info.external_attr = ({'directory': stat.S_IFDIR, 'file': stat.S_IFREG, 'symlink': stat.S_IFLNK}[typ] | 0o600) << 16
                z.writestr(info, raw)
            info = zipfile.ZipInfo('snapshot/manifest.json')
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            z.writestr(info, raw_manifest)
            if extra:
                extra(z)
        return archive, snapshot

    def parts(self, data=b'exact-original-ZIP-bytes'):
        middle = len(data) // 2
        parts = []
        for number, raw in enumerate((data[:middle], data[middle:])):
            name = 'part%d' % number
            (self.root / name).write_bytes(raw)
            parts.append({'name': name, 'bytes': len(raw), 'sha256': digest(raw), 'url': name})
        m = {'schema_version': r.SCHEMA, 'archive': {'name': 'whole.zip', 'bytes': len(data), 'sha256': digest(data)},
             'parts': parts, 'snapshot': {'root': 'snapshot', 'manifest': 'manifest.json', 'manifest_sha256': 'a' * 64}}
        return m, data

    def test_literal_symlink_quarantine_and_exact_regular_payload(self):
        archive, snapshot = self.fixture()
        out = self.root / 'new'
        receipt = r.extract_snapshot(archive, snapshot, out)
        self.assertEqual(receipt['regular_files_verified'], 1)
        self.assertEqual(receipt['directories_verified'], 1)
        self.assertFalse((out / 'snapshot/dir/original-link').exists())
        self.assertEqual((out / 'LINK-QUARANTINE/000000.target.txt').read_bytes(), b'/untrusted/absolute/target')
        self.assertEqual((out / 'snapshot/dir/file.txt').read_bytes(), b'original evidence\x00\xff')
        self.assertTrue((out / 'EXTRACTION-RECEIPT.json').is_file())
        self.assertFalse(any(p.is_symlink() for p in out.rglob('*')))

    def test_extract_existing_destination_unchanged(self):
        archive, snapshot = self.fixture()
        out = self.root / 'occupied'
        out.mkdir()
        (out / 'marker').write_text('keep')
        with self.assertRaises(FileExistsError):
            r.extract_snapshot(archive, snapshot, out)
        self.assertEqual((out / 'marker').read_text(), 'keep')

    def test_reject_symlink_output_ancestor(self):
        archive, snapshot = self.fixture()
        (self.root / 'real').mkdir()
        (self.root / 'alias').symlink_to(self.root / 'real', target_is_directory=True)
        with self.assertRaises(OSError):
            r.extract_snapshot(archive, snapshot, self.root / 'alias' / 'new')
        self.assertFalse((self.root / 'real' / 'new').exists())

    def test_traversal_rejected_before_output(self):
        for bad in ('../outside', '/absolute', 'C:/drive', 'snapshot/../escape', 'snapshot\\bad', 'snapshot//bad', 'snapshot/NUL'):
            with self.subTest(bad=bad):
                archive, snapshot = self.fixture(extra=lambda z: z.writestr(bad, b'x'))
                with self.assertRaises(r.RestoreError):
                    r.extract_snapshot(archive, snapshot, self.root / 'out')
                self.assertFalse((self.root / 'out').exists())

    def test_duplicate_archive_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            archive, snapshot = self.fixture(extra=lambda z: z.writestr('snapshot/dir/file.txt', b'x'))
        with self.assertRaisesRegex(r.RestoreError, 'Duplicate archive'):
            r.extract_snapshot(archive, snapshot, self.root / 'out')

    def test_duplicate_manifest_rejected(self):
        archive, snapshot = self.fixture(mutate=lambda d: d['entries'].append(dict(d['entries'][1])))
        with self.assertRaisesRegex(r.RestoreError, 'Duplicate manifest'):
            r.extract_snapshot(archive, snapshot, self.root / 'out')

    def test_extra_archive_file_rejected(self):
        archive, snapshot = self.fixture(extra=lambda z: z.writestr('snapshot/unexpected.tmp', b'preserve discrepancy'))
        with self.assertRaisesRegex(r.RestoreError, 'file sets differ'):
            r.extract_snapshot(archive, snapshot, self.root / 'out')
        self.assertTrue(archive.exists())
        self.assertFalse((self.root / 'out').exists())

    def test_missing_archive_file_rejected(self):
        def mutate(d):
            d['entries'].append({'path': 'absent', 'type': 'file', 'bytes': 0, 'sha256': digest(b'')})
        archive, snapshot = self.fixture(mutate=mutate)
        with self.assertRaisesRegex(r.RestoreError, 'file sets differ'):
            r.extract_snapshot(archive, snapshot, self.root / 'out')

    def test_wrong_payload_hash_retains_partial_extraction(self):
        archive, snapshot = self.fixture(mutate=lambda d: d['entries'][1].update(sha256='0' * 64))
        with self.assertRaisesRegex(r.RestoreError, 'Payload integrity'):
            r.extract_snapshot(archive, snapshot, self.root / 'out')
        self.assertTrue((self.root / 'out/snapshot/dir/file.txt').exists())
        self.assertFalse((self.root / 'out/EXTRACTION-RECEIPT.json').exists())

    def test_wrong_snapshot_manifest_hash_rejected_before_output(self):
        archive, snapshot = self.fixture()
        snapshot['manifest_sha256'] = '0' * 64
        with self.assertRaisesRegex(r.RestoreError, 'manifest integrity'):
            r.extract_snapshot(archive, snapshot, self.root / 'out')
        self.assertFalse((self.root / 'out').exists())

    def test_symlink_type_disagreement_rejected(self):
        archive, snapshot = self.fixture(mutate=lambda d: d['entries'][1].update(type='symlink', link_target='x'))
        with self.assertRaisesRegex(r.RestoreError, 'type mismatch'):
            r.extract_snapshot(archive, snapshot, self.root / 'out')

    def test_symlink_literal_mismatch_retained(self):
        def mutate(d):
            d['entries'][2]['link_target'] = '/different/target'
            d['link_inventory'][0]['target'] = '/different/target'
        archive, snapshot = self.fixture(mutate=mutate)
        with self.assertRaisesRegex(r.RestoreError, 'literal target mismatch'):
            r.extract_snapshot(archive, snapshot, self.root / 'out')
        self.assertFalse((self.root / 'out/snapshot/dir/original-link').exists())

    def test_link_inventory_mismatch_rejected(self):
        archive, snapshot = self.fixture(mutate=lambda d: d.update(link_inventory=[]))
        with self.assertRaisesRegex(r.RestoreError, 'Link inventory'):
            r.extract_snapshot(archive, snapshot, self.root / 'out')

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(r.RestoreError, 'Duplicate JSON'):
            r.loads(b'{"a":1,"a":2}')

    def test_reassembly_preserves_exact_bytes(self):
        m, data = self.parts()
        r.validate_distribution(m, pinned=False)
        out = self.root / 'complete.zip'
        result = r.reassemble(m, str(self.root / 'manifest.json'), out)
        self.assertEqual(out.read_bytes(), data)
        self.assertEqual(result['sha256'], digest(data))
        self.assertFalse((self.root / 'complete.zip.partial').exists())

    def test_resume_incomplete_part(self):
        m, data = self.parts()
        out = self.root / 'resume.zip'
        (self.root / 'resume.zip.partial').write_bytes(data[:3])
        r.reassemble(m, str(self.root / 'manifest.json'), out)
        self.assertEqual(out.read_bytes(), data)

    def test_resume_second_part(self):
        m, data = self.parts()
        out = self.root / 'resume.zip'
        (self.root / 'resume.zip.partial').write_bytes(data[:-2])
        r.reassemble(m, str(self.root / 'manifest.json'), out)
        self.assertEqual(out.read_bytes(), data)

    def test_corrupt_completed_part_rejected_and_preserved(self):
        m, data = self.parts()
        out = self.root / 'resume.zip'
        partial = self.root / 'resume.zip.partial'
        partial.write_bytes(b'x' + data[1:])
        with self.assertRaisesRegex(r.RestoreError, 'Part integrity'):
            r.reassemble(m, str(self.root / 'manifest.json'), out)
        self.assertFalse(out.exists())
        self.assertEqual(partial.read_bytes(), b'x' + data[1:])

    def test_corrupt_download_rejected_and_preserved(self):
        m, data = self.parts()
        (self.root / 'part0').write_bytes(b'x' * m['parts'][0]['bytes'])
        out = self.root / 'wrong.zip'
        with self.assertRaisesRegex(r.RestoreError, 'Part integrity'):
            r.reassemble(m, str(self.root / 'manifest.json'), out)
        self.assertFalse(out.exists())
        self.assertTrue((self.root / 'wrong.zip.partial').exists())

    def test_existing_completed_output_never_replaced(self):
        m, data = self.parts()
        out = self.root / 'existing.zip'
        out.write_bytes(b'preserve original')
        with self.assertRaisesRegex(r.RestoreError, 'already exists'):
            r.reassemble(m, str(self.root / 'manifest.json'), out)
        self.assertEqual(out.read_bytes(), b'preserve original')

    def test_cli_pins_reject_other_archive(self):
        m, _ = self.parts()
        with self.assertRaisesRegex(r.RestoreError, 'independently supplied'):
            r.validate_distribution(m)

    def test_partial_symlink_never_followed(self):
        m, _ = self.parts()
        victim = self.root / 'victim'
        victim.write_bytes(b'safe')
        (self.root / 'output.zip.partial').symlink_to(victim)
        with self.assertRaises(OSError):
            r.reassemble(m, str(self.root / 'manifest.json'), self.root / 'output.zip')
        self.assertEqual(victim.read_bytes(), b'safe')

    def test_https_resume_with_valid_content_range(self):
        class Response(io.BytesIO):
            status = 206
            headers = {'Content-Range': 'bytes 3-5/6'}
            def geturl(self):
                return 'https://release-assets.example.test/file'
        with mock.patch.object(r.urllib.request, 'urlopen', return_value=Response(b'def')) as request:
            with r.input_stream('https://github.example.test/file', start=3) as source:
                self.assertEqual(source.read(), b'def')
            self.assertEqual(request.call_args.args[0].get_header('Range'), 'bytes=3-')

    def test_https_resume_full_response_fallback(self):
        class Response(io.BytesIO):
            status = 200
            headers = {}
            def geturl(self):
                return 'https://release-assets.example.test/file'
        with mock.patch.object(r.urllib.request, 'urlopen', return_value=Response(b'abcdef')):
            with r.input_stream('https://github.example.test/file', start=3) as source:
                self.assertEqual(source.read(), b'def')

    def test_https_resume_bad_range_rejected(self):
        class Response(io.BytesIO):
            status = 206
            headers = {'Content-Range': 'bytes 1-5/6'}
            def geturl(self):
                return 'https://release-assets.example.test/file'
        with mock.patch.object(r.urllib.request, 'urlopen', return_value=Response(b'bcdef')):
            with self.assertRaisesRegex(r.RestoreError, 'Incorrect HTTP range'):
                with r.input_stream('https://github.example.test/file', start=3):
                    pass

    def test_untyped_manifest_entry_supported(self):
        archive, snapshot = self.fixture()
        rebuilt = self.root / 'untyped.zip'
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(rebuilt, 'w') as dest:
            for info in source.infolist():
                if info.filename == 'snapshot/manifest.json':
                    info.external_attr = 0o600 << 16
                dest.writestr(info, source.read(info))
        receipt = r.extract_snapshot(rebuilt, snapshot, self.root / 'untyped')
        self.assertEqual(receipt['status'], 'PASS')

    def test_http_not_accepted(self):
        with self.assertRaisesRegex(r.RestoreError, 'HTTPS'):
            r.read_limited('http://example.invalid/asset', 10)


if __name__ == '__main__':
    unittest.main(verbosity=2)
