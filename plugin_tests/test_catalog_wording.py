"""PKG-CATALOG-5: the catalog's wording on a 40-row pane and the words a fresh engineer reads (journey 33 run 1, reviews A and B).

Every change here is in the text form. The `--json` form is frozen (test_catalog_json_golden): the same recorded data, said in
better words on the screen. The working directories are the ones the start tests build, with the product's own routes.
"""
import copy
import re
import unittest

from plugin_tests import test_catalog as tc
from plugin_tests.test_start_goal import Fixtures, tearDownModule  # noqa: F401  (tearDownModule is the module hook)

GOALS = ('inspect', 'discover', 'adopt', 'change')
WIDTH = 120
PANE = 39  # the visible rows of a 40-row pane: the shell prompt takes the last one
ENTRY = re.compile(r'^  (inspect|discover|adopt|change):$')


def flat(lines):
    """Rows as one string: a command's trailing backslash dropped, runs of spaces made one."""
    return ' '.join(' '.join(lines).replace(' \\ ', ' ').split())


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
            self.assertIn('    ' + verdict, entry, (fixture, goal, name, 'no verdict line beside the next action in the last rows'))
            self.assertLessEqual(len(verdict) + 4, WIDTH)
            after = entry[entry.index('    ' + verdict) + 1:]
            self.assertIn(flat([item['next_action']]), flat(after), (fixture, goal, name))
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
                    self.assertEqual(rows['unsupported'], 'nothing recorded as unsupported in this build.')

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

    def sentence(self, goal):
        return ('No sign-in check was run. To look for an existing Azure sign-in, run: intune-iac start --goal %s --check-signin '
                'azure (it runs az account list --output json and nothing else).' % goal)

    def test_the_catalog_says_it_in_two_sentences_with_the_command_on_its_own_rows(self):
        for width in (120, 100):
            # a context names the tenant, so the blocked row shows the sign-in note first (an empty directory shows the tenant note)
            lines = self.lines('context', 'discover', width=width)
            self.assertIn(self.sentence('discover'), flat(lines), width)
            self.assertNotIn('start with --goal', flat(lines))
            self.assertNotIn('was run:', flat(lines))
            rows = [line.strip() for line in lines]
            self.assertIn('intune-iac start --goal discover --check-signin azure', rows, width)

    def test_the_start_screen_says_it_the_same_way_for_every_goal_that_needs_a_sign_in(self):
        from plugin_tests.test_start_goal import goal_block, run_cli
        for goal in ('discover', 'adopt', 'change'):
            for width in (60, 100, 120):
                code, text = run_cli(str(self.dirs['offline']), '--goal', goal, width=width)
                self.assertEqual(code, 0)
                _, block = goal_block(text)
                self.assertIn(self.sentence(goal), flat(block), (goal, width))
                self.assertNotIn('start with --goal', flat(block))
                # on its own rows: a command wider than the pane breaks between arguments, each row but the last ending in a backslash
                from plugin_tests.test_start_goal import StartGoalTests
                commands = [line.strip() for line in StartGoalTests('logical_lines').logical_lines(block)]
                self.assertIn('intune-iac start --goal %s --check-signin azure' % goal, commands, (goal, width))

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
                wanted = ['start', '--goal', goal, '--check-signin', 'azure']
                self.assertIn(wanted, commands, (goal, width))
                with contextlib.redirect_stderr(io.StringIO()):
                    args = parser.parse_args(wanted)
                self.assertEqual((args.command, args.goal, args.check_signin), ('start', goal, 'azure'))

    def test_the_recorded_note_is_unchanged_because_the_json_form_is_frozen(self):
        from intune_iac import readiness
        model = readiness.readiness(tc.survey(), tc.tr.host_report(), tc.doctor())
        for goal in ('discover', 'adopt', 'change'):
            row = next(row for row in model['operations'][goal]['rows'] if row['id'] == 'integration_service')
            recorded = readiness.NO_CHECK_RECORDED % goal
            self.assertIn(recorded, row['missing'])
            self.assertEqual(readiness.screen_note(recorded), self.sentence(goal))
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
        legend = next(i for i, line in enumerate(lines) if line.strip().startswith('Words used above: '))
        last_project = max(i for i, line in enumerate(lines) if line.strip().startswith('Resume'))
        self.assertTrue(last_project < legend < lines.index('NEXT ACTION'), (last_project, legend))
        legend_text = flat(lines[legend:lines.index('NEXT ACTION')])
        for word in ('discovered = ', 'usable here = ', 'no live connection = ', 'synthetic only = ', 'not qualified = '):
            self.assertIn(word, legend_text)

    def test_no_projects_no_legend(self):
        self.assertNotIn('Words used above', flat(self.lines('offline')))

    def test_authentication_is_not_checked_as_the_goal_rows_say_not_a_flat_negative(self):
        text = flat(self.lines('full'))
        self.assertNotIn('(not authenticated)', text)
        self.assertNotIn('not authenticated', text)
        self.assertIn('this product has no live connection (authentication not checked)', text)
        self.assertIn('source-asserted, authentication not checked', text)
        self.assertIn('authenticated: not checked', text)  # the goal rows' own word

    def test_the_recorded_words_stay_in_the_json_form(self):
        model = self.model('full')
        states = ' '.join(project['state'] for project in model['projects'])
        self.assertIn('this product has no live connection (not authenticated)', states)
        self.assertIn('source-asserted, not authenticated', states)

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


if __name__ == '__main__':
    unittest.main()
