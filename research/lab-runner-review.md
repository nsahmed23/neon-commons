# Independent review of the native lab runners

Reviewed the new adoption and locking qualification runners, their fixtures,
guides and regression tests against source baseline
`539f9421bf3ab890b0b0ced9d645e6896fbbc02a`. This reviewer did not implement the
runners or their fixes. Review covered command construction, source acquisition
boundaries, process ownership, cancellation, output ownership, native assertions,
and the distinction between a local simulation and production evidence.

The findings below have been repaired in the reviewed source. No further
blocking defect was found within the fixed, cooperative-workspace lab scope.
This is not approval of a general-purpose infrastructure executor.

## Findings and repairs

| Finding | Initial defect | Repair and verification |
| --- | --- | --- |
| L01 — Owned background process cleanup | The locking measurement started replacement applies without a `finally` cleanup. A failed lock observation or later assertion could leave its owned apply running after failure. | A context manager now terminates and reaps its owned live process group on exit. The implementer supplied the red regression; this reviewer independently injected an observation failure using a harmless owned sleeper and confirmed it was reaped. The real-process regression passes. |
| L02 — Cancellation and attempt evidence | Adoption cleanup handled only `TimeoutExpired`; interruption could leave its new-session child alive. A timeout also escaped before the command was recorded. Locking foreground execution had an analogous interruption gap, and measurement records existed only after a successful measurement pass. | Adoption catches interruption while waiting, terminates its owned group, records the outcome and output hashes, and then raises. Its top-level interruption receipt returns 130. Locking cleans up foreground commands on exceptions, checkpoints started/completed/error measurement attempts, and records interrupted failure. Adoption's real Ctrl-C and timeout regressions pass. |
| L03 — Output symlink traversal | Locking accepted a new output directory below a symlink parent. The reviewer reproduced `alias/run` creating `real/run`. | Locking requires a canonical path, rejects existing output, and excludes the plugin/upstream trees. Its symlink regression passes. Adoption already rejected symlink traversal and source containment. |
| L04 — Reopening validated source | Adoption copied its initial plain-OpenTofu HCL from the live source fixture after creating and validating its local snapshot. A concurrent source edit could change bytes used for execution after qualification. | The initial project now copies from the validated local repository snapshot. The guide explicitly limits this to a cooperative workspace. |
| L05 — Executable snapshot | Locking checked the supplied OpenTofu path, then reused that external path throughout execution. Concurrent replacement could invalidate the receipt's fixed-byte claim. | It now copies verified bytes into the fresh private output, rechecks that copy, and directs the wrapper to it. Adoption already used validated private copies. |
| L06 — Bounded validation | Locking read arbitrary source/executable sizes before rejecting their hashes. Adoption traversed and hashed extra fixture members before comparing the fixed inventory. | Locking uses a pre-size check and bounded read: 1 MiB per source member and 128 MiB for the executable. Adoption rejects unexpected tree members before hashing and bounds each accepted fixture member to 16 KiB. Oversize/extra-member regressions pass. |

Adoption also records the runner's own SHA-256 in its result, in addition to
native binary and fixture hashes. These hashes establish byte consistency;
they are not authenticated approval records.

## Independent checks

The final focused unit invocation passed **21 tests**, with no failures, errors
or skips:

```bash
python -m unittest plugin_tests.test_adoption_lab plugin_tests.test_locking_lab -v
```

These include actual harmless child-process interruption/timeout checks;
fixture/hash rejection; existing-output preservation; symlink rejection;
credential/configuration environment exclusion; duplicate, replacement and
extra-deletion plan counterexamples; and state identity, lineage and serial
mutations. Source-token checks alone were not treated as process or isolation
evidence.

The reviewer also invoked the adoption runner's guard with an explicitly
authored Python socket-creation probe. It returned `PermissionError` with errno
1. No connection was attempted. This supports the observed mandatory seccomp
socket denial; it does not establish filesystem isolation.

The reviewer inspected native adoption run `adoption-lab-run-05/result.json`:
**18 assertions and 25 native commands passed**. All **113** entries in its
artifact-hash inventory were independently recomputed without mismatches. This
run predates the final input-bound/runner-hash additions, so it is not presented
as execution of those later bytes. The release coordinator is responsible for
the final current-source and extracted-source execution receipts.

