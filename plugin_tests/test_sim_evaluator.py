"""NT-2 item 2 and the set invariants of item 3: the pure evaluator and the result it serializes.

Cases: every produced result validates against the proposed JSON Schema and the consumer invariants the schema
leaves to the reader; unsupported families are reported, never evaluated; ids (not names) match policies; list
order never changes the answer; removing evidence never makes a result more precise; and fully known random
fixtures agree with the reference rule of the model, written out independently below.
"""
import copy
import random
import unittest

from intune_iac import sim_eval, sim_model, sim_result
from intune_iac.io import AppError
from intune_iac.synthetic import generate_estate
from plugin_tests import sim_support as s
from plugin_tests.sim_cases import V1, V2, after_sets, bounds, devs, finding_ids, findings, profile, simulate


def world(devices=('a', 'b'), members=('a', 'b'), **more):
    return s.snapshot_doc(devices=[s.device(d) for d in devices], groups=[s.group('gA')],
                          memberships=[s.member('gA', m) for m in members], **more)


def add(*policies, removed=()):
    return s.revision_doc(list(policies), removed=removed)


class ResultContract(unittest.TestCase):
    def setUp(self):
        self.snapshot_doc = world(policies=[s.policy('old', [s.include('gA')])])
        self.revision_doc = add(s.policy('p', [s.include('gA')]))
        self.result, self.doc = simulate(self.snapshot_doc, self.revision_doc)

    def test_the_result_is_bound_to_the_exact_inputs(self):
        snapshot = sim_model.load_snapshot(self.snapshot_doc)
        revision = sim_model.load_revision(self.revision_doc)
        binding = self.doc['input_binding']
        self.assertEqual(binding, {'realm_id': 'synthetic', 'snapshot_sha256': snapshot.sha256,
                                   'desired_source_sha256': revision.sha256, 'semantics_sha256': profile().sha256})
        self.assertEqual(self.doc['schema_version'], 1)
        self.assertEqual(self.doc['evidence_class'], 'synthetic_snapshot_simulation')

    def test_a_result_never_authorizes_execution_or_claims_endpoint_effect(self):
        self.assertIs(self.doc['live_execution_authorized'], False)
        self.assertIs(self.doc['endpoint_effective'], False)

    def test_an_approved_realm_is_labelled_as_such(self):
        _, doc = simulate(s.snapshot_doc(devices=[s.device('a')], realm_id='approved:tenant-1'), add(s.policy('p', [])))
        self.assertEqual(doc['evidence_class'], 'approved_snapshot_simulation')
        self.assertEqual(doc['coverage']['universe'], 'complete_declared_tenant_snapshot')

    def test_the_simulation_id_is_deterministic_and_follows_the_inputs(self):
        _, again = simulate(self.snapshot_doc, self.revision_doc)
        self.assertEqual(again['simulation_id'], self.doc['simulation_id'])
        _, other = simulate(self.snapshot_doc, add(s.policy('p', [s.include('gA')], description='x')))
        self.assertNotEqual(other['simulation_id'], self.doc['simulation_id'])

    def test_the_whole_result_is_deterministic(self):
        _, again = simulate(self.snapshot_doc, self.revision_doc)
        self.assertEqual(again, self.doc)

    def test_the_validator_rejects_a_bound_that_is_reversed(self):
        broken = copy.deepcopy(self.doc)
        broken['cohorts'][0]['lower'], broken['cohorts'][0]['upper'] = 5, 1
        with self.assertRaises(AppError):
            sim_result.validate_result(broken)

    def test_the_validator_rejects_extra_keys_and_authorization(self):
        for change in (lambda d: d.update(extra=1), lambda d: d.update(live_execution_authorized=True),
                       lambda d: d.update(endpoint_effective=True), lambda d: d['cohorts'][0].update(percent=50)):
            broken = copy.deepcopy(self.doc)
            change(broken)
            with self.assertRaises(AppError):
                sim_result.validate_result(broken)

    def test_the_validator_rejects_a_finite_whole_universe_bound_when_the_outside_population_is_unknown(self):
        _, doc = simulate(s.snapshot_doc(devices=[s.device('a')], collections={'devices': {'complete': False, 'reason': 'query_ceiling'}}),
                          add(s.policy('p', [s.all_devices()])))
        broken = copy.deepcopy(doc)
        whole = [c for c in broken['cohorts'] if c['scope'] == 'whole_declared_universe']
        self.assertTrue(whole)
        whole[0]['upper'] = 10
        with self.assertRaises(AppError):
            sim_result.validate_result(broken)

    def test_the_validator_rejects_a_dangling_reason_reference(self):
        broken = copy.deepcopy(self.doc)
        broken['cohorts'][0]['reason_refs'] = ['no-such-finding']
        with self.assertRaises(AppError):
            sim_result.validate_result(broken)


