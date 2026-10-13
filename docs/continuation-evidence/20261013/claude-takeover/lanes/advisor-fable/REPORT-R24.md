# REPORT R24: Fable 5.1 review of route B1-L

Received by the controller at 2026-10-13T20:38:58Z as a SendMessage from teammate fable-advisor. Model from the API metadata in the advisor transcript: claude-fable-5-1. The text below is verbatim.

```text
R24 VERDICT: SEND WITH FIXES
claude-fable-5-1

BLOCKING (cheap, prevent wasted one-shot attempt)

F1. SOURCE-ACTION-02.md L44-68: steps 3, 4, 5 assume same shell as step 2 (`cd "$T"`). Work task tool calls often run each block in fresh shell; cwd falls back to default, likely /workspace/intune-continuation/work/projects/intune (origin = neon-commons). Fail-safe (remote `custody` absent there, push errors out) but rule 6 then ends action, needs re-relay. Fix: step 2 add last line `echo "$T"`; steps 3, 4, 5 each start with `cd "<T from step 2>" && ` (or state: "run every command from inside $T; if a new shell, first cd "$T""). Verify `git remote get-url custody` prints the custody URL before step 3.

F2. SOURCE-ACTION-02.md L35 rule 5 too thin. Auth mechanism in Work task unknown (helper UNCONFIGURED yet ls-remote private OK: proxy injection, GIT_ASKPASS or url.insteadOf with embedded token all possible). git-lfs error lines print endpoint URLs; a debugging rerun with trace env prints Authorization headers. Fix text, replace rule 5 with: "Keep any secret values out of your reply. Don't set GIT_TRACE, GIT_CURL_VERBOSE, GIT_TRACE_CURL or GIT_TRANSFER_TRACE. If any output line holds a URL with user-info or a token-like string, replace that part with REDACTED."

CHECKS (all AGREE unless noted)
1. Scope: push non-force to one new ref; `git lfs install --local` writes only .git/config + .git/hooks; no global/system touch; main untouched. OK.
2. Commands: `git init -b` (git >= 2.28) OK; `git lfs track` then add runs clean filter, pointer 129 B (42+76+11) so "<200" check right; `git lfs ls-files -l` form `<64-hex> * <path>` matches L75; `git lfs push <remote> <ref>` valid syntax, pushes all objects reachable from local ref when remote ref absent; pre-push hook on step 4 re-batches, finds object present, uploads nothing. Hang: `GIT_TERMINAL_PROMPT=0` makes `git credential fill` fail fast, no prompt; git-lfs dial/activity timeouts 30 s. OK. Note: upload href host (githubusercontent / S3) differs from github.com; proxy block there = connection error, L77 reading correct.
3. Order sane; lfs push before branch push; stop rules clear. OK.
4. Receiver fetch_lfs_probe.py: UA on every gh call (L47) and urllib (L114); href/header never printed (L110-124); NoRedirect returns None so 3xx raises, caught L118; pointer from git/blobs raw (L94), strict regex + 1024 cap (L37-38, L55-61); verdict needs oid+size+len+sha (L64-67); out-dir refused before any network (L147-149). OK. Tests cover parse, verdict, redirect, refuse. OK.
5. Wording plain, first person, no incident framing; approval line names repo, branch, file, LFS UA acceptance, "nothing else". Sufficient.
6. Facts: 2 GB/file Free+Pro (also Team; 5 GB Enterprise Cloud), 10 GiB storage + 10 GiB/month bandwidth, delete+recreate to purge LFS objects: match docs as I know them, no overreach. Note for OA-3 later: deleting branch leaves object counting against quota (already stated L24).

OPTIONAL HARDENINGS
H1. fetch_lfs_probe.py L113-116: allowlist href host (endswith ".githubusercontent.com" or ".amazonaws.com" or == "github.com") before sending batch headers; today headers go to whatever host batch names.
H2. fetch_lfs_probe.py L78-85: take tree from `.commit.commit.tree.sha` instead of passing commit sha to git/trees (works today, GitHub resolves commits, but explicit is stricter).
H3. fetch_lfs_probe.py L10 docstring says "never opened by another program" yet L175 zipfile lists members; either drop listing or say "central directory listed with zipfile, nothing extracted".

Wording: plain throughout; nothing likely to trigger refusal.
```

## Controller disposition (20:42Z)

- F1 applied differently, with the same effect and fewer moving parts. The folder is the fixed path `/tmp/lfs-probe-20261013-01`, and `mkdir` refuses an existing folder. Every git command uses `git -C <folder>`, so no step depends on the shell's working directory.
  - The remote check uses `git config --get remote.custody.url`, not `git remote get-url`. `get-url` expands `url.*.insteadOf` rewrites, which could print a login-bearing address if the Work task uses one.
- F2 applied, in plain words.
- H1 applied. The download host must be https and `github.com`, `*.github.com`, `*.githubusercontent.com` or `*.amazonaws.com`; it is checked before any request. Three tests were added, and 13 tests pass.
- H2 applied. The tree comes from `.commit.commit.tree.sha`.
- H3 applied. The docstring now says that zipfile lists the zip directory and nothing is extracted.
- Pointer size check: the pointer is exactly 130 bytes (43 + 76 + 11). Fable's 129 left out the newline after the version line. The "under 200" check is unaffected.
