"""Observation freshness is judged on a clock that never goes back (incident INC-a3feaed5ed-1, trace C).

The defect: a binding proposal judged the age of its observation on the bare wall clock. Evidence that had aged out
of the 3600 second window read fresh again after a backward wall step, and a new proposal then reached a PATCH.
The repair keeps a durable mark (clock.json beside the store database) and judges age on the effective time of
intune_iac.clock.Floor, while stamped_after_now stays on the raw wall reading.

Tests a to g fail on 83e167f and pass with the repair. Tests h to j are guards that pass before and after it.
Wall, monotonic and approval clocks are injected; nothing here waits on the host clock.
"""
import copy
import tempfile
import threading
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock, maintenance, protected, workbench_store, workbench_views
from intune_iac.io import AppError, write_json
from intune_iac.modeled_service import ModeledService
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore

START = 1_800_000_000
WINDOW = 3600
BACKWARD_STEP = 266


class Clocks:
    """An injected wall clock and monotonic clock. Real time moves both; a clock step moves only the wall."""

    def __init__(self, wall=START):
        self.wall, self.mono = wall, 5_000.0

    def now(self):
        return int(self.wall)

    def time(self):
        return float(self.wall)

    def monotonic(self):
        return self.mono

    def elapse(self, seconds):
        self.wall += seconds
        self.mono += seconds

    def step(self, seconds):
        self.wall += seconds


class FreshnessClockTestCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.clocks = Clocks()
        for target, name, replacement in (
                (workbench_store, 'time', types.SimpleNamespace(time=self.clocks.time)),
                (protected, '_now', self.clocks.now), (clock, 'monotonic', self.clocks.monotonic)):
            patcher = patch.object(target, name, **({'new': replacement} if name == 'time' else {'side_effect': replacement}))
            patcher.start()
            self.addCleanup(patcher.stop)
        clock.reset_process_anchor()
        self.addCleanup(clock.reset_process_anchor)
        self.fixture = generate_estate(seed=514, policy_count=3)
        self.tenant = self.fixture['truth']['tenant_id']
        self.ids = [p['id'] for p in self.fixture['truth']['policies']]
        self.oid = self.ids[0]
        self.service = ModeledService.create(self.root / 'service', self.fixture['capture'], self.ids)
        self.store = WorkbenchStore.create(self.root / 'store', self.tenant)
        self.store.collect(self.service)
        self.collected_at = self.clocks.time()
        before = self.service.snapshot()['current']
        self.desired = copy.deepcopy(before['objects'][self.oid])
        self.desired['description'] = 'Reviewed synthetic correction'
        self.desired_path = self.root / 'desired.json'
        write_json(self.desired_path, self.desired)
        self.operation = self.root / 'operation'
        self.floor_path = self.root / 'store' / 'clock.json'

    def propose(self):
        return maintenance.propose(self.root / 'store', self.root / 'service', self.oid, self.desired_path, self.operation)

    def patches(self):
        return [r for r in self.service.snapshot()['requests'] if r['method'] == 'PATCH']

    def refused(self, call=None):
        with self.assertRaises(AppError) as raised:
            (call or self.propose)()
        return raised.exception

    def assert_stale_proposal_held(self):
        error = self.refused()
        self.assertEqual(error.code, 'maintenance_observation_stale')
        self.assertIs(error.effects['operation_created'], False)
        self.assertFalse(self.operation.exists())
        self.assertEqual(self.patches(), [])

    def roll_back(self, seconds=BACKWARD_STEP):
        """The wall steps back while real (monotonic) time keeps going."""
        self.clocks.step(-seconds)
        self.clocks.mono += 5

    def reasons(self, store=None):
        return (store or self.store).inspect(self.oid)['freshness_reasons']

    def age_out_then_refuse(self):
        """Trace C up to the rollback: the evidence ages out, a binding proposal refuses it."""
        self.clocks.elapse(WINDOW + 1)
        self.assertEqual(self.reasons(), ['older_than_window'])
        self.assert_stale_proposal_held()