class UnsupportedFamilies(unittest.TestCase):
    def check(self, record):
        doc = world()
        result, out = simulate(doc, add(record))
        pid = record['id']
        self.assertNotIn(pid, result.detail['policies'])
        self.assertEqual([c for c in out['cohorts'] if pid in c['cohort_id']], [])
        unsupported = [f for f in out['findings'] if f['id'] == 'unsupported_policy:' + pid]
        self.assertEqual(len(unsupported), 1)
        self.assertEqual(unsupported[0]['kind'], 'unknown_semantics')
        self.assertEqual(unsupported[0]['certainty'], 'unknown')
        self.assertIn('unsupported_policy:' + pid, out['coverage']['unresolved_reasons'])
        return unsupported[0]

    def test_another_family_is_reported_and_not_silently_evaluated(self):
        finding = self.check(s.policy('legacy', [s.include('gA')], family='device_configuration_legacy'))
        self.assertIn('unsupported_family:device_configuration_legacy', finding['message'])

    def test_a_non_windows_platform_is_reported_and_not_evaluated(self):
        finding = self.check(s.policy('mac', [s.include('gA')], platforms='macOS'))
        self.assertIn('unsupported_platform', finding['message'])

    def test_an_illegal_filter_on_an_exclusion_is_refused_before_evaluation(self):
        bad = s.policy('bad', [{'type': 'exclusionGroupAssignmentTarget', 'group_id': s.uid('group/gA'),
                                'filter_type': 'include', 'filter_id': s.uid('filter/f')}])
        finding = self.check(bad)
        self.assertIn('exclusion_filter_unsupported', finding['message'])

    def test_an_unknown_target_type_is_preserved_as_unsupported(self):
        finding = self.check(s.policy('odd', [{'type': 'futureAssignmentTarget', 'filter_type': 'none'}]))
        self.assertIn('unsupported_target', finding['message'])

    def test_a_policy_with_an_incomplete_source_collection_is_not_evaluated(self):
        doc = world()
        record = s.policy('half', [s.include('gA')])
        record['incomplete_reason'] = 'assignments:access_denied'
        finding = self.check(record)
        self.assertIn('assignments:access_denied', finding['message'])


