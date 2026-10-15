"""NT-2 item 5: the 30,000-device synthetic fleet, checked for correctness first and then timed.

The expected device sets are computed here by enumerating every admissible completion of the uncertain facts and
applying the model's reference rule to each, which is independent of the evaluator's three-valued logic. The
evaluator's lower and upper sets must be sound against that enumeration, and equal to it for every device whose
facts are all known. Timing uses a monotonic clock, is printed as a measurement and is never asserted against a
target: the model sets none and the measurement is a baseline, not an operating limit.
"""
import itertools
import json
import unittest

from intune_iac import sim_eval, sim_fixture, sim_model, sim_profile, sim_result

MODELS = ('M1', 'M2', 'M3', 'M4', 'other')


def reference_applies(principal, kind, model, policy, user_groups, member, filters):
    """The reference rule of SIMULATOR_MODEL.md section 4 for one principal in one completed world."""
    def here(group_id):
        return (group_id in user_groups) == (kind == 'user')
    rows = [a for a in policy['assignments'] if a.get('group_id') and here(a['group_id'])]
    if any(a['type'] == 'exclusionGroupAssignmentTarget' and member(a['group_id'], principal) for a in rows):
        return False
    active = [a for a in rows if a['type'] == 'groupAssignmentTarget' and member(a['group_id'], principal)]
    exclude = [a for a in active if a['filter_type'] == 'exclude']
    if exclude:
        return not any(filters[a['filter_id']] == model for a in exclude)
    if any(a['filter_type'] == 'none' for a in active):
        return True
    return any(filters[a['filter_id']] == model for a in active if a['filter_type'] == 'include')


class Fixture(unittest.TestCase):
    def test_the_fleet_is_deterministic_and_has_the_hard_cases(self):
        a = sim_fixture.build_fleet(seed=3, devices=600)
        b = sim_fixture.build_fleet(seed=3, devices=600)
        self.assertEqual(sim_model.load_snapshot(a[0]).sha256, sim_model.load_snapshot(b[0]).sha256)
        other = sim_model.load_snapshot(sim_fixture.build_fleet(seed=4, devices=600)[0])
        self.assertNotEqual(sim_model.load_snapshot(a[0]).sha256, other.sha256)
        snapshot = sim_model.load_snapshot(a[0])
        names = [g.display_name for g in snapshot.groups if g.member_domain == 'device']
        self.assertGreater(len(names), len(set(names)), 'duplicate display names are part of the fleet')
        per_device = {}
        for c in snapshot.contexts:
            per_device.setdefault(c.device_id, set()).add(c.user_id)
        self.assertTrue(any(len(users) > 1 for users in per_device.values()), 'multi-user devices')
        self.assertTrue(any(d.sharing == 'shared' for d in snapshot.devices))
        presences = {f.presence for d in snapshot.devices for f in d.properties.values()}
        self.assertTrue({'known', 'unknown', 'observed_null'} <= presences)

    def test_an_incomplete_variant_is_marked_incomplete(self):
        snapshot = sim_model.load_snapshot(sim_fixture.build_fleet(seed=3, devices=100, complete=False)[0])
        self.assertFalse(snapshot.collections['devices'].complete)


