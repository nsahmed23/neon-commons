"""One graph projection of the read model: a selected object and one hop, typed, directed and revisioned.

Pure: the engine's relationships result (the same typed edges the Relationships view reads, with the selected
repository's scope when there is one) in, a graph out. The graph is what a renderer draws, so a terminal map and any
later page agree on identity, kind, state, edge type, provenance and freshness without reading a relationship out of a
displayed string. Nothing here asks the engine, opens a file or decides what may be done; it reports what was read.

A node carries the read model's own identifier, its kind (from the relation that names it, never from its text), a
display name only where the read model resolved one, and a state word. A group the read model has no name for stays an
unresolved identity: its name is None and its identifier is all there is. The revision is the digest of the
projection's canonical form, so a changed state, name, freshness word or edge is a new revision.
"""
from __future__ import annotations

import hashlib
import json

from .io import AppError

SCHEMA = 'workbench-relationship-graph/1'
# The state words of the execution and orchestration view (the owner's guide); a state the read model reports in any
# other words is not translated into one of these, it is unknown here.
STATES = ('queued', 'running', 'waiting', 'blocked', 'failed', 'cancelled', 'unknown', 'verified')
# Exact equivalents only. A prepared proposal is not queued and a dispatched one is not running, so neither is mapped.
STATE_FROM_RECORD = {'outcome_unknown': 'unknown', 'succeeded_verified': 'verified'}
OTHER_LAYER = 'OTHER RELATIONSHIPS'
# The kind a relation names. An assignment or exclusion names a group only when the read model gives a group id.
KIND_OF_RELATION = {'filter': 'filter', 'setting': 'setting', 'scope_tag': 'scope_tag', 'repository': 'repository'}


def state_word(value):
    """The workbench state word for a read-model state, or unknown: never a guess from similar words."""
    if value in STATES:
        return value
    return STATE_FROM_RECORD.get(value, 'unknown')


def _fail(message):
    raise AppError('graph_projection_invalid', message)


def _kind(edge):
    relation = edge['relation']
    if relation in ('assignment', 'exclusion'):
        details = edge.get('details') if isinstance(edge.get('details'), dict) else {}
        return 'group' if details.get('group_id') else 'target'
    return KIND_OF_RELATION.get(relation) or ('source' if relation in ('generated_from',) or relation.startswith('source_') else 'other')


def _edges_of(value):
    """The result's edges plus the selected repository's scope as a repository edge; the count of what had no target."""
    edges, excluded = [], 0
    for edge in value.get('relationships') or []:
        if (isinstance(edge, dict) and isinstance(edge.get('relation'), str) and edge['relation']
                and isinstance(edge.get('target_id'), (str, int)) and not isinstance(edge.get('target_id'), bool)
                and str(edge['target_id'])):
            edges.append(dict(edge, target_id=str(edge['target_id'])))
        else:
            excluded += 1
    repository = value.get('selected_repository')
    if isinstance(repository, dict) and isinstance(repository.get('scope'), dict):
        scope = repository['scope']
        edges.append({'relation': 'repository', 'assertion_class': repository.get('evidence_class', 'unknown'),
                      'target_id': '%s  %s / %s' % (scope.get('repository'), scope.get('stack'), scope.get('component')),
                      'details': {}})
    return edges, excluded


def _layers():
    from .workbench_screens import RELATION_GROUPS
    return [(heading, tuple(members)) for heading, members in RELATION_GROUPS]


def project(value, *, names=None, states=None, freshness=None):
    """The graph of one object and its one-hop neighbours.

    names: identifier -> display name, for the identities the read model resolved (others stay unresolved).
    states: identifier -> state word from the read model (anything outside STATES reads unknown).
    freshness: the observation's freshness word as the read model states it; absent, edges read unknown.
    """
    if not isinstance(value, dict) or not isinstance(value.get('object_id'), str) or not value['object_id']:
        _fail('A graph needs a result that names its object by identifier.')
    names = names if isinstance(names, dict) else {}
    states = states if isinstance(states, dict) else {}
    freshness = freshness if isinstance(freshness, str) and freshness else 'unknown'
    center_id = value['object_id']
    center = 'policy:' + center_id
    layers = _layers()
    edges, excluded = _edges_of(value)
    others = tuple(dict.fromkeys(edge['relation'] for edge in edges
                                 if not any(edge['relation'] in members for _, members in layers)))
    if others:
        layers.append((OTHER_LAYER, others))
    heading_of = {relation: heading for heading, members in layers for relation in members}
    order = {heading: index for index, (heading, _) in enumerate(layers)}

    nodes = {center: {'ref': center, 'id': center_id, 'kind': 'policy',
                      'name': value['name'] if isinstance(value.get('name'), str) and value['name'] else None,
                      'state': state_word(states.get(center_id))}}
    projected = []
    for edge in edges:
        kind = _kind(edge)
        ref = '%s:%s' % (kind, edge['target_id'])
        if ref not in nodes:
            name = names.get(edge['target_id'])
            nodes[ref] = {'ref': ref, 'id': edge['target_id'], 'kind': kind,
                          'name': name if isinstance(name, str) and name else None,
                          'state': state_word(states.get(edge['target_id']))}
        projected.append({'source': center, 'target': ref, 'type': edge['relation'], 'layer': heading_of[edge['relation']],
                          'provenance': str(edge.get('assertion_class', 'unknown')), 'freshness': freshness})
    projected.sort(key=lambda row: (order[row['layer']], row['target'].split(':', 1)[1], row['type'], row['target']))
    body = {'schema_version': SCHEMA, 'center': center,
            'nodes': [nodes[center]] + sorted((node for ref, node in nodes.items() if ref != center), key=lambda node: node['ref']),
            'edges': projected,
            'layers': [heading for heading, _ in layers if any(row['layer'] == heading for row in projected)],
            'excluded': excluded}
    revision = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                         allow_nan=False).encode('utf-8')).hexdigest()
    return dict(body, revision=revision)


def drawn_layers(graph, per_layer=None):
    """Each layer of a graph with the edges a renderer draws (the first `per_layer`, in order; all when None) and how
    many it does not draw. The terminal map and the companion page cut with the same rule and differ only in the limit."""
    layers = []
    for heading in graph['layers']:
        edges = [edge for edge in graph['edges'] if edge['layer'] == heading]
        shown = edges if per_layer is None else edges[:per_layer]
        layers.append((heading, shown, len(edges) - len(shown)))
    return layers


def traversal_order(graph, per_layer=None):
    """The node references in the order the keyboard visits them: the selected object, then layer by layer, each node once."""
    order = [graph['center']]
    for _, edges, _ in drawn_layers(graph, per_layer):
        for edge in edges:
            if edge['target'] not in order:
                order.append(edge['target'])
    return order
