"""Sealed, bounded declared-scope ownership prerequisite for native import.

This observes actual local native state files and the existing workbench index.
It never upgrades an imported report into authenticated remote ownership. The
first execution profile permits exactly one completely declared backend; the
runtime must separately authenticate that backend and its exact empty bytes.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import time

from intune_iac import workbench_views as views
from intune_iac.workbench_store import WorkbenchStore
from intune_iac.workbench_provenance import _read
from intune_iac.io import AppError, canonical, digest, parse_json

_SEAL = object()


def _fail(code):
    raise AppError(code, 'A complete current declared-scope ownership search was not established for native adoption.') from None


def _copy(value):
    return parse_json(canonical(value))


def _observe(store, object_id, scope, baseline_sha256):
    if type(store) is not WorkbenchStore:
        _fail('adoption_ownership_store_required')
    views._identity(object_id); scope = views._scope(scope)
    rows = store.artifacts(kind='ownership_index')
    if not rows: _fail('adoption_ownership_missing')
    row = max(rows, key=lambda item: item['sequence']); data = row['data']
    if data.get('evidence_class') != 'local_native_state_file_scan':
        _fail('adoption_ownership_native_scan_required')
    result = views._ownership_result(row, object_id, scope, time.time())
    if (result['status'] != 'no_ownership_found_in_declared_scope'
            or not result['fresh'] or not result['declared_scope_complete']):
        _fail('adoption_ownership_stale_incomplete_or_owned')
    document = data['document']
    # Every indexed declaration is considered; callers cannot select one source
    # out of a larger declared estate to make remote coverage appear complete.
    if document['declared_scopes'] != [scope] or len(document['sources']) != 1:
        _fail('adoption_ownership_multibackend_unqualified')
    declarations = store.artifacts(kind='repository_intent')
    known = [item['data']['scope'] for item in declarations]
    if any(item != scope for item in known):
        _fail('adoption_ownership_unsearched_repository_scope')
    source = data.get('source'); evidence = data.get('state_evidence')
    if type(source) is not dict or type(evidence) is not list or len(evidence) != 1:
        _fail('adoption_ownership_source_missing')
    raw = _read(Path(source['path']))
    if len(raw) != source['bytes'] or hashlib.sha256(raw).hexdigest() != source['sha256']:
        _fail('adoption_ownership_source_changed')
    scan = parse_json(raw)
    expected = {'schema_version': 'workbench-ownership-scan/1', 'tenant_id': store.tenant_id,
        'max_age_seconds': document['max_age_seconds'],
        'sources': [{'scope': scope, 'state_path': evidence[0]['state_path']}]}
    if scan != expected: _fail('adoption_ownership_declaration_changed')
    detail = evidence[0]
    if (detail.get('scope') != scope or detail.get('issues') != []
            or detail.get('backend_authenticated') is not False
            or detail.get('tenant_binding') != 'caller_declared_scope_only'):
        _fail('adoption_ownership_scan_invalid')
    state_raw = _read(Path(detail['state_path'])); state = parse_json(state_raw)
    source_state = detail.get('source', {})
    if (source_state.get('path') != detail['state_path'] or source_state.get('bytes') != len(state_raw)
            or source_state.get('sha256') != hashlib.sha256(state_raw).hexdigest()
            or source_state.get('sha256') != baseline_sha256
            or type(state) is not dict or state.get('version') != 4
            or type(state.get('serial')) is not int or state['serial'] < 0
            or type(state.get('lineage')) is not str or not state['lineage']
            or state.get('resources') != [] or state.get('outputs') != {}):
        _fail('adoption_ownership_baseline_changed_or_not_empty')
    if detail.get('state_revision') != {'lineage': state['lineage'], 'serial': state['serial'], 'sha256': baseline_sha256}:
        _fail('adoption_ownership_revision_changed')
    if document['sources'][0] != {'scope': scope, 'coverage': 'complete',
            'observed_at': detail['read_at'], 'claims': []}:
        _fail('adoption_ownership_claims_changed')
    return {'schema_version': 'native-adoption-ownership/1', 'tenant_id': store.tenant_id,
        'object_id': object_id, 'selected_scope': scope, 'declared_scopes': [scope],
        'artifact_id': row['artifact_id'], 'artifact_sequence': row['sequence'],
        'artifact_sha256': digest(row), 'repository_declarations_sha256': digest(declarations),
        'scan_source': source, 'state_evidence': evidence,
        'baseline_sha256': baseline_sha256, 'result': 'no_owner_in_completely_searched_declared_scope',
        'global_tenant_ownership_established': False, 'backend_authenticated': False,
        'sole_organizational_writer_approval': 'required_separately',
        'external_writer_absence_established': False, 'execution_authorized': False}


class OwnershipAdmission:
    __slots__ = ('_store', '_object', '_scope', '_baseline', '_facts', '_sha', '_pid')
    def __init__(self, seal, store, object_id, scope, baseline_sha256):
        if seal is not _SEAL or type(self) is not OwnershipAdmission:
            _fail('adoption_ownership_constructor_forbidden')
        self._store, self._object, self._scope, self._baseline = store, object_id, _copy(scope), baseline_sha256
        self._facts = _observe(store, object_id, scope, baseline_sha256)
        self._sha, self._pid = digest(self._facts), os.getpid()
    def __reduce_ex__(self, protocol): raise TypeError('Ownership admission cannot be serialized.')
    def __repr__(self): return '<OwnershipAdmission local declared scope only>'
    def binding(self):
        self.check()
        return _copy(self._facts)
    def check(self):
        if (self._pid != os.getpid() or digest(self._facts) != self._sha
                or _observe(self._store, self._object, self._scope, self._baseline) != self._facts):
            _fail('adoption_ownership_changed')


def admit_ownership(store, *, object_id, selected_scope, baseline_sha256):
    """Mint only after re-reading the latest scan's actual files and all scopes."""
    return OwnershipAdmission(_SEAL, store, object_id, selected_scope, baseline_sha256)
