import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.evaluator import evaluate
R=Path(__file__).resolve().parents[1]

def load(name): return json.loads((R/'backend/nexus/guidelines/encoded'/name).read_text())

def run(name,state,expect):
    r=evaluate(load(name),state); assert r['status']==expect,(name,state,r); return r

# GIST limited progression: exact option applicability must be resolvable.
r=run('nexus_gastrointestinal_stromal_tumors_v1_2026.json',{
    'cancer_type':'GIST','treatment_phase':'PROGRESSIVE','progression_extent':'LIMITED',
    'local_progression_amenable':False},'RECOMMENDATION')
assert r['terminal']=='prog_limited',r
assert 'gist_prog_switch' in {o['option_id'] for o in r['guideline_concordant_options']},r

# Basal-cell high-risk primary surgery route uses source-defined risk factor + feasibility.
r=run('nexus_basal_cell_skin_cancer_v1_2027.json',{
    'cancer_type':'BASAL_CELL_SKIN_CANCER','treatment_phase':'NEW_DIAGNOSIS','disease_extent':'LOCAL',
    'local_recurrence':False,'location_high_risk':True,'named_nerve_involvement':False,
    'surgery_feasible':True},'RECOMMENDATION')
assert r['terminal']=='high_primary_surgery',r

# Kidney post-nephrectomy high-risk clear-cell state.
r=run('nexus_kidney_cancer_v1_2027.json',{
    'cancer_type':'KIDNEY_CANCER','treatment_phase':'POST_NEPHRECTOMY','histology':'CLEAR_CELL',
    'postop_resection_complete':True,'postop_high_risk':True,'grade4_or_sarcomatoid':True,
    'clinical_t':'T3','clinical_m':'M0','resectable':True},'RECOMMENDATION')
assert r['terminal']=='post_cc_high',r

# Cervical active metastatic first-line state must reach the line/biomarker-aware route.
r=run('nexus_cervical_cancer_v2_2026.json',{
    'cancer_type':'CERVICAL_CANCER','histology':'SQUAMOUS_ADENO_ADENOSQUAMOUS',
    'treatment_phase':'DISTANT_METASTATIC_RECURRENCE','figo_stage':'IVB',
    'distant_metastases':True,'local_treatment_amenable':False,'systemic_line':'FIRST',
    'pd_l1_positive':False,'cisplatin_intolerant':False},'RECOMMENDATION')
assert r['terminal']=='met_first_standard',r

# AML post-induction remission: risk/transplant-aware consolidation branch.
r=run('nexus_acute_myeloid_leukemia_v5_2026.json',{
    'cancer_type':'ACUTE_MYELOID_LEUKEMIA','disease_family':'NON_APL_AML',
    'treatment_phase':'POST_INDUCTION','response_status':'CR','eln_risk':'INTERMEDIATE',
    'flt3_mutation':False,'transplant_candidate':True,'induction_regimen':'CPX351'},'RECOMMENDATION')
assert r['terminal']=='consol_intermediate',r

# Semantic unknown must fail closed, not prove nonmetastatic.
r=run('nexus_anal_carcinoma_v2_2026.json',{
    'cancer_type':'ANAL_CARCINOMA','histology':'SQUAMOUS_CELL','primary_site':'ANAL_CANAL',
    'clinical_m':'MX','treatment_phase':'NEW_DIAGNOSIS'},'NEEDS_INFORMATION')
print('SMOKE_TESTS=PASS')
