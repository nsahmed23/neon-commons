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
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import cli
from intune_iac.io import write_json

PROJECT = Path(__file__).resolve().parents[1]


def canary(label):
    # A distinct, secret-shaped value per route; the label is only a prefix that makes a failure readable.
    return label + '-' + secrets.token_urlsafe(30) + 'A1'


def forms(value):
    raw = value.encode()
    return {'plain': raw, 'base64': base64.b64encode(raw), 'urlsafe_base64': base64.urlsafe_b64encode(raw),
            'hex': raw.hex().encode(), 'json_escaped': json.dumps(value).encode()[1:-1]}


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

    def run_cli(self, argv, canaries, env=None):
        """Run cli.main in process; return (exit code, stdout, stderr, child argument lists)."""
        env = env or {}
        baseline = dict(os.environ)
        children = []
        real = subprocess.Popen

        class Recording(real):
            def __init__(self, args, *a, **k):
                children.append(args)
                super().__init__(args, *a, **k)

        out, err = io.StringIO(), io.StringIO()
        with patch('subprocess.Popen', Recording), patch.dict(os.environ, env):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(argv)
            after = dict(os.environ)
        self.assertEqual(after, {**baseline, **env}, 'the command changed the parent environment')
        self.assert_clean(canaries, out.getvalue(), err.getvalue(), children)
        return code, out.getvalue(), err.getvalue(), children

    def assert_clean(self, canaries, out, err, children, tree=None):
        leaks = Leaks(*canaries)
        self.assertEqual(leaks.in_bytes(out.encode()), [], 'canary on stdout')
        self.assertEqual(leaks.in_bytes(err.encode()), [], 'canary on stderr')
        self.assertEqual(leaks.in_bytes(json.dumps([[str(x) for x in c] if isinstance(c, (list, tuple)) else str(c)
                                                    for c in children]).encode()), [], 'canary in child argv')
        self.assertEqual(leaks.in_tree(tree or self.work), [], 'canary in a file the command wrote')

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

        try:
            with patch.object(ib, 'bind_live', side_effect=laboratory):
                code, out, _, _ = self.run_cli(['target', 'authenticate', '--input', str(path),
                    '--provider-secret-fd', str(descriptors[0]), '--backend-secret-fd', str(descriptors[1])],
                    (provider, backend))
        finally:
            for fd in descriptors:
                os.close(fd)
        self.assertEqual(json.loads(out)['assurance'], 'laboratory_recorded_responses')

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
        self.addCleanup(os.close, fd)
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
            self.run_cli(['capture', '--tenant', tenant, '--policy', policy, '--output', str(self.work / 'fdcap'),
                          '--token-fd', str(self.secret_fd(capture_token, 'capture.token'))], (capture_token,))
        self.assertEqual(delivered, [capture_token])
        document = self.inputs / 'target-fd.json'
        write_json(document, tt.fixture())
        tt.Connection.responses, tt.Connection.requests = tt.CollectionTests.responses(None), []
        with patch('intune_iac.target._now', return_value=tt.NOW), \
                patch('intune_iac.target.http.client.HTTPSConnection', tt.Connection):
            code, out, _, _ = self.run_cli(['target', 'collect', '--input', str(document),
                '--graph-token-fd', str(self.secret_fd(graph, 'graph.token')),
                '--management-token-fd', str(self.secret_fd(management, 'arm.token'))], (graph, management))
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
        code, out, _, _ = self.run_cli(['workbench', 'observer-run', '--job', str(job)], (secret, issued),
                                       {'HARNESS_OBSERVER_SECRET': secret})
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
                                        '--evidence', str(evidence)], (key, leaked), {'CLM_HARNESS_KEY': key})
        bodies = json.dumps([r['body'] for r in fake.requests]).encode()
        self.assertEqual(Leaks(key, leaked).in_bytes(bodies), [], 'canary in the judge request body')
        self.assertEqual(fake.requests, [], 'evidence with a secret-shaped value must not be sent at all')


if __name__ == '__main__':
    unittest.main()
