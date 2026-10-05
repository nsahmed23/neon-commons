# Terraform training corpus audit

The catalog is useful and has been acquired in full. It supplies practical patterns for grading real state transitions. It is a Terraform training catalog, not an Atmos or Intune adoption implementation. Its checks also have limits that the plugin must not inherit.

Source: [Stéphane Robert, terraform-dsoxlab-training](https://github.com/stephrobert/terraform-dsoxlab-training/tree/86b69d2292485d179698f5b9bf648a29f935e216), commit `86b69d2292485d179698f5b9bf648a29f935e216` (2026-09-25). Full Git checkout was acquired successfully. `source-files.json` records the SHA-256 of every tracked file. The repository was left pristine.

## What was actually reviewed

| Denominator | Completed here | Meaning |
|---|---:|---|
| Tracked source files | 1,663 / 1,663 | All bytes acquired and hashed, 5,488,893 bytes total. |
| Declared labs and actual lab roots | 88 / 88 | Exact match, including all declared fixture paths. |
| Plaintext files beneath lab roots | 1,310 / 1,310 | Automated content scan of 86,020 lines / 3,696,694 bytes. |
| Functional checker sources | 88 / 88 | Parsed actual Python ASTs; recorded 649 test functions and 1,564 assertion nodes. These are static counts, not collected or passing test cases. |
| Lab topics | 88 / 88 | Human review of content-derived titles, dependencies and actual test topics; disposition in `lab-matrix.csv`. |
| Selected semantic inspections | 24 / 88 | Targeted review of assertions, fixture/runtime mechanisms and lessons relevant to adoption. |
| Complete functional checker sources read | 8 / 88 | 2,157 lines; listed below. This is not a claim that all supporting prose or all 88 checkers received exhaustive manual review. |
| Encrypted reference solution files | 299 / 299 | Ciphertext acquired and hashed; zero decrypted or semantically reviewed. |
| Native upstream labs run by this inventory | 0 / 88 | Native runs by separate qualification harnesses must have their own receipts. |
| Isolated checker counterexamples | 2 / 2 | Selected real upstream assertion functions accepted adversarial stub inputs; no native provider or emulator ran. |

Complete checker review covers `getting-started/terraform-overview`, `getting-started/terraform-workflow`, `first-infra/debug-apply`, `state/understand-state`, `state/diagnose-state`, `state/state-locking`, `modules/test-module`, and `aws/import-moved-drift`.

The upstream `validation-labs.json` reports 88 `VALIDE` results under Terraform 1.16.1 / dsoxlab 0.1.91, dated 2026-09-25. It reports initial score zero for each, 87 final scores of 100 and one final score of 90 (`certifications-associate-essential-commands`, despite 8/8 tests). These are inspected upstream claims, not our executions. A passing solution and a failing starting state are useful controls, but do not establish that the grader rejects every incorrect history.

## Findings and required adaptations

| ID | Finding in inspected source | Concrete response for the plugin/lab |
|---|---|---|
| CAT-IDENTITY | `aws/import-moved-drift` finds the current instance by a tag, then compares current state to that current object. Its final inventory excludes terminated objects. The selected identity/count assertions accept a replacement instance after the original has terminated. | Capture immutable pre-operation IDs and inventory before any write; compare them after import, move and recovery. Check an independent mutation journal or all relevant object lifecycle states where available. |
| CAT-PLAN-HISTORY | `terraform-workflow` treats a saved plan becoming stale as proof that this particular plan was applied. Another apply can advance state and stale an unused plan. The selected assertion has no distinguishing evidence. | Bind execution to the reviewed plan bytes/hash and native tool invocation receipt. Retain state lineage/serial and postconditions. Use staleness as a concurrency check, not proof of approval or execution history. |
| CAT-IGNORE-ALL | `state/diagnose-state` uses `ignore_changes = all` to preserve a legacy random value whose declared attributes would otherwise cause replacement. | Keep that as a teaching comparison. Do not use ignored differences or a later zero-change plan to certify faithful Intune configuration. Require source/config/state value preservation independently. |
| CAT-EXECUTION | All labs say `runtime: shell`, but 11 declare Docker services; nine mount the host Docker socket; three require libvirt provider resources; one optional HCP lab provisions real remote resources. | Run only reviewed local scenarios in disposable directories with explicit executable/environment bounds. Treat Docker-socket, libvirt and remote-account scenarios as separate environments. Shell runtime does not provide isolation. |
| CAT-REPLAY | All 299 reference solution files are Ansible Vault ciphertext. Root pytest setup skips when the maintainer vault password is absent; unplayed labs also skip. | Do not report a skipped root suite as a successful replay. Write our own exercise answers from public fixtures and run the original reviewed assertions with replay disabled, or record unavailable execution. |
| CAT-CLI | Helpers invoke the literal `terraform` binary. Some fixture constraints demand Terraform >=1.15.0, even when exercises use a provider-free subset. | Record engine/version separately. Any OpenTofu wrapper, changed constraint or adapted assertion must be listed in the execution receipt. No cross-engine success inference. |
| CAT-SCOPE | The local locking test includes an S3 documentation questionnaire alongside actual local locking measurements. AWS/Floci tests exercise an emulator, not Azure or Intune. | Split observed local behavior, documentary facts, emulator behavior and live service results. Never promote one evidence class into another. |
| CAT-HARNESS | Shared subprocess helpers inherit process context and often omit timeouts. Graders deliberately apply, destroy, mutate files, push/move state, or kill their own child process group. | Wrap execution with a finite timeout, a deliberate environment, dedicated work directories and cleanup receipts. Do not expose production credentials or repositories to exercises. |

`checker-counterexamples.json` is deliberately labeled **isolated assertion evidence**. The script loads only three named, reviewed functions from the pinned checkout and supplies explicit stubs; it does not import upstream conftest, execute fixtures, call cloud APIs, or claim that a complete lab was replayed. The identity example establishes acceptance by two central assertions; it does not claim every assertion in that lab was executed. The stale-plan example establishes a missing distinction in the assertion; a separate native run is needed to observe the alternate history.

## Lessons to implement and qualify

| Capability | Best source lessons | Native local acceptance check | Remaining production boundary |
|---|---|---|---|
| Existing-object adoption | `state/understand-state`, `state/diagnose-state`, `aws/import-moved-drift` | Seed an object before management; record original identity/value; import it; assert no create/delete, unchanged identity/value, both ordinary and refresh-only no-change. | Selected Intune provider import/refresh/config serialization and real assignment semantics. |
| Reviewed plan execution | `getting-started/terraform-workflow`, `environments/terraform-in-automation` | Save native plan, inspect native JSON, bind its digest, apply that exact plan, reject stale or changed plan/context. Also run the stale-unused-plan counterexample. | Authenticated approver delivery, final effective cloud/backend context, privileged runner and concurrency. |
| Semantic relationships | `write-code/depends-on`, `state/terraform-state-list`, environment split labs | Keep value reference, explicit order, module membership, address migration and backend ownership as distinct relations; compare resolved Atmos values with native output. | Dynamic Atmos functions, authenticated reference existence, provider-specific ownership. |
| State identity | `state/backends`, `state/backup-restore-state`, `environments/workspace` | Verify effective local backend path, selected workspace, lineage and serial; refuse unrelated/older state; isolate separate stacks. | Azure storage endpoint/container/key/workspace/blob identity and lease behavior. |
| Partial failure recovery | `first-infra/debug-apply`, `hcp-terraform/remote-runs` | Cause a deterministic failure after one successful effect; resume; preserve successful IDs and prove the failed effect was repaired. | Real policy/settings/assignment request splitting and uncertain remote outcomes. |
| Locking and interruption | `state/state-locking` | Hold a real native state lock; measure contention; interrupt the owned child; reconcile the abandoned attempt and verify recovery. | Azure distributed locking, protected execution locks and service-side concurrent writers. |
| Non-destructive refactors | `state/terraform-state-mv`, `write-code/for-each`, `modules/module-anti-patterns` | Replay old-address state with a moved declaration; inspect `previous_address`, ordered action arrays and original IDs. | Real resource importer/address support across provider upgrades. |
| Removal | `state/terraform-state-rm`, `state/removed-block` | Distinguish forget/delete; ensure removing state ownership does not delete the simulated object or silently recreate it later. | Intune lifecycle/retention decisions and explicit removal authorization. |
| Test validity | `modules/test-module`, `scripts/valider-labs.py` | Intact baseline passes; required test count >0; deliberately corrupted values, mappings and prerequisites fail. | Native hosts, external services and observed incident recovery. |
| Sensitive evidence | `write-code/outputs`, sensitive-data family, CI lab | Canary secrets stay out of model-visible reports while raw state/plan remain restricted; demonstrate that `sensitive` alone does not remove values. | Live token handling, access policy, retention and incident operations. |

This gives an actionable local qualification curriculum. It closes acquisition of this pinned corpus and identifies concrete executable tests. It does **not** close G12 as fully executed, or make the plugin production-ready. Atmos workflow tests, actual selected-provider validation and service qualification must each retain their own denominator and receipts.

## Reproduce the content inventory and assertion counterexamples

Use a pristine checkout at the recorded pin and a Python environment with PyYAML:

```bash
python research/terraform-catalog/inventory.py --checkout /path/to/terraform-dsoxlab-training --output /tmp/catalog-audit
python research/terraform-catalog/checker-counterexamples.py --checkout /path/to/terraform-dsoxlab-training --output /tmp/catalog-audit/checker-counterexamples.json
```

The tools read the upstream checkout and write only their requested report locations and disposable temporary files. They do not run upstream lab scripts. The static inventory can be rebuilt deterministically.

## Attribution and reuse

Upstream content is published by Stéphane Robert under **Creative Commons Attribution 4.0 International**, as declared in the repository README and `LICENSE`. The exact license is retained as `UPSTREAM-LICENSE.txt`. Its source SHA-256 is `9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411`.

The inventory includes derived titles, descriptions, test names and assertion expressions. Changes made here are machine extraction, categorization, audit commentary, and isolated counterexample harnesses. They are not upstream endorsements. Any copied/adapted fixture or grader in the plugin's native lab must retain the repository, commit, attribution, license and a list of adaptations. This package contains no decrypted solution content or copied upstream executable binaries.
