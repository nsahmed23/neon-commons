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


class ShellFormTests(unittest.TestCase):
    """Item 2 (run11-2): every shell form the workbench prints is complete, starting with the program name."""

    MODULES = ('workbench', 'workbench_screens', 'workbench_tui', 'workbench_delivery', 'workbench_diagnostics',
               'companion_page')
    # "workbench COMMAND --flag": the shape of a shell form; the program name must stand in front of it.
    BARE = r"(?<!intune-iac )(?<![\w./-])workbench (?:[a-z][a-z-]+) --"

    def source(self, module):
        from pathlib import Path
        return (Path(__file__).resolve().parents[1] / 'intune_iac' / (module + '.py')).read_text(encoding='utf-8')

    def test_no_printed_shell_form_lacks_the_program_name(self):
        import re
        for module in self.MODULES:
            found = [match.group(0) for match in re.finditer(self.BARE, self.source(module))]
            self.assertEqual(found, [], module)

    def test_the_deployment_record_shell_form_starts_with_the_program(self):
        from plugin_tests.test_workbench_run9 import next_step
        step = next_step(record={'status': 'available', 'intent_id': 'i' * 64}, operation='/w/op', store='/w/store')
        self.assertIn('From a shell:\n  intune-iac workbench deployment-record --root /w/store --operation /w/op --intent '
                      + 'i' * 64, step)

    def test_the_companion_shell_forms_start_with_the_program(self):
        from intune_iac.companion_page import COMPANION_SERVE, COMPANION_WRITE
        self.assertTrue(COMPANION_WRITE.startswith('intune-iac workbench companion '), COMPANION_WRITE)
        self.assertTrue(COMPANION_SERVE.startswith('intune-iac workbench companion '), COMPANION_SERVE)
