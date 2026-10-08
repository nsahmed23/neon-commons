"""Closed read-only Plan-v2 phase history; never constructs a recovery permit."""
from pathlib import PurePosixPath
from . import worker_evidence as c,worker_evidence_observation as o
from .io import canonical,digest,parse_json
VERSION='native-adoption-recovery-plan/2'
EDGE='successor_operation_id original_operation_id successor_manifest_sha256 prior_operation_id prior_manifest_sha256 recovery_operation_id recovery_manifest_sha256 prior_phase_json'
FACTS='operation_id manifest_sha256 status cancelled outcome_sha256 scopes phase_kind phase_operation_id phase_manifest_sha256 phase_job_root phase_status phase_cancelled phase_outcome_sha256 phase_row_sha256 initial_verification_row_sha256 verification_operation_id policy_sha256 original_host phase_host original_import_journal_sha256 original_import_state_write broker_journal_sha256 host_run_manifest_sha256 host_run_receipt_sha256 lease_id lock recorded_metadata state_contract_sha256 state_write_attempts'
LINK='successor_operation_id successor_manifest_sha256 prior_operation_id prior_manifest_sha256 recovery_operation_id recovery_manifest_sha256 prior_phase_sha256 release_row'


def release(row,op,sha):
    if type(row) is not list or len(row)!=4 or row[:2]!=[op,sha] or row[2] not in ('release_observed','release_observed_execution_unknown'):c.fail('worker_evidence_phase_release')
    c.hashed(row[3])


def binding(m,original):
    b=m['recovery_binding'];p=b['phase'];f=m['original_facts'];c.shape(p,'kind operation_id manifest_sha256 job_root');observed=m['schema_version']==o.VERSION;c.shape(f,' '.join(k for k in FACTS.split() if k not in ('lease_id','lock','recorded_metadata','state_write_attempts'))+' broker_inspection_sha256 backend_attempt_count native_lease_request_count state_write_attempt_count' if observed else FACTS)
    if p['kind'] not in ('initial_verification','recovery_plan'):c.fail('worker_evidence_phase_kind')
    c.identifier(p['operation_id']);c.hashed(p['manifest_sha256'])
    if type(p['job_root']) is not str or not PurePosixPath(p['job_root']).is_absolute() or '..' in PurePosixPath(p['job_root']).parts:c.fail('worker_evidence_phase_root')
    if (f['operation_id']!=original['operation_id'] or f['manifest_sha256']!=digest(original) or f['verification_operation_id']!=original['verification_operation_id']
        or any(f[a]!=p[z] for a,z in [('phase_kind','kind'),('phase_operation_id','operation_id'),('phase_manifest_sha256','manifest_sha256'),('phase_job_root','job_root')])):c.fail('worker_evidence_phase_original')
    for key in ('outcome_sha256','phase_outcome_sha256','phase_row_sha256','initial_verification_row_sha256','policy_sha256','original_import_journal_sha256','broker_journal_sha256','host_run_manifest_sha256','host_run_receipt_sha256','state_contract_sha256'):c.hashed(f[key])
    if f['state_contract_sha256']!=digest(original['state_contract']):c.fail('worker_evidence_phase_original')
    if observed:
        c.hashed(f['broker_inspection_sha256'])
        if any(type(f[k]) is not int or f[k]!=0 for k in ('backend_attempt_count','native_lease_request_count','state_write_attempt_count')):c.fail('worker_evidence_observation_attempts')
    else:c.identifier(f['lease_id'])
    for key in ('cancelled','phase_cancelled'):
        if type(f[key]) is not bool:c.fail('worker_evidence_phase_facts')
    if (f['status'] not in ('outcome_unknown','import_host_completed_unverified','first_plan_host_completed_unverified') or f['phase_status'] not in ('outcome_unknown','first_plan_host_completed_unverified','plan_host_completed_unverified')
        or type(f['scopes']) is not list or not f['scopes'] or len(f['scopes'])!=len(set(f['scopes']))):c.fail('worker_evidence_phase_facts')
    for item in f['scopes']:c.hashed(item)
    for key in (('original_host','phase_host','original_import_state_write') if observed else ('original_host','phase_host','original_import_state_write','lock')):
        if type(f[key]) is not dict:c.fail('worker_evidence_phase_facts')
    for key in (() if observed else ('recorded_metadata','state_write_attempts')):
        if type(f[key]) is not list:c.fail('worker_evidence_phase_facts')
    if p['kind']=='initial_verification' and (p['operation_id']!=original['verification_operation_id'] or p['manifest_sha256']!=digest(original)):c.fail('worker_evidence_phase_initial')
    if p['operation_id']==m['operation_id']:c.fail('worker_evidence_phase_cycle')
    chain=b['ancestors']
    if type(chain) is not list or len(chain)>=32:c.fail('worker_evidence_phase_limit')
    seen={m['operation_id']};current=p['operation_id']
    for link in chain:
        obs=type(link) is dict and link.get('resolution_kind')==o.KIND
        c.shape(link,o.LINK if obs else LINK)
        for key in ('successor_operation_id','prior_operation_id', 'observation_id' if obs else 'recovery_operation_id'):c.identifier(link[key])
        for key in ('successor_manifest_sha256','prior_manifest_sha256','anchor_sha256' if obs else 'recovery_manifest_sha256','prior_phase_sha256'):c.hashed(link[key])
        if link['successor_operation_id']!=current or current in seen or link['prior_operation_id'] in seen|{current}:c.fail('worker_evidence_phase_cycle')
        if obs:
            r=link['observation_row']
            if type(r) is not list or len(r)!=6 or r[:5]!=[link['observation_id'],original['operation_id'],link['prior_operation_id'],link['prior_manifest_sha256'],link['anchor_sha256']]:c.fail('worker_evidence_observation_row')
            o.path(r[5])
        else:release(link['release_row'],link['recovery_operation_id'],link['recovery_manifest_sha256'])
        seen.add(current);current=link['prior_operation_id']
    return p


