"""The companion's local listener: the page and the current snapshot revision, to this machine only.

Requirement 17 UX-VIS, second slice. It binds 127.0.0.1 on an ephemeral port (there is no argument that names another
interface) and answers GET for exactly two addresses under a random path token: the page (/TOKEN/) and the snapshot
(/TOKEN/snapshot). Every other path is 404, every other method is 405, a request addressed to any host name but the
loopback address is 421 (a name an attacker rebinds to this port reads nothing), and a wrong token looks like any
unknown path. There is no write, execution, approval or navigation endpoint, no CORS header, no log line (the token
is in the address) and no reason in an error. The page and the snapshot come from callables the caller gives, so
this module reads no store and decides nothing.

It stops when stop() is called (the command ends), or when no page has been requested for the idle limit. Only a
request for the page with the right token counts as use: a poll, a wrong token and a refused method do not extend it.
The idle limit is judged on a monotonic clock (this host's wall clock steps), injectable as `monotonic`.
"""
from __future__ import annotations

import hmac
import http.server
import json
import re
import secrets
import threading
import time

from .io import AppError

LOOPBACK = '127.0.0.1'
IDLE_SECONDS = 1800
POLL_SECONDS = 3
TOKEN_BYTES = 24
REQUEST_TIMEOUT = 5
SNAPSHOT_NAME = 'snapshot'

# Injectable for tests; the idle limit uses it only for elapsed time within this process.
monotonic = time.monotonic

_CSP = re.compile(r'http-equiv="Content-Security-Policy" content="([^"]*)"')


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'intune-companion'
    sys_version = ''
    protocol_version = 'HTTP/1.0'
    timeout = REQUEST_TIMEOUT

    def version_string(self):
        return self.server_version

    def log_message(self, *args):
        """No log: the address (with its token) must not reach a terminal or a file through this."""

    def _send(self, status, body=b'', kind='text/plain; charset=utf-8', extra=()):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _refuse(self):
        self._send(405, b'GET only.\n', extra=(('Allow', 'GET'),))

    def __getattr__(self, name):
        # Every method but GET, known or not, gets the same refusal: the only thing a client can do here is read.
        if name.startswith('do_') and name != 'do_GET':
            return self._refuse
        raise AttributeError(name)

    def do_GET(self):
        companion = self.server.companion
        if self.headers.get('Host') not in companion.allowed_hosts:
            return self._send(421, b'Misdirected request.\n')
        parts = self.path.split('/')
        token_ok = len(parts) == 3 and parts[0] == '' and hmac.compare_digest(
            parts[1].encode('latin-1', 'replace'), companion.token.encode('ascii'))
        if not token_ok or parts[2] not in ('', SNAPSHOT_NAME):
            return self._send(404, b'Not found.\n')
        try:
            if parts[2] == SNAPSHOT_NAME:
                body = json.dumps(companion.snapshot_source(), sort_keys=True, separators=(',', ':')).encode('utf-8')
                return self._send(200, body, 'application/json')
            companion.touch()
            page = companion.page_source(companion.live)
            policy = _CSP.search(page)
            extra = (('Content-Security-Policy', policy.group(1) + "; frame-ancestors 'none'"),) if policy else ()
            return self._send(200, page.encode('utf-8'), 'text/html; charset=utf-8', extra)
        except AppError:
            return self._send(503, b'The object can no longer be read.\n')
        except Exception:
            # What went wrong stays on this side: the client is told only that it did.
            return self._send(500, b'The snapshot could not be read.\n')


class LiveCompanion:
    """One listener: start() binds it, wait() blocks until it ends, stop() ends it (safe to repeat)."""

    def __init__(self, page_source, snapshot_source, *, idle_seconds=IDLE_SECONDS, poll_seconds=POLL_SECONDS, token=None):
        if (not isinstance(idle_seconds, int) or isinstance(idle_seconds, bool) or idle_seconds < 1
                or not isinstance(poll_seconds, int) or isinstance(poll_seconds, bool) or not 1 <= poll_seconds <= 60):
            raise AppError('companion_live_invalid', 'Live mode needs an idle limit of at least one second and a poll interval of 1 to 60 seconds.')
        self.page_source, self.snapshot_source = page_source, snapshot_source
        self.idle_seconds = idle_seconds
        self.token = token if token is not None else secrets.token_urlsafe(TOKEN_BYTES)
        self.live = {'snapshot': SNAPSHOT_NAME, 'poll_seconds': poll_seconds, 'idle_seconds': idle_seconds}
        self.host, self.port, self.base, self.address, self.server = LOOPBACK, None, None, None, None
        self.allowed_hosts = set()
        self.last_page = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._closed = False

    def start(self):
        server = http.server.ThreadingHTTPServer((LOOPBACK, 0), Handler)
        server.daemon_threads = True
        server.companion = self
        self.server = server
        self.port = server.server_address[1]
        self.base = '/%s/' % self.token
        self.address = 'http://%s:%d%s' % (LOOPBACK, self.port, self.base)
        self.allowed_hosts = {'%s:%d' % (LOOPBACK, self.port), 'localhost:%d' % self.port}
        self.last_page = monotonic()
        self._thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        self._thread.start()
        return self

    def touch(self):
        with self._lock:
            self.last_page = monotonic()

    def wait_step(self):
        """One look at whether the listener has ended: 'stopped', 'idle' (and it stops itself), or None."""
        if self._stop.is_set():
            return 'stopped'
        with self._lock:
            idle = monotonic() - self.last_page >= self.idle_seconds
        if idle:
            self.stop()
            return 'idle'
        return None

    def wait(self, poll=0.2):
        """Block until the listener ends, and say why: 'idle' or 'stopped'."""
        while True:
            reason = self.wait_step()
            if reason:
                return reason
            self._stop.wait(poll)

    def stop(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._stop.set()
        if self.server is not None:
            if self._thread is not None:
                self.server.shutdown()
                self._thread.join(5)
            self.server.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
