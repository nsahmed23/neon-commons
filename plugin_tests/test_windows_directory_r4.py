"""Native API contract fixtures are not native Windows qualification."""
import copy
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import windows_directory as wd
from intune_iac.io import AppError

SID='S-1-5-21-111-222-333-1001'
VOLUME='\\\\?\\Volume{12345678-1234-1234-1234-123456789abc}\\'


class RecordedAPI:
    def __init__(self):
        self.sid=SID;self.opened=[];self.closed=[];self.fail_close=False;self.change={};self.fail_index=None
    def current_sid(self):return self.sid
    def volume(self,drive):
        if drive!='C:':raise AssertionError('unexpected drive')
        return VOLUME
    def open_directory(self,path):
        self.opened.append(path)
        return len(self.opened)
    def metadata(self,handle,*,private):
        if self.fail_index==handle:raise AppError('fixture_metadata_failure','fixture')
        result={'volume_serial':77,'file_id':format(handle,'032x'),'final_path':self.opened[handle-1],
                'filesystem':'NTFS','reparse':False}
        if private:result.update(owner_sid=SID,dacl_protected=True,
            aces=[{'type':'allow','sid':SID,'mask':0x1f01ff,'flags':3}])
        result.update(copy.deepcopy(self.change.get(handle,{})))
        return result
    def close(self,handle):
        self.closed.append(handle)
        if self.fail_close:raise AppError('fixture_cleanup_failure','fixture')


class WindowsDirectoryContractTests(unittest.TestCase):
    def test_exact_namespace_order_and_reverse_cleanup_are_independently_asserted(self):
        api=RecordedAPI()
        with wd._pin('C:\\Pilot\\Private',api) as pinned:
            value=pinned.receipt()
            self.assertEqual(api.opened,[VOLUME,VOLUME+'Pilot',VOLUME+'Pilot\\Private'])
            self.assertEqual(api.closed,[])
            self.assertEqual(value['directory_file_id'],'00000000000000000000000000000003')
            self.assertEqual(value['owner_sid'],SID)
            self.assertFalse(value['platform_qualified'])
            self.assertFalse(value['production_approved'])
        self.assertEqual(api.closed,[3,2,1])
        with self.assertRaises(AppError) as caught:pinned.revalidate()
        self.assertEqual(caught.exception.code,'windows_directory_handle_closed')

    def test_known_bad_path_aliases_never_reach_native_adapter(self):
        for path in ('relative','C:relative','C:\\','C:\\a\\..\\b','C:\\a\\.\\b',
                     'C:\\a\\\\b','C:\\a\\','C:\\a.','C:\\a ','C:\\a:stream',
                     'C:\\NUL.txt','C:\\COM1','C:\\LPT9.log','C:\\COM¹','C:\\CONOUT$','C:\\bad\ud800','C:/Pilot/Private',
                     '\\\\server\\share\\folder','\\\\?\\C:\\Pilot','C:\\x\x1b]52;bad'):
            with self.subTest(path=repr(path)):
                api=RecordedAPI()
                with self.assertRaises(AppError):
                    with wd._pin(path,api):pass
                self.assertEqual(api.opened,[])
        self.assertEqual(wd._components("C:\\- space 雪\\quote'folder"),('C:',('- space 雪',"quote'folder")))

    def test_foreign_owner_null_inherited_broad_or_unknown_aces_fail(self):
        valid={'owner_sid':SID,'dacl_protected':True,'aces':[{'type':'allow','sid':SID,'mask':1,'flags':0}]}
        variants=[{'owner_sid':'S-1-5-18'},{'dacl_protected':False},{'aces':[]},{'aces':None},
                  {'aces':[{'type':'allow','sid':'S-1-1-0','mask':1,'flags':0}]},
                  {'aces':[{'type':'deny','sid':SID,'mask':1,'flags':0}]},
                  {'aces':[{'type':'allow','sid':SID,'mask':1,'flags':16}]},
                  {'aces':[{'type':'allow','sid':SID,'mask':0,'flags':0}]}]
        wd._admit_private(valid,SID)
        for variant in variants:
            with self.subTest(variant=variant),self.assertRaises(AppError):wd._admit_private(valid|variant,SID)

    def test_reparse_wrong_volume_or_non_ntfs_never_yields_and_closes_all_opened_handles(self):
        for change in ({'reparse':True},{'volume_serial':78},{'filesystem':'ReFS'},
                       {'final_path':'\\\\?\\Volume{00000000-0000-0000-0000-000000000000}\\outside'}):
            api=RecordedAPI();api.change[2]=change
            with self.subTest(change=change),self.assertRaises(AppError):
                with wd._pin('C:\\Pilot\\Private',api):self.fail('unsupported identity admitted')
            self.assertEqual(api.closed,[2,1])

    def test_partial_open_failure_retains_primary_and_closes_previous_handles(self):
        api=RecordedAPI();api.fail_index=2;api.fail_close=True
        with self.assertRaises(AppError) as caught:
            with wd._pin('C:\\Pilot\\Private',api):pass
        self.assertEqual(caught.exception.code,'fixture_metadata_failure')
        self.assertEqual(api.closed,[2,1])
        self.assertIn('cleanup failed',caught.exception.__notes__[0])

    def test_identity_and_acl_changes_after_entry_are_rejected(self):
        for change in ('sid','acl','file_id'):
            api=RecordedAPI()
            with self.subTest(change=change),self.assertRaises(AppError):
                with wd._pin('C:\\Pilot\\Private',api):
                    if change=='sid':api.sid='S-1-5-18'
                    elif change=='acl':api.change[3]={'dacl_protected':False}
                    else:api.change[3]={'file_id':'f'*32}
            self.assertEqual(api.closed,[3,2,1])

    def test_cleanup_failure_after_success_is_not_a_successful_exit(self):
        api=RecordedAPI()
        with self.assertRaises(AppError) as caught:
            with wd._pin('C:\\Pilot\\Private',api):api.fail_close=True
        self.assertEqual(caught.exception.code,'windows_directory_close_failed')
        self.assertEqual(api.closed,[3,2,1])

    def test_non_windows_public_entrypoint_rejects_before_file_or_process_access(self):
        with patch.object(wd.sys,'platform','linux'),patch.object(os,'open',side_effect=AssertionError('file opened')),\
             patch.object(subprocess,'Popen',side_effect=AssertionError('process started')):
            with self.assertRaises(AppError) as caught:
                with wd.pin_private_directory('C:\\Pilot\\Private'):pass
        self.assertEqual(caught.exception.code,'windows_directory_platform_unsupported')

    def test_win32_structures_have_fixed_width_abi_layouts_without_native_claim(self):
        self.assertEqual(ctypes.sizeof(wd._FileInformation),52)
        self.assertEqual(ctypes.sizeof(wd._FileIdInformation),24)
        self.assertEqual(ctypes.sizeof(wd._AceHeader),4)
        self.assertTrue(wd._VOLUME.fullmatch(VOLUME))
        self.assertFalse(wd._VOLUME.fullmatch('\\\\server\\share\\'))


