"""NT-2 item 1: the typed, immutable snapshot adapter.

Cases: every fact carries its presence state; an empty completed collection differs from an uncollected one; JSON
null never stands for both an observed null and a failed collection; the three device identifiers stay apart;
display names are labels; the content hash ignores list order and moves with a membership change; the estate
adapter reuses the synthetic estate's own policies, groups and filters instead of copying their identities.
"""
import copy
import dataclasses
import unittest

from intune_iac import sim_model as m
from intune_iac.io import AppError, canonical
from intune_iac.synthetic import generate_estate
from plugin_tests import sim_support as s


def base():
    return s.snapshot_doc(
        devices=[s.device('a', osVersion='10.0.19045', model={'presence': 'observed_null'},
                          manufacturer={'presence': 'unknown'})],
        groups=[s.group('g1')], memberships=[s.member('g1', 'a')],
        policies=[s.policy('p1', [s.include('g1')])])


class FactPresence(unittest.TestCase):
    def test_every_presence_state_is_kept_with_its_provenance(self):
        doc = base()
        doc['devices'][0]['properties']['sku'] = {'presence': 'redacted'}
        doc['devices'][0]['properties']['edition'] = {'presence': 'unsupported'}
        device = m.load_snapshot(doc).devices[0]
        got = {name: fact.presence for name, fact in device.properties.items()}
        self.assertEqual(got, {'osVersion': 'known', 'model': 'observed_null', 'manufacturer': 'unknown',
                               'sku': 'redacted', 'edition': 'unsupported'})
        known = device.properties['osVersion']
        self.assertEqual((known.value, known.observed_at, known.source_ref, known.source_sha256),
                         ('10.0.19045', s.STAMP, 'synthetic-test', s.SHA))
        self.assertIsNone(device.properties['model'].value)
        self.assertIsNone(device.properties['manufacturer'].value)

    def test_json_null_is_refused_as_a_known_value(self):
        doc = base()
        doc['devices'][0]['properties']['model'] = None
        with self.assertRaises(AppError) as caught:
            m.load_snapshot(doc)
        self.assertEqual(caught.exception.code, 'sim_snapshot_invalid')

    def test_a_value_on_a_presence_that_has_none_is_refused(self):
        for presence in ('observed_null', 'unknown', 'absent', 'redacted', 'unsupported'):
            doc = base()
            doc['devices'][0]['properties']['model'] = {'presence': presence, 'value': 'x'}
            with self.assertRaises(AppError, msg=presence):
                m.load_snapshot(doc)

    def test_an_unknown_presence_word_is_refused(self):
        doc = base()
        doc['devices'][0]['properties']['model'] = {'presence': 'maybe'}
        with self.assertRaises(AppError):
            m.load_snapshot(doc)

    def test_a_property_not_listed_is_absent_not_null(self):
        device = m.load_snapshot(base()).devices[0]
        self.assertNotIn('deviceOwnership', device.properties)


class Collections(unittest.TestCase):
    def test_empty_completed_collection_differs_from_an_uncollected_one(self):
        doc = base()
        doc['collections'] = {'filters': {'complete': True}}
        snapshot = m.load_snapshot(doc)
        self.assertEqual(snapshot.filters, ())
        self.assertTrue(snapshot.collections['filters'].complete)
        self.assertEqual(snapshot.collections['filters'].presence, 'known')
        doc = base()
        del doc['filters']
        uncollected = m.load_snapshot(doc)
        self.assertFalse(uncollected.collections['filters'].complete)
        self.assertEqual(uncollected.collections['filters'].presence, 'unknown')

    def test_a_truncated_collection_keeps_its_reason(self):
        doc = base()
        doc['collections'] = {'policies': {'complete': False, 'reason': 'query_ceiling'}}
        state = m.load_snapshot(doc).collections['policies']
        self.assertEqual((state.complete, state.reason, state.presence), (False, 'query_ceiling', 'known'))

    def test_listed_collections_default_to_complete(self):
        self.assertTrue(m.load_snapshot(base()).collections['devices'].complete)


