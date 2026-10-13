# SOURCE-ACTION-02: send the synthetic probe through Git LFS (route B1-L)

Status: FINAL. Fable 5.1 review R24 (SEND WITH FIXES), both blocking fixes applied:
- F1: every command names the folder with `git -C`, so a fresh shell between steps cannot run git in the wrong repository;
- F2: the reply rule bans git trace output and asks for redaction.

The owner accepted that Git LFS sends its own User-Agent in the Work task: "I accept" (20:39:29Z), then "extend that exception to the Work task" (20:40:14Z).

Owner action: paste the fenced block into the same original Work task. Pasting it is the owner's approval of exactly what the block says: one new branch, one file, nothing else. Paste the Work task's reply here, or save it as `C:\Dev\Projects\intune-rescue\inbox\SOURCE-ACTION-REPLY-02.json`. Claude's watcher (`tools/fetch_lfs_probe.py`) downloads the file on this PC as soon as the branch appears and compares the hash.

What this tests: route B1-L end to end on 18,445 synthetic bytes. A pass does not cover large files, the LFS quota or any evidence classification.

```text
SOURCE-ACTION-02 - send the synthetic test file through Git LFS (one approved push).
Relayed by the owner, 2026-10-13.

Context: nsahmed23/intune-evidence-custody is my own private GitHub
repository, and the file is my own synthetic test file. Your last reply
showed that git reaches the repository and Git LFS is installed, while
release uploads don't work from here. So this test sends the file through
git with Git LFS. I approved exactly this: one new branch,
probe-lfs-20261013-01, in that repository, holding that one file through
Git LFS.

Rules:
1. Send only the file
   /workspace/intune-synthetic-export-work-export-b3071470-cc42-454e-876c-3e6a189e5beb/synthetic-original-work-probe.zip
   Don't change, move or delete it; the steps work on a copy in the new
   folder /tmp/lfs-probe-20261013-01.
2. Push only the new branch probe-lfs-20261013-01. Don't touch main or
   any other branch, tag or release, don't force-push, and don't touch any
   other repository.
3. Change no global or system git settings, credentials or connectors.
   Every setting goes in the new folder's repository only.
4. git commands send the header
   User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0
   through -c http.userAgent as written below. Git LFS sends its own
   User-Agent; I accepted that for this test.
5. Keep any secret values out of your reply. Don't turn on git's trace or
   verbose output (GIT_TRACE, GIT_CURL_VERBOSE, GIT_TRACE_CURL,
   GIT_TRANSFER_TRACE). If an output line contains a web address with a
   login in it, or anything that looks like a key, replace that part with
   REDACTED.
6. If any step fails, stop there, report the exit code and the error as
   printed, and don't retry.
7. Run every command exactly as written. Each one names the folder with
   git -C, so it works even if your shell starts fresh between commands.

Steps:
1. Check the file (no network): report its size and SHA-256. Continue only
   if they are 18445 and
   d01a9b0e9cd1506b1ee5d0defcfebf4f377af858ab610d3ec5362623ee0c67c3.
2. Build the commit in the new folder (no network). mkdir fails if the
   folder already exists; if it does, stop and report.
   mkdir /tmp/lfs-probe-20261013-01
   git -C /tmp/lfs-probe-20261013-01 init -q -b probe-lfs-20261013-01
   git -C /tmp/lfs-probe-20261013-01 lfs install --local
   git -C /tmp/lfs-probe-20261013-01 lfs track synthetic-original-work-probe.zip
   cp /workspace/intune-synthetic-export-work-export-b3071470-cc42-454e-876c-3e6a189e5beb/synthetic-original-work-probe.zip /tmp/lfs-probe-20261013-01/
   git -C /tmp/lfs-probe-20261013-01 add .gitattributes synthetic-original-work-probe.zip
   git -C /tmp/lfs-probe-20261013-01 -c user.name="Work task probe" -c user.email="probe@example.invalid" commit -q -m "probe: synthetic Git LFS transfer test"
   git -C /tmp/lfs-probe-20261013-01 remote add custody https://github.com/nsahmed23/intune-evidence-custody.git
   git -C /tmp/lfs-probe-20261013-01 config --get remote.custody.url
   git -C /tmp/lfs-probe-20261013-01 lfs ls-files -l
   git -C /tmp/lfs-probe-20261013-01 cat-file -s HEAD:synthetic-original-work-probe.zip
   git -C /tmp/lfs-probe-20261013-01 rev-parse HEAD
   Report the remote address, the git lfs ls-files line, the blob size and
   the commit id. Continue only if the remote address is
   https://github.com/nsahmed23/intune-evidence-custody.git, the ls-files
   line shows object id
   d01a9b0e9cd1506b1ee5d0defcfebf4f377af858ab610d3ec5362623ee0c67c3, and
   the blob size is under 200 bytes (the commit holds a small pointer,
   not the file itself).
3. Upload the file to the repository's Git LFS storage (network):
   GIT_TERMINAL_PROMPT=0 git -C /tmp/lfs-probe-20261013-01 lfs push custody probe-lfs-20261013-01
   Report the exit code and output. The branch is not pushed yet, so a
   failure here leaves no new branch in the repository.
4. Push the branch (network):
   GIT_TERMINAL_PROMPT=0 git -C /tmp/lfs-probe-20261013-01 -c http.userAgent="OpenAI File Downloader, XaiImageApiFetch/1.0" push custody HEAD:refs/heads/probe-lfs-20261013-01
   Report the exit code and output.
5. Confirm (network):
   GIT_TERMINAL_PROMPT=0 git -C /tmp/lfs-probe-20261013-01 -c http.userAgent="OpenAI File Downloader, XaiImageApiFetch/1.0" ls-remote custody
   Report the ref lines.

Leave the folder in place. Reply with one JSON object with the keys
preflight, build, lfs_push, git_push, confirm, errors.
```

Expected on success:
- step 2 shows `d01a9b0e9cd1506b1ee5d0defcfebf4f377af858ab610d3ec5362623ee0c67c3 * synthetic-original-work-probe.zip` and a blob of 130 bytes;
- step 5 shows `HEAD` and `refs/heads/main` at `a35da44ca366a0585b0a7224852e1440d209b79a`, plus `refs/heads/probe-lfs-20261013-01` at the commit id from step 2.

If step 3 fails with a connection error and no HTTP status, the Work task cannot reach GitHub's LFS storage host, and B1-L is closed for this task.
