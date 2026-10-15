#!/usr/bin/env bash
# Clean-install demonstration: unpack a runtime archive, install only from a folder of locked wheels, run the
# candidate guide's quickstart without a terminal, and print what each step did.
#
# Usage: demo-clean-install.sh ARCHIVE WHEEL_FOLDER WORK_FOLDER [EXPECTED_ARCHIVE_SHA256]
#
# It refuses to run inside a git checkout (the current folder or WORK_FOLDER), refuses an archive whose digest or
# file list does not match its own SHA256SUMS (or EXPECTED_ARCHIVE_SHA256, when given), and installs with
# --no-index, so it needs no network and reads nothing from the development workspace. The interpreter is
# `python3` unless PYTHON names another CPython 3.12 that has the venv module.
#
# Exit status: 0 every step passed; 1 a step failed; 2 refused to run here; 3 the archive failed verification;
# 64 wrong usage.

set -u

PYTHON=${PYTHON:-python3}

say() { printf '%s\n' "$*"; }
refuse() { code=$1; shift; say "REFUSED: $*" >&2; exit "$code"; }

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
    say "Usage: $0 ARCHIVE WHEEL_FOLDER WORK_FOLDER [EXPECTED_ARCHIVE_SHA256]" >&2
    exit 64
fi
ARCHIVE=$1
WHEELS=$2
WORK=$3
EXPECTED=${4:-}

# A folder is inside a checkout when it, or any folder above it, holds a .git entry (a directory, or a file for a worktree).
inside_checkout() {
    local dir
    dir=$(cd "$1" 2>/dev/null && pwd -P) || return 1
    while :; do
        [ -e "$dir/.git" ] && return 0
        [ "$dir" = "/" ] && return 1
        dir=$(dirname "$dir")
    done
}

nearest_existing() {
    local dir=$1
    while [ ! -d "$dir" ]; do dir=$(dirname "$dir"); done
    printf '%s\n' "$dir"
}

if inside_checkout "$PWD"; then
    refuse 2 "the current folder is inside a git checkout; run this from a folder outside every checkout."
fi
if inside_checkout "$(nearest_existing "$WORK")"; then
    refuse 2 "WORK_FOLDER is inside a git checkout; choose a folder outside every checkout."
fi
[ -f "$ARCHIVE" ] || refuse 64 "ARCHIVE is not a file: $ARCHIVE"
[ -d "$WHEELS" ] || refuse 64 "WHEEL_FOLDER is not a folder: $WHEELS"
if [ -e "$WORK" ] && [ -n "$(ls -A "$WORK" 2>/dev/null)" ]; then
    refuse 64 "WORK_FOLDER exists and is not empty; use a new folder."
fi

archive_sha256=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
say "archive sha256: $archive_sha256"
if [ -n "$EXPECTED" ] && [ "$archive_sha256" != "$EXPECTED" ]; then
    refuse 3 "the archive digest does not match EXPECTED_ARCHIVE_SHA256 ($EXPECTED)."
fi

mkdir -p -m 700 "$WORK" || refuse 64 "cannot create WORK_FOLDER."
WORK=$(cd "$WORK" && pwd -P)
mkdir -m 700 "$WORK/extract" "$WORK/logs" "$WORK/home"
ARCHIVE=$(cd "$(dirname "$ARCHIVE")" && pwd -P)/$(basename "$ARCHIVE")
WHEELS=$(cd "$WHEELS" && pwd -P)

# Nothing may come from the invoking user's environment or home.
export HOME="$WORK/home" PYTHONDONTWRITEBYTECODE=1 PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1
unset PYTHONPATH PYTHONHOME VIRTUAL_ENV

"$PYTHON" -m zipfile -e "$ARCHIVE" "$WORK/extract" >"$WORK/logs/00-extract.txt" 2>&1 \
    || refuse 3 "the archive cannot be unpacked (see $WORK/logs/00-extract.txt)."
roots=$(ls -A "$WORK/extract")
[ "$(printf '%s\n' "$roots" | wc -l)" -eq 1 ] || refuse 3 "the archive does not have exactly one top folder."
PRODUCT="$WORK/extract/$roots"

(cd "$PRODUCT" && [ -f SHA256SUMS ] && sha256sum --check --quiet SHA256SUMS) >"$WORK/logs/00-sha256sums.txt" 2>&1 \
    || refuse 3 "a file does not match the archive's SHA256SUMS (see $WORK/logs/00-sha256sums.txt)."
