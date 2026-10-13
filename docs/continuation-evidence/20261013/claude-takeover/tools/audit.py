"""Audit trail for the Intune rescue workspace: events, lane runs, transcript snapshots, tables.

Every communication and every piece of work across all lanes lands here:
- logs/events.jsonl   append-only; one line per owner directive, brief, dispatch, report, relay,
                      controller action, verification, decision or deviation. Time comes from the
                      system clock, never typed by hand.
- logs/runs.jsonl     one record per lane run (model requested and confirmed, effort, sandbox,
                      brief, outputs, transcript, exit, deviations); upserted by run_id.
- logs/transcripts/   byte copies of raw transcripts (Codex rollouts, Kimi sessions, Claude agent
                      and controller transcripts) with SHA256SUMS. Never overwritten: a changed
                      source gets a new timestamped name.
- logs/AUDIT-TABLES.md generated from the two JSONL files.

Usage (run with py -3.11 -I from anywhere; ROOT defaults to this file's parent's parent):
  audit.py event --actor controller --kind decision --summary "..." [--lane L2] [--ref PATH ...]
  audit.py run --file run.json            (or --json '{...}')
  audit.py snapshot SOURCE NAME [--rolling]  copy a transcript into logs/transcripts/NAME
  audit.py tables
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
EVENT_KINDS = {
    "owner-directive", "brief", "dispatch", "report", "relay-out", "relay-in", "agent-message",
    "controller-action", "verification", "decision", "deviation", "failure", "checkpoint",
}
RUN_REQUIRED = {"run_id", "lane", "executor", "model_requested", "status"}


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ref_record(raw):
    path = pathlib.Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    if path.is_file():
        rel = path.relative_to(ROOT).as_posix() if ROOT in path.parents else str(path)
        return {"path": rel, "bytes": path.stat().st_size, "sha256": sha256_of(path)}
    return {"path": raw, "missing": True}


def append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def cmd_event(args):
    if args.kind not in EVENT_KINDS:
        raise SystemExit(f"unknown kind {args.kind!r}; allowed: {sorted(EVENT_KINDS)}")
    record = {"utc": args.utc or utc_now(), "actor": args.actor, "kind": args.kind, "lane": args.lane,
              "summary": args.summary, "refs": [ref_record(r) for r in args.ref or []]}
    if args.utc:
        record["backfilled"] = True
    append_jsonl(LOGS / "events.jsonl", record)
    print(f"event {record['utc']} {args.kind} {args.lane or '-'}")


def cmd_run(args):
    record = json.loads(pathlib.Path(args.file).read_text(encoding="utf-8") if args.file else args.json)
    missing = RUN_REQUIRED - record.keys()
    if missing:
        raise SystemExit(f"run record missing {sorted(missing)}")
    for key in ("brief", "outputs", "transcripts"):
        if key in record:
            values = record[key] if isinstance(record[key], list) else [record[key]]
            record[key] = [ref_record(v) if isinstance(v, str) else v for v in values]
    record["recorded_utc"] = utc_now()
    runs = [r for r in read_jsonl(LOGS / "runs.jsonl") if r.get("run_id") != record["run_id"]]
    runs.append(record)
    runs.sort(key=lambda r: r["run_id"])
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "runs.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in runs),
                                     encoding="utf-8", newline="\n")
    print(f"run {record['run_id']} {record['status']} ({len(runs)} runs)")


def is_byte_prefix(old_path, new_path):
    """True when old_path's bytes are exactly the first bytes of new_path (append-only growth)."""
    with open(old_path, "rb") as old, open(new_path, "rb") as new:
        for chunk in iter(lambda: old.read(1 << 20), b""):
            if new.read(len(chunk)) != chunk:
                return False
    return True


