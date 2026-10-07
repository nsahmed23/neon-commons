"""Terminal and automation interface for the Intune IaC plugin."""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import sys

from . import __version__
from .io import AppError, load_json


def doctor():
    dependencies = {}
    for package, module in [('jsonschema','jsonschema'),('PyYAML','yaml'),('python-hcl2','hcl2')]:
        try: version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: version = None
        dependencies[package] = {'available':importlib.util.find_spec(module) is not None, 'version':version}
    ready = all(v['available'] for v in dependencies.values())
    provider_platform = sys.platform == 'linux' and platform.machine() == 'x86_64'
    return {'version':__version__,'status':'ready' if ready else 'missing_dependencies',
            'python':platform.python_version(),'dependencies':dependencies,
            'capabilities':{'wizard':'available' if ready else 'missing_dependencies',
                'workbench':'persistent_synthetic_observation_history_and_reviewed_maintenance',
                'generation':'bounded_synthetic_mapping','production_capture':'explicit_read_only_credentials_required' if os.name=='posix' else 'unavailable_on_platform',
                'production_generation':'bounded_inactive_candidate','semantic_graph':'local_typed_graph',
                'atmos_resolution':'bounded_literal_with_provenance','repository_discovery':'local_read_only','action_runner':'local_actions',
                'clm':'optional_external_service','mcp':'stdio_with_explicit_filesystem_capabilities',
                'complete_journey':'receipt_reconstructed_local_simulation_or_gated_live_review',
                'synthetic_estates':'seeded_26_case_corpus_with_independent_oracle',
                'native_atmos':'pinned_linux_amd64_literal_comparison_requires_explicit_binary',
                'protected_execution':'fixed_local_fixture_only_no_cloud_authority',
                'guided_cohort_workflow':'local_receipt_backed', 'target_binding':'consistency_and_partial_get_observation',
                'plan_review':'offline_show_json', 'reconciliation':'local_simulation_and_fixed_native_output_fixture',
                'cloud_apply':'unavailable','state_import':'unavailable',
                'provider_journey':'operator_admitted_executor_signed_receipt_network_denied' if provider_platform else 'unsupported_platform',
                'signed_approval':'requires_operator_pinned_linux_x86_64_runtime' if provider_platform else 'unsupported_platform',
                'explicit_identity':'read_only_host_config_and_separate_inherited_credential_fds' if os.name=='posix' else 'unsupported_platform'},
            'executables':{name:bool(shutil.which(name)) for name in ['atmos','tofu','pwsh','codex','claude']},
            'live_qualified':False, 'native_host_qualified':False}


def _paths(parser, output=False):
    parser.add_argument('--input',required=True)
    parser.add_argument('--context',required=True)
    if output: parser.add_argument('--output',required=True)


