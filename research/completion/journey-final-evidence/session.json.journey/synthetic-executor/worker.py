import hashlib,json,os,sys,tempfile
from pathlib import Path
root=Path.cwd()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def load(p):return json.loads(p.read_bytes())
def save(p,v):
 data=canonical(v); fd,name=tempfile.mkstemp(dir=p.parent)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.replace(name,p)
 fd=os.open(p.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
state=root/'state/terraform.tfstate';plan=Path(sys.argv[2]) if len(sys.argv)>2 else root/'saved.tfplan';cmd=sys.argv[1]
if cmd=='version':print('{"terraform_version":"synthetic-local-1"}')
elif cmd=='init':pass
elif cmd=='plan':
 s=load(state);v=load(root/'main.tf.json')['output']['fixture']['value']
 save(plan,{'schema':'synthetic-saved-plan/1','before_sha256':hashlib.sha256(state.read_bytes()).hexdigest(),'value':v})
elif cmd=='show':
 p=load(plan);s=load(state);before=s['outputs']['fixture']['value'];after=p['value'];change=canonical(before)!=canonical(after)
 print(json.dumps({'format_version':'1.2','terraform_version':'1.10.0','planned_values':{'outputs':{'fixture':{'value':after,'sensitive':False}}},'resource_changes':[],'configuration':{},'output_changes':{'fixture':{'actions':['update' if change else 'no-op'],'before':before,'after':after,'after_unknown':False,'before_sensitive':False,'after_sensitive':False}},'prior_state':{'format_version':'1.0','terraform_version':'1.10.0','values':{'outputs':{'fixture':{'value':before,'sensitive':False,'type':['object',{}]}}}}}))
elif cmd=='apply':
 p=load(plan)
 if p['before_sha256']!=hashlib.sha256(state.read_bytes()).hexdigest():sys.exit(3)
 s=load(state);s['serial']+=1;s['outputs']['fixture']['value']=p['value'];save(state,s)
else:sys.exit(2)
