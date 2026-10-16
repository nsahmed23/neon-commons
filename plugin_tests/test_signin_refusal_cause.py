"""PKG-SETUP-5E item 2: the refusal of an output folder names the condition the check actually found."""
import os
from pathlib import Path
import tempfile
import unittest

from intune_iac import capture, signin
from intune_iac.io import AppError
from plugin_tests.signin_fakes import TENANT_A
from plugin_tests.signin_golden_cases import POLICY
from plugin_tests.test_signin_collect_readable import rows, run_text
from plugin_tests.test_signin_golden import run_case_full

GENERIC = ('Capture requires a new directory with no symlinked ancestors; existing files are preserved. '
           'Name a folder that does not exist yet.')
NOT_SHOWN = '<the output path is not shown>'


def flat(text):
    return ' '.join(text.split())


def refusal(path_of, **kw):
    return run_text('collect_ok', output=path_of, **kw)


def symlinked_ancestor(scratch):
    real = Path(scratch) / 'real'
    real.mkdir()
    (Path(scratch) / 'link').symlink_to(real, target_is_directory=True)
    return str(Path(scratch) / 'link' / 'new-output')


def existing_folder(scratch):
    path = Path(scratch) / 'taken'
    path.mkdir()
    return str(path)


def long_name(scratch):
    return str(Path(scratch) / ('n' * 300))



class NamedCauseTests(unittest.TestCase):
    def why(self, path_of):
        text = refusal(path_of)[1]
        lines = rows(text)
        if 'Why:' not in lines:
            return ''
        start = lines.index('Why:')
        block = []
        for line in lines[start + 1:]:
            if not line.startswith('    '):
                break
            block.append(line)
        return flat(' '.join(block))

    def test_an_existing_folder_says_it_exists_and_not_that_a_link_is_involved(self):
        why = self.why(existing_folder)
        self.assertIn('already exists', why)
        self.assertNotIn('symbolic link', why)
        self.assertNotIn('too long', why)

    def test_a_symlinked_ancestor_says_a_link_is_on_the_way(self):
        why = self.why(symlinked_ancestor)
        self.assertIn('symbolic link', why)
        self.assertNotIn('already exists', why)
        self.assertNotIn('too long', why)

    def test_a_name_too_long_says_so_and_does_not_blame_a_link_or_existing_files(self):
        why = self.why(long_name)
        self.assertIn('too long', why)
        self.assertNotIn('symbolic link', why)
        self.assertNotIn('already exists', why)

    def test_a_missing_ancestor_says_a_folder_on_the_way_does_not_exist(self):
        why = self.why(lambda scratch: str(Path(scratch) / 'missing' / 'new'))
        self.assertIn('does not exist', why)
        self.assertNotIn('symbolic link', why)

    def test_a_file_where_a_folder_must_be_says_it_is_not_a_folder(self):
        def path_of(scratch):
            (Path(scratch) / 'plain').write_text('x')
            return str(Path(scratch) / 'plain' / 'new')
        why = self.why(path_of)
        self.assertIn('is not a folder', why)
        self.assertNotIn('symbolic link', why)

    @unittest.skipIf(os.name != 'posix' or os.geteuid() == 0, 'needs a non-root POSIX user')
    def test_a_parent_that_cannot_be_written_says_so(self):
        def path_of(scratch):
            parent = Path(scratch) / 'locked'
            parent.mkdir()
            parent.chmod(0o500)
            return str(parent / 'new')
        why = self.why(path_of)
        self.assertIn('does not allow', why)
        self.assertNotIn('symbolic link', why)

    def check_cause(self, path_of, cause):
        with tempfile.TemporaryDirectory() as scratch:
            path = path_of(scratch)
            with self.assertRaises(AppError) as caught:
                signin.check_new_output(path)
            self.assertEqual(caught.exception.code, 'capture_output_conflict')
            self.assertEqual(getattr(caught.exception, 'cause', None), cause)
            self.assertEqual(caught.exception.message, GENERIC)  # the message and so the JSON stay as they were

    def test_the_preflight_records_the_cause_it_found(self):
        self.check_cause(existing_folder, 'exists')
        self.check_cause(symlinked_ancestor, 'ancestor_symlink')
        self.check_cause(long_name, 'name_too_long')
        self.check_cause(lambda scratch: str(Path(scratch) / 'missing' / 'new'), 'ancestor_missing')

    def test_the_capture_command_records_the_cause_it_found(self):
        for path_of, cause in ((existing_folder, 'exists'), (symlinked_ancestor, 'ancestor_symlink'),
                               (long_name, 'name_too_long')):
            with tempfile.TemporaryDirectory() as scratch:
                with self.assertRaises(AppError) as caught:
                    capture._new_directory(path_of(scratch))
                self.assertEqual(caught.exception.code, 'capture_output_conflict')
                self.assertEqual(getattr(caught.exception, 'cause', None), cause)


if __name__ == '__main__':
    unittest.main()
