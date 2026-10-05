"""Trusted test-host location override; the qualified validator hash never changes."""
from dataclasses import replace
import os
from pathlib import Path

from intune_iac.approval_authority import VerifierPin


def verifier_pin(executable, sha256):
    pin = VerifierPin(executable, sha256)
    location = os.environ.get('INTUNE_TEST_VALIDATOR_LIBRARY')
    return pin if location is None else replace(pin, validator_library=Path(location))
