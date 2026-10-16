"""The inventory of released implementation digests (intune_iac/implementation_history.py).

The table is append-only and consulted only when a record is read as history. These tests pin every entry so that it
cannot change silently, tie the first entry to the digest the P3a fixtures froze (read from the frozen files, never
computed from current code), and check the three relations.
"""
import json
import unittest
from pathlib import Path

from intune_iac import implementation_history as history
from intune_iac.io import digest

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'pre_pin_migration'
JOURNEY = FIXTURES / 'journey/session.json.journey'
OPERATION = 'operations/d65bd73123014765922143bd45956e76/00.json'

FROZEN_DIGEST = 'c3ebd0c1c769e4d500406abb9b5b8ba716cea6f6da7108b8fec901daa875dc9c'
FROZEN_PROTECTED_FILES = {
    'protected.py': '79e167f7f4fdb1246f07a2589256890552b07480fba5bedce28f7c9f64dc1c43',
    'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
}
FROZEN_ATMOS_FILES = {
    'journey_native_atmos.py': 'f07515ca633659dc94cee515829cb71e3f5ffee27120ca9b527bfefa6d21bbe9',
    'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
    'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
    'protected.py': '79e167f7f4fdb1246f07a2589256890552b07480fba5bedce28f7c9f64dc1c43',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
}
FROZEN_WORKER_FILES = {
    'protected_worker.py': '1a2a0e48b84b8b30980cb9c743bb82835dfe59945edb857f8eb4c43c4045dc1b',
    'protected.py': '79e167f7f4fdb1246f07a2589256890552b07480fba5bedce28f7c9f64dc1c43',
    'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
    'approval_authority.py': '7770a65bf142491768cd74a10871e601ea0ffabeed1afbe21315e1d03fbe7c0e',
    'provider_journey.py': 'ba263a361a70a8c30d5e6d025a06baaa104b77c6b46faaae4220c7579cb9f4b7',
    'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
    'execution.py': '642a182551839da471a1e3ac3d60b4fde666637cfcf851013ea2f5d5e81e2e72',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
}
LABEL = 'ce27913-pre-pin-migration'
P3B_LABEL = 'pin-migration-p3b'
P3B_DIGEST = 'c22f9086f4c9e3d00c83193703f74e78fe60054ac4b0051b2de00f2d4ec73798'
P3B_PROTECTED_FILES = dict(FROZEN_PROTECTED_FILES, **{'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636'})
P3B_ATMOS_FILES = dict(FROZEN_ATMOS_FILES, **{
    'journey_native_atmos.py': '35d09602c49cb09b518643485c76f5dca75272da3ee5f95a57c8f1e6e57ea2ff',
    'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636'})
P3B_WORKER_FILES = dict(FROZEN_WORKER_FILES, **{
    'protected_worker.py': '7c2e92351298df585748edbc1c0418320a15a19db936b50449d0b29298019a4c',
    'protected.py': '3f1fc433999ad7606866f3587c39e0c1d7d9ffcc3b62831cd24fb670660c7636'})
AUTHZ_LABEL = 'authz-expiry-latch'
AUTHZ_WORKER_FILES = dict(P3B_WORKER_FILES, **{
    'approval_authority.py': '95effe8f97cfc0f600d5a2f54a76216110cf563276e88b657659c15d665061b8'})
AUTHZ_R2_LABEL = 'authz-expiry-latch-r2'
AUTHZ_R2_WORKER_FILES = dict(AUTHZ_WORKER_FILES, **{
    'approval_authority.py': 'bf29d3bbbc035c1a713d7c682164ab22e648fcb30a461f789bdaf00828616660',
    'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371'})
AUTHZ_R3_LABEL = 'authz-expiry-latch-r3'
AUTHZ_R3_WORKER_FILES = dict(AUTHZ_R2_WORKER_FILES, **{
    'approval_authority.py': '189da8ac643b188de8e4edc525a14e8bc06dd63a48b3637d70b7cc5d9bb097b0'})
CLOCK_LABEL = 'clock-bound'
CLOCK_DIGEST = '34918858c5211a7af70e02ce0bffe6471e693464d81f44e9d32c4216fbdf5dce'
CLOCK_PROTECTED_FILES = dict(P3B_PROTECTED_FILES, **{
    'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'})
