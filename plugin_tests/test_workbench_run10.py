"""PKG-PRES-RUN10 (journey 29 run 6 and journey 28 run 10 frame reviews): what the screens say, not what the product decides.

Item 1: the typed tree's header counts as the map's header does, from one function.
Item 2: the companion entry, its long text and the page name the command one way, in the product's own flags.
Item 3: at 60x20 the key line names the way to move the focus and the legend defines the no-state word.
Item 4: the typed tree's wrapped identifier sits under its column; a filter note reads as part of its row.
Items are added below in the order of the brief; each class names its item.
Temporary directories only.
"""
import re
import unittest

from plugin_tests import test_workbench_companion as companion_tests
from plugin_tests import test_workbench_states as states_tests
from plugin_tests.test_workbench_map_truth import MARK, MapTruth
from plugin_tests.test_workbench_run9 import CommandRows, text_of

GENERATED = {'relation': 'generated_from', 'target_id': '/home/nsahm/work/journey 29/generated/22222222-2222-4222-8222-222222222222.tf',
             'details': {}, 'assertion_class': 'historical_local_adoption'}


class TreeCountTests(MapTruth):
    def tree_header(self, value, width=100, rules='unicode'):
        from intune_iac.workbench_screens import relationship_lines
        return next(line for line in relationship_lines(value, width, rules) if '| coverage' in line)

    def test_the_tree_header_reads_as_the_map_header_does(self):
        from intune_iac.graph_projection import count_words
        with_file = dict(self.value, relationships=self.value['relationships'] + [GENERATED])
        for value in (self.value, with_file, dict(self.value, selected_repository=None),
                      dict(self.value, relationships=[], selected_repository=None),
                      dict(self.value, relationships=self.value['relationships'][:1], selected_repository=None)):
            words = count_words(self.graph(value))
            self.assertTrue(self.tree_header(value).startswith(words + ' | coverage'), (self.tree_header(value), words))

    def test_a_listed_repository_is_not_counted_as_an_edge(self):
        header = self.tree_header(self.value)
        self.assertTrue(header.startswith('7 relationships, 1 repository | coverage'), header)
        self.assertNotIn(' edges', header)
        self.assertNotIn(' edge ', header)

    def test_the_header_agrees_with_the_rows_the_tree_lists(self):
        from intune_iac.workbench_screens import relationship_lines
        lines = relationship_lines(self.value, 100, 'unicode')
        rows = [line for line in lines if line.lstrip(' │').startswith(('├', '└')) and ' writer ' not in line]
        self.assertEqual(len(rows), 7 + 1)
        self.assertIn('7 relationships, 1 repository', next(line for line in lines if '| coverage' in line))


WRITE_COMMAND = 'intune-iac workbench companion --root STORE --object ID --out FILE'


class CompanionWordingTests(companion_tests.Fixture):
    """Item 2: the focused companion entry, its long text and the page name the command one way, in the product's flags."""

    def entry(self):
        from intune_iac.workbench import _inspection, _store
        from intune_iac.workbench_screens import actions_lines
        actions = _inspection(_store(self.root), self.object_id, attention=True)['actions']
        last = len(actions) - 1
        rows = [line.strip() for line in actions_lines(actions, last, 116, name='Privacy pilot 3', object_id=self.object_id)]
        return actions[last], ' '.join(' '.join(rows).split())

    def test_the_entry_names_the_command_in_the_products_flags(self):
        action, rendered = self.entry()
        self.assertEqual(action['kind'], 'companion')
        self.assertIn(WRITE_COMMAND, rendered)
        self.assertIn('--serve', rendered)
        self.assertNotIn('"companion serve"', rendered)

    def test_the_address_is_printed_by_the_product_not_supplied(self):
        action, rendered = self.entry()
        self.assertRegex(rendered, r'--serve[^.]*prints? (the|its) (secret )?address')
        need = action['needs'][0]
        self.assertTrue(need.startswith('FILE:'), need)
        self.assertNotIn('serve', need)
        self.assertNotIn('loopback', need)
        self.assertRegex(need, r'you supply (it|the path)')
        self.assertIn('not an address', need)

    def test_the_page_names_the_same_command_and_where_the_address_comes_from(self):
        from intune_iac.companion_page import render_page
        from intune_iac.graph_projection import project
        html = render_page(project(self.value, freshness='fresh'), mode_class='synthetic_local_process_only')
        page = ' '.join(re.sub(r'<[^>]+>', ' ', re.sub(r'(?s)<(script|style).*?</\1>', ' ', html)).split())
        self.assertIn(WRITE_COMMAND, page)
        self.assertIn('workbench companion --root STORE --object ID --serve', page)
        self.assertNotIn('the same workbench companion command', page)
        self.assertRegex(page, r'--serve[^.]*prints? (the|its) (secret )?address')


