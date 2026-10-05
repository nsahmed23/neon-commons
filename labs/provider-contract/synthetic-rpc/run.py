#!/usr/bin/env python3
"""Run actual resource RPC against a GET-only in-memory Graph fixture, never a tenant."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('native_validation',HERE.parent/'native_validate.py')
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)

def resource_values(document):
    rows=document.get('values',document.get('planned_values',{})).get('root_module',{}).get('resources',[])
    matches=[r['values'] for r in rows if r.get('address')==native.RESOURCE+'.fixture']
    if len(matches)!=1:raise ValueError('exact resource address missing or duplicated')
    return matches[0]

def assignment_tuples(values):
    return sorted((r['type'],r.get('group_id'),r.get('filter_id'),r.get('filter_type')) for r in values)

def saved_snapshot(path):
    # OpenTofu 1.10.0 refresh-only JSON has no planned resource values when
    # there are no effects. Check its saved refreshed snapshot as well as the
    # JSON prior_state; never substitute authored HCL or imported state.
    with zipfile.ZipFile(path) as archive:
        rows=[row for row in archive.infolist() if row.filename=='tfstate']
        if len(rows)!=1 or rows[0].file_size>4*1024*1024:raise ValueError('invalid saved state snapshot')
        document=json.loads(archive.read(rows[0]))
    resources=document.get('resources',[])
    if len(resources)!=1:raise ValueError('unexpected saved resource denominator')
    row=resources[0]
    if row.get('mode')!='managed' or row.get('type')!=native.RESOURCE or row.get('name')!='fixture':raise ValueError('saved resource identity mismatch')
    instances=row.get('instances',[])
    if len(instances)!=1:raise ValueError('unexpected saved instance denominator')
    return instances[0]['attributes']

def oracle(values,fixture):
    expected=fixture['policy']
    for field,observed in [('id','id'),('name','name'),('description','description'),('platforms','platforms')]:
        if values.get(field)!=expected[observed]:raise ValueError('policy field mismatch: '+field)
    if values.get('role_scope_tag_ids')!=expected['roleScopeTagIds']:raise ValueError('scope tag mismatch')
    if values.get('technologies')!=['mdm']:raise ValueError('technology mismatch')
    for field,observed in [('created_date_time','createdDateTime'),('last_modified_date_time','lastModifiedDateTime'),('is_assigned','isAssigned'),('settings_count','settingCount')]:
        if values.get(field)!=expected[observed]:raise ValueError('computed policy field mismatch: '+field)
    if json.loads(values['settings'])!={'settings':fixture['settings']['value']}:raise ValueError('settings changed: IDs, wrappers, values, nulls, arrays must match exactly')
    expected_assignments=[]
    for row in fixture['assignments']:
        target=row['target'];expected_assignments.append({'type':target['@odata.type'].removeprefix('#microsoft.graph.'),'group_id':target['groupId'],'filter_id':target['deviceAndAppManagementAssignmentFilterId'],'filter_type':target['deviceAndAppManagementAssignmentFilterType']})
    if assignment_tuples(values['assignments'])!=assignment_tuples(expected_assignments):raise ValueError('assignment tuple/denominator mismatch')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tofu',required=True);p.add_argument('--provider',required=True);p.add_argument('--provider-sha256',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    tofu=Path(args.tofu).resolve(strict=True);provider=Path(args.provider).resolve(strict=True)
    if hashlib.sha256(tofu.read_bytes()).hexdigest()!=native.TOFU_SHA256:raise ValueError('OpenTofu pin mismatch')
    if hashlib.sha256(provider.read_bytes()).hexdigest()!=args.provider_sha256:raise ValueError('fixture provider pin mismatch')
    out=Path(args.output).absolute();out.mkdir(mode=0o700,parents=False,exist_ok=False)
    shutil.copyfile(HERE/'main.tf.json.txt',out/'main.tf.json')
    rc=out/'tofu.rc';rc.write_text('provider_installation { dev_overrides { '+json.dumps(native.SOURCE)+' = '+json.dumps(str(provider.parent))+' } }\n')
    env={'PATH':'/usr/bin:/bin','HOME':str(out),'TF_CLI_CONFIG_FILE':str(rc),'TF_IN_AUTOMATION':'1','CHECKPOINT_DISABLE':'1'}
    fixture=json.loads((HERE/'fixture.json').read_text())
    receipt={'status':'started','scope':'actual repaired resource through native RPC with separate synthetic provider Configure and GET-only in-memory transport','production_qualified':False,'production_provider_configure_qualified':False,'service_qualified':False,'provider_sha256':args.provider_sha256,'tofu_sha256':native.TOFU_SHA256,'fixture_sha256':hashlib.sha256((HERE/'fixture.json').read_bytes()).hexdigest(),'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'commands':{},'checks':{}}
    commands=[('schema',['providers','schema','-json']),('validate',['validate','-json']),('import',['import','-input=false','-no-color',native.RESOURCE+'.fixture',fixture['id']]),('state',['show','-json']),('ordinary',['plan','-input=false','-no-color','-detailed-exitcode','-out=ordinary.plan']),('ordinary_show',['show','-json','ordinary.plan']),('refresh',['plan','-refresh-only','-input=false','-no-color','-detailed-exitcode','-out=refresh.plan']),('refresh_show',['show','-json','refresh.plan'])]
    try:
        for name,tail in commands:receipt['commands'][name]=native.run([str(tofu)]+tail,out,env,name)
        if any(row['returncode']!=0 for row in receipt['commands'].values()):raise ValueError('native command failed or reported changes')
        for name in ('state','ordinary_show','refresh_show'):
            document=json.loads((out/(name+'.stdout')).read_text())
            if name=='refresh_show':
                oracle(resource_values(document['prior_state']),fixture)
                if document.get('planned_values',{}).get('root_module',{}).get('resources'):
                    oracle(resource_values(document),fixture)
                oracle(saved_snapshot(out/'refresh.plan'),fixture)
            else:oracle(resource_values(document),fixture)
            if name!='state':
                if document.get('errored') is not False:raise ValueError('saved plan errored status missing or true')
                for change in document.get('resource_changes',[])+document.get('resource_drift',[]):
                    if change['change']['actions']!=['no-op']:raise ValueError('saved plan contains effects')
                if name=='ordinary_show':oracle(saved_snapshot(out/'ordinary.plan'),fixture)
            receipt['checks'][name]='exact fixture policy/settings/assignment match'
        trace=[json.loads(line) for line in (out/'fixture-requests.jsonl').read_text().splitlines()]
        if not trace or any(row['method']!='GET' for row in trace):raise ValueError('missing trace or attempted mutation')
        pages=[row for row in trace if '/assignments' in row['url']]
        if len(pages)<6 or sum('$skiptoken=fixture%2B2' in row['url'] for row in pages)<3:raise ValueError('complete assignment paging not observed across three lifecycle reads')
        receipt['trace']={'requests':len(trace),'assignment_pages':len(pages),'methods':['GET'],'sha256':hashlib.sha256((out/'fixture-requests.jsonl').read_bytes()).hexdigest()}
        negative=out/'empty-policy';negative.mkdir(mode=0o700)
        shutil.copyfile(HERE/'main.tf.json.txt',negative/'main.tf.json')
        negative_env=dict(env,HOME=str(negative),INTUNE_SYNTHETIC_EMPTY_POLICY='1')
        row=native.run([str(tofu),'import','-input=false','-no-color',native.RESOURCE+'.fixture',fixture['id']],negative,negative_env,'import')
        receipt['empty_policy']=row
        diagnostic=(negative/'import.stderr').read_text()
        if row['returncode']==0 or 'Incomplete Policy Observation' not in diagnostic:raise ValueError('empty policy response was not explicitly refused')
        denied_trace=[json.loads(line) for line in (negative/'fixture-requests.jsonl').read_text().splitlines()]
        expected_url='https://graph.microsoft.com/beta/deviceManagement/configurationPolicies/'+fixture['id']
        if denied_trace!=[{'method':'GET','url':expected_url}]:raise ValueError('empty policy continued into settings/assignments or attempted a write')
        receipt['checks']['empty_policy_rejected_before_collections']=True
        receipt['status']='passed-synthetic-resource-rpc'
        receipt['checks'].update(identity_preserving_import=True,ordinary_saved_plan_no_change=True,refresh_only_saved_plan_no_change=True)
    except Exception as exc:receipt.update(status='failed',error=type(exc).__name__+': '+str(exc))
    (out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'status':receipt['status'],'error':receipt.get('error'),'production_qualified':False}))

if __name__=='__main__':main()
