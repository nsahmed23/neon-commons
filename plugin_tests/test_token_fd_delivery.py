"""capture and target collect take a read token from an inherited file descriptor, with target authenticate's rules.

No flag takes the token value. The environment-variable-name route stays; the file-descriptor route keeps the token
out of the parent session (its environment, its history and its process listing).
"""
import contextlib
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import cli, provider_journey as pj
from intune_iac.io import AppError

TENANT = '11111111-1111-4111-8111-111111111111'
POLICY = '22222222-2222-4222-8222-222222222222'


def canary(label):
    return label + '-' + secrets.token_urlsafe(30) + 'A1'


class Descriptors(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.opened = []
        self.identities = {}
        self.addCleanup(self.close_leftovers)

    def close_leftovers(self):
        # The CLI closes the descriptor it consumed, and its number may be reused; close only what is still ours.
        for fd, identity in self.identities.items():
            try:
                info = os.fstat(fd)
            except OSError:
                continue
            if (info.st_dev, info.st_ino) == identity:
                os.close(fd)

    def secret_fd(self, content, name='token', mode=0o600):
        path = self.root / name
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        path.chmod(mode)
        fd = os.open(path, os.O_RDONLY)
        self.opened.append(fd)
        info = os.fstat(fd)
        self.identities[fd] = (info.st_dev, info.st_ino)
        return fd

    def main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()


class FlagsTests(Descriptors):
    def test_no_flag_takes_a_token_value_and_the_help_names_the_private_route(self):
        for argv in (['capture', '--tenant', TENANT, '--policy', POLICY, '--output', 'x', '--token', 'v'],
                     ['capture', '--tenant', TENANT, '--policy', POLICY, '--output', 'x', '--token-value', 'v'],
                     ['target', 'collect', '--input', 'x', '--graph-token', 'v'],
                     ['target', 'collect', '--input', 'x', '--management-token', 'v']):
            with self.subTest(argv=argv[-2]), patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit):
                cli.parser().parse_args(argv)
        parser = cli.parser()
        for argv in (['capture', '--help'], ['target', 'collect', '--help']):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                parser.parse_args(argv)
            text = ' '.join(out.getvalue().split())
            with self.subTest(argv=argv[0] + ' ' + argv[1]):
                self.assertIn('-fd', text)
                self.assertIn('keeps the token out of the parent session', text)
                self.assertIn('environment', text)

    def test_the_new_flags_parse_as_integers(self):
        args = cli.parser().parse_args(['capture', '--tenant', TENANT, '--policy', POLICY, '--output', 'x',
                                        '--token-fd', '7'])
        self.assertEqual(args.token_fd, 7)
        args = cli.parser().parse_args(['target', 'collect', '--input', 'x', '--graph-token-fd', '8',
                                        '--management-token-fd', '9'])
        self.assertEqual((args.graph_token_fd, args.management_token_fd), (8, 9))


