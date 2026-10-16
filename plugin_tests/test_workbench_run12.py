"""PKG-PRES-RUN12 (journey 28 run 12 frame reviews): what the screens say, not what the product decides.

Items are added in the order of the brief; each class names its item. Temporary directories only.
"""
import unittest

from plugin_tests import test_workbench_diagnostics as diagnostics_tests
from plugin_tests import test_workbench_states as states_tests
from plugin_tests.test_workbench_map_truth import MapTruth
from plugin_tests.test_workbench_run10 import action
from plugin_tests.test_workbench_run11 import Proposed
from plugin_tests.test_workbench_screens import delivery_value


class OneNextOnDeliveryTests(unittest.TestCase):
    """Item 1 (frames 20, 39): when the hazard band carries the Next, the Delivery body keeps its explanation and
    prints no second `Next:` label (as the lifecycle line already does)."""
    workspace = states_tests.StateSurfaceTests.workspace
    BAND = states_tests.RunEightWorkspaceTests.BAND
    STEP = 'Record the deployment (a lists it). In the workspace:\n  deployment-record /w/op INTENT'

    def shown(self, signals):
        value = dict(delivery_value(), next_action=self.STEP)
        workspace = self.workspace(5, value)
        workspace.facts = dict(workspace.facts, signals=signals)
        return ' '.join(' '.join(workspace._summary_lines(118)).split())

    def test_with_a_band_next_the_body_has_no_next_label_but_keeps_its_explanation(self):
        text = self.shown([self.BAND])
        self.assertNotIn('Next:', text)
        self.assertIn('Record the deployment (a lists it). In the workspace: deployment-record /w/op INTENT', text)

    def test_without_a_band_the_body_keeps_its_next_label(self):
        self.assertIn('Next: Record the deployment (a lists it).', self.shown([]))


class StripSentenceTests(unittest.TestCase):
    """Item 2 (frame 67): the body sentence describes what the strip shows. The strip names no operation id when its
    operation is the newest (it prints `OP prepared`), so the sentence says that OP stands for that operation; the
    strip itself and its width rules (P-PRES-02) are unchanged."""
    from plugin_tests.test_workbench_run10 import StripOperationTests as _base
    refusal = _base.refusal
    surface = _base.surface
    STRIP, ABOUT = _base.STRIP, _base.ABOUT

    def test_the_sentence_says_what_the_strip_prints_not_an_id_it_does_not_show(self):
        from intune_iac.workbench_screens import strip_choice
        workspace = self.refusal()
        strip = strip_choice('11111111' * 4, 'p' * 32, {'operation': 'prepared'}, 140)[0]
        self.assertTrue(strip.endswith('OP prepared'), strip)
        text = ' '.join(' '.join(workspace._strip_note(118)).split())
        self.assertEqual(text, "The strip's OP prepared is operation a23983bd, the newest for this policy, not operation "
                               "f728f275, the one this screen is about.")


class WhereToTypeTests(unittest.TestCase):
    """Item 3 (frames 18, 31, 53, 63, 64; also 02 and 48): a printed command says where it is typed. The plan review's
    execute gets the framing frame 20 uses, with the complete shell form; DIGEST stays a placeholder, never prefilled."""
    OPERATION = '/w/op'

    def review(self, **kw):
        import time
        value = {'operation_id': 'f' * 32, 'operation_root': self.OPERATION, 'object_id': 'o' * 8, 'status': 'prepared',
                 'approval_digest': 'd' * 64, 'expires_at': time.time() + 200}
        return dict(value, **kw)

    def rows(self, value, width=118):
        from intune_iac.workbench_screens import lifecycle_lines
        return lifecycle_lines(4, width, value)

    def test_the_plan_review_frames_both_forms_and_keeps_the_placeholder(self):
        for width in (80, 118):
            text = '\n'.join(row.strip() for row in self.rows(self.review(), width))
            self.assertIn('In the workspace:\nexecute /w/op DIGEST\nFrom a shell:\nintune-iac workbench execute --operation '
                          '/w/op --approve-digest DIGEST', text, width)
            self.assertNotIn('Command:', text)
            self.assertNotIn('d' * 64, text)

    def test_a_no_change_plan_and_a_review_without_a_directory_say_it_too(self):
        no_change = ' '.join(' '.join(self.rows(self.review(changes=[], no_configuration_change=True))).split())
        self.assertIn('In the workspace: execute /w/op DIGEST From a shell: intune-iac workbench execute --operation /w/op '
                      '--approve-digest DIGEST', no_change)
        value = self.review()
        del value['operation_root']
        bare = ' '.join(' '.join(self.rows(value)).split())
        self.assertIn('In the workspace: execute OPERATION_DIR DIGEST From a shell: intune-iac workbench execute '
                      '--operation OPERATION_DIR --approve-digest DIGEST', bare)

    def test_a_path_with_spaces_is_quoted_in_both_forms(self):
        text = ' '.join(' '.join(self.rows(self.review(operation_root='/w/my op'))).split())
        self.assertIn("execute '/w/my op' DIGEST", text)
        self.assertIn("--operation '/w/my op' --approve-digest DIGEST", text)

    def test_the_queue_amend_command_says_it_is_typed_in_the_workspace(self):
        from intune_iac.workbench_screens import review_lines
        form = {'status': 'review_form_written', 'path': '/w/queue review.json', 'finding': 'incomplete', 'object_id': 'o' * 8}
        text = '\n'.join(row.strip() for row in review_lines(form, 118))
        self.assertNotIn('Command:', text)
        self.assertIn("In the workspace:\nqueue-amend '/w/queue review.json' none", text)

    def test_the_adopt_command_says_it_is_typed_in_the_workspace(self):
        from intune_iac.workbench_screens import adoption_lines
        value = {'status': 'ready_local_model_handoff', 'binding': {'session': '/w/session.json', 'object_ids': ['o' * 8]}}
        text = '\n'.join(row.strip() for row in adoption_lines(value, 118))
        self.assertIn("In the workspace:\nadopt '/w/session.json' NEW_HANDOFF_DIR", text)


