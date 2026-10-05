import json
import tempfile
import unittest
from pathlib import Path

from intune_iac.repository import discover_repository, public_resolution, resolve_component


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.put('atmos.yaml', 'stacks:\n  base_path: stacks\n  included_paths: ["deploy/**/*"]\ncomponents:\n  terraform:\n    base_path: components/terraform\n    command: tofu\n')

    def put(self, path, text):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def resolve(self, component='app'):
        return resolve_component(self.root, 'deploy/dev', component)

    def codes(self, report):
        return {b['code'] for b in report['blockers']}

    def minimal(self):
        self.put('stacks/deploy/dev.yaml', 'components:\n  terraform:\n    app:\n      vars: {region: west}\n')

    def test_ordered_imports_local_and_scoped_component_overrides(self):
        self.put('stacks/first.yaml', 'vars: {root: one, same: one}\ncomponents:\n  terraform:\n    base:\n      metadata: {type: abstract, component: wrong}\n      vars: {same: base, first: yes-string, items: [a, b]}\n')
        self.put('stacks/second.yaml', 'vars: {root: two, same: two}\ncomponents:\n  terraform:\n    later:\n      metadata: {type: abstract}\n      vars: {same: later, items: [c]}\n')
        self.put('stacks/deploy/dev.yaml', 'import: [first, second]\nvars: {root: local}\nterraform:\n  vars: {typed: true, same: type}\ncomponents:\n  terraform:\n    app:\n      metadata:\n        component: real/module\n        inherits: [base, later]\n      vars: {same: own}\n      overrides:\n        vars: {same: final}\n')
        result = self.resolve()
        self.assertEqual(result['status'], 'resolved', result)
        self.assertEqual(result['effective']['vars'], {'root': 'local', 'same': 'final', 'first': 'yes-string', 'items': ['c'], 'typed': True})
        self.assertEqual(result['effective']['command'], 'tofu')
        self.assertEqual(result['implementation'], 'real/module')
        origin = result['provenance']['/vars/same']
        self.assertEqual(origin['winner']['pointer'], '/components/terraform/app/overrides/vars/same')
        self.assertGreaterEqual(len(origin['history']), 6)
        self.assertFalse(result['execution_authorized'])

    def test_inheritance_does_not_inherit_metadata_component_or_parent_overrides(self):
        self.put('stacks/deploy/dev.yaml', 'components:\n  terraform:\n    base:\n      metadata: {type: abstract, component: elsewhere}\n      vars: {color: blue}\n      overrides:\n        vars: {color: red}\n    app:\n      metadata: {inherits: [base]}\n')
        result = self.resolve()
        self.assertEqual(result['status'], 'resolved', result)
        self.assertEqual(result['implementation'], 'app')
        self.assertEqual(result['effective']['vars']['color'], 'blue')
        self.assertNotIn('type', result['effective']['metadata'])

    def test_imported_components_are_discovered_and_abstract_not_selectable(self):
        self.put('stacks/base.yaml', 'components:\n  terraform:\n    base:\n      metadata: {type: abstract}\n    app:\n      vars: {client_secret: top-secret, tenant: org-label}\n')
        self.put('stacks/deploy/dev.yaml', 'import: [base]\n')
        report = discover_repository(self.root)
        self.assertEqual(report['status'], 'discovered', report)
        self.assertEqual([s['stack'] for s in report['stacks']], ['deploy/dev'])
        components = {c['name']: c for c in report['stacks'][0]['components']}
        self.assertTrue(components['app']['selectable'])
        self.assertFalse(components['base']['selectable'])
        self.assertNotIn('top-secret', json.dumps(report))
        self.assertNotIn('org-label', json.dumps(report))
        self.assertEqual(report['stack_identity'], 'physical_manifest_selector')

    def test_public_resolution_excludes_values_and_has_hash(self):
        self.put('stacks/deploy/dev.yaml', 'components:\n  terraform:\n    app:\n      env: {TOKEN: never-expose}\n')
        raw = self.resolve()
        report = public_resolution(raw)
        self.assertEqual(report['status'], 'resolved', report)
        self.assertNotIn('effective', report)
        self.assertNotIn('never-expose', json.dumps(report))
        self.assertEqual(len(report['configuration_sha256']), 64)
        self.assertIn('/env/TOKEN', report['effective_fields'])
        self.assertEqual(raw['effective']['env']['TOKEN'], 'never-expose')

    def test_recursive_literal_imports_and_relative_imports(self):
        self.put('stacks/common.yaml', 'vars: {one: first}\n')
        self.put('stacks/deploy/local.yaml', 'import: [common]\nvars: {two: second}\n')
        self.put('stacks/deploy/dev.yaml', 'import: [./local.yaml]\ncomponents:\n  terraform:\n    app: {}\n')
        self.assertEqual(self.resolve()['effective']['vars'], {'one':'first', 'two':'second'})

    def test_source_fingerprint_tracks_import_bytes_hcl_lock_and_file_additions(self):
        self.minimal()
        one = self.resolve()['source_fingerprint']
        self.put('components/terraform/app/main.tf', '# source one\n')
        two = self.resolve()['source_fingerprint']
        self.put('components/terraform/app/.terraform.lock.hcl', '# lock\n')
        three = self.resolve()['source_fingerprint']
        self.put('stacks/unselected.yaml', 'vars: {x: y}\n')
        four = self.resolve()['source_fingerprint']
        self.assertEqual(len({one, two, three, four}), 4)
        self.put('components/terraform/app/.terraform/runtime.tf', '# ignored\n')
        self.assertEqual(self.resolve()['source_fingerprint'], four)
        self.assertEqual(self.resolve(), self.resolve())

    def test_missing_import_and_cycles_block_without_effective(self):
        for value, expected in [('import: [missing]', 'missing_import'), ('import: [./dev.yaml]', 'import_cycle')]:
            with self.subTest(value=value):
                self.put('stacks/deploy/dev.yaml', value + '\ncomponents:\n  terraform:\n    app: {}\n')
                report = self.resolve()
                self.assertEqual(report['status'], 'blocked')
                self.assertIn(expected, self.codes(report))
                self.assertNotIn('effective', report)

    def test_inheritance_cycle_and_missing_parent_block(self):
        for parent, expected in [('app', 'inheritance_cycle'), ('absent', 'missing_parent')]:
            with self.subTest(parent=parent):
                self.put('stacks/deploy/dev.yaml', 'components:\n  terraform:\n    app:\n      metadata: {inherits: [' + parent + ']}\n')
                self.assertIn(expected, self.codes(self.resolve()))

    def test_unknown_dynamic_tag_alias_and_duplicate_block(self):
        for value, expected in [('"{{ .env.SECRET }}"', 'dynamic_value'), ('!env SECRET', 'unsupported_yaml_tag'), ('&a [*a]', 'yaml_alias'), ('{x: a, x: b}', 'duplicate_yaml_key')]:
            with self.subTest(value=value):
                self.put('stacks/deploy/dev.yaml', 'components:\n  terraform:\n    app:\n      vars:\n        value: ' + value + '\n')
                report = self.resolve()
                self.assertIn(expected, self.codes(report))
                self.assertNotIn('effective', report)

    def test_unsupported_config_and_import_options_are_explicit(self):
        self.minimal()
        self.put('atmos.yaml', 'stacks: {base_path: stacks}\nsettings: {list_merge_strategy: append}\n')
        self.assertIn('unsupported_list_merge_strategy', self.codes(self.resolve()))
        self.put('atmos.yaml', 'stacks: {base_path: stacks}\n')
        self.put('stacks/deploy/dev.yaml', 'import: [{path: base, context: {x: y}}]\n')
        self.assertIn('unsupported_import_options', self.codes(self.resolve()))

    def test_lists_replace_including_empty_and_type_change_blocks(self):
        self.put('stacks/base.yaml', 'vars: {items: [a, b]}\n')
        for value, expected in [('[c]', None), ('[]', None), ('wrong-type', 'merge_type_conflict')]:
            with self.subTest(value=value):
                self.put('stacks/deploy/dev.yaml', 'import: [base]\nvars: {items: '+value+'}\ncomponents:\n  terraform:\n    app: {}\n')
                report = self.resolve()
                if expected:
                    self.assertIn(expected, self.codes(report))
                else:
                    self.assertEqual(report['effective']['vars']['items'], ['c'] if value == '[c]' else [])

    def test_native_qualified_empty_and_null_import_overrides(self):
        # Mirrors Atmos 1.199.0 offline receipt atmos-empty_values.json.
        self.put('stacks/base.yaml', 'vars: {empty_string: old, zero: 7, disabled: true, null_value: old, empty_list: [old], empty_map: {old: old}}\n')
        self.put('stacks/deploy/dev.yaml', 'import: [base]\nvars: {empty_string: "", zero: 0, disabled: false, null_value: null, empty_list: [], empty_map: {}}\ncomponents:\n  terraform:\n    app: {}\n')
        report = self.resolve()
        self.assertEqual(report['status'], 'resolved', report)
        self.assertEqual(report['effective']['vars'], {'empty_string': '', 'zero': 0, 'disabled': False, 'null_value': None, 'empty_list': [], 'empty_map': {'old': 'old'}})
        self.assertEqual(report['provenance']['/vars/null_value']['winner']['path'], 'stacks/deploy/dev.yaml')

    def test_null_section_is_invalid_despite_null_leaf_support(self):
        self.put('stacks/deploy/dev.yaml', 'components:\n  terraform:\n    app:\n      vars: null\n')
        self.assertIn('expected_mapping', self.codes(self.resolve()))

    def test_native_qualified_null_shape_transitions(self):
        self.put('stacks/base.yaml', 'vars: {null_to_scalar: null, null_to_list: null, null_to_map: null, map_to_null: {old: 1}, list_to_null: [old], scalar_to_null: old}\n')
        self.put('stacks/deploy/dev.yaml', 'import: [base]\nvars: {null_to_scalar: new, null_to_list: [new], null_to_map: {new: 1}, map_to_null: null, list_to_null: null, scalar_to_null: null}\ncomponents:\n  terraform:\n    app: {}\n')
        report = self.resolve()
        self.assertEqual(report['status'], 'resolved', report)
        self.assertEqual(report['effective']['vars'], {'null_to_scalar': 'new', 'null_to_list': ['new'], 'null_to_map': {'new': 1}, 'map_to_null': None, 'list_to_null': None, 'scalar_to_null': None})

    def test_native_qualified_empty_component_and_override_values(self):
        for use_override in (False, True):
            with self.subTest(use_override=use_override):
                own = '      overrides:\n        vars: {text: "", count: 0, enabled: false, removed: null, items: [], nested: {}}\n' if use_override else '      vars: {text: "", count: 0, enabled: false, removed: null, items: [], nested: {}}\n'
                self.put('stacks/deploy/dev.yaml', 'components:\n  terraform:\n    base:\n      vars: {text: old, count: 7, enabled: true, removed: old, items: [old], nested: {old: old}}\n    app:\n      metadata: {inherits: [base]}\n'+own)
                report = self.resolve()
                self.assertEqual(report['status'], 'resolved', report)
                self.assertEqual(report['effective']['vars'], {'text': '', 'count': 0, 'enabled': False, 'removed': None, 'items': [], 'nested': {'old': 'old'}})

    def test_unselected_dynamic_manifest_does_not_block_literal_target(self):
        self.minimal()
        self.put('stacks/unselected.yaml', 'vars: {x: !env SECRET}\n')
        self.assertEqual(self.resolve()['status'], 'resolved')

    def test_backend_and_legacy_component_are_explicit_unknown(self):
        for value in ['backend: {azurerm: {key: state}}', 'component: old-base']:
            self.put('stacks/deploy/dev.yaml', 'components:\n  terraform:\n    app:\n      '+value+'\n')
            report = self.resolve()
            self.assertIn('unsupported_component_field', self.codes(report))
            self.assertNotIn('effective', report)

    def test_selection_is_physical_and_duplicate_engine_name_is_ambiguous(self):
        self.put('stacks/deploy/dev.yaml', 'components:\n  terraform:\n    app: {}\n  helmfile:\n    app: {}\n')
        self.assertIn('ambiguous_component', self.codes(self.resolve()))
        self.assertIn('invalid_stack_selector', self.codes(resolve_component(self.root, '../dev', 'app')))
        self.assertIn('stack_not_discovered', self.codes(resolve_component(self.root, 'org-dev', 'app')))

    def test_symlink_and_escape_are_blocked(self):
        self.minimal()
        (self.root/'stacks/linked.yaml').symlink_to(self.root/'stacks/deploy/dev.yaml')
        self.assertIn('unsafe_symlink', self.codes(self.resolve()))
        (self.root/'stacks/linked.yaml').unlink()
        self.put('atmos.yaml', 'stacks: {base_path: ../outside}\n')
        self.assertIn('unsafe_path', self.codes(self.resolve()))

    def test_file_limit_is_bounded(self):
        from unittest.mock import patch
        self.minimal()
        with patch('intune_iac.repository.MAX_FILES', 1):
            self.assertIn('repository_limit', self.codes(self.resolve()))

    def test_nested_map_provenance_retains_leaf_winners_and_list_replacement(self):
        self.put('stacks/base.yaml', 'vars: {nested: {kept: one, changed: old}, items: [first, second]}\n')
        self.put('stacks/deploy/dev.yaml', 'import: [base]\ncomponents:\n  terraform:\n    app:\n      vars: {nested: {changed: new}, items: [only]}\n')
        result = self.resolve()
        self.assertEqual(result['effective']['vars']['nested'], {'kept': 'one', 'changed': 'new'})
        self.assertEqual(result['provenance']['/vars/nested/kept']['winner']['path'], 'stacks/base.yaml')
        self.assertEqual(result['provenance']['/vars/nested/changed']['winner']['path'], 'stacks/deploy/dev.yaml')
        self.assertEqual(len(result['provenance']['/vars/items']['history']), 2)
        self.assertNotIn('/vars/items/1', result['provenance'])

    def test_excluded_paths_and_global_base_path(self):
        self.put('atmos.yaml', 'base_path: project\nstacks:\n  base_path: stacks\n  included_paths: ["deploy/**/*"]\n  excluded_paths: ["**/_defaults.yaml"]\n')
        self.put('project/stacks/deploy/_defaults.yaml', 'vars: {x: hidden}\n')
        self.put('project/stacks/deploy/dev.yaml', 'import: [./_defaults]\ncomponents:\n  terraform:\n    app: {}\n')
        report = discover_repository(self.root)
        self.assertEqual([s['stack'] for s in report['stacks']], ['deploy/dev'])
        result = self.resolve()
        self.assertEqual(result['effective']['vars']['x'], 'hidden')
        self.assertEqual(result['implementation_path'], 'project/components/terraform/app')

    def test_template_shadow_and_dynamic_naming_are_explicit_unknown(self):
        self.put('stacks/base.yaml', 'vars: {x: ordinary}\n')
        self.put('stacks/base.yaml.tmpl', 'vars: {x: rendered}\n')
        self.put('stacks/deploy/dev.yaml', 'import: [base.yaml]\ncomponents:\n  terraform:\n    app: {}\n')
        self.assertIn('template_manifest', self.codes(self.resolve()))
        self.put('atmos.yaml', 'stacks:\n  name_template: "{{.vars.tenant}}"\n')
        self.assertIn('dynamic_value', self.codes(self.resolve()))

    def test_partial_discovery_keeps_other_selectable_components(self):
        self.minimal()
        self.put('stacks/deploy/other.yaml', 'components:\n  terraform:\n    other:\n      vars: {secret: !env PRIVATE}\n')
        report = discover_repository(self.root)
        by_stack = {s['stack']: s for s in report['stacks']}
        self.assertEqual(by_stack['deploy/other']['status'], 'blocked')
        self.assertTrue(by_stack['deploy/dev']['components'][0]['selectable'])
        self.assertNotIn('PRIVATE', json.dumps(report))

    def test_byte_node_and_directory_limits_block(self):
        from unittest.mock import patch
        self.minimal()
        for limit in ('MAX_FILE_BYTES', 'MAX_TOTAL_BYTES', 'MAX_NODES', 'MAX_ENTRIES'):
            with self.subTest(limit=limit), patch('intune_iac.repository.'+limit, 1):
                self.assertIn('repository_limit', self.codes(self.resolve()))

    def test_settings_transforms_and_unsupported_override_sections_block(self):
        for setting, expected in [('settings: {integrations: {github: {x: y}}}', 'unsupported_settings_transform'), ('overrides: {metadata: {component: different}}', 'unsupported_component_override')]:
            self.put('stacks/deploy/dev.yaml', 'components:\n  terraform:\n    app:\n      '+setting+'\n')
            self.assertIn(expected, self.codes(self.resolve()))

    def test_aggregate_provenance_history_is_bounded(self):
        from unittest.mock import patch
        self.put('stacks/deploy/dev.yaml', 'vars: {x: global}\ncomponents:\n  terraform:\n    base:\n      vars: {x: base}\n    app:\n      metadata: {inherits: [base, base, base, base]}\n      vars: {x: own}\n')
        with patch('intune_iac.repository.MAX_HISTORY_ENTRIES', 10, create=True):
            self.assertIn('repository_limit', self.codes(self.resolve()))


if __name__ == '__main__':
    unittest.main()
