"""PKG-PRES-RUN15 (adversarial review of aa391f7, journeys 28 run 15 and 29 run 10): what the screens say.

Each class names its item of the brief. Temporary directories only.
"""
import re
import unittest

from intune_iac.workbench_tui import cell_width
from plugin_tests.test_workbench_map import Fixture
from plugin_tests.test_workbench_map_truth import MARK, MapTruth

SELECTED = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'


def flat(rows):
    return ' '.join(' '.join(rows).split())


class QueueRoutesActOnTheFindingsPolicyTests(unittest.TestCase):
    """Item 1 (review 20): queue-review commands act on the selected policy, so a finding of another policy
    puts `select <object_id>` first, and a finding of the selected policy prints no select."""

    def finding(self, object_id):
        return {'finding': 'reporting_incomplete', 'object_id': object_id, 'priority': 'review', 'priority_rationale': 'x',
                'review_record': {'status': 'not_recorded'}}

    def queue(self, object_id, selected):
        from intune_iac.workbench_screens import queue_lines
        return queue_lines({'findings': [self.finding(object_id)], 'scope': {}}, 118, selected=selected)

    def test_a_finding_of_another_policy_selects_it_before_the_review_commands(self):
        rows = [row.strip() for row in self.queue(OTHER, SELECTED)]
        self.assertIn(':select ' + OTHER, rows)
        self.assertLess(rows.index(':select ' + OTHER), rows.index(':queue-review-template reporting_incomplete NEW_JSON'))

    def test_a_finding_of_the_selected_policy_prints_no_select(self):
        rows = [row.strip() for row in self.queue(SELECTED, SELECTED)]
        self.assertNotIn(':select ' + SELECTED, rows)
        self.assertIn(':queue-review-template reporting_incomplete NEW_JSON', rows)

    def test_with_no_selection_the_finding_is_selected_first(self):
        self.assertIn(':select ' + OTHER, [row.strip() for row in self.queue(OTHER, None)])

    RECORDED = {'artifact_id': '53e45c2369a0' + '0' * 52, 'kind': 'queue_review', 'created': True,
                'recorded_at': '2026-10-16T01:17:47Z',
                'data': {'finding': 'reporting_incomplete', 'object_id': OTHER, 'version': 2}}

    def test_the_recorded_review_next_selects_the_findings_policy_first(self):
        from intune_iac.workbench_screens import recorded_lines
        rows = [row.strip() for row in recorded_lines(self.RECORDED, 118, selected=SELECTED)]
        self.assertLess(rows.index('select ' + OTHER), rows.index('queue-review reporting_incomplete'))

    def test_the_recorded_review_next_for_the_selected_policy_has_no_select(self):
        from intune_iac.workbench_screens import recorded_lines
        recorded = dict(self.RECORDED, data=dict(self.RECORDED['data'], object_id=SELECTED))
        rows = [row.strip() for row in recorded_lines(recorded, 118, selected=SELECTED)]
        self.assertNotIn('select ' + SELECTED, rows)
        self.assertIn('queue-review reporting_incomplete', rows)

    def test_the_workspace_passes_the_selected_policy(self):
        from plugin_tests import test_workbench_states as states_tests
        workspace = states_tests.StateSurfaceTests.workspace(None, 6, {'findings': [self.finding(OTHER)]})
        workspace.selected = SELECTED
        self.assertIn(':select ' + OTHER, [row.strip() for row in workspace._surface_summary(118)])


class ChangedBoundFileWordingTests(unittest.TestCase):
    """Item 2 (review 19): maintenance_source_changed is raised for the desired file and for the context file alike, and
    the refusal does not carry which one, so the cause must not name the unchanged context file."""
    WORDS = 'A file it bound (its desired file or its context file) changed after %s, so its review no longer describes what would run.'

    def refusal(self, **kw):
        from intune_iac.workbench_screens import refusal_lines
        value = {'status': 'error', 'error': {'code': 'maintenance_source_changed', 'message': 'A bound file changed.'}}
        return ' '.join(' '.join(refusal_lines(value, 118, **kw)).split())

    def test_the_cause_names_both_files_by_kind_and_no_path(self):
        text = self.refusal(operation='650a1a61', verb='execute', context_file='/w/my ctx.json')
        self.assertIn('Cause: ' + self.WORDS % 'operation 650a1a61 was prepared', text)
        self.assertNotIn('my ctx.json', text)

    def test_with_the_operation_unknown_the_cause_says_the_same_of_it(self):
        text = self.refusal(verb='execute')
        self.assertIn('Cause: ' + self.WORDS % 'it was prepared', text)

    def test_the_general_meaning_names_both_files_too(self):
        from intune_iac.workbench_screens import REFUSALS
        self.assertIn('(its desired file or its context file)', REFUSALS['maintenance_source_changed'][0])


