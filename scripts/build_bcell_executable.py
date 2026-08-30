from __future__ import annotations
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from builder_lib import Graph,atom,any_,all_,not_,opt,fact,upsert_fact,set_roles,src_prov
ROOT=Path(__file__).resolve().parents[1]; ENC=ROOT/'backend/nexus/guidelines/encoded'
NAME='nexus_b_cell_lymphomas_v4_2026.json'

def load(): return json.loads((ENC/NAME).read_text())
def save(p): (ENC/NAME).write_text(json.dumps(p,indent=2))
def P(p,s): return src_prov(p,s)
def add(p,*fs):
    for f in fs: upsert_fact(p,f)
def O(p,s,oid,label,text=None,preference=None,evidence=None,app=None,qualifiers=None,decision_relevant=True):
    return opt(oid,label,text,preference,evidence,app,qualifiers,P(p,s),decision_relevant)

def build():
    p=load()
    # Cancer-agnostic/patient-state facts needed by the B-cell algorithms. All are source-directed.
    add(p,
      fact('limited_contiguous','BOOLEAN'), fact('bulky_disease','BOOLEAN'),
      fact('smipi_gt1','BOOLEAN'), fact('ipi_ge2','BOOLEAN'),
      fact('pediatric_type_follicular','BOOLEAN'), fact('histologic_transformation','BOOLEAN'),
      fact('treatment_line','CODED',['FIRST','SECOND','THIRD_OR_LATER','RELAPSE_2_PLUS','UNKNOWN'],semantic_unknown=['UNKNOWN']),
      fact('older_or_infirm','BOOLEAN'), fact('very_frail_or_over80','BOOLEAN'), fact('poor_lvef','BOOLEAN'),
      fact('concurrent_cns_disease','BOOLEAN'), fact('pet_5ps','NUMERIC'), fact('biopsy_positive','BOOLEAN'),
      fact('prior_bendamustine','BOOLEAN'), fact('prior_anti_cd20','BOOLEAN'), fact('cd20_positive','BOOLEAN'),
      fact('gcb_subtype','BOOLEAN'), fact('relapse_interval_months','NUMERIC'), fact('transplant_intent','BOOLEAN'),
      fact('localized_disease','BOOLEAN'), fact('rt_feasible','BOOLEAN'), fact('surgery_feasible','BOOLEAN'),
      fact('h_pylori_positive','BOOLEAN'), fact('malt1_t1118_positive','BOOLEAN'), fact('lymphoma_present','BOOLEAN'),
      fact('symptomatic','BOOLEAN'), fact('single_field_rt_feasible','BOOLEAN'),
      fact('recurrence_pattern','CODED',['LOCAL','SYSTEMIC','UNKNOWN'],semantic_unknown=['UNKNOWN']),
      fact('splenomegaly','BOOLEAN'), fact('progressive_cytopenia','BOOLEAN'), fact('hepatitis_c_positive','BOOLEAN'),
      fact('hepatitis_treatment_eligible','BOOLEAN'),
      fact('tp53_mutated','BOOLEAN'), fact('indolent_mcl','BOOLEAN'), fact('aggressive_induction_candidate','BOOLEAN'),
      fact('mcl_mrd_status','CODED',['UMRD6','DMRD6','UNKNOWN'],semantic_unknown=['UNKNOWN']),
      fact('prior_cbtki','BOOLEAN'), fact('cbtki_relapse_interval_months','NUMERIC'), fact('prior_hdt_ascr','BOOLEAN'),
      fact('very_good_pr','BOOLEAN'),
      fact('burkitt_ldh_normal','BOOLEAN'), fact('burkitt_mass_cm','NUMERIC'), fact('burkitt_abdominal_mass','BOOLEAN'),
      fact('abdominal_lesion_completely_resected','BOOLEAN'),
      fact('hgbcl_bcl2_rearranged','BOOLEAN'), fact('hgbcl_bcl6_rearranged','BOOLEAN'), fact('myc_rearranged','BOOLEAN'),
      fact('prior_indolent_lines','NUMERIC'),
      fact('hiv_lymphoma_histology','CODED',['BURKITT','DLBCL','HHV8_DLBCL','PRIMARY_EFFUSION','PLASMABLASTIC','PRIMARY_CNS','UNKNOWN'],semantic_unknown=['UNKNOWN']),
      fact('systemic_therapy_candidate','BOOLEAN'), fact('high_risk_plasmablastic','BOOLEAN'),
      fact('ptld_subtype','CODED',['NONDESTRUCTIVE','POLYMORPHIC_B','MONOMORPHIC_B','MONOMORPHIC_T','CHL_TYPE','PRIMARY_CNS','UNKNOWN'],semantic_unknown=['UNKNOWN']),
      fact('ebv_driven','BOOLEAN'), fact('initial_ptld_therapy','CODED',['REDUCE_IMMUNOSUPPRESSION','RITUXIMAB','CHEMOIMMUNOTHERAPY','NONE','UNKNOWN'],semantic_unknown=['UNKNOWN']),
      fact('ipi_0_2','BOOLEAN'),
      fact('lymphoblastic_lineage','CODED',['B','T','UNKNOWN'],semantic_unknown=['UNKNOWN']),
    )
    routing={
      'cancer_type','diagnosis_confirmed','lymphoma_subtype','treatment_phase','stage_group','response_status','indications_for_treatment',
      'limited_contiguous','bulky_disease','smipi_gt1','pediatric_type_follicular','histologic_transformation','treatment_line','pet_5ps','biopsy_positive',
      'relapse_interval_months','transplant_candidate','car_t_candidate','transplant_intent','localized_disease','rt_feasible','surgery_feasible',
      'h_pylori_positive','malt1_t1118_positive','lymphoma_present','symptomatic','single_field_rt_feasible','recurrence_pattern',
      'splenomegaly','progressive_cytopenia','hepatitis_c_positive','hepatitis_treatment_eligible','tp53_mutated','indolent_mcl',
      'aggressive_induction_candidate','mcl_mrd_status','prior_cbtki','cbtki_relapse_interval_months','very_good_pr','burkitt_ldh_normal',
      'burkitt_mass_cm','burkitt_abdominal_mass','abdominal_lesion_completely_resected','hgbcl_bcl2_rearranged','hgbcl_bcl6_rearranged',
      'myc_rearranged','prior_indolent_lines','hiv_lymphoma_histology','systemic_therapy_candidate','high_risk_plasmablastic',
      'ptld_subtype','ebv_driven','initial_ptld_therapy','ipi_0_2','lymphoblastic_lineage'
    }
    option={'older_or_infirm','very_frail_or_over80','poor_lvef','concurrent_cns_disease','prior_bendamustine','prior_anti_cd20','cd20_positive','gcb_subtype','ipi_ge2','prior_hdt_ascr'}
    roles={d['key']:('ROUTING' if d['key'] in routing else 'OPTION_APPLICABILITY' if d['key'] in option else 'NON_ROUTING_CONTEXT') for d in p['fact_definitions']}
    g=Graph(); S=lambda *x:list(x)
    # Global scope/diagnosis/subtype classification.
    g.decision('scope','B-cell lymphoma?',atom('cancer_type','eq','B_CELL_LYMPHOMA'),'diag','outside',S('DIAG-1'),decision_id='bcell_scope')
    g.decision('diag','B-cell lymphoma diagnosis confirmed?',atom('diagnosis_confirmed','eq',True),'sub_foll','workup',S('DIAG-1'),decision_id='bcell_diagnosis')
    g.action('workup','Complete B-cell lymphoma classification, immunophenotyping/molecular differential diagnosis and subtype-specific staging before therapeutic routing.',S('DIAG-1'),[
      O(p,'DIAG-1','bcell_workup_path','Pathology and immunophenotypic/molecular classification'),
      O(p,'DIAG-1','bcell_workup_stage','Subtype-appropriate staging/workup')],support=['NHODG-A','NHODG-B','ST-1','ST-2','ST-3','ST-4','ST-5'],pathway_id='BCELL_WORKUP')
    # subtype chain
    chain=[
      ('sub_foll','FOLLICULAR','foll_entry','sub_mzlg','FOLL-1'),('sub_mzlg','MZL_GASTRIC','mzlg_entry','sub_mzlng','EMZLG-1'),
      ('sub_mzlng','MZL_NONGASTRIC','mzlng_entry','sub_nmzl','EMZLNG-1'),('sub_nmzl','MZL_NODAL','nmzl_entry','sub_smzl','NMZL-1'),
      ('sub_smzl','MZL_SPLENIC','smzl_entry','sub_mcl','SMZL-1'),('sub_mcl','MANTLE_CELL','mcl_entry','sub_dlbcl','MANT-1'),
      ('sub_dlbcl','DLBCL','dlbcl_entry','sub_pmbl','BCEL-1'),('sub_pmbl','PMBL','pmbl_entry','sub_trans','PMBL-1'),
      ('sub_trans','TRANSFORMED_DLBCL','trans_entry','sub_hgbl','HTBCEL-1'),('sub_hgbl','HIGH_GRADE_B_CELL','hgbl_entry','sub_burk','HGBL-1'),
      ('sub_burk','BURKITT','burk_entry','sub_hiv','BURK-1'),('sub_hiv','HIV_RELATED_B_CELL','hiv_entry','sub_blast','HIVLYM-1'),
      ('sub_blast','LYMPHOBLASTIC_LYMPHOMA','blast_entry','sub_ptld','BLAST-1'),('sub_ptld','PTLD','ptld_entry','need_subtype','PTLD-1')]
    for nid,val,t,f,sec in chain:
        g.decision(nid,f'{val} subtype?',atom('lymphoma_subtype','eq',val),t,f,S('DIAG-1',sec),decision_id=f'bcell_subtype_{val.lower()}')
    g.status('need_subtype','Exact B-cell lymphoma subtype is required for deterministic routing.','NEEDS_INFORMATION',S('DIAG-1'))

    # ---------- FOLLICULAR LYMPHOMA ----------
    g.decision('foll_entry','Pediatric-type follicular lymphoma?',atom('pediatric_type_follicular','eq',True),'foll_pediatric','foll_care_rr',S('FOLL-1','FOLL-6'),decision_id='foll_pediatric_type')
    g.decision('foll_care_rr','Current relapsed/refractory/progressive episode?',any_(atom('treatment_phase','eq','RELAPSED_REFRACTORY'),atom('response_status','in',['RELAPSED','PROGRESSIVE'])),'foll_rr_line','foll_care_response',S('FOLL-5'),decision_id='foll_care_rr')
    g.decision('foll_care_response','Current response assessment?',atom('treatment_phase','eq','RESPONSE_ASSESSMENT'),'foll_response','foll_care_surv',S('FOLL-5'),decision_id='foll_care_response')
    g.decision('foll_care_surv','Surveillance episode?',atom('treatment_phase','eq','SURVEILLANCE'),'foll_surv','foll_stage_limited',S('FOLL-5'),decision_id='foll_care_surveillance')
    g.action('foll_surv','Classic follicular lymphoma surveillance after response/no treatment indication.',S('FOLL-5'),[O(p,'FOLL-5','foll_surveillance','Clinical follow-up and source-defined surveillance imaging')],support=['NHODG-C'],pathway_id='FOLL_SURVEILLANCE')
    g.decision('foll_stage_limited','Stage I/II?',atom('stage_group','eq','LIMITED'),'foll_limited_contig','foll_stage_advanced',S('FOLL-2','FOLL-3'),decision_id='foll_stage_limited')
    g.decision('foll_stage_advanced','Stage III/IV?',atom('stage_group','eq','ADVANCED'),'foll_adv_indication','foll_need_stage',S('FOLL-2','FOLL-4'),decision_id='foll_stage_advanced')
    g.status('foll_need_stage','Follicular lymphoma stage is required.','NEEDS_INFORMATION',S('FOLL-2'))
    g.decision('foll_limited_contig','Stage I or contiguous stage II?',atom('limited_contiguous','eq',True),'foll_limited_contig_action','foll_limited_noncontig',S('FOLL-3'),decision_id='foll_limited_contiguous')
    g.action('foll_limited_contig_action','Classic follicular lymphoma stage I/contiguous II initial therapy.',S('FOLL-3'),[
      O(p,'FOLL-3','foll_isrt','ISRT','Preferred.',preference='PREFERRED'),
      O(p,'FOLL-3','foll_isrt_anti_cd20','ISRT + anti-CD20 monoclonal antibody ± chemotherapy'),
      O(p,'FOLL-3','foll_anti_cd20_chemo','Anti-CD20 monoclonal antibody ± chemotherapy','Certain circumstances.'),
      O(p,'FOLL-3','foll_limited_observe','Active surveillance','Selected patients.')],support=['FOLL-B','NHODG-D'],pathway_id='FOLL_LIMITED_CONTIGUOUS')
    g.decision('foll_limited_noncontig','Treatment indication present?',atom('indications_for_treatment','eq',True),'foll_limited_noncontig_treat','foll_limited_observe',S('FOLL-3'),decision_id='foll_noncontiguous_indication')
    g.action('foll_limited_noncontig_treat','Non-contiguous stage II follicular lymphoma with treatment indication.',S('FOLL-3'),[
      O(p,'FOLL-3','foll_noncontig_anti_cd20','Anti-CD20 monoclonal antibody ± chemotherapy ± local palliation')],support=['FOLL-B','NHODG-D'],pathway_id='FOLL_LIMITED_NONCONTIG_TREAT')
    g.action('foll_limited_observe','Non-contiguous stage II follicular lymphoma without treatment indication: active surveillance.',S('FOLL-3'),[O(p,'FOLL-3','foll_active_surveillance','Active surveillance')],pathway_id='FOLL_LIMITED_NONCONTIG_OBSERVE')
    g.decision('foll_adv_indication','Advanced follicular lymphoma treatment indication present?',atom('indications_for_treatment','eq',True),'foll_first_opts','foll_adv_observe',S('FOLL-4'),decision_id='foll_advanced_treatment_indication')
    g.action('foll_adv_observe','Stage III/IV follicular lymphoma without treatment indication: active surveillance.',S('FOLL-4'),[O(p,'FOLL-4','foll_adv_active_surv','Active surveillance',evidence='CATEGORY_1')],pathway_id='FOLL_ADV_NO_INDICATION')
    foll_first=[
      O(p,'FOLL-B','foll_br','Bendamustine + obinutuzumab or rituximab','Preferred.',preference='PREFERRED'),
      O(p,'FOLL-B','foll_chop_anti_cd20','CHOP + obinutuzumab or rituximab','Preferred.',preference='PREFERRED'),
      O(p,'FOLL-B','foll_cvp_anti_cd20','CVP + obinutuzumab or rituximab','Preferred.',preference='PREFERRED'),
      O(p,'FOLL-B','foll_r2','Lenalidomide + rituximab','Preferred.',preference='PREFERRED'),
      O(p,'FOLL-B','foll_ritux_lowburden','Rituximab alone','Preferred for low tumor burden.',preference='PREFERRED',app=atom('bulky_disease','eq',False)),
      O(p,'FOLL-B','foll_len_obin','Lenalidomide + obinutuzumab','Other recommended; category 2B.',preference='OTHER_RECOMMENDED',evidence='CATEGORY_2B'),
      O(p,'FOLL-B','foll_infirm_ritux','Rituximab','Preferred for older/infirm.',preference='PREFERRED',app=atom('older_or_infirm','eq',True))]
    g.action('foll_first_opts','Stage III/IV follicular lymphoma with treatment indication: first-line systemic therapy.',S('FOLL-4'),foll_first,support=['FOLL-B','NHODG-D'],pathway_id='FOLL_ADV_TREAT')
    g.decision('foll_response','Histologic transformation confirmed?',atom('histologic_transformation','eq',True),'trans_entry','foll_response_cr',S('FOLL-5','HTBCEL-1'),decision_id='foll_response_transformation')
    g.decision('foll_response_cr','CR after therapy?',atom('response_status','eq','CR'),'foll_surv','foll_response_pr',S('FOLL-5'),decision_id='foll_response_cr')
    g.decision('foll_response_pr','PR after therapy?',atom('response_status','eq','PR'),'foll_surv','foll_response_prog',S('FOLL-5'),decision_id='foll_response_pr')
    g.decision('foll_response_prog','NR/progressive disease?',atom('response_status','in',['SD','PROGRESSIVE']),'foll_rr_line','foll_need_response',S('FOLL-5'),decision_id='foll_response_nr_progressive')
    g.status('foll_need_response','Current follicular lymphoma response state is required.','NEEDS_INFORMATION',S('FOLL-5'))
    g.decision('foll_rr_line','Third-line or later follicular lymphoma?',atom('treatment_line','in',['THIRD_OR_LATER','RELAPSE_2_PLUS']),'foll_third','foll_second',S('FOLL-5','FOLL-B'),decision_id='foll_rr_line')
    g.action('foll_second','Follicular lymphoma second-line therapy.',S('FOLL-5'),[
      O(p,'FOLL-B','foll_2_br','Bendamustine + anti-CD20','Preferred if bendamustine not previously used.',preference='PREFERRED',app=atom('prior_bendamustine','eq',False)),
      O(p,'FOLL-B','foll_2_chop','CHOP + anti-CD20','Preferred.',preference='PREFERRED'),
      O(p,'FOLL-B','foll_2_cvp','CVP + anti-CD20','Preferred.',preference='PREFERRED'),
      O(p,'FOLL-B','foll_2_r2_epi','Lenalidomide + rituximab + epcoritamab-bysp','Preferred; category 1.',preference='PREFERRED',evidence='CATEGORY_1'),
      O(p,'FOLL-B','foll_2_r2_tafa','Lenalidomide + rituximab + tafasitamab-cxix','Preferred after ≥1 prior systemic therapy including anti-CD20.',preference='PREFERRED',app=atom('prior_anti_cd20','eq',True)),
      O(p,'FOLL-B','foll_2_len','Lenalidomide ± anti-CD20','Other recommended.',preference='OTHER_RECOMMENDED')],support=['FOLL-B'],pathway_id='FOLL_SECOND_LINE')
    g.action('foll_third','Follicular lymphoma third-line and subsequent therapy.',S('FOLL-5'),[
      O(p,'FOLL-B','foll_3_epcor','Epcoritamab-bysp','Preferred T-cell mediated therapy.',preference='PREFERRED',app=atom('cd20_positive','eq',True)),
      O(p,'FOLL-B','foll_3_mosun','Mosunetuzumab-axgb (IV or SC)','Preferred T-cell mediated therapy.',preference='PREFERRED',app=atom('cd20_positive','eq',True)),
      O(p,'FOLL-B','foll_3_cart','CD19 CAR T-cell therapy','Preferred.',preference='PREFERRED',app=atom('car_t_candidate','eq',True)),
      O(p,'FOLL-B','foll_3_zanu_obin','Zanubrutinib + obinutuzumab','Other recommended.',preference='OTHER_RECOMMENDED'),
      O(p,'FOLL-B','foll_3_allohct','Allogeneic HCT','Highly selected candidates.',app=atom('transplant_candidate','eq',True))],support=['FOLL-B'],pathway_id='FOLL_THIRD_PLUS')
    g.decision('foll_pediatric','Localized stage I/II pediatric-type follicular lymphoma?',atom('stage_group','eq','LIMITED'),'foll_ped_action','foll_ped_out',S('FOLL-6'),decision_id='foll_pediatric_localized')
    g.action('foll_ped_action','Pediatric-type follicular lymphoma in adults, localized stage I/II.',S('FOLL-6'),[
      O(p,'FOLL-6','foll_ped_excision','Complete excision','Preferred when feasible.',preference='PREFERRED',app=atom('surgery_feasible','eq',True)),
      O(p,'FOLL-6','foll_ped_isrt','ISRT',app=atom('rt_feasible','eq',True)),
      O(p,'FOLL-6','foll_ped_rchop','RCHOP','For extensive local disease not appropriate for excision/RT.',app=all_(atom('surgery_feasible','eq',False),atom('rt_feasible','eq',False)))],pathway_id='FOLL_PEDIATRIC_TYPE')
    g.status('foll_ped_out','Pediatric-type follicular lymphoma outside the localized adult pathway requires specialist review.','REQUIRES_REVIEW',S('FOLL-6'))

    # ---------- GASTRIC MZL ----------
    g.decision('mzlg_entry','Current response assessment after H. pylori/local therapy?',atom('treatment_phase','eq','RESPONSE_ASSESSMENT'),'mzlg_resp_hp','mzlg_rr_check',S('EMZLG-4','EMZLG-5'),decision_id='mzlg_response_phase')
    g.decision('mzlg_rr_check','Relapsed/progressive gastric MZL?',any_(atom('treatment_phase','eq','RELAPSED_REFRACTORY'),atom('response_status','in',['RELAPSED','PROGRESSIVE'])),'mzlg_recur_pattern','mzlg_stage_limited',S('EMZLG-6'),decision_id='mzlg_relapse')
    g.decision('mzlg_stage_limited','Localized gastric MZL?',atom('stage_group','eq','LIMITED'),'mzlg_hp','mzlg_stage_adv',S('EMZLG-2','EMZLG-3'),decision_id='mzlg_stage')
    g.decision('mzlg_stage_adv','Advanced gastric MZL?',atom('stage_group','eq','ADVANCED'),'mzlg_adv_ind','mzlg_need_stage',S('EMZLG-3'),decision_id='mzlg_advanced_confirm')
    g.status('mzlg_need_stage','Gastric MZL stage is required.','NEEDS_INFORMATION',S('EMZLG-1'))
    g.decision('mzlg_hp','H. pylori positive?',atom('h_pylori_positive','eq',True),'mzlg_t1118','mzlg_hpneg',S('EMZLG-2'),decision_id='mzlg_h_pylori')
    g.decision('mzlg_t1118','t(11;18) positive?',atom('malt1_t1118_positive','eq',True),'mzlg_hp_tpos','mzlg_abx',S('EMZLG-2'),decision_id='mzlg_t1118')
    g.action('mzlg_abx','Localized H. pylori-positive gastric MZL without known t(11;18) resistance pattern: H. pylori eradication therapy.',S('EMZLG-2'),[O(p,'EMZLG-2','mzlg_antibiotics','H. pylori eradication therapy')],pathway_id='MZLG_HP_POS_T1118_NEG')
    g.action('mzlg_hp_tpos','Localized H. pylori-positive, t(11;18)-positive gastric MZL.',S('EMZLG-2'),[
      O(p,'EMZLG-2','mzlg_tpos_abx','H. pylori eradication therapy'), O(p,'EMZLG-2','mzlg_tpos_isrt','ISRT','Preferred local therapy.',preference='PREFERRED',app=atom('rt_feasible','eq',True)),
      O(p,'EMZLG-2','mzlg_tpos_ritux','Rituximab','If ISRT contraindicated/unavailable.',app=atom('rt_feasible','eq',False))],pathway_id='MZLG_HP_POS_T1118_POS')
    g.action('mzlg_hpneg','Localized H. pylori-negative gastric MZL.',S('EMZLG-2'),[
      O(p,'EMZLG-2','mzlg_hpneg_isrt','ISRT','Preferred.',preference='PREFERRED',app=atom('rt_feasible','eq',True)),
      O(p,'EMZLG-2','mzlg_hpneg_ritux','Rituximab','If ISRT contraindicated/unavailable.',app=atom('rt_feasible','eq',False))],pathway_id='MZLG_HP_NEG')
    g.decision('mzlg_adv_ind','Advanced gastric MZL treatment indication?',atom('indications_for_treatment','eq',True),'mzl_first_systemic','mzlg_adv_surv',S('EMZLG-3'),decision_id='mzlg_advanced_indication')
    g.action('mzlg_adv_surv','Advanced gastric MZL without treatment indication: active surveillance.',S('EMZLG-3'),[O(p,'EMZLG-3','mzlg_adv_watch','Active surveillance')],pathway_id='MZLG_ADV_SURVEILLANCE')
    g.decision('mzlg_resp_hp','H. pylori remains positive?',atom('h_pylori_positive','eq',True),'mzlg_resp_lymph_poshp','mzlg_resp_lymph_neghp',S('EMZLG-4','EMZLG-5'),decision_id='mzlg_response_hp')
    g.decision('mzlg_resp_lymph_poshp','Lymphoma persists?',atom('lymphoma_present','eq',True),'mzlg_resp_both_pos','mzlg_hp_only',S('EMZLG-4','EMZLG-5'),decision_id='mzlg_response_lymphoma_poshp')
    g.decision('mzlg_resp_lymph_neghp','Lymphoma persists?',atom('lymphoma_present','eq',True),'mzlg_lymph_only','mzlg_both_neg',S('EMZLG-4','EMZLG-5'),decision_id='mzlg_response_lymphoma_neghp')
    g.action('mzlg_both_neg','H. pylori eradicated and gastric lymphoma cleared: observation/follow-up.',S('EMZLG-4','EMZLG-5'),[O(p,'EMZLG-4','mzlg_observe','Observe and repeat source-defined endoscopic assessment')],pathway_id='MZLG_RESPONSE_CLEAR')
    g.decision('mzlg_resp_both_pos','Symptomatic/progressive persistent lymphoma?',atom('symptomatic','eq',True),'mzlg_both_pos_treat','mzlg_both_pos_abx',S('EMZLG-4'),decision_id='mzlg_persistent_symptoms')
    g.action('mzlg_both_pos_abx','Persistent H. pylori and lymphoma without symptomatic/progressive disease: second-line H. pylori therapy and reassessment.',S('EMZLG-4'),[O(p,'EMZLG-4','mzlg_second_abx','Second-line H. pylori eradication therapy')],pathway_id='MZLG_PERSIST_BOTH_STABLE')
    g.action('mzlg_both_pos_treat','Persistent H. pylori and symptomatic/progressive gastric lymphoma.',S('EMZLG-4'),[O(p,'EMZLG-4','mzlg_second_abx2','Second-line H. pylori therapy'),O(p,'EMZLG-4','mzlg_persist_isrt','ISRT',app=atom('rt_feasible','eq',True))],pathway_id='MZLG_PERSIST_BOTH_TREAT')
    g.action('mzlg_hp_only','H. pylori persists but lymphoma cleared: second-line eradication therapy.',S('EMZLG-4'),[O(p,'EMZLG-4','mzlg_hp_only_abx','Second-line H. pylori eradication therapy')],pathway_id='MZLG_HP_PERSIST_LYMPH_CLEAR')
    g.decision('mzlg_lymph_only','Symptomatic/progressive residual lymphoma?',atom('symptomatic','eq',True),'mzlg_lymph_only_isrt','mzlg_lymph_only_watch',S('EMZLG-4','EMZLG-5'),decision_id='mzlg_residual_lymphoma_symptoms')
    g.action('mzlg_lymph_only_watch','H. pylori eradicated with stable/asymptomatic residual lymphoma: repeat endoscopy/biopsy or local management.',S('EMZLG-4','EMZLG-5'),[O(p,'EMZLG-4','mzlg_repeat_scope','Repeat endoscopy/biopsy and observation'),O(p,'EMZLG-4','mzlg_stable_isrt','ISRT',app=atom('rt_feasible','eq',True),decision_relevant=False)],pathway_id='MZLG_RESIDUAL_STABLE')
    g.action('mzlg_lymph_only_isrt','H. pylori eradicated with symptomatic/progressive residual gastric lymphoma: ISRT when feasible.',S('EMZLG-4','EMZLG-5'),[O(p,'EMZLG-4','mzlg_resid_isrt','ISRT',app=atom('rt_feasible','eq',True))],pathway_id='MZLG_RESIDUAL_PROGRESSIVE')
    g.decision('mzlg_recur_pattern','Local gastric MZL recurrence?',atom('recurrence_pattern','eq','LOCAL'),'mzlg_local_recur','mzlg_systemic_recur',S('EMZLG-6'),decision_id='mzlg_recurrence_pattern')
    g.action('mzlg_local_recur','Local gastric MZL recurrence.',S('EMZLG-6'),[O(p,'EMZLG-6','mzlg_rec_isrt','ISRT if not previously irradiated',app=atom('rt_feasible','eq',True)),O(p,'EMZLG-6','mzlg_rec_systemic','Advanced MZL systemic pathway if prior local therapy/precluded RT')],support=['MZL-A'],pathway_id='MZLG_LOCAL_RECURRENCE')
    g.action('mzlg_systemic_recur','Systemic gastric MZL recurrence: advanced MZL therapy.',S('EMZLG-6'),[O(p,'MZL-A','mzlg_rec_mzl_systemic','Marginal zone lymphoma subsequent-line systemic therapy')],support=['MZL-A'],pathway_id='MZLG_SYSTEMIC_RECURRENCE')

    # shared MZL option actions
    g.action('mzl_first_systemic','Advanced marginal zone lymphoma with treatment indication: subtype-appropriate first-line systemic therapy.',S('NMZL-3','EMZLG-3','EMZLNG-2','SMZL-2'),[
      O(p,'MZL-A','mzl_br','Bendamustine + rituximab','Preferred for NMZL.',preference='PREFERRED'),
      O(p,'MZL-A','mzl_rchop','RCHOP','Preferred for NMZL.',preference='PREFERRED'), O(p,'MZL-A','mzl_rcvp','RCVP','Preferred for NMZL.',preference='PREFERRED'),
      O(p,'MZL-A','mzl_ritux','Rituximab','Preferred for low-burden NMZL/SMZL.',preference='PREFERRED'),
      O(p,'MZL-A','mzl_r2','Lenalidomide + rituximab','Other recommended.',preference='OTHER_RECOMMENDED')],support=['MZL-A'],pathway_id='MZL_FIRST_LINE')
    g.decision('mzl_rr_line','Third-line or later MZL?',atom('treatment_line','in',['THIRD_OR_LATER','RELAPSE_2_PLUS']),'mzl_third','mzl_second',S('MZL-A'),decision_id='mzl_rr_line')
    g.action('mzl_second','Marginal zone lymphoma second-line therapy.',S('MZL-1'),[
      O(p,'MZL-A','mzl_2_br','Bendamustine + rituximab','Preferred if appropriate.',preference='PREFERRED'), O(p,'MZL-A','mzl_2_zanu','Zanubrutinib','Preferred after ≥1 prior anti-CD20 therapy.',preference='PREFERRED',app=atom('prior_anti_cd20','eq',True)),
      O(p,'MZL-A','mzl_2_rchop','RCHOP','Preferred.',preference='PREFERRED'),O(p,'MZL-A','mzl_2_rcvp','RCVP','Preferred.',preference='PREFERRED'),
      O(p,'MZL-A','mzl_2_r2','Lenalidomide + rituximab','Preferred.',preference='PREFERRED')],support=['MZL-A'],pathway_id='MZL_SECOND_LINE')
    g.action('mzl_third','Marginal zone lymphoma third-line/subsequent therapy.',S('MZL-1'),[
      O(p,'MZL-A','mzl_3_cart','CAR T-cell therapy',app=atom('car_t_candidate','eq',True)),O(p,'MZL-A','mzl_3_unused','Previously unused second-line regimen'),
      O(p,'MZL-A','mzl_3_allohct','Allogeneic HCT','Highly selected candidates.',app=atom('transplant_candidate','eq',True))],support=['MZL-A'],pathway_id='MZL_THIRD_PLUS')

    # Nongastric extranodal MZL
    g.decision('mzlng_entry','Relapsed/progressive nongastric extranodal MZL?',any_(atom('treatment_phase','eq','RELAPSED_REFRACTORY'),atom('response_status','in',['RELAPSED','PROGRESSIVE'])),'mzl_rr_line','mzlng_stage',S('EMZLNG-3'),decision_id='mzlng_rr')
    g.decision('mzlng_stage','Localized stage IE/contiguous IIE?',atom('stage_group','eq','LIMITED'),'mzlng_local','mzlng_advanced',S('EMZLNG-2'),decision_id='mzlng_stage')
    g.action('mzlng_local','Localized nongastric extranodal MZL.',S('EMZLNG-2'),[
      O(p,'EMZLNG-2','mzlng_isrt','ISRT','Preferred.',preference='PREFERRED',app=atom('rt_feasible','eq',True)),O(p,'EMZLNG-2','mzlng_surgery','Surgery for selected sites',app=atom('surgery_feasible','eq',True)),
      O(p,'EMZLNG-2','mzlng_ritux','Rituximab in selected cases'),O(p,'EMZLNG-2','mzlng_watch','Active surveillance in selected cases')],support=['NHODG-D'],pathway_id='MZLNG_LOCAL')
    g.decision('mzlng_advanced','Advanced/multifocal nongastric extranodal MZL treatment indication?',atom('indications_for_treatment','eq',True),'mzl_first_systemic','mzlng_watch_adv',S('EMZLNG-2','EMZLNG-3'),decision_id='mzlng_advanced_indication')
    g.action('mzlng_watch_adv','Advanced/multifocal nongastric extranodal MZL without treatment indication: active surveillance.',S('EMZLNG-2','EMZLNG-3'),[O(p,'EMZLNG-2','mzlng_adv_watch','Active surveillance')],pathway_id='MZLNG_ADV_WATCH')

    # Nodal MZL
    g.decision('nmzl_entry','Relapsed/progressive nodal MZL?',any_(atom('treatment_phase','eq','RELAPSED_REFRACTORY'),atom('response_status','in',['RELAPSED','PROGRESSIVE'])),'nmzl_trans_check','nmzl_response_phase',S('NMZL-4'),decision_id='nmzl_rr')
    g.decision('nmzl_trans_check','Histologic transformation confirmed?',atom('histologic_transformation','eq',True),'trans_entry','mzl_rr_line',S('NMZL-4','HTBCEL-1'),decision_id='nmzl_transformation_rr')
    g.decision('nmzl_response_phase','Response assessment?',atom('treatment_phase','eq','RESPONSE_ASSESSMENT'),'nmzl_response','nmzl_stage',S('NMZL-2','NMZL-4'),decision_id='nmzl_response_phase')
    g.decision('nmzl_stage','Stage I/II?',atom('stage_group','eq','LIMITED'),'nmzl_limited_contig','nmzl_adv_confirm',S('NMZL-2','NMZL-3'),decision_id='nmzl_stage')
    g.decision('nmzl_limited_contig','Stage I or contiguous stage II?',atom('limited_contiguous','eq',True),'nmzl_local_contig','nmzl_noncontig_ind',S('NMZL-2'),decision_id='nmzl_limited_contiguous')
    g.action('nmzl_local_contig','Nodal MZL stage I/contiguous II.',S('NMZL-2'),[
      O(p,'NMZL-2','nmzl_isrt','ISRT','Preferred.',preference='PREFERRED',app=atom('rt_feasible','eq',True)),O(p,'NMZL-2','nmzl_isrt_sys','ISRT + anti-CD20 ± chemotherapy'),O(p,'NMZL-2','nmzl_sys','Anti-CD20 ± chemotherapy','Certain circumstances.')],support=['MZL-A','NHODG-D'],pathway_id='NMZL_LOCAL_CONTIG')
    g.decision('nmzl_noncontig_ind','Treatment indication present?',atom('indications_for_treatment','eq',True),'mzl_first_systemic','nmzl_noncontig_watch',S('NMZL-2'),decision_id='nmzl_noncontiguous_indication')
    g.action('nmzl_noncontig_watch','Non-contiguous stage II nodal MZL without treatment indication: active surveillance.',S('NMZL-2'),[O(p,'NMZL-2','nmzl_noncontig_watchopt','Active surveillance')],pathway_id='NMZL_NONCONTIG_WATCH')
    g.decision('nmzl_adv_confirm','Stage III/IV?',atom('stage_group','eq','ADVANCED'),'nmzl_adv_ind','nmzl_need_stage',S('NMZL-3'),decision_id='nmzl_stage_advanced')
    g.status('nmzl_need_stage','Nodal MZL stage is required.','NEEDS_INFORMATION',S('NMZL-1'))
    g.decision('nmzl_adv_ind','Treatment indication present?',atom('indications_for_treatment','eq',True),'mzl_first_systemic','nmzl_adv_watch',S('NMZL-3'),decision_id='nmzl_advanced_indication')
    g.action('nmzl_adv_watch','Stage III/IV nodal MZL without treatment indication: active surveillance.',S('NMZL-3'),[O(p,'NMZL-3','nmzl_adv_watchopt','Active surveillance',evidence='CATEGORY_1')],pathway_id='NMZL_ADV_WATCH')
    g.decision('nmzl_response','Histologic transformation?',atom('histologic_transformation','eq',True),'trans_entry','nmzl_resp_cr',S('NMZL-2','NMZL-4'),decision_id='nmzl_response_transformation')
    g.decision('nmzl_resp_cr','CR or PR?',atom('response_status','in',['CR','PR']),'nmzl_surv','nmzl_resp_nr',S('NMZL-2','NMZL-4'),decision_id='nmzl_response_crpr')
    g.decision('nmzl_resp_nr','NR/progressive?',atom('response_status','in',['SD','PROGRESSIVE']),'mzl_rr_line','nmzl_need_resp',S('NMZL-4'),decision_id='nmzl_response_nr')
    g.status('nmzl_need_resp','Nodal MZL response is required.','NEEDS_INFORMATION',S('NMZL-4'))
    g.action('nmzl_surv','Nodal MZL CR/PR: clinical follow-up and source-defined surveillance imaging.',S('NMZL-2','NMZL-4'),[O(p,'NMZL-4','nmzl_surveillance','Surveillance')],pathway_id='NMZL_SURVEILLANCE')

    # Splenic MZL
    g.decision('smzl_entry','Relapsed/progressive splenic MZL?',any_(atom('treatment_phase','eq','RELAPSED_REFRACTORY'),atom('response_status','in',['RELAPSED','PROGRESSIVE'])),'smzl_rr_ind','smzl_asym_no_spleen',S('SMZL-3'),decision_id='smzl_rr')
    g.decision('smzl_asym_no_spleen','Asymptomatic without progressive cytopenia and no splenomegaly?',all_(atom('symptomatic','eq',False),atom('progressive_cytopenia','eq',False),atom('splenomegaly','eq',False)),'smzl_follow','smzl_spleen',S('SMZL-2'),decision_id='smzl_asymptomatic')
    g.decision('smzl_spleen','Splenomegaly present?',atom('splenomegaly','eq',True),'smzl_hcv','smzl_need_state',S('SMZL-2'),decision_id='smzl_splenomegaly')
    g.status('smzl_need_state','Splenic MZL symptom/cytopenia/splenomegaly state is required.','NEEDS_INFORMATION',S('SMZL-2'))
    g.decision('smzl_hcv','Hepatitis C positive?',atom('hepatitis_c_positive','eq',True),'smzl_hcv_eligible','smzl_symptom',S('SMZL-2'),decision_id='smzl_hepatitis_c')
    g.decision('smzl_hcv_eligible','Eligible for hepatitis C treatment?',atom('hepatitis_treatment_eligible','eq',True),'smzl_hcv_treat','smzl_symptom',S('SMZL-2'),decision_id='smzl_hcv_treatment_eligible')
    g.action('smzl_hcv_treat','Splenic MZL with hepatitis C and no contraindication: treat hepatitis C with hepatology involvement, then assess lymphoma response.',S('SMZL-2'),[O(p,'SMZL-2','smzl_hcv_therapy','Appropriate hepatitis C therapy')],pathway_id='SMZL_HCV')
    g.decision('smzl_symptom','Symptoms/clinically significant disease present?',atom('symptomatic','eq',True),'smzl_treat','smzl_follow',S('SMZL-2'),decision_id='smzl_symptoms')
    g.action('smzl_treat','Symptomatic splenic MZL requiring treatment.',S('SMZL-2'),[O(p,'SMZL-2','smzl_ritux','Rituximab','Preferred.',preference='PREFERRED'),O(p,'SMZL-2','smzl_splenectomy','Splenectomy','Category 2B.',evidence='CATEGORY_2B',app=atom('surgery_feasible','eq',True))],support=['MZL-A'],pathway_id='SMZL_TREAT')
    g.action('smzl_follow','Splenic MZL not requiring immediate therapy: follow-up/active surveillance.',S('SMZL-2','SMZL-3'),[O(p,'SMZL-3','smzl_followopt','Active surveillance/follow-up')],pathway_id='SMZL_FOLLOW')
    g.decision('smzl_rr_ind','Treatment indication at recurrence?',atom('indications_for_treatment','eq',True),'mzl_rr_line','smzl_follow',S('SMZL-3'),decision_id='smzl_recurrence_indication')

    # ---------- MANTLE CELL LYMPHOMA ----------
    g.decision('mcl_entry','Relapsed/refractory/progressive MCL?',any_(atom('treatment_phase','eq','RELAPSED_REFRACTORY'),atom('response_status','in',['RELAPSED','PROGRESSIVE'])),'mcl_rr_prior_cbtki','mcl_response_phase',S('MANT-6A','MANT-6B'),decision_id='mcl_rr')
    g.decision('mcl_response_phase','Response assessment?',atom('treatment_phase','eq','RESPONSE_ASSESSMENT'),'mcl_response','mcl_stage_limited',S('MANT-2','MANT-4','MANT-5'),decision_id='mcl_response_phase')
    g.decision('mcl_stage_limited','Stage I/II?',atom('stage_group','eq','LIMITED'),'mcl_limited_contig','mcl_advanced',S('MANT-1','MANT-2','MANT-3'),decision_id='mcl_stage')
    g.decision('mcl_limited_contig','Stage I/II nonbulky contiguous?',all_(atom('limited_contiguous','eq',True),atom('bulky_disease','eq',False)),'mcl_limited_action','mcl_limited_noncontig',S('MANT-2'),decision_id='mcl_limited_contiguous')
    g.action('mcl_limited_action','Localized MCL stage I/contiguous nonbulky II.',S('MANT-2'),[O(p,'MANT-2','mcl_isrt','ISRT',app=atom('rt_feasible','eq',True)),O(p,'MANT-2','mcl_less_aggressive','Less aggressive induction ± ISRT')],support=['MANT-A','NHODG-D'],pathway_id='MCL_LOCAL_CONTIG')
    g.decision('mcl_limited_noncontig','Symptomatic or other treatment indication?',atom('indications_for_treatment','eq',True),'mcl_less_aggressive_action','mcl_local_watch',S('MANT-2'),decision_id='mcl_noncontiguous_indication')
    g.action('mcl_less_aggressive_action','Noncontiguous stage II MCL requiring treatment: less aggressive induction.',S('MANT-2'),[O(p,'MANT-A','mcl_less_aggressive_regimens','Less aggressive induction regimen')],support=['MANT-A'],pathway_id='MCL_LOCAL_NONCONTIG_TREAT')
    g.action('mcl_local_watch','Highly selected noncontiguous stage II MCL without treatment indication: active surveillance.',S('MANT-2'),[O(p,'MANT-2','mcl_watch','Active surveillance')],pathway_id='MCL_LOCAL_WATCH')
    g.decision('mcl_advanced','Asymptomatic indolent MCL without treatment indication?',all_(atom('indolent_mcl','eq',True),atom('indications_for_treatment','eq',False)),'mcl_adv_watch','mcl_tp53',S('MANT-3'),decision_id='mcl_indolent')
    g.action('mcl_adv_watch','Asymptomatic indolent MCL: active surveillance.',S('MANT-3'),[O(p,'MANT-3','mcl_adv_watchopt','Active surveillance')],pathway_id='MCL_INDOLENT_WATCH')
    g.decision('mcl_tp53','TP53 mutated?',atom('tp53_mutated','eq',True),'mcl_tp53_action','mcl_aggressive_fit',S('MANT-3'),decision_id='mcl_tp53')
    g.action('mcl_tp53_action','Advanced MCL with TP53 mutation: clinical trial strongly recommended; otherwise subtype-appropriate induction.',S('MANT-3'),[O(p,'MANT-3','mcl_tp53_trial','Clinical trial','Strongly recommended.',preference='PREFERRED'),O(p,'MANT-A','mcl_tp53_induction','MCL induction regimen if trial unavailable')],support=['MANT-A'],pathway_id='MCL_TP53_MUTATED')
    g.decision('mcl_aggressive_fit','Suitable for aggressive induction?',atom('aggressive_induction_candidate','eq',True),'mcl_aggressive','mcl_less_aggressive_adv',S('MANT-4','MANT-5'),decision_id='mcl_aggressive_candidate')
    g.action('mcl_aggressive','Advanced TP53-wild-type MCL suitable for aggressive induction.',S('MANT-4'),[O(p,'MANT-4','mcl_aggr_trial','Clinical trial'),O(p,'MANT-A','mcl_aggr_regimen','Aggressive induction regimen')],support=['MANT-A'],pathway_id='MCL_AGGRESSIVE_INDUCTION')
    g.action('mcl_less_aggressive_adv','Advanced MCL not suitable for aggressive induction: less aggressive induction.',S('MANT-5'),[O(p,'MANT-A','mcl_less_regimen_adv','Less aggressive induction regimen')],support=['MANT-A'],pathway_id='MCL_LESS_AGGRESSIVE')
    g.decision('mcl_response','Complete response?',atom('response_status','eq','CR'),'mcl_cr_mrd','mcl_resp_pr',S('MANT-4','MANT-5'),decision_id='mcl_response_cr')
    g.decision('mcl_cr_mrd','MRD status after aggressive induction available?',atom('mcl_mrd_status','eq','UMRD6'),'mcl_umrd','mcl_mrd_detect',S('MANT-4'),decision_id='mcl_mrd_umrd')
    g.decision('mcl_mrd_detect','Detectable MRD at 10^-6?',atom('mcl_mrd_status','eq','DMRD6'),'mcl_dmrd','mcl_cr_maintenance',S('MANT-4'),decision_id='mcl_mrd_dmrd')
    g.action('mcl_umrd','MCL CR with uMRD6 after aggressive induction: do not proceed to HDT/ASCR solely for consolidation; maintenance per source.',S('MANT-4'),[O(p,'MANT-4','mcl_umrd_maintenance','Maintenance therapy')],pathway_id='MCL_CR_UMRD')
    g.action('mcl_dmrd','MCL CR with dMRD6 after aggressive induction: consider HDT/ASCR plus maintenance.',S('MANT-4'),[O(p,'MANT-4','mcl_dmrd_ascr','Consider HDT/ASCR',app=atom('transplant_candidate','eq',True)),O(p,'MANT-4','mcl_dmrd_maintenance','Maintenance therapy')],pathway_id='MCL_CR_DMRD')
    g.action('mcl_cr_maintenance','MCL CR when MRD-guided transplant decision is not applicable/known: maintenance according to induction pathway.',S('MANT-4','MANT-5'),[O(p,'MANT-A','mcl_ritux_maintenance','Rituximab maintenance')],support=['MANT-A'],pathway_id='MCL_CR_MAINTENANCE')
    g.decision('mcl_resp_pr','Partial response?',atom('response_status','eq','PR'),'mcl_pr_vgood','mcl_resp_prog',S('MANT-4','MANT-5'),decision_id='mcl_response_pr')
    g.decision('mcl_pr_vgood','Very good PR?',atom('very_good_pr','eq',True),'mcl_pr_watch','mcl_rr_prior_cbtki',S('MANT-6A','MANT-6B'),decision_id='mcl_vgood_pr')
    g.action('mcl_pr_watch','Very good PR in MCL: active surveillance may be considered; otherwise continue/consolidate according to source.',S('MANT-6A','MANT-6B'),[O(p,'MANT-6A','mcl_vgood_watch','Active surveillance')],pathway_id='MCL_VGOOD_PR')
    g.decision('mcl_resp_prog','No response/progressive?',atom('response_status','in',['SD','PROGRESSIVE']),'mcl_rr_prior_cbtki','mcl_need_resp',S('MANT-4','MANT-5'),decision_id='mcl_response_progressive')
    g.status('mcl_need_resp','MCL response status is required.','NEEDS_INFORMATION',S('MANT-4','MANT-5'))
    g.decision('mcl_rr_prior_cbtki','Previously exposed to a covalent BTKi?',atom('prior_cbtki','eq',True),'mcl_rr_interval','mcl_rr_late',S('MANT-6A','MANT-6B'),decision_id='mcl_prior_cbtki')
    g.decision('mcl_rr_interval','Relapse <24 months after prior covalent BTKi or progression on it?',atom('cbtki_relapse_interval_months','lt',24),'mcl_rr_early','mcl_rr_late',S('MANT-6A','MANT-6B'),decision_id='mcl_cbtki_interval')
    g.action('mcl_rr_late','MCL cBTKi-naïve or late relapse >24 months after cBTKi-containing regimen.',S('MANT-6A'),[
      O(p,'MANT-A','mcl_rr_cbtki','Covalent BTKi-containing therapy','Preferred if cBTKi-naïve.',preference='PREFERRED',app=atom('prior_cbtki','eq',False)),
      O(p,'MANT-A','mcl_rr_continuous','Other continuous-treatment regimen'),O(p,'MANT-A','mcl_rr_fixed','Fixed-duration regimen'),O(p,'MANT-6A','mcl_rr_isrt','ISRT',app=atom('rt_feasible','eq',True)),
      O(p,'MANT-A','mcl_rr_cart','CAR T-cell therapy for refractory/subsequent state',app=atom('car_t_candidate','eq',True)),O(p,'MANT-A','mcl_rr_noncbtki','Non-covalent BTKi')],support=['MANT-A'],pathway_id='MCL_RR_CBTKI_NAIVE_LATE')
    g.action('mcl_rr_early','MCL progression on cBTKi or early relapse <24 months.',S('MANT-6B'),[
      O(p,'MANT-A','mcl_early_noncbtki','Non-covalent BTKi'),O(p,'MANT-A','mcl_early_cart','CAR T-cell therapy',app=atom('car_t_candidate','eq',True)),
      O(p,'MANT-A','mcl_early_bispecific','Bispecific antibody therapy'),O(p,'MANT-A','mcl_early_other','Alternative systemic therapy not previously given'),O(p,'MANT-6B','mcl_early_isrt','ISRT',app=atom('rt_feasible','eq',True))],support=['MANT-A'],pathway_id='MCL_RR_EARLY')

    # ---------- DLBCL ----------
    g.decision('dlbcl_entry','Current primary refractory/relapsed DLBCL?',any_(atom('treatment_phase','eq','RELAPSED_REFRACTORY'),atom('response_status','eq','RELAPSED')),'dlbcl_rr_line_check','dlbcl_response_phase',S('BCEL-7','BCEL-8','BCEL-9'),decision_id='dlbcl_rr')
    g.decision('dlbcl_rr_line_check','Relapse #2 or later?',atom('treatment_line','eq','RELAPSE_2_PLUS'),'dlbcl_third_plus','dlbcl_relapse_interval',S('BCEL-9'),decision_id='dlbcl_rr_line')
    g.decision('dlbcl_response_phase','Response assessment after first-line therapy?',atom('treatment_phase','eq','RESPONSE_ASSESSMENT'),'dlbcl_resp_stage','dlbcl_stage_limited',S('BCEL-4','BCEL-5','BCEL-6'),decision_id='dlbcl_response_phase')
    g.decision('dlbcl_stage_limited','Stage I/II?',atom('stage_group','eq','LIMITED'),'dlbcl_limited_bulky','dlbcl_advanced_confirm',S('BCEL-2','BCEL-3'),decision_id='dlbcl_stage')
    g.decision('dlbcl_limited_bulky','Bulky (≥7.5 cm) or extensive mesenteric disease?',atom('bulky_disease','eq',True),'dlbcl_bulky_first','dlbcl_smipi',S('BCEL-3'),decision_id='dlbcl_bulky')
    g.decision('dlbcl_smipi','smIPI >1?',atom('smipi_gt1','eq',True),'dlbcl_full_first','dlbcl_short_first',S('BCEL-3'),decision_id='dlbcl_smipi')
    g.action('dlbcl_short_first','DLBCL stage I/II nonbulky, smIPI 0–1: RCHOP ×3 followed by PET-guided completion.',S('BCEL-3'),[O(p,'BCEL-3','dlbcl_rchop3','RCHOP ×3 cycles')],support=['BCEL-C'],pathway_id='DLBCL_LIMITED_NONBULKY_SMIPI01')
    g.action('dlbcl_bulky_first','DLBCL stage I/II bulky: RCHOP ×3–4 then interim PET/CT and completion pathway.',S('BCEL-3'),[O(p,'BCEL-3','dlbcl_bulky_rchop','RCHOP ×3–4 cycles')],support=['BCEL-C'],pathway_id='DLBCL_LIMITED_BULKY')
    g.decision('dlbcl_advanced_confirm','Stage III/IV or extensive stage II?',atom('stage_group','eq','ADVANCED'),'dlbcl_full_first','dlbcl_need_stage',S('BCEL-3'),decision_id='dlbcl_advanced_stage')
    g.status('dlbcl_need_stage','DLBCL stage is required.','NEEDS_INFORMATION',S('BCEL-3'))
    dlbcl_first=[
      O(p,'BCEL-C','dlbcl_rchop6','RCHOP','Category 1 preferred first-line.',preference='PREFERRED',evidence='CATEGORY_1'),
      O(p,'BCEL-C','dlbcl_pola_rchp','Polatuzumab vedotin + R-CHP','Category 1 for IPI ≥2.',preference='PREFERRED',evidence='CATEGORY_1',app=atom('ipi_ge2','eq',True)),
      O(p,'BCEL-C','dlbcl_da_epoch_r','DA-EPOCH-R','Other recommended.',preference='OTHER_RECOMMENDED'),
      O(p,'BCEL-C','dlbcl_poorlv_regimen','Poor-LV-function regimen (DA-EPOCH-R/CDOP-R/CEOP-R/GCVP-R)',app=atom('poor_lvef','eq',True)),
      O(p,'BCEL-C','dlbcl_frail_regimen','Frail/>80 regimen (CDOP-R/mini-RCHOP/GCVP-R)',app=atom('very_frail_or_over80','eq',True)),
      O(p,'BCEL-C','dlbcl_cns_integrated','Systemic regimen integrated with CNS-directed therapy',app=atom('concurrent_cns_disease','eq',True))]
    g.action('dlbcl_full_first','DLBCL requiring full-course first-line therapy.',S('BCEL-3'),dlbcl_first,support=['BCEL-C','BCEL-A'],pathway_id='DLBCL_FULL_FIRST_LINE')
    g.decision('dlbcl_resp_stage','Was the initial pathway limited nonbulky smIPI 0–1?',all_(atom('stage_group','eq','LIMITED'),atom('bulky_disease','eq',False),atom('smipi_gt1','eq',False)),'dlbcl_limited_pet','dlbcl_resp_bulky_check',S('BCEL-4'),decision_id='dlbcl_response_limited_nonbulky')
    g.decision('dlbcl_resp_bulky_check','Was limited-stage disease bulky?',all_(atom('stage_group','eq','LIMITED'),atom('bulky_disease','eq',True)),'dlbcl_bulky_pet','dlbcl_adv_pet',S('BCEL-5','BCEL-6'),decision_id='dlbcl_response_bulky')
    g.decision('dlbcl_limited_pet','PET 5-PS 1–3?',atom('pet_5ps','lte',3),'dlbcl_limited_cr','dlbcl_limited_pet4',S('BCEL-4'),decision_id='dlbcl_limited_pet_cr')
    g.decision('dlbcl_limited_pet4','PET 5-PS 4?',atom('pet_5ps','eq',4),'dlbcl_limited_pr','dlbcl_pet5_biopsy',S('BCEL-4'),decision_id='dlbcl_limited_pet4')
    g.action('dlbcl_limited_cr','Limited nonbulky DLBCL PET complete response after 3 RCHOP cycles.',S('BCEL-4'),[O(p,'BCEL-4','dlbcl_rchop1_more','One additional RCHOP cycle'),O(p,'BCEL-4','dlbcl_isrt_after3','ISRT',app=atom('rt_feasible','eq',True))],pathway_id='DLBCL_LIMITED_PET_CR')
    g.action('dlbcl_limited_pr','Limited nonbulky DLBCL PET 5-PS 4 partial response.',S('BCEL-4'),[O(p,'BCEL-4','dlbcl_rchop_total46','Continue RCHOP to total 4–6 cycles ± ISRT'),O(p,'BCEL-4','dlbcl_isrt_pr','ISRT',app=atom('rt_feasible','eq',True))],pathway_id='DLBCL_LIMITED_PET4')
    g.decision('dlbcl_bulky_pet','PET 5-PS 1–3 after limited bulky therapy?',atom('pet_5ps','lte',3),'dlbcl_bulky_cr','dlbcl_bulky_pet4',S('BCEL-5'),decision_id='dlbcl_bulky_pet_cr')
    g.decision('dlbcl_bulky_pet4','PET 5-PS 4?',atom('pet_5ps','eq',4),'dlbcl_bulky_pr','dlbcl_pet5_biopsy',S('BCEL-5'),decision_id='dlbcl_bulky_pet4')
    g.action('dlbcl_bulky_cr','Limited bulky DLBCL responding to therapy: complete planned systemic therapy ± ISRT per source.',S('BCEL-5'),[O(p,'BCEL-5','dlbcl_bulky_complete','Complete planned RCHOP course'),O(p,'BCEL-5','dlbcl_bulky_isrt','Consider ISRT',app=atom('rt_feasible','eq',True))],pathway_id='DLBCL_BULKY_RESPONSE')
    g.action('dlbcl_bulky_pr','Limited bulky DLBCL PET partial response: complete systemic therapy and consider ISRT/biopsy as source-directed.',S('BCEL-5'),[O(p,'BCEL-5','dlbcl_bulky_pr_complete','Complete planned systemic therapy'),O(p,'BCEL-5','dlbcl_bulky_pr_isrt','Consider ISRT',app=atom('rt_feasible','eq',True))],pathway_id='DLBCL_BULKY_PR')
    g.decision('dlbcl_adv_pet','CR/PR at interim or end treatment?',atom('response_status','in',['CR','PR']),'dlbcl_adv_response','dlbcl_pet5_biopsy',S('BCEL-6'),decision_id='dlbcl_advanced_response')
    g.action('dlbcl_adv_response','Advanced/extensive DLBCL responding to first-line therapy: complete total planned course; surveillance after CR and source-directed local RT in selected sites.',S('BCEL-6'),[O(p,'BCEL-6','dlbcl_continue6','Continue first-line therapy to total 6 cycles',evidence='CATEGORY_1'),O(p,'BCEL-6','dlbcl_selected_isrt','ISRT to selected bulky/isolated bone sites',app=atom('rt_feasible','eq',True),decision_relevant=False)],pathway_id='DLBCL_ADV_RESPONSE')
    g.decision('dlbcl_pet5_biopsy','Residual/progressive PET-positive disease biopsy positive?',atom('biopsy_positive','eq',True),'dlbcl_relapse_interval','dlbcl_biopsy_negative',S('BCEL-4','BCEL-5','BCEL-6'),decision_id='dlbcl_residual_biopsy')
    g.action('dlbcl_biopsy_negative','PET-positive residual lesion with negative biopsy: follow-up/local management rather than automatic salvage systemic therapy.',S('BCEL-4','BCEL-5','BCEL-6'),[O(p,'BCEL-4','dlbcl_negative_biopsy_follow','Clinical/imaging follow-up ± ISRT when source-appropriate')],pathway_id='DLBCL_RESIDUAL_BIOPSY_NEG')
    g.decision('dlbcl_relapse_interval','Primary refractory or relapse <12 months?',atom('relapse_interval_months','lt',12),'dlbcl_early_cart_candidate','dlbcl_late_transplant_intent',S('BCEL-7','BCEL-8'),decision_id='dlbcl_relapse_interval')
    g.decision('dlbcl_early_cart_candidate','CAR T-cell candidate?',atom('car_t_candidate','eq',True),'dlbcl_early_cart','dlbcl_early_noncart',S('BCEL-7'),decision_id='dlbcl_early_cart_candidate')
    g.action('dlbcl_early_cart','Primary refractory/early-relapse DLBCL eligible for CAR T-cell therapy.',S('BCEL-7'),[
      O(p,'BCEL-C','dlbcl_axi','Axicabtagene ciloleucel','Preferred/category 1.',preference='PREFERRED',evidence='CATEGORY_1'),O(p,'BCEL-C','dlbcl_liso','Lisocabtagene maraleucel','Preferred/category 1.',preference='PREFERRED',evidence='CATEGORY_1'),
      O(p,'BCEL-7','dlbcl_bridge','Bridging therapy as clinically necessary')],support=['BCEL-C'],pathway_id='DLBCL_EARLY_RELAPSE_CART')
    g.action('dlbcl_early_noncart','Primary refractory/early-relapse DLBCL not a CAR T-cell candidate.',S('BCEL-7'),[
      O(p,'BCEL-7','dlbcl_early_trial','Clinical trial'),O(p,'BCEL-C','dlbcl_early_gemox_epi','GemOx + epcoritamab-bysp','Preferred.',preference='PREFERRED'),O(p,'BCEL-C','dlbcl_early_gemox_glo','GemOx + glofitamab','Preferred.',preference='PREFERRED'),
      O(p,'BCEL-C','dlbcl_early_pola','Polatuzumab-based therapy','Preferred.',preference='PREFERRED'),O(p,'BCEL-C','dlbcl_early_tafa_len','Lenalidomide + tafasitamab-cxix','Not for primary refractory disease.',app=atom('relapse_interval_months','gte',1)),
      O(p,'BCEL-7','dlbcl_early_pallrt','Palliative RT',app=atom('rt_feasible','eq',True))],support=['BCEL-C'],pathway_id='DLBCL_EARLY_RELAPSE_NONCART')
    g.decision('dlbcl_late_transplant_intent','Intention/eligibility to proceed to transplant?',all_(atom('transplant_intent','eq',True),atom('transplant_candidate','eq',True)),'dlbcl_late_salvage','dlbcl_late_nontransplant',S('BCEL-8'),decision_id='dlbcl_late_transplant_intent')
    g.action('dlbcl_late_salvage','DLBCL relapse >12 months with transplant intent: salvage chemoimmunotherapy followed by response-directed HDT/ASCR.',S('BCEL-8'),[
      O(p,'BCEL-C','dlbcl_dha','DHA-platinum ± rituximab','Preferred.',preference='PREFERRED'),O(p,'BCEL-C','dlbcl_gdp','GDP ± rituximab','Preferred.',preference='PREFERRED'),O(p,'BCEL-C','dlbcl_ice','ICE ± rituximab','Preferred.',preference='PREFERRED'),
      O(p,'BCEL-8','dlbcl_hdt_ascr','HDT/ASCR after chemosensitive response',app=atom('transplant_candidate','eq',True))],support=['BCEL-C'],pathway_id='DLBCL_LATE_RELAPSE_TRANSPLANT')
    g.action('dlbcl_late_nontransplant','DLBCL relapse >12 months without transplant intent/eligibility: non-transplant second-line therapy.',S('BCEL-8'),[
      O(p,'BCEL-C','dlbcl_late_liso','Lisocabtagene maraleucel if CAR T eligible',app=atom('car_t_candidate','eq',True)),O(p,'BCEL-C','dlbcl_late_nontx_regimens','Preferred/other non-transplant systemic second-line regimen')],support=['BCEL-C'],pathway_id='DLBCL_LATE_RELAPSE_NONTRANSPLANT')
    # relapse 2+ terminal is independently line-aware
    g.action('dlbcl_third_plus','DLBCL relapse #2 or later: third-line/subsequent therapy.',S('BCEL-9'),[
      O(p,'BCEL-C','dlbcl_3_cart','CD19 CAR T-cell therapy','Preferred where eligible.',preference='PREFERRED',app=atom('car_t_candidate','eq',True)),O(p,'BCEL-C','dlbcl_3_epcor','Epcoritamab-bysp','Preferred.',preference='PREFERRED',app=atom('cd20_positive','eq',True)),O(p,'BCEL-C','dlbcl_3_glofit','Glofitamab','Preferred.',preference='PREFERRED',app=atom('cd20_positive','eq',True)),O(p,'BCEL-C','dlbcl_3_lonca','Loncastuximab tesirine-lpyl'),O(p,'BCEL-C','dlbcl_3_selinexor','Selinexor'),O(p,'BCEL-9','dlbcl_3_allohct','Allogeneic HCT in selected responders',app=atom('transplant_candidate','eq',True))],support=['BCEL-C'],pathway_id='DLBCL_THIRD_PLUS')

    # Primary cutaneous DLBCL leg type (BCEL-10) is represented as DLBCL + localized_disease; explicit path consumes page.
    # A dedicated morphology flag is not in original subtype taxonomy, so route through a new context fact only when supplied.
    add(p,fact('primary_cutaneous_leg_type','BOOLEAN'))
    roles['primary_cutaneous_leg_type']='ROUTING'
    # Insert before standard DLBCL routing by redirecting subtype DLBCL TRUE target.
    g.nodes['sub_dlbcl']['on']['TRUE']='dlbcl_cutaneous_check'
    g.decision('dlbcl_cutaneous_check','Primary cutaneous DLBCL, leg type?',atom('primary_cutaneous_leg_type','eq',True),'dlbcl_cutaneous_local','dlbcl_entry',S('BCEL-10'),decision_id='dlbcl_primary_cutaneous_leg_type')
    g.decision('dlbcl_cutaneous_local','Localized cutaneous disease?',atom('localized_disease','eq',True),'dlbcl_cutaneous_local_action','dlbcl_cutaneous_general',S('BCEL-10'),decision_id='dlbcl_cutaneous_localized')
    g.action('dlbcl_cutaneous_local_action','Primary cutaneous DLBCL leg type, localized disease: local RT and/or systemic chemoimmunotherapy per extent.',S('BCEL-10'),[O(p,'BCEL-10','pcdlbcl_isrt','ISRT',app=atom('rt_feasible','eq',True)),O(p,'BCEL-10','pcdlbcl_rchop','RCHOP-based systemic therapy')],support=['BCEL-C','NHODG-D'],pathway_id='PCDLBCL_LOCALIZED')
    g.action('dlbcl_cutaneous_general','Primary cutaneous DLBCL leg type, generalized disease: systemic DLBCL therapy.',S('BCEL-10'),[O(p,'BCEL-C','pcdlbcl_systemic','DLBCL systemic chemoimmunotherapy')],support=['BCEL-C'],pathway_id='PCDLBCL_GENERALIZED')

    # ---------- PMBL ----------
    g.decision('pmbl_entry','Response assessment after PMBL first-line therapy?',atom('treatment_phase','eq','RESPONSE_ASSESSMENT'),'pmbl_pet','pmbl_rr_check',S('PMBL-1'),decision_id='pmbl_response_phase')
    g.decision('pmbl_rr_check','Relapsed/refractory PMBL?',any_(atom('treatment_phase','eq','RELAPSED_REFRACTORY'),atom('response_status','in',['RELAPSED','PROGRESSIVE'])),'pmbl_rr','pmbl_first',S('PMBL-1'),decision_id='pmbl_rr')
    g.action('pmbl_first','PMBL first-line therapy.',S('PMBL-1'),[O(p,'PMBL-1','pmbl_da_epoch_r','DA-EPOCH-R ×6'),O(p,'PMBL-1','pmbl_rchop14','RCHOP-14 ×4–6'),O(p,'PMBL-1','pmbl_rchop21','RCHOP-21 ×6')],pathway_id='PMBL_FIRST_LINE')
    g.decision('pmbl_pet','PET 5-PS 1–3 complete response?',atom('pet_5ps','lte',3),'pmbl_surv','pmbl_pet4',S('PMBL-1'),decision_id='pmbl_pet_cr')
    g.decision('pmbl_pet4','PET 5-PS 4 partial response?',atom('pet_5ps','eq',4),'pmbl_pr','pmbl_biopsy',S('PMBL-1'),decision_id='pmbl_pet4')
    g.action('pmbl_surv','PMBL complete metabolic response: active surveillance/follow-up.',S('PMBL-1'),[O(p,'PMBL-1','pmbl_follow','Clinical follow-up and source-defined imaging')],pathway_id='PMBL_CR')
    g.action('pmbl_pr','PMBL PET 5-PS 4 partial response: active surveillance or ISRT in source-defined settings; biopsy before additional systemic therapy.',S('PMBL-1'),[O(p,'PMBL-1','pmbl_pr_watch','Active surveillance'),O(p,'PMBL-1','pmbl_pr_isrt','ISRT',app=atom('rt_feasible','eq',True))],pathway_id='PMBL_PR')
    g.decision('pmbl_biopsy','PET 5 residual/progressive mass biopsy positive?',atom('biopsy_positive','eq',True),'pmbl_rr','pmbl_surv',S('PMBL-1'),decision_id='pmbl_residual_biopsy')
    g.action('pmbl_rr','Relapsed/refractory PMBL.',S('PMBL-1'),[O(p,'PMBL-1','pmbl_pembro','Pembrolizumab'),O(p,'PMBL-1','pmbl_nivo_bv','Nivolumab ± brentuximab vedotin','Category 2B.',evidence='CATEGORY_2B'),O(p,'PMBL-1','pmbl_dlbcl_rr','Manage by DLBCL relapsed/refractory timing pathway')],support=['BCEL-7','BCEL-8'],pathway_id='PMBL_RELAPSED_REFRACTORY')

    # ---------- TRANSFORMED INDOLENT -> DLBCL ----------
    g.decision('trans_entry','Current transformed-lymphoma response assessment?',atom('treatment_phase','eq','RESPONSE_ASSESSMENT'),'trans_response','trans_prior_lines_check',S('HTBCEL-1','HTBCEL-2'),decision_id='trans_response_phase')
    g.decision('trans_prior_lines_check','Transformation after multiple prior indolent-lymphoma lines?',atom('prior_indolent_lines','gte',2),'trans_multi','trans_doublehit_bcl2',S('HTBCEL-1'),decision_id='trans_prior_lines')
    g.decision('trans_doublehit_bcl2','MYC + BCL2 rearranged?',all_(atom('myc_rearranged','eq',True),atom('hgbcl_bcl2_rearranged','eq',True)),'hgbl_entry','trans_minimal',S('HTBCEL-1'),decision_id='trans_double_hit')
    g.action('trans_minimal','Histologic transformation after minimal/no prior therapy: anthracycline-based chemoimmunotherapy ± ISRT.',S('HTBCEL-1'),[O(p,'HTBCEL-1','trans_anthracycline','Anthracycline-based chemoimmunotherapy'),O(p,'HTBCEL-1','trans_isrt','ISRT for localized/bulky/osseous disease',app=atom('rt_feasible','eq',True),decision_relevant=False)],support=['BCEL-C','NHODG-D'],pathway_id='TRANSFORMED_MINIMAL_PRIOR')
    g.decision('trans_multi','Candidate for additional active therapy?',atom('systemic_therapy_candidate','eq',True),'trans_multi_treat','trans_bsc',S('HTBCEL-3'),decision_id='trans_multi_candidate')
    g.action('trans_multi_treat','Histologic transformation after multiple prior therapies: clinical trial/systemic therapy/RT; response-directed cellular therapy or transplant when eligible.',S('HTBCEL-3'),[O(p,'HTBCEL-3','trans_trial','Clinical trial'),O(p,'HTBCEL-3','trans_sys','Systemic therapy'),O(p,'HTBCEL-3','trans_cart','CAR T-cell therapy',app=atom('car_t_candidate','eq',True)),O(p,'HTBCEL-3','trans_allohct','Allogeneic HCT',app=atom('transplant_candidate','eq',True)),O(p,'HTBCEL-3','trans_rt','ISRT',app=atom('rt_feasible','eq',True))],pathway_id='TRANSFORMED_MULTIPLE_PRIOR')
    g.action('trans_bsc','Histologic transformation not a candidate for additional active therapy: best supportive/palliative care.',S('HTBCEL-3'),[O(p,'HTBCEL-3','trans_bscopt','Best supportive/palliative care')],pathway_id='TRANSFORMED_BSC')
    # explicit transformed response page
    g.decision('trans_response','Transformed lymphoma complete response?',atom('response_status','eq','CR'),'trans_cr','trans_noncr',S('HTBCEL-2'),decision_id='trans_response_cr')
    g.action('trans_cr','Transformed lymphoma CR: surveillance; consider source-directed maintenance if coexisting extensive follicular lymphoma.',S('HTBCEL-2'),[O(p,'HTBCEL-2','trans_surv','Surveillance')],pathway_id='TRANSFORMED_CR')
    g.action('trans_noncr','Transformed lymphoma PR/NR/progression: repeat biopsy and eligible salvage/cellular-therapy pathway.',S('HTBCEL-2'),[O(p,'HTBCEL-2','trans_rebiopsy','Repeat biopsy'),O(p,'HTBCEL-2','trans_salvage_cart','CAR T-cell therapy when eligible',app=atom('car_t_candidate','eq',True))],pathway_id='TRANSFORMED_NONCR')

    # ---------- HIGH-GRADE B-CELL LYMPHOMA ----------
    g.decision('hgbl_entry','HGBL with MYC + BCL2 rearrangements?',all_(atom('myc_rearranged','eq',True),atom('hgbcl_bcl2_rearranged','eq',True)),'hgbl_doublehit','hgbl_other',S('HGBL-1'),decision_id='hgbl_myc_bcl2')
    g.action('hgbl_doublehit','HGBL with MYC and BCL2 rearrangements.',S('HGBL-1'),[O(p,'HGBL-1','hgbl_trial','Clinical trial'),O(p,'HGBL-1','hgbl_da_epoch_r','DA-EPOCH-R'),O(p,'HGBL-1','hgbl_rchop_lowrisk','RCHOP','For low-risk IPI <2.',app=atom('ipi_0_2','eq',True)),O(p,'HGBL-1','hgbl_mini_rchop','Mini-RCHOP','Frail/older.',app=atom('very_frail_or_over80','eq',True)),O(p,'HGBL-1','hgbl_isrt','Consolidative ISRT for localized disease',app=all_(atom('localized_disease','eq',True),atom('rt_feasible','eq',True)))],pathway_id='HGBL_MYC_BCL2')
    g.action('hgbl_other','HGBL-NOS or MYC/BCL6 rearranged without MYC/BCL2: DLBCL-like systemic therapy or clinical trial.',S('HGBL-1'),[O(p,'HGBL-1','hgbl_other_trial','Clinical trial'),O(p,'HGBL-1','hgbl_other_rchop','RCHOP'),O(p,'HGBL-1','hgbl_other_daepoch','DA-EPOCH-R'),O(p,'HGBL-1','hgbl_other_pola','Polatuzumab + R-CHP','Category 2B in source-defined setting.',evidence='CATEGORY_2B')],support=['BCEL-C'],pathway_id='HGBL_OTHER')

    # ---------- BURKITT ----------
    g.decision('burk_entry','Relapsed/refractory Burkitt lymphoma?',any_(atom('treatment_phase','eq','RELAPSED_REFRACTORY'),atom('response_status','in',['RELAPSED','PROGRESSIVE'])),'burk_rr_interval','burk_lowrisk_all',S('BURK-3'),decision_id='burk_rr')
    # low risk = normal LDH AND (stage I single extra-abdominal <10cm OR completely resected abdominal lesion)
    g.decision('burk_lowrisk_all','Normal LDH?',atom('burkitt_ldh_normal','eq',True),'burk_lowrisk_stage','burk_high',S('BURK-2'),decision_id='burk_ldh')
    g.decision('burk_lowrisk_stage','Stage I/limited?',atom('stage_group','eq','LIMITED'),'burk_abdominal','burk_high',S('BURK-2'),decision_id='burk_stage_lowrisk')
    g.decision('burk_abdominal','Abdominal presentation?',atom('burkitt_abdominal_mass','eq',True),'burk_abd_resect','burk_mass_lt10',S('BURK-2'),decision_id='burk_abdominal')
    g.decision('burk_abd_resect','Abdominal lesion completely resected?',atom('abdominal_lesion_completely_resected','eq',True),'burk_low','burk_high',S('BURK-2'),decision_id='burk_abdominal_resection')
    g.decision('burk_mass_lt10','Single extra-abdominal mass <10 cm?',atom('burkitt_mass_cm','lt',10),'burk_low','burk_high',S('BURK-2'),decision_id='burk_mass_threshold')
    g.action('burk_low','Low-risk Burkitt lymphoma induction with mandatory CNS prophylaxis.',S('BURK-2'),[O(p,'BURK-A','burk_low_codox','CODOX-M + rituximab'),O(p,'BURK-A','burk_low_daepoch','Risk-adapted DA-EPOCH-R'),O(p,'BURK-A','burk_low_hypercvad','HyperCVAD alternating high-dose methotrexate/cytarabine + rituximab')],support=['BURK-A'],pathway_id='BURKITT_LOW_RISK')
    g.action('burk_high','High-risk Burkitt lymphoma induction with CNS-directed therapy.',S('BURK-2'),[O(p,'BURK-A','burk_hi_codoxivac','CODOX-M/IVAC + rituximab'),O(p,'BURK-A','burk_hi_hypercvad','HyperCVAD + rituximab'),O(p,'BURK-A','burk_hi_daepoch','DA-EPOCH-R with source-directed intrathecal intensification when CNS involved')],support=['BURK-A'],pathway_id='BURKITT_HIGH_RISK')
    g.decision('burk_rr_interval','Relapse >6 months?',atom('relapse_interval_months','gt',6),'burk_rr_late','burk_rr_early',S('BURK-3'),decision_id='burk_relapse_interval')
    g.action('burk_rr_late','Burkitt relapse beyond early interval: clinical trial or second-line systemic therapy; transplant consolidation for responders when eligible.',S('BURK-3'),[O(p,'BURK-3','burk_rr_trial','Clinical trial'),O(p,'BURK-3','burk_rr_second','Second-line therapy'),O(p,'BURK-3','burk_rr_ascr','HDT/ASCR after CR',app=atom('transplant_candidate','eq',True)),O(p,'BURK-3','burk_rr_allo','Allogeneic HCT in selected responders',app=atom('transplant_candidate','eq',True))],pathway_id='BURKITT_RELAPSE_LATE')
    g.action('burk_rr_early','Very early Burkitt relapse/refractory disease: clinical trial or best supportive care; salvage individualized.',S('BURK-3'),[O(p,'BURK-3','burk_early_trial','Clinical trial'),O(p,'BURK-3','burk_early_bsc','Best supportive care')],pathway_id='BURKITT_RELAPSE_EARLY')

    # ---------- HIV-RELATED B-CELL LYMPHOMAS ----------
    hivchain=[('hiv_hist_burk','BURKITT','hiv_burk','hiv_hist_dlbcl'),('hiv_hist_dlbcl','DLBCL','hiv_dlbcl','hiv_hist_hhv8'),('hiv_hist_hhv8','HHV8_DLBCL','hiv_dlbcl','hiv_hist_pel'),('hiv_hist_pel','PRIMARY_EFFUSION','hiv_dlbcl','hiv_hist_plasma'),('hiv_hist_plasma','PLASMABLASTIC','hiv_plasma','hiv_hist_pcnsl'),('hiv_hist_pcnsl','PRIMARY_CNS','hiv_pcnsl','hiv_need_hist')]
    g.nodes['hiv_entry']={'kind':'decision','label':'HIV-related lymphoma histology: Burkitt?','expression':atom('hiv_lymphoma_histology','eq','BURKITT'),'on':{'TRUE':'hiv_burk','FALSE':'hiv_hist_dlbcl'},'source_pathways':['HIVLYM-2'],'decision_id':'hiv_histology_burkitt'}
    for nid,val,t,f in hivchain[1:]: g.decision(nid,f'HIV-related histology {val}?',atom('hiv_lymphoma_histology','eq',val),t,f,S('HIVLYM-2'),decision_id=f'hiv_histology_{val.lower()}')
    g.status('hiv_need_hist','Specific HIV-related B-cell lymphoma histology is required.','NEEDS_INFORMATION',S('HIVLYM-2'))
    g.action('hiv_burk','HIV-associated Burkitt lymphoma: Burkitt-directed induction with concurrent HIV/supportive management.',S('HIVLYM-3'),[O(p,'HIVLYM-A','hiv_burk_regimens','HIV-appropriate Burkitt regimen')],support=['BURK-A','HIVLYM-A','HIVLYM-B'],pathway_id='HIV_BURKITT')
    g.decision('hiv_dlbcl','Relapsed/refractory HIV-related DLBCL/HHV8 DLBCL/primary effusion lymphoma?',any_(atom('treatment_phase','eq','RELAPSED_REFRACTORY'),atom('response_status','in',['RELAPSED','PROGRESSIVE'])),'dlbcl_relapse_interval','hiv_dlbcl_first',S('HIVLYM-2','HIVLYM-3'),decision_id='hiv_dlbcl_rr')
    g.action('hiv_dlbcl_first','HIV-related DLBCL/related aggressive B-cell lymphoma first-line therapy with ART and supportive care.',S('HIVLYM-2','HIVLYM-3'),[O(p,'HIVLYM-A','hiv_dlbcl_regimen','HIV-associated aggressive B-cell lymphoma chemoimmunotherapy'),O(p,'HIVLYM-A','hiv_dlbcl_ritux','Rituximab when CD20 positive',app=atom('cd20_positive','eq',True))],support=['HIVLYM-A','HIVLYM-B'],pathway_id='HIV_DLBCL_FIRST')
    g.action('hiv_plasma','HIV-associated plasmablastic lymphoma.',S('HIVLYM-4'),[O(p,'HIVLYM-4','hiv_plasma_epoch','EPOCH-based systemic therapy'),O(p,'HIVLYM-4','hiv_plasma_hct','Consider HCT in first CR for high-risk disease',app=all_(atom('high_risk_plasmablastic','eq',True),atom('transplant_candidate','eq',True))),O(p,'HIVLYM-4','hiv_plasma_isrt','ISRT for localized disease',app=all_(atom('localized_disease','eq',True),atom('rt_feasible','eq',True)))],pathway_id='HIV_PLASMABLASTIC')
    g.decision('hiv_pcnsl','Candidate for systemic high-dose methotrexate?',atom('systemic_therapy_candidate','eq',True),'hiv_pcnsl_mtx','hiv_pcnsl_rt',S('HIVLYM-3'),decision_id='hiv_pcnsl_systemic_candidate')
    g.action('hiv_pcnsl_mtx','HIV-associated primary CNS lymphoma: ART + high-dose methotrexate-based therapy.',S('HIVLYM-3'),[O(p,'HIVLYM-3','hiv_pcnsl_hdmtx','High-dose methotrexate-based therapy + ART')],pathway_id='HIV_PCN_SL_MTX')
    g.action('hiv_pcnsl_rt','HIV-associated primary CNS lymphoma not candidate for systemic therapy: RT/palliative management.',S('HIVLYM-3'),[O(p,'HIVLYM-3','hiv_pcnsl_rtopt','RT',app=atom('rt_feasible','eq',True)),O(p,'HIVLYM-3','hiv_pcnsl_bsc','Best supportive care')],pathway_id='HIV_PCN_SL_NONSYSTEMIC')

    # ---------- LYMPHOBLASTIC LYMPHOMA ----------
    g.decision('blast_entry','B-lymphoblastic lymphoma lineage?',atom('lymphoblastic_lineage','eq','B'),'blast_b','blast_t',S('BLAST-1'),decision_id='blast_lineage')
    g.action('blast_b','B-lymphoblastic lymphoma: treat according to the B-ALL systemic/CNS-directed program referenced by the source.',S('BLAST-1'),[O(p,'BLAST-1','blast_b_all_program','B-ALL–type multiagent systemic + CNS-directed treatment')],pathway_id='B_LYMPHOBLASTIC_LYMPHOMA')
    g.action('blast_t','T-lymphoblastic lymphoma: treat according to the T-ALL/T-lymphoblastic systemic/CNS-directed program referenced by the source.',S('BLAST-1'),[O(p,'BLAST-1','blast_t_all_program','T-ALL/T-lymphoblastic–type multiagent systemic + CNS-directed treatment')],pathway_id='T_LYMPHOBLASTIC_LYMPHOMA')

    # ---------- PTLD ----------
    ptchain=[('ptld_non','NONDESTRUCTIVE','ptld_non_action','ptld_poly'),('ptld_poly','POLYMORPHIC_B','ptld_poly_action','ptld_mono_b'),('ptld_mono_b','MONOMORPHIC_B','ptld_mono_b_action','ptld_mono_t'),('ptld_mono_t','MONOMORPHIC_T','ptld_mono_t_action','ptld_chl'),('ptld_chl','CHL_TYPE','ptld_chl_action','ptld_cns'),('ptld_cns','PRIMARY_CNS','ptld_cns_action','ptld_need_sub')]
    for nid,val,t,f in ptchain:g.decision(nid,f'PTLD subtype {val}?',atom('ptld_subtype','eq',val),t,f,S('PTLD-1'),decision_id=f'ptld_subtype_{val.lower()}')
    # entry alias into chain
    g.nodes['ptld_entry']=g.nodes.pop('ptld_non'); g.nodes['ptld_entry']['decision_id']='ptld_subtype_nondestructive'
    g.status('ptld_need_sub','PTLD morphologic subtype is required.','NEEDS_INFORMATION',S('PTLD-1'))
    g.action('ptld_non_action','Nondestructive PTLD: reduce immunosuppression and response-assess; rituximab for persistent/progressive B-cell disease.',S('PTLD-2'),[O(p,'PTLD-2','ptld_non_ris','Reduce immunosuppression'),O(p,'PTLD-2','ptld_non_ritux','Rituximab for persistent/progressive disease',app=atom('response_status','in',['SD','PROGRESSIVE']))],pathway_id='PTLD_NONDESTRUCTIVE')
    g.decision('ptld_poly_action','Localized polymorphic PTLD?',atom('localized_disease','eq',True),'ptld_poly_local','ptld_poly_systemic',S('PTLD-3'),decision_id='ptld_polymorphic_localized')
    g.action('ptld_poly_local','Localized polymorphic B-cell PTLD: reduction of immunosuppression + rituximab/chemo; ISRT or surgery selected.',S('PTLD-3'),[O(p,'PTLD-3','ptld_poly_ris','Reduce immunosuppression'),O(p,'PTLD-3','ptld_poly_ritux','Rituximab ± chemoimmunotherapy'),O(p,'PTLD-3','ptld_poly_isrt','ISRT',app=atom('rt_feasible','eq',True)),O(p,'PTLD-3','ptld_poly_surg','Surgery',app=atom('surgery_feasible','eq',True))],pathway_id='PTLD_POLYMORPHIC_LOCAL')
    g.action('ptld_poly_systemic','Systemic polymorphic B-cell PTLD: reduction of immunosuppression + rituximab/chemoimmunotherapy; EBV-directed cellular therapy selected.',S('PTLD-3'),[O(p,'PTLD-3','ptld_poly_sys_ris','Reduce immunosuppression'),O(p,'PTLD-3','ptld_poly_sys_ritux','Rituximab ± chemoimmunotherapy'),O(p,'PTLD-3','ptld_poly_ebvctl','EBV-specific cytotoxic T lymphocytes',app=atom('ebv_driven','eq',True))],pathway_id='PTLD_POLYMORPHIC_SYSTEMIC')
    g.decision('ptld_mono_b_action','Initial PTLD therapy was reduction of immunosuppression alone?',atom('initial_ptld_therapy','eq','REDUCE_IMMUNOSUPPRESSION'),'ptld_mono_after_ris','ptld_mono_ritux_check',S('PTLD-2'),decision_id='ptld_mono_initial_ris')
    g.action('ptld_mono_after_ris','Monomorphic B-cell PTLD persistent after reduction of immunosuppression: rituximab or chemoimmunotherapy.',S('PTLD-2'),[O(p,'PTLD-2','ptld_mono_ritux','Rituximab'),O(p,'PTLD-2','ptld_mono_chemo','Chemoimmunotherapy')],pathway_id='PTLD_MONO_B_AFTER_RIS')
    g.decision('ptld_mono_ritux_check','Initial therapy rituximab?',atom('initial_ptld_therapy','eq','RITUXIMAB'),'ptld_mono_after_ritux','ptld_mono_after_chemo',S('PTLD-2'),decision_id='ptld_mono_initial_ritux')
    g.action('ptld_mono_after_ritux','Monomorphic B-cell PTLD after rituximab: chemoimmunotherapy or selected continued rituximab in lower-risk disease.',S('PTLD-2'),[O(p,'PTLD-2','ptld_mono_afterritux_chemo','Chemoimmunotherapy'),O(p,'PTLD-2','ptld_mono_continue_ritux','Continue rituximab in selected IPI 0–2 disease',app=atom('ipi_0_2','eq',True)),O(p,'PTLD-2','ptld_mono_ebvctl','EBV-specific cellular therapy',app=atom('ebv_driven','eq',True))],pathway_id='PTLD_MONO_B_AFTER_RITUX')
    g.action('ptld_mono_after_chemo','Monomorphic B-cell PTLD relapsed/refractory after chemoimmunotherapy: DLBCL relapsed/refractory pathway.',S('PTLD-2'),[O(p,'PTLD-2','ptld_mono_dlbcl_rr','DLBCL salvage/cellular-therapy pathway')],support=['BCEL-7','BCEL-8','BCEL-9'],pathway_id='PTLD_MONO_B_AFTER_CHEMO')
    g.action('ptld_mono_t_action','Monomorphic T-cell PTLD: external T-cell lymphoma guideline dependency.',S('PTLD-1'),[O(p,'PTLD-1','ptld_t_external','Refer to the appropriate NCCN T-cell lymphoma guideline')],pathway_id='PTLD_MONO_T_EXTERNAL')
    g.action('ptld_chl_action','Classic Hodgkin lymphoma–type PTLD: external Hodgkin lymphoma guideline dependency.',S('PTLD-1'),[O(p,'PTLD-1','ptld_chl_external','Refer to the NCCN Hodgkin Lymphoma guideline')],pathway_id='PTLD_CHL_EXTERNAL')
    g.action('ptld_cns_action','Primary CNS PTLD: high-dose methotrexate + rituximab when eligible.',S('PTLD-1'),[O(p,'PTLD-A','ptld_cns_mtx_r','High-dose methotrexate + rituximab',app=atom('systemic_therapy_candidate','eq',True)),O(p,'PTLD-A','ptld_cns_local','RT/palliative approach when systemic therapy is not feasible',app=atom('systemic_therapy_candidate','eq',False))],support=['PTLD-A'],pathway_id='PTLD_PRIMARY_CNS')

    g.status('outside','Outside the B-cell lymphoma guideline package.','OUTSIDE_ENCODED_SCOPE',S('DIAG-1'))

    # Cross-state contradictions with care-state priority.
    consistency=[
      {'id':'bcell_relapse_surveillance_conflict','when':all_(atom('treatment_phase','eq','SURVEILLANCE'),atom('response_status','in',['RELAPSED','PROGRESSIVE'])),'message':'Active relapse/progression conflicts with a surveillance care state.','source_pathways':['NHODG-C']},
      {'id':'bcell_limited_advanced_conflict','when':all_(atom('stage_group','eq','LIMITED'),atom('localized_disease','eq',False)),'message':'Limited stage conflicts with a confirmed nonlocalized disease state.','source_pathways':['ST-1']},
    ]
    p['nodes']=g.nodes; set_roles(p,roles); p['derived_rules']=[]; p['consistency_rules']=consistency
    p['lifecycle']={**p.get('lifecycle',{}),'package_status':'DRAFT','clinical_status':'REQUIRES_CLINICAL_REVIEW','runtime_eligible':False}
    save(p)
    print('built',NAME,'facts',len(p['fact_definitions']),'nodes',len(p['nodes']))

if __name__=='__main__': build()
