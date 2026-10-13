# ROUTE-DECISION-02: route B1-L (Git LFS) for the synthetic probe

Status: READY.
- Fable 5.1 review R24 returned SEND WITH FIXES, and all five fixes are applied (`lanes/advisor-fable/REPORT-R24.md`).
- The owner accepted the Git LFS User-Agent exception for the Work task: "I accept" at 20:39:29Z, then "extend that exception to the Work task" at 20:40:14Z.
- Pasting `outbox/SOURCE-ACTION-02.md` is the owner's approval of its exact scope. A separate approval line is optional.
- The receiver now refuses download hosts outside an https allowlist, and 13 tests pass.

## What SOURCE-REPLY-04 showed

`observations/SOURCE-REPLY-04-CHECK.json`, verdict PASS against the answers predicted at 20:10Z:
- gh with a full https address works on api.github.com from the Work task, so the earlier 401 is specific to uploads.github.com. Release uploads cannot work from this task, and route B1-R is closed for it. The owner's GitHub settings were not the cause.
- git over https reaches the private repository: `HEAD` and `refs/heads/main` at `a35da44c`.
- Git LFS 3.6.1 is installed in the Work task.

## Route B1-L

- **Destination:** the same private repository `nsahmed23/intune-evidence-custody`, on a new branch `probe-lfs-20261013-01`, never `main`. The branch holds `.gitattributes` and a pointer of about 130 bytes. The 18,445-byte file goes to the repository's Git LFS storage.
- **Source side:** `outbox/SOURCE-ACTION-02.md`. A new temporary repository in the Work task; `git lfs push` uploads the file first, then `git push` creates the branch. Nothing global changes in the Work task.
- **Receiver side:** `tools/fetch_lfs_probe.py` on this PC (10 unit tests pass). It is read-only and makes these requests with the required User-Agent:
  - it reads the branch, its file list and the pointer blob through the GitHub CLI;
  - it asks GitHub's LFS service for a download link;
  - it downloads once with redirects refused, into a new empty folder;
  - it compares size and SHA-256 against the pin.

  Tested at 20:30Z: the local login can query this repository's LFS service (a made-up object id returns "Object does not exist"), and without a login the service answers 401. One live poll at 20:34Z found no branch and created nothing.
- **Who can read it:** the owner, plus every GitHub App installed with access to all repositories (the ChatGPT Codex Connector and Claude among them), as for B1-R.
- **Retention:** the branch can be deleted at any time. LFS objects cannot be deleted one by one: GitHub's documented way to remove them is to delete and recreate the repository (docs.github.com, "Removing files from Git Large File Storage", read 20:35Z). That does not matter for synthetic bytes, but it matters for real evidence.
- **Limits that matter later, not for the probe** (docs.github.com, read 20:35Z):
  - The largest LFS file is 2 GB on GitHub Free and Pro.
  - Each account includes 10 GiB of LFS storage and 10 GiB of bandwidth per month on GitHub Free and Pro.
  - The owner's plan and current usage are unchecked.
- **User-Agent:** tested locally at 20:29Z against a listener on 127.0.0.1 (`tools/lfs_ua_loopback_test.py`). git sends the required User-Agent with `http.userAgent` or `http.extraHeader`. git-lfs 3.7.0 ignores both and always sends `git-lfs/<version> (...)`. The Work task's LFS requests therefore cannot carry the required header. The owner's CLAUDE.md rule covers requests Claude makes, so this needs the owner's explicit acceptance for the Work task. Claude's downloads on this PC still send the required header.
- **What a pass proves:** the source can move one small file through git and Git LFS into the private repository, and this PC can download it unchanged. A pass does not cover large files, the quota or evidence classification.

## Approval line for the owner

> Approve route B1-L for the synthetic probe only: the Work task may push one new branch, probe-lfs-20261013-01, to nsahmed23/intune-evidence-custody, holding synthetic-original-work-probe.zip through Git LFS, and Git LFS may send its own User-Agent there; nothing else.

## If not approved

- **B1-G, plain git without LFS:** every request carries the required header. GitHub rejects files over 100 MB, so real evidence would need many parts. Those parts would stay in git history.
- **Drive:** only with a changed authorization; no retry with the authorization unchanged.
- **Loss disposition (OA-3):** record the missing originals.
