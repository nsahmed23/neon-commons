"""The release candidate after Sol's review (PKG-RELEASE-1 round 3): what the demonstration script, the archive check, the identity
and the sensitive-file control must refuse. The first module of this package, test_release_candidate, holds the earlier tests; this
one starts where that one passed 1,000 lines and imports its stand-ins and helpers.
"""
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from plugin_tests import test_release_candidate as base

ROOT = base.ROOT
DEMO = base.DEMO
sha256 = base.sha256
squashed = base.squashed
guide_section = base.guide_section
code_blocks = base.code_blocks
LOCK = base.LOCK

# A stand-in for sha256sum that does what the real one does and, at the points a test names, changes the files the script is
# about to use. It counts its calls in SHIM_STATE; after call SHIM_SWAP_AFTER it replaces the caller's own files (the named
# paths, by rename, in place or by deletion, as SHIM_SWAP_MODE says); and on call SHIM_TAMPER_CALL for a file whose name is
# SHIM_TAMPER_NAME it overwrites that file before it is read. It also records the mode of the folder holding each file it hashes.
SHA256SUM_SHIM = '''#!/bin/sh
state=$SHIM_STATE
count=$(cat "$state/count" 2>/dev/null || echo 0)
count=$((count + 1))
echo "$count" > "$state/count"
for argument in "$@"; do
    if [ -f "$argument" ]; then
        echo "$(stat -c %a "$(dirname "$argument")") $argument" >> "$state/modes"
        if [ -n "${SHIM_TAMPER_NAME:-}" ] && [ "$(basename "$argument")" = "$SHIM_TAMPER_NAME" ]; then
            named=$(cat "$state/named" 2>/dev/null || echo 0)
            named=$((named + 1))
            echo "$named" > "$state/named"
            if [ "$named" = "$SHIM_TAMPER_CALL" ]; then cp "$SHIM_TAMPER_WITH" "$argument"; fi
        fi
    fi
done
out=$("$SHIM_REAL" "$@")
status=$?
if [ "$count" = "${SHIM_SWAP_AFTER:-0}" ]; then
    for pair in "$SHIM_SWAP_1" "$SHIM_SWAP_2"; do
        target=${pair%%|*}
        replacement=${pair#*|}
        case "$SHIM_SWAP_MODE" in
            rename) mv "$replacement" "$target" ;;
            overwrite) cp "$replacement" "$target" ;;
            delete) rm -f "$target" ;;
        esac
    done
fi
[ -z "$out" ] || printf '%s\\n' "$out"
exit $status
'''


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

    def shim(self, **settings):
        """Put the sha256sum stand-in first on the search path; `settings` become its SHIM_* variables. Returns the extra
        environment for run_script and the folder where this stand-in keeps its records (a new folder on every call)."""
        state = Path(tempfile.mkdtemp(prefix='shim-state-', dir=self.base))
        folder = self.base / 'shim-bin'
        folder.mkdir(exist_ok=True)
        (folder / 'sha256sum').write_text(SHA256SUM_SHIM)
        (folder / 'sha256sum').chmod(0o755)
        environment = {'PATH': f'{folder}:{os.environ["PATH"]}', 'SHIM_STATE': str(state), 'SHIM_REAL': shutil.which('sha256sum'),
                       'SHIM_SWAP_1': '|', 'SHIM_SWAP_2': '|', 'SHIM_SWAP_MODE': 'rename'}
        environment.update({'SHIM_' + name.upper(): str(value) for name, value in settings.items()})
        return environment, state

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

    def assertRefusedBeforeAnything(self, result, before, status=64, work='work'):
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        self.assertFalse((self.base / work).exists(), 'the work folder must not exist after a refusal')
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


