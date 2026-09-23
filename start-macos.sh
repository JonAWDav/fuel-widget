#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$(uname -s)" != Darwin ]; then
    echo 'Fuel start-macos.sh supports macOS only.' >&2
    exit 1
fi
if [ ! -x "$root/.venv/bin/python" ]; then
    echo 'Run bash setup.sh first.' >&2
    exit 1
fi

rm -f "$root/state/paused"
if launchctl print "gui/$(id -u)/com.fuelwidget.app" >/dev/null 2>&1; then
    launchctl kickstart -k "gui/$(id -u)/com.fuelwidget.app"
else
    nohup "$root/.venv/bin/python" -u "$root/supervise.py" \
        >>"$root/state/launchd.out.log" 2>>"$root/state/launchd.err.log" </dev/null &
fi
echo 'Fuel starting.'
