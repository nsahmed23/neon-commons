#!/usr/bin/env python3
"""Replay reviewed upstream local-locking tests with pinned OpenTofu, offline."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

UPSTREAM = "https://github.com/stephrobert/terraform-dsoxlab-training"
COMMIT = "86b69d2292485d179698f5b9bf648a29f935e216"
TOFU_SHA256 = "0a9eda0f0898896969492504a6ce778f310675e8a1eb960434c26806cd252627"
LAB = "labs/state/state-locking"
SOURCES = {
    "conftest.py": "428119f02bc6f83f7bcfef4b8a0ac6b3c1d235718de3bf2c29cbb5138c411f6e",
    f"{LAB}/challenge/tests/test_functional.py": "54288419ae96edf8c455ac5706077701bace6cc15f8f72ae94e844be5627adea",
    f"{LAB}/fixtures/main.tf": "09bfc7e66dce6f3082d5fcd1b84dc954b66ddb1355d1c2d3a428dce531979451",
    f"{LAB}/fixtures/observations.tf": "b09a65d37b1745d6fa176c04c536d53e5faf5c422c15b3df8ffeef65eb418078",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bounded_bytes(path, limit):
    if path.stat().st_size > limit:
        raise ValueError(f"Input exceeds {limit} byte limit: {path.name}")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Input exceeds {limit} byte limit: {path.name}")
    return data


def reviewed_sources(root):
    result = {}
    for relative, expected in SOURCES.items():
        path = root / relative
        if any(p.is_symlink() for p in [path, *path.parents]) or not path.is_file():
            raise ValueError(f"reviewed source must be a regular file: {relative}")
        data = bounded_bytes(path, 1024 * 1024)
        if digest(data) != expected:
            raise ValueError(f"reviewed source mismatch: {relative}")
        result[relative] = data
    return result


def new_output(path):
    if path.absolute() != path.resolve():
        raise ValueError("Output must use a canonical path without symlink traversal")
    path.mkdir(parents=True, exist_ok=False)
    path.chmod(0o700)
    return path


def clean_environment(root):
    return {
        "PATH": f"{root / 'bin'}:/usr/bin:/bin",
        "HOME": str(root / "home"), "TMPDIR": str(root / "tmp"),
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "TF_CLI_CONFIG_FILE": str(root / "terraform.rc"),
        "TF_IN_AUTOMATION": "1", "TF_INPUT": "0", "CHECKPOINT_DISABLE": "1",
        "LAB_NO_REPLAY": "1", "LAB_WORKDIR": str(root / "work"),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONNOUSERSITE": "1",
    }


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def execute(command, cwd, env, timeout=65):
    start = time.monotonic()
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException as exc:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        if isinstance(exc, subprocess.TimeoutExpired):
            raise RuntimeError(f"command deadline exceeded: {command[0]}") from exc
        raise
    return {"arguments": command[1:], "exit_code": process.returncode,
            "duration_seconds": round(time.monotonic() - start, 3),
            "stdout": stdout, "stderr": stderr}


def install_wrapper(root, tofu):
    # Foreground mode preserves the process group created by the upstream test,
    # whose killpg therefore kills only that owned apply and its sleep child.
    # Every CLI call is bounded; the only authored provisioner sleeps 20s.
    wrapper = root / "bin/terraform"
    wrapper.write_text("#!/bin/sh\nexec /usr/bin/timeout --foreground --signal=TERM --kill-after=5s 60s "
                       f"{shlex.quote(str(tofu))} \"$@\"\n")
    wrapper.chmod(0o700)


def wait_lock(work, process):
    path = work / "etat/.projet.tfstate.lock.info"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if data.get("ID"):
                    return path, data
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        if process.poll() is not None:
            break
        time.sleep(0.05)
    raise RuntimeError("No live lock observed")


@contextmanager
def background_apply(root, env, log_name):
    with (root / log_name).open("w") as log:
        process = subprocess.Popen(
            ["terraform", "apply", "-replace=terraform_data.lent", "-auto-approve", "-input=false", "-no-color"],
            cwd=root / "work", env=env, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
        try:
            yield process
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)


def measure(root, env):
    work = root / "work"
    records = []

    def run(*arguments):
        record = {"arguments": list(arguments), "status": "running"}
        records.append(record)
        write_json(root / "measurement-commands.json", records)
        try:
            result = execute(["terraform", *arguments], work, env)
        except BaseException as exc:
            record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            write_json(root / "measurement-commands.json", records)
            raise
        record.update(result, status="completed")
        write_json(root / "measurement-commands.json", records)
        return result

    def require(*arguments):
        result = run(*arguments)
        if result["exit_code"] != 0:
            raise RuntimeError(f"native command failed: {arguments[0]}: {result['stderr'][-1200:]}")
        return result

    require("init", "-input=false", "-no-color")
    require("apply", "-auto-approve", "-input=false", "-no-color")
    with background_apply(root, env, "measurement-apply.log") as process:
        lock, content = wait_lock(work, process)
        codes = {}
        commands = {
            "plan": ["plan", "-input=false", "-no-color", "-lock-timeout=0s"],
            "apply": ["apply", "-auto-approve", "-input=false", "-no-color"],
            "force_unlock": ["force-unlock", "-force", content["ID"]],
            "state_list": ["state", "list"], "show_json": ["show", "-json"],
            "plan_lock_false": ["plan", "-input=false", "-no-color", "-lock=false"],
        }
        for name, command in commands.items():
            codes[name] = run(*command)["exit_code"]
        timeout_result = run("plan", "-input=false", "-no-color", "-lock-timeout=1s")
        if not lock.exists() or process.poll() is not None:
            raise RuntimeError("Lock released before concurrency measurements completed")
        if process.wait(timeout=45) != 0:
            raise RuntimeError("Replacement apply failed")
    with background_apply(root, env, "crashed-apply.log") as process:
        lock, _ = wait_lock(work, process)
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    present = lock.exists()
    retry = require("plan", "-input=false", "-no-color")
    observations = {
        "fichier_verrou": lock.relative_to(work).as_posix(), "codes_pendant_verrou": codes,
        "verrou_residuel": {"plan_rc": retry["exit_code"], "fichier_subsiste": lock.exists()},
    }
    expected = {"plan": 1, "apply": 1, "force_unlock": 1,
                "state_list": 0, "show_json": 0, "plan_lock_false": 0}
    passed = (codes == expected and present and not lock.exists()
              and timeout_result["exit_code"] == 1 and timeout_result["duration_seconds"] >= 0.9)
    write_json(root / "measurements.json", {"observations": observations, "lock": content,
        "residual_present_before_plan": present, "lock_timeout": timeout_result,
        "passed": passed, "commands": records})
    if not passed:
        raise RuntimeError("Native locking observations violated the local scenario")
    (work / "observations.tf").write_text("\n".join(
        f'output "{key}" {{\n  value = jsondecode({json.dumps(json.dumps(value))})\n}}\n'
        for key, value in observations.items()))
    return observations


def run_lab(args):
    if sys.platform != "linux" or not Path("/usr/bin/timeout").is_file():
        raise ValueError("This qualification runner requires Linux and GNU timeout")
    upstream = Path(args.upstream).absolute()
    sources = reviewed_sources(upstream)
    tofu = Path(args.tofu).resolve(strict=True)
    if not stat.S_ISREG(tofu.stat().st_mode):
        raise ValueError("Expected a regular OpenTofu executable")
    tofu_bytes = bounded_bytes(tofu, 128 * 1024 * 1024)
    if digest(tofu_bytes) != TOFU_SHA256:
        raise ValueError("Expected reviewed OpenTofu 1.10.0 Linux amd64 binary")
    output = Path(args.output).absolute()
    for protected in (Path(__file__).resolve().parents[1], upstream.resolve()):
        if output.resolve().is_relative_to(protected) or protected.is_relative_to(output.resolve()):
            raise ValueError("Output must be outside the plugin and upstream source trees")
    root = new_output(output)
    for folder in ("bin", "home", "tmp", "work", "upstream"):
        (root / folder).mkdir()
    tofu = root / "bin/tofu-pinned"
    tofu.write_bytes(tofu_bytes)
    tofu.chmod(0o700)
    if digest(tofu.read_bytes()) != TOFU_SHA256:
        raise ValueError("Copied OpenTofu executable failed hash verification")
    (root / "terraform.rc").write_text('disable_checkpoint = true\nprovider_installation {\n  filesystem_mirror { path = "./no-providers" }\n}\n')
    for relative, data in sources.items():
        dest = root / "upstream" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    # Only this declared engine constraint and the learner's ??? holes change.
    main = sources[f"{LAB}/fixtures/main.tf"].decode().replace('">= 1.15.0"', '"= 1.10.0"')
    main = main.replace("path = ???", 'path = "etat/projet.tfstate"').replace("command = ???", 'command = "sleep 20"')
    (root / "work/main.tf").write_text(main)
    install_wrapper(root, tofu)
    env = clean_environment(root)
    receipt = {"source": UPSTREAM, "commit": COMMIT, "reviewed_hashes": SOURCES,
        "engine": "OpenTofu 1.10.0", "engine_sha256": TOFU_SHA256,
        "upstream_engine_requirement": "Terraform >=1.15.0",
        "adaptations": ["Local learner solution authored: backend path and sleep 20", "Version constraint changed to =1.10.0 for this OpenTofu replay", "observations.tf generated from a separate native measurement pass"],
        "unchanged_upstream_tests": True, "encrypted_solutions_used": False,
        "selected_scope": "8 upstream local-backend behavior tests; one S3 documentation test deselected",
        "boundaries": ["Not a dsoxlab CLI execution or Terraform 1.15 replay", "No S3, Azure, Intune, provider, host, or Atmos qualification", "Clean credential-free child environment; not an OS/network security sandbox", "Canceled upstream pytest may leave its separate child sessions running until their 60-second timeout; immediate universal descendant cleanup is not qualified"],
        "success": False}
    try:
        receipt["version"] = execute([str(tofu), "version", "-json"], root, env)
        receipt["pytest_version"] = execute(
            [str(Path(args.pytest_python).absolute()), "-m", "pytest", "--version"], root, env)
        if (receipt["pytest_version"]["exit_code"] != 0
                or receipt["pytest_version"]["stdout"].strip() != "pytest 8.4.2"):
            raise ValueError("Qualification requires pytest 8.4.2")
        receipt["observations"] = measure(root, env)
        tests = root / "upstream" / LAB / "challenge/tests/test_functional.py"
        result = execute([str(Path(args.pytest_python).absolute()), "-m", "pytest", str(tests),
                          "-q", "-k", "not test_backend_s3", "--junitxml", str(root / "upstream-junit.xml")],
                         root / "upstream", env, timeout=150)
        write_json(root / "upstream-pytest.json", result)
        xml = ET.parse(root / "upstream-junit.xml").getroot()
        suite = next(xml.iter("testsuite"))
        receipt["upstream_result"] = {k: int(suite.attrib[k]) for k in ("tests", "failures", "errors", "skipped")}
        receipt["upstream_result"]["deselected"] = 1
        receipt["success"] = (result["exit_code"] == 0 and receipt["upstream_result"] ==
            {"tests": 8, "failures": 0, "errors": 0, "skipped": 0, "deselected": 1})
    except (Exception, KeyboardInterrupt) as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        write_json(root / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2))
    if receipt.get("error", "").startswith("KeyboardInterrupt:"):
        return 130
    return 0 if receipt["success"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--tofu", required=True)
    parser.add_argument("--output", required=True, help="New disposable directory; existing paths are refused")
    parser.add_argument("--pytest-python", required=True, help="Python environment with pytest 8.4.2")
    args = parser.parse_args()
    try:
        return run_lab(args)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
