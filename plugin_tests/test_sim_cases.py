"""NT-2 item 3: the twenty-two discriminating cases of the simulator model, one test each, named after the case.

Every expected cohort below is written by hand from the model's table (SIMULATOR_MODEL.md section 8) and from
the reference rule in section 4. The tests never ask the evaluator what the answer should be.
Fixtures add or change one policy against a snapshot that has none (or one), so "after" is what the proposal does.
"""
import unittest

from plugin_tests import sim_support as s
from plugin_tests.sim_cases import (V1, V2, after_sets, aggregate, bounds, cohort, devs, finding_ids, findings,
                                    profile, simulate)


def snap(devices, groups, memberships, **more):
    return s.snapshot_doc(devices=devices, groups=groups, memberships=memberships, **more)


def add(p):
    return s.revision_doc([p])


class Sim01SameDeviceInTwoIncludedGroups(unittest.TestCase):
    def test_sim_01_same_device_in_two_included_groups_counts_once(self):
        doc = snap([s.device('a'), s.device('b'), s.device('c')], [s.group('gA'), s.group('gB')],
                   [s.member('gA', 'a'), s.member('gA', 'b'), s.member('gB', 'a')])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA'), s.include('gB')])))
        self.assertEqual(bounds(out, 'p', 'after'), (2, 2))
        self.assertEqual(after_sets(result, 'p'), (devs('a', 'b'), devs('a', 'b')))
        self.assertEqual(bounds(out, 'p', 'added'), (2, 2))


class Sim02IncludedAndExcludedDeviceGroup(unittest.TestCase):
    def test_sim_02_a_device_in_an_included_and_an_excluded_group_is_excluded_in_the_device_domain(self):
        doc = snap([s.device('a'), s.device('b'), s.device('c')], [s.group('gA'), s.group('gX')],
                   [s.member('gA', 'a'), s.member('gA', 'b'), s.member('gA', 'c'), s.member('gX', 'b')])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA'), s.exclude('gX')])))
        self.assertEqual(after_sets(result, 'p'), (devs('a', 'c'), devs('a', 'c')))
        self.assertEqual(bounds(out, 'p', 'after'), (2, 2))
        self.assertEqual(finding_ids(out, 'unsupported_cross_domain_exclusion'), [])


class Sim03UserInclusionWithDeviceGroupExclusion(unittest.TestCase):
    def setUp(self):
        self.doc = snap(
            [s.device('d1'), s.device('d2')], [s.group('gU', 'user'), s.group('gD')],
            [s.member('gU', 'u1', 'user'), s.member('gU', 'u2', 'user'), s.member('gD', 'd1')],
            users=[s.user('u1'), s.user('u2')],
            contexts=[s.context('u1', 'd1', 'primary_user'), s.context('u1', 'd1', 'signed_in'),
                      s.context('u2', 'd2', 'signed_in')])
        self.revision = add(s.policy('p', [s.include('gU'), s.exclude('gD')]))

    def test_sim_03_user_inclusion_plus_device_group_exclusion_warns_and_never_subtracts_by_primary_user(self):
        result, out = simulate(self.doc, self.revision)
        self.assertEqual(after_sets(result, 'p'), (devs('d1', 'd2'), devs('d1', 'd2')))
        self.assertEqual(bounds(out, 'p', 'after'), (2, 2))
        self.assertEqual(bounds(out, 'p', 'after', 'user_device_contexts'), (2, 2))
        warning = [f for f in out['findings'] if f['id'].startswith('unsupported_cross_domain_exclusion')]
        self.assertEqual(len(warning), 1)
        self.assertEqual(warning[0]['kind'], 'unsupported_target')
        self.assertIn(s.uid('group/gD'), warning[0]['id'])

    def test_sim_03_the_exposure_is_kept_even_though_the_exclusion_group_names_the_device(self):
        result, _ = simulate(self.doc, self.revision)
        self.assertIn(s.uid('device/d1'), after_sets(result, 'p')[0])


def filter_snapshot(devices, memberships, groups=('gA', 'gB'), filters=()):
    return snap(devices, [s.group(g) for g in groups], memberships, filters=filters)


