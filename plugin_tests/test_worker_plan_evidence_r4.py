"""Literal content and guarded artifact tests; no host or authentication claim."""
import copy,hashlib,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from intune_iac import worker_plan_evidence as evidence,provider_execution as pe
from intune_iac.io import AppError,canonical,digest

OBJECT='33333333-3333-4333-8333-333333333333'
def fixture():
    desired={'name':'Literal policy','description':'Original description','platforms':'windows10','technologies':['mdm'],
        'role_scope_tag_ids':['0'],'settings':'{"settings":[]}',
        'assignments':[{'type':'exclusionGroupAssignmentTarget','group_id':'22222222-2222-4222-8222-222222222222','filter_id':'00000000-0000-0000-0000-000000000000','filter_type':'none'},
        {'type':'groupAssignmentTarget','group_id':'11111111-1111-4111-8111-111111111111','filter_id':'44444444-4444-4444-8444-444444444444','filter_type':'include'}]}
    attrs=dict(desired,id=OBJECT,created_date_time='2026-10-07T00:00:00Z',last_modified_date_time='2026-10-07T00:00:00Z',is_assigned=True,settings_count=0,settings_catalog_template_type='none',timeouts=None)
    source={'resource':{pe.RESOURCE:{'selected':desired}},'provider':{'microsoft365':{'tenant_id':'11111111-1111-1111-1111-111111111111','cloud':'public'}}}
    state={'version':4,'terraform_version':'1.13.1','serial':13,'lineage':'9e357e8a-cd80-4159-96d7-f8998303defe','outputs':{},'resources':[{'mode':'managed','type':pe.RESOURCE,'name':'selected','provider':'provider["'+pe.SOURCE+'"]','instances':[{'schema_version':0,'identity_schema_version':0,'identity':{'id':OBJECT},'sensitive_attributes':[],'attributes':attrs}]}]}
    resource={'address':pe.ADDRESS,'mode':'managed','type':pe.RESOURCE,'name':'selected','provider_name':pe.SOURCE,'schema_version':0,'values':attrs,'sensitive_values':{},'identity':{'id':OBJECT},'identity_schema_version':0}
    values={'root_module':{'resources':[resource]}}
    plan={'format_version':'1.2','terraform_version':'1.13.1','variables':{'stage':{'value':'worker'}},'planned_values':copy.deepcopy(values),
        'resource_changes':[{'address':pe.ADDRESS,'mode':'managed','type':pe.RESOURCE,'name':'selected','provider_name':pe.SOURCE,'change':{'actions':['no-op'],'before':copy.deepcopy(attrs),'after':copy.deepcopy(attrs),'after_unknown':{},'before_sensitive':{},'after_sensitive':{},'before_identity':{'id':OBJECT},'after_identity':{'id':OBJECT}}}],
        'prior_state':{'format_version':'1.0','terraform_version':'1.13.1','values':copy.deepcopy(values)},
        'configuration':{'provider_config':{'microsoft365':{'name':'microsoft365','full_name':pe.SOURCE,'version_constraint':'1.0.0','expressions':{k:{'constant_value':v} for k,v in source['provider']['microsoft365'].items()}}},
            'root_module':{'resources':[{'address':pe.ADDRESS,'mode':'managed','type':pe.RESOURCE,'name':'selected','provider_config_key':'microsoft365','expressions':{k:{'constant_value':v} for k,v in desired.items()},'schema_version':0}],'variables':{'stage':{'type':'string','required':True}}}},
        'checks':[{'address':{'kind':'var','name':'stage','to_display':'var.stage'},'status':'pass','instances':[{'address':{'to_display':'var.stage'},'status':'pass'}]}],
        'timestamp':'2026-10-07T00:00:00Z','errored':False}
    return plan,state,source

class PlanEvidenceFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.plan,self.state,self.source=fixture();self.job=self.root/'job';self.job.mkdir(mode=0o700);self.archive=self.root/'archive'
        self.raw={'plan.bin':b'CONSTRUCTED-BINARY-NOT-NATIVE','plan.json':canonical(self.plan),'exit.txt':b'0\n'}
        for name,path in evidence.paths(self.job).items():
            path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);path.write_bytes(self.raw[name]);path.chmod(0o600)
    def args(self):
        state,source=canonical(self.state),canonical(self.source)
        return dict(state_raw=state,source_raw=source,object_id=OBJECT,state_sha256=hashlib.sha256(state).hexdigest(),source_sha256=hashlib.sha256(source).hexdigest(),effective_inputs_sha256=digest(self.source['resource'][pe.RESOURCE]['selected']))
    def valid(self,plan=None):return evidence.validate(canonical(self.plan if plan is None else plan),**self.args())
    def capture(self):return evidence.capture(self.job,self.archive,host_result={"status":"complete","fixture":"injected"})
    def qualify(self,record):return evidence.qualify(record,job_root=self.job,archive=self.archive,**self.args())

class NativePlanEvidenceTests(PlanEvidenceFixture):
    def test_full_literal_noop_has_no_receiving_authority(self):
        proof=self.valid();self.assertTrue(proof['before_after_planned_prior_values_equal_state']);self.assertFalse(proof['receiving_state_authentication_established']);self.assertFalse(proof['execution_authorized'])
    def test_wrong_immutable_identity_rejected(self):
        self.plan['resource_changes'][0]['change']['before']['id']='wrong';self.plan['resource_changes'][0]['change']['after']['id']='wrong'
        with self.assertRaises(AppError):self.valid()
    def test_noop_action_with_different_values_rejected(self):
        self.plan['resource_changes'][0]['change']['after']['description']='wrong'
        with self.assertRaises(AppError):self.valid()
    def test_assignment_include_filter_and_exclusion_are_full_values(self):
        for field in ('filter_id','filter_type','group_id','type'):
            value=copy.deepcopy(self.plan);value['resource_changes'][0]['change']['after']['assignments'][1][field]='wrong'
            with self.subTest(field=field),self.assertRaises(AppError):self.valid(value)
        self.plan['resource_changes'][0]['change']['after']['assignments'].pop(0)
        with self.assertRaises(AppError):self.valid()
    def test_prior_planned_and_identity_mismatches_reject(self):
        for key in ('planned_values','prior_state'):
            value=copy.deepcopy(self.plan);root=value[key] if key=='planned_values' else value[key]['values'];root['root_module']['resources'][0]['values']['description']='wrong'
            with self.subTest(key=key),self.assertRaises(AppError):self.valid(value)
        self.plan['resource_changes'][0]['change']['after_identity']['id']='wrong'
        with self.assertRaises(AppError):self.valid()
    def test_changed_source_configuration_or_effective_digest_reject(self):
        self.plan['configuration']['root_module']['resources'][0]['expressions']['description']['constant_value']='wrong'
        with self.assertRaises(AppError):self.valid()
        args=self.args();args['effective_inputs_sha256']='0'*64
        with self.assertRaises(AppError):evidence.validate(canonical(fixture()[0]),**args)
    def test_wrong_provider_unknown_sensitive_and_extra_resource_reject(self):
        mutations=[lambda p:p['configuration']['provider_config']['microsoft365'].update(full_name='wrong'),lambda p:p['resource_changes'][0]['change']['after_unknown'].update(description=True),lambda p:p['resource_changes'][0]['change']['after_sensitive'].update(settings=True),lambda p:p['planned_values']['root_module']['resources'].append(copy.deepcopy(p['planned_values']['root_module']['resources'][0]))]
        for change in mutations:
            value=copy.deepcopy(self.plan);change(value)
            with self.assertRaises(AppError):self.valid(value)
    def test_json_bool_number_float_and_schema_types_remain_distinct(self):
        for area in ('after','planned','prior','float','config_schema'):
            value=copy.deepcopy(self.plan)
            if area=='after':value['resource_changes'][0]['change']['after']['is_assigned']=1
            elif area=='planned':value['planned_values']['root_module']['resources'][0]['values']['is_assigned']=1
            elif area=='prior':value['prior_state']['values']['root_module']['resources'][0]['values']['is_assigned']=1
            elif area=='float':value['resource_changes'][0]['change']['after']['settings_count']=0.0
            else:value['configuration']['root_module']['resources'][0]['schema_version']=False
            with self.subTest(area=area),self.assertRaises(AppError):self.valid(value)
        self.state['resources'][0]['instances'][0]['schema_version']=False
        with self.assertRaises(AppError):self.valid()
    def test_state_version_config_required_and_null_key_presence_are_exact(self):
        self.state['version']=4.0
        with self.assertRaises(AppError):self.valid()
        self.state['version']=4
        self.plan['configuration']['root_module']['variables']['stage']['required']=1
        with self.assertRaises(AppError):self.valid()
        self.plan['configuration']['root_module']['variables']['stage']['required']=True
        self.source['resource'][pe.RESOURCE]['selected']['missing_null']=None
        self.plan['configuration']['root_module']['resources'][0]['expressions']['missing_null']={'constant_value':None}
        with self.assertRaises(AppError):self.valid()
    def test_regular_to_fifo_swap_does_not_block_open(self):
        import subprocess,sys
        code="""import os,sys
from pathlib import Path
from intune_iac import worker_plan_evidence as e
p=Path(sys.argv[1]);p.write_bytes(b'regular');p.chmod(0o600);original=e._private
def swap(path,*args,**kwargs):
 value=original(path,*args,**kwargs);value.unlink();os.mkfifo(value,0o600);return value
e._private=swap
try:e._read(p)
except e.AppError as error:sys.exit(0 if error.code=='plan_output_file_invalid' else 2)
sys.exit(3)
"""
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=os.pathsep.join(__import__('sys').path))
        # Staged runs must select the exact helper already under test as well.
        code="import intune_iac;intune_iac.__path__.insert(0,"+repr(str(Path(evidence.__file__).parent))+");\n"+code
        result=subprocess.run([sys.executable,'-B','-c',code,str(self.root/'fifo-race')],env=env,capture_output=True,timeout=3)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_source_values_cannot_disagree_with_noop_state(self):
        self.source['resource'][pe.RESOURCE]['selected']['description']='changed intended description'
        self.plan['configuration']['root_module']['resources'][0]['expressions']['description']['constant_value']='changed intended description'
        with self.assertRaises(AppError):self.valid()
    def test_drift_deferred_output_update_and_error_reject(self):
        mutations=[lambda p:p.update(resource_drift=[{}]),lambda p:p.update(deferred_changes=[{}]),lambda p:p.update(output_changes={'x':{}}),lambda p:p.update(errored=True),lambda p:p['resource_changes'][0]['change'].update(actions=['update'])]
        for change in mutations:
            value=copy.deepcopy(self.plan);change(value)
            with self.assertRaises(AppError):self.valid(value)
    def test_state_source_bytes_must_match_independent_supplied_hashes(self):
        for key in ('state_raw','source_raw'):
            args=self.args();args[key]+=b'\n'
            with self.assertRaises(AppError):evidence.validate(canonical(self.plan),**args)
    def test_capture_preserves_exact_bytes_and_requalifies(self):
        record=self.capture();qualified=self.qualify(record)
        self.assertTrue(qualified['first_plan_no_change'])
        for name,raw in self.raw.items():self.assertEqual((self.archive/name).read_bytes(),raw)
        self.assertEqual((self.archive/'receipt.json').read_bytes(),canonical(record))
    def test_all_source_and_archive_artifact_changes_reject(self):
        record=self.capture()
        for name in evidence.FILES:
            for path in (evidence.paths(self.job)[name],self.archive/name):
                raw=path.read_bytes();path.write_bytes(raw+b'x')
                with self.subTest(path=str(path)),self.assertRaises(AppError):self.qualify(record)
                path.write_bytes(raw)
    def test_receipt_record_changes_and_wrong_archive_reject(self):
        record=self.capture();changed=copy.deepcopy(record);changed['artifacts']['plan.bin']['sha256']='0'*64
        with self.assertRaises(AppError):self.qualify(changed)
        (self.archive/'receipt.json').write_bytes(canonical(dict(record,execution_authorized=True)))
        with self.assertRaises(AppError):self.qualify(record)
    def test_exit2_missing_output_partial_archive_never_noop(self):
        evidence.paths(self.job)['exit.txt'].write_bytes(b'2\n');record=self.capture()
        with self.assertRaises(AppError):self.qualify(record)
        (self.archive/'plan.bin').unlink()
        with self.assertRaises((AppError,OSError)):self.qualify(record)
    def test_symlink_hardlink_or_public_file_reject_before_capture(self):
        target=evidence.paths(self.job)['plan.bin'];original=target.read_bytes();target.unlink();other=self.root/'other';other.write_bytes(original);other.chmod(0o600);target.symlink_to(other)
        with self.assertRaises((AppError,OSError)):self.capture()
        target.unlink();os.link(other,target)
        with self.assertRaises(AppError):self.capture()
        target.unlink();target.write_bytes(original);target.chmod(0o644)
        with self.assertRaises(AppError):self.capture()
    def test_partial_archive_write_failure_preserves_prior_artifacts_no_receipt(self):
        original=evidence.protected._exclusive
        def stop(path,data):
            if Path(path).name=='plan.json':raise OSError('injected durable recording failure')
            return original(path,data)
        with patch.object(evidence.protected,'_exclusive',side_effect=stop),self.assertRaises(OSError):self.capture()
        self.assertEqual((self.archive/'plan.bin').read_bytes(),self.raw['plan.bin']);self.assertFalse((self.archive/'receipt.json').exists())
        with self.assertRaises(FileExistsError):self.capture()
    def _close_fault(self,error):
        target=evidence.paths(self.job)['plan.bin'];target.write_bytes(b'');real_close=os.close
        def failed(fd):real_close(fd);raise error
        with patch.object(evidence.os,'close',side_effect=failed):evidence._read(target)
    def test_primary_read_error_survives_secondary_close_failure(self):
        with self.assertRaises(AppError) as caught:self._close_fault(OSError('secondary'))
        self.assertEqual(caught.exception.code,'plan_output_file_invalid');self.assertTrue(caught.exception.__notes__)
    def test_secondary_cancellation_preserves_primary_chain(self):
        with self.assertRaises(KeyboardInterrupt) as caught:self._close_fault(KeyboardInterrupt('secondary'))
        self.assertIsInstance(caught.exception.__cause__,AppError)


