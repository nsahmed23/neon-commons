# Local Atmos workflow audit

Baseline: Intune IaC 0.2.1, commit `539f9421bf3ab890b0b0ced9d645e6896fbbc02a`. Audit date: 2026-09-30. This review used the Superpowers systematic-debugging process: inspect the relevant path, reproduce the counterexample, compare with a working control/native reference, then write failing assertions. The reviewer did not change implementation files.

Two concrete defects were reproduced. The regression module contains four test methods: one passing control and three failing methods, with six assertion failures when subcases are counted. There were no harness errors. These counts describe the pre-fix baseline, not subsequent repairs.

## LAB-A01 — Missing evidence binding for implementation presence (P2)

`repository.resolve_component` publishes `implementation_exists`, and the graph uses that observation to publish implementation presence. The source fingerprint contains file paths and hashes only; the selection fingerprint binds that source fingerprint and selectors. Creating an empty selected implementation directory therefore changes `implementation_exists` from `false` to `true` without changing either fingerprint. Replacing the directory with an ordinary extensionless file changes the observation back to false while preserving the fingerprints again.

The runner's repository proposal uses the same source fingerprint, so `_recheck` accepts both changes. This is a stale-evidence defect in the local read-only action path. It does not establish an external mutation or approval bypass: external execution remains unavailable.

Minimal reproduction:

1. Configure the stack base and component base, declare component `policy`, and leave its implementation directory absent.
2. Resolve `deploy/dev`/`policy` and create a `repository_resolve` proposal.
3. Create `components/terraform/policy/` with no files.
4. Resolve again: presence changes, both fingerprints remain equal, and the runner accepts its prior evidence.

Control: adding `components/terraform/policy/main.tf` changes the existing byte fingerprint and is correctly rejected by `_recheck`.

Root cause is `repository.py`'s file-only inventory/fingerprint together with the unbound `physical.is_dir()` observation; `runner.py::_repository_evidence` and `_recheck` inherit that omission. The repair should bind filesystem observations actually used by the report, while preserving separate claims for directory existence, valid implementation, and executable readiness. Directory existence alone must never become provider or HCL validation.

Regression methods:

- `test_implementation_presence_is_bound_to_selection_evidence`
- `test_runner_rejects_changed_implementation_presence` (missing → directory and directory → regular file)
- `test_hcl_bytes_already_invalidate_repository_proposal_control`

## LAB-A02 — Malformed effective dependencies disappear from selected queries (P2)

A stack root can contain `settings: {depends_on: [foundation]}`. The literal resolver correctly retains these literal bytes in the effective configuration. `graph.py::_project_effective_atmos` then encounters the list and executes `continue`, dropping the effective dependency without a diagnostic. The static declaration scanner considers component-local settings only, so the root/type-level versions do not receive a declaration diagnostic either.

Even the component-local variant loses its existing static diagnostic when querying the resolved component: the dependency query collects issue relevance from result nodes and edges, and both are empty in this case. The selected component is not included in that relevance set. Root-, type-, and component-local counterexamples all return `nodes: []`, `issues: []` for the selected dependency query.

Native evidence: Atmos **1.199.0**, binary SHA-256 `8e4b057f0cf38686c5eb61db57c8291027a22dfc4ce54a806dc83b34aa96757b`, was run against a self-authored literal fixture with a disabled engine command and no provider/HCL resources. The command was:

```text
atmos describe dependents foundation -s dev --format json --process-functions=false --process-templates=false
```

It exited **1**, reporting that `depends_on` expected `schema.DependsOn` but received `[]interface {}`. The native operation was read-only description of the supplied fixture. An allowlisted environment omitted credentials; the existing seccomp wrapper denied socket creation/connect. Filesystem isolation is not claimed. No provider, state mutation, cloud operation, or external model ran.

The Python graph still marked Atmos configuration resolution `resolved`. That label describes its bounded literal configuration scope; the defect is loss of the malformed dependency and its diagnostic, not an assertion that every literal configuration must be executable. The repair can retain the malformed declaration as unknown with a safe source reference and a component-bound issue. A selected dependency query must include that issue even when no valid dependency edge exists.

Regression method: `test_malformed_dependency_collection_remains_visible_for_selected_component`, covering root, type, and component scopes. It requires a dependency issue and keeps `execution_authorized: false`.

Native fixture/receipt evidence created during the audit:

| Artifact | SHA-256 |
|---|---|
| `lab-workflow-audit/malformed-global/atmos.yaml` | `08e07139a1a635cce8fb8b81f14eada0fb4dda9f85b4cfd09b68ee215f622f6e` |
| `lab-workflow-audit/malformed-global/stacks/deploy/dev.yaml` | `4906ec3bc5dbdb0d90b34454f3c528cc0a38b556ffc770a7610210655c8fb673` |
| `lab-workflow-audit/malformed-global-native.json` | `bf3ce6cec2c9416bd31ecd95170bd3d16977eda24d7689a80118358e593aaf42` |

Those temporary paths are relative to the execution workspace, outside this source checkout. The portable counterexamples are in `plugin_tests/test_lab_audit_regressions.py`; run them with `python -m unittest plugin_tests.test_lab_audit_regressions -v`. Native execution is not needed for ordinary regression discovery.

## Lab acceptance criteria derived from the audit

1. Preserve the difference between physical manifest selection and native logical stack/workspace. Compare native values before treating a target as resolved for execution.
2. Verify state/backend identity separately for two components or stacks that share an implementation directory. Merely resolving the same module is insufficient.
3. Test state removal/reimport and a second no-change plan against an independent preexisting resource, preserving both its identity and assignment-like nested relationships.
4. Include missing implementation, implementation replacement, malformed inherited dependency collection, and absent dependency target cases. The review should show the reason for unknown status, including in queries that have no valid edges.
5. Bind the selected repository/configuration/implementation observations and state identity to an action proposal; change each input independently and require rejection before dispatch.

These are bounded local acceptance criteria. The existing limitations around authenticated tenant ownership, live Intune assignment semantics, provider refresh/serialization, native host behavior, and production approval delivery remain qualification work rather than new audit findings.

## Hypotheses rejected

Extensionless imports with both ordinary YAML and template siblings initially appeared suspicious. Inspection of pinned Atmos `stack_processor_utils.go` showed the current extension-selection precedence agrees with the bounded resolver: `.yaml`, `.yml`, then template extensions for extensionless imports; explicit YAML extensions check for a template sibling. No finding was filed.

A trial using `{region}` in `name_pattern` did not produce the hypothesized cross-stack dependency mismatch: the pinned native output used `dev`, and region was not a resolved naming token in that experiment. Failed lookup commands were retained only as investigative evidence and do not substantiate a defect.
