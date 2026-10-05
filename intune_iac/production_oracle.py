"""Independent offline oracle for the plugin's production Graph capture.

This module imports neither the producer nor the reference projection.  Source
bytes, including unrecognized fields, are accounted for with opaque digests.
Passing these checks establishes only preservation within the bounded adapter;
it does not establish provider, service, ownership, or execution qualification.
"""
from __future__ import annotations

import hashlib
import json
import math
from itertools import repeat
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import UUID


_GRAPH = 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'
_NS = '#microsoft.graph.'
_DEFINITION = 'device_vendor_msft_policy_config_privacy_letappsaccesslocation'
_RESOURCE = 'microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json'


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _hash(value):
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _pointer_hash(pointer):
    return hashlib.sha256(pointer.encode('utf-8')).hexdigest()


def _decode(raw, *, capture=False):
    if not isinstance(raw, (str, bytes)) or len(raw) > 16 * 1024 * 1024:
        raise ValueError('input')
    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise ValueError('duplicate')
            result[name] = value
        return result
    def nonfinite(_):
        raise ValueError('number')
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    pending = [iter(((value, 0),))]
    nodes = 0
    while pending:
        try:
            node, depth = next(pending[-1])
        except StopIteration:
            pending.pop()
            continue
        nodes += 1
        if capture and nodes > 10000:
            raise ValueError('capture_node_limit')
        if depth > 64:
            raise ValueError('depth')
        if isinstance(node, float) and not math.isfinite(node):
            raise ValueError('number')
        if type(node) is int and abs(node) > 9007199254740991:
            raise ValueError('number')
        if isinstance(node, dict):
            pending.append(zip(node.values(), repeat(depth + 1)))
        elif isinstance(node, list):
            pending.append(zip(node, repeat(depth + 1)))
    _json_bytes(value)
    return value


def _walk(value):
    pending = [('', value)]
    while pending:
        pointer, node = pending.pop()
        yield pointer, node
        if isinstance(node, dict):
            children = [(pointer + '/' + k.replace('~', '~0').replace('/', '~1'), node[k])
                        for k in sorted(node)]
            pending.extend(reversed(children))
        elif isinstance(node, list):
            pending.extend(reversed([(pointer + '/' + str(i), v)
                                     for i, v in enumerate(node)]))


def _uuid(value):
    return (isinstance(value, str)
            and re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', value)
            and UUID(value).int != 0)


def _same(actual, expected):
    """JSON equality must distinguish bool from integer and absence from null."""
    return _json_bytes(actual) == _json_bytes(expected)


def _ordinary_text(value, *, empty=True, maximum=2048):
    return (isinstance(value, str) and len(value) <= maximum and (empty or bool(value))
            and not any(ord(c) < 32 or 127 <= ord(c) < 160 for c in value))


def _annotation(value, name):
    return '@odata.type' not in value or value['@odata.type'] == _NS + name


