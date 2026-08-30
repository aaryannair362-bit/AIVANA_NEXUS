from __future__ import annotations
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
    try:
        a=DeterministicEngineAdapter(ROOT)
        return {'status':'ok','engine_root':str(a.root),'encoded_packages':len(a.packages),'engine_signature':a.signature,'workflow':'FREE_TEXT→EXTRACTION→LONGITUDINAL_DELTA→CANCER_CLASSIFIER→CANONICAL_STATE→DETERMINISTIC_ENGINE'}
    except EngineNotFound as e:
        return {'status':'engine_missing','message':str(e)}

@app.post('/api/v1/nexus/run')
async def run_nexus(req:RunNexusRequest):
    return await orch.run(req)
