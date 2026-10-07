"""Read-only native lease recovery inspection, including expired operations.

This module contains no HTTP client, lease release or execution capability.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import time

from .io import AppError, canonical, digest, parse_json
from .provider_journey import _private
from .worker_broker import validate_policy


def _fail(code):
    raise AppError(code, 'Native recovery evidence could not be inspected without changing its preserved journal.') from None


def inspect_native_recovery(journal, *, policy):
    """Inspect an exact journal/policy pair without reviving expired authority."""
    if (type(policy) is not dict or type(policy.get('expires_at')) is not int or
            not 0 < policy['expires_at'] < 2**63): _fail('recovery_policy_invalid')
    # Structural validation is independent of present execution eligibility.
    structural = parse_json(canonical(policy)); structural['expires_at'] = int(time.time()) + 60
    validate_policy(structural)
    path = Path(journal).absolute(); _private(path)
    if path.stat().st_size > 16*1024*1024: _fail('recovery_journal_size')
    for suffix in ('-journal','-wal','-shm'):
        sidecar=Path(str(path)+suffix)
        if sidecar.exists() or sidecar.is_symlink(): _fail('recovery_journal_not_quiescent')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    db=sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=0)
    try:
        db.execute('PRAGMA query_only=ON')
        if db.execute('SELECT digest FROM binding').fetchall() != [(digest(policy),)]: _fail('recovery_policy_mismatch')
        rows=db.execute('SELECT n.sequence,n.host,n.path,n.action,n.lease_id,n.lock_metadata,a.status,a.response_code,a.route '
            'FROM native_lease_requests n JOIN attempts a ON a.sequence=n.sequence ORDER BY n.sequence').fetchall()
        writes=db.execute('SELECT sequence,route,status,response_code,request_sha256,response_sha256 FROM attempts ORDER BY sequence').fetchall()
    except sqlite3.Error: _fail('recovery_journal_invalid')
    finally: db.close()
    after=hashlib.sha256(path.read_bytes()).hexdigest()
    if after != before: _fail('recovery_journal_changed')
    routes={route['id']:route for route in policy['routes']};entries=[]
    for row in rows:
        sequence,host,blob_path,action,lease_id,metadata,status,response_code,identifier=row
        route=routes.get(identifier)
        if (route is None or route['effect'] not in ('lease','lock_metadata') or
                (host,blob_path)!=(route['host'],route['path']) or type(lease_id) is not str or
                not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',lease_id)):
            _fail('recovery_journal_route_mismatch')
        expected=route['headers'].get('x-ms-lease-action','metadata_set' if 'x-ms-meta-terraformlockid' in route.get('dynamic_headers',{}) else 'metadata_clear')
        if action != expected: _fail('recovery_journal_route_mismatch')
        if metadata is not None:
            try:
                raw=base64.b64decode(metadata,validate=True);document=parse_json(raw)
                if len(raw)>4096 or document['ID']!=lease_id or document['Path']!='https://'+host+blob_path:
                    _fail('recovery_journal_route_mismatch')
            except (ValueError,TypeError,KeyError,AppError): _fail('recovery_journal_route_mismatch')
        entries.append(dict(zip(('sequence','host','path','action','lease_id','lock_metadata','status','response_code','route'),row)))
    writes=[dict(zip(('sequence','route','status','response_code','request_sha256','response_sha256'),row))
            for row in writes if row[1] in routes and routes[row[1]]['effect'] in ('mutation','lease','lock_metadata','state_write')]
    return {'schema_version':'native-lease-recovery-inspection/1.0','journal_sha256':before,'policy_sha256':digest(policy),
        'operation_id':policy['operation_id'],'execution_binding_sha256':policy['execution_binding_sha256'],
        'expired':time.time()>=policy['expires_at'],'journal_unchanged':True,'entries':entries,'write_attempts':writes,
        'remote_state_observed':False,'remote_lease_observed':False,'automatic_release_authorized':False,
        'execution_authorized':False,'requires_independent_current_context_and_explicit_recovery':True}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['inspect']);parser.add_argument('--journal',required=True)
    parser.add_argument('--policy',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args(argv)
    try:
        source=Path(args.policy).absolute();_private(source)
        if source.stat().st_size>1024*1024: _fail('recovery_policy_invalid')
        result=inspect_native_recovery(args.journal,policy=parse_json(source.read_bytes()))
        output=Path(args.output).absolute();_private(output.parent,directory=True)
        descriptor=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            data=canonical(result);offset=0
            while offset<len(data):offset+=os.write(descriptor,data[offset:])
            os.fsync(descriptor)
        finally:os.close(descriptor)
        print(canonical({'status':'inspected','output':str(output),'sha256':hashlib.sha256(data).hexdigest(),
            'remote_actions':0,'execution_authorized':False}).decode())
        return 0
    except (AppError,OSError,sqlite3.Error) as error:
        print(canonical({'status':'blocked','error_code':getattr(error,'code',type(error).__name__),'remote_actions':0}).decode())
        return 1


if __name__=='__main__':raise SystemExit(main())
