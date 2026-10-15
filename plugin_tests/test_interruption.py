"""Interruption during an actual running modeled call (requirement 12; TASK-12 section 4; TASK-13 sections 7, 8).

The modeled service's synthetic latency holds a request after its durable write and before its answer, so an interrupt
lands inside a running call. These tests interrupt there and check the durable effects: the modeled change, the
operation journal, the collection run, the service lock, and that recovery never replays the change.
"""
import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock, maintenance, modeled_service, protected
from intune_iac.io import AppError, write_json
from intune_iac.modeled_service import BASE, ModeledService
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore

VARIABLE = 'INTUNE_IAC_MODELED_LATENCY_SECONDS'


class Interrupted(KeyboardInterrupt):
    pass


class LatencyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        fixture = generate_estate(seed=510, policy_count=2)
        self.ids = [policy['id'] for policy in fixture['truth']['policies']]
        self.tenant = fixture['truth']['tenant_id']
        self.service = ModeledService.create(self.root / 'service', fixture['capture'], self.ids)

    def stored(self):
        return json.loads((self.root / 'service' / 'service.json').read_text())

    def patch_body(self):
        snapshot = self.service.snapshot()
        body = copy.deepcopy(snapshot['current']['objects'][self.ids[0]])
        body['description'] = 'Changed while the answer was delayed'
        return body, str(snapshot['revision'])

    def test_without_the_setting_nothing_is_delayed_or_recorded(self):
        slept = []
        with patch.dict(os.environ, {}, clear=False), patch.object(modeled_service, 'sleep', slept.append):
            os.environ.pop(VARIABLE, None)
            self.service.request('GET', BASE, tenant_id=self.tenant)
        self.assertEqual(slept, [])
        self.assertNotIn('latency_seconds', self.stored()['requests'][-1])

    def test_the_delay_comes_after_the_durable_write_and_is_recorded(self):
        seen = []

        def during(seconds):
            seen.append((seconds, self.stored()['revision'], self.stored()['requests'][-1].get('latency_seconds')))

        body, etag = self.patch_body()
        with patch.dict(os.environ, {VARIABLE: '0.25'}), patch.object(modeled_service, 'sleep', during):
            self.service.request('PATCH', BASE + '/' + self.ids[0], tenant_id=self.tenant, body=body, if_match=etag)
        self.assertEqual(seen, [(0.25, int(etag) + 1, 0.25)])

    def test_an_unusable_setting_is_refused_before_anything_is_recorded(self):
        before = len(self.stored()['requests'])
        for value in ('abc', '-1', '31', 'nan', 'inf'):
            with patch.dict(os.environ, {VARIABLE: value}), self.assertRaises(AppError) as raised:
                self.service.request('GET', BASE, tenant_id=self.tenant)
            self.assertEqual(raised.exception.code, 'model_latency_invalid', value)
        self.assertEqual(len(self.stored()['requests']), before)

    def test_an_interrupt_inside_the_delay_keeps_the_change_and_releases_the_service(self):
        def interrupt(seconds):
            raise Interrupted()

        body, etag = self.patch_body()
        with patch.dict(os.environ, {VARIABLE: '5'}), patch.object(modeled_service, 'sleep', interrupt):
            with self.assertRaises(Interrupted):
                self.service.request('PATCH', BASE + '/' + self.ids[0], tenant_id=self.tenant, body=body, if_match=etag)
        self.assertEqual(self.service.snapshot()['current']['objects'][self.ids[0]]['description'], body['description'])
        os.environ.pop(VARIABLE, None)
        self.assertEqual(self.service.request('GET', BASE, tenant_id=self.tenant)['status'], 200)


