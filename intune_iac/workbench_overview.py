"""Estate overview: how the observed policies relate through groups, filters, scope tags and settings.

Read-only. It is built from the records Estate and Relationships already use:
each policy's current observation and its typed edges, the ownership and
freshness the store reports, and the maintenance queue's findings. It shows what
policies share (a group several of them target, a setting several configure)
and what was not established (policies without a complete observation, or
beyond the read bound), so an empty section never reads as "nothing there".
"""
from __future__ import annotations

VERSION = 'workbench-estate-overview/1'
MAX_POLICIES = 200


def _by_size(rows, *keys):
    """Most-shared first, then by identity, so the order is stable."""
    return sorted(rows, key=lambda row: (-sum(len(row[key]) for key in keys), str(row.get('group_id') or row.get('filter_id')
                                                                                         or row.get('tag') or row.get('setting'))))


def estate_overview(store, *, limit=MAX_POLICIES):
    """Groups, filters, scope tags and settings across the estate's observed policies; read-only."""
    from .workbench import _queue
    overview = store.overview(limit=limit)
    objects = [row for row in overview.get('objects') or [] if isinstance(row, dict)]
    pending = [row for row in overview.get('pending_observations') or [] if isinstance(row, dict)]
    total = (overview.get('pagination') or {}).get('total_objects', len(objects))
    findings = {}
    for finding in _queue(store, limit=limit)['findings']:
        if finding.get('object_id'):
            findings.setdefault(finding['object_id'], []).append(finding.get('finding'))
    groups, filters, tags, settings, ownership, policies = {}, {}, {}, {}, {}, []
    for row in objects:
        object_id = row['object_id']
        observed = store.inspect(object_id)
        edges = [edge for edge in observed.get('relationships') or [] if isinstance(edge, dict)]
        def targets(relation):
            return sorted({str(edge.get('target_id')) for edge in edges if edge.get('relation') == relation})
        included, excluded = targets('assignment'), targets('exclusion')
        for group in included:
            groups.setdefault(group, {'included_by': set(), 'excluded_by': set()})['included_by'].add(object_id)
        for group in excluded:
            groups.setdefault(group, {'included_by': set(), 'excluded_by': set()})['excluded_by'].add(object_id)
        used_filters, used_tags, used_settings = targets('filter'), targets('scope_tag'), targets('setting')
        for key, found in ((filters, used_filters), (tags, used_tags), (settings, used_settings)):
            for item in found:
                key.setdefault(item, set()).add(object_id)
        owner = str(observed.get('ownership') or 'unknown')
        ownership[owner] = ownership.get(owner, 0) + 1
        policies.append({'object_id': object_id, 'name': observed.get('name'), 'freshness': observed.get('freshness'),
                         'ownership': owner, 'included_groups': len(included), 'excluded_groups': len(excluded),
                         'filters': len(used_filters), 'scope_tags': used_tags, 'settings': len(used_settings),
                         'findings': findings.get(object_id, [])})
    not_established = [{'object_id': row.get('object_id'), 'reason': 'no_complete_observation',
                        'last_attempt': (row.get('last_attempt') or {}).get('status')} for row in pending]
    if isinstance(total, int) and total > len(objects):
        not_established.append({'reason': 'beyond_read_bound', 'count': total - len(objects)})
    return {'schema_version': VERSION, 'tenant_id': store.tenant_id, 'evidence_class': overview.get('evidence_class'),
            'counts': {'policies_read': len(objects), 'policies_total': total, 'without_complete_observation': len(pending)},
            'ownership': ownership,
            'groups': _by_size([{'group_id': group, 'included_by': sorted(value['included_by']),
                                 'excluded_by': sorted(value['excluded_by'])} for group, value in groups.items()],
                               'included_by', 'excluded_by'),
            'filters': _by_size([{'filter_id': key, 'used_by': sorted(value)} for key, value in filters.items()], 'used_by'),
            'scope_tags': _by_size([{'tag': key, 'used_by': sorted(value)} for key, value in tags.items()], 'used_by'),
            'shared_settings': _by_size([{'setting': key, 'used_by': sorted(value)} for key, value in settings.items()
                                         if len(value) > 1], 'used_by'),
            'distinct_settings': len(settings), 'policies': policies, 'not_established': not_established,
            'execution_authorized': False, 'cloud_authority': False}
