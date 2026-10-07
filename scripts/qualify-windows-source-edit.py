#!/usr/bin/env python3
"""Native disposable exact source edit and explicit interruption recovery qualifier."""
import argparse
from contextlib import redirect_stdout,redirect_stderr
import ctypes as C
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path,PureWindowsPath
import re
import subprocess
import sys
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from intune_iac.io import AppError,parse_json
from intune_iac import windows_source_edit as edit,windows_capture as capture
from intune_iac.windows_storage import create_private_directory
FILES=tuple(sorted(str(p.relative_to(ROOT)).replace(os.sep,'/') for p in (ROOT/'intune_iac').glob('*.py')))+('scripts/intune-windows-source.py','scripts/qualify-windows-source-edit.py')
def sha(data):return hashlib.sha256(data).hexdigest()
def _bind_review(case,value):
    """Pin the independent oracle to the exact reviewed mutation target."""
    root=case['repo'];relative=case['source_path']
    if (type(relative) is not str or not relative or '\\' in relative or relative.startswith('/') or
            any(part in ('','.','..') for part in relative.split('/'))):raise ValueError('case_source_path_invalid')
    if (type(value) is not dict or value.get('source_root')!=root or value.get('proposal_path')!=case['proposal'] or
            value.get('proposal_sha256')!=case['digest'] or value.get('tenant_id')!=case['tenant'] or
            value.get('protected_plan_approval') is not False or value.get('organizational_approval') is not False):raise ValueError('review_target_mismatch')
    source=value.get('authoritative_source')
    if (type(source) is not dict or source.get('path')!=relative or
            source.get('before_sha256')!=case['before_sha256'] or source.get('after_sha256')!=case['after_sha256'] or
            case['before_sha256']==case['after_sha256']):raise ValueError('review_source_mismatch')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('cases','cases-sha256','source-pins','source-pins-sha256','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--acknowledge-disposable-source-edits',action='store_true',required=True)
    args=parser.parse_args(argv);out=Path(args.output).absolute()
    if out.exists() or out.is_symlink() or out.resolve().is_relative_to(ROOT) or any(p.is_symlink() for p in out.parents):parser.error('new_output_outside_package_required')
    if os.name=='nt' and sys.platform=='win32':
        try:create_private_directory(str(out.parent),out.name)
        except AppError as error:
            print(json.dumps({'status':'BLOCKED','code':error.code,'checks':0,'commands':0,'storage_outcome':getattr(error,'storage_outcome',None)}));return 3
    else:out.mkdir(parents=True,mode=0o700)
    files={name:sha((ROOT/name).read_bytes()) for name in FILES};result={'schema_version':'intune-native-source-edit-qualification/1','status':'BLOCKED',
        'source_files':files,'checks':[],'commands':[],'blockers':[],'platform_qualified':False,'production_approved':False,'ordinary_windows_profile_enabled':False,
        'scope':'Actual disposable native local source writes and injected lost-ack recovery; no tenant/Git/plan/organizational authority or power-loss claim.',
        'environment':{'platform':sys.platform,'python':sys.version,'executable_sha256':sha(Path(sys.executable).read_bytes())}}
    def finish(code):
        result['source_files_after']={name:sha((ROOT/name).read_bytes()) for name in FILES}
        if result['source_files_after']!=files:result['status']='FAIL';code=1
        (out/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':result['status'],'checks':len(result['checks']),'commands':len(result['commands'])}));return code
    if os.name!='nt' or sys.platform!='win32':
        result['blockers'].append({'code':'native_windows_host_required','owner':'Windows endpoint/runner owner'});return finish(3)
    def assert_check(name,value):
        result['checks'].append({'id':name,'pass':bool(value)})
        if not value:raise ValueError('independent_assertion_failed')
    def invoke(case,name,tail,fault=None):
        argv=['--qualification-only','--store',case['store'],'--tenant',case['tenant']]+tail
        row={'id':case['id']+'/'+name,'argv':[sys.executable,'-B',str(ROOT/'scripts/intune-windows-source.py')]+argv,'injected_lost_rename_ack':fault};result['commands'].append(row)
        if fault is None:
            try:child=subprocess.run(row['argv'],capture_output=True,timeout=60,shell=False)
            except subprocess.TimeoutExpired as error:
                (out/(case['id']+'-'+name+'.stdout.raw')).write_bytes(error.stdout or b'');(out/(case['id']+'-'+name+'.stderr.raw')).write_bytes(error.stderr or b'');row['timeout']=True;raise
            code,stdout,stderr=child.returncode,child.stdout,child.stderr
        else:
            spec=importlib.util.spec_from_file_location('native_source_cli_qualifier',ROOT/'scripts/intune-windows-source.py');app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
            class FaultAPI(edit._NativeAPI):
                def __init__(self):super().__init__();self.source_renames=0
                def rename_new(self,handle,root_handle,name):
                    super().rename_new(handle,root_handle,name)
                    if not name.endswith(('.intent.json','.ready.json')):
                        self.source_renames+=1
                        if self.source_renames==fault:raise AppError('qualification_injected_lost_rename_ack','Actual native source rename completed; qualification interrupts its acknowledgement.')
            stdout_text,stderr_text=io.StringIO(),io.StringIO()
            with patch.object(edit,'_NativeAPI',FaultAPI),redirect_stdout(stdout_text),redirect_stderr(stderr_text):code=app.main(argv)
            stdout,stderr=stdout_text.getvalue().encode(),stderr_text.getvalue().encode()
            row['execution']='Actual CLI parser/handler in-process with real Win32 API subclass; only post-rename acknowledgement fault injected.'
        row['exit']=code;(out/(case['id']+'-'+name+'.stdout.raw')).write_bytes(stdout);(out/(case['id']+'-'+name+'.stderr.raw')).write_bytes(stderr)
        return code,parse_json(stdout if code==0 else stderr)
    def snapshot(path):
        # Independent direct native descriptor/attributes oracle on a held,
        # admitted path. Does not call the product edit_metadata/clone mapper.
        api=capture._NativeAPI();parent=str(PureWindowsPath(path).parent);name=PureWindowsPath(path).name
        with capture._directory(parent,api) as directory:
            raw=directory.read(name);handle=directory.files[name]['handle'];descriptor=C.c_void_p();text=C.c_void_p();length=C.c_uint32()
            info=0x00000005
            if api.a.GetSecurityInfo(handle,1,info,None,None,None,None,C.byref(descriptor)):raise ValueError('security_oracle_failed')
            fn=api.a.ConvertSecurityDescriptorToStringSecurityDescriptorW;fn.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32,C.POINTER(C.c_void_p),C.POINTER(C.c_uint32)];fn.restype=C.c_int
            try:
                if not fn(descriptor,1,info,C.byref(text),C.byref(length)):raise ValueError('security_oracle_failed')
                sddl=C.wstring_at(text)
            finally:
                if text:api.k.LocalFree(text)
                if descriptor:api.k.LocalFree(descriptor)
            from intune_iac.windows_directory import _FileInformation
            native=_FileInformation()
            if not api.k.GetFileInformationByHandle(handle,C.byref(native)):raise ValueError('attributes_oracle_failed')
            return {'sha256':sha(raw),'bytes':len(raw),'sddl':sddl,'attributes':int(native.attributes)}
    try:
        if sys.version_info[:2]!=(3,12) or C.sizeof(C.c_void_p)!=8:raise ValueError('native_cpython312_required')
        raw=Path(args.source_pins).read_bytes()
        if len(raw)>1024*1024 or sha(raw)!=args.source_pins_sha256:raise ValueError('source_pins_mismatch')
        pin=parse_json(raw)
        if set(pin)!={'source_commit','files'} or not re.fullmatch('[a-f0-9]{40}',pin['source_commit']) or pin['files']!=files:raise ValueError('reviewed_source_pin_required')
        result['declared_source_commit']=pin['source_commit'];result['commit_linkage']='Owner independently verifies file manifest against exact reviewed commit.';(out/'source-pins.json').write_bytes(raw)
        raw=Path(args.cases).read_bytes()
        if len(raw)>2*1024*1024 or sha(raw)!=args.cases_sha256:raise ValueError('cases_pin_mismatch')
        cases=parse_json(raw)
        if type(cases) is not dict or set(cases)!={'cases'} or len(cases['cases'])!=3:raise ValueError('three_disposable_cases_required')
        if {(c.get('fail_after_rename'),c.get('recovery')) for c in cases['cases']}!={(None,None),(1,'rollback'),(2,'complete')}:raise ValueError('required_recovery_cases_missing')
        if len({c['repo'].casefold() for c in cases['cases']})!=3:raise ValueError('distinct_disposable_checkouts_required')
        if len({c['id'] for c in cases['cases']})!=3:raise ValueError('distinct_case_ids_required')
        for case in cases['cases']:
            fields={'id','store','tenant','repo','proposal','digest','source_path','before_sha256','after_sha256','fail_after_rename','recovery'}
            if set(case)!=fields or not re.fullmatch('[a-z][a-z0-9-]{0,30}',case['id']):raise ValueError('case_shape_invalid')
            path=str(PureWindowsPath(case['repo']).joinpath(*case['source_path'].split('/')));before=snapshot(path)
            assert_check(case['id']+'/literal_before_hash',before['sha256']==case['before_sha256'])
            code,value=invoke(case,'review',['source-review','--proposal',case['proposal'],'--digest',case['digest']]);assert_check(case['id']+'/review_local_only',code==0 and value['result']['protected_plan_approval'] is False)
            _bind_review(case,value['result']);assert_check(case['id']+'/review_exact_target_bound',True)
            expires=str(time.time()+600);code,value=invoke(case,'apply',['source-edit','--proposal',case['proposal'],'--digest',case['digest'],'--expires-at',expires,'--acknowledge-local-file-edit'],case['fail_after_rename'])
            if case['fail_after_rename'] is None:
                assert_check(case['id']+'/applied',code==0 and value['result']['state']=='source_applied');identifier=value['result']['operation_id']
            else:
                assert_check(case['id']+'/interrupted_uncertain',code==3 and value['source_edit_outcome']['outcome_uncertain'] is True);identifier=value['source_edit_outcome']['operation_id']
                code,status=invoke(case,'pending',['source-edit-status','--source-root',case['repo'],'--operation',identifier]);assert_check(case['id']+'/pending',code==0 and status['result']['closed'] is False)
                code,value=invoke(case,'recover',['source-edit-recover','--source-root',case['repo'],'--operation',identifier,'--direction',case['recovery'],'--expires-at',str(time.time()+600),'--acknowledge-local-file-edit'])
                assert_check(case['id']+'/recovered',code==0 and value['result']['original_dispatch_uncertainty_preserved'] is True)
            after=snapshot(path);wanted=case['before_sha256'] if case['recovery']=='rollback' else case['after_sha256']
            assert_check(case['id']+'/literal_after_hash',after['sha256']==wanted)
            assert_check(case['id']+'/exact_acl_attributes',after['sddl']==before['sddl'] and after['attributes']==before['attributes'])
            code,status=invoke(case,'status',['source-edit-status','--source-root',case['repo'],'--operation',identifier]);assert_check(case['id']+'/closed',code==0 and status['result']['closed'] is True)
            assert_check(case['id']+'/no_protected_execution',status['result']['protected_execution_performed'] is False and status['result']['fresh_plan_required'] is True)
            (out/(case['id']+'-independent-snapshots.json')).write_text(json.dumps({'before':before,'after':after},indent=2)+'\n')
        result['status']='PASS';return finish(0)
    except (AppError,ValueError,TypeError,KeyError,OSError,subprocess.TimeoutExpired) as error:
        result['status']='FAIL';result['failure']={'type':type(error).__name__,'code':getattr(error,'code','native_source_edit_qualification_failed'),'storage_outcome':getattr(error,'storage_outcome',None)};return finish(1)
if __name__=='__main__':raise SystemExit(main())
