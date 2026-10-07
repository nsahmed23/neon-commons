"""Historical adoption projection plus fresh Graph equality; no backend authority.

The original capture is parsed as unverified historical evidence and checked
against its original signed hashes. It never becomes an authenticated capture.
Only a newly bound process-held reader supplies current Graph evidence.
"""
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
from intune_iac import worker_adoption_state as state, observation_reader as rd
from intune_iac import worker_precondition as wp, capture_adapter
from intune_iac.azure_backend import StateRevision
from intune_iac.identity_binding import BackendSpec
from intune_iac.io import AppError, canonical, digest, parse_json

FIELDS={'schema_version','profile','execution_binding_sha256','source_sha256','effective_inputs_sha256','locks_sha256','backend','baseline_revision','baseline_sha256','expected_semantic_sha256','resource_address','tenant_id','object_id','reader_identity','reader_identity_sha256','identity_observation_sha256','preimage_capture_sha256','preimage_raw_sha256','source_evidence_class','management_mapping_status','management_mapping_blockers','projection_profile','max_read_seconds','backend_state_authenticated','execution_authorized','service_freshness_atomic','ownership_proven'}

def _fail(code):raise AppError(code,'The original adoption projection or fresh independent observation was not established.') from None
def _copy(value):return parse_json(canonical(value))

def historical_projection(*,contract,baseline_raw,original_capture_root):
    """Inert content proof only. Caller must bind it to the registered operation."""
    if (type(contract) is not dict or set(contract)!=FIELDS or contract['schema_version']!='native-adoption-state-contract/1'
            or contract['profile'] not in ('azure_public_pilot','laboratory_native_protocol')
            or contract['resource_address']!=state.ADDRESS
            or contract['projection_profile']!='windows_mdm_nonsecret_choice_settings_explicit_direct_assignments/1'
            or type(contract['max_read_seconds']) is not int or not 1<=contract['max_read_seconds']<=30
            or any(contract[key] is not False for key in ('backend_state_authenticated','execution_authorized','service_freshness_atomic','ownership_proven'))):_fail('adoption_recovery_original_contract_unsupported')
    for key in ('execution_binding_sha256','source_sha256','effective_inputs_sha256','locks_sha256','baseline_sha256','expected_semantic_sha256','reader_identity_sha256','identity_observation_sha256','preimage_capture_sha256','preimage_raw_sha256'):
        if type(contract[key]) is not str or not state._HASH.fullmatch(contract[key]):_fail('adoption_recovery_original_contract_unsupported')
    if (type(baseline_raw) is not bytes or not 0<len(baseline_raw)<=state._MAX
            or hashlib.sha256(baseline_raw).hexdigest()!=contract['baseline_sha256']):_fail('adoption_recovery_baseline_substitution')
    try:
        original_revision=StateRevision(**contract['baseline_revision']);backend=BackendSpec(**contract['backend'])
    except (TypeError,KeyError):_fail('adoption_recovery_original_contract_unsupported')
    if StateRevision.observe(baseline_raw,etag=original_revision.etag)!=original_revision:_fail('adoption_recovery_baseline_substitution')
    before=parse_json(baseline_raw)
    if (set(before)-{'check_results'}!={'version','terraform_version','lineage','serial','resources','outputs'} or before['terraform_version']!='1.13.1'
            or before['resources']!=[] or before['outputs']!={} or before.get('check_results') is not None or original_revision.serial>=2147483647
            or backend.workspace!='default' or backend.state_lineage!=original_revision.lineage or type(backend.state_serial) is not int
            or backend.state_serial!=original_revision.serial or backend.state_sha256!=original_revision.sha256):_fail('adoption_recovery_baseline_not_empty')
    historical=capture_adapter.load_capture(original_capture_root,contract['tenant_id'])
    raw=historical['source']['raw_observed']
    if (historical['capture_sha256']!=contract['preimage_capture_sha256'] or digest(raw)!=contract['preimage_raw_sha256']
            or historical['object_id']!=contract['object_id'] or historical['tenant_id']!=contract['tenant_id']
            or any(row['coverage']!='complete' for row in historical['collections'])
            or historical['status']!=contract['management_mapping_status']
            or historical['source'].get('mapping_blockers',[])!=contract['management_mapping_blockers']):_fail('adoption_recovery_preimage_substitution')
    expected_class='graph_authenticated_observation' if contract['profile']=='azure_public_pilot' else 'graph_reader_laboratory'
    identity=contract['reader_identity']
    if (type(identity) is not dict or set(identity)!={'tenant_id','client_id','principal_object_id','object_ids'}
            or identity['tenant_id']!=contract['tenant_id'] or identity['object_ids']!=[contract['object_id']]
            or digest(identity)!=contract['reader_identity_sha256'] or contract['source_evidence_class']!=expected_class):_fail('adoption_recovery_original_reader_binding')
    attrs=state._projection(raw)
    expected={'version':4,'terraform_version':'1.13.1','lineage':before['lineage'],'serial':before['serial']+1,'outputs':{},'check_results':None,
        'resources':[{'mode':'managed','type':state.RESOURCE,'name':'selected','provider':state.PROVIDER,'instances':[{'schema_version':0,'identity_schema_version':0,
            'identity':{'id':attrs['id']},'attributes':attrs,'sensitive_attributes':[]}]}]}
    if digest(expected)!=contract['expected_semantic_sha256']:_fail('adoption_recovery_projection_substitution')
    return {'contract':_copy(contract),'raw':raw,'expected':expected,'baseline_revision':asdict(original_revision),
        'historical_capture_authenticated':False,'backend_state_authenticated':False,'execution_authorized':False}


