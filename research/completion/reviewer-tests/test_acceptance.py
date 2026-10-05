"""Independent bounded acceptance regressions; no tenant/provider calls.

The native admission check intercepts dispatch and never executes repository
configuration. This is evidence about the admission boundary, not an exploit.
"""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac.io import AppError
from intune_iac.mcp import FilesystemAuthority, call_tool
from intune_iac.synthetic import generate_estate, inspect_estate, simulate_local_transition


def plan_digest(estate):
    return hashlib.sha256(json.dumps(estate['plan'], sort_keys=True,
        separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class SyntheticAcceptance(unittest.TestCase):
    def assert_not_converged(self, estate):
        result = simulate_local_transition(estate)
        self.assertFalse(result['converged'], result)
        self.assertNotEqual(result['status'], 'converged')

    def test_missing_all_state_objects_is_not_converged(self):
        estate = generate_estate()
        estate['state']['objects'] = {}
        self.assert_not_converged(estate)

    def test_lost_assignment_is_not_converged(self):
        estate = generate_estate()
        next(iter(estate['state']['objects'].values()))['assignments'] = []
        self.assert_not_converged(estate)

    def test_empty_action_coverage_is_not_converged(self):
        estate = generate_estate()
        estate['plan']['actions'] = []
        estate['approval']['plan_sha256'] = plan_digest(estate)
        self.assert_not_converged(estate)

    def test_inspection_detects_missing_state_objects(self):
        estate = generate_estate()
        estate['state']['objects'] = {}
        self.assertFalse(inspect_estate(estate)['success'])

    def test_baseline_positive_control(self):
        estate = generate_estate()
        self.assertTrue(inspect_estate(estate)['success'])
        self.assertTrue(simulate_local_transition(estate)['converged'])


class AuthorityAcceptance(unittest.TestCase):
    def test_nested_action_read_is_confined_before_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            allowed = base / 'allowed'; allowed.mkdir()
            outside = base / 'outside.json'; outside.write_text('{}')
            authority = FilesystemAuthority([allowed], [allowed])
            for action, parameters in (
                ('inspect', {'input': str(outside), 'context': str(allowed/'context.json')}),
                ('graph_build', {'input': str(allowed/'capture.json'), 'output': str(allowed/'out.json'), 'atmos_root': str(base)}),
                ('repository_resolve', {'root': str(base), 'stack': 'a', 'component': 'b'}),
            ):
                with self.subTest(action=action), patch('intune_iac.runner.run') as dispatch:
                    with self.assertRaises(AppError) as raised:
                        call_tool('intune_run_local', {'action': action, 'parameters': parameters,
                            'state_dir': str(allowed/'journal')}, authority=authority)
                    self.assertEqual(raised.exception.code, 'filesystem_authority_denied')
                    dispatch.assert_not_called()
            self.assertEqual(list(allowed.iterdir()), [])


class NativeAdmissionAcceptance(unittest.TestCase):
    def assert_unadmitted_source_rejected(self, unrelated, selected_extra='', reject=True):
        from intune_iac.native_atmos import resolve_native_atmos
        from intune_iac.repository import resolve_component
        binary = Path('/tmp/intune-native-completion/atmos')
        if not binary.is_file(): self.skipTest('exact pinned local Atmos is unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'stacks').mkdir()
            (root/'components/terraform/policy').mkdir(parents=True)
            (root/'atmos.yaml').write_text("stacks: {base_path: stacks, included_paths: ['**/*'], name_pattern: '{stage}'}\ncomponents: {terraform: {base_path: components/terraform, command: tofu}}\n")
            selected = 'vars: {stage: pilot}\ncomponents:\n  terraform:\n    policy: {vars: {value: 1}}\n'
            (root/'stacks/physical.yaml').write_text(selected + selected_extra)
            if unrelated is not None:
                (root/'stacks/unrelated.yaml').write_text(unrelated)
            expected = resolve_component(root, 'physical', 'policy')
            native = dict(expected['effective'], atmos_stack='pilot', atmos_manifest='physical', component='policy')
            with patch('intune_iac.protected._supervise', return_value=json.dumps(native).encode()) as dispatch:
                result = resolve_native_atmos(root, 'physical', 'policy', executable=binary)
            if reject:
                dispatch.assert_not_called()
                self.assertEqual(result['status'], 'blocked')
            else:
                dispatch.assert_called_once()
                self.assertEqual(result['status'], 'verified')

    def test_literal_repository_positive_control(self):
        self.assert_unadmitted_source_rejected(
            'vars: {stage: secondary}\ncomponents: {terraform: {policy: {vars: {value: 2}}}}\n', reject=False)

    def test_unrelated_included_stack_is_admitted_before_dispatch(self):
        self.assert_unadmitted_source_rejected('import: [../../outside]\nvars: {stage: !exec "hostile-command"}\n')

    def test_unrelated_plain_import_traversal_rejected_before_dispatch(self):
        self.assert_unadmitted_source_rejected('import: [../../outside]\nvars: {stage: secondary}\n')

    def test_unselected_component_runtime_field_rejected_before_dispatch(self):
        self.assert_unadmitted_source_rejected(None,
            '    unselected:\n      hooks: {after: [hostile-command]}\n      vars: {stage: secondary}\n')


if __name__ == '__main__': unittest.main(verbosity=2)
