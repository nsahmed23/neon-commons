# Intune/Atmos 0.5.0 engineering candidate

Historical checkpoint: version and test claims below belong to the named earlier release. Current 0.5.1 scope and unresolved gates are in [EPOCH-ACCEPTANCE.md](EPOCH-ACCEPTANCE.md); the accompanying exact-archive receipts and acceptance ledger are authoritative for delivered 0.5.1 bytes and tests.

Enterprise production acceptance is **BLOCKED**. This release adds executable
identity, approval, provider-lifecycle and recovery components and their local
qualification evidence. It does not claim an authenticated live tenant journey,
an accepted provider/service lifecycle or organizational AppSec approval.

The previous 0.4.0 report and its 729-test claim remain historical evidence in
`COMPLETION-ACCEPTANCE.md`. Current raw runs and source hashes are under
`research/production-completion/`; final integrated and clean-extraction results
are attached to the packaged-release receipt. A missing test or prerequisite is
never converted into a pass.

## Acceptance against the four requested outcomes

| Outcome | Implemented and locally observed | Remaining release gate |
| --- | --- | --- |
| Provider serialization, pagination, import and no-change | Preserved repaired full-provider binary; closed Settings Catalog executor; exact configuration/schema/tool pins; import/refresh/ordinary plan and second-plan contracts; independent preservation mutations; modeled success/partial/lost-response/state-write scenarios | Full current provider RPC and service lifecycle qualification. Current runner denies required AF_UNIX plugin communication. Historical native evidence remains separate. |
| Authentic Atmos/backend/tenant identity | Actual pinned Atmos/OpenTofu local adoption replay; explicit tenant-specific client credential acquisition; opaque tokens; Graph principal and ARM/storage observations; conditional state read; separate provider/backend handles; recorded-response adversarial tests | Authorized live tenant/cloud/principal/backend observations, approved credentials/RBAC and exact native provider credential linkage. A saved evidence JSON is not an execution capability. |
| Protected execution and recovery | Independent signed receipts; malformed/weak key rejection; durable one-time consumption; scoped local locks; bound plan/configuration/source/state/toolchain; child watchdog; private outcome record; journal reconstruction and explicit uncertain outcomes; Azure Blob lease lifecycle mechanics | Organizational approver identity/delivery, complete privileged-worker filesystem and egress enforcement, and native Azure backend integration. Blob lease ownership does not fence Graph or substitute for OpenTofu's own state lock. |
| Supported hosts and enterprise pilot | Linux Python CLI/MCP/local journeys; pinned Atmos/OpenTofu labs. Separate Wally tooling runs on Node 22.16.0 and 24.19.0. Host restrictions are recorded explicitly. | Windows/PowerShell, macOS, actual supported agent discovery/loading and authorized narrow live enterprise pilot. Actual AppSec and accountable organizational acceptance remain required. |

No applicable gate is silently removed because local tests pass. Current provider
execution is explicitly IP-network-denied. The new interactive provider route
uses an operator-provisioned, admitted executor and separate private approval
policy; it is not a general executor for arbitrary repositories or HCL.
The original full local journey and the new provider route remain distinct;
their synthetic and native observations must not be merged into a claimed live
end-to-end adoption.

## Support profile and evidence classes

The production mapping profile remains deliberately narrow: public cloud,
Settings Catalog, Windows/MDM and the admitted choice-setting contract in
`production.py`. Other settings, platforms and resource families are not made
supported by broader synthetic fixtures. Existing family dispositions and the
21-catalog skill inventory are retained in `research/completion/`.

The new identity implementation supports explicit application client-secret
credentials only; it does not silently fall back to CLI, environment, managed,
delegated, certificate or federated credentials. Other identity methods remain
staged. Backend credentials may intentionally represent the same app only when
configured separately; no provider credential is implicitly reused for storage.

Evidence is separated into:

1. **Model/recorded-response:** identity, lease service fixtures, provider response
   transcripts, seeded estates and bounded state-machine checks.
