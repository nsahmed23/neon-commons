"""Receiver side of route B1-L: wait for the probe branch, download its Git LFS object, verify it.

Usage: py -3.11 -I tools/fetch_lfs_probe.py --out-dir <new empty dir> [--minutes 30] [--interval 30]
Read-only on GitHub, and every request sends the required User-Agent:
- the branch, its file list and the pointer file are read through the local GitHub CLI (gh attaches its own
  login; no token is read or printed);
- one Git LFS batch query (operation "download") goes through the same CLI;
- the link GitHub returns is downloaded once with urllib, only from an allowlisted https host, redirects refused.
  The link and the headers GitHub sends with it are used for that one request and never printed or saved.
The download goes into a new empty directory and is hashed; Python's zipfile lists its zip directory. Nothing is
extracted or opened by another program. Prints one JSON line per poll problem and a final JSON verdict; exit 0
only on PASS.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

GH = r"C:\Program Files\GitHub CLI\gh.exe"
UA = "OpenAI File Downloader, XaiImageApiFetch/1.0"
REPO = "nsahmed23/intune-evidence-custody"
BRANCH = "probe-lfs-20261013-01"
NAME = "synthetic-original-work-probe.zip"
PIN_BYTES = 18445
PIN_SHA256 = "d01a9b0e9cd1506b1ee5d0defcfebf4f377af858ab610d3ec5362623ee0c67c3"
BATCH_URL = f"https://github.com/{REPO}.git/info/lfs/objects/batch"
LFS_JSON = "application/vnd.git-lfs+json"
# Git LFS pointer spec v1 with no extension lines: anything else is not the pointer this probe expects.
POINTER_RE = re.compile(rb"version https://git-lfs\.github\.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize (\d+)\n")
MAX_POINTER = 1024
# Hosts GitHub's LFS service hands out for downloads; the batch headers go nowhere else.
DOWNLOAD_HOST_SUFFIXES = (".githubusercontent.com", ".amazonaws.com", ".github.com")


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gh(*args, stdin=None):
    env = dict(os.environ, GH_NO_UPDATE_NOTIFIER="1", GH_PROMPT_DISABLED="1")
    return subprocess.run([GH, "api", "-H", f"User-Agent: {UA}", *args], input=stdin, capture_output=True,
                          env=env, timeout=120)


def problem(result):
    return result.stderr.decode("utf-8", "replace").strip()[:300]


def parse_pointer(data):
    if len(data) > MAX_POINTER:
        raise ValueError(f"pointer larger than {MAX_POINTER} bytes")
    match = POINTER_RE.fullmatch(data)
    if not match:
        raise ValueError("not a Git LFS v1 pointer")
    return {"oid": match.group(1).decode(), "size": int(match.group(2))}


def verdict(pointer, data, pin_bytes=PIN_BYTES, pin_sha256=PIN_SHA256):
    matches = (pointer["oid"] == pin_sha256 and pointer["size"] == pin_bytes
               and len(data) == pin_bytes and hashlib.sha256(data).hexdigest() == pin_sha256)
    return "PASS" if matches else "FAIL"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects, so the headers from the batch answer never reach a host GitHub did not name."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def allowed_href(href):
    parts = urllib.parse.urlsplit(href)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host == "github.com" or host.endswith(DOWNLOAD_HOST_SUFFIXES))


def find_branch():
    """Return ({commit, tree}, None) once the branch exists, else (None, problem)."""
    result = gh("-H", "Accept: application/vnd.github+json", f"repos/{REPO}/branches/{BRANCH}",
                "--jq", "{commit: .commit.sha, tree: .commit.commit.tree.sha}")
    if result.returncode:
        return None, problem(result)
    return json.loads(result.stdout), None


def read_tree(tree_sha):
    result = gh("-H", "Accept: application/vnd.github+json", f"repos/{REPO}/git/trees/{tree_sha}",
                "--jq", "[.tree[] | {path, type, size, sha}]")
    if result.returncode:
        raise RuntimeError(f"tree read failed: {problem(result)}")
    return json.loads(result.stdout)


def read_pointer(blob_sha):
    # The git blob API returns the committed bytes (the pointer) and never substitutes the LFS content.
    result = gh("-H", "Accept: application/vnd.github.raw", f"repos/{REPO}/git/blobs/{blob_sha}")
    if result.returncode:
        raise RuntimeError(f"pointer read failed: {problem(result)}")
    return parse_pointer(result.stdout)


def batch_link(pointer):
    body = json.dumps({"operation": "download", "transfers": ["basic"], "objects": [pointer]}).encode()
    result = gh("-X", "POST", "-H", f"Accept: {LFS_JSON}", "-H", f"Content-Type: {LFS_JSON}", BATCH_URL,
                "--input", "-", stdin=body)
    if result.returncode:
        raise RuntimeError(f"LFS batch query failed: {problem(result)}")
    entry = json.loads(result.stdout)["objects"][0]
    if "error" in entry:
        raise RuntimeError(f"LFS batch error {entry['error'].get('code')}: {entry['error'].get('message')}")
    action = entry["actions"]["download"]
    return action["href"], action.get("header", {})


def download(href, header, limit):
    if not allowed_href(href):
        host = urllib.parse.urlsplit(href).hostname
        raise RuntimeError(f"download link refused: host {host} is not on the allowlist or not https")
    request = urllib.request.Request(href, headers={**header, "User-Agent": UA})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=60) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"download failed: HTTP {error.code} {error.reason}") from None
    except urllib.error.URLError as error:
        raise RuntimeError(f"download failed: {type(error.reason).__name__}") from None
    if len(data) > limit:
        raise RuntimeError("download larger than the pointer size")
    return data


def wait_for_branch(minutes, interval):
    deadline = time.monotonic() + minutes * 60
    polls = 0
    while True:
        polls += 1
        found, issue = find_branch()
        if found:
            return found, polls
        print(json.dumps({"utc": utc(), "poll": polls, "problem": issue}), flush=True)
        if time.monotonic() >= deadline:
            return None, polls
        time.sleep(interval)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=pathlib.Path)
    parser.add_argument("--minutes", type=float, default=30)
    parser.add_argument("--interval", type=float, default=30)
    args = parser.parse_args(argv)
    if args.out_dir.exists():
        print(json.dumps({"utc": utc(), "verdict": "REFUSED", "reason": "output directory already exists"}))
        return 2
    found, polls = wait_for_branch(args.minutes, args.interval)
    if not found:
        print(json.dumps({"utc": utc(), "verdict": "NOT_PUSHED", "polls": polls}))
        return 1
    report = {"utc": utc(), "polls": polls, "branch": BRANCH, "commit": found["commit"], "tree_sha": found["tree"]}
    try:
        report["tree"] = read_tree(found["tree"])
        blobs = [entry["sha"] for entry in report["tree"] if entry["path"] == NAME and entry["type"] == "blob"]
        if len(blobs) != 1:
            raise RuntimeError(f"{NAME} is not a single file at the top of the branch")
        pointer = read_pointer(blobs[0])
        report["pointer"] = pointer
        if pointer["oid"] != PIN_SHA256 or pointer["size"] != PIN_BYTES:
            print(json.dumps(dict(report, verdict="FAIL", reason="pointer does not name the pinned file")))
            return 1
        href, header = batch_link(pointer)
        data = download(href, header, pointer["size"])
    except (RuntimeError, ValueError) as error:
        print(json.dumps(dict(report, verdict="DOWNLOAD_FAILED", error=str(error)[:300])))
        return 1
    args.out_dir.mkdir(parents=True)
    target = args.out_dir / NAME
    target.write_bytes(data)
    members = None
    if data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(target) as archive:
            members = [{"name": item.filename, "bytes": item.file_size} for item in archive.infolist()]
    result = verdict(pointer, data)
    print(json.dumps(dict(report, verdict=result, downloaded_bytes=len(data),
                          sha256=hashlib.sha256(data).hexdigest(), expected_bytes=PIN_BYTES,
                          expected_sha256=PIN_SHA256, zip_members=members, path=str(target))))
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
