"""The release candidate after Sol's review (PKG-RELEASE-1 round 3): what the demonstration script, the archive check, the identity
and the sensitive-file control must refuse. The earlier tests are in test_release_candidate, whose stand-ins and helpers this uses."""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
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

# A stand-in for sha256sum that does what the real one does and, at the points a test names, changes the files the script is
# about to use. It counts its calls in SHIM_STATE; after call SHIM_SWAP_AFTER it replaces the caller's own files (by rename, in
# place or by deletion, as SHIM_SWAP_MODE says); on call SHIM_TAMPER_CALL for a file named SHIM_TAMPER_NAME it overwrites that
# file before it is read; and it records the mode of the folder holding each file it hashes.
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
                              env=environment, timeout=180, stdin=subprocess.DEVNULL)

    def listing(self):
        """Everything the script could have left: the test folder, the folder it runs in and its temporary folder."""
        return (sorted(p.name for p in self.base.iterdir()), sorted(p.name for p in self.outside.iterdir()),
                sorted(p.name for p in self.tmp.iterdir()))

    def forget_earlier_runs(self):
        for path in (self.log, self.pip_log):
            path.unlink(missing_ok=True)

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


# A stand-in pip whose log line says whether the interpreter that ran it was isolated (python -I).
RECORDING_PIP_MAIN = '''import os, sys
with open(os.environ['FAKE_PIP_LOG'], 'a') as log:
    log.write('isolated=%d %s\\n' % (sys.flags.isolated, ' '.join(sys.argv)))
'''
# The only Python or pip settings the script itself hands to an interpreter.
OWN_SETTINGS = {'PYTHONDONTWRITEBYTECODE=1', 'PYTHONSAFEPATH=1', 'PYTHONNOUSERSITE=1', 'PIP_CONFIG_FILE=/dev/null',
                'PIP_DISABLE_PIP_VERSION_CHECK=1'}


