"""Inert local reference provenance and attributed dictionary/comparison views.

Imported community exports never establish tenant identity, vendor definition
authority, desired-state approval or a new supported provider mapping.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit
from uuid import UUID

from .io import AppError, canonical, parse_json

MAX_REFERENCE_BYTES = 512 * 1024
MAX_SETTINGS = 1000
SCHEMA = 'workbench-source-reference/1.0'
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_REVISION = re.compile(r'[0-9a-f]{40}\Z')
_OIB_TOKEN = re.compile(r'OIBID:([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})(?![0-9A-Za-z-])')
_KNOWN_POLICY_FIELDS = frozenset({'id', 'name', 'description', 'platforms', 'technologies', 'settingCount',
    'settings', 'assignments', 'createdDateTime', 'lastModifiedDateTime', 'creationSource', 'priorityMetaData',
    'roleScopeTagIds', 'templateReference', '@odata.context', '@odata.type', '@odata.id', '@odata.editLink'})


def _fail(code='workbench_reference_invalid'):
    raise AppError(code, 'Reference data or provenance is invalid or outside the supported read-only profile.')


def _text(value, maximum=2048):
    return type(value) is str and 0 < len(value) <= maximum and not any(ord(c)<32 or 127<=ord(c)<160 for c in value)


def _uuid(value):
    try:
        parsed = UUID(value)
        if type(value) is not str or not parsed.int or str(parsed) != value.lower(): _fail()
        return str(parsed)
    except (ValueError, TypeError, AttributeError): _fail()


def _read(path):
    """Descriptor-relative no-follow walk; no symlink, hardlink or FIFO input."""
    if os.name != 'posix' or not hasattr(os, 'O_NOFOLLOW') or os.open not in os.supports_dir_fd:
        _fail('workbench_reference_platform_unsupported')
    candidate = Path(path)
    if '..' in candidate.parts: _fail('workbench_reference_path_unsafe')
    candidate = candidate.absolute()
    descriptors = []
    try:
        directory = os.open(candidate.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        for part in candidate.parts[1:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            descriptors.append(directory)
        fd = os.open(candidate.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        descriptors.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1: _fail('workbench_reference_path_unsafe')
        if before.st_size > MAX_REFERENCE_BYTES: _fail('workbench_reference_limit')
        blocks = bytearray()
        while len(blocks) <= MAX_REFERENCE_BYTES:
            block = os.read(fd, min(65536, MAX_REFERENCE_BYTES + 1 - len(blocks)))
            if not block: break
            blocks.extend(block)
        after = os.fstat(fd)
        if len(blocks) > MAX_REFERENCE_BYTES: _fail('workbench_reference_limit')
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) != (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            _fail('workbench_reference_changed')
        return bytes(blocks)
    except (OSError, TypeError, ValueError) as error:
        if isinstance(error, AppError): raise
        _fail('workbench_reference_path_unsafe')
    finally:
        for descriptor in reversed(descriptors): os.close(descriptor)


def _settings(body):
    """Keep every instance, including duplicate IDs and unfamiliar value shapes."""
    settings = body.get('settings') if isinstance(body,dict) else None
    if isinstance(settings,dict): settings = settings.get('settings')
    if not isinstance(settings,list): return [], ['settings_missing_or_unsupported']
    entries, blockers = [], []
    record_ids = set()
    for row in settings:
        if not isinstance(row,dict) or not isinstance(row.get('settingInstance'),dict) or 'settingDefinitionId' not in row['settingInstance']:
            blockers.append('setting_record_unrecognized')
        if isinstance(row,dict) and 'id' in row:
            if not _text(row['id'],512): blockers.append('setting_record_id_invalid')
            elif row['id'] in record_ids: blockers.append('setting_record_id_ambiguous')
            else: record_ids.add(row['id'])
    pending = [(settings, '/settings')]
    nodes = 0
    while pending:
        value, pointer = pending.pop(); nodes += 1
        if nodes > 20000: _fail('workbench_reference_limit')
        if isinstance(value,dict):
            if 'settingDefinitionId' in value:
                identifier = value['settingDefinitionId']
                if not _text(identifier,512): blockers.append('setting_identifier_invalid')
                else:
                    entries.append({'identifier':identifier, 'source_pointer':pointer,
                                    'type':value.get('@odata.type'), 'instance':copy.deepcopy(value)})
                    if len(entries)>MAX_SETTINGS: _fail('workbench_reference_limit')
            pending.extend((child,pointer+'/'+str(key).replace('~','~0').replace('/','~1')) for key,child in value.items())
        elif isinstance(value,list): pending.extend((child,pointer+'/'+str(index)) for index,child in enumerate(value))
    if settings and not entries: blockers.append('setting_instances_unrecognized')
    seen = set()
    for row in entries:
        if row['identifier'] in seen: blockers.append('setting_identifier_ambiguous')
        seen.add(row['identifier'])
    return sorted(entries,key=lambda row:(row['identifier'],row['source_pointer'])), sorted(set(blockers))


def _metadata(expected_sha256, source_revision, source_url, license_id, assertion_class):
    if not isinstance(expected_sha256,str) or not _HASH.fullmatch(expected_sha256): _fail()
    if not isinstance(source_revision,str) or not _REVISION.fullmatch(source_revision): _fail()
    if not _text(source_url) or any(c.isspace() for c in source_url): _fail()
    try:
        url = urlsplit(source_url)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment: _fail()
    except ValueError: _fail()
    if not _text(license_id,128) or assertion_class not in ('community_reference','organization_annotation'): _fail()


def reference_import(store, path, expected_sha256, source_revision, source_url, license_id,
                     assertion_class='community_reference'):
    _metadata(expected_sha256, source_revision, source_url, license_id, assertion_class)
    raw = _read(path)
    if hashlib.sha256(raw).hexdigest()!=expected_sha256: _fail('workbench_reference_digest_mismatch')
    body = parse_json(raw)
    if type(body) is not dict or not _text(body.get('name'),512) or not isinstance(body.get('settings'),list): _fail()
    exported_id = _uuid(body.get('id'))
    description = body.get('description')
    if description is not None and (type(description) is not str or len(description)>8192): _fail()
    tokens = _OIB_TOKEN.findall(description or '')
    if len(tokens)>1 or (description or '').count('OIBID:')!=len(tokens): _fail('workbench_reference_oib_ambiguous')
    oib_id = _uuid(tokens[0]) if tokens else None
    settings, blockers = _settings(body)
    unknown = sorted(set(body)-_KNOWN_POLICY_FIELDS)
    if unknown: blockers.append('unmapped_source_fields_retained')
    if body.get('platforms')!='windows10' or body.get('technologies')!='mdm': blockers.append('platform_profile_unqualified')
    if type(body.get('settingCount')) is not int or body['settingCount']!=len(body['settings']): blockers.append('setting_count_unverified')
    if 'assignments' not in body: blockers.append('assignments_not_captured')
    data = {'schema_version':SCHEMA, 'source_sha256':expected_sha256, 'source_revision':source_revision,
            'source_url':source_url, 'license_id':license_id, 'assertion_class':assertion_class,
            'source_authenticity_verified':False, 'raw_source':body, 'raw_bytes_base64':base64.b64encode(raw).decode('ascii'),
            'upstream_oib_id':oib_id, 'upstream_export_id':exported_id,
            'tenant_object_identity':'not_established', 'name':body['name'], 'settings':settings,
            'unknown_fields':unknown, 'blockers':sorted(set(blockers)), 'assignment_coverage':'unknown',
            'native_adoption_support':'UNSUPPORTED', 'vendor_definition_qualification':'not_established',
            'execution_authorized':False, 'cloud_authority':False}
    return store.record_artifact(kind='source_reference', object_id=None, data=data)


def _references(store):
    rows = store.artifacts(kind='source_reference',object_id=None)
    for row in rows:
        data = row.get('data',{})
        if data.get('schema_version')!=SCHEMA: _fail('workbench_reference_schema_unsupported')
        if row.get('tenant_id')!=store.tenant_id: _fail('workbench_reference_tenant_mismatch')
        try:
            _metadata(data['source_sha256'],data['source_revision'],data['source_url'],data['license_id'],data['assertion_class'])
            encoded=data['raw_bytes_base64']
            if not isinstance(encoded,str) or len(encoded)>4*((MAX_REFERENCE_BYTES+2)//3): _fail('workbench_reference_limit')
            raw=base64.b64decode(encoded,validate=True)
            if hashlib.sha256(raw).hexdigest()!=data['source_sha256'] or canonical(parse_json(raw))!=canonical(data['raw_source']):
                _fail('workbench_reference_digest_mismatch')
            if type(data['raw_source']) is not dict or not isinstance(data['raw_source'].get('settings'),list) or not _text(data['raw_source'].get('name'),512) or data['name']!=data['raw_source']['name']:
                _fail()
            settings,_=_settings(data['raw_source'])
            tokens=_OIB_TOKEN.findall(data['raw_source'].get('description') or '')
            if len(tokens)>1 or (data['raw_source'].get('description') or '').count('OIBID:')!=len(tokens): _fail()
            if canonical(settings)!=canonical(data['settings']) or data['upstream_export_id']!=_uuid(data['raw_source']['id']) or data['upstream_oib_id']!=(_uuid(tokens[0]) if tokens else None): _fail()
        except (KeyError,ValueError,TypeError): _fail('workbench_reference_record_invalid')
    return rows


def _mapping():
    path = Path(__file__).resolve().parents[1]/'corrections/contracts/capability-map.json'
    raw = _read(path); value = parse_json(raw)
    if value.get('schema_version')!='1.0.0' or not isinstance(value.get('entries'),list): _fail('workbench_mapping_invalid')
    return value, hashlib.sha256(raw).hexdigest()


def dictionary(store, query=''):
    if type(query) is not str or len(query)>512: _fail()
    entries = {}
    def entry(identifier):
        return entries.setdefault(identifier,{'identifier':identifier,'name':None,'aliases':[],
            'meaning':'unknown','vendor_dictionary':'unresolved','actual_uses':[],'local_mapping':[],'references':[]})
    overview = store.overview()
    for observed in overview.get('objects',[]):
        settings, blockers = _settings(observed.get('body'))
        for setting in settings:
            entry(setting['identifier'])['actual_uses'].append({**setting, 'object_id':observed['object_id'],
                'value':copy.deepcopy(setting['instance']),
                'name':observed.get('name', (observed.get('body') or {}).get('name')),
                'source':copy.deepcopy(observed.get('source')), 'ownership':'unknown',
                'snapshot_id':observed.get('snapshot_id'),'observed_at':observed.get('observed_at'),
                'evidence_class':observed.get('evidence_class','unknown'),'coverage':observed.get('coverage','unknown'),
                'freshness':observed.get('freshness','unknown'),'blockers':blockers})
    for reference in _references(store):
        data = reference['data']
        for setting in data['settings']:
            entry(setting['identifier'])['references'].append({**setting,'reference_id':reference['artifact_id'],
                **{key:data[key] for key in ('source_revision','source_url','license_id','assertion_class','source_sha256','upstream_oib_id','upstream_export_id')},
                'source_authenticity_verified':False,'native_adoption_support':'UNSUPPORTED'})
    mapping, mapping_sha = _mapping()
    for row in mapping['entries']:
        identifier = row.get('setting_definition_id')
        if identifier in entries:
            entry(identifier)['local_mapping'].append({'qualification':mapping['qualification'],
                'mapping_sha256':mapping_sha, 'assertion_class':'local_mapping', 'entry':copy.deepcopy(row),
                'service_definition_qualified':False})
    return {'query':query, 'entries':[entries[key] for key in sorted(entries) if query.casefold() in key.casefold()],
            'freshness':overview.get('freshness','unknown'),'cloud_authority':False,'execution_authorized':False,
            'qualification':'Observed values, bounded local mappings and attributed references are separate; vendor meanings and service applicability remain unknown.'}


def _compare(left, right):
    if left is None or right is None: return {'status':'unknown','reason':'company_desired_not_supplied','differences':[]}
    lrows,lblock = _settings(left); rrows,rblock = _settings(right)
    if lblock or rblock: return {'status':'unknown','blockers':sorted(set(lblock+rblock)),'differences':[]}
    lmap={row['identifier']:row['instance'] for row in lrows}; rmap={row['identifier']:row['instance'] for row in rrows}
    changes=[]
    for identifier in sorted(set(lmap)|set(rmap)):
        if identifier not in lmap: kind='only_right'
        elif identifier not in rmap: kind='only_left'
        elif canonical(lmap[identifier])==canonical(rmap[identifier]): continue
        else: kind='type_or_value_changed'
        changes.append({'identifier':identifier,'change':kind,'left':lmap.get(identifier),'right':rmap.get(identifier)})
    return {'status':'different' if changes else 'equal','scope':'setting_instances_by_definition_id',
            'differences':changes,'targeting_compared':False,'adoption_qualified':False}


def compare_reference(store, object_id, reference_id, company_path=None):
    observed = store.inspect(object_id)
    references = _references(store)
    selected = [row for row in references if row['artifact_id']==reference_id]
    if len(selected)!=1: _fail('workbench_reference_not_found')
    reference=selected[0]; data=reference['data']; upstream=data['raw_source']
    company=None; company_evidence=None
    if company_path is not None:
        raw=_read(company_path); company=parse_json(raw)
        if type(company) is not dict: _fail()
        if any(key in company and company[key]!=expected for key,expected in
               (('tenant_id',store.tenant_id),('object_id',object_id),('id',object_id))):
            _fail('workbench_company_identity_mismatch')
        company_evidence={'assertion_class':'caller_asserted_company_desired','sha256':hashlib.sha256(raw).hexdigest(),
                          'organizational_approval_verified':False}
    history=[]
    for prior in references:
        if prior['artifact_id']==reference_id: continue
        p=prior['data']
        same_oib=data['upstream_oib_id'] is not None and data['upstream_oib_id']==p['upstream_oib_id']
        same_export=data['upstream_export_id']==p['upstream_export_id'] and (not data['upstream_oib_id'] or not p['upstream_oib_id'])
        if not (same_oib or same_export): continue
        comparison=_compare(p['raw_source'],upstream)
        fields_changed={key for key in set(p['raw_source'])|set(upstream)
                        if key not in p['raw_source'] or key not in upstream or canonical(p['raw_source'][key])!=canonical(upstream[key])}
        metadata_fields={'name','lastModifiedDateTime','lastModifiedDateTime@odata.type'}
        if comparison['status']=='unknown': change_class='unknown'
        elif comparison['status']=='different': change_class='settings_changed'
        elif not fields_changed: change_class='unchanged'
        elif fields_changed<=metadata_fields: change_class='name_or_metadata_only'
        elif fields_changed<=metadata_fields|{'settings'}: change_class='setting_representation_changed'
        else: change_class='non_setting_fields_changed'
        history.append({'reference_id':prior['artifact_id'],'source_revision':p['source_revision'],
                        'lineage_basis':'matching_upstream_oib_token' if same_oib else 'matching_upstream_export_id_candidate',
                        'lineage_authenticated':False,'tenant_identity_established':False,
                        'chronology_verified':False,'comparison_direction':'other_reference_to_selected',
                        'change_class':change_class,'changed_top_level_fields':sorted(fields_changed),
                        'name_before':p['name'],'name_after':data['name'],'settings':comparison})
    return {'tenant_id':store.tenant_id,'object_id':object_id,'reference_id':reference_id,
            'identity':{'tenant_object_id':object_id,'upstream_oib_id':data['upstream_oib_id'],
                        'upstream_export_id':data['upstream_export_id'],'upstream_to_tenant_link':'explicit_comparison_selection_only'},
            'reference':{key:data[key] for key in ('source_sha256','source_revision','source_url','license_id','assertion_class')},
            'observed':{'snapshot_id':observed.get('snapshot_id'),'observed_at':observed.get('observed_at'),
                        'coverage':observed.get('coverage','unknown'),'freshness':observed.get('freshness','unknown')},
            'company':company_evidence,'comparisons':{'upstream_vs_observed':_compare(upstream,observed['body']),
                'upstream_vs_company':_compare(upstream,company),'company_vs_observed':_compare(company,observed['body'])},
            'reference_history':history,'drift_established':False,'automatic_overwrite':False,
            'execution_authorized':False,'cloud_authority':False,
            'qualification':'Reference differences are review evidence only; company input is caller-asserted and no tenant ownership, approval, vendor semantics or rollout authority is established.'}
