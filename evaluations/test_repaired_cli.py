"""Integrated CLI boundary checks; invoke the real local pipeline."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import runpy

ROOT = Path(__file__).resolve().parents[1]


class RepairedCli(unittest.TestCase):
    def invoke(self, source, output, context=None):
        return subprocess.run([
            sys.executable, str(ROOT / 'tools/build-reference.py'),
            '--input', str(source), '--context', str(context or ROOT / 'examples/context.json'),
            '--output', str(output)], capture_output=True, text=True, timeout=30)

    def test_success_requires_independent_preservation_receipt(self):
        source = ROOT / 'examples/supported/input/export.json'
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'out'
            result = self.invoke(source, dest)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertTrue(receipt.get('preservation_verified'), 'CLI must gate writes through independent preservation')
            stored = json.loads((dest / 'adoption/source-receipt.json').read_text())
            self.assertEqual(stored['source_byte_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())

    def test_partial_pipeline_is_checked_and_remains_inactive(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'out'
            result = self.invoke(ROOT / 'examples/partial/input/export.json', dest)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertTrue(json.loads(result.stdout).get('preservation_verified'))
            self.assertEqual(list(dest.rglob('*.tf')), [])
            self.assertEqual(json.loads((dest / 'commands/command-cards.json').read_text())['cards'], [])

    def test_duplicate_key_and_float_input_never_write(self):
        for raw in ['{"schema_version":"1.0.0","schema_version":"1.0.0"}', '{"number":1.5}']:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / 'bad.json'; source.write_text(raw)
                dest = Path(tmp) / 'out'; result = self.invoke(source, dest)
                self.assertEqual(result.returncode, 3)
                self.assertFalse(dest.exists())

    def test_parser_integer_boundary_matches_oracle(self):
        load = runpy.run_path(str(ROOT / 'tools/build-reference.py'))['load_with_bytes']
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'number.json'
            for value in [-9007199254740991, 9007199254740991]:
                source.write_text(json.dumps({'number': value}))
                self.assertEqual(load(source)[0]['number'], value)
            for value in [-9007199254740992, 9007199254740992]:
                source.write_text(json.dumps({'number': value}))
                with self.assertRaises(ValueError):
                    load(source)

    def test_unsupported_canary_never_enters_cli_or_written_artifacts(self):
        source = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        source['collections'][1]['pages'][0]['body']['value'][0]['settingInstance']['CLI_UNKNOWN_CANARY'] = 'CLI_UNKNOWN_CANARY'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'source.json'; path.write_text(json.dumps(source))
            dest = Path(tmp) / 'out'; result = self.invoke(path, dest)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn('CLI_UNKNOWN_CANARY', result.stdout + result.stderr)
            for artifact in dest.rglob('*'):
                if artifact.is_file():
                    self.assertNotIn(b'CLI_UNKNOWN_CANARY', artifact.read_bytes(), str(artifact))


if __name__ == '__main__':
    unittest.main()