class DomainsAndContexts(unittest.TestCase):
    def test_a_device_group_inclusion_does_not_reach_user_contexts_and_a_user_group_does_not_reach_devices(self):
        doc = s.snapshot_doc(
            devices=[s.device('d1'), s.device('d2')], users=[s.user('u1')],
            contexts=[s.context('u1', 'd2')], groups=[s.group('gD'), s.group('gU', 'user')],
            memberships=[s.member('gD', 'd1'), s.member('gU', 'u1', 'user')])
        result, out = simulate(doc, add(s.policy('byDevice', [s.include('gD')]), s.policy('byUser', [s.include('gU')])))
        self.assertEqual(after_sets(result, 'byDevice'), (devs('d1'), devs('d1')))
        self.assertEqual(bounds(out, 'byDevice', 'after', 'user_device_contexts'), (0, 0))
        self.assertEqual(after_sets(result, 'byUser'), (devs('d2'), devs('d2')))
        self.assertEqual(bounds(out, 'byUser', 'after', 'user_device_contexts'), (1, 1))

    def test_a_context_that_is_not_a_confirmed_sign_in_is_possible_not_definite(self):
        doc = s.snapshot_doc(devices=[s.device('d1'), s.device('d2'), s.device('d3')],
                             users=[s.user('u1'), s.user('u2'), s.user('u3')],
                             contexts=[s.context('u1', 'd1', 'signed_in'), s.context('u2', 'd2', 'primary_user'),
                                       s.context('u3', 'd3', 'enrollment_owner')],
                             groups=[s.group('gU', 'user')],
                             memberships=[s.member('gU', n, 'user') for n in ('u1', 'u2', 'u3')])
        result, out = simulate(doc, add(s.policy('p', [s.include('gU')])))
        self.assertEqual(after_sets(result, 'p'), (devs('d1'), devs('d1', 'd2', 'd3')))
        self.assertEqual(bounds(out, 'p', 'after', 'user_device_contexts'), (1, 3))

    def test_a_shared_device_sign_in_is_only_a_possible_context(self):
        doc = s.snapshot_doc(devices=[s.device('kiosk', sharing='shared'), s.device('own')],
                             users=[s.user('u1'), s.user('u2')],
                             contexts=[s.context('u1', 'kiosk'), s.context('u2', 'own')],
                             groups=[s.group('gU', 'user')], memberships=[s.member('gU', 'u1', 'user'), s.member('gU', 'u2', 'user')])
        result, _ = simulate(doc, add(s.policy('p', [s.include('gU')])))
        self.assertEqual(after_sets(result, 'p'), (devs('own'), devs('kiosk', 'own')))

    def test_all_users_reaches_known_users_and_unlisted_context_users_are_possible(self):
        doc = s.snapshot_doc(devices=[s.device('d1'), s.device('d2')], users=[s.user('u1')],
                             contexts=[s.context('u1', 'd1'), s.context('ghost', 'd2')])
        result, _ = simulate(doc, add(s.policy('p', [s.all_users()])))
        self.assertEqual(after_sets(result, 'p'), (devs('d1'), devs('d1', 'd2')))

    def test_a_group_of_unknown_domain_is_looked_up_by_the_principal_id(self):
        doc = s.snapshot_doc(devices=[s.device('d1'), s.device('d2')], users=[s.user('u1')],
                             contexts=[s.context('u1', 'd2')], groups=[s.group('gX', 'unknown')],
                             memberships=[s.member('gX', 'd1'), s.member('gX', 'u1', 'user')])
        result, _ = simulate(doc, add(s.policy('p', [s.include('gX')])))
        self.assertEqual(after_sets(result, 'p'), (devs('d1', 'd2'), devs('d1', 'd2')))

    def test_a_group_whose_membership_is_incomplete_makes_non_members_possible(self):
        doc = s.snapshot_doc(devices=[s.device('a'), s.device('b')], groups=[s.group('gA', complete=False)],
                             memberships=[s.member('gA', 'a')])
        result, _ = simulate(doc, add(s.policy('p', [s.include('gA')])))
        self.assertEqual(after_sets(result, 'p'), (devs('a'), devs('a', 'b')))

    def test_removing_an_exclusion_is_reported_and_the_set_grows(self):
        doc = s.snapshot_doc(devices=[s.device('a'), s.device('b')], groups=[s.group('gA'), s.group('gX')],
                             memberships=[s.member('gA', 'a'), s.member('gA', 'b'), s.member('gX', 'b')],
                             policies=[s.policy('p', [s.include('gA'), s.exclude('gX')])])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA')])))
        self.assertEqual(bounds(out, 'p', 'added'), (1, 1))
        removed = findings(out, 'exclusion_removed')
        self.assertEqual(len(removed), 1)
        self.assertIn(s.uid('group/gX'), removed[0]['id'])

    def test_a_policy_in_the_snapshot_that_the_revision_does_not_touch_has_no_cohorts(self):
        doc = world(policies=[s.policy('quiet', [s.include('gA')])])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA')])))
        self.assertNotIn(s.uid('policy/quiet'), result.detail['policies'])


