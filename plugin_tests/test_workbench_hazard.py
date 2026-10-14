"""The primary hazard and its response stay in the first viewport (P-PRES-03, P-PRES-12, P-PRES-02).

An unknown operation outcome, a failed collection, a changed repository or a stale observation is shown in a band
that is part of the frame, so a long policy, an opened evidence layer, scrolling or a narrow window never hides it.
The band names the condition and the key that offers the response; the context strip drops routine states before
hazards; the navigation row stays labeled at every width. Expected words are written by hand.
"""
import io
import unittest

from intune_iac.workbench_tui import cell_width

TENANT = '11111111-1111-4111-8111-111111111111'
POLICY = '22222222-2222-4222-8222-222222222222'
OPERATION = '651a8ce8ff0e42d5a091c70ac13d21a1'
SIZES = ((120, 40), (80, 24), (60, 20), (48, 20))


def signal(area, code, observed='Recorded.', step='Step.', **evidence):
    return {'area': area, 'code': code, 'observed': observed, 'next_step': step, 'evidence': evidence}


UNKNOWN = signal('operations', 'operation_outcome_unknown',
                 'Operation %s was dispatched and its outcome is unknown: model_response_lost.' % OPERATION,
                 'reconcile /work/op reads the service independently; execution is never replayed.',
                 operation_id=OPERATION, operation_root='/work/op')
DENIED = signal('collection', 'collection_failed', 'The last collection of this policy (run 3) ended denied.',
                'Collect again (:collect) when the source is reachable.', status='denied', error_code='workbench_collection_denied')
CHANGED = signal('repository', 'repository_stale', 'The repository changed since its recorded intent.',
                 'Review the difference on the Repository surface, then repository-refresh REVISION records the current source.')
STALE = signal('freshness', 'observation_stale', 'The newest observation is stale.', 'Collect again (:collect).')
ALL = [UNKNOWN, DENIED, CHANGED, STALE,
       signal('operations', 'operation_diverged', operation_id=OPERATION, operation_root='/work/op'),
       signal('operations', 'operation_record_disagrees', operation_id=OPERATION, operation_root='/work/op'),
       signal('operations', 'operation_unreadable'),
       signal('collection', 'collection_not_finished'),
       signal('repository', 'repository_consumer_mismatch'),
       signal('repository', 'repository_unavailable')]
MINIMUM = (40, 12)


class StripTests(unittest.TestCase):
    def strip(self, facts, width):
        from intune_iac.workbench_screens import context_strip
        return context_strip(TENANT, POLICY, dict({'name': 'Windows Privacy Pilot'}, **facts), width, 'synthetic')

    def test_routine_states_give_way_before_a_hazard(self):
        facts = {'observation': 'fresh', 'repository': 'current', 'operation': 'outcome_unknown'}
        for width in (100, 80, 60):
            line = self.strip(facts, width)
            self.assertLessEqual(cell_width(line), width, line)
            self.assertTrue(line.startswith('SYNTHETIC | TENANT 11111111 | POLICY '), line)
            if 'OP' in line or 'OPERATION' in line:
                continue
            # When the operation state cannot fit, no routine state may have been kept instead of it.
            self.assertNotIn('fresh', line, line); self.assertNotIn('current', line, line)
        self.assertIn('OP unknown', self.strip(facts, 80))

    def test_without_a_hazard_the_order_is_unchanged(self):
        facts = {'observation': 'fresh', 'repository': 'current', 'operation': 'succeeded_verified'}
        self.assertEqual(self.strip(facts, 200), 'SYNTHETIC | TENANT 11111111 | POLICY Windows Privacy Pilot (22222222) | '
                                                  'OBSERVED fresh | REPOSITORY current | OPERATION succeeded_verified')


class TabLineTests(unittest.TestCase):
    def test_navigation_stays_labeled_at_every_width(self):
        from intune_iac.workbench_screens import tab_line
        from intune_iac.workbench_tui import TABS
        for width in (120, 80, 61, 60, 48):
            line = tab_line(TABS, 1, width)
            self.assertLessEqual(cell_width(line), width, line)
            self.assertIn('Insp', line, line)
            # Never a row of bare digits: either every surface is named, or the line says how to reach them.
            if not all(name[:3] in line for name in TABS):
                self.assertIn('1-9', line, line)
                self.assertIn('?', line, line)


