# Work-thread index

These are saved engineering artifacts from the six work threads and parent work.
They are not reconstructed chat transcripts. Paths are relative to this repository.
No new test execution or acceptance claim is introduced by this index.

| Thread | Main records | Implementation / supporting evidence |
| --- | --- | --- |
| Wizard (`/root/wizard`) | [Engineering checkpoint](work/evidence/epoch-20261004/wizard/ENGINEERING-CHECKPOINT.json), [journey documentation](work/projects/intune/docs/JOURNEY.md) | `work/projects/intune/`; `work/evidence/epoch-20261004/wizard/`, `integrated-current/` |
| Native labs (`/root/native_labs`) | [Lab report](work/evidence/epoch-20261004/labs/REPORT.md), [catalog ledger](work/evidence/epoch-20261004/labs/catalog-ledger.json) | `work/evidence/epoch-20261004/labs/`, `azure-backend/`, `toolchain-upgrade/`, `native-smoke-observation/` |
| Performance (`/root/performance`) | [Results](work/evidence/epoch-20261004/performance/RESULTS.md), [checkpoint](work/evidence/epoch-20261004/performance/CHECKPOINT.json) | `work/evidence/epoch-20261004/performance/`, including all retained measurement attempts and separately delivered evaluator sources |
| Security (`/root/security`) | [Final report](work/evidence/epoch-20261004/security/FINAL-SECURITY-REPORT.md), [findings](work/evidence/epoch-20261004/security/findings-final-v13.json), [acceptance](work/evidence/epoch-20261004/security/security-acceptance.json) | `work/evidence/epoch-20261004/security/`, `powershell-linux/`, `provider-dependency-review/` |
| Wally (`/root/wally`) | [Wally report](work/evidence/epoch-20261004/wally/WALLY-REPORT.md), [acceptance ledger](work/evidence/epoch-20261004/wally/acceptance-ledger.json) | `work/projects/wally/`; `work/evidence/epoch-20261004/wally/`, `transfer-replay/`; actual trial inputs/outputs and retained negative results |
| Independent review (`/root/independent_review`) | [Archive review](work/releases/delivery-final/INDEPENDENT-DELIVERY-REVIEW.json), [staging review](work/releases/delivery-final/INDEPENDENT-STAGING-REVIEW.json) | `work/evidence/epoch-20261004/independent-review/`; replay scripts and records in `work/releases/delivery-final/` |
| Parent integration / provider (`/root`) | [Results](work/docs/RESULTS.md), [checkpoint](work/CHECKPOINT.md), [requirements](work/docs/T00-T13-ACCEPTANCE.md), [final delivery receipt](work/releases/delivery-final/DELIVERY-RECEIPT.json) | `work/provider-source/`; `work/evidence/epoch-20261004/provider-lifecycle/`, `provider-engine-pin/`, `packaging/`; `work/scripts/` |

## Historical and continuation material

- `inputs/Intune_Atmos_Wally_LLM_Continuation.zip`: exact original upload; original
  archives, original directives and inherited qualification evidence remain inside.
- `work/checkpoints/`: checkpoint 01 through 04, preserved as created.
- `work/releases/`: all canonical final deliverables, including exact source and
  runtime ZIPs, raw evidence, both provider binary archives and final proof ZIP.
- `work/docs/REPLAY-EPOCH.md`: replay and environmental prerequisites.
- `work/projects/intune/docs/OPERATIONS-EPOCH.md`: monitoring, credential lifecycle,
  incident response and recovery procedures.
- `provenance/SCOPE.json`: precise consolidation scope and exclusions.

Read the final ledgers before acting on an earlier checkpoint: draft status and
intermediate findings are preserved, rather than rewritten to look final.