class ChangedFileBridgeTests(unittest.TestCase):
    """Item 4 (frames 75, 77): REPOSITORY CHANGED sits beside NO CONFIGURATION CHANGE; one clause says the listed files
    do not alter this policy's body at the intent pointer (the verdict compares that body, workbench_repository.intent_freshness)."""
    BRIDGE = ("The listed files differ from the recorded ones, but they do not alter this policy's body at the intent "
              "pointer.")

    def rows(self, field_changes, sources=None, pointer_present=True):
        from intune_iac.workbench_screens import repository_lines
        status = {'schema_version': 'workbench-repository-status/1', 'scope': {'stack': 's', 'component': 'c'},
                  'freshness': {'status': 'stale', 'pointer_present': pointer_present, 'field_changes': field_changes,
                                'sources': sources or {'changed': ['stacks/dev.yaml'], 'added': ['stacks/new.yaml']}}}
        return repository_lines(status, 118)

    def text(self, *args, **kw):
        return ' '.join(' '.join(self.rows(*args, **kw)).split())

    def test_a_no_change_verdict_beside_listed_files_carries_the_bridge_once(self):
        text = self.text({'status': 'no_change', 'changes': []})
        self.assertEqual(text.count(self.BRIDGE), 1, text)
        self.assertLess(text.index('RECORDED INTENT AGAINST THE REPOSITORY NOW'), text.index(self.BRIDGE))
        self.assertLess(text.index(self.BRIDGE), text.index('NO CONFIGURATION CHANGE'))

    def test_a_changed_body_or_no_listed_file_says_no_such_thing(self):
        changed = {'status': 'changed', 'changes': [{'field': 'description', 'kind': 'changed', 'before': 'a', 'after': 'b'}]}
        self.assertNotIn(self.BRIDGE, self.text(changed))
        self.assertNotIn(self.BRIDGE, self.text({'status': 'no_change', 'changes': []},
                                                sources={'changed': [], 'added': [], 'removed': []}))

    def test_one_listed_file_reads_in_the_singular(self):
        text = self.text({'status': 'no_change', 'changes': []}, sources={'changed': ['stacks/dev.yaml']})
        self.assertIn("The listed file differs from the recorded one, but it does not alter this policy's body at the intent "
                      "pointer.", text)


class EqualityDefinedTests(unittest.TestCase):
    """Item 5: "the execution plan's equality" is defined where it is first used, as workbench_diff.field_changes
    compares: assignments, technologies and role scope tags as bags (order ignored, repeats counted), every other field
    exactly, including the order of settings."""
    CLAUSE = ('(assignments, technologies and role scope tags match in any order, each repeat counting; every other '
              'field, including the order of settings, must match exactly)')

    def test_the_plan_review_verdict_defines_it(self):
        from intune_iac.workbench_screens import change_lines
        text = ' '.join(' '.join(change_lines({'status': 'no_change', 'changes': []}, 118)).split())
        self.assertIn("under the execution plan's equality " + self.CLAUSE + '.', text)

    def test_the_repository_verdict_defines_it_before_it_says_the_observation_is_out(self):
        from intune_iac.workbench_screens import change_lines, REPOSITORY_SAME
        text = ' '.join(' '.join(change_lines({'status': 'no_change', 'changes': []}, 118, same=REPOSITORY_SAME)).split())
        self.assertIn("under the execution plan's equality " + self.CLAUSE + '. The observation is not part of this '
                      'comparison.', text)

    def test_the_clause_matches_what_the_comparison_does(self):
        from intune_iac.workbench_diff import BAGS, field_changes
        self.assertEqual(sorted(BAGS), ['assignments', 'role_scope_tag_ids', 'technologies'])
        body = {'name': 'n', 'description': 'd', 'platforms': 'windows10', 'technologies': ['a', 'b'], 'role_scope_tag_ids': ['0'],
                'settings': {'settings': [{'id': '0', 'settingInstance': {'settingDefinitionId': 'x'}},
                                          {'id': '1', 'settingInstance': {'settingDefinitionId': 'y'}}]},
                'assignments': ['p', 'q']}
        bag_order = dict(body, technologies=['b', 'a'], assignments=['q', 'p'])
        self.assertEqual(field_changes(body, bag_order)['status'], 'no_change')
        reordered = dict(body, settings={'settings': list(reversed(body['settings']['settings']))})
        self.assertEqual(field_changes(body, reordered)['status'], 'changed')


