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


GUIDE = ROOT / 'docs/CANDIDATE-GUIDE.md'
# Names the guide may mention that the archive writes or the reader creates, not files of the product.
GENERATED = {'SHA256SUMS', 'BUILD-IDENTITY.json', 'Intune_IaC_Plugin_Archive_Receipt.json'}
FILE_MENTION = (r'^(?:(?:docs|examples|scripts|contracts|intune_iac|skills|corrections|reference)/[A-Za-z0-9_./-]+'
                r'|[A-Za-z0-9_-]+(?:-[A-Za-z0-9_.]+)*\.(?:md|csv|lock|txt|json))$')


def guide_text():
    return GUIDE.read_text(encoding='utf-8')


def guide_commands(text):
    """Every `intune-iac ...` command the guide prints, as argument lists: code-block lines (continuations joined,
    a pipe or redirect ends the command) and inline code spans. The readiness test's extractor cuts each line."""
    from plugin_tests.test_readiness import ReadinessTests
    lines, in_block = [], False
    for raw in text.splitlines():
        if raw.lstrip().startswith('```'):
            in_block = not in_block
            continue
        if in_block:
            lines.append(raw.strip())
    joined, pending = [], ''
    for line in lines:
        if line.rstrip().endswith('\\'):
            pending += line.rstrip()[:-1] + ' '
            continue
        joined.append(pending + line)
        pending = ''
    spans = [span for raw in text.splitlines() if not raw.lstrip().startswith('```') for span in __import__('re').findall(r'`([^`]*intune-iac [^`]*)`', raw)]
    commands = []
    for line in joined + spans:
        if 'intune-iac ' not in line:
            continue
        tail = line.split('intune-iac ', 1)[1]
        for mark in (' | ', ' > ', ' < ', ' && '):
            tail = tail.split(mark)[0]
        found = ReadinessTests.printed_commands(ReadinessTests, 'intune-iac ' + tail)
        commands.extend(tokens for tokens in found if tokens and tokens[0])
    return commands


class CandidateGuideTests(unittest.TestCase):
    def test_the_guide_exists_and_is_linked_from_the_readme_and_start_here(self):
        self.assertTrue(GUIDE.is_file())
        for name in ('README.md', 'START-HERE.md'):
            self.assertIn('docs/CANDIDATE-GUIDE.md', (ROOT / name).read_text(encoding='utf-8'), name)

    def test_the_guide_is_in_the_runtime_archive_and_the_source_inventory(self):
        self.assertTrue('docs/CANDIDATE-GUIDE.md' in builder.runtime_files())
        self.assertTrue('docs/CANDIDATE-GUIDE.md' in (ROOT / 'release-source-files.txt').read_text().splitlines())

    def test_every_file_the_guide_names_is_in_the_runtime_archive(self):
        import re
        text = guide_text()
        mentioned = set()
        for span in re.findall(r'`([^`\n]+)`', text):
            for token in span.split():
                token = token.strip('.,;:()\'"')
                if re.match(FILE_MENTION, token) and not token.startswith(('demo/', 'Intune_IaC_Plugin_')):
                    mentioned.add(token)
        for line in (l for l in text.splitlines()):
            for token in line.split():
                token = token.strip('.,;:()\'"`')
                if re.match(r'^(?:docs|examples|scripts|contracts)/[A-Za-z0-9_./-]+\.[a-z]+$', token):
                    mentioned.add(token)
        self.assertGreater(len(mentioned), 8, mentioned)
        runtime = set(builder.runtime_files())
        missing = sorted(name for name in mentioned if name not in runtime and name not in GENERATED)
        self.assertEqual(missing, [], 'the guide names files the runtime archive does not hold')

    def test_every_intune_iac_command_in_the_guide_is_accepted_by_the_product_parser(self):
        from intune_iac import cli
        parser = cli.parser()
        commands = guide_commands(guide_text())
        self.assertGreater(len(commands), 12)
        for tokens in commands:
            with self.subTest(command=' '.join(tokens)), contextlib.redirect_stderr(io.StringIO()) as err:
                try:
                    parser.parse_args(tokens)
                except SystemExit as stop:
                    # --version is the one accepted command that ends the parse by itself, with status 0.
                    if not (tokens == ['--version'] and stop.code == 0):
                        self.fail('the product parser rejects: intune-iac %s\n%s' % (' '.join(tokens), err.getvalue()))

    def test_the_quickstart_covers_each_step_the_brief_lists(self):
        firsts = {' '.join(tokens[:2]) if tokens[0] in {'workbench', 'synthetic'} else tokens[0] for tokens in guide_commands(guide_text())}
        for step in ('doctor', 'start', 'wizard', 'synthetic generate', 'workbench lab-create', 'workbench init',
                     'workbench collect', 'workbench workspace', 'workbench families'):
            self.assertIn(step, firsts)

    def test_the_support_limits_are_stated(self):
        text = guide_text()
        for phrase in ('Linux x86_64', 'CPython 3.12', 'WSL', 'SYNTHETIC', 'CAPTURE', 'LABORATORY', 'Settings Catalog',
                       'native Windows', 'PowerShell', 'protected worker', '40 columns by 12 rows', 'simulate',
                       'filter grammar', '--no-index --find-links', 'SHA256SUMS', 'BUILD-IDENTITY'):
            self.assertIn(phrase, text)

    def test_the_guide_has_no_em_dash(self):
        self.assertNotIn('—', guide_text())

    def test_the_identifiers_the_guide_prints_are_the_ones_the_seeded_estate_produces(self):
        import re
        from intune_iac import synthetic
        text = guide_text()
        with tempfile.TemporaryDirectory() as directory:
            synthetic.write_estate(str(Path(directory) / 'estate'), seed=42, policy_count=3, case='baseline')
            estate = json.loads((Path(directory) / 'estate/capture-estate.json').read_text())
        owners = [item['owner_id'] for item in estate['collections'] if item['kind'] == 'settings']
        self.assertEqual(estate['tenant_id'], 'ca8a8057-a15f-5caa-8979-0090cd1bc11b')
        self.assertIn(estate['tenant_id'], text)
        self.assertIn('45838776-e1bd-566b-a8c5-ad684107e7da', owners)
        self.assertIn('45838776-e1bd-566b-a8c5-ad684107e7da', text)
        self.assertIn('22222222-2222-4222-8222-222222222222', text)
        sample = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        self.assertIn('22222222-2222-4222-8222-222222222222', json.dumps(sample))
        self.assertTrue(re.search(r'--seed 42|seed 42|default seed', text))


