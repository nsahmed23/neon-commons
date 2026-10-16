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


class RootlessCommandsSayWhyTests(unittest.TestCase):
    """Items 3 and 4 (run16-N3, run15-N3, run16-N4): reconcile and execute take only --operation (the operation directory
    names its store), said once beside the printed command; the interrupted line is not wrapped inside its path."""

    def setUp(self):
        import json
        import tempfile
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name) / 'journey 28 run 16' / 'operation-22222222-96c94f884625'
        directory.mkdir(parents=True)
        (directory / 'plan.json').write_text(json.dumps({'operation_id': '678e749f' + '0' * 24}))
        self.OPERATION = str(directory)
    NOTE = 'no --root: the operation directory names its store'

    def interrupted(self, command):
        from intune_iac.workbench import interrupted_lines
        return interrupted_lines({'store_root': '/home/engineer/journey 28 run 16/store',
                                  'interrupted_during': {'command': command, 'operation_root': self.OPERATION}})

    def test_the_interrupted_execute_says_once_why_reconcile_has_no_root(self):
        lines = self.interrupted('execute')
        self.assertEqual(sum(self.NOTE in line for line in lines), 1, lines)
        command = next(index for index, line in enumerate(lines) if line.startswith('  intune-iac workbench reconcile'))
        self.assertNotIn('--root', lines[command])
        self.assertIn(self.NOTE, lines[command + 1])

    def test_the_interrupted_reconcile_says_it_too(self):
        lines = self.interrupted('reconcile')
        self.assertEqual(sum(self.NOTE in line for line in lines), 1, lines)

    def test_the_plan_review_next_says_why_execute_has_no_root(self):
        from intune_iac.workbench_screens import lifecycle_next
        said = lifecycle_next(4, {'status': 'prepared', 'operation_root': self.OPERATION, 'expires_at': 4102444800,
                                  'approval_window': {'state': 'open'}}, 0)
        rows = said.split('\n')
        command = next(index for index, row in enumerate(rows) if row.startswith('  intune-iac workbench execute'))
        self.assertNotIn('--root', rows[command])
        self.assertEqual(said.count(self.NOTE), 1, said)
        self.assertIn(self.NOTE, rows[command + 1])

    def test_the_interrupted_sentence_is_one_row_with_its_directory_whole(self):
        from intune_iac.workbench import interrupted_text
        for command in ('execute', 'reconcile'):
            from intune_iac.workbench import interrupted_lines
            result = {'store_root': '/s', 'interrupted_during': {'command': command, 'operation_root': self.OPERATION}}
            first = interrupted_lines(result)[0]
            self.assertIn("(directory '%s')" % self.OPERATION, first)
            self.assertIn(first, interrupted_text(result, 80))


class GitPinWordsAndStagedFrameTests(unittest.TestCase):
    """Items 5 (run16-N5, N6): the pin flags go to the shell command below, not the command Enter stages; while a command
    is staged the shell-pins block is omitted, so the screen's Next stays on the first page."""
    COMMAND = 'intune-iac workbench repository-import --root /w/store --repository /w/repo --revision abc1234'
    EXPLANATION = ('Ready to record: every value comes from the repository. The commit is recorded as stated; add '
                   '--git-executable and --git-sha256 to the command to verify it against the files.')

    def text(self, **kw):
        from intune_iac.workbench_screens import repository_entry_lines
        value = {'repository': '/w/repo', 'revision': 'f' * 40, 'tenant_id': 't' * 8, 'status': 'discovered', 'components': [],
                 'candidates': [{'number': 1, 'object_id': 'o' * 32, 'state': 'ready', 'stack': 's', 'component': 'c',
                                 'policy_key': 'p', 'backend': 'local', 'backend_source': 'none_declared',
                                 'explanation': self.EXPLANATION, 'observed': {'present': False}, 'command': self.COMMAND}],
                 'next_action': 'x'}
        return ' '.join(' '.join(repository_entry_lines(value, 200, **kw)).split())

    def test_the_flags_are_added_to_the_shell_command_below(self):
        text = self.text()
        self.assertIn('add --git-executable and --git-sha256 to the shell command below to verify it against the files', text)
        self.assertNotIn('to the command to verify', text)

    def test_while_staged_the_shell_block_is_omitted_and_no_sentence_points_at_it(self):
        text = self.text(staged=True)
        self.assertNotIn('From a shell', text)
        self.assertNotIn('GIT_SHA256', text)
        self.assertNotIn('command below', text)
        self.assertNotIn('to the command to verify', text)
        self.assertIn('--git-executable and --git-sha256', text)

    def test_the_workspace_passes_the_staged_state(self):
        import inspect
        from intune_iac import workbench_tui
        self.assertIn('staged=', inspect.getsource(workbench_tui).split('repository_entry_lines(value, width')[1][:200])


if __name__ == '__main__':
    unittest.main()
