"""Strict target consistency and fixed GET-only Azure observations.

Neither a JSON document nor this collector authenticates the caller's principal,
protects an approval, observes the state blob, or authorizes an external action.
"""
from __future__ import annotations

import base64
import datetime as dt
import http.client
import json
import re
import ssl
import socket
import threading
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from .io import AppError, canonical, digest, parse_json
from .pin_profiles import CURRENT as CURRENT_PROFILE, LEGACY as LEGACY_PROFILE, tools

# Version 1 names the legacy tool pair (OpenTofu 1.10.0, Atmos 1.199.0) and stays readable for reproduction only: it is
# labelled legacy_reproduction_only, and nothing here ever writes a version 1 document back as version 2. Version 2
# names the current local qualification from native_pins.py: version and SHA-256 of both executables.
VERSION_V1 = 'target-evidence/1.0'
VERSION_V2 = 'target-evidence/2.0'
VERSION = VERSION_V2
_CURRENT, _LEGACY = tools(CURRENT_PROFILE), tools(LEGACY_PROFILE)
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


def _schema(version, toolchain):
    return _object({
        'schema_version': _constant(version), 'observed_at': TIMESTAMP,
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
            'toolchain': toolchain,
        }),
    })


def _toolchain(atmos_version, atmos_sha256, engine_version, engine_sha256):
    return _object({
        'atmos_version': _constant(atmos_version), 'atmos_sha256': atmos_sha256,
        'engine': _constant('tofu'), 'engine_version': _constant(engine_version),
        'engine_sha256': engine_sha256, 'provider_source': _constant('deploymenttheory/microsoft365'),
        'provider_version': _constant('1.0.0'), 'provider_lock_sha256': SHA,
    })


SCHEMA_V1 = _schema(VERSION_V1, _toolchain(_LEGACY['atmos_version'], SHA, _LEGACY['engine_version'], SHA))
SCHEMA_V2 = _schema(VERSION_V2, _toolchain(
    _CURRENT['atmos_version'], _constant(_CURRENT['atmos_sha256']),
    _CURRENT['engine_version'], _constant(_CURRENT['engine_sha256'])))
SCHEMA = SCHEMA_V2
VALIDATORS = {VERSION_V1: Draft202012Validator(SCHEMA_V1), VERSION_V2: Draft202012Validator(SCHEMA_V2)}
PROFILES = {VERSION_V1: LEGACY_PROFILE, VERSION_V2: CURRENT_PROFILE}
VALIDATOR = VALIDATORS[VERSION_V2]
UNVERIFIED = (
    'evidence_not_authenticated', 'principal_not_authenticated',
    'federation_not_authenticated', 'runtime_configuration_not_observed',
    'state_blob_not_observed', 'writer_ownership_not_verified',
)


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _issue(code, path=''):
    return {'code': code, 'path': path}


# EXPIRED ACCESS AND WRONG TENANT (offline). Claims in a token are read WITHOUT verification: nothing here checks the
# signature, so a claim is never trusted for access, only used to explain a refusal the product is already making.
# Of everything in a token, only the tenant identifier and the expiry time are kept or shown.
TOKEN_CODES = ('token_expired', 'token_wrong_tenant')
_TENANT_CLAIM = re.compile(GUID_PATTERN)
_MAX_EXPIRY = 4102444800  # 2100-01-01; a larger number is not a plausible expiry


def _expiry_text(moment):
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


def token_claims(token):
    """Unverified tenant id and expiry from a JWT-shaped token; both None for anything else. Never raises."""
    claims = {'tenant_id': None, 'expires_at': None}
    try:
        parts = token.split('.') if isinstance(token, str) and len(token) <= 16384 else []
        if len(parts) != 3:
            return claims
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
        if type(payload) is not dict:
            return claims
        tenant = payload.get('tid')
        if type(tenant) is str and _TENANT_CLAIM.fullmatch(tenant.lower()):
            claims['tenant_id'] = tenant.lower()
        expiry = payload.get('exp')
        if type(expiry) in (int, float) and 0 < expiry < _MAX_EXPIRY:
            claims['expires_at'] = _expiry_text(dt.datetime.fromtimestamp(expiry, dt.timezone.utc))
    except (ValueError, TypeError, OverflowError, OSError, UnicodeError):
        pass
    return claims


def _label(claim):
    return f' (unverified {claim} claim read from the token, used only to explain this refusal)'


def token_problem(token, tenant, now):
    """Explain a token that names another tenant, or has expired, before any call is made; else None.

    Returns code, message and next_step. The wrong tenant is named before expiry: a new token for the same wrong
    tenant would fail the same way.
    """
    claims = token_claims(token)
    if claims['tenant_id'] is not None and claims['tenant_id'] != tenant.lower():
        return {'code': 'token_wrong_tenant',
                'message': f"The token is for tenant {claims['tenant_id']} while this context names tenant {tenant}"
                           + _label('tenant') + '.',
                'next_step': f'Obtain a token for tenant {tenant}, then run this command again.'}
    if claims['expires_at'] is not None and _time(claims['expires_at']) <= now:
        return {'code': 'token_expired',
                'message': f"The token expired at {claims['expires_at']}" + _label('expiry') + '.',
                'next_step': f'Obtain a new token for tenant {tenant}, then run this command again.'}
    return None


