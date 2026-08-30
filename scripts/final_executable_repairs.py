from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ENC=ROOT/'backend/nexus/guidelines/encoded'

def load(name):
    p=ENC/name
    return p,json.loads(p.read_text())

def save(p,d): p.write_text(json.dumps(d,indent=2))

def prov(guideline,version,section,pages):
    return {'guideline':guideline,'version':version,'section':section,'page_label':section,'physical_pages':pages,'source_anchor':f"{section}:pages:{','.join(map(str,pages))}"}

def ensure_unknown_in_coded_domains(d):
    for fd in d.get('fact_definitions',[]):
        if fd.get('value_type')=='CODED' and 'UNKNOWN' in fd.get('semantic_unknown_values',[]) and 'UNKNOWN' not in fd.get('allowed_values',[]):
            fd.setdefault('allowed_values',[]).append('UNKNOWN')

def add_fact(d, fd):
    if not any(x.get('key')==fd['key'] for x in d['fact_definitions']): d['fact_definitions'].append(fd)

# Global semantic-UNKNOWN domain consistency.
for p in ENC.glob('*.json'):
    d=json.loads(p.read_text()); ensure_unknown_in_coded_domains(d); save(p,d)

# AML: remove graph-impossible duplicate options and redundant applicability inside already FLT3-gated branch.
p,d=load('nexus_acute_myeloid_leukemia_v5_2026.json')
for nid, oid in [('adverse_options','aml_adv_cpx'),('consol_adverse','aml_consol_adv_lower')]:
    opts=d['nodes'][nid]['recommendation']['options']
    d['nodes'][nid]['recommendation']['options']=[o for o in opts if o.get('option_id')!=oid]
for o in d['nodes']['maintenance_flt3_postchemo']['recommendation']['options']:
    if o.get('option_id')=='aml_postchemo_mido': o.pop('applicability',None)
save(p,d)

# B-cell: distinguish aggressive vs less-aggressive MCL induction at response assessment; remove redundant transplant filter in already transplant-intent DLBCL branch.
p,d=load('nexus_b_cell_lymphomas_v4_2026.json')
add_fact(d,{
    'key':'mcl_induction_strategy','value_type':'CODED','allowed_values':['AGGRESSIVE','LESS_AGGRESSIVE','UNKNOWN'],
    'semantic_unknown_values':['UNKNOWN'],'fact_role':'ROUTING',
    'description':'Actual MCL induction strategy used for the current response assessment timepoint; do not infer from candidacy alone.'
})
d['nodes']['mcl_response']['on']['TRUE']='mcl_cr_strategy'
d['nodes']['mcl_cr_strategy']={
    'kind':'decision','label':'Was the current MCL response assessed after aggressive induction?',
    'expression':{'fact':'mcl_induction_strategy','op':'eq','value':'AGGRESSIVE'},
    'on':{'TRUE':'mcl_cr_mrd','FALSE':'mcl_cr_maintenance'},
    'source_pathways':['MANT-4','MANT-5'],'decision_id':'mcl_cr_induction_strategy'
}
d['nodes']['mcl_cr_maintenance']['label']='MCL CR after less-aggressive induction: rituximab maintenance/clinical follow-up according to MANT-5.'
d['nodes']['mcl_cr_maintenance']['source_pathways']=['MANT-5']
d['nodes']['mcl_cr_maintenance']['recommendation']['title']=d['nodes']['mcl_cr_maintenance']['label']
for o in d['nodes']['dlbcl_late_salvage']['recommendation']['options']:
    if o.get('option_id')=='dlbcl_hdt_ascr': o.pop('applicability',None)
save(p,d)

# Bladder/UTUC: replace broken self-loop/generic high-grade shortcut with executable UTT-2 risk table.
p,d=load('nexus_bladder_cancer_v3_2026.json')
add_fact(d,{'key':'upper_tract_focality','value_type':'CODED','allowed_values':['UNIFOCAL','MULTIFOCAL','UNKNOWN'],'semantic_unknown_values':['UNKNOWN'],'fact_role':'ROUTING'})
add_fact(d,{'key':'upper_tract_size_cm','value_type':'NUMERIC','fact_role':'ROUTING'})
add_fact(d,{'key':'upper_tract_obstruction_or_invasion','value_type':'BOOLEAN','fact_role':'ROUTING'})
# The location remains clinically relevant to UTT-3 and is now used explicitly for ureter-specific management.
d['nodes']['utt_grade']['on']={'TRUE':'utt_high_obstruction','FALSE':'utt_low_focality'}
# remove obsolete/broken nodes
for n in ['utt_low','utt_low_base','utt_low_need_location','utt_high']:
    d['nodes'].pop(n,None)

