"""The companion's two ways to open (requirement 17 UX-VIS, second slice, item 2: snapshot and state).

A static file is written to the path the engineer gives and says it does not update itself. Live mode is a
loopback-only listener (127.0.0.1, an ephemeral port, a random path token, GET only) that serves the page and the
current snapshot revision, stops when the command ends or after an idle limit, and has no write, execution, approval
or navigation endpoint. The page polls the snapshot; its rule, which the tests here apply the same way, is: the
snapshot's revision or evidence mode differs from the page's -> STALE (never redrawn silently); the listener does not
answer twice running -> DISCONNECTED (the last snapshot stays with its revision and time). Every test request sets
the header User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0. Loopback only, temporary directories only.
"""
import http.client
import json
import os
from pathlib import Path
import re
import socket
import tempfile
import threading
import unittest
from unittest import mock

from plugin_tests.test_graph_projection import synthetic_policy

UA = 'OpenAI File Downloader, XaiImageApiFetch/1.0'


class Clock:
    """An injected monotonic clock: nothing here waits on the host clock."""
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class UnclosableSocket:
    """Stands in for a listening socket whose close fails: everything is the real socket's, but close() raises and the
    descriptor stays open (fileno() is never -1)."""
    def __init__(self, real, error=PermissionError):
        self._real = real
        self._error = error

    def close(self):
        raise self._error('raw close failed')

    def shutdown(self, how):
        raise OSError('raw shutdown failed')

    def __getattr__(self, name):
        return getattr(self._real, name)


class InterruptibleSocket:
    """A listening socket whose shutdown() and/or close() raise `error` (an interrupt); the rest is the real socket's.
    close_works=True makes close() really close it, so the port refuses afterwards."""
    def __init__(self, real, error=KeyboardInterrupt, on_shutdown=False, on_close=False):
        self._real, self._error, self._on_shutdown, self._on_close = real, error, on_shutdown, on_close

    def shutdown(self, how):
        if self._on_shutdown:
            raise self._error('interrupted in shutdown')
        if self._on_close:
            raise OSError('no wake-up here, so the port stays bound until close()')
        return self._real.shutdown(how)

    def close(self):
        if self._on_close:
            raise self._error('interrupted in close')
        return self._real.close()

    def __getattr__(self, name):
        return getattr(self._real, name)


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store, cls.value, cls.truth, cls.policy = synthetic_policy(cls.temp.name)
        cls.object_id = cls.policy['id']

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.world = {'value': self.value, 'states': {}, 'mode_class': 'synthetic_local_process_only', 'gone': False}
        self.out = tempfile.TemporaryDirectory()
        self.addCleanup(self.out.cleanup)
        self.clock = Clock()
        patch = mock.patch('intune_iac.companion_live.monotonic', self.clock)
        patch.start()
        self.addCleanup(patch.stop)
        self.live = None

    def read(self):
        from intune_iac.io import AppError
        if self.world['gone']:
            raise AppError('object_not_found', 'No such policy.')
        return {'value': self.world['value'], 'mode_class': self.world['mode_class'], 'tenant': self.truth['tenant_id'],
                'states': self.world['states'], 'freshness': 'fresh'}

    def start(self, **kw):
        from intune_iac.companion import start_live
        self.live = start_live(self.read, **kw)
        self.addCleanup(self.live.stop)
        return self.live

    def request(self, path, method='GET', headers=None, live=None, token=True):
        live = live or self.live
        connection = http.client.HTTPConnection('127.0.0.1', live.port, timeout=5)
        sent = {'User-Agent': UA}
        sent.update(headers or {})
        try:
            connection.request(method, (live.base if token else '') + path, headers=sent)
            reply = connection.getresponse()
            return reply.status, {key.lower(): value for key, value in reply.getheaders()}, reply.read()
        finally:
            connection.close()

    def raw(self, path, method='GET', headers=None, live=None):
        live = live or self.live
        connection = http.client.HTTPConnection('127.0.0.1', live.port, timeout=5)
        try:
            connection.request(method, path, headers=dict({'User-Agent': UA}, **(headers or {})))
            reply = connection.getresponse()
            return reply.status, {key.lower(): value for key, value in reply.getheaders()}, reply.read()
        finally:
            connection.close()

    def snapshot(self):
        status, _, body = self.request('snapshot')
        self.assertEqual(status, 200)
        return json.loads(body)

    def page(self):
        status, _, body = self.request('')
        self.assertEqual(status, 200)
        return body.decode('utf-8')


def judge(page, snapshot, failures):
    """The page's own rule (its script), applied to what the page holds, what the listener last said and how many
    polls in a row got no answer. Returns 'current', 'stale' or 'disconnected'."""
    held = re.search(r'data-revision="([0-9a-f]+)" data-mode="([^"]*)"', page)
    if failures >= 2:
        return 'disconnected'
    if snapshot is None:
        return 'current'
    return 'current' if (snapshot['revision'], snapshot['mode']) == (held.group(1), held.group(2)) else 'stale'


class StaticFileTests(Fixture):
    def run_static(self, name='companion.html', **kw):
        from intune_iac.companion import run_companion
        path = Path(self.out.name) / name
        return path, run_companion(self.read, out=str(path), **kw)

    def test_the_file_is_written_to_the_path_given_and_says_it_does_not_update_itself(self):
        path, result = self.run_static()
        self.assertTrue(path.is_file())
        text = path.read_bytes().decode('utf-8')
        self.assertIn('STATIC FILE: this page does not update itself', text)
        self.assertNotIn('data-live="1"', text)
        self.assertNotIn(b'\r', path.read_bytes())
        self.assertEqual(result['mode'], 'file')
        self.assertEqual(result['path'], str(path.resolve()))
        self.assertEqual(result['bytes'], len(path.read_bytes()))
        self.assertIn('does not update itself', result['notice'])
        self.assertIn(str(path.resolve()), result['notice'])
        self.assertIn('no browser was opened', result['notice'].lower())

    def test_the_file_carries_the_projections_revision_and_the_evidence_mode(self):
        from intune_iac.graph_projection import project
        path, result = self.run_static()
        text = path.read_text(encoding='utf-8')
        graph = project(self.value, freshness='fresh')
        self.assertEqual(result['revision'], graph['revision'])
        self.assertIn(graph['revision'], text)
        self.assertIn('SYNTHETIC', text)
        self.assertIn(self.value.get('observed_at') or 'observation time unknown', text)

    def test_a_file_replaces_the_previous_one_whole_and_leaves_no_temporary_file(self):
        path, _ = self.run_static()
        first = path.read_bytes()
        self.world['states'] = {self.object_id: 'blocked'}
        self.run_static()
        self.assertNotEqual(path.read_bytes(), first)
        self.assertEqual([item.name for item in Path(self.out.name).iterdir()], ['companion.html'])

    def test_a_path_that_would_not_be_written_safely_is_refused_and_nothing_is_written(self):
        from intune_iac.companion import run_companion
        from intune_iac.io import AppError
        folder = Path(self.out.name)
        (folder / 'dir').mkdir()
        target = folder / 'real.html'
        target.write_text('keep', encoding='utf-8')
        (folder / 'link.html').symlink_to(target)
        for bad, code in (('dir', 'companion_out_invalid'), ('missing/x.html', 'companion_out_invalid'),
                          ('link.html', 'companion_out_invalid'), ('', 'companion_out_invalid')):
            with self.assertRaises(AppError, msg=bad) as caught:
                run_companion(self.read, out=str(folder / bad) if bad else '')
            self.assertEqual(caught.exception.code, code, bad)
        self.assertEqual(target.read_text(encoding='utf-8'), 'keep')
        self.assertFalse((folder / 'missing').exists())

    def test_exactly_one_way_to_open_is_required(self):
        from intune_iac.companion import run_companion
        from intune_iac.io import AppError
        for kw in ({}, {'out': str(Path(self.out.name) / 'a.html'), 'serve': True}):
            with self.assertRaises(AppError) as caught:
                run_companion(self.read, **kw)
            self.assertEqual(caught.exception.code, 'companion_target_required')

    def test_a_read_that_cannot_name_an_object_writes_nothing(self):
        from intune_iac.companion import run_companion
        from intune_iac.io import AppError
        self.world['gone'] = True
        path = Path(self.out.name) / 'x.html'
        with self.assertRaises(AppError):
            run_companion(self.read, out=str(path))
        self.assertFalse(path.exists())

    def test_no_module_of_the_companion_launches_a_browser_or_reaches_out(self):
        for name in ('companion.py', 'companion_live.py', 'companion_page.py'):
            source = (Path(__file__).resolve().parent.parent / 'intune_iac' / name).read_text(encoding='utf-8')
            for word in ('webbrowser', 'subprocess', 'os.system', 'urllib.request', 'requests', 'startfile', 'xdg-open'):
                self.assertNotIn(word, source, name + ' ' + word)


