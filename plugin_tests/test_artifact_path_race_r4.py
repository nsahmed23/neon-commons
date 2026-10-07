"""Deterministic ancestor replacement at the actual file-open boundary."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import artifact_vault as vault
from intune_iac.io import AppError


@unittest.skipUnless(sys.platform == 'linux', 'Descriptor-relative Linux archival')
class ArtifactPathRaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.selected = self.root / 'selected'
        self.selected.mkdir(mode=0o700)
        self.relocated = self.root / 'original'
        self.outside = self.root / 'outside'
        self.outside.mkdir(mode=0o700)

    def swap(self):
        self.selected.rename(self.relocated)
        self.selected.symlink_to(self.outside, target_is_directory=True)

    def test_read_does_not_follow_parent_swapped_after_validation(self):
        for parent, contents in ((self.selected, b'approved bytes'), (self.outside, b'outside secret')):
            target = parent / 'capture'
            target.write_bytes(contents)
            target.chmod(0o600)
        real_open = os.open
        swapped = False

        def open_at_boundary(path, flags, *args, **kwargs):
            nonlocal swapped
            if not swapped and Path(path).name == 'capture':
                self.swap()
                swapped = True
            return real_open(path, flags, *args, **kwargs)

        with patch.object(vault.os, 'open', side_effect=open_at_boundary):
            try:
                actual = vault._read(self.selected / 'capture', 1024)
            except AppError:
                actual = None
        self.assertTrue(swapped)
        self.assertIn(actual, (None, b'approved bytes'))

    def test_write_never_redirects_into_replacement_parent(self):
        real_open = os.open
        swapped = False

        def open_at_boundary(path, flags, *args, **kwargs):
            nonlocal swapped
            if not swapped and Path(path).name.startswith('.artifact-stage-'):
                self.swap()
                swapped = True
            return real_open(path, flags, *args, **kwargs)

        with patch.object(vault.os, 'open', side_effect=open_at_boundary):
            try:
                vault._write_new(self.selected / 'restored', b'private restoration')
            except AppError:
                pass
        self.assertTrue(swapped)
        self.assertEqual(list(self.outside.iterdir()), [])
        self.assertFalse(any(p.name.startswith('.artifact-stage-') for p in self.relocated.iterdir()))


if __name__ == '__main__':
    unittest.main()
