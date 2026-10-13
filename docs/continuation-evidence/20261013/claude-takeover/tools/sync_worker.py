"""Background sync worker: keeps the local audit trail current. It never pushes.

Each cycle (every --interval seconds until --hours elapse, or until tools/STOP_SYNC exists):
  1. logs/controller-log.md from the controller session transcript
  2. rolling local snapshot of that transcript (byte-prefix checked; never published)
  3. board/ledger.js from ledger/ledger.json
  4. logs/AUDIT-TABLES.md from logs/events.jsonl and logs/runs.jsonl
  5. publish_branch.py --dry-run against the local branch ref (no fetch), which only reports what a
     publish would contain.
Publishing is a separate, owner-gated step: export the candidate with publish_branch.py --export-dir, scan it
with scan_published.py, get the owner's review, then push with --review-receipt bound to that exact file set.
Every step's exit code and output tail go to logs/sync-worker.log (local only). A failed step is
logged and the cycle continues; the next cycle retries. Git never prompts: GIT_TERMINAL_PROMPT=0 and
GCM_INTERACTIVE=never make a missing credential fail fast instead of hanging a background job.

Usage: py -3.11 -I tools/sync_worker.py --transcript <session.jsonl> [--interval 600] [--hours 12] [--once]
Stop early: create tools/STOP_SYNC (any content). The worker deletes nothing.
"""
import argparse
import datetime
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
LOG = ROOT / "logs" / "sync-worker.log"
STOP = TOOLS / "STOP_SYNC"
BRANCH = "continuation/r4-20261007"
PREFIX = "docs/continuation-evidence/20261013/claude-takeover"


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(line):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{utc_now()} {line}\n")


def step(cycle, name, argv, env):
    try:
        result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
        tail = " / ".join((result.stdout + result.stderr).strip().splitlines()[-4:])
        log(f"cycle={cycle} step={name} exit={result.returncode} tail={tail[:600]}")
        return result.returncode, result.stdout
    except subprocess.TimeoutExpired:
        log(f"cycle={cycle} step={name} exit=TIMEOUT after 900 s")
        return -1, ""


def cycle_once(cycle, args, env):
    py = [sys.executable, "-I"]
    step(cycle, "controller-log", py + [str(TOOLS / "controller_log.py"), "--transcript", args.transcript], env)
    step(cycle, "snapshot", py + [str(TOOLS / "audit.py"), "snapshot", args.transcript,
                                  f"claude/L0-controller-{pathlib.Path(args.transcript).stem[:8]}.jsonl", "--rolling"], env)
    step(cycle, "ledger-js", py + [str(TOOLS / "make_ledger_js.py"), str(ROOT)], env)
    step(cycle, "tables", py + [str(TOOLS / "audit.py"), "tables"], env)
    publish = py + [str(TOOLS / "publish_branch.py"), "--root", str(ROOT), "--repo", str(ROOT / "source.git"),
                    "--branch", BRANCH, "--prefix", PREFIX, "--allowlist", str(TOOLS / "publish-allowlist.txt"),
                    "--message", f"docs(takeover): sync audit trail {utc_now()}", "--dry-run"]
    step(cycle, "publish-dry-run", publish, env)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--interval", type=int, default=600)
    parser.add_argument("--hours", type=float, default=12.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", PYTHONUTF8="1")
    deadline = time.monotonic() + args.hours * 3600
    log(f"start pid={os.getpid()} interval={args.interval}s hours={args.hours}")
    cycle = 0
    while True:
        cycle += 1
        cycle_once(cycle, args, env)
        if args.once:
            break
        next_at = time.monotonic() + args.interval
        while time.monotonic() < min(next_at, deadline):
            if STOP.exists():
                log(f"stop requested via {STOP.name} after cycle {cycle}")
                return 0
            time.sleep(5)
        if time.monotonic() >= deadline:
            log(f"time limit reached after cycle {cycle}")
            return 0
    log(f"single cycle done (cycle {cycle})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
