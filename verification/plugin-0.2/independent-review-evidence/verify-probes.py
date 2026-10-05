import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0, '/workspace/scratch/26b6d364cfda/intune-iac-plugin')
from intune_iac import engine
from intune_iac.io import AppError
from intune_iac.repository import discover_repository, resolve_component, public_resolution
from intune_iac.mcp import call_tool
out=Path('/workspace/scratch/26b6d364cfda/review-02')
base=out/'baseline'
project=out/'verified-candidate'
engine.generate(base/'capture.json',base/'context.json',project)
checks=[]
changed_context=json.loads((base/'context.json').read_text());changed_context['repository_source_fingerprint']='a'*64
(out/'changed-context.json').write_text(json.dumps(changed_context))
try:
    engine.verify_project(base/'capture.json',out/'changed-context.json',project)
    raise AssertionError('changed context accepted')
except AppError as e:
    assert e.code=='postcondition_failed'
checks.append('changed context rejected by target receipt')
for name,relative,mutate in (
    ('assignment-removal','candidates/components/terraform/policy/configuration.json',lambda x:x.update(assignments=[])),
    ('false-authority','candidates/target.json',lambda x:x.update(execution_authorized=True)),
    ('missing-accounting','review/normalized.json',lambda x:x['field_accounting'].pop()),
):
    dest=out/name;shutil.copytree(project,dest)
    path=dest/relative;data=json.loads(path.read_text());mutate(data);path.write_text(json.dumps(data))
    manifest=dest/'generated-files.json';m=json.loads(manifest.read_text());m['files'][relative]=hashlib.sha256(path.read_bytes()).hexdigest();manifest.write_text(json.dumps(m))
    try:
        engine.verify_project(base/'capture.json',base/'context.json',dest)
        raise AssertionError(name+' accepted')
    except AppError as e:
        assert e.code=='postcondition_failed'
    checks.append(name+' rejected despite updated manifest')
repo=out/'repo'
(repo/'stacks/deploy').mkdir(parents=True)
(repo/'components/terraform/policy').mkdir(parents=True)
(repo/'atmos.yaml').write_text('stacks:\n  included_paths: ["deploy/**/*"]\n')
(repo/'stacks/base.yaml').write_text('vars: {region: west}\ncomponents:\n  terraform:\n    base:\n      metadata: {type: abstract}\n      vars: {retained: 1}\n')
(repo/'stacks/deploy/dev.yaml').write_text('import: [base]\ncomponents:\n  terraform:\n    policy:\n      metadata: {inherits: [base]}\n      vars: {region: east}\n      env: {TOKEN: repository-secret-canary}\n')
r=resolve_component(repo,'deploy/dev','policy');assert r['status']=='resolved'
assert r['effective']['vars']=={'region':'east','retained':1}
assert r['provenance']['/vars/region']['winner']['path']=='stacks/deploy/dev.yaml'
assert r['provenance']['/vars/retained']['winner']['path']=='stacks/base.yaml'
for result in (public_resolution(r), discover_repository(repo), call_tool('intune_repository_resolve',{'root':str(repo),'stack':'deploy/dev','component':'policy'})):
    assert 'repository-secret-canary' not in json.dumps(result)
checks.append('literal precedence/provenance and public/MCP value omission')
(repo/'components/terraform/policy/main.tf').write_text('# newly added implementation evidence\n')
assert resolve_component(repo,'deploy/dev','policy')['source_fingerprint']!=r['source_fingerprint']
checks.append('HCL file addition changes repository source closure')
(repo/'stacks/deploy/link.yaml').symlink_to(out/'changed-context.json')
assert discover_repository(repo)['status']=='blocked'
checks.append('source symlink blocks discovery')
(out/'verify-results.json').write_text(json.dumps(checks,indent=2))
print(json.dumps({'passed':len(checks),'checks':checks},indent=2))
