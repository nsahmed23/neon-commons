"""Policy, application and script families with their actual support disposition.

The product's `family-coverage.csv` is read unchanged: route, material, release
stage, the qualification each family still needs and its live status. The only
addition is where each family appears in the workbench today, stated from the
implementation rather than inferred. A runtime without the table says so.
"""
from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

VERSION = 'workbench-families/1'
TABLE = 'family-coverage.csv'
# Where each family appears in the workbench today; every other family is not in the estate.
PRESENCE = {
    'Windows plain Settings Catalog': 'estate, inspection, dictionary, history, health, adoption and maintenance (synthetic, offline)',
    'Groups, filters, scope tags': 'shown as referenced targets in the Inspector and Relationships; never managed',
    'Endpoint diagnostics': 'offline analysis materials only (examples/diagnostics); not in the estate',
    'Azure support': 'a backend for generated projects; not in the estate',
}


def families(root=None):
    """The family coverage table with each family's workbench presence; read-only."""
    path = Path(root or Path(__file__).resolve().parents[1]) / TABLE
    base = {'schema_version': VERSION, 'execution_authorized': False, 'cloud_authority': False}
    if not path.is_file():
        return dict(base, available=False, reason='family_coverage_not_packaged', families=[])
    data = path.read_bytes()
    rows = list(csv.DictReader(io.StringIO(data.decode('utf-8'))))
    return dict(base, available=True, source={'path': TABLE, 'sha256': hashlib.sha256(data).hexdigest()},
                families=[{'family': row['family'], 'route': row['candidate'], 'material': row['material'],
                           'stage': row['release_stage'], 'qualification_needed': row['qualification_needed'],
                           'live': row['live'], 'workbench': PRESENCE.get(row['family'], 'not in the estate')} for row in rows])