class RedBeforeTheRepairTests(FreshnessClockTestCase):
    """These fail on 83e167f: the age is judged on the bare wall clock."""

    def test_a_aged_out_evidence_stays_stale_after_a_backward_step_in_process(self):
        self.age_out_then_refuse()
        self.roll_back()
        observation = self.store.inspect(self.oid)
        self.assertEqual(observation['freshness'], 'stale')
        self.assertIn('older_than_window', observation['freshness_reasons'])
        self.assertIn('clock_moved_backward', observation['freshness_reasons'])
        self.assert_stale_proposal_held()

    def test_b_the_hold_survives_a_new_process_and_a_new_store_object(self):
        # No execute happens in this scenario: a changed service would refuse with service_changed and mask freshness.
        self.age_out_then_refuse()
        self.assertEqual(clock.Floor(self.floor_path).high_water(), self.clocks.time())
        clock.reset_process_anchor()
        reopened = WorkbenchStore(self.root / 'store')
        self.roll_back()
        self.assertIn('older_than_window', self.reasons(reopened))
        self.assertIn('clock_moved_backward', self.reasons(reopened))
        self.assert_stale_proposal_held()

    def test_c_inspect_writes_nothing_to_the_clock_record(self):
        self.assertTrue(self.floor_path.exists(), 'collect records the store clock')
        before = (self.floor_path.read_bytes(), self.floor_path.stat().st_mtime_ns)
        self.clocks.elapse(100)
        self.store.inspect(self.oid)
        self.roll_back()
        self.store.inspect(self.oid)
        self.assertEqual((self.floor_path.read_bytes(), self.floor_path.stat().st_mtime_ns), before)

    def test_d_collect_records_the_wall_never_the_stamp_it_was_given(self):
        self.store.collect(self.service, observed_at=self.clocks.time() + 86400)
        self.assertEqual(clock.Floor(self.floor_path).high_water(), self.collected_at)
        self.clocks.elapse(30)
        self.store.collect(self.service)
        current = self.store.inspect(self.oid)
        self.assertEqual(current['freshness'], 'fresh', current['freshness_reasons'])
        self.assertEqual(clock.Floor(self.floor_path).high_water(), self.clocks.time())

    def test_e_a_recollection_during_a_backward_step_neither_lowers_nor_clears_the_mark(self):
        self.age_out_then_refuse()
        mark = clock.Floor(self.floor_path).high_water()
        self.assertEqual(mark, self.clocks.time())
        self.roll_back()
        self.store.collect(self.service)
        # The mark may rise to what this process carried forward (mark plus the 5 monotonic seconds), never fall to the wall.
        self.assertGreaterEqual(clock.Floor(self.floor_path).high_water(), mark)
        self.assertGreater(clock.Floor(self.floor_path).high_water(), self.clocks.time())
        current = self.store.inspect(self.oid)
        self.assertEqual(current['freshness'], 'stale')
        self.assertIn('clock_moved_backward', current['freshness_reasons'])
        self.assert_stale_proposal_held()
        # The hold lasts until the wall reads at or after the mark again.
        self.clocks.step(BACKWARD_STEP + 60)
        self.assertEqual(self.reasons(), [])

    def test_f_a_damaged_clock_record_makes_inspect_stale_and_the_proposal_refuse(self):
        self.floor_path.write_bytes(b'{not json')
        observation = self.store.inspect(self.oid)
        self.assertEqual(observation['freshness'], 'stale')
        self.assertIn('clock_floor_invalid', observation['freshness_reasons'])
        before = self.floor_path.read_bytes()
        self.store.collect(self.service)
        self.assertEqual(self.floor_path.read_bytes(), before)
        self.assert_stale_proposal_held()

    def test_g_two_recorders_never_lower_the_mark(self):
        # test_clock_authority.py ReviewFindingTests.test_two_observers_never_lower_the_recorded_time, through collect.
        self.clocks.elapse(10)
        wall_of = {'high': START + 290, 'low': START + 24}
        self.clocks.time = lambda: float(wall_of.get(threading.current_thread().name, self.clocks.wall))
        workbench_store.time.time = self.clocks.time
        real_write = clock.write_json
        a_at_write, b_at_write, a_written = threading.Event(), threading.Event(), threading.Event()
        errors = []

        def ordered_write(target, value):
            if value['high_water'] == START + 290:
                a_at_write.set()
                b_at_write.wait(1)  # without the lock B reaches its write; with it B waits for the lock
                real_write(target, value)
                a_written.set()
            else:
                b_at_write.set()
                a_written.wait(5)
                real_write(target, value)

        def collect():
            try:
                WorkbenchStore(self.root / 'store').collect(self.service)
            except Exception as error:  # reported by the assertion below, not swallowed
                errors.append(error)

        with patch.object(clock, 'write_json', side_effect=ordered_write), \
                patch.object(clock, '_process_floor', side_effect=lambda key, wall: wall):
            high = threading.Thread(target=collect, name='high')
            high.start()
            self.assertTrue(a_at_write.wait(5), 'collect records the store clock')
            low = threading.Thread(target=collect, name='low')
            low.start()
            high.join(30)
            low.join(30)
        self.assertEqual(errors, [])
        self.assertEqual(clock.Floor(self.floor_path).high_water(), START + 290)


