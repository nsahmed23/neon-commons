# ROUTE-DECISION-01: transfer mechanism after SOURCE-REPLY-01

Status: PROPOSED, reviewed by Fable 5.1 (R20: no boundary conflict; its blocking fixes were in SOURCE-QUERY-02 and are applied). Waiting on SOURCE-REPLY-02 and owner approval. Nothing has been created, uploaded or authorized.

## What SOURCE-REPLY-01 changed

Checked by script against the pins SOURCE-QUERY-01 sent (`observations/SOURCE-REPLY-01-CHECK.json`):

| Object | Result |
|---|---|
| Four C32 archives (`r4-evidence`, `provider-candidates`, `current-diagnostic-scratch`, `current-exact-artifact-scratch`) | ABSENT: ENOENT at every recorded `/tmp` path; the echoed pins match the sent pins; no fresh hash possible |
| Their four embedded manifests | Not hashable: parent archives absent |
| Synthetic probe `synthetic-original-work-probe.zip` | PRESENT in `/workspace`: 18,445 B, SHA-256 `d01a9b0e...0c67c3`, size and mtime unchanged: PIN-MATCH |
| Probe receipt `WORK-EXPORT-PROBE.json` | PRESENT: 2,426 B, PIN-MATCH |
| Input roots for `r4-evidence` and `provider-candidates` (in `/workspace`) | Exist (existence only; completeness not checked) |
| Input roots for the two scratch layers (in `/tmp`) | Gone |

The source runtime is new: kernel boot 2026-10-13T15:52:05Z, the same logical environment, `/workspace` retained, `/tmp` nearly empty. Neither the cause nor the time `/tmp` was emptied is known; the reply observed only the current runtime. Capacity: `/workspace` has 3,018,752 B available to the task's account; `/tmp` has 9,441,345,536 B; the memory cgroup limit is 17,179,869,184 B (tmpfs pages count against memory).

Consequences:
1. Byte-identical recovery of the C32 archives is impossible unless SOURCE-QUERY-02 finds a surviving copy. Until then they are missing originals, like the C30 runtime ZIP and the observer ZIP.
2. An archive built from the surviving `/workspace` roots would be a new capture with a new cutoff and new hashes, never a recovery of C32's archives. The two scratch layers cannot be rebuilt from anything known.
3. The probe survives, so the route can still be qualified before any evidence decision.

## Decision: route B1-R, a GitHub Release asset on an owner-created private repository