class NarrowMapTests(MapTruth):
    """Item 3: at 60x20 the key line names a key that moves the focus and the legend defines the no-state word."""

    def narrow(self, size=(60, 20), rules="unicode", hscroll=0):
        ws = self.workspace(size, rules=rules)
        ws.hscroll = hscroll
        return MapTruth.plain(self, ws)

    def test_the_key_line_at_60x20_names_the_way_to_move_the_focus(self):
        for hscroll in (0, 8):
            line = self.narrow(hscroll=hscroll)[-1]
            for key in ('? help', 'a actions', 'Up/Down', 'Left/Right', 'Enter', 'q exit'):
                self.assertIn(key, line, (hscroll, line))
            self.assertLessEqual(len(line), 60)

    def test_a_key_is_named_only_where_it_works(self):
        from intune_iac.workbench_tui import help_line
        for inspect in (True, False):
            for pan in (True, False):
                line = help_line(60, map_keys=True, inspect=inspect, pan=pan)
                self.assertIn('Up/Down', line)
                self.assertIn('a actions', line)
                self.assertEqual('Enter' in line, inspect, (inspect, pan, line))
                self.assertEqual('Left/Right' in line, pan, (inspect, pan, line))

    def test_the_legend_at_60x20_defines_the_word_its_rows_show(self):
        for rules, word in (('unicode', '—'), ('ascii', 'n/a')):
            # Panned until the state column is in view: the rows show the word the legend must define.
            rows = [row.strip('│| ').rstrip() for row in self.narrow(rules=rules, hscroll=12)]
            self.assertTrue(any(row.endswith(' ' + word) for row in rows), (rules, rows))
            legend = next(row for row in rows if '> focus * selected' in row)
            self.assertIn('%s means no state' % word, legend, rules)
            self.assertIn('? help', legend)


class FilterBlockTests(MapTruth):
    """Item 4: a wrapped identifier sits under the column it continues; a filter note reads as part of the row above."""

    CONNECTORS = ('├', '└', '|-', '`-')

    def tree(self, width, rules):
        from intune_iac.workbench_screens import relationship_lines
        return relationship_lines(self.value, width, rules)

    def continuations(self, lines):
        """(row above, continuation) pairs: a continuation has the rail but no connector of its own."""
        found = []
        for above, line in zip(lines, lines[1:]):
            if (above.startswith('  ') and any(mark in above[:9] for mark in self.CONNECTORS) and line.startswith('  ')
                    and not any(mark in line[:9] for mark in self.CONNECTORS) and line.strip(' │|')):
                found.append((above, line))
        return found

    def test_a_wrapped_identifier_is_indented_under_the_column_it_continues(self):
        for rules in ('unicode', 'ascii'):
            seen = 0
            for width in (60, 80, 100):
                for above, line in self.continuations(self.tree(width, rules)):
                    seen += 1
                    target = above.index('Unresolved') if 'Unresolved' in above else None
                    if target is None:
                        continue
                    start = len(line) - len(line.lstrip(' │|'))
                    self.assertEqual(start, target, (rules, width, above, line))
            self.assertGreater(seen, 2, rules)

    def test_the_wrap_keeps_every_identifier_whole(self):
        identifier = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
        for rules in ('unicode', 'ascii'):
            wide = identifier.findall(' '.join(self.tree(200, rules)))
            self.assertGreater(len(wide), 5)
            for width in (60, 100):
                self.assertEqual(identifier.findall(' '.join(self.tree(width, rules))), wide, (rules, width))

    def test_a_filter_note_reads_as_part_of_the_row_above(self):
        for rules in ('unicode', 'ascii'):
            _, rows = self.rows(self.graph(freshness='fresh'), rules=rules)
            text = [row.rstrip() for row in rows]
            notes = [row for row in text if 'applies to b564fc9a' in row or '+ filter 5aa36291 include' in row]
            self.assertEqual(len(notes), 2, rules)
            for note in notes:
                body = note.lstrip(' │|').rstrip()
                self.assertTrue(body.startswith('(') and body.endswith(')'), (rules, note))
            index = next(i for i, row in enumerate(text) if 'filter 5aa36291' in row and MARK.search(row))
            self.assertIn('(applies to b564fc9a)', text[index + 1], rules)


