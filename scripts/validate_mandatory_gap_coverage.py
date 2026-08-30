from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ENC=ROOT/'backend/nexus/guidelines/encoded'

REQ={
'nexus_acute_lymphoblastic_leukemia_v2_2026.json': ['mrd_status','transplant_candidate','cns_involvement','ph_status','lineage','treatment_phase','response_status'],
'nexus_acute_myeloid_leukemia_v5_2026.json': ['cd33_positive','kmt2a_rearranged','npm1_mutation','flt3_mutation','idh1_mutation','idh2_mutation','tp53_mutation_or_del17p','mrd_status','transplant_candidate','prior_hma','venetoclax_contraindicated','response_status','cns_involvement','bpdc_n_cd123_positive','tagraxofusp_eligible','pivekimab_eligible'],
'nexus_anal_carcinoma_v2_2026.json': ['primary_site','clinical_m','perianal_early_local_excision_eligible','excision_margin_adequate','post_chemoradiation_status','recurrence_site','prior_rt','resectable_local_recurrence','metastatic_line'],
'nexus_b_cell_lymphomas_v4_2026.json': ['lymphoma_subtype','stage_group','bulky_disease','indications_for_treatment','response_status','transplant_candidate','car_t_candidate','treatment_line','prior_anti_cd20','prior_cbtki','mcl_mrd_status'],
'nexus_basal_cell_skin_cancer_v1_2027.json': ['location_high_risk','diameter_high_risk','poorly_defined_borders','recurrent_primary','immunosuppressed','site_prior_rt','aggressive_histology','perineural_involvement','margin_status','named_nerve_involvement','surgery_feasible','disease_extent','prior_hhi','hhi_intolerant_or_progressed'],
'nexus_biliary_tract_cancers_v1_2026.json': ['primary_site','resectable','postop_margin','postop_nodes_positive','systemic_line','msi_h_dmmr','tmb_high','her2_positive','fgfr2_fusion','idh1_mutation','ntrk_fusion','ret_fusion','braf_v600e','kras_g12c','nrg1_fusion'],
'nexus_bladder_cancer_v3_2026.json': ['clinical_t','clinical_n','clinical_m','nmibc_risk','bcg_unresponsive','radical_cystectomy_candidate','bladder_preservation_candidate','complete_turbt_feasible','ctdna_mrd_positive','fgfr3_alteration','cisplatin_eligible','metastatic_line','prior_checkpoint_inhibitor','prior_enfortumab'],
'nexus_bone_cancer_v1_2027.json': ['tumor_subtype','grade_group','location','tumor_compartment','resectable','metastatic','response_status','margin_status'],
'nexus_breast_cancer_v6_2026.json': ['hr_status','her2_status','her2_low','her2_ultralow','clinical_m','clinical_n','menopause','germline_brca_pathogenic','pd_l1_cps_ge10','residual_invasive_disease','metastatic_line','pik3ca_mutation','esr1_mutation','akt1_or_pten_alteration'],
'nexus_cervical_cancer_v2_2026.json': ['figo_stage','fertility_sparing_desired','lvsi','cone_margin_status','tumor_size_cm','depth_invasion_mm','histology','medically_operable','pelvic_nodes_positive','para_aortic_nodes_positive','positive_margin','positive_parametrium','distant_metastases','prior_pelvic_rt','recurrence_resectable_or_local_treatable','pd_l1_positive','msi_h_dmmr_or_tmbh','tmb_high','her2_positive','ntrk_fusion','ret_fusion','systemic_line'],
'nexus_gastric_cancer_v3_2026.json': ['clinical_t','clinical_n','clinical_m','potentially_resectable','medically_fit','path_margin','postop_received_preop_systemic','response_status','systemic_line','her2_positive','pd_l1_positive','msi_h_dmmr','cldn18_2_positive'],
'nexus_gastrointestinal_stromal_tumors_v1_2026.json': ['primary_site','tumor_size_cm','mitotic_rate_per_5mm2','genotype','resectable','significant_surgical_morbidity','response_status','postop_resection_complete','tumor_rupture','recurrence_risk','progression_extent','treatment_line','prior_tki'],
'nexus_hodgkin_lymphoma_v2_2026.json': ['histology','stage_group','risk_system','b_symptoms','esr_mm_hr','bulky_disease','nodal_region_count','e_lesion','age_over_60_or_unfit','pregnant','deauville','biopsy_result','transplant_candidate','relapse_timing','prior_autologous_hct','prior_bv','prior_cpi','asymptomatic_nlphl'],
'nexus_kidney_cancer_v1_2027.json': ['histology','clinical_t','clinical_n','clinical_m','resectable','postop_resection_complete','grade4_or_sarcomatoid','imdc_risk','hereditary_risk_criteria_met','metastasectomy_complete','prior_io','prior_vegf_tki','systemic_line'],
'nexus_myeloproliferative_neoplasms_v2_2026.json': ['subtype','mf_risk','symptomatic_splenomegaly_or_constitutional','constitutional_symptoms','symptomatic_splenomegaly','thrombosis_or_vascular_event','blast_percentage','prior_cytoreductive_inadequate_response','transplant_candidate','jak_inhibitor_prior']
}

