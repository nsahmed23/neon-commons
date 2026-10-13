"""Publish a sanitized workspace subtree using Git plumbing only.

Review gate: --export-dir DIR writes the exact sanitized candidate bytes for scanning and owner review (no commit,
no push; refuses a non-empty DIR, exit 2). A real --push needs --review-receipt FILE, a JSON with "verdict" "PASS"
and "files" ({relpath: {"sha256": hex, ...}}, the shape tools/scan_published.py writes). The candidate set must equal
the receipt's files exactly (paths and sha256); otherwise up to 20 differing paths are printed tagged
added/removed/changed, nothing is committed or pushed, and the exit code is 5. --dry-run never pushes, so it needs
no receipt.
"""

import argparse
from datetime import datetime, timezone
import fnmatch
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


TEXT_SUFFIXES = {".md", ".json", ".jsonl", ".html", ".js", ".py", ".txt", ".csv"}


class GitFailure(Exception):
    def __init__(self, stderr):
        super().__init__(stderr)
        self.stderr = stderr


def git(repo, *args, data=None):
    command = ["git", "-C", str(repo), *args]
    try:
        result = subprocess.run(
            command, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except OSError as exc:
        raise GitFailure(str(exc)) from exc
    if result.returncode:
        raise GitFailure(result.stderr.decode("utf-8", "replace"))
    return result.stdout


def oid(output):
    return output.strip().decode("ascii")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--allowlist", required=True, type=Path)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--message")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--export-dir", type=Path)
    parser.add_argument("--review-receipt", type=Path)
    args = parser.parse_args()
    if args.export_dir and args.push:
        parser.error("--export-dir cannot be combined with --push")
    if not args.root.is_dir():
        parser.error("--root must be a directory")
    if not args.allowlist.is_file():
        parser.error("--allowlist must be a file")
    parts = args.prefix.replace("\\", "/").split("/")
    if not parts or any(part in ("", ".", "..") for part in parts):
        parser.error("--prefix must be a nonempty path inside the repository")
    args.prefix_parts = parts
    if not args.branch or args.branch.startswith("-"):
        parser.error("--branch must be a valid branch name")
    if not args.remote or args.remote.startswith("-"):
        parser.error("--remote must be a remote name or path")
    check = subprocess.run(
        ["git", "check-ref-format", "--branch", args.branch],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check.returncode:
        parser.error("--branch must be a valid branch name")
    return args


def excluded_hard(relative):
    parts = relative.parts
    lowered = tuple(part.lower() for part in parts)
    if "source.git" in lowered or "inbox" in lowered:
        return True
    if any(a == "logs" and b == "transcripts" for a, b in zip(lowered, lowered[1:])):
        return True
    return relative.suffix.lower() in {".log", ".err"}


def matches(relative, pattern):
    path_parts = relative.as_posix().split("/")
    pattern_parts = pattern.split("/")

    def match_at(path_index, pattern_index):
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        part = pattern_parts[pattern_index]
        if part == "**":
            return any(
                match_at(next_index, pattern_index + 1)
                for next_index in range(path_index, len(path_parts) + 1)
            )
        return (
            path_index < len(path_parts)
            and fnmatch.fnmatchcase(path_parts[path_index], part)
            and match_at(path_index + 1, pattern_index + 1)
        )

    return match_at(0, 0)


def load_patterns(path):
    includes = []
    excludes = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("!"):
            if line[1:]:
                excludes.append(line[1:])
        else:
            includes.append(line)
    return includes, excludes


def home_pattern():
    user = os.environ.get("USERNAME") or getpass.getuser()
    name = re.escape(user)
    doubled = re.escape("\\\\")
    single = re.escape("\\")
    paths = [
        rf"[A-Za-z]:{doubled}Users{doubled}{name}",
        rf"[A-Za-z]:{single}Users{single}{name}",
        rf"[A-Za-z]:/Users/{name}",
        rf"/c/Users/{name}",
        rf"/mnt/c/Users/{name}",
    ]
    return re.compile("(?:" + "|".join(paths) + r")(?=$|[/\\])", re.IGNORECASE)


def encoded_home_pattern():
    user = os.environ.get("USERNAME") or getpass.getuser()
    return re.compile(
        r"([A-Za-z]--Users-)" + re.escape(user) + r"(?![A-Za-z0-9_])", re.IGNORECASE
    )


MEMORY_FILE_PATTERN = re.compile(
    r"(\.claude[/\\]projects[/\\][^/\\\s]+[/\\]memory[/\\])[\w.\-]+\.md", re.IGNORECASE
)


# The owner's Claude Code setting VALUE stays private; the bare key name reveals nothing and is kept.
REMOTE_CONTROL_VALUE_PATTERN = re.compile(
    r"[\"'`]?remoteControlAtStartup[\"'`]?\s*(?:is\s+|[:=]\s*)?(?:true|false)\b", re.IGNORECASE
)
# The owner's agent permission posture (same terms as controller_log.py POSTURE). Redacted in prose and data
# files only: a .py file keeps its patterns and test inputs, which reveal nothing about the owner's settings.
POSTURE_PATTERN = re.compile(
    r"danger-full-access|approval[ ]never|approval_policy(?:\s*=\s*\"never\")?|dangerously-skip-permissions"
    r"|bypass[ ]?permissions", re.IGNORECASE
)


def sanitize_text(value, home, encoded, redact_posture=False):
    value = home.sub("~", value)
    value = encoded.sub(r"\1~", value)
    value = REMOTE_CONTROL_VALUE_PATTERN.sub("[setting redacted]", value)
    if redact_posture:
        value = POSTURE_PATTERN.sub("[posture redacted]", value)
    return MEMORY_FILE_PATTERN.sub(r"\1[redacted].md", value)


def collect(root, patterns):
    includes, excludes = patterns
    replacement = home_pattern()
    encoded = encoded_home_pattern()
    collected = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d for d in dirs
            if not (Path(directory) / d).is_symlink()
            and not excluded_hard((Path(directory) / d).relative_to(root))
        )
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(root)
            if path.is_symlink() or excluded_hard(relative):
                continue
            if not any(matches(relative, pattern) for pattern in includes):
                continue
            if any(matches(relative, pattern) for pattern in excludes):
                continue
            raw = path.read_bytes()
            if relative.parts[0].lower() != "handoff" and path.suffix.lower() in TEXT_SUFFIXES:
                value = raw.decode("utf-8", "surrogateescape")
                posture = path.suffix.lower() != ".py"
                raw = sanitize_text(value, replacement, encoded, posture).encode("utf-8", "surrogateescape")
            collected.append((relative, raw))
    collected.sort(key=lambda item: item[0].as_posix())
    return collected