def edge(value,m):
    c.shape(value,EDGE);b=m['recovery_binding'];p=b['phase']
    expected={'successor_operation_id':m['operation_id'],'original_operation_id':m['original_operation_id'],'successor_manifest_sha256':digest(m),
        'prior_operation_id':p['operation_id'],'prior_manifest_sha256':p['manifest_sha256'],'recovery_operation_id':b['recovery_operation_id'],'recovery_manifest_sha256':b['recovery_manifest_sha256']}
    if any(value[key]!=item for key,item in expected.items()) or type(value['prior_phase_json']) is not str or canonical(parse_json(value['prior_phase_json']))!=canonical(m['original_facts']):c.fail('worker_evidence_phase_edge')


def record(value,original,at,op,sha):
    from . import worker_evidence_domains as d
    c.shape(value,'manifest row approval consumed');m=value['manifest'];row=value['row']
    if type(m) is not dict or m.get('schema_version') not in (d.RECOVERY,VERSION,o.VERSION) or m.get('operation_id')!=op or digest(m)!=sha:c.fail('worker_evidence_phase_manifest')
    if type(row) is not list or len(row)!=9 or row[:2]!=[original['operation_id'],sha] or row[3] not in ('outcome_unknown','plan_host_completed_unverified') or type(row[4]) is not int or row[4] not in (0,1) or type(row[5]) is not int or row[5]!=1 or row[7:]!=[None,None] or type(row[6]) is not str:c.fail('worker_evidence_phase_row')
    # This request-shaped parser input grants no trust or execution authority.
    req=d.make_request(m,{'readonly_shape_only':True},'0'*32);d.manifest(m,req,at,original)
    used=value['consumed'];c.shape(used,'issuer nonce operation_id manifest_sha256')
    if used['operation_id']!=op or used['manifest_sha256']!=sha:c.fail('worker_evidence_phase_consumed')
    return m


def phase_record(child,entry,s,*,terminal=False):
    original=s['domain_records']['original'];m=original['manifest'];p=child['recovery_binding']['phase']
    c.shape(entry,'manifest row approval consumed');row=entry['row']
    if p['kind']=='initial_verification':
        if (canonical(entry['manifest'])!=canonical(m) or type(row) is not list or len(row)!=4
            or row[0]!=m['verification_operation_id'] or type(row[1]) is not int or row[1]!=1
            or row[2] not in ('outcome_unknown','first_plan_host_completed_unverified') or type(row[3]) is not str):c.fail('worker_evidence_phase_initial')
        if (canonical(entry['approval'])!=canonical(original['approval']) or canonical(entry['consumed'])!=canonical(original['consumed'])
            or canonical({'verification_operation_id':row[0],'dispatches':row[1],'status':row[2],'outcome':parse_json(row[3])})!=canonical(original['domain_records']['verification'])
            or original['job']['dispatches']!=1):c.fail('worker_evidence_phase_initial')
    else:
        predecessor=record(entry,m,s['read_at'],p['operation_id'],p['manifest_sha256'])
        if row[2]!=p['job_root']:c.fail('worker_evidence_phase_root')
        if terminal and predecessor['schema_version'] in (VERSION,o.VERSION):c.fail('worker_evidence_phase_chain_terminal')
    if digest(row)!=child['original_facts']['phase_row_sha256']:c.fail('worker_evidence_phase_row_changed')


