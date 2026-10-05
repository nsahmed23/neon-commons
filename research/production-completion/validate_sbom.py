#!/usr/bin/env python3
"""Replay validation against the exact acquired CycloneDX schema, offline."""
import hashlib
import json
from pathlib import Path

from jsonschema import Draft7Validator, FormatChecker
from referencing import Registry, Resource

root = Path(__file__).resolve().parent
schema_bytes = (root / 'schemas/bom-1.6.schema.json').read_bytes()
assert hashlib.sha256(schema_bytes).hexdigest() == '1ebcb88a2c845ecb6ff7bee7aeabdff9422cb0347f3d6875b241bd444b7e098f'
schema = json.loads(schema_bytes)
artifact = (root / 'runtime-sbom.cdx.json').read_bytes()
registry = Registry().with_resource(schema['$id'], Resource.from_contents(schema))
validator = Draft7Validator(schema, format_checker=FormatChecker(), registry=registry)
errors = sorted((str(e) for e in validator.iter_errors(json.loads(artifact))))
print(json.dumps({'status': 'FAIL' if errors else 'PASS', 'schema_sha256': hashlib.sha256(schema_bytes).hexdigest(), 'artifact_sha256': hashlib.sha256(artifact).hexdigest(), 'errors': errors}, indent=2))
raise SystemExit(bool(errors))
