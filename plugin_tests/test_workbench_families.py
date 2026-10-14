"""Families: every policy, application and script family with its actual support disposition."""
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FamiliesTests(unittest.TestCase):
    def test_every_family_in_the_coverage_table_is_shown_with_its_stage_and_workbench_presence(self):
        from intune_iac.families import families
        value = families()
        self.assertEqual(value['schema_version'], 'workbench-families/1')
        self.assertTrue(value['available'])
        self.assertEqual(value['source']['path'], 'family-coverage.csv')
        rows = {row['family']: row for row in value['families']}
        self.assertEqual(len(rows), 9)
        catalog = rows['Windows plain Settings Catalog']
        self.assertEqual(catalog['stage'], 'offline reference')
        self.assertIn('estate', catalog['workbench'])
        self.assertIn('Relationships', rows['Groups, filters, scope tags']['workbench'])
        self.assertEqual(rows['Win32 apps']['workbench'], 'not in the estate')
        self.assertEqual(rows['Autopilot/enrollment']['stage'], 'later')
        self.assertEqual(rows['Autopilot/enrollment']['material'], 'explicit exclusion from first slice')
        self.assertFalse(value['execution_authorized'])

    def test_a_runtime_without_the_table_says_so(self):
        from intune_iac.families import families
        with tempfile.TemporaryDirectory() as temp:
            value = families(temp)
        self.assertEqual((value['available'], value['reason']), (False, 'family_coverage_not_packaged'))
        self.assertEqual(value['families'], [])

    def test_the_screen_lists_each_family_and_fits(self):
        from intune_iac.families import families
        from intune_iac.workbench_screens import families_lines
        from intune_iac.workbench_tui import cell_width
        lines = families_lines(families(), 100)
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], '[POLICY FAMILIES]')
        self.assertIn('Windows plain Settings Catalog', joined)
        self.assertIn('Win32 apps', joined)
        self.assertIn('not in the estate', joined)
        for line in lines:
            self.assertLessEqual(cell_width(line), 100, line)


if __name__ == '__main__':
    unittest.main()
