"""Bounded HTTPS-over-Unix egress broker for a separately isolated worker.

A broker policy is an operator-installed request contract, not approval. The
trusted controller must supply a process-held guard bound to its approved job.
Native upstream transport always uses fixed HTTPS443 and the system trust store.
The laboratory transport is a distinct type and cannot serve a native policy.
"""
from __future__ import annotations

from contextlib import contextmanager
import base64
import hashlib
from datetime import datetime, timezone
import http.client
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import ssl
import stat
import struct
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

from . import identity_binding as ib
from .azure_backend import NativeStateWriteContract
from .worker_state import ComputedNativeStateWriteContract
from . import worker_precondition as wp
from .io import AppError, canonical, digest, parse_json
from .provider_journey import _private

_HASH = re.compile(r'^[0-9a-f]{64}$')
_HOST = re.compile(r'^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$')
_HEADER = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')
_SEAL = object()
_GUID = re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$')
_HARMLESS_HEADERS = {'host', 'authorization', 'accept', 'accept-encoding', 'user-agent',
    'client-request-id', 'return-client-request-id', 'x-ms-client-request-id',
    'sdkversion', 'x-ms-useragent', 'x-client-sku', 'x-client-ver', 'x-client-os', 'x-client-cpu'}
_WRITE_EFFECTS = {'mutation', 'lease', 'state_write', 'lock_metadata'}
MAX_REQUEST = 1024 * 1024
MAX_RESPONSE = 16 * 1024 * 1024
_AUDIENCES = {'graph': 'https://graph.microsoft.com/.default',
              'arm': 'https://management.azure.com/.default',
              'storage': 'https://storage.azure.com/.default'}


def _fail(code):
    raise AppError(code, 'The protected egress request was not admitted or its outcome is uncertain.') from None


class BrokerGuard:
    def __init__(self, seal, execution_binding_sha256, recheck, binding=None):
        if seal is not _SEAL or not callable(recheck): _fail('broker_host_guard_required')
        self.execution_binding_sha256, self.recheck, self.binding = execution_binding_sha256, recheck, binding
        self.pid = os.getpid()

    def check(self, policy):
        if self.pid != os.getpid() or self.execution_binding_sha256 != policy['execution_binding_sha256']:
            _fail('broker_guard_binding')
        if time.time() >= policy['expires_at']: _fail('broker_expired')
        if policy['profile'] == 'azure_public_pilot':
            ib.require_live_binding(self.binding)
            self.binding.assert_fresh()
        elif self.binding is not None:
            _fail('broker_profile_mismatch')
        if self.recheck() is not None: _fail('broker_guard_contract')


def laboratory_guard(execution_binding_sha256, recheck):
    return BrokerGuard(_SEAL, execution_binding_sha256, recheck)


def live_guard(execution_binding_sha256, *, binding, recheck):
    """Trusted service API only. Recheck must enforce actual signed job authority.

    Identity authentication alone grants no mutation permission. This factory is
    never exposed as a terminal/model command or reconstructed from JSON.
    """
    ib.require_live_binding(binding)
    return BrokerGuard(_SEAL, execution_binding_sha256, recheck, binding)


def validate_backend_targets(policy, backend):
    """Validate declared routes against one bound backend; no authentication grant."""
    if type(backend) is not ib.BackendSpec: _fail('broker_backend_target_invalid')
    value = validate_policy(policy)
    host = urlsplit(backend.blob_endpoint).hostname
    state_path = '/' + backend.container + '/' + backend.key
    if value.get('native_lock') not in (None, {'host': host, 'path': state_path}): _fail('broker_backend_target_invalid')
    for route in value['routes']:
        if route['role'] != 'backend' or route['effect'] in ('oauth', 'discovery'): continue
        if route['audience'] == 'storage':
            listing = (route['method'] == 'GET' and route['effect'] == 'readonly' and
                       route['path'] == '/' + backend.container and
                       route['query'] == {'comp': 'list', 'marker': '', 'prefix': backend.key + 'env:', 'restype': 'container'})
            if route['host'] != host or not (route['path'] == state_path or listing):
                _fail('broker_backend_target_invalid')
        elif route['audience'] == 'arm':
            if (route['host'] != 'management.azure.com' or route['method'] != 'GET' or
                    route['path'] not in (backend.storage_account_resource_id, '/subscriptions/' + backend.subscription_id)):
                _fail('broker_backend_target_invalid')
        else: _fail('broker_backend_target_invalid')


