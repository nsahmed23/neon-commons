"""Actual shared CLI/terminal signed-evidence views; no native execution claim."""
import copy
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from intune_iac import worker_evidence as contract,worker_evidence_posix as host,workbench,workbench_evidence_views as views
from intune_iac.io import AppError,digest
from intune_iac.workbench_store import WorkbenchStore
ROOT=Path(contract.__file__).parents[1]
spec=importlib.util.spec_from_file_location('evidence_fixture',ROOT/'plugin_tests/test_worker_evidence_r4.py');fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.EvidenceTests.setUpClass();cls.f=fixture.EvidenceTests;cls.evidence=cls.f.root/'navigation-evidence';cls.evidence.mkdir(mode=0o700)
        host.ingest(cls.evidence,cls.f.envelope,cls.f.req,cls.f.policy,cls.f.verifier)
    @classmethod
    def tearDownClass(cls):fixture.EvidenceTests.tearDownClass()
    def cli(self,*args,ok=True):
        value=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/intune-iac.py'),'workbench',*map(str,args)],capture_output=True,text=True,timeout=20)
        if ok:self.assertEqual(value.returncode,0,value.stderr+value.stdout)
        else:self.assertNotEqual(value.returncode,0)
        return json.loads(value.stdout if value.returncode==0 else value.stderr)
    def link(self,store=None):
        f=self.f;store=store or f.store
        return self.cli('evidence-link','--root',store.root,'--object',f.req['object_id'],'--evidence-store',self.evidence,'--request-sha256',digest(f.req),'--trust',f.policy_path,'--verifier',f.verifier_path,'--scratch',f.scratch)
    def test_actual_cli_link_and_four_views_use_reverified_capture(self):
        row=self.link();result=self.cli('views','--root',self.f.store.root,'--object',self.f.req['object_id'])
        self.assertEqual(result['deployment']['baseline_kind'],'verified_signed_worker_deployment');self.assertEqual(result['deployment']['proof']['desired']['description'],'Reviewed correction')
        self.assertEqual(result['comparisons']['observed_vs_deployment']['status'],'equal');self.assertEqual(result['proposed']['saved_plan_sha256'],'b'*64)
        self.assertFalse(row['data']['baseline_admissible']);self.assertFalse(result['proposed']['execution_authorized'])
    def test_actual_terminal_same_commands_and_persistent_history(self):
        f=self.f;commands=iter(['select '+f.req['object_id'],'evidence-link '+' '.join(shlex.quote(str(v)) for v in (self.evidence,digest(f.req),f.policy_path,f.verifier_path,f.scratch)),'evidence-history','views','quit']);out=[]
        result=workbench.run_terminal(str(f.store.root),input_fn=lambda _:next(commands),result_fn=out.append)
        self.assertEqual(result['status'],'closed');history=next(v for v in out if v.get('schema_version')=='workbench-worker-evidence-history/1');self.assertTrue(history['entries']);self.assertEqual(history['entries'][0]['target']['object_id'],f.req['object_id'])
    def test_expired_is_verified_history_never_current_baseline(self):
        self.link();f=self.f
        with patch.object(host.time,'time',return_value=f.statement['expires_at']+1):
            result=views.history(f.store,f.req['object_id']);entry=result['entries'][0]
            self.assertEqual(entry['status'],'historical');self.assertEqual(entry['journal_status'],'unknown');self.assertTrue(entry['evidence']['historical_only']);self.assertFalse(entry['evidence']['baseline_admissible'])
            self.assertEqual(entry['evidence']['historical_snapshot_status'],'service_state_converged')
            from intune_iac.workbench_views import views as four_views
            display=four_views(f.store,f.req['object_id']);self.assertEqual(display['deployment']['status'],'unknown')
    def test_historical_mode_still_rejects_signature_and_current_revocation(self):
        f=self.f;bad=copy.deepcopy(f.envelope);bad['signature']='A'*88
        with self.assertRaises(AppError):contract.verify_envelope(bad,f.req,f.policy,f.verifier,now=f.statement['expires_at']+1,historical=True)
        policy=copy.deepcopy(f.policy);policy['revoked']=[{'issuer':'lab-export','key_id':'publisher','purpose':'publisher'}]
        with self.assertRaises(AppError):contract.verify_envelope(f.envelope,f.req,policy,f.verifier,now=f.statement['expires_at']+1,historical=True)
    def test_wrong_store_tenant_and_copied_claim_cannot_link(self):
        wrong=WorkbenchStore.create(self.f.root/'wrong-evidence-tenant','11111111-1111-4111-8111-111111111111')
        self.link(wrong) if wrong.tenant_id==self.f.req['tenant_id'] else self.cli('evidence-link','--root',wrong.root,'--object',self.f.req['object_id'],'--evidence-store',self.evidence,'--request-sha256',digest(self.f.req),'--trust',self.f.policy_path,'--verifier',self.f.verifier_path,'--scratch',self.f.scratch,ok=False)
        self.assertEqual(wrong.artifacts(kind='deployment_receipt'),[])
    def test_stored_success_flag_does_not_replace_bundle_bytes(self):
        self.link();f=self.f
        with __import__('sqlite3').connect(self.evidence/'evidence.sqlite3') as db:name=db.execute('SELECT attempt FROM received').fetchone()[0]
        path=self.evidence/name/'envelope.json';before=path.read_bytes();path.write_bytes(before+b' ')
        try:
            result=self.cli('views','--root',f.store.root,'--object',f.req['object_id']);self.assertEqual(result['deployment']['status'],'unknown')
            history=self.cli('evidence-history','--root',f.store.root,'--object',f.req['object_id']);self.assertTrue(all(v['status']=='unavailable' for v in history['entries']))
        finally:path.write_bytes(before)

    def test_tui_restores_only_readonly_evidence_history(self):
        import io
        from intune_iac.workbench_tui import Workspace,CONTEXT_VERSION
        f=self.f;path=f.store.root/'workspace-context.json'
        value={'schema_version':CONTEXT_VERSION,'tenant_id':f.store.tenant_id,'selected':f.req['object_id'],
            'tab':3,'view_command':'evidence-history','page_command':'overview 10 0'}
        path.write_text(json.dumps(value));path.chmod(0o600)
        ui=Workspace(f.store.root,stdin=io.StringIO(),stdout=io.StringIO());self.assertIn('evidence-history',ui.pending)
        for command in ('evidence-link /tmp/store '+'0'*64+' /tmp/trust /tmp/pin /tmp/scratch','ingest /tmp/input','evidence-history unexpected'):
            bad=dict(value,view_command=command)
            with self.assertRaises(AppError):ui._validate_context(bad)
        path.unlink()
    def test_native_workspace_admits_only_explicit_evidence_read_and_link_routes(self):
        from intune_iac.windows_workspace_binding import require_command
        require_command('evidence-history');require_command('evidence-link')
        for command in ('service-run','evidence-ingest','execute'):
            with self.assertRaises(AppError):require_command(command)
