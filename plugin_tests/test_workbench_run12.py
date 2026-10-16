"""PKG-PRES-RUN12 (journey 28 run 12 frame reviews): what the screens say, not what the product decides.

Items are added in the order of the brief; each class names its item. Temporary directories only.
"""
import unittest

from plugin_tests import test_workbench_states as states_tests
from plugin_tests.test_workbench_screens import delivery_value


class OneNextOnDeliveryTests(unittest.TestCase):
    """Item 1 (frames 20, 39): when the hazard band carries the Next, the Delivery body keeps its explanation and
    prints no second `Next:` label (as the lifecycle line already does)."""
    workspace = states_tests.StateSurfaceTests.workspace
    BAND = states_tests.RunEightWorkspaceTests.BAND
    STEP = 'Record the deployment (a lists it). In the workspace:\n  deployment-record /w/op INTENT'

    def shown(self, signals):
        value = dict(delivery_value(), next_action=self.STEP)
        workspace = self.workspace(5, value)
        workspace.facts = dict(workspace.facts, signals=signals)
        return ' '.join(' '.join(workspace._summary_lines(118)).split())

    def test_with_a_band_next_the_body_has_no_next_label_but_keeps_its_explanation(self):
        text = self.shown([self.BAND])
        self.assertNotIn('Next:', text)
        self.assertIn('Record the deployment (a lists it). In the workspace: deployment-record /w/op INTENT', text)

    def test_without_a_band_the_body_keeps_its_next_label(self):
        self.assertIn('Next: Record the deployment (a lists it).', self.shown([]))


class StripSentenceTests(unittest.TestCase):
    """Item 2 (frame 67): the body sentence describes what the strip shows. The strip names no operation id when its
    operation is the newest (it prints `OP prepared`), so the sentence says that OP stands for that operation; the
    strip itself and its width rules (P-PRES-02) are unchanged."""
    from plugin_tests.test_workbench_run10 import StripOperationTests as _base
    refusal = _base.refusal
    surface = _base.surface
    STRIP, ABOUT = _base.STRIP, _base.ABOUT

    def test_the_sentence_says_what_the_strip_prints_not_an_id_it_does_not_show(self):
        from intune_iac.workbench_screens import strip_choice
        workspace = self.refusal()
        strip = strip_choice('11111111' * 4, 'p' * 32, {'operation': 'prepared'}, 140)[0]
        self.assertTrue(strip.endswith('OP prepared'), strip)
        text = ' '.join(' '.join(workspace._strip_note(118)).split())
        self.assertEqual(text, "The strip's OP prepared is operation a23983bd, the newest for this policy, not operation "
                               "f728f275, the one this screen is about.")


