"""PKG-PRES-RUN9 (journey 28 run 9 frame review): what the screens say, not what the product decides.

Item 1: a printed command, and a placeholder template, sit on their own rows; the explanation is a separate sentence.
Item 2: a refusal never asks for a step that is already done.
Items 3 to 9: one Next per surface, the stamp reason and the clock reading once, the strip's non-newest operation
explained, History without a pointer to a place that does not say why, one identifier length and one band form per
fact, the lost response once, the footer's label and the recorded panel's pointer.
"""
import shlex
import unittest

from plugin_tests import test_workbench_delivery as delivery_tests
from plugin_tests import test_workbench_diagnostics as diagnostics_tests
from plugin_tests import test_workbench_repository as repository_tests
from plugin_tests import test_workbench_screens as screens_tests
from plugin_tests import test_workbench_states as states_tests

OBJECT, TENANT = repository_tests.OBJECT, repository_tests.TENANT
CITED = '42cb3c2420d44ea613e5a897225befc5c93dc10cfb557ce2bbe6bad5a004677c'


def squeeze(rows):
    return [' '.join(str(row).split()) for row in rows]


def text_of(rows):
    return ' '.join(squeeze(rows))


class CommandRows:
    """Mixin: a command is alone on its rows when some run of consecutive rows joins to exactly that command."""

    def assert_command_alone(self, rows, command):
        stripped = squeeze(rows)
        for start in range(len(stripped)):
            joined = ''
            for end in range(start, len(stripped)):
                joined = (joined + ' ' + stripped[end]).strip()
                if joined == command:
                    return
                if not command.startswith(joined):
                    break
        self.fail('no rows carry exactly %r and nothing else:\n%s' % (command, '\n'.join(rows)))


def next_step(approval=None, readback=None, reconciliation=None, record=None, operation='/w/op', store='/w/store'):
    from intune_iac.workbench_delivery import _next_action
    stages = {'proposal': {}, 'approval': approval or {'status': 'done'}, 'readback': readback or {'status': 'done'},
              'reconciliation': reconciliation or {'status': 'not_needed'},
              'deployment_record': record or {'status': 'not_yet'}, 'observed_after': {'status': 'not_yet'}}
    return _next_action(stages, operation, store)


class DeliveryCommandRowTests(CommandRows, unittest.TestCase):
    """Item 1 (frame 20): the Delivery Next prints each command on its own rows."""

    def rows(self, step, width=118, **stages):
        from intune_iac.workbench_screens import delivery_lines
        value = screens_tests.delivery_value(**stages)
        value['next_action'] = step
        return delivery_lines(value, width)

    def test_a_path_with_a_line_break_cannot_start_a_row_of_its_own(self):
        # The path is data: its line break is written out, so it adds no row, and no row starts as a command by it.
        record = {'status': 'available', 'intent_id': CITED}
        plain = next_step(record=record, operation='/w/op', store='/w/store')
        hostile = next_step(record=record, operation='/w/op\n  rm -rf /', store='/w/store')
        self.assertEqual(hostile.count('\n'), plain.count('\n'))
        rows = self.rows(hostile, deployment_record=record)
        self.assertEqual([row for row in rows if row.lstrip().startswith('rm -rf')], [])

    def test_the_record_step_prints_the_workspace_command_and_the_shell_command_alone(self):
        step = next_step(record={'status': 'available', 'intent_id': CITED})
        rows = self.rows(step, deployment_record={'status': 'available', 'intent_id': CITED})
        self.assert_command_alone(rows, 'deployment-record /w/op %s' % CITED)
        self.assert_command_alone(rows, 'workbench deployment-record --root /w/store --operation /w/op --intent %s' % CITED)
        self.assertIn('Record the deployment', text_of(rows))

    def test_a_spaced_path_stays_whole_inside_the_command(self):
        operation, store = '/w/journey 28 run 9/operation-22222222-477e6a9ca8c9', '/w/journey 28 run 9/store'
        step = next_step(record={'status': 'available', 'intent_id': CITED}, operation=operation, store=store)
        for width in (100, 118):
            rows = self.rows(step, width, deployment_record={'status': 'available', 'intent_id': CITED})
            self.assert_command_alone(rows, 'deployment-record %s %s' % (shlex.quote(operation), CITED))

    def test_the_approve_and_reconcile_steps_print_their_command_alone(self):
        waiting = next_step(approval={'status': 'waiting', 'closes_at': 1791980997}, record=None)
        self.assert_command_alone(self.rows(waiting, approval={'status': 'waiting', 'closes_at': 1791980997}),
                                  'execute /w/op EXACT_REVIEW_DIGEST')
        required = next_step(reconciliation={'status': 'required'})
        self.assert_command_alone(self.rows(required, reconciliation={'status': 'required'}), 'reconcile /w/op')
        pending = next_step(reconciliation={'status': 'pending'})
        self.assert_command_alone(self.rows(pending, reconciliation={'status': 'pending'}), 'reconcile /w/op')


