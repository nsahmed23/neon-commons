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


class InterruptedLineControlCharacterTests(unittest.TestCase):
    """Review of e1e153c: the unwrapped interrupted sentence must not carry a raw control character into the terminal."""

    def test_a_directory_name_with_a_newline_cannot_forge_a_row(self):
        import json
        import tempfile
        from pathlib import Path
        from intune_iac.workbench import interrupted_text
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'op\n[REFUSED] forged\tx'
            directory.mkdir()
            (directory / 'plan.json').write_text(json.dumps({'operation_id': '678e749f' + '0' * 24}))
            for command in ('execute', 'reconcile'):
                rows = interrupted_text({'store_root': '/s', 'interrupted_during': {
                    'command': command, 'operation_root': str(directory)}}, 200)
                self.assertTrue(rows[0].startswith('Interrupted while'), rows)
                self.assertFalse(any(row.startswith('[REFUSED]') for row in rows), rows)
                for row in rows:
                    if not row.startswith('  '):
                        self.assertFalse(set(row) & set('\t\n\v\f\r'), repr(row))


class InterruptedPathsAreDisplaySafeTests(unittest.TestCase):
    """The whole class behind the review of e1e153c: a path never puts a raw control character on the screen, in the
    sentence (escaped for display) or in a command row (ANSI-C quoted, so it is one line and still pastes correctly)."""
    CONTROLS = ''.join(chr(code) for code in list(range(32)) + [127])

    def setUp(self):
        import json
        import tempfile
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name) / 'op\n[REFUSED] forged\tx'
        directory.mkdir()
        (directory / 'plan.json').write_text(json.dumps({'operation_id': '678e749f' + '0' * 24}))
        self.path = str(directory)

    def rows(self, command, width=200, path=None):
        from intune_iac.workbench import interrupted_text
        return interrupted_text({'store_root': '/s', 'interrupted_during': {
            'command': command, 'operation_root': path or self.path}}, width)

    def test_no_raw_control_character_and_one_row_each_for_the_sentence_and_the_commands(self):
        for command in ('execute', 'reconcile'):
            for width in (80, 200):
                rows = self.rows(command, width)
                self.assertFalse(set(''.join(rows)) & set(self.CONTROLS), rows)
                self.assertFalse(any(row.startswith('[REFUSED]') for row in rows), (width, rows))
                self.assertEqual(sum(row.startswith('Interrupted while') for row in rows), 1, rows)
                self.assertIn('\\n[REFUSED] forged\\tx', rows[0])
                self.assertEqual(sum(row.startswith('  intune-iac workbench reconcile --operation') for row in rows), 1)

    def test_the_printed_command_argument_gives_back_the_exact_path_in_bash(self):
        import subprocess
        for command in ('execute', 'reconcile'):
            row = next(row for row in self.rows(command) if row.startswith('  intune-iac workbench reconcile'))
            argument = row.split('--operation ', 1)[1]
            self.assertTrue(argument.startswith("$'"), argument)
            done = subprocess.run(['bash', '-c', 'printf %s ' + argument], capture_output=True, timeout=20)
            self.assertEqual(done.stdout.decode('utf-8'), self.path)

    def test_every_control_character_a_backslash_and_a_quote_round_trip(self):
        import subprocess
        from intune_iac.workbench import _shell_arg
        text = '/w/a' + self.CONTROLS.replace('\x00', '') + "\\b'c d"
        done = subprocess.run(['bash', '-c', 'printf %s ' + _shell_arg(text)], capture_output=True, timeout=20)
        self.assertEqual(done.stdout.decode('utf-8'), text)
        self.assertNotIn('\n', _shell_arg(text))

    def test_an_ordinary_path_prints_exactly_as_before(self):
        import json
        import shlex
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'journey 28 run 16' / 'operation-22222222-96c94f884625'
            directory.mkdir(parents=True)
            (directory / 'plan.json').write_text(json.dumps({'operation_id': '678e749f' + '0' * 24}))
            rows = self.rows('execute', 200, str(directory))
            quoted = shlex.quote(str(directory))
            self.assertEqual(rows[0], 'Interrupted while executing operation 678e749f (directory %s).' % quoted)
            self.assertIn('  intune-iac workbench reconcile --operation ' + quoted, rows)

    def operation(self, name):
        import json
        import tempfile
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name) / name
        directory.mkdir()
        (directory / 'plan.json').write_text(json.dumps({'operation_id': '678e749f' + '0' * 24}))
        return str(directory)

    def test_a_backslash_without_a_control_character_prints_as_it_did(self):
        import shlex
        path = self.operation('C:\\work\\op')
        rows = self.rows('execute', 200, path)
        self.assertEqual(rows[0], 'Interrupted while executing operation 678e749f (directory %s).' % shlex.quote(path))
        self.assertNotIn('\\\\', rows[0])

    def test_a_backslash_and_a_newline_both_escape_unambiguously(self):
        path = self.operation('a\\b\nc')
        first = self.rows('execute', 200, path)[0]
        self.assertTrue(first.endswith("a\\\\b\\nc')."), first)
        self.assertFalse(set(first) & set(self.CONTROLS), first)


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


