# Terminal security qualification — 2026-10-04 epoch

Enterprise release remains **BLOCKED**. This epoch repairs verified local
boundary defects and executes the stable TERM-01–TERM-16 selection. Passing
individual assertions is not acceptance of a complete attack family or a
supported enterprise deployment. The final evidence receipt, rather than an
inherited test count, identifies the exact source and measured outcomes.

Replay from the extracted source using the pinned dependency environment:

```bash
python -B scripts/qualify-terminal-security.py --output /absolute/new-security-evidence
python -B scripts/qualify-change-coverage.py --output /absolute/new-change-evidence
python -B -m unittest plugin_tests.test_terminal_security_epoch plugin_tests.test_release_audit -v
python -B -m unittest plugin_tests.test_native_convergence_epoch -v
python -B scripts/security-audit-local.py inventory --root .
python -B scripts/security-audit-local.py sandbox-regressions --root .
```

The first command refuses an existing output directory and returns nonzero for
failed or skipped mandatory assertions. `receipt.json` includes every selected
test, source hashes, exact command, host/runtime, outcome, family limitations and
the independent enterprise gate. The scanner returns INCONCLUSIVE even when its
bounded inventory completes. It is not a comprehensive vulnerability analyzer.

## Supported execution and protected assets

The newly observed local environment is Linux x86_64, kernel 6.18.44,
glibc 2.39, Python 3.12.14. Native tools retain their separate exact pins:
OpenTofu 1.13.1, Atmos 1.230.1 and the repaired Microsoft365 1.0.0 candidate.
OpenTofu 1.10.0 and Atmos 1.199.0 remain historical reproduction profiles only.
Qualification does not transfer automatically to another version or host.

The operator controls the installed Python/dependency tree, credentials,
authority keys/store, approved executable pins and root capabilities. An
attacker can supply policy text, captures, saved files, repository contents,
model/tool requests and misleading review output. Tests include a pre-existing
hard link from an admitted root to an outside file. Another hostile process
with the same OS account can race ancestors, replace source/runtime libraries,
or rewrite the whole evidence store; this configuration is excluded from the
qualified cooperative-filesystem profile and needs an independently enforced
OS boundary before enterprise use.

Protected assets are policy identity/settings/targeting, tenant/cloud/principal
and backend identity, credentials, exact saved plans, signed one-use approval,
state lineage/serial, private execution outcomes, journal durability,
availability and inert operator presentation. A skill, repository instruction,
model response, report, approval-looking JSON or observed equality is never an
execution capability.

| Surface | Admitted contract | Excluded or missing evidence |
|---|---|---|
| Entry launcher | Operator-approved absolute Python with `-I`; trusted pinned dependencies; explicit arguments | `/usr/bin/env python3` shebang and ambient Python/shell startup are convenience launch paths, not a privileged reference monitor |
| Bash/Git Bash/PowerShell | No shipped runtime shell wrapper; proposed `.sh.txt`/`.ps1.txt` cards are inactive text. Actual Linux PowerShell 7.6.6 preview argument tests pass after rejecting its reserved `--%` binder token; unsupported smart single quotes are also rejected before preview emission | Native Windows shell startup, MSYS path conversion, Windows PowerShell 5.1/7 and ACL/reparse behavior remain unqualified; two Linux Utility-module autoload failures remain unexplained. The active smart-quote after-replay is blocked by automatic approval review; only constrained literal/rejection checks can be reported. Do not rename cards and claim protected execution |
| CLI/MCP parser | Closed commands, strict schemas, explicit host-provided roots, bounded inert inputs | Arbitrary Python imports or shell tools are trusted host authority and are not exposed by MCP |
| Repository discovery | Local bounded parser, no Git subprocesses, hooks, credential helpers, external diff or fsmonitor | Full arbitrary Atmos templates/workflows/hooks/provider configurations are rejected |
| Native tools | Exact tool/hash/configuration; minimal environment; fixed argument arrays; generated narrow component | General shell execution, arbitrary provider or HCL substitution, automatic update and registry fallback are unsupported |
| Provider worker | IP sockets denied, bounded output/deadline and per-process resource ceilings; process-group containment | AF_UNIX RPC unavailable here; broad Unix socket access, filesystem isolation and aggregate process limits need a qualified host supervisor |
| Files | Regular single-link JSON/repository inputs; symlink checks; after-open link check; atomic durable JSON and runner output transitions | Concurrent hostile ancestor/mount changes and Windows reparse points need native isolated-host evidence |
| Identity/approval | Separate explicit provider/backend identities; pinned verifier/library; signed complete operation binding; private one-use store | Live principal/RBAC/backend integration and organizational signer issuance remain external gates |
| Recovery | Started-before-dispatch records; durable outcomes; readback reconciliation without blind retry | Restoring state does not restore infrastructure; local locks do not fence other Graph writers |
| Evidence | Raw negative results, hashes and private execution records | Same-host hashes are not a trusted external anchor or proof against host-owner rewrite |

