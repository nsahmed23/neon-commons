"""Terminal and automation interface for the Intune IaC plugin."""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import shutil
import sys

from . import __version__
from .io import AppError, load_json

# Help for the read-token routes. No flag takes the token itself.
_CLAIMS_RULE=' Claims inside a token are unverified: they may cause an early local refusal and explain a service refusal; they never permit a call or an action.'
_TOKEN_ENV_HELP='Name of an environment variable that holds the token (not the token). The token must then sit in the environment of this process, so set it for this one command only; the descriptor route (-fd flag) keeps it out of the environment.'+_CLAIMS_RULE
_TOKEN_FD_HELP='Number of an inherited file descriptor to read the token from (private regular file or FIFO, 4096 bytes, 5 seconds, ASCII; the descriptor is closed after it is read). This route keeps the token out of the parent session (environment, history, process list) and wins over the environment-variable route, which is then not read. Example: --FLAG 3 3<token-file.'+_CLAIMS_RULE


class _Parser(argparse.ArgumentParser):
    """Every parser (this class is also the subparsers' class): no abbreviated options, and no argument VALUE is ever
    echoed. A person can paste a token where a number or a name belongs, so the usage error names options only."""

    def __init__(self,*args,**kwargs):
        kwargs.setdefault('allow_abbrev',False)
        super().__init__(*args,**kwargs)

    def error(self,message):
        self.print_usage(sys.stderr)
        self.exit(2,'%s: error: %s\n'%(self.prog,_parser_message(message)))


_SAFE_PARSER_TEXT=(re.compile(r'expected (?:one|at least one) argument'),re.compile(r'expected \d+ arguments?'),
    re.compile(r'expects the number of an inherited file descriptor'),re.compile(r'not allowed with argument [-\w., /]+'))


def _parser_message(message):
    # REDACTION POINT for the usage-error path. argparse puts values into several of its messages (invalid int value,
    # invalid choice, unrecognized arguments), so only fixed text and option names survive; anything else is generic.
    if message.startswith('unrecognized arguments: '):
        return 'unrecognized arguments (%d); argument values are never shown'%len(message.split(': ',1)[1].split())
    if message.startswith('the following arguments are required: '):
        return message
    match=re.fullmatch(r'(argument [-\w., /<>{}|]+): (.*)',message,re.S)
    if match:
        rest=match.group(2)
        if any(p.fullmatch(rest) for p in _SAFE_PARSER_TEXT):return message
        if rest.startswith('invalid choice'):return match.group(1)+': invalid choice (the value is not shown)'
        return match.group(1)+': invalid value (the value is not shown)'
    return 'invalid arguments (values are not shown)'


# The last line of defence at the text output boundary. Renderers escape record text through safe_text; this is for the surface
# that forgot. Every C0 control (the line feed, carriage return and tab as safe_text writes them), DEL, the C1 controls, the line and
# paragraph separators and the bidirectional overrides and isolates are shown as a visible escape, so no text-mode command can
# move the cursor, rewrite the terminal, start a row of its own or reorder what a person reads. Text safe_text already escaped
# holds none of these and is unchanged. Not applied to --json: JSON output keeps its own escaping.
#
# The guarded set, final: U+0000 to U+001F (C0), U+007F (DEL), U+0080 to U+009F (C1), U+061C (Arabic letter mark), U+200B to U+200F
# (zero-width space, non-joiner, joiner, left-to-right and right-to-left marks), U+2028 and U+2029 (line and paragraph separators),
# U+202A to U+202E (embeddings and overrides), U+2060 to U+2064 (word joiner and the invisible math operators), U+2066 to U+2069
# (isolates) and U+FEFF (byte order mark, zero-width no-break space). The direction marks and the invisible format characters
# reorder or hide what a person reads without moving the cursor.
_TEXT_GUARDED=re.compile('[\x00-\x1f\x7f-\x9f\u061c\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]')
_TEXT_NAMED={'\n':'\\n','\r':'\\r','\t':'\\t'}


