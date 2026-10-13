# SOURCE-QUERY-02: read-only follow-up after SOURCE-REPLY-01

Status: FINAL. Reviewed by Fable 5.1 (R20, verdict SEND-WITH-FIXES; both blocking fixes and all three non-blocking items applied). One deliberate deviation: Fable proposed `gh auth status` to read the token type. That command makes its own GitHub request, which cannot carry the owner's required User-Agent, so the type is read offline from an allowlisted token prefix instead.

Owner action: paste everything inside the fenced block below into the same original ChatGPT Work task (keep the task; do not reset it or start a new one). Paste its reply into the Claude Code session, or save it as `C:\Dev\Projects\intune-rescue\inbox\SOURCE-REPLY-02.json`.

Why: SOURCE-REPLY-01 found all four C32 archives absent from their recorded `/tmp` paths in a runtime that started 2026-10-13T15:52:05Z, while `/workspace` survived. This query settles three things and nothing more. First, does a copy of any archive or manifest survive elsewhere? Second, do the surviving input roots still match what the builder receipts recorded? Third, which kind of GitHub credential does the task use? That decides what the owner must change, if anything, for the release-asset route in `ROUTE-DECISION-01.md`. Corrections from the owner-relayed ChatGPT review are applied: d057cc15 is named as the immutable baseline, credential configuration is sanitized at the command level, and each limited observation is labeled as limited.

