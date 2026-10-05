# Integrated pipeline repair

The real `normalize`, `generate_files`, command renderers, and `write_project` paths now enforce the bounded correction contracts. This does not qualify an SDK request, refreshed provider state, or live Intune deployment.

Changes cover F01–F04, F06, and F09:

- Settings provider configuration is exactly `{id, settingInstance}`. Wrapper IDs are preserved and must be sequential canonical strings starting at zero; the wrapper discriminator is validated observed metadata.
- Captures start at the independently constructed public-cloud adapter root without a query. Every complete nextLink is followed exactly, with origin/path/query and loop checks. Page/body/provenance, ownership, duplicate identities, and setting counts are checked. An absent assignment acquisition remains `None`; explicit captured empty targeting remains `[]`.
- Actual JSON Schema validation gates the input, selected policy, each setting/assignment, and normalized output. Separate capability validation permits only the reviewed worked mapping. Group/filter IDs are full nonzero GUIDs and every used reference must have one external complete observation. Identical or contradictory duplicate references block generation.
- Unknown fields, unknown field names, secrets, and unsupported known shapes remain only in restricted input. Model-visible retention uses opaque IDs, canonical digest references, and no raw values. Every source container/leaf has a versioned rule, disposition, destination pointer(s), and loss-blocking flag.
- Generation checks context version, selected ID, pinned engine/Atmos/provider, identity key, normalized schema and guard flags before emission. Active output additionally revalidates provider projection and capability. Blocked output has no active `.tf` files and no infrastructure command cards.
- Command rendering accepts registered identifiers only. Harmless Python argv tests resolve the current absolute interpreter; provider command texts remain nonexecuted proposals.
- Invalid/malformed/unknown ownership manifests raise `FileExistsError`, preserving output bytes. Duplicate keys, unsafe paths, bad digests, reserved manifest paths, and manifest changes during rerun verification are rejected.

Validation: `evaluations/test_repaired_pipeline.py` first reproduced 19 failures and one error across 12 counterexample tests in `pipeline-red.log`. After implementation, the expanded 14 tests pass in `pipeline-green.log`. Cases include exact projection, initial filtered/projected/continuation captures, malformed polymorphic shapes, GUIDs, description limits, duplicate references, unknown-key/value canaries, unknown capabilities, incomplete targeting, malformed manifests, executable tokens, trusted Python argv, context versions, and forged normalized guards.

The original compatibility run identified the old unsupported-description echo expectation and CLI calls into the concurrently replaced oracle; those integration points are being handled by the root agent. No existing tests, tools, golden files, correction models/schemas, or invariants implementation were changed by this pipeline worker.

Limits: offline structural completeness is not capture authenticity, freshness, or atomic snapshot proof. Scope is synthetic Windows/MDM and the exact capability map. This work neither invokes nor qualifies a provider or an infrastructure engine. Native PowerShell, provider default sequencing, SDK serialization/refresh equality, and filesystem concurrency qualification beyond the local ownership gate remain external work.

## Review follow-up: owned symlinks

The real CLI originally classified a replaced owned file or directory symlink as generic input failure (exit 3), despite preserving bytes. A new real-CLI test reproduced both cases before the change (`pipeline-symlink-red.log`). Existing output ownership symlinks and inaccessible ownership files now raise `FileExistsError`, producing the required output conflict (exit 4). New-path validation remains an input error where no existing output ownership is being claimed. The test verifies every owned byte, manifest byte, and symlink target is unchanged. All 53 repaired pipeline and reference tests pass in `pipeline-symlink-green.log`.

## Review follow-up: actual output closure

The existing-directory rerun originally ignored unmanifested files, so additional active Terraform or configuration could remain in a project reported unchanged. A real-CLI test reproduced this for an extra `.tf` file, an extra YAML configuration, and an unlisted directory symlink (`pipeline-closure-red.log`). Reruns now require the actual filesystem file closure to equal all manifest-owned files plus the ownership manifest. Empty directories are allowed; every symlink directory or file, nonregular file, inaccessible closure, missing file, or unowned file is an output conflict. Closure is checked before owned byte verification and again before returning unchanged. The three cases now return exit 4 and preserve all existing bytes and symlink targets. All 54 pipeline and reference tests pass in `pipeline-closure-green.log`. These local checks do not establish protection against arbitrary concurrent external filesystem writes after verification.
