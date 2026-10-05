#!/usr/bin/env python3
"""Read a pinned training checkout; never execute its code or decrypt solutions.

Outputs content-derived records, not a claim that labs were executed or that
every assertion is correct. PyYAML is the only extra dependency.
"""
from __future__ import annotations

import argparse
import ast
import collections
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml

EXPECTED_COMMIT = "86b69d2292485d179698f5b9bf648a29f935e216"
REPOSITORY = "https://github.com/stephrobert/terraform-dsoxlab-training"

# Selected by inspection of actual assertions and runtime operations. All other
# labs still receive the same complete byte inventory / content scan below.
SELECTED = {
    "getting-started/terraform-overview": "Separate declared, managed and observed objects; compare identity before and after drift repair.",
    "getting-started/terraform-workflow": "Reopen the saved native plan and derive action classification independently; detect consumed or stale plans.",
    "getting-started/terraform-vs-opentofu": "Qualify each CLI/provider address/lock-file combination; compatibility has an explicit boundary.",
    "first-infra/debug-apply": "Recover partial execution by retaining previously successful identities and checking the real effect of the repaired step.",
    "write-code/count": "Positional keys can readdress objects; require stable identity keys and declarative moves.",
    "write-code/for-each": "Compare original resource identities after adding an instance or changing addressing.",
    "write-code/depends-on": "Separate implicit value references from explicit ordering requirements and avoid duplicate dependencies.",
    "write-code/lifecycle": "Inspect ordered replacement actions and action_reason; prevent_destroy is not protection after removing configuration.",
    "write-code/validation-check-preconditions": "Distinguish blocking preconditions from warning-only checks and deferred unknown values.",
    "state/understand-state": "Import existing values, detect refresh-dependent drift, and reject unrelated lineage or older serial.",
    "state/backends": "Resolve effective backend metadata after init and prove migration preserves state lineage.",
    "state/state-locking": "Measure actual concurrent lock contention and abandoned-process behavior; a lock-info file alone is not proof.",
    "state/terraform-state-mv": "Replay a move from old state in a disposable copy and assert previous_address plus no-op.",
    "state/terraform-state-rm": "Distinguish forget from delete and verify the real object survives; remaining configuration can recreate it.",
    "state/removed-block": "Test removal semantics per CLI version, including keyed-instance limitations and explicit destroy=false.",
    "state/backup-restore-state": "Record pre-write state and compare lineage, serial, inventory and artifact identity when restoring.",
    "state/diagnose-state": "A later no-change plan does not prove safe adoption; compare original values and both refresh-only and ordinary plans.",
    "modules/test-module": "Require real native test runs plus baseline-pass / mutant-fail controls; exit zero with zero tests is insufficient.",
    "environments/workspace": "Resolve selected workspace explicitly and test independent state inventories; workspace selection is process context.",
    "environments/terraform-in-automation": "Record plan 0/1/2 and fmt 3 distinctly; saved plans and JSON may contain secrets.",
    "aws/import-moved-drift": "Compare imported state IDs to independent emulator inventory, retain moves, and prove both kinds of no-change.",
    "aws/backend-s3-remote-state": "Exercise real backend contention and cross-stack output flow in an emulator, without claiming Azure equivalence.",
    "certifications/professional/capstone1-resource-lifecycle": "Test existing-object adoption and provider-side cleanup against an independent API inventory.",
    "certifications/professional/capstone3-collaborative-workflows": "Qualify two independent states and upstream-to-downstream value propagation through a real plan/apply cycle.",
}

FULL_CHECKER_REVIEWS = {
    "getting-started/terraform-overview", "getting-started/terraform-workflow",
    "first-infra/debug-apply", "state/understand-state", "state/diagnose-state",
    "state/state-locking", "modules/test-module", "aws/import-moved-drift",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True).stdout