def atoms(expr):
    if not expr:return []
    if 'fact' in expr:return [expr['fact']]
    if 'not' in expr:return atoms(expr['not'])
    out=[]
    for k in ('all','any'):
        for x in expr.get(k,[]):out+=atoms(x)
    return out

def used_refs(pkg):
    used={}
    def add(fid,where): used.setdefault(fid,[]).append(where)
    for nid,n in pkg.get('nodes',{}).items():
        if n.get('kind')=='decision':
            for f in atoms(n.get('expression',{})):add(f,'decision:'+nid)
        for o in n.get('recommendation',{}).get('options',[]):
            for f in atoms(o.get('applicability',{})):add(f,'option:'+nid+':'+str(o.get('option_id')))
    for r in pkg.get('derived_rules',[]):
        for f in atoms(r.get('when',{})):add(f,'derived:'+str(r.get('id')))
        if r.get('target_fact'):add(r['target_fact'],'derived_target:'+str(r.get('id')))
    for r in pkg.get('consistency_rules',[]):
        for f in atoms(r.get('when',{})):add(f,'consistency:'+str(r.get('id')))
    return used

def main():
    failed=0;report={}
    for fn,reqs in REQ.items():
        p=ENC/fn; pkg=json.loads(p.read_text()); defs={x['key']:x for x in pkg['fact_definitions']}; used=used_refs(pkg)
        invfacts={f for x in pkg.get('executable_decisions',[]) for f in x.get('input_fact_ids',[])}
        errs=[]
        for f in reqs:
            if f not in defs: errs.append('MISSING_FACT:'+f);continue
            if f not in used: errs.append('UNUSED:'+f)
            if f not in invfacts and defs[f].get('fact_role') not in {'DERIVED_DETERMINISTIC'}: errs.append('NOT_TESTED_IN_INVENTORY:'+f)
            if defs[f].get('fact_role') in {'DISPLAY_ONLY','PROVENANCE_ONLY','NON_ROUTING_CONTEXT'}: errs.append('BAD_ROLE:'+f+':'+str(defs[f].get('fact_role')))
        report[fn]={'required_facts':len(reqs),'errors':errs,'status':'PASS' if not errs else 'FAIL'}
        print(fn,report[fn]['status'],'required=',len(reqs),'errors=',len(errs))
        for e in errs: print('  ',e)
        failed += bool(errs)
    out=ROOT/'source_audit'/'MANDATORY_GAP_COVERAGE_REPORT.json';out.write_text(json.dumps({'packages':report,'failed_packages':failed},indent=2))
    print('FAILED_PACKAGES=',failed)
    raise SystemExit(1 if failed else 0)
if __name__=='__main__': main()
