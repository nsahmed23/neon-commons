import copy
import json
import sys
from pathlib import Path
sys.path.insert(0, '/workspace/scratch/26b6d364cfda/intune-iac-plugin')
from intune_iac import engine
from intune_iac.io import AppError

plugin = Path('/workspace/scratch/26b6d364cfda/intune-iac-plugin')
out = Path('/workspace/scratch/26b6d364cfda/review-02')
base = json.loads((plugin/'examples/supported/input/export.json').read_text())
base.update(synthetic=False, exporter={'id': 'intune-iac-settings-catalog-graph', 'version': '1.0.0'}, references=[], ownership=[])
context = json.loads((plugin/'examples/context.json').read_text())
context.update(source_is_synthetic=False, stack='deploy/dev', component='policy')
results=[]

def run(name, mutate):
    source=copy.deepcopy(base)
    mutate(source)
    folder=out/name
    folder.mkdir(exist_ok=True)
    src=folder/'capture.json'; ctx=folder/'context.json'
    src.write_text(json.dumps(source)); ctx.write_text(json.dumps(context))
    try:
        report=engine.inspect_source(src,ctx)
        n=report['normalized']
        result={'name':name, 'candidate_mapping_complete':n['candidate_mapping_complete'], 'coverage':n['coverage'], 'codes':[x['code'] for x in n['blockers']], 'configuration':n['configuration']}
    except AppError as e:
        result={'name':name,'rejected':e.code}
    results.append(result)

run('baseline',lambda s:None)

def empty_with_count(s):
    s['collections'][2]['pages'][0]['body']={'value':[], '@odata.count':2}
    s['collections'][0]['pages'][0]['body']['value'][0]['isAssigned']=False
run('empty_with_count',empty_with_count)

def assigned_empty(s):
    s['collections'][2]['pages'][0]['body']={'value':[]}
run('assigned_empty',assigned_empty)

def zero_with_rows(s):
    s['collections'][2]['pages'][0]['body']['@odata.count']=0
run('zero_count_with_rows',zero_with_rows)

def missing(s):
    s['collections'].pop()
run('missing_assignments',missing)

def secret(s):
    s['collections'][2]['pages'][0]['body']['value'][0]['target']['unknown-canary-key']={'CANARY':'secret-canary'}
run('unknown_assignment',secret)

def uppercase_duplicate(s):
    rows=s['collections'][2]['pages'][0]['body']['value']
    row=copy.deepcopy(rows[0]);row['id']='another-assignment-id'
    rows[0]['target']['groupId']='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    row['target']['groupId']='AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'
    s['collections'][2]['pages'][0]['body']['value']=[rows[0],row]
run('case_duplicate_target',uppercase_duplicate)
(out/'probe-results.json').write_text(json.dumps(results,indent=2))
for r in results:
    print(json.dumps({k:v for k,v in r.items() if k not in ('configuration','coverage')}))