class LegendMeaningTests(unittest.TestCase):
    """Item 6: a legend row says what the abbreviation stands for and what it means for the next action, not the
    state's own words again (`unknown = outcome unknown`)."""
    EXPECTED = {
        'succeeded_verified': 'verified = executed and read back as desired; v shows the rest',
        'not checked': 'unchecked = the repository was not compared with the recorded intent',
        'outcome_unknown': 'unknown = the change may have reached the service; reconcile it (a)',
        'recorded_intent_not_revalidated': 'not revalidated = shown from the recorded intent; repository not re-read',
        'desired_state_observed': 'observed = a readback found the service already holds the desired state',
        'age unknown': "age? = the observation's age cannot be judged; collect again (a)",
        'stale (later collection incomplete)': 'stale = a later collection did not finish; collect again (a)'}

    def test_each_row_carries_its_meaning(self):
        from intune_iac.workbench_screens import STRIP_DEFINITIONS
        for key, row in self.EXPECTED.items():
            self.assertEqual(STRIP_DEFINITIONS[key], row, key)

    def test_no_row_restates_its_own_key(self):
        import re
        from intune_iac.workbench_screens import STRIP_DEFINITIONS
        for key, row in STRIP_DEFINITIONS.items():
            short, _, meaning = row.partition(' = ')
            self.assertNotEqual(meaning, key.replace('_', ' '), row)
            if key in ('T', 'P'):
                continue
            extra = set(re.findall(r'[a-z]+', meaning)) - set(re.findall(r'[a-z]+', key.replace('_', ' '))) - {'the', 'a'}
            self.assertGreaterEqual(len(extra), 3, row)

    def test_rows_stay_short_enough_for_an_80_column_screen(self):
        from intune_iac.workbench_screens import STRIP_DEFINITIONS
        for key, row in STRIP_DEFINITIONS.items():
            self.assertLessEqual(len(row), 80, row)


class ClosedPlanNextNamesTheOpenProposalTests(unittest.TestCase):
    """Item 7a (frame 70): a closed plan's Next names the newest operation, which is a different one and still open,
    instead of pointing at fields above."""
    surface = states_tests.RefusalCauseTests.workspace
    NEWEST = 'a23983bd3a224bd1b08d8156a67fa773'
    CLOSED = 'c6d62cc78f584390bb41448b52f9e936'

    def rows(self, window, newest_status='prepared', newest=None):
        newest = newest or self.NEWEST
        facts = {'states': {'operation': {'operation_id': newest, 'journal_status': newest_status,
                                          'status': newest_status, 'approval_window': window}}}
        workspace = self.surface(facts)
        workspace.tab = 4
        workspace.value = {'operation_id': self.CLOSED, 'object_id': states_tests.OBJECT, 'status': 'prepared',
                           'approval_window': {'state': 'closed'}, 'expires_at': 1}
        return ' '.join(' '.join(workspace._summary_lines(118)).split())

    def test_the_next_names_the_open_newest_operation(self):
        text = self.rows('open')
        self.assertIn('Next: Prepare a proposal from the recorded intent (a: actions), or review the newest operation, '
                      'a23983bd, whose approval window is open; Expiry and Approval window above say why this plan cannot run',
                      text)

    def test_no_open_operation_keeps_the_old_next(self):
        text = self.rows('closed')
        self.assertIn('Next: Prepare a proposal from the recorded intent (a: actions); Expiry and Approval window above say why',
                      text)
        self.assertNotIn('or review the newest operation', text)

    def test_the_plan_that_is_the_newest_is_not_named_as_another(self):
        text = self.rows('open', newest=self.CLOSED)
        self.assertNotIn('or review the newest operation', text)


