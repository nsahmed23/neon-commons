"""Bounded imported device/workflow evidence; no collectors or remote authority.

Stage arithmetic delegates to the existing reference evidence engine. Imported
claims stay caller asserted, with exact file provenance and explicit local
identity bindings. Configuration acceptance never becomes endpoint success.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import UUID

from reference.core import evidence_summary
from reference.validation import schema_errors
from .io import AppError, parse_json, read_bytes

STAGES = ('object', 'assignment', 'cohort', 'receipt', 'execution', 'effective_state', 'outcome')
MAX_INPUT = 2 * 1024 * 1024


def _fail(code):
    raise AppError(code, 'Imported Workbench evidence is invalid, unbound, incomplete, or outside the supported local profile.')


def _time(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None: _fail('workbench_evidence_time')
        return stamp.timestamp()
    except (ValueError, TypeError, AttributeError): _fail('workbench_evidence_time')


def _source(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)): _fail('workbench_evidence_path')
    raw = read_bytes(path)
    if len(raw) > MAX_INPUT: _fail('workbench_evidence_limit')
    return parse_json(raw), str(path), hashlib.sha256(raw).hexdigest()


def _identity(store, value):
    if type(value) is not dict: _fail('workbench_evidence_shape')
    for field in ('tenant_id', 'object_id'):
        try:
            if type(value.get(field)) is not str or str(UUID(value[field])) != value[field]: _fail('workbench_evidence_identity')
        except ValueError: _fail('workbench_evidence_identity')
    if value['tenant_id'] != store.tenant_id: _fail('workbench_wrong_tenant')
    observed = store.inspect(value['object_id'])
    if observed['tenant_id'] != value['tenant_id']: _fail('workbench_wrong_tenant')
    return value['object_id']


def _validate(document):
    if schema_errors('evidence', document): _fail('workbench_device_evidence_schema')
    cohort = document['cohort']; rows = document['rows']
    if any(len(cohort[key]) > 10000 for key in ('eligible_ids', 'targeted_ids', 'excluded_ids')) or len(rows) > 50000:
        _fail('workbench_evidence_limit')
    if len({row['id'] for row in rows}) != len(rows): _fail('workbench_device_duplicate_evidence')
    if any(row['synthetic'] != document['synthetic'] for row in rows): _fail('workbench_device_evidence_class')
    if any(not value or len(value) > 256 for key in ('eligible_ids', 'targeted_ids', 'excluded_ids') for value in cohort[key]):
        _fail('workbench_device_identity')
    return document


def import_device_evidence(store, path):
    value, source_path, source_sha = _source(path)
    object_id = _identity(store, value)
    if set(value) != {'schema_version', 'tenant_id', 'object_id', 'evidence'} or value['schema_version'] != 'workbench-device-evidence/1':
        _fail('workbench_device_envelope')
    document = _validate(value['evidence'])
    data = {**value, 'source_path': source_path, 'source_sha256': source_sha,
            'evidence_class': 'synthetic' if document['synthetic'] else 'caller_asserted',
            'external_execution_verified': False, 'cloud_authority': False}
    return store.record_artifact('device_evidence', object_id, data)


def summarize_evidence(document, *, now=None):
    document = _validate(document)
    if now is not None and type(now) not in (int, float): _fail('workbench_evidence_time')
    now = datetime.now(timezone.utc).timestamp() if now is None else float(now)
    if now != now or abs(now) == float('inf'): _fail('workbench_evidence_time')
    targeted = set(document['cohort']['targeted_ids']); eligible = set(document['cohort']['eligible_ids'])
    excluded = set(document['cohort']['excluded_ids']); conflict_members = targeted & excluded | targeted - eligible
    indexed = {}
    for row in document['rows']:
        indexed.setdefault((row['stage'], row['device_id']), []).append((_time(row['observed_at']), row))
    capture = document['capture']; incomplete = capture['truncated'] or bool(capture['access_errors'])
    as_of = _time(document['as_of']); maximum_age = document['freshness_seconds']
    result = {'evidence_class': 'synthetic' if document['synthetic'] else 'caller_asserted',
              'as_of': document['as_of'], 'cohort_version': document['cohort']['version'],
              'eligible': len(eligible), 'targeted': len(targeted), 'excluded': len(excluded),
              'membership_conflicts': sorted(conflict_members), 'membership_assurance': 'caller_asserted',
              'out_of_cohort_devices': sorted({r['device_id'] for r in document['rows']} - targeted),
              'capture': capture, 'stages': {}, 'endpoint_health': 'unknown', 'endpoint_outcome': 'unknown',
              'configuration_parity': 'unknown', 'service_acceptance': 'unknown',
              'rollout_ready': False, 'rollout_approval': 'unknown', 'cloud_authority': False,
              'qualification': 'Imported stage evidence and arithmetic; no authenticated device effectiveness or rollout approval.'}
    for stage in STAGES:
        classified = []; counts = {name: 0 for name in ('conflicting', 'access_denied', 'partial', 'stale', 'future', 'missing', 'membership_conflicts')}
        devices = []
        for device in sorted(targeted):
            rows = indexed.get((stage, device), [])
            if not rows:
                counts['missing'] += 1; devices.append({'device_id': device, 'status': 'unknown', 'reason': 'missing'}); continue
            newest = max(stamp for stamp, row in rows)
            latest = [row for stamp, row in rows if stamp == newest]
            statuses = {row['status'] for row in latest}; coverage = {row['coverage'] for row in latest}
            fresh = now - newest <= maximum_age and now - as_of <= maximum_age
            reason = None
            if device in conflict_members: reason = 'membership_conflicts'
            elif 'access_denied' in coverage: reason = 'access_denied'
            elif incomplete or coverage != {'complete'}: reason = 'partial'
            elif newest > now or as_of > now or newest > as_of: reason = 'future'
            elif not fresh: reason = 'stale'
            conflicting = len(statuses) != 1 or 'conflicting' in statuses
            if conflicting: counts['conflicting'] += 1
            if reason: counts[reason] += 1
            status = next(iter(statuses)) if not conflicting else 'unknown'
            classified.append({'id': device, 'status': status if reason is None else 'unknown', 'fresh': reason is None})
            devices.append({'device_id': device, 'status': 'unknown' if reason else 'conflicting' if conflicting else status,
                            'reported_status': 'conflicting' if conflicting else status,
                            'reason': reason, 'observed_at': latest[0]['observed_at'], 'evidence_ids': [r['id'] for r in latest]})
        summary = evidence_summary(len(targeted), classified)
        summary.update(counts, reporting_success_percent=None if summary['success_per_reporter'] is None else 100 * summary['success_per_reporter'],
                       targeted_success_percent=None if summary['success_per_target'] is None else 100 * summary['success_per_target'],
                       devices=devices)
        result['stages'][stage] = summary
    return result


def device_health(store, object_id, *, now=None):
    store.inspect(object_id)
    rows = store.artifacts(kind='device_evidence', object_id=object_id)
    if not rows:
        return {'tenant_id': store.tenant_id, 'object_id': object_id, 'evidence_class': 'unknown',
                'stages': {stage: {'targeted': None, 'reporting': None, 'successful': None, 'unknown': None} for stage in STAGES},
                'endpoint_health': 'unknown', 'endpoint_outcome': 'unknown', 'rollout_ready': False,
                'rollout_approval': 'unknown', 'cloud_authority': False, 'reason': 'No policy-bound device evidence was imported.'}
    latest = max(rows, key=lambda row: row['sequence'])
    result = summarize_evidence(latest['data']['evidence'], now=now)
    result.update(tenant_id=store.tenant_id, object_id=object_id, artifact_id=latest['artifact_id'],
                  source_sha256=latest['data']['source_sha256'], source_path=latest['data']['source_path'])
    return result


def _url(value):
    if type(value) is not str or not 1 <= len(value) <= 4096: _fail('workbench_workflow_url')
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or any(ord(c) < 33 for c in value):
            _fail('workbench_workflow_url')
    except ValueError: _fail('workbench_workflow_url')
    return value


def import_workflow_run(store, path):
    value, source_path, source_sha = _source(path)
    object_id = _identity(store, value)
    required = {'schema_version', 'tenant_id', 'object_id', 'run_url', 'repository_revision', 'run_id', 'status', 'observed_at'}
    optional = {'workflow', 'repository_url', 'artifact_sha256', 'related_operation', 'observed_after'}
    if not required <= set(value) or set(value) - required - optional or value['schema_version'] != 'workbench-workflow-run/1': _fail('workbench_workflow_shape')
    _url(value['run_url'])
    if 'repository_url' in value: _url(value['repository_url'])
    if type(value['repository_revision']) is not str or not re.fullmatch('[0-9a-f]{40}', value['repository_revision']): _fail('workbench_workflow_revision')
    if 'artifact_sha256' in value and (type(value['artifact_sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', value['artifact_sha256'])): _fail('workbench_workflow_digest')
    if type(value['run_id']) is not str or not 1 <= len(value['run_id']) <= 256 or value['status'] not in ('pending', 'success', 'failure', 'cancelled', 'unknown'): _fail('workbench_workflow_shape')
    if 'workflow' in value and (type(value['workflow']) is not str or len(value['workflow']) > 512): _fail('workbench_workflow_shape')
    observed_at = _time(value['observed_at']); relationships = []
    if 'related_operation' in value:
        if not any(row['operation_id'] == value['related_operation'] for row in store.operations(object_id=object_id)):
            _fail('workbench_workflow_operation_unknown')
        relationships.append({'relation': 'related_operation', 'target_id': value['related_operation'],
                              'assertion_class': 'caller_asserted_relationship', 'local_target_verified': True})
    if 'observed_after' in value:
        matches = [row for row in store.history(object_id) if row['snapshot_id'] == value['observed_after'] and _time(row['observed_at']) <= observed_at]
        if not matches: _fail('workbench_workflow_snapshot_unknown')
        relationships.append({'relation': 'observed_after', 'target_id': value['observed_after'],
                              'assertion_class': 'caller_asserted_time_order', 'local_target_verified': True})
    data = {**value, 'relationships': relationships, 'source_path': source_path, 'source_sha256': source_sha,
            'evidence_class': 'caller_asserted', 'external_execution_verified': False, 'cloud_authority': False}
    return store.record_artifact('workflow_run', object_id, data)


def workflow_lineage(store, object_id):
    store.inspect(object_id)
    rows = store.artifacts(kind='workflow_run', object_id=object_id)
    return {'tenant_id': store.tenant_id, 'object_id': object_id, 'runs': rows,
            'evidence_class': 'caller_asserted', 'external_execution_verified': False, 'cloud_authority': False,
            'qualification': 'Imported links and statuses are inert claims; local relationship targets are identity-matched, not remote execution proof.'}
