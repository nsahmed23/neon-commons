"""PKG-SETUP-5B items 6 and 7 (findings 23 and 24): validate before minting a token; start --check-signin off POSIX.
"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from intune_iac import cli, signin, signin_facts
from intune_iac.io import AppError
from plugin_tests.signin_5b_common import Base, NIL, RealCaptureBase, jwt
from plugin_tests.signin_fakes import TENANT_A, TENANT_B, azure_account, azure_list
from plugin_tests.test_signin_fix1 import LISTING, POLICY, token_answer


class EarlyValidationTests(Base):  # items 23 and 24
    def test_a_nil_policy_is_refused_before_any_az_call(self):
        with self.assertRaises(AppError) as caught:
            signin.collect(TENANT_A, NIL, self.output, deadline=5)
        self.assertEqual(caught.exception.code, 'capture_identity_invalid')
        self.assertEqual(self.fakes.calls(), [])

    def test_a_nil_tenant_is_refused_too(self):
        with self.assertRaises(AppError) as caught:
            signin.collect(NIL, POLICY, self.output, deadline=5)
        self.assertEqual(caught.exception.code, 'capture_identity_invalid')
        self.assertEqual(self.fakes.calls(), [])

    def test_an_existing_output_path_is_refused_before_any_token_is_minted(self):
        for make in (lambda p: Path(p).mkdir(), lambda p: Path(p).write_text('x'), lambda p: Path(p).symlink_to('/')):
            path = Path(self.output)
            if path.is_symlink() or path.exists():
                path.unlink() if not path.is_dir() else path.rmdir()
            make(self.output)
            with self.assertRaises(AppError) as caught:
                signin.collect(TENANT_A, POLICY, self.output, deadline=5)
            self.assertEqual(caught.exception.code, 'capture_output_conflict')
            self.assertEqual(self.fakes.calls(), [])
            self.assertEqual(self.collectors(), [])

    def test_a_new_output_under_a_symlinked_ancestor_is_refused_before_any_token(self):
        real = Path(self.box) / 'real'
        real.mkdir()
        link = Path(self.box) / 'link'
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(AppError) as caught:
            signin.collect(TENANT_A, POLICY, str(link / 'new-output'), deadline=5)
        self.assertEqual(caught.exception.code, 'capture_output_conflict')
        self.assertEqual(self.fakes.calls(), [])
        self.assertEqual(list(real.iterdir()), [])  # the check created nothing

    def test_a_missing_ancestor_and_dot_segments_are_refused_and_nothing_is_created(self):
        for path, code in ((str(Path(self.box) / 'missing' / 'new'), 'capture_output_conflict'),
                           (str(Path(self.box) / 'a' / '..' / 'new'), 'capture_output_unsafe')):
            with self.assertRaises(AppError) as caught:
                signin.collect(TENANT_A, POLICY, path, deadline=5)
            self.assertEqual(caught.exception.code, code, path)
        self.assertEqual(self.fakes.calls(), [])
        self.assertFalse((Path(self.box) / 'missing').exists())

    def test_a_good_new_output_is_accepted_and_not_created_by_the_check(self):
        signin.check_new_output(str(Path(self.box) / 'fresh'))
        self.assertFalse((Path(self.box) / 'fresh').exists())

    # PKG-SETUP-5B round 3 ---------------------------------------------------------------------------------------------------

    def test_a_host_without_the_primitives_is_refused_before_any_token_never_silently_accepted(self):
        with patch('intune_iac.signin._output_check_supported', return_value=False):
            with self.assertRaises(AppError) as caught:
                signin.collect(TENANT_A, POLICY, str(Path(self.box) / 'new'), deadline=5)
        # the same code and exit status the capture command itself uses for an unsupported platform
        self.assertEqual(caught.exception.code, 'capture_platform_unavailable')
        self.assertEqual(self.fakes.calls(), [])
        self.assertEqual(self.collectors(), [])

    def test_a_stable_non_writable_parent_is_refused_before_any_token(self):
        import os
        if os.geteuid() == 0:
            self.skipTest('root can write anywhere; the probe cannot refuse')
        parent = Path(self.box) / 'readonly'
        parent.mkdir()
        parent.chmod(0o500)
        self.addCleanup(parent.chmod, 0o700)
        with self.assertRaises(AppError) as caught:
            signin.collect(TENANT_A, POLICY, str(parent / 'new'), deadline=5)
        self.assertEqual(caught.exception.code, 'capture_output_conflict')
        self.assertEqual(self.fakes.calls(), [])
        self.assertEqual(list(parent.iterdir()), [])

    def test_a_writable_parent_is_still_accepted(self):
        signin.check_new_output(str(Path(self.box) / 'fresh-writable'))

    def test_the_documented_race_limit_is_stated_in_the_module(self):
        self.assertIn('between the preflight and the child', signin.check_new_output.__doc__)
        self.assertIn('never exposed', signin.check_new_output.__doc__)

    def test_literal_dot_segments_are_unsafe_in_both_validators_before_any_normalisation(self):
        from intune_iac import capture
        existing = Path(self.box) / 'existing'
        existing.mkdir()
        for path in ('.', '%s/./new' % existing, '%s/a/../b' % existing, './new', '%s/.' % existing):
            for name, check in (('signin.check_new_output', signin.check_new_output), ('capture._new_directory', capture._new_directory)):
                with self.assertRaises(AppError) as caught:
                    check(path)
                self.assertEqual(caught.exception.code, 'capture_output_unsafe', (name, path))
        self.assertEqual(list(existing.iterdir()), [])  # neither validator created anything

    def test_one_shared_helper_does_the_dot_segment_check(self):
        from intune_iac import capture
        self.assertTrue(callable(capture.reject_dot_segments))
        capture.reject_dot_segments('/a/b/c')
        capture.reject_dot_segments('relative/new')
        for bad in ('.', '..', 'a/./b', 'a/../b', '/a/.', '/..'):
            with self.assertRaises(AppError):
                capture.reject_dot_segments(bad)

    def test_start_check_signin_off_posix_is_the_designed_refusal(self):
        args = argparse.Namespace(check_signin='azure', goal='discover')
        with patch('intune_iac.signin.detect', side_effect=AttributeError('killpg')) as detect, \
                patch('intune_iac.cli.os.name', 'nt'):
            with self.assertRaises(AppError) as caught:
                cli._start_signin(args)
        self.assertEqual(caught.exception.code, 'identity_fd_platform_unsupported')
        detect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
