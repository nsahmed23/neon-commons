"""Strict target consistency and fixed GET-only Azure observations.

Neither a JSON document nor this collector authenticates the caller's principal,
protects an approval, observes the state blob, or authorizes an external action.
"""
from __future__ import annotations

import datetime as dt
import http.client
import re
import ssl
import socket
import threading
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from .io import AppError, canonical, digest, parse_json

VERSION = 'target-evidence/1.0'
MAX_DOCUMENT_BYTES = 65536
MAX_RESPONSE_BYTES = 1024 * 1024
GUID_PATTERN = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
GUID = {'type': 'string', 'pattern': GUID_PATTERN}
SHA = {'type': 'string', 'pattern': r'^[0-9a-f]{64}$'}
NAME = {'type': 'string', 'pattern': r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$'}
RELATIVE = {'type': 'string', 'maxLength': 512,
            'pattern': r'^[A-Za-z0-9_-][A-Za-z0-9_.-]*(/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*$'}
TIMESTAMP = {'type': 'string', 'maxLength': 32, 'pattern': r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$'}
STORAGE_RESOURCE = re.compile(
    r'^/subscriptions/([0-9a-f-]{36})/resourceGroups/([A-Za-z0-9_()-][A-Za-z0-9_.()-]{0,89})'
    r'/providers/Microsoft\.Storage/storageAccounts/([a-z0-9]{3,24})$')


def _object(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def _constant(value):
    return {'const': value}


FEDERATION = _object({
    'issuer': {'type': 'string', 'minLength': 9, 'maxLength': 512},
    'subject': {'type': 'string', 'minLength': 1, 'maxLength': 512, 'pattern': r'^[\x21-\x7e]+$'},
    'audience': _constant('api://AzureADTokenExchange'),
})
IDENTITY = _object({
    'principal_object_id': GUID, 'client_id': GUID,
    'auth_kind': {'enum': ['workload_federation', 'managed_identity', 'application_certificate']},
    'federation': {'anyOf': [FEDERATION, {'type': 'null'}]},
})
SCHEMA = _object({
    'schema_version': _constant(VERSION), 'observed_at': TIMESTAMP,
    'binding': _object({
        'cloud': _constant('public'), 'tenant_id': GUID,
        'subscription_id': {'anyOf': [GUID, {'type': 'null'}]},
        'endpoints': _object({
            'graph': _constant('https://graph.microsoft.com'),
            'authority': _constant('https://login.microsoftonline.com'),
            'management': _constant('https://management.azure.com'),
            'storage_audience': _constant('https://storage.azure.com/'),
        }),
        'identity': IDENTITY,
        'repository': _object({
            'git_revision': {'type': 'string', 'pattern': r'^[0-9a-f]{40}$'},
            'dirty_files_sha256': SHA, 'source_sha256': SHA,
            'configuration_sha256': SHA, 'logical_stack': NAME,
            'physical_stack': RELATIVE, 'component': RELATIVE,
            'implementation_path': RELATIVE, 'runtime_layers_sha256': SHA,
        }),
        'backend': _object({
            'type': _constant('azurerm'), 'cloud': _constant('public'),
            'tenant_id': GUID, 'subscription_id': GUID, 'identity': IDENTITY,
            'storage_account_resource_id': {'type': 'string', 'maxLength': 256},
            'blob_endpoint': {'type': 'string', 'maxLength': 128},
            'container': {'type': 'string', 'minLength': 3, 'maxLength': 63,
                          'pattern': r'^[a-z0-9]+(-[a-z0-9]+)*$'},
            'key': RELATIVE, 'workspace': NAME,
            'resolved_blob_name': {'type': 'string', 'minLength': 1, 'maxLength': 1024},
            'state_lineage': GUID, 'state_serial': {'type': 'integer', 'minimum': 0, 'maximum': 9007199254740991},
            'state_sha256': SHA,
        }),
        'ownership': _object({
            'mode': _constant('single_writer'), 'writer_id': NAME,
            'scope_sha256': SHA, 'lease_id': GUID, 'lease_expires_at': TIMESTAMP,
        }),
        'toolchain': _object({
            'atmos_version': _constant('1.199.0'), 'atmos_sha256': SHA,
            'engine': _constant('tofu'), 'engine_version': _constant('1.10.0'),
            'engine_sha256': SHA, 'provider_source': _constant('deploymenttheory/microsoft365'),
            'provider_version': _constant('1.0.0'), 'provider_lock_sha256': SHA,
        }),
    }),
})
VALIDATOR = Draft202012Validator(SCHEMA)
UNVERIFIED = (
    'evidence_not_authenticated', 'principal_not_authenticated',
    'federation_not_authenticated', 'runtime_configuration_not_observed',
    'state_blob_not_observed', 'writer_ownership_not_verified',
)


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _issue(code, path=''):
    return {'code': code, 'path': path}


def _bounded(document):
    pending = [(document, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > 512 or depth > 12:
            return False
        if type(value) is dict:
            if len(value) > 64 or any(type(key) is not str or len(key) > 128 for key in value):
                return False
            pending.extend((item, depth + 1) for item in value.values())
        elif type(value) is list:
            if len(value) > 64:
                return False
            pending.extend((item, depth + 1) for item in value)
        elif type(value) is str:
            if len(value) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in value):
                return False
        elif value is not None and type(value) not in (int, bool):
            return False
    try:
        return len(canonical(document)) <= MAX_DOCUMENT_BYTES
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
        return False


def _snapshot(document):
    try:
        return parse_json(canonical(document)) if _bounded(document) else None
    except (AppError, TypeError, ValueError, UnicodeError, RecursionError):
        return None


def _time(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))


def _temporal_issues(document):
    try:
        now = _now()
        age = (now - _time(document['observed_at'])).total_seconds()
        lease_end = _time(document['binding']['ownership']['lease_expires_at'])
        issues = []
        if age < -30 or age > 300:
            issues.append(_issue('observation_not_fresh', '/observed_at'))
        if lease_end <= now:
            issues.append(_issue('ownership_lease_expired', '/binding/ownership/lease_expires_at'))
        return issues
    except ValueError:
        return [_issue('invalid_timestamp')]


def _federation_issues(identity, prefix):
    federation = identity['federation']
    if (identity['auth_kind'] == 'workload_federation') != (federation is not None):
        return [_issue('federation_auth_kind_mismatch', prefix + '/federation')]
    if federation is None:
        return []
    try:
        issuer = urlsplit(federation['issuer'])
        valid = (issuer.scheme == 'https' and issuer.hostname and issuer.port is None
                 and not issuer.username and not issuer.password and not issuer.query
                 and not issuer.fragment and not any(ord(c) < 33 or ord(c) > 126 for c in federation['issuer']))
    except ValueError:
        valid = False
    return [] if valid else [_issue('invalid_federation_origin', prefix + '/federation/issuer')]


def _relationship_issues(document):
    binding = document['binding']
    backend = binding['backend']
    issues = _federation_issues(binding['identity'], '/binding/identity')
    issues += _federation_issues(backend['identity'], '/binding/backend/identity')
    resource = STORAGE_RESOURCE.fullmatch(backend['storage_account_resource_id'])
    if not resource:
        issues.append(_issue('invalid_storage_resource_id', '/binding/backend/storage_account_resource_id'))
    else:
        subscription, _, account = resource.groups()
        if subscription != backend['subscription_id']:
            issues.append(_issue('storage_subscription_mismatch', '/binding/backend/subscription_id'))
        if backend['blob_endpoint'] != f'https://{account}.blob.core.windows.net':
            issues.append(_issue('storage_endpoint_mismatch', '/binding/backend/blob_endpoint'))
    expected_blob = backend['key']
    if backend['workspace'] != 'default':
        expected_blob += 'env:' + backend['workspace']
    if backend['resolved_blob_name'] != expected_blob:
        issues.append(_issue('workspace_blob_mismatch', '/binding/backend/resolved_blob_name'))
    return issues + _temporal_issues(document)


def inspect_target(document: dict) -> dict:
    """Validate supplied target binding; return only hashes, paths and fixed reasons."""
    result = {'schema_version': VERSION, 'valid': False, 'status': 'invalid',
              'assurance': 'supplied_consistency_only', 'execution_authorized': False,
              'blockers': [_issue(code) for code in UNVERIFIED]}
    document = _snapshot(document)
    if document is None:
        result['issues'] = [_issue('invalid_or_unbounded_document')]
        return result
    # Validator paths are schema-known fields; additional-property names and
    # error messages are deliberately never copied into reports.
    issues = []
    for error in VALIDATOR.iter_errors(document):
        path = '/' + '/'.join(str(part) for part in error.absolute_path) if error.absolute_path else ''
        issues.append(_issue('schema_' + error.validator, path))
        if len(issues) == 32:
            break
    if not issues:
        issues = _relationship_issues(document)
    result['issues'] = issues
    if not issues:
        result.update(valid=True, status='consistent', binding_sha256=digest(document['binding']))
    return result


def _differences(expected, observed, path='/binding'):
    if type(expected) is dict and type(observed) is dict:
        result = []
        for key in sorted(expected):
            result.extend(_differences(expected[key], observed[key], path + '/' + key))
        return result
    return [] if expected == observed else [{'path': path, 'reason': 'changed'}]


def compare_targets(expected: dict, observed: dict) -> dict:
    """Compare every validated binding leaf; a match is never authorization."""
    expected, observed = _snapshot(expected), _snapshot(observed)
    left, right = inspect_target(expected), inspect_target(observed)
    result = {'schema_version': VERSION, 'status': 'invalid', 'execution_authorized': False,
              'assurance': 'supplied_consistency_only', 'expected': left, 'observed': right,
              'differences': []}
    if left['valid'] and right['valid']:
        differences = _differences(expected['binding'], observed['binding'])
        result.update(status='mismatch' if differences else 'match', differences=differences)
    return result


def _get_json(host, path, token, timeout):
    """No proxy, redirect, retry, cookies, URL input, or alternate trust store API."""
    connection = None
    deadline = None
    try:
        connection = http.client.HTTPSConnection(host, timeout=timeout, context=ssl.create_default_context())
        connection.connect()
        connected_socket = connection.sock

        def stop_read():
            try:
                connected_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        # HTTP headers and body must also stop under a byte-dripping peer. DNS
        # resolution precedes this guard and depends on the OS resolver timeout.
        deadline = threading.Timer(timeout, stop_read)
        deadline.daemon = True
        deadline.start()
        connection.request('GET', path, headers={'Authorization': 'Bearer ' + token,
                           'Accept': 'application/json', 'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        if response.status != 200:
            raise AppError('service_response_unavailable', 'Required read was not successful.')
        content_type = response.getheader('Content-Type', '').split(';', 1)[0].lower()
        encoding = response.getheader('Content-Encoding', 'identity').lower()
        if content_type != 'application/json' or encoding not in ('identity', ''):
            raise AppError('unsupported_response_encoding', 'Required response format is unavailable.')
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise AppError('response_too_large', 'Response exceeded the collection bound.')
        value = parse_json(body)
        if not isinstance(value, dict):
            raise AppError('invalid_service_response', 'Required service facts are unavailable.')
        return value
    finally:
        if deadline is not None:
            deadline.cancel()
        if connection is not None:
            connection.close()


def _service_reads(document):
    binding = document['binding']
    backend = binding['backend']
    return [
        ('organization', 'graph.microsoft.com', '/v1.0/organization?$select=id',
         {'tenant_id': binding['tenant_id']}),
        ('subscription', 'management.azure.com', '/subscriptions/' + backend['subscription_id'] + '?api-version=2022-12-01',
         {'subscription_id': backend['subscription_id'], 'tenant_id': backend['tenant_id'], 'state': 'Enabled'}),
        ('storage_account', 'management.azure.com', backend['storage_account_resource_id'] + '?api-version=2023-05-01',
         {'resource_id': backend['storage_account_resource_id'], 'blob_endpoint': backend['blob_endpoint']}),
    ]


def _extract_facts(kind, value):
    if kind == 'organization':
        rows = value.get('value')
        if type(rows) is not list or len(rows) != 1 or '@odata.nextLink' in value or not isinstance(rows[0], dict):
            return None
        return {'tenant_id': rows[0].get('id')}
    if kind == 'subscription':
        return {'subscription_id': value.get('subscriptionId'), 'tenant_id': value.get('tenantId'), 'state': value.get('state')}
    properties = value.get('properties')
    endpoints = properties.get('primaryEndpoints') if isinstance(properties, dict) else None
    endpoint = endpoints.get('blob') if isinstance(endpoints, dict) else None
    if not isinstance(endpoint, str):
        return None
    # Azure returns the service root with a trailing slash; only that exact
    # one-slash representation is equivalent to the contract's origin.
    if endpoint.endswith('/'):
        endpoint = endpoint[:-1]
    return {'resource_id': value.get('id'), 'blob_endpoint': endpoint}


def collect_azure_observations(document: dict, *, graph_token: str,
                               management_token: str, timeout: int = 10) -> dict:
    """Three fixed TLS GETs; reads service facts without exposing credentials.

    Tokens remain opaque. Even successful resource reads do not establish the
    principal/client/federation fields, state, writer ownership, or approval.
    This API performs network reads only when explicitly called; inspect/compare
    never call it. Returned JSON is a report, not a reusable authority object.
    """
    # Freeze the request before inspection: subsequent caller edits cannot
    # substitute a different resource after validation.
    snapshot = _snapshot(document)
    inspection = inspect_target(snapshot)
    result = {'schema_version': 'azure-observations/1.0', 'status': 'invalid',
              'execution_authorized': False, 'assurance': 'partial_service_observation',
              'inspection': inspection, 'observations': [],
              'blockers': [_issue(code) for code in UNVERIFIED if code != 'evidence_not_authenticated']}
    tokens_valid = all(type(token) is str and 1 <= len(token) <= 16384
                       and all(33 <= ord(c) <= 126 for c in token)
                       for token in (graph_token, management_token))
    if not inspection['valid'] or not tokens_valid or type(timeout) is not int or not 1 <= timeout <= 30:
        result['issues'] = [_issue('invalid_collection_request')]
        return result
    for kind, host, path, expected in _service_reads(snapshot):
        try:
            value = _get_json(host, path, graph_token if kind == 'organization' else management_token, timeout)
            facts = _extract_facts(kind, value)
            if facts != expected:
                raise AppError('service_target_mismatch', 'Required service facts did not match.')
        except (AppError, OSError, ValueError, http.client.HTTPException):
            result.update(status='unavailable', issues=[_issue('service_observation_unavailable', '/' + kind)])
            return result
        result['observations'].append({'kind': kind, 'method': 'GET', 'service': host,
                                       'facts_sha256': digest(facts), 'observed_at': _now().isoformat()})
    result.update(status='observed', issues=[])
    return result
