<!-- Advisor review R22 of SOURCE-ACTION-01 and the updated ROUTE-DECISION-01. Sent by SendMessage at 2026-10-13T18:25:17.094Z; copied from the
advisor transcript because teammate messages reach the controller only after its turn ends. API-reported model claude-fable-5-1. -->

claude-fable-5-1

BLOCKING: none.

Checks asked (from memory of gh source, not network-verified; gh 2.46.0 is 2024-era, code paths below predate it):
- Absolute URL: `gh api` has `restURL()`; path starting https:// used verbatim. Auth: go-gh header transport attaches Authorization when request host == configured host or ends ".github.com"; uploads.github.com qualifies. AGREE step 3 works.
- `--input <file>` opens file, streams body, sets Content-Length from file size; uploads.github.com needs Content-Length. Method POST explicit, fine. `-H User-Agent` set on request first; transport skips default UA when header present. AGREE.
- Drafts: GET /repos/{o}/{r}/releases returns drafts for callers with push access. ghu_ token = intersection(app installation permissions on repo, user permission); owner = push. Contents:write proven by C32 push. Draft from UI with tag `probe-20261013-01` returns tag_name field before tag exists; auto source zips are not in `.assets`. AGREE step 2 jq finds it with no assets.
- Credential print: gh error output = "gh: <message> (HTTP nnn)"; no token, no Authorization echo; upload returns 201, no redirect. One write only (step 3). neon-commons never named in commands. No gh auto-retry on POST. AGREE.
- Owner app step (ROUTE-DECISION L48): correct path. ghu_ access evaluated at request time against installation, so adding repo to installation takes effect without new token. "Authorized GitHub Apps" tab irrelevant (user side already authorized, hence ghu_). AGREE.
- Boundaries: one-repo installation grant = handoff §9.1 L320 supported flow, narrowest grant; no new credential, no disguise, no tmpfs retry. AGREE.

NON-BLOCKING

N1. "Exactly two requests" and "write no files" (L13, L23) can break on gh itself: update notifier may GET cli/cli latest release and write ~/.config/gh/state.yml (skipped when stdout not a tty, Debian build may disable, but unproven). Fix: prefix both commands in steps 2 and 3 with `GH_NO_UPDATE_NOTIFIER=1 GH_PROMPT_DISABLED=1 ` and add to rule 1: "gh's own config/state writes are the only permitted write."

N2. App identification (ROUTE-DECISION L48 "the one with access to neon-commons"): other installed apps also reach neon-commons (fable-reviewer app from DEX era; possibly Claude app). Wrong app = 404 at step 2, wasted round. Fix text for L48: "the installation named ChatGPT, OpenAI, or Codex Connector (X-OAuth-Client-Id from SOURCE-REPLY-02 belongs to it); if more than one such installation exists, add the repository to each; ignore fable-reviewer, Claude and other apps."

N3. Error sanitization (rule 2, L24-26): HTTPS_PROXY set; Go transport errors can embed proxy URL including user-info. Add: "In any error text, replace the user-info part of any URL with REDACTED." Add interpretation line to rule 4: "A connection or proxy error (no HTTP status) means uploads.github.com not reachable through the proxy; report as ROUTE_UNREACHABLE, not as an auth failure."

VERDICT: SEND (N1-N3 optional, N1 recommended before paste).

Delivery note: this message reached the controller as a teammate message only after the controller's turn ended, with content identical to the copy above.