class Identity(unittest.TestCase):
    def test_the_three_device_identifiers_are_never_assumed_equal(self):
        device = m.load_snapshot(base()).devices[0]
        self.assertEqual(device.entra_device_id.presence, 'unknown')
        self.assertEqual(device.entra_object_id.presence, 'unknown')
        self.assertEqual(device.id_resolution, 'unresolved')
        self.assertNotEqual(device.entra_device_id.value, device.id)

    def test_explicit_entra_identifiers_are_kept_as_given(self):
        doc = base()
        doc['devices'][0]['entra_device_id'] = s.uid('entra-device/a')
        doc['devices'][0]['entra_object_id'] = s.uid('entra-object/a')
        device = m.load_snapshot(doc).devices[0]
        self.assertEqual(device.id_resolution, 'resolved')
        self.assertEqual(len({device.id, device.entra_device_id.value, device.entra_object_id.value}), 3)

    def test_duplicate_display_names_stay_two_groups(self):
        doc = base()
        doc['groups'] = [s.group('one', label='Pilot'), s.group('two', label='Pilot')]
        doc['memberships'] = []
        snapshot = m.load_snapshot(doc)
        self.assertEqual(len(snapshot.groups), 2)
        self.assertEqual(len(snapshot.group_by_id), 2)

    def test_duplicate_identifiers_are_refused(self):
        doc = base()
        doc['groups'] = [s.group('one'), s.group('one')]
        with self.assertRaises(AppError):
            m.load_snapshot(doc)

    def test_unknown_keys_are_refused_not_ignored(self):
        doc = base()
        doc['groups'][0]['surprise'] = True
        with self.assertRaises(AppError):
            m.load_snapshot(doc)

    def test_possible_membership_is_kept_apart_from_known(self):
        doc = base()
        doc['devices'].append(s.device('b'))
        doc['memberships'].append(s.member('g1', 'b', certainty='possible'))
        snapshot = m.load_snapshot(doc)
        g = s.uid('group/g1')
        self.assertEqual(snapshot.members_known[g], frozenset({s.uid('device/a')}))
        self.assertEqual(snapshot.members_possible[g], frozenset({s.uid('device/b')}))


class Immutability(unittest.TestCase):
    def test_the_snapshot_cannot_be_reassigned(self):
        snapshot = m.load_snapshot(base())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            snapshot.snapshot_id = 'other'
        with self.assertRaises(TypeError):
            snapshot.members_known['x'] = frozenset()

    def test_policy_bodies_are_copies(self):
        snapshot = m.load_snapshot(base())
        first = snapshot.policies[0].body
        first['name'] = 'mutated'
        self.assertNotEqual(snapshot.policies[0].body['name'], 'mutated')

    def test_the_source_document_is_not_retained(self):
        doc = base()
        snapshot = m.load_snapshot(doc)
        doc['policies'][0]['body']['name'] = 'changed after load'
        self.assertNotEqual(snapshot.policies[0].body['name'], 'changed after load')


class ContentHash(unittest.TestCase):
    def test_list_order_does_not_change_the_hash(self):
        doc = base()
        doc['devices'].append(s.device('b'))
        doc['groups'].append(s.group('g2'))
        shuffled = copy.deepcopy(doc)
        shuffled['devices'].reverse()
        shuffled['groups'].reverse()
        self.assertEqual(m.load_snapshot(doc).sha256, m.load_snapshot(shuffled).sha256)

    def test_a_membership_change_changes_the_hash(self):
        doc = base()
        changed = copy.deepcopy(doc)
        changed['devices'].append(s.device('b'))
        changed['memberships'].append(s.member('g1', 'b'))
        self.assertNotEqual(m.load_snapshot(doc).sha256, m.load_snapshot(changed).sha256)

    def test_the_hash_is_sha256_hex(self):
        self.assertRegex(m.load_snapshot(base()).sha256, r'^[0-9a-f]{64}$')


class Revision(unittest.TestCase):
    def test_revision_policies_are_typed_and_hashed(self):
        revision = m.load_revision(s.revision_doc([s.policy('p1', [s.include('g1')])], removed=['p2']))
        self.assertEqual(revision.policies[0].id, s.uid('policy/p1'))
        self.assertEqual(revision.removed_policy_ids, frozenset({s.uid('policy/p2')}))
        self.assertRegex(revision.sha256, r'^[0-9a-f]{64}$')

    def test_revision_hash_follows_content_not_order(self):
        a = s.revision_doc([s.policy('p1', []), s.policy('p2', [])])
        b = copy.deepcopy(a)
        b['policies'].reverse()
        self.assertEqual(m.load_revision(a).sha256, m.load_revision(b).sha256)

    def test_a_policy_cannot_be_both_changed_and_removed(self):
        with self.assertRaises(AppError):
            m.load_revision(s.revision_doc([s.policy('p1', [])], removed=['p1']))


