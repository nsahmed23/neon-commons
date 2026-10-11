# C25 Linux performance qualification replay

This lane uses exact source commit `e3bdefe0b1ac0c58e46f9af3360970f8e47ae393`
and tree `0bdbdeb3556acce23c8390abb20e835184880b27`. The durable restored source
archive is 17,956,520 bytes, SHA-256
`b18dd90c742e8082fef635c08807985ba631eb7634a2e4386c307daa3527917e`;
the runtime archive is 1,520,542 bytes, SHA-256
`7ca39bc46cef9d8a699ea1885646fcecd281cd7e6677607b106267eb6a8fd84d`.
Both are under `work/releases/continuation-0.9.0-r4-c25-restored-20261011`.

The complete extracted source and runtime are respectively:

```text
/tmp/intune-c25-restored-packages-20261011/extract-source/intune-iac-source
/tmp/intune-c25-restored-packages-20261011/extract-runtime/intune-iac
```

`PREPARATION-RECEIPT.json` records independent ZIP CRC and exact typed namespace,
file bytes and directory census before/after the actual preparations. `prepare.py`
and `run-prepared.py` are evidence drivers outside the shipped application.
The original full performance grader is byte-identical to its retained R3 grader.
The original R3 timings remain evidence for their original revision.

The workload retains three samples and the preregistered wall ceilings of 2s
for startup, 5s for ordinary operations, and 15s for capacity operations; CPU
ceilings are 1.5s/4s/12s and peak child RSS ceilings are 262,144/524,288/786,432
KiB. Every gated sample must satisfy all applicable ceilings. No sample removal,
post-result change or percentile/fleet claim is permitted.

The full source route creates one-policy and eight-policy modeled collections,
seeds history explicitly in independent SQL after a real collection, exercises
history bounds, performs 1,000 fresh-process imports of distinct caller-asserted
captures, and independently checks 100-policy backup/restore. Imports 1, 100 and
1,000 are gated performance samples; the other fixture-building imports retain
their outcomes/timings without claiming that all 1,000 have the three gated-sample
contract. An unpaged 1,000-object overview's explicit byte-limit rejection is
containment, not a successful complete-inventory claim.

The runtime route uses the preserved 1,000-import database, SHA-256
`408cd5eae0bd98181be4173ef528cb36c45e65d025e37ac6bb6536497aef9f56`,
copies it privately, and creates a separately declared SQL denial/pending variant.
It checks the exact union of twenty 50-object pages, unique and setting searches,
settings, health, dictionary, references, explicit over-limit rejections and a real
Linux PTY navigation route. Original and copied database bytes must remain exact.
The grader comes from the source archive; every product command uses the runtime
archive's actual `scripts/intune-iac.py` entrypoint.

The actual attempted commands, quiet-window attestation, raw product receipts,
process-name-only snapshots, stdout/stderr, before/after package bindings and
complete evidence capsules are retained under `source-run-01` and `runtime-run-01`.
Read their RESULT/FAILURE records before making any new claim. The attempt outputs
must never be reused or overwritten. Missing old `/tmp` preparations are recorded
as unavailable; this new lane does not manufacture their receipts.

For a justified new replay, choose new output paths and recover the pinned packages
first. The following flags were checked through actual `--help`:

```sh
/workspace/intune-runtime/bin/python -B /tmp/intune-c25-restored-packages-20261011/extract-source/intune-iac-source/scripts/qualify-workbench-performance.py --prepare --output /tmp/intune-performance-new-source-attempt
/workspace/intune-runtime/bin/python -B /tmp/intune-c25-restored-packages-20261011/extract-source/intune-iac-source/scripts/qualify-workbench-capacity.py --project /tmp/intune-c25-restored-packages-20261011/extract-runtime/intune-iac --store /workspace/intune-continuation/work/evidence/epoch-20261007-r3/performance/run-01/imported-store --prepare --output /tmp/intune-performance-new-runtime-attempt
```

After an explicit coordinator confirmation that other heavy qualification,
native execution, package hashing/builds and publication are paused, execute
the lanes sequentially. Replace the quiet-window description with the actual
confirmation; elapsed time alone does not establish it.

```sh
/workspace/intune-runtime/bin/python -B /tmp/intune-c25-restored-packages-20261011/extract-source/intune-iac-source/scripts/qualify-workbench-performance.py --run --output /tmp/intune-performance-new-source-attempt --python /workspace/intune-runtime/bin/python --quiet-window 'Actual coordinator confirmation; ambient host activity remains uncontrolled'
/workspace/intune-runtime/bin/python -B /tmp/intune-c25-restored-packages-20261011/extract-source/intune-iac-source/scripts/qualify-workbench-capacity.py --project /tmp/intune-c25-restored-packages-20261011/extract-runtime/intune-iac --run --output /tmp/intune-performance-new-runtime-attempt --python /workspace/intune-runtime/bin/python --quiet-window 'Actual coordinator confirmation; ambient host activity remains uncontrolled'
```

Preserve a failed attempt and stop dependent measurements. These are Linux
fresh-process and PTY measurements with uncontrolled warm OS caches. They do
not establish real Graph latency, authenticated platform authority, native
Windows/mintty/PowerShell, endpoint effectiveness, a fleet SLA, hostile-host or
power-loss durability, organizational AppSec acceptance or production approval.
