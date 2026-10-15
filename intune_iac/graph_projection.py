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
# Each kind in words, and the only kind an operation state can apply to: a policy has operations, and a group, a filter,
# a scope tag, a setting or a source has none, so it reads no state at all (never "unknown", which would claim a gap).
KIND_WORDS = {'policy': 'policy', 'group': 'group', 'filter': 'filter', 'scope_tag': 'scope tag', 'setting': 'setting',
              'repository': 'repository', 'target': 'assignment target', 'source': 'source', 'other': 'related item'}
KINDS_WITH_OPERATION = ('policy',)
NONE_RECORDED = 'none recorded'
FILTER_TYPES = ('include', 'exclude')


def state_word(value):
    """The workbench state word for a read-model state, or unknown: never a guess from similar words."""
    if not isinstance(value, str):
        return 'unknown'
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
            edges.append(dict(edge, target_id=str(edge['target_id']), _origin='read_model'))
        else:
            excluded += 1
    repository = value.get('selected_repository')
    if isinstance(repository, dict) and isinstance(repository.get('scope'), dict):
        scope = repository['scope']
        edges.append({'relation': 'repository', 'assertion_class': repository.get('evidence_class', 'unknown'),
                      'target_id': '%s  %s / %s' % (scope.get('repository'), scope.get('stack'), scope.get('component')),
                      'details': {}, '_origin': 'selection'})
    return edges, excluded


def _recorded_operation(raw):
    """The read model's own word for the policy's newest operation: none recorded when it names none, else exactly that
    word (expired, prepared, dispatched and the rest), and unknown when what it gave cannot be read as a word."""
    if raw is None:
        return NONE_RECORDED
    return raw if isinstance(raw, str) and raw else 'unknown'


def _filter_of(edge):
    """The filter an assignment or exclusion applies, with its type, as the read model states it; None when it states none."""
    details = edge.get('details') if isinstance(edge.get('details'), dict) else {}
    identifier = details.get('filter_id')
    if (edge['relation'] in ('assignment', 'exclusion') and details.get('filter_type') in FILTER_TYPES
            and isinstance(identifier, str) and identifier):
        return {'ref': 'filter:' + identifier, 'id': identifier, 'type': details['filter_type']}
    return None


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

    policy_name = value['name'] if isinstance(value.get('name'), str) and value['name'] else None
    nodes = {center: {'ref': center, 'id': center_id, 'kind': 'policy', 'name': policy_name,
                      'state': state_word(states.get(center_id)), 'kind_word': KIND_WORDS['policy'],
                      'label': policy_name or '(no name)', 'resolved': policy_name is not None, 'state_applies': True,
                      'operation': _recorded_operation(states.get(center_id))}}
    refs = {}
    for edge in edges:
        refs.setdefault(edge['target_id'], '%s:%s' % (_kind(edge), edge['target_id']) if edge['relation'] in ('assignment', 'exclusion') else None)
    projected = []
    for edge in edges:
        kind = _kind(edge)
        ref = '%s:%s' % (kind, edge['target_id'])
        if ref not in nodes:
            name = names.get(edge['target_id'])
            name = name if isinstance(name, str) and name else None
            nodes[ref] = {'ref': ref, 'id': edge['target_id'], 'kind': kind, 'name': name,
                          'state': state_word(states.get(edge['target_id'])), 'kind_word': KIND_WORDS.get(kind, kind),
                          'label': name or edge['target_id'], 'resolved': name is not None,
                          'state_applies': kind in KINDS_WITH_OPERATION, 'operation': None}
        applies = None
        if edge['relation'] == 'filter':
            details = edge.get('details') if isinstance(edge.get('details'), dict) else {}
            applies = refs.get(details.get('assignment_target')) if isinstance(details.get('assignment_target'), str) else None
        projected.append({'source': center, 'target': ref, 'type': edge['relation'], 'layer': heading_of[edge['relation']],
                          'provenance': str(edge.get('assertion_class', 'unknown')), 'freshness': freshness,
                          'origin': edge['_origin'], 'filter': _filter_of(edge), 'applies_to': applies})
    projected.sort(key=lambda row: (order[row['layer']], row['target'].split(':', 1)[1], row['type'], row['target']))
    body = {'schema_version': SCHEMA, 'center': center,
            'nodes': [nodes[center]] + sorted((node for ref, node in nodes.items() if ref != center), key=lambda node: node['ref']),
            'edges': projected,
            'layers': [heading for heading, _ in layers if any(row['layer'] == heading for row in projected)],
            'excluded': excluded,
            # What the read model listed (the tree's own count) and what the selection added, apart, so a header cannot
            # disagree with the tree: the repository the engineer selected is a source, not a listed relationship.
            'counts': {'relationships': sum(isinstance(edge, dict) for edge in value.get('relationships') or []),
                       'sources': sum(edge['_origin'] == 'selection' for edge in edges)}}
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


def distinct_labels(graph, width, ellipsis='\u2026'):
    """Each node's label cut to `width` characters so that two different nodes never print alike.

    A label that fits is whole. A longer one keeps its head and its tail around the ellipsis, because what tells paths
    and Settings Catalog identifiers apart is at the end (the shared folder, the shared device_vendor_msft prefix are
    at the start). The split is chosen once for the whole set, the first (nearest an even split) at which every
    different label reads differently, so the same set always cuts the same way. If no split can tell two labels apart
    (they differ only in the middle), the labels stay whole rather than be made to look alike; they then exceed the
    width, and the caller shows the full identifier beside them.
    """
    texts = {node['ref']: node['label'] for node in graph['nodes']}
    room = width - len(ellipsis)

    def cut(text, tail):
        if len(text) <= width:
            return text
        return text[:room - tail] + ellipsis + (text[len(text) - tail:] if tail else '')

    if room >= 1:
        tails = sorted(range(room), key=lambda tail: (abs(tail - room // 2), tail))
        for tail in tails:
            cuts = {ref: cut(text, tail) for ref, text in texts.items()}
            whole = set(texts.values())
            if len(set(cuts.values())) == len(whole):
                return cuts
    return dict(texts)