class ListenerTests(Fixture):
    def test_it_binds_only_to_loopback_on_an_ephemeral_port_with_a_random_token(self):
        live = self.start()
        self.assertEqual(live.host, '127.0.0.1')
        self.assertGreater(live.port, 0)
        self.assertEqual(live.server.socket.getsockname()[0], '127.0.0.1')
        self.assertRegex(live.address, r'^http://127\.0\.0\.1:%d/[A-Za-z0-9_-]{20,}/$' % live.port)
        from intune_iac.companion import start_live
        other = start_live(self.read)
        self.addCleanup(other.stop)
        self.assertNotEqual(other.token, live.token)
        self.assertNotEqual(other.port, live.port)
        # A caller cannot ask for another interface: there is no host argument.
        import inspect
        self.assertNotIn('host', inspect.signature(start_live).parameters)

    def test_it_serves_the_page_and_the_snapshot_and_they_agree_on_the_revision(self):
        self.start()
        page, snapshot = self.page(), self.snapshot()
        held = re.search(r'data-revision="([0-9a-f]+)" data-mode="([^"]*)" data-observed="([^"]*)"', page)
        self.assertEqual((held.group(1), held.group(2)), (snapshot['revision'], snapshot['mode']))
        self.assertEqual(snapshot['mode'], 'SYNTHETIC')
        self.assertEqual(snapshot['status'], 'ok')
        self.assertEqual(set(snapshot), {'schema_version', 'status', 'revision', 'mode', 'observed_at'})
        self.assertIn('data-live="1"', page)
        self.assertIn('data-snapshot="snapshot"', page)
        self.assertIn("connect-src 'self'", page)
        self.assertIn('LIVE: checking', page)
        self.assertNotIn('STATIC FILE', page)

    def test_the_response_headers_close_every_door_but_a_get_of_the_page_and_the_snapshot(self):
        self.start()
        for path, kind in (('', 'text/html; charset=utf-8'), ('snapshot', 'application/json')):
            status, headers, _ = self.request(path)
            self.assertEqual(status, 200)
            self.assertEqual(headers['content-type'], kind)
            self.assertEqual(headers['cache-control'], 'no-store')
            self.assertEqual(headers['x-content-type-options'], 'nosniff')
            self.assertEqual(headers['referrer-policy'], 'no-referrer')
            self.assertEqual(headers['cross-origin-resource-policy'], 'same-origin')
            self.assertNotIn('access-control-allow-origin', headers)
            self.assertNotIn('python', headers.get('server', '').lower())
        _, headers, _ = self.request('')
        self.assertIn("default-src 'none'", headers['content-security-policy'])
        self.assertIn("frame-ancestors 'none'", headers['content-security-policy'])
        self.assertIn("connect-src 'self'", headers['content-security-policy'])

    def test_a_wrong_token_is_refused_and_learns_nothing(self):
        live = self.start()
        for token in ('x' * len(live.token), live.token[:-1], live.token + 'x', '', 'AAAA'):
            for suffix in ('', 'snapshot'):
                status, _, body = self.raw('/%s/%s' % (token, suffix) if token else '/' + suffix)
                self.assertEqual(status, 404, (token, suffix))
                self.assertNotIn(live.token.encode(), body)
                self.assertNotIn(b'revision', body)
        _, _, unknown = self.raw('/nothing/here')
        _, _, wrong = self.raw('/%s/' % ('y' * len(live.token)))
        self.assertEqual(unknown, wrong, 'a wrong token and an unknown path look the same')

    def test_any_method_other_than_get_is_refused_and_changes_nothing(self):
        live = self.start()
        before = self.snapshot()
        for method in ('POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS', 'TRACE', 'CONNECT', 'FOO', 'get'):
            for path in ('', 'snapshot', 'approve'):
                status, headers, body = self.request(path, method=method)
                self.assertEqual(status, 405, (method, path))
                self.assertEqual(headers.get('allow'), 'GET')
                self.assertNotIn(b'revision', body)
            status, _, _ = self.raw('/wrong/', method=method)
            self.assertEqual(status, 405, method)
        status, _, _ = self.request('', method='POST', headers={'Content-Length': '4'})
        self.assertEqual(status, 405)
        self.assertEqual(self.snapshot(), before)

    def test_there_is_no_endpoint_beyond_the_page_and_the_snapshot(self):
        live = self.start()
        for path in ('', 'snapshot'):
            self.assertEqual(self.request(path)[0], 200)
        for path in ('snapshot/', 'navigate', 'select', 'approve', 'execute', 'run', 'events', 'index.html', 'favicon.ico',
                     '../', '%2e%2e/', 'snapshot?x=1', '?x=1', 'snapshot%00', 'snapshot/..'):
            self.assertEqual(self.request(path)[0], 404, path)
        for path in ('/', '/favicon.ico', '/' + live.token, '/robots.txt', '/%s//' % live.token):
            self.assertEqual(self.raw(path)[0], 404, path)

    def test_a_request_for_another_host_name_is_refused_so_a_rebound_name_reads_nothing(self):
        live = self.start()
        for host in ('evil.example', 'evil.example:%d' % live.port, '127.0.0.1:1', '[::1]:%d' % live.port, '10.0.0.5:%d' % live.port):
            status, _, body = self.request('', headers={'Host': host})
            self.assertEqual(status, 421, host)
            self.assertNotIn(b'revision', body)
        for host in ('127.0.0.1:%d' % live.port, 'localhost:%d' % live.port):
            self.assertEqual(self.request('', headers={'Host': host})[0], 200, host)

    def test_a_read_that_fails_says_so_without_the_reason(self):
        self.start()

        def broken():
            raise RuntimeError('secret detail /home/someone/path')
        self.live.snapshot_source = broken
        self.live.page_source = broken
        for path in ('', 'snapshot'):
            status, _, body = self.request(path)
            self.assertEqual(status, 500)
            self.assertNotIn(b'secret', body)
            self.assertNotIn(b'someone', body)

    def test_a_slow_connection_does_not_hold_up_the_others(self):
        live = self.start()
        stuck = socket.create_connection(('127.0.0.1', live.port), timeout=5)
        try:
            stuck.sendall(b'GET /')
            self.assertEqual(self.request('snapshot')[0], 200)
        finally:
            stuck.close()

    def test_every_test_request_sets_the_required_user_agent(self):
        seen = []
        from intune_iac import companion_live
        original = companion_live.Handler.do_GET
        def spy(handler):
            seen.append(handler.headers.get('User-Agent'))
            return original(handler)
        with mock.patch.object(companion_live.Handler, 'do_GET', spy):
            self.start()
            self.page()
            self.snapshot()
        self.assertEqual(seen, [UA, UA])


