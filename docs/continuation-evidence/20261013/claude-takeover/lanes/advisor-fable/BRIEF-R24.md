# BRIEF R24: review route B1-L (Git LFS) before owner relays it

Lane: advisor-fable. Read-only. Time box: 10 minutes from receipt; stop at the box and report what you have.

## Why
B1-R (release asset) dead for Work task. SOURCE-REPLY-04 PASS (`observations/SOURCE-REPLY-04-CHECK.json`): gh full-address GET on api.github.com OK; git ls-remote of private repo OK (HEAD + main at a35da44c); git-lfs 3.6.1 installed. So upload 401 specific to uploads.github.com.
Owner said at 20:05:01Z: "This isn’t a cybersecurity issue". Keep wording plain; no security-incident framing in owner-facing or Work-facing text.

## Read
1. `C:/Dev/Projects/intune-rescue/outbox/ROUTE-DECISION-02.md` (proposal + owner approval line).
2. `C:/Dev/Projects/intune-rescue/outbox/SOURCE-ACTION-02.md` (block owner pastes into Work task).
3. `C:/Dev/Projects/intune-rescue/tools/fetch_lfs_probe.py` + `tools/test_fetch_lfs_probe.py` (receiver; 10 tests pass).
4. Evidence: `observations/UPLOAD-HOST-CALIBRATION-01.json`, `observations/SOURCE-REPLY-04-CHECK.json`, `tools/lfs_ua_loopback_test.py` (result: git honors http.userAgent and http.extraHeader; git-lfs 3.7.0 ignores both, always sends git-lfs/<ver>). Local gh login LFS batch query on custody repo with made-up oid returned per-object 404 "Object does not exist on the server"; no login returned 401.
5. Prior context if needed: `outbox/SOURCE-ACTION-01.md`, `outbox/ROUTE-DECISION-01.md`, your `REPORT-R22.md`.

## Check
1. Block can't touch main, other branches/tags/releases, other repos, global/system git config, credentials. Non-force push only.
2. Commands correct for git-lfs 3.6.1 + recent git: `git init -b`, `git lfs install --local`, `git lfs track <file>`, `git lfs ls-files -l` output form, `git cat-file -s`, `git lfs push <remote-name> <branch>` before branch exists remotely, then `git push custody HEAD:refs/heads/<branch>`. Pre-push hook behavior after lfs push. Any step that could hang or prompt.
3. Failure order sane: lfs push first so no branch without object. Stop rules clear.
4. Receiver: every request sends required UA; nothing secret printed or saved (href, batch headers); redirects refused; pointer read from git blob API (not contents API); strict pointer parse; verdict needs pointer oid/size + bytes + sha all match pin; refuses existing out dir before any network.
5. Wording: plain; nothing likely to make the Work task refuse; approval line exact and sufficient (names branch, repo, file, git-lfs UA acceptance, nothing else).
6. Facts in ROUTE-DECISION-02 (LFS 2 GB per file Free/Pro; 10 GiB storage + 10 GiB bandwidth Free/Pro; LFS objects removable only by delete+recreate repo) stated without overreach.

## Rules
This lane is read-only: do not edit, move or delete any file anywhere.
Do not open `C:/Dev/Projects/intune-rescue/inbox/`, `logs/transcripts/`, or any session transcript.
Make no network requests and run no git commands.

## Report (SendMessage to team-lead, caveman full)
First line exactly: `R24 VERDICT: SEND` or `R24 VERDICT: SEND WITH FIXES` or `R24 VERDICT: HOLD`.
Line 2: your model id.
Then: blocking items (file, line, what, fix); optional hardenings; one line on wording.