class DeliveryFirstActionTests(unittest.TestCase):
    """Item 5: with a deployment record available and a stale observation, the band, the body and the list agree on one
    first action, and say the order: record the deployment, then collect."""

    RECORD = {'kind': 'deployment-record', 'available': True}
    COLLECT = {'kind': 'collect', 'available': True}
    # The band's collect-again findings by the evidence that makes them: (eligibility or signal, its code, its evidence).
    CASES = (('eligibility', 'service_changed', {'observed_revision': 1, 'service_revision': 2}),
             ('eligibility', 'policy_changed', {}),
             ('eligibility', 'source_mismatch', {}),
             ('signal', 'observation_stale', {'freshness_reasons': ['older_than_window']}),
             ('signal', 'collection_failed', {'status': 'failed'}),
             ('signal', 'collection_not_finished', {}),
             ('signal', 'observation_stale', {'freshness_reasons': ['stamped_after_now'], 'collect_cures': True}))

    def band(self, case, width, actions=True):
        from intune_iac.workbench_screens import hazard_rows
        kind, code, evidence = case
        facts = {'object_id': 'o', 'actions': [self.RECORD, self.COLLECT] if actions else [self.COLLECT]}
        signals = []
        if kind == 'eligibility':
            facts['eligibility'] = dict(evidence, reason=code, code='maintenance_observation_stale')
        else:
            signals = [{'area': 'freshness', 'code': code, 'evidence': evidence}]
        return ' '.join(' '.join(hazard_rows(facts, signals, width)).split())

    def test_the_band_names_the_deployment_record_before_the_collection_at_every_width(self):
        for case in self.CASES:
            for width in (140, 120, 100, 80, 60, 40):
                text = self.band(case, width)
                self.assertRegex(text, r'Record the deployment, then collect', (case, width, text))
                self.assertNotIn('then collection', text)

    def test_without_a_record_the_band_is_unchanged(self):
        for case in self.CASES:
            for width in (120, 80, 60):
                text = self.band(case, width, actions=False)
                self.assertNotIn('Record', text, (case, width))
                self.assertIn('ollect', text, (case, width))

    def test_the_body_says_the_same_order(self):
        from plugin_tests.test_workbench_run9 import next_step
        step = next_step(record={'status': 'available', 'intent_id': 'a' * 64})
        first = step.split('\n')[0]
        self.assertRegex(first, r'^Record the deployment \(a lists it\), then collect', first)
        self.assertIn('deployment-record /w/op ' + 'a' * 64, step)

    def test_the_body_names_no_collection_where_none_follows(self):
        from intune_iac.workbench_delivery import _next_action
        stages = {'proposal': {}, 'approval': {'status': 'done'}, 'readback': {'status': 'done'},
                  'reconciliation': {'status': 'not_needed'}, 'deployment_record': {'status': 'available', 'intent_id': 'a' * 64},
                  'observed_after': {'status': 'differs'}}
        self.assertNotIn('collect', _next_action(stages, '/w/op', '/w/store').split('\n')[0])

    def test_the_actions_list_puts_the_record_before_the_collection(self):
        from unittest import mock
        from intune_iac import workbench
        from plugin_tests import test_workbench_repository as repository_tests
        case = type('Case', (unittest.TestCase,), {'setUp': repository_tests.RepositoryOwnedChangeTests.setUp,
                                                   'runTest': lambda self: None})('runTest')
        case.setUp()
        try:
            record = {'operation_id': 'f' * 32, 'operation_root': case.root / 'operation', 'intent_id': 'a' * 64}
            attention = {'status': 'ok', 'checked': {},
                         'signals': [{'area': 'freshness', 'code': 'observation_stale',
                                      'evidence': {'freshness_reasons': ['older_than_window']}}]}
            with mock.patch.object(workbench, '_record_offer', return_value=record):
                actions = workbench._actions(case.store, repository_tests.OBJECT, attention, None, case.service.root)
            kinds = [action['kind'] for action in actions]
            self.assertIn('collect', kinds)
            self.assertLess(kinds.index('deployment-record'), kinds.index('collect'), kinds)
        finally:
            case.doCleanups()


OPERATION_DIRECTORY = '/w/journey 28 run 10/operation-22222222-132179e8da71'


class PlanDirectoryTests(CommandRows, unittest.TestCase):
    """Item 6: the plan review prints the operation's directory and the execute row carries the real path."""
    surface = states_tests.RefusalCauseTests.workspace

    def review(self, **kw):
        import time
        value = {'operation_id': 'f728f2751b5c4009bd8b28a5af2f5fc6', 'operation_root': OPERATION_DIRECTORY,
                 'object_id': states_tests.OBJECT, 'tenant_id': states_tests.TENANT, 'status': 'prepared',
                 'approval_digest': 'd' * 64, 'saved_plan_sha256': 'b' * 64, 'expires_at': time.time() + 200,
                 'evidence_class': 'synthetic_local_process_and_modeled_service_only'}
        return dict(value, **kw)

    def rows(self, value, width=118):
        workspace = self.surface()
        workspace.tab, workspace.value = 4, value
        return workspace._summary_lines(width)

    def test_the_plan_review_prints_the_operation_directory(self):
        for width in (80, 118):
            text = text_of(self.rows(self.review(), width))
            self.assertIn("Operation directory: '%s'" % OPERATION_DIRECTORY, text, width)

    def test_the_execute_row_carries_the_real_path_alone(self):
        for width in (80, 118):
            rows = self.rows(self.review(), width)
            self.assert_command_alone(rows, "execute '%s' DIGEST" % OPERATION_DIRECTORY)
            self.assertNotIn('OPERATION_DIR', text_of(rows), width)

    def test_a_path_with_a_line_break_cannot_start_a_row_of_its_own(self):
        rows = self.rows(self.review(operation_root='/w/op\n  rm -rf /'))
        self.assertEqual([row for row in rows if row.lstrip().startswith('rm -rf')], [])

    def test_a_review_without_a_directory_keeps_the_template_and_prints_no_row(self):
        value = self.review()
        del value['operation_root']
        rows = self.rows(value)
        self.assertNotIn('Operation directory', text_of(rows))
        self.assert_command_alone(rows, 'execute OPERATION_DIR DIGEST')


