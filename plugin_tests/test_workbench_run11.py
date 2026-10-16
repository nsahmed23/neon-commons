"""PKG-PRES-RUN11 (journey 28 run 11 frame reviews): what the screens say, not what the product decides.

Items are added in the order of the brief; each class names its item. Temporary directories only.
"""
import shlex
import unittest

from plugin_tests import test_workbench_repository as repository_tests
from plugin_tests import test_workbench_states as states_tests
from plugin_tests.test_workbench_map_truth import MapTruth
from intune_iac.workbench_screens import STRIP_DEFINITIONS
from plugin_tests.test_workbench_run10 import action

OBJECT, TENANT = repository_tests.OBJECT, repository_tests.TENANT


class Proposed(unittest.TestCase):
    """A store with a recorded intent that the repository has since changed, so propose-from-intent has a change."""
    RESOURCE_ADDRESS = repository_tests.RepositoryOwnedChangeTests.RESOURCE_ADDRESS
    setUp = repository_tests.RepositoryOwnedChangeTests.setUp
    import_intent = repository_tests.RepositoryOwnedChangeTests.import_intent
    edit_description = repository_tests.RepositoryOwnedChangeTests.edit_description
    workspace = states_tests.StateSurfaceTests.workspace
    summary = states_tests.StateSurfaceTests.summary

    def propose(self, name='operation'):
        from intune_iac.workbench_repository import propose_from_intent, refresh_intent
        self.import_intent()
        self.edit_description('Edited in the repository.')
        refresh_intent(self.store, OBJECT, 'b' * 40)
        return propose_from_intent(self.store.root, self.service.root, OBJECT, self.root / name)


class FilesWrittenTests(Proposed):
    """Item 1 (run11-1): the plan review after propose-from-intent lists the input files the action wrote."""

    def test_the_proposal_result_names_the_two_input_files(self):
        review = self.propose()
        output = str(self.root / 'operation')
        self.assertEqual(review['files_written'], [output + '.intent-desired.json', output + '.intent-context.json'])

    def test_the_plan_review_prints_the_row_with_both_paths_quoted(self):
        review = self.propose('operation one')
        text = self.summary(self.workspace(4, review))
        base = str(self.root / 'operation one')
        self.assertIn('Input files written: %s, %s' % (shlex.quote(base + '.intent-desired.json'),
                                                       shlex.quote(base + '.intent-context.json')), text)


class ShellFormTests(unittest.TestCase):
    """Item 2 (run11-2): every shell form the workbench prints is complete, starting with the program name."""

    MODULES = ('workbench', 'workbench_screens', 'workbench_tui', 'workbench_delivery', 'workbench_diagnostics',
               'companion_page')
    # "workbench COMMAND --flag": the shape of a shell form; the program name must stand in front of it.
    BARE = r"(?<!intune-iac )(?<![\w./-])workbench (?:[a-z][a-z-]+) --"

    def source(self, module):
        from pathlib import Path
        return (Path(__file__).resolve().parents[1] / 'intune_iac' / (module + '.py')).read_text(encoding='utf-8')

    def test_no_printed_shell_form_lacks_the_program_name(self):
        import re
        for module in self.MODULES:
            found = [match.group(0) for match in re.finditer(self.BARE, self.source(module))]
            self.assertEqual(found, [], module)

    def test_the_deployment_record_shell_form_starts_with_the_program(self):
        from plugin_tests.test_workbench_run9 import next_step
        step = next_step(record={'status': 'available', 'intent_id': 'i' * 64}, operation='/w/op', store='/w/store')
        self.assertIn('From a shell:\n  intune-iac workbench deployment-record --root /w/store --operation /w/op --intent '
                      + 'i' * 64, step)

    def test_the_companion_shell_forms_start_with_the_program(self):
        from intune_iac.companion_page import COMPANION_SERVE, COMPANION_WRITE
        self.assertTrue(COMPANION_WRITE.startswith('intune-iac workbench companion '), COMPANION_WRITE)
        self.assertTrue(COMPANION_SERVE.startswith('intune-iac workbench companion '), COMPANION_SERVE)


