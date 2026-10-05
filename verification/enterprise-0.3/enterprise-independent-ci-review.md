# Independent CI review

No reproducible blocking finding remains in the reviewed CI additions. This conclusion covers the exact files in `enterprise-independent-ci-review-snapshot.json`, not enterprise production acceptance.

Review was read-only. No product file was edited, no commit was made, and the existing main independent-review report was left unchanged.

## Scope and result

Reviewed `.github/workflows/validate.yml`, `research/enterprise-ci/check-archives.py`, their regression tests, CI handoff/source records, exact application-wheel locks, and directly relevant build/verification interfaces. The inspected workflow is validation-only: hosted Ubuntu, `contents: read`, no retained checkout credentials, cloud secrets, OIDC grant, privileged pull-request trigger or deployment consumer. Artifact upload remains a candidate-evidence action and cannot reverse an earlier job failure.

The Bash steps use `-euo pipefail`. Full-verifier gates check both process exit status and a strictly typed complete receipt; extracted-source verification uses the same gate. Archive verification checks outer build-receipt hashes, ZIP CRC, member paths/types/duplicates, complete member hashes and runtime/source byte agreement before a fresh extraction. The subsequent extracted-source tests, runtime doctor and byte-identical rebuild are actual configured commands, not a claim that GitHub has run them.

All three action commits were independently compared with the acquired primary-source clones and their version tags. Twelve source-ledger file hashes match those clones. The published Node 24/minimum runner and GHES artifact restrictions in the runbook agree with the inspected upstream READMEs. These checks do not authenticate publisher signatures or audit every bundled action dependency.

Application dependency installation uses the exact ten reviewed wheel hashes, verifies the wheelhouse, installs from it offline into a fresh virtual environment and runs `pip check`. The documentation correctly distinguishes that integrity boundary from the hosted runner, Python distribution, bootstrap pip and action dependency trust chains.

## Independently executed evidence

- `python -m unittest plugin_tests.test_ci_contract -v`: **7 passed**, zero failures, errors or skips. This includes actual Bash failure-boundary scenarios and ZIP negative cases; it is not the complete application test suite.
- Eight bounded `check_release` probes: the valid archive pair was accepted with `production_approved: false`; seven mutations/conditions were rejected. Cases covered changed outer digest, wrong receipt count, runtime/source mismatch, pre-existing output, symlinked output parent, duplicate manifest entry, and a runtime-only path-prefix collision mutation. The prefix-collision case also differed from source and therefore does not independently establish an extraction collision preflight. The existing-output canary was preserved.
- The independent probe outcomes are recorded in `enterprise-independent-ci-probes.json`; its hash is included in the review snapshot.

No finding was sent for repair because these checks did not reproduce an in-scope defect. The implementation owner's prior 0.2.2 archive-verification receipt and source-selection records were inspected as reported evidence; they are not relabeled here as independently repeated final-release verification.

## Limits and handoff

No GitHub workflow/action execution, native host installation, cloud operation, branch protection change, artifact upload or final enterprise approval occurred in this review. Local YAML/Bash/tests do not establish observed hosted-CI behavior. The first authorized hosted run and repository policy configuration remain the operational acceptance described in `docs/CI.md`.

The root integrator must retain `.github/workflows/validate.yml` and `research/enterprise-ci/check-archives.py` in the explicit source-release inventory because the extracted `test_ci_contract` suite uses both. Final release/extracted-suite evidence belongs to root integration; this review does not infer it from source-only tests. The archive receipt and source inventory are consistency inputs, not signatures or protection from a process able to replace the release and its receipt. Filesystem handling assumes the disposable cooperative runner described by this validation workflow; this is not an adversarial shared-filesystem sandbox claim.
