"""Archive creation needs a known, clean Git state, and what is archived is bound to the one commit the receipt names
(PKG-RELEASE-1 round 4). Real temporary repositories, with the fixture and the secret-shaped test data of test_release_hardening
(values are built at run time and never written out whole)."""
import contextlib
import io
import json
import shutil
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from plugin_tests import test_release_candidate as base
from plugin_tests import test_release_hardening as hard

builder = base.builder
sha256 = base.sha256
ALLOWANCE = 'release-sensitive-allow.txt'


def check_only(repo):
    """What `--check-only` prints for a repository fixture, or for a folder given as a path: it may report a state that
    --output-dir refuses."""
    root = repo if isinstance(repo, Path) else repo.root
    with patch.object(builder, 'ROOT', root), patch.object(builder, 'runtime_files', return_value=['README.md']), \
            patch.object(sys, 'argv', ['build-release.py', '--check-only']), contextlib.redirect_stdout(io.StringIO()) as out:
        try:
            builder.main()
        except ValueError as refused:
            raise AssertionError(f'--check-only refused a tree it may report on: {refused}') from None
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


class CapturedStateTests(GitCase):
    """Item 2: the allowance file is read once, as one of the captured files, and the binding lists the commit that was captured."""

    def committed_with_allowance(self):
        repo = hard.GitFixture(self)
        (repo.root / ALLOWANCE).write_text('# reviewed allowances\n')
        (repo.root / 'release-source-files.txt').write_text(f'README.md\nNOTES.md\n{ALLOWANCE}\nrelease-source-files.txt\n')
        repo.commit('the reviewed inventory lists an allowance file')
        return repo

    def reading(self, replacement):
        """A source_reader that records the reads of the allowance file and answers every read after the first with `replacement`."""
        original, reads = builder.source_reader, []

        @contextlib.contextmanager
        def reader():
            with original() as read:
                def counted(name):
                    data = read(name)
                    if name == ALLOWANCE:
                        reads.append(name)
                        if len(reads) > 1:
                            return replacement
                    return data
                yield counted
        return reader, reads

    def test_the_allowance_is_read_once_and_the_archive_holds_the_bytes_that_were_checked(self):
        repo = self.committed_with_allowance()
        reader, reads = self.reading(b'# replaced for a moment and put back\n')
        try:
            with patch.object(builder, 'source_reader', reader):
                receipt = repo.build()
        except ValueError as refused:
            self.fail(f'a second read of the allowance file changed what was checked: {refused}')
        self.assertEqual(reads, [ALLOWANCE], 'the allowance file was read more than once')
        archived = repo.member(ALLOWANCE)
        self.assertEqual(archived, b'# reviewed allowances\n')
        self.assertEqual(receipt['sensitive_content']['allowance_file_sha256'], base.sha256(archived))

    def test_an_allowance_file_that_the_inventory_does_not_list_is_refused(self):
        repo = hard.GitFixture(self)
        (repo.root / ALLOWANCE).write_text('# reviewed allowances\n')
        repo.commit('an allowance file the inventory does not list')
        message = self.refusal(repo)
        self.assertIn(ALLOWANCE, message)
        self.assertIn('inventory', message)
        self.assertNothingMade(repo)

    def test_the_binding_lists_the_commit_that_was_captured_and_not_head(self):
        repo = hard.GitFixture(self)
        captured, original = repo.git('rev-parse', 'HEAD'), builder.bind_to_commit

        def moved_first(snapshot, state):
            (repo.root / 'README.md').write_text('a later commit changes this file\n')
            repo.commit('a later commit, made after the final reading of the checkout')
            return original(snapshot, state)

        try:
            with patch.object(builder, 'bind_to_commit', moved_first):
                repo.build()
        except ValueError as refused:
            self.fail(f'the binding looked at HEAD instead of the captured commit: {refused}')
        record = repo.identity()
        self.assertEqual((record['commit'], record['dirty']), (captured, False))
        self.assertEqual(repo.member('README.md'), b'Reviewed project documentation\n')

    def test_only_a_full_lowercase_object_name_is_listed(self):
        for commit in ('HEAD', 'main', '--help', 'A' * 40, 'a' * 39, ''):
            with self.subTest(commit), self.assertRaises(ValueError):
                builder.bind_to_commit({}, {'commit': commit})


class ContentDigestTests(GitCase):
    """Round 5: `--check-only` reports the content digests a build would record, computed as the build computes them, so that an
    extracted source tree (which has no .git) can show that the source archive holds everything the runtime archive was made from."""

    def extracted_source(self, repo):
        target = repo.parent / 'extracted'
        with zipfile.ZipFile(repo.output / f'Intune_IaC_Plugin_{builder.__version__}_Source.zip') as archive:
            archive.extractall(target)
        return target / 'intune-iac-source'

    def test_check_only_reports_the_digests_that_a_real_build_records(self):
        repo = hard.GitFixture(self)
        report = check_only(repo)
        repo.build()
        self.assertEqual(report.get('runtime_content_sha256'), repo.identity('runtime')['content_sha256'])
        self.assertEqual(report.get('source_content_sha256'), repo.identity('source')['content_sha256'])
        self.assertNotEqual(report['runtime_content_sha256'], report['source_content_sha256'], 'the runtime archive holds fewer files')

    def test_an_extracted_source_tree_reproduces_both_digests_without_a_git_checkout(self):
        repo = hard.GitFixture(self)
        repo.build()
        tree = self.extracted_source(repo)
        self.assertFalse((tree / '.git').exists())
        report = check_only(tree)
        self.assertIsNone(report['checkout']['commit'], 'the extracted tree is not a checkout')
        self.assertEqual(report.get('runtime_content_sha256'), repo.identity('runtime')['content_sha256'])
        self.assertEqual(report.get('source_content_sha256'), repo.identity('source')['content_sha256'])

    def test_the_digests_follow_the_captured_files_and_not_the_identity_record_or_the_listing(self):
        repo = hard.GitFixture(self)
        repo.build()
        tree = self.extracted_source(repo)
        self.assertTrue((tree / 'BUILD-IDENTITY.json').is_file() and (tree / 'SHA256SUMS').is_file())
        before = check_only(tree)
        (tree / 'README.md').write_text('edited in the extracted tree\n')
        after = check_only(tree)
        for key in ('runtime_content_sha256', 'source_content_sha256'):
            self.assertNotEqual(after.get(key), before.get(key), key + ' did not follow an edited member')
        self.assertNotEqual(after.get('runtime_content_sha256'), repo.identity('runtime')['content_sha256'])


if __name__ == '__main__':
    unittest.main()
