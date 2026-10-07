"""Actual pinned Docker containment tests, not argv-only simulations."""
from dataclasses import asdict, replace
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from intune_iac.io import AppError, load_json
from intune_iac import worker_host as host

from scripts.qualification_tools import PINNED as QUALIFICATION_PINS, reference as qualification_tool

PROJECT = Path(__file__).resolve().parents[1]
DOCKER = qualification_tool('docker')
TOFU = qualification_tool('tofu')
RELAY = qualification_tool('relay_v2')


class WorkerHostR4Tests(unittest.TestCase):
    def setUp(self):
        retained = os.environ.get('INTUNE_WORKER_HOST_TEST_EVIDENCE')
        self.temp = tempfile.TemporaryDirectory(prefix='iw-host-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        if retained:
            destination = Path(retained) / self._testMethodName
            def preserve():
                skipped = []
                def ignore(directory, names):
                    result = []
                    for name in names:
                        path = Path(directory) / name
                        if path.is_socket():
                            skipped.append({'path': str(path.relative_to(self.root)), 'type': 'closed_runtime_unix_socket',
                                            'mode': path.stat().st_mode, 'uid': path.stat().st_uid})
                            result.append(name)
                    return result
                shutil.copytree(self.root, destination, symlinks=True, ignore=ignore)
                (destination / 'RUNTIME-IPC-NODES.json').write_text(json.dumps({'original_root': str(self.root),
                    'retained_regular_files_unchanged': True, 'nonportable_closed_ipc_nodes': skipped}, indent=2) + '\n')
            self.addCleanup(preserve)
        for name in ('source', 'control', 'job'):
            (self.root / name).mkdir(mode=0o700)
        (self.root / 'source/input.txt').write_text('BOUND-SOURCE-CANARY\n')

    def spec(self, script, **kwargs):
        (self.root / 'control/worker.sh').write_text(script)
        return host.HostSpec(str(DOCKER), str(self.root / 'source'),
            host.directory_binding(self.root / 'source')['sha256'], str(self.root / 'control'),
            host.directory_binding(self.root / 'control')['sha256'], str(self.root / 'job'), **kwargs)

    def receipt(self, spec, name='run'):
        result = host.launch(spec, self.root / name)
        self.assertTrue(result.get('cleanup', {}).get('removed'), result)
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['production_qualified'])
        return result

    def test_real_boundary_denies_root_source_control_internet_and_host_socket(self):
        spec = self.spec('''set -eu
id > /job/identity
cat /proc/self/status > /job/process-status
cat /proc/net/route > /job/routes
ls /sys/class/net > /job/interfaces
cat /source/input.txt > /job/source-read
if touch /escaped-root 2>/job/root-error; then exit 91; fi
if touch /source/escaped-input 2>/job/source-error; then exit 92; fi
if touch /control/escaped-control 2>/job/control-error; then exit 93; fi
if [ -e /var/run/docker.sock ]; then exit 94; fi
if [ -e /proc/1/root/var/run/docker.sock ]; then exit 95; fi
if nc -z -w 1 198.51.100.1 443 2>/job/network-error; then exit 96; fi
if [ "${WORKER_HOST_SECRET_CANARY-unset}" != unset ]; then exit 97; fi
printf 'bounded-complete\\n'
''')
        prior = os.environ.get('WORKER_HOST_SECRET_CANARY')
        os.environ['WORKER_HOST_SECRET_CANARY'] = 'HOST-SECRET-MUST-NOT-ENTER'
        try:
            result = self.receipt(spec)
        finally:
            if prior is None:
                os.environ.pop('WORKER_HOST_SECRET_CANARY', None)
            else:
                os.environ['WORKER_HOST_SECRET_CANARY'] = prior
        self.assertEqual(result['status'], 'complete', result)
        self.assertIn('uid=1000', (self.root / 'job/identity').read_text())
        status = (self.root / 'job/process-status').read_text()
        self.assertIn('CapEff:\t0000000000000000', status)
        self.assertIn('NoNewPrivs:\t1', status)
        self.assertIn('Seccomp:\t2', status)
        self.assertEqual((self.root / 'job/interfaces').read_text().strip(), 'lo')
        self.assertEqual((self.root / 'job/source-read').read_bytes(), b'BOUND-SOURCE-CANARY\n')
        self.assertFalse((self.root / 'source/escaped-input').exists())
        self.assertFalse((self.root / 'control/escaped-control').exists())
        inspections = [load_json(self.root / 'run' / item) for item in result['commands']]
        before = next(item for item in inspections if 'inspect-before' in item['stdout'])
        value = json.loads((self.root / 'run' / before['stdout']).read_bytes())[0]
        self.assertEqual(value['HostConfig']['PidsLimit'], 128)
        self.assertEqual(value['HostConfig']['Memory'], 1073741824)
        self.assertEqual(value['HostConfig']['LogConfig']['Type'], 'none')
        # Challenge the inspection verifier with contradictory daemon fields;
        # these dictionaries never configure or start a privileged container.
        for changes in ({'CapAdd': ['SYS_ADMIN']},
                        {'SecurityOpt': ['no-new-privileges', 'seccomp=unconfined']},
                        {'SecurityOpt': ['no-new-privileges', 'apparmor=unconfined']},
                        {'DeviceCgroupRules': ['a *:* rwm']},
                        {'RestartPolicy': {'Name': 'always', 'MaximumRetryCount': 0}}):
            with self.subTest(changes=changes):
                altered = deepcopy(value)
                altered['HostConfig'].update(changes)
                labels = value['Config']['Labels']
                with self.assertRaises(AppError) as failure:
                    host._boundary(altered, spec, labels['intune.workbench.host-run'],
                                   labels['intune.workbench.manifest-sha256'])
                self.assertEqual(failure.exception.code, 'worker_host_boundary_mismatch')

    def test_native_pinned_tofu_runs_inside_same_nonroot_boundary(self):
        tool = host.PinnedTool('tofu', str(TOFU), 'a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a')
        spec = self.spec('set -eu\nCHECKPOINT_DISABLE=1 /tools/tofu version -json > /job/tofu-version.json\n', tools=(tool,))
        result = self.receipt(spec)
        self.assertEqual(result['status'], 'complete', result)
        self.assertEqual(load_json(self.root / 'job/tofu-version.json')['terraform_version'], '1.13.1')

    def test_timeout_stops_container_descendants_and_preserves_primary_error(self):
        spec = self.spec('''set -eu
(while :; do printf x >> /job/heartbeat; sleep 0.05; done) &
wait
''', timeout_seconds=1)
        result = self.receipt(spec)
        self.assertEqual(result['primary_error'], 'worker_host_process_timeout')
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['cleanup']['stopped_state']['Running'])
        before = (self.root / 'job/heartbeat').read_bytes()
        time.sleep(0.2)
        self.assertEqual((self.root / 'job/heartbeat').read_bytes(), before)

    def test_combined_output_limit_preserves_bounded_stderr_and_cleans_container(self):
        spec = self.spec('while :; do printf "OUTPUT-CANARY-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX\\n" >&2; done\n', output_limit=4096)
        result = self.receipt(spec)
        self.assertEqual(result['primary_error'], 'worker_host_output_limit')
        commands = [load_json(self.root / 'run' / item) for item in result['commands']]
        started = next(item for item in commands if item['output_truncated'])
        stderr = (self.root / 'run' / started['stderr']).read_bytes()
        stdout = (self.root / 'run' / started['stdout']).read_bytes()
        self.assertLessEqual(len(stderr) + len(stdout), 4096)
        self.assertIn(b'OUTPUT-CANARY', stderr)

    def test_sigint_cleans_container_then_restores_parent_handler(self):
        spec = self.spec('set -eu\necho waiting > /job/waiting\nsleep 30\n')
        handler = signal.getsignal(signal.SIGINT)
        def interrupt():
            deadline = time.monotonic() + 5
            while not (self.root / 'job/waiting').exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            if (self.root / 'job/waiting').exists():
                os.kill(os.getpid(), signal.SIGINT)
        thread = threading.Thread(target=interrupt, daemon=True)
        thread.start()
        with self.assertRaises(KeyboardInterrupt):
            host.launch(spec, self.root / 'run')
        thread.join(timeout=5)
        receipt = load_json(self.root / 'run/receipt.json')
        self.assertEqual(receipt['status'], 'cancelled')
        self.assertTrue(receipt['cleanup']['removed'])
        self.assertIs(signal.getsignal(signal.SIGINT), handler)

    def test_sigkill_controller_recovery_removes_only_its_labeled_worker(self):
        spec = self.spec('set -eu\necho waiting > /job/waiting\nsleep 30\n')
        request = self.root / 'request.json'
        request.write_text(json.dumps(asdict(spec)))
        program = '''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from intune_iac.worker_host import HostSpec,PinnedTool,launch
value=json.loads(Path(sys.argv[2]).read_text());value['tools']=tuple(PinnedTool(**x) for x in value['tools'])
launch(HostSpec(**value),sys.argv[3])
'''
        process = subprocess.Popen([sys.executable, '-I', '-B', '-c', program, str(PROJECT), str(request), str(self.root / 'run')],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 6
            while not (self.root / 'job/waiting').exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue((self.root / 'job/waiting').exists())
            process.kill()
            process.communicate(timeout=5)
            recovered = host.recover(self.root / 'run')
            self.assertTrue(recovered['cleanup']['removed'])
            self.assertFalse(recovered['mutation_replayed'])
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
            if (self.root / 'run/journal.json').exists():
                host.recover(self.root / 'run')

    def test_source_and_tool_substitution_rejected_before_daemon_mutation(self):
        spec = self.spec('echo should-not-start\n')
        (self.root / 'source/input.txt').write_text('substituted')
        with self.assertRaises(AppError) as raised:
            host.launch(spec, self.root / 'run')
        self.assertEqual(raised.exception.code, 'worker_host_input_changed')
        self.assertFalse((self.root / 'run').exists())
        spec = self.spec('echo should-not-start\n', tools=(host.PinnedTool('tofu', str(TOFU), '0' * 64),))
        with self.assertRaises(AppError) as raised:
            host.launch(spec, self.root / 'run-tool')
        self.assertEqual(raised.exception.code, 'worker_host_tool_changed')

    def test_writable_job_alias_cannot_supply_a_pinned_tool(self):
        tool = self.root / 'job/aliased-tool'
        tool.write_bytes(b'#!/bin/sh\nprintf fixture-only\\n\n')
        tool.chmod(0o700)
        spec = self.spec('echo should-not-start\n', tools=(host.PinnedTool(
            'tofu', str(tool), hashlib.sha256(tool.read_bytes()).hexdigest()),))
        with self.assertRaises(AppError) as failure:
            host.launch(spec, self.root / 'rejected-job-alias')
        self.assertEqual(failure.exception.code, 'worker_host_writable_executable')
        self.assertFalse((self.root / 'rejected-job-alias').exists())

    def test_mount_csv_handles_spaces_commas_quotes_and_unicode_literally(self):
        renamed = self.root / 'source space,quote"-é'
        (self.root / 'source').rename(renamed)
        (self.root / 'control/worker.sh').write_text('cat /source/input.txt > /job/read\n')
        spec = host.HostSpec(str(DOCKER), str(renamed), host.directory_binding(renamed)['sha256'],
            str(self.root / 'control'), host.directory_binding(self.root / 'control')['sha256'], str(self.root / 'job'))
        result = self.receipt(spec)
        self.assertEqual(result['status'], 'complete', result)
        self.assertEqual((self.root / 'job/read').read_bytes(), b'BOUND-SOURCE-CANARY\n')

    def test_static_relay_reaches_only_mounted_unix_socket_without_internet(self):
        broker = self.root / 'broker'
        broker.mkdir(mode=0o700)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(broker / 'egress.sock'))
        os.chmod(broker / 'egress.sock', 0o600)
        server.listen(1)
        server.settimeout(5)
        received = []
        def respond():
            try:
                connection, _ = server.accept()
                with connection:
                    received.append(connection.recv(1024))
                    connection.sendall(b'UNIX-BOUNDARY-REPLY\n')
            except OSError:
                pass
        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        (self.root / 'control/broker-ca.pem').write_bytes(b'Explicit synthetic placeholder; no TLS claim in this socket-only probe.\n')
        ca = hashlib.sha256((self.root / 'control/broker-ca.pem').read_bytes()).hexdigest()
        relay = host.PinnedTool('relay', str(RELAY), QUALIFICATION_PINS['relay_v2']['sha256'])
        spec = self.spec('''set -eu
/tools/relay &
relay_pid=$!
trap 'kill "$relay_pid" 2>/dev/null || true' EXIT
sleep 0.2
printf 'UNIX-BOUNDARY-REQUEST\\n' | nc -w 3 127.0.0.1 18080 > /job/reply
''', tools=(relay,), broker_root=str(broker), broker_ca_sha256=ca)
        try:
            result = self.receipt(spec)
        finally:
            server.close()
            thread.join(timeout=5)
        self.assertEqual(result['status'], 'complete', result)
        self.assertEqual(received, [b'UNIX-BOUNDARY-REQUEST\n'])
        self.assertEqual((self.root / 'job/reply').read_bytes(), b'UNIX-BOUNDARY-REPLY\n')


if __name__ == '__main__':
    unittest.main()
