import getpass
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "publish_branch.py"


class PublishBranchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo.git"
        self.remote = self.base / "remote.git"
        self.root = self.base / "workspace"
        self.root.mkdir()
        self.env = os.environ.copy()
        self.env.update(
            GIT_AUTHOR_NAME="Fixture",
            GIT_AUTHOR_EMAIL="fixture@example.test",
            GIT_COMMITTER_NAME="Fixture",
            GIT_COMMITTER_EMAIL="fixture@example.test",
        )
        self.git_init(self.repo)
        self.git_init(self.remote)
        self.tip = self.seed_commit()
        self.git("update-ref", "refs/heads/main", self.tip)
        self.git(
            "fetch",
            str(self.repo),
            "refs/heads/main:refs/heads/main",
            repo=self.remote,
        )
        self.git("remote", "add", "origin", str(self.remote))
        self.allowlist = self.base / "allowlist.txt"
        self.allowlist.write_text(
            "# Includes and hard exclusions\n"
            "docs/**\nhandoff/**\nlogs/**\ninbox/**\n*.log\n*.err\n"
            "*.zip\n*.png\nsource.git/**\n!docs/skip.md\n",
            encoding="ascii",
        )
        self.write("docs/new.md", self.home_text().encode("utf-8"))
        self.write("docs/skip.md", b"skip")
        self.write("handoff/h.json", self.home_text().encode("utf-8"))
        self.write("logs/transcripts/t.jsonl", b"secret")
        self.write("inbox/r.json", b"secret")
        self.write("source.git/config", b"secret")
        self.write("x.log", b"secret")
        self.write("x.err", b"secret")
        self.write("archive.zip", b"\x00\xffzip")
        self.write("nested/archive.zip", b"outside root glob")
        self.write("image.png", b"\x89PNG\x00")

    def git_init(self, path):
        subprocess.run(
            ["git", "init", "--bare", str(path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env,
        )

    def git(self, *args, repo=None, data=None):
        return self.git_bytes(*args, repo=repo, data=data).strip().decode("ascii")

    def git_bytes(self, *args, repo=None, data=None):
        result = subprocess.run(
            ["git", "-C", str(repo or self.repo), *args],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env,
        )
        if result.returncode:
            self.fail(result.stderr.decode("utf-8", "replace"))
        return result.stdout

    def blob(self, data):
        return self.git("hash-object", "-w", "--stdin", data=data)

    def tree(self, entries):
        lines = []
        for name, (mode, kind, oid) in sorted(entries.items()):
            lines.append(f"{mode} {kind} {oid}\t{name}\n")
        return self.git("mktree", data="".join(lines).encode("ascii"))

    def seed_commit(self):
        docs = self.tree({"a.md": ("100644", "blob", self.blob(b"old docs"))})
        src = self.tree({"x.py": ("100644", "blob", self.blob(b"print(1)"))})
        keep = self.tree({"k.txt": ("100644", "blob", self.blob(b"keep"))})
        published_docs = self.tree(
            {"old.md": ("100644", "blob", self.blob(b"old published"))}
        )
        published = self.tree(
            {"docs": ("040000", "tree", published_docs), "keep": ("040000", "tree", keep)}
        )
        root = self.tree(
            {
                "docs": ("040000", "tree", docs),
                "published": ("040000", "tree", published),
                "src": ("040000", "tree", src),
            }
        )
        return self.git("commit-tree", root, "-m", "seed")

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def home_text(self):
        user = os.environ.get("USERNAME") or getpass.getuser()
        return f"C:\\Users\\{user}\\x and /c/Users/{user}/x"

    def run_script(self, *options):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "--repo",
                str(self.repo),
                "--branch",
                "main",
                "--prefix",
                "published/docs",
                "--allowlist",
                str(self.allowlist),
                *options,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env,
            text=True,
        )

    def test_copy_sanitize_graft_parent_and_no_changes(self):
        result = self.run_script("--message", "publish fixture")
        self.assertEqual(result.returncode, 0, result.stderr)
        commit = result.stdout.strip().splitlines()[-1]
        self.assertEqual(self.git("rev-parse", f"{commit}^"), self.tip)
        self.assertEqual(self.git("show", f"{commit}:published/docs/docs/new.md"), "~\\x and ~/x")
        self.assertEqual(
            self.git_bytes("show", f"{commit}:published/docs/handoff/h.json"),
            self.home_text().encode("utf-8"),
        )
        self.assertEqual(
            self.git_bytes("show", f"{commit}:published/docs/archive.zip"),
            b"\x00\xffzip",
        )
        names = self.git("ls-tree", "-r", "--name-only", commit).splitlines()
        for excluded in (
            "published/docs/docs/skip.md",
            "published/docs/logs/transcripts/t.jsonl",
            "published/docs/inbox/r.json",
            "published/docs/source.git/config",
            "published/docs/nested/archive.zip",
            "published/docs/x.log",
            "published/docs/x.err",
            "published/docs/old.md",
        ):
            self.assertNotIn(excluded, names)
        for kept in ("archive.zip", "image.png", "docs/new.md", "handoff/h.json"):
            self.assertIn("published/docs/" + kept, names)
        for path in ("docs", "src", "published/keep"):
            self.assertEqual(self.git("rev-parse", f"{commit}:{path}"), self.git("rev-parse", f"{self.tip}:{path}"))
        self.assertNotEqual(self.git("rev-parse", f"{commit}:published"), self.git("rev-parse", f"{self.tip}:published"))
        self.assertEqual(self.git("rev-parse", "refs/heads/main"), self.tip)
        self.git("update-ref", "refs/heads/main", commit, self.tip)
        again = self.run_script()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("no changes", again.stdout)

    def test_dry_run_reports_files_and_does_not_update_ref(self):
        result = self.run_script("--dry-run", "--push")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("docs/new.md", result.stdout)
        self.assertIn("handoff/h.json", result.stdout)
        self.assertEqual(self.git("rev-parse", "refs/heads/main"), self.tip)
        self.assertEqual(self.git("rev-parse", "refs/heads/main", repo=self.remote), self.tip)

    def test_escaped_home_paths_and_missing_existing_blob(self):
        user = os.environ.get("USERNAME") or getpass.getuser()
        forms = [
            f"D:\\Users\\{user}\\x",
            f"C:/Users/{user}/x",
            f"C:\\\\Users\\\\{user}\\\\x",
            f"/c/Users/{user}/x",
            f"/mnt/c/Users/{user}/x",
        ]
        self.write("docs/paths.txt", "\n".join(forms).encode("utf-8"))
        missing = self.git("rev-parse", f"{self.tip}:src/x.py")
        object_path = self.repo / "objects" / missing[:2] / missing[2:]
        object_path.chmod(stat.S_IWRITE)
        object_path.unlink()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        commit = result.stdout.strip().splitlines()[-1]
        self.assertEqual(
            self.git("show", f"{commit}:published/docs/docs/paths.txt"),
            "~\\x\n~/x\n~\\\\x\n~/x\n~/x",
        )
        self.assertEqual(
            self.git("rev-parse", f"{commit}:src"),
            self.git("rev-parse", f"{self.tip}:src"),
        )

    def test_project_folder_encoding_and_memory_file_names_redacted(self):
        user = os.environ.get("USERNAME") or getpass.getuser()
        lines = [
            f"folder C--Users-{user} here",
            f"folder d--users-{user.upper()}/x",
            "see ~/.claude/projects/C--Users-~/memory/[redacted].md for more",
            f"see C:\\Users\\{user}\\.claude\\projects\\C--Users-{user}\\memory\\project_y.md now",
            f"see C:/Users/{user}/.claude/projects/C--Users-{user}/memory/[redacted].md ok",
        ]
        self.write("docs/mem.md", "\n".join(lines).encode("utf-8"))
        self.write("handoff/mem.md", "\n".join(lines).encode("utf-8"))
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        commit = result.stdout.strip().splitlines()[-1]
        self.assertEqual(
            self.git("show", f"{commit}:published/docs/docs/mem.md"),
            "\n".join(
                [
                    "folder C--Users-~ here",
                    "folder d--users-~/x",
                    "see ~/.claude/projects/C--Users-~/memory/[redacted].md for more",
                    "see ~\\.claude\\projects\\C--Users-~\\memory\\[redacted].md now",
                    "see ~/.claude/projects/C--Users-~/memory/[redacted].md ok",
                ]
            ),
        )
        self.assertEqual(
            self.git_bytes("show", f"{commit}:published/docs/handoff/mem.md"),
            "\n".join(lines).encode("utf-8"),
        )

    def test_remote_control_setting_value_redacted(self):
        # The key is split so this test file does not itself carry a setting-with-value line.
        key = "remoteControl" + "AtStartup"
        lines = [
            f"transcripts ({key} true, host-intake L43)",
            f"ask: Remote Control starts on by default ({key} is true) and syncs",
            f'    "{key}": true',
            f"bare mention of {key} stays",
            f"setting (`{key}` is true) here",
        ]
        self.write("docs/rc.md", "\n".join(lines).encode("utf-8"))
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        commit = result.stdout.strip().splitlines()[-1]
        self.assertEqual(
            self.git("show", f"{commit}:published/docs/docs/rc.md"),
            "\n".join(
                [
                    "transcripts ([setting redacted], host-intake L43)",
                    "ask: Remote Control starts on by default ([setting redacted]) and syncs",
                    "    [setting redacted]",
                    f"bare mention of {key} stays",
                    "setting ([setting redacted]) here",
                ]
            ),
        )

    def test_posture_terms_redacted_outside_python_files(self):
        # Split literals keep this test file free of the terms it checks.
        full, never = "danger-" + "full-access", "approval " + "never"
        line = f"defaults (`{full}`, `{never}`) quoted"
        self.write("docs/p.md", line.encode("utf-8"))
        self.write("docs/p.py", line.encode("utf-8"))
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        commit = result.stdout.strip().splitlines()[-1]
        self.assertEqual(
            self.git("show", f"{commit}:published/docs/docs/p.md"),
            "defaults (`[posture redacted]`, `[posture redacted]`) quoted",
        )
        # Code keeps its patterns and test inputs; a .py file is never rewritten for posture.
        self.assertEqual(self.git("show", f"{commit}:published/docs/docs/p.py"), line)

    def test_fetch_uses_remote_tip(self):
        tree = self.git("rev-parse", f"{self.tip}^{{tree}}")
        advanced = self.git("commit-tree", tree, "-p", self.tip, "-m", "advance", repo=self.remote)
        self.git("update-ref", "refs/heads/main", advanced, repo=self.remote)
        result = self.run_script("--fetch")
        self.assertEqual(result.returncode, 0, result.stderr)
        commit = result.stdout.strip().splitlines()[-1]
        self.assertEqual(self.git("rev-parse", f"{commit}^"), advanced)
        self.assertEqual(self.git("rev-parse", "refs/heads/main"), advanced)

    def test_usage_and_other_git_failure_codes(self):
        usage = self.run_script("--prefix", "../escape")
        self.assertEqual(usage.returncode, 2)
        invalid_branch = self.run_script("--branch", "bad..branch")
        self.assertEqual(invalid_branch.returncode, 2)
        failure = self.run_script("--branch", "missing")
        self.assertEqual(failure.returncode, 4)
        self.assertTrue(failure.stderr.strip())

    def export(self, name="export"):
        target = self.base / name
        result = self.run_script("--export-dir", str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        return target

    def receipt(self, verdict="PASS", name="receipt.json", mutate=None):
        exported = self.export(name + ".dir")
        files = {}
        for path in sorted(p for p in exported.rglob("*") if p.is_file()):
            data = path.read_bytes()
            files[path.relative_to(exported).as_posix()] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if mutate:
            mutate(files)
        target = self.base / name
        target.write_text(json.dumps({"verdict": verdict, "files": files}), encoding="utf-8")
        return target

    def assert_nothing_pushed(self):
        self.assertEqual(self.git("rev-parse", "refs/heads/main"), self.tip)
        self.assertEqual(self.git("rev-parse", "refs/heads/main", repo=self.remote), self.tip)

    def test_push_fast_forward_then_rejection(self):
        result = self.run_script("--push", "--review-receipt", str(self.receipt()), "--message", "first push")
        self.assertEqual(result.returncode, 0, result.stderr)
        pushed = self.git("rev-parse", "refs/heads/main")
        self.assertEqual(pushed, self.git("rev-parse", "refs/heads/main", repo=self.remote))
        tree = self.git("rev-parse", f"{pushed}^{{tree}}")
        advanced = self.git("commit-tree", tree, "-p", pushed, "-m", "advance", repo=self.remote)
        self.git("update-ref", "refs/heads/main", advanced, repo=self.remote)
        self.write("docs/new.md", b"changed after advance")
        rejected = self.run_script("--push", "--review-receipt", str(self.receipt(name="r2.json")),
                                   "--message", "second push")
        self.assertEqual(rejected.returncode, 3, rejected.stderr)
        self.assertTrue(rejected.stderr.strip())
        self.assertEqual(self.git("rev-parse", "refs/heads/main"), pushed)

    def test_push_without_receipt_refused(self):
        result = self.run_script("--push")
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assert_nothing_pushed()

    def test_push_with_mismatched_receipt_refused_and_lists_paths(self):
        def mutate(files):
            files["docs/new.md"]["sha256"] = "0" * 64
            del files["handoff/h.json"]
            files["docs/ghost.md"] = {"bytes": 1, "sha256": "1" * 64}

        result = self.run_script("--push", "--review-receipt", str(self.receipt(mutate=mutate)))
        self.assertEqual(result.returncode, 5, result.stderr)
        report = result.stdout + result.stderr
        self.assertIn("changed docs/new.md", report)
        self.assertIn("added handoff/h.json", report)
        self.assertIn("removed docs/ghost.md", report)
        self.assert_nothing_pushed()

    def test_push_with_non_pass_verdict_refused(self):
        result = self.run_script("--push", "--review-receipt", str(self.receipt(verdict="FAIL")))
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assert_nothing_pushed()

    def test_edit_after_review_refused(self):
        receipt = self.receipt()
        self.write("docs/new.md", b"edited after the review")
        result = self.run_script("--push", "--review-receipt", str(receipt))
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertIn("changed docs/new.md", result.stdout + result.stderr)
        self.assert_nothing_pushed()

    def test_export_dir_writes_sanitized_bytes_and_refuses_non_empty(self):
        target = self.export()
        self.assertEqual((target / "docs/new.md").read_bytes(), b"~\\x and ~/x")
        self.assertFalse((target / "docs/skip.md").exists())
        self.assertEqual((target / "handoff/h.json").read_bytes(), self.home_text().encode("utf-8"))
        self.assertEqual((target / "archive.zip").read_bytes(), b"\x00\xffzip")
        self.assertFalse((target / "inbox").exists())
        again = self.run_script("--export-dir", str(target))
        self.assertEqual(again.returncode, 2)
        self.assert_nothing_pushed()

    def test_export_dir_cannot_combine_with_push(self):
        result = self.run_script("--push", "--export-dir", str(self.base / "e2"))
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.base / "e2").exists())


if __name__ == "__main__":
    unittest.main()
