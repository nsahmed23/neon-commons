"""Inactive native repository intent and immutable source proposal operations.

Uses the existing literal resolver/render/impact engine and private native store.
These routes do not edit repository source, run Git/provider or approve a plan.
"""
import copy
import difflib
import hashlib
from pathlib import PureWindowsPath
import re
import time
from .io import AppError,canonical,digest
from . import repository,windows_repository as source,windows_storage as storage
from .windows_workbench import WindowsWorkbenchStore


def _fail(code):raise AppError(code,'The native local source operation did not establish its exact identity, source, observation or publication scope.')


def _store(store):
    if type(store) is not WindowsWorkbenchStore:_fail('windows_source_store_required')
    return store


def _resolution(report):return {key:value for key,value in repository.public_resolution(report).items() if key!='native_source_access'}


def _import(store,root,stack,component,object_id,pointer,revision,backend,resource_address,api):
    from . import workbench_views as engine
    _store(store);engine._identity(object_id)
    if type(revision) is not str or not re.fullmatch('[0-9a-f]{40}',revision):engine._fail('workbench_repository_revision')
    report=source._resolve(root,engine._text(stack),engine._text(component),api)
    if report.get('status')!='resolved' or report.get('abstract') or not report.get('implementation_exists'):engine._fail('workbench_repository_unresolved')
    body=copy.deepcopy(engine._pointer(report['effective'],pointer));analysis=engine.semantics.analyze(body)
    if analysis['status']!='supported':_fail('windows_source_policy_projection_unsupported')
    scope=engine._scope({'repository':str(PureWindowsPath(root)),'stack':stack,'component':component,'backend':backend})
    data=engine._repository_intent(store,object_id,scope,revision,resource_address,pointer,body,report,analysis)
    data['native_source_snapshot']={'captured_root_identity':report['native_source_access']['root_identity'],
        'read_started_at':report['native_source_access']['read_started_at'],
        'read_completed_at':report['native_source_access']['read_completed_at'],
        'source_bytes_verified_at_read':True,'git_revision_verified':False,'publication_after_guard_release':True}
    return store.record_artifact('repository_intent',None,data)


def import_repository(store,root,stack,component,object_id,pointer,revision,backend,resource_address,*,git_executable=None,git_sha256=None):
    if git_executable is not None or git_sha256 is not None:_fail('windows_source_git_verification_unsupported')
    return _import(store,root,stack,component,object_id,pointer,revision,backend,resource_address,source._NativeAPI())


def _proposal(store,object_id,field,output,api,*,scope=None):
    from . import workbench_views as engine
    _store(store);value=engine.views(store,object_id,scope=scope);repo=value['repository'];observed=value['observed']
    if repo['status']!='recorded' or value['coverage']['observation']!='complete_fresh':engine._fail('workbench_source_acceptance_incomplete')
    if field not in {'/'+key for key in engine.semantics.FIELDS}:engine._fail('workbench_source_acceptance_field')
    new_value=engine._pointer(observed['body'],field);old_value=engine._pointer(repo['desired'],field)
    if canonical(new_value)==canonical(old_value):engine._fail('workbench_source_acceptance_no_change')
    root=repo['scope']['repository'];source.wd._components(root);source.wd._components(output)
    destination=PureWindowsPath(output);root_path=PureWindowsPath(root)
    if destination==root_path or destination.is_relative_to(root_path) or destination.is_relative_to(store.root):engine._fail('workbench_source_acceptance_output')
    started=time.time()
    with source._access(root,api) as access:
        resolver=repository._Repository(root,_access=access)
        fresh=resolver.resolve(repo['scope']['stack'],repo['scope']['component'])
        if digest(_resolution(fresh))!=digest({key:val for key,val in repo['resolution'].items() if key!='native_source_access'}):engine._fail('workbench_source_acceptance_stale')
        snapshot=repo.get('native_source_snapshot')
        if type(snapshot) is not dict or snapshot.get('captured_root_identity')!=access.root_identity:_fail('windows_source_root_binding_missing_or_changed')
        origin=fresh['provenance'].get(repo['effective_pointer']+field,{}).get('winner')
        if type(origin) is not dict or not {'path','pointer'}<=set(origin):engine._fail('workbench_source_acceptance_origin')
        path=access.contained(access.root/origin['path']);raw=access.read(path,repository.MAX_FILE_BYTES)
        if hashlib.sha256(raw).hexdigest()!=next((item['sha256'] for item in fresh['sources'] if item['path']==origin['path']),None):engine._fail('workbench_source_acceptance_stale')
        rendered=engine._render_source_proposal(raw,origin,old_value,new_value)
        impact=engine._source_impact(root,origin,discover=lambda _:repository._discover(resolver),
            resolve=lambda _,stack,component:repository._Repository(root,_access=access).resolve(stack,component))
        patch=''.join(difflib.unified_diff(raw.decode('utf-8').splitlines(True),rendered.decode().splitlines(True),
            fromfile='a/'+origin['path'],tofile='b/'+origin['path']))
        result=engine._source_proposal_document(store,object_id,field,repo,observed,origin,raw,rendered,impact)
        result['native_source_binding']={'root':root,'root_identity':access.root_identity,
            'source_file_identity':copy.deepcopy(access._directory(path.parent).files[path.name]['identity']),
            'scope':repo['scope'],'all_source_files':fresh['sources'],'read_started_at':started,
            'historical_intent_id':repo['artifact_id'],'historical_observation_snapshot_id':observed['snapshot_id'],
            'git_revision_verified':False,'platform_qualified':False}
    result['native_source_binding']['read_completed_at']=time.time()
    # Every original source handle closed successfully before publication. This
    # is an immutable proposal snapshot; any later edit must revalidate CAS.
    result['native_source_binding']['source_guards_released_before_publication']=True
    documents={'source.before.yaml':raw,'source.after.yaml':rendered,'change.patch':patch.encode()}
    result['proposal_files']={name:{'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)} for name,data in documents.items()}
    result['proposal_sha256']=digest(result)
    phase='before_output'
    try:
        phase='creating_output';storage._create_directory(str(destination.parent),destination.name,api);phase='output_created'
        for name,data in documents.items():storage._create_file(str(destination),name,data,api)
        phase='proposal_manifest_pending';storage._create_file(str(destination),'proposal.json',canonical(result)+b'\n',api)
        # Reopen all bytes in the completed new namespace; no caller path/label
        # makes a partial output a complete reviewed proposal.
        with source.wc._directory(destination,api) as saved:
            if set(saved.names())!=set(documents)|{'proposal.json'}:_fail('windows_source_proposal_namespace_changed')
            for name,data in {**documents,'proposal.json':canonical(result)+b'\n'}.items():
                if saved.read(name)!=data:_fail('windows_source_proposal_bytes_changed')
        return result
    except BaseException as error:
        error.source_proposal_outcome={'phase':phase,'retained_output':str(destination),'source_modified':False,
            'publication_uncertain':phase!='before_output','automatic_retry_permitted':False}
        raise


def propose_source_acceptance(store,object_id,field,output,*,scope=None):
    return _proposal(store,object_id,field,output,source._NativeAPI(),scope=scope)
