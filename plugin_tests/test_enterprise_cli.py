"""Command integration preserves uncertainty and credential boundaries."""
import contextlib
import io
import json
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from intune_iac.cli import execute, exit_code, main, parser
from intune_iac.execution import LocalFixtureAdapter, create_local_fixture, prepare_operation
from intune_iac.io import write_json
from plugin_tests.test_execution import plan


class EnterpriseCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def call(self, argv):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main(argv)
        return code, json.loads(output.getvalue() or errors.getvalue())

    def fixture(self):
        adapter = create_local_fixture(self.root / 'fixture', policy={'id':'one','value':1}, assignments=[],
                                       desired_policy={'id':'one','value':2}, desired_assignments=[{'id':'target'}])
        request = self.root / 'request.json'
        write_json(request, prepare_operation(adapter))
        argv = ['simulation','run','--root',str(adapter.root),'--request',str(request),
                '--state-dir',str(self.root / 'journal')]
        return adapter, argv

    def test_locked_actual_simulation_is_not_success_exit(self):
        adapter, argv = self.fixture()
        adapter.lock_path.mkdir()
        code, result = self.call(argv)
        self.assertEqual(result['status'], 'locked')
        self.assertNotEqual(code, 0)

    def test_lost_response_after_write_is_not_success_exit(self):
        adapter, argv = self.fixture()
        original = LocalFixtureAdapter.execute_step
        def lost_response(instance, *args, **kwargs):
            original(instance, *args, **kwargs)
            raise OSError('synthetic lost response')
        with patch.object(LocalFixtureAdapter, 'execute_step', lost_response):
            code, result = self.call(argv)
        self.assertEqual(result['status'], 'reconciliation_required')
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads((adapter.root/'policy.json').read_text())['value'], 2)
        self.assertTrue(adapter.lock_path.exists())

    def test_plan_review_codes_and_redaction(self):
        path = self.root / 'plan.json'
        for action, expected in [('no-op', 0), ('update', 2), ('delete', 2)]:
            write_json(path, plan(action))
            code, result = self.call(['plan','review','--input',str(path)])
            self.assertEqual(code, expected)
            self.assertFalse(result['execution_authorized'])

    def test_invalid_target_is_nonzero_and_collect_needs_explicit_tokens(self):
        path = self.root / 'target.json';write_json(path, {'CANARY':'secret'})
        code, result = self.call(['target','inspect','--input',str(path)])
        self.assertEqual(code, 3)
        self.assertNotIn('CANARY', json.dumps(result))
        with patch.dict('os.environ', {}, clear=True):
            code, result = self.call(['target','collect','--input',str(path)])
        self.assertEqual(code, 3)
        self.assertEqual(result['error']['code'], 'missing_explicit_credentials')

    def test_guided_flag_is_explicit(self):
        args = parser().parse_args(['wizard','--session','example.json','--guided'])
        self.assertTrue(args.guided)

    def test_new_read_tools_work_over_real_mcp_stdio_with_explicit_read_authority(self):
        path=self.root/'plan.json';write_json(path,plan())
        target=self.root/'target.json';write_json(target,{})
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'intune_plan_review','arguments':{'input':str(path)}}},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'intune_target_inspect','arguments':{'input':str(target)}}}]
        launcher=Path(__file__).resolve().parents[1]/'scripts/intune-iac.py'
        result=subprocess.run([sys.executable,str(launcher),'mcp','--read-root',str(self.root)],input=''.join(json.dumps(r)+'\n' for r in requests),capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        responses=[json.loads(line) for line in result.stdout.splitlines()]
        review=json.loads(responses[1]['result']['content'][0]['text'])
        self.assertFalse(review['execution_authorized'])
        self.assertEqual(review['status'],'no_change')
        self.assertTrue(responses[2]['result']['isError'])