class Sim04To08FilterModes(unittest.TestCase):
    F_INC = s.filt('inc', 'device.model -eq "M1"')
    F_EXC = s.filt('exc', 'device.manufacturer -eq "Dell"')

    def test_sim_04_include_filter_match_plus_exclude_filter_match_exclude_mode_wins_not_targeted(self):
        doc = filter_snapshot([s.device('a', model='M1', manufacturer='Dell')],
                              [s.member('gA', 'a'), s.member('gB', 'a')], filters=[self.F_INC, self.F_EXC])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA', 'include', 'inc'), s.include('gB', 'exclude', 'exc')])))
        self.assertEqual(after_sets(result, 'p'), (frozenset(), frozenset()))
        self.assertEqual(bounds(out, 'p', 'after'), (0, 0))

    def test_sim_05_include_filter_miss_plus_exclude_filter_miss_exclude_mode_wins_targeted(self):
        doc = filter_snapshot([s.device('d', model='M2', manufacturer='HP')],
                              [s.member('gA', 'd'), s.member('gB', 'd')], filters=[self.F_INC, self.F_EXC])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA', 'include', 'inc'), s.include('gB', 'exclude', 'exc')])))
        self.assertEqual(after_sets(result, 'p'), (devs('d'), devs('d')))
        self.assertEqual(bounds(out, 'p', 'after'), (1, 1))

    def test_sim_06_no_filter_assignment_plus_include_filter_miss_is_targeted(self):
        doc = filter_snapshot([s.device('a', model='M2'), s.device('b', model='M2')],
                              [s.member('gA', 'a'), s.member('gB', 'a'), s.member('gA', 'b')], filters=[self.F_INC])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA', 'include', 'inc'), s.include('gB')])))
        self.assertEqual(after_sets(result, 'p'), (devs('a'), devs('a')))
        self.assertEqual(bounds(out, 'p', 'after'), (1, 1))

    def test_sim_07_two_exclude_filters_one_matches_is_an_or_of_exclusions_not_targeted(self):
        f1 = s.filt('x1', 'device.model -eq "M1"')
        f2 = s.filt('x2', 'device.model -eq "M9"')
        doc = filter_snapshot(
            [s.device('a', model='M1'), s.device('c', model='M2'), s.device('e', model='M2')],
            [s.member('gA', 'a'), s.member('gB', 'a'), s.member('gA', 'c'), s.member('gB', 'c'), s.member('gB', 'e')],
            filters=[f1, f2])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA', 'exclude', 'x1'), s.include('gB', 'exclude', 'x2')])))
        self.assertEqual(after_sets(result, 'p'), (devs('c', 'e'), devs('c', 'e')))
        self.assertEqual(bounds(out, 'p', 'after'), (2, 2))

    def test_sim_08_two_include_filters_one_matches_is_targeted(self):
        f1 = s.filt('i1', 'device.model -eq "M1"')
        f2 = s.filt('i2', 'device.model -eq "M2"')
        doc = filter_snapshot([s.device('a', model='M2'), s.device('b', model='M3')],
                              [s.member('gA', 'a'), s.member('gB', 'a'), s.member('gA', 'b'), s.member('gB', 'b')],
                              filters=[f1, f2])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA', 'include', 'i1'), s.include('gB', 'include', 'i2')])))
        self.assertEqual(after_sets(result, 'p'), (devs('a'), devs('a')))
        self.assertEqual(bounds(out, 'p', 'after'), (1, 1))

    def test_a_group_exclusion_and_an_exclude_mode_filter_are_different_mechanisms(self):
        doc = filter_snapshot(
            [s.device('a', model='M1'), s.device('b', model='M2'), s.device('c', model='M2')],
            [s.member('gA', 'a'), s.member('gA', 'b'), s.member('gA', 'c'), s.member('gB', 'b')],
            filters=[s.filt('m1', 'device.model -eq "M1"')])
        # a: removed by the exclude-mode filter; b: removed by the excluded group; c: stays.
        result, _ = simulate(doc, add(s.policy('p', [s.include('gA', 'exclude', 'm1'), s.exclude('gB')])))
        self.assertEqual(after_sets(result, 'p'), (devs('c'), devs('c')))


