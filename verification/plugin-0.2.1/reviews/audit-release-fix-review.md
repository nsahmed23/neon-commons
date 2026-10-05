# Independent review of release and CLI fixes

Reviewed the actual diff in `scripts/build-release.py`, the new `plugin_tests/test_release_audit.py`, and the missing-dependency exit-code change in `intune_iac/cli.py`. No implementation files were changed by this reviewer. The final `release-source-files.txt` is intentionally pending explicit parent-agent review; this review did not recursively select an inventory for the release.

The review found two reproducible defects. Both were repaired by the parent agent and independently rechecked; no remaining blocker was found in the reviewed fixes. Final release-inventory and clean-extraction validation are still integration steps.

## Findings and verified repairs

### RF01 — Medium, fixed: release output preservation during an intervening write

`main` checks whether each destination exists, but `write_archive` later opens its destination with `zipfile.ZipFile(..., 'w')`. A regular file created after the preflight is silently truncated. The receipt's `write_text` has the same check-then-overwrite pattern. Two builders sharing a destination directory can also overwrite each other's outputs.

The counterexample intercepts the call to `write_archive`, creates a regular destination containing `existing-file-created-after-preflight`, and calls the real writer. The build succeeds and the canary is replaced by a ZIP. This is a deterministic scheduling counterexample, not a claimed adversarial filesystem attack.

Verified repair: ZIP destinations now use exclusive creation (`x`), and the receipt uses exclusive file creation. Independent late-arrival tests for runtime ZIP, source ZIP and receipt each raised `FileExistsError` and preserved the intervening file bytes. Interrupted or conflicted builds can leave partial release files; they are not treated as a completed release and a fresh output directory is required.

### RF02 — Medium, fixed: reserved `SHA256SUMS` source member

`source_files` accepts the root member `SHA256SUMS`. `write_archive` hashes that selected source file, then replaces its archived content with a newly generated receipt. The new receipt retains the old `SHA256SUMS` hash entry, which cannot match the replacement bytes.

The counterexample explicitly selects `README.md`, `release-source-files.txt`, and `SHA256SUMS`. Build succeeds; the resulting source archive's listed self-hash fails verification.

Verified repair: the root `SHA256SUMS` name is now reserved by member validation. The independent counterexample raises `ValueError` before the output directory is created. Nested historical `.../SHA256SUMS` files remain ordinary unchanged selected content.

## Positive checks

- Explicit source inventory excludes unlisted local captures and other incidental files; missing inventory does not fall back to recursive selection.
- Parent-directory symlinks for selected members are rejected. The resolved output-directory check prevents a symlink alias from placing archives back inside the checkout.
- Existing destinations present before the build are preserved by the preflight; exclusive creation now also preserves arrivals after that check.
- The selected source inventory must include itself and every selected runtime member, which makes a portable source rebuild possible.
- In a temporary explicit inventory containing the actual runtime files and builder, the source archive was cleanly extracted and rebuilt without Git metadata. Both resulting ZIPs were byte-identical to the first build. This is a bounded rebuild check, not verification of the not-yet-generated final release inventory.
- The CLI patch correctly maps `missing_dependencies` to the documented exit code 5, including a nested runner result; other status categories retain their previous behavior.
- All 10 release/CLI audit tests passed after the repairs, including parent-added regressions for the two review findings. An additional independent confirmation exercised all three late-arrival target types and reserved-member rejection.

## Evidence

- Repro script: `/workspace/scratch/26b6d364cfda/release-fix-review-repro.py`
- Repro result: `/workspace/scratch/26b6d364cfda/release-fix-review-repro.json`
- Post-fix confirmation script: `/workspace/scratch/26b6d364cfda/release-fix-review-confirm.py`
- Post-fix confirmation result: `/workspace/scratch/26b6d364cfda/release-fix-review-confirm.json`
- Existing test run: `/workspace/scratch/26b6d364cfda/release-fix-review-tests.txt`

The inventory is a deliberate selection boundary, not a credential-content scanner. The revised receipt correctly states this limitation. Final release verification must still inspect the reviewed inventory, verify every archive hash after extraction, and run the extracted-source suite.
