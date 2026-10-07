# Intune / Atmos / Wally R2 continuation — 0.7.0

The tested Intune source is publicly available at commit [`74130d0db99febf2f41cf4f4ebe2920a5d4dffb7`](https://github.com/nsahmed23/neon-commons/commit/74130d0db99febf2f41cf4f4ebe2920a5d4dffb7), on the separate `intune-workbench-source-0.7.0` branch. The unrelated Neon Commons main branch is unchanged.

Read the preserved [checkpoint](work/CHECKPOINT-20261005-R2.md), [execution sequence](work/docs/EXECUTION-SEQUENCE-20261005-R2.md), and [acceptance ledger](work/docs/CONTINUATION-ACCEPTANCE-20261005-R2.json). These copies retain the exact R2 bytes; publication does not update their engineering claims.

## Exact qualification evidence

- [Strict result: 1,141/1,141, zero failures/errors/skips](work/evidence/epoch-20261005-r2/milestone-0.7.0/strict-suite/result.json)
- [Complete raw strict test log](work/evidence/epoch-20261005-r2/milestone-0.7.0/strict-suite/test-log.txt) and [executed command](work/evidence/epoch-20261005-r2/milestone-0.7.0/strict.command.json)
- [Final candidate qualification](work/evidence/epoch-20261005-r2/milestone-0.7.0/QUALIFICATION.json), [archive/commit binding](work/evidence/epoch-20261005-r2/milestone-0.7.0/artifact-binding.json), [reproducibility](work/evidence/epoch-20261005-r2/milestone-0.7.0/reproducibility.json)
- [Actual maintenance CLI/PTY journey](work/evidence/epoch-20261005-r2/milestone-0.7.0/journey/receipt.json)
- [Independent expanded capture/history/health CLI journey](work/evidence/epoch-20261005-r2/capture-store/cli-run-081411/receipt.json)
- [Raw-evidence file inventory with hashes](prominent-raw-evidence.json) and [independent publication audit](publication-audit.json)

The source package is locally qualified in its recorded Linux laboratory scope. Native schema/credential-free validation does not qualify live provider lifecycle. Live Graph, device outcomes, additional host families and organizational production approval remain open. All historical failures and Wally negatives remain valid. No production tenant change or deployment is authorized by this handoff.

## Complete snapshot transfer

Original complete R2 filename: `Intune_Atmos_Wally_Continuation_20261005_R2.zip`.
Exact size: **2,289,864,715 bytes**.
SHA-256: `7117ab67ce6ae1912aa2c984774e6370216f3eb28be1510d0c6814cb4c295d0b`.

[Snapshot receipt](CONTINUATION-SNAPSHOT-R2-RECEIPT.json) describes 52,165 regular files, five literal symlinks and 11,522 directories. All six saved threads, original inputs, source, historical and new evidence are preserved. The historical three unexpected temporary files remain unresolved.

**Complete snapshot transfer published as 24 exact Git byte chunks.** The dedicated data branch is `intune-r2-snapshot-data-20261007`, pinned data commit `57131e285b87abd11df0b0196866d22db2a615e4`. The [distribution manifest](R2-DISTRIBUTION-MANIFEST.json) lists every immutable public raw URL, byte count and SHA-256. All byte chunks were pushed successfully; [fresh anonymous whole-archive reconstruction passed](public-download/PUBLIC-DOWNLOAD-RECEIPT.json), including an independent final size and SHA-256 check. No archive payload was omitted or repackaged.

Release attachment uploads returned HTTP401 through the configured connection; [that failure remains recorded](UPLOAD-BLOCKER.json). Authorized Git publication required no credential provisioning or privilege changes. The original two-part release-asset plan is superseded by this complete 24-chunk transfer. No GitHub automatic Source code ZIP is the complete handoff. Use the manifest and restore helper instead.

[The restore helper](distribution-tooling/restore_r2.py), its [usage and limits](distribution-tooling/README.md), and [extraction precautions](R2-SNAPSHOT-EXTRACTION.md) are provided for the completed transfer. The helper verifies fixed archive/manifest pins and can quarantine the five symbolic links as inert literal text when safely extracting to a fresh directory. It is new distribution tooling; its tests are separate from the preserved 1,141 product tests.

## Downloadable exact product packages

The [runtime package](packages/Intune_IaC_Plugin_0.7.0.zip), [source package](packages/Intune_IaC_Plugin_0.7.0_Source.zip) and [archive receipt](packages/Intune_IaC_Plugin_Archive_Receipt.json) are byte-identical copies of the qualified packages. They are product packages, not substitutes for the complete six-thread snapshot.

The restoration helper also passed full extraction of the unchanged R2 ZIP and an independently implemented complete filesystem rehash: [extraction receipt](distribution-tooling/full-extraction-result.json), [independent verification](distribution-tooling/full-extraction-independent-verification.json). This does not alter the original snapshot or its historical extraction-limit prose.


## Restore the complete unchanged snapshot

```sh
curl -fL -o restore_r2.py https://raw.githubusercontent.com/nsahmed23/neon-commons/intune-atmos-wally-r2-20261007/intune-workbench/r2-20261005/distribution-tooling/restore_r2.py
python3 restore_r2.py --manifest https://raw.githubusercontent.com/nsahmed23/neon-commons/intune-atmos-wally-r2-20261007/intune-workbench/r2-20261005/R2-DISTRIBUTION-MANIFEST.json --output Intune_Atmos_Wally_Continuation_20261005_R2.zip --extract Intune-R2-recovered
```

Helper SHA-256: `d073a532a5d89bda9fe682269dae64526d1749ded0c9972323c6f4d569919dcb`. Requires Python3.10+ on POSIX/Linux/WSL; no package install or credentials. Use a fresh extraction directory. The public reconstruction receipt binds immutable handoff commit `5141cb88e1b42c3cf17922848932f3ddf77ee396` and URLs; the branch command above is convenient but the manifest itself pins every chunk to its exact data commit.
