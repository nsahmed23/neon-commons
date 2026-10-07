"""Native-shaped dictionary entrypoints; actual SQLite, recorded Win32 only."""
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import unittest
from unittest.mock import patch

from intune_iac import windows_workbench as subject, windows_storage as storage
from intune_iac import workbench_provenance as provenance
from intune_iac.io import AppError
from plugin_tests import test_windows_capture_r4 as capture_fixture
from plugin_tests.test_windows_storage_r4 import ROOT, CANONICAL
from plugin_tests.test_workbench_provenance import policy, DEFINITION


class WindowsDictionaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=capture_fixture.WindowsCaptureTests()
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.make();self.store=self.fixture.store;self.api=self.fixture.api
        self.store.import_capture(self.fixture.path)
        storage._create_directory(ROOT,'package-assets',self.api)
        self.package=PureWindowsPath(ROOT)/'package-assets'
        self.store._package_directory=lambda:self.package
        for name in ('capability-map.json','vendor-documentation.json'):
            raw=(capture_fixture.PROJECT/'corrections/contracts'/name).read_bytes()
            storage._create_file(str(self.package),name,raw,self.api)
        raw=json.dumps(policy()).encode();storage._create_file(ROOT,'reference.json',raw,self.api)
        self.reference=self.store.reference_import(ROOT+'\\reference.json',hashlib.sha256(raw).hexdigest(),
            'a'*40,'https://learn.microsoft.com/example/unverified','LicenseRef-Invented')
        self.database=self.api.real(CANONICAL+'\\store\\observations.sqlite3')

    def test_same_dictionary_taxonomy_keeps_observation_reference_mapping_vendor_and_ai_separate(self):
        before=self.database.read_bytes()
        with patch.object(provenance,'_read',side_effect=AssertionError('POSIX reader reached')):
            value=self.store.dictionary(DEFINITION)
        self.assertEqual(len(value['entries']),1);entry=value['entries'][0]
        groups=entry['fact_provenance']['categories']
        self.assertEqual({k:v['record_count'] for k,v in groups.items()},
            {'vendor_documentation':1,'observed_value':1,'community_advice':1,'company_annotation':0,'local_mapping':1,'ai_interpretation':0})
        self.assertFalse(entry['fact_provenance']['cross_category_promotion'])
        observed=entry['actual_uses'][0]
        self.assertEqual(observed['object_id'],capture_fixture.P)
        self.assertEqual(observed['value']['choiceSettingValue']['value'],DEFINITION+'_2')
        self.assertFalse(observed['source']['source_authenticity_verified'])
        self.assertTrue(observed['source']['source_is_synthetic'])
        self.assertFalse(entry['references'][0]['source_authenticity_verified'])
        self.assertEqual(groups['ai_interpretation']['availability'],'not_implemented')
        self.assertEqual(self.database.read_bytes(),before);self.assertEqual(self.api.handles,{})

    def test_changed_vendor_bytes_fail_pinned_fact_boundary_without_database_write(self):
        before=self.database.read_bytes();path=self.api.real(CANONICAL+'\\package-assets\\vendor-documentation.json')
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(AppError) as caught:self.store.dictionary()
        self.assertEqual(caught.exception.code,'workbench_vendor_documentation_changed')
        self.assertEqual(self.database.read_bytes(),before);self.assertEqual(self.api.handles,{})

    def test_only_fixed_packaged_asset_names_are_admitted_before_file_access(self):
        before=list(self.api.events)
        for name in ('../vendor-documentation.json','C:\\outside','reference.json','vendor-documentation.json:stream'):
            with self.subTest(name=name),self.assertRaises(AppError) as caught:self.store._read_package_asset(name)
            self.assertEqual(caught.exception.code,'windows_workbench_package_asset_unsupported')
        self.assertEqual(self.api.events,before)

    def test_wrong_owner_of_packaged_file_fails_without_promoting_facts(self):
        original=self.api.file_metadata;before=self.database.read_bytes()
        def metadata(handle,sid):
            value=original(handle,sid)
            if '\\package-assets\\' in self.api.handles[handle][1]:value['owner_sid']='S-1-5-18'
            return value
        self.api.file_metadata=metadata
        with self.assertRaises(AppError):self.store.dictionary()
        self.assertEqual(self.database.read_bytes(),before);self.assertEqual(self.api.handles,{})

    def test_missing_package_asset_is_a_failure_and_preserves_retained_observations(self):
        source=self.api.real(CANONICAL+'\\package-assets\\capability-map.json')
        source.rename(source.with_suffix('.retained'))
        with self.assertRaises(AppError):self.store.dictionary()
        self.assertEqual(self.store.inspect(capture_fixture.P)['body']['name'],'Windows Privacy Pilot')
        self.assertTrue(source.with_suffix('.retained').exists())

    def test_readonly_text_dictionary_lineage_and_comparison_share_real_engine(self):
        path=Path(subject.__file__).resolve().parents[1]/'scripts/intune-windows-inspect.py'
        spec=importlib.util.spec_from_file_location('native_dictionary_text',path);app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
        before=self.database.read_bytes()
        with patch.object(app,'WindowsWorkbenchStore',lambda root,tenant:self.store):
            for args in (['dictionary','--query',DEFINITION],['lineage',capture_fixture.P],
                         ['reference-compare',capture_fixture.P,self.reference['artifact_id']]):
                out=io.StringIO();err=io.StringIO()
                with redirect_stdout(out),redirect_stderr(err):
                    code=app.main(['--qualification-only','--store',ROOT+'\\store','--tenant',capture_fixture.T,*args])
                self.assertEqual(code,0,err.getvalue());value=json.loads(out.getvalue())
                self.assertFalse(value['platform_qualified']);self.assertEqual(self.database.read_bytes(),before)
                if args[0]=='dictionary':self.assertEqual(value['result']['entries'][0]['identifier'],DEFINITION)
                elif args[0]=='lineage':self.assertEqual(value['result']['status'],'unknown')
                else:
                    self.assertEqual(value['result']['comparisons']['upstream_vs_observed']['status'],'different')
                    self.assertFalse(value['result']['execution_authorized'])

    def test_actual_text_help_and_native_host_gate_include_new_routes(self):
        if sys.platform=='win32':self.skipTest('Linux subprocess gate scope')
        path=Path(subject.__file__).resolve().parents[1]/'scripts/intune-windows-inspect.py'
        help_=subprocess.run([sys.executable,'-B',str(path),'--help'],capture_output=True,timeout=10)
        self.assertEqual(help_.returncode,0)
        for name in ('dictionary','lineage','reference-compare'):self.assertIn(name.encode(),help_.stdout)
        child=subprocess.run([sys.executable,'-B',str(path),'--qualification-only','--store',ROOT+'\\absent',
            '--tenant',capture_fixture.T,'dictionary'],capture_output=True,timeout=10)
        self.assertEqual(child.returncode,3)
        self.assertEqual(json.loads(child.stderr)['error']['code'],'windows_directory_platform_unsupported')


if __name__=='__main__':unittest.main()
