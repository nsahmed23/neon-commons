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


class CaptureClockTests(unittest.TestCase):
    """Gate group G5 (lanes/review-hazard-actions/GATE-d44c9d0.txt): a backward wall-clock step during a capture made it
    finish before it started, and the import refused it (workbench_capture_timestamp). A capture's own times now run on
    its start plus monotonic elapsed time."""

    def test_a_backward_step_during_a_capture_keeps_its_times_in_order(self):
        import json
        from datetime import datetime, timezone
        from intune_iac import capture as capture_module
        policy, tenant = '22222222-2222-4222-8222-222222222222', '11111111-1111-4111-8111-111111111111'
        root = 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'
        responses = {root: (200, b'{"value":[{"id":"' + policy.encode() + b'","name":"Pilot"}]}'),
                     root + '/' + policy + '/settings': (200, b'{"value":[]}'),
                     root + '/' + policy + '/assignments': (200, b'{"value":[]}')}
        clocks = Clocks(wall=START)

        class Wall(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromtimestamp(clocks.wall, tz)

        def transport(url):
            clocks.elapse(1)
            if url.endswith('/settings'):
                clocks.step(-266)  # the host clock steps back in the middle of the capture
            return responses[url]

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        output = Path(temp.name) / 'capture'
        with patch.object(capture_module, 'datetime', Wall), \
                patch.object(capture_module.time, 'monotonic', side_effect=clocks.monotonic):
            capture_module.capture(tenant, policy, output, transport=transport)
        receipt = json.loads((output / 'capture-receipt.json').read_bytes())
        started = datetime.fromisoformat(receipt['started_at'].replace('Z', '+00:00'))
        finished = datetime.fromisoformat(receipt['finished_at'].replace('Z', '+00:00'))
        self.assertGreaterEqual(finished, started)
        self.assertEqual((finished - started).total_seconds(), 3)
        # The import accepts the times (a capture that finished before it started is refused with an AppError).
        store = WorkbenchStore.create(Path(temp.name) / 'store', tenant)
        self.assertIn('run_id', store.import_capture(output))


class ReviewFindingTests(unittest.TestCase):
    """Fable's review of 15e7155 (lanes/review-clock-authority/FABLE-REVIEW.md)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        clock.reset_process_anchor()
        self.addCleanup(clock.reset_process_anchor)

    def test_two_observers_never_lower_the_recorded_time(self):
        # Finding 1: the read, comparison and write of clock.json are one locked step. Two threads stand for two
        # processes (no shared process floor): B reads before A writes, and without the lock B would write after A.
        import threading
        path = self.base / 'race' / 'clock.json'
        path.parent.mkdir()
        clock.Floor(path).observe(START)
        real_write = clock.write_json
        a_at_write, b_at_write, a_written = threading.Event(), threading.Event(), threading.Event()

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

        with patch.object(clock, 'write_json', side_effect=ordered_write), \
                patch.object(clock, '_process_floor', side_effect=lambda key, wall: wall):
            high = threading.Thread(target=clock.Floor(path).observe, args=(START + 290,))
            high.start()
            self.assertTrue(a_at_write.wait(5))
            low = threading.Thread(target=clock.Floor(path).observe, args=(START + 24,))
            low.start()
            high.join(10)
            low.join(10)
        self.assertEqual(clock.Floor(path).high_water(), START + 290)

    def test_the_recovery_text_names_a_restart(self):
        # Findings 3 and 6.
        from intune_iac.workbench_screens import REFUSALS
        self.assertIn('restart the workbench', REFUSALS['clock_moved_backward'][1])
        for code in ('clock_floor_invalid', 'clock_reading_invalid'):
            self.assertIn('Prepare a new proposal', REFUSALS[code][1])


class DamagedClockRecordTests(unittest.TestCase):
    """Finding 4: a damaged clock record fails closed with an audit event and a recovery."""
    setUp = MaintenanceDispatchTests.setUp
    patches = MaintenanceDispatchTests.patches
    execute = MaintenanceDispatchTests.execute

    def test_a_damaged_clock_record_refuses_with_an_audit_event(self):
        (self.operation / 'executor' / 'clock.json').write_text('not json')
        error = self.execute()
        self.assertEqual(error.code, 'clock_floor_invalid')
        self.assertFalse(error.effects['dispatched'])
        self.assertEqual(self.patches(), [])
        journal = maintenance._load(self.operation)[2]
        self.assertEqual(journal['status'], 'prepared')
        self.assertEqual((journal['events'][-1]['kind'], journal['events'][-1]['code']),
                         ('approval_refused', 'clock_floor_invalid'))


class FutureCaptureTests(unittest.TestCase):
    """Finding 2: a capture stamped later than the store's clock at its import gives way to the next own collection."""
    from plugin_tests import test_workbench_capture_store as _capture_store
    setUp = _capture_store.CaptureStoreTests.setUp
    batch = _capture_store.CaptureStoreTests.batch
    import_batch = _capture_store.CaptureStoreTests.import_batch

    def test_a_future_stamped_capture_gives_way_to_a_later_collection(self):
        import time
        now, oid = time.time(), self.ids[0]
        self.store.collect(self.service, observed_at=now - 900)
        future = self.batch(observed_at=now + 86400)
        future['body']['name'] = 'Future capture'
        self.import_batch(future)
        self.assertEqual(self.store.inspect(oid)['body']['name'], 'Future capture')
        later = self.store.collect(self.service, observed_at=now - 600)
        self.assertEqual(self.store.inspect(oid)['body']['name'], self.bodies[oid]['name'])
        self.assertEqual(self.store.overview()['last_success']['run_id'], later['run_id'])

    def test_an_older_capture_imported_later_still_keeps_capture_time_order(self):
        import time
        now, oid = time.time(), self.ids[0]
        latest = self.store.collect(self.service, observed_at=now - 300)
        older = self.batch(observed_at=now - 7200)
        older['body']['name'] = 'Older capture'
        self.import_batch(older)
        self.assertEqual(self.store.inspect(oid)['body']['name'], self.bodies[oid]['name'])
        self.assertEqual(self.store.overview()['last_success']['run_id'], latest['run_id'])


class LegacyMigrationOrderTests(unittest.TestCase):
    """Finding 5: migrating a v1 store seeds each head from the latest run by run order, as the store now orders its
    own collections."""
    from plugin_tests import test_workbench_capture_store as _capture_store
    setUp = _capture_store.CaptureStoreTests.setUp
    legacy = _capture_store.CaptureStoreTests.legacy

    def test_migration_seeds_heads_by_run_order(self):
        import json
        import sqlite3
        from intune_iac.io import digest
        legacy, oid = self.legacy(), self.ids[0]
        source = json.dumps({'service_kind': 'ModeledService', 'service_root': str(self.service.root), 'service_revision': 1})
        first, second = dict(self.bodies[oid]), dict(self.bodies[oid], name='Second run body')
        with sqlite3.connect(legacy.path) as db:
            for run_id, observed_at, body in ((1, 300, first), (2, 100, second)):  # run 1 stamped ahead by a clock step
                snapshot = digest({'tenant_id': self.tenant, 'object_id': oid, 'body': body})
                db.execute('INSERT INTO collection_runs VALUES(?,?,?,?,?,?,?,?,?)',
                           (run_id, self.tenant, observed_at, observed_at, observed_at + 1, 'complete', 'complete', None, 1))
                db.execute('INSERT INTO snapshots VALUES(?,?,?,?)', (snapshot, self.tenant, oid, json.dumps(body)))
                db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?)',
                           (run_id, run_id, snapshot, self.tenant, oid, observed_at, source))
        legacy.migrate(self.root / 'backup.sqlite3')
        self.assertEqual(legacy.inspect(oid)['body']['name'], 'Second run body')


