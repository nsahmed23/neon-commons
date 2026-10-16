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
