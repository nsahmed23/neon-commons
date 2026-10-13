"""Which User-Agent do git and git-lfs send, and can config change it? Loopback only.

Usage: py -3.11 -I tools/lfs_ua_loopback_test.py --work-dir <new empty dir>
Starts an HTTP listener on 127.0.0.1 (ephemeral port) that records each request's User-Agent values and answers 404.
Runs git ls-remote and git lfs locks against it with no setting, with http.userAgent, and with http.extraHeader.
Nothing leaves this machine. Prints one JSON report.
"""
import argparse
import http.server
import json
import os
import pathlib
import subprocess
import sys
import threading

UA = "OpenAI File Downloader, XaiImageApiFetch/1.0"
SEEN = []


class Recorder(http.server.BaseHTTPRequestHandler):
    def _answer(self):
        SEEN.append({"method": self.command, "path": self.path.split("?")[0],
                     "user_agents": self.headers.get_all("User-Agent") or []})
        body = b'{"message":"not found"}'
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _answer

    def log_message(self, *args):
        pass


def run(cmd, cwd):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", NO_PROXY="127.0.0.1", no_proxy="127.0.0.1",
               GCM_INTERACTIVE="never")
    before = len(SEEN)
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=60)
    return {"cmd": " ".join(cmd[1:]), "exit": result.returncode, "requests": SEEN[before:]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=pathlib.Path)
    args = parser.parse_args()
    if args.work_dir.exists():
        print(json.dumps({"verdict": "REFUSED", "reason": "work dir exists"}))
        return 2
    args.work_dir.mkdir(parents=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    subprocess.run(["git", "init", "-q"], cwd=args.work_dir, check=True)
    lfs = ["-c", f"lfs.url={base}/repo.git/info/lfs"]
    variants = {
        "none": [],
        "http.userAgent": ["-c", f"http.userAgent={UA}"],
        "http.extraHeader": ["-c", f"http.extraHeader=User-Agent: {UA}"],
    }
    report = {"listener": "127.0.0.1 only", "git_version": subprocess.run(["git", "--version"], capture_output=True,
              text=True).stdout.strip(), "git_lfs_version": subprocess.run(["git", "lfs", "version"],
              capture_output=True, text=True).stdout.strip(), "runs": []}
    for name, extra in variants.items():
        report["runs"].append(dict(run(["git", *extra, "ls-remote", f"{base}/repo.git"], args.work_dir), variant=name))
        report["runs"].append(dict(run(["git", *extra, *lfs, "lfs", "locks", "--json"], args.work_dir), variant=name))
    server.shutdown()
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