def source_signals(text: str) -> list[str]:
    patterns = {
        "host_docker_socket": r"/var/run/docker\.sock",
        "local_exec_provisioner": r'provisioner\s+"local-exec"',
        "remote_exec_provisioner": r'provisioner\s+"remote-exec"',
        "libvirt": r"libvirt|virsh",
        "network_service": r"socket\.create_connection|localhost:|127\.0\.0\.1",
        "hcp_remote_account": r"app\.terraform\.io/api|TF_TOKEN_app_terraform_io|TFE_TOKEN",
        "state_push_force": r"state.{0,50}push.{0,50}-force",
        "destroy_operation": r'["\x27]destroy["\x27]|terraform destroy',
        "process_termination": r"killpg|SIGKILL|\.kill\(",
        "deletion_operation": r"shutil\.rmtree|\.unlink\(|\brm\s+-",
        "environment_inheritance": r"os\.environ|\$\{?HOME\}?",
        "ignore_all_changes": r"ignore_changes\s*=\s*all",
        "unfinished_exercise": r"\?\?\?",
    }
    return sorted(name for name, pattern in patterns.items() if re.search(pattern, text))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkout", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    root = args.checkout.resolve()
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    if commit != EXPECTED_COMMIT:
        raise SystemExit(f"Expected pinned commit {EXPECTED_COMMIT}, found {commit}")
    if git(root, "status", "--porcelain", "--untracked-files=no").strip():
        raise SystemExit("Tracked checkout has modifications; use the pristine pin")
    names = sorted(p.decode() for p in git(root, "ls-files", "-z").split(b"\0") if p)
    data = {}
    ledger = []
    for name in names:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"Unsupported source member: {name}")
        raw = path.read_bytes()
        data[name] = raw
        encrypted = raw.startswith(b"$ANSIBLE_VAULT;")
        ledger.append({"path": name, "size_bytes": len(raw), "sha256": digest(raw),
                       "content_access": "encrypted_not_inspected" if encrypted else "plaintext_scanned"})

    metadata = yaml.safe_load(data["meta.yml"])
    upstream = json.loads(data["validation-labs.json"])
    declared = [(sec["id"], path) for sec in metadata["sections"] for path in sec["labs"]]
    discovered = {name.removeprefix("labs/").removesuffix("/lab.yaml")
                  for name in names if name.startswith("labs/") and name.endswith("/lab.yaml")}
    if len(declared) != 88 or {path for _, path in declared} != discovered:
        raise SystemExit("The pinned 88-entry declaration and actual lab roots disagree")
    records = []
    for section, rel in declared:
        prefix = f"labs/{rel}/"
        lab_names = [name for name in names if name.startswith(prefix)]
        solution_names = [name for name in names if name.startswith(f"solution/{rel}/")]
        contract = yaml.safe_load(data[prefix + "lab.yaml"])
        test_path = prefix + "challenge/tests/test_functional.py"
        test_source = data[test_path].decode("utf-8")
        test_ast = ast.parse(test_source, filename=test_path)
        tests = []
        for node in ast.walk(test_ast):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                tests.append({"name": node.name, "line": node.lineno,
                              "assertions": [ast.unparse(n.test) for n in ast.walk(node) if isinstance(n, ast.Assert)],
                              "parameterized": any("parametrize" in ast.unparse(d) for d in node.decorator_list)})
        decoded = {name: data[name].decode("utf-8") for name in lab_names}
        all_text = "\n".join(decoded.values())
        hcl_text = "\n".join(text for name, text in decoded.items() if name.endswith((".tf", ".hcl")))
        providers = sorted(set(re.findall(r'source\s*=\s*"((?:hashicorp|dmacvicar)/[^"\n]+)"', hcl_text)))
        required_versions = sorted(set(re.findall(r'required_version\s*=\s*"([^"\n]+)"', hcl_text)))
        declared_fixtures = contract["runtime"].get("fixtures", [])
        missing = [fixture for fixture in declared_fixtures if prefix + "fixtures/" + fixture not in data]
        services = contract["runtime"].get("services", [])
        if rel == "hcp-terraform/premier-run-distant":
            environment = "real_hcp_account_and_remote_mutations"
        elif services:
            environment = "docker_service_and_native_provider"
        elif "dmacvicar/libvirt" in providers:
            environment = "local_libvirt_host_mutations"
        elif providers:
            environment = "local_native_provider_or_module_registry"
        else:
            environment = "inspect_fixture_completion_before_classifying_provider_free"
        if rel in {"state/state-locking", "modules/test-module"}:
            environment = "provider_free_native_cli_candidate"
        records.append({
            "id": contract["id"], "path": rel, "section": section,
            "title": contract["title"], "description": contract["description"].strip(),
            "source_url": f"{REPOSITORY}/tree/{commit}/{prefix.rstrip('/')}",
            "test_path": test_path, "test_sha256": digest(data[test_path]),
            "test_functions": tests, "test_function_count": len(tests),
            "assertion_node_count": sum(isinstance(n, ast.Assert) for n in ast.walk(test_ast)),
            "plaintext_lab_files": len(lab_names), "plaintext_bytes": sum(len(data[n]) for n in lab_names),
            "plaintext_lines": sum(len(data[n].splitlines()) for n in lab_names),
            "plaintext_paths": lab_names,
            "solution_files": len(solution_names),
            "encrypted_solution_files": sum(data[n].startswith(b"$ANSIBLE_VAULT;") for n in solution_names),
            "runtime": contract["runtime"]["type"], "declared_fixtures": declared_fixtures,
            "missing_declared_fixtures": missing,
            "provider_sources_found_in_fixture_hcl": providers,
            "required_cli_versions_found": required_versions,
            "services": [{"name": s["name"], "image": s["image"],
                          "host_docker_socket": "/var/run/docker.sock" in json.dumps(s),
                          "post_start_commands": len(s.get("post_start", []))} for s in services],
            "source_risk_signals": source_signals(all_text), "execution_environment": environment,
            "review_scope": "all_plaintext_bytes_scanned_test_AST_and_topic_review",
            "selected_for_semantic_inspection": rel in SELECTED,
            "complete_checker_source_read": rel in FULL_CHECKER_REVIEWS,
            "lesson_for_plugin": SELECTED.get(rel, "Supporting curriculum; test topics and actual assertion expressions are recorded for targeted reuse."),
            "upstream_receipt": upstream["labs"].get(contract["id"]),
            "execution_by_this_inventory": "not_executed",
            "qualification": "No Atmos, Intune provider, Microsoft Graph, Azure backend, or host integration proof.",
        })
    summary = {
        "repository": REPOSITORY, "commit": commit,
        "license": "CC-BY-4.0", "license_sha256": digest(data["LICENSE"]),
        "source_manifest_sha256": digest(json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()),
        "tracked_files": len(ledger), "tracked_bytes": sum(x["size_bytes"] for x in ledger),
        "declared_labs": len(declared), "actual_lab_roots": len(discovered),
        "plaintext_lab_files": sum(r["plaintext_lab_files"] for r in records),
        "plaintext_lab_lines_scanned": sum(r["plaintext_lines"] for r in records),
        "plaintext_lab_bytes_scanned": sum(r["plaintext_bytes"] for r in records),
        "test_functions": sum(r["test_function_count"] for r in records),
        "assertion_nodes": sum(r["assertion_node_count"] for r in records),
        "encrypted_solution_files": sum(r["encrypted_solution_files"] for r in records),
        "selected_semantic_inspections": len(SELECTED),
        "complete_checker_files_read": len(FULL_CHECKER_REVIEWS),
        "complete_checker_lines_read": sum(len(data[f"labs/{rel}/challenge/tests/test_functional.py"].splitlines()) for rel in FULL_CHECKER_REVIEWS),
        "labs_with_declared_services": sum(bool(r["services"]) for r in records),
        "labs_mounting_docker_socket": sum(any(s["host_docker_socket"] for s in r["services"]) for r in records),
        "missing_declared_fixtures": sum(len(r["missing_declared_fixtures"]) for r in records),
        "upstream_verdict_counts": dict(collections.Counter(r["upstream_receipt"]["verdict"] for r in records)),
        "upstream_after_score_counts": dict(collections.Counter(str(r["upstream_receipt"]["score_apres"]) for r in records)),
        "our_executed_labs": 0,
        "method_limits": ["Static content scan and human topic/selected-assertion review are distinct from execution.",
                          "All 299 solution files are encrypted and were neither decrypted nor semantically inspected.",
                          "Provider references are extracted from fixtures, which intentionally contain incomplete exercises.",
                          "No claim of exhaustive semantic or security proof for every upstream assertion."],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [("inventory.json", {"schema_version": 1, "summary": summary, "labs": records}),
                        ("source-files.json", {"repository": REPOSITORY, "commit": commit, "files": ledger})]:
        (args.output / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    with (args.output / "lab-matrix.csv").open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["id", "path", "title", "test_functions", "assertions", "plaintext_files", "encrypted_solution_files", "environment", "selected_review", "execution", "lesson"])
        for r in records:
            writer.writerow([r["id"], r["path"], r["title"], r["test_function_count"], r["assertion_node_count"], r["plaintext_lab_files"], r["encrypted_solution_files"], r["execution_environment"], r["selected_for_semantic_inspection"], r["execution_by_this_inventory"], r["lesson_for_plugin"]])
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