The protected child environments omit BASH_ENV, ENV, exported functions,
PYTHONPATH/PYTHONSTARTUP, loader overrides, Git/Atmos/OpenTofu override variables
and ambient credentials. Do not infer that sanitizing a child can undo startup
code already executed by a compromised parent shell/interpreter. On an approved
POSIX host, launch from a trusted parent using its absolute Python path and
`-I`; keep the parent credential environment empty for local qualification.

## Verified changes and their limits

1. **Shared inode selection.** A model could choose an in-root hard link to an
   outside review graph; actual stdio MCP returned that graph's private canary.
   MCP now rejects multiply-linked regular paths. JSON and repository readers
   repeat the link-count check on the opened descriptor. A corresponding
   release-builder variant copied outside bytes into an allowlisted archive;
   it now checks single-link identity before and after reading. Legitimate
   spaces, quotes, Unicode and leading-dash filenames remain supported.
2. **Escaped descendants.** A child could use `setsid` or `setpgid`, outlive the
   supervisor and write after success, timeout, cancellation or output limit.
   The provider seccomp filter denies those calls after the parent establishes
   its supervised session. Ordinary provider-style child spawning remains
   available. This fixes process-group escape; it does not create a full OS
   sandbox or bound the aggregate number of child processes.
3. **Acknowledgement before namespace durability.** JSON persisted file data
   and renamed it without syncing the directory. Runner graph outputs and
   lock paths had related omissions. JSON now syncs the rename and directory
   entries it creates. Runner outputs/locks and wizard/cohort locks sync their
   namespace transitions; failed syncs cannot report successful completion.
   Tests observe syscall ordering and inject failures. No destructive power
   interruption was performed and filesystem/hardware durability assumptions
   remain explicit.

The evidence archive contains fail-before logs, passing regressions,
independently authored stdio/process probes and the reviewer's results.
The final independent persistence probe holds 10/10 invariants on repaired
source and 2/10 on original source, including release-reader link races,
capture descriptor cleanup and wizard/guided lock sync failures. This remains
controlled syscall-fault evidence, not a physical power-loss experiment.
The initial default-Python security replay lacked `jsonschema`; its failures
are retained. The hash-verified pinned runtime was then used. One early
hardlink test had an assertion-harness error, and one independent graph fixture
was invalid; those records remain visible beside the corrected tests.

The connected local OpenTofu fixture has separate fixed `second_plan` and
`second_show` operations. They retain `saved.tfplan` and write only
`second.tfplan`/`second-plan.json`. Verification requires unchanged original
request/plan bindings, stable state bytes/lineage/serial, and an actual native
no-change plan. Resume re-derives JSON with `show` and compares persisted
evidence; it never reapplies or replans. Interrupted second-plan output is
inspected and retained. The 40-test local regression run includes seven new
convergence/process-evidence cases and the inherited protected suite. This
proves output-only local fixture behavior, not Microsoft365 provider or Graph
convergence. Callers still separately verify the execution journal.

## S01–S08 acceptance mapping

`security/security-acceptance.json` records exact implementation hashes,
assertion IDs and raw evidence references for all eight tasks and sixteen
attack families. Its local assertion results do not waive the external gates.

