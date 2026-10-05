# Independent bounded completion acceptance review

Reviewed 2026-10-02. This is a bounded local acceptance/security review, not a
certification, penetration test of every component, or live qualification.
The threat model is hostile model arguments and imported repository/configuration
data; the filesystem/process owner is trusted unless a component expressly
claims OS isolation. No existing credentials, tenants, Graph calls, provider
calls, or live mutations were used. Product code was not modified by this reviewer.

## Final bounded result

All three confirmed findings below were fixed by their owners and independently
retested. The sampled MCP capability and CLI completion routes passed.
The independent `research/completion/reviewer-tests/` suite now contains thirteen
checks, all passing. Its final output is retained in
`reviewer-tests/acceptance-green.txt`; the original native-admission failure is
preserved in `reviewer-tests/acceptance-red.txt`.
No confirmed finding remains open within these sampled controls. This supports
bounded local acceptance of those controls, not whole-release or live acceptance.

## A-01: Unadmitted unrelated stack reaches native Atmos

**Severity: medium. Status: fixed by owner; reviewer regression passed.**

Before the fix, `native_atmos.resolve_native_atmos` accepted a repository on the strength of
`resolve_component(root, selected_stack, selected_component)`, then copied every
file in its `sources` inventory to the native snapshot. The literal resolver
intentionally parses only the selected/imported document closure, while
fingerprinting other stack manifests without parsing them. Thus an unrelated
included stack containing a dynamic YAML tag and a parent-traversing import is
copied into the snapshot and passed to native dispatch without inert-subset
admission.

Reproduction: create an ordinary `physical.yaml` with stage `pilot` and component
`policy`, then add `stacks/unrelated.yaml` containing:

```yaml
import: [../../outside]
vars: {stage: !exec "hostile-command"}
```

The selected literal resolution remained `resolved`. With the exact pinned local
Atmos binary available for its hash check, intercepting `_supervise` proved that
native dispatch was reached and the unrelated file's exact bytes existed in the
snapshot. A matching intercepted response yielded `status: verified`.
The independent negative test expected dispatch never to occur and initially
failed. The interceptor does not execute the tag or import and is not evidence
of command execution, a filesystem escape, or data disclosure. Native execution
still disables functions/templates, and that defense must not be conflated with
complete source admission.

The module docstring and `docs/REPOSITORY.md` native section promise independently
admitted source files and rejection of dynamic repositories. That promise was
stronger than the implementation. The owner added `_admit_all_sources`, which
admit-checks every staged YAML manifest, its imports, type sections and all
components before binary admission and dispatch. Reviewer regressions now reject
the dynamic unrelated stack, a separate plain-string parent-traversing import,
and an unselected component with a runtime hooks field. A valid two-stack literal
repository remains accepted by the intercepted comparison positive control.
The passive literal resolver's intentionally looser discovery behavior remains
distinct. These checks establish admission behavior; they are not native exploit
or native-parity tests.

## A-02: Synthetic no-op oracle ignored state content and action coverage

**Severity: medium. Status: fixed by owner; reviewer regression passed.**

Before the fix, either of these changes to `generate_estate()` left
`inspect_estate(...).success == true` and
`simulate_local_transition(...).converged == true`:

1. Replace `estate['state']['objects']` with an empty dictionary.
2. Remove all assignments from an existing state policy.

The original modeled plan, approval digest, lineage and serial were untouched.
An empty plan action list also passed after recomputing the explicitly modeled
approval digest. Metadata checks and a vacuous `any(actions != ['no-op'])` check
did not establish complete state semantics or action identity coverage.
This was a false synthetic convergence claim, not an execution-authorization
bypass: output remained explicitly synthetic with `execution_authorized: false`.

The owner added a source-independent authored state/action comparator. Reviewer
tests now reject missing state objects, lost assignments and empty action
coverage; inspection rejects missing objects, and the baseline remains accepted.
Owner tests additionally cover settings, duplicate/unrelated action identities,
and legitimate ordering alternatives. The separate journey convergence path
compares its independently reconstructed desired policy-hash model against
actual local synthetic-process state; this finding did not establish a bypass
of that path.

## A-03 / SEC-009: Rehashed saved plan could obtain approval for unreviewed effects

**Severity: high for the native local execution boundary. Status: fixed by
owner; synthetic and harmless native reviewer regressions passed.**

