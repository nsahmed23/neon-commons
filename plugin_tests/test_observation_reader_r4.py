"""Reader identity/scope and atomic publication; no live Graph qualification."""
import copy
import pickle
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from intune_iac.identity_binding import ClientSecretHandle
from intune_iac.io import AppError, canonical
from intune_iac.observation_reader import (
    CapturedObservation, LaboratoryGraphReader, LiveGraphReader, ReaderSpec,
    bind_laboratory_reader, publish_batch)
from intune_iac.observation_jobs import _Fixture
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore

CLIENT = '11111111-1111-4111-8111-111111111111'
PRINCIPAL = '33333333-3333-4333-8333-333333333333'
SECRET = 'R4-LOCAL-READER-SECRET-CANARY'
TOKEN = 'R4-LOCAL-READER-TOKEN-CANARY'


def fixture_for(estate, object_ids=None):
    tenant = estate['truth']['tenant_id']
    ids = object_ids or [item['id'] for item in estate['truth']['policies']]
    rows = [dict(method='POST', host='login.microsoftonline.com', path='/' + tenant + '/oauth2/v2.0/token',
                 status=200, body={'token_type': 'Bearer', 'expires_in': 3600, 'access_token': TOKEN}),
            dict(method='GET', host='graph.microsoft.com',
                 path="/v1.0/servicePrincipals(appId='" + CLIENT + "')?$select=id,appId,accountEnabled",
                 status=200, body={'id': PRINCIPAL, 'appId': CLIENT, 'accountEnabled': True})]
    for oid in ids:
        for kind in ('policies', 'settings', 'assignments'):
            collection = next(item for item in estate['capture']['collections']
                              if item['kind'] == kind and item['owner_id'] == (None if kind == 'policies' else oid))
            for page in collection['pages']:
                url = urlsplit(page['request_url'])
                body = copy.deepcopy(page['body'])
                if kind == 'assignments':
                    # Real-shaped assignments explicitly state this field;
                    # the product must never infer it from a synthetic seed.
                    for assignment in body['value']:
                        assignment.update(source='direct', sourceId=None)
                rows.append(dict(method='GET', host='graph.microsoft.com',
                    path=url.path + ('?' + url.query if url.query else ''), status=200, body=body))
    return {'schema_version': 'intune-observer-fixture/1', 'responses': rows}


