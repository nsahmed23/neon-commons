claude-fable-5-1

Q1 Routes
- AGREE order B2 > B1 > A. B2 near dead: Work report already says no callable binary-export op (WORK_EXPORT_FAILURE_USER_REPORT.md L22-25). Expect B1.
- DISAGREE premise "B1 = existing authorized path" (ROUTE-ANALYSIS-01 L13). C32 push was public admin metadata only (FINAL-RESULT.json L37). Private repo = new custodian plus new resource grant. Handoff §10 Route B L348 needs "its use is authorized"; §13 M2 L483 forbids "different transport to evade". Get owner written line "B1 private repo authorized for probe" before M2; separate OA for layers (§9 L309; §21 L689: personal GitHub = consumer service).
- ADD precedent: `intune-r2-snapshot-data-20261007`, `intune-r3-evidence-data-20261007` already on PUBLIC remote (host-intake L108). Source habit = data to origin. Every source brief: "never origin".
- ADD B1 split: 3 small layers (9.8/14.5/41.5 MB) plus 4 manifests (max 36 MB) fit plain git blobs; only r4-evidence needs release asset (uploads.github.com, different egress host) or LFS.
- ADD amendment not built yet; building = source write (§13 M3 L489). ROUTE-ANALYSIS L28 treats as ready. Own authorization step.
- No missed route. Page writer <=10 MiB (FINAL-RESULT L84) rightly ignored; use = disguise (§6.1 L251).

Q2 Query (C:\Dev\Projects\intune-rescue\outbox\SOURCE-QUERY-01.md)
Read-only yes; 4 leak paths plus gaps:
- L20-21 Rule 2 ADD: "No gh auth status --show-token, gh auth token, git credential fill, credential-file cat, env dumps, token-introspection endpoints."
- L22-23 Rule 3 ADD: "No git status (index write); git rev-parse HEAD, git remote -v only."
- L64-66 5b REPLACE "gh auth status or an API GET that shows granted scopes" WITH "gh auth status default masking; report X-OAuth-Scopes and X-Accepted-OAuth-Scopes header values only, never command line holding credential." ADD "`command -v git gh git-lfs curl`; `git remote -v`; `git config --get credential.helper` (name only); HEAD-only reachability of api.github.com, uploads.github.com, github-cloud.githubusercontent.com."
- L67-69 5c REPLACE "OAuth scopes it holds" WITH "scope list visible in action description or sanitized 403 body; no token introspection."
- L70-72 step 6 REPLACE open-ended writer hunt WITH "`ps -eo pid,comm,etime`; no lsof over tree."
- L73-76 step 7 ADD "cap 50 entries plus total count."

Q3 Receiver
AGREE ext4 fit; §6.1 L249 says links may be literal data anyway.
Top risk memory: host 2.2 GB avail (host-intake L23), no .wslconfig (L62), default WSL cap about 16 GB; 4.6 GB restore page cache balloons host, swap stall. Mitigation without config change: close 3 ChatGPT desktop procs plus Edge before M4; never stage in /tmp or /dev/shm (tmpfs 7.3G RAM, L64); ~/intune-rescue only. If owner approves config: `.wslconfig` memory=8GB autoMemoryReclaim=gradual (WSL 3.0.1 supports).
ADD: B2 download lands ~\Downloads NTFS first, outside receiver root. Confirm no OneDrive sync, hash there, copy to ext4, hash again.

Q4 Risks 48 h
1. tmpfs loss on resumption (FINAL-RESULT L101). Mit: query today; owner keeps Work task open, no reset; route pick same day reply lands.
2. No r4 route (fine-grained token, no gh/git-lfs, uploads.github.com blocked). Mit: 5b additions above; owner pre-creates empty private repo, grants only after reply.
3. Wrong custodian: origin push by habit, Downloads/OneDrive, Remote Control transcripts ([setting redacted], host-intake L43; §9.2 L334). Mit: "never origin" every brief; OA-3 before any archive byte on PC; handling session launched without Remote Control.

Q5 Next
Apply Q2 edits to C:\Dev\Projects\intune-rescue\outbox\SOURCE-QUERY-01.md, owner pastes, controller idle until SOURCE-REPLY-01. Nothing else.

Files read: ROUTE-ANALYSIS-01.md, SOURCE-QUERY-01.md, 2026-10-13-host-intake.json, handoff START_HERE.md, CLAUDE_CODE_HANDOFF.md §5-14 and §19-23, HANDOFF_STATE.json, evidence\FINAL-RESULT.json, evidence\WORK_EXPORT_FAILURE_USER_REPORT.md, reference\ARCHIVE_LAYER_PINS.json. Nothing written, no network, zip untouched.