class BrokerCredentials:
    """Host-held identity-bound OAuth substitution; never serializable or logged."""
    def __init__(self, seal, binding, backend_credential, execution_binding_sha256):
        if seal is not _SEAL or type(binding) not in (ib.LiveIdentityBinding, ib.LaboratoryIdentityBinding):
            _fail('broker_credential_binding')
        if type(execution_binding_sha256) is not str or not _HASH.fullmatch(execution_binding_sha256): _fail('broker_credential_binding')
        provider = binding.provider_environment()
        backend, _ = binding.backend_configuration(backend_credential)
        self.binding, self.backend_credential, self.execution_binding_sha256 = binding, backend_credential, execution_binding_sha256
        self.identities = {'provider': {'tenant_id': provider['M365_TENANT_ID'], 'client_id': provider['M365_CLIENT_ID']},
                           'backend': {'tenant_id': backend.tenant_id, 'client_id': backend.client_id}}
        self.placeholders = {role: 'intune-worker-placeholder-' + execution_binding_sha256 + '-' + role for role in self.identities}
        self.pid = os.getpid(); self.closed = False

    def __repr__(self): return '<BrokerCredentials redacted>'
    def __reduce_ex__(self, protocol): raise TypeError('Broker credentials cannot be serialized.')

    def check(self, policy):
        if self.closed or self.pid != os.getpid() or policy['execution_binding_sha256'] != self.execution_binding_sha256:
            _fail('broker_credential_binding')
        if ((policy['profile'] == 'azure_public_pilot') != (type(self.binding) is ib.LiveIdentityBinding) or
                any(role not in self.identities or identity != self.identities[role] for role, identity in policy['identities'].items())):
            _fail('broker_credential_binding')
        self.binding.assert_fresh()
        _, target = self.binding.backend_configuration(self.backend_credential)
        if policy['profile'] != 'laboratory_tls_fixture': validate_backend_targets(policy, target)

    def worker_environment(self):
        """Only placeholders and declared IDs; no actual credential is returned."""
        if self.closed or self.pid != os.getpid(): _fail('broker_credential_binding')
        self.binding.assert_fresh()
        backend, target = self.binding.backend_configuration(self.backend_credential)
        provider = self.identities['provider']
        return {'M365_TENANT_ID': provider['tenant_id'], 'M365_CLIENT_ID': provider['client_id'],
                'M365_CLIENT_SECRET': self.placeholders['provider'], 'M365_AUTH_METHOD': 'client_secret',
                'ARM_TENANT_ID': backend.tenant_id, 'ARM_CLIENT_ID': backend.client_id,
                'ARM_CLIENT_SECRET': self.placeholders['backend'], 'ARM_SUBSCRIPTION_ID': target.subscription_id,
                'ARM_ENVIRONMENT': 'public', 'ARM_USE_AZUREAD': 'true', 'ARM_USE_CLI': 'false',
                'ARM_USE_MSI': 'false', 'ARM_USE_OIDC': 'false', 'ARM_USE_AKS_WORKLOAD_IDENTITY': 'false'}

    def replace(self, policy, route, body):
        self.check(policy)
        if route['effect'] != 'oauth' or route['role'] not in self.identities: _fail('broker_credential_binding')
        pairs = parse_qsl(body.decode('ascii'), strict_parsing=True, max_num_fields=16)
        form = dict(pairs)
        if (form.get('client_secret') != self.placeholders[route['role']] or
                form.get('client_id') != self.identities[route['role']]['client_id']):
            _fail('broker_credential_binding')
        if route['role'] == 'provider': secret = self.binding.provider_environment()['M365_CLIENT_SECRET']
        else:
            self.binding.backend_configuration(self.backend_credential); secret = self.backend_credential._get()
        return urlencode([(key, secret if key == 'client_secret' else value) for key, value in pairs]).encode('ascii')

    def close(self): self.closed = True


def broker_credentials(*, binding, backend_credential, execution_binding_sha256):
    """Trusted controller API; no JSON/file-based recreation of credentials."""
    return BrokerCredentials(_SEAL, binding, backend_credential, execution_binding_sha256)


class NativeUpstream:
    def __init__(self): self._transport = ib._NativeTransport()

    def request(self, host, method, path, headers, body, *, timeout):
        return self._transport(ib._Request(method, host, path, headers, body), timeout=timeout, max_bytes=MAX_RESPONSE)


class LaboratoryUpstream:
    """Only loopback TLS. Never maps a native policy to an alternate endpoint."""
    def __init__(self, port, cafile):
        if type(port) is not int or not 1 <= port <= 65535: _fail('broker_lab_endpoint_invalid')
        self.port = port
        self.context = ssl.create_default_context(cafile=str(cafile))
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2

    def request(self, host, method, path, headers, body, *, timeout):
        conn = http.client.HTTPSConnection('127.0.0.1', self.port, timeout=timeout, context=self.context)
        try:
            conn.request(method, path, body=body, headers={**headers, 'Host': host})
            response = conn.getresponse()
            return ib.ServiceResponse(response.status, tuple(response.getheaders()),
                                      response.read(MAX_RESPONSE + 1) if method != 'HEAD' else b'')
        finally: conn.close()