def parser():
    p=argparse.ArgumentParser(prog='intune-iac',description='Inspect Intune captures, query relationships, and build verified local artifacts.')
    p.add_argument('--version',action='version',version=__version__)
    commands=p.add_subparsers(dest='command',required=True)
    from .workbench import add_parser as add_workbench_parser
    add_workbench_parser(commands)
    commands.add_parser('doctor',help='Report installed prerequisites and capability boundaries')
    _paths(commands.add_parser('inspect',help='Inspect one policy without writing output'))
    _paths(commands.add_parser('verify',help='Recheck an existing project against source-derived expectations'),True)
    gen=commands.add_parser('generate',help='Generate an owned local project and execution receipts')
    _paths(gen,True);gen.add_argument('--state-dir',default='.intune-iac/attempts')
    wiz=commands.add_parser('wizard',help='Start or resume the interactive local workflow')
    wiz.add_argument('--session',required=True)
    wiz.add_argument('--guided',action='store_true',help='Use the receipt-backed cohort authoring flow with a separate session')
    wiz.add_argument('--journey',action='store_true',help='Use the complete local lifecycle simulation or gated live review')
    wiz.add_argument('--journey-mode',choices=['simulation','live'],default=None)
    wiz.add_argument('--atmos-executable',help='Explicit pinned Atmos executable for the connected journey with --repo')
    wiz.add_argument('--tofu-executable',help='Explicit pinned OpenTofu for a disposable output-only local journey fixture; no native Intune provider')
    for name in ['input','context','output','repo','stack','component']:wiz.add_argument('--'+name)
    repo=commands.add_parser('repository',help='Discover stacks and resolve supported literal Atmos configuration').add_subparsers(dest='repository_command',required=True)
    repo_inspect=repo.add_parser('inspect');repo_inspect.add_argument('--root',required=True)
    repo_resolve=repo.add_parser('resolve');repo_resolve.add_argument('--root',required=True);repo_resolve.add_argument('--stack',required=True);repo_resolve.add_argument('--component',required=True)
    native=repo.add_parser('native',help='Compare admitted literal configuration with pinned Atmos 1.199.0')
    for name in ('root','stack','component','executable'):native.add_argument('--'+name,required=True)
    synthetic=commands.add_parser('synthetic',help='Generate and inspect reproducible synthetic estates').add_subparsers(dest='synthetic_command',required=True)
    sg=synthetic.add_parser('generate');sg.add_argument('--output',required=True);sg.add_argument('--seed',type=int,default=42);sg.add_argument('--policies',type=int,default=3);sg.add_argument('--case',default='baseline')
    si=synthetic.add_parser('inspect');si.add_argument('--input',required=True)
    action=commands.add_parser('action',help='Use the fixed local action registry')
    action.add_argument('operation',choices=['list','preview','run'])
    action.add_argument('action_id',nargs='?')
    action.add_argument('--parameters',help='JSON parameter file')
    action.add_argument('--state-dir',default='.intune-iac/attempts')
    graph=commands.add_parser('graph',help='Build/query the typed relationship graph').add_subparsers(dest='graph_command',required=True)
    build=graph.add_parser('build');build.add_argument('--input',required=True);build.add_argument('--context');build.add_argument('--atmos-root');build.add_argument('--output',required=True);build.add_argument('--state-dir',default='.intune-iac/attempts')
    query=graph.add_parser('query');query.add_argument('--graph',required=True);query.add_argument('--query',required=True);query.add_argument('--subject')
    judge=commands.add_parser('judge',help='Request an advisory assessment from the configured CLM service')
    judge.add_argument('--config',required=True);judge.add_argument('--claim',required=True);judge.add_argument('--evidence',required=True)
    cap=commands.add_parser('capture',help='Capture public Graph beta pages using an explicitly supplied read token')
    cap.add_argument('--tenant',required=True);cap.add_argument('--policy',required=True);cap.add_argument('--output',required=True);cap.add_argument('--token-env',default='INTUNE_GRAPH_TOKEN');cap.add_argument('--max-pages',type=int,default=100)
    cap.add_argument('--max-attempts-per-page',type=int,default=3,help='Bounded GET attempts per page, including the first (1 through 10)')
    cap.add_argument('--max-elapsed-seconds',type=float,default=120,help='Total network and retry budget, greater than zero and at most 120 seconds')
    cap.add_argument('--max-retry-delay-seconds',type=float,default=30,help='Maximum admitted Retry-After/backoff; a larger delay stops partial instead of retrying early')
    target=commands.add_parser('target',help='Inspect target evidence or explicitly collect partial service observations').add_subparsers(dest='target_command',required=True)
    ti=target.add_parser('inspect');ti.add_argument('--input',required=True)
    tc=target.add_parser('compare');tc.add_argument('--expected',required=True);tc.add_argument('--observed',required=True)
    collect=target.add_parser('collect');collect.add_argument('--input',required=True)
    collect.add_argument('--graph-token-env',default='INTUNE_GRAPH_TOKEN');collect.add_argument('--management-token-env',default='INTUNE_MANAGEMENT_TOKEN')
    authenticate=target.add_parser('authenticate',help='Read-only explicit identity binding; credentials arrive on inherited file descriptors')
    authenticate.add_argument('--input',required=True)
    authenticate.add_argument('--provider-secret-fd',required=True,type=int)
    authenticate.add_argument('--backend-secret-fd',required=True,type=int)
    provider=commands.add_parser('provider',help='Use an operator-admitted generated executor with external signed approval; network denied').add_subparsers(dest='provider_command',required=True)
    for operation in ('prepare','review','execute','reconcile','status','wizard'):
        command=provider.add_parser(operation)
        for name in ('executor-root','session','authority-config'):command.add_argument('--'+name,required=True)
        if operation=='execute':command.add_argument('--receipt',required=True)
    plan=commands.add_parser('plan',help='Review a bounded OpenTofu show -json document without running a provider').add_subparsers(dest='plan_command',required=True)
    pr=plan.add_parser('review');pr.add_argument('--input',required=True)
    simulation=commands.add_parser('simulation',help='Exercise a disposable local policy/assignment operation; never cloud execution').add_subparsers(dest='simulation_command',required=True)
    create=simulation.add_parser('create');create.add_argument('--root',required=True);create.add_argument('--input',required=True)
    prepare=simulation.add_parser('prepare');prepare.add_argument('--root',required=True)
    sr=simulation.add_parser('run');sr.add_argument('--root',required=True);sr.add_argument('--request',required=True);sr.add_argument('--state-dir',required=True)
    rec=simulation.add_parser('reconcile');rec.add_argument('--root',required=True);rec.add_argument('--operation-id',required=True);rec.add_argument('--state-dir',required=True)
    mcp=commands.add_parser('mcp',help='Serve local tools within operator-approved filesystem roots')
    mcp.add_argument('--read-root',action='append',default=[],help='Existing absolute directory readable by MCP tools; repeat as needed')
    mcp.add_argument('--write-root',action='append',default=[],help='Existing absolute directory writable by MCP tools; repeat as needed')
    return p


