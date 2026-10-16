"""PKG-TEXT-GUARD: no text-mode command writes a terminal control character, whichever surface forgot to escape.

The renderers escape record text through `safe_text`. This module is the check on the last line of defence in
`intune_iac.cli`: one guard where text-mode commands write their output. A hostile value is built at run time with
chr() and put where every text command can read it (a policy name, a recorded string, a directory name, a file name);
each command then runs in a subprocess over it and over a clean twin, and the raw stdout and stderr bytes are checked.
"""
import contextlib
import io
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

from intune_iac import cli
from intune_iac.synthetic import generate_estate
from plugin_tests import sim_support as sim
from plugin_tests.orchestration_fixtures import event, lifecycle, write_export
from plugin_tests.signin_fakes import TENANT_A, azure_account, azure_list, github_hosts

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'

# ESC with a CSI tail, CR and LF inside one value, BEL, DEL, C1 CSI, the line and paragraph separators and a bidirectional override.
HOSTILE = ''.join(chr(n) for n in (0x1b,)) + '[31m' + 'a' + chr(13) + 'b' + chr(10) + 'c' + chr(7) + chr(0x7f) + chr(0x9b) + \
    chr(0x2028) + chr(0x2029) + chr(0x202e) + chr(0x200e) + chr(0x200f) + chr(0x061c) + chr(0xfeff) + chr(0x200b) + \
    chr(0x2060) + chr(0x2064) + chr(0x206b) + chr(0xad) + chr(0xe0001) + 'z'
# A file or directory name cannot hold a slash; this one holds every other character of the hostile value.
CLEAN = 'plain-value'
GUARDED_CATEGORIES = frozenset(('Cc', 'Cf', 'Zl', 'Zp'))


def _forbidden_pattern():
    """A character class of every code point whose category is guarded, except the row-separating LF, built from the table."""
    ranges, start = [], None
    for number in range(0x110001):
        hit = (number < 0x110000 and number != 10 and not 0xd800 <= number <= 0xdfff
               and unicodedata.category(chr(number)) in GUARDED_CATEGORIES)
        if hit and start is None:
            start = number
        elif not hit and start is not None:
            ranges.append('\\U%08x-\\U%08x' % (start, number - 1))
            start = None
    return re.compile('[' + ''.join(ranges) + ']')


FORBIDDEN = _forbidden_pattern()
# Characters next to the guarded categories that must pass unchanged: spaces, ordinary letters and punctuation, unassigned points.
NEIGHBOURS = (0x20, 0x7e, 0xa0, 0x061b, 0x061d, 0x200a, 0x2010, 0x202f, 0x205f, 0x2065, 0xfefe, 0xff00, 0x41, 0x39, 0x2e, 0xe9, 0x4e2d)
OLD_NAME = 'Privacy pilot 7'
# Line-ending rule: the CLI writes LF only, on both streams, on every platform. A CR is a finding wherever it is.


def filesystem_accepts(base, text):
    """Whether a file whose name holds `text` can be created under `base` (decided by trying, not by platform)."""
    probe = Path(base) / ('probe-' + text)
    try:
        probe.write_text('x')
        probe.unlink()
        return True
    except (OSError, ValueError):
        return False


def fixture_name_text(base, text):
    """The text for file and directory names: the hostile value where the filesystem takes it, otherwise its printable part.
    Recorded values inside files always keep the whole hostile value."""
    return text if filesystem_accepts(base, text) else ''.join(ch for ch in text if ch.isprintable())


def forbidden_in(data):
    """The forbidden characters in raw output bytes, as code points. The bytes are decoded strictly as UTF-8: a byte that is not
    valid UTF-8 (a lone 0x9b, which a terminal reads as a C1 CSI) is reported as INVALID_UTF8, never decoded into something the
    pattern cannot match."""
    try:
        text, found = data.decode('utf-8'), []
    except UnicodeDecodeError:
        text, found = data.decode('utf-8', 'replace'), ['INVALID_UTF8']
    # No CR is allowed, alone or before an LF: the CLI writes LF only, so a CRLF cannot be told from an injected one.
    return sorted(found + ['U+%04X' % ord(ch) for ch in set(FORBIDDEN.findall(text))])


