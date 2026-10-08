"""Coherent read-only adoption/Plan source adapter; never recovers/migrates SQLite."""
from __future__ import annotations
import base64
import hashlib
from pathlib import Path
import time
from . import worker_evidence as c,worker_evidence_domains as d
from .io import digest,parse_json


def packed(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'base64':base64.b64encode(raw).decode()}


def snapshot(job_root,policy_path,req,*,capture_root=None,store_root=None,state_raw=None):
    from . import worker_evidence_posix as h
    req=c.request(req);policy_path=h._private(policy_path);h._outside_repository(policy_path)
    policy=h.load(policy_path,256*1024);c.shape(policy,'schema_version authority_root jobs_root verifier approvers admitted_manifest_sha256')
    if policy['schema_version']!='worker-service-policy/1':c.fail('worker_evidence_worker_policy')
    root=h._private(job_root,directory=True);authority=h._private(policy['authority_root'],directory=True);jobs=h._private(policy['jobs_root'],directory=True)
    if root.parent!=jobs or authority==jobs or authority in jobs.parents or jobs in authority.parents:c.fail('worker_evidence_worker_policy')
    originals={}
    def retained(path,limit=8*1024*1024):
        raw=h.read(path,limit);originals[str(path)]=raw;return raw
    with h.readonly_database(authority/'service.sqlite3') as (db,dbsha):
        h._columns(db,'jobs',['id','root','manifest_sha256','status','cancelled','dispatches','outcome','controller_pid','controller_start'])
        h._columns(db,'consumed',['issuer','nonce','operation_id','manifest_sha256']);h._columns(db,'events',['sequence','job','kind','payload','created_at'])
        def selected(selected_root,selected_req,*,historical_original=False):
            m=parse_json(retained(selected_root/'manifest.json',256*1024));binding=parse_json(retained(selected_root/'policy-binding.json',256*1024))
            c.shape(binding,'policy_sha256');c.hashed(binding['policy_sha256'])
            if digest(m)!=selected_req['manifest_sha256'] or (not historical_original and (digest(m) not in policy['admitted_manifest_sha256'] or binding!={'policy_sha256':digest(policy)})):c.fail('worker_evidence_worker_binding')
            recovery=selected_req['operation_kind']=='adoption_recovery_plan'
            verification=None;original=None
            if recovery:
                h._columns(db,'adoption_recovery_plans',['operation_id','original_operation_id','manifest_sha256','root','status','cancelled','dispatches','outcome','controller_pid','controller_start'])
                row=db.execute('SELECT root,manifest_sha256,status,cancelled,dispatches,outcome,original_operation_id FROM adoption_recovery_plans WHERE operation_id=?',(selected_req['operation_id'],)).fetchone()
                if row is None or row[:2]!=(str(selected_root),selected_req['manifest_sha256']) or row[6]!=m['original_operation_id']:c.fail('worker_evidence_job_registration')
                old=parse_json(retained(selected_root/'original.json',256*1024));c.shape(old,'root manifest_sha256')
                old_root=h._private(old['root'],directory=True)
                if old_root.parent!=jobs or old_root==selected_root or old['manifest_sha256']!=m['original_manifest_sha256']:c.fail('worker_evidence_recovery_original')
                old_manifest=parse_json(retained(old_root/'manifest.json',256*1024))
                old_req=dict(selected_req,operation_kind='state_adoption',original_manifest_sha256=None,operation_id=old_manifest['operation_id'],manifest_sha256=digest(old_manifest),execution_binding_sha256=old_manifest['execution_binding_sha256'],run_binding_sha256=old_manifest['run_binding_sha256'],run_id=old_manifest['run_context']['run_id'],run_attempt=old_manifest['run_context']['run_attempt'])
                original=selected(old_root,old_req,historical_original=True);event_job=m['original_operation_id'];archive=selected_root/'plan-output'
            else:
                row=db.execute('SELECT root,manifest_sha256,status,cancelled,dispatches,outcome FROM jobs WHERE id=?',(selected_req['operation_id'],)).fetchone()
                if row is None or row[:2]!=(str(selected_root),selected_req['manifest_sha256']):c.fail('worker_evidence_job_registration')
                h._columns(db,'adoption_operations',['operation_id','manifest_sha256','verification_id','verification_dispatches','verification_status','verification_outcome'])
                phase=db.execute('SELECT manifest_sha256,verification_id,verification_dispatches,verification_status,verification_outcome FROM adoption_operations WHERE operation_id=?',(selected_req['operation_id'],)).fetchone()
                if phase is None or phase[:2]!=(digest(m),m['verification_operation_id']):c.fail('worker_evidence_adoption_verification')
                verification={'verification_operation_id':phase[1],'dispatches':phase[2],'status':phase[3],'outcome':parse_json(phase[4]) if phase[4] else None}
                event_job=selected_req['operation_id'];archive=selected_root/'verification-plan-output'
            rows=db.execute('SELECT sequence,kind,payload,created_at FROM events WHERE job=? ORDER BY sequence LIMIT 1001',(event_job,)).fetchall()
            if not rows or len(rows)>1000:c.fail('worker_evidence_event_limit')
            events=[{'sequence':r[0],'kind':r[1],'payload':parse_json(r[2]),'created_at':r[3]} for r in rows]
            consumed=db.execute('SELECT issuer,nonce,operation_id,manifest_sha256 FROM consumed WHERE operation_id=?',(selected_req['operation_id'],)).fetchone();transcript=None
            if db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='approval_transcripts'").fetchone():
                h._columns(db,'approval_transcripts',['operation_id','receipt_json','receipt_sha256','consumed_at'])
                approval=db.execute('SELECT receipt_json,receipt_sha256,consumed_at FROM approval_transcripts WHERE operation_id=?',(selected_req['operation_id'],)).fetchone()
                if approval:
                    transcript={'receipt':parse_json(approval[0]),'receipt_sha256':approval[1],'consumed_at':approval[2]}
                    if db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?',(transcript['receipt']['payload']['issuer'],transcript['receipt']['payload']['key_id'])).fetchone():c.fail('worker_evidence_revoked')
            artifacts=None
            if archive.exists() or archive.is_symlink():
                h._private(archive,directory=True)
                if set(p.name for p in archive.iterdir())!={'plan.bin','plan.json','exit.txt','receipt.json'}:c.fail('worker_evidence_domain_archive_scope')
                artifacts={name:packed(retained(archive/name,64 if name=='exit.txt' else 8*1024*1024)) for name in ('plan.bin','plan.json','exit.txt','receipt.json')}
            source=None
            if artifacts is not None:
                source_path=Path(m['host_spec']['source_root'])/'project/components/terraform/intune-policy/main.tf.json'
                source=packed(retained(source_path))
            at=int(time.time())
            result={'schema_version':'worker-evidence-snapshot/2','read_at':at,'manifest':m,'policy_sha256':digest(policy),
                'journal':{'database_sha256':dbsha,'selected_event_count':len(events),'first_sequence':events[0]['sequence'],'last_sequence':events[-1]['sequence'],'events_sha256':digest(events)},
                'job':{'status':row[2],'cancel_requested':bool(row[3]),'dispatches':row[4],'outcome':parse_json(row[5]) if row[5] else None},
                'events':events,'approval':transcript,'consumed':dict(zip(('issuer','nonce','operation_id','manifest_sha256'),consumed)) if consumed else None,
                'capture_provenance':None,'capture':None,'domain_records':{'source_policy':{'reviewed_policy_sha256':binding['policy_sha256'],'current_policy_sha256':digest(policy)},'verification':verification,'original':original,'plan_artifacts':artifacts,'state':packed(retained(state_raw)) if state_raw is not None else None,'source':source}}
            if m['schema_version']=='native-adoption-recovery-plan/2':result['domain_records']['phase_ledger']=_phase_ledger(db,m,original,jobs,retained)
            return result
        value=selected(root,req)
        if capture_root is not None:
            if store_root is None:c.fail('worker_evidence_observation_required')
            value['capture'],captured=h._capture(capture_root,req['tenant_id']);value['capture_provenance']=h._capture_source(store_root,req,captured)
        elif store_root is not None:c.fail('worker_evidence_capture_required')
        for name,raw in originals.items():
            if h.read(name,8*1024*1024)!=raw:c.fail('worker_evidence_source_changed')
        if digest(h.load(policy_path,256*1024))!=digest(policy):c.fail('worker_evidence_source_changed')
        c.validate_snapshot(value,req);return value