Before the fix, `_validate_request` compared a request with its persisted
`preparation.json`, recomputed file hashes, and re-reviewed the JSON sidecar.
Those checks did not establish that the saved executable plan represented the
operation described by the reviewed JSON. Replacing the saved plan and updating
the mutable request/preparation hashes could preserve all those comparisons.
Checking the current `main.tf.json` did not constrain configuration embedded in
an opaque native saved plan. A newly issued in-process approval was therefore
possible for a saved plan whose effects were never reviewed.

The reviewer independently reproduced a benign end-to-end failure through the
fixed synthetic worker: initial state `{}`, approved desired value
`{"approved": 1}`, substituted saved value `{"unreviewed": 2}`. Only the saved
plan hash, aggregate binding digest and persisted preparation were updated;
the approved JSON sidecar was left unchanged. Validation returned `valid`,
approval produced a grant, and execution wrote the unreviewed value. Only
post-effect readback returned `outcome_unknown` / `readback_mismatch`.
This is recorded in `reviewer-tests/saved-plan-binding-red-observation.txt`.
The formal reviewer tests first ran after the owner's concurrent fix, so this
record is explicitly an observed reproduction, not a claimed RED unittest run.

The owner's separate native RED/GREEN regression produced a native saved plan
containing a `terraform_data` provisioner, restored the benign current config,
and rehashed the request/preparation. The old approval constructor accepted it.
That test never applied the provisioner, even in its RED run; command execution
impact follows from the saved-plan apply path and is not represented as an
observed malicious native effect. Its records are
`research/completion/protected-native-binary-provenance-{red,green}.txt`.

The fixed native validator re-runs pinned `show -json` on the exact saved plan
descriptor, compares those output bytes with the bound sidecar digest, and
performs the strict output-only semantic review. The synthetic validator parses
its exact saved-plan schema and independently binds the original state digest
and approved desired value. Checks run before grant issuance and before apply.
The existing post-effect comparison remains a separate uncertainty control.

Three independent saved-plan regression methods pass. Two reject the harmless
synthetic substitution before effective approval. The native method uses the
real pinned binary to plan an alternate literal output, with no resources,
providers or provisioners in the substituted config. It verifies rejection both
with the stale benign sidecar (`binary_plan_json_mismatch`) and with the truthful
replacement sidecar (independent output/configuration mismatch). That alternate
native plan is never applied; its state bytes remain unchanged. Evidence:
`reviewer-tests/saved-plan-binding-green.txt`.

## Sampled controls that passed

- MCP rejects top-level and nested input/repository paths outside operator roots
  before local action dispatch. Operator capabilities cannot be provided in
  tool arguments or initialize payloads. Missing authority, relative paths,
  symlinks and sibling lock placement outside the write roots are rejected by
  the sampled tests. The documented cooperative-filesystem boundary is honest;
  race resistance against a hostile filesystem owner is not established.
- CLI exposes the completion commands, rejects combined journey/guided modes,
  and returns nonzero for sampled failure/inconclusive/blocked qualification
  states. Synthetic generation and inspection execute real local routes.
- Native selected-stack dynamic tags, unsafe selectors, unsupported logical
  stack patterns and substituted executable bytes fail closed in owner tests.
- A run of `plugin_tests.test_native_atmos_completion`,
  `plugin_tests.test_security_boundaries_completion`,
  `plugin_tests.test_completion_cli` and
  `plugin_tests.test_synthetic_completion` passed **32 tests**. These are Python
  regressions, not 32 native executions or live tests.

Commands used Python at
`/workspace/scratch/e2e4042ea5fd/.venv/bin/python`, with the repository as working
directory. The independent suite runs with
`-m unittest discover -s research/completion/reviewer-tests -v`.

## Evidence and release boundaries

The native result compares a bounded configuration slice. Workspace/backend
digests do not authenticate identity or ownership. Journey completion represents
a synthetic local policy-hash process; no-change in that model is not provider
or tenant convergence. The reviewed documents disclose these limits.

No whole-repository security certification, Windows execution, production
Intune import/apply, arbitrary Atmos runtime-layer parity, or live recovery is
established by this review. Security agent evidence and native-lab receipts have
their own distinct scopes and denominators and are not substituted for these
reviewer checks.

For the separate Wally deliverable, the correct source archive retrieval is
reported blocked by HTTP 502. A continuation built from other material must
remain labeled as a continuation; this review does not establish repair or
acceptance of the unavailable original archive.
