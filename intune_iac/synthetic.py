"""Seeded local estates and an authored semantic oracle, never cloud authority.

Truth is built from a domain model before capture serialization. The comparison
code imports neither the production normalizer nor reference normalization.
Simulation is deliberately labelled; its history is not an authenticated receipt.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

STAMP = '2026-09-30T12:00:00Z'
BASE = 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'
NS = '#microsoft.graph.'
DEFINITION = 'device_vendor_msft_policy_config_privacy_letappsaccesslocation'
CASES = ('baseline', 'reordered', 'malicious-label', 'denied', 'pagination-loop',
         'missing-page', 'unknown-setting', 'stale-state', 'approval-replay',
         'wrong-target', 'partial-failure', 'recovery', 'empty-assignments',
         'omitted-assignments', 'null-assignments', 'cross-origin-page', 'duplicate-page',
         'missing-initial-page', 'nested-unknown', 'wrong-cloud', 'wrong-principal',
         'wrong-backend', 'wrong-lineage', 'expired-approval', 'plan-substitution', 'lease-loss')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _uid(seed, kind, index=0):
    return str(uuid5(NAMESPACE_URL, f'intune-iac/synthetic/v1/{seed}/{kind}/{index}'))


def _collection(kind, owner, records, page_size=1):
    endpoint = BASE + (f'/{owner}/{kind}' if owner else '')
    pages = []
    chunks = [records[i:i + page_size] for i in range(0, len(records), page_size)] or [[]]
    for i, chunk in enumerate(chunks):
        body = {'value': copy.deepcopy(chunk)}
        if i + 1 < len(chunks):
            body['@odata.nextLink'] = endpoint + f'?$skiptoken=synthetic-{i + 1}'
        pages.append({'request_url': endpoint + (f'?$skiptoken=synthetic-{i}' if i else ''),
                      'method': 'GET', 'http_status': 200, 'captured_at': STAMP, 'body': body})
    return {'kind': kind, 'owner_id': owner, 'coverage': 'complete', 'reason': None, 'pages': pages}


def generate_estate(seed=42, policy_count=3, case='baseline'):
    """Return reproducible JSON data; bounded size, stable IDs, no I/O."""
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise ValueError('seed must be an integer from 0 to 2147483647')
    if type(policy_count) is not int or not 1 <= policy_count <= 8:
        raise ValueError('policy_count must be an integer from 1 to 8')
    if case not in CASES:
        raise ValueError('unknown synthetic case')
    tenant = _uid(seed, 'tenant')
    groups = [_uid(seed, 'group', i) for i in range(3)]
    filter_id = _uid(seed, 'filter')
    tags = ['0', str(seed % 997 + 1)]
    models = []
    for i in range(policy_count):
        label = f'Privacy pilot {seed % 13}'  # duplicate labels intentionally
        if case == 'malicious-label':
            label = '${file("/etc/passwd")} $(touch /tmp/never) `whoami` '
        setting = {'id': '0', 'settingInstance': {
            '@odata.type': NS + 'deviceManagementConfigurationChoiceSettingInstance',
            'settingDefinitionId': DEFINITION, 'settingInstanceTemplateReference': None,
            'choiceSettingValue': {'@odata.type': NS + 'deviceManagementConfigurationChoiceSettingValue',
                                  'settingValueTemplateReference': None,
                                  'value': DEFINITION + '_2', 'children': []}}}
        assignments = [
            {'type': 'groupAssignmentTarget', 'group_id': groups[0],
             'filter_type': 'include', 'filter_id': filter_id},
            {'type': 'groupAssignmentTarget', 'group_id': groups[1], 'filter_type': 'none'},
            {'type': 'exclusionGroupAssignmentTarget', 'group_id': groups[2], 'filter_type': 'none'}]
        models.append({'id': _uid(seed, 'policy', i), 'name': label,
                       'description': f'Seed {seed}; authored synthetic policy {i}.',
                       'platforms': 'windows10', 'technologies': ['mdm'],
                       'role_scope_tag_ids': list(tags), 'settings': {'settings': [setting]},
                       'assignments': assignments})
    policies, collections, contexts = [], [], []
    for i, model in enumerate(models):
        oid = model['id']
        policies.append({'@odata.type': NS + 'deviceManagementConfigurationPolicy',
                         'id': oid, 'name': model['name'], 'description': model['description'],
                         'platforms': 'windows10', 'technologies': 'mdm', 'roleScopeTagIds': tags[:],
                         'createdDateTime': STAMP, 'lastModifiedDateTime': STAMP,
                         'settingCount': 1, 'isAssigned': True,
                         'templateReference': {'templateId': '', 'templateFamily': 'none',
                                               'templateDisplayName': None, 'templateDisplayVersion': None}})
        settings = [{'@odata.type': NS + 'deviceManagementConfigurationSetting', **copy.deepcopy(s)}
                    for s in model['settings']['settings']]
        assignments = []
        for j, item in enumerate(model['assignments']):
            target = {'@odata.type': NS + item['type'], 'groupId': item['group_id'],
                      'deviceAndAppManagementAssignmentFilterType': item['filter_type'],
                      'deviceAndAppManagementAssignmentFilterId': item.get('filter_id')}
            assignments.append({'@odata.type': NS + 'deviceManagementConfigurationPolicyAssignment',
                                'id': _uid(seed, f'assignment-{i}', j), 'target': target})
        collections.extend([_collection('settings', oid, settings),
                            _collection('assignments', oid, assignments)])
        contexts.append({'schema_version': '1.0.0', 'tenant_id': tenant, 'cloud': 'public',
                         'engine': 'tofu', 'engine_version': '1.10.0', 'atmos_version': '1.199.0',
                         'provider_source': 'deploymenttheory/microsoft365', 'provider_version': '1.0.0',
                         'component': 'intune-reference', 'stack': 'reference-dev',
                         'repository_revision': hashlib.sha1(f'synthetic:{seed}'.encode()).hexdigest(),
                         'source_is_synthetic': True, 'authorization': 'emit_only',
                         'backend_owner': 'external', 'state_key': f'synthetic/{seed}/intune.tfstate',
                         'selected_policy_id': oid})
    references = [{'kind': kind, 'id': oid, 'ownership': 'external', 'coverage': 'complete',
                   'captured_at': STAMP} for kind, oid in
                  [('group', x) for x in groups] + [('filter', filter_id)] + [('scope_tag', x) for x in tags]]
    capture = {'schema_version': '1.0.0', 'synthetic': True, 'tenant_id': tenant, 'cloud': 'public',
               'captured_at': STAMP, 'exporter': {'id': 'appendix-b-graph-snapshot', 'version': '1.0.0'},
               'collections': [_collection('policies', None, policies), *collections],
               'references': references,
               'ownership': [{'object_id': p['id'], 'current_writer': None, 'adoption_intent': 'propose_only'}
                             for p in models]}
    state = {'lineage': _uid(seed, 'lineage'), 'serial': 1,
             'objects': {p['id']: copy.deepcopy(p) for p in models}}
    plan = {'simulation': True, 'tenant_id': tenant, 'repository_revision': contexts[0]['repository_revision'],
            'state_lineage': state['lineage'], 'state_serial': 1,
            'actions': [{'id': p['id'], 'actions': ['no-op']} for p in models]}
    target_context = {'cloud': 'public', 'principal': _uid(seed, 'principal'),
                      'backend': contexts[0]['state_key']}
    plan['target_context'] = copy.deepcopy(target_context)
    approval = {'simulation': True, 'id': _uid(seed, 'approval'), 'tenant_id': tenant,
                'plan_sha256': _hash(plan), 'consumed': False, 'expires_at_tick': 10}
    expected = 'ready'
    target = capture['collections'][2]
    if case == 'denied':
        target.update(coverage='access_denied', reason='Synthetic HTTP 403')
        target['pages'] = [{'request_url': BASE + '/' + models[0]['id'] + '/assignments',
                            'method': 'GET', 'http_status': 403, 'captured_at': STAMP,
                            'body': {'error': {'code': 'Forbidden', 'message': 'Synthetic denied'}}}]
        expected = 'blocked'
    elif case == 'pagination-loop':
        target['pages'][-1]['body']['@odata.nextLink'] = target['pages'][0]['request_url']
        expected = 'blocked'
    elif case == 'missing-page':
        target['pages'].pop()
        expected = 'blocked'
    elif case == 'unknown-setting':
        capture['collections'][1]['pages'][0]['body']['value'][0]['settingInstance']['settingDefinitionId'] = 'future_unknown_setting'
        expected = 'blocked'
    elif case == 'empty-assignments':
        models[0]['assignments'] = []
        state['objects'][models[0]['id']]['assignments'] = []
        policies[0]['isAssigned'] = False
        for page in capture['collections'][0]['pages']:
            for row in page['body']['value']:
                if row['id'] == models[0]['id']: row['isAssigned'] = False
        target['pages'] = _collection('assignments', models[0]['id'], [])['pages']
    elif case == 'omitted-assignments':
        capture['collections'].remove(target)
        expected = 'blocked'
    elif case == 'null-assignments':
        target['pages'][0]['body']['value'] = None
        expected = 'blocked'
    elif case == 'cross-origin-page':
        target['pages'][0]['body']['@odata.nextLink'] = 'https://example.invalid/steal'
        expected = 'blocked'
    elif case == 'duplicate-page':
        target['pages'].append(copy.deepcopy(target['pages'][0]))
        expected = 'blocked'
    elif case == 'missing-initial-page':
        target['pages'].pop(0)
        expected = 'blocked'
    elif case == 'nested-unknown':
        capture['collections'][1]['pages'][0]['body']['value'][0]['settingInstance']['choiceSettingValue']['future'] = {'nested': None}
        expected = 'blocked'
    elif case == 'wrong-cloud':
        target_context['cloud'] = 'china'
    elif case == 'wrong-principal':
        target_context['principal'] = _uid(seed, 'other-principal')
    elif case == 'wrong-backend':
        target_context['backend'] = 'other/state'
    elif case == 'wrong-lineage':
        state['lineage'] = _uid(seed, 'other-lineage')
    elif case == 'expired-approval':
        approval['expires_at_tick'] = 0
    elif case == 'plan-substitution':
        plan['actions'][0]['actions'] = ['delete']
    elif case == 'reordered':
        capture['collections'].reverse()
        capture['references'].reverse()
        for collection in capture['collections']:
            for page in collection['pages']:
                page['body']['value'].reverse()
        for p in models:
            p['assignments'].reverse()
    elif case == 'stale-state':
        state['serial'] = 2
    elif case == 'approval-replay':
        approval['consumed'] = True
    elif case == 'wrong-target':
        approval['tenant_id'] = _uid(seed, 'other-tenant')
    plan['source_sha256'] = _hash(capture)
    approval['plan_sha256'] = _hash(plan)
    return {'schema_version': 'intune-synthetic-estate/1.0', 'case_id': f'S{seed:010d}-{case}',
            'seed': seed, 'case': case, 'capture': capture, 'contexts': contexts,
            'truth': {'tenant_id': tenant, 'policies': models, 'expected_mapping': expected,
                      'groups': groups, 'filters': [filter_id], 'scope_tags': tags},
            'repository': {'revision': contexts[0]['repository_revision'], 'logical_stack': 'reference-dev',
                           'component': 'intune-reference', 'ownership': 'synthetic-only'},
            'state': state, 'plan': plan, 'approval': approval, 'target_context': target_context,
            'clock_tick': 1, 'lease_valid': case != 'lease-loss',
            'history': [{'event': 'captured', 'synthetic': True, 'policy_ids': [p['id'] for p in models]}]}


def _bag(items):
    return Counter(_json(item) for item in items)


def compare_normalized(estate, normalized, policy_id=None):
    """Independent semantic checks; permutations are accepted, multiplicity is not."""
    truth = estate['truth']
    oid = policy_id or estate['contexts'][0]['selected_policy_id']
    model = next(p for p in truth['policies'] if p['id'] == oid)
    issues = []
    if normalized.get('tenant_id') != truth['tenant_id']: issues.append('tenant_changed')
    if normalized.get('object_id') != oid: issues.append('identity_changed')
    if normalized.get('execution_authorized') is not False: issues.append('authority_invented')
    if normalized.get('live_qualification') != 'not_run': issues.append('live_qualification_invented')
    expected_ready = truth['expected_mapping'] == 'ready' or oid != truth['policies'][0]['id']
    if normalized.get('offline_mapping_complete') is not expected_ready: issues.append('mapping_readiness_changed')
    if not expected_ready:
        if not normalized.get('blockers'): issues.append('missing_blocker')
        if estate['case'] in ('denied', 'omitted-assignments'):
            if (normalized.get('desired') or {}).get('assignments') is not None:
                issues.append('unknown_assignments_became_known')
        return issues
    desired = normalized.get('desired') or {}
    for name in ('name', 'description', 'platforms'):
        if desired.get(name) != model[name]: issues.append(name + '_changed')
    for name in ('technologies', 'role_scope_tag_ids', 'assignments'):
        try:
            if _bag(desired.get(name, [])) != _bag(model[name]): issues.append(name + '_changed')
        except (ValueError, TypeError): issues.append(name + '_changed')
    if desired.get('settings') != model['settings']: issues.append('settings_changed')
    return sorted(set(issues))


def _state_and_action_issues(estate):
    # A no-op is a semantic assertion about the complete estate, not just a
    # matching serial. This oracle is independent of the transition simulator.
    issues = []
    policies = estate['truth']['policies']
    wanted = {p['id']: p for p in policies}
    objects = estate['state'].get('objects')
    if not isinstance(objects, dict) or set(objects) != set(wanted):
        issues.append('state_object_coverage_changed')
    if isinstance(objects, dict):
        for oid, expected in wanted.items():
            actual = objects.get(oid)
            if not isinstance(actual, dict) or set(actual) != set(expected):
                issues.append('state_object_shape_changed')
                continue
            for field in ('id', 'name', 'description', 'platforms', 'settings'):
                if _json(actual[field]) != _json(expected[field]):
                    issues.append('state_' + field + '_changed')
            for field in ('technologies', 'role_scope_tag_ids', 'assignments'):
                if not isinstance(actual[field], list) or _bag(actual[field]) != _bag(expected[field]):
                    issues.append('state_' + field + '_changed')
    actions = estate['plan'].get('actions')
    expected_actions = [{'id': oid, 'actions': ['no-op']} for oid in wanted]
    if not isinstance(actions, list) or _bag(actions) != _bag(expected_actions):
        issues.append('plan_action_coverage_changed')
    return sorted(set(issues))


def inspect_estate(estate):
    """Check graph referential integrity against independently authored truth."""
    issues = _state_and_action_issues(estate)
    truth = estate['truth']
    if estate['capture']['tenant_id'] != truth['tenant_id']: issues.append('capture_tenant_changed')
    ids = [p['id'] for p in truth['policies']]
    if len(set(ids)) != len(ids): issues.append('duplicate_identity')
    inventory = [r for c in estate['capture']['collections'] if c['kind'] == 'policies'
                 for page in c['pages'] for r in page['body'].get('value', [])]
    if _bag([p['id'] for p in inventory]) != _bag(ids): issues.append('inventory_identity_changed')
    for index, policy in enumerate(truth['policies']):
        observed = [p for p in inventory if p['id'] == policy['id']]
        if len(observed) == 1:
            row = observed[0]
            for field in ('name', 'description', 'platforms'):
                if row.get(field) != policy[field]: issues.append('capture_' + field + '_changed')
            if _bag(row.get('roleScopeTagIds', [])) != _bag(policy['role_scope_tag_ids']): issues.append('capture_tags_changed')
            if row.get('technologies') != ','.join(policy['technologies']): issues.append('capture_technologies_changed')
        children = [c for c in estate['capture']['collections'] if c['owner_id'] == policy['id']]
        # Intentionally damaged source is retained as a negative case; healthy
        # source relationships still receive independently authored checks.
        damaged = index == 0 and truth['expected_mapping'] == 'blocked'
        if not damaged:
            settings = [r for c in children if c['kind'] == 'settings' for page in c['pages'] for r in page['body'].get('value', [])]
            projected_settings = [{k: v for k, v in row.items() if k != '@odata.type'} for row in settings]
            if {'settings': projected_settings} != policy['settings']: issues.append('capture_settings_changed')
            targets = [r['target'] for c in children if c['kind'] == 'assignments' for page in c['pages'] for r in page['body'].get('value', [])]
            projected_targets = []
            for target in targets:
                row = {'type': target['@odata.type'].removeprefix(NS), 'group_id': target['groupId'],
                       'filter_type': target['deviceAndAppManagementAssignmentFilterType']}
                if target.get('deviceAndAppManagementAssignmentFilterId') is not None:
                    row['filter_id'] = target['deviceAndAppManagementAssignmentFilterId']
                projected_targets.append(row)
            if _bag(projected_targets) != _bag(policy['assignments']): issues.append('capture_assignments_changed')
        for assignment in policy['assignments']:
            if assignment['group_id'] not in truth['groups']: issues.append('unknown_group')
            if assignment.get('filter_id') and assignment['filter_id'] not in truth['filters']: issues.append('unknown_filter')
        if any(t not in truth['scope_tags'] for t in policy['role_scope_tag_ids']): issues.append('unknown_scope_tag')
    if estate['plan']['state_lineage'] != estate['state']['lineage']: issues.append('state_lineage_changed')
    if estate['plan'].get('source_sha256') != _hash(estate['capture']): issues.append('source_changed')
    return {'success': not issues, 'issues': sorted(set(issues)), 'synthetic': True,
            'execution_authorized': False, 'live_qualification': 'not_run',
            'scope': 'Synthetic authored-truth referential and source semantics; not capture authentication.'}


def simulate_local_transition(estate, fault=None):
    """Pure local protocol exercise; returns copies and no authenticated authority."""
    item = copy.deepcopy(estate)
    plan, state, approval = item['plan'], item['state'], item['approval']
    errors = _state_and_action_issues(item)
    if item['truth']['expected_mapping'] != 'ready': errors.append('capture_incomplete')
    if approval['consumed']: errors.append('approval_replay')
    if approval['expires_at_tick'] <= item['clock_tick']: errors.append('approval_expired')
    if not item['lease_valid']: errors.append('lease_lost')
    if plan['target_context'] != item['target_context']: errors.append('target_context_changed')
    if approval['plan_sha256'] != _hash(plan): errors.append('plan_changed')
    if plan.get('source_sha256') != _hash(item['capture']): errors.append('source_changed')
    if type(plan['state_serial']) is not int or type(state['serial']) is not int: errors.append('invalid_state_serial')
    if approval['tenant_id'] != plan['tenant_id'] or plan['tenant_id'] != item['truth']['tenant_id']: errors.append('wrong_target')
    if plan['repository_revision'] != item['repository']['revision']: errors.append('repository_changed')
    if (plan['state_lineage'], plan['state_serial']) != (state['lineage'], state['serial']): errors.append('stale_state')
    before = _hash(state)
    if errors:
        return {'simulation': True, 'status': 'blocked', 'issues': errors, 'effects': 0,
                'before_state_sha256': before, 'after_state_sha256': before, 'converged': False,
                'execution_authorized': False, 'estate': item}
    faults = ('before-policy', 'after-policy', 'before-assignment', 'after-assignment',
              'before-state', 'after-state', 'before-receipt', 'after-receipt')
    if fault not in (None, *faults):
        raise ValueError('unknown synthetic fault')
    approval['consumed'] = True
    if fault is not None or item['case'] == 'partial-failure':
        item['history'].append({'event': 'simulated-uncertain-outcome', 'fault': fault or 'after-policy', 'approval_id': approval['id']})
        return {'simulation': True, 'status': 'reconciliation_required', 'issues': ['simulated_partial_failure'],
                'effects': 0, 'before_state_sha256': before, 'after_state_sha256': _hash(state),
                'converged': False, 'execution_authorized': False, 'estate': item}
    item['history'].append({'event': 'simulated-no-op', 'plan_sha256': approval['plan_sha256'],
                            'approval_id': approval['id'], 'state_sha256': before})
    return {'simulation': True, 'status': 'converged', 'issues': [], 'effects': 0,
            'before_state_sha256': before, 'after_state_sha256': _hash(state), 'converged': True,
            'execution_authorized': False, 'estate': item}


def selected_capture(estate, policy_id=None):
    """Explicit per-policy adapter for the existing single-selection mapping."""
    oid = policy_id or estate['contexts'][0]['selected_policy_id']
    if oid not in [p['id'] for p in estate['truth']['policies']]:
        raise ValueError('unknown policy identity')
    capture = copy.deepcopy(estate['capture'])
    capture['collections'] = [c for c in capture['collections'] if c['owner_id'] in (None, oid)]
    capture['ownership'] = [o for o in capture['ownership'] if o['object_id'] == oid]
    return capture


def write_estate(output, seed=42, policy_count=3, case='baseline'):
    """Write a fresh local fixture directory; never overwrite an existing estate."""
    output = Path(output).absolute()
    if any(p.is_symlink() for p in [output, *output.parents]):
        raise ValueError('synthetic output must not traverse symlinks')
    estate = generate_estate(seed, policy_count, case)
    output.mkdir(parents=True, exist_ok=False)
    output.chmod(0o700)
    values = {'estate.json': estate, 'capture.json': selected_capture(estate),
              'capture-estate.json': estate['capture'],
              'context.json': estate['contexts'][0], 'contexts.json': estate['contexts'],
              'truth.json': estate['truth'], 'state.json': estate['state'],
              'plan.json': estate['plan'], 'approval.json': estate['approval'], 'history.json': estate['history']}
    for name, value in values.items():
        path = output / name
        path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n')
        path.chmod(0o600)
    return {'case_id': estate['case_id'], 'seed': seed, 'synthetic': True,
            'capture': str(output / 'capture.json'), 'context': str(output / 'context.json'),
            'estate': str(output / 'estate.json'), 'output': str(output), 'execution_authorized': False}
