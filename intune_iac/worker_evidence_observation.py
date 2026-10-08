"""Pure Plan-v3 observation facts. No lease release or runtime capability."""
from pathlib import PurePosixPath
import hashlib
from . import worker_evidence as c
from .io import canonical,digest,parse_json
VERSION='native-adoption-recovery-plan/3'
KIND='unacquired_phase_observation'
CLASSIFICATION='no_native_backend_dispatch_observed_execution_unknown'
EDGE='successor_operation_id original_operation_id successor_manifest_sha256 prior_operation_id prior_manifest_sha256 observation_id anchor_sha256 prior_phase_json'
LINK='resolution_kind successor_operation_id successor_manifest_sha256 prior_operation_id prior_manifest_sha256 observation_id anchor_sha256 prior_phase_sha256 observation_row'
ROW='observation_id original_operation_id phase_operation_id phase_manifest_sha256 anchor_sha256 anchor_path'
FRESH='schema_version profile original identity backend_target identity_binding_sha256 state metadata locked adoption_state_proof adoption_capture state_artifact_sha256 observed_at storage_binding_sha256 classification release_performed execution_authorized platform_qualified'
PROJECTION='classification original_contract_sha256 original_expected_semantic_sha256 original_baseline_sha256 original_preimage_capture_sha256 original_preimage_raw_sha256 fresh_raw_sha256 reader_identity_sha256'


def stable(value):
    if type(value) is not dict:c.fail('worker_evidence_observation_original')
    return {key:item for key,item in value.items() if key!='policy_sha256'}


def path(value):
    if type(value) is not str or not PurePosixPath(value).is_absolute() or '..' in PurePosixPath(value).parts:c.fail('worker_evidence_observation_path')


def ids(binding):
    if binding['resolution_kind']!=KIND:c.fail('worker_evidence_observation_kind')
    c.identifier(binding['observation_id']);c.hashed(binding['anchor_sha256'])
    return binding['observation_id'],binding['anchor_sha256']


def row(value,manifest):
    b=manifest['recovery_binding'];p=b['phase'];identifier,sha=ids(b)
    if type(value) is not list or len(value)!=6 or value[:5]!=[identifier,manifest['original_operation_id'],p['operation_id'],p['manifest_sha256'],sha]:c.fail('worker_evidence_observation_row')
    path(value[5]);return value


def anchor(entry,manifest,at):
    from .worker_evidence_domains import member
    c.shape(entry,'row anchor');observed=row(entry['row'],manifest);raw=member(entry['anchor'])
    if hashlib.sha256(raw).hexdigest()!=observed[4]:c.fail('worker_evidence_observation_anchor_hash')
    a=parse_json(raw);c.shape(a,'schema_version observation_id classification service_authority_root original initial_observation implementation_files')
    if (a['schema_version']!='adoption-plan-unacquired-anchor/1' or a['observation_id']!=observed[0] or a['classification']!=CLASSIFICATION
        or canonical(stable(a['original']))!=canonical(stable(manifest['original_facts']))):c.fail('worker_evidence_observation_anchor')
    path(a['service_authority_root']);c.hashed(a['original']['policy_sha256'])
    inventory=a['implementation_files']
    if type(inventory) is not dict or not 1<=len(inventory)<=4096:c.fail('worker_evidence_observation_inventory')
    for name,sha in inventory.items():
        if type(name) is not str or not name or len(name)>4096:c.fail('worker_evidence_observation_inventory')
        c.hashed(sha)
    c.shape(a['initial_observation'],FRESH)
    if canonical(a['initial_observation']['original'])!=canonical(a['original']):c.fail('worker_evidence_observation_original')
    fresh(a['initial_observation'],manifest,at)
    return a


