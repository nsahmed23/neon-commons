"""Fixed Azure state observation and explicit unresolved execution contracts.

Observation reports never authorize effects. The storage token is a separate
opaque credential; neither an accepted GET nor self-asserted JSON authenticates
its principal, credential origin, approval channel, or writer ownership.
"""
from __future__ import annotations

import hashlib
from email.utils import formatdate
import http.client
import re
import socket
import ssl
import threading
from urllib.parse import quote, urlsplit

from .io import AppError, digest, parse_json
from .target import _snapshot, compare_targets, inspect_target

MAX_STATE_BYTES=16*1024*1024
ETAG=re.compile(r'^"[!#-~]{1,128}"$')
BLOCKERS=('backend_principal_not_authenticated','writer_ownership_not_authenticated',
          'protected_approval_unavailable','cloud_mutation_adapter_unavailable')


def qualification_contract():
    """Implementable host requirements; claims about satisfying them are untrusted."""
    return {'schema_version':'native-qualification-contract/1.0','execution_authorized':False,
            'required_protected_evidence':{
                'credential_provider':{'binding':['cloud','tenant_id','principal_object_id','client_id','auth_kind','federation','audience','credential_handle','expires_at'],
                                       'separate_scopes':['intune_graph','backend_management','backend_storage'],
                                       'authority':'host-configured credential provider; no request-supplied keys or decoded access-token claims'},
                'runtime':{'binding':['repository_revision','dirty_digest','effective_configuration','atmos_stack','component','workspace','provider_lock','executables','environment_allowlist'],
                           'authority':'same protected process that creates and executes the saved plan'},
                'backend':{'binding':['storage_resource_id','blob_endpoint','container','resolved_blob','etag','state_lineage','state_serial','state_sha256'],
                           'authority':'fresh fixed-origin authenticated service observation plus native backend locking'},
                'ownership':{'binding':['operation_id','scope_sha256','writer_id','lease_id','lease_expiry','fencing_token'],
                             'authority':'deployment-native exclusive writer service; HEAD lease status alone is insufficient'},
                'approval':{'binding':['operation_id','action','binary_plan_sha256','plan_json_sha256','configuration_sha256','target_sha256','toolchain_sha256','issued_at','expires_at','nonce'],
                            'authority':'enterprise-owned approver channel with independent trust root and durable one-time consumption'}},
            'unsupported_authority':['self_signed_json','caller_asserted_booleans','decoded_graph_access_token','local_fixture_approval','serialized_observation_report']}


def inspect_native_context(document, *, attestations=None):
    """Report consistency and hard gates; never authenticate supplied attestations."""
    inspection=inspect_target(document)
    result={'schema_version':'native-context/1.0','status':'blocked','execution_authorized':False,
            'target':inspection,'blockers':['protected_credential_provider_required','protected_approval_channel_required',
                                          'distributed_writer_and_fencing_required','live_provider_readback_required',
                                          'cloud_mutation_adapter_unavailable']}
    if attestations is not None:result['blockers'].append('serialized_attestations_are_not_authority')
    if not inspection['valid']:result['blockers'].append('invalid_target')
    return result


def _unavailable(): raise AppError('backend_observation_unavailable','Backend observation was not established.')


def _token(value):
    return type(value)is str and 1<=len(value)<=16384 and all(33<=ord(c)<=126 for c in value)


def _blob_read(host, path, token, method, timeout, *, etag=None):
    """Only target-derived fixed public Azure host/path, HEAD or GET, no redirects."""
    if method not in ('HEAD','GET'):_unavailable()
    connection=None;timer=None
    try:
        connection=http.client.HTTPSConnection(host,timeout=timeout,context=ssl.create_default_context())
        connection.connect();connected=connection.sock
        def stop():
            try:connected.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        timer=threading.Timer(timeout,stop);timer.daemon=True;timer.start()
        headers={'Authorization':'Bearer '+token,'x-ms-version':'2023-11-03','x-ms-date':formatdate(usegmt=True),'Accept-Encoding':'identity'}
        if etag is not None:
            if type(etag)is not str or not ETAG.fullmatch(etag):_unavailable()
            headers['If-Match']=etag
        connection.request(method,path,headers=headers)
        response=connection.getresponse()
        if response.status!=200:_unavailable()
        collected={}
        relevant={'etag','content-length','content-encoding','x-ms-blob-type','x-ms-lease-status','x-ms-lease-state','x-ms-lease-duration'}
        for key,value in response.getheaders():
            name=key.lower()
            if name in relevant:
                if name in collected:_unavailable()
                collected[name]=value
        _properties(collected)
        if collected.get('content-encoding','identity').lower() not in ('','identity'):_unavailable()
        body=response.read(MAX_STATE_BYTES+1) if method=='GET' else b''
        if len(body)>MAX_STATE_BYTES:_unavailable()
        return collected,body
    finally:
        if timer is not None:timer.cancel()
        if connection is not None:connection.close()


