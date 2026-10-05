#!/usr/bin/env python3
"""Read metadata from an already acquired pinned catalogue. NEVER runs labs."""
import argparse,hashlib,json,subprocess,re
from pathlib import Path
import yaml

def safe_read(p,root):
 if p.is_symlink() or root not in p.resolve().parents:raise ValueError('Unsafe file path')
 b=p.read_bytes()
 if len(b)>2*1024*1024:raise ValueError('Metadata size limit')
 return b

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--checkout',required=True);p.add_argument('--expected-commit',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 r=Path(a.checkout).resolve();o=Path(a.output)
 if o.exists():p.error('Output exists')
 if not re.fullmatch('[0-9a-f]{40}',a.expected_commit):p.error('Exact immutable commit required')
 c=subprocess.run(['git','-c','core.fsmonitor=false','-C',str(r),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
 if c!=a.expected_commit:p.error('Checkout does not match expected commit')
 meta=yaml.safe_load(safe_read(r/'meta.yml',r));declared=[x for s in meta['sections'] for x in s['labs']];rows=[]
 for rel in declared:
  path=r/'labs'/rel/'lab.yaml';row={'declared_path':str(path.relative_to(r)),'source_commit':c,'exists':path.is_file(),'execution_status':'not_run','semantic_effect_review':'required','attestation':None,'solution_decrypted':False}
  if path.is_file():
   b=safe_read(path,r);lab=yaml.safe_load(b);row.update(id=lab.get('id'),title=lab.get('title'),skills=lab.get('skills'),runtime=lab.get('runtime'),validation=lab.get('validation'),metadata_sha256=hashlib.sha256(b).hexdigest(),test_paths=[str(x.relative_to(r)) for x in path.parent.glob('challenge/tests/*') if x.is_file()])
  rows.append(row)
 observed={str(x.parent.relative_to(r/'labs')) for x in (r/'labs').rglob('lab.yaml') if not x.is_symlink()}
 out={'source_commit':c,'status':'metadata_scan_not_semantic_audit','declared_count':len(declared),'duplicate_declarations':sorted({x for x in declared if declared.count(x)>1}),'unlisted_lab_directories':sorted(observed-set(declared)),'labs':rows}
 o.write_text(json.dumps(out,indent=2)+'\n');return 0
if __name__=='__main__':raise SystemExit(main())
