"""Private, tenant-bound local observation memory for the explicit synthetic lab.

The collector is a reader of ModeledService, never a configuration writer. SQLite
FULL transactions publish complete batches atomically; failed attempts retain the
last complete batch. A cooperative same-user store is not a tamper-proof audit log
or a power-loss qualification. No cloud authentication is implemented here.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from datetime import datetime, timezone
import math
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time
from uuid import UUID

from .io import AppError, canonical, digest, parse_json, sync_directory
from .modeled_service import BASE, FIELDS, MAX_OBJECTS, ModeledService

SCHEMA_VERSION = 1
MAX_DOCUMENT = 2 * 1024 * 1024
MAX_QUERY_ROWS = 1000
MAX_QUERY_BYTES = 16 * 1024 * 1024
_SECRET_KEYS = frozenset({'access_token', 'refresh_token', 'client_secret', 'password', 'authorization', 'private_key', 'api_key'})

_SCHEMA_SQL = '''
                BEGIN IMMEDIATE;
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE collection_runs(run_id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL,
                    started_at REAL NOT NULL, observed_at REAL NOT NULL, completed_at REAL,
                    status TEXT NOT NULL, coverage TEXT NOT NULL, error_code TEXT, object_count INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE snapshots(snapshot_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    object_id TEXT NOT NULL, body_json TEXT NOT NULL);
                CREATE TABLE observations(observation_id INTEGER PRIMARY KEY,
                    run_id INTEGER NOT NULL REFERENCES collection_runs(run_id),
                    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                    tenant_id TEXT NOT NULL, object_id TEXT NOT NULL, observed_at REAL NOT NULL, source_json TEXT NOT NULL,
                    UNIQUE(run_id, object_id));
                CREATE INDEX observation_history ON observations(tenant_id,object_id,observed_at);
                CREATE TABLE relationships(snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                    relation TEXT NOT NULL,target_id TEXT NOT NULL,details_json TEXT NOT NULL,
                    PRIMARY KEY(snapshot_id,relation,target_id,details_json));
                CREATE TABLE deployments(run_id INTEGER PRIMARY KEY REFERENCES collection_runs(run_id), data_json TEXT NOT NULL);
                CREATE TABLE operations(sequence INTEGER PRIMARY KEY, operation_id TEXT NOT NULL,
                    object_id TEXT, data_json TEXT NOT NULL, recorded_at REAL NOT NULL);
                PRAGMA user_version=1;
                COMMIT;
            '''


def _fail(code):
    raise AppError(code, 'Workbench observation evidence is unavailable, incomplete, or outside the supported local profile.')


def _json(value):
    try:
        data = canonical(value)
        if len(data) > MAX_DOCUMENT: _fail('workbench_document_limit')
        result = parse_json(data)
        pending = [result]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                if any(str(k).lower() in _SECRET_KEYS for k in item): _fail('workbench_secret_field_rejected')
                pending.extend(item.values())
            elif isinstance(item, list): pending.extend(item)
        return data.decode('utf-8')
    except (TypeError, UnicodeError, RecursionError): _fail('workbench_document_invalid')


def _identity(value):
    try:
        if type(value) is not str or str(UUID(value)) != value: _fail('workbench_identity_invalid')
    except (ValueError, AttributeError): _fail('workbench_identity_invalid')
    return value


def _timestamp(value=None):
    if value is None: return time.time()
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None: _fail('workbench_time_invalid')
            value = parsed.timestamp()
        except ValueError: _fail('workbench_time_invalid')
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 253402300799:
        _fail('workbench_time_invalid')
    return float(value)


def _iso(value):
    return None if value is None else datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


def _path(value):
    path = Path(value).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)): _fail('workbench_symlink_rejected')
    return path


def _private(path, directory=False):
    path = _path(path)
    info = path.stat()
    if ((not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
            or info.st_uid != os.geteuid() or info.st_mode & 0o077 or (not directory and info.st_nlink != 1)):
        _fail('workbench_path_not_private')
    return path


def _deployment(value, observed_at):
    if value is None: return None
    if type(value) is not dict or set(value) - {'targeted', 'reporting', 'successful', 'failed', 'pending', 'observed_at'}:
        _fail('workbench_deployment_invalid')
    value = dict(value)
    for key in ('targeted', 'reporting', 'successful'):
        if type(value.get(key)) is not int or not 0 <= value[key] <= 100000000: _fail('workbench_deployment_invalid')
    for key in ('failed', 'pending'):
        if key in value and (type(value[key]) is not int or value[key] < 0): _fail('workbench_deployment_invalid')
    if not value['successful'] <= value['reporting'] <= value['targeted']: _fail('workbench_deployment_inconsistent')
    if value['successful'] + value.get('failed', 0) + value.get('pending', 0) > value['reporting']:
        _fail('workbench_deployment_inconsistent')
    value['observed_at'] = _timestamp(value.get('observed_at', observed_at))
    if value['observed_at'] > observed_at: _fail('workbench_deployment_future')
    return value



def _validate_body(body):
    if (set(body) != FIELDS or type(body['name']) is not str or not body['name']
            or body['description'] is not None and type(body['description']) is not str
            or type(body['platforms']) is not str or type(body['technologies']) is not list
            or any(type(v) is not str for v in body['technologies'])
            or type(body['role_scope_tag_ids']) is not list or any(type(v) is not str for v in body['role_scope_tag_ids'])
            or type(body['settings']) is not dict or type(body['settings'].get('settings')) is not list
            or any(type(v) is not dict for v in body['settings']['settings']) or type(body['assignments']) is not list):
        _fail('workbench_missing_coverage')
    for assignment in body['assignments']:
        if type(assignment) is not dict or assignment.get('type') not in (
                'groupAssignmentTarget','exclusionGroupAssignmentTarget','allDevicesAssignmentTarget','allLicensedUsersAssignmentTarget'):
            _fail('workbench_missing_coverage')
        if assignment['type'] in ('groupAssignmentTarget','exclusionGroupAssignmentTarget'): _identity(assignment.get('group_id'))
        mode = assignment.get('filter_type')
        if mode not in ('none','include','exclude'): _fail('workbench_missing_coverage')
        if mode != 'none': _identity(assignment.get('filter_id'))
        elif assignment.get('filter_id') not in (None,''): _fail('workbench_missing_coverage')


def _page(limit, offset):
    if type(offset) is not int or not 0 <= offset <= 1000000000: _fail('workbench_query_invalid')
    if limit is None: return MAX_QUERY_ROWS, offset, True
    if type(limit) is not int or not 1 <= limit <= MAX_QUERY_ROWS: _fail('workbench_query_invalid')
    return limit, offset, False


def _schema_signature(db):
    return [tuple(row) for row in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name')]


@lru_cache(maxsize=1)
def _expected_schema():
    db = sqlite3.connect(':memory:')
    try:
        db.executescript(_SCHEMA_SQL)
        return _schema_signature(db)
    finally: db.close()


def _validate_schema(db):
    if db.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION: _fail('workbench_schema_unsupported')
    if _schema_signature(db) != _expected_schema(): _fail('workbench_schema_invalid')


def _edges(body):
    edges = []
    for assignment in body['assignments']:
        kind = 'exclusion' if assignment.get('type') == 'exclusionGroupAssignmentTarget' else 'assignment'
        target = assignment.get('group_id', assignment.get('type', 'unknown'))
        edges.append((kind, target, assignment))
        if assignment.get('filter_id'):
            edges.append(('filter', assignment['filter_id'], {'mode': assignment.get('filter_type'), 'assignment_target': target}))
    for tag in body['role_scope_tag_ids']:
        edges.append(('scope_tag', str(tag), {'assertion_class': 'observed'}))
    pending = [body['settings']]
    seen = set()
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            definition = value.get('settingDefinitionId')
            if isinstance(definition, str) and definition not in seen:
                seen.add(definition); edges.append(('setting', definition, {'assertion_class': 'observed', 'meaning': 'unknown'}))
            pending.extend(value.values())
        elif isinstance(value, list): pending.extend(value)
    return edges


class WorkbenchStore:
    """Versioned bounded synthetic observations; queries have no service effects."""
    def __init__(self, root, tenant_id=None):
        self.root = _private(root, True)
        self.path = _private(self.root / 'observations.sqlite3')
        with self._connection() as db:
            _validate_schema(db)
            row = db.execute("SELECT value FROM metadata WHERE key='tenant_id'").fetchone()
            if row is None: _fail('workbench_schema_invalid')
            self.tenant_id = _identity(row[0])
            if tenant_id is not None and _identity(tenant_id) != self.tenant_id: _fail('workbench_wrong_tenant')

    @classmethod
    def create(cls, root, tenant_id):
        tenant_id = _identity(tenant_id)
        root = _path(root)
        if not root.parent.is_dir(): _fail('workbench_parent_required')
        root.mkdir(mode=0o700, exist_ok=False)
        sync_directory(root.parent)
        path = root / 'observations.sqlite3'
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        db = sqlite3.connect(path)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=FULL')
            db.executescript(_SCHEMA_SQL)
            with db: db.execute('INSERT INTO metadata VALUES(?,?)', ('tenant_id', tenant_id))
        finally: db.close()
        sync_directory(root)
        return cls(root, tenant_id)

    @contextmanager
    def _connection(self, write=False):
        _private(self.root, True); _private(self.path)
        for suffix in ('-journal', '-wal', '-shm'):
            candidate = Path(str(self.path) + suffix)
            if candidate.exists() or candidate.is_symlink(): _private(candidate)
        try:
            db = sqlite3.connect(self.path.as_uri() + ('?mode=rw' if write else '?mode=ro'), uri=True, timeout=5)
        except sqlite3.Error: _fail('workbench_database_error')
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA foreign_keys').fetchone()[0] != 1: _fail('workbench_foreign_keys_disabled')
            if write: db.execute('PRAGMA synchronous=FULL')
            else: db.execute('PRAGMA query_only=ON')
            yield db
        except sqlite3.Error:
            _fail('workbench_database_error')
        finally: db.close()

    def _read(self, service, fault):
        if type(service) is not ModeledService: _fail('workbench_modeled_service_required')
        manifest = service.snapshot()
        if manifest['current']['tenant_id'] != self.tenant_id: _fail('workbench_wrong_tenant')
        expected_ids, expected_revision = set(manifest['current']['objects']), manifest['revision']
        objects, seen, url, revision = {}, set(), BASE, None
        while url is not None:
            if url in seen or len(seen) >= 16 or not re.fullmatch(re.escape(BASE) + r'(?:\?page=[0-9]+)?', url):
                _fail('workbench_pagination_invalid')
            seen.add(url)
            request_fault = fault if fault in ('deny', 'throttle', 'cross-origin', 'loop') else None
            response = service.request('GET', url, tenant_id=self.tenant_id, fault=request_fault)
            if response['status'] != 200:
                _fail('workbench_collection_denied' if response['status'] == 403 else 'workbench_collection_incomplete')
            if revision is not None and response['revision'] != revision: _fail('workbench_revision_changed')
            revision = response['revision']
            body = response['body']
            if type(body) is not dict or type(body.get('value')) is not list: _fail('workbench_collection_incomplete')
            for item in body['value']:
                if type(item) is not dict: _fail('workbench_collection_incomplete')
                oid = _identity(item.get('id'))
                if oid in objects: _fail('workbench_duplicate_identity')
                value = {k: v for k, v in item.items() if k != 'id'}
                if set(value) != FIELDS or type(value['assignments']) is not list or type(value['settings']) is not dict or type(value['role_scope_tag_ids']) is not list:
                    _fail('workbench_missing_coverage')
                _validate_body(value)
                _json(value)
                objects[oid] = value
                if len(objects) > MAX_OBJECTS: _fail('workbench_collection_limit')
            if fault in ('partial', 'after-first-object', 'missing-coverage'): _fail('workbench_missing_coverage')
            url = body.get('@odata.nextLink')
        # The existing in-process lab exposes a revision-bound public manifest.
        # This closes truncated-page ambiguity only for this synthetic adapter;
        # it is not a Microsoft Graph completeness or oracle-isolation claim.
        if set(objects) != expected_ids: _fail('workbench_missing_coverage')
        if revision != expected_revision: _fail('workbench_revision_changed')
        return objects, revision

    def collect(self, service, *, observed_at=None, fault=None, deployment=None, source=None):
        observed_at = _timestamp(observed_at)
        if fault not in (None, 'deny', 'throttle', 'cross-origin', 'loop', 'partial', 'after-first-object', 'missing-coverage', 'before-publish'):
            _fail('workbench_fault_invalid')
        source = {} if source is None else source
        if type(source) is not dict: _fail('workbench_source_invalid')
        source_json = _json(source)
        with self._connection(True) as db, db:
            run_id = db.execute('INSERT INTO collection_runs(tenant_id,started_at,observed_at,status,coverage) VALUES(?,?,?,?,?)',
                (self.tenant_id, time.time(), observed_at, 'collecting', 'unknown')).lastrowid
        try:
            deployment = _deployment(deployment, observed_at)
            objects, revision = self._read(service, fault)
            source_json = _json({**source, 'service_kind':'ModeledService', 'service_root':str(service.root),
                'service_revision':revision, 'coverage_mechanism':'synthetic_revision_and_id_manifest', 'observed_estate_sha256':digest({'tenant_id':self.tenant_id,'objects':objects})})
            if fault == 'before-publish': _fail('workbench_publish_interrupted')
            with self._connection(True) as db, db:
                for oid, body in sorted(objects.items()):
                    snapshot_id = digest({'tenant_id': self.tenant_id, 'object_id': oid, 'body': body})
                    db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?)', (snapshot_id,self.tenant_id,oid,_json(body)))
                    db.execute('INSERT INTO observations(run_id,snapshot_id,tenant_id,object_id,observed_at,source_json) VALUES(?,?,?,?,?,?)',
                        (run_id,snapshot_id,self.tenant_id,oid,observed_at,source_json))
                    for relation, target, details in _edges(body):
                        db.execute('INSERT OR IGNORE INTO relationships VALUES(?,?,?,?)', (snapshot_id,relation,target,_json(details)))
                if deployment is not None: db.execute('INSERT INTO deployments VALUES(?,?)', (run_id,_json(deployment)))
                db.execute("UPDATE collection_runs SET completed_at=?,status='complete',coverage='complete',object_count=? WHERE run_id=?",
                    (time.time(),len(objects),run_id))
        except (AppError, OSError) as exc:
            code = exc.code if isinstance(exc, AppError) else 'workbench_io_failed'
            status = 'denied' if code == 'workbench_collection_denied' else 'partial' if code in ('workbench_missing_coverage', 'workbench_collection_incomplete', 'workbench_revision_changed') else 'failed'
            with self._connection(True) as db, db:
                db.execute('UPDATE collection_runs SET completed_at=?,status=?,coverage=?,error_code=? WHERE run_id=?',
                    (time.time(),status,status if status in ('denied','partial') else 'unknown',code,run_id))
        with self._connection() as db:
            return self._run(db.execute('SELECT * FROM collection_runs WHERE run_id=?', (run_id,)).fetchone())

    @staticmethod
    def _run(row):
        if row is None: return None
        value = dict(row)
        for key in ('started_at', 'observed_at', 'completed_at'): value[key] = _iso(value[key])
        value['evidence_class'] = 'synthetic'; value['cloud_authority'] = False
        return value

    def _latest(self, db):
        attempt = db.execute('SELECT * FROM collection_runs ORDER BY run_id DESC LIMIT 1').fetchone()
        success = db.execute("SELECT * FROM collection_runs WHERE status='complete' ORDER BY observed_at DESC,run_id DESC LIMIT 1").fetchone()
        return attempt, success

    def _observation(self, db, row):
        body = parse_json(row['body_json'])
        edges = [{'relation': e['relation'], 'target_id': e['target_id'], 'details': parse_json(e['details_json']), 'assertion_class': 'observed'}
                 for e in db.execute('SELECT * FROM relationships WHERE snapshot_id=? ORDER BY relation,target_id', (row['snapshot_id'],))]
        source = parse_json(row['source_json'])
        dictionary = []
        pending = [(body['settings'], '/settings')]
        while pending:
            value, location = pending.pop()
            if isinstance(value, dict):
                if isinstance(value.get('settingDefinitionId'), str):
                    dictionary.append({'identifier':value['settingDefinitionId'], 'name':None, 'aliases':[],
                        'meaning':'unknown', 'type':value.get('@odata.type', 'unknown'), 'value':value,
                        'object_id':row['object_id'], 'observed_path':location, 'assertion_class':'observed',
                        'documentation_source':None, 'documentation_date':None, 'ownership':'unknown'})
                pending.extend((child,location+'/'+str(key)) for key,child in value.items())
            elif isinstance(value,list): pending.extend((child,location+'/'+str(index)) for index,child in enumerate(value))
        for key in ('repository_path', 'source_path', 'atmos_stack', 'component'):
            if source.get(key): edges.append({'relation': 'source_' + key,'target_id':source[key],'details':{},'assertion_class':'attributed_source'})
        return {'tenant_id': self.tenant_id,'object_id':row['object_id'],'name':body.get('name'),
                'snapshot_id':row['snapshot_id'],'run_id':row['run_id'],'observed_at':_iso(row['observed_at']),
                'coverage':'complete','body':body,'source':source,'relationships':edges,'dictionary':dictionary,
                'ownership':'unknown','field_accounting':{field:'observed_complete' for field in sorted(FIELDS)},
                'changed_at':None,'attribution':'unknown','evidence_class':'synthetic','cloud_authority':False}

    @staticmethod
    def _health(deployment, now, max_age_seconds):
        result = {'deployment_scope':'collection', 'configuration_parity':'unknown','service_acceptance':'unknown','endpoint_outcome':'unknown',
                  'endpoint_health':'unknown','rollout_ready':False,'report_freshness':'unknown',
                  'targeted':None,'reporting':None,'successful':None,'failed':None,'pending':None,
                  'reporting_outcome_unknown':None,'unknown_or_stale':None,
                  'reporting_success_percent':None,'targeted_success_percent':None}
        if deployment is None: return result
        stale = now - deployment['observed_at'] > max_age_seconds or deployment['observed_at'] > now
        targeted, reporting, successful = (deployment[k] for k in ('targeted','reporting','successful'))
        unknown_reports = reporting-successful-deployment.get('failed',0)-deployment.get('pending',0)
        result.update(targeted=targeted,reporting=reporting,successful=successful,
            failed=deployment.get('failed'),pending=deployment.get('pending'),reporting_outcome_unknown=unknown_reports,
            report_freshness='stale' if stale else 'fresh',unknown_or_stale=targeted if stale else targeted-reporting+unknown_reports,
            reporting_success_percent=None if not reporting else 100*successful/reporting,
            targeted_success_percent=None if not targeted else 100*successful/targeted,
            observed_at=_iso(deployment['observed_at']))
        return result

    def overview(self, *, now=None, max_age_seconds=3600):
        now = _timestamp(now)
        if type(max_age_seconds) not in (int,float) or not math.isfinite(max_age_seconds) or max_age_seconds < 0: _fail('workbench_age_invalid')
        with self._connection() as db:
            attempt, success = self._latest(db)
            objects, deployment = [], None
            if success:
                rows = db.execute('SELECT o.*,s.body_json FROM observations o JOIN snapshots s USING(snapshot_id) WHERE o.run_id=? ORDER BY o.object_id',(success['run_id'],)).fetchall()
                objects = [self._observation(db,row) for row in rows]
                deployment_row = db.execute('SELECT data_json FROM deployments WHERE run_id=?',(success['run_id'],)).fetchone()
                if deployment_row: deployment = parse_json(deployment_row[0])
            health = self._health(deployment, now, max_age_seconds)
            age = None if success is None else max(0,now-success['observed_at'])
            retained_last_good = success is not None and attempt is not None and attempt['status'] != 'complete'
            freshness = 'unknown' if success is None else 'stale' if retained_last_good or age > max_age_seconds or success['observed_at'] > now else 'fresh'
            for obj in objects: obj.update(health=health, freshness=freshness)
            return {'tenant_id':self.tenant_id,'objects':objects,'last_attempt':self._run(attempt),'last_success':self._run(success),
                    'freshness':freshness,'retained_last_good':retained_last_good,'age_seconds':age,'health':health,'coverage':None if attempt is None else attempt['coverage'],
                    'evidence_class':'synthetic','cloud_authority':False,
                    'limitations':['Bounded synthetic service; no Graph or endpoint qualification.',
                                   'Same-user local storage is not tamper-proof; changed time and attribution are unknown.']}

    def inspect(self, object_id):
        _identity(object_id)
        overview = self.overview()
        for value in overview['objects']:
            if value['object_id'] == object_id:
                value.update(last_attempt=overview['last_attempt'],last_success=overview['last_success'])
                return value
        _fail('workbench_object_missing')

    def history(self, object_id, *, limit=None, offset=0):
        """Observed-time ordered history; explicit pages or fail on oversized result."""
        _identity(object_id)
        limit, offset, require_complete = _page(limit, offset)
        with self._connection() as db:
            rows = db.execute(
                'SELECT o.*,s.body_json FROM observations o JOIN snapshots s USING(snapshot_id) WHERE o.tenant_id=? AND o.object_id=? ORDER BY o.observed_at,o.observation_id LIMIT ? OFFSET ?',
                (self.tenant_id,object_id,limit+1 if require_complete else limit,offset))
            result, size = [], 0
            for row in rows:
                if len(result) >= limit: _fail('workbench_query_limit')
                value = self._observation(db,row); size += len(canonical(value))
                if size > MAX_QUERY_BYTES: _fail('workbench_query_limit')
                result.append(value)
            return result

    def compare(self, object_id, before_id, after_id):
        _identity(object_id)
        with self._connection() as db:
            snapshots = []
            for sid in (before_id,after_id):
                row = db.execute('SELECT body_json FROM snapshots WHERE snapshot_id=? AND tenant_id=? AND object_id=?',(sid,self.tenant_id,object_id)).fetchone()
                if row is None: _fail('workbench_snapshot_missing')
                snapshots.append(parse_json(row[0]))
        before, after = snapshots
        changes = [{'field':key,'before':before.get(key),'after':after.get(key)} for key in sorted(set(before)|set(after))
                   if canonical(before.get(key)) != canonical(after.get(key))]
        return {'tenant_id':self.tenant_id,'object_id':object_id,'before_id':before_id,'after_id':after_id,'changes':changes,
                'equal':not changes,'changed_at':None,'attribution':'unknown','evidence_class':'synthetic'}

    def record_operation(self, operation_id, data):
        if type(operation_id) is not str or not 1 <= len(operation_id) <= 128 or type(data) is not dict: _fail('workbench_operation_invalid')
        if data.get('tenant_id', self.tenant_id) != self.tenant_id: _fail('workbench_wrong_tenant')
        if data.get('cloud_authority') not in (None,False): _fail('workbench_authority_rejected')
        oid = data.get('object_id')
        if oid is not None: _identity(oid)
        body = _json({**data,'tenant_id':self.tenant_id,'cloud_authority':False})
        with self._connection(True) as db, db:
            sequence = db.execute('INSERT INTO operations(operation_id,object_id,data_json,recorded_at) VALUES(?,?,?,?)',
                (operation_id,oid,body,time.time())).lastrowid
        return {'sequence':sequence,'operation_id':operation_id}

    def operations(self, object_id=None, *, limit=None, offset=0):
        if object_id is not None: _identity(object_id)
        limit, offset, require_complete = _page(limit, offset)
        with self._connection() as db:
            rows = db.execute('SELECT * FROM operations WHERE (? IS NULL OR object_id=?) ORDER BY sequence LIMIT ? OFFSET ?',
                (object_id,object_id,limit+1 if require_complete else limit,offset))
            result, size = [], 0
            for row in rows:
                if len(result) >= limit: _fail('workbench_query_limit')
                value = {**parse_json(row['data_json']),'operation_id':row['operation_id'],'sequence':row['sequence'],'recorded_at':_iso(row['recorded_at'])}
                size += len(canonical(value))
                if size > MAX_QUERY_BYTES: _fail('workbench_query_limit')
                result.append(value)
            return result


    def backup(self, destination):
        """Export a consistent protected SQLite copy; never overwrite a backup."""
        destination = _path(destination)
        _private(destination.parent, True)
        if destination.exists(): _fail('workbench_backup_exists')
        descriptor, temporary = tempfile.mkstemp(prefix='.workbench-backup-', dir=destination.parent)
        os.close(descriptor)
        try:
            with self._connection() as source:
                target = sqlite3.connect(temporary)
                try:
                    source.backup(target)
                    if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok': _fail('workbench_backup_invalid')
                finally: target.close()
            with open(temporary, 'rb') as stream:
                os.fsync(stream.fileno())
                sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
            # Hard-link publication is exclusive (unlike replace); the temporary
            # name is immediately removed, restoring the single-link invariant.
            os.link(temporary, destination, follow_symlinks=False)
            os.unlink(temporary)
            sync_directory(destination.parent)
            return {'path':str(destination),'sha256':sha256,'tenant_id':self.tenant_id,'schema_version':SCHEMA_VERSION,
                    'evidence_class':'local_sqlite_backup','cloud_authority':False}
        except (OSError, sqlite3.Error): _fail('workbench_backup_failed')
        finally:
            Path(temporary).unlink(missing_ok=True)

    @classmethod
    def restore(cls, backup, root, tenant_id=None):
        """Restore into a new private directory; existing stores are preserved.

        Backup origin/integrity must be checked against an independently retained
        receipt by the caller. SQLite consistency alone does not prove provenance.
        """
        backup = _private(backup)
        try:
            source = sqlite3.connect(backup.as_uri() + '?mode=ro', uri=True)
            try:
                source.execute('PRAGMA trusted_schema=OFF'); source.execute('PRAGMA query_only=ON')
                _validate_schema(source)
                if source.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or source.execute('PRAGMA foreign_key_check').fetchone():
                    _fail('workbench_backup_invalid')
                row = source.execute("SELECT value FROM metadata WHERE key='tenant_id'").fetchone()
                if row is None: _fail('workbench_backup_invalid')
                restored_tenant = _identity(row[0])
                if tenant_id is not None and _identity(tenant_id) != restored_tenant: _fail('workbench_wrong_tenant')
                result = cls.create(root, restored_tenant)
                with result._connection(True) as target: source.backup(target)
                with open(result.path,'rb') as stream: os.fsync(stream.fileno())
                sync_directory(result.root)
                return cls(root, restored_tenant)
            finally: source.close()
        except sqlite3.Error: _fail('workbench_backup_invalid')