class BandTests(unittest.TestCase):
    def band(self, facts, signals, width):
        from intune_iac.workbench_screens import hazard_band
        return hazard_band(facts, signals, width)

    def test_an_unknown_outcome_leads_with_its_response(self):
        for width in (120, 80, 60, 48):
            line = self.band({'operation': 'outcome_unknown'}, [UNKNOWN], width)
            self.assertLessEqual(cell_width(line), width, line)
            self.assertTrue(line.startswith('! '), line)
            self.assertIn('unknown', line.lower(), line)
            self.assertIn('a: reconcile', line, line)
        self.assertIn(OPERATION[:8], self.band({'operation': 'outcome_unknown'}, [UNKNOWN], 120))

    def test_the_operation_outranks_other_conditions_and_the_rest_are_counted(self):
        line = self.band({'operation': 'outcome_unknown', 'observation': 'stale', 'repository': 'stale'},
                         [STALE, CHANGED, DENIED, UNKNOWN], 120)
        self.assertIn('a: reconcile', line)
        self.assertIn('+3 more: i', line)

    def test_each_condition_names_its_own_response(self):
        cases = ((DENIED, {'observation': 'stale'}, 'a: collect'), (CHANGED, {'repository': 'stale'}, 'a: refresh'),
                 (STALE, {'observation': 'stale'}, 'a: collect'))
        for found, facts, response in cases:
            line = self.band(facts, [found], 80)
            self.assertIn(response, line, line)
            self.assertLessEqual(cell_width(line), 80, line)

    def test_a_newer_result_never_hides_a_recorded_condition(self):
        # Only a newer read retires a recorded condition; the workspace reads again after any command that may write.
        self.assertIn('a: reconcile', self.band({'operation': 'reconciled', 'operation_id': OPERATION}, [UNKNOWN], 80))

    def test_the_count_survives_at_the_minimum_width(self):
        from intune_iac.workbench_screens import hazard_rows
        rows = hazard_rows({}, [ALL[6], DENIED], MINIMUM[0])
        self.assertTrue(all(cell_width(row) <= MINIMUM[0] for row in rows), rows)
        self.assertIn('+1 more: i', ' '.join(rows))

    def test_a_service_changed_since_the_observation_shows_when_nothing_outranks_it(self):
        eligibility = {'code': 'maintenance_observation_stale', 'reason': 'service_changed', 'observed_revision': 1,
                       'service_revision': 2}
        line = self.band({'eligibility': eligibility}, [], 80)
        self.assertIn('a: collect', line)
        self.assertIn('changed', line.lower())
        line = self.band({'eligibility': eligibility, 'operation': 'outcome_unknown'}, [UNKNOWN], 120)
        self.assertIn('a: reconcile', line)
        self.assertIn('+1 more: i', line)

    def test_another_tenant_leads_the_band(self):
        eligibility = {'code': 'maintenance_observation_incomplete', 'reason': 'tenant_mismatch'}
        self.assertIn('tenant', self.band({'eligibility': eligibility}, [UNKNOWN, DENIED], 120).lower())

    def test_another_operations_result_never_hides_an_unknown_outcome(self):
        line = self.band({'operation': 'prepared', 'operation_id': 'f' * 32}, [UNKNOWN], 120)
        self.assertIn('a: reconcile', line)
        self.assertIn(OPERATION[:8], line)

    def test_two_unknown_outcomes_are_both_counted(self):
        second = signal('operations', 'operation_outcome_unknown', 'Another operation is unknown.', 'Reconcile it.',
                        operation_id='e' * 32, operation_root='/work/other')
        self.assertIn('+1 more: i', self.band({}, [UNKNOWN, second], 120))

    def test_an_operation_known_only_from_this_session_still_shows(self):
        line = self.band({'operation': 'outcome_unknown'}, [], 80)
        self.assertIn('a: reconcile', line)

    def test_no_hazard_draws_no_band(self):
        self.assertIsNone(self.band({'observation': 'fresh', 'repository': 'current'}, [], 80))


