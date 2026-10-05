import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class CompletionCLITests(unittest.TestCase):
    def cli(self,*argv):
        return subprocess.run([sys.executable,str(ROOT/'scripts/intune-iac.py'),*map(str,argv)],cwd='/tmp',capture_output=True,text=True,timeout=30)

    def test_synthetic_generation_and_inspection_are_real_commands(self):
        with tempfile.TemporaryDirectory() as td:
            destination=Path(td)/'estate'
            answer=self.cli('synthetic','generate','--output',destination,'--seed','7','--policies','2')
            self.assertEqual(answer.returncode,0,answer.stderr)
            self.assertTrue((destination/'estate.json').is_file())
            result=self.cli('synthetic','inspect','--input',destination/'estate.json')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(json.loads(result.stdout)['success'])

    def test_journey_and_guided_cannot_be_combined(self):
        with tempfile.TemporaryDirectory() as td:
            answer=self.cli('wizard','--journey','--guided','--session',Path(td)/'s.json')
            self.assertEqual(answer.returncode,3)
            self.assertIn('conflicting_wizard_modes',answer.stderr)
            self.assertFalse((Path(td)/'s.json').exists())

    def test_nonpassing_qualification_status_has_nonzero_exit(self):
        from intune_iac.cli import exit_code
        for status in ('FAIL','INCONCLUSIVE','INVALID_TASK','INFRA_ERROR','BLOCKED','NOT_RUN'):
            self.assertNotEqual(exit_code({'status':status}),0,status)
        self.assertEqual(exit_code({'status':'PASS'}),0)
        self.assertNotEqual(exit_code({'success':False}),0)

    def test_new_commands_visible_in_help(self):
        self.assertIn('--journey',self.cli('wizard','--help').stdout)
        self.assertIn('native',self.cli('repository','--help').stdout)
