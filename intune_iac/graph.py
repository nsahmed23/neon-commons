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


def _validate_graph(graph):
    """Check integrity and the closed safe shape, not provenance authenticity."""
    from .graph_validation import validate_graph
    validate_graph(graph, MAX_GRAPH_RELATION_CHECKS)


def _query_policies(graph, selected, result):
    nodes = graph['nodes']
    sid = result['subject_id']
    result['nodes'] = [n for n in nodes if n['type'] == 'Policy' and (sid is None or n['id'] == sid)]
    result['coverage'] = [c for c in graph['coverage'] if c['aspect'] == 'policies' and (sid is None or c['subject_id'] == sid)]


def _query_assignments(graph, selected, result):
    nodes = graph['nodes']
    sid = result['subject_id']
    result['nodes'] = [n for n in nodes if n['type'] == 'Assignment' and (sid is None or n['policy_id'] == sid)]
    result['coverage'] = [c for c in graph['coverage'] if c['aspect'] == 'assignments' and (sid is None or c['subject_id'] == sid)]


def _query_why_setting(graph, selected, result):
    nodes = graph['nodes']
    edges = graph['edges']
    sid = result['subject_id']
    if selected is None or selected['type'] != 'SettingValue':
        raise AppError('invalid_subject', 'why-setting requires a SettingValue node ID.')
    result['nodes'] = [selected]
    result['edges'] = [e for e in edges if e['source'] == sid]
    definitions = {e['target'] for e in result['edges'] if e['predicate'] == 'hasDefinition'}
    result['edges'] += [e for e in edges if e['source'] in definitions and e['predicate'] == 'mappedBy']
    target_ids = {e['target'] for e in result['edges']}
    result['nodes'] += [n for n in nodes if n['id'] in target_ids and n['type'] in ('SettingDefinition', 'ProviderMapping')]


def _declared_dependency_edges(graph, subject_id):
    edges = graph['edges']
    relations = [edge for edge in edges if edge['predicate'] == 'declaresDependencyOn'
                 and (subject_id is None or edge['source'] == subject_id or edge['target'] == subject_id)]
    consumers = {edge['source'] for edge in relations}
    declarations = {node['id'] for node in graph['nodes'] if node['type'] == 'DependencyDeclaration'
                    and (subject_id is None or node['consumer_id'] == subject_id or node['consumer_id'] in consumers)}
    return relations + [edge for edge in edges if edge['predicate'] == 'hasDependencyDeclaration'
                        and edge['target'] in declarations]


def _selected_effective_dependencies(graph, subject_id):
    referring = {edge['source'] for edge in graph['edges']
                 if edge['predicate'] == 'dependsOn' and edge['target'] == subject_id}
    return {node['id'] for node in graph['nodes'] if node['type'] == 'EffectiveDependency'
            and (subject_id is None or node['consumer_id'] == subject_id or node['id'] in referring)}


def _effective_dependency_edges(graph, subject_id):
    dependencies = _selected_effective_dependencies(graph, subject_id)
    configurations = {node['configuration_id'] for node in graph['nodes'] if node['id'] in dependencies}
    selections = {'dependsOn': ('source', dependencies),
                  'hasEffectiveDependency': ('target', dependencies),
                  'hasEffectiveConfiguration': ('target', configurations)}
    result = []
    for edge in graph['edges']:
        if edge['predicate'] in selections:
            endpoint, identifiers = selections[edge['predicate']]
            if edge[endpoint] in identifiers:
                result.append(edge)
    return result


def _dependency_issues(graph, result):
    identifiers = {node['id'] for node in result['nodes']}
    artifacts = {node.get('origin', {}).get('artifact_id') for node in result['nodes']}
    return [issue for issue in graph['issues']
            if ('dependency' in issue['code'] or issue['code'].startswith('atmos_effective_'))
            and (result['subject_id'] is None or issue.get('subject_id') in identifiers
                 or issue.get('origin', {}).get('artifact_id') in artifacts)]


def _query_dependencies(graph, selected, result):
    sid = result['subject_id']
    result['edges'] = _declared_dependency_edges(graph, sid) + _effective_dependency_edges(graph, sid)
    identifiers = {edge[key] for edge in result['edges'] for key in ('source', 'target')}
    result['nodes'] = [node for node in graph['nodes'] if node['id'] in identifiers]
    result['execution_order'] = 'not_established'
    result['completeness'] = 'unknown'
    result['issues'] = _dependency_issues(graph, result)


