"""A job prepared under an earlier implementation cannot recover, and can be cancelled only administratively
(PKG-TIME-AUTHZ-B fix round 3, item 3).

Recovery is not a read: it calls the host and writes operational state. So recover runs the current-implementation gate
before any transaction or host call, for adoption and recovery-plan jobs. Cancel stops a job and calls no host, but a
cancellation from a stale record is still an action: the normal cancel refuses an earlier-set job too, and an explicit
administrative cancel stays available. It makes no host call and records in its event that the job implementation is
not current. A normal cancel of a current job is unchanged.
"""
import sqlite3
import unittest
from unittest.mock import patch

from intune_iac import protected, protected_worker as worker
from intune_iac import worker_adoption as adoption
from intune_iac import worker_adoption_reconcile as bridge
from intune_iac.io import AppError, load_json
from plugin_tests import test_adoption_expiry_latch as adoption_tests
from plugin_tests import test_adoption_recovery_expiry_latch as recovery_tests
from plugin_tests import test_service_expiry_latch as service_tests
from intune_iac import worker_service as service
from plugin_tests import test_protected_worker_r4 as worker_base
from intune_iac import implementation_history as history


def forbidden(name):
    def call(*args, **kwargs):
        raise AssertionError(name + ' was called for a job whose implementation is not current')
    return call


class WorkerCancelTests(unittest.TestCase):
    setUp = worker_base.ProtectedWorkerTests.setUp
    prepare = worker_base.ProtectedWorkerTests.prepare
    job = worker_base.ProtectedWorkerTests.job

    def row(self):
        connection = sqlite3.connect(self.job().policy.database)
        try:
            return connection.execute('SELECT status, cancel_requested FROM jobs').fetchone()
        finally:
            connection.close()

    def events(self):
        connection = sqlite3.connect(self.job().policy.database)
        try:
            return [load_json_text(p) for (p,) in connection.execute("SELECT payload FROM events WHERE kind='cancellation_requested'")]
        finally:
            connection.close()

    def prepare_under_the_earlier_set(self):
        earlier = dict(next(e for e in reversed(history.WORKER_INVENTORY)
                            if set(e['files']) == set(history.WORKER_COMPONENTS_EARLIER))['files'])
        self.assertNotEqual(set(earlier), set(worker._implementation()))
        with patch.object(worker, '_implementation', return_value=dict(earlier)):
            self.prepare()

    def test_a_normal_cancel_of_an_earlier_set_job_is_refused_and_changes_nothing(self):
        self.prepare_under_the_earlier_set()
        with patch.object(protected, 'inspect_executor', forbidden('inspect_executor')):
            with self.assertRaises(AppError) as raised:
                self.job().cancel()
        self.assertEqual(raised.exception.code, 'worker_implementation_changed')
        self.assertEqual(self.row(), ('prepared', 0))
        self.assertEqual(self.events(), [])

    def test_an_administrative_cancel_works_calls_nothing_and_records_that_the_implementation_is_not_current(self):
        self.prepare_under_the_earlier_set()
        with patch.object(protected, 'inspect_executor', forbidden('inspect_executor')), \
                patch.object(worker.WorkerJob, '_apply', forbidden('_apply')):
            result = self.job().cancel(administrative=True)
        self.assertTrue(result['cancellation_requested'])
        self.assertEqual(self.row(), ('cancelled_before_dispatch', 1))
        self.assertEqual(self.events(), [{'before_dispatch': True, 'administrative': True, 'implementation_current': False}])

    def test_a_normal_cancel_of_a_current_job_is_unchanged(self):
        self.prepare()
        self.assertTrue(self.job().cancel()['cancellation_requested'])
        self.assertEqual(self.events(), [{'before_dispatch': True}])


def load_json_text(text):
    import json
    return json.loads(text)


