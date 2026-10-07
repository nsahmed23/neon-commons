"""Reference UI/engine tests with modeled native events; no Win32 claim."""
from collections import deque
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import workbench_tui as tui,workbench,windows_workspace_binding as binding
from intune_iac.io import AppError
from intune_iac.workbench_store import WorkbenchStore

TENANT='11111111-1111-1111-1111-111111111111'

class Reader:
    def __init__(self,events):self.events=deque(events)
    def read(self):
        if not self.events:raise AssertionError('Modeled input exhausted without expected submit')
        return self.events.popleft()

class NativeSeamTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'store';self.store=WorkbenchStore.create(self.root,TENANT)
    def workspace(self,events):
        value=tui.Workspace(self.root,stdin=io.StringIO(),stdout=io.StringIO())
        value.submission_key='submit';value.key_reader=Reader(events);return value
    def test_plain_enter_consumed_without_submission_then_explicit_submit(self):
        w=self.workspace([('text',c) for c in ':help']+['enter','submit'])
        self.assertEqual(w.input(''),'help');self.assertFalse(w.key_reader.events)
    def test_multiline_paste_events_can_be_discarded_without_dispatch(self):
        w=self.workspace([('text',c) for c in ':execute']+['enter']+[('text',c) for c in 'anything']+['enter','escape',('text','q')])
        self.assertEqual(w.input(''),'quit');self.assertFalse(w.key_reader.events)
    def test_default_posix_enter_remains_complete_text_input(self):
        w=self.workspace([('text',c) for c in ':help']+['enter']);w.submission_key='enter'
        self.assertEqual(w.input(''),'help')
    def test_forged_native_binding_rejected(self):
        with self.assertRaises(AppError):tui.Workspace(self.root,_native_binding={'native':True})
        with self.assertRaises(AppError):binding.admit_store(str(self.root),self.store)
    def test_all_mutating_and_service_routes_explicitly_denied(self):
        for command in ('collect','capture-import','approve','execute','service-attach','service-cancel','service-link','reference-import','recover'):
            with self.assertRaises(AppError) as caught:binding.require_command(command)
            self.assertEqual(caught.exception.code,'native_workspace_command_unimplemented')
        for command in ('help','overview','select','inspect','health','history','cancel','quit'):binding.require_command(command)
    def test_dictionary_uses_exact_native_store_package_reader(self):
        from intune_iac.windows_workbench import WindowsWorkbenchStore
        from intune_iac import workbench_provenance
        native=WindowsWorkbenchStore.__new__(WindowsWorkbenchStore)
        native.overview=lambda **kwargs:{'objects':[]}
        native.artifacts=lambda **kwargs:[]
        calls=[]
        native.dictionary=lambda query='',**kwargs:(calls.append((query,kwargs)) or {'route':'native package reader'})
        with patch.object(workbench_provenance,'_read',side_effect=AssertionError('POSIX package read reached')):
            result=workbench._dictionary(native,'fixture',limit=10,offset=0)
        self.assertEqual(result,{'route':'native package reader'});self.assertEqual(len(calls),1)
    def test_native_store_views_admitted_with_journal_denials_in_evidence_reader(self):
        for command in ('views','views-page'):binding.require_command(command)
        # Actual store/journal/raw and command-route controls are independently
        # asserted in test_windows_views_r4; no execution route is admitted here.
        for command in ('execute','service-link','service-attach','approve'):
            with self.assertRaises(AppError):binding.require_command(command)
    def test_same_engine_explicit_route_guard_precedes_action(self):
        lines=iter(['collect','service-cancel anything anything','overview','quit']);seen=[]
        # Modeled admission only: native namespace/ACL is not asserted. The
        # actual shared dispatcher and fixed command guard run unchanged.
        with patch.object(binding,'admit_store',return_value=self.store),patch.object(self.store,'collect',side_effect=AssertionError('must not dispatch')):
            result=workbench.run_terminal(str(self.root),input_fn=lambda prompt:next(lines),result_fn=seen.append,_store_capability=object())
        self.assertEqual(result['status'],'closed')
        errors=[row for row in seen if row.get('status')=='error']
        self.assertEqual(len(errors),2)
        self.assertTrue(all(row['error']['code']=='native_workspace_command_unimplemented' for row in errors))

if __name__=='__main__':unittest.main(verbosity=2)
