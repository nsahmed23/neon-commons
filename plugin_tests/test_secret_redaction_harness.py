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


def forms(value):
    raw = value.encode()
    return {'plain': raw, 'base64': base64.b64encode(raw), 'urlsafe_base64': base64.urlsafe_b64encode(raw),
            'hex': raw.hex().encode(), 'json_escaped': json.dumps(value).encode()[1:-1]}


_WATCH = {'terminal': None}  # list while a command runs, else None


def _audit(event, args):
    if event == 'open' and _WATCH['terminal'] is not None:
        path = args[0]
        if isinstance(path, (str, bytes, os.PathLike)):
            text = os.fsdecode(path)
            if text.startswith(('/dev/tty', '/dev/pts/', '/dev/console')) or text.upper() in ('CON', 'CONOUT$', 'CONIN$'):
                _WATCH['terminal'].append(text)


sys.addaudithook(_audit)


class Leaks:
    """Finds a canary in text, files, argv lists and environments, by every encoding of it."""

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
    def without_authorization_headers(entry, allowed):
        """One socket write with the Authorization header removed when, and only when, it is an HTTP request head whose
        parsed Authorization header is exactly `Bearer <canary>` for a canary the route declares. A body, any other
        header, a URL or a write that is not a request head keeps every byte, so a canary there is a leak."""
        head, separator, rest = entry.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        first = lines[0].split(b" ")
        if not separator or len(first) != 3 or not first[2].startswith(b"HTTP/") or not first[0].isalpha():
            return entry
        kept = []
        for line in lines[1:]:
            name, colon, value = line.partition(b":")
            if colon and name.strip().lower() == b"authorization" and any(
                    value.strip() == b"Bearer " + c.encode() for c in allowed):
                continue
            kept.append(line)
        return b"\r\n".join([lines[0], *kept]) + separator + rest

    def run_cli(self, argv, canaries, env=None, expect=0, outputs=(), bearer_ok=(), entry=None, fds=()):
        """Run cli.main (or entry) in process with the work root as the working directory.

        Returns (exit code, stdout, stderr, children). The call must exit with `expect`. Channels observed, each shown
        non-vacuous by a planted-leak test below (fds: the credential descriptors the test supplied, of any type; none may
        be passed to a child or be inheritable at a child start or at the end of the call): stdout, stderr, the text of an uncaught exception, every file under
        the work root and under each declared output root (recursively), every new or changed file anywhere under the
        system temporary directory (recursively), each child's argv, environment, pass_fds and close_fds, every
        inheritable descriptor holding a canary (when a child starts and when the call ends), opens of a terminal
        device, bytes sent on a socket (a canary may appear only as the exact parsed Authorization header value
        `Bearer <canary>` of an HTTP request head, for canaries in bearer_ok), and
        the parent environment, which must be exactly the baseline plus the declared route variables.
        """
        env = env or {}
        leaks = Leaks(*canaries)
        baseline = dict(os.environ)
        children, terminal, wire, inherited = [], [], [], []
        real_popen = subprocess.Popen
        real_send, real_sendall = socket.socket.send, socket.socket.sendall

        def watching_send(self_, data, *a):
            wire.append(bytes(data))
            return real_send(self_, data, *a)

        def watching_sendall(self_, data, *a):
            wire.append(bytes(data))
            return real_sendall(self_, data, *a)

        class Recording(real_popen):
            def __init__(self, args, *a, **k):
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

        # The system temporary directory for this call is a sandbox (TMPDIR and tempfile.tempdir point at it), so
        # every file the command creates there, nested or not, is seen by a recursive snapshot.
        system_tmp = self.tmpbox
        before_tmp = self.snapshot(system_tmp, skip=None)
        out, err = io.StringIO(), io.StringIO()
        uncaught = None
        previous = os.getcwd()
        os.chdir(self.work)
        try:
            _WATCH['terminal'] = terminal
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
            _WATCH['terminal'] = None
            os.chdir(previous)
        # TMPDIR is the harness's own sandbox variable; every other variable must be the baseline plus the route's own.
        self.assertEqual({k: v for k, v in after.items() if k != 'TMPDIR'},
                         {k: v for k, v in {**baseline, **env}.items() if k != 'TMPDIR'},
                         'the command changed the parent environment')
        if uncaught is not None:
            self.assertEqual(leaks.in_bytes(uncaught.encode()), [], 'canary in an uncaught exception')
            self.fail('uncaught exception: ' + uncaught.splitlines()[-1])
        self.assert_clean(canaries, out.getvalue(), err.getvalue(), children)
        for root in outputs:
            self.assertEqual(leaks.in_tree(root), [], 'canary under a declared output root')
        self.assertEqual(terminal, [], 'the command opened a terminal device')
        self.assertEqual(inherited, [], 'a canary-bearing or supplied credential descriptor was passed to a child or '
                                        'left inheritable')
        sent = b'\n'.join(self.without_authorization_headers(entry_bytes, bearer_ok) for entry_bytes in wire)
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

    def test_only_a_parsed_authorization_header_may_carry_a_declared_bearer_canary(self):
        key = canary('wire')

        def request(headers=(), body=b''):
            head = b'POST /v1/systemone HTTP/1.1\r\nHost: localhost\r\n' + b''.join(h + b'\r\n' for h in headers) + b'\r\n'
            return head, body

        def sender(*writes):
            def entry(argv):
                left, right = socket.socketpair()
                with left, right:
                    for data in writes:
                        left.sendall(data)
                return 0
            return entry

        bearer = ('Bearer ' + key).encode()
        good_head, good_body = request([b'Authorization: ' + bearer], b'{"state":"fine"}')
        self.run_cli([], (key,), entry=sender(good_head, good_body), bearer_ok=(key,))
        for name, writes in (
                ('undeclared canary', (good_head, good_body)),
                ('payload in a body', (request([b'Authorization: ' + bearer])[0], b'payload=' + bearer)),
                ('another header', (request([b'Authorization: ' + bearer, b'X-Forwarded: ' + bearer])[0], good_body)),
                ('a different scheme in the header', (request([b'Authorization: Basic ' + key.encode()])[0], good_body)),
                ('a suffix after the value', (request([b'Authorization: ' + bearer + b'x'])[0], good_body)),
                ('not a request head', (b'Authorization: ' + bearer,)),
                ('in the url', (b'GET /?t=' + bearer.replace(b' ', b'%20') + b' HTTP/1.1\r\n\r\n',))):
            with self.subTest(name):
                allowed = () if name == 'undeclared canary' else (key,)
                if name == 'in the url':
                    # the percent-encoded form is a different byte string; the plain one is the leak
                    writes = (b'GET /?t=' + key.encode() + b' HTTP/1.1\r\n\r\n',)
                with self.assertRaisesRegex(AssertionError, 'written to a socket'):
                    self.run_cli([], (key,), entry=sender(*writes), bearer_ok=allowed)

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
                                        bearer_ok=(key,))
        self.assertEqual(len(fake.requests), 1, 'exactly one request must reach the fake endpoint')
        request = fake.requests[0]
        self.assertEqual(request['authorization'], 'Bearer ' + key, 'the key must have been consumed where it belongs')
        self.assertEqual(Leaks(key).in_bytes(json.dumps(request['body']).encode()), [], 'the key reached the body')
        self.assertEqual(json.loads(out)['status'], 'assessed')


if __name__ == '__main__':
    unittest.main()