class Sim09PossibleMembershipInHigherPriorityExcludeGroup(unittest.TestCase):
    def test_sim_09_possible_membership_in_an_exclude_filter_group_is_unknown_when_branches_disagree(self):
        doc = filter_snapshot([s.device('a', model='M1'), s.device('b', model='M1')],
                              [s.member('gA', 'a'), s.member('gA', 'b'), s.member('gB', 'a', certainty='possible')],
                              filters=[s.filt('m1', 'device.model -eq "M1"')])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA'), s.include('gB', 'exclude', 'm1')])))
        # b: exclude assignment cannot be active, no-filter branch applies: definite.
        # a: if gB is active the exclude filter matches and a is out; if not, a is in. The branches disagree.
        self.assertEqual(after_sets(result, 'p'), (devs('b'), devs('a', 'b')))
        self.assertEqual(bounds(out, 'p', 'after'), (1, 2))

    def test_sim_09_when_the_admissible_branches_agree_the_result_is_definite(self):
        doc = filter_snapshot([s.device('a', model='M2')],
                              [s.member('gA', 'a'), s.member('gB', 'a', certainty='possible')],
                              filters=[s.filt('m1', 'device.model -eq "M1"')])
        # If gB is active the exclude filter misses, so a stays; if it is not, a stays. Both branches agree.
        result, _ = simulate(doc, add(s.policy('p', [s.include('gA'), s.include('gB', 'exclude', 'm1')])))
        self.assertEqual(after_sets(result, 'p'), (devs('a'), devs('a')))


class Sim10ObservedNullVersusUnavailable(unittest.TestCase):
    def devices(self):
        return [s.device('a', model={'presence': 'observed_null'}), s.device('b'),
                s.device('c', model={'presence': 'unknown'}), s.device('d', model='X'),
                s.device('e', model={'presence': 'redacted'})]

    def members(self):
        return [s.member('gA', n) for n in 'abcde']

    def test_sim_10_observed_null_and_unavailable_properties_give_distinct_outcomes(self):
        doc = filter_snapshot(self.devices(), self.members(), groups=('gA',), filters=[s.filt('x', 'device.model -eq "X"')])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA', 'include', 'x')])))
        # a: null equals "X" is false by the profile's truth table. b, c, e: unknown, not null. d: true.
        self.assertEqual(after_sets(result, 'p'), (devs('d'), devs('b', 'c', 'd', 'e')))
        self.assertEqual(bounds(out, 'p', 'after'), (1, 4))

    def test_sim_10_the_negated_comparison_separates_null_from_unknown_the_other_way(self):
        doc = filter_snapshot(self.devices(), self.members(), groups=('gA',), filters=[s.filt('x', 'device.model -ne "X"')])
        result, _ = simulate(doc, add(s.policy('p', [s.include('gA', 'include', 'x')])))
        # a: a read null is not "X" (true). d: equal (false). The unavailable ones stay unknown.
        self.assertEqual(after_sets(result, 'p'), (devs('a'), devs('a', 'b', 'c', 'e')))

    def test_sim_10_provenance_of_each_unknown_is_kept_in_the_reasons(self):
        doc = filter_snapshot(self.devices(), self.members(), groups=('gA',), filters=[s.filt('x', 'device.model -eq "X"')])
        _, out = simulate(doc, add(s.policy('p', [s.include('gA', 'include', 'x')])))
        text = ' '.join(f['message'] for f in out['findings'])
        for code in ('property_absent:model', 'property_unknown:model', 'property_redacted:model'):
            self.assertIn(code, text)


class Sim11AllDevicesWithIncompleteInventory(unittest.TestCase):
    def test_sim_11_all_devices_with_incomplete_inventory_is_bounded_in_the_observed_universe_only(self):
        doc = snap([s.device('a'), s.device('b'), s.device('c')], [], [],
                   collections={'devices': {'complete': False, 'reason': 'query_ceiling'}})
        result, out = simulate(doc, add(s.policy('p', [s.all_devices()])))
        self.assertEqual(bounds(out, 'p', 'after'), (3, 3))
        self.assertEqual(cohort(out, f'policy:{s.uid("policy/p")}:after:unique_devices')['scope'], 'observed_universe')
        whole = cohort(out, 'changed:after:unique_devices:whole')
        self.assertEqual((whole['scope'], whole['lower'], whole['upper']), ('whole_declared_universe', 3, None))
        self.assertEqual(out['coverage']['universe'], 'captured_devices')
        self.assertEqual(out['coverage']['outside_snapshot_population'], 'unknown')
        self.assertFalse(out['coverage']['snapshot_complete'])
        self.assertIn('collection_incomplete:devices:query_ceiling', out['coverage']['unresolved_reasons'])

    def test_sim_11_the_virtual_target_stays_review_only_and_nothing_is_authorized(self):
        doc = snap([s.device('a')], [], [], collections={'devices': {'complete': False, 'reason': 'query_ceiling'}})
        _, out = simulate(doc, add(s.policy('p', [s.all_devices()])))
        review = findings(out, 'unsupported_target')
        self.assertTrue([f for f in review if f['id'].startswith('virtual_target_review_only')])
        self.assertIs(out['live_execution_authorized'], False)
        self.assertIs(out['endpoint_effective'], False)

    def test_sim_11_a_complete_inventory_gives_a_whole_declared_universe_bound(self):
        doc = snap([s.device('a'), s.device('b')], [], [])
        _, out = simulate(doc, add(s.policy('p', [s.all_devices()])))
        self.assertEqual(out['coverage']['universe'], 'complete_declared_synthetic_fleet')
        self.assertEqual(out['coverage']['outside_snapshot_population'], 'none_within_declared_scope')
        self.assertEqual(cohort(out, f'policy:{s.uid("policy/p")}:after:unique_devices')['scope'], 'whole_declared_universe')


