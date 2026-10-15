"""P3b item 5: the adoption policy across an upgrade (workbench_adoption.py).

A new or incomplete adoption of a journey whose relation to the current implementation is not same is refused by name
before anything is created; an existing complete handoff verifies as history with its binding, artefacts and collections
unchanged and the relation in the returned metadata only; a journey recorded under the current implementation adopts as
before. The upgraded copy and the frozen journey are those of test_pin_history_p3b.
"""
import json
import unittest

from plugin_tests import test_pre_pin_migration as frozen
from plugin_tests import test_workbench_adoption as adoption_base
from plugin_tests.test_pin_history_p3b import UNKNOWN_DIGEST, UpgradedFrozenCase, tree
from intune_iac.io import canonical


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


if __name__ == '__main__':
    unittest.main()
