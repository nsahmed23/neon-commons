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
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from intune_iac import cli
from intune_iac.synthetic import generate_estate
from plugin_tests import sim_support as sim
from plugin_tests.orchestration_fixtures import event, lifecycle, write_export
from plugin_tests.signin_fakes import FakeClis, TENANT_A, azure_account, azure_list, github_hosts

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'

# ESC with a CSI tail, CR and LF inside one value, BEL, DEL, C1 CSI, the line and paragraph separators and a bidirectional override.
HOSTILE = ''.join(chr(n) for n in (0x1b,)) + '[31m' + 'a' + chr(13) + 'b' + chr(10) + 'c' + chr(7) + chr(0x7f) + chr(0x9b) + \
    chr(0x2028) + chr(0x2029) + chr(0x202e) + 'z'
# A file or directory name cannot hold a slash; this one holds every other character of the hostile value.
CLEAN = 'plain-value'
FORBIDDEN = re.compile('[\x00-\x09\x0b-\x1f\x7f-\x9f  ‪-‮⁦-⁩]')
OLD_NAME = 'Privacy pilot 7'


def forbidden_in(data):
    """The forbidden characters in raw output bytes, as code points (a lone C1 byte pair decodes to one)."""
    return sorted({'U+%04X' % ord(ch) for ch in FORBIDDEN.findall(data.decode('utf-8', 'surrogateescape'))})


def replace_everywhere(value, old, new):
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [replace_everywhere(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: replace_everywhere(item, old, new) for key, item in value.items()}
    return value


class Fixture:
    """One working set: a start or catalog directory, an engineering export, simulator documents, fake sign-in clients
    and a workbench store, every recorded string built from `text`."""

    def __init__(self, text, base):
        self.text, self.base = text, Path(base)
        self.fakes = FakeClis(base=str(self.base))
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', COLUMNS='100',
                        PATH=self.fakes.path_entry() + os.pathsep + os.environ.get('PATH', ''))
        self._directory()
        self._engineering()
        self._simulate()
        self._signin()
        self._workbench()

    def run(self, *argv, stdin=''):
        return subprocess.run([sys.executable, '-B', str(CLI), *map(str, argv)], input=stdin.encode(), capture_output=True,
                              cwd='/tmp', timeout=60, env=self.env)

    def _directory(self):
        self.work = self.base / ('dir-' + self.text)
        self.work.mkdir()
        (self.work / ('file-' + self.text + '.json')).write_text(json.dumps({'name': self.text}))
        (self.work / ('note-' + self.text + '.txt')).write_text(self.text)
        (self.work / ('sub-' + self.text)).mkdir()

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
        return {
            'start': ['start', self.work],
            'start --goal': ['start', self.work, '--goal', 'inspect'],
            'catalog': ['catalog', self.work],
            'engineering': ['engineering', '--records', self.records],
            'simulate --format text': ['simulate', '--snapshot', self.snapshot, '--revision', self.revision, '--format', 'text'],
            'signin status': ['signin', 'status', '--tenant', TENANT_A, '--provider', 'all'],
            'workbench workflow': ['workbench', 'workflow', '--root', self.store, '--policy', self.policy_id],
        }

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
                self.assertEqual(forbidden_in(result.stdout), [], label)
                self.assertEqual(forbidden_in(result.stderr), [], label)
                self.assertTrue(result.stdout.strip(), label + ' printed nothing')

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
    def test_every_forbidden_character_is_shown_as_the_escape_safe_text_uses(self):
        from intune_iac.workbench_tui import safe_text
        every = [chr(n) for n in range(0x20) if n != 10] + [chr(0x7f)] + [chr(n) for n in range(0x80, 0xa0)] + \
            [chr(0x2028), chr(0x2029)] + [chr(n) for n in range(0x202a, 0x202f)] + [chr(n) for n in range(0x2066, 0x206a)]
        for char in every:
            with self.subTest(code=hex(ord(char))):
                shown = cli.text_guard('x' + char + 'y')
                self.assertEqual(shown, 'x' + safe_text(char) + 'y')
                self.assertNotRegex(shown, FORBIDDEN)

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
