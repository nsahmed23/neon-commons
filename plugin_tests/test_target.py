"""Target consistency and fixed read-only collection never grant execution authority."""
import copy
import datetime as dt
import importlib.util
import json
import unittest
from unittest.mock import patch

SPEC = importlib.util.find_spec('intune_iac.target')
if SPEC is not None:
    from intune_iac import target

NOW = dt.datetime(2026, 9, 30, 12, 0, 0, tzinfo=dt.timezone.utc)
GUID = '11111111-1111-4111-8111-111111111111'
SUB = '22222222-2222-4222-8222-222222222222'
OTHER = '33333333-3333-4333-8333-333333333333'
RESOURCE = f'/subscriptions/{SUB}/resourceGroups/reference/providers/Microsoft.Storage/storageAccounts/syntheticstate'


def identity():
    return {'principal_object_id': GUID, 'client_id': OTHER,
            'auth_kind': 'workload_federation', 'federation': {
                'issuer': 'https://token.actions.githubusercontent.com',
                'subject': 'repo:example/infra:environment:lab',
                'audience': 'api://AzureADTokenExchange'}}


def fixture():
    return {'schema_version': 'target-evidence/1.0', 'observed_at': '2026-09-30T11:59:30Z',
            'binding': {
                'cloud': 'public', 'tenant_id': GUID, 'subscription_id': None,
                'endpoints': {'graph': 'https://graph.microsoft.com',
                              'authority': 'https://login.microsoftonline.com',
                              'management': 'https://management.azure.com',
                              'storage_audience': 'https://storage.azure.com/'},
                'identity': identity(),
                'repository': {'git_revision': 'a' * 40, 'dirty_files_sha256': 'b' * 64,
                               'source_sha256': 'c' * 64, 'configuration_sha256': 'd' * 64,
                               'logical_stack': 'lab-dev', 'physical_stack': 'deploy/dev',
                               'component': 'intune', 'implementation_path': 'components/terraform/intune',
                               'runtime_layers_sha256': 'e' * 64},
                'backend': {'type': 'azurerm', 'cloud': 'public', 'tenant_id': GUID,
                            'subscription_id': SUB, 'identity': identity(),
                            'storage_account_resource_id': RESOURCE,
                            'blob_endpoint': 'https://syntheticstate.blob.core.windows.net',
                            'container': 'tfstate', 'key': 'intune.tfstate',
                            'workspace': 'lab', 'resolved_blob_name': 'intune.tfstateenv:lab',
                            'state_lineage': OTHER, 'state_serial': 7, 'state_sha256': 'f' * 64},
                'ownership': {'mode': 'single_writer', 'writer_id': 'intune-ci',
                              'scope_sha256': 'a' * 64, 'lease_id': GUID,
                              'lease_expires_at': '2026-09-30T12:01:00Z'},
                'toolchain': {'atmos_version': '1.199.0', 'atmos_sha256': 'b' * 64,
                              'engine': 'tofu', 'engine_version': '1.10.0', 'engine_sha256': 'c' * 64,
                              'provider_source': 'deploymenttheory/microsoft365',
                              'provider_version': '1.0.0', 'provider_lock_sha256': 'd' * 64}}}


def leaves(value, prefix=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, prefix + (key,))
    else:
        yield prefix, value


