"""Executable specifications only. No process spawning, network, or infrastructure I/O.

These models are not a patch to the original reference package. Inputs claiming
independent verification must come from trusted local re-inspection in a future
integration; these functions do not authenticate evidence or approvals.
"""
from __future__ import annotations
import copy,json,re,sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from jsonschema import Draft202012Validator,FormatChecker
R=Path(__file__).resolve().parents[1]
class ContractViolation(ValueError):pass

def _schema(name:str)->dict:
 return json.loads((R/'contracts'/f'{name}.schema.json').read_text(encoding='utf-8'))

def schema_errors(name:str,value:object)->list[str]:
 """Return paths/codes, never rejected raw values or validator messages."""
 schema=_schema(name);known=set()
 def declared(node):
  if isinstance(node,dict):
   known.update(node.get('properties',{}).keys())
   for child in node.values():declared(child)
  elif isinstance(node,list):
   for child in node:declared(child)
 declared(schema)
 def safe_path(path):return '/'.join(str(p) if isinstance(p,int) or p in known else 'unclassified' for p in path)
 v=Draft202012Validator(schema,format_checker=FormatChecker())
 return sorted({f'schema:{safe_path(e.absolute_path)}:{e.validator}' for e in v.iter_errors(value)})

def provider_settings(records:list[dict])->dict:
 """Configuration projection only; it does not simulate SDK or service writes."""
 if not isinstance(records,list) or not records:raise ContractViolation('nonempty_settings_required')
 result=[]
 for i,record in enumerate(records):
  if schema_errors('observed-setting',record):raise ContractViolation('setting_shape')
  # Explicit stricter *local* support rule. Pinned Go validator checks adjacency,
  # but its implementation does not enforce the comment's first-ID-zero claim.
  if record['id']!=str(i):raise ContractViolation('reference_id_sequence_not_supported')
  result.append({'id':record['id'],'settingInstance':copy.deepcopy(record['settingInstance'])})
 body={'settings':result}
 if schema_errors('provider-settings',body):raise ContractViolation('provider_config_shape')
 return body

def _url(url:str):
 if not isinstance(url,str) or any(ord(c)<32 or ord(c)==127 for c in url):raise ValueError('unsafe_url')
 u=urlsplit(url)
 if u.scheme!='https' or not u.hostname or u.username or u.password or u.fragment or u.port not in (None,443):raise ValueError('unsafe_url')
 return u

def capture_errors(collection:dict,expected_root:str)->list[str]:
 """Check structure relative to a caller-supplied TRUSTED adapter root.

The root must not be derived from collection.pages[0].request_url. The default
adapter supports no initial query. This is not authenticity, freshness, or a
claim that the server snapshot was transactionally consistent.
"""
 errors=schema_errors('capture',collection)
 if errors:return errors
 try:
  root=_url(expected_root)
  if root.query:raise ValueError('root_query')
 except (ValueError,TypeError):return ['invalid_adapter_boundary']
 if collection['coverage']!='complete':errors.append('declared_incomplete')
 pages=collection['pages']
 if not pages:return errors+['no_pages']
 if pages[0]['request_url']!=expected_root:errors.append('initial_boundary')
 expected=expected_root;seen=set()
 for page in pages:
  url=page['request_url']
  if url!=expected:errors.append('broken_chain')
  if url in seen:errors.append('loop')
  seen.add(url)
  try:
   u=_url(url)
   if (u.netloc,u.path)!=(root.netloc,root.path):errors.append('wrong_origin_or_path')
   q=parse_qs(u.query,keep_blank_values=True)
   if any(k.lower() in ('$filter','$select','$search','$expand','$top','$skip') for k in q):errors.append('unsupported_query')
  except (ValueError,TypeError):errors.append('unsafe_page_url')
  if page['method']!='GET' or page['http_status']!=200:errors.append('page_status')
  body=page['body']
  # Presence of any error envelope invalidates completeness, even if HTTP200
  # and a value array coexist. Empty/malformed envelopes are not success.
  if 'error' in body:errors.append('error_page')
  if not isinstance(body.get('value'),list):errors.append('collection_shape')
  expected=body.get('@odata.nextLink')
  if expected is not None:
   if not isinstance(expected,str) or not expected:errors.append('invalid_next_link')
   elif expected in seen:errors.append('loop')
 if expected is not None:errors.append('missing_tail')
 return sorted(set(errors))

