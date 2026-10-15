"""P3b item 5: the adoption policy across an upgrade (workbench_adoption.py).

A new or incomplete adoption of a journey whose relation to the current implementation is not same is refused by name
before anything is created; an existing complete handoff verifies as history with its binding, artefacts and collections
unchanged and the relation in the returned metadata only; a journey recorded under the current implementation adopts as
before. The upgraded copy and the frozen journey are those of test_pin_history_p3b.
"""
import json
import unittest
from unittest.mock import patch

from plugin_tests import test_pre_pin_migration as frozen
from plugin_tests import test_workbench_adoption as adoption_base
from plugin_tests.test_pin_history_p3b import UNKNOWN_DIGEST, UpgradedFrozenCase, tree
from intune_iac import implementation_history as history
from intune_iac import protected
from intune_iac import workbench_adoption as adoption
from intune_iac.io import AppError, canonical, digest, load_json, write_json


class FrozenPreviewTests(UpgradedFrozenCase):
    def test_preview_rebuilds_the_binding_and_says_the_journey_is_not_adoptable_as_new(self):
        journal = json.loads((self.handoff / 'adoption.json').read_text())
        result = self.copy.cli('workbench', 'adoption-preview', '--root', self.store, '--session', self.session)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        preview = json.loads(result.stdout)
        self.assertEqual(preview['binding_sha256'], journal['binding_sha256'])
        self.assertEqual(preview['implementation']['relation'], 'known_earlier')
        self.assertNotEqual(preview['status'], 'ready_local_model_handoff')
        self.assertFalse(preview['execution_authorized'])
        self.unchanged('journey/')


class AdoptionPolicyAcrossAnUpgradeTests(UpgradedFrozenCase):
    def adopt(self, output):
        return self.copy.cli('workbench', 'adopt', '--root', self.store, '--session', self.session, '--output', output)

    def test_new_adoption_after_the_change_is_refused_by_name_before_anything_is_created(self):
        new = frozen.FROZEN_ROOT / 'adoption/new-handoff'
        store_before = tree(self.store)
        result = self.adopt(new)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('workbench_adoption_implementation_not_current', result.stderr)
        self.assertIn('known_earlier', result.stderr)
        self.assertIn('again under the current implementation', result.stderr)
        self.assertFalse(new.exists())
        self.assertEqual(tree(self.store), store_before)
        self.unchanged('journey/')
        self.unchanged('adoption/handoff/')

    def test_an_incomplete_adoption_is_refused_the_same_way_and_left_as_it_was(self):
        partial = frozen.FROZEN_ROOT / 'adoption/partial'
        partial.mkdir(mode=0o700)
        journal = json.loads((self.handoff / 'adoption.json').read_text())
        journal.update(status='preparing', collection_run_id=None, artifact_ids={})
        (partial / 'adoption.json').write_bytes(canonical(journal))
        before = tree(partial)
        result = self.adopt(partial)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('workbench_adoption_implementation_not_current', result.stderr)
        self.assertEqual(tree(partial), before)

    def test_an_unrecognised_implementation_is_refused_for_new_adoption_too(self):
        self.copy.run('forge', self.session, UNKNOWN_DIGEST)
        new = frozen.FROZEN_ROOT / 'adoption/new-handoff'
        result = self.adopt(new)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(new.exists())


