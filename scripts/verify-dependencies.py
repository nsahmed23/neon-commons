#!/usr/bin/env python3
"""Read-only check of a wheelhouse against this release's reviewed dependency lock."""
from __future__ import annotations

import argparse
import email.parser
import hashlib
import io
import json
import os
import re
import stat
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from intune_iac.io import AppError, load_json, read_bytes


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _locked_packages(manifest):
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0.0"
            or manifest.get("platform") != "linux-x86_64-cpython-3.12"
            or not isinstance(manifest.get("packages"), list)
            or not 1 <= len(manifest["packages"]) <= 128):
        raise AppError("invalid_dependency_lock", "The dependency lock is invalid.")
    expected, names = {}, set()
    for row in manifest["packages"]:
        _validate_package(row)
        name = normalize(row["name"])
        if row["filename"] in expected or name in names:
            raise AppError("invalid_dependency_lock", "Locked dependencies must be unique.")
        names.add(name)
        expected[row["filename"]] = row
    return expected


def _matches(value, expression):
    return isinstance(value, str) and re.fullmatch(expression, value) is not None


def _validate_package(row):
    if not isinstance(row, dict):
        raise AppError("invalid_dependency_lock", "A locked dependency is malformed.")
    formats = {"filename": r"[A-Za-z0-9_.+-]+\.whl", "name": r"[A-Za-z0-9][A-Za-z0-9_.-]*",
               "sha256": r"[0-9a-f]{64}"}
    strings_valid = all(_matches(row.get(key), pattern) for key, pattern in formats.items())
    version_valid = isinstance(row.get("version"), str) and bool(row["version"])
    size_valid = type(row.get("size")) is int and 0 < row["size"] <= 16 * 1024 * 1024
    if not strings_valid or not version_valid or not size_valid:
        raise AppError("invalid_dependency_lock", "A locked dependency is malformed.")


def _wheelhouse_inventory(wheelhouse):
    root = Path(wheelhouse).absolute()
    if not root.is_dir() or any(p.is_symlink() for p in [root, *root.parents]):
        raise AppError("invalid_wheelhouse", "Use a regular local wheelhouse directory.")
    actual = set()
    with os.scandir(root) as entries:
        for entry in entries:
            if len(actual) >= 128 or not entry.is_file(follow_symlinks=False):
                raise AppError("invalid_wheelhouse", "Wheelhouse entries must be bounded regular files.")
            actual.add(entry.name)
    return root, actual


def _safe_member(info):
    name = info.filename
    return (not name.startswith("/") and "\\" not in name and ":" not in name
            and not any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))
            and not stat.S_ISLNK(info.external_attr >> 16))


def _verify_metadata(data, row):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 8192 or len({i.filename for i in infos}) != len(infos):
                raise ValueError()
            if not all(_safe_member(info) for info in infos):
                raise ValueError()
            metadata = [i for i in infos if i.filename.endswith(".dist-info/METADATA")]
            if len(metadata) != 1 or metadata[0].file_size > 1024 * 1024:
                raise ValueError()
            message = email.parser.BytesParser().parsebytes(archive.read(metadata[0]))
            if len(message.get_all("Name", [])) != 1 or len(message.get_all("Version", [])) != 1:
                raise ValueError()
            if normalize(message["Name"]) != normalize(row["name"]) or message["Version"] != row["version"]:
                raise ValueError()
    except (ValueError, KeyError, OSError, RuntimeError, zipfile.BadZipFile):
        raise AppError("wheel_metadata_mismatch", "Wheel metadata or paths do not match the supported contract.") from None


def verify_wheelhouse(wheelhouse, manifest):
    """Verify exact files, bytes and metadata; never install or execute a wheel."""
    expected = _locked_packages(manifest)
    root, actual = _wheelhouse_inventory(wheelhouse)
    if actual != set(expected):
        raise AppError("wheelhouse_inventory_mismatch", "The wheelhouse must contain exactly the locked wheels.")
    for filename, row in expected.items():
        data = read_bytes(root / filename)
        if len(data) != row["size"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise AppError("wheel_digest_mismatch", "A wheel differs from its reviewed digest.")
        _verify_metadata(data, row)
    return {"status": "verified", "packages": len(expected),
            "platform": manifest["platform"], "installation_performed": False,
            "publisher_authenticated": False, "vulnerabilities_assessed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", required=True)
    args = parser.parse_args()
    try:
        result = verify_wheelhouse(args.wheelhouse, load_json(ROOT / "dependency-lock.json"))
    except AppError as error:
        result = {"status": "rejected", "error": error.code}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "verified" else 3


if __name__ == "__main__":
    raise SystemExit(main())
