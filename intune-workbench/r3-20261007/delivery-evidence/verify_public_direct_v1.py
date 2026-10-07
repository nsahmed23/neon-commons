#!/usr/bin/env python3
"""Anonymous immutable public readback against a staged byte inventory."""
import argparse,concurrent.futures,datetime,hashlib,json,re,time
from pathlib import Path
import urllib.error,urllib.parse,urllib.request
p=argparse.ArgumentParser();p.add_argument('--commit',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if not re.fullmatch('[0-9a-f]{40}',a.commit):p.error('An immutable 40-character Git commit is required.')
a.output.mkdir(parents=True,exist_ok=False)
stage=Path('/workspace/intune-publication/repo/intune-workbench/r3-20261007')
rows=[{'path':str(p.relative_to(stage)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(stage.rglob('*')) if p.is_file() and not p.is_symlink()]
(a.output/'expected-files.json').write_text(json.dumps(rows,indent=2)+'\n')
base='https://raw.githubusercontent.com/nsahmed23/neon-commons/'+a.commit+'/intune-workbench/r3-20261007/'
def fetch(row):
 result=dict(row,url=base+urllib.parse.quote(row['path'],safe='/'),verified=False)
 try:
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  request=urllib.request.Request(result['url'],headers={'User-Agent':'Intune-R3-independent-anonymous-byte-readback','Accept':'application/octet-stream'})
  with opener.open(request,timeout=60) as response:
   data=response.read();result.update(http_status=response.status,response_url=response.url)
  target=a.output/'downloads'/row['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
  result.update(observed_bytes=len(data),observed_sha256=hashlib.sha256(data).hexdigest())
  result['verified']=result['http_status']==200 and result['observed_bytes']==row['bytes'] and result['observed_sha256']==row['sha256']
 except Exception as e:result.update(error_type=type(e).__name__,error=str(e))
 return result
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(fetch,rows))
extras=[]
for label,url,expected in [('neon_main','https://api.github.com/repos/nsahmed23/neon-commons/git/ref/heads/main','4ba077d93fecbf5f893ee13ef972c839cf13883d'),('tested_source','https://raw.githubusercontent.com/nsahmed23/neon-commons/289ee9477372825aad848f4482cf681c2ff43b02/plugin_tests/test_native_smoke_observation_epoch.py','01fb4992680253a613bd81ee12e7ec355a9e19c2df4ab427305338ea49787cb5')]:
 r={'label':label,'url':url,'expected':expected,'verified':False}
 try:
  request=urllib.request.Request(url,headers={'User-Agent':'Intune-R3-independent-anonymous-byte-readback'})
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=60) as response:data=response.read();r['http_status']=response.status
  (a.output/(label+'.response')).write_bytes(data)
  actual=json.loads(data)['object']['sha'] if label=='neon_main' else hashlib.sha256(data).hexdigest()
  r.update(observed=actual,verified=actual==expected and r['http_status']==200)
 except Exception as e:r.update(error_type=type(e).__name__,error=str(e))
 extras.append(r)
receipt={'status':'PASS_ANONYMOUS_PUBLIC_READBACK' if all(r['verified'] for r in results+extras) else 'FAIL_OR_INCOMPLETE_PRESERVED','started_at':started,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pinned_handoff_commit':a.commit,'authentication':'No Authorization/cookies/credential helper; anonymous HTTPS requests; proxy environment ignored.','files':results,'extra_checks':extras,'files_verified':sum(r['verified'] for r in results),'total_files':len(results),'bytes_verified':sum(r['observed_bytes'] for r in results if r['verified']),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Browser files, exact product packages and distribution manifest/tooling on pinned public handoff commit. Does not by itself verify multi-part evidence archive reconstruction; that separate distribution proof remains required.'}
(a.output/'PUBLIC-READBACK-RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:receipt[k] for k in ['status','files_verified','total_files','bytes_verified']}))
print(json.dumps({'failures':[{'path':r.get('path',r.get('label')),'error':r.get('error'),'verified':r['verified']} for r in results+extras if not r['verified']]}))
raise SystemExit(0 if receipt['status']=='PASS_ANONYMOUS_PUBLIC_READBACK' else 1)
