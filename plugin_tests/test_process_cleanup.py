"""Immediate, independent process-state assertions for both local supervisors.

Only protected-fixture tests disable its no-fork guard. Provider tests retain
their actual guard (fork allowed; setsid/setpgid denied). These are local
same-process-group tests, not hostile-host containment or escaped-group proof.
"""
from contextlib import nullcontext
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from intune_iac import protected, provider_execution
from intune_iac.io import AppError


class ProcessCleanupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.python = str(Path(sys.executable).resolve())

    def call(self, profile, code, *, evidence=None, **kwargs):
        argv = [self.python, '-I', '-S', '-c', code]
        if profile == 'protected':
            return protected._supervise(argv, cwd=self.root, env={}, evidence=evidence, **kwargs)
        return provider_execution._supervise(argv, cwd=self.root, env={}, executable=self.python,
                                              pass_fds=(), evidence=evidence, **kwargs)

    def fork_fixture(self, profile):
        return (patch.object(protected, '_network_filter', return_value=(lambda: None, lambda: None))
                if profile == 'protected' else nullcontext())

    def assert_stopped(self, pid):
        # Independent parser includes every remaining thread, not just leader.
        tasks = Path('/proc') / str(pid) / 'task'
        try: entries = list(tasks.iterdir())
        except FileNotFoundError: return
        for task in entries:
            try: data = (task / 'stat').read_bytes()
            except FileNotFoundError: continue
            state = data.rsplit(b') ', 1)[1].split()[0]
            self.assertIn(state, (b'Z', b'X', b'x'), (pid, task.name, state))

    def record_pids(self):
        return [int(p.read_text()) for p in self.root.glob('*.pid')]

    def test_closed_pipe_orphan_is_stopped_before_success_returns_both_profiles(self):
        code = ('import os,time\np=os.fork()\nif p==0:\n'
                ' os.close(1);os.close(2);time.sleep(60)\n'
                'else:\n open("orphan.pid","w").write(str(p))\n')
        for profile in ('protected', 'provider'):
            with self.subTest(profile=profile), self.fork_fixture(profile):
                evidence = {}; self.call(profile, code, evidence=evidence)
                for pid in self.record_pids(): self.assert_stopped(pid)
                self.assertEqual(evidence['process_cleanup']['status'], 'confirmed')
                self.assertTrue(evidence['process_cleanup']['direct_child_reaped'])

    def test_nested_orphans_are_stopped_at_timeout_both_profiles(self):
        code = ('import os,time\np=os.fork()\nif p==0:\n'
                ' q=os.fork()\n if q==0: time.sleep(60)\n'
                ' else: open("grandchild.pid","w").write(str(q));time.sleep(60)\n'
                'else:\n open("child.pid","w").write(str(p))\n')
        for profile in ('protected', 'provider'):
            with self.subTest(profile=profile), self.fork_fixture(profile):
                evidence = {}
                with self.assertRaises(AppError) as raised: self.call(profile, code, timeout=1, evidence=evidence)
                self.assertIn(raised.exception.code, ('process_timeout', 'provider_process_timeout'))
                for pid in self.record_pids(): self.assert_stopped(pid)
                self.assertEqual(evidence['process_cleanup']['status'], 'confirmed')

    def test_output_error_cleans_up_descendant_before_raising(self):
        code = ('import os,time\np=os.fork()\nif p==0: time.sleep(60)\n'
                'else:\n open("output-child.pid","w").write(str(p));print("x"*20000,flush=True);time.sleep(60)\n')
        for profile in ('protected', 'provider'):
            with self.subTest(profile=profile), self.fork_fixture(profile):
                evidence = {}
                with self.assertRaises(AppError): self.call(profile, code, output_limit=1000, evidence=evidence)
                for pid in self.record_pids(): self.assert_stopped(pid)
                self.assertEqual(evidence['process_cleanup']['status'], 'confirmed')

    def test_keyboard_interrupt_still_confirms_descendant_cleanup(self):
        original = protected.selectors.DefaultSelector
        class InterruptingSelector:
            def __init__(self): self.real = original()
            def register(self, *args): return self.real.register(*args)
            def unregister(self, *args): return self.real.unregister(*args)
            def get_map(self): return self.real.get_map()
            def close(self): return self.real.close()
            def select(self, timeout):
                if list(self_root.glob('*.pid')): raise KeyboardInterrupt()
                return self.real.select(timeout)
        self_root = self.root
        code = ('import os,time\np=os.fork()\nif p==0: time.sleep(60)\n'
                'else: open("cancel-child.pid","w").write(str(p));time.sleep(60)\n')
        with self.fork_fixture('protected'), patch.object(protected.selectors, 'DefaultSelector', InterruptingSelector):
            evidence = {}
            with self.assertRaises(KeyboardInterrupt): self.call('protected', code, evidence=evidence)
        for pid in self.record_pids(): self.assert_stopped(pid)
        self.assertEqual(evidence['process_cleanup']['status'], 'confirmed')
        self.assertEqual(evidence['primary_error'], 'KeyboardInterrupt')

    def test_provider_authority_revocation_after_pipes_closed_is_preserved(self):
        calls = []
        def active():
            calls.append(time.monotonic())
            if (self.root / 'ready').exists(): raise AppError('test_revoked', 'Synthetic revocation')
        code = 'import os,time\nos.close(1);os.close(2)\nopen("ready","w").close()\ntime.sleep(60)'
        evidence = {}
        with self.assertRaises(AppError) as raised: self.call('provider', code, evidence=evidence, active_check=active)
        self.assertEqual(raised.exception.code, 'test_revoked')
        self.assertGreater(len(calls), 1)
        self.assertEqual(evidence['process_cleanup']['status'], 'confirmed')

    def test_unobservable_cleanup_fails_closed_with_primary_error_retained(self):
        for profile in ('protected', 'provider'):
            with self.subTest(profile=profile):
                evidence = {}
                with patch.object(protected, '_process_group_members', side_effect=PermissionError('fixture'), create=True):
                    with self.assertRaises(AppError) as raised:
                        self.call(profile, 'raise SystemExit(7)', evidence=evidence)
                self.assertEqual(raised.exception.code, 'process_cleanup_unverified')
                self.assertEqual(evidence['process_cleanup']['status'], 'unverified')
                self.assertTrue(evidence['process_cleanup']['direct_child_reaped'])
                self.assertEqual(evidence['primary_error'], 'process_failed' if profile == 'protected' else None)

    def test_unreadable_anchor_still_kills_and_reaps_known_child(self):
        for profile in ('protected', 'provider'):
            with self.subTest(profile=profile):
                evidence = {}
                code = 'import os,time\nopen("anchor.pid","w").write(str(os.getpid()))\ntime.sleep(60)'
                with patch.object(protected, '_read_process_stat', side_effect=PermissionError('fixture')):
                    with self.assertRaises(AppError) as raised:
                        self.call(profile, code, timeout=1, evidence=evidence)
                self.assertEqual(raised.exception.code, 'process_cleanup_unverified')
                self.assertTrue(evidence['process_cleanup']['direct_child_reaped'])
                self.assertEqual(evidence['primary_error'], 'process_timeout' if profile == 'protected' else 'provider_process_timeout')
                for pid in self.record_pids(): self.assert_stopped(pid)

    def test_stuck_observation_cleanup_is_bounded_and_never_success(self):
        evidence = {}; started = time.monotonic()
        with patch.object(protected, 'PROCESS_CLEANUP_TIMEOUT', 0.05, create=True), \
             patch.object(protected, '_process_group_members', return_value=[{'pid': 123, 'tid': 123, 'state': 'R', 'starttime': 1}], create=True):
            with self.assertRaises(AppError) as raised: self.call('protected', 'pass', evidence=evidence)
        self.assertEqual(raised.exception.code, 'process_cleanup_timeout')
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(evidence['process_cleanup']['status'], 'unverified')

    def test_original_child_reserves_group_id_for_every_cleanup_signal(self):
        actual = os.killpg; observed = []
        def signal_owned_group(pgid, signum):
            # A reaped/reused PID is not a waitable child and fails immediately.
            status = os.waitid(os.P_PID, pgid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            observed.append((pgid, None if status is None else status.si_pid))
            return actual(pgid, signum)
        for profile in ('protected', 'provider'):
            with self.subTest(profile=profile):
                evidence = {}
                with patch.object(protected.os, 'killpg', side_effect=signal_owned_group):
                    self.call(profile, 'pass', evidence=evidence)
                self.assertTrue(observed)
                self.assertTrue(all(pid == child for pid, child in observed))
                with self.assertRaises(ChildProcessError):
                    os.waitid(os.P_PID, evidence['process_cleanup']['group_id'], os.WEXITED | os.WNOHANG | os.WNOWAIT)

    def test_resource_release_failure_does_not_mask_timeout_or_skip_cleanup(self):
        actual = protected._network_filter
        def guarded():
            child, release = actual()
            def failed_release():
                release(); raise RuntimeError('fixture release failure')
            return child, failed_release
        evidence = {}
        with patch.object(protected, '_network_filter', side_effect=guarded):
            with self.assertRaises(AppError) as raised:
                self.call('protected', 'import time;time.sleep(60)', timeout=1, evidence=evidence)
        self.assertEqual(raised.exception.code, 'process_timeout')
        self.assertEqual(evidence['primary_error'], 'process_timeout')
        self.assertEqual(evidence['process_cleanup']['status'], 'confirmed')
        self.assertEqual(evidence['resource_errors'], ['RuntimeError'])

    def test_cleanup_failure_still_closes_selector_and_both_pipes(self):
        actual_spawn = protected.subprocess.Popen
        actual_selector = protected.selectors.DefaultSelector
        processes, selectors = [], []
        def spawn(*args, **kwargs):
            process = actual_spawn(*args, **kwargs); processes.append(process); return process
        def selector():
            value = actual_selector(); selectors.append(value); return value
        evidence = {}
        with patch.object(protected.subprocess, 'Popen', side_effect=spawn), \
             patch.object(protected.selectors, 'DefaultSelector', side_effect=selector), \
             patch.object(protected, '_process_group_members', side_effect=PermissionError('fixture')):
            with self.assertRaises(AppError) as raised: self.call('protected', 'pass', evidence=evidence)
        self.assertEqual(raised.exception.code, 'process_cleanup_unverified')
        self.assertTrue(processes[0].stdout.closed)
        self.assertTrue(processes[0].stderr.closed)
        self.assertIsNone(selectors[0].get_map())
        self.assertTrue(evidence['process_cleanup']['direct_child_reaped'])

    def test_every_resource_release_is_attempted_after_prior_release_failure(self):
        calls = []
        class Resource:
            def __init__(self, name): self.name = name
            def close(self):
                calls.append(self.name)
                if self.name in ('selector', 'stdout'): raise OSError('fixture')
        class Process:
            stdout = Resource('stdout'); stderr = Resource('stderr')
        def release():
            calls.append('guard'); raise RuntimeError('fixture')
        errors = protected._release_process_resources(Process(), Resource('selector'), release)
        self.assertEqual(calls, ['guard', 'selector', 'stdout', 'stderr'])
        self.assertEqual(errors, ['RuntimeError', 'OSError', 'OSError'])

    def test_real_protected_profile_denies_process_creation_and_allows_threads(self):
        code = ('import os,threading\nt=threading.Thread(target=lambda:None);t.start();t.join()\n'
                'try: os.fork()\nexcept PermissionError: print("fork-denied-thread-ok")\n'
                'else: os._exit(8)\n')
        evidence = {}
        self.assertEqual(self.call('protected', code, evidence=evidence), b'fork-denied-thread-ok\n')
        self.assertEqual(evidence['process_cleanup']['status'], 'confirmed')

    def test_real_provider_profile_rejects_descendant_process_group_escape(self):
        code = ('import os\np=os.fork()\nif p==0:\n'
                ' denied=0\n for change in (os.setsid,lambda:os.setpgid(0,0)):\n'
                '  try: change()\n  except PermissionError: denied+=1\n'
                ' print(denied,flush=True);os._exit(0 if denied==2 else 9)\n'
                'else:\n _,s=os.waitpid(p,0);os._exit(os.waitstatus_to_exitcode(s))\n')
        result = self.call('provider', code)
        self.assertEqual(result, {'code': 0, 'stdout': b'2\n'})

    def test_proc_stat_parser_handles_parentheses_spaces_and_newlines(self):
        path = self.root / 'stat'
        fields = ['Z', '1', '73', '73'] + ['0'] * 15 + ['123456']
        path.write_bytes(b'73 (comm ) with\nparens)) ' + ' '.join(fields).encode())
        value = protected._read_process_stat(path)
        self.assertEqual((value['pid'], value['state'], value['pgrp'], value['session'], value['starttime']),
                         (73, 'Z', 73, 73, 123456))

    def test_proc_stat_parser_rejects_incomplete_and_oversized_evidence(self):
        path = self.root / 'stat'
        for value in (b'73 (incomplete) Z 1', b'wrong-format', b'x' * 8193):
            path.write_bytes(value)
            with self.subTest(value_bytes=len(value)), self.assertRaises(AppError):
                protected._read_process_stat(path)


if __name__ == '__main__': unittest.main()
