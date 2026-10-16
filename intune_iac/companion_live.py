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
import socket
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
# How long a second stop() waits for the first to finish closing the port, and how long each thread join waits.
STOP_WAIT_SECONDS = 5
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

    def _send_protected(self, companion, body, kind, csp=DEFAULT_CSP):
        """The one place token-protected content leaves. The source may have been slow, so whether stopping has begun is
        asked again here, at the moment of writing; if it has, the answer is the refusal of an unknown path and no content."""
        if not companion.begin_write():
            return self._send(404, b'Not found.\n')
        try:
            return self._send(200, body, kind, csp)
        finally:
            companion.end_write()

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
                return self._send_protected(companion, body, 'application/json')
            companion.touch()
            page = companion.page_source(companion.live)
            policy = self._page_policy(page)
            return self._send_protected(companion, page.encode('utf-8'), 'text/html; charset=utf-8', policy)
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
        # running -> stopping -> closed, or stopping -> close_failed (retryable: the next stop() tries the close again).
        # "closed" is the only state in which an end is reported, and it means the listening socket is closed.
        self._state = 'running'
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._changed = threading.Condition(self._lock)
        self._close_error = None   # why the last attempt failed; meaningful in close_failed only
        self._close_note = None    # a close problem that was recovered from (diagnostic only, never the end reason)
        self._serving_stopped = False
        # Failures met where nobody was waiting, kept until a caller has been given them. This is separate from the state
        # (which only the newest attempt may publish): a superseded attempt still records its failure here.
        self._undelivered = []
        self._consumed = False     # the failure behind the current close_failed state has been given to a waiter
        self._generation = 0       # one per stop attempt; only the newest attempt may publish a state
        self._writers = 0          # handlers admitted to write a protected response, until they have finished
        self._thread = None
        self._watchdog = None

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
                self._record_reason('idle')
                self._stop_in_background()
                return

    def _record_reason(self, reason):
        with self._lock:
            if self.ended is None:
                self.ended = reason

    def _stop_in_background(self):
        """Stop from a thread nobody waits on. A failure is not raised into it: it is kept (see _publish) until the next
        caller of wait(), wait_step() or stop() claims it, even if that caller's own retry then closes or fails."""
        try:
            self._run_stop(background=True)
        except BaseException:
            pass

    def end(self, reason, wait=True):
        """End the listener and record why (the first reason stays). wait=False hands the stopping to another thread,
        for a caller that is itself one of the listener's request threads."""
        self._record_reason(reason)
        if wait:
            self.stop()
        else:
            threading.Thread(target=self._stop_in_background, daemon=True).start()

    def begin_write(self):
        """Admit a handler to write protected content: refused once stopping has begun; otherwise it is counted, in the same
        step, so that stop() can wait for it."""
        with self._lock:
            if self._state != 'running':
                return False
            self._writers += 1
            return True

    def end_write(self):
        with self._changed:
            self._writers -= 1
            self._changed.notify_all()

    def _drain_writers(self):
        """Wait, bounded, for the handlers already writing; raises (no end is reported) if one is still writing after that."""
        with self._changed:
            if not self._changed.wait_for(lambda: self._writers == 0, STOP_WAIT_SECONDS):
                raise AppError('companion_live_writer_timeout', 'A response was still being written when the listener stopped.')

    @property
    def is_closed(self):
        """True once the stop has been established: the listening socket is closed and no protected response is being written."""
        with self._lock:
            return self._state == 'closed'

    @property
    def close_note(self):
        """A problem closing the port that was recovered from (the fallback closed the socket), or None. Never the end reason."""
        with self._lock:
            return self._close_note

    def _close_failure(self, error):
        failure = AppError('companion_live_close_failed', 'The listener could not be closed: %s' % type(error).__name__)
        failure.__cause__ = error
        return failure

    def _settled(self):
        return self._state in ('closed', 'close_failed')

    def wait_step(self):
        """One look at whether the listener has ended: 'stopped' or 'idle', or None while it runs or is still being
        stopped. It ends only once the port is closed, never while a stopper is still inside shutdown(). A close that
        failed is raised as companion_live_close_failed, also in the waiter that was itself the stopper."""
        if not self._stop.is_set() and self.expired():
            try:
                self.end('idle')
            except Exception as error:
                if error is self._close_error:
                    raise self._close_failure(error) from error
                raise
        with self._lock:
            # One critical section: the state, the claim and the consumed mark cannot be separated by another thread.
            state, error, reason = self._state, self._close_error, self.ended or 'stopped'
            claimed = self._claim_locked(consumes_state=state == 'close_failed')
            consumed = self._consumed
        if claimed:
            raise self._delivery(claimed)
        if state == 'close_failed':
            if consumed:
                # The failure behind this state has been given to a caller: say only that the close is unsettled.
                raise AppError('companion_live_close_unsettled', 'The listener has not been closed; stop() retries the close.')
            raise self._close_failure(error)
        return reason if state == 'closed' else None

    def wait(self, poll=0.2):
        """Block until the listener ends, and say why: 'idle' or 'stopped'."""
        while True:
            reason = self.wait_step()
            if reason:
                return reason
            with self._changed:
                self._changed.wait_for(self._settled, poll)

    def _raw_close(self, wake=False):
        """Close the raw listening socket, guarded; returns the error if that failed. wake=True first shuts it down, which
        also ends a connection backlog and wakes a thread still waiting on it, so the port refuses at once."""
        sock = getattr(self.server, 'socket', None)
        if sock is None:
            return None
        interrupted = None
        if wake:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            except BaseException as error:
                interrupted = error     # the close below is still attempted
        try:
            sock.close()
        except BaseException as error:
            # An interrupt too: the caller decides, so that no earlier error is lost with it. An interrupt from the wake-up
            # stays the primary failure over an ordinary close failure, which is named on it by class.
            if interrupted is not None:
                if isinstance(error, Exception):
                    interrupted.add_note('The close also failed: %s' % type(error).__name__)
                    return interrupted
                error.add_note('The wake-up shutdown was also interrupted: %s' % type(interrupted).__name__)
            return error
        return interrupted

    def _listener_closed(self):
        """Closure is judged by the socket itself: a closed socket has no descriptor."""
        try:
            return self.server.socket.fileno() == -1
        except Exception:
            return False

    def _close_listener(self):
        """Close the listening socket: server_close(), then the raw socket if that left it open. Returns the problem met on
        the way, if any (a diagnostic once the socket is closed). When both fail, the raw close's class is kept as a note on
        the first error (class only: no address, no token). An interrupt in server_close() still gets the raw close first."""
        problem = None
        try:
            self.server.server_close()
        except BaseException as error:
            problem = error
        raw_problem = None if self._listener_closed() else self._raw_close()
        if raw_problem is not None:
            if problem is None:
                problem = raw_problem
            elif isinstance(raw_problem, Exception):
                note = 'The raw close also failed: %s' % type(raw_problem).__name__
                if note not in getattr(problem, '__notes__', ()):
                    problem.add_note(note)
            else:
                # An interrupt during the raw close propagates; it carries the class of the first error so that is kept.
                raw_problem.add_note('The first close error was: %s' % type(problem).__name__)
                problem = raw_problem
        if problem is not None and not isinstance(problem, Exception):
            raise problem
        return problem

    def _bounded_shutdown(self):
        """server.shutdown() waits for the serve loop to leave, and nothing bounds that, so it runs in a helper thread and
        is waited for at most STOP_WAIT_SECONDS. True if it finished; False if it is still wedged (the caller then closes
        the socket itself). The helper changes no state of this object, so a late finish is harmless."""
        bound = STOP_WAIT_SECONDS    # read before the helper starts: this attempt keeps the bound it began with
        finished, failure = threading.Event(), []

        def run():
            try:
                self.server.shutdown()
            except BaseException as error:
                failure.append(error)
            finally:
                finished.set()
        threading.Thread(target=run, daemon=True).start()
        if not finished.wait(bound):
            return False
        if failure:
            raise failure[0]
        self._thread.join(bound)
        return True

    def _shut_down_and_close(self):
        """What the one stopper does, in order, every step bounded. Raises if the port could not be closed; returns the
        recovered problem, if any."""
        if self.server is None:
            return None
        forced = None
        if self._thread is not None and not self._serving_stopped:
            if self._bounded_shutdown():
                self._serving_stopped = True
            else:
                forced = self._raw_close(wake=True)
                if forced is not None and not isinstance(forced, Exception):
                    raise forced
                self._serving_stopped = self._listener_closed()
        problem = self._close_listener()
        if forced is not None:
            # The failure of the forced close is kept even if the close then worked: it is the diagnostic. A later
            # problem is named on it by class.
            if problem is not None:
                note = 'A later close attempt also failed: %s' % type(problem).__name__
                if note not in getattr(forced, '__notes__', ()):
                    forced.add_note(note)
            problem = forced
        if not self._listener_closed():
            raise problem or AppError('companion_live_close_failed', 'The listening socket is still open.')
        self._drain_writers()
        return problem

    def _publish(self, generation, state, error=None, note=None, background=False):
        """Record the outcome of a stop attempt, unless a newer attempt has taken over: a late finish never overwrites the
        state. Its failure is still recorded when it was a background attempt, because no caller is there to receive it."""
        with self._changed:
            if background and error is not None:
                self._undelivered.append(error)
            if self._generation != generation:
                return False
            self._state, self._close_error = state, error
            if state == 'closed':
                self._close_note = note
            else:
                self._consumed = False
            self._changed.notify_all()
            return True

    def _claim_locked(self, consumes_state=False):
        """Take every failure nobody has been given yet (the caller holds the lock); a failure that arrives later waits for
        the next caller. If this delivery is of the failure behind the current close_failed state, that state is consumed."""
        claimed, self._undelivered = self._undelivered, []
        if claimed and consumes_state:
            self._consumed = True
        return claimed

    def _claim(self, consumes_state=False):
        with self._lock:
            return self._claim_locked(consumes_state)

    def _delivery(self, claimed, own=None):
        """One error for a caller: chained from the earliest failure, naming by class every later one and the caller's own
        (no address, no token)."""
        report = AppError('companion_live_close_failed', 'The listener could not be closed: %s' % type(claimed[0]).__name__)
        report.__cause__ = claimed[0]
        for later in claimed[1:] + ([own] if own is not None else []):
            report.add_note('Also failed: %s' % type(later).__name__)
        return report

    def stop(self):
        return self._run_stop(background=False)

    def _run_stop(self, background):
        """Stop the listener; returns once the port is closed. A call that is not the first waits for the first to finish
        closing it; if that takes longer than STOP_WAIT_SECONDS it closes the raw listening socket itself, verifies it, and
        raises, so it never returns with the port bound unannounced and never reports an end that has not happened. After
        a failed close the next stop() tries the close again."""
        with self._lock:
            if self._state == 'running':
                role = 'first'
                if self.ended is None:
                    self.ended = 'stopped'
            elif self._state == 'close_failed':
                role = 'retry'
            else:
                role = 'follower'
            if role != 'follower':
                self._state = 'stopping'
                self._generation += 1
                mine = self._generation
        if role == 'follower':
            return self._follow(background)
        self._stop.set()
        try:
            problem = self._shut_down_and_close()
        except BaseException as error:
            published = self._publish(mine, 'close_failed', error, background=background)
            if role == 'retry' and isinstance(error, Exception):
                # The report below delivers the earlier failures with this one named, so the state it leaves is consumed.
                claimed = [] if background else self._claim(consumes_state=published)
                if claimed:
                    raise self._delivery(claimed, own=error)
                raise self._close_failure(error) from error
            raise
        if self._publish(mine, 'closed', note=problem):
            # Publish before this join: the watchdog may itself be waiting above as a second caller.
            if self._watchdog is not None and self._watchdog is not threading.current_thread():
                self._watchdog.join(STOP_WAIT_SECONDS)
        if not background:
            claimed = self._claim()
            if claimed:
                raise self._delivery(claimed)

    def _follow(self, background):
        with self._changed:
            generation = self._generation
            settled = self._changed.wait_for(self._settled, STOP_WAIT_SECONDS)
            state, error = self._state, self._close_error
        if settled:
            claimed = [] if background else self._claim(consumes_state=state == 'close_failed')
            if claimed:
                raise self._delivery(claimed)
            if state == 'close_failed':
                raise self._close_failure(error)
            return None
        # The stopper outlived the bound. Close the socket here, check that it is closed, and say what is true. This
        # attempt takes over the state, so a stopper that finishes later cannot overwrite it; the next stop() retries.
        forced = self._raw_close(wake=True)
        if forced is not None and not isinstance(forced, Exception):
            self._take_over(generation, forced, background)      # settled and retryable before the interrupt propagates
            raise forced
        if self._listener_closed():
            message = 'The listener is still being stopped by another caller; its port is closed.'
        else:
            message = ('The listener is still being stopped by another caller, and its port could not be closed: %s.'
                       % (type(forced).__name__ if forced is not None else 'the socket stayed open'))
        failure = AppError('companion_live_stop_timeout', message)
        failure.__cause__ = forced
        self._take_over(generation, failure, background)
        raise failure

    def _take_over(self, generation, failure, background):
        """A follower that gave up on the stopper takes the state over: queued once if nobody is there to receive it, the
        generation moves on so the stopper's late finish cannot overwrite this, and the next stop() retries at once."""
        with self._changed:
            if background:
                self._undelivered.append(failure)
            if self._state == 'stopping' and self._generation == generation:
                self._generation += 1
                self._state, self._close_error, self._consumed = 'close_failed', failure, False
                self._changed.notify_all()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