The reviewer inspected `lab-execution/locking-final/receipt.json`: **8 upstream
tests passed, zero failures/errors/skips, and one test was deselected**. It
records OpenTofu 1.10.0 and pytest 8.4.2. The receipt's SHA-256 is
`c1086cdeeed2596c741ebb73e3d583023d85d45b83eafc8fd1730ed7d6e04270`.
That native run predates only the final bounded-input guard and cancellation
wording. Its original receipt was retained without alteration; the separate
review addendum records that timing.

## What the native evidence supports

The locking runner copies and verifies the actual upstream Python test/helper
bytes from commit `86b69d2292485d179698f5b9bf648a29f935e216`. Its independently
authored learner solution changes the fixture's engine requirement from
Terraform `>=1.15.0` to OpenTofu `=1.10.0`, chooses a local backend path and a
20-second sleeping provisioner, then derives observation outputs in a separate
measurement pass. The unchanged upstream tests repeat the experiment. The
ninth test checks static S3 documentation answers and is explicitly excluded;
no S3 behavior is claimed. This is not a dsoxlab CLI run or a Terraform 1.15
qualification.

The adoption runner executes actual Atmos/OpenTofu commands with built-in
`terraform_data`. The assertions compare full local state fields, exact
resource-action sets, IDs, lineage, serial, included/excluded targeting values,
native versus plugin variables, named saved-plan application and stale-plan
rejection. The intact-state relocation and separate identity-only import are
correctly distinguished. Populating the imported object's input must expose an
update instead of being called no-change adoption.

There is no remote service behind `terraform_data`. A desired/current setting
difference does not qualify service-side drift detection, Intune refresh,
assignment replacement/merge, pagination or partial update recovery. The native
runner is a qualification script, not the plugin's protected production action
adapter. Its successful local apply must not be counted as authenticated
approval, tenant/backend targeting, remote locking or production plugin
completion.

## Operational limits retained explicitly

The adoption child environment omits inherited credentials and configuration,
and native children require a socket/connect-denying filter. Neither runner
provides a filesystem sandbox. The locking runner also provides no network
sandbox; its reviewed fixed payload uses only local built-in resources.

The unchanged upstream locking tests start separate-session subprocesses.
Canceling the outer pytest process does not guarantee immediate cleanup of
every such grandchild. Each reviewed native command remains wrapped in a
60-second timeout, with a five-second termination grace period; the only
authored provisioner sleeps for 20 seconds. This documented cancellation bound
is an operational limitation, not universal descendant-cleanup qualification.
The reviewed runner's directly owned measurement processes do have exception
cleanup.

The labs accept fixed source and tool bytes, rather than arbitrary user
repositories. Hostile concurrent same-user filesystem mutation, arbitrary
provider execution, Windows behavior and real cloud operations remain outside
this review.

## Follow-up: command transcript integrity

After the initial review, the release coordinator detected two command-log hash
mismatches in `adoption-lab-final`, despite its 18 semantic assertions passing.
The original evidence was preserved. The cause of those particular mismatches
was not established, so they must not be retrospectively attributed to the
mechanism below or counted as a fully verified run.

**L07 — Transcript finalization and final status (P2, repaired).** A subsequent
deterministic regression demonstrated that a descendant could retain the direct
stdout file descriptor after its command leader exited, then append bytes after
the runner had hashed the transcript. Another counterexample showed that a
modified transcript could still accompany a final `passed` report. These are
evidence-integrity defects even when resource/state assertions succeed.

The repaired runner captures stdout and stderr through parent-owned pipes,
drains both to EOF within the command deadline, and limits aggregate captured
output to 2 MiB. Only the parent writes and fsyncs the transcript files; the
native descendants never receive writable transcript-file handles. Timeout,
interruption and output-limit outcomes remain failed attempts with explicitly
incomplete capture. The final report rechecks every command transcript hash,
and the public entrypoint returns a failure code if that report is failed.

This reviewer read the new capture, final-report and exit-status paths and ran
the complete adoption test module independently: **18 tests passed**, including
four added regressions for delayed descendant output, bounded output,
transcript mutation and public exit status. No new blocking issue was found in
these changes within the documented cooperative-workspace scope.

The reviewer independently checked the fresh native run
`adoption-lab-final-captured`: it reports **18 assertions and 25 native commands**
passed, and all **113 artifact hashes** match. Its recorded runner hash equals
the current reviewed script:
`ca8a79f60e30ac95e5ad97d78e8f38273d88255792d7fc2f9d40c338e37ef744`.
This new run supplies current-source evidence for the repaired capture path;
it does not erase the earlier mismatches or broaden the lab's production scope.