def execute(args):
    if args.command=='workbench':
        from .workbench import command
        return command(args)
    if args.command=='doctor':return doctor()
    if args.command=='inspect':
        from .engine import inspect_source
        return inspect_source(args.input,args.context)
    if args.command=='verify':
        from .engine import verify_project
        return verify_project(args.input,args.context,args.output)
    if args.command=='generate':
        from .runner import run
        return run('generate',{'input':args.input,'context':args.context,'output':args.output},args.state_dir)
    if args.command=='wizard':
        if args.journey:
            if args.guided:raise AppError('conflicting_wizard_modes','Select only one wizard flow.')
            from .journey import run_journey
            return run_journey(args.session,args.input,args.context,args.output,repo=args.repo,stack=args.stack,component=args.component,mode=args.journey_mode,atmos_executable=args.atmos_executable,tofu_executable=args.tofu_executable)
        if args.journey_mode:raise AppError('journey_mode_requires_journey','Use --journey with --journey-mode.')
        if args.atmos_executable:raise AppError('journey_mode_requires_journey','Use --journey with --atmos-executable.')
        if args.tofu_executable:raise AppError('journey_mode_requires_journey','Use --journey with --tofu-executable.')
        from .wizard import run_wizard
        return run_wizard(args.session,args.input,args.context,args.output,repo=args.repo,stack=args.stack,component=args.component,guided=args.guided)
    if args.command=='repository':
        if args.repository_command=='native':
            from .native_atmos import resolve_native_atmos
            return resolve_native_atmos(args.root,args.stack,args.component,executable=args.executable)
        from .repository import discover_repository, resolve_component, public_resolution
        if args.repository_command=='inspect':return discover_repository(args.root)
        return public_resolution(resolve_component(args.root,args.stack,args.component))
    if args.command=='synthetic':
        from .synthetic import write_estate, inspect_estate
        if args.synthetic_command=='generate':return write_estate(args.output,seed=args.seed,policy_count=args.policies,case=args.case)
        return inspect_estate(load_json(args.input))
    if args.command=='action':
        from .runner import preview,run,REGISTRY,UNAVAILABLE
        if args.operation=='list':
            return {'actions':[
                {'id':name,'effect':'local_write' if spec['write'] else 'local_read','available':True}
                for name,spec in REGISTRY.items()], 'unavailable':sorted(UNAVAILABLE)}
        if not args.action_id or not args.parameters:raise AppError('invalid_parameters','Action ID and --parameters are required.')
        return (preview if args.operation=='preview' else run)(args.action_id,load_json(args.parameters),args.state_dir)
    if args.command=='graph':
        if args.graph_command=='query':
            from .graph import query_graph
            return query_graph(load_json(args.graph),args.query,args.subject)
        from .runner import run
        params={'input':args.input,'output':args.output}
        for name in ['context','atmos_root']:
            if getattr(args,name):params[name]=getattr(args,name)
        return run('graph_build',params,args.state_dir)
    if args.command=='judge':
        from .judge import assess
        return assess(args.config,args.claim,load_json(args.evidence))
    if args.command=='capture':
        from .capture import capture
        def progress(event):
            print(json.dumps(event,ensure_ascii=True,sort_keys=True,allow_nan=False),file=sys.stderr,flush=True)
        return capture(args.tenant,args.policy,args.output,token_env=args.token_env,max_pages=args.max_pages,
                       max_attempts_per_page=args.max_attempts_per_page,max_elapsed_seconds=args.max_elapsed_seconds,
                       max_retry_delay_seconds=args.max_retry_delay_seconds,progress=progress)
    if args.command=='target':return _target_command(args)
    if args.command=='provider':
        if sys.platform != 'linux' or platform.machine() != 'x86_64':
            raise AppError('provider_platform_unsupported','The provider journey requires the qualified Linux x86_64 runtime.')
        from .provider_journey import provider_command
        return provider_command(args)
    if args.command=='plan':
        from .execution import review_plan
        return review_plan(load_json(args.input))
    if args.command=='simulation':return _simulation_command(args)
    raise AppError('unknown_command','Unknown command.')


