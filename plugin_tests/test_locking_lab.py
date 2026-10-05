"""The native lab must reject unreviewed inputs before it executes them."""
import importlib.util
import os
from pathlib import Path
import signal
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LockingLabSafetyTests(unittest.TestCase):
    def module(self):
        script = ROOT / "scripts/qualify-locking-lab.py"
        self.assertTrue(script.is_file(), "Native locking lab runner is missing")
        spec = importlib.util.spec_from_file_location("locking_lab", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_changed_upstream_file_is_rejected(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)
            (source / "conftest.py").write_text("raise RuntimeError('unreviewed')")
            with self.assertRaisesRegex(ValueError, "reviewed source mismatch"):
                module.reviewed_sources(source)

    def test_oversized_upstream_source_is_rejected(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)
            with (source / "conftest.py").open("wb") as stream:
                stream.truncate(1024 * 1024 + 1)
            with self.assertRaisesRegex(ValueError, "exceeds"):
                module.reviewed_sources(source)

    def test_existing_output_is_preserved(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "run"
            target.mkdir()
            marker = target / "user-file"
            marker.write_text("preserve me")
            with self.assertRaises(FileExistsError):
                module.new_output(target)
            self.assertEqual(marker.read_text(), "preserve me")

    def test_output_symlink_parent_is_rejected(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "real").mkdir()
            (root / "alias").symlink_to(root / "real", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "canonical"):
                module.new_output(root / "alias/run")
            self.assertFalse((root / "real/run").exists())

    def test_clean_environment_has_no_inherited_credentials_or_tf_flags(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as td:
            env = module.clean_environment(Path(td))
            self.assertEqual(env["TF_IN_AUTOMATION"], "1")
            self.assertEqual(env["LAB_NO_REPLAY"], "1")
            self.assertFalse(any(k.startswith(("ARM_", "AZURE_", "AWS_", "TF_CLI_ARGS")) for k in env))
            self.assertNotIn("PYTHONPATH", env)
            self.assertEqual(env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")

    def test_source_symlink_is_rejected_even_if_bytes_match(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target"
            target.write_bytes(b"test")
            (root / "conftest.py").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "regular file"):
                module.reviewed_sources(root)

    def test_failed_measurement_reaps_its_background_process(self):
        module = self.module()
        process = None
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "bin").mkdir()
            (root / "work").mkdir()
            executable = root / "bin/terraform"
            executable.write_text("#!/bin/sh\nexec sleep 30\n")
            executable.chmod(0o700)
            try:
                with self.assertRaisesRegex(RuntimeError, "measurement interrupted"):
                    with module.background_apply(root, module.clean_environment(root), "test.log") as process:
                        raise RuntimeError("measurement interrupted")
                self.assertIsNotNone(process.poll(), "Failed measurement left its owned apply alive")
                self.assertLess(process.returncode, 0)
            finally:
                if process is not None and process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
