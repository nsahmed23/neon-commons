import copy
import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import journey_native_atmos as jna
from intune_iac.io import AppError, canonical, digest, load_json, write_json
from intune_iac.repository import resolve_component
from plugin_tests import test_native_atmos_completion as fixtures


class NativeAtmosReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root/'repo'; self.repo.mkdir()
        fixtures.NativeAtmosTests().repository(self.repo)
        expected = resolve_component(self.repo, 'physical', 'policy')
        self.tool = {'version':jna.ATMOS_VERSION, 'sha256':jna.ATMOS_SHA256}
        self.report = {
            'status':'verified','native_executed':True,'execution_authorized':False,
            'tenant_authenticated':False,'tool':self.tool,
            'source_fingerprint':expected['source_fingerprint'],
            'logical_stack':'pilot','physical_manifest':'physical',
            'comparisons':{k:True for k in (*jna.SECTIONS,'logical_stack','physical_manifest','implementation')},
            'comparison_sha256':{k:{'expected':digest(expected['effective'].get(k)),
                                      'observed':digest(expected['effective'].get(k))} for k in jna.SECTIONS},
            **{k:'a'*64 for k in ('stdout_sha256','native_configuration_sha256','workspace_sha256','backend_sha256')},
            'stderr_sha256':hashlib.sha256(b'').hexdigest(),
        }
        self.receipt = self.root/'receipt.json'
        native = dict(expected['effective'],atmos_stack='pilot',atmos_manifest='physical',component=expected['implementation'])
        raw = canonical(native)
        self.report['stdout_sha256'] = hashlib.sha256(raw).hexdigest()
        self.report['native_configuration_sha256'] = digest(native)
        self.report['workspace_sha256'] = digest(native.get('workspace'))
        self.report['backend_sha256'] = digest({'type':native.get('backend_type'),'config':native.get('backend')})
        self.raw_path = self.receipt.with_name(self.receipt.name+'.stdout.json')
        write_json(self.raw_path,{'schema':'native-atmos-raw/1','stdout_base64':base64.b64encode(raw).decode(),
                                 'stderr_base64':'','exit_code':0,'output_truncated':False})
        tool = patch.object(jna,'_tool',return_value=self.tool);tool.start();self.addCleanup(tool.stop)
        with patch.object(jna,'resolve_native_atmos',return_value=self.report):
            jna.execute(self.repo,'physical','policy','fixture-tool',self.receipt)

    def reconstruct(self):
        return jna.reconstruct(self.repo,'physical','policy','fixture-tool',self.receipt)

    def test_valid_receipt_does_not_reexecute_native_process(self):
        with patch.object(jna,'resolve_native_atmos',side_effect=AssertionError('unexpected process')):
            result = self.reconstruct()
        self.assertTrue(result['native_executed'])
        self.assertFalse(result['tenant_authenticated'])
        self.assertFalse(result['execution_authorized'])

    def test_source_change_invalidates_before_completion_flag_can_help(self):
        p = self.repo/'stacks/physical.yaml';p.write_text(p.read_text().replace('value: 1','value: 2'))
        with self.assertRaises(AppError):self.reconstruct()

    def test_rehashed_false_section_claim_is_rejected_independently(self):
        evidence = load_json(self.receipt)
        evidence['report']['comparison_sha256']['vars']['observed'] = 'b'*64
        evidence['evidence_sha256'] = digest({k:v for k,v in evidence.items() if k!='evidence_sha256'})
        write_json(self.receipt,evidence)
        with self.assertRaises(AppError):self.reconstruct()

    def test_missing_raw_hash_and_false_authority_claim_are_rejected(self):
        saved = load_json(self.receipt)
        for mutate in (lambda r:r.pop('stdout_sha256'),lambda r:r.update(execution_authorized=True)):
            evidence = copy.deepcopy(saved);mutate(evidence['report'])
            evidence['evidence_sha256'] = digest({k:v for k,v in evidence.items() if k!='evidence_sha256'})
            write_json(self.receipt,evidence)
            with self.assertRaises(AppError):self.reconstruct()

    def test_wrong_stack_does_not_reuse_success(self):
        with self.assertRaises(AppError):
            jna.reconstruct(self.repo,'other','policy','fixture-tool',self.receipt)

    def test_missing_raw_transcript_invalidates_completion(self):
        self.raw_path.unlink()
        with self.assertRaises(AppError):self.reconstruct()

    def test_changed_tool_locator_invalidates_even_same_claimed_bytes(self):
        with self.assertRaises(AppError):
            jna.reconstruct(self.repo,'physical','policy','other-tool',self.receipt)

    def rewrite_report(self, evidence):
        evidence['evidence_sha256'] = digest({k:v for k,v in evidence.items() if k!='evidence_sha256'})
        write_json(self.receipt,evidence)

    def test_rehashed_workspace_and_backend_claims_must_match_raw(self):
        original = load_json(self.receipt)
        for key in ('workspace_sha256','backend_sha256'):
            with self.subTest(key=key):
                evidence = copy.deepcopy(original)
                evidence['report'][key] = '0'*64
                self.rewrite_report(evidence)
                with self.assertRaises(AppError):self.reconstruct()

    def test_rehashed_raw_workspace_and_backend_must_match_section_digest(self):
        original = load_json(self.receipt)
        raw_original = load_json(self.raw_path)
        for key,value in (('workspace','substituted'),('backend',{'path':'substituted'}),('backend_type','s3')):
            with self.subTest(key=key):
                evidence = copy.deepcopy(original)
                raw_evidence = copy.deepcopy(raw_original)
                native = jna.parse_json(base64.b64decode(raw_evidence['stdout_base64']))
                native[key] = value
                raw = canonical(native)
                raw_evidence['stdout_base64'] = base64.b64encode(raw).decode()
                evidence['report']['stdout_sha256'] = hashlib.sha256(raw).hexdigest()
                evidence['report']['native_configuration_sha256'] = digest(native)
                write_json(self.raw_path,raw_evidence)
                self.rewrite_report(evidence)
                with self.assertRaises(AppError):self.reconstruct()

    def test_comparison_requires_actual_boolean(self):
        original = load_json(self.receipt)
        for value in (1,1.0):
            with self.subTest(value=value):
                evidence = copy.deepcopy(original)
                evidence['report']['comparisons']['vars'] = value
                self.rewrite_report(evidence)
                with self.assertRaises(AppError):self.reconstruct()

    def test_exit_code_requires_actual_integer(self):
        original = load_json(self.raw_path)
        for value in (False,0.0):
            with self.subTest(value=value):
                raw = copy.deepcopy(original);raw['exit_code'] = value
                write_json(self.raw_path,raw)
                with self.assertRaises(AppError):self.reconstruct()

    def test_malformed_objects_raise_controlled_error(self):
        original = load_json(self.receipt)
        for value in ([],None):
            with self.subTest(value=value):
                evidence = copy.deepcopy(original);evidence['report'] = value
                self.rewrite_report(evidence)
                with self.assertRaises(AppError):self.reconstruct()
