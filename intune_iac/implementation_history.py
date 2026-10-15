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
    {'label': 'pin-migration-p3b',
     'implementation_sha256': 'c22f9086f4c9e3d00c83193703f74e78fe60054ac4b0051b2de00f2d4ec73798',
     'files': {'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636',
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
    {'label': 'pin-migration-p3b',
     'files': {'journey_native_atmos.py': '35d09602c49cb09b518643485c76f5dca75272da3ee5f95a57c8f1e6e57ea2ff',
               'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
               'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
               'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc'}},
)

# The files protected_worker._implementation records in a job manifest, in its order (it reads this list). The first
# nine were the whole set until the approval judgment moved into validity.py, which relies on the recorded time in
# clock.py: both are bound now, so a changed judgment changes the digest and the execution gate refuses. Entries
# registered before that carry the nine; they stay readable as history (see _file_set_relation).
WORKER_COMPONENTS_EARLIER = ('protected_worker.py', 'protected.py', 'provider_execution.py', 'approval_authority.py',
                             'provider_journey.py', 'azure_backend.py', 'execution.py', 'io.py', 'native_pins.py')
WORKER_COMPONENTS = WORKER_COMPONENTS_EARLIER + ('validity.py', 'clock.py')

WORKER_INVENTORY = (
    {'label': 'ce27913-pre-pin-migration',
     'files': {'protected_worker.py': '1a2a0e48b84b8b30980cb9c743bb82835dfe59945edb857f8eb4c43c4045dc1b',
               'protected.py': '79e167f7f4fdb1246f07a2589256890552b07480fba5bedce28f7c9f64dc1c43',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': '7770a65bf142491768cd74a10871e601ea0ffabeed1afbe21315e1d03fbe7c0e',
               'provider_journey.py': 'ba263a361a70a8c30d5e6d025a06baaa104b77c6b46faaae4220c7579cb9f4b7',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc'}},
    {'label': 'pin-migration-p3b',
     'files': {'protected_worker.py': '7c2e92351298df585748edbc1c0418320a15a19db936b50449d0b29298019a4c',
               'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': '7770a65bf142491768cd74a10871e601ea0ffabeed1afbe21315e1d03fbe7c0e',
               'provider_journey.py': 'ba263a361a70a8c30d5e6d025a06baaa104b77c6b46faaae4220c7579cb9f4b7',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc'}},
    {'label': 'authz-expiry-latch',
     'files': {'protected_worker.py': '7c2e92351298df585748edbc1c0418320a15a19db936b50449d0b29298019a4c',
               'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': '95effe8f97cfc0f600d5a2f54a76216110cf563276e88b657659c15d665061b8',
               'provider_journey.py': 'ba263a361a70a8c30d5e6d025a06baaa104b77c6b46faaae4220c7579cb9f4b7',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc'}},
    {'label': 'authz-expiry-latch-r2',
     'files': {'protected_worker.py': '7c2e92351298df585748edbc1c0418320a15a19db936b50449d0b29298019a4c',
               'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': 'bf29d3bbbc035c1a713d7c682164ab22e648fcb30a461f789bdaf00828616660',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc'}},
    {'label': 'authz-expiry-latch-r3',
     'files': {'protected_worker.py': '7c2e92351298df585748edbc1c0418320a15a19db936b50449d0b29298019a4c',
               'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': '189da8ac643b188de8e4edc525a14e8bc06dd63a48b3637d70b7cc5d9bb097b0',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc'}},
    {'label': 'adoption-expiry-latch',
     'files': {'protected_worker.py': '7c2e92351298df585748edbc1c0418320a15a19db936b50449d0b29298019a4c',
               'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': 'bc39975ff1bd83cb466e7e0987252c7e60469e09a3d528adc8aeeb6c1a45e7a1',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc'}},
    {'label': 'adoption-expiry-latch-r2',
     'files': {'protected_worker.py': '959564bfe1e8a7724b890c4b932343f2ce9b74e5dde1d817d5121c59af065b21',
               'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': 'bc39975ff1bd83cb466e7e0987252c7e60469e09a3d528adc8aeeb6c1a45e7a1',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'validity.py': '29897140f49ad33e1c687aa22771d2f73bc667b472078b8910a1f530e9076b89',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
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


def _file_set_relation(name, components, inventory, recorded_files, current_files):
    # A record names the file set of the release that made it: the current set, or the set an inventory entry carries
    # (an entry is never rewritten, so a release made before the set grew keeps its own).
    sets = [set(components)] + [set(entry['files']) for entry in inventory]
    valid = (type(recorded_files) is dict and set(recorded_files) in sets
             and all(type(v) is str and _HEX.match(v) for v in recorded_files.values()))
    if valid and recorded_files == current_files:
        relation, label = SAME, None
    else:
        entry = next((e for e in inventory if valid and e['files'] == recorded_files), None)
        relation, label = (KNOWN_EARLIER, entry['label']) if entry else (UNKNOWN, None)
    return _result(name, components, relation, label,
                   digest(recorded_files) if valid else None,
                   digest(current_files) if type(current_files) is dict else None)


def native_atmos_relation(recorded_files, current_files):
    """Relation of a native Atmos receipt's recorded file inventory to the current one (the digest of the mapping)."""
    return _file_set_relation('native_atmos', NATIVE_ATMOS_COMPONENTS, NATIVE_ATMOS_INVENTORY, recorded_files, current_files)


def worker_relation(recorded_files, current_files):
    """Relation of a worker job's recorded implementation file set to the current one. A job may be read as history
    only under a released worker implementation registered in WORKER_INVENTORY."""
    return _file_set_relation('worker', WORKER_COMPONENTS, WORKER_INVENTORY, recorded_files, current_files)