CLOCK_ATMOS_FILES = dict(P3B_ATMOS_FILES, **{
    'journey_native_atmos.py': 'd31602b0aec59169346ea208a1da5069a0a2aaf98ce6c64583fbc731b77b1cdc',
    'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'})
ADOPTION_LATCH_R2_LABEL = 'adoption-expiry-latch-r2'
ADOPTION_LATCH_R2_WORKER_FILES = dict(AUTHZ_R3_WORKER_FILES, **{
    'protected_worker.py': '959564bfe1e8a7724b890c4b932343f2ce9b74e5dde1d817d5121c59af065b21',
    'approval_authority.py': 'bc39975ff1bd83cb466e7e0987252c7e60469e09a3d528adc8aeeb6c1a45e7a1',
    'validity.py': '29897140f49ad33e1c687aa22771d2f73bc667b472078b8910a1f530e9076b89',
    'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c'})
ADOPTION_LATCH_LABEL = 'adoption-expiry-latch'
ADOPTION_LATCH_WORKER_FILES = dict(AUTHZ_R3_WORKER_FILES, **{
    'approval_authority.py': 'bc39975ff1bd83cb466e7e0987252c7e60469e09a3d528adc8aeeb6c1a45e7a1'})

OWNED_LABEL = 'components-owned-by-consumers'
OWNED_DIGEST = 'f0043f3b6e5911420224d350fd66089363aca5894eaf3fbb7d97d95846f8045d'
OWNED_PROTECTED_FILES = dict(CLOCK_PROTECTED_FILES, **{
    'protected.py': '188e226067ecc86ffb45158ecc0463127dda533c3dc5f7af829d84c46f0454c5'})
OWNED_ATMOS_FILES = dict(CLOCK_ATMOS_FILES, **{
    'journey_native_atmos.py': '92a3afbdb3a0867d1aba6e8a6eeefdfb83a3beeea00db755a7566d484bfcdec0',
    'protected.py': '188e226067ecc86ffb45158ecc0463127dda533c3dc5f7af829d84c46f0454c5'})
ADOPTION_LATCH_R3_LABEL = 'adoption-expiry-latch-r3'
ADOPTION_LATCH_R3_WORKER_FILES = dict(ADOPTION_LATCH_R2_WORKER_FILES, **{
    'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
    'protected.py': '188e226067ecc86ffb45158ecc0463127dda533c3dc5f7af829d84c46f0454c5',
    'validity.py': 'd7bafb7503c3ac00d8232ec3308565d26d6eb0470e62e9a4804de54250917f68'})

P3D_LABEL = 'pin-migration-p3d'
P3D_DIGEST = '066af133912c017d8bcf0eac0f9af5ad760d657516e903b2771f95f07fe6d803'
P3D_PROTECTED_FILES = {
    'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
    'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c',
}
P3D_ATMOS_FILES = {
    'journey_native_atmos.py': '92a3afbdb3a0867d1aba6e8a6eeefdfb83a3beeea00db755a7566d484bfcdec0',
    'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
    'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
    'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c',
}
P3D_WORKER_FILES = {
    'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
    'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
    'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
    'approval_authority.py': 'bc39975ff1bd83cb466e7e0987252c7e60469e09a3d528adc8aeeb6c1a45e7a1',
    'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
    'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
    'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'validity.py': 'd7bafb7503c3ac00d8232ec3308565d26d6eb0470e62e9a4804de54250917f68',
    'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c',
}

CENSUS_LABEL = 'census-released-task'
CENSUS_DIGEST = '94adb94dcef11d6172cc6faf6780d96aaeaef7e7db87f9fafdf3981fc3501ebf'
CENSUS_PROTECTED_FILES = {
    'protected.py': 'd8c7e9b317b7391abfe31a3a0ba4ab1557eff72285c22ceaed2e63f6ce59424c',
    'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c',
}

CENSUS_ATMOS_FILES = {
    'journey_native_atmos.py': '92a3afbdb3a0867d1aba6e8a6eeefdfb83a3beeea00db755a7566d484bfcdec0',
    'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
    'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
    'protected.py': 'd8c7e9b317b7391abfe31a3a0ba4ab1557eff72285c22ceaed2e63f6ce59424c',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c',
}