class Sim12FilterInversion(unittest.TestCase):
    def test_sim_12_include_to_exclude_inversion_is_reported_and_both_sets_recomputed(self):
        f = s.filt('m1', 'device.model -eq "M1"')
        doc = snap([s.device('a', model='M1'), s.device('b', model='M2')], [s.group('gA')],
                   [s.member('gA', 'a'), s.member('gA', 'b')], filters=[f],
                   policies=[s.policy('p', [s.include('gA', 'include', 'm1')])])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA', 'exclude', 'm1')])))
        self.assertEqual(after_sets(result, 'p', 'before'), (devs('a'), devs('a')))
        self.assertEqual(after_sets(result, 'p', 'after'), (devs('b'), devs('b')))
        self.assertEqual(bounds(out, 'p', 'added'), (1, 1))
        self.assertEqual(bounds(out, 'p', 'removed'), (1, 1))
        self.assertEqual(bounds(out, 'p', 'retained'), (0, 0))
        inversion = findings(out, 'filter_inversion')
        self.assertEqual(len(inversion), 1)
        self.assertEqual(inversion[0]['certainty'], 'definite_under_model')


class Sim13To16SettingsConflicts(unittest.TestCase):
    def world(self):
        return snap([s.device('a'), s.device('b'), s.device('c')], [s.group('gA'), s.group('gB'), s.group('gC')],
                    [s.member('gA', 'a'), s.member('gA', 'b'), s.member('gB', 'a'), s.member('gB', 'b')])

    def test_sim_13_same_setting_and_value_on_overlapping_policies_is_equivalent_overlap_not_a_conflict(self):
        doc = self.world()
        doc['policies'] = [s.policy('p1', [s.include('gA')], [s.choice(s.DEF, V2)])]
        _, out = simulate(doc, add(s.policy('p2', [s.include('gB')], [s.choice(s.DEF, V2)])))
        self.assertEqual(len(findings(out, 'equivalent_overlap')), 1)
        self.assertEqual(findings(out, 'predicted_configuration_conflict'), [])
        self.assertEqual(findings(out, 'potential_conflict'), [])

    def test_sim_14_different_values_on_disjoint_cohorts_are_no_overlap_conflict_and_both_are_preserved(self):
        doc = self.world()
        doc['groups'].append(s.group('gD'))
        doc['devices'].append(s.device('z'))
        doc['memberships'].append(s.member('gD', 'z'))
        result, out = simulate(doc, s.revision_doc([s.policy('p1', [s.include('gA')], [s.choice(s.DEF, V1)]),
                                                    s.policy('p2', [s.include('gD')], [s.choice(s.DEF, V2)])]))
        for kind in ('predicted_configuration_conflict', 'potential_conflict', 'equivalent_overlap', 'unknown_semantics'):
            self.assertEqual(findings(out, kind), [], kind)
        self.assertEqual(after_sets(result, 'p1'), (devs('a', 'b'), devs('a', 'b')))
        self.assertEqual(after_sets(result, 'p2'), (devs('z'), devs('z')))
        overlaps = [c for c in out['cohorts'] if c['kind'] == 'conflict_overlap']
        self.assertEqual([(c['lower'], c['upper']) for c in overlaps], [(0, 0)])

    def test_sim_15_different_values_on_definite_overlap_are_predicted_and_on_possible_overlap_are_potential(self):
        doc = snap([s.device('a'), s.device('b'), s.device('c')], [s.group('gA'), s.group('gB'), s.group('gC')],
                   [s.member('gA', 'a'), s.member('gA', 'b'), s.member('gA', 'c'), s.member('gB', 'a'),
                    s.member('gB', 'c', certainty='possible'), s.member('gC', 'b', certainty='possible')])
        doc['policies'] = [s.policy('p1', [s.include('gA')], [s.choice(s.DEF, V1)])]
        revision = s.revision_doc([s.policy('p2', [s.include('gB')], [s.choice(s.DEF, V2)]),
                                   s.policy('p3', [s.include('gC')], [s.choice(s.DEF, V2)])])
        _, out = simulate(doc, revision)
        predicted = findings(out, 'predicted_configuration_conflict')
        potential = findings(out, 'potential_conflict')
        self.assertEqual(len(predicted), 1)
        self.assertIn(s.uid('policy/p2'), predicted[0]['id'])
        self.assertEqual(predicted[0]['certainty'], 'definite_under_model')
        self.assertEqual(len(potential), 1)
        self.assertIn(s.uid('policy/p3'), potential[0]['id'])
        self.assertEqual(potential[0]['certainty'], 'possible')
        by_pair = {tuple(c['cohort_id'].split(':')[1:3]): (c['lower'], c['upper'])
                   for c in out['cohorts'] if c['kind'] == 'conflict_overlap'}
        self.assertEqual(sorted(by_pair.values()), [(0, 1), (1, 2)])
        self.assertIn('not an observed endpoint failure', predicted[0]['message'])
        self.assertIn('different_value_conflicts', predicted[0]['message'])

    def test_sim_15_without_an_admitted_rule_the_overlap_is_unknown_semantics_not_a_conflict(self):
        doc = self.world()
        doc['policies'] = [s.policy('p1', [s.include('gA')], [s.choice(s.DEF, V1)])]
        norule = profile({'definitions': {s.DEF: {'scope': 'device', 'canonical': s.DEF}}})
        _, out = simulate(doc, add(s.policy('p2', [s.include('gB')], [s.choice(s.DEF, V2)])), norule)
        self.assertEqual(findings(out, 'predicted_configuration_conflict'), [])
        unknown = findings(out, 'unknown_semantics')
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]['certainty'], 'unknown')

    def test_sim_16_a_child_under_a_different_parent_choice_does_not_collide(self):
        doc = self.world()
        on, off = s.DEF_B + '_1', s.DEF_B + '_0'
        doc['policies'] = [s.policy('p1', [s.include('gA')],
                                    [s.choice(s.DEF_B, on, [s.child_choice(s.DEF_CHILD, s.DEF_CHILD + '_a')])])]
        _, out = simulate(doc, add(s.policy('p2', [s.include('gB')],
                                            [s.choice(s.DEF_B, off, [s.child_choice(s.DEF_CHILD, s.DEF_CHILD + '_b')])])))
        conflicts = findings(out, 'predicted_configuration_conflict')
        self.assertEqual(len(conflicts), 1)
        self.assertNotIn(s.DEF_CHILD, conflicts[0]['message'])
        self.assertTrue(all(s.DEF_CHILD not in ref for f in out['findings'] for ref in f['source_refs']))

    def test_sim_16_the_same_child_under_the_same_parent_choice_does_collide(self):
        doc = self.world()
        on = s.DEF_B + '_1'
        doc['policies'] = [s.policy('p1', [s.include('gA')],
                                    [s.choice(s.DEF_B, on, [s.child_choice(s.DEF_CHILD, s.DEF_CHILD + '_a')])])]
        _, out = simulate(doc, add(s.policy('p2', [s.include('gB')],
                                            [s.choice(s.DEF_B, on, [s.child_choice(s.DEF_CHILD, s.DEF_CHILD + '_b')])])))
        conflicts = findings(out, 'predicted_configuration_conflict')
        self.assertEqual(len(conflicts), 1)
        self.assertIn(s.DEF_CHILD, conflicts[0]['message'])

    def test_sim_16_different_collection_items_do_not_collide_and_the_shared_item_is_equivalent(self):
        doc = self.world()
        doc['policies'] = [s.policy('p1', [s.include('gA')], [s.collection(s.DEF_COLLECTION, ['x', 'y'])])]
        _, out = simulate(doc, add(s.policy('p2', [s.include('gB')], [s.collection(s.DEF_COLLECTION, ['z'])])))
        for kind in ('predicted_configuration_conflict', 'potential_conflict', 'equivalent_overlap'):
            self.assertEqual(findings(out, kind), [], kind)
        _, out = simulate(doc, add(s.policy('p2', [s.include('gB')], [s.collection(s.DEF_COLLECTION, ['y', 'z'])])))
        self.assertEqual(len(findings(out, 'equivalent_overlap')), 1)
        self.assertEqual(findings(out, 'predicted_configuration_conflict'), [])

    def test_a_sourced_precedence_rule_is_a_defined_precedence_not_a_conflict(self):
        doc = self.world()
        doc['policies'] = [s.policy('p1', [s.include('gA')], [s.choice(s.DEF, V1)])]
        prof = profile({'definitions': {s.DEF: {'scope': 'device', 'canonical': s.DEF, 'conflict_rule': 'different_value_conflicts',
                                                'precedence': {'prefer_value': V2, 'source': 'synthetic-doc:precedence-1'}}}})
        _, out = simulate(doc, add(s.policy('p2', [s.include('gB')], [s.choice(s.DEF, V2)])), prof)
        self.assertEqual(len(findings(out, 'defined_precedence')), 1)
        self.assertEqual(findings(out, 'predicted_configuration_conflict'), [])
        self.assertIn('synthetic-doc:precedence-1', findings(out, 'defined_precedence')[0]['message'])

    USER_SCOPED = {'definitions': {s.DEF: {'scope': 'user', 'canonical': s.DEF, 'conflict_rule': 'different_value_conflicts'}}}

    def shared_device_world(self):
        return snap([s.device('d')], [s.group('gU1', 'user'), s.group('gU2', 'user')],
                    [s.member('gU1', 'u1', 'user'), s.member('gU2', 'u2', 'user')],
                    users=[s.user('u1'), s.user('u2')], contexts=[s.context('u1', 'd'), s.context('u2', 'd')])

    def test_sim_15_user_scoped_settings_on_disjoint_user_contexts_of_a_shared_device_are_not_a_conflict(self):
        doc = self.shared_device_world()
        doc['policies'] = [s.policy('p1', [s.include('gU1')], [s.choice(s.DEF, V1)])]
        _, out = simulate(doc, add(s.policy('p2', [s.include('gU2')], [s.choice(s.DEF, V2)])), profile(self.USER_SCOPED))
        self.assertEqual(findings(out, 'predicted_configuration_conflict'), [])
        self.assertEqual(findings(out, 'potential_conflict'), [])
        overlap = [c for c in out['cohorts'] if c['kind'] == 'conflict_overlap']
        self.assertEqual([(c['unit'], c['lower'], c['upper']) for c in overlap], [('user_device_contexts', 0, 0)])

    def test_sim_15_user_scoped_settings_on_the_same_user_context_are_a_definite_conflict(self):
        doc = self.shared_device_world()
        doc['policies'] = [s.policy('p1', [s.include('gU1')], [s.choice(s.DEF, V1)])]
        _, out = simulate(doc, add(s.policy('p2', [s.include('gU1')], [s.choice(s.DEF, V2)])), profile(self.USER_SCOPED))
        predicted = findings(out, 'predicted_configuration_conflict')
        self.assertEqual(len(predicted), 1)
        self.assertEqual(predicted[0]['certainty'], 'definite_under_model')
        overlap = [c for c in out['cohorts'] if c['kind'] == 'conflict_overlap']
        self.assertEqual([(c['unit'], c['lower'], c['upper']) for c in overlap], [('user_device_contexts', 1, 1)])

    def test_sim_15_a_user_scoped_setting_assigned_to_a_device_is_only_a_possible_overlap(self):
        doc = snap([s.device('d')], [s.group('gU1', 'user'), s.group('gD')],
                   [s.member('gU1', 'u1', 'user'), s.member('gD', 'd')],
                   users=[s.user('u1')], contexts=[s.context('u1', 'd')])
        doc['policies'] = [s.policy('p1', [s.include('gU1')], [s.choice(s.DEF, V1)])]
        _, out = simulate(doc, add(s.policy('p2', [s.include('gD')], [s.choice(s.DEF, V2)])), profile(self.USER_SCOPED))
        self.assertEqual(findings(out, 'predicted_configuration_conflict'), [])
        self.assertEqual(len(findings(out, 'potential_conflict')), 1)