class StagedKeysSaidOnceTests(MapTruth):
    """Item 7b (frames 21, 37): while a command is staged the key line says Enter submits and Esc cancels; the notice
    says what to type and what the command does, not the same keys again."""
    ENTRIES = (action('collect', 'Collect again', command='collect'),
               action('reconcile', 'Reconcile operation 64581d41', command='reconcile /w/op'))

    def staged(self, layer, focus):
        ws = self.workspace((120, 40))
        ws.facts.update(actions=list(self.ENTRIES))
        ws._open_actions()
        ws.action_focus = focus
        ws.layer = layer
        ws._stage(ws._actions()[focus])
        return ws

    def test_the_notice_and_the_key_line_say_submit_and_cancel_once_between_them(self):
        from intune_iac.workbench_tui import typing_line
        for layer in ('actions', 'summary'):
            for focus in (0, 1):
                ws = self.staged(layer, focus)
                both = ws.notice + ' | ' + typing_line(120, 'command')
                self.assertEqual(both.count('Esc'), 1, (layer, focus, both))
                self.assertEqual(both.count('submits'), 1, (layer, focus, both))
                self.assertTrue(ws.notice.strip(), (layer, focus))

    def test_what_to_type_is_still_said(self):
        ws = self.workspace((120, 40))
        mechanics = ws._mechanics({'kind': 'repository-entry', 'needs': ['REPOSITORY: a path']}, bound=False)
        self.assertEqual(mechanics[0], 'Type REPOSITORY at the cursor.')
        bound = ws._mechanics({'kind': 'repository-refresh'}, bound=True)
        self.assertIn('the digest after it pins the difference you reviewed', bound[0])
        self.assertTrue(all('Esc' not in form and 'submit' not in form for form in mechanics + bound))


class CommandNamesInSentencesTests(unittest.TestCase):
    """Item 7c (frames 42, 44): a sentence that sends the engineer to collect says it in words and names the key that
    lists the action (`Collect again (a: actions)`); the command text itself is shown once, on the action entry."""

    def source(self, module):
        from pathlib import Path
        return (Path(__file__).resolve().parents[1] / 'intune_iac' / (module + '.py')).read_text(encoding='utf-8')

    def test_no_diagnostic_or_refusal_sentence_embeds_a_colon_command(self):
        import re
        for module in ('workbench_diagnostics', 'workbench_screens'):
            self.assertEqual(re.findall(r'\(:[a-z][a-z-]*\)', self.source(module)), [], module)

    def test_the_collection_signals_say_collect_again_with_the_actions_key(self):
        from intune_iac.workbench_diagnostics import _collection
        running = {'last_attempt': {'status': 'collecting', 'run_id': 3, 'started_at': '2026-10-16T01:00:00Z'}}
        step = _collection(running)[0][0]['next_step']
        self.assertEqual(step, 'If no collector is running now, the run was interrupted: collect again (a: actions).')
        failed = {'last_attempt': {'status': 'failed', 'run_id': 4, 'started_at': '2026-10-16T01:00:00Z',
                                   'completed_at': '2026-10-16T01:00:01Z', 'error_code': 'x'}}
        self.assertEqual(_collection(failed)[0][0]['next_step'],
                         'Collect again (a: actions) when the source is reachable; no complete observation of this policy '
                         'exists yet.')


class ExecutionStageWordsTests(unittest.TestCase):
    """Item 7e (frame 39, stage 4): an execution the engine reported done but the store never recorded as verified says
    what happened in plain words, not 'never registered'."""

    def row(self, **execution):
        from intune_iac.workbench_screens import delivery_lines
        value = delivery_value(execution=dict({'status': 'unknown', 'error_code': None, 'service_status': None}, **execution))
        return ' '.join(' '.join(delivery_lines(value, 160)).split())

    def test_the_stage_says_the_engine_reported_success_and_the_store_recorded_no_verified_result(self):
        text = self.row()
        self.assertIn('4 Execution outcome unknown: the engine reported succeeded verified, but the store never recorded '
                      'a verified result', text)
        self.assertNotIn('never registered', text)

    def test_a_stage_with_no_engine_result_is_unchanged(self):
        text = self.row(engine_status=None, error_code='model_response_lost')
        self.assertIn("outcome unknown: the modeled service's response was lost (model_response_lost) | no engine result "
                      "recorded", text)


class RefreshRouteTests(Proposed):
    """Item 8, M-74 (frames 10, 74): no screen prints `repository-refresh REVISION`, a form without the digest that the
    staged route (9, then a) pins; they name the staged route, which asks for the REVISION and pins the difference."""
    ROUTE = 'choose Refresh the repository intent (a: actions)'
    view = diagnostics_tests.DiagnosticsTests.view

    def source(self, module):
        from pathlib import Path
        return (Path(__file__).resolve().parents[1] / 'intune_iac' / (module + '.py')).read_text(encoding='utf-8')

    def test_no_screen_text_prints_the_unpinned_form(self):
        for module in ('workbench_diagnostics', 'workbench_screens', 'workbench_repository', 'workbench_tui'):
            self.assertNotIn('repository-refresh REVISION', self.source(module), module)

    def test_the_repository_band_next_names_the_staged_route(self):
        self.import_intent()
        self.edit_description('Edited in the repository.')
        _, signals = self.view()
        step = signals['repository_stale']['next_step']
        self.assertEqual(step, 'Review the difference on the Repository surface (9), then ' + self.ROUTE + ': it asks for '
                               'the REVISION and pins the difference you reviewed.')

    def test_the_refusals_and_the_status_name_it_too(self):
        from intune_iac.workbench_repository import NEXT_ACTIONS
        from intune_iac.workbench_screens import KNOWN_NEXT, REFUSALS
        for step in (REFUSALS['maintenance_repository_stale'][1], REFUSALS['workbench_repository_stale'][1],
                     KNOWN_NEXT['consumer_changed'], NEXT_ACTIONS['stale']):
            self.assertIn('Refresh the repository intent (a: actions)', step)
            self.assertIn('pins', step)
        self.assertIn('Then Prepare a proposal from the recorded intent (a: actions).',
                      REFUSALS['maintenance_repository_stale'][1])


