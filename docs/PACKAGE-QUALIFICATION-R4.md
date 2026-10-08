# Exact R4 package qualification procedure

This is executable preparation for the release engineer and independent artifact verifier. It is not a final artifact receipt. The root coordinator chooses the version and freezes the source only after the active service/recovery changes and their required local acceptance are complete. Existing R2/R3 results retain their original source, test scope and limitations. Repeating them is not a substitute for qualification of the final R4 bytes.

## Freeze and source linkage

1. Record the full final Git commit, parent linkage to `289ee9477372825aad848f4482cf681c2ff43b02`, tree identity, explicit `release-source-files.txt` digest, interpreter/dependency/native tool pins and the exact acceptance ledger. Check version agreement in `intune_iac/__init__.py`, `plugin.json`, `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json`. A version string does not authenticate an artifact.
2. Resolve all tracked or untracked changes that affect selected source or runtime dependencies. Preserve unrelated and failing evidence outside the source selection; do not delete it to obtain clean status. Every selected file must be committed as an ordinary file at the stated revision and have the exact tested bytes. If any required runtime file is unlisted, stop and explicitly review its admission.
3. Independently build a table of `relative path, Git blob object ID, committed byte count, committed SHA-256, tested byte count, tested SHA-256` for **every** inventory entry. Read raw Git blob bytes, without checkout, filters, replacement objects, hooks, external diffs, credential helpers or network. Bind the full commit/tree and pinned Git executable; verify Git object digests, not only a caller-provided revision label. Refuse unexpected symlink, submodule, hardlink, missing or duplicate entries. Compare the inventory's own committed bytes too. The existing `workbench_revision` resolver verifies only its bounded selected sources and must not be relabeled as whole-package proof.
4. Record source hashes before and after the final gates. Tests that load helpers or binaries outside the source archive need those exact dependencies in their receipt. Preserve the current stopped provider candidate as unqualified evidence; it must not replace the pinned provider. An implementation inventory mismatch invalidates service approval and needs a fresh reviewed service manifest, not a relaxed check.

The whole-inventory linkage procedure now has an actual release entrypoint. Run
its `--help` first; the repository argument requires a direct `.git` directory
(no worktree/gitdir indirection), while `--source` can be the final extracted
source package. Supply the independently observed pinned Git executable digest.
It rejects selected links, hardlinks, replaced source bytes, uncommitted inventory
changes, config includes/alternates/promisors and replacement-object substitution.
It rehashes every selected raw commit/tree/blob and the source before and after;
unselected files remain outside its explicitly recorded scope.

```text
PINNED_PYTHON -B TRUSTED_SOURCE/scripts/verify-source-linkage.py --repository DIRECT_LOCAL_REPOSITORY --source EXACT_EXTRACTED_SOURCE --commit FULL_COMMIT --git-executable PINNED_GIT --git-sha256 GIT_SHA256 --output NEW_LINKAGE_RECEIPT
```

The inventory check reads a single bounded no-follow source snapshot and ensures runtime selection is a subset. It does not prove clean Git linkage, absence of secrets, package reproducibility or production readiness:

```text
PINNED_PYTHON -B FINAL_SOURCE/scripts/build-release.py --check-only
```

Its `source_snapshot_sha256` is the SHA-256 of the sorted compact JSON map of selected path to file SHA-256. Preserve that map independently, not only the digest. No final archive is created by this command.

## Two archives and byte-identical reconstruction

Use new private output directories on a volume with adequate space. The current engineering `/workspace` is nearly full; `/tmp` is a separate available work volume. This is a local capacity observation, not a durable storage or encryption qualification. Record actual free space before allocating. Do not copy the complete recovered repository merely to build a selected roughly 61 MiB source snapshot.

Run only after the final source freeze. Replace uppercase names with exact reviewed absolute paths and independently retained hashes. The builder creates `Intune_IaC_Plugin_VERSION.zip`, `Intune_IaC_Plugin_VERSION_Source.zip` and `Intune_IaC_Plugin_Archive_Receipt.json`; preserve all three unchanged.