class Sim17IdentityAndMissingRelationships(unittest.TestCase):
    def test_sim_17_same_display_name_different_ids_stay_distinct(self):
        doc = snap([s.device('a'), s.device('b')], [s.group('g1', label='Pilot'), s.group('g2', label='Pilot')],
                   [s.member('g1', 'a'), s.member('g2', 'b')])
        result, out = simulate(doc, add(s.policy('p', [s.include('g1')])))
        self.assertEqual(after_sets(result, 'p'), (devs('a'), devs('a')))
        self.assertEqual(bounds(out, 'p', 'after'), (1, 1))

    def test_sim_17_a_missing_linked_group_gives_unknown_not_empty(self):
        doc = snap([s.device('a'), s.device('b'), s.device('c')], [s.group('g1')], [s.member('g1', 'a')])
        result, out = simulate(doc, add(s.policy('p', [s.include('ghost')])))
        self.assertEqual(after_sets(result, 'p'), (frozenset(), devs('a', 'b', 'c')))
        self.assertEqual(bounds(out, 'p', 'after'), (0, 3))
        self.assertIn('missing_group:' + s.uid('group/ghost'), out['coverage']['unresolved_reasons'])
        self.assertTrue(findings(out, 'coverage_gap'))


class Sim18RingOverlapAndMultiUserDevice(unittest.TestCase):
    def test_sim_18_unique_total_differs_from_ring_and_context_sums_and_the_overlap_is_disclosed(self):
        doc = snap([s.device('a'), s.device('b'), s.device('c')], [s.group('gU', 'user')],
                   [s.member('gU', 'u1', 'user'), s.member('gU', 'u2', 'user'), s.member('gU', 'u3', 'user')],
                   users=[s.user('u1'), s.user('u2'), s.user('u3')],
                   contexts=[s.context('u1', 'a'), s.context('u2', 'a'), s.context('u3', 'b')],
                   rings=[{'ring_id': 'r1', 'name': 'Wave 0', 'order': 0, 'device_ids': [s.uid('device/a'), s.uid('device/b')]},
                          {'ring_id': 'r2', 'name': 'UAT', 'order': 1, 'device_ids': [s.uid('device/b'), s.uid('device/c')]}])
        _, out = simulate(doc, add(s.policy('p', [s.include('gU')])))
        unique = aggregate(out, 'after')
        contexts = aggregate(out, 'after', 'user_device_contexts')
        ring1 = cohort(out, 'changed:after:unique_devices:ring:r1')
        ring2 = cohort(out, 'changed:after:unique_devices:ring:r2')
        self.assertEqual(unique, (2, 2))
        self.assertEqual(contexts, (3, 3))
        self.assertEqual((ring1['lower'], ring1['upper']), (2, 2))
        self.assertEqual((ring2['lower'], ring2['upper']), (1, 1))
        self.assertNotEqual(ring1['lower'] + ring2['lower'], unique[0])
        self.assertEqual((ring1['ring_id'], ring2['ring_id']), ('r1', 'r2'))
        overlap = [f for f in out['findings'] if f['id'] == 'ring_overlap']
        self.assertEqual(len(overlap), 1)
        self.assertIn('1 device', overlap[0]['message'])
        self.assertEqual([f for f in out['findings'] if f['id'] == 'ring_unclassified'], [])

    def test_sim_18_devices_outside_every_ring_are_reported_as_unclassified(self):
        doc = snap([s.device('a'), s.device('b')], [s.group('gA')], [s.member('gA', 'a'), s.member('gA', 'b')],
                   rings=[{'ring_id': 'r1', 'name': 'Wave 0', 'order': 0, 'device_ids': [s.uid('device/a')]}])
        _, out = simulate(doc, add(s.policy('p', [s.include('gA')])))
        unclassified = [f for f in out['findings'] if f['id'] == 'ring_unclassified']
        self.assertEqual(len(unclassified), 1)
        self.assertIn('1 device', unclassified[0]['message'])


