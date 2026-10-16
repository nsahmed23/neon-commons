#!/usr/bin/env bash
# Clean-install demonstration: unpack a runtime archive, install only from a folder of locked wheels, run the
# candidate guide's quickstart without a terminal, and print what each step did.
#
# Usage: demo-clean-install.sh [--pip-wheel PATH --pip-wheel-sha256 HEX] ARCHIVE WHEEL_FOLDER WORK_FOLDER
#                              EXPECTED_ARCHIVE_SHA256
#
# It refuses to run inside a git checkout (the current folder or WORK_FOLDER), refuses an archive whose digest is not
# EXPECTED_ARCHIVE_SHA256 or whose file list does not match its own SHA256SUMS, and installs with --no-index, so it needs
# no network and reads nothing from the development workspace. The interpreter is `python3` unless PYTHON names
# another CPython 3.12 that has the venv module.
#
# Neither executable input runs on trust. An archive carries its own SHA256SUMS, so a tampered archive can be consistent
# with itself, and a pip wheel runs as code. EXPECTED_ARCHIVE_SHA256 (64 lowercase hex digits) is therefore required, and so
# is --pip-wheel-sha256 whenever --pip-wheel is given; a run without either is refused with exit status 64 before anything is
# created. Take each digest from the published release record, not from this script's own printed line, which only echoes
# the file it was given. A named file that is a link, or is not a plain file, is refused. The archive and the wheel are
# copied once into a new folder that only this run can enter (under TMPDIR, or /tmp), and every check and every use reads
# those copies, hashed again just before first use; the folder is removed when the script ends. No Python or pip setting of the
# caller's (PYTHONPATH, PYTHONSTARTUP, PIP_*, VIRTUAL_ENV and the rest) reaches an interpreter the script starts: they are removed
# before the first one starts, each helper interpreter runs with -I, and its home is a private folder.
#
# Many Debian and Ubuntu hosts ship CPython without ensurepip, so `python3 -m venv` fails there. Either install the
# python3.12-venv package, or give --pip-wheel PATH (any pip wheel file, read in place): the virtual environment is
# then made with --without-pip and every pip command runs from the wheel itself (python PATH/pip ...), still from
# WHEEL_FOLDER only. A wheel whose sha256 is not --pip-wheel-sha256 is refused, with exit status 64 and both digests
# printed, before the script creates anything.
#
# The quickstart's sign-in step runs with no search path, so its answer (a blocked report, exit status 2) is the
# same on every host whether or not an Azure CLI is installed; no other step looks for one.
#
# Exit status: 0 every step passed; 1 a step failed; 2 refused to run here; 3 the archive failed verification;
# 64 wrong usage.

set -u

PYTHON=${PYTHON:-python3}

# Isolation. Nothing of the caller's Python or pip setup reaches an interpreter this script starts: every PYTHON* variable (but
# PYTHON itself, which only names the interpreter), every PIP_* variable and VIRTUAL_ENV are removed here, before the first
# interpreter is started, and every helper interpreter below also runs with -I (isolated: it ignores PYTHON* variables and the
# user site, and puts neither the script's folder nor the current folder on its module path). The few settings that follow are
# the script's own. The home is the staging folder's until the work folder exists (see Staging), and the work folder's after.
for name in $(compgen -e); do
    case $name in
        PYTHON) ;;
        PYTHON*|PIP_*|VIRTUAL_ENV) unset "$name" ;;
    esac
done
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1 PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1

# The one check of an archive's complete member set against its own SHA256SUMS, made on the archive before anything is
# unpacked. It is the command the guide shows under "Check the download", word for word (a test compares the two): it refuses
# a member that is not listed, a listed member that is absent, a member whose content differs, and an archive with more than
# one top folder, a repeated or unsafe name, or a link.
VERIFY_ARCHIVE='
import hashlib, sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
infos = [i for i in z.infolist() if not i.is_dir()]
names = [i.filename for i in infos]
bad = []
if len({n.split("/")[0] for n in names}) != 1 or any("/" not in n for n in names):
    bad.append("the archive must hold exactly one top folder")
if len(set(names)) != len(names):
    bad.append("a member name appears twice")
bad += ["unsafe member name: " + n for n in names if n.startswith("/") or "\\" in n or ".." in n.split("/")]
bad += ["symbolic link member: " + i.filename for i in infos if (i.external_attr >> 16) & 0o170000 == 0o120000]
top = (names[0].split("/")[0] + "/") if names else ""
sums = {}
if top + "SHA256SUMS" in names:
    for line in z.read(top + "SHA256SUMS").decode("utf-8").splitlines():
        digest, _, name = line.partition("  ")
        sums[name] = digest
