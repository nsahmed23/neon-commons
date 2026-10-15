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

    def test_state_words_read_as_words(self):
        self.assertIn('OP outcome unknown', self.strip({'operation': 'outcome_unknown'}, 200))

    def test_without_a_hazard_the_order_is_unchanged(self):
        facts = {'observation': 'fresh', 'repository': 'current', 'operation': 'succeeded_verified'}
        self.assertEqual(self.strip(facts, 200), 'SYNTHETIC | TENANT 11111111 | POLICY Windows Privacy Pilot (22222222) | '
                                                  'OBS fresh | REPO current | OP succeeded verified')


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

    def band_text(self, facts, signals, width):
        """Every row of the band: the count of other findings may take a row of its own."""
        from intune_iac.workbench_screens import hazard_rows
        return ' '.join(hazard_rows(facts, signals, width))

    def test_an_unknown_outcome_leads_with_its_response(self):
        for width in (120, 80, 60, 48):
            line = self.band({'operation': 'outcome_unknown'}, [UNKNOWN], width)
            self.assertLessEqual(cell_width(line), width, line)
            self.assertTrue(line.startswith('! '), line)
            self.assertIn('unknown', line.lower(), line)
            self.assertIn('Reconcile', line, line)
        self.assertIn(OPERATION[:8], self.band({'operation': 'outcome_unknown'}, [UNKNOWN], 120))

    def test_the_operation_outranks_other_conditions_and_the_rest_are_counted(self):
        line = self.band_text({'operation': 'outcome_unknown', 'observation': 'stale', 'repository': 'stale'},
                              [STALE, CHANGED, DENIED, UNKNOWN], 120)
        self.assertIn('Reconcile', line)
        self.assertIn('+3 more findings (2 Inspector)', line)

    def test_each_condition_names_its_own_response(self):
        cases = ((DENIED, {'observation': 'stale'}, 'Collect'), (CHANGED, {'repository': 'stale'}, 'Refresh'),
                 (STALE, {'observation': 'stale'}, 'Collect'))
        for found, facts, response in cases:
            line = self.band(facts, [found], 80)
            self.assertIn(response, line, line)
            self.assertLessEqual(cell_width(line), 80, line)

    def test_a_newer_result_never_hides_a_recorded_condition(self):
        # Only a newer read retires a recorded condition; the workspace reads again after any command that may write.
        self.assertIn('Reconcile', self.band({'operation': 'reconciled', 'operation_id': OPERATION}, [UNKNOWN], 80))

    def test_the_count_survives_at_the_minimum_width(self):
        from intune_iac.workbench_screens import hazard_rows
        rows = hazard_rows({}, [ALL[6], DENIED], MINIMUM[0])
        self.assertTrue(all(cell_width(row) <= MINIMUM[0] for row in rows), rows)
        self.assertIn('+1 more finding (2 Inspector)', ' '.join(rows))

    def test_a_service_changed_since_the_observation_shows_when_nothing_outranks_it(self):
        eligibility = {'code': 'maintenance_observation_stale', 'reason': 'service_changed', 'observed_revision': 1,
                       'service_revision': 2}
        line = self.band({'eligibility': eligibility}, [], 80)
        self.assertIn('Collect', line)
        self.assertIn('changed', line.lower())
        line = self.band_text({'eligibility': eligibility, 'operation': 'outcome_unknown'}, [UNKNOWN], 120)
        self.assertIn('Reconcile', line)
        self.assertIn('+1 more finding (2 Inspector)', line)

    def test_another_tenant_leads_the_band(self):
        eligibility = {'code': 'maintenance_observation_incomplete', 'reason': 'tenant_mismatch'}
        self.assertIn('tenant', self.band({'eligibility': eligibility}, [UNKNOWN, DENIED], 120).lower())

    def test_another_operations_result_never_hides_an_unknown_outcome(self):
        line = self.band({'operation': 'prepared', 'operation_id': 'f' * 32}, [UNKNOWN], 120)
        self.assertIn('Reconcile', line)
        self.assertIn(OPERATION[:8], line)

    def test_two_unknown_outcomes_are_both_counted(self):
        second = signal('operations', 'operation_outcome_unknown', 'Another operation is unknown.', 'Reconcile it.',
                        operation_id='e' * 32, operation_root='/work/other')
        self.assertIn('+1 more finding (2 Inspector)', self.band_text({}, [UNKNOWN, second], 120))

    def test_an_operation_known_only_from_this_session_still_shows(self):
        line = self.band({'operation': 'outcome_unknown'}, [], 80)
        self.assertIn('Reconcile', line)

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
            self.assertRegex(line, r'[a9i2]: [a-z]|\(a actions\)', line)  # a: action, 9: repository, i: details

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