class NoChangePlanTests(CommandRows, unittest.TestCase):
    """Item 7: a no-change plan's Next says what executing it does, as the code does it."""
    review = PlanDirectoryTests.review

    def no_change(self, **kw):
        return self.review(changes=[], no_configuration_change=True, field_changes={'status': 'no_change', 'changes': []}, **kw)

    def next_text(self, value, width=118):
        return ' '.join(' '.join(lifecycle_rows(value, width)).split())

    def test_the_next_does_not_say_approve_and_run_it(self):
        for value in (self.no_change(), self.review(changes=[])):
            text = self.next_text(value)
            self.assertNotIn('approve and run it', text)
            self.assertIn('Next: Nothing to apply: the desired body equals the observed body.', text)
            self.assertIn('sends no change to the service', text)
            self.assertIn('with the review digest', text)

    def test_the_command_row_is_still_alone_with_the_real_path(self):
        for width in (80, 118):
            self.assert_command_alone(lifecycle_rows(self.no_change(), width), "execute '%s' DIGEST" % OPERATION_DIRECTORY)

    def test_a_plan_with_a_change_is_unchanged(self):
        text = self.next_text(self.review(changes=['description'], no_configuration_change=False))
        self.assertIn('Next: approve and run it with the review digest (6 Execution shows the result). In the workspace:', text)  # run 12 item 3

    def test_the_words_are_what_executing_a_no_change_plan_does(self):
        # The code's own answer: a real no-change proposal executes without sending anything and reads the service back.
        from intune_iac import maintenance
        from intune_iac.workbench_repository import propose_from_intent
        from plugin_tests import test_workbench_repository as repository_tests
        owner = repository_tests.RepositoryOwnedChangeTests
        case = type('Case', (unittest.TestCase,), {'setUp': owner.setUp, 'import_intent': owner.import_intent,
                                                   'RESOURCE_ADDRESS': owner.RESOURCE_ADDRESS,
                                                   'runTest': lambda self: None})('runTest')
        case.setUp()
        try:
            case.import_intent()
            operation = case.root / 'operation'
            review = propose_from_intent(case.store.root, case.service.root, repository_tests.OBJECT, operation)
            self.assertEqual(maintenance.review(operation)['no_configuration_change'], True, review)
            result = maintenance.execute(operation, approve_digest=review['approval_digest'])
            self.assertEqual(result['status'], 'succeeded_verified')
            self.assertEqual(result['effects'], {'dispatched': True, 'service_change': 'no_change_needed'})
            events = [event['kind'] for event in maintenance._load(operation)[2]['events']]
            self.assertIn('service_no_change', events)
            self.assertNotIn('service_response', events)
        finally:
            case.doCleanups()


def lifecycle_rows(value, width):
    from intune_iac.workbench_screens import lifecycle_lines
    return lifecycle_lines(4, width, value)


PREPARE = 'Prepare a proposal from the recorded intent'
PREPARE_FROM_FILE = 'Prepare a local proposal from a desired file'


