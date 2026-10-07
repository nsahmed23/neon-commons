#!/usr/bin/env python3
"""Inactive native observer component CLI. It cannot register or enable tasks."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from intune_iac.io import AppError
from intune_iac import windows_observation_jobs as jobs,windows_observation as targets
from intune_iac.windows_observer_credentials import CredentialReference
from intune_iac.observation_reader import ReaderSpec
from intune_iac import windows_capture as capture


def parser():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    create=sub.add_parser('create',help='Create an inactive native read-only job; no credential read or network request.')
    for name in ('store','tenant','client','principal','output','credential-target','owner-sid'):create.add_argument('--'+name,required=True)
    create.add_argument('--object',action='append',required=True);create.add_argument('--interval-seconds',type=int,default=300);create.add_argument('--max-duration-seconds',type=int,default=120);create.add_argument('--laboratory-fixture')
    for name in ('run','status','prepare-task'):
        command=sub.add_parser(name);command.add_argument('--job',required=True)
        if name=='prepare-task':command.add_argument('--output',required=True);command.add_argument('--start-boundary',required=True);command.add_argument('--owner-sid',required=True)
    return p

def main(argv=None):
    args=parser().parse_args(argv);job=None;target=None
    try:
        if args.command=='create':
            target=targets.bind_native_target(args.store,args.tenant)
            fixture=None if args.laboratory_fixture is None else capture._reference_bytes(args.laboratory_fixture,target._api,16*1024*1024)
            job=jobs.create_native_job(target,ReaderSpec(args.tenant,args.client,args.principal,tuple(sorted(set(args.object)))),output=args.output,
                credential_reference=CredentialReference(args.credential_target,args.owner_sid,args.client),package_root=str(Path(__file__).resolve().parents[1]),interpreter=sys.executable,
                interval_seconds=args.interval_seconds,max_duration_seconds=args.max_duration_seconds,laboratory_fixture=fixture)
            result={**jobs.job_status(job),'status':'created'}
        else:
            job=jobs.open_native_job(args.job);target=job.target
            result=jobs.run_due(job) if args.command=='run' else jobs.job_status(job) if args.command=='status' else jobs.scheduler_artifacts(job,args.output,start_boundary=args.start_boundary,account_sid=args.owner_sid)
        print(json.dumps(result,sort_keys=True,ensure_ascii=True));return 0 if result.get('status') not in ('failed','blocked','interrupted') else 2
    except AppError as error:
        result={'status':'BLOCKED','error_code':error.code,'platform_qualified':False,'production_approved':False}
        for name in ('storage_outcome','observation_outcome'):
            if hasattr(error,name):result[name]=getattr(error,name)
        print(json.dumps(result,sort_keys=True,ensure_ascii=True));return 2
    except KeyboardInterrupt:
        print(json.dumps({'status':'INTERRUPTED','recovery':'Preserve the native journal and capture bytes; inspect the same job before a fresh read.'}));return 130
    finally:
        if job is not None:job.close()
        if target is not None:target.close()
if __name__=='__main__':raise SystemExit(main())
