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
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock, maintenance, protected, workbench_store
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


if __name__ == '__main__':
    unittest.main()
