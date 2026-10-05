"""Release content boundaries, independent of the checkout's incidental files."""
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/build-release.py'
SPEC = importlib.util.spec_from_file_location('release_builder_audit', SCRIPT)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ReleaseAuditTests(unittest.TestCase):
    def test_hardlinked_source_cannot_copy_outside_bytes_into_release(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); root = parent / 'repo'; root.mkdir()
            outside = parent / 'private.md'; outside.write_text('unlisted-private-canary')
            os.link(outside, root / 'README.md')
            with patch.object(builder, 'ROOT', root):
                with self.assertRaises(ValueError):
                    builder.write_archive(parent / 'out.zip', ['README.md'], 'source')

    def build(self, root, output, runtime=('README.md',)):
        with patch.object(builder, 'ROOT', root), patch.object(builder, 'runtime_files', return_value=list(runtime)), \
                patch.object(sys, 'argv', ['build-release.py', '--output-dir', str(output)]), \
                contextlib.redirect_stdout(io.StringIO()):
            builder.main()

    def fixture(self, root, names=('README.md', 'release-source-files.txt')):
        root.mkdir()
        (root / 'README.md').write_text('Reviewed project documentation\n')
        (root / 'release-source-files.txt').write_text('\n'.join(names) + '\n')

    def test_unlisted_local_data_does_not_enter_source_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); root = parent / 'repo'; output = parent / 'out'
            self.fixture(root)
            (root / '.env').write_text('TOKEN=private-canary\n')
            (root / 'tenant.tfstate').write_text('private-canary')
            (root / 'capture').mkdir()
            (root / 'capture/export.json').write_text('private-canary')
            self.build(root, output)
            with zipfile.ZipFile(output / f'Intune_IaC_Plugin_{builder.__version__}_Source.zip') as archive:
                names = set(archive.namelist())
                self.assertEqual(names, {'intune-iac-source/README.md',
                                         'intune-iac-source/release-source-files.txt',
                                         'intune-iac-source/SHA256SUMS'})
                self.assertFalse(any(b'private-canary' in archive.read(name) for name in names))

    def test_symlinked_runtime_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); root = parent / 'repo'; external = parent / 'private'
            self.fixture(root, ('README.md', 'release-source-files.txt', 'scripts/launcher.py'))
            external.mkdir(); (external / 'launcher.py').write_text('private-canary')
            (root / 'scripts').symlink_to(external, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.build(root, parent / 'out', ('scripts/launcher.py',))

    def test_output_symlink_into_checkout_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); root = parent / 'repo'
            self.fixture(root)
            alias = parent / 'alias'; alias.symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.build(root, alias / 'generated-archives')
            self.assertFalse((root / 'generated-archives').exists())

    def test_manifest_parent_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); root = parent / 'repo'
            self.fixture(root, ('README.md', 'release-source-files.txt', '../private.txt'))
            (parent / 'private.txt').write_text('private-canary')
            with self.assertRaises(ValueError):
                self.build(root, parent / 'out')

    def test_missing_manifest_is_not_recursive_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); root = parent / 'repo'
            self.fixture(root); (root / 'release-source-files.txt').unlink()
            with self.assertRaises(ValueError):
                self.build(root, parent / 'out')

    def test_existing_archive_and_receipt_are_preserved(self):
        for filename in (f'Intune_IaC_Plugin_{builder.__version__}.zip',
                         'Intune_IaC_Plugin_Archive_Receipt.json'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                parent = Path(directory); root = parent / 'repo'; output = parent / 'out'
                self.fixture(root); output.mkdir()
                existing = output / filename; existing.write_bytes(b'previous-release')
                with self.assertRaises(ValueError):
                    self.build(root, output)
                self.assertEqual(existing.read_bytes(), b'previous-release')

    def test_concurrent_output_creation_is_preserved(self):
        for receipt_race in (False, True):
            with self.subTest(receipt_race=receipt_race), tempfile.TemporaryDirectory() as directory:
                parent = Path(directory); root = parent / 'repo'; output = parent / 'out'
                self.fixture(root)
                original_write = builder.write_archive
                raced = output / ('Intune_IaC_Plugin_Archive_Receipt.json' if receipt_race
                                  else f'Intune_IaC_Plugin_{builder.__version__}.zip')
                def racing_write(destination, names, prefix):
                    if not receipt_race and prefix == 'intune-iac':
                        raced.write_bytes(b'concurrent-release')
                    result = original_write(destination, names, prefix)
                    if receipt_race and prefix == 'intune-iac-source':
                        raced.write_bytes(b'concurrent-release')
                    return result
                with patch.object(builder, 'write_archive', side_effect=racing_write):
                    with self.assertRaises((ValueError, FileExistsError)):
                        self.build(root, output)
                self.assertEqual(raced.read_bytes(), b'concurrent-release')

    def test_generated_hash_manifest_name_is_reserved(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); root = parent / 'repo'
            self.fixture(root, ('README.md', 'release-source-files.txt', 'SHA256SUMS'))
            (root / 'SHA256SUMS').write_text('obsolete-hashes')
            with self.assertRaises(ValueError):
                self.build(root, parent / 'out')

    def test_swapped_source_symlink_never_enters_snapshot(self):
        for parent_swap in (False, True):
            with self.subTest(parent_swap=parent_swap), tempfile.TemporaryDirectory() as directory:
                parent = Path(directory); root = parent / 'repo'; external = parent / 'external'
                self.fixture(root, ('README.md', 'release-source-files.txt', 'docs/review.md'))
                (root / 'docs').mkdir(); (root / 'docs/review.md').write_text('reviewed-bytes')
                external.mkdir(); (external / 'review.md').write_text('unlisted-private-canary')
                original_allowed = builder.allowed
                swapped = False
                def swap_after_check(path):
                    nonlocal swapped
                    result = original_allowed(path)
                    if path == root / 'docs/review.md' and result and not swapped:
                        swapped = True
                        if parent_swap:
                            (root / 'docs').rename(root / 'docs-original')
                            (root / 'docs').symlink_to(external, target_is_directory=True)
                        else:
                            path.unlink(); path.symlink_to(external / 'review.md')
                    return result
                with patch.object(builder, 'ROOT', root), patch.object(builder, 'allowed', side_effect=swap_after_check):
                    try:
                        builder.write_archive(parent / 'out.zip', ['docs/review.md'], 'source')
                    except (ValueError, OSError):
                        pass
                    else:
                        with zipfile.ZipFile(parent / 'out.zip') as archive:
                            self.assertNotIn(b'unlisted-private-canary', archive.read('source/docs/review.md'))

    def test_runtime_and_source_use_same_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); root = parent / 'repo'; output = parent / 'out'
            self.fixture(root)
            original_write = builder.write_archive
            def change_after_runtime(destination, names, prefix):
                result = original_write(destination, names, prefix)
                if prefix == 'intune-iac':
                    (root / 'README.md').write_text('changed-after-runtime-build')
                return result
            with patch.object(builder, 'write_archive', side_effect=change_after_runtime):
                self.build(root, output)
            with zipfile.ZipFile(output / f'Intune_IaC_Plugin_{builder.__version__}.zip') as runtime, \
                    zipfile.ZipFile(output / f'Intune_IaC_Plugin_{builder.__version__}_Source.zip') as source:
                self.assertEqual(runtime.read('intune-iac/README.md'), source.read('intune-iac-source/README.md'))


if __name__ == '__main__':
    unittest.main()
