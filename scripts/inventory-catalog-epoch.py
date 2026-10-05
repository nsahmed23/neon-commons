#!/usr/bin/env python3
"""Revalidate all pinned lab metadata and map the mandatory selected lab IDs."""
import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', required=True)
    parser.add_argument('--directive', required=True)
    parser.add_argument('--evidence', required=True)
    args = parser.parse_args()
    checkout = Path(args.checkout).resolve(strict=True)
    output = Path(args.evidence).resolve(strict=True)
    inherited = json.loads((ROOT/'research/terraform-catalog/inventory.json').read_text())
    manifest = json.loads((ROOT/'research/terraform-catalog/source-files.json').read_text())
    for row in manifest['files']:
        path = checkout/row['path']
        if path.is_symlink() or not path.is_file() or sha(path) != row['sha256']:
            raise ValueError('Pinned catalog mismatch: '+row['path'])
    doc = Path(args.directive).read_text()
    selected = dict(re.findall(r'^\| ((?:getting-started|first-infra|write-code|state|modules|environments|aws|hcp-terraform)-[^ |]+) \| ([^\n]+?) \|$', doc, re.M))
    if len(selected) != 50:
        raise ValueError('Expected exactly 50 selected lab IDs')
    metadata = {}
    for file in sorted((checkout/'labs').rglob('lab.yaml')):
        m = yaml.safe_load(file.read_text())
        if m['id'] in metadata:
            raise ValueError('Duplicate lab ID')
        metadata[m['id']] = (file, m)
    if set(metadata) != {row['id'] for row in inherited['labs']}:
        raise ValueError('Pinned metadata and inherited inventory disagree')
    probe = {'operation':['dsoxlab','doctor','--strict','--json'], 'automatic_fixes':False}
    try:
        r = subprocess.run(probe['operation'], capture_output=True, text=True, timeout=15)
        probe.update(exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        probe.update(status='BLOCKED', error=str(exc), exception=type(exc).__name__)
    (output/'dsoxlab-doctor.json').write_text(json.dumps(probe, indent=2)+'\n')
    if (output/'dsoxlab/doctor.stdout').exists():
        probe['superseded_by_qualified_isolated_runner']='dsoxlab/doctor.stdout'
        probe['scope']='Bare PATH probe only; isolated pinned dsoxlab0.2.5 exists and was separately executed'
        (output/'dsoxlab-doctor.json').write_text(json.dumps(probe, indent=2)+'\n')
    execution = {
        'state-state-locking': ('locking-repeat', 'scripts/qualify-locking-lab.py', 'Local lock contention; interrupted writer; state recovery; initial failed replay retained'),
        'modules-test-module': ('module', 'scripts/qualify-catalog-module.py', 'Intact module; four corruption mutants; expected validation failure; no state leak'),
        'modules-version-modules': ('catalog-versions-repaired', 'scripts/qualify-catalog-offline.py --profile versions', 'Git immutable commit vs tags; installed module interface and output identity'),
        'hcp-terraform-projects-teams': ('catalog-permissions', 'scripts/qualify-catalog-offline.py --profile permissions', 'Local expression computes six additive-permission cases; five documentary answers separate'),
        'hcp-terraform-policy-as-code': ('catalog-policy', 'scripts/qualify-catalog-offline.py --profile policy', 'Local expression computes seven advisory/enforced decisions and both plan conformity controls; three documentary checks separate'),
    }
    rows=[]
    for old in inherited['labs']:
        id = old['id']; file,m = metadata[id]; env = old['execution_environment']
        prereqs = ['Pinned declared CLI; bounded disposable work directory; source and checker verification']
        # Empty/unfinished fixture declarations do not imply provider-free labs.
        # These requirements were verified from each complete public challenge.
        latent_providers = {
            'getting-started-terraform-vs-opentofu':['hashicorp/random','hashicorp/local','hashicorp/null'],
            'getting-started-install-terraform':['hashicorp/random','hashicorp/local','hashicorp/null'],
            'getting-started-providers-resources-data-sources':['hashicorp/random','hashicorp/local','hashicorp/null'],
            'write-code-providers':['hashicorp/random'],
        }
        providers = old['provider_sources_found_in_fixture_hcl'] or latent_providers.get(id,[])
        if providers:
            prereqs.append('External provider plugin RPC transport (host AF_UNIX currently denied)')
        if old['services']:
            prereqs.append('Container runtime and declared service images')
            if any(s['host_docker_socket'] for s in old['services']):
                prereqs.append('Host Docker socket authority; absent and not expanded here')
        if env == 'local_libvirt_host_mutations':
            prereqs.append('Authorized libvirt host, hypervisor and disposable VM/network resources')
        if env == 'real_hcp_account_and_remote_mutations':
            prereqs.append('Explicit live HCP account, credentials, allowed paid/remote mutations')
        status='NOT_RUN'; disposition='reference_only'; reason='Transfer lesson retained; full upstream exercise not executed in this epoch'
        commands=[]; receipt=None; start=None;end=None;exit_code=None;cleanup='No task execution; none created'
        adaptations=[]
        if id in execution:
            run,script,assertion=execution[id];receipt=output/run/'receipt.json'
            info=json.loads(receipt.read_text()) if receipt.exists() else {}
            status='PASS' if info.get('success') else 'FAIL'
            disposition='execute_adapted';reason='Reviewed original upstream grader and own solution; pinned OpenTofu adaptation'
            command_receipt=output/(run+'.run.json')
            rr=json.loads(command_receipt.read_text()) if command_receipt.exists() else {}
            commands=rr.get('argv',[]);start=rr.get('started_at');end=rr.get('ended_at');exit_code=rr.get('exit_code')
            adaptations=info.get('adaptations',[])
            cleanup=info.get('state_files_remaining', 'Task-owned local state retained for inspection; grader final destroy executed')
        else:
            assertion=old['lesson_for_plugin']
            if env in ('local_libvirt_host_mutations','real_hcp_account_and_remote_mutations','docker_service_and_native_provider'):
                disposition='defer_with_readiness_consequence';reason='Specific host/service/authority prerequisites unavailable; does not block local native labs'
            elif providers:
                disposition='defer_with_readiness_consequence';reason='Pinned native plugin RPC requires denied AF_UNIX; no transport bypass permitted'
            elif id == 'hcp-terraform-hcp-workspaces':
                disposition='exclude_with_reason';reason='Tests cloud-backend init against HCP token boundary; Terraform-specific external endpoint behavior outside this offline Intune profile'
        row={
            'catalog_url':'https://blog.stephane-robert.info/en/labs/', 'source_url':old['source_url'],
            'commit':manifest['commit'],'license':'CC-BY-4.0','id':id,'path':str(file.relative_to(checkout)),
            'runtime':m['runtime'],'declared_cli_constraints':old['required_cli_versions_found'],
            'providers':providers,'services':old['services'],
            'fixture_inputs':old['declared_fixtures'],'source_effect_signals':old['source_risk_signals'],
            'required_permissions_and_prerequisites':prereqs,'original_grader':old['test_path'],
            'original_grader_sha256':old['test_sha256'],'metadata_sha256':sha(file),
            'selected':id in selected,'project_assertion':selected.get(id,assertion),
            'independent_assertion':assertion,'disposition':disposition,'rationale':reason,
            'status':status,'adaptation_diff':adaptations,'command':commands,
            'started_at':start,'ended_at':end,'exit_code':exit_code,
            'raw_log_receipt':str(receipt.relative_to(output)) if receipt else None,
            'receipt_sha256':sha(receipt) if receipt and receipt.exists() else None,
            'cleanup_observation':cleanup,
            'remaining_gap':'No original dsoxlab runner evidence; no live Intune/Azure parity',
            'upstream_runner_executed':False,
        }
        # Trace the catalog lesson to the actual project boundary. This is a
        # requirement map, never a claim those requirements are accepted.
        requirements=['T05'];code=['intune_iac/journey.py','intune_iac/repository.py']
        if any(x in id for x in ('locking','backends','backup-restore','workspace','separate-environments')):
            requirements=['T04','T06'];code=['intune_iac/blob_lease.py','intune_iac/provider_execution.py']
        if any(x in id for x in ('workflow','automation','policy-as-code','remote-runs')):
            requirements=['T05','T06','S02','S06'];code=['intune_iac/protected.py','intune_iac/approval_authority.py']
        if any(x in id for x in ('import','diagnose-state','understand-state','state-mv','state-rm','removed-block','count','for-each')):
            requirements=['T03','T05'];code=['intune_iac/production.py','intune_iac/production_oracle.py','intune_iac/provider_execution.py']
        if any(x in id for x in ('variables','outputs','organize','structure','monorepo','module')):
            requirements=['T03','T05'];code=['intune_iac/repository.py','intune_iac/native_atmos.py']
        if any(x in id for x in ('install','version','vs-opentofu','providers')):
            requirements=['T00','T02','T05','S02'];code=['intune_iac/native_atmos.py','intune_iac/provider_execution.py']
        if any(x in id for x in ('sensitive','credentials')):
            requirements=['T12','S03','S04','S06'];code=['intune_iac/identity_binding.py','intune_iac/terminal_safety.py']
        if any(x in id for x in ('debug-apply','clean-destroy')):
            requirements=['T05','T06','S07'];code=['intune_iac/provider_execution.py','intune_iac/provider_journey.py']
        if id=='modules-test-module':
            requirements=['T03','T08'];code=['intune_iac/production_oracle.py','scripts/qualify-synthetic.py']
        row['project_requirement_ids']=requirements
        row['project_implementation_paths']=[p for p in code if (ROOT/p).is_file()]
        runner_name='dsoxlab-final' if (output/'dsoxlab-final/receipt.json').exists() else 'dsoxlab'
        if id == 'modules-test-module' and (output/runner_name/'receipt.json').exists():
            runner=json.loads((output/runner_name/'receipt.json').read_text())
            row['upstream_runner_executed']=runner.get('status') == 'PASS'
            row['upstream_runner_receipt']=runner_name+'/receipt.json'
            row['upstream_runner_scope']='Original dsoxlab0.2.5 run/check; OpenTofu1.10 engine adaptation; original8case grader'
            row['remaining_gap']='Original Terraform-engine replay and live Intune/Azure parity not established'
        rows.append(row)
    result={'schema':'catalog-epoch/1','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'catalog_commit':manifest['commit'],'all_files_revalidated':len(manifest['files']),
        'lab_metadata_revalidated':len(rows),'selected_required':len(selected),
        'selected_found':len(set(selected)&set(metadata)), 'missing_selected_ids':sorted(set(selected)-set(metadata)),
        'source_inventory_sha256':sha(ROOT/'research/terraform-catalog/inventory.json'),
        'source_manifest_sha256':sha(ROOT/'research/terraform-catalog/source-files.json'),
        'web_check':{'url':'https://blog.stephane-robert.info/en/labs/','date':'2026-10-04',
                     'observed_total_catalogs':5,'observed_terraform_count':88,
                     'note':'Public landing page metadata only; source verified separately against pin'},
        'status_counts':{s:sum(r['status']==s for r in rows) for s in ('PASS','FAIL','NOT_RUN')},
        'retained_negative_runs':['locking/receipt.json','catalog-versions/receipt.json','synthetic.run.json','adoption.run.json'],
        'upstream_runner_replays':sum(r['upstream_runner_executed'] for r in rows),
        'executed_native_supporting_labs':['adoption-qualified/result.json','sealed-plan.json'],
        'supporting_lab_limit':'Supporting mechanisms do not turn referenced catalog rows into executed upstream exercises',
        'labs':rows}
    (output/'catalog-ledger.json').write_text(json.dumps(result,indent=2)+'\n')
    with (output/'catalog-ledger.csv').open('w') as stream:
        fields=['id','selected','disposition','status','project_assertion','rationale','original_grader','raw_log_receipt']
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    print(json.dumps({k:v for k,v in result.items() if k not in ('labs',)}))

if __name__=='__main__': main()
