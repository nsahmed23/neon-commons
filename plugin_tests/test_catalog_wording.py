"""PKG-CATALOG-5: the catalog's wording on a 40-row pane and the words a fresh engineer reads (journey 33 run 1, reviews A and B).

Every change here is in the text form. The `--json` form is frozen (test_catalog_json_golden): the same recorded data, said in
better words on the screen. The working directories are the ones the start tests build, with the product's own routes.
"""
import copy
import os
import re
import unittest

from plugin_tests import test_catalog as tc
from plugin_tests.test_start_goal import Fixtures, tearDownModule  # noqa: F401  (tearDownModule is the module hook)

GOALS = ('inspect', 'discover', 'adopt', 'change')
WIDTH = 120
PANE = 39  # the visible rows of a 40-row pane: the shell prompt takes the last one
ENTRY = re.compile(r'^  (inspect|discover|adopt|change):$')
# The unsupported row (PKG-CATALOG-6 item 2): the recorded cloud gap of `change`, and the sentence for a goal with no recorded gap.
CLOUD_GAP = 'yes: a managed change to the cloud has no route (see blocked).'
NO_GAP = 'no gap is recorded for this goal alone; what a live run still lacks is in the live row.'
# What the catalog says, for a directory it may not show, where the start screen prints the start command (PKG-CATALOG-6).
HIDDEN_NOTE = ('run the start command with this directory, --goal discover and --check-signin azure '
               '(the directory cannot be shown here; it runs az account list')


# What the start screen says, for a directory it may not show, where it would print the workspace command (PKG-START-STANDIN).
OPEN_WORKSPACE_WORDS = ('Open the workspace with the workbench workspace command using this saved store; '
                        'its path cannot be shown here.')


def flat(lines):
    """Rows as one string: a command's trailing backslash dropped, runs of spaces made one."""
    return ' '.join(' '.join(lines).replace(' \\ ', ' ').split())


def note_for(directory, goal='discover', said=False):
    """The recorded no-sign-in-check note as a screen says it for a surveyed directory: the operand is the one the screen's path
    writer writes for it (entry.text_paths, with no relative_to: DIRECTORY for a refused name, otherwise the directory in full,
    quoted), and the legend rides in the note only when the screen has not said it under its header (said=False)."""
    from pathlib import Path
    from intune_iac import entry, readiness
    operand = entry.text_paths(Path(directory), None)[3]()
    fields = entry.screen_directory(directory, operand)
    legend = '' if said or not fields['directory_hidden'] else readiness.DIRECTORY_NOT_SHOWN
    return readiness.screen_note(readiness.NO_CHECK_RECORDED % goal, fields['directory_operand'], legend)


def goal_rows(lines, goal):
    """{state label: its text joined across the wrapped rows} of one goal's block at 90 columns or more."""
    start = lines.index('  GOAL ' + goal)
    rows, label = {}, None
    for line in lines[start + 1:]:
        if line.startswith('  GOAL ') or not line.startswith('    '):
            break
        match = re.match(r'^    ([a-z-]+):\s*(.*)$', line)
        if match and not line.startswith(' ' * 20):
            label = match.group(1)
            rows[label] = [match.group(2)]
        else:
            rows[label].append(line.strip())
    return {name: ' '.join(' '.join(parts).split()) for name, parts in rows.items()}


def next_action_entries(lines):
    """{goal: the rows of its NEXT ACTION entry} from the last NEXT ACTION heading to the end."""
    start = len(lines) - 1 - lines[::-1].index('NEXT ACTION')
    entries, goal = {}, None
    for line in lines[start + 1:]:
        match = ENTRY.match(line)
        if match:
            goal = match.group(1)
            entries[goal] = []
        elif goal is not None:
            entries[goal].append(line)
    return entries


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dirs = Fixtures.get()

    def model(self, fixture, goal=None, manifest=None, relative_to=None):
        from intune_iac import catalog as module, entry
        value = entry.survey(self.dirs[fixture], relative_to=relative_to)
        return module.build(value, doctor=tc.doctor(), goal=goal, manifest=manifest, relative_to=relative_to)

    def lines(self, fixture, goal=None, width=WIDTH, manifest=None, relative_to=None):
        return tc.text_of(self.model(fixture, goal, manifest, relative_to), width)


class VerdictOnTheLastScreenTests(Base):
    """Item 1: a 40-row pane shows the last 39 rows, so each goal's verdict stands beside its next action there."""

    def check(self, fixture, goal):
        model = self.model(fixture, goal)
        lines = self.lines(fixture, goal)
        tail = lines[-PANE:]
        entries = next_action_entries(tail)
        shown = [item['goal'] for item in model['integrations'][0]['goals']]
        self.assertEqual(list(entries), shown, (fixture, goal))
        for item in model['integrations'][0]['goals']:
            name = item['goal']
            rows = goal_rows(lines, name)
            entry = entries[name]
            blocked = rows['blocked'].split('. ')[0] if rows['blocked'].startswith('yes, by') else rows['blocked']
            verdict = 'Verdict: operation-ready: %s; blocked: %s' % (rows['operation-ready'], blocked)
            # the verdict wraps now that it carries its caveats (PKG-CATALOG-6 item 3): read it across its rows
            text = flat(entry)
            self.assertIn(verdict, text, (fixture, goal, name, 'no verdict line beside the next action in the last rows'))
            from intune_iac.readiness import placeholders_in_words
            # the screen says a recorded command that holds a placeholder in words (PKG-START-STANDIN round 3)
            self.assertIn(flat([placeholders_in_words(item['next_action'])]), text[text.index(verdict):], (fixture, goal, name))
            # one source: the words are the state rows' own words, not a second wording of the same state
            self.assertEqual(item['operation_ready']['status'] in rows['operation-ready'], True)

    def test_every_goal_shows_its_verdict_and_next_action_in_the_last_39_rows(self):
        for fixture in ('offline', 'context', 'repository', 'full'):
            with self.subTest(fixture=fixture):
                self.check(fixture, None)

    def test_a_chosen_goal_shows_its_own_verdict_and_next_action_in_the_last_39_rows(self):
        for fixture in ('offline', 'full'):
            for goal in GOALS:
                with self.subTest(fixture=fixture, goal=goal):
                    self.check(fixture, goal)

    def test_the_verdict_is_built_from_the_same_data_as_the_state_rows(self):
        model = self.model('offline')
        for item in model['integrations'][0]['goals']:
            lines = self.lines('offline', item['goal'])
            entry = next_action_entries(lines)[item['goal']]
            text = flat(entry)
            self.assertIn('operation-ready: %s (readiness status: %s)' % (item['operation_ready']['state'],
                                                                         item['operation_ready']['status']), text)
            if item['blocked']['state'] == 'blocked':
                self.assertIn('blocked: yes, by %s (%s)' % (item['blocked']['row'], item['blocked']['row_state']), text)
            else:
                self.assertIn('blocked: no prerequisite is reported as not ready', text)


class LiveRowTests(Base):
    """Item 2: the live state and its recorded blockers have their own row; `unsupported` and `blocked` keep their own meaning."""

    def test_every_goal_has_a_live_row_with_the_recorded_blockers_and_nothing_else_carries_them(self):
        from intune_iac import integration_manifest
        blockers = [word.replace('_', ' ') for word in integration_manifest.load()['live_blockers']]
        for fixture in ('offline', 'full'):
            lines = self.lines(fixture)
            for goal in GOALS:
                with self.subTest(fixture=fixture, goal=goal):
                    rows = goal_rows(lines, goal)
                    self.assertEqual(list(rows), ['available', 'configured', 'authenticated', 'operation-ready', 'blocked',
                                                  'unsupported', 'live'])
                    self.assertTrue(rows['live'].startswith('not run; recorded blockers for a live run: '), rows['live'])
                    self.assertTrue(rows['live'].endswith(blockers[-1] + '.'), rows['live'])
                    for blocker in blockers:
                        self.assertIn(blocker, rows['live'])
                        for name in ('available', 'configured', 'authenticated', 'operation-ready', 'blocked', 'unsupported'):
                            self.assertNotIn(blocker, rows[name], (name, blocker))
                    self.assertNotIn('Live', rows['unsupported'])
                    self.assertEqual(rows['unsupported'], CLOUD_GAP if goal == 'change' else NO_GAP)

    def test_unsupported_keeps_the_operations_the_manifest_does_not_list(self):
        from intune_iac import integration_manifest
        manifest = copy.deepcopy(integration_manifest.load())
        for kind in manifest['object_kinds']:
            kind['operations'] = [item for item in kind['operations'] if item['name'] != 'adoption']
        rows = goal_rows(self.lines('offline', manifest=manifest), 'adopt')
        self.assertTrue(rows['unsupported'].startswith('yes: The manifest lists no adoption operation'), rows['unsupported'])
        self.assertNotIn('Live', rows['unsupported'])
        self.assertNotIn('blockers', rows['unsupported'])
        self.assertIn('provider not qualified', rows['live'])

    def test_blocked_stays_about_this_goal_here(self):
        rows = goal_rows(self.lines('offline'), 'inspect')
        self.assertEqual(rows['blocked'], 'no prerequisite is reported as not ready')
        self.assertNotIn('cloud executor', rows['blocked'])

    def test_the_layout_below_90_columns_keeps_the_live_row_too(self):
        for width in (60, 80):
            text = flat(self.lines('offline', width=width))
            self.assertEqual(text.count('recorded blockers for a live run:'), 4, width)


class VerdictCaveatsTests(Base):
    """PKG-CATALOG-6 item 3 (journey 33 run 2, review A finding F3): the closing Verdict line showed `operation-ready: yes` without
    the `authenticated: not checked` and `live: not run` facts that scrolled off. They ride on the line, from the rows' source."""

    CAVEATS = '; authenticated: not checked; live: not run'

    def test_every_goals_verdict_carries_what_is_not_checked_and_not_run(self):
        for fixture in ('offline', 'full'):
            for goal in GOALS:
                with self.subTest(fixture=fixture, goal=goal):
                    text = flat(next_action_entries(self.lines(fixture, goal)[-PANE:])[goal])
                    model = self.model(fixture, goal)['integrations'][0]['goals'][0]
                    self.assertIn('Verdict: operation-ready: %s (readiness status: %s)' % (
                        model['operation_ready']['state'], model['operation_ready']['status']), text)
                    self.assertIn(self.CAVEATS, text)

    def test_the_last_screen_of_inspect_says_ready_with_its_caveats(self):
        text = flat(self.lines('full', 'inspect')[-PANE:])
        self.assertIn('operation-ready: yes (readiness status: ready); blocked: no prerequisite is reported as not ready' +
                      self.CAVEATS, text)

    def test_a_checked_sign_in_drops_the_authenticated_caveat_and_keeps_live(self):
        from intune_iac import catalog as module
        from plugin_tests.test_signin_not_permission import GOOD
        from plugin_tests import test_readiness as tr
        value = module.build(tc.survey(tr.repository_item(), tr.context_item(tenant=GOOD['accounts'][0]['tenant'])),
                             doctor=tc.doctor(), signin={'azure': GOOD}, goal='discover')
        text = flat(next_action_entries(tc.text_of(value, WIDTH))['discover'])
        self.assertNotIn('authenticated: not checked', text)
        self.assertIn('; live: not run', text)

    def test_the_verdict_words_come_from_one_source(self):
        from intune_iac import catalog as module
        goal = self.model('offline', 'discover')['integrations'][0]['goals'][0]
        self.assertTrue(module.verdict_words(goal).endswith(self.CAVEATS))


