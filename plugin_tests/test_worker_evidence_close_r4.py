"""Real invalid signature plus injected owned-descriptor close failures."""
import base64
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from intune_iac import worker_evidence_posix as host
from intune_iac.io import AppError
from plugin_tests.signing_fixture import verifier_pin
from dataclasses import asdict

class VerifierCloseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        pin=verifier_pin(Path('/usr/bin/openssl'),hashlib.sha256(Path('/usr/bin/openssl').read_bytes()).hexdigest())
        self.pin=pin;host.write_new(self.root/'pin.json',{k:str(v) if isinstance(v,Path) else v for k,v in asdict(pin).items()});self.verifier=host.DetachedVerifier(self.root/'pin.json',self.root)
        self.key='d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a'
    def run_with_close_failure(self,*,interruption=None,closing=None,success=False):
        opened=[];real_open=os.open;real_close=os.close
        def open_file(path,*args,**kwargs):
            fd=real_open(path,*args,**kwargs)
            if str(path)==str(self.pin.executable):opened.append(fd)
            return fd
        def close(fd):
            real_close(fd)
            if fd in opened:opened.remove(fd);raise (closing or OSError('injected owned descriptor close'))
        with patch.object(host.os,'open',side_effect=open_file),patch.object(host.os,'close',side_effect=close):
            if success:
                with patch.object(host.protected,'_supervise',return_value=None):self.verifier(self.key,b'literal',bytes(64))
            elif interruption is None:self.verifier(self.key,b'literal',bytes(64))
            else:
                with patch.object(host.protected,'_supervise',side_effect=interruption):self.verifier(self.key,b'literal',bytes(64))
    def test_signature_failure_survives_final_descriptor_close(self):
        try:self.run_with_close_failure()
        except BaseException as error:self.assertIsInstance(error,AppError);self.assertEqual(error.code,'worker_evidence_signature_invalid')
        else:self.fail('no failure')
    def test_original_cancellation_survives_final_descriptor_close(self):
        original=KeyboardInterrupt('literal original')
        try:self.run_with_close_failure(interruption=original)
        except BaseException as error:self.assertIs(error,original)
        else:self.fail('no interruption')

    def test_secondary_close_interrupt_keeps_primary_signature_failure_as_cause(self):
        second=KeyboardInterrupt('literal secondary')
        try:self.run_with_close_failure(closing=second)
        except BaseException as error:self.assertIs(error,second);self.assertIsInstance(error.__cause__,AppError);self.assertEqual(error.__cause__.code,'worker_evidence_signature_invalid')
        else:self.fail('no interruption')
    def test_failed_close_never_returns_success(self):
        with self.assertRaises(OSError):self.run_with_close_failure(success=True)
