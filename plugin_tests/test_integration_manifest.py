"""The Intune integration manifest (integration-manifest/1): data only, built from facts the repository already holds.

Every value the manifest repeats is compared with the value at its source as it stands today. The sources are read
here, never copied: the family table is parsed from family-coverage.csv, the setup pins are read from the source text
of wizard.py, and the profiles, evidence classes, scopes and operations come from the modules that own them. Nothing
here touches a real workspace, a home directory, the network or a credential; every loader failure case uses a
temporary directory.
"""
import ast
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'contracts' / 'integration-manifest.json'
LEVEL_WORDS = {'discover-only', 'export-only', 'review-only', 'adoption-qualified', 'change-qualified'}
CSV_COLUMNS = ('family', 'candidate', 'material', 'release_stage', 'qualification_needed', 'live')


def module():
    from intune_iac import integration_manifest
    return integration_manifest


def manifest():
    return module().load()


def csv_rows():
    with open(ROOT / 'family-coverage.csv', encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream, strict=True))


def wizard_pins():
    """The pinned setup context, read from the source text of wizard.py (it is local to a function)."""
    tree = ast.parse((ROOT / 'intune_iac' / 'wizard.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_validate_selection_context':
            for statement in ast.walk(node):
                if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                        and getattr(statement.targets[0], 'id', None) == 'pinned'):
                    return ast.literal_eval(statement.value)
    raise AssertionError('wizard.py no longer holds the pinned setup context where this test reads it')


class ManifestContentTests(unittest.TestCase):
    def test_it_parses_with_the_expected_version_and_identity(self):
        value = manifest()
        self.assertEqual(value['schema_version'], 'integration-manifest/1')
        self.assertEqual(module().VERSION, 'integration-manifest/1')
        plugin = json.loads((ROOT / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(value['integration']['id'], 'intune')
        self.assertEqual(value['integration']['product'], plugin['name'])
        self.assertEqual(value['integration']['product_version'], plugin['version'])

    def test_the_description_says_a_catalog_entry_is_not_lifecycle_qualification(self):
        self.assertIn('not lifecycle qualification', manifest()['description'])

    def test_every_family_row_has_exactly_one_entry_and_no_entry_lacks_a_row(self):
        rows = csv_rows()
        entries = manifest()['families']
        self.assertEqual([entry['family'] for entry in entries], [row['family'] for row in rows])
        self.assertEqual(len({entry['family'] for entry in entries}), len(entries))
        for row, entry in zip(rows, entries):
            self.assertEqual({name: entry[name] for name in CSV_COLUMNS}, {name: row[name] for name in CSV_COLUMNS})

    def test_setup_pins_equal_the_values_in_the_wizard_and_the_start_context_keys(self):
        from intune_iac.entry import CONTEXT_KEYS
        context = manifest()['setup_context']
        self.assertEqual(context['pinned'], wizard_pins())
        self.assertEqual(context['start_context_keys'], sorted(CONTEXT_KEYS))

    def test_host_profiles_equal_the_profile_requirements(self):
        from intune_iac.host_capabilities import _PROFILE_REQUIREMENTS
        profiles = manifest()['host_profiles']
        self.assertEqual({name: tuple(value['requires']) for name, value in profiles.items()}, _PROFILE_REQUIREMENTS)

    def test_evidence_classes_and_live_blockers_equal_the_journey_contract(self):
        from intune_iac import journey
        value = manifest()
        self.assertEqual(value['evidence_classes'], journey.semantic_contract()['evidence_classes'])
        self.assertEqual(value['live_blockers'], list(journey.LIVE_BLOCKERS))

    def test_required_scopes_equal_the_identity_binding_scopes(self):
        from intune_iac import identity_binding
        self.assertEqual(manifest()['required_scopes'], {
            'graph': identity_binding._GRAPH_SCOPE, 'arm': identity_binding._ARM_SCOPE,
            'storage': identity_binding._STORAGE_SCOPE})

    def test_input_formats_equal_their_schema_files(self):
        formats = {item['id']: item for item in manifest()['input_formats']}
        self.assertEqual(set(formats), {'export-intake', 'capture'})
        for item in formats.values():
            schema = json.loads((ROOT / item['schema_file']).read_text(encoding='utf-8'))
            self.assertEqual(schema['title'], item['id'])
            self.assertEqual(schema['$id'], item['schema_id'])
        export = json.loads((ROOT / 'contracts/export-intake.schema.json').read_text(encoding='utf-8'))
        capture = json.loads((ROOT / 'corrections/contracts/capture.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(formats['export-intake']['schema_version'], export['properties']['schema_version']['const'])
        self.assertEqual(formats['export-intake']['collection_kinds'],
                         export['properties']['collections']['items']['properties']['kind']['enum'])
        self.assertEqual(formats['capture']['collection_kinds'], capture['properties']['kind']['enum'])

    def test_object_kinds_name_real_families_formats_operations_and_facets(self):
        from intune_iac import execution, graph, journey
        value = manifest()
        families = {entry['family']: entry for entry in value['families']}
        formats = {item['id'] for item in value['input_formats']}
        kinds = {kind['id']: kind for kind in value['object_kinds']}
        self.assertEqual(len(kinds), len(value['object_kinds']))
        self.assertIn(graph.FAMILY, kinds)
        for identifier, kind in kinds.items():
            self.assertEqual(families[kind['family']]['object_kind'], identifier)
            self.assertLessEqual(set(kind['input_formats']), formats)
        self.assertEqual({entry['object_kind'] for entry in families.values() if entry['object_kind']}, set(kinds))
        policy = kinds[graph.FAMILY]
        stages = journey.semantic_contract()['stages']
        self.assertEqual([item['name'] for item in policy['operations']], list(journey.STAGES))
        for item in policy['operations']:
            self.assertEqual(item['evidence_class'], stages[item['name']]['evidence_class'])
        self.assertEqual(policy['facets'], list(execution.FACETS))

    def test_no_level_other_than_unknown_appears_without_a_named_record(self):
        value = manifest()
        for kind in value['object_kinds']:
            if kind['level'] == 'unknown':
                self.assertIsNone(kind['level_record'], kind['id'])
                continue
            self.assertIn(kind['level'], LEVEL_WORDS, kind['id'])
            record = kind['level_record']
            self.assertIsInstance(record, dict, kind['id'])
            text = (ROOT / record['path']).read_text(encoding='utf-8-sig')
            self.assertIn(record['quote'], text, kind['id'])
            self.assertTrue(record['locator'], kind['id'])

    def test_the_review_only_level_follows_the_release_stage_in_the_family_table(self):
        value = manifest()
        rows = {row['family']: row for row in csv_rows()}
        for kind in value['object_kinds']:
            if kind['level'] == 'review-only':
                self.assertEqual(kind['level_record']['path'], 'family-coverage.csv')
                self.assertEqual(rows[kind['family']]['release_stage'], 'review only')

    def test_a_level_is_never_claimed_for_a_family_the_table_leaves_unqualified(self):
        rows = {row['family']: row for row in csv_rows()}
        for kind in manifest()['object_kinds']:
            if kind['level'] != 'unknown':
                self.assertNotEqual(rows[kind['family']]['live'], 'passed')
        levels = {kind['id']: kind['level'] for kind in manifest()['object_kinds']}
        self.assertNotIn('adoption-qualified', levels.values())
        self.assertNotIn('change-qualified', levels.values())


class LoaderTests(unittest.TestCase):
    def load_text(self, text):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'integration-manifest.json'
            path.write_text(text, encoding='utf-8')
            return module().load(path)

    def load_changed(self, change):
        value = copy.deepcopy(json.loads(MANIFEST.read_text(encoding='utf-8')))
        change(value)
        return self.load_text(json.dumps(value))

    def refused(self, code, call):
        from intune_iac.io import AppError
        with self.assertRaises(AppError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        self.assertTrue(caught.exception.message)
        return caught.exception

    def test_the_shipped_file_loads_unchanged_through_a_temporary_copy(self):
        self.assertEqual(self.load_text(MANIFEST.read_text(encoding='utf-8')), manifest())

    def test_a_missing_file_is_refused_with_the_loader_error(self):
        with tempfile.TemporaryDirectory() as temp:
            self.refused('integration_manifest_unreadable', lambda: module().load(Path(temp) / 'absent.json'))

    def test_a_malformed_file_is_refused_with_the_loader_error(self):
        for text in ('', '{', '[]', '"integration-manifest/1"', '{"schema_version": "integration-manifest/1", "schema_version": "x"}'):
            self.refused('integration_manifest_malformed', lambda text=text: self.load_text(text))

    def test_an_unknown_version_is_refused_and_named(self):
        error = self.refused('integration_manifest_version_unsupported',
                             lambda: self.load_changed(lambda value: value.update(schema_version='integration-manifest/2')))
        self.assertIn('integration-manifest/2', error.message)
        self.refused('integration_manifest_version_unsupported', lambda: self.load_text('{"description": "no version"}'))

    def test_a_missing_or_extra_top_level_key_is_refused(self):
        self.refused('integration_manifest_malformed', lambda: self.load_changed(lambda value: value.pop('families')))
        self.refused('integration_manifest_malformed', lambda: self.load_changed(lambda value: value.update(extra=1)))

    def test_a_wrong_type_is_refused(self):
        self.refused('integration_manifest_malformed', lambda: self.load_changed(lambda value: value.update(object_kinds={})))
        self.refused('integration_manifest_malformed', lambda: self.load_changed(lambda value: value['families'][0].update(live=3)))

    def test_a_duplicate_family_or_object_kind_is_refused(self):
        self.refused('integration_manifest_malformed',
                     lambda: self.load_changed(lambda value: value['families'].append(copy.deepcopy(value['families'][0]))))
        self.refused('integration_manifest_malformed',
                     lambda: self.load_changed(lambda value: value['object_kinds'].append(copy.deepcopy(value['object_kinds'][0]))))

    def test_a_level_outside_the_guides_words_is_refused(self):
        self.refused('integration_manifest_malformed',
                     lambda: self.load_changed(lambda value: value['object_kinds'][0].update(level='qualified')))

    def test_a_level_without_a_named_record_is_refused(self):
        def claim(value):
            value['object_kinds'][0].update(level='change-qualified', level_record=None)
        self.refused('integration_manifest_malformed', lambda: self.load_changed(claim))

    def test_a_record_that_escapes_the_repository_is_refused(self):
        def claim(value):
            value['object_kinds'][0].update(level='review-only', level_record={'path': '../outside.txt', 'quote': 'x', 'locator': 'y'})
        self.refused('integration_manifest_malformed', lambda: self.load_changed(claim))

    def test_unknown_with_a_record_is_refused(self):
        def claim(value):
            value['object_kinds'][0].update(level='unknown', level_record={'path': 'family-coverage.csv', 'quote': 'x', 'locator': 'y'})
        self.refused('integration_manifest_malformed', lambda: self.load_changed(claim))

    def test_a_kind_naming_an_absent_family_or_an_unlisted_kind_is_refused(self):
        self.refused('integration_manifest_malformed',
                     lambda: self.load_changed(lambda value: value['object_kinds'][0].update(family='No such family')))
        self.refused('integration_manifest_malformed',
                     lambda: self.load_changed(lambda value: value['families'][0].update(object_kind='no_such_kind')))


class FamiliesReadTheManifestTests(unittest.TestCase):
    def test_the_workbench_presence_in_the_families_view_comes_from_the_manifest(self):
        from intune_iac import families as families_module
        value = manifest()
        for entry in value['families']:
            if entry['family'] == 'Win32 apps':
                entry['workbench_presence'] = 'a sentence only the manifest holds'
        with patch.object(module(), 'load', return_value=value):
            rows = {row['family']: row for row in families_module.families()['families']}
        self.assertEqual(rows['Win32 apps']['workbench'], 'a sentence only the manifest holds')
        self.assertIn('estate', rows['Windows plain Settings Catalog']['workbench'])

    def test_the_families_view_still_lists_every_row_of_the_table_in_order(self):
        from intune_iac.families import families
        value = families()
        self.assertEqual([row['family'] for row in value['families']], [row['family'] for row in csv_rows()])
        by_family = {entry['family']: entry for entry in manifest()['families']}
        for row in value['families']:
            self.assertEqual(row['workbench'], by_family[row['family']]['workbench_presence'])

    def test_a_refused_manifest_is_reported_by_the_families_view_instead_of_failing(self):
        from intune_iac.families import families
        from intune_iac.io import AppError
        error = AppError('integration_manifest_version_unsupported', 'The integration manifest has an unsupported version.')
        with patch.object(module(), 'load', side_effect=error):
            value = families()
        self.assertEqual((value['available'], value['reason']), (False, 'integration_manifest_version_unsupported'))
        self.assertEqual(value['families'], [])
        self.assertIn('unsupported version', value['detail'])
        self.assertFalse(value['execution_authorized'])


if __name__ == '__main__':
    unittest.main()
