"""JSON and plain-text renderers for a simulation result.

Both renderers validate first and refuse a result that does not satisfy the schema, so nothing is displayed that
the contract would reject. The text states every bound as a range, says "unbounded" for a null upper, never gives
a verdict of "safe", and ends by saying the result authorizes nothing.
"""
from __future__ import annotations

import json
import textwrap

from .sim_result import validate_result

_CERTAINTY_ORDER = {'definite_under_model': 0, 'possible': 1, 'unknown': 2}
_INFORMATIONAL = {'blast_radius', 'equivalent_overlap', 'defined_precedence'}
_KINDS = ('before', 'after', 'added', 'removed', 'retained')
_WORDS = {'before': 'targeted before', 'after': 'targeted after', 'added': 'newly targeted',
          'removed': 'no longer targeted', 'retained': 'retained'}
CLOSING = 'This does not authorize execution; no endpoint effect.'


def render_json(doc):
    """Canonical, indented JSON with sorted keys and a final newline."""
    validate_result(doc)
    return json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + '\n'


def _bound(cohort):
    lower, upper = cohort['lower'], cohort['upper']
    if upper is None:
        return f'{lower} to unbounded'
    return str(lower) if lower == upper else f'{lower} to {upper}'


def _verdict(doc):
    if not doc['coverage']['snapshot_complete']:
        return ('no safe verdict: the snapshot is incomplete, so a lack of findings must not be read as a lack of conflicts')
    attention = [f for f in doc['findings'] if f['kind'] not in _INFORMATIONAL or f['certainty'] != 'definite_under_model']
    if attention:
        return f'findings need review ({len(attention)} to read below)'
    return 'no findings under the model; this describes the captured universe, not the endpoints'


def _summary(cohorts, prefix, suffix):
    by_kind = {c['kind']: c for c in cohorts if c['cohort_id'] == f'{prefix}:{c["kind"]}:{suffix}'}
    return ', '.join(f'{_WORDS[k]} {_bound(by_kind[k])}' for k in _KINDS if k in by_kind)


def render_text(doc, width=100):
    """The result as lines no longer than `width`, for a person reading a terminal."""
    validate_result(doc)
    binding, coverage = doc['input_binding'], doc['coverage']
    lines = [
        f'Target simulation {doc["simulation_id"]} ({doc["evidence_class"]})',
        f'Inputs: realm {binding["realm_id"]}; snapshot {binding["snapshot_sha256"][:12]}; '
        f'desired source {binding["desired_source_sha256"][:12]}; semantics {binding["semantics_sha256"][:12]}',
        f'Coverage: {coverage["universe"].replace("_", " ")}; snapshot '
        f'{"complete" if coverage["snapshot_complete"] else "incomplete"}; outside the snapshot: '
        f'{coverage["outside_snapshot_population"].replace("_", " ")}']
    if coverage['unresolved_reasons']:
        lines.append('Unresolved: ' + '; '.join(coverage['unresolved_reasons']))
    lines.append('Verdict: ' + _verdict(doc))
    cohorts = doc['cohorts']
    policies = sorted({c['cohort_id'].split(':')[1] for c in cohorts if c['cohort_id'].startswith('policy:')})
    if policies:
        lines += ['', 'Changed policies, unique devices, lower to upper:']
        aggregate = _summary(cohorts, 'changed', 'unique_devices')
        if aggregate:
            lines.append('All changed policies: ' + aggregate)
        for pid in policies:
            lines.append(f'Policy {pid}: ' + _summary(cohorts, 'policy:' + pid, 'unique_devices'))
        whole = [c for c in cohorts if c['cohort_id'].endswith(':whole')]
        for c in sorted(whole, key=lambda c: c['cohort_id']):
            lines.append(f'Whole declared universe, {_WORDS[c["kind"]]}: {_bound(c)}')
        contexts = _summary(cohorts, 'changed', 'user_device_contexts')
        if contexts:
            lines.append('User-on-device contexts: ' + contexts)
        for ring in sorted({c['ring_id'] for c in cohorts if c.get('ring_id')}):
            parts = [f'{_WORDS[c["kind"]]} {_bound(c)}' for c in cohorts if c.get('ring_id') == ring]
            lines.append(f'Ring {ring}: ' + ', '.join(parts))
    conflicts = [c for c in cohorts if c['kind'] == 'conflict_overlap']
    for c in conflicts:
        first, second = c['cohort_id'].split(':')[1:3]
        lines.append(f'Overlap of differing values, policies {first[:8]} and {second[:8]}, in unique devices: {_bound(c)}')
    findings = sorted(doc['findings'], key=lambda f: (_CERTAINTY_ORDER[f['certainty']], f['kind'], f['id']))
    lines += ['', f'Findings ({len(findings)}):' if findings else 'Findings: none']
    for f in findings:
        lines.append(f'[{f["certainty"]}] {f["kind"]}: {f["message"]}')
        lines.append(f'  Next: {f["permitted_next_action"]}')
    lines += ['', CLOSING]
    wrapped = []
    for line in lines:
        wrapped += textwrap.wrap(line, width, subsequent_indent='  ', break_long_words=True, break_on_hyphens=False) or ['']
    return wrapped
