"""Portable exact Workbench schema contract; no host or persistence dispatch."""
from functools import lru_cache
import sqlite3
from .io import AppError

SCHEMA_VERSION = 2
_SCHEMA_SQL_V1 = '''
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


_MIGRATION_STATEMENTS = (
    "CREATE TABLE run_details(run_id INTEGER PRIMARY KEY REFERENCES collection_runs(run_id), scope_json TEXT NOT NULL, source_json TEXT NOT NULL, evidence_class TEXT NOT NULL, domain TEXT NOT NULL)",
    "CREATE TABLE run_scope_objects(run_id INTEGER NOT NULL REFERENCES collection_runs(run_id), object_id TEXT NOT NULL, PRIMARY KEY(run_id,object_id))",
    "CREATE INDEX scoped_runs ON run_scope_objects(object_id,run_id)",
    "CREATE TABLE collection_coverage(run_id INTEGER NOT NULL REFERENCES collection_runs(run_id), kind TEXT NOT NULL, owner_id TEXT NOT NULL, coverage TEXT NOT NULL, reason TEXT, page_count INTEGER NOT NULL, PRIMARY KEY(run_id,kind,owner_id))",
    "CREATE TABLE object_heads(object_id TEXT PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES collection_runs(run_id), observation_id INTEGER REFERENCES observations(observation_id), observed_at REAL NOT NULL, present INTEGER NOT NULL CHECK(present IN (0,1)), domain TEXT NOT NULL)",
    "CREATE TABLE artifacts(sequence INTEGER PRIMARY KEY, artifact_id TEXT NOT NULL UNIQUE, tenant_id TEXT NOT NULL, kind TEXT NOT NULL, object_id TEXT, data_json TEXT NOT NULL, recorded_at REAL NOT NULL)",
    "CREATE INDEX artifact_lookup ON artifacts(kind,object_id,sequence)",
)
_SCHEMA_SQL = _SCHEMA_SQL_V1 + '\nBEGIN IMMEDIATE;\n' + ';\n'.join(_MIGRATION_STATEMENTS) + ';\nPRAGMA user_version=2;\nCOMMIT;\n'

def _fail(code):
    raise AppError(code, 'Workbench observation evidence is unavailable, incomplete, or outside the supported local profile.')

def _schema_signature(db):
    return [tuple(row) for row in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name')]


@lru_cache(maxsize=2)
def _expected_schema(version=SCHEMA_VERSION):
    db = sqlite3.connect(':memory:')
    try:
        db.executescript(_SCHEMA_SQL_V1 if version == 1 else _SCHEMA_SQL)
        return _schema_signature(db)
    finally: db.close()


def _validate_schema(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in (1,SCHEMA_VERSION): _fail('workbench_schema_unsupported')
    if _schema_signature(db) != _expected_schema(version): _fail('workbench_schema_invalid')
    return version
