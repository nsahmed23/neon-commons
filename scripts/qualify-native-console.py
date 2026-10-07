"""Manual actual-Windows console harness; never grants native platform approval.

Run from conhost/Windows Terminal PowerShell with an otherwise idle console.
This harness exercises console APIs only, not a Workbench store or cloud route.
No logs contain arbitrary typed text: the expected fixed fixture is compared in
memory and only its match result is retained. Escape/interrupt never passes.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project',required=True,help='Reviewed full project containing intune_iac')
parser.add_argument('--output',required=True,help='NEW local laboratory evidence directory')
args=parser.parse_args();project=Path(args.project).absolute();sys.path.insert(0,str(project))
from intune_iac import windows_terminal as terminal
console=terminal.NativeConsole()  # Reject unsupported host before creating output.
root=Path(args.output).absolute();root.mkdir(exist_ok=False)
source=Path(terminal.__file__);before=hashlib.sha256(source.read_bytes()).hexdigest()
receipt={'schema_version':'native-console-manual-qualification/1','status':'STARTED','platform_qualified':False,
    'production_approved':False,'source_sha256':before,'os_name':os.name,'sys_platform':sys.platform,
    'scope':'Actual console APIs only; no native store, Workspace integration, tenant/provider or device evidence',
    'before_modes':{'input':console.original_input,'output':console.original_output},'checks':{}}
checks=receipt['checks']
try:
    with console.session():
        receipt['during_modes']={'input':console.api.mode(console.input_handle),'output':console.api.mode(console.output_handle)}
        checks['native_mode_changed']=receipt['before_modes']!=receipt['during_modes']
        console.write('\x1b[2J\x1b[HConsole fixture only. No engine command can run.\r\n'
                      'Press Up, Down, then Enter, then Ctrl+Enter. Escape aborts.\r\n')
        expected=['up','down','enter','submit'];observed=[];deadline=time.monotonic()+60
        while len(observed)<4 and time.monotonic()<deadline:
            event=console.key_reader.read()
            if event in ('escape','interrupt','eof'):raise KeyboardInterrupt('Operator aborted fixture')
            if event in expected:observed.append(event)
        checks['navigation_enter_and_explicit_submit']=observed==expected
        console.write('Paste exactly FIRST followed by a newline then SECOND.\r\n'
                      'After the paste completes, press Ctrl+Enter once to finish this phase.\r\n')
        collected=[];ordinary_enters=0;submitted=False;deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            event=console.key_reader.read()
            if event in ('escape','interrupt','eof'):raise KeyboardInterrupt('Operator aborted fixture')
            if event=='submit':submitted=True;break
            if event=='enter':ordinary_enters+=1;collected.append('\n')
            elif isinstance(event,tuple):collected.append(event[1])
            if sum(map(len,collected))>128:raise ValueError('Input fixture exceeded bound')
        # The operator must independently affirm submit happened after the
        # paste; this trace alone cannot prove the provenance of key events.
        checks['paste_fixture_equals_expected']=''.join(collected)=='FIRST\nSECOND'
        checks['pasted_newline_was_not_submit']=ordinary_enters==1
        checks['explicit_completion_gesture_observed']=submitted
        receipt['paste_provenance_requires_operator_attestation']=True
        console.write('Resize the console now, then press Ctrl+Enter.\r\n')
        size_before=console.size();resize=False;deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            event=console.key_reader.read()
            if event in ('escape','interrupt','eof'):raise KeyboardInterrupt('Operator aborted fixture')
            if event=='redraw' or console.size()!=size_before:resize=True
            if event=='submit':break
        checks['actual_resize_observed']=resize
    receipt['after_modes']={'input':console.api.mode(console.input_handle),'output':console.api.mode(console.output_handle)}
    checks['exact_native_modes_restored']=receipt['after_modes']==receipt['before_modes']
    checks['source_unchanged']=before==hashlib.sha256(source.read_bytes()).hexdigest()
    receipt['status']='PASS_BOUNDED_MANUAL_CONSOLE' if all(checks.values()) else 'FAIL'
except BaseException as error:
    receipt['status']='FAIL';receipt['error']=getattr(error,'code',type(error).__name__)
    receipt['cleanup_failures']=getattr(error,'native_console_cleanup_failures',[])
    raise
finally:
    (root/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    (root/'tested-windows_terminal.py').write_bytes(source.read_bytes())