class CaptureFdTests(Descriptors):
    def fake(self, delivered):
        def factory(value):
            delivered.append(value)

            def get(url, *, timeout):
                body = {'value': [] if url.endswith(('/settings', '/assignments')) else [{'id': POLICY}]}
                return 200, json.dumps(body).encode(), ()
            return get
        return factory

    def run_capture(self, fd, extra_env=None, name='out'):
        delivered = []
        output = self.root / name
        with patch('intune_iac.capture._http_transport', self.fake(delivered)), \
                patch.dict(os.environ, extra_env or {}), patch.object(pj, 'read_credential_fd', wraps=pj.read_credential_fd) as spy:
            result = self.main(['capture', '--tenant', TENANT, '--policy', POLICY, '--output', str(output),
                                '--token-fd', str(fd)])
        return result, delivered, output, spy

    def test_token_arrives_from_the_descriptor_through_the_shared_reader_and_env_is_not_read(self):
        token, ambient = canary('fd'), canary('ambient')
        fd = self.secret_fd(token + '\n')
        (code, out, err), delivered, output, spy = self.run_capture(fd, {'INTUNE_GRAPH_TOKEN': ambient})
        self.assertEqual(code, 0, out + err)
        self.assertEqual(delivered, [token], 'the descriptor token, newline removed, is what the service receives')
        spy.assert_called_once_with(fd)
        for text in (out, err):
            self.assertNotIn(token, text)
        for path in output.rglob('*'):
            if path.is_file():
                self.assertNotIn(token.encode(), path.read_bytes())

    def test_same_rules_as_target_authenticate(self):
        cases = {
            'identity_credential_fd_private': dict(content='tok', mode=0o644),
            'identity_credential_fd_limit': dict(content=b'x' * 4097),
            'identity_credential_invalid': dict(content=b'caf\xc3\xa9'),
        }
        for code, spec in cases.items():
            with self.subTest(code):
                fd = self.secret_fd(spec['content'], name=code, mode=spec.get('mode', 0o600))
                (exit_code, out, err), delivered, _, _ = self.run_capture(fd, name='out-' + code)
                self.assertEqual(delivered, [])
                self.assertEqual(json.loads(err)['error']['code'], code)
                self.assertNotEqual(exit_code, 0)
        (exit_code, out, err), delivered, _, _ = self.run_capture(2, name='out-low')
        self.assertEqual(json.loads(err)['error']['code'], 'identity_explicit_credential_fd_required')

    def test_a_pipe_works_and_an_empty_descriptor_is_a_missing_token(self):
        token = canary('pipe')
        read_end, write_end = os.pipe()
        self.opened.append(read_end)
        os.write(write_end, token.encode())
        os.close(write_end)
        (code, out, err), delivered, _, _ = self.run_capture(read_end, name='out-pipe')
        self.assertEqual((code, delivered), (0, [token]), out + err)
        (code, out, err), delivered, _, _ = self.run_capture(self.secret_fd('\n', name='empty'), name='out-empty')
        self.assertEqual(delivered, [])
        self.assertEqual(json.loads(err)['error']['code'], 'identity_credential_fd_empty')

    def test_a_token_with_control_characters_is_still_invalid(self):
        (code, out, err), delivered, _, _ = self.run_capture(self.secret_fd('abc def'), name='out-space')
        self.assertEqual(json.loads(err)['error']['code'], 'capture_token_invalid')
        self.assertEqual(delivered, [])


class DescriptorHandlingTests(Descriptors):
    """Non-inheritable at once, source closed afterwards, exactly one line ending removed."""
    fake = CaptureFdTests.fake
    run_capture = CaptureFdTests.run_capture

    def closed(self, fd):
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_the_source_descriptor_is_made_non_inheritable_and_closed_after_the_route(self):
        token = canary('close')
        fd = self.secret_fd(token)
        calls = []
        real = os.set_inheritable

        def recording(descriptor, value):
            calls.append((descriptor, value))
            return real(descriptor, value)

        with patch('os.set_inheritable', recording):
            (code, out, err), delivered, _, _ = self.run_capture(fd)
        self.assertEqual((code, delivered), (0, [token]), out + err)
        self.assertIn((fd, False), calls)
        self.closed(fd)

    def test_the_source_is_closed_even_when_the_read_is_refused(self):
        fd = self.secret_fd('tok', name='loose', mode=0o644)
        (code, out, err), delivered, _, _ = self.run_capture(fd, name='out-refused')
        self.assertEqual(json.loads(err)['error']['code'], 'identity_credential_fd_private')
        self.closed(fd)

    def test_target_authenticate_closes_both_descriptors(self):
        from dataclasses import asdict
        from intune_iac import identity_binding as ib
        from plugin_tests.test_identity_binding_v5 import config, RecordedServices, Clock
        path = self.root / 'identity.json'
        path.write_text(json.dumps(asdict(config())))
        a, b = self.secret_fd('provider-' + canary('p'), 'p'), self.secret_fd('backend-' + canary('b'), 'b')

        def laboratory(cfg, **kwargs):
            return ib.bind_laboratory(cfg, **kwargs, transport=RecordedServices(), clock=Clock())

        with patch.object(ib, 'bind_live', side_effect=laboratory):
            code, out, err = self.main(['target', 'authenticate', '--input', str(path), '--provider-secret-fd', str(a),
                                        '--backend-secret-fd', str(b)])
        self.assertEqual(code, 0, out + err)
        self.closed(a)
        self.closed(b)

    def test_exactly_one_line_ending_is_removed_and_other_control_characters_are_refused(self):
        token = canary('lines')
        cases = ((token, True), (token + '\n', True), (token + '\r\n', True), (token + '\r\n\r\n', False),
                 (token + '\n\n', False), (token + '\r', False), (token[:8] + '\x01' + token[8:], False),
                 (token[:8] + '\t' + token[8:], False), (token[:8] + '\n' + token[8:], False), (token + '\x7f', False))
        for number, (content, ok) in enumerate(cases):
            with self.subTest(case=number, accepted=ok):
                fd = self.secret_fd(content, name='t%d' % number)
                (code, out, err), delivered, _, _ = self.run_capture(fd, name='o%d' % number)
                if ok:
                    self.assertEqual(delivered, [token])
                else:
                    self.assertEqual(delivered, [])
                    self.assertEqual(json.loads(err)['error']['code'], 'identity_credential_control_character')
                    self.assertNotIn(token, out + err)


