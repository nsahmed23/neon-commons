"""Archive creation needs a known, clean Git state, and what is archived is bound to the one commit the receipt names
(PKG-RELEASE-1 round 4). Real temporary repositories, with the fixture and the secret-shaped test data of test_release_hardening
(values are built at run time and never written out whole)."""
import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
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

    def test_the_build_refuses_a_digest_that_check_only_would_not_report(self):
        real = builder.content_digests
        for kind, lie in (('runtime', lambda r, s: ('0' * 64, s)), ('source', lambda r, s: (r, '1' * 64))):
            with self.subTest(kind):
                repo = hard.GitFixture(self)
                with patch.object(builder, 'content_digests', lambda snapshot, runtime: lie(*real(snapshot, runtime))):
                    # The digests are worked out once, so the lie reaches the check made against what the archive embeds.
                    message = self.refusal(repo)
                self.assertIn(kind, message)
                self.assertIn('--check-only reports', message)

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


CHECKER = base.ROOT / 'research/enterprise-ci/check-archives.py'
IDENTITY = 'BUILD-IDENTITY.json'
DIFFERENT_BYTES = 'Runtime bytes differ from source release bytes.'
RUNTIME = (f'Intune_IaC_Plugin_{builder.__version__}.zip', 'intune-iac')
SOURCE = (f'Intune_IaC_Plugin_{builder.__version__}_Source.zip', 'intune-iac-source')


