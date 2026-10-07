"""Presentation fixtures only; real command and PTY acceptance stays independent."""
import io,json,shlex,tempfile,unittest
from pathlib import Path
from intune_iac.io import AppError
from intune_iac.workbench_store import WorkbenchStore
from intune_iac.workbench_tui import Workspace,ADOPTION_NAVIGATION_VERSION,CONTEXT_VERSION
TENANT='11111111-1111-4111-8111-111111111111'
OBJECT='22222222-2222-4222-8222-222222222222'
class AdoptionPresentationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=WorkbenchStore.create(self.root/'store',TENANT);self.ui=Workspace(self.store.root,stdin=io.StringIO(),stdout=io.StringIO())
        self.job=str(self.root/'adoption job');self.policy=str(self.root/"policy ' reviewed.json")
    def command(self,action):return 'adoption-'+action+' '+shlex.quote(self.job)+' '+shlex.quote(self.policy)
    def result(self,action):return {'operation_id':'adoption-test','tenant_id':TENANT,'object_ids':[OBJECT],
        'manifest_sha256':'a'*64,'manifest':{'action':'native_state_only_import','intended_writer':{'organizational_sole_writer_approval_established':False}},
        'status':'outcome_unknown','outcome':None,'dispatches':1,'verification_dispatches':0,'verification_status':'not_started',
        'cancel_requested':action in ('cancel','recover'),'adoption_job_root':self.job,'adoption_policy':self.policy,
        'evidence_class':'protected_adoption_journal','interface_action':action}
    def test_readonly_reopen_tabs_exact_domain(self):
        self.ui._send(self.command('review'));self.ui.receive(self.result('review'))
        reopened=Workspace(self.store.root,stdin=io.StringIO(),stdout=io.StringIO())
        self.assertIn(self.command('review'),list(reopened.pending));self.assertEqual(reopened._tab_command(4),self.command('review'))
        self.assertEqual(reopened._tab_command(5),self.command('attach'));self.assertIsNone(reopened.active_service)
        stored=json.loads(self.ui.context_path.read_text());self.assertEqual(stored['adoption_navigation']['schema_version'],ADOPTION_NAVIGATION_VERSION)
        self.assertNotIn('manifest_sha256',self.ui.context_path.read_text());self.assertNotIn('outcome_unknown',self.ui.context_path.read_text())
    def test_cancel_recover_resume_only_attach(self):
        for action in ('cancel','recover'):
            self.ui._send(self.command(action));self.ui.receive(self.result(action))
            reopened=Workspace(self.store.root,stdin=io.StringIO(),stdout=io.StringIO())
            self.assertIn(self.command('attach'),list(reopened.pending));self.assertFalse(any(x.startswith(('adoption-cancel','adoption-recover','adoption-run','adoption-prepare')) for x in reopened.pending))
    def test_context_cannot_switch_domain_or_restore_authority(self):
        self.ui._send(self.command('review'));self.ui.receive(self.result('review'));base=json.loads(self.ui.context_path.read_text())
        cases=[]
        for action in ('run','prepare','cancel','recover'):cases.append(dict(base,view_command=self.command(action)))
        for change in ({'read_action':'cancel'},{'job_root':'relative'},{'signature':'forged'},{'schema_version':'workbench-service-navigation/1'}):
            cases.append(dict(base,adoption_navigation=dict(base['adoption_navigation'],**change)))
        cases.append(dict(base,view_command='adoption-review /other '+shlex.quote(self.policy)))
        cases.append(dict(base,view_command='service-review '+shlex.quote(self.job)+' '+shlex.quote(self.policy)))
        cases.append(dict(base,page_command=self.command('attach')))
        for value in cases:
            with self.assertRaises(AppError):self.ui._validate_context(value)
    def test_service_and_adoption_switch_without_domain_reuse(self):
        self.ui._send(self.command('review'));self.ui.receive(self.result('review'))
        value=dict(self.result('review'),service_job_root=self.job,service_policy=self.policy,evidence_class='protected_service_journal')
        value.pop('adoption_job_root');value.pop('adoption_policy');self.ui._send('service-review '+shlex.quote(self.job)+' '+shlex.quote(self.policy));self.ui.receive(value)
        self.assertIsNone(self.ui.active_adoption);self.assertTrue(self.ui._tab_command(5).startswith('service-attach '))
        self.ui._send(self.command('attach'));self.ui.receive(self.result('attach'));self.assertIsNone(self.ui.active_service)
    def test_state_only_presentation_preserves_uncertainty(self):
        self.ui._send(self.command('attach'));self.ui.receive(self.result('attach'));text='\n'.join(self.ui._surface_summary(150))
        self.assertIn('[PROTECTED STATE-ONLY ADOPTION JOURNAL]',text);self.assertIn('outcome_unknown',text)
        self.assertIn('does not deploy Graph',text);self.assertIn('not recorded; outcome unknown',text)
        self.assertIn('First-plan dispatches: 0',text)
    def test_legacy_and_protected_help_both_retained(self):
        from intune_iac.workbench import HELP
        self.assertTrue(any(x.startswith('adoption-preview ') for x in HELP['adoption']))
        self.assertTrue(any(x.startswith('adoption-link ') for x in HELP['protected_adoption']))
    def test_history_navigation_requires_selection(self):
        self.ui.selected=OBJECT;self.ui._send('adoption-history');self.ui.receive({'operations':[]});self.assertEqual(self.ui.view_command,'adoption-history')
        value=json.loads(self.ui.context_path.read_text());value['selected']=None
        with self.assertRaises(AppError):self.ui._validate_context(value)
    def test_back_from_adoption_history_clears_selected_and_history_view(self):
        self.ui.selected=OBJECT;self.ui._send('adoption-history');self.ui.receive({'operations':[]})
        self.ui._send('back');self.ui.receive({'status':'selection_cleared'})
        stored=json.loads(self.ui.context_path.read_text());self.assertIsNone(stored['selected']);self.assertEqual(stored['view_command'],'overview')
        reopened=Workspace(self.store.root,stdin=io.StringIO(),stdout=io.StringIO());self.assertNotIn('adoption-history',list(reopened.pending))