class RepositoryVerdictTests(Proposed):
    """Item 3 (run11-3): the repository's no-change verdict names the two sides the code compares.

    workbench_repository.intent_freshness compares the recorded intent's desired body with the repository's value
    now at the intent pointer (field_changes(data['desired'], desired_now)). No observation takes part.
    """

    def status(self):
        from intune_iac.workbench_repository import intent_freshness
        intent = self.import_intent()
        (self.repo / 'components/terraform/intune-reference/override.tf').write_text('output "x" {\n  value = 1\n}\n')
        fresh = intent_freshness(intent['data'])
        self.assertEqual((fresh['status'], fresh['field_changes']['status']), ('stale', 'no_change'))
        return {'freshness': fresh, 'scope': intent['data']['scope'], 'repository_intent_id': intent['artifact_id']}

    def rows(self, width=118):
        from intune_iac.workbench_screens import repository_lines
        return repository_lines(self.status(), width)

    def test_the_heading_and_the_verdict_name_the_recorded_intent_and_the_repository(self):
        rows = self.rows()
        text = ' '.join(' '.join(rows).split())
        self.assertIn('RECORDED INTENT AGAINST THE REPOSITORY NOW', rows)
        self.assertIn("NO CONFIGURATION CHANGE The recorded intent's desired body equals the repository's body now at the "
                      "intent pointer, under the execution plan's equality (assignments, technologies and role scope tags match in "
                      "any order, each repeat counting; every other field, including the order of settings, must match "
                      "exactly).", text)  # run 12 item 5
        self.assertIn('The observation is not part of this comparison.', text)

    def test_a_repository_verdict_never_speaks_of_the_observed_body_or_sits_under_the_old_heading(self):
        rows = self.rows()
        self.assertNotIn('DESIRED POLICY AT THE INTENT POINTER', rows)
        self.assertNotIn('observed body', ' '.join(rows))

    def test_the_plan_review_keeps_its_desired_against_observed_verdict(self):
        from intune_iac.workbench_screens import change_lines
        text = ' '.join(change_lines({'status': 'no_change', 'changes': []}, 118))
        self.assertIn('The desired body equals the observed body under the execution plan', text)


class RestoreReviewTests(Proposed):
    """Item 4 (run11-4): a restore plan says it restores operation N and that AFTER is that operation's observation
    from before its change, not the recorded intent (maintenance.propose_restore writes before_estate as the desired body)."""

    def restored(self):
        from intune_iac import maintenance
        from intune_iac.workbench import _restore_proposal
        review = self.propose()
        operation = self.root / 'operation'
        maintenance.execute(operation, approve_digest=review['approval_digest'])
        self.store.collect(self.service)
        return review, _restore_proposal(operation, self.root / 'restore')

    def test_the_restore_result_names_the_operation_it_restores(self):
        review, restore = self.restored()
        self.assertEqual(restore['restore_of'], review['operation_id'])
        self.assertNotEqual(restore['operation_id'], review['operation_id'])

    def test_the_change_review_says_it_is_a_restore_and_where_after_comes_from(self):
        review, restore = self.restored()
        text = self.summary(self.workspace(4, restore))
        short = review['operation_id'][:8]
        self.assertIn("Restore of operation %s: AFTER is that operation's observation from before its change, "
                      "not the recorded intent." % short, text)
        self.assertLess(text.index('Restore of operation'), text.index('[PLAN REVIEW]'))

    def test_a_plan_that_is_not_a_restore_says_nothing_of_one(self):
        self.assertNotIn('Restore of operation', self.summary(self.workspace(4, self.propose())))


def balanced(sentence):
    """True when every bracket closes in order and none is left open."""
    stack = []
    for char in sentence:
        if char == '(':
            stack.append(char)
        elif char == ')':
            if not stack:
                return False
            stack.pop()
    return not stack


class ReconcileNextTests(unittest.TestCase):
    """Item 5 (gemini-run11-2, frame 54): the Next that names reconcile reads as one balanced sentence."""

    UNKNOWN = {'operation_id': 'a' * 32, 'status': 'outcome_unknown'}

    def rendered(self, width):
        from intune_iac.workbench_screens import lifecycle_lines
        return ' '.join(' '.join(lifecycle_lines(5, width, self.UNKNOWN)).split())

    def test_the_rendered_next_has_balanced_parentheses_at_every_width(self):
        for width in (118, 80, 60):
            text = self.rendered(width)
            self.assertTrue(balanced(text), text)
            self.assertIn('Next: Reconcile it (a: actions); it never replays the change. v shows every delivery stage.', text)

    def test_the_lifecycle_next_for_a_prepared_unknown_operation_reads_the_same(self):
        from intune_iac.workbench_screens import lifecycle_next
        for tab, value in ((5, self.UNKNOWN), (4, self.UNKNOWN)):
            step = lifecycle_next(tab, value, 0)
            self.assertEqual(step, 'Reconcile it (a: actions); it never replays the change. v shows every delivery stage', tab)
            self.assertTrue(balanced(step), step)

    def test_the_band_and_the_lifecycle_name_reconcile_in_the_same_words(self):
        from intune_iac.workbench_screens import hazard_rows
        band = ' '.join(hazard_rows({'operation': 'outcome_unknown'}, [], 140))
        self.assertIn('Next: Reconcile it (a: actions); it never replays the change', band)
        self.assertTrue(balanced(band), band)


