"""Protected command boundary: hostile inputs and real disposable subprocesses."""
import copy
import importlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class ProtectedCompletionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('intune_iac.protected'), 'protected implementation absent')
        self.api = importlib.import_module('intune_iac.protected')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.executor = self.api.create_synthetic_executor(self.base / 'fixture', initial_value={}, desired_value={'policies': {'id': 'hash'}})
        self.receipts = self.base / 'receipts'

    def prepared(self):
        request = self.api.prepare_native_operation(self.executor)
        self.assertEqual(request['action'], 'synthetic_saved_plan_apply')
        grant = self.api.approve_synthetic_operation(request, executor=self.executor)
        return request, grant

    def test_actual_fixed_subprocess_and_durable_saved_plan_apply(self):
        request, grant = self.prepared()
        self.assertEqual(request['review']['status'], 'changes_require_review')
        result = self.api.execute_native_operation(request, self.receipts, executor=self.executor, approval=grant)
        self.assertEqual(result['status'], 'succeeded_verified', result)
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(self.api.inspect_executor(self.executor)['value_sha256'], request['bindings']['desired_value_sha256'])
        history = self.api.read_native_operation(request['operation_id'], self.receipts)
        self.assertEqual([e['kind'] for e in history['events']], ['prepared','authorized','dispatch_started','readback_verified','completed'])
        self.assertEqual(history['receipt_sha256'], result['receipt_sha256'])
        self.assertEqual(self.api.reconcile_native_operation(request['operation_id'], self.receipts, executor=self.executor)['classification'], 'desired_state_observed')

    def test_forged_json_grant_and_unknown_action_never_dispatch(self):
        request, grant = self.prepared()
        with patch.object(self.api, '_run', side_effect=AssertionError('dispatch')):
            result = self.api.execute_native_operation(request, self.receipts, executor=self.executor, approval={'approved': True, 'signature':'self-signed'})
            self.assertEqual(result['status'], 'rejected')
            altered = copy.deepcopy(request); altered['action'] = 'cloud_apply'
            self.assertEqual(self.api.execute_native_operation(altered,self.receipts,executor=self.executor,approval=grant)['status'], 'rejected')

    def test_executable_config_and_saved_plan_substitution_rejected(self):
        for field in ['saved.tfplan', 'main.tf.json', 'worker.py']:
            with self.subTest(field=field):
                root = self.base / ('fixture-' + field)
                executor = self.api.create_synthetic_executor(root, initial_value={}, desired_value={'x': 1})
                request = self.api.prepare_native_operation(executor)
                grant = self.api.approve_synthetic_operation(request, executor=executor)
                location = root / ('work/' + field if field != 'worker.py' else field)
                location.chmod(0o600)
                location.write_bytes(location.read_bytes() + b' ')
                with patch.object(self.api, '_run', side_effect=AssertionError('dispatch')):
                    result = self.api.execute_native_operation(request, self.base / ('receipts-' + field), executor=executor, approval=grant)
                self.assertEqual(result['status'], 'rejected', result)

    def test_expiry_stale_state_and_replay_block(self):
        request, grant = self.prepared()
        with patch.object(self.api, '_now', return_value=request['expires_at']):
            self.assertEqual(self.api.execute_native_operation(request,self.receipts,executor=self.executor,approval=grant)['status'], 'rejected')
        result = self.api.execute_native_operation(request,self.receipts,executor=self.executor,approval=grant)
        self.assertEqual(result['status'], 'succeeded_verified')
        self.assertEqual(self.api.execute_native_operation(request,self.receipts,executor=self.executor,approval=grant)['status'], 'rejected')

    def test_stale_backend_even_equal_values_blocks(self):
        request, grant = self.prepared()
        path = self.base / 'fixture/work/state/terraform.tfstate'
        data = json.loads(path.read_text()); data['serial'] += 1
        path.write_text(json.dumps(data))
        with patch.object(self.api, '_run', side_effect=AssertionError('dispatch')):
            self.assertEqual(self.api.execute_native_operation(request,self.receipts,executor=self.executor,approval=grant)['status'], 'rejected')

    def test_target_lock_is_shared_across_receipt_directories(self):
        request, grant = self.prepared()
        lock = self.base / 'fixture/.operation-lock'; lock.mkdir()
        (lock / 'owner.json').write_text('{}')
        with patch.object(self.api, '_run', side_effect=AssertionError('dispatch')):
            result = self.api.execute_native_operation(request,self.base/'another-receipts',executor=self.executor,approval=grant)
        self.assertEqual(result['status'], 'rejected')
        self.assertTrue(lock.exists())

    def test_unknown_after_dispatch_retains_lock_and_never_replays(self):
        request, grant = self.prepared()
        real_run = self.api._run
        def uncertain(executor, command):
            answer = real_run(executor, command)
            if command == 'apply': raise OSError('CANARY_PRIVATE')
            return answer
        with patch.object(self.api, '_run', side_effect=uncertain):
            result = self.api.execute_native_operation(request,self.receipts,executor=self.executor,approval=grant)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertNotIn('CANARY', json.dumps(result))
        self.assertTrue((self.base / 'fixture/.operation-lock').is_dir())
        self.assertEqual(self.api.reconcile_native_operation(request['operation_id'],self.receipts,executor=self.executor)['classification'],'desired_state_observed')
        self.assertFalse(self.api.reconcile_native_operation(request['operation_id'],self.receipts,executor=self.executor)['replay_authorized'])

    def test_lease_owner_loss_cannot_be_released(self):
        request, grant = self.prepared()
        real_run = self.api._run
        def replaced(executor, command):
            answer = real_run(executor, command)
            if command == 'apply': (self.base / 'fixture/.operation-lock/owner.json').write_text('{}')
            return answer
        with patch.object(self.api, '_run', side_effect=replaced):
            result = self.api.execute_native_operation(request,self.receipts,executor=self.executor,approval=grant)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertTrue((self.base / 'fixture/.operation-lock').is_dir())

    def test_receipt_failure_after_readback_is_unknown(self):
        request, grant = self.prepared(); actual = self.api._event
        def fail(root, kind, payload):
            if kind == 'completed': raise OSError('disk')
            return actual(root, kind, payload)
        with patch.object(self.api, '_event', side_effect=fail):
            result = self.api.execute_native_operation(request,self.receipts,executor=self.executor,approval=grant)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertTrue((self.base / 'fixture/.operation-lock').is_dir())

    def test_sanitized_environment_no_inherited_tokens_or_cli_overrides(self):
        with patch.dict(os.environ, {'ARM_CLIENT_SECRET':'CANARY','TF_CLI_ARGS':'-destroy','LD_PRELOAD':'/canary','PYTHONPATH':'/canary'}):
            env = self.api._environment(self.executor)
        self.assertFalse(set(env) & {'ARM_CLIENT_SECRET','TF_CLI_ARGS','LD_PRELOAD','PYTHONPATH'})
        self.assertEqual(env['TF_WORKSPACE'], 'default')

    def test_extra_request_fields_and_symlink_roots_rejected(self):
        request, grant = self.prepared(); request['command']='rm -rf /'
        self.assertEqual(self.api.execute_native_operation(request,self.receipts,executor=self.executor,approval=grant)['status'], 'rejected')
        (self.base/'link').symlink_to(self.base/'fixture',target_is_directory=True)
        with self.assertRaises(ValueError): self.api.SyntheticExecutor(self.base/'link')

    def test_corrupt_receipt_cannot_claim_success(self):
        request,grant=self.prepared()
        self.api.execute_native_operation(request,self.receipts,executor=self.executor,approval=grant)
        path=self.receipts/request['operation_id']/'04.json'
        value=json.loads(path.read_text());value['payload']['raw_secret']='CANARY';path.write_text(json.dumps(value))
        self.assertEqual(self.api.read_native_operation(request['operation_id'],self.receipts)['status'],'unknown')