class AdoptionJobTests(adoption_tests.AdoptionFixture):
    def upgrade(self):
        self.controller_files = {'fixture/controller.py': 'b' * 64}  # the controller changed after the job was prepared

    def state(self):
        return (self.job_row(), self.rows('SELECT cancelled FROM jobs'), self.rows('SELECT kind FROM events'),
                self.rows('SELECT status, controller_pid FROM jobs'))

    def outstanding(self, start='the-dead-controller', status='running'):
        """A job the earlier controller dispatched: running, with that controller's identity recorded."""
        with self.policy.connection() as db:
            db.execute("UPDATE jobs SET status=?, dispatches=1, controller_pid=999999, controller_start=? WHERE id=?",
                       (status, start, self.job.identifier))

    def test_an_outstanding_job_of_another_controller_is_recovered_to_outcome_unknown_without_a_host_call(self):
        self.upgrade()
        self.outstanding()
        with patch.object(adoption.AdoptionJob, 'status', return_value={}), \
                patch.object(adoption.host, 'recover', side_effect=AssertionError('the host was touched')) as host:
            self.job.recover()
        host.assert_not_called()
        self.assertEqual(self.rows('SELECT status, cancelled, dispatches, controller_pid, controller_start FROM jobs'),
                         [('outcome_unknown', 1, 1, None, None)])
        self.assertEqual(len(self.rows("SELECT kind FROM events WHERE kind='adoption_recovery_no_replay'")), 1)

    def test_a_job_whose_other_controller_is_alive_is_not_recovered_without_the_gate_either(self):
        self.upgrade()
        self.outstanding(start='controller-start')  # the patched identity of that pid matches: it is alive
        with patch.object(adoption.AdoptionJob, 'status', return_value={}), \
                patch.object(adoption.host, 'recover', side_effect=AssertionError('the host was touched')):
            with self.assertRaises(AppError) as raised:
                self.job.recover()
        self.assertEqual(raised.exception.code, 'adoption_cleanup_owner_active')
        self.assertEqual(self.rows('SELECT status, controller_pid FROM jobs'), [('running', 999999)])

    def test_an_outstanding_job_of_another_controller_can_be_cancelled_with_no_host_call(self):
        self.upgrade()
        self.outstanding()
        with patch.object(adoption.AdoptionJob, 'status', return_value={}), \
                patch.object(adoption.host, 'recover', side_effect=AssertionError('the host was touched')):
            self.job.cancel()
        self.assertEqual(self.rows('SELECT status, cancelled FROM jobs'), [('running', 1)])
        event = self.rows("SELECT payload FROM events WHERE kind='adoption_cancel_requested'")
        self.assertEqual([load_json_text(p) for (p,) in event], [{'dispatch_replayed': False}])

    def test_an_administrative_cancel_still_records_why(self):
        self.upgrade()
        with patch.object(adoption.AdoptionJob, 'status', return_value={}), \
                patch.object(adoption.host, 'recover', side_effect=AssertionError('the host was touched')):
            self.job.cancel(administrative=True)
        self.assertEqual(self.rows('SELECT cancelled FROM jobs'), [(1,)])
        event = self.rows("SELECT payload FROM events WHERE kind='adoption_cancel_requested'")
        self.assertEqual([load_json_text(p) for (p,) in event],
                         [{'dispatch_replayed': False, 'administrative': True, 'implementation_current': False}])

    def test_cancel_and_recover_of_a_current_job_are_unchanged(self):
        with patch.object(adoption.AdoptionJob, 'status', return_value={}), \
                patch.object(adoption.host, 'recover', return_value={}):
            self.job.cancel()
            self.job.recover()
        events = self.rows("SELECT payload FROM events WHERE kind='adoption_cancel_requested'")
        self.assertEqual([load_json_text(p) for (p,) in events], [{'dispatch_replayed': False}])
        self.assertEqual(self.rows("SELECT kind FROM events WHERE kind='adoption_recovery_no_replay'"), [('adoption_recovery_no_replay',)])


class RecoveryPlanJobTests(recovery_tests.RecoveryFixture):
    def upgrade(self):
        self.controller_files = {'fixture/controller.py': 'b' * 64}

    def state(self):
        return (self.rows('SELECT status, cancelled, dispatches FROM adoption_recovery_plans'), self.rows('SELECT kind FROM events'))

    def outstanding(self, start='the-dead-controller'):
        """A plan the earlier controller dispatched: running, with that controller's identity recorded."""
        with self.policy.connection() as db:
            db.execute("UPDATE adoption_recovery_plans SET status='running', dispatches=1, controller_pid=999999, "
                       "controller_start=? WHERE operation_id=?", (start, self.job.identifier))

    def test_an_outstanding_plan_of_another_controller_is_recovered_to_outcome_unknown_without_a_host_call(self):
        self.upgrade()
        self.outstanding()
        with patch.object(bridge.RecoveryPlanJob, 'status', return_value={}), \
                patch.object(bridge.host, 'recover', side_effect=AssertionError('the host was touched')) as host:
            self.job.recover()
        host.assert_not_called()
        self.assertEqual(self.rows('SELECT status, cancelled, dispatches, controller_pid, controller_start FROM adoption_recovery_plans'),
                         [('outcome_unknown', 1, 1, None, None)])
        self.assertEqual(len(self.rows("SELECT kind FROM events WHERE kind='adoption_recovery_plan_stopped_no_replay'")), 1)

    def test_a_plan_whose_other_controller_is_alive_is_not_recovered_without_the_gate_either(self):
        self.upgrade()
        self.outstanding(start='controller-start')
        with patch.object(bridge.RecoveryPlanJob, 'status', return_value={}), \
                patch.object(bridge.host, 'recover', side_effect=AssertionError('the host was touched')):
            with self.assertRaises(AppError) as raised:
                self.job.recover()
        self.assertEqual(raised.exception.code, 'adoption_recovery_controller_active')
        self.assertEqual(self.rows('SELECT status, controller_pid FROM adoption_recovery_plans'), [('running', 999999)])

    def test_an_outstanding_plan_of_another_controller_can_be_cancelled_with_no_host_call(self):
        self.upgrade()
        self.outstanding()
        with patch.object(bridge.RecoveryPlanJob, 'status', return_value={}), \
                patch.object(bridge.host, 'recover', side_effect=AssertionError('the host was touched')):
            self.job.cancel()
        self.assertEqual(self.rows('SELECT status, cancelled FROM adoption_recovery_plans'), [('running', 1)])

    def test_an_administrative_cancel_still_records_why(self):
        self.upgrade()
        with patch.object(bridge.RecoveryPlanJob, 'status', return_value={}):
            self.job.cancel(administrative=True)
        self.assertEqual(self.rows('SELECT cancelled FROM adoption_recovery_plans'), [(1,)])
        event = self.rows("SELECT payload FROM events WHERE kind='adoption_recovery_plan_cancel_requested'")
        self.assertEqual([load_json_text(p) for (p,) in event],
                         [{'operation_id': self.job.identifier, 'ownership_released': False,
                           'administrative': True, 'implementation_current': False}])

    def test_cancel_and_recover_of_a_current_job_are_unchanged(self):
        with patch.object(bridge.RecoveryPlanJob, 'status', return_value={}), \
                patch.object(bridge.host, 'recover', return_value={}):
            self.job.cancel()
            self.job.recover()
        events = self.rows("SELECT payload FROM events WHERE kind='adoption_recovery_plan_cancel_requested'")
        self.assertEqual([load_json_text(p) for (p,) in events],
                         [{'operation_id': self.job.identifier, 'ownership_released': False}] * 2)