class JsonWordingTests(Base):
    """PKG-CATALOG-6 item 4 (journey 33 run 2, review A finding F1): the --json strings said `(not authenticated)` where the text
    says authentication was not checked, and `blocked.missing` kept the old garbled sentence. Keys and structure are unchanged."""

    def test_a_project_state_reads_authentication_not_checked_as_the_text_does(self):
        value = self.model('full')
        self.assertTrue(value['projects'])
        for project in value['projects']:
            self.assertNotIn('not authenticated', project['state'], project['state'])
            self.assertNotIn('(not authenticated)', project['state'])
        self.assertTrue(any('(authentication not checked)' in project['state'] for project in value['projects']))
        text = flat(self.lines('full'))
        for project in value['projects']:
            self.assertIn(project['state'], text)

    def test_blocked_missing_is_the_two_sentences_the_text_says_not_the_garbled_one(self):
        goal = self.model('context', 'discover')['integrations'][0]['goals'][0]
        missing = goal['blocked']['missing']
        self.assertNotIn('no sign-in check was run: start with', missing)
        self.assertTrue(missing.startswith('No sign-in check was run. To look for an existing Azure sign-in, run: intune-iac start '),
                        missing)
        self.assertTrue(missing.endswith('--goal discover --check-signin azure (it runs az account list --output json and '
                                         'nothing else).'), missing)
        self.assertIn(missing, flat(self.lines('context', 'discover')).replace(' \\ ', ' '))

    def test_the_keys_of_the_record_are_unchanged(self):
        value = self.model('full')
        self.assertEqual(sorted(value), ['cloud_authority', 'directory', 'execution_authorized', 'integrations',
                                         'other_integrations', 'projects', 'schema_version', 'signin_checked'])
        self.assertEqual(sorted(value['projects'][0]), ['command', 'kind', 'label', 'note', 'path', 'state', 'summary'])
        self.assertEqual(sorted(value['integrations'][0]['goals'][0]['blocked']),
                         ['missing', 'next_action', 'row', 'row_state', 'state'])


class UnsupportedRowTests(Base):
    """PKG-CATALOG-6 item 2 (journey 33 run 2, review A finding F2): under `change`, `unsupported: nothing recorded as unsupported
    in this build.` sat beside `no cloud route exists`, and read as broad support. The row states the recorded gap where there is
    one and otherwise a sentence that cannot be read as support, from the records the other rows read."""

    def test_change_states_the_gap_the_available_and_blocked_rows_record(self):
        for fixture in ('offline', 'full'):
            rows = goal_rows(self.lines(fixture), 'change')
            self.assertEqual(rows['unsupported'], CLOUD_GAP, fixture)
            self.assertIn('no cloud route exists', rows['available'])
            self.assertNotIn('nothing recorded', rows['unsupported'])

    def test_a_goal_with_no_recorded_gap_does_not_read_as_broad_support(self):
        for goal in ('inspect', 'discover', 'adopt'):
            text = goal_rows(self.lines('offline'), goal)['unsupported']
            self.assertEqual(text, NO_GAP, goal)
            self.assertNotIn('nothing recorded as unsupported', text)
            self.assertNotIn('in this build', text)

    def test_the_gap_follows_the_records_the_available_row_reads(self):
        from intune_iac import integration_manifest
        manifest = copy.deepcopy(integration_manifest.load())
        manifest['live_blockers'] = [item for item in manifest['live_blockers'] if item != 'cloud_executor_unavailable']
        text = goal_rows(self.lines('offline', manifest=manifest), 'change')['unsupported']
        self.assertEqual(text, NO_GAP)
        self.assertNotIn('cloud', text)

    def test_the_json_form_keeps_its_unsupported_record(self):
        goals = {item['goal']: item for item in self.model('offline')['integrations'][0]['goals']}
        self.assertEqual(goals['change']['unsupported']['state'], 'none_recorded')
        self.assertEqual(goals['change']['unsupported']['reasons'], [])


class AvailableRowTests(Base):
    """Item 3: `available: yes` with `execute` listed says what the operations run against and that no cloud route exists."""

    def test_a_goal_whose_operations_only_run_on_the_modeled_service_says_so_in_the_available_row(self):
        for fixture in ('offline', 'full'):
            rows = goal_rows(self.lines(fixture), 'change')
            text = rows['available']
            self.assertTrue(text.startswith('yes, against the modeled service only; no cloud route exists ('), text)
            self.assertIn('operations: plan, approval, execute, reconcile', text)
            self.assertIn('evidence: synthetic local process only', text)

    def test_the_other_goals_keep_their_available_row(self):
        rows = {goal: goal_rows(self.lines('offline'), goal)['available'] for goal in ('inspect', 'discover', 'adopt')}
        self.assertEqual(rows['inspect'], 'yes (operations: inventory, selection, validation; evidence: local evidence only)')
        self.assertEqual(rows['discover'], 'yes (operations: discovery; evidence: local evidence only)')
        self.assertEqual(rows['adopt'], 'yes (operations: ownership, mapping, adoption; evidence: local evidence only)')

    def test_the_cloud_clause_follows_the_recorded_live_blockers(self):
        from intune_iac import integration_manifest
        manifest = copy.deepcopy(integration_manifest.load())
        manifest['live_blockers'] = [item for item in manifest['live_blockers'] if item != 'cloud_executor_unavailable']
        text = goal_rows(self.lines('offline', manifest=manifest), 'change')['available']
        self.assertTrue(text.startswith('yes, against the modeled service only ('), text)
        self.assertNotIn('no cloud route', text)

    def test_a_chosen_goal_says_it_too(self):
        self.assertIn('against the modeled service only; no cloud route exists',
                      goal_rows(self.lines('full', 'change'), 'change')['available'])


class GarbledSentenceTests(Base):
    """Item 4: a recorded sentence that read "no sign-in check was run: start with --goal discover ... looks for" becomes two
    sentences with the command on its own rows."""

    def sentence(self, goal, directory=None):
        """The note as a screen says it; the command names the surveyed directory so that it runs on what the screen is about."""
        import shlex
        where = '' if directory is None else shlex.quote(str(directory)) + ' '
        return ('No sign-in check was run. To look for an existing Azure sign-in, run: intune-iac start %s--goal %s --check-signin '
                'azure (it runs az account list --output json and nothing else).' % (where, goal))

    def command_rows(self, lines):
        from plugin_tests.test_start_goal import StartGoalTests
        return [line.strip() for line in StartGoalTests('logical_lines').logical_lines(lines)]

    def test_the_catalog_says_it_in_two_sentences_with_the_command_on_its_own_rows(self):
        directory = self.dirs['context']
        for width in (120, 100):
            # a context names the tenant, so the blocked row shows the sign-in note first (an empty directory shows the tenant note)
            lines = self.lines('context', 'discover', width=width)
            self.assertIn(self.sentence('discover', directory), flat(lines), width)
            self.assertNotIn('start with --goal', flat(lines))
            self.assertNotIn('was run:', flat(lines))
            self.assertIn('intune-iac start %s --goal discover --check-signin azure' % directory, self.command_rows(lines), width)

    def test_the_start_screen_says_it_the_same_way_for_every_goal_that_needs_a_sign_in(self):
        from plugin_tests.test_start_goal import goal_block, run_cli
        for goal in ('discover', 'adopt', 'change'):
            for width in (60, 100, 120):
                code, text = run_cli(str(self.dirs['offline']), '--goal', goal, width=width)
                self.assertEqual(code, 0)
                _, block = goal_block(text)
                directory = self.dirs['offline']
                self.assertIn(self.sentence(goal, directory), flat(block), (goal, width))
                self.assertNotIn('start with --goal', flat(block))
                # on its own rows: a command wider than the pane breaks between arguments, each row but the last ending in a backslash
                self.assertIn('intune-iac start %s --goal %s --check-signin azure' % (directory, goal), self.command_rows(block),
                              (goal, width))

    def test_the_command_it_prints_is_one_the_product_parser_accepts(self):
        import contextlib
        import io
        from intune_iac import cli
        from plugin_tests.test_readiness import ReadinessTests
        from plugin_tests.test_start_goal import StartGoalTests, goal_block, run_cli
        extractor = ReadinessTests('printed_commands')
        parser = cli.parser()
        for goal in ('discover', 'adopt', 'change'):
            for width in (50, 72, 120):
                _, block = goal_block(run_cli(str(self.dirs['offline']), '--goal', goal, width=width)[1])
                commands = [tokens for line in StartGoalTests('logical_lines').logical_lines(block)
                            for tokens in extractor.printed_commands(line)]
                wanted = ['start', str(self.dirs['offline']), '--goal', goal, '--check-signin', 'azure']
                self.assertIn(wanted, commands, (goal, width))
                with contextlib.redirect_stderr(io.StringIO()):
                    args = parser.parse_args(wanted)
                self.assertEqual((args.command, args.directory, args.goal, args.check_signin),
                                 ('start', str(self.dirs['offline']), goal, 'azure'))

    def test_a_directory_with_a_space_is_quoted_and_one_with_a_control_character_is_a_placeholder(self):
        import contextlib
        import io
        import shlex
        import shutil
        import tempfile
        from pathlib import Path
        from intune_iac import catalog as module, cli, entry, readiness
        self.assertIn("run: intune-iac start '/tmp/a b' --goal discover", note_for('/tmp/a b'))
        shown = note_for('/tmp/a\x1b[31mb')
        self.assertIn('run: intune-iac start DIRECTORY --goal discover', shown)
        self.assertNotIn('\x1b', shown)
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / 'estate dir'
            directory.mkdir()
            shutil.copyfile(Path(__file__).resolve().parents[1] / 'examples/context.json', directory / 'context.json')
            lines = tc.text_of(module.build(entry.survey(directory), doctor=tc.doctor(), goal='discover'), 100)
            command = next(row for row in self.command_rows(lines) if row.startswith('intune-iac start '))
            argv = shlex.split(command)
            self.assertEqual(argv[2], str(directory))
            with contextlib.redirect_stderr(io.StringIO()):
                args = cli.parser().parse_args(argv[1:])
            self.assertEqual((args.directory, args.goal, args.check_signin), (str(directory), 'discover', 'azure'))

    def test_the_recorded_note_is_unchanged_because_the_json_form_is_frozen(self):
        from intune_iac import readiness
        model = readiness.readiness(tc.survey(), tc.tr.host_report(), tc.doctor())
        for goal in ('discover', 'adopt', 'change'):
            row = next(row for row in model['operations'][goal]['rows'] if row['id'] == 'integration_service')
            recorded = readiness.NO_CHECK_RECORDED % goal
            self.assertIn(recorded, row['missing'])
            self.assertEqual(readiness.screen_note(recorded), self.sentence(goal))
            self.assertEqual(readiness.screen_note(recorded, '/work/here'), self.sentence(goal, '/work/here'))
        self.assertEqual(readiness.screen_note('Any other note stays as it is.'), 'Any other note stays as it is.')

    def test_after_a_sign_in_check_the_note_is_not_there(self):
        from intune_iac import readiness
        from plugin_tests.test_signin_not_permission import GOOD
        value = tc.catalog(tc.tr.context_item(tenant=GOOD['accounts'][0]['tenant']), signin={'azure': GOOD}, goal='discover')
        self.assertNotIn('No sign-in check was run', flat(tc.text_of(value, 120)))
        self.assertNotIn(readiness.NO_CHECK_RECORDED % 'discover', flat(tc.text_of(value, 120)))