class VisionReviewTests(unittest.TestCase):
    """Findings of the rendered-frame review (Gemini, run I) that were accepted."""
    ELIGIBILITY = {'code': 'maintenance_observation_stale', 'reason': 'service_changed', 'observed_revision': 1,
                   'service_revision': 2}

    def test_the_count_points_where_every_finding_is_listed(self):
        from intune_iac.workbench_screens import hazard_rows
        line = ' '.join(hazard_rows({'eligibility': self.ELIGIBILITY}, [UNKNOWN], 120))
        self.assertIn('+1 more finding (2 Inspector)', line)

    def test_the_inspector_lists_the_proposal_check_with_the_findings(self):
        from intune_iac.workbench_screens import _attention_lines
        value = {'attention': {'status': 'clear', 'signals': [], 'checked': {'operations': 'clear'}},
                 'observation_eligibility': self.ELIGIBILITY, 'actions': []}
        text = '\n'.join(_attention_lines(value, 120))
        self.assertIn('The source changed since this observation was captured (revision 1, now 2)', text)
        self.assertNotIn('No signal in the areas checked', text)
        # a lists the actions; it is not the collect key.
        self.assertIn('Collect again; a lists it', text)
        self.assertNotIn('(a)', text)

    def test_the_strip_never_says_fresh_beside_a_changed_service(self):
        from intune_iac.workbench_screens import context_strip
        line = context_strip(TENANT, POLICY, {'name': 'Pilot', 'observation': 'fresh', 'eligibility': self.ELIGIBILITY},
                             200, 'synthetic')
        self.assertIn('OBS source changed', line)
        self.assertNotIn('fresh', line)

    def test_available_actions_say_so_in_the_inspector(self):
        from intune_iac.workbench_screens import _attention_lines
        value = {'attention': {'status': 'clear', 'signals': [], 'checked': {}},
                 'actions': [{'kind': 'collect', 'label': 'Collect again', 'available': True, 'blocked': None}]}
        self.assertIn('Collect again (available)', '\n'.join(_attention_lines(value, 120)))

    def test_the_key_line_offers_the_bands_key_at_every_width(self):
        from intune_iac.workbench_tui import help_line
        for width in (120, 80, 48, 40):
            line = help_line(width, lead=('a actions',))
            self.assertLessEqual(cell_width(line), width, line)
            self.assertIn('a actions', line, width)
            self.assertIn('q exit', line, width)

    def test_below_the_minimum_only_keys_that_work_there_are_offered(self):
        from intune_iac.workbench_screens import constrained_rows
        facts = {'object_id': POLICY, 'operation': 'outcome_unknown', 'signals': [UNKNOWN, DENIED]}
        lines, _ = constrained_rows(TENANT, POLICY, facts, 'synthetic', 36, 10, '40x12', 'Ready.')
        text = '\n'.join(lines)
        self.assertIn('+1 more', text)
        self.assertNotIn('(2 Inspector)', text)  # no surface can be shown here
        self.assertNotIn('Esc', text)  # nothing is being typed
        self.assertIn('q exits', text)
        lines, _ = constrained_rows(TENANT, POLICY, facts, 'synthetic', 36, 10, '40x12', ':collect|', typing=True)
        text = '\n'.join(lines)
        self.assertIn('Esc discards', text)
        self.assertNotIn('q exits', text)  # q is typed into the command

    def test_the_actions_list_has_its_own_key_line(self):
        from intune_iac.workbench_tui import help_line
        for width in (120, 48, 40):
            line = help_line(width, 'actions', lead=('a actions',))
            self.assertLessEqual(cell_width(line), width, line)
            self.assertIn('Enter stages', line)
            self.assertIn('Esc closes', line)
            self.assertNotIn('a actions', line)

    def test_the_footer_never_cuts_the_evidence_class_mid_word(self):
        from intune_iac.workbench_tui import status_line
        self.assertEqual(status_line('synthetic_local_process_and_modeled_service_only', 1, 15, 17, 80, short='SYNTHETIC'),
                         '[synthetic] rows 1-15/17 | no automatic approval')
        self.assertEqual(status_line('synthetic', 1, 2, 66, 40, short='SYNTHETIC'), 'rows 1-2/66 | no automatic approval')


