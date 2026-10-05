"""Tamper and metadata counterexamples for the release dependency boundary."""
import copy
import hashlib
import importlib.util
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from intune_iac.io import AppError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify-dependencies.py"
SPEC = importlib.util.spec_from_file_location("verify_dependencies", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DependenciesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.make_wheel()

    def make_wheel(self, metadata=b"Name: example\nVersion: 1.0\n", extra=None):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("example-1.0.dist-info/METADATA", metadata)
            if extra:
                archive.writestr(extra, b"payload")
        data = stream.getvalue()
        self.path = self.root / "example-1.0-py3-none-any.whl"
        self.path.write_bytes(data)
        self.manifest = {"schema_version": "1.0.0", "platform": "linux-x86_64-cpython-3.12",
                         "packages": [{"filename": self.path.name, "name": "example", "version": "1.0",
                                       "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}]}

    def test_intact_bytes_and_metadata_verified_without_execution(self):
        report = MODULE.verify_wheelhouse(self.root, self.manifest)
        self.assertEqual(report["status"], "verified")
        self.assertFalse(report["installation_performed"])
        self.assertFalse(report["publisher_authenticated"])

    def test_tampered_bytes_rejected(self):
        self.path.write_bytes(self.path.read_bytes() + b"changed")
        with self.assertRaisesRegex(AppError, "reviewed digest"):
            MODULE.verify_wheelhouse(self.root, self.manifest)

    def test_missing_or_extra_file_rejected(self):
        (self.root / "extra.whl").write_bytes(b"extra")
        with self.assertRaisesRegex(AppError, "exactly"):
            MODULE.verify_wheelhouse(self.root, self.manifest)
        (self.root / "extra.whl").unlink()
        self.path.unlink()
        with self.assertRaisesRegex(AppError, "exactly"):
            MODULE.verify_wheelhouse(self.root, self.manifest)

    def test_hash_does_not_override_wrong_metadata_or_path(self):
        for metadata, extra in [(b"Name: substituted\nVersion: 1.0\n", None),
                                (b"Name: example\nVersion: 2.0\n", None),
                                (b"Name: example\nName: example\nVersion: 1.0\n", None),
                                (b"Name: example\nVersion: 1.0\n", "../escape")]:
            with self.subTest(metadata=metadata, extra=extra):
                self.make_wheel(metadata, extra)
                with self.assertRaisesRegex(AppError, "metadata or paths"):
                    MODULE.verify_wheelhouse(self.root, self.manifest)

    def test_duplicate_lock_and_symlink_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["packages"].append(copy.deepcopy(manifest["packages"][0]))
        with self.assertRaisesRegex(AppError, "unique"):
            MODULE.verify_wheelhouse(self.root, manifest)
        original = self.root / "original"
        self.path.rename(original)
        self.path.symlink_to(original)
        with self.assertRaisesRegex(AppError, "regular files"):
            MODULE.verify_wheelhouse(self.root, self.manifest)
