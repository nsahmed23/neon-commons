"""Words where the screens showed raw values or unscoped claims (journey 26 run 3 frame review, items 3, 5, 6, 8, 9,
15, 16, 17, 22, 24, 26, 27 and 28; logs/journey-26/FRAME-REVIEW-run3.md in the custody records).

Each screen keeps its exact values in the typed details (e) and the raw record (r); the summary says what they mean.
Expected words are written by hand.
"""
import tempfile
import unittest
from pathlib import Path

TENANT = '11111111-1111-4111-8111-111111111111'
POLICY = '22222222-2222-4222-8222-222222222222'


def text(lines):
    return ' '.join(' '.join(lines).split())


class ScreenWordTests(unittest.TestCase):
    def test_estate_filters_read_as_words_and_echo_the_search(self):
        # Items 3 and 27: "Global filters: {json}" on a cleared page; a search page that did not say what it searched.
        from intune_iac.workbench_screens import filter_words
        self.assertEqual(filter_words({'query': '', 'ownership': None, 'coverage': None, 'health': None}), 'No filters applied.')
        self.assertEqual(filter_words({'query': 'Pilot', 'ownership': 'unknown', 'coverage': 'stale_or_incomplete', 'health': None}),
                         'Filters: search "Pilot"; ownership unknown; coverage stale or incomplete.')

    def test_health_and_collection_times_are_readable(self):
        # Item 9: "as of 2026-10-14T22:25:35Z".
        from intune_iac.workbench_screens import _collection_lines, _object_health
        lines = text(_object_health({'name': 'Pilot', 'object_id': POLICY}, {
            'as_of': '2026-10-14T22:25:35Z', 'evidence_class': 'synthetic', 'cohort_version': 'v1',
            'targeted': 100, 'eligible': 100, 'excluded': 0, 'stages': {}}, 120))
        self.assertIn('as of 2026-10-14 22:25:35 UTC | cohort v1', lines)
        self.assertNotIn('22:25:35Z', lines)
        lines = text(_collection_lines({'freshness': 'fresh', 'last_success': {
            'completed_at': '2026-10-14T22:40:01.387953Z', 'run_id': 3, 'status': 'complete', 'error_code': None}}, 120))
        self.assertIn('Last success 2026-10-14 22:40:01 UTC | run 3 | complete | error none', lines)

    def test_device_matrix_rows_say_which_devices_they_hold(self):
        # Item 8: 100 devices in two rows of 50 read as a second, unlabelled bar.
        from intune_iac.workbench_screens import _matrix
        lines = _matrix((100, 8, 8, 0, 0, 0, 92), 80)
        bars = [line for line in lines if '[' in line]
        self.assertEqual(len(bars), 2)
        self.assertTrue(bars[0].strip().startswith('devices 1-50'), bars[0])
        self.assertTrue(bars[1].strip().startswith('devices 51-100'), bars[1])
        # Narrower, the label keeps its room and the rows shorten: every row still says which devices it holds.
        bars = [line.strip() for line in _matrix((100, 8, 8, 0, 0, 0, 92), 70) if '[' in line]
        self.assertEqual([bar.split('[')[0].strip() for bar in bars], ['devices 1-48', 'devices 49-96', 'devices 97-100'])
        self.assertTrue(all(len(line) <= 70 for line in _matrix((100, 8, 8, 0, 0, 0, 92), 70)))
        self.assertIn('each cell is 1 device', text(lines))
        single = [line for line in _matrix((30, 30, 30, 0, 0, 0, 0), 70) if '[' in line]
        self.assertEqual(len(single), 1)
        self.assertTrue(single[0].strip().startswith('['), single[0])

    def test_diagnostics_scope_the_device_evidence_claim_and_point_at_the_queue(self):
        # Item 6: "clear: the capture is complete" and "1 signal needs attention" beside three queue findings.
        from intune_iac.workbench_screens import diagnostics_lines
        signal = {'area': 'freshness', 'code': 'observation_stale', 'observed': 'The newest observation is stale.',
                  'next_step': 'Collect again.', 'evidence': {}}
        lines = text(diagnostics_lines({'name': 'Pilot', 'object_id': POLICY, 'signals': [signal],
                                        'checked': {'device_evidence': 'clear'}}, 140))
        self.assertIn('1 signal needs attention; reporting completeness and ownership are reviewed in the maintenance '
                      'queue (m)', lines)
        self.assertIn('device evidence capture complete and cohort consistent; whether devices reported is not judged '
                      'here (h shows the counts)', lines)
        self.assertNotIn('clear: the capture', lines)

    def test_diagnostics_evidence_reads_as_words(self):
        # Item 5: raw keys, ISO times and a JSON array.
        from intune_iac.workbench_screens import diagnostics_lines
        signal = {'area': 'freshness', 'code': 'observation_stale', 'observed': 'The newest observation is stale.',
                  'next_step': 'Wait.', 'evidence': {'snapshot_id': '599f74fd' + 'f' * 56,
                                                     'observed_at': '2026-10-14T22:40:01.387953Z',
                                                     'freshness_checked_at': '2026-10-14T22:36:01.712575Z',
                                                     'freshness_reasons': ['stamped_after_now']}}
        lines = text(diagnostics_lines({'name': 'Pilot', 'object_id': POLICY, 'signals': [signal], 'checked': {}}, 160))
        self.assertIn("Evidence snapshot 599f74fdffff; observed at 2026-10-14 22:40:01 UTC; freshness checked at "
                      "2026-10-14 22:36:01 UTC; freshness reasons: stamped after this host's clock", lines)
        self.assertNotIn('["', lines)
        self.assertNotIn('T22:40', lines)

    def test_families_and_the_writer_read_as_words(self):
        # Items 22 and 24: "live qualification: not_run" and "writer unknown: ownership_index_missing".
        from intune_iac.workbench_screens import families_lines, relationship_lines
        lines = text(families_lines({'available': True, 'source': {'path': 'family-coverage.csv', 'sha256': 'd' * 64},
                                     'families': [{'family': 'Windows', 'live': 'not_run'}]}, 120))
        self.assertIn('live qualification: not run.', lines)
        lines = text(relationship_lines({'object_id': POLICY, 'edges': [], 'ownership': 'unknown',
                                         'ownership_evidence': {'reason': 'ownership_index_missing'}}, 120))
        self.assertIn('writer unknown (ownership index missing)', lines)
        self.assertNotIn('ownership_index_missing', lines)


