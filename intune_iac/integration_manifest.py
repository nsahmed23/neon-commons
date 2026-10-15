"""The Intune integration manifest (integration-manifest/1): loaded, checked and returned as plain data.

contracts/integration-manifest.json states, from facts the repository already holds, what the Intune integration is
and what it implements: object kinds and their operations, input formats, setup pins, host profiles, evidence
classes, required scopes and one entry per row of family-coverage.csv. It is a catalog, not a qualification. An
object kind carries one of the guide's level words only where its level_record names the repository record that
establishes it; otherwise its level is unknown, and a level is never inferred from the existence of code.

The loader checks the shape and the version and refuses anything else with an AppError. It reads no other file,
holds no state and changes no behaviour: moving constants to read from this file is a later step.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from .io import AppError, parse_json, read_bytes

VERSION = 'integration-manifest/1'
PATH = Path(__file__).resolve().parents[1] / 'contracts' / 'integration-manifest.json'
UNKNOWN = 'unknown'
LEVELS = (UNKNOWN, 'discover-only', 'export-only', 'review-only', 'adoption-qualified', 'change-qualified')
FAMILY_COLUMNS = ('family', 'candidate', 'material', 'release_stage', 'qualification_needed', 'live')

_TOP = ('schema_version', 'description', 'integration', 'input_formats', 'object_kinds', 'setup_context',
        'host_profiles', 'evidence_classes', 'live_blockers', 'required_scopes', 'families')
_INTEGRATION = ('id', 'label', 'product', 'product_version')
_FORMAT = ('id', 'schema_file', 'schema_id', 'schema_version', 'collection_kinds')
_KIND = ('id', 'label', 'family', 'input_formats', 'facets', 'operations', 'level', 'level_record', 'level_note')
_OPERATION = ('name', 'evidence_class')
_RECORD = ('path', 'quote', 'locator')
_FAMILY = FAMILY_COLUMNS + ('workbench_presence', 'object_kind')
_CONTEXT = ('pinned', 'start_context_keys')


def _bad(detail):
    raise AppError('integration_manifest_malformed', 'The integration manifest is malformed: ' + detail + '.')


def _keys(value, names, where):
    if not isinstance(value, dict):
        _bad(where + ' must be an object')
    if set(value) != set(names):
        _bad(where + ' must have exactly the keys ' + ', '.join(names))
    return value


def _text(value, where, empty=False):
    if not isinstance(value, str) or (not value and not empty):
        _bad(where + ' must be ' + ('a string' if empty else 'a non-empty string'))
    return value


def _list(value, where):
    if not isinstance(value, list):
        _bad(where + ' must be a list')
    return value


def _texts(value, where):
    for index, item in enumerate(_list(value, where)):
        _text(item, where + '[%d]' % index)
    return value


def _unique(values, where):
    if len(set(values)) != len(values):
        _bad(where + ' has a duplicate')


def _check_record(record, where):
    _keys(record, _RECORD, where)
    for name in _RECORD:
        _text(record[name], where + '.' + name)
    path = PurePosixPath(record['path'])
    if path.is_absolute() or '..' in path.parts or '\\' in record['path']:
        _bad(where + '.path must be a relative path inside the repository')


def _check_kind(kind, formats, where):
    _keys(kind, _KIND, where)
    for name in ('id', 'label', 'family', 'level_note'):
        _text(kind[name], where + '.' + name)
    _texts(kind['facets'], where + '.facets')
    _texts(kind['input_formats'], where + '.input_formats')
    unlisted = [name for name in kind['input_formats'] if name not in formats]
    if unlisted:
        _bad(where + '.input_formats names an input format the manifest does not list: ' + unlisted[0])
    for index, operation in enumerate(_list(kind['operations'], where + '.operations')):
        _keys(operation, _OPERATION, where + '.operations[%d]' % index)
        for name in _OPERATION:
            _text(operation[name], where + '.operations[%d].%s' % (index, name))
    if kind['level'] not in LEVELS:
        _bad(where + '.level must be one of ' + ', '.join(LEVELS))
    if kind['level'] == UNKNOWN:
        if kind['level_record'] is not None:
            _bad(where + '.level_record must be null while the level is unknown')
    else:
        _check_record(kind['level_record'], where + '.level_record')


def _check_family(entry, kinds, where):
    _keys(entry, _FAMILY, where)
    for name in FAMILY_COLUMNS + ('workbench_presence',):
        _text(entry[name], where + '.' + name, empty=True)
    if not entry['family']:
        _bad(where + '.family must be a non-empty string')
    if entry['object_kind'] is not None and entry['object_kind'] not in kinds:
        _bad(where + '.object_kind names an object kind the manifest does not list')


def _check(value):
    _keys(value, _TOP, 'the manifest')
    _text(value['description'], 'description')
    integration = _keys(value['integration'], _INTEGRATION, 'integration')
    for name in _INTEGRATION:
        _text(integration[name], 'integration.' + name)
    formats = {}
    for index, item in enumerate(_list(value['input_formats'], 'input_formats')):
        where = 'input_formats[%d]' % index
        _keys(item, _FORMAT, where)
        for name in ('id', 'schema_file', 'schema_id'):
            _text(item[name], where + '.' + name)
        if item['schema_version'] is not None:
            _text(item['schema_version'], where + '.schema_version')
        _texts(item['collection_kinds'], where + '.collection_kinds')
        formats[item['id']] = item
    if len(formats) != len(value['input_formats']):
        _bad('input_formats has a duplicate id')
    kinds = {}
    for index, kind in enumerate(_list(value['object_kinds'], 'object_kinds')):
        _check_kind(kind, formats, 'object_kinds[%d]' % index)
        kinds[kind['id']] = kind
    if len(kinds) != len(value['object_kinds']):
        _bad('object_kinds has a duplicate id')
    context = _keys(value['setup_context'], _CONTEXT, 'setup_context')
    if not isinstance(context['pinned'], dict):
        _bad('setup_context.pinned must be an object')
    _texts(context['start_context_keys'], 'setup_context.start_context_keys')
    profiles = value['host_profiles']
    if not isinstance(profiles, dict):
        _bad('host_profiles must be an object')
    for name, profile in profiles.items():
        _texts(_keys(profile, ('requires',), 'host_profiles.' + name)['requires'], 'host_profiles.%s.requires' % name)
    if not isinstance(value['evidence_classes'], dict):
        _bad('evidence_classes must be an object')
    for name, meaning in value['evidence_classes'].items():
        _keys(meaning, ('establishes', 'does_not_establish'), 'evidence_classes.' + name)
        _texts(meaning['establishes'], 'evidence_classes.%s.establishes' % name)
        _texts(meaning['does_not_establish'], 'evidence_classes.%s.does_not_establish' % name)
    _texts(value['live_blockers'], 'live_blockers')
    scopes = value['required_scopes']
    if not isinstance(scopes, dict):
        _bad('required_scopes must be an object')
    for name, scope in scopes.items():
        _text(scope, 'required_scopes.' + name)
    names = []
    for index, entry in enumerate(_list(value['families'], 'families')):
        _check_family(entry, kinds, 'families[%d]' % index)
        names.append(entry['family'])
    _unique(names, 'families')
    linked = {entry['object_kind']: entry['family'] for entry in value['families'] if entry['object_kind']}
    for identifier, kind in kinds.items():
        if linked.get(identifier) != kind['family']:
            _bad('object kind %s and the family entry %s do not name each other' % (identifier, kind['family']))
    return value


def load(path=None):
    """The manifest at path (default: the shipped one), checked; raises AppError with a code naming the failure."""
    try:
        data = read_bytes(PATH if path is None else path)
    except AppError:
        raise AppError('integration_manifest_unreadable', 'The integration manifest could not be read as a local file.') from None
    try:
        value = parse_json(data)
    except AppError:
        _bad('it is not JSON with unique keys, bounded depth and finite values')
    if not isinstance(value, dict):
        _bad('the top level must be an object')
    version = value.get('schema_version')
    if version != VERSION:
        raise AppError('integration_manifest_version_unsupported',
                       'The integration manifest has an unsupported version (found %s; this product reads %s).'
                       % (repr(version)[:80], VERSION))
    return _check(value)
