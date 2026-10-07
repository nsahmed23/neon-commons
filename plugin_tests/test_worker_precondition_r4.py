"""Actual sealed reader/precondition interfaces with independent local responses."""
import copy
import hashlib
import json
from pathlib import Path
import pickle
import tempfile
import threading
import unittest
from unittest.mock import patch

from intune_iac import worker_precondition as wp, observation_reader as rd
from intune_iac.identity_binding import ClientSecretHandle
from intune_iac.io import AppError, canonical
from intune_iac.observation_jobs import _Fixture
from intune_iac.synthetic import generate_estate
from plugin_tests.test_observation_reader_r4 import fixture_for, CLIENT, PRINCIPAL


class WorkerPreconditionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.estate = generate_estate(seed=840, policy_count=1)
        self.tenant = self.estate['truth']['tenant_id']; self.oid = self.estate['truth']['policies'][0]['id']
        self.spec = rd.ReaderSpec(self.tenant, CLIENT, PRINCIPAL, (self.oid,))

    def capability(self, *, change_initial=None, change_check=None, change_intermediate=None, change_completed=None, clock=None):
        fixture = fixture_for(self.estate)
        initial = copy.deepcopy(fixture['responses'][2:])
        if change_initial: change_initial(initial)
        check = copy.deepcopy(initial)
        if change_check: change_check(check)
        intermediate = copy.deepcopy(initial)
        intermediate[0]['body']['value'][0]['description'] = 'Reviewed correction'
        if change_intermediate: change_intermediate(intermediate)
        completed = copy.deepcopy(intermediate)
        if change_completed: change_completed(completed)
        fixture['responses'] = fixture['responses'][:2] + initial + check + intermediate + completed + copy.deepcopy(completed)
        transport = _Fixture(canonical(fixture)); credential = ClientSecretHandle('SYNTHETIC-READER-SECRET')
        self.addCleanup(credential.close)
        reader = rd.bind_laboratory_reader(self.spec, credential=credential, transport=transport, **({'clock': clock} if clock else {}))
        self.addCleanup(reader.close)
        preimage = reader.capture(self.oid, self.root/'initial')
        batch, _ = preimage.verified(); raw = batch['source']['raw_observed']
        policy = {key:copy.deepcopy(raw['policy'][key]) for key in ('name','description','platforms','technologies','roleScopeTagIds')}
        policy['description'] = 'Reviewed correction'; policy['settings'] = copy.deepcopy(raw['settings'])
        assignments = {'assignments':[{'target':copy.deepcopy(row['target'])} for row in raw['assignments']]}
        kwargs = dict(reader=reader, preimage=preimage, execution_binding_sha256='a'*64,
            approved_policy_body=canonical(policy), approved_assignment_body=canonical(assignments), evidence_root=self.root/'checks')
        capability = wp.create_laboratory_precondition(**kwargs)
        self.addCleanup(capability.close)
        return capability, transport, kwargs

    def assert_code(self, code, action):
        with self.assertRaises(AppError) as raised: action()
        self.assertEqual(raised.exception.code, code)

    def check(self, capability, kwargs, stage='policy'):
        capability.check_before_mutation(stage=stage, request_body=kwargs['approved_policy_body' if stage=='policy' else 'approved_assignment_body'])

    def test_complete_fresh_preimage_and_reviewed_intermediate_are_distinct(self):
        capability, transport, kwargs = self.capability()
        count = len(transport.requests)
        self.check(capability, kwargs); self.assertEqual(len(transport.requests), count+5)
        self.check(capability, kwargs, 'assignments'); self.assertEqual(len(transport.requests), count+10)
        attempts = json.loads((self.root/'checks/attempts.json').read_bytes())
        self.assertEqual([row['status'] for row in attempts], ['matched','matched'])
        self.assertNotEqual(attempts[0]['capture_sha256'], attempts[1]['capture_sha256'])
        self.assertFalse(capability.binding()['execution_authorized'])
        self.assertIn('not atomic', capability.binding()['residual_race'])
        self.assertTrue(all(row['method']=='GET' for row in transport.requests[2:]))

    def test_portal_side_policy_change_blocks_before_mutation(self):
        capability, transport, kwargs = self.capability(change_check=lambda rows:rows[0]['body']['value'][0].update(description='Unreviewed change'))
        self.assert_code('precondition_observed_change', lambda:self.check(capability, kwargs))
        self.assertTrue((self.root/'checks/policy/capture-receipt.json').exists())
        self.assert_code('precondition_phase_invalid', lambda:self.check(capability, kwargs))
        self.assertEqual(len(transport.requests), 12)

    def test_denied_assignments_retained_and_never_complete(self):
        capability, _, kwargs = self.capability(change_check=lambda rows:rows[2].update(status=403,body={'error':{'code':'Denied'}}))
        self.assert_code('precondition_coverage_incomplete', lambda:self.check(capability, kwargs))
        attempt=json.loads((self.root/'checks/attempts.json').read_bytes())[0]
        self.assertEqual(attempt['error_code'],'precondition_coverage_incomplete')
        self.assertTrue((self.root/'checks/policy/raw').is_dir())

    def test_pagination_escape_is_not_requested(self):
        capability, transport, kwargs = self.capability(change_check=lambda rows:rows[2]['body'].update({'@odata.nextLink':'https://outside.invalid/policies'}))
        self.assert_code('precondition_coverage_incomplete', lambda:self.check(capability, kwargs))
        self.assertTrue(all(row['host'] in ('login.microsoftonline.com','graph.microsoft.com') for row in transport.requests))

    def test_wrong_setting_id_and_typed_value_fail(self):
        def change(rows): rows[1]['body']['value'][0]['id']='changed-id'
        capability, _, kwargs = self.capability(change_check=change)
        self.assert_code('precondition_observed_change', lambda:self.check(capability, kwargs))

    def test_ordered_unknown_array_and_null_are_not_dropped(self):
        def initial(rows): rows[1]['body']['value'][0]['retainedUnknown']={'sequence':[1,'1',None], 'present':None}
        def change(rows): rows[1]['body']['value'][0]['retainedUnknown']['sequence'].reverse()
        capability, _, kwargs = self.capability(change_initial=initial, change_check=change)
        self.assert_code('precondition_observed_change', lambda:self.check(capability, kwargs))

    def test_assignment_reorder_is_equal_but_targets_are_exact(self):
        def reorder(rows):
            rows[2]['body']['value'],rows[3]['body']['value']=rows[3]['body']['value'],rows[2]['body']['value']
        capability, _, kwargs = self.capability(change_check=reorder)
        self.check(capability, kwargs)
        self.assertEqual(json.loads((self.root/'checks/attempts.json').read_bytes())[0]['status'],'matched')

    def test_policy_success_does_not_authorize_changed_assignments(self):
        def change(rows): rows[2]['body']['value'][0]['target']['unexpectedFilter']='unreviewed'
        capability, _, kwargs = self.capability(change_intermediate=change)
        self.check(capability, kwargs)
        self.assert_code('precondition_observed_change', lambda:self.check(capability, kwargs,'assignments'))

    def test_intermediate_must_match_exact_reviewed_policy_settings(self):
        capability, _, kwargs = self.capability(change_intermediate=lambda rows:rows[0]['body']['value'][0].update(description='Other correction'))
        self.check(capability, kwargs)
        self.assert_code('precondition_observed_change', lambda:self.check(capability, kwargs,'assignments'))

    def test_json_and_generic_callback_cannot_construct_capability(self):
        capability, _, kwargs = self.capability()
        with self.assertRaises(AppError):wp.LiveGraphPrecondition(None,None,None,None,None,None,None,None)
        self.assert_code('precondition_reader_capability_required', lambda:wp.create_live_precondition(**{**kwargs,'evidence_root':self.root/'wrong-live'}))
        for fake in ({'source_authenticity_verified':True}, lambda:True):
            self.assert_code('precondition_reader_capability_required', lambda:wp.create_laboratory_precondition(**{**kwargs,'reader':fake,'evidence_root':self.root/'fake'}))
        with self.assertRaises(TypeError):pickle.dumps(capability)

    def test_exact_body_target_and_single_use_phase(self):
        capability, transport, kwargs=self.capability()
        self.assertEqual(capability.stage_for_request('PUT',"/beta/deviceManagement/configurationPolicies('"+self.oid+"')",kwargs['approved_policy_body']),'policy')
        self.assert_code('precondition_request_target',lambda:capability.stage_for_request('PUT','/beta/foreign',kwargs['approved_policy_body']))
        self.assert_code('precondition_request_substitution',lambda:capability.check_before_mutation(stage='policy',request_body=kwargs['approved_policy_body']+b' '))
        self.assert_code('precondition_phase_invalid',lambda:self.check(capability,kwargs,'assignments'))
        self.assertEqual(len(transport.requests),7)
        self.check(capability,kwargs)
        self.assert_code('precondition_phase_invalid',lambda:self.check(capability,kwargs))

    def test_expired_reader_stops_before_next_get(self):
        clock=[0.0];capability,transport,kwargs=self.capability(clock=lambda:clock[0]);clock[0]=120.0
        self.assert_code('reader_expired',lambda:self.check(capability,kwargs))
        self.assertEqual(len(transport.requests),7)

    def test_changed_capture_bytes_cannot_reconstruct_fresh_preimage(self):
        capability,transport,kwargs=self.capability()
        raw=self.root/'initial/raw/page-000000.json';raw.write_bytes(raw.read_bytes()+b' ')
        with self.assertRaises(AppError):self.check(capability,kwargs)
        self.assertEqual(len(transport.requests),7)

    def test_process_fork_and_closed_capability_do_not_reuse_authority(self):
        capability,_,kwargs=self.capability()
        with patch('intune_iac.worker_precondition.os.getpid',return_value=-1):
            self.assert_code('precondition_closed',lambda:self.check(capability,kwargs))
        capability.close();self.assert_code('precondition_closed',lambda:self.check(capability,kwargs))

    def test_completed_capture_is_sealed_fresh_desired_service_evidence(self):
        def completed(rows):
            rows[0]['body']['value'][0]['lastModifiedDateTime']='2026-10-01T00:00:00Z'
            rows[2]['body']['value'][0]['id']='new-service-assignment-id'
        capability,transport,kwargs=self.capability(change_completed=completed)
        self.assert_code('precondition_phase_invalid',capability.capture_completed)
        self.check(capability,kwargs);self.check(capability,kwargs,'assignments')
        capture=capability.capture_completed();self.assertIs(type(capture),rd.CapturedObservation)
        batch,source=capture.verified();raw=batch['source']['raw_observed']
        self.assertEqual(raw['policy']['description'],'Reviewed correction')
        self.assertEqual(raw['policy']['lastModifiedDateTime'],'2026-10-01T00:00:00Z')
        self.assertEqual(raw['policy']['settingCount'],1)
        self.assertEqual(raw['settings'][0]['id'],'0')
        self.assertEqual(raw['assignments'][0]['id'],'new-service-assignment-id')
        self.assertEqual(len(raw['assignments']),3)
        self.assertFalse(source['source_authenticity_verified'])
        self.assertEqual(len(transport.requests),22)
        self.assert_code('precondition_phase_invalid',capability.capture_completed)

    def test_completed_capture_rejects_unapproved_target_filter(self):
        def completed(rows):
            rows[2]['body']['value'][0]['target']['deviceAndAppManagementAssignmentFilterType']='exclude'
        capability,_,kwargs=self.capability(change_completed=completed)
        self.check(capability,kwargs);self.check(capability,kwargs,'assignments')
        self.assert_code('precondition_observed_change',capability.capture_completed)
        self.assertEqual(json.loads((self.root/'checks/attempts.json').read_bytes())[-1]['status'],'failed')

    def test_completed_capture_retains_unknown_assignment_metadata(self):
        def initial(rows):rows[2]['body']['value'][0]['unknownMetadata']={'raw':None}
        def completed(rows):rows[2]['body']['value'][0].pop('unknownMetadata')
        capability,_,kwargs=self.capability(change_initial=initial,change_completed=completed)
        self.check(capability,kwargs);self.check(capability,kwargs,'assignments')
        self.assert_code('precondition_observed_change',capability.capture_completed)

    def test_completed_capture_does_not_confuse_direct_with_inherited_assignment(self):
        def completed(rows):rows[2]['body']['value'][0]['source']='policySet'
        capability,_,kwargs=self.capability(change_completed=completed)
        self.check(capability,kwargs);self.check(capability,kwargs,'assignments')
        self.assert_code('precondition_observed_change',capability.capture_completed)

    def test_completion_capability_binds_desired_projection_and_recovery_is_read_only(self):
        capability,transport,kwargs=self.capability()
        self.check(capability,kwargs);self.check(capability,kwargs,'assignments')
        completion=capability.completion();facts=completion.verified()
        self.assertIs(type(completion),wp.LaboratoryGraphCompletion)
        self.assertEqual(facts['execution_binding_sha256'],'a'*64)
        self.assertEqual(facts['approved_projection_sha256'],capability.binding()['approved_projection_sha256'])
        self.assertIs(type(facts['capture']),rd.CapturedObservation)
        renewed=capability.completion();self.assertNotEqual(renewed.verified()['capture_sha256'],facts['capture_sha256'])
        self.assertTrue((self.root/'checks/completed-02/capture-receipt.json').is_file())
        self.assertEqual(len(transport.requests),27)
        self.assertTrue(all(row['method']=='GET' for row in transport.requests[1:]))
        self.assert_code('precondition_phase_invalid',lambda:self.check(capability,kwargs))

    def test_completion_cannot_be_serialized_or_rebuilt_from_success_label(self):
        capability,_,kwargs=self.capability()
        self.check(capability,kwargs);self.check(capability,kwargs,'assignments');completion=capability.completion()
        with self.assertRaises(TypeError):pickle.dumps(completion)
        self.assert_code('precondition_completion_constructor_forbidden',lambda:wp.LiveGraphCompletion(None,capability,{'status':'PASS'}))
        self.assert_code('precondition_completion_constructor_forbidden',lambda:wp.LaboratoryGraphCompletion(None,capability,{'status':'PASS'}))
        completion._facts['object_id']='other'
        self.assert_code('precondition_completion_changed',completion.verified)

    def test_completion_expires_and_does_not_reanimate_closed_reader(self):
        clock=[0.0];capability,_,kwargs=self.capability(clock=lambda:clock[0])
        self.check(capability,kwargs);self.check(capability,kwargs,'assignments');completion=capability.completion()
        clock[0]=120.0
        self.assert_code('reader_expired',completion.verified)

    def test_duplicate_assignment_identity_is_rejected(self):
        def change(rows):rows[3]['body']['value'][0]['id']=rows[2]['body']['value'][0]['id']
        capability,_,kwargs=self.capability(change_check=change)
        with self.assertRaises(AppError):self.check(capability,kwargs)

    def test_null_absent_and_number_string_remain_distinct(self):
        def initial(rows):rows[1]['body']['value'][0]['retainedUnknown']={'typed':1,'nullable':None}
        def changed(rows):
            rows[1]['body']['value'][0]['retainedUnknown']={'typed':'1'}
        capability,_,kwargs=self.capability(change_initial=initial,change_check=changed)
        self.assert_code('precondition_observed_change',lambda:self.check(capability,kwargs))

    def test_count_and_future_computed_timestamp_are_not_arbitrary(self):
        def change(rows):rows[0]['body']['value'][0]['settingCount']=2
        capability,_,kwargs=self.capability(change_check=change)
        self.assert_code('precondition_settings_incomplete',lambda:self.check(capability,kwargs))

    def test_future_intermediate_timestamp_is_not_admitted(self):
        def change(rows):rows[0]['body']['value'][0]['lastModifiedDateTime']='9999-01-01T00:00:00Z'
        capability,_,kwargs=self.capability(change_intermediate=change)
        self.check(capability,kwargs)
        self.assert_code('precondition_timestamp_invalid',lambda:self.check(capability,kwargs,'assignments'))

    def test_projection_mutation_stops_before_new_read(self):
        capability,transport,kwargs=self.capability();capability._policy['description']='mutated'
        self.assert_code('precondition_binding_changed',lambda:self.check(capability,kwargs))
        self.assertEqual(len(transport.requests),7)

    def test_concurrent_same_phase_has_one_reader_attempt(self):
        capability,transport,kwargs=self.capability();results=[]
        def run():
            try:self.check(capability,kwargs);results.append('matched')
            except AppError as error:results.append(error.code)
        threads=[threading.Thread(target=run) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=5);self.assertFalse(thread.is_alive())
        self.assertCountEqual(results,['matched','precondition_phase_invalid'])
        self.assertEqual(len(transport.requests),12)


if __name__=='__main__':unittest.main()
