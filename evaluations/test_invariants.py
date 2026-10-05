import copy,json,unittest
from pathlib import Path
from reference import invariants
R=Path(__file__).resolve().parents[1]
class IndependentInvariants(unittest.TestCase):
    def setUp(self):
        self.raw=json.loads((R/'examples/supported/input/export.json').read_text())
        self.n=json.loads((R/'examples/supported/expected/normalized.json').read_text())
    def test_reference_preserves(self): self.assertEqual(invariants.compare(self.raw,self.n),[])
    def test_deleted_exclusion_is_detected(self):
        self.n['desired']['assignments']=[x for x in self.n['desired']['assignments'] if x['type']!='exclusionGroupAssignmentTarget']
        self.assertIn('assignment_multiset_changed',invariants.compare(self.raw,self.n))
    def test_filter_mode_mutation_is_detected(self):
        self.n['desired']['assignments'][0]['filter_type']='exclude'
        self.assertIn('assignment_multiset_changed',invariants.compare(self.raw,self.n))
    def test_id_change_detected(self):
        self.n['object_id']='99999999-9999-4999-8999-999999999999'
        self.assertIn('selected_id_not_present',invariants.compare(self.raw,self.n))
    def test_field_lineage_missing_detected(self):
        self.n['field_accounting']=self.n['field_accounting'][1:]
        self.assertIn('source_field_accounting_not_closed',invariants.compare(self.raw,self.n))
    def test_setting_value_change_detected(self):
        self.n['desired']['settings']['settings'][0]['settingInstance']['choiceSettingValue']['value']='DIFFERENT'
        self.assertIn('settings_subtree_changed',invariants.compare(self.raw,self.n))
