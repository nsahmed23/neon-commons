"""Policy, application and script families with their actual support disposition.

The product's `family-coverage.csv` is read unchanged: route, material, release
stage, the qualification each family still needs and its live status, plus any
further columns as they are. The only addition is where each family appears in
the workbench today, stated from the implementation rather than inferred. A
runtime without the table, or with a table that cannot be read as written, says
so instead of failing.
"""
from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

VERSION = 'workbench-families/1'
TABLE = 'family-coverage.csv'
COLUMNS = ('family', 'candidate', 'material', 'release_stage', 'qualification_needed', 'live')
# Where each family appears in the workbench today; every other family is not in the estate.
PRESENCE = {
    'Windows plain Settings Catalog': 'estate, inspection, dictionary, history, health, adoption and maintenance (synthetic, offline)',
    'Groups, filters, scope tags': 'shown as referenced targets in the Inspector and Relationships; never managed',
    'Endpoint diagnostics': 'offline analysis materials only (examples/diagnostics); not in the estate',
    'Azure support': 'a backend for generated projects; not in the estate',
}


def _rows(data):
    """The table's rows, or the reason it cannot be read as written."""
    try:
        reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')), strict=True)
        header = list(reader.fieldnames or [])
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as error:
        return None, None, 'unreadable: %s' % str(error)[:200]
    missing = [name for name in COLUMNS if name not in header]
    if missing:
        return None, None, 'missing columns: ' + ', '.join(missing)
    for number, row in enumerate(rows, 2):
        if None in row or any(value is None for value in row.values()):
            return None, None, 'row %d does not have %d fields' % (number, len(header))
    return header, rows, None


def families(root=None):
    """The family coverage table with each family's workbench presence; read-only."""
    path = Path(root or Path(__file__).resolve().parents[1]) / TABLE
    base = {'schema_version': VERSION, 'execution_authorized': False, 'cloud_authority': False}
    if not path.is_file():
        return dict(base, available=False, reason='family_coverage_not_packaged', families=[])
    data = path.read_bytes()
    source = {'path': TABLE, 'sha256': hashlib.sha256(data).hexdigest()}
    header, rows, problem = _rows(data)
    if problem:
        return dict(base, available=False, reason='family_coverage_malformed', detail=problem, source=source, families=[])
    return dict(base, available=True, source=source,
                families=[{'family': row['family'], 'route': row['candidate'], 'material': row['material'],
                           'stage': row['release_stage'], 'qualification_needed': row['qualification_needed'],
                           'live': row['live'], 'workbench': PRESENCE.get(row['family'], 'not in the estate'),
                           'other_columns': {name: row[name] for name in header if name not in COLUMNS}} for row in rows])
