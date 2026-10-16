"""Redaction harness: every credential route is run with its own fake canary; no canary may leave its route.

Each canary is generated here, is random per run, and is shaped like a real secret (mixed case, digits, no words).
Nothing here uses a real token, tenant or network client: services are local fakes or modeled responses.

For each route the harness asserts that its canary is absent from stdout, stderr, every file the command wrote,
the arguments of every child process started during the call, and the parent environment after the call (the
environment must be exactly what it was before, so a command cannot export or persist the value). The judge route
also asserts the canary never reached the local fake endpoint's request body. Pattern: test_provider_journey_v5.py
IdentityAuthenticationCliTests.
"""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import traceback
import unittest
from unittest.mock import patch

from intune_iac import cli
from intune_iac.io import write_json

PROJECT = Path(__file__).resolve().parents[1]
_TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")  # the HTTP token grammar


def close_if_open(fd):
    # The command closes the descriptor it consumed; a leftover is closed here.
    try:
        os.close(fd)
    except OSError:
        pass


def recording_handle(handle_class, seen):
    # Records what a ClientSecretHandle was given, so a route's test proves the canary was consumed there. The class
    # itself is kept (the readers check its exact type); only its constructor is wrapped.
    original = handle_class.__init__

    def init(self, value, *a, **k):
        seen.append(value)
        original(self, value, *a, **k)
    return patch.object(handle_class, '__init__', init)


def canary(label):
    # A distinct, secret-shaped value per route; the label is only a prefix that makes a failure readable.
    return label + '-' + secrets.token_urlsafe(30) + 'A1'


