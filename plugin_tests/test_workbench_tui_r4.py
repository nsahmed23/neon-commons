"""Real Linux PTY/input and independent state assertions for visual presentation.

This does not replace the independent connected-maintenance qualifier or claim
native Windows, Graph, Azure, CI or device qualification.
"""
import copy
import io
import json
import os
from pathlib import Path
import select
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from intune_iac.io import AppError
from intune_iac.synthetic import generate_estate
from intune_iac.modeled_service import BASE, ModeledService
from intune_iac.workbench_store import WorkbenchStore
from intune_iac.workbench_tui import (ANSI_END, CONTEXT_VERSION, Workspace, cell_width,
    clip, pad, run_workspace, safe_text, terminal_session, wrap)

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'


class PresentationTests(unittest.TestCase):
    def test_controls_bidi_combining_are_visible_and_original_is_unchanged(self):
        original = '界 e\u0301\x1b]52;c;canary\x07\rFORGED\b\u202e\u009b31m'
        shown = safe_text(original)
        self.assertEqual(shown, '界 e\\u0301\\u001b]52;c;canary\\u0007\\rFORGED\\u0008\\u202e\\u009b31m')
        self.assertEqual(original.count('\x1b'), 1)
        self.assertFalse(any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in shown))

    def test_unicode_width_wrap_and_padding_do_not_overrun(self):
        self.assertEqual(cell_width('A界B'), 4)
        self.assertEqual(clip('A界B', 2), 'A')
        self.assertEqual(pad('界', 3), '界 ')
        for size in (12, 19, 40, 120):
            rendered = list(wrap('界' * 99 + '\u202eabc', size))
            self.assertTrue(all(cell_width(line) <= size for line in rendered))
            self.assertEqual(''.join(rendered), safe_text('界' * 99 + '\u202eabc'))

    def test_no_tty_keeps_complete_text_interface_without_ansi(self):
        with tempfile.TemporaryDirectory() as directory:
            store = WorkbenchStore.create(Path(directory) / 'store', '11111111-1111-4111-8111-111111111111')
            output = io.StringIO()
            result = run_workspace(store.root, stdin=io.StringIO('help\noverview\nquit\n'), stdout=output)
            self.assertEqual(result['status'], 'closed')
            self.assertIn('execute OPERATION_DIR EXPLICIT_REVIEW_DIGEST', output.getvalue())
            self.assertIn('restore-propose', output.getvalue())
            self.assertNotIn('\x1b', output.getvalue())
            self.assertFalse((store.root / 'workspace-context.json').exists())

    def test_no_tty_rejects_entire_oversized_physical_line(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            estate = generate_estate(seed=718, policy_count=1)
            object_ids = [p['id'] for p in estate['truth']['policies']]
            service = ModeledService.create(root / 'service', estate['capture'], object_ids)
            store = WorkbenchStore.create(root / 'store', estate['truth']['tenant_id'])
            store.collect(service)
            result = subprocess.run([sys.executable, '-B', str(CLI), 'workbench', 'workspace',
                '--root', str(store.root), '--service-root', str(service.root)],
                input='x' * 16386 + 'collect\nquit\n', text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertIn('invalid_workbench_request', result.stdout)
            self.assertEqual(len(store.collection_history()), 1,
                             'The tail of an oversized physical input line must never become another engine command')

    def test_context_rejects_tenant_substitution_mutation_replay_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = WorkbenchStore.create(root / 'store', '11111111-1111-4111-8111-111111111111')
            context = store.root / 'workspace-context.json'
            base = {'schema_version': CONTEXT_VERSION, 'tenant_id': store.tenant_id, 'selected': None,
                    'tab': 0, 'view_command': 'overview', 'page_command': 'overview 10 0'}
            for key, value in (('tenant_id', '22222222-2222-4222-8222-222222222222'),
                               ('view_command', 'execute /private/operation approved'),
                               ('page_command', 'overview\nexecute /private/operation approved'), ('tab', True)):
                candidate = dict(base); candidate[key] = value
                context.write_text(json.dumps(candidate)); context.chmod(0o600)
                before = context.read_bytes()
                with self.assertRaises(AppError): Workspace(store.root, stdin=io.StringIO(), stdout=io.StringIO())
                self.assertEqual(context.read_bytes(), before)
            context.unlink()
            outside = root / 'outside'; outside.write_text(json.dumps(base)); outside.chmod(0o600)
            context.symlink_to(outside)
            with self.assertRaises(AppError): Workspace(store.root, stdin=io.StringIO(), stdout=io.StringIO())
            self.assertTrue(context.is_symlink())


@unittest.skipUnless(os.name == 'posix' and sys.platform.startswith('linux'), 'Requires actual Linux PTY')
class VisualPTYTests(unittest.TestCase):
    def setUp(self):
        import fcntl
        import pty
        import struct
        import termios
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.estate = generate_estate(seed=717, policy_count=8)
        self.tenant = self.estate['truth']['tenant_id']
        self.ids = [p['id'] for p in self.estate['truth']['policies']]
        self.service = self.root / 'service'
        capture = self.root / 'capture.json'; capture.write_text(json.dumps(self.estate['capture']))
        ModeledService.create(self.service, self.estate['capture'], self.ids)
        self.store = WorkbenchStore.create(self.root / 'store', self.tenant)
        self.store.collect(ModeledService(self.service))
        self.master, self.slave = pty.openpty()
        self.addCleanup(os.close, self.master)
        self.addCleanup(os.close, self.slave)
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack('HHHH', 32, 120, 0, 0))
        self.before_attrs = termios.tcgetattr(self.slave)
        self.output = bytearray()
        self.proc = None

    def launch(self, *args):
        import fcntl
        import termios
        def session():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        env = dict(os.environ, TERM='xterm-256color', PYTHONDONTWRITEBYTECODE='1')
        self.proc = subprocess.Popen([sys.executable, '-B', str(CLI), 'workbench', 'workspace',
            '--root', str(self.store.root), '--service-root', str(self.service), *args],
            stdin=self.slave, stdout=self.slave, stderr=self.slave, env=env, cwd='/tmp', preexec_fn=session)
        self.addCleanup(self.cleanup_child)

    def cleanup_child(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill(); self.proc.wait(timeout=5)

    def read_until(self, needle, start=0, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if needle in self.output[start:]: return
            if select.select([self.master], [], [], min(.1, max(0, deadline - time.monotonic())))[0]:
                try: data = os.read(self.master, 65536)
                except OSError: break
                self.output.extend(data)
                if len(self.output) > 8 * 1024 * 1024: self.fail('PTY output exceeded fixture bound')
            elif self.proc and self.proc.poll() is not None: break
        self.fail('Expected inert output marker did not arrive: ' + repr(needle))

    def drain(self):
        # Initial help, overview and input each paint a frame. Consume earlier
        # frames before interpreting a response to a new key. No UI polling
        # output is expected while idle in this event-driven profile.
        deadline = time.monotonic() + .25
        while time.monotonic() < deadline and select.select([self.master], [], [], .04)[0]:
            self.output.extend(os.read(self.master, 65536))

    def settle(self, start=0, timeout=5):
        # A command draws a RUNNING frame, then the frame with its result. Every frame ends with ESC [ J, and
        # no content can contain it (text is escaped), so wait for the end of the first complete frame after a
        # RUNNING frame that does not itself say RUNNING.
        self.read_until(b'RUNNING:', start, timeout=timeout)
        position = bytes(self.output).find(b'RUNNING:', start)
        while True:
            self.read_until(b'\x1b[J', position, timeout=timeout)
            end = bytes(self.output).find(b'\x1b[J', position) + 3
            self.read_until(b'\x1b[J', end, timeout=timeout)
            following = bytes(self.output).find(b'\x1b[J', end)
            if b'RUNNING:' not in bytes(self.output)[end:following]:
                return
            position = end

    def launched(self, start=0, timeout=5):
        # A fresh launch draws its first view without a RUNNING frame; a resumed one re-sends its views. Either
        # way the first view shown says where the engineer is.
        self.read_until(b"Viewing ", start, timeout=timeout)

    def key(self, value, marker=None):
        self.drain()
        before = len(self.output)
        os.write(self.master, value)
        if marker is None:
            return self.settle(before, timeout=3)
        self.read_until(marker, before, timeout=3)

    def close_visual(self, key=b'q'):
        import termios
        self.drain()
        before = len(self.output)
        os.write(self.master, key)
        self.read_until(ANSI_END.encode(), before, timeout=3)
        self.proc.wait(timeout=3)
        self.assertEqual(termios.tcgetattr(self.slave), self.before_attrs)
        self.assertEqual(self.proc.returncode, 0)

    def test_keyboard_navigation_edit_cancel_context_and_no_mutation(self):
        before = ModeledService(self.service).snapshot()
        started = time.monotonic(); self.launch('--no-color', '--reduced-motion')
        self.launched()
        self.assertLess(time.monotonic() - started, 5)
        self.key(b'\r')  # actual Enter selects immutable row identity
        context = json.loads((self.store.root / 'workspace-context.json').read_text())
        selected = context['selected']; self.assertIn(selected, self.ids)
        self.key(b'3'); self.key(b'4')
        self.key(b':execute /never/approved invalid\x1b', marker=b'EDIT CANCELLED')
        self.key(b':settings\r')
        self.assertEqual(ModeledService(self.service).snapshot()['current'], before['current'])
        self.assertEqual(self.store.operations(), [])
        self.close_visual()
        context = json.loads((self.store.root / 'workspace-context.json').read_text())
        self.assertEqual(context['selected'], selected)
        self.assertEqual(context['view_command'], 'settings')
        self.assertNotIn('/never/approved', json.dumps(context))
        self.assertNotIn(b'\x1b[38;', self.output)

    def test_exact_plan_and_execution_panes_never_auto_replay(self):
        object_id = self.store.overview(limit=1)['objects'][0]['object_id']
        before = ModeledService(self.service).snapshot()['current']['objects']
        desired = copy.deepcopy(self.store.inspect(object_id)['body'])
        desired['description'] = 'A reviewed visual fixture correction'
        desired_path = self.root / 'desired.json'; desired_path.write_text(json.dumps(desired))
        operation = self.root / 'operation'
        self.launch('--no-color'); self.launched(); self.key(b'\r')
        self.key((':propose ' + shlex.quote(str(desired_path)) + ' ' + shlex.quote(str(operation)) + '\r').encode())
        journal = json.loads((operation / 'journal.json').read_text())
        self.assertEqual(journal['status'], 'prepared')
        self.assertIn(b'[PLAN REVIEW]', self.output)
        self.key(b'1'); self.key(b'5')  # Read-only review of active exact operation.
        self.assertEqual(json.loads((operation / 'journal.json').read_text())['status'], 'prepared')
        self.key((':execute ' + shlex.quote(str(operation)) + ' ' + journal['plan_sha256'] + ' lost-response\r').encode())
        self.assertEqual(json.loads((operation / 'journal.json').read_text())['status'], 'outcome_unknown')
        service_before_pane = ModeledService(self.service).snapshot()
        expected = copy.deepcopy(before); expected[object_id] = desired
        self.assertEqual(service_before_pane['current']['objects'], expected)
        self.key(b'4')
        self.key(b'6', marker=b'LAST RESULT:')
        self.assertIn(b'[EXECUTION RESULT]', self.output)
        self.assertEqual(ModeledService(self.service).snapshot(), service_before_pane)
        self.close_visual()
        context = json.loads((self.store.root / 'workspace-context.json').read_text())
        self.assertNotIn(str(operation), json.dumps(context))
        self.assertNotIn(journal['plan_sha256'], json.dumps(context))

    def test_page_navigation_and_exact_search_share_engine(self):
        self.launch('--no-color'); self.launched()
        self.key(b':overview 3 0\r')
        self.key(b'n')
        value = json.loads((self.store.root / 'workspace-context.json').read_text())
        self.assertEqual(value['page_command'], 'overview 3 3')
        self.assertIsNone(value['selected'])
        self.key(b'\r')
        value = json.loads((self.store.root / 'workspace-context.json').read_text())
        expected = self.store.overview(limit=3, offset=3)['objects'][0]['object_id']
        self.assertEqual(value['selected'], expected)
        self.key(b'/Privacy\r')
        value = json.loads((self.store.root / 'workspace-context.json').read_text())
        self.assertEqual(shlex.split(value['page_command']), ['search-page', '10', '0', 'Privacy'])
        self.close_visual()
        self.assertEqual(self.store.operations(), [])

    def test_global_filter_pages_and_resume_preserve_declared_scope(self):
        self.launch('--no-color'); self.launched()
        self.key(b':views-page 3 0 Privacy unknown complete_fresh -\r')
        self.assertIn(b'Global filters:', self.output)
        self.assertIn(b'Matching objects: 8 / inventory: 8', self.output)
        self.key(b'n')
        context = json.loads((self.store.root / 'workspace-context.json').read_text())
        self.assertEqual(shlex.split(context['page_command']), ['views-page', '3', '3', 'Privacy', 'unknown', 'complete_fresh', '-'])
        self.key(b'\r')
        context = json.loads((self.store.root / 'workspace-context.json').read_text())
        self.assertEqual(context['selected'], sorted(self.ids)[3])
        self.assertEqual(context['view_command'], 'inspect')
        self.close_visual()
        self.output = bytearray(); self.launch('--no-color')
        self.read_until(b'WHAT THE EVIDENCE SAYS IT DOES')
        self.drain()
        context = json.loads((self.store.root / 'workspace-context.json').read_text())
        self.assertEqual(shlex.split(context['page_command']), ['views-page', '3', '3', 'Privacy', 'unknown', 'complete_fresh', '-'])
        self.assertEqual(context['selected'], sorted(self.ids)[3])
        self.close_visual()

    def test_oversized_bracketed_paste_is_rejected_without_dispatch(self):
        self.launch('--no-color'); self.launched(); self.drain()
        start = len(self.output)
        os.write(self.master, b'\x1b[200~' + b'x' * 16385 + b'\x1b[201~\r')
        self.read_until(b'INPUT REJECTED:', start)
        self.assertEqual(self.store.operations(), [])
        self.close_visual()

    def test_reopen_restores_readonly_selection_and_history(self):
        self.launch(); self.launched(); self.key(b'\r'); self.key(b'4'); self.close_visual()
        saved = json.loads((self.store.root / 'workspace-context.json').read_text())
        self.output = bytearray(); self.launch()
        self.read_until(b'[OBSERVATION HISTORY]')
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            context = json.loads((self.store.root / 'workspace-context.json').read_text())
            if context['view_command'] == 'history-recent 10 0': break
            time.sleep(.02)
        self.assertEqual(context['selected'], saved['selected'])
        self.assertEqual(context['view_command'], 'history-recent 10 0')
        self.close_visual()
        self.assertEqual(self.store.operations(), [])

    def test_1001_observation_history_pages_and_resume_through_actual_pty(self):
        from plugin_tests.test_workbench_recent_history_r4 import retained_fixture
        fixture = self.root / 'retained-history'; fixture.mkdir()
        self.store, oid = retained_fixture(fixture)
        self.launch(); self.launched(); self.key(b'\r'); self.key(b'4')
        self.key(b':history-recent 2 0\r')
        self.key(b'n')
        context = json.loads((self.store.root / 'workspace-context.json').read_text())
        self.assertEqual(context['selected'], oid)
        self.assertEqual(context['view_command'], 'history-recent 2 2')
        self.assertEqual(context['tab'], 3)
        self.key(b'p')
        context = json.loads((self.store.root / 'workspace-context.json').read_text())
        self.assertEqual(context['view_command'], 'history-recent 2 0')
        self.key(b'n'); self.close_visual()
        self.output = bytearray(); self.launch(); self.read_until(b'[OBSERVATION HISTORY]')
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            context = json.loads((self.store.root / 'workspace-context.json').read_text())
            if context['view_command'] == 'history-recent 2 2': break
            time.sleep(.02)
        self.assertEqual(context['selected'], oid)
        self.assertEqual(context['view_command'], 'history-recent 2 2')
        self.assertIn(b'Newest first', self.output)
        self.close_visual()
        self.assertEqual(self.store.recent_history_page(oid)['pagination']['total_observations'], 1001)
        self.assertEqual(self.store.operations(), [])

    def test_resize_hostile_strings_and_bracketed_paste_need_submission(self):
        import fcntl
        import struct
        import termios
        service = ModeledService(self.service)
        body = copy.deepcopy(service.snapshot()['current']['objects'][self.ids[0]])
        body['name'] = '界 e\u0301\x1b]52;c;canary\x07\rFORGED\b\u202e'
        response = service.request('PATCH', BASE + '/' + self.ids[0], tenant_id=self.tenant,
                                   body=body, if_match=str(service.snapshot()['revision']))
        self.assertEqual(response['status'], 200)
        self.store.collect(service)
        self.launch('--theme', 'light', '--ascii'); self.launched()
        self.assertEqual(self.store.inspect(self.ids[0])['body']['name'], body['name'])
        self.assertNotIn(b'\x1b]', self.output)
        self.assertNotIn('\u202e'.encode(), self.output)
        start = len(self.output)
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack('HHHH', 14, 32, 0, 0))
        # 32 columns is below the documented minimum (40x12): the constrained state, which still takes input.
        self.read_until(b'below 40x12', start)
        self.key(b'\x1b[200~execute /not/approved invalid\nquit\x1b[201~\x1b', marker=b'EDIT CANCELLED')
        self.assertIsNone(self.proc.poll())
        self.assertEqual(self.store.operations(), [])
        self.close_visual()

    def test_utf8_terminal_draws_fine_rules_and_ascii_on_request(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}):
            self.launch('--theme', 'blueprint')
        self.launched()
        self.assertIn('┌─'.encode(), self.output)
        self.assertIn(b'\x1b[48;5;17;', self.output)  # the blueprint background
        self.close_visual()
        self.output = bytearray()
        with patch.dict(os.environ, {'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}):
            self.launch('--ascii', '--no-color')
        self.launched()
        self.assertNotIn('─'.encode(), self.output)
        self.assertNotIn(b'\x1b[48;5;', self.output)
        self.close_visual()

    def test_eof_and_sigint_restore_terminal(self):
        self.launch(); self.launched(); self.close_visual(b'\x04')
        self.output = bytearray(); self.launch(); self.launched()
        start = len(self.output); os.kill(self.proc.pid, signal.SIGINT)
        self.read_until(ANSI_END.encode(), start)
        self.proc.wait(timeout=3)
        import termios
        self.assertEqual(termios.tcgetattr(self.slave), self.before_attrs)
        self.assertEqual(self.store.operations(), [])

    def test_primary_exception_survives_cleanup_failure(self):
        import termios
        from unittest.mock import patch
        native_set = termios.tcsetattr
        calls = []
        class BrokenOutput:
            def write(self, value):
                if value == ANSI_END: raise OSError('synthetic cleanup failure')
            def flush(self): pass
        def fail_second(*args):
            calls.append(args)
            if len(calls) == 2: raise OSError('synthetic attribute cleanup failure')
            return native_set(*args)
        with os.fdopen(os.dup(self.slave), 'r', encoding='utf-8') as source:
            try:
                with patch.object(termios, 'tcsetattr', side_effect=fail_second):
                    with self.assertRaisesRegex(RuntimeError, 'primary failure') as raised:
                        with terminal_session(source, BrokenOutput()): raise RuntimeError('primary failure')
                self.assertEqual(len(raised.exception.__notes__), 1)
                self.assertIn('terminal attributes, display modes', raised.exception.__notes__[0])
            finally:
                native_set(self.slave, termios.TCSANOW, self.before_attrs)
        self.assertEqual(termios.tcgetattr(self.slave), self.before_attrs)

    def test_terminal_guard_restores_on_unexpected_exception(self):
        import termios
        with os.fdopen(os.dup(self.slave), 'r', encoding='utf-8') as source, os.fdopen(os.dup(self.slave), 'w', encoding='utf-8') as sink:
            with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
                with terminal_session(source, sink): raise RuntimeError('synthetic failure')
        self.assertEqual(termios.tcgetattr(self.slave), self.before_attrs)


if __name__ == '__main__': unittest.main()
