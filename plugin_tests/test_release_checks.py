"""Checks on the release candidate that need no stand-in archive: the identity report of an installed copy when its record lies or
cannot be read, the guide's quickstart against the script's steps, and the guide's digest wording. They live apart from
test_release_hardening so that neither module passes 1,000 lines; the stand-ins and helpers come from test_release_candidate."""
import json
import re
import shlex
import unittest

from plugin_tests import test_release_candidate as base

DEMO = base.DEMO
sha256 = base.sha256
squashed = base.squashed
guide_section = base.guide_section
code_blocks = base.code_blocks


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
