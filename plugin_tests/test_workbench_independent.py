"""Mutation sensitivity of the separate subprocess grader's literal oracle."""
import copy
import errno
import subprocess
import tempfile
from unittest.mock import patch
import importlib.util
from pathlib import Path
import unittest

_PATH = Path(__file__).resolve().parents[1] / 'scripts/qualify-workbench.py'
_SPEC = importlib.util.spec_from_file_location('workbench_independent_grader', _PATH)
grader = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(grader)


class IndependentWorkbenchOracleTests(unittest.TestCase):
    def test_all_declared_corruption_controls_and_good_permutation(self):
        controls = grader.negative_controls()
        self.assertEqual(len(controls), 9)
        self.assertTrue(all(controls.values()))

    def test_reordering_unordered_assignments_is_a_valid_alternative(self):
        expected = grader.expected_estate()
        actual = copy.deepcopy(expected)
        actual['objects'][grader.POLICY]['assignments'].reverse()
        grader.semantic_estate(expected, actual)

    def test_duplicate_assignment_cannot_be_hidden_by_set_comparison(self):
        expected = grader.expected_estate()
        actual = copy.deepcopy(expected)
        actual['objects'][grader.POLICY]['assignments'].append(copy.deepcopy(actual['objects'][grader.POLICY]['assignments'][0]))
        with self.assertRaises(AssertionError):
            grader.semantic_estate(expected, actual)

    def test_boolean_integer_comparison_is_type_sensitive(self):
        with self.assertRaises(AssertionError):
            grader.exact({'value': 1}, {'value': True})

    def test_null_and_missing_are_not_equivalent(self):
        expected = grader.expected_estate()
        actual = copy.deepcopy(expected)
        del actual['objects'][grader.POLICY]['settings']['settings'][0]['settingInstance']['settingInstanceTemplateReference']
        with self.assertRaises(AssertionError):
            grader.semantic_estate(expected, actual)

    def test_same_name_does_not_authorize_identity_coalescing(self):
        expected = grader.expected_estate()
        actual = copy.deepcopy(expected)
        del actual['objects'][grader.UNRELATED]
        with self.assertRaises(AssertionError):
            grader.semantic_estate(expected, actual)


class IndependentWorkbenchPtyExitTests(unittest.TestCase):
    def exercise(self, *, eio=False, timed_out=False):
        class Child:
            returncode = None
            killed = 0
            waits = []
            def poll(self): return self.returncode
            def kill(self): self.killed += 1
            def wait(self, timeout):
                self.waits.append(timeout)
                if timed_out and len(self.waits) == 1:
                    raise subprocess.TimeoutExpired(['fixture'], timeout)
                self.returncode = -9 if self.killed else 0
                return self.returncode
        child = Child()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = grader.Run(root / 'receipt', '/fixture/python')
            original_read = grader.os.read
            def read(fd, count):
                if fd != 7001: return original_read(fd, count)
                if eio: raise OSError(errno.EIO, 'PTY fixture end')
                return b''
            with patch.object(grader.pty, 'openpty', return_value=(7001, 7002)), \
                 patch.object(grader.fcntl, 'ioctl'), patch.object(grader.os, 'close'), \
                 patch.object(grader.os, 'read', side_effect=read), \
                 patch.object(grader.subprocess, 'Popen', return_value=child), \
                 patch.object(grader.select, 'select', return_value=([7001], [], [])), \
                 patch.object(grader.time, 'monotonic', side_effect=[100, 101, 102]):
                if timed_out:
                    with self.assertRaisesRegex(AssertionError, 'within 30 seconds'):
                        run.terminal_pty(root / 'store', root / 'service', [])
                else:
                    self.assertEqual(run.terminal_pty(root / 'store', root / 'service', []), '')
            self.assertEqual(child.waits[0], 28.0)
            self.assertEqual(child.killed, 2 if timed_out else 0)
            self.assertEqual(child.returncode, -9 if timed_out else 0)
            self.assertEqual(run.results['commands'][-1]['returncode'], child.returncode)
            self.assertGreaterEqual(run.results['commands'][-1]['seconds'], 0)
            if timed_out: self.assertEqual(child.waits[1], 2)

    def test_eof_before_exit_visibility_waits_within_original_deadline(self):
        self.exercise()

    def test_eio_before_exit_visibility_waits_within_original_deadline(self):
        self.exercise(eio=True)

    def test_actual_deadline_exhaustion_kills_and_reaps_with_bounded_wait(self):
        self.exercise(timed_out=True)

    def test_external_checker_is_bound_separately_and_cannot_change_unnoticed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); product = root / 'product'
            for relative in ('scripts/intune-iac.py', 'examples/supported/input/export.json'):
                path = product / relative; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixed product fixture')
            checker = root / 'external-checker.py'; checker.write_text('original checker')
            with patch.object(grader, 'PROJECT', product), patch.object(grader, '__file__', str(checker)):
                run = grader.Run(root / 'receipt', '/fixture/python')
                self.assertEqual(run.results['checker']['path'], str(checker))
                self.assertEqual(set(run.results['source_sha256']),
                                 {'scripts/intune-iac.py', 'examples/supported/input/export.json'})
                run.source_end()
                checker.write_text('changed checker')
                with self.assertRaisesRegex(AssertionError, 'checker changed'):
                    run.source_end()