class ResumeBaseTests(Base):
    """Item 5: the resume commands name paths relative to where `catalog` was run; the screen says so once, above them."""

    SENTENCE = ('Resume commands are typed from the directory this catalog was run in; a path outside it is printed in full.')
    PATH_FLAGS = ('--root', '--session', '--operation', '--repo', '--service-root', '--input', '--context')

    def base(self):
        from pathlib import Path
        return Path(self.dirs['full']).parent

    def test_the_directory_the_commands_are_typed_from_is_said_once_above_the_first_resume_command(self):
        lines = self.lines('full', relative_to=str(self.base()))
        text = flat(lines)
        self.assertEqual(text.count(self.SENTENCE), 1)
        heading = lines.index('SAVED PROJECTS')
        first = next(i for i, line in enumerate(lines) if line.strip() == 'Resume:')
        said = next(i for i, line in enumerate(lines) if line.strip().startswith('Resume commands are typed from'))
        self.assertTrue(heading < said < first, (heading, said, first))

    def test_what_it_says_is_true_of_the_commands_the_screen_prints(self):
        import shlex
        model = self.model('full', relative_to=str(self.base()))
        checked = 0
        for project in model['projects']:
            if not project['command']:
                continue
            argv = shlex.split(project['command'])
            for flag in self.PATH_FLAGS:
                if flag in argv:
                    value = argv[argv.index(flag) + 1]
                    if value.isupper() or value.startswith('NEW_') or value in ('STORE', 'CONTEXT_JSON'):
                        continue
                    from pathlib import Path
                    self.assertTrue(Path(value).is_absolute() or (self.base() / value).exists(), (flag, value))
                    checked += 1
        self.assertGreater(checked, 3)

    def test_no_resume_command_no_sentence(self):
        self.assertNotIn('Resume commands are typed from', flat(self.lines('offline')))
        self.assertIn('Nothing recognized here yet.', flat(self.lines('offline')))

    def test_a_narrow_pane_still_says_it_once(self):
        for width in (60, 80):
            self.assertEqual(flat(self.lines('full', width=width, relative_to=str(self.base()))).count(self.SENTENCE), 1, width)


class StateWordsTests(Base):
    """Item 6: one legend line under the saved projects, and authentication said the way the goal rows say it (not checked)."""

    def test_one_legend_line_under_the_saved_projects_defines_the_words(self):
        lines = self.lines('full')
        text = flat(lines)
        self.assertEqual(text.count('discovered = '), 1)
        legend = next(i for i, line in enumerate(lines) if line.strip().startswith('Legend: '))
        last_project = max(i for i, line in enumerate(lines) if line.strip().startswith('Resume'))
        self.assertTrue(last_project < legend < lines.index('NEXT ACTION'), (last_project, legend))
        legend_text = flat(lines[legend:lines.index('NEXT ACTION')])
        for word in ('discovered = ', 'usable here = ', 'no live connection = ', 'source-asserted = ', 'synthetic only = ',
                     'not qualified = '):
            self.assertIn(word, legend_text)
        # every word it defines is a word the project rows use
        for word in ('discovered', 'usable here', 'no live connection', 'source-asserted', 'synthetic only', 'not qualified'):
            self.assertIn(word, flat(lines[:legend]), word)

    def test_no_projects_no_legend(self):
        self.assertNotIn('Legend: ', flat(self.lines('offline')))

    def test_authentication_is_not_checked_as_the_goal_rows_say_not_a_flat_negative(self):
        text = flat(self.lines('full'))
        self.assertNotIn('(not authenticated)', text)
        self.assertNotIn('not authenticated', text)
        self.assertIn('this product has no live connection (authentication not checked)', text)
        self.assertIn('source-asserted, authentication not checked', text)
        self.assertIn('authenticated: not checked', text)  # the goal rows' own word

    def test_the_json_form_says_what_the_text_says(self):
        # PKG-CATALOG-6 item 4: the JSON strings no longer keep the flat negative the text replaced (the frozen words live on in
        # entry.STATE_WORDS, which start --json still records)
        model = self.model('full')
        states = ' '.join(project['state'] for project in model['projects'])
        self.assertIn('this product has no live connection (authentication not checked)', states)
        self.assertIn('source-asserted, authentication not checked', states)
        self.assertNotIn('not authenticated', states)

    def test_the_start_screen_uses_the_same_words(self):
        from plugin_tests.test_start_goal import run_cli
        for goal in (None, 'discover'):
            argv = [str(self.dirs['full'])] + ([] if goal is None else ['--goal', goal])
            text = flat(run_cli(*argv, width=120)[1].split('\n'))
            self.assertNotIn('not authenticated', text)
            self.assertIn('this product has no live connection (authentication not checked)', text)
            self.assertIn('discovered | usable here |', text)

    def test_the_words_fit_every_width(self):
        for width in (60, 80, 120):
            for line in self.lines('full', width=width):
                self.assertLessEqual(len(line), width, line)


class CaptureContactTests(Base):
    """Item 7: the next action that prints the capture command says whether capture makes a network request with the token, and
    that it only reads, from what capture.py does (the first test runs it against a recording transport, no network)."""

    TOKEN = 'FAKE-TOKEN-' + 'x9Z' * 8
    TENANT = '11111111-1111-4111-8111-111111111111'
    POLICY = '22222222-2222-4222-8222-222222222222'
    SENTENCE = ('The capture command sends the token to graph.microsoft.com in GET requests only (it reads, and changes nothing '
                'in the tenant) and writes what it reads into the new folder for the output.')

    @unittest.skipUnless(os.name == 'posix', 'capture persists through directory descriptors (POSIX)')
    def test_what_the_screen_says_is_what_capture_does(self):
        import json

        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from urllib.parse import urlsplit
        from intune_iac import capture, readiness
        from intune_iac.identity_binding import ServiceResponse
        seen = []

        class Recording:
            def __call__(self, request, *, timeout, max_bytes):
                seen.append(request)
                listing = request.path.endswith('/configurationPolicies')
                body = {'value': [{'id': CaptureContactTests.POLICY}]} if listing else {'value': []}
                return ServiceResponse(200, (), json.dumps(body).encode())

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'new-folder'
            with patch('intune_iac.identity_binding._NativeTransport', Recording), \
                    patch.dict(os.environ, {'CONTACT_TEST_TOKEN': self.TOKEN}):
                result = capture.capture(self.TENANT, self.POLICY, str(output), token_env='CONTACT_TEST_TOKEN')
            written = sorted(path.name for path in output.iterdir())
        self.assertEqual(result['status'], 'captured')
        self.assertGreaterEqual(len(seen), 3)
        host = urlsplit(capture.GRAPH_ROOT).netloc
        for request in seen:
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.host, host)
            self.assertIs(request.headers.get('Authorization') == 'Bearer ' + self.TOKEN, True)
            self.assertTrue(request.path.startswith(urlsplit(capture.GRAPH_ROOT).path))
            self.assertIsNone(request.body)
        # it writes only into the one new folder it was given
        self.assertEqual(written, ['capture-receipt.json', 'context.json', 'export.json', 'raw'])
        sentence = readiness.capture_contact('Run: intune-iac capture --tenant T --policy P --output NEW_DIR')
        self.assertEqual(sentence, self.SENTENCE)
        self.assertIn(host, sentence)

    def test_the_catalog_says_it_after_the_capture_command_in_the_blocked_row_and_the_next_action(self):
        for fixture in ('context', 'full'):
            lines = self.lines(fixture, 'discover')
            self.assertEqual(flat(lines).count(self.SENTENCE), 2, fixture)
            rows = goal_rows(lines, 'discover')
            self.assertTrue(rows['blocked'].endswith(self.SENTENCE), rows['blocked'])
            # a sentence of its own: the step's closing bracket is followed by a full stop before it begins
            self.assertIn('is another). ' + self.SENTENCE, rows['blocked'])
            entry = next_action_entries(lines)['discover']
            self.assertTrue(flat(entry).endswith(self.SENTENCE), flat(entry))
            # the legend of the command comes first, the sentence follows it
            self.assertLess(flat(entry).index('The capture command'), flat(entry).index(self.SENTENCE))

    def test_a_goal_that_prints_no_capture_command_says_nothing_about_it(self):
        for goal in ('inspect', 'adopt', 'change'):
            self.assertNotIn(self.SENTENCE, flat(self.lines('context', goal)), goal)

    def test_the_start_screen_says_it_too_wherever_it_prints_the_capture_command(self):
        from plugin_tests.test_start_goal import goal_block, run_cli
        _, block = goal_block(run_cli(str(self.dirs['context']), '--goal', 'discover', width=120)[1])
        self.assertIn(self.SENTENCE, flat(block))
        self.assertNotIn(self.SENTENCE, flat(goal_block(run_cli(str(self.dirs['context']), '--goal', 'inspect', width=120)[1])[1]))

    def test_the_sentence_names_no_command_so_a_command_row_is_never_cut(self):
        self.assertNotIn('intune-iac ', self.SENTENCE)

    def test_the_recorded_next_action_and_its_legend_stay_as_the_json_form_carries_them(self):
        from intune_iac import readiness
        model = readiness.readiness(tc.survey(tc.tr.context_item()), tc.tr.host_report(), tc.doctor())
        action = next(row for row in model['operations']['discover']['rows'] if row['id'] == 'integration_service')['next_action']
        self.assertIn('reads the named variable; one of the explicit-token routes, target collect is another)', action)
        self.assertNotIn('graph.microsoft.com', action)


