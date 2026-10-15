"""The companion's local listener: the page and the current snapshot revision, to this machine only.

Requirement 17 UX-VIS, second slice. It binds 127.0.0.1 on an ephemeral port (there is no argument that names another
interface) and answers GET for exactly two addresses under a random path token: the page (/TOKEN/) and the snapshot
(/TOKEN/snapshot). Every other path is 404, every other method is 405, a request addressed to any host name but the
loopback address is 421 (a name an attacker rebinds to this port reads nothing), and a wrong token looks like any
unknown path. There is no write, execution, approval or navigation endpoint, no CORS header, no log line (the token
is in the address) and no reason in an error. Every response, errors included, carries a restrictive content security
policy with frame-ancestors 'none'; an HTML page that does not carry its own policy is never sent. The page and the
snapshot come from callables the caller gives, so this module reads no store and decides nothing.

Limit of the design: loopback is not isolation between users of one machine. Possession of the address (its token) is
the only authentication, so any local user who obtains it can read the page and the snapshot. The announced address
is a secret and is said to be one; an OS-user-authenticated bridge is an open option, not built.

It stops when stop() is called (the command ends), or when no page has been requested for the idle limit. The idle
limit is enforced by the listener itself (a watchdog thread, and a check before every request is served), not by
whoever holds it: a caller that only keeps the returned object still gets the limit, and a late request cannot revive
an expired listener. Only a request for the page with the right token counts as use: a poll, a wrong token and a
refused method do not extend it. The limit is judged on a monotonic clock (this host's wall clock steps), injectable
as `monotonic`. Concurrent handlers are bounded; a connection over the bound is answered 503 at once and closed.
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
WATCH_SECONDS = 0.05
MAX_HANDLERS = 8
# What every non-page response is allowed to do: nothing, and not be framed.
DEFAULT_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

# Sent on every response of every kind: a page, a snapshot, a refusal, the parser's own errors and the overload reply.
SECURITY_HEADERS = (('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'),
                    ('Cross-Origin-Resource-Policy', 'same-origin'), ('Cross-Origin-Opener-Policy', 'same-origin'))

# Injectable for tests; the idle limit uses it only for elapsed time within this process.
monotonic = time.monotonic

_CSP = re.compile(r'http-equiv="Content-Security-Policy" content="([^"]*)"')
_TOKEN = re.compile(r'[A-Za-z0-9_-]{20,128}')


def _new_token():
    """A fresh path token: 24 random bytes, URL-safe. Private: no caller picks its own, so none can pick a weak one."""
    return secrets.token_urlsafe(TOKEN_BYTES)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'intune-companion'
    sys_version = ''
    protocol_version = 'HTTP/1.0'
    timeout = REQUEST_TIMEOUT

    def version_string(self):
        return self.server_version

    def log_message(self, *args):
        """No log: the address (with its token) must not reach a terminal or a file through this."""

    def _send(self, status, body=b'', kind='text/plain; charset=utf-8', csp=DEFAULT_CSP, extra=()):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        self.send_header('Content-Security-Policy', csp)
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def send_error(self, code, message=None, explain=None):
        """The parser's own refusals (a malformed request line, an unsupported version, a line or header too long) get the
        same headers as every other response, a fixed body, and nothing of the request or of this Python."""
        # A request line the parser could not read leaves the version at HTTP/0.9, which has no headers; this is HTTP/1.0.
        self.request_version = 'HTTP/1.0'
        self.close_connection = True
        self._send(code, b'Request refused.\n')

    def _refuse(self):
        self._send(405, b'GET only.\n', extra=(('Allow', 'GET'),))

    def __getattr__(self, name):
        # Every method but GET, known or not, gets the same refusal: the only thing a client can do here is read.
        if name.startswith('do_') and name != 'do_GET':
            return self._refuse
        raise AttributeError(name)

    def _page_policy(self, page):
        """The policy the page declares for itself, which becomes the header; a page without a sound one is not sent."""
        found = _CSP.search(page)
        if not found or "default-src 'none'" not in found.group(1) or 'unsafe' in found.group(1) or '*' in found.group(1):
            raise ValueError('the page has no sound content security policy')
        return found.group(1) + "; frame-ancestors 'none'"

    def do_GET(self):
        companion = self.server.companion
        if companion.expired():
            # An expired listener is gone: it neither answers nor starts a new window.
            companion.end('idle', wait=False)
            return self._send(404, b'Not found.\n')
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
            policy = self._page_policy(page)
            return self._send(200, page.encode('utf-8'), 'text/html; charset=utf-8', policy)
        except AppError:
            return self._send(503, b'The object can no longer be read.\n')
        except Exception:
            # What went wrong stays on this side: the client is told only that it did.
            return self._send(500, b'The snapshot could not be read.\n')


def _overload_reply():
    """The answer to a connection over the handler bound, written by hand (no handler runs for it) with the same headers."""
    body = b'Busy.\n'
    head = ['HTTP/1.0 503 Busy', 'Content-Type: text/plain; charset=utf-8', 'Content-Length: %d' % len(body)]
    head += ['%s: %s' % pair for pair in SECURITY_HEADERS] + ['Content-Security-Policy: ' + DEFAULT_CSP, 'Connection: close']
    return ('\r\n'.join(head) + '\r\n\r\n').encode('ascii') + body


class BoundedServer(http.server.ThreadingHTTPServer):
    """A threaded server that runs at most `limit` handlers at once; a connection over that is refused at once."""
    daemon_threads = True

    def __init__(self, address, handler, limit=MAX_HANDLERS):
        super().__init__(address, handler)
        self._slots = threading.BoundedSemaphore(limit)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            try:
                request.sendall(_overload_reply())
            except OSError:
                pass
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class LiveCompanion:
    """One listener: start() binds it and starts its watchdog, wait() blocks until it ends, stop() ends it (safe to repeat)."""

    def __init__(self, page_source, snapshot_source, *, idle_seconds=IDLE_SECONDS, poll_seconds=POLL_SECONDS):
        if (not isinstance(idle_seconds, int) or isinstance(idle_seconds, bool) or idle_seconds < 1
                or not isinstance(poll_seconds, int) or isinstance(poll_seconds, bool) or not 1 <= poll_seconds <= 60):
            raise AppError('companion_live_invalid', 'Live mode needs an idle limit of at least one second and a poll interval of 1 to 60 seconds.')
        token = _new_token()
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            raise AppError('companion_live_invalid', 'The listener could not make a sound path token.')
        self.token = token
        self.page_source, self.snapshot_source = page_source, snapshot_source
        self.idle_seconds = idle_seconds
        self.live = {'snapshot': SNAPSHOT_NAME, 'poll_seconds': poll_seconds, 'idle_seconds': idle_seconds}
        self.host, self.port, self.base, self.address, self.server = LOOPBACK, None, None, None, None
        self.allowed_hosts = set()
        self.last_page = None
        self.ended = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._watchdog = None
        self._closed = False

    def start(self):
        server = BoundedServer((LOOPBACK, 0), Handler)
        server.companion = self
        self.server = server
        self.port = server.server_address[1]
        self.base = '/%s/' % self.token
        self.address = 'http://%s:%d%s' % (LOOPBACK, self.port, self.base)
        self.allowed_hosts = {'%s:%d' % (LOOPBACK, self.port), 'localhost:%d' % self.port}
        self.last_page = monotonic()
        self._thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        self._thread.start()
        self._watchdog = threading.Thread(target=self._watch, daemon=True)
        self._watchdog.start()
        return self

    def touch(self):
        with self._lock:
            self.last_page = monotonic()

    def expired(self):
        with self._lock:
            return self.last_page is not None and monotonic() - self.last_page >= self.idle_seconds

    def _watch(self):
        """The idle limit, enforced by the listener itself so that no caller has to remember to."""
        while not self._stop.wait(WATCH_SECONDS):
            if self.expired():
                self.end('idle')
                return

    def end(self, reason, wait=True):
        """End the listener and record why (the first reason stays). wait=False hands the stopping to another thread,
        for a caller that is itself one of the listener's request threads."""
        with self._lock:
            if self.ended is None:
                self.ended = reason
        if wait:
            self.stop()
        else:
            threading.Thread(target=self.stop, daemon=True).start()

    def wait_step(self):
        """One look at whether the listener has ended: 'stopped' or 'idle', or None while it runs."""
        if not self._stop.is_set() and self.expired():
            self.end('idle')
        return (self.ended or 'stopped') if self._stop.is_set() else None

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
            if self.ended is None:
                self.ended = 'stopped'
        self._stop.set()
        if self.server is not None:
            if self._thread is not None:
                self.server.shutdown()
                self._thread.join(5)
            self.server.server_close()
        if self._watchdog is not None and self._watchdog is not threading.current_thread():
            self._watchdog.join(5)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
