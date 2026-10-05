"""Capture behavior: fabricated completeness, lost source bytes and leakage are bugs."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from intune_iac.io import AppError

T = '11111111-1111-4111-8111-111111111111'
P = '22222222-2222-4222-8222-222222222222'
ROOT = 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'
SETTINGS = ROOT + '/' + P + '/settings'
ASSIGNMENTS = ROOT + '/' + P + '/assignments'


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.output = self.folder/'capture'

    def capture(self, responses, **kwargs):
        from intune_iac.capture import capture
        calls = []
        def transport(url):
            calls.append(url)
            response = responses[url]
            if isinstance(response, Exception):
                raise response
            return response
        result = capture(T, P, self.output, transport=transport, **kwargs)
        return result, calls, json.loads((self.output/'export.json').read_bytes())

    def base(self):
        return {
            ROOT: (200, b'{ "value": [{"id":"' + P.encode() + b'","name":"Actual policy"}] }\n'),
            SETTINGS: (200, b'{"value":[{"id":"opaque-source-id","settingInstance":{"futureType":"KEPT-RAW"}}]}'),
            ASSIGNMENTS: (200, b'{"value":[]}'),
        }

    def test_adapter_is_available_for_real_capture(self):
        self.assertIsNotNone(importlib.util.find_spec('intune_iac.capture'),
                             'Real capture module is missing.')

    def test_whole_raw_page_bytes_and_truthful_identity_survive(self):
        responses = self.base()
        result, calls, export = self.capture(responses)
        self.assertEqual(calls, [ROOT, SETTINGS, ASSIGNMENTS])
        self.assertEqual(result['status'], 'captured')
        self.assertEqual(result['tenant_assurance'], 'caller_asserted')
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(export['synthetic'])
        self.assertNotEqual(export['exporter']['id'], 'appendix-b-graph-snapshot')
        self.assertEqual(export['ownership'], [])
        self.assertEqual(export['references'], [])
        self.assertEqual(export['collections'][1]['pages'][0]['body']['value'][0]['id'], 'opaque-source-id')
        receipt = json.loads((self.output/'capture-receipt.json').read_bytes())
        self.assertEqual(receipt['tenant_assurance'], 'caller_asserted')
        first = receipt['pages'][0]
        self.assertEqual((self.output/first['raw_path']).read_bytes(), responses[ROOT][1])
        self.assertEqual(first['source_byte_sha256'], hashlib.sha256(responses[ROOT][1]).hexdigest())
        self.assertEqual(receipt['export_byte_sha256'], hashlib.sha256((self.output/'export.json').read_bytes()).hexdigest())
        context = json.loads((self.output/'context.json').read_bytes())
        self.assertFalse(context['source_is_synthetic'])
        self.assertEqual(context['tenant_id'], T)
        self.assertEqual(context['selected_policy_id'], P)
        self.assertEqual(context['authorization'], 'emit_only')
        self.assertEqual(context['provider_version'], '1.0.0')
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        for path in self.output.rglob('*'):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600)

    def test_pagination_follows_entire_same_path_link_including_skip(self):
        responses = self.base()
        next_url = ROOT + '?$skip=2&$skiptoken=A%2BB'
        responses[ROOT] = (200, json.dumps({'value': [], '@odata.nextLink':next_url}).encode())
        responses[next_url] = (200, b'{"value":[{"id":"' + P.encode() + b'"}]}')
        result, calls, export = self.capture(responses)
        self.assertEqual(calls, [ROOT, next_url, SETTINGS, ASSIGNMENTS])
        self.assertEqual(export['collections'][0]['pages'][1]['request_url'], next_url)
        self.assertEqual(export['collections'][0]['coverage'], 'complete')
        self.assertFalse(result['provider_qualified'])

    def test_denied_relationship_retains_error_without_empty_success(self):
        responses = self.base()
        responses[ASSIGNMENTS] = (403, b'{"error":{"message":"SECRET-CANARY"}}')
        result, _, export = self.capture(responses)
        self.assertEqual(export['collections'][2]['coverage'], 'access_denied')
        self.assertNotIn('value', export['collections'][2]['pages'][0]['body'])
        self.assertEqual(result['status'], 'partial')
        self.assertNotIn('SECRET-CANARY', json.dumps(result))

    def test_malformed_and_error_success_responses_are_partial_with_raw_evidence(self):
        for raw in [b'{broken SECRET-CANARY', b'{"value":[],"value":[]}',
                    b'{"value":[],"error":{"message":"SECRET-CANARY"}}', b'{"value":null}', b'[]']:
            with self.subTest(raw=raw):
                self.output = self.folder/('capture-' + str(len(list(self.folder.iterdir()))))
                responses = self.base(); responses[SETTINGS] = (200, raw)
                result, _, export = self.capture(responses)
                self.assertEqual(export['collections'][1]['coverage'], 'partial')
                self.assertNotIn('SECRET-CANARY', json.dumps(result))
                receipt = json.loads((self.output/'capture-receipt.json').read_bytes())
                setting_page = next(p for p in receipt['pages'] if p['kind']=='settings')
                self.assertEqual((self.output/setting_page['raw_path']).read_bytes(), raw)

    def test_new_origin_wrong_path_and_loop_are_never_fetched(self):
        for next_url in ['https://evil.invalid/SECRET-CANARY', ASSIGNMENTS,
                         ROOT, ROOT + '#SECRET-CANARY', ROOT.replace('graph.microsoft.com','user@graph.microsoft.com')]:
            with self.subTest(url=next_url):
                self.output = self.folder/('capture-' + str(len(list(self.folder.iterdir()))))
                responses = self.base()
                responses[ROOT] = (200, json.dumps({'value':[], '@odata.nextLink':next_url}).encode())
                result, calls, export = self.capture(responses)
                self.assertEqual(calls.count(ROOT), 1)
                self.assertEqual(calls, [ROOT, SETTINGS, ASSIGNMENTS])
                self.assertEqual(export['collections'][0]['coverage'], 'partial')
                self.assertNotIn('SECRET-CANARY', json.dumps(result))

    def test_limit_never_fabricates_unrequested_relationships(self):
        result, calls, export = self.capture(self.base(), max_pages=1)
        self.assertEqual(calls, [ROOT])
        self.assertEqual([c['coverage'] for c in export['collections']], ['complete','partial','partial'])
        self.assertEqual(export['collections'][1]['pages'], [])
        self.assertEqual(result['status'], 'partial')

    def test_transport_exception_is_sanitized_and_partial(self):
        responses = self.base(); responses[SETTINGS] = RuntimeError('Bearer SECRET-CANARY')
        result, _, export = self.capture(responses)
        self.assertEqual(export['collections'][1]['coverage'], 'partial')
        self.assertEqual(export['collections'][1]['pages'], [])
        self.assertNotIn('SECRET-CANARY', json.dumps(result))
        self.assertNotIn('SECRET-CANARY', (self.output/'capture-receipt.json').read_text())

    def test_duplicate_source_record_id_across_pages_is_partial_without_rewriting(self):
        responses = self.base()
        next_url = SETTINGS + '?$skiptoken=next'
        responses[SETTINGS] = (200, json.dumps({'value':[{'id':'SOURCE-ID'}], '@odata.nextLink':next_url}).encode())
        responses[next_url] = (200, b'{"value":[{"id":"SOURCE-ID"}]}')
        result, _, export = self.capture(responses)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(export['collections'][1]['coverage'], 'partial')
        self.assertEqual([p['body']['value'][0]['id'] for p in export['collections'][1]['pages']], ['SOURCE-ID','SOURCE-ID'])

    def test_missing_selected_policy_is_partial_and_does_not_create_policy(self):
        responses = self.base(); responses[ROOT] = (200, b'{"value":[]}')
        result, _, export = self.capture(responses)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(export['collections'][0]['reason'], 'selected_policy_missing')
        self.assertEqual(export['collections'][0]['pages'][0]['body']['value'], [])

    def test_non_utf8_json_is_restricted_raw_evidence_not_success(self):
        responses = self.base(); responses[SETTINGS] = (200, b'\xff\xfe' + '{"value":[]}'.encode('utf-16-le'))
        result, _, export = self.capture(responses)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(export['collections'][1]['coverage'], 'partial')

    def test_oversize_response_preserves_bounded_received_prefix_and_marks_truncation(self):
        responses = self.base()
        raw = b'{"value":[]}' + b' ' * 100
        responses[SETTINGS] = (200, raw)
        with patch('intune_iac.capture.MAX_PAGE_BYTES', 80):
            result, _, export = self.capture(responses)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(export['collections'][1]['reason'], 'byte_limit')
        receipt = json.loads((self.output/'capture-receipt.json').read_bytes())
        page = next(p for p in receipt['pages'] if p['kind']=='settings')
        self.assertFalse(page['raw_capture_complete'])
        self.assertEqual((self.output/page['raw_path']).read_bytes(), raw[:81])

    def test_real_transport_uses_explicit_env_token_and_get_without_redirect_following(self):
        from intune_iac.capture import capture
        requests = []
        class Response:
            code = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                self.limit = limit
                return b'{"value":[{"id":"' + P.encode() + b'"}]}' if len(requests)==1 else b'{"value":[]}'
        class Opener:
            def open(self, request, timeout):
                requests.append(request)
                self.timeout = timeout
                return Response()
        opener = Opener()
        with patch.dict(os.environ, {'ONLY_THIS_TOKEN':'SECRET-CANARY'}, clear=True), \
                patch('intune_iac.capture.build_opener', return_value=opener) as builder:
            result = capture(T,P,self.output,token_env='ONLY_THIS_TOKEN')
        self.assertEqual([r.get_method() for r in requests], ['GET','GET','GET'])
        self.assertEqual([r.full_url for r in requests], [ROOT,SETTINGS,ASSIGNMENTS])
        self.assertEqual(requests[0].get_header('Authorization'), 'Bearer SECRET-CANARY')
        handler = next(value for value in builder.call_args.args if hasattr(value, 'redirect_request'))
        self.assertIsNone(handler.redirect_request(requests[0],None,302,'Found',{},'https://evil.invalid'))
        self.assertLessEqual(opener.timeout, 20)
        self.assertNotIn('SECRET-CANARY', json.dumps(result))
        for path in self.output.rglob('*.json'):
            self.assertNotIn('SECRET-CANARY', path.read_text())

    def test_existing_directory_and_symlink_ancestor_fail_before_transport(self):
        from intune_iac.capture import capture
        self.output.mkdir(); (self.output/'keep').write_text('KEEP')
        with self.assertRaises(AppError):
            capture(T,P,self.output,transport=lambda _: self.fail('Must not fetch'))
        self.assertEqual((self.output/'keep').read_text(), 'KEEP')
        link = self.folder/'link'; link.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaises(AppError):
            capture(T,P,link/'new',transport=lambda _: self.fail('Must not fetch'))
        self.assertFalse((self.folder/'new').exists())

    def test_no_token_fails_without_creating_output(self):
        from intune_iac.capture import capture
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AppError) as caught:
                capture(T,P,self.output,token_env='TEST_EXPLICIT_TOKEN')
        self.assertEqual(caught.exception.code, 'capture_token_missing')
        self.assertFalse(self.output.exists())

    def test_invalid_identity_or_limit_fails_before_transport(self):
        from intune_iac.capture import capture
        for tenant,policy,limit in [('bad',P,100),(T,'bad',100),(T,P,0),(T,P,True)]:
            with self.subTest(tenant=tenant,policy=policy,limit=limit):
                with self.assertRaises(AppError):
                    capture(tenant,policy,self.output,max_pages=limit,transport=lambda _: self.fail('Must not fetch'))
        self.assertFalse(self.output.exists())

    def test_unsupported_native_platform_returns_safe_unavailable_error(self):
        from intune_iac.capture import capture
        with patch('intune_iac.capture.os.name', 'nt'):
            with self.assertRaises(AppError) as caught:
                capture(T,P,self.output,transport=lambda _: self.fail('Must not fetch'))
        self.assertEqual(caught.exception.code, 'capture_platform_unavailable')
        self.assertFalse(self.output.exists())

    def test_real_shaped_capture_drives_engine_review_without_claiming_mapping(self):
        from intune_iac.engine import inspect_source, generate
        fixture = Path(__file__).resolve().parents[1]/'examples/supported/input/export.json'
        source = json.loads(fixture.read_bytes())
        responses = {}
        for collection in source['collections']:
            for page in collection['pages']:
                responses[page['request_url']] = (page['http_status'], json.dumps(page['body']).encode())
        body = json.loads(responses[ROOT][1])
        selected = next(p for p in body['value'] if p['id']==P)
        selected.update(creationSource='real-shaped-fixture', priorityMetaData={'priority':3})
        responses[ROOT] = (200, json.dumps(body).encode())
        body = json.loads(responses[SETTINGS][1]); body['value'][0]['id']='opaque-source-id'
        responses[SETTINGS] = (200, json.dumps(body).encode())
        result, _, export = self.capture(responses)
        review = inspect_source(result['export'], result['context'])
        self.assertEqual(review['status'], 'blocked')
        self.assertTrue(review['preservation_verified'])
        self.assertEqual(export['collections'][1]['pages'][0]['body']['value'][0]['id'], 'opaque-source-id')
        generated = generate(result['export'],result['context'],self.folder/'review')
        self.assertFalse(generated['offline_mapping_complete'])
        self.assertTrue(generated['preservation_verified'])
        self.assertTrue((self.folder/'review/BLOCKED.json').exists())
        self.assertFalse(list((self.folder/'review').rglob('*.tf')))


if __name__ == '__main__':
    unittest.main()
