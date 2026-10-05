"""Mutation sensitivity of the separate subprocess grader's literal oracle."""
import copy
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