class OneNextTests(unittest.TestCase):
    """Item 6 (frames 19, 38, 54): when the hazard band carries a Next, the lifecycle line adds none."""
    workspace = states_tests.StateSurfaceTests.workspace
    BAND = states_tests.RunEightWorkspaceTests.BAND
    RESULT = {'result': {'operation_id': 'a' * 32, 'status': 'succeeded_verified'}}
    UNKNOWN = {'operation_id': 'a' * 32, 'status': 'outcome_unknown'}
    RECONCILED = {'result': {'operation_id': 'a' * 32, 'status': 'reconciled', 'journal_status': 'reconciled'}}

    def banded(self, tab, value, signals=None):
        workspace = self.workspace(tab, value)
        workspace.facts = dict(workspace.facts, signals=[self.BAND] if signals is None else signals)
        return ' '.join(' '.join(workspace._summary_lines(118)).split())

    def test_the_band_carries_a_next_so_the_line_has_none(self):
        from intune_iac.workbench_screens import hazard_rows
        self.assertIn('Next:', ' '.join(hazard_rows({}, [self.BAND], 118)))
        for value in (self.RESULT, self.RECONCILED, self.UNKNOWN):
            text = self.banded(5, value)
            self.assertIn('Lifecycle: 9 Repository > 5 Plan > 6 Execution (here) > Delivery (v opens it).', text)
            self.assertNotIn('Next:', text, value)
            self.assertNotIn('shows every delivery stage', text, value)

    def test_without_a_band_the_line_keeps_its_next(self):
        self.assertIn('Next: v shows every delivery stage, including the deployment record.', self.banded(5, self.RESULT, []))
        self.assertIn('Next: Reconcile it (a: actions); it never replays the change.', self.banded(5, self.UNKNOWN, []))

    def test_a_command_the_band_does_not_carry_stays_on_the_plan_review(self):
        prepared = {'operation_id': 'a' * 32, 'object_id': OBJECT, 'status': 'prepared', 'expires_at': 4102444800,
                    'operation_root': '/w/op'}
        text = self.banded(4, prepared)
        self.assertIn("execute /w/op DIGEST", text)


class OneDescriptionTests(unittest.TestCase):
    """Item 7 (frames 21, 37, 62, 80): a focused entry states its effect once, in one description."""
    CLAIMS = {'reconcile': ('replaying the change',), 'collect': ('changes no policy',),
              'repository-refresh': ('no Git commit, approval or apply',), 'propose-from-intent': ('nothing is approved or sent',),
              'propose': ('nothing is approved or sent',), 'repository-entry': ('writes nothing',),
              'diagnostics': ('records nothing',), 'deployment-record': ('sends nothing',),
              'companion': ('records nothing', 'opens no browser')}

    def entry(self, kind, available=True):
        from intune_iac.workbench import ACTION_EFFECTS, ACTION_SUMMARY
        blocked = None if available else {'code': 'maintenance_observation_stale', 'message': 'Collect again.'}
        return {'kind': kind, 'label': 'Label of ' + kind, 'command': kind + ' x', 'cursor': None, 'needs': [],
                'summary': ACTION_SUMMARY[kind], 'effects': ACTION_EFFECTS[kind], 'available': available,
                'blocked': blocked, 'binding': {}}

    def focused(self, kind, available=True, width=118):
        from intune_iac.workbench_screens import actions_lines
        return ' '.join(' '.join(line.strip() for line in actions_lines([self.entry(kind, available)], 0, width)).split())

    def test_the_focused_entry_prints_one_description_block(self):
        from intune_iac.workbench import ACTION_EFFECTS, ACTION_SUMMARY
        for kind in ACTION_SUMMARY:
            for available in (True, False):
                text = self.focused(kind, available)
                self.assertIn(' '.join(ACTION_EFFECTS[kind].split()), text, kind)
                if ACTION_SUMMARY[kind] not in ACTION_EFFECTS[kind]:
                    self.assertNotIn(' '.join(ACTION_SUMMARY[kind].split()), text, kind)

    def test_the_other_entries_keep_their_one_line_summary(self):
        from intune_iac.workbench import ACTION_SUMMARY
        from intune_iac.workbench_screens import actions_lines
        entries = [self.entry('collect'), self.entry('reconcile')]
        text = ' '.join(' '.join(line.strip() for line in actions_lines(entries, 0, 118)).split())
        self.assertIn(' '.join(ACTION_SUMMARY['reconcile'].split()), text)

    def test_the_one_description_keeps_every_claim_the_summary_made(self):
        from intune_iac.workbench import ACTION_EFFECTS
        for kind, claims in self.CLAIMS.items():
            for claim in claims:
                self.assertIn(claim.lower(), ACTION_EFFECTS[kind].lower(), (kind, claim))

    def test_no_description_says_a_claim_twice(self):
        import re
        from intune_iac.workbench import ACTION_EFFECTS
        for kind, text in ACTION_EFFECTS.items():
            words = re.findall(r"[a-z']+", text.lower())
            grams = [' '.join(words[index:index + 4]) for index in range(len(words) - 3)]
            self.assertEqual(sorted({gram for gram in grams if grams.count(gram) > 1}), [], kind)
            for claim in self.CLAIMS[kind]:
                self.assertEqual(text.lower().count(claim.lower()), 1, (kind, claim))