class GuardsThatPassBeforeAndAfterTests(FreshnessClockTestCase):
    """These pass on 83e167f and must still pass with the repair."""

    def test_h_guard_a_future_stamp_is_refused_and_reads_fresh_again_once_the_wall_passes_it(self):
        self.roll_back()  # trace B: the wall reads before the stamp the store wrote
        observation = self.store.inspect(self.oid)
        self.assertIn('stamped_after_now', observation['freshness_reasons'])
        self.assertEqual(observation['freshness'], 'stale')
        self.assert_stale_proposal_held()
        # Real time passes until the wall is past the stamp and past anything this process carried.
        self.clocks.wall = self.collected_at + 100
        self.clocks.mono += 50
        self.assertEqual(self.reasons(), [])

    def test_i_guard_coherent_time_proposes_and_executes_with_one_patch(self):
        self.clocks.elapse(60)
        proposal = self.propose()
        result = maintenance.execute(self.operation, approve_digest=proposal['approval_digest'])
        self.assertEqual(result['status'], 'succeeded_verified', result)
        self.assertEqual(len(self.patches()), 1)

    def test_j_guard_age_exactly_at_the_window_is_fresh_and_one_second_more_is_older(self):
        self.clocks.elapse(WINDOW)
        self.assertEqual(self.store.inspect(self.oid)['age_seconds'], WINDOW)
        self.assertEqual(self.reasons(), [])
        self.clocks.elapse(1)
        self.assertEqual(self.reasons(), ['older_than_window'])


class ClockFactTests(FreshnessClockTestCase):
    """PKG-PRES-HOLD item 1: a clock hold says what the clock read and what was recorded, and nothing else changes."""

    def test_a_backward_hold_carries_the_reading_and_the_recorded_time(self):
        self.clocks.elapse(30)
        self.store.collect(self.service)
        recorded = clock.Floor(self.floor_path).high_water()
        self.roll_back()
        observation = self.store.inspect(self.oid)
        self.assertIn('clock_moved_backward', observation['freshness_reasons'])
        fact = observation['freshness_clock']
        self.assertEqual(set(fact), {'reads', 'recorded'})
        self.assertEqual(fact['reads'], self.clocks.time())
        self.assertGreaterEqual(fact['recorded'], recorded)
        self.assertGreater(fact['recorded'], fact['reads'])

    def test_an_unreadable_record_carries_the_reading_and_no_recorded_time(self):
        self.floor_path.write_bytes(b'{not json')
        observation = self.store.inspect(self.oid)
        self.assertIn('clock_floor_invalid', observation['freshness_reasons'])
        self.assertEqual(observation['freshness_clock'], {'reads': self.clocks.time(), 'recorded': None})

    def test_without_a_clock_reason_the_key_is_absent_and_nothing_else_changes(self):
        fresh = self.store.inspect(self.oid)
        self.assertNotIn('freshness_clock', fresh)
        self.clocks.elapse(WINDOW + 1)
        aged = self.store.inspect(self.oid)
        self.assertEqual(aged['freshness_reasons'], ['older_than_window'])
        self.assertNotIn('freshness_clock', aged)
        self.roll_back()
        held = self.store.inspect(self.oid)
        self.assertIn('freshness_clock', held)
        self.assertEqual(set(held) - {'freshness_clock'}, set(fresh))