class MinimumTests(unittest.TestCase):
    """At the documented minimum the hazard, its response and the identities are whole, never cut."""
    def test_the_documented_minimum_is_40_by_12(self):
        from intune_iac.workbench_tui import MIN_SIZE
        self.assertEqual(MIN_SIZE, MINIMUM)

    def test_every_condition_fits_whole_at_the_minimum_width(self):
        from intune_iac.workbench_screens import hazard_band
        for found in ALL:
            line = hazard_band({}, [found], MINIMUM[0])
            self.assertLessEqual(cell_width(line), MINIMUM[0], line)
            self.assertNotIn('...', line); self.assertNotIn('\u2026', line)
            self.assertRegex(line, r'[a9i]: [a-z]', line)  # a: action, 9: repository, i: details

    def test_the_key_line_and_footer_stay_whole_at_the_minimum_width(self):
        from intune_iac.workbench_tui import help_line, status_line
        keys = help_line(MINIMUM[0])
        self.assertLessEqual(cell_width(keys), MINIMUM[0], keys)
        self.assertIn('q exit', keys)
        footer = status_line('synthetic', 1, 2, 66, MINIMUM[0])
        self.assertLessEqual(cell_width(footer), MINIMUM[0], footer)
        self.assertTrue(footer.endswith(('no automatic approval', 'no auto-approval')), footer)

    def test_the_strip_keeps_mode_tenant_and_whole_policy_at_the_minimum_width(self):
        from intune_iac.workbench_screens import context_strip
        facts = {'name': 'A very long policy name ' * 3, 'observation': 'stale', 'repository': 'stale',
                 'operation': 'outcome_unknown'}
        for mode, word in (('synthetic', 'SYNTHETIC'), ('graph_authenticated_observation', 'LIVE READ-ONLY'),
                           (None, 'MODE UNKNOWN')):
            line = context_strip(TENANT, POLICY, facts, MINIMUM[0], mode)
            self.assertLessEqual(cell_width(line), MINIMUM[0], line)
            self.assertTrue(line.startswith(word + ' | '), line)
            self.assertIn('11111111', line); self.assertIn('22222222', line)
            line = context_strip(TENANT, None, {}, MINIMUM[0], mode)
            self.assertLessEqual(cell_width(line), MINIMUM[0], line)
            self.assertTrue(line.startswith(word + ' | '), line); self.assertIn('11111111', line)


class FrameTests(unittest.TestCase):
    """The band is chrome: every layer, every scroll position and every size in the matrix shows it."""
    def frame(self, size, layer='summary', scroll=0, lines=200):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        out = io.StringIO()
        workspace.__dict__.update(
            stdout=out, tab=1, value={'object_id': POLICY, 'evidence_class': 'synthetic'}, scroll=scroll, mode=None,
            notice='Ready.', rules='unicode', color=False, theme='dark', selected=POLICY, layer=layer,
            facts={'object_id': POLICY, 'name': 'Windows Privacy Pilot', 'observation': 'fresh', 'repository': 'current',
                   'operation': 'outcome_unknown', 'signals': [UNKNOWN]},
            store=type('S', (), {'tenant_id': TENANT})(), mode_class='synthetic', last_command='inspect')
        workspace._terminal_size = lambda: size
        workspace._data_lines = lambda width: ['metadata line %d %s' % (index, 'x' * 70) for index in range(lines)]
        workspace.draw()
        return [row for row in out.getvalue().replace('\x1b[H', '').replace('\x1b[J', '').split('\r\n')]

    def test_the_band_survives_layers_scrolling_and_the_size_matrix(self):
        for size in SIZES:
            for layer in ('summary', 'details', 'raw'):
                for scroll in (0, 10_000):
                    rows = self.frame(size, layer, scroll)
                    self.assertEqual(len(rows), size[1], (size, layer, scroll))
                    band = [row for row in rows if row.lstrip('\x1b[1m').startswith('! ')]
                    self.assertTrue(band, (size, layer, scroll, rows[:5]))
                    self.assertIn('a: reconcile', band[0], (size, band[0]))
                    for row in rows:
                        self.assertLessEqual(cell_width(row.replace('\x1b[1m', '').replace('\x1b[22m', '')), size[0], row)

    def test_at_the_minimum_size_the_full_frame_is_drawn(self):
        rows = self.frame(MINIMUM)
        self.assertEqual(len(rows), MINIMUM[1])
        self.assertTrue(any('a: reconcile' in row for row in rows))
        self.assertTrue(any(row.startswith('\u250c') for row in rows), rows)

    def test_below_the_minimum_a_constrained_state_keeps_the_hazard(self):
        for size in ((39, 30), (60, 11), (30, 8), (24, 3)):
            rows = self.frame(size)
            plain = [row.replace('\x1b[1m', '').replace('\x1b[22m', '') for row in rows]
            self.assertEqual(len(rows), size[1], size)
            for row in plain:
                self.assertLessEqual(cell_width(row), size[0], (size, row))
            joined = '\n'.join(plain)
            self.assertIn('a: reconcile', joined, size)
            self.assertIn('unknown', joined.lower(), size)
            self.assertIn('below 40x12', joined.lower(), size)
            self.assertNotIn('metadata line', joined, size)  # no body below the minimum

    def test_the_band_sits_above_the_body_in_the_first_rows(self):
        rows = self.frame((48, 20))
        index = next(index for index, row in enumerate(rows) if row.replace('[1m', '').startswith('! '))
        self.assertLess(index, 5)


if __name__ == '__main__':
    unittest.main()
