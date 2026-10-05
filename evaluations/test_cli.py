import unittest,subprocess,tempfile,sys,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
class Cli(unittest.TestCase):
 def run_cli(self,variant,dest):return subprocess.run([sys.executable,str(R/'tools/build-reference.py'),'--input',str(R/'examples'/variant/'input/export.json'),'--context',str(R/'examples/context.json'),'--output',str(dest)],capture_output=True,text=True)
 def test_supported_and_rerun(self):
  with tempfile.TemporaryDirectory() as d:
   x=self.run_cli('supported',Path(d)/'out');self.assertEqual(x.returncode,0,x.stderr);self.assertFalse(json.loads(x.stdout)['execution_authorized']);self.assertEqual(json.loads(self.run_cli('supported',Path(d)/'out').stdout)['result'],'unchanged')
 def test_partial(self):
  with tempfile.TemporaryDirectory() as d:
   x=self.run_cli('partial',Path(d)/'out');self.assertEqual(x.returncode,2,x.stderr);self.assertTrue((Path(d)/'out/BLOCKED.json').is_file());self.assertEqual(list((Path(d)/'out').rglob('*.tf')),[])
 def test_noninteractive_missing_arguments(self):
  x=subprocess.run([sys.executable,str(R/'tools/build-reference.py')],input='',capture_output=True,text=True);self.assertNotEqual(x.returncode,0)