class ChangedFileNamedTests(Proposed):
    """Item 8, M-66 (frame 66; delivery next steps): the refusal and the Delivery steps for a changed bound file name the
    operation and the file (the plan's context path, which maintenance._repository_review reports as context_path)."""

    def refusal(self, **kw):
        from intune_iac.workbench_screens import refusal_lines
        value = {'status': 'error', 'error': {'code': 'maintenance_source_changed', 'message': 'A bound file changed.'}}
        return ' '.join(' '.join(refusal_lines(value, 118, **kw)).split())

    def test_the_cause_names_the_operation_and_the_context_file(self):
        text = self.refusal(operation='650a1a61', verb='execute', context_file='/w/my ctx.json')
        self.assertIn("Cause: A file this proposal bound changed after operation 650a1a61 was prepared (the context file "
                      "'/w/my ctx.json'), so its review no longer describes what would run.", text)

    def test_with_only_the_operation_known_it_says_which_operation(self):
        text = self.refusal(operation='650a1a61', verb='execute')
        self.assertIn('Cause: A file this proposal bound changed after operation 650a1a61 was prepared (its context file), '
                      'so its review no longer describes what would run.', text)

    def test_neither_known_keeps_the_general_cause(self):
        self.assertIn('Cause: A file this proposal bound changed after it was prepared (its context file), so its review '
                      'no longer describes what would run.', self.refusal(verb='execute'))

    def test_the_workspace_reads_the_context_file_the_plan_bound(self):
        from intune_iac.workbench_tui import Workspace
        review = self.propose()
        operation = self.root / 'operation'
        context = self.root / 'operation.intent-context.json'
        ws = self.workspace(4, {})
        self.assertEqual(Workspace._context_file_for(ws, 'execute %s %s' % (shlex_quote(operation), review['approval_digest'])),
                         str(context))
        self.assertIsNone(Workspace._context_file_for(ws, 'collect'))
        self.assertIsNone(Workspace._context_file_for(ws, 'execute /nonexistent/operation DIGEST'))

    def test_delivery_steps_name_the_operation_and_the_file(self):
        from intune_iac.workbench_delivery import _next_step
        proposal = {'context_changed': True, 'context_path': '/w/my ctx.json', 'operation_id': 'a' * 32}
        stages = {'proposal': proposal, 'approval': {'status': 'waiting', 'closes_at': 4102444800},
                  'readback': {'status': 'done'}, 'reconciliation': {'status': 'not_needed'},
                  'deployment_record': {'status': 'not_yet'}, 'observed_after': {'status': 'not_yet'}}
        step = ' '.join(_next_step(stages, '/w/op', '/w/store').split())
        self.assertIn("The context file '/w/my ctx.json' that operation aaaaaaaa bound changed after it was prepared, so "
                      'execute refuses it (maintenance_source_changed)', step)
        done = dict(stages, approval={'status': 'done'}, deployment_record={'status': 'done', 'context_changed': True,
                                                                           'context_path': '/w/my ctx.json', 'operation_id': 'a' * 32})
        self.assertIn("The deployment of operation aaaaaaaa was recorded, but the context file '/w/my ctx.json' it bound "
                      'has changed since', ' '.join(_next_step(done, '/w/op', '/w/store').split()))
        gone = dict(stages, approval={'status': 'done'}, deployment_record={'status': 'not_available', 'reason': 'context_changed',
                                                                           'context_path': '/w/my ctx.json', 'operation_id': 'a' * 32})
        self.assertIn("The context file '/w/my ctx.json' that operation aaaaaaaa bound changed after it was prepared, so it "
                      'cannot become a deployment record', ' '.join(_next_step(gone, '/w/op', '/w/store').split()))


def shlex_quote(path):
    import shlex
    return shlex.quote(str(path))


