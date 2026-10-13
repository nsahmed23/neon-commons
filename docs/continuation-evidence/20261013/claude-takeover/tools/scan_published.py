"""Deterministic privacy scan plus file-hash manifest of a publication candidate directory.

Usage: py -3.11 -I tools/scan_published.py <dir> --rules <file> [--allow <file>] [--json-out <file>]

Rules file: lines `id<TAB>severity<TAB>regex`, `#` comments; append-only (see tools/publish-scan-rules.txt).
Allow file: lines `rule<TAB>relpath<TAB>sha256 of the exact line text`; suppresses that one line only, so an
edited line fires again. Every file is hashed; archives and images (.zip .png .jpg .jpeg .gif .webp .pdf) are
not content-scanned. A hit prints `SEVERITY rule path:line masked`, never the full match.
The JSON `files` map is the review receipt's file set that publish_branch.py --review-receipt compares against.
Exit 0: no unsuppressed HIGH. 1: unsuppressed HIGH. 2: rules unreadable or fewer than 15 rules (truncated).
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys

MIN_RULES = 15
BINARY_SUFFIXES = {".zip", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"}


def mask(text):
    return text[:6] + "***" if len(text) > 6 else "***"


def load_rules(path):
    rules = []
    for raw in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = raw.split("\t", 2)
        if len(parts) != 3 or not all(parts):
            raise ValueError(f"malformed rule line: {raw[:40]}")
        rid, severity, regex = parts
        rules.append((rid, severity.upper(), re.compile(regex)))
    return rules


def load_allow(path):
    allowed = set()
    if not path:
        return allowed
    for raw in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = raw.rstrip("\r\n").split("\t")
        if len(parts) == 3:
            allowed.add((parts[0], parts[1], parts[2].strip().lower()))
    return allowed


def scan(root, rules, allowed):
    files, hits, suppressed = {}, [], 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        files[rel] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            line_hash = hashlib.sha256(line.encode("utf-8")).hexdigest()
            for rid, severity, rx in rules:
                for match in rx.finditer(line):
                    if (rid, rel, line_hash) in allowed:
                        suppressed += 1
                        continue
                    hits.append({"file": rel, "line": number, "rule": rid, "severity": severity,
                                 "match": mask(match.group(0))})
    return files, hits, suppressed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dir", type=pathlib.Path)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--allow")
    parser.add_argument("--json-out")
    args = parser.parse_args()
    if not args.dir.is_dir():
        parser.error("dir must be a directory")
    try:
        rules = load_rules(args.rules)
        allowed = load_allow(args.allow)
    except (OSError, ValueError, re.error) as exc:
        print(f"RULES-ERROR {exc}", file=sys.stderr)
        return 2
    if len(rules) < MIN_RULES:
        print(f"RULES-ERROR only {len(rules)} rules parsed, need at least {MIN_RULES} (truncated rules file)",
              file=sys.stderr)
        return 2
    files, hits, suppressed = scan(args.dir, rules, allowed)
    high = sum(1 for h in hits if h["severity"] == "HIGH")
    for h in hits:
        print(f"{h['severity']} {h['rule']} {h['file']}:{h['line']} {h['match']}")
    print(f"SCAN files {len(files)} rules {len(rules)} hits {len(hits)} high {high} suppressed {suppressed}")
    if args.json_out:
        summary = {"files": files, "rules": len(rules), "hits": hits, "high": high}
        pathlib.Path(args.json_out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 1 if high else 0


if __name__ == "__main__":
    sys.exit(main())
