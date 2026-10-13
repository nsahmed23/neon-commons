"""Receiver side of route B1-R: wait for the probe asset on the draft release, download it, verify it.

Usage: py -3.11 -I tools/fetch_probe.py --out-dir <new empty dir> [--minutes 30] [--interval 30]
Read-only on GitHub: lists releases and downloads one asset through the local GitHub CLI with the required
User-Agent header (gh attaches its own existing login; no token is read or printed). The download goes into a
new empty directory and is only hashed and listed, never extracted or opened by another program.
Prints one JSON line per poll problem and a final JSON verdict; exit 0 only on PASS.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
import zipfile

GH = r"C:\Program Files\GitHub CLI\gh.exe"
UA = "User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0"
REPO = "nsahmed23/intune-evidence-custody"
TAG = "probe-20261013-01"
NAME = "synthetic-original-work-probe.zip"
PIN_BYTES = 18445
PIN_SHA256 = "d01a9b0e9cd1506b1ee5d0defcfebf4f377af858ab610d3ec5362623ee0c67c3"


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gh(*args):
    env = dict(os.environ, GH_NO_UPDATE_NOTIFIER="1", GH_PROMPT_DISABLED="1")
    return subprocess.run([GH, "api", "-H", UA, *args], capture_output=True, env=env)


def find_asset():
    result = gh("-H", "Accept: application/vnd.github+json", f"repos/{REPO}/releases",
                "--jq", f'[.[] | select(.tag_name == "{TAG}") | {{id, draft, assets: [.assets[] | {{id, name, size, state}}]}}]')
    if result.returncode:
        return None, result.stderr.decode("utf-8", "replace").strip()[:300]
    releases = json.loads(result.stdout or b"[]")
    if len(releases) != 1:
        return None, f"expected one release tagged {TAG}, found {len(releases)}"
    assets = [a for a in releases[0]["assets"] if a["name"] == NAME and a["state"] == "uploaded"]
    return (dict(assets[0], release_id=releases[0]["id"], draft=releases[0]["draft"]) if assets else None), None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=pathlib.Path)
    parser.add_argument("--minutes", type=float, default=30)
    parser.add_argument("--interval", type=float, default=30)
    args = parser.parse_args()
    if args.out_dir.exists():
        print(json.dumps({"utc": utc(), "verdict": "REFUSED", "reason": "output directory already exists"}))
        return 2
    deadline = time.monotonic() + args.minutes * 60
    polls = 0
    while True:
        polls += 1
        asset, problem = find_asset()
        if problem:
            print(json.dumps({"utc": utc(), "poll": polls, "problem": problem}), flush=True)
        if asset:
            break
        if time.monotonic() >= deadline:
            print(json.dumps({"utc": utc(), "verdict": "NOT_UPLOADED", "polls": polls}))
            return 1
        time.sleep(args.interval)
    args.out_dir.mkdir(parents=True)
    target = args.out_dir / NAME
    download = gh("-H", "Accept: application/octet-stream", f"repos/{REPO}/releases/assets/{asset['id']}")
    if download.returncode:
        print(json.dumps({"utc": utc(), "verdict": "DOWNLOAD_FAILED", "asset": asset,
                          "error": download.stderr.decode("utf-8", "replace").strip()[:300]}))
        return 1
    target.write_bytes(download.stdout)
    data = target.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    members = None
    if data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(target) as archive:
            members = [{"name": i.filename, "bytes": i.file_size} for i in archive.infolist()]
    verdict = "PASS" if len(data) == PIN_BYTES and digest == PIN_SHA256 and asset["size"] == PIN_BYTES else "FAIL"
    print(json.dumps({"utc": utc(), "verdict": verdict, "polls": polls, "asset": asset, "downloaded_bytes": len(data),
                      "sha256": digest, "expected_bytes": PIN_BYTES, "expected_sha256": PIN_SHA256,
                      "zip_magic": data[:4] == b"PK\x03\x04", "zip_members": members, "path": str(target)}))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
