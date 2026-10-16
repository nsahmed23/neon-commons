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
import re
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

    def test_the_identifiers_the_guide_prints_are_the_ones_the_bundled_sample_holds(self):
        import re
        text = guide_text()
        sample = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        context = json.loads((ROOT / 'examples/context.json').read_text())
        for identifier in (SAMPLE_TENANT, SAMPLE_POLICY):
            self.assertIn(identifier, text)
            self.assertIn(identifier, json.dumps(sample), identifier)
        self.assertIn(SAMPLE_TENANT, json.dumps(context))
        self.assertTrue(re.search(r'--seed 42|seed 42|default seed', text), 'the larger seeded estate is still explained')


SAMPLE_TENANT = '11111111-1111-4111-8111-111111111111'
SAMPLE_POLICY = '22222222-2222-4222-8222-222222222222'
# The sample data the runtime archive holds: what `start` and `catalog` find in an unpacked copy.
ARCHIVE_EXAMPLES = ('examples/context.json', 'examples/supported/input/export.json')
SECTIONS = ('What you need', 'Check the download', 'Install', 'The sample data', 'Quickstart with the bundled sample data',
            'Check a clean install end to end', 'Support limits', 'Troubleshooting', 'Reporting an issue')


def squashed(text):
    return ' '.join(text.split())


def guide_section(title):
    """The text of one second-level section of the guide, from its heading to the next."""
    import re
    match = re.search(r'^## ' + re.escape(title) + r'\n(.*?)(?=^## |\Z)', guide_text(), re.S | re.M)
    if not match:
        raise AssertionError('the guide has no section named ' + title)
    return match.group(1)


def code_blocks(text):
    blocks, current = [], None
    for line in text.splitlines():
        if line.lstrip().startswith('```'):
            if current is None:
                current = []
            else:
                blocks.append(current)
                current = None
        elif current is not None:
            current.append(line.strip())
    return blocks