def _target_command(args):
    if args.target_command=='authenticate':
        if os.name != 'posix':
            raise AppError('identity_fd_platform_unsupported','Explicit credential file descriptors require a Unix host.')
        from .provider_journey import authenticate_target
        return authenticate_target(args)
    from .target import inspect_target, compare_targets, collect_azure_observations
    if args.target_command=='inspect':return inspect_target(load_json(args.input))
    if args.target_command=='compare':return compare_targets(load_json(args.expected),load_json(args.observed))
    graph_token=os.environ.get(args.graph_token_env)
    management_token=os.environ.get(args.management_token_env)
    if not graph_token or not management_token:
        raise AppError('missing_explicit_credentials','Both explicit read-token environment variables are required.')
    return collect_azure_observations(load_json(args.input),graph_token=graph_token,management_token=management_token)


def _simulation_command(args):
    from .execution import LocalFixtureAdapter, create_local_fixture, prepare_operation, execute_operation
    if args.simulation_command=='create':
        source=load_json(args.input)
        fields={'policy','assignments','desired_policy','desired_assignments'}
        if not isinstance(source,dict) or set(source)!=fields:
            raise AppError('invalid_fixture','Simulation input requires current and desired policy and assignments.')
        adapter=create_local_fixture(args.root,**source)
        return {'status':'created','assurance':'local_simulation_only','external_execution':False,'binding':adapter.binding()}
    adapter=LocalFixtureAdapter(args.root)
    if args.simulation_command=='prepare':return prepare_operation(adapter)
    if args.simulation_command=='run':return execute_operation(load_json(args.request),args.state_dir,adapter=adapter)
    from .reconciliation import reconcile_operation
    return dict(reconcile_operation(args.operation_id,args.state_dir,adapter=adapter),status='review_only')


def exit_code(result):
    status=result.get('status')
    if status in {'FAIL','INVALID_TASK','INFRA_ERROR'} or result.get('success') is False:return 3
    if status in {'INCONCLUSIVE','BLOCKED','NOT_RUN','blocked_live_qualification','unknown_outcome','denied','throttled','interrupted'}:return 2
    if status in {'partial_or_divergent','service_converged_state_unreconciled','readback_unresolved','desired_state_observed_execution_unconfirmed'}:return 2
    if status == 'missing_dependencies':return 5
    if status in {'blocked','needs_review','unavailable','partial','abstained','abstain','review_only','changes_require_review'}:return 2
    if status in {'output_conflict','conflict','locked'}:return 4
    if status in {'rejected','failed','outcome_unknown','failed_no_effect_verified','invalid','mismatch','reconciliation_required'}:
        return 4 if result.get('error',{}).get('code')=='output_conflict' else 3
    if result.get('offline_mapping_complete') is False:return 2
    nested=result.get('result')
    if isinstance(nested,dict):return exit_code(nested)
    return 0


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='mcp':
            from .mcp import serve, FilesystemAuthority
            return serve(authority=FilesystemAuthority(args.read_root,args.write_root) if args.read_root or args.write_root else None)
        result=execute(args)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True,allow_nan=False))
        if args.command=='capture' and result.get('cancelled') is True:return 130
        return exit_code(result)
    except AppError as error:
        print(json.dumps({'status':'error','error':{'code':error.code,'message':error.message}}),file=sys.stderr)
        return 4 if error.code in {'output_conflict','capture_output_conflict'} else (2 if error.code in {'capture_platform_unavailable','provider_platform_unsupported','identity_fd_platform_unsupported'} else 3)
    except ImportError:
        print(json.dumps({'status':'error','error':{'code':'missing_dependencies','message':'Install the pinned runtime requirements in your Python environment.'}}),file=sys.stderr)
        return 5
    except KeyboardInterrupt:return 130
    except (ValueError,TypeError,KeyError,OSError):
        print(json.dumps({'status':'error','error':{'code':'invalid_request','message':'Request failed validation or local I/O.'}}),file=sys.stderr)
        return 3
