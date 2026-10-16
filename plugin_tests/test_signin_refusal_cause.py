"""PKG-SETUP-5E item 2: the refusal of an output folder names the condition the check actually found."""
import contextlib
import errno
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

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



def _symlink_cause():
    """What the open of a symlinked ancestor returns on this host: ELOOP names a link, ENOTDIR is neutral."""
    with tempfile.TemporaryDirectory() as scratch:
        path = symlinked_ancestor(scratch)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            os.close(os.open(str(Path(path).parent), flags))
        except OSError as error:
            return 'ancestor_symlink' if error.errno == errno.ELOOP else 'ancestor_not_real_directory'
    raise AssertionError('the open of a symlinked ancestor succeeded')


SYMLINK_CAUSE = _symlink_cause()


def fake_stat(kind):
    """An os.stat that reports every name as the given file type: a later lookup that disagrees with the failing call."""
    def stat_(name, *args, **kw):
        return os.stat_result((kind | 0o600, 1, 1, 1, 0, 0, 0, 0, 0, 0))
    return stat_


class OperationCauseTests(unittest.TestCase):
    """The cause is classified at the operation that failed: an ancestor open, the final mkdir, or a step after mkdir made it."""

    def run_with(self, patch_target, error, after_mkdir=False):
        with tempfile.TemporaryDirectory() as scratch:
            made = []
            real_mkdir, real_open = os.mkdir, os.open

            def mkdir(*args, **kw):
                real_mkdir(*args, **kw)
                made.append(True)

            def open_(*args, **kw):
                if made and patch_target == 'open':
                    raise error
                return real_open(*args, **kw)
            patches = [mock.patch.object(os, 'mkdir', mkdir)]
            if patch_target == 'open':
                patches.append(mock.patch.object(os, 'open', open_))
            elif patch_target in ('fchmod', 'fsync'):
                patches.append(mock.patch.object(os, patch_target, side_effect=error))
            elif patch_target == 'mkdir':
                patches = [mock.patch.object(os, 'mkdir', side_effect=error)]
            with contextlib.ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)
                with self.assertRaises(AppError) as caught:
                    capture._new_directory(str(Path(scratch) / 'new'))
            return caught.exception

    def test_a_missing_final_component_after_mkdir_is_not_a_missing_ancestor(self):
        error = self.run_with('open', OSError(errno.ENOENT, 'gone'))
        self.assertEqual(getattr(error, 'cause', None), 'created_then_failed')
        self.assertEqual(getattr(error, 'cause_errno', None), 'ENOENT')

    def test_a_failure_of_fchmod_or_fsync_after_mkdir_is_the_same_cause(self):
        for target in ('fchmod', 'fsync'):
            error = self.run_with(target, OSError(errno.EIO, 'io'))
            self.assertEqual(getattr(error, 'cause', None), 'created_then_failed', target)
            self.assertEqual(getattr(error, 'cause_errno', None), 'EIO', target)

    def test_the_sentence_says_the_folder_may_have_been_created_and_is_not_used(self):
        from intune_iac.signin_facts import _refusal_why
        why = flat(_refusal_why({'cause': 'created_then_failed', 'cause_errno': 'ENOENT'}))
        self.assertIn('may have been created', why)
        self.assertIn('not used', why)
        self.assertNotIn('does not exist', why)
        self.assertNotIn('nothing was written', why)

    def test_the_final_mkdir_has_its_own_causes(self):
        for error, cause in ((FileExistsError(errno.EEXIST, 'x'), 'exists'),
                             (PermissionError(errno.EACCES, 'x'), 'parent_not_writable'),
                             (OSError(errno.ENAMETOOLONG, 'x'), 'name_too_long'),
                             (OSError(errno.ENOENT, 'x'), 'unchecked')):
            self.assertEqual(getattr(self.run_with('mkdir', error), 'cause', None), cause, error)

    def test_an_ancestor_open_still_reports_a_missing_ancestor(self):
        with tempfile.TemporaryDirectory() as scratch:
            with self.assertRaises(AppError) as caught:
                capture._new_directory(str(Path(scratch) / 'missing' / 'new'))
        self.assertEqual(getattr(caught.exception, 'cause', None), 'ancestor_missing')


class NamedCauseTests(unittest.TestCase):
    def test_the_cause_does_not_follow_a_later_lookup_of_the_same_name(self):
        def plain_file(scratch):
            (Path(scratch) / 'plain').write_text('x')
            return str(Path(scratch) / 'plain' / 'new')
        for path_of in (plain_file, symlinked_ancestor):
            for kind in (stat.S_IFLNK, stat.S_IFREG, stat.S_IFDIR):
                causes = []
                for patched in (False, True):
                    with tempfile.TemporaryDirectory() as scratch:
                        path = path_of(scratch)
                        with mock.patch.object(os, 'stat', fake_stat(kind)) if patched else mock.patch.object(os, 'getpid'):
                            with self.assertRaises(AppError) as caught:
                                capture._new_directory(path)
                        causes.append(getattr(caught.exception, 'cause', None))
                self.assertEqual(causes[0], causes[1], (path_of.__name__, kind, causes))

    def test_a_plain_file_is_never_called_a_symbolic_link_by_the_cause(self):
        with tempfile.TemporaryDirectory() as scratch:
            (Path(scratch) / 'plain').write_text('x')
            with mock.patch.object(os, 'stat', fake_stat(stat.S_IFLNK)):
                with self.assertRaises(AppError) as caught:
                    signin.check_new_output(str(Path(scratch) / 'plain' / 'new'))
            self.assertNotEqual(getattr(caught.exception, 'cause', None), 'ancestor_symlink')


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
        # which sentence depends on the errno the open returned (ELOOP names a link; ENOTDIR does not); never on a later lookup
        self.assertTrue('symbolic link' in why or 'could not be opened as a real folder' in why, why)
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
        self.assertIn('could not be opened as a real folder', why)
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
        self.check_cause(symlinked_ancestor, SYMLINK_CAUSE)
        self.check_cause(long_name, 'name_too_long')
        self.check_cause(lambda scratch: str(Path(scratch) / 'missing' / 'new'), 'ancestor_missing')

    def test_the_capture_command_records_the_cause_it_found(self):
        for path_of, cause in ((existing_folder, 'exists'), (symlinked_ancestor, SYMLINK_CAUSE),
                               (long_name, 'name_too_long')):
            with tempfile.TemporaryDirectory() as scratch:
                with self.assertRaises(AppError) as caught:
                    capture._new_directory(path_of(scratch))
                self.assertEqual(caught.exception.code, 'capture_output_conflict')
                self.assertEqual(getattr(caught.exception, 'cause', None), cause)


if __name__ == '__main__':
    unittest.main()
