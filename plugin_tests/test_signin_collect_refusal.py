"""PKG-SETUP-5E item 1: a refused output folder of `signin collect` is a readable COLLECT: BLOCKED screen in text mode; --json is unchanged."""
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



class ReadableRefusalTests(unittest.TestCase):
    def check_screen(self, path_of):
        code, text, err = refusal(path_of)
        self.assertEqual(rows(text)[0], 'COLLECT: BLOCKED (capture_output_conflict)')
        self.assertEqual(err, '')
        self.assertEqual(code, 4)
        words = flat(text)
        self.assertIn('no collecting command started, so nothing was written', words)
        self.assertIn('Collecting command: not started', rows(text))
        self.assertNotIn('{', text)
        return text

    def test_an_existing_folder_gets_the_readable_screen(self):
        self.check_screen(existing_folder)

    def test_a_symlinked_ancestor_gets_the_readable_screen(self):
        self.check_screen(symlinked_ancestor)

    def test_a_name_too_long_for_a_folder_gets_the_readable_screen(self):
        self.check_screen(long_name)

    def test_the_next_steps_are_numbered_and_the_command_is_complete(self):
        text = self.check_screen(existing_folder)
        lines = rows(text)
        start = lines.index('Next step:')
        block = []
        for line in lines[start + 1:]:
            if not line.strip():
                break
            block.append(line)
        self.assertTrue(block[0].startswith('    1. '), block)
        self.assertTrue(any(line.startswith('    2. ') for line in block), block)
        words = flat(' '.join(block))
        # The command is said in words (readiness.placeholders_in_words): the resolved operands keep their option and
        # value, the unresolved one is described, and no NEW_DIR stand-in is printed.
        self.assertIn('the signin collect command using --tenant %s, --policy %s, naming --output as a new folder for the output'
                      % (TENANT_A, POLICY), words)
        self.assertNotIn('NEW_DIR', words)

    def test_the_last_line_is_the_exit_code_row_and_explains_exit_4(self):
        for path_of in (existing_folder, symlinked_ancestor, long_name):
            text = refusal(path_of)[1]
            last = text.rstrip('\n').split('\n\n')[-1]  # the exit-code row may wrap; it is the last block
            self.assertTrue(last.startswith('Exit code 4:'), last)
            self.assertIn('4 means', flat(text.partition('Exit code 4:')[2]))

    def test_the_exit_code_legend_covers_the_status_actually_returned_for_every_collect_screen(self):
        for name, code in (('collect_ok', 0), ('collect_partial_expired', 2), ('collect_child_fails', 3)):
            text = run_text(name)[1]
            self.assertIn('Exit code %d:' % code, text)
            self.assertIn('4 means', flat(text.partition('Exit code %d:' % code)[2]), name)

    def test_the_json_form_is_unchanged(self):
        code, out, err = run_case_full('collect_output_exists', json_flag=True)
        self.assertEqual((code, out), (4, ''))
        import json
        self.assertEqual(json.loads(err), {'status': 'error', 'error': {'code': 'capture_output_conflict', 'message': GENERIC}})


if __name__ == '__main__':
    unittest.main()