class AgeDefinitionStatesCauseOnlyTests(unittest.TestCase):
    """Item 3 (review 18): a clock hold and a stamp ahead are not cured by collecting again (the band, Diagnostics and
    the actions list all say so), so their definition rows state the cause and point at the Inspector."""
    KEYS = ('age unknown', 'age unknown (stamped ahead)')

    def test_the_rows_do_not_send_the_engineer_to_collect(self):
        from intune_iac.workbench_screens import STRIP_DEFINITIONS
        for key in self.KEYS:
            row = STRIP_DEFINITIONS[key]
            self.assertNotIn('collect', row, row)
            self.assertNotIn('(a)', row, row)
            self.assertIn('2 Inspector says why', row)
            self.assertLessEqual(len(row), 80, row)

    def test_the_rows_a_narrow_strip_prints_do_not_say_collect(self):
        from intune_iac.workbench_screens import strip_choice, strip_key_rows
        for observation in self.KEYS:
            facts = {'observation': observation, 'name': 'A policy', 'repository': 'not checked'}
            definitions = strip_choice('t' * 8, 'p' * 8, facts, 80, None)[1]
            self.assertTrue(definitions, observation)
            rows = strip_key_rows(definitions, 80)
            self.assertTrue(any('age?' in row for row in rows), rows)
            self.assertNotIn('collect', ' '.join(rows))

    def test_the_collect_cured_stale_row_still_says_collect(self):
        from intune_iac.workbench_screens import STRIP_DEFINITIONS
        self.assertIn('collect again (a)', STRIP_DEFINITIONS['stale (later collection incomplete)'])


class MapFallbackAt40x12Tests(Fixture):
    """Item 4 (run10-R1): at 40x12 the strip marker and its definition share one row, and the fallback sentence fits the
    36-column body, so the first screen of the body ends on a whole sentence."""

    def body(self, rows):
        top = next(index for index, row in enumerate(rows) if row.startswith('\u250c'))
        bottom = next(index for index, row in enumerate(rows) if row.startswith('\u2514'))
        return [row.strip('\u2502 ').rstrip() for row in rows[top + 1:bottom]]

    def test_the_marker_and_the_definition_share_one_row(self):
        rows = self.plain(self.workspace((40, 12)))
        marked = [row for row in rows if 'more: ?' in row]
        self.assertEqual(len(marked), 1, rows)
        self.assertIn('T = tenant', marked[0])
        self.assertIn('P = policy', marked[0])
        self.assertEqual([row for row in rows if 'T = tenant' in row], marked)

    def test_the_body_keeps_three_rows_and_ends_on_a_whole_sentence(self):
        body = self.body(self.plain(self.workspace((40, 12))))
        self.assertGreaterEqual(len(body), 3, body)
        self.assertEqual(body[0], 'MAP NOT DRAWN (needs 60x20)')
        self.assertEqual(body[1], 'PgDn: tree lists all relationships')

    def test_the_frame_still_fits_the_window(self):
        rows = self.plain(self.workspace((40, 12)))
        self.assertEqual(len(rows), 12, rows)
        for row in rows:
            self.assertLessEqual(cell_width(row), 40, row)

    def test_the_sentence_is_whole_on_one_row_at_every_width_from_40(self):
        from intune_iac.workbench_screens import map_unavailable_lines
        for width in range(36, 121):
            lines = map_unavailable_lines(width)
            self.assertEqual(len(lines), 3, (width, lines))
            self.assertTrue(lines[1].endswith('.') or lines[1].endswith('relationships'), lines)
            self.assertLessEqual(cell_width(lines[1]), width, lines)

    def test_a_wide_window_keeps_the_longer_sentence(self):
        from intune_iac.workbench_screens import map_unavailable_lines
        self.assertEqual(map_unavailable_lines(80)[1], 'The tree below lists every relationship.')


