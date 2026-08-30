import {spawnSync} from 'node:child_process';
import fs from 'node:fs';import path from 'node:path';import os from 'node:os';import {fileURLToPath} from 'node:url';
const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'); process.chdir(ROOT);
function loadEnv(){const p=path.join(ROOT,'.env');if(!fs.existsSync(p))return;for(const line of fs.readFileSync(p,'utf8').split(/\r?\n/)){if(!line||line.trim().startsWith('#')||!line.includes('='))continue;const i=line.indexOf('=');const k=line.slice(0,i).trim(),v=line.slice(i+1).trim();if(!(k in process.env))process.env[k]=v}}loadEnv();
const candidates=[process.env.NEXUS_PYTHON,path.join(ROOT,'.venv','bin','python'),'python3','python'].filter(Boolean);
let py=null;for(const c of candidates){if(spawnSync(c,['--version'],{stdio:'ignore'}).status===0){py=c;break}}
if(!py){console.error('Python 3 not found');process.exit(1)}
const code=`from pathlib import Path\nfrom integration_api.engine_adapter import DeterministicEngineAdapter,EngineNotFound\ntry:\n a=DeterministicEngineAdapter(Path.cwd());print('ENGINE_ROOT='+str(a.root));print('FINAL_ENGINE_SIGNATURE='+str(a.signature));print('DOCTOR=PASS')\nexcept Exception as e:\n print('DOCTOR=FAIL');print(type(e).__name__+': '+str(e));raise SystemExit(1)`;
const r=spawnSync(py,['-c',code],{cwd:ROOT,stdio:'inherit',env:{...process.env,PYTHONPATH:[ROOT,process.env.PYTHONPATH||''].filter(Boolean).join(path.delimiter)}});process.exit(r.status??1);
