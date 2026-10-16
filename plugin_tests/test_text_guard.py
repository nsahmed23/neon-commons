"""PKG-TEXT-GUARD items 1 and 2: the inventory, and the one guard at the text output boundary."""
import contextlib
import io
import re
import unittest
from unittest import mock

from intune_iac import cli
from plugin_tests.signin_fakes import TENANT_A

HOSTILE = ''.join(chr(n) for n in (0x1b,)) + '[31m' + 'a' + chr(13) + 'b' + chr(10) + 'c' + chr(7) + chr(0x7f) + chr(0x9b) + \
    chr(0x2028) + chr(0x2029) + chr(0x202e) + 'z'
FORBIDDEN = re.compile('[\x00-\x09\x0b-\x1f\x7f-\x9f  ‪-‮⁦-⁩]')


def forbidden_in(data):
    """The forbidden characters in raw output bytes, as code points (a lone C1 byte pair decodes to one)."""
    return sorted({'U+%04X' % ord(ch) for ch in FORBIDDEN.findall(data.decode('utf-8', 'surrogateescape'))})


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
