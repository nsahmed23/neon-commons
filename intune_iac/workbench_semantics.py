"""Versioned, lossless comparison for a bounded Settings Catalog view adapter.

Normalization is used only in comparisons; source/raw values and order remain
unchanged. Unsupported shapes or duplicate identities yield unknown, never an
invented equality. This does not widen the provider's execution support.
"""
from __future__ import annotations
import copy
from uuid import UUID
from .io import AppError, canonical, digest, parse_json

VERSION = 'workbench-field-semantics/1'
FIELDS = frozenset({'name','description','platforms','technologies','role_scope_tag_ids','settings','assignments'})
NS = '#microsoft.graph.deviceManagementConfiguration'


def contract():
    return {'schema_version':VERSION,'profile':'windows_settings_catalog_comparison',
        'fields':{'name':'typed scalar','description':'typed scalar; null distinct from absent and empty',
          'platforms':'typed scalar','technologies':'set of unique strings','role_scope_tag_ids':'set of unique strings',
          'assignments':'set of unique exact typed target tuples; includes/exclusions/filter modes are significant',
          'settings.settings':'keyed collection by service setting id; IDs and definition IDs retained',
          'setting.children':'keyed collection by settingDefinitionId; duplicates rejected',
          'setting.simpleSettingCollectionValue':'ordered sequence; order is significant'},
        'unknown_fields':'raw retained; comparison unknown','duplicate_handling':'reject duplicate set members/key identities; retain repeated ordered-sequence elements and all raw input',
        'raw_order_preserved':True,'execution_authorized':False}


def _uuid(value):
    try:return type(value) is str and str(UUID(value))==value
    except (ValueError,TypeError,AttributeError):return False


