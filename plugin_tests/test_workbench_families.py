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

    HEADER = 'family,candidate,material,release_stage,qualification_needed,live\n'

    def read(self, text, bom=False):
        from intune_iac.families import families
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'family-coverage.csv').write_bytes((b'\xef\xbb\xbf' if bom else b'') + text.encode('utf-8'))
            return families(temp)

    def test_a_byte_order_mark_is_accepted(self):
        value = self.read(self.HEADER + 'Win32 apps,route,material,review only,qualification,not_run\n', bom=True)
        self.assertTrue(value['available'])
        self.assertEqual(value['families'][0]['family'], 'Win32 apps')

    def test_a_missing_column_is_reported_instead_of_failing(self):
        value = self.read('family,candidate,material,release_stage,qualification_needed\nWin32 apps,r,m,s,q\n')
        self.assertEqual((value['available'], value['reason']), (False, 'family_coverage_malformed'))
        self.assertIn('live', value['detail'])
        self.assertEqual(value['families'], [])

    def test_a_short_or_long_row_is_reported(self):
        for row in ('Win32 apps,r,m,s,q\n', 'Win32 apps,r,m,s,q,l,extra\n'):
            value = self.read(self.HEADER + row)
            self.assertEqual(value['reason'], 'family_coverage_malformed', row)
            self.assertIn('row 2', value['detail'])

    def test_extra_columns_are_kept_with_each_family(self):
        value = self.read('family,candidate,material,release_stage,qualification_needed,live,owner\nWin32 apps,r,m,s,q,l,platform team\n')
        self.assertEqual(value['families'][0]['other_columns'], {'owner': 'platform team'})

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
