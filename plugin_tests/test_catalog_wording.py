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


if __name__ == '__main__':
    unittest.main()
