"""Validation of a simulation result: the proposed JSON Schema plus the invariants the schema leaves to its reader.

The schema is the pack's `simulation-result.schema.json`, kept unchanged under contracts/. The schema's own
comment names what a consumer must also enforce: lower <= upper when upper is finite, source-reference integrity,
and no finite whole-universe upper bound while the outside-snapshot population is unknown. A null upper means
unbounded, never zero.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from .io import AppError

SCHEMA_PATH = Path(__file__).resolve().parents[1] / 'contracts' / 'simulation-result.schema.json'
_REF = re.compile(r'^(snapshot|revision|profile):\S+$')
_cache = {}


def schema():
    if 'schema' not in _cache:
        _cache['schema'] = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
    return _cache['schema']


def _invalid(reason):
    raise AppError('sim_result_invalid', 'The simulation result is not valid: ' + reason + '.')


def validate_result(doc):
    """Raise AppError unless `doc` satisfies the schema and the consumer invariants; return it otherwise."""
    from jsonschema import Draft202012Validator
    errors = sorted(Draft202012Validator(schema()).iter_errors(doc), key=lambda e: list(map(str, e.path)))
    if errors:
        first = errors[0]
        _invalid('/'.join(map(str, first.path)) + ': ' + first.message[:200])
    findings = [f['id'] for f in doc['findings']]
    cohorts = [c['cohort_id'] for c in doc['cohorts']]
    if len(set(findings)) != len(findings) or len(set(cohorts)) != len(cohorts):
        _invalid('finding and cohort identifiers must be unique')
    resolvable = set(findings) | set(doc['coverage']['unresolved_reasons'])
    unknown_outside = doc['coverage']['outside_snapshot_population'] == 'unknown'
    for cohort in doc['cohorts']:
        if cohort['upper'] is not None and cohort['lower'] > cohort['upper']:
            _invalid(f'cohort {cohort["cohort_id"]} has lower above upper')
        if unknown_outside and cohort['scope'] == 'whole_declared_universe' and cohort['upper'] is not None:
            _invalid(f'cohort {cohort["cohort_id"]} gives a finite whole-universe upper bound while the outside population is unknown')
        for ref in cohort.get('reason_refs', []):
            if ref not in resolvable:
                _invalid(f'cohort {cohort["cohort_id"]} cites {ref}, which is neither a finding nor an unresolved reason')
    for finding in doc['findings']:
        for ref in finding['source_refs']:
            if not _REF.match(ref):
                _invalid(f'finding {finding["id"]} has a malformed source reference')
    return doc