class DirectoryInCommandTests(Base):
    """Round 2, item 1: the surveyed directory is named in the printed start command only when the PKG-SETUP-5D output rule accepts it
    (signin_facts.output_display: printable, within its limit, not credential-shaped as a whole or in any of its pieces). Otherwise
    the placeholder DIRECTORY stands for it, and the note says once, in the same words for every rejection, that it is not shown."""

    NOT_SHOWN = 'DIRECTORY is the directory this screen is about; its name is not shown here; '
    # label: (the surveyed directory, the pieces of it that must never be printed)
    REJECTED = {
        'a token prefix as a folder name': ('/tmp/work/ghp_abc1234', ('ghp_', 'abc1234')),
        'a token prefix at the end of a windows path': ('C:\\work\\ghp_abc1234', ('ghp_', 'abc1234')),
        'a bearer value': ('/tmp/work/Bearer ' + 'Qx7' * 10, ('Bearer', 'Qx7')),
        'a jwt-shaped piece': ('/tmp/work/eyJhbGciOiJIUzI1NiJ9.e30.c2ln/ctx', ('eyJ', 'c2ln', 'hbGci')),
        'an unbroken run of letters and digits': ('/tmp/work/' + 'a1' * 14, ('a1a1a1',)),
        'an escape': ('/tmp/work/a\x1b[31mb', ('\x1b', '[31m')),
        'a carriage return': ('/tmp/work/a\rb', ('\r',)),
        'a line feed': ('/tmp/work/a\nb', ('\n',)),
        'a name longer than the display limit': ('/tmp/' + '/'.join(['abcdefghij'] * 25), ('abcdefghij',)),
    }

    def recorded(self, goal='discover'):
        from intune_iac import readiness
        return readiness.NO_CHECK_RECORDED % goal

    def test_a_rejected_directory_is_never_in_the_command_and_the_note_says_once_that_it_is_not_shown(self):
        from intune_iac import readiness
        for label, (directory, forbidden) in self.REJECTED.items():
            with self.subTest(label):
                note = note_for(directory)
                self.assertIn('run: intune-iac start DIRECTORY --goal discover --check-signin azure (' + self.NOT_SHOWN, note)
                self.assertEqual(note.count('not shown'), 1)
                self.assertTrue(note.startswith('No sign-in check was run. To look for an existing Azure sign-in, run: '))
                self.assertTrue(note.endswith('it runs az account list --output json and nothing else).'))
                for fragment in forbidden:
                    self.assertNotIn(fragment, note)

    def test_every_rejection_reads_the_same_so_the_screen_does_not_say_which_rule_applied(self):
        from intune_iac import readiness
        notes = {note_for(directory) for directory, _ in self.REJECTED.values()}
        self.assertEqual(len(notes), 1, notes)

    def test_an_ordinary_directory_prints_exactly_as_before(self):
        from intune_iac import readiness
        for directory in ('/tmp/work/context dir', '/home/someone/estate', 'C:\\work\\estate dir', '/tmp/x.y/z', '/tmp/' + 'a' * 23,
                          '/tmp/Bearer', '/tmp/ghp'):
            note = note_for(directory)
            self.assertEqual(note, GarbledSentenceTests('sentence').sentence('discover', directory), directory)
            self.assertNotIn('not shown', note)
        # no directory at all (a survey that names none): the command without one, as the first round printed it
        self.assertEqual(readiness.screen_note(self.recorded()), GarbledSentenceTests('sentence').sentence('discover'))

    def test_the_catalog_and_the_start_screen_print_the_placeholder_for_a_credential_shaped_directory(self):
        import shutil
        import tempfile
        from pathlib import Path
        from intune_iac import catalog as module, entry
        from plugin_tests.test_start_goal import ROOT, goal_block, run_cli
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / 'ghp_abc1234'
            directory.mkdir()
            shutil.copyfile(ROOT / 'examples/context.json', directory / 'context.json')
            lines = tc.text_of(module.build(entry.survey(directory), doctor=tc.doctor(), goal='discover'), 120)
            rows = goal_rows(lines, 'discover')
            # a screen says once, under its header, that the name is not shown (round 3). The catalog prints no command for a
            # directory it may not show (PKG-CATALOG-6: DIRECTORY is a valid relative path); nor does the start screen
            # (PKG-START-STANDIN): both say it in the same words
            self.assertIn(HIDDEN_NOTE, rows['blocked'])
            self.assertNotIn('start DIRECTORY', rows['blocked'])
            self.assertNotIn('ghp_', rows['blocked'])
            self.assertEqual(flat(lines).count('its name is not shown here'), 1)
            text = run_cli(str(directory), '--goal', 'discover', width=120)[1]
            _, block = goal_block(text)
            start = next(i for i, line in enumerate(block) if line.startswith('  Integration and service: '))
            stop = next(i for i, line in enumerate(block) if line.startswith('  Exceptional secret input: '))
            row = flat(block[start:stop])
            self.assertIn(HIDDEN_NOTE, row)
            self.assertNotIn('start DIRECTORY', row)
            self.assertNotIn('ghp_', row)
            self.assertEqual(flat(text.split('\n')).count('its name is not shown here'), 1)

    def test_a_directory_named_with_an_escape_gets_the_same_placeholder_end_to_end(self):
        import shutil
        import tempfile
        from pathlib import Path
        from intune_iac import catalog as module, entry
        from plugin_tests.test_start_goal import ROOT
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / 'odd\x1b[31mname'
            try:
                directory.mkdir()
            except OSError:
                self.skipTest('this file system refuses a control byte in a name')
            shutil.copyfile(ROOT / 'examples/context.json', directory / 'context.json')
            rows = goal_rows(tc.text_of(module.build(entry.survey(directory), doctor=tc.doctor(), goal='discover'), 120), 'discover')
            self.assertIn(HIDDEN_NOTE, rows['blocked'])
            self.assertNotIn('\x1b', rows['blocked'])


class CaptureCommandPositionTests(Base):
    """Round 2, item 2: the capture sentence follows the capture command where it stands as a command, never a substring of the
    rendered text, so a path such as /tmp/intune-iac capture decoy inside another command does not claim a token is sent."""

    SENTENCE = CaptureContactTests.SENTENCE
    DECOY_ACTION = ("Run: intune-iac catalog '/tmp/intune-iac capture decoy' --goal adopt --check-signin azure (it runs az account "
                    "list --output json and nothing else).")

    def test_a_program_name_inside_a_quoted_path_is_not_a_command(self):
        from intune_iac import readiness
        for text in ("intune-iac catalog '/tmp/intune-iac capture decoy' --check-signin azure",
                     self.DECOY_ACTION,
                     "Run: intune-iac start '/work/a b/intune-iac capture x' --goal discover --check-signin azure",
                     'Directory: /tmp/intune-iac capture decoy',
                     'Look in the intune-iac capture decoy folder.'):
            self.assertEqual(readiness.capture_contact(text), '', text)
            self.assertNotIn('capture', readiness.command_names(text), text)

    def test_the_command_names_of_a_step_are_read_where_a_command_stands(self):
        from intune_iac import readiness
        self.assertEqual(readiness.command_names("intune-iac catalog '/tmp/intune-iac capture decoy' --check-signin azure"), ['catalog'])
        self.assertEqual(readiness.command_names('Then: intune-iac capture --tenant T --policy POLICY'), ['capture'])
        self.assertEqual(readiness.command_names('Choose one tenant, then run: intune-iac start DIRECTORY. Then: intune-iac capture --tenant T'),
                         ['start', 'capture'])
        self.assertEqual(readiness.command_names('Provide the read token only to this one command: intune-iac capture --tenant T'),
                         ['capture'])
        self.assertEqual(readiness.command_names('No command here.'), [])
        self.assertEqual(readiness.command_names('intune-iac'), [])

    def test_the_three_places_the_model_prints_the_capture_command_still_get_the_sentence(self):
        from intune_iac import readiness
        legend = '(POLICY is the policy id, a GUID; NEW_DIR is a folder that does not exist yet)'
        step = 'intune-iac capture --tenant 11111111-1111-4111-8111-111111111111 --policy POLICY --output NEW_DIR --token-env X ' + legend
        for text in (step, 'Choose one tenant, then run: intune-iac start DIRECTORY. Then: ' + step,
                     'Provide the read token only to this one command: ' + step + '.'):
            self.assertEqual(readiness.capture_contact(text), self.SENTENCE, text)

    def test_a_catalog_whose_next_action_only_names_the_decoy_gets_no_sentence(self):
        import copy
        # plain data: a catalog built here prints from its text build, so a hand-made one is a plain dict (no text build)
        value = dict(copy.deepcopy(self.model('full')))
        for goal in value['integrations'][0]['goals']:
            if goal['goal'] == 'discover':
                goal['blocked']['next_action'] = goal['next_action'] = self.DECOY_ACTION
        lines = tc.text_of(value, 120)
        self.assertNotIn(self.SENTENCE, flat(lines))
        self.assertIn('decoy', flat(lines))  # the action was rendered; only the sentence is absent
        # the unchanged catalog still says it, in the blocked row and in the next action
        self.assertEqual(flat(self.lines('full')).count(self.SENTENCE), 2)

    def test_a_start_screen_whose_next_action_only_names_the_decoy_gets_no_sentence(self):
        from intune_iac.entry import goal_readiness, start_lines, survey
        value = survey(self.dirs['context'])
        view = goal_readiness(value, 'discover')
        # the integration row and the secret row each print the capture command, and each gets the sentence
        self.assertEqual(flat(start_lines(value, 120, view)).count(self.SENTENCE), 2)
        for row in view['rows']:
            if row['needed']:
                row['next_action'] = self.DECOY_ACTION
        self.assertNotIn(self.SENTENCE, flat(start_lines(value, 120, view)))