class PlanCallerBindingTests(PlanEvidenceFixture):
    """Injected receiving proof only; exercise callers, never mint live authority."""
    def setUp(self):
        super().setUp()
        import sqlite3,types
        from intune_iac import worker_adoption as adoption,worker_provider as provider
        self.adoption=adoption;self.operation='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        self.source_root=self.root/'source';self.source_path=self.source_root/'project'/provider.PROJECT/'main.tf.json';self.source_path.parent.mkdir(parents=True,mode=0o700);self.source_path.write_bytes(canonical(self.source));self.source_path.chmod(0o600)
        self.receiving=self.root/'receiving';self.receiving.mkdir(mode=0o700);(self.receiving/'state.raw').write_bytes(canonical(self.state));(self.receiving/'state.raw').chmod(0o600)
        self.jobroot=self.root/'controller';self.jobroot.mkdir(mode=0o700);self.archive=self.jobroot/'verification-plan-output'
        self.host={'status':'complete','cleanup':{'removed':True}}
        self.record=evidence.capture(self.job,self.archive,host_result=self.host)
        self.dbpath=self.root/'authority.sqlite3';db=sqlite3.connect(self.dbpath);db.executescript('CREATE TABLE adoption_operations(operation_id TEXT,verification_status TEXT,verification_outcome TEXT);CREATE TABLE adoption_recovery_plans(operation_id TEXT,status TEXT,outcome TEXT);')
        self.outcome={'host':self.host,'plan_output_capture':self.record}
        db.execute('INSERT INTO adoption_operations VALUES (?,?,?)',(self.operation,'first_plan_host_completed_unverified',canonical(self.outcome).decode()));db.commit();db.close()
        self.policy=types.SimpleNamespace(connection=lambda:sqlite3.connect(self.dbpath))
        self.args_initial=self.args();self.manifest={'verification_host_spec':{},'object_ids':[OBJECT],
            'provider_binding':{'source_sha256':self.args_initial['source_sha256'],'effective_input_sha256':self.args_initial['effective_inputs_sha256']},
            'state_contract':{'management_mapping_status':'unsupported','management_mapping_blockers':['retained fixture limit']}}
        self.jobcap=types.SimpleNamespace(root=self.jobroot,policy=self.policy,identifier=self.operation,sha256='1'*64,manifest=self.manifest)
        self.receivingfacts={'state':{'sha256':self.args_initial['state_sha256']}}
        self.statecap=types.SimpleNamespace(_root=self.receiving,facts=lambda:copy.deepcopy(self.receivingfacts))
        self.spec=types.SimpleNamespace(source_root=self.source_root,job_root=self.job)
        self.runtime=types.SimpleNamespace(profile='native_docker_laboratory_protocol')
    # Do not inherit the helper test cases a second time; caller cases below are
    # independently named while sharing setup primitives only.
    def _initial(self):
        with patch.object(self.adoption.service,'_host_spec',return_value=self.spec),patch.object(self.adoption,'_backend_observation',return_value=self.statecap):return self.adoption._qualify_completion(self.jobcap,self.runtime)
    def test_initial_caller_binds_original_capture_and_rechecks_source_and_state(self):
        completion=self._initial();facts=completion.verified(self.jobcap);self.assertEqual(facts['plan_output_proof']['capture_sha256'],digest(self.record))
        for path in (self.source_path,self.receiving/'state.raw',self.archive/'plan.json',evidence.paths(self.job)['plan.bin']):
            raw=path.read_bytes();path.write_bytes(raw+b'\n')
            with self.subTest(path=str(path)),self.assertRaises(AppError):completion.verified(self.jobcap)
            path.write_bytes(raw)
    def test_initial_caller_rejects_missing_or_replaced_host_capture(self):
        for outcome in ({'host':self.host},{'host':dict(self.host,unexpected=True),'plan_output_capture':self.record}):
            with self.policy.connection() as db:db.execute('UPDATE adoption_operations SET verification_outcome=?',(canonical(outcome).decode(),))
            with self.assertRaises(AppError):self._initial()
    def test_initial_no_second_hash_can_bless_mutation_after_qualification(self):
        original=evidence.qualify
        def change(*args,**kwargs):
            result=original(*args,**kwargs);evidence.paths(self.job)['plan.bin'].write_bytes(b'changed after proof');return result
        with patch.object(evidence,'qualify',side_effect=change),self.assertRaises(AppError):self._initial()
    def test_recovery_caller_uses_same_full_validator_and_original_output_capture(self):
        from intune_iac import worker_adoption_reconcile as recovery
        import types
        os.rename(self.archive,self.jobroot/'plan-output');self.archive=self.jobroot/'plan-output'
        # New capture receipt below models the host controller's independently
        # emitted post-host record; it is not a receiving/authentication claim.
        self.record['archive_root']=str(self.archive);(self.archive/'receipt.json').write_bytes(canonical(self.record));self.outcome['plan_output_capture']=self.record
        with self.policy.connection() as db:db.execute('INSERT INTO adoption_recovery_plans VALUES (?,?,?)',(self.operation,'plan_host_completed_unverified',canonical(self.outcome).decode()))
        subject=object.__new__(recovery.RecoveryPlanJob);subject.root=self.jobroot;subject.identifier=self.operation;subject.policy=self.policy;subject.original=self.jobcap;subject.manifest={'host_spec':{},'provider_binding':self.manifest['provider_binding']}
        completed=types.SimpleNamespace(observation=types.SimpleNamespace(root=self.receiving))
        with patch.object(recovery,'_completion',return_value={'fresh_observation':self.receivingfacts}),patch.object(recovery.service,'_host_spec',return_value=self.spec):
            facts=subject._plan_evidence(completion=completed);self.assertTrue(facts['first_plan_no_change'])
            evidence.paths(self.job)['plan.json'].write_bytes(canonical(dict(self.plan,errored=True)))
            with self.assertRaises(AppError):subject._plan_evidence(completion=completed)


