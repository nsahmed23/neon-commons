"""Shared fixtures for the PKG-SETUP-5B tests: the real capture command behind a fake transport, and a fake JWT."""
import base64
import json
from pathlib import Path
import sys

from plugin_tests.test_signin_fix1 import Base

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = str(ROOT / 'plugin_tests' / 'signin_capture_launcher.py')
NIL = '00000000-0000-0000-0000-000000000000'


def b64(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=').decode()


def jwt(**claims):
    return b64({'alg': 'none', 'typ': 'JWT'}) + '.' + b64(claims) + '.' + b64('signature-0123456789')


class RealCaptureBase(Base):
    """The collecting child is the real capture command, run through a launcher that fakes only its HTTP transport."""
    capture_mode = '403'

    def command(self, tenant, policy, output, descriptor):
        return [sys.executable, '-B', LAUNCHER, str(ROOT), self.capture_mode, 'capture', '--tenant', tenant, '--policy', policy,
                '--output', output, '--token-fd', str(descriptor)]