class OverviewClockTests(FreshnessClockTestCase):
    """PKG-TIME-OVERVIEW: every freshness judgement in the workspace is made on the reading inspect would make.

    The hold scenario is a clock that steps back after the mark was recorded; BACKWARD_STEP is well past the
    tolerance, so the wall alone says fresh while the recorded time says the age cannot be established.
    """
    DEPLOYMENT = {'targeted': 4, 'reporting': 4, 'successful': 4}

    def setUp(self):
        super().setUp()
        patcher = patch.object(workbench_views, 'time', types.SimpleNamespace(time=self.clocks.time))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store.collect(self.service, deployment=self.DEPLOYMENT)
        self.scope = {'repository': str(self.root / 'repository'), 'stack': 'a', 'component': 'intune', 'backend': 'lab'}

    def hold(self, elapsed=600):
        """Time passes, a binding reading records it, then the wall steps back: a clock hold on every row."""
        self.clocks.elapse(elapsed)
        self.store.inspect(self.oid, bind=True)
        self.roll_back()

    def row(self, **kwargs):
        return next(r for r in self.store.overview(**kwargs)['objects'] if r['object_id'] == self.oid)

    def import_ownership(self):
        document = {'schema_version': 'workbench-ownership-index/1', 'tenant_id': self.tenant, 'max_age_seconds': 3600,
                    'declared_scopes': [self.scope], 'sources': [{'scope': self.scope, 'coverage': 'complete',
                    'observed_at': self.clocks.time(), 'claims': [{'object_id': self.oid, 'resource_address': 'policy.one',
                                                                   'parts': ['object', 'assignments']}]}]}
        write_json(self.root / 'ownership.json', document)
        return workbench_views.import_ownership(self.store, self.root / 'ownership.json')

    def import_refresh(self):
        body = copy.deepcopy(self.desired)
        document = {'schema_version': 'workbench-provider-refresh/1', 'tenant_id': self.tenant, 'object_id': self.oid,
                    'state_revision': {'lineage': 'lab', 'serial': 1, 'sha256': 'a' * 64}, 'state_body': body,
                    'refreshed_body': body, 'observed_at': self.clocks.time(), 'max_age_seconds': 3600, 'scope': self.scope}
        write_json(self.root / 'refresh.json', document)
        return workbench_views.import_provider_refresh(self.store, self.root / 'refresh.json')

    def import_evidence(self):
        from intune_iac.workbench_health import import_device_evidence
        stamp = datetime.fromtimestamp(self.clocks.time(), timezone.utc).isoformat().replace('+00:00', 'Z')
        devices = ['device-%d' % index for index in range(4)]
        document = {'schema_version': '1.0.0', 'synthetic': True, 'as_of': stamp, 'freshness_seconds': WINDOW,
                    'cohort': {'version': 'fixture', 'eligible_ids': devices, 'targeted_ids': devices, 'excluded_ids': []},
                    'rows': [{'id': 'row-' + name, 'device_id': name, 'stage': 'execution', 'status': 'success',
                              'observed_at': stamp, 'source_file': 'minimized.json', 'source_pointer': '/' + name,
                              'coverage': 'complete', 'synthetic': True} for name in devices],
                    'capture': {'timezone': 'UTC', 'clock_skew_seconds': None, 'logging_enabled': None,
                                'truncated': False, 'access_errors': []},
                    'promotion_thresholds': {'min_reporting_ratio': 1, 'min_success_ratio': 1}}
        write_json(self.root / 'device.json', {'schema_version': 'workbench-device-evidence/1', 'tenant_id': self.tenant,
                                               'object_id': self.oid, 'evidence': document})
        import_device_evidence(self.store, self.root / 'device.json')

    # Item 1: overview.

    def test_overview_judges_a_row_on_the_reading_inspect_makes(self):
        self.hold()
        inspected = self.store.inspect(self.oid)
        self.assertEqual(inspected['freshness_reasons'], ['clock_moved_backward'])
        row = self.row()
        for key in ('freshness', 'freshness_reasons', 'freshness_clock', 'age_seconds', 'freshness_checked_at', 'health'):
            self.assertEqual(row[key], inspected[key], key)

    def test_overview_keeps_aged_out_evidence_aged_after_a_backward_step(self):
        self.clocks.elapse(WINDOW + 1)
        self.store.inspect(self.oid, bind=True)
        self.roll_back()
        row = self.row()
        self.assertEqual(row['freshness'], 'stale')
        self.assertEqual(row['freshness_reasons'], self.store.inspect(self.oid)['freshness_reasons'])
        self.assertIn('older_than_window', row['freshness_reasons'])
        self.assertIn('clock_moved_backward', row['freshness_reasons'])

    def test_overview_inventory_is_not_fresh_while_a_clock_reason_holds(self):
        self.hold()
        overview = self.store.overview()
        self.assertEqual(overview['freshness'], 'stale')
        self.assertEqual(overview['age_seconds'], self.store.inspect(self.oid)['age_seconds'])

    def test_overview_names_an_unreadable_clock_record_in_each_row(self):
        self.floor_path.write_bytes(b'{not json')
        row = self.row()
        self.assertEqual(row['freshness'], 'stale')
        self.assertIn('clock_floor_invalid', row['freshness_reasons'])
        self.assertEqual(row['freshness_clock'], {'reads': self.clocks.time(), 'recorded': None})
        self.assertEqual(self.store.overview()['freshness'], 'stale')

    def test_guard_overview_with_an_explicit_now_is_unchanged_by_a_clock_hold(self):
        self.hold()
        wall = self.clocks.time()
        row = self.row(now=wall)
        self.assertEqual((row['freshness'], row['freshness_reasons']), ('fresh', []))
        self.assertNotIn('freshness_clock', row)
        self.assertEqual(self.store.overview(now=wall)['freshness'], 'fresh')
        aged = self.row(now=self.collected_at + WINDOW + 1)
        self.assertEqual(aged['freshness_reasons'], ['older_than_window'])

    # Item 2: deployment and report freshness.

    def test_collection_report_freshness_is_unknown_under_a_clock_hold(self):
        self.assertEqual(self.store.overview()['health']['report_freshness'], 'fresh')
        self.hold()
        health = self.store.overview()['health']
        self.assertEqual(health['report_freshness'], 'unknown')
        self.assertEqual(health['unknown_or_stale'], self.DEPLOYMENT['targeted'])
        self.assertEqual(self.store.inspect(self.oid)['health'], health)

    def test_collection_report_freshness_keeps_an_explicit_now(self):
        self.hold()
        self.assertEqual(self.store.overview(now=self.clocks.time())['health']['report_freshness'], 'fresh')
        self.assertEqual(self.store.overview(now=self.collected_at + WINDOW + 1)['health']['report_freshness'], 'stale')

    def test_device_report_age_is_judged_on_the_effective_time(self):
        from intune_iac.workbench_health import device_health
        self.import_evidence()
        fresh = device_health(self.store, self.oid)['stages']['execution']
        self.assertEqual((fresh['successful'], fresh['unknown']), (4, 0))
        self.assertNotIn('age_unknown', fresh)
        self.clocks.elapse(WINDOW + 1)
        self.store.inspect(self.oid, bind=True)
        self.roll_back()
        held = device_health(self.store, self.oid)
        stage = held['stages']['execution']
        self.assertEqual((stage['successful'], stage['unknown'], stage['age_unknown']), (0, 4, 4))
        self.assertEqual(stage['stale'] + stage['future'], 0)
        self.assertEqual({d['reason'] for d in stage['devices']}, {'age_unknown'})
        self.assertEqual(held['freshness_reasons'], ['clock_moved_backward'])

    def test_device_report_never_reads_fresh_under_a_clock_hold_that_leaves_the_age_in_window(self):
        from intune_iac.workbench_health import device_health
        self.import_evidence()
        self.hold()
        stage = device_health(self.store, self.oid)['stages']['execution']
        self.assertEqual((stage['successful'], stage['age_unknown']), (0, 4))

    def test_summarize_evidence_with_an_explicit_now_ignores_the_clock(self):
        from intune_iac.workbench_health import device_health
        self.import_evidence()
        self.hold()
        stage = device_health(self.store, self.oid, now=self.clocks.time())['stages']['execution']
        self.assertEqual((stage['successful'], stage['unknown']), (4, 0))
        self.assertNotIn('age_unknown', stage)

    # Item 3: views.

    def test_ownership_freshness_is_not_established_under_a_clock_hold(self):
        self.import_ownership()
        self.assertTrue(workbench_views.ownership(self.store, self.oid, self.scope)['fresh'])
        self.hold()
        held = workbench_views.ownership(self.store, self.oid, self.scope)
        self.assertIs(held['fresh'], False)
        self.assertEqual(held['status'], 'unknown')
        explicit = workbench_views.ownership(self.store, self.oid, self.scope, now=self.clocks.time())
        self.assertIs(explicit['fresh'], True)

    def test_estate_view_does_not_call_a_held_observation_fresh(self):
        self.assertEqual(workbench_views.views(self.store)['objects'][0]['coverage']['observation'], 'complete_fresh')
        self.hold()
        rows = {r['object_id']: r for r in workbench_views.views(self.store)['objects']}
        row = rows[self.oid]
        self.assertEqual(row['coverage']['observation'], 'stale_or_incomplete')
        self.assertEqual(row['freshness'], 'stale')
        self.assertEqual(row['freshness_reasons'], ['clock_moved_backward'])
        self.assertEqual(row['freshness_clock'], self.store.inspect(self.oid)['freshness_clock'])
        explicit = workbench_views.views(self.store, now=self.clocks.time())['objects'][0]
        self.assertEqual(explicit['coverage']['observation'], 'complete_fresh')
        self.assertNotIn('freshness_clock', explicit)

    def test_estate_view_filters_a_held_observation_out_of_complete_fresh(self):
        self.hold()
        self.assertEqual(workbench_views.views(self.store, coverage_filter='complete_fresh')['pagination']['total_objects'], 0)

    def test_estate_ownership_and_health_use_the_same_reading(self):
        self.import_ownership()
        self.import_evidence()
        self.hold()
        row = next(r for r in workbench_views.views(self.store, scope=self.scope)['objects'] if r['object_id'] == self.oid)
        self.assertIs(row['coverage']['ownership']['fresh'], False)
        self.assertEqual((row['health']['successful'], row['health']['unknown']), (0, 4))

    def test_selected_object_view_holds_coverage_and_the_provider_refresh_comparison(self):
        self.import_refresh()
        before = workbench_views.views(self.store, self.oid, scope=self.scope)
        self.assertEqual(before['coverage']['observation'], 'complete_fresh')
        self.assertNotEqual(before['comparisons']['provider_refresh_vs_state']['status'], 'unknown')
        self.hold()
        held = workbench_views.views(self.store, self.oid, scope=self.scope)
        self.assertEqual(held['coverage']['observation'], 'stale_or_incomplete')
        self.assertEqual(held['comparisons']['provider_refresh_vs_state']['status'], 'unknown')
        explicit = workbench_views.views(self.store, self.oid, scope=self.scope, now=self.clocks.time())
        self.assertNotEqual(explicit['comparisons']['provider_refresh_vs_state']['status'], 'unknown')

    # Item 4: the maintenance queue.

    def queue_findings(self):
        from intune_iac.workbench import _queue
        return _queue(self.store)['findings']

    def test_queue_shows_a_finding_for_a_held_row_with_the_inspector_words_and_recovery(self):
        from intune_iac.workbench_diagnostics import CLOCK_HOLD_STEPS
        from intune_iac.workbench_screens import QUEUE_HOLD_WORDS, queue_lines
        self.assertEqual([f for f in self.queue_findings() if f['finding'] == 'observation_stale'], [])
        self.hold()
        stale = [f for f in self.queue_findings() if f['finding'] == 'observation_stale' and f['object_id'] == self.oid]
        self.assertEqual(len(stale), 1)
        held = self.store.inspect(self.oid)
        self.assertEqual(stale[0]['evidence']['freshness_reasons'], ['clock_moved_backward'])
        self.assertEqual(stale[0]['evidence']['freshness_clock'], held['freshness_clock'])
        text = ' '.join('\n'.join(queue_lines({'findings': stale, 'pagination': {'total_objects': 1}}, 400)).split())
        self.assertIn('age unknown (%s)' % QUEUE_HOLD_WORDS['clock_moved_backward'], text)
        self.assertIn(CLOCK_HOLD_STEPS['clock_moved_backward'].split(';')[0], text)

    def test_queue_exception_expiry_treats_the_expiry_instant_as_expired(self):
        # An approval treats its expiry instant as expired; a queue exception must too.
        from intune_iac import workbench_queue
        expiry = '2027-01-15T09:00:00Z'
        at = datetime.fromisoformat(expiry.replace('Z', '+00:00')).timestamp()
        document = {'schema_version': workbench_queue.SCHEMA, 'tenant_id': self.tenant, 'object_id': self.oid,
                    'finding': 'ownership_unknown', 'owner': 'Endpoint operations', 'rationale': 'Confirm ownership.',
                    'review_due': '2027-01-15T08:00:00Z', 'exception_expiry': expiry, 'linked_proposals': []}
        write_json(self.root / 'review.json', document)
        workbench_queue.amend(self.store, self.root / 'review.json', expected_prior=None)
        read = lambda now: workbench_queue.current(self.store, self.oid, 'ownership_unknown', now=now)['exception_expired']
        self.assertIs(read(at - 1), False)
        self.assertIs(read(at), True)
        self.assertIs(read(at + 1), True)

    def test_an_expired_queue_exception_stays_expired_after_the_clock_steps_back(self):
        # Judged on the store's never-decreasing time: once the recorded time passed the expiry, a wall clock that
        # steps back before it does not make the exception current again.
        from intune_iac import workbench_queue
        expiry_at = self.clocks.time() + 600 - BACKWARD_STEP // 2
        expiry = datetime.fromtimestamp(expiry_at, timezone.utc).isoformat().replace('+00:00', 'Z')
        document = {'schema_version': workbench_queue.SCHEMA, 'tenant_id': self.tenant, 'object_id': self.oid,
                    'finding': 'ownership_unknown', 'owner': 'Endpoint operations', 'rationale': 'Confirm ownership.',
                    'review_due': expiry, 'exception_expiry': expiry, 'linked_proposals': []}
        write_json(self.root / 'review.json', document)
        workbench_queue.amend(self.store, self.root / 'review.json', expected_prior=None)
        self.hold(elapsed=600)
        self.assertLess(self.clocks.time(), expiry_at)  # the wall alone would call the exception current
        value = workbench_queue.current(self.store, self.oid, 'ownership_unknown')
        self.assertIs(value['exception_expired'], True)

    def test_held_ownership_names_the_clock_recovery_not_collecting_again(self):
        self.import_ownership()
        self.hold()
        held = [f for f in self.queue_findings() if f['finding'] == 'ownership_stale']
        self.assertTrue(held)  # one per policy the ownership index covers
        for finding in held:
            text = ' '.join(str(value) for value in finding.values())
            self.assertNotIn('collect every scope again', text)
            self.assertIn('collecting again does not clear this', text)

    def test_the_device_health_screen_names_devices_whose_report_age_is_unknown(self):
        from intune_iac.workbench_screens import _stage_lines
        stage = {'targeted': 4, 'reporting': 4, 'successful': 1, 'age_unknown': 3}
        text = ' '.join('\n'.join(_stage_lines({'execution': stage}, 100)).split())
        self.assertIn('Not counted as fresh success: 3 age unknown', text)

    # Item 5: agreement.

    @staticmethod
    def classify(freshness, reasons):
        from intune_iac.workbench_diagnostics import clock_hold
        return 'unknown' if clock_hold(reasons) else freshness

    def agreement(self):
        from intune_iac.workbench import _health, _queue
        from intune_iac.workbench_diagnostics import clock_hold
        inspected = self.store.inspect(self.oid)
        row = self.row()
        stale = [f for f in _queue(self.store)['findings'] if f['finding'] == 'observation_stale' and f['object_id'] == self.oid]
        queue = 'fresh' if not stale else 'unknown' if clock_hold(stale[0]['evidence'].get('freshness_reasons')) else 'stale'
        report = _health(self.store)['collection_health']['report_freshness']
        return {'inspect': self.classify(inspected['freshness'], inspected['freshness_reasons']),
                'overview': self.classify(row['freshness'], row['freshness_reasons']),
                'queue': queue, 'health': report}

    def test_inspect_overview_queue_and_health_agree_through_a_backward_step(self):
        everywhere = lambda verdict: dict.fromkeys(('inspect', 'overview', 'queue', 'health'), verdict)
        self.assertEqual(self.agreement(), everywhere('fresh'))
        self.clocks.elapse(WINDOW + 1)
        self.assertEqual(self.agreement(), everywhere('stale'))
        self.store.inspect(self.oid, bind=True)
        self.roll_back()
        self.assertEqual(self.agreement(), everywhere('unknown'))

    # Item 6: nothing read-only writes the clock record.

    def test_no_read_only_path_writes_the_clock_record(self):
        from intune_iac.workbench import _health, _queue
        from intune_iac.workbench_health import device_health
        self.import_ownership()
        self.import_refresh()
        self.import_evidence()

        def read_everything():
            self.store.overview()
            self.store.overview(query=self.oid)
            device_health(self.store, self.oid)
            _health(self.store)
            _queue(self.store)
            workbench_views.views(self.store)
            workbench_views.views(self.store, self.oid, scope=self.scope)
            workbench_views.ownership(self.store, self.oid, self.scope)

        snapshot = lambda: (self.floor_path.read_bytes(), self.floor_path.stat().st_mtime_ns)
        before = snapshot()
        self.clocks.elapse(30)
        read_everything()
        self.assertEqual(snapshot(), before)
        self.clocks.elapse(WINDOW)
        self.store.inspect(self.oid, bind=True)
        before = snapshot()
        self.roll_back()
        read_everything()
        self.assertEqual(snapshot(), before)
        self.floor_path.write_bytes(b'{not json')
        before = snapshot()
        read_everything()
        self.assertEqual(snapshot(), before)


if __name__ == '__main__':
    unittest.main()
