"""Exact raw Git identity and independently selected source negative controls."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/verify-source-linkage.py'
SPEC = importlib.util.spec_from_file_location('source_linkage_release', SCRIPT)
subject = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(subject)
GIT = Path('/usr/bin/git')


class SourceLinkageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='source-linkage-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.repo = self.root/'repo'; self.repo.mkdir()
        self.env = {'PATH':'/usr/bin:/bin', 'HOME':str(self.root), 'GIT_CONFIG_NOSYSTEM':'1',
                    'GIT_CONFIG_GLOBAL':'/dev/null', 'GIT_CONFIG_SYSTEM':'/dev/null', 'LANG':'C'}
        self.git('init','--quiet'); self.git('config','user.name','Local source fixture')
        self.git('config','user.email','fixture@example.invalid')
        (self.repo/'dir').mkdir()
        (self.repo/'dir/payload.bin').write_bytes(b'\x00\xff\r\nexact-binary\n')
        (self.repo/'README.md').write_bytes(b'Reviewed source\r\n')
        (self.repo/'release-source-files.txt').write_text('README.md\ndir/payload.bin\nrelease-source-files.txt\n')
        self.revision = self.commit()
        self.source = self.root/'source'; self.source.mkdir()
        for name in ('README.md','dir/payload.bin','release-source-files.txt'):
            target = self.source/name; target.parent.mkdir(exist_ok=True)
            target.write_bytes((self.repo/name).read_bytes())
        self.pin = hashlib.sha256(GIT.read_bytes()).hexdigest()

    def git(self,*args):
        return subprocess.check_output([str(GIT),*args],cwd=self.repo,env=self.env,stderr=subprocess.PIPE).strip().decode()

    def commit(self):
        self.git('add','--all'); self.git('commit','--quiet','-m','fixture')
        return self.git('rev-parse','HEAD')

    def verify(self,**kwargs):
        return subject.verify(self.repo,self.source,kwargs.pop('revision',self.revision),
            git_executable=GIT,git_sha256=kwargs.pop('pin',self.pin),**kwargs)

    def test_all_inventory_bytes_link_to_raw_commit_trees_and_blobs(self):
        (self.source/'unselected.txt').write_text('not silently certified')
        result = self.verify()
        self.assertEqual(result['status'],'PASS'); self.assertEqual(len(result['files']),3)
        rows = {r['path']:r for r in result['files']}
        self.assertEqual(rows['dir/payload.bin']['bytes'],len(b'\x00\xff\r\nexact-binary\n'))
        self.assertEqual(rows['README.md']['blob_id'],self.git('rev-parse',self.revision+':README.md'))
        self.assertEqual({r['kind'] for r in result['objects']},{'commit','tree','blob'})
        self.assertFalse(result['publisher_authenticated']); self.assertFalse(result['repository_modified'])

    def test_changed_selected_source_fails(self):
        (self.source/'README.md').write_text('changed')
        with self.assertRaisesRegex(ValueError,'source bytes differ'): self.verify()

    def test_uncommitted_inventory_addition_fails(self):
        p = self.source/'release-source-files.txt'; p.write_text(p.read_text()+'extra.txt\n')
        (self.source/'extra.txt').write_text('new')
        with self.assertRaisesRegex(ValueError,'inventory differs'): self.verify()

    def test_selected_symbolic_and_hard_links_fail_without_reading_outside(self):
        path = self.source/'README.md'; path.unlink()
        path.symlink_to(self.repo/'README.md')
        with self.assertRaises(OSError): self.verify()
        path.unlink(); os.link(self.repo/'README.md',path)
        with self.assertRaisesRegex(ValueError,'one link'): self.verify()

    def test_git_selected_symlink_is_not_a_regular_source(self):
        path = self.repo/'README.md'; path.unlink(); path.symlink_to('dir/payload.bin')
        self.revision = self.commit()
        with self.assertRaisesRegex(ValueError,'link, submodule'): self.verify()

    def test_git_config_include_is_rejected_before_command(self):
        with (self.repo/'.git/config').open('a') as stream: stream.write('\n[include]\n path = /not/read\n')
        with self.assertRaisesRegex(ValueError,'configuration indirection'): self.verify()

    def test_git_config_symlink_and_alternates_fail(self):
        config = self.repo/'.git/config'; saved = self.root/'saved-config'; config.rename(saved); config.symlink_to(saved)
        with self.assertRaises(OSError): self.verify()
        config.unlink(); saved.rename(config)
        (self.repo/'.git/objects/info/alternates').write_text('/not/read\n')
        with self.assertRaisesRegex(ValueError,'indirection'): self.verify()

    def test_wrong_tool_or_commit_pin_fails(self):
        with self.assertRaisesRegex(ValueError,'executable pin mismatch'): self.verify(pin='0'*64)
        with self.assertRaises(ValueError): self.verify(revision='HEAD')
        blob = self.git('rev-parse',self.revision+':README.md')
        with self.assertRaises(ValueError): self.verify(revision=blob)

    def test_replace_refs_cannot_substitute_another_commit(self):
        original = self.revision
        (self.repo/'README.md').write_text('replacement')
        other = self.commit(); self.git('replace',original,other)
        self.assertEqual(self.verify()['source_commit'],original)
        self.assertEqual(self.verify()['files'][0]['sha256'],hashlib.sha256(b'Reviewed source\r\n').hexdigest())

    def test_committed_traversal_inventory_is_rejected(self):
        path = self.repo/'release-source-files.txt'; path.write_text('release-source-files.txt\n../outside\n')
        self.revision = self.commit(); (self.source/path.name).write_bytes(path.read_bytes())
        with self.assertRaisesRegex(ValueError,'Unsafe source inventory'): self.verify()

    def test_actual_cli_new_receipt_then_no_overwrite(self):
        output = self.root/'result.json'
        argv = [sys.executable,'-B',str(SCRIPT),'--repository',str(self.repo),'--source',str(self.source),
            '--commit',self.revision,'--git-executable',str(GIT),'--git-sha256',self.pin,'--output',str(output)]
        first = subprocess.run(argv,capture_output=True)
        self.assertEqual(first.returncode,0,first.stderr)
        before = output.read_bytes(); self.assertEqual(json.loads(before)['status'],'PASS')
        second = subprocess.run(argv,capture_output=True)
        self.assertNotEqual(second.returncode,0); self.assertEqual(output.read_bytes(),before)


if __name__ == '__main__': unittest.main()
