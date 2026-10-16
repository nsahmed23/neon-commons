"""start prints commands whose paths work from the directory it was run in.

Directories are built with the product's own routes (the entry tests' builder). The command
line is called as a function with the current directory changed (and restored). A printed
command is parsed with the product parser and each path argument is resolved from the current
directory; no command is run.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import tempfile
import unittest

from plugin_tests.test_start_goal import Fixtures, run_cli

STOP_WORDS = frozenset({'and', 'then', 'or', 'from', 'to', 'with', 'for', 'as', 'that', 'is', 'the', 'in', 'on', 'by'})
TOKEN = re.compile(r"(?:'[^']*'|[^\s'])+")


def commands_in(text):
    """Each intune-iac command in a sentence as an argument list, quotes removed, cut where the sentence goes on."""
    commands = []
    for chunk in text.split('intune-iac ')[1:]:
        tokens = []
        for token in TOKEN.findall(chunk):
            if token.lower() in STOP_WORDS or token.startswith('('):
                break
            if set(token) == {'.'}:
                # A path such as . or .. is an argument, not sentence punctuation.
                tokens.append(token)
                continue
            tokens.append(token.rstrip('.,;:'))
            if token[-1] in '.,;:)':
                break
        commands.append(shlex.split(' '.join(tokens)))
    return commands


def logical_lines(lines):
    """Rows joined across trailing backslashes, so a wrapped command is one line again."""
    out, current = [], None
    for line in lines:
        current = line if current is None else current + ' ' + line.strip()
        if current.endswith(' \\'):
            current = current[:-2]
            continue
        out.append(current)
        current = None
    assert current is None, 'the last row of a command ends with a backslash'
    return out


def next_section(text):
    """The rows under the NEXT heading; none when there is no heading (PKG-SETUP-5C: start prints no empty NEXT)."""
    lines = text.split('\n')
    if 'NEXT' not in lines:
        return []
    start = lines.index('NEXT')
    end = next(i for i in range(start + 1, len(lines)) if lines[i] and not lines[i].startswith(' '))
    return lines[start + 1:end]


class StartPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dirs = Fixtures.get()
        cls.work = cls.dirs['full']
        cls.base = cls.work.parent

    def setUp(self):
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.base)

    def parse(self, argv):
        from intune_iac import cli
        with contextlib.redirect_stderr(io.StringIO()) as err:
            try:
                return cli.parser().parse_args(['3' if token == 'FD' else token for token in argv])
            except SystemExit:
                self.fail('the product parser rejects: intune-iac %s\n%s' % (' '.join(argv), err.getvalue()))

    def commands_of(self, value):
        found = []
        for action in value['next_actions']:
            found += commands_in(action)
        return found

    def test_when_the_surveyed_directory_is_the_current_one_the_actions_are_unchanged(self):
        from intune_iac.entry import survey
        os.chdir(self.work)
        code, text = run_cli(str(self.work), '--json')
        actions = json.loads(text)['next_actions']
        self.assertEqual(actions, survey(self.work)['next_actions'])
        self.assertIn('intune-iac workbench workspace --root store', '\n'.join(actions))

    def test_a_directory_below_the_current_one_prints_paths_relative_to_it(self):
        code, text = run_cli(str(self.work), '--json')
        workspace = next(c for c in self.commands_of(json.loads(text)) if c[:2] == ['workbench', 'workspace'])
        args = self.parse(workspace)
        self.assertEqual(args.root, 'work/store')
        self.assertTrue(os.path.samefile(args.root, self.work / 'store'))

    def test_every_path_in_every_printed_command_resolves_to_the_surveyed_object(self):
        targets = (('root', self.work / 'store'), ('service_root', self.work / 'service'),
                   ('session', self.work / 'session.json'), ('repo', self.work / 'repository'))
        for cwd in (self.base, self.base.parent, self.work / 'store'):
            os.chdir(cwd)
            code, text = run_cli(str(self.work), '--json')
            self.assertEqual(code, 0)
            checked = 0
            for argv in self.commands_of(json.loads(text)):
                args = self.parse(argv)
                for name, target in targets:
                    value = getattr(args, name, None)
                    if not isinstance(value, str) or value in ('STORE', 'SERVICE_ROOT', 'REPOSITORY'):
                        continue
                    self.assertTrue(os.path.exists(value), (str(cwd), argv))
                    self.assertTrue(os.path.samefile(value, target), (str(cwd), argv, value))
                    checked += 1
            self.assertGreater(checked, 2, str(cwd))

    def test_a_directory_outside_the_current_one_prints_absolute_paths(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            os.chdir(elsewhere)
            code, text = run_cli(str(self.work), '--json')
            workspace = next(c for c in self.commands_of(json.loads(text)) if c[:2] == ['workbench', 'workspace'])
            self.assertEqual(self.parse(workspace).root, str(self.work / 'store'))

    def test_the_screen_prints_the_same_paths_as_the_json(self):
        code, text = run_cli(str(self.work))
        joined = ' '.join(' '.join(logical_lines(next_section(text))).split())
        self.assertIn('intune-iac workbench workspace --root work/store', joined)

    def test_a_path_with_a_space_is_quoted_and_still_resolves(self):
        with tempfile.TemporaryDirectory() as temp:
            spaced = Path(temp) / 'my work'
            spaced.mkdir()
            shutil.copytree(self.work / 'store', spaced / 'my store')
            os.chdir(temp)
            actions = '\n'.join(json.loads(run_cli(str(spaced), '--json')[1])['next_actions'])
            self.assertIn("--root 'my work/my store'", actions)
            workspace = next(c for c in commands_in(actions) if c[:2] == ['workbench', 'workspace'])
            args = self.parse(workspace)
            self.assertEqual(args.root, 'my work/my store')
            self.assertTrue(os.path.samefile(args.root, spaced / 'my store'))
            os.chdir(spaced)
            actions = '\n'.join(json.loads(run_cli(str(spaced), '--json')[1])['next_actions'])
            self.assertIn("--root 'my store'", actions)

    def test_a_repository_at_the_root_names_the_path_start_was_run_on(self):
        code, text = run_cli(str(self.work / 'repository'), '--json')
        found = [c for a in json.loads(text)['next_actions'] for c in commands_in(a) if c[:2] == ['workbench', 'repository-entry']]
        self.assertTrue(found)
        args = self.parse(found[0])
        self.assertEqual(args.repo, 'work/repository')
        self.assertTrue(os.path.samefile(args.repo, self.work / 'repository'))
        os.chdir(self.work / 'repository')
        code, text = run_cli(str(self.work / 'repository'), '--json')
        found = [c for a in json.loads(text)['next_actions'] for c in commands_in(a) if c[:2] == ['workbench', 'repository-entry']]
        self.assertEqual(self.parse(found[0]).repo, '.')

    def test_the_json_items_keep_their_paths_relative_to_the_surveyed_directory(self):
        code, text = run_cli(str(self.work), '--json')
        paths = {item['path'] for item in json.loads(text)['items']}
        self.assertIn('store', paths)
        self.assertIn('repository', paths)


def tearDownModule():
    Fixtures.release()


if __name__ == '__main__':
    unittest.main()