class FrameTests(unittest.TestCase):
    """The band is chrome: every layer, every scroll position and every size in the matrix shows it."""
    def frame(self, size, layer='summary', scroll=0, lines=200, **extra):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        out = io.StringIO()
        workspace.__dict__.update(
            stdout=out, tab=1, value={'object_id': POLICY, 'evidence_class': 'synthetic'}, scroll=scroll, mode=None,
            notice='Ready.', rules='unicode', color=False, theme='dark', selected=POLICY, layer=layer,
            facts={'object_id': POLICY, 'name': 'Windows Privacy Pilot', 'observation': 'fresh', 'repository': 'current',
                   'operation': 'outcome_unknown', 'signals': [UNKNOWN]},
            store=type('S', (), {'tenant_id': TENANT})(), mode_class='synthetic', last_command='inspect')
        workspace.__dict__.update(extra)
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
                    self.assertIn('Reconcile', band[0], (size, band[0]))
                    for row in rows:
                        self.assertLessEqual(cell_width(row.replace('\x1b[1m', '').replace('\x1b[22m', '')), size[0], row)

    def test_at_the_minimum_size_the_full_frame_is_drawn(self):
        rows = self.frame(MINIMUM)
        self.assertEqual(len(rows), MINIMUM[1])
        self.assertTrue(any('Reconcile' in row for row in rows))
        self.assertTrue(any(row.startswith('\u250c') for row in rows), rows)

    def test_below_the_minimum_a_constrained_state_keeps_the_hazard(self):
        for size in ((39, 30), (60, 11), (30, 8), (24, 3)):
            rows = self.frame(size)
            plain = [row.replace('\x1b[1m', '').replace('\x1b[22m', '') for row in rows]
            self.assertEqual(len(rows), size[1], size)
            for row in plain:
                self.assertLessEqual(cell_width(row), size[0], (size, row))
            joined = '\n'.join(plain)
            self.assertIn('Reconcile', joined, size)
            self.assertIn('unknown', joined.lower(), size)
            self.assertIn('below 40x12', joined.lower(), size)
            self.assertNotIn('metadata line', joined, size)  # no body below the minimum

    def test_the_band_names_the_action_and_says_the_key_opens_actions(self):
        # TASK-11 2.6 item 4: one canonical action name; a opens the actions, it does not perform the named one.
        for size in SIZES + (MINIMUM,):
            rows = self.frame(size)
            band = ' '.join(row.replace('\x1b[1m', '').replace('\x1b[22m', '') for row in rows if '! ' in row[:8])
            self.assertIn('Reconcile', band, size)
            self.assertTrue('(a: actions)' in band or '(a actions)' in band, (size, band))
            self.assertNotIn('a: reconcile', band, size)
        first = next(row for row in self.frame(MINIMUM) if '! ' in row[:8])
        self.assertIn('(a actions)', first)  # the hazard and its response on one row at the minimum width

    def staged_frame(self, size, signals=()):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        out = io.StringIO()
        workspace.__dict__.update(
            stdout=out, tab=8, value={'object_id': POLICY, 'evidence_class': 'synthetic'}, scroll=0, mode=None,
            notice='', rules='unicode', color=False, theme='dark', selected=POLICY, layer='summary', submission_key='enter',
            facts={'object_id': POLICY, 'name': 'Windows Privacy Pilot', 'signals': list(signals)}, staged=None,
            store=type('S', (), {'tenant_id': TENANT})(), mode_class='synthetic', last_command='repository-status')
        workspace._terminal_size = lambda: size
        workspace._data_lines = lambda width: ['body line %d' % index for index in range(60)]
        action = {'kind': 'repository-refresh', 'label': 'Refresh the repository intent', 'command': 'repository-refresh ',
                  'cursor': len('repository-refresh '), 'needs': ['REVISION: the full 40-character commit ID'], 'binding': {}}
        workspace._stage_after_difference(action, {'schema_version': 'workbench-repository-status/1', 'object_id': POLICY,
                                                   'freshness': {'status': 'stale', 'resolution_sha256': 'c' * 64}})
        workspace.draw()
        return workspace, [row for row in out.getvalue().replace('\x1b[H', '').replace('\x1b[J', '').split('\r\n')]

    def test_while_a_command_is_typed_the_key_line_names_the_typing_keys(self):
        # Journey 27 run 1 frame 35: the actions key line (Enter stages, Esc closes, q exit) stayed while a staged
        # command was edited, where Enter submits, Esc cancels and q is typed into the command.
        for size in ((120, 40), (80, 24), MINIMUM):
            workspace, rows = self.staged_frame(size)
            keys = rows[-1].rstrip()
            self.assertTrue(keys.startswith('Enter submits | Esc cancels'), (size, keys))
            self.assertNotIn('stages', keys)
            self.assertNotIn('q exit', keys)
            self.assertLessEqual(cell_width(keys), size[0])

    def test_the_status_bar_names_the_evidence_class_in_words(self):
        # Frame-review items 23 and 29: no snake_case class and no uppercase-only short form in the status bar.
        from intune_iac.workbench_tui import status_line
        from intune_iac.workbench_screens import mode_word
        scope = 'synthetic_local_process_and_modeled_service_only'
        self.assertTrue(status_line(scope, 1, 3, 3, 120, short=mode_word(scope)).startswith(
            '[synthetic local process and modeled service only] rows 1-3/3'))
        self.assertTrue(status_line(scope, 1, 3, 3, 60, short=mode_word(scope)).startswith('[synthetic] rows 1-3/3'))

    def test_a_staged_refresh_states_its_whole_boundary_before_the_mechanics(self):
        # TASK-11 2.6 item 1: the boundary is complete at 120 and 80 columns and usable at the minimum.
        for size, boundary in (((120, 40), 'STAGED refresh: records a new intent only; no Git commit, approval or apply.'),
                               ((80, 24), 'STAGED refresh: records a new intent only; no Git commit, approval or apply.'),
                               ((48, 20), 'STAGED refresh: no commit, approval or apply.'),
                               (MINIMUM, 'New intent only; no commit/approve/apply')):
            workspace, rows = self.staged_frame(size)
            index = next(i for i, row in enumerate(rows) if row.rstrip() == boundary)
            self.assertIn('Esc cancels', rows[index + 1], (size, rows[index + 1]))
            self.assertTrue(rows[index + 2].startswith(':repository-refresh'), (size, rows[index + 2]))
            self.assertEqual(len(rows), size[1], size)
            for row in rows:
                self.assertLessEqual(cell_width(row), size[0], (size, row))
        self.assertTrue(workspace.notice.startswith('STAGED refresh: no Git commit, approval or apply.'), workspace.notice)

    def test_a_staged_command_keeps_its_instruction_on_screen(self):
        instruction = 'STAGED refresh: type the REVISION at the cursor; Enter records it; Esc discards.'
        for size in ((120, 40), (48, 20)):
            rows = self.frame(size, mode='command', buffer='repository-refresh  ' + 'c' * 64,
                              cursor=len('repository-refresh '), staged={'kind': 'repository-refresh', 'binding': {}},
                              notice=instruction)
            text = '\n'.join(rows)
            self.assertIn('STAGED refresh: type the REVISION', text, size)
            self.assertIn(':repository-refresh', text, size)

    def test_the_key_line_names_the_bands_key(self):
        for size in ((120, 40), (48, 20), (40, 12)):
            rows = self.frame(size)
            self.assertIn('a actions', rows[-1], (size, rows[-1]))

    def test_the_band_sits_above_the_body_in_the_first_rows(self):
        rows = self.frame((48, 20))
        index = next(index for index, row in enumerate(rows) if row.replace('[1m', '').startswith('! '))
        self.assertLess(index, 5)


