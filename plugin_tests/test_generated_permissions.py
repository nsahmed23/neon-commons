"""Generated tenant review material stays private after staging is published."""
import os
import stat
import tempfile
import unittest
from pathlib import Path

from reference.core import write_project


class GeneratedPermissionsTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'POSIX permissions qualification')
    def test_permissive_umask_cannot_expose_new_project(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'project'
            old = os.umask(0)
            try:
                self.assertEqual(write_project({'review/nested/normalized.json': '{"sensitive":"fixture"}'}, destination), 'created')
            finally:
                os.umask(old)
            for path in [destination, *destination.rglob('*')]:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600, path.name)

    @unittest.skipUnless(os.name == 'posix', 'POSIX permissions qualification')
    def test_existing_user_permissions_are_not_silently_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'project'
            files = {'review.json': '{}'}
            write_project(files, destination)
            destination.chmod(0o750)
            (destination / 'review.json').chmod(0o640)
            self.assertEqual(write_project(files, destination), 'unchanged')
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o750)
            self.assertEqual(stat.S_IMODE((destination / 'review.json').stat().st_mode), 0o640)
