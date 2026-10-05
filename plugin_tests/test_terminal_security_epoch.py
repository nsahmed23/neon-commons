"""Enterprise terminal regressions: observed effects, synthetic local data only."""
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from intune_iac.io import AppError
from intune_iac.mcp import FilesystemAuthority
from intune_iac import provider_execution as pe

ROOT = Path(__file__).resolve().parents[1]


class FileIdentityTests(unittest.TestCase):
    def test_hardlinked_outside_record_cannot_be_selected_by_hostile_model(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / 'allowed'; root.mkdir()
            outside = base / 'private.json'
            outside.write_text('{"canary":"SYNTHETIC-PRIVATE-RECORD"}')
            alias = root / 'public.json'; os.link(outside, alias)
            authority = FilesystemAuthority([root], [root])
            for write in (False, True):
                with self.subTest(write=write):
                    with self.assertRaises(AppError) as caught:
                        authority.check(str(alias), write=write)
                    self.assertEqual(caught.exception.code, 'filesystem_authority_denied')
            self.assertEqual(outside.read_text(), '{"canary":"SYNTHETIC-PRIVATE-RECORD"}')

    def test_composed_mcp_graph_request_cannot_read_an_outside_hardlink(self):
        from intune_iac.graph import build_graph
        from intune_iac.mcp import call_tool
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); allowed = base / 'approved'; allowed.mkdir()
            graph = build_graph(ROOT / 'examples/supported/input/export.json')
            for node in graph['nodes']:
                if node['type'] == 'Policy': node['name'] = 'SYNTHETIC-PRIVATE-POLICY'
            outside = base / 'private-graph.json'; outside.write_text(json.dumps(graph))
            alias = allowed / 'innocent.json'; os.link(outside, alias)
            with self.assertRaises(AppError) as caught:
                call_tool('intune_graph_query', {'graph': str(alias), 'query': 'policies'},
                          authority=FilesystemAuthority([allowed], []))
            self.assertEqual(caught.exception.code, 'filesystem_authority_denied')

    def test_after_open_identity_check_rejects_a_new_hardlink(self):
        from intune_iac.io import read_bytes
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'record.json'; source.write_text('{}')
            actual_open = os.open
            def open_then_link(*args, **kwargs):
                descriptor = actual_open(*args, **kwargs)
                os.link(source, root / 'racing-alias.json')
                return descriptor
            with patch('intune_iac.io.os.open', side_effect=open_then_link):
                with self.assertRaises(AppError) as caught: read_bytes(source)
            self.assertEqual(caught.exception.code, 'unsafe_file_identity')

    def test_regular_unusual_paths_remain_literal_and_usable(self):
        from intune_iac.io import load_json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('-leading.json', 'spaces and "quotes".json', '政策.json', '$(no-command).json'):
                path = root / name; path.write_text('{"literal":true}')
                FilesystemAuthority([root], []).check(str(path))
                self.assertEqual(load_json(path), {'literal': True})

    def test_repository_nested_hardlink_is_not_read(self):
        from intune_iac.repository import discover_repository
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = base / 'repository'; root.mkdir()
            (root / 'atmos.yaml').write_text('stacks:\n  base_path: stacks\n  included_paths: ["**/*"]\n')
            (root / 'stacks').mkdir()
            outside = base / 'private.yaml'; outside.write_text('vars: {password: SYNTHETIC-CANARY}\n')
            os.link(outside, root / 'stacks' / 'untrusted.yaml')
            result = discover_repository(root)
            self.assertIn('unsafe_hardlink', json.dumps(result))
            self.assertNotIn('SYNTHETIC-CANARY', json.dumps(result))


