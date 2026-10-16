"""The read-only :catalog layer in the workspace (PKG-UXVIS-3 item 4): the same records and states as the catalog command,
closed by Esc, no number key, fitting 120, 80 and 60 columns, a larger-window sentence below 60x20, words not colour."""
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from plugin_tests import test_catalog as tc
from plugin_tests import test_readiness as tr

TENANT = '11111111-1111-4111-8111-111111111111'
STATE_WORDS = ('available', 'configured', 'authenticated', 'operation-ready', 'blocked', 'unsupported')
ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')


def value():
    return tc.catalog(tr.repository_item(), tr.context_item())


class Keys:
    """A key reader that returns the given keys in order and then ends the session."""
    def __init__(self, *keys):
        self.keys = list(keys)

    def read(self):
        return self.keys.pop(0) if self.keys else 'eof'


def workspace(directory, size=(80, 24), color=False):
    from intune_iac.workbench_store import WorkbenchStore
    from intune_iac.workbench_tui import Workspace
    store = WorkbenchStore.create(Path(directory) / 'store', TENANT)
    out = io.StringIO()
    ws = Workspace(store.root, stdin=io.StringIO(), stdout=out, no_color=not color, rules='ascii')
    ws._terminal_size = lambda: size
    ws.size = size
    ws.out = out
    return ws


def rows_of(ws):
    ws.out.seek(0); ws.out.truncate()
    ws.draw()
    return ANSI.sub('', ws.out.getvalue().replace('\r\n', '\n')).split('\n')


class EngineCommandTests(unittest.TestCase):
    def test_the_workbench_command_returns_the_catalog_record_the_cli_builds(self):
        from intune_iac.workbench_tui import run_workspace
        with tempfile.TemporaryDirectory() as directory:
            from intune_iac.workbench_store import WorkbenchStore
            store = WorkbenchStore.create(Path(directory) / 'store', TENANT)
            out = io.StringIO()
            run_workspace(store.root, stdin=io.StringIO('catalog\nquit\n'), stdout=out)
            text = out.getvalue()
            self.assertNotIn('unknown_workbench_command', text)
            start = text.index('{\n  "schema_version": "integration-catalog/1"')
            shown, _ = json.JSONDecoder().raw_decode(text[start:])
            from intune_iac import catalog, entry
            expected = catalog.build(entry.survey(Path(directory)))
            states = lambda v: [{k: g[k] for k in ('goal', 'available', 'configured', 'operation_ready', 'blocked', 'unsupported')}
                                for g in v['integrations'][0]['goals']]
            self.assertEqual(states(shown), states(expected))
            self.assertEqual(shown['other_integrations'], expected['other_integrations'])
            self.assertIs(shown['execution_authorized'], False)

    def test_catalog_is_a_read_only_view_and_listed_in_the_help(self):
        from intune_iac.workbench import HELP
        from intune_iac.workbench_tui import VIEW_COMMANDS
        self.assertIn('catalog', VIEW_COMMANDS)
        self.assertTrue(any(line.startswith('catalog') for line in HELP['navigation']))


