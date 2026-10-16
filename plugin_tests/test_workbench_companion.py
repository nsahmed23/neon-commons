"""The companion's entry in the workbench (requirement 17 UX-VIS, second slice, item 3).

`workbench companion --root STORE --object ID (--out FILE | --serve)` prints the file path or the loopback address
and never launches a browser; the terminal has the same route (`companion FILE`, `companion serve`, `companion stop`)
and the actions menu offers it, last, with a notice that it is read-only. The page is the one the companion modules
draw from the engine's own relationships result. Real subprocesses for the command line; scripted input for the
terminal. Test HTTP requests set User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0. Loopback and temporary
directories only.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
import unittest.mock

from plugin_tests.test_graph_projection import synthetic_policy

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'
UA = 'OpenAI File Downloader, XaiImageApiFetch/1.0'


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store, cls.value, cls.truth, cls.policy = synthetic_policy(cls.temp.name)
        cls.root = str(Path(cls.temp.name) / 'store')
        cls.object_id = cls.policy['id']

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.out = tempfile.TemporaryDirectory()
        self.addCleanup(self.out.cleanup)

    def process(self, *args, **kw):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run([sys.executable, '-B', str(CLI), 'workbench', *map(str, args)], text=True, capture_output=True,
                              cwd='/tmp', timeout=60, env=env, **kw)


class ParserTests(Fixture):
    def parse(self, *args):
        from intune_iac.cli import parser
        return parser().parse_args(['workbench', 'companion', *map(str, args)])

    def test_one_way_to_open_is_required_and_the_forms_parse(self):
        out = Path(self.out.name) / 'x.html'
        args = self.parse('--root', self.root, '--object', self.object_id, '--out', out)
        self.assertEqual((args.workbench_command, args.out, args.serve), ('companion', str(out), False))
        args = self.parse('--root', self.root, '--object', self.object_id, '--serve')
        self.assertEqual((args.out, args.serve, args.idle_seconds), (None, True, 1800))
        for bad in (('--root', self.root, '--object', self.object_id),
                    ('--root', self.root, '--object', self.object_id, '--out', out, '--serve'),
                    ('--root', self.root, '--out', out), ('--object', self.object_id, '--out', out)):
            with self.assertRaises(SystemExit, msg=bad), unittest.mock.patch('sys.stderr'):
                self.parse(*bad)

    def test_there_is_no_host_port_or_token_option(self):
        from intune_iac.cli import parser
        text = ''
        with unittest.mock.patch('sys.stdout') as stdout:
            try:
                parser().parse_args(['workbench', 'companion', '--help'])
            except SystemExit:
                pass
            text = ''.join(call.args[0] for call in stdout.write.call_args_list)
        for word in ('--host', '--port', '--token', '--bind', '--browser', '--open'):
            self.assertNotIn(word, text)
        self.assertIn('--out', text)
        self.assertIn('--serve', text)


class StaticTests(Fixture):
    def test_the_file_route_writes_the_page_and_names_the_path_without_a_browser(self):
        path = Path(self.out.name) / 'companion.html'
        result = self.process('companion', '--root', self.root, '--object', self.object_id, '--out', path)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        value = json.loads(result.stdout)
        self.assertEqual((value['mode'], value['path']), ('file', str(path.resolve())))
        self.assertIn('No browser was opened', value['notice'])
        text = path.read_text(encoding='utf-8')
        self.assertIn('STATIC FILE', text)
        self.assertIn('SYNTHETIC', text)
        self.assertIn(self.object_id, text)
        self.assertIn(value['revision'], text)
        for edge in self.value['relationships']:
            self.assertIn(edge['target_id'], text)
        self.assertIn('[_] none recorded', text)

    def test_an_unknown_object_is_an_error_and_writes_nothing(self):
        path = Path(self.out.name) / 'none.html'
        result = self.process('companion', '--root', self.root, '--object', 'no-such-object', '--out', path)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(path.exists())

    def test_the_page_is_the_one_the_engines_relationships_result_draws(self):
        from intune_iac.companion import build_page
        from intune_iac.workbench import _companion_read, _store
        read = _companion_read(_store(self.root), self.object_id)
        page, graph = build_page(read)
        self.assertEqual({edge['type'] for edge in graph['edges']},
                         {'assignment', 'exclusion', 'filter', 'scope_tag', 'setting'})
        self.assertEqual(graph['counts']['relationships'], len(read()['value']['relationships']))
        self.assertEqual(read()["mode_class"], "synthetic")
        self.assertEqual(read()['tenant'], self.truth['tenant_id'])


class ServeTests(Fixture):
    def test_the_serve_route_prints_the_address_first_serves_it_and_ends_on_interrupt(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        process = subprocess.Popen([sys.executable, '-B', str(CLI), 'workbench', 'companion', '--root', self.root, '--object',
                                    self.object_id, '--serve'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   cwd='/tmp', env=env)
        self.addCleanup(process.kill)
        timer = threading.Timer(30, process.kill)
        timer.start()
        try:
            first = process.stdout.readline()
            found = re.search(r'http://127\.0\.0\.1:(\d+)(/[A-Za-z0-9_-]+/)', first)
            self.assertIsNotNone(found, first)
            self.assertIn('secret', first)
            self.assertIn('No browser was opened', first)
            port, base = int(found.group(1)), found.group(2)
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
            connection.request('GET', base + 'snapshot', headers={'User-Agent': UA})
            snapshot = json.loads(connection.getresponse().read())
            connection.close()
            self.assertEqual((snapshot['status'], snapshot['mode']), ('ok', 'SYNTHETIC'))
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
            connection.request('GET', base, headers={'User-Agent': UA})
            reply = connection.getresponse()
            page = reply.read().decode('utf-8')
            connection.close()
            self.assertEqual(reply.status, 200)
            self.assertIn(snapshot['revision'], page)
            self.assertIn('data-live="1"', page)
            process.send_signal(signal.SIGINT)
            rest, error = process.communicate(timeout=20)
        finally:
            timer.cancel()
        self.assertEqual(process.returncode, 0, error)
        self.assertEqual(json.loads(rest.strip().splitlines()[-1]), {'mode': 'live', 'stopped': 'interrupted'})
        self.assertNotIn(base, rest, 'the result never repeats the address')


class TerminalTests(Fixture):
    def run_terminal(self, *lines):
        from intune_iac.workbench import _run_terminal
        results, feed = [], iter(lines)
        _run_terminal(self.root, input_fn=lambda prompt: next(feed), result_fn=results.append)
        return results

    def test_the_terminal_writes_the_page_for_the_selected_policy(self):
        path = Path(self.out.name) / 'terminal.html'
        results = self.run_terminal('select ' + self.object_id, 'companion %s' % path, 'quit')
        written = next(item for item in results if isinstance(item, dict) and item.get('mode') == 'file')
        self.assertEqual(written['path'], str(path.resolve()))
        self.assertIn(self.object_id, path.read_text(encoding='utf-8'))
        self.assertIn('No browser was opened', written['notice'])

    def test_the_terminal_needs_a_selected_policy_and_exact_arguments(self):
        path = Path(self.out.name) / 'x.html'
        results = self.run_terminal('companion %s' % path, 'select ' + self.object_id, 'companion', 'companion a b', 'quit')
        codes = [item['error']['code'] for item in results if isinstance(item, dict) and item.get('status') == 'error']
        self.assertEqual(codes[0], 'selection_required')
        self.assertEqual(codes[1:], ['invalid_workbench_request', 'invalid_workbench_request'])
        self.assertFalse(path.exists())

    def test_the_terminal_serves_on_loopback_and_stops_it_and_stops_it_again_on_exit(self):
        results = self.run_terminal('select ' + self.object_id, 'companion serve', 'companion serve', 'companion stop', 'quit')
        live = next(item for item in results if isinstance(item, dict) and item.get('mode') == 'live' and 'address' in item)
        self.assertRegex(live['address'], r'^http://127\.0\.0\.1:\d+/[A-Za-z0-9_-]+/$')
        self.assertIn('secret', live['notice'])
        errors = [item['error']['code'] for item in results if isinstance(item, dict) and item.get('status') == 'error']
        self.assertEqual(errors, ['companion_running'])
        stopped = [item for item in results if isinstance(item, dict) and item.get('stopped')]
        self.assertEqual([item['stopped'] for item in stopped], ['stopped'])
        port = int(re.search(r':(\d+)/', live['address']).group(1))
        import socket
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', port), timeout=2)

    def test_leaving_the_terminal_stops_a_listener_it_started(self):
        results = self.run_terminal('select ' + self.object_id, 'companion serve', 'quit')
        live = next(item for item in results if isinstance(item, dict) and 'address' in item)
        port = int(re.search(r':(\d+)/', live['address']).group(1))
        import socket
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', port), timeout=2)

    def test_the_help_lists_the_route(self):
        from intune_iac.workbench import HELP
        self.assertTrue(any(line.startswith('companion ') for line in HELP['navigation']))
        self.assertTrue(any('never opens a browser' in line for line in HELP['navigation'] if line.startswith('companion ')))


class SessionEndTests(Fixture):
    def test_a_listener_started_in_the_terminal_stops_even_when_the_session_dies_of_an_error(self):
        import socket
        from intune_iac.workbench import _run_terminal
        results = []

        class Boom(RuntimeError):
            pass

        script = ['select ' + self.object_id, 'companion serve']

        def feed(prompt):
            if script:
                return script.pop(0)
            raise Boom('the input failed')

        with self.assertRaises(Boom):
            _run_terminal(self.root, input_fn=feed, result_fn=results.append)
        live = next(item for item in results if isinstance(item, dict) and 'address' in item)
        port = int(re.search(r':(\d+)/', live['address']).group(1))
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', port), timeout=2)

    def test_the_same_when_the_result_callback_raises(self):
        import socket
        from intune_iac.workbench import _run_terminal
        seen = []

        def present(value):
            seen.append(value)
            if isinstance(value, dict) and 'address' in value:
                raise RuntimeError('the presentation failed')

        feed = iter(['select ' + self.object_id, 'companion serve', 'quit'])
        with self.assertRaises(RuntimeError):
            _run_terminal(self.root, input_fn=lambda prompt: next(feed), result_fn=present)
        live = next(item for item in seen if isinstance(item, dict) and 'address' in item)
        port = int(re.search(r':(\d+)/', live['address']).group(1))
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', port), timeout=2)


class FailingStopTests(Fixture):
    """The session's cleanup when a listener will not close: the engineer sees the error, the listener stays held so
    `companion stop` can be retried, and an error already escaping the session is not replaced by the cleanup's."""

    def setUp(self):
        super().setUp()
        from intune_iac import companion
        self.listeners, self.repairs = [], []
        real_start = companion.start_live

        def capturing(*arguments, **keywords):
            live = real_start(*arguments, **keywords)
            self.listeners.append(live)
            self.addCleanup(live.stop)       # runs after the repairs below (cleanups run last in, first out)
            return live
        patch = unittest.mock.patch.object(companion, 'start_live', capturing)
        patch.start()
        self.addCleanup(patch.stop)

    def break_close(self):
        from plugin_tests.test_companion_live import UnclosableSocket
        live = self.listeners[0]
        real_socket = live.server.socket
        patch = unittest.mock.patch.object(live.server, 'server_close', side_effect=OSError('close failed'))
        patch.start()
        live.server.socket = UnclosableSocket(real_socket)

        def repair():
            patch.stop()
            live.server.socket = real_socket
        self.addCleanup(repair)
        self.repair = repair

    def run_terminal(self, *steps):
        """Lines are typed; callables run between prompts (to break or repair the listener)."""
        from intune_iac.workbench import _run_terminal
        results, remaining = [], list(steps)

        def feed(prompt):
            while True:
                step = remaining.pop(0)
                if callable(step):
                    step()
                else:
                    return step
        _run_terminal(self.root, input_fn=feed, result_fn=results.append)
        return results

    def test_a_failing_companion_stop_keeps_the_listener_held_and_a_retry_succeeds(self):
        import socket
        select = 'select ' + self.object_id
        results = self.run_terminal(select, 'companion serve', self.break_close, 'companion stop', 'companion serve',
                                    lambda: self.repair(), 'companion stop', 'quit')
        outcomes = [item['error']['code'] if item.get('status') == 'error' else item.get('stopped')
                    for item in results if isinstance(item, dict) and (item.get('status') == 'error' or item.get('stopped'))]
        self.assertEqual(outcomes, ['companion_live_close_failed', 'companion_running', 'stopped'])
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', self.listeners[0].port), timeout=2)

    def fail_in_the_background(self):
        """The listener's own stop failed in a background thread (its drain of writers timed out) and was not seen."""
        from intune_iac.io import AppError
        live = self.listeners[0]
        patch = unittest.mock.patch.object(live, '_drain_writers',
                                           side_effect=[AppError('companion_live_writer_timeout', 'held'), None])
        patch.start()
        self.addCleanup(patch.stop)
        live.end('idle', wait=False)
        for _ in range(100):
            if live._state == 'close_failed':
                break
            threading.Event().wait(0.05)
        self.assertEqual(live._state, 'close_failed')

    def test_a_listener_confirmed_closed_leaves_held_while_the_saved_failure_is_still_shown(self):
        results = self.run_terminal('select ' + self.object_id, 'companion serve', self.fail_in_the_background,
                                    'companion stop', 'companion serve', 'quit')
        shown = [item['error']['code'] if item.get('status') == 'error' else
                 ('serving' if 'address' in item else item.get('stopped'))
                 for item in results if isinstance(item, dict) and (item.get('status') == 'error' or 'address' in item
                                                                    or item.get('stopped'))]
        self.assertEqual(shown, ['serving', 'companion_live_close_failed', 'serving'])
        self.assertTrue(self.listeners[0].is_closed)

    def test_an_error_escaping_the_session_is_not_replaced_by_a_failing_stop(self):
        from intune_iac.workbench import _run_terminal

        class Boom(RuntimeError):
            pass
        script = ['select ' + self.object_id, 'companion serve', self.break_close]

        def feed(prompt):
            while script:
                step = script.pop(0)
                if callable(step):
                    step()
                else:
                    return step
            raise Boom('the input failed')
        with self.assertRaises(Boom) as caught:
            _run_terminal(self.root, input_fn=feed, result_fn=lambda value: None)
        notes = ' '.join(getattr(caught.exception, '__notes__', []))
        self.assertIn('companion_live_close_failed', notes)
        self.assertNotIn('127.0.0.1', notes)
        self.assertNotIn(self.listeners[0].token, notes)

    def test_with_nothing_escaping_a_failing_stop_at_the_end_is_raised(self):
        from intune_iac.io import AppError
        def end_of_input():
            raise EOFError
        with self.assertRaises(AppError) as caught:
            self.run_terminal('select ' + self.object_id, 'companion serve', self.break_close, end_of_input)
        self.assertEqual(caught.exception.code, 'companion_live_close_failed')


