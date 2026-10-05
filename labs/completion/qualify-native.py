#!/usr/bin/env python3
"""Fixed native parity/state curriculum; local built-in resources, socket denied."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from intune_iac.repository import resolve_component

spec = importlib.util.spec_from_file_location('adoption_lab', ROOT / 'scripts/qualify-adoption-lab.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
CASES = ('imports_ab','imports_ba','inherits_parent_b','inherits_parent_a','scope_local',
         'scope_override','empty_values','type_change','parent_to_child','child_to_override','null_shapes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--atmos', required=True)
    parser.add_argument('--tofu', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    binaries = {name: runner.verify_binary(Path(getattr(args, name)), name) for name in ('atmos','tofu')}
    output = runner.prepare_output(args.output)
    lab = runner.Lab(output, binaries)
    report = {'status': 'running', 'scope': 'Original supplement; no upstream lab replay claim.',
              'cloud_calls': 0, 'external_providers': 0, 'network_denied': True,
              'filesystem_isolated': False, 'checks': lab.checks, 'commands': lab.commands}
    try:
        fixture_manifest = {item['case']: {row['path']: row['sha256'] for row in item['files']}
                            for item in json.loads((ROOT/'verification/plugin-0.2/native/python-fixtures-native-source-manifest.json').read_text())}
        for case in CASES:
            source = ROOT / 'verification/plugin-0.2/native/python-fixtures' / case
            if any(p.is_symlink() for p in source.rglob('*')):
                raise ValueError('fixture symlink rejected')
            source_hashes = {str(p.relative_to(source)): runner.sha256(p) for p in source.rglob('*') if p.is_file()}
            if source_hashes != fixture_manifest[case]:
                raise ValueError('retained native parity fixture changed')
            work = output / ('parity-' + case)
            shutil.copytree(source, work)
            before = {str(p.relative_to(work)): runner.sha256(p) for p in work.rglob('*') if p.is_file()}
            result = resolve_component(work, 'orgs/qualification', 'leaf')
            out, err, code = lab.native('parity-' + case.replace('_','-'), 'atmos',
                ['describe','component','leaf','-s','qualification','--format','json',
                 '--process-functions=false','--process-templates=false'], cwd=work, expected=(0,1))
            if case == 'type_change':
                valid = result['status'] == 'blocked' and code != 0 and 'mergo merge failed' in err
            else:
                native = json.loads(out)
                valid = result['status'] == 'resolved' and code == 0 and result['effective']['vars'] == native['vars']
            after = {str(p.relative_to(work)): runner.sha256(p) for p in work.rglob('*') if p.is_file()}
            lab.check('literal-parity-' + case.replace('_','-'), valid and before == after,
                      {'source_files': before, 'python_status': result['status'], 'native_exit': code})
        # Independent built-in resource curriculum: exact addresses, identity,
        # state-only forget, partial failure and recovery on actual OpenTofu.
        work = output / 'state-curriculum'; work.mkdir()
        config = work / 'main.tf'
        prefix = 'terraform {\n  required_version = "= 1.10.0"\n}\n'
        old = prefix + 'resource "terraform_data" "old" {\n  input = "preserved"\n}\n'
        config.write_text(old)
        lab.native('state-init','tofu',['init','-input=false','-no-color'],cwd=work)
        lab.native('state-seed','tofu',['apply','-auto-approve','-input=false','-no-color'],cwd=work)
        original = json.loads((work/'terraform.tfstate').read_text())
        original_id = original['resources'][0]['instances'][0]['attributes']['id']
        config.write_text(prefix + 'resource "terraform_data" "adopted" {\n  input = "preserved"\n}\n'
                          + 'moved {\n  from = terraform_data.old\n  to = terraform_data.adopted\n}\n')
        lab.native('moved-plan','tofu',['plan','-input=false','-no-color','-detailed-exitcode','-out=moved.tfplan'],cwd=work,expected=(2,))
        out,_,_=lab.native('moved-json','tofu',['show','-json','moved.tfplan'],cwd=work)
        plan=json.loads(out);runner.write_json(output/'evidence/moved-plan.json',plan)
        change=plan['resource_changes'][0]
        lab.check('moved-no-replacement',len(plan['resource_changes'])==1 and change['previous_address']=='terraform_data.old'
                  and change['address']=='terraform_data.adopted' and change['change']['actions']==['no-op'])
        lab.native('moved-apply','tofu',['apply','-input=false','-no-color','moved.tfplan'],cwd=work)
        state=json.loads((work/'terraform.tfstate').read_text())
        lab.check('moved-preserves-identity',state['resources'][0]['instances'][0]['attributes']['id']==original_id
                  and state['lineage']==original['lineage'])
        config.write_text(prefix+'removed {\n  from = terraform_data.adopted\n  lifecycle {\n    destroy = false\n  }\n}\n')
        lab.native('forget-plan','tofu',['plan','-input=false','-no-color','-detailed-exitcode','-out=forget.tfplan'],cwd=work,expected=(2,))
        out,_,_=lab.native('forget-json','tofu',['show','-json','forget.tfplan'],cwd=work)
        plan=json.loads(out);runner.write_json(output/'evidence/forget-plan.json',plan)
        lab.check('forget-without-delete',len(plan['resource_changes'])==1 and plan['resource_changes'][0]['change']['actions']==['forget'])
        lab.native('forget-apply','tofu',['apply','-input=false','-no-color','forget.tfplan'],cwd=work)
        lab.native('forget-converged','tofu',['plan','-input=false','-no-color','-detailed-exitcode'],cwd=work)
        lab.check('forget-no-recreation',json.loads((work/'terraform.tfstate').read_text())['resources']==[])
        work = output/'partial-failure';work.mkdir();config=work/'main.tf'
        body=prefix+'''resource "terraform_data" "policy" {
  input = "preserved-policy"
}
resource "terraform_data" "assignment" {
  input = terraform_data.policy.id
  provisioner "local-exec" {
    command = "exit 1"
  }
}
'''
        config.write_text(body)
        lab.native('fault-init','tofu',['init','-input=false','-no-color'],cwd=work)
        _,err,code=lab.native('fault-apply','tofu',['apply','-auto-approve','-input=false','-no-color'],cwd=work,expected=(1,))
        failed=json.loads((work/'terraform.tfstate').read_text());runner.write_json(output/'evidence/partial-state.json',failed)
        policy=next(x for x in failed['resources'] if x['name']=='policy')['instances'][0]['attributes']['id']
        assignment=next(x for x in failed['resources'] if x['name']=='assignment')['instances'][0]
        lab.check('partial-native-effect-observed',bool(policy) and assignment['status']=='tainted' and 'local-exec provisioner error' in err)
        config.write_text(body.replace('exit 1','exit 0'))
        lab.native('fault-repair','tofu',['apply','-auto-approve','-input=false','-no-color'],cwd=work)
        repaired=json.loads((work/'terraform.tfstate').read_text());runner.write_json(output/'evidence/repaired-state.json',repaired)
        lab.check('repair-preserves-successful-policy',next(x for x in repaired['resources'] if x['name']=='policy')['instances'][0]['attributes']['id']==policy
                  and repaired['lineage']==failed['lineage'])
        lab.native('fault-converged','tofu',['plan','-input=false','-no-color','-detailed-exitcode'],cwd=work)
        lab.check('recovery-no-change',True)
        report['status']='passed'
    except Exception as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}')
    finally:
        report.update(checks_passed=len(lab.checks), native_commands=len(lab.commands),
                      binary_sha256={name:runner.sha256(path) for name,path in binaries.items()},
                      runner_sha256=runner.sha256(Path(__file__)))
        runner.write_json(output/'result.json',report)
    print(json.dumps({'status':report['status'],'checks':len(lab.checks),'commands':len(lab.commands),'error':report.get('error')},indent=2))
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
