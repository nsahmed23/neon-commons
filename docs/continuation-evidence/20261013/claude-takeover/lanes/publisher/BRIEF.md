# PUBLISHER BRIEF - publish_branch.py: sanitized rescue docs as fast-forward commits, no checkout

Role: implementer. Python 3.11+ stdlib only, plus git CLI. Test first (red, then green).

First line of report: exact model ID you run as.

Binding rules:
- Write only inside this directory: C:\Dev\Projects\intune-rescue\lanes\publisher. Do not touch any other path.
- No network commands. Never push to any remote URL. Tests use local fixture repositories created in a temp directory under this directory.
- Keep every file ASCII-only.
- Time box: 35 minutes. At the box, stop and report what works.

Goal: `publish_branch.py` turns an allowlisted, sanitized copy of a workspace into ONE new commit on a branch of a git repository without checking anything out, then optionally pushes it fast-forward.

Interface:
  py -3.11 publish_branch.py --root <workspace> --repo <git dir, may be bare> --branch <name> --prefix <path inside repo> --allowlist <file> [--remote origin] [--fetch] [--push] [--message <text>] [--dry-run]

Behavior:
1. --fetch: git -C <repo> fetch <remote> +refs/heads/<branch>:refs/heads/<branch>. The real repo is a blob-less partial clone: never read blobs of existing commits (that triggers network); trees are present.
2. tip = git rev-parse refs/heads/<branch>.
3. Collect files under --root matching the allowlist (one glob per line relative to root; lines starting '!' exclude; '#' comments). Hard excludes, even if allowlisted: anything under logs/transcripts/, source.git/, inbox/, any *.log, any *.err.
4. Sanitize text files (.md .json .jsonl .html .js .py .txt .csv): replace home-path forms of the current user (user = USERNAME env, else getpass.getuser()): C:\Users\<user>, C:/Users/<user>, C:\\Users\\<user> (JSON-escaped), /c/Users/<user>, /mnt/c/Users/<user>; drive letter any case. Replacement: "~". Files under handoff/ are never modified (byte-identical). Binary files (.zip .png) copied as is.
5. Write blobs with git hash-object -w --stdin. Build the new subtree with git mktree (nested directories). Graft it at --prefix by rewriting only the trees along the prefix path: git ls-tree <tree> (non-recursive) plus git mktree per level. All other subtrees keep their SHA.
6. New root tree equal to tip tree: print "no changes", exit 0, no commit.
7. Else git commit-tree <tree> -p <tip> -m <message or "docs(takeover): sync <UTC ISO>">. Print commit SHA.
8. --push without --dry-run: git -C <repo> push <remote> <commit>:refs/heads/<branch>. Never --force or +refspec. On success update refs/heads/<branch> to the commit. Rejection: print git stderr, exit 3.
9. --dry-run: steps 1-7 (loose objects in the object store are harmless), print file list with sizes and the would-be commit SHA; no ref update, no push.
10. Exit codes: 0 ok or no changes; 2 usage; 3 push rejected; 4 other git failure (print git stderr).

Tests (unittest, test_publish_branch.py, run with py -3.11 -m unittest -v test_publish_branch): fixture = git init --bare plus a seed commit with nested tree (docs/a.md, src/x.py) built with plumbing; a fake workspace with allowlisted and excluded files (logs/transcripts/t.jsonl, x.log, inbox/r.json), a text file containing C:\Users\<current user>\x and /c/Users/<current user>/x, and handoff/h.json containing a home path that must stay unchanged. Assert: excluded files absent from the commit; home paths sanitized; handoff bytes preserved; only trees on the prefix path changed; a second run with no changes makes no commit; commit parent is the tip; push to a second local bare repo (path remote) fast-forwards and updates the ref; a push after the remote advanced exits 3.

Report on stdout, caveman full: files written; exact test command; last 20 lines of its output verbatim; open issues. No recap.
