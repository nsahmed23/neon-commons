# SOURCE-QUERY-04: plain check of the failed release upload

Status: FINAL (read-only). Replaces SOURCE-QUERY-03, which stays unchanged as the record of what was drafted.

Owner action: paste the fenced block into the same original Work task, then paste its reply here or save it as `C:\Dev\Projects\intune-rescue\inbox\SOURCE-REPLY-04.json`.

Why it replaces 03:
- The owner said at 20:05:01Z: "This isn’t a cybersecurity issue". 03 was worded like a credential investigation (tokens, proxy settings, which hosts accept a login). 04 states the plain purpose: moving a test file between the owner's own systems.
- 03 step 3 could not have told us anything. Calibration at 20:08Z (`observations/UPLOAD-HOST-CALIBRATION-01.json`): a GET on the upload server returns HTTP 400 "Invalid name for request" with a valid login, with no login and with a fake one.
- The proxy listing is dropped; the decision does not need it.
- Added `git lfs version` (local, no network), because Git LFS is the next candidate if git reaches the private repository.
- `GIT_TERMINAL_PROMPT=0` makes git fail at once instead of waiting for a username.

```text
SOURCE-QUERY-04 - troubleshooting the failed release upload (read-only).
Relayed by the owner, 2026-10-13. This replaces SOURCE-QUERY-03; do not
run that one.

Context: nsahmed23/intune-evidence-custody is my own private GitHub
repository, and the file is my own synthetic test file. In
SOURCE-ACTION-01 your two reads from api.github.com worked, but attaching
the test file to the draft release returned "401 Bad credentials". Before
I pick another way to move files from here to my PC, I need two facts:
whether the same gh command form works on api.github.com, and whether git
can reach this repository from here.

Please run the three commands below, each once, and nothing else. They
only read: do not upload, push, create, change or delete anything, and do
not retry the upload. Keep any secret values out of your reply.

1. The server that worked, called with a full https address like the
   failed upload:
   GH_NO_UPDATE_NOTIFIER=1 GH_PROMPT_DISABLED=1 gh api -H "User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0" -H "Accept: application/vnd.github+json" "https://api.github.com/repos/nsahmed23/intune-evidence-custody/releases/411991153" --jq '{id, draft, tag_name}'

2. List the repository's branches and tags with git:
   GIT_TERMINAL_PROMPT=0 git -c http.userAgent="OpenAI File Downloader, XaiImageApiFetch/1.0" ls-remote https://github.com/nsahmed23/intune-evidence-custody.git

3. Check whether Git LFS is installed (no network):
   git lfs version

For each command, report the exit code and its output or error message as
printed. Reply with one JSON object with the keys api_full_address,
git_ls_remote, git_lfs, errors.
```

Expected if everything on the GitHub side is normal (checked locally at 20:10Z): command 1 prints `{"draft":true,"id":411991153,"tag_name":"probe-20261013-01"}`; command 2 prints `HEAD` and `refs/heads/main`, both at `a35da44ca366a0585b0a7224852e1440d209b79a` (a draft release creates no tag until it is published).

How the answers will be read:
- Command 1 works: the same client and login work on api.github.com but not on uploads.github.com, so release uploads cannot work from this task. Route B1-R closes. The cause is in the task's connection to GitHub, not in the owner's GitHub settings.
- Command 1 fails: the failure is in how gh handles full addresses, not in the upload server, and a different upload command could still work. That is a new decision.
- Command 2 lists the two refs above and command 3 shows Git LFS installed: git reaches the private repository from the task, and a Git LFS probe of the same 18,445-byte file becomes the next candidate. GitHub's per-file LFS limit is 2 GiB, and the owner's LFS quota is unchecked. It needs the owner's approval as a new route.
- Command 2 fails on authentication: this task's git cannot reach the new repository either, and both GitHub routes are closed for now.