def text_guard(text):
    """One row of text with every guarded character shown as the escape safe_text uses."""
    return _TEXT_GUARDED.sub(lambda m:_TEXT_NAMED.get(m.group(),'\\u%04x'%ord(m.group())),text)


def text_guard_rows(rows):
    """The rows of a text screen as the one string to write: each row guarded alone, so a line feed inside a value is escaped and
    cannot start a row of its own; the newline between rows is the only one left."""
    return '\n'.join(text_guard(row) for row in rows)


def _write_text(rows):
    """The one place text-mode commands write their screen."""
    print(text_guard_rows(rows));sys.stdout.flush()


def _descriptor(value):
    # A descriptor flag is parsed here, not with type=int: int()'s error text carries the value, and a token is exactly
    # what a person may paste there by mistake.
    if not isinstance(value,str) or not (value.isascii() and value.isdigit()) or len(value)>9:
        raise argparse.ArgumentTypeError('expects the number of an inherited file descriptor')
    return int(value)


def _tenant(value):
    # Parsed here, not echoed: a refusal never repeats what was typed (a token pasted by mistake stays out of the message).
    from .signin_facts import GUID
    if not isinstance(value,str) or not GUID.fullmatch(value):
        raise argparse.ArgumentTypeError('expects a tenant GUID')
    return value.lower()


def _policy(value):
    from .signin_facts import GUID
    if not isinstance(value,str) or not GUID.fullmatch(value):
        raise argparse.ArgumentTypeError('expects a policy GUID')
    return value.lower()


def _account(value):
    from .signin_facts import account_argument_ok
    if not account_argument_ok(value):
        raise argparse.ArgumentTypeError('expects an account name (letters, digits and . _ @ + -)')
    return value


def _fd_token(descriptor,owner=None):
    if os.name != 'posix':
        raise AppError('identity_fd_platform_unsupported','Explicit credential file descriptors require a Unix host.')
    from .provider_journey import read_token_fd
    return read_token_fd(descriptor,owner)


def _start_signin(args):
    # start runs no process unless --check-signin asks for the CLI listing; the flag without a goal has nothing to show.
    if not args.check_signin:return None
    if os.name != 'posix':
        raise AppError('identity_fd_platform_unsupported','Sign-in reuse needs a Unix host (inherited descriptors and bounded child output).')
    if not args.goal:raise AppError('signin_check_needs_goal','--check-signin needs --goal (it adds the sign-in to that goal\'s readiness).')
    from .signin import detect
    return detect(args.check_signin)


def _fd_owner(*descriptors):
    # One owner for every descriptor the route was given: all are closed once on any exit, a consumed one never again.
    if any(d is not None for d in descriptors) and os.name == 'posix':
        from .provider_journey import DescriptorOwner
        return DescriptorOwner(*[d for d in descriptors if d is not None])
    import contextlib
    return contextlib.nullcontext()