class StagedNoticeTests(MapTruth):
    """Item 7: the staged notice does not say again, under the open actions list, what the focused entry just said."""
    ENTRIES = (action('collect', 'Collect again', command='collect'),
               action('reconcile', 'Reconcile operation 64581d41', command='reconcile /w/op'))

    def listed(self, focus=0):
        ws = self.workspace((120, 40))
        ws.facts.update(actions=list(self.ENTRIES))
        ws._open_actions()
        ws.action_focus = focus
        return ws

    def test_under_the_open_list_the_notice_says_no_key_the_key_line_says(self):
        for focus, word in ((0, 'collect'), (1, 'reconcile')):
            ws = self.listed(focus)
            ws._stage(ws._actions()[focus])
            self.assertNotIn('STAGED', ws.notice)
            self.assertNotIn('Enter submits', ws.notice)  # run 12 item 7: the key line says Enter submits and Esc cancels
            self.assertNotIn('Esc cancels', ws.notice)
            self.assertTrue(ws.notice.strip())

    def test_outside_the_list_the_notice_still_says_what_the_staged_command_does(self):
        ws = self.listed(1)
        ws.layer = 'summary'
        ws._stage(ws._actions()[1])
        self.assertIn('STAGED reconcile: never replays the change.', ws.notice)


class KeyExplainedTests(unittest.TestCase):
    """Item 8 (gemini-run11-3, frame 67): a key the body names is explained on that screen."""
    RECORDED = {'artifact_id': '8f5e4404598b' + '0' * 52}
    REFUSED = {'status': 'error', 'error': {'code': 'workbench_deployment_intent_not_cited',
                                            'message': 'This operation cites repository intent ' + 'a' * 64 + ', not the intent given; '
                                            'record the deployment with the intent it cites.',
                                            'effects': {'deployment_recorded': False}}}

    def text(self, width=118):
        from intune_iac.workbench_screens import refusal_lines
        return ' '.join(' '.join(refusal_lines(self.REFUSED, width, operation='650a1a61', verb='deployment-record',
                                               recorded=self.RECORDED)).split())

    def test_the_v_in_the_refusal_says_what_it_opens(self):
        text = self.text()
        self.assertIn('already has deployment record 8f5e4404598b (v opens Delivery, where it is stage 7); there is nothing '
                      'to record.', text)
        self.assertNotIn('v shows it as stage 7', text)

    def test_a_refusal_with_no_key_named_names_none(self):
        from intune_iac.workbench_screens import refusal_lines
        value = {'status': 'error', 'error': {'code': 'workbench_deployment_intent_not_cited', 'message': 'x',
                                              'effects': {'deployment_recorded': False}}}
        self.assertNotIn(' v ', ' '.join(refusal_lines(value, 118, operation='650a1a61', verb='deployment-record')))


