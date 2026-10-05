# Synthetic estates and native local labs

`intune_iac.synthetic` creates reproducible Intune-shaped estates from an integer
seed. It emits raw policy/settings/assignment pages, stable UUIDs, duplicate
names, external groups/filters/scope tags, per-policy contexts, repository
identity, modeled state, a plan, approval and history. These are explicitly
synthetic artifacts. They are never credentials, signed approvals or evidence
that a tenant was changed.

```bash
python scripts/intune-iac.py synthetic generate --seed 42 --output /tmp/new-estate
python scripts/qualify-synthetic.py --output /tmp/new-synthetic-qualification
```

The Python API is `write_estate(output, seed=42, policy_count=3,
case='baseline')`. It returns `capture`, `context` and `estate` paths. The
existing reference mapping selects one policy; `capture.json` therefore uses
an explicit per-policy projection and retains the entire policy inventory.
`capture-estate.json` retains every policy's relationships. The
`selected_capture(estate, policy_id)` API supports each other policy without
selecting by display name. The generator accepts 1–8 policies; a separate test
constructs a 65-policy inventory and exercises the actual graph projection
budget rejection.

The oracle's expected policy data is authored before capture serialization.
`compare_normalized` imports no production or reference normalizer. It checks
identity, tenant, writable policy fields, settings, assignment multiplicity,
exclusions, filters, tags and readiness. Assignment/tag ordering and JSON key
ordering are legitimate alternatives. Mutation checks must reject changes to
meaning while accepting those alternatives. Existing independent engine
verification also checks every generated project against its source.

The retained `research/completion/synthetic/result.json` reports three seeds,
78 estates, 234 per-policy mapping/generation/verification runs, 69 deliberate
corruptions, 13 legitimate alternatives and 22 modeled transition checks.
These counts are distinct from the 17 Python test methods. The truth file is a
test fixture, not a tamper-resistant trust root or a production verifier.

| Case family | Executed distinction |
| --- | --- |
| Baseline, reordered, malicious label | Stable identity and full semantics survive; malicious-looking display text remains data. |
| Empty, omitted, null, denied assignments | Empty known targeting differs from missing/denied targeting; malformed null data remains blocked. |
| Pagination loop, cross-origin, duplicate, missing first/final page | Mapping is blocked; no active IaC is emitted. |
| Unknown setting and nested unknown field | Unqualified content is preserved for review and blocked from active generation. |
| Wrong tenant/cloud/principal/backend/lineage/serial | Modeled execution refuses changed target/state without effects. |
| Expired/replayed/substituted approval or plan, lease loss | Modeled execution refuses invalid authority/context without effects. |
| Before/after policy, assignment, state and receipt fault labels | The simulation records an uncertain outcome, consumes its modeled approval and refuses convergence/replay. These are protocol branches, not native crash injection. |
| Fresh plan for current serial | A legitimate newly reviewed modeled plan can converge. |

`simulate_local_transition` is an in-memory no-op adoption protocol. It models
approval consumption, target binding, state staleness and uncertainty. Complete
state object/field semantics and the exact plan action multiset must match the
authored truth before convergence; matching lineage/serial alone is insufficient. Its
`effects: 0` and `simulation: true` are intentional. Native partial effects are
established separately below. A `recovery` estate is a ready baseline for a
new modeled attempt; it does not itself prove recovery from a prior failure.

## Native receipts from this completion

The two original scripts ran unchanged, with newly acquired exact release
artifacts. Official published SHA256SUMS match Atmos 1.199.0 and the OpenTofu
1.10.0 archive; extracted executable hashes also match the existing pins.
This run did not verify release signatures. Acquisition details, the initial
missing-pytest failure, the successful rerun, command transcripts and evidence
are retained in `research/completion/native-labs/`.

| Run | Observed result | Boundary |
| --- | --- | --- |
| Original Atmos adoption | 18 checks, 25 native commands passed | Built-in local objects; saved plans, state identity, stack isolation, stale-plan refusal and bare-ID import limit. |
| Original upstream locking adaptation | 8 unchanged upstream tests passed; 1 S3 documentation test deselected | OpenTofu local backend, not Terraform 1.15, dsoxlab CLI, S3 or Azure. |
| Authored completion supplement | 18 checks, 24 native commands passed | 11 exact retained Atmos literal fixtures; moved/forgotten state and actual partial-effect recovery. |

```bash
python scripts/qualify-adoption-lab.py --atmos /path/to/atmos --tofu /path/to/tofu --output /tmp/new-adoption
python scripts/qualify-locking-lab.py --upstream /path/to/pinned-corpus --tofu /path/to/tofu --pytest-python /path/to/pytest-8.4.2/python --output /tmp/new-locking
python labs/completion/qualify-native.py --atmos /path/to/atmos --tofu /path/to/tofu --output /tmp/new-supplement
```

The supplement reuses the original bounded, clean-environment native child
runner and mandatory socket-denial filter. It hashes retained parity fixture
files against their existing source manifest before use. It operates only in
a fresh disposable directory with the accepted pinned executables. Native
commands have 45-second/output bounds and the shared 300-second overall bound.
It is not a filesystem sandbox and is not intended for hostile workspace
mutation. Do not pass user repositories or arbitrary commands to its internals.

The supplement proves that `moved` changes only the address while preserving
ID/lineage; `removed { lifecycle { destroy = false } }` plans `forget`, then
converges without recreation. Its partial apply uses two built-in objects and
a fixed failing local provisioner. The first object survives, the assignment
stand-in is tainted, repairing the fixed provisioner preserves the first ID,
and the next native plan returns no change. This is local state recovery, not
an Intune assignment-service transaction.

All 1,663 pinned upstream files were reacquired and their hashes matched the
retained corpus. Every one of the **88 labs** has an explicit disposition in
`upstream-lab-dispositions.json` and `.csv`: one native OpenTofu adaptation
replayed; 87 not replayed. Local/provider candidates still require their own
authored exercise completion and reviewed runtime. Docker, libvirt and HCP
scenarios require separate environments. The supplement is original work and
must not be counted as running those upstream labs. No encrypted solution was
decrypted. Attribution remains Stéphane Robert, CC BY 4.0, pinned commit
`86b69d2292485d179698f5b9bf648a29f935e216`.

No lab result changes live import/apply authorization. Native local evidence,
provider contract tests, mocked service behavior and live service qualification
retain separate boundaries and denominators.
