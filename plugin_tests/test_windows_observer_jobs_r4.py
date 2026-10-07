"""Actual finite job/store/capture interfaces with recorded Win32 effects only."""
from contextlib import contextmanager
import copy
import hashlib
import pickle
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from intune_iac import windows_observation_jobs as jobs,windows_observer_credentials as credentials
from intune_iac import windows_observation as target_api,windows_workbench as ww,windows_storage as ws
from intune_iac.io import AppError,canonical,parse_json,digest
from intune_iac.observation_reader import ReaderSpec
from intune_iac.synthetic import generate_estate
from plugin_tests.test_observation_reader_r4 import fixture_for,CLIENT,PRINCIPAL
from plugin_tests.test_windows_workbench_r4 import FilesystemAPI,ROOT,CANONICAL
from plugin_tests.test_windows_storage_r4 import SID

class CredentialAPI:
 def __init__(self,reference):
  self.reference=reference;self.sid=reference.owner_sid;self.calls=0;self.closed=0
  self.row={'flags':0,'type':1,'target':reference.target,'username':reference.client_id,'persist':2,'attribute_count':0,'alias':None,'blob':b'SYNTHETIC-EXISTING-ENTRY-SECRET'}
 def current_sid(self):return self.sid
 @contextmanager
 def read(self,target):
  self.calls+=1
  try:yield self.row
  finally:self.closed+=1

class CredentialContracts(unittest.TestCase):
 def setUp(self):
  self.reference=credentials.CredentialReference('IntuneWorkbench/observer/pilot',SID,CLIENT);self.api=CredentialAPI(self.reference)
 def source(self):return credentials._bind_laboratory_credential(self.reference,self.api)
 def test_explicit_entry_read_is_lazy_closes_handle_and_never_serializes(self):
  source=self.source();self.assertEqual(self.api.calls,0)
  with source.acquire() as secret:self.assertEqual(secret._get(),'SYNTHETIC-EXISTING-ENTRY-SECRET');self.assertNotIn('SECRET',repr(source));self.assertNotIn('SECRET',repr(secret))
  self.assertEqual((self.api.calls,self.api.closed),(1,1))
  with self.assertRaises(AppError):secret._get()
  with self.assertRaises(TypeError):pickle.dumps(source)
 def test_wrong_sid_rejected_before_credential_lookup(self):
  self.api.sid='S-1-5-18'
  with self.assertRaises(AppError):self.source()
  self.assertEqual(self.api.calls,0)
 def test_wrong_target_username_type_persistence_or_attributes_rejected(self):
  for field,value in [('target','Other'),('username',PRINCIPAL),('type',2),('type',True),('persist',3),('attribute_count',1),('flags',1),('alias','alias')]:
   with self.subTest(field=field,value=value):
    api=CredentialAPI(self.reference);api.row[field]=value;source=credentials._bind_laboratory_credential(self.reference,api)
    with self.assertRaises(AppError):
     with source.acquire():self.fail('unbound credential admitted')
    self.assertEqual(api.closed,1)
 def test_bad_blob_does_not_fall_back_to_environment_or_expose_bytes(self):
  for value in (b'',b'x'*4097,b'with space',b'\xff',b'line\nSECRET'):
   with self.subTest(value=value[:8]):
    self.api.row['blob']=value
    with self.assertRaises(AppError) as caught:
     with self.source().acquire():self.fail('bad secret admitted')
    self.assertNotIn('SECRET',str(caught.exception))
 def test_closed_or_sid_rebound_source_cannot_reacquire(self):
  source=self.source();source.close()
  with self.assertRaises(AppError):
   with source.acquire():self.fail('closed source')
  self.assertEqual(self.api.calls,0)
 def test_public_native_source_is_unavailable_on_linux_before_read(self):
  if sys.platform=='win32':self.skipTest('Linux guard only')
  with self.assertRaises(AppError) as caught:credentials.bind_native_credential(self.reference)
  self.assertEqual(caught.exception.code,'windows_directory_platform_unsupported')

