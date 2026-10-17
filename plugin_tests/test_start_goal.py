"""start --goal: the readiness model of one goal on the screen and in the JSON.

The working directories are built with the product's own routes (the entry tests'
builder) in temporary directories. The command line is called as a function, never
as a subprocess. The commands the screen prints are checked with the product's own
parser, using the extractor of the readiness tests.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TENANT = '11111111-1111-4111-8111-111111111111'
GOALS = ('inspect', 'discover', 'adopt', 'change')
LABELS = {'mode_goal': 'Mode and goal', 'tools_host': 'Tools and host', 'repository': 'Repository',
          'integration_service': 'Integration and service', 'iac_target': 'IaC target', 'backend': 'Backend',
          'execution_route': 'Execution route', 'secret_input': 'Exceptional secret input'}
ORDER = tuple(LABELS)
NEEDS = {
    'inspect': ('mode_goal', 'tools_host'),
    'discover': ('mode_goal', 'tools_host', 'integration_service', 'secret_input'),
    'adopt': ('mode_goal', 'tools_host', 'repository', 'integration_service', 'iac_target', 'backend', 'secret_input'),
    'change': ORDER,
}
HINT = 'Add --goal inspect, discover, adopt or change to see what that goal needs.'
STATE_WORDS = ('ready', 'missing', 'unknown')


class Fixtures:
    """Four temporary directories, built once: offline, repository only, context only, and everything."""
    built = None

    @classmethod
    def get(cls):
        if cls.built is None:
            import plugin_tests.test_entry as entry_tests
            temp = tempfile.TemporaryDirectory()
            base = Path(temp.name)
            work = base / 'work'
            work.mkdir()
            entry_tests.EntryTests.build(types.SimpleNamespace(root=work))
            (base / 'offline').mkdir()
            (base / 'repository').mkdir()
            shutil.copytree(work / 'repository', base / 'repository' / 'repository')
            (base / 'context').mkdir()
            shutil.copyfile(ROOT / 'examples/context.json', base / 'context' / 'context.json')
            cls.built = (temp, {'offline': base / 'offline', 'repository': base / 'repository',
                                'context': base / 'context', 'full': work})
        return cls.built[1]

    @classmethod
    def release(cls):
        """Remove the directories and forget them, so a later module in the same run builds its own instead of being
        handed paths that no longer exist."""
        if cls.built is not None:
            cls.built[0].cleanup()
            cls.built = None


def tearDownModule():
    Fixtures.release()


def run_cli(*argv, width=100):
    """main(['start', ...]) in this process, piped (not a terminal), at a fixed width."""
    from intune_iac.cli import main
    out = io.StringIO()
    with patch('shutil.get_terminal_size', return_value=os.terminal_size((width, 40))), contextlib.redirect_stdout(out):
        code = main(['start', *argv])
    return code, out.getvalue()


def goal_block(text):
    """The lines the goal adds: from its heading to the end, and everything before it."""
    lines = text.split('\n')
    start = next(i for i, line in enumerate(lines) if line.startswith('GOAL READINESS: '))
    return lines[:start], lines[start:]


def field(block, prefix):
    """One top-level line of the block, joined across its wrapped rows (they continue with four spaces)."""
    start = next(i for i, line in enumerate(block) if line.startswith(prefix))
    parts = [block[start]]
    for line in block[start + 1:]:
        if not line.startswith('    '):
            break
        parts.append(line.strip())
    return ' '.join(parts)


def needed_rows(block):
    """(label, state) of each needed row, in order, from the lines of the goal block."""
    rows, inside = [], False
    for line in block:
        if line == 'NEEDED FOR THIS GOAL':
            inside = True
            continue
        if inside and line and not line.startswith(' '):
            break
        if inside and line.startswith('  ') and not line.startswith('   '):
            label, _, state = line.strip().rpartition(': ')
            rows.append((label, state))
    return rows


def needed_section(block):
    """The text of the needed-rows section only."""
    out, inside = [], False
    for line in block:
        if line == 'NEEDED FOR THIS GOAL':
            inside = True
            continue
        if inside and line and not line.startswith(' '):
            break
        if inside:
            out.append(line)
    return '\n'.join(out)


class StartGoalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dirs = Fixtures.get()

    def goal(self, fixture, goal, width=100):
        code, text = run_cli(str(self.dirs[fixture]), '--goal', goal, width=width)
        self.assertEqual(code, 0)
        return text

    # the argument

    def test_goal_accepts_the_four_goals_and_nothing_else(self):
        from intune_iac import cli
        parser = cli.parser()
        for goal in GOALS:
            self.assertEqual(parser.parse_args(['start', '--goal', goal]).goal, goal)
        self.assertIsNone(parser.parse_args(['start']).goal)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(['start', '--goal', 'prepare'])

    # without --goal

    def test_without_a_goal_the_output_is_todays_plus_one_closing_line(self):
        from intune_iac.entry import start_lines, survey
        for fixture in ('offline', 'full'):
            for width in (60, 100):
                with patch('shutil.get_terminal_size', return_value=os.terminal_size((width, 40))):
                    today = start_lines(survey(self.dirs[fixture], relative_to=os.getcwd()), width)
                code, text = run_cli(str(self.dirs[fixture]), width=width)
                self.assertEqual(code, 0)
                lines = text.split('\n')
                self.assertEqual(lines[-1], '')
                lines = lines[:-1]
                self.assertEqual(lines[:len(today)], today, (fixture, width))
                closing = lines[len(today):]
                self.assertTrue(closing, 'no closing line')
                joined = ' '.join(part.strip() for part in closing)
                # The hint, then the one line that names the catalog (PKG-UXVIS-3).
                self.assertTrue(joined.startswith(HINT), joined)
                pointer = ('Catalog of what this build supports and where each goal stands: intune-iac catalog %s'
                           % self.dirs[fixture])
                self.assertEqual(joined[len(HINT):].split(), pointer.split())
                self.assertTrue(all(len(line) <= width for line in closing))

    def test_the_workspace_start_screen_has_no_closing_line(self):
        from intune_iac.entry import start_lines, survey
        self.assertNotIn('--goal', '\n'.join(start_lines(survey(self.dirs['offline']), 100)))

    def test_json_without_a_goal_is_unchanged(self):
        from intune_iac.entry import survey
        code, text = run_cli(str(self.dirs['offline']), '--json')
        self.assertEqual(code, 0)
        value = json.loads(text)
        self.assertNotIn('readiness', value)
        self.assertEqual(value, json.loads(json.dumps(survey(self.dirs['offline'], relative_to=os.getcwd()))))

    # with --goal: the lines

    def test_every_goal_shows_its_needed_rows_in_the_models_order_with_a_state_word(self):
        for fixture in self.dirs:
            for goal in GOALS:
                with self.subTest(fixture=fixture, goal=goal):
                    survey_part, block = goal_block(self.goal(fixture, goal))
                    self.assertEqual(survey_part[0], 'INTUNE WORKBENCH: START')
                    rows = needed_rows(block)
                    self.assertEqual([label for label, _ in rows], [LABELS[r] for r in NEEDS[goal]])
                    for _, state in rows:
                        self.assertIn(state, STATE_WORDS)
                    others = [LABELS[r] for r in ORDER if r not in NEEDS[goal]]
                    text = '\n'.join(block)
                    if others:
                        self.assertEqual(field(block, 'Not needed for this goal: '),
                                         'Not needed for this goal: ' + ', '.join(others) + '.')
                    else:
                        self.assertNotIn('Not needed for this goal', text)

    def test_the_goal_block_follows_the_surveys_summary_and_keeps_it(self):
        from intune_iac.entry import start_lines, survey
        with patch('shutil.get_terminal_size', return_value=os.terminal_size((100, 40))):
            today = start_lines(survey(self.dirs['full'], relative_to=os.getcwd()), 100)
        before, block = goal_block(self.goal('full', 'adopt'))
        self.assertEqual(before, today)
        self.assertNotIn(HINT, '\n'.join(block))

    def test_the_block_names_the_directory_the_host_and_the_goal_status(self):
        for goal in GOALS:
            _, block = goal_block(self.goal('offline', goal, width=400))
            self.assertRegex(block[0], r'^GOAL READINESS: %s \(status: (ready|missing|unknown)\)$' % goal)
            self.assertIn('Directory: ' + str(self.dirs['offline']), block)
            host = field(block, 'Host: ')
            self.assertIn('os ' + os.name, host)
            self.assertIn('platform ' + sys.platform, host)
            self.assertIn('Python %d.%d.%d' % sys.version_info[:3], host)

    def test_the_block_lists_the_supported_and_unsupported_profiles_from_the_host_report(self):
        from intune_iac import host_capabilities
        report = host_capabilities.report()
        supported = [n for n, e in report['profiles'].items() if e['status'] == 'IMPLEMENTED']
        unsupported = [n for n, e in report['profiles'].items() if e['status'] != 'IMPLEMENTED']
        _, block = goal_block(self.goal('offline', 'inspect', width=400))
        self.assertIn('Supported profiles: ' + (', '.join(supported) or 'none'), block)
        self.assertIn('Unsupported profiles: ' + (', '.join(unsupported) or 'none'), block)

    def test_inspect_lists_no_credential_sign_in_or_service_need(self):
        for fixture in self.dirs:
            _, block = goal_block(self.goal(fixture, 'inspect'))
            self.assertEqual([label for label, _ in needed_rows(block)], ['Mode and goal', 'Tools and host'])
            section = needed_section(block).lower()
            for word in ('sign-in', 'token', 'secret', 'tenant authenticate', 'intune-iac capture', 'credential needed: yes',
                         'integration', 'backend', 'execution route'):
                self.assertNotIn(word, section, (fixture, word))

    def test_a_goal_that_needs_nothing_blocking_is_ready_and_says_nothing_is_missing(self):
        _, block = goal_block(self.goal('offline', 'inspect'))
        self.assertIn('(status: ready)', block[0])
        text = '\n'.join(block)
        self.assertIn('Missing: nothing', text)
        self.assertNotIn('Could not check', text)

    @unittest.skipUnless(sys.platform == 'linux', 'the expected states assume a Linux host')
    def test_the_states_of_the_needed_rows_on_an_offline_directory(self):
        expected = {
            'inspect': [('Mode and goal', 'ready'), ('Tools and host', 'ready')],
            'discover': [('Mode and goal', 'ready'), ('Tools and host', 'ready'), ('Integration and service', 'missing'),
                         ('Exceptional secret input', 'unknown')],
            'adopt': [('Mode and goal', 'ready'), ('Tools and host', 'unknown'), ('Repository', 'missing'),
                      ('Integration and service', 'missing'), ('IaC target', 'missing'), ('Backend', 'unknown'),
                      ('Exceptional secret input', 'unknown')],
            'change': [('Mode and goal', 'missing'), ('Tools and host', 'unknown'), ('Repository', 'missing'),
                       ('Integration and service', 'missing'), ('IaC target', 'missing'), ('Backend', 'unknown'),
                       ('Execution route', 'missing'), ('Exceptional secret input', 'unknown')],
        }
        for goal in GOALS:
            _, block = goal_block(self.goal('offline', goal))
            self.assertEqual(needed_rows(block), expected[goal], goal)

    @unittest.skipUnless(sys.platform == 'linux', 'the expected states assume a Linux host')
    def test_a_repository_with_a_selectable_component_is_ready_for_adopt(self):
        _, block = goal_block(self.goal('repository', 'adopt'))
        rows = dict(needed_rows(block))
        self.assertEqual(rows['Repository'], 'ready')
        # No context names a stack and a component, so the target is not resolved.
        self.assertEqual(rows['IaC target'], 'missing')
        text = '\n'.join(block)
        self.assertIn('orgs/reference/dev', text)
        self.assertIn('intune-reference', text)

    @unittest.skipUnless(sys.platform == 'linux', 'the expected states assume a Linux host')
    def test_a_context_names_the_tenant_and_the_sign_in_stays_unknown(self):
        _, block = goal_block(self.goal('context', 'adopt'))
        rows = dict(needed_rows(block))
        self.assertEqual(rows['Integration and service'], 'unknown')
        self.assertIn('Tenant named by the surveyed inputs: ' + TENANT, '\n'.join(block))
        _, block = goal_block(self.goal('context', 'discover'))
        self.assertEqual(dict(needed_rows(block))['Integration and service'], 'unknown')
        _, block = goal_block(self.goal('offline', 'discover'))
        self.assertIn('Tenant named by the surveyed inputs: none named in GUID form', '\n'.join(block))

    def test_an_unknown_row_says_what_could_not_be_checked_and_never_reads_as_ready(self):
        for fixture in self.dirs:
            for goal in GOALS:
                text = self.goal(fixture, goal)
                _, block = goal_block(text)
                rows = needed_rows(block)
                index = {label: block.index('  %s: %s' % (label, state)) for label, state in rows}
                for position, (label, state) in enumerate(rows):
                    end = index[rows[position + 1][0]] if position + 1 < len(rows) else len(block)
                    body = '\n'.join(block[index[label]:end])
                    if state == 'unknown':
                        self.assertIn('    Could not check:', body, (fixture, goal, label))
                        self.assertNotIn('Missing: nothing', body)
                    elif state == 'missing':
                        self.assertIn('    Missing:', body, (fixture, goal, label))
                    else:
                        self.assertIn('Missing: nothing', body)
                    self.assertIn('    Next action (', body)

    def test_each_row_names_its_owner_role_as_the_model_gives_it(self):
        from intune_iac.entry import survey
        from intune_iac.cli import doctor
        from intune_iac.host_capabilities import report
        from intune_iac.readiness import readiness
        model = readiness(survey(self.dirs['full']), report(), doctor(executables=False))
        text = self.goal('full', 'change')
        for row in model['operations']['change']['rows']:
            self.assertIn('    Next action (%s):' % row['owner_role'], text, row['id'])

    def test_tools_are_not_looked_up_and_the_screen_says_so(self):
        text = self.goal('full', 'adopt')
        self.assertIn('intune-iac doctor', text)
        self.assertNotIn('and pass its result, with the host report, to this check', text)
        self.assertNotIn('not found on the search path', text)

    # width, pipes, control bytes

    def test_lines_fit_the_terminal_width(self):
        from intune_iac.workbench_tui import cell_width
        for fixture in self.dirs:
            for goal in GOALS:
                for width in (60, 80, 120):
                    text = self.goal(fixture, goal, width=width)
                    for line in text.split('\n'):
                        self.assertLessEqual(cell_width(line), width, (fixture, goal, width, line))

    def test_piped_output_has_no_control_byte_and_no_escape_sequence(self):
        for fixture in self.dirs:
            for goal in GOALS:
                text = self.goal(fixture, goal)
                self.assertNotIn('\x1b', text)
                self.assertNotIn('\x9b', text)
                self.assertFalse([c for c in text if ord(c) < 0x20 and c != '\n'], (fixture, goal))

    def test_a_control_byte_in_a_file_name_does_not_reach_the_screen(self):
        with tempfile.TemporaryDirectory() as temp:
            try:
                directory = Path(temp) / 'odd\x1b[31m\x07name'
                directory.mkdir()
            except OSError:
                self.skipTest('this file system refuses a control byte in a name')
            shutil.copyfile(ROOT / 'examples/context.json', directory / 'context.json')
            for goal in GOALS:
                code, text = run_cli(str(directory), '--goal', goal)
                self.assertEqual(code, 0)
                self.assertFalse([c for c in text if ord(c) < 0x20 and c != '\n'], goal)

    # the commands

    def logical_lines(self, block):
        """Rows joined across trailing backslashes, so a wrapped command is one line again."""
        out, current = [], None
        for line in block:
            if current is not None:
                current += ' ' + line.strip()
            else:
                current = line
            if current.endswith(' \\'):
                current = current[:-2]
                continue
            out.append(current)
            current = None
        self.assertIsNone(current, 'the last row of a command ends with a backslash')
        return out

    def test_every_command_the_screen_prints_is_accepted_by_the_product_parser(self):
        from intune_iac import cli
        from plugin_tests.test_readiness import ReadinessTests
        extractor = ReadinessTests('printed_commands')
        parser = cli.parser()
        checked = 0
        for fixture in self.dirs:
            for goal in GOALS:
                for width in (50, 72, 120):
                    _, block = goal_block(self.goal(fixture, goal, width=width))
                    for line in self.logical_lines(block):
                        for tokens in extractor.printed_commands(line):
                            argv = ['3' if token == 'FD' else token for token in tokens]
                            with contextlib.redirect_stderr(io.StringIO()) as err:
                                try:
                                    parser.parse_args(argv)
                                except SystemExit:
                                    self.fail('the product parser rejects: intune-iac %s\n%s' % (' '.join(tokens), err.getvalue()))
                            checked += 1
        self.assertGreater(checked, 100)

    def test_a_command_is_on_its_own_rows_and_nothing_printed_is_dropped(self):
        from intune_iac.cli import doctor
        from intune_iac.entry import survey
        from intune_iac.host_capabilities import report
        from intune_iac.readiness import placeholders_in_words, readiness, screen_note
        from plugin_tests.test_readiness import ReadinessTests
        extractor = ReadinessTests('printed_commands')
        for fixture in self.dirs:
            value = survey(self.dirs[fixture])
            model = readiness(value, report(), doctor(executables=False))
            for goal in GOALS:
                expected = []
                for row in model['operations'][goal]['rows']:
                    if row['needed']:
                        # The screen says each recorded note through screen_note (PKG-CATALOG-5, item 4); a note may hold a command.
                        for note in row['missing']:
                            # PKG-START-STANDIN round 3: a command with a placeholder is said in words, so it is not printed
                            expected += extractor.printed_commands(placeholders_in_words(screen_note(note, value['directory'])))
                        expected += extractor.printed_commands(placeholders_in_words(row['next_action']))
                for width in (50, 120):
                    _, block = goal_block(self.goal(fixture, goal, width=width))
                    shown = []
                    # The pointer start adds at its end (PKG-UXVIS-3): its sentence and its one command are not goal rows.
                    lines = [line for line in self.logical_lines(block) if line]
                    cut = next(i for i, line in enumerate(lines) if line.startswith('Catalog of what this build supports'))
                    lines = lines[:cut]
                    for line in lines:
                        if line.strip().startswith('intune-iac '):
                            shown += extractor.printed_commands(line.strip())
                        else:
                            self.assertNotIn('intune-iac ', line)
                    self.assertEqual(shown, expected, (fixture, goal, width))

    def test_a_long_command_wraps_between_arguments_with_a_trailing_backslash(self):
        _, block = goal_block(self.goal('offline', 'discover', width=60))
        # the capture command is words now (it holds placeholders); the sign-in check command is the long one that is printed
        starts = [i for i, line in enumerate(block) if line.strip().startswith('intune-iac start ')]
        self.assertTrue(starts)
        for start in starts:
            rows = [block[start]]
            while rows[-1].endswith(' \\'):
                rows.append(block[start + len(rows)])
            self.assertGreater(len(rows), 1)
            for row in rows[:-1]:
                self.assertTrue(row.endswith(' \\'))
            self.assertFalse(rows[-1].endswith('\\'))
            for row in rows[1:]:
                self.assertTrue(row.startswith(' ' * 4), row)

    # no process, no environment value

    def test_the_readiness_facts_start_no_process_and_read_no_environment_value(self):
        from intune_iac.entry import goal_readiness, survey
        value = survey(self.dirs['full'])

        class Recording(dict):
            reads = []

            def __getitem__(self, key):
                self.reads.append(key)
                return super().__getitem__(key)

            def get(self, key, default=None):
                self.reads.append(key)
                return super().get(key, default)

            def __contains__(self, key):
                self.reads.append(key)
                return super().__contains__(key)

        def refuse(*args, **kwargs):
            raise AssertionError('a process or a search-path lookup was started: %r' % (args,))

        recording = Recording(os.environ)
        Recording.reads = []
        with patch('subprocess.Popen', refuse), patch('shutil.which', refuse), patch('os.system', refuse), \
                patch.object(os, 'environ', recording):
            for goal in GOALS:
                result = goal_readiness(value, goal)
                self.assertEqual(result['goal'], goal)
        self.assertEqual(Recording.reads, [])

    def test_the_omitted_facts_are_named_in_the_result(self):
        from intune_iac.entry import goal_readiness, survey
        result = goal_readiness(survey(self.dirs['offline']), 'adopt')
        self.assertTrue(any('search path' in text for text in result['omitted_facts']))

    # the json

    def test_json_with_a_goal_carries_the_model_for_that_goal(self):
        from intune_iac.cli import doctor
        from intune_iac.entry import survey
        from intune_iac.host_capabilities import report
        from intune_iac.readiness import readiness
        for fixture in ('offline', 'full'):
            plain = json.loads(run_cli(str(self.dirs[fixture]), '--json')[1])
            for goal in GOALS:
                code, text = run_cli(str(self.dirs[fixture]), '--json', '--goal', goal)
                self.assertEqual(code, 0)
                value = json.loads(text)
                carried = value.pop('readiness')
                self.assertEqual(value, plain)
                model = readiness(survey(self.dirs[fixture]), report(), doctor(executables=False))
                operation = model['operations'][goal]
                self.assertEqual(carried['goal'], goal)
                self.assertEqual(carried['schema_version'], model['schema_version'])
                self.assertEqual(carried['status'], operation['status'])
                self.assertEqual(carried['rows'], operation['rows'])
                self.assertEqual(carried['blocking'], operation['blocking'])
                self.assertEqual([row['id'] for row in carried['rows']], list(ORDER))
                self.assertEqual([row['id'] for row in carried['rows'] if row['needed']], list(NEEDS[goal]))
                self.assertIs(carried['execution_authorized'], False)
                self.assertIs(carried['cloud_authority'], False)
                self.assertTrue(carried['omitted_facts'])

    def test_the_inspect_json_names_no_credential_row_as_needed(self):
        value = json.loads(run_cli(str(self.dirs['full']), '--json', '--goal', 'inspect')[1])
        needed = [row['id'] for row in value['readiness']['rows'] if row['needed']]
        self.assertEqual(needed, ['mode_goal', 'tools_host'])

    # the wording of the one row start can leave open

    def test_an_unreported_tool_lookup_points_at_doctor_and_not_at_a_check_to_pass_a_result_to(self):
        from intune_iac.cli import doctor
        from intune_iac.entry import survey
        from intune_iac.host_capabilities import report
        from intune_iac.readiness import readiness
        model = readiness(survey(self.dirs['offline']), report(), doctor(executables=False))
        row = next(r for r in model['operations']['adopt']['rows'] if r['id'] == 'tools_host')
        if sys.platform == 'linux':
            self.assertEqual(row['state'], 'unknown')
        self.assertNotIn('pass its result', row['next_action'])
        self.assertIn('intune-iac doctor', row['next_action'])


if __name__ == '__main__':
    unittest.main()
