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
        # Without colour a heading is still bold; the words and the rule are unchanged.
        self.assertIn('│\x1b[1m[CHANGE REVIEW]\x1b[22m', text)
        self.assertNotIn('\x1b[38;', text)
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


def xterm(code):
    """The xterm 256-colour value the workspace paints with."""
    code = int(code)
    if code < 16:
        raise ValueError('themes use the 6x6x6 cube or the grey ramp')
    if code < 232:
        levels, code = (0, 95, 135, 175, 215, 255), code - 16
        return levels[code // 36], levels[code // 6 % 6], levels[code % 6]
    grey = 8 + 10 * (code - 232)
    return grey, grey, grey


def contrast(first, second):
    """WCAG 2 contrast ratio of two sRGB colours."""
    def luminance(rgb):
        linear = [c / 255 / 12.92 if c / 255 <= 0.03928 else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class ContrastTests(unittest.TestCase):
    """Every text role meets WCAG AA (4.5:1) on its theme background; measured, not judged by eye."""
    def test_every_theme_role_is_readable_on_its_background(self):
        from intune_iac.workbench_tui import THEMES
        for theme, palette in THEMES.items():
            for role in ('fg', 'accent', 'ok', 'warn', 'bad'):
                ratio = contrast(xterm(palette[role]), xterm(palette['bg']))
                self.assertGreaterEqual(ratio, 4.5, '%s %s %.2f' % (theme, role, ratio))


class FrameChromeTests(unittest.TestCase):
    """Title, footer, help and borders: what the frame around every surface says."""
    def test_the_title_names_a_view_shown_on_another_surface(self):
        from intune_iac.workbench_tui import title_line
        self.assertEqual(title_line('Coverage', 'diagnostics', {}), 'INTUNE WORKBENCH  /  Coverage  /  Diagnostics')
        self.assertEqual(title_line('Execution', 'delivery /work/op', {}), 'INTUNE WORKBENCH  /  Execution  /  Delivery')
        self.assertEqual(title_line('Coverage', 'views', {}), 'INTUNE WORKBENCH  /  Coverage')
        self.assertEqual(title_line('Coverage', 'diagnostics', {'status': 'error'}), 'INTUNE WORKBENCH  /  Coverage')

    def test_long_text_is_shortened_at_a_word_with_an_ellipsis(self):
        from intune_iac.workbench_tui import fit
        self.assertEqual(fit('Ready. : opens the complete text command bar; Esc cancels editing.', 40),
                         'Ready. : opens the complete text...')
        self.assertEqual(fit('short', 40), 'short')
        self.assertLessEqual(cell_width(fit('x' * 90, 30, '…')), 30)

    def test_the_help_line_fits_every_width_without_a_cut_word(self):
        from intune_iac.workbench_tui import HELP_LINES, help_line
        for width in (160, 100, 80, 60):
            line = help_line(width)
            self.assertLessEqual(cell_width(line), width)
            self.assertIn(line, HELP_LINES)
            self.assertIn('q exit', line); self.assertIn(': command', line); self.assertIn('? help', line)

    def test_the_status_line_keeps_the_approval_statement_whole(self):
        from intune_iac.workbench_tui import status_line
        # The class is never cut mid-word: when it does not fit, its mode word stands in (the strip leads with it too).
        line = status_line('synthetic_local_process_and_modeled_service_only', 1, 12, 125, 60, short='SYNTHETIC')
        self.assertLessEqual(cell_width(line), 60)
        self.assertEqual(line, '[synthetic] rows 1-12/125 | no automatic approval')

    def test_headings_and_signal_lines_stand_out_with_and_without_colour(self):
        from intune_iac.workbench_tui import THEMES, emphasize, paint
        palette = THEMES['dark']
        signal = '│  ! The newest observation is stale.          │'
        self.assertEqual(emphasize(signal), '│  \x1b[1m! The newest observation is stale.\x1b[22m          │')
        painted = paint(signal, palette)
        self.assertTrue(painted.startswith('│  \x1b[1m! The newest observation is '), painted)
        self.assertIn('\x1b[38;5;%smstale' % palette['warn'], painted)
        self.assertEqual(emphasize('│WHAT THE EVIDENCE SAYS IT DOES     │'), '│\x1b[1mWHAT THE EVIDENCE SAYS IT DOES\x1b[22m     │')
        self.assertEqual(emphasize('│POLICY  Windows Privacy Pilot │'), '│\x1b[1mPOLICY\x1b[22m  Windows Privacy Pilot │')
        # Ordinary lines, values and identities are left as they are.
        for line in ('│Identity  2222 | windows10 │', '│      = "DEVICE_VALUE"   │', '│  include  4444-4444 │'):
            self.assertEqual(emphasize(line), line)

    def test_a_border_announces_more_content(self):
        from intune_iac.workbench_tui import ruled
        self.assertEqual(ruled('+', '-', '+', 30, ' more below: PgDn '), '+-- more below: PgDn ----------+')
        self.assertEqual(ruled('+', '-', '+', 10, ' more below: PgDn '), '+' + '-' * 10 + '+')

    def workspace(self, **extra):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(tab=7, value={'schema_version': 'workbench-families/1', 'available': False,
                                                'reason': 'family_coverage_not_packaged', 'families': []},
                                  selected=None, facts={}, rows=[], operation_rows=[], _detail_cache=None, **extra)
        return workspace

    def test_cached_record_lines_follow_the_value_not_its_address(self):
        workspace = self.workspace(layer='raw')
        workspace.value = {'a': [1, 2, 3]}
        self.assertEqual(workspace._raw_count(), 7)
        self.assertEqual(len(workspace._detail_lines(80)), 7)
        # Replaced twice without a render: the first value is freed, and CPython's dict free list
        # hands its address to the next dict. An address-keyed cache would return the first value's lines.
        workspace.value = {'b': 1}
        workspace.value = {'c': 1}
        self.assertEqual(workspace._raw_count(), 3)
        self.assertEqual(workspace._detail_lines(80), ['{', '  "c": 1', '}'])

    def test_a_wide_body_puts_the_raw_record_beside_the_summary(self):
        workspace = self.workspace(layer='raw')
        wide = workspace._body_lines(160, '│')
        left = (160 - 3) * 11 // 20
        self.assertEqual(wide[0][:len('[POLICY FAMILIES]')], '[POLICY FAMILIES]')
        self.assertEqual(wide[0][left:left + 3], ' │ ')
        self.assertTrue(wide[0][left + 3:].startswith('RAW RECORD'))
        self.assertTrue(any(line[left + 3:] == '{' for line in wide))
        for line in wide:
            self.assertLessEqual(cell_width(line), 160, line)
        # Below the wide threshold, and on the summary, the body stays one column.
        self.assertEqual(workspace._body_lines(120, '│'), workspace._data_lines(120))
        summary = self.workspace(layer='summary')
        self.assertEqual(summary._body_lines(160, '│'), summary._data_lines(160))
        self.assertTrue(summary._data_lines(160)[-1].startswith('Evidence: e typed details | r complete raw record'))

    def test_lineage_freshness_never_becomes_the_observation_freshness(self):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(selected='p1', facts={'object_id': 'p1', 'observation': 'fresh'}, last_command='lineage')
        workspace._learn({'object_id': 'p1', 'provenance_origin': {'kind': 'repository_intent'},
                          'freshness': 'recorded_intent_not_revalidated'})
        self.assertEqual(workspace.facts['observation'], 'fresh')
        workspace._learn({'object_id': 'p1', 'snapshot_id': 's', 'freshness': 'stale', 'evidence_class': 'synthetic'})
        self.assertEqual((workspace.facts['observation'], workspace.facts['evidence_class']), ('stale', 'synthetic'))


if __name__ == '__main__':
    unittest.main()