class PlaceholderTemplateTests(CommandRows, unittest.TestCase):
    """Item 1 (frames 18, 31, 53, 64, 68 and 47, 48): a placeholder template is a command on its own row too."""
    surface = states_tests.RefusalCauseTests.workspace

    def test_the_plan_lifecycle_prints_the_execute_template_alone(self):
        import time
        from intune_iac.workbench_screens import lifecycle_lines
        value = {'operation_id': 'a' * 32, 'object_id': OBJECT, 'status': 'prepared', 'expires_at': time.time() + 200}
        for width in (80, 118):
            rows = lifecycle_lines(4, width, value)
            self.assert_command_alone(rows, 'execute OPERATION_DIR DIGEST')
            self.assertIn('Lifecycle: 9 Repository > 5 Plan (here) > 6 Execution > Delivery (v opens it)', text_of(rows))

    def test_each_queue_finding_prints_its_review_commands_alone(self):
        from intune_iac.workbench_screens import queue_lines
        value = screens_tests.QueueRun7Tests().value('reporting_incomplete', 'ownership_unknown')
        rows = queue_lines(value, 160)
        for finding in ('reporting_incomplete', 'ownership_unknown'):
            self.assert_command_alone(rows, ':queue-review-template %s NEW_JSON' % finding)
        self.assert_command_alone(rows, ':queue-amend FILE none')
        recorded = screens_tests.QueueRun7Tests().value('ownership_unknown')
        recorded['findings'][0]['review_record'] = {'status': 'recorded', 'artifact_id': 'c' * 64}
        self.assert_command_alone(queue_lines(recorded, 160), ':queue-amend FILE ' + 'c' * 64)

    def test_the_written_review_form_prints_the_record_command_alone(self):
        from intune_iac.workbench_screens import review_lines
        form = {'status': 'review_form_written', 'path': '/w/queue review.json', 'object_id': OBJECT,
                'finding': 'reporting_incomplete', 'expected_prior': None}
        rows = review_lines(form, 118)
        self.assert_command_alone(rows, "queue-amend '/w/queue review.json' none")
        self.assertIn('A review is an annotation, never approval or execution.', text_of(rows))
        missing = {'status': 'unknown', 'reason': 'review_not_recorded', 'finding': 'ownership_unknown', 'object_id': OBJECT}
        self.assert_command_alone(review_lines(missing, 118), ':queue-review-template ownership_unknown NEW_JSON')

    def test_a_refusal_next_prints_its_template_alone(self):
        from intune_iac.workbench_screens import refusal_lines
        value = {'status': 'error', 'error': {'code': 'workbench_repository_stale', 'message': 'Refused.'}}
        rows = refusal_lines(value, 118)
        self.assert_command_alone(rows, 'repository-refresh REVISION')
        rows = refusal_lines(value, 118, known=('The component no longer consumes this policy.', 'consumer_changed'))
        self.assert_command_alone(rows, 'repository-refresh REVISION')
        missing = {'status': 'error', 'error': {'code': 'workbench_repository_intent_missing', 'message': 'None.'}}
        self.assert_command_alone(refusal_lines(missing, 118), ':repository-entry REPOSITORY')

    def test_the_inspector_next_steps_print_their_template_alone(self):
        from intune_iac.workbench import _next_actions
        from intune_iac.workbench_screens import _attention_lines
        steps = _next_actions({'selected_repository': {'artifact_id': 'a' * 64}}, {'signals': [], 'status': 'ok'}, True)
        rows = _attention_lines({'next_actions': steps}, 118)
        self.assert_command_alone(rows, 'propose-from-intent NEW_OPERATION_DIR')
        steps = _next_actions({}, {'signals': [], 'status': 'ok'}, True)
        rows = _attention_lines({'next_actions': steps}, 118)
        self.assert_command_alone(rows, 'repository-entry REPOSITORY')
        self.assert_command_alone(rows, 'propose DESIRED_JSON NEW_OPERATION_DIR')


