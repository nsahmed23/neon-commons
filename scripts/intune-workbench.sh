#!/usr/bin/bash
# Text/visual client launcher. This is not the protected execution worker.
# Invoke a trusted Bash with startup configuration disabled; see NATIVE-WINDOWS-R4.md.
set -eu

if [[ $# -lt 3 || $1 != --python || $3 != -- ]]; then
    printf '%s\n' 'usage: intune-workbench.sh --python ABSOLUTE_PYTHON -- [CLI arguments]' >&2
    exit 64
fi
python_executable=$2
shift 3
case "$python_executable" in
    /*|[A-Za-z]:/*|[A-Za-z]:\\*) ;;
    *) printf '%s\n' 'workbench_launcher_absolute_python_required' >&2; exit 64 ;;
esac
if [[ ! -f "$python_executable" || ! -x "$python_executable" ]]; then
    printf '%s\n' 'workbench_launcher_python_unavailable' >&2
    exit 66
fi

# Use Bash builtins: no PATH lookup or command-string evaluation for path assembly.
launcher_directory=${BASH_SOURCE[0]%/*}
launcher_directory=$(CDPATH='' builtin cd -- "$launcher_directory" && builtin pwd -P)
launcher="$launcher_directory/intune-iac.py"
if [[ ! -f "$launcher" ]]; then
    printf '%s\n' 'workbench_launcher_application_unavailable' >&2
    exit 66
fi

# Changes exist only in this child invocation. Filesystem arguments continue to
# use normal MSYS conversion; slash-prefixed Graph API paths retain their bytes.
# The application currently builds Graph routes internally. These two admitted
# prefixes also protect explicit path data at the native argument boundary.
(
    unset MSYS_NO_PATHCONV
    export MSYS2_ARG_CONV_EXCL='/beta/;/v1.0/'
    exec "$python_executable" -I -B "$launcher" "$@"
)
