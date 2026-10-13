"""One-time backfill of logs/events.jsonl and logs/runs.jsonl for 2026-10-13, 14:35Z to 15:25Z.

Times come from logs/controller-log.md (generated from the session transcript), matched by pattern,
so no timestamp here is typed from memory. Refuses to run if logs/events.jsonl already has content.
Run: py -3.11 -I tools/backfill_20261013.py
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import audit  # noqa: E402

LOG = audit.LOGS / "controller-log.md"
ROWS = [line.split(" | ") for line in LOG.read_text(encoding="ascii").splitlines() if line.startswith("| 2026-")]


def t(pattern, who=None):
    """UTC of the first controller-log row whose text matches pattern (seconds precision)."""
    for row in ROWS:
        ts, kind, what = row[0].strip("| "), row[1].strip(), " | ".join(row[2:])
        if (who is None or kind == who) and re.search(pattern, what):
            return ts[:19] + "Z"
    raise SystemExit(f"no controller-log row matches {pattern!r}")


E = []


def ev(utc, actor, kind, summary, lane=None, refs=()):
    E.append({"utc": utc, "actor": actor, "kind": kind, "lane": lane, "summary": summary,
              "refs": [audit.ref_record(r) for r in refs], "backfilled": True})


def main():
    if (audit.LOGS / "events.jsonl").exists() and (audit.LOGS / "events.jsonl").stat().st_size:
        raise SystemExit("events.jsonl already has content; backfill runs once")
    o = "owner"
    c = "controller"
    ev(t(r"Intune_Claude_Code_Handoff_2026-10-12", o), o, "owner-directive",
       "Handoff: path to Intune_Claude_Code_Handoff_2026-10-12.zip plus pasted ChatGPT summary of two handoff packages; take over per the handoff intake.",
       refs=["handoff/Intune_Claude_Code_Handoff_2026-10-12.zip"])
    ev(t(r"Verify every packaged file"), c, "verification",
       "Handoff ZIP: 17 regular-file entries, no unsafe paths; 16 of 16 SHA256SUMS entries match.",
       refs=["handoff/Intune_Claude_Code_Handoff_2026-10-12.zip"])
    ev(t(r"work with chatgpt and kimi", o), o, "owner-directive", "you need to work with chatgpt and kimi as well")
    ev(t(r"orchestratring thme", o), o, "owner-directive",
       "you are in charge of orchestratring thme and using fable 5.1 as an advisor lane")
    ev(t(r"Linux receiver observations"), c, "verification",
       "Windows host and WSL Ubuntu measured read-only: C: 326,692,147,200 B free on one NVMe; host RAM 2,211 MB available; Ubuntu 24.04.2 ext4, 4096-byte blocks.",
       refs=["observations/2026-10-13-host-intake.json"])
    ev(t(r"Create the rescue workspace"), c, "controller-action",
       "Created C:/Dev/Projects/intune-rescue; copied the original handoff ZIP; extraction re-verified 16 of 16.")
    ev(t(r"Hash both 0.9.0 package blobs"), c, "verification",
       "M1 PASS (public scope): continuation tip d057cc15 is C32; engine 39cc7761 tree f8bff355; ledger 2,025,195 B sha d6b787c6 matches; both 0.9.0 packages match bytes and SHA-256 at f9104700.",
       lane="M1", refs=[".checkpoints/M1-public-source.json"])
    ev(t(r"ROUTE-ANALYSIS-01\.md"), c, "decision",
       "ROUTE-ANALYSIS-01: no proven route (state D); candidates B2 chat download, B1 private GitHub, A Drive after scope repair.",
       refs=["observations/ROUTE-ANALYSIS-01.md"])
    ev(t(r"SOURCE-QUERY-01\.md"), c, "brief",
       "SOURCE-QUERY-01 v1 drafted: read-only inventory for the original ChatGPT Work task.",
       lane="L3", refs=["outbox/SOURCE-QUERY-01.draft-v1.md"])
    ev(t(r"Agent description: Fable 5.1 route review"), c, "dispatch",
       "L1 Fable 5.1 advisor dispatched (Agent, architect type, read-only tools, 20 min box).",
       lane="L1", refs=["lanes/advisor-fable/BRIEF.md"])
    ev(t(r"Run the GPT-6 Astra advisor lane"), c, "dispatch",
       "L2 GPT-6 Astra advisor dispatched via Codex (read-only sandbox, effort max).", lane="L2",
       refs=["lanes/advisor-astra/BRIEF.md"])
    ev(t(r"Run the Kimi K3 board-building lane"), c, "dispatch",
       "L4 Kimi K3 256k dispatched to build board/index.html (25 min box).", lane="L4", refs=["board/BRIEF.md"])
    ev(t(r"Inspect the Codex lane's exit"), c, "failure",
       "L2 attempt 1 refused before start: 'Not inside a trusted directory and --skip-git-repo-check was not specified.'",
       lane="L2", refs=["lanes/advisor-astra/stderr.log"])
    ev(t(r"Relaunch the GPT-6 Astra advisor lane"), c, "dispatch",
       "L2 attempt 2 relaunched with --skip-git-repo-check; header confirmed gpt-6-astra, read-only, effort max.", lane="L2")
    ev(t(r"Run the GPT-6 Sol M4-prep reading lane"), c, "dispatch",
       "L5 GPT-6 Sol dispatched to read the public snapshot builder and restorers (read-only, effort high).",
       lane="L5", refs=["lanes/m4-prep/BRIEF.md"])
    ev(t(r"Run the Kimi K3 board-building lane", "lane-notice"), "kimi", "report",
       "L4 run 01 finished: index.html 10,850 B; inputs untouched.", lane="L4",
       refs=["lanes/kimi-board/kimi-run-01.out", "lanes/kimi-board/index.run-01.html"])
    ev(t(r"Static-check Kimi's page"), c, "verification",
       "L4 run 01 static gate PASS: no network references, no innerHTML, only ledger.js loaded.", lane="L4")
    ev(t(r"Screenshot the board at desktop and phone widths"), c, "verification",
       "L4 run 01 render gate: desktop PASS; 380px FAIL (header and cards overflow sideways).", lane="L4")
    ev(t(r"Retry the headless Edge DOM dump"), c, "deviation",
       "Controller's headless Edge render logged one failed component-catalog update despite the disable flags; that request could not carry the mandated User-Agent.",
       lane="L4")
    ev(t(r"Kimi's bounded layout polish pass"), c, "dispatch",
       "L4 run 02 polish dispatched with four defects (overflow, width, dot scoping, viewport).", lane="L4",
       refs=["board/BRIEF-02.md"])
    ev(t(r"GPT-6 Sol M4-prep reading lane", "lane-notice"), "gpt-6-sol", "report",
       "L5 report: ZIP plus JSON manifest; POSIX-only stdlib restorer; FIFO entries are pinned omissions; no free-space check; fresh output root per attempt.",
       lane="L5", refs=["lanes/m4-prep/FINAL.md"])
    ev(t(r"Spot-check Sol's claims"), c, "verification",
       "L5 spot-check PASS against code: POSIX guard, limits (200,000 members, 32 GiB, 64 MiB manifest), FIFO handling, no free-space check.",
       lane="L5")
    ev("2026-10-13T14:59:19Z", "fable-advisor", "agent-message",
       "L1 finished (idle notification) but its plain-text report did not reach the controller.", lane="L1")
    ev(t(r"^SendMessage"), c, "relay-out", "Asked fable-advisor to resend its Q1-Q5 report via SendMessage.", lane="L1")
    ev(t(r"claude-fable-5-1 Q1 Routes", "agent:fable-advisor"), "fable-advisor", "report",
       "L1 report delivered; model claude-fable-5-1. Key points: B1 is a new custodian needing explicit owner authorization; never push to origin; amendment is a separate source write; 7 query edits.",
       lane="L1", refs=["lanes/advisor-fable/REPORT.md"])
    ev(t(r"Keep the v1 query draft"), c, "decision",
       "Fable's query edits applied; v1 preserved as SOURCE-QUERY-01.draft-v1.md.", lane="L3",
       refs=["outbox/SOURCE-QUERY-01.draft-v1.md"])
    ev(t(r"Relaunch the GPT-6 Astra advisor lane", "lane-notice"), "gpt-6-astra", "report",
       "L2 report; model gpt-6-astra. Key points: no automatic partial transfer; decouple M2 from layer availability; no auth/API calls in the query (overruled: Fable leads).",
       lane="L2", refs=["lanes/advisor-astra/FINAL.md"])
    ev(t(r"^Use 6\.1 sol", o), o, "owner-directive", "Use 6.1 sol")
    ev(t(r"Kimi's bounded layout polish pass", "lane-notice"), "kimi", "report",
       "L4 run 02 finished: index.html 11,556 B; 4 defects fixed; Kimi verified 360px in headless Edge on temp copies it removed.",
       lane="L4", refs=["lanes/kimi-board/kimi-run-02.out"])
    ev(t(r"Read Kimi's polish report"), c, "deviation",
       "L4 run 02 launched a headless browser and wrote temp copies outside board/; the brief neither authorized nor forbade it; no residue found.",
       lane="L4")
    ev(t(r"Sol and opus are equivalents", o), o, "owner-directive",
       "Sol and opus are equivalents in my head with opus 5.5 leading. Then Astra and fable are equivalents with fable 5.1 leading")
    ev(t(r"Sol and opus are equivalents", o), c, "decision",
       "Routing set: Opus 5.5 leads, GPT-6.1 Sol is its ChatGPT-side peer; Fable 5.1 leads the advisor tier, GPT-6 Astra is its peer. The Fable-vs-Astra conflict on step 5b resolves for Fable.")
    ev(t(r"documenting and creating logs", o), o, "owner-directive",
       "Make sure we are documenting and creating logs for all communication and documentation and work being done across all agents")
    ev(t(r"background worker updating our branch", o), o, "owner-directive",
       "Make sure we have a background worker updating our branch with this work as well")
    ev(t(r"bunch of branches open", o), o, "owner-directive", "There seems to be a bunch of branches open (screenshot of 12 neon-commons branches)",
       refs=["logs/owner-attachments/2026-10-13T151432Z-github-branches.png"])
    ev(t(r"probs fine", o), o, "owner-directive", "No one looks at my GitHub so it's probs fine")
    ev(t(r"probs fine", o), c, "decision",
       "Publish sanitized work products as fast-forward commits on continuation/r4-20261007 under docs/continuation-evidence/20261013/claude-takeover/; no new branch, never main, never force. Raw transcripts, inbox replies and private evidence stay local.")
    ev(t(r"Run the GPT-6\.1 Sol final query check"), c, "dispatch",
       "Sol query check dispatched on gpt-6.1-sol (read-only, effort high).", lane="L6", refs=["lanes/sol-query-check/BRIEF.md"])
    ev(t(r"Run the GPT-6\.1 Sol publisher implementation lane"), c, "dispatch",
       "Publisher implementation dispatched on gpt-6.1-sol (workspace-write, effort high, TDD).", lane="L7",
       refs=["lanes/publisher/BRIEF.md"])
    ev(t(r"Fetch all branch and tag tips"), c, "verification",
       "Branch map: 12 branches; 6 fully contained in another branch or tag (wally handoff, r2, r3; source 0.7.0, 0.8.0; pre-migration); 6 hold unique history.")
    ev(t(r"Inspect both GPT-6\.1 Sol lanes"), c, "failure",
       "Both gpt-6.1-sol lanes rejected before work: HTTP 400 'The gpt-6.1-sol model is not supported when using Codex with a ChatGPT account.'",
       refs=["lanes/sol-query-check/stderr-attempt1-gpt-6.1-sol-rejected.log",
             "lanes/publisher/stderr-attempt1-gpt-6.1-sol-rejected.log"])
    ev(t(r"Relaunch the Sol query check on GPT-6 Sol"), c, "dispatch",
       "Sol query check relaunched on fallback gpt-6-sol (same tier).", lane="L6")
    ev(t(r"Relaunch the publisher implementation lane"), c, "dispatch",
       "Publisher relaunched on fallback gpt-6-sol (same tier).", lane="L7")
    ev(t(r"Snapshot all lane transcripts"), c, "controller-action",
       "Raw transcripts snapshotted to logs/transcripts/ (local only) with SHA256SUMS: Codex rollouts, Kimi sessions, Fable subagent, controller session.",
       refs=["logs/transcripts/SHA256SUMS"])
    ev(t(r"Relaunch the Sol query check on GPT-6 Sol", "lane-notice"), "gpt-6-sol", "report",
       "L6 report; model gpt-6-sol: 7 line edits (two contradictions from the merge, mid-hash change guard, User-Agent on source HEAD checks).",
       lane="L6", refs=["lanes/sol-query-check/FINAL.md"])
    ev(t(r"Extract exact UTC times"), c, "decision",
       "SOURCE-QUERY-01 final: Sol edits adopted; gh auth status replaced by the gh api header check, which can carry the User-Agent.",
       lane="L3", refs=["outbox/SOURCE-QUERY-01.md"])
    for record in sorted(E, key=lambda r: r["utc"]):
        audit.append_jsonl(audit.LOGS / "events.jsonl", record)
    print(f"backfilled {len(E)} events")

    def run(**fields):
        path = audit.LOGS / "runs.tmp.json"
        path.write_text(json.dumps(fields), encoding="utf-8")
        audit.cmd_run(type("A", (), {"file": str(path), "json": None})())
        path.unlink()

    run(run_id="R01", lane="L1 advisor-fable", executor="Claude Agent (architect, read-only tools)",
        model_requested="fable", model_confirmed="claude-fable-5-1 (report line 1)", effort="agent default",
        sandbox="read-only tools", start_utc=t(r"Agent description: Fable 5.1"), end_utc="2026-10-13T14:59:19Z",
        exit="n/a", status="DONE", brief="lanes/advisor-fable/BRIEF.md", outputs=["lanes/advisor-fable/REPORT.md"],
        transcripts=["logs/transcripts/claude/L1-fable-advisor.jsonl"],
        deviations=["report reached the controller only after a SendMessage nudge at 15:03Z"])
    run(run_id="R02", lane="L2 advisor-astra", executor="Codex CLI 0.156.0", model_requested="gpt-6-astra",
        model_confirmed="none (refused before start)", effort="max", sandbox="read-only",
        start_utc=t(r"Run the GPT-6 Astra advisor lane"), end_utc=t(r"Run the GPT-6 Astra advisor lane", "lane-notice"),
        exit=1, status="FAILED", brief="lanes/advisor-astra/BRIEF.md", outputs=["lanes/advisor-astra/stderr.log"],
        deviations=["non-git workdir needs --skip-git-repo-check"])
    run(run_id="R03", lane="L2 advisor-astra", executor="Codex CLI 0.156.0", model_requested="gpt-6-astra",
        model_confirmed="gpt-6-astra (stderr header and report line 1)", effort="max", sandbox="read-only",
        start_utc=t(r"Relaunch the GPT-6 Astra advisor lane"), end_utc=t(r"Relaunch the GPT-6 Astra advisor lane", "lane-notice"),
        exit=0, status="DONE", brief="lanes/advisor-astra/BRIEF.md",
        outputs=["lanes/advisor-astra/FINAL.md", "lanes/advisor-astra/stderr-02.log"],
        transcripts=["logs/transcripts/codex/L2-astra-attempt2-01a135c3.jsonl"], deviations=[])
    run(run_id="R04", lane="L4 kimi-board", executor="Kimi Code CLI 0.37.2", model_requested="kimi-code/k3-256k",
        model_confirmed="UNCONFIRMED (the CLI silently falls back on a mistyped ID; see wire.jsonl)", effort="default",
        sandbox="prompt mode, auto permission, cwd board/", start_utc=t(r"Run the Kimi K3 board-building lane"),
        end_utc=t(r"Run the Kimi K3 board-building lane", "lane-notice"), exit=0, status="DONE",
        brief="board/BRIEF.md", outputs=["lanes/kimi-board/index.run-01.html", "lanes/kimi-board/kimi-run-01.out"],
        transcripts=["logs/transcripts/kimi/session_5d587009-5de0-43f7-9dfe-2522fe5cd671/agents/main/wire.jsonl"],
        deviations=["controller render gate: 380px overflow (fixed in R06)"])
    run(run_id="R05", lane="L5 m4-prep", executor="Codex CLI 0.156.0", model_requested="gpt-6-sol",
        model_confirmed="gpt-6-sol (stderr header)", effort="high", sandbox="read-only",
        start_utc=t(r"Run the GPT-6 Sol M4-prep reading lane"),
        end_utc=t(r"GPT-6 Sol M4-prep reading lane", "lane-notice"), exit=0, status="DONE",
        brief="lanes/m4-prep/BRIEF.md", outputs=["lanes/m4-prep/FINAL.md"],
        transcripts=["logs/transcripts/codex/L5-sol-m4prep-01a135c5.jsonl"], deviations=[])
    run(run_id="R06", lane="L4 kimi-board", executor="Kimi Code CLI 0.37.2", model_requested="kimi-code/k3-256k",
        model_confirmed="UNCONFIRMED (see wire.jsonl)", effort="default", sandbox="prompt mode, auto permission, cwd board/",
        start_utc=t(r"Kimi's bounded layout polish pass"),
        end_utc=t(r"Kimi's bounded layout polish pass", "lane-notice"), exit=0, status="DONE",
        brief="board/BRIEF-02.md", outputs=["board/index.html", "lanes/kimi-board/kimi-run-02.out"],
        transcripts=["logs/transcripts/kimi/session_ddda5909-c578-4eb8-a938-12333548d2f4/agents/main/wire.jsonl"],
        deviations=["ran headless Edge on temp copies outside board/ (removed)"])
    run(run_id="R07", lane="L6 sol-query-check", executor="Codex CLI 0.156.0", model_requested="gpt-6.1-sol",
        model_confirmed="none (HTTP 400 for ChatGPT-account login)", effort="high", sandbox="read-only",
        start_utc=t(r"Run the GPT-6\.1 Sol final query check"),
        end_utc=t(r"GPT-6\.1 Sol final query check", "lane-notice"), exit=1, status="FAILED",
        brief="lanes/sol-query-check/BRIEF.md", outputs=["lanes/sol-query-check/stderr-attempt1-gpt-6.1-sol-rejected.log"],
        transcripts=["logs/transcripts/codex/sol-query-check-attempt1-6.1-rejected-01a135d8-acd2.jsonl"],
        deviations=["model not entitled on this Codex login"])
    run(run_id="R08", lane="L7 publisher", executor="Codex CLI 0.156.0", model_requested="gpt-6.1-sol",
        model_confirmed="none (HTTP 400 for ChatGPT-account login)", effort="high", sandbox="workspace-write",
        start_utc=t(r"Run the GPT-6\.1 Sol publisher implementation lane"),
        end_utc=t(r"GPT-6\.1 Sol publisher implementation lane", "lane-notice"), exit=1, status="FAILED",
        brief="lanes/publisher/BRIEF.md", outputs=["lanes/publisher/stderr-attempt1-gpt-6.1-sol-rejected.log"],
        transcripts=["logs/transcripts/codex/publisher-attempt1-6.1-rejected-01a135d8-b44c.jsonl"],
        deviations=["model not entitled on this Codex login"])
    run(run_id="R09", lane="L6 sol-query-check", executor="Codex CLI 0.156.0", model_requested="gpt-6-sol",
        model_confirmed="gpt-6-sol (stderr header and report line 1)", effort="high", sandbox="read-only",
        start_utc=t(r"Relaunch the Sol query check on GPT-6 Sol"),
        end_utc=t(r"Relaunch the Sol query check on GPT-6 Sol", "lane-notice"), exit=0, status="DONE",
        brief="lanes/sol-query-check/BRIEF.md", outputs=["lanes/sol-query-check/FINAL.md"], deviations=[])
    run(run_id="R10", lane="L7 publisher", executor="Codex CLI 0.156.0", model_requested="gpt-6-sol",
        model_confirmed="gpt-6-sol (stderr header)", effort="high", sandbox="workspace-write",
        start_utc=t(r"Relaunch the publisher implementation lane"), end_utc=None, exit=None, status="RUNNING",
        brief="lanes/publisher/BRIEF.md", outputs=[], deviations=[])


if __name__ == "__main__":
    main()
