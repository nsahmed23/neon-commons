"""Small sequential stdio MCP server. No model, shell, cloud or credential tools."""
from __future__ import annotations

import json
from pathlib import Path
import stat
import sys

from . import __version__
from .io import AppError, MAX_BYTES, load_json, parse_json


def _schema(properties,required):
    return {'type':'object','properties':properties,'required':required,'additionalProperties':False}


S={'type':'string','minLength':1}
LOCAL_ACTIONS=['inspect','generate','graph_build','graph_query','repository_inspect','repository_resolve']
TOOLS=[
    {'name':'intune_doctor','description':'Report local prerequisites and supported capability boundaries.','inputSchema':_schema({},[]),'annotations':{'readOnlyHint':True,'openWorldHint':False}},
    {'name':'intune_inspect','description':'Inspect a local versioned capture and context. Returns preserved observations and blockers; does not write files.','inputSchema':_schema({'input':S,'context':S},['input','context']),'annotations':{'readOnlyHint':True,'openWorldHint':False}},
    {'name':'intune_preview','description':'Describe a fixed local action and evidence binding without executing it or writing receipts.','inputSchema':_schema({'action':{'enum':LOCAL_ACTIONS},'parameters':{'type':'object'},'state_dir':S},['action','parameters','state_dir']),'annotations':{'readOnlyHint':True,'openWorldHint':False}},
    {'name':'intune_run_local','description':'Run one registered local action with file-conflict protection and receipts. No shell, provider, or cloud execution.','inputSchema':_schema({'action':{'enum':LOCAL_ACTIONS},'parameters':{'type':'object'},'state_dir':S},['action','parameters','state_dir']),'annotations':{'readOnlyHint':False,'destructiveHint':False,'openWorldHint':False}},
    {'name':'intune_graph_query','description':'Query typed local policy, targeting, setting, impact and Atmos declaration relationships.','inputSchema':_schema({'graph':S,'query':{'enum':['policies','assignments','why-setting','impact','dependencies','placement']},'subject':S},['graph','query']),'annotations':{'readOnlyHint':True,'openWorldHint':False}},
    {'name':'intune_repository_inspect','description':'Discover local Atmos stacks and components without evaluating templates or executing commands.','inputSchema':_schema({'root':S},['root']),'annotations':{'readOnlyHint':True,'openWorldHint':False}},
    {'name':'intune_repository_resolve','description':'Resolve supported literal Atmos imports and inheritance. Return structural evidence and origins with configuration values omitted.','inputSchema':_schema({'root':S,'stack':S,'component':S},['root','stack','component']),'annotations':{'readOnlyHint':True,'openWorldHint':False}},
    {'name':'intune_plan_review','description':'Inspect local OpenTofu show JSON for changes, unknowns and preservation contradictions. This never authorizes execution.','inputSchema':_schema({'input':S},['input']),'annotations':{'readOnlyHint':True,'openWorldHint':False}},
    {'name':'intune_target_inspect','description':'Inspect a supplied local target binding. Consistency does not authenticate identity, ownership or approval.','inputSchema':_schema({'input':S},['input']),'annotations':{'readOnlyHint':True,'openWorldHint':False}},
    {'name':'intune_target_compare','description':'Compare all validated local target-binding fields without network requests or authorization.','inputSchema':_schema({'expected':S,'observed':S},['expected','observed']),'annotations':{'readOnlyHint':True,'openWorldHint':False}},
]


def _valid_initialize(params):
    """Validate required negotiation metadata before changing connection state."""
    version = params.get('protocolVersion')
    capabilities = params.get('capabilities')
    client = params.get('clientInfo')
    return (isinstance(version, str) and bool(version.strip())
            and isinstance(capabilities, dict)
            and all(isinstance(capabilities[key], dict)
                    for key in ('roots', 'sampling', 'elicitation', 'experimental') if key in capabilities)
            and isinstance(client, dict)
            and all(isinstance(client.get(key), str) and client[key].strip()
                    for key in ('name', 'version')))


class FilesystemAuthority:
    """Operator-provided capability, never accepted in model tool arguments.

    This confines the server's path selection on a cooperative filesystem. An
    attacker controlling the server process or racing filesystem ancestors needs
    an OS sandbox; path validation is not a replacement for that isolation.
    """
    def __init__(self, read_roots, write_roots):
        def roots(values):
            result=[]
            for value in values:
                path=Path(value)
                if (not path.is_absolute() or not path.is_dir()
                        or any(p.is_symlink() for p in (path,*path.parents))):
                    raise AppError('filesystem_authority_invalid','Authority roots must be existing absolute regular directories.')
                result.append(path.resolve())
            return tuple(result)
        self.read_roots=roots(read_roots)
        self.write_roots=roots(write_roots)

    def check(self, value, *, write=False):
        if not isinstance(value,str) or not value or '\x00' in value:
            raise AppError('filesystem_authority_denied','Requested path is outside the operator capability.')
        path=Path(value)
        if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path,*path.parents)):
            raise AppError('filesystem_authority_denied','Requested path is outside the operator capability.')
        resolved=path.resolve()
        roots=self.write_roots if write else self.read_roots
        if not any(resolved.is_relative_to(root) for root in roots):
            raise AppError('filesystem_authority_denied','Requested path is outside the operator capability.')
        # A pathname under an approved root does not prove that its inode is
        # exclusively scoped there. The other hard-link names are unknowable
        # from this path, so shared regular files are unsupported for both
        # reads and writes. Actual readers repeat this check after opening.
        try:
            info = path.stat()
        except FileNotFoundError:
            return  # A not-yet-created output still passes root confinement.
        except OSError:
            raise AppError('filesystem_authority_denied','Requested path could not be safely inspected.') from None
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise AppError('filesystem_authority_denied','Hard-linked files are outside the operator capability.')


