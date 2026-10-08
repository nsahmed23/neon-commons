"""Inactive native evidence-access contract for the existing four-view engine.

SQLite snapshots and guarded raw captures use the existing native store. This
module does not reinterpret POSIX maintenance/protected-worker journals or
promote imported metadata into a verified deployment. Ordinary Windows remains
unsupported pending native qualification; every unsupported link stays visible.
"""
from .windows_workbench import WindowsWorkbenchStore
from .io import AppError,canonical


class _NativeViewReader:
    def __init__(self):self.issues=[]
    def reject(self,kind,*,row=None):
        evidence=row.get('data',{}).get('evidence_class') if row is not None else None
        reason=('native_protected_adoption_journal_unsupported' if evidence=='linked_protected_adoption'
                else 'native_protected_service_journal_unsupported' if evidence=='linked_protected_service'
                else 'native_modeled_execution_journal_unsupported' if evidence=='verified_local_modeled_deployment'
                else 'native_selected_operation_journal_unsupported' if kind=='proposed_operation'
                else 'deployment_claim_not_independently_verified')
        item={'status':'UNSUPPORTED','purpose':kind,'reason':reason,'path_opened':False,
              'baseline_admissible':False,'cloud_authority':False,'execution_authorized':False}
        if row is not None:item.update(artifact_id=row['artifact_id'],evidence_class=evidence)
        self.issues.append(item)
        return {'status':'unknown','reason':reason,'evidence_access':item,
                'unresolved_risks':['Required execution journal must be read on its qualified execution host; a stored link or caller label is insufficient.']}
    def decorate(self,result):
        result['native_evidence_access']={'profile':'inactive_native_store_inspection',
            'stored_repository_snapshot':'preserved_with_separate_current_source_readback',
            'stored_ownership_and_refresh':'caller_assertions_with_original_scope',
            'observation':'guarded_native_store_and_capture_readback',
            'execution_journals':'direct_host_access_unsupported','received_signed_worker_snapshots':'reverify_exact_bytes_current_trust_and_pinned_native_verifier','issues':self.issues,
            'current_repository_resolution_implemented':True,'platform_qualified':False,'workbench_profile_enabled':False}
        if result.get('repository',{}).get('status')=='recorded':
            from .windows_repository import readback_windows_repository
            try:readback=readback_windows_repository(result['repository'])
            except AppError as error:
                readback={'status':'unknown','reason':error.code,
                    'recorded_revision_and_source_hashes_preserved':True,'git_revision_verified':False}
            result['repository']['current_working_source_readback']=readback
        if self.issues and result.get('deployment',{}).get('reason')=='verified_deployment_missing':
            result['deployment']['reason']='required_deployment_evidence_unsupported_or_unverified'
        if len(canonical(result))>16*1024*1024:
            raise AppError('workbench_views_bound','Native view evidence exceeds the existing output bound.')
        return result


def _reader_for(store):
    # No caller flag, subclass or persisted metadata selects native support.
    return _NativeViewReader() if type(store) is WindowsWorkbenchStore else None
