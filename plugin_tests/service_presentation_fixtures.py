"""The hand-authored presentation fixtures of the protected service views.

They are shared by test_workbench_service_tui_r4 (ServicePresentationTests) and the rendered-surface sweep
(test_rendered_surfaces). They live here, and not in test_workbench_service_tui_r4, because that module imports
test_worker_service_r4 at its top, and that imports the pinned docker of scripts/qualification_tools: a tool these
fixtures never use, so a machine without it could not load them. Nothing here imports it.
"""
import io
from pathlib import Path
import shlex
import tempfile

from intune_iac.workbench_store import WorkbenchStore
from intune_iac.workbench_tui import Workspace

TENANT='11111111-1111-4111-8111-111111111111'
OBJECT='22222222-2222-4222-8222-222222222222'


class ServiceFixtures:
    """setUp, response and command of the service presentation tests: a mixin for a unittest.TestCase."""
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