| Requirement | Implemented/executed evidence | Acceptance still required |
|---|---|---|
| S01 Launch chain | Static launch/subprocess inventory; no-Git-process adversarial repository test; fixed native argument arrays | Native approved parent shells and native Windows launch chain |
| S02 Command/environment controls | Literal unusual paths; environment inheritance probe; tool/configuration substitution refusal; schemas and exact argv | Windows argument semantics and complete deployed process envelope |
| S03 Files/network/resources | Hardlink/symlink regression and variants; malicious pagination/redirect fixtures; timeout/output/cancel/descendant probes | OS filesystem/Unix-socket containment, aggregate process limits, native provider RPC, live network policy |
| S04 Presentation/approval | ASCII-safe JSON output containing OSC/CSI/C1/bidi/CR/backspace payloads; real signature and plan-substitution checks | Actual supported terminal/clipboard instrumentation and organization-issued approval |
| S05 Change coverage | Actual apply_patch CLI, redirection/heredoc, sed, Python, Node, generator, rename, offline authored npm package install and lockfile change; independent before/after content and inode snapshots account for all 13 changed files in the bundled scanner | Native editor/host hook integration, additional language analyzers and third-party installer effects |
| S06 Logs/auditors | Secret-safe evidence/representations; forged completion does not establish execution; independent reviewer challenged fixes | External trusted anchoring, organizational log retention/access and real reviewer/grader attack qualification |
| S07 Composed attacks | TERM-01–16 receipt links actual selected assertions; stdio MCP hardlink→private-canary and child detach→late-write before/after effects | Full native privileged workflow and each explicitly listed family gap |
| S08 Hosts/operations | Local Linux source and artifact replay; below operational procedures | Native Windows/PowerShell/Git Bash/macOS if advertised; full installer/update host run; AppSec and authorized tenant pilot |

The current AF_UNIX provider test preserves its explicit prerequisite skip.
The isolated `bwrap --unshare-all` regression attempt failed with
`bwrap: open /proc/8/ns/ns failed: No such file or directory` in this epoch.
Its exact arguments, exit code and stderr are in `security/sandbox-attempt.json`.
No alternate namespace or transport was used to evade that restriction.
Independent local tests continued, including real process filters and signed
approval mechanisms. Those are weaker, accurately labeled evidence.

`security/change-coverage/receipt.json` preserves all nine actual write
mechanisms, command results, tool hashes and before/after device, inode,
link-count and content records. The offline npm fixture has no third-party
dependencies; `--ignore-scripts` prevented its deliberately supplied preinstall
marker. Its installed subtree was explicitly inventoried because the generic
source scanner excludes `node_modules`. No changed-file omission or forbidden
marker was observed. This establishes snapshot accounting for those operations;
it does not establish editor-hook coverage or absence of vulnerabilities.

**Unresolved workspace restart/replan observation.** Retained PTY runs showed
a leftover session lock after successful exit and, in a later replan, old
plan-receipt bytes despite a new operation ID. Instrumented workspace and
`/tmp` reruns subsequently passed. The cause remains unproved; successful
non-reproduction does not close this credible durability/recovery gap. It is
tracked separately in `security/findings-final-v13.json`, with the original
negative artifacts and replay continuation. Do not attribute it to the four
repaired local findings or treat syscall-fault tests as its root-cause proof.

## Supply-chain tool disposition

No new security plugin or hosted scanning service was adopted or given project
content. `security/tool-dispositions.json` records which primary references were
read and which exact executable/license/dependency checks remain incomplete.
Mutable documentation is not a pinned executable audit.

