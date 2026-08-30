from __future__ import annotations
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from .models import RunNexusRequest
from .orchestrator import NexusOrchestrator
from .engine_adapter import DeterministicEngineAdapter, EngineNotFound

ROOT=Path(__file__).resolve().parents[1]
UI=ROOT/'frontend'/'index.html'
app=FastAPI(title='NEXUS History + OPD Manual Test',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
orch=NexusOrchestrator(ROOT)

@app.get('/')
def home():return FileResponse(UI)

@app.get('/api/health')
def health():
    extraction={
        'configured_provider':os.getenv('NEXUS_EXTRACTION_PROVIDER','auto'),
        'gemini_key_configured':bool(os.getenv('GEMINI_API_KEY','').strip()),
        'ollama_probe_enabled':not bool(os.getenv('RENDER') or os.getenv('NEXUS_DISABLE_OLLAMA','').strip().lower() in {'1','true','yes'}),
    }
    try:
        a=DeterministicEngineAdapter(ROOT)
        return {'status':'ok','engine_root':str(a.root),'encoded_packages':len(a.packages),'engine_signature':a.signature,'workflow':'FREE_TEXT→EXTRACTION→LONGITUDINAL_DELTA→CANCER_CLASSIFIER→CANONICAL_STATE→DETERMINISTIC_ENGINE','extraction':extraction}
    except EngineNotFound as e:
        return {'status':'engine_missing','message':str(e),'extraction':extraction}

@app.post('/api/v1/nexus/run')
async def run_nexus(req:RunNexusRequest):
    return await orch.run(req)

if __name__=='__main__':
    import uvicorn
    # Render (and most PaaS hosts) inject PORT and expect a 0.0.0.0 bind; NEXUS_HOST/NEXUS_PORT
    # remain for local overrides. This entrypoint is a fallback for `python -m integration_api.app`;
    # both tooling/dev.mjs (local) and render.yaml (Render) invoke uvicorn directly instead.
    uvicorn.run(app,host=os.getenv('NEXUS_HOST','0.0.0.0'),port=int(os.getenv('PORT',os.getenv('NEXUS_PORT','8000'))))
