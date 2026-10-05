#!/usr/bin/env python3
"""Offline synthetic-reference builder. No network, authentication or engine calls."""
from pathlib import Path
import argparse,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
 from jsonschema import Draft202012Validator,FormatChecker
 import hcl2
 from reference.core import normalize,generate_files,write_project
 from reference.invariants import compare
except ModuleNotFoundError:
 print('Validation environment is incomplete. Run tools/runtime-check.py; no input was processed.',file=sys.stderr)
 raise SystemExit(5)
R=Path(__file__).resolve().parents[1]
def load_with_bytes(path):
 raw=Path(path).read_bytes()
 if len(raw)>16*1024*1024:raise ValueError('Input exceeds reference size limit')
 def pairs(xs):
  d={}
  for k,v in xs:
   if k in d:raise ValueError('Duplicate JSON key')
   d[k]=v
  return d
 value=json.loads(raw,object_pairs_hook=pairs,
   parse_float=lambda _:(_ for _ in ()).throw(ValueError('Floating point input outside bounded contract')),
   parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON value')))
 def bounded(v,depth=0):
  if depth>64:raise ValueError('Input exceeds reference nesting limit')
  if type(v) is int and abs(v)>9007199254740991:raise ValueError('Integer outside canonical reference range')
  if isinstance(v,dict):
   for child in v.values():bounded(child,depth+1)
  elif isinstance(v,list):
   for child in v:bounded(child,depth+1)
 bounded(value)
 return value,raw
def load(path):return load_with_bytes(path)[0]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--context',required=True);p.add_argument('--output',required=True)
 a=p.parse_args()
 try:
  b,raw=load_with_bytes(a.input);c=load(a.context)
  Draft202012Validator(load(R/'contracts/export-intake.schema.json'),format_checker=FormatChecker()).validate(b)
  n=normalize(b,c['selected_policy_id'],c['tenant_id']);files=generate_files(n,c)
  files['adoption/source-receipt.json']=json.dumps({'schema_version':'1.0.0',
    'source_byte_sha256':hashlib.sha256(raw).hexdigest(),
    'source_canonical_sha256':n['source_canonical_sha256']},indent=2,sort_keys=True)+'\n'
  errors=compare(raw,n,files=files,context=c)
  if errors:
   print('Independent preservation check failed; no output was written.',file=sys.stderr)
   return 3
  status=write_project(files,Path(a.output))
  print(json.dumps({'schema_version':'1.0.0','result':status,'file_count':len(files),'offline_mapping_complete':n['offline_mapping_complete'],'blocker_codes':sorted(set(x['code'] for x in n['blockers'])),'preservation_verified':True,'execution_authorized':False}))
  return 0 if n['offline_mapping_complete'] else 2
 except FileExistsError:
  print('Output conflict: use a new staging directory; existing files were not overwritten.',file=sys.stderr);return 4
 except KeyboardInterrupt:return 130
 except Exception:
  print('Input or local validation failed. Inspect locally; raw payload was not echoed.',file=sys.stderr);return 3
if __name__=='__main__':raise SystemExit(main())
