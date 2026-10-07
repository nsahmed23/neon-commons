"""Closed completion of two observed Settings Catalog computed state fields.

This is separate from the frozen fully-known state projection. It never grants
write authority, invents computed values or changes provider state serialization.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
import re
import time

from .azure_backend import StateRevision, NativeStateWriteContract
from .io import AppError, canonical, digest, parse_json
from .observation_reader import CapturedObservation
from . import worker_precondition as wp

RESOURCE = 'microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json'
PROVIDER = 'registry.terraform.io/deploymenttheory/microsoft365'
COMPUTED = frozenset({'settings_count', 'last_modified_date_time'})
_MAX = 16 * 1024 * 1024
_HASH = re.compile(r'^[0-9a-f]{64}$')


def _fail(code):
    raise AppError(code, 'The generated native state could not be matched to its approved plan and independent completed observation.') from None


def _capture(value):
    if type(value) is not CapturedObservation: _fail('worker_state_sealed_capture_required')
    batch, source = value.verified()
    if (value.cancelled or batch['status'] not in ('complete', 'unsupported') or
            any(c['coverage'] != 'complete' or c['reason'] is not None or c['page_count'] < 1 for c in batch['collections']) or
            source['evidence_class'] not in ('graph_authenticated_observation', 'graph_reader_laboratory')):
        _fail('worker_state_capture_incomplete')
    return batch, source


def _checks(plan):
    checks = plan.get('checks', [])
    if type(checks) is not list or len(checks) > 32: _fail('worker_state_check_unsupported')
    result = []
    for check in checks:
        if (type(check) is not dict or set(check) != {'address', 'status', 'instances'} or check['status'] != 'pass' or
                type(check['address']) is not dict or set(check['address']) != {'kind', 'name', 'to_display'} or
                check['address']['kind'] != 'var' or type(check['address']['name']) is not str or
                not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', check['address']['name'])):
            _fail('worker_state_check_unsupported')
        address = 'var.' + check['address']['name']
        if check['address']['to_display'] != address or check['instances'] != [{'address': {'to_display': address}, 'status': 'pass'}]:
            _fail('worker_state_check_unsupported')
        result.append({'object_kind': 'var', 'config_addr': address, 'status': 'pass',
                       'objects': [{'object_addr': address, 'status': 'pass'}]})
    return result or None


class ComputedNativeStateWriteContract:
    """One existing pinned resource, two observation-bound computed attributes."""
    def __init__(self, *, baseline_raw, plan_json_raw, saved_plan_sha256,
                 execution_binding_sha256, preimage, precondition):
        if any(type(v) is not bytes or not 0 < len(v) <= _MAX for v in (baseline_raw, plan_json_raw)) or any(
                type(v) is not str or not _HASH.fullmatch(v) for v in (saved_plan_sha256, execution_binding_sha256)):
            _fail('worker_state_contract_invalid')
        batch, source = _capture(preimage)
        if type(precondition) not in (wp.LiveGraphPrecondition, wp.LaboratoryGraphPrecondition): _fail('worker_state_precondition_required')
        gate_binding = precondition.binding()
        if (gate_binding['execution_binding_sha256'] != execution_binding_sha256 or
                gate_binding['preimage_capture_sha256'] != batch['capture_sha256'] or
                gate_binding['identity'] != source['identity']): _fail('worker_state_precondition_binding')
        before, plan = parse_json(baseline_raw), parse_json(plan_json_raw)
        StateRevision.observe(baseline_raw, etag='"input-content-only"')
        if (type(before) is not dict or type(plan) is not dict or type(before.get('resources')) is not list or
                before.get('serial', 2147483647) >= 2147483647 or type(plan.get('resource_changes')) is not list or set(before) != {'version', 'terraform_version', 'serial', 'lineage', 'outputs', 'resources', 'check_results'} or
                before['terraform_version'] != '1.13.1' or before['outputs'] != {} or len(before['resources']) != 1 or
                plan.get('format_version') != '1.2' or plan.get('terraform_version') != '1.13.1' or plan.get('errored') is not False or
                plan.get('resource_drift') not in (None, []) or plan.get('deferred_changes') not in (None, []) or
                plan.get('output_changes') not in (None, {}) or len(plan.get('resource_changes', [])) != 1):
            _fail('worker_state_profile_unsupported')
        resource = before['resources'][0]
        if (type(resource) is not dict or type(resource.get('instances')) is not list or set(resource) != {'mode', 'type', 'name', 'provider', 'instances'} or resource['mode'] != 'managed' or
                resource['type'] != RESOURCE or resource['provider'] != 'provider["' + PROVIDER + '"]' or
                type(resource['name']) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', resource['name']) or
                len(resource['instances']) != 1):
            _fail('worker_state_profile_unsupported')
        instance = resource['instances'][0]
        if (type(instance) is not dict or set(instance) - {'schema_version', 'attributes', 'sensitive_attributes', 'identity', 'identity_schema_version', 'private', 'dependencies'} or
                instance.get('schema_version') != 0 or type(instance.get('schema_version')) is not int or
                instance.get('identity_schema_version') != 0 or type(instance.get('identity_schema_version')) is not int or
                type(instance.get('attributes')) is not dict or instance.get('identity') != {'id': batch['object_id']} or
                instance['attributes'].get('id') != batch['object_id']):
            _fail('worker_state_profile_unsupported')
        address = RESOURCE + '.' + resource['name']; change = plan['resource_changes'][0]
        if (type(change) is not dict or type(change.get('change')) is not dict or change.get('address') != address or change.get('mode') != 'managed' or change.get('type') != RESOURCE or
                change.get('name') != resource['name'] or change.get('provider_name') != PROVIDER or
                change.get('previous_address') is not None or change.get('deposed') is not None or change.get('index') is not None):
            _fail('worker_state_profile_unsupported')
        action = change['change']; unknown = action.get('after_unknown')
        if (action.get('actions') != ['update'] or action.get('importing') is not None or
                canonical(action.get('before')) != canonical(instance['attributes']) or
                action.get('before_identity') != instance['identity'] or action.get('after_identity') != instance['identity'] or
                type(unknown) is not dict or set(k for k, v in unknown.items() if v is True) != COMPUTED or
                not NativeStateWriteContract._known({k: v for k, v in unknown.items() if k not in COMPUTED}) or
                type(action.get('after')) is not dict or set(action['after']) != set(instance['attributes']) - COMPUTED or
                action['after'].get('id') != batch['object_id']):
            _fail('worker_state_unknown_values_unsupported')
        if type(plan.get('planned_values')) is not dict: _fail('worker_state_profile_unsupported')
        root = plan['planned_values'].get('root_module')
        if type(root) is not dict or set(root) != {'resources'} or type(root['resources']) is not list or len(root['resources']) != 1:
            _fail('worker_state_profile_unsupported')
        planned = root['resources'][0]
        if (type(planned) is not dict or planned.get('address') != address or planned.get('schema_version') != 0 or planned.get('identity_schema_version') != 0 or
                planned.get('identity') != instance['identity'] or canonical(planned.get('values')) != canonical(action['after'])):
            _fail('worker_state_profile_unsupported')
        expected = parse_json(canonical(before)); expected['serial'] += 1
        expected['check_results'] = _checks(plan)
        attrs = parse_json(canonical(action['after']))
        attrs.update({key: {'observation_bound_computed_attribute': key} for key in COMPUTED})
        expected['resources'][0]['instances'][0]['attributes'] = attrs
        self._template = canonical(expected); self.pid = os.getpid(); self.created_at = time.time()
        self.execution_binding_sha256 = execution_binding_sha256
        self._reader_identity_sha256 = digest(source['identity']); self._source_class = source['evidence_class']
        self.object_id, self.tenant_id = batch['object_id'], batch['tenant_id']
        self._binding = {'schema_version': 'computed-native-state-write-contract/1.0',
            'profile': 'pinned_settings_catalog_update_with_two_independent_computed_fields',
            'execution_binding_sha256': execution_binding_sha256, 'baseline_sha256': hashlib.sha256(baseline_raw).hexdigest(),
            'plan_json_sha256': hashlib.sha256(plan_json_raw).hexdigest(), 'saved_plan_sha256': saved_plan_sha256,
            'admission_template_sha256': hashlib.sha256(self._template).hexdigest(), 'resource_address': address,
            'tenant_id': self.tenant_id, 'object_id': self.object_id, 'reader_identity_sha256': self._reader_identity_sha256,
            'preimage_capture_sha256': batch['capture_sha256'], 'precondition_binding_sha256': digest(gate_binding), 'computed_attributes': sorted(COMPUTED),
            'source_evidence_class': self._source_class, 'management_mapping_status': batch['status'],
            'management_mapping_blockers': batch['source'].get('mapping_blockers', []),
            'execution_authorized': False, 'service_freshness_atomic': False}

        self._contract_digest = digest(self._binding)

    def _fresh(self):
        if (self.pid != os.getpid() or digest(self._binding) != self._contract_digest or
                hashlib.sha256(self._template).hexdigest() != self._binding['admission_template_sha256'] or
                self.execution_binding_sha256 != self._binding['execution_binding_sha256']):
            _fail('worker_state_contract_changed')

    def binding(self):
        self._fresh(); return parse_json(canonical(self._binding))

    def admit(self, candidate_raw, *, completion):
        if self.pid != os.getpid() or type(candidate_raw) is not bytes or not 0 < len(candidate_raw) <= _MAX:
            _fail('worker_state_candidate_invalid')
        self._fresh()
        expected_type = wp.LiveGraphCompletion if self._source_class == 'graph_authenticated_observation' else wp.LaboratoryGraphCompletion
        if type(completion) is not expected_type: _fail('worker_state_completed_capture_invalid')
        facts = completion.verified()
        if (facts['execution_binding_sha256'] != self.execution_binding_sha256 or
                facts['precondition_binding_sha256'] != self._binding['precondition_binding_sha256']):
            _fail('worker_state_completed_capture_invalid')
        batch, source = _capture(facts['capture'])
        if (batch['tenant_id'] != self.tenant_id or batch['object_id'] != self.object_id or
                digest(source['identity']) != self._reader_identity_sha256 or source['evidence_class'] != self._source_class or
                not self.created_at <= batch['observed_at'] <= time.time() or time.time() - batch['observed_at'] > 30):
            _fail('worker_state_completed_capture_invalid')
        raw = batch['source']['raw_observed']; policy, settings = raw['policy'], raw['settings']
        if (type(policy) is not dict or policy.get('id') != self.object_id or type(settings) is not list or
                type(policy.get('settingCount')) is not int or policy['settingCount'] != len(settings) or
                not 0 <= policy['settingCount'] <= 2147483647 or type(policy.get('lastModifiedDateTime')) is not str):
            _fail('worker_state_computed_evidence_invalid')
        try: stamp = datetime.fromisoformat(policy['lastModifiedDateTime'].replace('Z', '+00:00'))
        except ValueError: _fail('worker_state_computed_evidence_invalid')
        if stamp.tzinfo is None: _fail('worker_state_computed_evidence_invalid')
        # Exact pinned GraphToFrameworkTime conversion uses Go time.RFC3339:
        # retain offset, omit fractional seconds, and use Z for UTC.
        rendered = stamp.replace(microsecond=0).isoformat(timespec='seconds').replace('+00:00', 'Z')
        expected = parse_json(self._template)
        expected['resources'][0]['instances'][0]['attributes'].update(
            settings_count=policy['settingCount'], last_modified_date_time=rendered)
        if canonical(parse_json(candidate_raw)) != canonical(expected): _fail('worker_state_candidate_mismatch')
        return {'schema_version': 'computed-native-state-write-admission/1.0', 'status': 'content_matched',
            'contract_sha256': digest(self._binding), 'body_sha256': hashlib.sha256(candidate_raw).hexdigest(),
            'completed_capture_sha256': batch['capture_sha256'], 'reader_identity_sha256': self._reader_identity_sha256,
            'source_evidence_class': self._source_class, 'management_mapping_status': batch['status'],
            'management_mapping_blockers': batch['source'].get('mapping_blockers', []),
            'execution_authorized': False, 'service_freshness_atomic': False}
