"""Wrapper transport tests; Linux assertions never qualify native Windows."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'


class BashLauncherContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native host ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "- quoted ' 雪"
        self.root.mkdir()
        self.wrapper = self.root / 'intune-workbench.sh'
        shutil.copyfile(SCRIPTS / self.wrapper.name, self.wrapper)
        self.capture = self.root / 'argv.json'
        (self.root / 'intune-iac.py').write_text(
            'import json,os,pathlib,sys\n'
            'pathlib.Path(os.environ["INTUNE_HOST_PROBE"]).write_text(json.dumps({'
            '"argv":sys.argv[1:],"isolated":sys.flags.isolated,"bytecode":sys.dont_write_bytecode,'
            '"exclusions":os.environ.get("MSYS2_ARG_CONV_EXCL"),'
            '"global_disable":os.environ.get("MSYS_NO_PATHCONV")}))\n'
            'sys.exit(int(os.environ.get("INTUNE_HOST_EXIT", "0")))\n', encoding='utf-8')
        self.env = dict(os.environ, INTUNE_HOST_PROBE=str(self.capture),
                        MSYS2_ARG_CONV_EXCL='*', MSYS_NO_PATHCONV='1')

    def run_wrapper(self, args, **kwargs):
        return subprocess.run(['/bin/bash', '--noprofile', '--norc', str(self.wrapper), *args],
                              capture_output=True, env=self.env, timeout=15, **kwargs)

    def test_literal_transport_scoped_msys_and_isolated_python(self):
        args = ['/beta/deviceManagement/configurationPolicies', '/v1.0/groups',
                str(self.root / 'real filesystem.txt'), '-leading', 'quoted " value',
                "single ' value", '雪', 'CR\r\nLF', '$(touch harmless-marker)',
                '\x1b]52;c;SYNTHETIC\x07']
        result = self.run_wrapper(['--python', sys.executable, '--', *args])
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = json.loads(self.capture.read_text())
        self.assertEqual(captured['argv'], args)
        self.assertEqual(captured['exclusions'], '/beta/;/v1.0/')
        self.assertIsNone(captured['global_disable'])
        self.assertEqual(captured['isolated'], 1)
        self.assertTrue(captured['bytecode'])
        self.assertEqual(self.env['MSYS2_ARG_CONV_EXCL'], '*')
        self.assertEqual(self.env['MSYS_NO_PATHCONV'], '1')
        self.assertFalse((self.root / 'harmless-marker').exists())
        self.assertEqual(result.stdout, b'')

    def test_missing_or_relative_interpreter_never_falls_back(self):
        for args in (['--', '--help'], ['--python', 'python', '--', '--help'],
                     ['--python', sys.executable, '--help']):
            with self.subTest(args=args):
                result = self.run_wrapper(args)
                self.assertEqual(result.returncode, 64)
                self.assertFalse(self.capture.exists())

    def test_untrusted_missing_executable_path_is_not_echoed(self):
        result = self.run_wrapper(['--python', '/missing/\x1b]52;c;CANARY\x07', '--'])
        self.assertEqual(result.returncode, 66)
        self.assertNotIn(b'CANARY', result.stderr)
        self.assertFalse(self.capture.exists())

    def test_native_nonzero_is_preserved(self):
        self.env['INTUNE_HOST_EXIT'] = '37'
        result = self.run_wrapper(['--python', sys.executable, '--', '--help'])
        self.assertEqual(result.returncode, 37)

    def test_actual_application_help_uses_same_launcher(self):
        result = subprocess.run(['/bin/bash', '--noprofile', '--norc',
                                 str(SCRIPTS / 'intune-workbench.sh'), '--python',
                                 sys.executable, '--', 'workbench', '--help'],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'workbench', result.stdout)


class QualificationProcedureContract(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('windows_workbench_qualifier',
                           SCRIPTS / 'qualify-windows-workbench.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_non_windows_is_explicitly_blocked_without_native_probe(self):
        if sys.platform == 'win32':
            self.skipTest('Non-Windows refusal is a Linux negative; run the native procedure on Windows.')
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'receipt'
            result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'qualify-windows-workbench.py'),
                                     '--plugin', str(ROOT), '--output', str(out)],
                                    capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 3, result.stderr)
            receipt = json.loads((out / 'receipt.json').read_text())
            self.assertEqual(receipt['status'], 'BLOCKED')
            self.assertFalse(receipt['native_windows_qualified'])
            self.assertEqual(receipt['commands'], [])
            self.assertEqual(receipt['blockers'][0]['code'], 'native_windows_host_required')
            self.assertEqual(receipt['implementation_gates'],[])
            procedure=json.loads((out/'procedure-manifest.json').read_text())
            self.assertEqual(procedure['required_implementation_gate']['current_native_windows_status'],'UNSUPPORTED')

    def test_unavailable_store_is_a_required_unsupported_gate_not_functional_pass(self):
        module=self.module()
        document={'host_capabilities':{'schema_version':'intune-host-capabilities/1','profiles':{
            'workbench_store':{'status':'UNSUPPORTED','missing_primitives':['effective_uid','fcntl_lock']}}}}
        value=module.store_profile_gate(document)
        self.assertEqual(value['status'],'UNSUPPORTED')
        self.assertEqual(value['functional_qualification'],'BLOCKED')
        self.assertEqual(value['missing_primitives'],['effective_uid','fcntl_lock'])
        document['host_capabilities']['profiles']['workbench_store']={'status':'IMPLEMENTED','missing_primitives':[]}
        value=module.store_profile_gate(document)
        self.assertEqual(value['status'],'IMPLEMENTED')
        self.assertEqual(value['functional_qualification'],'NOT_STARTED')

    def test_missing_or_inconsistent_implementation_report_cannot_admit_store(self):
        module=self.module()
        for profile in ({}, {'status':'PASS','missing_primitives':[]},
                        {'status':'IMPLEMENTED','missing_primitives':['fcntl_lock']},
                        {'status':'UNSUPPORTED','missing_primitives':[]},
                        {'status':'UNSUPPORTED','missing_primitives':'fcntl_lock'}):
            with self.subTest(profile=profile):
                document={'host_capabilities':{'schema_version':'intune-host-capabilities/1','profiles':{'workbench_store':profile}}}
                with self.assertRaisesRegex(ValueError,'host_capability_report_required'):
                    module.store_profile_gate(document)

    def test_required_unsupported_or_unfinished_route_never_becomes_pass(self):
        module=self.module(); assertions=[{'passed':True}]
        unsupported={'status':'UNSUPPORTED','functional_qualification':'BLOCKED'}
        passed={'status':'PASS','functional_qualification':'PASS'}
        self.assertEqual(module.qualification_status(assertions,[unsupported]),'UNSUPPORTED')
        self.assertEqual(module.qualification_status(assertions,[passed,unsupported]),'UNSUPPORTED')
        self.assertEqual(module.qualification_status(assertions,[{'status':'IMPLEMENTED','functional_qualification':'NOT_STARTED'}]),'FAIL')
        self.assertEqual(module.qualification_status(assertions,[]),'FAIL')
        self.assertEqual(module.qualification_status([{'passed':False}],[unsupported]),'FAIL')
        self.assertEqual(module.qualification_status(assertions,[passed,passed]),'PASS')

    def test_output_reuse_is_rejected_and_existing_evidence_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'existing'; out.mkdir()
            marker = out / 'receipt.json'; marker.write_bytes(b'preserve contrary evidence\r\n')
            before = hashlib.sha256(marker.read_bytes()).hexdigest()
            result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'qualify-windows-workbench.py'),
                                     '--plugin', str(ROOT), '--output', str(out)],
                                    capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(hashlib.sha256(marker.read_bytes()).hexdigest(), before)

    def test_drive_conversion_preserves_spaces_unicode_and_rejects_unc(self):
        module = self.module()
        self.assertEqual(module.git_bash_path("C:\\Lab Space\\-雪\\file's.json"),
                         "/c/Lab Space/-雪/file's.json")
        for value in ('relative/file', '\\\\server\\share\\file', '/tmp/file'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError): module.git_bash_path(value)

    def test_powershell_uses_argumentlist_and_preserves_primary_failure_contract(self):
        text = (SCRIPTS / 'intune-workbench.ps1').read_text()
        self.assertIn('.ArgumentList.Add(', text)
        self.assertIn('Resolve-WorkbenchExitCode', text)
        self.assertNotIn('Invoke-Expression', text)
        self.assertNotIn('.Arguments =', text)
        self.assertNotIn('$env:MSYS2_ARG_CONV_EXCL', text)
        self.assertIn('powershell_argument_list_required', text)

    def test_package_binding_rejects_substitution_and_extra_files_without_deletion(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);root=base/'package';root.mkdir()
            payload=root/'plan.bin';payload.write_bytes(b'exact\r\n\x00\xff')
            archive=base/'runtime.zip'
            with zipfile.ZipFile(archive,'w') as zipped:
                zipped.writestr('intune-iac/plan.bin',payload.read_bytes())
            expected=hashlib.sha256(archive.read_bytes()).hexdigest()
            result=module.package_identity(root,archive,expected)
            self.assertEqual(result['files']['plan.bin']['bytes'],9)
            payload.write_bytes(b'substituted')
            with self.assertRaisesRegex(ValueError,'package_file_mismatch'):
                module.package_identity(root,archive,expected)
            payload.write_bytes(b'exact\r\n\x00\xff')
            extra=root/'unexpected';extra.write_bytes(b'preserve this discrepancy')
            with self.assertRaisesRegex(ValueError,'package_file_set_mismatch'):
                module.package_identity(root,archive,expected)
            self.assertEqual(extra.read_bytes(),b'preserve this discrepancy')

    def test_package_binding_rejects_case_collision_traversal_and_wrong_digest(self):
        module=self.module()
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);root=base/'package';root.mkdir()
            (root/'a').write_bytes(b'a')
            for names,code in [(['intune-iac/a','intune-iac/A'],'package_collision'),
                               (['intune-iac/../escape'],'unsafe_package_member')]:
                archive=base/(code+'.zip')
                with zipfile.ZipFile(archive,'w') as zipped:
                    for name in names:zipped.writestr(name,b'a')
                expected=hashlib.sha256(archive.read_bytes()).hexdigest()
                with self.assertRaisesRegex(ValueError,code):module.package_identity(root,archive,expected)
                with self.assertRaisesRegex(ValueError,'package_digest_mismatch'):
                    module.package_identity(root,archive,'0'*64)


if __name__ == '__main__':
    unittest.main()