def _check_authority(name,args,authority):
    if name=='intune_doctor':return
    if not isinstance(authority,FilesystemAuthority):
        raise AppError('filesystem_authority_required','Start this server with operator-approved read/write roots.')
    for key in ('input','context','expected','observed','graph','root'):
        if key in args:authority.check(args[key])
    if name in {'intune_preview','intune_run_local'}:
        # The journal is an effect even when the selected action only reads.
        authority.check(args['state_dir'],write=True)
        params=args['parameters']
        for key in ('input','context','graph','root','atmos_root'):
            if key in params:authority.check(params[key])
        if 'output' in params:
            authority.check(params['output'],write=True)
            # Runner lock files live beside the target; confine those effects too.
            authority.check(str(Path(params['output']).parent),write=True)


def call_tool(name,args,*,authority=None):
    tool=next((t for t in TOOLS if t['name']==name),None)
    if tool is None:raise AppError('unknown_tool','Unknown tool.')
    from jsonschema import Draft202012Validator
    if not isinstance(args,dict) or not Draft202012Validator(tool['inputSchema']).is_valid(args):
        raise AppError('invalid_parameters','Tool arguments do not match the declared schema.')
    _check_authority(name,args,authority)
    if name=='intune_doctor':
        from .cli import doctor
        return doctor()
    if name=='intune_inspect':
        from .engine import inspect_source
        return inspect_source(args['input'],args['context'])
    if name=='intune_plan_review':
        from .execution import review_plan
        return review_plan(load_json(args['input']))
    if name in {'intune_target_inspect','intune_target_compare'}:
        from .target import inspect_target, compare_targets
        if name=='intune_target_inspect':return inspect_target(load_json(args['input']))
        return compare_targets(load_json(args['expected']),load_json(args['observed']))
    if name in {'intune_repository_inspect','intune_repository_resolve'}:
        from .repository import discover_repository, resolve_component, public_resolution
        if name == 'intune_repository_inspect':return discover_repository(args['root'])
        return public_resolution(resolve_component(args['root'],args['stack'],args['component']))
    if name in {'intune_preview','intune_run_local'}:
        from .runner import preview,run
        return (preview if name=='intune_preview' else run)(args['action'],args['parameters'],args['state_dir'])
    from .graph import query_graph
    return query_graph(load_json(args['graph']),args['query'],args.get('subject'))


def serve(input_stream=None,output_stream=None,*,authority=None):
    stream=input_stream or sys.stdin.buffer
    output=output_stream or sys.stdout
    phase='new'
    def send(message):
        output.write(json.dumps(message,ensure_ascii=True,allow_nan=False,separators=(',',':'))+'\n');output.flush()
    while True:
        line=stream.readline(MAX_BYTES+1)
        if not line:return 0
        if len(line)>MAX_BYTES:
            send({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Message size limit exceeded.'}})
            return 1
        request=None
        try:
            request=parse_json(line.decode('utf-8') if isinstance(line, bytes) else line)
            if not isinstance(request,dict) or request.get('jsonrpc')!='2.0' or not isinstance(request.get('method'),str):
                send({'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Invalid request.'}});continue
            method=request['method'];params=request.get('params',{})
            if 'id' not in request:
                if (method == 'notifications/initialized' and phase == 'negotiated'
                        and isinstance(params, dict)):
                    phase = 'ready'
                continue
            ident=request['id']
            if isinstance(ident,bool) or not isinstance(ident,(int,str)):
                send({'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Invalid request ID.'}});continue
            response={'jsonrpc':'2.0','id':ident}
            if not isinstance(params,dict):
                response['error']={'code':-32602,'message':'Invalid parameters.'}
            elif method=='initialize':
                if phase != 'new':
                    response['error']={'code':-32600,'message':'Initialization already negotiated.'}
                elif not _valid_initialize(params):
                    response['error']={'code':-32602,'message':'Invalid initialization parameters.'}
                else:
                    requested=params['protocolVersion']
                    version=requested if requested in {'2024-11-05','2025-03-26','2025-06-18'} else '2025-06-18'
                    phase='negotiated'
                    response['result']={'protocolVersion':version,'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'intune-iac','version':__version__}}
            elif method=='ping':response['result']={}
            elif phase != 'ready':response['error']={'code':-32000,'message':'Complete initialization first.'}
            elif method=='tools/list':response['result']={'tools':TOOLS}
            elif method=='tools/call':
                name=params.get('name')
                if not any(t['name']==name for t in TOOLS):
                    response['error']={'code':-32602,'message':'Unknown tool.'}
                else:
                    try:
                        result=call_tool(name,params.get('arguments',{}),authority=authority)
                        failed=result.get('status') in {'error','rejected','failed','outcome_unknown','failed_no_effect_verified','needs_review','unavailable','invalid','mismatch'}
                        response['result']={'content':[{'type':'text','text':json.dumps(result,ensure_ascii=True,allow_nan=False)}],'isError':failed}
                    except AppError as error:
                        response['result']={'content':[{'type':'text','text':json.dumps({'error':{'code':error.code,'message':error.message}})}],'isError':True}
                    except (ValueError,TypeError,KeyError,OSError,ImportError):
                        response['result']={'content':[{'type':'text','text':'{"error":{"code":"tool_failed","message":"Local tool failed validation or prerequisites."}}'}],'isError':True}
            else:response['error']={'code':-32601,'message':'Method not found.'}
            send(response)
        except (AppError, UnicodeError):
            send({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Invalid JSON message.'}})
        except KeyboardInterrupt:return 130
