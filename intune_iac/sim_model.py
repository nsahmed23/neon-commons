"""Typed, immutable snapshot and proposed-revision entities for the blast-radius and conflict simulator.

The simulator's input is a value, never a live store. A snapshot is built once from a document (or from a synthetic
estate plus a device population), validated strictly, hashed over its canonical content so list order cannot change
its identity, and then only read. Every collected fact carries its presence state; an unlisted collection is
uncollected (presence unknown), which is a different thing from an empty collection that was fully read.
Identifiers are the keys; display names are labels and may repeat.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from types import MappingProxyType

from .io import AppError, canonical, digest

SNAPSHOT_SCHEMA = 'intune-sim-snapshot/1'
REVISION_SCHEMA = 'intune-sim-revision/1'
PRESENCE = ('known', 'observed_null', 'absent', 'unknown', 'redacted', 'unsupported')
COLLECTIONS = ('devices', 'users', 'user_device_contexts', 'groups', 'memberships', 'filters', 'policies',
               'assignments', 'rings')
RELATIONS = ('signed_in', 'primary_user', 'enrollment_owner')
SHARING = ('personal', 'shared', 'userless')
MEMBER_DOMAINS = ('user', 'device', 'mixed', 'unknown')
_HEX64 = re.compile(r'^[0-9a-f]{64}$')
MAX_ITEMS = 2_000_000


def _fail(where, reason):
    raise AppError('sim_snapshot_invalid', f'Simulator input is invalid at {where}: {reason}.')


def _exact(obj, required, optional, where):
    if type(obj) is not dict:
        _fail(where, 'an object is required')
    missing = required - set(obj)
    extra = set(obj) - required - optional
    if missing or extra:
        _fail(where, 'missing ' + ','.join(sorted(missing)) if missing else 'unsupported keys ' + ','.join(sorted(map(str, extra))))
    return obj


def _text(value, where):
    if type(value) is not str or not value or len(value) > 4096:
        _fail(where, 'a non-empty bounded string is required')
    return value


def _list(value, where):
    if type(value) is not list or len(value) > MAX_ITEMS:
        _fail(where, 'a bounded list is required')
    return value


@dataclass(frozen=True)
class Fact:
    """One collected value with the state it was collected in. `value` is None unless presence is `known`."""
    value: object
    presence: str
    observed_at: str | None
    source_ref: str | None
    source_sha256: str | None


@dataclass(frozen=True)
class CollectionState:
    name: str
    presence: str          # known: this collection was read; unknown: it was never collected
    complete: bool
    reason: str | None


@dataclass(frozen=True)
class Device:
    id: str
    entra_device_id: Fact
    entra_object_id: Fact
    id_resolution: str
    sharing: str
    properties: object


@dataclass(frozen=True)
class User:
    id: str


@dataclass(frozen=True)
class UserDeviceContext:
    user_id: str
    device_id: str
    relation: str
    certainty: str


@dataclass(frozen=True)
class Group:
    id: str
    display_name: str
    member_domain: str
    kind: str
    membership_complete: bool


@dataclass(frozen=True)
class Filter:
    id: str
    display_name: str
    platform: str
    expression: Fact


@dataclass(frozen=True)
class PolicyRecord:
    id: str
    family: str
    source_path: str | None
    body_json: str
    incomplete_reason: str | None

    @property
    def body(self):
        return json.loads(self.body_json)

    @property
    def sha256(self):
        return digest({'id': self.id, 'family': self.family, 'body': self.body})


@dataclass(frozen=True)
class Ring:
    ring_id: str
    name: str
    order: int
    device_ids: frozenset
    group_ids: tuple


@dataclass(frozen=True, eq=False)
class Snapshot:
    snapshot_id: str
    realm_id: str
    tenant_id: str
    cloud: str
    captured_start: str
    captured_end: str
    collections: object
    devices: tuple
    users: tuple
    contexts: tuple
    groups: tuple
    group_by_id: object
    members_known: object
    members_possible: object
    filters: tuple
    filter_by_id: object
    policies: tuple
    policy_by_id: object
    rings: tuple
    sha256: str


@dataclass(frozen=True, eq=False)
class ProposedRevision:
    revision_id: str
    source_ref: str
    policies: tuple
    removed_policy_ids: frozenset
    sha256: str


def _fact(raw, defaults, where):
    if type(raw) is dict and 'presence' in raw:
        _exact(raw, {'presence'}, {'value', 'observed_at', 'source_ref', 'source_sha256'}, where)
        presence = raw['presence']
        if presence not in PRESENCE:
            _fail(where, 'unknown presence word')
        value = raw.get('value')
        if presence == 'known':
            if value is None:
                _fail(where, 'a known fact needs a value; use observed_null for a null that was read')
        elif value is not None:
            _fail(where, 'presence ' + presence + ' carries no value')
        meta = {k: raw.get(k, defaults[k]) for k in ('observed_at', 'source_ref', 'source_sha256')}
    elif raw is None or type(raw) in (dict, list):
        _fail(where, 'a scalar value or a presence object is required; JSON null is not a fact')
    else:
        presence, value, meta = 'known', raw, dict(defaults)
    if meta['source_sha256'] is not None and not _HEX64.match(str(meta['source_sha256'])):
        _fail(where, 'source_sha256 must be 64 lowercase hex characters')
    return Fact(value, presence, meta['observed_at'], meta['source_ref'], meta['source_sha256'])


def _sorted_by_content(items):
    return sorted(items, key=canonical)


def _normalize(doc):
    """Return a copy with every collection in content order, so list order never changes the hash."""
    out = json.loads(canonical(doc))
    for name in ('devices', 'users', 'user_device_contexts', 'groups', 'memberships', 'filters', 'policies', 'rings'):
        if isinstance(out.get(name), list):
            out[name] = _sorted_by_content(out[name])
    for ring in out.get('rings', []) if isinstance(out.get('rings'), list) else []:
        for key in ('device_ids', 'group_ids'):
            if isinstance(ring.get(key), list):
                ring[key] = sorted(ring[key], key=str)
    return out


def _unique(rows, key, where):
    seen = set()
    for row in rows:
        ident = getattr(row, key)
        if ident in seen:
            _fail(where, 'duplicate identifier')
        seen.add(ident)


def _collections(doc, defaults):
    declared = doc.get('collections', {})
    if type(declared) is not dict or set(declared) - set(COLLECTIONS):
        _fail('collections', 'an object keyed by known collection names is required')
    states = {}
    for name in COLLECTIONS:
        entry = declared.get(name)
        present = name in doc or (name == 'assignments' and 'policies' in doc)
        if entry is not None:
            _exact(entry, set(), {'complete', 'reason', 'presence'}, 'collections/' + name)
            complete = entry.get('complete', True)
            if type(complete) is not bool:
                _fail('collections/' + name, 'complete must be a boolean')
            presence = entry.get('presence', 'known' if present else 'unknown')
            if presence not in PRESENCE:
                _fail('collections/' + name, 'unknown presence word')
            states[name] = CollectionState(name, presence, complete and presence == 'known', entry.get('reason'))
        elif present:
            states[name] = CollectionState(name, 'known', True, None)
        else:
            states[name] = CollectionState(name, 'unknown', False, 'collection_not_collected')
    return MappingProxyType(states)


def load_snapshot(doc):
    """Build the immutable typed snapshot from a synthetic or approved document; strict about every key."""
    optional = set(COLLECTIONS) - {'assignments'} | {'collections'}
    _exact(doc, {'schema', 'snapshot_id', 'realm_id', 'tenant_id', 'cloud', 'captured_start', 'captured_end',
                 'observed_at', 'source_ref', 'source_sha256'}, optional, 'snapshot')
    if doc['schema'] != SNAPSHOT_SCHEMA:
        _fail('schema', 'unsupported schema version')
    defaults = {'observed_at': _text(doc['observed_at'], 'observed_at'),
                'source_ref': _text(doc['source_ref'], 'source_ref'), 'source_sha256': doc['source_sha256']}
    if not _HEX64.match(str(doc['source_sha256'])):
        _fail('source_sha256', 'must be 64 lowercase hex characters')
    for key in ('snapshot_id', 'realm_id', 'tenant_id', 'cloud', 'captured_start', 'captured_end'):
        _text(doc[key], key)
    states = _collections(doc, defaults)

    devices = []
    for i, raw in enumerate(_list(doc.get('devices', []), 'devices')):
        where = f'devices/{i}'
        _exact(raw, {'id'}, {'entra_device_id', 'entra_object_id', 'sharing', 'properties'}, where)
        sharing = raw.get('sharing', 'personal')
        if sharing not in SHARING:
            _fail(where, 'unknown sharing kind')
        absent = {'presence': 'unknown'}
        entra_device = _fact(raw.get('entra_device_id', absent), defaults, where + '/entra_device_id')
        entra_object = _fact(raw.get('entra_object_id', absent), defaults, where + '/entra_object_id')
        props = raw.get('properties', {})
        if type(props) is not dict:
            _fail(where, 'properties must be an object')
        facts = {_text(k, where): _fact(v, defaults, f'{where}/properties/{k}') for k, v in sorted(props.items())}
        both = entra_device.presence == 'known' and entra_object.presence == 'known'
        devices.append(Device(_text(raw['id'], where), entra_device, entra_object,
                              'resolved' if both else 'unresolved', sharing, MappingProxyType(facts)))
    _unique(devices, 'id', 'devices')
    device_ids = {d.id for d in devices}

    users = tuple(User(_text(_exact(r, {'id'}, set(), f'users/{i}')['id'], f'users/{i}'))
                  for i, r in enumerate(_list(doc.get('users', []), 'users')))
    _unique(users, 'id', 'users')

    contexts = []
    for i, raw in enumerate(_list(doc.get('user_device_contexts', []), 'user_device_contexts')):
        where = f'user_device_contexts/{i}'
        _exact(raw, {'user_id', 'device_id', 'relation', 'certainty'}, set(), where)
        if raw['relation'] not in RELATIONS or raw['certainty'] not in ('known', 'possible'):
            _fail(where, 'unknown relation or certainty')
        contexts.append(UserDeviceContext(_text(raw['user_id'], where), _text(raw['device_id'], where),
                                          raw['relation'], raw['certainty']))
    if len({(c.user_id, c.device_id, c.relation) for c in contexts}) != len(contexts):
        _fail('user_device_contexts', 'duplicate context')

    groups = []
    for i, raw in enumerate(_list(doc.get('groups', []), 'groups')):
        where = f'groups/{i}'
        _exact(raw, {'id', 'member_domain'}, {'display_name', 'type', 'membership_complete'}, where)
        if raw['member_domain'] not in MEMBER_DOMAINS:
            _fail(where, 'unknown member domain')
        complete = raw.get('membership_complete', True)
        if type(complete) is not bool:
            _fail(where, 'membership_complete must be a boolean')
        groups.append(Group(_text(raw['id'], where), str(raw.get('display_name', '')), raw['member_domain'],
                            str(raw.get('type', 'unknown')), complete))
    _unique(groups, 'id', 'groups')
    group_by_id = MappingProxyType({g.id: g for g in groups})

    known, possible = {g.id: set() for g in groups}, {g.id: set() for g in groups}
    for i, raw in enumerate(_list(doc.get('memberships', []), 'memberships')):
        where = f'memberships/{i}'
        _exact(raw, {'group_id', 'member_id', 'member_kind', 'certainty'}, set(), where)
        if raw['member_kind'] not in ('user', 'device') or raw['certainty'] not in ('known', 'possible'):
            _fail(where, 'unknown member kind or certainty')
        gid = _text(raw['group_id'], where)
        if gid not in group_by_id:
            _fail(where, 'membership names a group that is not in the snapshot')
        domain = group_by_id[gid].member_domain
        if domain in ('user', 'device') and domain != raw['member_kind']:
            _fail(where, 'member kind does not match the group member domain')
        (known if raw['certainty'] == 'known' else possible)[gid].add(_text(raw['member_id'], where))
    members_known = MappingProxyType({k: frozenset(v) for k, v in known.items()})
    members_possible = MappingProxyType({k: frozenset(v - known[k]) for k, v in possible.items()})

    filters = []
    for i, raw in enumerate(_list(doc.get('filters', []), 'filters')):
        where = f'filters/{i}'
        _exact(raw, {'id', 'expression'}, {'display_name', 'platform'}, where)
        filters.append(Filter(_text(raw['id'], where), str(raw.get('display_name', '')),
                              str(raw.get('platform', 'unknown')), _fact(raw['expression'], defaults, where + '/expression')))
    _unique(filters, 'id', 'filters')

    policies = _policies(_list(doc.get('policies', []), 'policies'), 'policies')
    rings = []
    for i, raw in enumerate(_list(doc.get('rings', []), 'rings')):
        where = f'rings/{i}'
        _exact(raw, {'ring_id', 'name', 'order'}, {'device_ids', 'group_ids'}, where)
        if type(raw['order']) is not int:
            _fail(where, 'order must be an integer')
        rings.append(Ring(_text(raw['ring_id'], where), _text(raw['name'], where), raw['order'],
                          frozenset(map(str, _list(raw.get('device_ids', []), where))),
                          tuple(sorted(map(str, _list(raw.get('group_ids', []), where))))))
    _unique(rings, 'ring_id', 'rings')
    del device_ids

    normalized = _normalize(doc)
    return Snapshot(
        snapshot_id=doc['snapshot_id'], realm_id=doc['realm_id'], tenant_id=doc['tenant_id'], cloud=doc['cloud'],
        captured_start=doc['captured_start'], captured_end=doc['captured_end'], collections=states,
        devices=tuple(sorted(devices, key=lambda d: d.id)), users=tuple(sorted(users, key=lambda u: u.id)),
        contexts=tuple(sorted(contexts, key=lambda c: (c.user_id, c.device_id, c.relation))),
        groups=tuple(sorted(groups, key=lambda g: g.id)), group_by_id=group_by_id,
        members_known=members_known, members_possible=members_possible,
        filters=tuple(sorted(filters, key=lambda f: f.id)),
        filter_by_id=MappingProxyType({f.id: f for f in filters}),
        policies=tuple(sorted(policies, key=lambda p: p.id)), policy_by_id=MappingProxyType({p.id: p for p in policies}),
        rings=tuple(sorted(rings, key=lambda r: r.ring_id)), sha256=digest(normalized))


def _policies(rows, where):
    policies = []
    for i, raw in enumerate(rows):
        here = f'{where}/{i}'
        _exact(raw, {'id', 'body'}, {'family', 'source_path', 'incomplete_reason'}, here)
        if type(raw['body']) is not dict:
            _fail(here, 'body must be an object')
        reason = raw.get('incomplete_reason')
        if reason is not None:
            _text(reason, here)
        path = raw.get('source_path')
        policies.append(PolicyRecord(_text(raw['id'], here), str(raw.get('family', 'settings_catalog')),
                                     None if path is None else _text(path, here), canonical(raw['body']).decode(), reason))
    _unique(policies, 'id', where)
    return policies


def load_revision(doc):
    """The proposed repository revision: replacement or added policies and the ids it removes."""
    _exact(doc, {'schema', 'revision_id', 'source_ref', 'policies'}, {'removed_policy_ids'}, 'revision')
    if doc['schema'] != REVISION_SCHEMA:
        _fail('schema', 'unsupported schema version')
    policies = _policies(_list(doc['policies'], 'policies'), 'revision/policies')
    removed = frozenset(_text(x, 'removed_policy_ids') for x in _list(doc.get('removed_policy_ids', []), 'removed_policy_ids'))
    if removed & {p.id for p in policies}:
        _fail('removed_policy_ids', 'a policy cannot be both changed and removed')
    normalized = _normalize(doc)
    normalized['policies'] = _sorted_by_content(normalized['policies'])
    normalized['removed_policy_ids'] = sorted(removed)
    return ProposedRevision(_text(doc['revision_id'], 'revision_id'), _text(doc['source_ref'], 'source_ref'),
                            tuple(sorted(policies, key=lambda p: p.id)), removed, digest(normalized))


# ---- the synthetic estate adapter -------------------------------------------------------------------------------

_NS = '#microsoft.graph.'


def _rows(collection):
    rows = []
    for page in collection.get('pages', []):
        value = page.get('body', {}).get('value')
        if not isinstance(value, list):
            return None
        rows.extend(value)
    return rows


def _collection_problem(collection):
    """Why a captured collection cannot be read as complete, or None."""
    if collection is None:
        return 'collection_not_collected'
    if collection.get('coverage') != 'complete':
        return str(collection.get('coverage'))
    pages = collection.get('pages', [])
    urls = [p.get('request_url') for p in pages]
    if len(set(urls)) != len(urls):
        return 'pagination_incomplete'
    if not pages or any('@odata.nextLink' in p.get('body', {}) for p in pages[-1:]):
        return 'pagination_incomplete'
    if _rows(collection) is None:
        return 'malformed_page'
    return None


def _project_assignment(target):
    row = {'type': str(target['@odata.type']).removeprefix(_NS), 'filter_type': target['deviceAndAppManagementAssignmentFilterType']}
    if target.get('groupId') is not None:
        row['group_id'] = target['groupId']
    if target.get('deviceAndAppManagementAssignmentFilterId') is not None:
        row['filter_id'] = target['deviceAndAppManagementAssignmentFilterId']
    return row


def snapshot_from_estate(estate, population=None, *, realm_id='synthetic'):
    """Adapt a seeded synthetic estate (`synthetic.generate_estate`) into a snapshot.

    Policies, settings, assignments, group and filter identities, the tenant and the capture time come from the
    estate's own capture; nothing is re-authored. The estate carries no devices, users, memberships or filter
    expressions, so those come only from an explicit `population`; without it the device universe is uncollected.
    """
    population = population or {}
    unsupported = set(population) - {'devices', 'users', 'user_device_contexts', 'memberships', 'rings',
                                     'group_domains', 'complete_groups', 'filter_expressions'}
    if unsupported:
        _fail('population', 'unsupported keys ' + ','.join(sorted(unsupported)))
    capture = estate['capture']
    by_kind = {}
    for collection in capture['collections']:
        by_kind.setdefault((collection['kind'], collection.get('owner_id')), collection)
    policy_rows = _rows(by_kind[('policies', None)]) or []
    problems = {'policies': _collection_problem(by_kind.get(('policies', None))), 'assignments': None, 'settings': None}
    policies = []
    for row in policy_rows:
        oid = row['id']
        settings_c, assign_c = by_kind.get(('settings', oid)), by_kind.get(('assignments', oid))
        reasons = []
        for kind, collection in (('settings', settings_c), ('assignments', assign_c)):
            problem = _collection_problem(collection)
            if problem:
                reasons.append(f'{kind}:{problem}')
                problems[kind] = problems[kind] or problem
        settings = [{k: v for k, v in r.items() if k != '@odata.type'} for r in (_rows(settings_c) or [])] if settings_c else []
        assignments = [_project_assignment(r['target']) for r in (_rows(assign_c) or [])] if assign_c else []
        body = {'name': row['name'], 'description': row['description'], 'platforms': row['platforms'],
                'technologies': [t for t in str(row['technologies']).split(',') if t],
                'role_scope_tag_ids': list(row['roleScopeTagIds']), 'settings': {'settings': settings},
                'assignments': assignments}
        record = {'id': oid, 'family': 'settings_catalog', 'body': body}
        if reasons:
            record['incomplete_reason'] = ','.join(reasons)
        policies.append(record)
    references = capture.get('references', [])
    domains = population.get('group_domains', {})
    complete_groups = set(population.get('complete_groups', ()))
    expressions = population.get('filter_expressions', {})
    groups = [{'id': r['id'], 'display_name': r['id'], 'member_domain': domains.get(r['id'], 'unknown'),
               'type': 'unknown', 'membership_complete': r['id'] in complete_groups}
              for r in references if r['kind'] == 'group']
    filters = []
    for r in references:
        if r['kind'] != 'filter':
            continue
        given = expressions.get(r['id'])
        filters.append({'id': r['id'], 'display_name': r['id'], 'platform': (given or {}).get('platform', 'unknown'),
                        'expression': given['expression'] if given else {'presence': 'unknown'}})
    collections = {'policies': {'complete': problems['policies'] is None, 'reason': problems['policies']},
                   'assignments': {'complete': problems['assignments'] is None, 'reason': problems['assignments']},
                   'filters': {'complete': True}}
    if problems['assignments'] == 'collection_not_collected':
        collections['assignments'] = {'complete': False, 'presence': 'unknown', 'reason': problems['assignments']}
    for key in ('devices', 'users', 'user_device_contexts', 'memberships', 'rings'):
        if key in population:
            collections[key] = {'complete': True}
    doc = {'schema': SNAPSHOT_SCHEMA, 'snapshot_id': estate['case_id'], 'realm_id': realm_id,
           'tenant_id': capture['tenant_id'], 'cloud': capture['cloud'], 'captured_start': capture['captured_at'],
           'captured_end': capture['captured_at'], 'observed_at': capture['captured_at'],
           'source_ref': 'synthetic-estate:' + estate['case_id'], 'source_sha256': digest(capture),
           'groups': groups, 'filters': filters, 'policies': policies, 'collections': collections}
    for key in ('devices', 'users', 'user_device_contexts', 'memberships', 'rings'):
        if key in population:
            doc[key] = population[key]
    return load_snapshot(doc)
