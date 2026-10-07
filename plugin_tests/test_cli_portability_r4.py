"""No-fcntl parser smoke tests; these do not qualify a native Windows host."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PortableParserTests(unittest.TestCase):
    def test_help_does_not_import_unavailable_native_execution_dependencies(self):
        probe = '''import importlib.abc,runpy,sys
class DenyFcntl(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname == 'fcntl': raise ModuleNotFoundError('fcntl deliberately unavailable in parser probe')
sys.meta_path.insert(0,DenyFcntl())
sys.argv=[sys.argv[1],*sys.argv[2:]]
runpy.run_path(sys.argv[0],run_name='__main__')
'''
        for args in (['--help'], ['workbench', '--help'], ['worker', '--help'], ['service', '--help'], ['artifact', '--help']):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, '-B', '-c', probe, str(ROOT / 'scripts/intune-iac.py'), *args],
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(b'usage:', result.stdout)


if __name__ == '__main__': unittest.main()