def _properties(headers):
    etag=headers.get('etag');length=headers.get('content-length')
    if type(etag)is not str or not ETAG.fullmatch(etag) or type(length)is not str or not re.fullmatch('[0-9]{1,9}',length) or not 1<=int(length)<=MAX_STATE_BYTES:_unavailable()
    if headers.get('x-ms-blob-type')!='BlockBlob':_unavailable()
    if headers.get('x-ms-lease-status') not in ('locked','unlocked') or headers.get('x-ms-lease-state') not in ('available','leased','expired','breaking','broken'):_unavailable()
    if headers.get('x-ms-lease-duration') not in (None,'fixed','infinite'):_unavailable()
    return {'etag':etag,'length':int(length),'lease_status':headers['x-ms-lease-status'],
            'lease_state':headers['x-ms-lease-state'],'lease_duration':headers.get('x-ms-lease-duration')}


def collect_backend_observation(document, *, storage_token, timeout=10):
    """HEAD -> If-Match GET -> If-Match HEAD of one exact existing state blob.

    No lease acquisition, state creation, account-key retrieval, or mutation.
    DNS lookup still relies on OS resolver bounds; deployment must supervise the
    read-only collector externally if a total wall-clock deadline is required.
    """
    result={'schema_version':'azure-backend-observation/1.0','status':'invalid','execution_authorized':False,
            'assurance':'service_accepted_opaque_storage_credential_only','observations':[],'blockers':list(BLOCKERS)}
    snapshot=_snapshot(document)
    if compare_targets(snapshot,snapshot)['status']!='match' or not _token(storage_token) or type(timeout)is not int or not 1<=timeout<=30:
        result['issues']=['invalid_collection_request'];return result
    backend=snapshot['binding']['backend'];host=urlsplit(backend['blob_endpoint']).hostname
    path='/'+quote(backend['container'],safe='')+'/'+quote(backend['resolved_blob_name'],safe='/')
    try:
        head,_=_blob_read(host,path,storage_token,'HEAD',timeout);properties=_properties(head)
        result['observations'].append({'kind':'blob_properties','method':'HEAD','facts_sha256':digest(properties)})
        get,body=_blob_read(host,path,storage_token,'GET',timeout,etag=properties['etag'])
        if _properties(get)!=properties or len(body)!=properties['length']:_unavailable()
        state=parse_json(body)
        if type(state)is not dict or state.get('version')!=4 or state.get('lineage')!=backend['state_lineage'] or type(state.get('serial'))is not int or state['serial']!=backend['state_serial'] or hashlib.sha256(body).hexdigest()!=backend['state_sha256']:_unavailable()
        result['observations'].append({'kind':'state_bytes','method':'GET','facts_sha256':digest({'lineage':state['lineage'],'serial':state['serial'],'state_sha256':hashlib.sha256(body).hexdigest()})})
        final,_=_blob_read(host,path,storage_token,'HEAD',timeout,etag=properties['etag'])
        if _properties(final)!=properties:_unavailable()
        result['observations'].append({'kind':'unchanged_blob_properties','method':'HEAD','facts_sha256':digest(properties)})
        result.update(status='observed',issues=[],binding_sha256=digest(snapshot['binding']),
                      backend_state={'etag_sha256':digest(properties['etag']),'state_lineage_sha256':digest(state['lineage']),
                                     'state_serial':state['serial'],'state_sha256':hashlib.sha256(body).hexdigest(),
                                     'lease_status':properties['lease_status'],'lease_state':properties['lease_state']})
    except (AppError,OSError,ValueError,TypeError,http.client.HTTPException):
        result.update(status='unavailable',issues=['backend_observation_unavailable'])
    return result