class GuideStructureTests(unittest.TestCase):
    """The guide covers what this build does, section by section, and says only what the product can back."""

    def test_the_guide_has_every_section_in_order(self):
        import re
        headings = re.findall(r'^## (.+)$', guide_text(), re.M)
        self.assertEqual([h for h in headings if h in SECTIONS], list(SECTIONS), headings)

    def test_the_commands_for_each_part_of_the_build_are_shown(self):
        shown = {' '.join(tokens[:2]) if tokens[0] in {'workbench', 'synthetic', 'signin'} else tokens[0]
                 for tokens in guide_commands(guide_text())}
        for command in ('start', 'signin status', 'catalog', 'workbench workflow', 'workbench workspace', 'engineering',
                        'workbench families', 'wizard', 'doctor', 'synthetic generate', 'workbench lab-create',
                        'workbench init', 'workbench collect'):
            self.assertIn(command, shown)
        self.assertIn('`:workflow`', guide_text(), 'the workspace command that opens the workflow map is named')
        self.assertIn('`:catalog`', guide_text())

    def test_every_command_of_the_quickstart_is_run_by_the_demonstration_script(self):
        script = squashed(DEMO.read_text())
        interactive = {'intune-iac workbench workspace --root demo/store --service-root demo/service'}
        commands = [line for block in code_blocks(guide_section('Quickstart with the bundled sample data')) for line in block
                    if 'intune-iac' in line]
        self.assertGreaterEqual(len(commands), 12)
        for command in commands:
            if command not in interactive:
                self.assertIn(squashed(command), script, 'the script does not run: ' + command)

    def test_the_guide_shows_the_enforced_wheel_digest_and_says_why_it_matters(self):
        section = squashed(guide_section('Check a clean install end to end'))
        for phrase in ('--pip-wheel-sha256', 'ba0d021a166865d2265246961bec0152ff124de910c5cc39f1156ce3fa7c69dc',
                       'runs as code', 'before it creates anything', 'CPython 3.11.9'):
            self.assertIn(phrase, section)

    def test_the_script_commands_in_the_guide_are_accepted_by_the_scripts_own_argument_parser(self):
        import shlex
        commands = [line for block in code_blocks(guide_text()) for line in block
                    if line.startswith('bash scripts/demo-clean-install.sh')]
        self.assertGreaterEqual(len(commands), 2)
        self.assertTrue(any('--pip-wheel-sha256' in command for command in commands))
        with tempfile.TemporaryDirectory() as directory:
            for command in commands:
                with self.subTest(command=command):
                    # The guide names the archive digest by a placeholder, which the script would rightly refuse as not hex.
                    tokens = ['0' * 64 if token == 'RELEASE_RECORD_ARCHIVE_SHA256' else token for token in shlex.split(command)[2:]]
                    result = subprocess.run(['bash', str(DEMO), *tokens], cwd=directory, capture_output=True,
                                            text=True, env={'PATH': os.environ['PATH']}, timeout=60)
                    # The placeholder paths do not exist, so the first refusal is the archive: every option was accepted.
                    self.assertEqual(result.returncode, 64, result.stdout + result.stderr)
                    self.assertIn('ARCHIVE is not a file', result.stderr)
                    self.assertNotIn('Usage:', result.stderr)

    def test_the_sample_data_section_names_what_the_estate_is_made_of(self):
        section = guide_section('The sample data')
        for phrase in ('examples/supported/input/export.json', 'examples/context.json', SAMPLE_TENANT, SAMPLE_POLICY,
                       'synthetic', 'modeled service', 'seed 42'):
            self.assertIn(phrase, section)

    def test_the_support_limits_state_each_boundary_plainly(self):
        section = squashed(guide_section('Support limits')).lower()
        for phrase in ('synthetic and modeled evidence only', 'no live tenant, ci or cloud write',
                       'native windows and powershell are not qualified', 'g13', 'denied', 'docs/external-gates-r4.md',
                       'cloud_apply', 'live_qualified'):
            self.assertIn(phrase, section)

    def test_troubleshooting_names_the_ensurepip_failure_and_both_remedies(self):
        section = squashed(guide_section('Troubleshooting'))
        for phrase in ('python3 -m venv', 'ensurepip is not available', 'python3.12-venv', '--pip-wheel', '--without-pip',
                       'scripts/demo-clean-install.sh'):
            self.assertIn(phrase, section)
        self.assertIn('ensurepip', squashed(guide_section('Install')), 'the install section points at the way out')

    def test_every_refusal_the_guide_names_is_a_code_the_product_can_raise(self):
        import re
        sources = ''.join(path.read_text(encoding='utf-8') for path in sorted((ROOT / 'intune_iac').glob('*.py')))
        named = {span for span in re.findall(r'`([^`\n]+)`', guide_text()) if re.fullmatch(r'[a-z][a-z0-9]*(?:_[a-z0-9]+)+', span)}
        for code in ('invalid_request', 'output_conflict', 'workbench_object_missing', 'model_service_missing',
                     'capture_token_missing', 'cli_not_found', 'service_runtime_symlink'):
            self.assertIn(code, named, 'the troubleshooting section should explain ' + code)
        for code in sorted(named):
            self.assertIn(code, sources, 'the guide names ' + code + ' and no module of the product holds it')

    def test_the_issue_channel_is_marked_as_awaiting_the_owner_and_invents_no_address(self):
        import re
        section = guide_section('Reporting an issue')
        marker = "awaiting the owner's choice"
        self.assertEqual(sum(marker in s for s in re.split(r'(?<=[.!?])\s+', squashed(section))), 1, 'one sentence says it')
        self.assertTrue(squashed(section).startswith('**') and marker in squashed(section).split('**')[1],
                        'the sentence opens the section, in bold')
        self.assertNotRegex(section, r'@|https?://|www\.|mailto:')


