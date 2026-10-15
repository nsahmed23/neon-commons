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


class RepositoryVerdictTests(Proposed):
    """Item 3 (run11-3): the repository's no-change verdict names the two sides the code compares.

    workbench_repository.intent_freshness compares the recorded intent's desired body with the repository's value
    now at the intent pointer (field_changes(data['desired'], desired_now)). No observation takes part.
    """

    def status(self):
        from intune_iac.workbench_repository import intent_freshness
        intent = self.import_intent()
        (self.repo / 'components/terraform/intune-reference/override.tf').write_text('output "x" {\n  value = 1\n}\n')
        fresh = intent_freshness(intent['data'])
        self.assertEqual((fresh['status'], fresh['field_changes']['status']), ('stale', 'no_change'))
        return {'freshness': fresh, 'scope': intent['data']['scope'], 'repository_intent_id': intent['artifact_id']}

    def rows(self, width=118):
        from intune_iac.workbench_screens import repository_lines
        return repository_lines(self.status(), width)

    def test_the_heading_and_the_verdict_name_the_recorded_intent_and_the_repository(self):
        rows = self.rows()
        text = ' '.join(' '.join(rows).split())
        self.assertIn('RECORDED INTENT AGAINST THE REPOSITORY NOW', rows)
        self.assertIn("NO CONFIGURATION CHANGE The recorded intent's desired body equals the repository's body now at the "
                      "intent pointer, under the execution plan's equality.", text)
        self.assertIn('The observation is not part of this comparison.', text)

    def test_a_repository_verdict_never_speaks_of_the_observed_body_or_sits_under_the_old_heading(self):
        rows = self.rows()
        self.assertNotIn('DESIRED POLICY AT THE INTENT POINTER', rows)
        self.assertNotIn('observed body', ' '.join(rows))

    def test_the_plan_review_keeps_its_desired_against_observed_verdict(self):
        from intune_iac.workbench_screens import change_lines
        text = ' '.join(change_lines({'status': 'no_change', 'changes': []}, 118))
        self.assertIn('The desired body equals the observed body under the execution plan', text)
