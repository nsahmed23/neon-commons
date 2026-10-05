"""Safety and claim checks for the native, provider-free adoption lab."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/qualify-adoption-lab.py'


class AdoptionLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = None
        if SCRIPT.exists():
            spec = importlib.util.spec_from_file_location('adoption_lab', SCRIPT)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)

    def lab(self):
        self.assertIsNotNone(self.module, 'The native adoption lab runner is not implemented')
        return self.module

    def test_exact_fixture_accepts_only_reviewed_source(self):
        lab = self.lab()
        fixture = ROOT / 'labs/atmos-adoption/fixture'
        lab.validate_fixture(fixture)
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            modified = Path(tmp) / 'fixture'
            shutil.copytree(fixture, modified)
            (modified / 'components/terraform/policy/main.tf').write_text('provider "azurerm" {}\n')
            with self.assertRaisesRegex(ValueError, 'fixture'):
                lab.validate_fixture(modified)

    def test_extra_fixture_file_is_rejected(self):
        lab = self.lab()
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            modified = Path(tmp) / 'fixture'
            shutil.copytree(ROOT / 'labs/atmos-adoption/fixture', modified)
            (modified / 'components/terraform/policy/override.tf').write_text('terraform {}')
            with self.assertRaisesRegex(ValueError, 'fixture'):
                lab.validate_fixture(modified)

    def test_unexpected_member_is_rejected_before_any_hashing(self):
        lab = self.lab()
        import shutil
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            modified = Path(tmp) / 'fixture'
            shutil.copytree(ROOT / 'labs/atmos-adoption/fixture', modified)
            (modified / 'unexpected.bin').write_bytes(b'not-an-accepted-member')
            with patch.object(lab, 'sha256', side_effect=AssertionError('must reject members before hashing')):
                with self.assertRaisesRegex(ValueError, 'fixture'):
                    lab.validate_fixture(modified)

    def test_oversized_fixture_is_rejected_before_streaming_hash(self):
        lab = self.lab()
        import shutil
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            modified = Path(tmp) / 'fixture'
            shutil.copytree(ROOT / 'labs/atmos-adoption/fixture', modified)
            (modified / 'components/terraform/policy/main.tf').write_bytes(b'x' * 20000)
            with patch.object(lab, 'sha256', side_effect=AssertionError('must bound fixture reads')):
                with self.assertRaisesRegex(ValueError, 'fixture'):
                    lab.validate_fixture(modified)

    def test_symlinked_fixture_file_is_rejected(self):
        lab = self.lab()
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            modified = Path(tmp) / 'fixture'
            shutil.copytree(ROOT / 'labs/atmos-adoption/fixture', modified)
            main = modified / 'components/terraform/policy/main.tf'
            value = main.read_bytes()
            main.unlink()
            other = Path(tmp) / 'other'
            other.write_bytes(value)
            main.symlink_to(other)
            with self.assertRaisesRegex(ValueError, 'fixture'):
                lab.validate_fixture(modified)

    def test_environment_does_not_inherit_credentials_or_config(self):
        lab = self.lab()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = dict(os.environ)
            try:
                os.environ.update({'ARM_CLIENT_SECRET': 'CANARY', 'TF_CLI_ARGS': '-destroy', 'ATMOS_BASE_PATH': '/etc', 'PYTHONPATH': '/evil'})
                env = lab.clean_environment(root)
            finally:
                os.environ.clear()
                os.environ.update(old)
            self.assertNotIn('CANARY', json.dumps(env))
            for key in ('HOME', 'ARM_CLIENT_SECRET', 'TF_CLI_ARGS', 'ATMOS_BASE_PATH', 'PYTHONPATH'):
                self.assertNotIn(key, env)
            self.assertEqual(env['ATMOS_TELEMETRY_ENABLED'], 'false')
            self.assertEqual(env['TF_CLI_CONFIG_FILE'], str(root / 'empty.tofurc'))

    def test_output_must_be_new_and_not_contain_source(self):
        lab = self.lab()
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            existing = parent / 'existing'
            existing.mkdir()
            (existing / 'keep').write_text('keep')
            with self.assertRaises((ValueError, FileExistsError)):
                lab.prepare_output(existing)
            self.assertEqual((existing / 'keep').read_text(), 'keep')
        with self.assertRaises(ValueError):
            lab.prepare_output(ROOT / 'do-not-create-lab-output')
        self.assertFalse((ROOT / 'do-not-create-lab-output').exists())

    def test_no_change_assertion_rejects_replacement_and_hidden_deletion(self):
        lab = self.lab()
        expected = {'terraform_data.policy': ['no-op'], 'terraform_data.targeting': ['no-op']}
        plan = {'resource_changes': [
            {'address': address, 'change': {'actions': actions}}
            for address, actions in expected.items()]}
        lab.require_actions(plan, expected)
        plan['resource_changes'][0]['change']['actions'] = ['delete', 'create']
        with self.assertRaises(AssertionError):
            lab.require_actions(plan, expected)
        plan['resource_changes'][0]['change']['actions'] = ['no-op']
        plan['resource_changes'].append({'address': 'terraform_data.lost', 'change': {'actions': ['delete']}})
        with self.assertRaises(AssertionError):
            lab.require_actions(plan, expected)

    def test_no_change_assertion_rejects_duplicate_addresses(self):
        lab = self.lab()
        plan = {'resource_changes': [
            {'address': 'terraform_data.policy', 'change': {'actions': ['delete']}},
            {'address': 'terraform_data.policy', 'change': {'actions': ['no-op']}}]}
        with self.assertRaises(AssertionError):
            lab.require_actions(plan, {'terraform_data.policy': ['no-op']})

    def test_state_preservation_requires_ids_lineage_and_serial(self):
        lab = self.lab()
        state = {'lineage': 'l', 'serial': 4, 'resources': [
            {'mode': 'managed', 'type': 'terraform_data', 'name': 'policy',
             'instances': [{'attributes': {'id': 'policy-id', 'input': {'value': 'allow'}}}]}]}
        same = json.loads(json.dumps(state))
        lab.require_same_state(state, same)
        for field in ('lineage', 'serial'):
            changed = json.loads(json.dumps(state))
            changed[field] = 'different'
            with self.assertRaises(AssertionError):
                lab.require_same_state(state, changed)
        same['resources'][0]['instances'][0]['attributes']['id'] = 'different-id'
        with self.assertRaises(AssertionError):
            lab.require_same_state(state, same)

    def test_native_tool_must_have_expected_digest(self):
        lab = self.lab()
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'tofu'
            fake.write_text('#!/bin/sh\necho pretend\n')
            fake.chmod(0o755)
            with self.assertRaisesRegex(ValueError, 'digest'):
                lab.verify_binary(fake, 'tofu')

    def native_fixture(self, root, body):
        import sys
        import time
        lab = self.lab()
        (root / 'runtime-bin').mkdir()
        (root / 'logs').mkdir()
        (root / 'work').mkdir()
        fake = root / 'runtime-bin/tofu'
        fake.write_text('#!' + sys.executable + '\n' + body)
        fake.chmod(0o700)
        instance = lab.Lab.__new__(lab.Lab)
        instance.root = root
        instance.repository = root / 'work'
        instance.environment = lab.clean_environment(root)
        instance.deadline = time.monotonic() + 10
        instance.commands = []
        instance.checks = []
        return instance

    def test_waits_for_descendant_output_before_hashing(self):
        lab = self.lab()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = self.native_fixture(root, """import os,time
