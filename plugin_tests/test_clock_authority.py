"""Time authority (owner directive inbox/PRODUCT-TASK-12.md, section 3; journey 25 run 3 executed a no-change plan whose
approval window had closed, because the host clock stepped back 266 seconds).

- An approval window never reopens when the wall clock steps back: validity is judged on an effective time that never
  goes backward (the latest time this operation recorded, carried forward within a process by monotonic time).
- A backward step beyond a small tolerance means validity cannot be established: the mutation is held, nothing is
  dispatched, and the refusal says how to recover.
- An expiry, once found, is recorded durably beside the approval and refuses every later attempt, after a clock
  rollback and a restart too.
- The store's own later collection outranks its earlier one whatever their wall times; an imported capture keeps
  capture-time order.

Wall and monotonic clocks are injected; nothing here waits on the host clock.
"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import clock, maintenance, protected
from intune_iac.io import AppError, write_json
from intune_iac.modeled_service import BASE, ModeledService
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore

START = 1_800_000_000


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


def inject(test, clocks):
    for target, name, function in ((protected, '_now', clocks.now), (clock, 'monotonic', clocks.monotonic)):
        patcher = patch.object(target, name, side_effect=function)
        patcher.start()
        test.addCleanup(patcher.stop)
    clock.reset_process_anchor()
    test.addCleanup(clock.reset_process_anchor)


class ApprovalWindowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.clocks = Clocks()
        inject(self, self.clocks)
        self.executor = protected.create_synthetic_executor(self.base / 'fixture', initial_value={}, desired_value={'x': 1})
        self.request = protected.prepare_native_operation(self.executor)
        self.receipts = self.base / 'receipts'

    def refused(self, call):
        with self.assertRaises(AppError) as raised:
            call()
        return raised.exception.code

    def approve(self):
        return protected.approve_synthetic_operation(self.request, executor=self.executor)

    def test_the_window_is_open_to_its_last_second_and_closed_at_expiry(self):
        self.clocks.wall = self.request['expires_at'] - 1
        self.approve()
        self.clocks.wall = self.request['expires_at']
        self.assertEqual(self.refused(self.approve), 'expired_request')

    def test_an_expired_window_stays_expired_after_the_clock_steps_back(self):
        self.clocks.elapse(self.request['expires_at'] - self.clocks.now())
        self.assertEqual(self.refused(self.approve), 'expired_request')
        self.assertTrue((self.executor.root / 'expired.json').exists())
        self.clocks.step(-266)
        self.assertEqual(self.refused(self.approve), 'expired_request')

    def test_a_recorded_expiry_survives_a_rollback_and_a_restart(self):
        self.clocks.elapse(400)
        self.assertEqual(self.refused(self.approve), 'expired_request')
        # A new process: the anchor resets, the executor is read again, and the wall clock reads before expiry.
        clock.reset_process_anchor()
        self.clocks.wall = self.request['created_at'] + 10
        self.executor = protected.SyntheticExecutor(self.base / 'fixture')
        self.assertEqual(self.refused(self.approve), 'expired_request')

    def test_a_backward_step_holds_the_mutation_and_dispatches_nothing(self):
        self.clocks.elapse(100)
        grant = self.approve()  # records the time it saw
        self.clocks.step(-80)
        with patch.object(protected, '_run', wraps=protected._run) as run:
            result = protected.execute_native_operation(self.request, self.receipts, executor=self.executor, approval=grant)
        self.assertEqual(result['status'], 'rejected', result)
        self.assertEqual(result['error']['code'], 'clock_moved_backward')
        self.assertNotIn('apply', [call.args[1] for call in run.call_args_list])

    def test_a_backward_step_after_a_restart_is_detected_from_the_recorded_time(self):
        self.clocks.elapse(100)
        self.approve()
        clock.reset_process_anchor()
        self.clocks.step(-80)
        self.assertEqual(self.refused(self.approve), 'clock_moved_backward')

    def test_expiry_after_review_but_before_dispatch_refuses_before_the_apply(self):
        grant = self.approve()
        original = protected._event

        def event(root, kind, payload):
            sha = original(root, kind, payload)
            if kind == 'authorized':
                self.clocks.elapse(400)  # the window closes between approval and dispatch
            return sha

        with patch.object(protected, '_event', side_effect=event), patch.object(protected, '_run', wraps=protected._run) as run:
            result = protected.execute_native_operation(self.request, self.receipts, executor=self.executor, approval=grant)
        self.assertEqual(result['status'], 'rejected', result)
        self.assertEqual(result['error']['code'], 'expired_request')
        self.assertNotIn('apply', [call.args[1] for call in run.call_args_list])

    def test_within_one_process_monotonic_time_carries_the_floor(self):
        floor = clock.Floor(self.base / 'floor.json')
        first = floor.observe(START + 50, persist=False)
        self.assertFalse(first['backward'])
        self.clocks.elapse(5)
        second = floor.observe(START + 10, persist=False)  # the wall clock stepped back 45 s in this process
        self.assertTrue(second['backward'])
        self.assertGreaterEqual(second['effective'], START + 55)
        self.assertFalse((self.base / 'floor.json').exists())


class MaintenanceDispatchTests(unittest.TestCase):
    """A mutation-capable plan (a description change): an expired or uncertain window sends nothing to the service and
    leaves an audit event; a later attempt after a clock rollback is refused again."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        fixture = generate_estate(seed=510, policy_count=2)
        self.ids = [policy['id'] for policy in fixture['truth']['policies']]
        self.service = ModeledService.create(self.root / 'service', fixture['capture'], self.ids)
        self.store = WorkbenchStore.create(self.root / 'store', fixture['truth']['tenant_id'])
        import time
        # Stamped well inside the past, so the host clock's 266 s steps never read it as stamped ahead.
        self.store.collect(self.service, observed_at=time.time() - 600)
        self.clocks = Clocks(wall=int(time.time()))
        inject(self, self.clocks)
        desired = copy.deepcopy(self.service.snapshot()['current']['objects'][self.ids[0]])
        desired['description'] = 'Reviewed synthetic correction'
        write_json(self.root / 'desired.json', desired)
        self.operation = self.root / 'operation'
        self.proposal = maintenance.propose(self.root / 'store', self.root / 'service', self.ids[0],
                                            self.root / 'desired.json', self.operation)

    def patches(self):
        return [request for request in self.service.snapshot()['requests'] if request['method'] == 'PATCH']

    def execute(self):
        with self.assertRaises(AppError) as raised:
            maintenance.execute(self.operation, approve_digest=self.proposal['approval_digest'])
        return raised.exception

    def test_an_expired_window_sends_nothing_and_is_recorded(self):
        self.clocks.elapse(400)
        error = self.execute()
        self.assertEqual(error.code, 'expired_request')
        self.assertFalse(error.effects['dispatched'])
        self.assertEqual(self.patches(), [])
        journal = maintenance._load(self.operation)[2]
        self.assertEqual(journal['status'], 'prepared')
        self.assertEqual([event['kind'] for event in journal['events']][-1], 'approval_refused')
        self.assertEqual(journal['events'][-1]['code'], 'expired_request')
        # The clock is rolled back below expiry: the recorded expiry still refuses, and still nothing is sent.
        self.clocks.wall = self.proposal['expires_at'] - 200
        clock.reset_process_anchor()
        self.assertEqual(self.execute().code, 'expired_request')
        self.assertEqual(self.patches(), [])

    def test_a_backward_step_holds_the_change_and_explains_recovery(self):
        self.clocks.elapse(30)
        protected.validate_native_operation(  # a check that records the time it saw
            maintenance._load(self.operation)[4], executor=protected.SyntheticExecutor(self.operation / 'executor'),
            require_fresh=True)
        self.clocks.step(-266)
        clock.reset_process_anchor()
        error = self.execute()
        self.assertEqual(error.code, 'clock_moved_backward')
        self.assertFalse(error.effects['dispatched'])
        self.assertEqual(self.patches(), [])


class ObservationOrderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        fixture = generate_estate(seed=511, policy_count=1)
        self.object_id = fixture['truth']['policies'][0]['id']
        self.tenant = fixture['truth']['tenant_id']
        self.service = ModeledService.create(self.root / 'service', fixture['capture'], [self.object_id])
        self.store = WorkbenchStore.create(self.root / 'store', self.tenant)

    def test_a_later_collection_outranks_a_future_stamped_one(self):
        import time
        now = time.time()
        first = self.store.collect(self.service, observed_at=now + 900)  # stamped ahead by a clock excursion
        body = dict(self.service.snapshot()['current']['objects'][self.object_id], description='Changed later')
        self.service.request('PATCH', BASE + '/' + self.object_id, tenant_id=self.tenant, body=body,
                             if_match=str(self.service.snapshot()['revision']))
        second = self.store.collect(self.service, observed_at=now - 600)
        self.assertGreater(second['run_id'], first['run_id'])
        inspected = self.store.inspect(self.object_id)
        self.assertEqual(inspected['run_id'], second['run_id'])
        self.assertEqual(inspected['body']['description'], 'Changed later')
        self.assertEqual(inspected['freshness'], 'fresh')
        overview = self.store.overview()
        self.assertEqual(overview['freshness'], 'fresh')


if __name__ == '__main__':
    unittest.main()