d['nodes'].update({
'utt_low_focality':{
 'kind':'decision','label':'Low-grade UTUC unifocal?','expression':{'fact':'upper_tract_focality','op':'eq','value':'UNIFOCAL'},
 'on':{'TRUE':'utt_low_size','FALSE':'utt_low_intermediate'},'source_pathways':['UTT-2'],'decision_id':'utt_low_focality'},
'utt_low_size':{
 'kind':'decision','label':'Low-grade unifocal UTUC <1.5 cm?','expression':{'fact':'upper_tract_size_cm','op':'lt','value':1.5},
 'on':{'TRUE':'utt_low_risk','FALSE':'utt_low_intermediate'},'source_pathways':['UTT-2'],'decision_id':'utt_low_size_1_5'},
'utt_low_risk':{
 'kind':'action','label':'Low-risk UTUC (low grade, unifocal, <1.5 cm): kidney-sparing endoscopic/chemo-ablation or surveillance per UTT-2.',
 'status':'RECOMMENDATION','recommendation_id':'utt_low_risk','source_pathways':['UTT-2'],'pathway_id':'UTUC_LOW_RISK',
 'recommendation':{'title':'Low-risk UTUC','options':[
   {'option_id':'utt_low_endoscopic','label':'Endoscopic ablation','text':'Thermal or laser endoscopic ablation.','decision_relevant':True,'source_provenance':prov('Bladder Cancer','3.2026','UTT-2',[57])},
   {'option_id':'utt_low_chemoablation','label':'Chemo-ablation','text':'Chemo-ablation where source-defined.','decision_relevant':True,'source_provenance':prov('Bladder Cancer','3.2026','UTT-2',[57])},
   {'option_id':'utt_low_surveillance','label':'Endoscopic/urographic surveillance','text':'Periodic endoscopy and upper-tract urography.','decision_relevant':True,'source_provenance':prov('Bladder Cancer','3.2026','UTT-2',[57])}
 ],'supporting_sections':['BL-F'],'next_steps':[]}},
'utt_low_intermediate':{
 'kind':'action','label':'Low-intermediate-risk UTUC (low grade with multifocality or size >=1.5 cm): endoscopic ablation plus intrapelvic therapy per UTT-2.',
 'status':'RECOMMENDATION','recommendation_id':'utt_low_intermediate','source_pathways':['UTT-2'],'pathway_id':'UTUC_LOW_INTERMEDIATE',
 'recommendation':{'title':'Low-intermediate-risk UTUC','options':[
   {'option_id':'utt_lowint_endo_intrapelvic','label':'Endoscopic ablation + intrapelvic therapy','text':'Thermal/laser endoscopic ablation plus retrograde or antegrade intrapelvic therapy.','decision_relevant':True,'source_provenance':prov('Bladder Cancer','3.2026','UTT-2',[57])}
 ],'supporting_sections':['BL-F'],'next_steps':[]}},
'utt_high_obstruction':{
 'kind':'decision','label':'High-grade UTUC with renal obstruction or invasion on axial imaging?','expression':{'fact':'upper_tract_obstruction_or_invasion','op':'eq','value':True},
 'on':{'TRUE':'utt_high_risk','FALSE':'utt_high_focality'},'source_pathways':['UTT-2'],'decision_id':'utt_high_obstruction_invasion'},
'utt_high_focality':{
 'kind':'decision','label':'High-grade UTUC multifocal?','expression':{'fact':'upper_tract_focality','op':'eq','value':'MULTIFOCAL'},
 'on':{'TRUE':'utt_high_risk','FALSE':'utt_high_size'},'source_pathways':['UTT-2'],'decision_id':'utt_high_focality'},
'utt_high_size':{
 'kind':'decision','label':'High-grade unifocal UTUC <1.5 cm?','expression':{'fact':'upper_tract_size_cm','op':'lt','value':1.5},
 'on':{'TRUE':'utt_high_intermediate','FALSE':'utt_high_risk'},'source_pathways':['UTT-2'],'decision_id':'utt_high_size_1_5'},
'utt_high_intermediate':{
 'kind':'action','label':'High-intermediate-risk UTUC (high grade, unifocal, <1.5 cm): standard radical nephroureterectomy; nephron-sparing endoscopic/intrapelvic approach only for imperative nephron-sparing circumstances.',
 'status':'RECOMMENDATION','recommendation_id':'utt_high_intermediate','source_pathways':['UTT-2'],'pathway_id':'UTUC_HIGH_INTERMEDIATE',
 'recommendation':{'title':'High-intermediate-risk UTUC','options':[
   {'option_id':'utt_hiint_rnu','label':'Radical nephroureterectomy with bladder cuff','text':'With perioperative intravesical chemotherapy and consideration of neoadjuvant chemotherapy in selected patients.','decision_relevant':True,'applicability':{'fact':'nephron_sparing_required_or_preferred','op':'eq','value':False},'source_provenance':prov('Bladder Cancer','3.2026','UTT-2',[57])},
   {'option_id':'utt_hiint_nephron','label':'Endoscopic ablation + intrapelvic therapy','text':'Imperative nephron-sparing pathway.','decision_relevant':True,'applicability':{'fact':'nephron_sparing_required_or_preferred','op':'eq','value':True},'source_provenance':prov('Bladder Cancer','3.2026','UTT-2',[57])}
 ],'supporting_sections':['BL-F','BL-G'],'next_steps':[]}},
'utt_high_risk':{
 'kind':'action','label':'High-risk UTUC (high grade with multifocality, size >=1.5 cm, obstruction, or invasion): radical nephroureterectomy; source-defined alternative for imperative nephron sparing.',
 'status':'RECOMMENDATION','recommendation_id':'utt_high_risk','source_pathways':['UTT-2'],'pathway_id':'UTUC_HIGH_RISK',
 'recommendation':{'title':'High-risk UTUC','options':[
   {'option_id':'utt_high_rnu','label':'Radical nephroureterectomy with bladder cuff','text':'With perioperative intravesical chemotherapy and consideration of neoadjuvant chemotherapy in selected patients.','decision_relevant':True,'applicability':{'fact':'nephron_sparing_required_or_preferred','op':'eq','value':False},'source_provenance':prov('Bladder Cancer','3.2026','UTT-2',[57])},
   {'option_id':'utt_high_imperative','label':'Systemic therapy + radiation therapy','text':'Source-defined imperative nephron-sparing management for high-risk disease.','decision_relevant':True,'applicability':{'fact':'nephron_sparing_required_or_preferred','op':'eq','value':True},'source_provenance':prov('Bladder Cancer','3.2026','UTT-2',[57])}
 ],'supporting_sections':['BL-G'],'next_steps':[]}}
})
# Ureter-specific location still changes surgical option per UTT-3. Add location-conditioned options to UTUC actions.
for aid in ['utt_high_intermediate','utt_high_risk']:
    act=d['nodes'][aid]
    opts=act['recommendation']['options']
    opts.append({'option_id':f'{aid}_distal_ureterectomy','label':'Distal ureterectomy + regional lymphadenectomy + ureteral reimplantation','text':'Preferred when clinically feasible for distal ureter high-grade disease; source-defined selected ureter pathway.','decision_relevant':True,
                 'applicability':{'all':[{'fact':'primary_site','op':'eq','value':'URETER'},{'fact':'upper_tract_location','op':'eq','value':'DISTAL_URETER'},{'fact':'upper_tract_grade','op':'eq','value':'HIGH'}]},
                 'source_provenance':prov('Bladder Cancer','3.2026','UTT-3',[58])})
