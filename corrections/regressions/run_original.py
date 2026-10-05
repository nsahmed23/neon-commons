"""Run desired-behavior tests against an unchanged Appendix B pack; expect failures."""
import argparse,datetime,importlib,io,json,os,subprocess,sys,unittest
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--pack',required=True);p.add_argument('--output',required=True);a=p.parse_args()
os.environ['APPENDIX_B_PACK']=str(Path(a.pack).resolve());sys.dont_write_bytecode=True
# Dependency and entrypoint failure are harness outcomes, never reproduced bugs.
preflight=[]
for dependency in ['jsonschema','yaml']:
 try:importlib.import_module(dependency)
 except ImportError:preflight.append('missing_dependency:'+dependency)
if not preflight:
 try:
  check=subprocess.run([sys.executable,str(Path(a.pack)/'tools/build-reference.py'),'--help'],capture_output=True,text=True,timeout=15)
  if check.returncode:preflight.append('cli_startup_failed')
 except (OSError,subprocess.TimeoutExpired):preflight.append('cli_startup_failed')
if preflight:
 out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
 report={'scope':'regression harness preflight; no behavioral tests executed','status':'blocked','tests':0,'passes':0,'failures':0,'harness_errors':1,'causes':preflight}
 (out/'regression-against-original.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2));raise SystemExit(5)
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_original_regressions as tests
class Result(unittest.TextTestResult):
 def __init__(self,*a,**k):super().__init__(*a,**k);self.records=[]
 def addSuccess(self,t):super().addSuccess(t);self.records.append({'case':t.id(),'status':'pass'})
 def addFailure(self,t,e):super().addFailure(t,e);self.records.append({'case':t.id(),'status':'fail','failure':str(e[1])})
 def addError(self,t,e):super().addError(t,e);self.records.append({'case':t.id(),'status':'harness-error','error':str(e[1])})
log=io.StringIO();r=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
report={'scope':'desired-behavior regression assertions against unchanged original; failures are reproduced counterexamples, not repairs','observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tests':r.testsRun,'passes':len([x for x in r.records if x['status']=='pass']),'failures':len(r.failures),'harness_errors':len(r.errors),'cases':r.records}
(out/'regression-against-original.json').write_text(json.dumps(report,indent=2)+'\n');(out/'regression-against-original.log').write_text(log.getvalue());print(json.dumps({k:v for k,v in report.items() if k!='cases'},indent=2))
raise SystemExit(0 if r.wasSuccessful() else 1)
