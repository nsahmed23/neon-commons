# Atmos lab source audit and reuse decisions

The requested local lab is feasible. Official Atmos examples already teach catalog imports, component aliases, existing Terraform adoption and state migration. Their source must be inspected before execution: “no cloud credentials” often still means network access, external providers, tool downloads or hooks.

This review cloned three complete working trees with shallow history, pinned their commits, and inspected selected implementation files. It did not execute their complete test suites. The 48 selected file hashes and source links are in `source-ledger.json`.

| Repository | Pinned commit | License | Use here |
|---|---|---|---|
| [cloudposse/atmos](https://github.com/cloudposse/atmos) | `67c41025906dccbed309334218d2c41a394862e4` | Apache-2.0 | Stack/catalog structure, existing-project migration, migration/hook counterexamples |
| [cloudposse/test-helpers](https://github.com/cloudposse/test-helpers) | `b9bf0df1746c9460e2624dd5bfe9e7f139473b07` | Apache-2.0 | Disposable fixtures, dependency lifecycle, apply then no-change plan assertions |
| [minamijoyo/tfmigrate](https://github.com/minamijoyo/tfmigrate) | `e9f8a87fef214e2fe3e3108f88fd855d988e7a1d` | MIT | State migration preview, rejection on unexpected plan changes, failure and replay boundaries |

No upstream implementation code is vendored by this research directory. Its recommendations adapt ideas into the plugin's own tests. Any later copying must retain the upstream license and applicable notices; modified Apache-licensed files need modification notices.

## What the actual examples establish

All paths below are relative to the pinned Atmos repository.

| Source | Useful relationship or scenario | Dependencies and audit decision |
|---|---|---|
| `examples/quick-start-simple` | Three logical stages import a shared station catalog; `metadata.component: weather` separates instance name from implementation | `weather/main.tf` calls `https://wttr.in` through `data.http` and writes through `local_file`. `required_providers {}` does not remove these implicit providers or pin them. Reuse the stack pattern; replace the weather module in the offline lab. |
| `examples/native-terraform` | Keep existing tfvars with `!include`, or convert to literal YAML; explicit `name: production` differs from filename `prod.yaml` | Uses `hashicorp/null ~>3.2`. Dynamic includes and newer stack-name behavior exceed the plugin's current literal resolver. Treat these as counterexamples and future qualification cases, not silently supported input. |
| `examples/hooks-tfmigrate` | Rename a managed address while retaining identity, sharing local state across legacy/current components; preview before apply and history for reruns | Uses random provider plus auto-downloaded OpenTofu and tfmigrate; workspaces are disabled to share one state. It is local, but not provider-free/offline as supplied. |
| `examples/hooks-tfmigrate-advanced` | Import, state removal, provider-address replacement, count-to-for_each moves, two-state moves, mismatched hook modes, migration failure | Useful adverse cases. The import example uses `random_string` and imports `prexist1`; this is a provider-specific demonstration, not Intune adoption evidence. Some examples intentionally allow hook failure. Such settings cannot become production acceptance defaults. |
| `examples/hooks-tflint/components/terraform/example` | A simple `terraform_data` resource and typed input with no provider download | The resource is suitable for the offline fixture. The surrounding stack invokes a TFLint hook; do not assume the entire example needs only OpenTofu. |
| `tests/fixtures/components/terraform/exit-code` | Built-in resource permits deterministic process-failure tests without registry downloads | Includes a local-exec provisioner and timestamp replacement. Adopt the failure-test idea, not an always-changing resource in a no-change adoption case. |
| `tests/fixtures/scenarios/hooks-keychain-test/components/terraform/hook-and-store` | Minimal built-in resource preserves input/output data | Reuse this minimal-resource idea independently of the keychain/hook stack. |

The installed Atmos binary is **1.199.0**, corresponding to source tag commit `10886fe5b17f034c01e2396c0c47de19575a8065`. That tag contains quick-start-simple but lacks the newer native-terraform, hooks-tfmigrate and hooks-tflint examples and migrate command tree. Current-main documentation must not be presented as validation of installed 1.199.0 behavior. The new lab should pin and record its tool versions.

There is also a source-level documentation discrepancy worth preserving: the advanced migration README gives `--migration migrations/<file>`, while the current state-migration agent skill says to pass just the filename because the generated configuration already points at the migrations directory. The correct invocation needs qualification against the chosen Atmos release; this audit did not execute tfmigrate to resolve it.

## What to take from the testing helper

`pkg/atmos/terraform_apply.go:ApplyAndIdempotentE` runs apply and then requires a detailed-exitcode plan to return zero. This is a useful executable convergence condition. The component-helper also creates disposable fixture trees and destroys dependencies in reverse order.

Two patterns should not become our acceptance oracle:

- `pkg/atmos/terraform_plan.go:PlanE` supplies `-lock=false`. Production adoption must retain state locking and bind the observed state revision to the reviewed action.
- `pkg/atmos/component-helper/20_drift_tst.go:DriftTest` searches for human-readable no-change text. Our gate should inspect the exit status and structured saved-plan changes, including unexpected deletes, replacements, drift and output changes under an explicit policy.

The helper's current module declares Go 1.24.2 and toolchain 1.26.5, Terratest and broad AWS/Kubernetes/container dependencies. Adding the whole module would be unnecessary dependency expansion for this Python plugin's small local harness. Its cloud/module suites were not run.

## tfmigrate: useful mechanism, specific limits

`tfmigrate/migrator.go:setupWorkDir` initializes the configured backend, selects the workspace, pulls existing state and temporarily overrides the backend to local. `state_migrator.go:plan` applies the migration operations to temporary state, runs a detailed-exitcode Terraform/OpenTofu plan, and normally rejects exit 2. `Apply` computes that migration again and only then calls state push. `tfexec/terraform_plan.go` uses a temporary state path and saved plan; `state_import_action.go` invokes the provider's import operation against temporary state.

This is a concrete model for reviewable state adoption. It does **not** make arbitrary provider calls harmless: init, import and refresh still execute the configured providers and their service reads, and repository hooks may run other commands. For Intune, the importer and refresh behavior still need provider qualification.

The source exposes four integration requirements:

1. `force`, `skip_plan`, `from_skip_plan` and `to_skip_plan` bypass parts of the no-change gate. A restricted adoption adapter must reject these options instead of relying on defaults.
2. Multi-state apply pushes destination state before source state in two separate calls. A failure between them is a partial migration, not an atomic outcome; reconciliation must inspect both stores before retry.
3. History persistence happens after the state changes. `command/history_runner.go` explicitly reports that apply can succeed while saving history fails. Durable action receipts must represent that uncertain replay boundary.
4. `history/controller.go` identifies applied migrations by filename. A production action must additionally bind the reviewed migration/configuration/tool digests, effective target/backend, state lineage and serial. A filename is not content integrity or authenticated approval.

The inspected `StatePush` invocation does not force overwrite or disable locking by default. This review did not establish a single lock spanning the entire pull/plan/push sequence or an atomic multi-state transaction. Preserve the underlying lineage/serial protections and add orchestration-level concurrency control.

## Native feasibility experiment actually executed

`native-import-probe.json` records a self-authored fixture executed with the installed Atmos 1.199.0 and OpenTofu 1.10.0. It used a built-in `terraform_data.identity` resource, a local backend, default workspace, literal stack configuration, a clean environment, and child-only network-deny seccomp. No external provider, Intune service, cloud credential or model was used.

| Command/condition | Observed result |
|---|---|
| Atmos describe component | Exit 0; resolved stack `lab`, component `adoption`, workspace `default` |
| Atmos OpenTofu init | Exit 0; built-in provider, no registry download |
| Import a UUID to identity-only `terraform_data` | Exit 0; exact UUID retained |
| Plan after identity-only import | Detailed exit code 0, no changes |
| Add a populated `input` object after that import | Detailed exit code 2, update-in-place |

The counterexample matters: built-in import binds the ID but does not reconstruct arbitrary input/settings. It supports a genuine native identity/import/no-change lab, while populated policy preservation must be tested separately. Calling an imported `terraform_data` object an Intune policy roundtrip would overstate the evidence.

The first experiment launch referenced a nonexistent Python executable and failed before Atmos started. The path was corrected to the running interpreter; the receipt records only launched native commands and explicitly notes that harness error.

## Resulting lab requirements

- Exercise real Atmos describe, init, import, plan and apply against disposable built-in resources; record executable versions, command results, state identities and structured plan assertions.
- Include catalog/default/override provenance and logical stack/component/implementation/workspace distinctions. Compare plugin resolution with native Atmos only for the admitted literal subset.
- Separate identity-only import, state-address refactoring, settings/targeting preservation and drift simulation. Each scenario must state whether it modifies configuration, local state, a local surrogate or a real service.
- Require no-change after successful adoption and repeat execution. Fail closed on unexpected replacement, incomplete capture, wrong identity, changed backend/plan binding, partial outcomes and stale approval evidence.
- Keep the actual selected Intune provider schema/refresh and service tests as separate qualification gates. The lab removes the excuse for missing local engineering; it does not substitute for those gates.

This report's recommendations are inputs to the executable lab implementation. Completion claims must cite that lab's own receipt, not the existence of these upstream examples or this source review.