DEMO = ROOT / 'scripts/demo-clean-install.sh'


class CleanInstallScriptTests(unittest.TestCase):
    """The demonstration script refuses to run where it should not, and its quickstart is the guide's."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.fixture = FixtureBuild(self)
        self.fixture.build()
        self.archive = self.fixture.archive('runtime')
        self.wheels = self.base / 'wheels'
        self.wheels.mkdir()
        self.outside = self.base / 'outside'
        self.outside.mkdir()

    def run_script(self, *args, cwd=None):
        environment = {'PATH': os.environ['PATH'], 'LANG': 'C.UTF-8'}
        return subprocess.run(['bash', str(DEMO), *map(str, args)], cwd=cwd or self.outside, capture_output=True, text=True,
                              env=environment, timeout=120)

    def rewritten(self, change):
        """A copy of the runtime archive after `change(members)` edited its {name: bytes} mapping."""
        with zipfile.ZipFile(self.archive) as source:
            members = {info.filename: source.read(info) for info in source.infolist()}
        change(members)
        path = self.base / 'changed.zip'
        with zipfile.ZipFile(path, 'w') as out:
            for name, data in members.items():
                out.writestr(name, data)
        return path

    def test_the_script_is_valid_shell_and_has_lf_endings(self):
        self.assertTrue(DEMO.is_file())
        self.assertNotIn(b'\r', DEMO.read_bytes())
        self.assertEqual(subprocess.run(['bash', '-n', str(DEMO)], capture_output=True).returncode, 0)

    def test_wrong_usage_is_refused_with_the_usage_line(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 64)
        self.assertIn('Usage:', result.stderr)

    def test_it_refuses_to_run_from_inside_a_checkout(self):
        checkout = self.base / 'checkout'
        (checkout / '.git').mkdir(parents=True)
        (checkout / 'deeper').mkdir()
        for cwd in (checkout, checkout / 'deeper'):
            with self.subTest(cwd=str(cwd.relative_to(self.base))):
                result = self.run_script(self.archive, self.wheels, self.base / 'work', cwd=cwd)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('git checkout', result.stderr)
                self.assertFalse((self.base / 'work').exists())

    def test_it_refuses_a_work_folder_inside_a_checkout(self):
        checkout = self.base / 'checkout'
        (checkout / '.git').mkdir(parents=True)
        result = self.run_script(self.archive, self.wheels, checkout / 'new' / 'work')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('WORK_FOLDER is inside a git checkout', result.stderr)
        self.assertFalse((checkout / 'new').exists())

    def test_it_refuses_a_work_folder_that_is_not_empty(self):
        work = self.base / 'work'
        work.mkdir()
        (work / 'old.txt').write_text('earlier run')
        result = self.run_script(self.archive, self.wheels, work)
        self.assertEqual(result.returncode, 64)
        self.assertIn('not empty', result.stderr)

    def test_it_refuses_an_archive_whose_digest_is_not_the_expected_one(self):
        result = self.run_script(self.archive, self.wheels, self.base / 'work', '0' * 64)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('does not match EXPECTED_ARCHIVE_SHA256', result.stderr)
        self.assertFalse((self.base / 'work').exists())

    def test_it_accepts_the_matching_expected_digest_and_reads_on(self):
        digest = sha256(self.archive.read_bytes())
        result = self.run_script(self.archive, self.wheels, self.base / 'work', digest)
        self.assertIn('archive sha256: ' + digest, result.stdout)
        self.assertIn('SHA256SUMS verified', result.stdout)

    def test_it_refuses_an_archive_with_a_member_that_differs_from_sha256sums(self):
        path = self.rewritten(lambda members: members.update({'intune-iac/README.md': b'edited after the build\n'}))
        result = self.run_script(path, self.wheels, self.base / 'work')
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('SHA256SUMS', result.stderr)
        self.assertFalse((self.base / 'work/extract/intune-iac/.venv').exists())

    def test_it_refuses_an_archive_with_a_file_sha256sums_does_not_list(self):
        path = self.rewritten(lambda members: members.update({'intune-iac/extra.txt': b'not listed\n'}))
        result = self.run_script(path, self.wheels, self.base / 'work')
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('does not list', result.stderr)

    def test_a_verified_archive_that_is_not_the_runtime_is_refused_before_any_install(self):
        result = self.run_script(self.archive, self.wheels, self.base / 'work')
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('SHA256SUMS verified', result.stdout)
        self.assertIn('not a runtime archive', result.stderr)
        self.assertFalse((self.base / 'work/extract/intune-iac/.venv').exists())

    def test_it_installs_only_from_the_wheel_folder_with_every_hash_flag(self):
        text = DEMO.read_text()
        for flag in ('--no-index', '--find-links', '--require-hashes', '--only-binary :all:', '--isolated'):
            self.assertIn(flag, text)
        for forbidden in ('curl', 'wget', 'git clone', 'pip download', 'sudo'):
            self.assertNotIn(forbidden, text)

    def test_the_quickstart_steps_are_the_guides_commands_word_for_word(self):
        import re
        guide = ' '.join(guide_text().split())
        steps = re.findall(r'^step (\S+) "(.*)"(?: .*)?$', DEMO.read_text(), re.M)
        quick = [(name, command) for name, command in steps if 'intune-iac' in command and name != 'build-identity']
        self.assertGreaterEqual(len(quick), 10)
        for name, command in quick:
            normalized = ' '.join(command.replace('\\n', '\\n').split())
            self.assertIn(normalized, guide, name + ' differs from the guide')

    def test_the_script_is_in_the_runtime_archive_the_source_inventory_and_the_guide(self):
        self.assertTrue('scripts/demo-clean-install.sh' in builder.runtime_files())
        self.assertTrue('scripts/demo-clean-install.sh' in (ROOT / 'release-source-files.txt').read_text().splitlines())
        self.assertIn('scripts/demo-clean-install.sh', guide_text())


# A stand-in for the product inside a stand-in runtime archive: it prints, for any command, the text each step of the
# script looks for, so the install plumbing runs end to end without installing anything.
STUB_PRODUCT = '''import json, sys
args = sys.argv[1:]
if args == ['--version']:
    print('0.9.0')
elif args[:1] == ['doctor']:
    print(json.dumps({'status': 'ready', 'build': {'status': 'identified', 'product_version': '0.9.0',
                                                    'commit': None, 'content_sha256': '0' * 64}}))
else:
    print('Export Context "status": "complete_simulation" "execution_authorized": false "synthetic": true '
          '"status": "created" "evidence_class": "synthetic" "coverage": "complete" "relation": "setting" '
          '"status": "closed" "available": true')
'''
STUB_VERIFY = 'print(\'{"status": "verified"}\')\n'
# A stand-in for the pip wheel: a zip whose pip/__main__.py records how it was called, as the real wheel is run
# (python PATH/pip ...).
FAKE_PIP_MAIN = '''import os, sys
with open(os.environ['FAKE_PIP_LOG'], 'a') as log:
    log.write('wheel-pip ' + ' '.join(sys.argv) + '\\n')
'''
# A stand-in for the interpreter the script is told to use (PYTHON): it reports whether ensurepip exists as the test
# says, creates the environment without pip (and puts a recording pip module in it when it was asked for one), and
# hands everything else to the real interpreter.
FAKE_INTERPRETER = '''#!/bin/sh
case "$1" in
    -c)
        case "$2" in
            *ensurepip*) [ "$FAKE_ENSUREPIP" = present ]; exit $? ;;
        esac ;;
    -m)
        if [ "$2" = venv ]; then
            echo "venv $*" >> "$FAKE_LOG"
            shift 2
            if [ "$1" = --without-pip ]; then exec "$REAL_PYTHON" -m venv "$@"; fi
            "$REAL_PYTHON" -m venv --without-pip "$@" || exit 1
            site=$("$1/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])') || exit 1
            mkdir -p "$site/pip"
            : > "$site/pip/__init__.py"
            printf '%s\\n' 'import os, sys' \\
                "open(os.environ['FAKE_PIP_LOG'], 'a').write('module-pip ' + ' '.join(sys.argv[1:]) + chr(10))" \\
                > "$site/pip/__main__.py"
            exit 0
        fi ;;
esac
exec "$REAL_PYTHON" "$@"
'''
LOCK = 'requirements-runtime-linux-x86_64-cp312.lock'


class PipWheelInstallTests(unittest.TestCase):
    """A host whose Python has no ensurepip: `--pip-wheel PATH` makes the environment without pip and runs every pip
    command from the wheel file. Without the option the script installs as it always did."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.outside = self.base / 'outside'
        self.outside.mkdir()
        self.wheels = self.base / 'wheels'
        self.wheels.mkdir()
        members = {'scripts/intune-iac.py': STUB_PRODUCT, 'scripts/verify-dependencies.py': STUB_VERIFY,
                   LOCK: '# a stand-in lock: this test runs the plumbing, not an install\n'}
        members['SHA256SUMS'] = ''.join(f'{sha256(text.encode())}  {name}\n' for name, text in sorted(members.items()))
        self.archive = self.base / 'stand-in-runtime.zip'
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for name, text in members.items():
                archive.writestr('intune-iac/' + name, text)
        self.pip_wheel = self.base / 'pip-0.0-py3-none-any.whl'
        with zipfile.ZipFile(self.pip_wheel, 'w') as archive:
            archive.writestr('pip/__init__.py', '')
            archive.writestr('pip/__main__.py', FAKE_PIP_MAIN)
        self.interpreter = self.base / 'interpreter'
        self.interpreter.write_text(FAKE_INTERPRETER)
        self.interpreter.chmod(0o755)
        self.log = self.base / 'calls.log'
        self.pip_log = self.base / 'pip-calls.log'

    def run_script(self, *args, ensurepip='missing'):
        environment = {'PATH': os.environ['PATH'], 'LANG': 'C.UTF-8', 'PYTHON': str(self.interpreter),
                       'REAL_PYTHON': sys.executable, 'FAKE_ENSUREPIP': ensurepip, 'FAKE_LOG': str(self.log),
                       'FAKE_PIP_LOG': str(self.pip_log)}
        return subprocess.run(['bash', str(DEMO), *map(str, args)], cwd=self.outside, capture_output=True, text=True,
                              env=environment, timeout=180)

    def pip_calls(self):
        return self.pip_log.read_text().splitlines() if self.pip_log.exists() else []

    def venv_calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def install_arguments(self):
        return (f'--isolated install --no-index --no-cache-dir --find-links {self.wheels} --require-hashes '
                f'--only-binary :all: -r {LOCK}')

    def test_with_the_option_the_environment_has_no_pip_and_every_install_runs_from_the_wheel(self):
        result = self.run_script('--pip-wheel', self.pip_wheel, self.archive, self.wheels, self.base / 'work')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.venv_calls(), ['venv -m venv --without-pip .venv'])
        wheel = f'{self.pip_wheel}/pip'
        self.assertEqual(self.pip_calls(), [f'wheel-pip {wheel} {self.install_arguments()}',
                                            f'wheel-pip {wheel} --isolated check'])
        self.assertIn('RESULT: every step passed.', result.stdout)

    def test_the_wheels_sha256_is_printed_next_to_the_archives(self):
        result = self.run_script('--pip-wheel', self.pip_wheel, self.archive, self.wheels, self.base / 'work')
        self.assertIn('pip wheel sha256: ' + sha256(self.pip_wheel.read_bytes()), result.stdout)
        self.assertIn('archive sha256: ' + sha256(self.archive.read_bytes()), result.stdout)

    def test_the_option_may_follow_the_arguments_and_take_an_equals_sign(self):
        result = self.run_script(self.archive, self.wheels, self.base / 'work', f'--pip-wheel={self.pip_wheel}')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.venv_calls(), ['venv -m venv --without-pip .venv'])

    def test_the_wheel_is_read_in_place_and_not_copied_into_the_work_folder(self):
        before = self.pip_wheel.read_bytes()
        result = self.run_script('--pip-wheel', self.pip_wheel, self.archive, self.wheels, self.base / 'work')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(list((self.base / 'work').rglob('*.whl')), [])
        self.assertEqual(self.pip_wheel.read_bytes(), before)

    def test_a_host_without_ensurepip_is_accepted_only_with_the_option(self):
        with_option = self.run_script('--pip-wheel', self.pip_wheel, self.archive, self.wheels, self.base / 'a')
        self.assertEqual(with_option.returncode, 0, with_option.stdout + with_option.stderr)
        calls_before = (self.venv_calls(), self.pip_calls())
        without = self.run_script(self.archive, self.wheels, self.base / 'b')
        self.assertEqual(without.returncode, 1, without.stdout + without.stderr)
        self.assertIn('environment', without.stdout)
        self.assertIn('--pip-wheel', without.stdout + without.stderr, 'the failure should name the way out')
        self.assertIn('python3.12-venv', without.stdout + without.stderr, 'and the other way out')
        self.assertEqual((self.venv_calls(), self.pip_calls()), calls_before, 'nothing is made or installed on a refusal')

    def test_without_the_option_the_script_installs_through_the_environments_own_pip_as_before(self):
        result = self.run_script(self.archive, self.wheels, self.base / 'work', ensurepip='present')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.venv_calls(), ['venv -m venv .venv'])
        self.assertEqual(self.pip_calls(), [f'module-pip {self.install_arguments()}', 'module-pip --isolated check'])
        self.assertNotIn('pip wheel sha256', result.stdout)

    def test_a_missing_wheel_a_missing_value_and_a_non_pip_zip_are_refused_before_anything_is_made(self):
        not_pip = self.base / 'other.whl'
        with zipfile.ZipFile(not_pip, 'w') as archive:
            archive.writestr('something/__init__.py', '')
        work = self.base / 'work'
        cases = {'missing file': ('--pip-wheel', self.base / 'absent.whl', self.archive, self.wheels, work),
                 'folder': ('--pip-wheel', self.wheels, self.archive, self.wheels, work),
                 'not a pip wheel': ('--pip-wheel', not_pip, self.archive, self.wheels, work),
                 'no value': (self.archive, self.wheels, work, '--pip-wheel'),
                 'unknown option': ('--no-such-option', self.archive, self.wheels, work)}
        for name, arguments in cases.items():
            with self.subTest(name):
                result = self.run_script(*arguments)
                self.assertEqual(result.returncode, 64, result.stdout + result.stderr)
                self.assertTrue(('Usage:' in result.stderr) or ('REFUSED:' in result.stderr), result.stderr)
                self.assertFalse(work.exists(), 'a refused run makes nothing')
                self.assertEqual((self.venv_calls(), self.pip_calls()), ([], []))

    def test_usage_names_the_option_and_the_comment_says_when_to_use_it(self):
        self.assertIn('[--pip-wheel PATH]', self.run_script().stderr)
        header = '\n'.join(DEMO.read_text().splitlines()[:30])
        self.assertIn('--pip-wheel', header)
        self.assertIn('ensurepip', header)


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
