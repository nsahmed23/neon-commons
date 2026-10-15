"""start examines the directory it is pointed at, not only the directories below it.

Directories are built with the product's own routes (the entry tests' builder) in temporary
directories; the command line is called as a function.
"""
import tempfile
import unittest
from pathlib import Path

from plugin_tests.test_start_goal import Fixtures, goal_block, needed_rows, run_cli


class StartRootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = Fixtures.get()['full']

    def survey(self, path):
        from intune_iac.entry import survey
        return survey(path)

    def kinds(self, value):
        return {(item['kind'], item['path']) for item in value['items']}

    def test_a_repository_at_the_root_of_the_surveyed_directory_is_found(self):
        value = self.survey(self.work / 'repository')
        self.assertIn(('repository', '.'), self.kinds(value))
        item = next(i for i in value['items'] if i['kind'] == 'repository')
        self.assertEqual(item['git_revision'], 'a' * 40)
        self.assertTrue(item['states']['configured'])
        code, text = run_cli(str(self.work / 'repository'))
        self.assertEqual(code, 0)
        self.assertNotIn('Nothing recognized here yet.', text)
        self.assertIn('Repository', text)

    def test_the_goal_block_sees_a_repository_at_the_root(self):
        code, text = run_cli(str(self.work / 'repository'), '--goal', 'adopt')
        _, block = goal_block(text)
        rows = dict(needed_rows(block))
        self.assertEqual(rows['Repository'], 'ready')
        self.assertNotIn('No Atmos repository (atmos.yaml) was found under the surveyed directory', '\n'.join(block))

    def test_a_store_at_the_root_and_a_service_at_the_root_are_found(self):
        self.assertIn(('store', '.'), self.kinds(self.survey(self.work / 'store')))
        self.assertIn(('modeled_service', '.'), self.kinds(self.survey(self.work / 'service')))

    def test_an_operation_and_a_generated_project_at_the_root_are_found(self):
        with tempfile.TemporaryDirectory() as temp:
            operation = Path(temp) / 'op'
            operation.mkdir()
            (operation / 'plan.json').write_text('{}')
            (operation / 'journal.json').write_text('{}')
            self.assertIn(('operation', '.'), self.kinds(self.survey(operation)))
            generated = Path(temp) / 'gen'
            generated.mkdir()
            (generated / 'generated-files.json').write_text('{}')
            self.assertIn(('generated_project', '.'), self.kinds(self.survey(generated)))

    def test_the_parent_still_finds_the_same_repository_and_store(self):
        found = self.kinds(self.survey(self.work))
        self.assertIn(('repository', 'repository'), found)
        self.assertIn(('store', 'store'), found)
        self.assertNotIn(('repository', '.'), found)
        self.assertNotIn(('store', '.'), found)

    def test_a_directory_with_nothing_recognizable_is_still_empty(self):
        code, text = run_cli(str(Fixtures.get()['offline']))
        self.assertIn('Nothing recognized here yet.', text)


def tearDownModule():
    Fixtures.release()


if __name__ == '__main__':
    unittest.main()
