# Complete Intune / Atmos / Wally handoff

The complete original repository is now available as ONE release attachment:

[Download Intune_Atmos_Wally_Repository_All_Threads.zip](https://github.com/nsahmed23/neon-commons/releases/download/intune-full-handoff-20261004/Intune_Atmos_Wally_Repository_All_Threads.zip)

[Release page and separate technical handoff](https://github.com/nsahmed23/neon-commons/releases/tag/intune-full-handoff-20261004)

Size: **1,156,114,547 bytes**
SHA-256: **5a16fc491944d1e8b73295d26ab8f4399f1156c0c7f1847e3faca7d3a68cc214**

Use the named release attachment. GitHub's automatic “Source code (zip)” contains this transfer branch, not the full repository.
The incomplete 129-part transfer was abandoned and is superseded by the full attachment; do not run the legacy restore.py or attempt to assemble the partial archive/ folder.

## Codex Cloud recovery

From the root of this branch, with Python 3 and curl, run:

```sh
curl -fL --retry 2 -o Intune_Atmos_Wally_Repository_All_Threads.zip https://github.com/nsahmed23/neon-commons/releases/download/intune-full-handoff-20261004/Intune_Atmos_Wally_Repository_All_Threads.zip
python3 intune-workbench/restore_release.py Intune_Atmos_Wally_Repository_All_Threads.zip --destination intune-recovered
```

The script verifies the fixed size and SHA-256 before extracting into a new directory. It executes no archived project code.

Read the recovered repository's README.md, WORK_THREADS.md, AGENTS.md and work/CHECKPOINT.md, then the full execution/security directives. Run its documented repository-manifest verifier before modifying the recovered tree. The additional Intune_Workbench_Technical_Execution_Handoff.md beside this README contains the user's updated continuation specification. Reconcile it against the latest source/evidence; do not restart completed repairs or substitute its reference lab for the product.

The archive includes all six SAVED engineering work threads, source, raw evidence, checkpoints, original inputs and release packages. Saved work records are not an export of private agent conversation transcripts. Preserve all recorded negative results and qualification gaps. Enterprise acceptance remains blocked; no Wally candidate was promoted. This publication changes no engineering acceptance claim and authorizes no tenant operation.

Main branch and the original Neon Commons project are unchanged. This branch is a delivery route for the separate Intune/Atmos/Wally project.
