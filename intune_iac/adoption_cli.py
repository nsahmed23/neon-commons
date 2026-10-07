"""Text-only review/control of adoption; no caller can deserialize a runtime."""
from intune_iac.host_capabilities import require_profile
from intune_iac.io import AppError

ACTIONS = ('review', 'status', 'attach', 'cancel', 'recover')


def add_parser(commands):
    parser = commands.add_parser('adoption', help='Prepare or inspect a separately approved state-only native import')
    routes = parser.add_subparsers(dest='adoption_command', required=True)
    for name in ('prepare', *ACTIONS, 'recovery-plan-prepare', *('recovery-plan-' + action for action in ACTIONS)):
        route = routes.add_parser(name)
        route.add_argument('--job-root', required=True)
        route.add_argument('--policy', required=True)
        if name in ('prepare', 'recovery-plan-prepare'): route.add_argument('--manifest', required=True)
        if name == 'recovery-plan-prepare': route.add_argument('--original-job-root', required=True)


def invoke(action, job_root, policy_path, *, tenant_id=None, object_id=None):
    require_profile('protected_worker')
    if action not in ACTIONS: raise AppError('adoption_interface_action', 'Use a declared adoption review or recovery command.')
    from intune_iac.worker_adoption import AdoptionJob
    job = AdoptionJob(job_root, policy_path)
    if ((tenant_id is not None and job.manifest['tenant_id'] != tenant_id)
            or (object_id is not None and object_id not in job.manifest['object_ids'])):
        raise AppError('adoption_workspace_target_mismatch', 'The adoption job does not match the active tenant and selected object.')
    result = getattr(job, action)()
    return dict(result, operation_id=job.identifier, tenant_id=job.manifest['tenant_id'],
        object_ids=job.manifest['object_ids'], profile=job.manifest['profile'],
        adoption_job_root=str(job.root), adoption_policy=str(policy_path),
        evidence_class='protected_adoption_journal', interface_action=action,
        terminal_dispatches_mutation=False, platform_qualified=False)


def command(args):
    require_profile('protected_worker')
    if args.adoption_command.startswith('recovery-plan-'):
        from intune_iac.worker_adoption_reconcile import RecoveryPlanJob, prepare_job as prepare_recovery_plan
        action = args.adoption_command.removeprefix('recovery-plan-')
        if action == 'prepare':
            from intune_iac.worker_service import _bounded_private_json
            from intune_iac.worker_adoption import AdoptionJob
            original = AdoptionJob(args.original_job_root, args.policy)
            return prepare_recovery_plan(args.job_root, original=original, manifest=_bounded_private_json(args.manifest), policy_path=args.policy)
        return invoke_plan(action, args.job_root, args.policy)
    if args.adoption_command == 'prepare':
        from intune_iac.worker_service import _bounded_private_json
        from intune_iac.worker_adoption import prepare_job
        return prepare_job(args.job_root, manifest=_bounded_private_json(args.manifest), policy_path=args.policy)
    return invoke(args.adoption_command, args.job_root, args.policy)


def invoke_plan(action, job_root, policy_path, *, tenant_id=None, object_id=None):
    require_profile('protected_worker')
    if action not in ACTIONS: raise AppError('adoption_interface_action', 'Use a declared Plan review or recovery command.')
    from intune_iac.worker_adoption_reconcile import RecoveryPlanJob
    job = RecoveryPlanJob(job_root, policy_path)
    original = job.original.manifest
    if ((tenant_id is not None and original['tenant_id'] != tenant_id)
            or (object_id is not None and object_id not in original['object_ids'])):
        raise AppError('adoption_workspace_target_mismatch', 'The Plan review does not match the active tenant and selected object.')
    result = getattr(job, action)()
    return dict(result, operation_id=job.identifier, tenant_id=original['tenant_id'], object_ids=original['object_ids'],
        profile=job.manifest['profile'], adoption_plan_job_root=str(job.root), adoption_plan_policy=str(policy_path),
        evidence_class='protected_adoption_recovery_plan_journal', interface_action=action,
        terminal_dispatches_mutation=False, import_replay_authorized=False, platform_qualified=False)
