"""API-shaped offline examples, never evidence of a live tenant/provider run."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    source = json.loads((ROOT/'examples/supported/input/export.json').read_text())
    source['synthetic'] = False
    source['exporter'] = {'id':'intune-iac-settings-catalog-graph','version':'1.0.0'}
    source['references'] = []
    source['ownership'] = []
    policy = source['collections'][0]['pages'][0]['body']['value'][0]
    policy.update(creationSource='portal', priorityMetaData=None, templateReference=None,
                  disableEntraGroupPolicyAssignment=False)
    for a in source['collections'][2]['pages'][0]['body']['value']:
        a.update(source='direct', sourceId=None)
    context = json.loads((ROOT/'examples/context.json').read_text())
    context.update(source_is_synthetic=False, component='windows-privacy', stack='workstation-pilot')
    return source, context


class ProductionTests(unittest.TestCase):
    def run_engine(self, source=None, context=None):
        from intune_iac.engine import inspect_source, generate, verify_project
        s,c = inputs()
        source = s if source is None else source
        context = c if context is None else context
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        src = folder/'source.json'; ctx = folder/'context.json'; output = folder/'project'
        src.write_text(json.dumps(source)); ctx.write_text(json.dumps(context))
        review = inspect_source(src,ctx)
        result = generate(src,ctx,output)
        self.assertTrue(verify_project(src,ctx,output)['preservation_verified'])
        return review,result,output,src,ctx

    def test_explicit_known_capture_emits_useful_inactive_candidate(self):
        review,result,output,_,_ = self.run_engine()
        n = review['normalized']
        self.assertEqual(review['source_mode'],'plugin_graph_capture')
        self.assertTrue(n['candidate_mapping_complete'])
        self.assertFalse(n['offline_mapping_complete'])
        self.assertFalse(n['provider_qualified'])
        self.assertEqual(n['ownership'],{'status':'unknown'})
        self.assertTrue(all(r['coverage']=='unknown' for r in n['references']))
        self.assertTrue(list(output.rglob('main.tf.txt')))
        self.assertFalse(list(output.rglob('*.tf')))
        config = json.loads(next(output.rglob('configuration.json')).read_text())
        self.assertEqual(config,n['configuration'])
        self.assertEqual(config['assignments'],[
            {'type':'groupAssignmentTarget','group_id':'44444444-4444-4444-8444-444444444444','filter_type':'include','filter_id':'77777777-7777-4777-8777-777777777777'},
            {'type':'groupAssignmentTarget','group_id':'55555555-5555-4555-8555-555555555555','filter_type':'none'},
            {'type':'exclusionGroupAssignmentTarget','group_id':'66666666-6666-4666-8666-666666666666','filter_type':'none'}])
        self.assertIsNone(n['observed']['policy']['templateReference'])
        self.assertEqual(n['observed']['policy']['creationSource'],'portal')
        self.assertEqual(json.loads((output/'commands/command-cards.json').read_text())['cards'],[])
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(n['request_projection']['status'],'not_constructed')
        self.assertEqual(n['state_expectations']['status'],'unqualified')

    def test_optional_wrapper_annotations_and_returned_skip_links(self):
        source,context=inputs()
        for c in source['collections']:
            for record in c['pages'][0]['body']['value']:record.pop('@odata.type',None)
        c=source['collections'][1]
        old=copy.deepcopy(c['pages'][0])
        next_url=old['request_url']+'?$skip=0&$skiptoken=A%2BB'
        c['pages'][0]['body']={'value':[],'@odata.nextLink':next_url}
        old['request_url']=next_url;c['pages'].append(old)
        review,_,_,_,_=self.run_engine(source,context)
        self.assertTrue(review['normalized']['candidate_mapping_complete'])
        self.assertNotIn('@odata.type',review['normalized']['observed']['settings'][0])

    def test_repository_context_accepts_safe_physical_target_paths(self):
        source,context=inputs()
        for key in ('provider_source','provider_version','engine','engine_version','atmos_version'):context.pop(key)
        context.update(stack='deploy/dev',component='intune/windows',implementation='settings/catalog',
                       tenant_assurance='source_asserted',target_assurance='repository_literal_resolution_only',
                       repository_source_fingerprint='a'*64)
        review,_,output,_,_=self.run_engine(source,context)
        self.assertTrue(review['normalized']['candidate_mapping_complete'])
        self.assertTrue((output/'candidates/components/terraform/intune/windows/main.tf.txt').is_file())

    def test_complete_empty_assignments_are_retained_exactly(self):
        source,context=inputs();source['collections'][2]['pages'][0]['body']['value']=[]
        source['collections'][0]['pages'][0]['body']['value'][0]['isAssigned']=False
        review,_,_,_,_=self.run_engine(source,context)
        self.assertEqual(review['normalized']['configuration']['assignments'],[])

    def test_contradictory_collection_counts_block_candidate(self):
        for count, empty in [(2, True), (0, False), (4, False)]:
            with self.subTest(count=count, empty=empty):
                source,context=inputs()
                body=source['collections'][2]['pages'][0]['body']
                body['@odata.count']=count
                if empty:
                    body['value']=[]
                    source['collections'][0]['pages'][0]['body']['value'][0]['isAssigned']=False
                review,_,output,_,_=self.run_engine(source,context)
                self.assertFalse(review['normalized']['candidate_mapping_complete'])
                self.assertIn('collection_count_mismatch',{b['code'] for b in review['blockers']})
                self.assertFalse(list(output.rglob('main.tf.txt')))

    def test_matching_count_is_consistent_across_complete_pages(self):
        source,context=inputs()
        collection=source['collections'][2];first=collection['pages'][0]
        last=copy.deepcopy(first)
        first['body']['value'],last['body']['value']=first['body']['value'][:1],last['body']['value'][1:]
        first['body']['@odata.count']=3
        first['body']['@odata.nextLink']=first['request_url']+'?$skiptoken=after-one'
        last['request_url']=first['body']['@odata.nextLink'];last['body']['@odata.count']=3
        collection['pages'].append(last)
        review,_,_,_,_=self.run_engine(source,context)
        self.assertTrue(review['normalized']['candidate_mapping_complete'])

    def test_assignment_flag_contradiction_blocks_candidate(self):
        for assigned in [False,True]:
            source,context=inputs()
            source['collections'][0]['pages'][0]['body']['value'][0]['isAssigned']=assigned
            if assigned:source['collections'][2]['pages'][0]['body']['value']=[]
            review,_,_,_,_=self.run_engine(source,context)
            self.assertFalse(review['normalized']['candidate_mapping_complete'])
            self.assertIn('assignment_flag_mismatch',{b['code'] for b in review['blockers']})

    def test_uuid_case_does_not_evade_duplicate_identity_or_target_checks(self):
        for mode in ['target','record']:
            source,context=inputs()
            rows=source['collections'][2]['pages'][0]['body']['value']
            duplicate=copy.deepcopy(rows[0]);duplicate['id']='another-assignment-id'
            if mode=='target':
                rows[0]['target']['groupId']='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
                duplicate['target']['groupId']='AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'
                expected='duplicate_assignment_target'
            else:
                rows[0]['id']='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
                duplicate['id']='AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'
                duplicate['target']['groupId']='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
                expected='duplicate_or_missing_source_identity'
            source['collections'][2]['pages'][0]['body']['value']=[rows[0],duplicate]
            review,_,_,_,_=self.run_engine(source,context)
            self.assertFalse(review['normalized']['candidate_mapping_complete'])
            self.assertIn(expected,{b['code'] for b in review['blockers']})

    def test_non_null_priority_is_observed_but_unmapped(self):
        source,context=inputs()
        source['collections'][0]['pages'][0]['body']['value'][0]['priorityMetaData']={'priority':3}
        review,_,output,_,_=self.run_engine(source,context)
        self.assertEqual(review['normalized']['observed']['policy']['priorityMetaData'],{'priority':3})
        self.assertIn('policy_behavior_not_mapped',{b['code'] for b in review['blockers']})
        self.assertFalse(list(output.rglob('main.tf.txt')))

    def test_opaque_setting_identity_is_retained_and_never_renumbered(self):
        source,context = inputs()
        source['collections'][1]['pages'][0]['body']['value'][0]['id']='f9179d22-1061-43a0-bf14-7cf20aabb991'
        review,_,output,_,_ = self.run_engine(source,context)
        n=review['normalized']
        self.assertEqual(n['observed']['settings'][0]['id'],'f9179d22-1061-43a0-bf14-7cf20aabb991')
        self.assertIsNone(n['configuration'])
        self.assertFalse(n['candidate_mapping_complete'])
        self.assertIn('unsupported_setting_configuration_id',{b['code'] for b in n['blockers']})
        self.assertFalse(list(output.rglob('main.tf.txt')))

    def test_missing_denied_and_incomplete_assignments_never_become_empty(self):
        for mode in ['missing','denied','continuation']:
            with self.subTest(mode=mode):
                source,context=inputs()
                if mode=='missing': source['collections'].pop()
                elif mode=='denied':
                    a=source['collections'][2]; a.update(coverage='access_denied',reason='access_denied')
                    a['pages'][0].update(http_status=403,body={'error':{'message':'PRIVATE-CANARY'}})
                else: source['collections'][2]['pages'][0]['body']['@odata.nextLink']=source['collections'][2]['pages'][0]['request_url']+'?$skip=3'
                review,_,output,_,_=self.run_engine(source,context)
                self.assertFalse(review['normalized']['candidate_mapping_complete'])
                self.assertIsNone(review['normalized']['configuration'])
                self.assertNotIn('PRIVATE-CANARY',''.join(p.read_text() for p in output.rglob('*') if p.is_file()))

    def test_policy_set_assignments_are_not_flattened(self):
        source,context=inputs()
        source['collections'][2]['pages'][0]['body']['value'][0].update(source='policySets',sourceId='SECRET-CANARY')
        review,_,output,_,_=self.run_engine(source,context)
        self.assertIn('assignment_source_not_direct',{b['code'] for b in review['blockers']})
        self.assertFalse(review['normalized']['candidate_mapping_complete'])
        self.assertNotIn('SECRET-CANARY',''.join(p.read_text() for p in output.rglob('*') if p.is_file()))

    def test_unknown_nested_fields_and_values_remain_opaque(self):
        for where in ['policy','setting','assignment','body']:
            source,context=inputs()
            index={'policy':0,'setting':1,'assignment':2,'body':1}[where]
            body=source['collections'][index]['pages'][0]['body']
            target=body if where=='body' else body['value'][0]
            target['PRIVATE-CANARY-KEY']={'value':'PRIVATE-CANARY-VALUE'}
            review,_,output,_,_=self.run_engine(source,context)
            self.assertFalse(review['normalized']['candidate_mapping_complete'])
            self.assertNotIn('PRIVATE-CANARY',''.join(p.read_text() for p in output.rglob('*') if p.is_file()))

    def test_oracle_detects_changed_config_observation_identity_and_accounting(self):
        from intune_iac.production_oracle import compare
        review,_,output,src,ctx=self.run_engine()
        context=json.loads(ctx.read_text()); n=review['normalized']
        for mutate in [lambda v: v['configuration']['assignments'].clear(),
                       lambda v: v['observed']['settings'][0].update(id='1'),
                       lambda v: v['configuration']['settings']['settings'][0].update(id='1'),
                       lambda v: v['coverage'][0].update(complete=False),
                       lambda v: v['field_accounting'].pop(),
                       lambda v: v.update(provider_qualified=True)]:
            changed=copy.deepcopy(n); mutate(changed)
            self.assertTrue(compare(src.read_bytes(),changed,context=context))
        files={p.relative_to(output).as_posix():p.read_text() for p in output.rglob('*') if p.is_file() and p.name!='generated-files.json'}
        path=next(p for p in files if p.endswith('configuration.json'))
        altered=json.loads(files[path]); altered['assignments']=[]; files[path]=json.dumps(altered)
        self.assertTrue(compare(src.read_bytes(),n,context=context,files=files))

    def test_self_consistent_manifest_cannot_authorize_modified_candidate(self):
        from intune_iac.engine import verify_project
        from intune_iac.io import AppError
        _,_,output,src,ctx=self.run_engine()
        path=next(output.rglob('main.tf.txt')); path.write_text(path.read_text().replace('prevent_destroy = true','prevent_destroy = false'))
        manifest=json.loads((output/'generated-files.json').read_text())
        manifest['files'][path.relative_to(output).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
        (output/'generated-files.json').write_text(json.dumps(manifest))
        with self.assertRaises(AppError): verify_project(src,ctx,output)

    def test_changed_repository_context_invalidates_existing_candidate(self):
        from intune_iac.engine import verify_project
        from intune_iac.io import AppError
        _,_,output,src,ctx=self.run_engine()
        context=json.loads(ctx.read_text());context['repository_source_fingerprint']='a'*64
        ctx.write_text(json.dumps(context))
        with self.assertRaises(AppError):verify_project(src,ctx,output)

    def test_invalid_nested_field_types_are_safe_blockers(self):
        for value in ([], {}, True, 2):
            source,context=inputs()
            source['collections'][2]['pages'][0]['body']['value'][0]['sourceId']=value
            review,_,output,_,_=self.run_engine(source,context)
            self.assertFalse(review['normalized']['candidate_mapping_complete'])
            self.assertFalse(list(output.rglob('main.tf.txt')))

    def test_target_labels_are_validated_as_literals(self):
        from intune_iac.engine import inspect_source
        from intune_iac.io import AppError
        for value in ['../escape','${SECRET}','folder/../name','', 'name\ncanary']:
            source,context=inputs(); context['component']=value
            with self.assertRaises(AppError): self.run_engine(source,context)


if __name__=='__main__': unittest.main()
