"""Read-only account usage. Credentials stay in their existing stores."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import requests

ROOT = Path(__file__).resolve().parent

def window(label, used, reset):
    if used is None:
        return None
    used = float(used)
    if not 0 <= used <= 100:
        raise ValueError('Invalid usage percentage')
    if isinstance(reset, str):
        reset = dt.datetime.fromisoformat(reset.replace('Z', '+00:00')).timestamp()
    return {'label': label, 'remaining': 100-used, 'reset': reset}

def codex():
    node = os.environ.get('FUEL_NODE') or shutil.which('node')
    if not node: raise RuntimeError('Install Node.js and restart Fuel')
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
    result = subprocess.run([node, str(ROOT/'probe.mjs')],
        capture_output=True, text=True, timeout=30, **options)
    if result.returncode:
        raise RuntimeError('Codex connection unavailable')
    raw = json.loads(result.stdout)
    limit = (raw.get('rateLimitsByLimitId') or {}).get('codex') or raw.get('rateLimits') or {}
    windows = []
    for name in ('primary', 'secondary'):
        w = limit.get(name)
        if not w:
            continue
        minutes = w.get('windowDurationMins')
        label = {300:'5-hour', 10080:'Weekly', 1440:'Daily'}.get(minutes, f'{minutes} min' if minutes else 'Allowance')
        item = window(label, w.get('usedPercent'), w.get('resetsAt'))
        if item:
            windows.append(item)
    if not windows:
        raise RuntimeError('No Codex allowance returned')
    return {'windows':windows, 'blocked': raw.get('ordinaryUsageAllowed') is False}

def claude():
    config = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home()/'.claude')))
    credential_file = config/'.credentials.json'
    if credential_file.exists():
        raw_credentials = credential_file.read_text(encoding='utf-8')
    elif sys.platform == 'darwin':
        try:
            keychain = subprocess.run(['security','find-generic-password','-s','Claude Code-credentials','-w'],
                capture_output=True, text=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError('Claude credentials unavailable in Keychain') from None
        if keychain.returncode:
            raise RuntimeError('Claude credentials unavailable in Keychain')
        raw_credentials = keychain.stdout
    else:
        raise RuntimeError('Sign in to Claude Code')
    try:
        creds = json.loads(raw_credentials)['claudeAiOauth']
    except (ValueError, KeyError, TypeError):
        raise RuntimeError('Claude credentials unavailable') from None
    response = requests.get('https://api.anthropic.com/api/oauth/usage', headers={
        'Authorization':'Bearer '+creds['accessToken'], 'anthropic-beta':'oauth-2025-04-20'}, timeout=20)
    if response.status_code in (401,403):
        raise RuntimeError('Sign in to Claude Code')
    if response.status_code == 429:
        raise RuntimeError('Claude rate limited; retrying')
    response.raise_for_status()
    raw = response.json()
    windows = []
    for key,label in [('five_hour','5-hour'),('seven_day','Weekly')]:
        w=raw.get(key)
        if w:
            item=window(label,w.get('utilization'),w.get('resets_at'))
            if item:
                windows.append(item)
    if not windows:
        raise RuntimeError('No Claude allowance returned')
    for limit in raw.get('limits') or []:
        if limit.get('kind')!='weekly_scoped': continue
        scope=limit.get('scope') or {}
        name=(scope.get('model') or {}).get('display_name')
        if name and limit.get('percent') is not None:
            item=window(str(name)+' week',limit['percent'],limit.get('resets_at'))
            if item: windows.append(item)
    return {'windows':windows, 'blocked':False}

def effective(data):
    if not data or not data.get('windows'):
        return None
    if data.get('blocked'):
        return 0
    return min(w['remaining'] for w in data['windows'])

if __name__ == '__main__':
    for name,fn in [('Codex',codex),('Claude',claude)]:
        print(name, json.dumps(fn()))