if os.fork()==0:
    time.sleep(0.2)
    os.write(1,b'late\\n')
    os._exit(0)
os.write(1,b'early\\n')
""")
            stdout, stderr, code = instance.native('late-output', 'tofu', ['version'])
            self.assertEqual((stdout, stderr, code), ('early\nlate\n', '', 0))
            self.assertEqual(instance.commands[0]['stdout_sha256'], lab.sha256(root / 'logs/late-output.stdout'))

    def test_output_limit_kills_group_and_marks_incomplete_receipt(self):
        self.lab()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = self.native_fixture(root, "import os,time\nos.write(1,b'x'*3000000)\ntime.sleep(30)\n")
            with self.assertRaisesRegex(RuntimeError, 'output limit'):
                instance.native('too-large', 'tofu', ['version'])
            receipt = json.loads((root / 'logs/too-large.json').read_text())
            self.assertEqual(receipt['outcome'], 'output_limit')
            self.assertFalse(receipt['transcript_complete'])
            self.assertLessEqual((root / 'logs/too-large.stdout').stat().st_size, 2097152)

    def test_final_report_cannot_pass_changed_transcript(self):
        lab = self.lab()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = self.native_fixture(root, "print('recorded')\n")
            instance.native('recorded', 'tofu', ['version'])
            (root / 'logs/recorded.stdout').write_text('changed')
            report = instance.report('passed')
            self.assertEqual(report['status'], 'failed')
            self.assertIn('command transcript', report['error'])

    def test_main_returns_failure_when_transcript_changes_before_report(self):
        lab = self.lab()
        import contextlib
        import io
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = self.native_fixture(root, "print('original transcript')\n")
            def execute_then_tamper():
                instance.native('recorded', 'tofu', ['version'])
                (root / 'logs/recorded.stdout').write_text('changed after command')
            instance.perform = execute_then_tamper
            printed = io.StringIO()
            # Pins/output handling have their own real boundary tests. Here the
            # actual native(), report(), and main() observe the changed log.
            with patch.object(lab, 'verify_binary', return_value=root / 'runtime-bin/tofu'), \
                 patch.object(lab, 'prepare_output', return_value=root), \
                 patch.object(lab, 'Lab', return_value=instance), contextlib.redirect_stdout(printed):
                code = lab.main(['--tofu', 'tofu', '--atmos', 'atmos', '--output', str(root)])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(printed.getvalue())['status'], 'failed')
            self.assertEqual(json.loads((root / 'result.json').read_text())['status'], 'failed')

    def process_failure(self, mode):
        # The child is a real owned sleeper. The driver records whether native()
        # cleaned it up, then kills it itself if the implementation failed.
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'runtime-bin').mkdir()
            (root / 'logs').mkdir()
            (root / 'work').mkdir()
            fake = root / 'runtime-bin/tofu'
            fake.write_text('#!' + sys.executable + '\nimport os,time,pathlib\n'
                            + 'pathlib.Path(' + repr(str(root / 'child.pid')) + ').write_text(str(os.getpid()))\n'
                            + 'time.sleep(30)\n')
            fake.chmod(0o700)
            driver = root / 'driver.py'
            driver.write_text("""import importlib.util,json,os,pathlib,signal,threading,time