def check_streams(case, label, result):
    """Stdout and stderr of one command hold no forbidden character and no invalid UTF-8; stdout is not empty."""
    case.assertEqual(forbidden_in(result.stdout), [], label)
    case.assertEqual(forbidden_in(result.stderr), [], label)
    case.assertTrue(result.stdout.strip(), label + ' printed nothing')


def replace_everywhere(value, old, new):
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [replace_everywhere(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: replace_everywhere(item, old, new) for key, item in value.items()}
    return value


FAKE_TOOL = '''"""A stand-in for az or gh: prints the canned answer for the subcommand it was called with. Not a real client."""
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
tool, args = sys.argv[1], sys.argv[2:] + ['', '']
with open(os.path.join(here, 'calls.log'), 'a', encoding='utf-8', newline='\\n') as log:
    log.write(' '.join(sys.argv[2:]) + '\\n')
base = os.path.join(here, '%s.%s_%s' % (tool, args[0], args[1]))
if not os.path.exists(base + '.out'):
    sys.exit(127)
for suffix, stream in (('.out', sys.stdout.buffer), ('.err', sys.stderr.buffer)):
    if os.path.exists(base + suffix):
        with open(base + suffix, 'rb') as handle:
            stream.write(handle.read())
        stream.flush()
code = 0
if os.path.exists(base + '.code'):
    with open(base + '.code', encoding='utf-8') as handle:
        code = int(handle.read().strip() or 0)
sys.exit(code)
'''


def launcher_text(tool, directory, executable, windows):
    """The launcher for one fake tool: a .cmd file on Windows (CRLF, the batch convention), an executable shell wrapper elsewhere."""
    if windows:
        return '@"%s" "%s" %s %%*\r\n' % (executable, str(directory).replace('/', '\\') + '\\fake_tool.py', tool)
    return '#!/bin/sh\nexec %s %s %s "$@"\n' % (shlex.quote(str(executable)), shlex.quote(str(Path(directory) / 'fake_tool.py')), tool)


class PortableClis:
    """Fake az and gh that run on every platform: one Python script run by sys.executable, a launcher beside it per tool, and
    canned answers in files named <tool>.<first>_<second>.(out|err|code). Calls are logged to calls.log."""

    def __init__(self, base=None, windows=None):
        self.windows = os.name == 'nt' if windows is None else windows
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.directory = Path(self.temp.name).resolve()
        (self.directory / 'fake_tool.py').write_text(FAKE_TOOL, encoding='utf-8', newline='\n')
        for tool in ('az', 'gh'):
            text = launcher_text(tool, self.directory, sys.executable, self.windows)
            if self.windows:
                (self.directory / (tool + '.cmd')).write_bytes(text.encode('utf-8'))
            else:
                path = self.directory / tool
                path.write_text(text, encoding='utf-8', newline='\n')
                path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def cleanup(self):
        self.temp.cleanup()

    def path_entry(self):
        return str(self.directory)

    def answer(self, tool, first, second, out='', err='', code=0):
        base = self.directory / ('%s.%s_%s' % (tool, first, second))
        for suffix, value in (('out', out), ('err', err), ('code', str(code))):
            Path(str(base) + '.' + suffix).write_bytes(value.encode('utf-8'))

    def calls(self):
        log = self.directory / 'calls.log'
        return log.read_text(encoding='utf-8').splitlines() if log.exists() else []


class Fixture:
    """One working set: a start or catalog directory, an engineering export, simulator documents, fake sign-in clients
    and a workbench store, every recorded string built from `text`."""

    def __init__(self, text, base):
        self.text, self.base = text, Path(base)
        self.fakes = PortableClis(base=str(self.base))
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', COLUMNS='100',
                        PATH=self.fakes.path_entry() + os.pathsep + os.environ.get('PATH', ''))
        self._directory()
        self._engineering()
        self._simulate()
        self._signin()
        self._workbench()

    def run(self, *argv, stdin=''):
        return subprocess.run([sys.executable, '-B', str(CLI), *map(str, argv)], input=stdin.encode(), capture_output=True,
                              cwd=str(self.base), timeout=60, env=self.env)

    def _directory(self):
        name = fixture_name_text(self.base, self.text)
        self.work = self.base / ('dir-' + name)
        self.work.mkdir()
        (self.work / ('file-' + name + '.json')).write_text(json.dumps({'name': self.text}))
        (self.work / ('note-' + name + '.txt')).write_bytes(self.text.encode('utf-8'))  # bytes: no newline translation
        (self.work / ('sub-' + name)).mkdir()

    def _engineering(self):
        self.records = self.base / 'records'
        events = (lifecycle('T-1', terminal='dispatch.failed', reason='bad ' + self.text)
                  + [event(10, 'dispatch.queued', 'T-' + self.text, kind='advisor')]
                  + lifecycle('T-2', start=20, terminal='dispatch.completed'))
        write_export(self.records, events)

    def _simulate(self):
        label = 'Policy ' + self.text
        group = sim.group('g1', 'device', label=label)
        base_policy = sim.policy('p1', [sim.include('g1')], label=label)
        edited = sim.policy('p1', [sim.include('g1')], label=label + 'x', description='rev ' + self.text)
        doc = sim.snapshot_doc(devices=[sim.device('d1')], groups=[group], memberships=[sim.member('g1', 'd1')],
                               policies=[base_policy])
        self.snapshot, self.revision = self.base / 'snapshot.json', self.base / 'revision.json'
        self.snapshot.write_text(json.dumps(doc))
        self.revision.write_text(json.dumps(sim.revision_doc(policies=[edited])))

    def _signin(self):
        self.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(user='alex' + self.text + '@example.test')))
        self.fakes.answer('gh', 'auth', 'status', code=1,
                          out=github_hosts(('github.com', 'octo' + self.text, 'error', True)))

    def _workbench(self):
        estate = generate_estate(seed=501, policy_count=2)
        capture = replace_everywhere(estate['capture'], OLD_NAME, OLD_NAME + ' ' + self.text)
        tenant = estate['truth']['tenant_id']
        self.policy_id = estate['truth']['policies'][0]['id']
        self.store, service = self.base / 'memory', self.base / 'service'
        capture_file = self.base / 'capture.json'
        capture_file.write_text(json.dumps(capture))
        for argv in (('init', '--root', self.store, '--tenant', tenant),
                     ('lab-create', '--service-root', service, '--input', capture_file, '--object', self.policy_id),
                     ('collect', '--root', self.store, '--service-root', service)):
            done = self.run('workbench', *argv)
            if done.returncode != 0:
                raise AssertionError('fixture step %s failed: %r' % (argv[0], done.stderr[-300:]))

    def sweep(self):
        """{label: argv} of every text-mode command, over this fixture."""
        commands = {
            'start': ['start', self.work],
            'start --goal': ['start', self.work, '--goal', 'inspect'],
            'catalog': ['catalog', self.work],
            'engineering': ['engineering', '--records', self.records],
            'simulate --format text': ['simulate', '--snapshot', self.snapshot, '--revision', self.revision, '--format', 'text'],
            'signin status': ['signin', 'status', '--tenant', TENANT_A, '--provider', 'all'],
            'workbench workflow': ['workbench', 'workflow', '--root', self.store, '--policy', self.policy_id],
        }
        if os.name != 'posix':
            del commands['signin status']  # the product refuses sign-in reuse off a Unix host (identity_fd_platform_unsupported)
        return commands

    def json_forms(self):
        return {key: argv + ['--json'] for key, argv in self.sweep().items()
                if key in {'start', 'catalog', 'engineering', 'signin status', 'workbench workflow'}}