def _known_policy(value):
    fields = {'@odata.type', 'id', 'name', 'description', 'platforms', 'technologies',
              'roleScopeTagIds', 'createdDateTime', 'lastModifiedDateTime',
              'settingCount', 'isAssigned', 'templateReference', 'creationSource',
              'priorityMetaData', 'disableEntraGroupPolicyAssignment'}
    if not isinstance(value, dict) or set(value) - fields:
        return False
    if not _annotation(value, 'deviceManagementConfigurationPolicy'):
        return False
    if not _uuid(value.get('id')) or not _ordinary_text(value.get('name'), empty=False, maximum=512):
        return False
    if value.get('description') is not None and not _ordinary_text(value.get('description'), maximum=1500):
        return False
    if value.get('platforms') != 'windows10' or value.get('technologies') != 'mdm':
        return False
    tags = value.get('roleScopeTagIds')
    if not isinstance(tags, list) or any(not _ordinary_text(tag, empty=False, maximum=128) for tag in tags):
        return False
    if len(set(tags)) != len(tags):
        return False
    for name in ('createdDateTime', 'lastModifiedDateTime', 'creationSource'):
        if value.get(name) is not None and not _ordinary_text(value[name], maximum=512):
            return False
    if 'settingCount' in value and (type(value['settingCount']) is not int or value['settingCount'] < 0):
        return False
    if 'isAssigned' in value and type(value['isAssigned']) is not bool:
        return False
    priority = value.get('priorityMetaData')
    if priority is not None:
        if not isinstance(priority, dict) or set(priority) - {'@odata.type', 'priority'} or type(priority.get('priority')) is not int:
            return False
        if priority.get('@odata.type', _NS + 'deviceManagementPriorityMetaData') not in (
                _NS + 'deviceManagementPriorityMetaData', 'microsoft.graph.deviceManagementPriorityMetaData'):
            return False
    if 'disableEntraGroupPolicyAssignment' in value and type(value['disableEntraGroupPolicyAssignment']) is not bool:
        return False
    template = value.get('templateReference')
    if template is not None:
        if not isinstance(template, dict) or set(template) - {'@odata.type', 'templateId', 'templateFamily', 'templateDisplayName', 'templateDisplayVersion'}:
            return False
        if template.get('@odata.type', _NS + 'deviceManagementConfigurationPolicyTemplateReference') not in (
                _NS + 'deviceManagementConfigurationPolicyTemplateReference', 'microsoft.graph.deviceManagementConfigurationPolicyTemplateReference'):
            return False
        if template.get('templateId') != '' or template.get('templateFamily') != 'none':
            return False
        if any(template.get(name) is not None for name in ('templateDisplayName', 'templateDisplayVersion')):
            return False
    return True


def _known_setting(value):
    if not isinstance(value, dict) or set(value) - {'@odata.type', 'id', 'settingInstance'}:
        return False
    if not _annotation(value, 'deviceManagementConfigurationSetting'):
        return False
    if not _ordinary_text(value.get('id'), empty=False, maximum=512):
        return False
    instance = value.get('settingInstance')
    if not isinstance(instance, dict) or set(instance) - {'@odata.type', 'settingDefinitionId', 'settingInstanceTemplateReference', 'choiceSettingValue'}:
        return False
    if instance.get('@odata.type') != _NS + 'deviceManagementConfigurationChoiceSettingInstance':
        return False
    if instance.get('settingDefinitionId') != _DEFINITION or instance.get('settingInstanceTemplateReference') is not None:
        return False
    choice = instance.get('choiceSettingValue')
    if not isinstance(choice, dict) or set(choice) - {'@odata.type', 'settingValueTemplateReference', 'value', 'children'}:
        return False
    return (choice.get('@odata.type') == _NS + 'deviceManagementConfigurationChoiceSettingValue'
            and choice.get('settingValueTemplateReference') is None
            and choice.get('value') == _DEFINITION + '_2'
            and choice.get('children') == [])


def _known_assignment(value):
    if not isinstance(value, dict) or set(value) - {'@odata.type', 'id', 'target', 'source', 'sourceId'}:
        return False
    if not _annotation(value, 'deviceManagementConfigurationPolicyAssignment') or not _ordinary_text(value.get('id'), empty=False, maximum=512):
        return False
    if value.get('source') != 'direct' or value.get('sourceId') not in (None, ''):
        return False
    target = value.get('target')
    if not isinstance(target, dict) or set(target) - {'@odata.type', 'groupId', 'deviceAndAppManagementAssignmentFilterType', 'deviceAndAppManagementAssignmentFilterId'}:
        return False
    if target.get('@odata.type') not in (_NS + 'groupAssignmentTarget', _NS + 'exclusionGroupAssignmentTarget') or not _uuid(target.get('groupId')):
        return False
    filter_type = target.get('deviceAndAppManagementAssignmentFilterType')
    filter_id = target.get('deviceAndAppManagementAssignmentFilterId')
    if target.get('@odata.type') == _NS + 'exclusionGroupAssignmentTarget' and filter_type != 'none':
        return False
    return (filter_type == 'none' and filter_id is None
            or filter_type in ('include', 'exclude') and bool(_uuid(filter_id)))