class CanonicalNameTests(unittest.TestCase):
    """Item 8: an action has one name, the actions list's own, wherever it is named; one verb for "never replays"."""

    MODULES = ('workbench_screens', 'workbench_tui', 'workbench', 'workbench_delivery')
    # Names the one action went by in run 10 (frames 65 to 73) and the verbs that said "replay" another way.
    VARIANTS = (r'(?i)prepare (a |the )?(new )?proposal again', r'(?i)\bprepare again\b', r'(?i)\bprepare a new proposal',
                r'(?i)\ba new proposal\b', r'for the value you want', r'Prepare a proposal \(a', r'Prepare a proposal from the recorded repository intent',
                r'(?i)repeats? the change', r'(?i)repeating the change')

    def source(self, module):
        from pathlib import Path
        return (Path(__file__).resolve().parents[1] / 'intune_iac' / (module + '.py')).read_text(encoding='utf-8')

    def test_no_module_names_the_action_by_another_name_or_says_repeat(self):
        for module in self.MODULES:
            source = self.source(module)
            for variant in self.VARIANTS:
                self.assertEqual([found.group(0) for found in re.finditer(variant, source)], [], (module, variant))

    def test_the_label_the_actions_list_offers_is_the_name_used(self):
        source = self.source('workbench')
        self.assertIn("offer('propose-from-intent', '%s'," % PREPARE, source)
        self.assertIn("offer('propose', '%s'," % PREPARE_FROM_FILE, source)

    def test_every_proposal_a_refusal_table_tells_the_engineer_to_prepare_has_the_list_name(self):
        from intune_iac import workbench_screens as screens
        texts = [part for pair in screens.REFUSALS.values() for part in pair]
        texts += [part for triple in screens.RESTORE_REFUSALS.values() for part in triple] + list(screens.KNOWN_NEXT.values())
        found = [match for text in texts for match in re.findall(r'(?i)prepare (?:a|the|it)\b[^.;(]*proposal[^.;(]*', text)]
        self.assertTrue(found)
        for match in found:
            self.assertTrue(match.startswith(PREPARE), match)

    def test_the_lifecycle_the_band_and_delivery_say_the_list_name(self):
        import time
        from intune_iac.workbench_delivery import _next_step
        from intune_iac.workbench_screens import hazard_rows, lifecycle_next
        closed = {'operation_id': 'a' * 32, 'status': 'prepared', 'expires_at': time.time() - 5}
        self.assertEqual(lifecycle_next(4, closed, time.time()),
                         PREPARE + ' (a: actions); Expiry and Approval window above say why')
        changed = {'operation_id': 'a' * 32, 'status': 'prepared', 'repository': {'cited': None, 'context_changed': True}}
        self.assertEqual(lifecycle_next(4, changed, 0), PREPARE + ' (a: actions)')
        facts = {'object_id': 'o', 'operation': 'prepared', 'operation_id': 'a' * 32,
                 'signals': [{'area': 'operations', 'code': 'operation_approval_held', 'evidence': {'operation_id': 'a' * 32}}]}
        band = ' '.join(' '.join(hazard_rows(facts, facts['signals'], 140)).split())
        self.assertIn('Wait, or ' + PREPARE + ' (a: actions)', band)
        stages = {'proposal': {}, 'approval': {'status': 'expired', 'closes_at': 1}, 'readback': {'status': 'not_yet'},
                  'reconciliation': {'status': 'not_needed'}, 'deployment_record': {'status': 'not_yet'},
                  'observed_after': {'status': 'not_yet'}}
        self.assertTrue(_next_step(stages, '/w/op', '/w/store').startswith(PREPARE + ' (a: actions);'))

    def test_one_verb_says_the_change_is_never_replayed(self):
        from intune_iac.workbench_screens import EXECUTION_EFFECTS, execution_effect_lines
        from intune_iac.workbench_tui import STAGED_BOUNDARY
        self.assertIn('without replaying the change', EXECUTION_EFFECTS['unknown'])
        self.assertTrue(all('replays the change' in text for text in STAGED_BOUNDARY['reconcile']))
        reconciled = execution_effect_lines({'effects': {'replayed': False}}, 118)
        self.assertEqual(' '.join(reconciled), 'Effect: Reconcile read the service and recorded what it found; it did not replay the change.')


def action(kind, label, available=True, **extra):
    blocked = None if available else {'code': 'workbench_desired_capability', 'message': 'The reference component cannot propose it.'}
    return dict({'kind': kind, 'label': label, 'command': kind + ' ', 'cursor': None, 'needs': [], 'summary': 'A summary.',
                 'effects': 'More than the summary.', 'available': available, 'blocked': blocked, 'binding': {}}, **extra)


class ActionsOverlayTests(MapTruth):
    """Item 9: inside the actions list the band names an entry, not a key that is not there, and a blocked focused entry
    does not offer Enter to stage it."""

    ENTRIES = (action('collect', 'Collect again', command='collect'),
               action('propose-from-intent', PREPARE, available=False),
               action('companion', 'Write the read-only isometric page for this policy'))

    def listed(self, focus=0, size=(120, 40)):
        ws = self.workspace(size)
        ws.facts.update(actions=list(self.ENTRIES),
                        eligibility={'code': 'maintenance_observation_stale', 'reason': 'service_changed',
                                     'observed_revision': 1, 'service_revision': 2})
        ws._open_actions()
        ws.action_focus = focus
        return ws

    def band(self, ws):
        return next(row for row in self.plain(ws) if row.startswith('!')).strip()

    def test_the_band_inside_the_list_names_the_entry_not_the_key(self):
        ws = self.listed()
        band = self.band(ws)
        self.assertIn('Next: Collect again', band)
        self.assertNotIn('(a: actions)', band)
        self.assertIn('(entry 1)', band)
        ws.layer = 'summary'
        self.assertIn('(a: actions)', self.band(ws))

    def test_the_entry_is_the_one_the_list_numbers(self):
        for entries, expected in (((self.ENTRIES[1], self.ENTRIES[0]), '(entry 2)'), ((self.ENTRIES[2],), None)):
            ws = self.listed()
            ws.facts['actions'] = list(entries)
            band = self.band(ws)
            self.assertNotIn('(a: actions)', band)
            self.assertNotIn('(a actions)', band)
            if expected:
                self.assertIn(expected, band)
            else:
                self.assertNotIn('(entry', band)

    def test_a_blocked_focused_entry_does_not_offer_enter_to_stage_it(self):
        for focus, blocked in ((0, False), (1, True)):
            ws = self.listed(focus)
            ws.notice = ws._actions_notice()
            rows = self.plain(ws)
            self.assertEqual('Enter stages' in rows[-1], not blocked, (focus, rows[-1]))
            self.assertEqual('Enter stages' in rows[-2], not blocked, (focus, rows[-2]))
            self.assertIn('Up/Down choose', rows[-1])
            self.assertIn('Esc closes', rows[-1])

    def test_moving_the_focus_onto_a_blocked_entry_replaces_the_notice(self):
        ws = self.listed()
        self.keys(ws, ['down', ('text', 'q')])
        self.assertIn('Enter stages', ws.key_reader.notices[0])
        self.assertNotIn('Enter stages', ws.key_reader.notices[1])
        self.assertIn('blocked', ws.key_reader.notices[1])

    def test_a_blocked_reason_inside_the_list_names_no_key_that_is_not_there(self):
        from intune_iac.workbench_screens import actions_lines
        entry = action('propose-from-intent', PREPARE, available=False,
                       blocked={'code': 'workbench_desired_capability', 'message': 'The reference component cannot propose it.'})
        text = text_of(actions_lines([entry], 0, 120))
        self.assertIn('Refresh the repository intent', text)
        self.assertNotIn('(a: actions)', text)


