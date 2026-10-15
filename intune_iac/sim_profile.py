"""The versioned semantics profile of the simulator.

Everything the evaluator is allowed to assume about Intune lives here and is hashed into the result: which filter
properties and operators are admitted, how an observed null compares, how confident a user-on-device relation is,
and, per setting definition, the scope, the canonical identity, whether duplicate values conflict, how a
collection merges and any sourced precedence. A definition the profile does not name is unknown semantics, never
a guessed rule. The seed profile below is a synthetic starting point for fixtures and tests; its filter grammar is
not yet checked against the vendor documentation and says so in its provenance field.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from .io import AppError, digest

SCHEMA = 'intune-sim-semantics/1'
TRUTH = ('T', 'F')

DEFAULT = {
    'schema': SCHEMA,
    'version': '1',
    'provenance': 'synthetic seed profile; filter properties and operators are not yet verified against vendor documentation',
    'filters': {
        'properties': {'osVersion': 'version', 'manufacturer': 'string', 'model': 'string', 'deviceOwnership': 'string',
                       'deviceName': 'string', 'operatingSystemSKU': 'string', 'enrollmentProfileName': 'string'},
        'null_truth': {'-eq': 'F', '-ne': 'T', '-contains': 'F', '-notContains': 'T', '-startsWith': 'F',
                       '-in': 'F', '-notIn': 'T', '-gt': 'F', '-ge': 'F', '-lt': 'F', '-le': 'F'},
    },
    'eligibility': {'signed_in': 'T', 'primary_user': 'U', 'enrollment_owner': 'U', 'shared_device': 'U'},
    'definitions': {},
    'aliases': {},
    'virtual_targets': {'write_support': 'review_only'},
    'external_management_collected': False,
    'max_uncertain_assignments': 10,
}
_TOP = set(DEFAULT)
_DEFINITION_KEYS = {'scope', 'canonical', 'conflict_rule', 'collection_mode', 'precedence'}


def _fail(where, reason):
    raise AppError('sim_profile_invalid', f'Semantics profile is invalid at {where}: {reason}.')


@dataclass(frozen=True, eq=False)
class Profile:
    doc: dict
    sha256: str

    @property
    def filter_properties(self):
        return self.doc['filters']['properties']

    @property
    def null_truth(self):
        return self.doc['filters']['null_truth']

    @property
    def eligibility(self):
        return self.doc['eligibility']

    @property
    def max_uncertain(self):
        return self.doc['max_uncertain_assignments']

    @property
    def external_management_collected(self):
        return self.doc['external_management_collected']

    def canonical(self, definition_id):
        """The canonical identity of a setting definition, following only explicitly declared aliases."""
        return self.doc['aliases'].get(definition_id, definition_id)

    def definition(self, definition_id):
        return self.doc['definitions'].get(self.canonical(definition_id))


def default_profile():
    return load_profile({})


def load_profile(doc):
    if type(doc) is not dict or set(doc) - _TOP:
        _fail('profile', 'an object with known keys is required')
    merged = copy.deepcopy(DEFAULT)
    for key, value in doc.items():
        if key in ('filters', 'eligibility', 'virtual_targets'):
            if type(value) is not dict or set(value) - set(DEFAULT[key]):
                _fail(key, 'unsupported keys')
            for inner, given in value.items():
                merged[key][inner] = copy.deepcopy(given)
        else:
            merged[key] = copy.deepcopy(value)
    if merged['schema'] != SCHEMA:
        _fail('schema', 'unsupported schema version')
    if type(merged['max_uncertain_assignments']) is not int or not 0 <= merged['max_uncertain_assignments'] <= 16:
        _fail('max_uncertain_assignments', 'an integer from 0 to 16 is required')
    if type(merged['external_management_collected']) is not bool:
        _fail('external_management_collected', 'a boolean is required')
    for name, kind in merged['filters']['properties'].items():
        if kind not in ('string', 'version'):
            _fail('filters/properties/' + name, 'unknown property type')
    for op, value in merged['filters']['null_truth'].items():
        if value not in TRUTH:
            _fail('filters/null_truth/' + op, 'T or F is required')
    for name, value in merged['eligibility'].items():
        if value not in TRUTH + ('U',):
            _fail('eligibility/' + name, 'T or U is required')
    if type(merged['aliases']) is not dict or not all(type(k) is str and type(v) is str for k, v in merged['aliases'].items()):
        _fail('aliases', 'a map of strings is required')
    if type(merged['definitions']) is not dict:
        _fail('definitions', 'an object is required')
    for name, entry in merged['definitions'].items():
        where = 'definitions/' + name
        if type(entry) is not dict or set(entry) - _DEFINITION_KEYS or entry.get('scope') not in ('device', 'user'):
            _fail(where, 'a scope of device or user and known keys are required')
        if entry.get('conflict_rule') not in (None, 'different_value_conflicts'):
            _fail(where, 'unknown conflict rule')
        if entry.get('collection_mode') not in (None, 'itemwise'):
            _fail(where, 'unknown collection mode')
        precedence = entry.get('precedence')
        if precedence is not None and (type(precedence) is not dict or set(precedence) != {'prefer_value', 'source'}
                                       or type(precedence['source']) is not str or not precedence['source']):
            _fail(where, 'precedence needs a preferred value and a source')
    return Profile(merged, digest(merged))