def text_commands(parser):
    """The text-mode commands of a parser, read from the parser: every leaf command with a `--json` switch (its default is the
    readable form) or a `--format` choice named text."""
    found = set()

    def walk(node, path):
        subs = [a for a in node._actions if a.__class__.__name__ == '_SubParsersAction']
        if not subs:
            options = {opt: act for act in node._actions for opt in act.option_strings}
            if '--json' in options or 'text' in (getattr(options.get('--format'), 'choices', None) or ()):
                found.add(' '.join(path))
            return
        for action in subs:
            for name, child in action.choices.items():
                if name in action._name_parser_map and action._name_parser_map[name] is child:
                    walk(child, path + [name])

    walk(parser, [])
    return found


TEXT_COMMANDS = {'start', 'catalog', 'engineering', 'simulate', 'signin status', 'signin collect', 'workbench workflow'}


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)

    def test_a_command_runs_in_the_fixtures_own_temporary_directory(self):
        fixture = Fixture.__new__(Fixture)
        fixture.base, fixture.env = self.base, {}
        with mock.patch.object(subprocess, 'run') as run:
            fixture.run('doctor')
        self.assertEqual(run.call_args.kwargs['cwd'], str(self.base))

    def test_hostile_names_are_used_only_where_the_filesystem_accepts_them(self):
        accepted = filesystem_accepts(self.base, HOSTILE)
        name = fixture_name_text(self.base, HOSTILE)
        self.assertEqual(name == HOSTILE, accepted)
        self.assertEqual(fixture_name_text(self.base, CLEAN), CLEAN)
        # whatever the filesystem refuses, the name part that remains must be creatable
        self.assertTrue(filesystem_accepts(self.base, name))
        with mock.patch.object(sys.modules[__name__], 'filesystem_accepts', lambda base, text: text == CLEAN):
            self.assertTrue(fixture_name_text(self.base, HOSTILE).isprintable())

    def test_recorded_values_keep_the_hostile_controls_whatever_the_names_do(self):
        fixture = Fixture.__new__(Fixture)
        fixture.text, fixture.base = HOSTILE, self.base
        with mock.patch.object(sys.modules[__name__], 'filesystem_accepts', lambda base, text: False):
            fixture._directory()
        recorded = json.loads(next(fixture.work.glob('file-*.json')).read_text())
        self.assertEqual(recorded, {'name': HOSTILE})
        self.assertEqual(next(fixture.work.glob('note-*.txt')).read_bytes(), HOSTILE.encode('utf-8'))
        self.assertTrue(fixture.work.name.isprintable())

    def test_rows_are_joined_by_one_lf_and_never_by_the_platform_newline(self):
        self.assertEqual(cli.text_guard_rows(['a', 'b' + chr(13) + chr(10) + 'c', 'd']), 'a\nb\\r\\nc\nd')
        self.assertNotIn('\r', cli.text_guard_rows(['a', 'b' + chr(13), 'c']))

    def test_a_cr_alone_or_before_lf_is_a_finding_on_every_platform(self):
        for data in (b'one\rtwo', b'one\r\ntwo\r\n', b'Policy\r\nINJECTED', b'one\r\r\ntwo'):
            with self.subTest(data=data):
                self.assertEqual(forbidden_in(data), ['U+000D'])
        self.assertEqual(forbidden_in(b'one\ntwo\n'), [])

    def test_the_streams_are_written_with_lf_only_even_where_the_platform_translates_newlines(self):
        """A Windows text stream turns each LF into CRLF; the CLI reconfigures both streams so it does not."""
        from intune_iac.io import AppError
        for label, argv, patched, result in (
                ('stdout', ['catalog', '.'], [('intune_iac.catalog.catalog_lines', ['one', 'two', 'three'])], {}),
                ('stderr', ['catalog', '.'], [], AppError('invalid_request', 'Request failed.'))):
            raw_out, raw_err = io.BytesIO(), io.BytesIO()
            out = io.TextIOWrapper(raw_out, encoding='utf-8', newline='\r\n', write_through=True)
            err = io.TextIOWrapper(raw_err, encoding='utf-8', newline='\r\n', write_through=True)
            with self.subTest(stream=label), contextlib.ExitStack() as stack:
                if isinstance(result, Exception):
                    stack.enter_context(mock.patch.object(cli, 'execute', side_effect=result))
                else:
                    stack.enter_context(mock.patch.object(cli, 'execute', return_value=result))
                for target, value in patched:
                    stack.enter_context(mock.patch(target, return_value=value))
                stack.enter_context(mock.patch.object(sys, 'stdout', out))
                stack.enter_context(mock.patch.object(sys, 'stderr', err))
                cli.main(argv)
            out.flush(), err.flush()
            written = raw_out.getvalue() + raw_err.getvalue()
            self.assertTrue(written.strip(), label)
            self.assertNotIn(b'\r', written, label)
            self.assertEqual(forbidden_in(written), [], label)

    def test_a_real_run_writes_no_cr_byte_to_either_stream(self):
        fixture = Fixture.__new__(Fixture)
        fixture.base, fixture.env = self.base, dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        for argv in (['catalog', self.base], ['plan', 'review', '--input', self.base / 'absent.json']):
            with self.subTest(argv=argv[0]):
                done = fixture.run(*argv)
                self.assertTrue(done.stdout.strip() or done.stderr.strip())
                self.assertNotIn(b'\r', done.stdout)
                self.assertNotIn(b'\r', done.stderr)


