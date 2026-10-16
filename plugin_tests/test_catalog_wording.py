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


if __name__ == '__main__':
    unittest.main()
