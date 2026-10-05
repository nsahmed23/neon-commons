"""Local verifier for this correction/specification pack; never runs the old pack."""
from __future__ import annotations
import argparse,ast,datetime,io,json,sys,unittest,csv
from pathlib import Path
R=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(R/'regressions'));sys.path.insert(0,str(R/'models'))

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--output',help='Optional local directory for a new receipt/log');a=p.parse_args()
 failures=[];counts={'json':0,'jsonl':0,'python':0,'csv':0}
 for f in sorted(R.rglob('*')):
  if not f.is_file():continue
  rel=f.relative_to(R).as_posix()
  if f.is_symlink():failures.append('symlink:'+rel);continue
  try:
   if f.suffix=='.json':json.loads(f.read_text(encoding='utf-8'));counts['json']+=1
   elif f.suffix=='.jsonl':
    for line in f.read_text(encoding='utf-8').splitlines():json.loads(line)
    counts['jsonl']+=1
   elif f.suffix=='.py':ast.parse(f.read_text(encoding='utf-8'));counts['python']+=1
   elif f.suffix=='.csv':
    rows=list(csv.reader(io.StringIO(f.read_text(encoding='utf-8'))));assert rows and all(len(row)==len(rows[0]) for row in rows);counts['csv']+=1
  except Exception as e:failures.append(rel+':'+type(e).__name__)
 required=['BUILD-START-HERE.md','CORRECTION-SPEC.md','defect-to-correction.csv','revised-gaps.json','sources/provider-dependency-map.json','sources/source-evidence.json','contracts/SESSION-INTEGRATION.md','qualification/PROVIDER-SERVICE.md','qualification/HOSTS-AND-EVALUATION.md','evidence/baseline-verifier.json','evidence/regression-against-original.json']
 for name in required:
  if not (R/name).is_file():failures.append('missing:'+name)
 import test_contract_models
 stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_contract_models))
 import contract_model,copy
 model=json.loads((R/'contracts/resume-stage-map.json').read_text());base=json.loads((R/'fixtures/session-early.json').read_text());matrix=[]
 for state,frontier in model['state_frontier'].items():
  for changed in model['invalidation_frontier']:
   for m in ['unknown','partial','complete']:
    sess=copy.deepcopy(base);sess.update(saved_state=state,completed=model['stages'][:frontier],mapping_status=m);now=copy.deepcopy(sess['fingerprints']);now[changed]='changed'
    output=contract_model.resume_decision(sess,now,sess['completed'],m)
    ok=output['milestone_index']<=frontier and output['external_execution'] is False
    matrix.append({'saved_state':state,'changed_fingerprint':changed,'mapping_status':m,'output':output,'nonadvancement_assertion':'pass' if ok else 'fail','assurance':'isolated model under synthetic verified-receipt assumptions'})
    if not ok:failures.append('matrix:'+state+':'+changed+':'+m)
 receipt={'schema_version':'1.0.0','observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'new correction schemas and pure executable specifications only; not patched original, provider or host behavior','static_counts':counts,'static_failures':failures,'tests':{'run':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),'failed':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)},'resume_grid':{'cases':len(matrix),'assertion':'no advance past saved milestone frontier and no external execution; not all semantic transition properties','failures':sum(x['nonadvancement_assertion']=='fail' for x in matrix)},'not_run':['original repair integration','complete new oracle implementation','provider process or HCL/provider validation','native PowerShell/Windows','native Claude/Codex packaging/evaluation','paid model benchmark','Azure/Graph auth, import, plan, apply or collection'],'status':'pass' if not failures and result.wasSuccessful() else 'fail'}
 if a.output:
  out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
  (out/'contract-model-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
  (out/'contract-model-tests.log').write_text(stream.getvalue(),encoding='utf-8')
  (out/'resume-matrix.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in matrix),encoding='utf-8')
 print(json.dumps(receipt,indent=2));return 0 if receipt['status']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