class StagingTests(ScriptCase):
    """Item 2: the archive and the wheel are copied once, before any check, into a folder only this run can enter, and every
    check and use after that reads the copies. A check of the named path followed by a second read of it would leave a window
    in which the file could be swapped for another one."""

    def another_archive(self, name='other.zip', version='SWAPPED-0.9.0'):
        return self.make_archive(self.base / name, product=base.STUB_PRODUCT.replace("print('0.9.0')", f"print('{version}')"))

    def another_wheel(self, name='other.whl'):
        return self.make_wheel(self.base / name, main=base.FAKE_PIP_MAIN.replace("'wheel-pip '", "'SWAPPED-wheel-pip '"))

    def forget_earlier_runs(self):
        for path in (self.log, self.pip_log):
            path.unlink(missing_ok=True)

    def test_what_runs_is_the_copy_made_before_any_check_whatever_happens_to_the_named_files(self):
        for mode in ('rename', 'overwrite', 'delete'):
            with self.subTest(mode):
                work = 'work-' + mode
                self.forget_earlier_runs()
                self.make_archive(self.archive)
                self.make_wheel(self.pip_wheel)
                environment, state = self.shim(swap_after=2, swap_mode=mode, swap_1=f'{self.archive}|{self.another_archive()}',
                                               swap_2=f'{self.pip_wheel}|{self.another_wheel()}')
                result = self.run_script(*self.complete(work), env=environment)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                changed = (not self.archive.exists()) if mode == 'delete' else (
                    b'SWAPPED' in zipfile.ZipFile(self.archive).read('intune-iac/scripts/intune-iac.py'))
                self.assertTrue(changed, 'the stand-in did not change the named archive, so this run proves nothing')
                logs = self.base / work / 'logs'
                version = next(logs.glob('*-version.txt')).read_text()
                self.assertIn('0.9.0', version)
                self.assertNotIn('SWAPPED', version, 'the archive that ran is not the one that was checked')
                pip_calls = self.calls()[1]
                self.assertTrue(pip_calls and all(line.startswith('wheel-pip ') for line in pip_calls),
                                'the wheel that ran is not the one that was checked: ' + repr(pip_calls))

    def test_a_staged_copy_that_changes_after_it_was_verified_is_refused_before_it_is_used(self):
        digest = self.archive_digest()
        cases = {'archive': ('archive.zip', self.another_archive, 3, 'the staged archive changed after it was verified'),
                 'wheel': (self.pip_wheel.name, self.another_wheel, 64, 'the staged pip wheel changed after it was verified')}
        for name, (staged_name, replacement, status, message) in cases.items():
            with self.subTest(name):
                self.forget_earlier_runs()
                environment, _ = self.shim(tamper_name=staged_name, tamper_call=2, tamper_with=replacement())
                result = self.run_script(*self.complete('work-' + name), env=environment)
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                self.assertIn(message, result.stderr)
                self.assertNotIn('RESULT: every step passed.', result.stdout)
                self.assertEqual(self.listing()[2], [], 'the staging folder is removed when the script ends')
        self.assertEqual(digest, self.archive_digest())

    def test_a_symbolic_link_or_a_special_file_is_not_an_input(self):
        link_archive = self.base / 'archive-link.zip'
        link_archive.symlink_to(self.archive)
        link_wheel = self.base / 'wheel-link.whl'
        link_wheel.symlink_to(self.pip_wheel)
        fifo = self.base / 'wheel.fifo'
        os.mkfifo(fifo)
        wheel_options = ['--pip-wheel', self.pip_wheel, '--pip-wheel-sha256', self.wheel_digest()]
        cases = {'the archive is a link': (wheel_options + [link_archive], 'ARCHIVE is a symbolic link'),
                 'the archive is a folder': (wheel_options + [self.wheels], 'ARCHIVE is not a file'),
                 'the wheel is a link': (['--pip-wheel', link_wheel, '--pip-wheel-sha256', self.wheel_digest(), self.archive],
                                         'the --pip-wheel path is a symbolic link'),
                 'the wheel is a pipe': (['--pip-wheel', fifo, '--pip-wheel-sha256', self.wheel_digest(), self.archive],
                                         'the --pip-wheel path is not a file')}
        for number, (name, (arguments, message)) in enumerate(cases.items()):
            with self.subTest(name):
                work = f'work-{number}'
                self.forget_earlier_runs()
                before = self.listing()
                result = self.run_script(*arguments, self.wheels, self.base / work, self.archive_digest())
                self.assertRefusedBeforeAnything(result, before, work=work)
                self.assertIn(message, result.stderr)

    def test_the_copies_live_in_a_private_folder_that_is_gone_when_the_script_ends(self):
        failing = self.make_archive(self.base / 'failing.zip', product=base.STUB_PRODUCT.replace("print('0.9.0')", "print('0.9.0'); sys.exit(1)"))
        outcomes = {'a pass': (self.complete('work-pass'), 0),
                    'a wrong archive digest': (self.complete()[:-1] + ['0' * 64], 3),
                    'a step that fails': (['--pip-wheel', self.pip_wheel, '--pip-wheel-sha256', self.wheel_digest(), failing,
                                           self.wheels, self.base / 'work-fail', sha256(failing.read_bytes())], 1)}
        for name, (arguments, status) in outcomes.items():
            with self.subTest(name):
                environment, state = self.shim()
                result = self.run_script(*arguments, env=environment)
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                self.assertEqual(self.listing()[2], [], 'nothing is left in the temporary folder')
                modes = [line.split(' ', 1) for line in (state / 'modes').read_text().splitlines()]
                staged = [(mode, path) for mode, path in modes if path.startswith(str(self.tmp) + '/')]
                self.assertTrue(staged, 'no file was hashed inside the temporary folder: ' + repr(modes))
                self.assertEqual({mode for mode, _ in staged}, {'700'}, 'the staging folder is private to this run')
                self.assertEqual({Path(path).name for _, path in staged} >= {'archive.zip', self.pip_wheel.name}, True)
                self.assertFalse(any(path.startswith(str(self.base / 'work')) for _, path in staged))


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
                       'private temporary folder', 'symbolic link'):
            self.assertIn(phrase, section)
        for endorsement in ('runs the wheel anyway', 'a fourth argument', 'optional'):
            self.assertNotIn(endorsement, section)


if __name__ == '__main__':
    unittest.main()
