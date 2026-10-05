"""Contract runner integrity tests; no provider or Go runtime is needed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'qualify-provider-contract.py'


class ProviderContractLabTests(unittest.TestCase):
    def module(self):
        self.assertTrue(SCRIPT.is_file(), 'provider qualification runner must exist')
        spec = importlib.util.spec_from_file_location('provider_contract_qualification', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_go_failure_cannot_be_passed_qualification(self):
        mod = self.module()
        events = '\n'.join(json.dumps(x) for x in [
            {'Action':'run','Test':'TestPreservesID'},
            {'Action':'fail','Test':'TestPreservesID'},
            {'Action':'fail','Package':'contract'}])
        report = mod.summarize_go_tests(events, 1)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['tests_failed'], ['TestPreservesID'])
        self.assertFalse(report['production_qualified'])

    def test_empty_or_truncated_go_output_cannot_pass(self):
        mod = self.module()
        for output in ['', '{', '{"Action":"run","Test":"TestA"}']:
            with self.subTest(output=output):
                self.assertEqual(mod.summarize_go_tests(output,0)['status'],'failed')

    def test_skips_not_qualification(self):
        mod = self.module()
        output = '\n'.join(json.dumps(x) for x in [
            {'Action':'skip','Test':'TestA'}, {'Action':'pass','Package':'contract'}])
        self.assertEqual(mod.summarize_go_tests(output,0)['status'],'failed')

    def test_source_mutation_fails_before_execution(self):
        mod = self.module()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'source.go').write_text('tampered')
            with self.assertRaises(ValueError):
                mod.verify_sources(root,[{'path':'source.go','sha256':'0'*64}])

    def test_source_symlink_and_escape_rejected(self):
        mod = self.module()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'target').write_text('x')
            (root/'link').symlink_to(root/'target')
            for name in ['../target','/tmp/target','link']:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    mod.verify_sources(root,[{'path':name,'sha256':'0'*64}])

    def test_source_hashes_derive_from_actual_bytes(self):
        mod = self.module()
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'source.go').write_bytes(b'package test\n')
            expected = hashlib.sha256(b'package test\n').hexdigest()
            result = mod.verify_sources(root,[{'path':'source.go','sha256':expected}])
            self.assertEqual(result[0]['sha256'],expected)

    def test_unreviewed_go_executable_rejected(self):
        mod = self.module()
        self.assertTrue(hasattr(mod, 'verify_go'), 'compiler integrity check must exist')
        with tempfile.TemporaryDirectory() as d:
            executable = Path(d)/'go'
            executable.write_bytes(b'not-the-reviewed-compiler')
            with self.assertRaises(ValueError):
                mod.verify_go(executable)

    def test_patch_candidate_requires_both_exact_source_hashes(self):
        mod = self.module()
        self.assertTrue(hasattr(mod, 'apply_patch_candidate'), 'patch staging guard must exist')
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root/'internal/services/common/custom_requests/get_request.go'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'original')
            original = hashlib.sha256(b'original').hexdigest()
            candidate = hashlib.sha256(b'candidate').hexdigest()
            for old, new in [('0'*64,candidate),(original,'0'*64)]:
                with self.subTest(old=old), self.assertRaises(ValueError):
                    mod.apply_patch_candidate(root,b'candidate',old,new)
                self.assertEqual(target.read_bytes(),b'original')
            mod.apply_patch_candidate(root,b'candidate',original,candidate)
            self.assertEqual(target.read_bytes(),b'candidate')

    def test_exited_parent_does_not_leave_pipe_holding_descendant(self):
        mod = self.module()
        import os
        import signal
        import sys
        import time
        from unittest.mock import patch
        real_clock = time.monotonic
        real_popen = mod.subprocess.Popen
        started = real_clock()
        leaders = []
        leader_exited = False
        clock_started = False
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pid_file = root/'child.pid'
            heartbeat = root/'child.heartbeat'
            child_code = (
                'import sys,time; stream=open(sys.argv[1],"ab",buffering=0)\n'
                'for _ in range(1200):\n'
                ' stream.write(b"x"); time.sleep(0.05)\n'
            )
            parent_code = (
                'import pathlib,subprocess,sys; '
                'p=subprocess.Popen([sys.executable,"-c",sys.argv[2],sys.argv[3]]); '
                'pathlib.Path(sys.argv[1]).write_text(str(p.pid))'
            )
            def capture_popen(*args, **kwargs):
                leader = real_popen(*args, **kwargs)
                leaders.append(leader)
                return leader
            def deadline_clock():
                nonlocal leader_exited, clock_started
                now = real_clock()
                if not clock_started:
                    clock_started = True
                    return now
                leader_exited = bool(leaders and leaders[0].poll() is not None)
                ready = leader_exited and heartbeat.exists() and heartbeat.stat().st_size > 0
                return now + 601 if ready or now - started > 10 else now
            child_pid = None
            try:
                with patch.object(mod.time, 'monotonic', side_effect=deadline_clock), \
                     patch.object(mod.subprocess, 'Popen', side_effect=capture_popen):
                    with self.assertRaises(TimeoutError):
                        mod.run_logged([sys.executable,'-c',parent_code,str(pid_file),child_code,str(heartbeat)],
                                       root, {'PATH':os.environ.get('PATH','/usr/bin:/bin')}, root)
                self.assertTrue(leader_exited, 'counterexample requires an exited group leader')
                child_pid = int(pid_file.read_text())
                # The host virtualizes PIDs; /proc/<Popen.pid> is not a valid oracle.
                # A real child's monotonic heartbeat proves whether it kept running.
                time.sleep(0.1)
                before = heartbeat.stat().st_size
                self.assertGreater(before, 0, 'counterexample requires a running child')
                time.sleep(0.3)
                self.assertEqual(heartbeat.stat().st_size, before,
                                 'owned descendant survived timeout cleanup')
            finally:
                if child_pid is None and pid_file.exists():
                    child_pid = int(pid_file.read_text())
                if child_pid is not None:
                    try:
                        os.kill(child_pid,signal.SIGKILL)
                    except ProcessLookupError:
                        pass
