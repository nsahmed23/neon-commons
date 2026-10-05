import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import mcp, runner

ROOT = Path(__file__).resolve().parents[1]


class RepositoryInterfaceTests(unittest.TestCase):
    def test_cli_exposes_repository_and_repository_wizard_arguments(self):
        result = subprocess.run([sys.executable, str(ROOT/'scripts/intune-iac.py'), 'repository', '--help'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('resolve', result.stdout)
        result = subprocess.run([sys.executable, str(ROOT/'scripts/intune-iac.py'), 'wizard', '--help'], text=True, capture_output=True)
        self.assertIn('--repo', result.stdout)
        self.assertIn('--stack', result.stdout)
        self.assertIn('--component', result.stdout)

    def test_read_only_actions_are_in_fixed_registry(self):
        for name in ['repository_inspect', 'repository_resolve']:
            self.assertIn(name, runner.REGISTRY)
            self.assertFalse(runner.REGISTRY[name]['write'])

    def test_mcp_has_closed_read_only_repository_tools(self):
        for name in ['intune_repository_inspect', 'intune_repository_resolve']:
            entry = next((t for t in mcp.TOOLS if t['name'] == name), None)
            self.assertIsNotNone(entry)
            self.assertTrue(entry['annotations']['readOnlyHint'])
            self.assertFalse(entry['inputSchema']['additionalProperties'])

    def test_repository_action_rejects_extra_parameters_without_writes(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)/'state'
            result = runner.preview('repository_resolve', {'root': td, 'stack': 'dev', 'component': 'intune', 'shell': 'bad'}, state)
            self.assertEqual(result['error']['code'], 'invalid_parameters')
            self.assertFalse(state.exists())

    def make_repository(self, root):
        repo = root/'repo'
        (repo/'stacks').mkdir(parents=True)
        (repo/'components/terraform/app').mkdir(parents=True)
        (repo/'atmos.yaml').write_text('stacks: {base_path: stacks}\n')
        (repo/'stacks/dev.yaml').write_text('components:\n  terraform:\n    app:\n      env: {SECRET: private-canary}\n')
        (repo/'components/terraform/app/main.tf').write_text('# initial\n')
        return repo

    def test_runner_rejects_result_not_bound_to_repository_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = self.make_repository(root)
            with patch('intune_iac.runner._dispatch', return_value={'status':'resolved','source_fingerprint':'0'*64}):
                result = runner.run('repository_resolve', {'root':str(repo),'stack':'dev','component':'app'}, root/'state')
            self.assertEqual(result['status'], 'rejected')
            self.assertEqual(result['error']['code'], 'postcondition_failed')

    def test_preview_binds_relevant_repository_bytes_and_does_not_write(self):
        from intune_iac.io import AppError
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = self.make_repository(root); state = root/'state'
            proposal = runner.preview('repository_resolve', {'root':str(repo),'stack':'dev','component':'app'}, state)
            self.assertEqual(proposal['status'],'ready', proposal)
            self.assertFalse(state.exists())
            (repo/'components/terraform/app/main.tf').write_text('# changed\n')
            with self.assertRaises(AppError) as caught:
                runner._recheck(proposal['proposal'])
            self.assertEqual(caught.exception.code, 'evidence_changed')

    def test_actual_cli_mcp_and_runner_reports_do_not_expose_values(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = self.make_repository(root)
            result = subprocess.run([sys.executable,str(ROOT/'scripts/intune-iac.py'),'repository','resolve','--root',str(repo),'--stack','dev','--component','app'],text=True,capture_output=True,cwd='/tmp')
            self.assertEqual(result.returncode,0,result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['status'],'resolved')
            self.assertNotIn('effective',report)
            self.assertNotIn('private-canary',result.stdout)
            via_mcp=mcp.call_tool('intune_repository_resolve',{'root':str(repo),'stack':'dev','component':'app'},authority=mcp.FilesystemAuthority([repo],[]))
            self.assertEqual(via_mcp,report)
            outcome=runner.run('repository_resolve',{'root':str(repo),'stack':'dev','component':'app'},root/'state')
            self.assertEqual(outcome['status'],'succeeded_verified',outcome)
            self.assertEqual(outcome['result'],report)
            self.assertNotIn('private-canary',json.dumps(outcome))


if __name__ == '__main__':
    unittest.main()
