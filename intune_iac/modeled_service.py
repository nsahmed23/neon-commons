"""Durable, account-free Intune request model; never an HTTP/live adapter.

Only explicit synthetic captures are admitted. The raw-capture projector is
independent of the production normalizer/serializer. Service state and modeled
requests live in one atomically replaced snapshot under a cooperative lock.
This models supported semantics/faults, not Microsoft Graph authorization or
service timing, and is not a hostile-host containment boundary.
"""
from __future__ import annotations

from collections import Counter
import copy
import fcntl
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit
from uuid import UUID

from .io import AppError, canonical, digest, load_json, write_json, sync_directory

VERSION = 'intune-stateful-model/1.0'
BASE = 'https://intune-model.invalid/policies'
GRAPH = 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'
FIELDS = frozenset({'name', 'description', 'platforms', 'technologies', 'role_scope_tag_ids', 'settings', 'assignments'})
MAX_OBJECTS = 8
MAX_REQUESTS = 4096
FAULTS = frozenset({None, 'deny', 'throttle', 'lost-response', 'after-policy', 'cross-origin', 'loop'})


def _fail(code):
    raise AppError(code, 'Synthetic service evidence is incomplete, changed, or outside the supported model.')


def _uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value: _fail('model_identity_invalid')
    except (ValueError, AttributeError): _fail('model_identity_invalid')
    return value


def _bag(value):
    if type(value) is not list: _fail('model_collection_invalid')
    return Counter(digest(item) for item in value)


def _pages(capture, kind, owner):
    rows = [r for r in capture.get('collections', []) if r.get('kind') == kind and r.get('owner_id') == owner]
    if len(rows) != 1 or rows[0].get('coverage') != 'complete': _fail('model_capture_incomplete')
    pages = rows[0].get('pages')
    if type(pages) is not list or not pages or len(pages) > 1024: _fail('model_capture_incomplete')
    expected = GRAPH + ('/' + owner + '/' + kind if owner else '')
    collection_path = urlsplit(expected).path
    seen, records = set(), []
    for page in pages:
        if type(page) is not dict or page.get('request_url') != expected or expected in seen:
            _fail('model_pagination_invalid')
        seen.add(expected)
        parsed = urlsplit(expected)
        if (parsed.scheme != 'https' or parsed.netloc != 'graph.microsoft.com'
                or parsed.path != collection_path or parsed.fragment):
            _fail('model_pagination_invalid')
        body = page.get('body')
        if page.get('method') != 'GET' or page.get('http_status') != 200 or type(body) is not dict or type(body.get('value')) is not list:
            _fail('model_capture_incomplete')
        if len(records) + len(body['value']) > 1024: _fail('model_collection_limit')
        records.extend(copy.deepcopy(body['value']))
        expected = body.get('@odata.nextLink')
    if expected is not None: _fail('model_capture_incomplete')
    if any(type(row) is not dict or type(row.get('id')) is not str for row in records): _fail('model_record_invalid')
    if len({row['id'] for row in records}) != len(records): _fail('model_duplicate_identity')
    return records


def project_capture(capture, selected_ids):
    """Author supported expected semantics directly from complete raw pages.

    Setting subtrees remain exact; list permutations in assignments/tags/tech
    may be equivalent. Null, omitted, and empty assignments are not conflated.
    Unknown content is rejected by the engine before execution, independently
    of this projection; this model never grants mapping readiness or authority.
    """
    if type(capture) is not dict or capture.get('synthetic') is not True or capture.get('cloud') != 'public':
        _fail('model_synthetic_capture_required')
    tenant = _uuid(capture.get('tenant_id'))
    if type(selected_ids) is not list or not 1 <= len(selected_ids) <= MAX_OBJECTS or len(set(selected_ids)) != len(selected_ids):
        _fail('model_selection_invalid')
    policies = {row['id']: row for row in _pages(capture, 'policies', None)}
    objects = {}
    for oid in selected_ids:
        _uuid(oid)
        if oid not in policies: _fail('model_identity_missing')
        policy = policies[oid]
        settings = _pages(capture, 'settings', oid)
        assignments = _pages(capture, 'assignments', oid)
        targets = []
        for row in assignments:
            target = row.get('target')
            if type(target) is not dict or type(target.get('@odata.type')) is not str or not target['@odata.type'].startswith('#microsoft.graph.'):
                _fail('model_target_invalid')
            kind = target['@odata.type'].removeprefix('#microsoft.graph.')
            if kind not in ('groupAssignmentTarget', 'exclusionGroupAssignmentTarget', 'allDevicesAssignmentTarget', 'allLicensedUsersAssignmentTarget'):
                _fail('model_target_unsupported')
            item = {'type': kind}
            if 'groupId' in target: item['group_id'] = _uuid(target['groupId'])
            if kind in ('groupAssignmentTarget', 'exclusionGroupAssignmentTarget') and 'group_id' not in item:
                _fail('model_target_invalid')
            mode = target.get('deviceAndAppManagementAssignmentFilterType')
            if mode not in ('none', 'include', 'exclude'): _fail('model_filter_invalid')
            item['filter_type'] = mode
            fid = target.get('deviceAndAppManagementAssignmentFilterId')
            if mode == 'none':
                if fid not in (None, ''): _fail('model_filter_invalid')
            else: item['filter_id'] = _uuid(fid)
            targets.append(item)
        technology = policy.get('technologies')
        if type(technology) is not str or not technology: _fail('model_policy_invalid')
        desired = {'name': policy.get('name'), 'description': policy.get('description'),
            'platforms': policy.get('platforms'), 'technologies': technology.split(','),
            'role_scope_tag_ids': copy.deepcopy(policy.get('roleScopeTagIds')),
            'settings': {'settings': [{k: copy.deepcopy(v) for k, v in row.items() if k != '@odata.type'} for row in settings]},
            'assignments': targets}
        if type(desired['name']) is not str or not desired['name'] or type(desired['role_scope_tag_ids']) is not list:
            _fail('model_policy_invalid')
        objects[oid] = desired
    return {'schema_version': 'intune-semantic-estate/1.0', 'tenant_id': tenant,
            'cloud': 'public', 'objects': objects}