save(p,d)

# Bone: site is already explicitly required upstream, so site-specific planning option is not conditionally hideable at these actions.
p,d=load('nexus_bone_cancer_v1_2027.json')
for nid in ['chor_adjrt','chor_surv','chor_defrt']:
    for o in d['nodes'][nid].get('recommendation',{}).get('options',[]):
        if o.get('option_id')=='chordoma_site_specific_planning': o.pop('applicability',None)
save(p,d)

# GIST: fourth-line is line-gated. Use ripretinib-exposure/progression rather than generic prior-TKI duplication.
p,d=load('nexus_gastrointestinal_stromal_tumors_v1_2026.json')
add_fact(d,{'key':'prior_ripretinib','value_type':'BOOLEAN','fact_role':'OPTION_APPLICABILITY'})
add_fact(d,{'key':'progressed_on_ripretinib','value_type':'BOOLEAN','fact_role':'OPTION_APPLICABILITY'})
opts=d['nodes']['adv_fourth']['recommendation']['options']
for o in opts:
    if o.get('option_id')=='gist_adv4_ripretinib':
        o['label']='Ripretinib 150 mg daily'
        o['text']='Preferred fourth-line therapy if not previously received.'
        o['preference_category']='PREFERRED';o['evidence_category']='CATEGORY_1'
        o['applicability']={'fact':'prior_ripretinib','op':'eq','value':False}
