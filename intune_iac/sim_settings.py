"""Setting instances and their comparison for the Settings Catalog conflict pass.

A setting is never keyed on its definition id alone. The comparison key is (realm, tenant, platform, scope,
canonical identity, structural path, collection item): the path carries every ancestor with the parent choice that
gates the child, so the same child definition under a different parent choice or a different collection item is a
different key and cannot collide. Values are compared as typed values, never normalized beyond what the document
states. A conflict is only ever predicted under a rule the semantics profile admits for that definition, and the
finding says which rule; otherwise the overlap is unknown semantics.
"""
from __future__ import annotations

from dataclasses import dataclass

from .io import canonical


@dataclass(frozen=True)
class Instance:
    key: tuple
    definition_id: str
    canonical_id: str
    path: str
    item: str | None
    value: tuple
    itemwise_known: bool


@dataclass(frozen=True)
class Classification:
    kind: str | None      # equivalent_overlap, predicted_configuration_conflict, potential_conflict, defined_precedence, unknown_semantics
    certainty: str
    rule: str | None
    detail: str
    admitted: bool        # an admitted rule compared two different values (so an overlap cohort is meaningful)


def _simple(value):
    return ('simple', value['@odata.type'], value['value'])


def flatten(normalized_body, profile, realm_id, tenant_id):
    """All setting instances of one normalized policy body, keyed for comparison. Unsupported shapes never reach here."""
    found = {}

    def add(canon, definition_id, scope, prefix, item, value, itemwise_known=True):
        path = '/'.join(prefix + [canon])
        key = (realm_id, tenant_id, 'windows10', scope, canon, path, item)
        found[key] = Instance(key, definition_id, canon, path, item, value, itemwise_known)

    def walk(instance, prefix):
        definition_id = instance['settingDefinitionId']
        canon = profile.canonical(definition_id)
        entry = profile.definition(definition_id)
        scope = entry['scope'] if entry else 'unknown'
        kind = instance['@odata.type']
        if kind.endswith('ChoiceSettingInstance'):
            choice = instance['choiceSettingValue']
            add(canon, definition_id, scope, prefix, None, ('choice', choice['value']))
            for child in choice['children']:
                walk(child, prefix + [f'{canon}={choice["value"]}'])
        elif kind.endswith('SimpleSettingCollectionInstance'):
            values = [_simple(v) for v in instance['simpleSettingCollectionValue']]
            if entry and entry.get('collection_mode') == 'itemwise':
                for value in values:
                    add(canon, definition_id, scope, prefix, canonical(list(value)).decode(), ('item',))
            else:
                add(canon, definition_id, scope, prefix, None,
                    ('collection', tuple(sorted(values, key=lambda v: canonical(list(v))))), itemwise_known=False)
        else:
            add(canon, definition_id, scope, prefix, None, _simple(instance['simpleSettingValue']))

    for row in normalized_body['settings']['settings']:
        walk(row['settingInstance'], [])
    return found


def value_text(instance):
    value = instance.value
    if value[0] == 'choice':
        return value[1]
    if value[0] == 'item':
        return f'collection item {instance.item}'
    if value[0] == 'collection':
        return 'collection ' + canonical([list(v) for v in value[1]]).decode()
    return repr(value[2])


def classify(profile, a, b, lower_overlap, upper_overlap):
    """Classify two instances with the same key by value and by definite or possible target overlap."""
    if a.value == b.value:
        if not upper_overlap:
            return None
        return Classification('equivalent_overlap', 'definite_under_model' if lower_overlap else 'possible', None,
                              'same canonical value in a compatible context; redundancy, not a conflict', False)
    entry = profile.definition(a.definition_id)
    if entry is None:
        return Classification('unknown_semantics' if upper_overlap else None, 'unknown', None,
                              'the setting definition is not in the semantics profile', False)
    precedence = entry.get('precedence')
    if precedence and upper_overlap and a.value[0] in ('choice', 'simple'):
        winner = [x for x in (a, b) if x.value[-1] == precedence['prefer_value']]
        if len(winner) == 1:
            return Classification('defined_precedence', 'definite_under_model' if lower_overlap else 'possible',
                                  None, f'value {precedence["prefer_value"]} wins by a sourced rule ({precedence["source"]})', False)
    rule = entry.get('conflict_rule')
    if rule and a.itemwise_known and b.itemwise_known:
        if lower_overlap:
            return Classification('predicted_configuration_conflict', 'definite_under_model', rule,
                                  'incompatible values over a definite overlap', True)
        if upper_overlap:
            return Classification('potential_conflict', 'possible', rule,
                                  'incompatible values over a possible overlap', True)
        return Classification(None, 'definite_under_model', rule, 'incompatible values over no overlap', True)
    if not upper_overlap:
        return None
    return Classification('unknown_semantics', 'unknown', None,
                          'no admitted conflict rule or merge mode for this setting', False)
