"""Checks on the release candidate that need no stand-in archive: the identity report of an installed copy when its record lies or
cannot be read, the guide's quickstart against the script's steps, and the guide's digest wording. They live apart from
test_release_hardening so that neither module passes 1,000 lines; the stand-ins and helpers come from test_release_candidate."""
import json
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from plugin_tests import test_release_candidate as base

DEMO = base.DEMO
sha256 = base.sha256
squashed = base.squashed
guide_section = base.guide_section
code_blocks = base.code_blocks
WORKFLOW = base.ROOT / '.github/workflows/validate.yml'


class IdentityGapTests(unittest.TestCase):
    """A record that lies about its own file count or content digest while its SHA256SUMS line is brought along, and a record or
    listing that cannot be read, must each be reported."""

    def setUp(self):
        self.fixture = base.FixtureBuild(self)
        self.fixture.build()
        self.installed = self.fixture.extract('runtime')

    def report(self):
        from intune_iac import build_identity
        return build_identity.report(self.installed)

    def rewrite_record(self, **changes):
        """Edit the identity record and bring its SHA256SUMS line along, so that only what the record claims is wrong."""
        path = self.installed / base.IDENTITY
        record = json.loads(path.read_text())
        record.update(changes)
        data = (json.dumps(record, indent=2, sort_keys=True) + '\n').encode()
        path.write_bytes(data)
        sums = self.installed / 'SHA256SUMS'
        lines = [f'{sha256(data)}  {base.IDENTITY}' if line.endswith('  ' + base.IDENTITY) else line
                 for line in sums.read_text().splitlines()]
        sums.write_text('\n'.join(lines) + '\n')

    def test_a_record_that_claims_another_file_count_is_inconsistent(self):
        self.assertEqual(self.report()['status'], 'identified')
        self.rewrite_record(file_count=self.report()['file_count'] + 5)
        self.assertEqual(self.report()['status'], 'inconsistent')

    def test_a_record_that_claims_another_content_digest_is_inconsistent(self):
        self.rewrite_record(content_sha256='0' * 64)
        self.assertEqual(self.report()['status'], 'inconsistent')

    def test_a_record_or_listing_that_cannot_be_read_is_reported_and_never_raised(self):
        record = self.installed / base.IDENTITY
        good_record, sums = record.read_bytes(), self.installed / 'SHA256SUMS'
        good_sums = sums.read_bytes()
        cases = {'not json': (record, b'{not json'), 'not utf-8': (record, b'\xff\xfe\x00'), 'not an object': (record, b'[]'),
                 'missing keys': (record, b'{"schema_version": "build-identity/1"}'), 'a line that is no digest': (sums, b'garbage line\n'),
                 'a listing that is not utf-8': (sums, b'\xff\xfe')}
        for name, (path, data) in cases.items():
            with self.subTest(name):
                path.write_bytes(data)
                try:
                    value = self.report()
                except Exception as error:      # the point of the test: nothing may escape `doctor`
                    self.fail(f'report() raised {error!r}')
                finally:
                    record.write_bytes(good_record)
                    sums.write_bytes(good_sums)
                self.assertEqual(value['status'], 'unreadable')


class QuickstartCommandTests(unittest.TestCase):
    """The guide's quickstart code blocks and the script's steps are the same list of commands, in both directions."""

    def test_the_scripts_simple_steps_are_lines_of_the_guides_quickstart_and_doctor_is_one_of_them(self):
        section = guide_section('Quickstart with the bundled sample data')
        lines = {squashed(line) for block in code_blocks(section) for line in block if line.startswith('intune-iac ')}
        steps = re.findall(r'(?:^|\s)step (\S+) "(intune-iac [^"|]*)"', DEMO.read_text(), re.M)
        self.assertGreaterEqual(len(steps), 12)
        for name, command in steps:
            if name != 'build-identity':
                self.assertIn(squashed(command), lines, f'the script runs "{command}" and the guide does not show it')
        for needed in ('intune-iac --version', 'intune-iac doctor'):
            self.assertIn(needed, lines, 'the quickstart code blocks must show it')