class RunningKeysTests(MapTruth):
    """Item 9 (frames 32, 40): a running step says what Ctrl-C leaves and what to do afterwards."""
    COMMANDS = {'execute': "execute '/w/op' " + 'a' * 64, 'reconcile': "reconcile '/w/op'", 'collect': 'collect',
                'other': 'history-recent'}
    LEFT = {'execute': ('unknown', 'reconcile'), 'reconcile': ('only reads', 'again'), 'collect': ('no end', 'collect again'),
            'other': ('unfinished', 'diagnostics')}

    def test_each_running_step_says_what_the_interrupt_leaves_and_the_next_step(self):
        from intune_iac.workbench_tui import running_keys
        for kind, command in self.COMMANDS.items():
            line = running_keys(command, 140)
            self.assertTrue(line.startswith('Ctrl-C '), line)
            for word in self.LEFT[kind]:
                self.assertIn(word, line, (kind, line))

    def test_the_line_fits_the_window_at_every_width_and_keeps_its_response(self):
        from intune_iac.workbench_tui import cell_width, running_keys
        for kind, command in self.COMMANDS.items():
            for width in (140, 100, 80, 60, 48):
                line = running_keys(command, width)
                self.assertLessEqual(cell_width(line), width, (kind, width, line))
                self.assertIn('Ctrl-C', line)

    def test_the_bottom_row_of_a_running_frame_is_that_line_not_the_idle_keys(self):
        from intune_iac.workbench_tui import running_notice, running_keys
        ws = self.workspace((120, 40))
        command = self.COMMANDS['execute']
        ws.last_command = command
        ws.notice = running_notice(command)
        rows = self.plain(ws)
        self.assertEqual(rows[-1].strip(), running_keys(command, 120))
        self.assertIn('RUNNING: executing operation', rows[-2])
        ws.notice = 'Summary shown.'
        self.assertIn('? help', self.plain(ws)[-1])


class RestoreRefusalNextTests(unittest.TestCase):
    """Item 10 (run11-6, frame 69): the restore refusal's Next says whose value the proposal it points to carries."""

    def text(self, width=118):
        from intune_iac.workbench_screens import refusal_lines
        value = {'status': 'error', 'error': {'code': 'maintenance_source_changed', 'message': 'A bound file changed.',
                                              'effects': {'files_written': [], 'operation_created': False}}}
        return ' '.join(' '.join(refusal_lines(value, width, operation='650a1a61', verb='restore-propose')).split())

    def test_the_next_proposes_the_recorded_intents_value_not_the_originals(self):
        text = self.text()
        self.assertIn("Next: Prepare a proposal from the recorded intent (a: actions); that proposes the recorded intent's "
                      "value, not the original's, and uses nothing from the original.", text)
        self.assertNotIn('nothing from the original is used', text)

    def test_a_non_restore_refusal_keeps_its_own_next(self):
        from intune_iac.workbench_screens import refusal_lines
        value = {'status': 'error', 'error': {'code': 'maintenance_source_changed', 'message': 'A bound file changed.'}}
        text = ' '.join(' '.join(refusal_lines(value, 118, operation='650a1a61', verb='execute')).split())
        self.assertNotIn("not the original's", text)


class ReplayRefusalVerbTests(unittest.TestCase):
    """Item 11a (run11-7, frame 56): the replay refusal uses one verb, in its title and its cause."""

    def lines(self):
        from intune_iac.workbench_screens import refusal_lines
        value = {'status': 'error', 'error': {'code': 'maintenance_replay_forbidden', 'message': 'This operation is no longer '
                                              'awaiting approval: it was already dispatched, or it was rejected.',
                                              'effects': {'dispatched': False}}}
        return refusal_lines(value, 118, operation='ca165125', verb='execute')

    def test_the_title_and_the_cause_both_say_replayed(self):
        lines = self.lines()
        text = ' '.join(' '.join(lines).split())
        self.assertEqual(lines[0], '[REFUSED] This operation cannot be replayed (maintenance_replay_forbidden)')
        self.assertIn('Execution is never replayed.', text)
        self.assertNotIn('executed again', text)


class QueueNoneTests(unittest.TestCase):
    """Item 11b (run11-8, frame 47): `none` is explained where `queue-amend FILE none` is shown."""
    FINDING = {'finding': 'reporting_incomplete', 'object_id': 'o' * 8, 'priority': 'review', 'priority_rationale': 'x',
               'review_record': {'status': 'not_recorded'}}
    MEANING = 'none means this finding has no earlier review to replace'

    def test_the_queue_names_what_none_means_beside_the_command(self):
        from intune_iac.workbench_screens import queue_lines
        text = ' '.join(' '.join(queue_lines({'findings': [self.FINDING], 'scope': {}}, 118)).split())
        self.assertIn(':queue-amend FILE none', text)
        self.assertIn(self.MEANING, text)

    def test_a_finding_with_an_earlier_review_names_that_review_instead(self):
        from intune_iac.workbench_screens import queue_lines
        prior = 'f' * 64
        finding = dict(self.FINDING, review_record={'status': 'recorded', 'artifact_id': prior})
        text = ' '.join(' '.join(queue_lines({'findings': [finding], 'scope': {}}, 118)).split())
        self.assertIn(':queue-amend FILE ' + prior, text)
        self.assertNotIn(self.MEANING, text)
        self.assertIn('The last word of the second command is the earlier review it replaces.', text)

    def test_the_written_form_explains_none_too(self):
        from intune_iac.workbench_screens import review_lines
        value = {'status': 'review_form_written', 'path': '/w/queue review.json', 'finding': 'reporting_incomplete',
                 'object_id': 'o' * 8, 'expected_prior': None}
        text = ' '.join(' '.join(review_lines(value, 118)).split())
        self.assertIn("queue-amend '/w/queue review.json' none", text)
        self.assertIn(self.MEANING, text)