class NativeJobContracts(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.api=FilesystemAPI(Path(self.temp.name)/'files')
  def connect(database,**kwargs):kwargs['timeout']=.02;return self.api.connect(database,**kwargs)
  self.fs=ww._Filesystem(self.api,connect)
  self.estate=generate_estate(seed=845,policy_count=1);self.tenant=self.estate['truth']['tenant_id'];self.oid=self.estate['truth']['policies'][0]['id'];self.spec=ReaderSpec(self.tenant,CLIENT,PRINCIPAL,(self.oid,))
  self.store=ww.WindowsWorkbenchStore._create(ROOT+'\\store',self.tenant,self.fs);self.target=target_api._bind_laboratory_target(self.store);self.addCleanup(self.target.close)
  self.reference=credentials.CredentialReference('IntuneWorkbench/observer/pilot',SID,CLIENT)
  self.package=ROOT+'\\app';ws._create_directory(ROOT,'app',self.api)
  for name in ('intune_iac','scripts'):ws._create_directory(self.package,name,self.api)
  for name in ('__init__.py','module.py'):ws._create_file(self.package+'\\intune_iac',name,b'# reviewed fixture runtime\n',self.api)
  ws._create_file(self.package+'\\scripts','intune-windows-observer.py',b'# exact inert fixture entrypoint\n',self.api)
  self.exe=ROOT+'\\python.exe';ws._create_file(ROOT,'python.exe',b'MZ-SYNTHETIC-NATIVE-EXECUTABLE-NOT-RUN',self.api)
 def create(self,name='job',fixture=None):
  value=jobs._create_job(self.target,self.spec,output=ROOT+'\\'+name,credential_reference=self.reference,package_root=self.package,interpreter=self.exe,interval_seconds=60,max_duration_seconds=30,laboratory_fixture=canonical(fixture or fixture_for(self.estate)))
  self.addCleanup(value.close);return value
 def count(self):
  with self.store._connection() as db:return db.execute('SELECT COUNT(*) FROM collection_runs').fetchone()[0]
 def event(self,job):return job._load()[1]
 def test_create_is_inactive_and_run_once_publishes_real_sqlite_then_not_due(self):
  job=self.create();self.assertEqual(self.count(),0);self.assertEqual(jobs.job_status(job)['status'],'idle')
  result=jobs.run_due(job);self.assertEqual(result['status'],'complete');self.assertEqual(self.count(),1);self.assertEqual(result['success_count'],1);self.assertFalse(result['attempt_record']['source_authenticity_verified'])
  self.assertGreater(result['retained_capture_bytes'],0)
  with patch.object(credentials,'bind_native_credential',side_effect=AssertionError('not-due read credential')):
   again=jobs.run_due(job)
  self.assertEqual(again['status'],'not_due');self.assertFalse(again['network_attempted']);self.assertEqual(self.count(),1);self.assertEqual(self.api.handles,{})
 def test_laboratory_target_cannot_select_live_profile(self):
  with self.assertRaises(AppError):jobs._create_job(self.target,self.spec,output=ROOT+'\\bad',credential_reference=self.reference,package_root=self.package,interpreter=self.exe)
  self.assertFalse(self.api.real(CANONICAL+'\\bad').exists())
 def test_runtime_bytes_change_blocks_before_read_or_new_event(self):
  job=self.create();before=self.event(job);self.api.real(CANONICAL+'\\app\\intune_iac\\module.py').write_bytes(b'changed')
  with self.assertRaises(AppError) as caught:jobs.run_due(job)
  self.assertEqual(caught.exception.code,'windows_observer_runtime_changed');self.assertEqual(self.event(job),before);self.assertEqual(self.count(),0)
 def test_actual_database_replacement_revokes_job(self):
  job=self.create();path=self.api.real(CANONICAL+'\\store\\observations.sqlite3');new=path.with_name('replacement');new.write_bytes(path.read_bytes());new.replace(path)
  with self.assertRaises(AppError) as caught:jobs.run_due(job)
  self.assertEqual(caught.exception.code,'windows_observer_target_changed');self.assertEqual(self.count(),0)
 def test_named_lock_prevents_second_actual_entrypoint(self):
  job=self.create()
  with job.io.lock(job.root):
   self.assertEqual(jobs.job_status(job)['status'],'active')
   with self.assertRaises(AppError) as caught:jobs.run_due(job)
   self.assertEqual(caught.exception.code,'windows_storage_lock_busy')
  self.assertEqual(self.count(),0);self.assertEqual(jobs.run_due(job)['status'],'complete')
 def test_extra_stage_or_modified_event_prevents_automatic_resume(self):
  job=self.create();events=str(jobs.PureWindowsPath(job.root)/'events');ws._create_file(events,'stage-'+'a'*32+'.json',b'partial',self.api)
  with self.assertRaises(AppError) as caught:jobs.run_due(job)
  self.assertEqual(caught.exception.code,'windows_observer_event_chain_invalid');self.assertEqual(self.count(),0)
 def test_hostile_config_cannot_change_identity_or_promote_profile(self):
  job=self.create();path=self.api.real(CANONICAL+'\\job\\config.json');value=parse_json(path.read_bytes());value['profile']='graph_public_live';path.write_bytes(canonical(value))
  with self.assertRaises(AppError):jobs.run_due(job)
  self.assertEqual(self.count(),0)
 def test_denied_scope_preserves_last_good_and_durable_failure(self):
  first=self.create();jobs.run_due(first);good=self.store.inspect(self.oid)['body']
  fixture=fixture_for(self.estate);fixture['responses'][4].update(status=403,body={'error':{'code':'Denied'}})
  denied=self.create('denied',fixture);result=jobs.run_due(denied)
  self.assertEqual(result['status'],'failed');self.assertEqual(result['failure_count'],1);self.assertEqual(self.store.inspect(self.oid)['body'],good);self.assertEqual(self.count(),2)
 def test_commit_then_receipt_failure_retains_both_uncertainty_records(self):
  job=self.create();self.api.fail_creation='store-outcome-';result=jobs.run_due(job)
  self.assertEqual(result['status'],'failed');self.assertEqual(self.count(),1)
  record=result['attempt_record'];self.assertTrue(record['storage_outcome']['outcome_uncertain']);self.assertTrue(record['observation_outcome']['outcome_uncertain']);self.assertEqual(len(self.store.storage_status()['unresolved_intents']),2)
 def test_crash_after_database_commit_recovers_domain_without_duplicate_authentication(self):
  job=self.create();real=job._append;calls=[]
  def fail_settle(config,last,previous,state,record):
   if state['active_attempt'] is None:raise AppError('fixture_settle_crash','fixture')
   return real(config,last,previous,state,record)
  with patch.object(job,'_append',side_effect=fail_settle),self.assertRaises(AppError):jobs.run_due(job)
  self.assertEqual(self.count(),1);self.assertIsNotNone(self.event(job)['state']['active_attempt'])
  with patch.object(jobs,'bind_laboratory_reader',side_effect=AssertionError('must not reauthenticate old attempt')):result=jobs.run_due(job)
  self.assertEqual(result['status'],'not_due');self.assertEqual(result['interrupted_count'],1);self.assertEqual(self.count(),1);self.assertGreater(result['retained_capture_bytes'],0)
  record=self.event(job)['record'];self.assertTrue(record['publication_found_before_recovery']);self.assertEqual(len(record['persisted_collection_run_ids']),1)
 def test_interrupted_before_authentication_recovers_failed_scope_once(self):
  job=self.create()
  with patch.object(credentials,'_bind_laboratory_credential',side_effect=KeyboardInterrupt()),self.assertRaises(KeyboardInterrupt):jobs.run_due(job)
  self.assertEqual(self.count(),1);self.assertEqual(self.event(job)['state']['interrupted_count'],1);self.assertEqual(jobs.run_due(job)['status'],'not_due')
 def test_xml_is_disabled_single_exact_action_sid_and_no_secret_value(self):
  job=self.create();receipt=jobs.scheduler_artifacts(job,ROOT+'\\task',start_boundary='2026-10-08T00:00:00Z',account_sid=SID);raw=self.api.real(CANONICAL+'\\task\\observer-task.xml').read_bytes();doc=ET.fromstring(raw);ns={'t':'http://schemas.microsoft.com/windows/2004/02/mit/task'}
  self.assertEqual(doc.findtext('t:Settings/t:Enabled',namespaces=ns),'false');self.assertEqual(doc.findtext('t:Triggers/t:TimeTrigger/t:Enabled',namespaces=ns),'false')
  self.assertEqual(doc.findtext('t:Principals/t:Principal/t:RunLevel',namespaces=ns),'LeastPrivilege');self.assertEqual(doc.findtext('t:Principals/t:Principal/t:UserId',namespaces=ns),SID);self.assertEqual(len(doc.findall('t:Actions/t:Exec',ns)),1)
  self.assertNotIn(b'SYNTHETIC-WINDOWS-OBSERVER-ONLY',raw);self.assertNotIn(b'CredWrite',raw);self.assertFalse(receipt['installed']);self.assertFalse(receipt['activated']);self.assertEqual(self.count(),0)
 def test_xml_rejects_overlap_and_unqualified_start_time(self):
  job=self.create()
  for output,stamp in [(job.root+'\\task','2026-10-08T00:00:00Z'),(ROOT+'\\task','2026-10-08T00:00:00'),(ROOT+'\\task','<Injected/>')]:
   with self.subTest(output=output,stamp=stamp),self.assertRaises(AppError):jobs.scheduler_artifacts(job,output,start_boundary=stamp,account_sid=SID)
  self.assertEqual(self.count(),0)
 def test_closed_job_or_json_cannot_execute(self):
  job=self.create();job.close()
  with self.assertRaises(AppError):jobs.run_due(job)
  with self.assertRaises(AppError):jobs.run_due({'approved':True})
  with self.assertRaises(TypeError):pickle.dumps(job)
 def test_native_qualification_fixture_exercises_the_same_actual_reader(self):
  import importlib.util
  path=Path(jobs.__file__).resolve().parent.parent/'scripts'/'qualify-windows-observer-job.py';spec=importlib.util.spec_from_file_location('native_job_qualifier',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  raw,oid=module.fixture(self.estate);self.spec=ReaderSpec(self.tenant,module.CLIENT,module.PRINCIPAL,(oid,));self.reference=credentials.CredentialReference('IntuneWorkbench/observer/qualifier',SID,module.CLIENT)
  job=self.create(fixture=parse_json(raw));result=jobs.run_due(job);self.assertEqual(result['status'],'complete');self.assertEqual(self.count(),1)
 def test_failed_namespace_barrier_blocks_network_and_retains_stage(self):
  job=self.create()
  with job.io.lock(job.root):pass
  self.api.failure='namespace'
  with patch.object(jobs,'bind_laboratory_reader',side_effect=AssertionError('network after failed event barrier')),self.assertRaises(AppError) as caught:jobs.run_due(job)
  self.assertTrue(caught.exception.storage_outcome['outcome_uncertain']);self.assertEqual(self.count(),0)
  self.api.failure=None
  with self.assertRaises(AppError) as later:jobs.run_due(job)
  self.assertEqual(later.exception.code,'windows_observer_event_chain_invalid')
 def test_primary_cancellation_survives_failed_recording(self):
  job=self.create();real=job._append;primary=KeyboardInterrupt()
  def fail_settle(config,last,previous,state,record):
   if state['active_attempt'] is None:raise OSError('fixture receipt disk full')
   return real(config,last,previous,state,record)
  with patch.object(credentials,'_bind_laboratory_credential',side_effect=primary),patch.object(job,'_append',side_effect=fail_settle),self.assertRaises(KeyboardInterrupt) as caught:jobs.run_due(job)
  self.assertIs(caught.exception,primary);self.assertEqual(primary.observer_recording_failure,'OSError');self.assertIsNotNone(self.event(job)['state']['active_attempt'])
 def test_missed_cycles_are_counted_without_catchup_burst(self):
  with patch.object(jobs.time,'time',return_value=1800000000):job=self.create()
  with patch.object(jobs.time,'time',return_value=1800000301):result=jobs.run_due(job)
  self.assertEqual(result['missed_cycles'],5);self.assertEqual(result['run_count'],1);self.assertEqual(self.count(),1)
 def test_stale_or_failed_history_never_claims_freshness(self):
  job=self.create();jobs.run_due(job)
  with patch.object(jobs.time,'time',return_value=jobs.time.time()+121):self.assertEqual(jobs.job_status(job)['freshness'],'stale')
 def test_modified_event_bytes_cannot_rewrite_counters(self):
  job=self.create();root=self.api.real(CANONICAL+'\\job\\events');path=next(root.glob('event-*.json'));value=parse_json(path.read_bytes());value['state']['success_count']=999;path.write_bytes(canonical(value))
  with self.assertRaises(AppError) as caught:jobs.run_due(job)
  self.assertEqual(caught.exception.code,'windows_observer_event_chain_invalid');self.assertEqual(self.count(),0)
 def test_percent_expansion_token_in_task_path_is_denied_before_output(self):
  job=self.create('%PATH%')
  with self.assertRaises(AppError) as caught:jobs.scheduler_artifacts(job,ROOT+'\\task',start_boundary='2026-10-08T00:00:00Z',account_sid=SID)
  self.assertEqual(caught.exception.code,'windows_observer_task_argument_invalid');self.assertFalse(self.api.real(CANONICAL+'\\task').exists())
 def test_task_cannot_substitute_account_sid(self):
  job=self.create()
  with self.assertRaises(AppError) as caught:jobs.scheduler_artifacts(job,ROOT+'\\task',start_boundary='2026-10-08T00:00:00Z',account_sid='S-1-5-18')
  self.assertEqual(caught.exception.code,'windows_observer_task_account_changed');self.assertFalse(self.api.real(CANONICAL+'\\task').exists())
 def test_reader_cleanup_failure_cannot_mark_cycle_complete_or_advance_last_success(self):
  from intune_iac.observation_reader import LaboratoryGraphReader
  job=self.create()
  with patch.object(LaboratoryGraphReader,'close',side_effect=AppError('fixture_reader_close_failed','fixture')):result=jobs.run_due(job)
  self.assertEqual(result['status'],'failed');self.assertEqual(result['last_error'],'fixture_reader_close_failed');self.assertEqual(result['success_count'],0);self.assertIsNone(result['last_success']);self.assertEqual(self.count(),1)
 def test_primary_after_capture_and_secondary_cleanup_errors_both_survive(self):
  from intune_iac.observation_reader import LaboratoryGraphReader
  job=self.create();real=job._runtime;calls=[]
  def runtime(config):
   calls.append(1)
   if len(calls)==2:raise AppError('fixture_primary_after_capture','fixture')
   return real(config)
  with patch.object(job,'_runtime',side_effect=runtime),patch.object(LaboratoryGraphReader,'close',side_effect=OSError('secondary cleanup')):result=jobs.run_due(job)
  self.assertEqual(result['status'],'failed');self.assertEqual(result['last_error'],'fixture_primary_after_capture');self.assertEqual(result['attempt_record']['cleanup_failures'],['OSError']);self.assertEqual(result['success_count'],0)
 def test_source_has_one_renderer_and_one_retention_measurement_helper(self):
  import ast
  module=ast.parse(Path(jobs.__file__).read_text());names=[node.name for node in module.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))]
  self.assertEqual(len(names),len(set(names)));self.assertNotIn('_attempt_size',names)
 def set_state(self,job,**updates):
  config,last,previous=job._load();state=copy.deepcopy(last['state']);state.update(updates);job._append(config,last,previous,state,last['record'])
 def test_compound_reader_and_publication_errors_preserve_primary_and_secondary(self):
  from intune_iac.observation_reader import LaboratoryGraphReader
  job=self.create();primary=AppError('fixture_reader_primary','fixture');secondary=AppError('fixture_publication_secondary','fixture');secondary.storage_outcome={'outcome_uncertain':True};secondary.observation_outcome={'outcome_uncertain':True}
  with patch.object(LaboratoryGraphReader,'close',side_effect=primary),patch.object(target_api.LaboratoryWindowsObservationTarget,'publish',side_effect=secondary):result=jobs.run_due(job)
  record=result['attempt_record'];self.assertEqual(record['error_code'],'fixture_reader_primary');self.assertEqual(record['primary_failure']['code'],'fixture_reader_primary');self.assertEqual(record['secondary_failures'][0]['code'],'fixture_publication_secondary');self.assertTrue(record['secondary_failures'][0]['storage_outcome']['outcome_uncertain']);self.assertTrue(record['observation_outcome']['outcome_uncertain']);self.assertEqual(result['success_count'],0);self.assertIsNone(result['last_success']);self.assertIsNone(self.event(job)['state']['active_attempt'])
 def test_actual_sqlite_contention_after_reader_error_settles_with_primary_and_secondary(self):
  from intune_iac.observation_reader import LaboratoryGraphReader
  job=self.create();real_publish=self.target.publish
  path=self.api.real(CANONICAL+'\\store\\observations.sqlite3')
  def locked_publish(*args,**kwargs):
   db=sqlite3.connect(path);db.execute('BEGIN IMMEDIATE')
   try:return real_publish(*args,**kwargs)
   finally:db.rollback();db.close()
  # The store's filesystem invokes the owned connection seam; the DB lock is real.
  with patch.object(LaboratoryGraphReader,'close',side_effect=AppError('fixture_reader_primary','fixture')),patch.object(target_api.LaboratoryWindowsObservationTarget,'publish',side_effect=locked_publish):result=jobs.run_due(job)
  record=result['attempt_record'];self.assertEqual(result['last_error'],'fixture_reader_primary');self.assertEqual(record['secondary_failures'][0]['type'],'OperationalError');self.assertEqual(record['secondary_failures'][0]['phase'],'publication');self.assertIsNone(self.event(job)['state']['active_attempt']);self.assertEqual(self.count(),0)
 def test_retention_status_blocks_before_new_capture_and_reports_action(self):
  job=self.create();self.set_state(job,retained_capture_bytes=jobs.MAX_RETAINED-1);before=self.event(job)
  result=jobs.job_status(job);self.assertEqual(result['status'],'blocked');self.assertEqual(result['retention_error'],'windows_observer_capture_retention_limit');self.assertIn('Preserve',result['next_action'])
  with patch.object(jobs,'bind_laboratory_reader',side_effect=AssertionError('retention cannot authenticate')),self.assertRaises(AppError):jobs.run_due(job)
  self.assertEqual(self.event(job),before);self.assertEqual(self.count(),0)
 def test_cycle_exhaustion_and_runtime_change_status_are_actionable(self):
  job=self.create();self.set_state(job,run_count=jobs.MAX_RUNS);result=jobs.job_status(job);self.assertEqual(result['status'],'blocked');self.assertEqual(result['retention_error'],'windows_observer_cycle_limit')
  self.api.real(CANONICAL+'\\app\\intune_iac\\module.py').write_bytes(b'changed');result=jobs.job_status(job);self.assertEqual(result['binding_error'],'windows_observer_runtime_changed');self.assertIn('runtime',result['next_action'])
 def test_status_preserves_last_attempt_timestamps_declared_and_missing_scope(self):
  fixture=fixture_for(self.estate);fixture['responses'][4].update(status=403,body={'error':{'code':'Denied'}});job=self.create(fixture=fixture);result=jobs.run_due(job);status=jobs.job_status(job)
  self.assertEqual(status['last_attempted_at'],result['attempt_record']['started_at']);self.assertEqual(status['last_attempt_ended_at'],result['attempt_record']['ended_at']);self.assertEqual(status['declared_object_ids'],[self.oid]);self.assertEqual(status['last_attempt_incomplete_object_ids'],[self.oid]);self.assertEqual(status['last_attempt_scope_status'],'incomplete');self.assertIn('incomplete',status['next_action'])
 def test_partial_capture_failures_consume_measured_budget_before_next_object(self):
  # Reduced admission budget exercises two actual failed captures and retained
  # bytes; it is not a 512MiB native scale claim. Reserve remains exactly56MiB.
  self.estate=generate_estate(seed=845,policy_count=4);ids=tuple(sorted(p['id'] for p in self.estate['truth']['policies']));self.spec=ReaderSpec(self.tenant,CLIENT,PRINCIPAL,ids)
  calibration=self.create('calibration');jobs.run_due(calibration)
  first=next(self.api.real(CANONICAL+'\\calibration\\captures').glob('*/'+ids[0]));first_bytes=sum(path.stat().st_size for path in first.rglob('*') if path.is_file())
  job=self.create();real_capture=self.target.capture;calls=[]
  def partial(*args,**kwargs):
   real_capture(*args,**kwargs);calls.append((args[1],args[2]));raise AppError('fixture_partial_capture_failed','fixture')
  budget=jobs.MAX_CAPTURE_BYTES+first_bytes+128
  with patch.object(target_api.LaboratoryWindowsObservationTarget,'capture',side_effect=partial),patch.object(jobs,'MAX_RETAINED',budget):result=jobs.run_due(job)
  self.assertEqual(len(calls),2);self.assertEqual(result['status'],'failed');self.assertGreater(result['retained_capture_bytes'],first_bytes);self.assertLessEqual(result['retained_capture_bytes'],budget);self.assertEqual(self.count(),8)
  directory=self.api.real(CANONICAL+'\\job\\captures');actual=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file());self.assertEqual(result['retained_capture_bytes'],actual);self.assertEqual(len(list(directory.glob('*/*/export.json'))),2)
 def test_unknown_partial_measurement_exhausts_budget_and_cannot_continue(self):
  self.estate=generate_estate(seed=845,policy_count=3);ids=tuple(sorted(p['id'] for p in self.estate['truth']['policies']));self.spec=ReaderSpec(self.tenant,CLIENT,PRINCIPAL,ids);job=self.create();real_capture=self.target.capture;calls=[]
  def partial(*args,**kwargs):
   real_capture(*args,**kwargs);calls.append(args[1]);raise AppError('fixture_partial_capture_failed','fixture')
  with patch.object(target_api.LaboratoryWindowsObservationTarget,'capture',side_effect=partial),patch.object(job.io,'capture_size',side_effect=OSError('fixture unreadable partial')):result=jobs.run_due(job)
  self.assertEqual(len(calls),1);self.assertEqual(result['status'],'failed');self.assertEqual(result['retained_capture_bytes'],jobs.MAX_RETAINED);self.assertTrue(result['attempt_record']['publication_blocked']);self.assertEqual(result['last_error'],'fixture_partial_capture_failed');self.assertEqual(result['retained_capture_bytes_basis'],'unknown_conservative_budget_charge');self.assertEqual(self.count(),0);self.assertEqual(jobs.job_status(job)['status'],'blocked')
  with patch.object(jobs.time,'time',return_value=jobs.time.time()+61),patch.object(jobs,'bind_laboratory_reader',side_effect=AssertionError('spent budget')),self.assertRaises(AppError):jobs.run_due(job)
 def test_measurement_cancellation_preserves_failed_capture_cause_and_interrupt(self):
  job=self.create();real_capture=self.target.capture;primary=AppError('fixture_partial_capture_failed','fixture');interrupt=KeyboardInterrupt()
  def partial(*args,**kwargs):real_capture(*args,**kwargs);raise primary
  with patch.object(target_api.LaboratoryWindowsObservationTarget,'capture',side_effect=partial),patch.object(job.io,'capture_size',side_effect=interrupt),self.assertRaises(KeyboardInterrupt) as caught:jobs.run_due(job)
  self.assertIs(caught.exception,interrupt);self.assertIs(caught.exception.__cause__,primary);event=self.event(job);record=event['record'];self.assertEqual(record['error_code'],'fixture_partial_capture_failed');self.assertEqual(record['status'],'interrupted');self.assertEqual(record['secondary_failures'][0]['type'],'KeyboardInterrupt');self.assertEqual(event['state']['interrupted_count'],1);self.assertEqual(event['state']['success_count'],0);self.assertEqual(self.count(),0)
 def test_postcapture_measurement_cancellation_preserves_reader_cleanup_primary(self):
  from intune_iac.observation_reader import LaboratoryGraphReader
  job=self.create();measure=jobs._attempt_bytes;calls=[];primary=AppError('fixture_reader_cleanup_primary','fixture');interrupt=KeyboardInterrupt()
  def measurement(*args,**kwargs):
   calls.append(1)
   if len(calls)==2:raise interrupt
   return measure(*args,**kwargs)
  with patch.object(LaboratoryGraphReader,'close',side_effect=primary),patch.object(jobs,'_attempt_bytes',side_effect=measurement),self.assertRaises(KeyboardInterrupt) as caught:jobs.run_due(job)
  self.assertIs(caught.exception,interrupt);self.assertIs(caught.exception.__cause__,primary);record=self.event(job)['record'];self.assertEqual(record['error_code'],'fixture_reader_cleanup_primary');self.assertEqual(record['status'],'interrupted');self.assertEqual(record['secondary_failures'][0]['type'],'KeyboardInterrupt');self.assertEqual(self.count(),0)
 def test_native_public_creation_rejects_laboratory_target(self):
  with self.assertRaises(AppError):jobs.create_native_job(self.target,self.spec,output=ROOT+'\\blocked',credential_reference=self.reference,package_root=self.package,interpreter=self.exe)

if __name__=='__main__':unittest.main()
