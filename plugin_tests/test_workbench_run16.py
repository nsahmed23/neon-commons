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


class ChangedFileRefusalNamesTheChangedFileTests(unittest.TestCase):
    """Item 2 (run16-N2, review 19): the refusal carries which bound file changed (error.effects['changed']) and the
    cause names that file by path; the code and the next step do not change."""

    def refusal(self, changed=None, **kw):
        from intune_iac.workbench_screens import refusal_lines
        error = {'code': 'maintenance_source_changed', 'message': 'A bound file changed.'}
        if changed:
            error['effects'] = {'changed': changed, 'dispatched': False}
        return ' '.join(' '.join(refusal_lines({'status': 'error', 'error': error}, 118, **kw)).split())

    def test_a_changed_context_file_is_named_by_path(self):
        text = self.refusal('context', operation='c3163845', verb='execute', context_file='/w/my ctx.json',
                            desired_file='/w/desired.json')
        self.assertIn("A file this proposal bound changed after operation c3163845 was prepared (the context file "
                      "'/w/my ctx.json'), so its review no longer describes what would run.", text)
        self.assertNotIn('desired.json', text)
        self.assertNotIn('its desired file or its context file', text)

    def test_a_changed_desired_file_is_named_by_path_and_not_the_context_file(self):
        text = self.refusal('desired_source', operation='c3163845', verb='execute', context_file='/w/ctx.json',
                            desired_file='/w/my desired.json')
        self.assertIn("(the desired file '/w/my desired.json')", text)
        self.assertNotIn('ctx.json', text)

    def test_a_known_kind_with_no_readable_path_still_says_which_kind(self):
        self.assertIn('(the desired file)', self.refusal('desired_source', operation='c3163845', verb='execute'))
        self.assertIn('(the context file)', self.refusal('context', verb='execute'))

    def test_an_unknown_kind_keeps_the_general_wording_and_the_code_and_next_step_stay(self):
        text = self.refusal(None, operation='c3163845', verb='execute', context_file='/w/ctx.json')
        self.assertIn('A file it bound (its desired file or its context file) changed after operation c3163845 was prepared', text)
        for changed in ('desired_source', 'context'):
            said = self.refusal(changed, operation='c3163845', verb='execute')
            self.assertIn('(maintenance_source_changed)', said)
            self.assertIn('Next: Prepare a proposal from the recorded intent (a: actions)', said)


class WorkspaceReadsTheDesiredFileTests(unittest.TestCase):
    def test_the_workspace_reads_the_desired_file_the_plan_bound(self):
        from plugin_tests.test_workbench_run11 import Proposed
        from intune_iac.workbench_tui import Workspace
        import shlex

        class Case(Proposed):
            def runTest(self):
                review = self.propose()
                operation = self.root / 'operation'
                ws = self.workspace(4, {})
                command = 'execute %s %s' % (shlex.quote(str(operation)), review['approval_digest'])
                self.assertEqual(Workspace._desired_file_for(ws, command), str(self.root / 'operation.intent-desired.json'))
                self.assertIsNone(Workspace._desired_file_for(ws, 'collect'))
        case = Case()
        case.setUp()
        try:
            case.runTest()
        finally:
            case.tearDown()
            case.doCleanups()


if __name__ == '__main__':
    unittest.main()
