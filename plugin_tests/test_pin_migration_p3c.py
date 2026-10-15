"""P3c: the versioned pin migration, generation side.

Step 1 (target descriptor schema v2), step 2 (generation by context version), step 3 (golden projects, oracles) and
step 4 (help, docs, manifest). The pins are never typed twice here: every expectation about the current pins is read
from native_pins.py, and every expectation about the legacy pins is read from its legacy entries.

History stays readable and execution stays strict: nothing in this module touches the P3a frozen fixtures, and a
version-1 document or context is only ever read, labelled legacy_reproduction_only, never written back as version 2.
"""
import copy
import datetime as dt
import json
import unittest
from unittest.mock import patch

from intune_iac import native_pins
from plugin_tests import test_target as base

CURRENT = 'current_local_qualification'
LEGACY = 'legacy_reproduction_only'


def _pin(pins, profile):
    (sha, entry), = [(sha, entry) for sha, entry in pins.items() if entry['profile'] == profile]
    return sha, entry['version']


CURRENT_TOFU_SHA, CURRENT_TOFU = _pin(native_pins.OPENTOFU_PINS, CURRENT)
CURRENT_ATMOS_SHA, CURRENT_ATMOS = _pin(native_pins.ATMOS_PINS, CURRENT)
LEGACY_TOFU_SHA, LEGACY_TOFU = _pin(native_pins.OPENTOFU_PINS, LEGACY)
LEGACY_ATMOS_SHA, LEGACY_ATMOS = _pin(native_pins.ATMOS_PINS, LEGACY)


def v2_descriptor():
    document = base.fixture()
    document['schema_version'] = 'target-evidence/2.0'
    toolchain = document['binding']['toolchain']
    toolchain.update(atmos_version=CURRENT_ATMOS, atmos_sha256=CURRENT_ATMOS_SHA,
                     engine_version=CURRENT_TOFU, engine_sha256=CURRENT_TOFU_SHA)
    return document