class MoreFindingsTests(unittest.TestCase):
    """Item 10: "+N more" names what it counts and where."""

    def band(self, others, width=140, **kw):
        from intune_iac.workbench_screens import hazard_rows
        codes = ('repository_stale', 'repository_consumer_mismatch', 'collection_failed')[:others]
        signals = [{'area': 'freshness', 'code': 'observation_stale', 'evidence': {'freshness_reasons': ['older_than_window']}}] + [
            {'area': 'x', 'code': code, 'evidence': {'status': 'failed'}} for code in codes]
        return ' '.join(' '.join(hazard_rows({'object_id': 'o'}, signals, width, **kw)).split())

    def test_the_count_names_the_findings_and_the_surface_that_lists_them(self):
        self.assertIn('+1 more finding (2 Inspector)', self.band(1))
        self.assertIn('+2 more findings (2 Inspector)', self.band(2))

    def test_in_the_inspector_it_names_the_section_and_while_typing_no_surface(self):
        self.assertIn('+1 more finding in NEEDS ATTENTION', self.band(1, here=True))
        typing = self.band(1, routes=False)
        self.assertIn('+1 more finding', typing)
        self.assertNotIn('Inspector', typing)
        self.assertNotIn(': 2', typing)

    def test_the_noun_survives_every_width(self):
        for width in (140, 120, 100, 80, 60, 40):
            for others in (1, 2):
                text = self.band(others, width)
                self.assertRegex(text, r'\+%d more findings? \(2 Inspector\)' % others, (width, text))


class KeyNamesTests(unittest.TestCase):
    """Item 11: a key the body names (v, d, n, p) is in the key line or explained where it is named."""

    def unexplained(self, text):
        found = []
        for match in re.finditer(r'(?<![\w/:.-])([dvnp])(?![\w/:.-])', text):
            if not re.match(r'(shows?|opens?|to open|reads?|lists?)\b', text[match.end():].lstrip()):
                found.append(text[max(0, match.start() - 25):match.end() + 25])
        return found

    def lifecycles(self):
        import time
        from intune_iac.workbench_screens import lifecycle_lines
        now = time.time()
        prepared = {'operation_id': 'a' * 32, 'status': 'prepared', 'expires_at': now + 200}
        values = {8: ({'freshness': {'status': 'current'}}, {'freshness': {'status': 'stale'}}),
                  4: (prepared, dict(prepared, expires_at=now - 1), dict(prepared, changes=[], no_configuration_change=True),
                      dict(prepared, repository={'cited': None, 'context_changed': True})),
                  5: ({'status': 'outcome_unknown'}, {'status': 'reconciled'}, {'status': 'succeeded_verified'})}
        for tab, items in values.items():
            for value in items:
                for width in (80, 118):
                    yield tab, ' '.join(' '.join(lifecycle_lines(tab, width, value, now)).split())

    def test_the_lifecycle_line_explains_the_key_it_names(self):
        seen = 0
        for tab, text in self.lifecycles():
            seen += 1
            self.assertEqual(self.unexplained(text), [], (tab, text))
            self.assertIn('Delivery (v opens it)', text)
            self.assertNotIn('key v', text)
        self.assertGreater(seen, 10)

    def test_no_refusal_or_next_text_names_a_key_without_saying_what_it_does(self):
        from intune_iac import workbench_screens as screens
        texts = [part for pair in screens.REFUSALS.values() for part in pair]
        texts += [part for triple in screens.RESTORE_REFUSALS.values() for part in triple] + list(screens.KNOWN_NEXT.values())
        for text in texts:
            self.assertEqual(self.unexplained(text), [], text)

    def test_the_history_and_the_setting_hint_explain_n_p_and_d(self):
        from intune_iac.workbench_screens import history_lines
        value = {'object_id': 'o', 'order': 'observed_at_desc_observation_id_desc', 'pagination': {'has_more': True, 'total_observations': 3},
                 'history': [{'observed_at': '2026-10-15T10:00:00Z', 'run_id': 1, 'coverage': 'complete', 'snapshot_id': 'a' * 64, 'body': {}}]}
        text = ' '.join(' '.join(history_lines(value, 118)).split())
        self.assertIn('n shows older observations, p shows newer observations', text)
        self.assertEqual(self.unexplained(text), [], text)


