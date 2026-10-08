"""Distinct real signatures and modeled common-SQL ancestry; no live capability."""
import copy,sqlite3,tempfile,unittest,types
from pathlib import Path
from unittest.mock import patch
from intune_iac import worker_adoption_reconcile as bridge
from intune_iac.io import AppError,canonical,digest
from plugin_tests import test_worker_adoption_reconcile_r4 as old_contracts

class PhaseSignatureTests(unittest.TestCase):
    def setUp(self):
        old_contracts.RecoveryPlanContracts.setUp(self)
        self.manifest['schema_version']=bridge.PHASE_VERSION
    def signed(self,**kwargs):return old_contracts.RecoveryPlanContracts.signed(self,**kwargs)
    def test_actual_nul_v2_independent_signature(self):
        self.assertTrue(bridge.PHASE_SIGNATURE_DOMAIN.endswith(b'\0'))
        receipt=self.signed(domain=bridge.PHASE_SIGNATURE_DOMAIN,schema_version=bridge.PHASE_APPROVAL_VERSION)
        self.assertEqual(bridge._verify(self.policy,self.manifest,receipt),receipt['payload'])
    def test_v1_and_v2_signatures_cannot_cross_domains(self):
        old=self.signed()
        with self.assertRaises(AppError):bridge._verify(self.policy,self.manifest,old)
        new=self.signed(domain=bridge.PHASE_SIGNATURE_DOMAIN,schema_version=bridge.PHASE_APPROVAL_VERSION)
        self.manifest['schema_version']=bridge.VERSION
        with self.assertRaises(AppError):bridge._verify(self.policy,self.manifest,new)
    def test_new_domain_still_binds_nonce_manifest_and_operation(self):
        for changed in ({'nonce':'nothex'},{'manifest_sha256':'0'*64},{'operation_id':'11111111-1111-4111-8111-111111111111'}):
            receipt=self.signed(domain=bridge.PHASE_SIGNATURE_DOMAIN,schema_version=bridge.PHASE_APPROVAL_VERSION,**changed)
            with self.assertRaises(AppError):bridge._verify(self.policy,self.manifest,receipt)
    def test_unknown_manifest_cannot_select_domain(self):
        with self.assertRaises(AppError):bridge._signature_contract({'schema_version':'native-adoption-recovery-plan/999'})

class PhaseAncestorFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.db=sqlite3.connect(self.root/'authority.sqlite3');self.addCleanup(self.db.close)
        self.db.executescript('''CREATE TABLE adoption_recovery_plans(operation_id TEXT PRIMARY KEY,original_operation_id TEXT,manifest_sha256 TEXT,root TEXT,status TEXT,cancelled INTEGER DEFAULT0,dispatches INTEGER,outcome TEXT,controller_pid INTEGER,controller_start TEXT);
        CREATE TABLE adoption_plan_successors(successor_operation_id TEXT PRIMARY KEY,original_operation_id TEXT,successor_manifest_sha256 TEXT,prior_operation_id TEXT UNIQUE,prior_manifest_sha256 TEXT,recovery_operation_id TEXT,recovery_manifest_sha256 TEXT,prior_phase_json TEXT);
        CREATE TABLE consumed(issuer TEXT,nonce TEXT,operation_id TEXT,manifest_sha256 TEXT);
        CREATE TABLE native_lease_recoveries(original_operation TEXT PRIMARY KEY,recovery_operation TEXT,manifest_sha256 TEXT,status TEXT,observed_sha256 TEXT);
        CREATE TABLE adoption_operations(operation_id TEXT,verification_id TEXT,verification_dispatches INTEGER,verification_status TEXT,verification_outcome TEXT);'''.replace('DEFAULT0','DEFAULT 0'))
        self.original=types.SimpleNamespace(identifier='original',sha256='a'*64,manifest={})
        self.old=self.plan('old');self.plan('selected');self.selected=self.edge('selected','old')
        self.release('selected');self.binding={'phase':{'kind':'recovery_plan','operation_id':'selected','manifest_sha256':self.selected,'job_root':str(self.root/'selected')},'recovery_operation_id':'release-selected','recovery_manifest_sha256':digest('release-selected'),'ancestors':self.chain()}
    def plan(self,name):
        root=self.root/name;root.mkdir(mode=0o700)
        manifest={'schema_version':bridge.VERSION,'operation_id':name,'original_operation_id':'original'}
        (root/'manifest.json').write_bytes(canonical(manifest));(root/'manifest.json').chmod(0o600);sha=digest(manifest)
        self.db.execute('INSERT INTO adoption_recovery_plans VALUES (?,?,?,?,?,?,?,?,?,?)',(name,'original',sha,str(root),'outcome_unknown',1,1,canonical({'status':'unknown','phase':name}).decode(),None,None));self.db.execute('INSERT INTO consumed VALUES (?,?,?,?)',('fixture',name,name,sha));return sha
    def release(self,name):self.db.execute('INSERT INTO native_lease_recoveries VALUES (?,?,?,?,?)',(name,'release-'+name,digest('release-'+name),'release_observed','1'*64))
    def edge(self,child,prior):
        row=self.db.execute('SELECT original_operation_id,manifest_sha256,root,status,cancelled,dispatches,outcome,controller_pid,controller_start FROM adoption_recovery_plans WHERE operation_id=?',(prior,)).fetchone()
        facts={'operation_id':'original','phase_operation_id':prior,'phase_manifest_sha256':row[1],'phase_kind':'recovery_plan','phase_row_sha256':digest(list(row))}
        ancestors=bridge._ancestor_chain(self.db,self.original,prior)
        self.release(prior)
        manifest={'schema_version':bridge.PHASE_VERSION,'operation_id':child,'original_operation_id':'original','original_facts':facts,
            'recovery_binding':{'phase':{'kind':'recovery_plan','operation_id':prior,'manifest_sha256':row[1],'job_root':str(self.root/prior)},'recovery_operation_id':'release-'+prior,'recovery_manifest_sha256':digest('release-'+prior),'ancestors':ancestors}}
        sha=digest(manifest);(self.root/child/'manifest.json').write_bytes(canonical(manifest));self.db.execute('UPDATE adoption_recovery_plans SET manifest_sha256=? WHERE operation_id=?',(sha,child));self.db.execute('UPDATE consumed SET manifest_sha256=? WHERE operation_id=?',(sha,child))
        self.db.execute('INSERT INTO adoption_plan_successors VALUES (?,?,?,?,?,?,?,?)',(child,'original',sha,prior,row[1],'release-'+prior,digest('release-'+prior),canonical(facts).decode()));return sha
    def chain(self):return bridge._ancestor_chain(self.db,self.original,'selected')

