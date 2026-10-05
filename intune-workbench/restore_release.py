"""Verify and extract the complete release attachment. No project code is executed."""
import argparse,hashlib,json,shutil,stat,zipfile
from pathlib import Path,PurePosixPath
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('archive',type=Path)
p.add_argument('--destination',type=Path,default=Path('intune-recovered'))
a=p.parse_args()
expected='5a16fc491944d1e8b73295d26ab8f4399f1156c0c7f1847e3faca7d3a68cc214'
if a.destination.exists(): raise SystemExit('Destination must not exist.')
h=hashlib.sha256()
with a.archive.open('rb') as f:
 while b:=f.read(1024*1024): h.update(b)
if a.archive.stat().st_size!=1156114547 or h.hexdigest()!=expected: raise SystemExit('Archive size or SHA-256 mismatch; refusing extraction.')
with zipfile.ZipFile(a.archive) as z:
 seen=set()
 for i in z.infolist():
  n=i.filename; q=PurePosixPath(n); mode=i.external_attr>>16
  if q.is_absolute() or '..' in q.parts or chr(92) in n or ':' in n or n in seen or stat.S_ISLNK(mode): raise SystemExit('Unsafe archive path: '+repr(n))
  if stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR): raise SystemExit('Special archive entry')
  seen.add(n)
 a.destination.mkdir()
 for i in z.infolist():
  t=a.destination/i.filename
  if i.is_dir(): t.mkdir(parents=True,exist_ok=True); continue
  t.parent.mkdir(parents=True,exist_ok=True)
  with z.open(i) as src,t.open('xb') as dst: shutil.copyfileobj(src,dst)
  if (i.external_attr>>16)&0o111: t.chmod(0o700)
print(json.dumps({'status':'PASS','sha256':expected,'entries':len(seen),'destination':str(a.destination),'project_code_executed':False}))
