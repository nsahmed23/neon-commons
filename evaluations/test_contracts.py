import json,unittest
from pathlib import Path
from jsonschema import Draft202012Validator,FormatChecker
R=Path(__file__).resolve().parents[1]
class Contracts(unittest.TestCase):
 def test_contracts_and_examples(self):
  cases=json.loads((R/'contracts/examples/test-cases.json').read_text())
  self.assertGreaterEqual(len(cases),12)
  for c in cases:
   with self.subTest(schema=c['schema']):
    s=json.loads((R/'contracts'/c['schema']).read_text());Draft202012Validator.check_schema(s);v=Draft202012Validator(s,format_checker=FormatChecker())
    v.validate(json.loads((R/'contracts'/c['valid']).read_text()))
    self.assertTrue(list(v.iter_errors(json.loads((R/'contracts'/c['invalid']).read_text()))))
 def test_all_exports_validate(self):
  v=Draft202012Validator(json.loads((R/'contracts/export-intake.schema.json').read_text()),format_checker=FormatChecker())
  for p in R.glob('examples/*/input/export.json'):v.validate(json.loads(p.read_text()))
 def test_all_normalized_validate(self):
  v=Draft202012Validator(json.loads((R/'contracts/observed-inventory.schema.json').read_text()),format_checker=FormatChecker())
  for p in R.glob('examples/*/expected/normalized.json'):v.validate(json.loads(p.read_text()))
if __name__=='__main__':unittest.main()
