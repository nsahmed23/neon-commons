"""Bounded literal no-op proof and immutable post-host output capture.

This module proves byte/content relationships only. Callers must independently
establish receiving-state authentication and bind the captured output record to
their durable host outcome before exposing the result. It grants no authority.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import stat
from intune_iac import protected,provider_execution as pe
from intune_iac.io import AppError,canonical,digest,parse_json
from intune_iac.provider_journey import _private
from intune_iac.worker_adoption_provider import PLAN_PATH,PLAN_JSON_PATH,PLAN_EXIT_PATH

VERSION='native-plan-output-capture/1'
LIMIT=32*1024*1024
FILES={'plan.bin':PLAN_PATH,'plan.json':PLAN_JSON_PATH,'exit.txt':PLAN_EXIT_PATH}


def _fail(code):raise AppError(code,'The exact native no-change plan output and independently supplied state/source relationship were not established.') from None

def _read(path,limit=LIMIT):
    path=_private(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    primary=None
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_uid!=os.geteuid() or before.st_mode&0o077 or not 0<before.st_size<=limit:_fail('plan_output_file_invalid')
        chunks=[];total=0
        while total<=limit:
            chunk=os.read(fd,min(1024*1024,limit+1-total))
            if not chunk:break
            chunks.append(chunk);total+=len(chunk)
        raw=b''.join(chunks)
        after=os.fstat(fd);named=os.lstat(path)
        fields=lambda value:(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns,value.st_uid,value.st_mode,value.st_nlink)
        if len(raw)!=before.st_size or fields(before)!=fields(after) or fields(after)!=fields(named):_fail('plan_output_file_changed')
        return raw
    except BaseException as error:primary=error;raise
    finally:
        try:os.close(fd)
        except BaseException as secondary:
            if primary is None:raise
            primary.add_note('Secondary plan-output descriptor cleanup: '+type(secondary).__name__)
            if isinstance(secondary,(KeyboardInterrupt,SystemExit)):raise secondary from primary


def paths(job_root):
    root=_private(job_root,directory=True)
    return {name:root/value.removeprefix('/job/') for name,value in FILES.items()}


def capture(job_root,archive,*,host_result):
    if type(host_result) is not dict or host_result.get('status')!='complete':_fail('plan_output_host_not_complete')
    host_sha=digest(host_result)
    source=paths(job_root);root=Path(archive).absolute();_private(root.parent,directory=True)
    # Read each artifact once through pinned regular-file descriptors. The raw
    # serialization is preserved, not regenerated from a parsed representation.
    raw={name:_read(path,64 if name=='exit.txt' else LIMIT) for name,path in source.items()}
    root.mkdir(mode=0o700,exist_ok=False);protected._sync(root.parent)
    for name,data in raw.items():protected._exclusive(root/name,data)
    facts={'schema_version':VERSION,'host_result_sha256':host_sha,'source_root':str(Path(job_root).absolute()),'archive_root':str(root),
        'artifacts':{name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'source_path':str(source[name])} for name,data in raw.items()},
        'receiving_state_authentication_established':False,'execution_authorized':False}
    protected._exclusive(root/'receipt.json',canonical(facts));return facts


def read(record,*,job_root,archive):
    if type(record) is not dict:_fail('plan_output_capture_required')
    raw_record=canonical(record);root=_private(archive,directory=True);source=paths(job_root)
    if (set(record)!={'schema_version','host_result_sha256','source_root','archive_root','artifacts','receiving_state_authentication_established','execution_authorized'}
            or type(record['host_result_sha256']) is not str or len(record['host_result_sha256'])!=64 or any(c not in '0123456789abcdef' for c in record['host_result_sha256'])
            or record['schema_version']!=VERSION or record['source_root']!=str(Path(job_root).absolute()) or record['archive_root']!=str(root)
            or record['receiving_state_authentication_established'] is not False or record['execution_authorized'] is not False
            or type(record['artifacts']) is not dict or set(record['artifacts'])!=set(FILES)
            or _read(root/'receipt.json',64*1024)!=raw_record):_fail('plan_output_capture_changed')
    data={}
    for name,path in source.items():
        pin=record['artifacts'][name]
        if (type(pin) is not dict or set(pin)!={'bytes','sha256','source_path'} or pin['source_path']!=str(path)
                or type(pin['bytes']) is not int or pin['bytes']<=0 or type(pin['sha256']) is not str or len(pin['sha256'])!=64
                or any(c not in '0123456789abcdef' for c in pin['sha256'])):_fail('plan_output_capture_changed')
        archived=_read(root/name,64 if name=='exit.txt' else LIMIT);current=_read(path,64 if name=='exit.txt' else LIMIT)
        if archived!=current or len(archived)!=pin['bytes'] or hashlib.sha256(archived).hexdigest()!=pin['sha256']:_fail('plan_output_artifact_changed')
        data[name]=archived
    return data


def _same(left,right):
    # JSON booleans and numbers (including integral floats) remain distinct.
    # Python's recursive equality intentionally does not provide that contract.
    return canonical(left)==canonical(right)


def _closed_mask(value):
    if value is False:return True
    if type(value) is dict:return all(_closed_mask(item) for item in value.values())
    if type(value) is list:return all(_closed_mask(item) for item in value)
    return False


def _resource(value,attributes,object_id):
    if (type(value) is not dict or set(value)!={'address','mode','type','name','provider_name','schema_version','values','sensitive_values','identity','identity_schema_version'}
            or value['address']!=pe.ADDRESS or value['mode']!='managed' or value['type']!=pe.RESOURCE or value['name']!='selected'
            or value['provider_name']!=pe.SOURCE or type(value['schema_version']) is not int or value['schema_version']!=0
            or not _same(value['values'],attributes) or not _closed_mask(value['sensitive_values']) or value['identity']!={'id':object_id}
            or type(value['identity_schema_version']) is not int or value['identity_schema_version']!=0):_fail('plan_output_resource_mismatch')


def _module(value,attributes,object_id):
    if type(value) is not dict or set(value)!={'root_module'}:_fail('plan_output_module_scope')
    root=value['root_module']
    if type(root) is not dict or set(root)!={'resources'} or type(root['resources']) is not list or len(root['resources'])!=1:_fail('plan_output_module_scope')
    _resource(root['resources'][0],attributes,object_id)


def validate(plan_raw,*,state_raw,source_raw,object_id,state_sha256,source_sha256,effective_inputs_sha256):
    """Literal supported representation; independent authentication belongs caller."""
    if (type(plan_raw) is not bytes or type(state_raw) is not bytes or type(source_raw) is not bytes
            or hashlib.sha256(state_raw).hexdigest()!=state_sha256 or hashlib.sha256(source_raw).hexdigest()!=source_sha256):_fail('plan_output_input_changed')
    plan,state,source=(parse_json(raw) for raw in (plan_raw,state_raw,source_raw))
    try:
        if (type(state) is not dict or type(state.get('version')) is not int or state.get('version')!=4 or state.get('terraform_version')!='1.13.1' or state.get('outputs')!={}
                or type(state.get('resources')) is not list or len(state['resources'])!=1):_fail('plan_output_state_scope')
        item=state['resources'][0]
        if (set(item)!={'mode','type','name','provider','instances'} or item['mode']!='managed' or item['type']!=pe.RESOURCE or item['name']!='selected'
                or item['provider']!='provider["'+pe.SOURCE+'"]' or len(item['instances'])!=1):_fail('plan_output_state_scope')
        instance=item['instances'][0];attributes=instance['attributes']
        if (set(instance)!={'schema_version','attributes','sensitive_attributes','identity','identity_schema_version'} or type(instance.get('schema_version')) is not int or instance.get('schema_version')!=0 or type(instance.get('identity_schema_version')) is not int or instance.get('identity_schema_version')!=0 or instance.get('identity')!={'id':object_id}
                or instance.get('sensitive_attributes')!=[] or type(attributes) is not dict or attributes.get('id')!=object_id):_fail('plan_output_state_identity')
        desired=source['resource'][pe.RESOURCE]['selected']
        if (set(source['resource'])!={pe.RESOURCE} or set(source['resource'][pe.RESOURCE])!={'selected'} or digest(desired)!=effective_inputs_sha256 or any(key not in attributes or not _same(attributes[key],value) for key,value in desired.items())):_fail('plan_output_source_scope')
        required={'format_version','terraform_version','variables','planned_values','resource_changes','prior_state','configuration','checks','timestamp','errored'}
        if (type(plan) is not dict or not required<=set(plan)<=required|{'resource_drift','output_changes','deferred_changes'}
                or plan['format_version']!='1.2' or plan['terraform_version']!='1.13.1' or plan['errored'] is not False
                or plan.get('resource_drift') not in (None,[]) or plan.get('deferred_changes') not in (None,[]) or plan.get('output_changes') not in (None,{})
                or plan['variables']!={'stage':{'value':'worker'}} or type(plan['resource_changes']) is not list or len(plan['resource_changes'])!=1):_fail('plan_output_not_noop')
        change=plan['resource_changes'][0]
        if (set(change)!={'address','mode','type','name','provider_name','change'} or change['address']!=pe.ADDRESS or change['mode']!='managed'
                or change['type']!=pe.RESOURCE or change['name']!='selected' or change['provider_name']!=pe.SOURCE):_fail('plan_output_change_scope')
        values=change['change']
        if (set(values)!={'actions','before','after','after_unknown','before_sensitive','after_sensitive','before_identity','after_identity'}
                or values['actions']!=['no-op'] or not _same(values['before'],attributes) or not _same(values['after'],attributes) or values['after_unknown']!={}
                or values['before_identity']!={'id':object_id} or values['after_identity']!={'id':object_id}
                or not _closed_mask(values['before_sensitive']) or not _closed_mask(values['after_sensitive'])):_fail('plan_output_values_mismatch')
        _module(plan['planned_values'],attributes,object_id)
        prior=plan['prior_state']
        if set(prior)!={'format_version','terraform_version','values'} or prior['format_version']!='1.0' or prior['terraform_version']!='1.13.1':_fail('plan_output_prior_state')
        _module(prior['values'],attributes,object_id)
        configuration=plan['configuration'];root=configuration['root_module'];entries=root['resources']
        if (set(configuration)!={'provider_config','root_module'} or set(root)!={'resources','variables'} or len(entries)!=1
                or not _same(root['variables'],{'stage':{'type':'string','required':True}})):_fail('plan_output_configuration_scope')
        expected_resource={'address':pe.ADDRESS,'mode':'managed','type':pe.RESOURCE,'name':'selected','provider_config_key':'microsoft365',
            'expressions':{key:{'constant_value':value} for key,value in desired.items()},'schema_version':0}
        if not _same(entries[0],expected_resource):_fail('plan_output_configuration_changed')
        expected_provider={'microsoft365':{'name':'microsoft365','full_name':pe.SOURCE,'version_constraint':'1.0.0',
            'expressions':{key:{'constant_value':value} for key,value in source['provider']['microsoft365'].items()}}}
        if not _same(configuration['provider_config'],expected_provider):_fail('plan_output_provider_configuration_changed')
        checks=[{'address':{'kind':'var','name':'stage','to_display':'var.stage'},'status':'pass','instances':[{'address':{'to_display':'var.stage'},'status':'pass'}]}]
        if not _same(plan['checks'],checks):_fail('plan_output_checks_unestablished')
    except (KeyError,TypeError,IndexError,AttributeError):_fail('plan_output_shape_unsupported')
    return {'schema_version':'native-noop-content-proof/1','object_id':object_id,'resource_address':pe.ADDRESS,
        'state_sha256':state_sha256,'source_sha256':source_sha256,'effective_inputs_sha256':effective_inputs_sha256,
        'full_values_sha256':digest(attributes),'plan_json_sha256':hashlib.sha256(plan_raw).hexdigest(),
        'before_after_planned_prior_values_equal_state':True,'source_configuration_equal':True,
        'receiving_state_authentication_established':False,'execution_authorized':False}


def qualify(record,*,job_root,archive,state_raw,source_raw,object_id,state_sha256,source_sha256,effective_inputs_sha256):
    data=read(record,job_root=job_root,archive=archive)
    if data['exit.txt']!=b'0\n':_fail('plan_output_exit_not_zero')
    proof=validate(data['plan.json'],state_raw=state_raw,source_raw=source_raw,object_id=object_id,state_sha256=state_sha256,source_sha256=source_sha256,effective_inputs_sha256=effective_inputs_sha256)
    return {'capture_sha256':digest(record),'artifacts':record['artifacts'],'content_proof':proof,'first_plan_no_change':True,'exit_code':0}
