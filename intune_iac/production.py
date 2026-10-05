"""Versioned, bounded capture-to-candidate projection. Never emits active IaC."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from urllib.parse import urlsplit
from uuid import UUID

from .io import AppError, digest

EXPORTER = {'id':'intune-iac-settings-catalog-graph','version':'1.0.0'}
ROOT = 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'
ODATA = '#microsoft.graph.'
DEFINITION = 'device_vendor_msft_policy_config_privacy_letappsaccesslocation'
RESOURCE = 'microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json'
MAX_SOURCE_NODES = 10000


def accepts(source):
    return source.get('synthetic') is False and source.get('exporter') == EXPORTER


def _source_budget(source):
    # Iterators bound traversal memory by depth, even for very wide arrays.
    pending = [iter((source,))]
    count = 0
    while pending:
        try:
            value = next(pending[-1])
        except StopIteration:
            pending.pop()
            continue
        count += 1
        if count > MAX_SOURCE_NODES:
            raise AppError('capture_node_limit', 'Production capture exceeds the 10,000 JSON-node mapping budget. Keep the complete capture intact; larger inventories require a qualified batching or streaming adapter.')
        if isinstance(value, dict):
            pending.append(iter(value.values()))
        elif isinstance(value, list):
            pending.append(iter(value))


def _ref(pointer):
    return hashlib.sha256(pointer.encode()).hexdigest()


def _text(value, maximum=2048):
    return isinstance(value,str) and len(value)<=maximum and all(ord(c)>=32 and not 127<=ord(c)<160 for c in value)


def _uuid(value):
    try:
        return isinstance(value,str) and bool(re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',value)) and bool(UUID(value).int)
    except ValueError:
        return False


def _type(record, name):
    # Optional base annotations are inferred from the selected collection route.
    return '@odata.type' not in record or record['@odata.type']==ODATA+name


def _policy(record):
    allowed={'@odata.type','id','name','description','platforms','technologies','roleScopeTagIds',
             'createdDateTime','lastModifiedDateTime','settingCount','isAssigned','templateReference',
             'creationSource','priorityMetaData','disableEntraGroupPolicyAssignment'}
    if not isinstance(record,dict) or set(record)-allowed or not _type(record,'deviceManagementConfigurationPolicy'):
        return False
    if not _uuid(record.get('id')) or not _text(record.get('name'),512) or not record['name']:
        return False
    if record.get('description') is not None and not _text(record['description'],1500): return False
    if record.get('platforms')!='windows10' or record.get('technologies')!='mdm': return False
    tags=record.get('roleScopeTagIds')
    if not isinstance(tags,list) or len(tags)!=len(set(x for x in tags if isinstance(x,str))) or any(not _text(x,128) or not x for x in tags): return False
    for k in ('createdDateTime','lastModifiedDateTime','creationSource'):
        if k in record and record[k] is not None and not _text(record[k],512): return False
    if 'settingCount' in record and (type(record['settingCount']) is not int or record['settingCount']<0):return False
    for k in ('isAssigned','disableEntraGroupPolicyAssignment'):
        if k in record and type(record[k]) is not bool:return False
    template=record.get('templateReference')
    if template is not None:
        if not isinstance(template,dict) or set(template)-{'@odata.type','templateId','templateFamily','templateDisplayName','templateDisplayVersion'}:return False
        if template.get('@odata.type',ODATA+'deviceManagementConfigurationPolicyTemplateReference') not in (ODATA+'deviceManagementConfigurationPolicyTemplateReference','microsoft.graph.deviceManagementConfigurationPolicyTemplateReference'):return False
        if template.get('templateId')!='' or template.get('templateFamily')!='none' or template.get('templateDisplayName') is not None or template.get('templateDisplayVersion') is not None:return False
    priority=record.get('priorityMetaData')
    if priority is not None:
        if not isinstance(priority,dict) or set(priority)-{'@odata.type','priority'} or type(priority.get('priority')) is not int:return False
        if priority.get('@odata.type',ODATA+'deviceManagementPriorityMetaData') not in (ODATA+'deviceManagementPriorityMetaData','microsoft.graph.deviceManagementPriorityMetaData'):return False
    return True


def _setting(record):
    if not isinstance(record,dict) or set(record)-{'@odata.type','id','settingInstance'} or not _type(record,'deviceManagementConfigurationSetting'):return False
    if not _text(record.get('id'),512) or not record['id']:return False
    instance=record.get('settingInstance')
    if not isinstance(instance,dict) or set(instance)-{'@odata.type','settingDefinitionId','settingInstanceTemplateReference','choiceSettingValue'}:return False
    if instance.get('@odata.type')!=ODATA+'deviceManagementConfigurationChoiceSettingInstance' or instance.get('settingDefinitionId')!=DEFINITION or instance.get('settingInstanceTemplateReference') is not None:return False
    value=instance.get('choiceSettingValue')
    return (isinstance(value,dict) and not set(value)-{'@odata.type','value','children','settingValueTemplateReference'}
            and value.get('@odata.type')==ODATA+'deviceManagementConfigurationChoiceSettingValue'
            and value.get('value')==DEFINITION+'_2' and value.get('children')==[]
            and value.get('settingValueTemplateReference') is None)


def _assignment(record):
    if not isinstance(record,dict) or set(record)-{'@odata.type','id','target','source','sourceId'} or not _type(record,'deviceManagementConfigurationPolicyAssignment'):return False
    if not _text(record.get('id'),512) or not record['id']:return False
    if record.get('source')!='direct' or record.get('sourceId') not in (None,''):return False
    target=record.get('target')
    if not isinstance(target,dict) or set(target)-{'@odata.type','groupId','deviceAndAppManagementAssignmentFilterType','deviceAndAppManagementAssignmentFilterId'}:return False
    if target.get('@odata.type') not in (ODATA+'groupAssignmentTarget',ODATA+'exclusionGroupAssignmentTarget') or not _uuid(target.get('groupId')):return False
    mode=target.get('deviceAndAppManagementAssignmentFilterType'); fid=target.get('deviceAndAppManagementAssignmentFilterId')
    if mode not in ('none','include','exclude'):return False
    if target['@odata.type']==ODATA+'exclusionGroupAssignmentTarget' and mode!='none':return False
    return fid is None if mode=='none' else _uuid(fid)


def _trusted(url, root):
    if not isinstance(url,str) or any(ord(c)<32 or ord(c)>=127 for c in url):return False
    try:p=urlsplit(url)
    except ValueError:return False
    return p.scheme=='https' and p.netloc=='graph.microsoft.com' and p.path==urlsplit(root).path and not p.fragment and not p.username and not p.password


def _accounting(source, rows, policy_id, policy, settings, assignments, candidate):
    """Account for every node with a versioned rule and exact output locations.

    Pointer names always remain opaque. A retained source hash is not a mapping:
    mapped nodes name their observation/configuration destinations explicitly.
    """
    records = {}
    restricted_roots = set()
    for ci, collection in enumerate(source['collections']):
        for pi, page in enumerate(collection['pages']):
            bp = f'/collections/{ci}/pages/{pi}/body'
            body = page['body']
            if set(body) - {'value', '@odata.context', '@odata.count', '@odata.nextLink'} or not isinstance(body.get('value'), list):
                restricted_roots.add(bp)
            for ri, _ in enumerate(body.get('value', []) if isinstance(body.get('value'), list) else []):
                records[f'{bp}/value/{ri}'] = ('invalid', ri, False)
    for kind, observed in [('policies', [policy]), ('settings', settings), ('assignments', assignments)]:
        for index, (value, pointer) in enumerate(rows[kind]):
            if kind == 'policies':
                selected = value.get('id') == policy_id
                records[pointer] = ('policy' if selected else 'unselected', 0, bool(policy))
            else:
                records[pointer] = (kind[:-1], index, bool(observed[index]))
    desired_policy = {'name':'name', 'description':'description', 'platforms':'platforms',
                      'technologies':'technologies/0', 'roleScopeTagIds':'role_scope_tag_ids'}
    assignment_fields = {'@odata.type':'type', 'groupId':'group_id',
                         'deviceAndAppManagementAssignmentFilterType':'filter_type',
                         'deviceAndAppManagementAssignmentFilterId':'filter_id'}
    result = []
    def walk(value, path, record=None, suffix=''):
        if path in records:
            record = records[path]; suffix = ''
        disposition, rule, destinations, loss = 'service_owned', 'capture.provenance', [], False
        if path == '/tenant_id':
            disposition, rule, destinations = 'identity', 'capture.tenant', ['/tenant_id', '/key']
        elif path == '/references' or path.startswith('/references/'):
            disposition, rule = 'separately_managed', 'capture.unverified_reference'
        elif path == '/ownership' or path.startswith('/ownership/'):
            rule = 'capture.unverified_ownership'
        page_root = '/'.join(path.split('/')[:6])
        if page_root in restricted_roots:
            disposition, rule, loss = 'unsupported', 'retention.unsupported_page', True
        elif record:
            kind, index, accepted = record
            if kind == 'unselected':
                rule = 'capture.unselected_object'
            elif not accepted:
                disposition, rule, loss = 'unsupported', 'retention.unsupported_record', True
            else:
                base = '/observed/policy' if kind == 'policy' else f'/observed/{kind}s/{index}'
                destinations = [base + suffix]
                rule = kind + '.observation'
                field = suffix.split('/')[1] if suffix else ''
                if kind == 'policy':
                    if field == 'id':
                        disposition, rule = 'identity', 'policy.identity'
                        destinations.extend(['/object_id', '/key'])
                    elif field in desired_policy:
                        disposition, rule = 'desired', 'policy.configuration'
                        if candidate:
                            destinations.append('/configuration/' + desired_policy[field] + suffix[len(field)+1:])
                    elif field == 'priorityMetaData' and policy.get(field) is not None or field == 'disableEntraGroupPolicyAssignment' and policy.get(field) is True:
                        disposition, rule, loss = 'unsupported', 'policy.unmapped_behavior', True
                elif kind == 'setting':
                    if field == 'id':
                        disposition, rule = 'identity', 'setting.identity'
                        if value != str(index): loss = True
                        if candidate: destinations.append(f'/configuration/settings/settings/{index}' + suffix)
                    elif field == 'settingInstance':
                        disposition, rule = 'desired', 'setting.configuration'
                        if candidate: destinations.append(f'/configuration/settings/settings/{index}' + suffix)
                elif kind == 'assignment' and field == 'target':
                    disposition, rule = 'relationship', 'assignment.target'
                    if candidate:
                        remainder = suffix[len('/target'):]
                        if not remainder:
                            destinations.append(f'/configuration/assignments/{index}')
                        elif remainder[1:] in assignment_fields:
                            mapped = assignment_fields[remainder[1:]]
                            if mapped != 'filter_id' or assignments[index]['target']['deviceAndAppManagementAssignmentFilterType'] != 'none':
                                destinations.append(f'/configuration/assignments/{index}/' + mapped)
                            else:
                                rule = 'assignment.inactive_filter'
        # A public digest of a restricted scalar is a dictionary oracle. Only
        # already-visible mapped scalars get a value digest; containers never do.
        visible_scalar = bool(destinations) and not loss and not isinstance(value, (dict, list))
        result.append({'source_node_ref':_ref(path), 'source_value_sha256':digest(value) if visible_scalar else None,
                       'classification':'mapped' if destinations else 'restricted_source',
                       'disposition':disposition, 'rule_id':rule, 'rule_version':'1.1.0',
                       'destination_pointers':destinations, 'loss_blocking':loss,
                       'retention_locator':'restricted-original-source'})
        if isinstance(value, dict):
            for key in sorted(value):
                segment = '/' + key.replace('~','~0').replace('/','~1')
                walk(value[key], path + segment, record, suffix + segment)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                segment = '/' + str(index)
                walk(child, path + segment, record, suffix + segment)
    walk(source, '')
    return result

def validate_context(source,context):
    required={'schema_version':'1.0.0','tenant_id':source['tenant_id'],'cloud':'public',
              'authorization':'emit_only','source_is_synthetic':False}
    pins={'provider_source':'deploymenttheory/microsoft365','provider_version':'1.0.0',
          'engine':'tofu','engine_version':'1.10.0','atmos_version':'1.199.0'}
    allowed=set(required)|set(pins)|{'selected_policy_id','component','stack','implementation',
             'tenant_assurance','target_assurance','repository_source_fingerprint',
             'repository_revision','backend_owner','state_key'}
    if set(context)-allowed or any(type(context.get(k)) is not type(v) or context.get(k)!=v for k,v in required.items()) or any(type(context[k]) is not type(v) or context[k]!=v for k,v in pins.items() if k in context) or not _uuid(context.get('selected_policy_id')) or not _uuid(source.get('tenant_id')) or source.get('cloud')!='public':
        raise AppError('invalid_context','Production candidates require the pinned public-cloud, emit-only context.')
    for key in ('component','stack','implementation'):
        if key=='implementation' and key not in context:continue
        if not isinstance(context.get(key),str) or len(context[key])>256 or not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*',context[key]):
            raise AppError('invalid_context','Component and stack must be safe relative target labels.')
    for key in ('repository_source_fingerprint','repository_revision'):
        size=64 if key=='repository_source_fingerprint' else 40
        if key in context and (not isinstance(context[key],str) or not re.fullmatch('[0-9a-f]{'+str(size)+'}',context[key])):
            raise AppError('invalid_context','Repository fingerprints must have a valid encoding.')
    for key in ('tenant_assurance','target_assurance','backend_owner','state_key'):
        if key in context and not _text(context[key],512):
            raise AppError('invalid_context','Target context metadata must be bounded literal text.')


def normalize(source,context):
    if not accepts(source):raise AppError('invalid_capture','The production mapping requires the exact plugin capture exporter.')
    _source_budget(source)
    validate_context(source,context)
    policy_id=context['selected_policy_id']; blockers=[]; mapping_blocked=False
    def block(code,path,mapping=True):
        nonlocal mapping_blocked
        item={'code':code,'path_ref':_ref(path)}
        if item not in blockers:blockers.append(item)
        mapping_blocked = mapping_blocked or mapping
    coverage=[]; rows={}
    for kind in ('policies','settings','assignments'):
        owner=None if kind=='policies' else policy_id
        matches=[(i,c) for i,c in enumerate(source['collections']) if c['kind']==kind and c['owner_id']==owner]
        root=ROOT if owner is None else ROOT+'/'+owner+'/'+kind
        values=[]; complete=False
        if len(matches)==1:
            ci,c=matches[0]; complete=c['coverage']=='complete' and c['reason'] is None and bool(c['pages'])
            expected=root; seen=set(); ids=set(); declared_counts=[]
            for pi,p in enumerate(c['pages']):
                path=f'/collections/{ci}/pages/{pi}/body'
                url=p['request_url']; body=p['body']
                page_ok=(url==expected and url not in seen and _trusted(url,root) and p['method']=='GET' and p['http_status']==200 and isinstance(body.get('value'),list) and not set(body)-{'value','@odata.context','@odata.count','@odata.nextLink'})
                seen.add(url)
                if '@odata.context' in body and not _text(body['@odata.context']):page_ok=False
                if '@odata.count' in body and (type(body['@odata.count']) is not int or body['@odata.count']<0):page_ok=False
                if page_ok:
                    if '@odata.count' in body:declared_counts.append(body['@odata.count'])
                    for ri,record in enumerate(body['value']):
                        rp=path+'/value/'+str(ri)
                        if not isinstance(record,dict):complete=False;block('invalid_source_record',rp);continue
                        rid=record.get('id')
                        if kind!='settings' and _uuid(rid):rid=str(UUID(rid))
                        if not isinstance(rid,str) or rid in ids:complete=False;block('duplicate_or_missing_source_identity',rp)
                        if isinstance(rid,str):ids.add(rid)
                        values.append((record,rp))
                else:complete=False;block('invalid_collection_page',path)
                if '@odata.nextLink' in body:
                    expected=body['@odata.nextLink']
                    if not isinstance(expected,str) or not expected or not _trusted(expected,root):complete=False
                else:expected=None
            complete=complete and expected is None
            if any(count!=len(values) for count in declared_counts):
                complete=False;block('collection_count_mismatch','/collections/'+kind)
        if not complete:block('collection_incomplete','/collections/'+kind)
        rows[kind]=values;coverage.append({'kind':kind,'complete':complete})
    if len(source['collections'])!=3:block('unexpected_collection_set','/collections')
    selected=[(p,path) for p,path in rows['policies'] if p.get('id')==policy_id]
    policy={}
    if len(selected)!=1:block('selected_policy_missing_or_duplicate','/collections/policies')
    else:
        p,path=selected[0]
        if _policy(p):
            policy=copy.deepcopy(p)
            if p.get('priorityMetaData') is not None or p.get('disableEntraGroupPolicyAssignment') is True:block('policy_behavior_not_mapped',path)
        else:block('unsupported_policy_shape',path)
    settings=[]; setting_map=[]
    for i,(record,path) in enumerate(rows['settings']):
        if not _setting(record):settings.append({});block('unsupported_setting_shape',path);continue
        settings.append(copy.deepcopy(record)); accepted_id=record['id']==str(i)
        setting_map.append({'source_id':record['id'],'configuration_id':record['id'] if accepted_id else None,'source_ordinal':i})
        if not accepted_id:block('unsupported_setting_configuration_id',path+'/id')
    if not settings:block('settings_missing','/collections/settings')
    if len(settings)!=1:block('unsupported_setting_cardinality','/collections/settings')
    if policy and 'settingCount' in policy and policy['settingCount']!=len(settings):block('setting_count_mismatch','/collections/policies')
    assignments=[]; desired_assignments=[]; target_keys=set(); references=set()
    for record,path in rows['assignments']:
        if 'source' not in record:block('assignment_source_unobserved',path)
        elif record.get('source')!='direct':block('assignment_source_not_direct',path)
        if not _assignment(record):assignments.append({});block('unsupported_assignment_shape',path);continue
        assignments.append(copy.deepcopy(record)); t=record['target']; mode=t['deviceAndAppManagementAssignmentFilterType']
        projected={'type':t['@odata.type'].removeprefix(ODATA),'group_id':t['groupId'],'filter_type':mode}
        if mode!='none':projected['filter_id']=t['deviceAndAppManagementAssignmentFilterId'];references.add(('filter',projected['filter_id']))
        references.add(('group',projected['group_id']))
        identity=dict(projected,group_id=str(UUID(projected['group_id'])))
        if 'filter_id' in identity:identity['filter_id']=str(UUID(identity['filter_id']))
        key=digest(identity)
        if key in target_keys:block('duplicate_assignment_target',path)
        target_keys.add(key);desired_assignments.append(projected)
    if 'isAssigned' in policy and policy['isAssigned']!=bool(rows['assignments']):
        block('assignment_flag_mismatch','/collections/policies')
    for tag in policy.get('roleScopeTagIds',[]):references.add(('scope_tag',tag))
    candidate=not mapping_blocked
    configuration=None
    if candidate:
        configuration={'name':policy['name'],'description':policy.get('description'),'platforms':policy['platforms'],
                       'technologies':[policy['technologies']],'role_scope_tag_ids':policy['roleScopeTagIds'],
                       'settings':{'settings':[{'id':s['id'],'settingInstance':copy.deepcopy(s['settingInstance'])} for s in settings]},
                       'assignments':desired_assignments}
    # The capture contract contains claims, not authenticated reference receipts
    # or repository ownership decisions. These remain separate qualification gates.
    if references:block('reference_evidence_unverified','/references',False)
    block('ownership_unknown','/ownership',False)
    block('provider_qualification_required','',False)
    return {'schema_version':'production-1.2.0','source_mode':'plugin_graph_capture','object_id':policy_id,'tenant_id':source['tenant_id'],
            'key':'p_'+UUID(source['tenant_id']).hex+'_'+UUID(policy_id).hex,'source_canonical_sha256':digest(source),
            'observed':{'policy':policy,'settings':settings,'assignments':assignments},'configuration':configuration,
            'setting_id_map':setting_map,'coverage':coverage,'candidate_mapping_complete':candidate,
            'offline_mapping_complete':False,'blockers':blockers,
            'references':[{'kind':kind,'id':rid,'coverage':'unknown','ownership':'unverified'} for kind,rid in sorted(references)],
            'ownership':{'status':'unknown'},
            'request_projection':{'status':'not_constructed','provider_constructor_setting_id_behavior':'configuration_ids_not_copied','wire_serialization_qualified':False},
            'state_expectations':{'status':'unqualified','source_setting_ids':[s['id'] for s in settings if s],'roundtrip_verified':False},
            'field_accounting':_accounting(source,rows,policy_id,policy,settings,assignments,candidate),'execution_authorized':False,'provider_qualified':False,'live_qualification':'not_run'}


def _render(value):
    return json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n'


def generate_files(normalized,context):
    n=normalized
    files={'README.md':'# Settings Catalog capture candidate\n\nBounded offline mapping of caller-asserted Graph capture. Provider validity, tenant authenticity, reference evidence and repository ownership remain unqualified. Candidate Terraform has an inactive .tf.txt suffix. No provider, import, plan or apply was run.\n',
           'review/normalized.json':_render(n),
           'BLOCKED.json':_render({'execution_allowed':False,'blockers':n['blockers']}),
           'commands/command-cards.json':_render({'schema_version':'1.0.0','cards':[]}),
           'adoption/setting-id-map.json':_render({'schema_version':'1.0.0','entries':n['setting_id_map']}),
           'adoption/target-receipt.json':_render({'schema_version':'1.0.0','context_canonical_sha256':digest(context),
               'component':context['component'],'stack':context['stack'],'implementation':context.get('implementation'),
               'repository_source_fingerprint':context.get('repository_source_fingerprint'),'execution_authorized':False})}
    if n['candidate_mapping_complete']:
        prefix='candidates/components/terraform/'+context['component']+'/'
        files[prefix+'configuration.json']=_render(n['configuration'])
        files[prefix+'settings.json']=_render(n['configuration']['settings'])
        files['candidates/target.json']=_render({'schema_version':'1.0.0','component':context['component'],'stack':context['stack'],'tenant_id':n['tenant_id'],'object_id':n['object_id'],'source_authenticity_verified':False,'provider_qualified':False,'execution_authorized':False})
        files[prefix+'main.tf.txt']='''# INACTIVE CANDIDATE: local projection only; provider validity is unqualified.
terraform {
  required_version = "= 1.10.0"
  required_providers {
    microsoft365 = { source = "deploymenttheory/microsoft365", version = "= 1.0.0" }
  }
}
locals {
  configuration = jsondecode(file("${path.module}/configuration.json"))
}
resource "microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json" "policy" {
  name = local.configuration.name
  description = local.configuration.description
  platforms = local.configuration.platforms
  technologies = local.configuration.technologies
  role_scope_tag_ids = local.configuration.role_scope_tag_ids
  settings = jsonencode(local.configuration.settings)
  assignments = local.configuration.assignments
  lifecycle {
    prevent_destroy = true
    precondition {
      condition = local.configuration.name == "" && local.configuration.name != ""
      error_message = "Inactive candidate requires independent provider and tenant qualification."
    }
  }
}
'''
    return files