class WorkspaceWordTests(unittest.TestCase):
    def workspace(self, tab, value, mode_class='synthetic'):
        from intune_iac.workbench_tui import Workspace
        workspace = Workspace.__new__(Workspace)
        workspace.__dict__.update(tab=tab, value=value, selected=POLICY, facts={'object_id': POLICY}, mode_class=mode_class,
                                  rows=[], layer='summary', last_command='views', store=type('S', (), {'tenant_id': TENANT})())
        return workspace

    def test_coverage_states_read_as_statements(self):
        # Item 28: "Ownership freshness: no", "Repository: recorded".
        value = {'schema_version': 'workbench-four-views/1', 'repository': {'status': 'recorded'},
                 'observed': {'status': 'recorded'}, 'proposed': {'status': 'not_recorded'},
                 'coverage': {'observation': 'stale_or_incomplete', 'management': 'unknown', 'state_tracked': 'not_recorded',
                              'mapping': 'supported_comparison_only', 'platform_qualified': False,
                              'ownership': {'declared_scope_complete': False, 'fresh': False}}, 'comparisons': {}}
        lines = text(self.workspace(6, value)._surface_summary(120))
        for words in ('Repository intent: recorded', 'Observation: recorded', 'Proposal: not recorded',
                      'Platform qualification: not qualified',
                      'Ownership: declared scope not complete; ownership index not fresh'):
            self.assertIn(words, lines)
        self.assertNotIn('Ownership freshness', lines)
        self.assertNotIn(': no ', lines + ' ')

    def test_an_estate_page_names_the_estate_evidence_class(self):
        # Item 26: "[evidence class not stated]" on filtered and searched pages of the same synthetic estate.
        workspace = self.workspace(0, {'objects': [], 'filters': {'query': 'x'}})
        self.assertEqual(workspace._scope({}), 'synthetic')
        self.assertEqual(self.workspace(7, {'navigation': []})._scope({}), 'evidence class not stated')


class SurveyWordTests(unittest.TestCase):
    def test_a_journey_session_reads_as_words(self):
        # Item 16: "complete_simulation | next complete_simulation | 17 of 17 stages verify".
        from intune_iac.entry import _summary
        item = {'kind': 'journey_session', 'lifecycle': 'complete_simulation', 'next_state': 'complete_simulation',
                'verified': 17, 'states': {'configured': True}}
        self.assertEqual(_summary(item), 'complete simulation | 17 of 17 stages verified as completed')
        item = dict(item, lifecycle='in_progress', next_state='await_approval', verified=9)
        self.assertEqual(_summary(item), 'in progress | next await approval | 9 of 17 stages verified as completed')

    def test_each_item_says_it_is_usable_here_not_configured(self):
        # Item 15: "configured" on every row beside "No live discovery connection is configured".
        from intune_iac.entry import start_lines
        value = {'directory': '/work', 'items': [{'kind': 'store', 'path': 'store', 'tenant_id': TENANT, 'objects': 1,
                                                 'freshness': 'fresh', 'intents': [], 'operations': 0,
                                                 'states': {'configured': True, 'authenticated': 'offline',
                                                            'qualified': 'synthetic_only'}}],
                 'next_actions': [], 'missing': [], 'notes': []}
        lines = text(start_lines(value, 120))
        self.assertIn('discovered | usable here |', lines)
        self.assertNotIn('| configured |', lines)

    def test_the_store_counts_operations_not_journal_records(self):
        # Item 17: "2 operations" for one operation with two records.
        from intune_iac.entry import _store_item
        from intune_iac.workbench_store import WorkbenchStore
        with tempfile.TemporaryDirectory() as directory:
            store = WorkbenchStore.create(Path(directory) / 'store', TENANT)
            store.record_operation('op-1', {'object_id': POLICY, 'status': 'prepared'})
            store.record_operation('op-1', {'object_id': POLICY, 'status': 'executed'})
            item = _store_item(Path(directory), store.root, 'store')
            self.assertEqual(item['operations'], 1)
