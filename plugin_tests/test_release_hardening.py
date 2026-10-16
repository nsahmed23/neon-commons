"""The release candidate after Sol's review (PKG-RELEASE-1 round 3): what the demonstration script, the archive check, the identity
and the sensitive-file control must refuse. The first module of this package, test_release_candidate, holds the earlier tests; this
one starts where that one passed 1,000 lines and imports its stand-ins and helpers.
"""
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from plugin_tests import test_release_candidate as base

ROOT = base.ROOT
DEMO = base.DEMO
sha256 = base.sha256
squashed = base.squashed
guide_section = base.guide_section
code_blocks = base.code_blocks
LOCK = base.LOCK


class ScriptCase(unittest.TestCase):
    """The demonstration script against a stand-in runtime archive, a fake pip wheel and an interpreter stand-in. Nothing
    installs: the stand-in archive holds a stub product, the fake wheel logs how it was called."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.outside = self.base / 'outside'
        self.outside.mkdir()
        self.wheels = self.base / 'wheels'
        self.wheels.mkdir()
        self.tmp = self.base / 'tmp'              # TMPDIR of the script: whatever it stages must be gone when it ends
        self.tmp.mkdir()
        self.archive = self.make_archive(self.base / 'stand-in-runtime.zip')
        self.pip_wheel = self.make_wheel(self.base / 'pip-0.0-py3-none-any.whl')
        self.interpreter = self.base / 'interpreter'
        self.interpreter.write_text(base.FAKE_INTERPRETER)
        self.interpreter.chmod(0o755)
        self.log = self.base / 'calls.log'
        self.pip_log = self.base / 'pip-calls.log'

    def make_archive(self, path, product=None):
        members = {'scripts/intune-iac.py': product or base.STUB_PRODUCT, 'scripts/verify-dependencies.py': base.STUB_VERIFY,
                   LOCK: '# a stand-in lock: these tests run the plumbing, not an install\n'}
        members['SHA256SUMS'] = ''.join(f'{sha256(text.encode())}  {name}\n' for name, text in sorted(members.items()))
        with zipfile.ZipFile(path, 'w') as archive:
            for name, text in members.items():
                archive.writestr('intune-iac/' + name, text)
        return path

    def make_wheel(self, path, main=None):
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('pip/__init__.py', '')
            archive.writestr('pip/__main__.py', main or base.FAKE_PIP_MAIN)
        return path

    def archive_digest(self):
        return sha256(self.archive.read_bytes())

    def wheel_digest(self):
        return sha256(self.pip_wheel.read_bytes())

    def complete(self, work='work'):
        """A complete argument list: the wheel with its digest, the archive with its digest."""
        return ['--pip-wheel', self.pip_wheel, '--pip-wheel-sha256', self.wheel_digest(), self.archive, self.wheels,
                self.base / work, self.archive_digest()]

    def run_script(self, *args, ensurepip='missing', env=None, cwd=None):
        environment = {'PATH': os.environ['PATH'], 'LANG': 'C.UTF-8', 'PYTHON': str(self.interpreter),
                       'REAL_PYTHON': sys.executable, 'FAKE_ENSUREPIP': ensurepip, 'FAKE_LOG': str(self.log),
                       'FAKE_PIP_LOG': str(self.pip_log), 'TMPDIR': str(self.tmp)}
        environment.update(env or {})
        return subprocess.run(['bash', str(DEMO), *map(str, args)], cwd=cwd or self.outside, capture_output=True, text=True,
                              env=environment, timeout=180)

    def listing(self):
        """Everything the script could have left: the test folder, the folder it runs in and its temporary folder."""
        return (sorted(p.name for p in self.base.iterdir()), sorted(p.name for p in self.outside.iterdir()),
                sorted(p.name for p in self.tmp.iterdir()))

    def calls(self):
        return ((self.log.read_text().splitlines() if self.log.exists() else []),
                (self.pip_log.read_text().splitlines() if self.pip_log.exists() else []))

    def assertRefusedBeforeAnything(self, result, before, status=64):
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        self.assertFalse((self.base / 'work').exists(), 'the work folder must not exist after a refusal')
        self.assertEqual(self.listing(), before, 'a refusal creates nothing and leaves no staging folder behind')
        self.assertEqual(self.calls(), ([], []), 'no environment is made and nothing is installed')


class RequiredDigestTests(ScriptCase):
    """Item 1: an archive carries its own SHA256SUMS and a pip wheel runs as code, so neither runs on trust."""

    def test_a_run_with_both_digests_passes(self):
        result = self.run_script(*self.complete())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('RESULT: every step passed.', result.stdout)

    def test_the_archive_digest_is_required(self):
        before = self.listing()
        for name, arguments in (('a wheel with its digest', self.complete()[:-1]),
                                ('no wheel', [self.archive, self.wheels, self.base / 'work'])):
            with self.subTest(name):
                result = self.run_script(*arguments)
                self.assertRefusedBeforeAnything(result, before)
                self.assertIn('EXPECTED_ARCHIVE_SHA256 is required', result.stderr)
                self.assertIn('REFUSED:', result.stderr)

    def test_a_malformed_archive_digest_is_a_usage_error_and_nothing_is_created(self):
        digest = self.archive_digest()
        before = self.listing()
        for name, value in {'uppercase': digest.upper(), 'one short': digest[:-1], 'one long': digest + '0',
                            'not hex': 'g' * 64, 'empty': '', 'prefixed': 'sha256:' + digest}.items():
            with self.subTest(name):
                result = self.run_script(*self.complete()[:-1], value)
                self.assertRefusedBeforeAnything(result, before)
                self.assertIn('EXPECTED_ARCHIVE_SHA256 must be 64 lowercase hex digits', result.stderr)
                self.assertIn('Usage:', result.stderr)

    def test_a_wheel_without_its_digest_is_refused_and_nothing_is_created(self):
        before = self.listing()
        for name, options in (('separate', ['--pip-wheel', self.pip_wheel]), ('equals sign', [f'--pip-wheel={self.pip_wheel}'])):
            with self.subTest(name):
                result = self.run_script(*options, self.archive, self.wheels, self.base / 'work', self.archive_digest())
                self.assertRefusedBeforeAnything(result, before)
                self.assertIn('--pip-wheel needs --pip-wheel-sha256', result.stderr)
                self.assertIn('runs as code', result.stderr)

    def test_the_usage_line_shows_the_archive_digest_as_required(self):
        usage = self.run_script().stderr
        self.assertIn('WORK_FOLDER EXPECTED_ARCHIVE_SHA256', usage)
        self.assertNotIn('[EXPECTED_ARCHIVE_SHA256]', usage)


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
        for phrase in ('published release record', 'not from the line the script prints', 'refuses to run without'):
            self.assertIn(phrase, section)
        for endorsement in ('runs the wheel anyway', 'a fourth argument', 'optional'):
            self.assertNotIn(endorsement, section)


if __name__ == '__main__':
    unittest.main()
