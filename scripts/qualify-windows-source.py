#!/usr/bin/env python3
"""Native disposable import/proposal journey; no authoritative source edit."""
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
from intune_iac.windows_capture import _reference_bytes,_NativeAPI
FILES=tuple(sorted(str(path.relative_to(ROOT)).replace(os.sep,'/') for path in (ROOT/'intune_iac').glob('*.py')))+('scripts/intune-windows-source.py','scripts/qualify-windows-source.py')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    names=('store','tenant','repo','stack','component','object','pointer','revision','backend','resource-address','field','proposal','expected','expected-sha256','output')
    for name in names:parser.add_argument('--'+name,required=True)
    parser.add_argument('--source-pins');parser.add_argument('--source-pins-sha256');args=parser.parse_args(argv)
    output=Path(args.output).absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(ROOT) or any(p.is_symlink() for p in output.parents):parser.error('new_output_outside_package_required')
    if os.name=='nt' and sys.platform=='win32':
        try:create_private_directory(str(output.parent),output.name)
        except AppError as error:
            print(json.dumps({'status':'BLOCKED','code':error.code,'checks':0,'commands':0,'storage_outcome':getattr(error,'storage_outcome',None),'retained_output':str(output)}));return 3
    else:output.mkdir(parents=True,mode=0o700)
    files={name:sha(ROOT/name) for name in FILES};result={'schema_version':'intune-windows-source-qualification/1','status':'BLOCKED','source_files':files,
        'checks':[],'commands':[],'blockers':[],'platform_qualified':False,'workbench_profile_enabled':False,'production_approved':False,
        'scope':'Actual native local repository intent import and immutable proposal; no source editing, Git authentication, service mutation or approval.',
        'environment':{'platform':sys.platform,'python':sys.version,'executable_sha256':sha(sys.executable)}}
    def finish(code):
        result['source_files_after']={name:sha(ROOT/name) for name in FILES}
        if result['source_files_after']!=files:result['status']='FAIL';code=1
        (output/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':result['status'],'checks':len(result['checks']),'commands':len(result['commands'])}));return code
    if os.name!='nt' or sys.platform!='win32':
        result['blockers'].append({'code':'native_windows_host_required','owner':'Windows endpoint/runner owner'});return finish(3)
    def run(identifier,tail):
        command=[sys.executable,'-B',str(ROOT/'scripts/intune-windows-source.py'),'--qualification-only','--store',args.store,'--tenant',args.tenant]+tail
        row={'id':identifier,'argv':command,'exit':None};result['commands'].append(row)
        try:child=subprocess.run(command,capture_output=True,timeout=60,shell=False)
        except subprocess.TimeoutExpired as error:
            (output/(identifier+'.stdout.raw')).write_bytes(error.stdout or b'');(output/(identifier+'.stderr.raw')).write_bytes(error.stderr or b'');row['timed_out']=True;raise
        (output/(identifier+'.stdout.raw')).write_bytes(child.stdout);(output/(identifier+'.stderr.raw')).write_bytes(child.stderr);row['exit']=child.returncode
        if child.returncode:raise ValueError('application_command_failed')
        return parse_json(child.stdout)
    try:
        if sys.version_info[:2]!=(3,12) or ctypes.sizeof(ctypes.c_void_p)!=8:raise ValueError('native_cpython312_required')
        pins=Path(args.source_pins or '').read_bytes()
        if len(pins)>1024*1024 or hashlib.sha256(pins).hexdigest()!=args.source_pins_sha256:raise ValueError('source_pins_mismatch')
        pin=parse_json(pins)
        if set(pin)!={'source_commit','files'} or not re.fullmatch('[a-f0-9]{40}',pin['source_commit']) or pin['files']!=files:raise ValueError('exact_source_pins_required')
        result['declared_source_commit']=pin['source_commit'];result['linkage']='Independently verify exact files against reviewed source commit.';(output/'source-pins.json').write_bytes(pins)
        raw=Path(args.expected).read_bytes()
        if len(raw)>2*1024*1024 or hashlib.sha256(raw).hexdigest()!=args.expected_sha256:raise ValueError('expected_pin_mismatch')
        expected=parse_json(raw)
        if type(expected) is not dict or set(expected)!={'source_path','before_sha256','after_sha256','affected_stacks','source_pointer'}:raise ValueError('independent_expected_fields_required')
        api=_NativeAPI();before=_reference_bytes(str(Path(args.repo)/expected['source_path']),api,2*1024*1024)
        if hashlib.sha256(before).hexdigest()!=expected['before_sha256']:raise ValueError('source_before_pin_mismatch')
        command=['repository-import']
        for name in ('repo','stack','component','object','pointer','revision','backend','resource-address'):command+=['--'+name,getattr(args,name.replace('-','_'))]
        imported=run('repository-import',command)
        proposed=run('source-acceptance-propose',['source-acceptance-propose','--object',args.object,'--field',args.field,'--output',args.proposal])['result']
        saved_before=_reference_bytes(str(Path(args.proposal)/'source.before.yaml'),api,2*1024*1024)
        saved_after=_reference_bytes(str(Path(args.proposal)/'source.after.yaml'),api,2*1024*1024)
        original_after=_reference_bytes(str(Path(args.repo)/expected['source_path']),api,2*1024*1024)
        checks={'exact_source_before':saved_before==before,'independent_candidate_bytes':hashlib.sha256(saved_after).hexdigest()==expected['after_sha256'],
            'source_untouched':original_after==before,'exact_authoritative_path':proposed['authoritative_source']['path']==expected['source_path'],
            'exact_winning_pointer':proposed['authoritative_source']['pointer']==expected['source_pointer'],
            'independent_shared_impact':[row['stack'] for row in proposed['shared_inheritance_impact']]==expected['affected_stacks'],
            'fresh_plan_required':proposed['fresh_plan_required'] is True and proposed['no_resource_changes_established'] is False,
            'local_only':imported['tenant_mutation'] is False and proposed['execution_authorized'] is False and proposed['source_modified'] is False}
        result['checks']=[{'id':key,'pass':bool(value)} for key,value in checks.items()];result['status']='PASS' if all(checks.values()) else 'FAIL'
        return finish(0 if result['status']=='PASS' else 1)
    except (AppError,ValueError,TypeError,KeyError,OSError,subprocess.TimeoutExpired) as error:
        result['status']='FAIL';result['failure']={'type':type(error).__name__,'code':getattr(error,'code','native_source_qualification_failed')};return finish(1)
if __name__=='__main__':raise SystemExit(main())