class DescendantLifetimeTests(unittest.TestCase):
    def test_provider_descendant_cannot_detach_then_write_after_supervisor_returns(self):
        """Failing-before probe self-cleans; never starts a persistent process."""
        for operation in ('os.setsid()', 'os.setpgid(0, 0)'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                marker, pid_file = root / 'late-write', root / 'pid'
                child = ('import os,time,pathlib\n'
                         'pathlib.Path(' + repr(str(pid_file)) + ').write_text(str(os.getpid()))\n'
                         'try: ' + operation + '\n'
                         'except PermissionError: pass\n'
                         'os.close(1);os.close(2)\n'
                         'time.sleep(0.25)\n'
                         'pathlib.Path(' + repr(str(marker)) + ').write_text("harmless-probe")\n')
                parent = ('import subprocess,sys,time,pathlib\n'
                          'subprocess.Popen([sys.executable,"-c",' + repr(child) + '])\n'
                          'ready=pathlib.Path(' + repr(str(pid_file)) + ')\n'
                          'while not ready.exists(): time.sleep(0.005)\n')
                try:
                    result = pe._supervise([sys.executable, '-c', parent], cwd=root, env={},
                                           executable=sys.executable, pass_fds=(), timeout=2)
                    self.assertEqual(result['code'], 0)
                    time.sleep(0.4)
                    self.assertFalse(marker.exists(), 'Detached child wrote after supervisor returned')
                finally:
                    if pid_file.exists():
                        try: os.kill(int(pid_file.read_text()), signal.SIGKILL)
                        except ProcessLookupError: pass


class DurablePersistenceTests(unittest.TestCase):
    def test_capture_new_directory_sync_failure_prevents_transport(self):
        from intune_iac.capture import capture
        with tempfile.TemporaryDirectory() as directory:
            actual_sync = os.fsync; parent = Path(directory).stat()
            def fail_parent(descriptor):
                info = os.fstat(descriptor)
                if (info.st_dev, info.st_ino) == (parent.st_dev, parent.st_ino): raise OSError('synthetic parent sync failure')
                return actual_sync(descriptor)
            transport = unittest.mock.Mock(return_value=(200, b'{"value":[]}'))
            with patch('os.fsync', side_effect=fail_parent):
                with self.assertRaises(AppError):
                    capture('11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222',
                            Path(directory) / 'capture', transport=transport)
            transport.assert_not_called()

    def test_json_acknowledgement_syncs_renamed_file_and_created_directories(self):
        from intune_iac.io import write_json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'new' / 'journal' / 'event.json'
            synced = set(); actual_sync = os.fsync
            def observe(descriptor):
                info = os.fstat(descriptor)
                synced.add((info.st_dev, info.st_ino))
                return actual_sync(descriptor)
            with patch('intune_iac.io.os.fsync', side_effect=observe):
                write_json(target, {'phase': 'before-dispatch'})
            for path in (target, target.parent, target.parent.parent, root):
                info = path.stat()
                self.assertIn((info.st_dev, info.st_ino), synced, 'Acknowledgement omitted required directory sync')

    def test_directory_sync_failure_cannot_be_acknowledged(self):
        from intune_iac.io import write_json
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'receipt.json'; actual_sync = os.fsync
            def fail_directory(descriptor):
                if stat.S_ISDIR(os.fstat(descriptor).st_mode): raise OSError('synthetic directory durability failure')
                return actual_sync(descriptor)
            with patch('intune_iac.io.os.fsync', side_effect=fail_directory):
                with self.assertRaises(AppError) as caught: write_json(target, {'status': 'verified'})
            self.assertEqual(caught.exception.code, 'write_failed')

    def test_runner_syncs_graph_namespace_before_success(self):
        from intune_iac.runner import run
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); output = base / 'outputs'; output.mkdir()
            target = output / 'graph.json'; synced = []; actual_sync = os.fsync
            def observe(descriptor):
                info = os.fstat(descriptor)
                if stat.S_ISDIR(info.st_mode): synced.append((info.st_dev, info.st_ino, target.exists()))
                return actual_sync(descriptor)
            with patch('os.fsync', side_effect=observe):
                result = run('graph_build', {'input': str(ROOT / 'examples/supported/input/export.json'),
                                             'output': str(target)}, base / 'journal')
            self.assertEqual(result['status'], 'succeeded_verified')
            info = output.stat()
            self.assertIn((info.st_dev, info.st_ino, True), synced)

    def test_runner_directory_failure_cannot_dispatch_or_claim_success(self):
        from intune_iac.runner import run
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); output = base / 'outputs'; output.mkdir()
            target = output / 'graph.json'; identity = output.stat(); actual_sync = os.fsync
            def fail_output(descriptor):
                info = os.fstat(descriptor)
                if (info.st_dev, info.st_ino) == (identity.st_dev, identity.st_ino): raise OSError('synthetic ENOSPC')
                return actual_sync(descriptor)
            with patch('os.fsync', side_effect=fail_output), patch('intune_iac.runner._dispatch') as dispatch:
                result = run('graph_build', {'input': str(ROOT / 'examples/supported/input/export.json'),
                                             'output': str(target)}, base / 'journal')
            self.assertEqual(result['status'], 'rejected')
            dispatch.assert_not_called()
            self.assertFalse(target.exists())

    def test_wizard_modes_require_lock_directory_durability_before_controller(self):
        from intune_iac.wizard import run_wizard
        for guided, controller in ((False, 'intune_iac.wizard._run_wizard'), (True, 'intune_iac.workflow._guide')):
            with self.subTest(guided=guided), tempfile.TemporaryDirectory() as directory:
                actual_sync = os.fsync
                def fail_directory(descriptor):
                    if stat.S_ISDIR(os.fstat(descriptor).st_mode): raise OSError('synthetic durability failure')
                    return actual_sync(descriptor)
                with patch('os.fsync', side_effect=fail_directory), patch(controller, return_value={'status': 'finished'}) as body:
                    result = run_wizard(Path(directory) / 'session.json',
                        input_path=ROOT / 'examples/supported/input/export.json', context_path=ROOT / 'examples/context.json',
                        output_path=Path(directory) / 'output', guided=guided, output_fn=lambda text: None)
                self.assertEqual(result['status'], 'blocked')
                body.assert_not_called()


