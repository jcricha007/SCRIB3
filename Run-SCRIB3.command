#!/bin/bash
set -euo pipefail

finish() {
    local result=$?
    if [ "$result" -ne 0 ] && [ -t 0 ]; then
        printf '\nPress Return to close this window.'
        read -r _ || true
    fi
}
trap finish EXIT

repo_dir="$(cd "$(dirname "$0")" && pwd)"

if [ "$(uname -s)" != "Darwin" ]; then
    printf 'This launcher is for macOS. See README.md for Windows instructions.\n' >&2
    exit 1
fi

python_probe='import sys, tkinter, venv; sys.exit(0 if sys.version_info >= (3, 12) else 1)'

if [ -n "${SCRIB3_PYTHON:-}" ]; then
    candidates=("$SCRIB3_PYTHON")
else
    candidates=(
        "$repo_dir/.venv-macos/bin/python"
        python3.13 python3.12 python3.14 python3
        /Library/Frameworks/Python.framework/Versions/3.*/bin/python3
        /opt/homebrew/bin/python3
        /opt/homebrew/opt/python@3.13/bin/python3.13
        /opt/homebrew/opt/python@3.12/bin/python3.12
        /opt/homebrew/opt/python@3.14/bin/python3.14
        /usr/local/bin/python3
        /usr/local/opt/python@3.13/bin/python3.13
        /usr/local/opt/python@3.12/bin/python3.12
        /usr/local/opt/python@3.14/bin/python3.14
    )
fi

for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "$python_probe" >/dev/null 2>&1; then
        "$candidate" "$repo_dir/scripts/start_macos.py" "$@"
        exit "$?"
    fi
done

printf '%s\n' \
    'SCRIB3 needs Python 3.12 or newer with Tk.' \
    'Install Python using the macOS installer at https://www.python.org/downloads/macos/' \
    'Then run Install Certificates.command in its Applications/Python folder.' \
    'For Homebrew Python 3.13, run brew install python-tk@3.13.' \
    'If SCRIB3_PYTHON is set, check that it points to the Python executable you want to use.' >&2
exit 1