else:
    bad.append("the archive has no SHA256SUMS")
members = {n[len(top):] for n in names if n.startswith(top)} - {"SHA256SUMS"}
bad += ["not listed in SHA256SUMS: " + n for n in sorted(members - set(sums))]
bad += ["listed in SHA256SUMS but absent from the archive: " + n for n in sorted(set(sums) - members)]
bad += ["differs from its SHA256SUMS line: " + n for n in sorted(members & set(sums))
        if hashlib.sha256(z.read(top + n)).hexdigest() != sums[n]]
if bad:
    sys.exit("REFUSED:\n  " + "\n  ".join(bad[:25]))
print("SHA256SUMS verified: %d files, each listed and matching, none unlisted" % len(members))
'

say() { printf '%s\n' "$*"; }
refuse() { code=$1; shift; say "REFUSED: $*" >&2; exit "$code"; }
usage() { say "Usage: $0 [--pip-wheel PATH --pip-wheel-sha256 HEX] ARCHIVE WHEEL_FOLDER WORK_FOLDER EXPECTED_ARCHIVE_SHA256" >&2; exit 64; }
usage_error() { say "REFUSED: $*" >&2; usage; }

PIP_WHEEL=
PIP_WHEEL_GIVEN=no
PIP_WHEEL_SHA256=
PIP_WHEEL_SHA256_GIVEN=no
POSITIONAL=()
while [ "$#" -gt 0 ]; do
    case $1 in
        --pip-wheel) [ "$#" -ge 2 ] || usage_error "--pip-wheel needs a value."; PIP_WHEEL=$2; PIP_WHEEL_GIVEN=yes; shift 2 ;;
        --pip-wheel=*) PIP_WHEEL=${1#--pip-wheel=}; PIP_WHEEL_GIVEN=yes; shift ;;
        --pip-wheel-sha256) [ "$#" -ge 2 ] || usage_error "--pip-wheel-sha256 needs a value."
            PIP_WHEEL_SHA256=$2; PIP_WHEEL_SHA256_GIVEN=yes; shift 2 ;;
        --pip-wheel-sha256=*) PIP_WHEEL_SHA256=${1#--pip-wheel-sha256=}; PIP_WHEEL_SHA256_GIVEN=yes; shift ;;
        --) shift; POSITIONAL+=("$@"); break ;;
        -*) usage ;;
        *) POSITIONAL+=("$1"); shift ;;
    esac
done
if [ "$PIP_WHEEL_SHA256_GIVEN" = yes ]; then
    [ "$PIP_WHEEL_GIVEN" = yes ] || usage_error "--pip-wheel-sha256 needs --pip-wheel: it is the digest that file must have."
    # Spelled out, with no range, so that no locale can read a-f as including capitals.
    case $PIP_WHEEL_SHA256 in
        ''|*[!0123456789abcdef]*) usage_error "--pip-wheel-sha256 must be 64 lowercase hex digits." ;;
    esac
    [ "${#PIP_WHEEL_SHA256}" -eq 64 ] || usage_error "--pip-wheel-sha256 must be 64 lowercase hex digits."
fi
# A pip wheel runs as code: without its digest the script would run whatever file it was pointed at.
if [ "$PIP_WHEEL_GIVEN" = yes ] && [ "$PIP_WHEEL_SHA256_GIVEN" = no ]; then
    usage_error "--pip-wheel needs --pip-wheel-sha256: the wheel runs as code, so say which file it must be."
fi
if [ "${#POSITIONAL[@]}" -eq 3 ]; then
    usage_error "EXPECTED_ARCHIVE_SHA256 is required: the archive carries its own SHA256SUMS, so only a digest taken from the published release record can tell a tampered archive."
fi
if [ "${#POSITIONAL[@]}" -ne 4 ]; then usage; fi
ARCHIVE=${POSITIONAL[0]}
WHEELS=${POSITIONAL[1]}
WORK=${POSITIONAL[2]}
EXPECTED=${POSITIONAL[3]}
case $EXPECTED in
    ''|*[!0123456789abcdef]*) usage_error "EXPECTED_ARCHIVE_SHA256 must be 64 lowercase hex digits." ;;
