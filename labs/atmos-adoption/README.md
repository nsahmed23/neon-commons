# Native Atmos adoption lab

This lab executes **Atmos 1.199.0 and OpenTofu 1.10.0**, with the built-in
`terraform_data` resource and disposable local state. It exercises the mechanics
of wrapping an existing managed estate in Atmos: retain state and identity,
resolve stack configuration, review a saved plan, apply that exact plan, isolate
workspaces, and reject a stale plan. The plugin independently resolves the same
literal stack files and its effective variables are compared with native Atmos.

It is original lab code. No upstream lab solution is copied, and no external
Terraform provider, cloud account, container, paid model, or dsoxlab installation
is needed. `terraform_data` stores local values; it does **not** implement Intune
policy updates, targeting, pagination, refresh, or assignment service semantics.

## Run the complete lab

Prerequisites:

- Linux amd64, Python 3.12+, `libseccomp.so.2`, and the plugin's existing Python
  validation dependencies (`requirements-validation.txt`).
- Previously acquired Atmos **1.199.0** and OpenTofu **1.10.0** Linux amd64
  executables. Acquisition is separate from execution; the runner never downloads
  or silently changes versions. Binaries must match the SHA-256 values below.
- A **new directory outside the plugin source**, whose parent already exists.

From the plugin source directory:

```bash
python scripts/qualify-adoption-lab.py \
  --atmos /absolute/path/to/atmos \
  --tofu /absolute/path/to/tofu \
  --output /tmp/intune-atmos-adoption-lab
```

Use another fresh output name for each run. Existing output is an error and is
preserved. The process returns 0 only when every native command and assertion
succeeds; failure returns 1, and an interrupted run returns 130. A command has a
45-second deadline, combined captured output is limited to 2 MiB per command,
and the entire lab has a 300-second deadline.

