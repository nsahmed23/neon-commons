"""Bounded literal no-op proof and immutable post-host output capture.

This module proves byte/content relationships only. Callers must independently
establish receiving-state authentication and bind the captured output record to
their durable host outcome before exposing the result. It grants no authority.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import stat
from intune_iac import protected,provider_execution as pe
from intune_iac.io import AppError,canonical,digest,parse_json
from intune_iac.provider_journey import _private
from intune_iac.worker_adoption_provider import PLAN_PATH,PLAN_JSON_PATH,PLAN_EXIT_PATH

VERSION='native-plan-output-capture/1'
LIMIT=32*1024*1024
FILES={'plan.bin':PLAN_PATH,'plan.json':PLAN_JSON_PATH,'exit.txt':PLAN_EXIT_PATH}


def _fail(code):raise AppError(code,'The exact native no-change plan output and independently supplied state/source relationship were not established.') from None

def _read(path,limit=LIMIT):
    path=_private(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    primary=None
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_uid!=os.geteuid() or before.st_mode&0o077 or not 0<before.st_size<=limit:_fail('plan_output_file_invalid')
        chunks=[];total=0
        while total<=limit:
            chunk=os.read(fd,min(1024*1024,limit+1-total))
            if not chunk:break
            chunks.append(chunk);total+=len(chunk)
        raw=b''.join(chunks)
        after=os.fstat(fd);named=os.lstat(path)
        fields=lambda value:(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns,value.st_uid,value.st_mode,value.st_nlink)
        if len(raw)!=before.st_size or fields(before)!=fields(after) or fields(after)!=fields(named):_fail('plan_output_file_changed')
        return raw
    except BaseException as error:primary=error;raise
    finally:
        try:os.close(fd)
        except BaseException as secondary:
            if primary is None:raise
            primary.add_note('Secondary plan-output descriptor cleanup: '+type(secondary).__name__)
            if isinstance(secondary,(KeyboardInterrupt,SystemExit)):raise secondary from primary


def paths(job_root):
    root=_private(job_root,directory=True)
    return {name:root/value.removeprefix('/job/') for name,value in FILES.items()}


def capture(job_root,archive,*,host_result):
    if type(host_result) is not dict or host_result.get('status')!='complete':_fail('plan_output_host_not_complete')
    host_sha=digest(host_result)
    source=paths(job_root);root=Path(archive).absolute();_private(root.parent,directory=True)
    # Read each artifact once through pinned regular-file descriptors. The raw
    # serialization is preserved, not regenerated from a parsed representation.
    raw={name:_read(path,64 if name=='exit.txt' else LIMIT) for name,path in source.items()}
    root.mkdir(mode=0o700,exist_ok=False);protected._sync(root.parent)
    for name,data in raw.items():protected._exclusive(root/name,data)
    facts={'schema_version':VERSION,'host_result_sha256':host_sha,'source_root':str(Path(job_root).absolute()),'archive_root':str(root),
        'artifacts':{name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'source_path':str(source[name])} for name,data in raw.items()},
        'receiving_state_authentication_established':False,'execution_authorized':False}
    protected._exclusive(root/'receipt.json',canonical(facts));return facts


def read(record,*,job_root,archive):
    if type(record) is not dict:_fail('plan_output_capture_required')
    raw_record=canonical(record);root=_private(archive,directory=True);source=paths(job_root)
    if (set(record)!={'schema_version','host_result_sha256','source_root','archive_root','artifacts','receiving_state_authentication_established','execution_authorized'}
            or type(record['host_result_sha256']) is not str or len(record['host_result_sha256'])!=64 or any(c not in '0123456789abcdef' for c in record['host_result_sha256'])
            or record['schema_version']!=VERSION or record['source_root']!=str(Path(job_root).absolute()) or record['archive_root']!=str(root)
            or record['receiving_state_authentication_established'] is not False or record['execution_authorized'] is not False
            or type(record['artifacts']) is not dict or set(record['artifacts'])!=set(FILES)
            or _read(root/'receipt.json',64*1024)!=raw_record):_fail('plan_output_capture_changed')
    data={}
    for name,path in source.items():
        pin=record['artifacts'][name]
        if (type(pin) is not dict or set(pin)!={'bytes','sha256','source_path'} or pin['source_path']!=str(path)
                or type(pin['bytes']) is not int or pin['bytes']<=0 or type(pin['sha256']) is not str or len(pin['sha256'])!=64
                or any(c not in '0123456789abcdef' for c in pin['sha256'])):_fail('plan_output_capture_changed')
        archived=_read(root/name,64 if name=='exit.txt' else LIMIT);current=_read(path,64 if name=='exit.txt' else LIMIT)
        if archived!=current or len(archived)!=pin['bytes'] or hashlib.sha256(archived).hexdigest()!=pin['sha256']:_fail('plan_output_artifact_changed')
        data[name]=archived
    return data


from .worker_plan_content import _same, _closed_mask, _resource, _module, validate


def qualify(record,*,job_root,archive,state_raw,source_raw,object_id,state_sha256,source_sha256,effective_inputs_sha256):
    data=read(record,job_root=job_root,archive=archive)
    if data['exit.txt']!=b'0\n':_fail('plan_output_exit_not_zero')
    proof=validate(data['plan.json'],state_raw=state_raw,source_raw=source_raw,object_id=object_id,state_sha256=state_sha256,source_sha256=source_sha256,effective_inputs_sha256=effective_inputs_sha256)
    return {'capture_sha256':digest(record),'artifacts':record['artifacts'],'content_proof':proof,'first_plan_no_change':True,'exit_code':0}