esac
[ "${#EXPECTED}" -eq 64 ] || usage_error "EXPECTED_ARCHIVE_SHA256 must be 64 lowercase hex digits."

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
# An input is a plain file. A link is refused, so that the file that is copied below is the file that was named.
plain_file() {
    [ ! -L "$2" ] || refuse 64 "$1 is a symbolic link: $2 (name the file itself, not a link to it)."
    [ -f "$2" ] || refuse 64 "$1 is not a file: $2"
}
plain_file ARCHIVE "$ARCHIVE"
[ -d "$WHEELS" ] || refuse 64 "WHEEL_FOLDER is not a folder: $WHEELS"
if [ -e "$WORK" ] && [ -n "$(ls -A "$WORK" 2>/dev/null)" ]; then
    refuse 64 "WORK_FOLDER exists and is not empty; use a new folder."
fi
if [ "$PIP_WHEEL_GIVEN" = yes ]; then plain_file "the --pip-wheel path" "$PIP_WHEEL"; fi

# Staging. The archive and the wheel are copied once, before any check, into a new folder that only this run can enter, and
# every check and every use after this point reads the copies. Checking a named path and then reading it again would leave a
# window in which the file could be replaced by another one. The folder is removed when the script ends, however it ends.
STAGE=
cleanup() {
    case $STAGE in
        */intune-iac-stage.*) rm -rf -- "$STAGE" ;;
    esac
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
STAGE=$(mktemp -d "${TMPDIR:-/tmp}/intune-iac-stage.XXXXXXXX") || refuse 64 "cannot create a private staging folder under ${TMPDIR:-/tmp}."
STAGE=$(cd "$STAGE" && pwd -P)
if [ ! -O "$STAGE" ] || [ "$(stat -c %a "$STAGE")" != 700 ]; then
    refuse 64 "the staging folder is not private to this run: $STAGE"
fi
# No interpreter reads the caller's home: it is this private folder until the work folder exists.
mkdir -m 700 "$STAGE/home"
export HOME="$STAGE/home"

# stage_copy LABEL SOURCE DESTINATION: copy one input (a link is copied as a link, never followed) and refuse if what arrived is
# not a plain file, which is what a swap for a link between the check above and this copy would leave.
stage_copy() {
    cp -P -- "$2" "$3" 2>/dev/null || refuse 64 "$1 cannot be copied into the staging folder: $2"
    if [ -L "$3" ] || [ ! -f "$3" ]; then refuse 64 "$1 changed into a link or a special file while it was being copied: $2"; fi
    chmod 600 "$3"
}

# recheck LABEL STAGED_PATH DIGEST EXIT_STATUS: hash a staged copy again, immediately before it is used.
recheck() {
    local actual
    actual=$(sha256sum "$2" | cut -d' ' -f1)
    [ "$actual" = "$3" ] || refuse "$4" "the staged $1 changed after it was verified (expected $3, actual $actual)."
}

STAGED_ARCHIVE=$STAGE/archive.zip
stage_copy ARCHIVE "$ARCHIVE" "$STAGED_ARCHIVE"
if [ "$PIP_WHEEL_GIVEN" = yes ]; then
    mkdir -m 700 "$STAGE/wheel"
    STAGED_WHEEL=$STAGE/wheel/$(basename -- "$PIP_WHEEL")
    stage_copy "the --pip-wheel file" "$PIP_WHEEL" "$STAGED_WHEEL"
    PIP_WHEEL_NAMED=$PIP_WHEEL
    PIP_WHEEL=$STAGED_WHEEL
    # The digest of the copy is taken and compared first, so that nothing opens a wheel that is not the one that was named.
    pip_sha256=$(sha256sum "$PIP_WHEEL" | cut -d' ' -f1)
    if [ "$pip_sha256" != "$PIP_WHEEL_SHA256" ]; then
        refuse 64 "the pip wheel's sha256 does not match --pip-wheel-sha256 (expected $PIP_WHEEL_SHA256, actual $pip_sha256); nothing was created."
    fi
    # A pip wheel is a zip that holds the package's __main__.py, which is what `python PATH/pip` runs.
    "$PYTHON" -I -c 'import sys, zipfile; sys.exit(0 if "pip/__main__.py" in zipfile.ZipFile(sys.argv[1]).namelist() else 1)' \
        "$PIP_WHEEL" 2>/dev/null || refuse 64 "the --pip-wheel file is not a pip wheel (no pip/__main__.py inside): $PIP_WHEEL_NAMED"
fi

archive_sha256=$(sha256sum "$STAGED_ARCHIVE" | cut -d' ' -f1)
say "archive sha256: $archive_sha256"
if [ "$PIP_WHEEL_GIVEN" = yes ]; then
    say "pip wheel sha256: $pip_sha256 (matches --pip-wheel-sha256)"
