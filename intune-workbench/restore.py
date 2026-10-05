"""Restore the complete handoff; executes no archived project code."""
import hashlib,json,os,shutil,stat,tempfile,zipfile
from pathlib import Path, PurePosixPath
BASE=Path(__file__).resolve().parent
EXPECTED='5a16fc491944d1e8b73295d26ab8f4399f1156c0c7f1847e3faca7d3a68cc214'
m=json.loads((BASE/'manifest.json').read_text())
assert m['sha256']==EXPECTED and m['size']==1156114547
out=Path.cwd()/m['filename']; dest=Path.cwd()/'intune-recovered'
if out.exists() or dest.exists(): raise SystemExit('Output already exists; choose a new working directory.')
for row in m['parts']:
 p=BASE/row['path']
 if not p.is_file(): raise SystemExit('Missing required part: '+str(p))
with tempfile.NamedTemporaryFile(dir=Path.cwd(),prefix='intune-restore-',delete=False) as f:
 temp=Path(f.name); whole=hashlib.sha256(); total=0
 try:
  for row in m['parts']:
   b=(BASE/row['path']).read_bytes()
   if len(b)!=row['size'] or hashlib.sha256(b).hexdigest()!=row['sha256']: raise ValueError('Invalid part: '+row['path'])
   whole.update(b); total+=len(b); f.write(b)
  if total!=m['size'] or whole.hexdigest()!=EXPECTED: raise ValueError('Whole archive mismatch')
  f.flush(); os.fsync(f.fileno())
 except BaseException:
  temp.unlink(missing_ok=True); raise
os.link(temp,out); temp.unlink()
with zipfile.ZipFile(out) as z:
 seen=set()
 for info in z.infolist():
  name=info.filename; p=PurePosixPath(name); mode=info.external_attr>>16
  if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or name in seen or stat.S_ISLNK(mode): raise ValueError('Unsafe archive entry: '+repr(name))
  seen.add(name)
  if stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR): raise ValueError('Special archive entry')
 dest.mkdir()
 for info in z.infolist():
  target=dest/info.filename
  if info.is_dir(): target.mkdir(parents=True,exist_ok=True); continue
  target.parent.mkdir(parents=True,exist_ok=True)
  with z.open(info) as src,target.open('xb') as dst: shutil.copyfileobj(src,dst)
  if (info.external_attr>>16)&0o111: target.chmod(0o700)
print(json.dumps({'status':'PASS','bytes':total,'sha256':EXPECTED,'extracted_to':str(dest),'project_code_executed':False}))
