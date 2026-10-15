"""The inventory of released implementation digests (intune_iac/implementation_history.py).

The table is append-only and consulted only when a record is read as history. These tests pin every entry so that it
cannot change silently, tie the first entry to the digest the P3a fixtures froze (read from the frozen files, never
computed from current code), and check the three relations.
"""
import json
import unittest
from pathlib import Path

from intune_iac import implementation_history as history
from intune_iac.io import digest

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'pre_pin_migration'
JOURNEY = FIXTURES / 'journey/session.json.journey'
OPERATION = 'operations/d65bd73123014765922143bd45956e76/00.json'

FROZEN_DIGEST = 'c3ebd0c1c769e4d500406abb9b5b8ba716cea6f6da7108b8fec901daa875dc9c'
FROZEN_PROTECTED_FILES = {
    'protected.py': '79e167f7f4fdb1246f07a2589256890552b07480fba5bedce28f7c9f64dc1c43',
    'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
}
FROZEN_ATMOS_FILES = {
    'journey_native_atmos.py': 'f07515ca633659dc94cee515829cb71e3f5ffee27120ca9b527bfefa6d21bbe9',
    'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
    'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
    'protected.py': '79e167f7f4fdb1246f07a2589256890552b07480fba5bedce28f7c9f64dc1c43',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
}
LABEL = 'ce27913-pre-pin-migration'


def frozen_digests():
    """Every implementation digest the P3a fixtures recorded, read from the frozen files."""
    found = set()
    for name in ('native-request.json', 'synthetic-executor/preparation.json', OPERATION):
        document = json.loads((JOURNEY / name).read_text())
        request = document['payload']['request'] if name == OPERATION else document
        found.add(request['bindings']['implementation_sha256'])
    return found


class InventoryPinTests(unittest.TestCase):
    """Appending an entry is a deliberate release act that updates these literals; nothing else may change."""

    def test_protected_inventory_holds_exactly_the_pinned_entries(self):
        self.assertEqual(
            [dict(entry) for entry in history.PROTECTED_INVENTORY],
            [{'label': LABEL, 'implementation_sha256': FROZEN_DIGEST, 'files': FROZEN_PROTECTED_FILES}])

    def test_native_atmos_inventory_holds_exactly_the_pinned_entries(self):
        self.assertEqual(
            [dict(entry) for entry in history.NATIVE_ATMOS_INVENTORY],
            [{'label': LABEL, 'files': FROZEN_ATMOS_FILES}])

    def test_component_sets_are_the_bound_file_sets(self):
        self.assertEqual(history.PROTECTED_COMPONENTS, ('protected.py', 'execution.py', 'io.py', 'native_pins.py'))
        self.assertEqual(history.NATIVE_ATMOS_COMPONENTS, ('journey_native_atmos.py', 'native_atmos.py', 'repository.py',
                                                          'protected.py', 'io.py', 'native_pins.py'))

    def test_each_protected_entry_digest_is_the_digest_of_its_listed_files(self):
        for entry in history.PROTECTED_INVENTORY:
            self.assertEqual(set(entry['files']), set(history.PROTECTED_COMPONENTS), entry['label'])
            self.assertEqual(history.protected_digest(entry['files']), entry['implementation_sha256'], entry['label'])

    def test_labels_and_digests_are_unique(self):
        for inventory in (history.PROTECTED_INVENTORY, history.NATIVE_ATMOS_INVENTORY):
            labels = [entry['label'] for entry in inventory]
            self.assertEqual(len(labels), len(set(labels)))
        digests = [entry['implementation_sha256'] for entry in history.PROTECTED_INVENTORY]
        self.assertEqual(len(digests), len(set(digests)))


class FrozenDigestTests(unittest.TestCase):
    def test_the_fixtures_record_exactly_one_digest_and_it_is_the_first_entry(self):
        found = frozen_digests()
        # Not vacuous: the files were read and held a digest, and it is the pinned one.
        self.assertEqual(found, {FROZEN_DIGEST})
        self.assertEqual(history.PROTECTED_INVENTORY[0]['implementation_sha256'], next(iter(found)))

    def test_lookup_finds_the_frozen_digest_as_known_earlier(self):
        found = frozen_digests()
        self.assertTrue(found)
        for recorded in found:
            result = history.protected_relation(recorded, '0' * 64)
            self.assertEqual(result['relation'], 'known_earlier')
            self.assertEqual(result['inventory_label'], LABEL)
            self.assertEqual(result['recorded_implementation_sha256'], recorded)


class RelationTests(unittest.TestCase):
    def test_same_when_the_record_names_the_current_digest(self):
        result = history.protected_relation('a' * 64, 'a' * 64)
        self.assertEqual((result['relation'], result['inventory_label']), ('same', None))

    def test_same_takes_precedence_over_the_table(self):
        result = history.protected_relation(FROZEN_DIGEST, FROZEN_DIGEST)
        self.assertEqual(result['relation'], 'same')

    def test_unknown_when_neither_current_nor_in_the_table(self):
        result = history.protected_relation('b' * 64, 'a' * 64)
        self.assertEqual((result['relation'], result['inventory_label']), ('unknown', None))

    def test_result_names_both_digests_the_bound_components_and_the_claim(self):
        result = history.protected_relation(FROZEN_DIGEST, 'a' * 64)
        self.assertEqual(result['inventory'], 'protected_operation')
        self.assertEqual(result['current_implementation_sha256'], 'a' * 64)
        self.assertEqual(result['bound_components'], list(history.PROTECTED_COMPONENTS))
        self.assertIn('claim', result['recorded_implementation_basis'])
        self.assertIn('not authentication', result['recognition_limit'])

    def test_malformed_digest_is_unknown_never_an_error_or_a_match(self):
        for value in (None, 7, '', 'A' * 64, FROZEN_DIGEST[:-1], [FROZEN_DIGEST]):
            self.assertEqual(history.protected_relation(value, 'a' * 64)['relation'], 'unknown', value)

    def test_native_atmos_same_known_earlier_and_unknown(self):
        current = dict(FROZEN_ATMOS_FILES, **{'io.py': 'c' * 64})
        self.assertEqual(history.native_atmos_relation(current, current)['relation'], 'same')
        earlier = history.native_atmos_relation(FROZEN_ATMOS_FILES, current)
        self.assertEqual((earlier['relation'], earlier['inventory_label']), ('known_earlier', LABEL))
        self.assertEqual(earlier['recorded_implementation_sha256'], digest(FROZEN_ATMOS_FILES))
        self.assertEqual(earlier['bound_components'], list(history.NATIVE_ATMOS_COMPONENTS))
        altered = dict(FROZEN_ATMOS_FILES, **{'io.py': 'd' * 64})
        self.assertEqual(history.native_atmos_relation(altered, current)['relation'], 'unknown')

    def test_native_atmos_malformed_inventory_is_unknown(self):
        current = dict(FROZEN_ATMOS_FILES, **{'io.py': 'c' * 64})
        for value in (None, [], {}, dict(FROZEN_ATMOS_FILES, extra='e' * 64),
                      {k: v for k, v in FROZEN_ATMOS_FILES.items() if k != 'io.py'}):
            self.assertEqual(history.native_atmos_relation(value, current)['relation'], 'unknown', value)


if __name__ == '__main__':
    unittest.main()