if __name__ == '__main__': unittest.main()

class ExecutableTrustRegressionTests(unittest.TestCase):
    def test_synthetic_manifest_cannot_install_an_arbitrary_tool(self):
        from intune_iac import protected as p
        from intune_iac.io import digest
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'fixture'
            p.create_synthetic_executor(root,initial_value={},desired_value={'x':1})
            tool=root/'tool';tool.chmod(0o700);tool.write_bytes(b'#!/bin/sh\nexit 0\n')
            manifest=json.loads((root/'executor.json').read_text());manifest['executable_sha256']=p._sha(tool)
            (root/'executor.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):p.SyntheticExecutor(root)

class NativeContextCompletionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('intune_iac.native_context'),'native context implementation absent')
        self.api=importlib.import_module('intune_iac.native_context')
        from plugin_tests.test_target import fixture,NOW
        self.document=fixture()
        self.clock=patch('intune_iac.target._now',return_value=NOW);self.clock.start();self.addCleanup(self.clock.stop)
        self.state={'version':4,'terraform_version':'1.10.0','lineage':self.document['binding']['backend']['state_lineage'],'serial':7,'resources':[],'outputs':{}}
        from intune_iac.io import canonical
        import hashlib
        self.body=canonical(self.state)
        self.document['binding']['backend']['state_sha256']=hashlib.sha256(self.body).hexdigest()
        self.headers={'etag':'"test-etag"','content-length':str(len(self.body)),'x-ms-blob-type':'BlockBlob','x-ms-lease-status':'locked','x-ms-lease-state':'leased','x-ms-lease-duration':'infinite'}

    def test_head_get_if_match_head_exact_state_and_no_identity_overclaim(self):
        def response(host,path,token,method,timeout,etag=None):
            return (dict(self.headers),self.body if method=='GET' else b'')
        with patch.object(self.api,'_blob_read',side_effect=response) as read:
            result=self.api.collect_backend_observation(self.document,storage_token='opaque-token')
        self.assertEqual(result['status'],'observed',result)
        self.assertEqual([x.args[3] for x in read.call_args_list],['HEAD','GET','HEAD'])
        self.assertEqual(read.call_args_list[1].kwargs['etag'],'"test-etag"')
        self.assertEqual(read.call_args_list[0].args[0],'syntheticstate.blob.core.windows.net')
        self.assertEqual(read.call_args_list[0].args[1],'/tfstate/intune.tfstateenv%3Alab')
        self.assertFalse(result['execution_authorized'])
        self.assertIn('backend_principal_not_authenticated',result['blockers'])
        self.assertIn('writer_ownership_not_authenticated',result['blockers'])
        self.assertNotIn('opaque-token',json.dumps(result))

    def test_changed_etag_denied_partial_and_serial_mismatch_fail_closed(self):
        cases=['changed_etag','denied','partial','serial']
        for case in cases:
            calls=[]
            def response(host,path,token,method,timeout,etag=None):
                calls.append(method);headers=dict(self.headers);body=self.body if method=='GET' else b''
                if case=='denied':raise OSError('CANARY')
                if case=='changed_etag' and len(calls)>1:headers['etag']='"other"'
                if case=='partial' and method=='GET':body=body[:-1]
                if case=='serial' and method=='GET':body=body.replace(b'"serial":7',b'"serial":8')
                return headers,body
            with self.subTest(case=case),patch.object(self.api,'_blob_read',side_effect=response):
                result=self.api.collect_backend_observation(self.document,storage_token='opaque-token')
            self.assertEqual(result['status'],'unavailable',result)
            self.assertNotIn('CANARY',json.dumps(result))

    def test_self_signed_reports_never_authorize_cloud(self):
        result=self.api.inspect_native_context(self.document,attestations={'approved':True,'self_signed':True,'principal_verified':True})
        self.assertEqual(result['status'],'blocked')
        self.assertFalse(result['execution_authorized'])
        self.assertIn('protected_credential_provider_required',result['blockers'])
        self.assertIn('cloud_mutation_adapter_unavailable',result['blockers'])

