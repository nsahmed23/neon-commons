"""Pinned native OpenTofu output-only convergence and saved-plan preservation."""
from pathlib import Path
import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import protected as p


NATIVE_TEST_EXECUTABLE = os.environ.get('INTUNE_TEST_TOFU_EXECUTABLE', '/tmp/intune-native-completion/tofu')

@unittest.skipUnless(Path(NATIVE_TEST_EXECUTABLE).is_file(), 'pinned native OpenTofu fixture unavailable')
class NativeConvergenceEpochTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.executor = p.create_native_local_executor(self.root / 'executor',
            executable=NATIVE_TEST_EXECUTABLE, initial_value={},
            desired_value={'policy': {'id': 'immutable', 'settings': [True, 7, 'literal']}})
        self.request = p.prepare_native_operation(self.executor)
        grant = p.approve_native_local_operation(self.request, executor=self.executor)
        result = p.execute_native_operation(self.request, self.root / 'receipts', executor=self.executor, approval=grant)
        self.assertEqual(result['status'], 'succeeded_verified', result)
        self.work = self.executor.root / 'work'

    def test_actual_second_plan_is_no_change_without_replacing_approved_plan(self):
        approved = (self.work / 'saved.tfplan').read_bytes()
        before = p._state(self.executor)
        report = p.verify_native_convergence(self.executor, self.request)
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(report['scope'], 'native_local_output_only')
        self.assertEqual(report['changes'], [])
        self.assertEqual(before, p._state(self.executor))
        self.assertEqual((self.work / 'saved.tfplan').read_bytes(), approved)
        self.assertNotEqual(report['second_plan_sha256'], report['approved_saved_plan_sha256'])
        second = json.loads((self.work / 'second-plan.json').read_text())
        self.assertEqual(second['output_changes']['fixture']['actions'], ['no-op'])
        commands = []; original = p._run
        def observe(executor, command):
            commands.append(command)
            return original(executor, command)
        with patch.object(p, '_run', side_effect=observe):
            self.assertEqual(p.reconstruct_native_convergence(self.executor, self.request, report), report)
            self.assertEqual(p.verify_native_convergence(self.executor, self.request), report)
        self.assertNotIn('second_plan', commands)
        self.assertNotIn('apply', commands)

    def test_forged_sidecar_and_report_cannot_hide_saved_plan_mismatch(self):
        report = p.verify_native_convergence(self.executor, self.request)
        sidecar = self.work / 'second-plan.json'
        document = json.loads(sidecar.read_text())
        document['output_changes']['fixture']['after']['policy']['id'] = 'forged'
        sidecar.write_text(json.dumps(document))
        forged = copy.deepcopy(report)
        forged['second_plan_json_sha256'] = p._sha(sidecar)
        with self.assertRaisesRegex(ValueError, 'could not be verified'):
            p.reconstruct_native_convergence(self.executor, self.request, forged)

    def test_lineage_serial_and_original_plan_changes_are_rejected(self):
        report = p.verify_native_convergence(self.executor, self.request)
        state_path = self.work / 'state/terraform.tfstate'
        state_bytes = state_path.read_bytes()
        for field, value in [('lineage', 'forged-lineage'), ('serial', report['serial'] + 1)]:
            with self.subTest(field=field):
                state = json.loads(state_bytes); state[field] = value
                state_path.write_text(json.dumps(state))
                with self.assertRaises(ValueError):
                    p.reconstruct_native_convergence(self.executor, self.request, report)
                state_path.write_bytes(state_bytes)
        (self.work / 'saved.tfplan').write_bytes((self.work / 'second.tfplan').read_bytes())
        with self.assertRaises(ValueError):
            p.reconstruct_native_convergence(self.executor, self.request, report)

    def test_report_type_substitution_does_not_equal_verified_evidence(self):
        report = p.verify_native_convergence(self.executor, self.request)
        for field, value in [('execution_authorized', 0), ('serial', float(report['serial']))]:
            with self.subTest(field=field):
                forged = dict(report); forged[field] = value
                with self.assertRaises(ValueError):
                    p.reconstruct_native_convergence(self.executor, self.request, forged)

    def test_partial_second_plan_is_recovered_without_replanning(self):
        p._run(self.executor, 'second_plan')
        before = (self.work / 'second.tfplan').read_bytes()
        report = p.verify_native_convergence(self.executor, self.request)
        self.assertEqual((self.work / 'second.tfplan').read_bytes(), before)
        self.assertEqual(report['status'], 'verified')

    def test_changed_state_during_second_plan_is_rejected(self):
        original = p._run
        def mutate(executor, command):
            result = original(executor, command)
            if command == 'second_plan':
                path = self.work / 'state/terraform.tfstate'
                state = json.loads(path.read_text()); state['serial'] += 1
                path.write_text(json.dumps(state))
            return result
        with patch.object(p, '_run', side_effect=mutate):
            with self.assertRaises(ValueError):
                p.verify_native_convergence(self.executor, self.request)
        self.assertTrue((self.work / 'second.tfplan').exists())

    def test_concurrent_verifier_and_unexpected_file_are_rejected(self):
        lock = self.executor.root / '.convergence-lock'; lock.write_text('other owner')
        with self.assertRaises(ValueError): p.verify_native_convergence(self.executor, self.request)
        self.assertEqual(lock.read_text(), 'other owner')
        self.assertFalse((self.work / 'second.tfplan').exists())
        lock.unlink(); (self.work / 'unexpected.tf').write_text('')
        with self.assertRaises(ValueError): p.verify_native_convergence(self.executor, self.request)


class NativeSupervisorEvidenceTests(unittest.TestCase):
    def test_raw_stderr_and_exit_status_are_observed_without_changing_return(self):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            evidence = {}
            result = p._supervise([sys.executable, '-I', '-S', '-c',
                "import sys;sys.stdout.write('out');sys.stderr.write('diagnostic')"],
                cwd=Path(directory), env={}, evidence=evidence)
            self.assertEqual(result, b'out')
            self.assertEqual(evidence, {'stdout_bytes': b'out', 'stderr_bytes': b'diagnostic',
                                       'exit_code': 0, 'output_truncated': False})


if __name__ == '__main__': unittest.main()