def classify_denial(body):
    """token_expired / token_wrong_tenant when a 401/403 body says so in the service's own error code, else None."""
    try:
        value = json.loads(body[:8192]) if isinstance(body, (bytes, bytearray)) else None
    except (ValueError, UnicodeError):
        return None
    error = value.get('error') if type(value) is dict else None
    if type(error) is not dict:
        return None
    code, message = error.get('code'), error.get('message')
    code = code if type(code) is str else ''
    message = message.lower() if type(message) is str else ''
    if code == 'InvalidAuthenticationTokenTenant' or (code == 'InvalidAuthenticationToken'
                                                      and ('wrong issuer' in message or 'tenant' in message)):
        return 'token_wrong_tenant'
    if code == 'ExpiredAuthenticationToken' or (code == 'InvalidAuthenticationToken' and 'expired' in message):
        return 'token_expired'
    return None


def service_denial(code, token, tenant):
    """The explanation for a service answer. Nothing from the service's body is carried; only the code decided it."""
    claims = token_claims(token)
    if code == 'token_wrong_tenant':
        seen = f" (the token's own unverified tenant claim is {claims['tenant_id']})" if claims['tenant_id'] else ''
        return {'code': code, 'message': f'The service answered that the token belongs to a different tenant than '
                                         f'this context names ({tenant}){seen}.',
                'next_step': f'Obtain a token for tenant {tenant}, then run this command again.'}
    seen = f" (the token's own unverified expiry claim is {claims['expires_at']})" if claims['expires_at'] else ''
    return {'code': code, 'message': f'The service answered that the token has expired{seen}.',
            'next_step': f'Obtain a new token for tenant {tenant}, then run this command again.'}


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
              'pin_profile': None, 'blockers': [_issue(code) for code in UNVERIFIED]}
    document = _snapshot(document)
    if document is None:
        result['issues'] = [_issue('invalid_or_unbounded_document')]
        return result
    # The declared version selects the schema and the label. A version this module does not know is judged against
    # the current schema, which reports the unsupported version at /schema_version, and carries no pin profile.
    declared = document.get('schema_version') if type(document) is dict else None
    known = type(declared) is str and declared in VALIDATORS
    if known:
        result.update(schema_version=declared, pin_profile=PROFILES[declared])
    # Validator paths are schema-known fields; additional-property names and
    # error messages are deliberately never copied into reports.
    issues = []
    for error in VALIDATORS[declared if known else VERSION].iter_errors(document):
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
        # A legacy descriptor never matches a current one, even where every binding leaf agrees.
        differences = ([{'path': '/schema_version', 'reason': 'changed'}]
                       if expected['schema_version'] != observed['schema_version'] else [])
        differences += _differences(expected['binding'], observed['binding'])
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
            if response.status in (401, 403):
                # STOP POINT: the service says the token expired or belongs to another tenant; the caller returns
                # at once and makes no further call.
                denial = classify_denial(response.read(8192))
                if denial is not None:
                    raise AppError(denial, 'The service rejected the token.')
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
    binding = snapshot['binding']
    # STOP POINT (before any connection): a token whose own claims name another tenant, or that has expired.
    for where, token, tenant in (('/graph_token', graph_token, binding['tenant_id']),
                                 ('/management_token', management_token, binding['backend']['tenant_id'])):
        problem = token_problem(token, tenant, _now())
        if problem is not None:
            result.update(status='unavailable', issues=[{'code': problem['code'], 'path': where,
                                                         'message': problem['message'], 'next_step': problem['next_step']}])
            return result
    for kind, host, path, expected in _service_reads(snapshot):
        token = graph_token if kind == 'organization' else management_token
        try:
            value = _get_json(host, path, token, timeout)
            facts = _extract_facts(kind, value)
            if facts != expected:
                raise AppError('service_target_mismatch', 'Required service facts did not match.')
        except AppError as error:
            if error.code in TOKEN_CODES:
                tenant = binding['tenant_id'] if kind == 'organization' else binding['backend']['tenant_id']
                explained = service_denial(error.code, token, tenant)
                result.update(status='unavailable', issues=[{'code': explained['code'], 'path': '/' + kind,
                                                             'message': explained['message'],
                                                             'next_step': explained['next_step']}])
                return result
            result.update(status='unavailable', issues=[_issue('service_observation_unavailable', '/' + kind)])
            return result
        except (OSError, ValueError, http.client.HTTPException):
            result.update(status='unavailable', issues=[_issue('service_observation_unavailable', '/' + kind)])
            return result
        result['observations'].append({'kind': kind, 'method': 'GET', 'service': host,
                                       'facts_sha256': digest(facts), 'observed_at': _now().isoformat()})
    result.update(status='observed', issues=[])
    return result