CENSUS_WORKER_FILES = {
    'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
    'protected.py': 'd8c7e9b317b7391abfe31a3a0ba4ab1557eff72285c22ceaed2e63f6ce59424c',
    'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
    'approval_authority.py': 'bc39975ff1bd83cb466e7e0987252c7e60469e09a3d528adc8aeeb6c1a45e7a1',
    'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
    'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
    'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'validity.py': 'd7bafb7503c3ac00d8232ec3308565d26d6eb0470e62e9a4804de54250917f68',
    'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c',
}

TRANSITIONAL_LABEL = 'census-transitional-task'
TRANSITIONAL_DIGEST = '8fe205043818895050a1ff13b45c1515c9deec959d534cacae4c51dc4d95f78d'
TRANSITIONAL_PROTECTED_FILES = {
    'protected.py': '29dc883cda8124d21c778f23c6187ee3fce35fc9692c676c0fc943fbdcdb477b',
    'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c',
}

TRANSITIONAL_ATMOS_FILES = {
    'journey_native_atmos.py': '92a3afbdb3a0867d1aba6e8a6eeefdfb83a3beeea00db755a7566d484bfcdec0',
    'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
    'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
    'protected.py': '29dc883cda8124d21c778f23c6187ee3fce35fc9692c676c0fc943fbdcdb477b',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c',
}

TRANSITIONAL_WORKER_FILES = {
    'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
    'protected.py': '29dc883cda8124d21c778f23c6187ee3fce35fc9692c676c0fc943fbdcdb477b',
    'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
    'approval_authority.py': 'bc39975ff1bd83cb466e7e0987252c7e60469e09a3d528adc8aeeb6c1a45e7a1',
    'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
    'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
    'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'validity.py': 'd7bafb7503c3ac00d8232ec3308565d26d6eb0470e62e9a4804de54250917f68',
    'clock.py': 'd7e379c4f226dd08a62212cf7dd492bbe7405cd9425723d399540687d8773d3c',
}
AUTHZ_C2_LABEL = 'authz-c-legacy-expiry-rows-kept'
AUTHZ_C2_WORKER_FILES = dict(P3D_WORKER_FILES, **{
    'approval_authority.py': '97d13b0d57b7679b50425c44f2d14562324070f4dff9b2807d591db0ef1a4960',
    'validity.py': '6e6b1c17da420006584bdde1cea72b751ab7a473c8eafa3ea7b717fe62299112'})
AUTHZ_C_LABEL = 'authz-c-exact-artifact-key'
AUTHZ_C_WORKER_FILES = dict(P3D_WORKER_FILES, **{
    'approval_authority.py': '97d13b0d57b7679b50425c44f2d14562324070f4dff9b2807d591db0ef1a4960',
    'validity.py': '0e56c680c28414520d5fecf0f0645b5a436f4eb7360e112e24a3b7a4046b68b8'})


def frozen_digests():
    """Every implementation digest the P3a fixtures recorded, read from the frozen files."""
    found = set()
    for name in ('native-request.json', 'synthetic-executor/preparation.json', OPERATION):
        document = json.loads((JOURNEY / name).read_text())
        request = document['payload']['request'] if name == OPERATION else document
        found.add(request['bindings']['implementation_sha256'])
    return found