def _route_url(value, endpoint):
    if not isinstance(value, str) or not value or any(not 32 <= ord(c) < 127 for c in value):
        return False
    try:
        parts = urlsplit(value)
        return (parts.scheme == 'https' and parts.netloc == 'graph.microsoft.com'
                and parts.path == urlsplit(endpoint).path and not parts.fragment
                and parts.username is None and parts.password is None)
    except ValueError:
        return False


def _collections(source, policy_id, issue):
    """Read each collection and independently prove its complete page chain."""
    result = {'policies': [], 'settings': [], 'assignments': []}
    coverage = []
    for kind in result:
        owner = None if kind == 'policies' else policy_id
        candidates = [(i, value) for i, value in enumerate(source['collections'])
                      if value.get('kind') == kind and value.get('owner_id') == owner]
        complete = False
        if len(candidates) == 1:
            ci, collection = candidates[0]
            endpoint = _GRAPH if kind == 'policies' else _GRAPH + '/' + policy_id + '/' + kind
            complete = (collection.get('coverage') == 'complete'
                        and collection.get('reason') is None and bool(collection['pages']))
            expected_url = endpoint
            seen_urls = set()
            seen_records = set()
            annotated_totals = []
            for pi, page in enumerate(collection['pages']):
                body_pointer = '/collections/' + str(ci) + '/pages/' + str(pi) + '/body'
                url, body = page['request_url'], page['body']
                page_checks = [url == expected_url, url not in seen_urls, _route_url(url, endpoint),
                               page['method'] == 'GET', type(page['http_status']) is int and page['http_status'] == 200,
                               isinstance(body.get('value'), list),
                               not set(body) - {'value', '@odata.context', '@odata.count', '@odata.nextLink'}]
                if '@odata.context' in body:
                    page_checks.append(_ordinary_text(body['@odata.context']))
                if '@odata.count' in body:
                    page_checks.append(type(body['@odata.count']) is int and body['@odata.count'] >= 0)
                seen_urls.add(url)
                if not all(page_checks):
                    complete = False
                    issue('invalid_collection_page', body_pointer)
                else:
                    if '@odata.count' in body:
                        annotated_totals.append(body['@odata.count'])
                    for ri, record in enumerate(body['value']):
                        record_pointer = body_pointer + '/value/' + str(ri)
                        if not isinstance(record, dict):
                            complete = False
                            issue('invalid_source_record', record_pointer)
                            continue
                        identity = record.get('id')
                        if kind in ('policies','assignments') and _uuid(identity):
                            identity = str(UUID(identity))
                        if not isinstance(identity, str) or identity in seen_records:
                            complete = False
                            issue('duplicate_or_missing_source_identity', record_pointer)
                        if isinstance(identity, str):
                            seen_records.add(identity)
                        result[kind].append((record, record_pointer))
                expected_url = body.get('@odata.nextLink')
                if '@odata.nextLink' in body and not _route_url(expected_url, endpoint):
                    complete = False
            complete = bool(complete and expected_url is None)
            if any(total != len(result[kind]) for total in annotated_totals):
                complete = False
                issue('collection_count_mismatch', '/collections/' + kind)
        if not complete:
            issue('collection_incomplete', '/collections/' + kind)
        coverage.append({'kind': kind, 'complete': complete})
    if len(source['collections']) != 3:
        issue('unexpected_collection_set', '/collections')
    return coverage, result


