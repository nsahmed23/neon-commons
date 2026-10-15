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


class RestoreReviewTests(Proposed):
    """Item 4 (run11-4): a restore plan says it restores operation N and that AFTER is that operation's observation
    from before its change, not the recorded intent (maintenance.propose_restore writes before_estate as the desired body)."""

    def restored(self):
        from intune_iac import maintenance
        from intune_iac.workbench import _restore_proposal
        review = self.propose()
        operation = self.root / 'operation'
        maintenance.execute(operation, approve_digest=review['approval_digest'])
        self.store.collect(self.service)
        return review, _restore_proposal(operation, self.root / 'restore')

    def test_the_restore_result_names_the_operation_it_restores(self):
        review, restore = self.restored()
        self.assertEqual(restore['restore_of'], review['operation_id'])
        self.assertNotEqual(restore['operation_id'], review['operation_id'])

    def test_the_change_review_says_it_is_a_restore_and_where_after_comes_from(self):
        review, restore = self.restored()
        text = self.summary(self.workspace(4, restore))
        short = review['operation_id'][:8]
        self.assertIn("Restore of operation %s: AFTER is that operation's observation from before its change, "
                      "not the recorded intent." % short, text)
        self.assertLess(text.index('Restore of operation'), text.index('[PLAN REVIEW]'))

    def test_a_plan_that_is_not_a_restore_says_nothing_of_one(self):
        self.assertNotIn('Restore of operation', self.summary(self.workspace(4, self.propose())))


def balanced(sentence):
    """True when every bracket closes in order and none is left open."""
    stack = []
    for char in sentence:
        if char == '(':
            stack.append(char)
        elif char == ')':
            if not stack:
                return False
            stack.pop()
    return not stack


class ReconcileNextTests(unittest.TestCase):
    """Item 5 (gemini-run11-2, frame 54): the Next that names reconcile reads as one balanced sentence."""

    UNKNOWN = {'operation_id': 'a' * 32, 'status': 'outcome_unknown'}

    def rendered(self, width):
        from intune_iac.workbench_screens import lifecycle_lines
        return ' '.join(' '.join(lifecycle_lines(5, width, self.UNKNOWN)).split())

    def test_the_rendered_next_has_balanced_parentheses_at_every_width(self):
        for width in (118, 80, 60):
            text = self.rendered(width)
            self.assertTrue(balanced(text), text)
            self.assertIn('Next: Reconcile it (a: actions); it never replays the change. v shows every delivery stage.', text)

    def test_the_lifecycle_next_for_a_prepared_unknown_operation_reads_the_same(self):
        from intune_iac.workbench_screens import lifecycle_next
        for tab, value in ((5, self.UNKNOWN), (4, self.UNKNOWN)):
            step = lifecycle_next(tab, value, 0)
            self.assertEqual(step, 'Reconcile it (a: actions); it never replays the change. v shows every delivery stage', tab)
            self.assertTrue(balanced(step), step)

    def test_the_band_and_the_lifecycle_name_reconcile_in_the_same_words(self):
        from intune_iac.workbench_screens import hazard_rows
        band = ' '.join(hazard_rows({'operation': 'outcome_unknown'}, [], 140))
        self.assertIn('Next: Reconcile it (a: actions); it never replays the change', band)
        self.assertTrue(balanced(band), band)


class OneNextTests(unittest.TestCase):
    """Item 6 (frames 19, 38, 54): when the hazard band carries a Next, the lifecycle line adds none."""
    workspace = states_tests.StateSurfaceTests.workspace
    BAND = states_tests.RunEightWorkspaceTests.BAND
    RESULT = {'result': {'operation_id': 'a' * 32, 'status': 'succeeded_verified'}}
    UNKNOWN = {'operation_id': 'a' * 32, 'status': 'outcome_unknown'}
    RECONCILED = {'result': {'operation_id': 'a' * 32, 'status': 'reconciled', 'journal_status': 'reconciled'}}

    def banded(self, tab, value, signals=None):
        workspace = self.workspace(tab, value)
        workspace.facts = dict(workspace.facts, signals=[self.BAND] if signals is None else signals)
        return ' '.join(' '.join(workspace._summary_lines(118)).split())

    def test_the_band_carries_a_next_so_the_line_has_none(self):
        from intune_iac.workbench_screens import hazard_rows
        self.assertIn('Next:', ' '.join(hazard_rows({}, [self.BAND], 118)))
        for value in (self.RESULT, self.RECONCILED, self.UNKNOWN):
            text = self.banded(5, value)
            self.assertIn('Lifecycle: 9 Repository > 5 Plan > 6 Execution (here) > Delivery (v opens it).', text)
            self.assertNotIn('Next:', text, value)
            self.assertNotIn('shows every delivery stage', text, value)

    def test_without_a_band_the_line_keeps_its_next(self):
        self.assertIn('Next: v shows every delivery stage, including the deployment record.', self.banded(5, self.RESULT, []))
        self.assertIn('Next: Reconcile it (a: actions); it never replays the change.', self.banded(5, self.UNKNOWN, []))

    def test_a_command_the_band_does_not_carry_stays_on_the_plan_review(self):
        prepared = {'operation_id': 'a' * 32, 'object_id': OBJECT, 'status': 'prepared', 'expires_at': 4102444800,
                    'operation_root': '/w/op'}
        text = self.banded(4, prepared)
        self.assertIn("execute /w/op DIGEST", text)
