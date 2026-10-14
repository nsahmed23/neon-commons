"""Protected-service presentation and read-only navigation; no UI execution authority.

Hand-authored response fixtures qualify presentation only. Actual service/PTY
cases are separate and retain their real policy/journal checks.
"""
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

from intune_iac.io import AppError
from intune_iac.workbench_store import WorkbenchStore
from intune_iac.workbench_tui import CONTEXT_VERSION, SERVICE_NAVIGATION_VERSION, Workspace
from plugin_tests import test_worker_service_r4 as service_tests

PROJECT=Path(__file__).resolve().parents[1]
CLI=PROJECT/'scripts/intune-iac.py'

TENANT='11111111-1111-4111-8111-111111111111'
OBJECT='22222222-2222-4222-8222-222222222222'
OTHER='33333333-3333-4333-8333-333333333333'


class ServicePresentationTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.store=WorkbenchStore.create(self.root/'store',TENANT)
        self.ui=Workspace(self.store.root,stdin=io.StringIO(),stdout=io.StringIO())
        self.job=str(self.root/'service job 界')
        self.policy=str(self.root/"policy ' reviewed.json")

    def response(self,action='review',**changes):
        manifest={'operation_id':'service-op-12071','tenant_id':TENANT,'object_ids':[OBJECT],
                  'profile':'native_docker_laboratory_tls','action':'apply_saved_plan',
                  'saved_plan_sha256':'c'*64,'backend_scope_sha256':'d'*64,
                  'execution_binding_sha256':'e'*64,'run_binding_sha256':'f'*64,
                  'expires_at':1791500000}
        value={'manifest':manifest,'manifest_sha256':'a'*64,'signature_domain_hex':'73636f706500',
               'authority':'independent_external_signer_required','execution_authorized':False,
               'production_authorized':False,'operation_id':manifest['operation_id'],'tenant_id':TENANT,
               'object_ids':[OBJECT],'profile':manifest['profile'],'saved_plan_sha256':'c'*64,
               'expires_at':manifest['expires_at'],'service_job_root':self.job,'service_policy':self.policy,
               'evidence_class':'protected_service_journal','interface_action':action,
               'terminal_dispatches_mutation':False,'platform_qualified':False}
        if action!='review':
            value.pop('manifest');value.update(status='running',cancel_requested=False,dispatches=1,outcome=None,
                events=[{'sequence':1,'kind':'prepared','payload':{'manifest_sha256':'a'*64},'created_at':1791400000}],
                ci_attestation='unestablished_host_policy_contract_only')
        value.update(changes);return value

    def command(self,action):return 'service-'+action+' '+shlex.quote(self.job)+' '+shlex.quote(self.policy)

    def test_service_review_presents_manifest_and_approval_scope(self):
        self.ui._send(self.command('review'));self.ui.receive(self.response())
        shown='\n'.join(self.ui._surface_summary(120))
        self.assertIn('[PROTECTED SERVICE REVIEW]',shown)
        self.assertIn('Manifest SHA-256: '+'a'*64,shown)
        self.assertIn('Plan SHA-256: '+'c'*64,shown)
        self.assertIn('independent_external_signer_required',shown)
        self.assertIn(OBJECT,shown)
        self.assertEqual(self.ui._tab_command(4),self.command('review'))
        self.assertEqual(self.ui._tab_command(5),self.command('attach'))

    def test_status_keeps_cancellation_distinct_from_unknown_outcome(self):
        self.ui._send(self.command('status'));self.ui.receive(self.response('status',cancel_requested=True))
        shown='\n'.join(self.ui._surface_summary(120))
        self.assertIn('[PROTECTED SERVICE EXECUTION]',shown)
        self.assertIn('Durable status: running',shown)
        self.assertIn('Cancellation requested: true',shown)
        self.assertIn('Recorded dispatches: 1',shown)
        self.assertIn('not recorded; outcome unknown',shown)
        self.assertIn('does not establish termination',shown)
        self.assertIn('unestablished_host_policy_contract_only',shown)
        self.assertNotIn('succeeded',shown)

    def test_complete_exact_manifest_and_journal_remain_inspectable(self):
        value=self.response();value['manifest']['provider_binding']={'opaque':'retain exact value 界'}
        self.ui._send(self.command('review'));self.ui.receive(value)
        self.assertIn('retain exact value 界','\n'.join(self.ui._data_lines(180)))
        value=self.response('attach',outcome={'operation_outcome':'host_completed_service_unverified',
            'independent_service_readback':'required','primary_error':None})
        self.ui._send(self.command('attach'));self.ui.receive(value)
        shown='\n'.join(self.ui._data_lines(180))
        self.assertIn('host_completed_service_unverified',shown)
        self.assertIn('independent_service_readback',shown)
        self.assertIn('prepared',shown)
        self.assertIn('does not establish independent service or device convergence',shown)

    def test_only_readonly_paths_survive_detach_and_tab_switch(self):
        self.ui._send(self.command('review'));self.ui.receive(self.response())
        self.ui._send('overview');self.ui.receive({'objects':[]})
        restored=Workspace(self.store.root,stdin=io.StringIO(),stdout=io.StringIO())
        self.assertEqual(restored._tab_command(4),self.command('review'))
        self.assertEqual(restored._tab_command(5),self.command('attach'))
        saved=json.loads(self.ui.context_path.read_text())
        self.assertEqual(saved['service_navigation'],{'schema_version':SERVICE_NAVIGATION_VERSION,
            'job_root':self.job,'policy_path':self.policy,'read_action':'review'})
        for secret in ('manifest','signature_domain_hex','approval','saved_plan_sha256','a'*64,'c'*64):
            self.assertNotIn(secret,self.ui.context_path.read_text())

    def test_cancel_and_recover_never_replay_after_detach(self):
        for action in ('cancel','recover'):
            with self.subTest(action=action):
                self.ui._send(self.command(action));self.ui.receive(self.response(action,cancel_requested=True))
                restored=Workspace(self.store.root,stdin=io.StringIO(),stdout=io.StringIO())
                self.assertEqual(restored.active_service['read_action'],'attach')
                self.assertIn(self.command('attach'),list(restored.pending))
                self.assertFalse(any(command.startswith(('service-cancel','service-recover','service-run'))
                                     for command in restored.pending))

    def test_saved_mutating_or_unbounded_service_context_is_rejected(self):
        base={'schema_version':CONTEXT_VERSION,'tenant_id':TENANT,'selected':None,
              'view_command':self.command('review'),'page_command':'overview','tab':4}
        nav={'schema_version':SERVICE_NAVIGATION_VERSION,'job_root':self.job,'policy_path':self.policy,'read_action':'review'}
        invalid=[dict(base,view_command=self.command(action)) for action in ('cancel','recover','run','prepare')]
        invalid.extend([dict(base,service_navigation=dict(nav,read_action='cancel')),
            dict(base,service_navigation=dict(nav,signed_receipt={'approved':True})),
            dict(base,service_navigation=dict(nav,job_root='/different/job')),
            dict(base,page_command=self.command('attach')),
            dict(base,view_command='service-review relative/path '+shlex.quote(self.policy)),
            dict(base,view_command='service-review '+shlex.quote('/a/../b')+' '+shlex.quote(self.policy)),
            dict(base,view_command='service-review '+shlex.quote('/a\nforged')+' '+shlex.quote(self.policy)),
            dict(base,view_command='service-review "unfinished')])
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(AppError) as error:self.ui._validate_context(candidate)
                self.assertEqual(error.exception.code,'workspace_context_invalid')

    def test_legacy_context_readonly_service_route_is_safe_and_quoted(self):
        saved={'schema_version':CONTEXT_VERSION,'tenant_id':TENANT,'selected':None,
               'view_command':self.command('status'),'page_command':'overview','tab':5}
        self.ui.context_path.write_text(json.dumps(saved));self.ui.context_path.chmod(0o600)
        restored=Workspace(self.store.root,stdin=io.StringIO(),stdout=io.StringIO())
        self.assertEqual(list(restored.pending),['overview',self.command('status')])
        restored._send(self.command('status'));restored.receive(self.response('status'))
        self.assertEqual(shlex.split(restored._tab_command(4)),['service-review',self.job,self.policy])

    def test_wrong_object_or_policy_error_does_not_replace_active_service(self):
        self.ui._send(self.command('review'));self.ui.receive(self.response())
        before=self.ui.context_path.read_bytes()
        self.ui._send('service-review /another/job /another/policy')
        self.ui.receive({'status':'error','error':{'code':'service_workspace_target_mismatch'}})
        self.assertEqual(self.ui.context_path.read_bytes(),before)
        self.assertEqual(self.ui._tab_command(4),self.command('review'))

    def test_new_selected_identity_clears_active_service(self):
        self.ui.selected=OBJECT
        self.ui._send(self.command('review'));self.ui.receive(self.response())
        self.ui._send('select '+OTHER);self.ui.receive({'object_id':OTHER})
        self.assertIsNone(self.ui.active_service)
        self.assertEqual(self.ui._tab_command(4),'operations')