```text
SOURCE-QUERY-02 - read-only follow-up to SOURCE-REPLY-01.
From the receiver controller, relayed by the owner, 2026-10-13.
Baseline: C32 commit d057cc15c9928dd1a34a965b8d8ebf8e6755d94a is the
immutable C32 baseline. Report the source HEAD you observe separately.
Do not fetch, pull or compare with any remote.

This request is read-only. It is not an export, a rebuild or a transfer.

Rules:
1. Do not upload, export, attach, share, copy, move, rename, compress,
   split, delete, restore, rebuild or retry anything. Never commit, push,
   or create a branch, tag, release or repository anywhere. Do not change
   the repository, credentials, connectors, approvals or any laboratory
   state. Do not start background work, restart anything, or run project
   code. Write no files anywhere, including /tmp; compute digests in a
   pipe. The only tolerated write is a temporary spill by sort itself in
   step 4; report it if it happens.
2. Credentials must not appear even in your own command output: anything
   a command prints is already in this task's transcript. Use only the
   exact commands given in step 6 for configuration and environment
   checks. Do not run gh auth token, gh auth status, git credential fill
   or any credential helper, env, printenv, set, or token-introspection
   endpoints, and do not open credential or gh configuration files (test
   -e for existence only). Print any URL with its user-info part
   replaced by REDACTED.
3. Label limited observations as limited. A process listing names
   candidate writers; it does not prove that nothing writes. Host
   reachability, an HTTP 200 from /user and scope headers do not prove
   permission for any particular repository, release or LFS object. A
   bounded list states its bound and is never an amendment manifest.
4. Do not widen the search beyond the steps below. If a field cannot be
   settled with these steps, write UNKNOWN and name the smallest single
   operation that would settle it. Stop after the reply.

Steps:
1. runtime: current UTC; kernel boot time; uptime; whether the boot time
   differs from 2026-10-13T15:52:05Z; source HEAD from git rev-parse HEAD.
2. copies (time box 10 minutes): with find -P -xdev, regular files only,
   under whichever of /workspace /tmp /var/tmp /home /root exist, list
   files whose size equals one of the eight pins below or whose name
   matches *.PRIVATE-AVAILABLE.zip or R4-EVIDENCE-MANIFEST.json. Hash at
   most 200 hits (report the total count) and give path, bytes, fresh
   SHA-256 and pin match. If the box expires, report the roots covered
   and not covered.
   archives (label, bytes, sha256):
   r4-evidence                     1469518188  7bbc9f88eee9b4c417f622fb76cb5e2c0b0d4790d5b7cceaa2ae661ce2012ad7
   provider-candidates                9849950  755b9f4f8d29e562f476fc7e1f3bb8f376fd0fbfbeabe7a8e7e7ec78099280c7
   current-diagnostic-scratch        14485539  60960f3760f24893e7114185d5d14ee7ab3e35e1fc17008097d2b6eecc83e939
   current-exact-artifact-scratch    41538870  c221c1410d905806275dc3ea72c2793db83839816d112d4d3095e3bbe4819add
   manifests (label, bytes, sha256):
   r4-evidence                       35983862  9f53658f8b795e136d32baab6d7043741a81cd6450e9d640489fb01a97610fb1
   provider-candidates                2875760  bccf1c15dcda000ebeae37f1c23de016233d062d8a0edcf535b39f67ffd99fa6
   current-diagnostic-scratch            5496  43ef5e7852f9e2be9878cfc17ef096182d166fc693b970333828e54e11f7b992
   current-exact-artifact-scratch     1677589  5d8b84ecc1c8bf9690fa0cbfa0012650430e36f302f4982969a04366b7984c2e
3. receipts: for each of the four files
   <epoch>/integration/storage-diagnosis-C32-20261012-01/stopped-at-export-boundary/<label>-builder-receipt.json
   (epoch = /workspace/intune-continuation/work/evidence/epoch-20261007-r4)
   give bytes and a fresh SHA-256 compared with these pins:
   r4-evidence                     21c10ba712bb77e39c4a998928e32eab7f1d1a51cc7ce7d8394d63aaa3fe0aee
   provider-candidates             e6d56171467b72f1f3c7f236da43c9a4b83170895af9faa272c06ec9cc022f84
   current-diagnostic-scratch      31e08a8fbc3fbd123e8ec9b3b16ebf879c2ef56832031146767b9f10e0e5f243
   current-exact-artifact-scratch  a1c2c1fcabdcb01df48d17e099656bad10571f6e5434871cfa578609a7559b02
   Then give each receipt's top-level keys and the values of scalar
   fields that record counts, bytes, hashes, input roots, cutoff, or
   start and finish times. For lists give only their length. No member
   paths.
4. census (metadata only; read no file contents) of the two surviving
   input roots /workspace/intune-continuation/work/evidence/epoch-20261007-r4
   and /workspace/intune-continuation/work/provider-candidates, using
   find -P -xdev: counts by type (regular, directory, symlink, FIFO,
   socket, other); sum of regular-file sizes; largest regular-file size;
   number of regular files over 104857600 bytes and over 2147483648
   bytes; the same counts restricted to entries whose mtime is at or
   before the cutoff 2026-10-12T21:23:33.007726Z; and a structural digest
   per root: the SHA-256 of the lines "<type letter> <size> <relative
   path>" for all entries, where size is the byte size for regular files
   and symlinks and 0 for everything else, sorted with LC_ALL=C sort -S
   512M, computed in a pipe without printing paths. Compare the
   at-or-before-cutoff counts with step 3 where a receipt records
   comparable counts: MATCH, DIFFERENT (both numbers) or NOT_COMPARABLE.
   Modification time is not creation time; say so.
5. post_cutoff_records: the 18 records SOURCE-REPLY-01 did not list
   (68 total), with the same fields (path_base, relative_path, bytes,
   mtime_utc), then list_complete.
6. github_client. Run exactly these, from the repository directory, and
   report their output:
   a. gh --version | head -n 1
   b. gh release upload --help >/dev/null 2>&1; echo "release-upload $?"
      gh api --help >/dev/null 2>&1; echo "api $?"
   c. for v in GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GH_HOST
      GIT_ASKPASS SSH_AUTH_SOCK HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY
      http_proxy https_proxy all_proxy no_proxy; do [ -n "${!v+x}" ] &&
      echo "$v SET"; done
   d. for v in GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN; do
      if [ -n "${!v+x}" ]; then p="${!v%%_*}"; case "$p" in
      ghp|gho|ghu|ghs|ghr|github) echo "$v prefix $p";;
      *) echo "$v prefix OTHER";; esac; fi; done
   e. test -e ~/.config/gh/hosts.yml && echo "gh hosts file present"
   f. git config --name-only --get-regexp '^http\.(.*\.)?extraheader$'
      (never without --name-only; empty output means NONE)
   g. git config --get-regexp '^credential(\..+)?\.helper$' | awk '{ if
      ($2 ~ /^(store|cache|manager|manager-core|osxkeychain|libsecret)$/)
      print $1, $2; else print $1, "CUSTOM_HELPER_PRESENT_DETAILS_WITHHELD" }'
      (empty output means UNCONFIGURED)
   h. exactly one network request: gh api --include user with
      -H "User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0".
      From it report only: HTTP status; the values of the headers
      X-OAuth-Scopes and X-Accepted-OAuth-Scopes (match header names
      exactly and case-insensitively, one header per line; an empty value
      is ""); whether the headers X-OAuth-Client-Id and
      github-authentication-token-expiration are present (presence only);
      and the body fields login and type.
   Then classify auth_type from d: ghp = CLASSIC_PAT, gho = OAUTH_APP,
   ghu = APP_USER, ghs = APP_INSTALLATION, github = FINE_GRAINED_PAT; if
   no token variable is set, NOT_IN_ENVIRONMENT; otherwise UNKNOWN. Say
   whether the X-OAuth-Scopes value includes repo. Make no other network
   request.

Reply with one JSON object with these keys: runtime, copies, receipts,
census, post_cutoff_records, github_client, errors,
smallest_unresolved_operation.
```
