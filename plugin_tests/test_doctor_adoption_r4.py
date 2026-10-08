"""Actual doctor/CLI contracts; no provider dispatch or live qualification."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'


class DoctorAdoptionTests(unittest.TestCase):
    def cli(self, *arguments, missing_primitives=False):
        argv = [sys.executable, '-B', str(CLI), *arguments]
        if missing_primitives:
            code = '''import runpy,sys
from intune_iac import host_capabilities as host
keys=tuple(host._facts())
host._facts=lambda:dict.fromkeys(keys,False)
sys.argv=[sys.argv[1],*sys.argv[2:]]
runpy.run_path(sys.argv[0],run_name='__main__')
'''
            argv = [sys.executable, '-B', '-c', code, str(CLI), *arguments]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT))
        with tempfile.TemporaryDirectory() as unrelated:
            result = subprocess.run(argv, cwd=unrelated, env=env, capture_output=True,
                                    text=True, timeout=20)
            self.assertEqual(list(Path(unrelated).iterdir()), [])
        return result

    def test_actual_doctor_reports_implemented_import_without_qualification(self):
        result = self.cli('doctor')
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        route = value['route_scope']['adoption']
        self.assertEqual(route['durable_protected_service_import'],
                         'implemented_separately_approved_state_only_import')
        self.assertEqual(route['native_service_preparation'], 'durable_manifest_preparation_and_review_cli')
        self.assertEqual(route['controller_dispatch'], 'exact_signed_approval_and_process_held_runtime')
        self.assertEqual(route['verification'], 'independent_state_and_graph_readback_plus_no_change_first_plan')
        self.assertEqual(route['local_native_evidence'], 'separate_source_and_artifact_bound_receipts')
        discovered = value['host_capabilities']['profiles']['protected_worker']['status'] == 'IMPLEMENTED'
        self.assertIs(route['host_prerequisites_discovered'], discovered)
        expected = ('separately_approved_protected_service_and_legacy_provider_prepare'
                    if discovered else 'unsupported_platform')
        self.assertEqual(value['capabilities']['state_import'], expected)
        for key in ('terminal_dispatches_import', 'platform_qualified', 'live_qualified', 'production_approved'):
            self.assertIs(route[key], False)
        self.assertFalse(value['live_qualified']); self.assertFalse(value['native_host_qualified'])
        self.assertEqual(route['requires'], ['reviewed_host_policy', 'exact_runtime_and_tool_pins',
                         'authenticated_target', 'complete_declared_ownership_scan',
                         'separate_exact_import_approval', 'qualified_execution_platform',
                         'organizational_production_approval'])

    def test_unavailable_host_retains_implementation_but_denies_adoption(self):
        result = self.cli('doctor', missing_primitives=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        route = value['route_scope']['adoption']
        self.assertEqual(route['durable_protected_service_import'],
                         'implemented_separately_approved_state_only_import')
        self.assertFalse(route['host_prerequisites_discovered'])
        self.assertEqual(value['capabilities']['state_import'], 'unsupported_platform')
        with tempfile.TemporaryDirectory() as temporary:
            job = Path(temporary) / 'uncreated-job'
            denied = self.cli('adoption', 'status', '--job-root', str(job),
                              '--policy', str(Path(temporary) / 'absent-policy.json'), missing_primitives=True)
            self.assertEqual(denied.returncode, 2, denied.stdout)
            self.assertEqual(json.loads(denied.stderr)['error']['code'], 'host_profile_unsupported')
            self.assertFalse(job.exists())

    def test_actual_help_exposes_review_recovery_without_execution_command(self):
        result = self.cli('adoption', '--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        for route in ('prepare', 'review', 'status', 'attach', 'cancel', 'recover',
                      'recovery-plan-prepare', 'recovery-plan-review', 'recovery-plan-status',
                      'recovery-plan-attach', 'recovery-plan-cancel', 'recovery-plan-recover'):
            self.assertIn(route, result.stdout)
        for forbidden in ('run', 'execute', 'import'):
            denied = self.cli('adoption', forbidden)
            self.assertEqual(denied.returncode, 2)
            self.assertIn('invalid choice', denied.stderr)


if __name__ == '__main__': unittest.main()