fi
if [ "$archive_sha256" != "$EXPECTED" ]; then
    refuse 3 "the archive digest does not match EXPECTED_ARCHIVE_SHA256 ($EXPECTED)."
fi

# The archive's member set is checked against its SHA256SUMS before anything is unpacked or created.
members=$("$PYTHON" -I -c "$VERIFY_ARCHIVE" "$STAGED_ARCHIVE" 2>&1) \
    || refuse 3 "the archive's files do not match its SHA256SUMS: $members"
say "$members"

mkdir -p -m 700 "$WORK" || refuse 64 "cannot create WORK_FOLDER."
WORK=$(cd "$WORK" && pwd -P)
mkdir -m 700 "$WORK/extract" "$WORK/logs" "$WORK/home"
WHEELS=$(cd "$WHEELS" && pwd -P)

export HOME="$WORK/home"

recheck archive "$STAGED_ARCHIVE" "$EXPECTED" 3
"$PYTHON" -I -m zipfile -e "$STAGED_ARCHIVE" "$WORK/extract" >"$WORK/logs/00-extract.txt" 2>&1 \
    || refuse 3 "the archive cannot be unpacked (see $WORK/logs/00-extract.txt)."
roots=$(ls -A "$WORK/extract")
[ "$(printf '%s\n' "$roots" | wc -l)" -eq 1 ] || refuse 3 "the archive does not have exactly one top folder."
PRODUCT="$WORK/extract/$roots"

(cd "$PRODUCT" && [ -f SHA256SUMS ] && sha256sum --check --quiet SHA256SUMS) >"$WORK/logs/00-sha256sums.txt" 2>&1 \
    || refuse 3 "a file does not match the archive's SHA256SUMS (see $WORK/logs/00-sha256sums.txt)."
listed=$(cd "$PRODUCT" && awk '{print $2}' SHA256SUMS | sort)
present=$(cd "$PRODUCT" && find . -type f ! -name SHA256SUMS | sed 's|^\./||' | sort)
[ "$listed" = "$present" ] || refuse 3 "the unpacked folder holds files that SHA256SUMS does not list, or lacks listed ones."
say "The unpacked files were checked against SHA256SUMS again: every file matches and none is unlisted."

[ -f "$PRODUCT/scripts/intune-iac.py" ] && [ -f "$PRODUCT/requirements-runtime-linux-x86_64-cp312.lock" ] \
    || refuse 3 "this is not a runtime archive of the product."

cd "$PRODUCT" || exit 1
RESULTS=()
FAILED=0
N=0

# record NAME STATUS DETAIL
record() { RESULTS+=("$(printf '%-18s %-5s %s' "$1" "$2" "$3")"); [ "$2" = PASS ] || FAILED=1; }

# step NAME COMMAND [EXPECTED_TEXT...]: run COMMAND (shell text) and pass it when it exits as expected and its output
# holds each text. The expected exit status is 0 unless EXPECT_EXIT names another; when STEP_PATH is set it is the
# search path for that one command, so a step can run on a host with no Azure CLI whatever the host has.
step() {
    local name=$1 command=$2 log rc text want=${EXPECT_EXIT:-0} saved_path=$PATH
    shift 2
    N=$((N + 1))
    log="$WORK/logs/$(printf '%02d' "$N")-$name.txt"
    if [ -n "${STEP_PATH+x}" ]; then PATH=$STEP_PATH; fi
    eval "$command" >"$log" 2>&1
    rc=$?
    PATH=$saved_path
    if [ "$rc" -ne "$want" ]; then record "$name" FAIL "exit $rc, expected $want, see $log"; return 1; fi
    for text in "$@"; do
        if ! grep -q -F -- "$text" "$log"; then record "$name" FAIL "output lacks: $text (see $log)"; return 1; fi
    done
    record "$name" PASS "exit $rc"
}

summary() {
    say ""
    say "Summary"
    printf '%s\n' "${RESULTS[@]}"
    if [ "$FAILED" -eq 0 ]; then say "RESULT: every step passed."; exit 0; fi
    say "RESULT: at least one step failed." >&2
    exit 1
}

if [ "$PIP_WHEEL_GIVEN" = yes ]; then
    record pip-wheel PASS "sha256 $pip_sha256 (matches --pip-wheel-sha256)"
    # The environment is made without pip, so only the venv module is needed, not ensurepip.
    "$PYTHON" -I -c 'import venv' >/dev/null 2>&1 && ok=1 || ok=0
    missing="the venv module"
    venv_command='"$PYTHON" -I -m venv --without-pip .venv'
    pip_command='.venv/bin/python -I "$PIP_WHEEL/pip"'