class Sim19SnapshotEndsAtQueryCeiling(unittest.TestCase):
    def test_sim_19_a_truncated_snapshot_is_incomplete_and_never_a_zero_conflict_safe_result(self):
        doc = snap([s.device('a')], [s.group('gA')], [s.member('gA', 'a')],
                   policies=[s.policy('p1', [s.include('gA')], [s.choice(s.DEF, V1)])],
                   collections={'policies': {'complete': False, 'reason': 'query_ceiling'}})
        _, out = simulate(doc, add(s.policy('p2', [s.include('gA')], [s.choice(s.DEF, V2)])))
        self.assertFalse(out['coverage']['snapshot_complete'])
        self.assertEqual(out['coverage']['outside_snapshot_population'], 'unknown')
        self.assertIn('collection_incomplete:policies:query_ceiling', out['coverage']['unresolved_reasons'])
        gap = findings(out, 'coverage_gap')
        self.assertTrue(gap)
        self.assertTrue(all(f['certainty'] == 'unknown' for f in gap))
        self.assertTrue(any('no safe verdict' in f['message'] for f in gap))
        self.assertTrue(any(f['id'].startswith('predicted_configuration_conflict') for f in out['findings']))

    def test_sim_19_an_uncollected_collection_is_incomplete_too(self):
        doc = snap([s.device('a')], [s.group('gA')], [s.member('gA', 'a')])
        del doc['filters']
        _, out = simulate(doc, add(s.policy('p', [s.include('gA')])))
        self.assertIn('collection_incomplete:filters:collection_not_collected', out['coverage']['unresolved_reasons'])
        self.assertTrue(any('no safe verdict' in f['message'] for f in findings(out, 'coverage_gap')))


