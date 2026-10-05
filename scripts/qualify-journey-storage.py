#!/usr/bin/env python3
"""Trace task-owned CLI receipt writes and lock identity during real PTY runs.

Diagnostic instrumentation wraps persistence/ownership observation only. It does
not alter accepted commands, state transitions, or authority. No timing result
from this profile is a product performance claim. Each child records intended
bytes and immediately observed file metadata/hash under its absolute path.
"""
from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('journey_navigation_diagnostic', ROOT / 'scripts/qualify-journey-navigation.py')
nav = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(nav)
ORIGINAL = nav.Terminal.__init__

TRACE = r'''
import hashlib,json,os,runpy,sys,time
from pathlib import Path
root,log,script,*args=sys.argv[1:]
sys.path.insert(0,root)
from intune_iac import journey,workflow
from intune_iac.io import canonical
stream=open(log,'a',buffering=1)
def info(path):
 p=Path(path).absolute()
 try:
  s=p.lstat()
  return {'path':str(p),'resolved':str(p.resolve()),'dev':s.st_dev,'ino':s.st_ino,'nlink':s.st_nlink,'size':s.st_size,'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns,'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() and s.st_size<16777216 else None}
 except FileNotFoundError:return {'path':str(p),'absent':True}
def emit(event,**kw):
 stream.write(json.dumps({'event':event,'pid':os.getpid(),'ppid':os.getppid(),'time_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),**kw},sort_keys=True)+'\n');stream.flush()
emit('start',argv=[script,*args],cwd=os.getcwd())
original_write=journey.write_json
def write(path,value):
 emit('write_intended',file=info(path),intended_sha256=hashlib.sha256(canonical(value)+b'\n').hexdigest())
 try:return original_write(path,value)
 finally:emit('write_observed',file=info(path))
journey.write_json=write
original_lock=workflow._owns_lock
def owns(path,identity,token):
 result=original_lock(path,identity,token)
 emit('lock_observed',file=info(path),expected_dev_ino=identity,expected_token_sha256=hashlib.sha256(token).hexdigest(),owned=result)
 return result
workflow._owns_lock=owns
original_checkpoint=journey._checkpoint
def checkpoint(session,state,observed,stage,guard):
 path=journey._receipt_path(session,stage)
 emit('checkpoint_before',stage=stage,file=info(path))
 try:return original_checkpoint(session,state,observed,stage,guard)
 finally:emit('checkpoint_after',stage=stage,file=info(path))
journey._checkpoint=checkpoint
original_invalidate=journey._invalidate
def invalidate(session,start):
 emit('invalidate_before',stage=start,files=[info(journey._receipt_path(session,s)) for s in journey.STAGES])
 try:return original_invalidate(session,start)
 finally:emit('invalidate_after',stage=start,files=[info(journey._receipt_path(session,s)) for s in journey.STAGES])
journey._invalidate=invalidate
sys.argv=[script,*args]
try:runpy.run_path(script,run_name='__main__')
finally:emit('finish');stream.close()
'''

def traced(self, argv, cwd, destination):
    # Preserve actual interpreter/CLI arguments, excluding interpreter -B only
    # because it remains explicitly supplied to the wrapper process itself.
    script_index = 2 if argv[1] == '-B' else 1
    actual = [argv[0], '-B', '-c', TRACE, str(ROOT), str(destination.with_suffix('.io.jsonl')), *argv[script_index:]]
    return ORIGINAL(self, actual, cwd, destination)

nav.Terminal.__init__ = traced
if __name__ == '__main__': raise SystemExit(nav.main())
