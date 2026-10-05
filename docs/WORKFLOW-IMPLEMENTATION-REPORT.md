# Task 4 implementation and evidence

Status: implemented and exercised for **local cohort authoring**. Enterprise E06 remains partial. The guided journey does not authenticate targets, qualify the provider, establish writer ownership, execute adoption or reconcile a remote operation.

## Delivered

- `intune_iac/workflow.py`: strict local session/receipt contract, current artifact reconstruction, dependency checks, saved frontier intersection, targeted invalidation, ring/group intent and partial cohort generation.
- `intune_iac/wizard.py`: backward-compatible `guided=False` parameter delegates to the new flow when requested. The existing v1 single-policy wizard remains unchanged otherwise.
- `plugin_tests/test_workflow.py`: 23 tests covering the integrated guided path and its adversarial cases.
- `docs/WORKFLOW.md`: commands, exact local meaning of milestones, storage and recovery boundaries.
- Root integration added `wizard --guided` to `intune_iac/cli.py`.

Signatures are `run_guided_workflow(session_path, input_path=None, context_path=None, output_path=None, input_fn=input, output_fn=print, repo=None, stack=None, component=None)`, `reconstruct_progress(session_path)` and `preview_resume(session_path, changes)`.

The local `ownership` milestone records a completed assessment whose answer is unknown; it never claims authenticated ownership. Ring/group decisions are declared intent; no membership is inferred and captured assignments are not retargeted. This distinction is in runtime output and every returned progress report: `external_verified_completed=[]`, `execution_authorized=false`.

## Verification executed

Command:

```bash
/workspace/scratch/26b6d364cfda/plugin-clean-venv/bin/python -m unittest plugin_tests.test_workflow plugin_tests.test_wizard -q
```

Observed result: **40 tests passed** (23 guided workflow, 17 existing wizard), zero failures/errors/skips; 10.883 seconds in the recorded final scoped run. Log: `/workspace/scratch/26b6d364cfda/workflow-scope-green.txt`. Root owns the final integrated whole-project verifier after parallel changes stabilize.

The initial 12 workflow regressions failed as assertions because the guided implementation was absent. After implementation they passed. Additional hardening reproduced and repaired these specific failures:

| Finding | Failing observation | Repair and retained regression |
|---|---|---|
| Cancellation lost after save | A cancelled session could be saved and later generate without `continue` | Preserve cancelled lifecycle across suspension |
| Receipt write failed after output | Unknown marker incorrectly reset to none | Retain unknown until checkpoint commits; no automatic replay |
| Synthetic repo mode | Synthetic reference generator could produce active output against repository intent | Refuse synthetic repository mode, matching the original wizard boundary |
| State read before lock | Simulated prior writer cancellation was ignored | Reread session under the acquired cooperative lock |
| Parent-path alias, independently found by security reviewer | `x/../SESSION.evidence/inventory.json` concealed source inside the receipt directory; checkpoint overwrote it | Canonicalize after symlink rejection, then check all scopes before writes |
| Preexisting evidence | First use replaced a user file at the derived receipt path | Exclusively create the evidence directory; preserve conflicts |

The red logs remain at `workflow-red.txt`, `workflow-hardening-red.txt`, `workflow-repository-red.txt`, `workflow-lock-red.txt`, `workflow-alias-red.txt` and `workflow-evidence-conflict-red.txt` in the workspace root. The first draft of the initial test used an incorrect `examples/unsupported` fixture path; it was corrected to the actual `examples/partial` path before the recorded 12-assertion red baseline. That harness correction was not a product fix.

Additional passing coverage includes missing or rehashed forged receipts, cyclic dependency claims, symlinked receipts, source changes at the prompt, generated output edits with a forged manifest hash, forged completion beyond the saved frontier, changed cohorts and stack, synthetic assurance escalation, legacy session preservation, unknown outcomes, and complete multi-policy output denominators. A production-shaped repository journey emits inactive `.tf.txt` candidates and zero active `.tf` files.

## Actual CLI subprocess journey