class AdoptionRecoveryProjection:
    """Content + newly authenticated Graph; no execution/release authority."""
    def __init__(self,*,contract,baseline_raw,original_capture_root,reader):
        self.proof=historical_projection(contract=contract,baseline_raw=baseline_raw,original_capture_root=original_capture_root)
        self.reader=reader;self._reader_id=id(reader);self.pid=os.getpid();self._proof_sha=digest(self.proof)
        self._reader_type=rd.LiveGraphReader if contract['profile']=='azure_public_pilot' else rd.LaboratoryGraphReader
        if type(reader) is not self._reader_type:_fail('adoption_recovery_reader_required')
        evidence=reader.evidence()
        if (canonical(evidence['identity'])!=canonical(contract['reader_identity']) or evidence['evidence_class']!=contract['source_evidence_class']
                or evidence['source_authenticity_verified'] is not (self._reader_type is rd.LiveGraphReader)):_fail('adoption_recovery_reader_binding')
        self._reader_evidence=digest(evidence)
    def __reduce_ex__(self,protocol):raise TypeError('Fresh reader authority cannot be serialized.')
    def check(self):
        if (self.pid!=os.getpid() or digest(self.proof)!=self._proof_sha or type(self.reader) is not self._reader_type
                or id(self.reader)!=self._reader_id or digest(self.reader.evidence())!=self._reader_evidence):_fail('adoption_recovery_projection_changed')
    def observe(self,candidate_raw,output,*,state_write_attempts):
        self.check();contract=self.proof['contract']
        if type(state_write_attempts) is not int or not 0<=state_write_attempts<=1:_fail('adoption_recovery_state_write_ambiguous')
        if type(candidate_raw) is not bytes or not 0<len(candidate_raw)<=state._MAX:_fail('adoption_recovery_state_invalid')
        raw_sha=hashlib.sha256(candidate_raw).hexdigest()
        revision=StateRevision.observe(candidate_raw,etag='"content-only"')
        classification='unexpected_state'
        if raw_sha==contract['baseline_sha256']:classification='original_baseline'
        elif canonical(parse_json(candidate_raw))==canonical(self.proof['expected']) and state_write_attempts==1:classification='approved_adoption_successor'
        capture=self.reader.capture(contract['object_id'],Path(output),max_elapsed_seconds=contract['max_read_seconds'])
        batch,source,_=wp._validated_capture(capture,self.reader,max_age=contract['max_read_seconds'])
        graph_equal=(batch['tenant_id']==contract['tenant_id'] and batch['object_id']==contract['object_id']
            and canonical(batch['source']['raw_observed'])==canonical(self.proof['raw']))
        self.check()
        return {'schema_version':'adoption-original-projection-observation/1','original_contract_sha256':digest(contract),
            'original_baseline_sha256':contract['baseline_sha256'],'original_preimage_capture_sha256':contract['preimage_capture_sha256'],
            'original_preimage_raw_sha256':contract['preimage_raw_sha256'],'original_expected_semantic_sha256':contract['expected_semantic_sha256'],
            'classification':classification,'state_sha256':raw_sha,'state_lineage':revision.lineage,'state_serial':revision.serial,
            'graph_unchanged':graph_equal,'fresh_capture_sha256':batch['capture_sha256'],'fresh_raw_sha256':digest(batch['source']['raw_observed']),
            'fresh_identity_observation_sha256':source['identity_observation_sha256'],'reader_identity_sha256':digest(source['identity']),
            'source_evidence_class':source['evidence_class'],'management_mapping_status':batch['status'],
            'management_mapping_blockers':batch['source'].get('mapping_blockers',[]),'actor_attribution':'unestablished',
            'historical_capture_authenticated':False,'backend_state_authenticated':False,'execution_authorized':False},capture
