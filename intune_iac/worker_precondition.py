"""Fresh authenticated, lossless Graph read gates for the protected worker.

Only an existing process-held reader and captured observation can construct this
capability. It grants no mutation authority and cannot make a Graph read/write
pair atomic. Raw observations remain private and every read attempt is retained.
"""
from __future__ import annotations
from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import threading
import time

from . import observation_reader as reader_api
from .io import AppError, canonical, digest, parse_json, write_json

VERSION = 'worker-graph-precondition/1'
SEMANTICS = 'worker-graph-lossless-semantics/1'
_LIVE, _LAB, _COMPLETION = object(), object(), object()
_HASH = re.compile('[0-9a-f]{64}')
_MAX_BYTES = 2 * 1024 * 1024
_POLICY_FIELDS = frozenset(('name', 'description', 'platforms', 'technologies', 'roleScopeTagIds', 'settings'))


def _fail(code):
    raise AppError(code, 'The fresh Graph precondition, exact target, evidence or approved mutation projection could not be verified.') from None


def semantics():
    return {'version': SEMANTICS, 'policy': 'all fields retained; typed scalars and unknown fields compared exactly',
        'roleScopeTagIds': 'set of unique typed strings', 'settings': 'keyed by exact service setting id; duplicate IDs rejected',
        'assignments': 'keyed by exact service assignment id before write; targets preserved exactly',
        'choiceSettingValue.children': 'keyed by settingDefinitionId; duplicate IDs rejected',
        'other_arrays': 'ordered, including simpleSettingCollectionValue and unknown arrays',
        'null_absent_empty': 'distinct', 'raw_bytes_and_order': 'retained in each private capture',
        'intermediate_computed_fields': ['lastModifiedDateTime', 'settingCount'],
        'completed_assignments': 'exact unique target set; existing target metadata retained except observed service ID; new targets admit only known direct-assignment response fields',
        'atomic_read_write': False}


