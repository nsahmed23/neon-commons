"""Bounded GET retry contracts; fixtures never authenticate a live tenant."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from intune_iac import capture as module
from intune_iac.capture_adapter import load_capture
from intune_iac.io import AppError

T = '11111111-1111-4111-8111-111111111111'
P = '22222222-2222-4222-8222-222222222222'
ROOT = module.GRAPH_ROOT


class CaptureRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'capture'
        fixture = Path(__file__).resolve().parents[1]/'examples/supported/input/export.json'
        source = json.loads(fixture.read_bytes())
        self.responses = {}
        for collection in source['collections']:
            for page in collection['pages']:
                body = copy.deepcopy(page['body'])
                if collection['kind'] == 'assignments':
                    for row in body['value']: row.update(source='direct', sourceId=None)
                self.responses[page['request_url']] = (200, json.dumps(body).encode())
        self.calls = []; self.events = []

    def run_capture(self, first=(), **kwargs):
        pending = list(first)
        def transport(url):
            self.calls.append(url)
            value = pending.pop(0) if url == ROOT and pending else self.responses[url]
            if isinstance(value, BaseException): raise value
            return value
        return module.capture(T, P, self.path, transport=transport, **kwargs)

    def receipt(self): return json.loads((self.path/'capture-receipt.json').read_bytes())
    def exported(self): return json.loads((self.path/'export.json').read_bytes())
    def rewrite(self, receipt): (self.path/'capture-receipt.json').write_text(json.dumps(receipt))

    def test_transient_get_is_retried_instead_of_permanently_partial(self):
        with patch.object(module.time, 'sleep'):
            result = self.run_capture([(429, b'{"error":{"message":"RESTRICTED-CANARY"}}')])
        self.assertEqual(result['status'], 'captured')
        self.assertEqual(self.calls[:2], [ROOT, ROOT])
        self.assertNotIn('RESTRICTED-CANARY', json.dumps(result))

    def test_retry_after_zero_preserves_every_raw_attempt_and_one_export_page(self):
        raw = b'{"error":{"message":"RESTRICTED-CANARY"}}'
        result = self.run_capture([(429, raw, {'Retry-After':'0'})], progress=self.events.append)
        receipt = self.receipt(); exported = self.exported()
        self.assertEqual(result['status'], 'captured')
        self.assertEqual(receipt['schema_version'], '1.1.0')
        self.assertEqual(len(receipt['pages']), 4)
        self.assertEqual(len(exported['collections'][0]['pages']), 1)
        self.assertEqual((self.path/receipt['pages'][0]['raw_path']).read_bytes(), raw)
        self.assertEqual(receipt['attempts'][0]['retry_delay_seconds'], 0)
        self.assertTrue(receipt['attempts'][0]['wait_completed'])
        self.assertEqual(self.events[0]['retry_in_seconds'], 0)
        batch = load_capture(self.path, T)
        self.assertEqual(batch['status'], 'complete')
        self.assertEqual(batch['source']['capture_attempts']['attempt_count'], 4)
        self.assertEqual(batch['source']['capture_attempts']['retry_count'], 1)
        self.assertNotIn('RESTRICTED-CANARY', json.dumps(batch))

    def test_retry_after_above_cap_stops_without_early_retry(self):
        result = self.run_capture([(429, b'{}', {'Retry-After':'31'})], max_retry_delay_seconds=30)
        self.assertEqual(self.calls.count(ROOT), 1)
        self.assertEqual(result['coverage'][0]['reason'], 'retry_delay_limit')
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(load_capture(self.path,T)['status'], 'partial')

    def test_oversized_retry_after_does_not_degrade_into_early_retry(self):
        with patch.object(module.time,'sleep'):
            result=self.run_capture([(429,b'{}',{'Retry-After':'9'*200})])
        self.assertEqual(self.calls.count(ROOT),1)
        self.assertEqual(result['coverage'][0]['reason'],'retry_delay_limit')

    def test_retry_after_date_uses_wall_time_but_deadline_remains_monotonic(self):
        with patch.object(module.time, 'time', return_value=0), patch.object(module.time, 'sleep'):
            result = self.run_capture([(503,b'{}',{'Retry-After':'Thu, 01 Jan 1970 00:00:02 GMT'})], progress=self.events.append)
        self.assertEqual(result['status'], 'captured')
        self.assertEqual(self.events[0]['retry_in_seconds'],2)
        self.assertEqual(self.receipt()['attempts'][0]['retry_delay_source'],'retry_after_date')

    def test_untrusted_header_is_never_displayed_and_uses_bounded_backoff(self):
        with patch.object(module.time, 'sleep'):
            self.run_capture([(503,b'{}',{'Retry-After':'\x1b]0;SECRET\x07'})],progress=self.events.append)
        self.assertEqual(self.events[0]['retry_in_seconds'],1)
        self.assertNotIn('SECRET',json.dumps(self.events)+json.dumps(self.receipt()))

    def test_total_attempt_budget_includes_retries(self):
        result = self.run_capture([(429,b'{}',{'Retry-After':'0'})],max_pages=1)
        self.assertEqual(self.calls,[ROOT])
        self.assertEqual(result['status'],'partial')
        self.assertEqual(self.receipt()['attempt_count'],1)
        self.assertEqual(load_capture(self.path,T)['status'],'partial')

    def test_every_retry_body_counts_toward_global_byte_budget(self):
        with patch.object(module,'MAX_TOTAL_BYTES',60):
            result=self.run_capture([(429,b' '*50,{'Retry-After':'0'})])
        receipt=self.receipt()
        self.assertEqual(sum(r['source_bytes'] for r in receipt['pages']),60)
        self.assertEqual(self.calls,[ROOT,ROOT])
        self.assertEqual(result['coverage'][0]['reason'],'byte_limit')
        self.assertFalse(receipt['pages'][-1]['raw_capture_complete'])

    def test_truncated_transient_body_is_not_retried(self):
        with patch.object(module,'MAX_PAGE_BYTES',20):
            result=self.run_capture([(429,b' '*21,{'Retry-After':'0'})])
        self.assertEqual(self.calls.count(ROOT),1)
        self.assertEqual(result['coverage'][0]['reason'],'byte_limit')

    def test_per_page_attempt_exhaustion_is_bounded_and_partial(self):
        result=self.run_capture([(503,b'{}',{'Retry-After':'0'})]*5,max_attempts_per_page=2)
        self.assertEqual(self.calls.count(ROOT),2)
        self.assertEqual(result['coverage'][0]['reason'],'retry_exhausted')
        self.assertEqual(load_capture(self.path,T)['status'],'partial')

    def test_delay_beyond_remaining_deadline_is_not_slept_or_retried(self):
        with patch.object(module.time,'sleep') as sleep:
            result=self.run_capture([(429,b'{}',{'Retry-After':'1'})],max_elapsed_seconds=.1)
        self.assertFalse(sleep.called)
        self.assertEqual(self.calls.count(ROOT),1)
        self.assertEqual(result['coverage'][0]['reason'],'time_limit')

    def test_transient_transport_error_retains_safe_attempt_record(self):
        with patch.object(module.time,'sleep'):
            result=self.run_capture([TimeoutError('Bearer SECRET-CANARY')])
        self.assertEqual(result['status'],'captured')
        receipt=self.receipt()
        self.assertEqual(receipt['attempts'][0]['error'],'transport_failed')
        self.assertIsNone(receipt['attempts'][0]['raw_path'])
        self.assertNotIn('SECRET-CANARY',json.dumps(receipt))
        self.assertEqual(load_capture(self.path,T)['status'],'complete')

    def test_denied_and_redirect_are_not_retried(self):
        for status in (401,403,301,302,400,404,500):
            with self.subTest(status=status):
                self.path=Path(self.temp.name)/str(status);self.calls=[]
                result=self.run_capture([(status,b'{"error":{"message":"PRIVATE"}}',{'Location':'https://evil.invalid/'})])
                self.assertEqual(self.calls.count(ROOT),1)
                self.assertEqual(result['status'],'partial')
                self.assertNotIn('PRIVATE',json.dumps(result))

    def test_retry_does_not_relax_continuation_origin_or_collection(self):
        for next_url in ('https://evil.invalid/page',ROOT+'/'+P+'/assignments'):
            with self.subTest(next_url=next_url),patch.object(module.time,'sleep'):
                self.path=Path(self.temp.name)/str(len(list(Path(self.temp.name).iterdir())))
                self.calls=[]
                self.responses[ROOT]=(200,json.dumps({'value':[],'@odata.nextLink':next_url}).encode())
                result=self.run_capture([(429,b'{}')])
                self.assertEqual(self.calls.count(ROOT),2)
                self.assertEqual(result['coverage'][0]['reason'],'untrusted_continuation')

    def test_interrupt_during_backoff_persists_partial_capture_and_no_more_requests(self):
        with patch.object(module.time,'sleep',side_effect=KeyboardInterrupt):
            result=self.run_capture([(429,b'{}')])
        self.assertTrue(result['cancelled'])
        self.assertEqual(self.calls,[ROOT])
        self.assertTrue(all(c['reason']=='cancelled' for c in result['coverage']))
        self.assertEqual(self.receipt()['attempt_count'],1)
        self.assertFalse(self.receipt()['attempts'][0]['wait_completed'])
        self.assertEqual(load_capture(self.path,T)['status'],'partial')

    def test_retry_chain_tampering_is_rejected(self):
        self.run_capture([(429,b'{}',{'Retry-After':'0'})])
        original=self.receipt()
        for change in ('wrong_number','wrong_url','wrong_delay','wrong_raw','suppress_success','unfinished_wait','wrong_attempt','downgrade'):
            receipt=copy.deepcopy(original)
            if change=='wrong_number':receipt['attempts'][1]['number']=1
            if change=='wrong_url':receipt['attempts'][0]['request_url']='https://evil.invalid'
            if change=='wrong_delay':receipt['attempts'][0]['retry_delay_seconds']=1000
            if change=='wrong_raw':receipt['attempts'][0]['raw_path']=receipt['attempts'][1]['raw_path']
            if change=='suppress_success':receipt['pages'][1]['export_page']=False
            if change=='unfinished_wait':receipt['attempts'][0]['wait_completed']=False
            if change=='wrong_attempt':receipt['attempts'][1]['attempt_in_page']=1
            if change=='downgrade':receipt['schema_version']='1.0.0'
            self.rewrite(receipt)
            with self.subTest(change=change),self.assertRaises(AppError):load_capture(self.path,T)

    def test_legacy_receipt_remains_importable_without_retry_inference(self):
        self.run_capture()
        receipt=self.receipt();receipt['schema_version']='1.0.0';receipt.pop('attempts',None)
        receipt.pop('cancelled',None)
        for row in receipt['pages']:
            row.pop('attempt_number',None);row.pop('export_page',None)
        self.rewrite(receipt)
        self.assertEqual(load_capture(self.path,T)['status'],'complete')

    def test_invalid_retry_limits_do_not_fetch_or_create_directory(self):
        for keyword,value in (('max_attempts_per_page',0),('max_attempts_per_page',True),('max_attempts_per_page',11),('max_elapsed_seconds',0),('max_elapsed_seconds',float('nan')),('max_retry_delay_seconds',31)):
            with self.subTest(keyword=keyword,value=value),self.assertRaises(AppError):
                self.run_capture(**{keyword:value})
        self.assertEqual(self.calls,[]);self.assertFalse(self.path.exists())

    def test_native_dns_timeout_cancels_before_any_credential_send(self):
        from intune_iac import identity_binding as identity
        entered=threading.Event();release=threading.Event();finished=threading.Event();sent=[]
        class Connection:
            sock=None
            def __init__(self,*args,**kwargs):pass
            def connect(self):entered.set();release.wait(1)
            def request(self,*args,**kwargs):sent.append(args)
            def close(self):finished.set()
        with patch.object(identity.http.client,'HTTPSConnection',Connection),patch.object(identity,'_system_tls_context',return_value=None),patch.dict(os.environ,{'TEST_CAPTURE_TOKEN':'SECRET-CANARY'}):
            started=time.monotonic()
            try:
                result=module.capture(T,P,self.path,token_env='TEST_CAPTURE_TOKEN',max_elapsed_seconds=.03)
                self.assertLess(time.monotonic()-started,.5)
                self.assertTrue(entered.is_set())
                self.assertEqual(result['status'],'partial')
            finally:release.set();finished.wait(1)
        self.assertEqual(sent,[])
        self.assertNotIn('SECRET-CANARY',json.dumps(self.receipt()))

    def test_native_interrupt_during_connect_retains_cancelled_attempt_without_send(self):
        from intune_iac import identity_binding as identity
        entered=threading.Event();release=threading.Event();finished=threading.Event();sent=[]
        original=identity.queue.Queue
        class InterruptQueue(original):
            def get(self,**kwargs):
                if not entered.wait(1):raise AssertionError('Connection not entered')
                raise KeyboardInterrupt()
        class Connection:
            sock=None
            def __init__(self,*args,**kwargs):pass
            def connect(self):entered.set();release.wait(1)
            def request(self,*args,**kwargs):sent.append(args)
            def close(self):finished.set()
        with patch.object(identity.http.client,'HTTPSConnection',Connection),patch.object(identity,'_system_tls_context',return_value=None),patch.object(identity.queue,'Queue',InterruptQueue),patch.dict(os.environ,{'TEST_CAPTURE_TOKEN':'SECRET-CANARY'}):
            try:result=module.capture(T,P,self.path,token_env='TEST_CAPTURE_TOKEN')
            finally:release.set();finished.wait(1)
        self.assertEqual(sent,[]);self.assertTrue(result['cancelled'])
        self.assertEqual(self.receipt()['attempts'][0]['error'],'cancelled')
        self.assertEqual(load_capture(self.path,T)['status'],'partial')


if __name__=='__main__':unittest.main()