if not any(o.get('option_id')=='gist_adv4_ripretinib_escalation' for o in opts):
    opts.append({'option_id':'gist_adv4_ripretinib_escalation','label':'Ripretinib dose escalation to 150 mg twice daily','text':'Useful in certain circumstances after progression on ripretinib 150 mg daily.','decision_relevant':True,'preference_category':'USEFUL_IN_CERTAIN_CIRCUMSTANCES','applicability':{'all':[{'fact':'prior_ripretinib','op':'eq','value':True},{'fact':'progressed_on_ripretinib','op':'eq','value':True}]},'source_provenance':prov('Gastrointestinal Stromal Tumors','1.2026','GIST-E',[19])})
save(p,d)

print('FINAL_EXECUTABLE_REPAIRS_APPLIED')

# Basal Cell: separate primary-treatment state from postoperative margin state so NEW_DIAGNOSIS never asks for a future margin.
p,d=load('nexus_basal_cell_skin_cancer_v1_2027.json')
# Insert post-treatment phase before recurrence/local risk routing.
d['nodes']['care_recur']['on']['FALSE']='care_post_treatment'
d['nodes']['care_post_treatment']={
  'kind':'decision','label':'Post-treatment/post-excision margin assessment state?',
  'expression':{'fact':'treatment_phase','op':'eq','value':'POST_TREATMENT'},
  'on':{'TRUE':'post_risk_any','FALSE':'risk_any'},'source_pathways':['BCC-3','BCC-4','BCC-6'],'decision_id':'bcc_post_treatment_state'
}
# Primary local routing: low-risk goes directly to primary treatment, high-risk surgery feasible goes to primary surgery.
d['nodes']['risk_all_negative']['on']['TRUE']='low_primary'
d['nodes']['high_surgery']['on']['TRUE']='high_primary_surgery'
d['nodes']['high_primary_surgery']={
  'kind':'action','label':'High-risk BCC primary treatment when surgery is feasible: Mohs/PDEMA preferred; standard excision with wider margins is an alternative; multidisciplinary planning as appropriate.',
  'status':'RECOMMENDATION','recommendation_id':'high_primary_surgery','source_pathways':['BCC-4'],'pathway_id':'BCC_HIGH_RISK_PRIMARY_SURGERY',
  'recommendation':{'title':'High-risk BCC primary surgery','options':[
     {'option_id':'bcc_high_mohs_pdema','label':'Mohs or PDEMA','text':'Preferred for high-risk BCC.','decision_relevant':True,'preference_category':'PREFERRED','source_provenance':prov('Basal Cell Skin Cancer','1.2027','BCC-4',[9])},
     {'option_id':'bcc_high_standard_excision','label':'Standard excision with wider surgical margins','text':'With postoperative margin assessment and reconstruction only after clear margins as appropriate.','decision_relevant':True,'source_provenance':prov('Basal Cell Skin Cancer','1.2027','BCC-4',[9])}
  ],'supporting_sections':['BCC-B'],'next_steps':['POST_TREATMENT_MARGIN_ASSESSMENT']}
}
# Post-treatment risk classification uses the same source-defined high-risk factors, then margin.
d['nodes']['post_risk_any']={
  'kind':'decision','label':'Post-treatment lesion classified high risk by any BCC-2 factor?',
  'expression':d['nodes']['risk_any']['expression'],
  'on':{'TRUE':'high_surgery_margin','FALSE':'post_risk_all_negative'},'source_pathways':['BCC-2','BCC-4'],'decision_id':'bcc_post_high_risk_any'
}
d['nodes']['post_risk_all_negative']={
  'kind':'decision','label':'All BCC-2 high-risk factors confirmed absent for post-treatment lesion?',
  'expression':d['nodes']['risk_all_negative']['expression'],
  'on':{'TRUE':'low_local','FALSE':'need_risk'},'source_pathways':['BCC-2','BCC-3'],'decision_id':'bcc_post_all_high_risk_absent'
}
# Preserve existing low_local/high_surgery_margin as postoperative margin decisions only.
save(p,d)

