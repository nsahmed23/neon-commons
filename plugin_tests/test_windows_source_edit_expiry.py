"""A local source edit cannot cross its acknowledged expiry while the wall clock stays inside it (PKG-TIME-AUTHZ-C).

apply_source_proposal and recover_source_edit judge the acknowledgment's expires_at on the bare wall clock before the
first rename, between the two renames and before every recovery rename. A wall clock that stepped back (or stood still)
while real time passed let the edit go on past the expiry the operator acknowledged.

The acknowledgment is an operator's local statement (acknowledged=True, the actor's SID, a caller-supplied expires_at),
not an authenticated artefact a store could latch: a later, legitimate acknowledgment carries a new expires_at and so a new
operation. The durable record that exists is the append-only source journal, and it already refuses a replay of the same
operation. What is added is the local elapsed deadline: each call arms its monotonic deadline when the acknowledgment is
accepted, and the call stops at either clock. A stop between the renames leaves the same recoverable partial state the
wall-clock stop always did.

Each test drives the public entry points (_apply, _recover) of the recorded Win32 model used by
test_windows_source_edit_r4, with the monotonic clock jumped while the wall clock stays inside the window.
"""
import time
import unittest
from unittest.mock import patch

from intune_iac import windows_source_edit as subject
from intune_iac.io import AppError
from plugin_tests import test_windows_source_edit_r4 as base
from plugin_tests.test_clock_authority import Clocks


class SourceEditWindowTests(unittest.TestCase):
    setUp = base.NativeSourceEditTests.setUp
    apply = base.NativeSourceEditTests.apply
    operation = base.NativeSourceEditTests.operation
    recover = base.NativeSourceEditTests.recover
    inspect = base.NativeSourceEditTests.inspect

    def monotonic_jumps_when(self, condition):
        """The monotonic clock runs an hour ahead from the moment condition() is true; the wall clock does not move."""
        real = time.monotonic
        return patch.object(subject.time, 'monotonic', side_effect=lambda: real() + (3600 if condition() else 0))

    def test_a_deadline_reached_before_the_first_rename_stops_the_edit_with_nothing_renamed(self):
        candidate_prepared = lambda: any(event[0] == 'clone-metadata' for event in self.api.events)
        with self.monotonic_jumps_when(candidate_prepared), self.assertRaises(AppError) as caught:
            self.apply()
        self.assertEqual(caught.exception.code, 'windows_source_edit_ack_expired')
        self.assertEqual(self.api.renames, 0)
        self.assertEqual((self.real / 'stacks/defaults.yaml').read_bytes(), self.before)

    def test_a_deadline_reached_between_the_renames_does_not_leave_the_source_moved_away(self):
        # The window bounds when the edit may start (before the first rename); it is not judged between the two renames,
        # where a refusal would leave the source file moved away and the repository blocked on an unresolved edit.
        with self.monotonic_jumps_when(lambda: self.api.renames >= 1):
            result = self.apply()
        self.assertEqual(result['state'], 'source_applied')
        self.assertEqual(self.api.renames, 2)
        self.assertEqual((self.real / 'stacks/defaults.yaml').read_bytes(), self.after)
        self.assertTrue(self.inspect()['closed'])

    def test_a_recovery_judges_its_window_once_before_the_first_rename_not_between_renames(self):
        self.api.fail_after = 2
        with self.assertRaises(AppError):
            self.apply()  # the second rename's acknowledgment is lost: the candidate is applied and no closure is recorded
        self.assertEqual(self.api.renames, 2)
        with self.monotonic_jumps_when(lambda: self.api.renames >= 3):
            result = subject._recover(self.store, self.root, self.operation(), 'rollback', time.time() + 600, True, self.api)
        self.assertEqual(result['state'], 'source_restored')  # both rollback renames ran although the deadline passed between them
        self.assertEqual(self.api.renames, 4)
        self.assertEqual((self.real / 'stacks/defaults.yaml').read_bytes(), self.before)

    def test_a_recovery_stops_before_its_rename_when_the_deadline_is_reached(self):
        self.api.fail_after = 1
        with self.assertRaises(AppError):
            self.apply()  # the first rename's acknowledgment is lost: the backup exists and the candidate is ready
        self.assertEqual(self.api.renames, 1)
        recorded = []
        real = subject.ws._create_file

        def create(parent, name, data, api):
            result = real(parent, name, data, api)
            if name.endswith('.recovery.json'):
                recorded.append(name)  # the recovery intent is recorded: its deadline has been armed
            return result
        with patch.object(subject.ws, '_create_file', create), self.monotonic_jumps_when(lambda: bool(recorded)), \
                self.assertRaises(AppError) as caught:
            subject._recover(self.store, self.root, self.operation(), 'complete', time.time() + 600, True, self.api)
        self.assertEqual(caught.exception.code, 'windows_source_edit_ack_expired')
        self.assertEqual(self.api.renames, 1)

    def injected(self):
        clocks = Clocks(time.time())
        for name, function in (('time', clocks.time), ('monotonic', clocks.monotonic)):
            patcher = patch.object(subject.time, name, side_effect=function)
            patcher.start()
            self.addCleanup(patcher.stop)
        return clocks

    def rolled_back_after_accepting(self, clocks, seconds=100):
        """The acknowledgment is accepted, and then the wall clock steps back before anything else is done."""
        real = subject._acknowledge

        def acknowledge_then_step_back(*args, **kwargs):
            result = real(*args, **kwargs)
            clocks.step(-seconds)
            return result
        return patch.object(subject, '_acknowledge', side_effect=acknowledge_then_step_back)

    def test_a_wall_step_between_accepting_the_acknowledgment_and_arming_the_window_does_not_extend_the_edit(self):
        clocks = self.injected()
        expires = clocks.time() + 10  # accepted with ten seconds left
        candidate_prepared = lambda: any(event[0] == 'clone-metadata' for event in self.api.events)
        real = clocks.monotonic
        with self.rolled_back_after_accepting(clocks), \
                patch.object(subject.time, 'monotonic', side_effect=lambda: real() + (11 if candidate_prepared() else 0)), \
                self.assertRaises(AppError) as caught:
            self.apply(expires=expires)  # eleven real seconds pass before the first rename
        self.assertEqual(caught.exception.code, 'windows_source_edit_ack_expired')
        self.assertEqual(self.api.renames, 0)
        self.assertEqual((self.real / 'stacks/defaults.yaml').read_bytes(), self.before)

    def test_the_same_holds_for_a_recovery_acknowledgment(self):
        self.api.fail_after = 1
        with self.assertRaises(AppError):
            self.apply()  # the first rename's acknowledgment is lost: the backup exists and the candidate is ready
        operation = self.operation()
        clocks = self.injected()
        recorded = []
        real_create, real = subject.ws._create_file, clocks.monotonic

        def create(parent, name, data, api):
            result = real_create(parent, name, data, api)
            if name.endswith('.recovery.json'):
                recorded.append(name)
            return result
        with self.rolled_back_after_accepting(clocks), patch.object(subject.ws, '_create_file', create), \
                patch.object(subject.time, 'monotonic', side_effect=lambda: real() + (11 if recorded else 0)), \
                self.assertRaises(AppError) as caught:
            subject._recover(self.store, self.root, operation, 'complete', clocks.time() + 10, True, self.api)
        self.assertEqual(caught.exception.code, 'windows_source_edit_ack_expired')
        self.assertEqual(self.api.renames, 1)

    def test_an_open_window_still_applies_and_recovers(self):
        result = self.apply()
        self.assertEqual(result['state'], 'source_applied')
        self.assertEqual(self.api.renames, 2)