def _json(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_BYTES: _fail('precondition_payload_invalid')
    try: return parse_json(raw)
    except AppError: _fail('precondition_payload_invalid')


def _snapshot(value):
    try: return _json(canonical(value))
    except (TypeError, ValueError, RecursionError): _fail('precondition_payload_invalid')


def _keyed(rows, key):
    if type(rows) is not list or len(rows) > 1000: _fail('precondition_collection_invalid')
    identities = []
    for row in rows:
        if type(row) is not dict or type(row.get(key)) is not str or not row[key] or len(row[key]) > 512:
            _fail('precondition_collection_invalid')
        identities.append(row[key])
    if len(set(identities)) != len(identities): _fail('precondition_collection_duplicate')
    return sorted(rows, key=lambda row: row[key])


def _nested(value):
    if type(value) is list: return [_nested(item) for item in value]
    if type(value) is not dict: return value
    result = {key: _nested(item) for key, item in value.items()}
    if value.get('@odata.type') == '#microsoft.graph.deviceManagementConfigurationChoiceSettingValue' and 'children' in value:
        result['children'] = _keyed(result['children'], 'settingDefinitionId')
    return result


def _lossless(raw):
    raw = _snapshot(raw)
    if type(raw) is not dict or set(raw) != {'policy', 'settings', 'assignments'}: _fail('precondition_observation_invalid')
    policy = raw['policy']
    if (type(policy) is not dict or policy.get('platforms') != 'windows10' or policy.get('technologies') != 'mdm'
            or type(policy.get('name')) is not str or not policy['name'] or type(policy.get('id')) is not str):
        _fail('precondition_profile_unsupported')
    tags = policy.get('roleScopeTagIds')
    if type(tags) is not list or not tags or any(type(tag) is not str or not tag for tag in tags) or len(set(tags)) != len(tags):
        _fail('precondition_collection_invalid')
    result = _nested(raw); result['policy']['roleScopeTagIds'] = sorted(tags)
    result['settings'] = _keyed(result['settings'], 'id')
    result['assignments'] = _keyed(result['assignments'], 'id')
    if not result['settings'] or type(policy.get('settingCount')) is not int or policy['settingCount'] != len(result['settings']):
        _fail('precondition_settings_incomplete')
    targets = []
    for row in result['assignments']:
        target = row.get('target')
        if type(target) is not dict or type(target.get('@odata.type')) is not str: _fail('precondition_assignment_invalid')
        targets.append(digest(target))
    if len(set(targets)) != len(targets): _fail('precondition_collection_duplicate')
    return result


def _timestamp(value):
    if type(value) is not str or len(value) > 64: _fail('precondition_timestamp_invalid')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None: raise ValueError()
        return parsed.timestamp()
    except (ValueError, OverflowError): _fail('precondition_timestamp_invalid')


def _validated_capture(captured, reader, *, max_age):
    if type(captured) is not reader_api.CapturedObservation: _fail('precondition_capture_capability_required')
    batch, source = captured.verified(); current = reader.evidence()
    if (captured.cancelled or canonical(source['identity']) != canonical(current['identity'])
            or source['identity_observation_sha256'] != current['identity_observation_sha256']
            or source['evidence_class'] != current['evidence_class']
            or source['source_authenticity_verified'] != current['source_authenticity_verified']):
        _fail('precondition_reader_binding')
    if (type(batch.get('observed_at')) not in (int, float) or not 0 <= time.time() - batch['observed_at'] <= max_age
            or batch['tenant_id'] != current['identity']['tenant_id']
            or batch['object_id'] not in current['identity']['object_ids']):
        _fail('precondition_observation_stale')
    coverage = batch.get('collections')
    if (type(coverage) is not list or len(coverage) != 3
            or {row.get('kind') for row in coverage} != {'policies', 'settings', 'assignments'}
            or any(row.get('coverage') != 'complete' or row.get('reason') is not None or row.get('page_count', 0) < 1 for row in coverage)):
        _fail('precondition_coverage_incomplete')
    raw = batch['source']['raw_observed']; normalized = _lossless(raw)
    if normalized['policy']['id'] != batch['object_id']: _fail('precondition_object_mismatch')
    return batch, source, normalized


class _Precondition:
    __slots__ = ('_reader', '_preimage', '_raw', '_normalized', '_policy', '_assignments', '_bodies',
        '_binding', '_binding_digest', '_root', '_pid', '_phase', '_closed', '_lock', '_attempts', '_timeout', '_completed_count',
        'execution_binding_sha256', 'profile', 'assurance')

    def __init__(self, seal, reader, preimage, execution_binding_sha256, approved_policy_body, approved_assignment_body, evidence_root, max_read_seconds):
        live = type(self) is LiveGraphPrecondition and seal is _LIVE
        lab = type(self) is LaboratoryGraphPrecondition and seal is _LAB
        if not (live or lab): _fail('precondition_constructor_forbidden')
        expected_reader = reader_api.LiveGraphReader if live else reader_api.LaboratoryGraphReader
        if type(reader) is not expected_reader: _fail('precondition_reader_capability_required')
        if type(execution_binding_sha256) is not str or not _HASH.fullmatch(execution_binding_sha256): _fail('precondition_execution_binding')
        if type(max_read_seconds) is not int or not 1 <= max_read_seconds <= 30: _fail('precondition_read_limit')
        batch, source, normalized = _validated_capture(preimage, reader, max_age=300)
        policy, assignments = _json(approved_policy_body), _json(approved_assignment_body)
        if (type(policy) is not dict or set(policy) != _POLICY_FIELDS or policy.get('platforms') != 'windows10'
                or policy.get('technologies') != 'mdm' or type(policy.get('name')) is not str or not policy['name']
                or policy.get('description') is not None and type(policy['description']) is not str
                or type(assignments) is not dict or set(assignments) != {'assignments'}
                or type(assignments['assignments']) is not list or len(assignments['assignments']) > 1000
                or any(type(row) is not dict or set(row) != {'target'} or type(row['target']) is not dict for row in assignments['assignments'])):
            _fail('precondition_projection_invalid')
        expected = _snapshot(batch['source']['raw_observed'])
        expected['policy'].update({key: value for key, value in policy.items() if key != 'settings'})
        expected['settings'] = policy['settings']; expected['policy']['settingCount'] = len(policy['settings']) if type(policy['settings']) is list else None
        _lossless(expected)
        keys = [digest(row['target']) for row in assignments['assignments']]
        if len(set(keys)) != len(keys): _fail('precondition_collection_duplicate')
        root = Path(evidence_root).absolute()
        if '..' in root.parts or any(path.is_symlink() for path in (root, *root.parents)): _fail('precondition_evidence_path')
        try: root.mkdir(mode=0o700)
        except OSError: _fail('precondition_evidence_path')
        self._reader, self._preimage = reader, preimage
        self._raw, self._normalized = _snapshot(batch['source']['raw_observed']), normalized
        self._policy, self._assignments = policy, assignments
        self._bodies = {'policy': hashlib.sha256(approved_policy_body).hexdigest(), 'assignments': hashlib.sha256(approved_assignment_body).hexdigest()}
        self.execution_binding_sha256 = execution_binding_sha256
        self.profile = 'azure_public_pilot' if live else 'laboratory_native_protocol'
        self.assurance = 'authenticated_graph_precondition' if live else 'laboratory_recorded_graph_precondition'
        self._binding = {'schema_version': VERSION, 'semantics': semantics(), 'profile': self.profile,
            'assurance': self.assurance, 'execution_binding_sha256': execution_binding_sha256,
            'identity': source['identity'], 'identity_observation_sha256': source['identity_observation_sha256'],
            'tenant_id': batch['tenant_id'], 'object_id': batch['object_id'],
            'preimage_capture_sha256': batch['capture_sha256'], 'preimage_raw_sha256': digest(self._raw),
            'preimage_semantic_sha256': digest(self._normalized),
            'approved_projection_sha256': digest({'policy': self._policy, 'assignments': self._assignments}),
            'approved_body_sha256': self._bodies.copy(), 'max_read_seconds': max_read_seconds,
            'residual_race': 'Graph reads and subsequent policy/assignment writes are not atomic; no If-Match or tenant writer fence is established.',
            'execution_authorized': False, 'platform_qualified': False}
        self._binding_digest = digest(self._binding)
        self._root, self._pid, self._phase, self._closed = root, os.getpid(), 'initial', False
        self._lock, self._attempts, self._timeout = threading.RLock(), [], max_read_seconds
        self._completed_count = 0
        write_json(root / 'binding.json', self._binding)

    def __repr__(self): return '<' + type(self).__name__ + ' redacted>'
    def __reduce_ex__(self, protocol): raise TypeError('Graph precondition capabilities cannot be serialized.')

    def _fresh(self):
        if self._closed or self._pid != os.getpid(): _fail('precondition_closed')
        if (digest(self._binding) != self._binding_digest or self.execution_binding_sha256 != self._binding['execution_binding_sha256']
                or self.profile != self._binding['profile'] or self.assurance != self._binding['assurance']
                or self._timeout != self._binding['max_read_seconds']
                or digest(self._raw) != self._binding['preimage_raw_sha256']
                or digest(self._normalized) != self._binding['preimage_semantic_sha256']
                or self._bodies != self._binding['approved_body_sha256']
                or digest({'policy': self._policy, 'assignments': self._assignments}) != self._binding['approved_projection_sha256']):
            _fail('precondition_binding_changed')
        self._reader.evidence()
        self._preimage.verified()

    def binding(self):
        self._fresh(); return _snapshot(self._binding)

    def stage_for_request(self, method, path, body):
        self._fresh(); oid = self._binding['object_id']
        if method == 'PUT' and path == "/beta/deviceManagement/configurationPolicies('" + oid + "')": stage = 'policy'
        elif method == 'POST' and path == '/beta/deviceManagement/configurationPolicies/' + oid + '/assign': stage = 'assignments'
        else: _fail('precondition_request_target')
        if type(body) is not bytes or hashlib.sha256(body).hexdigest() != self._bodies[stage]: _fail('precondition_request_substitution')
        return stage

    def _observe(self, name):
        captured = self._reader.capture(self._binding['object_id'], self._root / name, max_elapsed_seconds=self._timeout)
        batch, source, normalized = _validated_capture(captured, self._reader, max_age=self._timeout)
        if batch['object_id'] != self._binding['object_id']: _fail('precondition_object_mismatch')
        return captured, batch, normalized

    def _intermediate(self, actual):
        expected = _snapshot(self._raw)
        expected['policy'].update({key: value for key, value in self._policy.items() if key != 'settings'})
        expected['settings'] = self._policy['settings']; expected['policy']['settingCount'] = len(self._policy['settings'])
        previous = self._raw['policy'].get('lastModifiedDateTime')
        observed = actual['policy'].get('lastModifiedDateTime')
        if previous is not None or observed is not None:
            now = _timestamp(observed)
            if previous is not None and now < _timestamp(previous) or now > time.time() + 60: _fail('precondition_timestamp_invalid')
            expected['policy']['lastModifiedDateTime'] = observed
        return _lossless(expected)

    def check_before_mutation(self, *, stage, request_body):
        with self._lock:
            self._fresh()
            if stage not in ('policy', 'assignments') or type(request_body) is not bytes or hashlib.sha256(request_body).hexdigest() != self._bodies[stage]:
                _fail('precondition_request_substitution')
            if self._phase != ('initial' if stage == 'policy' else 'policy_checked'): _fail('precondition_phase_invalid')
            self._phase = 'checking'; attempt = {'stage': stage, 'status': 'started', 'capture': str(self._root / stage)}
            self._attempts.append(attempt); write_json(self._root / 'attempts.json', self._attempts)
            try:
                _, batch, actual = self._observe(stage)
                expected = self._normalized if stage == 'policy' else self._intermediate(actual)
                if canonical(actual) != canonical(expected): _fail('precondition_observed_change')
                self._fresh()
                attempt.update(status='matched', capture_sha256=batch['capture_sha256'], observed_at=batch['observed_at'])
                write_json(self._root / 'attempts.json', self._attempts)
                self._phase = stage + '_checked'
            except BaseException as error:
                self._phase = 'failed'; attempt.update(status='failed', error_code=getattr(error, 'code', type(error).__name__))
                try: write_json(self._root / 'attempts.json', self._attempts)
                except Exception: pass
                raise

    def capture_completed(self):
        """Return fresh sealed service evidence only after exact desired parity.

        This observes service-assigned assignment IDs/metadata without pretending
        they were declared by the assign request. Every approved target must occur
        exactly once; all policy/settings fields use the same lossless semantics.
        It does not attest device effectiveness or make any mutation successful.
        """
        return self._capture_completed(recovery=False)

    def _capture_completed(self, *, recovery):
        with self._lock:
            self._fresh()
            if self._phase != 'assignments_checked' and not (recovery and self._phase == 'completed'):
                _fail('precondition_phase_invalid')
            self._phase = 'checking'
            self._completed_count += 1
            name = 'completed' if self._completed_count == 1 else 'completed-' + str(self._completed_count).zfill(2)
            attempt = {'stage': 'completed', 'status': 'started', 'capture': str(self._root / name)}
            self._attempts.append(attempt); write_json(self._root / 'attempts.json', self._attempts)
            try:
                captured, batch, actual = self._observe(name)
                expected = self._intermediate(actual)
                expected_targets = sorted(canonical(row['target']) for row in self._assignments['assignments'])
                actual_targets = sorted(canonical(row['target']) for row in actual['assignments'])
                if (canonical(actual['policy']) != canonical(expected['policy'])
                        or canonical(actual['settings']) != canonical(expected['settings'])
                        or actual_targets != expected_targets):
                    _fail('precondition_observed_change')
                previous_assignments = {digest(row['target']): row for row in self._raw['assignments']}
                for row in actual['assignments']:
                    previous = previous_assignments.get(digest(row['target']))
                    metadata = {key: value for key, value in row.items() if key != 'id'}
                    if previous is not None:
                        if canonical(metadata) != canonical({key: value for key, value in previous.items() if key != 'id'}):
                            _fail('precondition_observed_change')
                    elif (set(row) - {'id', 'target', '@odata.type', 'source', 'sourceId'}
                            or row.get('@odata.type', '#microsoft.graph.deviceManagementConfigurationPolicyAssignment') != '#microsoft.graph.deviceManagementConfigurationPolicyAssignment'
                            or row.get('source') != 'direct' or 'sourceId' not in row or row['sourceId'] not in (None, '')):
                        _fail('precondition_assignment_metadata_unsupported')
                self._fresh()
                attempt.update(status='matched', capture_sha256=batch['capture_sha256'], observed_at=batch['observed_at'])
                write_json(self._root / 'attempts.json', self._attempts)
                self._phase = 'completed'
                return captured
            except BaseException as error:
                self._phase = 'failed'; attempt.update(status='failed', error_code=getattr(error, 'code', type(error).__name__))
                try: write_json(self._root / 'attempts.json', self._attempts)
                except Exception: pass
                raise

    def completion(self):
        captured = self._capture_completed(recovery=True)
        kind = LiveGraphCompletion if type(self) is LiveGraphPrecondition else LaboratoryGraphCompletion
        return kind(_COMPLETION, self, captured)

    def close(self):
        with self._lock: self._closed = True


class LiveGraphPrecondition(_Precondition):
    __slots__ = ()


class LaboratoryGraphPrecondition(_Precondition):
    __slots__ = ()


class _GraphCompletion:
    __slots__ = ('_gate', '_capture', '_facts', '_digest', '_pid')

    def __init__(self, seal, gate, captured):
        if (seal is not _COMPLETION
                or not ((type(self) is LiveGraphCompletion and type(gate) is LiveGraphPrecondition)
                    or (type(self) is LaboratoryGraphCompletion and type(gate) is LaboratoryGraphPrecondition))
                or gate._phase != 'completed'):
            _fail('precondition_completion_constructor_forbidden')
        gate._fresh()
        batch, _, _ = _validated_capture(captured, gate._reader, max_age=gate._timeout)
        self._gate, self._capture, self._pid = gate, captured, os.getpid()
        self._facts = {'execution_binding_sha256': gate.execution_binding_sha256,
            'precondition_binding_sha256': gate._binding_digest,
            'approved_projection_sha256': gate._binding['approved_projection_sha256'],
            'capture_sha256': batch['capture_sha256'], 'tenant_id': batch['tenant_id'], 'object_id': batch['object_id'],
            'profile': gate.profile, 'assurance': gate.assurance, 'observed_at': batch['observed_at']}
        self._digest = digest(self._facts)

    def __repr__(self): return '<' + type(self).__name__ + ' redacted>'
    def __reduce_ex__(self, protocol): raise TypeError('Graph completion capabilities cannot be serialized.')

    def verified(self):
        self._gate._fresh()
        if self._pid != os.getpid() or self._gate._phase != 'completed' or digest(self._facts) != self._digest:
            _fail('precondition_completion_changed')
        batch, _, _ = _validated_capture(self._capture, self._gate._reader, max_age=self._gate._timeout)
        if (self._facts['execution_binding_sha256'] != self._gate.execution_binding_sha256
                or self._facts['precondition_binding_sha256'] != self._gate._binding_digest
                or self._facts['capture_sha256'] != batch['capture_sha256']):
            _fail('precondition_completion_changed')
        return {**_snapshot(self._facts), 'capture': self._capture}


class LiveGraphCompletion(_GraphCompletion):
    __slots__ = ()


class LaboratoryGraphCompletion(_GraphCompletion):
    __slots__ = ()


def create_live_precondition(*, reader, preimage, execution_binding_sha256, approved_policy_body, approved_assignment_body, evidence_root, max_read_seconds=30):
    return LiveGraphPrecondition(_LIVE, reader, preimage, execution_binding_sha256, approved_policy_body, approved_assignment_body, evidence_root, max_read_seconds)


def create_laboratory_precondition(*, reader, preimage, execution_binding_sha256, approved_policy_body, approved_assignment_body, evidence_root, max_read_seconds=30):
    return LaboratoryGraphPrecondition(_LAB, reader, preimage, execution_binding_sha256, approved_policy_body, approved_assignment_body, evidence_root, max_read_seconds)
