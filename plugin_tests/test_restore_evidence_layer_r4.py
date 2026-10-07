"""Independent literal ZIP/manifest oracle for the no-follow evidence restorer.

Fixture construction deliberately does not use the product's normalizers,
inventory builders or hashing helpers. Most assertions drive the real CLI.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

PROJECT=Path(__file__).resolve().parents[1]
SCRIPT=PROJECT/'scripts/restore-evidence-layer.py'
SCHEMA='intune-r4-evidence-supplement/1'


def literal_sha(value):return hashlib.sha256(value).hexdigest()


class EvidenceRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.archive=self.root/'evidence.zip';self.output=self.root/'restored'
        self.calls=[]
        destination=os.environ.get('INTUNE_RESTORE_TEST_EVIDENCE')
        self.evidence=Path(destination)/self._testMethodName if destination else None
        if self.evidence:
            self.evidence.mkdir(parents=True,exist_ok=False)
            self.addCleanup(self.preserve)

    def preserve(self):
        (self.evidence/'commands.json').write_text(json.dumps(self.calls,indent=2)+'\n')
        if self.archive.exists():(self.evidence/'input.zip').write_bytes(self.archive.read_bytes())
        if self.output.exists():
            shutil.copytree(self.output,self.evidence/'partial-or-complete-output',symlinks=True)
            records=[]
            for parent,dirs,files in os.walk(self.output,followlinks=False):
                for name in dirs+files:
                    path=Path(parent)/name;meta=path.lstat()
                    item={'path':str(path.relative_to(self.output)),'mode':meta.st_mode}
                    if path.is_symlink():item.update(type='symlink',target=os.readlink(path))
                    elif path.is_file():item.update(type='file',bytes=meta.st_size,sha256=literal_sha(path.read_bytes()))
                    else:item.update(type='directory')
                    records.append(item)
            (self.evidence/'output-inventory.json').write_text(json.dumps(records,indent=2)+'\n')

    def fixture(self,*,entries=None,extra=None,changes=None,manifest_changes=None):
        if entries is None:
            entries=[('data','directory',b''),('data/exact.bin','file',b'\x00literal\r\n\xff'),
                ('data/run.sh','file',b'#!/bin/sh\nexit 71\n'),('fixture','directory',b''),
                ('fixture/.git','directory',b''),('fixture/.git/config','file',b'[core]\n hooksPath = /NEVER-EXECUTE\n'),
                ('negative','directory',b''),('negative/absolute','symlink',b'/DO-NOT-FOLLOW-THIS-TARGET'),
                ('negative/relative','symlink',b'../../outside')]
        inventory=[];payload=[]
        for path,kind,raw in entries:
            item={'path':path,'type':kind,'bytes':len(raw),'sha256':literal_sha(raw),'mode':0o755 if path.endswith('run.sh') else 0o600}
            if kind=='symlink':item['link_target']=raw.decode()
            inventory.append(item);payload.append((path,kind,raw))
        document={'schema':SCHEMA,'entries':inventory,'link_inventory':[{'path':i['path'],'target':i['link_target']} for i in inventory if i['type']=='symlink'],
                  'hardlink_groups':[]}
        if manifest_changes:manifest_changes(document)
        raw=json.dumps(document,sort_keys=True).encode()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(self.archive,'w',compression=zipfile.ZIP_STORED) as archive:
                archive.writestr('layer/MANIFEST.json',raw)
                for path,kind,data in payload:
                    entry=zipfile.ZipInfo('layer/'+path+('/' if kind=='directory' else ''))
                    mode={'file':stat.S_IFREG,'directory':stat.S_IFDIR,'symlink':stat.S_IFLNK}[kind]
                    entry.create_system=3;entry.external_attr=(mode|0o600)<<16
                    if changes:changes(entry,path)
                    archive.writestr(entry,data)
                if extra:
                    for name,data in extra:archive.writestr(name,data)
        self.snapshot={'root':'layer','manifest':'MANIFEST.json','manifest_sha256':literal_sha(raw),'schema':SCHEMA}
        return document

    def invoke(self,**overrides):
        source=overrides.pop('archive',self.archive);out=overrides.pop('output',self.output)
        values={'bytes':str(self.archive.stat().st_size),'sha256':literal_sha(self.archive.read_bytes()),
            'snapshot-root':self.snapshot['root'],'manifest':self.snapshot['manifest'],
            'manifest-sha256':self.snapshot['manifest_sha256'],'schema':self.snapshot['schema']}
        values.update(overrides)
        command=[sys.executable,'-B',str(SCRIPT),'--archive',str(source),'--output',str(out)]
        for name,value in values.items():command.extend(['--'+name,str(value)])
        result=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=10)
        self.calls.append({'argv':command,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        return result

    def assert_rejected(self,result,*,before_write=True):
        self.assertEqual(result.returncode,1,result.stdout+result.stderr)
        self.assertIn('EXTRACTION FAILED:',result.stderr)
        self.assertNotIn('"status": "PASS"',result.stdout)
        self.assertFalse((self.output/'EXTRACTION-RECEIPT.json').exists())
        if before_write:self.assertFalse(self.output.exists())

    def test_actual_cli_exact_binary_nested_git_and_final_literal_links(self):
        document=self.fixture();original=self.archive.read_bytes()
        outside=self.root/'outside';outside.write_bytes(b'OUTSIDE MUST REMAIN UNTOUCHED')
        result=self.invoke();self.assertEqual(result.returncode,0,result.stderr)
        receipt=json.loads(result.stdout)
        self.assertEqual((self.output/'layer/data/exact.bin').read_bytes(),b'\x00literal\r\n\xff')
        self.assertEqual((self.output/'layer/fixture/.git/config').read_bytes(),b'[core]\n hooksPath = /NEVER-EXECUTE\n')
        self.assertEqual(os.readlink(self.output/'layer/negative/absolute'),'/DO-NOT-FOLLOW-THIS-TARGET')
        self.assertEqual(os.readlink(self.output/'layer/negative/relative'),'../../outside')
        self.assertEqual(outside.read_bytes(),b'OUTSIDE MUST REMAIN UNTOUCHED')
        self.assertEqual(self.archive.read_bytes(),original)
        self.assertEqual(receipt['regular_files_verified'],3)
        self.assertEqual(receipt['directories_verified'],4)
        self.assertEqual(len(receipt['literal_links_created_last']),2)
        self.assertEqual(receipt['links_followed'],0)
        self.assertFalse(receipt['content_executed']);self.assertFalse(receipt['historical_three_unexpected_files_closed'])
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode),0o700)
        self.assertEqual(stat.S_IMODE((self.output/'layer/data/exact.bin').stat().st_mode),0o600)
        self.assertEqual(stat.S_IMODE((self.output/'layer/data/run.sh').stat().st_mode),0o700)
        expected={'layer','layer/MANIFEST.json','EXTRACTION-RECEIPT.json'}|{'layer/'+i['path'] for i in document['entries']}
        actual={str(p.relative_to(self.output)) for p in self.output.rglob('*')}
        self.assertEqual(actual,expected)

    def test_actual_cli_wrong_archive_size_hash_and_manifest_pin_write_nothing(self):
        self.fixture();before=self.archive.read_bytes()
        for override in ({'bytes':self.archive.stat().st_size+1},{'sha256':'0'*64},{'manifest-sha256':'0'*64}):
            with self.subTest(override=override):self.assert_rejected(self.invoke(**override))
        self.assertEqual(self.archive.read_bytes(),before)

    def test_actual_cli_traversal_absolute_windows_alias_and_duplicate_members(self):
        for name in ('../escape','/absolute','C:/drive','layer/back\\slash','layer/a/../escape',
                     'layer/CON','layer/alternate:stream','layer/trailing.','layer//double','layer/data/exact.bin'):
            with self.subTest(name=name):
                self.fixture(extra=[(name,b'hostile')]);self.assert_rejected(self.invoke())

    def test_actual_cli_duplicate_manifest_path_and_json_key_are_refused(self):
        self.fixture(manifest_changes=lambda doc:doc['entries'].append(copy.deepcopy(doc['entries'][0])))
        self.assert_rejected(self.invoke())
        # The archive is correctly pinned but its JSON contains a duplicate key.
        raw=b'{"schema":"'+SCHEMA.encode()+b'","schema":"'+SCHEMA.encode()+b'","entries":[],"link_inventory":[]}'
        with zipfile.ZipFile(self.archive,'w') as archive:archive.writestr('layer/MANIFEST.json',raw)
        self.snapshot['manifest_sha256']=literal_sha(raw)
        self.assert_rejected(self.invoke())

    def test_actual_cli_zip_null_name_alias_is_rejected_before_output(self):
        self.fixture(entries=[('harmless','file',b'payload')],
            manifest_changes=lambda doc:doc['entries'][0].update(path='harm'))
        raw=self.archive.read_bytes()
        self.assertEqual(raw.count(b'layer/harmless'),2)
        self.archive.write_bytes(raw.replace(b'layer/harmless',b'layer/harm\x00ess'))
        self.assert_rejected(self.invoke())

    def test_actual_cli_type_mismatch_fifo_and_symlink_parent_are_refused(self):
        for mode in (stat.S_IFLNK,stat.S_IFIFO,stat.S_IFDIR):
            with self.subTest(mode=mode):
                def changed(entry,path):
                    if path=='data/exact.bin':entry.external_attr=(mode|0o600)<<16
                self.fixture(changes=changed);self.assert_rejected(self.invoke())
        self.fixture(entries=[('link','symlink',b'/outside'),('link/child','file',b'no')])
        self.assert_rejected(self.invoke())

    def test_actual_cli_member_set_missing_parent_and_link_inventory_are_refused(self):
        self.fixture(extra=[('layer/unlisted',b'no')]);self.assert_rejected(self.invoke())
        self.fixture(entries=[('missing/child','file',b'no')]);self.assert_rejected(self.invoke())
        self.fixture(manifest_changes=lambda doc:doc['link_inventory'].clear());self.assert_rejected(self.invoke())

    def test_actual_cli_payload_hash_failure_preserves_partial_and_archive(self):
        def corrupt(doc):
            next(item for item in doc['entries'] if item['path']=='data/exact.bin')['sha256']='0'*64
        self.fixture(manifest_changes=corrupt);before=self.archive.read_bytes()
        self.assert_rejected(self.invoke(),before_write=False)
        self.assertTrue((self.output/'layer/data/exact.bin').exists())
        self.assertEqual(self.archive.read_bytes(),before)
        self.assertFalse((self.output/'layer/negative/absolute').is_symlink())

    def test_actual_cli_earlier_link_is_not_published_before_later_file_verification(self):
        def corrupt(doc):doc['entries'][-1]['sha256']='0'*64
        self.fixture(entries=[('negative-link','symlink',b'/outside'),('later-file','file',b'later')],manifest_changes=corrupt)
        self.assert_rejected(self.invoke(),before_write=False)
        self.assertFalse((self.output/'layer/negative-link').is_symlink())
        self.assertEqual((self.output/'layer/later-file').read_bytes(),b'later')

    def test_actual_cli_crc_failure_preserves_partial_without_links(self):
        self.fixture()
        original=self.archive.read_bytes();needle=b'\x00literal\r\n\xff'
        self.assertEqual(original.count(needle),1)
        self.archive.write_bytes(original.replace(needle,b'\x00Literal\r\n\xff'))
        before=self.archive.read_bytes()
        self.assert_rejected(self.invoke(),before_write=False)
        self.assertIn('CRC',self.calls[-1]['stderr'])
        self.assertTrue(self.output.exists());self.assertEqual(self.archive.read_bytes(),before)
        self.assertFalse((self.output/'layer/negative/absolute').is_symlink())

    def test_actual_cli_existing_directory_file_and_symlink_are_never_overwritten(self):
        self.fixture();existing=self.root/'existing';existing.mkdir();sentinel=existing/'sentinel';sentinel.write_bytes(b'keep')
        for destination in (existing,sentinel):
            with self.subTest(destination=str(destination)):
                result=self.invoke(output=destination);self.assertEqual(result.returncode,1)
                self.assertEqual(sentinel.read_bytes(),b'keep')
        linked=self.root/'linked';linked.symlink_to(existing,target_is_directory=True)
        self.assertEqual(self.invoke(output=linked).returncode,1)
        self.assertTrue(linked.is_symlink());self.assertEqual(sentinel.read_bytes(),b'keep')
        self.assertEqual({p.name for p in existing.iterdir()},{'sentinel'})

    def test_actual_cli_source_and_output_symlink_ancestors_are_refused(self):
        self.fixture();before=self.archive.read_bytes()
        alias=self.root/'parent-link';alias.symlink_to(self.root,target_is_directory=True)
        self.assert_rejected(self.invoke(archive=alias/self.archive.name))
        self.assert_rejected(self.invoke(output=alias/'restored'))
        leaf=self.root/'source-link.zip';leaf.symlink_to(self.archive)
        self.assert_rejected(self.invoke(archive=leaf))
        self.assertEqual(self.archive.read_bytes(),before)

    def test_changed_open_archive_after_initial_pin_fails_without_pass_receipt(self):
        self.fixture();source=self.archive.read_bytes()
        spec=importlib.util.spec_from_file_location('independent_restore_changed',SCRIPT)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        original=module.file_chunks;changed=False
        def injected(stream):
            nonlocal changed
            yield from original(stream)
            if not changed:
                changed=True
                with self.archive.open('ab') as output:output.write(b'CHANGED AFTER PIN')
        module.file_chunks=injected
        with self.assertRaises(module.RestoreError) as failure:
            module.extract(self.archive,archive_bytes=len(source),archive_sha256=literal_sha(source),snapshot=self.snapshot,output=self.output)
        self.assertIn('Archive changed',str(failure.exception))
        self.assertTrue((self.output/'layer/data/exact.bin').exists())
        self.assertFalse((self.output/'EXTRACTION-RECEIPT.json').exists())
        self.assertTrue(self.archive.read_bytes().endswith(b'CHANGED AFTER PIN'))

    def test_actual_cli_unsupported_manifest_schema_is_refused(self):
        self.fixture(manifest_changes=lambda doc:doc.update(schema='unsupported/100'))
        self.assert_rejected(self.invoke())

    def test_actual_cli_literal_control_and_bidi_names_are_preserved_without_terminal_controls(self):
        names=('clipboard\x1b]52;c;Y2FuYXJ5\x07','forged\nPASS','bidi\u202eevil','csi\u009b31m')
        self.fixture(entries=[(hostile,'file',b'payload') for hostile in names])
        result=self.invoke();self.assertEqual(result.returncode,0,result.stderr)
        for hostile in names:self.assertEqual((self.output/'layer'/hostile).read_bytes(),b'payload')
        self.assertFalse(any(ord(char)<32 and char!='\n' or 127<=ord(char)<=159 or char=='\u202e'
                             for char in result.stdout+result.stderr))

    def test_actual_cli_control_filename_payload_error_is_escaped_and_preserved(self):
        name='negative-\x1b]52;c;Y2FuYXJ5\x07.bin'
        self.fixture(entries=[(name,'file',b'payload')],manifest_changes=lambda doc:doc['entries'][0].update(sha256='0'*64))
        result=self.invoke();self.assert_rejected(result,before_write=False)
        self.assertEqual((self.output/'layer'/name).read_bytes(),b'payload')
        self.assertNotIn('\x1b',result.stderr);self.assertNotIn('\x07',result.stderr)
        self.assertIn('\\u001b',result.stderr)

    def test_actual_cli_oserror_diagnostic_escapes_literal_source_filename(self):
        self.fixture();hostile=self.root/'missing\x1b]52;c;Y2FuYXJ5\x07.zip'
        result=self.invoke(archive=hostile);self.assert_rejected(result)
        self.assertNotIn('\x1b',result.stderr);self.assertNotIn('\x07',result.stderr)
        # OSError first uses Python repr (\\x1b); JSON then quotes that
        # already-inert representation. Preserve it without requiring a
        # different Unicode escape spelling.
        self.assertIn('x1b]52;',result.stderr)

    def test_actual_cli_unsupported_compression_has_bounded_safe_failure(self):
        self.fixture();raw=bytearray(self.archive.read_bytes())
        local=raw.index(b'PK\x03\x04');central=raw.index(b'PK\x01\x02')
        raw[local+8:local+10]=(99).to_bytes(2,'little')
        raw[central+10:central+12]=(99).to_bytes(2,'little')
        self.archive.write_bytes(raw)
        result=self.invoke();self.assert_rejected(result)
        self.assertNotIn('Traceback',result.stderr)

    def test_unexpected_output_file_is_preserved_and_blocks_pass(self):
        self.fixture();source=self.archive.read_bytes()
        spec=importlib.util.spec_from_file_location('independent_restore_unexpected',SCRIPT)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        original=module.write_new
        def injected(rootfd,path,*args,**kwargs):
            result=original(rootfd,path,*args,**kwargs)
            if path.endswith('/data/exact.bin'):
                fd=os.open('unexpected-temporary-file',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=rootfd)
                os.write(fd,b'PRESERVE AND INVESTIGATE');os.close(fd)
            return result
        module.write_new=injected
        with self.assertRaises(module.RestoreError) as failure:
            module.extract(self.archive,archive_bytes=len(source),archive_sha256=literal_sha(source),snapshot=self.snapshot,output=self.output)
        self.assertIn('file set',str(failure.exception))
        self.assertEqual((self.output/'unexpected-temporary-file').read_bytes(),b'PRESERVE AND INVESTIGATE')
        self.assertFalse((self.output/'EXTRACTION-RECEIPT.json').exists())
        self.assertEqual(self.archive.read_bytes(),source)

    def test_replaced_output_bytes_are_detected_by_post_extraction_readback(self):
        self.fixture();source=self.archive.read_bytes()
        spec=importlib.util.spec_from_file_location('independent_restore_replaced',SCRIPT)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        original=module.write_new
        def injected(rootfd,path,*args,**kwargs):
            result=original(rootfd,path,*args,**kwargs)
            if path.endswith('/data/exact.bin'):
                pieces=path.split('/')
                with module.descend(rootfd,pieces[:-1]) as parent:
                    fd=os.open(pieces[-1],os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW,dir_fd=parent)
                    os.write(fd,b'\x00MUTATED\r\n\xff');os.close(fd)
            return result
        module.write_new=injected
        with self.assertRaises(module.RestoreError):
            module.extract(self.archive,archive_bytes=len(source),archive_sha256=literal_sha(source),snapshot=self.snapshot,output=self.output)
        self.assertEqual((self.output/'layer/data/exact.bin').read_bytes(),b'\x00MUTATED\r\n\xff')
        self.assertFalse((self.output/'EXTRACTION-RECEIPT.json').exists())

    def test_actual_cli_hardlink_metadata_requires_equal_declared_regular_bytes(self):
        self.fixture(manifest_changes=lambda doc:doc.update(hardlink_groups=[{'group':'one','paths':['data/exact.bin','missing']}]))
        self.assert_rejected(self.invoke())

    def test_actual_cli_hardlink_group_materializes_independent_verified_files(self):
        self.fixture(entries=[('first','file',b'equal'),('second','file',b'equal')],
            manifest_changes=lambda doc:doc.update(hardlink_groups=[{'group':'one','paths':['first','second']}]))
        result=self.invoke();self.assertEqual(result.returncode,0,result.stderr)
        receipt=json.loads(result.stdout)
        first=self.output/'layer/first';second=self.output/'layer/second'
        self.assertEqual(first.read_bytes(),b'equal');self.assertEqual(second.read_bytes(),b'equal')
        self.assertNotEqual(first.stat().st_ino,second.stat().st_ino)
        self.assertEqual(first.stat().st_nlink,1);self.assertEqual(second.stat().st_nlink,1)
        self.assertEqual(receipt['hardlink_groups_preserved_as_separate_regular_files'],[{'group':'one','paths':['first','second']}])


if __name__=='__main__':unittest.main()
