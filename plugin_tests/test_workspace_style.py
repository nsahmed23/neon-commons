"""The workspace's visual language: fine rules, words first, focus and pinned selection apart, themes.

Hand-written expectations; no terminal is needed except where noted.
"""
import io
import re
import unittest

from intune_iac.workbench_tui import cell_width

SGR = re.compile(r'\x1b\[[0-9;]*m')


class RulesTests(unittest.TestCase):
    def test_fine_rules_need_utf8_and_a_capable_terminal(self):
        from intune_iac.workbench_tui import choose_rules
        self.assertEqual(choose_rules('utf-8', 'xterm-256color', 'auto'), 'unicode')
        self.assertEqual(choose_rules('UTF8', 'screen', 'auto'), 'unicode')
        self.assertEqual(choose_rules('ascii', 'xterm-256color', 'auto'), 'ascii')
        self.assertEqual(choose_rules('utf-8', 'linux', 'auto'), 'ascii')
        self.assertEqual(choose_rules('utf-8', 'xterm-256color', 'ascii'), 'ascii')

    def frame(self, rules, color=False, theme='dark', lines=('[CHANGE REVIEW]', 'Freshness stale', 'plain')):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        out = io.StringIO()
        workspace.__dict__.update(stdout=out, tab=0, value={'evidence_class': 'synthetic'}, scroll=0, mode=None, notice='Ready.',
                                  rules=rules, color=color, theme=theme, selected=None, facts={}, store=type('S', (), {'tenant_id': '11111111'})())
        workspace._terminal_size = lambda: (40, 12)
        workspace._data_lines = lambda width: list(lines)
        workspace.draw()
        return out.getvalue()

    def test_unicode_frame_uses_fine_rules_and_ascii_keeps_its_glyphs(self):
        text = self.frame('unicode')
        self.assertIn('┌' + '─' * 38 + '┐', text)
        self.assertIn('│[CHANGE REVIEW]', text)
        self.assertIn('└' + '─' * 38 + '┘', text)
        ascii_text = self.frame('ascii')
        self.assertIn('+' + '-' * 38 + '+', ascii_text)
        self.assertNotIn('─', ascii_text)

    def test_every_drawn_line_keeps_the_terminal_width(self):
        for rules in ('unicode', 'ascii'):
            for color in (False, True):
                lines = SGR.sub('', self.frame(rules, color)).replace('\x1b[H', '').replace('\x1b[J', '').split('\r\n')
                for line in lines:
                    self.assertEqual(cell_width(line), 40, (rules, color, line))

    def test_color_reinforces_words_and_never_replaces_them(self):
        plain = SGR.sub('', self.frame('unicode', color=True))
        self.assertIn('Freshness stale', plain)
        painted = self.frame('unicode', color=True)
        self.assertRegex(painted, r'\x1b\[38;5;\d+mstale\x1b\[38;5;\d+m')
        self.assertRegex(painted, r'\x1b\[1m\[CHANGE REVIEW\]\x1b\[22m')
        self.assertNotIn('\x1b[38;5', self.frame('unicode', color=False))


class PaintTests(unittest.TestCase):
    def test_only_named_states_are_painted_and_the_background_survives(self):
        from intune_iac.workbench_tui import THEMES, paint
        palette = THEMES['dark']
        line = '│  [x] 1 Proposal  repository intent (current) | Graph value translation NOT verified'
        painted = paint(line, palette)
        self.assertEqual(SGR.sub('', painted), line)
        self.assertIn('\x1b[38;5;%sm[x]\x1b[38;5;%sm' % (palette['ok'], palette['fg']), painted)
        self.assertNotIn('verified\x1b', painted)
        self.assertNotIn('\x1b[0m', painted)
        for word, tone in (('[!]', 'bad'), ('REFUSED', 'bad'), ('expired', 'bad'), ('[?]', 'warn'),
                           ('NO CONFIGURATION CHANGE', 'ok'), ('REPOSITORY CHANGED SINCE THE RECORDED INTENT', 'warn')):
            self.assertIn('\x1b[38;5;%sm%s' % (palette[tone], word), paint('│' + word + ' here', palette), word)

    def test_every_theme_defines_the_same_roles(self):
        from intune_iac.workbench_tui import THEMES
        self.assertEqual(sorted(THEMES), ['blueprint', 'dark', 'high-contrast', 'light'])
        for name, palette in THEMES.items():
            self.assertEqual(sorted(palette), ['accent', 'bad', 'bg', 'fg', 'ok', 'warn'], name)
            self.assertEqual(len(set(palette[role] for role in ('fg', 'ok', 'warn', 'bad'))), 4, name)

    def test_an_unknown_theme_is_refused(self):
        from intune_iac.io import AppError
        from intune_iac.workbench_tui import run_workspace
        with self.assertRaises(AppError) as caught:
            run_workspace('/nonexistent', theme='neon')
        self.assertEqual(caught.exception.code, 'workspace_theme_invalid')


class EstateMarkerTests(unittest.TestCase):
    def test_focus_and_pinned_selection_are_marked_apart(self):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        rows = [{'object_id': 'a' * 8, 'name': 'A'}, {'object_id': 'b' * 8, 'name': 'B'}, {'object_id': 'c' * 8, 'name': 'C'}]
        workspace.__dict__.update(tab=0, rows=rows, highlight=0, selected='b' * 8, value={'objects': rows},
                                  operation_rows=[], _detail_cache=None)
        lines = workspace._data_lines(80)
        self.assertIn('>  ' + 'a' * 8, lines)
        self.assertIn(' * ' + 'b' * 8, lines)
        self.assertIn('   ' + 'c' * 8, lines)
        self.assertTrue(any('> focus' in line and '* pinned selection' in line for line in lines))


if __name__ == '__main__':
    unittest.main()
