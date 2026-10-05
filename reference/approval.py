"""Offline binding comparison. No match authenticates an approver or authorizes execution.

Structured v2 is the full target contract. The legacy flat interface is retained
for historical callers only and is explicitly not execution authorization.
"""
from datetime import datetime
from corrections.models.contract_model import approval_mismatches
FIELDS=['source_digest','configuration_digest','plan_digest','provider_lock_digest','cohort_digest','git_revision','tenant_id','subscription_id','component','stack','engine','engine_version','atmos_version','principal_id']
LEGACY_TARGET_FIELDS=['cloud','backend','state_key','service_endpoint','identity','selected_ids_digest','ownership_digest']
def _time(value):
 d=datetime.fromisoformat(value.replace('Z','+00:00'))
 if d.tzinfo is None:raise ValueError('Timezone-aware timestamp required')
 return d

def mismatches(expected,observed,now):
 if 'binding' in expected or expected.get('schema_version')=='2.0.0':
  binding=observed.get('binding') if isinstance(observed,dict) and 'binding' in observed else observed
  return approval_mismatches(expected,binding,now)
 # Every extra target field supplied by either side is bound. Omission is a mismatch.
 fields=FIELDS+[k for k in LEGACY_TARGET_FIELDS if k in expected or k in observed]
 errors=[k for k in fields if k not in expected or expected[k] is None or k not in observed or observed[k]!=expected[k]]
 if expected.get('engine')!='tofu':errors.append('enterprise_engine')
 if _time(now)>=_time(expected['expires_at']):errors.append('expired')
 if 'approved_at' in expected and _time(now)<_time(expected['approved_at']):errors.append('not_yet_valid')
 return sorted(set(errors))