class BytecodeCommandTests(unittest.TestCase):
    """Round 4, item 3: every start of a product script in the guide and in the demonstration script runs without writing
    bytecode, so that the copy stays identified, and the guide says that a cache in the product counts as an unlisted file."""

    START = re.compile(r'(?:python3?|\.venv/bin/python|"\$PYTHON")([^\n`|;]*?)scripts/(?:verify-dependencies|intune-iac)\.py')

    def test_every_start_of_a_product_script_passes_dash_B(self):
        starts = []
        for label, text in (('the guide', base.guide_text()), ('the script', DEMO.read_text())):
            starts += [(label, match.group(0)) for match in self.START.finditer(text)]
        self.assertGreaterEqual(len(starts), 4, starts)
        for label, start in starts:
            with self.subTest(start):
                self.assertTrue(re.search(r'(?:^|\s)-[A-Za-z]*B[A-Za-z]*\s', start),
                                f'{label} starts a product script that may write bytecode: {start}')

    def test_the_guide_says_that_a_cache_in_the_product_counts_and_that_its_commands_write_none(self):
        text = squashed(guide_section('Check the download'))
        for phrase in ('counts as an unlisted file', 'starts Python with `-B`', 'the `.venv` and `demo` folders'):
            self.assertIn(phrase, text)
        self.assertNotIn('and `__pycache__` folders', text)


class CiStepTests(unittest.TestCase):
    """Round 5: the CI step that rebuilt the archives from the extracted source and compared the zips byte for byte could not pass
    (built_at, commit and tree are in the identity) and the builder now refuses to make archives from a tree without a known commit.
    It checks the property it wanted instead: the extracted source reproduces the content digests the original archives record."""

    def steps(self):
        return yaml.safe_load(WORKFLOW.read_text())['jobs']['validate']['steps']

    def step(self):
        return next(step for step in self.steps() if step['id'] == 'extracted')

    def comparison(self):
        """(the file --check-only writes, the python the step runs on it) from the step's script."""
        found = re.search(r"--check-only[^\n]*> \"\$CI_ROOT/([^\"]+)\"\n\s*python - <<'PY'\n(.*?)\nPY\b", self.step()['run'], re.S)
        if not found:
            self.fail('the step does not run --check-only into a file and then compare what it reports')
        return found.group(1), found.group(2)

    def test_the_step_checks_content_digests_and_never_rebuilds_archives_from_the_extracted_tree(self):
        step = self.step()
        invocations = [(match.group(1), match.group(2)) for item in self.steps()
                       for match in re.finditer(r'(\S*extracted\S*/build-release\.py)"?\s+([^\n]*)', item.get('run', ''))]
        self.assertTrue(invocations, 'no step runs the extracted tree\'s builder')
        for path, arguments in invocations:
            self.assertTrue(arguments.startswith('--check-only'), arguments)
            self.assertNotIn('--output-dir', arguments)
        for needed in ('runtime_content_sha256', 'source_content_sha256', 'BUILD-IDENTITY.json', 'content_sha256'):
            self.assertIn(needed, step['run'])
        for gone in ('rebuilt', 'byte-identical', 'read_bytes() !='):
            self.assertNotIn(gone, step['run'])
        self.assertIn('content digests', step['name'], 'the name says what the step proves')
        self.assertEqual(step['id'], 'extracted')

    def ci_root(self, recorded_runtime='a' * 64, recorded_source='b' * 64, reported=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / 'release').mkdir()
        for name, prefix, digest in (('Intune_IaC_Plugin_0.9.0.zip', 'intune-iac', recorded_runtime),
                                     ('Intune_IaC_Plugin_0.9.0_Source.zip', 'intune-iac-source', recorded_source)):
            with zipfile.ZipFile(root / 'release' / name, 'w') as archive:
                archive.writestr(prefix + '/BUILD-IDENTITY.json', json.dumps({'content_sha256': digest}))
        report = {'runtime_content_sha256': 'a' * 64, 'source_content_sha256': 'b' * 64} if reported is None else reported
        (root / self.comparison()[0]).write_text(json.dumps(report))
        return root

    def compare(self, root):
        return subprocess.run([sys.executable, '-I', '-'], input=self.comparison()[1], capture_output=True, text=True, timeout=60,
                              env={'CI_ROOT': str(root), 'PATH': '/usr/bin:/bin'})

    def test_matching_digests_pass_and_the_run_says_what_it_compared(self):
        result = self.compare(self.ci_root())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('a' * 64, result.stdout)
        self.assertIn('b' * 64, result.stdout)

    def test_a_different_digest_fails_the_step_naming_both_digests(self):
        cases = {'runtime': ({'runtime_content_sha256': 'c' * 64, 'source_content_sha256': 'b' * 64}, 'a' * 64, 'c' * 64),
                 'source': ({'runtime_content_sha256': 'a' * 64, 'source_content_sha256': 'd' * 64}, 'b' * 64, 'd' * 64)}
        for kind, (reported, recorded, computed) in cases.items():
            with self.subTest(kind):
                result = self.compare(self.ci_root(reported=reported))
                self.assertNotEqual(result.returncode, 0, result.stdout)
                for text in (kind, recorded, computed):
                    self.assertIn(text, result.stderr + result.stdout)

    def test_the_ci_handoff_describes_the_comparison_and_no_longer_a_byte_for_byte_rebuild(self):
        text = squashed((base.ROOT / 'docs/CI.md').read_text(encoding='utf-8'))
        for phrase in ('`--check-only`', 'content digests', '`content_sha256`', '`BUILD-IDENTITY.json`'):
            self.assertIn(phrase, text)
        for gone in ('byte for byte', 'byte-identical'):
            self.assertNotIn(gone, text)

    def test_a_check_that_reports_no_digest_or_a_missing_archive_fails_instead_of_passing(self):
        self.assertNotEqual(self.compare(self.ci_root(reported={'status': 'PASS'})).returncode, 0)
        root = self.ci_root()
        (root / 'release/Intune_IaC_Plugin_0.9.0_Source.zip').unlink()
        self.assertNotEqual(self.compare(root).returncode, 0)


