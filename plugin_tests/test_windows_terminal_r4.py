"""Modeled native ABI/input/session faults; no Windows qualification claim."""
import ctypes
import importlib.util
import os
from pathlib import Path
import sys
import unittest

from intune_iac.io import AppError
from intune_iac import windows_terminal as module


class RecordingAPI:
    def __init__(self):
        self.modes={11:0x1F7, 12:0x03};self.calls=[];self.events=[];self.fail_set=None;self.fail_write=False
    def handles(self):return 11,12
    def mode(self,handle):return self.modes[handle]
    def set_mode(self,handle,value):
        self.calls.append(('mode',handle,value))
        if self.fail_set==(handle,value):raise AppError('injected_set_failure','mode failure')
        self.modes[handle]=value
    def write(self,handle,text):
        self.calls.append(('write',handle,text))
        if self.fail_write:raise AppError('injected_output_failure','write failure')
        return len(text)
    def size(self,handle):return 80,24
    def wait(self,handle,timeout):self.calls.append(('wait',handle,timeout));return bool(self.events)
    def read(self,handle):return self.events.pop(0)


def event(key,unicode=0,*,control=0,repeat=1,down=True):
    return {'kind':'key','down':down,'repeat':repeat,'virtual_key':key,'unicode':unicode,'control':control}


class NativeConsoleStagedTests(unittest.TestCase):
    def make(self):
        api=RecordingAPI();console=module.NativeConsole.__new__(module.NativeConsole);console._initialize(api);return console,api
    def test_actual_nonwindows_constructor_rejects(self):
        if os.name=='nt':self.skipTest('Run native harness on Windows; this negative targets Linux.')
        with self.assertRaises(AppError) as caught:module.NativeConsole()
        self.assertEqual(caught.exception.code,'native_console_host_unsupported')
    def test_explicit_win32_abi_layouts(self):
        self.assertEqual(ctypes.sizeof(module.KEY_EVENT),16)
        self.assertEqual(ctypes.sizeof(module.INPUT_RECORD),20)
        self.assertEqual(module.INPUT_RECORD.event.offset,4)
        self.assertEqual(ctypes.sizeof(module.SCREEN_BUFFER_INFO),22)
    def test_mode_change_before_entry_rejects_without_resetting_user_mode(self):
        console,api=self.make();api.modes[11]=0x123
        with self.assertRaises(AppError) as caught:
            with console.session():self.fail('stale mode admitted')
        self.assertEqual(caught.exception.code,'native_console_mode_changed_before_session')
        self.assertEqual(api.modes[11],0x123);self.assertFalse(api.calls)
    def test_modes_restored_on_normal_return(self):
        console,api=self.make();original=dict(api.modes)
        with console.session():
            self.assertTrue(console.active);self.assertNotEqual(api.modes,original)
            self.assertEqual(console.size(),(80,24))
        self.assertEqual(api.modes,original);self.assertFalse(console.active)
        self.assertEqual(len([r for r in api.calls if r[0]=='write']),2)
    def test_primary_interrupt_preserved_with_cleanup_failure(self):
        console,api=self.make();primary=KeyboardInterrupt('deliberate')
        try:
            with console.session():
                api.fail_set=(11,console.original_input)
                raise primary
        except KeyboardInterrupt as error:
            self.assertIs(error,primary);self.assertEqual(error.native_console_cleanup_failures,['AppError:input_mode'])
        else:self.fail('primary missing')
        self.assertEqual(api.modes[12],console.original_output)
    def test_setup_failure_restores_first_mode(self):
        console,api=self.make();original=dict(api.modes)
        api.fail_set=(12,console.original_output|5)
        with self.assertRaises(AppError) as caught:
            with console.session():self.fail('session yielded after failed setup')
        self.assertEqual(caught.exception.code,'injected_set_failure');self.assertEqual(api.modes,original)
    def test_cleanup_failure_reported_without_primary(self):
        console,api=self.make()
        with self.assertRaises(AppError) as caught:
            with console.session():api.fail_write=True
        self.assertEqual(caught.exception.code,'native_console_cleanup_failed')
        self.assertEqual(api.modes,{11:console.original_input,12:console.original_output})
    def test_ordinary_enter_cannot_mint_submission(self):
        console,api=self.make()
        api.events=[event(13,13,repeat=64),event(13,13,control=module.CTRL,repeat=64)]
        self.assertEqual(console.key_reader.read(),'enter');self.assertEqual(console.key_reader.read(),'submit')
        self.assertIsNone(console.key_reader.read());self.assertEqual(console.submission_key,'submit')
    def test_utf16_pairs_and_unmatched_surrogates(self):
        console,api=self.make();api.events=[event(0,0xD83D),event(0,0xDE00),event(0,0xDE00),event(0,ord('A'))]
        self.assertEqual([console.key_reader.read() for _ in range(4)],['ignored',('text','😀'),'ignored',('text','A')])
    def test_repeat_and_control_bounds(self):
        console,api=self.make();api.events=[event(0x26,repeat=2),event(0,65,repeat=65),event(0x43,3,control=module.CTRL),event(0,27)]
        self.assertEqual([console.key_reader.read() for _ in range(5)],['up','up','ignored','interrupt','ignored'])
    def test_resize_keyup_and_bounded_wait(self):
        console,api=self.make();api.events=[{'kind':'resize'},event(65,65,down=False)]
        self.assertEqual(console.key_reader.read(),'redraw');self.assertEqual(console.key_reader.read(),'ignored');self.assertIsNone(console.key_reader.read())
        self.assertTrue(all(row[2]==150 for row in api.calls if row[0]=='wait'))


if __name__=='__main__':unittest.main(verbosity=2)