class ServiceJobTests(service_tests.ServiceFixture):
    """The service job (PKG-TIME-AUTHZ-C fix round): the same gate, the same administrative path."""
    def setUp(self):
        super().setUp()
        self.controller_files = {'fixture/controller.py': 'a' * 64}
        self.job.manifest['implementation_files'] = dict(self.controller_files)
        patcher = patch.object(service, 'implementation_binding', side_effect=lambda: dict(self.controller_files))
        patcher.start()
        self.addCleanup(patcher.stop)

    def upgrade(self):
        self.controller_files = {'fixture/controller.py': 'b' * 64}  # the controller changed after the job was prepared

    def state(self):
        return (self.rows('SELECT status, cancelled, dispatches, controller_pid FROM jobs'), self.rows('SELECT kind FROM events'),
                self.rows('SELECT scope, job FROM ownership'))

    def outstanding(self, pid=999999, start='the-dead-controller'):
        """A job the earlier controller dispatched: running, with that controller's identity recorded."""
        with self.policy.connection() as db:
            db.execute("UPDATE jobs SET status='running', dispatches=1, controller_pid=?, controller_start=? WHERE id=?",
                       (pid, start, self.job.identifier))

    def test_an_outstanding_job_of_another_controller_is_recovered_to_outcome_unknown_without_a_host_call(self):
        self.upgrade()
        self.outstanding()
        with patch.object(service.host, 'recover', side_effect=AssertionError('the host was touched')) as host:
            self.job.recover()
        host.assert_not_called()
        self.assertEqual(self.rows('SELECT status, cancelled, dispatches, controller_pid, controller_start FROM jobs'),
                         [('outcome_unknown', 1, 1, None, None)])

    def test_a_job_whose_other_controller_is_alive_is_not_recovered_without_the_gate_either(self):
        self.upgrade()
        self.outstanding(start='controller-start')  # the patched identity of that pid matches: it is alive
        with patch.object(service.host, 'recover', side_effect=AssertionError('the host was touched')):
            with self.assertRaises(AppError) as raised:
                self.job.recover()
        self.assertEqual(raised.exception.code, 'service_cleanup_owner_active')
        self.assertEqual(self.rows('SELECT status, controller_pid FROM jobs'), [('running', 999999)])

    def test_an_outstanding_job_of_another_controller_can_be_cancelled_with_no_host_call(self):
        self.upgrade()
        self.outstanding()
        with patch.object(service.host, 'recover', side_effect=AssertionError('the host was touched')):
            self.job.cancel()
        self.assertEqual(self.rows('SELECT status, cancelled FROM jobs'), [('running', 1)])
        event = self.rows("SELECT payload FROM events WHERE kind='cancel_requested'")
        self.assertEqual([load_json_text(p) for (p,) in event], [{'dispatch_replayed': False}])

    def test_an_administrative_cancel_still_records_why(self):
        self.upgrade()
        with patch.object(service.host, 'recover', side_effect=AssertionError('the host was touched')):
            self.job.cancel(administrative=True)
        self.assertEqual(self.rows('SELECT cancelled FROM jobs'), [(1,)])
        event = self.rows("SELECT payload FROM events WHERE kind='cancel_requested'")
        self.assertEqual([load_json_text(p) for (p,) in event],
                         [{'dispatch_replayed': False, 'administrative': True, 'implementation_current': False}])

    def test_cancel_and_recover_of_a_current_job_are_unchanged(self):
        with patch.object(service.host, 'recover', return_value={}):
            self.job.cancel()
            self.job.recover()
        events = self.rows("SELECT payload FROM events WHERE kind='cancel_requested'")
        self.assertEqual([load_json_text(p) for (p,) in events], [{'dispatch_replayed': False}])
        self.assertEqual(self.rows("SELECT kind FROM events WHERE kind='recovery_no_replay'"), [('recovery_no_replay',)])


if __name__ == '__main__':
    unittest.main()