def analyze(body):
    try:
        if len(canonical(body))>2*1024*1024: raise ValueError()
        raw=parse_json(canonical(body))
    except (AppError,ValueError,TypeError,RecursionError):
        raise AppError('workbench_semantics_bound','Policy comparison exceeds the supported JSON bound.') from None
    blockers=[]
    def fail(pointer,code):blockers.append({'path':pointer,'code':code})
    def exact(obj,required,optional,pointer):
        if type(obj) is not dict:fail(pointer,'object_required');return False
        if not required<=set(obj) or set(obj)-required-optional:fail(pointer,'unsupported_or_missing_fields');return False
        return True
    def unique(values,pointer):
        if type(values) is not list or len(values)>1000:fail(pointer,'bounded_list_required');return None
        keys=[digest(v) for v in values]
        if len(set(keys))!=len(keys):fail(pointer,'duplicate_entry')
        return values
    def value(obj,pointer):
        if not exact(obj,{'@odata.type','value'},{'settingValueTemplateReference'},pointer):return obj
        kind=obj['@odata.type'];v=obj['value']
        types={NS+'StringSettingValue':str,NS+'IntegerSettingValue':int,NS+'BooleanSettingValue':bool}
        if type(kind) is not str or kind not in types or type(v) is not types.get(kind):fail(pointer,'unsupported_or_wrong_value_type')
        ref=obj.get('settingValueTemplateReference')
        if ref is not None:fail(pointer,'template_reference_unqualified')
        return copy.deepcopy(obj)
    def setting(obj,pointer):
        if type(obj) is not dict:fail(pointer,'setting_object_required');return obj
        kind=obj.get('@odata.type');kinds={NS+'ChoiceSettingInstance':'choiceSettingValue',NS+'SimpleSettingInstance':'simpleSettingValue',NS+'SimpleSettingCollectionInstance':'simpleSettingCollectionValue'}
        field=kinds.get(kind) if type(kind) is str else None
        if field is None:fail(pointer,'unsupported_setting_type');return obj
        if not exact(obj,{'@odata.type','settingDefinitionId',field},{'settingInstanceTemplateReference'},pointer):return obj
        if type(obj['settingDefinitionId']) is not str or not obj['settingDefinitionId']:fail(pointer,'definition_identity_invalid')
        if obj.get('settingInstanceTemplateReference') is not None:fail(pointer,'template_reference_unqualified')
        result=copy.deepcopy(obj)
        if field=='choiceSettingValue':
            v=obj[field]
            if not exact(v,{'@odata.type','value','children'},{'settingValueTemplateReference'},pointer+'/'+field):return result
            if v['@odata.type']!=NS+'ChoiceSettingValue' or type(v['value']) is not str:fail(pointer,'choice_type_invalid')
            if v.get('settingValueTemplateReference') is not None:fail(pointer,'template_reference_unqualified')
            children=unique(v['children'],pointer+'/children')
            if children is not None:
                ids=[c.get('settingDefinitionId') if type(c) is dict else None for c in children]
                if len(set(x for x in ids if type(x) is str))!=len(ids):fail(pointer,'duplicate_or_missing_child_identity')
                normalized=[setting(c,pointer+'/children/'+str(i)) for i,c in enumerate(children)]
                result[field]['children']=sorted(normalized,key=lambda c:canonical(c))
        elif field=='simpleSettingValue':result[field]=value(obj[field],pointer+'/'+field)
        else:
            values=obj[field]
            if type(values) is not list or len(values)>1000:fail(pointer+'/'+field,'bounded_sequence_required')
            else:result[field]=[value(v,pointer+'/'+field+'/'+str(i)) for i,v in enumerate(values)]
        return result
    normalized=copy.deepcopy(raw)
    if not exact(raw,FIELDS,set(),''):return {'schema_version':VERSION,'raw':raw,'blockers':blockers,'status':'unsupported','normalized':None}
    if type(raw['name']) is not str or not raw['name'] or len(raw['name'])>512:fail('/name','invalid_name')
    if raw['description'] is not None and type(raw['description']) is not str:fail('/description','invalid_description')
    if raw['platforms']!='windows10':fail('/platforms','unsupported_platform')
    for field in ('technologies','role_scope_tag_ids'):
        values=unique(raw[field],'/'+field)
        if values is not None:
            if any(type(x) is not str or not x for x in values):fail('/'+field,'string_set_required')
            normalized[field]=sorted(values,key=canonical)
    if type(raw['technologies']) is list and set(x for x in raw['technologies'] if type(x) is str)!={'mdm'}:fail('/technologies','unsupported_technology')
    assignments=unique(raw['assignments'],'/assignments')
    if assignments is not None:
        for i,row in enumerate(assignments):
            p='/assignments/'+str(i)
            if type(row) is not dict:fail(p,'target_required');continue
            required={'type','filter_type'};kind=row.get('type');mode=row.get('filter_type')
            if kind in ('groupAssignmentTarget','exclusionGroupAssignmentTarget'):
                required.add('group_id')
                if not _uuid(row.get('group_id')):fail(p,'group_identity_invalid')
            elif kind not in ('allDevicesAssignmentTarget','allLicensedUsersAssignmentTarget'):fail(p,'unsupported_target')
            if mode in ('include','exclude'):
                required.add('filter_id')
                if not _uuid(row.get('filter_id')):fail(p,'filter_identity_invalid')
            elif mode!='none':fail(p,'filter_mode_invalid')
            if kind=='exclusionGroupAssignmentTarget' and mode!='none':fail(p,'exclusion_filter_unsupported')
            exact(row,required,set(),p)
        normalized['assignments']=sorted(copy.deepcopy(assignments),key=canonical)
    settings=raw['settings']
    if exact(settings,{'settings'},set(),'/settings'):
        records=unique(settings['settings'],'/settings/settings')
        if records is not None:
            ids=[];rows=[]
            for i,row in enumerate(records):
                p='/settings/settings/'+str(i)
                if not exact(row,{'id','settingInstance'},set(),p):continue
                if type(row['id']) is not str or not row['id']:fail(p,'setting_identity_invalid')
                ids.append(row['id']);rows.append({'id':row['id'],'settingInstance':setting(row['settingInstance'],p+'/settingInstance')})
            if len(set(str(x) for x in ids))!=len(ids):fail('/settings/settings','duplicate_setting_identity')
            normalized['settings']['settings']=sorted(rows,key=canonical)
    return {'schema_version':VERSION,'raw':raw,'blockers':blockers,'status':'supported' if not blockers else 'unsupported',
            'normalized':normalized if not blockers else None}


def compare(left,right):
    a,b=analyze(left),analyze(right)
    result={'semantics_version':VERSION,'status':'unknown','changed_fields':[],'left':a,'right':b,
            'raw_changed':canonical(left)!=canonical(right),'execution_authorized':False}
    if a['blockers'] or b['blockers']:return result
    result['changed_fields']=[key for key in sorted(FIELDS) if canonical(a['normalized'][key])!=canonical(b['normalized'][key])]
    result['status']='different' if result['changed_fields'] else 'equal'
    return result