class SurfaceNineTests(unittest.TestCase):
    """Item 11c (run11-9): no band pointer to the surface the engineer is on."""
    CHANGED = {'area': 'repository', 'code': 'repository_stale', 'observed': 'x', 'next_step': 'y', 'evidence': {}}
    UNAVAILABLE = {'area': 'repository', 'code': 'repository_unavailable', 'observed': 'x', 'next_step': 'y', 'evidence': {}}

    def band(self, signal, **kw):
        from intune_iac.workbench_screens import hazard_rows
        return ' '.join(hazard_rows({}, [signal], 140, **kw))

    def test_on_other_surfaces_the_band_still_points_at_the_difference(self):
        self.assertIn('9: difference', self.band(self.CHANGED))
        self.assertIn('9: repository', self.band(self.UNAVAILABLE))

    def test_on_the_repository_surface_the_band_does_not(self):
        for signal in (self.CHANGED, self.UNAVAILABLE):
            band = self.band(signal, repository_here=True)
            self.assertNotIn('9:', band)
        self.assertIn('Next: Refresh the repository intent (a: actions)', self.band(self.CHANGED, repository_here=True))

    def test_the_workspace_passes_the_surface_it_draws(self):
        ws = states_tests.StateSurfaceTests.workspace(states_tests.StateSurfaceTests(), 8, {})
        ws.facts = dict(ws.facts, signals=[self.CHANGED])
        ws.stdout = type('Out', (), {'buffer': [], 'write': lambda self, text: self.buffer.append(text),
                                     'flush': lambda self: None})()
        ws.rules, ws.color = 'ascii', False
        ws.mode_class = 'synthetic'
        ws._terminal_size = lambda: (120, 40)
        ws.draw()
        drawn = ''.join(ws.stdout.buffer)
        self.assertIn('Repository changed since its intent.', drawn)
        self.assertNotIn('9: difference', drawn)


class BlockedRecoveryTests(unittest.TestCase):
    """Item 11d (gemini-run11-4, frame 80): a blocked entry that names another action says where it is."""

    def text(self):
        from intune_iac.workbench_screens import actions_lines
        entry = {'kind': 'propose-from-intent', 'label': 'Prepare a proposal from the recorded intent', 'command': 'x', 'cursor': None,
                 'needs': [], 'summary': 'S.', 'effects': 'E.', 'available': False, 'binding': {},
                 'blocked': {'code': 'workbench_desired_capability', 'message': 'The reference component cannot propose it.'}}
        return ' '.join(' '.join(actions_lines([entry], 0, 118)).split())

    def test_the_entry_says_where_refresh_appears_and_that_it_is_itself_the_proposal(self):
        text = self.text()
        self.assertIn("Change that setting in the repository's stack input to a supported value.", text)
        self.assertIn('Once the repository reads as changed, this list offers Refresh the repository intent; after it, this '
                      'entry, Prepare a proposal from the recorded intent, can be staged.', text)
        self.assertNotIn('then Refresh the repository intent and Prepare', text)
        self.assertNotIn('(a: actions)', text)