class PlanOutputRecordingTests(PlanEvidenceFixture):
    """Actual dispatcher finalization/SQLite, injected host and transport only."""
    def exercise(self,recovery=False,interrupt=False):
        import sqlite3,types
        from intune_iac import worker_adoption as adoption,worker_adoption_reconcile as bridge
        root=self.root/'controller';root.mkdir(mode=0o700);dbpath=self.root/'authority.sqlite3';operation='fixture-operation';original='original-operation'
        db=sqlite3.connect(dbpath);db.executescript('CREATE TABLE jobs(id TEXT,status TEXT,outcome TEXT,controller_pid INTEGER,controller_start TEXT);CREATE TABLE adoption_operations(operation_id TEXT,verification_status TEXT,verification_outcome TEXT);CREATE TABLE adoption_recovery_plans(operation_id TEXT,status TEXT,outcome TEXT,controller_pid INTEGER,controller_start TEXT);CREATE TABLE ownership(scope TEXT,job TEXT);')
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',(operation,'running','{"original_import":"preserved"}',os.getpid(),'fixture'))
        db.execute('INSERT INTO adoption_operations VALUES (?,?,?)',(operation,'running',None));db.execute('INSERT INTO adoption_recovery_plans VALUES (?,?,?,?,?)',(operation,'running',None,os.getpid(),'fixture'));db.execute('INSERT INTO ownership VALUES (?,?)',('exact-scope',original if recovery else operation));db.commit();db.close()
        policy=types.SimpleNamespace(connection=lambda:sqlite3.connect(dbpath),event=lambda *args:None,root=self.root)
        subject=types.SimpleNamespace(root=root,policy=policy,identifier=operation,original=types.SimpleNamespace(identifier=original),manifest={'profile':'native_docker_laboratory_protocol','execution_binding_sha256':'1'*64,'broker_policy':{},'verification_broker_policy':{}})
        def status():
            with policy.connection() as db:return {'status':db.execute('SELECT status FROM '+('adoption_recovery_plans WHERE operation_id=?' if recovery else 'jobs WHERE id=?'),(operation,)).fetchone()[0]}
        subject.status=status
        runtime=types.SimpleNamespace(profile='native_docker_laboratory_protocol',upstream=None,credentials=None,certificate=self.root/'cert',private_key=self.root/'key')
        spec=types.SimpleNamespace(job_root=self.job,broker_root=self.root)
        permit=types.SimpleNamespace(active=True,check_active=lambda:None)
        server=types.SimpleNamespace(serve=lambda:None,close=lambda:None)
        transport=types.SimpleNamespace(native_recovery_record=lambda:{'fixture':'no actual network'})
        result={'status':'complete','cleanup':{'removed':True,'stopped_state':{'Running':False}}}
        failure=KeyboardInterrupt('cancel during output recording') if interrupt else OSError('output recording failed')
        module=bridge if recovery else adoption
        with patch.object(module,'_Permit' if recovery else 'AdoptionPermit',return_value=permit),patch.object(module.broker,'laboratory_guard',return_value=None),patch.object(module.broker,'EgressBroker',return_value=transport),patch.object(module.broker,'UnixBrokerServer',return_value=server),patch.object(module.host,'launch',return_value=result),patch.object(evidence,'capture',side_effect=failure):
            if interrupt:
                with self.assertRaises(KeyboardInterrupt):
                    if recovery:bridge.RecoveryPlanJob._dispatch(subject,{},runtime,spec,b'{}')
                    else:adoption.AdoptionJob._dispatch(subject,{},runtime,spec,verification=True)
            else:
                outcome=bridge.RecoveryPlanJob._dispatch(subject,{},runtime,spec,b'{}') if recovery else adoption.AdoptionJob._dispatch(subject,{},runtime,spec,verification=True)
                self.assertEqual(outcome['status'],'outcome_unknown')
        with policy.connection() as db:
            if recovery:row=db.execute('SELECT status,outcome FROM adoption_recovery_plans').fetchone()
            else:row=db.execute('SELECT verification_status,verification_outcome FROM adoption_operations').fetchone()
            self.assertEqual(row[0],'outcome_unknown');data=__import__('json').loads(row[1]);self.assertEqual(data['host'],result);self.assertIsNone(data['plan_output_capture']);self.assertEqual(db.execute('SELECT COUNT(*) FROM ownership').fetchone()[0],1)
        self.assertTrue(evidence.paths(self.job)['plan.bin'].exists())
    def test_initial_output_recording_failure_retains_host_and_unknown_ownership(self):self.exercise()
    def test_recovery_output_recording_failure_retains_host_and_unknown_ownership(self):self.exercise(recovery=True)
    def test_initial_cancellation_during_output_recording_is_durable_and_raised(self):self.exercise(interrupt=True)
    def test_recovery_cancellation_during_output_recording_is_durable_and_raised(self):self.exercise(recovery=True,interrupt=True)

if __name__=='__main__':unittest.main()