if __name__ == '__main__':
    unittest.main()


class SharedPrefixTests(unittest.TestCase):
    """Eight characters are not assumed unique (TASK-11 2.6 item 6). The read model gives each shortened identity the
    shortest prefix no other policy or operation in the store shares; every short form on these surfaces uses it."""
    PREFIXES = {POLICY: POLICY[:10], OPERATION: OPERATION[:9]}

    def test_the_strip_and_the_constrained_state_name_the_policy_by_its_unique_prefix(self):
        from intune_iac.workbench_screens import constrained_rows, context_strip
        facts = {'name': 'Windows Privacy Pilot', 'identity_prefixes': self.PREFIXES}
        self.assertIn('(22222222-2)', context_strip(TENANT, POLICY, facts, 200, 'synthetic'))
        self.assertIn('P 22222222-2', context_strip(TENANT, POLICY, facts, 40, 'synthetic'))
        # Width-only and height-only below the 40x12 minimum, then the minimum's own strip.
        for width, height in ((39, 12), (40, 11)):
            lines, _ = constrained_rows(TENANT, POLICY, dict(facts, signals=[UNKNOWN]), 'synthetic', width, height,
                                        '40x12', 'Viewing Inspector.')
            joined = '\n'.join(lines)
            self.assertIn('P 22222222-2', joined)
            self.assertIn('below 40x12', joined)
            self.assertTrue(all(cell_width(line) <= width for line in lines), lines)

    def test_the_band_and_the_state_name_the_operation_by_its_unique_prefix(self):
        from intune_iac.workbench_screens import hazard_rows, state_lines
        rows = hazard_rows({'identity_prefixes': self.PREFIXES}, [UNKNOWN], 120)
        self.assertTrue(rows[0].startswith('! Operation 651a8ce8f: outcome unknown.'), rows)
        lines = state_lines({'operation': {'operation_id': OPERATION, 'journal_status': 'outcome_unknown'}}, 120,
                            prefixes=self.PREFIXES)
        self.assertIn('651a8ce8f outcome unknown', ' '.join(' '.join(lines).split()))

    def test_the_actions_heading_names_the_policy_by_its_unique_prefix(self):
        from intune_iac.workbench_screens import actions_lines
        lines = actions_lines([], 0, 120, 'Windows Privacy Pilot', POLICY, prefixes=self.PREFIXES)
        self.assertIn('(22222222-2)', lines[0])

    def test_a_prefix_that_is_not_the_identity_s_own_is_never_shown(self):
        from intune_iac.workbench_screens import short_id
        self.assertEqual(short_id(POLICY, {POLICY: 'ffffffff-f'}), '22222222')
        self.assertEqual(short_id(POLICY, {POLICY: '2222'}), '22222222')  # never shorter than eight
        self.assertEqual(short_id(POLICY), '22222222')

    def test_unique_prefixes_extend_only_where_identities_share_a_head(self):
        from intune_iac.io import unique_prefixes
        twin = POLICY[:9] + '3333-4333-8333-333333333333'
        self.assertEqual(unique_prefixes([POLICY, twin, TENANT]),
                         {POLICY: '22222222-2', twin: '22222222-3', TENANT: '11111111'})
        self.assertEqual(unique_prefixes(['abcdefgh'], others=['abcdefghij']), {'abcdefgh': 'abcdefgh'})


