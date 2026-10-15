"""start lays NEXT out as steps: one sentence says what to do, and the command follows on its own rows.

A wrapped command breaks between arguments and every row but the last ends with a backslash, so
copying the rows runs one command. Commands are parsed with the product parser, never run.
"""
import contextlib
import io
import re
import unittest

from plugin_tests.test_start_goal import Fixtures, run_cli
from plugin_tests.test_start_paths import commands_in, logical_lines, next_section


def command_rows(lines):
    """Every command printed on rows of its own, as argument lists, a wrapped one rejoined across its backslashes."""
    found = []
    for line in logical_lines(lines):
        if line.strip().startswith('intune-iac '):
            found += commands_in(line.strip())
    return found


class StartStepsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dirs = Fixtures.get()

    def parse(self, argv):
        from intune_iac import cli
        with contextlib.redirect_stderr(io.StringIO()) as err:
            try:
                return cli.parser().parse_args(['3' if token == 'FD' else token for token in argv])
            except SystemExit:
                self.fail('the product parser rejects: intune-iac %s\n%s' % (' '.join(argv), err.getvalue()))

    def test_next_puts_each_command_on_its_own_rows(self):
        for fixture in self.dirs:
            for width in (50, 80, 120):
                code, text = run_cli(str(self.dirs[fixture]), width=width)
                lines = next_section(text)
                self.assertTrue(lines or fixture == 'context', fixture)
                for line in lines:
                    if 'intune-iac ' in line:
                        self.assertTrue(line.strip().startswith('intune-iac '), (fixture, width, line))
                self.assertFalse([c for c in text if ord(c) < 0x20 and c != '\n'])

    def test_a_step_is_one_sentence_then_its_command(self):
        code, text = run_cli(str(self.dirs['offline']), width=100)
        lines = next_section(text)
        steps = [i for i, line in enumerate(lines) if re.match(r'  \d\. ', line)]
        for index in steps:
            self.assertTrue(lines[index].rstrip().endswith(':'), lines[index])
            self.assertTrue(lines[index + 1].strip().startswith('intune-iac '), lines[index:index + 2])

    def test_an_empty_directory_has_a_step_per_command(self):
        code, text = run_cli(str(self.dirs['offline']), width=100)
        lines = next_section(text)
        steps = [line for line in lines if re.match(r'  \d\. ', line)]
        self.assertEqual(len(steps), 3, lines)
        commands = command_rows(lines)
        self.assertEqual([c[:2] for c in commands], [['wizard', '--session'], ['workbench', 'init'], ['workbench', 'repository-entry']])
        for argv in commands:
            self.parse(argv)

    def test_a_repository_with_no_store_says_to_create_one_first(self):
        code, text = run_cli(str(self.dirs['repository']), width=100)
        commands = command_rows(next_section(text))
        names = [c[:2] for c in commands]
        self.assertIn(['workbench', 'init'], names)
        self.assertLess(names.index(['workbench', 'init']), names.index(['workbench', 'repository-entry']))
        for argv in commands:
            self.parse(argv)

    def test_a_wrapped_command_ends_its_rows_with_a_backslash_and_rejoins_to_one_command(self):
        code, text = run_cli(str(self.dirs['offline']), width=50)
        lines = next_section(text)
        wrapped = [i for i, line in enumerate(lines) if line.endswith(' \\')]
        self.assertTrue(wrapped)
        for index in wrapped:
            self.assertTrue(lines[index + 1].startswith(' ' * 4), lines[index:index + 2])
        self.assertFalse(lines[-1].endswith('\\'))
        for row in lines:
            self.assertLessEqual(len(row), 50, row)
        for argv in command_rows(lines):
            self.parse(argv)

    def test_every_next_command_parses_for_each_fixture(self):
        checked = 0
        for fixture in self.dirs:
            for width in (50, 120):
                code, text = run_cli(str(self.dirs[fixture]), width=width)
                for line in logical_lines(next_section(text)):
                    if line.strip().startswith('intune-iac '):
                        for argv in commands_in(line.strip()):
                            self.parse(argv)
                            checked += 1
        self.assertGreater(checked, 8)

    def test_the_goal_block_still_follows_next(self):
        code, text = run_cli(str(self.dirs['full']), '--goal', 'adopt')
        self.assertLess(text.index('NEXT'), text.index('GOAL READINESS: adopt'))

    def test_the_json_next_actions_stay_sentences_with_the_command_in_them(self):
        import json
        code, text = run_cli(str(self.dirs['offline']), '--json')
        actions = json.loads(text)['next_actions']
        self.assertEqual(len(actions), 3)
        self.assertTrue(all('intune-iac ' in action for action in actions))


def tearDownModule():
    Fixtures.release()


if __name__ == '__main__':
    unittest.main()