def doctor(executables=True):
    # executables=False leaves out the one fact that reads an environment value (the search path); start --goal uses it.
    from .host_capabilities import report as host_report
    host = host_report()
    dependencies = {}
    for package, module in [('jsonschema','jsonschema'),('PyYAML','yaml'),('python-hcl2','hcl2')]:
        try: version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: version = None
        dependencies[package] = {'available':importlib.util.find_spec(module) is not None, 'version':version}
    ready = all(v['available'] for v in dependencies.values())
    provider_platform = host['profiles']['protected_worker']['status'] == 'IMPLEMENTED'
    from .build_identity import report as build_report
    return {'version':__version__,'status':'ready' if ready else 'missing_dependencies', 'host_capabilities': host,
            # Which release build this copy came from, so a problem report names it; a checkout has none.
            'build': build_report(),
            'status_scope':'Runtime package dependencies only; route prerequisites are reported separately in host_capabilities.',
            'python':platform.python_version(),'dependencies':dependencies,
            'capabilities':{'wizard':'available' if ready else 'missing_dependencies',
                'workbench':('persistent_scoped_observation_history_and_reviewed_maintenance'
                    if host['profiles']['workbench_store']['status']=='IMPLEMENTED' else 'unsupported_host'),
                'generation':'bounded_synthetic_mapping','production_capture':'explicit_read_only_credentials_required' if os.name=='posix' else 'unavailable_on_platform',
                'production_generation':'bounded_inactive_candidate','semantic_graph':'local_typed_graph',
                'atmos_resolution':'bounded_literal_with_provenance','repository_discovery':'local_read_only','action_runner':'local_actions',
                'clm':'optional_external_service','mcp':'stdio_with_explicit_filesystem_capabilities',
                'complete_journey':'modeled_workbench_and_separate_native_local_service_routes',
                'synthetic_estates':'seeded_26_case_corpus_with_independent_oracle',
                'native_atmos':'pinned_linux_amd64_literal_comparison_requires_explicit_binary',
                'protected_execution':'network_denied_laboratory_worker_and_separate_exact_plan_service' if provider_platform else 'unsupported_platform',
                'guided_cohort_workflow':'local_receipt_backed', 'target_binding':'consistency_and_partial_get_observation',
                'plan_review':'exact_saved_plan_and_provenance_review', 'reconciliation':'sealed_independent_readback_preserves_uncertain_execution',
                'cloud_apply':'unavailable','state_import':'separately_approved_protected_service_and_legacy_provider_prepare' if provider_platform else 'unsupported_platform',
                'provider_journey':'operator_admitted_executor_signed_receipt_network_denied' if provider_platform else 'unsupported_platform',
                'signed_approval':'requires_operator_pinned_linux_x86_64_runtime' if provider_platform else 'unsupported_platform',
                'explicit_identity':'read_only_host_config_and_separate_inherited_credential_fds' if os.name=='posix' else 'unsupported_platform'},
            **({'executables':{name:bool(shutil.which(name)) for name in ['atmos','tofu','pwsh','codex','claude']}} if executables else {}),
            'route_scope': {
                'protected_service': {'implementation': 'common_exact_plan_worker_contract',
                    'available_on_host': provider_platform, 'normal_apply': 'separately_approved_protected_controller',
                    'requires': ['reviewed_host_policy', 'exact_runtime_and_tool_pins', 'authenticated_target',
                                 'separate_exact_operation_approval', 'qualified_execution_platform'],
                    'platform_qualified': False},
                'adoption': {'legacy_provider_prepare': 'network_denied_executor_route',
                    'native_service_preparation': 'durable_manifest_preparation_and_review_cli',
                    'durable_protected_service_import': 'implemented_separately_approved_state_only_import',
                    'host_prerequisites_discovered': provider_platform,
                    'controller_dispatch': 'exact_signed_approval_and_process_held_runtime',
                    'terminal_dispatches_import': False,
                    'verification': 'independent_state_and_graph_readback_plus_no_change_first_plan',
                    'local_native_evidence': 'separate_source_and_artifact_bound_receipts',
                    'requires': ['reviewed_host_policy', 'exact_runtime_and_tool_pins', 'authenticated_target',
                                 'complete_declared_ownership_scan', 'separate_exact_import_approval',
                                 'qualified_execution_platform', 'organizational_production_approval'],
                    'platform_qualified': False, 'live_qualified': False, 'production_approved': False},
                'native_windows': {'components': 'inactive_private_store_observation_and_console_adapters',
                    'ordinary_profile': 'unsupported_pending_integration_and_native_qualification',
                    'platform_qualified': False}},
            'live_qualified':False, 'native_host_qualified':False}


def _paths(parser, output=False):
    parser.add_argument('--input',required=True)
    parser.add_argument('--context',required=True)
    if output: parser.add_argument('--output',required=True)