| Tool | Release | Executable SHA-256 |
| --- | --- | --- |
| Atmos | [v1.199.0](https://github.com/cloudposse/atmos/releases/tag/v1.199.0) | `8e4b057f0cf38686c5eb61db57c8291027a22dfc4ce54a806dc83b34aa96757b` |
| OpenTofu | [v1.10.0](https://github.com/opentofu/opentofu/releases/tag/v1.10.0) | `0a9eda0f0898896969492504a6ce778f310675e8a1eb960434c26806cd252627` |

These are executable hashes, not ZIP hashes. Checksums identify the previously
qualified artifacts; authenticate any new acquisition against official release
checksums and signatures. The runner rejects other bytes. A version upgrade
requires deliberate review, new pins, and fresh native qualification.

## What happens

| Step | Native operation and asserted result |
| --- | --- |
| Resolve | Native `describe component` resolves logical `dev`/`prod`; the plugin resolves physical `deploy/dev`/`deploy/prod`. Effective variables must be exactly equal. The differing selector concepts remain explicit. |
| Create a pre-existing estate | Plain OpenTofu creates a policy-shaped local object and a targeting-shaped object. Capture their IDs, full state, lineage, and serial before adoption. |
| Adopt intact state | Relocate the exact state bytes into the component's `dev` workspace. The original active state path must cease to exist. No identity is rediscovered by labels or tags. |
| Plan and apply no change | Atmos creates a saved plan with detailed exit code 0. Both resource actions must be `no-op`. Atmos applies that named saved plan; state resources, outputs, lineage, and serial must remain equal. |
| Isolate stacks | The same implementation under `prod` plans two creations and receives a different state lineage and resource IDs. The `dev` state must remain unchanged. |
| Detect desired change | A `setting=deny` override produces an in-place policy update, preserving its ID and producing no targeting change. The saved plan is retained. |
| Apply another saved plan | A separate `setting=ask` plan is inspected and applied using Atmos's pinned `--from-plan --planfile` interface. The state serial advances while IDs and lineage remain equal. |
| Reject stale state | Direct OpenTofu execution of the earlier `deny` plan must fail specifically with `Saved plan is stale`. Both current stacks' states must remain unchanged. This proves state-staleness rejection, not approver authentication or execution provenance. |
| Import a bare ID | A separate identity-only `terraform_data` resource is imported through Atmos. The ID is retained and the identity-only project produces an exit-0 no-change plan. |
| Expose import's limit | Add populated input to that imported resource. It must plan an update: bare-ID import did not recover configuration values. This is separate from intact-state adoption. |
| Leave a visible difference | The `dev` manifest still says `allow` after applying the `ask` saved plan. The final plan must expose that desired/current difference; the lab does not silently reset it. |

The fixed fixture has an abstract catalog component, inherited variables, two
physical deployment manifests sharing one implementation, and a local targeting
reference to the preserved policy ID. Included and excluded groups are synthetic
UUIDs. The local state relationship is asserted; no group membership or real
Intune assignment operation is inferred.

## Inspect the evidence

The output directory contains:

- `result.json`: every assertion, binary/fixture hashes, native argv, expected and
  actual exit codes, environment and scope.
- `logs/`: separate stdout, stderr, and receipt for each command. Timeout, output-limit, and
  interruption attempts are recorded after the owned child group is terminated.
  Child output is drained through pipes before the parent alone writes each
  transcript; final reporting rechecks each transcript against its command receipt.
- `evidence/`: original state, independent plugin resolution, and machine-readable
  plan JSON. Resource action sets must match exactly, including all addresses;
  an extra deletion or replacement fails.
- `artifact-hashes.json`: hashes of generated evidence and working files, excluding
  copied runtime executables (their pinned hashes are in `result.json`). This is
  a consistency inventory, not an authenticated receipt or an approval.
- `repository/`: the actual working Atmos repository and its local state.
- `original/`: the pre-adoption OpenTofu configuration, without its relocated
  active state file.

For the reviewed runner, a successful execution currently contains **18 checks
and 25 native commands**. Resource UUIDs differ across runs; reproducibility means
that the assertions and behavior recur, not that separately created states have
identical bytes. Inspect the current `result.json` rather than relying on this
count if the lab changes.

## Execution boundary

The runner accepts only the seven fixture files with hashes embedded in its
source. Modified or additional files, symlinks, different native binary bytes,
existing output directories, and output inside the plugin source are rejected.
It copies and validates the fixture into the fresh output before execution.

Native children inherit an explicit minimal environment, with no credentials,
`TF_CLI_ARGS`, shell customizations, user home, or caller-provided Atmos settings.
A local `getent` helper supplies a fixture home for pinned Atmos's home lookup.
Telemetry and version checks are disabled. A mandatory child-only Linux seccomp
filter denies `socket`, `socketpair`, and `connect`; there is no permissive
fallback if the filter fails. Processes run without a shell, in their own process
group, which is terminated on timeout or interruption.

There is no filesystem sandbox. This tool is for its reviewed fixed fixture in a
cooperative workspace, not arbitrary user repositories or hostile concurrent
filesystem modification. The script's internal `--guarded-exec` entrypoint is a
child bootstrap, not a general-purpose safe command API. The normal public
interface takes only tool paths and a new output path.

## What this closes and what it cannot close

This supplies actual native evidence for the bounded local Atmos/OpenTofu
workflow, rather than only testing Python models against generated fixtures. It
also gives a repeatable regression surface for future resolver and action-runner
work. Deterministic plan/state assertions are the judge for these invariants; an
LLM can explain a failure but cannot change a failed result to a pass.

Production adoption still needs selected Intune provider schema and refreshed
state qualification, real capture authenticity, target/backend identity,
authenticated approval delivery, remote locking and recovery, assignment service
semantics, provider partial-failure behavior, and native-host qualification.
`terraform_data` has no independent remote service to refresh; the final desired
value difference is not evidence of detecting real service-side drift. A passed
lab does not enable production import/apply actions in the plugin.
