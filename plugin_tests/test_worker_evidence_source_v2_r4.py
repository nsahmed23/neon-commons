"""Signed v2 inspection contracts; modeled journal, no native v2 dispatch claim."""
import copy
import importlib.util
from pathlib import Path
import time
import unittest
from intune_iac import worker_evidence as subject,worker_evidence_posix as host
from intune_iac.io import AppError,digest,canonical
STAGE=Path(subject.__file__).parents[1]
spec=importlib.util.spec_from_file_location('v2_evidence_fixture',STAGE/'plugin_tests/test_worker_evidence_r4.py');fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

class SourceV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.EvidenceTests.setUpClass();cls.f=fixture.EvidenceTests
    @classmethod
    def tearDownClass(cls):fixture.EvidenceTests.tearDownClass()
    def build(self,change=None):
        f=self.f;manifest=copy.deepcopy(f.snap['manifest']);manifest['schema_version']='worker-service-operation/2';manifest['profile']='native_docker_laboratory_protocol';context=manifest['run_context']
        provider={'object_id':manifest['object_ids'][0],'provider_identity':{'tenant_id':manifest['tenant_id']},'backend':{'state_blob':'https://synthetic.invalid/selected.tfstate'},
            'source_revision':context['source_revision'],'source_sha256':context['source_sha256'],'effective_input_sha256':context['effective_inputs_sha256'],'lockfile_sha256':context['provider_lock_sha256']}
        manifest['provider_binding']=provider;manifest['backend_scope_sha256']=digest(provider['backend'])
        facts={'schema_version':'worker-source-authoring-binding/1','local_scope':{'repository':'/signed/historical/literal repository','stack':context['stack'],'component':context['component'],'backend':provider['backend']['state_blob']},
            'logical_repository':context['repository'],'repository_association':'explicit_operation_manifest_declaration','local_root_identity':[{'path':'/signed/historical','device':1,'inode':2}],
            'tenant_id':manifest['tenant_id'],'object_id':manifest['object_ids'][0],'resource_address':'microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json.selected',
            'intent_artifact_id':'1'*64,'intent_data_sha256':'2'*64,'source_revision':context['source_revision'],'revision_evidence':{'literal_fixture':'not a fresh local Git check'},
            'git_storage_binding':{'schema_version':'worker-source-git-storage/1','files':[],'directories':[],'literal_fixture':'not a native execution capability'},'resolved_inputs_sha256':context['effective_inputs_sha256'],
            'materialized_configuration_sha256':context['source_sha256'],'materialized_source_manifest':{'literal-source.json':context['source_sha256']},
            'provider_binding_sha256':digest(provider),'provider_lock_sha256':context['provider_lock_sha256'],'authored_component_sha256':'3'*64,
            'management_mapping_status':'unsupported','source_evidence_class':'pinned_local_git_and_literal_materialization','remote_origin_authenticated':False,'commit_actor_authenticated':False,
            'execution_authorized':False,'platform_qualified':False,'limitations':['Hand-authored parser fixture retains signed claims; no source origin or controller dispatch established.']}
        manifest['source_authoring_binding']=facts
        if change:change(manifest)
        policy=copy.deepcopy(f.policy)
        for role in ('publishers','approvers'):
            for row in policy[role]:row['profiles']=['native_docker_laboratory_protocol']
        request=subject.make_request(manifest,policy,'e'*32);snapshot=copy.deepcopy(f.snap);snapshot['manifest']=manifest;now=int(time.time());snapshot['read_at']=now
        receipt=f.f.fixture.receipt(manifest_sha256=digest(manifest));snapshot['approval']={'receipt':receipt,'receipt_sha256':digest(receipt),'consumed_at':now}
        snapshot['consumed'].update(manifest_sha256=digest(manifest),nonce=receipt['payload']['nonce'])
        snapshot['job']['outcome']['independent_readback']['manifest_sha256']=digest(manifest)
        for event in snapshot['events']:
            event['created_at']=now
            if event['kind'] in ('prepared','dispatch_consumed'):event['payload']['manifest_sha256']=digest(manifest)
            if event['kind']=='independent_state_reconciled':event['payload']=copy.deepcopy(snapshot['job']['outcome'])
        snapshot['journal']['events_sha256']=digest(snapshot['events'])
        statement=copy.deepcopy(f.statement);statement.update(request_sha256=digest(request),request_nonce=request['nonce'],snapshot=snapshot,issued_at=now,expires_at=now+900)
        return f.sign(statement),request,policy
    def test_signed_v2_keeps_complete_source_binding_without_authority(self):
        envelope,request,policy=self.build();result=subject.verify_envelope(envelope,request,policy,self.f.verifier,now=int(time.time())).result()
        self.assertEqual(result['source_authoring_binding'],envelope['payload']['snapshot']['manifest']['source_authoring_binding']);self.assertEqual(result['source_authoring_binding']['management_mapping_status'],'unsupported')
        self.assertFalse(result['execution_authorized']);self.assertFalse(result['source_authoring_binding']['remote_origin_authenticated']);self.assertIn('no_capability',result['source_authoring_assurance'])
    def test_actual_cli_v2_ingest_reopen_preserves_binding_and_raw_signature(self):
        envelope,request,policy=self.build();root=self.f.root/'v2-actual-cli';root.mkdir(mode=0o700);store=root/'received';store.mkdir(mode=0o700)
        for name,value in [('envelope',envelope),('request',request),('trust',policy)]:host.write_new(root/(name+'.json'),value)
        auth=['--trust',root/'trust.json','--verifier',self.f.verifier_path,'--scratch',self.f.scratch]
        instance=self.f('test_actual_cli_signed_prepare_assemble_ingest_reopen')
        first=instance.cli('ingest',*auth,'--envelope',root/'envelope.json','--request',root/'request.json','--evidence-store',store)
        reopened=instance.cli('reopen',*auth,'--request-sha256',digest(request),'--evidence-store',store)
        self.assertEqual(first['bundle_sha256'],reopened['bundle_sha256']);self.assertEqual(reopened['review']['manifest']['schema_version'],'worker-service-operation/2')
    def test_separately_signed_wrong_identity_hash_authority_and_unknown_fields_rejected(self):
        changes=[lambda m:m['source_authoring_binding'].update(remote_origin_authenticated=True),lambda m:m['source_authoring_binding'].update(resolved_inputs_sha256='0'*64),
            lambda m:m['source_authoring_binding']['local_scope'].update(component='wrong'),lambda m:m['source_authoring_binding'].update(unknown='retained but unsupported'),
            lambda m:m['source_authoring_binding'].update(provider_binding_sha256='0'*64),lambda m:m.update(provider_binding={'backend':[]})]
        for change in changes:
            envelope,request,policy=self.build(change)
            with self.subTest(change=change),self.assertRaises(AppError):subject.verify_envelope(envelope,request,policy,self.f.verifier,now=int(time.time()))
    def test_v2_manifest_cannot_be_relabelled_v1_or_drop_source_binding(self):
        envelope,request,policy=self.build()
        for edit in (lambda m:m.update(schema_version='worker-service-operation/1'),lambda m:m.pop('source_authoring_binding')):
            candidate=copy.deepcopy(envelope);edit(candidate['payload']['snapshot']['manifest'])
            with self.assertRaises(AppError):subject.verify_envelope(candidate,request,policy,self.f.verifier,now=int(time.time()))

    def test_current_decimal_uint64_identity_preserves_large_native_inode(self):
        def edit(m):
            f=m['source_authoring_binding'];f['schema_version']='worker-source-authoring-binding/2';f['git_storage_binding']['schema_version']='worker-source-git-storage/2';f['local_root_identity']=[{'path':'/workspace','device':'99','inode':'9223372036854775909'}]
        envelope,request,policy=self.build(edit);result=subject.verify_envelope(envelope,request,policy,self.f.verifier,now=int(time.time())).result()
        self.assertEqual(result['source_authoring_binding']['local_root_identity'][0]['inode'],'9223372036854775909');self.assertFalse(result['execution_authorized'])
    def test_decimal_identity_does_not_widen_unknown_schema_or_numeric_rules(self):
        for value in ('01','-1','18446744073709551616',False,1):
            def edit(m):
                f=m['source_authoring_binding'];f['schema_version']='worker-source-authoring-binding/2';f['git_storage_binding']['schema_version']='worker-source-git-storage/2';f['local_root_identity']=[{'path':'/literal','device':'1','inode':value}]
            envelope,request,policy=self.build(edit)
            with self.subTest(value=value),self.assertRaises(AppError):subject.verify_envelope(envelope,request,policy,self.f.verifier,now=int(time.time()))
