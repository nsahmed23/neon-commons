import json,unittest
from pathlib import Path
from reference.core import normalize
R=Path(__file__).resolve().parents[1];P='22222222-2222-4222-8222-222222222222';T='11111111-1111-4111-8111-111111111111'
class IntakeEdges(unittest.TestCase):
 def base(self):return json.loads((R/'examples/supported/input/export.json').read_text())
 def test_wrong_collection_owner_url(self):
  b=self.base();c=next(x for x in b['collections'] if x['kind']=='settings');c['pages'][0]['request_url']=c['pages'][0]['request_url'].replace(P,'99999999-9999-4999-8999-999999999999');self.assertTrue(normalize(b,P,T)['blockers'])
 def test_prefix_is_not_route(self):
  b=self.base();b['collections'][0]['pages'][0]['request_url']='https://graph.microsoft.com/beta/deviceManagement/configurationPoliciesNotAnApi';self.assertTrue(normalize(b,P,T)['blockers'])
 def test_unknown_nested_template_metadata(self):
  b=self.base();b['collections'][0]['pages'][0]['body']['value'][0]['templateReference']['futureRequiredSetting']=123;self.assertTrue(normalize(b,P,T)['blockers'])
