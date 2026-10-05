"""Independent release-result controls, including unittest's non-failing outcomes."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class VerifierContractTests(unittest.TestCase):
    def run_case(self, body):
        spec = importlib.util.spec_from_file_location('release_verifier', ROOT / 'scripts/verify-plugin.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        namespace = {'unittest': unittest}
        exec(body, namespace)
        suite = unittest.TestSuite() if 'Probe' not in namespace else unittest.defaultTestLoader.loadTestsFromTestCase(namespace['Probe'])
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'result'
            with patch.object(sys, 'argv', ['verify-plugin.py', '--output', str(output)]), \
                 patch.object(unittest.defaultTestLoader, 'discover', return_value=suite), \
                 contextlib.redirect_stdout(io.StringIO()):
                code = module.main()
            return code, json.loads((output / 'result.json').read_text())

    def test_real_success_control(self):
        code, result = self.run_case('class Probe(unittest.TestCase):\n def test_ok(self): self.assertEqual(2+2,4)')
        self.assertEqual(code, 0)
        self.assertEqual(result['passed'], 1)
        self.assertIs(result['success'], True)

    def test_empty_suite_cannot_pass(self):
        code, result = self.run_case('')
        self.assertNotEqual(code, 0)
        self.assertIs(result['success'], False)

    def test_skipped_suite_cannot_pass(self):
        code, result = self.run_case('class Probe(unittest.TestCase):\n @unittest.skip("missing host")\n def test_skipped(self): pass')
        self.assertNotEqual(code, 0)
        self.assertIs(result['success'], False)

    def test_expected_failure_cannot_pass(self):
        code, result = self.run_case('class Probe(unittest.TestCase):\n @unittest.expectedFailure\n def test_expected(self): self.fail("unimplemented")')
        self.assertNotEqual(code, 0)
        self.assertIs(result['success'], False)

    def test_multiple_failing_subtests_do_not_make_negative_pass_count(self):
        code, result = self.run_case('class Probe(unittest.TestCase):\n def test_subs(self):\n  for value in (1,2):\n   with self.subTest(value=value): self.assertEqual(value,0)')
        self.assertNotEqual(code, 0)
        self.assertEqual(result['tests'], 1)
        self.assertEqual(result['passed'], 0)
        self.assertEqual(result['failures'], 2)

    def test_unexpected_success_is_not_counted_as_pass(self):
        code, result = self.run_case('class Probe(unittest.TestCase):\n @unittest.expectedFailure\n def test_unexpected(self): pass')
        self.assertNotEqual(code, 0)
        self.assertEqual(result['passed'], 0)

    def test_skipped_subtest_cannot_pass(self):
        code, result = self.run_case('class Probe(unittest.TestCase):\n def test_subs(self):\n  with self.subTest(value=1): self.skipTest("missing adapter")\n  with self.subTest(value=2): self.assertTrue(True)')
        self.assertNotEqual(code, 0)
        self.assertEqual(result['passed'], 0)
