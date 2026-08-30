import {spawn, spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
process.chdir(ROOT);

function loadEnv(){
  const p=path.join(ROOT,'.env');
  if(!fs.existsSync(p)) return;
  for(const line of fs.readFileSync(p,'utf8').split(/\r?\n/)){
    if(!line || line.trim().startsWith('#') || !line.includes('=')) continue;
    const i=line.indexOf('='); const k=line.slice(0,i).trim(); const v=line.slice(i+1).trim();
    if(!(k in process.env)) process.env[k]=v;
  }
}
loadEnv();

const commonRepoNames=['NEXUS_15_CANCERS_ANTIGRAVITY_READY','NEXUS_15_CANCERS_PATHWAY_COMPLETE_AI_ENGINEERING_REVIEWED','NEXUS_15_CANCERS_ANTIGRAVITY_READY_FULL_REPO','2VNCCN','v1NCCN','NCCN-Nexus'];
function existingPythonCandidates(){
  const c=[];
  if(process.env.NEXUS_PYTHON) c.push(process.env.NEXUS_PYTHON);
  c.push(path.join(ROOT,'.venv','bin','python'));
  const roots=[];
  if(process.env.NEXUS_ENGINE_ROOT) roots.push(process.env.NEXUS_ENGINE_ROOT);
  for(const parent of [path.dirname(ROOT),path.join(os.homedir(),'Desktop')]) for(const name of commonRepoNames) roots.push(path.join(parent,name));
  for(const r of roots){ c.push(path.join(r,'backend','.venv','bin','python')); c.push(path.join(r,'.venv','bin','python')); }
  c.push('python3','python');
  return [...new Set(c)];
}
function runnable(bin){ const r=spawnSync(bin,['--version'],{stdio:'ignore'}); return r.status===0; }
function hasRuntimeDeps(bin){
  const r=spawnSync(bin,['-c','import fastapi,uvicorn,pydantic,httpx'],{stdio:'ignore'});
  return r.status===0;
}
let python=null;
for(const p of existingPythonCandidates()){
  if(runnable(p) && hasRuntimeDeps(p)){ python=p; break; }
}

if(!python){
  const system=existingPythonCandidates().find(runnable);
  if(!system){ console.error('Python 3 is required.'); process.exit(1); }
  const vpy=path.join(ROOT,'.venv','bin','python');
  console.log('NEXUS runtime dependencies were not found in an existing Python environment. Creating .venv…');
  let r=spawnSync(system,['-m','venv','.venv'],{stdio:'inherit'}); if(r.status!==0) process.exit(r.status??1);
  r=spawnSync(vpy,['-m','pip','install','-r','requirements.txt'],{stdio:'inherit'});
  if(r.status!==0){
    console.error('\nDependency installation failed. If your NEXUS backend already has a working virtualenv, set NEXUS_PYTHON=/full/path/to/backend/.venv/bin/python in .env and rerun npm run dev.');
    process.exit(r.status??1);
  }
  python=vpy;
}

const host=process.env.NEXUS_HOST||'127.0.0.1';
const port=process.env.NEXUS_PORT||'8000';
const url=`http://${host}:${port}`;
console.log(`\nNEXUS manual test starting at ${url}`);
console.log(`Python runtime: ${python}`);
console.log('Only PATIENT HISTORY + CURRENT OPD NOTE are required.');
console.log('The server verifies the exact final 15-package/984-decision engine before running a pathway.\n');

const child=spawn(python,['-m','uvicorn','integration_api.app:app','--host',host,'--port',port,'--reload'],{
  stdio:'inherit', env:{...process.env,PYTHONPATH:[ROOT,process.env.PYTHONPATH||''].filter(Boolean).join(path.delimiter)}
});
setTimeout(()=>{
  if(process.env.NEXUS_NO_OPEN==='1') return;
  if(process.platform==='darwin') spawn('open',[url],{stdio:'ignore',detached:true});
  else if(process.platform==='win32') spawn('cmd',['/c','start','',url],{stdio:'ignore'});
},1200);
for(const sig of ['SIGINT','SIGTERM']) process.on(sig,()=>{child.kill(sig);process.exit()});
child.on('exit',c=>process.exit(c??0));
