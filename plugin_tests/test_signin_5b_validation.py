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