class ProcessBoundaryTests(unittest.TestCase):
    def setUp(self):
        from intune_iac import protected
        self.api=protected
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.python=str(Path(__import__('sys').executable).resolve())

    def call(self,code,**kwargs):
        return self.api._supervise([self.python,'-I','-S','-c',code],cwd=self.root,env={'PATH':'/usr/bin:/bin'},**kwargs)

    def test_native_process_has_kernel_network_denial(self):
        out=self.call('import socket\ntry: socket.socket()\nexcept PermissionError: print("denied")\nelse: raise RuntimeError("network enabled")')
        self.assertEqual(out,b'denied\n')

    def test_unbounded_output_and_timeout_do_not_escape(self):
        from intune_iac.io import AppError
        with self.assertRaises(AppError) as caught:self.call('print("CANARY"*10000)',output_limit=1000)
        self.assertEqual(caught.exception.code,'process_output_limit')
        self.assertNotIn('CANARY',str(caught.exception))
        with self.assertRaises(AppError) as caught:self.call('import time; time.sleep(60)',timeout=1)
        self.assertEqual(caught.exception.code,'process_timeout')

    def test_descendant_inherits_deadline_even_when_direct_child_exits(self):
        from intune_iac.io import AppError
        pidfile=self.root/'child.pid'
        code='import os,time\np=os.fork()\nif p==0:\n time.sleep(60)\nelse:\n open("child.pid","w").write(str(p))\n'
        # Isolate supervisor cleanup from the stronger production no-fork filter.
        # Only this controlled test disables the pre-exec guard to create a child.
        with patch.object(self.api,'_network_filter',return_value=(lambda:None,lambda:None)):
            with self.assertRaises(AppError):self.call(code,timeout=1)
        pid=int(pidfile.read_text())
        status=Path('/proc')/str(pid)/'stat'
        if status.exists():self.assertEqual(status.read_text().split()[2],'Z')

    def test_unrelated_inheritable_descriptor_is_closed(self):
        fd=os.open(self.root/'private',os.O_CREAT|os.O_RDWR,0o600)
        try:
            os.set_inheritable(fd,True)
            out=self.call('import os\ntry: os.fstat('+str(fd)+')\nexcept OSError: print("closed")\nelse: print("leaked")')
            self.assertEqual(out,b'closed\n')
        finally:os.close(fd)

    def test_values_cannot_become_terraform_expressions_even_on_resume(self):
        for value in ({'x':'${file("/etc/passwd")}'},['%{ for x in [] }']):
            with self.assertRaises(ValueError):self.api.create_synthetic_executor(self.root/'bad',initial_value={},desired_value=value)
        executor=self.api.create_synthetic_executor(self.root/'f',initial_value={},desired_value={})
        from intune_iac.io import digest
        config=json.loads((executor.root/'work/main.tf.json').read_text());config['output']['fixture']['value']={'x':'${file("/etc/passwd")}'}
        (executor.root/'work/main.tf.json').write_text(json.dumps(config))
        manifest=json.loads((executor.root/'executor.json').read_text());manifest['desired_value_sha256']=digest(config['output']['fixture']['value'])
        (executor.root/'executor.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):self.api.SyntheticExecutor(executor.root)


class NativeOpenTofuCompletionTests(unittest.TestCase):
    @unittest.skipUnless(Path('/tmp/intune-native-completion/tofu').exists(),'pinned native tool not installed; see measured qualification')
    def test_pinned_actual_native_saved_plan_apply_and_raw_mismatch_preserved(self):
        from intune_iac import protected as p
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            executor=p.create_native_local_executor(root/'f',executable='/tmp/intune-native-completion/tofu',initial_value={},desired_value={'x':1})
            request=p.prepare_native_operation(executor)
            self.assertEqual(request['review']['generic_review_status'],'blocked')
            self.assertIn({'code':'prior_output_value_mismatch','location':'plan'},request['review']['generic_blockers'])
            approval=p.approve_native_local_operation(request,executor=executor)
            result=p.execute_native_operation(request,root/'receipts',executor=executor,approval=approval)
            self.assertEqual(result['status'],'succeeded_verified',result)
            self.assertEqual(result['assurance'],'native_local_opentofu_only')
            self.assertEqual(p.reconcile_native_operation(request['operation_id'],root/'receipts',executor=executor)['classification'],'desired_state_observed')

class StateLineageRegressionTests(unittest.TestCase):
    def test_state_replacement_with_desired_value_cannot_claim_success(self):
        from intune_iac import protected as p
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);executor=p.create_synthetic_executor(root/'f',initial_value={},desired_value={'x':1})
            request=p.prepare_native_operation(executor);approval=p.approve_synthetic_operation(request,executor=executor)
            original=p._run
            def replacement(executor,command):
                output=original(executor,command)
                if command=='apply':
                    path=executor.root/'work/state/terraform.tfstate';state=json.loads(path.read_text())
                    state['lineage']='new-lineage';state['serial']=0;path.write_text(json.dumps(state))
                return output
            with patch.object(p,'_run',side_effect=replacement):result=p.execute_native_operation(request,root/'receipts',executor=executor,approval=approval)
            self.assertEqual(result['status'],'outcome_unknown',result)
            self.assertEqual(p.reconcile_native_operation(request['operation_id'],root/'receipts',executor=executor)['classification'],'diverged')

