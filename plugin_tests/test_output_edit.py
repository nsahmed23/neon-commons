"""Recognizing a repository-owned edit of the desired policy inside generated output.

The supported example is generated into a temporary directory, then edited by
hand as an engineer would. The expected classifications are written by hand.
"""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from intune_iac.engine import generate

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / 'examples/supported/input/export.json'
CONTEXT = ROOT / 'examples/context.json'
STACK = 'stacks/orgs/reference/dev.yaml'
KEY = 'p_11111111111141118111111111111111_22222222222242228222222222222222'
OBSERVED = '"description": "Synthetic reference; not production advice."'
EDITED = '"description": "Synthetic reference; reviewed repository edit."'


def tree(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(root).rglob('*')) if path.is_file()}


class OutputEditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = self.root / 'generated'
        generate(EXPORT, CONTEXT, self.output)
        self.stack = self.output / STACK

    def classify(self, source=EXPORT):
        from intune_iac.output_edit import classify
        value = classify(source, CONTEXT, self.output)
        self.assertEqual(value['schema_version'], 'generated-output-edit/1')
        self.assertFalse(value['execution_authorized'])
        return value

    def replace(self, old, new):
        text = self.stack.read_text()
        self.assertEqual(text.count(old), 1, old)
        self.stack.write_text(text.replace(old, new))

    def test_unchanged_output_is_unchanged(self):
        value = self.classify()
        self.assertEqual(value['classification'], 'unchanged')
        self.assertEqual((value['changed'], value['added'], value['removed']), ([], [], []))

    def test_an_edit_inside_the_policy_is_repository_owned(self):
        self.replace(OBSERVED, EDITED)
        value = self.classify()
        self.assertEqual(value['classification'], 'repository_owned_policy_edit')
        self.assertEqual(value['changed'], [STACK])
        self.assertEqual((value['policy_key'], value['pointer']), (KEY, '/vars/policies/' + KEY))
        self.assertTrue(value['values_changed'])
        self.assertEqual(value['verification'], 'stale')
        changes = value['field_changes']
        self.assertEqual(changes['status'], 'changed')
        self.assertEqual([(c['field'], c['before'], c['after']) for c in changes['changes']],
                         [('description', 'Synthetic reference; not production advice.', 'Synthetic reference; reviewed repository edit.')])
        self.assertIn('repository-import', ' '.join(value['next_steps']))

    def test_a_comment_only_edit_changes_no_value(self):
        self.replace('# Authoritative desired policy', '# Reviewed. Authoritative desired policy')
        value = self.classify()
        self.assertEqual(value['classification'], 'repository_owned_policy_edit')
        self.assertFalse(value['values_changed'])
        self.assertEqual(value['field_changes']['status'], 'no_change')

    def test_an_edit_outside_the_policy_is_another_change(self):
        self.replace('command: tofu', 'command: terraform')
        value = self.classify()
        self.assertEqual((value['classification'], value['reason']), ('other_change', 'stack_changed_outside_the_policy'))

    def test_a_second_policy_key_is_another_change(self):
        self.replace('        policies:\n', '        policies:\n          p_extra: {}\n')
        value = self.classify()
        self.assertEqual((value['classification'], value['reason']), ('other_change', 'policy_keys_changed'))

    def test_another_changed_file_is_another_change(self):
        self.replace(OBSERVED, EDITED)
        (self.output / 'README.md').write_text('edited\n')
        value = self.classify()
        self.assertEqual((value['classification'], value['reason']), ('other_change', 'files_besides_the_stack_changed'))
        self.assertEqual(value['changed'], ['README.md', STACK])

    def test_an_added_file_is_another_change(self):
        self.replace(OBSERVED, EDITED)
        (self.output / 'components/terraform/intune-reference/override.tf').write_text('output "x" {\n  value = 1\n}\n')
        value = self.classify()
        self.assertEqual(value['classification'], 'other_change')
        self.assertEqual(value['added'], ['components/terraform/intune-reference/override.tf'])

    def test_a_duplicate_key_is_refused_by_the_repository_loader(self):
        self.replace('      command: tofu\n', '      command: tofu\n      command: tofu\n')
        value = self.classify()
        self.assertEqual((value['classification'], value['reason']), ('other_change', 'stack_not_literal'))
        self.assertEqual(value['blocker']['code'], 'duplicate_yaml_key')

    def test_a_template_value_is_refused_by_the_repository_loader(self):
        self.replace(OBSERVED, '"description": "{{ .vars.stage }}"')
        value = self.classify()
        self.assertEqual((value['classification'], value['reason']), ('other_change', 'stack_not_literal'))
        self.assertEqual(value['blocker']['code'], 'dynamic_value')

    def test_an_edited_manifest_is_another_change(self):
        manifest = self.output / 'generated-files.json'
        manifest.write_bytes(manifest.read_bytes() + b'\n')
        self.assertEqual(self.classify()['classification'], 'other_change')

    def test_a_changed_source_cannot_be_attributed_to_the_engineer(self):
        # The same edit appears in the stack, but the source that should have produced the output changed too:
        # the source receipt no longer matches, so the change is not classified as the engineer's.
        text = EXPORT.read_text()
        self.assertGreater(text.count('Synthetic reference; not production advice.'), 0)
        source = self.root / 'export.json'
        source.write_text(text.replace('Synthetic reference; not production advice.', 'Synthetic reference; reviewed repository edit.'))
        self.replace(OBSERVED, EDITED)
        value = self.classify(source)
        self.assertEqual((value['classification'], value['reason']), ('other_change', 'files_besides_the_stack_changed'))
        self.assertIn('adoption/source-receipt.json', value['changed'])

    def test_the_classifier_writes_nothing(self):
        self.replace(OBSERVED, EDITED)
        before = tree(self.root)
        self.classify()
        self.assertEqual(tree(self.root), before)


if __name__ == '__main__':
    unittest.main()
