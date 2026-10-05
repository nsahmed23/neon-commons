#!/usr/bin/env python3
"""Verify genuine pinned offline validation dependencies; never installs or fetches."""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import importlib.metadata as metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON runtime receipt")
    args = parser.parse_args()
    errors = []
    versions = {}
    for line in (ROOT / "requirements-validation.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, expected = line.split("==", 1)
        try:
            actual = metadata.version(name)
            versions[name] = {"expected": expected, "observed": actual}
            if actual != expected:
                errors.append("dependency_version:" + name)
        except metadata.PackageNotFoundError:
            errors.append("dependency_missing:" + name)
    modules = {}
    for name in ("jsonschema", "yaml", "hcl2"):
        try:
            module = importlib.import_module(name)
            modules[name] = str(Path(module.__file__).resolve())
        except ImportError:
            errors.append("module_missing:" + name)
    smoke = {}
    if "jsonschema" in modules:
        from jsonschema import Draft202012Validator, FormatChecker
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                  "type": "object", "required": ["id"], "additionalProperties": False,
                  "properties": {"id": {"type": "string", "format": "uuid", "minLength": 36, "maxLength": 36}}}
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        valid = {"id": "11111111-1111-4111-8111-111111111111"}
        smoke["draft202012_uuid_length_unknown_key"] = (
            validator.is_valid(valid)
            and not validator.is_valid({"id": "11111111111141118111111111111111"})
            and not validator.is_valid({"id": "invalid"})
            and not validator.is_valid(dict(valid, unknown=True)))
    if "yaml" in modules:
        import yaml
        smoke["yaml_safe_load"] = yaml.safe_load("offline: true\n") == {"offline": True}
    if "hcl2" in modules:
        import hcl2
        from hcl2.utils import SerializationOptions
        parsed = hcl2.loads('import {\n to = policy.example\n id = "11111111-1111-4111-8111-111111111111"\n}\n',
                            serialization_options=SerializationOptions(strip_string_quotes=True, explicit_blocks=False, with_comments=False))
        smoke["hcl_import_structure"] = parsed == {"import": [{"to": "${policy.example}", "id": "11111111-1111-4111-8111-111111111111"}]}
        try:
            hcl2.loads('import { id = "unterminated }')
        except Exception:
            smoke["hcl_malformed_rejected"] = True
        else:
            smoke["hcl_malformed_rejected"] = False
    errors.extend("smoke_failure:" + name for name, passed in smoke.items() if not passed)
    blocked = any(error.startswith(("dependency_", "module_")) for error in errors)
    receipt = {"observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
               "scope": "local validation runtime only; no provider, cloud or model execution",
               "python": sys.version, "interpreter": sys.executable, "versions": versions,
               "modules": modules, "smoke_checks": smoke, "errors": errors,
               "status": "blocked" if blocked else ("pass" if not errors else "fail")}
    rendered = json.dumps(receipt, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 2 if blocked else (0 if not errors else 1)


if __name__ == "__main__":
    raise SystemExit(main())
