import unittest,yaml
from pathlib import Path
R=Path(__file__).resolve().parents[1]
class Wizard(unittest.TestCase):
 def setUp(self):
  self.m=yaml.safe_load((R/'wizard/wizard-state-machine.yaml').read_text());self.q=yaml.safe_load((R/'wizard/wizard-questions.yaml').read_text())['questions']
 def test_all_states_and_questions_close(self):
  states=self.m['states'];self.assertIn(self.m['initial'],states)
  for name,state in states.items():
   for target in state['on'].values():self.assertIn(target,states)
   q=state['question_id']
   if q:
    self.assertIn(q,self.q)
    self.assertEqual(set(state['on']),{x['id'] for x in self.q[q]['choices']})
    self.assertIn(self.q[q]['recommended'],state['on'])
   if state['terminal']:self.assertFalse(state['on'])
 def test_missing_seven_old_states_now_defined(self):
  self.assertTrue({'blocked_with_offline_alternative','handoff_only','mapping_gap_decision','ownership_conflict','ownership_question','repair_generated','review_existing'}<=set(self.m['states']))
 def test_synthetic_transcripts_are_valid_paths(self):
  cases=yaml.safe_load((R/'wizard/transition-cases.yaml').read_text())
  for path in cases['paths'].values():
   for i in range(0,len(path)-2,2):self.assertEqual(self.m['states'][path[i]]['on'][path[i+1]],path[i+2])
  for c in cases['invalid_cases']:self.assertNotIn(c['event'],self.m['states'][c['state']]['on'])
 def test_no_live_execution_states(self):
  self.assertTrue(all(s['effect_class'] in {'local_read','local_write','emit_only'} for s in self.m['states'].values()))
if __name__=='__main__':unittest.main()
