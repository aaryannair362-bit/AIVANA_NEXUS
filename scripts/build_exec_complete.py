from __future__ import annotations
import json,re,sys
from pathlib import Path
from copy import deepcopy
from builder_lib import Graph,atom,any_,all_,not_,opt,fact,upsert_fact,set_roles,src_prov

ROOT=Path(__file__).resolve().parents[1]
ENC=ROOT/'backend/nexus/guidelines/encoded'

def load(name): return json.loads((ENC/name).read_text())
def save(name,pkg): (ENC/name).write_text(json.dumps(pkg,indent=2,sort_keys=False))

def support_src(pkg,section): return src_prov(pkg,section)

def common_finalize(pkg,g,roles,extra_decisions=None,derived_rules=None,consistency_rules=None):
    pkg['nodes']=g.nodes
    set_roles(pkg,roles)
    pkg['derived_rules']=derived_rules or []
    pkg['consistency_rules']=consistency_rules or []
    pkg['lifecycle']={**pkg.get('lifecycle',{}),'package_status':'DRAFT','clinical_status':'REQUIRES_CLINICAL_REVIEW','runtime_eligible':False}
    pkg['executable_decisions']=extra_decisions or []
    return pkg

def all_builder():
    name='nexus_acute_lymphoblastic_leukemia_v2_2026.json'; pkg=load(name)
    # add source-driving facts
    additions=[
      fact('age_years','NUMERIC',role='OPTION_APPLICABILITY'),
      fact('substantial_comorbidities','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('poor_risk_b_all','BOOLEAN',role='DERIVED_DETERMINISTIC'),
      fact('high_risk_t_all','BOOLEAN',role='ROUTING'),
      fact('prior_hct','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('relapse_interval_years','NUMERIC',role='OPTION_APPLICABILITY'),
      fact('prior_tki_count','NUMERIC',role='OPTION_APPLICABILITY'),
      fact('cd19_positive','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('cd22_positive','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('kmt2a_rearranged','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('extramedullary_disease','BOOLEAN',role='ROUTING'),
    ]
    for f in additions: upsert_fact(pkg,f)
    roles={d['key']:('ROUTING' if d['key'] in {'cancer_type','diagnosis_confirmed','lineage','ph_status','treatment_phase','response_status','mrd_status','cns_involvement','transplant_candidate'} else d.get('fact_role','NON_ROUTING_CONTEXT')) for d in pkg['fact_definitions']}
    roles.update({'age_years':'OPTION_APPLICABILITY','substantial_comorbidities':'OPTION_APPLICABILITY','poor_risk_b_all':'DERIVED_DETERMINISTIC','high_risk_t_all':'ROUTING','prior_hct':'OPTION_APPLICABILITY','relapse_interval_years':'OPTION_APPLICABILITY','prior_tki_count':'OPTION_APPLICABILITY','cd19_positive':'OPTION_APPLICABILITY','cd22_positive':'OPTION_APPLICABILITY','kmt2a_rearranged':'OPTION_APPLICABILITY','extramedullary_disease':'ROUTING'})
    g=Graph(); src=lambda *x:list(x)
    # global routing / care-state priority
    g.decision('scope','Acute lymphoblastic leukemia?',atom('cancer_type','eq','ACUTE_LYMPHOBLASTIC_LEUKEMIA'),'diag','outside',src('ALL-1'),'all_scope')
    g.decision('diag','Diagnosis confirmed?',atom('diagnosis_confirmed'),'care_rr','workup',src('ALL-1'),'all_diagnosis_confirmed')
    g.action('workup','Complete ALL diagnosis, molecular characterization, baseline MRD clone definition, CNS evaluation, workup and transplant evaluation before treatment routing.',src('ALL-1','ALL-2','ALL-3'),[
      opt('all_workup_molecular','Molecular/cytogenetic characterization','Complete BCR::ABL1 and recurrent genomic testing required for subtype/risk-directed therapy.',src=support_src(pkg,'ALL-1')),
      opt('all_workup_cns','Lumbar puncture with intrathecal therapy','Perform CNS evaluation/prophylaxis according to ALL-3/ALL-B.',src=support_src(pkg,'ALL-3')),
      opt('all_workup_transplant','Early transplant evaluation/donor search','Strongly consider early HCT evaluation.',src=support_src(pkg,'ALL-3')),
    ],support=['ALL-A','ALL-B','ALL-C','ALL-F','ALL-G'],pathway_id='ALL_WORKUP')
    g.decision('care_rr','Relapsed/refractory or active progression episode?',any_(atom('treatment_phase','eq','RELAPSED_REFRACTORY'),atom('response_status','in',['REFRACTORY','RELAPSED'])),'rr_lineage','care_surv',src('ALL-8'),'all_care_state_rr')
    g.decision('care_surv','Post-treatment surveillance episode?',atom('treatment_phase','eq','SURVEILLANCE'),'surveillance','lineage_b',src('ALL-7'),'all_care_state_surveillance')
    g.action('surveillance','ALL surveillance after completion of therapy with clinical/CBC follow-up, disease-specific molecular monitoring, and prompt relapse workup when indicated.',src('ALL-7'),[
      opt('all_surv_standard','Scheduled surveillance','Follow ALL-7 surveillance intervals.'),
      opt('all_surv_phplus_bcrabl','Periodic BCR::ABL1 quantification','For Ph-positive ALL.',app=atom('ph_status','eq','POSITIVE')),
    ],support=['ALL-F'],pathway_id='ALL_SURVEILLANCE')
    g.decision('lineage_b','B-ALL lineage?',atom('lineage','eq','B_ALL'),'b_ph','lineage_t',src('ALL-3'),'all_lineage_b')
    g.decision('lineage_t','T-ALL lineage?',atom('lineage','eq','T_ALL'),'t_phase','lineage_missing',src('ALL-3'),'all_lineage_t')
    g.status('lineage_missing','ALL lineage is unresolved or outside B-ALL/T-ALL scope.','NEEDS_DIFFERENT_PATHWAY',src('ALL-1','ALL-3'))
    # B-ALL split
    g.decision('b_ph','BCR::ABL1/Philadelphia chromosome positive?',atom('ph_status','eq','POSITIVE'),'bph_phase','bph_negative_confirm',src('ALL-4'),'all_b_ph_status_positive')
    g.decision('bph_negative_confirm','BCR::ABL1/Philadelphia chromosome confirmed negative?',atom('ph_status','eq','NEGATIVE'),'bneg_phase','need_ph',src('ALL-5'),'all_b_ph_status_negative')
    g.status('need_ph','BCR::ABL1/Philadelphia status is required before B-ALL treatment routing.','NEEDS_INFORMATION',src('ALL-4','ALL-5'))
    # Ph+ care state
    g.decision('bph_phase','Post-induction/consolidation response assessment?',any_(atom('treatment_phase','eq','POST_INDUCTION'),atom('treatment_phase','eq','POST_CONSOLIDATION')),'bph_response','bph_initial',src('ALL-4'),'all_bph_phase_response')
    g.decision('bph_response','Marrow CR achieved?',atom('response_status','in',['CR','CR_WITH_MRD']),'bph_mrd','rr_phplus',src('ALL-4'),'all_bph_marrow_cr')
    g.decision('bph_mrd','MRD negative at current post-treatment timepoint?',atom('mrd_status','eq','NEGATIVE'),'bph_mrdneg','bph_mrdpos_confirm',src('ALL-4'),'all_bph_mrd')
    g.decision('bph_mrdpos_confirm','MRD positive?',atom('mrd_status','eq','POSITIVE'),'bph_mrdpos','need_mrd_bph',src('ALL-4'),'all_bph_mrd_positive')
    g.status('need_mrd_bph','Current MRD status is required for Ph-positive B-ALL post-remission routing.','NEEDS_INFORMATION',src('ALL-4'))
    # Frontline exact options by age/comorbidity
    bph_front_opts=[
      opt('all_bph_trial','Clinical trial','Preferred.',preference='PREFERRED',src=support_src(pkg,'ALL-D')),
      opt('all_bph_blin_tki','TKI + blinatumomab','Other recommended frontline induction.',preference='OTHER_RECOMMENDED',src=support_src(pkg,'ALL-D')),
      opt('all_bph_hypercvad_tki','TKI + HyperCVAD','Other recommended for patients <65 without substantial comorbidities.',preference='OTHER_RECOMMENDED',app=all_(atom('age_years','lt',65),atom('substantial_comorbidities','eq',False)),src=support_src(pkg,'ALL-D')),
      opt('all_bph_steroid_tki','TKI + corticosteroid','Useful in certain circumstances; also low-intensity option in older/comorbid patients.',preference='USEFUL_IN_CERTAIN_CIRCUMSTANCES',src=support_src(pkg,'ALL-D')),
      opt('all_bph_vin_dex_tki','TKI + vincristine + dexamethasone','Useful/low-intensity option.',preference='USEFUL_IN_CERTAIN_CIRCUMSTANCES',src=support_src(pkg,'ALL-D')),
      opt('all_bph_epoch_tki','TKI + dose-adjusted EPOCH','Moderate-intensity option for age >=65 or substantial comorbidities.',preference='OTHER_RECOMMENDED',app=any_(atom('age_years','gte',65),atom('substantial_comorbidities','eq',True)),src=support_src(pkg,'ALL-D')),
      opt('all_bph_minihypercvd_tki','TKI + mini-hyperCVD','Moderate-intensity option for age >=65 or substantial comorbidities.',preference='OTHER_RECOMMENDED',app=any_(atom('age_years','gte',65),atom('substantial_comorbidities','eq',True)),src=support_src(pkg,'ALL-D')),
      opt('all_bph_phallcon','TKI + PhALLCON regimen','Moderate-intensity option for age >=65 or substantial comorbidities.',preference='OTHER_RECOMMENDED',app=any_(atom('age_years','gte',65),atom('substantial_comorbidities','eq',True)),src=support_src(pkg,'ALL-D')),
      opt('all_bph_cns','CNS prophylaxis / intrathecal therapy','All ALL regimens include CNS prophylaxis.',src=support_src(pkg,'ALL-D')),
    ]
    g.action('bph_initial','Ph-positive B-ALL initial therapy: TKI-containing induction selected by age/comorbidity, with mandatory CNS prophylaxis and response/MRD assessment.',src('ALL-4'),bph_front_opts,support=['ALL-C','ALL-D','ALL-E','ALL-F','ALL-G'],next_steps=['Response assessment','MRD assessment','Consolidation'],pathway_id='ALL_PH_POSITIVE_INITIAL')
    bph_mrdpos_opts=[
      opt('all_bph_mrdpos_blin_tki','Blinatumomab + TKI','Preferred for MRD-positive consolidation.',preference='PREFERRED',src=support_src(pkg,'ALL-4')),
      opt('all_bph_mrdpos_multi_tki','Multiagent therapy + TKI','Alternative consolidation.',src=support_src(pkg,'ALL-4')),
      opt('all_bph_mrdpos_tki','TKI','Alternative consolidation.',src=support_src(pkg,'ALL-4')),
      opt('all_bph_mrdpos_hct','Allogeneic HCT','Consider in appropriate candidates after response.',app=atom('transplant_candidate','eq',True),src=support_src(pkg,'ALL-4')),
      opt('all_bph_mrdpos_cns','CNS-directed/prophylactic intrathecal therapy','Required per ALL regimen and CNS status.',src=support_src(pkg,'ALL-B')),
    ]
    g.action('bph_mrdpos','Ph-positive B-ALL in marrow CR with persistent MRD: MRD-directed consolidation/escalation.',src('ALL-4'),bph_mrdpos_opts,support=['ALL-D','ALL-E','ALL-F','ALL-G'],next_steps=['Repeat MRD','ABL1 kinase-domain testing if indicated','HCT evaluation'],pathway_id='ALL_PH_POSITIVE_MRD_POSITIVE')
    bph_mrdneg_opts=[
      opt('all_bph_mrdneg_blin_tki','Blinatumomab + TKI','Post-remission option.',src=support_src(pkg,'ALL-4')),
      opt('all_bph_mrdneg_multi_tki','Continue multiagent therapy + TKI','Post-remission option.',src=support_src(pkg,'ALL-4')),
      opt('all_bph_mrdneg_tki','TKI','Post-remission option.',src=support_src(pkg,'ALL-4')),
      opt('all_bph_mrdneg_hct','Allogeneic HCT','For appropriate candidates.',app=atom('transplant_candidate','eq',True),src=support_src(pkg,'ALL-4')),
    ]
    g.action('bph_mrdneg','Ph-positive B-ALL in MRD-negative marrow CR: continue source-defined consolidation/maintenance with HCT for appropriate candidates.',src('ALL-4'),bph_mrdneg_opts,support=['ALL-D','ALL-F','ALL-G'],next_steps=['Surveillance after MRD-negative CR','TKI maintenance when applicable'],pathway_id='ALL_PH_POSITIVE_MRD_NEGATIVE')
    # Ph-negative B-ALL
    g.decision('bneg_phase','Post-induction/consolidation response assessment?',any_(atom('treatment_phase','eq','POST_INDUCTION'),atom('treatment_phase','eq','POST_CONSOLIDATION')),'bneg_response','bneg_initial',src('ALL-5'),'all_bneg_phase_response')
    g.decision('bneg_response','Marrow CR achieved?',atom('response_status','in',['CR','CR_WITH_MRD']),'bneg_mrd','rr_phnegative',src('ALL-5'),'all_bneg_marrow_cr')
    g.decision('bneg_mrd','MRD negative?',atom('mrd_status','eq','NEGATIVE'),'bneg_mrdneg','bneg_mrdpos_confirm',src('ALL-5'),'all_bneg_mrd')
    g.decision('bneg_mrdpos_confirm','MRD positive?',atom('mrd_status','eq','POSITIVE'),'bneg_mrdpos','need_mrd_bneg',src('ALL-5'),'all_bneg_mrd_positive')
    g.status('need_mrd_bneg','Current MRD status is required for Ph-negative B-ALL post-remission routing.','NEEDS_INFORMATION',src('ALL-5'))
    bneg_initial_opts=[
      opt('all_bneg_trial','Clinical trial','Preferred across age groups.',preference='PREFERRED',src=support_src(pkg,'ALL-D')),
      opt('all_bneg_calgb10403','CALGB 10403','Preferred for AYA without substantial comorbidities.',preference='PREFERRED',app=all_(atom('age_years','lt',40),atom('substantial_comorbidities','eq',False)),src=support_src(pkg,'ALL-D')),
      opt('all_bneg_dfci','DFCI ALL regimen','Preferred for AYA without substantial comorbidities.',preference='PREFERRED',app=all_(atom('age_years','lt',40),atom('substantial_comorbidities','eq',False)),src=support_src(pkg,'ALL-D')),
      opt('all_bneg_ecog1910','ECOG 1910','Other recommended for adults <65 without substantial comorbidities; also high-intensity option in older/comorbid patients.',preference='OTHER_RECOMMENDED',src=support_src(pkg,'ALL-D')),
      opt('all_bneg_hypercvad','HyperCVAD','Other recommended for <65 without substantial comorbidities.',preference='OTHER_RECOMMENDED',app=all_(atom('age_years','lt',65),atom('substantial_comorbidities','eq',False)),src=support_src(pkg,'ALL-D')),
      opt('all_bneg_low_vp','Vincristine + prednisone','Low-intensity older/comorbid option.',app=any_(atom('age_years','gte',65),atom('substantial_comorbidities','eq',True)),src=support_src(pkg,'ALL-D')),
      opt('all_bneg_pomp','POMP','Low-intensity older/comorbid option.',app=any_(atom('age_years','gte',65),atom('substantial_comorbidities','eq',True)),src=support_src(pkg,'ALL-D')),
      opt('all_bneg_inotuz_mini','Inotuzumab ozogamicin + mini-hyperCVD','Moderate-intensity older/comorbid option.',app=any_(atom('age_years','gte',65),atom('substantial_comorbidities','eq',True)),src=support_src(pkg,'ALL-D')),
      opt('all_bneg_minihypercvd','Mini-hyperCVD','Moderate-intensity older/comorbid option.',app=any_(atom('age_years','gte',65),atom('substantial_comorbidities','eq',True)),src=support_src(pkg,'ALL-D')),
    ]
    g.action('bneg_initial','Ph-negative B-ALL initial induction selected by age/fitness with CNS prophylaxis and planned response/MRD assessment.',src('ALL-5'),bneg_initial_opts,support=['ALL-C','ALL-D','ALL-E','ALL-F','ALL-G'],pathway_id='ALL_PH_NEGATIVE_INITIAL')
    g.action('bneg_mrdpos','Ph-negative B-ALL in marrow CR with MRD positivity: blinatumomab-based post-remission therapy with HCT consideration for high-risk/eligible patients.',src('ALL-5'),[
      opt('all_bneg_mrdpos_blin_multi','Blinatumomab + continued multiagent therapy','Preferred.',preference='PREFERRED'),
      opt('all_bneg_mrdpos_blin','Blinatumomab','Alternative when multiagent therapy is contraindicated.'),
      opt('all_bneg_mrdpos_hct','Allogeneic HCT','Especially with high-risk features.',app=atom('transplant_candidate','eq',True)),
    ],support=['ALL-D','ALL-F','ALL-G'],pathway_id='ALL_PH_NEGATIVE_MRD_POSITIVE')
    g.action('bneg_mrdneg','Ph-negative B-ALL in MRD-negative marrow CR: post-remission blinatumomab/continued multiagent therapy and maintenance or HCT according to risk/candidacy.',src('ALL-5'),[
      opt('all_bneg_mrdneg_blin_multi','Blinatumomab + continued multiagent therapy','Preferred.'),
      opt('all_bneg_mrdneg_blin','Blinatumomab','Alternative.'),
      opt('all_bneg_mrdneg_hct','Allogeneic HCT','Consider especially if high-risk.',app=all_(atom('transplant_candidate','eq',True),atom('poor_risk_b_all','eq',True))),
      opt('all_bneg_mrdneg_pomp','POMP maintenance','Post-remission maintenance option.'),
    ],support=['ALL-D','ALL-F','ALL-G'],pathway_id='ALL_PH_NEGATIVE_MRD_NEGATIVE')
    # T-ALL
    g.decision('t_phase','Post-induction/consolidation response assessment?',any_(atom('treatment_phase','eq','POST_INDUCTION'),atom('treatment_phase','eq','POST_CONSOLIDATION')),'t_response','t_initial',src('ALL-6'),'all_t_phase_response')
    g.decision('t_response','Marrow CR achieved?',atom('response_status','in',['CR','CR_WITH_MRD']),'t_mrd','rr_tall',src('ALL-6'),'all_t_marrow_cr')
    g.decision('t_mrd','MRD negative?',atom('mrd_status','eq','NEGATIVE'),'t_mrdneg','t_mrdpos_confirm',src('ALL-6'),'all_t_mrd')
    g.decision('t_mrdpos_confirm','MRD positive?',atom('mrd_status','eq','POSITIVE'),'t_mrdpos','need_mrd_t',src('ALL-6'),'all_t_mrd_positive')
    g.status('need_mrd_t','Current MRD status is required for T-ALL post-remission routing.','NEEDS_INFORMATION',src('ALL-6'))
    g.action('t_initial','T-ALL initial induction selected by age/fitness with CNS prophylaxis.',src('ALL-6'),[
      opt('all_t_trial','Clinical trial','Preferred.',preference='PREFERRED'),
      opt('all_t_calgb10403','CALGB 10403','Preferred for AYA without substantial comorbidities.',app=all_(atom('age_years','lt',40),atom('substantial_comorbidities','eq',False))),
      opt('all_t_cog0434','COG AALL0434','Preferred for AYA without substantial comorbidities.',app=all_(atom('age_years','lt',40),atom('substantial_comorbidities','eq',False))),
      opt('all_t_hypercvad','HyperCVAD','Other recommended for <65 without substantial comorbidities.',app=all_(atom('age_years','lt',65),atom('substantial_comorbidities','eq',False))),
      opt('all_t_graall','Dose-adjusted GRAALL-2014','Other recommended for adults <65 without substantial comorbidities.',app=all_(atom('age_years','lt',65),atom('substantial_comorbidities','eq',False))),
      opt('all_t_minihypercvd','Mini-hyperCVD','Moderate-intensity older/comorbid option.',app=any_(atom('age_years','gte',65),atom('substantial_comorbidities','eq',True))),
    ],support=['ALL-C','ALL-D','ALL-E','ALL-F','ALL-G'],pathway_id='ALL_T_INITIAL')
    g.action('t_mrdpos','T-ALL in marrow CR with MRD positivity: continue multiagent therapy and consider allogeneic HCT, particularly with high-risk disease or slow/incomplete MRD clearance.',src('ALL-6'),[
      opt('all_t_mrdpos_multi','Continue multiagent therapy'),
      opt('all_t_mrdpos_hct','Allogeneic HCT','Favored for high-risk T-ALL/slow MRD clearance.',app=atom('transplant_candidate','eq',True)),
    ],support=['ALL-D','ALL-F','ALL-G'],pathway_id='ALL_T_MRD_POSITIVE')
    g.action('t_mrdneg','T-ALL in MRD-negative marrow CR: continue multiagent therapy then maintenance or HCT when high-risk/appropriate.',src('ALL-6'),[
      opt('all_t_mrdneg_multi','Continue multiagent therapy'),
      opt('all_t_mrdneg_hct','Allogeneic HCT','For high-risk/appropriate candidates.',app=all_(atom('transplant_candidate','eq',True),atom('high_risk_t_all','eq',True))),
      opt('all_t_pomp','POMP maintenance'),
    ],support=['ALL-D','ALL-F','ALL-G'],pathway_id='ALL_T_MRD_NEGATIVE')
    # RR lineage router. CNS/extramedullary affects option set, but systemic therapy remains required.
    g.decision('rr_lineage','Relapsed/refractory B-ALL?',atom('lineage','eq','B_ALL'),'rr_b_ph','rr_t_lineage',src('ALL-8'),'all_rr_lineage_b')
    g.decision('rr_b_ph','Relapsed/refractory Ph-positive B-ALL?',atom('ph_status','eq','POSITIVE'),'rr_phplus','rr_phnegative_confirm',src('ALL-8'),'all_rr_b_ph')
    g.decision('rr_phnegative_confirm','Relapsed/refractory Ph-negative B-ALL?',atom('ph_status','eq','NEGATIVE'),'rr_phnegative','need_ph',src('ALL-8'),'all_rr_b_phneg')
    g.decision('rr_t_lineage','Relapsed/refractory T-ALL?',atom('lineage','eq','T_ALL'),'rr_tall','lineage_missing',src('ALL-8'),'all_rr_lineage_t')
    g.action('rr_phplus','Relapsed/refractory Ph-positive B-ALL: ABL1 mutation-directed TKI-based salvage with immunotherapy/cellular therapy and HCT consolidation when appropriate.',src('ALL-8'),[
      opt('all_rr_phplus_tki','Mutation-appropriate TKI','Asciminib +/- another TKI, bosutinib, dasatinib, imatinib, nilotinib, or ponatinib per mutation/tolerance.',preference='OTHER_RECOMMENDED'),
      opt('all_rr_phplus_blin','Blinatumomab +/- TKI','CD19-directed salvage.',app=atom('cd19_positive','eq',True)),
      opt('all_rr_phplus_inotuz','Inotuzumab ozogamicin +/- TKI','CD22-directed salvage.',app=atom('cd22_positive','eq',True)),
      opt('all_rr_phplus_tisa','Tisagenlecleucel','Age <26, refractory or >=2 relapses, after therapy including two TKIs.',app=all_(atom('age_years','lt',26),atom('prior_tki_count','gte',2),atom('cd19_positive','eq',True))),
      opt('all_rr_phplus_brexu','Brexucabtagene autoleucel','Following TKI therapy.',app=all_(atom('prior_tki_count','gte',1),atom('cd19_positive','eq',True))),
      opt('all_rr_phplus_obeca','Obecabtagene autoleucel','Following TKI therapy.',app=all_(atom('prior_tki_count','gte',1),atom('cd19_positive','eq',True))),
      opt('all_rr_phplus_hct','Allogeneic HCT after second remission','If eligible and appropriate.',app=atom('transplant_candidate','eq',True)),
      opt('all_rr_cns','CNS-directed therapy/prophylaxis','Systemic therapy is required even for isolated extramedullary relapse.',app=any_(atom('cns_involvement','eq',True),atom('extramedullary_disease','eq',True))),
    ],support=['ALL-B','ALL-D','ALL-F','ALL-G'],pathway_id='ALL_RR_PH_POSITIVE')
    g.action('rr_phnegative','Relapsed/refractory Ph-negative B-ALL: antigen/age/prior-treatment-directed immunotherapy or cellular therapy, other salvage regimens, and HCT consolidation when appropriate.',src('ALL-8'),[
      opt('all_rr_bneg_blin','Blinatumomab','Preferred; CD19-directed.',preference='PREFERRED',evidence='CATEGORY_1',app=atom('cd19_positive','eq',True)),
      opt('all_rr_bneg_inotuz','Inotuzumab ozogamicin','Preferred; CD22-directed.',preference='PREFERRED',evidence='CATEGORY_1',app=atom('cd22_positive','eq',True)),
      opt('all_rr_bneg_tisa','Tisagenlecleucel','Preferred for age <26 with refractory disease or >=2 relapses.',preference='PREFERRED',app=all_(atom('age_years','lt',26),atom('cd19_positive','eq',True))),
      opt('all_rr_bneg_brexu','Brexucabtagene autoleucel','Preferred CD19 CAR-T option.',preference='PREFERRED',app=atom('cd19_positive','eq',True)),
      opt('all_rr_bneg_obeca','Obecabtagene autoleucel','Preferred CD19 CAR-T option.',preference='PREFERRED',app=atom('cd19_positive','eq',True)),
      opt('all_rr_bneg_revumenib','Revumenib','For KMT2A-rearranged disease.',app=atom('kmt2a_rearranged','eq',True)),
      opt('all_rr_bneg_late_reuse','Consider initial regimen again','For late relapse >3 years.',app=atom('relapse_interval_years','gt',3)),
      opt('all_rr_bneg_hct','Allogeneic HCT after second remission','If eligible.',app=atom('transplant_candidate','eq',True)),
      opt('all_rr_bneg_cns','CNS-directed therapy/prophylaxis','For CNS/extramedullary involvement.',app=any_(atom('cns_involvement','eq',True),atom('extramedullary_disease','eq',True))),
    ],support=['ALL-B','ALL-D','ALL-F','ALL-G'],pathway_id='ALL_RR_PH_NEGATIVE')
    g.action('rr_tall','Relapsed/refractory T-ALL: clinical trial preferred; source-listed salvage regimens with molecularly directed therapy when applicable, CNS management, and HCT consolidation when appropriate.',src('ALL-8'),[
      opt('all_rr_t_trial','Clinical trial','Preferred.',preference='PREFERRED'),
      opt('all_rr_t_nelarabine','Nelarabine +/- etoposide/cyclophosphamide','Other recommended.'),
      opt('all_rr_t_bortezomib','Bortezomib-containing regimen','Other recommended.'),
      opt('all_rr_t_daratumumab','Daratumumab-containing regimen','Other recommended; category 2B.'),
      opt('all_rr_t_venetoclax','Venetoclax-containing regimen','Other recommended.'),
      opt('all_rr_t_revumenib','Revumenib','For KMT2A-rearranged disease.',app=atom('kmt2a_rearranged','eq',True)),
      opt('all_rr_t_late_reuse','Consider initial regimen again','For late relapse >3 years.',app=atom('relapse_interval_years','gt',3)),
      opt('all_rr_t_hct','Allogeneic HCT after second remission','If eligible.',app=atom('transplant_candidate','eq',True)),
      opt('all_rr_t_cns','CNS-directed therapy/prophylaxis','For CNS/extramedullary involvement.',app=any_(atom('cns_involvement','eq',True),atom('extramedullary_disease','eq',True))),
    ],support=['ALL-B','ALL-D','ALL-F','ALL-G'],pathway_id='ALL_RR_T')
    g.status('outside','Case is outside the acute lymphoblastic leukemia ruleset.','OUTSIDE_ENCODED_SCOPE',src('ALL-1'))
    # derived risk is intentionally deterministic, not extractable as a synthetic route variable.
    derived=[]
    # poor_risk_b_all remains optional direct fact here because full genomic mutation vector is not represented in compact schema; mark source ambiguity/schema limitation in report later.
    consistency=[
      {'id':'all_ph_positive_requires_b_lineage','when':all_(atom('ph_status','eq','POSITIVE'),atom('lineage','neq','B_ALL')),'message':'Ph-positive ALL branch is B-lineage-specific in this package.','source_pathways':['ALL-4']},
      {'id':'all_surveillance_active_relapse_conflict','when':all_(atom('treatment_phase','eq','SURVEILLANCE'),atom('response_status','in',['REFRACTORY','RELAPSED'])),'message':'Active relapse/refractory disease cannot remain on routine surveillance.','source_pathways':['ALL-7','ALL-8']},
    ]
    common_finalize(pkg,g,roles,derived_rules=derived,consistency_rules=consistency)
    save(name,pkg)


def aml_builder():
    name='nexus_acute_myeloid_leukemia_v5_2026.json'; pkg=load(name)
    additions=[
      fact('tp53_mutation_or_del17p','BOOLEAN',role='ROUTING'),
      fact('cardiac_issues','BOOLEAN',role='ROUTING'),
      fact('cns_involvement','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('induction_regimen','CODED',['CPX351','CYTARABINE_BASED','LOWER_INTENSITY','OTHER','UNKNOWN'],role='ROUTING'),
      fact('post_hct','BOOLEAN',role='ROUTING'),
      fact('relapse_interval_months','NUMERIC',role='OPTION_APPLICABILITY'),
      fact('tagraxofusp_eligible','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('pivekimab_eligible','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('prior_flt3_inhibitor','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('prior_targeted_therapy_resistance','BOOLEAN',role='OPTION_APPLICABILITY'),
    ]
    for f in additions: upsert_fact(pkg,f)
    roles={d['key']:'ROUTING' for d in pkg['fact_definitions']}
    for k in ['cd33_positive','flt3_mutation','idh1_mutation','idh2_mutation','npm1_mutation','kmt2a_rearranged','transplant_candidate','prior_hma','venetoclax_contraindicated','bpdc_n_cd123_positive','cns_involvement','tagraxofusp_eligible','pivekimab_eligible','prior_flt3_inhibitor','prior_targeted_therapy_resistance','relapse_interval_months']:
        roles[k]='OPTION_APPLICABILITY'
    roles['mrd_status']='ROUTING'; roles['response_status']='ROUTING'; roles['induction_regimen']='ROUTING'; roles['post_hct']='ROUTING'; roles['tp53_mutation_or_del17p']='ROUTING'; roles['cardiac_issues']='ROUTING'
    g=Graph(); src=lambda *x:list(x)
    g.decision('scope','AML/APL/BPDCN ruleset?',atom('cancer_type','eq','ACUTE_MYELOID_LEUKEMIA'),'family_bpdcn','outside',src('EVAL-1'),'aml_scope')
    g.decision('family_bpdcn','BPDCN?',atom('disease_family','eq','BPDCN'),'bpdcn_rr_state','family_apl',src('BPDCN-INTRO','BPDCN-1'),'aml_family_bpdcn')
    g.decision('family_apl','APL?',atom('disease_family','eq','APL'),'apl_rr_state','family_nonapl',src('EVAL-2','APL-1'),'aml_family_apl')
    g.decision('family_nonapl','Non-APL AML?',atom('disease_family','eq','NON_APL_AML'),'aml_care_rr','workup',src('EVAL-2','AML-1'),'aml_family_nonapl')
    g.action('workup','Complete AML diagnostic studies, cytogenetic/molecular characterization, CNS/extramedullary evaluation when indicated, and early transplant planning before treatment routing.',src('EVAL-1','EVAL-2','EVAL-2A'),[
      opt('aml_workup_molecular','AML molecular/cytogenetic profiling','Includes ELN-driving and immediately actionable lesions.'),
      opt('aml_workup_hct','Early HCT referral/HLA typing','For patients with potential future HCT.'),
      opt('aml_workup_cns','CNS evaluation','Lumbar puncture/imaging when clinically indicated.',app=atom('cns_involvement','eq',True),decision_relevant=False),
    ],support=['AML-A','AML-B','AML-F'],pathway_id='AML_WORKUP')
    # BPDCN
    g.decision('bpdcn_rr_state','Relapsed/refractory BPDCN?',atom('treatment_phase','eq','RELAPSED_REFRACTORY'),'bpdcn_rr','bpdcn_initial_response',src('BPDCN-4'),'aml_bpdcn_rr_state')
    g.decision('bpdcn_initial_response','Post-induction BPDCN response assessment?',atom('treatment_phase','eq','POST_INDUCTION'),'bpdcn_response','bpdcn_initial',src('BPDCN-2','BPDCN-3'),'aml_bpdcn_postind')
    g.decision('bpdcn_response','Complete response after BPDCN induction?',atom('response_status','in',['CR','CRH_CRI','MLFS']),'bpdcn_cr','bpdcn_rr',src('BPDCN-2','BPDCN-3'),'aml_bpdcn_response')
    g.action('bpdcn_initial','BPDCN induction: select CD123-directed therapy when expression/eligibility support it, otherwise intensive/lower-intensity chemotherapy; all patients receive CNS-directed prophylaxis/treatment.',src('BPDCN-1','BPDCN-2','BPDCN-3','BPDCN-3A'),[
      opt('bpdcn_tagrax','Tagraxofusp-erzs','CD123-directed option when CD123 is expressed and eligibility criteria are met.',app=all_(atom('bpdc_n_cd123_positive','eq',True),atom('tagraxofusp_eligible','eq',True)),src=support_src(pkg,'BPDCN-2')),
      opt('bpdcn_pivekimab','Pivekimab sunirine-pvzy','CD123-directed option when CD123 is expressed and exclusion criteria are absent.',app=all_(atom('bpdc_n_cd123_positive','eq',True),atom('pivekimab_eligible','eq',True)),src=support_src(pkg,'BPDCN-2')),
      opt('bpdcn_hypercvad','HyperCVAD','Intensive chemotherapy option.',src=support_src(pkg,'BPDCN-3')),
      opt('bpdcn_aml_induction','AML-type 7+3 induction','Intensive chemotherapy option.',src=support_src(pkg,'BPDCN-3')),
      opt('bpdcn_chop','CHOP','Lymphoma-type induction option.',src=support_src(pkg,'BPDCN-3')),
      opt('bpdcn_hma_ven','HMA + venetoclax','Lower-intensity option.',src=support_src(pkg,'BPDCN-3')),
      opt('bpdcn_it','Intrathecal chemotherapy','For documented CNS disease and prophylaxis.',src=support_src(pkg,'BPDCN-B')),
    ],support=['BPDCN-A','BPDCN-B','BPDCN-C'],pathway_id='BPDCN_INITIAL')
    g.action('bpdcn_cr','BPDCN complete response after induction: transplant consolidation preferred when eligible; otherwise continue source-defined therapy/monitoring.',src('BPDCN-2','BPDCN-3'),[
      opt('bpdcn_cr_allohct','Allogeneic HCT','Preferred in appropriate responders.',preference='PREFERRED',app=atom('transplant_candidate','eq',True)),
      opt('bpdcn_cr_autohct','Autologous HCT','Other recommended in selected patients.',app=atom('transplant_candidate','eq',True)),
      opt('bpdcn_cr_continue','Continue induction agent until progression/unacceptable toxicity','When transplant is not performed.'),
    ],support=['BPDCN-A','BPDCN-C'],next_steps=['Surveillance BPDCN-4'],pathway_id='BPDCN_CR')
    g.action('bpdcn_rr','Relapsed/refractory BPDCN: clinical trial preferred; use eligible CD123-directed therapy not rendered inappropriate by expression/exclusions, alternative chemotherapy/local RT, and donor search/HCT planning in appropriate patients.',src('BPDCN-4'),[
      opt('bpdcn_rr_trial','Clinical trial','Preferred.',preference='PREFERRED'),
      opt('bpdcn_rr_pivekimab','Pivekimab sunirine-pvzy','Requires CD123 expression/eligibility.',app=all_(atom('bpdc_n_cd123_positive','eq',True),atom('pivekimab_eligible','eq',True))),
      opt('bpdcn_rr_tagrax','Tagraxofusp-erzs','Requires CD123 expression/eligibility.',app=all_(atom('bpdc_n_cd123_positive','eq',True),atom('tagraxofusp_eligible','eq',True))),
      opt('bpdcn_rr_chemo','Chemotherapy not already used'),
      opt('bpdcn_rr_hma_ven','HMA + venetoclax'),
      opt('bpdcn_rr_rt','Local RT to isolated lesions/areas'),
      opt('bpdcn_rr_hct','Donor search / allogeneic HCT planning','For appropriate candidates.',app=atom('transplant_candidate','eq',True)),
    ],support=['BPDCN-A','BPDCN-B','BPDCN-C'],pathway_id='BPDCN_RR')
    # APL
    g.decision('apl_rr_state','Relapsed APL?',atom('treatment_phase','eq','RELAPSED_REFRACTORY'),'apl_relapse','apl_postcon',src('APL-6'),'aml_apl_rr')
    g.decision('apl_postcon','Post-consolidation/monitoring phase?',any_(atom('treatment_phase','eq','POST_CONSOLIDATION'),atom('treatment_phase','eq','MAINTENANCE'),atom('treatment_phase','eq','SURVEILLANCE')),'apl_monitor','apl_postind',src('APL-5'),'aml_apl_postcon')
    g.decision('apl_postind','Post-induction APL response phase?',atom('treatment_phase','eq','POST_INDUCTION'),'apl_consolidation','apl_risk',src('APL-2','APL-3','APL-4'),'aml_apl_postind')
    g.decision('apl_risk','High-risk APL by WBC >10 x10^9/L?',atom('wbc_count','gt',10),'apl_high_cardiac','apl_low',src('APL-1'),'aml_apl_wbc_risk')
    g.decision('apl_high_cardiac','Cardiac issues affecting high-risk APL regimen?',atom('cardiac_issues','eq',True),'apl_high_card','apl_high',src('APL-1','APL-4'),'aml_apl_cardiac')
    g.action('apl_low','Low-risk APL: ATRA + arsenic trioxide-based induction/consolidation, with source-defined alternatives when arsenic is unavailable/contraindicated.',src('APL-1','APL-2'),[
      opt('apl_low_atra_ato_daily','ATRA + daily arsenic trioxide','Category 1.',preference='PREFERRED',evidence='CATEGORY_1'),
      opt('apl_low_atra_ato_intermit','ATRA + intermittent arsenic trioxide','Category 1.',evidence='CATEGORY_1'),
      opt('apl_low_atra_ida','ATRA + idarubicin','Useful if arsenic unavailable/contraindicated.',evidence='CATEGORY_1'),
      opt('apl_low_atra_go','ATRA + gemtuzumab ozogamicin','Useful if arsenic unavailable/contraindicated.'),
    ],support=['APL-A','APL-B'],next_steps=['Bone marrow response assessment','Consolidation per protocol','Post-consolidation molecular monitoring'],pathway_id='APL_LOW_RISK')
    g.action('apl_high','High-risk APL without cardiac contraindication: ATRA plus arsenic/anthracycline/cytarabine/GO source regimens, followed by protocol-consistent consolidation.',src('APL-1','APL-3'),[
      opt('apl_high_atra_ida_ato','ATRA + idarubicin + arsenic trioxide','Preferred regimen.'),
      opt('apl_high_atra_daily_ato_go','ATRA + daily arsenic trioxide + gemtuzumab ozogamicin','Preferred regimen.'),
      opt('apl_high_atra_inter_ato_go','ATRA + intermittent arsenic trioxide + gemtuzumab ozogamicin','Preferred regimen.'),
      opt('apl_high_atra_dauno_cyt','ATRA + daunorubicin + cytarabine','Useful when arsenic unavailable/contraindicated.'),
      opt('apl_high_atra_ida','ATRA + idarubicin','Useful when arsenic unavailable/contraindicated.'),
    ],support=['APL-A','APL-B'],pathway_id='APL_HIGH_RISK')
    g.action('apl_high_card','High-risk APL with cardiac issues: use the dedicated cardiac-issue induction pathway and protocol-consistent consolidation.',src('APL-4'),[
      opt('apl_high_card_ato_atra_go','ATRA + arsenic trioxide + gemtuzumab ozogamicin-based approach','Cardiac-issue pathway per APL-4.'),
    ],support=['APL-A','APL-B'],pathway_id='APL_HIGH_RISK_CARDIAC')
    g.action('apl_consolidation','APL after induction response: continue the same protocol-specific consolidation strategy; molecular positivity immediately post-induction alone does not redirect therapy.',src('APL-2','APL-3','APL-4'),[
      opt('apl_consolidation_protocol','Protocol-consistent consolidation','Do not mix induction/consolidation components from different source protocols.'),
    ],support=['APL-B'],next_steps=['Post-consolidation molecular assessment'],pathway_id='APL_CONSOLIDATION')
    g.action('apl_monitor','APL post-consolidation: molecular monitoring and regimen/risk-specific maintenance only when source-defined.',src('APL-5'),[
      opt('apl_monitor_molecular','Molecular monitoring'),
      opt('apl_monitor_maintenance','Maintenance therapy','Only for source-defined regimen/risk situations.',decision_relevant=False),
    ],support=['APL-B'],pathway_id='APL_MONITORING')
    g.action('apl_relapse','Relapsed APL: salvage selected by prior ATRA/ATO exposure and molecular response, followed by consolidation/transplant strategy.',src('APL-6'),[
      opt('apl_rel_salvage','APL salvage therapy','Select ATO/ATRA/anthracycline/GO-based salvage according to prior exposure.'),
      opt('apl_rel_hct','Transplant consolidation','According to molecular response and eligibility.',app=atom('transplant_candidate','eq',True)),
    ],support=['APL-A','APL-B'],pathway_id='APL_RELAPSE')
    # Non-APL AML care-state priority
    g.decision('aml_care_rr','Relapsed/refractory AML?',any_(atom('treatment_phase','eq','RELAPSED_REFRACTORY'),atom('response_status','in',['REFRACTORY','RELAPSED'])),'rr_npm1','aml_postind_state',src('AML-8','AML-9'),'aml_rr_state')
    g.decision('aml_postind_state','Post-induction assessment?',atom('treatment_phase','eq','POST_INDUCTION'),'postind_response','aml_postcon_state',src('AML-3','AML-5'),'aml_postind_state')
    g.decision('aml_postcon_state','Post-consolidation/maintenance/surveillance state?',any_(atom('treatment_phase','eq','POST_CONSOLIDATION'),atom('treatment_phase','eq','MAINTENANCE'),atom('treatment_phase','eq','SURVEILLANCE')),'maintenance_router','aml_new_state',src('AML-7','AML-8'),'aml_postcon_state')
    g.decision('aml_new_state','New-diagnosis AML?',atom('treatment_phase','eq','NEW_DIAGNOSIS'),'intensive_elig','workup',src('AML-1','AML-2','AML-4'),'aml_new_state')
    g.decision('intensive_elig','Eligible for intensive induction?',atom('intensive_induction_eligible','eq',True),'intensive_tp53','lower_idh1',src('AML-1','AML-2','AML-4'),'aml_intensive_eligibility')
    g.decision('intensive_tp53','TP53 mutation or del(17p) adverse-risk state?',atom('tp53_mutation_or_del17p','eq',True),'tp53_trial','intensive_mrc',src('AML-2'),'aml_tp53')
    g.action('tp53_trial','Intensive-eligible AML with TP53 mutation/del(17p): clinical trial is the source-preferred strategy; other source-listed intensive/lower-intensity regimens remain alternatives.',src('AML-2'),[
      opt('aml_tp53_trial','Clinical trial','Preferred.',preference='PREFERRED'),
      opt('aml_tp53_7_3','Standard 7+3','Other recommended.'),
      opt('aml_tp53_cpx','CPX-351','Other recommended; category 2B.'),
      opt('aml_tp53_aza_ven','Azacitidine + venetoclax','Other recommended.'),
      opt('aml_tp53_dec_ven','Decitabine + venetoclax','Other recommended.'),
    ],support=['AML-A','AML-E','AML-F'],pathway_id='AML_TP53_ADVERSE')
    g.decision('intensive_mrc','Therapy-related AML / antecedent MDS-CMML / MDS-related biology?',atom('therapy_related_or_mrc','eq',True),'mrc_age','intensive_cbf',src('AML-2'),'aml_mrc_biology')
    g.decision('mrc_age','Age >=60?',atom('age_ge_60','eq',True),'mrc_age60','mrc_lt60',src('AML-2'),'aml_mrc_age')
    g.action('mrc_age60','Therapy-related/MDS-related AML age >=60 and intensive-eligible: CPX-351 is preferred; source-listed alternatives remain available.',src('AML-2'),[
      opt('aml_mrc60_cpx','CPX-351','Preferred; category 1.',preference='PREFERRED',evidence='CATEGORY_1'),
      opt('aml_mrc60_7_3','Standard 7+3','Other recommended.'),
      opt('aml_mrc60_aza_ven','Azacitidine + venetoclax','Other recommended.'),
      opt('aml_mrc60_dec_ven','Decitabine + venetoclax','Other recommended.'),
    ],support=['AML-E','AML-F'],pathway_id='AML_MRC_AGE60')
    g.action('mrc_lt60','Therapy-related/MDS-related AML age <60 and intensive-eligible: standard 7+3 is preferred; CPX-351 and source-listed alternatives are options.',src('AML-2'),[
      opt('aml_mrclt60_7_3','Standard 7+3','Preferred.',preference='PREFERRED'),
      opt('aml_mrclt60_cpx','CPX-351','Other recommended.'),
      opt('aml_mrclt60_aza_ven','Azacitidine + venetoclax','Other recommended.'),
    ],support=['AML-E','AML-F'],pathway_id='AML_MRC_LT60')
    g.decision('intensive_cbf','Core-binding-factor AML?',atom('cbf_aml','eq',True),'cbf_options','intensive_adverse',src('AML-1'),'aml_cbf')
    g.action('cbf_options','CBF AML intensive induction: standard 7+3 with gemtuzumab is preferred when CD33-positive; other cytarabine-based options and FLT3-directed additions apply when appropriate.',src('AML-1'),[
      opt('aml_cbf_7_3_go','7+3 + gemtuzumab ozogamicin','Preferred when CD33-positive.',preference='PREFERRED',app=atom('cd33_positive','eq',True)),
      opt('aml_cbf_7_3','Standard 7+3','Other recommended.'),
      opt('aml_cbf_flagida_go','FLAG-IDA + gemtuzumab ozogamicin','Other recommended; CD33-positive.',app=atom('cd33_positive','eq',True)),
      opt('aml_cbf_midostaurin','7+3 + midostaurin','For FLT3-ITD or TKD.',app=atom('flt3_mutation','eq',True)),
      opt('aml_cbf_quizartinib','7+3 + quizartinib','For FLT3-ITD; package fact represents FLT3 mutation and requires subtype confirmation clinically.',app=atom('flt3_mutation','eq',True)),
    ],support=['AML-A','AML-E'],next_steps=['AML-3 response assessment'],pathway_id='AML_CBF_INITIAL')
    g.decision('intensive_adverse','ELN adverse-risk AML?',atom('eln_risk','eq','ADVERSE'),'adverse_options','nonadverse_options',src('AML-1','AML-2'),'aml_eln_adverse')
    g.action('adverse_options','Intensive-eligible adverse-risk non-APL AML without the separately handled TP53/MDS-related states: source-listed intensive induction with early HCT planning.',src('AML-2'),[
      opt('aml_adv_trial','Clinical trial','Strong consideration.'),
      opt('aml_adv_7_3','Standard 7+3'),
      opt('aml_adv_cpx','CPX-351','When source biology criteria apply.',app=atom('therapy_related_or_mrc','eq',True)),
      opt('aml_adv_aza_ven','Azacitidine + venetoclax'),
      opt('aml_adv_dec_ven','Decitabine + venetoclax'),
      opt('aml_adv_hct_plan','Early allogeneic HCT planning','If candidate.',app=atom('transplant_candidate','eq',True)),
    ],support=['AML-A','AML-E','AML-F'],pathway_id='AML_ADVERSE_INITIAL')
    g.action('nonadverse_options','Intensive-eligible favorable/intermediate non-CBF AML: standard intensive induction with mutation/CD33-directed additions where source-defined.',src('AML-1'),[
      opt('aml_nonadv_7_3','Standard 7+3','Preferred/other recommended according to risk group.'),
      opt('aml_nonadv_go','7+3 + gemtuzumab ozogamicin','For CD33-positive disease where source-listed.',app=atom('cd33_positive','eq',True)),
      opt('aml_nonadv_midostaurin','7+3 + midostaurin','FLT3-mutated.',app=atom('flt3_mutation','eq',True)),
      opt('aml_nonadv_quiz','7+3 + quizartinib','FLT3-ITD-specific option; verify FLT3 subtype.',app=atom('flt3_mutation','eq',True)),
      opt('aml_nonadv_hct_plan','HCT planning','Risk/MRD dependent.',app=atom('transplant_candidate','eq',True)),
    ],support=['AML-A','AML-E'],pathway_id='AML_NONADVERSE_INITIAL')
    # lower-intensity detailed option applicability
    g.decision('lower_idh1','IDH1-mutated AML?',atom('idh1_mutation','eq',True),'lower_idh1_action','lower_noidh1',src('AML-4'),'aml_lower_idh1')
    g.action('lower_idh1_action','AML not receiving intensive induction with IDH1 mutation: exact lower-intensity source options filtered by HMA exposure and venetoclax suitability.',src('AML-4','AML-4A'),[
      opt('aml_low_idh1_aza_ven','Azacitidine + venetoclax','Preferred.',preference='PREFERRED',app=atom('venetoclax_contraindicated','eq',False)),
      opt('aml_low_idh1_aza_ivo','Azacitidine + ivosidenib','Preferred.',preference='PREFERRED'),
      opt('aml_low_idh1_dec_ven','Decitabine + venetoclax','Preferred.',preference='PREFERRED',app=atom('venetoclax_contraindicated','eq',False)),
      opt('aml_low_idh1_ivo','Ivosidenib','Other recommended.'),
      opt('aml_low_idh1_oraldec_ven','Oral decitabine/cedazuridine + venetoclax','Other recommended.',app=atom('venetoclax_contraindicated','eq',False)),
      opt('aml_low_idh1_ldac_ven','LDAC + venetoclax','Useful after prior HMA exposure.',app=all_(atom('prior_hma','eq',True),atom('venetoclax_contraindicated','eq',False))),
      opt('aml_low_idh1_hma_alone','Azacitidine or decitabine','Useful when venetoclax contraindicated.',app=atom('venetoclax_contraindicated','eq',True)),
      opt('aml_low_idh1_oluta','Olutasidenib','Useful when not eligible for preferred regimen/ivosidenib context.'),
    ],support=['AML-E','AML-J'],next_steps=['AML-5 response assessment'],pathway_id='AML_LOWER_IDH1')
    g.action('lower_noidh1','AML not receiving intensive induction without IDH1 mutation: exact lower-intensity options filtered by prior HMA exposure, venetoclax suitability, FLT3/IDH2/CD33.',src('AML-4','AML-4A'),[
      opt('aml_low_aza_ven','Azacitidine + venetoclax','Preferred.',preference='PREFERRED',app=atom('venetoclax_contraindicated','eq',False)),
      opt('aml_low_dec_ven','Decitabine + venetoclax','Preferred.',preference='PREFERRED',app=atom('venetoclax_contraindicated','eq',False)),
      opt('aml_low_oraldec_ven','Oral decitabine/cedazuridine + venetoclax','Other recommended.',app=atom('venetoclax_contraindicated','eq',False)),
      opt('aml_low_ldac_ven','LDAC + venetoclax','Useful after prior HMA exposure.',app=all_(atom('prior_hma','eq',True),atom('venetoclax_contraindicated','eq',False))),
      opt('aml_low_hma_alone','Azacitidine or decitabine','Useful when venetoclax contraindicated.',app=atom('venetoclax_contraindicated','eq',True)),
      opt('aml_low_ldac','LDAC','Useful after prior HMA or when venetoclax contraindicated.',app=any_(atom('prior_hma','eq',True),atom('venetoclax_contraindicated','eq',True))),
      opt('aml_low_gilteritinib','Gilteritinib +/- azacitidine','FLT3-mutated, not eligible for preferred regimen.',app=atom('flt3_mutation','eq',True)),
      opt('aml_low_enasidenib','Enasidenib +/- azacitidine','IDH2-mutated, not eligible for preferred regimen.',app=atom('idh2_mutation','eq',True)),
      opt('aml_low_go','Gemtuzumab ozogamicin','CD33-positive, not eligible for preferred regimen.',app=atom('cd33_positive','eq',True)),
    ],support=['AML-E','AML-J'],next_steps=['AML-5 response assessment'],pathway_id='AML_LOWER_NO_IDH1')
    # Post induction: intensive vs lower intensity by induction regimen
    g.decision('postind_response','Response/remission achieved after induction?',atom('response_status','in',['CR','CRH_CRI','MLFS']),'postind_remission','postind_noresponse',src('AML-3','AML-5'),'aml_postind_response')
    g.decision('postind_remission','Was lower-intensity induction used?',atom('induction_regimen','eq','LOWER_INTENSITY'),'lower_response_hct','consol_risk',src('AML-5','AML-6'),'aml_postind_regimen')
    g.decision('lower_response_hct','Transplant candidate with donor/appropriate first-remission plan?',atom('transplant_candidate','eq',True),'lower_hct','lower_continue',src('AML-5'),'aml_lower_response_hct')
    g.action('lower_hct','Response after lower-intensity AML therapy with HCT candidacy: proceed to allogeneic HCT in first remission when appropriate.',src('AML-5'),[opt('aml_lower_hct','Allogeneic HCT','For eligible patients with available donor.')],support=['AML-F','AML-H'],pathway_id='AML_LOWER_RESPONSE_HCT')
    g.action('lower_continue','Response after lower-intensity AML therapy without immediate HCT: continue the induction lower-intensity regimen, with MRD/response monitoring and maintenance transition as appropriate.',src('AML-5'),[opt('aml_lower_continue','Continue lower-intensity induction regimen')],support=['AML-H','AML-J'],next_steps=['AML-7/AML-8 as appropriate'],pathway_id='AML_LOWER_RESPONSE_CONTINUE')
    g.decision('postind_noresponse','Lower-intensity induction with no response/progression?',atom('induction_regimen','eq','LOWER_INTENSITY'),'lower_noresp','intensive_reind_cpx',src('AML-3','AML-5'),'aml_postind_noresponse_regimen')
    g.action('lower_noresp','No response/progression after lower-intensity AML therapy: relapsed/refractory therapy or best supportive care; do not silently continue ineffective therapy.',src('AML-5'),[
      opt('aml_lower_noresp_rr','Relapsed/refractory AML therapy','See AML-9 targeted/salvage options.'),
      opt('aml_lower_noresp_bsc','Best supportive care'),
    ],support=['AML-E','AML-F'],pathway_id='AML_LOWER_NO_RESPONSE')
    g.decision('intensive_reind_cpx','Was CPX-351 used during induction?',atom('induction_regimen','eq','CPX351'),'reind_cpx','reind_other',src('AML-3'),'aml_reind_cpx')
    g.action('reind_cpx','Persistent disease after CPX-351 induction: CPX-351 reinduction is source-supported only because CPX-351 was used initially; alternative salvage/AML-9 options remain.',src('AML-3'),[
      opt('aml_reind_cpx351','CPX-351 reinduction','Only if CPX-351 used in induction.'),
      opt('aml_reind_cpx_rr','AML-9 salvage/targeted therapy'),
    ],support=['AML-E'],pathway_id='AML_REIND_CPX')
    g.action('reind_other','Persistent/refractory disease after non-CPX intensive induction: source-listed reinduction/salvage selected by prior regimen and actionable biology.',src('AML-3','AML-9'),[
      opt('aml_reind_cytarabine','Cytarabine-based reinduction'),
      opt('aml_reind_7_3','7+3 / 5+2 reinduction'),
      opt('aml_reind_hma_ven','HMA + venetoclax','If appropriate.'),
      opt('aml_reind_targeted','Mutation-directed AML-9 therapy','If actionable mutation is present.',app=any_(atom('flt3_mutation','eq',True),atom('idh1_mutation','eq',True),atom('idh2_mutation','eq',True),atom('npm1_mutation','eq',True),atom('kmt2a_rearranged','eq',True),atom('cd33_positive','eq',True))),
    ],support=['AML-E','AML-J'],pathway_id='AML_REIND_OTHER')
    # consolidation risk/MRD/transplant
    g.decision('consol_risk','Favorable-risk AML?',atom('eln_risk','eq','FAVORABLE'),'consol_fav_mrd','consol_flt3',src('AML-6','AML-6A'),'aml_consol_risk_fav')
    g.decision('consol_fav_mrd','MRD positive/high-risk feature despite favorable-risk AML?',atom('mrd_status','eq','POSITIVE'),'consol_fav_hct','consol_fav',src('AML-6','AML-6A'),'aml_consol_fav_mrd')
    g.action('consol_fav_hct','Favorable-risk AML with MRD positivity/high-risk feature: consider allogeneic HCT rather than routine favorable-risk consolidation alone.',src('AML-6','AML-6A'),[
      opt('aml_consol_fav_hct','Allogeneic HCT','When eligible.',app=atom('transplant_candidate','eq',True)),
      opt('aml_consol_fav_cyt','Cytarabine-based consolidation','May be used while donor search/when HCT not pursued.'),
    ],support=['AML-H'],pathway_id='AML_CONSOL_FAV_MRD_POS')
    g.action('consol_fav','Favorable-risk AML in remission without MRD positivity: cytarabine-based consolidation with gemtuzumab continuation only when appropriate from induction.',src('AML-6','AML-6A'),[
      opt('aml_consol_fav_cyt','Cytarabine-based consolidation'),
      opt('aml_consol_fav_go','Cytarabine +/- gemtuzumab ozogamicin','CD33-positive and only if GO was used during induction.',app=atom('cd33_positive','eq',True)),
    ],support=['AML-H'],pathway_id='AML_CONSOL_FAVORABLE')
    g.decision('consol_flt3','FLT3-mutated AML?',atom('flt3_mutation','eq',True),'consol_flt3_action','consol_other_risk',src('AML-6'),'aml_consol_flt3')
    g.action('consol_flt3_action','FLT3-mutated AML in remission: allogeneic HCT is preferred for FLT3-ITD when appropriate; cytarabine plus mutation-appropriate FLT3 inhibitor is an alternative.',src('AML-6'),[
      opt('aml_consol_flt3_hct','Allogeneic HCT','Preferred for FLT3-ITD in eligible patients.',preference='PREFERRED',app=atom('transplant_candidate','eq',True)),
      opt('aml_consol_flt3_mido','Cytarabine + midostaurin','FLT3-ITD or TKD.'),
      opt('aml_consol_flt3_quiz','Cytarabine + quizartinib','FLT3-ITD only; subtype must be confirmed.'),
    ],support=['AML-H'],pathway_id='AML_CONSOL_FLT3')
    g.decision('consol_other_risk','Adverse-risk AML?',atom('eln_risk','eq','ADVERSE'),'consol_adverse','consol_intermediate',src('AML-6'),'aml_consol_adverse')
    g.action('consol_adverse','Adverse/poor-risk AML in remission: allogeneic HCT preferred when eligible; regimen-specific consolidation/continuation when HCT is not immediate.',src('AML-6'),[
      opt('aml_consol_adv_hct','Allogeneic HCT','Preferred.',preference='PREFERRED',app=atom('transplant_candidate','eq',True)),
      opt('aml_consol_adv_cyt','Cytarabine-based consolidation'),
      opt('aml_consol_adv_cpx','CPX-351 consolidation','Only if CPX-351 was used in induction.',app=atom('induction_regimen','eq','CPX351')),
      opt('aml_consol_adv_lower','Continue lower-intensity regimen','If lower-intensity induction was used.',app=atom('induction_regimen','eq','LOWER_INTENSITY')),
    ],support=['AML-H'],pathway_id='AML_CONSOL_ADVERSE')
    g.action('consol_intermediate','Intermediate-risk AML in remission: consider allogeneic HCT vs cytarabine-based consolidation according to candidacy and MRD/risk.',src('AML-6'),[
      opt('aml_consol_int_hct','Allogeneic HCT','For eligible patients.',app=atom('transplant_candidate','eq',True)),
      opt('aml_consol_int_cyt','Cytarabine-based consolidation'),
    ],support=['AML-H'],pathway_id='AML_CONSOL_INTERMEDIATE')
    # maintenance/surveillance
    g.decision('maintenance_router','Post-allogeneic HCT?',atom('post_hct','eq',True),'maintenance_posthct','maintenance_nohct',src('AML-7','AML-8'),'aml_maintenance_posthct')
    g.decision('maintenance_posthct','History of FLT3 mutation?',atom('flt3_mutation','eq',True),'maintenance_flt3_hct','maintenance_highrisk_hct',src('AML-7'),'aml_posthct_flt3')
    g.action('maintenance_flt3_hct','Post-allogeneic-HCT AML in remission with FLT3 mutation: FLT3-inhibitor maintenance options according to mutation subtype/MRD.',src('AML-7'),[
      opt('aml_mnt_gilteritinib','Gilteritinib','Preferred for FLT3-ITD in CR1 without pre-transplant MRD negativity.'),
      opt('aml_mnt_sorafenib','Sorafenib','FLT3-ITD only.'),
      opt('aml_mnt_midostaurin','Midostaurin','FLT3-ITD or TKD.'),
      opt('aml_mnt_quizartinib','Quizartinib','FLT3-ITD only.'),
    ],support=['AML-H'],pathway_id='AML_POSTHCT_FLT3_MAINT')
    g.action('maintenance_highrisk_hct','Post-allogeneic-HCT AML in remission without FLT3-directed maintenance indication: source-defined high-risk maintenance may be considered; otherwise surveillance.',src('AML-7','AML-8'),[
      opt('aml_mnt_lowdec_gcsf','Low-dose decitabine + G-CSF','Category 2B in high-risk post-HCT context.'),
      opt('aml_mnt_surveillance','Surveillance'),
    ],support=['AML-H'],pathway_id='AML_POSTHCT_MAINT')
    g.decision('maintenance_nohct','Non-CBF AML after intensive chemotherapy, in remission, with no planned HCT?',all_(atom('cbf_aml','eq',False),atom('transplant_candidate','eq',False)),'maintenance_oralaza','surveillance_aml',src('AML-7','AML-8'),'aml_nonhct_maintenance')
    g.action('maintenance_oralaza','Non-CBF AML in remission after intensive chemotherapy with no planned HCT: oral azacitidine maintenance may be used; surveillance remains part of follow-up.',src('AML-7'),[
      opt('aml_mnt_oralaza','Oral azacitidine until progression/unacceptable toxicity','Category 1 for age >=55; verify age criteria clinically.'),
      opt('aml_mnt_hma12','Azacitidine or decitabine up to 12 cycles','Useful when oral azacitidine cannot be used.'),
    ],support=['AML-H'],pathway_id='AML_ORAL_AZA_MAINT')
    g.action('surveillance_aml','AML surveillance after completion of consolidation/maintenance: CBC-based follow-up, marrow testing when indicated, and molecular monitoring where applicable.',src('AML-8'),[
      opt('aml_surv_schedule','CBC/platelets surveillance schedule'),
      opt('aml_surv_mrd','Molecular/MRD monitoring when applicable'),
    ],support=['AML-H','AML-I'],pathway_id='AML_SURVEILLANCE')
    # RR targeted hierarchy to ensure all source mutations affect options
    g.decision('rr_npm1','NPM1-mutated relapsed/refractory AML?',atom('npm1_mutation','eq',True),'rr_npm1_action','rr_kmt2a',src('AML-9'),'aml_rr_npm1')
    g.decision('rr_kmt2a','KMT2A-rearranged relapsed/refractory AML?',atom('kmt2a_rearranged','eq',True),'rr_kmt2a_action','rr_flt3',src('AML-9'),'aml_rr_kmt2a')
    g.decision('rr_flt3','FLT3-mutated relapsed/refractory AML?',atom('flt3_mutation','eq',True),'rr_flt3_action','rr_idh1',src('AML-9'),'aml_rr_flt3')
    g.decision('rr_idh1','IDH1-mutated relapsed/refractory AML?',atom('idh1_mutation','eq',True),'rr_idh1_action','rr_idh2',src('AML-9'),'aml_rr_idh1')
    g.decision('rr_idh2','IDH2-mutated relapsed/refractory AML?',atom('idh2_mutation','eq',True),'rr_idh2_action','rr_cd33',src('AML-9'),'aml_rr_idh2')
    g.decision('rr_cd33','CD33-positive relapsed/refractory AML?',atom('cd33_positive','eq',True),'rr_cd33_action','rr_other',src('AML-9'),'aml_rr_cd33')
    def rr_common(extra):
      return extra+[
        opt('aml_rr_trial','Clinical trial','Strongly preferred.',preference='PREFERRED'),
        opt('aml_rr_intensive','Intensive salvage chemotherapy','For appropriate patients.'),
        opt('aml_rr_lessint','Less-intensive therapy','HMA/LDAC +/- venetoclax as appropriate; prior HMA exposure matters.',app=atom('prior_hma','eq',False)),
        opt('aml_rr_hct','Allogeneic HCT after remission','For eligible patients.',app=atom('transplant_candidate','eq',True)),
      ]
    g.action('rr_npm1_action','Relapsed/refractory NPM1-mutated AML: NPM1-directed menin-inhibitor options plus source salvage/HCT strategy.',src('AML-8','AML-9'),rr_common([
      opt('aml_rr_revumenib_npm1','Revumenib','NPM1-mutated targeted option.'),
      opt('aml_rr_ziftomenib','Ziftomenib','NPM1-mutated targeted option.'),
    ]),support=['AML-E','AML-H','AML-J'],pathway_id='AML_RR_NPM1')
    g.action('rr_kmt2a_action','Relapsed/refractory KMT2A-rearranged AML: revumenib-based targeted therapy plus source salvage/HCT strategy.',src('AML-8','AML-9'),rr_common([opt('aml_rr_revumenib_kmt2a','Revumenib','KMT2A-rearranged targeted option.')]),support=['AML-E','AML-H'],pathway_id='AML_RR_KMT2A')
    g.action('rr_flt3_action','Relapsed/refractory FLT3-mutated AML: FLT3-directed salvage plus source salvage/HCT strategy.',src('AML-8','AML-9'),rr_common([
      opt('aml_rr_gilteritinib','Gilteritinib','Category 1 for FLT3-mutated R/R AML.',evidence='CATEGORY_1'),
      opt('aml_rr_sorafenib_hma','HMA + sorafenib','FLT3-ITD option.'),
      opt('aml_rr_quizartinib','Quizartinib','FLT3-ITD option; category 2B.'),
    ]),support=['AML-E','AML-H'],pathway_id='AML_RR_FLT3')
    g.action('rr_idh1_action','Relapsed/refractory IDH1-mutated AML: IDH1-directed salvage plus source salvage/HCT strategy.',src('AML-8','AML-9'),rr_common([opt('aml_rr_ivosidenib','Ivosidenib'),opt('aml_rr_olutasidenib','Olutasidenib')]),support=['AML-E'],pathway_id='AML_RR_IDH1')
    g.action('rr_idh2_action','Relapsed/refractory IDH2-mutated AML: enasidenib plus source salvage/HCT strategy.',src('AML-8','AML-9'),rr_common([opt('aml_rr_enasidenib','Enasidenib')]),support=['AML-E'],pathway_id='AML_RR_IDH2')
    g.action('rr_cd33_action','Relapsed/refractory CD33-positive AML without an earlier targeted hierarchy match: gemtuzumab ozogamicin plus source salvage/HCT strategy.',src('AML-8','AML-9'),rr_common([opt('aml_rr_go','Gemtuzumab ozogamicin','CD33-positive targeted option.')]),support=['AML-E'],pathway_id='AML_RR_CD33')
    g.action('rr_other','Relapsed/refractory AML without a represented actionable mutation: clinical trial, intensive/less-intensive salvage according to fitness/prior therapy, and HCT when remission/eligibility permit.',src('AML-8','AML-9'),rr_common([]),support=['AML-E','AML-H','AML-J'],pathway_id='AML_RR_OTHER')
    g.status('outside','Case is outside AML/APL/BPDCN ruleset.','OUTSIDE_ENCODED_SCOPE',src('EVAL-1'))
    consistency=[
      {'id':'aml_surveillance_active_relapse','when':all_(atom('treatment_phase','eq','SURVEILLANCE'),atom('response_status','in',['REFRACTORY','RELAPSED','PERSISTENT'])),'message':'Active AML cannot be routed as routine surveillance.','source_pathways':['AML-8']},
      {'id':'aml_apl_family_with_nonapl_risk','when':all_(atom('disease_family','eq','APL'),atom('eln_risk','in',['FAVORABLE','INTERMEDIATE','ADVERSE'])),'message':'ELN non-APL risk should not drive APL treatment classification.','source_pathways':['APL-1','AML-A']},
    ]
    common_finalize(pkg,g,roles,consistency_rules=consistency)
    save(name,pkg)

if __name__=='__main__':
    all_builder(); aml_builder(); print('built ALL and AML')

def breast_builder():
    name='nexus_breast_cancer_v6_2026.json'; pkg=load(name)
    additions=[
      fact('clinical_t','CODED',['T1','T2','T3','T4','TX'],role='ROUTING'),
      fact('clinical_n','CODED',['N0','N1','N2','N3','NX'],role='ROUTING'),
      fact('dcis_margin_status','CODED',['NEGATIVE','CLOSE','POSITIVE','UNKNOWN'],role='ROUTING'),
      fact('dcis_er_positive','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('dcis_low_risk_rt_omission_criteria','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('breast_conserving_candidate','BOOLEAN',role='ROUTING'),
      fact('surgical_nodal_staging_indicated','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('pd_l1_cps_ge10','BOOLEAN',role='ROUTING'),
      fact('her2_low','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('her2_ultralow','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('pik3ca_mutation','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('esr1_mutation','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('akt1_or_pten_alteration','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('tumor_agnostic_targetable_marker','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('visceral_crisis','BOOLEAN',role='ROUTING'),
      fact('metastatic_line','CODED',['FIRST','SECOND','THIRD_PLUS','FOURTH_PLUS','UNKNOWN'],role='ROUTING'),
      fact('prior_endocrine_within_1y','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('prior_cdk46_inhibitor','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('prior_pd1_pdl1_inhibitor','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('prior_her2_targeted_therapy','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('preop_pembrolizumab_received','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('high_risk_recurrence','BOOLEAN',role='OPTION_APPLICABILITY'),
      fact('pregnancy_trimester','CODED',['FIRST','SECOND','THIRD','UNKNOWN'],role='ROUTING'),
      fact('phyllodes_margin_positive','BOOLEAN',role='ROUTING'),
      fact('paget_underlying_invasive_cancer','BOOLEAN',role='ROUTING'),
    ]
    for f in additions: upsert_fact(pkg,f)
    roles={d['key']:'ROUTING' for d in pkg['fact_definitions']}
    for k in ['dcis_er_positive','dcis_low_risk_rt_omission_criteria','surgical_nodal_staging_indicated','her2_low','her2_ultralow','pik3ca_mutation','esr1_mutation','akt1_or_pten_alteration','tumor_agnostic_targetable_marker','prior_endocrine_within_1y','prior_cdk46_inhibitor','prior_pd1_pdl1_inhibitor','prior_her2_targeted_therapy','preop_pembrolizumab_received','high_risk_recurrence','germline_brca_pathogenic']:
        roles[k]='OPTION_APPLICABILITY'
    g=Graph(); src=lambda *x:list(x)
    g.decision('scope','Breast cancer?',atom('cancer_type','eq','BREAST_CANCER'),'special_phyll','outside',src('BINV-1','DCIS-1'),'breast_scope')
    # Special pathologies
    g.decision('special_phyll','Phyllodes tumor?',atom('diagnosis_class','eq','PHYLLODES'),'phyll_phase','special_paget',src('PHYLL-1'),'breast_phyllodes')
    g.decision('phyll_phase','Recurrent/metastatic phyllodes disease?',any_(atom('treatment_phase','eq','LOCOREGIONAL_RECURRENCE'),atom('treatment_phase','eq','METASTATIC')),'phyll_recur','phyll_margin',src('PHYLL-1'),'breast_phyll_phase')
    g.decision('phyll_margin','Positive/inadequate phyllodes surgical margin?',atom('phyllodes_margin_positive','eq',True),'phyll_reexcision','phyll_primary',src('PHYLL-1'),'breast_phyll_margin')
    g.action('phyll_reexcision','Phyllodes tumor with positive/inadequate margin: re-excision to achieve adequate margins when feasible.',src('PHYLL-1'),[opt('phyll_reexcision_opt','Re-excision for adequate margins')],pathway_id='BREAST_PHYLLODES_MARGIN_POS')
    g.action('phyll_primary','Localized phyllodes tumor with adequate margin state: surgical management and surveillance according to PHYLL-1.',src('PHYLL-1'),[opt('phyll_surgery','Wide local excision/mastectomy as anatomy requires'),opt('phyll_surv','Surveillance')],pathway_id='BREAST_PHYLLODES_LOCALIZED')
    g.action('phyll_recur','Recurrent/metastatic phyllodes tumor: resect local recurrence when feasible and use sarcoma-directed systemic/palliative principles for metastatic disease.',src('PHYLL-1'),[opt('phyll_recur_surg','Surgery for resectable local recurrence'),opt('phyll_recur_systemic','Systemic therapy for metastatic/unresectable disease')],pathway_id='BREAST_PHYLLODES_RECURRENT')
    g.decision('special_paget','Paget disease?',atom('diagnosis_class','eq','PAGET'),'paget_underlying','phase_preg',src('PAGET-1','PAGET-2'),'breast_paget')
    g.decision('paget_underlying','Underlying invasive carcinoma present?',atom('paget_underlying_invasive_cancer','eq',True),'paget_invasive','paget_noninv',src('PAGET-1','PAGET-2'),'breast_paget_underlying')
    g.action('paget_invasive','Paget disease with underlying invasive breast cancer: definitive local therapy plus nodal/receptor-directed invasive cancer management.',src('PAGET-1','PAGET-2'),[opt('paget_inv_local','Breast surgery +/- RT per extent'),opt('paget_inv_nodes','Axillary staging when indicated'),opt('paget_inv_systemic','Systemic therapy according to underlying invasive tumor biomarkers')],support=['BINV-D','BINV-I'],pathway_id='BREAST_PAGET_INVASIVE')
    g.action('paget_noninv','Paget disease without underlying invasive carcinoma: breast-conserving surgery + RT or mastectomy according to extent, with nodal staging only when indicated.',src('PAGET-1','PAGET-2'),[opt('paget_bcs','Breast-conserving surgery + RT'),opt('paget_mast','Mastectomy'),opt('paget_nodes','Nodal staging if source indications are present',app=atom('surgical_nodal_staging_indicated','eq',True))],support=['BINV-D','BINV-I'],pathway_id='BREAST_PAGET_NONINVASIVE')
    g.decision('phase_preg','Breast cancer during pregnancy?',atom('treatment_phase','eq','PREGNANCY'),'preg_trimester','class_dcis',src('PREG-1','PREG-2'),'breast_pregnancy')
    g.decision('preg_trimester','First trimester?',atom('pregnancy_trimester','eq','FIRST'),'preg_first','preg_later_confirm',src('PREG-1','PREG-2'),'breast_preg_trimester_first')
    g.decision('preg_later_confirm','Second/third trimester?',atom('pregnancy_trimester','in',['SECOND','THIRD']),'preg_later','preg_unknown',src('PREG-1','PREG-2'),'breast_preg_trimester_later')
    g.status('preg_unknown','Pregnancy trimester is required for pregnancy-specific treatment timing.','NEEDS_INFORMATION',src('PREG-1','PREG-2'))
    g.action('preg_first','Breast cancer in first trimester: surgery can proceed when indicated; systemic/radiation timing must follow first-trimester pregnancy constraints.',src('PREG-1','PREG-2'),[opt('preg_first_surg','Surgery when indicated'),opt('preg_first_delay_chemo','Defer contraindicated systemic therapy until pregnancy-appropriate timing'),opt('preg_first_no_rt','Do not deliver breast RT during pregnancy')],support=['BINV-C','BINV-M'],pathway_id='BREAST_PREG_FIRST')
    g.action('preg_later','Breast cancer in second/third trimester: surgery and pregnancy-compatible systemic therapy timing per PREG pathway; RT remains deferred until postpartum.',src('PREG-1','PREG-2'),[opt('preg_later_surg','Surgery when indicated'),opt('preg_later_chemo','Pregnancy-compatible chemotherapy when source timing permits'),opt('preg_later_no_rt','Defer RT until postpartum')],support=['BINV-C','BINV-M'],pathway_id='BREAST_PREG_LATER')
    # DCIS
    g.decision('class_dcis','Ductal carcinoma in situ?',atom('diagnosis_class','eq','DCIS'),'dcis_phase','class_inv',src('DCIS-1','DCIS-2'),'breast_class_dcis')
    g.decision('dcis_phase','Postsurgical/surveillance DCIS episode?',any_(atom('treatment_phase','eq','POST_SURGERY'),atom('treatment_phase','eq','SURVEILLANCE')),'dcis_margin','dcis_local_choice',src('DCIS-1','DCIS-2'),'breast_dcis_phase')
    g.decision('dcis_local_choice','Breast-conserving approach feasible/selected?',atom('breast_conserving_candidate','eq',True),'dcis_bcs','dcis_mast',src('DCIS-1'),'breast_dcis_local_choice')
    g.action('dcis_bcs','DCIS eligible for breast conservation: excision with margin assessment, selective SLNB only when source indications apply, then postsurgical RT/endocrine decisions.',src('DCIS-1'),[opt('dcis_bcs_excision','Breast-conserving surgery/excision'),opt('dcis_bcs_slnb','Sentinel lymph node biopsy','Only when source indications apply.',app=atom('surgical_nodal_staging_indicated','eq',True))],support=['BINV-D','BINV-F','BINV-I'],next_steps=['DCIS-2 postsurgical treatment'],pathway_id='BREAST_DCIS_BCS')
    g.action('dcis_mast','DCIS not managed with breast conservation: mastectomy pathway with selective SLNB considerations.',src('DCIS-1'),[opt('dcis_mastectomy','Mastectomy'),opt('dcis_mast_slnb','Sentinel lymph node biopsy','May be considered/omitted only under source-defined criteria.',app=atom('surgical_nodal_staging_indicated','eq',True))],support=['BINV-D'],pathway_id='BREAST_DCIS_MAST')
    g.decision('dcis_margin','DCIS surgical margin positive?',atom('dcis_margin_status','eq','POSITIVE'),'dcis_reexcision','dcis_post_options',src('DCIS-2','BINV-F'),'breast_dcis_margin')
    g.action('dcis_reexcision','DCIS with positive surgical margin: further surgery/re-excision according to margin and planned local therapy.',src('DCIS-2'),[opt('dcis_reexcision','Re-excision/further surgery for positive margin')],support=['BINV-F'],pathway_id='BREAST_DCIS_MARGIN_POS')
    g.action('dcis_post_options','DCIS after adequate surgery: RT and endocrine risk-reduction options filtered by low-risk omission criteria and ER status.',src('DCIS-2'),[
      opt('dcis_wbrt','Whole-breast RT after BCS','Standard postsurgical local-control option.'),
      opt('dcis_omit_rt','Omit RT with endocrine therapy alone','May be considered only when RTOG 9804 low-risk criteria are met.',app=atom('dcis_low_risk_rt_omission_criteria','eq',True)),
      opt('dcis_endocrine','Endocrine risk-reduction therapy','For ER-positive DCIS.',app=atom('dcis_er_positive','eq',True)),
      opt('dcis_surveillance','Surveillance/follow-up'),
    ],support=['BINV-K','BINV-I'],pathway_id='BREAST_DCIS_POST')
    # invasive
    g.decision('class_inv','Invasive breast cancer?',atom('diagnosis_class','eq','INVASIVE'),'care_met','class_missing',src('BINV-1'),'breast_class_invasive')
    g.decision('care_met','Active metastatic/stage IV disease?',any_(atom('clinical_m','eq','M1'),atom('treatment_phase','eq','METASTATIC')),'met_hr','care_recur',src('BINV-18','BINV-21'),'breast_care_met')
    g.decision('care_recur','Locoregional recurrence without distant disease?',atom('treatment_phase','eq','LOCOREGIONAL_RECURRENCE'),'recur_local','care_postpre',src('BINV-19','BINV-20'),'breast_care_recur')
    g.action('recur_local','Biopsy-proven locoregional breast recurrence without distant disease: local therapy according to resectability/prior RT plus receptor-directed systemic treatment.',src('BINV-19','BINV-20'),[
      opt('breast_recur_surgery','Surgical resection when feasible'),
      opt('breast_recur_rt','Radiation/re-irradiation according to prior RT and anatomy'),
      opt('breast_recur_systemic','Systemic therapy according to current HR/HER2 biomarkers'),
    ],support=['BINV-I','BINV-P','BINV-Q'],pathway_id='BREAST_LOCOREGIONAL_RECURRENCE')
    g.decision('care_postpre','After preoperative systemic therapy?',atom('treatment_phase','eq','POST_PREOPERATIVE'),'postpre_residual','care_postop',src('BINV-16'),'breast_care_postpre')
    g.decision('postpre_residual','Residual invasive disease after preoperative therapy?',atom('residual_invasive_disease','eq',True),'postpre_receptor','postpre_pcr_receptor',src('BINV-16'),'breast_postpre_residual')
    # residual: receptor-specific options
    g.decision('postpre_receptor','HER2-positive residual disease?',atom('her2_status','eq','POSITIVE'),'postpre_resid_her2','postpre_resid_hr',src('BINV-16'),'breast_postpre_resid_her2')
    g.decision('postpre_resid_hr','HR-positive/HER2-negative residual disease?',all_(atom('hr_status','eq','POSITIVE'),atom('her2_status','eq','NEGATIVE')),'postpre_resid_hrpos','postpre_resid_tnbc',src('BINV-16'),'breast_postpre_resid_hr')
    g.action('postpre_resid_her2','HER2-positive residual invasive disease after preoperative therapy: T-DXd for high-risk recurrence or T-DM1, complete HER2 therapy; add endocrine therapy if HR-positive.',src('BINV-16'),[
      opt('breast_postpre_tdx','Fam-trastuzumab deruxtecan-nxki','Category 1 for high-risk recurrence.',evidence='CATEGORY_1',app=atom('high_risk_recurrence','eq',True)),
      opt('breast_postpre_tdm1','Ado-trastuzumab emtansine','Category 1.',evidence='CATEGORY_1'),
      opt('breast_postpre_endocrine','Adjuvant endocrine therapy','If HR-positive.',app=atom('hr_status','eq','POSITIVE')),
    ],support=['BINV-M','BINV-K'],pathway_id='BREAST_POSTPRE_RESID_HER2')
    g.action('postpre_resid_hrpos','HR-positive/HER2-negative residual invasive disease after preoperative therapy: endocrine therapy plus source-defined high-risk targeted/adjuvant options.',src('BINV-16'),[
      opt('breast_postpre_hr_endocrine','Adjuvant endocrine therapy','Category 1.',evidence='CATEGORY_1'),
      opt('breast_postpre_hr_olaparib','Adjuvant olaparib for 1 year','For germline BRCA1/2 pathogenic variant and high-risk criteria.',evidence='CATEGORY_1',app=atom('germline_brca_pathogenic','eq',True)),
      opt('breast_postpre_hr_cdk','Adjuvant abemaciclib or ribociclib','For source-defined high-risk eligible patients.',app=atom('high_risk_recurrence','eq',True)),
    ],support=['BINV-K','BINV-M'],pathway_id='BREAST_POSTPRE_RESID_HRPOS')
    g.action('postpre_resid_tnbc','HR-negative/HER2-negative residual invasive disease after preoperative therapy: continue pembrolizumab if used preoperatively, consider capecitabine and/or olaparib for germline BRCA.',src('BINV-16'),[
      opt('breast_postpre_tnbc_pembro','Adjuvant pembrolizumab','Only if pembrolizumab-containing regimen was given preoperatively.',evidence='CATEGORY_1',app=atom('preop_pembrolizumab_received','eq',True)),
      opt('breast_postpre_tnbc_capec','Adjuvant capecitabine','6-8 cycles per source.'),
      opt('breast_postpre_tnbc_olaparib','Adjuvant olaparib for 1 year','For germline BRCA1/2 pathogenic variant.',evidence='CATEGORY_1',app=atom('germline_brca_pathogenic','eq',True)),
    ],support=['BINV-M'],pathway_id='BREAST_POSTPRE_RESID_TNBC')
    g.decision('postpre_pcr_receptor','HER2-positive pCR/ypT0N0?',atom('her2_status','eq','POSITIVE'),'postpre_pcr_her2','postpre_pcr_nonher2',src('BINV-16'),'breast_postpre_pcr_her2')
    g.action('postpre_pcr_her2','HER2-positive pCR/ypT0N0 after preoperative therapy: complete up to one year of trastuzumab +/- pertuzumab; add endocrine therapy if HR-positive.',src('BINV-16'),[
      opt('breast_pcr_her2_complete','Complete up to 1 year trastuzumab +/- pertuzumab'),
      opt('breast_pcr_her2_endocrine','Adjuvant endocrine therapy','If HR-positive.',app=atom('hr_status','eq','POSITIVE')),
    ],support=['BINV-K','BINV-M'],pathway_id='BREAST_POSTPRE_PCR_HER2')
    g.action('postpre_pcr_nonher2','HER2-negative pCR after preoperative therapy: complete receptor-specific adjuvant therapy when source-defined and proceed to follow-up.',src('BINV-16'),[
      opt('breast_pcr_hr_endocrine','Adjuvant endocrine therapy','If HR-positive.',app=atom('hr_status','eq','POSITIVE')),
      opt('breast_pcr_tnbc_pembro','Complete adjuvant pembrolizumab','If preoperative pembrolizumab regimen was used.',app=all_(atom('hr_status','eq','NEGATIVE'),atom('preop_pembrolizumab_received','eq',True))),
    ],support=['BINV-K','BINV-M'],pathway_id='BREAST_POSTPRE_PCR')
    # upfront surgery / adjuvant
    g.decision('care_postop','Postoperative/adjuvant planning after upfront surgery?',atom('treatment_phase','eq','POST_SURGERY'),'postop_her2','care_surv',src('BINV-5','BINV-6','BINV-7','BINV-8','BINV-9','BINV-10','BINV-11'),'breast_care_postop')
    g.decision('postop_her2','HER2-positive postoperative disease?',atom('her2_status','eq','POSITIVE'),'postop_her2_hr','postop_her2neg_confirm',src('BINV-5','BINV-9'),'breast_postop_her2')
    g.decision('postop_her2_hr','HR-positive?',atom('hr_status','eq','POSITIVE'),'postop_hrpos_her2','postop_hrneg_her2',src('BINV-5','BINV-9'),'breast_postop_her2_hr')
    g.action('postop_hrpos_her2','Postoperative HR-positive/HER2-positive invasive breast cancer: HER2-directed adjuvant therapy according to pathologic risk plus endocrine therapy.',src('BINV-5'),[opt('breast_adj_her2_chemo','HER2-directed chemotherapy regimen per BINV-M'),opt('breast_adj_her2_endocrine','Adjuvant endocrine therapy','Category 1.'),opt('breast_adj_her2_pert','Pertuzumab + trastuzumab','For node-positive/high-risk disease.',app=atom('pathologic_node_status','eq','N_POSITIVE'))],support=['BINV-K','BINV-M'],pathway_id='BREAST_ADJ_HRPOS_HER2POS')
    g.action('postop_hrneg_her2','Postoperative HR-negative/HER2-positive invasive breast cancer: pathologic-risk-directed HER2-targeted adjuvant therapy.',src('BINV-9'),[opt('breast_adj_hrneg_her2','HER2-directed chemotherapy regimen per BINV-M'),opt('breast_adj_hrneg_pert','Pertuzumab + trastuzumab','For node-positive/high-risk disease.',app=atom('pathologic_node_status','eq','N_POSITIVE'))],support=['BINV-M'],pathway_id='BREAST_ADJ_HRNEG_HER2POS')
    g.decision('postop_her2neg_confirm','HER2-negative?',atom('her2_status','eq','NEGATIVE'),'postop_hr','need_her2',src('BINV-6','BINV-7','BINV-8','BINV-10'),'breast_postop_her2neg')
    g.decision('postop_hr','HR-positive?',atom('hr_status','eq','POSITIVE'),'postop_meno','postop_tnbc',src('BINV-6','BINV-7','BINV-8','BINV-10'),'breast_postop_hr')
    g.decision('postop_meno','Postmenopausal?',atom('menopause','eq','POSTMENOPAUSAL'),'postop_hrpost','postop_pre_confirm',src('BINV-6'),'breast_postop_meno')
    g.decision('postop_pre_confirm','Premenopausal?',atom('menopause','eq','PREMENOPAUSAL'),'postop_pre_node','need_meno',src('BINV-7','BINV-8'),'breast_postop_pre')
    g.decision('postop_pre_node','Pathologic node-positive?',atom('pathologic_node_status','eq','N_POSITIVE'),'postop_pre_npos','postop_pre_n0',src('BINV-7','BINV-8'),'breast_postop_node')
    g.action('postop_hrpost','Postmenopausal HR-positive/HER2-negative postoperative disease: endocrine therapy with chemotherapy/genomic-risk and high-risk targeted additions as source-indicated.',src('BINV-6'),[opt('breast_adj_hrpost_endocrine','Adjuvant endocrine therapy'),opt('breast_adj_hrpost_chemo','Adjuvant chemotherapy','According to pathologic/genomic risk.',decision_relevant=False),opt('breast_adj_hrpost_olaparib','Adjuvant olaparib','For germline BRCA high-risk disease.',app=atom('germline_brca_pathogenic','eq',True))],support=['BINV-K','BINV-N'],pathway_id='BREAST_ADJ_HRPOS_HER2NEG_POST')
    g.action('postop_pre_npos','Premenopausal HR-positive/HER2-negative node-positive postoperative disease: ovarian suppression/endocrine +/- chemotherapy and high-risk targeted therapy as source-defined.',src('BINV-8'),[opt('breast_adj_pre_npos_endocrine','Ovarian suppression + endocrine therapy'),opt('breast_adj_pre_npos_chemo','Adjuvant chemotherapy'),opt('breast_adj_pre_npos_olaparib','Adjuvant olaparib','For germline BRCA high-risk disease.',app=atom('germline_brca_pathogenic','eq',True))],support=['BINV-K','BINV-N'],pathway_id='BREAST_ADJ_PRE_NPOS')
    g.action('postop_pre_n0','Premenopausal HR-positive/HER2-negative node-negative postoperative disease: genomic-risk-directed chemotherapy decision plus endocrine therapy.',src('BINV-7'),[opt('breast_adj_pre_n0_endocrine','Adjuvant endocrine therapy'),opt('breast_adj_pre_n0_chemo','Chemotherapy according to genomic/pathologic risk',decision_relevant=False)],support=['BINV-K','BINV-N'],pathway_id='BREAST_ADJ_PRE_N0')
    g.action('postop_tnbc','Postoperative HR-negative/HER2-negative invasive breast cancer: pathologic-stage-directed chemotherapy and germline-BRCA-directed adjuvant olaparib where source criteria are met.',src('BINV-10'),[opt('breast_adj_tnbc_chemo','Adjuvant chemotherapy according to pathologic stage'),opt('breast_adj_tnbc_olaparib','Adjuvant olaparib','For germline BRCA high-risk disease.',app=atom('germline_brca_pathogenic','eq',True))],support=['BINV-M'],pathway_id='BREAST_ADJ_TNBC')
    g.status('need_her2','HER2 status must be resolved before receptor-directed therapy.','NEEDS_INFORMATION',src('BINV-A'))
    g.status('need_meno','Menopausal status is required for this HR-positive/HER2-negative branch.','NEEDS_INFORMATION',src('BINV-O'))
    # surveillance / preop / localized initial
    g.decision('care_surv','Surveillance/follow-up episode?',atom('treatment_phase','eq','SURVEILLANCE'),'surv','care_preop',src('BINV-17'),'breast_care_surv')
    g.action('surv','Breast cancer surveillance/follow-up after curative-intent treatment.',src('BINV-17'),[opt('breast_surv_exam','Clinical follow-up'),opt('breast_surv_mammo','Breast imaging surveillance')],support=['BINV-R'],pathway_id='BREAST_SURVEILLANCE')
    g.decision('care_preop','Preoperative systemic therapy selected/planned?',any_(atom('treatment_phase','eq','PREOPERATIVE_SYSTEMIC'), all_(atom('her2_status','eq','POSITIVE'), any_(atom('clinical_t','in',['T2','T3','T4']), atom('clinical_n','in',['N1','N2','N3']))), all_(atom('hr_status','eq','NEGATIVE'), atom('her2_status','eq','NEGATIVE'), any_(atom('clinical_t','in',['T2','T3','T4']), atom('clinical_n','in',['N1','N2','N3'])))),'preop_receptor','localized_ibc',src('BINV-12','BINV-13','BINV-14','BINV-15'),'breast_preop')
    g.decision('preop_receptor','HER2-positive preoperative disease?',atom('her2_status','eq','POSITIVE'),'preop_her2','preop_hr',src('BINV-12','BINV-13','BINV-14','BINV-15'),'breast_preop_her2')
    g.decision('preop_hr','HR-positive/HER2-negative preoperative disease?',all_(atom('hr_status','eq','POSITIVE'),atom('her2_status','eq','NEGATIVE')),'preop_hrpos','preop_tnbc',src('BINV-12','BINV-13','BINV-14','BINV-15'),'breast_preop_hr')
    g.action('preop_her2','HER2-positive localized disease selected for preoperative systemic therapy: HER2-directed neoadjuvant regimen with response assessment, then surgery and residual-disease-directed BINV-16 therapy.',src('BINV-12','BINV-13','BINV-14','BINV-15'),[opt('breast_preop_her2_regimen','HER2-directed preoperative regimen per BINV-M'),opt('breast_preop_her2_surg','Surgery/axillary management after response assessment')],support=['BINV-M','BINV-D','BINV-E'],next_steps=['BINV-16'],pathway_id='BREAST_PREOP_HER2')
    g.action('preop_hrpos','HR-positive/HER2-negative localized disease selected for preoperative systemic therapy: endocrine or chemotherapy according to tumor/patient context, then surgery and adjuvant pathway.',src('BINV-12','BINV-13','BINV-14','BINV-15'),[opt('breast_preop_hr_chemo','Preoperative chemotherapy where indicated'),opt('breast_preop_hr_endocrine','Preoperative endocrine therapy in selected patients')],support=['BINV-L','BINV-M'],next_steps=['BINV-16'],pathway_id='BREAST_PREOP_HRPOS')
    g.action('preop_tnbc','Triple-negative localized disease selected for preoperative systemic therapy: source neoadjuvant chemo-immunotherapy where indicated, then surgery and residual-disease-directed adjuvant pathway.',src('BINV-12','BINV-13','BINV-14','BINV-15'),[opt('breast_preop_tnbc_regimen','Preoperative chemotherapy +/- pembrolizumab per BINV-M'),opt('breast_preop_tnbc_surg','Surgery/axillary management after response')],support=['BINV-M'],next_steps=['BINV-16'],pathway_id='BREAST_PREOP_TNBC')
    g.decision('localized_ibc','Inflammatory breast cancer?',atom('inflammatory','eq',True),'ibc','localized_local',src('IBC-1','IBC-2'),'breast_ibc')
    g.action('ibc','Inflammatory breast cancer: preoperative systemic therapy -> mastectomy/axillary surgery -> radiation and receptor/residual-directed adjuvant therapy.',src('IBC-1','IBC-2'),[opt('ibc_preop','Preoperative systemic therapy'),opt('ibc_surgery','Modified radical mastectomy/axillary management after response'),opt('ibc_rt','Postmastectomy radiation'),opt('ibc_adjuvant','Receptor/residual-directed adjuvant therapy')],support=['BINV-M','BINV-I'],pathway_id='BREAST_INFLAMMATORY')
    g.decision('localized_local','Breast-conserving approach feasible?',atom('breast_conserving_candidate','eq',True),'localized_bcs','localized_mast',src('BINV-1','BINV-2','BINV-3','BINV-4'),'breast_localized_local')
    g.action('localized_bcs','Localized invasive breast cancer treated with breast conservation: BCS + appropriate axillary staging + RT, followed by receptor/pathology-directed adjuvant therapy.',src('BINV-1','BINV-2','BINV-4'),[opt('breast_local_bcs','Breast-conserving surgery'),opt('breast_local_nodes','Axillary staging when indicated',app=atom('surgical_nodal_staging_indicated','eq',True)),opt('breast_local_rt','Breast/regional nodal RT according to stage/pathology')],support=['BINV-D','BINV-E','BINV-F','BINV-I'],next_steps=['BINV-5 through BINV-11'],pathway_id='BREAST_LOCALIZED_BCS')
    g.action('localized_mast','Localized invasive breast cancer not managed with breast conservation: mastectomy +/- axillary staging and PMRT according to stage/pathology, followed by systemic adjuvant therapy.',src('BINV-1','BINV-3','BINV-4'),[opt('breast_local_mast','Mastectomy'),opt('breast_local_mast_nodes','Axillary staging when indicated',app=atom('surgical_nodal_staging_indicated','eq',True)),opt('breast_local_pmrt','Postmastectomy RT according to nodal/T-stage criteria',decision_relevant=False)],support=['BINV-D','BINV-E','BINV-I'],next_steps=['BINV-5 through BINV-11'],pathway_id='BREAST_LOCALIZED_MAST')
    # Metastatic exact routing
    g.decision('met_hr','HR-positive metastatic disease?',atom('hr_status','eq','POSITIVE'),'met_hr_her2','met_her2neg_hrneg',src('BINV-21'),'breast_met_hr')
    g.decision('met_hr_her2','HER2-positive?',atom('her2_status','eq','POSITIVE'),'met_hrpos_her2','met_hrneg_her2confirm',src('BINV-24','BINV-25'),'breast_met_hr_her2')
    g.decision('met_hrneg_her2confirm','HER2-negative?',atom('her2_status','eq','NEGATIVE'),'met_hrpos_her2neg_visc','need_her2',src('BINV-22','BINV-23'),'breast_met_hr_her2neg')
    g.decision('met_hrpos_her2neg_visc','Visceral crisis?',atom('visceral_crisis','eq',True),'met_hrpos_visceral','met_hrpos_line',src('BINV-22','BINV-23'),'breast_met_hr_visceral')
    g.decision('met_hrpos_line','First-line metastatic therapy?',atom('metastatic_line','eq','FIRST'),'met_hrpos_first','met_hrpos_later',src('BINV-22','BINV-23'),'breast_met_hr_line')
    g.action('met_hrpos_visceral','HR-positive/HER2-negative metastatic breast cancer with visceral crisis: cytotoxic/rapidly efficacious therapy; endocrine-targeted combinations only in selected circumstances.',src('BINV-22','BINV-23'),[
      opt('breast_hrvis_cytotoxic','Cytotoxic therapy per BINV-Q 2/5'),
      opt('breast_hrvis_targeted_endo','Endocrine + targeted therapy','May be considered in certain circumstances despite visceral crisis.',decision_relevant=False),
    ],support=['BINV-Q','BINV-R'],pathway_id='BREAST_MET_HRPOS_VISCRISIS')
    g.action('met_hrpos_first','First-line HR-positive/HER2-negative metastatic breast cancer without visceral crisis: endocrine + CDK4/6 inhibitor, with mutation-directed first-line alternatives when source criteria are met.',src('BINV-22'),[
      opt('breast_hr1_ai_ribo','Aromatase inhibitor + ribociclib','Preferred; category 1.',preference='PREFERRED',evidence='CATEGORY_1'),
      opt('breast_hr1_ai_abema','Aromatase inhibitor + abemaciclib','Preferred.',preference='PREFERRED'),
      opt('breast_hr1_ai_palbo','Aromatase inhibitor + palbociclib','Preferred.',preference='PREFERRED'),
      opt('breast_hr1_fulv_cdk','Fulvestrant + CDK4/6 inhibitor','For progression on/early relapse after adjuvant endocrine therapy.',app=atom('prior_endocrine_within_1y','eq',True)),
      opt('breast_hr1_inavolisib','Fulvestrant + inavolisib + palbociclib','For PIK3CA activating mutation in the source-defined early-relapse setting.',app=all_(atom('pik3ca_mutation','eq',True),atom('prior_endocrine_within_1y','eq',True))),
    ],support=['BINV-P','BINV-R'],pathway_id='BREAST_MET_HRPOS_FIRST')
    g.action('met_hrpos_later','Second/subsequent-line HR-positive/HER2-negative metastatic disease: endocrine/targeted options filtered by PIK3CA/AKT/PTEN/ESR1 and prior CDK4/6 exposure; cytotoxic therapy when endocrine refractory.',src('BINV-23'),[
      opt('breast_hrlater_fulv_cdk','Fulvestrant + CDK4/6 inhibitor','If CDK4/6 inhibitor not previously used.',evidence='CATEGORY_1',app=atom('prior_cdk46_inhibitor','eq',False)),
      opt('breast_hrlater_geda','Fulvestrant + gedatolisib +/- palbociclib','For tumors without PIK3CA mutation after >=1 line endocrine therapy.',evidence='CATEGORY_1',app=atom('pik3ca_mutation','eq',False)),
      opt('breast_hrlater_aktpi3k','PI3K/AKT-pathway targeted therapy','For PIK3CA or AKT1 activating mutation or PTEN inactivation.',app=any_(atom('pik3ca_mutation','eq',True),atom('akt1_or_pten_alteration','eq',True))),
      opt('breast_hrlater_esr1','ESR1-targeted endocrine therapy','For ESR1-mutated tumors after prior endocrine therapy.',app=atom('esr1_mutation','eq',True)),
      opt('breast_hrlater_everolimus','Everolimus + endocrine therapy'),
      opt('breast_hrlater_cytotoxic','Cytotoxic therapy','When endocrine-refractory/visceral symptomatic or after sequential endocrine benefit exhausted.'),
    ],support=['BINV-P','BINV-Q','BINV-R'],pathway_id='BREAST_MET_HRPOS_LATER')
    # HR+ HER2+
    g.decision('met_hrpos_her2','First-line HER2-positive metastatic therapy?',atom('metastatic_line','eq','FIRST'),'met_her2_first','met_her2_later',src('BINV-24','BINV-25','BINV-26'),'breast_met_her2_line')
    # HR-negative route: HER2 positive vs TNBC
    g.decision('met_her2neg_hrneg','HER2-positive metastatic disease?',atom('her2_status','eq','POSITIVE'),'met_her2_line_hrneg','met_tnbc_confirm',src('BINV-26','BINV-27'),'breast_met_hrneg_her2')
    g.decision('met_her2_line_hrneg','First-line HER2-positive metastatic therapy?',atom('metastatic_line','eq','FIRST'),'met_her2_first','met_her2_later',src('BINV-26'),'breast_met_her2_line_hrneg')
    g.decision('met_tnbc_confirm','HER2-negative confirmed?',atom('her2_status','eq','NEGATIVE'),'met_tnbc_line','need_her2',src('BINV-27'),'breast_met_tnbc_confirm')
    her2_first_opts=[
      opt('breast_her2_1_doc_thp','Docetaxel + trastuzumab + pertuzumab','Category 1 preferred.',preference='PREFERRED',evidence='CATEGORY_1'),
      opt('breast_her2_1_pac_thp','Paclitaxel + trastuzumab + pertuzumab','Preferred.',preference='PREFERRED'),
      opt('breast_her2_1_tdx_p','Fam-trastuzumab deruxtecan-nxki + pertuzumab','Other recommended.'),
      opt('breast_her2_1_endocrine','Endocrine therapy + trastuzumab +/- pertuzumab','For HR-positive disease.',app=atom('hr_status','eq','POSITIVE')),
      opt('breast_her2_gbrca_parpi','PARP inhibitor','Panel supports use for germline BRCA-associated disease; lower-level evidence in HER2-positive tumors.',app=atom('germline_brca_pathogenic','eq',True)),
    ]
    g.action('met_her2_first','First-line HER2-positive metastatic breast cancer: trastuzumab/pertuzumab-based therapy or source alternative; add endocrine therapy when HR-positive.',src('BINV-24','BINV-26'),her2_first_opts,support=['BINV-P','BINV-Q','BINV-R'],pathway_id='BREAST_MET_HER2_FIRST')
    g.action('met_her2_later','Second and later-line HER2-positive metastatic breast cancer: line-aware HER2-targeted options.',src('BINV-25','BINV-26'),[
      opt('breast_her2_later_tuc','Capecitabine + tucatinib + trastuzumab','Category 1 preferred second/third line.',preference='PREFERRED',evidence='CATEGORY_1'),
      opt('breast_her2_later_tdx','Fam-trastuzumab deruxtecan-nxki','Category 1 preferred second/third line.',preference='PREFERRED',evidence='CATEGORY_1'),
      opt('breast_her2_later_tdm1','T-DM1','Second/third-line option.'),
      opt('breast_her2_later_4plus','Fourth-line and beyond HER2 regimens','Trastuzumab-containing, lapatinib/neratinib, margetuximab and other source-listed options.',app=atom('metastatic_line','eq','FOURTH_PLUS')),
      opt('breast_her2_later_endocrine','Alternate endocrine therapy +/- HER2-targeted therapy','For HR-positive disease not endocrine refractory.',app=atom('hr_status','eq','POSITIVE')),
    ],support=['BINV-P','BINV-Q','BINV-R'],pathway_id='BREAST_MET_HER2_LATER')
    # TNBC line and biomarker exact
    g.decision('met_tnbc_line','First-line TNBC?',atom('metastatic_line','eq','FIRST'),'tnbc_first_pdl1','tnbc_second',src('BINV-27'),'breast_tnbc_line')
    g.decision('tnbc_first_pdl1','PD-L1 CPS >=10?',atom('pd_l1_cps_ge10','eq',True),'tnbc_first_pdl1pos','tnbc_first_gbrca',src('BINV-Q'),'breast_tnbc_pdl1')
    g.decision('tnbc_first_gbrca','Germline BRCA1/2 pathogenic variant?',atom('germline_brca_pathogenic','eq',True),'tnbc_first_gbrca_pos','tnbc_first_standard',src('BINV-Q'),'breast_tnbc_gbrca')
    g.action('tnbc_first_pdl1pos','First-line TNBC with PD-L1 CPS >=10: pembrolizumab-containing category 1 preferred regimens regardless of germline BRCA status.',src('BINV-27'),[
      opt('tnbc_pdl1_chemo_pembro','Chemotherapy + pembrolizumab','Category 1 preferred.',preference='PREFERRED',evidence='CATEGORY_1'),
      opt('tnbc_pdl1_saci_pembro','Sacituzumab govitecan + pembrolizumab','Category 1 preferred.',preference='PREFERRED',evidence='CATEGORY_1'),
    ],support=['BINV-Q'],pathway_id='BREAST_TNBC_FIRST_PDL1')
    g.action('tnbc_first_gbrca_pos','First-line TNBC with PD-L1 CPS <10/not PD-1 candidate and germline BRCA1/2 pathogenic variant: PARP inhibitor or platinum are category 1 preferred.',src('BINV-27'),[
      opt('tnbc_gbrca_parpi','PARP inhibitor: olaparib or talazoparib','Category 1 preferred.',preference='PREFERRED',evidence='CATEGORY_1'),
      opt('tnbc_gbrca_platinum','Platinum: carboplatin or cisplatin','Category 1 preferred.',preference='PREFERRED',evidence='CATEGORY_1'),
    ],support=['BINV-Q'],pathway_id='BREAST_TNBC_FIRST_GBRCA')
    g.action('tnbc_first_standard','First-line TNBC with PD-L1 CPS <10/not PD-1 candidate and no germline BRCA pathogenic variant: sacituzumab govitecan, datopotamab deruxtecan, or systemic chemotherapy per source.',src('BINV-27'),[
      opt('tnbc_std_saci','Sacituzumab govitecan','Category 1 preferred.',preference='PREFERRED',evidence='CATEGORY_1'),
      opt('tnbc_std_dato','Datopotamab deruxtecan','Category 1 preferred.',preference='PREFERRED',evidence='CATEGORY_1'),
      opt('tnbc_std_chemo','Systemic chemotherapy'),
    ],support=['BINV-Q'],pathway_id='BREAST_TNBC_FIRST_STANDARD')
    g.decision('tnbc_second','Second-line TNBC?',atom('metastatic_line','eq','SECOND'),'tnbc_second_gbrca','tnbc_thirdplus',src('BINV-Q'),'breast_tnbc_second')
    g.decision('tnbc_second_gbrca','Germline BRCA1/2 pathogenic variant?',atom('germline_brca_pathogenic','eq',True),'tnbc_second_gbrca_pos','tnbc_second_nogbrca',src('BINV-Q'),'breast_tnbc_second_gbrca')
    g.action('tnbc_second_gbrca_pos','Second-line TNBC with germline BRCA pathogenic variant: PARP inhibitor preferred; sacituzumab and other systemic options remain if not previously used.',src('BINV-27'),[
      opt('tnbc_2_gbrca_parpi','PARP inhibitor','Category 1 preferred.',preference='PREFERRED',evidence='CATEGORY_1'),
      opt('tnbc_2_saci','Sacituzumab govitecan','Category 1 preferred if not previously used.',preference='PREFERRED',evidence='CATEGORY_1'),
    ],support=['BINV-Q'],pathway_id='BREAST_TNBC_SECOND_GBRCA')
    g.action('tnbc_second_nogbrca','Second-line TNBC without germline BRCA pathogenic variant: sacituzumab preferred; T-DXd if HER2-low and not previously used, plus other systemic options.',src('BINV-27'),[
      opt('tnbc_2_saci_nobr','Sacituzumab govitecan','Category 1 preferred.',preference='PREFERRED',evidence='CATEGORY_1'),
      opt('tnbc_2_tdx','Fam-trastuzumab deruxtecan-nxki','For HER2 IHC 1+ or 2+/ISH-negative.',app=atom('her2_low','eq',True)),
      opt('tnbc_2_chemo','Systemic chemotherapy'),
    ],support=['BINV-Q'],pathway_id='BREAST_TNBC_SECOND_NOGBRCA')
    g.action('tnbc_thirdplus','Third-line and beyond TNBC: biomarker-directed targeted therapy where present plus systemic chemotherapy; do not repeat PD-1/PD-L1 therapy after progression on a checkpoint inhibitor.',src('BINV-27'),[
      opt('tnbc_3_targeted','Tumor-agnostic targeted therapy','For MSI-H/TMB-H/NTRK/RET or other source-defined target.',app=atom('tumor_agnostic_targetable_marker','eq',True)),
      opt('tnbc_3_saci','Sacituzumab govitecan','If not previously used.'),
      opt('tnbc_3_tdx','Fam-trastuzumab deruxtecan-nxki','For HER2-low disease if not previously used.',app=atom('her2_low','eq',True)),
      opt('tnbc_3_chemo','Systemic chemotherapy'),
    ],support=['BINV-Q','BINV-R'],pathway_id='BREAST_TNBC_THIRDPLUS')
    g.status('class_missing','Breast diagnosis class is not established.','NEEDS_INFORMATION',src('BINV-1'))
    g.status('outside','Case is outside breast cancer ruleset.','OUTSIDE_ENCODED_SCOPE',src('BINV-1'))
    consistency=[
      {'id':'breast_metastatic_m0_conflict','when':all_(atom('treatment_phase','eq','METASTATIC'),atom('clinical_m','eq','M0')),'message':'Current metastatic care state conflicts with M0 status.','source_pathways':['BINV-18','BINV-21']},
      {'id':'breast_surveillance_metastatic_conflict','when':all_(atom('treatment_phase','eq','SURVEILLANCE'),atom('clinical_m','eq','M1')),'message':'Stage IV disease cannot route to routine curative-intent surveillance.','source_pathways':['BINV-17','BINV-18']},
    ]
    common_finalize(pkg,g,roles,consistency_rules=consistency)
    save(name,pkg)
