"""PKG-PRES-RUN16 (frame reviews of journey 28 run 16 and journey 29 run 11): what the screens say.

Each class names its item of the brief. Temporary directories only.
"""
import unittest


class ClosedPlanNextGivesItsReasonInlineTests(unittest.TestCase):
    """Item 1 (run16-N1): the Next sits above Expiry and Approval window, so it never points at them by position."""

    CLOSES = 1791980606

    def next(self, newest_open=None, expires=True):
        from intune_iac.workbench_screens import lifecycle_next
        value = {'status': 'prepared', 'approval_window': {'state': 'closed'}}
        if expires:
            value['expires_at'] = self.CLOSES
        return lifecycle_next(4, value, self.CLOSES + 10, newest_open=newest_open)

    def test_the_reason_is_the_closing_time(self):
        from intune_iac.workbench_screens import _readable_epoch
        said = self.next()
        self.assertIn('its approval window closed at ' + _readable_epoch(self.CLOSES), said)
        self.assertIn('UTC', said)

    def test_the_open_newest_operation_form_gives_the_reason_too(self):
        said = self.next(newest_open='5593d547')
        self.assertIn('review the newest operation, 5593d547', said)
        self.assertIn('its approval window closed at 2026', said)

    def test_no_positional_reference_remains(self):
        for said in (self.next(), self.next('5593d547'), self.next(expires=False)):
            self.assertNotIn(' above', said)
            self.assertNotIn(' below', said)
            self.assertNotIn('Expiry and Approval window', said)

    def test_a_closed_plan_without_a_readable_expiry_still_says_it_closed(self):
        self.assertIn('approval window is closed', self.next(expires=False))


if __name__ == '__main__':
    unittest.main()
