#!/usr/bin/env python3
"""Read-only native repository/current-source qualification through actual views.

Use a pre-existing private disposable native store with a repository_intent
artifact and its exact DOS source root. No source edits, credentials or cloud I/O.
The expected file is authored independently of the resolver before this run.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from intune_iac.io import AppError,parse_json
from intune_iac.windows_storage import create_private_directory

FILES=('intune_iac/repository.py','intune_iac/windows_repository.py','intune_iac/windows_views.py',
    'intune_iac/workbench_views.py','intune_iac/workbench_semantics.py','intune_iac/windows_capture.py',
    'intune_iac/windows_directory.py','intune_iac/windows_storage.py','intune_iac/windows_sqlite.py',
    'intune_iac/windows_workbench.py','intune_iac/workbench_store.py','intune_iac/workbench_schema.py',
    'intune_iac/io.py','scripts/intune-windows-inspect.py','scripts/qualify-windows-repository.py')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('store','tenant','object','expected','expected-sha256','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--source-pins');parser.add_argument('--source-pins-sha256');args=parser.parse_args(argv)
    output=Path(args.output).absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(ROOT) or any(p.is_symlink() for p in output.parents):parser.error('new_output_outside_package_required')
    if sys.platform=='win32' and os.name=='nt':
        try:create_private_directory(str(output.parent),output.name)
        except AppError as error:
            print(json.dumps({'status':'BLOCKED','code':error.code,'checks':0,'commands':0,
                'retained_output':str(output),'storage_outcome':getattr(error,'storage_outcome',None)}));return 3
    else:output.mkdir(parents=True,mode=0o700)
    files={name:sha(ROOT/name) for name in FILES};result={'schema_version':'intune-windows-repository-qualification/1',
        'status':'BLOCKED','source_files':files,'checks':[],'commands':[],'blockers':[],
        'platform_qualified':False,'production_approved':False,'workbench_profile_enabled':False,
        'environment':{'platform':sys.platform,'python':sys.version,'executable_sha256':sha(sys.executable)},
        'scope':'Native current source read through existing readonly views; no Git authentication, cloud/service or production support claim.'}
    def finish(code):
        result['source_files_after']={name:sha(ROOT/name) for name in FILES}
        if result['source_files_after']!=files:result['status']='FAIL';code=1
        (output/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':result['status'],'checks':len(result['checks']),'commands':len(result['commands'])}));return code
    if sys.platform!='win32' or os.name!='nt':
        result['blockers'].append({'code':'native_windows_host_required','owner':'Windows endpoint/runner owner'});return finish(3)
    try:
        if sys.version_info[:2]!=(3,12) or ctypes.sizeof(ctypes.c_void_p)!=8:raise ValueError('native_cpython312_64_required')
        pins=Path(args.source_pins or '').read_bytes()
        if len(pins)>1024*1024 or hashlib.sha256(pins).hexdigest()!=args.source_pins_sha256:raise ValueError('source_pins_mismatch')
        pin=parse_json(pins)
        if set(pin)!={'source_commit','files'} or not re.fullmatch('[a-f0-9]{40}',pin['source_commit']) or pin['files']!=files:raise ValueError('exact_source_pins_required')
        result['declared_source_commit']=pin['source_commit'];result['commit_linkage']='Independent reviewed-commit linkage required.'
        (output/'source-pins.json').write_bytes(pins)
        expected_raw=Path(args.expected).read_bytes()
        if len(expected_raw)>2*1024*1024 or hashlib.sha256(expected_raw).hexdigest()!=args.expected_sha256:raise ValueError('expected_pin_mismatch')
        expected=parse_json(expected_raw)
        if type(expected) is not dict or set(expected)!={'current_policy','source_files','source_hashes_equal','recorded_source_revision'}:raise ValueError('expected_literal_fields_required')
        command=[sys.executable,'-B',str(ROOT/'scripts/intune-windows-inspect.py'),'--qualification-only','--store',args.store,'--tenant',args.tenant,'views',args.object]
        entry={'id':'actual-native-views','argv':command,'exit':None};result['commands'].append(entry)
        try:child=subprocess.run(command,capture_output=True,timeout=60,shell=False)
        except subprocess.TimeoutExpired as error:
            (output/'views.stdout.raw').write_bytes(error.stdout or b'');(output/'views.stderr.raw').write_bytes(error.stderr or b'');entry['timed_out']=True;raise
        (output/'views.stdout.raw').write_bytes(child.stdout);(output/'views.stderr.raw').write_bytes(child.stderr);entry['exit']=child.returncode
        if child.returncode!=0:raise ValueError('actual_views_failed')
        view=parse_json(child.stdout)['result'];current=view['repository']['current_working_source_readback']
        checks={'exact_identity':view['tenant_id']==args.tenant and view['object_id']==args.object,
            'independent_expected_policy':current.get('current_policy')==expected['current_policy'],
            'independent_source_bytes':current.get('source_files')==expected['source_files'],
            'separate_current_baseline':current.get('source_hashes_equal') is expected['source_hashes_equal'],
            'recorded_revision_preserved':current.get('recorded_source_revision')==expected['recorded_source_revision'],
            'no_git_or_execution_promotion':current.get('git_revision_verified') is False and current.get('execution_authorized') is False,
            'bounded_timestamp':0<=current['read_started_at']<=current['read_completed_at'],
            'no_default_profile_activation':view['native_evidence_access']['workbench_profile_enabled'] is False}
        result['checks']=[{'id':key,'pass':bool(value)} for key,value in checks.items()]
        result['status']='PASS' if all(checks.values()) else 'FAIL';return finish(0 if result['status']=='PASS' else 1)
    except (AppError,ValueError,TypeError,KeyError,OSError,subprocess.TimeoutExpired) as error:
        result['status']='FAIL';result['failure']={'type':type(error).__name__,'code':getattr(error,'code','native_repository_qualification_failed')};return finish(1)

if __name__=='__main__':raise SystemExit(main())