class RepositoryNodeLabelTests(MapTruth):
    """Item 5 (run10-3): the repository node row cuts the local path alone. It no longer splices the head of the path
    onto the tail of the scope (the component name), which read as a path that is not recorded."""
    FOLDER = '/home/nsahm/work/journey 28 run 8/repository'

    def value_with(self, folder=None):
        return dict(self.value, selected_repository={
            'evidence_class': 'recorded_repository_intent',
            'scope': {'repository': folder or self.FOLDER, 'stack': 'orgs/reference/dev', 'component': 'intune-reference'}})

    def label(self, folder=None):
        _, rows = self.rows(self.graph(self.value_with(folder)))
        row = next(row for row in rows if 'repository' in row and MARK.search(row))
        return re.search(r'\[.\] (.*?)\s+\u2014', row.split('\u2192')[1]).group(1)

    def test_the_label_is_the_cut_path_and_names_no_component(self):
        label = self.label()
        self.assertNotIn('reference', label)
        self.assertTrue(label.startswith('/home/nsahm/w'), label)
        self.assertTrue(label.endswith('/repository'), label)
        self.assertIn('\u2026', label)

    def test_a_path_that_fits_is_shown_whole(self):
        self.assertEqual(self.label('/work/repo'), '/work/repo')

    def test_the_full_identity_stays_in_the_focus_rows(self):
        lines, rows = self.rows(self.graph(self.value_with()))
        self.assertIn(self.FOLDER + '  orgs/reference/dev / intune-reference', '\n'.join(
            line for line in self.focus_text(self.value_with())))

    def focus_text(self, value):
        from intune_iac.workbench_screens import map_lines
        graph = self.graph(value)
        repository = next(node for node in graph['nodes'] if node['kind'] == 'repository')
        return map_lines(graph, 200, focus=repository['ref'])


class StatusNamesTheLineTerminalCommandTests(unittest.TestCase):
    """Item 6, low 33: the repository status reaches the line terminal and the CLI as JSON, where keys 9 and a do not
    exist, so its next step also names the pinned command (M-74 still bans the unpinned form)."""

    def test_the_stale_step_keeps_the_key_route_and_names_the_pinned_command(self):
        from intune_iac.workbench_repository import NEXT_ACTIONS
        step = ' '.join(NEXT_ACTIONS['stale'].split())
        self.assertIn('Refresh the repository intent (a: actions)', step)
        self.assertIn('In the line terminal, where 9 and a are not keys, type repository-refresh REVISION '
                      'RESOLUTION_SHA256', step)
        self.assertIn('resolution_sha256 shown above', step)

    def test_no_unpinned_form_is_printed_by_any_screen_module(self):
        import re
        from pathlib import Path
        for module in ('workbench_diagnostics', 'workbench_screens', 'workbench_repository', 'workbench_tui'):
            source = (Path(__file__).resolve().parents[1] / 'intune_iac' / (module + '.py')).read_text(encoding='utf-8')
            self.assertEqual(re.findall(r'repository-refresh REVISION(?! RESOLUTION_SHA256)', source), [], module)


class GitPinsFromAShellTests(unittest.TestCase):
    """Item 6, low 34: the workspace repository-import takes no git pins, so the repository entry screen says the pins
    work only from a shell and prints that shell command with both flags."""
    COMMAND = "intune-iac workbench repository-import --root /w/store --repository /w/repo --revision abc1234"
    EXPLANATION = ('Ready to record: every value comes from the repository. The commit is recorded as stated; add '
                   '--git-executable and --git-sha256 to the command to verify it against the files.')

    def lines(self, width=200, **candidate):
        from intune_iac.workbench_screens import repository_entry_lines
        value = {'repository': '/w/repo', 'revision': 'f' * 40, 'tenant_id': 't' * 8, 'status': 'discovered', 'components': [],
                 'candidates': [dict({'number': 1, 'object_id': 'o' * 32, 'state': 'ready', 'stack': 's', 'component': 'c',
                                      'policy_key': 'p', 'backend': 'local', 'backend_source': 'none_declared',
                                      'explanation': self.EXPLANATION, 'observed': {'present': False}}, **candidate)],
                 'next_action': 'x'}
        return repository_entry_lines(value, width)

    def test_the_screen_says_the_pins_work_only_from_a_shell(self):
        text = ' '.join(' '.join(self.lines(command=self.COMMAND)).split())
        self.assertIn('The pins work only from a shell; the workspace repository-import cannot take them. From a shell:', text)

    def test_the_shell_command_is_printed_with_both_flags(self):
        rows = [row.strip() for row in self.lines(command=self.COMMAND)]
        self.assertIn(self.COMMAND + ' --git-executable GIT_PATH --git-sha256 GIT_SHA256', rows)

    def test_a_candidate_with_no_pin_flags_in_its_explanation_prints_no_shell_form(self):
        text = ' '.join(' '.join(self.lines(explanation='Recorded and current.', command=self.COMMAND)).split())
        self.assertNotIn('From a shell', text)

    def test_a_candidate_without_a_command_prints_no_command(self):
        text = ' '.join(' '.join(self.lines()).split())
        self.assertNotIn('From a shell', text)


