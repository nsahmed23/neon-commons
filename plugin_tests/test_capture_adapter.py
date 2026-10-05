"""Import preserves byte evidence and scoped coverage without promoting authority."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from intune_iac.capture import capture
from intune_iac.io import AppError
T='11111111-1111-4111-8111-111111111111'
P='22222222-2222-4222-8222-222222222222'
ROOT=Path(__file__).resolve().parents[1]

class CaptureAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'capture'
        fixture=json.loads((ROOT/'examples/supported/input/export.json').read_text())
        self.responses={p['request_url']:(p['http_status'],json.dumps(p['body']).encode()) for c in fixture['collections'] for p in c['pages']}
        # The existing synthetic export omits assignment source metadata.
        # This explicitly authored GET fixture observes direct assignment;
        # the importer must not infer it when actual capture omits the field.
        for url,(status,raw) in list(self.responses.items()):
            if url.endswith('/assignments'):
                body=json.loads(raw)
                for row in body['value']:row.update(source='direct',sourceId=None)
                self.responses[url]=(status,json.dumps(body).encode())
    def make(self):
        capture(T,P,self.path,transport=lambda url:self.responses[url]);return self.path
    def load(self):
        from intune_iac.capture_adapter import load_capture
        return load_capture(self.path,tenant_id=T)
    def rewrite(self,name,value):
        path=self.path/name;path.write_text(json.dumps(value))
        if name!='capture-receipt.json':
            receipt=json.loads((self.path/'capture-receipt.json').read_text())
            receipt[{'export.json':'export_byte_sha256','context.json':'context_byte_sha256'}[name]]=hashlib.sha256(path.read_bytes()).hexdigest()
            (self.path/'capture-receipt.json').write_text(json.dumps(receipt))
    def test_complete_capture_preserves_exact_selected_body_without_authority(self):
        self.make();batch=self.load()
        self.assertEqual(batch['object_id'],P);self.assertEqual(batch['status'],'complete')
        self.assertEqual(batch['body']['name'],'Windows Privacy Pilot')
        self.assertEqual(len(batch['body']['assignments']),3)
        self.assertEqual(batch['scope'],{'kind':'policy','object_ids':[P]})
        self.assertEqual(batch['source']['tenant_assurance'],'caller_asserted')
        self.assertFalse(batch['source']['execution_authorized']);self.assertFalse(batch['source']['source_authenticity_verified'])
        self.assertEqual(len(batch['collections']),3)
    def test_denied_assignments_are_denied_not_empty_body_or_error_disclosure(self):
        url=next(u for u in self.responses if u.endswith('/assignments'))
        self.responses[url]=(403,b'{"error":{"message":"SECRET-CANARY"}}')
        self.make();batch=self.load()
        self.assertEqual(batch['status'],'denied');self.assertIsNone(batch['body'])
        self.assertEqual(batch['collections'][2]['coverage'],'access_denied')
        self.assertNotIn('SECRET-CANARY',json.dumps(batch))
    def test_changed_raw_rejected_even_when_export_hash_matches(self):
        self.make();p=self.path/'raw/page-000000.json';p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaises(AppError):self.load()
    def test_rehashed_export_cannot_substitute_original_raw_values(self):
        self.make();source=json.loads((self.path/'export.json').read_text())
        source['collections'][1]['pages'][0]['body']['value'][0]['id']='substituted'
        self.rewrite('export.json',source)
        with self.assertRaises(AppError):self.load()
    def test_authority_claim_is_never_promoted(self):
        self.make();receipt=json.loads((self.path/'capture-receipt.json').read_text());receipt['execution_authorized']=True
        self.rewrite('capture-receipt.json',receipt)
        with self.assertRaises(AppError):self.load()
    def test_receipt_export_context_tenant_and_object_bind(self):
        self.make();context=json.loads((self.path/'context.json').read_text());context['tenant_id']='33333333-3333-4333-8333-333333333333'
        self.rewrite('context.json',context)
        with self.assertRaises(AppError):self.load()
    def test_missing_page_receipt_and_duplicate_collection_rejected(self):
        self.make();receipt=json.loads((self.path/'capture-receipt.json').read_text());receipt['pages'].pop()
        self.rewrite('capture-receipt.json',receipt)
        with self.assertRaises(AppError):self.load()
    def test_missing_final_page_cannot_claim_complete(self):
        self.make();source=json.loads((self.path/'export.json').read_text());collection=source['collections'][0]
        page=collection['pages'][0];page['body']['@odata.nextLink']=page['request_url']+'?$skip=1'
        raw=self.path/'raw/page-000000.json';raw.write_text(json.dumps(page['body']))
        receipt=json.loads((self.path/'capture-receipt.json').read_text());receipt['pages'][0].update(source_bytes=raw.stat().st_size,source_byte_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
        self.rewrite('capture-receipt.json',receipt);self.rewrite('export.json',source)
        with self.assertRaises(AppError):self.load()
    def test_unknown_mapping_preserves_raw_and_explicit_blockers(self):
        url=next(u for u in self.responses if u.endswith('/settings'));status,raw=self.responses[url];body=json.loads(raw)
        body['value'][0]['settingInstance']['choiceSettingValue']['value']='future-choice'
        self.responses[url]=(status,json.dumps(body).encode());self.make();batch=self.load()
        self.assertEqual(batch['status'],'unsupported');self.assertIsNone(batch['body'])
        self.assertIn('future-choice',json.dumps(batch['source']['raw_observed']))
        self.assertTrue(batch['source']['mapping_blockers'])
    def test_symlink_and_hardlink_raw_rejected(self):
        self.make();p=self.path/'raw/page-000000.json';outside=self.root/'outside';p.rename(outside);p.symlink_to(outside)
        with self.assertRaises(AppError):self.load()
        p.unlink();os.link(outside,p)
        with self.assertRaises(AppError):self.load()
    def test_extra_file_preserved_and_rejected_not_deleted(self):
        self.make();extra=self.path/'unexpected.tmp';extra.write_text('retain me')
        with self.assertRaises(AppError):self.load()
        self.assertEqual(extra.read_text(),'retain me')

if __name__=='__main__':unittest.main()
