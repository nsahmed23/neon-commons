#!/usr/bin/env python3
"""Read-only source inventory and evidence checks; inventory never imports target.

This is a bounded triage tool, not a vulnerability scanner certification. Findings
are candidates requiring source review and separately isolated reproduction.
The explicit sandbox-regressions command executes its fixed test corpus only.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import unicodedata

VERSION = "security-inventory/1.0"
MAX_FILES = 20000
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
SKIP = {".git", "__pycache__", ".venv", "node_modules", "wheelhouse", "acquired"}
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".go", ".ps1", ".sh", ".yml", ".yaml", ".toml", ".json", ".hcl", ".tf"}
STATES = {"candidate", "confirmed", "mitigated", "rejected", "duplicate", "blocked"}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()


def read_regular(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE:
            raise ValueError("nonregular_or_oversized")
        data = stream.read(MAX_FILE + 1)
        after = os.fstat(stream.fileno())
        if len(data) > MAX_FILE or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("changed_or_oversized")
    return data


def call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return call_name(node.value) + "." + node.attr
    return "<dynamic>"


def triage_python(data):
    """Deliberately small AST rules; no import, eval, command, or target execution."""
    tree = ast.parse(data)
    candidates = []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(x.name for x in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.Call):
            name = call_name(node.func)
            rule = None
            if name in {"eval", "exec", "os.system", "os.popen"}:
                rule = "dynamic_execution_review"
            elif name in {"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_output", "subprocess.check_call"}:
                rule = "subprocess_boundary_review"
                if any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
                    rule = "shell_true_review"
            elif name.endswith("extractall"):
                rule = "archive_extraction_review"
            elif name.endswith("build_opener") and not any(isinstance(a, ast.Call) and call_name(a.func).endswith("ProxyHandler") for a in node.args):
                rule = "ambient_proxy_review"
            if rule:
                candidates.append({"rule": rule, "line": node.lineno, "status": "candidate", "severity": None})
    return sorted(set(imports)), candidates


def inventory(root):
    root = Path(root).absolute()
    if not root.is_dir() or any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("unsafe_root")
    files = []
    gaps = []
    names = {}
    total = 0
    entries = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as iterator:
            for entry in iterator:
                entries += 1
                if entries > MAX_FILES:
                    gaps.append({"path": ".", "reason": "entry_limit"})
                    pending.clear()
                    break
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                if entry.name in SKIP:
                    gaps.append({"path": relative, "reason": "excluded_dependency_or_acquisition_tree"})
                    continue
                if entry.is_symlink():
                    gaps.append({"path": relative, "reason": "symlink_not_followed"})
                    continue
                key = unicodedata.normalize("NFC", relative).casefold()
                if key in names and names[key] != relative:
                    gaps.append({"path": relative, "reason": "case_or_unicode_collision", "other": names[key]})
                names[key] = relative
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                    continue
                if path.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                try:
                    data = read_regular(path)
                    total += len(data)
                    if total > MAX_TOTAL:
                        gaps.append({"path": relative, "reason": "aggregate_byte_limit"})
                        pending.clear()
                        break
                    item = {"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "imports": [], "candidates": []}
                    if path.suffix == ".py":
                        item["imports"], item["candidates"] = triage_python(data)
                    # Only location and type are retained; candidate secret bytes never enter a report.
                    if re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", data):
                        item["candidates"].append({"rule": "private_key_marker_review", "line": None, "status": "candidate", "severity": None})
                    files.append(item)
                except (ValueError, OSError, SyntaxError, UnicodeError, RecursionError) as error:
                    gaps.append({"path": relative, "reason": type(error).__name__})
    files.sort(key=lambda x: x["path"])
    return {"schema_version": VERSION, "status": "INCONCLUSIVE", "assurance": "bounded_static_triage_only", "target_code_executed": False,
            "files": files, "coverage_gaps": sorted(gaps, key=lambda x: x["path"]),
            "source_manifest_sha256": hashlib.sha256(canonical([{k: v for k, v in f.items() if k in {"path", "sha256"}} for f in files])).hexdigest(),
            "limits": {"entries": MAX_FILES, "file_bytes": MAX_FILE, "total_bytes": MAX_TOTAL},
            "limitations": ["rules do not establish reachability or impact", "non-Python code inventoried but not parsed", "dependency advisories not fetched", "no secret absence guarantee", "file walk assumes trusted nonconcurrent ancestors"]}


def validate_ledger(document):
    errors = []
    if not isinstance(document, dict) or not isinstance(document.get("findings"), list):
        return ["invalid_top_level"]
    ids = set()
    for i, finding in enumerate(document["findings"]):
        if not isinstance(finding, dict):
            errors.append(f"{i}:invalid_record")
            continue
        ident = finding.get("id")
        if not isinstance(ident, str) or ident in ids:
            errors.append(f"{i}:invalid_or_duplicate_id")
        ids.add(ident if isinstance(ident, str) else str(i))
        state = finding.get("state")
        if state not in STATES:
            errors.append(f"{i}:invalid_state")
        required = {"attacker", "prerequisites", "input", "invariant", "trace", "impact", "evidence", "blocker", "repair", "reviewer"}
        if not required <= finding.keys():
            errors.append(f"{i}:missing_evidence_fields")
        if state == "confirmed" and (not finding.get("evidence") or not finding.get("reviewer")):
            errors.append(f"{i}:confirmation_without_evidence_or_review")
        if state in {"candidate", "blocked"} and finding.get("severity") is not None:
            errors.append(f"{i}:unverified_severity")
        if state == "mitigated" and (not finding.get("repair") or not finding.get("evidence")):
            errors.append(f"{i}:mitigation_without_evidence")
    return errors


def sandbox_regressions(root):
    """Fixed local tests, no shell, no arbitrary commands, no host write mount.

    Requires Linux bubblewrap with user/mount/network/PID namespaces. It fails
    closed if any control is unavailable. Output is bounded by RLIMIT_FSIZE.
    """
    if sys.platform != "linux" or not Path("/usr/bin/bwrap").is_file():
        return {"status": "BLOCKED", "reason": "linux_bubblewrap_required"}
    import resource
    root = Path(root).resolve()
    prefix = Path(sys.prefix).resolve()
    executable = Path(sys.executable).absolute()
    modules = ["plugin_tests.test_security_boundaries_completion", "plugin_tests.test_security_audit_completion",
               "plugin_tests.test_generated_permissions", "plugin_tests.test_restricted_hashes",
               "plugin_tests.test_graph_budget",
               "plugin_tests.test_workflow.WorkflowTests.test_parent_alias_cannot_hide_source_inside_evidence"]
    command = ["/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--new-session",
               "--cap-drop", "ALL", "--ro-bind", "/usr", "/usr",
               "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
               "--symlink", "usr/lib64", "/lib64"]
    if not prefix.is_relative_to("/usr"):
        command += ["--ro-bind", str(prefix), str(prefix)]
    base = Path(sys.base_prefix).resolve()
    if base != prefix and not base.is_relative_to("/usr"):
        command += ["--ro-bind", str(base), str(base)]
    command += ["--ro-bind", str(root), "/target", "--size", "1048576", "--tmpfs", "/tmp",
                "--size", "67108864", "--tmpfs", "/scratch", "--chdir", "/target", "--clearenv",
                "--setenv", "PATH", "/usr/bin", "--setenv", "HOME", "/scratch",
                "--setenv", "TMPDIR", "/scratch", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
                "--setenv", "INTUNE_AUDIT_ISOLATED", "1",
                "--setenv", "PYTHONHASHSEED", "0", str(executable), "-B", "-m", "unittest", *modules, "-v"]

    def limits():
        for kind, value in [(resource.RLIMIT_CPU, 30), (resource.RLIMIT_AS, 1024 * 1024 * 1024),
                            (resource.RLIMIT_NPROC, 32), (resource.RLIMIT_NOFILE, 128),
                            (resource.RLIMIT_FSIZE, 64 * 1024 * 1024), (resource.RLIMIT_CORE, 0)]:
            resource.setrlimit(kind, (value, value))
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                 env={}, start_new_session=True, preexec_fn=limits)
        timed_out = False
        try:
            child.wait(timeout=40)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        stdout.seek(0); stderr.seek(0)
        out = stdout.read(1024 * 1024 + 1); err = stderr.read(1024 * 1024 + 1)
    blocked = child.returncode != 0 and (b"bwrap:" in err)
    truncated = len(out) > 1024 * 1024 or len(err) > 1024 * 1024
    infra_error = timed_out or truncated or b"ModuleNotFoundError:" in err
    return {"status": "BLOCKED" if blocked else "INFRA_ERROR" if infra_error else "PASS" if child.returncode == 0 else "FAIL",
            "assurance": "isolated_python_regressions_only", "exit_code": child.returncode,
            "timed_out": timed_out, "output_truncated": truncated, "command": command, "environment": {"PATH": "/usr/bin", "HOME": "/scratch", "TMPDIR": "/scratch", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0", "INTUNE_AUDIT_ISOLATED": "1"},
            "sandbox": {"network": "new_unshared_namespace", "source": "read_only", "toolchain": "read_only", "host_writable_mounts": [], "scratch_bytes": 67108864, "temporary_bytes": 1048576, "cpu_seconds": 30, "wall_seconds": 40, "memory_bytes": 1073741824, "processes": 32, "file_bytes": 67108864, "retained_output_bytes_per_stream": 1048576, "procfs": "absent"},
            "stdout": out.decode("utf-8", errors="replace"), "stderr": err.decode("utf-8", errors="replace"),
            "limitations": ["not native Windows", "not live tenant", "not a whole-repository security acceptance"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory"); inv.add_argument("--root", required=True)
    val = sub.add_parser("validate-ledger"); val.add_argument("--input", required=True)
    run = sub.add_parser("sandbox-regressions"); run.add_argument("--root", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inventory":
            result = inventory(args.root)
            code = 0  # Successful inventory, explicitly not security PASS.
        elif args.command == "validate-ledger":
            errors = validate_ledger(json.loads(read_regular(Path(args.input))))
            result = {"status": "FAIL" if errors else "PASS", "assurance": "ledger_structure_only", "errors": errors}
            code = 1 if errors else 0
        else:
            result = sandbox_regressions(args.root)
            code = 0 if result["status"] == "PASS" else 3
    except (ValueError, OSError, TypeError, RecursionError):
        result = {"status": "INFRA_ERROR", "reason": "invalid_or_unreadable_input"}; code = 2
    print(json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
