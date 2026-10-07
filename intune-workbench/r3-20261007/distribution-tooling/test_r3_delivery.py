import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

import build_r3_evidence as builder
import restore_r3_evidence as restore
import publish_r3_git_chunks as publisher


class R3DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def epoch(self):
        root=self.root/'epoch-20261007-r3';root.mkdir();(root/'raw').mkdir()
        (root/'raw/failed.log').write_bytes(b'negative evidence\x00\xff')
        (root/'raw/empty').mkdir();(root/'sentinel').write_bytes(b'keep literal bytes')
        os.link(root/'sentinel',root/'hardlink-copy')
        (root/'negative-link').symlink_to('/outside/untrusted/target')
        return root

    def parts(self,data=b'complete archive bytes'):
        split=len(data)//2;parts=[]
        for i,raw in enumerate((data[:split],data[split:]),1):
            name='part%02d'%i;(self.root/name).write_bytes(raw)
            parts.append({'name':name,'bytes':len(raw),'sha256':builder.sha(raw),'url':name})
        value={'schema_version':restore.SCHEMA,'archive':{'name':'evidence.zip','bytes':len(data),'sha256':builder.sha(data)},'parts':parts}
        return value,data

    def test_entire_epoch_bytes_links_directories_and_hardlinks_preserved(self):
        epoch=self.epoch();output=self.root/'evidence.zip';before=builder.scan(epoch)
        result=builder.build(epoch,output,{'base':'R2 complete snapshot','product_commit':'a'*40})
        self.assertEqual(result['status'],'PASS');self.assertEqual(result['regular_files'],3)
        self.assertEqual(len(result['symlinks']),1);self.assertEqual(len(result['hardlink_groups']),1)
        self.assertEqual(before,builder.scan(epoch));self.assertFalse(result['complete_repository'])
        self.assertTrue(result['complete_evidence_epoch'])
        with zipfile.ZipFile(output) as z:
            manifest=json.loads(z.read(builder.ARCHIVE_ROOT+'/'+builder.MANIFEST))
            prefix=builder.ARCHIVE_ROOT+'/work/evidence/'+epoch.name+'/'
            self.assertEqual(z.read(prefix+'negative-link'),b'/outside/untrusted/target')
            self.assertTrue(stat.S_ISLNK(z.getinfo(prefix+'negative-link').external_attr>>16))
            self.assertEqual(z.read(prefix+'raw/failed.log'),b'negative evidence\x00\xff')
            self.assertEqual(z.read(prefix+'sentinel'),z.read(prefix+'hardlink-copy'))
            self.assertIn(prefix+'raw/empty/',z.namelist())
        self.assertEqual(builder.verify(output,manifest)['verified_entries'],len(manifest['entries']))

    def test_builder_rejects_existing_output_and_preserves_it(self):
        epoch=self.epoch();output=self.root/'existing.zip';output.write_bytes(b'preserved')
        with self.assertRaisesRegex(ValueError,'already exists'):builder.build(epoch,output,{})
        self.assertEqual(output.read_bytes(),b'preserved')

    def test_builder_rejects_output_inside_input(self):
        epoch=self.epoch()
        with self.assertRaisesRegex(ValueError,'outside epoch'):builder.build(epoch,epoch/'recursive.zip',{})
        self.assertFalse((epoch/'recursive.zip').exists())

    def test_builder_never_follows_output_ancestor_for_zip_or_receipt(self):
        epoch=self.epoch();before=builder.scan(epoch);alias=self.root/'alias';alias.symlink_to(epoch,target_is_directory=True)
        with self.assertRaises(OSError):builder.build(epoch,alias/'escape.zip',{})
        self.assertEqual(before,builder.scan(epoch))
        self.assertFalse((epoch/'escape.zip.receipt.json').exists())

    def test_builder_rejects_special_file_instead_of_skipping(self):
        epoch=self.epoch();os.mkfifo(epoch/'named-pipe')
        with self.assertRaisesRegex(ValueError,'Unsupported special'):builder.build(epoch,self.root/'bad.zip',{})
        self.assertTrue(stat.S_ISFIFO((epoch/'named-pipe').lstat().st_mode))

    def test_changed_epoch_fails_and_preserves_partial(self):
        epoch=self.epoch();original=builder.verify
        def change_after_verify(path,manifest):
            result=original(path,manifest);(epoch/'unexpected.tmp').write_bytes(b'preserve discrepancy');return result
        with mock.patch.object(builder,'verify',side_effect=change_after_verify):
            with self.assertRaisesRegex(ValueError,'file set or metadata changed'):builder.build(epoch,self.root/'changed.zip',{})
        self.assertTrue((self.root/'changed.zip.partial').exists());self.assertFalse((self.root/'changed.zip').exists())
        self.assertTrue((epoch/'unexpected.tmp').exists())
        self.assertEqual(json.loads((self.root/'changed.zip.receipt.json').read_text())['status'],'FAIL')

    def test_reassembly_exact_byte_identity_and_no_extraction(self):
        m,data=self.parts();restore.validate_distribution(m,len(data),builder.sha(data))
        output=self.root/'restored.zip';result=restore.reassemble(m,str(self.root/'manifest.json'),output)
        self.assertEqual(output.read_bytes(),data);self.assertEqual(result['sha256'],builder.sha(data))
        self.assertEqual(set(p.name for p in self.root.iterdir()),{'part01','part02','restored.zip'})

    def test_caller_pins_cannot_be_replaced_by_manifest(self):
        m,data=self.parts()
        with self.assertRaisesRegex(restore.RestoreError,'caller-supplied'):restore.validate_distribution(m,len(data),'0'*64)
        with self.assertRaisesRegex(restore.RestoreError,'caller-supplied'):restore.validate_distribution(m,len(data)+1,builder.sha(data))

    def test_resume_partial_into_second_chunk(self):
        m,data=self.parts();output=self.root/'resume.zip';(self.root/'resume.zip.partial').write_bytes(data[:-2])
        restore.reassemble(m,str(self.root/'manifest.json'),output);self.assertEqual(output.read_bytes(),data)

    def test_corrupt_chunk_preserved_and_not_published(self):
        m,data=self.parts();(self.root/'part01').write_bytes(b'x'*m['parts'][0]['bytes'])
        with self.assertRaisesRegex(restore.RestoreError,'Part integrity'):restore.reassemble(m,str(self.root/'manifest.json'),self.root/'corrupt.zip')
        self.assertFalse((self.root/'corrupt.zip').exists());self.assertTrue((self.root/'corrupt.zip.partial').exists())

    def test_output_never_overwritten(self):
        m,data=self.parts();output=self.root/'existing.zip';output.write_bytes(b'keep')
        with self.assertRaisesRegex(restore.RestoreError,'already exists'):restore.reassemble(m,str(self.root/'manifest.json'),output)
        self.assertEqual(output.read_bytes(),b'keep')

    def test_resume_symlink_not_followed(self):
        m,data=self.parts();victim=self.root/'victim';victim.write_bytes(b'keep')
        (self.root/'unsafe.zip.partial').symlink_to(victim)
        with self.assertRaises(OSError):restore.reassemble(m,str(self.root/'manifest.json'),self.root/'unsafe.zip')
        self.assertEqual(victim.read_bytes(),b'keep')

    def test_http_range_is_checked(self):
        class Response(io.BytesIO):
            status=206;headers={'Content-Range':'bytes 3-5/6'}
            def geturl(self):return 'https://raw.example.test/file'
        with mock.patch.object(restore.urllib.request,'urlopen',return_value=Response(b'def')):
            with restore.input_stream('https://raw.example.test/file',3) as response:self.assertEqual(response.read(),b'def')
        class Wrong(Response):headers={'Content-Range':'bytes 1-5/6'}
        with mock.patch.object(restore.urllib.request,'urlopen',return_value=Wrong(b'bcdef')):
            with self.assertRaisesRegex(restore.RestoreError,'Incorrect HTTP range'):
                with restore.input_stream('https://raw.example.test/file',3):pass

    def test_bare_git_chunks_preserve_exact_bytes_without_worktree_copies(self):
        raw=b'byte-exact-complete-evidence-archive';archive=self.root/'evidence.zip';archive.write_bytes(raw)
        receipt=self.root/'receipt.json';receipt.write_text(json.dumps({'status':'PASS','bytes':len(raw),'sha256':builder.sha(raw),'provenance':{'r3_source_commit':'a'*40}}))
        manifest=self.root/'distribution.json';repository=self.root/'data.git'
        with mock.patch.object(publisher,'CHUNK_BYTES',7):
            result=publisher.publish(archive,receipt,repository,manifest,push=False)
        self.assertEqual(result['status'],'LOCAL_STAGED');self.assertFalse(result['duplicate_chunk_worktree_files_created'])
        value=json.loads(manifest.read_text());combined=b''
        for part in value['parts']:
            output=subprocess.run(['git','--git-dir',str(repository),'cat-file','blob',result['data_commit']+':'+part['repository_path']],capture_output=True,check=True).stdout
            self.assertEqual(len(output),part['bytes']);self.assertEqual(builder.sha(output),part['sha256']);combined+=output
            self.assertIn('/'+result['data_commit']+'/',part['url'])
            self.assertFalse((repository/part['repository_path']).exists())
        self.assertEqual(combined,raw)

    def test_wrong_schema_duplicate_parts_and_traversal_rejected(self):
        for mutation in (lambda m:m.update(schema_version='intune-r2-split-release/1'),
                         lambda m:m['parts'][1].update(name=m['parts'][0]['name']),
                         lambda m:m['parts'][0].update(name='../outside')):
            m,data=self.parts();mutation(m)
            with self.assertRaises(restore.RestoreError):restore.validate_distribution(m,len(data),builder.sha(data))

if __name__=='__main__':unittest.main(verbosity=2)