class StripKeyTests(MapTruth):
    """Item 12: wherever the strip shows an abbreviated width form, the same screen defines it once: in the pinned legend
    row where the screen has one (the map), otherwise on a row above the key line, at 40x12, 60x20 and 80x24."""
    SIZES = ((40, 12), (60, 20), (80, 24))
    WIDER = ((100, 30), (110, 30), (120, 40))  # frame 19: OP verified is shown at 120x40 too
    BATTERY = (
        {'operation': 'succeeded_verified', 'observation': 'fresh', 'repository': 'current'},
        {'operation': 'outcome_unknown', 'observation': 'source changed', 'repository': 'current'},
        {'operation': 'reconciled', 'observation': 'stale (later collection incomplete)', 'repository': 'not checked'},
        {'operation': 'held', 'observation': 'age unknown (stamped ahead)', 'repository': 'recorded_intent_not_revalidated'},
        {'operation': 'unreadable', 'observation': 'fresh', 'repository': 'desired_state_observed'},
        {'operation': 'succeeded_verified', 'observation': 'source changed', 'repository': 'current'})
    # The form as the strip spells it, and the definition the screen must carry once.
    FORMS = (
        (r'\| T [0-9a-f]{8}', 'T = tenant'), (r'\| P [0-9a-f]{8}', 'P = policy'),
        # Run 12 item 6: the rows carry meanings (STRIP_DEFINITIONS); this test checks where they stand, not their words.
        (r'OP (?:[0-9a-f]{8} )?verified\b', STRIP_DEFINITIONS['succeeded_verified']),
        (r'OP (?:[0-9a-f]{8} )?unknown\b', STRIP_DEFINITIONS['outcome_unknown']),
        (r'REPO unchecked', STRIP_DEFINITIONS['not checked']),
        (r'REPO not revalidated', STRIP_DEFINITIONS['recorded_intent_not_revalidated']),
        (r'REPO observed', STRIP_DEFINITIONS['desired_state_observed']),
        (r'OBS age\?', STRIP_DEFINITIONS['age unknown']),
        (r'OBS stale(?! \()', STRIP_DEFINITIONS['stale (later collection incomplete)']))

    def screen(self, size, facts, tab=1):
        ws = self.workspace(size, tab=tab, facts=dict({'object_id': self.object_id, 'name': 'Windows Privacy Pilot'}, **facts))
        rows = self.plain(ws)
        return rows, '\n'.join(rows)

    def test_every_abbreviated_form_on_the_strip_is_defined_once_on_its_screen(self):
        import re
        seen = set()
        for size in self.SIZES + self.WIDER:
            for facts in self.BATTERY:
                rows, text = self.screen(size, facts)
                strip = rows[2]
                for pattern, meaning in self.FORMS:
                    if re.search(pattern, strip):
                        if meaning == STRIP_DEFINITIONS['age unknown'] and 'stamped' in facts['observation']:
                            meaning = STRIP_DEFINITIONS['age unknown (stamped ahead)']  # the same word, its own row
                        seen.add(meaning)
                        self.assertEqual(text.count(meaning), 1, (size, facts, strip, meaning, rows))
                        self.assertNotIn(meaning, strip)
        # The battery reached the width forms the brief names, at the sizes it names.
        for meaning in ('T = tenant', 'P = policy', STRIP_DEFINITIONS['succeeded_verified'], STRIP_DEFINITIONS['outcome_unknown']):
            self.assertIn(meaning, seen)

    def test_a_strip_with_no_abbreviated_form_carries_no_key(self):
        rows, text = self.screen((140, 40), self.BATTERY[1])
        self.assertNotIn(' = tenant', text)
        self.assertNotIn(STRIP_DEFINITIONS['outcome_unknown'], text)

    def test_the_map_screen_defines_them_in_its_pinned_legend_row(self):
        checked = 0
        for size in ((80, 24), (100, 30)):
            rows, text = self.screen(size, self.BATTERY[1], tab=2)
            if 'OP unknown' not in rows[2]:
                continue
            checked += 1
            meaning = STRIP_DEFINITIONS['outcome_unknown']
            self.assertEqual(text.count(meaning), 1, rows)
            holder = next(row for row in rows if meaning in row)
            self.assertTrue(holder.startswith('│'), holder)  # inside the frame, with the map's legend
            self.assertNotIn(meaning, rows[-1] + rows[-2])
            legend = rows.index(holder)
            self.assertTrue(any('focus' in row for row in rows[legend - 3:legend + 1]), rows[legend - 3:legend + 1])
        self.assertGreaterEqual(checked, 1)

    def test_every_definition_fits_the_window_whole(self):
        from intune_iac.workbench_tui import cell_width
        for size in self.SIZES:
            for facts in self.BATTERY:
                rows, _ = self.screen(size, facts)
                for row in rows:
                    self.assertLessEqual(cell_width(row), size[0], (size, row))


