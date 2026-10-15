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


class SourceEditWindowTests(unittest.TestCase):
    setUp = base.NativeSourceEditTests.setUp
    apply = base.NativeSourceEditTests.apply
    operation = base.NativeSourceEditTests.operation
    recover = base.NativeSourceEditTests.recover

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

    def test_a_deadline_reached_between_the_renames_stops_the_partial_edit_until_fresh_recovery(self):
        with self.monotonic_jumps_when(lambda: self.api.renames >= 1), self.assertRaises(AppError) as caught:
            self.apply()
        self.assertEqual(caught.exception.code, 'windows_source_edit_ack_expired')
        self.assertEqual(self.api.renames, 1)
        self.assertFalse((self.real / 'stacks/defaults.yaml').exists())
        self.recover('rollback')
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

    def test_an_open_window_still_applies_and_recovers(self):
        result = self.apply()
        self.assertEqual(result['state'], 'source_applied')
        self.assertEqual(self.api.renames, 2)


if __name__ == '__main__':
    unittest.main()
