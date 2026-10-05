"""Structural and semantic validation of the closed, byte-backed review graph."""
from __future__ import annotations

import re

from reference.validation import schema_errors, capability_errors
from .graph_contract import (CARDINALITIES, DERIVED_NODE_TYPES, NODE_FIELDS,
                             NODE_OPTIONAL_FIELDS, PREDICATE_CONTRACTS)
from .io import AppError, digest


def fail():
    raise AppError('invalid_graph', 'Graph integrity or safe review structure is invalid.')


def closed(row, required, allowed):
    if not isinstance(row, dict) or not required <= row.keys() or not row.keys() <= allowed:
        fail()


def scalar_fields(row, exceptions=()):
    for key, value in row.items():
        if key in exceptions:
            continue
        if not isinstance(value, (str, int, type(None))) or isinstance(value, bool):
            fail()
        if isinstance(value, str) and (len(value) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            fail()


def hashed(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)


def _validate_envelope(graph, max_relationship_checks):
    fields = {'schema_version', 'nodes', 'edges', 'sources', 'coverage', 'issues',
              'execution_authorized', 'live_qualification', 'atmos', 'graph_digest'}
    if set(graph) != fields:
        fail()
    if graph.get('execution_authorized') is not False or graph.get('live_qualification') != 'not_run':
        fail()
    if any(not isinstance(graph[k], list) or len(graph[k]) > 100000 for k in ('nodes', 'edges', 'sources', 'coverage', 'issues')):
        fail()
    work = len(graph['nodes']) * (len(graph['edges']) + len(graph['coverage']) + len(graph['sources']))
    if work > max_relationship_checks:
        raise AppError('graph_query_budget', 'Graph exceeds the bounded relationship-validation work budget; the complete graph was not queried.')
    try:
        if graph['graph_digest'] != digest({k: v for k, v in graph.items() if k != 'graph_digest'}):
            fail()
    except (ValueError, TypeError, RecursionError):
        fail()


class GraphValidator:
    """Indexes are built only after collection bounds and closed row shapes pass."""
    def __init__(self, graph):
        self.graph = graph
        self.node_ids = set()
        self.source_ids = set()
        self.by_id = {}
        self.sources_by_id = {}
        self.outgoing = {}

    def origin(self, row):
        if 'origin' not in row:
            return
        origin = row['origin']
        closed(origin, {'artifact_id', 'pointer'}, {'artifact_id', 'pointer', 'line', 'column'})
        if origin['artifact_id'] not in self.source_ids or not isinstance(origin['pointer'], str) or len(origin['pointer']) > 4096:
            fail()
        if origin['pointer'] and not origin['pointer'].startswith(('/', 'opaque:')):
            fail()
        if any(ord(c) < 32 or ord(c) == 127 for c in origin['pointer']):
            fail()
        if any(not isinstance(origin[k], int) or isinstance(origin[k], bool) or origin[k] < 1 for k in ('line', 'column') if k in origin):
            fail()

    def sources(self):
        for source in self.graph['sources']:
            closed(source, {'id', 'type', 'sha256', 'kind'}, {'id', 'type', 'sha256', 'kind', 'path', 'adapter'})
            if source['type'] != 'SourceArtifact' or not hashed(source['sha256']):
                fail()
            if source['kind'] not in ('intune_capture', 'placement_context', 'atmos_yaml') or source['id'] in self.source_ids:
                fail()
            if 'adapter' in source and (source['kind'] != 'intune_capture' or source['adapter'] != 'plugin_graph_capture/1.0.0'):
                fail()
            scalar_fields(source)
            self.source_ids.add(source['id'])
        self.sources_by_id = {source['id']: source for source in self.graph['sources']}

    def _setting_shape(self, node):
        record = {'id': node.get('setting_id'), 'settingInstance': node.get('normalized_instance')}
        if schema_errors('observed-setting', record) or capability_errors([record]):
            fail()
        if node['value_digest'] != digest(node['normalized_instance']):
            fail()

    def _assignment_capture(self, node):
        if not any(key in node for key in ('assignment_source', 'assignment_source_id', 'capture_adapter')):
            return
        if node.get('capture_adapter') != 'plugin_graph_capture/1.0.0' or node.get('assignment_source', 'direct') != 'direct' or node.get('assignment_source_id') not in (None, ''):
            fail()
        source = self.sources_by_id.get(node.get('origin', {}).get('artifact_id'), {})
        if source.get('adapter') != node['capture_adapter']:
            fail()

    def nodes(self):
        for node in self.graph['nodes']:
            if not isinstance(node, dict) or node.get('type') not in NODE_FIELDS:
                fail()
            fields = set(NODE_FIELDS[node['type']].split())
            closed(node, {'id', 'type', 'status'} | fields,
                   {'id', 'type', 'status', 'origin'} | fields | NODE_OPTIONAL_FIELDS.get(node['type'], set()))
            if not isinstance(node['id'], str) or node['id'] in self.node_ids:
                fail()
            self.node_ids.add(node['id'])
            self.origin(node)
            if node['status'] not in ('observed', 'declared', 'referenced', 'derived'):
                fail()
            scalar_fields(node, ('origin', 'normalized_instance'))
            if node['type'] == 'SettingValue':
                self._setting_shape(node)
            if node['type'] == 'Assignment':
                self._assignment_capture(node)
        self.by_id = {node['id']: node for node in self.graph['nodes']}

    def edges(self):
        identities = set()
        for edge in self.graph['edges']:
            closed(edge, {'id', 'source', 'predicate', 'target', 'status'},
                   {'id', 'source', 'predicate', 'target', 'status', 'origin', 'filter_mode', 'order', 'resolution', 'qualification'})
            if edge['source'] not in self.node_ids or edge['target'] not in self.node_ids or edge['predicate'] not in PREDICATE_CONTRACTS or edge['status'] not in ('observed', 'declared', 'derived'):
                fail()
            scalar_fields(edge, ('origin',))
            if not isinstance(edge['id'], str) or not edge['id'] or edge['id'] in identities:
                fail()
            identities.add(edge['id'])
            self.origin(edge)
            self.outgoing.setdefault((edge['source'], edge['predicate']), []).append(edge)

    def coverage(self):
        expected = set()
        for node in self.graph['nodes']:
            if node['type'] == 'Tenant':
                expected.add((node['id'], 'policies'))
            elif node['type'] == 'Policy':
                expected.update((node['id'], aspect) for aspect in ('policies', 'settings', 'assignments'))
            elif node['type'] == 'StackDeclaration':
                expected.add((node['id'], 'atmos_effective_resolution'))
            elif node['type'] == 'ComponentInstance' and node['resolution_status'] == 'resolved':
                expected.add((node['id'], 'atmos_effective_resolution'))
        seen = set()
        for claim in self.graph['coverage']:
            fields = {'subject_id', 'aspect', 'status', 'origin'}
            closed(claim, fields, fields)
            if claim['subject_id'] not in self.node_ids or claim['status'] not in ('complete', 'unknown') or claim['aspect'] not in ('policies', 'settings', 'assignments', 'atmos_effective_resolution'):
                fail()
            scalar_fields(claim, ('origin',))
            self.origin(claim)
            identity = (claim['subject_id'], claim['aspect'])
            if identity not in expected or identity in seen:
                fail()
            if self.by_id[claim['subject_id']]['type'] == 'StackDeclaration' and claim['status'] != 'unknown':
                fail()
            seen.add(identity)
        if seen != expected:
            fail()

    def issues(self):
        for issue in self.graph['issues']:
            closed(issue, {'code'}, {'code', 'subject_id', 'origin', 'status'})
            if not isinstance(issue['code'], str) or not re.fullmatch('[a-z][a-z0-9_]{0,100}', issue['code']):
                fail()
            scalar_fields(issue, ('origin',))
            self.origin(issue)

    def atmos(self):
        row = self.graph['atmos']
        closed(row, {'resolution_status'}, {'resolution_status', 'adapter', 'effective_config', 'tenant_verification', 'execution_order'})
        scalar_fields(row)
        if row['resolution_status'] not in ('unknown', 'not_requested', 'partial', 'resolved'):
            fail()

    def targets(self, node_id, predicate):
        return [self.by_id[e['target']] for e in self.outgoing.get((node_id, predicate), [])]

    def exact_target(self, node_id, predicate, target_id):
        if [node['id'] for node in self.targets(node_id, predicate)] != [target_id]:
            fail()

    def relationship_contracts(self):
        for edge in self.graph['edges']:
            contract = PREDICATE_CONTRACTS[edge['predicate']]
            source, target = self.by_id[edge['source']], self.by_id[edge['target']]
            if source['type'] not in contract.source_types or target['type'] not in contract.target_types or edge['status'] not in contract.statuses:
                fail()
            derived = 'derived' in (edge['status'], source['status'], target['status'])
            if edge['predicate'] == 'usesImplementation' and derived:
                if edge['status'] != 'derived' or source['type'] != 'EffectiveConfiguration' or target['type'] != 'ComponentDefinition':
                    fail()
            elif derived and edge['status'] != 'derived':
                fail()

    def cardinalities(self, node):
        selectors = ((node['type'], None), (node['type'], node.get('resolution_status')))
        for selector in dict.fromkeys(selectors):
            for predicate, (minimum, maximum) in CARDINALITIES.get(selector, {}).items():
                count = len(self.outgoing.get((node['id'], predicate), []))
                if count < minimum or maximum is not None and count > maximum:
                    fail()

    def policy(self, node):
        tenant = self.by_id.get(node['tenant_id'], {})
        if tenant.get('type') != 'Tenant' or any(tenant.get(k) != node[k] for k in ('cloud', 'tenant_uuid')):
            fail()
        self.exact_target(node['id'], 'inTenant', node['tenant_id'])

    def setting(self, node):
        if self.by_id.get(node['policy_id'], {}).get('type') != 'Policy':
            fail()
        self.exact_target(node['id'], 'ofPolicy', node['policy_id'])
        definitions = self.targets(node['id'], 'hasDefinition')
        if len(definitions) != 1 or definitions[0]['definition_id'] != node['definition_id'] or node['normalized_instance']['settingDefinitionId'] != node['definition_id']:
            fail()

    def assignment(self, node):
        from .graph import _uuid
        policy = self.by_id.get(node['policy_id'], {})
        group = self.by_id.get(node['group_id'], {})
        if policy.get('type') != 'Policy' or group.get('type') != 'Group':
            fail()
        if not isinstance(node['assignment_uuid'], str) or not node['assignment_uuid'] or _uuid(node['group_uuid']) is None:
            fail()
        if _uuid(group['object_uuid']) != _uuid(node['group_uuid']) or any(group[k] != policy[k] for k in ('cloud', 'tenant_uuid')):
            fail()
        self.exact_target(node['id'], 'ofPolicy', node['policy_id'])
        if node['target_type'] not in ('groupAssignmentTarget', 'exclusionGroupAssignmentTarget'):
            fail()
        if node['target_type'] == 'exclusionGroupAssignmentTarget' and node['filter_mode'] != 'none':
            fail()
        predicate = 'excludesGroup' if node['target_type'] == 'exclusionGroupAssignmentTarget' else 'includesGroup'
        self.exact_target(node['id'], predicate, node['group_id'])
        if self.targets(node['id'], 'includesGroup' if predicate == 'excludesGroup' else 'excludesGroup'):
            fail()
        self.assignment_filter(node, policy)

    def assignment_filter(self, node, policy):
        from .graph import _uuid
        filters = self.targets(node['id'], 'usesFilter')
        if node['filter_mode'] == 'none':
            if node['filter_uuid'] is not None or filters:
                fail()
        elif node['filter_mode'] in ('include', 'exclude'):
            if len(filters) != 1 or _uuid(node['filter_uuid']) is None or _uuid(filters[0]['object_uuid']) != _uuid(node['filter_uuid']):
                fail()
            if any(filters[0][k] != policy[k] for k in ('cloud', 'tenant_uuid')):
                fail()
            if any(e.get('filter_mode') != node['filter_mode'] for e in self.outgoing.get((node['id'], 'usesFilter'), [])):
                fail()
        else:
            fail()

    def effective_stack(self, node):
        from .graph import identity, _safe_selector
        if node['resolution_status'] != 'resolved' or not _safe_selector(node['physical_stack']):
            fail()
        if node['id'] != identity('effective-stack', node['repository_scope_id'], node['physical_stack']):
            fail()

    def component_definition(self, node):
        from .graph import identity, _safe_selector
        if node['status'] != 'derived':
            return
        if node.get('implementation_presence') not in ('present', 'missing') or not _safe_selector(node.get('implementation_directory')):
            fail()
        if not _safe_selector(node['implementation_path']):
            fail()
        if node['id'] != identity('effective-component-definition', node['repository_scope_id'], node['engine_type'], node['implementation_path']):
            fail()

    def component_instance(self, node):
        if node['resolution_status'] not in ('unknown', 'resolved'):
            fail()
        stack = self.by_id.get(node['stack_id'], {})
        if node['resolution_status'] == 'resolved':
            self.resolved_component(node, stack)
        elif node['status'] != 'declared' or stack.get('type') != 'StackDeclaration' or self.targets(node['id'], 'hasEffectiveConfiguration'):
            fail()

    def resolved_component(self, node, stack):
        from .graph import identity, _safe_selector
        if node['status'] != 'derived' or stack.get('type') != 'EffectiveStack' or stack['repository_scope_id'] != node['repository_scope_id']:
            fail()
        if not _safe_selector(node['name']) or node['engine_type'] != 'terraform':
            fail()
        if node['id'] != identity('effective-component-instance', node['repository_scope_id'], stack['physical_stack'], node['engine_type'], node['name']):
            fail()
        self.exact_target(node['id'], 'belongsToEffectiveStack', stack['id'])
        configs = self.targets(node['id'], 'hasEffectiveConfiguration')
        if len(configs) != 1 or configs[0]['type'] != 'EffectiveConfiguration' or configs[0]['component_id'] != node['id']:
            fail()
        coverage = [c for c in self.graph['coverage'] if c['subject_id'] == node['id'] and c['aspect'] == 'atmos_effective_resolution']
        if len(coverage) != 1 or coverage[0]['status'] != 'complete':
            fail()

    def effective_configuration(self, node):
        from .graph import identity
        component = self.by_id.get(node['component_id'], {})
        if component.get('type') != 'ComponentInstance' or component.get('resolution_status') != 'resolved':
            fail()
        if node['resolution_status'] != 'resolved' or node['adapter'] != 'bounded-atmos/1.0':
            fail()
        if not all(hashed(node[key]) for key in ('source_fingerprint', 'selection_fingerprint', 'config_digest')):
            fail()
        if node['dependency_context_digest'] is not None and not hashed(node['dependency_context_digest']):
            fail()
        if node['id'] != identity('effective-configuration', node['component_id'], node['selection_fingerprint']):
            fail()
        definitions = self.targets(node['id'], 'usesImplementation')
        if len(definitions) != 1 or definitions[0]['type'] != 'ComponentDefinition':
            fail()
        if definitions[0]['repository_scope_id'] != component['repository_scope_id'] or definitions[0]['engine_type'] != component['engine_type']:
            fail()
        self.configuration_sources(node, component, definitions[0])
        self.exact_target(component['id'], 'hasEffectiveConfiguration', node['id'])

    def configuration_sources(self, node, component, definition):
        evidence = self.targets(node['id'], 'derivedFrom')
        if not evidence or any(n['type'] != 'ResolutionSource' or n['configuration_id'] != node['id'] for n in evidence):
            fail()
        inventory = []
        for item in evidence:
            artifact = self.sources_by_id.get(item['source_artifact_id'], {})
            if artifact.get('kind') != 'atmos_yaml' or not isinstance(artifact.get('path'), str):
                fail()
            inventory.append({'path': artifact['path'], 'sha256': artifact['sha256']})
        if len({item['path'] for item in inventory}) != len(inventory):
            fail()
        if node['source_fingerprint'] != digest({'adapter': 'atmos-literal/1.0', 'sources': sorted(inventory, key=lambda item: item['path'])}):
            fail()
        stack = self.by_id[component['stack_id']]
        selection = [node['source_fingerprint'], stack['physical_stack'], component['engine_type'], component['name'],
                     definition['implementation_directory'], definition['implementation_presence'] == 'present']
        if node['selection_fingerprint'] != digest(selection):
            fail()

    def resolution_source(self, node):
        from .graph import identity
        if node['source_artifact_id'] not in self.source_ids or self.by_id.get(node['configuration_id'], {}).get('type') != 'EffectiveConfiguration':
            fail()
        if node.get('origin', {}).get('artifact_id') != node['source_artifact_id']:
            fail()
        if node['id'] != identity('resolution-source', node['configuration_id'], node['source_artifact_id']):
            fail()
        if node['id'] not in [n['id'] for n in self.targets(node['configuration_id'], 'derivedFrom')]:
            fail()

    def effective_dependency(self, node):
        from .graph import _safe_selector
        config = self.by_id.get(node['configuration_id'], {})
        if config.get('type') != 'EffectiveConfiguration' or config['component_id'] != node['consumer_id']:
            fail()
        if node['adapter'] != 'settings.depends_on/literal' or node['resolution_status'] not in ('unknown', 'resolved'):
            fail()
        if node['selector_scope'] not in ('implicit_same_physical_stack', 'unresolved_selector') or node['context_relation'] not in ('equal', 'different', 'unknown'):
            fail()
        if any(node[k] is not None and not _safe_selector(node[k]) for k in ('component_selector', 'stack_selector')):
            fail()
        dependencies = self.targets(node['id'], 'dependsOn')
        if node['resolution_status'] == 'resolved':
            self.resolved_dependency(node, config, dependencies)
        elif dependencies:
            fail()
        if node['id'] not in [n['id'] for n in self.targets(config['id'], 'hasEffectiveDependency')]:
            fail()

    def resolved_dependency(self, node, config, dependencies):
        if len(dependencies) != 1 or dependencies[0]['type'] != 'ComponentInstance' or dependencies[0]['resolution_status'] != 'resolved':
            fail()
        target = dependencies[0]
        target_stack = self.by_id[target['stack_id']]
        consumer = self.by_id[node['consumer_id']]
        if node['selector_scope'] != 'implicit_same_physical_stack' or node['stack_selector'] is not None or node['context_relation'] != 'equal':
            fail()
        if target['name'] != node['component_selector'] or target_stack['id'] != consumer['stack_id']:
            fail()
        target_config = self.targets(target['id'], 'hasEffectiveConfiguration')
        if len(target_config) != 1 or config['dependency_context_digest'] is None or config['dependency_context_digest'] != target_config[0]['dependency_context_digest']:
            fail()

    def semantic_nodes(self):
        validators = {
            'Policy': self.policy, 'SettingValue': self.setting, 'Assignment': self.assignment,
            'EffectiveStack': self.effective_stack, 'ComponentDefinition': self.component_definition,
            'ComponentInstance': self.component_instance, 'EffectiveConfiguration': self.effective_configuration,
            'ResolutionSource': self.resolution_source, 'EffectiveDependency': self.effective_dependency,
        }
        for node in self.graph['nodes']:
            kind = node['type']
            if kind in DERIVED_NODE_TYPES and node['status'] != 'derived':
                fail()
            if node['status'] == 'derived' and kind not in DERIVED_NODE_TYPES | {'ComponentInstance', 'ComponentDefinition'}:
                fail()
            self.cardinalities(node)
            if kind in validators:
                validators[kind](node)
        self.effective_summary()

    def effective_summary(self):
        effective_count = sum(node['type'] == 'ComponentInstance' and node['resolution_status'] == 'resolved'
                              for node in self.graph['nodes'])
        atmos = self.graph['atmos']
        if (atmos['resolution_status'] in ('resolved', 'partial')) != bool(effective_count):
            fail()
        if effective_count and (atmos.get('adapter') != 'bounded-atmos/1.0' or atmos.get('tenant_verification') != 'not_established' or atmos.get('execution_order') != 'not_established'):
            fail()


def validate_graph(graph, max_relationship_checks):
    """Preserve byte integrity, bounded work, closed shapes and known semantics."""
    _validate_envelope(graph, max_relationship_checks)
    validator = GraphValidator(graph)
    validator.sources()
    validator.nodes()
    validator.edges()
    validator.coverage()
    validator.issues()
    validator.atmos()
    validator.relationship_contracts()
    validator.semantic_nodes()
