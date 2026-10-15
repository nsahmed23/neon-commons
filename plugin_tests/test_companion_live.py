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