BOOT_LABEL = 'boot-session-anchor'
BOOT_DIGEST = 'cfd572ab6a29293e0e955f2ac4570263e54e67906ea65d3301504b16aeb03995'
BOOT_PROTECTED_FILES = {
    'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
    'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8',
}
BOOT_ATMOS_FILES = {
    'journey_native_atmos.py': '92a3afbdb3a0867d1aba6e8a6eeefdfb83a3beeea00db755a7566d484bfcdec0',
    'native_atmos.py': '77da0489216ac52e99d0ed2f3a677eec944b4e7c8f7d45a91cae2e282368d62a',
    'repository.py': '6c444bb93076dac5f31deb249c2b15fe174e5e310d780406ed293d994ba2027a',
    'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8',
}
BOOT_WORKER_FILES = {
    'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
    'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
    'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
    'approval_authority.py': '97d13b0d57b7679b50425c44f2d14562324070f4dff9b2807d591db0ef1a4960',
    'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
    'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
    'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'validity.py': 'c7fa43eb1e90d441f790a8f7c8fa8dedd84885b1adee4e7ab510e4ffb7ed8e20',
    'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8',
}
CUTOFF_LABEL = 'migration-cutoff'
CUTOFF_WORKER_FILES = {
    'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
    'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
    'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
    'approval_authority.py': '97d13b0d57b7679b50425c44f2d14562324070f4dff9b2807d591db0ef1a4960',
    'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
    'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
    'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'validity.py': 'b58ea8a6c73e14542d86243a34668b89a9b7432e9fe105136b9522dc3925a341',
    'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8',
}
CUTOFF2_LABEL = 'migration-cutoff-boundary'
CUTOFF2_WORKER_FILES = {
    'protected_worker.py': '191c0c7549c8fcd1b9cfa2ff43311bdc23282f9e3d357602268a113f170d5299',
    'protected.py': '186ee85bc5228f71360477442207bf4bb0591ca2338e6b38dd3177b368412e14',
    'provider_execution.py': '653e4191156444fd05a0937c8c3a5f5a6c6097fa07e9cb5f34a1278cdb2a7731',
    'approval_authority.py': '97d13b0d57b7679b50425c44f2d14562324070f4dff9b2807d591db0ef1a4960',
    'provider_journey.py': 'dfba89eaf20dfa42c423fcecc2f8fea6bf75d9f2e50ee24d05996307efa9c371',
    'azure_backend.py': '83c6079140bc1740d0ac8d2d4773a07faa2046de93f4b84a79cd23712e597eab',
    'execution.py': 'd77a3c1519621bcc04c74034d4cfb55c4e0b5fadde74e50980c36b1d520feadd',
    'io.py': '8ae9ba7696521e4c608f39ba90bedb98d2a9f2bdd614d279a001c793c2b17fe4',
    'native_pins.py': '0047f15debc49c0e2e7660521b22fed4568eb93015c2e2fef107ba62635a9cbc',
    'validity.py': '695df1d0c14273da219f67b1787e68029ce6e5939be2dc02955b7d2145f99525',
    'clock.py': '49bd3d46c5ffcc554cbcc157a70a27504046807b940836844d16069b79e0e4c8',
}

