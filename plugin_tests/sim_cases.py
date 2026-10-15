"""Shared harness for the simulator tests: runs a scenario, validates the result and checks the set invariants.

Expected cohorts are always written by hand in the tests. Nothing here computes a targeting answer; the only
calls into the product are the loaders, `simulate`, and the result validator, whose job is to reject bad output.
"""
import copy

from intune_iac import sim_eval, sim_model, sim_profile, sim_result
from plugin_tests import sim_support as s

V1 = s.DEF + '_1'
V2 = s.DEF + '_2'

PROFILE = {
    'definitions': {
        s.DEF: {'scope': 'device', 'canonical': s.DEF, 'conflict_rule': 'different_value_conflicts'},
        s.DEF_B: {'scope': 'device', 'canonical': s.DEF_B, 'conflict_rule': 'different_value_conflicts'},
        s.DEF_CHILD: {'scope': 'device', 'canonical': s.DEF_CHILD, 'conflict_rule': 'different_value_conflicts'},
        s.DEF_COLLECTION: {'scope': 'device', 'canonical': s.DEF_COLLECTION, 'collection_mode': 'itemwise',
                           'conflict_rule': 'different_value_conflicts'},
    }}


def profile(extra=None):
    doc = copy.deepcopy(PROFILE)
    doc.update(copy.deepcopy(extra or {}))
    return sim_profile.load_profile(doc)


def ids(kind, *names):
    return frozenset(s.uid(kind + '/' + n) for n in names)


def devs(*names):
    return ids('device', *names)


def simulate(snapshot_doc, revision_doc=None, prof=None):
    snapshot = sim_model.load_snapshot(snapshot_doc)
    revision = sim_model.load_revision(revision_doc if revision_doc is not None else s.revision_doc())
    prof = prof or profile()
    result = sim_eval.simulate(snapshot, revision, prof)
    doc = result.to_schema()
    sim_result.validate_result(doc)
    assert_sound(result, doc)
    return result, doc


def cohort(doc, cohort_id):
    found = [c for c in doc['cohorts'] if c['cohort_id'] == cohort_id]
    assert len(found) == 1, (cohort_id, [c['cohort_id'] for c in doc['cohorts']])
    return found[0]


def bounds(doc, policy_name, kind, unit='unique_devices'):
    c = cohort(doc, f'policy:{s.uid("policy/" + policy_name)}:{kind}:{unit}')
    return c['lower'], c['upper']


def aggregate(doc, kind, unit='unique_devices', suffix=''):
    c = cohort(doc, f'changed:{kind}:{unit}{suffix}')
    return c['lower'], c['upper']


def finding_ids(doc, prefix=''):
    return [f['id'] for f in doc['findings'] if f['id'].startswith(prefix)]


def findings(doc, kind):
    return [f for f in doc['findings'] if f['kind'] == kind]


def after_sets(result, policy_name, world='after'):
    entry = result.detail['policies'][s.uid('policy/' + policy_name)][world]
    return entry['lower_devices'], entry['upper_devices']


def assert_sound(result, doc):
    """L is inside U for every policy and world, bounds are ordered, and the cohort numbers follow the model table."""
    for pid, worlds in result.detail['policies'].items():
        for world, entry in worlds.items():
            assert entry['lower_devices'] <= entry['upper_devices'], (pid, world, 'devices')
            assert entry['lower_contexts'] <= entry['upper_contexts'], (pid, world, 'contexts')
        l0, u0 = worlds['before']['lower_devices'], worlds['before']['upper_devices']
        l1, u1 = worlds['after']['lower_devices'], worlds['after']['upper_devices']
        expected = {'before': (len(l0), len(u0)), 'after': (len(l1), len(u1)),
                    'added': (len(l1 - u0), len(u1 - l0)), 'removed': (len(l0 - u1), len(u0 - l1)),
                    'retained': (len(l0 & l1), len(u0 & u1))}
        for kind, want in expected.items():
            got = cohort(doc, f'policy:{pid}:{kind}:unique_devices')
            assert (got['lower'], got['upper']) == want, (pid, kind, got, want)
    for c in doc['cohorts']:
        assert c['upper'] is None or c['lower'] <= c['upper'], c