class LaunchAndPresentationTests(unittest.TestCase):
    def test_protected_child_does_not_inherit_startup_or_loader_environment(self):
        from intune_iac import protected
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); marker = root / 'startup-executed'
            startup = root / 'startup.sh'; startup.write_text('printf attack > ' + str(marker) + '\n')
            executor = protected.create_synthetic_executor(root / 'executor', initial_value={}, desired_value={})
            hostile = {'BASH_ENV': str(startup), 'ENV': str(startup), 'PYTHONSTARTUP': str(startup),
                       'PYTHONPATH': str(root), 'LD_PRELOAD': '/nonexistent',
                       'BASH_FUNC_printf%%': '() { exit 91; }', 'TF_CLI_ARGS': '-destroy'}
            with patch.dict(os.environ, hostile):
                environment = protected._environment(executor)
                self.assertFalse(set(hostile) & set(environment))
                output = protected._supervise([str(Path(sys.executable).resolve()), '-I', '-S', '-c',
                    'import os,json;print(json.dumps(sorted(os.environ)))'], cwd=root,
                    env=environment, executable=str(Path(sys.executable).resolve()))
            self.assertFalse(set(hostile) & set(json.loads(output)))
            self.assertFalse(marker.exists())

    def test_repository_discovery_never_runs_git_config_or_hook(self):
        from intune_iac.repository import discover_repository
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); marker = root / 'hook-executed'
            (root / '.git' / 'hooks').mkdir(parents=True)
            (root / '.git' / 'config').write_text('[core]\n hooksPath = hooks\n fsmonitor = malicious\n')
            (root / '.git' / 'hooks' / 'post-checkout').write_text('#!/bin/sh\nprintf executed > ' + str(marker))
            (root / 'atmos.yaml').write_text('stacks:\n  base_path: stacks\n  included_paths: ["**/*"]\n')
            (root / 'stacks').mkdir()
            (root / 'stacks' / 'demo.yaml').write_text('components:\n  terraform:\n    demo: {}\n')
            with patch('subprocess.Popen', side_effect=AssertionError('Repository inspection launched a process')):
                result = discover_repository(root)
            self.assertFalse(marker.exists())
            self.assertNotEqual(result.get('status'), 'error')

    def test_cli_json_does_not_emit_active_terminal_sequences(self):
        import io
        from intune_iac.cli import main
        controls = '\x1b]52;c;Y2FuYXJ5\x07\x1b]8;;https://invalid\x1b\\\r\b\u009b2J\u202eFORGED'
        output = io.StringIO()
        with patch('intune_iac.cli.execute', return_value={'status': 'ready', 'name': controls}), patch('sys.stdout', output):
            self.assertEqual(main(['doctor']), 0)
        rendered = output.getvalue()
        self.assertTrue(all(ord(char) >= 32 and ord(char) < 127 or char == '\n' for char in rendered))
        self.assertEqual(json.loads(rendered)['name'], controls)


class ChangeCoverageTests(unittest.TestCase):
    def test_final_snapshot_accounts_for_multiple_write_mechanisms(self):
        """Snapshot scanner coverage, not a claim that a host hook ran."""
        from plugin_tests.test_security_audit_completion import audit
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = """printf 'value = 1\\n' > redirect.py
cat > heredoc.py <<'FIXTURE'
value = 2
FIXTURE
sed -i 's/1/3/' redirect.py
mkdir nested
printf '{"lockfileVersion":3}\\n' > nested/package-lock.json
mv heredoc.py renamed.py
"""
            subprocess.run(['/bin/bash', '--noprofile', '--norc', '-c', script], cwd=root, env={},
                           stdin=subprocess.DEVNULL, check=True, capture_output=True, timeout=5)
            (root / 'python-write.py').write_text('value = 4\n')
            actual = {path.relative_to(root).as_posix(): __import__('hashlib').sha256(path.read_bytes()).hexdigest()
                      for path in root.rglob('*') if path.is_file()}
            scanned = audit.inventory(root)
            self.assertEqual({row['path']: row['sha256'] for row in scanned['files']}, actual)
            self.assertEqual(scanned['coverage_gaps'], [])
            self.assertEqual(scanned['status'], 'INCONCLUSIVE')


if __name__ == '__main__':
    unittest.main()
