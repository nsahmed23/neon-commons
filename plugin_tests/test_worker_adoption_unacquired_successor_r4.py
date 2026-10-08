"""Separate /3 signatures and modeled same-authority edges; no live authority."""
import copy,json,sqlite3,types,unittest
from pathlib import Path
from unittest.mock import patch
from intune_iac import worker_adoption_reconcile as bridge
from intune_iac.io import AppError,canonical,digest
from plugin_tests import test_worker_adoption_phase_successor_r4 as phase_tests
from plugin_tests import test_worker_adoption_reconcile_r4 as old_contracts


class UnacquiredCompletionContract(unittest.TestCase):
    def setUp(self):
        phase_tests.PhaseCompletionFactsTests.setUp(self)
        self.completion.facts.update(schema_version='adoption-plan-unacquired-observation/1',
            classification='no_native_backend_dispatch_observed_execution_unknown',release_performed=False,ownership_release_authorized=False)
        observed=types.SimpleNamespace(_original=lambda selected:copy.deepcopy(self.complete),
            CLASSIFICATION='no_native_backend_dispatch_observed_execution_unknown')
        patcher=patch.object(bridge,'_unacquired_types',return_value=(observed,type('UnusedLiveObservation',(),{}),type(self.completion)))
        patcher.start();self.addCleanup(patcher.stop)
    def test_exact_modeled_observation_uses_its_own_original_fact_producer(self):
        self.assertEqual(bridge._completion(self.job,self.completion),self.completion.facts)
    def test_release_claim_or_wrong_observation_kind_rejects(self):
        for key,value in [('schema_version','released-completion'),('classification','release_observed'),('release_performed',True),('ownership_release_authorized',True)]:
            with self.subTest(key=key):
                before=copy.deepcopy(self.completion.facts);self.completion.facts[key]=value
                try:
                    with self.assertRaises(AppError):bridge._completion(self.job,self.completion)
                finally:self.completion.facts=before


class UnacquiredSignatures(unittest.TestCase):
    def setUp(self):
        old_contracts.RecoveryPlanContracts.setUp(self);self.manifest['schema_version']=bridge.UNACQUIRED_VERSION
    def signed(self,**kwargs):return old_contracts.RecoveryPlanContracts.signed(self,**kwargs)
    def test_actual_nul_new_domain_accepts_only_v3(self):
        self.assertTrue(bridge.UNACQUIRED_SIGNATURE_DOMAIN.endswith(b'\0'))
        receipt=self.signed(domain=bridge.UNACQUIRED_SIGNATURE_DOMAIN,schema_version=bridge.UNACQUIRED_APPROVAL_VERSION)
        self.assertEqual(bridge._verify(self.policy,self.manifest,receipt),receipt['payload'])
        for domain,schema in ((bridge.SIGNATURE_DOMAIN,bridge.APPROVAL_VERSION),(bridge.PHASE_SIGNATURE_DOMAIN,bridge.PHASE_APPROVAL_VERSION)):
            with self.subTest(schema=schema),self.assertRaises(AppError):bridge._verify(self.policy,self.manifest,self.signed(domain=domain,schema_version=schema))
    def test_v3_signature_cannot_approve_old_operation_or_rehydrate_json(self):
        receipt=self.signed(domain=bridge.UNACQUIRED_SIGNATURE_DOMAIN,schema_version=bridge.UNACQUIRED_APPROVAL_VERSION)
        for version in (bridge.VERSION,bridge.PHASE_VERSION):
            with self.subTest(version=version),self.assertRaises(AppError):bridge._verify(self.policy,{**self.manifest,'schema_version':version},receipt)
        with self.assertRaises(AppError):bridge._completion({}, {'classification':'no_native_backend_dispatch_observed_execution_unknown'})