class FixRoundTests(Fixture):
    """Sol's review of a1bafb6, items 1, 2, 5, 6 and 7."""

    def refused(self, port, seconds=3.0):
        """Whether connecting to the port is refused within `seconds` (real time; the listener's own clock is injected)."""
        import time
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                socket.create_connection(('127.0.0.1', port), timeout=1).close()
            except OSError:
                return True
            time.sleep(0.02)
        return False

    def test_the_idle_limit_is_enforced_with_no_lifecycle_call_at_all(self):
        live = self.start(idle_seconds=1)
        self.assertEqual(self.request('snapshot')[0], 200)
        self.clock.now += 2
        # Nobody calls wait() or wait_step(): a frame that only keeps the returned object is the caller this is for.
        self.assertTrue(self.refused(live.port), 'the listener must stop by itself')
        self.assertEqual(live.ended, 'idle')
        self.assertEqual(live.wait(poll=0.01), 'idle')

    def test_a_request_that_arrives_late_cannot_revive_an_expired_listener(self):
        from intune_iac import companion_live
        with mock.patch.object(companion_live, 'WATCH_SECONDS', 3600):
            live = self.start(idle_seconds=1)
            self.clock.now += 5
            try:
                status, _, body = self.request('')
            except OSError:
                status, body = None, b''
            self.assertNotEqual(status, 200)
            self.assertNotIn(b'<svg', body)
            self.assertTrue(self.refused(live.port), 'and it goes away, it does not carry on')
            self.assertEqual(live.ended, 'idle')

    def test_the_watchdog_is_joined_when_the_listener_stops(self):
        live = self.start()
        watchdog = live._watchdog
        self.assertTrue(watchdog.is_alive())
        live.stop()
        self.assertFalse(watchdog.is_alive())
        self.assertEqual(live.ended, 'stopped')

    def test_there_is_no_public_token_parameter_anywhere(self):
        import inspect
        from intune_iac.companion import run_companion, start_live
        from intune_iac.companion_live import LiveCompanion
        for function in (start_live, run_companion, LiveCompanion.__init__):
            self.assertNotIn('token', inspect.signature(function).parameters, function)

    def test_the_default_token_is_24_random_bytes_and_a_test_may_inject_through_the_private_factory_only(self):
        import base64
        from intune_iac import companion_live
        live = self.start()
        raw = base64.urlsafe_b64decode(live.token + '=' * (-len(live.token) % 4))
        self.assertEqual(len(raw), companion_live.TOKEN_BYTES)
        with mock.patch.object(companion_live, '_new_token', lambda: 'F' * 32):
            fixed = self.start()
        self.assertEqual(fixed.token, 'F' * 32)
        self.assertEqual(self.request('snapshot', live=fixed)[0], 200)
        # A factory that hands back something weak is refused, not served.
        from intune_iac.companion import start_live
        from intune_iac.io import AppError
        for weak in ('x', '', 'a/b' + 'c' * 30, '\u00e9' * 30, None, 7):
            with mock.patch.object(companion_live, '_new_token', lambda weak=weak: weak):
                with self.assertRaises(AppError, msg=repr(weak)):
                    start_live(self.read)

    def test_the_notice_and_the_page_call_the_address_a_secret_and_say_who_is_not_isolated(self):
        live = self.start()
        for text in (live.notice, self.page()):
            lowered = text.lower()
            self.assertIn('secret', lowered)
            self.assertIn('not isolated', lowered)
        self.assertIn('same machine', live.notice.lower())

    def test_every_response_carries_a_restrictive_policy_with_frame_ancestors(self):
        live = self.start()
        cases = [self.request(''), self.request('snapshot'), self.request('nothing'), self.request('', method='POST'),
                 self.request('', headers={'Host': 'evil.example'}), self.raw('/wrong/')]
        def broken(*args):
            raise RuntimeError('x')
        live.snapshot_source = broken
        cases.append(self.request('snapshot'))
        self.world['gone'] = True
        live.page_source = lambda settings: self.read()
        cases.append(self.request(''))
        self.assertEqual({status for status, _, _ in cases}, {200, 404, 405, 421, 500, 503})
        for status, headers, _ in cases:
            policy = headers.get('content-security-policy', '')
            self.assertIn("default-src 'none'", policy, status)
            self.assertIn("frame-ancestors 'none'", policy, status)
            self.assertIn("base-uri 'none'", policy, status)
            self.assertIn("form-action 'none'", policy, status)
            self.assertNotIn('unsafe', policy)

    def test_a_page_without_its_expected_policy_is_never_served(self):
        live = self.start()
        for html in ('<html><body>no policy</body></html>',
                     '<meta http-equiv="Content-Security-Policy" content="default-src *">',
                     '<meta http-equiv="Content-Security-Policy" content="script-src \'self\'">'):
            live.page_source = lambda settings, html=html: html
            status, headers, body = self.request('')
            self.assertEqual(status, 500, html)
            self.assertNotIn(b'<html', body)
            self.assertIn("frame-ancestors 'none'", headers['content-security-policy'])

    def test_concurrent_handlers_are_bounded_and_the_excess_fails_fast(self):
        from intune_iac import companion_live
        live = self.start()
        before = threading.active_count()
        stuck = []
        try:
            for _ in range(companion_live.MAX_HANDLERS * 5):
                connection = socket.create_connection(('127.0.0.1', live.port), timeout=5)
                connection.sendall(b'GET /')
                stuck.append(connection)
            threading.Event().wait(0.3)
            self.assertLessEqual(threading.active_count() - before, companion_live.MAX_HANDLERS + 1)
            # The excess is answered at once with a busy status, not left hanging.
            replies = 0
            for connection in stuck[companion_live.MAX_HANDLERS + 2:]:
                connection.settimeout(1)
                try:
                    if connection.recv(64).startswith(b'HTTP/1.0 503'):
                        replies += 1
                except OSError:
                    pass
            self.assertGreater(replies, 0)
        finally:
            for connection in stuck:
                connection.close()
        for _ in range(100):
            try:
                if self.request('snapshot')[0] == 200:
                    break
            except OSError:
                pass
            threading.Event().wait(0.05)
        else:
            self.fail('the listener serves again once the stuck clients are gone')

    def test_a_few_slow_clients_do_not_stop_a_normal_request(self):
        live = self.start()
        stuck = [socket.create_connection(('127.0.0.1', live.port), timeout=5) for _ in range(3)]
        try:
            for connection in stuck:
                connection.sendall(b'GET /')
            self.assertEqual(self.request('snapshot')[0], 200)
        finally:
            for connection in stuck:
                connection.close()