class ConstrainedStripKeyTests(unittest.TestCase):
    """Item 12: below the minimum the abbreviated forms are defined too, in what room the window leaves."""

    def rows(self, width, height):
        from intune_iac.workbench_screens import constrained_rows
        facts = {'name': 'P', 'operation': 'outcome_unknown', 'observation': 'fresh', 'repository': 'current'}
        lines, _ = constrained_rows(TENANT, OBJECT, facts, 'synthetic', width, height, '40x12', 'Ready.')
        return lines

    def test_the_forms_the_window_shows_are_defined_once(self):
        lines = self.rows(36, 10)
        text = '\n'.join(lines)
        self.assertIn('T 11111111', text)
        for meaning in ('T = tenant', 'P = policy'):
            self.assertEqual(text.count(meaning), 1, lines)

    def test_the_definitions_give_way_before_the_hazard_when_rows_run_out(self):
        lines = self.rows(36, 5)
        self.assertEqual(len(lines), 5)
        self.assertNotIn('= tenant', '\n'.join(lines))
        self.assertTrue(any(line.startswith('!') for line in lines), lines)


class StripMarkerTests(MapTruth):
    """Item 13: a strip that leaves segments out to fit ends with how many, and the key that shows them in full."""
    FACTS = {'name': 'Windows Privacy Pilot', 'observation': 'source changed', 'repository': 'current',
             'operation': 'outcome_unknown'}
    MARKER = r'\+(\d+) more: \?'

    def strip(self, width, facts=None):
        from intune_iac.workbench_screens import context_strip
        return context_strip(TENANT, OBJECT, dict(facts or self.FACTS, object_id=OBJECT), width, 'synthetic')

    def segments(self, text):
        import re
        return len(re.findall(r'\b(?:OBS|REPO|OP) ', text))

    def test_a_strip_that_drops_segments_ends_with_the_count_and_the_key(self):
        import re
        for width in range(48, 100):
            text = self.strip(width)
            marker = re.search(self.MARKER + '$', text)
            shown = self.segments(text)
            self.assertEqual(bool(marker), shown < 3, (width, text))
            if marker:
                self.assertEqual(int(marker.group(1)), 3 - shown, (width, text))
                self.assertTrue(text.endswith(' | ' + marker.group(0)), text)

    def test_the_same_wording_at_every_width_that_truncates(self):
        import re
        wording = {re.sub(r'\d+', 'N', re.search(self.MARKER, self.strip(width)).group(0))
                   for width in range(48, 100) if re.search(self.MARKER, self.strip(width))}
        self.assertEqual(wording, {'+N more: ?'})

    def test_a_strip_that_holds_every_segment_has_no_marker(self):
        self.assertNotIn('more: ?', self.strip(140))
        self.assertEqual(self.segments(self.strip(140)), 3)

    def test_nothing_is_dropped_without_the_marker_on_the_screen_at_60x20_and_40x12(self):
        import re
        from intune_iac.workbench_tui import cell_width
        for size in ((60, 20), (40, 12)):
            ws = self.workspace(size, tab=1, facts=dict(self.FACTS, object_id=self.object_id))
            rows = self.plain(ws)
            self.assertTrue(all(cell_width(row) <= size[0] for row in rows), (size, rows))
            strip_rows = [row for row in rows[2:5] if row.strip().startswith('SYNTHETIC') or 'more: ?' in row]
            text = ' '.join(row.strip() for row in strip_rows)
            marker = re.search(self.MARKER, text)
            self.assertIsNotNone(marker, (size, rows[:6]))
            self.assertEqual(int(marker.group(1)), 3 - self.segments(text), (size, text))

    def test_the_marker_is_not_cut_off_where_the_identities_fill_the_row(self):
        # 40 columns: the mode, the tenant and the policy fill the row, so the marker takes the row under it.
        from intune_iac.workbench_screens import strip_rows
        text = self.strip(40)
        rows = strip_rows(text, 40)
        self.assertEqual(len(rows), 2, rows)
        self.assertTrue(rows[0].startswith('SYNTHETIC | T '), rows)
        self.assertRegex(rows[1], r'^\+3 more: \?$')

    def test_the_help_key_prints_the_line_in_full(self):
        from intune_iac.workbench_screens import help_lines, strip_choice
        full = strip_choice(TENANT, OBJECT, dict(self.FACTS, object_id=OBJECT), 400, 'synthetic')[0]
        text = ' '.join(' '.join(help_lines(60, strip=full)).split())
        self.assertIn(' '.join(full.split()), text)
        self.assertIn('+N more: ?', text)
        ws = self.workspace((60, 20), tab=7, facts=dict(self.FACTS, object_id=self.object_id),
                            value={'navigation': []})
        shown = ' '.join(' '.join(ws._surface_summary(56)).split())
        self.assertIn('Line now SYNTHETIC | TENANT 029c33b1 | POLICY Windows Privacy Pilot (d665d54b) | OBS source changed | '
                      'REPO current | OP outcome unknown', shown)
