#!/usr/bin/env python3
"""Create, inspect and resume an offline local evidence store; never executes cloud tools."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
 from reference import workflow
except ModuleNotFoundError:
 print('Validation environment is incomplete; run tools/runtime-check.py.',file=sys.stderr)
 raise SystemExit(5)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('operation',choices=['create','inspect','resume','suspend','cancel'])
p.add_argument('--offline',required=True,action='store_true',help='Required acknowledgment: local consistency checks only')
p.add_argument('--root',required=True,type=Path,help='Approved local evidence directory; no symlinks')
p.add_argument('--saved-state',default='repository_inspection')
p.add_argument('--artifact',action='append',default=[],metavar='KIND:RELATIVE_PATH')
p.add_argument('--resume',action='store_true',help='Explicit local intent to resume a suspended/cancelled session')
a=p.parse_args()
try:
 if a.operation=='create':
  pairs=[]
  for item in a.artifact:
   if item.count(':')!=1:raise workflow.StoreError('artifact_argument_invalid')
   pairs.append(tuple(item.split(':',1)))
  value=workflow.create(a.root,a.saved_state,pairs)
 elif a.operation=='inspect':value=workflow.inspect(a.root)
 elif a.operation=='resume':value=workflow.resume(a.root,local_resume=a.resume)
 else:
  workflow.set_lifecycle(a.root,'cancelled' if a.operation=='cancel' else 'suspended');value={'external_execution':False,'authorization_reused':False,'lifecycle':a.operation}
 print(json.dumps(value,sort_keys=True));raise SystemExit(0)
except (workflow.StoreError,OSError,ValueError):
 print(json.dumps({'error':'local_receipt_store_rejected','external_execution':False,'authorization_reused':False}));raise SystemExit(3)
