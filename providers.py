"""Read-only provider adapters and bounded Windows app discovery.

Only allowlisted credential names are read. Nothing is copied into app state.
"""
import json
import math
import os
import re
from pathlib import Path
import shutil
import socket
import requests
import yaml
from feeds import codex, claude, window

def setting(name):
    value = os.environ.get(name)
    if value: return value
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
            return str(winreg.QueryValueEx(key,name)[0])
    except (ImportError,OSError): return ''

def hermes_home():
    return Path(setting('HERMES_HOME') or Path.home()/'.hermes')

def secret(name):
    value = setting(name)
    if value: return value
    try:
        for line in (hermes_home()/'.env').read_text(encoding='utf-8').splitlines():
            key,sep,value=line.partition('=')
            if sep and key.strip().removeprefix('export ')==name:
                return value.strip().strip('"').strip("'")
    except OSError: pass
    return ''

def get_json(url, token='', local=False):
    session=requests.Session()
    if local: session.trust_env=False
    with session:
        r=session.get(url,headers={'Authorization':'Bearer '+token} if token else {},timeout=(2,12),allow_redirects=False)
        if r.status_code in (401,403): raise RuntimeError('Sign-in needs attention')
        if r.status_code==429: raise RuntimeError('Rate limited; retrying soon')
        if r.status_code!=200: raise RuntimeError('Usage service unavailable')
        return r.json()

def number(value):
    try: value=float(value)
    except (TypeError,ValueError): raise RuntimeError('Usage response changed') from None
    if not math.isfinite(value):
        raise RuntimeError('Usage response changed')
    return float(value)

def parse_kimi(raw):
    windows=[]
    # Kimi Code's direct coding API reports usage and rolling limits.
    entries=[]
    if raw.get('usage'): entries.append(('Plan',raw['usage']))
    for i,limit in enumerate(raw.get('limits') or []):
        detail=limit.get('detail') or limit
        duration=(limit.get('window') or {}).get('duration')
        entries.append(('5-hour' if duration==5 else f'Window {i+1}',detail))
    for label,item in entries:
        total=number(item.get('limit'))
        remaining=number(item.get('remaining'))
        if total>0: windows.append(window(label,max(0,min(100,100*(1-remaining/total))),item.get('resetTime')))
    if not windows: raise RuntimeError('Kimi quota format unavailable')
    return {'windows':windows,'blocked':False}

def kimi():
    key=secret('KIMI_CODE_API_KEY') or secret('KIMI_CODING_API_KEY') or secret('KIMI_API_KEY') or secret('MOONSHOT_API_KEY')
    if not key: raise RuntimeError('Kimi API key not connected')
    if key.startswith('sk-kimi-'):
        return parse_kimi(get_json('https://api.kimi.com/coding/v1/usages',key))
    raw=get_json('https://api.moonshot.ai/v1/users/me/balance',key)
    if raw.get('code')!=0: raise RuntimeError('Kimi balance unavailable')
    balance=number(raw.get('data',{}).get('available_balance'))
    return {'kind':'balance','windows':[],'balance':balance,'unit':'USD',
            'detail':'Moonshot API prepaid balance','subtitle':'Kimi API'}

def openrouter():
    raw=get_json('https://openrouter.ai/api/v1/key',secret('OPENROUTER_API_KEY')).get('data',{})
    limit=raw.get('limit'); remaining=raw.get('limit_remaining')
    windows=[]
    if limit is not None and remaining is not None and number(limit)>0:
        windows=[window('Key budget',max(0,min(100,100*(1-number(remaining)/number(limit)))),None)]
    return {'kind':'balance','windows':windows,'balance':number(remaining) if remaining is not None else None,
            'unit':'USD','spent':number(raw.get('usage',0)), 'detail':'API key budget' if limit is not None else 'No key spending cap',
            'subtitle':'OpenRouter'}

def ollama():
    raw=get_json('http://127.0.0.1:11434/api/ps',local=True)
    if not isinstance(raw.get('models'),list): raise RuntimeError('Ollama response unavailable')
    models=[str(m.get('name','Model')) for m in raw['models']]
    memory=sum(number(m.get('size_vram',0)) for m in raw['models'])/1024**3
    return {'kind':'local','windows':[],'models':models,'detail':f'{len(models)} loaded / {memory:.1f} GB VRAM',
            'subtitle':'Local models; no subscription quota'}

def lmstudio():
    raw=get_json('http://127.0.0.1:1234/api/v1/models',setting('LM_API_TOKEN'),local=True)
    models=raw.get('models')
    if not isinstance(models,list): raise RuntimeError('LM Studio v1 API unavailable')
    loaded=[str(m.get('display_name') or m.get('key') or 'Model') for m in models if m.get('loaded_instances')]
    return {'kind':'local','windows':[],'models':loaded,'detail':f'{len(loaded)} models loaded',
            'subtitle':'Local models; no subscription quota'}