def fresh(fresh,manifest,at,*,allow_completed_rebind=False):
    c.shape(fresh,FRESH)
    expected_profile='azure_public_unacquired_adoption_plan' if manifest['profile']=='azure_public_pilot' else 'laboratory_unacquired_adoption_plan'
    if (fresh['schema_version']!='adoption-plan-unacquired-fresh-observation/1' or fresh['profile']!=expected_profile
        or fresh['classification']!=CLASSIFICATION or fresh['locked'] is not False or type(fresh['metadata']) is not dict or fresh['metadata']
        or any(fresh[key] is not False for key in ('release_performed','execution_authorized','platform_qualified'))
        or canonical(stable(fresh['original']))!=canonical(stable(manifest['original_facts']))):c.fail('worker_evidence_observation_fresh')
    for key in ('identity_binding_sha256','state_artifact_sha256','storage_binding_sha256'):c.hashed(fresh[key])
    c.number(fresh['observed_at'],1,at+5)
    state=fresh['state'];c.shape(state,'lineage serial sha256 semantic_sha256 etag bytes');c.identifier(state['lineage']);c.number(state['serial'],0,9007199254740991);c.number(state['bytes'],1,16*1024*1024)
    for key in ('sha256','semantic_sha256'):c.hashed(state[key])
    if type(state['etag']) is not str or not state['etag'] or len(state['etag'])>1024 or fresh['state_artifact_sha256']!=state['sha256']:c.fail('worker_evidence_observation_state')
    # ETag can change after a later independent read; exact content/revision cannot.
    selected=manifest['recovery_binding']['state'];c.shape(selected,'lineage serial sha256 semantic_sha256 etag bytes')
    if type(selected['etag']) is not str or not selected['etag'] or len(selected['etag'])>1024:c.fail('worker_evidence_observation_state')
    if type(selected) is not dict or canonical({k:v for k,v in state.items() if k!='etag'})!=canonical({k:v for k,v in selected.items() if k!='etag'}):c.fail('worker_evidence_observation_state')
    capture=fresh['adoption_capture'];c.shape(capture,'capture_sha256 path');c.hashed(capture['capture_sha256']);path(capture['path'])
    proof=fresh['adoption_state_proof']
    if (type(proof) is not dict or proof.get('classification')!='approved_adoption_successor' or proof.get('graph_unchanged') is not True
        or proof.get('original_contract_sha256')!=manifest['recovery_binding']['original_contract_sha256']):c.fail('worker_evidence_observation_projection')
    try:projection={key:proof[key] for key in PROJECTION.split()}
    except KeyError:c.fail('worker_evidence_observation_projection')
    if digest(projection)!=manifest['recovery_binding']['projection_sha256']:c.fail('worker_evidence_observation_projection')
    declared=manifest['provider_binding']['backend']
    if (canonical(fresh['identity'])!=canonical(declared['identity']) or canonical(fresh['backend_target'])!=canonical(declared['backend'])
        or (not allow_completed_rebind and fresh['identity_binding_sha256']!=manifest['identity_binding_sha256']) or fresh['storage_binding_sha256']!=manifest['storage_binding_sha256']
        or any(canonical(fresh['backend_target'].get(key))!=canonical(state[field]) for key,field in [('state_lineage','lineage'),('state_serial','serial'),('state_sha256','sha256')])):c.fail('worker_evidence_observation_identity')
    return fresh


def edge(value,manifest):
    c.shape(value,EDGE);b=manifest['recovery_binding'];p=b['phase'];identifier,sha=ids(b)
    expected={'successor_operation_id':manifest['operation_id'],'original_operation_id':manifest['original_operation_id'],'successor_manifest_sha256':digest(manifest),
        'prior_operation_id':p['operation_id'],'prior_manifest_sha256':p['manifest_sha256'],'observation_id':identifier,'anchor_sha256':sha}
    if any(value[key]!=item for key,item in expected.items()) or type(value['prior_phase_json']) is not str or canonical(parse_json(value['prior_phase_json']))!=canonical(manifest['original_facts']):c.fail('worker_evidence_observation_edge')


def completed(facts,manifest,ledger,at):
    c.shape(facts,'schema_version profile classification observation_id anchor_sha256 anchor_path anchor_row original service_authority_root fresh_observation fresh_observation_sha256 initial_state_etag current_state_etag etag_changed_since_assessment etag_change_cause lease_independently_unlocked lock_metadata_remaining release_performed ownership_release_authorized platform_qualified production_approved')
    a=anchor(ledger['current_observation'],manifest,at);b=manifest['recovery_binding'];observed=fresh(facts['fresh_observation'],manifest,at,allow_completed_rebind=True)
    if (facts['schema_version']!='adoption-plan-unacquired-observation/1' or facts['classification']!=CLASSIFICATION or facts['profile']!=observed['profile']
        or facts['observation_id']!=b['observation_id'] or facts['anchor_sha256']!=b['anchor_sha256'] or facts['anchor_path']!=ledger['current_observation']['row'][5]
        or canonical(facts['anchor_row'])!=canonical(ledger['current_observation']['row']) or facts['service_authority_root']!=a['service_authority_root']
        or canonical(facts['original'])!=canonical(observed['original']) or facts['fresh_observation_sha256']!=digest(observed)
        or facts['lease_independently_unlocked'] is not True
        or any(facts[key] is not False for key in ('lock_metadata_remaining','release_performed','ownership_release_authorized','platform_qualified','production_approved'))):c.fail('worker_evidence_observation_completion')
    initial=a['initial_observation']['state']['etag'];current=observed['state']['etag'];changed=initial!=current
    if facts['initial_state_etag']!=initial or facts['current_state_etag']!=current or facts['etag_changed_since_assessment'] is not changed or facts['etag_change_cause']!=('unestablished' if changed else 'unchanged'):c.fail('worker_evidence_observation_etag')
    return facts
