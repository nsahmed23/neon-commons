"""Hand-written builders for simulator tests: documents only, never the evaluator under test.

Identifiers are derived from names so a test reads by name while every key stays a UUID. Display names are labels
and are deliberately allowed to repeat.
"""
import copy
from uuid import NAMESPACE_URL, uuid5

STAMP = '2026-10-15T12:00:00Z'
SHA = 'a' * 64
NS = '#microsoft.graph.'
DEF = 'device_vendor_msft_policy_config_privacy_letappsaccesslocation'
DEF_B = 'device_vendor_msft_policy_config_privacy_letappsaccesscamera'
DEF_CHILD = 'device_vendor_msft_policy_config_privacy_child'
DEF_COLLECTION = 'device_vendor_msft_policy_config_privacy_collection'


def uid(name):
    return str(uuid5(NAMESPACE_URL, 'intune-iac/sim-test/' + name))


def snapshot_doc(devices=(), groups=(), memberships=(), filters=(), policies=(), users=(), contexts=(), rings=(),
                 collections=None, snapshot_id='snap-1', realm_id='synthetic'):
    doc = {'schema': 'intune-sim-snapshot/1', 'snapshot_id': snapshot_id, 'realm_id': realm_id,
           'tenant_id': uid('tenant'), 'cloud': 'public', 'captured_start': STAMP, 'captured_end': STAMP,
           'observed_at': STAMP, 'source_ref': 'synthetic-test', 'source_sha256': SHA,
           'devices': [copy.deepcopy(d) for d in devices], 'users': [copy.deepcopy(u) for u in users],
           'user_device_contexts': [copy.deepcopy(c) for c in contexts],
           'groups': [copy.deepcopy(g) for g in groups], 'memberships': [copy.deepcopy(m) for m in memberships],
           'filters': [copy.deepcopy(f) for f in filters], 'policies': [copy.deepcopy(p) for p in policies],
           'rings': [copy.deepcopy(r) for r in rings]}
    if collections is not None:
        doc['collections'] = copy.deepcopy(collections)
    return doc


def device(name, sharing='personal', **properties):
    return {'id': uid('device/' + name), 'sharing': sharing, 'properties': properties}


def user(name):
    return {'id': uid('user/' + name)}


def context(user_name, device_name, relation='signed_in', certainty='known'):
    return {'user_id': uid('user/' + user_name), 'device_id': uid('device/' + device_name),
            'relation': relation, 'certainty': certainty}


def group(name, domain='device', complete=True, label=None):
    return {'id': uid('group/' + name), 'display_name': label or name, 'member_domain': domain,
            'type': 'static', 'membership_complete': complete}


def member(group_name, member_name, kind='device', certainty='known'):
    return {'group_id': uid('group/' + group_name), 'member_id': uid(kind + '/' + member_name),
            'member_kind': kind, 'certainty': certainty}


def filt(name, expression, platform='windows10'):
    return {'id': uid('filter/' + name), 'display_name': name, 'platform': platform, 'expression': expression}


def choice(definition=DEF, value=None, children=()):
    value = definition + '_2' if value is None else value
    return {'id': '0', 'settingInstance': {
        '@odata.type': NS + 'deviceManagementConfigurationChoiceSettingInstance',
        'settingDefinitionId': definition, 'settingInstanceTemplateReference': None,
        'choiceSettingValue': {'@odata.type': NS + 'deviceManagementConfigurationChoiceSettingValue',
                               'settingValueTemplateReference': None, 'value': value,
                               'children': [copy.deepcopy(c) for c in children]}}}


def child_choice(definition, value, children=()):
    return choice(definition, value, children)['settingInstance']


def collection(definition, values):
    return {'id': '0', 'settingInstance': {
        '@odata.type': NS + 'deviceManagementConfigurationSimpleSettingCollectionInstance',
        'settingDefinitionId': definition, 'settingInstanceTemplateReference': None,
        'simpleSettingCollectionValue': [
            {'@odata.type': NS + 'deviceManagementConfigurationStringSettingValue',
             'settingValueTemplateReference': None, 'value': v} for v in values]}}


def assign(kind, group_name=None, mode='none', filter_name=None):
    row = {'type': kind, 'filter_type': mode}
    if group_name is not None:
        row['group_id'] = uid('group/' + group_name)
    if mode != 'none':
        row['filter_id'] = uid('filter/' + filter_name)
    return row


def include(group_name, mode='none', filter_name=None):
    return assign('groupAssignmentTarget', group_name, mode, filter_name)


def exclude(group_name):
    return assign('exclusionGroupAssignmentTarget', group_name)


def all_devices(mode='none', filter_name=None):
    return assign('allDevicesAssignmentTarget', None, mode, filter_name)


def all_users():
    return assign('allLicensedUsersAssignmentTarget')


def policy(name, assignments, settings=None, label=None, description='', family='settings_catalog',
           platforms='windows10', source_path=None):
    body = {'name': label or name, 'description': description, 'platforms': platforms, 'technologies': ['mdm'],
            'role_scope_tag_ids': ['0'], 'settings': {'settings': settings if settings is not None else [choice()]},
            'assignments': [copy.deepcopy(a) for a in assignments]}
    record = {'id': uid('policy/' + name), 'family': family, 'body': body}
    if source_path:
        record['source_path'] = source_path
    return record


def revision_doc(policies=(), removed=(), revision_id='rev-1'):
    return {'schema': 'intune-sim-revision/1', 'revision_id': revision_id, 'source_ref': 'repo@' + revision_id,
            'policies': [copy.deepcopy(p) for p in policies], 'removed_policy_ids': [uid('policy/' + r) for r in removed]}
