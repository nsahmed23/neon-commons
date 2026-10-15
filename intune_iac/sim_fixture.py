"""A reproducible synthetic fleet for checking and timing the simulator at scale.

`build_fleet` returns a snapshot document and a proposed revision from a seed alone: duplicate group display
names, multi-user and shared devices, possible memberships, unknown and read-null properties, overlapping rings,
and an optional incomplete devices collection. `measure` builds it, loads it and evaluates it with a monotonic
clock and reports what it saw. The numbers are a baseline on whatever host ran them; they are not a supported
operating limit and the model sets no speed target.

    python -m intune_iac.sim_fixture --devices 30000 --seed 1 --repeats 3
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import time
from uuid import UUID

from .io import digest
from .sim_eval import simulate
from .sim_model import SNAPSHOT_SCHEMA, REVISION_SCHEMA, load_revision, load_snapshot
from .sim_profile import load_profile
from .sim_result import validate_result

STAMP = '2026-10-15T12:00:00Z'
SOURCE_SHA = 'b' * 64
DEF = 'device_vendor_msft_policy_config_privacy_letappsaccesslocation'
NS = '#microsoft.graph.'
MODELS = ('M1', 'M2', 'M3', 'M4')
DEVICE_GROUPS = 10
_KINDS = {'device': 0xD, 'user': 0xE, 'group': 0xA, 'filter': 0xF, 'policy': 0xB, 'tenant': 0xC}


def _id(kind, seed, index):
    return str(UUID(int=(_KINDS[kind] << 120) | ((seed & 0xFFFFFFFF) << 64) | index))


def _setting(value):
    return [{'id': '0', 'settingInstance': {
        '@odata.type': NS + 'deviceManagementConfigurationChoiceSettingInstance',
        'settingDefinitionId': DEF, 'settingInstanceTemplateReference': None,
        'choiceSettingValue': {'@odata.type': NS + 'deviceManagementConfigurationChoiceSettingValue',
                               'settingValueTemplateReference': None, 'value': f'{DEF}_{value}', 'children': []}}}]


def _policy(seed, index, assignments, value):
    return {'id': _id('policy', seed, index), 'family': 'settings_catalog',
            'body': {'name': f'Fleet policy {index}', 'description': '', 'platforms': 'windows10', 'technologies': ['mdm'],
                     'role_scope_tag_ids': ['0'], 'settings': {'settings': _setting(value)}, 'assignments': assignments}}


def build_fleet(seed=1, devices=30000, complete=True):
    """Return (snapshot_document, revision_document); identical for identical arguments."""
    rng = random.Random(seed)
    users = max(1, devices * 3 // 4)
    dev = [_id('device', seed, i) for i in range(devices)]
    usr = [_id('user', seed, i) for i in range(users)]
    gd = [_id('group', seed, i) for i in range(DEVICE_GROUPS)]
    gu = [_id('group', seed, 100 + i) for i in range(2)]
    flt = [_id('filter', seed, i) for i in range(len(MODELS))]
    rows = []
    for i, ident in enumerate(dev):
        properties = {'manufacturer': rng.choice(('Dell', 'HP', 'Lenovo'))}
        if i % 97 == 0:
            properties['model'] = {'presence': 'unknown'}
        elif i % 211 == 0:
            properties['model'] = {'presence': 'observed_null'}
        else:
            properties['model'] = rng.choice(MODELS)
        rows.append({'id': ident, 'sharing': 'shared' if i % 500 == 0 else 'personal', 'properties': properties})
    contexts = []
    for i, ident in enumerate(dev):
        relation = 'primary_user' if i % 20 == 0 else 'signed_in'
        contexts.append({'user_id': usr[i % users], 'device_id': ident, 'relation': relation, 'certainty': 'known'})
        if i % 5 == 0 and users > 1:
            second = usr[(i * 7 + 1) % users]
            if second != usr[i % users]:
                contexts.append({'user_id': second, 'device_id': ident, 'relation': 'signed_in', 'certainty': 'known'})
    memberships = []
    for group in gd:
        for ident in dev:
            draw = rng.random()
            if draw < 0.12:
                memberships.append({'group_id': group, 'member_id': ident, 'member_kind': 'device', 'certainty': 'known'})
            elif draw < 0.124:
                memberships.append({'group_id': group, 'member_id': ident, 'member_kind': 'device', 'certainty': 'possible'})
    for group in gu:
        memberships += [{'group_id': group, 'member_id': u, 'member_kind': 'user', 'certainty': 'known'}
                        for u in usr if rng.random() < 0.3]
    groups = ([{'id': g, 'display_name': 'Fleet wave group', 'member_domain': 'device', 'type': 'static', 'membership_complete': True}
               for g in gd]
              + [{'id': g, 'display_name': f'Fleet users {i}', 'member_domain': 'user', 'type': 'static', 'membership_complete': True}
                 for i, g in enumerate(gu)])
    filters = [{'id': f, 'display_name': f'Model {m}', 'platform': 'windows10', 'expression': f'device.model -eq "{m}"'}
               for f, m in zip(flt, MODELS)]

    def inc(group, mode='none', filter_index=None):
        row = {'type': 'groupAssignmentTarget', 'group_id': group, 'filter_type': mode}
        if mode != 'none':
            row['filter_id'] = flt[filter_index]
        return row
    exc = {'type': 'exclusionGroupAssignmentTarget', 'group_id': gd[2], 'filter_type': 'none'}
    exc_device = {'type': 'exclusionGroupAssignmentTarget', 'group_id': gd[5], 'filter_type': 'none'}
    base = [_policy(seed, 0, [inc(gd[0]), inc(gd[1], 'include', 0), exc], 1),
            _policy(seed, 1, [inc(gd[3], 'exclude', 1), inc(gd[4])], 2),
            _policy(seed, 2, [inc(gu[0]), exc_device], 1),
            _policy(seed, 3, [inc(gd[6], 'include', 2), inc(gd[7], 'include', 3)], 2)]
    revision_policies = [_policy(seed, 0, [inc(gd[0]), inc(gd[1], 'exclude', 0)], 1),
                         _policy(seed, 1, [inc(gd[3], 'exclude', 1), inc(gd[4])], 1),
                         _policy(seed, 4, [inc(gu[1]), inc(gd[8]), {'type': 'exclusionGroupAssignmentTarget', 'group_id': gd[9], 'filter_type': 'none'}], 2)]
    rings = [{'ring_id': f'ring{r}', 'name': f'Wave {r}', 'order': r,
              'device_ids': [d for i, d in enumerate(dev) if i % modulus == 0]} for r, modulus in enumerate((10, 7, 11))]
    snapshot = {'schema': SNAPSHOT_SCHEMA, 'snapshot_id': f'fleet-{seed}-{devices}', 'realm_id': 'synthetic',
                'tenant_id': _id('tenant', seed, 0), 'cloud': 'public', 'captured_start': STAMP, 'captured_end': STAMP,
                'observed_at': STAMP, 'source_ref': 'synthetic-fleet', 'source_sha256': SOURCE_SHA,
                'devices': rows, 'users': [{'id': u} for u in usr], 'user_device_contexts': contexts, 'groups': groups,
                'memberships': memberships, 'filters': filters, 'policies': base, 'rings': rings}
    if not complete:
        snapshot['collections'] = {'devices': {'complete': False, 'reason': 'query_ceiling'}}
    revision = {'schema': REVISION_SCHEMA, 'revision_id': f'fleet-rev-{seed}', 'source_ref': 'synthetic-fleet-revision',
                'policies': revision_policies, 'removed_policy_ids': [base[2]['id']]}
    return snapshot, revision


def measure(seed=1, devices=30000, repeats=3, complete=True):
    """Build, load and evaluate the fleet; times are integers from time.monotonic_ns and always at least 1."""
    started = time.monotonic_ns()
    document, revision_document = build_fleet(seed, devices, complete)
    built = time.monotonic_ns()
    snapshot, revision, profile = load_snapshot(document), load_revision(revision_document), load_profile({})
    loaded = time.monotonic_ns()
    runs, result = [], None
    for _ in range(repeats):
        tick = time.monotonic_ns()
        result = simulate(snapshot, revision, profile)
        runs.append(max(1, time.monotonic_ns() - tick))
    doc = validate_result(result.to_schema())
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:
        peak = None
    return {'clock': 'time.monotonic_ns', 'seed': seed, 'devices': devices, 'repeats': repeats,
            'build_ns': max(1, built - started), 'load_snapshot_ns': max(1, loaded - built),
            'simulate_ns': runs, 'cold_simulate_ns': runs[0],
            'warm_simulate_min_ns': min(runs[1:]) if len(runs) > 1 else None,
            'cache_note': 'no cross-run cache exists; every evaluation rebuilds its index',
            'peak_rss_kib': peak, 'peak_rss_scope': 'whole process high-water mark, not the simulator alone',
            'collections': {'devices': len(document['devices']), 'user_device_contexts': len(document['user_device_contexts']),
                            'memberships': len(document['memberships']), 'policies': len(document['policies'])},
            'cohorts': len(doc['cohorts']), 'findings': len(doc['findings']), 'coverage': doc['coverage'],
            'result_sha256': digest(doc), 'python': platform.python_version(), 'host': platform.platform()}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Time the simulator on a reproducible synthetic fleet.')
    parser.add_argument('--devices', type=int, default=30000)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--incomplete', action='store_true', help='Mark the devices collection as truncated')
    args = parser.parse_args(argv)
    print(json.dumps(measure(args.seed, args.devices, args.repeats, not args.incomplete), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
