# Receiver and authorization worksheet

**Blank fields are UNKNOWN, not approved defaults.** This is a planning worksheet, not an authorization receipt. Preserve existing owner-approved forms when available. Do not put tokens, keys, signed URLs, private plans, or raw tenant captures here.

## Owner decisions

| Field | Owner decision / evidence reference |
|---|---|
| Evidence classification and permitted model-visible metadata | UNKNOWN |
| Evidence owner authorized to permit transfer | UNKNOWN |
| Exact source environment/task identity | Original Work identity must be verified against the C32 record |
| Supported source export action and its authority | UNKNOWN; latest attempted Drive action was scope-denied |
| Exact receiver machine/environment | UNKNOWN; mini PC is a proposed option |
| Exact receiver path / private object destination | UNKNOWN |
| Who may read/write destination and its parents | UNKNOWN |
| Retention requirement and enforcement | UNKNOWN |
| Off-machine / independent-failure-domain backup destination | UNKNOWN |
| Approval for raw private evidence on this machine/provider | NOT ESTABLISHED |
| Approval for local agent to process raw evidence / expose metadata to model | NOT ESTABLISHED |
| Supported action size/resume limits | UNKNOWN |
| Approved synthetic retry after what changed prerequisite | UNKNOWN |
| Credential/consent owner; approved process, no secret values | UNKNOWN |
| Remote Control allowed by account/data policy | NOT DECIDED; optional |

## Measured receiver facts

Record measurement time, command/action, actual environment, and unredacted protected receipt location. Avoid publishing sensitive host identifiers.

| Field | Fresh observation |
|---|---|
| Resolved receiving parent path | UNKNOWN |
| Filesystem / mount / backing volume | UNKNOWN |
| Block/allocation size | UNKNOWN |
| Executing account available bytes | UNKNOWN |
| Inodes / quota limits where applicable | UNKNOWN |
| Windows backing disk availability if WSL/VM | UNKNOWN |
| Guest availability if WSL/VM | UNKNOWN |
| RAM/tmpfs/swap constraints where relevant | UNKNOWN |
| Existing approved write/delete probe result | NOT PERFORMED; no evidence deletion implied |
| Current full transfer/restore peak requirement | Remeasure; 7,827,771,392 bytes is one recorded example before amendment/future outputs |
| Separate lab and control reserves | Preserve original requirements |
| Observed persistence versus documented retention | UNKNOWN |
| Existing backup and verified restore | UNKNOWN |

## Source transfer inventory

| Layer | Source filename/path | Current size/SHA match | Actual destination ID/version/path | Independent readback | Full restore |
|---|---|---|---|---|---|
| r4-evidence | UNKNOWN | NOT_CHECKED | NONE | NOT_STARTED | NOT_STARTED |
| provider-candidates | UNKNOWN | NOT_CHECKED | NONE | NOT_STARTED | NOT_STARTED |
| current-diagnostic-scratch | UNKNOWN | NOT_CHECKED | NONE | NOT_STARTED | NOT_STARTED |
| current-exact-artifact-scratch | UNKNOWN | NOT_CHECKED | NONE | NOT_STARTED | NOT_STARTED |
| Explicit post-cutoff amendment | UNKNOWN | NOT_DEFINED | NONE | NOT_STARTED | NOT_STARTED |

Record cutoff, amendment add/replace/supersede rules, expected manifests, typed-node handling, and missing-original exclusions before declaring completeness. Source labels are not filenames. A null destination is not a broken link to be guessed.

## Decisions that must remain separate

A source export permission is not approval for production data on a home machine. A private folder is not OAuth scope. Local free disk is not source access. A verified ZIP hash is not full restoration. Successful restoration is not laboratory qualification. A new machine is not permission to re-run G13.