class OneEffectTests(companion_tests.Fixture):
    """Item 12: a focused entry says its effect once: its long text adds to the summary and does not repeat it."""

    # Run 11 item 7 supersedes the run 10 split (a summary plus a long text that added to it): the focused entry
    # prints its one full description in place of the summary, so it is the long text that holds each claim, once.
    def test_the_focused_entry_prints_the_long_text_in_place_of_the_summary(self):
        from intune_iac.workbench import ACTION_EFFECTS, ACTION_SUMMARY
        from intune_iac.workbench_screens import actions_lines
        entry = {'kind': 'collect', 'label': 'Collect again', 'command': 'collect', 'cursor': None, 'needs': [],
                 'summary': ACTION_SUMMARY['collect'], 'effects': ACTION_EFFECTS['collect'], 'available': True,
                 'blocked': None, 'binding': {}}
        text = ' '.join(' '.join(line.strip() for line in actions_lines([entry], 0, 116)).split())
        self.assertIn(ACTION_EFFECTS['collect'], text)
        self.assertNotIn(ACTION_SUMMARY['collect'], text)

    def test_the_three_named_actions_keep_what_each_claims_in_one_place(self):
        from intune_iac.workbench import ACTION_EFFECTS
        for kind, claims in (('collect', ('collection run', 'changes no policy')),
                             ('deployment-record', ('records the deployment', 'sends nothing')),
                             ('companion', ('records nothing', 'opens no browser'))):
            for claim in claims:
                self.assertEqual(ACTION_EFFECTS[kind].lower().count(claim), 1, (kind, claim))

    def test_the_long_text_still_says_what_only_it_says(self):
        from intune_iac.workbench import ACTION_EFFECTS
        self.assertIn('denied or partial result', ACTION_EFFECTS['collect'])
        self.assertIn('context bytes its plan bound', ACTION_EFFECTS['deployment-record'])
        self.assertIn('not platform qualified', ACTION_EFFECTS['deployment-record'])
        self.assertIn('secret address', ACTION_EFFECTS['companion'])
        self.assertIn('can approve or run nothing', ACTION_EFFECTS['companion'])

    def test_the_focused_entry_prints_each_claim_once(self):
        from intune_iac.workbench import _inspection, _store
        from intune_iac.workbench_screens import actions_lines
        actions = _inspection(_store(self.root), self.object_id, attention=True)['actions']
        last = len(actions) - 1
        text = ' '.join(' '.join(line.strip() for line in actions_lines(actions, last, 116)).split()).lower()
        for claim in ('records nothing', 'opens no browser', 'opens a browser'):
            self.assertLessEqual(text.count(claim), 1, claim)


class StampTimeOnceTests(unittest.TestCase):
    """Lower weight (frame 44): the stamp time is printed once on the stamped-ahead Inspector."""
    CHECKED, STAMP = '2026-10-15T17:45:10Z', '2026-10-15T18:00:10Z'

    def screen(self):
        from intune_iac.workbench_diagnostics import _freshness
        from intune_iac.workbench_screens import _attention_lines, state_lines
        signals, _ = _freshness({'observed_at': self.STAMP, 'freshness': 'stale', 'freshness_reasons': ['stamped_after_now'],
                                 'freshness_checked_at': self.CHECKED, 'snapshot_id': 'b' * 64,
                                 'next_collection_replaces': 'same_service', 'ordering_service_root': '/w/service'}, False)
        observation = {'evidence_class': 'synthetic', 'run_id': 5, 'observed_at': self.STAMP, 'coverage': 'complete',
                       'freshness': 'stale', 'freshness_reasons': ['stamped_after_now'],
                       'freshness_checked_at': self.CHECKED, 'eligibility': None}
        signal = dict(signals[0], evidence=dict(signals[0]['evidence'], collect_cures=True))
        state = state_lines({'observation': observation}, 118)
        attention = _attention_lines({'attention': {'signals': [signal], 'checked': {}}, 'actions': [],
                                      'states': {'observation': observation}}, 118)
        return text_of(state), text_of(attention)

    def test_the_stamp_time_is_printed_once(self):
        state, attention = self.screen()
        self.assertEqual((state + ' ' + attention).count('18:00:10'), 1, (state, attention))
        self.assertIn('2026-10-15 18:00:10 UTC', state)
        self.assertEqual((state + ' ' + attention).count('17:45:10'), 1)

    def test_the_state_row_still_says_the_reason_and_the_clock_reading(self):
        state, attention = self.screen()
        self.assertIn("age not known (stamped after this host's clock: this host's clock read 2026-10-15 17:45:10 UTC)", state)
        self.assertIn('The newest observation is not known to be fresh.', attention)


