"""The generated Atmos stack input is the single authoritative desired policy.

Expected values come from the reviewed normalized fixture and hand-written
cases, not from the generator under test.
"""
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from intune_iac.engine import generate
from intune_iac.repository import resolve_component
from reference.core import stack_input_problems, stack_input_text

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'examples/supported/input/export.json'
CONTEXT = ROOT / 'examples/context.json'


class StackInputTests(unittest.TestCase):
    def test_generated_stack_input_round_trips_through_the_repository_resolver(self):
        normalized = json.loads((ROOT / 'examples/supported/expected/normalized.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'project'
            generate(SOURCE, CONTEXT, output)
            self.assertFalse((output / 'components/terraform/intune-reference/adoption-input.json').exists())
            report = resolve_component(output, 'orgs/reference/dev', 'intune-reference')
            self.assertEqual(report['status'], 'resolved')
            variables = report['effective']['vars']
            self.assertEqual(variables['policies'], {normalized['key']: normalized['desired']})
            self.assertIs(variables['live_qualification_ack'], False)
            self.assertEqual(variables['policies'][normalized['key']]['role_scope_tag_ids'], ['0'])
            self.assertIn('var.policies', (output / 'components/terraform/intune-reference/main.tf').read_text())

    def test_template_syntax_in_the_source_gives_an_explicit_review_only_package(self):
        source = json.loads(SOURCE.read_text())
        policies = [c for c in source['collections'] if c['kind'] == 'policies']
        policies[0]['pages'][0]['body']['value'][0]['description'] = 'Literal ${not_a_reference} in a description'
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'export.json'; path.write_text(json.dumps(source))
            output = Path(temp) / 'project'
            result = generate(path, CONTEXT, output)
            self.assertFalse(result['offline_mapping_complete'])
            self.assertIn('stack_input_template_syntax', result['blocker_codes'])
            self.assertTrue((output / 'BLOCKED.json').exists())
            self.assertFalse((output / 'stacks').exists())

    def test_representability_rules(self):
        self.assertEqual(stack_input_problems({'a': 'x{{y'}), ['stack_input_template_syntax'])
        self.assertEqual(stack_input_problems({'b': ['{%']}), ['stack_input_template_syntax'])
        self.assertEqual(stack_input_problems({'k${': 1}), ['stack_input_template_syntax'])
        self.assertEqual(stack_input_problems({'n': 2 ** 53}), ['stack_input_integer_range'])
        self.assertEqual(stack_input_problems({'n': -(2 ** 53)}), ['stack_input_integer_range'])
        self.assertEqual(stack_input_problems({'n': 2 ** 53 - 1, 'b': True, 's': '{ { } $ {'}), [])
        self.assertEqual(stack_input_problems({'a': '${', 'n': 2 ** 60}),
                         ['stack_input_integer_range', 'stack_input_template_syntax'])

    def test_characters_yaml_would_fold_or_reject_are_escaped_and_round_trip(self):
        value = {'description': 'line\u2028sep\x85nel\x7fdel\ufeffbom \u00e9 \U0001f600', 'role_scope_tag_ids': ['0'],
                 'none': None, 'empty': [], 'flag': False, 'count': 7}
        text = 'vars:\n  policies:\n    key: ' + stack_input_text(value, 4) + '\n'
        for char in ('\u2028', '\x85', '\x7f', '\ufeff'):
            self.assertNotIn(char, text)
        self.assertEqual(yaml.safe_load(text)['vars']['policies']['key'], value)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'stacks').mkdir(); (root / 'components/terraform/c').mkdir(parents=True)
            (root / 'atmos.yaml').write_text('stacks:\n  base_path: stacks\n  included_paths: ["s.yaml"]\n'
                                             'components:\n  terraform:\n    base_path: components/terraform\n')
            (root / 'stacks/s.yaml').write_text('components:\n  terraform:\n    c:\n      ' +
                                                text.replace('\n', '\n      ').rstrip() + '\n')
            report = resolve_component(root, 's', 'c')
            self.assertEqual(report['status'], 'resolved', report.get('reason'))
            self.assertEqual(report['effective']['vars']['policies']['key'], value)


if __name__ == '__main__':
    unittest.main()