class DirectoryEchoTests(Base):
    """Round 3: every text place that prints the surveyed directory (the catalog's header, start's header, start's Directory: line
    and the catalog pointer at the end of start) applies the rule that guards the output path of signin collect
    (signin_facts.output_display). A refused name prints as DIRECTORY, and each screen says once, under its header, that the name
    is not shown. An ordinary directory prints exactly as before."""

    SAID = 'DIRECTORY is the directory this screen is about; its name is not shown here.'
    # label: (the name of the folder to survey, or None for a path over the display limit; the pieces that must never be printed)
    NAMES = {
        'a token prefix': ('ghp_abc1234', ('ghp_', 'abc1234')),
        'a bearer value': ('Bearer ' + 'Qx7' * 10, ('Bearer', 'Qx7')),
        'a jwt-shaped piece': ('eyJhbGciOiJIUzI1NiJ9.e30.c2ln', ('eyJ', 'c2ln', 'hbGci')),
        'an unbroken run': ('a1' * 14, ('a1a1a1',)),
        'an escape': ('xx9\x1b[31myy9', ('\x1b', 'xx9', 'yy9')),
        'a carriage return': ('xx9\ryy9', ('\r', 'xx9', 'yy9')),
        'a line feed': ('xx9\nyy9', ('xx9', 'yy9')),
        'a path over the display limit': (None, ('abcdefghij',)),
    }
    START_HEADER = 'DIRECTORY | offline (no live connection) | synthetic evidence stays labelled synthetic'
    CATALOG_HEADER = 'DIRECTORY | offline | this lists only what this build holds'

    def folder(self, temp, name):
        """A folder that holds only the example context (it names a tenant), named as the case says; None when the file system
        refuses the name."""
        import shutil
        from pathlib import Path
        from plugin_tests.test_start_goal import ROOT
        directory = Path(temp) / ('/'.join(['abcdefghij'] * 25) if name is None else name)
        try:
            directory.mkdir(parents=True)
        except OSError:
            return None
        shutil.copyfile(ROOT / 'examples/context.json', directory / 'context.json')
        return directory

    def cli(self, *argv, width=120):
        import contextlib
        import io
        from unittest.mock import patch
        from intune_iac import cli
        out = io.StringIO()
        with patch('shutil.get_terminal_size', return_value=os.terminal_size((width, 40))), contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, out.getvalue()

    NEXT_ROW = re.compile(r'^(    [a-z-]+:|  GOAL |[A-Z])')

    def outside_authenticated_rows(self, lines):
        """The lines of a catalog screen without its `authenticated` rows. Their sign-in command carries the directory in the
        recorded message (authenticated.message in catalog --json, a frozen form), which this round leaves as it is; a name with a
        line feed even breaks that row over several lines, so the row runs to the next state row."""
        kept, inside = [], False
        for line in lines:
            if line.startswith('    authenticated:'):
                inside = True
                continue
            if inside and not self.NEXT_ROW.match(line):
                continue
            inside = False
            kept.append(line)
        return kept

    @staticmethod
    def blocked_row(lines, goal):
        """The text of one goal's blocked row, read without the state-row parser (the authenticated row above it may be broken)."""
        start = lines.index('  GOAL ' + goal)
        at = next(index for index in range(start, len(lines)) if lines[index].startswith('    blocked:'))
        parts = [lines[at].split(':', 1)[1]]
        for line in lines[at + 1:]:
            if not line.startswith(' ' * 21):
                break
            parts.append(line)
        return ' '.join(' '.join(parts).split())

    def each(self, check):
        """check(folder, the pieces that must never be printed) for every refused name, each as its own sub-test."""
        import tempfile
        for label, (name, forbidden) in self.NAMES.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as temp:
                directory = self.folder(temp, name)
                if directory is None:
                    self.skipTest('this file system refuses that name')
                check(directory, forbidden)

    def start_screen(self, directory, *extra):
        from plugin_tests.test_start_goal import run_cli
        code, text = run_cli(str(directory), *extra, width=120)
        self.assertEqual(code, 0)
        return text, text.split('\n')

    def catalog_screen(self, directory):
        code, text = self.cli('catalog', str(directory))
        self.assertEqual(code, 0)
        return text, text.split('\n')

    def test_place_1_the_catalog_header_prints_the_placeholder_and_the_statement_under_it(self):
        def check(directory, forbidden):
            _, lines = self.catalog_screen(directory)
            self.assertEqual(lines[:4], ['INTEGRATION CATALOG', self.CATALOG_HEADER, self.SAID,
                                         'No other integration is available in this build.'])
        self.each(check)

    def test_place_2_the_start_header_prints_the_placeholder_and_the_statement_under_it(self):
        def check(directory, forbidden):
            for extra in ((), ('--goal', 'discover')):
                _, lines = self.start_screen(directory, *extra)
                self.assertEqual(lines[:3], ['INTUNE WORKBENCH: START', self.START_HEADER, self.SAID], extra)
        self.each(check)

    def test_place_3_the_directory_line_of_a_goal_screen_prints_the_placeholder(self):
        def check(directory, forbidden):
            _, lines = self.start_screen(directory, '--goal', 'discover')
            self.assertIn('Directory: DIRECTORY', lines)
        self.each(check)

    def test_place_4_the_catalog_pointer_at_the_end_of_start_prints_the_placeholder(self):
        from plugin_tests.test_start_goal import StartGoalTests

        def check(directory, forbidden):
            for extra in ((), ('--goal', 'discover')):
                _, lines = self.start_screen(directory, *extra)
                commands = [line.strip() for line in StartGoalTests('logical_lines').logical_lines(lines)]
                # PKG-START-STANDIN: the pointer says the catalog command in words; DIRECTORY would be a real folder to a shell
                self.assertNotIn('intune-iac catalog DIRECTORY', commands, extra)
                self.assertIn('Catalog of what this build supports and where each goal stands: the catalog command with this '
                              'directory (the directory cannot be shown here)', flat(lines), extra)
        self.each(check)

    def test_the_notes_command_names_the_placeholder_on_both_screens(self):
        from plugin_tests.test_start_goal import StartGoalTests

        def check(directory, forbidden):
            _, lines = self.start_screen(directory, '--goal', 'discover')
            commands = [line.strip() for line in StartGoalTests('logical_lines').logical_lines(lines)]
            # PKG-START-STANDIN: the start screen says it in the catalog's words, as the catalog does (PKG-CATALOG-6)
            self.assertNotIn('intune-iac start DIRECTORY --goal discover --check-signin azure', commands)
            self.assertIn(HIDDEN_NOTE, flat(lines))
            _, lines = self.catalog_screen(directory)
            self.assertIn(HIDDEN_NOTE, self.blocked_row(lines, 'discover'))
        self.each(check)

    def test_each_screen_says_once_that_the_name_is_not_shown_and_prints_no_piece_of_it(self):
        def check(directory, forbidden):
            for text, lines in (self.start_screen(directory), self.start_screen(directory, '--goal', 'discover')):
                self.assertEqual(text.count('its name is not shown here'), 1)
                for fragment in forbidden:
                    self.assertNotIn(fragment, text)
            text, lines = self.catalog_screen(directory)
            self.assertEqual(text.count('its name is not shown here'), 1)
            kept = '\n'.join(self.outside_authenticated_rows(lines))
            for fragment in forbidden:
                self.assertNotIn(fragment, kept)
        self.each(check)

    def test_an_ordinary_directory_is_printed_as_before_and_nothing_says_a_name_is_not_shown(self):
        import tempfile
        from plugin_tests.test_start_goal import StartGoalTests, run_cli
        with tempfile.TemporaryDirectory() as temp:
            directory = self.folder(temp, 'estate dir')
            quoted = "'%s'" % directory
            code, text = run_cli(str(directory), '--goal', 'discover', width=120)
            lines = text.split('\n')
            self.assertEqual(lines[1], '%s | offline (no live connection) | synthetic evidence stays labelled synthetic' % directory)
            self.assertIn('Directory: %s' % directory, lines)
            commands = [line.strip() for line in StartGoalTests('logical_lines').logical_lines(lines)]
            self.assertIn('intune-iac start %s --goal discover --check-signin azure' % quoted, commands)
            self.assertIn('intune-iac catalog %s' % quoted, commands)
            self.assertNotIn('not shown', text)
            code, text = self.cli('catalog', str(directory))
            lines = text.split('\n')
            self.assertEqual(lines[:3], ['INTEGRATION CATALOG', '%s | offline | this lists only what this build holds' % directory,
                                         'No other integration is available in this build.'])
            self.assertNotIn('not shown', text)