def reference_errors(records:list[dict])->list[str]:
 """Conservative duplicate policy: reject even identical duplicates.

Supersession requires a separately specified provenance/freshness rule, not
array order. GUID/value/relationship validation is a separate required gate.
"""
 if not isinstance(records,list):return ['reference_shape']
 seen=set();errors=[]
 for r in records:
  if not isinstance(r,dict) or not isinstance(r.get('kind'),str) or not isinstance(r.get('id'),str):errors.append('reference_shape');continue
  key=(r['kind'],r['id'].lower())
  if key in seen:errors.append('duplicate_reference')
  seen.add(key)
 return sorted(set(errors))

def resume_decision(session:dict,current:dict,verified_completed:list[str],current_mapping_status:str)->dict:
 """Prune invalidated receipts and find first uncompleted prerequisite.

verified_completed/current are trusted caller inputs, NOT values accepted from
the saved session. The model never authorizes or executes an operation. The
saved frontier caps completion so invalidation cannot advance unfinished work.
"""
 config=json.loads((R/'contracts/resume-stage-map.json').read_text())
 stages=config['stages'];frontiers=config['state_frontier'];triggers=config['invalidation_frontier']
 def result(state,index,reasons):return {'next_state':state,'milestone_index':index,'reasons':reasons,'external_execution':False,'authorization_reused':False}
 if schema_errors('session-state',session) or current_mapping_status not in ('unknown','complete','partial','blocked'):
  return result(config['fallback'],0,['session_or_mapping_invalid'])
 if not isinstance(current,dict) or set(current)!=set(triggers) or any(v is not None and (not isinstance(v,str) or not v) for v in current.values()):
  return result(config['fallback'],0,['current_fingerprint_contract_invalid'])
 if not isinstance(verified_completed,list) or any(x not in stages for x in verified_completed):return result(config['fallback'],0,['verification_receipts_invalid'])
 if session['in_flight_outcome']=='unknown':return result('reconciliation_required',0,['ambiguous_operation_no_replay'])
 cap=frontiers[session['saved_state']]
 completed=set(session['completed']) & set(verified_completed) & set(stages[:cap])
 changed=[k for k in triggers if session['fingerprints'][k]!=current[k]]
 earliest=min([triggers[k] for k in changed]+[len(stages)])
 completed &= set(stages[:earliest])
 if current_mapping_status!=session['mapping_status'] or current_mapping_status in ('unknown','blocked'):
  completed &= set(stages[:5])
 # Taking a contiguous prefix closes all prerequisite dependencies.
 index=next((i for i,s in enumerate(stages) if s not in completed),len(stages))
 next_states=['repository_inspection','source_selection','inventory','object_selection','ownership_detection','provider_mapping','generation_dispatch','local_validation','adoption_preview','qualification_handoff']
 state=next_states[index]
 if index==6:state='generate' if current_mapping_status=='complete' else 'partial_generate'
 elif index>=8 and current_mapping_status!='complete':state='mapping_gap_decision';index=5
 return result(state,index,['invalidated:'+k for k in sorted(changed)])

def _time(x:str):
 d=datetime.fromisoformat(x.replace('Z','+00:00'))
 if d.tzinfo is None:raise ValueError('timezone_required')
 return d

def approval_mismatches(approval:dict,observed_binding:dict,now:str)->list[str]:
 """Compare explicit context, NOT authenticity of approval or execution."""
 errors=schema_errors('approval-context',approval)
 if errors:return ['approval_context_schema']
 obs={**approval,'binding':observed_binding}
 if schema_errors('approval-context',obs):return ['observed_context_schema']
 def walk(a,b,path='binding'):
  if type(a) is not type(b):
   yield path
  elif isinstance(a,dict):
   for key in a:yield from walk(a[key],b[key],path+'/'+key)
  elif a!=b:yield path
 errors.extend(walk(approval['binding'],observed_binding))
 try:
  start=_time(approval['approved_at']);end=_time(approval['expires_at']);t=_time(now)
  if not start<=t<end:errors.append('expired_or_not_yet_valid')
 except (ValueError,TypeError,KeyError):errors.append('invalid_time')
 return sorted(set(errors))

PREVIEW_EXECUTABLES=frozenset({'atmos','tofu','python',sys.executable})
def validate_executable(token:str)->str:
 """Validate a registered preview identifier, not executable trust.

Python and this process's exact interpreter path are registered solely for
offline argv roundtrip tests. They confer no provider execution authority.
Execution must resolve an allowlisted absolute path and independently verify
the pinned binary hash. Bash ``command --`` does not force external execution.
"""
 if not isinstance(token,str) or token not in PREVIEW_EXECUTABLES:raise ContractViolation('invalid_executable_token')
 if token!=sys.executable and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.+-]*',token):raise ContractViolation('invalid_executable_token')
 if any(ord(c)<32 or ord(c)==127 for c in token):raise ContractViolation('invalid_executable_token')
 return token
