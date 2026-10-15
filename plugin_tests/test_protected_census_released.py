"""A task the kernel is releasing must not make protected cleanup unverifiable (DEF-CENSUS-RELEASED-TASK).

Linux's do_task_stat starts pgrp and session at -1 and fills them only while it can lock the task's signal state, which is
gone once the task is released (state X). The cleanup census reads every process on the host, so it can meet such a line
for a task of another process group, or for a thread listed under our own group's leader. The line is a task that can
never run again; every other negative or inconsistent value stays malformed and fails closed.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import protected
from intune_iac.io import AppError

# The record E1 captured for a /bin/true of another process group, completed with plausible values up to the start time
# (field 22): state X, ppid 0, pgrp -1, session -1, tty 0, tpgid -1, flags 4227084, minflt 352, ...
E1_LINE = b'887361 (true) X 0 -1 -1 0 -1 4227084 352 0 0 0 0 0 0 0 20 0 1 0 5364178 0 0 18446744073709551615 0 0\n'


def stat_line(state, pgrp, session, starttime=5364178, pid=887361):
    fields = [state, '1', str(pgrp), str(session), '0', '-1', '4227084', '0', '0', '0', '0', '0', '0', '0', '0',
              '20', '0', '1', '0', str(starttime), '0', '0']
    return ('%d (true) %s\n' % (pid, ' '.join(fields))).encode()


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'stat'

    def test_the_exact_e1_line_reads_as_a_released_task(self):
        self.path.write_bytes(E1_LINE)
        value = protected._read_process_stat(self.path)
        self.assertEqual((value['pid'], value['state'], value['pgrp'], value['session']), (887361, 'X', -1, -1))

    def test_a_lowercase_x_released_task_reads_the_same_way(self):
        self.path.write_bytes(stat_line('x', -1, -1))
        value = protected._read_process_stat(self.path)
        self.assertEqual((value['state'], value['pgrp'], value['session']), ('x', -1, -1))

    def test_every_other_negative_or_inconsistent_value_is_still_refused(self):
        cases = {
            'live state with pgrp -1': stat_line('S', -1, -1),
            'live state with pgrp -1 and a valid session': stat_line('S', -1, 5),
            'running state with pgrp -1': stat_line('R', -1, 5),
            'zombie with pgrp -1': stat_line('Z', -1, -1),
            'released with pgrp -1 and session 0': stat_line('X', -1, 0),
            'released with pgrp 0 and session -1': stat_line('X', 0, -1),
            'released with only the session negative': stat_line('X', 5, -1),
            'released with only the pgrp negative': stat_line('X', -1, 5),
            'released with pgrp -2 and session -2': stat_line('X', -2, -2),
            'released with a negative start time': stat_line('X', -1, -1, starttime=-1),
            'live with a negative start time': stat_line('S', 5, 5, starttime=-1),
        }
        for name, data in cases.items():
            with self.subTest(name):
                self.path.write_bytes(data)
                with self.assertRaises(AppError) as raised:
                    protected._read_process_stat(self.path)
                self.assertEqual(raised.exception.code, 'process_cleanup_observation_invalid')

    def test_a_consistent_live_record_is_unchanged(self):
        self.path.write_bytes(stat_line('S', 73, 73))
        value = protected._read_process_stat(self.path)
        self.assertEqual((value['state'], value['pgrp'], value['session']), ('S', 73, 73))


class CensusTests(unittest.TestCase):
    """Real /bin/true children, with the stat reader wrapped so that one entry reads as the released line."""

    def setUp(self):
        self.original = protected._read_process_stat
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)

    def released(self, pid):
        """What the real parser makes of the released line for pid (a refusal on a parser that rejects it)."""
        path = Path(self.directory.name) / ('stat-%d' % pid)
        path.write_bytes(stat_line('X', -1, -1, pid=pid))
        return self.original(path)

    def spawn(self):
        process = subprocess.Popen(['/bin/true'], start_new_session=True)
        self.addCleanup(process.wait)
        return process

    @contextmanager
    def reading(self, wrapper):
        with patch.object(protected, '_read_process_stat', side_effect=wrapper):
            yield

    def cleanup(self, process, wrapper):
        evidence = {}
        with self.reading(wrapper):
            try:
                protected._cleanup_process_group(process, evidence=evidence)
            except AppError as error:
                return error.code, evidence
        return None, evidence

    @staticmethod
    def is_task_of(path, pid):
        return len(path.parts) == 6 and path.parts[2:4] == (str(pid), 'task') and path.name == 'stat'

    def test_a_released_foreign_entry_does_not_make_cleanup_unverifiable(self):
        process = self.spawn(); foreign = os.getpid(); seen = []
        def wrapper(path):
            path = Path(path)
            if len(path.parts) == 4 and path.parts[2] == str(foreign) and path.name == 'stat':
                seen.append(path); return self.released(foreign)
            return self.original(path)
        code, evidence = self.cleanup(process, wrapper)
        self.assertTrue(seen, 'the foreign entry was never read, so the test proves nothing')
        self.assertIsNone(code)
        self.assertEqual(evidence['status'], 'confirmed')
        self.assertTrue(evidence['direct_child_reaped'])

    def test_a_released_thread_of_our_own_leader_is_an_exited_member(self):
        process = self.spawn(); seen = []
        def wrapper(path):
            path = Path(path)
            if self.is_task_of(path, process.pid):
                seen.append(path); return self.released(int(path.parts[4]))
            return self.original(path)
        code, evidence = self.cleanup(process, wrapper)
        self.assertTrue(seen, 'the thread entry was never read, so the test proves nothing')
        self.assertIsNone(code)
        self.assertEqual(evidence['status'], 'confirmed')
        self.assertEqual(evidence['live_members'], [])

    def test_a_live_state_in_our_group_still_blocks_confirmation_until_it_is_gone(self):
        for state in ('S', 'R'):
            with self.subTest(state=state):
                process = self.spawn(); reads = []
                def wrapper(path):
                    path = Path(path); value = self.original(path)
                    if self.is_task_of(path, process.pid):
                        reads.append(path)
                        if len(reads) <= 3: return dict(value, state=state)
                    return value
                code, evidence = self.cleanup(process, wrapper)
                self.assertIsNone(code)
                self.assertGreater(len(reads), 3)
                self.assertGreaterEqual(evidence['observations'], 5)
                self.assertEqual(evidence['status'], 'confirmed')

    def test_a_live_state_that_never_goes_away_is_never_confirmed(self):
        process = self.spawn()
        def wrapper(path):
            path = Path(path); value = self.original(path)
            return dict(value, state='S') if self.is_task_of(path, process.pid) else value
        with patch.object(protected, 'PROCESS_CLEANUP_TIMEOUT', 0.2):
            code, evidence = self.cleanup(process, wrapper)
        self.assertEqual(code, 'process_cleanup_timeout')
        self.assertEqual(evidence['status'], 'unverified')

    def test_a_released_anchor_still_fails_as_anchor_lost(self):
        process = self.spawn()
        def wrapper(path):
            path = Path(path)
            if len(path.parts) == 4 and path.parts[2] == str(process.pid) and path.name == 'stat':
                return self.released(process.pid)
            return self.original(path)
        code, evidence = self.cleanup(process, wrapper)
        self.assertEqual(code, 'process_cleanup_unverified')
        self.assertEqual(evidence['observation_error'], 'process_cleanup_anchor_lost')
        self.assertEqual(evidence['status'], 'unverified')


if __name__ == '__main__':
    unittest.main()
