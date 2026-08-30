from __future__ import annotations
import asyncio,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

from integration_api.models import RunNexusRequest
from integration_api.orchestrator import NexusOrchestrator
from integration_api.extraction import validate_observations,_compact_schema
from integration_api.taxonomy import detect_cancer

FAKE_BREAST={
    'guideline_id':'NCCN_BREAST','title':'Breast Cancer','version':'6.2026',
    'fact_definitions':[
        {'key':'cancer_type','value_type':'CODED','allowed_values':['BREAST_CANCER'],'fact_role':'ROUTING'},
        {'key':'her2_status','value_type':'CODED','allowed_values':['POSITIVE','NEGATIVE','UNKNOWN'],'fact_role':'ROUTING'},
        {'key':'clinical_m','value_type':'CODED','allowed_values':['M0','M1','MX'],'semantic_unknown_values':['MX'],'fact_role':'ROUTING'},
        {'key':'hr_status','value_type':'CODED','allowed_values':['POSITIVE','NEGATIVE','UNKNOWN'],'fact_role':'ROUTING'},
        {'key':'synthetic_route','value_type':'CODED','allowed_values':['A','B'],'fact_role':'DERIVED_DETERMINISTIC','extraction_allowed':False},
    ],
    'nodes':{'met':{'kind':'action','source_pathways':['BINV-18']}},
    'coverage':{'primary_sections':{'BINV-18':{'physical_pages':[42],'source_anchor':'BINV-18:pages:42'}}},
}

class FakeAdapter:
    root=Path('/fake/final-engine')
    signature={'packages':15,'executable_decisions':984,'status':'FINAL_15_PACKAGE_SIGNATURE_VERIFIED'}
    def resolve(self,cancer_type):
        assert cancer_type=='BREAST_CANCER'
        return 'nexus_breast_cancer_v6_2026.json',FAKE_BREAST
    def evaluate(self,pkg,state):
        m=state.get('clinical_m')
        mv=m.get('value') if isinstance(m,dict) else m
        h=state.get('her2_status')
        hs=h.get('status') if isinstance(h,dict) else None
        if hs=='CONFLICT':
            return {'status':'REQUIRES_REVIEW','current_node':'her2_check','conflicts':['her2_status'],'missing_information':[],'source_pathways':['BINV-A']}
        if mv=='M1':
            return {'status':'NEEDS_INFORMATION','current_node':'met','current_section':'BINV-18','missing_information':['hr_status'],'source_pathways':['BINV-18'],'trace':[{'node_id':'metastatic','result':True}]}
        return {'status':'NEEDS_INFORMATION','current_node':'m_check','missing_information':['clinical_m'],'source_pathways':['BINV-1']}

async def run(history,note):
    o=NexusOrchestrator(ROOT);o._adapter=FakeAdapter()
    return await o.run(RunNexusRequest(patient_history=history,current_opd_note=note))

# Acronym false positives: ordinary English 'all'/'gist' must not select cancer.
m=detect_cancer('', 'All results reviewed today. We discussed the gist of the plan.')
assert m.status=='NOT_DETECTED',m

# Unsupported explicit primary overrides historical supported disease when current note names it.
m=detect_cancer('Breast cancer diagnosed in 2024.','Today biopsy confirms pancreatic adenocarcinoma.')
assert m.status=='UNSUPPORTED',m

# LLM extraction schema cannot include cancer selector or guideline-derived route facts.
schema={x['key'] for x in _compact_schema(FAKE_BREAST)}
assert 'cancer_type' not in schema and 'synthetic_route' not in schema,schema

# Hallucinated evidence is rejected even when fact/value are otherwise legal.
obs,un=validate_observations([{'fact_id':'her2_status','value':'POSITIVE','status':'CONFIRMED','evidence_text':'HER2 positive'}],FAKE_BREAST,'CURRENT_OPD','Biopsy shows HER2 negative.')
assert not obs and any('could not be grounded' in x for x in un),(obs,un)

# Never invent HR status. Explicit HER2 negative is extracted; absent HR remains absent.
r=asyncio.run(run('', '58-year-old woman with invasive breast carcinoma. HER2 negative.'))
cf=r['extraction']['canonical_facts_sent_to_engine']
assert cf['cancer_type']['value']=='BREAST_CANCER',cf
assert cf['her2_status']['value']=='NEGATIVE',cf
assert 'hr_status' not in cf,cf
assert r['nexus_result']['status']=='NEEDS_INFORMATION',r

# Historical M0 is superseded by explicit current distant metastatic evidence, without routing back to old state.
r=asyncio.run(run('Breast cancer diagnosed in 2024. Clinical M0 at diagnosis.', 'PET-CT now shows liver and bone metastases.'))
cf=r['extraction']['canonical_facts_sent_to_engine']
assert cf['clinical_m']['value']=='M1',cf
assert r['extraction']['updated_facts'],r['extraction']
assert r['extraction']['superseded_facts'],r['extraction']
assert r['nexus_result']['current_pathway_node']=='met',r
assert r['nexus_result']['status']=='NEEDS_INFORMATION',r
assert r['nexus_result']['missing_pathway_changing_facts']==['hr_status'],r

# Same biomarker with conflicting chronology stays a conflict unless note explicitly marks newer/repeat evidence.
r=asyncio.run(run('Breast carcinoma. HER2 negative.', 'Breast carcinoma. HER2 positive.'))
assert r['extraction']['canonical_facts_sent_to_engine']['her2_status']['status']=='CONFLICT',r
assert r['nexus_result']['status']=='REQUIRES_REVIEW',r

r=asyncio.run(run('Breast carcinoma. HER2 negative.', 'Breast carcinoma. New repeat biopsy now confirms HER2 positive.'))
assert r['extraction']['canonical_facts_sent_to_engine']['her2_status']['value']=='POSITIVE',r
assert r['extraction']['updated_facts'],r

print('FREE_TEXT_INTEGRATION_CONTRACT=PASS')