listed=$(cd "$PRODUCT" && awk '{print $2}' SHA256SUMS | sort)
present=$(cd "$PRODUCT" && find . -type f ! -name SHA256SUMS | sed 's|^\./||' | sort)
[ "$listed" = "$present" ] || refuse 3 "the archive holds files that SHA256SUMS does not list, or lacks listed ones."
say "SHA256SUMS verified: every file matches and none is unlisted."

[ -f "$PRODUCT/scripts/intune-iac.py" ] && [ -f "$PRODUCT/requirements-runtime-linux-x86_64-cp312.lock" ] \
    || refuse 3 "this is not a runtime archive of the product."

cd "$PRODUCT" || exit 1
RESULTS=()
FAILED=0
N=0

# record NAME STATUS DETAIL
record() { RESULTS+=("$(printf '%-18s %-5s %s' "$1" "$2" "$3")"); [ "$2" = PASS ] || FAILED=1; }

# step NAME COMMAND [EXPECTED_TEXT...]: run COMMAND (shell text) and pass it when it exits 0 and its output holds each text.
step() {
    local name=$1 command=$2 log rc text
    shift 2
    N=$((N + 1))
    log="$WORK/logs/$(printf '%02d' "$N")-$name.txt"
    eval "$command" >"$log" 2>&1
    rc=$?
    if [ "$rc" -ne 0 ]; then record "$name" FAIL "exit $rc, see $log"; return 1; fi
    for text in "$@"; do
        if ! grep -q -F -- "$text" "$log"; then record "$name" FAIL "output lacks: $text (see $log)"; return 1; fi
    done
    record "$name" PASS "exit 0"
}

summary() {
    say ""
    say "Summary"
    printf '%s\n' "${RESULTS[@]}"
    if [ "$FAILED" -eq 0 ]; then say "RESULT: every step passed."; exit 0; fi
    say "RESULT: at least one step failed." >&2
    exit 1
}

"$PYTHON" -c 'import venv, ensurepip' >/dev/null 2>&1 && ok=1 || ok=0
if [ "$ok" -eq 0 ]; then
    record environment FAIL "$PYTHON lacks the venv or ensurepip module (on Debian or Ubuntu install python3.12-venv)"
    summary
fi

step venv "\"$PYTHON\" -m venv .venv" || summary
step wheelhouse "\"$PYTHON\" scripts/verify-dependencies.py --wheelhouse \"$WHEELS\"" '"status": "verified"' || summary
step install ".venv/bin/python -m pip --isolated install --no-index --no-cache-dir --find-links \"$WHEELS\" --require-hashes --only-binary :all: -r requirements-runtime-linux-x86_64-cp312.lock" || summary
step pip-check ".venv/bin/python -m pip --isolated check" || summary

# The guide's quickstart, command for command. The guide defines this function in the reader's shell.
intune-iac() { .venv/bin/python -B scripts/intune-iac.py "$@"; }

step demo-folder "mkdir -m 700 demo"
step version "intune-iac --version"
step doctor "intune-iac doctor" '"status": "ready"' '"status": "identified"'
step start "intune-iac start examples" 'Export' 'Context'
step wizard "printf '%s\n' continue continue continue 22222222-2222-4222-8222-222222222222 continue continue continue continue generate continue continue plan approve execute reconcile continue finish | intune-iac wizard --journey --journey-mode simulation --session demo/journey.json --input examples/supported/input/export.json --context examples/context.json --output demo/journey-output" '"status": "complete_simulation"' '"execution_authorized": false'
step synthetic-estate "intune-iac synthetic generate --output demo/estate --policies 3" '"synthetic": true'
step lab-create "intune-iac workbench lab-create --service-root demo/service --input demo/estate/capture-estate.json --object 45838776-e1bd-566b-a8c5-ad684107e7da" '"status": "created"'
step store-init "intune-iac workbench init --root demo/store --tenant ca8a8057-a15f-5caa-8979-0090cd1bc11b" '"evidence_class": "synthetic"'
step collect "intune-iac workbench collect --root demo/store --service-root demo/service" '"coverage": "complete"'
step workspace "printf 'select 45838776-e1bd-566b-a8c5-ad684107e7da\nrelationships\nquit\n' | intune-iac workbench workspace --root demo/store --service-root demo/service" '"relation": "setting"' '"status": "closed"'
step families "intune-iac workbench families" '"available": true'

# What the build says it is, so the run names the exact files it exercised.
build_line() {
    .venv/bin/python -c 'import json, sys; b = json.load(sys.stdin)["build"]; print("build:", b["status"], b["product_version"], "commit", b["commit"], "content", b["content_sha256"])'
}
step build-identity "intune-iac doctor | build_line" 'build: identified'
tail -n 1 "$WORK/logs/$(printf '%02d' "$N")-build-identity.txt"

summary