class CrossJournalReplayRegressionTests(unittest.TestCase):
    def test_consumed_request_cannot_gain_new_approval_in_another_journal(self):
        from intune_iac import protected as p
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);e=p.create_synthetic_executor(root/'f',initial_value={},desired_value={})
            req=p.prepare_native_operation(e);approval=p.approve_synthetic_operation(req,executor=e)
            original=p._run
            # Native no-op may leave its backend state byte-identical.
            def noop(executor,command):return b'' if command=='apply' else original(executor,command)
            with patch.object(p,'_run',side_effect=noop):result=p.execute_native_operation(req,root/'a',executor=e,approval=approval)
            self.assertEqual(result['status'],'succeeded_verified',result)
            with self.assertRaises(ValueError):p.approve_synthetic_operation(req,executor=e)

class ReviewBindingRegressionTests(unittest.TestCase):
    def test_rewritten_preparation_cannot_mislabel_change_as_noop(self):
        from intune_iac import protected as p
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);e=p.create_synthetic_executor(root/'f',initial_value={},desired_value={'x':1})
            request=p.prepare_native_operation(e)
            request['review']['status']='no_change';request['review']['generic_review_status']='no_change'
            (e.root/'preparation.json').write_text(json.dumps(request))
            with self.assertRaises(ValueError):p.approve_synthetic_operation(request,executor=e)

