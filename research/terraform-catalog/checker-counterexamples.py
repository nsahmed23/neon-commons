#!/usr/bin/env python3
"""Run two isolated counterexamples against selected, inspected upstream checks.

No Terraform, network, provider, cloud or upstream fixture runs. We compile only
the three named, pinned checker functions; their dependencies are explicit local
stubs. The result establishes an assertion limitation, not a native lab replay.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace


PIN = "86b69d2292485d179698f5b9bf648a29f935e216"


def load_selected(checkout: Path, relative: str, names: list[str], scope: dict) -> dict:
    path = checkout / relative
    raw = path.read_bytes()
    tree = ast.parse(raw, filename=relative)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in selected} != set(names):
        raise RuntimeError("Pinned source no longer has the inspected checkers")
    # No module imports, decorators, fixtures or other top-level code execute.
    for node in selected:
        if node.decorator_list:
            raise RuntimeError("Unexpected checker decorator")
    exec(compile(ast.Module(body=selected, type_ignores=[]), relative, "exec"), scope)
    return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "checkers": names}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    commit = subprocess.run(["git", "-C", str(args.checkout), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(args.checkout), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, check=True).stdout.strip()
    if commit != PIN or dirty:
        raise SystemExit("Use the pristine pinned source checkout")
    results = []
    target = "aws_instance.billing_api"
    original = {"InstanceId": "i-original-before-adoption", "State": {"Name": "terminated"}}
    replacement = {"InstanceId": "i-new-after-recreation", "State": {"Name": "running"},
                   "Tags": [{"Key": "Name", "Value": "legacy-billing-api"}, {"Key": "Owner", "Value": "ops"}]}
    state = {target: {"values": {"id": replacement["InstanceId"], "tags": {"Owner": "ops"}}}}
    scope = {"ADRESSE_CIBLE": target, "_instance_heritee": lambda: replacement,
             "_instances_vivantes": lambda: [replacement], "_gerees": lambda: state}
    names = ["test_l_instance_du_state_est_celle_qui_preexistait", "test_aucune_instance_supplementaire_n_a_ete_creee"]
    source = load_selected(args.checkout, "labs/aws/import-moved-drift/challenge/tests/test_functional.py", names, scope)
    for name in names:
        scope[name]()
    results.append({"id": "CAT-IDENTITY", "result": "counterexample_reproduced",
                    "method": "actual_upstream_assertion_functions_with_explicit_inventory_and_state_stubs",
                    "source": source, "pre_operation_id": original["InstanceId"],
                    "post_operation_id": replacement["InstanceId"], "selected_assertions_passed": len(names),
                    "meaning": "The selected identity/count checks accept a replacement once both current inventory and state point to it.",
                    "limit": "The complete AWS lab and real emulator were not executed."})
    with tempfile.TemporaryDirectory(prefix="catalog-checker-counterexample-") as temporary:
        temp = Path(temporary)
        work = temp / "work"
        work.mkdir()
        # The fixture records that a different apply advanced state. This check
        # receives only the stale response and cannot distinguish that history.
        (work / "history.json").write_text(json.dumps({"saved_plan_A_executed": False, "ordinary_apply_B_executed": True}))
        calls = []

        def stale_response(*argv: str, cwd: Path) -> SimpleNamespace:
            calls.append(list(argv))
            return SimpleNamespace(returncode=1, stderr="Error: Saved plan is stale", stdout="")

        scope = {"Path": Path, "shutil": shutil, "terraform": stale_response,
                 "PLAN_ENREGISTRE": "tfplan"}
        names = ["test_le_plan_enregistre_a_ete_applique_et_est_desormais_perime"]
        source = load_selected(args.checkout, "labs/getting-started/terraform-workflow/challenge/tests/test_functional.py", names, scope)
        scope[names[0]](work, temp / "test-tmp")
        results.append({"id": "CAT-PLAN-HISTORY", "result": "counterexample_reproduced",
                        "method": "actual_upstream_assertion_function_with_explicit_stale_CLI_response_stub",
                        "source": source, "saved_plan_A_executed": False, "ordinary_apply_B_executed": True,
                        "checker_accepted_stale_response": True, "cli_calls_stubbed": calls,
                        "meaning": "The checker has no evidence that distinguishes the saved plan from a different apply advancing state.",
                        "limit": "This isolates the assertion; a separate native CLI experiment is needed to observe the alternate history."})
    document = {"schema_version": 1, "commit": PIN, "counterexamples": results,
                "native_cli_or_lab_execution": False}
    args.output.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({"isolated_checker_counterexamples": len(results), "reproduced": len(results), "native_lab_runs": 0}))


if __name__ == "__main__":
    main()