def _phase_ledger(db,m,original,jobs,retained):
    from . import worker_evidence_posix as h,worker_evidence_phase as phase
    h._columns(db,'native_lease_recoveries',['original_operation','recovery_operation','issuer','nonce','manifest_sha256','status','response_code','observed_sha256'])
    h._columns(db,'adoption_plan_successors',phase.EDGE.split())
    def edge(op):
        row=db.execute('SELECT '+','.join(phase.EDGE.split())+' FROM adoption_plan_successors WHERE successor_operation_id=?',(op,)).fetchone()
        return dict(zip(phase.EDGE.split(),row)) if row else None
    def release(op):
        row=db.execute('SELECT recovery_operation,manifest_sha256,status,observed_sha256 FROM native_lease_recoveries WHERE original_operation=?',(op,)).fetchone()
        if row is None:c.fail('worker_evidence_phase_release')
        return list(row)
    def record(op):
        row=db.execute('SELECT original_operation_id,manifest_sha256,root,status,cancelled,dispatches,outcome,controller_pid,controller_start FROM adoption_recovery_plans WHERE operation_id=?',(op,)).fetchone()
        if row is None:c.fail('worker_evidence_phase_row')
        root=h._private(row[2],directory=True)
        if root.parent!=jobs:c.fail('worker_evidence_phase_root')
        manifest=parse_json(retained(root/'manifest.json',256*1024))
        if digest(manifest)!=row[1] or manifest.get('operation_id')!=op:c.fail('worker_evidence_phase_manifest')
        used=db.execute('SELECT issuer,nonce,operation_id,manifest_sha256 FROM consumed WHERE operation_id=?',(op,)).fetchone()
        raw=db.execute('SELECT receipt_json,receipt_sha256,consumed_at FROM approval_transcripts WHERE operation_id=?',(op,)).fetchone()
        approval={'receipt':parse_json(raw[0]),'receipt_sha256':raw[1],'consumed_at':raw[2]} if raw else None
        if approval and db.execute('SELECT 1 FROM revoked WHERE issuer=? AND key_id=?',(approval['receipt']['payload']['issuer'],approval['receipt']['payload']['key_id'])).fetchone():c.fail('worker_evidence_revoked')
        return {'manifest':manifest,'row':list(row),'approval':approval,'consumed':dict(zip(('issuer','nonce','operation_id','manifest_sha256'),used)) if used else None}
    selected=m['recovery_binding']['phase'];phase.binding(m,original['manifest'])
    def initial():
        row=db.execute('SELECT verification_id,verification_dispatches,verification_status,verification_outcome FROM adoption_operations WHERE operation_id=?',(original['manifest']['operation_id'],)).fetchone()
        return {'manifest':original['manifest'],'row':list(row) if row else None,'approval':original['approval'],'consumed':original['consumed']}
    selected_record=initial() if selected['kind']=='initial_verification' else record(selected['operation_id'])
    chain=m['recovery_binding']['ancestors'];terminal_id=chain[-1]['prior_operation_id'] if chain else selected['operation_id']
    terminal=initial() if terminal_id==original['manifest']['verification_operation_id'] else record(terminal_id)
    return {'selected':selected_record,'terminal':terminal,'current_edge':edge(m['operation_id']),'current_release':release(selected['operation_id']),
        'ancestors':[{'record':record(link['successor_operation_id']),'edge':edge(link['successor_operation_id']),'release':release(link['prior_operation_id'])} for link in m['recovery_binding']['ancestors']]}
