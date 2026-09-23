import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {existsSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const windowsExe=process.env.APPDATA ? path.join(process.env.APPDATA,'npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe') : '';
const macCandidates=[
 path.join(os.homedir(),'.npm-global/bin/codex'),
 path.join(os.homedir(),'.local/bin/codex'),
 path.join(os.homedir(),'.bun/bin/codex'),
 '/opt/homebrew/bin/codex',
 '/usr/local/bin/codex'
];
const exe=process.env.CODEX_BINARY || (process.platform==='win32' && windowsExe && existsSync(windowsExe) ? windowsExe : '') ||
 (process.platform==='darwin' ? macCandidates.find(existsSync) : '') || 'codex';
const child=spawn(exe,['app-server','--stdio'],{windowsHide:true,stdio:['pipe','pipe','ignore']});
const pending=new Map(); let seq=0;
const deadline=setTimeout(()=>{child.kill(); process.exit(1)},25000);
child.on('error',()=>process.exit(1));
createInterface({input:child.stdout}).on('line',line=>{try{const m=JSON.parse(line); const p=pending.get(m.id); if(p){pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}}catch{}});
function req(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});child.stdin.write(JSON.stringify({id,method,params})+'\n')})}
try {
 await req('initialize',{clientInfo:{name:'fuel_widget',version:'1.0.0'},capabilities:{experimentalApi:true}});
 child.stdin.write(JSON.stringify({method:'initialized',params:{}})+'\n');
 const r=await req('account/rateLimits/read',{skipRateLimitResetCredits:true,supportsLunaReserveFallback:false});
 console.log(JSON.stringify(r));
} catch {process.exitCode=1} finally {clearTimeout(deadline);child.kill()}
