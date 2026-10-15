"""PKG-PRES-RUN11 (journey 28 run 11 frame reviews): what the screens say, not what the product decides.

Items are added in the order of the brief; each class names its item. Temporary directories only.
"""
import shlex
import unittest

from plugin_tests import test_workbench_repository as repository_tests
from plugin_tests import test_workbench_states as states_tests

OBJECT, TENANT = repository_tests.OBJECT, repository_tests.TENANT


class Proposed(unittest.TestCase):
    """A store with a recorded intent that the repository has since changed, so propose-from-intent has a change."""
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description
    workspace = states_tests.StateSurfaceTests.workspace
    summary = states_tests.StateSurfaceTests.summary

    def propose(self, name='operation'):
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        return propose_from_intent(self.store.root, self.service.root, OBJECT, self.root / name)


class FilesWrittenTests(Proposed):
    """Item 1 (run11-1): the plan review after propose-from-intent lists the input files the action wrote."""

    def test_the_proposal_result_names_the_two_input_files(self):
        review = self.propose()
        output = str(self.root / 'operation')
        self.assertEqual(review['files_written'], [output + '.intent-desired.json', output + '.intent-context.json'])

    def test_the_plan_review_prints_the_row_with_both_paths_quoted(self):
        review = self.propose('operation one')
        text = self.summary(self.workspace(4, review))
        base = str(self.root / 'operation one')
        self.assertIn('Input files written: %s, %s' % (shlex.quote(base + '.intent-desired.json'),
                                                       shlex.quote(base + '.intent-context.json')), text)
