#!/usr/bin/env python3
"""Read-only worker export and local evidence ingest; never executes a worker."""
import argparse
import base64
import json
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from intune_iac import worker_evidence as contract,worker_evidence_posix as host
from intune_iac.io import AppError,canonical,digest


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    request=sub.add_parser('request');request.add_argument('--manifest',required=True);request.add_argument('--trust',required=True);request.add_argument('--output',required=True)
    prepare=sub.add_parser('prepare')
    for name in ('request','trust','publisher','job-root','policy','output'):prepare.add_argument('--'+name,required=True)
    prepare.add_argument('--capture-root');prepare.add_argument('--store-root');prepare.add_argument('--state-raw')
    for action in ('assemble','inspect','ingest','reopen'):
        part=sub.add_parser(action)
        for name in ('trust','verifier','scratch'):part.add_argument('--'+name,required=True)
        if action in ('inspect','reopen'):part.add_argument('--historical',action='store_true')
        if action=='assemble':
            for name in ('statement','signature','request','output'):part.add_argument('--'+name,required=True)
        elif action=='reopen':part.add_argument('--evidence-store',required=True);part.add_argument('--request-sha256',required=True)
        else:
            for name in ('envelope','request'):part.add_argument('--'+name,required=True)
            if action=='ingest':part.add_argument('--evidence-store',required=True)
    args=parser.parse_args()
    try:
        # A loose file has no store to hold the durable clock mark, so a current judgment is refused here (as on the Windows
        # route): current admissibility is `ingest` followed by `reopen`; `inspect --historical` is history only.
        if args.action=='inspect' and not args.historical:contract.fail('worker_evidence_inspect_requires_store')
        policy=host.load(args.trust)
        if args.action=='request':
            value=contract.make_request(host.load(args.manifest),policy,uuid.uuid4().hex);host.write_new(args.output,value)
            result={'status':'CREATED','request_sha256':digest(value),'execution_authorized':False}
        elif args.action=='prepare':
            value=host.prepare(host.load(args.request),policy,host.load(args.publisher),args.job_root,args.policy,capture_root=args.capture_root,store_root=args.store_root,state_raw=args.state_raw)
            host.write_new(args.output,value);result={'status':'PREPARED_UNSIGNED','statement_sha256':digest(value),'signature_domain_hex':contract.DOMAIN.hex(),'execution_authorized':False}
        else:
            verifier=host.DetachedVerifier(args.verifier,args.scratch)
            if args.action=='reopen':result=host.reopen(args.evidence_store,args.request_sha256,policy,verifier,historical=args.historical)
            else:
                req=None if args.action=='ingest' else host.load(args.request)
                if args.action=='assemble':
                    envelope={'schema_version':'signed-worker-evidence/1','payload':host.load(args.statement),'signature':base64.b64encode(host.read(args.signature,64)).decode()}
                    result=contract.verify_envelope(envelope,req,policy,verifier,now=int(time.time()),historical=True).result();host.write_new(args.output,envelope)
                else:
                    if args.action=='ingest':result=host.ingest_raw(args.evidence_store,host.read(args.envelope),host.read(args.request),policy,verifier)
                    else:result=contract.verify_envelope(host.load(args.envelope),req,policy,verifier,now=int(time.time()),historical=args.historical).result()
        print(json.dumps(result,sort_keys=True,ensure_ascii=True));return 0
    except (AppError,OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({'status':'FAIL','code':getattr(error,'code',type(error).__name__),'baseline_admissible':False,'execution_authorized':False}),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
