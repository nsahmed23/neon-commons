"""Independent, bounded offline preservation oracle.

No normalizer, generator, validation, or shared projection helpers are imported.
Schemas and capability declarations are data, read by this separately implemented
parser. Equality here does not establish server authenticity or provider roundtrip.
"""
from collections import Counter
from datetime import datetime
import hashlib
import json
import shlex
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
ODATA = '#microsoft.graph.'
RESOURCE = 'microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json'
PROVIDER = 'deploymenttheory/microsoft365'
SECRET_KEYS = {'clientsecret', 'accesstoken', 'refreshtoken', 'password', 'privatekey',
               'authorization', 'recoverykey', 'secret'}


def _escape(key):
    return key.replace('~', '~0').replace('/', '~1')


def _walk(value, pointer=''):
    yield pointer, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, pointer + '/' + _escape(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, pointer + '/' + str(index))


def pointers(value, p=''):
    """Legacy public traversal API, including every container and empty node."""
    return [pointer for pointer, _ in _walk(value, p)]


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def _json_equal(actual, expected):
    """Preserve JSON types: Python equates true with 1 and false with 0."""
    return _canonical(actual) == _canonical(expected)


def _artifact_json(text):
    # Generated JSON has the same bounded integer-only contract as this slice.
    # Parse independently; duplicate keys must not disappear before comparison.
    return _strict_source(text)[0]