# Bone/Chordoma + Chondrosarcoma: separate NEW_DIAGNOSIS primary local treatment from POST_PRIMARY margin/adjuvant state; execute chordoma site-specific primary surgery.
p,d=load('nexus_bone_cancer_v1_2027.json')
add_fact(d,{'key':'chordoma_large_extracompartmental','value_type':'BOOLEAN','fact_role':'ROUTING'})
# Chondrosarcoma care state
d['nodes']['chon_recur']['on']['FALSE']='chon_post_state'
d['nodes']['chon_post_state']={
 'kind':'decision','label':'Post-primary-treatment chondrosarcoma state?',
 'expression':{'fact':'treatment_phase','op':'eq','value':'POST_PRIMARY'},
 'on':{'TRUE':'chon_post_subtype','FALSE':'chon_subtype'},'source_pathways':['CHON-2','CHON-3'],'decision_id':'chon_post_primary_state'}
d['nodes']['chon_post_subtype']={
 'kind':'decision','label':'Post-primary conventional/clear-cell/high-grade chondrosarcoma requiring margin-directed follow-up?',
 'expression':{'fact':'chondrosarcoma_subtype','op':'in','value':['CONVENTIONAL','CLEAR_CELL']},
 'on':{'TRUE':'chon_surg_margin','FALSE':'chon_subtype'},'source_pathways':['CHON-2','CHON-3'],'decision_id':'chon_post_subtype'}
# New resectable disease should recommend surgery, not require a future margin.
d['nodes']['chon_conv_resect']['on']['TRUE']='chon_primary_surgery'
d['nodes']['chon_primary_surgery']={
 'kind':'action','label':'Resectable conventional/clear-cell/high-grade chondrosarcoma: wide excision with histologically negative margins.',
 'status':'RECOMMENDATION','recommendation_id':'chon_primary_surgery','source_pathways':['CHON-3'],'pathway_id':'CHONDROSARCOMA_PRIMARY_SURGERY',
 'recommendation':{'title':'Primary surgery for resectable chondrosarcoma','options':[{'option_id':'chon_wide_excision','label':'Wide excision','text':'Wide excision to achieve histologically negative margins.','decision_relevant':True,'source_provenance':prov('Bone Cancer','1.2027','CHON-3',[9])}], 'supporting_sections':['BONE-A'],'next_steps':['POST_PRIMARY_MARGIN_ASSESSMENT']}}

# Chordoma: distinguish recurrence, post-primary, and new primary states; site changes surgery type.
d['nodes']['chor_hist']['on']['FALSE']='chor_post_state'
d['nodes']['chor_post_state']={
 'kind':'decision','label':'Post-primary-treatment chordoma state?',
 'expression':{'fact':'treatment_phase','op':'eq','value':'POST_PRIMARY'},
 'on':{'TRUE':'chor_post_risk','FALSE':'chor_site_skull'},'source_pathways':['CHOR-2','CHOR-3'],'decision_id':'chor_post_primary_state'}
d['nodes']['chor_post_risk']={
 'kind':'decision','label':'Positive margin or large extracompartmental chordoma after resection?',
 'expression':{'any':[{'fact':'margin_status','op':'eq','value':'POSITIVE'},{'fact':'chordoma_large_extracompartmental','op':'eq','value':True}]},
 'on':{'TRUE':'chor_adjrt','FALSE':'chor_surv'},'source_pathways':['CHOR-2'],'decision_id':'chor_post_margin_or_large'}
d['nodes']['chor_site_skull']={
 'kind':'decision','label':'Skull-base/clival conventional chordoma?',
 'expression':{'fact':'chordoma_site','op':'eq','value':'SKULL_BASE_CLIVAL'},
 'on':{'TRUE':'chor_skull_resect','FALSE':'chor_site_axial'},'source_pathways':['CHOR-2'],'decision_id':'chor_site_skull'}