READERS={'Codex':codex,'Claude':claude,'Kimi':kimi,'OpenRouter':openrouter,'Ollama':ollama,'LM Studio':lmstudio}

def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=.15): return True
    except OSError: return False

def installed_names():
    names=[]
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            for branch in ('SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall',
                           'SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall'):
                try:
                    with winreg.OpenKey(hive,branch) as root:
                        for i in range(winreg.QueryInfoKey(root)[0]):
                            try:
                                with winreg.OpenKey(root,winreg.EnumKey(root,i)) as item:
                                    names.append(str(winreg.QueryValueEx(item,'DisplayName')[0]).lower())
                            except OSError: pass
                except OSError: pass
    except ImportError: pass
    return names

def discover():
    result={'Codex':{'kind':'meter'},'Claude':{'kind':'meter'}}
    home=Path.home(); appdata=Path(os.environ.get('APPDATA',home)); local=Path(os.environ.get('LOCALAPPDATA',home))
    installed=installed_names()
    catalog={
        'Cursor':([home/'.cursor',appdata/'Cursor'], 'cursor'),
        'Gemini':([home/'.gemini'],'gemini'),
        'Windsurf':([home/'.codeium',appdata/'Windsurf'],'windsurf'),
        'Kimi':([home/'.kimi',home/'.kimi-code'],'kimi'),
        'Hermes':([hermes_home(),local/'hermes'],'hermes'),
        'Ollama':([home/'.ollama',local/'Ollama'],'ollama'),
        'LM Studio':([home/'.lmstudio',appdata/'LM Studio'],'lms'),
        'ChatGPT':([],None), 'GitHub Copilot':([home/'.copilot'],None),
        'Jan':([home/'.jan',appdata/'Jan'],None),
        'GPT4All':([local/'nomic.ai'],None), 'AnythingLLM':([appdata/'anythingllm-desktop'],None),
        'Msty':([appdata/'Msty'],None), 'Chatbox':([appdata/'xyz.chatboxapp.app'],None),
        'Perplexity':([],None), 'DeepSeek':([],None)}
    for name,(paths,command) in catalog.items():
        if any(p.exists() for p in paths) or (command and shutil.which(command)) or any(n==name.lower() or n.startswith(name.lower()+' ') for n in installed):
            result[name]={'kind':'detected','detail':'Usage is not exposed to Fuel','subtitle':'Detected on this PC'}
    for name,key in [('Gemini','GEMINI_API_KEY'),('OpenAI API','OPENAI_API_KEY'),('Anthropic API','ANTHROPIC_API_KEY'),
                     ('DeepSeek','DEEPSEEK_API_KEY'),('Grok','XAI_API_KEY'),('Groq','GROQ_API_KEY'),('Mistral','MISTRAL_API_KEY')]:
        if secret(key): result[name]={'kind':'detected','detail':'Usage needs a provider adapter','subtitle':'API credential detected'}
    if secret('OPENROUTER_API_KEY'): result['OpenRouter']={'kind':'meter'}
    if any(secret(k) for k in ('KIMI_CODE_API_KEY','KIMI_CODING_API_KEY','KIMI_API_KEY','MOONSHOT_API_KEY')): result['Kimi']={'kind':'meter'}
    for name,port in [('Ollama',11434),('LM Studio',1234)]:
        if port_open(port): result[name]={'kind':'meter'}
    if 'Hermes' in result:
        try:
            conf=yaml.safe_load((hermes_home()/'config.yaml').read_text(encoding='utf-8')) or {}
            model=conf.get('model',{})
            provider=model.get('provider','') if isinstance(model,dict) else ''
            linked={'kimi-coding':'Kimi','openrouter':'OpenRouter','anthropic':'Claude','openai-codex':'Codex','ollama':'Ollama'}.get(provider)
            result['Hermes']={'kind':'linked' if linked else 'detected','linked':linked,
                'detail':f'Allowance shown under {linked}' if linked else 'Provider usage not connected',
                'subtitle':'Agent uses its configured provider'}
        except (OSError,ValueError,yaml.YAMLError): pass
    for app in installed:
        if re.search(r'\b(ai|llm|gpt|copilot)\b',app) and not any(name.lower() in app for name in result):
            result[app[:60]]={'kind':'detected','detail':'Usage needs a provider adapter','subtitle':'Detected AI desktop app'}
        if len(result)>=30:break
    return result
