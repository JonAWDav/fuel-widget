#!/bin/sh
set -eu

if [ "$(uname -s)" != Darwin ]; then
    echo 'The macOS launch agent requires macOS.' >&2
    exit 1
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
label='com.fuelwidget.app'
agents="$HOME/Library/LaunchAgents"
plist="$agents/$label.plist"
domain="gui/$(id -u)"

if [ -e "$plist" ] || launchctl print "$domain/$label" >/dev/null 2>&1; then
    echo 'Fuel launch agent already exists. Inspect it before changing startup settings.' >&2
    exit 1
fi

mkdir -p "$agents" "$root/state"
FUEL_INSTALL_ROOT="$root" FUEL_INSTALL_PLIST="$plist" \
    FUEL_INSTALL_NODE="$(command -v node)" \
    FUEL_INSTALL_CODEX="$(command -v codex 2>/dev/null || true)" \
    "$root/.venv/bin/python" - <<'PY'
import os
from pathlib import Path
import plistlib

root = Path(os.environ['FUEL_INSTALL_ROOT'])
environment = {
    'PATH': os.pathsep.join(p for p in (
        str(Path.home() / '.local/bin'), str(Path.home() / '.npm-global/bin'),
        str(Path.home() / '.bun/bin'), '/opt/homebrew/bin', '/usr/local/bin',
        '/usr/bin', '/bin', '/usr/sbin', '/sbin') if p),
    'FUEL_NODE': os.environ['FUEL_INSTALL_NODE'],
}
if os.environ.get('CODEX_BINARY') or os.environ.get('FUEL_INSTALL_CODEX'):
    environment['CODEX_BINARY'] = os.environ.get('CODEX_BINARY') or os.environ['FUEL_INSTALL_CODEX']
if os.environ.get('CLAUDE_CONFIG_DIR'):
    environment['CLAUDE_CONFIG_DIR'] = os.environ['CLAUDE_CONFIG_DIR']
job = {
    'Label': 'com.fuelwidget.app',
    'ProgramArguments': [str(root / '.venv/bin/python'), '-u', str(root / 'supervise.py')],
    'WorkingDirectory': str(root),
    'RunAtLoad': True,
    'KeepAlive': True,
    'ThrottleInterval': 5,
    'EnvironmentVariables': environment,
    'StandardOutPath': str(root / 'state/launchd.out.log'),
    'StandardErrorPath': str(root / 'state/launchd.err.log'),
}
with open(os.environ['FUEL_INSTALL_PLIST'], 'wb') as output:
    plistlib.dump(job, output)
PY

plutil -lint "$plist"
if [ "${1:-}" = '--prepare-only' ]; then
    echo "Prepared launch agent at $plist without starting it."
    exit 0
fi

started=$(date +%s)
launchctl bootstrap "$domain" "$plist"
launchctl print "$domain/$label" >/dev/null

attempt=0
while [ "$attempt" -lt 15 ]; do
    if "$root/.venv/bin/python" - "$root/state/health.json" "$started" <<'PY'
import json
from pathlib import Path
import sys
try:
    health = json.loads(Path(sys.argv[1]).read_text())
    ok = health.get('heartbeat', 0) >= float(sys.argv[2])
except (OSError, ValueError):
    ok = False
sys.exit(0 if ok else 1)
PY
    then
        echo 'Installed and started Fuel at sign-in.'
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 1
done

echo "Launch agent installed, but Fuel did not report healthy. Check $root/state/launchd.err.log" >&2
exit 1
