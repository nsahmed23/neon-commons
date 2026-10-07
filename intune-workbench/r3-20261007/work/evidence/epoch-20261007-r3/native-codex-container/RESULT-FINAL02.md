# Exact final02 Linux Codex qualification

Source commit `c122e38e33641336bc5af47b9dbf06eb0e58bc32`; runtime ZIP **513,895 bytes**, SHA-256 `cce47f620f5e1e7d3dbdab1e030624fae3991cbf88376737a4eda07e6c703515`.

The retained driver executed the actual digest-pinned native Codex CLI in the previously qualified disposable Linux Docker profile. `final-runtime-02/assertions.json` passes **26/26** independent literal/ZIP/tar/kernel assertions over **10 native commands** (nine positive, one expected unknown-plugin rejection). All **130 installed payloads** match the runtime ZIP. Registration, discovery, install, enabled listing, uninstall and marketplace removal passed; mounted input bytes were unchanged, final home/config were empty as specified and the container was removed.

`INDEPENDENT-SPOTCHECK-FINAL02.json` independently cross-checks the raw evidence: 24 grouped checks, 64 receipt hashes, four wrapper output hashes, exact argv/exit outcomes and all installed files. These counts overlap; they are separate from the product strict-suite count.

Boundary: user 1000, dropped capabilities, no-new-privileges, read-only root and input, network none, private temporary home, resource bounds and no account, credential or Docker-socket mount. Docker 28.4.0, Codex 0.159.0-alpha.3 SHA-256 `981ade7b03926534c654fd718ced3a9f378b7b2841271e29156f939462d176e9`, pinned image digest and actual launch arguments remain in the raw receipt. No model session or skill invocation was run; this does not qualify other hosts, the provider worker boundary, live cloud services or organizational production approval.

Replay exact arguments are in `FINAL02-COMMANDS.json`; use `qualify-native.py --plugin EXACT_EXTRACTED_RUNTIME --output NEW_CASE`, followed by `grade-native.py --case NEW_CASE --runtime-zip EXACT_ZIP --commit EXACT_SOURCE_COMMIT`. Use a new case directory, the retained reviewed digest-pinned image and native binary; do not mount personal account state or provide credentials. An already passed lane does not need routine repetition.

Earlier `RESULT.md`, `EVIDENCE-HASHES.json` and `final-runtime-01/` remain unchanged and retain their earlier exact-package scope. This later result supersedes older unavailable-host prose only for the Linux CLI lifecycle actually observed.