d['nodes']['chor_site_axial']={
 'kind':'decision','label':'Sacrococcygeal or mobile-spine conventional chordoma?',
 'expression':{'fact':'chordoma_site','op':'in','value':['SACROCOCCYGEAL','MOBILE_SPINE']},
 'on':{'TRUE':'chor_axial_resect','FALSE':'chor_site_missing'},'source_pathways':['CHOR-2'],'decision_id':'chor_site_sacral_mobile'}
d['nodes']['chor_site_missing']={'kind':'status','label':'Chordoma primary site is required for site-specific local treatment planning.','status':'NEEDS_INFORMATION','source_pathways':['CHOR-2']}
d['nodes']['chor_skull_resect']={
 'kind':'decision','label':'Skull-base/clival chordoma resectable?','expression':{'fact':'resectable','op':'eq','value':True},
 'on':{'TRUE':'chor_skull_primary','FALSE':'chor_defrt'},'source_pathways':['CHOR-2'],'decision_id':'chor_skull_resectable'}
d['nodes']['chor_axial_resect']={
 'kind':'decision','label':'Sacrococcygeal/mobile-spine chordoma resectable?','expression':{'fact':'resectable','op':'eq','value':True},
 'on':{'TRUE':'chor_axial_primary','FALSE':'chor_defrt'},'source_pathways':['CHOR-2'],'decision_id':'chor_axial_resectable'}
d['nodes']['chor_skull_primary']={
 'kind':'action','label':'Resectable skull-base/clival chordoma: maximal safe/intralesional excision ± adjuvant RT; postoperative contrast-enhanced MRI assesses adequacy of excision.',
 'status':'RECOMMENDATION','recommendation_id':'chor_skull_primary','source_pathways':['CHOR-2'],'pathway_id':'CHORDOMA_SKULL_BASE_PRIMARY',
 'recommendation':{'title':'Skull-base/clival chordoma primary treatment','options':[{'option_id':'chor_skull_intralesional','label':'Maximal safe/intralesional excision ± RT','text':'Primary local treatment for resectable skull-base/clival chordoma.','decision_relevant':True,'source_provenance':prov('Bone Cancer','1.2027','CHOR-2',[12])}], 'supporting_sections':['BONE-C'],'next_steps':['POST_PRIMARY_MRI_MARGIN_ASSESSMENT']}}
d['nodes']['chor_axial_primary']={
 'kind':'action','label':'Resectable sacrococcygeal/mobile-spine chordoma: wide excision ± adjuvant RT.',
 'status':'RECOMMENDATION','recommendation_id':'chor_axial_primary','source_pathways':['CHOR-2'],'pathway_id':'CHORDOMA_SACRAL_SPINE_PRIMARY',
 'recommendation':{'title':'Sacrococcygeal/mobile-spine chordoma primary treatment','options':[{'option_id':'chor_axial_wide_excision','label':'Wide excision ± adjuvant RT','text':'Primary local treatment for resectable sacrococcygeal/mobile-spine chordoma.','decision_relevant':True,'source_provenance':prov('Bone Cancer','1.2027','CHOR-2',[12])}], 'supporting_sections':['BONE-C'],'next_steps':['POST_PRIMARY_MARGIN_ASSESSMENT']}}
# Remove legacy new-diagnosis chordoma resect/margin nodes if no longer referenced; keep post margin node only if referenced.
d['nodes'].pop('chor_resect',None)
d['nodes'].pop('chor_surg_margin',None)
# Site-specific re-excision is specifically relevant to skull-base path; adjuvant RT applies across source-defined positive/large local risk.
for o in d['nodes']['chor_adjrt']['recommendation']['options']:
    if o.get('option_id')=='chor_reexcision': o['applicability']={'fact':'chordoma_site','op':'eq','value':'SKULL_BASE_CLIVAL'}
    if o.get('option_id')=='chordoma_site_specific_planning': o.pop('applicability',None)
save(p,d)