2. **Native local:** actual pinned executable observations, real signatures,
   SQLite/process races, native Atmos/OpenTofu labs and Node hooks/tooling.
3. **Live service:** NOT_RUN in this work. No Microsoft tenant mutation occurred.

Cryptographic verifier/library pins, runtime limits and recovery rules are in
`SIGNED-APPROVAL.md`. The ten locked Python dependencies are unchanged. Evaluation
and native lab dependencies are outside the shipped Python runtime requirements.
The provider binary and source provenance remain independently identified
artifacts, not an implicit download or automatic install step.

## Security and recovery acceptance

New implementation defects discovered by independent challenge were recorded and
repaired separately from historical repository defects. These included approval
expiry during slow verification, spawning before the first authority check,
weak public-key admission, a native-loader cache mismatch, and forged completion
journal provenance. Read the findings and replay logs; their finite coverage is
not certification or a claim of zero vulnerabilities.

Public journals, session flags and state equality cannot prove which plan ran.
The host's private authority record must attest the exact outcome before resumed
completion is accepted. After an uncertain dispatch, reconciliation is read-only
and may establish desired state without establishing successful execution. No
automatic mutation retry or infrastructure rollback is implied.

Compromise of the execution account/interpreter, approved binaries and libraries,
credential store, approval issuer or runner defeats protections that trust those
components. The current provider network filter does not by itself isolate all
filesystem access or every local Unix socket endpoint. A production host must
supply and qualify that boundary; no switch disables the current IP denial to
pretend the missing boundary exists.

## Wally remains a separate acceptance decision

The newly supplied Wally 3.0.0 archive was independently preserved, reproduced and
repaired as Wally 3.0.1. Its application-facing review remains read-only. Its
review cannot authorize Intune actions or accept security risks.

The bounded evaluation package has 24 exposed TRAIN tasks across eight families,
functional/metamorphic oracles, grader challenges, four matched treatments and a
fixed downstream repairer interface. The runner could not enforce the required
agent isolation: all 96 scheduled treatment trials are NOT_RUN, with zero model
calls. Structural grading cannot establish the correctness of arbitrary causal
prose; that gap is explicit and blocks usefulness credit and promotion. No
candidate was promoted. No Intune performance benefit or generalization claim
is established by hook measurements or simulator results.

## Exact external qualification sequence

Complete these against the exact release hashes; retain every failed attempt.
Named roles below are required owners, not organizational appointments by an LLM.

1. **Host maintainer:** qualify the pinned toolchain on each advertised native
   host, including AF_UNIX provider RPC, filesystem/egress denial, cancellation,
   descendant cleanup and real agent discovery/loading. Run the packaged native
   labs and clean-extraction tests. A permissive fallback is not a passing test.
2. **AppSec and execution-service owner:** independently review the privileged
   worker, issuer/key delivery, global replay store, credentials and Azure backend
   integration. Resolve confirmed or credible unresolved high-impact findings.
3. **Tenant/backend owner:** authorize a disposable tenant/subscription and exact
   pilot object IDs, groups, filters, scope tags, principal permissions and state
   location. Use explicit credentials through the documented protected channels.
4. **Pilot operator:** collect authenticated inventory; establish complete
   preservation; import immutable IDs; refresh-only and ordinary no-change plan;
   approve one exact saved change; apply; authenticated readback; second no-change
   plan. Preserve settings and assignment tuples, exclusions and filter modes.
5. **Pilot/recovery owner:** exercise denied collections, lease/concurrency loss,
   revoked credentials, interruption, response loss and journal/state/receipt
   failures within authorized scope. Reconcile uncertain mutations without blind
   retries. Observe rollout/diagnostics on the explicitly included endpoints.
6. **Release owner:** record accountable residual-risk decisions and dates, then
   expand beyond the narrow pilot only after the relevant additional families,
   identities, hosts and scale limits are separately qualified.

The library APIs and replay commands are executable; unavailable credentials,
native isolation and organizational acceptance are not fabricated internally.
This document records remaining implementation/integration gaps as well as
external qualifications, rather than attributing every gap to tenant access.
