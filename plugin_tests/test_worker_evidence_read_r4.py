"""Actual private file mutations; failed candidates and originals remain local."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from intune_iac import worker_evidence_posix as host
from intune_iac.io import AppError
class PrivateReadTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name);self.path=self.root/'input';self.path.write_bytes(b'original exact bytes');self.path.chmod(0o600)
    def mutated(self,change):
        real=os.read;changed=[]
        def read(fd,n):
            raw=real(fd,n)
            if raw and not changed:changed.append(True);change()
            return raw
        with patch.object(host.os,'read',side_effect=read),self.assertRaises(AppError):host.read(self.path)
    def test_after_open_same_target_symlink_denied_original_retained(self):
        def change():self.path.rename(self.root/'retained');self.path.symlink_to(self.root/'retained')
        self.mutated(change);self.assertEqual((self.root/'retained').read_bytes(),b'original exact bytes')
    def test_after_open_public_mode_rejected(self):self.mutated(lambda:self.path.chmod(0o644))
    def test_after_open_hardlink_rejected(self):self.mutated(lambda:os.link(self.path,self.root/'retained-link'))
    def test_primary_read_error_survives_close_failure(self):
        real=os.close;primary=OSError('read primary')
        def close(fd):real(fd);raise OSError('close secondary')
        with patch.object(host.os,'read',side_effect=primary),patch.object(host.os,'close',side_effect=close):
            try:host.read(self.path)
            except OSError as error:self.assertIs(error,primary)
            else:self.fail('missing original read failure')
