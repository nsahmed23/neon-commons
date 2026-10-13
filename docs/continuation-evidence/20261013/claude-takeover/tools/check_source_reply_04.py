"""Save SOURCE-REPLY-04 verbatim from the session transcript and check it against the expected answers.

Usage: py -3.11 -I tools/check_source_reply_04.py --transcript <session .jsonl> --timestamp <owner message ts>
Writes inbox/SOURCE-REPLY-04.json (verbatim, local only), inbox/RECEIVED-04.json and
observations/SOURCE-REPLY-04-CHECK.json. Refuses to overwrite an existing reply file.
"""
import argparse
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPECTED_RELEASE = {"draft": True, "id": 411991153, "tag_name": "probe-20261013-01"}
EXPECTED_REFS = [("a35da44ca366a0585b0a7224852e1440d209b79a", "HEAD"),
                 ("a35da44ca366a0585b0a7224852e1440d209b79a", "refs/heads/main")]


def owner_text(transcript, timestamp):
    for line in transcript.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry.get("type") != "user" or entry.get("timestamp") != timestamp:
            continue
        content = entry["message"]["content"]
        if isinstance(content, str):
            return content
        return "".join(part.get("text", "") for part in content if part.get("type") == "text")
    raise SystemExit(f"no owner message at {timestamp}")


def check(reply):
    api, ls, lfs = reply["api_full_address"], reply["git_ls_remote"], reply["git_lfs"]
    refs = [tuple(row.split("\t")) for row in ls["output"].splitlines() if row]
    results = {
        "api_full_address": api["exit_code"] == 0 and json.loads(api["output"]) == EXPECTED_RELEASE,
        "git_ls_remote": ls["exit_code"] == 0 and refs == EXPECTED_REFS,
        "git_lfs": lfs["exit_code"] == 0 and lfs["output"].startswith("git-lfs/"),
        "errors_empty": reply["errors"] == [],
    }
    return results, refs, lfs["output"].strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", required=True, type=pathlib.Path)
    parser.add_argument("--timestamp", required=True)
    args = parser.parse_args()
    target = ROOT / "inbox" / "SOURCE-REPLY-04.json"
    if target.exists():
        print("REFUSED: inbox/SOURCE-REPLY-04.json already exists")
        return 2
    text = owner_text(args.transcript, args.timestamp)
    data = text.encode("utf-8")
    target.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (ROOT / "inbox" / "RECEIVED-04.json").write_text(json.dumps({
        "transcript_timestamp_utc": args.timestamp, "relayed_by": "owner",
        "files": {"SOURCE-REPLY-04.json": {"bytes": len(data), "sha256": digest}},
        "note": "Local only: inbox/ is hard-excluded from publication."}, indent=2) + "\n", encoding="utf-8")
    results, refs, lfs_version = check(json.loads(text))
    verdict = "PASS" if all(results.values()) else "FAIL"
    report = {
        "id": "SOURCE-REPLY-04-CHECK", "reply": {"bytes": len(data), "sha256": digest},
        "expected_from": "observations/UPLOAD-HOST-CALIBRATION-01.json", "results": results,
        "refs": [{"sha": sha, "ref": ref} for sha, ref in refs], "source_git_lfs": lfs_version,
        "verdict": verdict,
        "reading": "Same gh client and login work on api.github.com with a full address, so the upload 401 is specific "
                   "to uploads.github.com from this task: route B1-R is closed for this task. Git over https reaches "
                   "the private repository and Git LFS is installed, so a Git LFS probe is the next candidate route.",
    }
    (ROOT / "observations" / "SOURCE-REPLY-04-CHECK.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
