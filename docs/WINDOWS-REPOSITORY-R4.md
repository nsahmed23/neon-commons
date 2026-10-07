# Inactive native current-source repository reading

`views` and the qualification-only `scripts/intune-windows-inspect.py ... views OBJECT_ID` now keep the stored repository intent and a separate `current_working_source_readback`. The exact native store dispatch reads the original recorded DOS root with the same literal Atmos resolver. It does not map an old POSIX path to a new checkout. Missing or inadmissible source evidence remains `unknown`; no source edit, apply or refresh occurs.

The selected stack/component, every selected source hash, exact effective policy, field comparison, source additions/removals/changes, provenance and read interval are exposed. Source CRLF and raw order remain unchanged. The resolver's existing typed merge, import, alias, template, depth/file/byte and unsupported-feature rules apply. The guarded reader additionally validates private current-token NTFS ownership, file types, ancestor/namespace identity, duplicates/case ambiguity, reparse/hardlink exclusion, and final source bytes while handles are retained. Arbitrary vars/env are omitted; a pointer to an unsupported policy shape cannot disclose arbitrary configuration.

Current root identity is an observation of this read. Historical intent records did not bind a native filesystem identity, so the result explicitly says that the prior root identity is unavailable. The recorded revision and its original assurance remain intact. Reading current bytes does not authenticate a Git commit, prove prior root identity, establish native Atmos/provider behavior or guarantee freshness after handles close. Existing source provenance describes inheritance; this route does not authorize source edits or assert a complete cross-stack change-impact plan.

`repository.resolve_component` retains its public signature, POSIX path checks and default implementation. Only a private `_Repository` capability seam supplies native filesystem access. `windows_repository.resolve_windows_component` is an internal raw-effective result; presentations must use the public resolution or bounded policy readback. Ordinary Windows support remains disabled.

## Local scope

The local tests use actual source YAML/JSON/HCL bytes, actual SQLite and the existing application terminal parser, with recorded Win32 filesystem effects. They are not Windows OS, mintty, Git Bash, PowerShell, real service, CI, device or native security proof. Source mutation/case collision/unsafe pointer controls reject or return explicit blocked/unknown results. Earlier qualification and failed attempts remain retained.

## Executable native procedure

On an authorized native Windows x64 CPython 3.12 host, prepare a disposable private NTFS checkout and native store using the existing native storage/store APIs. The store must contain an explicitly reviewed `workbench-repository-intent/1` artifact for the exact tenant/object, DOS root, stack/component, backend and `/vars/...` policy pointer; capture/history can be prepared through the existing reader qualifier. This is local fixture preparation, not tenant mutation. Preserve the original fixture and run every variant in a new private output directory.

Author and independently hash an expected JSON with exactly `current_policy`, sorted `source_files` (`path`,`sha256` rows), `source_hashes_equal` and `recorded_source_revision`. Author source pins with exactly `source_commit` and `files` for the qualifier's `FILES`; separately verify those bytes against the reviewed commit. Then run:

```text
python -B scripts/qualify-windows-repository.py --store C:\Pilot\Private\store --tenant TENANT --object OBJECT --expected C:\Pilot\Private\expected.json --expected-sha256 SHA256 --source-pins C:\Pilot\Private\source-pins.json --source-pins-sha256 SHA256 --output C:\Pilot\Private\new-evidence
```

The harness drives the actual readonly views subprocess and retains raw stdout/stderr, exit, source pins before/after and independent exact-policy/source assertions. Its default labels remain platform-qualified=false even if this bounded procedure passes. Re-run with independently authored expected values for an inherited source edit and added HCL/lock bytes; verify null/types/ordered arrays and inclusion/exclusion/filter changes. Retain negative variants: missing/wrong-owner root, reparse/hardlink, case alias, changed source during read, unsupported import/template, malformed pointer and a foreign POSIX scope. The observer must confirm every relevant known-bad case was rejected; a single happy-path receipt does not close this matrix.

Native authenticated Git verification, protected-worker journal access and deployment baselines are separate remaining contracts. A copied receipt or caller label does not establish a verified deployment. Required Windows OS qualification, namespace barrier behavior, crash/power-loss, selected workplace terminals and organizational risk review remain blocking gates.