def parser():
    p=_Parser(prog='intune-iac',description='Inspect Intune captures, query relationships, and build verified local artifacts.')
    p.add_argument('--version',action='version',version=__version__)
    commands=p.add_subparsers(dest='command',required=True)
    from .workbench import add_parser as add_workbench_parser
    add_workbench_parser(commands)
    from .workbench_parsers import add_worker_parser, add_service_parser
    add_worker_parser(commands)
    add_service_parser(commands)
    from .adoption_cli import add_parser as add_adoption_parser
    add_adoption_parser(commands)
    from .artifact_vault import add_parser as add_artifact_parser
    add_artifact_parser(commands)
    from .sim_cli import add_parser as add_simulate_parser
    add_simulate_parser(commands)
    commands.add_parser('doctor',help='Report installed prerequisites and capability boundaries')
    start=commands.add_parser('start',help='Survey a working directory: what already exists, its states and the next step (read-only, offline)')
    start.add_argument('directory',nargs='?',default='.')
    start.add_argument('--json',action='store_true',help='Print the survey as JSON instead of the readable screen')
    from .readiness import OPERATIONS as goals
    start.add_argument('--goal',choices=goals,help='Also show what one goal needs and what is missing, from facts start can gather offline')
    start.add_argument('--check-signin',choices=('azure','github','all'),help='With --goal: also look for an existing sign-in by running the CLI listing (az account list --output json, gh auth status --json hosts); reads no token')
    catalog=commands.add_parser('catalog',help='List the integrations this build holds, what each goal needs here, and the saved projects (read-only, offline)')
    catalog.add_argument('directory',nargs='?',default='.')
    catalog.add_argument('--json',action='store_true',help='Print the catalog as JSON instead of the readable screen')
    catalog.add_argument('--goal',choices=goals,help='Show one goal only (and its one next action)')
    catalog.add_argument('--check-signin',choices=('azure','github','all'),help='Look for an existing sign-in by running the CLI listing (az account list --output json, gh auth status --json hosts); reads no token; a sign-in is never permission')
    engineering=commands.add_parser('engineering',help='Show engineering orchestration records from a loopctl export (read-only, offline)')
    engineering.add_argument('--records',help='Directory written by loopctl export (header.json and events.jsonl); without it the command says nothing is configured')
    engineering.add_argument('--controller-log',help='Controller log (JSON lines); its dispatch lines are counted, never modelled')
    engineering.add_argument('--evidence-root',action='append',default=[],help='Absolute directory that evidence references must lie inside to be reported as recorded; repeat as needed. No path text is ever shown')
    engineering.add_argument('--json',action='store_true',help='Print the view as JSON instead of text')
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
    from .pin_profiles import CURRENT, LEGACY, tools
    native=repo.add_parser('native',help='Compare admitted literal configuration with pinned Atmos %s (Atmos %s only for legacy reproduction)'%(tools(CURRENT)['atmos_version'],tools(LEGACY)['atmos_version']))
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
    judge=commands.add_parser('judge',help='Request an advisory assessment from the configured CLM service (refuses URL passwords, secret-named pairs, JWTs, keys, and hex or base64 runs of 32 or more characters (a single 32+ character token, padding included, that decodes as base64 is refused even if it is a compound word; a member named for a secret may hold only a policy key, a relative .tfstate path or a fixed redacted placeholder; a Settings Catalog setting id such as device_vendor_msft_... is accepted only as the whole value of settingDefinitionId or setting_definition_id) in the claim and evidence, with a position and never the text; it cannot prove a secret is absent, so do not put secrets in evidence)')
    judge.add_argument('--config',required=True);judge.add_argument('--claim',required=True);judge.add_argument('--evidence',required=True)
    cap=commands.add_parser('capture',help='Capture public Graph beta pages using an explicitly supplied read token')
    cap.add_argument('--tenant',required=True);cap.add_argument('--policy',required=True);cap.add_argument('--output',required=True);cap.add_argument('--token-env',default='INTUNE_GRAPH_TOKEN',help=_TOKEN_ENV_HELP)
    cap.add_argument('--token-fd',type=_descriptor,help=_TOKEN_FD_HELP);cap.add_argument('--max-pages',type=int,default=100)
    cap.add_argument('--max-attempts-per-page',type=int,default=3,help='Bounded GET attempts per page, including the first (1 through 10)')
    cap.add_argument('--max-elapsed-seconds',type=float,default=120,help='Total network and retry budget, greater than zero and at most 120 seconds')
    cap.add_argument('--max-retry-delay-seconds',type=float,default=30,help='Maximum admitted Retry-After/backoff; a larger delay stops partial instead of retrying early')
    target=commands.add_parser('target',help='Inspect target evidence or explicitly collect partial service observations').add_subparsers(dest='target_command',required=True)
    ti=target.add_parser('inspect');ti.add_argument('--input',required=True)
    tc=target.add_parser('compare');tc.add_argument('--expected',required=True);tc.add_argument('--observed',required=True)
    collect=target.add_parser('collect');collect.add_argument('--input',required=True)
    collect.add_argument('--graph-token-env',default='INTUNE_GRAPH_TOKEN',help=_TOKEN_ENV_HELP);collect.add_argument('--management-token-env',default='INTUNE_MANAGEMENT_TOKEN',help=_TOKEN_ENV_HELP)
    collect.add_argument('--graph-token-fd',type=_descriptor,help=_TOKEN_FD_HELP);collect.add_argument('--management-token-fd',type=_descriptor,help=_TOKEN_FD_HELP)
    authenticate=target.add_parser('authenticate',help='Read-only explicit identity binding; credentials arrive on inherited file descriptors')
    authenticate.add_argument('--input',required=True)
    authenticate.add_argument('--provider-secret-fd',required=True,type=_descriptor)
    authenticate.add_argument('--backend-secret-fd',required=True,type=_descriptor)
    signin=commands.add_parser('signin',help='Reuse an existing az or gh sign-in: show it, check it against the context tenant (reads no token)').add_subparsers(dest='signin_command',required=True)
    status=signin.add_parser('status',help='Run the CLI listing (az account list --output json, and gh auth status --json hosts with --provider) and judge it against the context tenant')
    status.add_argument('--tenant',type=_tenant,help='The context tenant (a GUID); without it the sign-in is shown but never called usable')
    status.add_argument('--account',type=_account,help='The account to use when several are signed in; it must be the one the Azure CLI uses by default')
    status.add_argument('--provider',choices=('azure','github','all'),default='azure')
    status.add_argument('--deadline',type=float,default=15.0,help='Seconds allowed for each CLI call (greater than zero, at most 60)')
    status.add_argument('--json',action='store_true',help='Print the result as JSON (for scripts) instead of the readable screen')
    collect_with=signin.add_parser('collect',help='Collect read-only evidence (like capture) with the reused Azure sign-in: a short-lived token goes to the collecting child on an inherited file descriptor, never an argument or the environment')
    collect_with.add_argument('--tenant',required=True,type=_tenant)
    collect_with.add_argument('--policy',required=True,type=_policy)
    collect_with.add_argument('--output',required=True,help='New directory for the capture')
    collect_with.add_argument('--account',type=_account,help='The account to use when several are signed in; it must be the one the Azure CLI uses by default')
    collect_with.add_argument('--deadline',type=float,default=15.0,help='Seconds allowed for each az call (greater than zero, at most 60)')
    collect_with.add_argument('--collect-deadline',type=float,default=120.0,help='Seconds allowed for the collecting command (greater than zero, at most 600)')
    collect_with.add_argument('--json',action='store_true',help='Print the result as JSON (for scripts) instead of the readable screen')
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
    if args.command=='start':
        from .entry import goal_readiness, survey
        value=survey(args.directory,relative_to=os.getcwd())
        if args.goal:value['readiness']=goal_readiness(value,args.goal,_start_signin(args))
        else:_start_signin(args)
        return value
    if args.command=='catalog':
        from .catalog import build
        from .entry import survey
        value=survey(args.directory,relative_to=os.getcwd())
        # The sign-in listing runs only when asked; the catalog reads it as a verdict, never as permission.
        signin=None
        if args.check_signin:
            from .signin import detect
            signin=detect(args.check_signin)
        return build(value,signin=signin,goal=args.goal,relative_to=os.getcwd())
    if args.command=='engineering':
        from .engineering_view import command
        return command(args)
    if args.command=='workbench':
        from .workbench import command
        return command(args)
    if args.command=='worker':
        from .host_capabilities import require_profile
        require_profile('protected_worker')
        from .protected_worker import command
        return command(args)
    if args.command=='adoption':
        from .adoption_cli import command
        return command(args)
    if args.command=='service':
        from .service_cli import command
        return command(args)
    if args.command=='artifact':
        from .host_capabilities import require_profile
        require_profile('artifact_vault')
        from .artifact_vault import command
        return command(args)
    if args.command=='simulate':
        from .sim_cli import command
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
        with _fd_owner(args.token_fd) as owner:
            token=_fd_token(args.token_fd,owner) if args.token_fd is not None else None
        return capture(args.tenant,args.policy,args.output,token_env=args.token_env,token=token,max_pages=args.max_pages,
                       max_attempts_per_page=args.max_attempts_per_page,max_elapsed_seconds=args.max_elapsed_seconds,
                       max_retry_delay_seconds=args.max_retry_delay_seconds,progress=progress)
    if args.command=='signin':return _signin_command(args)
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