class NativeBinaryProvenanceRegressionTests(unittest.TestCase):
    @unittest.skipUnless(Path('/tmp/intune-native-completion/tofu').exists(),'pinned native tool not installed')
    def test_rehashed_binary_with_provisioner_cannot_use_benign_plan_json(self):
        from intune_iac import protected as p
        from intune_iac.io import canonical,digest
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);e=p.create_native_local_executor(root/'f',executable='/tmp/intune-native-completion/tofu',initial_value={},desired_value={'x':1})
            request=p.prepare_native_operation(e)
            innocent=(e.root/'work/main.tf.json').read_bytes()
            # PLANNING ONLY: this provisioner is never applied, even in the RED run.
            config=json.loads(innocent)
            config['resource']={'terraform_data':{'unexpected':{'input':'x','provisioner':[{'local-exec':{'command':'touch '+str(root/'SHOULD_NOT_EXIST')}}]}}}
            (e.root/'work/main.tf.json').write_bytes(canonical(config))
            p._supervise([str(e.executable),'plan','-input=false','-no-color','-lock=true','-lock-timeout=0s','-out='+str(e.root/'work/saved.tfplan')],cwd=e.root/'work',env=p._environment(e))
            (e.root/'work/main.tf.json').write_bytes(innocent)
            request['bindings']['saved_plan_sha256']=p._sha(e.root/'work/saved.tfplan')
            request['binding_sha256']=digest(request['bindings'])
            (e.root/'preparation.json').write_bytes(canonical(request))
            with self.assertRaises(ValueError):p.approve_native_local_operation(request,executor=e)
            self.assertFalse((root/'SHOULD_NOT_EXIST').exists())