Harness: `/workspace/scratch/26b6d364cfda/qualify-guided-workflow.py`.

Evidence directory: `/workspace/scratch/26b6d364cfda/enterprise-workflow-qualification-final`.

Three actual Python CLI subprocess invocations passed **10 checks**:

1. Select two observed policy UUIDs, one supported and one without captured relationships; save at `partial_generate`.
2. Confirm a changed stack preview retains milestone frontier six and the partial path.
3. Resume, generate both UUID project directories and finish a local handoff. The supported synthetic project has reference HCL; the blocked policy has blockers and no active HCL.
4. Reconstruct all nine local milestones from current files, with no external completion or authority.
5. Delete the mapping receipt, reconstruct the missing prerequisite, and resume the actual CLI to verify it displays `provider_mapping` without replaying generation.

The receipt records each exact argv, stdin digest, exit code, transcript hashes, source file hashes and check result. Receipt SHA-256: `068ae1c1f69bc98d81344c775225aa00497089aa739f923e084acef0d930a4bb`.

An earlier harness assumed all stdout was JSON, although the interactive CLI correctly writes prompts followed by a JSON result. That parsing failure and successful product transcript are preserved in `/workspace/scratch/26b6d364cfda/enterprise-workflow-qualification`. The fixed harness parses the trailing result and used a fresh directory. No cloud, provider, native host or paid model operation occurred.

## Claude-m comparison requested during implementation

Read-only inspection at commit `703f383198963a3596f7a86ff63c9f98574a21b6` of `TheLobbi/Claude-m`:

| File | SHA-256 | Finding |
|---|---|---|
| `README.md` | `6e722229f49f93a871225924eb4be9474f10c9a26ead8194368abdc18a389045` | Claims a Microsoft plugin marketplace and MIT licensing; a LICENSE/COPYING file was not found in the acquired tree |
| `microsoft-intune/commands/intune-compliance-policy-deploy.md` | `168841872a75503c4353e5fed16e3e2cff03f31145c135e7cbdff20e60d1204e` | Generic preflight, baseline, mutation and readback prose; lists placeholder-looking GET endpoints `/intune-compliance-policy-deploy` and `/microsoft-intune/verification`; not selected-provider or Graph qualification evidence |
| `planner-orchestrator/skills/planner-orchestration/references/etag-patterns.md` | `3e6eade715de2c303eb70972f871eb0bf67a323e90a56d6466fc2aebd8dc98c6` | Separates task/details ETags and recommends bounded retries for Planner; these claims were not applied to Intune or uncertain outcomes |

Useful design direction is explicit baseline/readback and separate per-resource progress. It does not supply an Intune request/state harness or prove a resumable wizard's receipt integrity. No code was copied, no supplied hooks or skills installed, no instructions executed and no service endpoints called. The marketplace's production-grade label was not accepted as validation.

## Rulings and remaining boundaries

- Use a separate `2.1.0` local session format and explicit `--guided` opt-in. This preserves existing workflows and avoids claiming automatic migration of the proposed correction v2 schema. Cost: v1 sessions need their original wizard or a new guided session.
- Implement nine local observation milestones, not fictitious enterprise success. Unknown ownership and membership remain visible. Cost: external adoption still requires the authenticated resolver/executor/provider workstreams.
- Record cohort intent without changing assignments. Cost: ring rollout and group membership qualification are still independent implementation/tenant work.
- Keep unknown interrupted generation non-replayable and preserve evidence. Cost: guided automatic reconciliation is not implemented; the user must independently inspect the result and attempts.
- Per-file atomic replacement is not a whole-session power-loss transaction or an adversarial filesystem guarantee. Cooperative local locking and truncation on broken receipt dependencies are the qualified boundary.

Remaining live gates: real exporter/provider schema/import/refresh/no-change behavior; authenticated tenant/principal/backend/writer; protected approval and executor; policy/assignment partial failure readback; actual cohort membership; host/platform qualification; authorized tenant pilot and enterprise acceptance. This report does not close those gates or the enterprise goal.
