<!-- Advisor review R20 of ROUTE-DECISION-01 and SOURCE-QUERY-02. Sent by SendMessage at 2026-10-13T17:43:16.013Z; it did not reach the
controller's context, so the controller copied it from the advisor transcript. API-reported model claude-fable-5-1. -->

claude-fable-5-1

BLOCKING

B1. SOURCE-QUERY-02 step 6 (L93-94) not transcript-safe. `git config --get-regexp 'http.*extraheader'` prints VALUE (Authorization: basic <base64 token>) into tool output before model can withhold. Same for `git config credential.helper` if custom helper embeds token in args. Rule 2 (L30-35) governs reply text only, not tool output already logged in ChatGPT transcript. Fix, replace L93-94 "git config key names matching http.*.extraheader; credential.helper classification" with:
"git config --name-only --get-regexp '^http\..*\.extraheader$' (never without --name-only; empty = NONE); credential.helper: run only
git config --get-all credential.helper | awk '{ if ($1 ~ /^(store|cache|manager|manager-core|osxkeychain|libsecret)$/) print $1; else print \"CUSTOM_HELPER_PRESENT_DETAILS_WITHHELD\" }'
(empty = UNCONFIGURED)."
Also env names (L89-92): add exact command so model does not run env/printenv: "for v in GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GH_HOST GIT_ASKPASS SSH_AUTH_SOCK HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy; do [ -n \"${!v+x}\" ] && echo \"$v SET\"; done".

B2. Route-deciding fact missing: token TYPE. ROUTE-DECISION-01 L35 says owner "adds this one repository to the GitHub App's or token's repository access", but Q02 cannot tell App installation (ghs_), fine-grained PAT (github_pat_), classic PAT (ghp_), OAuth app token (gho_, scopes fixed by app, owner cannot widen). NO_CLASSIC_SCOPES (L101-102) collapses three different owner actions into one. Fix, add to step 6 before gh api call:
"gh auth status (plain, never --show-token; default output masks token). Report only: account login, host, token source line (env var name or keyring), and token prefix before first underscore (ghp, gho, ghs, ghu, github_pat) from the masked Token: line. Classify auth_type: CLASSIC_PAT / OAUTH_APP / APP_INSTALLATION / APP_USER / FINE_GRAINED_PAT / UNKNOWN."
Then L103 "Make no other network request" -> "gh auth status and gh api user are the only two network requests."

NON-BLOCKING

N1. Step 2 roots (L50-51): drop /mnt /opt /srv. Owner correction "no extended discovery"; handoff §7 L264 no indiscriminate search. Keep /workspace /tmp /var/tmp /home /root.

N2. Step 3 (L66-71): receipt SHA-256 asked but no pins. ARCHIVE_LAYER_PINS.json has builder_receipt_sha256: r4-evidence 21c10ba712bb77e39c4a998928e32eab7f1d1a51cc7ce7d8394d63aaa3fe0aee, provider-candidates e6d56171467b72f1f3c7f236da43c9a4b83170895af9faa272c06ec9cc022f84, current-diagnostic-scratch 31e08a8fbc3fbd123e8ec9b3b16ebf879c2ef56832031146767b9f10e0e5f243, current-exact-artifact-scratch a1c2c1fcabdcb01df48d17e099656bad10571f6e5434871cfa578609a7559b02. Add to step 3 or compare locally on reply; unpinned receipt cannot anchor new-capture census (step 4).

N3. Step 4 structural digest (L79-81) sorts ~100k+ lines; `sort` spills temp files to $TMPDIR when over buffer, contradicts rule 1 "write no files ... including /tmp". Add: "use LC_ALL=C sort -S 512M; sort's own temp spill in /tmp is the one permitted write."

Route B1-R: no boundary conflict found. New-capture framing honest (ROUTE-DECISION L22, L64-68); cite handoff §10 D L364 and §7 L264 (new identities after approval, never backdated) as authority for owner decision at L66. Probe + r4 use same `gh api --input` client (L34), matches owner "same mechanism" correction.

VERDICT: SEND-WITH-FIXES (B1, B2).

Delivery note: this message reached the controller as a teammate message only after the controller's turn ended, with content identical to the copy above.
