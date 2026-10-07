"""Actual capture/SQLite with recorded Win32 effects; never native qualification."""
import copy
import pickle
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from intune_iac.io import AppError,canonical
from intune_iac.identity_binding import ClientSecretHandle
from intune_iac.observation_jobs import _Fixture
from intune_iac.synthetic import generate_estate
from intune_iac import observation_reader as reader,windows_observation as subject,windows_workbench as ww
from plugin_tests.test_observation_reader_r4 import fixture_for,CLIENT,PRINCIPAL,SECRET
from plugin_tests.test_windows_workbench_r4 import FilesystemAPI,ROOT,CANONICAL

class NativeObservationContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.api=FilesystemAPI(Path(self.temp.name)/'files');self.fs=ww._Filesystem(self.api,self.api.connect)
        self.estate=generate_estate(seed=840,policy_count=1);self.tenant=self.estate['truth']['tenant_id']
        self.oid=self.estate['truth']['policies'][0]['id'];self.spec=reader.ReaderSpec(self.tenant,CLIENT,PRINCIPAL,(self.oid,))
        self.store=ww.WindowsWorkbenchStore._create(ROOT+'\\store',self.tenant,self.fs)
        self.target=subject._bind_laboratory_target(self.store);self.addCleanup(self.target.close)
        self.database=self.api.real(CANONICAL+'\\store\\observations.sqlite3')
    def make_reader(self,fixture=None):
        transport=_Fixture(canonical(fixture or fixture_for(self.estate)))
        credential=ClientSecretHandle(SECRET);self.addCleanup(credential.close)
        value=reader.bind_laboratory_reader(self.spec,credential=credential,transport=transport);self.addCleanup(value.close)
        return value,transport
    def capture(self,name='capture',fixture=None):
        value,transport=self.make_reader(fixture)
        return self.target.capture(value,self.oid,ROOT+'\\'+name),transport
    def publish(self,value,attempt='b'*32):return self.target.publish([value],job_id='a'*32,attempt_id=attempt)
    def counts(self):
        with sqlite3.connect(self.database) as db:
            return tuple(db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ('collection_runs','observations','snapshots'))
    def test_capture_exact_raw_and_same_atomic_engine_without_authority_promotion(self):
        item,transport=self.capture();result=self.publish(item)[0]
        self.assertEqual(result['status'],'complete');self.assertEqual(self.counts(),(1,1,1))
        self.assertEqual(result['evidence_class'],'graph_reader_laboratory');self.assertFalse(result['assurance']['source_authenticity_verified'])
        raw=self.api.real(CANONICAL+'\\capture\\raw')
        self.assertEqual(sorted(p.name for p in raw.iterdir()),['page-000000.json','page-000001.json','page-000002.json','page-000003.json','page-000004.json'])
        self.assertEqual((raw/'page-000000.json').read_bytes(),canonical(fixture_for(self.estate)['responses'][2]['body']))
        self.assertEqual(len(transport.requests),7);self.assertEqual(self.api.handles,{})
        status=self.store.storage_status();self.assertEqual(status['unresolved_intents'],[])
        self.assertEqual({r['kind'] for r in status['outcomes']},{'sqlite_connection','observation_publication'})
    def test_denied_assignments_preserve_last_good_and_attempt(self):
        good,_=self.capture();self.publish(good);before=self.store.inspect(self.oid)['body']
        fixture=fixture_for(self.estate);fixture['responses'][4].update(status=403,body={'error':{'code':'Denied'}})
        denied,_=self.capture('denied',fixture);result=self.publish(denied,'c'*32)[0]
        self.assertEqual(result['status'],'denied');self.assertEqual(self.store.inspect(self.oid)['body'],before)
        self.assertEqual(self.counts(),(2,1,1));self.assertEqual(self.api.handles,{})
    def test_cross_origin_pagination_records_partial_without_request(self):
        fixture=fixture_for(self.estate);fixture['responses'][4]['body']['@odata.nextLink']='https://outside.invalid/x'
        item,transport=self.capture(fixture=fixture);result=self.publish(item)[0]
        self.assertEqual(result['status'],'partial');self.assertEqual(self.counts(),(1,0,0));self.assertEqual(len(transport.requests),5)
    def test_replay_same_capability_is_idempotent_new_attempt_retains_attempt_not_history(self):
        item,_=self.capture();first=self.publish(item);self.assertEqual(self.publish(item),first)
        second=self.publish(item,'c'*32)[0];self.assertEqual(second['source']['duplicate_of_run_id'],first[0]['run_id'])
        self.assertEqual(self.counts(),(2,1,1))
    def test_source_mutation_cannot_promote_laboratory_or_publish(self):
        item,_=self.capture();item._source.update(evidence_class='graph_authenticated_observation',source_authenticity_verified=True,source_is_synthetic=False)
        with self.assertRaises(AppError) as caught:self.publish(item)
        self.assertEqual(caught.exception.code,'reader_capture_changed');self.assertEqual(self.counts(),(0,0,0))
    def test_target_substitution_and_serialized_metadata_rejected(self):
        item,_=self.capture();second=subject._bind_laboratory_target(self.store)
        with self.assertRaises(AppError) as caught:second.publish([item],job_id='a'*32,attempt_id='b'*32)
        self.assertEqual(caught.exception.code,'windows_observer_capture_target_mismatch')
        with self.assertRaises(AppError):self.publish({'source_authenticity_verified':True})
        for value in (self.target,self.target._storage,item):
            with self.assertRaises(TypeError):pickle.dumps(value)
        self.assertEqual(self.counts(),(0,0,0))
    def test_public_posix_publisher_does_not_widen_store_type_gate(self):
        item,_=self.capture()
        with self.assertRaises(AppError) as caught:reader.publish_batch(self.store,[item],job_id='a'*32,attempt_id='b'*32)
        self.assertEqual(caught.exception.code,'reader_publication_invalid');self.assertEqual(self.counts(),(0,0,0))
    def test_posix_public_route_cannot_relocate_native_bound_capture(self):
        from intune_iac.workbench_store import WorkbenchStore
        item,_=self.capture();other=WorkbenchStore.create(Path(self.temp.name)/'other-posix-store',self.tenant)
        with self.assertRaises(AppError) as caught:reader.publish_batch(other,[item],job_id='a'*32,attempt_id='b'*32)
        self.assertEqual(caught.exception.code,'reader_publication_invalid')
        with sqlite3.connect(other.path) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM collection_runs').fetchone()[0],0)
        self.assertEqual(self.counts(),(0,0,0))

    def test_live_typed_reader_rejected_by_lab_storage_before_policy_get(self):
        value,transport=self.make_reader()
        # Constructor injection here is a recorded test only; no native TLS or live claim.
        live=reader.LiveGraphReader(reader._LIVE,value._spec,value._credential,value._transport,value._clock,value._token,value._expiry,value._identity)
        with self.assertRaises(AppError) as caught:self.target.capture(live,self.oid,ROOT+'\\must-not-create')
        self.assertEqual(caught.exception.code,'windows_observer_live_to_laboratory_forbidden')
        self.assertEqual(len(transport.requests),2);self.assertFalse(self.api.real(CANONICAL+'\\must-not-create').exists())
    def test_wrong_tenant_and_changed_store_root_rejected_before_capture(self):
        value,transport=self.make_reader();self.store.tenant_id=CLIENT
        with self.assertRaises(AppError):self.target.capture(value,self.oid,ROOT+'\\must-not-create')
        self.assertEqual(len(transport.requests),2);self.assertEqual(self.counts(),(0,0,0))
    def test_actual_replaced_database_identity_rejected_before_mutation(self):
        item,_=self.capture();replacement=self.database.with_name('new.sqlite3');replacement.write_bytes(self.database.read_bytes());replacement.replace(self.database)
        with self.assertRaises(AppError) as caught:self.publish(item)
        self.assertEqual(caught.exception.code,'windows_observer_target_changed');self.assertEqual(self.counts(),(0,0,0))
    def test_changed_capture_bytes_rejected_before_publication(self):
        item,_=self.capture();path=self.api.real(CANONICAL+'\\capture\\raw\\page-000000.json');path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(AppError):self.publish(item)
        self.assertEqual(self.counts(),(0,0,0))
    def test_failure_after_storing_objects_rolls_back_every_table_and_retains_intent(self):
        item,_=self.capture();real=self.store._store_objects
        def fail(*args,**kwargs):real(*args,**kwargs);raise AppError('injected_publication_failure','fixture')
        with patch.object(self.store,'_store_objects',fail),self.assertRaises(AppError):self.publish(item)
        self.assertEqual(self.counts(),(0,0,0))
        with sqlite3.connect(self.database) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM collection_coverage').fetchone()[0],0)
        self.assertEqual(len(self.store.storage_status()['unresolved_intents']),2);self.assertEqual(self.api.handles,{})
    def test_possible_commit_then_outcome_write_failure_is_uncertain_retained(self):
        item,_=self.capture();self.api.fail_creation='store-outcome-'
        with self.assertRaises(AppError) as caught:self.publish(item)
        self.assertEqual(caught.exception.code,'fixture_disk_full');self.assertTrue(caught.exception.observation_outcome['outcome_uncertain'])
        self.assertTrue(caught.exception.storage_outcome['outcome_uncertain']);self.assertEqual(self.counts(),(1,1,1))
        self.assertEqual(len(self.store.storage_status()['unresolved_intents']),2);self.assertEqual(self.api.handles,{})
    def test_cancelled_native_output_retains_attempted_bytes_and_primary(self):
        value,transport=self.make_reader();self.api.failure='write-interrupt'
        with self.assertRaises(KeyboardInterrupt) as caught:self.target.capture(value,self.oid,ROOT+'\\interrupted')
        self.assertTrue(caught.exception.storage_outcome['outcome_uncertain'])
        self.assertTrue(self.api.real(CANONICAL+'\\interrupted\\raw\\page-000000.json').exists())
        self.assertEqual(self.counts(),(0,0,0));self.assertEqual(self.api.handles,{})
    def test_missing_namespace_barrier_retains_output_and_prevents_service_reads(self):
        value,transport=self.make_reader();self.api.failure='namespace'
        with self.assertRaises(AppError) as caught:self.target.capture(value,self.oid,ROOT+'\\uncertain')
        self.assertEqual(caught.exception.code,'windows_storage_namespace_flush_unavailable');self.assertTrue(caught.exception.storage_outcome['outcome_uncertain'])
        self.assertTrue(self.api.real(CANONICAL+'\\uncertain').exists());self.assertEqual(len(transport.requests),2)
    def test_closed_target_cannot_reuse_previous_capability(self):
        item,_=self.capture();self.target.close()
        with self.assertRaises(AppError) as caught:self.publish(item)
        self.assertEqual(caught.exception.code,'windows_observer_closed');self.assertEqual(self.counts(),(0,0,0))
    def test_sqlite_concurrent_writer_does_not_publish_partial_batch(self):
        original=self.fs.connect
        def quick(database,**kwargs):kwargs['timeout']=0.01;return original(database,**kwargs)
        self.fs.connect=quick;self.target=subject._bind_laboratory_target(self.store)
        item,_=self.capture();blocker=sqlite3.connect(self.database);blocker.execute('BEGIN IMMEDIATE')
        try:
            with self.assertRaises(sqlite3.OperationalError):self.publish(item)
        finally:blocker.rollback();blocker.close()
        self.assertEqual(self.counts(),(0,0,0));self.publish(item);self.assertEqual(self.counts(),(1,1,1))
    def test_transaction_revalidates_tenant_after_begin_before_mutation(self):
        item,_=self.capture();original=subject._Target._validate_transaction
        def changed(target,db):
            db.execute("UPDATE metadata SET value=? WHERE key='tenant_id'",(CLIENT,))
            original(target,db)
        with patch.object(subject._Target,'_validate_transaction',changed),self.assertRaises(AppError) as caught:self.publish(item)
        self.assertEqual(caught.exception.code,'windows_observer_wrong_tenant');self.assertEqual(self.counts(),(0,0,0))
        with sqlite3.connect(self.database) as db:self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='tenant_id'").fetchone()[0],self.tenant)
    def test_throttling_exhaustion_retains_every_raw_attempt(self):
        fixture=fixture_for(self.estate);retry=copy.deepcopy(fixture['responses'][2])
        retry.update(status=429,body={'error':{'code':'TooManyRequests'}},headers=[['Retry-After','0']])
        fixture['responses']=fixture['responses'][:2]+[copy.deepcopy(retry) for _ in range(3)]
        item,transport=self.capture(fixture=fixture);result=self.publish(item)[0]
        self.assertEqual(result['status'],'partial');self.assertEqual(self.counts(),(1,0,0))
        self.assertEqual(len(list(self.api.real(CANONICAL+'\\capture\\raw').iterdir())),3)
        self.assertEqual(len(transport.requests),5)
    def test_older_capture_never_replaces_current_body(self):
        with patch('intune_iac.capture._stamp',return_value='2026-10-07T12:00:00Z'):newer,_=self.capture('newer')
        self.publish(newer);before=self.store.inspect(self.oid)['body']
        fixture=fixture_for(self.estate);fixture['responses'][2]['body']['value'][0]['description']='Older observation'
        with patch('intune_iac.capture._stamp',return_value='2026-10-06T12:00:00Z'):older,_=self.capture('older',fixture)
        self.publish(older,'d'*32);self.assertEqual(self.store.inspect(self.oid)['body'],before);self.assertEqual(len(self.store.history(self.oid)),2)

    def test_posix_output_cleanup_preserves_primary_and_attempts_all_owned_closes(self):
        from intune_iac import capture as capture_module
        primary=AppError('primary_capture_failure','fixture');closed=[]
        def failing_close(handle):
            closed.append(handle)
            if handle==21:raise KeyboardInterrupt()
        with (patch.object(capture_module,'_new_directory',return_value=(Path('/fixture'),20)),
                patch.object(capture_module.os,'mkdir'),patch.object(capture_module.os,'open',return_value=21),
                patch.object(capture_module.os,'fchmod'),patch.object(capture_module.os,'close',side_effect=failing_close)):
            with self.assertRaises(AppError) as caught:
                with capture_module._posix_output('/fixture'):raise primary
        self.assertIs(caught.exception,primary);self.assertEqual(closed,[21,20])
        self.assertEqual(primary.capture_cleanup_failures,['KeyboardInterrupt'])

    def test_public_native_target_remains_blocked_before_filesystem_on_linux(self):
        if sys.platform=='win32':self.skipTest('Linux guard assertion')
        with self.assertRaises(AppError) as caught:subject.bind_native_target(ROOT+'\\store',self.tenant)
        self.assertEqual(caught.exception.code,'windows_directory_platform_unsupported')

if __name__=='__main__':unittest.main()