class FakeToolTests(unittest.TestCase):
    def test_the_windows_launcher_is_a_cmd_file_that_runs_the_script_with_the_python_in_use(self):
        # Generated and inspected only: this host is not Windows, so the .cmd branch is not executed here.
        text = launcher_text('az', 'C:/work/fakes', 'C:/Python/python.exe', True)
        self.assertEqual(text, '@"C:/Python/python.exe" "C:\\work\\fakes\\fake_tool.py" az %*\r\n')

    def test_the_other_launcher_is_an_executable_shell_wrapper_around_the_same_script(self):
        text = launcher_text('gh', '/w/fakes dir', '/usr/bin/python3', False)
        self.assertEqual(text, "#!/bin/sh\nexec /usr/bin/python3 '/w/fakes dir/fake_tool.py' gh \"$@\"\n")

    def test_both_launchers_are_written_for_the_chosen_platform(self):
        with tempfile.TemporaryDirectory() as base:
            windows = PortableClis(base, windows=True)
            self.assertTrue((windows.directory / 'az.cmd').read_bytes().endswith(b'%*\r\n'))
            self.assertFalse((windows.directory / 'az').exists())

    @unittest.skipUnless(os.name == 'posix', 'runs the wrapper')
    def test_the_wrapper_prints_the_canned_answer_logs_the_call_and_returns_its_code(self):
        with tempfile.TemporaryDirectory() as base:
            fakes = PortableClis(base)
            fakes.answer('az', 'account', 'list', out='[1]', err='warn', code=3)
            done = subprocess.run([str(fakes.directory / 'az'), 'account', 'list', '--output', 'json'], capture_output=True)
            self.assertEqual((done.stdout, done.stderr, done.returncode), (b'[1]', b'warn', 3))
            self.assertEqual(fakes.calls(), ['account list --output json'])
            self.assertEqual(subprocess.run([str(fakes.directory / 'gh'), 'auth', 'status']).returncode, 127)