spec=importlib.util.spec_from_file_location('lab', SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
r=pathlib.Path(OUTPUT);lab=m.Lab.__new__(m.Lab)
lab.root=r;lab.repository=r/'work';lab.environment=m.clean_environment(r)
lab.deadline=time.monotonic()+(0.4 if MODE=='timeout' else 10);lab.commands=[]
def interrupt():
    while not (r/'child.pid').exists(): time.sleep(0.01)
    os.kill(os.getpid(),signal.SIGINT)
if MODE=='interrupt': threading.Thread(target=interrupt,daemon=True).start()
try:
    lab.native('interrupted','tofu',['version'])
except BaseException as exc:
    failure=type(exc).__name__
pid=int((r/'child.pid').read_text())
try:
    os.kill(pid,0);alive=True
except ProcessLookupError: alive=False
if alive: os.killpg(pid,signal.SIGKILL)
receipt=r/'logs/interrupted.json'
print(json.dumps({'failure':failure,'alive':alive,'receipt':json.loads(receipt.read_text()) if receipt.exists() else None}))
""".replace('SCRIPT', repr(str(SCRIPT))).replace('OUTPUT', repr(str(root))).replace('MODE', repr(mode)))
            proc = subprocess.run([sys.executable, str(driver)], capture_output=True, text=True, timeout=15)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            self.assertFalse(result['alive'], 'owned child survived interrupted qualification')
            self.assertIsNotNone(result['receipt'], 'interrupted command was absent from ledger')
            self.assertEqual(result['receipt']['outcome'], mode)
            self.assertNotEqual(result['receipt']['exit_code'], 0)

    def test_ctrl_c_terminates_owned_process_and_records_attempt(self):
        self.lab()
        self.process_failure('interrupt')

    def test_timeout_records_terminated_attempt(self):
        self.lab()
        self.process_failure('timeout')

    def test_guard_is_linux_only_and_denies_socket_operations(self):
        lab = self.lab()
        self.assertEqual(lab.NETWORK_DENIED_SYSCALLS, ('socket', 'socketpair', 'connect'))
        source = SCRIPT.read_text()
        self.assertIn('start_new_session=True', source)
        self.assertIn('os.killpg', source)
        self.assertNotIn('shell=True', source)


if __name__ == '__main__':
    unittest.main()
