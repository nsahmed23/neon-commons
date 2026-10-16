"""Archive creation needs a known, clean Git state, and what is archived is bound to the one commit the receipt names
(PKG-RELEASE-1 round 4). Real temporary repositories, with the fixture and the secret-shaped test data of test_release_hardening
(values are built at run time and never written out whole)."""
import contextlib
import io
import json
import shutil
import sys
import unittest
from unittest.mock import patch

from plugin_tests import test_release_candidate as base
from plugin_tests import test_release_hardening as hard

builder = base.builder
sha256 = base.sha256
ALLOWANCE = 'release-sensitive-allow.txt'


def check_only(repo):
    """What `--check-only` prints for the repository: it may report a state that --output-dir refuses."""
    with patch.object(builder, 'ROOT', repo.root), patch.object(builder, 'runtime_files', return_value=['README.md']), \
            patch.object(sys, 'argv', ['build-release.py', '--check-only']), contextlib.redirect_stdout(io.StringIO()) as out:
        builder.main()
    return json.loads(out.getvalue())


class GitCase(unittest.TestCase):
    def setUp(self):
        if not shutil.which('git'):
            self.skipTest('git is not available here')

    def refusal(self, repo):
        """The message of the ValueError `--output-dir` raises for the repository; a build that succeeds or crashes fails the test."""
        try:
            repo.build()
        except ValueError as refused:
            return str(refused)
        except Exception as other:
            self.fail(f'expected a refusal, got {other!r}')
        self.fail('the archives were made')

    def assertNothingMade(self, repo):
        self.assertFalse(repo.output.exists(), 'the output folder was created')


class CleanStateTests(GitCase):
    """Item 1: `--output-dir` refuses unless the commit is known, git reports no tracked change and no captured file differs from
    the commit. `--check-only` may still report such a state."""

    def test_a_tracked_edit_refuses_the_archives_and_check_only_reports_it(self):
        repo = hard.GitFixture(self)
        (repo.root / 'README.md').write_text('edited after the commit\n')
        message = self.refusal(repo)
        self.assertIn('clean checkout', message)
        self.assertIn('README.md', message)
        self.assertNothingMade(repo)
        checkout = check_only(repo)['checkout']
        self.assertIs(checkout['dirty'], True)
        self.assertEqual((checkout['differing_files'], checkout['commit']), (['README.md'], repo.git('rev-parse', 'HEAD')))

    def test_a_change_that_git_status_hides_refuses_the_archives_too(self):
        repo = hard.GitFixture(self)
        repo.git('update-index', '--assume-unchanged', 'NOTES.md')
        (repo.root / 'NOTES.md').write_text('changed, and hidden from git status\n')
        self.assertEqual(repo.git('status', '--porcelain', '--untracked-files=no'), '', 'git status shows nothing')
        self.assertIn('NOTES.md', self.refusal(repo))
        self.assertNothingMade(repo)
        self.assertEqual(check_only(repo)['checkout']['differing_files'], ['NOTES.md'])

    def test_an_edit_to_a_tracked_file_outside_the_inventory_refuses_the_archives_too(self):
        repo = hard.GitFixture(self)
        (repo.root / 'OTHER.md').write_text('tracked, not inventoried\n')
        repo.commit('add a tracked file the inventory does not name')
        (repo.root / 'OTHER.md').write_text('edited after the commit\n')
        self.assertIn('clean checkout', self.refusal(repo))
        self.assertNothingMade(repo)
        checkout = check_only(repo)['checkout']
        self.assertEqual((checkout['dirty'], checkout['differing_files']), (True, []))

    def test_an_unknown_commit_refuses_the_archives_but_not_the_check(self):
        for name in ('inside another repository', 'outside any repository'):
            with self.subTest(name):
                repo = hard.GitFixture(self, nested=True)
                if name.startswith('inside'):
                    repo.git('init', '-q', '-b', 'main', root=repo.parent)       # the folder above the project is the repository
                    repo.git('add', '-A', root=repo.parent)
                    repo.git('commit', '-q', '-m', 'outer', root=repo.parent)
                self.assertIn('known Git state', self.refusal(repo))
                self.assertNothingMade(repo)
                self.assertIsNone(check_only(repo)['checkout']['commit'])

    def test_an_uncommitted_allowance_cannot_authorize_a_planted_value(self):
        for name, plant_committed in (('the value and the allowance are both uncommitted', False),
                                      ('the value is committed and only the allowance is uncommitted', True)):
            with self.subTest(name):
                repo = hard.GitFixture(self)
                (repo.root / 'docs').mkdir()
                (repo.root / 'docs/notes.txt').write_text('plain notes\n')
                (repo.root / ALLOWANCE).write_text('# reviewed allowances\n')
                (repo.root / 'release-source-files.txt').write_text(
                    f'README.md\nNOTES.md\ndocs/notes.txt\n{ALLOWANCE}\nrelease-source-files.txt\n')
                if plant_committed:
                    (repo.root / 'docs/notes.txt').write_bytes(hard.SHAPES['jwt']())
                repo.commit('the reviewed inventory and an allowance file without entries')
                (repo.root / 'docs/notes.txt').write_bytes(hard.SHAPES['jwt']())
                (repo.root / ALLOWANCE).write_text(
                    f'docs/notes.txt | {sha256((repo.root / "docs/notes.txt").read_bytes())} | jwt | a made-up value used by a test\n')
                message = self.refusal(repo)
                self.assertIn(ALLOWANCE, message)
                self.assertNothingMade(repo)
                report = check_only(repo)
                self.assertIn(ALLOWANCE, report['checkout']['differing_files'])
                self.assertTrue(all(item['allowed'] for item in report['sensitive_content']['findings']))


if __name__ == '__main__':
    unittest.main()