class ActionsMenuTests(Fixture):
    def actions(self):
        from intune_iac.workbench import _inspection, _store
        return _inspection(_store(self.root), self.object_id, attention=True)['actions']

    def test_the_menu_offers_the_companion_last_with_its_notice(self):
        actions = self.actions()
        offered = actions[-1]
        self.assertEqual(offered['kind'], 'companion')
        self.assertTrue(offered['available'])
        self.assertIsNone(offered['blocked'])
        self.assertEqual((offered['command'], offered['cursor']), ('companion ', len('companion ')))
        self.assertTrue(offered['needs'])
        self.assertIn('FILE', offered['needs'][0])
        self.assertIn('read-only', offered['summary'].lower())
        # One effect description (PKG-PRES-RUN10 item 12): the summary says what it writes and that it opens no browser.
        self.assertIn('browser', offered['summary'])
        self.assertIn('file you name', offered['summary'])
        self.assertIn('secret address', offered['effects'])
        self.assertEqual(offered['binding']['object_id'], self.object_id)
        self.assertEqual(sum(action['kind'] == 'companion' for action in actions), 1)

    def test_every_other_action_keeps_its_place(self):
        kinds = [action['kind'] for action in self.actions()]
        self.assertEqual(kinds[:-1], [kind for kind in kinds if kind != 'companion'])


if __name__ == '__main__':
    unittest.main()
