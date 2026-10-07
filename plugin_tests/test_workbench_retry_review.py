"""Independent retry/receipt admission probes; no live service credentials."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from intune_iac import capture, cli
from intune_iac.capture_adapter import load_capture
from intune_iac.io import AppError

TENANT = '11111111-1111-4111-8111-111111111111'
POLICY = '22222222-2222-4222-8222-222222222222'
GRAPH = 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'


class RetryIndependentReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.output = self.root / 'capture'
        source = json.loads((Path(__file__).resolve().parents[1] / 'examples/supported/input/export.json').read_text())
        self.responses = {}
        for collection in source['collections']:
            for page in collection['pages']:
                body = copy.deepcopy(page['body'])
                if collection['kind'] == 'assignments':
                    for row in body['value']: row.update(source='direct', sourceId=None)
                self.responses[page['request_url']] = (200, json.dumps(body).encode())
        self.requests = []

    def run_capture(self, first, **kwargs):
        queue = list(first)
        def get(url, **unused):
            self.requests.append(url)
            response = queue.pop(0) if queue and url == GRAPH else self.responses[url]
            if isinstance(response, BaseException): raise response
            return response
        return capture.capture(TENANT, POLICY, self.output, transport=get, **kwargs)

    def receipt(self):
        return json.loads((self.output / 'capture-receipt.json').read_text())

    def write_receipt(self, document):
        (self.output / 'capture-receipt.json').write_text(json.dumps(document))

    def test_denial_cannot_be_relabelled_as_a_suppressed_retry(self):
        self.run_capture([(429, b'{"error":{"message":"private-body"}}', {'Retry-After': '0'})])
        original = self.receipt()
        for status in [200, 401, 403, 301, 500]:
            changed = copy.deepcopy(original)
            changed['attempts'][0]['http_status'] = status
            changed['pages'][0]['http_status'] = status
            self.write_receipt(changed)
            with self.subTest(status=status), self.assertRaises(AppError):
                load_capture(self.output, TENANT)

    def test_successor_cannot_move_between_collection_owners_after_retry(self):
        self.run_capture([(429, b'{}', {'Retry-After': '0'})])
        original = self.receipt()
        changed = copy.deepcopy(original)
        changed['attempts'][1]['owner_id'] = POLICY
        changed['pages'][1]['owner_id'] = POLICY
        self.write_receipt(changed)
        with self.assertRaises(AppError): load_capture(self.output, TENANT)

    def test_retry_delay_boolean_negative_nan_and_overlimit_rejected(self):
        self.run_capture([(503, b'{}', {'Retry-After': '0'})])
        original = self.receipt()
        for value in [True, -1, float('nan'), 31]:
            changed = copy.deepcopy(original)
            changed['attempts'][0]['retry_delay_seconds'] = value
            self.write_receipt(changed)
            with self.subTest(value=value), self.assertRaises(AppError):
                load_capture(self.output, TENANT)

    def test_cancelled_transport_retains_zero_raw_pages_and_blocks_later_reads(self):
        result = self.run_capture([KeyboardInterrupt()])
        self.assertTrue(result['cancelled'])
        self.assertEqual(self.requests, [GRAPH])
        self.assertEqual(self.receipt()['pages'], [])
        self.assertEqual(self.receipt()['attempts'][0]['error'], 'cancelled')
        batch = load_capture(self.output, TENANT)
        self.assertEqual(batch['status'], 'partial')
        self.assertIsNone(batch['body'])

    def test_cancellation_cannot_be_disclaimed_by_receipt_flag(self):
        self.run_capture([KeyboardInterrupt()])
        changed = self.receipt(); changed['cancelled'] = False
        self.write_receipt(changed)
        with self.assertRaises(AppError): load_capture(self.output, TENANT)

    def test_progress_failure_is_partial_without_becoming_cancellation(self):
        def progress(_): raise RuntimeError('PRIVATE-PROGRESS')
        result = self.run_capture([(429, b'{}', {'Retry-After': '0'})], progress=progress)
        self.assertFalse(result['cancelled'])
        self.assertEqual(result['coverage'][0]['reason'], 'progress_failed')
        batch = load_capture(self.output, TENANT)
        self.assertEqual(batch['status'], 'partial')
        self.assertFalse(batch['source']['capture_attempts']['cancelled'])
        self.assertNotIn('PRIVATE-PROGRESS', json.dumps(result) + json.dumps(batch))

    def test_conflicting_or_oversized_retry_after_never_justifies_an_early_retry(self):
        for index, headers in enumerate([[('Retry-After', '0'), ('retry-after', '999')],
                                         {'Retry-After': '9' * 200}]):
            self.output = self.root / ('capture-' + str(index)); self.requests = []
            with self.subTest(headers=index), patch.object(capture.time, 'sleep') as wait:
                result = self.run_capture([(429, b'{}', headers)])
                self.assertEqual(result['coverage'][0]['reason'], 'retry_delay_limit')
                self.assertEqual(self.requests.count(GRAPH), 1)
                self.assertFalse(wait.called)
                self.assertEqual(load_capture(self.output, TENANT)['status'], 'partial')

    def test_partial_retry_receipt_preserves_terminal_denial_after_transient(self):
        self.run_capture([(503, b'{}', {'Retry-After': '0'}),
                          (403, b'{"error":{"message":"PRIVATE-DENIAL"}}')])
        batch = load_capture(self.output, TENANT)
        self.assertEqual(batch['status'], 'denied')
        self.assertIsNone(batch['body'])
        self.assertEqual(batch['source']['capture_attempts']['attempts'][1]['http_status'], 403)
        self.assertNotIn('PRIVATE-DENIAL', json.dumps(batch))
        self.assertEqual(self.requests.count(GRAPH), 2)

    def test_missing_retry_raw_file_is_rejected_without_deleting_any_other_evidence(self):
        self.run_capture([(429, b'{}', {'Retry-After': '0'})])
        target = self.output / self.receipt()['pages'][0]['raw_path']
        target.rename(self.root / 'retained-retry-raw')
        with self.assertRaises(AppError): load_capture(self.output, TENANT)
        self.assertEqual((self.root / 'retained-retry-raw').read_bytes(), b'{}')
        self.assertEqual(len(list((self.output / 'raw').iterdir())), 3)

    def test_cli_progress_and_result_do_not_echo_bearer_server_or_header_bytes(self):
        calls = []
        def factory(token):
            self.assertEqual(token, 'BEARER-CANARY')
            def get(url, *, timeout):
                self.assertGreater(timeout, 0); self.assertLessEqual(timeout, 20)
                calls.append(url)
                if len(calls) == 1:
                    return 503, b'{"error":{"message":"BODY-CANARY"}}', {'Retry-After': '\x1b]0;HEADER-CANARY\x07'}
                return self.responses[url]
            return get
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(capture, '_http_transport', factory), patch.object(capture.time, 'sleep'), \
                patch.dict(os.environ, {'REVIEW_CAPTURE_TOKEN': 'BEARER-CANARY'}), redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(['capture', '--tenant', TENANT, '--policy', POLICY, '--output', str(self.output),
                             '--token-env', 'REVIEW_CAPTURE_TOKEN', '--max-attempts-per-page', '2'])
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue()); event = json.loads(stderr.getvalue())
        self.assertEqual(result['status'], 'captured')
        self.assertEqual(event['retry_in_seconds'], 1)
        self.assertEqual(event['delay_source'], 'backoff')
        self.assertNotIn('CANARY', stdout.getvalue() + stderr.getvalue())
        self.assertEqual((self.output / 'raw/page-000000.json').read_bytes(), b'{"error":{"message":"BODY-CANARY"}}')

    def test_cli_cancel_returns_130_with_durable_partial_receipt(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        def factory(token):
            def get(url, *, timeout): raise KeyboardInterrupt()
            return get
        with patch.object(capture, '_http_transport', factory), \
                patch.dict(os.environ, {'REVIEW_CAPTURE_TOKEN': 'synthetic'}), redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(['capture', '--tenant', TENANT, '--policy', POLICY, '--output', str(self.output),
                             '--token-env', 'REVIEW_CAPTURE_TOKEN'])
        self.assertEqual(code, 130)
        self.assertEqual(json.loads(stdout.getvalue())['status'], 'partial')
        self.assertEqual(load_capture(self.output, TENANT)['status'], 'partial')


if __name__ == '__main__': unittest.main()
