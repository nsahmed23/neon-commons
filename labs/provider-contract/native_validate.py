#!/usr/bin/env python3
"""Native schema and HCL validation only; no Configure, plans, state, or tenant calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess

TOFU_SHA256='0a9eda0f0898896969492504a6ce778f310675e8a1eb960434c26806cd252627'
RESOURCE='microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json'
SOURCE='registry.terraform.io/deploymenttheory/microsoft365'


def run(command, directory, env, prefix):
    stdout=directory/(prefix+'.stdout');stderr=directory/(prefix+'.stderr')
    with stdout.open('wb') as out, stderr.open('wb') as err:
        proc=subprocess.Popen(command,cwd=directory,env=env,stdout=out,stderr=err,start_new_session=True)
        try:
            code=proc.wait(timeout=180)
        finally:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait(timeout=5)
    return {'command':command,'returncode':code,'stdout_bytes':stdout.stat().st_size,'stdout_sha256':hashlib.sha256(stdout.read_bytes()).hexdigest(),'stderr_sha256':hashlib.sha256(stderr.read_bytes()).hexdigest()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tofu',required=True);parser.add_argument('--provider',required=True);parser.add_argument('--provider-sha256',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--synthetic-resource-fixture',action='store_true',help='use the separate lab provider schema; never claims production provider RPC')
    args=parser.parse_args();tofu=Path(args.tofu).resolve(strict=True);provider=Path(args.provider).resolve(strict=True)
    if hashlib.sha256(tofu.read_bytes()).hexdigest()!=TOFU_SHA256:raise ValueError('OpenTofu executable differs from pinned 1.10.0')
    if hashlib.sha256(provider.read_bytes()).hexdigest()!=args.provider_sha256:raise ValueError('provider executable identity mismatch')
    output=Path(args.output).absolute();output.mkdir(mode=0o700,parents=False,exist_ok=False)
    cli=output/'tofu.rc';cli.write_text('provider_installation { dev_overrides { '+json.dumps(SOURCE)+' = '+json.dumps(str(provider.parent))+' } }\n')
    env={'PATH':'/usr/bin:/bin','HOME':str(output),'TF_CLI_CONFIG_FILE':str(cli),'TF_IN_AUTOMATION':'1','CHECKPOINT_DISABLE':'1'}
    config={'terraform':{'required_providers':{'microsoft365':{'source':SOURCE,'version':'1.0.0'}}},'provider':{'microsoft365':{} if args.synthetic_resource_fixture else {'cloud':'public'}}}
    (output/'main.tf.json').write_text(json.dumps(config,indent=2)+'\n')
    receipt={'provider_sha256':args.provider_sha256,'tofu_sha256':TOFU_SHA256,'production_qualified':False,'service_qualified':False,'scope':'native GetProviderSchema and ValidateResourceConfig only; no Configure/import/plan/apply/read','cases':{},'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    receipt['production_provider']=not args.synthetic_resource_fixture
    if args.synthetic_resource_fixture:receipt['scope']='Separate synthetic provider with actual resource Schema/ValidateResourceConfig RPC; not production provider schema or Configure'
    receipt['schema']=run([str(tofu),'providers','schema','-json'],output,env,'schema')
    if receipt['schema']['returncode']==0:
        schema=json.loads((output/'schema.stdout').read_text())
        selected=schema['provider_schemas'][SOURCE]['resource_schemas'][RESOURCE]
        (output/'selected-schema.json').write_text(json.dumps(selected,indent=2)+'\n')
    settings={'settings':[{'id':'0','settingInstance':{'@odata.type':'#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance','settingDefinitionId':'device_vendor_msft_policy_config_privacy_letappsaccesslocation','settingInstanceTemplateReference':None,'choiceSettingValue':{'@odata.type':'#microsoft.graph.deviceManagementConfigurationChoiceSettingValue','value':'device_vendor_msft_policy_config_privacy_letappsaccesslocation_2','settingValueTemplateReference':None,'children':[]}}}]}
    cases={'ordinary':(settings,True),'observed_wrapper':(json.loads(json.dumps(settings)),True),'null_instance':({'settings':[{'id':'0','settingInstance':None}]},False),'unknown_type':(json.loads(json.dumps(settings)),False)}
    cases['observed_wrapper'][0]['settings'][0].update({'id':'37','@odata.type':'#microsoft.graph.deviceManagementConfigurationSetting'})
    cases['unknown_type'][0]['settings'][0]['settingInstance']['@odata.type']='#future.type'
    cases.update({'filter_omitted':(settings,True),'filter_zero_explicit':(settings,True),'filter_include_missing':(settings,False),
                  'filter_zero_include':(settings,False),'filter_zero_exclude':(settings,False),'filter_zero_omitted_mode':(settings,True),
                  'filter_include_valid':(settings,True),'filter_exclude_valid':(settings,True),'filter_invalid_guid':(settings,False)})
    for name,(value,desired_valid) in cases.items():
        config['resource']={RESOURCE:{'fixture':{'name':'Synthetic validation fixture','platforms':'windows10','technologies':['mdm'],'settings':json.dumps(value,separators=(',',':'))}}}
        if name.startswith('filter_'):
            assignment={'type':'groupAssignmentTarget','group_id':'11111111-1111-4111-8111-111111111111','filter_type':'none'}
            if name.startswith('filter_zero_'): assignment['filter_id']='00000000-0000-0000-0000-000000000000'
            if name=='filter_include_missing': assignment['filter_type']='include'
            if name in ('filter_zero_include','filter_zero_exclude'): assignment['filter_type']=name.removeprefix('filter_zero_')
            if name=='filter_zero_omitted_mode': assignment.pop('filter_type')
            if name in ('filter_include_valid','filter_exclude_valid'):
                assignment.update(filter_id='44444444-4444-4444-8444-444444444444',filter_type=name.split('_')[1])
            if name=='filter_invalid_guid': assignment['filter_id']='not-a-guid'
            config['resource'][RESOURCE]['fixture']['assignments']=[assignment]
        (output/'main.tf.json').write_text(json.dumps(config,indent=2)+'\n')
        row=run([str(tofu),'validate','-json'],output,env,name)
        row['configuration_sha256']=hashlib.sha256((output/'main.tf.json').read_bytes()).hexdigest();row['desired_valid']=desired_valid
        try: row['observed_valid']=json.loads((output/(name+'.stdout')).read_text()).get('valid')
        except ValueError:row['observed_valid']=None
        row['matches_desired_contract']=row['observed_valid'] is desired_valid
        receipt['cases'][name]=row
        (output/(name+'.tf.json.txt')).write_bytes((output/'main.tf.json').read_bytes())
    receipt['schema_rpc_qualified']=receipt['schema']['returncode']==0
    receipt['hcl_validation_qualified']=receipt['schema_rpc_qualified'] and all(r['matches_desired_contract'] for r in receipt['cases'].values())
    (output/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'schema_rpc_qualified':receipt['schema_rpc_qualified'],'hcl_validation_qualified':receipt['hcl_validation_qualified'],'production_qualified':False}))

if __name__=='__main__':main()