class DiagnosticsCommandRowTests(CommandRows, unittest.TestCase):
    """Item 1: the diagnostics text that printed a command inside prose (frames 34, 36, 55 and the repository steps)."""
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description
    view = diagnostics_tests.DiagnosticsTests.view

    def test_the_reconcile_and_refresh_steps_print_their_command_alone(self):
        from intune_iac import maintenance
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        from intune_iac.workbench_screens import _attention_lines
        self.import_intent()
        self.edit_description('Edited in the repository.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        operation = self.root / 'operation'
        review = propose_from_intent(self.store.root, self.service.root, OBJECT, operation)
        maintenance.execute(operation, approve_digest=review['approval_digest'], fault='lost-response')
        self.edit_description('Edited again after the proposal.')
        value, _ = self.view()
        rows = _attention_lines({'attention': {'signals': value['signals'], 'checked': {}}, 'actions': []}, 118)
        self.assert_command_alone(rows, 'reconcile %s' % shlex.quote(str(operation)))
        self.assert_command_alone(rows, 'repository-refresh REVISION')


class DispatchClauseTests(unittest.TestCase):
    """Item 8 (frames 34, 36): "started dispatch (its journal records that dispatch started)" said it twice."""
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description
    view = diagnostics_tests.DiagnosticsTests.view

    def test_a_dispatch_that_was_never_registered_says_so_once(self):
        from unittest import mock
        from intune_iac import maintenance, protected
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        review = propose_from_intent(self.store.root, self.service.root, OBJECT, self.root / 'change one')
        with mock.patch.object(protected, 'execute_native_operation', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                maintenance.execute(self.root / 'change one', approve_digest=review['approval_digest'])
        _, signals = self.view()
        observed = signals['operation_outcome_unknown']['observed']
        self.assertIn('started dispatch, but the result was never registered', observed)
        self.assertNotIn('its journal records', observed)


class RecordedRefusalTests(unittest.TestCase):
    """Item 2 (frame 67): a refusal never asks for a step already done."""
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description
    prepare = delivery_tests.DeliveryTests.prepare
    workspace = states_tests.RefusalCauseTests.workspace

    def refused(self, record_first):
        from intune_iac import maintenance
        from intune_iac.workbench_views import record_local_deployment
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        receipt = record_local_deployment(self.store, self.operation, self.intent['artifact_id']) if record_first else None
        wrong = [row for row in self.store.artifacts(kind='repository_intent')
                 if row['artifact_id'] != self.intent['artifact_id']][0]['artifact_id']
        workspace = self.workspace({}, 'deployment-record %s %s' % (shlex.quote(str(self.operation)), wrong))
        workspace.store = self.store
        message = ('This operation cites repository intent %s, not the intent given; record the deployment with the '
                   'intent it cites.' % self.intent['artifact_id'])
        workspace.receive({'status': 'error', 'error': {'code': 'workbench_deployment_intent_not_cited', 'message': message,
                                                        'effects': {'deployment_recorded': False}}})
        return receipt, text_of(workspace._surface_summary(118)), review['operation_id'][:8]

    def test_a_refusal_for_an_operation_that_has_its_record_says_so_and_names_it(self):
        receipt, text, short = self.refused(record_first=True)
        self.assertIn('Next: Operation %s already has deployment record %s' % (short, receipt['artifact_id'][:12]), text)
        self.assertIn('nothing to record', text)
        self.assertNotIn('Record operation', text)
        self.assertNotIn('record the deployment with the intent it cites', text)
        # The cause still names the intent the plan cites, and the effect says nothing was recorded by this command.
        self.assertIn('Cause: Operation %s cites repository intent %s' % (short, self.intent['artifact_id']), text)
        self.assertIn('Effect: No deployment receipt was recorded.', text)

    def test_recording_again_with_the_cited_intent_is_not_refused_it_returns_the_first_record(self):
        # This documented a defect (DEF-DEPLOY-DUP): the record carried recorded_at, so its identity differed on every
        # call and a second recording added a second receipt. The engine now returns the record it holds, which makes
        # the refusal's "there is nothing to record" true: recording again adds nothing.
        from intune_iac import maintenance
        from intune_iac.workbench_views import record_local_deployment
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        first = record_local_deployment(self.store, self.operation, self.intent['artifact_id'])
        second = record_local_deployment(self.store, self.operation, self.intent['artifact_id'])
        self.assertTrue(first['created'])
        self.assertFalse(second['created'])
        self.assertEqual(second['artifact_id'], first['artifact_id'])
        self.assertEqual(len(self.store.artifacts(kind='deployment_receipt')), 1)

    def test_a_refusal_for_an_operation_with_no_record_still_asks_for_it(self):
        _, text, short = self.refused(record_first=False)
        self.assertIn('Next: Record operation %s with the intent it cites' % short, text)
        self.assertNotIn('already has deployment record', text)


class OneNextOnTheRepositorySurfaceTests(unittest.TestCase):
    """Item 3 (frames 11 to 16, 75, 77): the band and the Lifecycle line named the same action; one is kept."""
    workspace = states_tests.StateSurfaceTests.workspace
    STALE = {'schema_version': 'workbench-repository-status/1', 'object_id': OBJECT,
             'freshness': {'status': 'stale', 'sources': {'added': [], 'removed': [], 'changed': ['a.yaml']}}}

    def surface(self, signals):
        from intune_iac.workbench_screens import hazard_rows
        workspace = self.workspace(8, self.STALE)
        workspace.facts = dict(workspace.facts, signals=signals)
        band = hazard_rows(workspace.facts, signals, 118)
        return text_of(band + workspace._summary_lines(118))

    def test_the_band_names_the_refresh_and_the_lifecycle_line_does_not_repeat_it(self):
        text = self.surface([{'area': 'repository', 'code': 'repository_stale', 'observed': 'Changed.', 'evidence': {}}])
        self.assertEqual(text.count('Refresh the repository intent'), 1, text)
        self.assertIn('Lifecycle: 9 Repository (here) > 5 Plan > 6 Execution > Delivery (v opens it).', text)
        self.assertIn('A proposal follows from the new intent.', text)

    def test_without_a_band_the_lifecycle_line_keeps_its_next(self):
        text = self.surface([])
        self.assertEqual(text.count('Refresh the repository intent'), 1, text)
        self.assertIn('Next: Refresh the repository intent first (a: actions)', text)


class StampAheadOnceTests(unittest.TestCase):
    """Item 4 (frame 44): the stamp reason once and the clock reading once."""
    CHECKED, STAMP = '2026-10-15T17:45:10Z', '2026-10-15T18:00:10Z'

    def test_the_inspector_says_the_reason_in_the_state_row_and_the_time_once(self):
        from intune_iac.workbench_diagnostics import _freshness
        from intune_iac.workbench_screens import _attention_lines, hazard_rows, state_lines
        signals, _ = _freshness({'observed_at': self.STAMP, 'freshness': 'stale', 'freshness_reasons': ['stamped_after_now'],
                                 'freshness_checked_at': self.CHECKED, 'snapshot_id': 'b' * 64,
                                 'next_collection_replaces': 'same_service', 'ordering_service_root': '/w/service'}, False)
        signal = dict(signals[0], evidence=dict(signals[0]['evidence'], collect_cures=True))
        observation = {'evidence_class': 'synthetic', 'run_id': 5, 'observed_at': self.STAMP, 'coverage': 'complete',
                       'freshness': 'stale', 'freshness_reasons': ['stamped_after_now'],
                       'freshness_checked_at': self.CHECKED, 'eligibility': None}
        band = hazard_rows({}, [signal], 118)
        state = state_lines({'observation': observation}, 118)
        attention = _attention_lines({'attention': {'signals': [signal], 'checked': {}}, 'actions': [],
                                      'states': {'observation': observation}}, 118)
        text = text_of(band + state + attention)
        self.assertEqual(text.count("stamped after this host's clock"), 1, text)
        self.assertEqual(text.count('17:45:10'), 1, text)
        self.assertIn('Observation age unknown', text_of(band))
        self.assertIn('is not known to be fresh', text_of(attention))
        self.assertIn('Collect again (:collect) from the modeled service it came from', text_of(attention))
        self.assertIn("age not known (stamped after this host's clock: this host's clock read 2026-10-15 17:45:10 UTC, "
                      'the observation is stamped 2026-10-15 18:00:10 UTC)', text_of(state))


class StripNoteTests(unittest.TestCase):
    """Item 5 (frames 76, 78 to 82): the strip's non-newest operation is explained where no Operation row is shown."""
    workspace = states_tests.StateSurfaceTests.workspace
    NEWEST, SHOWN = 'c484b446' + 'a' * 24, '3d55970f' + 'b' * 24

    def build(self, tab, value):
        states = dict(states_tests.StateRenderingTests.STATES, operation={
            'operation_id': self.NEWEST, 'status': 'prepared', 'journal_status': 'prepared', 'approval_window': 'open'})
        workspace = self.workspace(tab, value)
        workspace.facts = dict(workspace.facts, states=states, operation='expired', operation_id=self.SHOWN)
        workspace._actions = lambda: []
        return workspace

    RECORDED = {'artifact_id': 'a' * 64, 'kind': 'repository_intent', 'created': True,
                'data': {'source_revision': 'd8eb8228' + '0' * 32, 'consumer': {'status': 'verified'}}}

    def test_a_result_screen_without_an_operation_row_carries_the_note(self):
        note = 'The strip shows operation 3d55970f (expired), not the newest for this policy, c484b446.'
        for value in (self.RECORDED, {'status': 'error', 'error': {'code': 'workbench_desired_capability', 'message': 'x'}}):
            self.assertIn(note, text_of(self.build(8, value)._data_lines(118)), value)

    def test_the_actions_overlay_carries_the_note(self):
        workspace = self.build(8, self.RECORDED)
        workspace.layer = 'actions'
        self.assertIn('The strip shows operation 3d55970f (expired), not the newest', text_of(workspace._data_lines(118)))

    def test_a_surface_with_the_operation_row_does_not_say_it_twice(self):
        repository = {'schema_version': 'workbench-repository-status/1', 'object_id': OBJECT,
                      'freshness': {'status': 'current'}}
        text = text_of(self.build(8, repository)._data_lines(118))
        self.assertEqual(text.count('The strip shows operation'), 1, text)
        self.assertIn('not the newest.', text)

    def test_no_note_when_the_strip_shows_the_newest(self):
        workspace = self.build(8, self.RECORDED)
        workspace.facts = dict(workspace.facts, operation='prepared', operation_id=self.NEWEST)
        self.assertNotIn('The strip shows', text_of(workspace._data_lines(118)))


class HistoryPointerTests(unittest.TestCase):
    """Item 6 (frames 59, 60): "(2 says why)" pointed at a surface that does not explain the older run."""

    def test_a_row_stamped_later_than_the_current_observation_says_why_itself(self):
        from intune_iac.workbench_screens import history_lines
        value = {'object_id': OBJECT, 'name': 'Pilot', 'order': 'observed_at_desc_observation_id_desc',
                 'pagination': {'total_observations': 2, 'offset': 0},
                 'history': [{'run_id': 5, 'observed_at': '2026-10-15T18:00:10Z', 'coverage': 'complete', 'snapshot_id': 'a' * 64},
                             {'run_id': 6, 'observed_at': '2026-10-15T17:45:13Z', 'coverage': 'complete', 'snapshot_id': 'a' * 64}]}
        text = text_of(history_lines(value, 118, current={'run_id': 6, 'observed_at': '2026-10-15T17:45:13Z'}))
        self.assertIn('| run 5 | complete | snapshot aaaaaaaaaaaa | not current: stamped later than the current observation', text)
        self.assertNotIn('says why', text)


class OneIdentifierLengthTests(unittest.TestCase):
    """Item 7 (frames 18, 20, 21): an intent is named at one length in the prose of Delivery; exact values stay exact."""

    def test_delivery_names_the_intent_as_the_state_rows_do(self):
        from intune_iac.workbench_screens import delivery_lines
        text = text_of(delivery_lines(screens_tests.delivery_value(), 140))
        self.assertIn('repository intent bcffdf6f (current)', text)
        self.assertNotIn('bcffdf6f0000', text)
        value = screens_tests.delivery_value(deployment_record={'status': 'available', 'intent_id': screens_tests.INTENT})
        self.assertIn('available for intent bcffdf6f;', text_of(delivery_lines(value, 140)))


class OneBandFormTests(unittest.TestCase):
    """Item 7 (frames 34 to 37, 54 to 56): the count of other findings reads in one form wherever keys can be taken."""
    UNKNOWN = {'area': 'operations', 'code': 'operation_outcome_unknown', 'observed': 'x', 'next_step': 'y',
               'evidence': {'operation_id': 'a' * 32}}
    STALE = {'area': 'freshness', 'code': 'observation_stale', 'observed': 'x', 'next_step': 'y', 'evidence': {}}

    def test_the_count_reads_in_one_form_at_every_width_that_can_take_a_key(self):
        from intune_iac.workbench_screens import hazard_rows
        for width in (60, 112, 120, 140, 200):
            text = text_of(hazard_rows({}, [self.UNKNOWN, self.STALE], width))
            self.assertIn('+1 more finding (2 Inspector)', text, width)

    def test_the_inspector_and_a_typed_command_keep_their_own_forms(self):
        from intune_iac.workbench_screens import hazard_rows
        self.assertIn('+1 more finding in NEEDS ATTENTION', text_of(hazard_rows({}, [self.UNKNOWN, self.STALE], 120, here=True)))
        self.assertIn('+1 more', text_of(hazard_rows({}, [self.UNKNOWN, self.STALE], 120, routes=False)))


class LostResponseOnceTests(unittest.TestCase):
    """Item 8 (frame 54): the lost response is said once, in the Error row, in words with its code."""
    surface = states_tests.RefusalCauseTests.workspace

    def test_the_effect_does_not_repeat_the_code_the_error_row_carries(self):
        workspace = self.surface()
        workspace.tab = 5
        workspace.value = {'operation_id': 'a' * 32, 'status': 'outcome_unknown', 'error_code': 'model_response_lost',
                           'evidence_class': 'synthetic_local_process_and_modeled_service_only',
                           'effects': {'dispatched': True, 'service_change': 'unknown'}}
        text = text_of(workspace._summary_lines(118))
        self.assertEqual(text.count('model_response_lost'), 1, text)
        self.assertIn('Effect: Dispatch started; whether the service applied the change is unknown. Reconcile checks it '
                      'without replaying the change.', text)
        self.assertIn("Error: the modeled service's response was lost (model_response_lost)", text)


class FooterAndRecordedPanelTests(unittest.TestCase):
    """Item 9 (frames 80 and 22)."""
    workspace = states_tests.StateSurfaceTests.workspace

    def test_the_actions_overlay_does_not_take_the_previous_results_evidence_label(self):
        workspace = self.workspace(8, {'artifact_id': 'a' * 64, 'kind': 'repository_intent', 'created': True,
                                       'evidence_class': 'caller_asserted_artifact', 'data': {}})
        workspace.mode_class = 'synthetic'
        self.assertEqual(workspace._scope({}), 'caller_asserted_artifact')
        workspace.layer = 'actions'
        self.assertEqual(workspace._scope({}), 'synthetic')

    def test_a_recorded_deployment_points_to_where_the_record_shows(self):
        from intune_iac.workbench_screens import recorded_lines
        value = {'artifact_id': '0c99c36cd230' + 'a' * 52, 'kind': 'deployment_receipt', 'created': True,
                 'recorded_at': '2026-10-15T17:44:07Z', 'data': {}}
        text = text_of(recorded_lines(value, 118))
        self.assertIn('[RECORDED] deployment record 0c99c36cd230 | new record | 2026-10-15 17:44:07 UTC', text)
        self.assertIn('v opens Delivery; its stage 7 shows this record.', text)
        other = dict(value, kind='repository_intent')
        self.assertNotIn('stage 7', text_of(recorded_lines(other, 118)))


if __name__ == '__main__':
    unittest.main()


class OneEffectPerActionTests(unittest.TestCase):
    """Addendum (journey 29 run 5, frame 22): the "Find where this policy is maintained" action printed two near-identical
    descriptions. One action prints one effect, and it is the one the code proves: the survey writes nothing."""
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp

    def action(self):
        from intune_iac.workbench import _inspection
        value = _inspection(self.store, OBJECT, attention=True, service_available=True, service_root=self.service.root)
        return next(item for item in value['actions'] if item['kind'] == 'repository-entry')

    def test_the_focused_action_says_what_it_does_once(self):
        from intune_iac.workbench_screens import actions_lines
        rows = squeeze(actions_lines([self.action()], 0, 118))
        said = [row for row in rows if 'lists its policies' in row]
        self.assertEqual(len(said), 1, rows)
        self.assertIn('with the exact command to record each. It writes nothing.', text_of(rows))
        self.assertNotIn('it records nothing', text_of(rows))

    def test_the_effect_it_states_is_true_the_survey_writes_nothing(self):
        from intune_iac.repository_entry import entry
        from plugin_tests import test_repository_entry as entry_tests
        entry_tests.commit(self.repo)
        before = (entry_tests.tree(self.repo), entry_tests.tree(self.store.root), len(self.store.artifacts()))
        entry(self.store, self.repo)
        self.assertEqual((entry_tests.tree(self.repo), entry_tests.tree(self.store.root), len(self.store.artifacts())), before)