class StoreLastRegisteredLabelTests(unittest.TestCase):
    """Item 6, low 35: the operation state row's time is when the store last registered the operation, which is not
    the journal's last record when the journal and the store disagree."""

    def row(self):
        from intune_iac.workbench_screens import state_lines
        states = {'operation': {'operation_id': 'd' * 32, 'journal_status': 'succeeded_verified',
                                'status': 'succeeded_verified', 'recorded_at': '2026-10-16T01:16:31Z'}}
        return ' '.join(' '.join(state_lines(states, 140)).split())

    def test_the_time_is_labelled_as_the_stores_registration(self):
        text = self.row()
        self.assertIn('dddddddd succeeded verified; store last registered 2026-10-16 01:16:31 UTC', text)
        self.assertNotIn('journal last recorded', text)


class FrameNeverTallerThanTheWindowTests(MapTruth):
    """Item 6, low 36: when the band, the strip split and the key rows would make the frame taller than the window at
    the minimum height, the key rows are dropped first, then the strip split, before the title and tab line scroll
    away. A band of any height is patched in, because the real band's wording is shorter than the rows it would need."""
    FACTS = {'operation': 'outcome_unknown', 'observation': 'source changed', 'repository': 'current',
             'name': 'Windows Privacy Pilot'}

    def screen(self, size, band_rows, tab=1):
        from unittest import mock
        band = ['! band row %d' % number for number in range(band_rows)]
        with mock.patch('intune_iac.workbench_screens.hazard_rows', lambda *args, **kw: band):
            ws = self.workspace(size, tab=tab, facts=dict(self.FACTS, object_id=self.object_id))
            return self.plain(ws)

    def test_the_frame_has_no_more_rows_than_the_window_when_dropping_rows_can_make_it_fit(self):
        for band_rows in (1, 2, 3, 4):
            rows = self.screen((40, 12), band_rows)
            self.assertLessEqual(len(rows), 12, (band_rows, rows))

    def test_the_title_and_tab_line_stay_on_the_first_rows(self):
        rows = self.screen((40, 12), 4)
        self.assertTrue(rows[0].startswith('INTUNE WORKBENCH'), rows)
        self.assertTrue(rows[1].startswith('[2'), rows)
        self.assertEqual(sum(1 for row in rows if row.startswith('! band row')), 4, rows)

    def test_the_split_is_dropped_before_the_title(self):
        rows = self.screen((40, 12), 4)
        self.assertFalse(any('more: ?' in row or 'T = tenant' in row for row in rows), rows)
        self.assertTrue(rows[2].startswith('SYNTHETIC | T '), rows)

    def test_a_frame_that_fits_keeps_the_split_and_its_definitions(self):
        rows = self.screen((40, 12), 1)
        self.assertTrue(any('more: ?' in row and 'T = tenant' in row for row in rows), rows)
        rows = self.screen((40, 30), 4)
        self.assertTrue(any('more: ?' in row and 'T = tenant' in row for row in rows), rows)


class OpenWindowWasOpenAtTheLastReadTests(unittest.TestCase):
    """Item 6, low 37: the newest operation's approval window comes from the last read of the policy, which can be
    older than the 300-second window, so the Next says it was open then."""

    def text(self):
        from plugin_tests.test_workbench_run12 import ClosedPlanNextNamesTheOpenProposalTests as Closed
        return Closed('test_the_next_names_the_open_newest_operation').rows('open')

    def test_the_next_says_the_window_was_open_at_the_last_read_of_this_policy(self):
        self.assertIn('review the newest operation, a23983bd, whose approval window was open at the last read of this '
                      'policy; this plan cannot run because its approval window closed at ', self.text())

    def test_it_no_longer_claims_the_window_is_open_now(self):
        self.assertNotIn('approval window is open', self.text())
