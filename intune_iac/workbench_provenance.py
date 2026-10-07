"""Inert local reference provenance and attributed dictionary/comparison views.

Imported community exports never establish tenant identity, vendor definition
authority, desired-state approval or a new supported provider mapping.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.parse import urlsplit
from uuid import UUID

from .io import AppError, canonical, parse_json

MAX_REFERENCE_BYTES = 512 * 1024
MAX_SETTINGS = 1000
MAX_LINEAGE_FIELDS = 4096
MAX_LINEAGE_ORIGINS = 8192
VENDOR_DOCUMENTATION_SHA256 = 'c758641e932f85014e5ec3451073828ad0f04a20fb850196ae6bb1b0f699bcd8'
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


def _vendor_documentation():
    """Only release-pinned factual summaries qualify as vendor documentation.

    This does not consume caller references or infer Graph choice values from
    CSP integers. Updating facts requires a reviewed source/pin change.
    """
    path = Path(__file__).resolve().parents[1]/'corrections/contracts/vendor-documentation.json'
    raw = _read(path)
    if hashlib.sha256(raw).hexdigest() != VENDOR_DOCUMENTATION_SHA256:
        _fail('workbench_vendor_documentation_changed')
    value = parse_json(raw)
    if (type(value) is not dict or value.get('schema_version') != 'workbench-vendor-documentation/1'
            or type(value.get('entries')) is not list):
        _fail('workbench_vendor_documentation_invalid')
    return value['entries']


def _lineage_pointer(value, *, allow_empty=False):
    return (type(value) is str and ((allow_empty and value == '') or value.startswith('/'))
            and len(value) <= 1024 and not any(ord(c)<32 or 127<=ord(c)<160 for c in value)
            and re.search(r'~(?![01])', value) is None)


def _lineage_path(value):
    return (_text(value, 1024) and not value.startswith('/') and '\\' not in value
            and ':' not in value and all(part not in ('', '.', '..') for part in value.split('/'))
            and not PurePosixPath(value).is_absolute())


def repository_lineage(store, object_id, pointer=None):
    """Navigate a captured value-free literal resolution, never reread/execute it.

    File hashes bind the recorded locations, not their current disk contents or
    publisher authority. Earlier container origins express merge precedence,
    not proof every nested value was overridden. Values remain undisclosed.
    """
    if pointer is not None and not _lineage_pointer(pointer):
        _fail('workbench_lineage_pointer_invalid')
    observed = store.inspect(object_id)
    result = {'tenant_id': store.tenant_id, 'object_id': object_id,
        'snapshot_id': observed.get('snapshot_id'), 'observed_at': observed.get('observed_at'),
        'freshness': observed.get('freshness', 'unknown'), 'status': 'unknown',
        'repository': None, 'sources': [], 'fields': [], 'edges': [], 'blockers': [],
        'provenance_origin': {'kind': 'current_observation', 'snapshot_id': observed.get('snapshot_id')},
        'assertion_class': 'captured_local_literal_resolution', 'source_authenticity_verified': False,
        'native_atmos_qualified': False, 'effective_values_included': False,
        'execution_authorized': False, 'cloud_authority': False,
        'qualification': 'Captured literal source locations and precedence only; current files, native Atmos, tenant authority and Graph-to-variable mapping are not verified.'}
    source = observed.get('source') or {}
    if type(source) is not dict: _fail('workbench_lineage_invalid')
    report = source.get('repository_resolution')
    if report is None:
        adoptions = store.artifacts(kind='adoption', object_id=object_id)
        if adoptions:
            # Store order is immutable local sequence. A later unassociated
            # adoption must not silently inherit an older repository claim.
            latest = adoptions[-1]
            if type(latest) is not dict or type(latest.get('data')) is not dict:
                _fail('workbench_lineage_adoption_invalid')
            data = latest['data']; binding = data.get('binding')
            if (latest.get('tenant_id') != store.tenant_id or latest.get('object_id') != object_id
                    or data.get('schema_version') != 'workbench-adoption/1'
                    or data.get('tenant_id') != store.tenant_id or data.get('object_id') != object_id
                    or data.get('execution_authorized') is not False or data.get('cloud_authority') is not False
                    or type(binding) is not dict or binding.get('schema_version') != 'workbench-adoption/1'
                    or binding.get('tenant_id') != store.tenant_id or type(binding.get('object_ids')) is not list
                    or object_id not in binding['object_ids'] or binding.get('execution_authorized') is not False
                    or data.get('binding_sha256') != hashlib.sha256(canonical(binding)).hexdigest()):
                _fail('workbench_lineage_adoption_invalid')
            report = binding.get('repository')
            if report is not None:
                result['provenance_origin'] = {'kind': 'historical_adoption', 'artifact_id': latest['artifact_id'],
                    'recorded_at': latest.get('recorded_at'), 'binding_sha256': data['binding_sha256']}
                result['observation_freshness'] = result['freshness']
                result['freshness'] = 'historical_not_revalidated'
                result['assertion_class'] = 'historical_local_adoption_resolution'
                source = {}  # Historical repository differs legitimately from later observation metadata.
    if report is None:
        result['reason'] = 'repository_resolution_not_collected'
        return result
    if (type(report) is not dict or report.get('schema_version') != '1.0'
            or report.get('adapter') != 'atmos-literal/1.0'
            or report.get('evaluation_scope') != 'repository_local_literal_configuration'
            or report.get('execution_authorized') is not False or 'effective' in report
            or report.get('status') not in ('resolved', 'blocked')):
        _fail('workbench_lineage_invalid')
    for key in ('root', 'stack', 'component'):
        if not _text(report.get(key), 2048): _fail('workbench_lineage_invalid')
    for source_key, report_key in (('repository_path', 'root'), ('atmos_stack', 'stack'), ('component', 'component')):
        if source_key in source and source[source_key] != report[report_key]: _fail('workbench_lineage_invalid')
    sources = report.get('sources')
    if type(sources) is not list or len(sources) > 512: _fail('workbench_lineage_limit')
    source_hashes = {}
    for row in sources:
        if (type(row) is not dict or set(row) != {'path', 'sha256'} or not _lineage_path(row.get('path'))
                or row['path'] in source_hashes or type(row.get('sha256')) is not str or not _HASH.fullmatch(row['sha256'])):
            _fail('workbench_lineage_invalid')
        source_hashes[row['path']] = row['sha256']
    fingerprint = hashlib.sha256(canonical({'adapter': report['adapter'], 'sources': sources})).hexdigest()
    if report.get('source_fingerprint') != fingerprint: _fail('workbench_lineage_invalid')
    result['sources'] = copy.deepcopy(sources)
    result['repository'] = {'path': report['root'], 'stack': report['stack'], 'component': report['component'],
        'source_fingerprint': fingerprint, 'configuration_sha256': None,
        'observation_only': True, 'current_source_bytes_verified': False}
    blockers = report.get('blockers')
    if type(blockers) is not list or len(blockers) > 128: _fail('workbench_lineage_limit')
    for blocker in blockers:
        if type(blocker) is not dict or not _text(blocker.get('code'), 128): _fail('workbench_lineage_invalid')
        result['blockers'].append({'code': blocker['code'], 'status': 'unknown'})
    if report['status'] == 'blocked':
        result['status'] = 'blocked'
        return result
    if blockers or type(report.get('configuration_sha256')) is not str or not _HASH.fullmatch(report['configuration_sha256']):
        _fail('workbench_lineage_invalid')
    result['repository']['configuration_sha256'] = report['configuration_sha256']
    provenance = report.get('provenance')
    if type(provenance) is not dict: _fail('workbench_lineage_invalid')
    if len(provenance) > MAX_LINEAGE_FIELDS: _fail('workbench_lineage_limit')
    if report.get('effective_fields') != sorted(provenance): _fail('workbench_lineage_invalid')
    if pointer is not None and pointer not in provenance: _fail('workbench_lineage_field_unknown')
    total_origins = 0
    def origin(value):
        if (type(value) is not dict or set(value) != {'path', 'pointer', 'line', 'column'}
                or not _lineage_pointer(value['pointer'], allow_empty=True)
                or any(type(value[k]) is not int or not 0 <= value[k] <= 2147483647 for k in ('line', 'column'))):
            _fail('workbench_lineage_invalid')
        path = value['path']
        if path == 'atmos-literal/1.0' and value['pointer'] == '/defaults/command' and value['line'] == value['column'] == 0:
            return {**value, 'sha256': None, 'source_kind': 'resolver_default'}
        if (not _lineage_path(path) or path not in source_hashes or value['line'] < 1 or value['column'] < 1):
            _fail('workbench_lineage_invalid')
        return {**value, 'sha256': source_hashes[path], 'source_kind': 'captured_repository_file'}
    for field in sorted(provenance):
        row = provenance[field]
        if (not _lineage_pointer(field) or type(row) is not dict or set(row) != {'winner', 'history'}
                or type(row['history']) is not list or not row['history']):
            _fail('workbench_lineage_invalid')
        total_origins += len(row['history'])
        if total_origins > MAX_LINEAGE_ORIGINS: _fail('workbench_lineage_limit')
        history = [origin(value) for value in row['history']]
        winner = origin(row['winner'])
        if canonical(winner) != canonical(history[-1]): _fail('workbench_lineage_invalid')
        if pointer is not None and field != pointer: continue
        result['fields'].append({'effective_pointer': field, 'winner': winner, 'history': history,
                                 'earlier_origins': history[:-1]})
        result['edges'].append({'relation': 'defined_in', 'effective_pointer': field, 'origin': winner})
        for earlier, later in zip(history, history[1:]):
            result['edges'].append({'relation': 'precedence_before', 'effective_pointer': field,
                                    'earlier': earlier, 'later': later})
    result['status'] = 'available'
    return result


def dictionary(store, query=''):
    if type(query) is not str or len(query)>512: _fail()
    entries = {}
    def entry(identifier):
        return entries.setdefault(identifier,{'identifier':identifier,'name':None,'aliases':[],
            'meaning':'unknown','vendor_dictionary':'unresolved','actual_uses':[],'local_mapping':[],
            'references':[],'vendor_documentation':[]})
    overview = store.overview()
    for observed in overview.get('objects',[]):
        settings, blockers = _settings(observed.get('body'))
        for setting in settings:
            entry(setting['identifier'])['actual_uses'].append({**setting, 'object_id':observed['object_id'],
                'value':copy.deepcopy(setting['instance']),
                'name':observed.get('name', (observed.get('body') or {}).get('name')),
                'source':copy.deepcopy(observed.get('source')), 'ownership':'unknown',
                'repository_lineage': {'object_id': observed['object_id'], 'command': 'lineage',
                    'navigation_supported': True,
                    'current_resolution_recorded': type((observed.get('source') or {}).get('repository_resolution')) is dict,
                    'historical_resolution_status': 'query_required'},
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
    for facts in _vendor_documentation():
        identifier = facts['setting_definition_id']
        if identifier in entries:
            entry(identifier)['vendor_documentation'].append(copy.deepcopy(facts))
    def matches(row):
        terms = [row['identifier'], *row['aliases']]
        for facts in row['vendor_documentation']:
            terms.extend([facts['name'], facts['csp_uri'], *facts['aliases']])
        return any(query.casefold() in term.casefold() for term in terms)
    return {'query':query, 'entries':[entries[key] for key in sorted(entries) if matches(entries[key])],
            'freshness':overview.get('freshness','unknown'),'cloud_authority':False,'execution_authorized':False,
            'qualification':'Observed values, local mappings, community/company references and pinned vendor documentation are separate. Graph enum translation and observed-device applicability remain unqualified.'}


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
