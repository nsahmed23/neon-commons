import tempfile
import unittest
from pathlib import Path

from intune_iac.io import AppError


class NativeAtmosTests(unittest.TestCase):
    def repository(self, root):
        (root/'stacks').mkdir();(root/'components/terraform/policy').mkdir(parents=True)
        (root/'atmos.yaml').write_text("stacks: {base_path: stacks, included_paths: ['**/*'], name_pattern: '{stage}'}\ncomponents: {terraform: {base_path: components/terraform, command: tofu}}\n")
        (root/'stacks/physical.yaml').write_text('vars: {stage: pilot, tenant: descriptive-label}\ncomponents: {terraform: {policy: {vars: {value: 1}}}}\n')
        (root/'components/terraform/policy/main.tf').write_text('variable "value" { type = number }\n')

    def test_logical_mapping_is_component_context_not_entra_identity(self):
        from intune_iac.native_atmos import expected_logical_stack
        from intune_iac.repository import resolve_component
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.repository(root)
            expected=resolve_component(root,'physical','policy')
            self.assertEqual(expected_logical_stack(root,expected),'pilot')
            self.assertEqual(expected['tenant_verification'],'not_established')

    def test_dynamic_repository_rejected_before_native_launch(self):
        from intune_iac.native_atmos import resolve_native_atmos
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.repository(root)
            (root/'stacks/physical.yaml').write_text('vars: {stage: !exec "whoami"}\n')
            result=resolve_native_atmos(root,'physical','policy',executable=root/'absent')
            self.assertEqual(result['status'],'blocked')
            self.assertFalse(result['native_executed'])

    def test_substituted_binary_rejected(self):
        from intune_iac.native_atmos import resolve_native_atmos
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.repository(root)
            binary=root/'atmos';binary.write_text('malicious')
            with self.assertRaises(AppError) as raised:
                resolve_native_atmos(root,'physical','policy',executable=binary)
            self.assertEqual(raised.exception.code,'unqualified_atmos_executable')

    def test_missing_naming_context_and_selector_injection_rejected(self):
        from intune_iac.native_atmos import expected_logical_stack, resolve_native_atmos
        from intune_iac.repository import resolve_component
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.repository(root)
            (root/'atmos.yaml').write_text("stacks: {base_path: stacks, name_pattern: '{region}'}\n")
            with self.assertRaises(AppError):expected_logical_stack(root,resolve_component(root,'physical','policy'))
            answer=resolve_native_atmos(root,'--help','policy',executable=root/'absent')
            self.assertEqual(answer['status'],'blocked')