def validate_policy(value):
    if (type(value) is not dict or set(value) - {'native_lock'} != {'schema_version', 'profile', 'operation_id', 'execution_binding_sha256',
            'expires_at', 'worker_uid', 'identities', 'routes'} or value['schema_version'] != 'protected-egress-policy/1.0' or
            value['profile'] not in ('laboratory_tls_fixture', 'laboratory_native_protocol', 'azure_public_pilot') or
            type(value['operation_id']) is not str or not re.fullmatch(r'[0-9a-f-]{32,36}', value['operation_id']) or
            type(value['execution_binding_sha256']) is not str or not _HASH.fullmatch(value['execution_binding_sha256']) or
            type(value['expires_at']) is not int or not time.time() < value['expires_at'] <= time.time() + 900 or
            type(value['worker_uid']) is not int or not 0 <= value['worker_uid'] <= 2147483647 or
            type(value['routes']) is not list or not 1 <= len(value['routes']) <= 128):
        _fail('broker_policy_invalid')
    identities = value['identities']
    if type(identities) is not dict or not identities or set(identities) - {'provider', 'backend', 'reader'}:
        _fail('broker_policy_invalid')
    for role, identity in identities.items():
        if (type(identity) is not dict or set(identity) != {'tenant_id', 'client_id'} or
                any(type(v) is not str or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', v) for v in identity.values())):
            _fail('broker_policy_invalid')
    if len({v['client_id'] for v in identities.values()}) != len(identities): _fail('broker_role_separation')
    lock = value.get('native_lock')
    if lock is not None:
        if (type(lock) is not dict or set(lock) != {'host', 'path'} or
                type(lock['host']) is not str or not re.fullmatch(r'[a-z0-9]{3,24}\.blob\.core\.windows\.net|blob\.fixture\.invalid', lock['host']) or
                type(lock['path']) is not str or not re.fullmatch(r'/[a-z0-9-]+/[A-Za-z0-9_./-]+', lock['path']) or
                '..' in lock['path'].split('/') or '//' in lock['path']):
            _fail('broker_native_lock_invalid')
    identifiers = set(); total = 0
    for route in value['routes']:
        if (type(route) is not dict or set(route) - {'state_contract_sha256', 'dynamic_headers'} != {'id', 'host', 'method', 'path', 'query', 'headers',
                'body_sha256', 'role', 'audience', 'effect', 'max_attempts'} or
                type(route['id']) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', route['id']) or route['id'] in identifiers or
                type(route['host']) is not str or not _HOST.fullmatch(route['host']) or
                route['method'] not in ('GET', 'HEAD', 'POST', 'PUT', 'PATCH') or
                type(route['role']) is not str or route['role'] not in identities or type(route['audience']) is not str or route['audience'] not in _AUDIENCES or
                route['effect'] not in ('readonly', 'oauth', 'mutation', 'lease', 'state_write', 'discovery', 'lock_metadata') or
                type(route['body_sha256']) is not str or not _HASH.fullmatch(route['body_sha256']) or
                type(route['max_attempts']) is not int or not 1 <= route['max_attempts'] <= 32):
            _fail('broker_policy_invalid')
        if value['profile'] == 'laboratory_tls_fixture':
            if not route['host'].endswith('.fixture.invalid'): _fail('broker_policy_invalid')
        elif route['host'] not in ('login.microsoftonline.com', 'graph.microsoft.com', 'management.azure.com') and not re.fullmatch(r'[a-z0-9]{3,24}\.blob\.core\.windows\.net', route['host']):
            _fail('broker_policy_invalid')
        if (type(route['path']) is not str or not route['path'].startswith('/') or
                len(route['path']) > 2048 or any(c in route['path'] for c in '%?#\\\r\n\x00') or
                '..' in route['path'].split('/') or route['path'].startswith('//')):
            _fail('broker_policy_invalid')
        if (type(route['query']) is not dict or len(route['query']) > 8 or
                any(type(k) is not str or not re.fullmatch(r'[$A-Za-z][A-Za-z0-9_$-]{0,63}', k) or
                    type(v) is not str or len(v) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in v)
                    for k, v in route['query'].items()) or
                type(route['headers']) is not dict or len(route['headers']) > 16):
            _fail('broker_policy_invalid')
        if route['role'] in ('provider', 'reader') and route['audience'] != 'graph': _fail('broker_role_separation')
        if route['role'] == 'backend' and route['audience'] not in ('arm', 'storage'): _fail('broker_role_separation')
        if route['role'] == 'reader' and route['effect'] not in ('readonly', 'oauth', 'discovery'): _fail('broker_role_separation')
        if route['effect'] == 'oauth':
            login = 'login.fixture.invalid' if value['profile'] == 'laboratory_tls_fixture' else 'login.microsoftonline.com'
            if route['host'] != login or route['path'] != '/' + identities[route['role']]['tenant_id'] + '/oauth2/v2.0/token' or route['query']:
                _fail('broker_oauth_binding')
        elif route['effect'] == 'discovery':
            login = 'login.fixture.invalid' if value['profile'] == 'laboratory_tls_fixture' else 'login.microsoftonline.com'
            tenant = identities[route['role']]['tenant_id']
            expected_query = {'api-version': '1.1', 'authorization_endpoint': 'https://' + login + '/' + tenant + '/oauth2/v2.0/authorize'}
            if (route['host'] != login or route['method'] != 'GET' or route['body_sha256'] != hashlib.sha256(b'').hexdigest() or
                    not ((route['path'] == '/common/discovery/instance' and route['query'] == expected_query) or
                         (route['path'] == '/' + tenant + '/v2.0/.well-known/openid-configuration' and route['query'] == {}))):
                _fail('broker_discovery_binding')
        elif value['profile'] != 'laboratory_tls_fixture':
            target_audience = ('graph' if route['host'] == 'graph.microsoft.com' else
                               'arm' if route['host'] == 'management.azure.com' else
                               'storage' if route['host'].endswith('.blob.core.windows.net') else None)
            if route['audience'] != target_audience: _fail('broker_token_binding')
            if target_audience == 'arm' and route['effect'] != 'readonly': _fail('broker_request_not_admitted')
        for key, item in route['headers'].items():
            if (type(key) is not str or not _HEADER.fullmatch(key) or key in ('authorization', 'proxy-authorization', 'host', 'content-length', 'transfer-encoding',
                       'x-http-method-override', 'x-ms-copy-source', 'x-ms-copy-source-authorization', 'x-ms-copy-action',
                       'x-ms-blob-sequence-number', 'x-ms-sequence-number-action') or
                    type(item) is not str or len(item) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in item)):
                _fail('broker_policy_invalid')
        dynamic = route.get('dynamic_headers', {})
        allowed_dynamic = {'x-ms-proposed-lease-id': {'native_lease_proposal'},
            'x-ms-lease-id': {'active_native_lease'},
            'x-ms-meta-terraformlockid': {'native_lock_metadata_plan', 'native_lock_metadata_apply'}}
        if (type(dynamic) is not dict or set(dynamic) - set(allowed_dynamic) or set(dynamic) & set(route['headers']) or
                any(type(v) is not str or v not in allowed_dynamic[k] for k, v in dynamic.items()) or
                dynamic and (route['role'] != 'backend' or route['audience'] != 'storage')):
            _fail('broker_dynamic_headers_invalid')
        if 'x-ms-proposed-lease-id' in dynamic and (route['effect'] != 'lease' or route['headers'].get('x-ms-lease-action') != 'acquire'):
            _fail('broker_dynamic_headers_invalid')
        if 'x-ms-meta-terraformlockid' in dynamic and not (route['effect'] == 'lock_metadata' or
                route['effect'] == 'state_write' and dynamic['x-ms-meta-terraformlockid'] == 'native_lock_metadata_apply'):
            _fail('broker_dynamic_headers_invalid')
        if 'x-ms-meta-terraformlockid' in route['headers']: _fail('broker_dynamic_headers_invalid')
        if route['effect'] == 'readonly' and (route['method'] not in ('GET', 'HEAD') or route['body_sha256'] != hashlib.sha256(b'').hexdigest()):
            _fail('broker_policy_invalid')
        if route['effect'] == 'oauth' and (route['method'] != 'POST' or route['headers'].get('content-type') not in ('application/x-www-form-urlencoded', 'application/x-www-form-urlencoded; charset=utf-8')): _fail('broker_policy_invalid')
        if route['effect'] == 'mutation' and (route['method'] not in ('POST', 'PUT', 'PATCH') or route['max_attempts'] != 1 or
                route['role'] != 'provider' or route['audience'] != 'graph' or
                route['host'] != ('graph.fixture.invalid' if value['profile'] == 'laboratory_tls_fixture' else 'graph.microsoft.com')):
            _fail('broker_policy_invalid')
        if route['effect'] == 'lease' and (route['method'] != 'PUT' or route['role'] != 'backend' or route['audience'] != 'storage' or
                (value['profile'] != 'laboratory_tls_fixture' and re.fullmatch(r'[a-z0-9]{3,24}\.blob\.core\.windows\.net', route['host']) is None) or
                (value['profile'] == 'laboratory_tls_fixture' and route['host'] != 'blob.fixture.invalid') or
                route['query'] != {'comp': 'lease'} or route['body_sha256'] != hashlib.sha256(b'').hexdigest() or
                route['headers'].get('x-ms-lease-action') not in ('acquire', 'renew', 'release')):
            _fail('broker_policy_invalid')
        if route['effect'] == 'state_write':
            if (route['role'] != 'backend' or route['audience'] != 'storage' or route['method'] != 'PUT' or
                    route['max_attempts'] != 1 or route['query'] or route['headers'].get('x-ms-blob-type') != 'BlockBlob' or
                    route['headers'].get('content-type') not in ('application/json', 'application/octet-stream') or
                    type(route.get('state_contract_sha256')) is not str or not _HASH.fullmatch(route['state_contract_sha256']) or
                    (value['profile'] == 'laboratory_tls_fixture' and route['host'] != 'blob.fixture.invalid')):
                _fail('broker_state_contract_invalid')
            if value['profile'] != 'laboratory_tls_fixture' and dynamic.get('x-ms-lease-id') != 'active_native_lease':
                _fail('broker_native_lock_invalid')
        elif 'state_contract_sha256' in route: _fail('broker_state_contract_invalid')
        if route['effect'] == 'lock_metadata':
            if (route['method'] != 'PUT' or route['role'] != 'backend' or route['audience'] != 'storage' or
                    route['query'] != {'comp': 'metadata'} or route['body_sha256'] != hashlib.sha256(b'').hexdigest() or
                    route['max_attempts'] != 1 or dynamic.get('x-ms-lease-id') != 'active_native_lease' or
                    (value['profile'] == 'laboratory_tls_fixture' and route['host'] != 'blob.fixture.invalid')):
                _fail('broker_native_lock_invalid')
        if value['profile'] != 'laboratory_tls_fixture' and route['effect'] == 'lease':
            action = route['headers']['x-ms-lease-action']
            if action == 'acquire':
                if (route['max_attempts'] != 1 or dynamic != {'x-ms-proposed-lease-id': 'native_lease_proposal'} or
                        route['headers'].get('x-ms-lease-duration') != '-1'):
                    _fail('broker_native_lock_invalid')
            elif dynamic.get('x-ms-lease-id') != 'active_native_lease': _fail('broker_native_lock_invalid')
        if route['effect'] == 'mutation' and value['profile'] != 'laboratory_tls_fixture' and lock is None:
            _fail('broker_native_lock_invalid')
        identifiers.add(route['id']); total += route['max_attempts']
    if total > 256: _fail('broker_policy_invalid')
    return parse_json(canonical(value))


