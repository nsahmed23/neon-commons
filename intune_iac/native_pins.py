"""Exact Linux AMD64 artifacts admitted only for bounded local qualification.

The legacy profile is retained for explicit historical reproduction. Neither
profile grants provider, remote backend, tenant, or enterprise acceptance.
Sizes are per artifact, not a relaxed generic file-size ceiling.
"""
OPENTOFU_CURRENT_SHA256 = 'a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a'
ATMOS_CURRENT_SHA256 = 'f3b5b42e897a2778678cc1231e7a4e2476773bc61ea2af225586dc4e96408802'
OPENTOFU_PINS = {
    OPENTOFU_CURRENT_SHA256: {'version':'1.13.1','bytes':114188448,'profile':'current_local_qualification'},
    '0a9eda0f0898896969492504a6ce778f310675e8a1eb960434c26806cd252627':
        {'version':'1.10.0','bytes':88379576,'profile':'legacy_reproduction_only'},
}
ATMOS_PINS = {
    ATMOS_CURRENT_SHA256: {'version':'1.230.1','bytes':293986466,'profile':'current_local_qualification'},
    '8e4b057f0cf38686c5eb61db57c8291027a22dfc4ce54a806dc83b34aa96757b':
        {'version':'1.199.0','bytes':154943672,'profile':'legacy_reproduction_only'},
}