class ReviewFixTests(unittest.TestCase):
    """Journey 27 run 2's reviews (logs/journey-27/FRAME-REVIEW-run2.md, Sonnet 1, 9, 10, 11, 18, 19, 20; Gemini 1, 2, 5,
    7 to 10): no route the screen cannot take, the command bar keeps its verb, every row fits."""

    def test_below_the_minimum_the_band_names_the_response_without_a_key(self):
        from intune_iac.workbench_screens import constrained_rows
        for width, height in ((39, 12), (40, 11), (36, 10)):
            lines, band = constrained_rows(TENANT, POLICY, {'signals': [UNKNOWN]}, 'synthetic', width, height, '40x12',
                                           'Viewing Inspector.')
            text = ' '.join(lines[index] for index in band)
            self.assertIn('Reconcile', text, (width, height))
            self.assertNotIn('(a actions)', text)
            self.assertNotIn('a: actions', text)

    def test_while_a_command_is_typed_the_band_offers_no_key(self):
        workspace, rows = FrameTests.staged_frame(self, (120, 40), signals=[CHANGED])
        # Band rows are drawn bold; the words are what the test reads.
        plain = [row.replace('\x1b[1m', '').replace('\x1b[22m', '').rstrip() for row in rows]
        band = [row for row in plain if row.startswith('! ')]
        self.assertEqual(band, ['! Repository changed since its intent. Next: Refresh the repository intent'])

    def test_below_the_minimum_a_view_notice_says_the_surface_is_hidden(self):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        out = io.StringIO()
        workspace.__dict__.update(stdout=out, mode=None, buffer='', cursor=0, notice='Viewing Inspector.', rules='unicode',
                                  color=False, theme='dark', selected=POLICY, mode_class='synthetic',
                                  facts={'object_id': POLICY, 'signals': [UNKNOWN]}, store=type('S', (), {'tenant_id': TENANT})())
        workspace._terminal_size = lambda: (39, 12)
        workspace.draw()
        self.assertIn('Inspector hidden; enlarge to see it', out.getvalue())
        self.assertNotIn('Viewing Inspector', out.getvalue())

    def test_the_command_bar_keeps_the_verb_and_marks_what_it_cuts(self):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        path = "/work/journey 27 Z\u00fcrich's \"pilot\"/operation-22222222-6d64398f5dcb"
        workspace.__dict__.update(mode='command', buffer="reconcile '%s'" % path, notice='')
        workspace.cursor = len(workspace.buffer)
        line = workspace._prompt_line(40, '\u2026')
        self.assertTrue(line.startswith(':reconcile \u2026'), line)
        self.assertTrue(line.endswith("'|"), line)
        self.assertLessEqual(cell_width(line), 40)
        workspace.buffer, workspace.cursor = 'repository-refresh  ' + 'c' * 64, len('repository-refresh ')
        line = workspace._prompt_line(60, '\u2026')
        self.assertTrue(line.startswith(':repository-refresh |'), line)
        self.assertTrue(line.endswith('\u2026'), line)
        self.assertLessEqual(cell_width(line), 60)
        workspace.buffer, workspace.cursor = 'help', 4
        self.assertEqual(workspace._prompt_line(60, '\u2026'), ':help|')

    def test_the_key_line_keeps_a_actions_down_to_48_columns(self):
        from intune_iac.workbench_tui import help_line
        for width in (120, 80, 60, 48):
            line = help_line(width)
            self.assertIn('a actions', line, width)
            self.assertLessEqual(cell_width(line), width)
        self.assertIn('q exit', help_line(40))

    def test_the_count_says_where_the_other_findings_are(self):
        from intune_iac.workbench_screens import hazard_rows
        self.assertIn('+1 more finding in NEEDS ATTENTION', ' '.join(hazard_rows({}, [UNKNOWN, STALE], 120, here=True)))  # run 8 item 13: where, not "below"
        # Run 8 item 15 kept the longest form of the hazard, so the count changed its wording with the width ("+1 more: 2"
        # at 120, "+1 more: 2 Inspector" at 140). Run 9 (frames 54 and 56): one form per fact, at every width.
        self.assertIn('+1 more finding (2 Inspector)', ' '.join(hazard_rows({}, [UNKNOWN, STALE], 120)))
        self.assertIn('+1 more finding (2 Inspector)', ' '.join(hazard_rows({}, [UNKNOWN, STALE], 140)))
        narrow = hazard_rows({}, [UNKNOWN, STALE], 48)
        self.assertTrue(any('+1 more' in row for row in narrow), narrow)
        self.assertTrue(all(cell_width(row) <= 48 for row in narrow), narrow)

    def test_the_40_column_boundaries_say_what_the_action_does(self):
        from intune_iac.workbench_tui import STAGED_BOUNDARY
        self.assertEqual(STAGED_BOUNDARY['repository-refresh'][-1], 'New intent only; no commit/approve/apply')
        self.assertEqual(STAGED_BOUNDARY['propose-from-intent'][-1], 'Local proposal; nothing approved or sent')
        for forms in STAGED_BOUNDARY.values():
            self.assertLessEqual(cell_width(forms[-1]), 40, forms[-1])

    def test_a_heading_wider_than_the_frame_wraps_and_no_body_row_is_clipped(self):
        from intune_iac.workbench_screens import state_lines
        lines = state_lines({}, 38, 'STATE (from the last read of this policy)')
        self.assertTrue(all(cell_width(line) <= 38 for line in lines), lines)
        self.assertIn('policy)', ' '.join(lines))
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        out = io.StringIO()
        workspace.__dict__.update(
            stdout=out, tab=1, value={'object_id': POLICY, 'evidence_class': 'synthetic'}, scroll=0, mode=None, notice='',
            rules='unicode', color=False, theme='dark', selected=POLICY, layer='summary', submission_key='enter',
            facts={'object_id': POLICY, 'signals': []}, staged=None, store=type('S', (), {'tenant_id': TENANT})(),
            mode_class='synthetic', last_command='inspect')
        workspace._terminal_size = lambda: (60, 30)
        workspace._data_lines = lambda width: ['alpha ' * 30]
        workspace.draw()
        rows = out.getvalue().replace('\x1b[H', '').replace('\x1b[J', '').split('\r\n')
        self.assertEqual(sum(row.count('alpha') for row in rows), 30)


