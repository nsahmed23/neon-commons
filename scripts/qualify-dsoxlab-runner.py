#!/usr/bin/env python3
"""Pinned dsoxlab doctor and provider-free original runner reproduction.

Only a disposable catalog copy is mutated. Linux child network syscalls are
denied; no --fix, provisioning, services, remote accounts or privileged actions.
The original dsoxlab runner is used with an explicitly adapted OpenTofu engine.
"""
import argparse
import base64
import csv
import datetime
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from intune_iac.native_atmos import _GUARD

WHEEL_SHA='23c9f4244342b4812097e1d4afb3ce9b35dba9a8780595f7e2a04da9dd59c29c'
TOFU_SHA='0a9eda0f0898896969492504a6ce778f310675e8a1eb960434c26806cd252627'

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('checkout','python','wheel','tofu','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();checkout=Path(a.checkout).resolve(strict=True);py=Path(a.python).absolute();wheel=Path(a.wheel).resolve(strict=True);tofu=Path(a.tofu).resolve(strict=True)
    if sha(wheel)!=WHEEL_SHA or sha(tofu)!=TOFU_SHA:raise ValueError('Pin mismatch')
    manifest=json.loads((ROOT/'research/terraform-catalog/source-files.json').read_text())
    expected_paths={r['path'] for r in manifest['files']}
    actual_paths=set()
    for path in checkout.rglob('*'):
        if path.is_symlink():raise ValueError('Symlink in catalog snapshot')
        if path.is_file():actual_paths.add(path.relative_to(checkout).as_posix())
    if actual_paths!=expected_paths:raise ValueError('Catalog must be the exact pinned archive snapshot, without added files')
    for row in manifest['files']:
        if sha(checkout/row['path'])!=row['sha256']:raise ValueError('Source differs')
    # Verify wheel payload against RECORD, beyond the whole-artifact digest.
    with zipfile.ZipFile(wheel) as z:
        record=next(n for n in z.namelist() if n.endswith('.dist-info/RECORD'))
        for name,checksum,size in csv.reader(io.StringIO(z.read(record).decode())):
            if not checksum:continue
            algorithm,expected=checksum.split('=',1)
            if algorithm!='sha256':raise ValueError('Unexpected wheel hash algorithm')
            raw=z.read(name)
            if base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')!=expected or len(raw)!=int(size):raise ValueError('Wheel payload mismatch')
    output=Path(a.output).absolute()
    if output != output.resolve() or any(p.is_symlink() for p in (output,*output.parents)):
        raise ValueError('Output must be canonical and may not traverse symlinks')
    if output.is_relative_to(checkout) or output.is_relative_to(ROOT):raise ValueError('Output overlaps source')
    output.mkdir(mode=0o700,parents=False,exist_ok=False)
    catalog=output/'catalog';shutil.copytree(checkout,catalog)
    for name in ('home','bin','tmp'):(output/name).mkdir()
    binary=output/'bin/tofu';shutil.copyfile(tofu,binary);binary.chmod(0o700)
    wrapper=output/'bin/terraform'
    import shlex
    wrapper.write_text('#!/bin/sh\nexec /usr/bin/timeout --foreground --kill-after=2s 30s '+shlex.quote(str(binary))+' "$@"\n');wrapper.chmod(0o700)
    (output/'terraform.rc').write_text('disable_checkpoint = true\nprovider_installation { filesystem_mirror { path = "./empty-mirror" } }\n')
    env={'PATH':str(output/'bin')+':'+str(py.parent)+':/usr/bin:/bin','HOME':str(output/'home'),'TMPDIR':str(output/'tmp'),
         'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TF_CLI_CONFIG_FILE':str(output/'terraform.rc'),'CHECKPOINT_DISABLE':'1',
         'TF_IN_AUTOMATION':'1','TF_INPUT':'0','DSOXLAB_LANG':'en','LAB_NO_REPLAY':'1','PYTHONNOUSERSITE':'1',
         'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0','SHELL':'/bin/bash'}
    report={'schema':'dsoxlab-native-runner/1','runner_version':'0.2.5','runner_wheel_sha256':WHEEL_SHA,
            'runner_license':'Apache-2.0','catalog_commit':manifest['commit'],'catalog_license':'CC-BY-4.0',
            'upstream_runner_executed':True,'engine':'OpenTofu 1.10.0 (adaptation)','commands':[],
            'authority':'read-only diagnosis; task-owned shell fixture and local grading only',
            'network':'child seccomp denies socket/socketpair/connect; optional doctor egress probe expected denied',
            'harness_sha256':sha(Path(__file__)),'live_service_calls':0,'automatic_fixes':False,'production_qualified':False}
    dsox=py.parent/'dsoxlab'
    def run(label,tail,timeout=60):
        args=[str(py),'-I','-S','-c',_GUARD,str(dsox),*tail]
        start=datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (output/(label+'.stdout')).open('wb') as stdout,(output/(label+'.stderr')).open('wb') as stderr:
            proc=subprocess.Popen(args,cwd=catalog,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
            try:code=proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait();code=124
        row={'label':label,'argv':args,'started_at':start,'ended_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exit_code':code,
             'stdout_sha256':sha(output/(label+'.stdout')),'stderr_sha256':sha(output/(label+'.stderr'))}
        report['commands'].append(row);(output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');return code
    run('version',['--version'])
    run('doctor',['doctor','--strict','--json','--lab-home',str(catalog)])
    run('list',['list-labs','--json','--lab-home',str(catalog)])
    run('show',['show','modules-test-module','--lab-home',str(catalog)])
    # start diagnoses the whole catalog (Docker labs included); run is the
    # supported shell-only entrypoint for this specific no-service exercise.
    run('start',['start','modules-test-module','--lab-home',str(catalog)])
    prepared=run('run',['run','modules-test-module','--lab-home',str(catalog)])
    before=run('check-before',['check','modules-test-module','--json','--lab-home',str(catalog)])
    spec=importlib.util.spec_from_file_location('module_lab',ROOT/'scripts/qualify-catalog-module.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    target=catalog/'labs/modules/test-module/challenge/work/etiquette/tests/etiquette.tftest.hcl'
    if not target.is_file():
        report.update(status='BLOCKED',error='Original runner did not prepare expected module fixture')
    else:
        target.write_text(m.SOLUTION)
        after=run('check-after',['check','modules-test-module','--json','--lab-home',str(catalog)])
        # Parse actual machine report; an exit zero alone does not prove cases.
        try:result=json.loads((output/'check-after.stdout').read_text())
        except json.JSONDecodeError:result=None
        measured = result.get('check',{}) if isinstance(result,dict) else {}
        complete = measured.get('ok') is True and measured.get('passed') == 8 and measured.get('total') == 8
        report.update(status='PASS' if prepared==0 and before!=0 and after==0 and complete else 'FAIL',grade_before_exit=before,grade_after_exit=after,grade_after=result)
    report['scope']='Original runner, pinned catalog bytes, original provider-free module grader, authored suite; OpenTofu engine adaptation'
    report['cleanup']='Interactive shell receives EOF; original runner exited; only owned catalog progress/state files retained'
    (output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'commands':len(report['commands'])}))
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