class NativeDirectoryProcedureTests(unittest.TestCase):
    def module(self):
        path=Path(__file__).resolve().parents[1]/'scripts/qualify-windows-directory.py'
        spec=importlib.util.spec_from_file_location('native_directory_qualifier',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_independent_oracle_requires_real_negative_fixture_properties(self):
        module=self.module()
        private={'case':'private','directory':True,'reparse':False,'owner_sid':SID,'protected':True,
                 'aces':[{'sid':SID,'type':'Allow','rights':0x1f01ff}]}
        broad=copy.deepcopy(private);broad['case']='broad_acl';broad['aces'].append({'sid':'S-1-1-0','type':'Allow','rights':1})
        foreign=copy.deepcopy(private);foreign.update(case='foreign_owner',owner_sid='S-1-5-18')
        value={'schema':'independent-dotnet-directory-oracle/1','powershell_major':7,'current_sid':SID,
               'fixtures':[private,broad,{'case':'reparse','directory':True,'reparse':True},
                           {'case':'reparse_ancestor','directory':True,'reparse':False,'reparse_ancestors':['fixture-junction']},foreign]}
        self.assertTrue(module.expected_fixtures(value))
        for index,field,bad in ((0,'protected',False),(1,'aces',private['aces']),(2,'reparse',False),
                                (3,'reparse_ancestors',[]),(4,'owner_sid',SID)):
            altered=copy.deepcopy(value);altered['fixtures'][index][field]=bad
            with self.subTest(index=index):self.assertFalse(module.expected_fixtures(altered))
        self.assertFalse(module.expected_fixtures({'powershell_major':'7'}))

    def test_actual_qualifier_on_linux_records_blocker_and_runs_no_native_command(self):
        if sys.platform=='win32':self.skipTest('The actual Windows procedure is a separate native gate.')
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'new-receipt'
            result=subprocess.run([sys.executable,'-B',str(root/'scripts/qualify-windows-directory.py'),
                '--fixtures','NO-NATIVE-FIXTURE-IS-READ','--output',str(output)],capture_output=True,timeout=10)
            self.assertEqual(result.returncode,3,result.stderr)
            value=json.loads((output/'RESULT.json').read_text())
            self.assertEqual(value['status'],'BLOCKED')
            self.assertEqual(value['commands'],[])
            self.assertEqual(value['checks'],[])
            self.assertFalse(value['platform_qualified'])


if __name__=='__main__':unittest.main()