class InventoryPinTests(unittest.TestCase):
    """Appending an entry is a deliberate release act that updates these literals; nothing else may change."""

    def test_protected_inventory_holds_exactly_the_pinned_entries(self):
        self.assertEqual(
            [dict(entry) for entry in history.PROTECTED_INVENTORY],
            [{'label': LABEL, 'implementation_sha256': FROZEN_DIGEST, 'files': FROZEN_PROTECTED_FILES},
             {'label': P3B_LABEL, 'implementation_sha256': P3B_DIGEST, 'files': P3B_PROTECTED_FILES},
             {'label': CLOCK_LABEL, 'implementation_sha256': CLOCK_DIGEST, 'files': CLOCK_PROTECTED_FILES},
             {'label': OWNED_LABEL, 'implementation_sha256': OWNED_DIGEST, 'files': OWNED_PROTECTED_FILES},
             {'label': P3D_LABEL, 'implementation_sha256': P3D_DIGEST, 'files': P3D_PROTECTED_FILES},
             {'label': CENSUS_LABEL, 'implementation_sha256': CENSUS_DIGEST, 'files': CENSUS_PROTECTED_FILES},
             {'label': TRANSITIONAL_LABEL, 'implementation_sha256': TRANSITIONAL_DIGEST, 'files': TRANSITIONAL_PROTECTED_FILES},
             {'label': BOOT_LABEL, 'implementation_sha256': BOOT_DIGEST, 'files': BOOT_PROTECTED_FILES}])

    def test_native_atmos_inventory_holds_exactly_the_pinned_entries(self):
        self.assertEqual(
            [dict(entry) for entry in history.NATIVE_ATMOS_INVENTORY],
            [{'label': LABEL, 'files': FROZEN_ATMOS_FILES}, {'label': P3B_LABEL, 'files': P3B_ATMOS_FILES},
             {'label': CLOCK_LABEL, 'files': CLOCK_ATMOS_FILES},
             {'label': OWNED_LABEL, 'files': OWNED_ATMOS_FILES}, {'label': P3D_LABEL, 'files': P3D_ATMOS_FILES},
             {'label': CENSUS_LABEL, 'files': CENSUS_ATMOS_FILES},
             {'label': TRANSITIONAL_LABEL, 'files': TRANSITIONAL_ATMOS_FILES},
             {'label': BOOT_LABEL, 'files': BOOT_ATMOS_FILES}])

    def test_worker_inventory_holds_exactly_the_pinned_entries(self):
        self.assertEqual(
            [dict(entry) for entry in history.WORKER_INVENTORY],
            [{'label': LABEL, 'files': FROZEN_WORKER_FILES}, {'label': P3B_LABEL, 'files': P3B_WORKER_FILES},
             {'label': AUTHZ_LABEL, 'files': AUTHZ_WORKER_FILES},
             {'label': AUTHZ_R2_LABEL, 'files': AUTHZ_R2_WORKER_FILES},
             {'label': AUTHZ_R3_LABEL, 'files': AUTHZ_R3_WORKER_FILES},
             {'label': ADOPTION_LATCH_LABEL, 'files': ADOPTION_LATCH_WORKER_FILES},
             {'label': ADOPTION_LATCH_R2_LABEL, 'files': ADOPTION_LATCH_R2_WORKER_FILES},
             {'label': ADOPTION_LATCH_R3_LABEL, 'files': ADOPTION_LATCH_R3_WORKER_FILES},
             {'label': P3D_LABEL, 'files': P3D_WORKER_FILES},
             {'label': CENSUS_LABEL, 'files': CENSUS_WORKER_FILES},
             {'label': TRANSITIONAL_LABEL, 'files': TRANSITIONAL_WORKER_FILES},
             {'label': AUTHZ_C_LABEL, 'files': AUTHZ_C_WORKER_FILES},
             {'label': AUTHZ_C2_LABEL, 'files': AUTHZ_C2_WORKER_FILES},
             {'label': BOOT_LABEL, 'files': BOOT_WORKER_FILES},
             {'label': CUTOFF_LABEL, 'files': CUTOFF_WORKER_FILES},
             {'label': CUTOFF2_LABEL, 'files': CUTOFF2_WORKER_FILES}])

    def test_each_entry_names_only_its_own_component_set(self):
        # An entry carries the file set of its own release: the earlier set until clock.py was bound, the current set
        # since. No entry is ever rewritten, so earlier ones keep the earlier set.
        from intune_iac import journey_native_atmos, protected
        for inventory, earlier, components in (
                (history.PROTECTED_INVENTORY, history.PROTECTED_COMPONENTS_EARLIER, protected.PROTECTED_COMPONENTS),
                (history.NATIVE_ATMOS_INVENTORY, history.NATIVE_ATMOS_COMPONENTS_EARLIER, journey_native_atmos.NATIVE_ATMOS_COMPONENTS)):
            for entry in inventory:
                self.assertIn(set(entry['files']), (set(earlier), set(components)), entry['label'])
            self.assertEqual(set(inventory[-1]['files']), set(components))
            kinds = [set(entry['files']) == set(components) for entry in inventory]
            self.assertEqual(kinds, sorted(kinds))  # earlier-set entries precede current-set entries, never the reverse
        # A worker entry carries the file set of its own release: the nine files until validity.py and clock.py were
        # bound, the current set (owned by protected_worker) since. No entry is ever rewritten.
        from intune_iac import protected_worker
        sets = (set(history.WORKER_COMPONENTS_EARLIER), set(protected_worker.WORKER_COMPONENTS))
        for entry in history.WORKER_INVENTORY:
            self.assertIn(set(entry['files']), sets, entry['label'])
        self.assertEqual(set(history.WORKER_INVENTORY[-1]['files']), set(protected_worker.WORKER_COMPONENTS))
        kinds = [set(entry['files']) == set(protected_worker.WORKER_COMPONENTS) for entry in history.WORKER_INVENTORY]
        self.assertEqual(kinds, sorted(kinds))  # earlier-set entries precede current-set entries, never the reverse

    def test_component_sets_are_the_bound_file_sets(self):
        self.assertEqual(history.PROTECTED_COMPONENTS_EARLIER, ('protected.py', 'execution.py', 'io.py', 'native_pins.py'))
        from intune_iac import journey_native_atmos, protected
        self.assertEqual(protected.PROTECTED_COMPONENTS, ('protected.py', 'execution.py', 'io.py', 'native_pins.py', 'clock.py'))
        self.assertEqual(history.NATIVE_ATMOS_COMPONENTS_EARLIER, ('journey_native_atmos.py', 'native_atmos.py', 'repository.py',
                                                                  'protected.py', 'io.py', 'native_pins.py'))
        self.assertEqual(journey_native_atmos.NATIVE_ATMOS_COMPONENTS, history.NATIVE_ATMOS_COMPONENTS_EARLIER + ('clock.py',))

    def test_each_protected_entry_digest_is_the_digest_of_its_listed_files(self):
        from intune_iac import protected
        for entry in history.PROTECTED_INVENTORY:
            self.assertIn(set(entry['files']), (set(history.PROTECTED_COMPONENTS_EARLIER), set(protected.PROTECTED_COMPONENTS)),
                          entry['label'])
            self.assertEqual(history.protected_digest(entry['files']), entry['implementation_sha256'], entry['label'])

    def test_labels_and_digests_are_unique(self):
        for inventory in (history.PROTECTED_INVENTORY, history.NATIVE_ATMOS_INVENTORY):
            labels = [entry['label'] for entry in inventory]
            self.assertEqual(len(labels), len(set(labels)))
        digests = [entry['implementation_sha256'] for entry in history.PROTECTED_INVENTORY]
        self.assertEqual(len(digests), len(set(digests)))