class FixRound2Tests(Fixture):
    """Sol's verification of d6900b4: the remaining parts of findings 6 and 8."""

    SECURITY = {'cache-control': 'no-store', 'x-content-type-options': 'nosniff', 'referrer-policy': 'no-referrer',
                'cross-origin-resource-policy': 'same-origin'}

    def check_headers(self, headers, where):
        for name, value in self.SECURITY.items():
            self.assertEqual(headers.get(name), value, (where, name))
        policy = headers.get('content-security-policy', '')
        self.assertIn("default-src 'none'", policy, where)
        self.assertIn("frame-ancestors 'none'", policy, where)

    def exchange(self, live, payload):
        """Send raw bytes and read the whole reply: status line, headers (lower-cased names) and body."""
        connection = socket.create_connection(('127.0.0.1', live.port), timeout=5)
        try:
            connection.sendall(payload)
            data = b''
            while True:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                data += chunk
        finally:
            connection.close()
        head, _, body = data.partition(b'\r\n\r\n')
        lines = head.decode('latin-1').split('\r\n')
        headers = {line.split(':', 1)[0].lower(): line.split(':', 1)[1].strip() for line in lines[1:] if ':' in line}
        return lines[0], headers, body

    def test_the_overload_reply_carries_the_same_security_headers(self):
        from intune_iac import companion_live
        live = self.start()
        stuck = [socket.create_connection(('127.0.0.1', live.port), timeout=5) for _ in range(companion_live.MAX_HANDLERS)]
        try:
            for connection in stuck:
                connection.sendall(b'GET /')
            threading.Event().wait(0.3)
            status, headers, body = self.exchange(live, b'GET / HTTP/1.0\r\n\r\n')
        finally:
            for connection in stuck:
                connection.close()
        self.assertTrue(status.startswith('HTTP/1.0 503'), status)
        self.check_headers(headers, 'overload')
        self.assertEqual(headers.get('content-length'), str(len(body)))
        self.assertNotIn(live.token.encode(), body)

    def test_a_request_the_parser_refuses_carries_the_same_headers_and_no_detail(self):
        live = self.start()
        cases = {'one word': b'BAD\r\n\r\n', 'bad version': b'GET / HTTP/9.9\r\n\r\n',
                 'not http': b'GET / FTP/1.0\r\n\r\n', 'five words': b'GET / HTTP/1.1 extra extra\r\n\r\n',
                 'long line': b'GET /' + b'a' * 70000 + b' HTTP/1.0\r\n\r\n',
                 'many headers': b'GET / HTTP/1.0\r\n' + b'X: y\r\n' * 150 + b'\r\n'}
        for name, payload in cases.items():
            status, headers, body = self.exchange(live, payload)
            self.assertRegex(status, r'^HTTP/1\.[01] [45]\d\d', (name, status))
            self.check_headers(headers, name)
            self.assertNotIn(b'<', body, name)
            self.assertNotIn(b'Python', body, name)
            self.assertNotIn(live.token.encode(), body, name)
        self.assertEqual(self.request('snapshot')[0], 200)

    def test_an_unavailable_snapshot_still_names_a_mode_as_text(self):
        self.start()
        self.world['gone'] = True
        snapshot = self.snapshot()
        self.assertEqual((snapshot['status'], snapshot['revision']), ('object_unavailable', None))
        self.assertIsInstance(snapshot['mode'], str)
        self.assertEqual(snapshot['mode'], 'MODE UNKNOWN')


class StaleAndDisconnectedTests(Fixture):
    def test_a_state_change_makes_the_held_page_stale_and_the_page_is_never_changed_under_the_reader(self):
        self.start()
        held = self.page()
        self.assertEqual(judge(held, self.snapshot(), 0), 'current')
        self.world['states'] = {self.object_id: 'blocked'}
        snapshot = self.snapshot()
        self.assertEqual(judge(held, snapshot, 0), 'stale')
        # Nothing was pushed to the page; a fresh request is the reader's own act and gets the new snapshot whole.
        newer = self.page()
        self.assertNotEqual(newer, held)
        self.assertEqual(judge(newer, snapshot, 0), 'current')
        drawn = lambda text: re.search(r'<svg\b.*?</svg>', text, re.S).group(0)
        self.assertIn('[!] blocked', drawn(newer))
        self.assertNotIn('[!] blocked', drawn(held))

    def test_filtering_and_deletion_change_the_revision_and_are_reported_stale(self):
        self.start()
        held = self.page()
        base = self.snapshot()['revision']
        revisions = {base}
        relations = self.value['relationships']
        group = next(edge['target_id'] for edge in relations if edge['relation'] == 'exclusion')
        for changed in ([edge for edge in relations if edge['relation'] != 'filter'],      # filtering: the filter is gone
                        [edge for edge in relations if edge['target_id'] != group],         # deletion: a group is gone
                        []):                                                                # everything deleted
            self.world['value'] = dict(self.value, relationships=changed)
            snapshot = self.snapshot()
            self.assertEqual(judge(held, snapshot, 0), 'stale')
            revisions.add(snapshot['revision'])
        self.assertEqual(len(revisions), 4)
        self.world['value'] = self.value
        self.assertEqual(judge(held, self.snapshot(), 0), 'current', 'back to what the page holds')

    def test_a_deleted_object_is_stale_with_no_revision_and_the_page_is_not_served(self):
        self.start()
        held = self.page()
        self.world['gone'] = True
        snapshot = self.snapshot()
        self.assertEqual((snapshot['status'], snapshot['revision']), ('object_unavailable', None))
        self.assertEqual(judge(held, snapshot, 0), 'stale')
        status, _, body = self.request('')
        self.assertEqual(status, 503)
        self.assertNotIn(b'<svg', body)

    def test_a_change_of_evidence_mode_alone_is_stale(self):
        self.start()
        held = self.page()
        self.world['mode_class'] = 'graph_capture_unverified'
        snapshot = self.snapshot()
        self.assertEqual(snapshot['mode'], 'CAPTURE')
        self.assertEqual(judge(held, snapshot, 0), 'stale')

    def test_a_listener_that_is_gone_is_disconnected_and_the_held_page_keeps_its_revision(self):
        live = self.start()
        held = self.page()
        revision = re.search(r'data-revision="([0-9a-f]+)"', held).group(1)
        live.stop()
        failures = 0
        for _ in range(2):
            with self.assertRaises(OSError):
                http.client.HTTPConnection('127.0.0.1', live.port, timeout=2).request('GET', live.base + 'snapshot', headers={'User-Agent': UA})
            failures += 1
        self.assertEqual(judge(held, None, 1), 'current', 'one missed poll is not yet a disconnect')
        self.assertEqual(judge(held, None, failures), 'disconnected')
        self.assertIn(revision, held)

    def test_the_script_reads_the_same_rule_the_tests_apply(self):
        self.start()
        script = re.search(r'<script>(.*)</script>', self.page(), re.S).group(1)
        self.assertIn('snapshot.revision === revision && snapshot.mode === mode', script)
        self.assertIn('failures >= 2', script)


