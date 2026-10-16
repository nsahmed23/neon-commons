"""PKG-SETUP-5E item 3: the output path is printed through the shared path writer (quoted when needed, placeholder when refused)."""
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



class PathPrintingTests(unittest.TestCase):
    def test_a_path_with_spaces_is_quoted_once_so_it_can_be_copied(self):
        box = {}

        def path_of(scratch):
            box['path'] = str(Path(scratch) / 'my out folder')
            return box['path']
        text = run_text('collect_ok', output=path_of)[1]
        self.assertIn("Output folder: '%s' (not present after this run)" % box['path'], rows(text))

    def test_a_refused_folder_with_spaces_is_quoted_too(self):
        box = {}

        def path_of(scratch):
            path = Path(scratch) / 'taken folder'
            path.mkdir()
            box['path'] = str(path)
            return box['path']
        text = refusal(path_of)[1]
        self.assertIn("Output folder: '%s' (no collecting command started" % box['path'], flat(text))

    def test_an_ordinary_path_is_not_quoted(self):
        box = {}

        def path_of(scratch):
            box['path'] = str(Path(scratch) / 'plain-folder')
            return box['path']
        text = run_text('collect_ok', output=path_of)[1]
        self.assertIn('Output folder: %s (not present after this run)' % box['path'], rows(text))

    def test_a_token_shaped_name_still_shows_the_placeholder_on_the_refusal_screen(self):
        shaped = 'ghp_' + 'a1' * 18

        def path_of(scratch):
            path = Path(scratch) / shaped
            path.mkdir()
            return str(path)
        code, text, err = refusal(path_of)
        self.assertEqual(rows(text)[0], 'COLLECT: BLOCKED (capture_output_conflict)')
        self.assertNotIn(shaped, text + err)
        self.assertIn(NOT_SHOWN, flat(text))

    def test_a_control_character_name_is_a_placeholder_on_the_refusal_screen(self):
        def path_of(scratch):
            path = Path(scratch) / 'bad\x1b[2Jname'
            path.mkdir()
            return str(path)
        code, text, err = refusal(path_of)
        self.assertNotIn('\x1b', text)
        self.assertIn(NOT_SHOWN, flat(text))

    def test_a_name_too_long_to_display_is_a_placeholder_on_the_refusal_screen(self):
        text = refusal(long_name)[1]
        self.assertIn(NOT_SHOWN, flat(text))
        self.assertNotIn('n' * 100, text)


if __name__ == '__main__':
    unittest.main()