@unittest.skipUnless(sys.platform.startswith('linux'), 'Actual Linux service journal/PTY qualification')
class ServiceEntrypointTests(unittest.TestCase):
    """Real protected journal and CLI; intentionally no worker dispatch or live claim."""
    @classmethod
    def setUpClass(cls):service_tests.WorkerServiceR4Tests.setUpClass()
    @classmethod
    def tearDownClass(cls):service_tests.WorkerServiceR4Tests.tearDownClass()

    def setUp(self):
        self.fixture=service_tests.WorkerServiceR4Tests('test_cancel_before_dispatch_and_restart_cannot_start')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare()
        self.store=WorkbenchStore.create(self.fixture.root/'ui-store',self.fixture.manifest['tenant_id'])
        self.commands=[]
        retained=os.environ.get('INTUNE_SERVICE_UI_TEST_EVIDENCE')
        self.evidence=Path(retained)/self._testMethodName if retained else None
        if self.evidence:
            self.evidence.mkdir(parents=True,exist_ok=False)
            self.addCleanup(self.preserve)

    def preserve(self):
        (self.evidence/'commands.json').write_text(json.dumps(self.commands,indent=2)+'\n')
        (self.evidence/'final-status.json').write_text(json.dumps(self.fixture.job().status(),indent=2)+'\n')
        (self.evidence/'manifest.json').write_text(json.dumps(self.fixture.manifest,indent=2)+'\n')
        if hasattr(self,'output'):(self.evidence/'pty.raw').write_bytes(bytes(self.output))
        context=self.store.root/'workspace-context.json'
        if context.exists():(self.evidence/'workspace-context.json').write_bytes(context.read_bytes())

    def command(self,action):
        return 'service-'+action+' '+shlex.quote(str(self.fixture.job_root))+' '+shlex.quote(str(self.fixture.policy_path))

    def cli(self,args,*,input=None):
        command=[sys.executable,'-B',str(CLI),*args]
        result=subprocess.run(command,input=input,text=True,capture_output=True,timeout=15,cwd='/tmp')
        self.commands.append({'argv':command,'stdin':input,'returncode':result.returncode,
            'stdout':result.stdout,'stderr':result.stderr})
        return result

    def test_actual_cli_and_no_tty_read_same_job_without_dispatch(self):
        before=self.fixture.job().status()
        for action in ('review','status','attach'):
            result=self.cli(['service',action,'--job-root',str(self.fixture.job_root),'--policy',str(self.fixture.policy_path)])
            self.assertEqual(result.returncode,0,result.stderr)
            value=json.loads(result.stdout)
            self.assertEqual(value['operation_id'],self.fixture.identifier)
            self.assertEqual(value['manifest_sha256'],before['manifest_sha256'])
            self.assertFalse(value['terminal_dispatches_mutation'])
        result=self.cli(['workbench','workspace','--root',str(self.store.root)],
            input='\n'.join([self.command('review'),self.command('status'),self.command('attach'),'quit','']))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('\x1b',result.stdout)
        self.assertIn('protected_service_journal',result.stdout)
        self.assertIn(self.fixture.identifier,result.stdout)
        self.assertEqual(self.fixture.job().status(),before)
        self.assertEqual(self.fixture.fixture.calls,[])
        self.assertFalse((self.store.root/'workspace-context.json').exists())

    def test_actual_terminal_tenant_mismatch_cannot_cancel(self):
        before=self.fixture.job().status()
        wrong=WorkbenchStore.create(self.fixture.root/'wrong-tenant',TENANT)
        result=self.cli(['workbench','workspace','--root',str(wrong.root)],input=self.command('cancel')+'\nquit\n')
        self.assertIn('service_workspace_target_mismatch',result.stdout)
        self.assertEqual(self.fixture.job().status(),before)
        self.assertEqual(self.fixture.fixture.calls,[])

    def test_actual_pty_review_attach_cancel_detach_and_reopen_never_replay(self):
        import fcntl
        import pty
        import struct
        import termios
        from plugin_tests import test_workbench_tui_r4 as tui_tests
        self.master,self.slave=pty.openpty();self.addCleanup(os.close,self.master);self.addCleanup(os.close,self.slave)
        fcntl.ioctl(self.slave,termios.TIOCSWINSZ,struct.pack('HHHH',36,140,0,0))
        self.before_attrs=termios.tcgetattr(self.slave);self.output=bytearray();self.proc=None
        for name in ('read_until','drain','key','settle','launched','close_visual','cleanup_child'):
            setattr(self,name,getattr(tui_tests.VisualPTYTests,name).__get__(self,type(self)))
        self.addCleanup(self.cleanup_child)
        def launch():
            def session():os.setsid();fcntl.ioctl(0,termios.TIOCSCTTY,0)
            command=[sys.executable,'-B',str(CLI),'workbench','workspace','--root',str(self.store.root),'--no-color']
            self.commands.append({'argv':command,'transport':'actual Linux PTY'})
            self.proc=subprocess.Popen(command,stdin=self.slave,stdout=self.slave,stderr=self.slave,
                env=dict(os.environ,TERM='xterm-256color',PYTHONDONTWRITEBYTECODE='1'),cwd='/tmp',preexec_fn=session)
        before=self.fixture.job().status()
        launch();self.launched()
        self.key((':'+self.command('review')+'\n').encode())
        self.assertIn(b'[PROTECTED SERVICE REVIEW]',self.output)
        self.key(b'6');self.assertIn(b'[PROTECTED SERVICE EXECUTION]',self.output)
        self.key(b'5');self.assertEqual(self.fixture.job().status(),before)
        self.key((':'+self.command('cancel')+'\n').encode())
        cancelled=self.fixture.job().status()
        self.assertEqual(cancelled['status'],'cancelled_before_dispatch')
        self.assertTrue(cancelled['cancel_requested']);self.assertEqual(cancelled['dispatches'],0)
        self.assertEqual([event['kind'] for event in cancelled['events']],['prepared','cancel_requested'])
        self.key((':'+self.command('recover')+'\n').encode())
        recovered=self.fixture.job().status()
        self.assertEqual(recovered['status'],'cancelled_before_dispatch')
        self.assertEqual(recovered['dispatches'],0)
        self.assertEqual([event['kind'] for event in recovered['events']],
            ['prepared','cancel_requested','recovery_cancel_requested','recovery_no_replay'])
        self.assertEqual(recovered['events'][-1]['payload'],{'container_never_recorded':True})
        self.close_visual()
        saved=json.loads((self.store.root/'workspace-context.json').read_text())
        self.assertEqual(saved['service_navigation']['read_action'],'attach')
        self.assertEqual(saved['view_command'],self.command('attach'))
        start=len(self.output);launch();self.read_until(b'[PROTECTED SERVICE EXECUTION]',start)
        self.settle(start);self.key(b'5');self.key(b'6');self.close_visual()
        self.assertEqual(self.fixture.job().status(),recovered)
        self.assertEqual(self.fixture.fixture.calls,[])


if __name__=='__main__':unittest.main()