def _validate_inputs(source, context):
    # The intake schema is declarative data. No producer validation helper is used.
    from jsonschema import Draft202012Validator, FormatChecker
    schema_path = Path(__file__).resolve().parents[1] / 'contracts/export-intake.schema.json'
    schema = json.loads(schema_path.read_text(encoding='utf-8'))
    if not Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(source):
        raise ValueError('capture_shape')
    if source['synthetic'] is not False or source['exporter'] != {
            'id': 'intune-iac-settings-catalog-graph', 'version': '1.0.0'}:
        raise ValueError('capture_family')
    if not isinstance(context, dict) or not _uuid(source['tenant_id']) or source['cloud'] != 'public':
        raise ValueError('context')
    required = {'schema_version': '1.0.0', 'tenant_id': source['tenant_id'], 'cloud': 'public',
                'source_is_synthetic': False, 'authorization': 'emit_only'}
    pins = {'provider_source': 'deploymenttheory/microsoft365', 'provider_version': '1.0.0',
            'engine': 'tofu', 'engine_version': '1.10.0', 'atmos_version': '1.199.0'}
    allowed = set(required) | set(pins) | {
        'selected_policy_id', 'component', 'stack', 'implementation', 'tenant_assurance',
        'target_assurance', 'repository_source_fingerprint', 'repository_revision',
        'backend_owner', 'state_key'}
    if set(context) - allowed or any(key not in context or not _same(context[key], value)
                                     for key, value in required.items()):
        raise ValueError('context')
    if any(key in context and not _same(context[key], value) for key, value in pins.items()):
        raise ValueError('context')
    if not _uuid(context.get('selected_policy_id')):
        raise ValueError('context')
    for field in ('component', 'stack', 'implementation'):
        if field == 'implementation' and field not in context:
            continue
        value = context.get(field)
        if not isinstance(value, str) or len(value) > 256 or not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', value):
            raise ValueError('context')
    for field, size in (('repository_source_fingerprint', 64), ('repository_revision', 40)):
        if field in context and (not isinstance(context[field], str)
                                 or not re.fullmatch('[0-9a-f]{' + str(size) + '}', context[field])):
            raise ValueError('context')
    for field in ('tenant_assurance', 'target_assurance', 'backend_owner', 'state_key'):
        if field in context and not _ordinary_text(context[field], maximum=512):
            raise ValueError('context')


