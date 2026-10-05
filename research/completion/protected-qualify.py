#!/usr/bin/env python3
"""Replay the pinned local-only native qualification; never performs cloud IO."""
import argparse
import hashlib
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from intune_iac import protected as protected
from intune_iac.io import canonical,parse_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--executable',required=True,type=Path)
    args=parser.parse_args()
    output=Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='protected-native-qualification-') as temporary:
        root=Path(temporary)
        executor=protected.create_native_local_executor(root/'fixture',executable=args.executable,
            initial_value={},desired_value={'policy_hash':'synthetic-value-no-cloud'})
        request=protected.prepare_native_operation(executor)
        raw=(executor.root/'work/plan.json').read_bytes()
        (output/'protected-native-plan.json').write_bytes(raw)
        generic=protected.review_plan(dict(parse_json(raw),resource_changes=[]))
        approval=protected.approve_native_local_operation(request,executor=executor)
        result=protected.execute_native_operation(request,root/'receipts',executor=executor,approval=approval)
        history=protected.read_native_operation(request['operation_id'],root/'receipts')
        observation=protected.reconcile_native_operation(request['operation_id'],root/'receipts',executor=executor)
        assert result['status']=='succeeded_verified',result
        assert observation['classification']=='desired_state_observed',observation
        report={'schema_version':'protected-native-qualification/1.0',
            'scope':'actual_pinned_opentofu_linux_local_output_only','cloud_operations':False,
            'network':'kernel_seccomp_socket_operations_denied',
            'resource_ceilings':{'address_space_bytes':protected.CHILD_ADDRESS_SPACE_BYTES,'cpu_seconds':protected.CHILD_CPU_SECONDS,'file_bytes':protected.CHILD_FILE_BYTES,'file_descriptors':protected.CHILD_FILE_DESCRIPTORS,'core_bytes':0,'new_processes':'seccomp_denied','runtime_threads':'allowed_shared_process_budgets'},'request':request,'generic_review':generic,
            'result':result,'history':history,'reconciliation':observation,
            'raw_plan_sha256':hashlib.sha256(raw).hexdigest(),'implementation_sha256':protected._sha(protected.__file__)}
        (output/'protected-native-measured.json').write_bytes(canonical(report)+b'\n')
        print('Actual pinned native saved-plan result:',result['status'])
        print('Independent reconciliation:',observation['classification'])
        print('Preserved generic reviewer status:',generic['status'])


if __name__=='__main__':main()