class WindowViewTests(unittest.TestCase):
    """The review, the lifecycle line and Delivery judge the window as execute does, without recording anything."""
    setUp = MaintenanceDispatchTests.setUp
    patches = MaintenanceDispatchTests.patches
    execute = MaintenanceDispatchTests.execute

    def tree(self):
        import hashlib
        executor = self.operation / 'executor'
        return {str(path.relative_to(executor)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(executor.rglob('*')) if path.is_file()}

    def window(self):
        return maintenance.review(self.operation)['approval_window']['state']

    def approval(self):
        from intune_iac.workbench_delivery import delivery
        return next(item for item in delivery(self.operation)['stages'] if item['stage'] == 'approval')

    def test_the_review_reports_the_window_as_execute_judges_it_and_records_nothing(self):
        before = self.tree()
        self.assertEqual(self.window(), 'open')
        self.clocks.elapse(400)
        self.assertEqual(self.window(), 'closed')
        self.assertEqual(self.tree(), before, 'a review records nothing')
        self.execute()  # the refused attempt records the expiry
        self.clocks.wall = self.proposal['expires_at'] - 200
        clock.reset_process_anchor()
        self.assertEqual(self.window(), 'closed_recorded')

    def test_a_backward_step_is_reported_not_called_open(self):
        # Prepare recorded the creation time; a reading 266 s earlier cannot be judged.
        self.clocks.step(-266)
        clock.reset_process_anchor()
        self.assertEqual(self.window(), 'clock_moved_backward')
        self.assertEqual(self.approval()['status'], 'clock_uncertain')

    def test_delivery_and_the_lifecycle_line_follow_the_recorded_expiry(self):
        from intune_iac.workbench_screens import _approval_text, lifecycle_next
        self.clocks.elapse(400)
        self.execute()
        self.clocks.wall = self.proposal['expires_at'] - 200
        clock.reset_process_anchor()
        stage = self.approval()
        self.assertEqual((stage['status'], stage.get('recorded')), ('expired', True))
        self.assertIn('recorded; a clock that reads earlier does not reopen it', _approval_text(stage, stage['status']))
        review = maintenance.review(self.operation)
        self.assertIn('approval window has closed', lifecycle_next(4, review, self.clocks.now()))

    def test_a_damaged_clock_record_reads_as_unknown_and_refused(self):
        from intune_iac.workbench_screens import lifecycle_next
        (self.operation / 'executor' / 'clock.json').write_text('not json')
        self.assertEqual(self.window(), 'unknown')
        self.assertEqual(self.approval()['status'], 'clock_unreadable')
        self.assertIn("recorded time cannot be read, so execute refuses it",
                      lifecycle_next(4, maintenance.review(self.operation), self.clocks.now()))

    def test_the_held_and_unreadable_windows_read_as_such(self):
        from intune_iac.workbench_screens import _approval_text, lifecycle_next
        stage = {'stage': 'approval', 'status': 'clock_uncertain', 'opens_at': START, 'closes_at': START + 300}
        self.assertIn("held: this host's clock reads earlier than a time this operation recorded",
                      _approval_text(stage, 'clock_uncertain'))
        self.assertIn("recorded time cannot be read", _approval_text(dict(stage, status='clock_unreadable'), 'clock_unreadable'))
        review = {'status': 'prepared', 'approval_window': {'state': 'clock_moved_backward'}, 'expires_at': START + 300}
        self.assertIn("this host's clock reads earlier than this operation's recorded time, so execute holds it",
                      lifecycle_next(4, review, START))

    def test_the_plan_review_names_the_window_for_a_prepared_plan_only(self):
        from plugin_tests.test_workbench_words import ReviewWordTests, text
        value = {'operation_id': 'a' * 32, 'status': 'prepared', 'approval_digest': 'b' * 64, 'expires_at': START + 300,
                 'approval_window': {'state': 'clock_moved_backward'}}
        lines = text(ReviewWordTests.workspace(self, 4, value)._surface_summary(160))
        self.assertIn("Approval window: held: this host's clock reads earlier than a time this operation recorded", lines)
        lines = text(ReviewWordTests.workspace(self, 4, dict(value, status='outcome_unknown'))._surface_summary(160))
        self.assertNotIn('Approval window', lines)