class OwnershipTests(Descriptors):
    """One owner for every supplied descriptor: each is closed exactly once on every route exit."""

    def closes(self, argv, numbers, patches=()):
        """Run argv; return how many times os.close was called with each original number. os.dup is moved above 100 so
        a duplicate can never take an original's number and be mistaken for a second close of it."""
        import fcntl
        calls = []
        real_close = os.close
        identities = {n: (os.fstat(n).st_dev, os.fstat(n).st_ino) for n in numbers}

        def recording_close(d):
            # Count a close only while the number still names the original file: a number the CLI later reuses for
            # something else (an output directory, say) is not a second close of the descriptor it was given.
            try:
                info = os.fstat(d)
                calls.append(d if identities.get(d) == (info.st_dev, info.st_ino) else None)
            except OSError:
                calls.append(d)  # closing a number that is already closed is a double close
            return real_close(d)

        with patch('os.close', recording_close), \
                patch('os.dup', lambda d: fcntl.fcntl(d, fcntl.F_DUPFD_CLOEXEC, 100)):
            for p in patches:
                p.start()
            try:
                result = self.main(argv)
            finally:
                for p in patches:
                    p.stop()
        return result, {n: calls.count(n) for n in numbers}

    def collect_argv(self, graph, management):
        document = self.root / 'target.json'
        document.write_text('{}')
        return ['target', 'collect', '--input', str(document), '--graph-token-fd', str(graph),
                '--management-token-fd', str(management)]

    def test_the_equality_refusal_closes_the_shared_descriptor_once(self):
        fd = self.secret_fd(canary('same'))
        (code, out, err), counts = self.closes(self.collect_argv(fd, fd), [fd])
        self.assertEqual(json.loads(err)['error']['code'], 'identity_separate_credential_fds_required')
        self.assertEqual(counts, {fd: 1})
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_a_failed_first_read_still_closes_the_unattempted_descriptor(self):
        loose = self.secret_fd('tok', name='loose', mode=0o644)
        other = self.secret_fd(canary('other'), name='other')
        (code, out, err), counts = self.closes(self.collect_argv(loose, other), [loose, other])
        self.assertEqual(json.loads(err)['error']['code'], 'identity_credential_fd_private')
        self.assertEqual(counts, {loose: 1, other: 1})
        with self.assertRaises(OSError):
            os.fstat(other)

    def test_authenticate_closes_each_number_once_on_success_and_on_failure(self):
        from dataclasses import asdict
        from intune_iac import identity_binding as ib
        from plugin_tests.test_identity_binding_v5 import config, RecordedServices, Clock
        path = self.root / 'identity.json'
        path.write_text(json.dumps(asdict(config())))

        def laboratory(cfg, **kwargs):
            return ib.bind_laboratory(cfg, **kwargs, transport=RecordedServices(), clock=Clock())

        a, b = self.secret_fd(canary('p'), 'p'), self.secret_fd(canary('b'), 'b')
        argv = ['target', 'authenticate', '--input', str(path), '--provider-secret-fd', str(a), '--backend-secret-fd', str(b)]
        (code, out, err), counts = self.closes(argv, [a, b], [patch.object(ib, 'bind_live', side_effect=laboratory)])
        self.assertEqual((code, counts), (0, {a: 1, b: 1}), out + err)
        loose, other = self.secret_fd('tok', 'loose2', 0o644), self.secret_fd(canary('o'), 'other2')
        argv = ['target', 'authenticate', '--input', str(path), '--provider-secret-fd', str(loose),
                '--backend-secret-fd', str(other)]
        (code, out, err), counts = self.closes(argv, [loose, other])
        self.assertEqual(json.loads(err)['error']['code'], 'identity_credential_fd_private')
        self.assertEqual(counts, {loose: 1, other: 1})

    def test_a_descriptor_given_to_capture_is_closed_once(self):
        fd = self.secret_fd(canary('cap'))
        (code, out, err), counts = self.closes(['capture', '--tenant', TENANT, '--policy', POLICY, '--output',
                                                str(self.root / 'o'), '--token-fd', str(fd)], [fd],
                                               [patch('intune_iac.capture._http_transport', CaptureFdTests.fake(None, []))])
        self.assertEqual(counts, {fd: 1})


