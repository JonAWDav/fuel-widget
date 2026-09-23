#!/bin/sh
set -eu

if [ "$(uname -s)" != Darwin ]; then
    echo 'Fuel setup.sh supports macOS only.' >&2
    exit 1
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"

if ! command -v node >/dev/null 2>&1; then
    echo 'Install Node.js, then open a new Terminal window.' >&2
    exit 1
fi

python=''
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
        python="$candidate"
        break
    fi
done
if [ -z "$python" ]; then
    echo 'Install Python 3.11 or later, then open a new Terminal window.' >&2
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    "$python" -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
mkdir -p state

if [ "${1:-}" = '--no-startup' ]; then
    echo 'Installed without automatic startup. Run bash start-macos.sh to launch.'
else
    bash "$root/install-macos.sh"
fi
