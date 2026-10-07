"""Modeled file records only; actual reference navigation validator is reused."""
from contextlib import contextmanager
import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

from intune_iac.io import AppError, canonical
from intune_iac import windows_workspace_context as module
TENANT='11111111-1111-1111-1111-111111111111'

class Files:
    def __init__(self):self.data={};self.locked=False;self.fail_after=False
    @contextmanager
    def lock(self):
        if self.locked:raise AppError('modeled_lock_busy','Busy')
        self.locked=True
        try:yield
        finally:self.locked=False
    def names(self):assert self.locked;return list(self.data)
    def read(self,name):assert self.locked;return self.data[name]
    def publish(self,name,data):
        assert self.locked
        if name in self.data:raise FileExistsError(name)
        self.data[name]=data
        if self.fail_after:raise AppError('modeled_namespace_uncertain','Unknown durability')

class ContextStagedTests(unittest.TestCase):
    def setUp(self):
        self.files=Files();self.store=SimpleNamespace(tenant_id=TENANT)
        self.context=module._ContextCore(self.store,self.files)
        self.value={'schema_version':'intune-workspace-context/1','tenant_id':TENANT,'selected':None,'view_command':'overview','page_command':'overview','tab':0}
    def test_public_constructor_rejects_json_and_generic_store(self):
        for store in ({'tenant_id':TENANT},self.store):
            with self.assertRaises(AppError):module.WindowsWorkspaceContext(store)
    def test_roundtrip_and_identical_save_is_noop(self):
        self.assertIsNone(self.context.load());first=self.context.save(self.value);self.assertEqual(first['generation'],1)
        self.assertEqual(self.context.load(),self.value);self.assertFalse(self.context.save(self.value)['changed']);self.assertEqual(len(self.files.data),1)
    def test_existing_validator_rejects_mutating_navigation_and_wrong_tenant(self):
        for changes in ({'view_command':'approve anything'},{'tenant_id':'22222222-2222-2222-2222-222222222222'},{'pending':'execute'}):
            with self.assertRaises(AppError):self.context.save({**self.value,**changes})
        self.assertFalse(self.files.data)
    def test_chained_generations_reopen(self):
        self.context.save(self.value);value={**self.value,'view_command':'health','tab':6}
        self.context.save(value);fresh=module._ContextCore(self.store,self.files)
        self.assertEqual(fresh.load(),value);self.assertEqual(len(self.files.data),2)
    def test_tampered_raw_record_rejected_and_preserved(self):
        self.context.save(self.value);name=next(iter(self.files.data));self.files.data[name]+=b' '
        with self.assertRaises(AppError):self.context.load()
        self.assertEqual(len(self.files.data),1)
    def test_gap_and_fork_rejected(self):
        self.context.save(self.value);raw=next(iter(self.files.data.values()));name=next(iter(self.files.data))
        self.files.data[name.replace('0000000001','0000000003')]=self.files.data.pop(name)
        with self.assertRaises(AppError):self.context.load()
        self.files.data={name:raw,name.replace(name[-69:-5],'a'*64):raw}
        with self.assertRaises(AppError):self.context.load()
    def test_unknown_generation_and_oversized_record_rejected(self):
        self.files.data['workspace-context-latest.json']=b'{}'
        with self.assertRaises(AppError):self.context.load()
        self.files.data={};self.context.save(self.value);name=next(iter(self.files.data))
        self.files.data[name]=b'x'*(module.MAX_BYTES+1)
        with self.assertRaises(AppError):self.context.load()
    def test_uncertain_publication_retained_and_reopened(self):
        self.files.fail_after=True
        with self.assertRaises(AppError):self.context.save(self.value)
        self.assertEqual(len(self.files.data),1);self.files.fail_after=False
        self.assertEqual(self.context.load(),self.value);self.assertFalse(self.context.save(self.value)['changed'])
    def test_capacity_fails_without_deleting_any_generation(self):
        for index in range(module.MAX_GENERATIONS):self.context.save({**self.value,'page_command':'overview 10 '+str(index)})
        with self.assertRaises(AppError):self.context.save({**self.value,'page_command':'overview 10 256'})
        self.assertEqual(len(self.files.data),module.MAX_GENERATIONS)
    def test_concurrent_cooperative_lock_failure_precedes_publication(self):
        self.files.locked=True
        with self.assertRaises(AppError):self.context.save(self.value)
        self.assertFalse(self.files.data)

if __name__=='__main__':unittest.main(verbosity=2)