class ArchivePairCase(GitCase):
    """The runtime and the source archive of one clean build, made by the real builder from a real repository, and the repository's
    CI archive check (research/enterprise-ci/check-archives.py) to run on them; helpers to change one archive and keep its digest
    list and the build receipt in step, so that the check under test is the only thing left that can notice the change."""

    def setUp(self):
        super().setUp()
        spec = importlib.util.spec_from_file_location('ci_archive_checker', CHECKER)
        self.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.checker)

    def build(self):
        """The runtime and source archive of one clean commit of a fresh repository."""
        repo = hard.GitFixture(self)
        repo.build()
        return repo

    def check(self, repo, folder='extracted'):
        """The repository's check on the build's two archives: its refusal as the message, success as None. Anything other than
        a refusal is a defect of the check and is left to fail the test."""
        try:
            self.checker.check_release(repo.output, repo.parent / folder)
        except ValueError as refused:
            return str(refused)
        return None

    def rewrite(self, repo, archive, changes, consistent=True):
        """Change members of one archive (a member mapped to None is dropped). When consistent, its SHA256SUMS and the build receipt
        follow the new bytes, so the comparison of shared members is the only check left that can notice the difference; when not,
        only the member bytes change."""
        filename, prefix = archive
        path = repo.output / filename
        with zipfile.ZipFile(path) as opened:
            members = {info.filename[len(prefix) + 1:]: opened.read(info) for info in opened.infolist()}
        listing = members.pop('SHA256SUMS')
        for name, data in changes.items():
            if data is None:
                del members[name]
            else:
                members[name] = data
        if consistent:
            listing = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in sorted(members.items())).encode()
        path.unlink()
        with zipfile.ZipFile(path, 'w') as rewritten:
            for name, data in {**members, 'SHA256SUMS': listing}.items():
                rewritten.writestr(f'{prefix}/{name}', data)
        if consistent:
            receipt_path = repo.output / 'Intune_IaC_Plugin_Archive_Receipt.json'
            receipt = json.loads(receipt_path.read_text())
            row = next(item for item in receipt['archives'] if item['filename'] == filename)
            row.update(files=len(members) + 1, listed_hashes=len(members), bytes=path.stat().st_size,
                       sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            receipt_path.write_text(json.dumps(receipt))

    def record(self, repo, archive):
        """The identity record inside one archive, parsed."""
        filename, prefix = archive
        with zipfile.ZipFile(repo.output / filename) as opened:
            return json.loads(opened.read(f'{prefix}/{IDENTITY}'))

    def edit_record(self, repo, archive, changes, settle=True):
        """Set fields of one archive's identity record ('companion.key' reaches into the companion; None removes the field), with the
        archive's digest list and the receipt kept in step. The source record's companion names the runtime archive's own digest, so
        after a change to the runtime archive that line is made true again (unless settle is false): only the edited field is wrong."""
        record = self.record(repo, archive)
        for path, value in changes.items():
            holder, _, key = path.rpartition('.')
            target = record[holder] if holder else record
            if value is None:
                target.pop(key, None)
            else:
                target[key] = value
        self.rewrite(repo, archive, {IDENTITY: json.dumps(record, indent=2).encode() + b'\n'})
        if settle and archive == RUNTIME:
            digest = hashlib.sha256((repo.output / RUNTIME[0]).read_bytes()).hexdigest()
            self.edit_record(repo, SOURCE, {'companion.archive_sha256': digest}, settle=False)


class ArchiveCheckTests(ArchivePairCase):
    """Round 6: the CI's archive check accepts the runtime and the source archive of one clean build. Each archive's
    BUILD-IDENTITY.json describes that archive, so the two differ by design and are not required to match; every other member
    the two share must still have the same bytes, and every member still has to match its own archive's digest list."""

    def test_the_runtime_and_source_archive_of_one_clean_build_pass_and_are_extracted(self):
        repo = self.build()
        self.assertNotEqual(repo.member(IDENTITY, 'runtime'), repo.member(IDENTITY, 'source'), 'the two identity records differ by design')
        self.assertEqual(repo.member('README.md', 'runtime'), repo.member('README.md', 'source'))
        refused = self.check(repo)
        self.assertIsNone(refused, 'the check refused the two archives of one clean build: ' + str(refused))
        for folder, kind in (('intune-iac', 'runtime'), ('intune-iac-source', 'source')):
            self.assertEqual(json.loads((repo.parent / 'extracted' / folder / IDENTITY).read_text())['archive_kind'], kind)
            self.assertEqual((repo.parent / 'extracted' / folder / 'README.md').read_bytes(), repo.member('README.md', kind))

    def test_the_command_the_workflow_runs_passes_on_the_same_archives(self):
        repo = self.build()
        result = subprocess.run([sys.executable, '-B', str(CHECKER), '--directory', str(repo.output), '--output',
                                 str(repo.parent / 'by-command')], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, 'the check failed on the two archives of one clean build: ' + result.stderr[-400:])
        report = json.loads(result.stdout)
        self.assertIs(report['success'], True)
        self.assertIs(report['shared_runtime_bytes_verified'], True)

    def test_an_edited_shared_member_other_than_the_identity_record_still_fails(self):
        cases = {'edited in the source archive': (SOURCE, {'README.md': b'edited in the source archive only\n'}),
                 'edited in the runtime archive': (RUNTIME, {'README.md': b'edited in the runtime archive only\n'}),
                 'dropped from the source archive': (SOURCE, {'README.md': None})}
        for name, (archive, changes) in cases.items():
            with self.subTest(name):
                repo = self.build()
                self.assertIsNone(self.check(repo, 'untouched'), 'the untouched pair must pass, or this proves nothing')
                self.rewrite(repo, archive, changes)
                self.assertEqual(self.check(repo), DIFFERENT_BYTES)
                self.assertFalse((repo.parent / 'extracted').exists(), 'nothing is extracted from archives that differ')

    def test_the_identity_record_is_left_out_of_the_comparison_but_not_out_of_the_archive_digest_list(self):
        for member in (IDENTITY, 'README.md'):
            with self.subTest(member):
                repo = self.build()
                self.rewrite(repo, SOURCE, {member: b'changed without updating the digest list\n'}, consistent=False)
                self.assertEqual(self.check(repo), 'Archive member digest mismatch.')


SHARED_FIELDS = ('built_at', 'commit', 'dirty', 'product_version', 'schema_version', 'tree')


class IdentityRecordTests(ArchivePairCase):
    """Round 7: the CI archive check refuses a pair whose two identity records do not belong together, naming the field. Both
    archives hold a record; the fields that name the build are equal in both; each record's companion names the other archive as it
    is; each record describes its own archive (kind, file count, content digest). Each condition is tried alone, on a real pair
    changed in that one place, after the untouched pair has been shown to pass."""

    def refused(self, repo, expected):
        self.assertEqual(self.check(repo), expected)
        self.assertFalse((repo.parent / 'extracted').exists(), 'nothing is extracted from a pair that does not belong together')

    def test_the_clean_pair_still_passes_and_says_that_its_records_were_checked(self):
        repo = self.build()
        report = self.checker.check_release(repo.output, repo.parent / 'extracted')
        self.assertIs(report['success'], True)
        self.assertIs(report.get('identity_records_verified'), True)

    def test_a_pair_built_from_two_different_commits_is_refused_naming_the_commit(self):
        repo = hard.GitFixture(self)
        repo.build()
        first = repo.output
        repo.git('commit', '--allow-empty', '-q', '-m', 'second')
        repo.output = repo.parent / 'second-out'
        repo.build()
        pair = repo.parent / 'pair'
        pair.mkdir()
        rows = []
        for out, (filename, _) in ((first, RUNTIME), (repo.output, SOURCE)):
            shutil.copy(out / filename, pair / filename)
            receipt = json.loads((out / 'Intune_IaC_Plugin_Archive_Receipt.json').read_text())
            rows += [item for item in receipt['archives'] if item['filename'] == filename]
        (pair / 'Intune_IaC_Plugin_Archive_Receipt.json').write_text(json.dumps({'version': builder.__version__, 'archives': rows}))
        repo.output = pair
        self.assertNotEqual(self.record(repo, RUNTIME)['commit'], self.record(repo, SOURCE)['commit'], 'the pair is from two commits')
        self.assertEqual(self.record(repo, RUNTIME)['tree'], self.record(repo, SOURCE)['tree'], 'and from the same tree')
        self.refused(repo, f'The runtime and source {IDENTITY} records do not agree on commit.')

    def test_each_shared_field_that_differs_or_is_missing_is_refused_naming_it(self):
        other = {'built_at': '2000-01-01T00:00:00Z', 'commit': '1' * 40, 'dirty': True, 'product_version': '0.0.1',
                 'schema_version': 'build-identity/0', 'tree': '2' * 40}
        self.assertEqual(tuple(sorted(other)), SHARED_FIELDS)
        for field in SHARED_FIELDS:
            for how, value in (('differs', other[field]), ('is missing from the source record', None)):
                with self.subTest(f'{field} {how}'):
                    repo = self.build()
                    self.assertIsNone(self.check(repo, 'untouched'), 'the untouched pair must pass, or this proves nothing')
                    self.assertNotEqual(self.record(repo, SOURCE)[field], value)
                    self.edit_record(repo, SOURCE, {field: value})
                    self.refused(repo, f'The runtime and source {IDENTITY} records do not agree on {field}.')

    def test_an_archive_without_its_identity_record_is_refused(self):
        for kind, archive in (('runtime', RUNTIME), ('source', SOURCE)):
            with self.subTest(kind):
                repo = self.build()
                self.rewrite(repo, archive, {IDENTITY: None})
                self.refused(repo, f'The {kind} archive has no {IDENTITY}.')

    def test_an_identity_record_that_is_not_a_json_object_is_refused(self):
        for data, why in ((b'this is not json', 'is not valid JSON'), (b'["a", "list"]', 'is not a JSON object')):
            with self.subTest(why):
                repo = self.build()
                self.rewrite(repo, SOURCE, {IDENTITY: data})
                self.refused(repo, f'The source {IDENTITY} {why}.')

    def test_a_companion_that_does_not_name_the_other_archive_as_it_is_is_refused(self):
        wrong = '0' * 64
        cases = {'the runtime record names another source content digest': (RUNTIME, 'companion.content_sha256', wrong, 'runtime', 'source'),
                 'the source record names another runtime archive digest': (SOURCE, 'companion.archive_sha256', wrong, 'source', 'runtime'),
                 'the runtime record names the wrong kind': (RUNTIME, 'companion.archive_kind', 'runtime', 'runtime', 'source'),
                 'the source record names the wrong kind': (SOURCE, 'companion.archive_kind', 'source', 'source', 'runtime')}
        for name, (archive, path, value, kind, other) in cases.items():
            with self.subTest(name):
                repo = self.build()
                self.assertIsNone(self.check(repo, 'untouched'), 'the untouched pair must pass, or this proves nothing')
                self.edit_record(repo, archive, {path: value})
                self.refused(repo, f'The {kind} {IDENTITY} field {path} does not name the {other} archive.')
        for kind, archive, other in (('runtime', RUNTIME, 'source'), ('source', SOURCE, 'runtime')):
            with self.subTest(f'the {kind} record has no companion'):
                repo = self.build()
                self.edit_record(repo, archive, {'companion': None})
                self.refused(repo, f'The {kind} {IDENTITY} has no companion naming the {other} archive.')

    def test_the_companion_digest_links_are_required_and_not_optional(self):
        """The builder always writes runtime.companion.content_sha256 and source.companion.archive_sha256. A record without the key is
        refused naming it, also when both are gone and every digest list and the receipt were made to match (the receipt is unsigned):
        otherwise the pair would carry no binding between its two archives."""
        content, archive_digest, kind_key = 'companion.content_sha256', 'companion.archive_sha256', 'companion.archive_kind'
        cases = {'the runtime record without its source content digest': ([(RUNTIME, content)], 'runtime', content),
                 'the source record without its runtime archive digest': ([(SOURCE, archive_digest)], 'source', archive_digest),
                 'both digests removed together': ([(RUNTIME, content), (SOURCE, archive_digest)], 'runtime', content),
                 'the runtime companion without the kind': ([(RUNTIME, kind_key)], 'runtime', kind_key),
                 'the source companion without the kind': ([(SOURCE, kind_key)], 'source', kind_key)}
        for name, (removals, kind, path) in cases.items():
            with self.subTest(name):
                repo = self.build()
                self.assertIsNone(self.check(repo, 'untouched'), 'the untouched pair must pass, or this proves nothing')
                for archive, key in removals:
                    self.edit_record(repo, archive, {key: None})
                self.refused(repo, f'The {kind} {IDENTITY} field {path} is missing.')

    def test_a_record_that_does_not_describe_its_own_archive_is_refused(self):
        for kind, archive, other in (('runtime', RUNTIME, 'source'), ('source', SOURCE, 'runtime')):
            for label, field, change in (('archive_kind', 'archive_kind', lambda count: other),
                                         ('file_count', 'file_count', lambda count: count + 1),
                                         ('file_count as a float', 'file_count', float),
                                         ('content_sha256', 'content_sha256', lambda count: '0' * 64)):
                with self.subTest(f'{kind} {label}'):
                    repo = self.build()
                    self.assertIsNone(self.check(repo, 'untouched'), 'the untouched pair must pass, or this proves nothing')
                    self.edit_record(repo, archive, {field: change(self.record(repo, archive)['file_count'])})
                    self.refused(repo, f'The {kind} {IDENTITY} field {field} does not match the {kind} archive.')


if __name__ == '__main__':
    unittest.main()
