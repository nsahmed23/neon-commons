"""Typed read-only disposition when interrupted adoption is not observed.

This path cannot import, release a remote lease or claim native import failure.
It releases only the stopped original operation's local scopes after fresh
receiving-state/Graph evidence proves the exact original baseline still exists.
"""
import uuid
from intune_iac import worker_adoption as adoption,worker_service as service,protected
from intune_iac import worker_adoption_recovery as recovery
from intune_iac.io import AppError,canonical,digest,parse_json

def _fail(code):raise AppError(code,'The original baseline was not independently established for the stopped adoption; retain its ownership and unknown outcome.') from None

def _facts(job,completion):
    if type(job) is not adoption.AdoptionJob:_fail('adoption_disposition_original_required')
    expected=recovery.LiveAdoptionRecoveryCompletion if job.manifest['profile']=='azure_public_pilot' else recovery.LaboratoryAdoptionRecoveryCompletion
    if type(completion) is not expected or completion.context.job is not job:_fail('adoption_disposition_completion_required')
    job._check(expiry=False);facts=completion.verified();observed=facts['fresh_observation'];proof=observed['adoption_state_proof'];original=facts['original'];contract=job.manifest['state_contract']
    if (original['operation_id']!=job.identifier or original['manifest_sha256']!=job.sha256 or original['status']!='outcome_unknown'
            or facts['service_authority_root']!=str(job.policy.root) or original['scopes']!=service._scopes(job.manifest)
            or facts['lease_independently_unlocked'] is not True or facts['lock_metadata_remaining'] is not False
            or observed['locked'] is not False or observed['metadata']!={} or proof['classification']!='original_baseline'
            or proof['graph_unchanged'] is not True or proof['actor_attribution']!='unestablished'
            or proof['original_contract_sha256']!=digest(contract) or proof['original_baseline_sha256']!=contract['baseline_sha256']
            or proof['original_preimage_capture_sha256']!=contract['preimage_capture_sha256']
            or proof['original_preimage_raw_sha256']!=contract['preimage_raw_sha256'] or proof['fresh_raw_sha256']!=contract['preimage_raw_sha256']
            or proof['reader_identity_sha256']!=contract['reader_identity_sha256']
            or {k:v for k,v in observed['state'].items() if k!='etag'}!={k:v for k,v in contract['baseline_revision'].items() if k!='etag'}):
        _fail('adoption_disposition_baseline_not_established')
    return facts

def reconcile_baseline(job,completion):
    """Atomically retain unknown attribution and release only original scopes."""
    facts=_facts(job,completion);original=facts['original']
    with job.policy.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT status,cancelled,dispatches,outcome,controller_pid,controller_start FROM jobs WHERE id=?',(job.identifier,)).fetchone()
        consumed=db.execute('SELECT manifest_sha256 FROM consumed WHERE operation_id=?',(job.identifier,)).fetchone()
        scopes=sorted(r[0] for r in db.execute('SELECT scope FROM ownership WHERE job=?',(job.identifier,)))
        phase=db.execute('SELECT verification_dispatches,verification_status FROM adoption_operations WHERE operation_id=?',(job.identifier,)).fetchone()
        plan_table=db.execute("SELECT type FROM sqlite_master WHERE name='adoption_recovery_plans'").fetchone()
        if plan_table is not None:
            if plan_table!=('table',):_fail('adoption_disposition_plan_schema')
            if db.execute('SELECT 1 FROM adoption_recovery_plans WHERE original_operation_id=? LIMIT 1',(job.identifier,)).fetchone():
                _fail('adoption_disposition_successor_plan_exists')
        if (row is None or row[0]!='outcome_unknown' or row[2]!=1 or row[4] is not None or row[5] is not None
                or consumed!=(job.sha256,) or scopes!=original['scopes'] or phase!=(0,'not_started')
                or digest(parse_json(row[3]))!=original['outcome_sha256']):_fail('adoption_disposition_original_changed')
        # The completion's fresh capture, exact receiving bytes, original once
        # row and private artifacts must remain valid immediately before write.
        if _facts(job,completion)!=facts:_fail('adoption_disposition_completion_changed')
        prior=parse_json(row[3]);report={'schema_version':'adoption-baseline-disposition/1','classification':'adoption_not_observed_execution_unknown',
            'previous_import_outcome':prior,'original_import_status':row[0],'original_import_dispatches':row[2],
            'independent_completion':facts,'reservation_released':True,'import_replayed':False,'import_retry_authorized':False,
            'graph_mutated':False,'state_mutated':False,'remote_lease_action':False,'actor_attribution':'unestablished',
            'future_adoption_requires':'new independently approved operation and fresh complete ownership admission',
            'endpoint_effectiveness':'unestablished','platform_qualified':False,'production_approved':False}
        db.execute('UPDATE jobs SET status=?,outcome=? WHERE id=?',('adoption_not_observed_execution_unknown',canonical(report).decode(),job.identifier))
        db.execute('DELETE FROM ownership WHERE job=?',(job.identifier,))
        job.policy.event(db,job.identifier,'adoption_baseline_independently_disposed',report);db.execute('COMMIT')
    protected._sync(job.policy.root)
    try:protected._exclusive(job.root/('adoption-baseline-disposition-'+uuid.uuid4().hex+'.json'),canonical(report))
    except BaseException as error:
        try:
            with job.policy.connection() as db:job.policy.event(db,job.identifier,'adoption_baseline_disposition_archive_failed',{
                'error':getattr(error,'code',type(error).__name__),'known_disposition_preserved':True,'import_retry_authorized':False})
        except BaseException as secondary:
            error.add_note('Secondary adoption disposition failure recording: '+str(getattr(secondary,'code',type(secondary).__name__)))
            if isinstance(secondary,(KeyboardInterrupt,SystemExit)):raise secondary from error
        raise
    try:return job.status()
    except BaseException as error:
        error.add_note('Baseline disposition transaction committed; reattach read-only. Import replay remains forbidden.')
        raise