class InterruptedOperationTests(unittest.TestCase):
    """Through the maintenance engine and the store: the durable records an interrupted call leaves, and recovery."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        fixture = generate_estate(seed=510, policy_count=2)
        self.ids = [policy['id'] for policy in fixture['truth']['policies']]
        self.service = ModeledService.create(self.root / 'service', fixture['capture'], self.ids)
        self.store = WorkbenchStore.create(self.root / 'store', fixture['truth']['tenant_id'])
        self.store.collect(self.service, observed_at=time.time() - 600)
        # A stable injected clock for the approval window: this host's 266 s steps would otherwise hold the change
        # (correctly), and the interrupt would never be reached.
        patcher = patch.object(protected, '_now', return_value=int(time.time()))
        patcher.start()
        self.addCleanup(patcher.stop)
        clock.reset_process_anchor()
        self.addCleanup(clock.reset_process_anchor)

    def requests(self, method):
        rows = json.loads((self.root / 'service' / 'service.json').read_text())['requests']
        return [row for row in rows if row['method'] == method]

    def interrupt_on(self, method):
        def during(seconds):
            if self.requests(method):
                raise Interrupted()
        return during

    def test_an_interrupted_dispatch_is_unknown_until_reconciled_and_never_replayed(self):
        desired = copy.deepcopy(self.service.snapshot()['current']['objects'][self.ids[0]])
        desired['description'] = 'Reviewed synthetic correction'
        write_json(self.root / 'desired.json', desired)
        proposal = maintenance.propose(self.root / 'store', self.root / 'service', self.ids[0], self.root / 'desired.json',
                                       self.root / 'operation')
        with patch.dict(os.environ, {VARIABLE: '5'}), patch.object(modeled_service, 'sleep', self.interrupt_on('PATCH')):
            with self.assertRaises(Interrupted):
                maintenance.execute(self.root / 'operation', approve_digest=proposal['approval_digest'])
        journal = maintenance._load(self.root / 'operation')[2]
        self.assertEqual(journal['status'], 'outcome_unknown')
        self.assertIn('dispatch_started', [event['kind'] for event in journal['events']])
        self.assertEqual(len(self.requests('PATCH')), 1)
        self.assertEqual(self.requests('PATCH')[0].get('latency_seconds'), 5.0)
        os.environ.pop(VARIABLE, None)
        maintenance.reconcile(self.root / 'operation')
        self.assertNotEqual(maintenance._load(self.root / 'operation')[2]['status'], 'outcome_unknown')
        self.assertEqual(len(self.requests('PATCH')), 1, 'reconciliation never replays the change')

    def test_an_interrupted_collection_has_no_end_and_the_next_one_completes(self):
        from intune_iac.workbench_diagnostics import diagnostics
        with patch.dict(os.environ, {VARIABLE: '5'}), patch.object(modeled_service, 'sleep', self.interrupt_on('GET')):
            with self.assertRaises(Interrupted):
                self.store.collect(self.service)
        attempt = self.store.inspect(self.ids[0])['last_attempt']
        self.assertEqual(attempt['status'], 'collecting')
        codes = {signal['code'] for signal in diagnostics(self.store, self.ids[0])['signals']}
        self.assertIn('collection_not_finished', codes)
        os.environ.pop(VARIABLE, None)
        self.assertEqual(self.store.collect(self.service)['status'], 'complete')
        self.assertEqual(self.store.inspect(self.ids[0])['last_attempt']['status'], 'complete')


class InterruptedSessionWordsTests(unittest.TestCase):
    """What a person reads after Ctrl-C: what was running, what it left, and the exact next step."""
    setUp = InterruptedOperationTests.setUp
    requests = InterruptedOperationTests.requests
    interrupt_on = InterruptedOperationTests.interrupt_on

    def session(self, commands, method):
        from intune_iac.workbench import run_terminal
        pending = iter(commands)

        def read(prompt):
            return next(pending)
        with patch.dict(os.environ, {VARIABLE: '5'}), patch.object(modeled_service, 'sleep', self.interrupt_on(method)):
            return run_terminal(self.root / 'store', service_root=self.root / 'service', input_fn=read,
                                output_fn=lambda line: None)

    def test_an_interrupted_execution_names_the_operation_to_reconcile(self):
        from intune_iac.workbench import interrupted_lines
        desired = copy.deepcopy(self.service.snapshot()['current']['objects'][self.ids[0]])
        desired['description'] = 'Reviewed synthetic correction'
        write_json(self.root / 'desired.json', desired)
        proposal = maintenance.propose(self.root / 'store', self.root / 'service', self.ids[0], self.root / 'desired.json',
                                       self.root / 'operation')
        result = self.session(['execute %s %s' % (self.root / 'operation', proposal['approval_digest'])], 'PATCH')
        self.assertEqual(result['status'], 'interrupted')
        self.assertEqual(result['interrupted_during'], {'command': 'execute', 'operation_root': str(self.root / 'operation')})
        text = '\n'.join(interrupted_lines(result))
        self.assertIn('Interrupted while executing operation %s' % (self.root / 'operation'), text)
        self.assertIn('outcome is unknown', text)
        self.assertIn('intune-iac workbench reconcile --operation %s' % (self.root / 'operation'), text)
        self.assertIn('never replays the change', text)
        self.assertNotIn('{', text)

    def test_an_interrupted_collection_says_it_has_no_end_and_to_collect_again(self):
        from intune_iac.workbench import interrupted_lines
        result = self.session(['collect'], 'GET')
        self.assertEqual(result['interrupted_during'], {'command': 'collect', 'service_root': str(self.root / 'service')})
        text = '\n'.join(interrupted_lines(result))
        self.assertIn('Interrupted during a collection', text)
        self.assertIn('records no end', text)
        self.assertIn('intune-iac workbench collect --root %s --service-root %s' % (self.root / 'store', self.root / 'service'), text)
        self.assertNotIn('reconcile', text)

    def test_an_interrupt_at_the_prompt_says_nothing_was_running(self):
        from intune_iac.workbench import interrupted_lines, run_terminal

        def read(prompt):
            raise KeyboardInterrupt
        result = run_terminal(self.root / 'store', input_fn=read, output_fn=lambda line: None)
        self.assertIsNone(result['interrupted_during'])
        self.assertIn('Nothing was running', '\n'.join(interrupted_lines(result)))

    def test_a_terminal_reads_sentences_and_a_pipe_reads_json(self):
        import io
        from intune_iac import cli
        result = {'status': 'interrupted', 'evidence_class': 'local_interface_result', 'interrupted_during': None,
                  'recovery': 'x', 'store_root': str(self.root / 'store')}

        class Terminal(io.StringIO):
            def isatty(self):
                return True
        for stream, json_expected in ((Terminal(), False), (io.StringIO(), True)):
            with patch.object(cli, 'execute', return_value=result), patch('sys.stdout', stream):
                code = cli.main(['workbench', 'workspace', '--root', str(self.root / 'store')])
            self.assertEqual(code, 2)
            self.assertEqual(stream.getvalue().startswith('{'), json_expected, stream.getvalue()[:80])
