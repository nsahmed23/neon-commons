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

# The file sets of earlier releases only. The CURRENT set of each implementation digest is owned by the module that is
# bound by it (protected.PROTECTED_COMPONENTS, protected_worker.WORKER_COMPONENTS, journey_native_atmos.
# NATIVE_ATMOS_COMPONENTS): this module is not itself bound by any digest, so it must not be able to say what is bound.
# Entries registered before clock.py (protected, native Atmos) or validity.py and clock.py (worker) were bound carry the
# earlier sets below, and stay readable as history.
PROTECTED_COMPONENTS_EARLIER = ('protected.py', 'execution.py', 'io.py', 'native_pins.py')
NATIVE_ATMOS_COMPONENTS_EARLIER = ('journey_native_atmos.py', 'native_atmos.py', 'repository.py',
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
    {'label': 'clock-bound',
     'implementation_sha256': '34918858c5211a7af70e02ce0bffe6471e693464d81f44e9d32c4216fbdf5dce',
     'files': {'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636',
               'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'components-owned-by-consumers',
     'implementation_sha256': 'f0043f3b6e5911420224d350fd66089363aca5894eaf3fbb7d97d95846f8045d',
     'files': {'protected.py': '188e226067ecc86ffb45158ecc0463127dda533c3dc5f7af829d84c46f0454c5',
               'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'pin-migration-p3d',
     'implementation_sha256': '066af133912c017d8bcf0eac0f9af5ad760d657516e903b2771f95f07fe6d803',
     'files': {'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'census-released-task',
     'implementation_sha256': '94adb94dcef11d6172cc6faf6780d96aaeaef7e7db87f9fafdf3981fc3501ebf',
     'files': {'protected.py': 'd8c7e9b317b7391abfe31a3a0ba4ab1557eff72285c22ceaed2e63f6ce59424c',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'census-transitional-task',
     'implementation_sha256': '8fe205043818895050a1ff13b45c1515c9deec959d534cacae4c51dc4d95f78d',
     'files': {'protected.py': '29dc883cda8124d21c778f23c6187ee3fce35fc9692c676c0fc943fbdcdb477b',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'boot-session-anchor',
     'implementation_sha256': 'cfd572ab6a29293e0e955f2ac4570263e54e67906ea65d3301504b16aeb03995',
     'files': {'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8'}},
    {'label': 'integration-authz-c-on-census',
     'implementation_sha256': 'd26b4227f0d4239d4245ca1676855889df9b3b9b46a6083e479638c7991d65e4',
     'files': {'protected.py': '29dc883cda8124d21c778f23c6187ee3fce35fc9692c676c0fc943fbdcdb477b',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8'}},
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
    {'label': 'clock-bound',
     'files': {'journey_native_atmos.py': 'd31602b0aec59169346ea208a1da5069a0a2aaf98ce6c64583fbc731b77b1cdc',
               'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
               'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
               'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'components-owned-by-consumers',
     'files': {'journey_native_atmos.py': '92a3afbdb3a0867d1aba6e8a6eeefdfb83a3beeea00db755a7566d484bfcdec0',
               'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
               'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
               'protected.py': '188e226067ecc86ffb45158ecc0463127dda533c3dc5f7af829d84c46f0454c5',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'pin-migration-p3d',
     'files': {'journey_native_atmos.py': '92a3afbdb3a0867d1aba6e8a6eeefdfb83a3beeea00db755a7566d484bfcdec0',
               'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
               'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
               'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'census-released-task',
     'files': {'journey_native_atmos.py': '92a3afbdb3a0867d1aba6e8a6eeefdfb83a3beeea00db755a7566d484bfcdec0',
               'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
               'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
               'protected.py': 'd8c7e9b317b7391abfe31a3a0ba4ab1557eff72285c22ceaed2e63f6ce59424c',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'census-transitional-task',
     'files': {'journey_native_atmos.py': '92a3afbdb3a0867d1aba6e8a6eeefdfb83a3beeea00db755a7566d484bfcdec0',
               'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
               'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
               'protected.py': '29dc883cda8124d21c778f23c6187ee3fce35fc9692c676c0fc943fbdcdb477b',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'boot-session-anchor',
     'files': {'journey_native_atmos.py': '92a3afbdb3a0867d1aba6e8a6eeefdfb83a3beeea00db755a7566d484bfcdec0',
               'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
               'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
               'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8'}},
    {'label': 'integration-authz-c-on-census',
     'files': {'journey_native_atmos.py': '92a3afbdb3a0867d1aba6e8a6eeefdfb83a3beeea00db755a7566d484bfcdec0',
               'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
               'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
               'protected.py': '29dc883cda8124d21c778f23c6187ee3fce35fc9692c676c0fc943fbdcdb477b',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8'}},
)

# The nine files protected_worker._implementation recorded in a job manifest until validity.py and clock.py were bound.
WORKER_COMPONENTS_EARLIER = ('protected_worker.py', 'protected.py', 'provider_execution.py', 'approval_authority.py',
                             'provider_journey.py', 'azure_backend.py', 'execution.py', 'io.py', 'native_pins.py')

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
    {'label': 'adoption-expiry-latch-r3',
     'files': {'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
               'protected.py': '188e226067ecc86ffb45158ecc0463127dda533c3dc5f7af829d84c46f0454c5',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': 'bc39975ff1bd83cb466e7e0987252c7e60469e09a3d528adc8aeeb6c1a45e7a1',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'validity.py': 'd7bafb7503c3ac00d8232ec3308565d26d6eb0470e62e9a4804de54250917f68',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'pin-migration-p3d',
     'files': {'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
               'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': 'bc39975ff1bd83cb466e7e0987252c7e60469e09a3d528adc8aeeb6c1a45e7a1',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'validity.py': 'd7bafb7503c3ac00d8232ec3308565d26d6eb0470e62e9a4804de54250917f68',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'census-released-task',
     'files': {'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
               'protected.py': 'd8c7e9b317b7391abfe31a3a0ba4ab1557eff72285c22ceaed2e63f6ce59424c',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': 'bc39975ff1bd83cb466e7e0987252c7e60469e09a3d528adc8aeeb6c1a45e7a1',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'validity.py': 'd7bafb7503c3ac00d8232ec3308565d26d6eb0470e62e9a4804de54250917f68',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'census-transitional-task',
     'files': {'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
               'protected.py': '29dc883cda8124d21c778f23c6187ee3fce35fc9692c676c0fc943fbdcdb477b',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': 'bc39975ff1bd83cb466e7e0987252c7e60469e09a3d528adc8aeeb6c1a45e7a1',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'validity.py': 'd7bafb7503c3ac00d8232ec3308565d26d6eb0470e62e9a4804de54250917f68',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'authz-c-exact-artifact-key',
     'files': {'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
               'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': '97d13b0d57b7679b50425c44f2d14562324070f4dff9b2807d591db0ef1a4960',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'validity.py': '0e56c680c28414520d5fecf0f0645b5a436f4eb7360e112e24a3b7a4046b68b8',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'authz-c-legacy-expiry-rows-kept',
     'files': {'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
               'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': '97d13b0d57b7679b50425c44f2d14562324070f4dff9b2807d591db0ef1a4960',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'validity.py': '6e6b1c17da420006584bdde1cea72b751ab7a473c8eafa3ea7b717fe62299112',
               'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'}},
    {'label': 'boot-session-anchor',
     'files': {'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
               'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': '97d13b0d57b7679b50425c44f2d14562324070f4dff9b2807d591db0ef1a4960',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'validity.py': 'c7fa43eb1e90d441f790a8f7c8fa8dedd84885b1adee4e7ab510e4ffb7ed8e20',
               'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8'}},
    {'label': 'migration-cutoff',
     'files': {'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
               'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': '97d13b0d57b7679b50425c44f2d14562324070f4dff9b2807d591db0ef1a4960',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'validity.py': 'b58ea8a6c73e14542d86243a34668b89a9b7432e9fe105136b9522dc3925a341',
               'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8'}},
    {'label': 'migration-cutoff-boundary',
     'files': {'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
               'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': '97d13b0d57b7679b50425c44f2d14562324070f4dff9b2807d591db0ef1a4960',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'validity.py': '695df1d0c14273da219f67b1787e68029ce6e5939be2dc02955b7d2145f99525',
               'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8'}},
    {'label': 'integration-authz-c-on-census',
     'files': {'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
               'protected.py': '29dc883cda8124d21c778f23c6187ee3fce35fc9692c676c0fc943fbdcdb477b',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': '97d13b0d57b7679b50425c44f2d14562324070f4dff9b2807d591db0ef1a4960',
               'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'validity.py': '695df1d0c14273da219f67b1787e68029ce6e5939be2dc02955b7d2145f99525',
               'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8'}},
    {'label': 'setup-3-credential-descriptors',
     'files': {'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
               'protected.py': '29dc883cda8124d21c778f23c6187ee3fce35fc9692c676c0fc943fbdcdb477b',
               'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
               'approval_authority.py': '97d13b0d57b7679b50425c44f2d14562324070f4dff9b2807d591db0ef1a4960',
               'provider_journey.py': '6de3a3a6e9de2eab56a3e80e06551045b15eafae22b161e0362c6c1bc1ac4acc',
               'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
               'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
               'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
               'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
               'validity.py': '695df1d0c14273da219f67b1787e68029ce6e5939be2dc02955b7d2145f99525',
               'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8'}},
)

_HEX = re.compile(r'[0-9a-f]{64}\Z')
RECOGNITION_LIMIT = ('Recognition is not authentication: the inventory rejects a digest it does not know, but it cannot '
                     'show which recognised implementation produced a record. Local evidence is cooperative.')
RECORD_CLAIM = 'the digest is the record\'s own claim; it was not verified against the implementation that wrote it'


def protected_digest(files):
    """The combined value protected records for a per-file mapping, in the mapping's own order (protected owns the current
    order; an inventory entry carries the order of its release). Used for the inventory's historical digests."""
    return digest([files[name] for name in files])


def _result(inventory, components, relation, label, recorded, current):  # components: the consumer's current set
    return {'relation': relation, 'inventory': inventory, 'inventory_label': label,
            'recorded_implementation_sha256': recorded, 'current_implementation_sha256': current,
            'bound_components': list(components), 'recorded_implementation_basis': RECORD_CLAIM,
            'recognition_limit': RECOGNITION_LIMIT}


def protected_relation(recorded_sha256, current_sha256, components=()):
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
    return _result('protected_operation', components, relation, label,
                   recorded_sha256 if valid else None, current_sha256)


def _file_set_relation(name, inventory, recorded_files, current_files):
    # A record names the file set of the release that made it: the current set, or the set an inventory entry carries
    # (an entry is never rewritten, so a release made before the set grew keeps its own).
    components = list(current_files) if type(current_files) is dict else []  # the consumer's own current set
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
    return _file_set_relation('native_atmos', NATIVE_ATMOS_INVENTORY, recorded_files, current_files)


def worker_relation(recorded_files, current_files):
    """Relation of a worker job's recorded implementation file set to the current one. A job may be read as history
    only under a released worker implementation registered in WORKER_INVENTORY."""
    return _file_set_relation('worker', WORKER_INVENTORY, recorded_files, current_files)