class Correctness(unittest.TestCase):
    def check(self, devices, seed):
        doc, revision = sim_fixture.build_fleet(seed=seed, devices=devices)
        result = sim_eval.simulate(sim_model.load_snapshot(doc), sim_model.load_revision(revision), sim_profile.load_profile({}))
        sim_result.validate_result(result.to_schema())
        user_groups = frozenset(g['id'] for g in doc['groups'] if g['member_domain'] == 'user')
        filters = {f['id']: f['expression'].split('"')[1] for f in doc['filters']}
        known, possible = {}, {}
        for m in doc['memberships']:
            (known if m['certainty'] == 'known' else possible).setdefault(m['group_id'], set()).add(m['member_id'])
        contexts = {}
        for c in doc['user_device_contexts']:
            contexts.setdefault(c['device_id'], []).append(c)
        after = {p['id']: p for p in doc['policies'] if p['id'] not in revision['removed_policy_ids']}
        after.update({p['id']: p for p in revision['policies']})
        checked = exact_checked = 0
        for pid, worlds in result.detail['policies'].items():
            policy = after.get(pid)
            if policy is None:
                self.assertEqual(worlds['after']['upper_devices'], frozenset())
                continue
            lower, upper = worlds['after']['lower_devices'], worlds['after']['upper_devices']
            for device in doc['devices']:
                did = device['id']
                prop = device['properties'].get('model')
                if isinstance(prop, dict) and prop.get('presence') == 'unknown':
                    options = MODELS
                else:
                    options = (None,) if isinstance(prop, dict) else (prop,)
                maybe = [(g, did) for g in possible if did in possible[g]]
                shared = device.get('sharing') == 'shared'
                signed = [c['user_id'] for c in contexts.get(did, []) if c['relation'] == 'signed_in' and not shared]
                maybe_ctx = [c['user_id'] for c in contexts.get(did, []) if c['relation'] != 'signed_in' or shared]
                hits = set()
                for model in options:
                    for chosen in itertools.product((False, True), repeat=len(maybe)):
                        taken = {pair for pair, take in zip(maybe, chosen) if take}

                        def member(group_id, principal, taken=taken):
                            return principal in known.get(group_id, ()) or (group_id, principal) in taken
                        for ctx_choice in itertools.product((False, True), repeat=len(maybe_ctx)):
                            users = signed + [u for u, take in zip(maybe_ctx, ctx_choice) if take]
                            hits.add(reference_applies(did, 'device', model, policy['body'], user_groups, member, filters)
                                     or any(reference_applies(u, 'user', model, policy['body'], user_groups, member, filters)
                                            for u in users))
                expected_lower = hits == {True}
                expected_upper = True in hits
                checked += 1
                if did in lower:
                    self.assertTrue(expected_lower, (pid, did))
                if expected_upper:
                    self.assertIn(did, upper, (pid, did))
                if not maybe and not maybe_ctx and len(options) == 1:
                    exact_checked += 1
                    self.assertEqual(did in lower, expected_lower, (pid, did))
                    self.assertEqual(did in upper, expected_upper, (pid, did))
        self.assertGreater(checked, 0)
        self.assertGreater(exact_checked, checked // 2)

    def test_a_small_fleet_is_sound_and_exact_where_facts_are_known(self):
        self.check(devices=400, seed=11)

    def test_a_thirty_thousand_device_fleet_is_sound_and_exact_where_facts_are_known(self):
        self.check(devices=30000, seed=1)


class Measurement(unittest.TestCase):
    def test_the_measurement_is_taken_with_a_monotonic_clock_and_reported(self):
        report = sim_fixture.measure(seed=1, devices=30000, repeats=3)
        print('\nSIM_BENCH ' + json.dumps(report, sort_keys=True))
        self.assertEqual(report['clock'], 'time.monotonic_ns')
        self.assertEqual(report['devices'], 30000)
        self.assertEqual(len(report['simulate_ns']), 3)
        for key in ('build_ns', 'load_snapshot_ns', 'cold_simulate_ns', 'warm_simulate_min_ns', 'peak_rss_kib',
                    'cohorts', 'findings'):
            self.assertIn(key, report)
        self.assertTrue(all(isinstance(v, int) and v > 0 for v in report['simulate_ns']))
        self.assertEqual(report['cold_simulate_ns'], report['simulate_ns'][0])
        self.assertEqual(report['warm_simulate_min_ns'], min(report['simulate_ns'][1:]))
        self.assertNotIn('target', report)

    def test_the_same_seed_gives_the_same_result_digest(self):
        a = sim_fixture.measure(seed=2, devices=300, repeats=2)
        b = sim_fixture.measure(seed=2, devices=300, repeats=2)
        self.assertEqual(a['result_sha256'], b['result_sha256'])
        self.assertRegex(a['result_sha256'], r'^[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