| Field | Proposal |
|---|---|
| Owner | `nsahmed23`, the personal account; not an organization or employer tenant |
| Repository | new, suggested name `nsahmed23/intune-evidence-custody` (owner's choice), created by the owner with an initial README so a release can target a commit |
| Visibility | private; no collaborators; Actions, Pages, wiki and forking off |
| Mechanism | GitHub Releases REST asset upload: `POST https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets?name={file}` with `Content-Type: application/zip` and the raw file bytes as the body; one file per asset; GitHub documents each release file as under 2 GiB |
| Release | one draft release, tag `probe-20261013-01`, created by the owner in the web UI with no files attached; the source only uploads |
| Source client | the Work task's existing `gh` (present at `/usr/bin/gh`; `gh api user` returned 200), using `gh api` with `-H "User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0"` and `--input <file>`; first `GET /repos/{owner}/{repo}/releases` to find the draft's id and upload URL. A client that cannot send that User-Agent is not used |
| Source authentication | whatever the Work task already uses, unchanged: no new token, no `gh auth login`, no credential extraction. SOURCE-QUERY-02 step 6 classifies it. The owner's action depends on the type. Classic PAT or OAuth-app token with `repo` scope: none. GitHub App (user or installation token): add this one repository to the app's repository access. Fine-grained PAT: add this one repository to that token. OAuth-app token without `repo`: the route needs a new decision, because the owner cannot widen it without re-authorizing the app. Nothing broader than one repository |
| Receiver download | the owner opens the draft release page signed in and downloads the asset in the browser into a new empty folder; Claude handles no GitHub credential. (Local `gh` 2.78.0 exists and is logged in; using it is an alternative only if the owner prefers.) |
| Verification | Claude computes size and SHA-256 of the downloaded file; PASS only for 18,445 B and `d01a9b0e9cd1506b1ee5d0defcfebf4f377af858ab610d3ec5362623ee0c67c3`; the source's upload response must report the same size and asset name |
| Audience | the owner; the Work task's GitHub identity (write, this repository only); GitHub as provider |
| Retention | until the owner deletes the asset or the repository; GitHub-side retention after deletion UNKNOWN |
| Classification | the probe is synthetic, so OA-3 is not needed for the probe; any evidence asset needs OA-3 first |

Why not the others:
- Ordinary Git push: GitHub blocks files over 100 MiB, so the 1,469,518,188 B layer cannot be one tracked file. A probe pushed with Git would not qualify a release upload.
- Git LFS: depends on the owner's LFS storage and bandwidth quota, which nobody has checked. GitHub documents no total-size or bandwidth limit for releases, only the per-file limit.
- Drive: the C33 upload failed with 403 `ACCESS_TOKEN_SCOPE_INSUFFICIENT`; it needs a connector scope repair first, and its size limit is UNKNOWN.
- Linear attachment: the size fits (under 2 GB), but it puts the data with a third party, with an unknown audience and a 60-second signed URL.
- ChatGPT Page Files: 10 MiB limit; it would qualify only the probe, not the real transfer.
- ChatGPT Library: not exposed in this Work task.
- Gmail: no qualified attachment size.

## Probe procedure (after OA-2)

1. The owner creates the repository and the draft release as above, and makes any one-repository access change SOURCE-REPLY-02 shows is needed.
2. The owner sends this line, with the real repository name: "Approve route B1-R for the synthetic probe only: repository nsahmed23/<name>, draft release probe-20261013-01; the Work task may list releases and upload synthetic-original-work-probe.zip to that draft, nothing else." Claude then writes SOURCE-ACTION-01 for the Work task. It allows exactly two network calls, list releases and upload `synthetic-original-work-probe.zip` to that draft, and nothing else. It does no retries on any 4xx and reports the HTTP status, the asset id, and the size and name from the API.
3. The owner downloads the asset in the browser into an empty folder and tells Claude the path.
4. Claude hashes the file without extracting it and records PASS or FAIL in `observations/`.

What a PASS proves: the source's credential and network path reach a second, private repository (this is unknown today; the task may be limited to `neon-commons`), it can write a release asset there, and the bytes arrive unchanged. What it does not prove: behavior at 1.47 GB (time, interruption, retries), or any evidence classification.

Stop rules: any 401, 403, 404 or 422 stops the step and is reported as it is; a step is never repeated with unchanged authorization. There is no fallback to another mechanism without a new decision, and nothing else goes to `nsahmed23/neon-commons`.

## After a probe PASS (not authorized by this document)

The surviving roots could be moved only as a new capture. The handoff permits that only as new artifacts under new identities, after an explicit owner decision, never backdated or relabeled as recovery (`CLAUDE_CODE_HANDOFF.md` section 7 line 264 and section 10 Route D line 364). It needs:
- OA-3: classification, destination and retention.
- The owner explicitly lifting the handoff's "large source tmpfs retries" boundary for one build in `/tmp`, which is the only staging space. The upload must follow in the same session, because `/tmp` does not survive a runtime restart.
- Every asset under 2 GiB.
- The C32 archives recorded as missing originals.

Restore on this PC would use the per-layer `scripts/restore-evidence-layer.py`, one layer per fresh output root. `scripts/restore-complete-layers.py` requires nine fixed layer ids (`LAYER_IDS`, line 24 at d057cc15) and must never be fed fabricated inputs. Before any restore, measure:
- free space in the WSL ext4 filesystem and on C:, which holds its virtual disk;
- the WSL memory limit (no `.wslconfig`, so the default share of 32 GB);
- the restorer's peak memory on the smallest layer first.

Capping WSL memory would tighten the guest; closing applications is the lever.