class StableIdentifiers(unittest.TestCase):
    def test_policies_are_matched_by_id_never_by_display_name(self):
        doc = world(policies=[s.policy('one', [s.include('gA')], label='Same name'),
                              s.policy('two', [], label='Same name')])
        result, out = simulate(doc, add(s.policy('two', [s.include('gA')], label='Same name')))
        self.assertEqual(sorted(result.detail['policies']), [s.uid('policy/two')])
        self.assertEqual(bounds(out, 'two', 'added'), (2, 2))

    def test_renaming_labels_does_not_change_any_cohort(self):
        base = world(policies=[s.policy('p', [s.include('gA')], label='before')])
        _, first = simulate(base, add(s.policy('p', [], label='x')))
        renamed = copy.deepcopy(base)
        renamed['groups'][0]['display_name'] = 'a completely different label'
        renamed['policies'][0]['body']['name'] = 'renamed'
        _, second = simulate(renamed, add(s.policy('p', [], label='y')))
        self.assertEqual(first['cohorts'], second['cohorts'])

    def test_identifiers_are_compared_exactly_not_case_folded(self):
        doc = world()
        upper = s.include('gA')
        upper['group_id'] = upper['group_id'].upper()
        result, out = simulate(doc, add(s.policy('p', [upper])))
        self.assertEqual(result.detail['policies'], {})
        self.assertIn('unsupported_policy:' + s.uid('policy/p'), finding_ids(out))


class Invariants(unittest.TestCase):
    def fixture(self):
        return s.snapshot_doc(
            devices=[s.device('a', model='M1'), s.device('b', model='M2'), s.device('c', model='M1')],
            groups=[s.group('g1'), s.group('g2'), s.group('g3')],
            memberships=[s.member('g1', 'a'), s.member('g1', 'b'), s.member('g2', 'b'), s.member('g2', 'c'), s.member('g3', 'a')],
            filters=[s.filt('m1', 'device.model -eq "M1"')],
            policies=[s.policy('p1', [s.include('g1')], [s.choice(s.DEF, V1)])])

    def revision(self):
        return add(s.policy('p1', [s.include('g1'), s.include('g2', 'include', 'm1'), s.exclude('g3')], [s.choice(s.DEF, V1)]),
                   s.policy('p2', [s.include('g2')], [s.choice(s.DEF, V2)]))

    def test_permuting_collection_order_does_not_change_the_result(self):
        doc, revision = self.fixture(), self.revision()
        _, first = simulate(doc, revision)
        rng = random.Random(5)
        for _ in range(5):
            shuffled, rev = copy.deepcopy(doc), copy.deepcopy(revision)
            for name in ('devices', 'groups', 'memberships', 'filters', 'policies'):
                rng.shuffle(shuffled[name])
            rng.shuffle(rev['policies'])
            _, again = simulate(shuffled, rev)
            self.assertEqual(again, first)

    def test_removing_evidence_never_makes_a_result_more_precise(self):
        doc, revision = self.fixture(), self.revision()
        base, _ = simulate(doc, revision)
        degradations = []
        for index in range(len(doc['memberships'])):
            changed = copy.deepcopy(doc)
            changed['memberships'][index]['certainty'] = 'possible'
            degradations.append(changed)
        for device in range(len(doc['devices'])):
            changed = copy.deepcopy(doc)
            changed['devices'][device]['properties'] = {'model': {'presence': 'unknown'}}
            degradations.append(changed)
        changed = copy.deepcopy(doc)
        changed['groups'][1]['membership_complete'] = False
        degradations.append(changed)
        for changed in degradations:
            degraded, _ = simulate(changed, revision)
            for pid, worlds in base.detail['policies'].items():
                for world_name, entry in worlds.items():
                    other = degraded.detail['policies'][pid][world_name]
                    self.assertLessEqual(other['lower_devices'], entry['lower_devices'])
                    self.assertGreaterEqual(other['upper_devices'], entry['upper_devices'])

    def test_a_fully_known_world_has_equal_lower_and_upper_sets(self):
        result, _ = simulate(self.fixture(), self.revision())
        for worlds in result.detail['policies'].values():
            for entry in worlds.values():
                self.assertEqual(entry['lower_devices'], entry['upper_devices'])