class FrozenDigestTests(unittest.TestCase):
    def test_the_fixtures_record_exactly_one_digest_and_it_is_the_first_entry(self):
        found = frozen_digests()
        # Not vacuous: the files were read and held a digest, and it is the pinned one.
        self.assertEqual(found, {FROZEN_DIGEST})
        self.assertEqual(history.PROTECTED_INVENTORY[0]['implementation_sha256'], next(iter(found)))

    def test_lookup_finds_the_frozen_digest_as_known_earlier(self):
        found = frozen_digests()
        self.assertTrue(found)
        for recorded in found:
            result = history.protected_relation(recorded, '0' * 64)
            self.assertEqual(result['relation'], 'known_earlier')
            self.assertEqual(result['inventory_label'], LABEL)
            self.assertEqual(result['recorded_implementation_sha256'], recorded)


class RelationTests(unittest.TestCase):
    def test_same_when_the_record_names_the_current_digest(self):
        result = history.protected_relation('a' * 64, 'a' * 64)
        self.assertEqual((result['relation'], result['inventory_label']), ('same', None))

    def test_same_takes_precedence_over_the_table(self):
        result = history.protected_relation(FROZEN_DIGEST, FROZEN_DIGEST)
        self.assertEqual(result['relation'], 'same')

    def test_unknown_when_neither_current_nor_in_the_table(self):
        result = history.protected_relation('b' * 64, 'a' * 64)
        self.assertEqual((result['relation'], result['inventory_label']), ('unknown', None))

    def test_result_names_both_digests_the_bound_components_and_the_claim(self):
        from intune_iac import protected
        result = history.protected_relation(FROZEN_DIGEST, 'a' * 64, protected.PROTECTED_COMPONENTS)
        self.assertEqual(result['inventory'], 'protected_operation')
        self.assertEqual(result['current_implementation_sha256'], 'a' * 64)
        self.assertEqual(result['bound_components'], list(protected.PROTECTED_COMPONENTS))
        self.assertIn('claim', result['recorded_implementation_basis'])
        self.assertIn('not authentication', result['recognition_limit'])

    def test_malformed_digest_is_unknown_never_an_error_or_a_match(self):
        for value in (None, 7, '', 'A' * 64, FROZEN_DIGEST[:-1], [FROZEN_DIGEST]):
            self.assertEqual(history.protected_relation(value, 'a' * 64)['relation'], 'unknown', value)

    def test_native_atmos_same_known_earlier_and_unknown(self):
        current = dict(FROZEN_ATMOS_FILES, **{'io.py': 'c' * 64})
        self.assertEqual(history.native_atmos_relation(current, current)['relation'], 'same')
        earlier = history.native_atmos_relation(FROZEN_ATMOS_FILES, current)
        self.assertEqual((earlier['relation'], earlier['inventory_label']), ('known_earlier', LABEL))
        self.assertEqual(earlier['recorded_implementation_sha256'], digest(FROZEN_ATMOS_FILES))
        self.assertEqual(earlier['bound_components'], list(current))  # the consumer's own current set
        altered = dict(FROZEN_ATMOS_FILES, **{'io.py': 'd' * 64})
        self.assertEqual(history.native_atmos_relation(altered, current)['relation'], 'unknown')

    def test_native_atmos_malformed_inventory_is_unknown(self):
        current = dict(FROZEN_ATMOS_FILES, **{'io.py': 'c' * 64})
        for value in (None, [], {}, dict(FROZEN_ATMOS_FILES, extra='e' * 64),
                      {k: v for k, v in FROZEN_ATMOS_FILES.items() if k != 'io.py'}):
            self.assertEqual(history.native_atmos_relation(value, current)['relation'], 'unknown', value)


