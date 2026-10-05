#!/usr/bin/env python3
"""Replay pinned provider-free module mutation lab; never a dsoxlab runner claim."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LAB = 'labs/modules/test-module'
SOLUTION = '''variables { prefixe = "atelier" }
run "default" {
  command = plan
  assert {
    condition = output.etiquette == "atelier"
    error_message = "Default label differs"
  }
  assert {
    condition = output.longueur == 7
    error_message = "Default length differs"
  }
}
run "suffix" {
  command = plan
  variables { suffixe = "nord" }
  assert {
    condition = output.etiquette == "atelier-nord"
    error_message = "Suffix differs"
  }
}
run "uppercase" {
  command = plan
  variables { majuscules = true }
  assert {
    condition = output.etiquette == "ATELIER"
    error_message = "Uppercase differs"
  }
}
run "invalid_prefix" {
  command = plan
  variables { prefixe = "ab" }
  expect_failures = [var.prefixe]
}
'''

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--upstream', required=True)
    p.add_argument('--tofu', required=True)
    p.add_argument('--pytest-python', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    source = Path(a.upstream).resolve(strict=True)
    manifest = json.loads((ROOT/'research/terraform-catalog/source-files.json').read_text())
    files = {r['path']: r['sha256'] for r in manifest['files']}
    names = ['conftest.py', f'{LAB}/challenge/tests/test_functional.py']
    names += [n for n in files if n.startswith(f'{LAB}/fixtures/')]
    for n in names:
        if source.joinpath(n).is_symlink() or sha(source/n) != files[n]:
            raise ValueError('Pinned source mismatch: '+n)
    spec = importlib.util.spec_from_file_location('locking_lab', ROOT/'scripts/qualify-locking-lab.py')
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    tofu = Path(a.tofu).resolve(strict=True)
    if sha(tofu) != h.TOFU_SHA256:
        raise ValueError('OpenTofu pin mismatch')
    output = Path(a.output).absolute()
    for protected in (ROOT, source):
        if output.resolve().is_relative_to(protected) or protected.is_relative_to(output.resolve()):
            raise ValueError('Output must not overlap source')
    output = h.new_output(output)
    for n in ('bin', 'home', 'tmp', 'work', 'upstream'):
        (output/n).mkdir()
    for n in names:
        dest = output/'upstream'/n; dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((source/n).read_bytes())
    shutil.copytree(source/LAB/'fixtures', output/'work', dirs_exist_ok=True)
    pinned = output/'bin/tofu'; shutil.copyfile(tofu, pinned); pinned.chmod(0o700)
    if sha(pinned) != h.TOFU_SHA256:
        raise ValueError('Copied executable mismatch')
    h.install_wrapper(output, pinned)
    (output/'terraform.rc').write_text('disable_checkpoint = true\nprovider_installation { filesystem_mirror { path = "./no-providers" } }\n')
    env = h.clean_environment(output)
    tests = output/'upstream'/LAB/'challenge/tests/test_functional.py'
    report = {'schema':'catalog-module/1','catalog_commit':manifest['commit'],
        'lab_id':'modules-test-module','evidence_class':'adapted_native_opentofu',
        'dsoxlab_runner_executed':False,'encrypted_solutions_read':False,
        'source_hashes':{n:files[n] for n in names},'harness_sha256':sha(Path(__file__)),
        'adaptations':['OpenTofu 1.10.0 via fixed bounded terraform wrapper',
                       'Original authored test suite; unchanged module and upstream grader',
                       'No dsoxlab provisioning; copied declared fixtures'], 'commands':[]}
    def grade(label):
        cmd = [str(Path(a.pytest_python).absolute()),'-m','pytest',str(tests),'-q',
               '--junitxml',str(output/(label+'.xml'))]
        r = h.execute(cmd, output/'upstream', env, timeout=150)
        h.write_json(output/(label+'.json'),r);report['commands'].append({'label':label,**r})
        suite = next(ET.parse(output/(label+'.xml')).getroot().iter('testsuite'))
        return {k:int(suite.attrib[k]) for k in ('tests','errors','failures','skipped')},r['exit_code']
    version = h.execute([str(Path(a.pytest_python).absolute()),'-m','pytest','--version'],output,env)
    if version['stdout'].strip() != 'pytest 8.4.2':
        raise ValueError('pytest 8.4.2 required')
    report['before'], before = grade('before')
    target = output/'work/etiquette/tests/etiquette.tftest.hcl'
    target.write_text(SOLUTION)
    report['after'], after = grade('after')
    report['independent_module_preservation'] = all(sha(output/'work'/Path(n).relative_to(f'{LAB}/fixtures')) == files[n]
        for n in names if n.startswith(f'{LAB}/fixtures/') and not n.endswith('.tftest.hcl'))
    report['state_files_remaining'] = [str(x.relative_to(output)) for x in (output/'work').rglob('*.tfstate*')]
    report['success'] = (before != 0 and after == 0 and report['after'] == {'tests':8,'errors':0,'failures':0,'skipped':0}
        and report['independent_module_preservation'] and not report['state_files_remaining'])
    report['limitations'] = ['No provider RPC, live service, Atmos or enterprise host qualification',
                             'Cooperative workspace; not a hostile-code filesystem sandbox']
    h.write_json(output/'receipt.json',report)
    print(json.dumps({k:report[k] for k in ('success','before','after','independent_module_preservation','state_files_remaining')}))
    return 0 if report['success'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