class ReducedBandNamesTheOperationTests(unittest.TestCase):
    """Item 8, L-60 (frame 35, 60x20): the strip drops OP at 60 columns and the band carried no operation id, so
    nothing on the screen said which operation is unknown; the narrow band now names it."""
    OPERATION = 'c0e8470422ca4504916bf759d495698d'
    SIGNAL = {'area': 'operations', 'code': 'operation_outcome_unknown', 'observed': 'Started dispatch.',
              'next_step': 'Reconcile.', 'evidence': {'operation_id': OPERATION}}

    def band(self, width, evidence=None):
        from intune_iac.workbench_screens import hazard_rows
        signal = dict(self.SIGNAL, evidence=self.SIGNAL['evidence'] if evidence is None else evidence)
        return hazard_rows({'signals': [signal]}, [signal], width)

    def test_at_60_columns_the_band_names_the_operation_and_keeps_its_response(self):
        from intune_iac.workbench_tui import cell_width
        rows = self.band(60)
        self.assertEqual(rows[0], '! Op c0e84704 unknown. Reconcile, never replays (a: actions)')
        self.assertLessEqual(cell_width(rows[0]), 60)

    def test_wider_bands_keep_the_id_and_the_narrowest_keeps_its_response(self):
        self.assertIn('c0e84704', self.band(80)[0])
        self.assertIn('Reconcile (a actions)', self.band(40)[0])

    def test_without_an_operation_id_the_band_is_unchanged(self):
        self.assertEqual(self.band(60, evidence={})[0], '! Outcome unknown. Reconcile, never replays (a: actions)')


class RunningStripTests(unittest.TestCase):
    """Item 8, L-running (frame 32): while execute runs, the strip shows the operation as executing, not prepared (the
    status line already says executing); a read-only reconcile shows reconciling; nothing else changes the strip."""
    workspace = states_tests.StateSurfaceTests.workspace

    def strip(self, notice, command, width=140, operation='prepared'):
        ws = self.workspace(5, {})
        ws.facts = dict(ws.facts, name='Windows Privacy Pilot', operation=operation, repository='current', observation='fresh')
        ws.notice, ws.last_command = notice, command
        return ws._context_strip(width)

    def test_an_executing_operation_is_shown_as_executing(self):
        strip = self.strip('RUNNING: executing operation c0e84704; its outcome is not yet known.', "execute '/w/op' " + 'a' * 64)
        self.assertTrue(strip.endswith('OP executing'), strip)
        self.assertNotIn('prepared', strip)

    def test_a_reconcile_shows_reconciling(self):
        strip = self.strip('RUNNING: reconciling operation c0e84704 (a read; it never replays the change).', "reconcile '/w/op'")
        self.assertTrue(strip.endswith('OP reconciling'), strip)

    def test_otherwise_the_strip_keeps_the_recorded_state(self):
        self.assertTrue(self.strip('', 'collect').endswith('OP prepared'))
        self.assertTrue(self.strip('RUNNING: collecting from the service; the new observation is not yet recorded.',
                                   'collect').endswith('OP prepared'))

    def test_executing_is_a_hazard_the_strip_keeps_after_routine_states(self):
        running = 'RUNNING: executing operation c0e84704; its outcome is not yet known.'
        command = "execute '/w/op' " + 'a' * 64
        for width in (100, 120, 140):
            self.assertIn('OP executing', self.strip(running, command, width), width)
        from intune_iac.workbench_screens import HAZARD_STATES
        self.assertIn('executing', HAZARD_STATES['OPERATION'])
        self.assertNotIn('reconciling', HAZARD_STATES['OPERATION'])  # a read; it never replays the change


class OneHiddenFindingMarkerTests(unittest.TestCase):
    """Item 8, L-more (frames 34, 37, 54, 55): the marker for hidden findings reads one way on every surface, in the form
    that names the surface: `+N more finding(s) (2 Inspector)`."""
    SIGNALS = [
        {'area': 'operations', 'code': 'operation_outcome_unknown', 'observed': 'x', 'next_step': 'y', 'evidence': {}},
        {'area': 'freshness', 'code': 'observation_stale', 'observed': 'x', 'next_step': 'y', 'evidence': {}},
        {'area': 'repository', 'code': 'repository_stale', 'observed': 'x', 'next_step': 'y', 'evidence': {}}]

    def rows(self, count, **kw):
        from intune_iac.workbench_screens import hazard_rows
        return ' '.join(' '.join(hazard_rows({}, self.SIGNALS[:count], 140, **kw)).split())

    def test_every_surface_and_mode_uses_the_same_wording(self):
        for kw in ({}, {'here': True}, {'routes': False}, {'here': True, 'routes': False}, {'listed': True}):
            self.assertIn('+1 more finding (2 Inspector)', self.rows(2, **kw), kw)
            self.assertIn('+2 more findings (2 Inspector)', self.rows(3, **kw), kw)
            self.assertNotIn('NEEDS ATTENTION', self.rows(2, **kw), kw)

    def test_no_marker_without_other_findings(self):
        self.assertNotIn('more finding', self.rows(1))


