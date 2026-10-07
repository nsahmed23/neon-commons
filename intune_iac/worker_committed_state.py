"""Read-only equality with an original approved computed state projection.

Staged module: no mutation authority. Historical hash-bound inputs are distinct
from the fresh, independently authenticated complete Graph capture.
"""
from datetime import datetime
import hashlib
import os
from pathlib import Path
import time
from intune_iac import worker_precondition as wp, worker_state as ws, observation_reader as reader_api
from intune_iac.io import AppError,canonical,digest,parse_json
from intune_iac.azure_backend import StateRevision
from intune_iac import worker_service as service,worker_lease_recovery as lease
from intune_iac.worker_recovery import inspect_native_recovery

_SEAL=object()
_FIELDS={'schema_version','profile','execution_binding_sha256','baseline_sha256','plan_json_sha256','saved_plan_sha256','admission_template_sha256','resource_address','tenant_id','object_id','reader_identity_sha256','preimage_capture_sha256','precondition_binding_sha256','computed_attributes','source_evidence_class','management_mapping_status','management_mapping_blockers','execution_authorized','service_freshness_atomic'}

def _fail(code):raise AppError(code,'The freshly observed state was not established as the original approved committed projection.') from None

def _copy(value):return parse_json(canonical(value))

class _CommittedObserver:
    def __init__(self,seal,*,job,reader,preimage_raw,policy_body,assignment_body,baseline_raw,plan_json_raw,saved_plan_raw):
        live=type(self) is LiveCommittedStateObserver
        if (seal is not _SEAL or type(self) not in (LiveCommittedStateObserver,LaboratoryCommittedStateObserver)
                or type(job) is not service.ServiceJob or type(reader) is not (reader_api.LiveGraphReader if live else reader_api.LaboratoryGraphReader)
                or job.manifest['profile']!=('azure_public_pilot' if live else 'native_docker_laboratory_protocol')):_fail('committed_state_capability_required')
        original=lease._original(job);manifest=job.manifest;contracts=manifest.get('state_contracts')
        if type(contracts) is not dict or set(contracts)!={'state-write'}:_fail('committed_state_contract_unsupported')
        contract=contracts['state-write'];gate=manifest['precondition_binding']
        if (type(contract) is not dict or set(contract)!=_FIELDS or contract['schema_version']!='computed-native-state-write-contract/1.0'
                or contract['profile']!='pinned_settings_catalog_update_with_two_independent_computed_fields'
                or contract['computed_attributes']!=sorted(ws.COMPUTED) or contract['execution_binding_sha256']!=manifest['execution_binding_sha256']
                or contract['precondition_binding_sha256']!=digest(gate) or contract['tenant_id']!=manifest['tenant_id']
                or [contract['object_id']]!=manifest['object_ids'] or contract['execution_authorized'] is not False):_fail('committed_state_contract_unsupported')
        for raw,expected in ((preimage_raw,gate['preimage_raw_sha256']),(policy_body,gate['approved_body_sha256']['policy']),
                (assignment_body,gate['approved_body_sha256']['assignments']),(baseline_raw,contract['baseline_sha256']),
                (plan_json_raw,contract['plan_json_sha256']),(saved_plan_raw,contract['saved_plan_sha256'])):
            if type(raw) is not bytes or not 0<len(raw)<=16*1024*1024 or hashlib.sha256(raw).hexdigest()!=expected:_fail('committed_state_original_artifact_substitution')
        if (contract['saved_plan_sha256']!=manifest['saved_plan_sha256'] or
                contract['baseline_sha256']!=manifest['provider_binding']['backend']['backend']['state_sha256'] or
                contract['preimage_capture_sha256']!=gate['preimage_capture_sha256']):_fail('committed_state_original_binding')
        prior=parse_json(preimage_raw);policy=parse_json(policy_body);assignments=parse_json(assignment_body)
        baseline=parse_json(baseline_raw);plan=parse_json(plan_json_raw)
        if (digest(prior)!=gate['preimage_raw_sha256'] or digest(wp._lossless(prior))!=gate['preimage_semantic_sha256']
                or type(policy) is not dict or set(policy)!=wp._POLICY_FIELDS or type(assignments) is not dict or set(assignments)!={'assignments'}
                or type(assignments['assignments']) is not list or any(type(row) is not dict or set(row)!={'target'} for row in assignments['assignments'])
                or digest({'policy':policy,'assignments':assignments})!=gate['approved_projection_sha256']
                or plan.get('format_version')!='1.2' or plan.get('terraform_version')!='1.13.1' or plan.get('errored') is not False):_fail('committed_state_original_binding')
        StateRevision.observe(baseline_raw,etag='"historical-content-only"')
        identity=reader.evidence()
        if (canonical(identity['identity'])!=canonical(gate['identity']) or digest(gate['identity'])!=contract['reader_identity_sha256']
                or contract['source_evidence_class']!=('graph_authenticated_observation' if live else 'graph_reader_laboratory')):_fail('committed_state_reader_binding')
        inspection=inspect_native_recovery(job.root/'broker.sqlite3',policy=manifest['broker_policy'])
        writes=[row for row in inspection['write_attempts'] if row['route']=='state-write']
        if len(writes)!=1 or writes[0]['status'] not in ('dispatch_started','outcome_unknown','response_received'):_fail('committed_state_original_write_unestablished')
        if len({digest(row['target']) for row in assignments['assignments']})!=len(assignments['assignments']):_fail('committed_state_assignment_duplicate')
        self.job,self.reader,self.original=job,reader,original
        self.contract,self.gate,self.prior,self.policy,self.assignments=_copy(contract),_copy(gate),prior,policy,assignments
        self.baseline=baseline;self.pid=os.getpid();self._binding=digest({'original':original,'contract':contract,'gate':gate,'prior':prior,'policy':policy,'assignments':assignments,'baseline':baseline})
    def __repr__(self):return '<'+type(self).__name__+' redacted>'
    def __reduce_ex__(self,protocol):raise TypeError('Committed-state reader authority cannot be serialized.')
    def check(self):
        if (self.pid!=os.getpid() or lease._original(self.job)!=self.original or self._binding!=digest({'original':self.original,'contract':self.contract,'gate':self.gate,'prior':self.prior,'policy':self.policy,'assignments':self.assignments,'baseline':self.baseline})
                or canonical(self.reader.evidence()['identity'])!=canonical(self.gate['identity'])):_fail('committed_state_observer_changed')
    def observe(self,candidate_raw,output):
        self.check();captured=self.reader.capture(self.contract['object_id'],Path(output))
        batch,source,actual=wp._validated_capture(captured,self.reader,max_age=30)
        if (batch['tenant_id']!=self.contract['tenant_id'] or batch['object_id']!=self.contract['object_id']
                or source['evidence_class']!=self.contract['source_evidence_class']):_fail('committed_state_capture_binding')
        expected=_copy(self.prior);expected['policy'].update({k:v for k,v in self.policy.items() if k!='settings'})
        expected['settings']=self.policy['settings'];expected['policy']['settingCount']=len(self.policy['settings'])
        stamp=actual['policy'].get('lastModifiedDateTime');previous=self.prior['policy'].get('lastModifiedDateTime')
        if wp._timestamp(stamp)>time.time()+60 or previous is not None and wp._timestamp(stamp)<wp._timestamp(previous):_fail('committed_state_timestamp_invalid')
        expected['policy']['lastModifiedDateTime']=stamp;expected=wp._lossless(expected)
        if (canonical(actual['policy'])!=canonical(expected['policy']) or canonical(actual['settings'])!=canonical(expected['settings'])
                or sorted(canonical(row['target']) for row in actual['assignments'])!=sorted(canonical(row['target']) for row in self.assignments['assignments'])):_fail('committed_state_graph_not_desired')
        prior_assignments={digest(row['target']):row for row in self.prior['assignments']}
        for row in actual['assignments']:
            old=prior_assignments.get(digest(row['target']))
            if old is not None:
                if canonical({k:v for k,v in row.items() if k!='id'})!=canonical({k:v for k,v in old.items() if k!='id'}):_fail('committed_state_assignment_metadata_changed')
            elif (set(row)-{'id','target','@odata.type','source','sourceId'} or row.get('@odata.type','#microsoft.graph.deviceManagementConfigurationPolicyAssignment')!='#microsoft.graph.deviceManagementConfigurationPolicyAssignment'
                    or row.get('source')!='direct' or 'sourceId' not in row or row['sourceId'] not in (None,'')):_fail('committed_state_assignment_metadata_changed')
        revision=StateRevision.observe(candidate_raw,etag='"content-proof-only"');candidate=parse_json(candidate_raw)
        if revision.lineage!=self.baseline['lineage'] or revision.serial!=self.baseline['serial']+1:_fail('committed_state_revision_not_original_successor')
        try:attributes=candidate['resources'][0]['instances'][0]['attributes']
        except (KeyError,IndexError,TypeError):_fail('committed_state_template_mismatch')
        policy=batch['source']['raw_observed']['policy'];settings=batch['source']['raw_observed']['settings']
        if type(policy.get('settingCount')) is not int or policy['settingCount']!=len(settings):_fail('committed_state_computed_mismatch')
        rendered=datetime.fromisoformat(stamp.replace('Z','+00:00')).replace(microsecond=0).isoformat(timespec='seconds').replace('+00:00','Z')
        if attributes.get('settings_count')!=len(settings) or type(attributes.get('settings_count')) is not int or attributes.get('last_modified_date_time')!=rendered:_fail('committed_state_computed_mismatch')
        for key in ws.COMPUTED:attributes[key]={'observation_bound_computed_attribute':key}
        if digest(candidate)!=self.contract['admission_template_sha256']:_fail('committed_state_template_mismatch')
        self.check()
        facts={'schema_version':'committed-state-original-projection/1','original_operation_id':self.job.identifier,'original_manifest_sha256':self.job.sha256,
            'original_contract_sha256':digest(self.contract),'original_template_sha256':self.contract['admission_template_sha256'],
            'original_saved_plan_sha256':self.contract['saved_plan_sha256'],'original_preimage_raw_sha256':self.gate['preimage_raw_sha256'],
            'state_sha256':hashlib.sha256(candidate_raw).hexdigest(),'state_lineage':revision.lineage,'state_serial':revision.serial,
            'desired_raw_sha256':digest(batch['source']['raw_observed']),'reader_identity_sha256':digest(source['identity']),
            'computed_values':{'settings_count':len(settings),'last_modified_date_time':rendered},'source_evidence_class':source['evidence_class'],
            'management_mapping_status':batch['status'],'management_mapping_blockers':batch['source'].get('mapping_blockers',[]),
            'actor_attribution':'unestablished','execution_authorized':False,'platform_qualified':False}
        return facts,captured

class LiveCommittedStateObserver(_CommittedObserver):pass
class LaboratoryCommittedStateObserver(_CommittedObserver):pass

def live_observer(**kwargs):return LiveCommittedStateObserver(_SEAL,**kwargs)
def laboratory_observer(**kwargs):return LaboratoryCommittedStateObserver(_SEAL,**kwargs)
