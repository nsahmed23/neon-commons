"""Readable field-level differences between two bounded policy bodies.

The differences follow the maintenance plan's own equality
(``modeled_service.compare_semantics``): assignments, technologies and role
scope tags are bags, and every other field, including the order of setting
records, is exact. Values are reported verbatim, never normalized. A shape
outside the bounded model is reported as unknown, never as an invented
difference. This is presentation evidence; it grants no execution authority.
"""
from __future__ import annotations

import copy
from collections import Counter

from .io import canonical, digest

VERSION = 'workbench-field-changes/1'
FIELDS = ('name', 'description', 'platforms', 'technologies', 'role_scope_tag_ids', 'settings', 'assignments')
BAGS = frozenset({'technologies', 'role_scope_tag_ids', 'assignments'})
MAX_CHANGES = 1000


def _shape_blockers(body, side):
    if type(body) is not dict:
        return [{'side': side, 'path': '', 'code': 'object_required'}]
    if set(body) != set(FIELDS):
        return [{'side': side, 'path': '', 'code': 'unsupported_or_missing_fields'}]
    blockers = [{'side': side, 'path': '/' + field, 'code': 'list_required'}
                for field in sorted(BAGS) if type(body[field]) is not list]
    settings = body['settings']
    if type(settings) is not dict or set(settings) != {'settings'} or type(settings['settings']) is not list:
        return blockers + [{'side': side, 'path': '/settings', 'code': 'settings_shape_invalid'}]
    ids = []
    for index, row in enumerate(settings['settings']):
        if type(row) is not dict or type(row.get('id')) is not str or type(row.get('settingInstance')) is not dict:
            blockers.append({'side': side, 'path': '/settings/settings/%d' % index, 'code': 'setting_record_invalid'})
        else:
            ids.append(row['id'])
    if len(set(ids)) != len(ids):
        blockers.append({'side': side, 'path': '/settings/settings', 'code': 'duplicate_setting_identity'})
    return blockers


def _pointer_token(key):
    return str(key).replace('~', '~0').replace('/', '~1')


def _leaves(before, after, path=''):
    """Pointer-level differences inside one record. Lists compare by position."""
    if type(before) is dict and type(after) is dict:
        for key in sorted(set(before) | set(after)):
            pointer = path + '/' + _pointer_token(key)
            if key not in before:
                yield {'path': pointer, 'kind': 'added', 'after': copy.deepcopy(after[key])}
            elif key not in after:
                yield {'path': pointer, 'kind': 'removed', 'before': copy.deepcopy(before[key])}
            else:
                yield from _leaves(before[key], after[key], pointer)
    elif type(before) is list and type(after) is list and len(before) == len(after):
        for index, (left, right) in enumerate(zip(before, after)):
            yield from _leaves(left, right, path + '/' + str(index))
    elif type(before) is not type(after) or canonical(before) != canonical(after):
        yield {'path': path, 'before': copy.deepcopy(before), 'after': copy.deepcopy(after)}


def _bag_changes(field, before, after):
    left, right = Counter(digest(item) for item in before), Counter(digest(item) for item in after)
    changes, seen = [], Counter()
    for item in before:
        key = digest(item); seen[key] += 1
        if seen[key] > right[key]:
            changes.append({'field': field, 'kind': 'removed', 'path': '/' + field, 'value': copy.deepcopy(item)})
    seen = Counter()
    for item in after:
        key = digest(item); seen[key] += 1
        if seen[key] > left[key]:
            changes.append({'field': field, 'kind': 'added', 'path': '/' + field, 'value': copy.deepcopy(item)})
    return changes


def _definition(row):
    value = row['settingInstance'].get('settingDefinitionId')
    return value if type(value) is str else None


def _setting_changes(before, after):
    left, right = before['settings']['settings'], after['settings']['settings']
    by_id = {row['id']: row for row in left}
    after_ids = {row['id'] for row in right}
    path = '/settings/settings'
    changes = [{'field': 'settings', 'kind': 'removed', 'path': path, 'setting_id': row['id'],
                'setting_definition_id': _definition(row), 'value': copy.deepcopy(row)}
               for row in left if row['id'] not in after_ids]
    for row in right:
        previous = by_id.get(row['id'])
        if previous is None:
            changes.append({'field': 'settings', 'kind': 'added', 'path': path, 'setting_id': row['id'],
                            'setting_definition_id': _definition(row), 'value': copy.deepcopy(row)})
        elif canonical(previous) != canonical(row):
            changes.append({'field': 'settings', 'kind': 'changed', 'path': path, 'setting_id': row['id'],
                            'setting_definition_id': _definition(row),
                            'differences': list(_leaves(previous, row))})
    common_before = [row['id'] for row in left if row['id'] in after_ids]
    common_after = [row['id'] for row in right if row['id'] in by_id]
    if common_before != common_after:
        # The plan compares the settings list exactly, so an order change alone
        # is still a change. It is named here instead of being hidden.
        changes.append({'field': 'settings', 'kind': 'reordered', 'path': path,
                        'before_order': [row['id'] for row in left], 'after_order': [row['id'] for row in right]})
    return changes


def field_changes(before, after):
    """Return the exact field-level differences from ``before`` to ``after``."""
    blockers = _shape_blockers(before, 'before') + _shape_blockers(after, 'after')
    result = {'schema_version': VERSION, 'status': 'unknown', 'changes': [], 'blockers': blockers,
              'equality': 'maintenance_plan_fields', 'complete': True, 'execution_authorized': False}
    if blockers:
        return result
    changes = []
    for field in FIELDS:
        if field in BAGS:
            changes.extend(_bag_changes(field, before[field], after[field]))
        elif field == 'settings':
            changes.extend(_setting_changes(before, after))
        elif type(before[field]) is not type(after[field]) or canonical(before[field]) != canonical(after[field]):
            changes.append({'field': field, 'kind': 'changed', 'path': '/' + field,
                            'before': copy.deepcopy(before[field]), 'after': copy.deepcopy(after[field])})
    if len(changes) > MAX_CHANGES:
        changes, result['complete'] = changes[:MAX_CHANGES], False
    result.update(status='changed' if changes else 'no_change', changes=changes)
    return result