class GivenIntentShownTests(unittest.TestCase):
    """Item 8, L-given (frame 67): the refusal that says the intent given is not the one the plan cites shows the given
    intent beside the cited one, taken from the command the engineer typed."""
    CITED, GIVEN = '7e' * 32, 'ab' * 32
    MESSAGE = ('This operation cites repository intent %s, not the intent given; record the deployment with the intent it '
               'cites.' % CITED)

    def value(self):
        return {'status': 'error', 'error': {'code': 'workbench_deployment_intent_not_cited', 'message': self.MESSAGE,
                                              'effects': {'deployment_recorded': False}}}

    def test_the_cause_shows_both_intents(self):
        from intune_iac.workbench_screens import refusal_lines
        text = ' '.join(' '.join(refusal_lines(self.value(), 140, operation='d190dfd4', verb='deployment-record',
                                               given=self.GIVEN)).split())
        self.assertIn('Cause: Operation d190dfd4 cites repository intent %s, not the intent given (%s)' % (self.CITED, self.GIVEN),
                      text)

    def test_without_the_command_s_intent_the_cause_is_unchanged(self):
        from intune_iac.workbench_screens import refusal_lines
        text = ' '.join(' '.join(refusal_lines(self.value(), 140, operation='d190dfd4', verb='deployment-record')).split())
        self.assertIn('not the intent given;', text)
        self.assertNotIn('not the intent given (', text)

    def test_the_workspace_reads_the_intent_from_the_deployment_record_command(self):
        from intune_iac.workbench_tui import Workspace
        self.assertEqual(Workspace._intent_given(None, "deployment-record '/w/my op' " + self.GIVEN), self.GIVEN)
        self.assertIsNone(Workspace._intent_given(None, "deployment-record '/w/my op'"))
        self.assertIsNone(Workspace._intent_given(None, 'collect'))


class RelatedOperationsTests(unittest.TestCase):
    """Item 8, L-proposals (frame 47): the list is operations with their latest outcomes, so it says so, and it uses
    the 8-character operation ids the rest of the workspace uses."""

    def text(self):
        from intune_iac.workbench_screens import queue_lines
        records = [{'operation_id': 'b668ad2fa6c54d20b94bd8677ce56735', 'sequence': 1, 'status': 'prepared', 'recorded_at': 'T1'},
                   {'operation_id': 'b668ad2fa6c54d20b94bd8677ce56735', 'sequence': 2, 'status': 'succeeded_verified', 'recorded_at': 'T2'}]
        value = {'findings': [{'object_id': 'o' * 8, 'finding': 'ownership_unknown', 'priority': 'review', 'owner': None,
                               'owner_role': 'human_review_assignee', 'writer_ownership': {'status': 'unknown', 'reason': 'x'},
                               'source_owner_claim': {'assertion_class': 'source_declared', 'value': None},
                               'review_record': {'status': 'unknown', 'reason': 'review_not_recorded'},
                               'compatibility': {'profile': 'synthetic_windows_settings_catalog', 'native_provider_qualified': False},
                               'evidence': {'evidence_class': 'synthetic', 'observed_at': 'T0', 'snapshot_id': 'a' * 64},
                               'related_proposals': records}]}
        return '\n'.join(queue_lines(value, 120))

    def test_the_heading_says_operations_and_the_id_has_eight_characters(self):
        text = self.text()
        self.assertIn('Related operations (1)\n    b668ad2f succeeded verified (2 journal records; latest T2)', text)
        self.assertNotIn('Related proposals', text)
        self.assertNotIn('b668ad2fa6c5', text)


class JournalLastRecordedTests(unittest.TestCase):
    """Item 8, L-lastrecorded (frame 23): `last recorded` beside a later deployment record read as the latest record of
    anything; the Operation row says it is the operation's journal."""

    def row(self, **operation):
        from intune_iac.workbench_screens import state_lines
        states = {'operation': dict({'operation_id': 'd' * 32, 'journal_status': 'succeeded_verified',
                                     'status': 'succeeded_verified', 'recorded_at': '2026-10-16T01:16:31Z'}, **operation)}
        return ' '.join(' '.join(state_lines(states, 140)).split())

    def test_the_time_is_labelled_as_the_journals(self):
        text = self.row()
        self.assertIn('dddddddd succeeded verified; journal last recorded 2026-10-16 01:16:31 UTC', text)
        self.assertNotIn('; last recorded', text)


class CollectionNextOnTheInspectorTests(unittest.TestCase):
    """Item 8, L-next2 (frames 24, 43, 46): the collection result's Next named key 2 while the screen was already 2; on
    the Inspector it says what pressing 2 again does."""
    RUN = {'run_id': 2, 'status': 'complete', 'object_count': 1, 'coverage': 'complete', 'observed_at': '2026-10-16T01:16:37Z'}

    def next_of(self, tab, value=None):
        from intune_iac.workbench_screens import collection_result_lines
        text = ' '.join(' '.join(collection_result_lines(value or self.RUN, 120, tab=tab)).split())
        return text[text.index('Next:'):]

    def test_on_the_inspector_it_says_what_pressing_2_again_does(self):
        self.assertEqual(self.next_of(1), 'Next: press 2 again to read this policy with this observation; this screen shows '
                                          'the collection result.')

    def test_elsewhere_the_step_is_unchanged(self):
        for tab in (0, 3, 4, None):
            self.assertEqual(self.next_of(tab), 'Next: 2 reads this policy again with this observation.')

    def test_an_incomplete_run_is_unchanged_everywhere(self):
        incomplete = dict(self.RUN, status='partial')
        self.assertEqual(self.next_of(1, incomplete), self.next_of(0, incomplete))