def validate(s):
    m=s['manifest'];original=s['domain_records']['original']['manifest'];b=m['recovery_binding'];p=binding(m,original)
    ledger=s['domain_records']['phase_ledger'];c.shape(ledger,'selected current_edge '+('current_observation' if m['schema_version']==o.VERSION else 'current_release')+' ancestors terminal');selected=ledger['selected']
    phase_record(m,selected,s)
    if m['schema_version']==o.VERSION:o.anchor(ledger['current_observation'],m,s['read_at'])
    else:release(ledger['current_release'],b['recovery_operation_id'],b['recovery_manifest_sha256'])
    if s['job']['dispatches']==1:(o.edge if m['schema_version']==o.VERSION else edge)(ledger['current_edge'],m)
    elif ledger['current_edge'] is not None:c.fail('worker_evidence_phase_unconsumed_edge')
    if type(ledger['ancestors']) is not list or len(ledger['ancestors'])!=len(b['ancestors']):c.fail('worker_evidence_phase_ancestors')
    child=m
    for i,(entry,declared) in enumerate(zip(ledger['ancestors'],b['ancestors'])):
        obs=type(declared) is dict and declared.get('resolution_kind')==o.KIND
        c.shape(entry,'record edge '+('observation' if obs else 'release'))
        prior=record(entry['record'],original,s['read_at'],declared['successor_operation_id'],declared['successor_manifest_sha256'])
        if prior['schema_version']!=(o.VERSION if obs else VERSION):c.fail('worker_evidence_phase_ancestor_version')
        if digest(entry['record']['row'])!=child['original_facts']['phase_row_sha256'] or (i==0 and canonical(entry['record'])!=canonical(selected)):c.fail('worker_evidence_phase_row_changed')
        (o.edge if obs else edge)(entry['edge'],prior);observed=entry['edge']
        keys=('successor_operation_id','successor_manifest_sha256','prior_operation_id','prior_manifest_sha256')+ (('observation_id','anchor_sha256') if obs else ('recovery_operation_id','recovery_manifest_sha256'))
        if obs:
            o.anchor(entry['observation'],prior,s['read_at'])
            if canonical(entry['observation']['row'])!=canonical(declared['observation_row']):c.fail('worker_evidence_observation_row')
        else:
            release(entry['release'],declared['recovery_operation_id'],declared['recovery_manifest_sha256'])
            if canonical(entry['release'])!=canonical(declared['release_row']):c.fail('worker_evidence_phase_ancestor_binding')
        if any(observed[key]!=declared[key] for key in keys) or digest(parse_json(observed['prior_phase_json']))!=declared['prior_phase_sha256'] or canonical(prior['recovery_binding']['ancestors'])!=canonical(b['ancestors'][i+1:]):c.fail('worker_evidence_phase_ancestor_binding')
        child=prior
    phase_record(child,ledger['terminal'],s,terminal=True)
    if not ledger['ancestors'] and canonical(ledger['terminal'])!=canonical(selected):c.fail('worker_evidence_phase_chain_terminal')
    return ledger


def approvals(s,req,policy,verify):
    from . import worker_evidence_domains as d
    ledger=validate(s);seen=set();records=[e['record'] for e in ledger['ancestors']]
    if ledger['terminal']['manifest']['schema_version']!=d.ADOPTION:records.append(ledger['terminal'])
    if s['manifest']['recovery_binding']['phase']['kind']=='recovery_plan':records.insert(0,ledger['selected'])
    for entry in records:
        m=entry['manifest']
        if m['operation_id'] in seen:continue
        seen.add(m['operation_id']);oldreq=d.make_request(m,policy,req['nonce']);version={VERSION:'2',o.VERSION:'3',d.RECOVERY:'1'}[m['schema_version']]
        minimal={'manifest':m,'read_at':s['read_at'],'approval':entry['approval'],'consumed':entry['consumed'],'events':s['events'],'job':{'dispatches':entry['row'][5]}}
        result=c.approval_transcript(minimal,oldreq,policy,verify,schema='signed-native-adoption-recovery-plan-approval/'+version,domain=('intune-workbench:native-adoption-recovery-plan-approval:v'+version+'\x00').encode(),dispatch_kind='adoption_recovery_plan_consumed',selected_operation=True)
        if result!='verified_retained_original':return 'predecessor_plan_approval_not_retained'
    return 'verified_retained_original'
