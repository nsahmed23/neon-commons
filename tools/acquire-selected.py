#!/usr/bin/env python3
"""Optional PUBLIC source acquisition only. Never installs or executes downloaded code.
Requires explicit --allow-network. Not network-tested in this environment.
"""
import argparse,hashlib,json,re,sys
from pathlib import Path,PurePosixPath
from urllib.parse import quote,urlparse
from urllib.request import build_opener,HTTPRedirectHandler,Request
ROOT=Path(__file__).resolve().parents[1]
class RestrictedRedirect(HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  u=urlparse(newurl)
  if u.scheme!='https' or u.netloc!='raw.githubusercontent.com':raise ValueError('Redirect outside approved source origin')
  return super().redirect_request(req,fp,code,msg,headers,newurl)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--allow-network',action='store_true');p.add_argument('--output',required=True);a=p.parse_args()
 if not a.allow_network:p.error('Explicit --allow-network is required; no request made')
 out=Path(a.output)
 if out.exists():p.error('Use a new destination to prevent overwriting source material')
 out.mkdir(parents=False);receipts=[];opener=build_opener(RestrictedRedirect())
 for line in (ROOT/'code-catalog.jsonl').read_text().splitlines():
  u=json.loads(line);sha=u['commit_sha'];blob=u.get('blob_sha');parts=PurePosixPath(u['path'])
  if not sha or not blob:receipts.append({'id':u['id'],'status':'skipped_missing_pin_or_blob'});continue
  try:
   if not re.fullmatch('[0-9a-f]{40}',sha) or not re.fullmatch('[0-9a-f]{40}',blob):raise ValueError('Bad pin')
   if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',u['repository']):raise ValueError('Bad repository')
   if parts.is_absolute() or '..' in parts.parts or '\\' in u['path']:raise ValueError('Unsafe path')
   url=f'https://raw.githubusercontent.com/{u["repository"]}/{sha}/{quote(u["path"],safe="/")}'
   with opener.open(Request(url,headers={'User-Agent':'Intune-IaC-materials-acquirer/1.0'}),timeout=30) as res:
    raw=res.read(10*1024*1024+1)
   if len(raw)>10*1024*1024:raise ValueError('Source exceeds size limit')
   actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
   if actual!=blob:raise ValueError('Git blob mismatch')
   dest=out/u['source_id']/u['path'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
   receipts.append({'id':u['id'],'status':'acquired_not_executed','path':str(dest.relative_to(out)),'commit_sha':sha,'blob_sha':actual,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
  except Exception as e:receipts.append({'id':u['id'],'status':'failed','error_type':type(e).__name__})
 (out/'acquisition-receipt.json').write_text(json.dumps(receipts,indent=2)+'\n')
 return 1 if any(x['status']=='failed' for x in receipts) else 0
if __name__=='__main__':raise SystemExit(main())