def _lineage(source, rows, selected_id, policy, settings, assignments, configuration_available):
    """Derive field dispositions independently from source-record locations."""
    locations = {}
    for family in ('policies', 'settings', 'assignments'):
        for ordinal, (record, pointer) in enumerate(rows[family]):
            selected = family != 'policies' or record.get('id') == selected_id
            valid = bool(policy) if family == 'policies' else bool(
                (settings if family == 'settings' else assignments)[ordinal])
            locations[pointer] = (pointer, family, ordinal, selected, valid)
    page_retention = set()
    record_retention = set()
    for ci, collection in enumerate(source['collections']):
        for pi, page in enumerate(collection['pages']):
            root = '/collections/' + str(ci) + '/pages/' + str(pi) + '/body'
            contents = page['body']
            if not isinstance(contents.get('value'), list) or set(contents).difference({'value', '@odata.context', '@odata.count', '@odata.nextLink'}):
                page_retention.add(root)
            if isinstance(contents.get('value'), list):
                record_retention.update(root + '/value/' + str(i) for i in range(len(contents['value'])))
    output = []
    for pointer, value in _walk(source):
        meaning = 'service_owned'
        rule = 'capture.provenance'
        destinations = []
        blocking = False
        if pointer == '/tenant_id':
            meaning, rule = 'identity', 'capture.tenant'
            destinations = ['/tenant_id', '/key']
        if pointer == '/references' or pointer.startswith('/references/'):
            meaning, rule = 'separately_managed', 'capture.unverified_reference'
        if pointer == '/ownership' or pointer.startswith('/ownership/'):
            rule = 'capture.unverified_ownership'
        parts = pointer.split('/')
        record_root = '/'.join(parts[:8])
        location = locations.get(record_root)
        if '/'.join(parts[:6]) in page_retention:
            meaning, rule, blocking = 'unsupported', 'retention.unsupported_page', True
        elif location is None and record_root in record_retention:
            meaning, rule, blocking = 'unsupported', 'retention.unsupported_record', True
        elif location is not None:
            origin, family, ordinal, selected, valid = location
            relative = pointer[len(origin):]
            parts = relative.split('/')[1:]
            attribute = parts[0] if parts else None
            if not selected:
                rule = 'capture.unselected_object'
            elif not valid:
                meaning, rule, blocking = 'unsupported', 'retention.unsupported_record', True
            else:
                kind = {'policies':'policy', 'settings':'setting', 'assignments':'assignment'}[family]
                observed_path = '/observed/policy' if family == 'policies' else '/observed/' + family + '/' + str(ordinal)
                destinations = [observed_path + relative]
                rule = kind + '.observation'
                if family == 'policies':
                    names = {'name':'name', 'description':'description', 'platforms':'platforms',
                             'technologies':'technologies/0', 'roleScopeTagIds':'role_scope_tag_ids'}
                    if attribute == 'id':
                        meaning, rule = 'identity', 'policy.identity'
                        destinations += ['/object_id', '/key']
                    elif attribute in names:
                        meaning, rule = 'desired', 'policy.configuration'
                        if configuration_available:
                            tail = '/' + '/'.join(parts[1:]) if len(parts) > 1 else ''
                            destinations.append('/configuration/' + names[attribute] + tail)
                    elif (attribute == 'priorityMetaData' and policy.get(attribute) is not None
                          or attribute == 'disableEntraGroupPolicyAssignment' and policy.get(attribute) is True):
                        meaning, rule, blocking = 'unsupported', 'policy.unmapped_behavior', True
                elif family == 'settings':
                    if attribute == 'id':
                        meaning, rule = 'identity', 'setting.identity'
                        blocking = value != str(ordinal)
                    elif attribute == 'settingInstance':
                        meaning, rule = 'desired', 'setting.configuration'
                    if attribute in ('id', 'settingInstance') and configuration_available:
                        destinations.append('/configuration/settings/settings/' + str(ordinal) + relative)
                elif attribute == 'target':
                    meaning, rule = 'relationship', 'assignment.target'
                    if configuration_available:
                        config = '/configuration/assignments/' + str(ordinal)
                        if len(parts) == 1:
                            destinations.append(config)
                        elif len(parts) == 2:
                            name = {'@odata.type':'type', 'groupId':'group_id',
                                    'deviceAndAppManagementAssignmentFilterType':'filter_type',
                                    'deviceAndAppManagementAssignmentFilterId':'filter_id'}.get(parts[1])
                            if name == 'filter_id' and assignments[ordinal]['target']['deviceAndAppManagementAssignmentFilterType'] == 'none':
                                rule = 'assignment.inactive_filter'
                            elif name:
                                destinations.append(config + '/' + name)
        public_hash = None
        if destinations and not blocking and type(value) not in (dict, list):
            public_hash = _hash(value)
        output.append({'source_node_ref':_pointer_hash(pointer), 'source_value_sha256':public_hash,
                       'classification':'mapped' if destinations else 'restricted_source',
                       'disposition':meaning, 'rule_id':rule, 'rule_version':'1.1.0',
                       'destination_pointers':destinations, 'loss_blocking':blocking,
                       'retention_locator':'restricted-original-source'})
    return output


