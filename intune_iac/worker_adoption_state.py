"""Closed existing-policy adoption projection; no execution/backend authority.

Graph authenticity comes only from the process-held reader. Supplied state bytes
and StateRevision are content assertions: the controller must separately bind an
actual authenticated receiving-backend observation before approval or dispatch.
"""
from dataclasses import asdict
from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit

from .azure_backend import StateRevision
from .identity_binding import BackendSpec
from . import observation_reader as rd, worker_precondition as wp
from .io import AppError,canonical,digest,parse_json,write_json

RESOURCE='microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json'
PROVIDER='provider["registry.terraform.io/deploymenttheory/microsoft365"]'
ADDRESS=RESOURCE+'.selected'
_HASH=re.compile('[a-f0-9]{64}');_UUID=re.compile('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
_SEAL=object();_MAX=1024*1024

def _fail(code):raise AppError(code,'The closed adoption projection, fresh observation or operation binding is unsupported or changed.') from None
def _copy(value):return parse_json(canonical(value))
def _retain(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(parent)
    finally:os.close(parent)
def _text(value,maximum=4096):
    if type(value) is not str or not 1<=len(value)<=maximum or any(ord(c)<32 for c in value):_fail('adoption_projection_unsupported')
    return value

def _date(value):
    _text(value,64)
    try:stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:_fail('adoption_projection_unsupported')
    if stamp.tzinfo is None:_fail('adoption_projection_unsupported')
    return stamp.replace(microsecond=0).isoformat(timespec='seconds').replace('+00:00','Z')

def _choice(instance,depth=0):
    if (depth>16 or type(instance) is not dict or set(instance)!={'@odata.type','settingDefinitionId','settingInstanceTemplateReference','choiceSettingValue'}
            or instance['@odata.type']!='#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance'
            or instance['settingInstanceTemplateReference'] is not None):_fail('adoption_settings_unsupported')
    _text(instance['settingDefinitionId'],1024);value=instance['choiceSettingValue']
    if (type(value) is not dict or set(value)!={'@odata.type','value','settingValueTemplateReference','children'}
            or value['@odata.type']!='#microsoft.graph.deviceManagementConfigurationChoiceSettingValue'
            or value['settingValueTemplateReference'] is not None or type(value['children']) is not list or len(value['children'])>128):_fail('adoption_settings_unsupported')
    _text(value['value'],2048)
    for child in value['children']:_choice(child,depth+1)
    if len({child['settingDefinitionId'] for child in value['children']})!=len(value['children']):_fail('adoption_settings_unsupported')

def _projection(raw):
    # Unknown fields/types remain unsupported instead of being silently dropped.
    if type(raw) is not dict or set(raw)!={'policy','settings','assignments'}:_fail('adoption_projection_unsupported')
    p,settings,assignments=raw['policy'],raw['settings'],raw['assignments']
    fields={'id','name','description','platforms','technologies','roleScopeTagIds','settingCount','isAssigned','createdDateTime','lastModifiedDateTime'}
    if (type(p) is not dict or set(p)-{'@odata.type'}!=fields or p.get('@odata.type','#microsoft.graph.deviceManagementConfigurationPolicy')!='#microsoft.graph.deviceManagementConfigurationPolicy'
            or not _UUID.fullmatch(_text(p['id'],36)) or p['platforms']!='windows10' or p['technologies']!='mdm'
            or p['description'] is not None and type(p['description']) is not str or type(p['isAssigned']) is not bool
            or type(p['settingCount']) is not int or type(settings) is not list or not 1<=len(settings)<=128 or p['settingCount']!=len(settings)
            or type(p['roleScopeTagIds']) is not list or not p['roleScopeTagIds'] or len(p['roleScopeTagIds'])>128):_fail('adoption_projection_unsupported')
    _text(p['name']);tags=[_text(v,128) for v in p['roleScopeTagIds']]
    if len(set(tags))!=len(tags):_fail('adoption_projection_unsupported')
    ids=[]
    for row in settings:
        if (type(row) is not dict or set(row)!={'id','@odata.type','settingInstance'} or row['@odata.type']!='#microsoft.graph.deviceManagementConfigurationSetting'
                or type(row['id']) is not str or not re.fullmatch('[0-9]{1,10}',row['id'])):_fail('adoption_settings_unsupported')
        ids.append(row['id']);_choice(row['settingInstance'])
    if len(set(ids))!=len(ids):_fail('adoption_settings_unsupported')
    if type(assignments) is not list or len(assignments)>128:_fail('adoption_assignments_unsupported')
    projected=[];assignment_ids=[]
    for row in assignments:
        if (type(row) is not dict or set(row)!={'id','@odata.type','source','sourceId','target'}
                or row['@odata.type']!='#microsoft.graph.deviceManagementConfigurationPolicyAssignment'
                or row['source']!='direct' or row['sourceId'] is not None):_fail('adoption_assignments_unsupported')
        assignment_ids.append(_text(row['id'],512));t=row['target']
        if type(t) is not dict or type(t.get('@odata.type')) is not str:_fail('adoption_assignments_unsupported')
        kind=t['@odata.type'].removeprefix('#microsoft.graph.')
        if kind not in ('groupAssignmentTarget','exclusionGroupAssignmentTarget','allDevicesAssignmentTarget','allLicensedUsersAssignmentTarget'):_fail('adoption_assignments_unsupported')
        group=kind in ('groupAssignmentTarget','exclusionGroupAssignmentTarget')
        if (set(t)!={'@odata.type','deviceAndAppManagementAssignmentFilterId','deviceAndAppManagementAssignmentFilterType'}|({'groupId'} if group else set())
                or group and (type(t['groupId']) is not str or not _UUID.fullmatch(t['groupId']))
                or type(t['deviceAndAppManagementAssignmentFilterId']) is not str or not _UUID.fullmatch(t['deviceAndAppManagementAssignmentFilterId'])
                or t['deviceAndAppManagementAssignmentFilterType'] not in ('none','include','exclude')):_fail('adoption_assignments_unsupported')
        if (t['deviceAndAppManagementAssignmentFilterType']=='none')!=(t['deviceAndAppManagementAssignmentFilterId']=='00000000-0000-0000-0000-000000000000'):_fail('adoption_assignments_unsupported')
        projected.append({'type':kind,'group_id':t.get('groupId'),'filter_id':t['deviceAndAppManagementAssignmentFilterId'],'filter_type':t['deviceAndAppManagementAssignmentFilterType']})
    if len(set(assignment_ids))!=len(assignment_ids) or len({digest(v) for v in projected})!=len(projected):_fail('adoption_assignments_unsupported')
    # Go encoding/json + JSONAlphabetically: sorted map keys, arrays unchanged,
    # HTML and line-separator escapes retained inside the provider string value.
    settings_json=canonical({'settings':settings}).decode().replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    return {'id':p['id'],'name':p['name'],'description':p['description'],'platforms':'windows10','technologies':['mdm'],
        'role_scope_tag_ids':sorted(tags),'settings_count':p['settingCount'],'is_assigned':p['isAssigned'],
        'created_date_time':_date(p['createdDateTime']),'last_modified_date_time':_date(p['lastModifiedDateTime']),
        'settings_catalog_template_type':'','settings':settings_json,'assignments':sorted(projected,key=canonical) or None,'timeouts':None}

class AdoptionStateObservation:
    """Sealed projection+fresh Graph proof; supplied backend bytes are not authenticated."""
    def __init__(self,seal,contract,raw,revision,capture):
        if seal is not _SEAL or type(contract) is not NativeAdoptionStateContract:_fail('adoption_observation_capability_required')
        self._contract,self._raw,self._revision,self._capture=contract,raw,revision,capture;self._pid=os.getpid()
        self._hash=hashlib.sha256(raw).hexdigest();self._binding=digest(contract.binding())
    def verified(self):
        self._contract._fresh()
        if (self._pid!=os.getpid() or type(self._revision) is not StateRevision or digest(self._contract.binding())!=self._binding
                or StateRevision.observe(self._raw,etag=self._revision.etag)!=self._revision or hashlib.sha256(self._raw).hexdigest()!=self._hash):_fail('adoption_observation_changed')
        batch,source,_=wp._validated_capture(self._capture,self._contract._reader,max_age=30)
        self._contract._match_graph(batch)
        return {'schema_version':'adoption-state-projection-observation/1','contract_sha256':self._binding,
            'state_raw':self._raw,'state_revision':self._revision,'capture':self._capture,'profile':self._contract.profile,
            'source_evidence_class':source['evidence_class'],'backend_state_authenticated':False,'execution_authorized':False,
            'reconciliation_authorized':False,'lease_release_authorized':False,'actor_attribution':'unestablished'}
    def __reduce_ex__(self,protocol):raise TypeError('Adoption observations cannot be serialized.')
    def __repr__(self):return '<AdoptionStateObservation projection only>'

class NativeAdoptionStateContract:
    def __init__(self,*,baseline_raw,baseline_revision,backend,reader,preimage,execution_binding_sha256,source_sha256,effective_inputs_sha256,locks_sha256,evidence_root,max_read_seconds=30):
        if (type(baseline_raw) is not bytes or not 0<len(baseline_raw)<=_MAX or type(baseline_revision) is not StateRevision or type(backend) is not BackendSpec
                or type(reader) not in (rd.LiveGraphReader,rd.LaboratoryGraphReader) or type(max_read_seconds) is not int or not 1<=max_read_seconds<=30
                or any(type(v) is not str or not _HASH.fullmatch(v) for v in (execution_binding_sha256,source_sha256,effective_inputs_sha256,locks_sha256))):_fail('adoption_contract_invalid')
        if StateRevision.observe(baseline_raw,etag=baseline_revision.etag)!=baseline_revision:_fail('adoption_baseline_mismatch')
        before=parse_json(baseline_raw)
        if (set(before)-{'check_results'}!={'version','terraform_version','lineage','serial','resources','outputs'} or before['terraform_version']!='1.13.1'
                or before['resources']!=[] or before['outputs']!={} or before.get('check_results') is not None or baseline_revision.serial>=2147483647):_fail('adoption_baseline_not_empty')
        if (backend.workspace!='default' or backend.state_lineage!=baseline_revision.lineage or type(backend.state_serial) is not int or backend.state_serial!=baseline_revision.serial or backend.state_sha256!=baseline_revision.sha256
                or type(backend.blob_endpoint) is not str or not re.fullmatch(r'https://[a-z0-9]{3,24}\.blob\.core\.windows\.net',backend.blob_endpoint)
                or type(backend.container) is not str or not re.fullmatch('[a-z0-9-]{3,63}',backend.container)
                or type(backend.key) is not str or not re.fullmatch('[A-Za-z0-9_./-]{1,512}',backend.key) or '..' in backend.key.split('/') or '//' in backend.key):_fail('adoption_backend_binding')
        batch,source,_=wp._validated_capture(preimage,reader,max_age=300);raw=batch['source']['raw_observed'];attrs=_projection(raw)
        expected={'version':4,'terraform_version':'1.13.1','lineage':before['lineage'],'serial':before['serial']+1,'outputs':{},'check_results':None,
            'resources':[{'mode':'managed','type':RESOURCE,'name':'selected','provider':PROVIDER,'instances':[{'schema_version':0,'identity_schema_version':0,
            'identity':{'id':attrs['id']},'attributes':attrs,'sensitive_attributes':[]}]}]}
        self.profile='azure_public_pilot' if type(reader) is rd.LiveGraphReader else 'laboratory_native_protocol'
        self._reader,self._preimage,self._raw=reader,preimage,_copy(raw);self._reader_object_id,self._preimage_object_id=id(reader),id(preimage);self._expected=canonical(expected);self._pid=os.getpid();self._phase='prepared';self._lock=threading.RLock();self._reads=0
        self._root=Path(evidence_root).absolute()
        if '..' in self._root.parts or any(p.is_symlink() for p in (self._root,*self._root.parents)):_fail('adoption_evidence_path')
        try:self._root.mkdir(mode=0o700)
        except OSError:_fail('adoption_evidence_path')
        self._binding={'schema_version':'native-adoption-state-contract/1','profile':self.profile,'execution_binding_sha256':execution_binding_sha256,
            'source_sha256':source_sha256,'effective_inputs_sha256':effective_inputs_sha256,'locks_sha256':locks_sha256,'backend':asdict(backend),'baseline_revision':asdict(baseline_revision),
            'baseline_sha256':baseline_revision.sha256,'expected_semantic_sha256':hashlib.sha256(self._expected).hexdigest(),'resource_address':ADDRESS,
            'tenant_id':batch['tenant_id'],'object_id':batch['object_id'],'reader_identity':source['identity'],'reader_identity_sha256':digest(source['identity']),
            'identity_observation_sha256':source['identity_observation_sha256'],'preimage_capture_sha256':batch['capture_sha256'],'preimage_raw_sha256':digest(raw),
            'source_evidence_class':source['evidence_class'],'management_mapping_status':batch['status'],'management_mapping_blockers':batch['source'].get('mapping_blockers',[]),
            'projection_profile':'windows_mdm_nonsecret_choice_settings_explicit_direct_assignments/1','max_read_seconds':max_read_seconds,
            'backend_state_authenticated':False,'execution_authorized':False,'service_freshness_atomic':False,'ownership_proven':False}
        self._digest=digest(self._binding);write_json(self._root/'binding.json',self._binding)
    def __reduce_ex__(self,protocol):raise TypeError('Adoption contracts cannot be serialized.')
    def __repr__(self):return '<NativeAdoptionStateContract content admission only>'
    def _fresh(self):
        if (self._pid!=os.getpid() or digest(self._binding)!=self._digest or self.profile!=self._binding['profile'] or digest(self._raw)!=self._binding['preimage_raw_sha256']
                or hashlib.sha256(self._expected).hexdigest()!=self._binding['expected_semantic_sha256']):_fail('adoption_contract_changed')
        expected_type=rd.LiveGraphReader if self.profile=='azure_public_pilot' else rd.LaboratoryGraphReader
        if type(self._reader) is not expected_type or id(self._reader)!=self._reader_object_id or type(self._preimage) is not rd.CapturedObservation or id(self._preimage)!=self._preimage_object_id:
            _fail('adoption_reader_or_preimage_changed')
        evidence=self._reader.evidence();batch,source=self._preimage.verified()
        for current in (evidence,source):
            if (canonical(current['identity'])!=canonical(self._binding['reader_identity']) or current['identity_observation_sha256']!=self._binding['identity_observation_sha256']
                    or current['evidence_class']!=self._binding['source_evidence_class'] or current['source_authenticity_verified'] is not (self.profile=='azure_public_pilot')):
                _fail('adoption_reader_or_preimage_changed')
        if batch['capture_sha256']!=self._binding['preimage_capture_sha256'] or digest(batch['source']['raw_observed'])!=self._binding['preimage_raw_sha256']:
            _fail('adoption_reader_or_preimage_changed')
    def binding(self):self._fresh();return _copy(self._binding)
    def _match_graph(self,batch):
        if (batch['tenant_id']!=self._binding['tenant_id'] or batch['object_id']!=self._binding['object_id'] or canonical(batch['source']['raw_observed'])!=canonical(self._raw)):_fail('adoption_graph_changed')
    def _match_state(self,raw):
        if type(raw) is not bytes or not 0<len(raw)<=_MAX:_fail('adoption_state_invalid')
        if canonical(parse_json(raw))!=self._expected:_fail('adoption_state_mismatch')
    def _observe(self):
        self._reads+=1
        if self._reads>32:_fail('adoption_observation_limit')
        capture=self._reader.capture(self._binding['object_id'],self._root/('observation-'+str(self._reads).zfill(4)),max_elapsed_seconds=self._binding['max_read_seconds'])
        batch,_,_=wp._validated_capture(capture,self._reader,max_age=self._binding['max_read_seconds']);self._match_graph(batch);return capture
    def admit(self,candidate_raw):
        with self._lock:
            self._fresh()
            if self._phase!='prepared':_fail('adoption_admission_spent')
            self._phase='checking';write_json(self._root/'admission-started.json',{'candidate_sha256':hashlib.sha256(candidate_raw).hexdigest() if type(candidate_raw) is bytes else None,'status':'checking'})
            try:
                self._match_state(candidate_raw);_retain(self._root/'candidate-state.json',candidate_raw);capture=self._observe();batch,_=capture.verified()
                result={'schema_version':'native-adoption-state-admission/1','contract_sha256':self._digest,'body_sha256':hashlib.sha256(candidate_raw).hexdigest(),
                    'candidate_artifact':'candidate-state.json','fresh_capture_sha256':batch['capture_sha256'],'status':'projection_and_graph_matched','execution_authorized':False,'backend_state_authenticated':False,'service_freshness_atomic':False}
                write_json(self._root/'admission-result.json',result);self._phase='admitted';return result
            except BaseException:self._phase='blocked';raise
    def observe_successor(self,candidate_raw,*,revision):
        with self._lock:
            self._fresh();self._match_state(candidate_raw)
            if type(revision) is not StateRevision or StateRevision.observe(candidate_raw,etag=revision.etag)!=revision:_fail('adoption_observation_changed')
            return AdoptionStateObservation(_SEAL,self,candidate_raw,revision,self._observe())