def change(value, path, replacement):
    for key in path[:-1]: value = value[key]
    value[path[-1]] = replacement


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(SPEC, 'target evidence implementation is missing')
        self.clock = patch('intune_iac.target._now', return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_complete_document_is_consistent_but_never_authenticated(self):
        result = target.inspect_target(fixture())
        self.assertTrue(result['valid'])
        self.assertEqual(result['assurance'], 'supplied_consistency_only')
        self.assertFalse(result['execution_authorized'])
        self.assertIn('principal_not_authenticated', {x['code'] for x in result['blockers']})
        self.assertNotIn(GUID, json.dumps(result))

    def test_same_binding_matches_without_granting_authority(self):
        left, right = fixture(), fixture()
        right['observed_at'] = '2026-09-30T11:59:40Z'
        result = target.compare_targets(left, right)
        self.assertEqual(result['status'], 'match')
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(result['differences'], [])

    def test_every_binding_leaf_mutation_prevents_match(self):
        original = fixture()
        for path, old in leaves(original['binding']):
            with self.subTest(path=path):
                mutated = copy.deepcopy(original)
                new = old + '-changed' if isinstance(old, str) else 999 if type(old) is int else GUID
                change(mutated['binding'], path, new)
                result = target.compare_targets(original, mutated)
                self.assertNotEqual(result['status'], 'match')
                self.assertFalse(result['execution_authorized'])

    def test_every_required_leaf_omission_and_null_is_invalid(self):
        original = fixture()
        for path, old in leaves(original):
            for null in (False, True):
                if null and old is None: continue
                with self.subTest(path=path, null=null):
                    mutated = copy.deepcopy(original)
                    parent = mutated
                    for key in path[:-1]: parent = parent[key]
                    if null: parent[path[-1]] = None
                    else: del parent[path[-1]]
                    self.assertFalse(target.inspect_target(mutated)['valid'])

    def test_assurance_claim_and_nested_unknown_fields_are_rejected_without_echo(self):
        for path in ((), ('binding',), ('binding', 'identity'), ('binding', 'backend', 'identity')):
            document = fixture()
            parent = document
            for key in path: parent = parent[key]
            parent['SECRET_CANARY'] = 'authenticated'
            result = target.inspect_target(document)
            self.assertFalse(result['valid'])
            self.assertNotIn('SECRET_CANARY', json.dumps(result))

    def test_invalid_shapes_are_bounded_and_secret_free(self):
        cases = [None, [], {'SECRET_CANARY': 'x' * 100000}, {'schema_version': float('nan')}]
        cyclic = {}; cyclic['cycle'] = cyclic; cases.append(cyclic)
        for document in cases:
            result = target.inspect_target(document)
            self.assertFalse(result['valid'])
            self.assertNotIn('SECRET_CANARY', json.dumps(result))

    def test_wrong_origins_and_credentials_are_rejected(self):
        for value in ('https://graph.microsoft.com.evil.test', 'http://graph.microsoft.com',
                      'https://user:SECRET_CANARY@graph.microsoft.com',
                      'https://graph.microsoft.com/?token=SECRET_CANARY'):
            document = fixture(); document['binding']['endpoints']['graph'] = value
            self.assertFalse(target.inspect_target(document)['valid'])

    def test_backend_identity_and_resolved_workspace_are_independently_bound(self):
        document = fixture(); document['binding']['backend']['resolved_blob_name'] = 'lab/intune.tfstate'
        self.assertFalse(target.inspect_target(document)['valid'])
        document = fixture(); document['binding']['backend']['workspace'] = 'default'
        document['binding']['backend']['resolved_blob_name'] = 'intune.tfstate'
        self.assertTrue(target.inspect_target(document)['valid'])
        document['binding']['backend']['subscription_id'] = OTHER
        self.assertFalse(target.inspect_target(document)['valid'])

    def test_storage_origin_must_match_resource_account(self):
        document = fixture(); document['binding']['backend']['blob_endpoint'] = 'https://otheraccount.blob.core.windows.net'
        self.assertFalse(target.inspect_target(document)['valid'])

    def test_bad_ids_booleans_paths_and_federation_are_invalid(self):
        for path, value in [
            (('binding', 'tenant_id'), 'not-a-guid'),
            (('binding', 'backend', 'state_serial'), True),
            (('binding', 'backend', 'state_serial'), -1),
            (('binding', 'backend', 'workspace'), '../prod'),
            (('binding', 'repository', 'physical_stack'), '../prod'),
            (('binding', 'identity', 'federation'), None),
            (('binding', 'identity', 'federation', 'issuer'), 'https://issuer.test/?SECRET_CANARY'),
        ]:
            document = fixture(); change(document, path, value)
            self.assertFalse(target.inspect_target(document)['valid'])

    def test_certificate_identity_requires_null_federation(self):
        document = fixture(); document['binding']['identity']['auth_kind'] = 'application_certificate'
        self.assertFalse(target.inspect_target(document)['valid'])
        document['binding']['identity']['federation'] = None
        self.assertTrue(target.inspect_target(document)['valid'])

    def test_stale_future_or_expired_ownership_is_invalid(self):
        for timestamp in ('2026-09-30T11:00:00Z', '2026-09-30T12:00:31Z', 'bad', '2026-09-30T12:00:00'):
            document = fixture(); document['observed_at'] = timestamp
            self.assertFalse(target.inspect_target(document)['valid'])
        document = fixture(); document['binding']['ownership']['lease_expires_at'] = '2026-09-30T11:59:59Z'
        self.assertFalse(target.inspect_target(document)['valid'])

    def test_valid_changed_serial_reports_only_path(self):
        document = fixture(); document['binding']['backend']['state_serial'] += 1
        result = target.compare_targets(fixture(), document)
        self.assertEqual(result['status'], 'mismatch')
        self.assertEqual(result['differences'], [{'path': '/binding/backend/state_serial', 'reason': 'changed'}])

    def test_control_suffix_in_every_string_leaf_is_rejected(self):
        for path, old in leaves(fixture()):
            if not isinstance(old, str): continue
            for suffix in ('\n', '\r', '\x00', '\x7f'):
                document = fixture(); change(document, path, old + suffix)
                with self.subTest(path=path, suffix=repr(suffix)):
                    self.assertFalse(target.inspect_target(document)['valid'])

    def test_comparison_freezes_inputs_before_inspection(self):
        left, right = fixture(), fixture()
        original = target.inspect_target
        def mutate_after_inspection(snapshot):
            result = original(snapshot)
            right['binding']['backend']['state_serial'] = 999
            return result
        with patch('intune_iac.target.inspect_target', side_effect=mutate_after_inspection):
            result = target.compare_targets(left, right)
        self.assertEqual(result['status'], 'match')

    def test_inputs_are_not_mutated(self):
        document = fixture(); original = copy.deepcopy(document)
        target.inspect_target(document); target.compare_targets(document, document)
        self.assertEqual(document, original)


class Response:
    def __init__(self, value, status=200, headers=None):
        self.status = status
        self.data = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.headers = {'Content-Type': 'application/json', **(headers or {})}
    def getheader(self, key, default=None): return self.headers.get(key, default)
    def read(self, amount): return self.data[:amount]


class Connection:
    responses = []
    requests = []
    instances = []
    def __init__(self, host, **kwargs):
        self.host = host; self.kwargs = kwargs; self.stopped = False; self.instances.append(self)
    def request(self, method, path, headers=None):
        if self.stopped: raise OSError('deadline fired')
        self.requests.append((self.host, method, path, headers))
    def getresponse(self): return self.responses.pop(0)
    def close(self): pass
    def connect(self): self.sock = self
    def shutdown(self, how): self.stopped = True


class CollectionTests(unittest.TestCase):
    setUp = TargetTests.setUp
    def responses(self):
        return [Response({'value': [{'id': GUID}]}),
                Response({'subscriptionId': SUB, 'tenantId': GUID, 'state': 'Enabled'}),
                Response({'id': RESOURCE, 'name': 'syntheticstate',
                          'properties': {'primaryEndpoints': {'blob': 'https://syntheticstate.blob.core.windows.net/'}}})]

    def collect(self, responses=None, document=None, graph_token='GRAPH_CANARY'):
        Connection.responses = self.responses() if responses is None else responses
        Connection.requests = []
        with patch('intune_iac.target.http.client.HTTPSConnection', Connection):
            return target.collect_azure_observations(document or fixture(), graph_token=graph_token,
                                                     management_token='ARM_CANARY')

    def test_fixed_reads_observe_service_facts_but_not_principal_or_execution(self):
        result = self.collect()
        self.assertEqual(result['status'], 'observed')
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(len(result['observations']), 3)
        self.assertEqual([r[1] for r in Connection.requests], ['GET'] * 3)
        self.assertEqual([r[0] for r in Connection.requests],
                         ['graph.microsoft.com', 'management.azure.com', 'management.azure.com'])
        rendered = json.dumps(result)
        self.assertNotIn('GRAPH_CANARY', rendered); self.assertNotIn('ARM_CANARY', rendered)
        self.assertNotIn(GUID, rendered)
        self.assertIn('principal_not_authenticated', {x['code'] for x in result['blockers']})

    def test_post_connect_deadline_aborts_read_and_tls_is_verified(self):
        import ssl
        class ImmediateDeadline:
            def __init__(self, timeout, callback): self.callback = callback
            def start(self): self.callback()
            def cancel(self): pass
        with patch('threading.Timer', ImmediateDeadline):
            result = self.collect()
        self.assertEqual(result['status'], 'unavailable')
        context = Connection.instances[-1].kwargs['context']
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_collection_freezes_input_before_transport(self):
        document = fixture()
        original = target.inspect_target
        def mutate_after_inspection(snapshot):
            result = original(snapshot)
            document['binding']['backend']['storage_account_resource_id'] = '/UNVALIDATED'
            return result
        with patch('intune_iac.target.inspect_target', side_effect=mutate_after_inspection):
            result = self.collect(document=document)
        self.assertEqual(result['status'], 'observed')
        self.assertIn(RESOURCE, Connection.requests[-1][2])
        self.assertNotIn('UNVALIDATED', Connection.requests[-1][2])

    def test_invalid_target_and_header_token_stop_before_any_request(self):
        document = fixture(); document['binding']['cloud'] = 'unknown'
        self.assertEqual(self.collect(document=document)['status'], 'invalid')
        self.assertEqual(Connection.requests, [])
        self.assertEqual(self.collect(graph_token='x\r\nSECRET_CANARY')['status'], 'invalid')
        self.assertEqual(Connection.requests, [])

    def test_denied_redirect_and_malformed_response_remain_unavailable(self):
        for response in (Response({'error': 'SECRET_CANARY'}, 403),
                         Response({}, 302, {'Location': 'https://evil.test'}),
                         Response(b'not json SECRET_CANARY'),
                         Response({'value': []}), Response({'value': [{'id': OTHER}]}),
                         Response({'value': [{'id': GUID}], '@odata.nextLink': 'https://evil.test'})):
            result = self.collect(responses=[response])
            self.assertEqual(result['status'], 'unavailable')
            self.assertEqual(len(Connection.requests), 1)
            self.assertNotIn('SECRET_CANARY', json.dumps(result))

    def test_oversized_and_encoded_response_rejected(self):
        for response in (Response(b'x' * (1024 * 1024 + 1)),
                         Response({'value': [{'id': GUID}]}, headers={'Content-Encoding': 'gzip'})):
            self.assertEqual(self.collect(responses=[response])['status'], 'unavailable')

    def test_backend_tenant_or_storage_endpoint_mismatch_cannot_pass(self):
        responses = self.responses(); responses[1] = Response({'subscriptionId': SUB, 'tenantId': OTHER, 'state': 'Enabled'})
        self.assertEqual(self.collect(responses=responses)['status'], 'unavailable')
        responses = self.responses(); responses[2] = Response({'id': RESOURCE, 'name': 'syntheticstate',
                                  'properties': {'primaryEndpoints': {'blob': 'https://evil.test/'}}})
        self.assertEqual(self.collect(responses=responses)['status'], 'unavailable')

    def test_transport_exception_never_echoes_exception_or_token(self):
        with patch('intune_iac.target.http.client.HTTPSConnection', side_effect=OSError('SECRET_CANARY')):
            result = target.collect_azure_observations(fixture(), graph_token='GRAPH_CANARY', management_token='ARM_CANARY')
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn('CANARY', json.dumps(result))


if __name__ == '__main__': unittest.main()