def _derive(source, context):
    """Reconstruct the source-derived contract without invoking normalization."""
    issues = []
    mapping_errors = []
    def issue(code, pointer, mapping=True):
        item = {'code': code, 'path_ref': _pointer_hash(pointer)}
        if item not in issues:
            issues.append(item)
        if mapping:
            mapping_errors.append(code)

    policy_id = context['selected_policy_id']
    coverage, rows = _collections(source, policy_id, issue)
    policy = {}
    selected = [(row, pointer) for row, pointer in rows['policies'] if row.get('id') == policy_id]
    if len(selected) != 1:
        issue('selected_policy_missing_or_duplicate', '/collections/policies')
    elif not _known_policy(selected[0][0]):
        issue('unsupported_policy_shape', selected[0][1])
    else:
        policy, pointer = selected[0]
        if policy.get('priorityMetaData') is not None or policy.get('disableEntraGroupPolicyAssignment') is True:
            issue('policy_behavior_not_mapped', pointer)

    settings = []
    identities = []
    for ordinal, (row, pointer) in enumerate(rows['settings']):
        if not _known_setting(row):
            settings.append({})
            issue('unsupported_setting_shape', pointer)
        else:
            settings.append(row)
            configuration_id = row['id'] if row['id'] == str(ordinal) else None
            identities.append({'source_id': row['id'], 'configuration_id': configuration_id,
                               'source_ordinal': ordinal})
            if configuration_id is None:
                issue('unsupported_setting_configuration_id', pointer + '/id')
    if not settings:
        issue('settings_missing', '/collections/settings')
    if len(settings) != 1:
        issue('unsupported_setting_cardinality', '/collections/settings')
    if 'settingCount' in policy and policy['settingCount'] != len(settings):
        issue('setting_count_mismatch', '/collections/policies')

    assignments = []
    projected_assignments = []
    references = set()
    target_digests = set()
    for row, pointer in rows['assignments']:
        if 'source' not in row:
            issue('assignment_source_unobserved', pointer)
        elif row.get('source') != 'direct':
            issue('assignment_source_not_direct', pointer)
        if not _known_assignment(row):
            assignments.append({})
            issue('unsupported_assignment_shape', pointer)
            continue
        assignments.append(row)
        target = row['target']
        mode = target['deviceAndAppManagementAssignmentFilterType']
        projected = {'type': target['@odata.type'][len(_NS):], 'group_id': target['groupId'],
                     'filter_type': mode}
        if mode != 'none':
            projected['filter_id'] = target['deviceAndAppManagementAssignmentFilterId']
            references.add(('filter', projected['filter_id']))
        references.add(('group', projected['group_id']))
        target_identity = {**projected, 'group_id': str(UUID(projected['group_id']))}
        if 'filter_id' in projected:
            target_identity['filter_id'] = str(UUID(projected['filter_id']))
        target_digest = _hash(target_identity)
        if target_digest in target_digests:
            issue('duplicate_assignment_target', pointer)
        target_digests.add(target_digest)
        projected_assignments.append(projected)
    if 'isAssigned' in policy and policy['isAssigned'] != bool(rows['assignments']):
        issue('assignment_flag_mismatch', '/collections/policies')
    references.update(('scope_tag', value) for value in policy.get('roleScopeTagIds', []))

    complete = not mapping_errors
    configuration = None
    if complete:
        configuration = {
            'name': policy['name'], 'description': policy.get('description'),
            'platforms': policy['platforms'], 'technologies': [policy['technologies']],
            'role_scope_tag_ids': policy['roleScopeTagIds'],
            'settings': {'settings': [{'id': row['id'], 'settingInstance': row['settingInstance']}
                                      for row in settings]},
            'assignments': projected_assignments}
    if references:
        issue('reference_evidence_unverified', '/references', False)
    issue('ownership_unknown', '/ownership', False)
    issue('provider_qualification_required', '', False)

    return {
        'schema_version': 'production-1.2.0', 'source_mode': 'plugin_graph_capture',
        'object_id': policy_id, 'tenant_id': source['tenant_id'],
        'key': 'p_' + UUID(source['tenant_id']).hex + '_' + UUID(policy_id).hex,
        'source_canonical_sha256': _hash(source),
        'observed': {'policy': policy, 'settings': settings, 'assignments': assignments},
        'configuration': configuration, 'setting_id_map': identities, 'coverage': coverage,
        'candidate_mapping_complete': complete, 'offline_mapping_complete': False,
        'blockers': issues,
        'references': [{'kind': kind, 'id': rid, 'coverage': 'unknown', 'ownership': 'unverified'}
                       for kind, rid in sorted(references)],
        'ownership': {'status': 'unknown'},
        'request_projection': {'status': 'not_constructed',
                               'provider_constructor_setting_id_behavior': 'configuration_ids_not_copied',
                               'wire_serialization_qualified': False},
        'state_expectations': {'status': 'unqualified', 'source_setting_ids': [row['id'] for row in settings if row],
                               'roundtrip_verified': False},
        'field_accounting': _lineage(source, rows, policy_id, policy, settings, assignments, complete),
        'execution_authorized': False, 'provider_qualified': False, 'live_qualification': 'not_run'}