MODELS = ('M1', 'M2', 'M3')


def reference_applies(device_id, device_model, assignments, excluded, members, matches):
    """The reference rule of SIMULATOR_MODEL.md section 4, over plain Python data."""
    if any(device_id in members[g] for g in excluded):
        return False
    active = [a for a in assignments if device_id in members[a[0]]]
    exclude = [a for a in active if a[1] == 'exclude']
    if exclude:
        return not any(matches(device_model, a[2]) for a in exclude)
    if any(a[1] == 'none' for a in active):
        return True
    return any(matches(device_model, a[2]) for a in active if a[1] == 'include')


class AgainstTheReferenceRule(unittest.TestCase):
    def build(self, seed):
        rng = random.Random(seed)
        names = [f'd{i}' for i in range(rng.randint(3, 9))]
        model_of = {n: rng.choice(MODELS) for n in names}
        groups = [f'g{i}' for i in range(rng.randint(2, 4))]
        members = {g: {n for n in names if rng.random() < 0.5} for g in groups}
        assignments, excluded = [], []
        for _ in range(rng.randint(1, 4)):
            mode = rng.choice(('none', 'include', 'exclude'))
            row = (rng.choice(groups), mode, rng.choice(MODELS) if mode != 'none' else None)
            if row not in assignments:
                assignments.append(row)
        if rng.random() < 0.5:
            excluded.append(rng.choice(groups))
        return names, model_of, groups, members, assignments, excluded

    def test_two_hundred_random_known_fixtures_agree_with_the_reference_rule(self):
        for seed in range(200):
            names, model_of, groups, members, assignments, excluded = self.build(seed)
            rows = [s.include(g, mode, f'is-{m}') if mode != 'none' else s.include(g) for g, mode, m in assignments]
            rows += [s.exclude(g) for g in excluded]
            doc = s.snapshot_doc(
                devices=[s.device(n, model=model_of[n]) for n in names], groups=[s.group(g) for g in groups],
                memberships=[s.member(g, n) for g in groups for n in sorted(members[g])],
                filters=[s.filt(f'is-{m}', f'device.model -eq "{m}"') for m in MODELS])
            result, _ = simulate(doc, add(s.policy('p', rows)))
            expected = frozenset(s.uid('device/' + n) for n in names if reference_applies(
                n, model_of[n], assignments, excluded, members, lambda model, wanted: model == wanted))
            self.assertEqual(after_sets(result, 'p'), (expected, expected), f'seed {seed}')

    def test_removing_evidence_from_random_fixtures_only_widens_the_bounds(self):
        for seed in range(60):
            names, model_of, groups, members, assignments, excluded = self.build(seed)
            rows = [s.include(g, mode, f'is-{m}') if mode != 'none' else s.include(g) for g, mode, m in assignments]
            rows += [s.exclude(g) for g in excluded]
            rng = random.Random(1000 + seed)
            memberships = [(g, n) for g in groups for n in sorted(members[g])]

            def make(possible):
                return s.snapshot_doc(
                    devices=[s.device(n, model=model_of[n]) if n not in possible['blind'] else s.device(n) for n in names],
                    groups=[s.group(g) for g in groups],
                    memberships=[s.member(g, n, certainty='possible' if (g, n) in possible['pairs'] else 'known')
                                 for g, n in memberships],
                    filters=[s.filt(f'is-{m}', f'device.model -eq "{m}"') for m in MODELS])
            exact, _ = simulate(make({'pairs': set(), 'blind': set()}), add(s.policy('p', rows)))
            pairs = {p for p in memberships if rng.random() < 0.3}
            blind = {n for n in names if rng.random() < 0.3}
            wider, _ = simulate(make({'pairs': pairs, 'blind': blind}), add(s.policy('p', rows)))
            lower, upper = after_sets(exact, 'p')
            lower2, upper2 = after_sets(wider, 'p')
            self.assertLessEqual(lower2, lower, f'seed {seed}')
            self.assertGreaterEqual(upper2, upper, f'seed {seed}')


