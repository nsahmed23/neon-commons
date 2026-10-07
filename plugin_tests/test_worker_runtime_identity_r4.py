"""Actual filesystem inventory changes invalidate the reviewed controller."""
from pathlib import Path
import shutil
import sys
import _ssl
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import worker_runtime_identity as runtime


class RuntimeIdentityTests(unittest.TestCase):
    def test_complete_package_and_actual_interpreter_stdlib_native_libraries_bound(self):
        inventory = runtime.inventory(); root = Path(runtime.__file__).parent
        expected = {'package/' + str(path.relative_to(root)) for path in root.rglob('*.py')}
        self.assertEqual({key for key in inventory if key.startswith('package/')}, expected)
        self.assertIn('package/capture.py', inventory)
        self.assertIn('package/capture_adapter.py', inventory)
        self.assertIn('package/workbench_store.py', inventory)
        self.assertIn('package/worker_state.py', inventory)
        self.assertTrue(any(key.startswith('interpreter/') for key in inventory))
        if getattr(_ssl, '__file__', None):
            self.assertTrue(any('_ssl' in key for key in inventory))
        else:
            self.assertIn('_ssl', sys.builtin_module_names)
        self.assertTrue(any(key.startswith('loaded-native/') and 'libc.so' in key for key in inventory))
        self.assertTrue(any(key.startswith('loaded-native/') and 'libseccomp' in key for key in inventory))
        # This qualified CPython statically embeds _ssl/libcrypto; dynamically
        # loaded native libraries are covered by the observed maps inventory.
    def test_changed_transitive_file_and_added_module_invalidate_cached_inventory(self):
        with tempfile.TemporaryDirectory(prefix='iw-runtime-copy-') as temporary:
            root = Path(temporary) / 'package'
            shutil.copytree(Path(runtime.__file__).parent, root, ignore=shutil.ignore_patterns('__pycache__'))
            with patch.object(runtime, '__file__', str(root / 'worker_runtime_identity.py')):
                before = runtime.inventory()
                with (root / 'capture.py').open('a') as stream: stream.write('\n# deliberate private fixture transitive change\n')
                changed = runtime.inventory()
                self.assertNotEqual(before['package/capture.py'], changed['package/capture.py'])
                (root / 'unreviewed_fixture_module.py').write_text('VALUE = 1\n')
                added = runtime.inventory()
                self.assertIn('package/unreviewed_fixture_module.py', added)
                self.assertEqual(len(added), len(changed) + 1)
    def test_source_symlink_is_not_a_declared_runtime_file(self):
        with tempfile.TemporaryDirectory(prefix='iw-runtime-link-') as temporary:
            root = Path(temporary); (root / 'worker_runtime_identity.py').write_text('# private fixture\n')
            (root / 'capture.py').symlink_to(Path(runtime.__file__).parent / 'capture.py')
            with patch.object(runtime, '__file__', str(root / 'worker_runtime_identity.py')):
                with self.assertRaises(Exception) as error: runtime.inventory()
                self.assertEqual(error.exception.code, 'service_runtime_symlink')


if __name__ == '__main__': unittest.main()