def read_tree(repo, tree):
    entries = {}
    output = git(repo, "ls-tree", "-z", tree)
    for record in output.split(b"\0"):
        if not record:
            continue
        header, raw_name = record.split(b"\t", 1)
        mode, kind, sha = header.decode("ascii").split(" ")
        name = raw_name.decode("utf-8", "surrogateescape")
        entries[name] = (mode, kind, sha)
    return entries


def make_tree(repo, entries):
    records = []
    for name, (mode, kind, sha) in entries.items():
        record = f"{mode} {kind} {sha}\t".encode("ascii")
        records.append(record + name.encode("utf-8", "surrogateescape") + b"\0")
    return oid(git(repo, "mktree", "--missing", "-z", data=b"".join(records)))


def subtree_from_files(repo, files):
    root = {}
    for relative, content in files:
        sha = oid(git(repo, "hash-object", "-w", "--stdin", data=content))
        node = root
        parts = relative.parts
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = ("100644", "blob", sha)

    def write(node):
        entries = {}
        for name, value in node.items():
            if isinstance(value, dict):
                entries[name] = ("040000", "tree", write(value))
            else:
                entries[name] = value
        return make_tree(repo, entries)

    return write(root)


def graft(repo, old_tree, parts, new_tree):
    entries = read_tree(repo, old_tree)
    name = parts[0]
    if len(parts) == 1:
        entries[name] = ("040000", "tree", new_tree)
    else:
        previous = entries.get(name)
        if previous is not None and previous[1] != "tree":
            raise GitFailure(f"prefix component is not a tree: {name}")
        old_child = previous[2] if previous else make_tree(repo, {})
        entries[name] = ("040000", "tree", graft(repo, old_child, parts[1:], new_tree))
    return make_tree(repo, entries)