class PhaseAncestorTests(PhaseAncestorFixture):
    def test_one_exact_consumed_edge_preserves_old_row_and_spent_approval(self):
        before=self.db.execute('SELECT * FROM adoption_recovery_plans ORDER BY operation_id').fetchall();facts=self.chain();self.assertEqual([x['prior_operation_id'] for x in facts],['old']);self.assertEqual(before,self.db.execute('SELECT * FROM adoption_recovery_plans ORDER BY operation_id').fetchall());self.assertEqual(self.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0],2)
    def test_unconsumed_or_cancelled_before_dispatch_child_cannot_exempt(self):
        self.db.execute("DELETE FROM consumed WHERE operation_id='selected'")
        with self.assertRaises(AppError):self.chain()
        self.db.execute('INSERT INTO consumed VALUES (?,?,?,?)',('fixture','new','selected',self.selected));self.db.execute("UPDATE adoption_recovery_plans SET status='cancelled_before_dispatch',dispatches=0 WHERE operation_id='selected'")
        with self.assertRaises(AppError):self.chain()
    def test_foreign_or_orphan_child_rejected(self):
        self.db.execute("UPDATE adoption_plan_successors SET original_operation_id='foreign'")
        with self.assertRaises(AppError):self.chain()
        self.db.execute("UPDATE adoption_plan_successors SET original_operation_id='original'");self.db.execute("DELETE FROM adoption_recovery_plans WHERE operation_id='selected'")
        with self.assertRaises(AppError):self.chain()
    def test_prior_row_outcome_and_recovery_ledger_are_immutable(self):
        original=self.db.execute("SELECT outcome FROM adoption_recovery_plans WHERE operation_id='old'").fetchone()[0];self.db.execute("UPDATE adoption_recovery_plans SET outcome='{}' WHERE operation_id='old'")
        with self.assertRaises(AppError):self.chain()
        self.db.execute("UPDATE adoption_recovery_plans SET outcome=? WHERE operation_id='old'",(original,));self.db.execute("UPDATE native_lease_recoveries SET status='dispatch_started' WHERE original_operation='old'")
        with self.assertRaises(AppError):self.chain()
    def test_active_controller_or_wrong_consumed_manifest_rejected(self):
        self.db.execute("UPDATE adoption_recovery_plans SET controller_pid=123 WHERE operation_id='selected'")
        with self.assertRaises(AppError):self.chain()
        self.db.execute("UPDATE adoption_recovery_plans SET controller_pid=NULL WHERE operation_id='selected'");self.db.execute("UPDATE consumed SET manifest_sha256=? WHERE operation_id='selected'",('0'*64,))
        with self.assertRaises(AppError):self.chain()
    def test_cycle_rejected(self):
        self.db.execute("UPDATE adoption_plan_successors SET prior_operation_id='selected' WHERE successor_operation_id='selected'")
        with self.assertRaises(AppError):self.chain()
    def test_missing_consumed_v2_edge_and_changed_child_manifest_reject(self):
        self.db.execute("DELETE FROM adoption_plan_successors WHERE successor_operation_id='selected'")
        with self.assertRaises(AppError):self.chain()
        (self.root/'selected/manifest.json').write_bytes(b'{}')
        with self.assertRaises(AppError):self.chain()
    def test_closed_finite_bound_32_rejects_33_edges(self):
        self.assertEqual(bridge.MAX_PHASE_ANCESTORS,32)
        prior='chain-32';self.plan(prior)
        for number in reversed(range(32)):
            child='chain-'+str(number);self.plan(child);self.edge(child,prior);prior=child
        self.assertEqual(len(bridge._ancestor_chain(self.db,self.original,prior)),32)
        self.db.execute("DELETE FROM adoption_plan_successors WHERE successor_operation_id='selected'")
        self.edge('selected',prior)
        with self.assertRaises(AppError) as caught:self.chain()
        self.assertEqual(caught.exception.code,'adoption_recovery_phase_chain_limit')
    def test_initial_verification_ancestor_requires_exact_registered_row(self):
        self.db.execute("DELETE FROM adoption_plan_successors WHERE successor_operation_id='selected'")
        initial=('initial',1,'outcome_unknown',canonical({'status':'unknown'}).decode());self.db.execute('INSERT INTO adoption_operations VALUES (?,?,?,?,?)',('original',*initial));self.release('initial')
        facts={'operation_id':'original','phase_kind':'initial_verification','phase_operation_id':'initial','phase_manifest_sha256':self.original.sha256,'phase_row_sha256':digest(list(initial))}
        manifest={'schema_version':bridge.PHASE_VERSION,'operation_id':'selected','original_operation_id':'original','original_facts':facts,
            'recovery_binding':{'phase':{'kind':'initial_verification','operation_id':'initial','manifest_sha256':self.original.sha256,'job_root':str(self.root/'original')},'recovery_operation_id':'release-initial','recovery_manifest_sha256':digest('release-initial'),'ancestors':[]}}
        self.selected=digest(manifest);(self.root/'selected/manifest.json').write_bytes(canonical(manifest));self.db.execute("UPDATE adoption_recovery_plans SET manifest_sha256=? WHERE operation_id='selected'",(self.selected,));self.db.execute("UPDATE consumed SET manifest_sha256=? WHERE operation_id='selected'",(self.selected,))
        self.db.execute('INSERT INTO adoption_plan_successors VALUES (?,?,?,?,?,?,?,?)',('selected','original',self.selected,'initial',self.original.sha256,'release-initial',digest('release-initial'),canonical(facts).decode()))
        self.assertEqual(self.chain()[0]['prior_operation_id'],'initial');self.db.execute('UPDATE adoption_operations SET verification_dispatches=0')
        with self.assertRaises(AppError):self.chain()
    def test_only_selected_and_verified_ancestors_can_exempt_conflicts(self):
        phase=types.SimpleNamespace(identifier='selected',database_snapshot=lambda db:({},None,None))
        manifest={'original_facts':{},'recovery_binding':self.binding}
        with patch.object(bridge,'_phase_from_binding',return_value=phase),patch.object(bridge,'_held_phase',return_value=None):
            bridge._phase_transaction(self.db,self.original,manifest,phase=phase)
            self.plan('unrelated')
            with self.assertRaises(AppError):bridge._phase_transaction(self.db,self.original,manifest,phase=phase)
    def test_prepared_cancelled_successor_has_no_edge_or_ownership_transfer(self):
        self.plan('new');self.db.execute("UPDATE adoption_recovery_plans SET status='cancelled_before_dispatch',dispatches=0,cancelled=1 WHERE operation_id='new'");self.db.execute("DELETE FROM consumed WHERE operation_id='new'")
        phase=types.SimpleNamespace(identifier='selected',database_snapshot=lambda db:({},None,None));manifest={'original_facts':{},'recovery_binding':self.binding}
        with patch.object(bridge,'_phase_from_binding',return_value=phase),patch.object(bridge,'_held_phase',return_value=None):bridge._phase_transaction(self.db,self.original,manifest,phase=phase)
        self.assertIsNone(self.db.execute("SELECT 1 FROM adoption_plan_successors WHERE successor_operation_id='new'").fetchone())
    def test_registered_initial_verification_terminates_with_existing_edge_table(self):
        self.original.manifest={'verification_operation_id':'initial'}
        self.db.execute('CREATE TABLE jobs(id TEXT,manifest_sha256 TEXT,status TEXT,dispatches INTEGER,controller_pid INTEGER,controller_start TEXT)')
        self.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?)',('original',self.original.sha256,'outcome_unknown',1,None,None))
        self.db.execute('INSERT INTO consumed VALUES (?,?,?,?)',('fixture','original','original',self.original.sha256))
        self.db.execute('INSERT INTO adoption_operations VALUES (?,?,?,?,?)',('original','initial',1,'outcome_unknown','{}'))
        self.assertEqual(bridge._ancestor_chain(self.db,self.original,'initial'),[])
        with self.assertRaises(AppError):bridge._ancestor_chain(self.db,self.original,'arbitrary-absent')
        self.db.execute("DELETE FROM consumed WHERE operation_id='original'")
        with self.assertRaises(AppError):bridge._ancestor_chain(self.db,self.original,'initial')
    def test_next_child_at_32_edges_is_refused_before_consumption(self):
        prior='bounded-31';self.plan(prior)
        for number in reversed(range(31)):
            child='bounded-'+str(number);self.plan(child);self.edge(child,prior);prior=child
        self.db.execute("DELETE FROM adoption_plan_successors WHERE successor_operation_id='selected'")
        self.selected=self.edge('selected',prior);chain=self.chain();self.assertEqual(len(chain),32)
        self.db.execute("DELETE FROM adoption_recovery_plans WHERE operation_id='old'")
        binding=dict(self.binding,ancestors=chain);binding['phase']=dict(binding['phase'],manifest_sha256=self.selected)
        phase=types.SimpleNamespace(identifier='selected',database_snapshot=lambda db:({},None,None));manifest={'original_facts':{},'recovery_binding':binding}
        with patch.object(bridge,'_phase_from_binding',return_value=phase),patch.object(bridge,'_held_phase',return_value=None),self.assertRaises(AppError):bridge._phase_transaction(self.db,self.original,manifest,phase=phase)
    def test_declared_ancestor_list_cannot_be_replaced(self):
        phase=types.SimpleNamespace(identifier='selected',database_snapshot=lambda db:({},None,None));manifest={'original_facts':{},'recovery_binding':dict(self.binding,ancestors=[])}
        with patch.object(bridge,'_phase_from_binding',return_value=phase),patch.object(bridge,'_held_phase',return_value=None),self.assertRaises(AppError):bridge._phase_transaction(self.db,self.original,manifest,phase=phase)