def _deadline(value):
    if not isinstance(value,float) or not 0<value<=60:
        raise AppError('signin_deadline_invalid','The deadline must be greater than zero and at most 60 seconds.')
    return value


def _signin_command(args,presentation=False):
    if os.name != 'posix':
        raise AppError('identity_fd_platform_unsupported','Sign-in reuse needs a Unix host (inherited descriptors and bounded child output).')
    from . import signin
    if args.signin_command=='collect':
        if not isinstance(args.collect_deadline,float) or not 0<args.collect_deadline<=600:
            raise AppError('signin_deadline_invalid','The collect deadline must be greater than zero and at most 600 seconds.')
        if presentation:return signin.collect_view(args.tenant,args.policy,args.output,args.account,_deadline(args.deadline),args.collect_deadline)
        return signin.collect(args.tenant,args.policy,args.output,args.account,_deadline(args.deadline),args.collect_deadline)
    if presentation:return signin.status_view(args.tenant,args.account,args.provider,_deadline(args.deadline))
    return signin.status_report(args.tenant,args.account,args.provider,_deadline(args.deadline))


def _target_command(args):
    if args.target_command=='authenticate':
        if os.name != 'posix':
            raise AppError('identity_fd_platform_unsupported','Explicit credential file descriptors require a Unix host.')
        from .provider_journey import authenticate_target
        return authenticate_target(args)
    from .target import inspect_target, compare_targets, collect_azure_observations
    if args.target_command=='inspect':return inspect_target(load_json(args.input))
    if args.target_command=='compare':return compare_targets(load_json(args.expected),load_json(args.observed))
    with _fd_owner(args.graph_token_fd,args.management_token_fd) as owner:
        if args.graph_token_fd is not None and args.graph_token_fd==args.management_token_fd:
            raise AppError('identity_separate_credential_fds_required','Use a separate file descriptor for each token.')
        # Each token comes from its descriptor when one is named (the environment variable is then not read), else
        # from the environment variable it names. The owner closes whichever descriptor a failure left unread.
        graph_token=_fd_token(args.graph_token_fd,owner) if args.graph_token_fd is not None else os.environ.get(args.graph_token_env)
        management_token=_fd_token(args.management_token_fd,owner) if args.management_token_fd is not None else os.environ.get(args.management_token_env)
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
    if status in {'blocked','needs_review','unavailable','partial','abstained','abstain','review_only','changes_require_review','repository_handoff'}:return 2
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
        if args.command=='start' and not args.json:
            # The guided entry is read by a person first; --json keeps the machine form.
            from .entry import goal_readiness, start_lines, survey
            value=survey(args.directory,relative_to=os.getcwd())
            goal=goal_readiness(value,args.goal,_start_signin(args)) if args.goal else None
            if goal is None:_start_signin(args)
            _write_text(start_lines(value,shutil.get_terminal_size((100,40)).columns,goal,goal_hint=goal is None))
            return 0
        if args.command=='simulate' and args.format=='text':
            # A person reads this; --format json keeps the machine form, which is the schema result.
            from .sim_cli import text_lines
            _write_text(text_lines(args))
            return 0
        if args.command=='signin' and not args.json:
            # A person reads the sign-in status or the collect result; --json keeps the data form for scripts. The exit code is the
            # same either way. This is the only caller of the text routes: the presentation comes back beside the result, never inside it.
            from .signin_facts import collect_lines, status_lines
            result,shown=_signin_command(args,presentation=True)
            code=exit_code(result)
            render=collect_lines if args.signin_command=='collect' else status_lines
            _write_text(render(result,shutil.get_terminal_size((100,40)).columns,code,shown))
            return code
        result=execute(args)
        if args.command=='catalog' and not args.json:
            # A person reads the catalog; --json keeps the data form. Read-only, so the exit is 0.
            from .catalog import catalog_lines
            _write_text(catalog_lines(result,shutil.get_terminal_size((100,40)).columns))
            return 0
        if args.command=='engineering' and not args.json:
            # A person reads the engineering view; --json keeps the data form. Read-only, so the exit is 0.
            from .engineering_view import lines_for
            _write_text(lines_for(result))
            return 0
        if args.command=='workbench' and getattr(args,'workbench_command',None)=='workflow' and not args.json:
            # A person reads the workflow map; --json keeps the data form. The same lanes as the workspace layer, 80 columns
            # when piped and the terminal's width otherwise, in ASCII where the output encoding is not UTF-8. Read-only.
            from .engineering_view import output_width
            from .workbench_screens import workflow_text_lines
            encoding=(getattr(sys.stdout,'encoding',None) or '').lower().replace('-','').replace('_','')
            _write_text(workflow_text_lines(result,output_width(),'unicode' if encoding=='utf8' else 'ascii'))
            return 0
        if (getattr(args,'workbench_command',None)=='workspace' and isinstance(result,dict)
                and result.get('status')=='interrupted' and sys.stdout.isatty()):
            # A person reads this after Ctrl-C: sentences with the exact next step; a pipe keeps the JSON.
            from .workbench import interrupted_text
            _write_text(interrupted_text(result,shutil.get_terminal_size((100,40)).columns))
            return exit_code(result)
        try:
            print(json.dumps(result,ensure_ascii=True,sort_keys=True,allow_nan=False));sys.stdout.flush()
        except BrokenPipeError:
            # The reader left (for example `| head`): exit as a writer killed by SIGPIPE would, quietly, and keep
            # Python's own flush at exit from failing again.
            os.dup2(os.open(os.devnull,os.O_WRONLY),sys.stdout.fileno())
            return 141
        if args.command=='capture' and result.get('cancelled') is True:return 130
        return exit_code(result)
    except AppError as error:
        detail = {'code':error.code,'message':error.message}
        if error.code == 'host_profile_unsupported' and type(getattr(error, 'details', None)) is dict:
            detail['details'] = error.details
        if type(getattr(error, 'effects', None)) is dict:
            detail['effects'] = error.effects
        print(json.dumps({'status':'error','error':detail}),file=sys.stderr)
        return 4 if error.code in {'output_conflict','capture_output_conflict'} else (2 if error.code in {'capture_platform_unavailable','provider_platform_unsupported','identity_fd_platform_unsupported','host_profile_unsupported'} else 3)
    except ImportError:
        print(json.dumps({'status':'error','error':{'code':'missing_dependencies','message':'Install the pinned runtime requirements in your Python environment.'}}),file=sys.stderr)
        return 5
    except KeyboardInterrupt:return 130
    except (ValueError,TypeError,KeyError,OSError):
        print(json.dumps({'status':'error','error':{'code':'invalid_request','message':'Request failed validation or local I/O.'}}),file=sys.stderr)
        return 3