MAX_DIFF_LINES = 20


def export_candidate(files, target):
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        print(f"refusing to export into a non-empty path: {target}", file=sys.stderr)
        return 2
    for relative, content in files:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    target.mkdir(parents=True, exist_ok=True)
    print(f"exported {len(files)} files to {target}")
    return 0


def check_receipt(files, receipt_path):
    """Return None when the receipt approves exactly this candidate set, else a list of reasons."""
    if receipt_path is None:
        return ["no --review-receipt given; a push needs a PASS receipt for this exact file set"]
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        approved = {path: entry["sha256"] for path, entry in receipt["files"].items()}
        verdict = receipt["verdict"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [f"unreadable review receipt: {exc}"]
    problems = []
    if verdict != "PASS":
        problems.append(f"receipt verdict is {verdict!r}, not 'PASS'")
    candidate = {relative.as_posix(): hashlib.sha256(content).hexdigest() for relative, content in files}
    diffs = [f"added {path}" for path in sorted(candidate.keys() - approved.keys())]
    diffs += [f"removed {path}" for path in sorted(approved.keys() - candidate.keys())]
    diffs += [f"changed {path}" for path in sorted(candidate.keys() & approved.keys())
              if candidate[path] != approved[path]]
    problems += diffs[:MAX_DIFF_LINES]
    if len(diffs) > MAX_DIFF_LINES:
        problems.append(f"... and {len(diffs) - MAX_DIFF_LINES} more differing paths")
    return problems or None


def publish(args):
    repo = args.repo
    files = collect(args.root, load_patterns(args.allowlist))
    if args.export_dir:
        return export_candidate(files, args.export_dir)
    if args.push and not args.dry_run:
        problems = check_receipt(files, args.review_receipt)
        if problems:
            print("PUBLISH REFUSED by the review gate:", file=sys.stderr)
            for problem in problems:
                print(problem, file=sys.stderr)
            return 5
    if args.fetch:
        git(
            repo,
            "fetch",
            args.remote,
            f"+refs/heads/{args.branch}:refs/heads/{args.branch}",
        )
    tip = oid(git(repo, "rev-parse", f"refs/heads/{args.branch}"))
    tip_tree = oid(git(repo, "rev-parse", f"{tip}^{{tree}}"))
    subtree = subtree_from_files(repo, files)
    new_root = graft(repo, tip_tree, args.prefix_parts, subtree)
    if new_root == tip_tree:
        print("no changes")
        return 0
    message = args.message or "docs(takeover): sync " + datetime.now(timezone.utc).isoformat()
    commit = oid(git(repo, "commit-tree", new_root, "-p", tip, "-m", message))
    if args.dry_run:
        for relative, content in files:
            print(f"{relative.as_posix()} {len(content)}")
    print(commit)
    if args.push and not args.dry_run:
        try:
            git(repo, "push", args.remote, f"{commit}:refs/heads/{args.branch}")
        except GitFailure as exc:
            print(exc.stderr, file=sys.stderr, end="" if exc.stderr.endswith("\n") else "\n")
            return 3
        git(repo, "update-ref", f"refs/heads/{args.branch}", commit, tip)
    return 0


def main():
    args = parse_args()
    try:
        return publish(args)
    except GitFailure as exc:
        print(exc.stderr, file=sys.stderr, end="" if exc.stderr.endswith("\n") else "\n")
        return 4
    except (OSError, UnicodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