class CollectFdTests(Descriptors):
    def run_collect(self, argv_tail, env=None):
        from plugin_tests import test_target as tt
        document = self.root / 'target.json'
        document.write_text(json.dumps(tt.fixture()))
        tt.Connection.responses = tt.CollectionTests.responses(None)
        tt.Connection.requests = []
        with patch('intune_iac.target._now', return_value=tt.NOW), \
                patch('intune_iac.target.http.client.HTTPSConnection', tt.Connection), patch.dict(os.environ, env or {}):
            result = self.main(['target', 'collect', '--input', str(document), *argv_tail])
        return result, [headers['Authorization'] for _, _, _, headers in tt.Connection.requests]

    def test_both_tokens_from_descriptors(self):
        graph, management = canary('graph'), canary('arm')
        a, b = self.secret_fd(graph, 'g'), self.secret_fd(management + '\n', 'm')
        (code, out, err), sent = self.run_collect(['--graph-token-fd', str(a), '--management-token-fd', str(b)],
                                                  {'INTUNE_GRAPH_TOKEN': 'ambient-graph', 'INTUNE_MANAGEMENT_TOKEN': 'ambient-arm'})
        self.assertEqual(code, 0, out + err)
        self.assertEqual(sent, ['Bearer ' + graph, 'Bearer ' + management, 'Bearer ' + management])
        self.assertNotIn(graph, out + err)
        self.assertNotIn(management, out + err)

    def test_routes_can_be_mixed_per_token(self):
        graph, management = canary('graph'), canary('arm')
        a = self.secret_fd(graph, 'g')
        (code, out, err), sent = self.run_collect(['--graph-token-fd', str(a), '--management-token-env', 'ARM_VIA_ENV'],
                                                  {'ARM_VIA_ENV': management})
        self.assertEqual(code, 0, out + err)
        self.assertEqual(sent[0], 'Bearer ' + graph)
        self.assertEqual(sent[1], 'Bearer ' + management)

    def test_two_tokens_need_two_descriptors_and_a_bad_descriptor_sends_nothing(self):
        a = self.secret_fd(canary('one'), 'one')
        (code, out, err), sent = self.run_collect(['--graph-token-fd', str(a), '--management-token-fd', str(a)])
        self.assertEqual(json.loads(err)['error']['code'], 'identity_separate_credential_fds_required')
        self.assertEqual(sent, [])
        # the equality refusal closed the shared descriptor, so the next route gets a fresh one
        a = self.secret_fd(canary('two'), 'two')
        loose = self.secret_fd('tok', 'loose', 0o644)
        (code, out, err), sent = self.run_collect(['--graph-token-fd', str(loose), '--management-token-fd', str(a)])
        self.assertEqual(json.loads(err)['error']['code'], 'identity_credential_fd_private')
        self.assertEqual(sent, [])


if __name__ == '__main__':
    unittest.main()
