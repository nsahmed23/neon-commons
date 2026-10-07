#!/usr/bin/env python3
"""Qualification-only native local source operations; never tenant execution."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from intune_iac.io import AppError
from intune_iac.windows_workbench import WindowsWorkbenchStore
from intune_iac import workbench_views


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification-only',action='store_true',required=True)
    parser.add_argument('--store',required=True);parser.add_argument('--tenant',required=True)
    commands=parser.add_subparsers(dest='command',required=True)
    imp=commands.add_parser('repository-import')
    for name in ('repo','stack','component','object','pointer','revision','backend','resource-address'):imp.add_argument('--'+name,required=True)
    proposal=commands.add_parser('source-acceptance-propose')
    for name in ('object','field','output'):proposal.add_argument('--'+name,required=True)
    for name in ('source-review','source-edit'):
        command=commands.add_parser(name);command.add_argument('--proposal',required=True);command.add_argument('--digest',required=True)
        if name=='source-edit':
            command.add_argument('--expires-at',type=float,required=True);command.add_argument('--acknowledge-local-file-edit',action='store_true',required=True)
    status=commands.add_parser('source-edit-status');status.add_argument('--source-root',required=True);status.add_argument('--operation',required=True)
    recover=commands.add_parser('source-edit-recover');recover.add_argument('--source-root',required=True);recover.add_argument('--operation',required=True)
    recover.add_argument('--direction',choices=('complete','rollback','abort'),required=True);recover.add_argument('--expires-at',type=float,required=True)
    recover.add_argument('--acknowledge-local-file-edit',action='store_true',required=True)
    args=parser.parse_args(argv)
    try:
        store=WindowsWorkbenchStore(args.store,args.tenant)
        if args.command=='repository-import':
            value=workbench_views.import_repository(store,args.repo,args.stack,args.component,args.object,
                args.pointer,args.revision,args.backend,args.resource_address)
        elif args.command=='source-acceptance-propose':value=workbench_views.propose_source_acceptance(store,args.object,args.field,args.output)
        else:
            from intune_iac import windows_source_edit
            if args.command=='source-review':value=windows_source_edit.review_source_proposal(store,args.proposal,args.digest)
            elif args.command=='source-edit':value=windows_source_edit.apply_source_proposal(store,args.proposal,args.digest,args.expires_at,acknowledged=args.acknowledge_local_file_edit)
            elif args.command=='source-edit-status':value=windows_source_edit.inspect_source_edit(store,args.source_root,args.operation)
            else:value=windows_source_edit.recover_source_edit(store,args.source_root,args.operation,args.direction,args.expires_at,acknowledged=args.acknowledge_local_file_edit)

        result={'schema_version':'intune-windows-local-source/1','qualification_only':True,
            'workbench_profile_enabled':False,'platform_qualified':False,'production_approved':False,
            'source_modified':False if args.command in ('repository-import','source-acceptance-propose','source-review','source-edit-status') else None,
            'source_edit_requested':args.command in ('source-edit','source-edit-recover'),'tenant_mutation':False,'execution_authorized':False,'result':value}
        rendered=json.dumps(result,sort_keys=True,ensure_ascii=True,allow_nan=False)
        if len(rendered.encode())>16*1024*1024:raise AppError('windows_source_output_bound','Local source result exceeds the output bound.')
        print(rendered);return 0
    except AppError as error:
        print(json.dumps({'status':'error','error':{'code':error.code,'message':str(error)},
            'source_proposal_outcome':getattr(error,'source_proposal_outcome',None),
            'source_edit_outcome':getattr(error,'source_edit_outcome',None),
            'storage_outcome':getattr(error,'storage_outcome',None)},ensure_ascii=True),file=sys.stderr);return 3
    except (OSError,ValueError,TypeError):
        print(json.dumps({'status':'error','error':{'code':'windows_source_failed',
            'message':'Local source operation failed; retain all source, proposal and store evidence.'}}),file=sys.stderr);return 3

if __name__=='__main__':raise SystemExit(main())