class Sim20InvalidationAfterReview(unittest.TestCase):
    def setUp(self):
        from intune_iac import sim_eval, sim_model
        self.sim_eval, self.sim_model = sim_eval, sim_model
        self.doc = snap([s.device('a'), s.device('b')], [s.group('gA')], [s.member('gA', 'a')])
        self.revision = add(s.policy('p', [s.include('gA')], description='first'))
        self.profile = profile()
        _, self.out = simulate(self.doc, self.revision, self.profile)

    def current(self, doc=None, revision=None, prof=None):
        return self.sim_eval.binding_status(
            self.out, self.sim_model.load_snapshot(doc or self.doc),
            self.sim_model.load_revision(revision or self.revision), prof or self.profile)

    def test_sim_20_an_unchanged_input_is_still_current(self):
        self.assertEqual(self.current(), (True, []))

    def test_sim_20_a_membership_change_after_review_invalidates_the_result(self):
        changed = snap([s.device('a'), s.device('b')], [s.group('gA')], [s.member('gA', 'a'), s.member('gA', 'b')])
        self.assertEqual(self.current(changed), (False, ['snapshot_changed']))

    def test_sim_20_a_source_change_after_review_invalidates_the_result(self):
        changed = add(s.policy('p', [s.include('gA')], description='second'))
        self.assertEqual(self.current(revision=changed), (False, ['desired_source_changed']))

    def test_sim_20_a_semantics_change_after_review_invalidates_the_result(self):
        other = profile({'external_management_collected': True})
        self.assertEqual(self.current(prof=other), (False, ['semantics_changed']))


