"""Actual source bytes/CAS/recovery on recorded Win32; native remains blocked."""
import copy
import importlib.util
import io
import shlex
import sys
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from intune_iac import windows_source_edit as subject,windows_repository,workbench_views
from intune_iac.io import AppError
from plugin_tests import test_windows_source_r4 as source_fixture
from plugin_tests.test_windows_repository_r4 import RepositoryAPI
from plugin_tests.test_windows_storage_r4 import ROOT,CANONICAL,SID

class EditAPI(RepositoryAPI):
    def initialize(self):
        self.file_security={};self.renames=0;self.fail_before=None;self.fail_after=None;self.fail_clone=False;self.fail_after_rename_flush=False
    def edit_metadata(self,handle,sid):
        identity=self.file_metadata(handle,sid)
        return copy.deepcopy(self.file_security.setdefault(identity['file_id'],{'attributes':0x22,
            'security':{'owner_sid':SID,'dacl_protected':True,'aces':[{'type':'allow','sid':SID,'mask':0x1201bf,'flags':0}]}}))
    def open_candidate(self,path,sid):return self.open_file(path,sid)
    def clone_metadata(self,handle,metadata,sid):
        if self.fail_clone:raise AppError('injected_acl_copy_failure','literal')
        identity=self.file_metadata(handle,sid);self.file_security[identity['file_id']]=copy.deepcopy(metadata);self.events.append(('clone-metadata',identity['file_id']))
    def rename_new(self,handle,root_handle,name):
        if name.endswith(('.intent.json','.ready.json')):return super().rename_new(handle,root_handle,name)
        self.renames+=1
        if self.renames==self.fail_before:raise KeyboardInterrupt('injected before rename')
        super().rename_new(handle,root_handle,name)
        if self.renames==self.fail_after:raise AppError('injected_lost_rename_ack','literal')
    def flush_namespace(self,handle):
        if self.renames and self.fail_after_rename_flush:raise AppError('injected_namespace_barrier_failure','literal')
        return super().flush_namespace(handle)