class SyntheticSemanticBindingRegressionTests(unittest.TestCase):
    def test_consistent_noop_json_cannot_hide_real_saved_value_change(self):
        from intune_iac import protected as p
        from intune_iac.io import canonical,digest
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);e=p.create_synthetic_executor(root/'f',initial_value={},desired_value={'x':1})
            request=p.prepare_native_operation(e);path=e.root/'work/plan.json';document=json.loads(path.read_text())
            change=document['output_changes']['fixture'];change['before']=change['after'];change['actions']=['no-op']
            document['prior_state']['values']['outputs']['fixture']['value']=change['after']
            path.write_bytes(canonical(document))
            reviewed=p.review_plan(document)
            request['review']={'status':reviewed['status'],'plan_json_sha256':reviewed['plan_json_sha256'],'generic_review_status':reviewed['status'],'generic_blockers':reviewed['blockers']}
            request['bindings']['plan_json_sha256']=p._sha(path);request['binding_sha256']=digest(request['bindings'])
            (e.root/'preparation.json').write_bytes(canonical(request))
            with self.assertRaises(ValueError):p.approve_synthetic_operation(request,executor=e)

class BackendTransportBoundaryTests(unittest.TestCase):
    def test_exact_tls_headers_no_redirect_and_cleanup(self):
        from intune_iac import native_context as context
        from unittest.mock import Mock
        body=b'{"version":4}'
        headers=[('ETag','"etag"'),('Content-Length',str(len(body))),('x-ms-blob-type','BlockBlob'),('x-ms-lease-status','unlocked'),('x-ms-lease-state','available')]
        response=Mock(status=200);response.getheaders.return_value=headers;response.read.return_value=body
        connection=Mock();connection.getresponse.return_value=response
        with patch.object(context.http.client,'HTTPSConnection',return_value=connection) as constructor,patch.object(context.threading,'Timer') as timer:
            actual_headers,actual_body=context._blob_read('synthetic.blob.core.windows.net','/state/fixed','opaque','GET',5,etag='"etag"')
        self.assertEqual(actual_body,body)
        constructor.assert_called_once()
        self.assertEqual(constructor.call_args.args,('synthetic.blob.core.windows.net',))
        sent=connection.request.call_args
        self.assertEqual(sent.args,('GET','/state/fixed'))
        self.assertEqual(sent.kwargs['headers']['Authorization'],'Bearer opaque')
        self.assertEqual(sent.kwargs['headers']['If-Match'],'"etag"')
        self.assertEqual(sent.kwargs['headers']['x-ms-version'],'2023-11-03')
        self.assertIn('x-ms-date',sent.kwargs['headers'])
        connection.close.assert_called_once();timer.return_value.cancel.assert_called_once()
        for status,extra in [(302,[]),(206,[]),(200,[('ETag','"duplicate"')]),(200,[('Content-Encoding','gzip')])]:
            response=Mock(status=status);response.getheaders.return_value=headers+extra;response.read.return_value=body
            connection=Mock();connection.getresponse.return_value=response
            with self.subTest(status=status,extra=extra),patch.object(context.http.client,'HTTPSConnection',return_value=connection),patch.object(context.threading,'Timer'):
                with self.assertRaises(ValueError):context._blob_read('synthetic.blob.core.windows.net','/state/fixed','opaque','GET',5)
                connection.close.assert_called_once()

    def test_invalid_host_credentials_and_clock_prevent_network_dispatch(self):
        from intune_iac import native_context as context
        from plugin_tests.test_target import fixture,NOW
        with patch('intune_iac.target._now',return_value=NOW),patch.object(context,'_blob_read') as transport:
            bad=fixture();bad['binding']['backend']['blob_endpoint']='https://attacker.invalid'
            self.assertEqual(context.collect_backend_observation(bad,storage_token='opaque')['status'],'invalid')
            self.assertEqual(context.collect_backend_observation(fixture(),storage_token='opaque\nheader')['status'],'invalid')
            self.assertEqual(context.collect_backend_observation(fixture(),storage_token='opaque',timeout=True)['status'],'invalid')
            bad=fixture();bad['observed_at']='2020-01-01T00:00:00Z'
            self.assertEqual(context.collect_backend_observation(bad,storage_token='opaque')['status'],'invalid')
            transport.assert_not_called()

