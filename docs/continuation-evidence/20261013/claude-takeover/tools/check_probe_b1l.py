"""Save SOURCE-ACTION-REPLY-02 verbatim, check it, and write the route B1-L probe verdict.

Usage: py -3.11 -I tools/check_probe_b1l.py --transcript <session .jsonl> --timestamp <queue enqueue ts>
Inputs: the owner's relayed reply (from the session transcript), the receiver watcher's final line
(logs/fetch-lfs-probe-01.log) and three read-only GitHub reads through the local gh with the required User-Agent.
Writes inbox/SOURCE-ACTION-REPLY-02.json (verbatim, local only), inbox/RECEIVED-ACTION-02.json and
observations/PROBE-B1L-01.json. Refuses to overwrite an existing reply file.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GH = r"C:\Program Files\GitHub CLI\gh.exe"
UA = "User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0"
REPO = "repos/nsahmed23/intune-evidence-custody"
PIN_BYTES = 18445
PIN_SHA256 = "d01a9b0e9cd1506b1ee5d0defcfebf4f377af858ab610d3ec5362623ee0c67c3"
MAIN = "a35da44ca366a0585b0a7224852e1440d209b79a"
BRANCH = "probe-lfs-20261013-01"
BLOCK_DELIVERED_UTC = "2026-10-13T20:44:00Z"  # controller message carrying the FINAL block
LAST_POLL_WITHOUT_BRANCH_UTC = "2026-10-13T20:46:35Z"


def relayed_text(transcript, timestamp):
    for line in transcript.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry.get("timestamp") != timestamp:
            continue
        if entry.get("type") == "queue-operation" and entry.get("operation") == "enqueue":
            return entry["content"]
        if entry.get("type") == "user" and isinstance(entry["message"]["content"], str):
            return entry["message"]["content"]
    raise SystemExit(f"no relayed owner message at {timestamp}")


def gh_json(path, jq):
    env = dict(os.environ, GH_NO_UPDATE_NOTIFIER="1", GH_PROMPT_DISABLED="1")
    result = subprocess.run([GH, "api", "-H", UA, "-H", "Accept: application/vnd.github+json", path, "--jq", jq],
                            capture_output=True, env=env, timeout=120)
    if result.returncode:
        raise SystemExit(f"gh read failed for {path}: {result.stderr.decode('utf-8', 'replace')[:200]}")
    return json.loads(result.stdout)


def check_reply(reply, commit):
    expected_refs = [f"{MAIN}\tHEAD", f"{MAIN}\trefs/heads/main", f"{commit}\trefs/heads/{BRANCH}"]
    build = reply["build"]
    return {
        "preflight_pin": reply["preflight"]["bytes"] == PIN_BYTES and reply["preflight"]["sha256"] == PIN_SHA256
        and reply["preflight"]["size_and_mtime_unchanged"] is True,
        "final_block_used": build["folder"] == "/tmp/lfs-probe-20261013-01",
        "remote_address": build["remote_address"] == "https://github.com/nsahmed23/intune-evidence-custody.git",
        "lfs_object_id": build["lfs_ls_files_line"] == f"{PIN_SHA256} * synthetic-original-work-probe.zip",
        "pointer_blob_130": build["blob_size"] == 130,
        "commit_matches_receiver": build["commit_id"] == commit,
        "lfs_push_ok": reply["lfs_push"]["exit_code"] == 0 and reply["lfs_push"]["attempts"] == 1,
        "git_push_new_branch": reply["git_push"]["exit_code"] == 0 and "[new branch]" in reply["git_push"]["stderr"],
        "refs_expected": reply["confirm"]["ref_lines"] == expected_refs,
        "errors_empty": reply["errors"] == [],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", required=True, type=pathlib.Path)
    parser.add_argument("--timestamp", required=True)
    args = parser.parse_args()
    target = ROOT / "inbox" / "SOURCE-ACTION-REPLY-02.json"
    if target.exists():
        print("REFUSED: inbox/SOURCE-ACTION-REPLY-02.json already exists")
        return 2
    text = relayed_text(args.transcript, args.timestamp)
    data = text.encode("utf-8")
    target.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (ROOT / "inbox" / "RECEIVED-ACTION-02.json").write_text(json.dumps({
        "transcript_timestamp_utc": args.timestamp, "relayed_by": "owner",
        "files": {"SOURCE-ACTION-REPLY-02.json": {"bytes": len(data), "sha256": digest}},
        "note": "Local only: inbox/ is hard-excluded from publication."}, indent=2) + "\n", encoding="utf-8")
    receiver = json.loads((ROOT / "logs" / "fetch-lfs-probe-01.log").read_text(encoding="utf-8").splitlines()[-1])
    commit = receiver["commit"]
    reply_checks = check_reply(json.loads(text), commit)
    refs = gh_json(f"{REPO}/git/refs", '[.[] | "\\(.object.sha) \\(.ref)"]')
    meta = gh_json(f"{REPO}/git/commits/{commit}", "{author, message, parents: [.parents[].sha]}")
    releases = gh_json(f"{REPO}/releases", "[.[] | {id, draft, tag_name, assets: (.assets | length)}]")
    github_checks = {
        "refs_main_unchanged_plus_one_branch": refs == [f"{MAIN} refs/heads/main", f"{commit} refs/heads/{BRANCH}"],
        "commit_by_work_task_probe": meta["author"]["name"] == "Work task probe" and meta["parents"] == [],
        "release_unchanged": releases == [{"id": 411991153, "draft": True, "tag_name": "probe-20261013-01", "assets": 0}],
    }
    receiver_ok = receiver["verdict"] == "PASS" and receiver["sha256"] == PIN_SHA256
    verdict = "PASS" if receiver_ok and all(reply_checks.values()) and all(github_checks.values()) else "FAIL"
    stamped = datetime.datetime.fromisoformat(meta["author"]["date"].replace("Z", "+00:00"))
    earliest = datetime.datetime.fromisoformat(BLOCK_DELIVERED_UTC.replace("Z", "+00:00"))
    latest = datetime.datetime.fromisoformat(receiver["utc"].replace("Z", "+00:00"))
    report = {
        "id": "PROBE-B1L-01", "route": "B1-L (Git LFS)", "verdict": verdict,
        "receiver": {k: receiver[k] for k in ("utc", "polls", "commit", "tree_sha", "tree", "pointer", "verdict",
                                               "downloaded_bytes", "sha256", "zip_members", "path")},
        "source_reply": {"bytes": len(data), "sha256": digest, "checks": reply_checks},
        "github": {"refs": refs, "commit_author": meta["author"], "message": meta["message"], "releases": releases,
                   "checks": github_checks},
        "work_clock": {
            "commit_stamped_utc": meta["author"]["date"], "block_delivered_utc": BLOCK_DELIVERED_UTC,
            "branch_absent_utc": LAST_POLL_WITHOUT_BRANCH_UTC, "branch_seen_utc": receiver["utc"],
            "lag_seconds_min": int((earliest - stamped).total_seconds()),
            "lag_seconds_max": int((latest - stamped).total_seconds()),
            "reading": "The commit is stamped before the block that created it was delivered, so the Work task's clock "
                       "runs behind this PC's by the range above. Work-clock times in earlier replies (for example the "
                       "15:52:05Z boot) carry the same offset if it was the same then.",
        },
        "proves": "The source moved one 18,445-byte file through git and Git LFS into the private repository, and this "
                  "PC downloaded it unchanged (same size and SHA-256 as the source pin).",
        "does_not_prove": "Large files, the LFS quota, Work-task limits on long uploads, or any evidence classification.",
    }
    (ROOT / "observations" / "PROBE-B1L-01.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": verdict, "reply": report["source_reply"], "github": github_checks,
                      "work_clock": {k: v for k, v in report["work_clock"].items() if k != "reading"}}, indent=1))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