class NativeSourceEditTests(unittest.TestCase):
    def setUp(self):
        self.fixture=source_fixture.NativeSourceTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.api=self.fixture.api;self.api.__class__=EditAPI;self.api.initialize()
        self.store=self.fixture.store;self.root=self.fixture.root;self.real=self.fixture.real;self.output=self.fixture.output
        self.fixture.imp();self.proposal=self.fixture.propose();self.expected=self.proposal['proposal_sha256'];self.expires=time.time()+1200
        self.before=(self.real/'stacks/defaults.yaml').read_bytes();self.after=self.api.real(CANONICAL+'\\proposal\\source.after.yaml').read_bytes()
    def apply(self,**kw):return subject._apply(self.store,self.output,kw.get('expected',self.expected),kw.get('expires',self.expires),kw.get('ack',True),self.api)
    def operation(self):return subject._acknowledge(self.store,self.proposal,self.expected,self.expires,True,self.api)['operation_id']
    def recover(self,direction):return subject._recover(self.store,self.root,self.operation(),direction,time.time()+600,True,self.api)
    def inspect(self):return subject._inspect(self.store,self.root,self.operation(),self.api)
    def test_exact_local_edit_preserves_backup_metadata_and_never_authorizes_plan(self):
        result=self.apply();self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.after)
        self.assertEqual(result['state'],'source_applied');self.assertTrue(result['fresh_plan_required']);self.assertFalse(result['protected_execution_performed'])
        files=result['observed_files'];self.assertEqual(files['original']['metadata'],files['backup']['metadata'])
        self.assertEqual(files['original']['metadata']['attributes'],0x22)
        backup=self.real/'stacks'/(''+subject.PREFIX+self.operation()+'.backup');self.assertEqual(backup.read_bytes(),self.before)
        self.assertEqual(self.api.renames,2);self.assertEqual(self.api.handles,{})
        with patch.object(windows_repository,'_NativeAPI',return_value=self.api):view=workbench_views.views(self.store,source_fixture.OID)
        self.assertEqual(view['repository']['current_working_source_readback']['policy_comparison']['changed_fields'],['description'])
        self.assertEqual(view['repository']['desired']['description'],None);self.assertEqual(view['deployment']['status'],'unknown')
    def test_ack_digest_expiry_replay_and_changed_source_fail_without_mutation(self):
        for kw in ({'ack':False},{'expires':time.time()-1},{'expected':'0'*64}):
            with self.subTest(kw=kw),self.assertRaises(AppError):self.apply(**kw)
            self.assertEqual(self.api.renames,0);self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.before)
        (self.real/'stacks/defaults.yaml').write_bytes(self.before+b' ')
        with self.assertRaises(AppError):self.apply()
        self.assertEqual(self.api.renames,0);(self.real/'stacks/defaults.yaml').write_bytes(self.before)
        self.apply();count=self.api.renames
        with self.assertRaises(AppError) as caught:self.apply()
        self.assertEqual(caught.exception.code,'windows_source_edit_replay_denied');self.assertEqual(self.api.renames,count)
    def test_lost_first_rename_ack_blocks_read_import_then_explicit_completion(self):
        self.api.fail_after=1
        with self.assertRaises(AppError) as caught:self.apply()
        self.assertTrue(caught.exception.source_edit_outcome['outcome_uncertain']);self.assertFalse((self.real/'stacks/defaults.yaml').exists())
        self.assertEqual(self.inspect()['classification'],'original_backed_up_candidate_ready')
        with self.assertRaises(AppError) as blocked:windows_repository._resolve(self.root,'deploy/pilot','intune',self.api)
        self.assertEqual(blocked.exception.code,'windows_repository_source_edit_unresolved')
        with patch.object(windows_repository,'_NativeAPI',return_value=self.api):view=workbench_views.views(self.store,source_fixture.OID)
        pending=view['repository']['current_working_source_readback']['pending_local_source_edit']
        self.assertEqual(pending['operation_id'],self.operation());self.assertEqual(pending['next_action']['command'],'source-edit-status')
        self.assertEqual(pending['source_root'],str(self.root));self.assertEqual(pending['next_action']['arguments'],[str(self.root),self.operation()])
        self.assertIs(pending['outcome_uncertain'],True);self.assertIs(pending['automatic_retry_permitted'],False)
        self.assertEqual(view['repository']['current_working_source_readback']['status'],'unknown');self.assertEqual(pending['invalid_closure_records'],[])
        self.assertFalse(view['native_evidence_access']['platform_qualified'])
        count=len(self.store.artifacts(kind='repository_intent'))
        with self.assertRaises(AppError):self.fixture.imp()
        self.assertEqual(len(self.store.artifacts(kind='repository_intent')),count)
        self.api.fail_after=None;result=self.recover('complete');self.assertEqual(result['state'],'source_applied')
        self.assertTrue(result['original_dispatch_uncertainty_preserved']);self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.after);self.assertEqual(self.api.handles,{})
    def test_lost_first_rename_ack_explicit_rollback_preserves_candidate(self):
        self.api.fail_after=1
        with self.assertRaises(AppError):self.apply()
        self.api.fail_after=None;result=self.recover('rollback');self.assertEqual(result['state'],'source_restored')
        self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.before)
        candidate=self.real/'stacks'/(subject.PREFIX+self.operation()+'.candidate');self.assertEqual(candidate.read_bytes(),self.after);self.assertEqual(self.api.handles,{})
    def test_lost_second_rename_ack_reconciles_without_replaying_mutation(self):
        self.api.fail_after=2
        with self.assertRaises(AppError):self.apply()
        self.assertEqual(self.inspect()['classification'],'candidate_applied');self.api.fail_after=None
        count=self.api.renames;result=self.recover('complete');self.assertEqual(self.api.renames,count)
        self.assertEqual(result['state'],'source_applied');self.assertTrue(result['recovery'])
    def test_lost_second_rename_ack_can_explicitly_restore_before_bytes(self):
        self.api.fail_after=2
        with self.assertRaises(AppError):self.apply()
        self.api.fail_after=None;result=self.recover('rollback');self.assertEqual(result['state'],'source_restored')
        self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.before);self.assertEqual(self.api.renames,4)
    def test_metadata_copy_failure_leaves_original_and_only_explicit_abort_closes(self):
        self.api.fail_clone=True
        with self.assertRaises(AppError) as caught:self.apply()
        self.assertEqual(caught.exception.code,'injected_acl_copy_failure');self.assertEqual(self.api.renames,0)
        self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.before)
        self.api.fail_clone=False
        with self.assertRaises(AppError):self.recover('complete')
        result=self.recover('abort');self.assertEqual(result['state'],'source_before_observed');self.assertEqual(self.api.handles,{})
    def test_barrier_failure_and_conflicting_destination_are_never_overwritten(self):
        self.api.fail_after_rename_flush=True
        with self.assertRaises(AppError):self.apply()
        self.api.fail_after_rename_flush=False;(self.real/'stacks/defaults.yaml').write_bytes(b'foreign changed source')
        with self.assertRaises(AppError) as caught:self.recover('complete')
        self.assertEqual(caught.exception.code,'windows_source_edit_conflicting_files');self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),b'foreign changed source')
        self.assertEqual(self.api.handles,{})
    def test_current_import_contending_writer_fails_before_new_intent(self):
        from intune_iac import windows_storage
        count=len(self.store.artifacts(kind='repository_intent'))
        with windows_storage._lock(self.root,subject.LOCK,self.api):
            with self.assertRaises(AppError) as caught:self.fixture.imp()
        self.assertEqual(caught.exception.code,'windows_storage_lock_busy');self.assertEqual(len(self.store.artifacts(kind='repository_intent')),count)
    def test_compound_primary_rename_and_close_failures_keep_primary_and_all_handles_close(self):
        original=self.api.rename_new;primary=KeyboardInterrupt('literal primary')
        def fail(*args):self.api.close_fail=True;raise primary
        with patch.object(self.api,'rename_new',side_effect=fail),self.assertRaises(KeyboardInterrupt) as caught:self.apply()
        self.assertIs(caught.exception,primary);self.assertEqual(self.api.handles,{})
        self.assertTrue(caught.exception.source_edit_outcome['outcome_uncertain'])

    def test_expiry_between_renames_does_not_leave_the_source_moved_away(self):
        # The acknowledgment window bounds when the edit may start; it is judged once, before the first rename.
        before=time.time()
        with patch.object(subject.time,'time',side_effect=lambda:self.expires+1 if self.api.renames else before):result=self.apply()
        self.assertEqual(result['state'],'source_applied');self.assertEqual(self.api.renames,2)
        self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.after)
    def test_expiry_before_the_first_rename_refuses_with_the_source_untouched(self):
        with patch.object(subject.time,'time',side_effect=lambda:self.expires+1),self.assertRaises(AppError) as caught:self.apply()
        self.assertEqual(caught.exception.code,'windows_source_edit_ack_expired');self.assertEqual(self.api.renames,0)
        self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.before)
    def test_failed_closure_requires_explicit_reconciliation_without_new_mutation(self):
        self.api.fail_creation='.closed.json'
        with self.assertRaises(AppError) as caught:self.apply()
        self.assertEqual(caught.exception.source_edit_outcome['phase'],'closure_pending')
        self.assertTrue(self.inspect()['outcome_uncertain']);self.assertEqual(self.api.renames,2)
        self.api.fail_creation=None;result=self.recover('complete')
        self.assertEqual(self.api.renames,2);self.assertEqual(result['state'],'source_applied')
    def test_changed_provider_lock_and_substituted_backup_are_rejected(self):
        lock=self.real/'components/terraform/intune/.terraform.lock.hcl';original=lock.read_bytes();lock.write_bytes(original+b'# changed')
        with self.assertRaises(AppError) as caught:self.apply()
        self.assertEqual(caught.exception.code,'windows_source_edit_source_changed');self.assertEqual(self.api.renames,0)
        lock.write_bytes(original);self.api.fail_after=1
        with self.assertRaises(AppError):self.apply()
        backup=self.real/'stacks'/(subject.PREFIX+self.operation()+'.backup');backup.write_bytes(b'altered retained backup')
        self.api.fail_after=None
        with self.assertRaises(AppError) as caught:self.recover('rollback')
        self.assertEqual(caught.exception.code,'windows_source_edit_conflicting_files');self.assertEqual(backup.read_bytes(),b'altered retained backup')
    def test_real_shared_terminal_review_edit_view_and_no_source_values_in_events(self):
        from intune_iac import workbench
        quote=shlex.quote;lines=iter(['select '+source_fixture.OID,'source-review '+quote(self.output)+' '+self.expected,
            'source-edit '+quote(self.output)+' '+self.expected+' '+str(self.expires)+' ACK-LOCAL-FILE-EDIT','views','quit']);results=[]
        with patch.object(subject,'_NativeAPI',return_value=self.api),patch.object(windows_repository,'_NativeAPI',return_value=self.api):
            out=workbench.run_terminal(str(self.store.root),input_fn=lambda _:next(lines),result_fn=results.append,_store_capability=self.store)
        self.assertEqual(out['status'],'closed');self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.after)
        self.assertEqual(len([r for r in results if r.get('schema_version')=='workbench-local-source-review/1']),1)
        self.assertEqual(len([r for r in results if r.get('schema_version')=='workbench-local-source-edit-closure/1']),1)
        self.assertNotIn('never-output',json.dumps(results));self.assertEqual(self.api.handles,{})
    def test_actual_cli_interruption_status_and_explicit_rollback(self):
        script=Path(subject.__file__).parents[1]/'scripts/intune-windows-source.py';spec=importlib.util.spec_from_file_location('native_source_edit_cli',script);app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
        prefix=['--qualification-only','--store',str(self.store.root),'--tenant',self.store.tenant_id]
        def run(args):
            out,err=io.StringIO(),io.StringIO()
            with patch.object(app,'WindowsWorkbenchStore',return_value=self.store),patch.object(subject,'_NativeAPI',return_value=self.api),patch('sys.stdout',out),patch('sys.stderr',err):code=app.main(prefix+args)
            return code,out.getvalue(),err.getvalue()
        self.api.fail_after=1;code,out,error=run(['source-edit','--proposal',self.output,'--digest',self.expected,'--expires-at',str(self.expires),'--acknowledge-local-file-edit'])
        self.assertEqual(code,3);self.assertTrue(json.loads(error)['source_edit_outcome']['outcome_uncertain'])
        self.api.fail_after=None;code,out,error=run(['source-edit-status','--source-root',self.root,'--operation',self.operation()])
        self.assertEqual(code,0);self.assertEqual(json.loads(out)['result']['classification'],'original_backed_up_candidate_ready')
        code,out,error=run(['source-edit-recover','--source-root',self.root,'--operation',self.operation(),'--direction','rollback','--expires-at',str(time.time()+600),'--acknowledge-local-file-edit'])
        self.assertEqual(code,0);self.assertEqual(json.loads(out)['result']['state'],'source_restored');self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.before)
        self.assertNotIn('never-output',out+error);self.assertEqual(self.api.handles,{})
    def test_interrupted_partial_closure_is_retained_and_recovery_can_publish_new_receipt(self):
        original=self.api.write
        def partial(handle,data):
            name=self.api.handles[handle][1]
            if '.closed' in name:
                original(handle,data[:len(data)//2]);raise KeyboardInterrupt('partial final receipt')
            return original(handle,data)
        with patch.object(self.api,'write',side_effect=partial),self.assertRaises(KeyboardInterrupt):self.apply()
        damaged=list(self.real.glob(subject.PREFIX+'*.closed*.json'))
        self.assertEqual(len(damaged),1);damaged_before=damaged[0].read_bytes();count=self.api.renames
        result=self.recover('complete')
        self.assertEqual(result['state'],'source_applied');self.assertEqual(self.api.renames,count)
        self.assertEqual(damaged[0].read_bytes(),damaged_before)
        self.assertEqual(len(self.inspect()['closure']['invalid_records']),1)

    def test_partial_initial_intent_never_publishes_a_poisoned_source_gate(self):
        original=self.api.write
        def partial(handle,data):
            if '.intent' in self.api.handles[handle][1]:
                original(handle,data[:len(data)//2]);raise KeyboardInterrupt('partial initial intent')
            return original(handle,data)
        with patch.object(self.api,'write',side_effect=partial),self.assertRaises(KeyboardInterrupt):self.apply()
        self.assertEqual(self.api.renames,0);self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.before)
        self.assertEqual(windows_repository._resolve(self.root,'deploy/pilot','intune',self.api)['status'],'resolved')
        self.assertTrue(list(self.real.glob(subject.PREFIX+'*.intent*')))
    def test_partial_ready_receipt_allows_only_explicit_abort_before_source_mutation(self):
        original=self.api.write
        def partial(handle,data):
            if '.ready' in self.api.handles[handle][1]:
                original(handle,data[:len(data)//2]);raise KeyboardInterrupt('partial ready intent')
            return original(handle,data)
        with patch.object(self.api,'write',side_effect=partial),self.assertRaises(KeyboardInterrupt):self.apply()
        self.assertEqual(self.api.renames,0);self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.before)
        result=self.recover('abort');self.assertEqual(result['state'],'source_before_observed')
        self.assertTrue(list(self.real.glob(subject.PREFIX+'*.ready*')))

    def test_import_lock_cleanup_failure_cannot_publish_repository_intent(self):
        count=len(self.store.artifacts(kind='repository_intent'));original=self.api.unlock
        def fail(*args):original(*args);raise KeyboardInterrupt('literal unlock failure')
        with patch.object(self.api,'unlock',side_effect=fail),self.assertRaises(KeyboardInterrupt):self.fixture.imp()
        self.assertEqual(len(self.store.artifacts(kind='repository_intent')),count)
        self.assertEqual(self.api.handles,{})
    def test_recovery_same_byte_candidate_substitution_between_observation_and_rename_is_denied(self):
        self.api.fail_after=1
        with self.assertRaises(AppError):self.apply()
        self.api.fail_after=None;original=subject._existing_state;replaced=[]
        def replace(*args):
            result=original(*args)
            if not replaced:
                path=self.real/'stacks'/(subject.PREFIX+self.operation()+'.candidate');raw=path.read_bytes()
                path.rename(path.with_name(path.name+'.retained'));path.write_bytes(raw);replaced.append(True)
            return result
        count=self.api.renames
        with patch.object(subject,'_existing_state',side_effect=replace),self.assertRaises(AppError):self.recover('complete')
        self.assertEqual(self.api.renames,count);self.assertFalse((self.real/'stacks/defaults.yaml').exists())
        self.assertEqual(self.api.handles,{})
    def test_recovery_same_byte_backup_substitution_is_denied_before_restore(self):
        self.api.fail_after=1
        with self.assertRaises(AppError):self.apply()
        self.api.fail_after=None;original=subject._existing_state;replaced=[]
        def replace(*args):
            result=original(*args)
            if not replaced:
                path=self.real/'stacks'/(subject.PREFIX+self.operation()+'.backup');raw=path.read_bytes()
                path.rename(path.with_name(path.name+'.retained'));path.write_bytes(raw);replaced.append(True)
            return result
        count=self.api.renames
        with patch.object(subject,'_existing_state',side_effect=replace),self.assertRaises(AppError):self.recover('rollback')
        self.assertEqual(self.api.renames,count);self.assertFalse((self.real/'stacks/defaults.yaml').exists())

    def test_recovery_changed_recorded_dependency_denies_completion_but_retains_rollback(self):
        self.api.fail_after=1
        with self.assertRaises(AppError):self.apply()
        self.api.fail_after=None;count=self.api.renames;lock=self.real/'components/terraform/intune/.terraform.lock.hcl'
        changed=lock.read_bytes()+b'# independently changed during interruption\n';lock.write_bytes(changed)
        with self.assertRaises(AppError) as caught:self.recover('complete')
        self.assertEqual(caught.exception.code,'windows_source_edit_dependency_changed');self.assertEqual(self.api.renames,count)
        result=self.recover('rollback');self.assertEqual((self.real/'stacks/defaults.yaml').read_bytes(),self.before);self.assertEqual(lock.read_bytes(),changed)
        self.assertFalse(result['recovery_context']['surrounding_inputs_restored'])
    def test_recovery_root_identity_change_before_dispatch_denies_source_mutation(self):
        self.api.fail_after=1
        with self.assertRaises(AppError):self.apply()
        self.api.fail_after=None;count=self.api.renames;original=subject._existing_state;changed=[];metadata=self.api.metadata
        def replace(*args):
            value=original(*args)
            if not changed:changed.append(True)
            return value
        def observed(handle,*args,**kw):
            value=metadata(handle,*args,**kw)
            if changed and self.api.real(value['final_path'])==self.real:value=dict(value,file_id='f'*32)
            return value
        with patch.object(subject,'_existing_state',side_effect=replace),patch.object(self.api,'metadata',side_effect=observed),self.assertRaises(AppError):self.recover('complete')
        self.assertEqual(self.api.renames,count);self.assertFalse((self.real/'stacks/defaults.yaml').exists())

    def test_linux_public_native_writer_factory_remains_blocked_before_mutation(self):
        if sys.platform=='win32':self.skipTest('Linux unsupported-host negative')
        with self.assertRaises(AppError) as caught:subject.apply_source_proposal(self.store,self.output,self.expected,self.expires,acknowledged=True)
        self.assertEqual(caught.exception.code,'windows_directory_platform_unsupported');self.assertEqual(self.api.renames,0)

if __name__=='__main__':unittest.main()


class NativePendingEditPresentationTests(unittest.TestCase):
    def pending(self):
        return {'operation_id':'a'*64,'source_root':ROOT,'outcome_uncertain':True,
            'next_action':{'command':'source-edit-status','arguments':[ROOT,'a'*64]},
            'invalid_closure_records':[],'automatic_retry_permitted':False}
    def test_closed_pending_shape_preserves_unknown_and_no_automatic_retry(self):
        from intune_iac.windows_views import _NativeViewReader
        value=self.pending();error=AppError('windows_repository_source_edit_unresolved','literal');error.source_edit_pending=value
        with patch.object(windows_repository,'readback_windows_repository',side_effect=error):
            result=_NativeViewReader().decorate({'repository':{'status':'recorded'}})
        retained=result['repository']['current_working_source_readback'];self.assertEqual(retained['pending_local_source_edit'],value)
        value['next_action']['arguments'][0]='changed later';self.assertEqual(retained['pending_local_source_edit']['next_action']['arguments'][0],ROOT)
        self.assertEqual(retained['status'],'unknown');self.assertFalse(retained['git_revision_verified'])
        self.assertFalse(result['native_evidence_access']['platform_qualified'])
    def test_wrong_error_or_changed_pending_command_never_invents_recovery_route(self):
        from intune_iac.windows_views import _NativeViewReader
        for code,change in [('different_error',lambda v:None),('windows_repository_source_edit_unresolved',lambda v:v.update(automatic_retry_permitted=True)),('windows_repository_source_edit_unresolved',lambda v:v['next_action'].update(command='source-edit-apply')),('windows_repository_source_edit_unresolved',lambda v:v.update(operation_id='wrong'))]:
            value=self.pending();change(value);error=AppError(code,'literal');error.source_edit_pending=value
            with patch.object(windows_repository,'readback_windows_repository',side_effect=error):
                result=_NativeViewReader().decorate({'repository':{'status':'recorded'}})
            self.assertNotIn('pending_local_source_edit',result['repository']['current_working_source_readback'])
