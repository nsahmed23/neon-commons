import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    def test_saved_output_is_rederived_from_source_not_its_own_manifest(self):
        import hashlib
        from intune_iac.engine import generate, verify_project
        from intune_iac.io import AppError
        with tempfile.TemporaryDirectory() as td:
            output=Path(td)/'project'
            source=ROOT/'examples/supported/input/export.json'; context=ROOT/'examples/context.json'
            generate(source,context,output)
            path=output/'components/terraform/intune-reference/adoption-input.json'
            value=json.loads(path.read_text());value['desired']['assignments']=[]
            path.write_text(json.dumps(value))
            manifest=json.loads((output/'generated-files.json').read_text())
            manifest['files'][path.relative_to(output).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
            (output/'generated-files.json').write_text(json.dumps(manifest))
            with self.assertRaises(AppError):verify_project(source,context,output)

    def test_supported_generation_is_verified_and_changed_file_is_preserved(self):
        from intune_iac.engine import generate
        from intune_iac.io import AppError
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'project'
            result = generate(ROOT/'examples/supported/input/export.json', ROOT/'examples/context.json', output)
            self.assertTrue(result['preservation_verified'])
            self.assertFalse(result['execution_authorized'])
            target = output/'README.md'
            target.write_text('user edit')
            with self.assertRaises(AppError) as error:
                generate(ROOT/'examples/supported/input/export.json', ROOT/'examples/context.json', output)
            self.assertEqual(error.exception.code, 'output_conflict')
            self.assertEqual(target.read_text(), 'user edit')

    def test_denied_assignments_produce_no_active_iac(self):
        from intune_iac.engine import generate
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)/'project'
            result = generate(ROOT/'examples/access-denied/input/export.json', ROOT/'examples/context.json', output)
            self.assertFalse(result['offline_mapping_complete'])
            self.assertFalse(list(output.rglob('*.tf')))
            self.assertEqual(json.loads((output/'commands/command-cards.json').read_text())['cards'], [])

    def test_real_capture_is_review_only_and_never_spoofed(self):
        from intune_iac.engine import generate
        with tempfile.TemporaryDirectory() as td:
            source = json.loads((ROOT/'examples/supported/input/export.json').read_text())
            source['synthetic'] = False
            source['exporter'] = {'id':'company-capture','version':'1'}
            path = Path(td)/'source.json'; path.write_text(json.dumps(source))
            output = Path(td)/'project'
            result = generate(path, ROOT/'examples/context.json', output)
            self.assertFalse(result['offline_mapping_complete'])
            self.assertFalse(list(output.rglob('*.tf')))
            self.assertIn('reference_generator_accepts_synthetic_only', result['blocker_codes'])

    def test_duplicate_keys_and_nonfinite_fail_without_echoing_payload(self):
        from intune_iac.io import AppError, load_json
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'bad.json'
            for content in ['{"secret-canary":1,"secret-canary":2}', '{"secret-canary":NaN}']:
                path.write_text(content)
                with self.assertRaises(AppError) as error: load_json(path)
                self.assertNotIn('secret-canary', str(error.exception))

    def test_unsupported_value_does_not_escape_in_runtime_result(self):
        from intune_iac.engine import inspect_source
        with tempfile.TemporaryDirectory() as td:
            source = json.loads((ROOT/'examples/supported/input/export.json').read_text())
            source['unknownSecret'] = 'CANARY-NOT-FOR-REVIEW'
            path = Path(td)/'source.json'; path.write_text(json.dumps(source))
            # Closed intake rejects unknown top-level fields with safe diagnostics.
            from intune_iac.io import AppError
            with self.assertRaises(AppError) as error:
                inspect_source(path, ROOT/'examples/context.json')
            self.assertNotIn('CANARY', str(error.exception))


if __name__ == '__main__': unittest.main()