class ByteCheckTests(unittest.TestCase):
    def test_a_lone_c1_byte_is_not_valid_utf8_and_is_reported(self):
        self.assertNotEqual(forbidden_in(b'\x9b[31m'), [])
        self.assertIn('INVALID_UTF8', forbidden_in(b'ok\n\x9b[31m'))

    def test_a_c1_control_encoded_as_utf8_is_reported_by_its_code_point(self):
        self.assertEqual(forbidden_in(b'\xc2\x9b[31m'), ['U+009B'])

    def test_clean_bytes_and_ordinary_non_ascii_pass(self):
        self.assertEqual(forbidden_in('row one\nrow two é 中文\n'.encode('utf-8')), [])

    def test_a_planted_lone_c1_byte_on_stderr_fails_the_stream_check(self):
        planted = subprocess.CompletedProcess([], 0, stdout=b'ok\n', stderr=b'\x9b[31m')
        with self.assertRaises(AssertionError):
            check_streams(self, 'planted', planted)
        check_streams(self, 'control', subprocess.CompletedProcess([], 0, stdout=b'ok\n', stderr=b''))


class InventoryTests(unittest.TestCase):
    def test_the_text_mode_commands_are_the_ones_the_parser_exposes(self):
        # Read from the parser, not typed: a command added with a --json switch or a text --format fails here until the sweep
        # below (and the route test) name it. `workbench workspace` and `workbench terminal` are interactive screens with no
        # switch; their output does not pass through cli.py (see the report), so they are not in this inventory.
        self.assertEqual(text_commands(cli.parser()), TEXT_COMMANDS)


class TextGuardSweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temps = [tempfile.TemporaryDirectory(), tempfile.TemporaryDirectory()]
        for temp in cls.temps:
            cls.addClassCleanup(temp.cleanup)
        cls.hostile = Fixture(HOSTILE, cls.temps[0].name)
        cls.clean = Fixture(CLEAN, cls.temps[1].name)

    def test_no_text_command_writes_a_control_character_to_stdout_or_stderr(self):
        for label, argv in self.hostile.sweep().items():
            with self.subTest(command=label):
                result = self.hostile.run(*argv)
                check_streams(self, label, result)

    def test_the_fake_sign_in_tools_are_python_scripts_with_a_launcher_for_the_platform(self):
        directory = Path(self.hostile.fakes.path_entry())
        self.assertTrue((directory / 'fake_tool.py').exists())
        for tool in ('az', 'gh'):
            self.assertTrue((directory / (tool + ('.cmd' if os.name == 'nt' else ''))).exists(), tool)

    @unittest.skipUnless(os.name == 'posix', 'sign-in reuse is a Unix feature of the product (inherited descriptors)')
    def test_signin_status_runs_in_full_through_the_fakes(self):
        done = self.clean.run('signin', 'status', '--tenant', TENANT_A)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.decode('utf-8').splitlines()[0], 'AZURE: READY')
        self.assertIn('account list --output json', self.clean.fakes.calls())

    def test_the_exit_code_equals_the_exit_code_on_a_clean_fixture(self):
        clean, hostile = self.clean.sweep(), self.hostile.sweep()
        for label in hostile:
            with self.subTest(command=label):
                self.assertEqual(self.hostile.run(*hostile[label]).returncode, self.clean.run(*clean[label]).returncode, label)

    def test_the_guard_changes_nothing_a_clean_fixture_prints(self):
        for label, argv in self.clean.sweep().items():
            with self.subTest(command=label):
                out = self.clean.run(*argv).stdout.decode('utf-8')
                self.assertEqual(cli.text_guard_rows(out.rstrip('\n').split('\n')), out.rstrip('\n'), label)

    def test_json_output_is_the_serialization_of_the_result_and_nothing_else(self):
        for label, argv in self.hostile.json_forms().items():
            with self.subTest(command=label):
                done = self.hostile.run(*argv)
                body = done.stdout.decode('ascii')
                self.assertTrue(body.endswith('\n') and body.count('\n') == 1, label)
                self.assertEqual(json.dumps(json.loads(body), ensure_ascii=True, sort_keys=True, allow_nan=False) + '\n', body, label)
                self.assertTrue(body.isascii() and not FORBIDDEN.search(body.replace('\n', '')), label)