class UnacquiredFixture(phase_tests.PhaseAncestorFixture):
    def setUp(self):
        super().setUp();self.original.policy=types.SimpleNamespace(root=self.root/'authority');self.original.policy.root.mkdir(mode=0o700)
        self.db.executescript('''CREATE TABLE adoption_plan_unacquired_observations(observation_id TEXT PRIMARY KEY,original_operation_id TEXT,phase_operation_id TEXT,phase_manifest_sha256 TEXT,anchor_sha256 TEXT,anchor_path TEXT);
        CREATE TABLE adoption_plan_observation_successors(successor_operation_id TEXT PRIMARY KEY,original_operation_id TEXT,successor_manifest_sha256 TEXT,prior_operation_id TEXT UNIQUE,prior_manifest_sha256 TEXT,observation_id TEXT,anchor_sha256 TEXT,prior_phase_json TEXT);''')
        self.plan('observed');self.observed_manifest,self.anchor=self.observed_edge('observed','selected')
    def observed_edge(self,child,prior):
        row=self.db.execute('SELECT original_operation_id,manifest_sha256,root,status,cancelled,dispatches,outcome,controller_pid,controller_start FROM adoption_recovery_plans WHERE operation_id=?',(prior,)).fetchone()
        facts={'operation_id':'original','phase_operation_id':prior,'phase_manifest_sha256':row[1],'phase_kind':'recovery_plan','phase_row_sha256':digest(list(row))}
        anchor={'schema_version':'adoption-plan-unacquired-anchor/1','observation_id':'observation-'+prior,
            'classification':'no_native_backend_dispatch_observed_execution_unknown','service_authority_root':str(self.original.policy.root),
            'original':facts,'initial_observation':{'modeled':True},'implementation_files':{'fixture':'a'*64}}
        path=self.root/('anchor-'+prior+'.json');path.write_bytes(canonical(anchor));path.chmod(0o600)
        self.db.execute('INSERT INTO adoption_plan_unacquired_observations VALUES (?,?,?,?,?,?)',(anchor['observation_id'],'original',prior,row[1],digest(anchor),str(path)))
        manifest={'schema_version':bridge.UNACQUIRED_VERSION,'operation_id':child,'original_operation_id':'original','original_facts':facts,
            'recovery_binding':{'resolution_kind':bridge.UNACQUIRED_KIND,'observation_id':anchor['observation_id'],'anchor_sha256':digest(anchor),
                'phase':{'kind':'recovery_plan','operation_id':prior,'manifest_sha256':row[1],'job_root':str(self.root/prior)},
                'ancestors':bridge._ancestor_chain(self.db,self.original,prior)}}
        sha=digest(manifest);(self.root/child/'manifest.json').write_bytes(canonical(manifest))
        self.db.execute('UPDATE adoption_recovery_plans SET manifest_sha256=? WHERE operation_id=?',(sha,child));self.db.execute('UPDATE consumed SET manifest_sha256=? WHERE operation_id=?',(sha,child))
        self.db.execute('INSERT INTO adoption_plan_observation_successors VALUES (?,?,?,?,?,?,?,?)',(child,'original',sha,prior,row[1],anchor['observation_id'],digest(anchor),canonical(facts).decode()))
        return manifest,path


class UnacquiredAncestors(UnacquiredFixture):
    def test_mixed_chain_preserves_release_shape_and_names_observation_explicitly(self):
        chain=bridge._ancestor_chain(self.db,self.original,'observed')
        self.assertEqual(len(chain),2);self.assertEqual(chain[0]['resolution_kind'],bridge.UNACQUIRED_KIND)
        self.assertIn('observation_row',chain[0]);self.assertNotIn('release_row',chain[0]);self.assertIn('release_row',chain[1]);self.assertNotIn('resolution_kind',chain[1])
        self.assertEqual(chain[1:],self.observed_manifest['recovery_binding']['ancestors'])
    def test_missing_or_changed_observation_and_anchor_reject(self):
        raw=self.anchor.read_bytes();self.anchor.write_bytes(b'{}')
        with self.assertRaises(AppError):bridge._ancestor_chain(self.db,self.original,'observed')
        self.anchor.write_bytes(raw);self.db.execute('UPDATE adoption_plan_unacquired_observations SET phase_operation_id=?',('foreign',))
        with self.assertRaises(AppError):bridge._ancestor_chain(self.db,self.original,'observed')
    def test_semantically_equal_reformatted_anchor_bytes_reject(self):
        self.anchor.write_bytes(self.anchor.read_bytes()+b'\n')
        with self.assertRaises(AppError):bridge._ancestor_chain(self.db,self.original,'observed')
    def test_no_release_row_can_substitute_for_observation(self):
        self.db.execute('DELETE FROM adoption_plan_unacquired_observations')
        with self.assertRaises(AppError):bridge._ancestor_chain(self.db,self.original,'observed')
    def test_cross_table_duplicate_child_and_prior_both_reject(self):
        for child,prior in [('observed','foreign'),('other-child','selected')]:
            with self.subTest(child=child):
                self.db.execute('INSERT INTO adoption_plan_successors VALUES (?,?,?,?,?,?,?,?)',(child,'original','0'*64,prior,'1'*64,'fake-release','2'*64,'{}'))
                try:
                    with self.assertRaises(AppError):bridge._ancestor_chain(self.db,self.original,'observed')
                finally:self.db.execute('DELETE FROM adoption_plan_successors WHERE successor_operation_id=?',(child,))
    def test_current_consumed_child_can_recheck_but_new_child_cannot_occupy_prior(self):
        bridge._successor_slot(self.db,self.original,self.observed_manifest,'observed')
        for current in (None,'other'):
            with self.assertRaises(AppError):bridge._successor_slot(self.db,self.original,self.observed_manifest,current)
        changed={**self.observed_manifest,'operation_id':'new-child'}
        with self.assertRaises(AppError):bridge._successor_slot(self.db,self.original,changed,None)
    def test_unconsumed_or_cancelled_before_dispatch_observation_child_never_exempts(self):
        self.db.execute('DELETE FROM consumed WHERE operation_id=?',('observed',))
        with self.assertRaises(AppError):bridge._ancestor_chain(self.db,self.original,'observed')
    def test_original_wrong_classification_or_foreign_authority_anchor_reject(self):
        anchor=json.loads(self.anchor.read_bytes());anchor['classification']='release_observed';self.anchor.write_bytes(canonical(anchor));sha=digest(anchor)
        self.db.execute('UPDATE adoption_plan_unacquired_observations SET anchor_sha256=?',(sha,))
        with self.assertRaises(AppError):bridge._observation_row(self.db,self.original,'selected',self.selected,anchor['observation_id'],sha,self.observed_manifest['original_facts'])


