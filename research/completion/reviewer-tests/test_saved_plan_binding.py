"""A saved plan must describe the same operation as the reviewed plan JSON.

Only the package's fixed synthetic worker executes. The substitution changes a
JSON output dictionary; it contains no command, interpolation, or executable.
"""
import tempfile
import unittest
from pathlib import Path

from intune_iac import protected as p
from intune_iac.io import AppError, canonical, digest, load_json


class SavedPlanBindingAcceptance(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.executor = p.create_synthetic_executor(self.base/'executor',
            initial_value={}, desired_value={'approved': 1})
        self.request = p.prepare_native_operation(self.executor)
        saved = self.executor.root/'work/saved.tfplan'
        document = load_json(saved)
        document['value'] = {'unreviewed': 2}
        saved.write_bytes(canonical(document))
        self.request['bindings']['saved_plan_sha256'] = p._sha(saved)
        self.request['binding_sha256'] = digest(self.request['bindings'])
        (self.executor.root/'preparation.json').write_bytes(canonical(self.request))
        self.before = (self.executor.root/'work/state/terraform.tfstate').read_bytes()

    def tearDown(self):
        self.temporary.cleanup()

    def test_validation_rejects_rehashed_saved_plan_with_unreviewed_value(self):
        with self.assertRaises(AppError):
            p.validate_native_operation(self.request, executor=self.executor)

    def test_rehashed_saved_plan_cannot_obtain_effectful_approval(self):
        try:
            approval = p.approve_synthetic_operation(self.request, executor=self.executor)
        except AppError:
            self.assertEqual((self.executor.root/'work/state/terraform.tfstate').read_bytes(), self.before)
            return
        result = p.execute_native_operation(self.request, self.base/'receipts',
            executor=self.executor, approval=approval)
        observed = (self.executor.root/'work/state/terraform.tfstate').read_bytes()
        self.assertEqual(observed, self.before,
            'Unreviewed local value was applied before rejection: ' + repr(result))
        self.assertEqual(result['status'], 'rejected')


class NativeSavedPlanBindingAcceptance(unittest.TestCase):
    @unittest.skipUnless(Path('/tmp/intune-native-completion/tofu').is_file(),
                         'exact pinned native OpenTofu unavailable')
    def test_literal_native_binary_substitution_and_matching_sidecar_are_rejected(self):
        """Native plan contains only a harmless output, no resources/provisioners."""
        import copy
        import hashlib
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            executor = p.create_native_local_executor(base/'native',
                executable='/tmp/intune-native-completion/tofu',
                initial_value={}, desired_value={'approved': 1})
            request = p.prepare_native_operation(executor)
            original_state = (executor.root/'work/state/terraform.tfstate').read_bytes()
            config_path = executor.root/'work/main.tf.json'
            original_config = config_path.read_bytes()
            config = load_json(config_path)
            config['output']['fixture']['value'] = {'unreviewed': 2}
            config_path.write_bytes(canonical(config))
            # Produce a real opaque saved plan using the fixed, socket-denied
            # native runner. This output-only plan is never applied.
            p._supervise([str(executor.executable), 'plan', '-input=false',
                '-no-color', '-lock=true', '-lock-timeout=0s',
                '-out='+str(executor.root/'work/saved.tfplan')],
                cwd=executor.root/'work', env=p._environment(executor))
            config_path.write_bytes(original_config)
            request['bindings']['saved_plan_sha256'] = p._sha(executor.root/'work/saved.tfplan')
            request['binding_sha256'] = digest(request['bindings'])
            (executor.root/'preparation.json').write_bytes(canonical(request))
            with self.assertRaises(AppError) as raised:
                p.approve_native_local_operation(request, executor=executor)
            self.assertEqual(raised.exception.code, 'binary_plan_json_mismatch')
            # Also supply the truthful sidecar for the substituted binary. The
            # independent output-only semantic review must reject its new value.
            raw = p._run(executor, 'show')
            (executor.root/'work/plan.json').write_bytes(raw)
            request['bindings']['plan_json_sha256'] = hashlib.sha256(raw).hexdigest()
            request['binding_sha256'] = digest(request['bindings'])
            (executor.root/'preparation.json').write_bytes(canonical(request))
            with self.assertRaises(AppError) as raised:
                p.approve_native_local_operation(request, executor=executor)
            self.assertIn(raised.exception.code, {'native_output_plan_mismatch', 'native_configuration_mismatch'})
            self.assertEqual((executor.root/'work/state/terraform.tfstate').read_bytes(), original_state)
            self.assertFalse((executor.root/'consumed.json').exists())


if __name__ == '__main__': unittest.main(verbosity=2)
