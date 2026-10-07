# Intune / Atmos / Wally R3 continuation — 0.8.0

The exact tested source is commit [`289ee9477372825aad848f4482cf681c2ff43b02`](https://github.com/nsahmed23/neon-commons/commit/289ee9477372825aad848f4482cf681c2ff43b02), continuing preserved 0.7.0 commit `74130d0db99febf2f41cf4f4ebe2920a5d4dffb7`. The unrelated Neon Commons main branch is unchanged.

Read the [checkpoint](work/CHECKPOINT-20261007-R3.md), [acceptance ledger](work/docs/CONTINUATION-ACCEPTANCE-20261007-R3.json), and [short execution sequence](work/docs/EXECUTION-SEQUENCE-20261007-R3.md). The ledger preserves the complete R2 ledger and its exact **1,141-test** scope; that baseline was not rerun.

## Implemented and qualified

Wizard adoption now connects preserved lineage to persistent maintenance, exact-plan approval/execution, independent readback, convergence, delayed-response recovery without replay, and closed-terminal scheduled observation. Bounded capture retries preserve progress, raw attempts and cancellation. Scoped reads and explicit pagination repair five routes that failed on the 1,000-policy fixture. Narrow official vendor reference facts retain separate authority and applicability limits.

- Exact extracted source: **1242/1242 passed**, 0 failures, 0 errors, 0 skips. [Result](work/evidence/epoch-20261007-r3/milestone-0.8.0-final03/strict-suite/result.json), [complete raw test log](work/evidence/epoch-20261007-r3/milestone-0.8.0-final03/strict-suite/test-log.txt), [command](work/evidence/epoch-20261007-r3/milestone-0.8.0-final03/strict.command.json).
- Exact source and runtime each: connected journey **64 checks / 34 commands / 10 PTY sessions**; capture **59 checks / 20 real CLI commands**; capacity **48 CLI/PTY commands / 10 named checks**. These overlapping checks are not added to the strict count.
- Actual pinned OpenTofu init/provider schema RPC/credential-free validation passed. Linux Codex registration/discovery/install/list/uninstall passed **26 assertions / 10 commands**, with all **130 installed files** matching the runtime ZIP. [Native result](work/evidence/epoch-20261007-r3/native-codex-container/RESULT-FINAL02.md) and [independent raw-evidence review](work/evidence/epoch-20261007-r3/native-codex-container/INDEPENDENT-SPOTCHECK-FINAL02.json). No model session or skill invocation was run.
- [Commit/package binding](work/evidence/epoch-20261007-r3/milestone-0.8.0-final03/artifact-binding.json), [byte-identical rebuild and unchanged extracted file maps](work/evidence/epoch-20261007-r3/milestone-0.8.0-final03/reproducibility.json), [qualification](work/evidence/epoch-20261007-r3/milestone-0.8.0-final03/QUALIFICATION.json), [capacity qualification](work/evidence/epoch-20261007-r3/milestone-0.8.0-final02/CAPACITY-QUALIFICATION.json).

The runtime archive is byte-identical to final02. Its completed native, capture, capacity and runtime journey evidence is retained with its original commit and archive identity, supported by the [explicit reuse proof](work/evidence/epoch-20261007-r3/milestone-0.8.0-final03/REUSED-QUALIFICATION-EVIDENCE.json) and [independent package comparison](work/evidence/epoch-20261007-r3/independent-artifact-reuse-final03/receipt.json). Final03 changes only the native guard observation test; its strict suite, source connected journey and rebuild were executed separately. The intermediate final02 strict failure (1,241/1,242) remains preserved.

The original descendant census cleanup repair has explicit root cause and original failing-before/passing-after evidence; it remains unchanged. A separate SIGINT ownership gap found by the first R3 strict gate was repaired and independently qualified through both supervisors with background-thread cases. The first strict result (1,234/1,236; one failure and one error) and rejected mask-only intermediate repair are preserved. [Spawn repair review](work/evidence/epoch-20261007-r3/strict-scheduler-independent-review/README.md). [Evidence reconciliation](work/evidence/epoch-20261007-r3/reconciliation/RECONCILIATION.md). Historical unexplained temporary files, workspace restart/reappearance gaps, and the recorded earlier commit-command actor attribution gap remain unresolved; source content and tested commit linkage are independently verified. All failures, skips, inconclusive security results and Wally negatives remain evidence, not deleted exceptions.

## Exact product packages

| Package | Bytes | SHA-256 |
|---|---:|---|
| [Source](packages/Intune_IaC_Plugin_0.8.0_Source.zip) | 16,627,882 | `4a0e56e4e01dd58e911a7fd0ad87c8f0be851630f3beb9c40d7ccc0b1b4c8590` |
| [Runtime](packages/Intune_IaC_Plugin_0.8.0.zip) | 513,895 | `cce47f620f5e1e7d3dbdab1e030624fae3991cbf88376737a4eda07e6c703515` |

These product packages supplement the complete repository; they do not replace it. All 3,087 source payloads match the tested Git commit, apart from the separately generated archive manifest documented in the binding receipt.

## Complete recovery layers

1. Retain/recover the **complete immutable R2 repository snapshot**, all six saved threads, original inputs and historical evidence from the [R2 handoff](https://github.com/nsahmed23/neon-commons/releases/tag/intune-r2-handoff-20261007). Exact ZIP: **2,289,864,715 bytes**, SHA-256 `7117ab67ce6ae1912aa2c984774e6370216f3eb28be1510d0c6814cb4c295d0b`. Its fresh anonymous full reconstruction and safe extraction were independently verified.
2. Add these exact 0.8.0 packages and current checkpoint/ledger. Use a separate source working copy; preserve the R2 source and evidence.
3. Add the **entire R3 evidence epoch** from [R3 evidence distribution manifest](R3-DISTRIBUTION-MANIFEST.json), using the [separate reassembly-only helper](distribution-tooling/restore_r3_evidence.py) and [instructions](distribution-tooling/README.md). All payloads, failures, binaries and literal symlinks are included in the typed supplement. This is explicitly a supplement, not a replacement complete repository ZIP. The helper validates independent byte/SHA pins and does not extract or execute anything.

The complete R3 supplement is **1,013,682,416 bytes**, SHA-256 `a133c651f2df19885d8b1706944bd953f5a5be67960955ee7021600707b62a35`. It preserves **28,975 regular files and five literal symlinks**. [Build and exact file-set verification](delivery-evidence/ARCHIVE-BUILD-RECEIPT.json).

[Browser evidence index](prominent-evidence.json) supplies selected byte-identical raw receipts; the full supplement preserves every epoch file. GitHub automatic Source code ZIPs are not the complete repository. Existing release-asset upload returned HTTP401; pinned public Git byte chunks provide the complete transfer without credential provisioning or privilege changes.

## Remaining release gates

**Laboratory:** the exact 0.8.0 packages passed the recorded local scopes. **Platform:** native Linux schema and Codex install lifecycle passed only their stated scopes; live Graph/Intune/Azure/GitHub controls, device outcomes, skill activation and other hosts remain unqualified. **Organizational production approval:** not granted.

The live execution worker and integrated Azure backend remain an implementation/integration gate requiring reviewed host, egress, filesystem, secret, issuer and backend boundaries; supplying a token does not create a production adapter. Finite modeled scheduling is not an installed authenticated Graph fleet collector. Broader mappings/native OIB/dynamic Atmos remain unsupported. [External procedures](guides/EXTERNAL-QUALIFICATION-R3.md) and the acceptance ledger specify each environment, authorization, procedure, expected evidence and release blocker. No production mutation, deployment, new paid service, credential provisioning or privilege expansion occurred.

The files under `guides/` preserve their original package bytes. Earlier host statements in those documents remain historical; the current checkpoint and linked `RESULT-FINAL02.md` establish the newer, narrowly scoped Linux Codex install qualification. They do not establish model/skill activation or qualification on other hosts.