class WorkerInventoryTests(unittest.TestCase):
    def test_worker_component_set_is_the_set_protected_worker_binds(self):
        from intune_iac import protected_worker
        self.assertEqual(protected_worker.WORKER_COMPONENTS, tuple(protected_worker._implementation()))

    def test_first_worker_entry_is_the_pinned_release_and_is_listed_under_the_same_label(self):
        first = dict(history.WORKER_INVENTORY[0])
        self.assertEqual(first, {'label': LABEL, 'files': FROZEN_WORKER_FILES})
        # Its protected.py is the protected inventory's first entry: one release, two views of it.
        self.assertEqual(first['files']['protected.py'], FROZEN_PROTECTED_FILES['protected.py'])

    def test_worker_relation_same_known_earlier_and_unknown(self):
        current = dict(FROZEN_WORKER_FILES, **{'io.py': 'c' * 64})
        self.assertEqual(history.worker_relation(current, current)['relation'], 'same')
        earlier = history.worker_relation(FROZEN_WORKER_FILES, current)
        self.assertEqual((earlier['relation'], earlier['inventory_label']), ('known_earlier', LABEL))
        self.assertEqual(earlier['bound_components'], list(current))  # the consumer's own current set
        drifted = dict(FROZEN_WORKER_FILES, **{'provider_execution.py': 'd' * 64})
        self.assertEqual(history.worker_relation(drifted, current)['relation'], 'unknown')
        for value in (None, {}, dict(FROZEN_WORKER_FILES, extra='e' * 64)):
            self.assertEqual(history.worker_relation(value, current)['relation'], 'unknown', value)


class ReleaseRegistrationTests(unittest.TestCase):
    """A release that changes a bound file must register the digest it ships, or the records it makes read as unknown
    after the next change. Each test says exactly what to append."""

    def assert_registered(self, inventory_name, inventory, recorded_value, files):
        registered = [entry['files'] for entry in inventory]
        if files not in registered:
            lines = ['    {\'label\': \'<release label>\',']
            if inventory_name == 'PROTECTED_INVENTORY':
                lines.append('     \'implementation_sha256\': %r,' % recorded_value)
            lines.append("     'files': {\n%s}}," % ',\n'.join('               %r: %r' % item for item in files.items()))
            self.fail('The current implementation is not registered in %s. Append this entry to it in '
                      'intune_iac/implementation_history.py (never edit or remove an existing entry), then add it to the '
                      'pinned lists in plugin_tests/test_implementation_history.py:\n%s'
                      % (inventory_name, '\n'.join(lines)))

    def test_the_current_protected_implementation_is_registered(self):
        from intune_iac import protected
        files = protected._implementation_files()
        self.assert_registered('PROTECTED_INVENTORY', history.PROTECTED_INVENTORY, history.protected_digest(files), files)

    def test_the_current_native_atmos_implementation_is_registered(self):
        from intune_iac import journey_native_atmos
        files = journey_native_atmos._implementation()
        self.assert_registered('NATIVE_ATMOS_INVENTORY', history.NATIVE_ATMOS_INVENTORY, digest(files), files)

    def test_the_current_worker_implementation_is_registered(self):
        from intune_iac import protected_worker
        files = protected_worker._implementation()
        self.assert_registered('WORKER_INVENTORY', history.WORKER_INVENTORY, digest(files), files)

    def test_the_failure_message_says_what_to_append(self):
        with self.assertRaises(AssertionError) as raised:
            self.assert_registered('PROTECTED_INVENTORY', history.PROTECTED_INVENTORY, 'f' * 64, {'io.py': 'e' * 64})
        message = str(raised.exception)
        for part in ('PROTECTED_INVENTORY', 'intune_iac/implementation_history.py', 'implementation_sha256', 'f' * 64, 'e' * 64, 'Append'):
            self.assertIn(part, message)


if __name__ == '__main__':
    unittest.main()