class PhaseAtomicConsumptionTests(PhaseAncestorFixture):
    """Actual run transaction with inert admission/runtime seams injected."""
    def exercise_run(self,failure):
        self.db.executescript('CREATE TABLE approval_transcripts(operation_id TEXT PRIMARY KEY,receipt_json TEXT,receipt_sha256 TEXT,consumed_at INTEGER);CREATE TABLE revoked(issuer TEXT,key_id TEXT);CREATE TABLE ownership(scope TEXT,job TEXT);')
        self.db.execute('INSERT INTO ownership VALUES (?,?)',('scope','original'))
        if failure:self.db.execute("CREATE TRIGGER refuse_new_edge BEFORE INSERT ON adoption_plan_successors WHEN NEW.successor_operation_id='new-plan' BEGIN SELECT RAISE(ABORT,'injected edge-record failure');END")
        jobroot=self.root/'new-plan';jobroot.mkdir(mode=0o700);native=self.root/'native';native.mkdir(mode=0o700);proxy=self.root/'proxy';proxy.mkdir(mode=0o700)
        manifest={'schema_version':bridge.PHASE_VERSION,'original_facts':{},'recovery_binding':self.binding,'identity_binding_sha256':'identity','host_spec':{}}
        sha=digest(manifest);self.db.execute('INSERT INTO adoption_recovery_plans VALUES (?,?,?,?,?,?,?,?,?,?)',('new-plan','original',sha,str(jobroot),'prepared',0,0,None,None,None));self.db.commit()
        subject=object.__new__(bridge.RecoveryPlanJob);subject.root=jobroot;subject.identifier='new-plan';subject.sha256=sha;subject.manifest=manifest;subject.original=self.original
        subject.policy=types.SimpleNamespace(connection=lambda:sqlite3.connect(self.root/'authority.sqlite3'),event=lambda *args:None)
        subject._check=lambda:None;calls=[];subject._dispatch=lambda *args:calls.append('host-boundary') or {'status':'injected-no-native'}
        runtime=object.__new__(bridge.RecoveryPlanRuntime);phase=types.SimpleNamespace(identifier='selected',database_snapshot=lambda db:({},None,None))
        payload={'issuer':'fixture','key_id':'key','nonce':'new-spent-nonce'};facts={'fresh_observation':{'identity_binding_sha256':'identity'}}
        with patch.object(bridge.RecoveryPlanRuntime,'check',return_value=None),patch.object(bridge,'_completion',return_value=facts),patch.object(bridge,'_binding',return_value=self.binding),patch.object(bridge,'_verify',return_value=payload),patch.object(bridge.service,'_host_spec',return_value=types.SimpleNamespace(job_root=native,broker_root=proxy)),patch.object(bridge,'_original_row',return_value=None),patch.object(bridge,'_phase_from_binding',return_value=phase),patch.object(bridge,'_held_phase',return_value=None),patch.object(bridge.service,'_scopes',return_value=['scope']),patch.object(bridge.service,'_controller_identity',return_value='fixture-start'):
            if failure:
                with self.assertRaises(sqlite3.DatabaseError):subject.run({'payload':'injected'},runtime=runtime,completion={})
            else:self.assertEqual(subject.run({'payload':'injected'},runtime=runtime,completion={})['status'],'injected-no-native')
        row=self.db.execute("SELECT status,dispatches FROM adoption_recovery_plans WHERE operation_id='new-plan'").fetchone()
        consumed=self.db.execute("SELECT COUNT(*) FROM consumed WHERE operation_id='new-plan'").fetchone()[0]
        transcript=self.db.execute("SELECT COUNT(*) FROM approval_transcripts WHERE operation_id='new-plan'").fetchone()[0]
        edges=self.db.execute("SELECT COUNT(*) FROM adoption_plan_successors WHERE successor_operation_id='new-plan'").fetchone()[0]
        self.assertEqual((consumed,transcript,edges),(0,0,0) if failure else (1,1,1));self.assertEqual(row,('prepared',0) if failure else ('running',1));self.assertEqual(calls,[] if failure else ['host-boundary']);self.assertEqual(self.db.execute('SELECT scope,job FROM ownership').fetchall(),[('scope','original')])
    def test_edge_insert_failure_rolls_back_consumption_transcript_dispatch(self):self.exercise_run(True)
    def test_edge_and_new_approval_are_durable_before_injected_dispatch(self):self.exercise_run(False)