class AdoptionWithoutAChangeStillWorksTests(unittest.TestCase):
    """A journey completed and adopted under the same implementation: relation same, nothing refused."""
    setUp = adoption_base.WorkbenchAdoptionTests.setUp
    process = adoption_base.WorkbenchAdoptionTests.process
    call = adoption_base.WorkbenchAdoptionTests.call
    complete = adoption_base.WorkbenchAdoptionTests.complete
    adopt = adoption_base.WorkbenchAdoptionTests.adopt

    def test_preview_adopt_and_repeat_adopt_report_same(self):
        self.complete()
        preview = self.call('adoption-preview', '--root', self.store_root, '--session', self.session)
        self.assertEqual(preview['status'], 'ready_local_model_handoff')
        self.assertEqual(preview['implementation']['relation'], 'same')
        first = self.adopt()
        self.assertEqual(first['status'], 'adopted_local_model')
        self.assertEqual(first['implementation']['relation'], 'same')
        self.assertEqual(first['implementation']['recorded_implementation_sha256'],
                         first['implementation']['current_implementation_sha256'])
        journal = json.loads((self.handoff / 'adoption.json').read_text())
        second = self.adopt()
        self.assertEqual(second['binding_sha256'], first['binding_sha256'])
        self.assertEqual(json.loads((self.handoff / 'adoption.json').read_text()), journal)
        self.assertNotIn('implementation', journal['binding'])
        self.assertNotIn('implementation', journal)


class HistoricalAdoptionRaceTests(unittest.TestCase):
    """The completeness that selects the policy must also control the mutation (review F1)."""
    setUp = adoption_base.WorkbenchAdoptionTests.setUp
    process = adoption_base.WorkbenchAdoptionTests.process
    complete = adoption_base.WorkbenchAdoptionTests.complete

    def partial_handoff(self):
        preview = adoption.preview(self.store, self.session)
        partial = self.root / 'partial handoff'
        partial.mkdir(mode=0o700)
        binding = preview['binding']
        write_json(partial / 'adoption.json', {
            'schema_version': adoption.VERSION, 'store_root': str(self.store.root), 'handoff_root': str(partial),
            'binding': binding, 'binding_sha256': digest(binding), 'status': 'preparing',
            'collection_run_id': None, 'artifact_ids': {}})
        return partial

    def upgrade(self):
        recorded_files = protected._implementation_files()
        inventory = history.PROTECTED_INVENTORY + ({'label': 'test-release', 'files': recorded_files,
                                                    'implementation_sha256': history.protected_digest(recorded_files)},)
        return (patch.object(history, 'PROTECTED_INVENTORY', inventory),
                patch.object(protected, '_implementation_files', return_value=dict(recorded_files, **{'io.py': 'c' * 64})))

    def test_incomplete_historical_adoption_cannot_borrow_a_complete_classification(self):
        self.complete()
        partial = self.partial_handoff()
        checkpoint = partial / 'adoption.json'
        real_complete = adoption._complete_handoff

        def flip_status(output):
            value = load_json(checkpoint)
            value['status'] = 'complete'
            write_json(checkpoint, value)
            self.assertTrue(real_complete(output))
            value['status'] = 'preparing'
            write_json(checkpoint, value)
            return True

        recognised, changed = self.upgrade()
        with recognised, changed, patch.object(adoption, '_complete_handoff', side_effect=flip_status):
            with self.assertRaises(AppError) as raised:
                adoption.adopt(self.store, self.session, partial)
        self.assertEqual(raised.exception.code, 'workbench_adoption_implementation_not_current')
        self.assertFalse((partial / 'service').exists(), 'a model was created from a historical journey')
        self.assertEqual(load_json(checkpoint)['status'], 'preparing')

    def test_a_handoff_directory_removed_after_the_classification_is_not_created_for_a_historical_journey(self):
        self.complete()
        partial = self.partial_handoff()
        real_complete = adoption._complete_handoff

        def remove_after_reading(output):
            answer = real_complete(output)
            (partial / 'adoption.json').unlink()
            partial.rmdir()
            return True

        recognised, changed = self.upgrade()
        with recognised, changed, patch.object(adoption, '_complete_handoff', side_effect=remove_after_reading):
            with self.assertRaises(AppError) as raised:
                adoption.adopt(self.store, self.session, partial)
        self.assertEqual(raised.exception.code, 'workbench_adoption_implementation_not_current')
        self.assertFalse(partial.exists())


if __name__ == '__main__':
    unittest.main()