def compare_semantics(expected, actual):
    """Return independent field-level mismatches; never bless dropped fields."""
    issues = []
    if type(actual) is not dict or set(actual) != set(expected): return ['estate_shape_changed']
    for key in ('schema_version', 'tenant_id', 'cloud'):
        if actual[key] != expected[key]: issues.append(key + '_changed')
    if type(actual['objects']) is not dict or set(actual['objects']) != set(expected['objects']):
        return issues + ['immutable_ids_changed']
    for oid, desired in expected['objects'].items():
        seen = actual['objects'][oid]
        if type(seen) is not dict or set(seen) != FIELDS:
            issues.append(oid + ':field_shape_changed'); continue
        for field in FIELDS:
            try:
                equal = (_bag(desired[field]) == _bag(seen[field])
                         if field in ('assignments', 'technologies', 'role_scope_tag_ids')
                         else digest(desired[field]) == digest(seen[field]))
            except (AppError, ValueError, TypeError): equal = False
            if not equal: issues.append(oid + ':' + field + '_changed')
    return sorted(issues)


def _safe(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)): _fail('model_symlink_rejected')
    return path


class ModeledService:
    """Explicit local model API with stable immutable IDs, ETags and faults."""
    def __init__(self, root):
        self.root = _safe(root)
        self.path = _safe(self.root / 'service.json')
        if not self.root.is_dir(): _fail('model_service_missing')

    @classmethod
    def create(cls, root, capture, selected_ids):
        expected = project_capture(capture, selected_ids)
        root = _safe(root)
        if not root.parent.is_dir(): _fail('model_parent_required')
        root.mkdir(mode=0o700, exist_ok=False); sync_directory(root.parent)
        write_json(root / 'service.json', {'schema_version': VERSION, 'source_sha256': digest(capture),
            'initial': expected, 'current': copy.deepcopy(expected), 'revision': 1, 'requests': []})
        return cls(root)

    def _load(self):
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 8 * 1024 * 1024:
            _fail('model_state_invalid')
        value = load_json(self.path)
        if (type(value) is not dict or set(value) != {'schema_version', 'source_sha256', 'initial', 'current', 'revision', 'requests'}
                or value['schema_version'] != VERSION or type(value['revision']) is not int or value['revision'] < 1
                or type(value['requests']) is not list or len(value['requests']) > MAX_REQUESTS): _fail('model_state_invalid')
        return value

    def snapshot(self):
        return copy.deepcopy(self._load())

    def request(self, method, path, *, tenant_id, body=None, if_match=None, fault=None, page_size=2):
        """Execute one modeled request, with no sockets or credentials.

        PATCH can fail after policy facets but before assignments, or lose its
        response after a complete durable write. GET readback is always fresh.
        All requests/outcomes, including denied ones, are retained atomically.
        """
        if (fault not in FAULTS or type(page_size) is not int or not 1 <= page_size <= 8
                or type(method) is not str or method not in ('GET', 'POST', 'PATCH', 'DELETE')
                or type(path) is not str or len(path) > 4096): _fail('model_request_invalid')
        try:
            if len(canonical(body)) > 1024 * 1024: _fail('model_request_limit')
        except (TypeError, ValueError, RecursionError): _fail('model_request_invalid')
        lock = _safe(self.root / 'service.lock')
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1: _fail('model_lock_invalid')
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: _fail('model_writer_busy')
            state = self._load()
            if len(state['requests']) >= MAX_REQUESTS: _fail('model_request_limit')
            before = digest(state['current'])
            record = {'sequence': len(state['requests']) + 1, 'method': method, 'path': path,
                'request_body': copy.deepcopy(body), 'if_match': if_match, 'before_sha256': before,
                'fault': fault, 'status': None, 'revision_before': state['revision'], 'evidence_class': 'modeled_request'}
            status, response, mutation = 400, {'error': 'unsupported_request'}, False
            if tenant_id != state['current']['tenant_id']:
                status, response = 403, {'error': 'wrong_tenant'}
            elif fault in ('deny', 'throttle'):
                status, response = (403, {'error': 'denied'}) if fault == 'deny' else (429, {'error': 'throttled', 'retry_after': 1})
            elif type(path) is str and path.startswith(BASE):
                suffix = path[len(BASE):]
                objects = state['current']['objects']
                if method == 'GET' and (suffix == '' or suffix.startswith('?page=')):
                    try: start = 0 if not suffix else int(suffix.removeprefix('?page='))
                    except ValueError: start = -1
                    if 0 <= start <= len(objects):
                        ids = sorted(objects)[start:start + page_size]
                        response = {'value': [{'id': oid, **copy.deepcopy(objects[oid])} for oid in ids]}
                        if start + page_size < len(objects): response['@odata.nextLink'] = BASE + '?page=' + str(start + page_size)
                        if fault == 'cross-origin': response['@odata.nextLink'] = 'https://example.invalid/forbidden'
                        if fault == 'loop': response['@odata.nextLink'] = path
                        status = 200
                elif suffix.startswith('/') and suffix[1:] in objects:
                    oid = suffix[1:]
                    if method == 'GET': status, response = 200, {'id': oid, **copy.deepcopy(objects[oid]), '@odata.etag': str(state['revision'])}
                    elif method == 'PATCH' and type(body) is dict and set(body) == FIELDS:
                        if if_match != str(state['revision']): status, response = 412, {'error': 'stale_revision'}
                        else:
                            old_assignments = copy.deepcopy(objects[oid]['assignments'])
                            objects[oid] = copy.deepcopy(body)
                            if fault == 'after-policy': objects[oid]['assignments'] = old_assignments
                            state['revision'] += 1; mutation = True
                            status, response = (503, {'error': 'partial_write'}) if fault == 'after-policy' else (200, {'id': oid, '@odata.etag': str(state['revision'])})
                    elif method == 'DELETE' and if_match == str(state['revision']):
                        del objects[oid]; state['revision'] += 1; mutation = True; status, response = 204, None
                elif method == 'POST' and suffix == '' and type(body) is dict and set(body) == FIELDS | {'id'}:
                    oid = _uuid(body['id'])
                    if oid in objects: status, response = 409, {'error': 'duplicate_identity'}
                    elif len(objects) >= MAX_OBJECTS: status, response = 413, {'error': 'scale_limit'}
                    else:
                        objects[oid] = {k: copy.deepcopy(v) for k, v in body.items() if k != 'id'}
                        state['revision'] += 1; mutation = True; status, response = 201, {'id': oid}
            record.update(status=status, after_sha256=digest(state['current']), revision_after=state['revision'],
                          mutation_committed=mutation, response_lost=fault == 'lost-response' and mutation)
            state['requests'].append(record); write_json(self.path, state)
            if record['response_lost']: _fail('model_response_lost')
            return {'status': status, 'body': response, 'revision': state['revision'], 'model_only': True}
        finally:
            os.close(fd)

    def readback(self, *, tenant_id):
        objects, seen, url, revision = {}, set(), BASE, None
        while url is not None:
            if url in seen or len(seen) >= 16 or not (url == BASE or url.startswith(BASE + '?page=')):
                _fail('model_readback_pagination_invalid')
            seen.add(url)
            response = self.request('GET', url, tenant_id=tenant_id)
            if response['status'] != 200 or (revision is not None and response['revision'] != revision):
                _fail('model_readback_incomplete')
            revision = response['revision']
            for item in response['body']['value']:
                oid = item['id']
                if oid in objects: _fail('model_readback_duplicate')
                objects[oid] = {key: value for key, value in item.items() if key != 'id'}
            url = response['body'].get('@odata.nextLink')
        return {'schema_version': 'intune-semantic-estate/1.0', 'tenant_id': tenant_id,
                'cloud': 'public', 'objects': objects}