class PaddingTests(unittest.TestCase):
    """Text inside the frame keeps one column of space from each border, at every size (journey 27 review, Sonnet 23)."""

    def frame(self, size):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        out = io.StringIO()
        workspace.__dict__.update(
            stdout=out, tab=1, value={'object_id': POLICY, 'evidence_class': 'synthetic'}, scroll=0, mode=None, notice='',
            rules='unicode', color=False, theme='dark', selected=POLICY, layer='summary', submission_key='enter',
            facts={'object_id': POLICY, 'signals': []}, staged=None, store=type('S', (), {'tenant_id': TENANT})(),
            mode_class='synthetic', last_command='inspect')
        workspace._terminal_size = lambda: size
        workspace._data_lines = lambda width: [('word ' * 60).strip(), 'x' * width]
        workspace.draw()
        return [row for row in out.getvalue().replace('\x1b[H', '').replace('\x1b[J', '').split('\r\n')]

    def test_text_keeps_a_column_from_each_border(self):
        for size in ((120, 40), (80, 24), (40, 12)):
            inside = [row.replace('\x1b[1m', '').replace('\x1b[22m', '') for row in self.frame(size) if row.startswith('│')]
            self.assertTrue(inside, size)
            for row in inside:
                self.assertEqual(cell_width(row), size[0], (size, row))
                self.assertEqual(row[1], ' ', (size, row))
                self.assertEqual(row[-2], ' ', (size, row))
