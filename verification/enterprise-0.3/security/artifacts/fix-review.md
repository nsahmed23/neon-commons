# Security repair review

Four low-severity source-backed findings were validated during the Standard scan and all four fixes were independently reviewed in the working tree. This is a partial critical-runtime source audit, not an enterprise production certification. The canonical findings retain vulnerable pre-repair evidence so the audit is reproducible.

| Finding | Repair reviewed | Remaining boundary |
|---|---|---|
| Generated capture/project permissions | Explicit new POSIX directories 0700 and files 0600, including nested files and manifest | Existing permissions preserved; native Windows ACLs and copies/backups unqualified |
| Graph work amplification | Early source/policy multiplicative budgets, stored-graph relational budget before digest, shared outgoing adjacency index | Conservative bounds; enterprise scale/performance qualification separate |
| Restricted-value dictionary recovery | Public per-field digests only for already-visible mapped scalar values; independent oracle and contract version updated | Whole-source digest is equality evidence, not confidentiality |
| Guided parent-path alias overwrite | Canonical scopes after symlink checks; source overlap rejected before writes | Cooperative filesystem, not hostile concurrent ancestor isolation |

Additional independent review caused or checked repairs to plan type-aware equality, malformed replacement paths, receipt event fields and sequence, planned-output denominator, stale-session reload under lock, existing evidence preservation, target control-character rejection and input snapshots, and nonzero CLI exit status for locked/uncertain operations. These were correctness/hardening items; no external execution-authority bypass was established. The dependency verifier was reviewed as read-only exact-lock evidence and makes no publisher-authentication or vulnerability-assessment claim.

Auditor executed three bounded synthetic baseline probes retained under artifacts/. Implementation owners supplied covering red/green tests; the auditor independently read the repairs and selected tests. Owner-reported latest workflow result: 40 scoped tests and a three-invocation, ten-check CLI journey passed. Final integrated release checks remain the root agent's responsibility.

## Repair snapshot

Git base: 3fbfae8f986feda036c6fdb14257be6ad1c5b826. Working-tree edits were in progress; these exact SHA-256 values identify the repair code inspected on 2026-09-30, not an immutable release:

```text
c3629b281d13f08336c910876bb6480e7d644701cf0984d99236b75fc2a6ff0a  reference/core.py
2e2d08637917803f3c040313c46f9a8e4a83fe83fae5eee9577218eefba8f96b  intune_iac/graph.py
f4b956719016ca1fb2ad1efa26c69f05f0c483c222a0ed42e8cc46d68d19610d  intune_iac/production.py
aa5ccadc090493215f0954e86ed543d834883feda8cf6afb6ef7dd6eb965790c  intune_iac/production_oracle.py
0ea8f4116539849225dcdd3dfeaf367c223c86972d098bff095f94575623da51  intune_iac/workflow.py
f1f159c9f17af1be427791fde360a0cbea342348495153c6ed27c1d425623748  intune_iac/target.py
0a6c09809f625434d8bfba4d708fc88a5540e832d991ba81dc018c8d00cf786e  intune_iac/execution.py
15dfaaff88046c5a603f35404f27b26670b5eed9bd47c28471671fec8dfe22a5  intune_iac/reconciliation.py
28620e937e9379417ab237b1643d0abeb05a25a9efb22c7daf37fea4a2bbf6b8  intune_iac/cli.py
1c5881e0db6740dbaef432bf7d5add049cb5d9511f3e2d532c564bba80801d63  scripts/verify-dependencies.py
```

The Standard preflight returned ready, with warning-level unavailable independent nested worker and unknown six-slot capacity. No configuration change, cloud request, real credential use, privileged installation or paid benchmark was performed by this audit. Measured token usage was not provided.
