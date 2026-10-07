"""Literal independently expected snapshot bytes, failure retention and CLI tests."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).absolute().parents[1]
spec=importlib.util.spec_from_file_location('snapshot_subject',ROOT/'scripts/prepare-evidence-snapshot.py')
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)
BASE=Path(os.environ.get('INTUNE_SNAPSHOT_TEST_ROOT') or tempfile.mkdtemp(prefix='intune-evidence-snapshot-tests-'))
BASE.mkdir(exist_ok=True)

class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.root=BASE/self._testMethodName;self.root.mkdir();self.a=self.root/'evidence';self.a.mkdir();self.b=self.root/'failed-stage';self.b.mkdir();self.out=self.root/'new-snapshot';self.map={'schema_version':S.SCHEMA,'roots':[self.row(self.a,'r4'),self.row(self.b,'tmp/failed-stage')]}
        (self.a/'exact.bin').write_bytes(b'\x00\r\n\xffliteral bytes\n');(self.b/'failure.log').write_bytes(b'FAIL retained\r\n')
    def row(self,path,prefix,kind='directory'):return {'source':str(path),'prefix':prefix,'type':kind,'owner':'literal test owner','reason':'retain literal qualification evidence'}
    def run_snapshot(self,document=None,**kw):
        document=document or self.map;return S.snapshot(document,self.out,document_sha256=S.B.sha(S.B.canonical(document)),**kw)
    def test_actual_cli_preserves_literal_bytes_symlinks_empty_dirs_and_mode_metadata(self):
        (self.a/'empty').mkdir();script=self.a/'-\u96ea run.sh';script.write_bytes(b'#!/bin/sh\nexit 7\n');script.chmod(0o755)
        outside=self.root/'unrelated';outside.write_bytes(b'DO NOT READ THIS TARGET');os.symlink(str(outside),self.a/'absolute-link');os.symlink('../missing',self.a/'broken-link')
        os.link(self.a/'exact.bin',self.a/'hardlinked-copy.bin')
        mapping=self.root/'roots.json';raw=S.B.canonical(self.map);mapping.write_bytes(raw)
        child=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/prepare-evidence-snapshot.py'),'--roots',str(mapping),'--roots-sha256',hashlib.sha256(raw).hexdigest(),'--output',str(self.out)],capture_output=True)
        (self.root/'stdout.raw').write_bytes(child.stdout);(self.root/'stderr.raw').write_bytes(child.stderr)
        self.assertEqual(child.returncode,0);receipt=json.loads(child.stdout);self.assertEqual(receipt['status'],'PASS')
        self.assertEqual((self.out/'r4/exact.bin').read_bytes(),b'\x00\r\n\xffliteral bytes\n');self.assertEqual((self.out/'tmp/failed-stage/failure.log').read_bytes(),b'FAIL retained\r\n')
        self.assertEqual(os.readlink(self.out/'r4/absolute-link'),str(outside));self.assertEqual(os.readlink(self.out/'r4/broken-link'),'../missing');self.assertEqual(outside.read_bytes(),b'DO NOT READ THIS TARGET')
        self.assertEqual((self.out/'r4/hardlinked-copy.bin').stat().st_nlink,1);self.assertNotEqual((self.out/'r4/hardlinked-copy.bin').stat().st_ino,(self.out/'r4/exact.bin').stat().st_ino)
        self.assertEqual(stat.S_IMODE((self.out/'r4/-\u96ea run.sh').stat().st_mode),0o700);self.assertTrue((self.out/'r4/empty').is_dir())
        before=json.loads((self.out/'_snapshot/source-before.json').read_bytes());self.assertEqual(before['roots'][0]['entries']['exact.bin']['source_signature'][-1],2)
    def test_empty_selected_root_materializes_its_structural_prefix_parents(self):
        empty=self.root/'empty-source';empty.mkdir()
        document={'schema_version':S.SCHEMA,'roots':[self.row(empty,'task-owned/temporary/empty-source')]}
        result=self.run_snapshot(document)
        self.assertEqual(result['status'],'PASS');self.assertTrue((self.out/'task-owned/temporary/empty-source').is_dir())
        self.assertEqual(list((self.out/'task-owned/temporary/empty-source').iterdir()),[])

    def test_existing_output_never_overwritten_and_all_originals_remain(self):
        self.run_snapshot();before=(self.out/'r4/exact.bin').read_bytes()
        with self.assertRaises(ValueError):self.run_snapshot()
        self.assertEqual((self.out/'r4/exact.bin').read_bytes(),before);self.assertEqual((self.a/'exact.bin').read_bytes(),before)
    def test_source_and_output_overlap_rejected_before_creation(self):
        self.out=self.a/'nested-new'
        with self.assertRaises(ValueError):self.run_snapshot()
        self.assertFalse(self.out.exists())
        self.out=self.root/'out';document={'schema_version':S.SCHEMA,'roots':[self.row(self.a,'r4'),self.row(self.a/'child','child')]}
        with self.assertRaises(ValueError):self.run_snapshot(document)
        self.assertFalse(self.out.exists())
    def test_prefix_overlap_alias_reserved_and_traversal_rejected(self):
        for prefixes in (('x','x/child'),('x','X'),('../x','y'),('_SNAPSHOT','y'),('x\\y','z')):
            with self.subTest(prefixes=prefixes):
                document={'schema_version':S.SCHEMA,'roots':[self.row(self.a,prefixes[0]),self.row(self.b,prefixes[1])]}
                with self.assertRaises(ValueError):self.run_snapshot(document)
                self.assertFalse(self.out.exists())
    def test_literal_file_and_symlink_roots_are_explicitly_supported(self):
        target=self.root/'not-read';target.write_bytes(b'external');link=self.root/'literal-link';os.symlink(str(target),link)
        document={'schema_version':S.SCHEMA,'roots':[self.row(self.a/'exact.bin','stdout/exact.bin','file'),self.row(link,'links/negative','symlink')]}
        self.run_snapshot(document);self.assertEqual((self.out/'stdout/exact.bin').read_bytes(),b'\x00\r\n\xffliteral bytes\n');self.assertEqual(os.readlink(self.out/'links/negative'),str(target))
    def test_symlink_ancestor_is_never_followed(self):
        alias=self.root/'alias';alias.symlink_to(self.a,target_is_directory=True)
        document={'schema_version':S.SCHEMA,'roots':[self.row(alias,'r4')]}
        with self.assertRaises(OSError):self.run_snapshot(document)
        self.assertFalse(self.out.exists())
    def test_fifo_requires_exact_pinned_omission_and_roundtrip_preserves_metadata(self):
        os.mkfifo(self.a/'ended-ipc')
        with self.assertRaises(ValueError):self.run_snapshot()
        self.assertTrue(stat.S_ISFIFO((self.a/'ended-ipc').lstat().st_mode));self.assertFalse(self.out.exists())
        self.out=self.root/'new-with-explicit-omission';omissions={'schema_version':'intune-r4-ipc-omissions/1','entries':[{'path':'r4/ended-ipc','type':'fifo','reason':'Ended disposable reader IPC; source retained, endpoint not reconstructed.'}]}
        self.run_snapshot(omissions=omissions,omissions_sha256=S.B.sha(S.B.canonical(omissions)))
        self.assertFalse((self.out/'r4/ended-ipc').exists());meta=json.loads((self.out/'_snapshot/snapshot.json').read_bytes());self.assertFalse(meta['complete_selected_roots']);self.assertFalse(meta['complete_original_corpus_established'])
        archive=self.root/'snapshot.zip';receipt=S.B.build(self.out,archive,{'scope':'literal fixture snapshot','snapshot_metadata':meta})
        restored=self.root/'restore-new';S.R.extract(archive,archive_bytes=receipt['bytes'],archive_sha256=receipt['sha256'],snapshot={'root':receipt['snapshot_root'],'manifest':receipt['manifest'],'manifest_sha256':receipt['manifest_sha256'],'schema':receipt['schema']},output=restored)
        result=restored/receipt['snapshot_root']/'work/evidence'/self.out.name
        self.assertEqual((result/'r4/exact.bin').read_bytes(),b'\x00\r\n\xffliteral bytes\n');self.assertEqual(json.loads((result/'_snapshot/ipc-omissions.json').read_bytes()),omissions)
    def test_unlisted_or_false_type_omissions_fail_closed(self):
        for entry in ({'path':'r4/exact.bin','type':'fifo','reason':'invalid regular omission'},{'path':'r4/missing','type':'socket','reason':'not present'}):
            with self.subTest(entry=entry):
                self.out=self.root/('denied-'+entry['type']);doc={'schema_version':'intune-r4-ipc-omissions/1','entries':[entry]}
                with self.assertRaises(ValueError):self.run_snapshot(omissions=doc,omissions_sha256=S.B.sha(S.B.canonical(doc)))
                self.assertFalse(self.out.exists())
    def test_source_changed_during_copy_preserves_failed_partial(self):
        original=S._copy_file;changed=[]
        def copy(*args):
            original(*args)
            if not changed:(self.a/'exact.bin').write_bytes(b'changed while copying');changed.append(True)
        with patch.object(S,'_copy_file',side_effect=copy),self.assertRaises(ValueError):self.run_snapshot()
        self.assertTrue(self.out.exists());self.assertEqual((self.a/'exact.bin').read_bytes(),b'changed while copying');receipt=json.loads(self.out.with_name(self.out.name+'.snapshot-receipt.json').read_bytes());self.assertEqual(receipt['status'],'FAIL');self.assertTrue(receipt['partial_preserved'])
    def test_source_replacement_with_symlink_denied_before_target_read(self):
        outside=self.root/'outside';outside.write_bytes(b'not copied');original=S._copy_file;changed=[]
        def copy(fd,leaf,*args):
            if not changed:
                (self.a/'exact.bin').rename(self.a/'retained-original');os.symlink(str(outside),self.a/'exact.bin');changed.append(True)
            return original(fd,leaf,*args)
        with patch.object(S,'_copy_file',side_effect=copy),self.assertRaises(OSError):self.run_snapshot()
        self.assertEqual(outside.read_bytes(),b'not copied');self.assertTrue((self.a/'retained-original').exists())
    def test_unexpected_output_is_preserved_and_prevents_pass(self):
        original=S.R.verify_output
        def verify(fd,expected):
            (self.out/'unexpected-retained').write_bytes(b'literal negative');return original(fd,expected)
        with patch.object(S.R,'verify_output',side_effect=verify),self.assertRaises(ValueError):self.run_snapshot()
        self.assertEqual((self.out/'unexpected-retained').read_bytes(),b'literal negative')
    def test_source_change_during_final_output_readback_is_rejected(self):
        original=S.R.verify_output
        def verify(*args):
            original(*args);(self.a/'late-added').write_bytes(b'retained source addition')
        with patch.object(S.R,'verify_output',side_effect=verify),self.assertRaises(ValueError):self.run_snapshot()
        self.assertEqual((self.a/'late-added').read_bytes(),b'retained source addition')
    def test_primary_cleanup_failure_is_not_replaced_and_every_fd_closed(self):
        primary=KeyboardInterrupt('literal primary');closed=[]
        def close(fd):closed.append(fd);raise RuntimeError('secondary close')
        with patch.object(S.os,'close',side_effect=close),self.assertRaises(KeyboardInterrupt) as caught:
            with S._handles() as handles:handles.extend([101,102,103]);raise primary
        self.assertIs(caught.exception,primary);self.assertEqual(closed,[103,102,101]);self.assertEqual(primary.snapshot_cleanup_failures,['RuntimeError']*3)

if __name__=='__main__':unittest.main()