class OneNounTests(unittest.TestCase):
    """Lower weight (frame 67): stage 7 shows the record id and the screen says record, not receipt, for the deployment."""
    NOUNS = (r'(?i)deployment receipt', r'(?i)\blocal receipt', r'(?i)a receipt in this store', r'The receipt is a verified')

    def test_stage_7_shows_the_record_id_the_notice_and_the_panel_print(self):
        from intune_iac.workbench_screens import delivery_lines
        from plugin_tests.test_workbench_screens import delivery_value
        text = text_of(delivery_lines(delivery_value(deployment_record={'artifact_id': '4679402135fd' + '0' * 52}), 140))
        self.assertIn('7 Deployment recorded 2026-10-14 12:25:00 UTC | record 4679402135fd | intent', text)

    def test_stage_7_without_an_id_is_unchanged(self):
        from intune_iac.workbench_screens import delivery_lines
        from plugin_tests.test_workbench_screens import delivery_value
        text = text_of(delivery_lines(delivery_value(), 140))
        self.assertNotIn('| record ', text)

    def test_the_notice_the_refusal_effect_and_the_action_say_record(self):
        from intune_iac.workbench import ACTION_EFFECTS, ACTION_SUMMARY
        from intune_iac.workbench_screens import refusal_lines
        from intune_iac.workbench_tui import STAGED_BOUNDARY
        workspace = states_tests.RefusalCauseTests.workspace(states_tests.RefusalCauseTests(), {}, 'deployment-record /w/op ' + 'a' * 64)
        notice = workspace._notice_for({'artifact_id': '4679402135fd' + '0' * 52, 'kind': 'deployment_receipt', 'created': True})
        self.assertEqual(notice, 'deployment-record recorded deployment record 4679402135fd.')
        value = {'status': 'error', 'error': {'code': 'workbench_deployment_intent_not_cited', 'message': 'x',
                                              'effects': {'deployment_recorded': False}}}
        self.assertIn('Effect: No deployment record was made.', text_of(refusal_lines(value, 118)))
        self.assertIn('Records the deployment in this store', ACTION_SUMMARY['deployment-record'])
        self.assertIn('as a verified local modeled baseline', ACTION_EFFECTS['deployment-record'])
        self.assertTrue(all('receipt' not in text for text in STAGED_BOUNDARY['deployment-record']), STAGED_BOUNDARY['deployment-record'])

    def test_no_module_says_deployment_receipt(self):
        from pathlib import Path
        for module in ('workbench_screens', 'workbench_tui', 'workbench', 'workbench_delivery'):
            source = (Path(__file__).resolve().parents[1] / 'intune_iac' / (module + '.py')).read_text(encoding='utf-8')
            for noun in self.NOUNS:
                self.assertEqual([found.group(0) for found in re.finditer(noun, source)], [], (module, noun))


class StripOperationTests(unittest.TestCase):
    """Item 10: an operation the strip shows and the screen does not discuss is named once in the body."""
    surface = states_tests.RefusalCauseTests.workspace
    STRIP = 'a23983bd3a224bd1b08d8156a67fa773'
    ABOUT = 'f728f2751b5c4009bd8b28a5af2f5fc6'

    def refusal(self, command='deployment-record /w/op %s' % ('a' * 64), about=None, status='error'):
        facts = {'states': {'operation': {'operation_id': self.STRIP, 'journal_status': 'prepared'}}}
        workspace = self.surface(facts, command)
        workspace.value = {'status': status, 'error': {'code': 'workbench_deployment_intent_not_cited', 'message': 'Refused.'}}
        workspace.known_operations = {'/w/op': about or self.ABOUT}
        return workspace

    def test_the_note_names_the_strip_operation_and_the_one_the_screen_is_about(self):
        text = ' '.join(' '.join(self.refusal()._strip_note(118)).split())
        # Run 12 item 2: the strip prints `OP prepared`, no id, so the sentence says what OP stands for.
        self.assertEqual(text, "The strip's OP prepared is operation a23983bd, the newest for this policy, not operation "
                               "f728f275, the one this screen is about.")

    def test_no_note_where_the_screen_is_about_the_strip_operation(self):
        self.assertEqual(self.refusal(about=self.STRIP)._strip_note(118), [])

    def test_no_note_where_the_command_names_no_operation_or_the_result_is_not_a_refusal(self):
        self.assertEqual(self.refusal(command='collect')._strip_note(118), [])
        self.assertEqual(self.refusal(status='ok')._strip_note(118), [])

    def test_the_whole_screen_names_it_once(self):
        workspace = self.refusal()
        workspace.tab = 5
        body = ' '.join(' '.join(workspace._body_lines(118, 'unicode')).split())
        self.assertEqual(body.count("The strip's OP"), 1, body)