class Sim21DescriptionOnlyChange(unittest.TestCase):
    def test_sim_21_same_target_set_changed_description_only_is_no_device_setting_delta(self):
        doc = snap([s.device('a'), s.device('b')], [s.group('gA')], [s.member('gA', 'a'), s.member('gA', 'b')],
                   policies=[s.policy('p', [s.include('gA')], description='old')])
        result, out = simulate(doc, add(s.policy('p', [s.include('gA')], description='new')))
        self.assertEqual(bounds(out, 'p', 'added'), (0, 0))
        self.assertEqual(bounds(out, 'p', 'removed'), (0, 0))
        self.assertEqual(bounds(out, 'p', 'retained'), (2, 2))
        note = [f for f in out['findings'] if f['id'].startswith('description_only_change')]
        self.assertEqual(len(note), 1)
        self.assertIn('no device-setting delta', note[0]['message'])
        self.assertIn('wire preview', note[0]['message'])
        for kind in ('predicted_configuration_conflict', 'potential_conflict', 'equivalent_overlap'):
            self.assertEqual(findings(out, kind), [])


class Sim22PolicyUnassigned(unittest.TestCase):
    def doc(self):
        return snap([s.device('a'), s.device('b')], [s.group('gA')], [s.member('gA', 'a'), s.member('gA', 'b')],
                    policies=[s.policy('p', [s.include('gA')])])

    def check(self, revision):
        result, out = simulate(self.doc(), revision)
        self.assertEqual(after_sets(result, 'p', 'after'), (frozenset(), frozenset()))
        self.assertEqual(bounds(out, 'p', 'removed'), (2, 2))
        self.assertEqual(bounds(out, 'p', 'added'), (0, 0))
        persist = [f for f in out['findings'] if f['id'].startswith('csp_state_may_persist')]
        self.assertEqual(len(persist), 1)
        self.assertEqual(persist[0]['certainty'], 'unknown')
        self.assertIn('not proven endpoint rollback', persist[0]['message'])
        self.assertIs(out['endpoint_effective'], False)

    def test_sim_22_a_policy_removed_from_the_repository_is_removal_from_intended_targeting_only(self):
        self.check(s.revision_doc(removed=['p']))

    def test_sim_22_a_policy_with_its_assignments_emptied_is_the_same_report(self):
        self.check(add(s.policy('p', [])))


if __name__ == '__main__':
    unittest.main()
