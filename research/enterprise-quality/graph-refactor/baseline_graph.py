"""Byte-backed typed review graph; no cloud calls or general query interpreter."""
from __future__ import annotations
import copy
import hashlib
import re
from uuid import UUID

from reference.core import normalize, PROVIDER, PROVIDER_VERSION, RESOURCE
from .io import AppError, digest, read_bytes, parse_json

QUERIES = ('policies', 'assignments', 'why-setting', 'impact', 'dependencies', 'placement')
FAMILY = 'settings_catalog_policy'
MAX_SOURCE_NODES = 10000
MAX_POLICIES = 64
MAX_PROJECTION_NODE_VISITS = 100000
MAX_PROJECTION_BYTES = 8 * 1024 * 1024
MAX_GRAPH_RELATION_CHECKS = 2000000


def identity(kind, *parts):
    """Structured scoped identity: labels are never identity keys."""
    return kind + ':' + digest(list(parts))


def _uuid(value):
    try:
        parsed = UUID(value)
        return str(parsed) if parsed.int else None
    except (ValueError, TypeError, AttributeError):
        return None


def _safe_selector(value):
    return (isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.\-/]{1,256}', value)
            and not value.startswith('/') and '..' not in value.split('/'))


def _dependency_context_digest(effective):
    values = effective.get('vars', {})
    fields = ('namespace', 'tenant', 'environment', 'stage')
    if not isinstance(values, dict) or any(key in values and not isinstance(values[key], str) for key in fields):
        return None
    return digest({key: values[key] for key in fields if key in values})


def _production_inventory_chain_complete(collection):
    """Validate captured continuation evidence without interpreting its query."""
    from urllib.parse import urlsplit
    from reference.validation import schema_errors
    if schema_errors('capture', collection) or collection['coverage'] != 'complete' or collection['reason'] is not None or not collection['pages']:
        return False
    expected = 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'
    seen = set()
    for page in collection['pages']:
        url = page['request_url']
        if url != expected or url in seen or page['method'] != 'GET' or page['http_status'] != 200:
            return False
        if not isinstance(url, str) or any(ord(c) < 32 or ord(c) >= 127 for c in url):
            return False
        try:
            parsed = urlsplit(url)
        except ValueError:
            return False
        if parsed.scheme != 'https' or parsed.netloc != 'graph.microsoft.com' or parsed.path != '/beta/deviceManagement/configurationPolicies' or parsed.fragment or parsed.username or parsed.password:
            return False
        seen.add(url)
        body = page['body']
        if set(body) - {'value','@odata.context','@odata.count','@odata.nextLink'} or not isinstance(body.get('value'), list):
            return False
        if '@odata.context' in body:
            context = body['@odata.context']
            if not isinstance(context, str) or len(context) > 2048 or any(ord(c) < 32 or 127 <= ord(c) < 160 for c in context):
                return False
        if '@odata.nextLink' in body:
            expected = body['@odata.nextLink']
            if not isinstance(expected, str) or not expected:
                return False
        else:
            expected = None
    return expected is None