class EstateEndToEnd(unittest.TestCase):
    def test_the_estates_own_policy_evaluates_with_a_population_and_validates(self):
        estate = generate_estate(seed=7, policy_count=3)
        g0, g1, g2 = estate['truth']['groups']
        fid = estate['truth']['filters'][0]
        pids = [p['id'] for p in estate['truth']['policies']]
        members = {g0: ('a', 'c', 'd'), g1: ('b',), g2: ('c',)}
        population = {
            'devices': [s.device('a', osVersion='10.0.1'), s.device('b'), s.device('c', osVersion='10.0.2'),
                        s.device('d', osVersion='9.1'), s.device('e')],
            'group_domains': {g0: 'device', g1: 'device', g2: 'device'}, 'complete_groups': [g0, g1, g2],
            'memberships': [{'group_id': g, 'member_id': s.uid('device/' + n), 'member_kind': 'device', 'certainty': 'known'}
                            for g, ns in members.items() for n in ns],
            'filter_expressions': {fid: {'expression': 'device.osVersion -ge "10.0"', 'platform': 'windows10'}}}
        snapshot = sim_model.snapshot_from_estate(estate, population)
        revision_doc = s.revision_doc()
        revision_doc['removed_policy_ids'] = [pids[0]]
        revision = sim_model.load_revision(revision_doc)
        result = sim_eval.simulate(snapshot, revision, profile())
        doc = result.to_schema()
        sim_result.validate_result(doc)
        before = result.detail['policies'][pids[0]]['before']
        # a: include-filter group, filter matches; b: no-filter group; c: excluded; d: filter misses; e: in no group.
        self.assertEqual(before['lower_devices'], devs('a', 'b'))
        self.assertEqual(before['upper_devices'], devs('a', 'b'))
        self.assertEqual(result.detail['policies'][pids[0]]['after']['upper_devices'], frozenset())


class ExternalManagementAndCoverage(unittest.TestCase):
    def test_settings_comparison_reports_that_external_management_was_not_collected(self):
        doc = world(policies=[s.policy('p1', [s.include('gA')], [s.choice(s.DEF, V1)])])
        _, out = simulate(doc, add(s.policy('p2', [s.include('gA')], [s.choice(s.DEF, V2)])))
        self.assertIn('external_management_unknown', out['coverage']['unresolved_reasons'])
        _, quiet = simulate(world(), add(s.policy('p', [s.include('gA')], settings=[])))
        self.assertNotIn('external_management_unknown', quiet['coverage']['unresolved_reasons'])

    def test_a_missing_filter_makes_the_assignment_unknown_and_is_a_coverage_gap(self):
        doc = world()
        result, out = simulate(doc, add(s.policy('p', [s.include('gA', 'include', 'ghost-filter')])))
        self.assertEqual(after_sets(result, 'p'), (frozenset(), devs('a', 'b')))
        self.assertIn('missing_filter:' + s.uid('filter/ghost-filter'), out['coverage']['unresolved_reasons'])

    def test_a_filter_with_an_unsupported_expression_is_unknown_and_named_in_the_reasons(self):
        doc = world(filters=[s.filt('rx', 'device.model -match "M.*"')])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA', 'include', 'rx')])))
        self.assertEqual(after_sets(result, 'p'), (frozenset(), devs('a', 'b')))
        self.assertTrue(any(r.startswith('filter_unsupported:' + s.uid('filter/rx')) for r in out['coverage']['unresolved_reasons']))


if __name__ == '__main__':
    unittest.main()