def _component_placement(graph, selected, result):
    sid = result['subject_id']
    instance_relations = {'usesImplementation', 'belongsToStackDeclaration',
                          'belongsToEffectiveStack', 'hasEffectiveConfiguration'}
    relations = [edge for edge in graph['edges'] if edge['source'] == sid
                 and edge['predicate'] in instance_relations]
    configurations = {edge['target'] for edge in relations if edge['predicate'] == 'hasEffectiveConfiguration'}
    relations += [edge for edge in graph['edges'] if edge['source'] in configurations
                  and edge['predicate'] in ('usesImplementation', 'derivedFrom')]
    related = {edge['target'] for edge in relations} | {sid}
    result['nodes'] = [node for node in graph['nodes'] if node['id'] in related]
    result['edges'] = relations
    result['stack_resolution'] = selected['resolution_status']
    definitions = [node for node in result['nodes'] if node['type'] == 'ComponentDefinition' and node['status'] == 'derived']
    if definitions:
        result['implementation_presence'] = definitions[0]['implementation_presence']


def _query_placement(graph, selected, result):
    if selected and selected['type'] == 'ComponentInstance':
        _component_placement(graph, selected, result)
    else:
        sid = result['subject_id']
        result['nodes'] = [node for node in graph['nodes'] if node['type'] == 'PlacementIntent'
                           and (sid is None or node['policy_id'] == sid)]
    result['target_verification'] = 'not_established'


def _query_impact(graph, selected, result):
    nodes = graph['nodes']
    edges = graph['edges']
    sid = result['subject_id']
    if selected is None:
        raise AppError('invalid_subject', 'impact requires an exact graph subject.')
    visited = {sid}
    frontier = [sid]
    while frontier:
        current = frontier.pop()
        for e in edges:
            if e['target'] == current and e['source'] not in visited:
                visited.add(e['source'])
                frontier.append(e['source'])
    result['nodes'] = [n for n in nodes if n['id'] in visited]
    result['edges'] = [e for e in edges if e['source'] in visited and e['target'] in visited]
    result['completeness'] = 'unknown'
    result['execution_order'] = 'not_established'


def _query_subject(graph, subject):
    if subject is not None and not isinstance(subject, str):
        raise AppError('invalid_subject', 'Graph subject must be an exact node ID or policy UUID.')
    selected = next((node for node in graph['nodes'] if node['id'] == subject), None)
    if selected is None and subject is not None:
        matches = [node for node in graph['nodes'] if node['type'] == 'Policy' and node['object_uuid'] == subject]
        if len(matches) == 1:
            selected = matches[0]
    if subject is not None and selected is None:
        raise AppError('unknown_subject', 'Graph subject was not found or was ambiguous.')
    return selected


def _query_policy_issues(graph, query, selected, result):
    sid = result['subject_id']
    if query == 'why-setting':
        policy_ids = {selected['policy_id']}
    else:
        policy_ids = {node['id'] for node in graph['nodes'] if node['type'] == 'Policy' and (sid is None or node['id'] == sid)}
    result['issues'] = [issue for issue in graph['issues'] if issue.get('subject_id') in policy_ids]


def _query_sources(graph, result):
    artifact_ids = set()
    for collection in ('nodes', 'edges', 'coverage', 'issues'):
        artifact_ids.update(row.get('origin', {}).get('artifact_id') for row in result.get(collection, []))
    result['sources'] = [source for source in graph['sources'] if source['id'] in artifact_ids]


_QUERY_HANDLERS = {'policies': _query_policies, 'assignments': _query_assignments,
                   'why-setting': _query_why_setting, 'dependencies': _query_dependencies,
                   'placement': _query_placement, 'impact': _query_impact}


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
    selected = _query_subject(graph, subject)
    result = {'query': query, 'subject_id': selected['id'] if selected else None,
              'nodes': [], 'edges': [], 'coverage': [], 'sources': [], 'execution_authorized': False}
    _QUERY_HANDLERS[query](graph, selected, result)
    if not result['edges']:
        ids = {node['id'] for node in result['nodes']}
        result['edges'] = [edge for edge in graph['edges'] if edge['source'] in ids]
    if query in ('policies', 'assignments', 'why-setting'):
        _query_policy_issues(graph, query, selected, result)
    _query_sources(graph, result)
    if query == 'impact':
        result['issues'] = graph['issues']
    return copy.deepcopy(result)