def cmd_snapshot(args):
    source = pathlib.Path(args.source)
    target_dir = LOGS / "transcripts"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / args.name
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".partial")
    shutil.copyfile(source, staging)  # freeze first: a live transcript keeps growing while we read it
    digest = sha256_of(staging)
    if target.exists():
        if sha256_of(target) == digest:
            staging.unlink()
            print(f"unchanged {args.name}")
            return
        if args.rolling:
            if not is_byte_prefix(target, staging):
                staging.unlink()
                raise SystemExit(f"{args.name}: stored copy is not a prefix of the source; refusing to overwrite")
        else:
            stem, dot, ext = target.name.rpartition(".")
            stamp = utc_now().replace(":", "")
            target = target.with_name(f"{stem}.{stamp}.{ext}" if dot else f"{target.name}.{stamp}")
    staging.replace(target)
    name = target.relative_to(target_dir).as_posix()
    append_jsonl(target_dir / "SNAPSHOTS.jsonl", {"utc": utc_now(), "name": name, "source": str(source),
                                                  "bytes": target.stat().st_size, "sha256": digest,
                                                  "rolling": bool(args.rolling)})
    latest = {}
    for record in read_jsonl(target_dir / "SNAPSHOTS.jsonl"):
        latest[record["name"]] = record["sha256"]
    (target_dir / "SHA256SUMS").write_text("".join(f"{sha}  {n}\n" for n, sha in sorted(latest.items())),
                                           encoding="utf-8", newline="\n")
    print(f"snapshot {name} {target.stat().st_size} B")


def cell(value, limit=160):
    text = " ".join(str(value if value is not None else "").split()).replace("|", "/")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def cmd_tables(_args):
    runs = read_jsonl(LOGS / "runs.jsonl")
    events = read_jsonl(LOGS / "events.jsonl")
    out = ["# Audit tables", "", f"Generated {utc_now()} by tools/audit.py from logs/runs.jsonl and logs/events.jsonl.", "",
           f"## Lane runs ({len(runs)})", "",
           "| run | lane | executor | model requested / confirmed | effort | sandbox | start / end UTC | exit | status | deviations |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        out.append("| " + " | ".join(cell(x) for x in (
            r["run_id"], r["lane"], r["executor"],
            f"{r['model_requested']} / {r.get('model_confirmed', 'UNCONFIRMED')}",
            r.get("effort"), r.get("sandbox"), f"{r.get('start_utc')} / {r.get('end_utc')}",
            r.get("exit"), r["status"], "; ".join(r.get("deviations", [])) or "none")) + " |")
    out += ["", f"## Events ({len(events)})", "", "| UTC | actor | kind | lane | summary | refs |", "|---|---|---|---|---|---|"]
    for e in events:
        refs = ", ".join(r.get("path", "") for r in e.get("refs", []))
        mark = " (backfilled)" if e.get("backfilled") else ""
        out.append("| " + " | ".join(cell(x, 220) for x in (
            e["utc"] + mark, e["actor"], e["kind"], e.get("lane") or "-", e["summary"], refs)) + " |")
    (LOGS / "AUDIT-TABLES.md").write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"tables: {len(runs)} runs, {len(events)} events")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    ev = sub.add_parser("event")
    ev.add_argument("--actor", required=True)
    ev.add_argument("--kind", required=True)
    ev.add_argument("--summary", required=True)
    ev.add_argument("--lane")
    ev.add_argument("--ref", action="append")
    ev.add_argument("--utc", help="only for backfilling a past event; marks it backfilled")
    rn = sub.add_parser("run")
    group = rn.add_mutually_exclusive_group(required=True)
    group.add_argument("--file")
    group.add_argument("--json")
    sn = sub.add_parser("snapshot")
    sn.add_argument("source")
    sn.add_argument("name")
    sn.add_argument("--rolling", action="store_true",
                    help="append-only source: replace the stored copy only if it is a byte prefix of the source")
    sub.add_parser("tables")
    args = parser.parse_args()
    {"event": cmd_event, "run": cmd_run, "snapshot": cmd_snapshot, "tables": cmd_tables}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