else
    "$PYTHON" -I -c 'import venv, ensurepip' >/dev/null 2>&1 && ok=1 || ok=0
    missing="the venv or ensurepip module"
    venv_command='"$PYTHON" -I -m venv .venv'
    pip_command='.venv/bin/python -I -m pip'
fi
if [ "$ok" -eq 0 ]; then
    record environment FAIL "$PYTHON lacks $missing (on Debian or Ubuntu install python3.12-venv, or run this script again with --pip-wheel PATH to a pip wheel file)"
    summary
fi

# The commands are single-quoted text that `step` evaluates, so a path is expanded where it is used and is never read as shell syntax.
step venv "$venv_command" || summary
step wheelhouse '"$PYTHON" -I scripts/verify-dependencies.py --wheelhouse "$WHEELS"' '"status": "verified"' || summary
# The staged wheel runs as code, so it is hashed again just before each run of it.
before_pip() { if [ "$PIP_WHEEL_GIVEN" = yes ]; then recheck "pip wheel" "$PIP_WHEEL" "$PIP_WHEEL_SHA256" 64; fi; }
before_pip
step install "$pip_command"' --isolated install --no-index --no-cache-dir --find-links "$WHEELS" --require-hashes --only-binary :all: -r requirements-runtime-linux-x86_64-cp312.lock' || summary
before_pip
step pip-check "$pip_command"' --isolated check' || summary

# The guide's quickstart, command for command. The guide defines this function in the reader's shell.
intune-iac() { .venv/bin/python -B scripts/intune-iac.py "$@"; }

step demo-folder "mkdir -m 700 demo"
step version "intune-iac --version"
step doctor "intune-iac doctor" '"status": "ready"' '"status": "identified"'
step start "intune-iac start examples" 'INTUNE WORKBENCH: START' 'Export' 'Context' 'No live discovery connection is configured'
step start-goal "intune-iac start examples --goal inspect" 'GOAL READINESS: inspect (status: ready)'
# The sample tenant is made up and this step must not depend on the host's Azure CLI, so the step runs with no search path:
# the answer is the same on every host, a blocked report with exit status 2.
EXPECT_EXIT=2 STEP_PATH=/nonexistent-search-path step signin-status "intune-iac signin status --tenant 11111111-1111-4111-8111-111111111111" 'AZURE: BLOCKED (unknown: cli_not_found)' 'Exit code 2: blocked (0 means ready).'
step wizard "printf '%s\n' continue continue continue 22222222-2222-4222-8222-222222222222 continue continue continue continue generate continue continue plan approve execute reconcile continue finish | intune-iac wizard --journey --journey-mode simulation --session demo/journey.json --input examples/supported/input/export.json --context examples/context.json --output demo/journey-output" '"status": "complete_simulation"' '"execution_authorized": false'
step lab-create "intune-iac workbench lab-create --service-root demo/service --input examples/supported/input/export.json --object 22222222-2222-4222-8222-222222222222" '"status": "created"'
step store-init "intune-iac workbench init --root demo/store --tenant 11111111-1111-4111-8111-111111111111" '"evidence_class": "synthetic"'
step collect "intune-iac workbench collect --root demo/store --service-root demo/service" '"coverage": "complete"'
step start-demo "intune-iac start demo" 'Store' 'Service' 'Journey' 'Generated' 'Open the workspace'
step catalog "intune-iac catalog demo" 'INTEGRATION CATALOG' 'No other integration is available in this build.' 'GOAL change'
step workspace "printf 'select 22222222-2222-4222-8222-222222222222\nrelationships\nquit\n' | intune-iac workbench workspace --root demo/store --service-root demo/service" '"relation": "setting"' '"status": "closed"'
step workflow "intune-iac workbench workflow --root demo/store --policy 22222222-2222-4222-8222-222222222222 --service-root demo/service" '[WORKFLOW]' 'Position: observe' 'This view is read-only'
step engineering "intune-iac engineering" 'Engineering records are not configured'
step families "intune-iac workbench families" '"available": true'
step synthetic-estate "intune-iac synthetic generate --output demo/estate --policies 3" '"synthetic": true'

# What the build says it is, so the run names the exact files it exercised.
build_line() {
    .venv/bin/python -I -c 'import json, sys; b = json.load(sys.stdin)["build"]; print("build:", b["status"], b["product_version"], "commit", b["commit"], "content", b["content_sha256"])'
}
step build-identity "intune-iac doctor | build_line" 'build: identified'
tail -n 1 "$WORK/logs/$(printf '%02d' "$N")-build-identity.txt"

summary