class StopTests(Fixture):
    def test_stop_ends_the_listener_and_is_safe_to_repeat(self):
        live = self.start()
        self.assertEqual(self.request('snapshot')[0], 200)
        live.stop()
        live.stop()
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', live.port), timeout=2)
        self.assertEqual(live.wait(poll=0.01), 'stopped')

    def test_it_stops_after_the_idle_limit_without_a_page_request(self):
        live = self.start(idle_seconds=600)
        self.clock.now += 599
        results = []
        thread = threading.Thread(target=lambda: results.append(live.wait(poll=0.01)))
        thread.start()
        thread.join(0.3)
        self.assertTrue(thread.is_alive(), 'still inside the limit')
        self.assertEqual(self.request('snapshot')[0], 200)
        self.clock.now += 2
        thread.join(5)
        self.assertEqual(results, ['idle'])
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', live.port), timeout=2)

    def hold_first_stopper(self, live):
        """Make server.shutdown() block until released, so the thread that began stopping is held inside it: the interval
        in which the port has not yet been closed. Returns (entered, release)."""
        entered, release = threading.Event(), threading.Event()
        real = live.server.shutdown

        def held():
            entered.set()
            release.wait(10)
            real()
        patch = mock.patch.object(live.server, 'shutdown', held)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(release.set)
        return entered, release

    def port_accepts(self, live):
        try:
            socket.create_connection(('127.0.0.1', live.port), timeout=2).close()
        except OSError:
            return False
        return True

    def run_in_thread(self, call):
        outcome = []

        def target():
            try:
                outcome.append(('returned', call()))
            except Exception as error:
                outcome.append(('raised', error))
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        return thread, outcome

    def test_wait_does_not_report_the_end_while_the_watchdog_is_still_stopping_it(self):
        live = self.start(idle_seconds=600)
        entered, release = self.hold_first_stopper(live)
        self.clock.now += 601
        self.assertTrue(entered.wait(5), 'the watchdog began stopping the listener')
        self.assertTrue(self.port_accepts(live), 'precondition: the first stopper is held before the port is closed')
        self.assertIsNone(live.wait_step(), 'wait_step reported an end while the port still accepts')
        thread, outcome = self.run_in_thread(lambda: live.wait(poll=0.01))
        thread.join(0.3)
        self.assertTrue(thread.is_alive(), 'wait() returned while the port still accepts connections')
        release.set()
        thread.join(5)
        self.assertEqual(outcome, [('returned', 'idle')])
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', live.port), timeout=2)

    def test_a_second_stop_does_not_return_before_the_first_has_closed_the_port(self):
        live = self.start()
        entered, release = self.hold_first_stopper(live)
        first, first_outcome = self.run_in_thread(live.stop)
        self.assertTrue(entered.wait(5), 'the first stop() is inside shutdown()')
        second, second_outcome = self.run_in_thread(live.stop)
        second.join(0.3)
        self.assertTrue(second.is_alive(), 'the second stop() returned while the port still accepts connections')
        self.assertTrue(self.port_accepts(live))
        release.set()
        first.join(5)
        second.join(5)
        self.assertEqual([first_outcome, second_outcome], [[('returned', None)], [('returned', None)]])
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', live.port), timeout=2)

    def test_a_second_end_that_waits_does_not_return_before_the_first_has_closed_the_port(self):
        live = self.start()
        entered, release = self.hold_first_stopper(live)
        first, _ = self.run_in_thread(live.stop)
        self.assertTrue(entered.wait(5))
        second, second_outcome = self.run_in_thread(lambda: live.end('idle'))
        second.join(0.3)
        self.assertTrue(second.is_alive(), 'end(wait=True) returned while the port still accepts connections')
        release.set()
        first.join(5)
        second.join(5)
        self.assertEqual(second_outcome, [('returned', None)])
        self.assertEqual(live.ended, 'stopped', 'the reason recorded first, under the lock, wins')
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', live.port), timeout=2)

    def test_a_second_stop_that_is_not_released_in_time_raises_instead_of_reporting_an_end(self):
        from intune_iac import companion_live
        from intune_iac.io import AppError
        live = self.start()
        entered, release = self.hold_first_stopper(live)
        first, _ = self.run_in_thread(live.stop)
        self.assertTrue(entered.wait(5))
        # A shorter bound, only so the test does not wait the full production bound; the production bound is unchanged.
        with mock.patch.object(companion_live, 'STOP_WAIT_SECONDS', 0.2, create=True):
            with self.assertRaises(AppError) as caught:
                live.stop()
        self.assertEqual(caught.exception.code, 'companion_live_stop_timeout')
        # Round 1 asserted the port still accepted here; the caller must not return with the port bound, so it is force-closed.
        self.assertFalse(self.port_accepts(live), 'the timed-out caller returned with the port still bound')
        release.set()
        first.join(5)

    def test_a_first_stopper_wedged_in_shutdown_is_bounded_and_the_port_is_closed(self):
        from intune_iac import companion_live
        with mock.patch.object(companion_live, 'STOP_WAIT_SECONDS', 0.2):
            live = self.start()
            entered, release = self.hold_first_stopper(live)
            stopper, outcome = self.run_in_thread(live.stop)
            stopper.join(3)
            self.assertFalse(stopper.is_alive(), 'stop() did not return within the bound while shutdown() was wedged')
            self.assertEqual(outcome, [('returned', None)])
            self.assertFalse(self.port_accepts(live), 'the port is closed when stop() returns')
            live.stop()
            self.assertEqual(live.wait_step(), 'stopped')
            release.set()
            threading.Event().wait(0.3)    # the wedged attempt's helper now finishes; it must not change the state
            self.assertEqual(live.wait_step(), 'stopped')
            self.assertTrue(live.is_closed)

    def test_a_follower_whose_raw_close_fails_records_that_error_and_reports_the_port_truthfully(self):
        from intune_iac import companion_live
        from intune_iac.io import AppError
        live = self.start()
        entered, release = self.hold_first_stopper(live)
        real_socket = live.server.socket
        live.server.socket = UnclosableSocket(real_socket)
        self.addCleanup(lambda: setattr(live.server, 'socket', real_socket))
        first, _ = self.run_in_thread(live.stop)
        self.assertTrue(entered.wait(5))
        with mock.patch.object(companion_live, 'STOP_WAIT_SECONDS', 0.2):
            with self.assertRaises(AppError) as caught:
                live.stop()
        self.assertEqual(caught.exception.code, 'companion_live_stop_timeout')
        self.assertIsInstance(caught.exception.__cause__, PermissionError, 'the raw-close error is recorded')
        self.assertIn('could not be closed', caught.exception.message)
        self.assertTrue(self.port_accepts(live), 'precondition: the port really is still bound')
        release.set()
        first.join(5)

    def test_when_both_closes_fail_the_recorded_error_carries_the_raw_close_class(self):
        live = self.start()
        self.break_close(live)
        first, outcome = self.run_in_thread(live.stop)
        first.join(5)
        error = outcome[0][1]
        self.assertIsInstance(error, OSError)
        notes = ' '.join(getattr(error, '__notes__', []))
        self.assertIn('PermissionError', notes)
        self.assertNotIn('127.0.0.1', notes)
        self.assertNotIn(live.token, notes)

    def test_ending_from_a_request_thread_hands_the_stopping_over_and_the_first_reason_wins(self):
        live = self.start()
        entered, release = self.hold_first_stopper(live)
        caller, outcome = self.run_in_thread(lambda: live.end('idle', wait=False))
        caller.join(2)
        self.assertEqual(outcome, [('returned', None)], 'end(wait=False) must not block its caller')
        self.assertTrue(entered.wait(5), 'another thread is doing the stopping')
        live.end('later', wait=False)
        self.assertEqual(live.ended, 'idle')
        self.assertIsNone(live.wait_step())
        release.set()
        self.assertEqual(live.wait(poll=0.01), 'idle')
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', live.port), timeout=2)

    def break_close(self, live, raw=True, error=OSError, raw_error=PermissionError):
        """Make server.server_close() raise `error` and, with raw=True, make closing the raw listening socket fail too.
        Returns repair(), which undoes both (it also runs as a cleanup, so the fixture's own stop() can then close the port)."""
        real_socket = live.server.socket
        patch = mock.patch.object(live.server, 'server_close', side_effect=error('close failed'))
        patch.start()
        if raw:
            live.server.socket = UnclosableSocket(real_socket, raw_error)

        def repair():
            patch.stop()
            live.server.socket = real_socket
        self.addCleanup(repair)
        return repair

    def test_a_close_that_fails_is_reported_loudly_never_as_an_end_and_never_as_a_hang(self):
        # Round 1 patched server_close alone. With the raw-socket fallback that no longer prevents closure, so it now
        # breaks both closes; what it asserts is otherwise unchanged.
        from intune_iac.io import AppError
        live = self.start()
        self.break_close(live)
        first, first_outcome = self.run_in_thread(live.stop)
        first.join(5)
        self.assertEqual([kind for kind, _ in first_outcome], ['raised'])
        self.assertIsInstance(first_outcome[0][1], OSError, 'the first stopper sees the failure itself')
        waiter, waiter_outcome = self.run_in_thread(lambda: live.wait(poll=0.01))
        waiter.join(1)
        self.assertFalse(waiter.is_alive(), 'wait() hung after the close failed')
        self.assertEqual([kind for kind, _ in waiter_outcome], ['raised'], 'wait() must not return a reason')
        self.assertIsInstance(waiter_outcome[0][1], AppError)
        self.assertEqual(waiter_outcome[0][1].code, 'companion_live_close_failed')
        self.assertIn('OSError', waiter_outcome[0][1].message)
        with self.assertRaises(AppError) as step:
            live.wait_step()
        self.assertEqual(step.exception.code, 'companion_live_close_failed')
        with self.assertRaises(AppError) as second:
            live.stop()
        self.assertEqual(second.exception.code, 'companion_live_close_failed', 'not the timeout')

    def test_a_failed_server_close_whose_raw_socket_close_works_still_ends_normally_and_keeps_a_note(self):
        live = self.start()
        self.break_close(live, raw=False)
        live.stop()
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', live.port), timeout=2)
        self.assertEqual(live.wait(poll=0.01), 'stopped', 'the note is a diagnostic, never the end reason')
        self.assertIsInstance(live.close_note, OSError)
        live.stop()

    def test_when_both_closes_fail_the_failure_is_chained_and_a_later_stop_recovers(self):
        from intune_iac.io import AppError
        live = self.start()
        repair = self.break_close(live)
        first, first_outcome = self.run_in_thread(live.stop)
        first.join(5)
        self.assertEqual([kind for kind, _ in first_outcome], ['raised'])
        with self.assertRaises(AppError) as waiting:
            live.wait_step()
        self.assertEqual(waiting.exception.code, 'companion_live_close_failed')
        self.assertIsInstance(waiting.exception.__cause__, OSError, 'chained from the recorded error')
        with self.assertRaises(AppError) as retried:
            live.stop()
        self.assertEqual(retried.exception.code, 'companion_live_close_failed', 'the retry fails and says so')
        self.assertIsInstance(retried.exception.__cause__, OSError)
        self.assertTrue(self.port_accepts(live), 'precondition: the port is still bound while the close fails')
        repair()
        live.stop()
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', live.port), timeout=2)
        self.assertEqual(live.wait_step(), 'stopped')
        self.assertIsNone(live.close_note)

    def test_the_waiter_that_is_itself_the_first_stopper_gets_close_failed_not_the_raw_error(self):
        from intune_iac import companion_live
        from intune_iac.io import AppError
        with mock.patch.object(companion_live, 'WATCH_SECONDS', 3600):
            live = self.start(idle_seconds=600)
        self.break_close(live)
        self.clock.now += 601
        with self.assertRaises(AppError) as caught:
            live.wait(poll=0.01)
        self.assertEqual(caught.exception.code, 'companion_live_close_failed')
        self.assertIsInstance(caught.exception.__cause__, OSError)

    def test_an_interrupt_during_the_close_is_not_translated(self):
        from intune_iac import companion_live
        with mock.patch.object(companion_live, 'WATCH_SECONDS', 3600):
            live = self.start(idle_seconds=600)
        self.break_close(live, error=KeyboardInterrupt)
        self.clock.now += 601
        with self.assertRaises(KeyboardInterrupt):
            live.wait(poll=0.01)

    def check_a_source_held_across_stop(self, path, source):
        live = self.start()
        entered, release = threading.Event(), threading.Event()
        real = getattr(live, source)

        def held(*arguments):
            entered.set()
            release.wait(10)
            return real(*arguments)
        setattr(live, source, held)
        self.addCleanup(release.set)
        client, outcome = self.run_in_thread(lambda: self.request(path))
        self.assertTrue(entered.wait(5), 'the request passed the token check and is inside its source')
        live.stop()
        self.assertEqual(live.wait_step(), 'stopped')
        release.set()
        client.join(5)
        self.assertEqual([kind for kind, _ in outcome], ['returned'])
        status, _, body = outcome[0][1]
        self.assertEqual(status, 404, 'protected content was sent after stopping began')
        self.assertEqual(body, b'Not found.\n')

    def test_a_page_request_blocked_in_its_source_when_stopping_begins_never_gets_content(self):
        self.check_a_source_held_across_stop('', 'page_source')

    def test_a_snapshot_request_blocked_in_its_source_when_stopping_begins_never_gets_content(self):
        self.check_a_source_held_across_stop('snapshot', 'snapshot_source')

    def hold_a_writer(self):
        """Hold a page request inside its response write, after it was admitted. Returns (entered, release, client, outcome)."""
        from intune_iac import companion_live
        entered, release = threading.Event(), threading.Event()
        real = companion_live.Handler._send

        def held(handler, status, *arguments, **keywords):
            if status == 200:
                entered.set()
                release.wait(10)
            return real(handler, status, *arguments, **keywords)
        patch = mock.patch.object(companion_live.Handler, '_send', held)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(release.set)
        client, outcome = self.run_in_thread(lambda: self.request(''))
        self.assertTrue(entered.wait(5), 'the request was admitted and is writing')
        return entered, release, client, outcome

    def test_the_end_is_not_reported_while_an_admitted_writer_is_still_writing(self):
        live = self.start()
        _, release, client, outcome = self.hold_a_writer()
        stopper, stopper_outcome = self.run_in_thread(live.stop)
        stopper.join(0.3)
        self.assertTrue(stopper.is_alive(), 'stop() returned while a response was still being written')
        self.assertFalse(self.port_accepts(live), 'the listener is closed first, then the writers are awaited')
        self.assertIsNone(live.wait_step(), 'an end was reported while a writer was still writing')
        release.set()
        stopper.join(5)
        client.join(5)
        self.assertEqual(stopper_outcome, [('returned', None)])
        self.assertEqual(outcome[0][1][0], 200, 'a writer admitted before stopping began finishes its response')
        self.assertEqual(live.wait_step(), 'stopped')

    def test_a_writer_past_the_bound_makes_stop_raise_without_reporting_an_end(self):
        from intune_iac import companion_live
        from intune_iac.io import AppError
        live = self.start()
        _, release, client, _ = self.hold_a_writer()
        with mock.patch.object(companion_live, 'STOP_WAIT_SECONDS', 0.2):
            with self.assertRaises(AppError) as caught:
                live.stop()
            self.assertEqual(caught.exception.code, 'companion_live_writer_timeout')
            with self.assertRaises(AppError) as waiting:
                live.wait_step()
            self.assertEqual(waiting.exception.code, 'companion_live_close_failed')
        release.set()
        client.join(5)
        live.stop()
        self.assertEqual(live.wait_step(), 'stopped')

    def fail_in_the_background(self, how):
        """A stop that nobody is waiting on fails: a writer is held past the drain bound while the watchdog ('watchdog') or a
        request thread's hand-over ('handover') does the stopping. Returns the listener once its close has failed and the
        writer has finished, so that the next caller's retry can succeed."""
        from intune_iac import companion_live
        patch = mock.patch.object(companion_live, 'STOP_WAIT_SECONDS', 0.2)
        patch.start()
        self.addCleanup(patch.stop)
        live = self.start(idle_seconds=600)
        _, release, client, _ = self.hold_a_writer()
        if how == 'watchdog':
            self.clock.now += 601
        else:
            live.end('idle', wait=False)
        for _ in range(100):
            if live._state == 'close_failed':
                break
            threading.Event().wait(0.05)
        self.assertEqual(live._state, 'close_failed', 'precondition: the background stop failed')
        release.set()
        client.join(5)
        return live

    def test_a_background_failure_is_delivered_once_to_the_next_stop_even_when_its_retry_closes_the_listener(self):
        from intune_iac.io import AppError
        for how in ('watchdog', 'handover'):
            with self.subTest(how=how):
                live = self.fail_in_the_background(how)
                with self.assertRaises(AppError) as first:
                    live.stop()
                self.assertEqual(first.exception.code, 'companion_live_close_failed')
                self.assertEqual(first.exception.__cause__.code, 'companion_live_writer_timeout')
                self.assertTrue(live.is_closed, 'the retry still closed the listener')
                self.assertFalse(self.port_accepts(live))
                live.stop()
                self.assertEqual(live.wait_step(), 'idle')

    def test_a_background_failure_is_delivered_once_to_the_next_wait(self):
        # Guard: this already held on the state alone; the point is that the one delivery is not repeated by what follows.
        from intune_iac.io import AppError
        live = self.fail_in_the_background('watchdog')
        with self.assertRaises(AppError) as first:
            live.wait(poll=0.01)
        self.assertEqual(first.exception.code, 'companion_live_close_failed')
        self.assertEqual(first.exception.__cause__.code, 'companion_live_writer_timeout')
        live.stop()
        self.assertEqual(live.wait_step(), 'idle', 'the first recorded reason stays the end reason')

    def scripted_drain(self, live, *outcomes):
        """Replace the writer drain by a script: each call raises the next outcome if it is an exception, else returns."""
        remaining = list(outcomes)

        def drain():
            outcome = remaining.pop(0) if remaining else None
            if outcome is not None:
                raise outcome
        patch = mock.patch.object(live, '_drain_writers', drain)
        patch.start()
        self.addCleanup(patch.stop)

    def settle(self, live, state='close_failed'):
        for _ in range(100):
            if live._state == state:
                return
            threading.Event().wait(0.05)
        self.fail('the listener did not reach %s' % state)

    def test_a_foreground_retry_that_fails_does_not_lose_the_background_failure_before_it(self):
        from intune_iac.io import AppError
        live = self.start()
        first, second = OSError('first, in the background'), KeyError('second, in the retry')
        self.scripted_drain(live, first, second)
        live.end('idle', wait=False)
        self.settle(live)
        with self.assertRaises(AppError) as caught:
            live.stop()
        self.assertEqual(caught.exception.code, 'companion_live_close_failed')
        self.assertIs(caught.exception.__cause__, first, 'the earliest failure is the cause')
        self.assertIn('KeyError', ' '.join(getattr(caught.exception, '__notes__', [])), 'the retry\'s own failure is named')
        live.stop()
        self.assertEqual(live.wait_step(), 'idle')

    def test_two_background_failures_before_any_caller_are_delivered_together(self):
        from intune_iac.io import AppError
        live = self.start()
        first, second = OSError('first'), KeyError('second')
        self.scripted_drain(live, first, second)
        live.end('idle', wait=False)
        self.settle(live)
        live._stop_in_background()
        with self.assertRaises(AppError) as caught:
            live.stop()
        self.assertIs(caught.exception.__cause__, first)
        self.assertIn('KeyError', ' '.join(getattr(caught.exception, '__notes__', [])))
        live.stop()
        self.assertEqual(live.wait_step(), 'idle')

    def test_a_stale_background_attempt_that_fails_after_being_superseded_is_still_delivered(self):
        from intune_iac import companion_live
        from intune_iac.io import AppError
        live = self.start()
        stale = KeyError('stale attempt')
        drained = threading.Event()

        def failing_drain_once(remaining=[stale]):
            if remaining:
                drained.set()
                raise remaining.pop()
        patch = mock.patch.object(live, '_drain_writers', failing_drain_once)
        patch.start()
        self.addCleanup(patch.stop)
        entered, release = self.hold_first_stopper(live)
        live.end('idle', wait=False)
        self.assertTrue(entered.wait(5), 'the background attempt is inside shutdown()')
        with mock.patch.object(companion_live, 'STOP_WAIT_SECONDS', 0.2):
            with self.assertRaises(AppError) as timeout:
                live.stop()       # a foreground follower: times out and takes the state over
        self.assertEqual(timeout.exception.code, 'companion_live_stop_timeout')
        release.set()
        self.assertTrue(drained.wait(5), 'the superseded attempt went on and failed')
        threading.Event().wait(0.2)
        with self.assertRaises(AppError) as caught:
            live.stop()
        self.assertIs(caught.exception.__cause__, stale)
        self.assertTrue(live.is_closed)

    def test_after_one_delivery_a_still_unsettled_close_is_reported_as_unsettled_not_as_the_same_failure_again(self):
        from intune_iac.io import AppError
        live = self.start()
        failure = OSError('background')
        self.scripted_drain(live, failure)
        live.end('idle', wait=False)
        self.settle(live)
        with self.assertRaises(AppError) as first:
            live.wait_step()
        self.assertIs(first.exception.__cause__, failure)
        for call in (live.wait_step, lambda: live.wait(poll=0.01)):
            with self.assertRaises(AppError) as again:
                call()
            self.assertEqual(again.exception.code, 'companion_live_close_unsettled')
            self.assertEqual(again.exception.message, 'The listener has not been closed; stop() retries the close.')
            self.assertIsNone(again.exception.__cause__)
        live.stop()
        self.assertEqual(live.wait_step(), 'idle')

    def test_an_interrupt_in_the_raw_close_keeps_the_class_of_the_first_close_error(self):
        live = self.start()
        self.break_close(live, raw_error=KeyboardInterrupt)
        with self.assertRaises(KeyboardInterrupt) as caught:
            live.stop()
        self.assertIn('OSError', ' '.join(getattr(caught.exception, '__notes__', [])))

    def background_follower_interrupted(self, **how):
        """A stopper is wedged in shutdown(); a background stop follows it, times out, and its force-close is interrupted."""
        from intune_iac import companion_live
        live = self.start()
        entered, release = self.hold_first_stopper(live)
        real_socket = live.server.socket
        live.server.socket = InterruptibleSocket(real_socket, **how)
        self.addCleanup(lambda: setattr(live.server, 'socket', real_socket))
        first, _ = self.run_in_thread(live.stop)
        self.assertTrue(entered.wait(5))
        with mock.patch.object(companion_live, 'STOP_WAIT_SECONDS', 0.2):
            live._stop_in_background()
        return live

    def test_a_background_follower_interrupted_in_the_wake_up_shutdown_is_recorded_and_still_closes(self):
        from intune_iac.io import AppError
        live = self.background_follower_interrupted(on_shutdown=True)
        self.assertTrue(live._listener_closed(), 'the close was still attempted after the interrupted wake-up')
        for _ in range(40):      # without the wake-up, the serve loop releases the port at its next poll (50 ms)
            if not self.port_accepts(live):
                break
            threading.Event().wait(0.05)
        self.assertFalse(self.port_accepts(live))
        with self.assertRaises(AppError) as caught:
            live.wait_step()
        self.assertEqual(caught.exception.code, 'companion_live_close_failed')
        self.assertIsInstance(caught.exception.__cause__, KeyboardInterrupt)

    def test_a_background_follower_interrupted_in_the_raw_close_is_recorded_and_the_port_is_reported_as_bound(self):
        from intune_iac.io import AppError
        live = self.background_follower_interrupted(on_close=True)
        self.assertTrue(self.port_accepts(live), 'the close was interrupted, so the port is still bound')
        with self.assertRaises(AppError) as caught:
            live.wait_step()
        self.assertEqual(caught.exception.code, 'companion_live_close_failed')
        self.assertIsInstance(caught.exception.__cause__, KeyboardInterrupt)

    def test_a_retry_that_delivers_a_claimed_failure_with_its_own_leaves_the_state_consumed(self):
        from intune_iac.io import AppError
        live = self.start()
        first, second = OSError('first, in the background'), KeyError('second, in the retry')
        self.scripted_drain(live, first, second)
        live.end('idle', wait=False)
        self.settle(live)
        with self.assertRaises(AppError):
            live.stop()
        with self.assertRaises(AppError) as again:
            live.wait_step()
        self.assertEqual(again.exception.code, 'companion_live_close_unsettled')
        self.assertIsNone(again.exception.__cause__)

    def test_a_failure_published_between_the_state_read_and_the_claim_is_delivered_exactly_once(self):
        from intune_iac.io import AppError
        live = self.start()
        failure = OSError('background, published in the gap')
        with live._lock:
            live._state, live._generation = 'stopping', 7
        real_claim = live._claim

        published = []

        def claim_after_a_publish(*arguments, **keywords):
            if not published:
                published.append(True)
                live._publish(7, 'close_failed', failure, background=True)
            return real_claim(*arguments, **keywords)
        patch = mock.patch.object(live, '_claim', claim_after_a_publish)
        patch.start()
        self.addCleanup(patch.stop)
        outcomes = []

        def step():
            try:
                outcomes.append(('returned', live.wait_step()))
            except AppError as error:
                outcomes.append((error.code, error.__cause__))
        step()
        if not published:
            published.append(True)
            live._publish(7, 'close_failed', failure, background=True)    # a version with no gap: published here
        step()
        step()
        deliveries = [cause for code, cause in outcomes if code == 'companion_live_close_failed']
        self.assertEqual(deliveries, [failure], outcomes)
        self.assertEqual(outcomes[-1][0], 'companion_live_close_unsettled')

    def test_only_a_page_request_with_the_token_extends_the_limit(self):
        live = self.start(idle_seconds=600)
        self.clock.now += 500
        self.assertEqual(self.page().count('<svg'), 1)
        self.clock.now += 500
        # Polls, wrong tokens and refused methods do not count as use.
        self.assertEqual(self.request('snapshot')[0], 200)
        self.raw('/wrong/')
        self.request('', method='POST')
        self.clock.now += 99
        self.assertEqual(live.wait_step(), None)
        self.clock.now += 2
        self.assertEqual(live.wait_step(), 'idle')

    def test_the_command_ending_stops_it(self):
        from intune_iac.companion import run_companion
        announced = []
        def announce(text):
            announced.append(text)
            self.assertEqual(len(announced), 1)
            address = re.search(r'http://127\.0\.0\.1:(\d+)/([A-Za-z0-9_-]+)/', text)
            self.port, self.base = int(address.group(1)), '/%s/' % address.group(2)
            raise KeyboardInterrupt
        result = run_companion(self.read, serve=True, announce=announce)
        self.assertEqual(result['mode'], 'live')
        self.assertEqual(result['stopped'], 'interrupted')
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', self.port), timeout=2)

    def run_live_with_a_broken_close(self, announce, raw):
        """run_companion(serve=True) whose listener cannot close its port (raw=False: only server_close fails, so the
        fallback closes the socket). Returns (the listener, repair)."""
        from intune_iac import companion
        real_start, captured = companion.start_live, []

        def capturing(*arguments, **keywords):
            live = real_start(*arguments, **keywords)
            captured.append(live)
            self.addCleanup(live.stop)       # runs last: after the repair below, so it can close the port
            captured.append(self.break_close(live, raw=raw))
            return live
        with mock.patch.object(companion, 'start_live', capturing):
            try:
                companion.run_companion(self.read, serve=True, announce=announce)
            finally:
                self.live_under_test = captured[0]
        return captured[0]

    def test_a_cleanup_failure_does_not_replace_the_error_the_engineer_needs(self):
        def announce(text):
            raise RuntimeError('the announcement failed')
        with self.assertRaises(RuntimeError) as caught:
            self.run_live_with_a_broken_close(announce, raw=True)
        self.assertEqual(str(caught.exception), 'the announcement failed')
        notes = ' '.join(getattr(caught.exception, '__notes__', []))
        self.assertIn('companion_live_close_failed', notes)
        self.assertIn('OSError', notes)
        self.assertNotIn('127.0.0.1', notes)
        self.assertNotIn(self.live_under_test.token, notes)

    def test_an_interrupt_is_not_replaced_by_a_cleanup_failure_either(self):
        def announce(text):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.run_live_with_a_broken_close(announce, raw=True)
        self.assertIn('companion_live_close_failed', ' '.join(getattr(caught.exception, '__notes__', [])))

    def test_with_the_fallback_the_port_is_closed_when_the_error_propagates(self):
        def announce(text):
            raise RuntimeError('the announcement failed')
        with self.assertRaises(RuntimeError) as caught:
            self.run_live_with_a_broken_close(announce, raw=False)
        self.assertEqual(getattr(caught.exception, '__notes__', []), [], 'stop() succeeded, so there is nothing to note')
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', self.live_under_test.port), timeout=2)

    def test_a_cleanup_failure_with_nothing_propagating_is_raised(self):
        from intune_iac.companion import release_listener
        from intune_iac.io import AppError

        class Stuck:
            def stop(self):
                raise AppError('companion_live_close_failed', 'The listener could not be closed: OSError')
        with self.assertRaises(AppError) as caught:
            release_listener(Stuck(), None)
        self.assertEqual(caught.exception.code, 'companion_live_close_failed')

    def run_live_with_a_stop_that_raises(self, announce, error):
        """run_companion(serve=True) whose listener's stop() raises `error` (any BaseException) every time."""
        from intune_iac import companion
        real_start = companion.start_live

        def capturing(*arguments, **keywords):
            live = real_start(*arguments, **keywords)
            self.addCleanup(live.stop)       # the real stop, bound now: it runs after the patch below is undone
            patch = mock.patch.object(live, 'stop', side_effect=error)
            patch.start()
            self.addCleanup(patch.stop)
            return live
        with mock.patch.object(companion, 'start_live', capturing):
            companion.run_companion(self.read, serve=True, announce=announce)

    def test_a_cleanup_baseexception_does_not_replace_the_error_that_is_escaping(self):
        def announce(text):
            raise RuntimeError('the announcement failed')
        for error in (KeyboardInterrupt('stop interrupted'), SystemExit(3)):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(RuntimeError) as caught:
                    self.run_live_with_a_stop_that_raises(announce, error)
                self.assertEqual(str(caught.exception), 'the announcement failed')
                notes = ' '.join(getattr(caught.exception, '__notes__', []))
                self.assertIn(type(error).__name__, notes)
                self.assertNotIn('127.0.0.1', notes)

    def test_an_interrupt_is_kept_when_the_cleanup_raises_a_baseexception(self):
        def announce(text):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.run_live_with_a_stop_that_raises(announce, SystemExit(3))
        self.assertIn('SystemExit', ' '.join(getattr(caught.exception, '__notes__', [])))

    def test_with_nothing_escaping_a_cleanup_baseexception_propagates_unchanged(self):
        from intune_iac.companion import release_listener

        class Interrupted:
            def stop(self):
                raise KeyboardInterrupt('stop interrupted')
        with self.assertRaises(KeyboardInterrupt) as caught:
            release_listener(Interrupted(), None)
        self.assertEqual(str(caught.exception), 'stop interrupted')
        self.assertEqual(getattr(caught.exception, '__notes__', []), [])

    def test_serve_prints_the_address_never_launches_a_browser_and_stops_when_idle(self):
        from intune_iac.companion import run_companion
        said = []
        def announce(text):
            said.append(text)
            self.clock.now += 100000      # nobody ever loads the page
        result = run_companion(self.read, serve=True, announce=announce, idle_seconds=60)
        self.assertEqual(result['stopped'], 'idle')
        self.assertEqual(len(said), 1)
        self.assertRegex(said[0], r'http://127\.0\.0\.1:\d+/[A-Za-z0-9_-]+/')
        self.assertIn('this machine only', said[0])
        self.assertIn('no browser was opened', said[0].lower())
        self.assertIn('Ctrl+C', said[0])
        self.assertNotIn(re.search(r'/([A-Za-z0-9_-]{20,})/', said[0]).group(1), json.dumps(result))

    def test_the_listener_starts_only_when_asked_and_leaves_no_thread_behind(self):
        before = threading.active_count()
        live = self.start()
        self.assertGreater(threading.active_count(), before)
        live.stop()
        deadline = 50
        while threading.active_count() > before and deadline:
            threading.Event().wait(0.02)
            deadline -= 1
        self.assertLessEqual(threading.active_count(), before)

    def test_live_settings_reach_the_page(self):
        self.start(idle_seconds=900, poll_seconds=7)
        page = self.page()
        self.assertIn('data-poll="7000"', page)
        self.assertIn('15 minutes', page)


if __name__ == '__main__':
    unittest.main()
