"""Fixed qualification tool inputs; no downloads, daemon operations or repins."""
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

from scripts import qualification_tools as q
PROJECT=Path(__file__).resolve().parents[1]

class QualificationToolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='iw-tool-inputs-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.original=q.reference('relay_v3');self.copy=self.root/'relay-v3'
        shutil.copyfile(self.original,self.copy);self.copy.chmod(0o500)
    def test_relocated_fixed_bytes_accepted_without_repins(self):
        self.assertEqual(q.reference('relay_v3',{'INTUNE_QUALIFICATION_RELAY_V3':str(self.copy)}),self.copy)
        self.assertEqual(hashlib.sha256(self.copy.read_bytes()).hexdigest(),'4255592e3b477d9c7fba06a59536d07effaa2a54e9e848f4908fecae672a25a0')
    def test_same_size_changed_bytes_rejected_despite_caller_digest(self):
        raw=self.copy.read_bytes();self.copy.chmod(0o600);self.copy.write_bytes(raw[:-1]+bytes([raw[-1]^1]));self.copy.chmod(0o500)
        with self.assertRaises(ValueError):q.reference('relay_v3',{'INTUNE_QUALIFICATION_RELAY_V3':str(self.copy),'INTUNE_QUALIFICATION_RELAY_V3_SHA256':hashlib.sha256(self.copy.read_bytes()).hexdigest()})
    def test_leaf_and_parent_symlinks_refused(self):
        leaf=self.root/'alias';leaf.symlink_to(self.copy)
        with self.assertRaises(OSError):q.reference('relay_v3',{'INTUNE_QUALIFICATION_RELAY_V3':str(leaf)})
        parent=self.root/'parent';parent.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(OSError):q.reference('relay_v3',{'INTUNE_QUALIFICATION_RELAY_V3':str(parent/self.copy.name)})
    def test_hardlinks_and_writable_or_nonexecutable_files_refused(self):
        link=self.root/'hard';os.link(self.copy,link)
        with self.assertRaises(ValueError):q.reference('relay_v3',{'INTUNE_QUALIFICATION_RELAY_V3':str(link)})
        link.unlink()
        for mode in (0o600,0o777):
            self.copy.chmod(mode)
            with self.assertRaises(ValueError):q.reference('relay_v3',{'INTUNE_QUALIFICATION_RELAY_V3':str(self.copy)})
    def test_missing_explicit_path_never_falls_back_to_legacy(self):
        with self.assertRaises(OSError):q.reference('relay_v3',{'INTUNE_QUALIFICATION_RELAY_V3':str(self.root/'missing')})
    def test_unknown_role_and_relative_empty_control_paths_refused(self):
        with self.assertRaises(ValueError):q.reference('provider')
        for value in ('','relative','/tmp/../tool','/tmp/a\nsecret'):
            with self.assertRaises(ValueError):q.reference('relay_v3',{'INTUNE_QUALIFICATION_RELAY_V3':value})
    def test_changed_open_input_fails_closure(self):
        with self.assertRaises(ValueError):
            with q.opened(self.copy,executable=True):
                self.copy.chmod(0o600);self.copy.write_bytes(b'changed')
    def invoke(self,output,**paths):
        argv=[sys.executable,'-B',str(PROJECT/'scripts/prepare-qualification-tools.py'),'verify','--output',str(output)]
        for role in q.PINNED:argv+=['--'+role.replace('_','-'),str(paths.get(role,q.reference(role)))]
        return subprocess.run(argv,capture_output=True,text=True,timeout=15)
    def test_actual_cli_emits_verified_path_only_input_map_without_execution(self):
        out=self.root/'receipt';result=self.invoke(out,relay_v3=self.copy);self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout);env=json.loads((out/'environment.json').read_text())
        self.assertEqual(set(env),{x['environment']for x in q.PINNED.values()});self.assertEqual(env['INTUNE_QUALIFICATION_RELAY_V3'],str(self.copy))
        self.assertFalse(report['binary_execution']);self.assertFalse(report['network_attempted']);self.assertFalse(report['ci_qualified'])
        self.assertEqual(report['tools']['tofu']['version'],'1.13.1');self.assertEqual(report['tools']['docker']['version'],'28.4.0')
    def test_actual_cli_wrong_input_before_output_and_existing_output_preserved(self):
        out=self.root/'new';bad=self.root/'wrong';bad.write_bytes(b'wrong');bad.chmod(0o500)
        result=self.invoke(out,relay_v3=bad);self.assertEqual(result.returncode,2);self.assertFalse(out.exists())
        out.mkdir();(out/'keep').write_bytes(b'KEEP');result=self.invoke(out);self.assertEqual(result.returncode,2);self.assertEqual((out/'keep').read_bytes(),b'KEEP')

if __name__=='__main__':unittest.main()
