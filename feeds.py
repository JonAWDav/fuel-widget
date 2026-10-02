"""Read-only account usage. Credentials stay in their existing stores."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
import requests

ROOT = Path(__file__).resolve().parent

class RateLimited(RuntimeError):
    """Carries the server's Retry-After so the widget can stay quiet long enough."""
    def __init__(self, message, seconds=None):
        super().__init__(message)
        try: self.seconds = max(0., float(seconds)) if seconds is not None else None
        except (TypeError, ValueError): self.seconds = None

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
    if time.time() < _claude_usage_locked_until:
        return claude_from_headers(creds['accessToken'])
    response = requests.get('https://api.anthropic.com/api/oauth/usage', headers={
        'Authorization':'Bearer '+creds['accessToken'], 'anthropic-beta':'oauth-2025-04-20'}, timeout=20)
    if response.status_code in (401,403):
        raise RuntimeError('Sign in to Claude Code')
    if response.status_code == 429:
        # The usage endpoint can stay locked for days. Leave it alone for a while and
        # read the same allowance from the rate-limit headers on a 1-token request.
        try: wait = float(response.headers.get('Retry-After') or 0)
        except ValueError: wait = 0
        _lock_claude_usage(max(wait, 3600))
        return claude_from_headers(creds['accessToken'])
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

_claude_usage_locked_until = 0.

def _lock_claude_usage(seconds):
    global _claude_usage_locked_until
    _claude_usage_locked_until = time.time() + seconds

def claude_from_headers(token):
    """Fallback: the unified rate-limit headers carry the same 5-hour and weekly utilisation."""
    response = requests.post('https://api.anthropic.com/v1/messages', headers={
        'Authorization':'Bearer '+token, 'anthropic-beta':'oauth-2025-04-20',
        'anthropic-version':'2023-06-01', 'content-type':'application/json'},
        json={'model':'claude-haiku-4-5-20251001', 'max_tokens':1,
              'system':"You are Claude Code, Anthropic's official CLI for Claude.",
              'messages':[{'role':'user','content':'hi'}]}, timeout=30)
    if response.status_code in (401,403):
        raise RuntimeError('Sign in to Claude Code')
    if response.status_code == 429 and not response.headers.get('anthropic-ratelimit-unified-5h-utilization'):
        raise RateLimited('Claude rate limited; retrying', response.headers.get('Retry-After'))
    return parse_claude_headers(response.headers)

def parse_claude_headers(headers):
    windows = []
    for key,label in [('5h','5-hour'),('7d','Weekly')]:
        used = headers.get(f'anthropic-ratelimit-unified-{key}-utilization')
        if used is None: continue
        try: used = float(used)*100
        except ValueError: raise RuntimeError('Usage response changed') from None
        reset = headers.get(f'anthropic-ratelimit-unified-{key}-reset')
        item = window(label, max(0, min(100, used)), float(reset) if reset else None)
        if item: windows.append(item)
    if not windows:
        raise RuntimeError('No Claude allowance returned')
    return {'windows':windows, 'blocked':headers.get('anthropic-ratelimit-unified-status') == 'rejected'}

def effective(data):
    if not data or not data.get('windows'):
        return None
    if data.get('blocked'):
        return 0
    return min(w['remaining'] for w in data['windows'])

if __name__ == '__main__':
    for name,fn in [('Codex',codex),('Claude',claude)]:
        print(name, json.dumps(fn()))