class UnacquiredAtomicConsumption(UnacquiredFixture):
    """Real run transaction; inert admission/runtime and host are injected."""
    def exercise(self,failure):
        self.db.executescript('CREATE TABLE approval_transcripts(operation_id TEXT PRIMARY KEY,receipt_json TEXT,receipt_sha256 TEXT,consumed_at INTEGER);CREATE TABLE revoked(issuer TEXT,key_id TEXT);CREATE TABLE ownership(scope TEXT,job TEXT);')
        self.db.execute('INSERT INTO ownership VALUES (?,?)',('scope','original'))
        self.db.execute('DELETE FROM adoption_plan_observation_successors WHERE successor_operation_id=?',('observed',))
        self.db.execute('DELETE FROM consumed WHERE operation_id=?',('observed',))
        manifest={**self.observed_manifest,'identity_binding_sha256':'identity','host_spec':{}};sha=digest(manifest)
        self.db.execute('UPDATE adoption_recovery_plans SET manifest_sha256=?,status=?,cancelled=0,dispatches=0,outcome=NULL WHERE operation_id=?',(sha,'prepared','observed'))
        if failure:self.db.execute("CREATE TRIGGER refuse_observation_edge BEFORE INSERT ON adoption_plan_observation_successors BEGIN SELECT RAISE(ABORT,'injected observation edge-record failure');END")
        self.db.commit();native=self.root/'native';native.mkdir(mode=0o700);proxy=self.root/'proxy';proxy.mkdir(mode=0o700)
        subject=object.__new__(bridge.RecoveryPlanJob);subject.root=self.root/'observed';subject.identifier='observed';subject.sha256=sha;subject.manifest=manifest;subject.original=self.original
        subject.policy=types.SimpleNamespace(connection=lambda:sqlite3.connect(self.root/'authority.sqlite3'),event=lambda *args:None)
        subject._check=lambda:None;calls=[];subject._dispatch=lambda *args:calls.append('injected-host') or {'status':'injected-no-native'}
        runtime=object.__new__(bridge.RecoveryPlanRuntime);phase=types.SimpleNamespace(identifier='selected',database_snapshot=lambda db:({},None,None))
        payload={'issuer':'fixture','key_id':'key','nonce':'new-observation-nonce'};facts={'fresh_observation':{'identity_binding_sha256':'identity'}}
        with patch.object(bridge.RecoveryPlanRuntime,'check',return_value=None),patch.object(bridge,'_completion',return_value=facts),patch.object(bridge,'_binding',return_value=manifest['recovery_binding']),patch.object(bridge,'_verify',return_value=payload),patch.object(bridge.service,'_host_spec',return_value=types.SimpleNamespace(job_root=native,broker_root=proxy)),patch.object(bridge,'_original_row',return_value=None),patch.object(bridge,'_phase_from_binding',return_value=phase),patch.object(bridge,'_held_phase',return_value=None),patch.object(bridge.service,'_scopes',return_value=['scope']),patch.object(bridge.service,'_controller_identity',return_value='fixture-start'):
            if failure:
                with self.assertRaises(sqlite3.DatabaseError):subject.run({'payload':'injected'},runtime=runtime,completion={})
            else:self.assertEqual(subject.run({'payload':'injected'},runtime=runtime,completion={})['status'],'injected-no-native')
        row=self.db.execute('SELECT status,dispatches FROM adoption_recovery_plans WHERE operation_id=?',('observed',)).fetchone()
        counts=tuple(self.db.execute('SELECT COUNT(*) FROM '+table+' WHERE '+column+'=?',('observed',)).fetchone()[0] for table,column in [('consumed','operation_id'),('approval_transcripts','operation_id'),('adoption_plan_observation_successors','successor_operation_id')])
        self.assertEqual(counts,(0,0,0) if failure else (1,1,1));self.assertEqual(row,('prepared',0) if failure else ('running',1))
        self.assertEqual(calls,[] if failure else ['injected-host']);self.assertEqual(self.db.execute('SELECT scope,job FROM ownership').fetchall(),[('scope','original')])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM adoption_plan_successors').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM adoption_plan_unacquired_observations').fetchone()[0],1)
    def test_observation_edge_and_new_approval_are_committed_before_dispatch(self):self.exercise(False)
    def test_failed_observation_edge_insert_rolls_back_approval_and_dispatch(self):self.exercise(True)
