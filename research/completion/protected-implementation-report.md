# Protected execution completion checkpoint

Status: implemented and locally qualified for two explicitly local fixture modes;
**enterprise Intune execution remains blocked**. No Azure token, tenant, cloud
mutation, new paid service, publication or approver trust root was used.

## Concrete delivered behavior

- Actual OpenTofu 1.10.0 Linux AMD64 binary copied from the checksum-qualified release is pinned by exact executable digest.
- A generated literal-output/default-workspace/local-backend fixture is initialized, planned, shown, approved, applied from its saved binary and independently read back.
- The separate synthetic mode runs a fixed isolated child process, supports arbitrary bounded inert JSON fixture values, and backs the guided journey's execution simulation.
- Native binary plan contents are independently rederived with the pinned engine before grant and last-moment validation. JSON sidecars, mutable preparation files and rehashed binary substitutions cannot claim authority over unreviewed native effects.
- Child command arrays are fixed; credentials, CLI/environment overrides, inherited file descriptors, shell dispatch and ambient user configuration are excluded. Seccomp denies socket operations. Output and elapsed process time are bounded; hard AS/CPU/file/descriptor/core ceilings constrain each child before native saved-plan parsing. Seccomp forbids new processes while allowing runtime threads.
- Exact state lineage/serial/digest and before/desired values are bound and independently checked. Durable target-local consumption prevents replay even when a no-op leaves byte-identical state and callers choose another receipt directory.
- Exclusive fsynced hash-linked records and target locks preserve uncertainty after dispatch, lost ownership or receipt failures. Reconciliation classifies independent state without replay or lock theft.
- A separate fixed-origin read-only Azure backend collector performs HEAD → If-Match GET → If-Match HEAD, checking ETag, raw state digest, lineage, serial and lease metadata. It does not claim credential principal or writer ownership authentication.

## Evidence

| Artifact | What it demonstrates |
|---|---|
| `protected-red.txt` | Initial test-first boundary failures before implementation |
| `protected-green.txt` | Current complete protected/native-context test results |
| `protected-native-measured.json` | Actual pinned native local plan/apply, complete receipt history, independent reconciliation and exact implementation digest |
| `protected-native-plan.json` | Unmodified actual native plan JSON, including the prior-output counterexample |
| `protected-native-qualification.txt` | Successful measured native replay result |
| `protected-qualify.py` | Reproducible native-only local qualification script |
| `protected-executable-substitution-{red,green}.txt` | Independent interpreter identity prevents a manifest from self-pinning hostile executable bytes |
| `protected-state-lineage-{red,green}.txt` | A different state lineage cannot pass desired-value readback |
| `protected-cross-journal-replay-{red,green}.txt` | Byte-identical no-op cannot obtain another grant after durable consumption |
| `protected-review-binding-{red,green}.txt` | Rewriting request and preparation review labels cannot relabel a bound change |
| `protected-native-binary-provenance-{red,green}.txt` | A binary plan containing `terraform_data`/`local-exec`, created by planning only, cannot use benign JSON to obtain approval; no malicious apply ran |
| `protected-synthetic-semantic-{red,green}.txt` | Consistent no-op JSON cannot hide the actual saved fixture value change |
| `protected-resource-bounds-{red,green}.txt` | Oversized virtual allocation and sparse files fail, hard resource ceilings are measured, process creation is denied while runtime threads work |
| `protected-context-{red,green}.txt` | Azure backend collector's supplied/simulated state and hard-gate behavior |
| `protected-source-ledger.json` | Exact Microsoft skill/reference identities, applicability limits and official REST/native sources |

The final suite includes hostile grants/actions, executable/configuration/plan
substitution, stale state, expiry, replay, retained ownership, failed receipt
persistence, corrupted journals, state replacement, actual socket denial,
byte-budget overflow, a child that outlives its parent, unrelated descriptor
closure, interpolation rejection, TLS request construction, redirects/partial
responses/duplicate headers/compression refusal and target/credential validation.

Independent security and acceptance reviewers separately reproduced the mutable
saved-plan/value issue, retained failing evidence, and verified the repaired
boundary. Their evidence is recorded in the completion security/reviewer files;
this report does not substitute the implementation author's tests for independent
review.

## Native counterexample retained

The ordinary generic plan reviewer still blocks the actual output-only native
plan because OpenTofu's refresh recomputes its `prior_state` output value while
`output_changes.before` retains the actual original state value. The fixed local
output-only slice independently observes the original state and validates the
exact before/after/configuration and absence of all resource/module/provider
constructs. It preserves the generic blocker and raw JSON. No golden or generic
provider-plan reviewer was weakened to manufacture acceptance.

## Remaining real dependencies

This is not a live Intune executor. No Intune apply/import/assignment adapter,
authentic enterprise approval verifier, protected credential-provider integration
or distributed writer/lease service is shipped. The explicit native context
contract and read-only collector make those requirements implementable without
pretending that local JSON satisfies them. Live credential/principal/federation,
state-backend/platform/TLS behavior, selected-provider effects and independent
service readback still need authorized target evidence.

The local implementation assumes private cooperative POSIX storage and a trusted
runtime. It is not a hostile-administrator filesystem sandbox or tamper-proof
audit store. Windows, network filesystem/power-loss behavior, multithreaded
launcher-host qualification and deployment-native lock/fencing remain open.
The static Linux pin and actual output-only fixture qualify a narrow slice; they
do not close enterprise release acceptance or the provider/service denominator.