def _aligned_base64(raw, encode):
    """The base64 text a value leaves inside a larger base64 payload, at each of the three byte alignments.

    Characters that mix the value's bits with unknown neighbouring bytes are dropped; the rest is fixed by the value.
    """
    found = []
    for lead in range(3):
        text = encode(b"\x00" * lead + raw).decode().rstrip("=")
        total = lead + len(raw)
        skip = -(-lead * 8 // 6)
        keep = total // 3 * 4 + total % 3
        if keep - skip >= 8:
            found.append(text[skip:keep].encode())
    return found


def forms(value):
    """The enumerated transformations a canary is searched for in (this list is the whole claim; nothing else is).

    plain; JSON-escaped; hex (lower and upper case); percent-encoding of every byte (lower and upper case hex digits);
    base64, standard and URL-safe alphabets, padded and unpadded; and each base64 alphabet as the value would appear
    inside a larger base64 payload at the three byte alignments.
    """
    raw = value.encode()
    standard, urlsafe = base64.b64encode(raw), base64.urlsafe_b64encode(raw)
    found = {'plain': raw, 'json_escaped': json.dumps(value).encode()[1:-1],
             'hex': raw.hex().encode(), 'hex_upper': raw.hex().upper().encode(),
             'percent_upper': ''.join('%{:02X}'.format(b) for b in raw).encode(),
             'percent_lower': ''.join('%{:02x}'.format(b) for b in raw).encode(),
             'base64': standard, 'base64_unpadded': standard.rstrip(b'='),
             'urlsafe_base64': urlsafe, 'urlsafe_base64_unpadded': urlsafe.rstrip(b'=')}
    for number, form in enumerate(_aligned_base64(raw, base64.b64encode)):
        found['base64_aligned_%d' % number] = form
    for number, form in enumerate(_aligned_base64(raw, base64.urlsafe_b64encode)):
        found['urlsafe_base64_aligned_%d' % number] = form
    return found


class ConnectionRegistry:
    """A monotonic id per socket object, assigned on first use, holding a strong reference to the object.

    Never id(socket): once a socket is destroyed Python may give its id to an unrelated one, and their bytes would be
    concatenated into a request that neither sent.
    """

    def __init__(self):
        self.objects = []

    def key(self, owner):
        for number, known in enumerate(self.objects):
            if known is owner:
                return number
        self.objects.append(owner)
        return len(self.objects) - 1


_WATCH = {'terminal': None, 'launch': None, 'deleted': None}  # lists/dicts while a command runs, else None


def _scan_before_removal(path, dir_fd=None):
    """Read what is about to be removed. A relative path is resolved against dir_fd (through /proc/self/fd on Linux);
    if it cannot be resolved the route fails, because the removal could not be inspected."""
    state = _WATCH['deleted']
    try:
        text = os.fsdecode(path)
        if not os.path.isabs(text) and dir_fd is not None and dir_fd != -1:
            text = os.path.join(os.readlink('/proc/self/fd/%d' % dir_fd), text)
        target = Path(text).resolve()
        if not any(root == target or root in target.parents for root in state['roots']):
            return
        files = [target] if target.is_file() else [q for q in target.rglob('*') if q.is_file()] if target.is_dir() else []
        for item in files:
            if state['leaks'].in_bytes(item.read_bytes()):
                state['found'].append(item.name)
    except OSError:
        state['unresolved'].append(repr(path))  # a removal that could not be inspected fails the route


def _audit(event, args):
    if event == 'open' and _WATCH['terminal'] is not None:
        path = args[0]
        if isinstance(path, (str, bytes, os.PathLike)):
            text = os.fsdecode(path)
            if text.startswith(('/dev/tty', '/dev/pts/', '/dev/console')) or text.upper() in ('CON', 'CONOUT$', 'CONIN$'):
                _WATCH['terminal'].append(text)
    elif event in ('os.system', 'os.posix_spawn', 'os.exec') and _WATCH['launch'] is not None:
        _WATCH['launch'].append((event, repr(args)))
    elif event in ('os.remove', 'shutil.rmtree') and _WATCH['deleted'] is not None and isinstance(
            args[0], (str, bytes, os.PathLike)):
        _scan_before_removal(args[0], args[1] if len(args) > 1 else None)


sys.addaudithook(_audit)


class Leaks:
    """Finds a canary in text, files, argv lists and environments, in the transformations forms() enumerates."""

    def __init__(self, *values):
        self.values = values

    def in_bytes(self, data):
        return [(i, name) for i, value in enumerate(self.values) for name, form in forms(value).items() if form in data]

    def in_tree(self, root):
        found = []
        for path in sorted(Path(root).rglob('*')):
            if path.is_file():
                for hit in self.in_bytes(path.read_bytes()):
                    found.append((str(path.relative_to(root)),) + hit)
        return found


class RedactionHarness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / 'work'
        self.work.mkdir()
        # Inputs that legitimately hold a canary (secret files, evidence files) live outside the scanned tree.
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        self.tmpbox = self.root / 'tmpbox'
        self.tmpbox.mkdir()

    @staticmethod
    def snapshot(directory, skip):
        """Every file under directory (recursively, nested directories included) with its mtime and size."""
        found = {}
        for base, dirs, files in os.walk(directory, onerror=lambda error: None):
            dirs[:] = [d for d in dirs if skip is None or Path(base, d) != skip]
            for name in files:
                path = Path(base, name)
                try:
                    info = path.lstat()
                    found[path] = (info.st_mtime_ns, info.st_size)
                except OSError:
                    pass  # another process removed it between listing and stat
        return found

    @staticmethod
    def inheritable_leaks(leaks):
        """Descriptors this process holds that a child would inherit and whose content holds a canary."""
        hits = []
        for name in os.listdir('/proc/self/fd'):
            fd = int(name)
            try:
                if fd > 2 and os.get_inheritable(fd) and stat.S_ISREG(os.fstat(fd).st_mode):
                    if leaks.in_bytes(os.pread(fd, 1 << 20, 0)):
                        hits.append(fd)
            except OSError:
                pass  # closed since it was listed, or not readable
        return hits

    @staticmethod
    def descriptor_open_and_inheritable(fd):
        try:
            return os.get_inheritable(fd)
        except OSError:
            return False  # closed (the command consumed and closed it)

    @staticmethod
    def parse_requests(stream):
        """Split one connection's client-to-server bytes into complete parsed requests, in order.

        Each request is (method, target, headers, body): every header occurrence in order, and the body read to its
        declared Content-Length. Bytes that are not part of a parsed request (a partial request, a response, a raw write)
        are returned as leftover and are scanned whole. A request-shaped body is inside its outer request's body.
        """
        requests, leftover, position = [], b"", 0
        while position < len(stream):
            end = stream.find(b"\r\n\r\n", position)
            head = stream[position:end] if end >= 0 else b""
            lines = head.split(b"\r\n")
            first = lines[0].split(b" ")
            if end < 0 or len(first) != 3 or not first[2].startswith(b"HTTP/") or not first[0].isalpha():  # not even request-shaped
                leftover += stream[position:]
                break
            headers = []
            syntax_ok = first[2] == b"HTTP/1.1" and _TOKEN.fullmatch(first[0]) is not None  # the version http.client emits
            for line in lines[1:]:
                name, colon, value = line.partition(b":")
                if not colon or _TOKEN.fullmatch(name) is None:
                    syntax_ok = False  # no colon, or a field name that is not an HTTP token (no surrounding whitespace)
                headers.append((name, value.strip(b" \t")) if colon else (line, None))
            length = 0
            for name, value in headers:
                if name.lower() == b"content-length" and value is not None and value.isdigit():
                    length = int(value)
            body_start = end + 4
            if len(stream) < body_start + length:
                # A partial request (its body is shorter than its Content-Length) is not complete: no exemption.
                leftover += stream[position:]
                break
            if not syntax_ok or any(line[:1] in (b" ", b"\t") for line in lines[1:]):
                # Malformed syntax, or an obsolete folded continuation that can change a header's value: no exemption.
                leftover += stream[position:body_start + length]
            else:
                requests.append((first[0].decode(), first[1].decode("latin-1"), headers,
                                 stream[body_start:body_start + length]))
            position = body_start + length
        return requests, leftover

    @classmethod
    def socket_scan_text(cls, wire, allowed):
        """The bytes to scan for canaries: everything sent on every socket except exactly one permitted header value.

        allowed maps a canary to the (method, path) route that declares it. A canary is permitted only as exactly one
        Authorization header whose value is exactly `Bearer <canary>` on that route. Every other header occurrence
        (a second Authorization header included), the target, the body and any unparsed write are kept whole.
        """
        streams = {}
        for owner, data in wire:
            streams[owner] = streams.get(owner, b"") + data
        kept = []
        for stream in streams.values():
            requests, leftover = cls.parse_requests(stream)
            kept.append(leftover)
            for method, target, headers, body in requests:
                authorizations = [i for i, (name, _) in enumerate(headers) if name.lower() == b"authorization"]
                permitted = None
                if len(authorizations) == 1:
                    value = headers[authorizations[0]][1]
                    for canary_value, route in allowed.items():
                        if value == b"Bearer " + canary_value.encode() and (method, target) == tuple(route):
                            permitted = authorizations[0]
                kept.append(method.encode() + b" " + target.encode("latin-1"))
                kept.extend(b": ".join([name, value if value is not None else b""])
                            for i, (name, value) in enumerate(headers) if i != permitted)
                kept.append(body)
        return b"\n".join(kept)

    def run_cli(self, argv, canaries, env=None, expect=0, outputs=(), bearer_ok=None, entry=None, fds=()):
        """Run cli.main (or entry) in process with the work root as the working directory.

        Returns (exit code, stdout, stderr, children). The call must exit with `expect`. Channels observed, each shown
        non-vacuous by a planted-leak test below (fds: the credential descriptors the test supplied, of any type; none may
        be passed to a child or be inheritable at a child start or at the end of the call): stdout, stderr, the text of an uncaught exception, every file under
        the work root and under each declared output root (recursively), every new or changed file anywhere under the
        system temporary directory (recursively), each child's argv, environment, pass_fds and close_fds, every
        inheritable descriptor holding a canary (when a child starts and when the call ends), opens of a terminal
        device, bytes sent on a socket (a canary may appear only as the exact parsed Authorization header value
        `Bearer <canary>`, exactly one such header, on the (method, path) route bearer_ok declares for that canary; every
        other header occurrence, the target, the body and any unparsed write are scanned whole), and
        the parent environment, which must be exactly the baseline plus the declared route variables.
        """
        env = env or {}
        bearer_ok = bearer_ok or {}
        leaks = Leaks(*canaries)
        baseline = dict(os.environ)
        children, terminal, wire, inherited = [], [], [], []
        stdin_data, launches, deleted, unresolved = [], [], [], []
        child_stdin_fds = set()
        real_os_write = os.write
        allowed_routes = dict(bearer_ok)
        real_popen = subprocess.Popen
        real_send, real_sendall = socket.socket.send, socket.socket.sendall

        connections = ConnectionRegistry()

        def watching_send(self_, data, *a):
            wire.append((connections.key(self_), bytes(data)))
            return real_send(self_, data, *a)

        def watching_sendall(self_, data, *a):
            wire.append((connections.key(self_), bytes(data)))
            return real_sendall(self_, data, *a)

        class StdinProxy:
            """Wraps a child's stdin pipe so every write is recorded; everything else passes through."""

            def __init__(self, stream):
                self.__dict__['stream'] = stream
                self.__dict__['number'] = stream.fileno()
                child_stdin_fds.add(self.number)

            def close(self):
                child_stdin_fds.discard(self.number)  # the number may be reused once closed
                return self.stream.close()

            def write(self, data):
                stdin_data.append(data if isinstance(data, bytes) else str(data).encode())
                return self.stream.write(data)

            def __getattr__(self, name):
                return getattr(self.stream, name)

        class Recording(real_popen):
            def communicate(self, input=None, timeout=None):
                if input is not None:
                    stdin_data.append(input if isinstance(input, bytes) else str(input).encode())
                return super().communicate(input, timeout)

            def __init__(self, args, *a, **k):
                supplied = k.get('stdin')
                if supplied is not None and supplied not in (subprocess.PIPE, subprocess.DEVNULL):
                    # A file object (or descriptor number) given as stdin: read its content without moving its position.
                    try:
                        number = supplied if isinstance(supplied, int) else supplied.fileno()
                        stdin_data.append(os.pread(number, 1 << 20, 0))
                    except (OSError, AttributeError, ValueError):
                        pass  # a pipe or a non-seekable object cannot be read ahead
                passed = list(k.get('pass_fds') or ())
                children.append({'argv': [str(x) for x in args] if isinstance(args, (list, tuple)) else [str(args)],
                                 'env': dict(k.get('env') or os.environ), 'pass_fds': passed,
                                 'close_fds': k.get('close_fds', True)})
                for fd in passed:
                    try:
                        if leaks.in_bytes(os.pread(fd, 1 << 20, 0)):
                            inherited.append(fd)
                    except OSError:
                        pass
                inherited.extend(RedactionHarness.inheritable_leaks(leaks))
                inherited.extend(fd for fd in fds if fd in passed or RedactionHarness.descriptor_open_and_inheritable(fd))
                super().__init__(args, *a, **k)
                if self.stdin is not None:
                    self.stdin = StdinProxy(self.stdin)

        # The system temporary directory for this call is a sandbox (TMPDIR and tempfile.tempdir point at it), so
        # every file the command creates there, nested or not, is seen by a recursive snapshot.
        system_tmp = self.tmpbox
        before_tmp = self.snapshot(system_tmp, skip=None)
        out, err = io.StringIO(), io.StringIO()
        uncaught = None
        previous = os.getcwd()
        os.chdir(self.work)
        # Descriptors 1 and 2 are captured at the descriptor level too: a write straight to the descriptor never
        # passes through sys.stdout. The originals are saved with os.dup and restored afterwards.
        fd_files = {number: tempfile.TemporaryFile() for number in (1, 2)}
        saved = {number: os.dup(number) for number in (1, 2)}
        try:
            for number, handle in fd_files.items():
                os.dup2(handle.fileno(), number)
            def watching_write(fd, data):
                if fd in child_stdin_fds:
                    stdin_data.append(bytes(data))
                return real_os_write(fd, data)

            os.write = watching_write
            _WATCH['terminal'] = terminal
            _WATCH['launch'] = launches
            _WATCH['deleted'] = {'leaks': leaks, 'roots': [self.work.resolve(), system_tmp.resolve(),
                                                           *[Path(o).resolve() for o in outputs]], 'found': deleted,
                                 'unresolved': unresolved}
            with patch('subprocess.Popen', Recording), patch.dict(os.environ, {**env, 'TMPDIR': str(system_tmp)}), \
                    patch.object(tempfile, 'tempdir', str(system_tmp)), \
                    patch.object(socket.socket, 'send', watching_send), patch.object(socket.socket, 'sendall', watching_sendall):
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        code = (entry or cli.main)(argv)
                    except BaseException:
                        uncaught = traceback.format_exc()
                        code = None
                after = dict(os.environ)
                inherited.extend(self.inheritable_leaks(leaks))
                inherited.extend(fd for fd in fds if self.descriptor_open_and_inheritable(fd))
        finally:
            os.write = real_os_write
            _WATCH['terminal'] = _WATCH['launch'] = _WATCH['deleted'] = None
            for number in (1, 2):
                os.dup2(saved[number], number)
                os.close(saved[number])
            os.chdir(previous)
        fd_output = {}
        for number, handle in fd_files.items():
            handle.seek(0)
            fd_output[number] = handle.read()
            handle.close()
        # TMPDIR is the harness's own sandbox variable; every other variable must be the baseline plus the route's own.
        self.assertEqual({k: v for k, v in after.items() if k != 'TMPDIR'},
                         {k: v for k, v in {**baseline, **env}.items() if k != 'TMPDIR'},
                         'the command changed the parent environment')
        if uncaught is not None:
            self.assertEqual(leaks.in_bytes(uncaught.encode()), [], 'canary in an uncaught exception')
            self.fail('uncaught exception: ' + uncaught.splitlines()[-1])
        for number, data in fd_output.items():
            self.assertEqual(leaks.in_bytes(data), [], 'canary written to file descriptor %d' % number)
        self.assert_clean(canaries, out.getvalue(), err.getvalue(), children)
        self.assertEqual(deleted, [], 'a file held a canary before it was removed')
        self.assertEqual(unresolved, [], 'a removal could not be resolved and so could not be inspected')
        self.assertEqual(leaks.in_bytes(b''.join(stdin_data)), [], 'canary sent to a child process stdin')
        self.assertEqual([event for event, _ in launches if leaks.in_bytes(repr(_).encode())], [],
                         'canary in the arguments of a launch API')
        self.assertEqual(launches, [], 'a launch API (os.system, posix_spawn or exec) was used; routes declare none')
        for root in outputs:
            self.assertEqual(leaks.in_tree(root), [], 'canary under a declared output root')
        self.assertEqual(terminal, [], 'the command opened a terminal device')
        self.assertEqual(inherited, [], 'a canary-bearing or supplied credential descriptor was passed to a child or '
                                        'left inheritable')
        sent = self.socket_scan_text(wire, allowed_routes)
        self.assertEqual(leaks.in_bytes(sent), [], 'canary written to a socket')
        after_tmp = self.snapshot(system_tmp, skip=None)
        for path, stamp in after_tmp.items():
            if before_tmp.get(path) != stamp:
                try:
                    data = path.read_bytes()
                except OSError:
                    continue  # removed again by the command itself
                self.assertEqual(leaks.in_bytes(data), [], 'canary in a system temporary file')
        self.assertEqual(code, expect, 'unexpected exit code; stdout: ' + out.getvalue()[:600])
        return code, out.getvalue(), err.getvalue(), children

    def assert_clean(self, canaries, out, err, children, tree=None):
        leaks = Leaks(*canaries)
        self.assertEqual(leaks.in_bytes(out.encode()), [], 'canary on stdout')
        self.assertEqual(leaks.in_bytes(err.encode()), [], 'canary on stderr')
        self.assertEqual(leaks.in_bytes(json.dumps(children, sort_keys=True).encode()), [],
                         'canary in a child process argv or environment')
        self.assertEqual(leaks.in_tree(tree or self.work), [], 'canary in a file the command wrote')

    # planted leaks: each channel is shown to fire, so a clean result elsewhere means something ----------------

    def planted(self, entry, pattern, **kwargs):
        value = canary('planted')
        with self.assertRaisesRegex(AssertionError, pattern):
            self.run_cli([], (value,), entry=lambda argv: entry(value), **kwargs)

    def test_planted_leaks_are_each_caught(self):
        def to_stdout(v):
            print(v)
            return 0

        def to_exception(v):
            raise RuntimeError('failed with ' + v)

        def to_file(v):
            Path('leak.txt').write_text(v)
            return 0

        declared = self.root / 'declared'
        declared.mkdir()

        def to_declared_root(v):
            (declared / 'deep').mkdir()
            (declared / 'deep' / 'out.txt').write_text(v)
            return 0

        nested = self.tmpbox / 'pre-existing'
        (nested / 'deep').mkdir(parents=True)

        def to_nested_temp(v):
            (nested / 'deep' / 'leak.txt').write_text(v)
            return 0

        def to_terminal(v):
            try:
                os.close(os.open('/dev/tty', os.O_WRONLY))
            except OSError:
                pass  # no controlling terminal here; the attempt is what is observed
            return 0

        def to_socket(v):
            left, right = socket.socketpair()
            with left, right:
                left.sendall(('payload=' + v).encode())
            return 0

        def to_child_argument(v):
            subprocess.run(['true', v])
            return 0

        def to_child_environment(v):
            subprocess.run(['true'], env={'SECRET': v})
            return 0

        def to_passed_descriptor(v):
            handle = tempfile.TemporaryFile()
            handle.write(v.encode())
            handle.flush()
            subprocess.run(['true'], pass_fds=(handle.fileno(),))
            handle.close()
            return 0

        def left_inheritable(v):
            handle = tempfile.TemporaryFile()
            handle.write(v.encode())
            handle.flush()
            os.set_inheritable(handle.fileno(), True)
            self.addCleanup(handle.close)
            return 0

        read_end, write_end = os.pipe()
        self.addCleanup(close_if_open, read_end)
        self.addCleanup(close_if_open, write_end)
        fifo = self.tmpbox / 'credential.fifo'
        os.mkfifo(fifo)
        fifo_fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        self.addCleanup(close_if_open, fifo_fd)

        def pipe_passed(v):
            os.set_inheritable(read_end, True)
            subprocess.run(['true'], pass_fds=(read_end,))
            os.set_inheritable(read_end, False)
            return 0

        def fifo_left_inheritable(v):
            os.set_inheritable(fifo_fd, True)
            return 0

        def to_environment(v):
            os.environ['PERSISTED'] = v
            return 0

        for name, entry, pattern, kwargs in (
                ('stdout', to_stdout, 'canary on stdout', {}),
                ('uncaught exception', to_exception, 'uncaught exception', {}),
                ('work file', to_file, 'file the command wrote', {}),
                ('declared output root', to_declared_root, 'declared output root', {'outputs': [declared]}),
                ('nested temporary file', to_nested_temp, 'system temporary file', {}),
                ('terminal device', to_terminal, 'terminal device', {}),
                ('socket', to_socket, 'written to a socket', {}),
                ('child argument', to_child_argument, 'child process argv', {}),
                ('child environment', to_child_environment, 'child process argv or environment', {}),
                ('passed descriptor', to_passed_descriptor, 'credential descriptor', {}),
                ('left inheritable', left_inheritable, 'credential descriptor', {}),
                ('supplied pipe passed to a child', pipe_passed, 'credential descriptor', {'fds': (read_end,)}),
                ('supplied FIFO left inheritable', fifo_left_inheritable, 'credential descriptor', {'fds': (fifo_fd,)}),
                ('parent environment', to_environment, 'parent environment', {})):
            with self.subTest(channel=name):
                os.environ.pop('PERSISTED', None)
                self.planted(entry, pattern, **kwargs)
                os.environ.pop('PERSISTED', None)

    def test_only_one_parsed_authorization_header_on_the_declared_route_may_carry_a_bearer_canary(self):
        key = canary('wire')
        route = ('POST', '/v1/systemone')
        bearer = ('Bearer ' + key).encode()

        def request(headers=(), body=b'', path=b'/v1/systemone', declare_length=True):
            lines = [b'POST ' + path + b' HTTP/1.1', b'Host: localhost', *headers]
            if declare_length:
                lines.append(b'Content-Length: ' + str(len(body)).encode())
            return b'\r\n'.join(lines) + b'\r\n\r\n' + body

        def sender(*writes):
            def entry(argv):
                left, right = socket.socketpair()
                with left, right:
                    for data in writes:
                        left.sendall(data)
                return 0
            return entry

        good = request([b'Authorization: ' + bearer], b'{"state":"fine"}')
        self.run_cli([], (key,), entry=sender(good), bearer_ok={key: route})
        self.run_cli([], (key,), entry=sender(good[:20], good[20:]), bearer_ok={key: route})  # split across writes
        nested_head = request([b'Authorization: ' + bearer], b'')
        nested_body = b'POST /unrelated HTTP/1.1\r\nAuthorization: ' + bearer + b'\r\n\r\n'
        for name, writes, allowed in (
                ('undeclared canary', (good,), {}),
                ('duplicate Authorization header on the declared route',
                 (request([b'Authorization: ' + bearer, b'Authorization: ' + bearer]),), {key: route}),
                ('request-shaped body inside an outer request body',
                 (request([b'Authorization: ' + bearer], nested_body),), {key: route}),
                ('request-shaped second request on an undeclared route',
                 (request([]), nested_body), {key: route}),
                ('Authorization header on an undeclared route',
                 (request([b'Authorization: ' + bearer], path=b'/other'),), {key: route}),
                ('folded continuation after the authorization value',
                 (b'POST /v1/systemone HTTP/1.1\r\nauthorization: Bearer ' + key.encode() + b'\r\n extra\r\n'
                  b'Content-Length: 0\r\n\r\n',), {key: route}),
                ('tab continuation after the authorization value',
                 (b'POST /v1/systemone HTTP/1.1\r\nAuthorization: Bearer ' + key.encode() + b'\r\n\textra\r\n'
                  b'Content-Length: 0\r\n\r\n',), {key: route}),
                ('body shorter than Content-Length',
                 (b'POST /v1/systemone HTTP/1.1\r\nAuthorization: Bearer ' + key.encode() + b'\r\n'
                  b'Content-Length: 1\r\n\r\n',), {key: route}),
                ('unsupported HTTP version',
                 (b'POST /v1/systemone HTTP/not-http\r\nAuthorization: Bearer ' + key.encode() + b'\r\n'
                  b'Content-Length: 0\r\n\r\n',), {key: route}),
                ('HTTP/1.0 is not emitted by the client',
                 (b'POST /v1/systemone HTTP/1.0\r\nAuthorization: Bearer ' + key.encode() + b'\r\n'
                  b'Content-Length: 0\r\n\r\n',), {key: route}),
                ('whitespace before the colon of a field name',
                 (b'POST /v1/systemone HTTP/1.1\r\nAuthorization : Bearer ' + key.encode() + b'\r\n'
                  b'Content-Length: 0\r\n\r\n',), {key: route}),
                ('declared path but another method',
                 (good.replace(b'POST', b'PUT', 1),), {key: route}),
                ('payload in a body', (request([b'Authorization: ' + bearer], b'payload=' + bearer),), {key: route}),
                ('another header', (request([b'Authorization: ' + bearer, b'X-Forwarded: ' + bearer]),), {key: route}),
                ('a different scheme in the header', (request([b'Authorization: Basic ' + key.encode()]),), {key: route}),
                ('a suffix after the value', (request([b'Authorization: ' + bearer + b'x']),), {key: route}),
                ('not a request head', (b'Authorization: ' + bearer,), {key: route}),
                ('in the target', (request([], path=b'/v1/systemone?t=' + key.encode()),), {key: route}),
                ('a raw write beside a good request', (good, b'leak=' + key.encode()), {key: route})):
            with self.subTest(name):
                with self.assertRaisesRegex(AssertionError, 'written to a socket'):
                    self.run_cli([], (key,), entry=sender(*writes), bearer_ok=allowed)

    def test_the_connection_registry_never_merges_two_owners(self):
        class Same:
            def __eq__(self, other):
                return True

            def __hash__(self):
                return 1

        first, second = Same(), Same()
        registry = ConnectionRegistry()
        self.assertEqual((registry.key(first), registry.key(second), registry.key(first)), (0, 1, 0))
        self.assertIs(registry.objects[0], first)  # a strong reference is held, so no id can be reused

    def test_a_request_split_over_two_connections_is_not_reassembled_into_an_exempt_one(self):
        key = canary('conn')
        route = ('POST', '/v1/systemone')
        head = b'POST /v1/systemone HTTP/1.1\r\nAuthorization: Bearer ' + key.encode() + b'\r\n'
        tail = b'Content-Length: 0\r\n\r\n'

        def two_sockets(argv):
            import gc
            first_left, first_right = socket.socketpair()
            first_left.sendall(head)
            first_left.close()
            first_right.close()
            del first_left, first_right
            gc.collect()
            second_left, second_right = socket.socketpair()
            second_left.sendall(tail)
            second_left.close()
            second_right.close()
            return 0

        with self.assertRaisesRegex(AssertionError, 'written to a socket'):
            self.run_cli([], (key,), entry=two_sockets, bearer_ok={key: route})

    def test_planted_encodings_are_each_caught(self):
        def std(v, lead=b'', tail=b''):
            return base64.b64encode(lead + v.encode() + tail).decode()

        def url(v, lead=b'', tail=b''):
            return base64.urlsafe_b64encode(lead + v.encode() + tail).decode()

        transforms = {
            'hex upper': lambda v: v.encode().hex().upper(),
            'percent upper': lambda v: ''.join('%{:02X}'.format(b) for b in v.encode()),
            'percent lower': lambda v: ''.join('%{:02x}'.format(b) for b in v.encode()),
            'base64 padded': std, 'base64 unpadded': lambda v: std(v).rstrip('='),
            'urlsafe padded': url, 'urlsafe unpadded': lambda v: url(v).rstrip('='),
            'embedded base64, alignment 1': lambda v: std(v, b'x', b'yyyy'),
            'embedded base64, alignment 2': lambda v: std(v, b'xx', b'yyyyy'),
            'embedded urlsafe, alignment 1': lambda v: url(v, b'x', b'yyyy'),
        }
        for name, transform in transforms.items():
            def to_file(v, transform=transform):
                Path('leak.txt').write_text(transform(v))
                return 0

            with self.subTest(form=name):
                self.planted(to_file, 'file the command wrote')

    def test_planted_descriptor_output_and_transient_files_are_caught(self):
        def to_fd1(v):
            os.write(1, v.encode())
            return 0

        def to_fd2(v):
            os.write(2, v.encode())
            return 0

        def written_and_deleted(v):
            path = Path('transient.txt')
            path.write_text(v)
            path.unlink()
            return 0

        def tree_written_and_removed(v):
            Path('scratch').mkdir()
            (Path('scratch') / 'deep.txt').write_text(v)
            shutil.rmtree('scratch')
            return 0

        def temporary_written_and_deleted(v):
            path = Path(tempfile.gettempdir()) / 'transient.tmp'
            path.write_text(v)
            os.remove(path)
            return 0

        def removed_with_dir_fd(v):
            Path('nested').mkdir()
            (Path('nested') / 'leak.txt').write_text(v)
            directory_fd = os.open('nested', os.O_RDONLY)
            try:
                os.remove('leak.txt', dir_fd=directory_fd)
            finally:
                os.close(directory_fd)
            return 0

        def tree_removed_with_dir_fd(v):
            (Path('outer') / 'inner').mkdir(parents=True)
            (Path('outer') / 'inner' / 'leak.txt').write_text(v)
            directory_fd = os.open('outer', os.O_RDONLY)
            try:
                shutil.rmtree('inner', dir_fd=directory_fd)
            finally:
                os.close(directory_fd)
            return 0

        for name, entry, pattern in (('removed with dir_fd', removed_with_dir_fd, 'before it was removed'),
                                     ('rmtree with dir_fd', tree_removed_with_dir_fd, 'before it was removed'),
                                     ('fd 1', to_fd1, 'file descriptor 1'), ('fd 2', to_fd2, 'file descriptor 2'),
                                     ('deleted work file', written_and_deleted, 'before it was removed'),
                                     ('removed tree', tree_written_and_removed, 'before it was removed'),
                                     ('deleted temporary file', temporary_written_and_deleted, 'before it was removed')):
            with self.subTest(channel=name):
                self.planted(entry, pattern)

    def test_planted_child_stdin_and_other_launch_apis_are_caught(self):
        def communicate_input(v):
            subprocess.run(['cat'], input=v.encode(), stdout=subprocess.DEVNULL)
            return 0

        def stdin_pipe_write(v):
            child = subprocess.Popen(['cat'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
            child.stdin.write(v.encode())
            child.stdin.close()
            child.wait()
            return 0

        def descriptor_write_to_stdin(v):
            child = subprocess.Popen(['cat'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
            os.write(child.stdin.fileno(), v.encode())
            child.stdin.close()
            child.wait()
            return 0

        def stdin_file_object(v):
            with tempfile.TemporaryFile() as handle:
                handle.write(v.encode())
                handle.seek(0)
                subprocess.run(['cat'], stdin=handle, stdout=subprocess.DEVNULL)
            return 0

        def system_call(v):
            # Deliberate: os.system is the launch API this plant exercises; the harness must catch it. Fixed command.
            os.system('true ' + v)
            return 0

        def unneeded_launch(v):
            os.system('true')  # deliberate plant: a launch on a route that declares none
            return 0

        for name, entry, pattern in (('descriptor-level write to stdin', descriptor_write_to_stdin, 'child process stdin'),
                                     ('file object supplied as stdin', stdin_file_object, 'child process stdin'),
                                     ('communicate input', communicate_input, 'child process stdin'),
                                     ('stdin pipe write', stdin_pipe_write, 'child process stdin'),
                                     ('os.system with the canary', system_call, 'launch API'),
                                     ('os.system on a route that declares none', unneeded_launch, 'launch API')):
            with self.subTest(channel=name):
                self.planted(entry, pattern)

    # start and doctor ------------------------------------------------------------------------------------

    def test_start_and_doctor_keep_ambient_and_file_canaries_out(self):
        token, secret = canary('start-env'), canary('start-file')
        # The survey directory holds a file with the canary under keys start does not report. It is outside the scanned
        # tree and must be byte-for-byte unchanged afterwards (start is read-only).
        survey = self.root / 'survey'
        survey.mkdir()
        write_json(survey / 'estate.json', {'schema_version': '1.0.0', 'client_secret': secret, 'note': secret,
                                            'collections': []})
        before = {p.name: p.read_bytes() for p in survey.iterdir()}
        env = {'INTUNE_GRAPH_TOKEN': token, 'INTUNE_MANAGEMENT_TOKEN': token}
        for argv in (['start', str(survey)], ['start', str(survey), '--json'], ['doctor']):
            with self.subTest(argv=argv[0] + ' ' + ' '.join(argv[2:])):
                self.run_cli(argv, (token, secret), env)
                self.assertEqual({p.name: p.read_bytes() for p in survey.iterdir()}, before)

    def test_start_and_doctor_as_real_processes(self):
        token = canary('proc-env')
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'INTUNE_GRAPH_TOKEN': token}
        for argv in (['start', str(self.work), '--json'], ['doctor']):
            result = subprocess.run([sys.executable, '-I', '-B', str(PROJECT / 'scripts/intune-iac.py'), *argv],
                                    cwd=self.work, env=env, capture_output=True, timeout=60)
            self.assertEqual(Leaks(token).in_bytes(result.stdout + result.stderr), [], argv[0])

    # target authenticate (file-descriptor route) ---------------------------------------------------------

    def test_authenticate_file_descriptor_route(self):
        from dataclasses import asdict
        from intune_iac import identity_binding as ib
        from plugin_tests.test_identity_binding_v5 import config, RecordedServices, Clock
        provider, backend = canary('provider'), canary('backend')
        path = self.inputs / 'identity.json'
        write_json(path, asdict(config()))
        files = []
        for name, value in (('provider.secret', provider), ('backend.secret', backend)):
            p = self.inputs / name
            p.write_bytes(value.encode())
            p.chmod(0o600)
            files.append(p)
        descriptors = [os.open(p, os.O_RDONLY) for p in files]

        def laboratory(cfg, **kwargs):
            return ib.bind_laboratory(cfg, **kwargs, transport=RecordedServices(), clock=Clock())

        consumed = []
        try:
            with patch.object(ib, 'bind_live', side_effect=laboratory), \
                    recording_handle(ib.ClientSecretHandle, consumed):
                code, out, _, _ = self.run_cli(['target', 'authenticate', '--input', str(path),
                    '--provider-secret-fd', str(descriptors[0]), '--backend-secret-fd', str(descriptors[1])],
                    (provider, backend), fds=descriptors)
        finally:
            for fd in descriptors:
                close_if_open(fd)
        self.assertEqual(json.loads(out)['assurance'], 'laboratory_recorded_responses')
        self.assertEqual(consumed, [provider, backend], 'each descriptor secret must have reached its handle')

    # capture (token by environment-variable name, local fake service) ------------------------------------

    def test_capture_with_token_environment_name(self):
        token = canary('capture')
        tenant, policy = '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'
        delivered = []

        def factory(value):
            delivered.append(value)

            def get(url, *, timeout):
                if url.endswith('/settings') or url.endswith('/assignments'):
                    body = {'value': []}
                else:
                    body = {'value': [{'id': policy, 'name': 'fake'}]}
                return 200, json.dumps(body).encode(), ()
            return get

        output = self.work / 'captured'
        with patch('intune_iac.capture._http_transport', factory):
            code, out, _, _ = self.run_cli(['capture', '--tenant', tenant, '--policy', policy, '--output', str(output),
                                            '--token-env', 'HARNESS_CAPTURE_TOKEN'], (token,),
                                           {'HARNESS_CAPTURE_TOKEN': token})
        self.assertEqual(delivered, [token], 'the fake service must have been handed the token, or the test proves nothing')
        self.assertTrue((output / 'export.json').is_file())

    # capture and target collect (token from an inherited descriptor; nothing in the parent environment) --------

    def secret_fd(self, value, name):
        path = self.inputs / name
        path.write_bytes(value.encode())
        path.chmod(0o600)
        fd = os.open(path, os.O_RDONLY)
        self.addCleanup(close_if_open, fd)
        return fd

    def test_capture_and_collect_with_descriptor_tokens(self):
        from plugin_tests import test_target as tt
        capture_token, graph, management = canary('fdcapture'), canary('fdgraph'), canary('fdarm')
        tenant, policy = '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'
        delivered = []

        def factory(value):
            delivered.append(value)
            return lambda url, *, timeout: (200, json.dumps(
                {'value': [] if url.endswith(('/settings', '/assignments')) else [{'id': policy}]}).encode(), ())

        with patch('intune_iac.capture._http_transport', factory):
            capture_fd = self.secret_fd(capture_token, 'capture.token')
            self.run_cli(['capture', '--tenant', tenant, '--policy', policy, '--output', str(self.work / 'fdcap'),
                          '--token-fd', str(capture_fd)], (capture_token,), fds=(capture_fd,))
        self.assertEqual(delivered, [capture_token])
        document = self.inputs / 'target-fd.json'
        write_json(document, tt.fixture())
        tt.Connection.responses, tt.Connection.requests = tt.CollectionTests.responses(None), []
        with patch('intune_iac.target._now', return_value=tt.NOW), \
                patch('intune_iac.target.http.client.HTTPSConnection', tt.Connection):
            graph_fd, management_fd = self.secret_fd(graph, 'graph.token'), self.secret_fd(management, 'arm.token')
            code, out, _, _ = self.run_cli(['target', 'collect', '--input', str(document),
                '--graph-token-fd', str(graph_fd), '--management-token-fd', str(management_fd)],
                (graph, management), fds=(graph_fd, management_fd))
        self.assertEqual(json.loads(out)['status'], 'observed')

    # target collect (token by environment-variable name, local fake service) -----------------------------

    def test_target_collect_with_token_environment_names(self):
        from plugin_tests import test_target as tt
        graph, management = canary('graph'), canary('management')
        document = self.inputs / 'target.json'
        write_json(document, tt.fixture())
        responses = tt.CollectionTests.responses(None)
        tt.Connection.responses, tt.Connection.requests = responses, []
        with patch('intune_iac.target._now', return_value=tt.NOW), \
                patch('intune_iac.target.http.client.HTTPSConnection', tt.Connection):
            code, out, _, _ = self.run_cli(['target', 'collect', '--input', str(document),
                                            '--graph-token-env', 'HARNESS_GRAPH', '--management-token-env', 'HARNESS_ARM'],
                                           (graph, management), {'HARNESS_GRAPH': graph, 'HARNESS_ARM': management})
        self.assertEqual(json.loads(out)['status'], 'observed')
        sent = [headers['Authorization'] for _, _, _, headers in tt.Connection.requests]
        self.assertEqual(sent, ['Bearer ' + graph, 'Bearer ' + management, 'Bearer ' + management])

    # scheduled observer job -----------------------------------------------------------------------------

    def test_observer_job_create_scheduler_and_run(self):
        from intune_iac.observation_jobs import create_job, scheduler_artifacts
        from intune_iac.observation_reader import ReaderSpec
        from intune_iac.synthetic import generate_estate
        from intune_iac.workbench_store import WorkbenchStore
        from plugin_tests.test_observation_reader_r4 import CLIENT, PRINCIPAL, fixture_for, TOKEN
        secret = canary('observer')
        estate = generate_estate(seed=846, policy_count=1)
        tenant, oid = estate['truth']['tenant_id'], estate['truth']['policies'][0]['id']
        store = WorkbenchStore.create(self.work / 'store', tenant)
        fixture = self.inputs / 'fixture.json'
        rows = fixture_for(estate)
        issued = canary('issued')
        for row in rows['responses']:
            if isinstance(row['body'], dict) and row['body'].get('access_token') == TOKEN:
                row['body']['access_token'] = issued
        write_json(fixture, rows)
        job = self.work / 'job'
        created = create_job(store, ReaderSpec(tenant, CLIENT, PRINCIPAL, (oid,)), output=job,
                             secret_env='HARNESS_OBSERVER_SECRET', interval_seconds=60, laboratory_fixture=fixture)
        scheduler_artifacts(job, self.work / 'scheduler')
        state = json.loads((job / 'state.json').read_text())
        state['next_due'] = '2026-01-01T00:00:00Z'
        write_json(job / 'state.json', state)
        import intune_iac.observation_jobs as jobs
        consumed = []
        with recording_handle(jobs.ClientSecretHandle, consumed):
            code, out, _, _ = self.run_cli(['workbench', 'observer-run', '--job', str(job)], (secret, issued),
                                           {'HARNESS_OBSERVER_SECRET': secret})
        self.assertEqual(consumed, [secret], 'the observer must have consumed its environment secret')
        self.assertEqual(json.loads(out)['status'], 'complete')
        self.assertEqual(created['status'], 'created')

    # judge path (local fake endpoint) --------------------------------------------------------------------

    def test_judge_path_never_sends_a_canary_in_evidence_or_the_api_key(self):
        from plugin_tests.test_judge import JudgeTests
        key, leaked = canary('judgekey'), canary('evidence')
        fake = JudgeTests('setUp')
        fake.setUp()
        self.addCleanup(fake.tearDown)
        fake.config['api_key_env'] = 'CLM_HARNESS_KEY'
        config = self.inputs / 'judge-config.json'
        shutil_copy = {'tokenizer.json': fake.tokenizer, 'head.pt': fake.head}
        for name, source in shutil_copy.items():
            (self.inputs / name).write_bytes(source.read_bytes())
        write_json(config, fake.config)
        evidence = self.inputs / 'evidence.json'
        # The canary sits under an innocent key; a key-name scan would not see it.
        write_json(evidence, [{'id': 'record-1', 'text': 'enabled', 'detail': leaked}])
        code, out, _, _ = self.run_cli(['judge', '--config', str(config), '--claim', 'The setting is enabled.',
                                        '--evidence', str(evidence)], (key, leaked), {'CLM_HARNESS_KEY': key},
                                        expect=2)
        bodies = json.dumps([r['body'] for r in fake.requests]).encode()
        self.assertEqual(Leaks(key, leaked).in_bytes(bodies), [], 'canary in the judge request body')
        self.assertEqual(fake.requests, [], 'evidence with a secret-shaped value must not be sent at all')

    def test_judge_path_sends_benign_evidence_with_the_api_key_only_in_the_authorization_header(self):
        from plugin_tests.test_judge import JudgeTests
        key = canary('judgekey')
        fake = JudgeTests('setUp')
        fake.setUp()
        self.addCleanup(fake.tearDown)
        fake.config['api_key_env'] = 'CLM_HARNESS_KEY'
        for name, source in {'tokenizer.json': fake.tokenizer, 'head.pt': fake.head}.items():
            (self.inputs / name).write_bytes(source.read_bytes())
        config = self.inputs / 'judge-config.json'
        write_json(config, fake.config)
        evidence = self.inputs / 'benign.json'
        write_json(evidence, [{'id': 'record-1', 'text': 'enabled'}])
        code, out, _, _ = self.run_cli(['judge', '--config', str(config), '--claim', 'The setting is enabled.',
                                        '--evidence', str(evidence)], (key,), {'CLM_HARNESS_KEY': key},
                                        bearer_ok={key: ('POST', '/v1/systemone')})
        self.assertEqual(len(fake.requests), 1, 'exactly one request must reach the fake endpoint')
        request = fake.requests[0]
        self.assertEqual(request['authorization'], 'Bearer ' + key, 'the key must have been consumed where it belongs')
        self.assertEqual(Leaks(key).in_bytes(json.dumps(request['body']).encode()), [], 'the key reached the body')
        self.assertEqual(json.loads(out)['status'], 'assessed')


if __name__ == '__main__':
    unittest.main()