class GuideDigestTests(unittest.TestCase):
    """The guide shows only the forms the script accepts and says where a digest is to be taken from."""

    def script_lines(self):
        return [line for block in code_blocks(base.guide_text()) for line in block
                if line.startswith('bash scripts/demo-clean-install.sh')]

    def test_every_script_command_in_the_guide_carries_the_required_digests(self):
        lines = self.script_lines()
        self.assertGreaterEqual(len(lines), 2)
        for line in lines:
            with self.subTest(command=line[:70]):
                tokens = shlex.split(line)[2:]
                self.assertEqual('--pip-wheel' in tokens, '--pip-wheel-sha256' in tokens, 'a wheel and its digest go together')
                positional, skip = [], False
                for token in tokens:
                    if skip:
                        skip = False
                    elif token in ('--pip-wheel', '--pip-wheel-sha256'):
                        skip = True
                    elif not token.startswith('--'):
                        positional.append(token)
                self.assertEqual(len(positional), 4, 'ARCHIVE, WHEEL_FOLDER, WORK_FOLDER and the archive digest')
                self.assertTrue(positional[3] == 'RELEASE_RECORD_ARCHIVE_SHA256' or len(positional[3]) == 64, positional[3])

    def test_the_guide_says_where_each_digest_comes_from_and_endorses_no_unchecked_run(self):
        section = squashed(guide_section('Check a clean install end to end'))
        for phrase in ('published release record', 'not from the line the script prints', 'refuses to run without',
                       'private temporary folder', 'symbolic link', 'isolated (`python -I`)'):
            self.assertIn(phrase, section)
        for endorsement in ('runs the wheel anyway', 'a fourth argument', 'optional'):
            self.assertNotIn(endorsement, section)


if __name__ == '__main__':
    unittest.main()