class LayerTests(unittest.TestCase):
    def test_a_catalog_result_opens_the_catalog_layer_on_the_help_surface(self):
        with tempfile.TemporaryDirectory() as directory:
            ws = workspace(directory)
            ws.last_command = 'catalog'
            ws.receive(value())
            self.assertEqual(ws.layer, 'catalog')
            self.assertEqual(ws.tab, 7)
            rows = rows_of(ws)
            self.assertIn('catalog', rows[0].lower())

    def test_every_state_is_a_word_in_the_layer_at_each_size_and_no_line_overruns(self):
        with tempfile.TemporaryDirectory() as directory:
            ws = workspace(directory)
            ws.value, ws.layer, ws.tab, ws.last_command = value(), 'catalog', 7, 'catalog'
            for size in ((120, 40), (80, 24), (60, 20)):
                ws._terminal_size = lambda size=size: size
                ws.size = size
                ws.scroll = 0
                shown = []
                for _ in range(12):
                    rows = rows_of(ws)
                    for row in rows:
                        self.assertLessEqual(len(row), size[0], (size, row))
                        self.assertTrue(all(32 <= ord(c) < 127 for c in row), repr(row))
                    shown += rows
                    ws.scroll += size[1] - 8
                text = '\n'.join(shown)
                for word in STATE_WORDS:
                    self.assertIn(word, text, (size, word))
                self.assertIn('No other integration is available in this build', text.replace('\n', ' '))
                self.assertNotIn('larger window', text)

    def test_no_colour_draws_no_colour_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            ws = workspace(directory)
            ws.value, ws.layer, ws.tab, ws.last_command = value(), 'catalog', 7, 'catalog'
            ws.out.seek(0); ws.out.truncate()
            ws.draw()
            self.assertNotIn('38;5', ws.out.getvalue())
            self.assertNotIn('48;5', ws.out.getvalue())

    def test_the_layer_shows_the_same_lines_as_the_catalog_command(self):
        from intune_iac import catalog
        with tempfile.TemporaryDirectory() as directory:
            ws = workspace(directory, size=(120, 400))
            data = value()
            ws.value, ws.layer, ws.tab, ws.last_command = data, 'catalog', 7, 'catalog'
            body = [row.strip() for row in rows_of(ws)]
            for line in catalog.catalog_lines(data, 116):
                if line.strip():
                    self.assertIn(line.strip(), body)

    def test_a_window_below_60x20_says_the_catalog_needs_a_larger_window(self):
        with tempfile.TemporaryDirectory() as directory:
            ws = workspace(directory)
            ws.value, ws.layer, ws.tab, ws.last_command = value(), 'catalog', 7, 'catalog'
            for size in ((40, 12), (59, 24), (80, 19)):
                ws._terminal_size = lambda size=size: size
                ws.size = size
                text = ' '.join(rows_of(ws))
                self.assertIn('larger window', text, size)
                self.assertNotIn('operation-ready', text, size)

    def test_below_the_frame_minimum_the_constrained_screen_says_it_too(self):
        with tempfile.TemporaryDirectory() as directory:
            ws = workspace(directory)
            ws.value, ws.layer, ws.tab, ws.last_command = value(), 'catalog', 7, 'catalog'
            for size in ((39, 11), (30, 8)):
                ws._terminal_size = lambda size=size: size
                text = ' '.join(rows_of(ws))
                self.assertIn('larger window', text, size)
                self.assertIn('atalog', text, size)

    def test_esc_closes_the_layer_and_returns_to_the_view_before_it(self):
        with tempfile.TemporaryDirectory() as directory:
            ws = workspace(directory)
            ws.value, ws.layer, ws.tab, ws.last_command = value(), 'catalog', 7, 'catalog'
            ws.trail = [(0, 'overview')]
            ws.key_reader = Keys('escape')
            self.assertEqual(ws.input(''), 'overview')
            self.assertEqual(ws.layer, 'summary')

    def test_esc_with_no_earlier_view_still_closes_the_layer(self):
        with tempfile.TemporaryDirectory() as directory:
            ws = workspace(directory)
            ws.value, ws.layer, ws.tab, ws.last_command = value(), 'catalog', 7, 'catalog'
            ws.trail = []
            ws.key_reader = Keys('escape')
            self.assertEqual(ws.input(''), 'overview')
            self.assertEqual(ws.layer, 'summary')

    def test_the_layer_opens_nothing_that_changes_state(self):
        with tempfile.TemporaryDirectory() as directory:
            ws = workspace(directory)
            ws.value, ws.layer, ws.tab, ws.last_command = value(), 'catalog', 7, 'catalog'
            for char in ('a', 'e', 'r', 'f'):
                ws.key_reader = Keys(('text', char), 'eof')
                with self.assertRaises(EOFError):
                    ws.input('')
                self.assertEqual(ws.layer, 'catalog', char)
                self.assertIn('read-only', ws.notice)
            self.assertFalse(ws.mode)

    def test_the_key_map_stays_one_to_nine_with_no_catalog_key(self):
        from intune_iac.workbench_tui import TABS, TAB_COMMANDS
        self.assertEqual(TABS, ('Estate', 'Inspector', 'Relationships', 'History', 'Plan', 'Execution', 'Coverage', 'Help',
                                'Repository'))
        self.assertNotIn('catalog', TAB_COMMANDS)

    def test_the_key_line_names_esc_in_the_layer(self):
        from intune_iac.workbench_tui import help_line
        for width in (120, 80, 60, 40):
            line = help_line(width, 'catalog')
            self.assertIn('Esc', line)
            self.assertLessEqual(len(line), width)
            self.assertNotIn('a actions', line)


if __name__ == '__main__':
    unittest.main()
