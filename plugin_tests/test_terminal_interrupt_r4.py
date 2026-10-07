"""Actual SIGINT in SQLite callbacks must not become a recoverable UI error."""
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

from intune_iac.workbench import run_terminal
from intune_iac.workbench_store import WorkbenchStore


@unittest.skipUnless(os.name == 'posix', 'Actual POSIX signal delivery')
class TerminalInterruptTests(unittest.TestCase):
    def test_sqlite_callback_interrupt_closes_before_next_command(self):
        with tempfile.TemporaryDirectory() as directory:
            store = WorkbenchStore.create(Path(directory) / 'store', '11111111-1111-4111-8111-111111111111')
            original = WorkbenchStore._query_budget
            armed = False
            delivered = 0
            inputs = []
            results = []
            previous = signal.getsignal(signal.SIGINT)

            @contextmanager
            def callback_budget(db):
                with original(db) as charge:
                    def callback():
                        nonlocal armed, delivered
                        if armed:
                            armed = False
                            delivered += 1
                            os.kill(os.getpid(), signal.SIGINT)
                        return 0
                    db.set_progress_handler(callback, 1)
                    yield charge

            def read(_prompt):
                nonlocal armed
                inputs.append(len(inputs))
                if len(inputs) == 1:
                    armed = True
                    return 'overview'
                return 'quit'

            with patch.object(WorkbenchStore, '_query_budget', staticmethod(callback_budget)):
                result = run_terminal(store.root, input_fn=read, result_fn=results.append)
            self.assertEqual(delivered, 1, 'Signal was sent inside an actual SQLite progress callback')
            self.assertEqual(result['status'], 'interrupted')
            self.assertEqual(len(inputs), 1, 'No subsequent command may dispatch after swallowed SIGINT')
            self.assertEqual(signal.getsignal(signal.SIGINT), previous)
            self.assertFalse(any(row.get('error', {}).get('code') == 'workbench_database_error' for row in results))


if __name__ == '__main__':
    unittest.main()