def _digest(value):
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def _strict_source(source):
    raw_digest = None
    if isinstance(source, (bytes, bytearray, str)):
        raw = source.encode('utf-8') if isinstance(source, str) else bytes(source)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError('source_size_limit')
        raw_digest = hashlib.sha256(raw).hexdigest()
        def pairs(entries):
            result = {}
            for key, value in entries:
                if key in result:
                    raise ValueError('duplicate_json_key')
                result[key] = value
            return result
        def prohibited(_):
            raise ValueError('unsupported_numeric_encoding')
        try:
            source = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                                parse_float=prohibited, parse_constant=prohibited)
        except (UnicodeError, json.JSONDecodeError, RecursionError):
            raise ValueError('source_parse_failed') from None
    def bounded(value, depth=0):
        if depth > 64:
            raise ValueError('source_depth_limit')
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError('source_shape_invalid')
            for child in value.values():
                bounded(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                bounded(child, depth + 1)
        elif isinstance(value, float) or (isinstance(value, int) and not isinstance(value, bool)
                                         and abs(value) > 9007199254740991):
            raise ValueError('unsupported_numeric_encoding')
        elif value is not None and not isinstance(value, (str, int, bool)):
            raise ValueError('source_shape_invalid')
    bounded(source)
    if not isinstance(source, dict):
        raise ValueError('source_shape_invalid')
    return source, raw_digest


def _schema(name):
    path = ROOT / 'corrections/contracts' / (name + '.schema.json')
    if not path.is_file():
        path = ROOT / 'contracts' / (name + '.schema.json')
    return json.loads(path.read_text())


def _schema_valid(name, value):
    from jsonschema import Draft202012Validator, FormatChecker
    return Draft202012Validator(_schema(name), format_checker=FormatChecker()).is_valid(value)


def _inside(pointer, roots):
    return any(pointer == root or pointer.startswith(root + '/') for root in roots)


def _stamp(value):
    try:
        return isinstance(value, str) and datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is not None
    except (ValueError, TypeError):
        return False


def _guid(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value.lower() and UUID(value).int != 0
    except (ValueError, AttributeError):
        return False


def _relationship_identity(value):
    return str(UUID(value)) if _guid(value) else value


def _known_projection(source):
    """Whitelist by reviewed schema/discriminator, retaining absent vs null.

    Return safe observed data and roots retained only in restricted originals.
    Invalid *known* primitive values are retained for inactive review, never
    treated as capability-qualified. Unknown keys/types and secret values drop.
    """
    unknown, sensitive = set(), set()
    instance_names = set()
    value_names = set()
    ss = _schema('observed-setting')
    for definition in ss['$defs'].values():
        variants = definition.get('oneOf', [definition])
        for variant in variants:
            props = variant.get('properties', {})
            instance_names.update(props)
            value_names.update(props)
    setting_names = set(ss['properties']) | instance_names | value_names | {
        'settingInstanceTemplateId', 'settingValueTemplateId', 'useTemplateDefault',
        'groupSettingCollectionValue'}
    accepted_types = {ODATA + name for name in [
        'deviceManagementConfigurationPolicy', 'deviceManagementConfigurationPolicyAssignment',
        'groupAssignmentTarget', 'exclusionGroupAssignmentTarget',
        'deviceManagementConfigurationSetting', 'deviceManagementConfigurationChoiceSettingInstance',
        'deviceManagementConfigurationChoiceSettingValue', 'deviceManagementConfigurationSimpleSettingInstance',
        'deviceManagementConfigurationIntegerSettingValue', 'deviceManagementConfigurationStringSettingValue']}
    def project(value, spec, pointer, document, role=None):
        if isinstance(value, dict):
            fields = set(spec.get('properties', {})) if role != 'setting' else setting_names
            result = {}
            for key, child in value.items():
                pp = pointer + '/' + _escape(key)
                secret = key.lower().replace('_', '') in SECRET_KEYS or (
                    'SecretSettingValue' in str(value.get('@odata.type', '')) and key == 'value')
                if secret:
                    sensitive.add(pp)
                elif key not in fields or (key == '@odata.type' and child not in accepted_types):
                    unknown.add(pp)
                else:
                    childspec = spec.get('properties', {}).get(key, {})
                    result[key] = project(child, childspec, pp, document, role)
            return result
        if isinstance(value, list):
            return [project(child, spec.get('items', {}), pointer + '/' + str(i), document, role)
                    for i, child in enumerate(value)]
        return value
    # Wrapper keys are deliberately independent from generated normalization.
    top_fields = {'schema_version', 'synthetic', 'tenant_id', 'cloud', 'captured_at',
                  'exporter', 'collections', 'references', 'ownership'}
    exporter_fields = {'id', 'version'}
    ownership_fields = {'object_id', 'current_writer', 'adoption_intent'}
    ref_fields = {'kind', 'id', 'ownership', 'coverage', 'captured_at'}
    collection_fields = {'kind', 'owner_id', 'coverage', 'reason', 'pages'}
    page_fields = {'request_url', 'method', 'http_status', 'captured_at', 'body'}
    def whitelist(value, allowed, pointer):
        if not isinstance(value, dict):
            return value
        out = {}
        for key, child in value.items():
            pp = pointer + '/' + _escape(key)
            if key.lower().replace('_', '') in SECRET_KEYS:
                sensitive.add(pp)
            elif key not in allowed:
                unknown.add(pp)
            else:
                out[key] = child
        return out
    clean = whitelist(source, top_fields, '')
    clean['exporter'] = whitelist(source.get('exporter', {}), exporter_fields, '/exporter')
    clean['references'] = [whitelist(v, ref_fields, '/references/' + str(i))
                           for i, v in enumerate(source.get('references', []))]
    clean['ownership'] = [whitelist(v, ownership_fields, '/ownership/' + str(i))
                          for i, v in enumerate(source.get('ownership', []))]
    clean['collections'] = []
    for ci, collection in enumerate(source.get('collections', [])):
        cp = '/collections/' + str(ci)
        cc = whitelist(collection, collection_fields, cp)
        cc['pages'] = []
        for pi, page in enumerate(collection.get('pages', [])):
            pp = cp + '/pages/' + str(pi)
            pc = whitelist(page, page_fields, pp)
            body = whitelist(page.get('body', {}), {'value', '@odata.nextLink', '@odata.context', '@odata.count', 'error'}, pp + '/body')
            if 'error' in body:
                body['error'] = whitelist(body['error'], set(), pp + '/body/error')
            values = body.get('value', [])
            if isinstance(values, list):
                spec = _schema({'policies': 'observed-policy', 'settings': 'observed-setting',
                                'assignments': 'observed-assignment'}.get(collection.get('kind'), 'observed-policy'))
                body['value'] = [project(v, spec, pp + '/body/value/' + str(vi), spec, 'setting' if collection.get('kind') == 'settings' else None)
                                 for vi, v in enumerate(values)]
            pc['body'] = body
            cc['pages'].append(pc)
        clean['collections'].append(cc)
    return clean, unknown, sensitive


def _collections(source, pid):
    """Independently derive boundary, linked pages, coverage and observations."""
    rows, values, valid = [], {}, True
    required = {('policies', None), ('settings', pid), ('assignments', pid)}
    root = 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'
    counts = Counter()
    for ci, collection in enumerate(source.get('collections', [])):
        kind, owner = collection.get('kind'), collection.get('owner_id')
        if kind != 'policies' and owner != pid:
            valid = False
            continue
        if kind not in {'policies', 'settings', 'assignments'}:
            valid = False
            continue
        ident = kind, owner
        counts[ident] += 1
        boundary = root if kind == 'policies' else root + '/' + str(owner) + '/' + str(kind)
        pages = collection.get('pages', [])
        complete = collection.get('coverage') == 'complete' and bool(pages) and _schema_valid('capture', collection)
        expected, seen, observed = boundary, set(), []
        annotated_counts = []
        for pi, page in enumerate(pages):
            url = page.get('request_url')
            complete = complete and isinstance(url, str) and url == expected and url not in seen
            if isinstance(url, str):
                seen.add(url)
                parsed = urlsplit(url)
                complete = complete and parsed.scheme == 'https' and parsed.netloc == 'graph.microsoft.com'
                complete = complete and parsed.path == urlsplit(boundary).path and not parsed.fragment
                complete = complete and not any(ord(c) < 32 or ord(c) == 127 for c in url)
                complete = complete and not ({'$filter', '$search', '$select', '$top', '$skip', '$expand'} & {k.lower() for k in parse_qs(parsed.query, keep_blank_values=True)})
            complete = complete and page.get('method') == 'GET' and page.get('http_status') == 200 and _stamp(page.get('captured_at'))
            body = page.get('body', {})
            if isinstance(body, dict) and 'error' in body:
                complete = False
            if isinstance(body, dict) and '@odata.count' in body:
                annotated_counts.append(body['@odata.count'])
            vv = body.get('value') if isinstance(body, dict) else None
            if not isinstance(vv, list):
                complete = False
            elif page.get('http_status') == 200:
                observed.extend((value, f'/collections/{ci}/pages/{pi}/body/value/{vi}') for vi, value in enumerate(vv))
            expected = body.get('@odata.nextLink') if isinstance(body, dict) else None
        observed_keys = [record.get('id') if kind == 'settings' else _relationship_identity(record.get('id'))
                         for record, _ in observed if isinstance(record, dict)]
        identities_valid = (len(observed_keys) == len(observed)
                            and all(isinstance(identity, str) for identity in observed_keys))
        if identities_valid:
            identities_valid = len(observed_keys) == len(set(observed_keys))
        complete = bool(complete and identities_valid and expected is None
                        and all(type(value) is int and value >= 0 and value == len(observed)
                                for value in annotated_counts))
        rows.append({'kind': kind, 'owner_id': owner, 'complete': complete,
                     'page_count': len(pages), 'source_pointer': '/collections/' + str(ci)})
        values.setdefault(ident, observed)
        valid = valid and complete
    return rows, values, bool(valid and all(counts[k] == 1 for k in required))


def _capable(policy, settings):
    """Read declarative registry; no generator capability function is used."""
    path = ROOT / 'corrections/contracts/capability-map.json'
    if not path.is_file():
        return False
    registry = json.loads(path.read_text())
    # Registry parsing is reviewed and kept deliberately limited to declarations.
    if registry.get('schema_version') != '1.0.0' or registry.get('qualification') != 'bounded_offline_mapping_only' or registry.get('default_status') != 'review_only':
        return False
    entries = registry.get('entries', [])
    for setting in settings:
        instance = setting.get('settingInstance', {})
        match = [entry for entry in entries if entry.get('setting_definition_id') == instance.get('settingDefinitionId')]
        if len(match) != 1:
            return False
        entry = match[0]
        if policy.get('platforms') != entry.get('platforms'):
            return False
        if policy.get('technologies') != entry.get('technologies'):
            return False
        val = instance.get('choiceSettingValue', instance.get('simpleSettingValue', {}))
        if entry.get('support_status') != 'supported_offline' or instance.get('@odata.type') != entry.get('instance_type') or val.get('@odata.type') != entry.get('value_type'):
            return False
        allowed = entry.get('permitted_values', [])
        if val.get('value') not in allowed:
            return False
        if entry.get('children') != 'empty_only' or val.get('children') != []:
            return False
    return bool(settings)


def _accounting(source, policy_pointer, settings, assignments, unknown, sensitive):
    """Separate reviewed field rule implementation; all containers included."""
    output = []
    policy_names = {'name': 'name', 'description': 'description', 'platforms': 'platforms',
                    'technologies': 'technologies', 'roleScopeTagIds': 'role_scope_tag_ids'}
    source_digest = _digest(source)
    for pointer, value in _walk(source):
        disposition, rule, destinations = 'service_owned', 'capture.provenance.v2', []
        if policy_pointer and (pointer == policy_pointer or pointer.startswith(policy_pointer + '/')):
            suffix = pointer[len(policy_pointer):]
            attr = suffix[1:].split('/')[0]
            if attr == 'id':
                disposition, rule, destinations = 'identity', 'policy.identity.v2', ['/object_id', '/key']
            elif attr in policy_names:
                destination = '/desired/' + policy_names[attr] + suffix[len(attr) + 1:]
                if attr == 'technologies':
                    destination += '/0'
                disposition, rule, destinations = 'desired', 'policy.desired.v2', [destination]
            else:
                rule, destinations = 'policy.metadata.v2', ['/observed/policy' + suffix]
        for index, (_, sp) in enumerate(settings):
            desired_index = sum(not _inside(prior, unknown | sensitive) for _, prior in settings[:index])
            if pointer == sp or pointer.startswith(sp + '/'):
                suffix = pointer[len(sp):]
                rule, destinations = 'setting.wrapper.v2', ['/observed/settings/' + str(index) + suffix]
                if suffix == '/id':
                    disposition, rule, destinations = 'identity', 'setting.identity.v2', ['/desired/settings/settings/' + str(desired_index) + '/id']
                elif suffix == '/@odata.type':
                    rule = 'setting.wrapper-type.v2'
                elif suffix == '/settingInstance' or suffix.startswith('/settingInstance/'):
                    disposition, rule, destinations = 'desired', 'setting.instance.v2', ['/desired/settings/settings/' + str(desired_index) + suffix]
        for index, (assignment, ap) in enumerate(assignments):
            desired_index = sum(not _inside(prior, unknown | sensitive) for _, prior in assignments[:index])
            if pointer == ap or pointer.startswith(ap + '/'):
                suffix = pointer[len(ap):]
                rule, destinations = 'assignment.metadata.v2', ['/observed/assignments/' + str(index) + suffix]
                if suffix == '/target' or suffix.startswith('/target/'):
                    disposition, rule, destinations = 'relationship', 'assignment.target.v2', []
                    if suffix == '/target':
                        destinations = ['/desired/assignments/' + str(desired_index)]
                    else:
                        key = suffix[len('/target/'):]
                        mapped = {'@odata.type': 'type', 'groupId': 'group_id',
                                  'deviceAndAppManagementAssignmentFilterType': 'filter_type',
                                  'deviceAndAppManagementAssignmentFilterId': 'filter_id'}.get(key)
                        if mapped and not (mapped == 'filter_id' and assignment.get('target', {}).get('deviceAndAppManagementAssignmentFilterType') == 'none'):
                            destinations = ['/desired/assignments/' + str(desired_index) + '/' + mapped]
        if pointer == '/references' or pointer.startswith('/references/'):
            disposition, rule, destinations = 'separately_managed', 'reference.external.v2', [pointer]
            parts = pointer.split('/')
            if len(parts) > 2 and parts[2].isdigit():
                original_index = int(parts[2])
                mapped_index = sum(not _inside('/references/' + str(i), unknown | sensitive) for i in range(original_index))
                destinations = ['/references/' + str(mapped_index) + ('/' + '/'.join(parts[3:]) if len(parts) > 3 else '')]
        restricted = _inside(pointer, unknown) or _inside(pointer, sensitive)
        if restricted:
            disposition = 'sensitive_local_only' if _inside(pointer, sensitive) else 'unsupported'
            rule = 'retention.sensitive.v2' if disposition == 'sensitive_local_only' else 'retention.unsupported.v2'
            destinations = []
        kind = ('null' if value is None else 'boolean' if isinstance(value, bool) else 'object' if isinstance(value, dict)
                else 'array' if isinstance(value, list) else 'number' if isinstance(value, int) else 'string')
        row = {'source_pointer': pointer, 'kind': kind, 'disposition': disposition,
               'rule_id': rule, 'rule_version': '2.0.0', 'destination_pointers': destinations,
               'reason': 'Restricted original only' if restricted else rule,
               'loss_blocking': restricted}
        if restricted:
            finding = 'f_' + hashlib.sha256(pointer.encode('utf-8')).hexdigest()[:24]
            row.update(source_pointer='opaque:' + finding, finding_id=finding,
                       retention_locator='restricted-original-source', source_digest_ref=source_digest)
        output.append(row)
    return output


def _assignment_equal(actual, expected):
    if actual is None or expected is None:
        return actual is expected
    if not isinstance(actual, list) or not isinstance(expected, list):
        return False
    return Counter(_canonical(v) for v in actual) == Counter(_canonical(v) for v in expected)


def _desired_equal(actual, expected):
    if not isinstance(actual, dict) or set(actual) != set(expected):
        return False
    return all(_assignment_equal(actual[key], value) if key == 'assignments' else _json_equal(actual[key], value)
               for key, value in expected.items())


def _files(files):
    if isinstance(files, (str, Path)):
        directory = Path(files)
        return {p.relative_to(directory).as_posix(): p.read_text(encoding='utf-8')
                for p in directory.rglob('*') if p.is_file()}
    if isinstance(files, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
        return files
    raise ValueError('generated_files_invalid')


def _artifacts(files, expected, normalized, partial, raw_digest):
    errors = []
    address = RESOURCE + '.policy["' + expected['key'] + '"]'
    args = ['terraform', 'import', 'intune-reference', '-s', 'reference-dev', address, expected['pid']]
    if any(name.endswith(('.sh', '.ps1', '.bat', '.cmd')) for name in files):
        errors.append('generated_active_script_unqualified')
    allowed_configs = set() if partial else {
        'components/terraform/intune-reference/main.tf',
        'components/terraform/intune-reference/imports.tf',
        'atmos.yaml', 'stacks/orgs/reference/dev.yaml'}
    for name in files:
        if name.endswith(('.tfvars', '.tfvars.json', '.hcl', '.yaml', '.yml')) and name not in allowed_configs:
            errors.append('generated_config_path_unqualified')
    try:
        manifest = _artifact_json(files['generated-files.json']) if 'generated-files.json' in files else None
        if manifest is not None:
            actual_hashes = {name: hashlib.sha256(value.encode('utf-8')).hexdigest()
                             for name, value in files.items() if name != 'generated-files.json'}
            if manifest.get('schema_version') != '1.0.0' or manifest.get('files') != actual_hashes:
                errors.append('generated_manifest_changed')
        if raw_digest is not None and 'adoption/source-receipt.json' not in files:
            errors.append('raw_source_receipt_missing')
        if 'adoption/source-receipt.json' in files:
            receipt = _artifact_json(files['adoption/source-receipt.json'])
            if receipt.get('schema_version') != '1.0.0' or set(receipt) != {'schema_version', 'source_byte_sha256', 'source_canonical_sha256'}:
                errors.append('source_receipt_invalid')
            if receipt.get('source_canonical_sha256') != expected['digest']:
                errors.append('source_receipt_digest_changed')
            if raw_digest is not None and receipt.get('source_byte_sha256') != raw_digest:
                errors.append('raw_source_digest_changed')
        object_map = _artifact_json(files['adoption/object-map.json'])
        objects = object_map.get('objects', [])
        if len(objects) != 1:
            errors.append('generated_object_map_changed')
        else:
            obj = objects[0]
            for key, value in {'tenant_id': expected['tenant'], 'object_id': expected['pid'],
                               'address': address, 'import_id': expected['pid'],
                               'resource_family': 'settings_catalog_policy',
                               'provider_source': PROVIDER, 'provider_version': '1.0.0',
                               'referenced_objects_owner': 'external'}.items():
                if obj.get(key) != value:
                    errors.append('generated_object_map_changed')
        command_doc = _artifact_json(files['commands/command-cards.json'])
        cards = command_doc.get('cards')
        if not isinstance(cards, list) or set(command_doc) != {'schema_version', 'cards'} or command_doc['schema_version'] != '1.0.0':
            errors.append('generated_commands_invalid')
        elif partial and cards:
            errors.append('partial_has_command_cards')
        elif not partial:
            expected_card = {
                'id': 'propose-import', 'purpose': 'Attach existing policy ID through the pinned importer; not execute here',
                'executable': 'atmos', 'arguments': args, 'working_directory': '.',
                'effect_class': 'state_mutation', 'effects': {'local_write': True, 'network': True,
                    'state_write': True, 'cloud_write': 'provider_path_requires_qualification'},
                'authorization': 'protected_ci_required', 'execution_allowed': False,
                'expected_exit_codes': [0], 'provider_source': PROVIDER, 'provider_version': '1.0.0'}
            if not _json_equal(cards, [expected_card]):
                errors.append('generated_command_contract_changed')
            if any(card.get('execution_allowed') is not False for card in cards):
                errors.append('false_execution_authority')
            if any(card.get('arguments') != args for card in cards):
                errors.append('generated_command_identity_changed')
            bash = '#!/usr/bin/env bash\nset -o pipefail\n' + ' '.join(shlex.quote(arg) for arg in ['atmos', *args]) + '\nstatus=$?\nexit "$status"\n'
            def ps_quote(arg):
                return "'" + arg.replace("'", "''") + "'"
            powershell = ("#requires -Version 7.3\n$ErrorActionPreference = 'Stop'\n"
                "$PSNativeCommandArgumentPassing = 'Standard'\n$exe = " + ps_quote('atmos')
                + '\n$nativeArgs = @(' + ', '.join(ps_quote(arg) for arg in args) + ')\n'
                + '& $exe @nativeArgs\n$nativeStatus = $LASTEXITCODE\nexit $nativeStatus\n')
            if files.get('commands/PROPOSED-import.sh.txt') != bash or files.get('commands/PROPOSED-import.ps1.txt') != powershell:
                errors.append('generated_command_preview_changed')
        adoption_path = 'review/adoption-input.json' if partial else 'components/terraform/intune-reference/adoption-input.json'
        adoption = _artifact_json(files[adoption_path])
        if adoption.get('key') != expected['key'] or not _desired_equal(adoption.get('desired'), expected['desired']):
            errors.append('generated_desired_changed')
        if not _json_equal(_artifact_json(files['adoption/field-accounting.json']).get('records'), normalized.get('field_accounting')):
            errors.append('generated_accounting_changed')
        if not _json_equal(_artifact_json(files['adoption/coverage.json']).get('collections'), expected['coverage']):
            errors.append('generated_coverage_changed')
        capability = _artifact_json(files['adoption/capability.json'])
        if capability.get('offline_mapping_complete') is not (not partial) or capability.get('execution_authorized') is not False:
            errors.append('generated_capability_changed')
    except (KeyError, TypeError, ValueError):
        errors.append('generated_json_invalid')
    active = [name for name in files if name.endswith(('.tf', '.tf.json'))]
    expected_active = {'components/terraform/intune-reference/main.tf', 'components/terraform/intune-reference/imports.tf'}
    if not partial and set(active) != expected_active:
        errors.append('generated_component_paths_changed')
    if not partial:
        try:
            import yaml
            class UniqueLoader(yaml.SafeLoader):
                pass
            def unique_mapping(loader, node):
                result = {}
                for key_node, value_node in node.value:
                    key = loader.construct_object(key_node)
                    if key in result:
                        raise ValueError('duplicate_yaml_key')
                    result[key] = loader.construct_object(value_node)
                return result
            UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)
            atmos = yaml.load(files['atmos.yaml'], Loader=UniqueLoader)
            expected_atmos = {'base_path': '.', 'components': {'terraform': {
                'base_path': 'components/terraform', 'command': 'tofu', 'apply_auto_approve': False,
                'auto_generate_backend_file': False}}, 'stacks': {'base_path': 'stacks',
                'included_paths': ['orgs/**/*'], 'name_pattern': '{tenant}-{stage}'}}
            stack = yaml.load(files['stacks/orgs/reference/dev.yaml'], Loader=UniqueLoader)
            expected_stack = {'vars': {'tenant': 'reference', 'stage': 'dev'},
                'components': {'terraform': {'intune-reference': {'command': 'tofu',
                    'vars': {'live_qualification_ack': False}}}}}
            if not _json_equal(atmos, expected_atmos) or not _json_equal(stack, expected_stack):
                errors.append('generated_stack_guard_changed')
            if files.get('.tool-versions') != 'opentofu 1.10.0\natmos 1.199.0\n':
                errors.append('generated_tool_versions_changed')
        except ImportError:
            errors.append('yaml_parser_unavailable')
        except Exception:
            errors.append('generated_yaml_parse_failed')
    if partial:
        if active:
            errors.append('partial_has_active_infrastructure')
        return errors
    try:
        import hcl2
        from hcl2.utils import SerializationOptions
    except ImportError:
        return errors + ['hcl_parser_unavailable']
    try:
        parsed = []
        for name in active:
            if name.endswith('.tf.json'):
                errors.append('generated_hcl_json_unqualified')
            else:
                parsed.append(hcl2.loads(files[name], serialization_options=SerializationOptions(
                    strip_string_quotes=True, explicit_blocks=False, with_comments=False)))
        if any(set(p) - {'terraform', 'variable', 'locals', 'resource', 'output', 'import'} for p in parsed):
            errors.append('generated_hcl_blocks_changed')
        resources = [r for p in parsed for r in p.get('resource', [])]
        imports = [i for p in parsed for i in p.get('import', [])]
        if len(resources) != 1 or set(resources[0]) != {RESOURCE} or set(resources[0][RESOURCE]) != {'policy'}:
            errors.append('generated_resource_address_changed')
        else:
            resource = resources[0][RESOURCE]['policy']
            mapped = {key: '${each.value.' + key + '}' for key in
                      ['name', 'description', 'platforms', 'technologies', 'role_scope_tag_ids', 'assignments']}
            mapped['settings'] = '${jsonencode(each.value.settings)}'
            mapped['for_each'] = {'${(local.adoption.key)}': '${local.adoption.desired}'}
            for field, expression in mapped.items():
                if resource.get(field) != expression:
                    errors.append('generated_resource_field_changed')
            if set(resource) != set(mapped) | {'lifecycle'}:
                errors.append('generated_resource_field_changed')
            lifecycle = resource.get('lifecycle', [])
            if not _json_equal(lifecycle, [{'prevent_destroy': True, 'precondition': [{'condition': '${var.live_qualification_ack}', 'error_message': 'Reference materials only: qualify provider, target and authorization before execution.'}]}]):
                errors.append('generated_guard_changed')
        if imports != [{'to': '${' + address + '}', 'id': expected['pid']}]:
            errors.append('generated_import_identity_changed')
        locals_ = [v for p in parsed for v in p.get('locals', [])]
        if locals_ != [{'adoption': '${jsondecode(file("${path.module}/adoption-input.json"))}'}]:
            errors.append('generated_input_binding_changed')
        terraform = [v for p in parsed for v in p.get('terraform', [])]
        if len(terraform) != 1 or terraform[0] != {'required_version': '>= 1.10.0, < 1.11.0', 'required_providers': [{'microsoft365': {'source': PROVIDER, 'version': '1.0.0'}}]}:
            errors.append('generated_provider_changed')
        variables = [v for p in parsed for v in p.get('variable', [])]
        if len(variables) != 1 or set(variables[0]) != {'live_qualification_ack'} or variables[0]['live_qualification_ack'].get('default') is not False or variables[0]['live_qualification_ack'].get('type') != 'bool':
            errors.append('generated_guard_changed')
        outputs = [v for p in parsed for v in p.get('output', [])]
        if len(outputs) != 1 or set(outputs[0]) != {'adoption_object_ids'} or outputs[0]['adoption_object_ids'].get('value') != '${{for k, v in ' + RESOURCE + '.policy : k => v.id}}':
            errors.append('generated_output_changed')
    except Exception:
        # Parser details might contain source values and must remain local.
        errors.append('generated_hcl_parse_failed')
    return errors


def compare(source, normalized, files=None, context=None):
    """Return safe error codes. Correct inactive partial review returns [].

    Context is the trusted selection/tenant input for repaired callers. Legacy
    two-argument callers derive selection from the record for API compatibility;
    they cannot independently establish the caller's selection intent.
    """
    try:
        source, raw_digest = _strict_source(source)
        return _compare(source, normalized, files, context or {}, raw_digest)
    except ImportError:
        return ['oracle_dependency_unavailable']
    except ValueError as error:
        code = str(error)
        return [code if code in {'source_size_limit', 'source_depth_limit', 'duplicate_json_key',
                                 'unsupported_numeric_encoding', 'source_parse_failed', 'source_shape_invalid',
                                 'generated_files_invalid'} else 'oracle_contract_invalid']
    except (KeyError, TypeError, AttributeError, IndexError, RecursionError):
        return ['oracle_input_invalid']


def _compare(source, normalized, files, context, raw_digest):
    errors = []
    if not isinstance(normalized, dict):
        return ['normalized_shape_invalid']
    pid = context.get('selected_policy_id', normalized.get('object_id'))
    tenant = context.get('tenant_id', source.get('tenant_id'))
    if not _guid(pid) or not _guid(tenant):
        return ['selected_identity_invalid']
    key = 'p_' + UUID(tenant).hex + '_' + UUID(pid).hex
    if normalized.get('object_id') != pid:
        errors.append('selected_id_not_present')
    if source.get('tenant_id') != tenant or normalized.get('tenant_id') != tenant:
        errors.append('tenant_changed')
    if normalized.get('key') != key:
        errors.append('resource_key_changed')
    digest = _digest(source)
    if normalized.get('source_canonical_sha256') != digest:
        errors.append('source_digest_changed')
    clean, unknown, sensitive = _known_projection(source)
    opaque_roots = set(unknown | sensitive)
    coverage, observations, complete = _collections(source, pid)
    _, safe_observations, _ = _collections(clean, pid)
    policies = observations.get(('policies', None), [])
    matches = [(value, pointer) for value, pointer in policies if isinstance(value, dict) and value.get('id', '').lower() == pid.lower()]
    if len(matches) != 1:
        return list(dict.fromkeys(errors + ['selected_id_not_present']))
    policy, policy_pointer = matches[0]
    safe_matches = [value for value, _ in safe_observations.get(('policies', None), []) if isinstance(value, dict) and value.get('id', '').lower() == pid.lower()]
    safe_policy = safe_matches[0]
    settings = observations.get(('settings', pid), [])
    assignments = observations.get(('assignments', pid), [])
    safe_settings = [v for v, _ in safe_observations.get(('settings', pid), [])]
    safe_assignments = [v for v, _ in safe_observations.get(('assignments', pid), [])]
    from jsonschema import Draft202012Validator, FormatChecker
    for field, value in list(safe_policy.items()):
        fragment = _schema('observed-policy')['properties'].get(field)
        if fragment and not Draft202012Validator(fragment, format_checker=FormatChecker()).is_valid(value):
            unknown.add(policy_pointer + '/' + _escape(field))
            del safe_policy[field]
    desired_settings = []
    for index, setting in enumerate(safe_settings):
        if not _schema_valid('observed-setting', setting) or not _capable(policy, [setting]):
            unknown.add(settings[index][1])
            safe_settings[index] = {}
        else:
            desired_settings.append({'id': setting['id'], 'settingInstance': setting['settingInstance']})
    for index, assignment in enumerate(safe_assignments):
        if not _schema_valid('observed-assignment', assignment):
            unknown.add(assignments[index][1])
            safe_assignments[index] = {}

    qualified = _schema_valid('export-intake', source) and complete and not unknown and not sensitive and source.get('cloud') == 'public' and source.get('synthetic') is True
    qualified = qualified and source.get('schema_version') == '1.0.0' and source.get('exporter') == {'id': 'appendix-b-graph-snapshot', 'version': '1.0.0'}
    qualified = qualified and _schema_valid('observed-policy', policy) and policy.get('@odata.type') == ODATA + 'deviceManagementConfigurationPolicy'
    qualified = qualified and all(_schema_valid('observed-setting', v) and v.get('@odata.type') == ODATA + 'deviceManagementConfigurationSetting' for v, _ in settings)
    qualified = qualified and all(_schema_valid('observed-assignment', v) and v.get('@odata.type') == ODATA + 'deviceManagementConfigurationPolicyAssignment' for v, _ in assignments)
    qualified = qualified and [s.get('id') for s, _ in settings] == [str(i) for i in range(len(settings))]
    qualified = qualified and policy.get('settingCount') == len(settings) and _capable(policy, [s for s, _ in settings])
    qualified = qualified and ('isAssigned' not in policy or policy['isAssigned'] == bool(assignments))
    for family, records in [('policies', policies), ('settings', settings), ('assignments', assignments)]:
        ids = [v.get('id') if family == 'settings' else _relationship_identity(v.get('id'))
               for v, _ in records if isinstance(v, dict)]
        qualified = qualified and len(ids) == len(set(ids))
    required_refs = {('scope_tag', tag) for tag in policy.get('roleScopeTagIds', [])}
    desired_assignments, target_tuples = [], []
    for assignment in safe_assignments:
        target = assignment.get('target')
        if not isinstance(target, dict):
            qualified = False
            continue
        ty = target.get('@odata.type', '').removeprefix(ODATA)
        group = target.get('groupId')
        mode = target.get('deviceAndAppManagementAssignmentFilterType')
        fid = target.get('deviceAndAppManagementAssignmentFilterId')
        required_refs.add(('group', group))
        if mode in {'include', 'exclude'}:
            required_refs.add(('filter', fid))
        tup = ty, _relationship_identity(group), mode, _relationship_identity(fid) if mode != 'none' else None
        target_tuples.append(tup)
        d = {'type': ty, 'group_id': group, 'filter_type': mode}
        if mode != 'none':
            d['filter_id'] = fid
        desired_assignments.append(d)
    qualified = qualified and len(target_tuples) == len(set(target_tuples))
    references = source.get('references', [])
    ref_schema = _schema('observed-inventory')['properties']['references']['items']
    safe_refs = []
    for index, original in enumerate(references):
        ref = clean['references'][index]
        good = Draft202012Validator(ref_schema, format_checker=FormatChecker()).is_valid(ref)
        good = good and (ref.get('kind') not in {'group', 'filter'} or _guid(ref.get('id')))
        if not good:
            unknown.add('/references/' + str(index))
            qualified = False
        else:
            safe_refs.append(ref)
    clean['references'] = safe_refs
    identities = [(r.get('kind'), r.get('id', '').lower()) for r in references]
    qualified = qualified and len(identities) == len(set(identities))
    for ident in required_refs:
        ref_identity = lambda kind, value: _relationship_identity(value) if kind in {'group','filter'} else value
        refs = [r for r in references if r.get('kind') == ident[0]
                and ref_identity(r.get('kind'), r.get('id')) == ref_identity(*ident)]
        qualified = qualified and len(refs) == 1 and refs[0].get('ownership') == 'external' and refs[0].get('coverage') == 'complete' and _stamp(refs[0].get('captured_at'))
    ownership = [v for v in source.get('ownership', []) if v.get('object_id') == pid]
    qualified = qualified and len(ownership) == 1 and ownership[0].get('current_writer') in {None, 'this-repository'}
    partial = not qualified
    expected_desired = {'name': safe_policy.get('name'), 'description': safe_policy.get('description'),
                        'platforms': safe_policy.get('platforms'), 'technologies': [safe_policy['technologies']] if 'technologies' in safe_policy else [],
                        'role_scope_tag_ids': safe_policy.get('roleScopeTagIds'),
                        'settings': {'settings': desired_settings},
                        'assignments': desired_assignments if safe_assignments or next((r['complete'] for r in coverage if r['kind'] == 'assignments'), False) else None}
    desired = normalized.get('desired', {})
    for a, b in [('name', 'name'), ('description', 'description'), ('platforms', 'platforms'),
                 ('technologies', 'technologies'), ('roleScopeTagIds', 'role_scope_tag_ids')]:
        if not _json_equal(desired.get(b), expected_desired[b]):
            errors.append('policy_field_changed:' + a)
    if not _json_equal(desired.get('settings'), expected_desired['settings']):
        errors.append('settings_subtree_changed')
    if not _assignment_equal(desired.get('assignments'), expected_desired['assignments']):
        errors.append('assignment_multiset_changed')
    if set(desired) != set(expected_desired):
        errors.append('desired_fields_changed')
    expected_observed = {'policy': safe_policy, 'settings': safe_settings, 'assignments': safe_assignments}
    if not _json_equal(normalized.get('observed'), expected_observed):
        errors.append('observed_records_changed')
    if not _json_equal(normalized.get('references'), clean.get('references')):
        errors.append('references_changed')
    if not _json_equal(normalized.get('coverage'), coverage):
        errors.append('source_completeness_changed')
    if normalized.get('offline_mapping_complete') is not (not partial):
        errors.append('mapping_status_changed')
    if bool(normalized.get('blockers')) != partial:
        errors.append('blocker_status_changed')
    expected_accounting = _accounting(source, policy_pointer, settings, assignments, unknown, sensitive)
    actual = normalized.get('field_accounting', [])
    if Counter(row.get('source_pointer') for row in actual) != Counter(row['source_pointer'] for row in expected_accounting):
        errors.append('source_field_accounting_not_closed')
    if not _json_equal(actual, expected_accounting):
        errors.append('source_field_accounting_changed')
    if normalized.get('execution_authorized') is not False or normalized.get('live_qualification') != 'not_run':
        errors.append('false_execution_authority')
    if files is not None:
        ff = _files(files)
        expected = {'key': key, 'pid': pid, 'tenant': tenant, 'digest': digest,
                    'desired': expected_desired, 'coverage': coverage}
        errors += _artifacts(ff, expected, normalized, partial, raw_digest)
        # Controlled canaries are supported explicitly; unsafe roots are also
        # checked for exact string values/unknown key names >= 12 characters.
        markers = set(context.get('forbidden_canaries', []))
        for pp, value in _walk(source):
            if _inside(pp, opaque_roots) and isinstance(value, str) and len(value) >= 12:
                markers.add(value)
        markers.update(pp.rsplit('/', 1)[-1].replace('~1', '/').replace('~0', '~') for pp in opaque_roots
                       if len(pp.rsplit('/', 1)[-1]) >= 12)
        public = _canonical(normalized) + '\n' + '\n'.join(ff.values())
        if any(marker in public for marker in markers if isinstance(marker, str) and marker):
            errors.append('restricted_raw_canary_exposed')
    return list(dict.fromkeys(errors))
