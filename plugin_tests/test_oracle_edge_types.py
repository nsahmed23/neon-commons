"""Mutations must fail independent preservation checks even with fresh hashes."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from reference.core import normalize, generate_files
from reference.invariants import compare

ROOT = Path(__file__).resolve().parents[1]

class OracleArtifactEdgeTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((ROOT/'examples/supported/input/export.json').read_text())
        self.context = json.loads((ROOT/'examples/context.json').read_text())
        self.normalized = normalize(self.source, self.context['selected_policy_id'], self.context['tenant_id'])
        self.files = generate_files(self.normalized, self.context)

    def check(self, files):
        if 'generated-files.json' in files:
            manifest = json.loads(files['generated-files.json'])
            manifest['files'] = {k:hashlib.sha256(v.encode()).hexdigest() for k,v in files.items() if k != 'generated-files.json'}
            files['generated-files.json'] = json.dumps(manifest)
        return compare(self.source, self.normalized, files, self.context)

    def test_unmodified_control(self):
        self.assertEqual(self.check(self.files), [])

    def test_numeric_command_effect_is_not_boolean(self):
        files = copy.deepcopy(self.files)
        card = json.loads(files['commands/command-cards.json'])
        card['cards'][0]['effects']['network'] = 1
        files['commands/command-cards.json'] = json.dumps(card)
        self.assertIn('generated_command_contract_changed', self.check(files))

    def test_duplicate_json_member_rejected_even_if_last_value_correct(self):
        files = copy.deepcopy(self.files)
        name = 'adoption/capability.json'
        files[name] = '{"offline_mapping_complete": false,' + files[name].lstrip()[1:]
        self.assertIn('generated_json_invalid', self.check(files))

    def test_yaml_zero_is_not_boolean_false(self):
        files = copy.deepcopy(self.files)
        self.assertIn('apply_auto_approve: false', files['atmos.yaml'])
        files['atmos.yaml'] = files['atmos.yaml'].replace('apply_auto_approve: false', 'apply_auto_approve: 0')
        self.assertIn('generated_stack_guard_changed', self.check(files))
