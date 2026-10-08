#!/usr/bin/env python3
"""Inactive native signed-evidence ingestion/navigation; no execution authority."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from intune_iac.io import AppError


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qualification-only',required=True,action='store_true')
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('inspect','ingest','reopen','link','history','copy-store'):
        child=sub.add_parser(name)
        if name not in ('history','copy-store'):
            for key in ('trust','verifier-pin','scratch'):child.add_argument('--'+key,required=True)
        if name in ('inspect','ingest'):
            for key in ('envelope','request'):child.add_argument('--'+key,required=True)
        if name in ('ingest','reopen','link','history','copy-store'):child.add_argument('--root',required=True)
        if name in ('reopen','link'):child.add_argument('--request-sha256',required=True)
        if name in ('inspect','reopen'):child.add_argument('--historical',action='store_true')
        if name in ('link','history'):child.add_argument('--object',required=True)
        if name=='link':child.add_argument('--evidence-store',required=True)
        if name=='copy-store':child.add_argument('--destination',required=True)
    args=parser.parse_args(argv)
    try:
        from intune_iac.windows_worker_evidence import inspect_windows_evidence
        from intune_iac.windows_worker_evidence_store import ingest_windows_evidence,reopen_windows_evidence,copy_windows_evidence_store
        from intune_iac.windows_workbench import WindowsWorkbenchStore
        from intune_iac import workbench_evidence_views as views
        if args.command=='inspect':value=inspect_windows_evidence(args.envelope,args.request,args.trust,args.verifier_pin,args.scratch,historical=args.historical)
        elif args.command=='ingest':value=ingest_windows_evidence(args.root,args.envelope,args.request,args.trust,args.verifier_pin,args.scratch)
        elif args.command=='reopen':value=reopen_windows_evidence(args.root,args.request_sha256,args.trust,args.verifier_pin,args.scratch,historical=args.historical)
        elif args.command=='copy-store':value=copy_windows_evidence_store(args.root,args.destination)
        elif args.command=='link':value=views.link(WindowsWorkbenchStore(args.root),args.object,args.evidence_store,args.request_sha256,args.trust,args.verifier_pin,args.scratch)
        else:value=views.history(WindowsWorkbenchStore(args.root),args.object)
        value.update(qualification_only=True,workbench_profile_enabled=False,platform_qualified=False)
        print(json.dumps(value,ensure_ascii=True,sort_keys=True));return 0
    except (AppError,OSError,ValueError,TypeError,KeyError) as error:
        print(json.dumps({'status':'FAIL','code':getattr(error,'code',type(error).__name__),'baseline_admissible':False,'execution_authorized':False},ensure_ascii=True),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
