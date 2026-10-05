# Implemented validation CI — E09 engineering work

The actual workflow is `.github/workflows/validate.yml`; the operational handoff is `docs/CI.md`. This work adds validation, not deployment or production approval. It has not been enabled or run on GitHub.

The workflow has read-only repository permission, no retained checkout credentials, no cloud authentication, no `pull_request_target`, no privileged deployment consumer, fixed hosted Linux/Python scope and exact upstream action commit pins. It acquires hash-locked wheels, verifies them before installation, runs complete local/core tests and CLI journeys, builds candidates, verifies/extracts archives, tests the extracted source/runtime and checks byte-identical rebuilding. Every relevant failure propagates. Candidate evidence is retained for seven days when an authorized host later runs it.

`source-ledger.json` records verified tag-to-commit mappings and inspected raw-file hashes from the primary action repositories. `python-release-selection.json` separately records the pinned upstream Python distribution manifest that lists CPython 3.12.14 for Ubuntu 24.04 x64. Node 24/minimum runner requirements and the artifact action's lack of GHES support are explicit in the runbook. Neither action execution nor Python distribution download is claimed here.

## Executed checks

```text
/workspace/scratch/26b6d364cfda/plugin-clean-venv/bin/python -m unittest plugin_tests.test_ci_contract
```

At the implementation checkpoint, **7 tests passed**, with zero failures/errors/skips (`green-tests.txt`). Those tests include twelve negative workflow mutations, Bash syntax checks of every actual run step, five executed full-verifier shell scenarios, and ZIP controls/tampering/unsafe paths/symlinks/duplicates. The shell scenarios replace the verifier process at its boundary; they test actual workflow failure handling, not a new run of the full application suite.

The test suite first failed seven assertions because the workflow/helper were absent (`red-tests.txt`). A later boolean-count receipt counterexample failed before strict count typing was added (`red-receipt-types.txt`). No environment failure was relabeled as a passing CI run.

The archive helper also ran against the intact previously built 0.2.2 archives. It verified both outer hashes, CRC/member safety, **920 listed member hashes**, identical shared runtime/source bytes and fresh extraction (`prior-release-archive-check.json`). This validates the helper against actual existing packages; it does not constitute qualification of the final new archive. Root performs that final integration after updating the reviewed inventory.

The workflow and helper are independently reviewed before handoff. Final branch-wide/full-extracted-suite evidence belongs to root integration, so this workstream does not duplicate or claim those runs.

## Open acceptance work

No GitHub-hosted run, action sandbox, artifact upload, branch protection/ruleset, support-owner assignment, publisher signature verification, organization approval or cloud execution happened. The GitHub runner/Python/action bootstrap chain has trust and update requirements beyond the hash-locked application wheels. GHES/self-hosted platforms are outside this workflow's declared support. E09 remains open for observed CI hosting and enterprise operational acceptance; no green placeholder gate is introduced.