class GuardUnitTests(unittest.TestCase):
    def test_every_code_point_is_changed_if_and_only_if_its_category_is_cc_cf_zl_or_zp(self):
        from intune_iac.workbench_tui import safe_text
        wrong, covered, changed = [], 0, 0
        for number in range(0x110000):
            if 0xd800 <= number <= 0xdfff:
                continue
            char, covered = chr(number), covered + 1
            shown = cli.text_guard(char)
            guarded = unicodedata.category(char) in GUARDED_CATEGORIES
            changed += shown != char
            if (shown != char) != guarded or (guarded and shown != safe_text(char)):
                wrong.append(hex(number))
        self.assertEqual(wrong[:20], [])
        self.assertEqual(covered, 0x110000 - 0x800)
        self.assertGreater(changed, 100)

    def test_the_forbidden_pattern_matches_exactly_the_guarded_categories_except_the_row_newline(self):
        sample = [chr(n) for n in range(0x110000) if not 0xd800 <= n <= 0xdfff]
        matched = {ch for ch in sample if FORBIDDEN.match(ch)}
        expected = {ch for ch in sample if unicodedata.category(ch) in GUARDED_CATEGORIES and ch != '\n'}
        self.assertEqual(len(matched ^ expected), 0)

    def test_the_deprecated_format_controls_are_escaped(self):
        for number in range(0x206a, 0x2070 - 0):
            if unicodedata.category(chr(number)) == 'Cf':
                with self.subTest(code=hex(number)):
                    self.assertEqual(cli.text_guard('Policy 123' + chr(number) + 'ABC'), 'Policy 123\\u%04xABC' % number)

    def test_a_character_outside_the_basic_plane_is_escaped_with_the_long_form_safe_text_uses(self):
        self.assertEqual(cli.text_guard('a' + chr(0xe0001) + 'b'), 'a\\U000e0001b')

    def test_the_characters_next_to_the_guarded_set_pass_unchanged(self):
        for number in NEIGHBOURS:
            with self.subTest(code=hex(number)):
                self.assertEqual(cli.text_guard('x' + chr(number) + 'y'), 'x' + chr(number) + 'y')
        ordinary = 'Policy 123, "quoted" (a-z) éèü 中文 Ж א ا —    '
        self.assertEqual(cli.text_guard(ordinary), ordinary)

    def test_the_direction_marks_and_invisible_format_characters_are_escaped(self):
        for number in (0x200e, 0x200f, 0x061c, 0xfeff, 0x200b, 0x200c, 0x200d, 0x2060, 0x2061, 0x2062, 0x2063, 0x2064):
            with self.subTest(code=hex(number)):
                self.assertEqual(cli.text_guard('Policy 123' + chr(number) + 'ABC'), 'Policy 123\\u%04xABC' % number)

    def test_text_the_renderers_already_escaped_is_unchanged(self):
        from intune_iac.workbench_tui import safe_text
        for value in (HOSTILE, 'plain text, with "quotes" and éè and 中文', 'a' * 300):
            once = safe_text(value)
            self.assertEqual(cli.text_guard(once), once)

    def test_the_row_newline_stays_and_a_newline_inside_a_row_is_escaped(self):
        self.assertEqual(cli.text_guard_rows(['one', 'two' + chr(10) + 'three']), 'one\ntwo\\nthree')

    def test_every_text_route_writes_through_the_guard_whatever_its_renderer_forgot(self):
        """A renderer whose escape is disabled (the deliberate mutation) hands the boundary raw controls on each route."""
        raw = ['row ' + chr(0x1b) + '[2J' + chr(0x9b) + chr(0x2028) + chr(0x202e) + chr(10) + 'forged row', 'second']
        with_tty = type('Tty', (io.StringIO,), {'isatty': lambda self: True})
        routes = (
            ('start', ['start', '.'], [('intune_iac.entry.survey', {}), ('intune_iac.entry.start_lines', raw)], 0, {}),
            ('simulate', ['simulate', '--revision', 'r', '--snapshot', 's', '--format', 'text'],
             [('intune_iac.sim_cli.text_lines', raw)], 0, {}),
            ('signin status', ['signin', 'status'],
             [('intune_iac.cli._signin_command', ({'status': 'ready'}, {})), ('intune_iac.signin_facts.status_lines', raw)], 0, {}),
            ('signin collect', ['signin', 'collect', '--tenant', TENANT_A, '--policy', TENANT_A, '--output', 'o'],
             [('intune_iac.cli._signin_command', ({'status': 'ready'}, {})), ('intune_iac.signin_facts.collect_lines', raw)], 0, {}),
            ('catalog', ['catalog', '.'], [('intune_iac.catalog.catalog_lines', raw)], 0, {}),
            ('engineering', ['engineering'], [('intune_iac.engineering_view.lines_for', raw)], 0, {}),
            ('workbench workflow', ['workbench', 'workflow', '--root', 'r', '--policy', 'p'],
             [('intune_iac.workbench_screens.workflow_text_lines', raw)], 0, {}),
            ('workbench workspace (interrupted)', ['workbench', 'workspace', '--root', 'r'],
             [('intune_iac.workbench.interrupted_text', raw)], 2, {'status': 'interrupted'}))
        for label, argv, patches, code, result in routes:
            with self.subTest(command=label), contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(cli, 'execute', return_value=result))
                for target, value in patches:
                    stack.enter_context(mock.patch(target, return_value=value))
                out = stack.enter_context(contextlib.redirect_stdout(with_tty()))
                self.assertEqual(cli.main(argv), code)
            written = out.getvalue()
            self.assertEqual(forbidden_in(written.encode('utf-8')), [], label)
            self.assertEqual(written, 'row \\u001b[2J\\u009b\\u2028\\u202e\\nforged row\nsecond\n', label)


if __name__ == '__main__':
    unittest.main()
