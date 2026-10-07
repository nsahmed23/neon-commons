"""Preparation and durable observation of the separately protected service.

No JSON, text command or UI input can construct the process-held execution
runtime. Apply remains the trusted service controller's explicit operation.
"""
from .host_capabilities import require_profile
from .io import AppError

READ_ACTIONS = ('review', 'status', 'attach')
ACTIONS = (*READ_ACTIONS, 'cancel', 'recover')


def invoke(action, job_root, policy_path, *, tenant_id=None, object_id=None):
    require_profile('protected_worker')
    if action not in ACTIONS:
        raise AppError('service_interface_action', 'Use a declared service observation or recovery command.')
    from .worker_service import ServiceJob
    job = ServiceJob(job_root, policy_path)
    if ((tenant_id is not None and job.manifest['tenant_id'] != tenant_id) or
            (object_id is not None and object_id not in job.manifest['object_ids'])):
        raise AppError('service_workspace_target_mismatch', 'The service job does not match the active tenant and selected object.')
    result = getattr(job, action)()
    return dict(result, operation_id=job.identifier, tenant_id=job.manifest['tenant_id'],
                object_ids=job.manifest['object_ids'], profile=job.manifest['profile'],
                saved_plan_sha256=job.manifest['saved_plan_sha256'], expires_at=job.manifest['expires_at'],
                service_job_root=str(job.root), service_policy=str(policy_path),
                evidence_class='protected_service_journal', interface_action=action,
                terminal_dispatches_mutation=False, platform_qualified=False)


def command(args):
    require_profile('protected_worker')
    if args.service_command == 'prepare':
        from .worker_service import prepare_job, _bounded_private_json
        return prepare_job(args.job_root, manifest=_bounded_private_json(args.manifest), policy_path=args.policy)
    return invoke(args.service_command, args.job_root, args.policy)
