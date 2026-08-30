import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.evaluator import evaluate
R=Path(__file__).resolve().parents[1]/'backend/nexus/guidelines/encoded'

def ev(name,state):
    pkg=json.loads((R/name).read_text())
    return evaluate(pkg,state)

# Post-intravesical bladder state must stay in NMIBC logic and respect current TURBT/BCG state.
r=ev('nexus_bladder_cancer_v3_2026.json',{
    'cancer_type':'BLADDER_CANCER','primary_site':'BLADDER','histology':'UROTHELIAL',
    'treatment_phase':'POST_INTRAVESICAL','clinical_t':'T1','clinical_m':'M0','nmibc_risk':'HIGH',
    'visually_complete_turbt':True,'positive_urine_cytology':False,
    'adequate_bcg_received':True,'bcg_unresponsive':True,'radical_cystectomy_candidate':True})
assert r['status']=='RECOMMENDATION' and r['terminal']=='bcg_unresp_cyst_action',r

# Post-primary bone state must not replay initial therapy. Use a source-defined post-op chordoma state.
r=ev('nexus_bone_cancer_v1_2027.json',{
    'cancer_type':'BONE_CANCER','treatment_phase':'POST_PRIMARY','tumor_subtype':'CHORDOMA',
    'chordoma_subtype':'CONVENTIONAL','chordoma_subtype':'CONVENTIONAL','margin_status':'NEGATIVE','chordoma_large_extracompartmental':False})
assert r['status']=='RECOMMENDATION' and r['terminal']=='chor_surv',r

# Workup MPN must remain workup.
r=ev('nexus_myeloproliferative_neoplasms_v2_2026.json',{
    'cancer_type':'MYELOPROLIFERATIVE_NEOPLASM','treatment_phase':'WORKUP','subtype':'UNCLASSIFIED','blast_percentage':1})
assert r['status']=='RECOMMENDATION' and r['terminal']=='workup',r

# APL workup and post-induction must not leak into new-diagnosis induction.
r=ev('nexus_acute_myeloid_leukemia_v5_2026.json',{
    'cancer_type':'ACUTE_MYELOID_LEUKEMIA','disease_family':'APL','treatment_phase':'WORKUP'})
assert r['status']=='RECOMMENDATION' and r['terminal']=='apl_workup_action',r
r=ev('nexus_acute_myeloid_leukemia_v5_2026.json',{
    'cancer_type':'ACUTE_MYELOID_LEUKEMIA','disease_family':'APL','treatment_phase':'POST_INDUCTION'})
assert r['status']=='RECOMMENDATION' and r['terminal']=='apl_consolidation',r

# Advanced BTC phase must positively route into systemic-line logic rather than preoperative treatment.
r=ev('nexus_biliary_tract_cancers_v1_2026.json',{
    'cancer_type':'BILIARY_TRACT_CANCER','primary_site':'INTRAHEPATIC_CHOLANGIOCARCINOMA',
    'treatment_phase':'RECURRENT_UNRESECTABLE_METASTATIC','systemic_line':'FIRST'})
assert r['status'] in ('RECOMMENDATION','NEEDS_INFORMATION'),r
# It must never return an initial resection action in this care state.
assert r.get('terminal') not in {'i_resect','i_primary_resection','i_surgery'},r

# Semantic MX is unresolved and must not prove nonmetastatic anal cancer.
r=ev('nexus_anal_carcinoma_v2_2026.json',{
    'cancer_type':'ANAL_CARCINOMA','histology':'SQUAMOUS_CELL','primary_site':'ANAL_CANAL',
    'clinical_m':'MX','treatment_phase':'NEW_DIAGNOSIS'})
assert r['status']=='NEEDS_INFORMATION',r

# Whole-state schema validation is fail-closed.
r=ev('nexus_kidney_cancer_v1_2027.json',{
    'cancer_type':'KIDNEY_CANCER','treatment_phase':'NEW_DIAGNOSIS','clinical_t':'BOGUS'})
assert r['status']=='INVALID_INPUT',r

# Current active metastatic disease has care-state priority over a historical/postoperative phase label.
# It must never silently release postoperative surveillance; the engine should enter KID-4 and
# request only the immediately decision-relevant metastatic fact if still unknown.
r=ev('nexus_kidney_cancer_v1_2027.json',{
    'cancer_type':'KIDNEY_CANCER','treatment_phase':'POST_NEPHRECTOMY','clinical_m':'M1',
    'histology':'CLEAR_CELL','postop_resection_complete':True})
assert r.get('terminal') not in {'post_surv','kidney_postop_surveillance','post_cc_low','post_ncc_surv'},r
assert r['status'] in {'NEEDS_INFORMATION','RECOMMENDATION'},r
assert r.get('current_section')=='KID-4' or 'KID-4' in r.get('source_pathways',[]),r
r=ev('nexus_basal_cell_skin_cancer_v1_2027.json',{
    'cancer_type':'BASAL_CELL_SKIN_CANCER','treatment_phase':'POST_TREATMENT','disease_extent':'METASTATIC'})
# Active metastatic disease has priority over a historical/post-treatment phase label.
assert r.get('terminal') not in {'bcc_followup_recurrence','followup','local_followup'},r
assert r.get('current_section')=='BCC-5' or 'BCC-5' in r.get('source_pathways',[]),r
assert r['status'] in {'NEEDS_INFORMATION','RECOMMENDATION'},r

print('PHASE_AND_SCHEMA_SAFETY=PASS')