class IdleLimitWordsTests(unittest.TestCase):
    """Item 6 (journey 29 N1): the idle limit is printed in the unit it is, never rounded up to minutes."""

    def test_seconds_below_a_minute_or_not_a_whole_minute(self):
        from intune_iac.companion_page import idle_limit_words
        self.assertEqual([idle_limit_words(n) for n in (1, 2, 59, 90, 61)],
                         ['1 second', '2 seconds', '59 seconds', '90 seconds', '61 seconds'])

    def test_whole_minutes_with_singular_and_plural(self):
        from intune_iac.companion_page import idle_limit_words
        self.assertEqual([idle_limit_words(n) for n in (60, 120, 1800)], ['1 minute', '2 minutes', '30 minutes'])

    def test_the_listener_notice_states_the_limit_in_seconds(self):
        from plugin_tests.test_workbench_companion import Fixture
        from intune_iac.companion import start_live
        from intune_iac.workbench import _companion_read, _store

        class Case(Fixture):
            def runTest(self):
                live = start_live(_companion_read(_store(self.root), self.object_id), idle_seconds=2)
                try:
                    self.said = live.notice
                finally:
                    live.stop()
        Case.setUpClass()
        try:
            case = Case()
            case.setUp()
            case.runTest()
            case.doCleanups()
        finally:
            Case.tearDownClass()
        self.assertIn('it also stops after 2 seconds without a page request', case.said)
        self.assertNotIn('minutes', case.said)

    def test_the_page_note_states_the_limit_in_seconds_too(self):
        from plugin_tests.test_companion_page import Fixture
        Fixture.setUpClass()
        try:
            case = Fixture()
            text = ' '.join(case.page(live={'snapshot': 'snapshot', 'poll_seconds': 3, 'idle_seconds': 2}).split())
        finally:
            Fixture.tearDownClass()
        self.assertIn('or 2 seconds after this page was last loaded', text)
        self.assertNotIn('1 minutes', text)


class HelpListsTheHiddenStripFieldsTests(unittest.TestCase):
    """Item 7 (journey 29 N4): where the strip says '+N more: ?', Help's first screen starts with a row naming the hidden
    fields and their values."""
    FULL = ('SYNTHETIC | TENANT 029c33b1 | POLICY Windows Privacy Pilot (d665d54b) | OBS source changed | '
            'REPO current | OP outcome unknown')
    SHOWN = 'SYNTHETIC | T 029c33b1 | P d665d54b | OBS source changed | +2 more: ?'

    def test_the_hidden_fields_are_listed_with_their_values_right_after_the_title(self):
        from intune_iac.workbench_screens import help_lines
        lines = help_lines(60, strip=self.FULL, strip_shown=self.SHOWN)
        self.assertEqual(lines[0], 'HELP')
        row = ' '.join(' '.join(lines[1:3]).split())
        self.assertTrue(row.startswith('Hidden in the strip at this size (+2 more):'), row)
        self.assertIn('REPO current', row)
        self.assertIn('OP outcome unknown', row)
        self.assertNotIn('OBS source changed', row)
        self.assertNotIn('SYNTHETIC', row)

    def test_no_row_when_the_strip_hides_nothing(self):
        from intune_iac.workbench_screens import help_lines
        self.assertNotIn('Hidden in the strip', ' '.join(help_lines(60, strip=self.FULL, strip_shown=self.FULL)))
        self.assertNotIn('Hidden in the strip', ' '.join(help_lines(60, strip=self.FULL)))

    def test_the_workspace_help_at_60x20_starts_with_the_row(self):
        from plugin_tests.test_workbench_run11 import StripMarkerTests
        StripMarkerTests.setUpClass()
        try:
            case = StripMarkerTests('strip')
            case.setUp()
            ws = case.workspace((60, 20), tab=7, facts=dict(case.FACTS, object_id=case.object_id), value={'navigation': []})
            rows = ws._surface_summary(56)
            case.doCleanups()
        finally:
            StripMarkerTests.tearDownClass()
        first = ' '.join(' '.join(row for row in rows[:6]).split())
        self.assertIn('Hidden in the strip at this size (+', first)
        self.assertIn('OBS source changed | REPO current | OP outcome unknown', first)
        self.assertLess(first.index('Hidden in the strip'), first.index('KEYS'))


class CompanionEndLineTests(unittest.TestCase):
    """Item 8 (journey 29 N5): one prose line before the JSON end line, which stays as it is for scripts."""

    def test_the_prose_line_names_how_it_ended(self):
        from intune_iac.companion import end_line
        self.assertEqual(end_line({'mode': 'live', 'stopped': 'interrupted'}),
                         'The companion stopped (interrupted); its address no longer answers.')
        self.assertEqual(end_line({'mode': 'live', 'stopped': 'idle'}),
                         'The companion stopped (idle); its address no longer answers.')
        self.assertIsNone(end_line({'mode': 'file', 'path': '/w/x.html'}))

    def test_the_command_prints_the_prose_line_before_the_result_and_leaves_the_result_unchanged(self):
        import contextlib
        import io
        from unittest import mock
        from intune_iac import workbench
        args = type('Args', (), {'workbench_command': 'companion', 'root': '/nowhere', 'object': 'o', 'out': None,
                                 'serve': True, 'idle_seconds': 2})()
        result = {'mode': 'live', 'stopped': 'idle'}
        out = io.StringIO()
        with mock.patch.object(workbench, '_store', return_value=object()), \
                mock.patch.object(workbench, '_companion_read', return_value=lambda: {}), \
                mock.patch('intune_iac.companion.run_companion', return_value=result), \
                mock.patch('intune_iac.host_capabilities.require_profile'), contextlib.redirect_stdout(out):
            returned = workbench.command(args)
        self.assertEqual(returned, result)
        self.assertEqual(out.getvalue().splitlines(),
                         ['The companion stopped (idle); its address no longer answers.'])


if __name__ == '__main__':
    unittest.main()