# AML family-specific WORKUP guards: a workup care state must never silently fall into induction.
p,d=load('nexus_acute_myeloid_leukemia_v5_2026.json')
d['nodes']['family_bpdcn']['on']['TRUE']='bpdcn_workup_state'
d['nodes']['bpdcn_workup_state']={
 'kind':'decision','label':'BPDCN diagnostic/workup phase?',
 'expression':{'fact':'treatment_phase','op':'eq','value':'WORKUP'},
 'on':{'TRUE':'bpdcn_workup_action','FALSE':'bpdcn_rr_state'},
 'source_pathways':['BPDCN-1'],'decision_id':'aml_bpdcn_workup_state'}
d['nodes']['bpdcn_workup_action']={
 'kind':'action','label':'BPDCN workup: complete source-defined diagnostic confirmation, extent/CNS assessment and eligibility evaluation before treatment selection.',
 'status':'RECOMMENDATION','recommendation_id':'bpdcn_workup_action','source_pathways':['BPDCN-1'],'pathway_id':'BPDCN_WORKUP',
 'recommendation':{'title':'BPDCN diagnostic/workup phase','options':[
   {'option_id':'bpdcn_complete_workup','label':'Complete BPDCN diagnostic/workup assessment','text':'Complete BPDCN-1 source-defined workup before treatment routing.','decision_relevant':True,'source_provenance':prov('Acute Myeloid Leukemia','5.2026','BPDCN-1',[48])}
 ],'supporting_sections':['BPDCN-A','BPDCN-B'],'next_steps':['BPDCN_TREATMENT_SELECTION']}}
d['nodes']['family_apl']['on']['TRUE']='apl_workup_state'
d['nodes']['apl_workup_state']={
 'kind':'decision','label':'APL diagnostic/workup phase?',
 'expression':{'fact':'treatment_phase','op':'eq','value':'WORKUP'},
 'on':{'TRUE':'apl_workup_action','FALSE':'apl_rr_state'},
 'source_pathways':['EVAL-2','APL-1'],'decision_id':'aml_apl_workup_state'}
d['nodes']['apl_workup_action']={
 'kind':'action','label':'Confirmed/suspected APL workup: complete source-defined diagnostic confirmation, baseline risk/supportive assessment and required pretreatment evaluation before definitive induction routing.',
 'status':'RECOMMENDATION','recommendation_id':'apl_workup_action','source_pathways':['EVAL-2','APL-1'],'pathway_id':'APL_WORKUP',
 'recommendation':{'title':'APL diagnostic/workup phase','options':[
   {'option_id':'apl_complete_workup','label':'Complete APL diagnostic/risk workup','text':'Complete APL-1/EVAL-2 source-defined assessment before risk-directed induction selection.','decision_relevant':True,'source_provenance':prov('Acute Myeloid Leukemia','5.2026','APL-1',[16])}
 ],'supporting_sections':['APL-A'],'next_steps':['APL_RISK_DIRECTED_INDUCTION']}}
d['nodes']['family_nonapl']['on']['TRUE']='aml_workup_state'
d['nodes']['aml_workup_state']={
 'kind':'decision','label':'Non-APL AML diagnostic/workup phase?',
 'expression':{'fact':'treatment_phase','op':'eq','value':'WORKUP'},
 'on':{'TRUE':'aml_workup_action','FALSE':'aml_care_rr'},
 'source_pathways':['EVAL-1','EVAL-2'],'decision_id':'aml_nonapl_workup_state'}
d['nodes']['aml_workup_action']={
 'kind':'action','label':'Non-APL AML workup: complete morphology/flow, cytogenetic and molecular risk studies, CNS/extramedullary evaluation when indicated, fitness assessment and early transplant planning before induction selection.',
 'status':'RECOMMENDATION','recommendation_id':'aml_workup_action','source_pathways':['EVAL-1','EVAL-2'],'pathway_id':'AML_WORKUP',
 'recommendation':{'title':'AML diagnostic/workup phase','options':[
   {'option_id':'aml_complete_workup','label':'Complete AML diagnostic/risk workup','text':'Complete EVAL-1/EVAL-2 source-defined evaluation before deterministic induction selection.','decision_relevant':True,'source_provenance':prov('Acute Myeloid Leukemia','5.2026','EVAL-1',[12])}
 ],'supporting_sections':['AML-A','AML-B'],'next_steps':['AML_RISK_AND_FITNESS_ROUTING']}}
save(p,d)
