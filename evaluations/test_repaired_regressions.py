"""Run the supplied desired-behavior assertions against this repaired package.

Only F07's version-specific property lookup changes: v2 persists fingerprints
and an artifact index. Actual receipt reconstruction/resume is tested separately
against the integrated workflow, including both originally reported cases.
"""
import importlib.util
import json
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
previous = os.environ.get('APPENDIX_B_PACK')
os.environ['APPENDIX_B_PACK'] = str(ROOT)
spec = importlib.util.spec_from_file_location('supplied_regression_cases', ROOT / 'corrections/regressions/test_original_regressions.py')
supplied = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supplied)
if previous is None:
    os.environ.pop('APPENDIX_B_PACK', None)
else:
    os.environ['APPENDIX_B_PACK'] = previous


class IntegratedRegressions(supplied.Regressions):
    def test_F07_session_fingerprints_complete(self):
        schema = json.loads((ROOT / 'contracts/session-state.schema.json').read_text())
        self.assertEqual(schema['properties']['schema_version']['const'], '2.0.0')
        props = schema['properties']['fingerprints']['properties']
        required = {'selected_ids_digest', 'ownership_digest', 'provider_version', 'plan_digest', 'identity_digest'}
        self.assertTrue(required <= props.keys())
        self.assertIn('artifact_index', schema['required'])


class PositiveControls(supplied.ExistingControls):
    pass


if __name__ == '__main__':
    unittest.main()