class EstateAdapter(unittest.TestCase):
    def setUp(self):
        self.estate = generate_estate(seed=7, policy_count=3)
        self.truth = self.estate['truth']

    def test_policies_groups_and_filters_come_from_the_estate_not_a_copy(self):
        snapshot = m.snapshot_from_estate(self.estate)
        self.assertEqual({p.id for p in snapshot.policies}, {p['id'] for p in self.truth['policies']})
        self.assertEqual({g.id for g in snapshot.groups}, set(self.truth['groups']))
        self.assertEqual({f.id for f in snapshot.filters}, set(self.truth['filters']))
        self.assertEqual(snapshot.tenant_id, self.truth['tenant_id'])
        self.assertEqual(snapshot.realm_id, 'synthetic')

    def test_assignment_and_setting_shapes_match_the_estates_authored_truth(self):
        snapshot = m.snapshot_from_estate(self.estate)
        for authored in self.truth['policies']:
            body = snapshot.policy_by_id[authored['id']].body
            self.assertEqual(sorted(map(canonical, body['assignments'])), sorted(map(canonical, authored['assignments'])))
            self.assertEqual(body['settings'], authored['settings'])
            self.assertEqual(body['name'], authored['name'])
            self.assertEqual(body['technologies'], authored['technologies'])

    def test_duplicate_estate_labels_do_not_merge_policies(self):
        names = [p['name'] for p in self.truth['policies']]
        self.assertEqual(len(set(names)), 1)
        self.assertEqual(len(m.snapshot_from_estate(self.estate).policies), 3)

    def test_the_estate_has_no_devices_so_the_universe_is_uncollected(self):
        snapshot = m.snapshot_from_estate(self.estate)
        self.assertEqual(snapshot.devices, ())
        self.assertFalse(snapshot.collections['devices'].complete)
        self.assertEqual(snapshot.collections['devices'].presence, 'unknown')

    def test_a_population_adds_devices_and_memberships_without_touching_estate_identities(self):
        group = self.truth['groups'][0]
        population = {'devices': [s.device('a', osVersion='10.0.1')], 'users': [], 'user_device_contexts': [],
                      'group_domains': {group: 'device'},
                      'memberships': [{'group_id': group, 'member_id': s.uid('device/a'),
                                       'member_kind': 'device', 'certainty': 'known'}],
                      'filter_expressions': {self.truth['filters'][0]: {'expression': 'device.osVersion -ge "10.0"',
                                                                         'platform': 'windows10'}}}
        snapshot = m.snapshot_from_estate(self.estate, population)
        self.assertEqual(len(snapshot.devices), 1)
        self.assertEqual(snapshot.members_known[group], frozenset({s.uid('device/a')}))
        self.assertEqual(snapshot.group_by_id[group].member_domain, 'device')
        self.assertEqual(snapshot.filters[0].expression.presence, 'known')
        self.assertEqual({g.id for g in snapshot.groups}, set(self.truth['groups']))

    def test_a_filter_without_a_supplied_expression_is_unknown_not_empty(self):
        snapshot = m.snapshot_from_estate(self.estate)
        self.assertEqual(snapshot.filters[0].expression.presence, 'unknown')

    def test_a_denied_assignments_collection_is_incomplete_with_its_reason(self):
        estate = generate_estate(seed=7, policy_count=3, case='denied')
        snapshot = m.snapshot_from_estate(estate)
        state = snapshot.collections['assignments']
        self.assertFalse(state.complete)
        self.assertIn('access_denied', state.reason)

    def test_an_omitted_assignments_collection_is_uncollected(self):
        estate = generate_estate(seed=7, policy_count=3, case='omitted-assignments')
        state = m.snapshot_from_estate(estate).collections['assignments']
        self.assertEqual((state.presence, state.complete), ('unknown', False))

    def test_the_estate_is_not_mutated(self):
        before = copy.deepcopy(self.estate)
        m.snapshot_from_estate(self.estate)
        self.assertEqual(before, self.estate)


if __name__ == '__main__':
    unittest.main()
