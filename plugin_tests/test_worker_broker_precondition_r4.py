"""Broker calls actual sealed reader preconditions before loopback TLS writes."""
import copy
import hashlib
import json
import time
import unittest
from urllib.parse import urlencode

from intune_iac import identity_binding as ib, observation_reader as rd, worker_broker as wb
from intune_iac.io import AppError, canonical
from plugin_tests import test_worker_broker_r4 as tls, test_worker_precondition_r4 as capture
from plugin_tests.test_identity_binding_v5 import config, RecordedServices, TENANT
from plugin_tests.test_observation_reader_r4 import CLIENT, PRINCIPAL


class BrokerPreconditionTests(unittest.TestCase):
    setUpClass = classmethod(tls.BrokerTests.setUpClass.__func__)
    tearDownClass = classmethod(tls.BrokerTests.tearDownClass.__func__)
    setUp = tls.BrokerTests.setUp

    def native(self, *, changed=False, omit=False, cancel_after_read=False):
        fixture=capture.WorkerPreconditionTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        previous=fixture.estate['truth']['tenant_id']
        fixture.estate=json.loads(json.dumps(fixture.estate).replace(previous,TENANT))
        fixture.tenant=TENANT;fixture.spec=rd.ReaderSpec(TENANT,CLIENT,PRINCIPAL,(fixture.oid,))
        gate,transport,kwargs=fixture.capability(change_check=(lambda rows:rows[0]['body']['value'][0].update(description='Portal edit')) if changed else None)
        provider=ib.ClientSecretHandle('HOST-PROVIDER');backend=ib.ClientSecretHandle('HOST-BACKEND')
        self.addCleanup(provider.close);self.addCleanup(backend.close)
        binding=ib.bind_laboratory(config(),provider_credential=provider,backend_credential=backend,transport=RecordedServices())
        vault=wb.broker_credentials(binding=binding,backend_credential=backend,execution_binding_sha256='a'*64)
        self.addCleanup(vault.close)
        identity=vault.identities['provider'];form=urlencode({'client_id':identity['client_id'],
            'client_secret':vault.placeholders['provider'],'grant_type':'client_credentials','scope':wb._AUDIENCES['graph']}).encode()
        value=copy.deepcopy(self.policy);value.update(profile='laboratory_native_protocol',execution_binding_sha256='a'*64,
            identities=vault.identities,native_lock={'host':'examplestate.blob.core.windows.net','path':'/tfstate/intune/prod.tfstate'})
        # Exact backend target comes from the identity capability.
        _,target=binding.backend_configuration(backend)
        value['native_lock']={'host':target.blob_endpoint.removeprefix('https://').rstrip('/'),'path':'/'+target.container+'/'+target.key}
        template=copy.deepcopy(value['routes'][0]);template.update(host='login.microsoftonline.com',path='/'+TENANT+'/oauth2/v2.0/token',
            body_sha256=hashlib.sha256(form).hexdigest())
        mutations=[]
        for stage,method,path in [('policy','PUT',"/beta/deviceManagement/configurationPolicies('"+fixture.oid+"')"),
                ('assignments','POST','/beta/deviceManagement/configurationPolicies/'+fixture.oid+'/assign')]:
            mutations.append({'id':stage,'host':'graph.microsoft.com','method':method,'path':path,'query':{},
                'headers':{'content-type':'application/json'},'body_sha256':hashlib.sha256(kwargs['approved_'+('policy' if stage=='policy' else 'assignment')+'_body']).hexdigest(),
                'role':'provider','audience':'graph','effect':'mutation','max_attempts':1})
        value['routes']=[template]+mutations
        def guard():
            if cancel_after_read and len(transport.requests)>7:raise AppError('controller_cancelled','Fixture cancellation after actual read.')
        broker=wb.EgressBroker(value,journal=self.root/'native.sqlite3',guard=wb.laboratory_guard('a'*64,guard),
            upstream=self.upstream,credentials=vault,precondition=None if omit else gate)
        response=broker.handle(template['host'],'POST',template['path'],template['headers'],form)
        token=json.loads(response.body)['access_token']
        lock=value['native_lock'];broker.leases[(lock['host'],lock['path'])]={'id':'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee','operation':'OperationTypeApply'}
        return broker,gate,transport,kwargs,mutations,token

    def send(self,broker,route,body,token):
        return broker.handle(route['host'],route['method'],route['path'],{**route['headers'],'authorization':'Bearer '+token},body)

    def test_actual_reader_checks_precede_each_actual_tls_mutation(self):
        broker,gate,transport,kwargs,routes,token=self.native()
        self.assertEqual(self.send(broker,routes[0],kwargs['approved_policy_body'],token).status,200)
        self.assertEqual(len(transport.requests),12)
        self.assertEqual(self.send(broker,routes[1],kwargs['approved_assignment_body'],token).status,200)
        self.assertEqual(len(transport.requests),17)
        self.assertEqual([call[0] for call in self.calls],['POST','PUT','POST'])
        self.assertEqual(self.calls[-2][3],kwargs['approved_policy_body'])

    def test_portal_change_blocks_without_any_graph_forward(self):
        broker,gate,transport,kwargs,routes,token=self.native(changed=True)
        with self.assertRaises(AppError) as raised:self.send(broker,routes[0],kwargs['approved_policy_body'],token)
        self.assertEqual(raised.exception.code,'precondition_observed_change')
        self.assertEqual(len(self.calls),1)
        with broker._database() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM attempts WHERE route="policy"').fetchone()[0],0)

    def test_cancellation_after_fresh_read_prevents_dispatch(self):
        broker,gate,transport,kwargs,routes,token=self.native(cancel_after_read=True)
        with self.assertRaises(AppError) as raised:self.send(broker,routes[0],kwargs['approved_policy_body'],token)
        self.assertEqual(raised.exception.code,'controller_cancelled');self.assertEqual(len(self.calls),1)

    def test_native_profile_cannot_omit_independent_capability(self):
        with self.assertRaises(AppError) as raised:self.native(omit=True)
        self.assertEqual(raised.exception.code,'broker_precondition_required');self.assertEqual(self.calls,[])

    def test_assignments_cannot_precede_policy_and_bad_token_cannot_consume_phase(self):
        broker,gate,transport,kwargs,routes,token=self.native()
        with self.assertRaises(AppError):self.send(broker,routes[1],kwargs['approved_assignment_body'],token)
        self.assertEqual(len(transport.requests),7)
        with self.assertRaises(AppError):self.send(broker,routes[0],kwargs['approved_policy_body'],'foreign')
        self.assertEqual(len(transport.requests),7)
        self.assertEqual(self.send(broker,routes[0],kwargs['approved_policy_body'],token).status,200)