class EgressBroker:
    def __init__(self, policy, *, journal, guard, upstream, state_contracts=None, credentials=None, precondition=None):
        self.policy = validate_policy(policy)
        self.policy_sha256 = digest(self.policy); self.closed = False
        if type(guard) is not BrokerGuard: _fail('broker_host_guard_required')
        expected = NativeUpstream if self.policy['profile'] == 'azure_public_pilot' else LaboratoryUpstream
        if type(upstream) is not expected: _fail('broker_profile_mismatch')
        self.state_contracts = {} if state_contracts is None else dict(state_contracts)
        state_routes = {r['id']: r for r in self.policy['routes'] if r['effect'] == 'state_write'}
        if set(self.state_contracts) != set(state_routes): _fail('broker_state_contract_invalid')
        for identifier, contract in self.state_contracts.items():
            route = state_routes[identifier]
            if (type(contract) not in (NativeStateWriteContract, ComputedNativeStateWriteContract) or digest(contract.binding()) != route['state_contract_sha256'] or
                    contract.binding().get('expected_semantic_sha256', contract.binding().get('admission_template_sha256')) != route['body_sha256']):
                _fail('broker_state_contract_invalid')
        if credentials is not None and type(credentials) is not BrokerCredentials: _fail('broker_credential_binding')
        if self.policy['profile'] != 'laboratory_tls_fixture' and credentials is None: _fail('broker_credential_binding')
        self.credentials = credentials
        if credentials is not None:
            credentials.check(self.policy)
            if self.policy['profile'] == 'azure_public_pilot' and credentials.binding is not guard.binding:
                _fail('broker_credential_binding')
        self.precondition = precondition; self.graph_completion = None; self.state_admissions = {}
        mutations = [route for route in self.policy['routes'] if route['effect'] == 'mutation']
        if precondition is not None or (mutations and self.policy['profile'] != 'laboratory_tls_fixture'):
            expected_gate = wp.LiveGraphPrecondition if self.policy['profile'] == 'azure_public_pilot' else wp.LaboratoryGraphPrecondition
            if type(precondition) is not expected_gate: _fail('broker_precondition_required')
            binding = precondition.binding()
            if (binding['execution_binding_sha256'] != self.policy['execution_binding_sha256'] or
                    binding['profile'] != self.policy['profile'] or binding['tenant_id'] != self.policy['identities'].get('provider', {}).get('tenant_id')):
                _fail('broker_precondition_binding')
            targets = {('PUT', "/beta/deviceManagement/configurationPolicies('" + binding['object_id'] + "')"): 'policy',
                       ('POST', '/beta/deviceManagement/configurationPolicies/' + binding['object_id'] + '/assign'): 'assignments'}
            if len(mutations) != 2 or {(r['method'], r['path']) for r in mutations} != set(targets): _fail('broker_precondition_binding')
            for route in mutations:
                if (route['host'] != 'graph.microsoft.com' or route['query'] or
                        route['body_sha256'] != binding['approved_body_sha256'][targets[(route['method'], route['path'])]]):
                    _fail('broker_precondition_binding')
        for contract in self.state_contracts.values():
            if type(contract) is ComputedNativeStateWriteContract:
                if precondition is None or contract.binding()['precondition_binding_sha256'] != digest(precondition.binding()):
                    _fail('broker_state_contract_invalid')
        self.guard, self.upstream = guard, upstream
        guard.check(self.policy)
        self.journal = Path(journal).absolute(); _private(self.journal.parent, directory=True)
        try:
            descriptor = os.open(self.journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.fsync(descriptor); os.close(descriptor)
        except FileExistsError: pass
        _private(self.journal)
        self._lock = threading.RLock(); self.tokens = {}; self.leases = {}
        with self._database() as db:
            db.execute('CREATE TABLE IF NOT EXISTS binding (digest TEXT NOT NULL)')
            rows = db.execute('SELECT digest FROM binding').fetchall()
            if not rows: db.execute('INSERT INTO binding VALUES (?)', (digest(self.policy),))
            elif rows != [(digest(self.policy),)]: _fail('broker_journal_binding')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (sequence INTEGER PRIMARY KEY, route TEXT NOT NULL, request_sha256 TEXT NOT NULL, status TEXT NOT NULL, response_code INTEGER, response_sha256 TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS native_lease_requests (sequence INTEGER PRIMARY KEY, host TEXT NOT NULL, path TEXT NOT NULL, action TEXT NOT NULL, lease_id TEXT NOT NULL, lock_metadata TEXT)')
            db.commit()

    def check(self):
        if self.closed or digest(self.policy) != self.policy_sha256: _fail('broker_policy_changed_or_closed')
        self.guard.check(self.policy)
        if self.credentials is not None: self.credentials.check(self.policy)

    @contextmanager
    def _database(self):
        _private(self.journal)
        for suffix in ('-journal', '-wal', '-shm'):
            candidate = Path(str(self.journal) + suffix)
            if candidate.exists() or candidate.is_symlink(): _private(candidate)
        db = sqlite3.connect(self.journal, timeout=0)
        db.execute('PRAGMA synchronous=FULL'); db.execute('PRAGMA journal_mode=DELETE'); db.execute('PRAGMA trusted_schema=OFF')
        try:
            yield db
        except BaseException:
            db.rollback(); raise
        finally:
            db.close()

    def native_recovery_record(self):
        """Read-only facts for explicit recovery; never reacquire or force-unlock.

        The proposed/acquired lease ID and exact lock metadata are private local
        authority-bearing data. They remain durable even if dispatch is killed.
        A controller must independently inspect current Blob/Graph/state context
        and obtain separately bound recovery authorization before any release.
        """
        with self._lock, self._database() as db:
            rows = db.execute('SELECT n.sequence,n.host,n.path,n.action,n.lease_id,n.lock_metadata,a.status,a.response_code '
                'FROM native_lease_requests n JOIN attempts a ON a.sequence=n.sequence ORDER BY n.sequence').fetchall()
        return {'schema_version': 'native-lease-recovery-record/1.0', 'policy_sha256': self.policy_sha256,
            'execution_binding_sha256': self.policy['execution_binding_sha256'], 'automatic_release_authorized': False,
            'entries': [dict(zip(('sequence','host','path','action','lease_id','lock_metadata','status','response_code'), row)) for row in rows],
            'requires_independent_current_context_and_explicit_recovery': True}

    def _route(self, host, method, target, headers, body):
        if (type(target) is not str or len(target) > 4096 or '\\' in target or
                any(ord(c) < 32 or ord(c) == 127 for c in target)):
            _fail('broker_request_not_admitted')
        parts = urlsplit(target)
        if parts.scheme or parts.netloc or parts.fragment: _fail('broker_request_not_admitted')
        try: query = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True, max_num_fields=8)
        except ValueError: _fail('broker_request_not_admitted')
        if len({k for k, _ in query}) != len(query): _fail('broker_request_not_admitted')
        candidates = [r for r in self.policy['routes'] if (r['host'], r['method'], r['path']) == (host, method, parts.path)
                      and dict(query) == r['query'] and
                      all(headers.get(k) == v for k, v in r['headers'].items()) and
                      set(r.get('dynamic_headers', {})) <= set(headers) and
                      not (set(headers) - _HARMLESS_HEADERS - set(r['headers']) - set(r.get('dynamic_headers', {}))) and
                      (r['effect'] == 'state_write' or hashlib.sha256(body).hexdigest() == r['body_sha256'])]
        if len(candidates) != 1: _fail('broker_request_not_admitted')
        route = candidates[0]
        self._check_dynamic(route, headers)
        if headers.get('host') not in (None, host, host + ':443'): _fail('broker_request_not_admitted')
        if route['effect'] == 'oauth':
            try:
                pairs = parse_qsl(body.decode('ascii'), strict_parsing=True, max_num_fields=16)
                form = dict(pairs)
            except (ValueError, UnicodeError): _fail('broker_oauth_binding')
            if len(form) != len(pairs) or set(form) - {'client_id', 'client_secret', 'grant_type', 'scope', 'client_info', 'claims'}:
                _fail('broker_oauth_binding')
            if form.get('client_id') != self.policy['identities'][route['role']]['client_id'] or not form.get('client_secret'):
                _fail('broker_oauth_binding')
            if form.get('grant_type') != 'client_credentials' or form.get('scope') not in (_AUDIENCES[route['audience']], _AUDIENCES[route['audience']] + ' openid offline_access profile'):
                _fail('broker_oauth_binding')
            if 'authorization' in headers: _fail('broker_oauth_binding')
        elif route['effect'] == 'discovery':
            if 'authorization' in headers: _fail('broker_discovery_binding')
        else:
            authorization = headers.get('authorization', '')
            if not authorization.startswith('Bearer ') or len(authorization) > 65536:
                _fail('broker_token_binding')
            record = self.tokens.get(hashlib.sha256(authorization[7:].encode()).hexdigest())
            if not record or record[:2] != (route['role'], route['audience']) or time.monotonic() >= record[2]:
                _fail('broker_token_binding')
        return route

    def _check_dynamic(self, route, headers):
        key = (route['host'], route['path']); lease = self.leases.get(key)
        for name, rule in route.get('dynamic_headers', {}).items():
            value = headers[name]
            if rule == 'native_lease_proposal':
                if not _GUID.fullmatch(value) or lease is not None: _fail('broker_native_lock_invalid')
            elif rule == 'active_native_lease':
                if lease is None or value != lease['id']: _fail('broker_native_lock_invalid')
            else:
                try:
                    raw = base64.b64decode(value, validate=True)
                    if len(raw) > 4096 or base64.b64encode(raw).decode() != value: _fail('broker_native_lock_invalid')
                    document = parse_json(raw)
                    created = datetime.fromisoformat(document['Created'].replace('Z', '+00:00'))
                except (ValueError, TypeError, KeyError, AttributeError, AppError): _fail('broker_native_lock_invalid')
                expected = 'OperationTypePlan' if rule == 'native_lock_metadata_plan' else 'OperationTypeApply'
                if (type(document) is not dict or set(document) != {'ID', 'Operation', 'Info', 'Who', 'Version', 'Created', 'Path'} or
                        lease is None or document['ID'] != lease['id'] or document['Operation'] != expected or
                        document['Info'] != '' or document['Version'] != '1.13.1' or
                        type(document['Who']) is not str or not re.fullmatch(r'@[0-9a-f]{12}', document['Who']) or
                        document['Path'] != 'https://' + route['host'] + route['path'] or
                        created.tzinfo is None or abs(created.timestamp() - time.time()) > 120):
                    _fail('broker_native_lock_invalid')
        if route['effect'] == 'state_write' and self.policy['profile'] != 'laboratory_tls_fixture':
            if lease is None or lease.get('operation') != 'OperationTypeApply': _fail('broker_native_lock_invalid')
            if 'x-ms-meta-terraformlockid' in headers and headers['x-ms-meta-terraformlockid'] != lease.get('metadata'):
                _fail('broker_native_lock_invalid')
        if route['effect'] == 'mutation' and self.policy.get('native_lock') is not None:
            lock = self.policy['native_lock']; held = self.leases.get((lock['host'], lock['path']))
            if held is None or held.get('operation') != 'OperationTypeApply': _fail('broker_native_lock_invalid')

    def handle(self, host, method, target, headers, body):
        # One actual service request at a time: fresh Graph reads, lease state,
        # durable dispatch and the response cannot interleave another mutation.
        with self._lock:
            return self._handle(host, method, target, headers, body)

    def _handle(self, host, method, target, headers, body):
        if type(body) is not bytes or len(body) > MAX_REQUEST or type(headers) is not dict:
            _fail('broker_request_not_admitted')
        if len(headers) > 64: _fail('broker_request_not_admitted')
        for key, value in headers.items():
            if (type(key) is not str or not _HEADER.fullmatch(key) or type(value) is not str or
                    any(ord(c) < 32 or ord(c) == 127 for c in value) or key in
                    ('proxy-authorization', 'transfer-encoding', 'upgrade', 'trailer', 'connection')):
                _fail('broker_request_not_admitted')
        if sum(len(k) + len(v) for k, v in headers.items()) > 32768: _fail('broker_request_not_admitted')
        self.check()
        with self._lock:
            route = self._route(host, method, target, headers, body)
            with self._database() as db:
                db.execute('BEGIN IMMEDIATE')
                prior = db.execute('SELECT status FROM attempts WHERE route=?', (route['id'],)).fetchall()
                if len(prior) >= route['max_attempts'] or (route['effect'] in _WRITE_EFFECTS and any(row[0] != 'response_received' for row in prior)):
                    _fail('broker_attempt_not_replayable')
                if route['effect'] in _WRITE_EFFECTS:
                    write_ids = {item['id'] for item in self.policy['routes'] if item['effect'] in _WRITE_EFFECTS}
                    uncertain = db.execute("SELECT route FROM attempts WHERE status IN ('dispatch_started','outcome_unknown','service_write_not_confirmed')").fetchall()
                    if any(item[0] in write_ids for item in uncertain): _fail('broker_uncertain_write_barrier')
                if route['effect'] == 'mutation' and self.precondition is not None:
                    stage = self.precondition.stage_for_request(method, route['path'], body)
                    self.precondition.check_before_mutation(stage=stage, request_body=body)
                    self.check(); self._check_dynamic(route, headers)
                if route['effect'] == 'state_write':
                    contract = self.state_contracts[route['id']]
                    if type(contract) is ComputedNativeStateWriteContract:
                        if self.graph_completion is None: self.graph_completion = self.precondition.completion()
                        admitted = contract.admit(body, completion=self.graph_completion)
                    else: admitted = contract.admit(body)
                    self.state_admissions[route['id']] = admitted
                    self.check(); self._check_dynamic(route, headers)
                cursor = db.execute('INSERT INTO attempts(route,request_sha256,status) VALUES (?,?,?)',
                    (route['id'], digest({'host': host, 'method': method, 'target': target, 'body_sha256': hashlib.sha256(body).hexdigest()}), 'dispatch_started'))
                sequence = cursor.lastrowid
                if route['effect'] in ('lease', 'lock_metadata'):
                    db.execute('INSERT INTO native_lease_requests VALUES (?,?,?,?,?,?)', (sequence, host, route['path'],
                        route['headers'].get('x-ms-lease-action', 'metadata_set' if 'x-ms-meta-terraformlockid' in headers else 'metadata_clear'),
                        headers.get('x-ms-proposed-lease-id', headers.get('x-ms-lease-id', '')),
                        headers.get('x-ms-meta-terraformlockid')))
                db.commit()
        try:
            self.check()
            timeout = min(10, self.policy['expires_at'] - time.time())
            if timeout <= 0: _fail('broker_expired')
            forwarded_body = self.credentials.replace(self.policy, route, body) if route['effect'] == 'oauth' and self.credentials is not None else body
            response = self.upstream.request(host, method, target, {**headers, 'accept-encoding': 'identity'}, forwarded_body, timeout=timeout)
            self.check()
            if (type(response) is not ib.ServiceResponse or type(response.status) is not int or
                    not 200 <= response.status <= 599 or 300 <= response.status <= 399 or
                    type(response.body) is not bytes or len(response.body) > MAX_RESPONSE or
                    type(response.headers) is not tuple or len(response.headers) > 100):
                _fail('broker_upstream_response_invalid')
            normalized = {}
            for pair in response.headers:
                if type(pair) is not tuple or len(pair) != 2 or any(type(v) is not str for v in pair):
                    _fail('broker_upstream_response_invalid')
                key, value = pair; key = key.lower()
                if key in normalized or not _HEADER.fullmatch(key) or any(ord(c) < 32 or ord(c) == 127 for c in value):
                    _fail('broker_upstream_response_invalid')
                normalized[key] = value
            if sum(len(k) + len(v) for k, v in normalized.items()) > 65536 or normalized.get('content-encoding') not in (None, 'identity'): _fail('broker_upstream_response_invalid')
            if route['effect'] == 'discovery' and response.status == 200:
                metadata = parse_json(response.body)
                tenant = self.policy['identities'][route['role']]['tenant_id']
                authority = 'https://' + route['host'] + '/' + tenant
                if type(metadata) is not dict: _fail('broker_discovery_response_invalid')
                if route['path'] == '/common/discovery/instance':
                    if metadata.get('tenant_discovery_endpoint') != authority + '/v2.0/.well-known/openid-configuration':
                        _fail('broker_discovery_response_invalid')
                    aliases = metadata.get('metadata', [])
                    if type(aliases) is not list or len(aliases) > 16: _fail('broker_discovery_response_invalid')
                    for entry in aliases:
                        if type(entry) is not dict: _fail('broker_discovery_response_invalid')
                        # The SDK's preferred network must not redirect credentials
                        # to an authority absent from this protected profile.
                        if route['host'] in entry.get('aliases', []) and entry.get('preferred_network') != route['host']:
                            _fail('broker_discovery_response_invalid')
                elif (metadata.get('token_endpoint') != authority + '/oauth2/v2.0/token' or
                        metadata.get('authorization_endpoint') != authority + '/oauth2/v2.0/authorize'):
                    _fail('broker_discovery_response_invalid')
            if route['effect'] == 'oauth' and response.status == 200:
                token = parse_json(response.body)
                if (type(token) is not dict or token.get('token_type') != 'Bearer' or
                        type(token.get('access_token')) is not str or not 1 <= len(token['access_token']) <= 32768 or
                        type(token.get('expires_in')) is not int or not 1 <= token['expires_in'] <= 86400):
                    _fail('broker_oauth_response_invalid')
                with self._lock:
                    self.tokens[hashlib.sha256(token['access_token'].encode()).hexdigest()] = (
                        route['role'], route['audience'], time.monotonic() + token['expires_in'])
            journal_status = 'response_received'
            if route['effect'] in _WRITE_EFFECTS and not 200 <= response.status < 300:
                journal_status = 'service_write_not_confirmed'
            with self._lock:
                key = (host, route['path'])
                if journal_status != 'response_received' and route['effect'] in ('lease', 'lock_metadata'):
                    self.leases.pop(key, None)
                if 200 <= response.status < 300 and route['effect'] == 'lease':
                    action = route['headers']['x-ms-lease-action']
                    if action == 'acquire':
                        proposal = headers.get('x-ms-proposed-lease-id')
                        if not proposal or normalized.get('x-ms-lease-id') != proposal: _fail('broker_native_lock_invalid')
                        self.leases[key] = {'id': proposal, 'operation': None}
                    else:
                        if normalized.get('x-ms-lease-id', headers.get('x-ms-lease-id')) != headers.get('x-ms-lease-id'):
                            self.leases.pop(key, None); _fail('broker_native_lock_invalid')
                        if action == 'release': self.leases.pop(key, None)
                if 200 <= response.status < 300 and route['effect'] == 'lock_metadata':
                    if key not in self.leases: _fail('broker_native_lock_invalid')
                    metadata = headers.get('x-ms-meta-terraformlockid')
                    self.leases[key]['operation'] = parse_json(base64.b64decode(metadata))['Operation'] if metadata else None
                    self.leases[key]['metadata'] = metadata
            with self._lock, self._database() as db:
                db.execute('UPDATE attempts SET status=?,response_code=?,response_sha256=? WHERE sequence=?',
                           (journal_status, response.status, hashlib.sha256(response.body).hexdigest(), sequence)); db.commit()
            return response
        except BaseException:
            with self._lock, self._database() as db:
                if route['effect'] in ('lease', 'lock_metadata'): self.leases.pop((host, route['path']), None)
                db.execute('UPDATE attempts SET status=? WHERE sequence=?', ('outcome_unknown', sequence)); db.commit()
            _fail('broker_upstream_outcome_unknown')


class _DeadlineReader:
    def __init__(self, connection, deadline):
        self.connection, self.deadline = connection, deadline
        self.stream = connection.makefile('rb', buffering=0)

    def read(self, maximum):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0: _fail('broker_http_deadline')
        self.connection.settimeout(min(10, remaining))
        return self.stream.read(maximum)

    def readline(self, maximum):
        data = bytearray()
        while len(data) < maximum:
            block = self.read(1)
            if not block: break
            data.extend(block)
            if block == b'\n': break
        return bytes(data)

    def close(self): self.stream.close()


def _read_body(stream, headers):
    """Decode the observed Kiota chunk framing before exact-body admission."""
    def exact(length):
        data = bytearray()
        while len(data) < length:
            block = stream.read(length - len(data))
            if not block: _fail('broker_http_invalid')
            data.extend(block)
        return bytes(data)
    encoding = headers.pop('transfer-encoding', None)
    if encoding is not None:
        if encoding != 'chunked' or 'content-length' in headers or 'trailer' in headers:
            _fail('broker_http_invalid')
        body = bytearray()
        for _ in range(4096):
            line = stream.readline(32)
            if not re.fullmatch(rb'[0-9A-Fa-f]{1,8}\r\n', line): _fail('broker_http_invalid')
            length = int(line[:-2], 16)
            if length == 0:
                if exact(2) != b'\r\n': _fail('broker_http_invalid')
                return bytes(body)
            if len(body) + length > MAX_REQUEST: _fail('broker_request_not_admitted')
            body.extend(exact(length))
            if exact(2) != b'\r\n': _fail('broker_http_invalid')
        _fail('broker_http_invalid')
    length = headers.pop('content-length', '0')
    if not re.fullmatch(r'0|[1-9][0-9]{0,6}', length) or int(length) > MAX_REQUEST:
        _fail('broker_request_not_admitted')
    return exact(int(length))


def _headers(stream):
    start = stream.readline(8193)
    if not start.endswith(b'\r\n') or len(start) > 8192: _fail('broker_http_invalid')
    try: method, target, version = start[:-2].decode('ascii').split(' ')
    except (ValueError, UnicodeError): _fail('broker_http_invalid')
    if version != 'HTTP/1.1': _fail('broker_http_invalid')
    result = {}; total = len(start)
    while True:
        line = stream.readline(8193); total += len(line)
        if total > 32768 or not line.endswith(b'\r\n') or len(line) > 8192 or len(result) > 64:
            _fail('broker_http_invalid')
        if line == b'\r\n': break
        try: key, value = line[:-2].decode('ascii').split(':', 1)
        except (ValueError, UnicodeError): _fail('broker_http_invalid')
        key = key.lower()
        if not _HEADER.fullmatch(key) or key in result or any(ord(c) < 32 or ord(c) == 127 for c in value):
            _fail('broker_http_invalid')
        result[key] = value.strip(' ')
    return method, target, result


class UnixBrokerServer:
    """One CONNECT plus one TLS request per connection, bounded peers/resources."""
    def __init__(self, path, broker, *, certificate, private_key):
        if type(broker) is not EgressBroker: _fail('broker_host_guard_required')
        self.path = Path(path).absolute(); _private(self.path.parent, directory=True)
        _private(certificate); _private(private_key)
        if self.path.exists() or self.path.is_symlink(): _fail('broker_socket_exists')
        self.broker = broker; self.stop = threading.Event(); self.slots = threading.BoundedSemaphore(4)
        self.connections = set(); self.connections_lock = threading.Lock()
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_cert_chain(str(certificate), str(private_key))
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.socket.bind(str(self.path)); self.path.chmod(0o600); self.socket.listen(4); self.socket.settimeout(0.2)
        except BaseException:
            self.socket.close(); raise

    def _connection(self, connection):
        stream = None; deadline = time.monotonic() + 20
        with self.connections_lock: self.connections.add(connection)
        try:
            connection.settimeout(10)
            _, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != self.broker.policy['worker_uid']: _fail('broker_peer_rejected')
            stream = _DeadlineReader(connection, deadline)
            method, target, headers = _headers(stream)
            hosts = {route['host'] for route in self.broker.policy['routes']}
            host = target.removesuffix(':443')
            if (method != 'CONNECT' or target != host + ':443' or host not in hosts or
                    headers.get('host') not in (host, target) or set(headers) - {'host', 'proxy-connection', 'user-agent'} or
                    headers.get('user-agent') not in (None, 'Go-http-client/1.1')):
                _fail('broker_connect_rejected')
            stream.close(); stream = None
            self.broker.check()
            connection.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            previous = connection
            connection = self.context.wrap_socket(connection, server_side=True, do_handshake_on_connect=False)
            with self.connections_lock:
                self.connections.discard(previous); self.connections.add(connection)
            connection.do_handshake()
            stream = _DeadlineReader(connection, deadline)
            method, target, headers = _headers(stream)
            if headers.get('host') not in (host, host + ':443'): _fail('broker_request_not_admitted')
            if headers.get('connection') == 'close': headers.pop('connection')
            body = _read_body(stream, headers)
            response = self.broker.handle(host, method, target, headers, body)
            output_headers = {k.lower(): v for k, v in response.headers if k.lower() in
                ('content-type', 'etag', 'x-ms-version', 'x-ms-blob-type', 'x-ms-request-id', 'x-ms-lease-id',
                 'request-id', 'retry-after', 'odata-version', 'www-authenticate', 'x-ms-meta-terraformlockid')}
            length = next((v for k, v in response.headers if k.lower() == 'content-length'), '0') if method == 'HEAD' else str(len(response.body))
            if not re.fullmatch(r'0|[1-9][0-9]{0,12}', length): _fail('broker_upstream_response_invalid')
            output_headers.update({'content-length': length, 'connection': 'close'})
            head = 'HTTP/1.1 ' + str(response.status) + ' Upstream\r\n' + ''.join(k + ': ' + v + '\r\n' for k, v in output_headers.items()) + '\r\n'
            connection.sendall(head.encode('ascii') + response.body)
        except (AppError, OSError, ValueError, sqlite3.Error):
            try: connection.sendall(b'HTTP/1.1 403 Denied\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            except OSError: pass
        finally:
            if stream is not None:
                try: stream.close()
                except OSError: pass
            with self.connections_lock: self.connections.discard(connection)
            connection.close(); self.slots.release()

    def serve(self):
        try:
            while not self.stop.is_set() and time.time() < self.broker.policy['expires_at']:
                try: connection, _ = self.socket.accept()
                except socket.timeout: continue
                except OSError:
                    if self.stop.is_set(): break
                    raise
                if not self.slots.acquire(blocking=False): connection.close(); continue
                threading.Thread(target=self._connection, args=(connection,), daemon=True, name='intune-egress-connection').start()
        finally: self.socket.close()

    def close(self):
        self.stop.set(); self.broker.closed = True; self.socket.close()
        with self.connections_lock:
            for connection in self.connections:
                try: connection.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                connection.close()
        # Preserve the socket path for explicit owner cleanup; never unlink an
        # unverified path that another process could have replaced.
