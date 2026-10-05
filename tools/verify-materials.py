#!/usr/bin/env python3
"""Verify the integrated offline reference. Does not launch cloud/agent tools.

Writes result-summary.json and final-test-log.txt to the selected receipt directory.
Requires the genuine pinned packages in requirements-validation.txt. It never
installs dependencies or fetches URLs.
"""
from __future__ import annotations

import argparse
import ast
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import sys
import unittest
import importlib.metadata

import yaml
from jsonschema import Draft202012Validator, validators

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

REQUIRED = [
    "BUILD-START-HERE.md", "INPUTS-AND-DECISIONS.md", "BUILD-PLAN.md",
    "MATERIALS-STATUS.md", "gap-register.json", "requirements-traceability.csv",
    "source-lock.json", "code-catalog.jsonl", "reuse-ledger.csv",
    "citation-repair-ledger.csv", "THIRD-PARTY-NOTICES.md", "ZIP-ACCEPTANCE.md",
    "catalog-manifest.json", "provider-api-coverage.csv", "compatibility.csv",
    "family-coverage.csv", "permission-matrix.csv", "microsoft-workflows.yaml",
    "PERMISSIONS.md", "DIAGNOSTICS.md", "INTUNE-ROLLOUT.md",
    "contracts/NORMALIZATION.md", "wizard/wizard-state-machine.yaml",
    "wizard/wizard-questions.yaml", "wizard/FILES-AND-RESUME.md",
    "wizard/PLATFORM-AND-COMMANDS.md", "reference/core.py", "reference/invariants.py",
    "reference/approval.py", "tools/build-reference.py",
    "evaluations/HOSTS-AND-HARNESSES.md", "evaluations/test_additional_materials.py",
]
EXCLUDE = {"__pycache__", ".pytest_cache"}


def files():
    return sorted(p for p in ROOT.rglob("*") if p.is_file()
                  and p.relative_to(ROOT).parts[0] != '.git'
                  and not (set(p.relative_to(ROOT).parts) & EXCLUDE)
                  and p.suffix != ".pyc")


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def no_nonfinite_number(value):
    raise ValueError(f"Nonfinite JSON number: {value}")


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        no_nonfinite_number(value)
    return number


def strict_json_decoder():
    return json.JSONDecoder(object_pairs_hook=no_duplicate_keys,
                            parse_constant=no_nonfinite_number,
                            parse_float=finite_float)


def parse_json(text):
    return strict_json_decoder().decode(text)


def parse_jsonl(text):
    """JSONL requires one complete JSON value on each nonblank line."""
    return [parse_json(line) for line in text.splitlines() if line.strip()]


def parse_jsonstream(text):
    """Parse complete JSON values separated by JSON whitespace, without junk."""
    decoder = strict_json_decoder()
    records = []
    offset = 0
    while offset < len(text):
        while offset < len(text) and text[offset] in " \t\r\n":
            offset += 1
        if offset == len(text):
            break
        record, offset = decoder.raw_decode(text, offset)
        records.append(record)
        if offset < len(text) and text[offset] not in " \t\r\n":
            raise ValueError("JSON stream records must be separated by JSON whitespace")
    return records


def check_json_schema(schema):
    """Honor known dialects; retain Draft 2020-12 only for undeclared schemas."""
    if isinstance(schema, dict) and "$schema" in schema:
        dialect = schema["$schema"]
        if not isinstance(dialect, str):
            raise ValueError("JSON Schema dialect must be a known $schema URI")
        validator = validators.validator_for(schema, default=None)
        if validator is None:
            raise ValueError(f"Unknown JSON Schema dialect: {dialect}")
    else:
        validator = Draft202012Validator
    validator.check_schema(schema)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', help='Receipt directory; default is verification/ inside this copy')
    args = parser.parse_args()
    failures = []
    counts = {"json": 0, "jsonl_records": 0, "jsonstream_records": 0, "yaml": 0, "csv": 0,
              "python_syntax": 0, "schemas": 0, "generated_projects": 0,
              "generated_files_verified": 0}
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            failures.append(f"Missing required file: {name}")
    for path in files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            if path.is_symlink():
                raise ValueError("Symlink is not permitted in the materials distribution")
            raw = path.read_text(encoding="utf-8")
            if path.suffix == ".json":
                parse_json(raw)
                counts["json"] += 1
            elif path.suffix == ".jsonl":
                counts["jsonl_records"] += len(parse_jsonl(raw))
            elif path.suffix == ".jsonstream":
                counts["jsonstream_records"] += len(parse_jsonstream(raw))
            elif path.suffix in {".yaml", ".yml"} or path.name.endswith((".yaml.example", ".yml.example")):
                list(yaml.safe_load_all(raw))
                counts["yaml"] += 1
            elif path.suffix == ".csv":
                rows = list(csv.DictReader(io.StringIO(raw)))
                if not rows or any(None in row for row in rows):
                    raise ValueError("Empty or malformed CSV")
                counts["csv"] += 1
            elif path.suffix == ".py":
                ast.parse(raw, filename=rel)
                counts["python_syntax"] += 1
            if path.name.endswith(".schema.json"):
                check_json_schema(parse_json(raw))
                counts["schemas"] += 1
        except Exception as exc:
            failures.append(f"{rel}: {type(exc).__name__}: {exc}")
    for manifest in ROOT.glob("examples/*/expected/project/generated-files.json"):
        try:
            record = parse_json(manifest.read_text(encoding="utf-8"))
            for name, expected in record["files"].items():
                part = PurePosixPath(name)
                if part.is_absolute() or ".." in part.parts or "\\" in name:
                    raise ValueError("Unsafe generated-file path")
                path = manifest.parent / name
                if path.is_symlink() or not path.is_file():
                    raise ValueError(f"Missing/unsafe generated file {name}")
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError(f"Hash mismatch {name}")
                counts["generated_files_verified"] += 1
            counts["generated_projects"] += 1
        except Exception as exc:
            failures.append(f"{manifest.relative_to(ROOT)}: {exc}")
    log = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "evaluations"), pattern="test_*.py")
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    success = not failures and result.wasSuccessful()
    summary = {
        "schema_version": "1.0.0",
        "verified_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "integrated offline reference, independent preservation, parsed generated HCL and local workflow; not provider execution or native host/live qualification",
        "result": "pass" if success else "fail",
        "static_counts": counts,
        "static_failures": failures,
        "tests": {"run": result.testsRun, "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped) - len(result.expectedFailures),
                  "failures": len(result.failures), "errors": len(result.errors),
                  "skipped": len(result.skipped), "expected_failures": len(result.expectedFailures)},
        "runtime": {name: importlib.metadata.version(name) for name in ['jsonschema', 'PyYAML', 'python-hcl2']},
        "not_run": ["Actual provider schema/serialization validation", "OpenTofu/Atmos execution", "native Windows/PowerShell execution", "Claude/Codex host install or eval", "agent A/B benchmarks", "live Azure/Graph/Intune calls", "provider-backed import/plan", "dsoxlab execution"],
        "limitations": ["Schema validity is not service correctness.", "Synthetic plans and fixtures are not provider traces.", "Source pins and source text review are not acquired dependency closure.", "Bash argv roundtrip invokes only the local Python interpreter, not a cloud or provider tool.", "No comprehensive secret-scanning guarantee is made."]
    }
    destination = Path(args.output) if args.output else ROOT / "verification"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "result-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (destination / "final-test-log.txt").write_text(log.getvalue(), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not success:
        print(log.getvalue(), file=sys.stderr)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
