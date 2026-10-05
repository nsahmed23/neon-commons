"""Actual local contract gates shared by the repaired reference entrypoints.

The correction models remain isolated decision specifications. These exports
make their bounded input/output validators usable by the integrated pipeline;
they do not confer provider, service, or command execution qualification.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from corrections.models.contract_model import (
    ContractViolation, capture_errors, provider_settings, reference_errors,
    validate_executable,
)

ROOT = Path(__file__).resolve().parents[1]


def schema_errors(name: str, value: object) -> list[str]:
    """Validate a named local schema, returning only safe path/error codes.

    Correction schemas take precedence where a versioned contract replaces an
    original schema. Only known schema filenames under these two directories
    are addressable. Unknown keys in instance data never appear in diagnostics.
    """
    if not isinstance(name, str) or not name.replace('-', '').isalnum():
        raise ContractViolation('unknown_contract')
    candidates = [ROOT / 'corrections' / 'contracts' / f'{name}.schema.json',
                  ROOT / 'contracts' / f'{name}.schema.json']
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        raise ContractViolation('unknown_contract')
    schema = json.loads(path.read_text(encoding='utf-8'))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    # Numeric path components are safe; property names must be declared in the
    # selected schema. Anything else is an opaque marker, never an unknown key.
    known = set()
    def declared(node):
        if isinstance(node, dict):
            known.update(node.get('properties', {}).keys())
            for child in node.values():
                declared(child)
        elif isinstance(node, list):
            for child in node:
                declared(child)
    declared(schema)
    def safe_path(path):
        return '/'.join(str(p) if isinstance(p, int) or p in known else 'unclassified' for p in path)
    return sorted({f'schema:{safe_path(error.absolute_path)}:{error.validator}'
                   for error in validator.iter_errors(value)})


def capability_errors(records: list[dict], platforms: str = 'windows10',
                      technologies: str = 'mdm') -> list[str]:
    """Reject shape-valid settings outside the exact worked offline mapping.

    Mapping qualification is deliberately separate from shape projection.
    Unknown definitions/values are review-only even when they satisfy schemas.
    """
    mapping = json.loads((ROOT / 'corrections' / 'contracts' / 'capability-map.json').read_text())
    if not isinstance(records, list) or not records:
        return ['unqualified_setting_capability']
    for record in records:
        if schema_errors('observed-setting', record):
            return ['unqualified_setting_capability']
        instance = record['settingInstance']
        value = instance.get('choiceSettingValue', {})
        matched = any(
            entry['support_status'] == 'supported_offline'
            and entry['platforms'] == platforms
            and entry['technologies'] == technologies
            and entry['setting_definition_id'] == instance['settingDefinitionId']
            and entry['instance_type'] == instance['@odata.type']
            and entry['value_type'] == value.get('@odata.type')
            and value.get('value') in entry['permitted_values']
            and entry['children'] == 'empty_only' and value.get('children') == []
            for entry in mapping['entries']
        )
        if not matched:
            return ['unqualified_setting_capability']
    return []