class ObservationReaderR4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.estate = generate_estate(seed=840, policy_count=1)
        self.tenant = self.estate['truth']['tenant_id']
        self.oid = self.estate['truth']['policies'][0]['id']
        self.spec = ReaderSpec(self.tenant, CLIENT, PRINCIPAL, (self.oid,))
        self.store = WorkbenchStore.create(self.root / 'store', self.tenant)

    def reader(self, fixture=None, **kwargs):
        transport = _Fixture(canonical(fixture or fixture_for(self.estate)))
        credential = ClientSecretHandle(SECRET)
        self.addCleanup(credential.close)
        reader = bind_laboratory_reader(self.spec, credential=credential, transport=transport, **kwargs)
        self.addCleanup(reader.close)
        return reader, transport, credential

    def captured(self, name='capture', fixture=None):
        reader, transport, _ = self.reader(fixture)
        return reader.capture(self.oid, self.root / name), reader, transport

    def publish(self, item, attempt='b' * 32):
        return publish_batch(self.store, [item], job_id='a' * 32, attempt_id=attempt)

    def counts(self):
        with sqlite3.connect(self.store.path) as db:
            return tuple(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                         for table in ('collection_runs', 'observations', 'snapshots'))

    def test_laboratory_capability_has_no_route_to_live_or_json_authority(self):
        captured, reader, transport = self.captured()
        self.assertIs(type(reader), LaboratoryGraphReader)
        self.assertFalse(reader.evidence()['source_authenticity_verified'])
        result = self.publish(captured)[0]
        self.assertEqual(result['evidence_class'], 'graph_reader_laboratory')
        self.assertFalse(result['assurance']['source_authenticity_verified'])
        self.assertEqual(transport.position, len(transport.rows))
        with self.assertRaises(AppError):
            LiveGraphReader(None, self.spec, None, None, None, None, None, None)
        with self.assertRaises(AppError):
            self.publish({'source_authenticity_verified': True})
        with self.assertRaises(TypeError):
            pickle.dumps(reader)
        with self.assertRaises(TypeError):
            pickle.dumps(captured)

    def test_wrong_principal_rejected_before_policy_requests(self):
        fixture = fixture_for(self.estate)
        fixture['responses'][1]['body']['id'] = CLIENT
        transport = _Fixture(canonical(fixture))
        credential = ClientSecretHandle(SECRET)
        with self.assertRaises(AppError) as raised:
            bind_laboratory_reader(self.spec, credential=credential, transport=transport)
        credential.close()
        self.assertEqual(raised.exception.code, 'reader_principal_mismatch')
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_token_expiry_and_credential_revocation_stop_before_capture(self):
        clock = [0.0]
        reader, transport, credential = self.reader(clock=lambda: clock[0], max_duration_seconds=5)
        clock[0] = 5.0
        with self.assertRaises(AppError) as raised:
            reader.capture(self.oid, self.root / 'expiry')
        self.assertEqual(raised.exception.code, 'reader_expired')
        self.assertEqual(len(transport.requests), 2)
        second, transport, credential = self.reader()
        credential.close()
        with self.assertRaises(AppError):
            second.capture(self.oid, self.root / 'revoked')
        self.assertEqual(len(transport.requests), 2)

    def test_scope_rejected_before_unselected_request(self):
        reader, transport, _ = self.reader()
        with self.assertRaises(AppError) as raised:
            reader.capture(CLIENT, self.root / 'wrong')
        self.assertEqual(raised.exception.code, 'reader_scope_mismatch')
        self.assertEqual(len(transport.requests), 2)

    def test_cross_origin_assignment_page_is_never_requested(self):
        fixture = fixture_for(self.estate)
        fixture['responses'][4]['body']['@odata.nextLink'] = 'https://outside.invalid/collect'
        captured, _, transport = self.captured(fixture=fixture)
        result = self.publish(captured)[0]
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(all(item['host'] in ('login.microsoftonline.com', 'graph.microsoft.com') for item in transport.requests))
        self.assertEqual(len(transport.requests), 5)
        self.assertEqual(self.counts(), (1, 0, 0))

    def test_denied_assignment_retains_last_good_exact_body(self):
        first, _, _ = self.captured()
        self.publish(first)
        before = self.store.inspect(self.oid)['body']
        fixture = fixture_for(self.estate)
        fixture['responses'][4].update(status=403, body={'error': {'code': 'Denied'}})
        denied, _, _ = self.captured('denied', fixture)
        result = self.publish(denied, 'c' * 32)[0]
        self.assertEqual(result['status'], 'denied')
        self.assertEqual(self.store.inspect(self.oid)['body'], before)
        self.assertEqual(len(self.store.history(self.oid)), 1)
        self.assertEqual(self.store.inspect(self.oid)['freshness'], 'stale')

    def test_identical_retry_is_idempotent_and_conflicting_retry_fails(self):
        first, _, _ = self.captured()
        original = self.publish(first)
        self.assertEqual(self.publish(first), original)
        self.assertEqual(self.counts(), (1, 1, 1))
        second, _, _ = self.captured('second')
        with self.assertRaises(AppError) as raised:
            self.publish(second)
        self.assertEqual(raised.exception.code, 'reader_publication_conflict')
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_changed_staged_bytes_do_not_publish(self):
        captured, _, _ = self.captured()
        path = self.root / 'capture' / 'raw' / 'page-000000.json'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaises(AppError):
            self.publish(captured)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_same_capture_new_attempt_retains_attempt_without_inventing_history(self):
        first, _, _ = self.captured()
        first_run = self.publish(first)[0]
        second = self.publish(first, 'c' * 32)[0]
        self.assertNotEqual(first_run['run_id'], second['run_id'])
        self.assertEqual(second['source']['duplicate_of_run_id'], first_run['run_id'])
        self.assertEqual(self.counts(), (2, 1, 1))
        self.assertEqual(self.publish(first, 'c' * 32)[0], second)

    def test_atomic_publication_rolls_back_run_coverage_and_snapshot(self):
        captured, _, _ = self.captured()
        real = self.store._store_objects
        def broken(*args, **kwargs):
            real(*args, **kwargs)
            raise AppError('deliberate_publication_failure', 'Deliberate test failure')
        with patch.object(self.store, '_store_objects', broken), self.assertRaises(AppError):
            self.publish(captured)
        self.assertEqual(self.counts(), (0, 0, 0))
        with sqlite3.connect(self.store.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM collection_coverage').fetchone()[0], 0)
        self.publish(captured)
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_out_of_order_snapshot_cannot_replace_newer_observation(self):
        with patch('intune_iac.capture._stamp', return_value='2026-10-07T12:00:00Z'):
            newer, _, _ = self.captured('newer')
        self.publish(newer)
        before = self.store.inspect(self.oid)['body']
        fixture = fixture_for(self.estate)
        fixture['responses'][2]['body']['value'][0]['description'] = 'An older snapshot arriving later'
        with patch('intune_iac.capture._stamp', return_value='2026-10-06T12:00:00Z'):
            older, _, _ = self.captured('older', fixture)
        self.publish(older, 'd' * 32)
        self.assertEqual(self.store.inspect(self.oid)['body'], before)
        self.assertEqual(len(self.store.history(self.oid)), 2)

    def test_secrets_not_in_capture_store_or_public_result(self):
        captured, _, _ = self.captured()
        result = self.publish(captured)
        payloads = [canonical(result), self.store.path.read_bytes()]
        payloads.extend(path.read_bytes() for path in (self.root / 'capture').rglob('*') if path.is_file())
        for payload in payloads:
            self.assertNotIn(SECRET.encode(), payload)
            self.assertNotIn(TOKEN.encode(), payload)

    def test_plain_capture_import_never_inherits_reader_assurance(self):
        self.captured()
        result = self.store.import_capture(self.root / 'capture')
        self.assertEqual(result['evidence_class'], 'graph_capture_unverified')
        self.assertFalse(result['assurance']['source_authenticity_verified'])


if __name__ == '__main__':
    unittest.main()
