"""Host capability controls; fixture simulations are not native Windows evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from intune_iac.io import AppError
from intune_iac import host_capabilities as host

ROOT = Path(__file__).resolve().parents[1]


class HostCapabilityTests(unittest.TestCase):
    def test_actual_host_report_never_claims_qualification(self):
        value = host.report()
        self.assertEqual(value['schema_version'], 'intune-host-capabilities/1')
        self.assertEqual(value['host']['sys_platform'], sys.platform)
        self.assertFalse(value['native_windows_qualified'])
        self.assertFalse(value['platform_qualified'])
        self.assertFalse(value['production_approved'])
        for profile in value['profiles'].values():
            self.assertIn(profile['status'], ('IMPLEMENTED','UNSUPPORTED'))
            self.assertFalse(profile['platform_qualified'])
            self.assertFalse(profile['production_approved'])
            self.assertEqual(profile['status']=='IMPLEMENTED', not profile['missing_primitives'])

    def test_doctor_availability_uses_actual_required_host_primitives(self):
        from intune_iac import cli
        facts={key:False for key in host._facts()}
        with patch.object(host,'_facts',return_value=facts):
            value=cli.doctor()
        self.assertEqual(value['capabilities']['workbench'],'unsupported_host')
        for route in ('protected_execution','provider_journey','signed_approval'):
            self.assertEqual(value['capabilities'][route],'unsupported_platform')
        self.assertIn('Runtime package dependencies only',value['status_scope'])
        self.assertFalse(value['live_qualified'])
        self.assertFalse(value['native_host_qualified'])

    def test_fixture_windows_absence_is_implementation_gap_not_missing_receipt(self):
        facts = {key:False for key in host._facts()}
        facts['x86_64'] = True; facts['fsync'] = True
        with patch.object(host, '_facts', return_value=facts):
            value = host.report()
            for name in ('workbench_store','graph_observer','protected_worker','artifact_vault','visual_workspace'):
                self.assertEqual(value['profiles'][name]['status'], 'UNSUPPORTED')
                with self.assertRaises(AppError) as raised: host.require_profile(name)
                self.assertEqual(raised.exception.code, 'host_profile_unsupported')
                self.assertEqual(raised.exception.details['profile'], name)
                self.assertFalse(raised.exception.details['platform_qualified'])
            self.assertIn('effective_uid',value['profiles']['workbench_store']['missing_primitives'])
            self.assertIn('DACL', ' '.join(value['profiles']['workbench_store']['required_implementation']))
            self.assertIn('process', ' '.join(value['profiles']['protected_worker']['required_implementation']))

    def test_missing_fcntl_blocks_import_dependency_including_vault_validator(self):
        facts = {key:True for key in host._facts()}; facts['fcntl_lock'] = False
        with patch.object(host, '_facts', return_value=facts):
            with self.assertRaises(AppError) as raised: host.require_profile('workbench_store')
            self.assertEqual(raised.exception.details['missing_primitives'], ['fcntl_lock'])
            # The vault's admitted validator imports approval_authority, which
            # imports fcntl even though encryption does not acquire its lock.
            with self.assertRaises(AppError) as vault: host.require_profile('artifact_vault')
            self.assertEqual(vault.exception.details['missing_primitives'], ['fcntl_lock'])

    def test_architecture_discovery_without_uname_does_not_spawn(self):
        with patch.object(os, 'uname', None, create=True), \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('unexpected process')):
            self.assertEqual(host._machine(), 'unknown')
            self.assertEqual(host.report()['host']['machine'], 'unknown')

    def test_unknown_profile_rejected_without_echoing_untrusted_text(self):
        with self.assertRaises(AppError) as raised: host.require_profile('bad\x1b]52;c;CANARY\x07')
        self.assertEqual(raised.exception.code, 'host_profile_unknown')
        self.assertNotIn('CANARY',raised.exception.message)
        self.assertNotIn('\x1b',raised.exception.message)

    def test_report_reads_no_files_or_credentials_and_starts_no_process(self):
        with patch.dict(os.environ, {'CLIENT_SECRET':'HOST-SECRET-CANARY'}), \
             patch.object(os, 'open', side_effect=AssertionError('unexpected open')), \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('unexpected process')):
            value = host.report()
        self.assertNotIn('HOST-SECRET-CANARY',json.dumps(value))

    def test_returned_report_cannot_change_future_requirements(self):
        value=host.report(); value['profiles']['workbench_store']['required_primitives'].clear()
        self.assertIn('effective_uid',host.report()['profiles']['workbench_store']['required_primitives'])

    def test_module_is_portable_when_actual_fcntl_import_is_denied(self):
        code = r'''
import importlib.abc,json,sys
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('fcntl','termios'):raise ModuleNotFoundError('native module unavailable fixture')
sys.modules.pop('fcntl',None);sys.modules.pop('termios',None);sys.meta_path.insert(0,Deny())
from intune_iac.host_capabilities import report,require_profile
from intune_iac.io import AppError
value=report()
try:require_profile('workbench_store')
except AppError as error:
 print(json.dumps({'schema':value['schema_version'],'profile':value['profiles']['workbench_store'],'error':error.code,'details':error.details}))
else:raise AssertionError('unsupported host dispatched')
'''
        result=subprocess.run([sys.executable,'-B','-c',code],cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout)
        self.assertEqual(value['error'],'host_profile_unsupported')
        self.assertIn('fcntl_lock',value['profile']['missing_primitives'])
        self.assertEqual(value['details']['status'],'UNSUPPORTED')

    def test_actual_cli_rejects_missing_store_dependency_before_creation(self):
        code = r'''
import importlib.abc,runpy,sys
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='fcntl':raise ModuleNotFoundError('fixture native module unavailable')
sys.modules.pop('fcntl',None);sys.meta_path.insert(0,Deny())
sys.argv=[sys.argv[1],*sys.argv[2:]]
runpy.run_path(sys.argv[0],run_name='__main__')
'''
        with tempfile.TemporaryDirectory() as directory:
            destination=Path(directory)/'must-not-be-created'
            result=subprocess.run([sys.executable,'-B','-c',code,str(ROOT/'scripts/intune-iac.py'),
                'workbench','init','--root',str(destination),'--tenant','91111111-1111-4111-8111-111111111111'],
                cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,2,result.stderr)
            value=json.loads(result.stderr)['error']
            self.assertEqual(value['code'],'host_profile_unsupported')
            self.assertEqual(value['details']['profile'],'workbench_store')
            self.assertFalse(destination.exists())
            self.assertNotIn('Traceback',result.stderr)

    def test_actual_observer_cli_rejects_missing_linux_after_store_prerequisites(self):
        # Fixture changes discovery only; the actual CLI and adapter gate run.
        # This is not a native macOS/Windows service qualification.
        code = r'''
import runpy,sys
from intune_iac import host_capabilities as h
original=h._facts
def facts():
 value=original();value['linux']=False;value['procfs']=False;return value
h._facts=facts
sys.argv=[sys.argv[1],*sys.argv[2:]]
runpy.run_path(sys.argv[0],run_name='__main__')
'''
        with tempfile.TemporaryDirectory() as directory:
            destination=Path(directory)/'must-not-be-opened'
            result=subprocess.run([sys.executable,'-B','-c',code,str(ROOT/'scripts/intune-iac.py'),
                'workbench','observer-status','--job',str(destination)],cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,2,result.stderr)
            value=json.loads(result.stderr)['error']
            self.assertEqual(value['code'],'host_profile_unsupported')
            self.assertEqual(value['details']['profile'],'graph_observer')
            self.assertIn('linux',value['details']['missing_primitives'])
            self.assertFalse(destination.exists())


if __name__=='__main__':unittest.main()