class GuideBehaviourTests(unittest.TestCase):
    """Each claim the guide makes about what a command prints is checked against the product, run from a folder that
    holds only the sample data the runtime archive holds."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.temp.name)
        for name in ARCHIVE_EXAMPLES:
            (cls.work / name).parent.mkdir(parents=True, exist_ok=True)
            (cls.work / name).write_bytes((ROOT / name).read_bytes())
        (cls.work / 'home').mkdir(mode=0o700)
        (cls.work / 'demo').mkdir(mode=0o700)
        (cls.work / 'no-cli').mkdir()
        for arguments in (('workbench', 'lab-create', '--service-root', 'demo/service', '--input',
                           'examples/supported/input/export.json', '--object', SAMPLE_POLICY),
                          ('workbench', 'init', '--root', 'demo/store', '--tenant', SAMPLE_TENANT),
                          ('workbench', 'collect', '--root', 'demo/store', '--service-root', 'demo/service')):
            result = cls.run_cli(*arguments)
            if result.returncode != 0:
                raise AssertionError('building the sample estate failed: %s %s' % (arguments, result.stdout + result.stderr))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def run_cli(cls, *arguments, search_path=None):
        environment = {'PATH': os.environ['PATH'] if search_path is None else search_path, 'LANG': 'C.UTF-8',
                       'HOME': str(cls.work / 'home'), 'COLUMNS': '100'}
        return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/intune-iac.py'), *arguments], cwd=cls.work,
                              capture_output=True, text=True, env=environment, timeout=120)

    # (what the guide shows, the command, the exit status the guide states, what the guide quotes of the output)
    CLAIMS = (
        ('start', ('start', 'examples'), 0,
         ('INTUNE WORKBENCH: START', 'FOUND', 'NEXT', 'MISSING', 'discovered', 'usable here', 'source-asserted',
          'synthetic only', 'No live discovery connection is configured: offline inspection and preparation remain available.')),
        ('start goal', ('start', 'examples', '--goal', 'inspect'), 0, ('GOAL READINESS: inspect (status: ready)',)),
        ('signin', ('signin', 'status', '--tenant', SAMPLE_TENANT), 2,
         ('AZURE: BLOCKED (unknown: cli_not_found)', 'Exit code 2: blocked (0 means ready).')),
        ('start demo', ('start', 'demo'), 0, ('Store', 'Service', 'Open the workspace')),
        ('catalog', ('catalog', 'demo'), 0,
         ('INTEGRATION CATALOG', 'No other integration is available in this build.', 'GOAL inspect', 'GOAL discover',
          'GOAL adopt', 'GOAL change', 'operation-ready', 'unsupported', 'against the modeled service only; no cloud route exists')),
        ('workflow', ('workbench', 'workflow', '--root', 'demo/store', '--policy', SAMPLE_POLICY, '--service-root', 'demo/service'), 0,
         ('[WORKFLOW]', 'Position: observe', 'not recorded', 'This view is read-only')),
        ('engineering', ('engineering',), 0, ('Engineering records are not configured',)),
    )

    def test_each_command_answers_as_the_guide_says(self):
        guide = squashed(guide_text())
        for name, arguments, status, quoted in self.CLAIMS:
            with self.subTest(name):
                result = self.run_cli(*arguments, search_path=str(self.work / 'no-cli') if name == 'signin' else None)
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                screen = squashed(result.stdout)
                for phrase in quoted:
                    self.assertIn(phrase, screen, 'the product no longer prints: ' + phrase)
                    self.assertIn(phrase, guide, 'the guide does not quote: ' + phrase)

    def test_the_larger_estate_adds_a_second_tenant_as_the_guide_says(self):
        import shutil
        phrase = 'Two tenants are named by the surveyed inputs; choose one.'
        shutil.copytree(self.work / 'demo', self.work / 'demo2', symlinks=True)
        made = self.run_cli('synthetic', 'generate', '--output', 'demo2/estate', '--policies', '3')
        self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
        self.assertIn('"synthetic": true', made.stdout)
        self.assertIn(phrase, squashed(self.run_cli('catalog', 'demo2').stdout))
        self.assertIn(phrase, squashed(guide_text()), 'the guide does not quote: ' + phrase)

    def test_the_commands_the_guide_shows_for_these_claims_are_the_ones_tested(self):
        shown = {' '.join(tokens) for tokens in guide_commands(guide_text())}
        for name, arguments, status, quoted in self.CLAIMS:
            self.assertIn(' '.join(arguments), shown, name)

    def test_the_refusals_the_guide_explains_are_what_the_product_answers(self):
        cases = (
            (('workbench', 'workflow', '--root', 'demo/store', '--policy', '99999999-9999-4999-8999-999999999999'), 3,
             'workbench_object_missing'),
            (('workbench', 'collect', '--root', 'demo/store', '--service-root', 'demo/nowhere'), 3, 'model_service_missing'),
            (('workbench', 'init', '--root', 'demo/store', '--tenant', SAMPLE_TENANT), 3, 'invalid_request'),
            (('capture', '--tenant', SAMPLE_TENANT, '--policy', SAMPLE_POLICY, '--output', 'demo/capture-out'), 3,
             'capture_token_missing'),
        )
        guide = guide_text()
        for arguments, status, code in cases:
            with self.subTest(code):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                self.assertIn(code, result.stderr)
                self.assertIn(code, guide)
        usage = self.run_cli('signin', 'status', '--tenant', 'not-a-guid')
        self.assertEqual(usage.returncode, 2)
        self.assertIn('invalid value (the value is not shown)', squashed(guide_text()))
        self.assertIn('invalid value (the value is not shown)', usage.stderr)


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

    def run_script(self, *args, cwd=None, trusted=True):
        """Run the script. It requires the archive's digest as a fourth argument: unless a test says `trusted=False`, a run
        of ARCHIVE, WHEEL_FOLDER and WORK_FOLDER is given the digest of the archive it names."""
        args = list(map(str, args))
        if trusted and len(args) == 3 and not args[0].startswith('-'):
            args.append(sha256(Path(args[0]).read_bytes()))
        environment = {'PATH': os.environ['PATH'], 'LANG': 'C.UTF-8'}
        return subprocess.run(['bash', str(DEMO), *args], cwd=cwd or self.outside, capture_output=True, text=True,
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
STUB_PRODUCT = '''import json, shutil, sys
args = sys.argv[1:]
if args == ['--version']:
    print('0.9.0')
elif args[:1] == ['doctor']:
    print(json.dumps({'status': 'ready', 'build': {'status': 'identified', 'product_version': '0.9.0',
                                                    'commit': None, 'content_sha256': '0' * 64}}))
elif args[:2] == ['signin', 'status']:
    # A host with an Azure CLI on the search path answers differently, so a step that is not given an empty search path fails.
    if shutil.which('az'):
        print('AZURE: READY (the stand-in found an az on the search path)')
    else:
        print('AZURE: BLOCKED (unknown: cli_not_found)')
        print('Exit code 2: blocked (0 means ready).')
        sys.exit(2)
else:
    print('INTUNE WORKBENCH: START Export Context No live discovery connection is configured '
          'GOAL READINESS: inspect (status: ready) Store Service Journey Generated Open the workspace '
          'INTEGRATION CATALOG No other integration is available in this build. GOAL change '
          '[WORKFLOW] Position: observe This view is read-only Engineering records are not configured '
          '"status": "complete_simulation" "execution_authorized": false "synthetic": true '
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
        self.tmp = self.base / 'tmp'     # the script's TMPDIR: the folder it stages its copies in
        self.tmp.mkdir()
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
        self.az_log = self.base / 'az-calls.log'
        # An Azure CLI on the host's search path: the sign-in step must not see it.
        self.host_bin = self.base / 'host-bin'
        self.host_bin.mkdir()
        (self.host_bin / 'az').write_text('#!/bin/sh\necho "az $*" >> "$FAKE_AZ_LOG"\nexit 0\n')
        (self.host_bin / 'az').chmod(0o755)

    def run_script(self, *args, ensurepip='missing', trusted=True):
        """Run the script. The script requires the archive's digest and, with a pip wheel, the wheel's: unless a test says
        `trusted=False`, a run that gives neither is given the digest of the first path it names (the archive) and of
        `self.pip_wheel`, so the tests of the install path need not repeat them."""
        args = list(map(str, args))
        if trusted:
            positional, skip = [], False
            for argument in args:
                if skip:
                    skip = False
                elif argument in ('--pip-wheel', '--pip-wheel-sha256'):
                    skip = True
                elif not argument.startswith('--'):
                    positional.append(argument)
            wheel_given = any(a == '--pip-wheel' or a.startswith('--pip-wheel=') for a in args)
            if wheel_given and not any(a.startswith('--pip-wheel-sha256') for a in args):
                args += ['--pip-wheel-sha256', sha256(self.pip_wheel.read_bytes())]
            if len(positional) == 3:
                args.append(sha256(Path(positional[0]).read_bytes()))
        environment = {'PATH': f'{self.host_bin}:{os.environ["PATH"]}', 'LANG': 'C.UTF-8', 'PYTHON': str(self.interpreter),
                       'REAL_PYTHON': sys.executable, 'FAKE_ENSUREPIP': ensurepip, 'FAKE_LOG': str(self.log),
                       'FAKE_PIP_LOG': str(self.pip_log), 'FAKE_AZ_LOG': str(self.az_log), 'TMPDIR': str(self.tmp)}
        return subprocess.run(['bash', str(DEMO), *args], cwd=self.outside, capture_output=True, text=True,
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
        # The wheel that runs is the copy made in the script's private staging folder, not the file that was named.
        staged = re.escape(f'{self.tmp}') + r'/intune-iac-stage\.\w+/wheel/' + re.escape(self.pip_wheel.name) + '/pip'
        calls = self.pip_calls()
        self.assertEqual(len(calls), 2, calls)
        self.assertRegex(calls[0], f'^wheel-pip {staged} ' + re.escape(self.install_arguments()) + '$')
        self.assertRegex(calls[1], f'^wheel-pip {staged} ' + re.escape('--isolated check') + '$')
        self.assertIn('RESULT: every step passed.', result.stdout)

    def test_the_sign_in_step_runs_with_no_search_path_so_a_hosts_az_is_never_called(self):
        result = self.run_script('--pip-wheel', self.pip_wheel, self.archive, self.wheels, self.base / 'work')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = next(line for line in result.stdout.splitlines() if line.startswith('signin-status'))
        self.assertIn('PASS', row)
        self.assertIn('exit 2', row)
        self.assertFalse(self.az_log.exists() and self.az_log.read_text(), 'the host az was called')
        logs = sorted((self.base / 'work/logs').glob('*-signin-status.txt'))
        self.assertEqual(len(logs), 1)
        self.assertIn('cli_not_found', logs[0].read_text())

    def test_every_quickstart_step_ran_and_passed_in_the_guides_order(self):
        result = self.run_script('--pip-wheel', self.pip_wheel, self.archive, self.wheels, self.base / 'work')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = [line.split()[0] for line in result.stdout.split('Summary\n', 1)[1].splitlines() if line.split() and line.split()[1:2] == ['PASS']]
        steps = ['demo-folder', 'version', 'doctor', 'start', 'start-goal', 'signin-status', 'wizard', 'lab-create', 'store-init',
                 'collect', 'start-demo', 'catalog', 'workspace', 'workflow', 'engineering', 'families', 'synthetic-estate',
                 'build-identity']
        self.assertEqual([name for name in rows if name in steps], steps)

    def test_the_wheels_sha256_is_printed_next_to_the_archives(self):
        result = self.run_script('--pip-wheel', self.pip_wheel, self.archive, self.wheels, self.base / 'work')
        self.assertIn('pip wheel sha256: ' + sha256(self.pip_wheel.read_bytes()), result.stdout)
        self.assertIn('archive sha256: ' + sha256(self.archive.read_bytes()), result.stdout)

    def test_the_option_may_follow_the_arguments_and_take_an_equals_sign(self):
        result = self.run_script(self.archive, self.wheels, self.base / 'work', f'--pip-wheel={self.pip_wheel}')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.venv_calls(), ['venv -m venv --without-pip .venv'])

    def test_the_wheel_runs_from_a_staged_copy_that_is_not_left_behind_and_the_named_file_is_untouched(self):
        before = self.pip_wheel.read_bytes()
        result = self.run_script('--pip-wheel', self.pip_wheel, self.archive, self.wheels, self.base / 'work')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(list((self.base / 'work').rglob('*.whl')), [], 'the copy is not left in the work folder')
        self.assertEqual(list(self.tmp.iterdir()), [], 'the staging folder is removed when the script ends')
        self.assertEqual(self.pip_wheel.read_bytes(), before)

    # --pip-wheel-sha256: the wheel runs as code, so the caller can say which file it must be.
    def wheel_digest(self):
        return sha256(self.pip_wheel.read_bytes())

    def quick_archive(self):
        """A verified archive that is not a runtime archive: once every argument is accepted the script reads on to exit 3."""
        members = {'README.md': 'a verified archive without the product\n'}
        members['SHA256SUMS'] = ''.join(f'{sha256(text.encode())}  {name}\n' for name, text in sorted(members.items()))
        path = self.base / 'plain.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, text in members.items():
                archive.writestr('intune-iac/' + name, text)
        return path

    def listing(self):
        return sorted(p.name for p in self.base.iterdir()), sorted(p.name for p in self.outside.iterdir())

    def test_a_matching_digest_is_accepted_and_the_whole_run_passes(self):
        digest = self.wheel_digest()
        result = self.run_script('--pip-wheel', self.pip_wheel, '--pip-wheel-sha256', digest, self.archive, self.wheels,
                                 self.base / 'work')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('pip wheel sha256: ' + digest, result.stdout)
        self.assertIn('RESULT: every step passed.', result.stdout)
        self.assertEqual(self.venv_calls(), ['venv -m venv --without-pip .venv'])
        self.assertEqual(len(self.pip_calls()), 2)

    def test_the_digest_option_takes_either_spelling_and_either_order(self):
        digest = self.wheel_digest()
        quick = self.quick_archive()
        spellings = (('--pip-wheel', self.pip_wheel, '--pip-wheel-sha256', digest),
                     ('--pip-wheel-sha256', digest, '--pip-wheel', self.pip_wheel),
                     (f'--pip-wheel={self.pip_wheel}', f'--pip-wheel-sha256={digest}'))
        for index, options in enumerate(spellings):
            with self.subTest(index):
                result = self.run_script(*options, quick, self.wheels, self.base / f'quick{index}')
                # Every argument was accepted and the digest matched, so the run read on to the archive check.
                self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
                self.assertIn('not a runtime archive', result.stderr)
                self.assertIn('pip wheel sha256: ' + digest, result.stdout)

    def test_a_different_digest_is_refused_before_anything_is_created(self):
        digest = self.wheel_digest()
        flipped = digest[:-1] + ('0' if digest[-1] != '0' else '1')
        for name, expected in (('all zero', '0' * 64), ('one digit off', flipped)):
            with self.subTest(name):
                work = self.base / 'work'
                before = self.listing()
                result = self.run_script('--pip-wheel', self.pip_wheel, '--pip-wheel-sha256', expected, self.archive,
                                         self.wheels, work)
                self.assertEqual(result.returncode, 64, result.stdout + result.stderr)
                self.assertIn('expected ' + expected, result.stderr)
                self.assertIn('actual ' + digest, result.stderr)
                self.assertFalse(work.exists(), 'the work folder must not exist after a refusal')
                self.assertEqual(self.listing(), before, 'a refusal creates nothing')
                self.assertEqual((self.venv_calls(), self.pip_calls()), ([], []))
                self.assertNotIn('RESULT:', result.stdout)

    def test_a_malformed_digest_is_a_usage_error_and_nothing_is_created(self):
        digest = self.wheel_digest()
        cases = {'uppercase': digest.upper(), 'one short': digest[:-1], 'one long': digest + '0', 'not hex': 'g' * 64,
                 'empty': '', 'prefixed': 'sha256:' + digest, 'a space': digest[:32] + ' ' + digest[33:]}
        for name, value in cases.items():
            with self.subTest(name):
                work = self.base / 'work'
                before = self.listing()
                result = self.run_script('--pip-wheel', self.pip_wheel, '--pip-wheel-sha256', value, self.archive,
                                         self.wheels, work)
                self.assertEqual(result.returncode, 64, result.stdout + result.stderr)
                self.assertIn('--pip-wheel-sha256 must be 64 lowercase hex digits', result.stderr)
                self.assertIn('Usage:', result.stderr)
                self.assertEqual(self.listing(), before)
                self.assertEqual((self.venv_calls(), self.pip_calls()), ([], []))
        with self.subTest('no value'):
            result = self.run_script('--pip-wheel', self.pip_wheel, self.archive, self.wheels, self.base / 'work',
                                     '--pip-wheel-sha256', trusted=False)
            self.assertEqual(result.returncode, 64, result.stdout + result.stderr)
            self.assertIn('--pip-wheel-sha256 needs a value', result.stderr)
            self.assertFalse((self.base / 'work').exists())

    def test_the_digest_without_a_wheel_is_a_usage_error_and_nothing_is_created(self):
        work = self.base / 'work'
        before = self.listing()
        for name, options in (('separate', ('--pip-wheel-sha256', self.wheel_digest())),
                              ('equals sign', (f'--pip-wheel-sha256={self.wheel_digest()}',))):
            with self.subTest(name):
                result = self.run_script(*options, self.archive, self.wheels, work, ensurepip='present')
                self.assertEqual(result.returncode, 64, result.stdout + result.stderr)
                self.assertIn('--pip-wheel-sha256 needs --pip-wheel', result.stderr)
                self.assertIn('Usage:', result.stderr)
                self.assertEqual(self.listing(), before)
                self.assertEqual((self.venv_calls(), self.pip_calls()), ([], []))

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

    def test_usage_names_the_options_and_the_comment_says_when_to_use_them(self):
        usage = self.run_script().stderr
        self.assertIn('[--pip-wheel PATH --pip-wheel-sha256 HEX]', usage)
        header = '\n'.join(DEMO.read_text().splitlines()[:40])
        self.assertIn('--pip-wheel', header)
        self.assertIn('ensurepip', header)
        self.assertIn('--pip-wheel-sha256', header)
        self.assertIn('runs as code', header)


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
