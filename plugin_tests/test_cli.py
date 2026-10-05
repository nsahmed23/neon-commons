import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT/'scripts/intune-iac.py'


class CliTests(unittest.TestCase):
    def cli(self, *args, input=None):
        return subprocess.run([sys.executable,str(CLI),*map(str,args)],input=input,text=True,capture_output=True,cwd='/tmp')

    def test_relocatable_help_does_not_need_cwd(self):
        result = self.cli('--help')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('wizard',result.stdout)

    def test_doctor_does_not_claim_live_qualification(self):
        result = self.cli('doctor')
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout)
        self.assertFalse(report['live_qualified'])
        self.assertEqual(report['capabilities']['cloud_apply'],'unavailable')

    def test_inspect_reports_blockers_with_exit_two(self):
        result=self.cli('inspect','--input',ROOT/'examples/access-denied/input/export.json','--context',ROOT/'examples/context.json')
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'],'blocked')

    def test_mcp_initialize_list_and_unknown_tool(self):
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'execute_shell','arguments':{'command':'echo bad'}}}]
        result=self.cli('mcp',input='\n'.join(map(json.dumps,requests))+'\n')
        self.assertEqual(result.returncode,0,result.stderr)
        lines=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([v['id'] for v in lines],[1,2,3])
        self.assertTrue(any(t['name']=='intune_inspect' for t in lines[1]['result']['tools']))
        self.assertEqual(lines[2]['error']['code'],-32602)

    def test_mcp_preview_never_creates_state_or_output(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'project'; state=Path(td)/'state'
            requests=[{'jsonrpc':'2.0','id':0,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}},
              {'jsonrpc':'2.0','method':'notifications/initialized'},
              {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'intune_preview','arguments':{'action':'generate','parameters':{'input':str(ROOT/'examples/supported/input/export.json'),'context':str(ROOT/'examples/context.json'),'output':str(out)},'state_dir':str(state)}}}]
            result=self.cli('mcp','--read-root',ROOT,'--write-root',td,input='\n'.join(map(json.dumps,requests))+'\n')
            self.assertEqual(result.returncode,0,result.stderr)
            lines=[json.loads(line) for line in result.stdout.splitlines()]
            self.assertFalse(lines[-1]['result'].get('isError',False),lines)
            self.assertFalse(state.exists());self.assertFalse(out.exists())

    def test_mcp_preserved_output_conflict_is_tool_error(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'project';out.mkdir();(out/'user.txt').write_text('keep')
            requests=[{'jsonrpc':'2.0','id':0,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}},
              {'jsonrpc':'2.0','method':'notifications/initialized'},
              {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'intune_run_local','arguments':{'action':'generate','parameters':{'input':str(ROOT/'examples/supported/input/export.json'),'context':str(ROOT/'examples/context.json'),'output':str(out)},'state_dir':str(Path(td)/'state')}}}]
            result=self.cli('mcp','--read-root',ROOT,'--write-root',td,input='\n'.join(map(json.dumps,requests))+'\n')
            lines=[json.loads(line) for line in result.stdout.splitlines()]
            self.assertTrue(lines[-1]['result']['isError'])
            self.assertEqual((out/'user.txt').read_text(),'keep')


if __name__ == '__main__': unittest.main()
