# ROUTE-DECISION-01: transfer mechanism after SOURCE-REPLY-01

Status: PROPOSED, reviewed by Fable 5.1 (R20: no boundary conflict). SOURCE-REPLY-02 has settled the open facts (section below). Approved for the probe 2026-10-13 18:45Z. The probe FAILED at the upload (see the probe result below); diagnosis in `outbox/SOURCE-QUERY-03.md`.

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

## What SOURCE-REPLY-02 settled

Checked by script against the pins SOURCE-QUERY-02 sent (`observations/SOURCE-REPLY-02-CHECK.json`). The source runtime has not restarted since 15:52:05Z, and its HEAD is still the C32 baseline.

| Question | Answer |
|---|---|
| Does a copy of any C32 archive or manifest survive? | No, in `/workspace`, `/tmp`, `/var/tmp` and `/home`. Five files named `R4-EVIDENCE-MANIFEST.json` (2,439 to 5,633 B, test and restore artifacts) match no pin. `/root` could not be searched (permission denied). The four archives are missing originals |
| Are the builder receipts intact? | Yes: all four match their pins, and each records the same archive and manifest pins as C32 |
| Do the surviving roots match the receipts? | By count and bytes, yes. `r4-evidence` at or before the cutoff: 82,115 regular files, 3,893,135,483 B, 640 symlinks and 8 FIFOs, equal to the receipt and its 8 omissions. `provider-candidates`: 5,734 files and 27,278,816 B, equal. Directory counts are 6 and 2 lower than the archive records; that fits a two-directory archive wrapper plus four directories touched after the cutoff, but cannot be proven without the original manifest. Counts and bytes do not prove contents |
| What changed after the cutoff? | Exactly the 64 listed records (241,052 B) in the epoch; the 68-record list is now complete |
| Sizes that matter for transport | Largest file 293,986,466 B; 4 files over 100 MiB (so ordinary Git cannot carry even the unpacked tree); none over 2 GiB |
| Which GitHub credential does the task use? | A GitHub App user-to-server token (`ghu_` prefix in `GH_TOKEN`, short-lived, behind an HTTPS proxy) for login `nsahmed23`; no classic scopes, as expected for an app token. `gh` 2.46.0 has `release upload` and `api` |

## Decision: route B1-R, a GitHub Release asset on an owner-created private repository

| Field | Proposal |
|---|---|
| Owner | `nsahmed23`, the personal account; not an organization or employer tenant |
| Repository | new, suggested name `nsahmed23/intune-evidence-custody` (owner's choice), created by the owner with an initial README so a release can target a commit |
| Visibility | private; no collaborators; Actions, Pages, wiki and forking off |
| Mechanism | GitHub Releases REST asset upload: `POST https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets?name={file}` with `Content-Type: application/zip` and the raw file bytes as the body; one file per asset; GitHub documents each release file as under 2 GiB |
| Release | one draft release, tag `probe-20261013-01`, created by the owner in the web UI with no files attached; the source only uploads |
| Source client | the Work task's existing `gh` (present at `/usr/bin/gh`; `gh api user` returned 200), using `gh api` with `-H "User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0"` and `--input <file>`; first `GET /repos/{owner}/{repo}/releases` to find the draft's id and upload URL. A client that cannot send that User-Agent is not used |
| Source authentication | the Work task's existing GitHub App user token, unchanged: no new token, no `gh auth login`, no credential extraction. Owner action: GitHub > Settings > Applications > Installed GitHub Apps > the installation named ChatGPT, OpenAI or Codex Connector (the source's token belongs to it; if there is more than one such installation, do this for each; leave fable-reviewer, Claude and other apps alone) > Configure > Repository access. If it says "Only select repositories", add the new repository; if "All repositories", change nothing. That gives the app its existing permissions on this one repository; it pushed C32, so it very likely has contents write |
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

1. The owner creates the repository and the draft release as above, and adds the repository to the ChatGPT GitHub App's access if the app uses selected repositories.
2. The owner sends this line, with the real repository name: "Approve route B1-R for the synthetic probe only: repository nsahmed23/<name>, draft release probe-20261013-01; the Work task may read that repository's visibility, list its releases and upload synthetic-original-work-probe.zip to that draft, nothing else." The owner then pastes `outbox/SOURCE-ACTION-01.md` into the Work task. It allows exactly three network calls: confirm the repository is private, list its releases, and upload `synthetic-original-work-probe.zip` to that draft. Nothing else. It does no retries and reports the status, the asset id, and the size and name from the API.
3. The owner downloads the asset in the browser into an empty folder and tells Claude the path.
4. Claude hashes the file without extracting it and records PASS or FAIL in `observations/`.

What a PASS proves: the source's credential and network path reach a second, private repository (this is unknown today; the task may be limited to `neon-commons`), it can write a release asset there, and the bytes arrive unchanged. What it does not prove: behavior at 1.47 GB (time, interruption, retries), or any evidence classification.

Stop rules: any 401, 403, 404 or 422 stops the step and is reported as it is; a step is never repeated with unchanged authorization. There is no fallback to another mechanism without a new decision, and nothing else goes to `nsahmed23/neon-commons`.

## After a probe PASS (not authorized by this document)

The surviving roots could be moved only as a new capture. The handoff permits that only as new artifacts under new identities, after an explicit owner decision, never backdated or relabeled as recovery (`CLAUDE_CODE_HANDOFF.md` section 7 line 264 and section 10 Route D line 364). It needs:
- OA-3: classification, destination and retention.
- The owner explicitly lifting the handoff's "large source tmpfs retries" boundary for one build in `/tmp`, which is the only staging space. The upload must follow in the same session, because `/tmp` does not survive a runtime restart.
- Every asset under 2 GiB, and each upload finished within the app token's lifetime (the token is short-lived).
- The C32 archives recorded as missing originals.

Restore on this PC would use the per-layer `scripts/restore-evidence-layer.py`, one layer per fresh output root. `scripts/restore-complete-layers.py` requires nine fixed layer ids (`LAYER_IDS`, line 24 at d057cc15) and must never be fed fabricated inputs. Before any restore, measure:
- free space in the WSL ext4 filesystem and on C:, which holds its virtual disk;
- the WSL memory limit (no `.wslconfig`, so the default share of 32 GB);
- the restorer's peak memory on the smallest layer first.

Capping WSL memory would tighten the guest; closing applications is the lever.

## Probe result, 2026-10-13 18:43Z

SOURCE-ACTION-01 ran its three requests; the reply is local, in `inbox/SOURCE-ACTION-REPLY-01.json`:
- Preflight: PASS (18,445 B, pin match).
- Request 1: PASS, the repository is private.
- Request 2: PASS, exactly one draft release with no assets.
- Request 3, the upload to `uploads.github.com`: FAIL, HTTP 401 `Bad credentials`.

Nothing was uploaded and there was no retry. The owner's GitHub side is correct: the ChatGPT Codex Connector app has all repositories, with read and write access to code. A 401 rather than a 403 means the upload host did not accept the credential that reached it, while `api.github.com` accepted the same task's reads. The cause is not established; SOURCE-QUERY-03 tests it read-only. By the stop rules, B1-R gets no retry and no fallback without a new decision.
