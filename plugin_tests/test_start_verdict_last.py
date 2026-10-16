"""PKG-SETUP-5D item 3: `start --goal` shows its goal readiness verdict where a 40-row pane shows it.

The screen is longer than a pane, so the pane shows only its tail. The verdict heading stays where it is (the long sections
follow it); one summary line, built by the same function from the same status, repeats it as the last line. No goal, no line.
"""
import json
import re
import unittest

from plugin_tests.test_start_goal import GOALS, Fixtures, run_cli, tearDownModule  # noqa: F401  (tearDownModule is the module hook)

SUMMARY = re.compile(r'^GOAL READINESS: (inspect|discover|adopt|change) \(status: (ready|missing|unknown)\)$')


class VerdictLastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dirs = Fixtures.get()

    def screen(self, fixture, goal, width=100):
        code, text = run_cli(str(self.dirs[fixture]), '--goal', goal, width=width)
        self.assertEqual(code, 0)
        return text.rstrip('\n').split('\n')

    def test_the_last_line_is_the_goal_summary_and_equals_the_heading(self):
        for fixture in ('offline', 'full'):
            for goal in GOALS:
                lines = self.screen(fixture, goal)
                self.assertRegex(lines[-1], SUMMARY, (fixture, goal))
                heading = next(line for line in lines if line.startswith('GOAL READINESS: '))
                self.assertEqual(lines[-1], heading, (fixture, goal))

    def test_the_summary_is_visible_in_the_last_rows_of_a_forty_row_pane(self):
        for fixture in ('offline', 'full'):
            for goal in GOALS:
                lines = self.screen(fixture, goal)
                self.assertTrue(any(SUMMARY.match(line) for line in lines[-39:]), (fixture, goal))

    def test_the_status_is_the_one_the_json_reports(self):
        from intune_iac.cli import main
        import contextlib
        import io
        for goal in GOALS:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(['start', str(self.dirs['full']), '--goal', goal, '--json']), 0)
            status = json.loads(out.getvalue())['readiness']['status']
            self.assertEqual(self.screen('full', goal)[-1], 'GOAL READINESS: %s (status: %s)' % (goal, status))

    def test_without_a_goal_there_is_no_summary_line(self):
        code, text = run_cli(str(self.dirs['full']))
        self.assertEqual(code, 0)
        self.assertFalse(any(line.startswith('GOAL READINESS') for line in text.split('\n')))

    def test_the_summary_appears_once_more_and_nothing_follows_it(self):
        lines = self.screen('full', 'adopt')
        self.assertEqual(sum(1 for line in lines if line.startswith('GOAL READINESS: ')), 2)
        self.assertEqual(lines[-1].startswith('GOAL READINESS: '), True)

    def test_a_narrow_pane_keeps_the_summary_on_one_row(self):
        self.assertRegex(self.screen('offline', 'change', width=40)[-1], SUMMARY)


if __name__ == '__main__':
    unittest.main()
