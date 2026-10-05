import unittest,copy
from reference import approval
class Approval(unittest.TestCase):
 def setUp(self):
  self.r={k:'a'*64 for k in ['source_digest','configuration_digest','plan_digest','provider_lock_digest','cohort_digest']}
  self.r.update(git_revision='b'*40,tenant_id='tenant',subscription_id='sub',component='intune-reference',stack='reference-dev',engine='tofu',engine_version='1.10.0',atmos_version='1.199.0',principal_id='principal',expires_at='2026-09-30T14:00:00Z')
 def test_same(self):self.assertEqual(approval.mismatches(self.r,copy.deepcopy(self.r),'2026-09-30T13:00:00Z'),[])
 def test_stale_plan(self):
  x=copy.deepcopy(self.r);x['plan_digest']='c'*64
  self.assertIn('plan_digest',approval.mismatches(self.r,x,'2026-09-30T13:00:00Z'))
 def test_wrong_tenant(self):
  x=copy.deepcopy(self.r);x['tenant_id']='other'
  self.assertIn('tenant_id',approval.mismatches(self.r,x,'2026-09-30T13:00:00Z'))
 def test_expired(self):self.assertIn('expired',approval.mismatches(self.r,self.r,'2026-09-30T15:00:00Z'))
 def test_missing(self):
  x=copy.deepcopy(self.r);del x['provider_lock_digest']
  self.assertIn('provider_lock_digest',approval.mismatches(self.r,x,'2026-09-30T13:00:00Z'))
 def test_naive_clock_rejected(self):
  with self.assertRaises(ValueError):approval.mismatches(self.r,self.r,'2026-09-30T13:00:00')
