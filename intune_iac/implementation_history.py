"""Released implementation digests, consulted only when a record is read as history.

A protected operation binds the implementation that prepared it (protected.py, _bindings) and a native Atmos
receipt binds its own file set (journey_native_atmos.py, _implementation). Editing any bound file changes the
current value, so a record made earlier no longer equals it. Execution must still refuse such a record; reading it
as history may accept it only when its implementation is one this table recognises.

Recognition is not authentication. The table rejects an invented digest. It cannot show which recognised
implementation produced a record, so on unsigned local files a record relabelled with a recognised digest (or with
the current one) and every hash recomputed is accepted. Results therefore name the digest as the record's own claim.

The tables are append-only. Each release that changes a bound file appends the digest it replaces, with its
per-file values; a test pins every entry so none changes silently. The first entry is the digest the P3a fixtures
recorded (plugin_tests/fixtures/pre_pin_migration), with the per-file values of the commit that produced it.
"""
from __future__ import annotations

import re

from .io import digest

SAME = 'same'
KNOWN_EARLIER = 'known_earlier'
UNKNOWN = 'unknown'

# The files protected._bindings digests, in its order.
PROTECTED_COMPONENTS = ('protected.py', 'execution.py', 'io.py', 'native_pins.py')
# The files journey_native_atmos._implementation records.
NATIVE_ATMOS_COMPONENTS = ('journey_native_atmos.py', 'native_atmos.py', 'repository.py',
                           'protected.py', 'io.py', 'native_pins.py')

# Append only. Never edit or remove an entry: a record made under it would stop reading as history.
PROTECTED_INVENTORY = (
    {'label': 'ce27913-pre-pin-migration',
     'implementation_sha256': 'c3ebd0c1c769e4d500406abb9b5b8ba716cea6f6da7108b8fec901daa875dc9c',
     'files': {'protected.py': '79e167f7f4fdb1246f07a2589256890552b07480fba5bedce28f7c9f64dc1c43',
               'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc'}},
)

NATIVE_ATMOS_INVENTORY = (
    {'label': 'ce27913-pre-pin-migration',
     'files': {'journey_native_atmos.py': 'f07515ca633659dc94cee515829cb71e3f5ffee27120ca9b527bfefa6d21bbe9',
               'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
               'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
               'protected.py': '79e167f7f4fdb1246f07a2589256890552b07480fba5bedce28f7c9f64dc1c43',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc'}},
)

_HEX = re.compile(r'[0-9a-f]{64}\Z')
RECOGNITION_LIMIT = ('Recognition is not authentication: the inventory rejects a digest it does not know, but it cannot '
                     'show which recognised implementation produced a record. Local evidence is cooperative.')
RECORD_CLAIM = 'the digest is the record\'s own claim; it was not verified against the implementation that wrote it'


def protected_digest(files):
    """The combined value protected._bindings records for a per-file mapping."""
    return digest([files[name] for name in PROTECTED_COMPONENTS])


def _result(inventory, components, relation, label, recorded, current):
    return {'relation': relation, 'inventory': inventory, 'inventory_label': label,
            'recorded_implementation_sha256': recorded, 'current_implementation_sha256': current,
            'bound_components': list(components), 'recorded_implementation_basis': RECORD_CLAIM,
            'recognition_limit': RECOGNITION_LIMIT}


def protected_relation(recorded_sha256, current_sha256):
    """Relation of a protected request's recorded implementation digest to the current one.

    same: they are equal. known_earlier: the recorded digest is in PROTECTED_INVENTORY. unknown: neither, or not a
    digest at all.
    """
    valid = type(recorded_sha256) is str and bool(_HEX.match(recorded_sha256))
    if valid and recorded_sha256 == current_sha256:
        relation, label = SAME, None
    else:
        entry = next((e for e in PROTECTED_INVENTORY if valid and e['implementation_sha256'] == recorded_sha256), None)
        relation, label = (KNOWN_EARLIER, entry['label']) if entry else (UNKNOWN, None)
    return _result('protected_operation', PROTECTED_COMPONENTS, relation, label,
                   recorded_sha256 if valid else None, current_sha256)


def native_atmos_relation(recorded_files, current_files):
    """Relation of a native Atmos receipt's recorded file inventory to the current one (the digest of the mapping)."""
    valid = (type(recorded_files) is dict and set(recorded_files) == set(NATIVE_ATMOS_COMPONENTS)
             and all(type(v) is str and _HEX.match(v) for v in recorded_files.values()))
    if valid and recorded_files == current_files:
        relation, label = SAME, None
    else:
        entry = next((e for e in NATIVE_ATMOS_INVENTORY if valid and e['files'] == recorded_files), None)
        relation, label = (KNOWN_EARLIER, entry['label']) if entry else (UNKNOWN, None)
    return _result('native_atmos', NATIVE_ATMOS_COMPONENTS, relation, label,
                   digest(recorded_files) if valid else None,
                   digest(current_files) if type(current_files) is dict else None)