class ChildResourceBoundaryRegressionTests(unittest.TestCase):
    def setUp(self):
        from intune_iac import protected
        self.api=protected
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.python=str(Path(__import__('sys').executable).resolve())

    def run_child(self,code):
        return self.api._supervise([self.python,'-I','-S','-c',code],cwd=self.root,env={'PATH':'/usr/bin:/bin'})

    def test_parser_like_oversized_virtual_allocation_fails_without_host_allocation(self):
        # Anonymous mapping reserves address space without touching 5 GiB RAM.
        code='import mmap\ntry:\n m=mmap.mmap(-1,5*1024**3)\nexcept (OSError,MemoryError):\n print("bounded")\nelse:\n print("unbounded");m.close()'
        self.assertEqual(self.run_child(code),b'bounded\n')

    def test_process_creation_denied_but_runtime_threads_work(self):
        code='import os,threading\nt=threading.Thread(target=lambda:None);t.start();t.join()\ntry:\n pid=os.fork()\nexcept PermissionError:\n print("process-denied-thread-ok")\nelse:\n if pid==0: os._exit(0)\n os.waitpid(pid,0);print("process-allowed")'
        self.assertEqual(self.run_child(code),b'process-denied-thread-ok\n')

    def test_hard_limits_and_nondumpable_core_budget(self):
        code='import json,resource\nprint(json.dumps({name:resource.getrlimit(getattr(resource,name)) for name in ("RLIMIT_AS","RLIMIT_CPU","RLIMIT_FSIZE","RLIMIT_NOFILE","RLIMIT_CORE")}))'
        observed=json.loads(self.run_child(code))
        self.assertEqual(observed,{'RLIMIT_AS':[4*1024**3]*2,'RLIMIT_CPU':[20]*2,'RLIMIT_FSIZE':[64*1024**2]*2,'RLIMIT_NOFILE':[256]*2,'RLIMIT_CORE':[0,0]})

    def test_sparse_file_budget_stops_growth(self):
        code='import os,signal\nsignal.signal(signal.SIGXFSZ,signal.SIG_IGN)\nf=open("bounded-file","wb")\ntry:\n f.truncate(65*1024**2)\nexcept OSError:\n print("bounded")\nelse:\n print("unbounded")\nfinally:\n f.close()'
        self.assertEqual(self.run_child(code),b'bounded\n')
        self.assertLessEqual((self.root/'bounded-file').stat().st_size,64*1024**2)