class ReplayRecordOrderTests(unittest.TestCase):
    """The acknowledgment's replay record is the intent journal: it is committed durably, under the source lock, before the
    candidate exists or anything is renamed, so a call that dies at any later point cannot be replayed."""
    setUp = base.NativeSourceEditTests.setUp
    apply = base.NativeSourceEditTests.apply

    def test_the_intent_is_flushed_before_the_candidate_is_prepared_or_anything_is_renamed(self):
        start = len(self.api.events)
        self.apply()
        events = self.api.events[start:]
        intent = [number for number, event in enumerate(events)
                  if event[0] == 'flush-file' and subject.INTENT_SUFFIX in str(event[1])]
        staged = [number for number, event in enumerate(events) if '.candidate' in str(event[1])]
        self.assertEqual(len(intent), 1)
        self.assertTrue(staged)
        self.assertLess(intent[0], staged[0])  # the replay record is flushed before the candidate file is even created
        barrier = [number for number, event in enumerate(events) if event[0] == 'flush-namespace' and intent[0] < number < staged[0]]
        self.assertTrue(barrier)  # and the namespace flush that makes its name durable comes before the candidate too

    def test_a_call_that_dies_before_the_first_rename_cannot_be_replayed(self):
        self.api.fail_before = 1
        with self.assertRaises(KeyboardInterrupt):
            self.apply()
        self.api.fail_before = None
        self.assertEqual(self.api.renames, 1)  # the first rename was dispatched and never completed
        with self.assertRaises(AppError) as caught:
            self.apply()
        self.assertEqual(caught.exception.code, 'windows_source_edit_replay_denied')
        self.assertEqual(self.api.renames, 1)  # the replay did not reach a rename
        self.assertEqual((self.real / 'stacks/defaults.yaml').read_bytes(), self.before)

    def test_a_call_refused_after_the_intent_is_recorded_cannot_be_replayed(self):
        self.api.fail_clone = True  # the candidate cannot be prepared: the call is refused after the intent was recorded
        with self.assertRaises(AppError):
            self.apply()
        self.api.fail_clone = False
        with self.assertRaises(AppError) as caught:
            self.apply()
        self.assertEqual(caught.exception.code, 'windows_source_edit_replay_denied')
        self.assertEqual(self.api.renames, 0)


if __name__ == '__main__':
    unittest.main()
