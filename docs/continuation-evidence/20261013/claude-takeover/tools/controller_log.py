"""Timestamped controller log from a Claude Code session transcript (JSONL).

Ported from pharos-lab-olr r1-day/controller_log.py and extended for this workspace. One row per:
- owner message (verbatim up to 2,000 chars, including messages sent mid-turn; longer relays are withheld and
  replaced by a length and sha256 prefix marker, because they may carry pasted third-party text);
- agent message (teammate or subagent reports delivered to the controller);
- controller reply to the owner (assistant text, up to 600 chars);
- controller tool call (tool name plus its description or target);
- lane notification (background task completed or failed, with its summary line);
- tool error (first line).
Tool outputs are not copied; lane outputs live under lanes/ and logs/transcripts/.

Usage: py -3.11 -I tools/controller_log.py --transcript <session.jsonl> [--since ISO] [--until ISO] [--out PATH]
Agent-permission posture terms are replaced with [posture redacted] in every row.
Output is ASCII-only (non-ASCII is backslash-escaped), so it renders anywhere.
"""
import argparse
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_PREFIXES = ("<command-", "<local-command", "Caveat:", "This session is being continued", "[Request interrupted",
                 "<user-prompt-submit-hook>", "Base directory for this skill", "Tool loaded.")
MIDTURN = re.compile(r"The user sent a new message while you were working:\s*(.*?)(?:\n\s*This is how Claude Code surfaces|\Z)", re.S)
AGENT = re.compile(r"<(?:agent|teammate)-message[^>]*?(?:from|teammate_id)=\"([^\"]+)\"[^>]*>(.*?)</(?:agent|teammate)-message>", re.S)
TASK = re.compile(r"<task-notification>.*?<status>(.*?)</status>.*?<summary>(.*?)</summary>", re.S)


OWNER_LIMIT = 2000
POSTURE = re.compile(
    r"danger-full-access|approval[ ]never|approval_policy(?:\s*=\s*\"never\")?|dangerously-skip-permissions"
    r"|bypass[ ]?permissions", re.I)
REDACTION = "[posture redacted]"


def clean(text, limit):
    text = " ".join(str(text).split())
    text = POSTURE.sub(REDACTION, text).replace("|", "/")
    text = text.encode("ascii", "backslashreplace").decode("ascii")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def row_text(who, what):
    """Row text for one entry; long owner relays are withheld, with a hash so the paste stays identifiable."""
    if who == "owner":
        collapsed = " ".join(str(what).split())
        if len(collapsed) > OWNER_LIMIT:
            digest = hashlib.sha256(str(what).encode("utf-8")).hexdigest()[:16]
            return (f"[owner relay withheld from the published log: {len(collapsed)} chars, sha256 {digest}; "
                    "full text kept in the local transcript]")
        return clean(what, OWNER_LIMIT)
    return clean(what, 600)


def texts_of(content):
    if isinstance(content, str):
        return [content]
    return [b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text"]


def tool_target(inp):
    for key in ("description", "file_path", "pattern", "url", "query", "skill", "prompt", "command"):
        if isinstance(inp, dict) and inp.get(key):
            return f"{key}: {inp[key]}"
    return ""


def error_first_line(block):
    content = block.get("content")
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    lines = [ln for ln in str(content or "").splitlines() if ln.strip()]
    if not lines:
        return "(empty error)"
    return f"{lines[0]}: {lines[1]}" if lines[0].startswith("Exit code") and len(lines) > 1 else lines[0]


def classify_user_text(text):
    """Yield (who, what) rows for one user-side text block."""
    rows = []
    for match in MIDTURN.finditer(text):
        rows.append(("owner", match.group(1).strip()))
    for sender, body in AGENT.findall(text):
        rows.append((f"agent:{sender}", body.strip()))
    for status, summary in TASK.findall(text):
        rows.append(("lane-notice", f"{status.strip()}: {summary.strip()}"))
    if rows:
        return rows
    stripped = text.lstrip()
    if not stripped or stripped.startswith(SKIP_PREFIXES) or stripped.startswith("<system-reminder>"):
        return []
    return [("owner", text)]


def rows_from(transcript, since, until):
    seen = set()
    with open(transcript, encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = entry.get("timestamp")
            if not ts or not (since <= ts < until) or entry.get("isSidechain"):
                continue
            message = entry.get("message") or {}
            content = message.get("content")
            attachment = entry.get("attachment") or {}
            if entry.get("type") == "attachment" and attachment.get("type") == "queued_command":
                prompt = attachment.get("prompt")
                if isinstance(prompt, list):
                    prompt = " ".join(b.get("text", "") for b in prompt if isinstance(b, dict))
                for who, what in classify_user_text(str(prompt or "")) or [("owner", str(prompt or ""))]:
                    key = (who, " ".join(what.split())[:200])
                    if not what.strip() or (who == "owner" and key in seen):
                        continue
                    seen.add(key)
                    yield ts, who, row_text(who, what)
                continue
            if entry.get("type") == "user":
                if entry.get("isMeta") or entry.get("isCompactSummary"):
                    continue
                if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                            yield ts, "error", clean(error_first_line(block), 300)
                    continue
                for text in texts_of(content):
                    for who, what in classify_user_text(text):
                        # Only owner messages are replayed by the transcript once delivered; repeated lane
                        # notices and agent messages are separate events and must all be kept.
                        key = (who, " ".join(what.split())[:200])
                        if who == "owner" and key in seen:
                            continue
                        seen.add(key)
                        yield ts, who, row_text(who, what)
            elif entry.get("type") == "assistant" and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        yield ts, "controller", clean(f"{block.get('name')} {tool_target(block.get('input'))}", 300)
                    elif block.get("type") == "text" and block.get("text", "").strip():
                        yield ts, "controller-says", clean(block["text"], 600)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--since", default="2026-10-13T00:00:00Z")
    parser.add_argument("--until", default="2100-01-01T00:00:00Z")
    parser.add_argument("--out", default=str(ROOT / "logs" / "controller-log.md"))
    args = parser.parse_args()
    rows = list(rows_from(args.transcript, args.since, args.until))
    rows.sort(key=lambda r: r[0])
    kinds = {}
    for _, who, _ in rows:
        kind = who.split(":")[0]
        kinds[kind] = kinds.get(kind, 0) + 1
    out = [f"# Controller log, {args.since} to {args.until}", "",
           "Generated by `tools/controller_log.py` from the controller session transcript",
           f"(`{pathlib.PurePath(args.transcript).name}`). Rows: owner messages, agent messages, controller replies,",
           "controller tool calls, lane notifications and tool errors. Tool outputs are not copied; lane outputs are",
           "under `lanes/`, raw transcripts under `logs/transcripts/` (local only).", "",
           "Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())), "",
           "| UTC | who | what |", "|---|---|---|"]
    out += [f"| {ts} | {who} | {what} |" for ts, who, what in rows]
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(out) + "\n", encoding="ascii", newline="\n")
    print(f"CONTROLLER-LOG rows {len(rows)} " + " ".join(f"{k}={v}" for k, v in sorted(kinds.items())))


if __name__ == "__main__":
    main()