class TerminalSafetyTests(Base):
    """Round 4: nothing the surveyed directory or the surveyed files are called can reach the terminal as a control byte, and a
    directory name the output-path rule refuses is shown as DIRECTORY in every printed copy of it (the authenticated rows, the
    resume commands and start's next steps too). The data the text comes from is never edited: the --json forms stay byte for byte."""

    # label: (the folder's name, the pieces of it that must never be printed)
    NAMES = {
        'an escape': ('xx9\x1b[31myy9', ('xx9', 'yy9')),
        'a carriage return': ('xx9\ryy9', ('xx9', 'yy9')),
        'a line feed': ('xx9\nyy9', ('xx9', 'yy9')),
        'a C1 character': ('xx9\x85yy9', ('xx9', 'yy9')),
        'a C1 control sequence introducer': ('xx9\x9b31myy9', ('xx9', 'yy9')),
        'a token prefix': ('ghp_abc1234', ('ghp_', 'abc1234')),
    }
    GOALS = ('inspect', 'discover', 'adopt', 'change')

    @staticmethod
    def raw_output(cwd, *argv):
        """(exit code, the bytes the command wrote to stdout) of the real command line, typed from cwd, at 120 columns."""
        import contextlib
        import io
        from unittest.mock import patch
        from intune_iac import cli
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding='utf-8', newline='', write_through=True)
        old = os.getcwd()
        os.chdir(cwd)
        try:
            with patch('shutil.get_terminal_size', return_value=os.terminal_size((120, 40))), contextlib.redirect_stdout(stream):
                code = cli.main(list(argv))
            stream.flush()
        finally:
            os.chdir(old)
        return code, buffer.getvalue()

    def assert_no_control_byte(self, data, label):
        """No C0 character but the newline that ends a row, no DEL and no C1 character in the bytes (read as UTF-8)."""
        text = data.decode('utf-8')
        bad = sorted({hex(ord(char)) for char in text if (ord(char) < 32 and char != '\n') or ord(char) == 127 or 0x80 <= ord(char) <= 0x9f})
        self.assertEqual(bad, [], label)
        return text

    def estate_in(self, parent, name):
        """A copy of the start tests' full estate (a store, a session, a repository, an export ...: every kind that prints a resume
        command and a next step) in a folder of that name; None when the file system refuses the name."""
        import shutil
        from pathlib import Path
        target = Path(parent) / name
        try:
            shutil.copytree(self.dirs['full'], target)
        except OSError:
            return None
        return target

    def test_no_control_byte_reaches_stdout_from_a_directory_name_in_any_screen_and_the_name_is_shown_as_directory(self):
        import tempfile
        for label, (name, forbidden) in self.NAMES.items():
            for cwd_kind in ('the parent', 'an unrelated directory'):
                with self.subTest(label, cwd=cwd_kind), tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as elsewhere:
                    folder = self.estate_in(temp, name)
                    if folder is None:
                        self.skipTest('this file system refuses that name')
                    cwd = temp if cwd_kind == 'the parent' else elsewhere
                    screens = {'catalog': self.raw_output(cwd, 'catalog', str(folder))[1]}
                    for goal in self.GOALS:
                        screens['catalog --goal ' + goal] = self.raw_output(cwd, 'catalog', str(folder), '--goal', goal)[1]
                    screens['start'] = self.raw_output(cwd, 'start', str(folder))[1]
                    for goal in self.GOALS:
                        screens['start --goal ' + goal] = self.raw_output(cwd, 'start', str(folder), '--goal', goal)[1]
                    for screen, data in screens.items():
                        text = self.assert_no_control_byte(data, screen)
                        for fragment in forbidden:
                            self.assertNotIn(fragment, text, screen)
                    # the printed copies that carry the directory say DIRECTORY (read across the wrapped rows)
                    catalog = flat(screens['catalog'].decode('utf-8').split('\n'))
                    # PKG-CATALOG-6: the catalog prints no command with a stand-in for the directory, in the authenticated rows
                    # or in the resume commands; it says what is missing. The start screen below does the same (PKG-START-STANDIN).
                    self.assertNotIn('catalog DIRECTORY', catalog)
                    self.assertNotIn('DIRECTORY/', catalog)
                    self.assertIn('run the catalog command with this directory and --check-signin azure '
                                  '(the directory cannot be shown here', catalog)
                    self.assertIn('Resume with the workbench workspace command using this saved store; its path cannot be shown here.',
                                  catalog)
                    start = flat(screens['start'].decode('utf-8').split('\n'))
                    self.assertNotIn('DIRECTORY/', start)                                                 # the next steps, in words
                    self.assertIn(OPEN_WORKSPACE_WORDS, start)
                    self.assertIn('Resume with the wizard command using this saved session; its path cannot be shown here.', start)
                    self.assertIn('See the policies the repository holds with the workbench repository-entry command using this '
                                  'repository; its path cannot be shown here.', start)

    def test_an_ordinary_folder_keeps_every_path_it_prints(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            folder = self.estate_in(temp, 'estate dir')
            _, data = self.raw_output(temp, 'catalog', str(folder))
            text = flat(data.decode('utf-8').split('\n'))
            self.assertNotIn('DIRECTORY', text)
            self.assertIn("intune-iac workbench workspace --root 'estate dir/store' --service-root 'estate dir/service'", text)
            self.assertIn("intune-iac catalog 'estate dir' --check-signin azure", text)  # round 6: the writer's operand, relative to cwd
            _, data = self.raw_output(temp, 'start', str(folder))
            self.assertNotIn('DIRECTORY', data.decode('utf-8'))

    def test_a_control_character_in_the_name_of_a_surveyed_file_is_never_sent_and_the_name_is_shown_as_PATH(self):
        """Round 4 showed such a name as an escape in its row; round 5 writes it PATH in the rows as in the commands, so the
        sentence that says PATH is a name not shown here is true of the whole screen (nothing of the name is printed)."""
        import shutil
        import tempfile
        from pathlib import Path
        from plugin_tests.test_start_goal import ROOT
        for label, name, shown in (('an escape', 'ex\x1b[31mport.json', 'ex\\u001b[31mport.json'),
                                   ('a C1 character', 'ex\x85port.json', 'ex\\u0085port.json'),
                                   ('a carriage return', 'ex\rport.json', 'ex\\rport.json'),
                                   ('a line feed', 'ex\nport.json', 'ex\\nport.json')):
            with self.subTest(label), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp) / 'work'
                folder.mkdir()
                shutil.copyfile(ROOT / 'examples/context.json', folder / 'context.json')
                try:
                    shutil.copyfile(ROOT / 'examples/supported/input/export.json', folder / name)
                except OSError:
                    self.skipTest('this file system refuses that name')
                for argv in (('catalog', str(folder)), ('start', str(folder))):
                    text = self.assert_no_control_byte(self.raw_output(temp, *argv)[1], argv)
                    self.assertNotIn(shown, text, argv)
                    self.assertNotIn('port.json', text, argv)
                    self.assertEqual(text.count('PATH is a path in this directory whose name is not shown here.'), 1, argv)
                    self.assertRegex(text, r'Export\s+PATH[: ]', argv)


