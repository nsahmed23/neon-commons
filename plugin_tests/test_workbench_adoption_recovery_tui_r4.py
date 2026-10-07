"""New Plan-only UI state is navigation, never an execution capability."""
import io,json,shlex,tempfile,unittest
from pathlib import Path
from intune_iac.io import AppError
from intune_iac.workbench_store import WorkbenchStore
from intune_iac.workbench_tui import Workspace,ADOPTION_PLAN_NAVIGATION_VERSION
TENANT='11111111-1111-4111-8111-111111111111';OBJECT='22222222-2222-4222-8222-222222222222'
class RecoveryPlanPresentation(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.store=WorkbenchStore.create(self.root/'store',TENANT)
        self.ui=Workspace(self.store.root,stdin=io.StringIO(),stdout=io.StringIO());self.ui.selected=OBJECT
        self.job=str(self.root/'recovery plan');self.policy=str(self.root/'policy.json')
    def command(self,action):return 'adoption-plan-'+action+' '+shlex.quote(self.job)+' '+shlex.quote(self.policy)
    def result(self,action):return {'operation_id':'new-plan','original_operation_id':'old-import','manifest_sha256':'a'*64,
        'status':'outcome_unknown','cancel_requested':False,'dispatches':1,'adoption_plan_job_root':self.job,'adoption_plan_policy':self.policy,
        'evidence_class':'protected_adoption_recovery_plan_journal','interface_action':action,'original':{'status':'outcome_unknown','outcome':{'dispatches':1}},
        'manifest':{'action':'native_first_plan_only','original_operation_id':'old-import'}}
    def test_plan_review_tabs_and_reopen_preserve_exact_domain(self):
        self.ui._send(self.command('review'));self.ui.receive(self.result('review'));reopened=Workspace(self.store.root,stdin=io.StringIO(),stdout=io.StringIO())
        self.assertIn(self.command('review'),list(reopened.pending));self.assertEqual(reopened._tab_command(4),self.command('review'));self.assertEqual(reopened._tab_command(5),self.command('attach'))
        context=json.loads(self.ui.context_path.read_text());self.assertEqual(context['adoption_plan_navigation']['schema_version'],ADOPTION_PLAN_NAVIGATION_VERSION)
        self.assertIsNone(context['service_navigation']);self.assertIsNone(context['adoption_navigation']);self.assertNotIn('outcome',self.ui.context_path.read_text())
    def test_cancel_recover_reopen_only_reads(self):
        for action in ('cancel','recover'):
            self.ui._send(self.command(action));self.ui.receive(self.result(action));reopened=Workspace(self.store.root,stdin=io.StringIO(),stdout=io.StringIO())
            self.assertIn(self.command('attach'),list(reopened.pending));self.assertFalse(any(x.startswith(('adoption-plan-cancel','adoption-plan-recover')) for x in reopened.pending))
    def test_cross_domain_changed_path_and_mutation_context_rejected(self):
        self.ui._send(self.command('review'));self.ui.receive(self.result('review'));base=json.loads(self.ui.context_path.read_text())
        for command in (self.command('run'),self.command('cancel'),self.command('recover'),'service-review '+shlex.quote(self.job)+' '+shlex.quote(self.policy),'adoption-review '+shlex.quote(self.job)+' '+shlex.quote(self.policy),'adoption-plan-review /wrong '+shlex.quote(self.policy)):
            with self.assertRaises(AppError):self.ui._validate_context(dict(base,view_command=command))
    def test_unknown_original_and_planonly_restriction_displayed(self):
        self.ui._send(self.command('attach'));self.ui.receive(self.result('attach'));text='\n'.join(self.ui._surface_summary(160))
        self.assertIn('[ADOPTION RECOVERY PLAN JOURNAL]',text);self.assertIn('Original status: outcome_unknown',text);self.assertIn('plan only',text);self.assertIn('no import or apply is replayed',text)
    def test_new_selection_discards_prior_plan_context(self):
        self.ui._send(self.command('review'));self.ui.receive(self.result('review'));self.ui._send('select 33333333-3333-4333-8333-333333333333');self.ui.receive({'object_id':'33333333-3333-4333-8333-333333333333'})
        self.assertIsNone(self.ui.active_adoption_plan)