class ConsumerVerifiedWordsTests(unittest.TestCase):
    """Item 8, L-verified (frames 07, 17, 30, 52, 75, 76, 78, 79, 82): `Consumer: verified` under a caller-asserted
    revision says what was verified (workbench_repository.consumer_contract: the component's files, as read, consume
    exactly this policy), not the revision."""
    SAID = "verified (the component's files, as read, consume exactly this policy)"

    def test_the_refresh_result_says_what_was_verified(self):
        from intune_iac.workbench_screens import refresh_result_lines
        value = {'artifact_id': 'a' * 64, 'created': True, 'data': {'source_revision': 'f' * 40, 'revision_content_verified': False,
                                                                   'consumer': {'status': 'verified'}}}
        text = ' '.join(' '.join(refresh_result_lines(value, 140)).split())
        self.assertIn('Consumer: ' + self.SAID, text)
        self.assertIn('caller asserted, not checked against the files', text)

    def test_the_repository_status_says_it_in_the_same_words(self):
        from intune_iac.workbench_screens import repository_lines
        status = {'scope': {'stack': 's', 'component': 'c'}, 'revision_content_verified': False,
                  'consumer': {'status': 'verified', 'reasons': []}, 'freshness': {'status': 'current'}}
        text = ' '.join(' '.join(repository_lines(status, 140)).split())
        self.assertIn('Consumer ' + self.SAID, text)

    def test_other_consumer_states_are_unchanged(self):
        from intune_iac.workbench_screens import refresh_result_lines, repository_lines
        value = {'artifact_id': 'a' * 64, 'created': True, 'data': {'source_revision': 'f' * 40, 'consumer': {'status': 'mismatch'}}}
        self.assertIn('Consumer: mismatch', ' '.join(refresh_result_lines(value, 140)))
        status = {'scope': {}, 'consumer': {'status': 'mismatch', 'reasons': ['policy_key_identity']}, 'freshness': {'status': 'stale'}}
        self.assertIn('Consumer mismatch: policy_key_identity', ' '.join(repository_lines(status, 140)))


class RecordedQueueReviewTests(unittest.TestCase):
    """Item 8, L-bare (frame 49): the line that follows recording a queue review names the finding, the policy and the
    next step (reading it back), all from the record's own data (workbench_queue.amend)."""
    VALUE = {'artifact_id': '53e45c2369a0' + '0' * 52, 'kind': 'queue_review', 'created': True, 'recorded_at': '2026-10-16T01:17:47Z',
             'data': {'finding': 'reporting_incomplete', 'object_id': '22222222-2222-4222-8222-222222222222', 'version': 2,
                      'previous_artifact_id': 'f' * 64}}

    def rows(self, value=None):
        from intune_iac.workbench_screens import recorded_lines
        return recorded_lines(value or self.VALUE, 118)

    def test_the_record_names_finding_policy_version_and_next(self):
        text = '\n'.join(row.strip() for row in self.rows())
        self.assertIn('Review version 2 of reporting incomplete for policy 22222222: an annotation, never approval or '
                      'execution.', text)
        self.assertIn('Next: In the workspace:\nqueue-review reporting_incomplete', text)

    def test_a_record_without_the_data_is_unchanged(self):
        bare = dict(self.VALUE, data={})
        self.assertEqual(len(self.rows(bare)), 1)


class ReopenedReviewInputsTests(Proposed):
    """Item 8, L-nofiles (frames 65, 70, 72): a plan review reopened later has no files_written (that came with the
    proposal call), so it shows the input files the plan itself records it bound: the desired source and the context."""

    def test_a_reopened_review_lists_the_files_the_plan_bound(self):
        from intune_iac import maintenance
        review = self.propose('operation one')
        base = str(self.root / 'operation one')
        reopened = maintenance.review(self.root / 'operation one')
        self.assertNotIn('files_written', reopened)
        text = self.summary(self.workspace(4, reopened))
        self.assertIn('Input files bound by the plan: %s, %s' % (shlex_quote(base + '.intent-desired.json'),
                                                                shlex_quote(base + '.intent-context.json')), text)
        self.assertNotIn('Input files written', text)

    def test_the_fresh_proposal_keeps_its_written_row_and_adds_no_second(self):
        review = self.propose('operation two')
        text = self.summary(self.workspace(4, review))
        self.assertIn('Input files written:', text)
        self.assertNotIn('Input files bound', text)

    def test_an_unreadable_plan_shows_no_row(self):
        text = self.summary(self.workspace(4, {'operation_id': 'a' * 32, 'operation_root': '/nonexistent/operation',
                                              'object_id': states_tests.OBJECT, 'status': 'prepared'}))
        self.assertNotIn('Input files', text)