if __name__=='__main__':unittest.main()


class PhaseCompletionFactsTests(unittest.TestCase):
    """Modeled completion-interface checks; patched types mint no capability."""
    def setUp(self):
        class Original:
            identifier='original';sha256='a'*64
            policy=types.SimpleNamespace(database='/fixture/common.sqlite3',root=Path('/fixture/authority'))
            manifest={'profile':'native_docker_laboratory_protocol','state_contract':{'fixture':'content-only'}}
            def _check(self,**kwargs):pass
        class Completion:
            def verified(self):return self.facts
        self.job=Original();self.phase=types.SimpleNamespace(original=self.job)
        self.complete={'operation_id':'original','policy_sha256':'b'*64,'phase_operation_id':'stopped-plan',
            'broker_journal_sha256':'c'*64,'host_run_manifest_sha256':'d'*64,'host_run_receipt_sha256':'e'*64,
            'lease_id':'fixture-lease','lock':{'host':'fixture.invalid','path':'/state'},'recorded_metadata':'fixture',
            'state_contract_sha256':'f'*64,'state_write_attempts':1}
        self.completion=Completion();self.completion.context=types.SimpleNamespace(phase=self.phase)
        self.completion.facts={'service_authority_root':str(self.job.policy.root),'original':copy.deepcopy(self.complete),
            'lease_independently_unlocked':True,'fresh_observation':{'locked':False,'adoption_state_proof':{
                'classification':'approved_adoption_successor','graph_unchanged':True,
                'original_contract_sha256':digest(self.job.manifest['state_contract'])}}}
        self.reader=types.SimpleNamespace(_original=lambda selected:copy.deepcopy(self.complete))
        for patcher in (patch.object(bridge.adoption,'AdoptionJob',Original),
                        patch.object(bridge,'_phase_types',return_value=(self.reader,type('LiveFixture',(),{}),Completion))):
            patcher.start();self.addCleanup(patcher.stop)
    def test_full_phase_original_record_is_required_and_accepted(self):
        self.assertEqual(bridge._completion(self.job,self.completion),self.completion.facts)
    def test_missing_or_changed_extended_record_never_matches(self):
        for key in ('broker_journal_sha256','host_run_manifest_sha256','host_run_receipt_sha256','lease_id',
                    'lock','recorded_metadata','state_contract_sha256','state_write_attempts'):
            for altered in (None,'changed'):
                with self.subTest(key=key,mutation='missing' if altered is None else 'changed'):
                    facts=copy.deepcopy(self.complete)
                    if altered is None:del facts[key]
                    else:facts[key]=altered
                    self.completion.facts['original']=facts
                    with self.assertRaises(AppError) as caught:bridge._completion(self.job,self.completion)
                    self.assertEqual(caught.exception.code,'adoption_recovery_successor_required')
