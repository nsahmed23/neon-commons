#!/usr/bin/env python3
"""Inactive native text inspection route for explicit local qualification.

No tenant calls, writes, host-profile activation, credential loading or plan
execution. This route does not establish Windows platform qualification.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from intune_iac.io import AppError
from intune_iac.windows_workbench import WindowsWorkbenchStore


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification-only',action='store_true',required=True)
    parser.add_argument('--store',required=True)
    parser.add_argument('--tenant',required=True)
    parser.add_argument('--limit',type=int,default=100)
    parser.add_argument('--offset',type=int,default=0)
    commands=parser.add_subparsers(dest='command',required=True)
    overview=commands.add_parser('overview');overview.add_argument('--query')
    for name in ('inspect','history','raw'):
        commands.add_parser(name).add_argument('object_id')
    for name in ('collections','operations','artifacts'):
        commands.add_parser(name).add_argument('--object-id')
    commands.add_parser('storage-status')
    args=parser.parse_args(argv)
    try:
        if not 1<=args.limit<=1000 or not 0<=args.offset<=1000000:
            raise AppError('windows_inspect_query_limit','Use a bounded page and nonnegative offset.')
        store=WindowsWorkbenchStore(args.store,args.tenant)
        page={'limit':args.limit,'offset':args.offset}
        if args.command=='overview':value=store.overview(query=args.query,**page)
        elif args.command=='inspect':value=store.inspect(args.object_id)
        elif args.command=='history':value=store.history(args.object_id,**page)
        elif args.command=='raw':value=store.raw_capture_observation(args.object_id)
        elif args.command=='collections':value=store.collection_history(args.object_id,**page)
        elif args.command=='operations':value=store.operations(args.object_id,**page)
        elif args.command=='artifacts':value=store.artifacts(object_id=args.object_id,**page)
        else:value=store.storage_status()
        result={'schema_version':'intune-windows-inspection/1','evidence_class':'local_readonly_inspection',
            'qualification_only':True,'workbench_profile_enabled':False,'platform_qualified':False,
            'production_approved':False,'service_authentication_reestablished':False,'result':value}
        rendered=json.dumps(result,ensure_ascii=True,sort_keys=True,allow_nan=False)
        if len(rendered.encode('utf-8'))>16*1024*1024:
            raise AppError('windows_inspect_output_limit','Request a smaller page.')
        print(rendered);return 0
    except AppError as error:
        print(json.dumps({'status':'error','error':{'code':error.code,'message':str(error)}},ensure_ascii=True),file=sys.stderr)
        return 3
    except (OSError,ValueError,TypeError):
        print(json.dumps({'status':'error','error':{'code':'windows_inspect_failed',
            'message':'Read-only qualification failed; retain source artifacts for inspection.'}}),file=sys.stderr)
        return 3


if __name__=='__main__':raise SystemExit(main())