class OperandRenderingTests(Base):
    """Round 5: the text form builds its commands from their path operands. A path operand at or under a refused directory is
    written DIRECTORY plus the remainder before any quoting; an operand that terminal escaping would change is written as a
    placeholder; the relative_to the builder was given is the one the text uses. The JSON forms keep their rendering."""

    PATH_FLAGS = ('--root', '--session', '--operation', '--repo', '--service-root', '--input', '--context')
    PATH_SAID = 'PATH is a path in this directory whose name is not shown here.'

    def estate_in(self, parent, *names):
        """A copy of the start tests' full estate in parent/names (a store, a session, a repository, an export ...); None when
        the file system refuses a name."""
        import shutil
        from pathlib import Path
        target = Path(parent).joinpath(*names)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(self.dirs['full'], target)
        except OSError:
            return None
        return target

    def screens(self, cwd, folder):
        """{what was typed: the screen} for catalog and start, all goals, typed from cwd, read from the raw stdout bytes."""
        raw = TerminalSafetyTests.raw_output
        shown = {'catalog': raw(cwd, 'catalog', str(folder))[1].decode('utf-8'),
                 'start': raw(cwd, 'start', str(folder))[1].decode('utf-8')}
        for goal in GOALS:
            shown['catalog --goal ' + goal] = raw(cwd, 'catalog', str(folder), '--goal', goal)[1].decode('utf-8')
            shown['start --goal ' + goal] = raw(cwd, 'start', str(folder), '--goal', goal)[1].decode('utf-8')
        return shown

    def command_rows(self, text):
        from plugin_tests.test_start_goal import StartGoalTests
        joined = StartGoalTests('logical_lines').logical_lines(text.split('\n'))
        return [row.strip() for row in joined if row.strip().startswith('intune-iac ')]

    def test_a_refused_directory_whose_own_name_needs_shell_quoting_is_replaced_before_the_quoting(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as elsewhere:
            folder = self.estate_in(temp, 'ghp_abc1234', "o'connor")
            for cwd in (temp, elsewhere):
                shown = self.screens(cwd, folder)
                for label, text in shown.items():
                    for fragment in ('ghp_', 'abc1234', 'connor'):
                        self.assertNotIn(fragment, text, (cwd == temp, label))
                self.assertNotIn('DIRECTORY/', flat(shown['start'].split('\n')), 'start')  # PKG-START-STANDIN
                self.assertIn(OPEN_WORKSPACE_WORDS, flat(shown['start'].split('\n')), 'start')
                self.assertNotIn('DIRECTORY/', flat(shown['catalog'].split('\n')), 'the catalog prints no stand-in command')

    def test_the_relative_to_the_build_was_given_is_the_one_the_text_uses_not_the_working_directory(self):
        import os
        import tempfile
        from intune_iac import catalog as module, entry
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as elsewhere:
            hidden = self.estate_in(temp, 'ghp_abc1234')
            ordinary = self.estate_in(temp, 'estate dir')
            old = os.getcwd()
            os.chdir(elsewhere)
            try:
                for folder, refused in ((hidden, True), (ordinary, False)):
                    survey = entry.survey(folder, relative_to=temp)
                    value = module.build(survey, doctor=tc.doctor(), relative_to=temp)
                    catalog = flat(module.catalog_lines(value, 120))
                    start = flat(entry.start_lines(survey, 120))
                    if refused:
                        self.assertNotIn('ghp_', catalog + start)
                        self.assertNotIn('DIRECTORY/', catalog)  # PKG-CATALOG-6: no stand-in inside a catalog command
                        self.assertNotIn('DIRECTORY/', start)  # PKG-START-STANDIN: no stand-in inside a start command either
                        self.assertIn(OPEN_WORKSPACE_WORDS, start)
                    else:  # written for temp, where the paths are relative to it
                        self.assertIn("intune-iac workbench workspace --root 'estate dir/store'", catalog)
                        self.assertIn("intune-iac workbench workspace --root 'estate dir/store'", start)
            finally:
                os.chdir(old)

    def test_an_operand_that_terminal_escaping_would_change_is_a_placeholder_never_an_escaped_copy(self):
        import shutil
        import tempfile
        from pathlib import Path
        from plugin_tests.test_start_goal import ROOT
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as elsewhere:
            # the directory itself: printable, not credential-shaped, but its accent is a combining mark
            folder = self.estate_in(temp, 'café')
            for cwd in (temp, elsewhere):
                for label, text in self.screens(cwd, folder).items():
                    for row in self.command_rows(text):
                        self.assertNotIn('\\u0301', row, (label, row))
                        self.assertNotIn('cafe', row, (label, row))
                    self.assertNotIn('cafe', text, label)
                shown = self.screens(cwd, folder)
                self.assertNotIn('DIRECTORY/', flat(shown['catalog'].split('\n')))  # PKG-CATALOG-6
                self.assertNotIn('DIRECTORY/', flat(shown['start'].split('\n')))  # PKG-START-STANDIN
                self.assertIn(OPEN_WORKSPACE_WORDS, flat(shown['start'].split('\n')))
                self.assertEqual(shown['start'].count('its name is not shown here'), 1)
            # a surveyed file: an operand inside an ordinary folder
            work = Path(temp) / 'work'
            work.mkdir()
            shutil.copyfile(ROOT / 'examples/context.json', work / 'context.json')
            shutil.copyfile(ROOT / 'examples/supported/input/export.json', work / 'ex́port.json')
            for label, text in self.screens(temp, work).items():
                for row in self.command_rows(text):
                    self.assertNotIn('\\u0301', row, (label, row))
            catalog = self.screens(temp, work)['catalog']
            self.assertNotIn('--input PATH', flat(catalog.split('\n')))   # round 2: no stand-in operand in a catalog command
            self.assertEqual(catalog.count(self.PATH_SAID), 1)

    def test_aliases_and_spellings_of_a_refused_directory_are_replaced_too(self):
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as elsewhere:
            folder = self.estate_in(temp, 'ghp_abc1234')
            (Path(temp) / 'other').mkdir()
            backslash = self.estate_in(temp, 'win\\ghp_abc1234')
            spellings = {'a .. alias': os.path.join(temp, 'other', '..', 'ghp_abc1234'), 'a trailing slash': str(folder) + '/',
                         'a backslash in the name': str(backslash)}
            for label, spelling in spellings.items():
                for cwd in (temp, elsewhere):
                    for what, text in self.screens(cwd, spelling).items():
                        self.assertNotIn('ghp_', text, (label, what))
                        self.assertNotIn('abc1234', text, (label, what))

    def test_every_command_a_screen_prints_for_copying_parses_back_to_the_surveyed_paths(self):
        import contextlib
        import io
        import os
        import shlex
        import tempfile
        from pathlib import Path
        from intune_iac import cli, entry
        from plugin_tests.test_catalog_json_golden import build_estate
        parser = cli.parser()
        checked = operands = 0
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as elsewhere:
            folders = {'the journey 33 estate': build_estate(temp), 'the start tests estate': self.estate_in(temp, 'full estate'),
                       'a name with an apostrophe': self.estate_in(temp, "o'connor"),
                       'a name with a space and a dollar sign': self.estate_in(temp, 'a b$c')}
            for label, folder in folders.items():
                targets = {os.path.realpath(folder / item['path']) for item in entry.survey(folder)['items']}
                for cwd in (temp, elsewhere):
                    for what, text in self.screens(cwd, folder).items():
                        for row in self.command_rows(text):
                            argv = shlex.split(row)
                            self.assertEqual(argv[0], 'intune-iac', row)
                            with contextlib.redirect_stderr(io.StringIO()) as err:
                                try:
                                    parser.parse_args(['3' if word == 'FD' else word for word in argv[1:]])
                                except SystemExit:
                                    self.fail('the product parser rejects %r (%s)\n%s' % (row, label, err.getvalue()))
                            checked += 1
                            if argv[1] in ('catalog', 'start') and len(argv) > 2 and not argv[2].startswith('-'):
                                self.assertEqual(os.path.realpath(os.path.join(cwd, argv[2])), os.path.realpath(folder), (label, what, row))
                                operands += 1
                            for flag in self.PATH_FLAGS:
                                if flag in argv:
                                    operand = argv[argv.index(flag) + 1]
                                    if operand.isupper() or operand.startswith('NEW_') or operand in ('STORE', 'CONTEXT_JSON'):
                                        continue
                                    self.assertIn(os.path.realpath(os.path.join(cwd, operand)), targets, (label, what, row))
                                    operands += 1
            type(self).round_trip_counts = (checked, operands)  # for the report: how many commands and operands were read back
            self.assertGreater(checked, 200)
            self.assertGreater(operands, 100)

    def test_the_text_build_has_the_json_builds_judgments_and_only_its_path_strings_differ(self):
        import copy
        import tempfile
        from intune_iac import catalog as module, entry

        def judged(value):
            """The build without the strings that carry paths: every state and verdict stays."""
            value = copy.deepcopy(dict(value))
            for key in ('directory', 'directory_hidden', 'directory_operand'):  # the text build holds the directory as a screen says it
                value.pop(key, None)
            for project in value['projects']:
                # a command the screen may not print says why in its note (PKG-CATALOG-6); the commands themselves are path strings
                project['command'] = project['path'] = None
                said = project['note'] == module.COMMAND_NOT_SHOWN or (project['note'] or '').startswith(module.RESUME_WORDS)
                project['note'] = None if said else project['note']
            for goal in value['integrations'][0]['goals']:
                goal['authenticated']['message'] = goal['next_action'] = None
                goal['blocked']['next_action'] = goal['blocked']['missing'] = None  # recorded strings; the states beside them stay
            return value

        def surveyed(survey):
            """The survey without the strings that carry paths: every item, state and note stays."""
            survey = copy.deepcopy(dict(survey))
            for key in ('directory', 'directory_hidden', 'directory_operand'):
                survey.pop(key, None)
            survey['next_actions'] = survey['skipped_links'] = None
            for item in survey['items']:
                item['path'] = None
            return survey

        import shutil
        from pathlib import Path
        from plugin_tests.test_start_goal import ROOT
        with tempfile.TemporaryDirectory() as temp:
            named = Path(temp) / 'work'
            named.mkdir()
            shutil.copyfile(ROOT / 'examples/context.json', named / 'context.json')
            shutil.copyfile(ROOT / 'examples/supported/input/export.json', named / 'ghp_abc1234.json')
            folders = {'a refused item name': named, 'ordinary': self.estate_in(temp, 'estate dir'),
                       'refused': self.estate_in(temp, 'ghp_abc1234'),
                       'accent': self.estate_in(temp, 'café')}
            for label, folder in folders.items():
                survey = entry.survey(folder, relative_to=temp)
                value = module.build(survey, doctor=tc.doctor(), relative_to=temp)
                text = value.text_build
                self.assertEqual(judged(value), judged(text), label)
                self.assertEqual(surveyed(survey), surveyed(survey.text_build), label)
                self.assertEqual(len(survey['next_actions']), len(survey.text_build['next_actions']), label)
                self.assertEqual(len(survey['items']), len(survey.text_build['items']), label)
                # the screen says the same states and verdicts as the data
                lines = module.catalog_lines(value, 120)
                for goal in value['integrations'][0]['goals']:
                    rows = goal_rows(lines, goal['goal'])
                    self.assertEqual(rows['operation-ready'], module._ready_words(goal), (label, goal['goal']))
                    self.assertTrue(rows['blocked'].startswith(module._blocked_words(goal)), (label, goal['goal']))
                    self.assertTrue(rows['authenticated'].startswith(goal['authenticated']['state'].replace('_', ' ')), (label, goal['goal']))
                    self.assertIn('Verdict: ' + module.verdict_words(goal), flat(lines))

    def test_plain_data_that_crossed_a_json_boundary_prints_as_the_built_data_does_or_shows_less(self):
        """A result that was written as JSON and read back is plain data: it has no text build. The screens then print the
        recorded strings when the directory is shown and every word of a command passes the display rule; for a directory the
        screen may not show they print no command (the operands are not at hand to write DIRECTORY plus the remainder)."""
        import json
        import tempfile
        from intune_iac import catalog as module, entry
        with tempfile.TemporaryDirectory() as temp:
            for name, refused in (('estate dir', False), ("o'connor", False), ('ghp_abc1234', True), ('cafe' + chr(0x301), True)):
                folder = self.estate_in(temp, name)
                survey = entry.survey(folder, relative_to=temp)
                value = module.build(survey, doctor=tc.doctor(), relative_to=temp)
                plain_value, plain_survey = json.loads(json.dumps(value)), json.loads(json.dumps(survey))
                self.assertIs(type(plain_value), dict)
                self.assertIs(type(plain_survey), dict)
                built = (module.catalog_lines(value, 120), entry.start_lines(survey, 120))
                plain = (module.catalog_lines(plain_value, 120), entry.start_lines(plain_survey, 120))
                if not refused:
                    # the same screens; the only difference is the directory operand of the sign-in command, the note and the pointer:
                    # the builders write it relative to where the command runs, plain data (no relative_to) has it in full
                    import os
                    import shlex
                    absolute, relative = shlex.quote(str(folder)), shlex.quote(os.path.relpath(folder, temp))
                    for shown_plain, shown_built in zip(plain, built):
                        self.assertEqual(flat(shown_plain).replace(absolute, relative), flat(shown_built), name)
                    continue
                shown = '\n'.join(plain[0] + plain[1])
                for fragment in ('ghp_', 'abc1234', 'cafe', '\\u0301', chr(0x301)):
                    self.assertNotIn(fragment, shown, (name, fragment))
                self.assertNotIn('catalog DIRECTORY', flat(plain[0]), name)  # PKG-CATALOG-6: words, never a stand-in command
                self.assertIn('run the catalog command with this directory and --check-signin azure (the directory cannot be shown here',
                              flat(plain[0]), name)
                self.assertIn('Resume: no command (the command names a path whose name is not shown here)', flat(plain[0]), name)
                self.assertIn('A next step names a path whose name is not shown here.', flat(plain[1]), name)

    def test_plain_data_prints_no_command_with_an_operand_the_display_rule_refuses_even_in_a_shown_directory(self):
        import json
        import shutil
        import tempfile
        from pathlib import Path
        from intune_iac import catalog as module, entry
        from plugin_tests.test_start_goal import ROOT
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / 'work'
            work.mkdir()
            shutil.copyfile(ROOT / 'examples/context.json', work / 'context.json')
            shutil.copyfile(ROOT / 'examples/supported/input/export.json', work / ('ex' + chr(0x301) + 'port.json'))
            survey = entry.survey(work, relative_to=temp)
            value = module.build(survey, doctor=tc.doctor(), relative_to=temp)
            plain_value, plain_survey = json.loads(json.dumps(value)), json.loads(json.dumps(survey))
            screens = {'catalog': module.catalog_lines(plain_value, 120), 'start': entry.start_lines(plain_survey, 120)}
            for label, lines in screens.items():
                for row in self.command_rows('\n'.join(lines)):
                    self.assertNotIn(chr(0x301), row, (label, row))
                    self.assertNotIn('\\u0301', row, (label, row))
            self.assertIn('A next step names a path whose name is not shown here.', flat(screens['start']))
            self.assertIn('Resume: no command (the command names a path whose name is not shown here)', flat(screens['catalog']))

    def test_an_item_name_the_display_rule_refuses_is_the_placeholder_in_the_rows_as_in_the_commands(self):
        """The sentence 'PATH is a path in this directory whose name is not shown here' must be true of the whole screen: the
        FOUND and SAVED PROJECTS rows and the skipped links say PATH too, not only the commands."""
        import json
        import re
        import shutil
        import tempfile
        from pathlib import Path
        from intune_iac import catalog as module, entry
        from plugin_tests.test_start_goal import ROOT
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / 'work'
            work.mkdir()
            shutil.copyfile(ROOT / 'examples/context.json', work / 'context.json')
            shutil.copyfile(ROOT / 'examples/supported/input/export.json', work / 'ghp_abc1234.json')
            screens = self.screens(temp, work)  # the real command line, raw stdout
            for label, text in screens.items():
                self.assertNotIn('ghp_', text, label)
                self.assertNotIn('abc1234', text, label)
            self.assertEqual(screens['catalog'].count(self.PATH_SAID), 1)
            self.assertEqual(screens['start'].count(self.PATH_SAID), 1)
            self.assertIn('Export PATH:', screens['catalog'])
            self.assertTrue(re.search(r'Export\s+PATH\s+synthetic', screens['start']), screens['start'][:400])
            # plain data (written as JSON and read back) prints the same rows
            survey = entry.survey(work, relative_to=temp)
            value = module.build(survey, doctor=tc.doctor(), relative_to=temp)
            plain = '\n'.join(module.catalog_lines(json.loads(json.dumps(value)), 120) +
                              entry.start_lines(json.loads(json.dumps(survey)), 120))
            self.assertNotIn('ghp_', plain)
            self.assertNotIn('abc1234', plain)
            # the JSON forms keep the recorded name
            self.assertIn('ghp_abc1234.json', json.dumps(value))
            self.assertIn('ghp_abc1234.json', json.dumps(survey))

    # -- round 6, item 1: plain data (a result that is not the builders' own) ---------------------------------------------------
    EXPLANATION = 'A next step names a path whose name is not shown here.'

    def plain_pair(self, temp, *names):
        """(a catalog, a survey, the folder) of a copy of the start tests' estate; the first two as plain data (written as JSON and
        read back)."""
        import json
        from intune_iac import catalog as module, entry
        folder = self.estate_in(temp, *names)
        survey = entry.survey(folder, relative_to=temp)
        value = module.build(survey, doctor=tc.doctor(), relative_to=temp)
        return json.loads(json.dumps(value)), json.loads(json.dumps(survey)), folder

    def test_a_plain_goal_next_action_with_an_operand_the_rule_refuses_is_not_printed_as_a_command(self):
        import tempfile
        from intune_iac import catalog as module
        planted = "Run: intune-iac workbench workspace --root '/tmp/cafe" + chr(0x301) + "'"
        with tempfile.TemporaryDirectory() as temp:
            value, _, _ = self.plain_pair(temp, 'work')
            goal = value['integrations'][0]['goals'][0]
            goal['next_action'] = planted
            goal['blocked'] = dict(goal['blocked'], state='blocked', row='Planted row', row_state='missing', missing=None,
                                   next_action=planted)
            lines = module.catalog_lines(value, 120)
            shown = '\n'.join(lines)
            for fragment in ('cafe', chr(0x301), '\\u0301'):
                self.assertNotIn(fragment, shown, fragment)
            self.assertGreaterEqual(flat(lines).count(self.EXPLANATION), 2)  # the blocked row and the next action
            # a step that names nothing refused stays as recorded
            goal['next_action'] = 'Run: intune-iac workbench workspace --root store'
            self.assertIn('intune-iac workbench workspace --root store', flat(module.catalog_lines(value, 120)))

    def test_a_plain_not_checked_sign_in_message_is_written_again_from_the_directory_even_when_it_is_shown(self):
        import shlex
        import tempfile
        from intune_iac import catalog as module
        planted = ("Sign-in is not checked. Run: intune-iac catalog '/tmp/cafe" + chr(0x301) + "' --check-signin azure (it runs az "
                   "account list --output json and nothing else, and reads no token).")
        with tempfile.TemporaryDirectory() as temp:
            value, _, folder = self.plain_pair(temp, 'work')
            for goal in value['integrations'][0]['goals']:
                self.assertEqual(goal['authenticated']['state'], 'not_checked')
                goal['authenticated']['message'] = planted
            shown = '\n'.join(module.catalog_lines(value, 120))
            for fragment in ('cafe', chr(0x301), '\\u0301'):
                self.assertNotIn(fragment, shown, fragment)
            self.assertIn('intune-iac catalog %s --check-signin azure' % shlex.quote(str(folder)),
                          flat(module.catalog_lines(value, 120)))

    def test_a_plain_readiness_view_prints_no_step_or_note_with_an_operand_the_rule_refuses(self):
        import tempfile
        from intune_iac import entry
        planted = "Run: intune-iac workbench workspace --root '/tmp/cafe" + chr(0x301) + "'"
        with tempfile.TemporaryDirectory() as temp:
            _, survey, _ = self.plain_pair(temp, 'work')
            view = entry.goal_readiness(survey, 'adopt')
            needed = [row for row in view['rows'] if row['needed']]
            needed[0]['state'], needed[0]['missing'], needed[0]['next_action'] = 'missing', [planted], planted
            needed[1]['next_action'] = 'Run: intune-iac start DIRECTORY'  # names nothing refused: in words (a placeholder)
            lines = entry.start_lines(survey, 120, view)
            shown = '\n'.join(lines)
            for fragment in ('cafe', chr(0x301), '\\u0301'):
                self.assertNotIn(fragment, shown, fragment)
            self.assertGreaterEqual(flat(lines).count(self.EXPLANATION), 2)  # the note and the next action of the planted row
            self.assertIn('Run: the start command, naming the directory to survey', flat(lines))

    def test_a_plain_catalog_of_a_refused_directory_prints_neither_the_directory_nor_a_step_that_names_it(self):
        import tempfile
        from intune_iac import catalog as module
        with tempfile.TemporaryDirectory() as temp:
            value, _, folder = self.plain_pair(temp, 'ghp_abc1234')
            goals = value['integrations'][0]['goals']
            goals[0]['next_action'] = "Run: intune-iac workbench workspace --root '%s'" % (folder / 'store')
            goals[1]['next_action'] = 'No action needed.'
            lines = module.catalog_lines(value, 120)
            shown = '\n'.join(lines)
            for fragment in ('ghp_', 'abc1234'):
                self.assertNotIn(fragment, shown, fragment)
            self.assertIn(self.EXPLANATION, flat(lines))
            self.assertIn('No action needed.', flat(lines))  # a step that names nothing is not hidden with the others

    # -- round 6, item 2: persistence ----------------------------------------------------------------------------------------------
    def test_persistence_rebuilds_a_plain_dict_and_keeps_none_of_the_text_build(self):
        # pickle is used here only to round-trip values this test builds itself, in memory; no file or untrusted data is loaded
        import copy
        import pickle
        import tempfile
        from intune_iac import catalog as module, entry
        with tempfile.TemporaryDirectory() as temp:
            folder = self.estate_in(temp, 'ghp_abc1234')
            survey = entry.survey(folder, relative_to=temp)
            value = module.build(survey, doctor=tc.doctor(), relative_to=temp)
            for label, original in (('survey', survey), ('catalog', value)):
                clones = [pickle.loads(pickle.dumps(original, protocol)) for protocol in range(0, pickle.HIGHEST_PROTOCOL + 1)]
                clones += [copy.copy(original), copy.deepcopy(original)]  # copy and shelve use the same reduction as pickle
                for clone in clones:
                    self.assertIs(type(clone), dict, label)
                    self.assertEqual(clone, dict(original), label)
                    self.assertFalse(hasattr(clone, 'text_build'), label)
                    self.assertFalse(hasattr(clone, 'text_placeholders'), label)
            # a persisted value prints through the plain-data path: nothing of the refused name
            shown = '\n'.join(module.catalog_lines(pickle.loads(pickle.dumps(value)), 120) +
                              entry.start_lines(pickle.loads(pickle.dumps(survey)), 120))
            for fragment in ('ghp_', 'abc1234'):
                self.assertNotIn(fragment, shown, fragment)
            # while the builders' own value still prints from its text build
            self.assertNotIn('DIRECTORY/', flat(entry.start_lines(survey, 120)))  # PKG-START-STANDIN: words, not a stand-in
            self.assertIn(OPEN_WORKSPACE_WORDS, flat(entry.start_lines(survey, 120)))

    # -- round 6, item 3: one writer for every command operand ------------------------------------------------------------------
    def test_the_note_the_pointer_and_the_sign_in_command_are_written_relative_to_relative_to_like_the_actions(self):
        import tempfile
        from intune_iac import catalog as module, entry
        with tempfile.TemporaryDirectory() as base:
            folder = self.estate_in(base, 'estate dir')
            survey = entry.survey(folder, relative_to=base)
            seen = {'note': 0, 'pointer': 0, 'sign-in': 0, 'action': 0}
            for goal in GOALS:
                start = entry.start_lines(survey, 120, entry.goal_readiness(survey, goal))
                catalog = module.catalog_lines(module.build(survey, doctor=tc.doctor(), goal=goal, relative_to=base), 120)
                for label, lines in (('start', start), ('catalog', catalog)):
                    for row in self.command_rows('\n'.join(lines)):
                        self.assertNotIn(str(folder), row, (goal, label, row))  # no command names the directory in full
                    text = flat(lines)
                    seen['action'] += "intune-iac workbench workspace --root 'estate dir/store'" in text
                    seen['note'] += "intune-iac start 'estate dir' --goal %s --check-signin azure" % goal in text
                    seen['pointer'] += label == 'start' and "intune-iac catalog 'estate dir'" in text
                    seen['sign-in'] += "intune-iac catalog 'estate dir' --goal %s --check-signin azure" % goal in text
            for what, count in seen.items():
                self.assertGreater(count, 0, what)

    def test_without_a_relative_to_the_pointer_and_the_note_keep_the_directory_in_full(self):
        import shlex
        import tempfile
        from intune_iac import entry
        with tempfile.TemporaryDirectory() as base:
            folder = self.estate_in(base, 'estate dir')
            survey = entry.survey(folder)
            text = flat(entry.start_lines(survey, 120, entry.goal_readiness(survey, 'adopt')))
            self.assertIn('intune-iac catalog %s' % shlex.quote(str(folder)), text)
            self.assertIn('intune-iac start %s --goal adopt --check-signin azure' % shlex.quote(str(folder)), text)

    def test_a_text_build_holds_the_directory_as_a_screen_says_it_never_the_refused_name(self):
        import json
        import tempfile
        from intune_iac import catalog as module, entry
        with tempfile.TemporaryDirectory() as temp:
            folder = self.estate_in(temp, 'ghp_abc1234')
            survey = entry.survey(folder, relative_to=temp)
            value = module.build(survey, doctor=tc.doctor(), relative_to=temp)
            for built in (survey.text_build, value.text_build):
                self.assertEqual(built['directory'], 'DIRECTORY')
                self.assertNotIn('ghp_abc1234', json.dumps(built))
            ordinary = self.estate_in(temp, 'estate dir')
            self.assertEqual(entry.survey(ordinary, relative_to=temp).text_build['directory'], str(ordinary))

    def test_the_json_forms_keep_today_rendering_for_a_refused_directory(self):
        import tempfile
        from intune_iac import catalog as module, entry
        with tempfile.TemporaryDirectory() as temp:
            folder = self.estate_in(temp, 'ghp_abc1234')
            survey = entry.survey(folder, relative_to=temp)
            value = module.build(survey, doctor=tc.doctor(), relative_to=temp)
            self.assertIn('--root ghp_abc1234/store', ' '.join(p['command'] for p in value['projects'] if p['command']))
            self.assertIn('--root ghp_abc1234/store', ' '.join(survey['next_actions']))
            self.assertIn(str(folder), value['integrations'][0]['goals'][0]['authenticated']['message'])


if __name__ == '__main__':
    unittest.main()