| Candidate | Reviewed boundary/effect | Disposition |
|---|---|---|
| [Guardian](https://github.com/semgrep/guardian/blob/main/CHANGELOG.md) | Changelog describes first-use scanner downloads, background updates, scan requests, credentials/telemetry and host-specific change reporting | Reference only; no installation, authentication or project disclosure; no approved artifact pin |
| [just-bash](https://github.com/vercel-labs/just-bash/blob/main/THREAT_MODEL.md) | Host custom commands/filesystem/fetch remain trusted; interpreter is not a native provider VM | Not adopted; its [hardlink advisory](https://github.com/vercel-labs/just-bash/security/advisories/GHSA-g5pf-mh4h-h655) identifies affected `<3.3.0`, patched `3.3.0`; used as variant-search reference only |
| [Tracekit](https://github.com/LoopGlitch26/Tracekit) | Fork of Cygnux-Labs/Tracekit; MIT; installer can modify host hooks; transcript collection and observer/report are separate trust boundaries | Reference only; no hook install/listener/transcript export; an unanchored hash chain is insufficient |
| [Cisco MCP Scanner](https://github.com/cisco-ai-defense/mcp-scanner) | Apache-2.0; static/YARA mode differs from API/LLM, package download/execute and hash-lookup modes | Not adopted; no API transmission or server startup; exact revision/dependency audit is required before any future execution |
| ShellCheck/PSScriptAnalyzer/Gitleaks/Semgrep CLI | Not installed in this environment | NOT_RUN; no clean-scan claim, no privileged package install |
| Bundled `security-audit-local.py` | Inspected bounded read-only Python AST triage and explicit coverage gaps | Executed; latest recorded snapshot has 1,195 files/72 candidates/12 explicit gaps, INCONCLUSIVE; exact source hashes are in `security/static-inventory-final-v2.json`, corrected complete disposition accounting in `security/static-triage-final-v3.json` |
| Bandit 1.8.6 / detect-secrets 1.5.0 | Hash-verified wheels, license files and dependency pins inspected; private snapshot, clean environment and kernel network/process-creation denial | Actual Bandit CLI: 85 rule candidates, zero parse errors. Secret detector CLI fork was denied; unmodified sequential scanner API produced 146 candidates. Independent source triage and positive controls retained in `security/external-scans`; neither scan certifies absence of vulnerabilities or credentials |
| Other addendum leads | Detection generation, offensive suites and vendor marketing do not supply this product's deterministic controls | Reference/excluded from runtime; unresolved pins/licenses/effects block adoption, not independent product tests |

## Concrete host and enterprise continuation

**Host owner:** provide a disposable approved Linux x86_64 test host with the
exact package, pinned dependencies and tool hashes. Run clean archive verification,
the TERM harness, existing native adoption/provider/locking labs and the full
suite. Require provider AF_UNIX RPC to execute, rather than skip. Observe denied
out-of-root reads/writes, forbidden Unix sockets and destinations, aggregate
process/memory/output limits, cancellation and loss of the parent process.
Repeat success and failure with actual native binaries. A bypass flag that
disables the product's IP denial is not a permitted continuation.

**Windows owner, only if Windows support is sought:** stage the exact package in
a disposable account with pinned Python/dependencies. Record OS, filesystem,
Python, Git Bash/MSYS and PowerShell build/hash. Use `pwsh -NoProfile
-NonInteractive -File` with a fixed reviewed wrapper and literal argument arrays;
first prove that importing the package and basic CLI/wizard work. The current
provider route deliberately rejects non-Linux platforms. Implement/qualify a
native protected adapter before attempting provider acceptance. Exercise
profiles, exported environment, Unicode/case collisions, leading dashes,
quotes, junctions/reparse points, ACLs, cancellation and child cleanup. Do not
report a Linux simulation as Windows evidence or relax execution policy.

**AppSec and execution-service owner:** review all open gaps in the TERM receipt,
source-pinned findings and deployment architecture. Keep authority issuer and
private key separate from the worker/model. Verify replay-store durability,
key revocation during execution, limits, network broker, credential handling,
and external audit anchoring. Record an accountable owner and approval date;
the LLM leaves these unassigned. Any credible unresolved high-impact path,
failed mandatory control or absent mandatory evidence blocks release.

**Tenant/backend owner:** approve exact public-cloud tenant, provider principal,
backend principal/subscription/storage/container/blob, policy IDs, group/filter
references, permitted changes and stop conditions. Start with a disposable
narrow Windows Settings Catalog choice-setting policy. Existing public commands
support read-only `target authenticate` with explicit inherited secret FDs and
network-denied provider operations. A complete live execution adapter and Azure
backend integration remain implementation gates; there is no honest live-apply
command in this artifact. Do not remove the network filter to manufacture one.

Once that separately reviewed adapter exists, capture immutable IDs and every
settings/assignment/exclusion/filter fact independently; import; perform refresh
and no-change planning; bind one exact saved change to signer, principal/backend,
state revision and all hashes; apply once; capture actual outgoing requests;
read back both policy and assignments; prove second-plan convergence. Inject
only tenant-owner-authorized failures. Missing pages, changed identity or state,
lease loss, output/receipt failure or revoked approval must stop execution.

## Monitoring, rotation, incident response and recovery

Monitor refused identity/binding changes, incomplete inventory, approval replay,
expiry/revocation, process resource/timeout events, lock loss, partial or unknown
outcomes and receipt-write failure. Record operation IDs, bounded event types,
hashes, UTC times and status; exclude tokens, secret-bearing settings, raw state
and full model/tool prompts. Retain raw sensitive artifacts only in the private
operator evidence store, with organization-defined retention/access rules.

For suspected credential exposure: stop new operations, revoke the relevant
application credential through its authorized identity owner, invalidate pending
approvals and rebind provider/backend identities separately. Replace the
credential using the same explicit protected channel; never silently fall back
to CLI/environment identities. Preserve private audit evidence before cleanup.

For interruption, failed durable writes, lost response or uncertain mutation:
preserve the attempt, state revision and lock; make no automatic retry. Obtain
authenticated readback and compare policy and assignment facets independently.
Classify unchanged, desired-state-observed, partial, diverged or unknown. Desired
state alone does not prove the approved plan executed. Replan and obtain a fresh
one-use approval only after the authorized operator resolves the uncertainty.
Never restore a state backup as a substitute for remote reconciliation.

For install/update/uninstall: verify the archive manifest in a fresh private
directory, use hash-locked offline dependencies, run `doctor` and the exact
artifact's tests, then perform an operator-controlled installation switch. Keep
the replay/revocation store across upgrades. Do not merge project instructions,
execute repository hooks, or overwrite shell profiles. Uninstall removes only
owned package files; preserve evidence and revoke credentials separately.
Repeat qualification after any source/tool/provider/model/permission change.

## Native toolchain advisory boundary

Static `go version -m` inspection of the historical epoch binaries found Go 1.24.3
in OpenTofu 1.10.0, Go 1.25.0 in Atmos 1.199.0, and Go 1.24.1 in tfsec 1.28.14.
The provider compiler upgrade does not update these binaries. Exact binary
hashes, effective dependency replacements, OSV requests/responses and 240
unique advisory records are retained in
`security/external-scans/native-buildinfo/`. Advisory aliases are not separate
vulnerabilities, and a module match is not function reachability evidence.

The historical OpenTofu 1.10.0 release has upstream reports of provider-cache symlink
writes and malicious Git download URL reads, among other issues. The protected
local executor admits only generated output-only configuration, local state,
fixed filenames and commands; it rejects provider/module blocks and provider
cache entries. The Atmos helper admits an inert subset and uses fixed describe
arguments with functions/templates disabled under the network/process guard.
These exclusions narrow the local experiments; they do not qualify arbitrary
repository initialization, remote module acquisition, workflows or live
backends. Replacement tool pins require their own provenance, build-info review
and complete native regression evidence before adoption.

The separate Azurite exercise uses authored input and a scoped cooperative
loopback proxy. It is not the product execution boundary and does not provide
kernel network containment of a compromised binary. Its results do not enlarge
the protected executor's authority. `SEC-GAP-NATIVE-TOOLCHAIN` remains an
enterprise release gate; consult the current findings ledger and native-tool
disposition before selecting an execution profile.

The current narrow local profile separately pins OpenTofu 1.13.1
(`a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a`)
and Atmos 1.230.1
(`f3b5b42e897a2778678cc1231e7a4e2476773bc61ea2af225586dc4e96408802`).
`toolchain-upgrade/qualification.json` binds their verified release signatures,
source revisions, connected 17-stage local journey and independent helper
checks. Legacy pins remain reproduction profiles. The new binaries still have
advisory module matches whose reachable entrypoints need review; module counts
and successful local journeys do not establish generic tool safety. Historical
native timings do not transfer to these versions.

The verified source build of `golang.org/x/vuln` v1.8.0 was run against all
three current binaries using a complete pinned offline Go vulnerability database.
Its local-build version string is `v0.0.0`; source provenance records identify
the actual scanner revision. All three binaries yielded zero extracted package
symbols, so the scanner fell back to conservative module matching. Its
function-shaped wildcard records do not establish linked-symbol reachability.
`security/external-scans/govulncheck/CONCLUSION.json` preserves the raw scans,
metadata extraction and correction of the initial provisional interpretation.
The separately recorded provider main-package dependency graph excludes the
OpenPGP package implicated by its remaining Go advisory. That source-profile
observation is not symbol extraction from the stripped binary, a review of
tool/test dependencies, or a zero-vulnerability claim. OpenTofu and Atmos
matched entrypoints remain unqualified outside the narrow admitted operations.

The final provider binary is SHA-256
`415097131c64a47c8435ce9528d050382996cfa4bed38d0960548f160a0b0dd3`,
built from the repaired resource with Go 1.26.8 and recorded dependency updates.
The final in-process resource test has 12 top-level groups and 55 records
including nested subcases, all passing. Default native schema/validate attempts
failed. A separate explicit lab trace profile captured the actual provider's
Unix listener `operation not permitted` errors; initialization succeeded.
`provider-lifecycle/native-smoke-trace.json` and its raw logs substantiate this
host restriction. Full native RPC lifecycle and live-service qualification
remain blocked; no alternate transport was used to bypass it.