class WhereToTypeTests(unittest.TestCase):
    """Item 3 (frames 18, 31, 53, 63, 64; also 02 and 48): a printed command says where it is typed. The plan review's
    execute gets the framing frame 20 uses, with the complete shell form; DIGEST stays a placeholder, never prefilled."""
    OPERATION = '/w/op'

    def review(self, **kw):
        import time
        value = {'operation_id': 'f' * 32, 'operation_root': self.OPERATION, 'object_id': 'o' * 8, 'status': 'prepared',
                 'approval_digest': 'd' * 64, 'expires_at': time.time() + 200}
        return dict(value, **kw)

    def rows(self, value, width=118):
        from intune_iac.workbench_screens import lifecycle_lines
        return lifecycle_lines(4, width, value)

    def test_the_plan_review_frames_both_forms_and_keeps_the_placeholder(self):
        for width in (80, 118):
            text = '\n'.join(row.strip() for row in self.rows(self.review(), width))
            self.assertIn('In the workspace:\nexecute /w/op DIGEST\nFrom a shell:\nintune-iac workbench execute --operation '
                          '/w/op --approve-digest DIGEST', text, width)
            self.assertNotIn('Command:', text)
            self.assertNotIn('d' * 64, text)

    def test_a_no_change_plan_and_a_review_without_a_directory_say_it_too(self):
        no_change = ' '.join(' '.join(self.rows(self.review(changes=[], no_configuration_change=True))).split())
        self.assertIn('In the workspace: execute /w/op DIGEST From a shell: intune-iac workbench execute --operation /w/op '
                      '--approve-digest DIGEST', no_change)
        value = self.review()
        del value['operation_root']
        bare = ' '.join(' '.join(self.rows(value)).split())
        self.assertIn('In the workspace: execute OPERATION_DIR DIGEST From a shell: intune-iac workbench execute '
                      '--operation OPERATION_DIR --approve-digest DIGEST', bare)

    def test_a_path_with_spaces_is_quoted_in_both_forms(self):
        text = ' '.join(' '.join(self.rows(self.review(operation_root='/w/my op'))).split())
        self.assertIn("execute '/w/my op' DIGEST", text)
        self.assertIn("--operation '/w/my op' --approve-digest DIGEST", text)

    def test_the_queue_amend_command_says_it_is_typed_in_the_workspace(self):
        from intune_iac.workbench_screens import review_lines
        form = {'status': 'review_form_written', 'path': '/w/queue review.json', 'finding': 'incomplete', 'object_id': 'o' * 8}
        text = '\n'.join(row.strip() for row in review_lines(form, 118))
        self.assertNotIn('Command:', text)
        self.assertIn("In the workspace:\nqueue-amend '/w/queue review.json' none", text)

    def test_the_adopt_command_says_it_is_typed_in_the_workspace(self):
        from intune_iac.workbench_screens import adoption_lines
        value = {'status': 'ready_local_model_handoff', 'binding': {'session': '/w/session.json', 'object_ids': ['o' * 8]}}
        text = '\n'.join(row.strip() for row in adoption_lines(value, 118))
        self.assertIn("In the workspace:\nadopt '/w/session.json' NEW_HANDOFF_DIR", text)


class ChangedFileBridgeTests(unittest.TestCase):
    """Item 4 (frames 75, 77): REPOSITORY CHANGED sits beside NO CONFIGURATION CHANGE; one clause says the listed files
    do not alter this policy's body at the intent pointer (the verdict compares that body, workbench_repository.intent_freshness)."""
    BRIDGE = ("The listed files differ from the recorded ones, but they do not alter this policy's body at the intent "
              "pointer.")

    def rows(self, field_changes, sources=None, pointer_present=True):
        from intune_iac.workbench_screens import repository_lines
        status = {'schema_version': 'workbench-repository-status/1', 'scope': {'stack': 's', 'component': 'c'},
                  'freshness': {'status': 'stale', 'pointer_present': pointer_present, 'field_changes': field_changes,
                                'sources': sources or {'changed': ['stacks/dev.yaml'], 'added': ['stacks/new.yaml']}}}
        return repository_lines(status, 118)

    def text(self, *args, **kw):
        return ' '.join(' '.join(self.rows(*args, **kw)).split())

    def test_a_no_change_verdict_beside_listed_files_carries_the_bridge_once(self):
        text = self.text({'status': 'no_change', 'changes': []})
        self.assertEqual(text.count(self.BRIDGE), 1, text)
        self.assertLess(text.index('RECORDED INTENT AGAINST THE REPOSITORY NOW'), text.index(self.BRIDGE))
        self.assertLess(text.index(self.BRIDGE), text.index('NO CONFIGURATION CHANGE'))

    def test_a_changed_body_or_no_listed_file_says_no_such_thing(self):
        changed = {'status': 'changed', 'changes': [{'field': 'description', 'kind': 'changed', 'before': 'a', 'after': 'b'}]}
        self.assertNotIn(self.BRIDGE, self.text(changed))
        self.assertNotIn(self.BRIDGE, self.text({'status': 'no_change', 'changes': []},
                                                sources={'changed': [], 'added': [], 'removed': []}))

    def test_one_listed_file_reads_in_the_singular(self):
        text = self.text({'status': 'no_change', 'changes': []}, sources={'changed': ['stacks/dev.yaml']})
        self.assertIn("The listed file differs from the recorded one, but it does not alter this policy's body at the intent "
                      "pointer.", text)
