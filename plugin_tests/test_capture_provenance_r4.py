"""Laboratory labels stay accurate without granting real service authority."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from intune_iac import capture, production
from intune_iac.capture_adapter import load_capture
from intune_iac.identity_binding import ClientSecretHandle
from intune_iac.io import AppError, canonical
from intune_iac.observation_jobs import _Fixture
from intune_iac.observation_reader import ReaderSpec, bind_laboratory_reader
from intune_iac.synthetic import generate_estate
from plugin_tests.test_observation_reader_r4 import fixture_for, CLIENT, PRINCIPAL


class CaptureProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.estate=generate_estate(seed=840,policy_count=1)
        self.tenant=self.estate['truth']['tenant_id'];self.oid=self.estate['truth']['policies'][0]['id']

    def captured(self):
        credential=ClientSecretHandle('SYNTHETIC-ONLY-PROVENANCE-TEST');self.addCleanup(credential.close)
        reader=bind_laboratory_reader(ReaderSpec(self.tenant,CLIENT,PRINCIPAL,(self.oid,)),credential=credential,
            transport=_Fixture(canonical(fixture_for(self.estate))))
        self.addCleanup(reader.close)
        result=reader.capture(self.oid,self.root/'capture')
        return result,[json.loads((self.root/'capture'/name).read_bytes()) for name in ('export.json','context.json','capture-receipt.json')]

    def test_typed_laboratory_capture_preserves_markers_and_has_no_observed_toolchain(self):
        result,(source,context,receipt)=self.captured();batch,identity=result.verified()
        self.assertIs(source['synthetic'],True);self.assertIs(context['source_is_synthetic'],True)
        self.assertIs(receipt['source_is_synthetic'],True);self.assertIs(receipt['toolchain_observed'],False)
        self.assertEqual(receipt['context_assurance'],'proposed_emit_only_labels_not_observed_toolchain')
        self.assertTrue({'engine_version','atmos_version','provider_version'}.isdisjoint(context))
        self.assertIs(batch['source']['source_is_synthetic'],True)
        self.assertIs(identity['source_authenticity_verified'],False);self.assertIs(identity['execution_authorized'],False)
        self.assertEqual(identity['evidence_class'],'graph_reader_laboratory')
        self.assertIs(receipt['source_authenticity_verified'],False)
        self.assertIsNotNone(batch['body'])

    def test_observation_mapping_does_not_relax_production_candidate_gate(self):
        _,(source,context,receipt)=self.captured();before=canonical(source)
        mapped=production.normalize_observation(source,context)
        self.assertIsNotNone(mapped['configuration']);self.assertIs(mapped['source_is_synthetic'],True)
        self.assertIs(mapped['execution_authorized'],False);self.assertEqual(canonical(source),before)
        with self.assertRaises(AppError):production.normalize(source,context)
        plain=load_capture(self.root/'capture',self.tenant)
        self.assertEqual(plain['source']['evidence_class'],'graph_capture_unverified')
        self.assertIs(plain['source']['source_authenticity_verified'],False)

    def test_changed_marker_rejected_even_with_consistent_document_digest(self):
        _,(_,context,receipt)=self.captured();context['source_is_synthetic']=False
        data=canonical(context)+b'\n';(self.root/'capture/context.json').write_bytes(data)
        receipt['context_byte_sha256']=hashlib.sha256(data).hexdigest()
        (self.root/'capture/capture-receipt.json').write_bytes(canonical(receipt)+b'\n')
        with self.assertRaises(AppError):load_capture(self.root/'capture',self.tenant)

    def test_invalid_provenance_rejected_before_output_or_request(self):
        with self.assertRaises(AppError) as caught:
            capture.capture(self.tenant,self.oid,self.root/'invalid',transport=lambda url:self.fail('No request'),source_is_synthetic=1)
        self.assertEqual(caught.exception.code,'capture_provenance_invalid');self.assertFalse((self.root/'invalid').exists())