class IsolationTests(ScriptCase):
    """Item 3: nothing from the caller's Python environment or home reaches an interpreter the script starts, from the first
    one on. Until the work folder exists, the home is a private folder inside the staging folder."""

    def hostile(self):
        """A PYTHONPATH folder with a sitecustomize and a home with a usercustomize, each of which writes a marker if it runs."""
        marker = self.base / 'MARKER'
        folder = self.base / 'hostile'
        folder.mkdir()
        (folder / 'sitecustomize.py').write_text(f"open({str(marker)!r}, 'a').write('sitecustomize ran\\n')\n")
        home = self.base / 'caller-home'
        site = home / '.local/lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'
        site.mkdir(parents=True)
        (site / 'usercustomize.py').write_text(f"open({str(marker)!r}, 'a').write('usercustomize ran\\n')\n")
        return marker, folder, home

    def test_caller_code_on_pythonpath_or_in_the_callers_home_never_runs_in_a_full_run_or_a_refused_one(self):
        marker, folder, home = self.hostile()
        not_pip = self.base / 'not-pip.whl'
        with zipfile.ZipFile(not_pip, 'w') as archive:
            archive.writestr('README', 'a zip that is not a pip wheel')
        cases = {'a full run': (self.complete('work-full'), 0, 'RESULT: every step passed.'),
                 'a run refused after the first interpreter started': (
                     ['--pip-wheel', not_pip, '--pip-wheel-sha256', sha256(not_pip.read_bytes()), self.archive, self.wheels,
                      self.base / 'work-refused', self.archive_digest()], 64, 'is not a pip wheel')}
        for name, (arguments, status, text) in cases.items():
            with self.subTest(name):
                result = self.run_script(*arguments, env={'PYTHONPATH': str(folder), 'HOME': str(home)})
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                self.assertIn(text, result.stdout + result.stderr)
                self.assertFalse(marker.exists(), 'code of the caller ran in an interpreter the script started: '
                                 + (marker.read_text() if marker.exists() else ''))

    def test_no_python_or_pip_setting_of_the_callers_reaches_any_interpreter_and_the_home_is_private(self):
        caller_home = self.base / 'caller-home'
        caller_home.mkdir()
        env_log = self.base / 'interpreters.log'
        hostile = {'PYTHONPATH': str(self.base / 'elsewhere'), 'PYTHONHOME': str(self.base / 'no-such-python-home'),
                   'PYTHONSTARTUP': '/dev/null', 'PYTHONUSERBASE': str(self.base / 'user-base'), 'PYTHONINSPECT': '1',
                   'PYTHONWARNINGS': 'error', 'PYTHONSAFEPATH': '', 'VIRTUAL_ENV': str(self.base / 'venv-elsewhere'),
                   'PIP_INDEX_URL': 'https://example.invalid/simple', 'PIP_REQUIRE_VIRTUALENV': '1',
                   'PIP_CONFIG_FILE': str(self.base / 'pip.conf'), 'HOME': str(caller_home), 'FAKE_ENV_LOG': str(env_log)}
        result = self.run_script(*self.complete('work-env'), env=hostile)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        records = [block.splitlines() for block in env_log.read_text().split('--\n') if block.strip()]
        self.assertGreaterEqual(len(records), 4, 'the stand-in saw too few interpreter starts to prove anything')
        work_home = str((self.base / 'work-env').resolve() / 'home')
        for index, record in enumerate(records):
            with self.subTest(call=record[0]):
                self.assertTrue(record[0].startswith('args: -I '), 'an interpreter was started without -I: ' + record[0])
                self.assertLessEqual(set(record[2:]), OWN_SETTINGS, 'the caller\'s settings reached an interpreter')
                home = record[1].removeprefix('HOME=')
                self.assertNotEqual(home, str(caller_home))
                staged_home = re.fullmatch(re.escape(str(self.tmp)) + r'/intune-iac-stage\.\w+/home', home) is not None
                self.assertTrue(staged_home or home == work_home, 'the home is neither private nor the work folder: ' + home)
                if index == 0:
                    self.assertTrue(staged_home, 'before the work folder exists the home is private to the staging folder')

    def test_pip_runs_in_an_isolated_interpreter(self):
        self.make_wheel(self.pip_wheel, main=RECORDING_PIP_MAIN)
        result = self.run_script(*self.complete('work-pip'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = self.calls()[1]
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(all(line.startswith('isolated=1 ') for line in lines), lines)

    def test_every_interpreter_the_script_names_is_started_isolated_except_the_product_itself(self):
        text = DEMO.read_text()
        starts = re.findall(r'("\$PYTHON"|\.venv/bin/python)( [^\n]*)', text)
        self.assertGreaterEqual(len(starts), 7)
        for interpreter, rest in starts:
            with self.subTest(interpreter + rest[:50]):
                if 'scripts/intune-iac.py' in rest:
                    self.assertTrue(rest.startswith(' -B '), 'the guide runs the product with -B: ' + rest)
                else:
                    self.assertTrue(rest.startswith(' -I'), 'started without -I: ' + interpreter + rest)


class MemberSetTests(ScriptCase):
    """Item 4: one command compares an archive's complete member set with its SHA256SUMS before anything is unpacked, and the
    guide and the script run the same text."""

    def guide_command(self):
        section = guide_section('Check the download')
        match = re.search(r"python3 -I -c '\n(.*?)\n' Intune_IaC_Plugin_0\.9\.0\.zip", section, re.S)
        if not match:
            self.fail('the guide shows no member check before it unpacks')
        return match.group(1).strip()

    def script_command(self):
        match = re.search(r"^VERIFY_ARCHIVE='\n(.*?)\n'$", DEMO.read_text(), re.S | re.M)
        if not match:
            self.fail('the script holds no member check')
        return match.group(1).strip()

    def variant(self, change, name='variant.zip'):
        """A copy of the stand-in runtime archive after `change(members)` edited its {name: bytes} mapping."""
        with zipfile.ZipFile(self.archive) as source:
            members = {info.filename: source.read(info) for info in source.infolist()}
        change(members)
        path = self.base / name
        with zipfile.ZipFile(path, 'w') as out:
            for member, data in members.items():
                out.writestr(member, data)
        return path

    def verify(self, archive):
        return subprocess.run([sys.executable, '-I', '-c', self.guide_command(), str(archive)], cwd=self.outside,
                              capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)

    def mismatches(self):
        """Each way an archive's member set can differ from its SHA256SUMS: the change, and the text the refusal must hold."""
        def add_extra(members): members['intune-iac/extra.py'] = b'print(1)\n'
        def drop_listed(members): del members['intune-iac/scripts/verify-dependencies.py']
        def list_absent(members): members['intune-iac/SHA256SUMS'] += ('0' * 64 + '  docs/absent.md\n').encode()
        def edit(members): members['intune-iac/scripts/verify-dependencies.py'] = b'print("changed")\n'
        return {'a file that is not listed': (add_extra, 'not listed in SHA256SUMS: extra.py'),
                'a listed file that is absent': (drop_listed,
                                                 'listed in SHA256SUMS but absent from the archive: scripts/verify-dependencies.py'),
                'a line for a file that was never there': (list_absent,
                                                           'listed in SHA256SUMS but absent from the archive: docs/absent.md'),
                'a member whose content differs': (edit, 'differs from its SHA256SUMS line: scripts/verify-dependencies.py')}

    def test_the_guide_and_the_script_run_the_same_command(self):
        self.assertEqual(self.guide_command(), self.script_command())
        self.assertNotIn("'", self.script_command(), 'a quote would end the shell text the command sits in')

    def test_the_command_accepts_a_complete_archive_and_names_each_way_a_member_set_can_differ(self):
        good = self.verify(self.archive)
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertIn('SHA256SUMS verified: 3 files', good.stdout)
        for name, (change, text) in self.mismatches().items():
            with self.subTest(name):
                result = self.verify(self.variant(change))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(text, result.stderr)
                self.assertNotIn('SHA256SUMS verified', result.stdout)

    def test_the_command_refuses_other_shapes_of_archive(self):
        def second_top(members): members['other/file.txt'] = b'x'
        def unsafe(members): members['intune-iac/../evil.txt'] = b'x'
        def no_sums(members): del members['intune-iac/SHA256SUMS']
        cases = {'two top folders': (second_top, 'exactly one top folder'), 'an unsafe name': (unsafe, 'unsafe member name'),
                 'no SHA256SUMS': (no_sums, 'no SHA256SUMS')}
        for name, (change, text) in cases.items():
            with self.subTest(name):
                result = self.verify(self.variant(change))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(text, result.stderr)
        link = self.base / 'link.zip'
        with zipfile.ZipFile(self.archive) as source, zipfile.ZipFile(link, 'w') as out:
            for info in source.infolist():
                out.writestr(info, source.read(info))
            entry = zipfile.ZipInfo('intune-iac/linked')
            entry.external_attr = 0o120777 << 16
            out.writestr(entry, 'README.md')
        twice = self.base / 'twice.zip'
        with zipfile.ZipFile(self.archive) as source, zipfile.ZipFile(twice, 'w') as out, warnings.catch_warnings():
            warnings.simplefilter('ignore')
            for info in source.infolist():
                out.writestr(info, source.read(info))
            out.writestr('intune-iac/scripts/intune-iac.py', 'print("second copy")\n')
        for name, path, text in (('a link member', link, 'symbolic link member'), ('a repeated name', twice, 'appears twice')):
            with self.subTest(name):
                result = self.verify(path)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(text, result.stderr)

    def test_the_command_only_reads_the_archive(self):
        self.verify(self.variant(self.mismatches()['a file that is not listed'][0]))
        self.verify(self.archive)
        self.assertEqual(sorted(p.name for p in self.outside.iterdir()), [], 'the command ran in this folder and wrote nothing')

    def test_the_script_refuses_each_mismatch_before_it_creates_or_unpacks_anything(self):
        for number, (name, (change, text)) in enumerate(self.mismatches().items()):
            with self.subTest(name):
                variant = self.variant(change, name=f'variant-{number}.zip')
                work = f'work-{number}'
                self.forget_earlier_runs()
                before = self.listing()
                result = self.run_script('--pip-wheel', self.pip_wheel, '--pip-wheel-sha256', self.wheel_digest(), variant,
                                         self.wheels, self.base / work, sha256(variant.read_bytes()))
                self.assertRefusedBeforeAnything(result, before, status=3, work=work)
                self.assertIn(text, result.stderr)

    def test_the_guide_runs_the_member_check_before_it_unpacks_and_describes_each_command_as_it_is(self):
        section = guide_section('Check the download')
        self.assertIn("python3 -I -c '", section)
        self.assertIn('python3 -I -m zipfile -e', section)
        self.assertLess(section.index("python3 -I -c '"), section.index('python3 -I -m zipfile -e'))
        text = squashed(section)
        for phrase in ('does not unpack the archive', 'lacks a file that it lists', 'checks every file the list names and nothing else',
                       'does not look for a file the list does not name',
                       '`doctor` also names any file under the unpacked folder that the list does not name'):
            self.assertIn(phrase, text)
        self.assertNotIn('check every file inside it', text)


class UnlistedFileTests(unittest.TestCase):
    """Item 4: `doctor` names files under the unpacked folder that SHA256SUMS does not list, and does not say `identified`
    while there are any. It does not count the folders the guide creates at the top of the unpacked folder, or bytecode caches,
    and it says so."""

    def setUp(self):
        self.fixture = base.FixtureBuild(self)
        self.fixture.build()
        self.installed = self.fixture.extract('runtime')

    def report(self):
        from intune_iac import build_identity
        return build_identity.report(self.installed)

    def put(self, name, text='x\n'):
        path = self.installed / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_an_intact_copy_is_identified_and_the_report_names_what_it_does_not_count(self):
        value = self.report()
        self.assertEqual(value['status'], 'identified')
        self.assertEqual(value.get('unlisted_files'), [])
        self.assertEqual(value.get('unlisted_count'), 0)
        counted_not = ' '.join(value.get('unlisted_not_counted', []))
        for name in ('.venv', 'demo', '__pycache__'):
            self.assertIn(name, counted_not)

    def test_a_file_the_list_does_not_name_is_reported_and_the_copy_is_not_identified(self):
        self.put('extra.py')
        self.put('docs/extra.md')
        value = self.report()
        self.assertNotEqual(value['status'], 'identified')
        self.assertEqual(value.get('unlisted_files'), ['docs/extra.md', 'extra.py'])
        self.assertEqual(value.get('unlisted_count'), 2)
        self.assertIn('not list', value['note'])

    def test_what_the_guide_creates_and_bytecode_caches_are_not_counted(self):
        self.put('.venv/lib/site.py')
        self.put('demo/journey.json')
        self.put('demo/store/db/entry.txt')
        self.put('docs/__pycache__/x.cpython-312.pyc')
        value = self.report()
        self.assertEqual(value['status'], 'identified')
        self.assertEqual(value.get('unlisted_files'), [])

    def test_the_same_names_deeper_in_the_tree_are_counted(self):
        self.put('docs/demo/notes.txt')
        self.put('docs/.venv/lib.py')
        self.put('.venv-copy/x')
        value = self.report()
        self.assertNotEqual(value['status'], 'identified')
        self.assertEqual(value.get('unlisted_files'), ['.venv-copy/x', 'docs/.venv/lib.py', 'docs/demo/notes.txt'])

    def test_a_link_is_an_unlisted_entry_and_is_not_followed(self):
        outside = self.fixture.parent / 'outside-folder'
        outside.mkdir()
        (outside / 'secret.txt').write_text('x')
        os.symlink(outside, self.installed / 'linked-folder')
        os.symlink(outside / 'secret.txt', self.installed / 'linked-file')
        value = self.report()
        self.assertNotEqual(value['status'], 'identified')
        self.assertEqual(value.get('unlisted_files'), ['linked-file', 'linked-folder'])

    def test_a_listed_file_that_changed_is_still_reported_as_modified(self):
        (self.installed / 'README.md').write_text('edited\n')
        value = self.report()
        self.assertEqual((value['status'], value['modified_files']), ('modified', ['README.md']))
        self.assertEqual(value.get('unlisted_files'), [])

    def test_doctor_carries_the_same_report(self):
        from intune_iac import build_identity, cli
        self.put('extra.py')
        with patch.object(build_identity, 'PACKAGE_ROOT', self.installed):
            value = cli.doctor()
        self.assertNotEqual(value['build']['status'], 'identified')
        self.assertEqual(value['build'].get('unlisted_files'), ['extra.py'])


builder = base.builder
CLEAN_ENVIRONMENT = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}


class GitFixture:
    """A real repository holding a tiny reviewed project: README.md, NOTES.md and an inventory naming both and itself."""

    def __init__(self, case, nested=False):
        temp = tempfile.TemporaryDirectory()
        case.addCleanup(temp.cleanup)
        self.parent = Path(temp.name)
        self.root = self.parent / 'project'
        self.root.mkdir()
        self.output = self.parent / 'out'
        for name, text in (('README.md', 'Reviewed project documentation\n'), ('NOTES.md', 'Source only notes\n'),
                           ('release-source-files.txt', 'README.md\nNOTES.md\nrelease-source-files.txt\n')):
            (self.root / name).write_text(text)
        if not nested:
            self.git('init', '-q', '-b', 'main')
            self.commit('first')

    def git(self, *args, cwd=None, root=None):
        result = subprocess.run(['git', '-C', str(root or cwd or self.root), '-c', 'user.name=Release Tests',
                                 '-c', 'user.email=release-tests', '-c', 'commit.gpgsign=false', *args],
                                capture_output=True, text=True, env=dict(CLEAN_ENVIRONMENT, GIT_CONFIG_NOSYSTEM='1'), timeout=60)
        if result.returncode != 0:
            raise AssertionError('git ' + ' '.join(args) + ': ' + result.stderr)
        return result.stdout.strip()

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', message)

    def build(self, *, runtime=('README.md',)):
        with patch.object(builder, 'ROOT', self.root), patch.object(builder, 'runtime_files', return_value=list(runtime)), \
                patch.object(builder, 'build_time', return_value=base.BUILT_AT), \
                patch.object(sys, 'argv', ['build-release.py', '--output-dir', str(self.output)]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            builder.main()
        return json.loads(out.getvalue())

    def member(self, name, kind='source'):
        archive = f'Intune_IaC_Plugin_{builder.__version__}' + ('' if kind == 'runtime' else '_Source') + '.zip'
        with zipfile.ZipFile(self.output / archive) as opened:
            return opened.read(('intune-iac/' if kind == 'runtime' else 'intune-iac-source/') + name)

    def identity(self, kind='runtime'):
        return json.loads(self.member('BUILD-IDENTITY.json', kind))


class GitBindingTests(unittest.TestCase):
    """Item 5: the identity describes the files the archive holds. A path in the inventory that is not in the commit is refused,
    the checkout is read before and after the snapshot and must not have moved, and a captured file that differs from the
    commit makes the build dirty whether or not git's own status says so."""

    def setUp(self):
        if not shutil.which('git'):
            self.skipTest('git is not available here')
        self.repo = GitFixture(self)

    def test_a_clean_checkout_names_its_commit_and_tree_and_is_not_dirty(self):
        self.repo.build()
        record = self.repo.identity()
        self.assertEqual(record['commit'], self.repo.git('rev-parse', 'HEAD'))
        self.assertEqual(record['tree'], self.repo.git('rev-parse', 'HEAD^{tree}'))
        self.assertIs(record['dirty'], False)

    def test_an_inventoried_path_that_is_not_in_the_commit_is_refused(self):
        def untracked(repo):
            (repo.root / 'EXTRA.md').write_text('shipped but never committed\n')

        def ignored(repo):
            (repo.root / 'EXTRA.md').write_text('ignored\n')
            (repo.root / '.git/info/exclude').write_text('EXTRA.md\n')

        def added_but_not_committed(repo):
            (repo.root / 'EXTRA.md').write_text('staged, not committed\n')
            repo.git('add', 'EXTRA.md')

        for name, prepare in {'untracked': untracked, 'ignored': ignored, 'added but not committed': added_but_not_committed}.items():
            with self.subTest(name):
                repo = GitFixture(self)
                prepare(repo)
                (repo.root / 'release-source-files.txt').write_text('README.md\nNOTES.md\nEXTRA.md\nrelease-source-files.txt\n')
                try:
                    repo.build()
                except ValueError as refusal:
                    message = str(refusal)
                except Exception as other:      # a crash is not a refusal that names the path
                    self.fail(f'expected a refusal naming EXTRA.md, got {other!r}')
                else:
                    self.fail('the build accepted an inventoried path that is not in the commit')
                self.assertIn('EXTRA.md', message)
                self.assertIn('not committed', message)
                self.assertFalse(repo.output.exists() and any(repo.output.iterdir()), 'no archive was written')

    def test_a_checkout_that_moves_while_the_snapshot_is_read_aborts_the_build(self):
        original = builder.source_files
        moves = {'a new commit': lambda repo: repo.git('commit', '-q', '--allow-empty', '-m', 'moved'),
                 'an edit of a tracked file': lambda repo: (repo.root / 'NOTES.md').write_text('edited mid-build\n')}
        for name, move in moves.items():
            with self.subTest(name):
                repo = GitFixture(self)

                def hooked(inventory_bytes=None, move=move, repo=repo):
                    names = original(inventory_bytes)
                    move(repo)
                    return names

                with patch.object(builder, 'source_files', hooked), self.assertRaises(ValueError) as caught:
                    repo.build()
                self.assertIn('changed while the snapshot was read', str(caught.exception))

    def test_an_allowance_file_that_is_not_in_the_commit_is_refused_like_a_source(self):
        repo = GitFixture(self)
        (repo.root / 'docs').mkdir()
        (repo.root / 'docs/found.txt').write_bytes(SHAPES['jwt']())
        (repo.root / 'release-sensitive-allow.txt').write_text(
            f'docs/found.txt | {sha256((repo.root / "docs/found.txt").read_bytes())} | jwt | a made-up value used by a test\n')
        (repo.root / '.git/info/exclude').write_text('release-sensitive-allow.txt\n')       # so the allowance file is never committed
        (repo.root / 'release-source-files.txt').write_text(
            'README.md\nNOTES.md\ndocs/found.txt\nrelease-sensitive-allow.txt\nrelease-source-files.txt\n')
        repo.commit('add a file with a JWT-shaped value')
        with patch.object(builder, 'host_identity', create=True, return_value=(FAKE_HOME, 'fixture-user')):
            try:
                repo.build()
            except ValueError as refusal:
                self.assertIn('release-sensitive-allow.txt', str(refusal))
                self.assertIn('not committed', str(refusal))
            else:
                self.fail('an allowance file that is untracked was accepted')


# Secret-shaped test data is assembled here, never written out whole, so that this file does not itself hold what the control
# looks for when a release is built from the checkout this file belongs to.
FAKE_HOME = '/home/' + 'fixture-user'
SHAPES = {
    'private_key': lambda: ('-----BEGIN ' + 'RSA PRIVATE KEY-----\n' + 'MIIB' * 5 + '\n').encode(),
    'jwt': lambda: ('token = eyJ' + 'a' * 10 + '.' + 'b' * 12 + '.' + 'c' * 10 + '\n').encode(),
    'vendor_token': lambda: ('key = gh' + 'p_' + 'A1b2C3d4E5' * 4 + '\n').encode(),
    'entra_secret': lambda: ('secret = abc' + '1' + 'Q' + '~' + 'x' * 24 + '\n').encode(),
    'host_home_path': lambda: ('see ' + FAKE_HOME + '/projects/notes.txt\n').encode(),
}
COUNTED_ONLY = {
    'bearer': lambda: ('Authorization: Bear' + 'er ' + 'abcdefghij0123456789' + '\n').encode(),
    'url_password': lambda: ('https://' + 'someone:' + 'pa55word' + chr(64) + 'example.test/path\n').encode(),
}


class SensitiveFixture:
    """A FixtureBuild with extra inventoried files, an optional allowance file and a fixed idea of the building host."""

    def __init__(self, case, files=None, allowance=None):
        self.fixture = base.FixtureBuild(case)
        root = self.fixture.root
        names = ['README.md', 'NOTES.md']
        for name, data in (files or {}).items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes(data)
            names.append(name)
        if allowance is not None:
            (root / 'release-sensitive-allow.txt').write_text(allowance)
            names.append('release-sensitive-allow.txt')       # the reviewed file is one of the captured, archived files
        (root / 'release-source-files.txt').write_text('\n'.join(names + ['release-source-files.txt']) + '\n')
        self.root = root

    def build(self):
        with patch.object(builder, 'host_identity', create=True, return_value=(FAKE_HOME, 'fixture-user')):
            receipt = self.fixture.build()
        if 'sensitive_content' not in receipt:
            raise AssertionError('the receipt has no sensitive_content block')
        return receipt

    def digest(self, name):
        return sha256((self.root / name).read_bytes())


class SensitiveNameTests(unittest.TestCase):
    """Item 6, names: the existing guard stays as it is, and these names are refused beside it."""

    DENIED = ('.env', '.env.local', 'config/.env.production', 'terraform.tfstate', 'terraform.tfstate.backup', 'x/state.tfstate.1',
              'ca.pem', 'deploy/server.key', 'store.pfx', 'store.p12', 'id_rsa', 'home/id_rsa.pub', 'id_ed25519', 'id_ed25519.pub',
              'credentials.json', 'cfg/credentials.json', '.netrc', '.npmrc', 'sub/.pypirc', 'CA.PEM', 'Credentials.JSON')
    ALLOWED = ('env.md', 'docs/keys.md', 'credentials-guide.md', 'README.pem.md', 'docs/envelope.txt', 'identity.py', 'docs/netrc.md')

    def source_files(self, name):
        fixture = base.FixtureBuild(self)
        (fixture.root / name).parent.mkdir(parents=True, exist_ok=True)
        (fixture.root / name).write_text('content\n')
        inventory = ('README.md\n' + name + '\nrelease-source-files.txt\n').encode()
        with patch.object(builder, 'ROOT', fixture.root):
            return builder.source_files(inventory)

    def test_each_sensitive_name_is_refused(self):
        for name in self.DENIED:
            with self.subTest(name):
                with self.assertRaises(ValueError) as caught:
                    self.source_files(name)
                self.assertIn('Sensitive artifact name', str(caught.exception))
                self.assertIn(name, str(caught.exception))

    def test_ordinary_names_that_only_look_similar_are_accepted(self):
        for name in self.ALLOWED:
            with self.subTest(name):
                try:
                    names = self.source_files(name)
                except ValueError as refusal:
                    self.fail(f'{name} was refused: {refusal}')
                self.assertIn(name, names)

    def test_the_existing_tfstate_guard_is_still_there_word_for_word(self):
        guard = ("if Path(name).name == '.env' or '.tfstate' in Path(name).name or Path(name).suffix in {'.key', '.pem'}:")
        self.assertIn(guard, (ROOT / 'scripts/build-release.py').read_text())


class SensitiveContentTests(unittest.TestCase):
    """Item 6, content: the bytes about to be archived are scanned for fixed secret shapes, private-key markers and the building
    host's own home path. A finding that no reviewed allowance covers refuses the build; the receipt records what was found,
    masked, with counts."""

    def test_each_kind_refuses_the_build_and_the_message_never_holds_the_value(self):
        for kind, make in SHAPES.items():
            with self.subTest(kind):
                data = make()
                sensitive = SensitiveFixture(self, {'docs/found.txt': data})
                with self.assertRaises(ValueError) as caught:
                    sensitive.build()
                message = str(caught.exception)
                self.assertIn('docs/found.txt', message)
                self.assertIn(kind, message)
                self.assertIn('release-sensitive-allow.txt', message)
                self.assertNotIn(data.decode().strip().split()[-1], message)
                self.assertFalse(sensitive.fixture.output.exists() and any(sensitive.fixture.output.iterdir()), 'no archive was written')

    def allowance_for(self, sensitive, name, kind, reason='a made-up value used by a test'):
        return f'{name} | {sensitive.digest(name)} | {kind} | {reason}\n'

    def test_a_reviewed_allowance_lets_the_build_through_and_the_receipt_records_the_finding_masked(self):
        for kind, make in SHAPES.items():
            with self.subTest(kind):
                data = make()
                probe = SensitiveFixture(self, {'docs/found.txt': data})
                allowance = '# reviewed by the release owner\n\n' + self.allowance_for(probe, 'docs/found.txt', kind)
                sensitive = SensitiveFixture(self, {'docs/found.txt': data}, allowance=allowance)
                receipt = sensitive.build()
                block = receipt['sensitive_content']
                found = [item for item in block['findings'] if item['kind'] == kind]
                self.assertEqual(len(found), 1, block['findings'])
                self.assertEqual((found[0]['path'], found[0]['sha256'], found[0]['count'], found[0]['allowed']),
                                 ('docs/found.txt', sensitive.digest('docs/found.txt'), 1, True))
                self.assertEqual(found[0]['line'], 1)
                value = data.decode().strip().split()[-1]
                self.assertNotIn(value, json.dumps(receipt), 'the receipt holds the value itself')
                if kind == 'host_home_path':
                    self.assertIn(found[0]['masked'], ('<home>', '<user>'))
                else:
                    self.assertIn('*', found[0]['masked'])
                self.assertEqual(block['allowance_file_sha256'], sha256((sensitive.root / 'release-sensitive-allow.txt').read_bytes()))

    def test_an_allowance_that_does_not_match_the_bytes_or_the_kind_covers_nothing(self):
        data = SHAPES['jwt']()
        probe = SensitiveFixture(self, {'docs/found.txt': data})
        good = self.allowance_for(probe, 'docs/found.txt', 'jwt')
        cases = {'the file was edited after review': good.replace(probe.digest('docs/found.txt'), '0' * 64),
                 'a different kind': good.replace('| jwt |', '| vendor_token |'),
                 'a different path': good.replace('docs/found.txt', 'docs/other.txt')}
        for name, allowance in cases.items():
            with self.subTest(name):
                sensitive = SensitiveFixture(self, {'docs/found.txt': data}, allowance=allowance)
                with self.assertRaises(ValueError) as caught:
                    sensitive.build()
                self.assertIn('docs/found.txt', str(caught.exception))

    def test_an_unused_allowance_is_counted_and_does_not_refuse(self):
        stale = f'docs/gone.txt | {"1" * 64} | jwt | the file this reviewed was removed\n'
        receipt = SensitiveFixture(self, allowance=stale).build()
        self.assertEqual((receipt['sensitive_content']['allowance_entries'], receipt['sensitive_content']['allowance_unused']), (1, 1))

    def test_a_malformed_allowance_line_refuses_the_build(self):
        for line in ('docs/found.txt | not-a-digest | jwt | reason\n', f'docs/found.txt | {"1" * 64} | no_such_kind | reason\n',
                     f'docs/found.txt | {"1" * 64} | jwt |\n', 'only three | fields | here\n'):
            with self.subTest(line):
                with self.assertRaises(ValueError) as caught:
                    SensitiveFixture(self, allowance=line).build()
                self.assertIn('release-sensitive-allow.txt', str(caught.exception))

    def test_the_two_weakest_shapes_are_counted_and_never_refuse(self):
        files = {f'docs/{kind}.txt': make() for kind, make in COUNTED_ONLY.items()}
        try:
            receipt = SensitiveFixture(self, files).build()
        except ValueError as refusal:
            self.fail(f'a shape that is only counted refused the build: {refusal}')
        block = receipt['sensitive_content']
        self.assertEqual(block['findings'], [])
        for kind in COUNTED_ONLY:
            self.assertEqual(block['counted_only'][kind], {'files': 1, 'matches': 1}, kind)

    def test_a_clean_tree_reports_what_it_scanned_and_what_the_control_does_not_do(self):
        receipt = SensitiveFixture(self).build()
        block = receipt['sensitive_content']
        self.assertEqual((block['findings'], block['scanned_files']), ([], 3))
        self.assertGreater(block['scanned_bytes'], 0)
        self.assertIn('does not classify arbitrary content', block['limits'])
        self.assertNotIn('not automatically classified', receipt['source_selection'])
        self.assertIn('sensitive_content', receipt['source_selection'])

    def test_the_guide_says_what_the_control_does_and_does_not_do(self):
        text = squashed(guide_section('Support limits'))
        for phrase in ('release-sensitive-allow.txt', 'does not classify arbitrary content', 'home path'):
            self.assertIn(phrase, text)


if __name__ == '__main__':
    unittest.main()