class TargetDescriptorV2Tests(unittest.TestCase):
    def setUp(self):
        from intune_iac import target
        self.target = target
        clock = patch('intune_iac.target._now', return_value=base.NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def test_a_v2_descriptor_with_the_current_pins_is_consistent_and_labelled_current(self):
        result = self.target.inspect_target(v2_descriptor())
        self.assertTrue(result['valid'], result['issues'])
        self.assertEqual(result['schema_version'], 'target-evidence/2.0')
        self.assertEqual(result['pin_profile'], CURRENT)
        self.assertFalse(result['execution_authorized'])

    def test_the_v2_toolchain_is_exactly_the_current_pins_from_native_pins(self):
        for field, wrong in (('atmos_version', LEGACY_ATMOS), ('engine_version', LEGACY_TOFU),
                             ('atmos_sha256', LEGACY_ATMOS_SHA), ('engine_sha256', LEGACY_TOFU_SHA),
                             ('atmos_sha256', 'b' * 64), ('engine_sha256', 'c' * 64)):
            with self.subTest(field=field, wrong=wrong):
                document = v2_descriptor()
                document['binding']['toolchain'][field] = wrong
                result = self.target.inspect_target(document)
                self.assertFalse(result['valid'])
                self.assertIn('/binding/toolchain/' + field, [issue['path'] for issue in result['issues']])

    def test_a_v1_descriptor_still_loads_and_says_it_is_for_reproduction_only(self):
        document = base.fixture()
        before = copy.deepcopy(document)
        result = self.target.inspect_target(document)
        self.assertTrue(result['valid'], result['issues'])
        self.assertEqual(result['schema_version'], 'target-evidence/1.0')
        self.assertEqual(result['pin_profile'], LEGACY)
        self.assertEqual(document, before)
        self.assertNotIn('target-evidence/2.0', json.dumps(result))

    def test_the_legacy_pins_are_the_legacy_entries_of_native_pins(self):
        toolchain = base.fixture()['binding']['toolchain']
        self.assertEqual((toolchain['atmos_version'], toolchain['engine_version']), (LEGACY_ATMOS, LEGACY_TOFU))

    def test_versions_do_not_mix(self):
        mixed = base.fixture()
        mixed['binding']['toolchain'].update(atmos_version=CURRENT_ATMOS, engine_version=CURRENT_TOFU)
        self.assertFalse(self.target.inspect_target(mixed)['valid'])
        relabelled = v2_descriptor()
        relabelled['schema_version'] = 'target-evidence/1.0'
        self.assertFalse(self.target.inspect_target(relabelled)['valid'])
        legacy_in_v2 = base.fixture()
        legacy_in_v2['schema_version'] = 'target-evidence/2.0'
        self.assertFalse(self.target.inspect_target(legacy_in_v2)['valid'])

    def test_an_unrecognised_version_is_invalid_and_has_no_profile(self):
        document = v2_descriptor()
        document['schema_version'] = 'target-evidence/3.0'
        result = self.target.inspect_target(document)
        self.assertFalse(result['valid'])
        self.assertIsNone(result['pin_profile'])
        self.assertIn('/schema_version', [issue['path'] for issue in result['issues']])

    def test_every_other_v2_field_is_still_checked(self):
        for path, old in base.leaves(v2_descriptor()):
            for null in (False, True):
                if null and old is None:
                    continue
                with self.subTest(path=path, null=null):
                    mutated = v2_descriptor()
                    parent = mutated
                    for key in path[:-1]:
                        parent = parent[key]
                    if null:
                        parent[path[-1]] = None
                    else:
                        del parent[path[-1]]
                    self.assertFalse(self.target.inspect_target(mutated)['valid'])

    def test_compare_labels_each_side_and_never_matches_across_versions(self):
        legacy = self.target.compare_targets(base.fixture(), base.fixture())
        self.assertEqual(legacy['status'], 'match')
        self.assertEqual((legacy['expected']['pin_profile'], legacy['observed']['pin_profile']), (LEGACY, LEGACY))
        current = self.target.compare_targets(v2_descriptor(), v2_descriptor())
        self.assertEqual(current['status'], 'match')
        self.assertEqual(current['expected']['pin_profile'], CURRENT)
        across = self.target.compare_targets(base.fixture(), v2_descriptor())
        self.assertEqual(across['status'], 'mismatch')
        self.assertIn({'path': '/schema_version', 'reason': 'changed'}, across['differences'])
        self.assertFalse(across['execution_authorized'])

    def test_reading_a_v1_descriptor_through_the_cli_writes_nothing(self):
        import tempfile
        from pathlib import Path
        from intune_iac import cli
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'legacy.target.json'
            path.write_text(json.dumps(base.fixture(), sort_keys=True), encoding='utf-8')
            before = path.read_bytes()
            before_names = sorted(p.name for p in Path(temporary).iterdir())
            result = cli._target_command(type('Args', (), {'target_command': 'inspect', 'input': str(path)})())
            self.assertEqual(result['pin_profile'], LEGACY)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(sorted(p.name for p in Path(temporary).iterdir()), before_names)

    def test_the_native_context_report_carries_the_label(self):
        from intune_iac import native_context
        legacy = native_context.inspect_native_context(base.fixture())
        self.assertEqual(legacy['target']['pin_profile'], LEGACY)
        current = native_context.inspect_native_context(v2_descriptor())
        self.assertEqual(current['target']['pin_profile'], CURRENT)
        self.assertFalse(current['execution_authorized'])

    def test_an_invalid_document_reports_no_profile_and_no_values(self):
        for document in (None, [], {'schema_version': float('nan')}):
            result = self.target.inspect_target(document)
            self.assertFalse(result['valid'])
            self.assertIsNone(result['pin_profile'])


if __name__ == '__main__':
    unittest.main()
