# R4 initial reconciliation checkpoint

This is a continuation checkpoint, not a completed milestone or release.
Source baseline is **0.8.0**, commit
`289ee9477372825aad848f4482cf681c2ff43b02`, on dedicated branch
`continuation/r4-20261007`. The root coordinator recorded a clean starting tree
in `work/evidence/epoch-20261007-r4/BASELINE.json`. No older source was restored
over newer work. The current implementation agents may have subsequent
uncommitted changes; inspect Git status before continuing.

The complete user-supplied contract is persisted byte-identically at
`work/docs/INTUNE-WORKBENCH-STRICT-CONTRACT-20261007.md` and this project's
`docs/STRICT-CONTINUATION-CONTRACT-R4.md`: **26,294 bytes**, SHA-256
`88192ac7e2627368fedcbc01e8f1faeb0f26120983f70bcdbb89e87bbdcb2c5a`.
It supersedes the earlier “brief not yet supplied” observation without rewriting
that historical receipt.

`docs/CONTINUATION-R4-LEDGER.json` records 91 requirement rows with the requested
identity, profile, status, evidence class, source/artifact applicability,
procedure, evidence, environment, limitation, next action and owner fields.
It includes 18 explicit fault families. Only baseline continuation linkage is
PASS; new implementation/qualification remains NOT_STARTED or externally
BLOCKED until actual receipts justify an update. Status here does not erase
existing implementation or original qualification. The initial ledger is also
saved unchanged in `work/evidence/epoch-20261007-r4/reconciliation/INITIAL-LEDGER.json`.

The historical R3 acceptance ledger remains unchanged: **310,833 bytes**, SHA-256
`7c1e5839c1c470199fd31f849b67730f7236c2a61e7375b1a6075e0e99f8b6a7`.
The baseline 1,242/1,242 exact-source strict result, 64-check/34-command/10-PTY
connected journey and separate 1,141-test R2 result were **not rerun**. Failed
final01/final02 candidates, cleanup/acquisition repairs and failed intermediate
repairs, all six threads, raw inputs, old skips, Wally negatives, unexpected
files/reappearance and commit-actor gaps stay immutable. The original three
unexpected files and attribution gap are not closed by successful new work.

The first unblocked dependency is accurate repository/observed/proposed/coverage
views, distinct collector/provider-state/deployment baselines, and complete
declared cross-stack ownership. Extend the existing store and application
entrypoints. Independently challenge merged-only, portal-only and simultaneous
changes, state-absent objects, conflicting owner, stale index, incomplete
collection, bad IDs/targeting/types and collection semantics. Then integrate
the common protected worker/backend contract; implement authentic reader and
independent scheduling; present those shared contracts in the visual workspace;
qualify required native routes; and qualify/package the exact reviewed release.
These dependencies and scoped external gates are recorded in the ledger.

Read `docs/OPERATING-PROFILE-R4.md` before expanding support. Native Windows/Git
Bash is a required external route, not removed because this host is Linux.
Current source pins are OpenTofu **1.13.1** and Atmos **1.230.1**; older
1.10.0/1.199.0 lab/fixture contracts retain historical scope. The new production
CI choice is unresolved: GitHub Actions is the existing documented candidate,
Azure DevOps Pipelines is unconfirmed. Implement the common worker contract
locally first; deployment needs the actual organizational choice and applicable
authorization. Do not disable the restricted lab network boundary.

The actual launcher is `scripts/intune-iac.py`. Root, `workbench`, `provider`,
`capture` and `target` help were invoked with the retained runtime; all five
exited zero. Raw stdout/stderr, argv and hashes are saved in
`work/evidence/epoch-20261007-r4/reconciliation/HELP-RECEIPT.json` and sibling
files. These are entrypoint discovery records, not tests or service evidence.
No new qualification command is claimed until its implementation and help exist.

Resume by reviewing current status and the preserved plan:

```bash
cd /workspace/intune-continuation/work/projects/intune
git status --short
git log -5 --oneline
cat docs/CONTINUATION-R4-CHECKPOINT.md
cat docs/OPERATING-PROFILE-R4.md
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py workbench --help
```

At this checkpoint the ledger agent changed only four project documentation
files (`STRICT-CONTINUATION-CONTRACT-R4.md`, `CONTINUATION-R4-LEDGER.json`,
`CONTINUATION-R4-CHECKPOINT.md`, `OPERATING-PROFILE-R4.md`), the work-level brief
copy, and new `reconciliation/` evidence. The agent did not commit; the
coordinator owns the integrated durable commit. New candidate/artifact
identities remain null rather than incorrectly borrowing baseline hashes.

The initial reconciliation's structural checks validate required fields,
normalized statuses, unique IDs, dependency references, existing source paths,
brief equality and historical reference hashes. They do not count as product
tests. Save new independent product assertions and failed attempts in new R4
subdirectories, update exact revision/artifact applicability, and commit a
durable checkpoint after each meaningful increment.

**Outcomes:** laboratory work under the new contract is incomplete; required
platform qualification is blocked on concrete native environments and approved
service scopes; organizational production approval is absent. Continue all
independent local work. No production change, credential provisioning, platform
administration, paid resource or privilege expansion is authorized by this
checkpoint.

## Increment 1 — exact capture replay repair

The initial two new regressions failed: sequential replay produced two observations; four concurrent imports produced four. Publication now serializes duplicate detection and insertion in one SQLite write transaction. Every import attempt remains visible, exact raw capture bytes and original timestamps remain unchanged, and duplicates reference the original observation without refreshing it. The changed-scope run passed 37 tests (overlapping existing suites; not added to the historical strict count). Before/after argv, output and source hashes are in `work/evidence/epoch-20261007-r4/capture-reimport/`.

This commit checkpoints the store repair, its two actual-entrypoint/concurrency regressions and the R4 contract/ledger/profile. It is not an integrated R4 release. Additional working-tree files for views, authenticated collection, visual presentation, backend and worker are being implemented on the same continuation branch; preserve them and inspect `git status --short`. The complete old 1,242-test suite has not been rerun. The new baseline/pending reader evidence-class and inert artifact-kind plumbing is additive; imported evidence remains non-authoritative.

Resume this repair with:

```bash
/workspace/intune-runtime/bin/python -B -m unittest plugin_tests.test_capture_reimport_r4 plugin_tests.test_capture_adapter plugin_tests.test_workbench_capture_store plugin_tests.test_workbench_paging
```

Continue integrating the pending A/B/C/D lanes and independent acceptance. This checkpoint does not close the milestone, service, native Windows or production gates.
