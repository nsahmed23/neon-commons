#!/usr/bin/env python3
"""Native private-store/job probe using recorded Graph bytes; creates no task.

Provide an already approved private parent and a NEW output name. No real
credential, tenant endpoint or Task Scheduler activation occurs. A successful
component receipt does not qualify the terminal or registered schedule.
"""
import argparse
from pathlib import Path,PureWindowsPath
import sys
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from intune_iac.io import AppError,canonical
from intune_iac import windows_storage as ws,windows_directory as wd,windows_workbench as ww
from intune_iac import windows_observation_jobs as jobs,windows_observation as targets
from intune_iac.windows_observer_credentials import CredentialReference
from intune_iac.observation_reader import ReaderSpec
from intune_iac.synthetic import generate_estate

TENANT='11111111-1111-4111-8111-111111111111';CLIENT='22222222-2222-4222-8222-222222222222';PRINCIPAL='44444444-4444-4444-8444-444444444444'

def fixture(estate):
    from urllib.parse import urlsplit
    import copy
    oid=estate['truth']['policies'][0]['id'];tenant=estate['truth']['tenant_id']
    rows=[{'method':'POST','host':'login.microsoftonline.com','path':'/'+tenant+'/oauth2/v2.0/token','status':200,'body':{'token_type':'Bearer','expires_in':3600,'access_token':'SYNTHETIC-NATIVE-JOB-ONLY'}},
        {'method':'GET','host':'graph.microsoft.com','path':"/v1.0/servicePrincipals(appId='"+CLIENT+"')?$select=id,appId,accountEnabled",'status':200,'body':{'id':PRINCIPAL,'appId':CLIENT,'accountEnabled':True}}]
    for kind in ('policies','settings','assignments'):
        collection=next(item for item in estate['capture']['collections'] if item['kind']==kind and item['owner_id']==(None if kind=='policies' else oid))
        for page in collection['pages']:
            url=urlsplit(page['request_url']);body=copy.deepcopy(page['body'])
            if kind=='assignments':
                for row in body['value']:row.update(source='direct',sourceId=None)
            rows.append({'method':'GET','host':'graph.microsoft.com','path':url.path+('?' + url.query if url.query else ''),'status':200,'body':body})
    return canonical({'schema_version':'intune-observer-fixture/1','responses':rows}),oid

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);p.add_argument('--start-boundary',required=True);args=p.parse_args();job=None;target=None;root=PureWindowsPath(args.output)
    try:
        ws.create_private_directory(str(root.parent),root.name);estate=generate_estate(seed=1845,policy_count=1);raw,oid=fixture(estate);tenant=estate['truth']['tenant_id']
        store=ww.WindowsWorkbenchStore.create(str(root/'store'),tenant);target=targets.bind_native_target(str(root/'store'),tenant);sid=target._binding['directory']['owner_sid']
        job=jobs.create_native_job(target,ReaderSpec(tenant,CLIENT,PRINCIPAL,(oid,)),output=str(root/'job'),credential_reference=CredentialReference('IntuneWorkbench/observer/qualification-only',sid,CLIENT),package_root=str(Path(__file__).resolve().parents[1]),interpreter=sys.executable,interval_seconds=60,max_duration_seconds=120,laboratory_fixture=raw)
        first=jobs.run_due(job);second=jobs.run_due(job);task=jobs.scheduler_artifacts(job,str(root/'inactive-task'),start_boundary=args.start_boundary,account_sid=sid)
        checks={'first_cycle_recorded':first['status']=='complete','second_cycle_not_due':second['status']=='not_due' and second['network_attempted'] is False,'no_live_assurance':first['attempt_record']['source_authenticity_verified'] is False,'task_not_installed':task['installed'] is False,'task_not_activated':task['activated'] is False,'collection_persisted':len(store.collection_history())==1}
        receipt={'status':'PASS' if all(checks.values()) else 'FAIL','scope':'Actual native Windows storage, finite job and inert XML with recorded Graph response fixture; no native Task Scheduler activation or live service evidence','checks':checks,'first':first,'second':second,'task':task,'platform_qualified':False,'production_approved':False}
        ws.create_new_file(str(root),'qualification-receipt.json',canonical(receipt));print(json.dumps({'status':receipt['status'],'checks':checks}));return 0 if all(checks.values()) else 1
    except AppError as error:
        print(json.dumps({'status':'BLOCKED','error_code':error.code,'native_checks_passed':0,'platform_qualified':False}));return 2
    finally:
        if job is not None:job.close()
        if target is not None:target.close()
if __name__=='__main__':raise SystemExit(main())