def _check_files(raw, expected, files, context):
    """Check the entire output closure and independently parse the inactive HCL."""
    if not isinstance(files, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                          for k, v in files.items()):
        return ['production_files_invalid']
    expected_json = {
        'review/normalized.json': expected,
        'BLOCKED.json': {'execution_allowed': False, 'blockers': expected['blockers']},
        'commands/command-cards.json': {'schema_version': '1.0.0', 'cards': []},
        'adoption/setting-id-map.json': {'schema_version': '1.0.0', 'entries': expected['setting_id_map']},
        'adoption/target-receipt.json': {'schema_version': '1.0.0', 'context_canonical_sha256': _hash(context),
                                        'component': context['component'], 'stack': context['stack'],
                                        'implementation': context.get('implementation'),
                                        'repository_source_fingerprint': context.get('repository_source_fingerprint'),
                                        'execution_authorized': False},
        'adoption/source-receipt.json': {'schema_version': '1.0.0',
                                        'source_byte_sha256': hashlib.sha256(raw).hexdigest(),
                                        'source_canonical_sha256': expected['source_canonical_sha256']}}
    allowed = {'README.md'}
    hcl_path = None
    if expected['candidate_mapping_complete']:
        prefix = 'candidates/components/terraform/' + context['component'] + '/'
        expected_json[prefix + 'configuration.json'] = expected['configuration']
        expected_json[prefix + 'settings.json'] = expected['configuration']['settings']
        expected_json['candidates/target.json'] = {
            'schema_version': '1.0.0', 'component': context['component'], 'stack': context['stack'],
            'tenant_id': expected['tenant_id'], 'object_id': expected['object_id'],
            'source_authenticity_verified': False, 'provider_qualified': False, 'execution_authorized': False}
        hcl_path = prefix + 'main.tf.txt'
        allowed.add(hcl_path)
    allowed.update(expected_json)
    if set(files) != allowed:
        return ['production_file_closure_changed']
    errors = []
    for path, value in expected_json.items():
        try:
            if not _same(_decode(files[path]), value):
                errors.append('production_json_file_changed')
        except (ValueError, TypeError, UnicodeError, RecursionError):
            errors.append('production_json_file_invalid')
    if hcl_path is not None:
        try:
            import hcl2
            from hcl2.utils import SerializationOptions
            parsed = hcl2.loads(files[hcl_path], serialization_options=SerializationOptions(
                strip_string_quotes=True, explicit_blocks=False, with_comments=False))
            attributes = {field: '${local.configuration.' + field + '}' for field in (
                'name', 'description', 'platforms', 'technologies', 'role_scope_tag_ids', 'assignments')}
            attributes['settings'] = '${jsonencode(local.configuration.settings)}'
            attributes['lifecycle'] = [{'prevent_destroy': True, 'precondition': [{
                'condition': '${local.configuration.name == "" && local.configuration.name != ""}',
                'error_message': 'Inactive candidate requires independent provider and tenant qualification.'}]}]
            hcl_expected = {
                'terraform': [{'required_version': '= 1.10.0', 'required_providers': [{
                    'microsoft365': {'source': 'deploymenttheory/microsoft365', 'version': '= 1.0.0'}}]}],
                'locals': [{'configuration': '${jsondecode(file("${path.module}/configuration.json"))}'}],
                'resource': [{_RESOURCE: {'policy': attributes}}]}
            if not _same(parsed, hcl_expected):
                errors.append('production_hcl_changed')
        except ImportError:
            errors.append('production_hcl_parser_unavailable')
        except Exception:
            errors.append('production_hcl_invalid')
    return sorted(set(errors))


def compare(raw: bytes, normalized: dict, *, context: dict, files: dict | None = None) -> list:
    """Return only fixed safe codes; never expose source data or parser messages."""
    try:
        if not isinstance(raw, bytes) or not isinstance(normalized, dict):
            return ['production_input_invalid']
        source = _decode(raw, capture=True)
        _validate_inputs(source, context)
        expected = _derive(source, context)
        if not _same(normalized, expected):
            return ['production_normalized_mismatch']
        return [] if files is None else _check_files(raw, expected, files, context)
    except Exception:
        # Third-party parsers may include raw values in exception strings.
        return ['production_source_validation_failed']
