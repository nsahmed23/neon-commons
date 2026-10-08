"""Pure literal no-op content decoder shared by worker and portable reader.

Exact extraction from worker_plan_evidence.py SHA 5c8dba489c21f6d23d792ba64d639e8bf228d7a0176e5619dc655349c4cda06c.
Byte/content relationships only; no receiving-state authentication or authority.
"""
from __future__ import annotations
import hashlib
from .io import AppError,canonical,digest,parse_json
RESOURCE='microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json'
ADDRESS=RESOURCE+'.selected'
SOURCE='registry.terraform.io/deploymenttheory/microsoft365'

def _fail(code):raise AppError(code,'The exact native no-change plan output and independently supplied state/source relationship were not established.') from None

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
            or value['address']!=ADDRESS or value['mode']!='managed' or value['type']!=RESOURCE or value['name']!='selected'
            or value['provider_name']!=SOURCE or type(value['schema_version']) is not int or value['schema_version']!=0
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
        if (set(item)!={'mode','type','name','provider','instances'} or item['mode']!='managed' or item['type']!=RESOURCE or item['name']!='selected'
                or item['provider']!='provider["'+SOURCE+'"]' or len(item['instances'])!=1):_fail('plan_output_state_scope')
        instance=item['instances'][0];attributes=instance['attributes']
        if (set(instance)!={'schema_version','attributes','sensitive_attributes','identity','identity_schema_version'} or type(instance.get('schema_version')) is not int or instance.get('schema_version')!=0 or type(instance.get('identity_schema_version')) is not int or instance.get('identity_schema_version')!=0 or instance.get('identity')!={'id':object_id}
                or instance.get('sensitive_attributes')!=[] or type(attributes) is not dict or attributes.get('id')!=object_id):_fail('plan_output_state_identity')
        desired=source['resource'][RESOURCE]['selected']
        if (set(source['resource'])!={RESOURCE} or set(source['resource'][RESOURCE])!={'selected'} or digest(desired)!=effective_inputs_sha256 or any(key not in attributes or not _same(attributes[key],value) for key,value in desired.items())):_fail('plan_output_source_scope')
        required={'format_version','terraform_version','variables','planned_values','resource_changes','prior_state','configuration','checks','timestamp','errored'}
        if (type(plan) is not dict or not required<=set(plan)<=required|{'resource_drift','output_changes','deferred_changes'}
                or plan['format_version']!='1.2' or plan['terraform_version']!='1.13.1' or plan['errored'] is not False
                or plan.get('resource_drift') not in (None,[]) or plan.get('deferred_changes') not in (None,[]) or plan.get('output_changes') not in (None,{})
                or plan['variables']!={'stage':{'value':'worker'}} or type(plan['resource_changes']) is not list or len(plan['resource_changes'])!=1):_fail('plan_output_not_noop')
        change=plan['resource_changes'][0]
        if (set(change)!={'address','mode','type','name','provider_name','change'} or change['address']!=ADDRESS or change['mode']!='managed'
                or change['type']!=RESOURCE or change['name']!='selected' or change['provider_name']!=SOURCE):_fail('plan_output_change_scope')
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
        expected_resource={'address':ADDRESS,'mode':'managed','type':RESOURCE,'name':'selected','provider_config_key':'microsoft365',
            'expressions':{key:{'constant_value':value} for key,value in desired.items()},'schema_version':0}
        if not _same(entries[0],expected_resource):_fail('plan_output_configuration_changed')
        expected_provider={'microsoft365':{'name':'microsoft365','full_name':SOURCE,'version_constraint':'1.0.0',
            'expressions':{key:{'constant_value':value} for key,value in source['provider']['microsoft365'].items()}}}
        if not _same(configuration['provider_config'],expected_provider):_fail('plan_output_provider_configuration_changed')
        checks=[{'address':{'kind':'var','name':'stage','to_display':'var.stage'},'status':'pass','instances':[{'address':{'to_display':'var.stage'},'status':'pass'}]}]
        if not _same(plan['checks'],checks):_fail('plan_output_checks_unestablished')
    except (KeyError,TypeError,IndexError,AttributeError):_fail('plan_output_shape_unsupported')
    return {'schema_version':'native-noop-content-proof/1','object_id':object_id,'resource_address':ADDRESS,
        'state_sha256':state_sha256,'source_sha256':source_sha256,'effective_inputs_sha256':effective_inputs_sha256,
        'full_values_sha256':digest(attributes),'plan_json_sha256':hashlib.sha256(plan_raw).hexdigest(),
        'before_after_planned_prior_values_equal_state':True,'source_configuration_equal':True,
        'receiving_state_authentication_established':False,'execution_authorized':False}