def _policy_inventory_complete(collection, production=False):
    """Check inventory identities/counts independently of per-policy projection."""
    from reference.validation import capture_errors
    chain_complete = (_production_inventory_chain_complete(collection) if production else
                      not capture_errors(collection, 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'))
    if not chain_complete:
        return False
    identities = set()
    counts = []
    for page in collection['pages']:
        body = page['body']
        if '@odata.count' in body:
            count = body['@odata.count']
            if type(count) is not int or count < 0:
                return False
            counts.append(count)
        for record in body['value']:
            oid = _uuid(record.get('id')) if isinstance(record, dict) else None
            if oid is None or oid in identities:
                return False
            identities.add(oid)
    return all(count == len(identities) for count in counts)


def _check_projection_budget(bundle, byte_count):
    """Bound the existing whole-capture, per-policy projection algorithm."""
    def reject():
        raise AppError('graph_projection_budget',
                       'Graph projection exceeds its bounded work budget. Keep the complete capture intact; larger inventories require a qualified indexed or batching adapter.')
    nodes = 0
    stack = [iter([bundle])]
    while stack:
        try:
            value = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        nodes += 1
        if nodes > MAX_SOURCE_NODES:
            reject()
        if isinstance(value, dict):
            stack.append(iter(value.values()))
        elif isinstance(value, list):
            stack.append(iter(value))
    policies = set()
    collections = bundle.get('collections', [])
    for collection in collections if isinstance(collections, list) else []:
        if not isinstance(collection, dict) or collection.get('kind') != 'policies' or collection.get('owner_id') is not None:
            continue
        pages = collection.get('pages', [])
        for page in pages if isinstance(pages, list) else []:
            if not isinstance(page, dict) or page.get('http_status') != 200:
                continue
            body = page.get('body')
            rows = body.get('value', []) if isinstance(body, dict) else []
            for row in rows if isinstance(rows, list) else []:
                policy = _uuid(row.get('id')) if isinstance(row, dict) else None
                if policy:
                    policies.add(policy)
                    if len(policies) > MAX_POLICIES:
                        reject()
    multiplier = max(1, len(policies))
    if nodes * multiplier > MAX_PROJECTION_NODE_VISITS or byte_count * multiplier > MAX_PROJECTION_BYTES:
        reject()


def build_graph(input_path, context_path=None, atmos_root=None):
    raw_bytes = read_bytes(input_path)
    bundle = parse_json(raw_bytes)
    if not isinstance(bundle, dict) or not _uuid(bundle.get('tenant_id')):
        raise AppError('invalid_graph_source', 'Graph source requires a valid tenant UUID.')
    _check_projection_budget(bundle, len(raw_bytes))
    tenant_uuid = _uuid(bundle['tenant_id'])
    cloud_raw = bundle.get('cloud')
    cloud = cloud_raw if cloud_raw in ('public', 'usgovernment', 'dod', 'china') else 'unknown:' + digest(cloud_raw)
    source_hash = hashlib.sha256(raw_bytes).hexdigest()
    source_id = identity('source', source_hash)
    from .production import accepts as production_accepts
    production_capture = production_accepts(bundle)
    graph = {'schema_version': 'intune-review-graph/1.0', 'nodes': [], 'edges': [],
             'sources': [{'id': source_id, 'type': 'SourceArtifact', 'sha256': source_hash, 'kind': 'intune_capture'}],
             'coverage': [], 'issues': [], 'execution_authorized': False,
             'live_qualification': 'not_run', 'atmos': {'resolution_status': 'not_requested'}}
    if production_capture:
        graph['sources'][0]['adapter'] = 'plugin_graph_capture/1.0.0'
    nodes = {}
    def add(kind, key, **fields):
        row = {'id': key, 'type': kind, **fields}
        if key not in nodes:
            nodes[key] = row; graph['nodes'].append(row)
        return key
    edge_ids = set()
    def edge(source, predicate, target, origin=None, **fields):
        row = {'id': identity('edge', source, predicate, target, origin, fields), 'source': source,
               'predicate': predicate, 'target': target, 'status': 'observed', **fields}
        if origin is not None: row['origin'] = origin
        if row['id'] not in edge_ids:
            edge_ids.add(row['id'])
            graph['edges'].append(row)
    def origin(pointer):
        return {'artifact_id': source_id, 'pointer': pointer}
    tenant = add('Tenant', identity('tenant', cloud, tenant_uuid), cloud=cloud, tenant_uuid=tenant_uuid, status='observed', identity_assurance='source_asserted')
    collections = bundle.get('collections', [])
    if not isinstance(collections, list):
        raise AppError('invalid_graph_source', 'Graph source requires capture collections.')
    inventory = [(ci,c) for ci,c in enumerate(collections) if isinstance(c,dict) and c.get('kind')=='policies' and c.get('owner_id') is None]
    inventory_complete = len(inventory)==1 and _policy_inventory_complete(inventory[0][1], production_capture)
    graph['coverage'].append({'subject_id':tenant,'aspect':'policies','status':'complete' if inventory_complete else 'unknown',
                             'origin':origin('/collections/' + str(inventory[0][0]) if inventory else '/collections')})
    # Collect identities only from successful policy pages. No raw record survives.
    candidates = []
    candidate_ids = set()
    records = {}
    for ci, collection in enumerate(collections):
        if not isinstance(collection, dict): continue
        pages = collection.get('pages', [])
        if not isinstance(pages, list): continue
        for pi, page in enumerate(pages):
            if not isinstance(page, dict) or page.get('http_status') != 200: continue
            body = page.get('body', {})
            values = body.get('value', []) if isinstance(body, dict) else []
            if not isinstance(values, list): continue
            for ri, record in enumerate(values):
                if not isinstance(record, dict): continue
                pointer = f'/collections/{ci}/pages/{pi}/body/value/{ri}'
                kind = collection.get('kind')
                records.setdefault((kind, collection.get('owner_id')), []).append((record, pointer))
                if kind == 'policies' and collection.get('owner_id') is None:
                    oid = _uuid(record.get('id'))
                    if oid and oid not in candidate_ids:
                        candidate_ids.add(oid)
                        candidates.append(oid)
    for oid in candidates:
        policy_id = identity('policy', cloud, tenant_uuid, FAMILY, oid)
        try:
            if production_capture:
                from reference.validation import schema_errors
                from .production import normalize as production_normalize
                from .production_oracle import compare as production_compare
                if schema_errors('export-intake', bundle):
                    raise ValueError('invalid capture structure')
                # Local advisory labels satisfy the projection contract; no
                # placement context or target authentication is inferred here.
                review_context = {'schema_version': '1.0.0', 'tenant_id': tenant_uuid, 'cloud': cloud,
                                  'authorization': 'emit_only', 'source_is_synthetic': False,
                                  'selected_policy_id': oid, 'component': 'graph-review', 'stack': 'graph-review'}
                n = production_normalize(bundle, review_context)
                if production_compare(raw_bytes, n, context=review_context):
                    raise ValueError('independent capture preservation check failed')
            else:
                n = normalize(bundle, oid, tenant_uuid)
        except (AppError, ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError):
            graph['issues'].append({'code': 'capture_projection_failed', 'subject_id': policy_id})
            n = None
        matches = [(r,p) for r,p in records.get(('policies', None), []) if _uuid(r.get('id')) == oid]
        pointer = matches[0][1]
        safe_policy = n['observed']['policy'] if n else {}
        add('Policy', policy_id, cloud=cloud, tenant_uuid=tenant_uuid, tenant_id=tenant,
            family=FAMILY, object_uuid=oid, name=safe_policy.get('name'), status='observed', origin=origin(pointer))
        edge(policy_id, 'inTenant', tenant, origin(pointer))
        if not n:
            for kind in ('policies','settings','assignments'):
                graph['coverage'].append({'subject_id': policy_id, 'aspect': kind, 'status': 'unknown', 'origin': origin('/collections')})
            continue
        # Core blockers already replace unsupported and sensitive pointer names with opaque hashes.
        for blocker in n['blockers']:
            if blocker['code'] == 'unselected_collection_owner': continue
            blocker_pointer = 'opaque:' + blocker['path_ref'] if production_capture else blocker['source_pointer']
            graph['issues'].append({'subject_id': policy_id, 'code': blocker['code'], 'origin': origin(blocker_pointer)})
        for kind in ('policies', 'settings', 'assignments'):
            claims = [c for c in n['coverage'] if c['kind'] == kind and (production_capture or kind == 'policies' or c['owner_id'] == oid)]
            source_collections = [(i,c) for i,c in enumerate(collections) if isinstance(c, dict) and c.get('kind') == kind and c.get('owner_id') == (None if kind == 'policies' else oid)]
            claim_pointer = '/collections/' + str(source_collections[0][0]) if len(source_collections) == 1 else '/collections'
            graph['coverage'].append({'subject_id': policy_id, 'aspect': kind,
                'status': 'complete' if len(claims) == 1 and claims[0]['complete'] else 'unknown',
                'origin': origin(claim_pointer if production_capture else claims[0]['source_pointer'] if claims else '/collections')})
        for i, setting in enumerate(n['observed']['settings']):
            if not setting: continue
            source_rows = [r for r in records.get(('settings', oid), []) if r[0].get('id') == setting['id']]
            if len(source_rows) != 1 or sum(s.get('id')==setting['id'] for s in n['observed']['settings'] if s) != 1: continue
            inst = setting['settingInstance']
            if production_capture:
                from reference.validation import schema_errors, capability_errors
                projected_setting = {'id': setting['id'], 'settingInstance': inst}
                if schema_errors('observed-setting', projected_setting) or capability_errors([projected_setting]):
                    graph['issues'].append({'subject_id': policy_id, 'code': 'graph_setting_projection_unsupported',
                                            'origin': origin(source_rows[0][1])})
                    continue
            sid = identity('setting', policy_id, setting['id'])
            did = identity('setting-definition', cloud, inst['settingDefinitionId'])
            add('SettingDefinition', did, definition_id=inst['settingDefinitionId'], status='declared')
            add('SettingValue', sid, policy_id=policy_id, setting_id=setting['id'],
                definition_id=inst['settingDefinitionId'], value_digest=digest(inst), normalized_instance=copy.deepcopy(inst), mapping_status='supported',
                status='observed', origin=origin(source_rows[0][1]))
            mapping = add('ProviderMapping', identity('mapping', did, PROVIDER, PROVIDER_VERSION, RESOURCE),
                provider_source=PROVIDER, provider_version=PROVIDER_VERSION, resource=RESOURCE,
                qualification='production_capture_candidate_unqualified' if production_capture else 'bounded_synthetic_mapping', status='declared')
            edge(sid, 'ofPolicy', policy_id, origin(source_rows[0][1]))
            edge(sid, 'hasDefinition', did, origin(source_rows[0][1]))
            edge(did, 'mappedBy', mapping)
        ref_rows = {(r['kind'], r['id']): r for r in n['references']}
        for i, assignment in enumerate(n['observed']['assignments']):
            if not assignment: continue
            assignment_key = _uuid(assignment['id']) or assignment['id']
            source_rows = [r for r in records.get(('assignments', oid), []) if (_uuid(r[0].get('id')) or r[0].get('id')) == assignment_key]
            if len(source_rows) != 1 or sum((_uuid(a.get('id')) or a.get('id')) == assignment_key for a in n['observed']['assignments'] if a) != 1: continue
            target = assignment['target']
            aid = identity('assignment', cloud, tenant_uuid, FAMILY, oid, assignment_key)
            target_type = target['@odata.type'].removeprefix('#microsoft.graph.')
            group_uuid = _uuid(target['groupId'])
            group = add('Group', identity('group', cloud, tenant_uuid, group_uuid), cloud=cloud,
                tenant_uuid=tenant_uuid, object_uuid=group_uuid, status='referenced',
                reference_coverage=ref_rows.get(('group', target['groupId']), {}).get('coverage', 'unknown'))
            annotation = {}
            if production_capture:
                annotation['capture_adapter'] = 'plugin_graph_capture/1.0.0'
                if 'source' in assignment: annotation['assignment_source'] = assignment['source']
                if 'sourceId' in assignment: annotation['assignment_source_id'] = assignment['sourceId']
            add('Assignment', aid, policy_id=policy_id, assignment_uuid=assignment['id'], target_type=target_type,
                group_uuid=group_uuid, group_id=group, filter_mode=target['deviceAndAppManagementAssignmentFilterType'],
                filter_uuid=target.get('deviceAndAppManagementAssignmentFilterId'), status='observed', origin=origin(source_rows[0][1]), **annotation)
            edge(aid, 'ofPolicy', policy_id, origin(source_rows[0][1]))
            edge(aid, 'excludesGroup' if target_type == 'exclusionGroupAssignmentTarget' else 'includesGroup', group, origin(source_rows[0][1]))
            fid = _uuid(target.get('deviceAndAppManagementAssignmentFilterId'))
            if fid:
                filt = add('Filter', identity('filter', cloud, tenant_uuid, fid), cloud=cloud, tenant_uuid=tenant_uuid,
                    object_uuid=fid, status='referenced', reference_coverage=ref_rows.get(('filter', fid), {}).get('coverage', 'unknown'))
                edge(aid, 'usesFilter', filt, origin(source_rows[0][1]), filter_mode=target['deviceAndAppManagementAssignmentFilterType'])
    if context_path is not None:
        context_bytes = read_bytes(context_path); context = parse_json(context_bytes)
        if not isinstance(context, dict): raise AppError('invalid_graph_context', 'Graph context must be an object.')
        cs = identity('source', hashlib.sha256(context_bytes).hexdigest())
        graph['sources'].append({'id': cs, 'type': 'SourceArtifact', 'sha256': hashlib.sha256(context_bytes).hexdigest(), 'kind': 'placement_context'})
        selected = _uuid(context.get('selected_policy_id'))
        for policy in list(graph['nodes']):
            if policy['type'] != 'Policy' or policy['object_uuid'] != selected: continue
            # Names identify placement intent only; never authenticate a tenant or resolve a stack.
            def label(value):
                return value if isinstance(value,str) and 0 < len(value) <= 128 and all(c.isalnum() or c in '-_./' for c in value) else None
            placement = add('PlacementIntent', identity('placement', policy['id'], cs), policy_id=policy['id'],
                component=label(context.get('component')), stack_label=label(context.get('stack')),
                target_verification='not_established', status='declared', origin={'artifact_id': cs, 'pointer': ''})
            edge(placement, 'proposesPlacementOf', policy['id'], status='declared')
    if atmos_root is not None:
        from .atmos import inspect_atmos
        fragment = inspect_atmos(atmos_root)
        for key in ('nodes', 'edges', 'sources', 'coverage', 'issues'): graph[key].extend(fragment[key])
        graph['atmos'] = fragment['atmos']
        _project_effective_atmos(graph, atmos_root)
    graph['graph_digest'] = digest(graph)
    return graph


def _project_effective_atmos(graph, root):
    """Project bounded resolver evidence, never its raw effective configuration."""
    from pathlib import Path
    root = Path(root).resolve()
    if not (root / 'atmos.yaml').is_file():
        return
    from .repository import discover_repository, resolve_component
    discovery = discover_repository(root)
    if discovery.get('status') != 'discovered':
        graph['issues'].append({'code': 'atmos_effective_resolution_blocked', 'status': 'unknown'})
        return
    scope = identity('repository-scope', str(root))
    node_ids = {n['id'] for n in graph['nodes']}
    source_ids = {s['id'] for s in graph['sources']}
    source_by_path = {}
    def add(kind, key, **fields):
        if key not in node_ids:
            graph['nodes'].append({'id': key, 'type': kind, 'status': 'derived', **fields})
            node_ids.add(key)
        return key
    def edge(source, predicate, target, origin=None):
        fields = {'source': source, 'predicate': predicate, 'target': target, 'status': 'derived'}
        if origin is not None:
            fields['origin'] = origin
        graph['edges'].append({'id': identity('edge', fields), **fields})
    for source in discovery['sources']:
        sid = identity('source', scope, source['path'], source['sha256'])
        source_by_path[source['path']] = sid
        if sid not in source_ids:
            graph['sources'].append({'id': sid, 'type': 'SourceArtifact', 'kind': 'atmos_yaml',
                                    'path': source['path'], 'sha256': source['sha256']})
            source_ids.add(sid)
    def origin(provenance, fallback):
        evidence = provenance.get('winner', provenance) if isinstance(provenance, dict) else {}
        path = evidence.get('path', fallback)
        result = {'artifact_id': source_by_path[path], 'pointer': ''}
        if evidence.get('pointer'):
            # Keys beneath config and depends_on may themselves contain secrets.
            result['pointer'] = 'opaque:' + digest(evidence['pointer'])
        for key in ('line', 'column'):
            if isinstance(evidence.get(key), int) and evidence[key] > 0:
                result[key] = evidence[key]
        return result
    resolutions = {}
    blocked = False
    for stack in discovery['stacks']:
        # Manifest failures can leave no component rows to iterate. Retain the
        # failed stack in the overall denominator instead of declaring success.
        if stack.get('status') == 'blocked':
            blocked = True
            graph['issues'].append({'code': 'atmos_effective_resolution_blocked', 'status': 'unknown',
                                    'origin': origin({}, stack['manifest'])})
        for component in stack['components']:
            if component['kind'] != 'terraform':
                continue
            resolution = resolve_component(root, stack['stack'], component['name'])
            if resolution.get('status') != 'resolved':
                blocked = True
                graph['issues'].append({'code': 'atmos_effective_resolution_blocked', 'status': 'unknown',
                                        'origin': origin({}, stack['manifest'])})
                continue
            if resolution.get('abstract'):
                continue
            # A filesystem edit between calls cannot borrow the discovery sources.
            if resolution['source_fingerprint'] != discovery['source_fingerprint']:
                blocked = True
                graph['issues'].append({'code': 'atmos_effective_sources_changed', 'status': 'unknown'})
                continue
            physical = stack['stack']
            stack_id = add('EffectiveStack', identity('effective-stack', scope, physical),
                           repository_scope_id=scope, physical_stack=physical,
                           resolution_status='resolved', origin=origin({}, stack['manifest']))
            instance = add('ComponentInstance', identity('effective-component-instance', scope, physical, component['kind'], component['name']),
                           repository_scope_id=scope, stack_id=stack_id, name=component['name'],
                           engine_type=component['kind'], resolution_status='resolved', origin=origin({}, stack['manifest']))
            config_id = add('EffectiveConfiguration', identity('effective-configuration', instance, resolution['selection_fingerprint']),
                            component_id=instance, adapter='bounded-atmos/1.0',
                            source_fingerprint=resolution['source_fingerprint'],
                            selection_fingerprint=resolution['selection_fingerprint'],
                            config_digest=digest(resolution['effective']), resolution_status='resolved',
                            dependency_context_digest=_dependency_context_digest(resolution['effective']),
                            origin=origin({}, stack['manifest']))
            definition = add('ComponentDefinition', identity('effective-component-definition', scope, component['kind'], resolution['implementation']),
                             implementation_path=resolution['implementation'], engine_type=component['kind'], repository_scope_id=scope,
                             implementation_presence='present' if resolution['implementation_exists'] else 'missing',
                             implementation_directory=resolution['implementation_path'],
                             origin=origin(resolution.get('provenance', {}).get('/metadata/component', {}), stack['manifest']))
            edge(instance, 'belongsToEffectiveStack', stack_id)
            edge(instance, 'hasEffectiveConfiguration', config_id)
            edge(config_id, 'usesImplementation', definition)
            for source in resolution['sources']:
                source_id = source_by_path[source['path']]
                evidence_id = add('ResolutionSource', identity('resolution-source', config_id, source_id),
                                  configuration_id=config_id, source_artifact_id=source_id,
                                  origin={'artifact_id': source_id, 'pointer': ''})
                edge(config_id, 'derivedFrom', evidence_id)
            graph['coverage'].append({'subject_id': instance, 'aspect': 'atmos_effective_resolution',
                                      'status': 'complete', 'origin': origin({}, stack['manifest'])})
            resolutions[(physical, component['name'])] = (instance, config_id, resolution, stack['manifest'])
    for (physical, name), (instance, config_id, resolution, manifest) in resolutions.items():
        settings = resolution['effective'].get('settings', {})
        dependencies = settings.get('depends_on', {}) if isinstance(settings, dict) else {}
        if not isinstance(dependencies, dict):
            evidence = resolution.get('provenance', {}).get('/settings/depends_on', {})
            dependency = add('EffectiveDependency', identity('effective-dependency-invalid-collection', config_id),
                             consumer_id=instance, configuration_id=config_id,
                             component_selector=None, stack_selector=None,
                             selector_scope='unresolved_selector', context_relation='unknown',
                             resolution_status='unknown', adapter='settings.depends_on/literal',
                             origin=origin(evidence, manifest))
            edge(config_id, 'hasEffectiveDependency', dependency)
            graph['issues'].append({'code': 'atmos_dependency_collection_unresolved', 'subject_id': dependency,
                                    'status': 'unknown', 'origin': origin(evidence, manifest)})
            blocked = True
            continue
        for key, selector in dependencies.items():
            literal = isinstance(selector, dict) and set(selector) <= {'component', 'stack'}
            component_name = selector.get('component') if literal else None
            stack_name = selector.get('stack') if literal else None
            if not _safe_selector(component_name) or (stack_name is not None and not _safe_selector(stack_name)):
                component_name = stack_name = None
            implicit = literal and 'stack' not in selector and component_name is not None
            target = resolutions.get((physical, component_name)) if implicit else None
            context_relation = 'unknown'
            if target:
                consumer_context = _dependency_context_digest(resolution['effective'])
                target_context = _dependency_context_digest(target[2]['effective'])
                if consumer_context is not None and target_context is not None:
                    context_relation = 'equal' if consumer_context == target_context else 'different'
                if context_relation != 'equal':
                    target = None
            pointer = '/settings/depends_on/' + str(key).replace('~', '~0').replace('/', '~1')
            evidence = resolution.get('provenance', {}).get(pointer + '/component',
                       resolution.get('provenance', {}).get(pointer, {}))
            dependency = add('EffectiveDependency', identity('effective-dependency', config_id, digest(key)),
                             consumer_id=instance, configuration_id=config_id,
                             component_selector=component_name, stack_selector=stack_name,
                             selector_scope='implicit_same_physical_stack' if implicit else 'unresolved_selector',
                             context_relation=context_relation,
                             resolution_status='resolved' if target else 'unknown',
                             adapter='settings.depends_on/literal', origin=origin(evidence, manifest))
            edge(config_id, 'hasEffectiveDependency', dependency)
            if target:
                edge(dependency, 'dependsOn', target[0], origin(evidence, manifest))
            else:
                reason = ('atmos_dependency_selector_unresolved' if not implicit else
                          'atmos_dependency_context_unresolved' if context_relation != 'equal' and (physical, component_name) in resolutions else
                          'atmos_dependency_target_unresolved')
                graph['issues'].append({'code': reason, 'subject_id': dependency, 'status': 'unknown',
                                        'origin': origin(evidence, manifest)})
    if resolutions:
        graph['atmos'] = {'adapter': 'bounded-atmos/1.0', 'resolution_status': 'partial' if blocked else 'resolved',
                          'effective_config': 'safe_structural_projection', 'tenant_verification': 'not_established',
                          'execution_order': 'not_established'}


# Closed review projection: adding arbitrary source payload fields is not accepted.
_NODE_FIELDS = {
    'Tenant': 'cloud tenant_uuid identity_assurance',
    'Policy': 'cloud tenant_uuid tenant_id family object_uuid name',
    'SettingDefinition': 'definition_id',
    'SettingValue': 'policy_id setting_id definition_id value_digest normalized_instance mapping_status',
    'ProviderMapping': 'provider_source provider_version resource qualification',
    'Group': 'cloud tenant_uuid object_uuid reference_coverage',
    'Filter': 'cloud tenant_uuid object_uuid reference_coverage',
    'Assignment': 'policy_id assignment_uuid target_type group_uuid group_id filter_mode filter_uuid',
    'PlacementIntent': 'policy_id component stack_label target_verification',
    'ManifestDeclaration': 'source_artifact_id',
    'StackDeclaration': 'manifest_id stack_identity',
    'ComponentInstance': 'repository_scope_id stack_id name engine_type resolution_status',
    'ComponentDefinition': 'implementation_path engine_type repository_scope_id',
    'ImportOccurrence': 'manifest_id order literal_path resolution_status',
    'DependencyDeclaration': 'consumer_id component_selector stack_selector adapter resolution_status',
    'ConfigAssignment': 'component_id section key_digest',
    'EffectiveStack': 'repository_scope_id physical_stack resolution_status',
    'EffectiveConfiguration': 'component_id adapter source_fingerprint selection_fingerprint config_digest resolution_status dependency_context_digest',
    'ResolutionSource': 'configuration_id source_artifact_id',
    'EffectiveDependency': 'consumer_id configuration_id component_selector stack_selector resolution_status adapter selector_scope context_relation',
}
_NODE_OPTIONAL_FIELDS = {'ComponentDefinition': {'implementation_presence', 'implementation_directory'},
                         'Assignment': {'capture_adapter', 'assignment_source', 'assignment_source_id'}}
_PREDICATES = {'inTenant','ofPolicy','hasDefinition','mappedBy','includesGroup','excludesGroup','usesFilter',
               'proposesPlacementOf','isDeclaredBy','belongsToStackDeclaration','usesImplementation',
               'hasImport','resolvesToManifest','imports','inheritsConfigurationFrom','hasDependencyDeclaration',
               'declaresDependencyOn','hasConfigDeclaration','belongsToEffectiveStack','hasEffectiveConfiguration',
               'derivedFrom','hasEffectiveDependency','dependsOn'}
_EDGE_TYPES = {
    'inTenant': ({'Policy'}, {'Tenant'}),
    'ofPolicy': ({'SettingValue', 'Assignment'}, {'Policy'}),
    'hasDefinition': ({'SettingValue'}, {'SettingDefinition'}),
    'mappedBy': ({'SettingDefinition'}, {'ProviderMapping'}),
    'includesGroup': ({'Assignment'}, {'Group'}),
    'excludesGroup': ({'Assignment'}, {'Group'}),
    'usesFilter': ({'Assignment'}, {'Filter'}),
    'proposesPlacementOf': ({'PlacementIntent'}, {'Policy'}),
    'isDeclaredBy': ({'StackDeclaration'}, {'ManifestDeclaration'}),
    'belongsToStackDeclaration': ({'ComponentInstance'}, {'StackDeclaration'}),
    'usesImplementation': ({'ComponentInstance', 'EffectiveConfiguration'}, {'ComponentDefinition'}),
    'hasImport': ({'ManifestDeclaration'}, {'ImportOccurrence'}),
    'resolvesToManifest': ({'ImportOccurrence'}, {'ManifestDeclaration'}),
    'imports': ({'ManifestDeclaration'}, {'ManifestDeclaration'}),
    'inheritsConfigurationFrom': ({'ComponentInstance'}, {'ComponentInstance'}),
    'hasDependencyDeclaration': ({'ComponentInstance'}, {'DependencyDeclaration'}),
    'declaresDependencyOn': ({'ComponentInstance'}, {'ComponentInstance'}),
    'hasConfigDeclaration': ({'ComponentInstance'}, {'ConfigAssignment'}),
    'belongsToEffectiveStack': ({'ComponentInstance'}, {'EffectiveStack'}),
    'hasEffectiveConfiguration': ({'ComponentInstance'}, {'EffectiveConfiguration'}),
    'derivedFrom': ({'EffectiveConfiguration'}, {'ResolutionSource'}),
    'hasEffectiveDependency': ({'EffectiveConfiguration'}, {'EffectiveDependency'}),
    'dependsOn': ({'EffectiveDependency'}, {'ComponentInstance'}),
}


def _validate_graph(graph):
    """Check integrity and the closed safe shape, not provenance authenticity."""
    import re
    from reference.validation import schema_errors, capability_errors
    def fail():
        raise AppError('invalid_graph', 'Graph integrity or safe review structure is invalid.')
    def closed(row, required, allowed):
        if not isinstance(row,dict) or not required <= row.keys() or not row.keys() <= allowed: fail()
    def scalar_fields(row, exceptions=()):
        for key,value in row.items():
            if key in exceptions: continue
            if not isinstance(value,(str,int,type(None))) or isinstance(value,bool): fail()
            if isinstance(value,str) and (len(value)>4096 or any(ord(c)<32 or ord(c)==127 for c in value)): fail()
    if set(graph) != {'schema_version','nodes','edges','sources','coverage','issues','execution_authorized','live_qualification','atmos','graph_digest'}: fail()
    if graph.get('execution_authorized') is not False or graph.get('live_qualification') != 'not_run': fail()
    if any(not isinstance(graph[k],list) or len(graph[k]) > 100000 for k in ('nodes','edges','sources','coverage','issues')): fail()
    if len(graph['nodes']) * (len(graph['edges']) + len(graph['coverage']) + len(graph['sources'])) > MAX_GRAPH_RELATION_CHECKS:
        raise AppError('graph_query_budget', 'Graph exceeds the bounded relationship-validation work budget; the complete graph was not queried.')
    try:
        if graph['graph_digest'] != digest({k:v for k,v in graph.items() if k != 'graph_digest'}): fail()
    except (ValueError, TypeError, RecursionError): fail()
    node_ids = set(); source_ids = set()
    for source in graph['sources']:
        closed(source, {'id','type','sha256','kind'}, {'id','type','sha256','kind','path','adapter'})
        if source['type'] != 'SourceArtifact' or not isinstance(source['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',source['sha256']): fail()
        if source['kind'] not in ('intune_capture','placement_context','atmos_yaml') or source['id'] in source_ids: fail()
        if 'adapter' in source and (source['kind'] != 'intune_capture' or source['adapter'] != 'plugin_graph_capture/1.0.0'): fail()
        scalar_fields(source)
        source_ids.add(source['id'])
    def check_origin(row):
        if 'origin' not in row: return
        o = row['origin']; closed(o, {'artifact_id','pointer'}, {'artifact_id','pointer','line','column'})
        if o['artifact_id'] not in source_ids or not isinstance(o['pointer'],str) or len(o['pointer']) > 4096: fail()
        if o['pointer'] and not o['pointer'].startswith(('/', 'opaque:')): fail()
        if any(ord(c)<32 or ord(c)==127 for c in o['pointer']): fail()
        if any(not isinstance(o[k],int) or isinstance(o[k],bool) or o[k]<1 for k in ('line','column') if k in o): fail()
    for node in graph['nodes']:
        if not isinstance(node,dict) or node.get('type') not in _NODE_FIELDS: fail()
        closed(node, {'id','type','status'} | set(_NODE_FIELDS[node['type']].split()), {'id','type','status','origin'} | set(_NODE_FIELDS[node['type']].split()) | _NODE_OPTIONAL_FIELDS.get(node['type'], set()))
        if not isinstance(node['id'],str) or node['id'] in node_ids: fail()
        node_ids.add(node['id']); check_origin(node)
        if node['status'] not in ('observed','declared','referenced','derived'): fail()
        for key,value in node.items():
            if key in ('origin','normalized_instance'): continue
            if not isinstance(value,(str,int,type(None))) or isinstance(value,bool): fail()
            if isinstance(value,str) and (len(value)>4096 or any(ord(c)<32 or ord(c)==127 for c in value)): fail()
        if node['type'] == 'SettingValue':
            record = {'id':node.get('setting_id'),'settingInstance':node.get('normalized_instance')}
            if schema_errors('observed-setting',record) or capability_errors([record]): fail()
            if node['value_digest'] != digest(node['normalized_instance']): fail()
        if node['type'] == 'Assignment':
            if any(key in node for key in ('assignment_source','assignment_source_id','capture_adapter')):
                if node.get('capture_adapter') != 'plugin_graph_capture/1.0.0' or node.get('assignment_source', 'direct') != 'direct' or node.get('assignment_source_id') not in (None, ''): fail()
                source = next((s for s in graph['sources'] if s['id'] == node.get('origin', {}).get('artifact_id')), {})
                if source.get('adapter') != node['capture_adapter']: fail()
    for edge in graph['edges']:
        closed(edge, {'id','source','predicate','target','status'}, {'id','source','predicate','target','status','origin','filter_mode','order','resolution','qualification'})
        if edge['source'] not in node_ids or edge['target'] not in node_ids or edge['predicate'] not in _PREDICATES or edge['status'] not in ('observed','declared','derived'): fail()
        scalar_fields(edge, ('origin',))
        check_origin(edge)
    for claim in graph['coverage']:
        closed(claim, {'subject_id','aspect','status','origin'}, {'subject_id','aspect','status','origin'})
        if claim['subject_id'] not in node_ids or claim['status'] not in ('complete','unknown') or claim['aspect'] not in ('policies','settings','assignments','atmos_effective_resolution'): fail()
        scalar_fields(claim, ('origin',))
        check_origin(claim)
    for issue in graph['issues']:
        closed(issue, {'code'}, {'code','subject_id','origin','status'})
        if not isinstance(issue['code'],str) or not re.fullmatch('[a-z][a-z0-9_]{0,100}',issue['code']): fail()
        scalar_fields(issue, ('origin',))
        check_origin(issue)
    closed(graph['atmos'], {'resolution_status'}, {'resolution_status','adapter','effective_config','tenant_verification','execution_order'})
    scalar_fields(graph['atmos'])
    if graph['atmos']['resolution_status'] not in ('unknown','not_requested','partial','resolved'): fail()
    # A recomputable digest does not make contradictory resolution claims valid.
    by_id = {node['id']: node for node in graph['nodes']}
    sources_by_id = {source['id']: source for source in graph['sources']}
    for edge in graph['edges']:
        source_types, target_types = _EDGE_TYPES[edge['predicate']]
        if by_id[edge['source']]['type'] not in source_types or by_id[edge['target']]['type'] not in target_types:
            fail()
    effective_types = {'EffectiveStack','EffectiveConfiguration','ResolutionSource','EffectiveDependency'}
    outgoing = {}
    for relation in graph['edges']:
        outgoing.setdefault((relation['source'], relation['predicate']), []).append(relation)
    def targets(node_id, predicate):
        return [by_id[e['target']] for e in outgoing.get((node_id, predicate), [])]
    def exact_target(node_id, predicate, target_id):
        if [n['id'] for n in targets(node_id, predicate)] != [target_id]: fail()
    def hashed(value):
        return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)
    effective_count = 0
    for node in graph['nodes']:
        kind = node['type']
        if kind == 'Policy':
            tenant = by_id.get(node['tenant_id'], {})
            if tenant.get('type') != 'Tenant' or any(tenant.get(k) != node[k] for k in ('cloud','tenant_uuid')): fail()
            exact_target(node['id'], 'inTenant', node['tenant_id'])
        elif kind == 'SettingValue':
            if by_id.get(node['policy_id'], {}).get('type') != 'Policy': fail()
            exact_target(node['id'], 'ofPolicy', node['policy_id'])
            definitions = targets(node['id'], 'hasDefinition')
            if len(definitions) != 1 or definitions[0]['definition_id'] != node['definition_id'] or node['normalized_instance']['settingDefinitionId'] != node['definition_id']: fail()
        elif kind == 'Assignment':
            policy = by_id.get(node['policy_id'], {})
            group = by_id.get(node['group_id'], {})
            if policy.get('type') != 'Policy' or group.get('type') != 'Group': fail()
            # Graph assignment keys can be opaque strings in production captures.
            if not isinstance(node['assignment_uuid'], str) or not node['assignment_uuid'] or _uuid(node['group_uuid']) is None: fail()
            if _uuid(group['object_uuid']) != _uuid(node['group_uuid']) or any(group[k] != policy[k] for k in ('cloud','tenant_uuid')): fail()
            exact_target(node['id'], 'ofPolicy', node['policy_id'])
            if node['target_type'] not in ('groupAssignmentTarget','exclusionGroupAssignmentTarget'): fail()
            if node['target_type'] == 'exclusionGroupAssignmentTarget' and node['filter_mode'] != 'none': fail()
            predicate = 'excludesGroup' if node['target_type'] == 'exclusionGroupAssignmentTarget' else 'includesGroup'
            exact_target(node['id'], predicate, node['group_id'])
            if targets(node['id'], 'includesGroup' if predicate == 'excludesGroup' else 'excludesGroup'): fail()
            filters = targets(node['id'], 'usesFilter')
            if node['filter_mode'] == 'none':
                if node['filter_uuid'] is not None or filters: fail()
            elif node['filter_mode'] in ('include','exclude'):
                if len(filters) != 1 or _uuid(node['filter_uuid']) is None or _uuid(filters[0]['object_uuid']) != _uuid(node['filter_uuid']): fail()
                if any(filters[0][k] != policy[k] for k in ('cloud','tenant_uuid')): fail()
                filter_edges = outgoing.get((node['id'], 'usesFilter'), [])
                if any(e.get('filter_mode') != node['filter_mode'] for e in filter_edges): fail()
            else: fail()
        if kind in effective_types and node['status'] != 'derived': fail()
        if node['status'] == 'derived' and kind not in effective_types | {'ComponentInstance','ComponentDefinition'}: fail()
        if kind == 'EffectiveStack':
            if node['resolution_status'] != 'resolved' or not _safe_selector(node['physical_stack']): fail()
            if node['id'] != identity('effective-stack', node['repository_scope_id'], node['physical_stack']): fail()
        elif kind == 'ComponentDefinition' and node['status'] == 'derived':
            if node.get('implementation_presence') not in ('present','missing') or not _safe_selector(node.get('implementation_directory')): fail()
            if not _safe_selector(node['implementation_path']): fail()
            if node['id'] != identity('effective-component-definition', node['repository_scope_id'], node['engine_type'], node['implementation_path']): fail()
        elif kind == 'ComponentInstance':
            if node['resolution_status'] not in ('unknown','resolved'): fail()
            stack = by_id.get(node['stack_id'], {})
            if node['resolution_status'] == 'resolved':
                effective_count += 1
                if node['status'] != 'derived' or stack.get('type') != 'EffectiveStack' or stack['repository_scope_id'] != node['repository_scope_id']: fail()
                if not _safe_selector(node['name']) or node['engine_type'] != 'terraform': fail()
                if node['id'] != identity('effective-component-instance', node['repository_scope_id'], stack['physical_stack'], node['engine_type'], node['name']): fail()
                exact_target(node['id'], 'belongsToEffectiveStack', stack['id'])
                configs = targets(node['id'], 'hasEffectiveConfiguration')
                if len(configs) != 1 or configs[0]['type'] != 'EffectiveConfiguration' or configs[0]['component_id'] != node['id']: fail()
                coverage = [c for c in graph['coverage'] if c['subject_id'] == node['id'] and c['aspect'] == 'atmos_effective_resolution']
                if len(coverage) != 1 or coverage[0]['status'] != 'complete': fail()
            elif node['status'] != 'declared' or stack.get('type') != 'StackDeclaration' or targets(node['id'], 'hasEffectiveConfiguration'): fail()
        elif kind == 'EffectiveConfiguration':
            component = by_id.get(node['component_id'], {})
            if component.get('type') != 'ComponentInstance' or component.get('resolution_status') != 'resolved': fail()
            if node['resolution_status'] != 'resolved' or node['adapter'] != 'bounded-atmos/1.0': fail()
            if not all(hashed(node[key]) for key in ('source_fingerprint','selection_fingerprint','config_digest')): fail()
            if node['dependency_context_digest'] is not None and not hashed(node['dependency_context_digest']): fail()
            if node['id'] != identity('effective-configuration', node['component_id'], node['selection_fingerprint']): fail()
            definitions = targets(node['id'], 'usesImplementation')
            if len(definitions) != 1 or definitions[0]['type'] != 'ComponentDefinition': fail()
            if definitions[0]['repository_scope_id'] != component['repository_scope_id'] or definitions[0]['engine_type'] != component['engine_type']: fail()
            evidence = targets(node['id'], 'derivedFrom')
            if not evidence or any(n['type'] != 'ResolutionSource' or n['configuration_id'] != node['id'] for n in evidence): fail()
            source_inventory = []
            for item in evidence:
                artifact = sources_by_id.get(item['source_artifact_id'], {})
                if artifact.get('kind') != 'atmos_yaml' or not isinstance(artifact.get('path'), str): fail()
                source_inventory.append({'path': artifact['path'], 'sha256': artifact['sha256']})
            if len({item['path'] for item in source_inventory}) != len(source_inventory): fail()
            if node['source_fingerprint'] != digest({'adapter': 'atmos-literal/1.0', 'sources': sorted(source_inventory, key=lambda item: item['path'])}): fail()
            stack = by_id[component['stack_id']]
            if node['selection_fingerprint'] != digest([node['source_fingerprint'], stack['physical_stack'], component['engine_type'], component['name'],
                                                       definitions[0]['implementation_directory'], definitions[0]['implementation_presence'] == 'present']): fail()
            exact_target(component['id'], 'hasEffectiveConfiguration', node['id'])
        elif kind == 'ResolutionSource':
            if node['source_artifact_id'] not in source_ids or by_id.get(node['configuration_id'], {}).get('type') != 'EffectiveConfiguration': fail()
            if node.get('origin', {}).get('artifact_id') != node['source_artifact_id']: fail()
            if node['id'] != identity('resolution-source', node['configuration_id'], node['source_artifact_id']): fail()
            if node['id'] not in [n['id'] for n in targets(node['configuration_id'], 'derivedFrom')]: fail()
        elif kind == 'EffectiveDependency':
            config = by_id.get(node['configuration_id'], {})
            if config.get('type') != 'EffectiveConfiguration' or config['component_id'] != node['consumer_id']: fail()
            if node['adapter'] != 'settings.depends_on/literal' or node['resolution_status'] not in ('unknown','resolved'): fail()
            if node['selector_scope'] not in ('implicit_same_physical_stack','unresolved_selector') or node['context_relation'] not in ('equal','different','unknown'): fail()
            if any(node[k] is not None and not _safe_selector(node[k]) for k in ('component_selector','stack_selector')): fail()
            deps = targets(node['id'], 'dependsOn')
            if node['resolution_status'] == 'resolved':
                if len(deps) != 1 or deps[0]['type'] != 'ComponentInstance' or deps[0]['resolution_status'] != 'resolved': fail()
                target_stack = by_id[deps[0]['stack_id']]
                consumer = by_id[node['consumer_id']]
                if node['selector_scope'] != 'implicit_same_physical_stack' or node['stack_selector'] is not None or node['context_relation'] != 'equal': fail()
                if deps[0]['name'] != node['component_selector'] or target_stack['id'] != consumer['stack_id']: fail()
                target_config = targets(deps[0]['id'], 'hasEffectiveConfiguration')
                if len(target_config) != 1 or config['dependency_context_digest'] is None or config['dependency_context_digest'] != target_config[0]['dependency_context_digest']: fail()
            elif deps: fail()
            if node['id'] not in [n['id'] for n in targets(config['id'], 'hasEffectiveDependency')]: fail()
    edge_types = {'belongsToEffectiveStack': ({'ComponentInstance'}, {'EffectiveStack'}),
                  'hasEffectiveConfiguration': ({'ComponentInstance'}, {'EffectiveConfiguration'}),
                  'derivedFrom': ({'EffectiveConfiguration'}, {'ResolutionSource'}),
                  'hasEffectiveDependency': ({'EffectiveConfiguration'}, {'EffectiveDependency'}),
                  'dependsOn': ({'EffectiveDependency'}, {'ComponentInstance'})}
    for edge in graph['edges']:
        if edge['predicate'] in edge_types:
            source_type, target_type = edge_types[edge['predicate']]
            if edge['status'] != 'derived' or by_id[edge['source']]['type'] not in source_type or by_id[edge['target']]['type'] not in target_type: fail()
        elif edge['status'] == 'derived' or by_id[edge['source']]['status'] == 'derived' or by_id[edge['target']]['status'] == 'derived':
            if edge['status'] != 'derived': fail()
            if edge['predicate'] != 'usesImplementation' or by_id[edge['source']]['type'] != 'EffectiveConfiguration' or by_id[edge['target']]['type'] != 'ComponentDefinition': fail()
    if (graph['atmos']['resolution_status'] in ('resolved','partial')) != bool(effective_count): fail()
    if effective_count and (graph['atmos'].get('adapter') != 'bounded-atmos/1.0' or graph['atmos'].get('tenant_verification') != 'not_established' or graph['atmos'].get('execution_order') != 'not_established'): fail()


def query_graph(graph, query, subject=None):
    """Fixed constructive reads, returning detached safe graph projections."""
    if query not in QUERIES:
        raise AppError('unsupported_query', 'Select a documented graph query.')
    if not isinstance(graph, dict) or graph.get('schema_version') != 'intune-review-graph/1.0':
        raise AppError('invalid_graph', 'Expected a versioned Intune review graph.')
    try:
        _validate_graph(graph)
    except (KeyError, TypeError, AttributeError, RecursionError):
        raise AppError('invalid_graph', 'Graph integrity or safe review structure is invalid.') from None
    if subject is not None and not isinstance(subject, str):
        raise AppError('invalid_subject', 'Graph subject must be an exact node ID or policy UUID.')
    nodes = graph['nodes']; edges = graph['edges']
    selected = next((n for n in nodes if n['id'] == subject), None)
    if selected is None and subject is not None:
        matches = [n for n in nodes if n['type'] == 'Policy' and n['object_uuid'] == subject]
        if len(matches) == 1: selected = matches[0]
    if subject is not None and selected is None:
        raise AppError('unknown_subject', 'Graph subject was not found or was ambiguous.')
    sid = selected['id'] if selected else None
    result = {'query': query, 'subject_id': sid, 'nodes': [], 'edges': [], 'coverage': [], 'sources': [], 'execution_authorized': False}
    if query == 'policies':
        result['nodes'] = [n for n in nodes if n['type'] == 'Policy' and (sid is None or n['id'] == sid)]
        result['coverage'] = [c for c in graph['coverage'] if c['aspect']=='policies' and (sid is None or c['subject_id']==sid)]
    elif query == 'assignments':
        result['nodes'] = [n for n in nodes if n['type'] == 'Assignment' and (sid is None or n['policy_id'] == sid)]
        result['coverage'] = [c for c in graph['coverage'] if c['aspect'] == 'assignments' and (sid is None or c['subject_id'] == sid)]
    elif query == 'why-setting':
        if selected is None or selected['type'] != 'SettingValue':
            raise AppError('invalid_subject', 'why-setting requires a SettingValue node ID.')
        result['nodes'] = [selected]
        result['edges'] = [e for e in edges if e['source'] == sid]
        definitions = {e['target'] for e in result['edges'] if e['predicate'] == 'hasDefinition'}
        result['edges'] += [e for e in edges if e['source'] in definitions and e['predicate'] == 'mappedBy']
        target_ids = {e['target'] for e in result['edges']}
        result['nodes'] += [n for n in nodes if n['id'] in target_ids and n['type'] in ('SettingDefinition', 'ProviderMapping')]
    elif query == 'dependencies':
        result['edges'] = [e for e in edges if e['predicate'] == 'declaresDependencyOn' and (sid is None or e['source'] == sid or e['target'] == sid)]
        declared_consumers = {e['source'] for e in result['edges']}
        declaration_ids = {n['id'] for n in nodes if n['type'] == 'DependencyDeclaration' and
                           (sid is None or n['consumer_id'] == sid or n['consumer_id'] in declared_consumers)}
        result['edges'] += [e for e in edges if e['predicate'] == 'hasDependencyDeclaration' and e['target'] in declaration_ids]
        dependency_ids = {n['id'] for n in nodes if n['type'] == 'EffectiveDependency' and
                          (sid is None or n['consumer_id'] == sid or any(e['source'] == n['id'] and e['predicate'] == 'dependsOn' and e['target'] == sid for e in edges))}
        config_ids = {n['configuration_id'] for n in nodes if n['id'] in dependency_ids}
        result['edges'] += [e for e in edges if
                            (e['predicate'] == 'dependsOn' and e['source'] in dependency_ids) or
                            (e['predicate'] == 'hasEffectiveDependency' and e['target'] in dependency_ids) or
                            (e['predicate'] == 'hasEffectiveConfiguration' and e['target'] in config_ids)]
        ids = {e[k] for e in result['edges'] for k in ('source','target')}
        result['nodes'] = [n for n in nodes if n['id'] in ids]
        result['execution_order'] = 'not_established'
        result['completeness'] = 'unknown'
        artifacts = {n.get('origin', {}).get('artifact_id') for n in result['nodes']}
        result['issues'] = [issue for issue in graph['issues'] if
                            ('dependency' in issue['code'] or issue['code'].startswith('atmos_effective_')) and
                            (sid is None or issue.get('subject_id') in ids or issue.get('origin', {}).get('artifact_id') in artifacts)]
    elif query == 'placement':
        if selected and selected['type'] == 'ComponentInstance':
            relations = [e for e in edges if e['source'] == sid and e['predicate'] in ('usesImplementation','belongsToStackDeclaration','belongsToEffectiveStack','hasEffectiveConfiguration')]
            config_ids = {e['target'] for e in relations if e['predicate'] == 'hasEffectiveConfiguration'}
            relations += [e for e in edges if e['source'] in config_ids and e['predicate'] in ('usesImplementation','derivedFrom')]
            related = {e['target'] for e in relations} | {sid}
            result['nodes'] = [n for n in nodes if n['id'] in related]
            result['edges'] = relations
            result['stack_resolution'] = selected['resolution_status']
            definitions = [n for n in result['nodes'] if n['type'] == 'ComponentDefinition' and n['status'] == 'derived']
            if definitions:
                result['implementation_presence'] = definitions[0]['implementation_presence']
        else:
            result['nodes'] = [n for n in nodes if n['type'] == 'PlacementIntent' and (sid is None or n['policy_id'] == sid)]
        result['target_verification'] = 'not_established'
    elif query == 'impact':
        if selected is None: raise AppError('invalid_subject', 'impact requires an exact graph subject.')
        # Reverse relation closure identifies declared consumers, never an execution schedule.
        visited = {sid}; frontier = [sid]
        while frontier:
            current = frontier.pop()
            for e in edges:
                if e['target'] == current and e['source'] not in visited:
                    visited.add(e['source']); frontier.append(e['source'])
        result['nodes'] = [n for n in nodes if n['id'] in visited]
        result['edges'] = [e for e in edges if e['source'] in visited and e['target'] in visited]
        result['completeness'] = 'unknown'; result['execution_order'] = 'not_established'
    if not result['edges']:
        ids = {n['id'] for n in result['nodes']}
        result['edges'] = [e for e in edges if e['source'] in ids]
    if query in ('policies', 'assignments', 'why-setting'):
        policy_ids = ({selected['policy_id']} if query == 'why-setting' else
                      {n['id'] for n in nodes if n['type'] == 'Policy' and (sid is None or n['id'] == sid)})
        result['issues'] = [issue for issue in graph['issues'] if issue.get('subject_id') in policy_ids]
    artifact_ids = {n.get('origin', {}).get('artifact_id') for n in result['nodes']}
    artifact_ids.update(e.get('origin', {}).get('artifact_id') for e in result['edges'])
    artifact_ids.update(c.get('origin', {}).get('artifact_id') for c in result['coverage'])
    artifact_ids.update(i.get('origin', {}).get('artifact_id') for i in result.get('issues', []))
    result['sources'] = [s for s in graph['sources'] if s['id'] in artifact_ids]
    if query == 'impact': result['issues'] = graph['issues']
    return copy.deepcopy(result)