```text
PINNED_PYTHON -B FINAL_SOURCE/scripts/build-release.py --output-dir NEW_BUILD_A
PINNED_PYTHON -B TRUSTED_SOURCE/scripts/verify-release-artifact.py --archive EXACT_SOURCE_ZIP --sha256 INDEPENDENT_SOURCE_ZIP_SHA256 --extract NEW_SOURCE_EXTRACTION
PINNED_PYTHON -B TRUSTED_SOURCE/scripts/verify-release-artifact.py --archive EXACT_RUNTIME_ZIP --sha256 INDEPENDENT_RUNTIME_ZIP_SHA256 --extract NEW_RUNTIME_EXTRACTION
PINNED_PYTHON -B NEW_SOURCE_EXTRACTION/intune-iac-source/scripts/build-release.py --check-only
PINNED_PYTHON -B NEW_SOURCE_EXTRACTION/intune-iac-source/scripts/build-release.py --output-dir NEW_BUILD_B
```

Independently compare both exact ZIP byte streams, sizes and SHA-256 values between A and B. Compare the selected source file table with the source ZIP `SHA256SUMS`, the extracted source files, and the tested-commit table. Compare every runtime member with the corresponding source member and its extracted bytes; require the exact expected set, including complete text/UI entrypoints, launchers, operational docs, native relay source and restoration helpers. Rebuilding from the extracted source verifies that selection does not depend on unlisted checkout files.

Archive `SHA256SUMS` proves internal consistency, not publisher identity or linkage to a tested commit. The trusted external receipt supplies those identities. The verifier does not execute archive code. Independently enumerate the final extracted file set and read back bytes before running it; unexpected files remain preserved and block clean closure. The complete-layer wrapper has its own final physical-set assertion. Earlier three unexplained temporary files remain an open historical finding even if a new extraction has no extras.

The builder uses fixed ZIP timestamps and a single anchored source snapshot for both archives. It rejects symlink/hardlinked source files, missing inventory members, unlisted runtime modules and existing archive/receipt targets. The source inventory is deliberately a content-admission boundary; no build-time pattern scan replaces AppSec or private-data classification.

## Qualify the extracted entrypoints

The strict suite also discovers real Docker host and protected-service tests.
Prepare the unchanged fixed Docker/OpenTofu/relay-v2/relay-v3 inputs through
[the qualification-tool procedure](QUALIFICATION-TOOLS-R4.md), then supply its
four reviewed `INTUNE_QUALIFICATION_*` path values to the verifier environment.
The preparation command reads and hashes existing tools; it does not configure
a daemon, pull an image, provision credentials or approve a different host.
Legacy workspace paths remain defaults for historical replay, not a portable
installation contract. A generic hosted CI runner still requires the exact
declared native profile and its real evidence; relocation cannot waive that gate.

Record source/runtime archive hashes with every command, not just the mutable checkout path. The required verifier has no `--strict` flag: its normal successful result already requires all planned tests to complete with no failures, errors, skips, expected failures or unexpected successes. `--include-core` adds the retained repaired-core scope. Run this required exact final-source gate once; do not rerun the historical 1,141-test R2 or 1,242-test R3 suites merely to increase counts.

```text
PINNED_PYTHON -B EXACT_EXTRACTED_SOURCE/scripts/verify-plugin.py --include-core --output NEW_FINAL_SOURCE_TESTS
PINNED_PYTHON -B EXACT_EXTRACTED_RUNTIME/scripts/intune-iac.py doctor
PINNED_PYTHON -B EXACT_EXTRACTED_RUNTIME/scripts/intune-iac.py service --help
PINNED_PYTHON -B EXACT_EXTRACTED_SOURCE/scripts/qualify-workflow.py --plugin EXACT_EXTRACTED_RUNTIME --output NEW_RUNTIME_CLI
PINNED_PYTHON -B EXACT_EXTRACTED_SOURCE/scripts/qualify-terminal.py --plugin EXACT_EXTRACTED_RUNTIME --output NEW_RUNTIME_TERMINAL
PINNED_PYTHON -B EXACT_EXTRACTED_SOURCE/scripts/qualify-workbench-connected.py --plugin EXACT_EXTRACTED_RUNTIME --python PINNED_PYTHON --output NEW_RUNTIME_CONNECTED
```

