"""The release candidate package: a build a stranger can install and identify (PKG-RELEASE-1).

Every test builds from temporary directories or reads the checkout; nothing here installs, fetches or touches a
real workspace. Each class belongs to one item of the package.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/build-release.py'
SPEC = importlib.util.spec_from_file_location('release_builder_candidate', SCRIPT)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

COMMIT = 'a' * 40
TREE = 'b' * 40
BUILT_AT = '2026-10-16T01:02:03Z'
IDENTITY = 'BUILD-IDENTITY.json'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class FixtureBuild:
    """A tiny reviewed checkout, built with a fixed commit, tree and clock."""

    def __init__(self, case):
        self.case = case
        temp = tempfile.TemporaryDirectory()
        case.addCleanup(temp.cleanup)
        self.parent = Path(temp.name)
        self.root = self.parent / 'repo'
        self.root.mkdir()
        (self.root / 'README.md').write_text('Reviewed project documentation\n')
        (self.root / 'NOTES.md').write_text('Source only notes\n')
        (self.root / 'release-source-files.txt').write_text('README.md\nNOTES.md\nrelease-source-files.txt\n')
        self.output = self.parent / 'out'

    def build(self, state=None, built_at=BUILT_AT):
        state = {'commit': COMMIT, 'tree': TREE, 'dirty': False} if state is None else state
        with patch.object(builder, 'ROOT', self.root), patch.object(builder, 'runtime_files', return_value=['README.md']), \
                patch.object(builder, 'git_state', return_value=state), patch.object(builder, 'build_time', return_value=built_at), \
                patch.object(sys, 'argv', ['build-release.py', '--output-dir', str(self.output)]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            builder.main()
        self.receipt = json.loads(out.getvalue())
        return self.receipt

    def archive(self, kind):
        name = f'Intune_IaC_Plugin_{builder.__version__}' + ('' if kind == 'runtime' else '_Source') + '.zip'
        return self.output / name

    def members(self, kind):
        prefix = 'intune-iac/' if kind == 'runtime' else 'intune-iac-source/'
        with zipfile.ZipFile(self.archive(kind)) as archive:
            return {info.filename[len(prefix):]: archive.read(info) for info in archive.infolist()}

    def identity(self, kind):
        return json.loads(self.members(kind)[IDENTITY])

    def extract(self, kind='runtime'):
        destination = self.parent / ('installed-' + kind)
        for name, data in self.members(kind).items():
            (destination / name).parent.mkdir(parents=True, exist_ok=True)
            (destination / name).write_bytes(data)
        return destination


def listed(members):
    """The SHA256SUMS of an archive as {name: digest}."""
    return {line.split('  ', 1)[1]: line.split('  ', 1)[0] for line in members['SHA256SUMS'].decode().splitlines()}


def content_digest(members):
    """Digest of every listed member except the identity record, as the identity record defines it."""
    lines = ''.join(f'{digest}  {name}\n' for name, digest in sorted(listed(members).items()) if name != IDENTITY)
    return sha256(lines.encode())


class BuildIdentityTests(unittest.TestCase):
    EXPECTED_KEYS = {'schema_version', 'archive_kind', 'product_version', 'commit', 'tree', 'dirty', 'built_at',
                     'file_count', 'content_sha256'}

    def setUp(self):
        self.fixture = FixtureBuild(self)
        self.receipt = self.fixture.build()

    def test_every_archive_carries_an_identity_record_naming_the_build(self):
        for kind in ('runtime', 'source'):
            with self.subTest(kind=kind):
                record = self.fixture.identity(kind)
                self.assertEqual(record['schema_version'], 'build-identity/1')
                self.assertEqual(record['archive_kind'], kind)
                self.assertEqual(record['product_version'], builder.__version__)
                self.assertEqual((record['commit'], record['tree'], record['dirty']), (COMMIT, TREE, False))
                self.assertEqual(record['built_at'], BUILT_AT)
                self.assertTrue(self.EXPECTED_KEYS <= set(record), set(record))

    def test_the_identity_record_is_listed_in_the_archives_own_sha256sums(self):
        for kind in ('runtime', 'source'):
            with self.subTest(kind=kind):
                members = self.fixture.members(kind)
                self.assertEqual(listed(members)[IDENTITY], sha256(members[IDENTITY]))

    def test_the_content_digest_matches_the_files_the_archive_holds(self):
        for kind, files in (('runtime', 1), ('source', 3)):
            with self.subTest(kind=kind):
                members = self.fixture.members(kind)
                record = json.loads(members[IDENTITY])
                self.assertEqual(record['content_sha256'], content_digest(members))
                self.assertEqual(record['file_count'], files)

    def test_each_archive_names_the_other_by_digest(self):
        runtime, source = self.fixture.identity('runtime'), self.fixture.identity('source')
        self.assertEqual(runtime['companion'], {'archive_kind': 'source', 'content_sha256': source['content_sha256']})
        self.assertEqual(source['companion'], {'archive_kind': 'runtime',
                                               'archive_sha256': sha256(self.fixture.archive('runtime').read_bytes())})

    def test_the_receipt_gives_each_archive_digest_and_the_build(self):
        by_name = {item['filename']: item for item in self.receipt['archives']}
        for kind in ('runtime', 'source'):
            archive = self.fixture.archive(kind)
            self.assertEqual(by_name[archive.name]['sha256'], sha256(archive.read_bytes()))
            self.assertEqual(by_name[archive.name]['content_sha256'], self.fixture.identity(kind)['content_sha256'])
        self.assertEqual(self.receipt['build'], {'commit': COMMIT, 'tree': TREE, 'dirty': False, 'built_at': BUILT_AT})

    def test_a_source_file_named_like_the_identity_record_is_refused(self):
        other = FixtureBuild(self)
        (other.root / IDENTITY).write_text('{}')
        (other.root / 'release-source-files.txt').write_text(f'README.md\n{IDENTITY}\nrelease-source-files.txt\n')
        with self.assertRaises(ValueError):
            other.build()

    def test_a_checkout_without_git_state_records_nulls_not_a_guess(self):
        other = FixtureBuild(self)
        other.build(state={'commit': None, 'tree': None, 'dirty': None})
        record = other.identity('runtime')
        self.assertEqual((record['commit'], record['tree'], record['dirty']), (None, None, None))


class GitStateAndClockTests(unittest.TestCase):
    def test_outside_a_repository_the_state_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, 'ROOT', Path(directory)):
            self.assertEqual(builder.git_state(), {'commit': None, 'tree': None, 'dirty': None})

    def test_the_checkout_state_is_the_commit_and_tree_git_reports(self):
        def git(*args):
            return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()
        try:
            commit, tree = git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')
        except (OSError, subprocess.CalledProcessError):
            self.skipTest('git or a repository is not available here')
        state = builder.git_state()
        self.assertEqual((state['commit'], state['tree']), (commit, tree))
        self.assertIsInstance(state['dirty'], bool)

    def test_the_build_time_honours_source_date_epoch_and_is_utc_seconds(self):
        with patch.dict(os.environ, {'SOURCE_DATE_EPOCH': '1760000000'}):
            self.assertEqual(builder.build_time(), '2025-10-09T08:53:20Z')
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SOURCE_DATE_EPOCH', None)
            self.assertRegex(builder.build_time(), r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')


class InstalledIdentityTests(unittest.TestCase):
    """What `doctor` prints from an installed copy."""

    def setUp(self):
        self.fixture = FixtureBuild(self)
        self.fixture.build()
        self.installed = self.fixture.extract('runtime')

    def report(self, root=None):
        from intune_iac import build_identity
        return build_identity.report(self.installed if root is None else root)

    def test_an_intact_install_reports_the_build_it_came_from(self):
        value = self.report()
        self.assertEqual(value['status'], 'identified')
        for key, expected in (('commit', COMMIT), ('tree', TREE), ('built_at', BUILT_AT), ('archive_kind', 'runtime'),
                              ('product_version', builder.__version__)):
            self.assertEqual(value[key], expected)
        self.assertEqual(value['content_sha256'], self.fixture.identity('runtime')['content_sha256'])
        self.assertEqual(value['modified_files'], [])

    def test_an_edited_file_is_named_not_hidden(self):
        (self.installed / 'README.md').write_text('edited after install\n')
        value = self.report()
        self.assertEqual(value['status'], 'modified')
        self.assertEqual(value['modified_files'], ['README.md'])

    def test_a_missing_file_is_named(self):
        (self.installed / 'README.md').unlink()
        self.assertEqual(self.report()['modified_files'], ['README.md'])

    def test_a_listing_that_no_longer_matches_the_record_is_inconsistent(self):
        sums = self.installed / 'SHA256SUMS'
        sums.write_text(sums.read_text() + f'{"0" * 64}  extra.txt\n')
        self.assertEqual(self.report()['status'], 'inconsistent')

    def test_a_checkout_is_not_a_release_build(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self.report(Path(directory))
        self.assertEqual(value['status'], 'not_a_release_build')
        self.assertIn('checkout', value['note'])

    def test_an_unreadable_record_is_reported_not_raised(self):
        (self.installed / IDENTITY).write_text('{not json')
        self.assertEqual(self.report()['status'], 'unreadable')

    def test_doctor_carries_the_same_report(self):
        from intune_iac import build_identity, cli
        with patch.object(build_identity, 'PACKAGE_ROOT', self.installed):
            value = cli.doctor()
        self.assertEqual(value['build']['status'], 'identified')
        self.assertEqual(value['build']['commit'], COMMIT)

    def test_doctor_in_a_checkout_says_so(self):
        from intune_iac import cli
        self.assertEqual(cli.doctor()['build']['status'], 'not_a_release_build')


class RuntimeContentTests(unittest.TestCase):
    """The runtime archive holds what the quickstart runs: the families view needs the table and the manifest."""

    def test_the_runtime_list_names_the_integration_manifest_and_the_family_table(self):
        names = builder.runtime_files()
        for name in ('contracts/integration-manifest.json', 'family-coverage.csv'):
            self.assertTrue(name in names, name + ' is not in the runtime archive list')
            self.assertTrue(builder.allowed(ROOT / name), name)

    def test_a_tree_of_exactly_the_runtime_files_serves_the_families_view(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory) / 'installed'
            for name in builder.runtime_files():
                (tree / name).parent.mkdir(parents=True, exist_ok=True)
                (tree / name).write_bytes((ROOT / name).read_bytes())
            code = ('import json, sys; sys.path.insert(0, sys.argv[1]); from intune_iac import families; '
                    'value = families.families(); print(json.dumps([value["available"], value.get("reason"), len(value["families"])]))')
            result = subprocess.run([sys.executable, '-B', '-c', code, str(tree)], cwd=directory, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        available, reason, count = json.loads(result.stdout)
        self.assertEqual((available, reason), (True, None))
        self.assertGreaterEqual(count, 9)


class CheckoutBuildCheckTests(unittest.TestCase):
    # Found 2026-10-15 at base 7f9d86f: `scripts/build-release.py --check-only` refuses the reviewed inventory because
    # it lists the frozen synthetic executor state (a .tfstate file name) added with the pre-pin-migration fixtures.
    # The sensitive-name guard is a security control and this package may not relax it; the controller decides
    # between a path-and-digest exception and dropping the file from the inventory. Remove expectedFailure then.
    @unittest.expectedFailure
    def test_the_checkout_inventory_passes_the_build_check(self):
        with patch.object(sys, 'argv', ['build-release.py', '--check-only']), contextlib.redirect_stdout(io.StringIO()) as out:
            builder.main()
        self.assertEqual(json.loads(out.getvalue())['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
