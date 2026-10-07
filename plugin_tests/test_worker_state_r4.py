"""Independent captured observations complete only approved computed state fields."""
import copy
import time
import unittest
from unittest.mock import patch

from intune_iac.io import AppError, canonical, digest, parse_json
from intune_iac import worker_state as ws
from plugin_tests import test_worker_precondition_r4 as fixtures


class WorkerStateTests(unittest.TestCase):
    setUp = fixtures.WorkerPreconditionTests.setUp
    capability = fixtures.WorkerPreconditionTests.capability
    check = fixtures.WorkerPreconditionTests.check
    assert_code = fixtures.WorkerPreconditionTests.assert_code

    def contract(self, *, mutate_plan=None, mutate_baseline=None, mutate_capture=None, capture_data=None):
        gate, transport, kwargs = capture_data or self.capability(change_initial=mutate_capture)
        oid = gate.binding()['object_id']; name = 'policy'; address = ws.RESOURCE + '.' + name
        attrs = {'id': oid, 'description': 'before', 'settings_count': 1, 'last_modified_date_time': '2026-01-01T00:00:00Z'}
        after = {'id': oid, 'description': 'Reviewed correction'}
        baseline = {'version': 4, 'terraform_version': '1.13.1', 'serial': 2,
            'lineage': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', 'outputs': {}, 'check_results': None,
            'resources': [{'mode':'managed','type':ws.RESOURCE,'name':name,'provider':'provider["'+ws.PROVIDER+'"]',
                'instances':[{'schema_version':0,'identity_schema_version':0,'identity':{'id':oid},
                              'attributes':attrs,'sensitive_attributes':[],'private':'cHJpdmF0ZQ=='}]}]}
        change = {'address':address,'mode':'managed','type':ws.RESOURCE,'name':name,'provider_name':ws.PROVIDER,
            'change':{'actions':['update'],'before':copy.deepcopy(attrs),'after':copy.deepcopy(after),
                'before_identity':{'id':oid},'after_identity':{'id':oid},
                'after_unknown':{'settings_count':True,'last_modified_date_time':True}}}
        planned = {'address':address,'schema_version':0,'identity_schema_version':0,'identity':{'id':oid},'values':copy.deepcopy(after)}
        plan = {'format_version':'1.2','terraform_version':'1.13.1','errored':False,'resource_changes':[change],
            'planned_values':{'root_module':{'resources':[planned]}},'checks':[
                {'address':{'kind':'var','name':'stage','to_display':'var.stage'},'status':'pass',
                 'instances':[{'address':{'to_display':'var.stage'},'status':'pass'}]}]}
        if mutate_plan: mutate_plan(plan)
        if mutate_baseline: mutate_baseline(baseline)
        contract = ws.ComputedNativeStateWriteContract(baseline_raw=canonical(baseline),plan_json_raw=canonical(plan),
            saved_plan_sha256='b'*64,execution_binding_sha256='a'*64,preimage=kwargs['preimage'],precondition=gate)
        return contract, gate, transport, kwargs, baseline, plan

    def complete(self, gate, kwargs, baseline, plan):
        self.check(gate,kwargs); self.check(gate,kwargs,'assignments'); completion=gate.completion()
        batch,_=completion.verified()['capture'].verified();raw=batch['source']['raw_observed']
        result=copy.deepcopy(baseline);result['serial']+=1
        result['resources'][0]['instances'][0]['attributes']={**plan['resource_changes'][0]['change']['after'],
            'settings_count':raw['policy']['settingCount'],'last_modified_date_time':raw['policy']['lastModifiedDateTime']}
        result['check_results']=[{'object_kind':'var','config_addr':'var.stage','status':'pass',
            'objects':[{'object_addr':'var.stage','status':'pass'}]}]
        return completion,result

    def test_complete_matches_independent_reader_fields_and_preserves_native_metadata(self):
        contract,gate,transport,kwargs,before,plan=self.contract();completion,candidate=self.complete(gate,kwargs,before,plan)
        evidence=contract.admit(canonical(candidate),completion=completion)
        self.assertEqual(evidence['body_sha256'],digest(candidate));self.assertFalse(evidence['execution_authorized'])
        self.assertEqual(len(transport.requests),22)
        self.assertEqual(candidate['resources'][0]['instances'][0]['private'],'cHJpdmF0ZQ==')
        self.assertEqual(contract.binding()['precondition_binding_sha256'],digest(gate.binding()))

    def test_computed_values_cannot_be_arbitrary_typed_values(self):
        contract,gate,_,kwargs,before,plan=self.contract();completion,candidate=self.complete(gate,kwargs,before,plan)
        for field,value in [('settings_count',2),('last_modified_date_time','2026-10-07T00:00:00Z'),('description','unapproved')]:
            changed=copy.deepcopy(candidate);changed['resources'][0]['instances'][0]['attributes'][field]=value
            self.assert_code('worker_state_candidate_mismatch',lambda:contract.admit(canonical(changed),completion=completion))

    def test_unknown_third_field_and_create_are_rejected(self):
        for mutate in [lambda p:p['resource_changes'][0]['change']['after_unknown'].update(description=True),
                       lambda p:p['resource_changes'][0]['change'].update(actions=['create'])]:
            with self.subTest(mutation=mutate):
                # Each call owns fresh captures and evidence directories.
                self.setUp()
                self.assert_code('worker_state_unknown_values_unsupported',lambda:self.contract(mutate_plan=mutate))

    def test_lineage_serial_identity_private_outputs_and_checks_cannot_change(self):
        contract,gate,_,kwargs,before,plan=self.contract();completion,candidate=self.complete(gate,kwargs,before,plan)
        edits=[lambda c:c.update(lineage='bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee'),lambda c:c.update(serial=100),
            lambda c:c.update(outputs={'secret':{'value':'token'}}),lambda c:c.update(check_results=None),
            lambda c:c['resources'][0]['instances'][0].update(private='ZXhmaWw='),
            lambda c:c['resources'][0]['instances'][0].update(identity={'id':'foreign'})]
        for edit in edits:
            changed=copy.deepcopy(candidate);edit(changed)
            self.assert_code('worker_state_candidate_mismatch',lambda:contract.admit(canonical(changed),completion=completion))

    def test_unsealed_completion_and_raw_capture_do_not_establish_desired_state(self):
        contract,gate,_,kwargs,before,plan=self.contract();completion,candidate=self.complete(gate,kwargs,before,plan)
        for fake in [completion.verified(),completion.verified()['capture'],{'verified':True},lambda:True]:
            self.assert_code('worker_state_completed_capture_invalid',lambda:contract.admit(canonical(candidate),completion=fake))

    def test_wrong_plan_baseline_and_unknown_check_are_rejected(self):
        self.assert_code('worker_state_unknown_values_unsupported',lambda:self.contract(
            mutate_plan=lambda p:p['resource_changes'][0]['change']['before'].update(description='not baseline')))

    def test_failed_variable_check_cannot_be_stored_as_passing(self):
        self.assert_code('worker_state_check_unsupported',lambda:self.contract(
            mutate_plan=lambda p:p['checks'][0].update(status='fail')))

    def test_closed_reader_and_forked_contract_cannot_admit(self):
        contract,gate,_,kwargs,before,plan=self.contract();completion,candidate=self.complete(gate,kwargs,before,plan)
        with patch('intune_iac.worker_state.os.getpid',return_value=-1):
            self.assert_code('worker_state_candidate_invalid',lambda:contract.admit(canonical(candidate),completion=completion))
        gate.close();self.assert_code('precondition_closed',lambda:contract.admit(canonical(candidate),completion=completion))

    def test_serial_overflow_is_not_a_new_native_revision(self):
        self.assert_code('worker_state_profile_unsupported',lambda:self.contract(mutate_baseline=lambda b:b.update(serial=2147483647)))

    def test_malformed_closed_input_returns_domain_error(self):
        for mutate in [lambda p:p.update(planned_values=[]),lambda p:p.update(resource_changes=[None]),
                       lambda p:p['planned_values'].update(root_module={'resources':None})]:
            self.setUp()
            with self.assertRaises(AppError):self.contract(mutate_plan=mutate)

    def test_management_mapping_remains_unsupported_while_raw_completion_is_exact(self):
        def raw_change(rows): rows[1]['body']['value'][0]['id']='37'
        contract,gate,_,kwargs,before,plan=self.contract(mutate_capture=raw_change)
        completion,candidate=self.complete(gate,kwargs,before,plan)
        admitted=contract.admit(canonical(candidate),completion=completion)
        self.assertEqual(admitted['management_mapping_status'],'unsupported')
        self.assertTrue(any(row['code']=='unsupported_setting_configuration_id' for row in admitted['management_mapping_blockers']))
        self.assertFalse(admitted['execution_authorized'])

    def test_changed_contract_template_cannot_redefine_approved_projection(self):
        contract,gate,_,kwargs,before,plan=self.contract()
        contract._template=canonical({'exfiltration':'changed'})
        self.assert_code('worker_state_contract_changed',contract.binding)