The connected harness is an independently asserted **modeled** application journey. Its `--plugin` override selects exact application bytes while checker/fixtures remain separately bound. It does not exercise the protected native provider service or prove device effect. Rebind and run the reviewed native service journey/checker against the final service/runtime implementation inventory, actual pinned Atmos/OpenTofu/provider/relay and declared laboratory protocol profile; retain its exact command, checker SHA-256, source hashes and independent Graph/backend assertions. There is intentionally no invented `service run` terminal command. Native execution uses `ServiceJob.run(signed_receipt, runtime=...)` from the separately trusted controller.

Existing native receipts may be reused only where all relevant dependency bytes and tested circumstances remain identical. If service identity, recovery, state admission, broker, provider, storage or runtime inventory changes, run the corresponding connected success and negative routes against the final package. A prior passing candidate cannot automatically qualify changed final bytes. Required actual negative controls include signature/plan/source substitution, replay, scope conflict, stale state/preimage, partial policy/assignment failure, interruption, lease uncertainty and independently observed recovery. Do not replay the stopped malformed-provider-error lane without its applicable authorization.

The broad verifier and focused/native journeys overlap. Report per-scope counts and outcome, preserving failures/skips; never add overlapping totals. The current GitHub validation workflow is an existing platform contract with separate source and extracted-source gates. A local final-package run does not establish that workflow ran, and local reuse does not waive its actual CI gates.

Capacity/performance runs require a relevant change or final qualification gate and a preregistered quiet window, workload, thresholds and resources. Use the actual commands and root-selection limitations in [the external gate register](EXTERNAL-GATES-R4.md). Native Windows, real Azure/Graph, installed observation scheduling, CI and device routes require their actual authorized environments. Keep their BLOCKED/FAIL/unknown states separate from local package PASS.

## Full continuation evidence and verified delivery

Freeze the full R4 evidence corpus separately after the package qualification receipts exist. Keep literal hostile filenames/links, nested Git fixtures, negative attempts and original inputs. Only transient sockets/FIFOs/IPC are excluded under an explicit typed omission record; never silently omit failed or inconvenient regular files. Capture both a start/end path census and byte/type map so concurrent changes or new files block a frozen manifest. Preserve originals unchanged.

Build both R4 evidence supplements (complete epoch and explicitly attributed external task roots) and the separate stopped provider candidate layer into fresh paths, with exact byte/type manifests, archive sizes/hashes, ordered part pins and the combined root/capsule/IPC coverage map. Complete all nine required layers in [the restoration contract](COMPLETE-LAYER-RESTORATION-R4.md); do not substitute a runtime/source ZIP for the complete R2 baseline. Finalize a **new external** manifest from `CONTINUATION-LAYERS-R4.template.json` after actual R4 pins exist. The committed preparation template remains intentionally blocked. Avoid self-reference: the finalized outer manifest and its delivery receipt live outside the frozen layer they describe.

Record the exact ordered paths returned by transfer. Verify the independently trusted outer-manifest hash and every part/archive before extraction, then restore each layer to its own new directory with `scripts/restore-complete-layers.py`. Do not overlay generations, glob substitute parts or delete unexpected files. The wrapper preserves partial failures and verifies the final physical set. Allocate a suitable separate volume before the full-layer gate; tiny fixture qualification does not prove the exact final multi-gigabyte delivery.

For a saved or published delivery, download/read back the exact returned artifact identity under existing authorization and compare size/hash to the frozen receipt before extraction. Publication and production deployment are distinct actions; no new account, credential, service, repository administration or production mutation is authorized here. When an artifact service or volume is unavailable, preserve locally qualified exact artifacts and name that delivery gate as blocked rather than claiming readback occurred.

The final decision records three separate outcomes: laboratory completion of the exact candidate, real platform qualification for the declared operating profile, and accountable organizational pilot approval. AppSec, provider findings, native Windows support, real tenant/service/device evidence and named owner decisions cannot be established by a passing package suite.
