from __future__ import annotations
import json
from pathlib import Path
from copy import deepcopy

ROOT=Path(__file__).resolve().parents[1]
ENC=ROOT/'backend/nexus/guidelines/encoded'
AMB=ROOT/'source_audit'/'SOURCE_AMBIGUITY_RECORDS.json'


def load(fn): return json.loads((ENC/fn).read_text())
def save(fn,p): (ENC/fn).write_text(json.dumps(p,indent=2,sort_keys=False))

def atom(f,op='eq',value=True,**kw):
    d={'fact':f,'op':op,'value':value}; d.update(kw); return d

def all_(*xs): return {'all':list(xs)}
def any_(*xs): return {'any':list(xs)}
def not_(x): return {'not':x}

def factdef(p,key):
    for d in p.get('fact_definitions',[]):
        if d.get('key')==key:return d
    raise KeyError(key)

def set_role(p,key,role,rationale=None):
    d=factdef(p,key); d['fact_role']=role
    if rationale:d['fact_role_rationale']=rationale

def add_fact(p,key,value_type='BOOLEAN',allowed=None,role='ROUTING',unknown=None,description=None):
    for d in p.get('fact_definitions',[]):
        if d.get('key')==key:
            d['value_type']=value_type; d['fact_role']=role
            if allowed is not None:d['allowed_values']=allowed
            if unknown is not None:d['semantic_unknown_values']=unknown
            if description:d['description']=description
            return
    d={'key':key,'value_type':value_type,'fact_role':role}
    if allowed is not None:d['allowed_values']=allowed
    if unknown is not None:d['semantic_unknown_values']=unknown
    if description:d['description']=description
    p.setdefault('fact_definitions',[]).append(d)

def prov(p,sec):
    cov=p.get('coverage',{}); meta=cov.get('primary_sections',{}).get(sec) or cov.get('supporting_sections',{}).get(sec) or {}
    pages=meta.get('pages',[])
    return {'guideline':p.get('title'),'version':p.get('version'),'section':sec,'page_label':sec,'physical_pages':pages,'source_anchor':f'{sec}:pages:{",".join(map(str,pages))}'}

def add_src(p,nid,*secs):
    n=p['nodes'][nid]; a=n.setdefault('source_pathways',[])
    for s in secs:
        if s not in a:a.append(s)

def add_support(p,nid,*secs):
    n=p['nodes'][nid]; r=n.setdefault('recommendation',{}); a=r.setdefault('supporting_sections',[])
    for s in secs:
        if s not in a:a.append(s)

def option(p,nid,oid):
    for o in p['nodes'][nid].get('recommendation',{}).get('options',[]):
        if o.get('option_id')==oid:return o
    raise KeyError((nid,oid))

def add_option(p,nid,oid,label,text,sec,app=None,pref=None,evidence=None,qualifiers=None,decision_relevant=True):
    opts=p['nodes'][nid].setdefault('recommendation',{}).setdefault('options',[])
    for o in opts:
        if o.get('option_id')==oid:return o
    o={'option_id':oid,'label':label,'text':text,'decision_relevant':decision_relevant,'source_provenance':prov(p,sec)}
    if app is not None:o['applicability']=app
    if pref:o['preference_category']=pref
    if evidence:o['evidence_category']=evidence
    if qualifiers:o['qualifiers']=qualifiers
    opts.append(o); return o

def and_app(o,expr):
    old=o.get('applicability')
    o['applicability']=expr if not old else all_(old,expr)

def decision(p,nid,label,expr,t,f,secs,decision_id=None):
    p['nodes'][nid]={'kind':'decision','label':label,'expression':expr,'on':{'TRUE':t,'FALSE':f},'source_pathways':list(secs),'decision_id':decision_id or nid}

def action(p,nid,label,secs,options=None,support=None,pathway_id=None,next_steps=None):
    p['nodes'][nid]={'kind':'action','label':label,'status':'RECOMMENDATION','recommendation_id':nid,'source_pathways':list(secs),'recommendation':{'title':label,'options':options or [],'supporting_sections':support or [],'next_steps':next_steps or []}}
    if pathway_id:p['nodes'][nid]['pathway_id']=pathway_id

def ambiguity(records,pkg,decision,sec,issue,behavior):
    rec={'guideline_id':pkg.get('guideline_id'),'version':pkg.get('version'),'source_section':sec,'decision':decision,'ambiguity':issue,'fail_closed_behavior':behavior}
    if rec not in records:records.append(rec)

def add_consistency(p,rid,expr,message,secs):
    arr=p.setdefault('consistency_rules',[])
    if not any(r.get('id')==rid for r in arr):arr.append({'id':rid,'when':expr,'message':message,'source_pathways':list(secs)})


def patch_all(records):
    fn='nexus_acute_lymphoblastic_leukemia_v2_2026.json'; p=load(fn)
    add_src(p,'diag','ALL-1A'); add_src(p,'workup','ALL-1A','ALL-2A'); add_support(p,'workup','ALL-1A','ALL-2A')
    for nid in ['bph_phase','bph_response','bph_mrd','bph_mrdpos_confirm','bph_initial','bph_mrdpos','bph_mrdneg']:
        if nid in p['nodes']: add_src(p,nid,'ALL-4A')
    for nid in ['bph_initial','bph_mrdpos','bph_mrdneg']:
        if nid in p['nodes']: add_support(p,nid,'ALL-4A')
    # ALL-8 explicitly distinguishes first post-remission consolidative HCT from relapse after prior allogeneic HCT.
    for nid,oid in [('rr_phplus','all_rr_phplus_hct'),('rr_phnegative','all_rr_bneg_hct'),('rr_tall','all_rr_t_hct')]:
        if nid in p['nodes']:
            and_app(option(p,nid,oid),atom('prior_hct','eq',False))
            add_option(p,nid,oid+'_second','Second allogeneic HCT and/or donor lymphocyte infusion','For relapse after prior allogeneic HCT, a second HCT and/or DLI can be considered when clinically appropriate.','ALL-8',app=all_(atom('transplant_candidate','eq',True),atom('prior_hct','eq',True)))
    save(fn,p)


def patch_aml(records):
    fn='nexus_acute_myeloid_leukemia_v5_2026.json'; p=load(fn)
    add_src(p,'postind_response','AML-3A'); add_src(p,'intensive_reind_cpx','AML-3A'); add_src(p,'reind_cpx','AML-3A'); add_src(p,'reind_other','AML-3A')
    add_support(p,'reind_cpx','AML-3A'); add_support(p,'reind_other','AML-3A')
    # prior_cpx351 is semantically redundant with induction_regimen=CPX351, which is the canonical decision-driving fact.
    set_role(p,'prior_cpx351','PROVENANCE_ONLY','Redundant historical representation; executable reinduction routing uses canonical induction_regimen=CPX351 per AML-3/AML-3A.')
    # Source uses qualitative "long first remission" with no numeric cutoff. Do not guess from relapse_interval_months.
    set_role(p,'relapse_interval_months','NON_ROUTING_CONTEXT','AML-9 describes long versus relatively short first remission without a numeric month threshold; raw interval is retained but not converted into an unsupported cutoff.')
    add_fact(p,'long_first_remission_confirmed','BOOLEAN',role='OPTION_APPLICABILITY',description='Human/source-context determination that first remission is long enough for source-described reinduction consideration; no numeric cutoff is invented.')
    ambiguity(records,p,'AML-9 long-versus-short first-remission distinction','AML-9','The guideline uses qualitative long/relatively short first remission without defining a numeric threshold on this page.','Do not derive from relapse_interval_months. Require explicit long_first_remission_confirmed if re-use/reinduction applicability depends on it.')
    # Add a source-specific cytotoxic reinduction option constrained by the explicit qualitative state and not prior targeted resistance.
    for nid in ['rr_npm1_action','rr_kmt2a_action','rr_flt3_action','rr_idh1_action','rr_idh2_action','rr_cd33_action','rr_other']:
        if nid in p['nodes']:
            add_option(p,nid,'aml_rr_reinduction_long','Reinduction with a previously effective cytotoxic regimen','AML-9 allows reinduction in certain circumstances such as a long first remission; this does not authorize automatic targeted-agent reuse.','AML-9',app=atom('long_first_remission_confirmed','eq',True))
    # Source explicitly restricts targeted-agent re-use when stopped for clinical resistance. Apply only to a dedicated re-challenge option.
    set_role(p,'prior_targeted_therapy_resistance','OPTION_APPLICABILITY','Used only to determine whether a targeted agent may be retried; it does not suppress first exposure to a different targeted agent.')
    add_fact(p,'targeted_agent_rechallenge_considered','BOOLEAN',role='OPTION_APPLICABILITY')
    for nid in ['rr_npm1_action','rr_kmt2a_action','rr_flt3_action','rr_idh1_action','rr_idh2_action']:
        if nid in p['nodes']:
            add_option(p,nid,'aml_rr_targeted_rechallenge','Rechallenge a previously used targeted agent','AML-9 permits targeted-therapy retry only if it was not administered continuously and was not stopped for clinical resistance.','AML-9',app=all_(atom('targeted_agent_rechallenge_considered','eq',True),atom('prior_targeted_therapy_resistance','eq',False)))
    # AML-7 post-chemotherapy FLT3 maintenance: prior FLT3 inhibitor + no planned HCT is a source condition.
    add_fact(p,'flt3_itd','BOOLEAN',role='OPTION_APPLICABILITY',description='FLT3 internal tandem duplication (ITD) is explicitly distinguished from other FLT3 alterations for AML-7/AML-E option applicability.')
    set_role(p,'prior_flt3_inhibitor','OPTION_APPLICABILITY','AML-7 explicitly uses prior FLT3-inhibitor exposure in the post-chemotherapy maintenance route.')
    if p['nodes']['maintenance_router']['on']['FALSE']=='maintenance_nohct':
        p['nodes']['maintenance_router']['on']['FALSE']='maintenance_nohct_flt3_history'
    decision(p,'maintenance_nohct_flt3_history','History of FLT3 mutation with prior FLT3 inhibitor and no allogeneic HCT planned?',all_(atom('flt3_mutation','eq',True),atom('prior_flt3_inhibitor','eq',True),atom('transplant_candidate','eq',False)),'maintenance_flt3_postchemo','maintenance_nohct',['AML-7'],'aml_postchemo_flt3_maintenance_eligibility')
    action(p,'maintenance_flt3_postchemo','Post-chemotherapy AML in remission with prior FLT3 inhibitor and no planned allogeneic HCT: FLT3-directed maintenance per AML-7.',['AML-7'],support=['AML-E'],pathway_id='AML_POSTCHEMO_FLT3_MAINT')
    add_option(p,'maintenance_flt3_postchemo','aml_postchemo_quiz','Quizartinib','Preferred for FLT3-ITD in the source-defined maintenance context.','AML-7',app=atom('flt3_itd','eq',True),pref='PREFERRED')
    add_option(p,'maintenance_flt3_postchemo','aml_postchemo_mido','Midostaurin','Option for FLT3-ITD or FLT3-TKD in the source-defined maintenance context.','AML-7',app=atom('flt3_mutation','eq',True))
    save(fn,p)


def patch_bcell(records):
    fn='nexus_b_cell_lymphomas_v4_2026.json'; p=load(fn)
    # GCB vs non-GCB is required diagnostic characterization but HGBL/DLBCL source does not make the broad GCB label alone a top-level treatment branch.
    set_role(p,'gcb_subtype','NON_ROUTING_CONTEXT','BCEL-1 requires GCB versus non-GCB characterization; the encoded primary DLBCL route is driven by stage/response/relapse and specific rearrangements rather than GCB label alone.')
    # Explicit HGBL MYC/BCL6 distinction.
    if 'hgbl_entry' in p['nodes']:
        p['nodes']['hgbl_entry']['on']['FALSE']='hgbl_bcl6'
        decision(p,'hgbl_bcl6','HGBL with MYC and BCL6 rearrangements (without MYC/BCL2 double-hit)?',atom('hgbcl_bcl6_rearranged','eq',True),'hgbl_bcl6_action','hgbl_other',['HGBL-1'],'bcell_hgbl_myc_bcl6')
        action(p,'hgbl_bcl6_action','HGBL with MYC and BCL6 rearrangements: source notes DLBCL-NOS-like outcomes but uncertain optimal chemotherapy; clinical trial and DLBCL/HGBL regimens with early-stage ISRT consideration.',['HGBL-1'],support=['BCEL-C','NHODG-D'],pathway_id='BCELL_HGBL_MYC_BCL6')
        add_option(p,'hgbl_bcl6_action','hgbl_bcl6_trial','Clinical trial','Recommended.','HGBL-1',pref='PREFERRED')
        add_option(p,'hgbl_bcl6_action','hgbl_bcl6_daepochr','DA-EPOCH + rituximab','Source-listed induction option.','HGBL-1')
        add_option(p,'hgbl_bcl6_action','hgbl_bcl6_polarchp','Pola-R-CHP','Category 2B source-listed option.','HGBL-1',evidence='CATEGORY_2B')
        add_option(p,'hgbl_bcl6_action','hgbl_bcl6_rchop','CHOP + rituximab','Source-listed induction option.','HGBL-1')
        add_option(p,'hgbl_bcl6_action','hgbl_bcl6_isrt','Consolidative ISRT','Consider for early-stage disease.','HGBL-1',app=atom('stage_group','eq','LIMITED'))
    # single-field RT feasibility is relevant to localized extranodal MZL sites; use as option applicability wherever a one-field local route is represented.
    # In the executable package the broad local RT choice is expressed on MZL localized actions.
    used=False
    for nid,n in p['nodes'].items():
        if n.get('kind')!='action':continue
        if any(s in n.get('source_pathways',[]) for s in ['EMZLNG-1','EMZLNG-2','EMZLNG-3','NMZL-2','FOLL-3']):
            for o in n.get('recommendation',{}).get('options',[]):
                if 'ISRT' in o.get('label','') or 'radiation' in o.get('label','').lower():
                    and_app(o,atom('single_field_rt_feasible','eq',True)); used=True
    if not used:
        # Retain as non-routing if no explicit one-field decision exists in the selected primary route.
        set_role(p,'single_field_rt_feasible','NON_ROUTING_CONTEXT','No standalone one-field feasibility branch is defined in the encoded primary algorithm; local RT options already require multidisciplinary site-specific feasibility.')
    # Prior HDT/ASCR changes interpretation of later-line relapse options; expose options that are specifically valid after transplant.
    for nid in ['dlbcl_third_plus']:
        if nid in p['nodes']:
            add_option(p,nid,'dlbcl_post_ascr_bispecific','Bispecific antibody therapy','Source includes bispecific therapy for disease progression after transplant or CAR T-cell therapy.','BCEL-C',app=atom('prior_hdt_ascr','eq',True),pref='PREFERRED')
            add_option(p,nid,'dlbcl_post_ascr_selinexor','Selinexor','Source lists selinexor including after disease progression following transplant or CAR T-cell therapy.','BCEL-C',app=atom('prior_hdt_ascr','eq',True))
    save(fn,p)


def patch_bcc(records):
    fn='nexus_basal_cell_skin_cancer_v1_2027.json'; p=load(fn)
    add_src(p,'low_primary','BCC-3A'); add_src(p,'low_posmargin','BCC-3A'); add_support(p,'low_primary','BCC-3A'); add_support(p,'low_posmargin','BCC-3A')
    set_role(p,'high_risk_any','PROVENANCE_ONLY','The executable BCC-2 risk decision directly evaluates every source-defined high-risk factor; this summary field is not accepted from extraction as guideline authority.')
    # local_recurrence may independently signal current recurrence; combine with episode state rather than ignore it.
    p['nodes']['care_recur']['expression']=any_(p['nodes']['care_recur']['expression'],atom('local_recurrence','eq',True))
    # prior_hhi independently controls HHI-naive vs exposed option filtering; current HHI progression/intolerance already routes second-line.
    for nid in ['nodal','met']:
        if nid in p['nodes']:
            for o in p['nodes'][nid].get('recommendation',{}).get('options',[]):
                lab=o.get('label','').lower()
                if 'vismodegib' in lab or 'sonidegib' in lab or 'hedgehog' in lab:
                    and_app(o,atom('prior_hhi','eq',False))
                if 'cemiplimab' in lab:
                    and_app(o,atom('prior_hhi','eq',True))
    # If those actions have catalog-like unlabeled systemic options, add exact exposure-sensitive options.
    for nid in ['nodal','met']:
        if nid in p['nodes']:
            add_option(p,nid,f'bcc_{nid}_hhi','Hedgehog pathway inhibitor','For HHI-naive advanced BCC where source lists HHI.','BCC-D',app=atom('prior_hhi','eq',False),pref='PREFERRED')
            add_option(p,nid,f'bcc_{nid}_cemip','Cemiplimab-rwlc','For second-line/HHI-intolerant or source-defined advanced disease after HHI exposure.','BCC-D',app=atom('prior_hhi','eq',True),pref='PREFERRED')
    save(fn,p)


def patch_biliary(records):
    fn='nexus_biliary_tract_cancers_v1_2026.json'; p=load(fn)
    # presentation jaundice/obstruction explicitly routes gallbladder/extrahepatic workup.
    if 'gb_mass' in p['nodes']:
        p['nodes']['gb_mass']['expression']=any_(p['nodes']['gb_mass']['expression'],atom('jaundice_or_biliary_obstruction','eq',True))
    # Use canonical duplicated post-op fields instead of leaving them unused: consistency catches disagreement with primary postresection facts.
    add_consistency(p,'btc_margin_duplicate_conflict',all_(atom('margin_status','neq','UNKNOWN'),atom('post_resection_margin','neq','UNKNOWN'),not_({'any':[all_(atom('margin_status','eq','R0'),atom('post_resection_margin','eq','R0')),all_(atom('margin_status','eq','R1'),atom('post_resection_margin','eq','R1')),all_(atom('margin_status','eq','R2'),atom('post_resection_margin','eq','R2'))]})),'Duplicate postoperative margin facts disagree; reconcile source pathology before routing.',['GALL-6','INTRA-2','EXTRA-2'])
    # Mark redundant aliases as provenance-only when a more specific canonical fact drives the graph.
    set_role(p,'gallbladder_t_stage','PROVENANCE_ONLY','Canonical postresection gallbladder routing uses pathologic_t; gallbladder_t_stage is retained as source-normalization provenance.')
    set_role(p,'margin_status','PROVENANCE_ONLY','Canonical postresection routing uses post_resection_margin; generic margin_status is retained for provenance/normalization.')
    set_role(p,'nodes_positive','PROVENANCE_ONLY','Canonical postoperative routing uses node_positive; plural alias retained for provenance/normalization.')
    # cis_at_margin changes extrahepatic postoperative chemoradiation consideration. Add explicit option applicability on postoperative eCCA action if present.
    candidates=[nid for nid,n in p['nodes'].items() if n.get('kind')=='action' and 'EXTRA-2' in n.get('source_pathways',[])]
    for nid in candidates:
        add_option(p,nid,'btc_extra_cis_margin_crt','Fluoropyrimidine-based chemoradiation','Source postoperative extrahepatic route considers chemoradiation for R1/CIS-at-margin contexts.','EXTRA-2',app=atom('cis_at_margin','eq',True))
    # generic molecular_actionable_alteration is only a summary. Exact biomarkers drive option applicability.
    set_role(p,'molecular_actionable_alteration','PROVENANCE_ONLY','Exact biomarker facts (FGFR2, IDH1, HER2, BRAF, NTRK, RET, KRAS G12C, NRG1, MSI/dMMR/TMB) drive option applicability; this summary is not guideline authority.')
    # Performance status is a contextual selector in systemic-therapy principles; gate an intensive doublet/triplet catalog option only if explicit. Otherwise retain as non-routing context.
    set_role(p,'performance_status_good','NON_ROUTING_CONTEXT','BIL-C requires regimen selection in clinical context; no single binary performance-status threshold is specified for all listed regimens, so the generic boolean is not used to invent exclusions.')
    # progression is equivalent to subsequent-line state when current treatment_line is not already explicit.
    if 'sys_line' in p['nodes']:
        # treatment line remains authoritative; add consistency rather than override.
        add_consistency(p,'btc_progression_firstline_conflict',all_(atom('disease_progression','eq',True),atom('treatment_line','eq','FIRST')),'Documented progression conflicts with FIRST-line current treatment state; reconcile line/episode before option routing.',['BIL-C'])
    save(fn,p)


def patch_bladder(records):
    fn='nexus_bladder_cancer_v3_2026.json'; p=load(fn)
    # Continuation upper-tract pages are active algorithm pages; attach to corresponding site nodes/actions.
    for nid in ['utt','utt_grade','utt_low','utt_high']:
        add_src(p,nid,'UTT-2','UTT-4')
        if p['nodes'][nid].get('kind')=='action':add_support(p,nid,'UTT-2','UTT-4')
    # histology distinguishes urothelial from non-urothelial. Existing urothelial_histology fact is canonical; retain generic alias as provenance only.
    set_role(p,'histology','PROVENANCE_ONLY','Primary bladder routing uses canonical urothelial_histology; generic histology is retained for pathology provenance.')
    # NMIBC risk variables: if explicit nmibc_risk is unknown, source raw grade/CIS should at minimum prevent false low-risk treatment.
    if 'nmibc_risk_decision' in p['nodes']:
        add_consistency(p,'bladder_cis_lowrisk_conflict',all_(atom('cis_present','eq',True),atom('nmibc_risk','eq','LOW')),'CIS cannot be treated as source low-risk NMIBC; reconcile risk assignment.',['BL-2'])
        add_consistency(p,'bladder_highgrade_lowrisk_conflict',all_(atom('tumor_grade','eq','HIGH'),atom('nmibc_risk','eq','LOW')),'High-grade disease conflicts with low-risk NMIBC assignment.',['BL-2'])
    # Adequate BCG is necessary to call a case BCG-unresponsive. Guard unresponsive branch.
    if 'bcg_state' in p['nodes']:
        add_consistency(p,'bladder_bcg_unresponsive_without_adequate_bcg',all_(atom('bcg_status','eq','UNRESPONSIVE'),atom('adequate_bcg_received','eq',False)),'BCG-unresponsive state requires adequate prior BCG exposure per BL-F.',['BL-F','BL-2'])
    # upper tract site/detail facts affect kidney-sparing strategy.
    for nid in ['utt_low']:
        if nid in p['nodes']:
            add_option(p,nid,'utt_low_nephron_sparing','Kidney-/nephron-sparing management','Favor source-defined endoscopic/segmental strategies when nephron preservation is required/preferred and oncologically feasible.','UTT-2',app=atom('nephron_sparing_required_or_preferred','eq',True))
    # Use upper_tract_location and urethral_location in deterministic decisions by adding source-specific subroutes.
    if 'utt_low' in p['nodes']:
        old=deepcopy(p['nodes']['utt_low']); p['nodes']['utt_low_base']=old
        p['nodes']['utt_low']={'kind':'decision','label':'Low-grade upper-tract tumor location defined?','expression':atom('upper_tract_location','in',['RENAL_PELVIS','UPPER_URETER','MID_URETER','DISTAL_URETER']),'on':{'TRUE':'utt_low_base','FALSE':'utt_low_need_location'},'source_pathways':['UTT-1','UTT-2','UTT-3','UTT-4'],'decision_id':'bladder_utt_low_location'}
        p['nodes']['utt_low_need_location']={'kind':'status','label':'Upper-tract location is required to select the precise kidney-/ureter-sparing procedure.','status':'NEEDS_INFORMATION','source_pathways':['UTT-2','UTT-4']}
    # Primary urethral location matters in PCU algorithm; if a pcu action exists, require known location before local route.
    for nid in list(p['nodes']):
        if nid.startswith('pcu_') and p['nodes'][nid].get('kind')=='action' and 'PCU-1' in p['nodes'][nid].get('source_pathways',[]):
            for o in p['nodes'][nid].get('recommendation',{}).get('options',[]):
                if not o.get('applicability'):
                    o['applicability']=atom('urethral_location','in',['MALE_PENDULOUS','MALE_BULBAR','FEMALE'])
    save(fn,p)


def patch_bone(records):
    fn='nexus_bone_cancer_v1_2027.json'; p=load(fn)
    # Generic grade/location aliases are captured by subtype-specific canonical facts in each tumor family.
    set_role(p,'grade_group','PROVENANCE_ONLY','Subtype-specific grade/histology facts drive CHON/OSTEO decisions; generic grade_group is retained for pathology provenance.')
    set_role(p,'location','PROVENANCE_ONLY','Subtype-specific anatomic facts (chondrosarcoma/chordoma/primary-site facts) drive branches; generic location is provenance context.')
    # Chordoma site is relevant to local surgery/RT technique but the primary executable route uses resectability/margins. Attach as option applicability for local modality notes.
    for nid in ['chor_surg_margin','chor_defrt','chor_adjrt','chor_surv']:
        if nid in p['nodes'] and p['nodes'][nid].get('kind')=='action':
            add_option(p,nid,'chordoma_site_specific_planning','Site-specific multidisciplinary local planning','Chordoma surgery/RT technique and feasibility are site-dependent (sacral/mobile spine/skull-base).','CHOR-2',app=atom('chordoma_site','in',['SACROCOCCYGEAL','MOBILE_SPINE','SKULL_BASE_CLIVAL']))
    # Primary-site control explicitly determines metastatic Ewing local therapy; if generic fact is not used by existing route, add option gate to metastatic action(s).
    for nid,n in p['nodes'].items():
        if n.get('kind')=='action' and 'EW-3' in n.get('source_pathways',[]):
            add_option(p,nid,'ew_met_primary_control','Definitive local control of primary site','Use surgery and/or RT to primary site when source-defined; applicability depends on whether primary is already controlled.','EW-3',app=atom('primary_site_controlled','eq',False))
    # GCTB axial unresectable state favors denosumab/embolization/RT/ablation route; include as an independent route trigger and prior denosumab exposure for recurrence choice.
    if 'gctb_resect' in p['nodes']:
        p['nodes']['gctb_resect']['expression']=all_(p['nodes']['gctb_resect']['expression'],atom('gctb_axial_unresectable','eq',False))
    if 'gctb_rec' in p['nodes']:
        add_option(p,'gctb_rec','gctb_rec_denosumab_reuse','Denosumab','Use/re-use only when source-appropriate and not already failed/intolerant.','GCTB-3',app=atom('denosumab_prior','eq',False))
    # Periosteal osteosarcoma is source-recognized; ensure high-grade pathway accounts for it rather than leaving the fact unused.
    if 'osteo_low' in p['nodes']:
        p['nodes']['osteo_low']['expression']=all_(p['nodes']['osteo_low']['expression'],atom('osteo_periosteal','eq',False))
    save(fn,p)


def patch_breast(records):
    fn='nexus_breast_cancer_v6_2026.json'; p=load(fn)
    add_src(p,'surv','BINV-28'); add_support(p,'surv','BINV-28')
    # Remove literal DEFERRED marker from a valid internal pregnancy action; source specifies RT postpartum timing.
    if 'preg_later' in p['nodes']:
        p['nodes']['preg_later']['label']=p['nodes']['preg_later']['label'].replace('deferred until postpartum','postponed until postpartum')
        p['nodes']['preg_later']['recommendation']['title']=p['nodes']['preg_later']['label']
    # Clinical T/N are current presentation facts. Use them in consistency and high-risk pre/post-neoadjuvant definitions rather than leave unused.
    add_consistency(p,'breast_metastatic_tn_local_conflict',all_(atom('treatment_phase','eq','METASTATIC'),atom('clinical_t','eq','TX'),atom('clinical_n','eq','NX')),'Metastatic disease may be valid with TX/NX, but local stage is unresolved; local-treatment components must not be inferred.',['BINV-18','BINV-21'])
    # High-risk HER2 residual disease definition uses initial cT/cN/ypN. Add deterministic high-risk derivation where source criteria are expressible.
    p.setdefault('derived_rules',[])
    if not any(r.get('id')=='breast_her2_highrisk_initial_cT4' for r in p['derived_rules']):
        p['derived_rules'] += [
          {'id':'breast_her2_highrisk_initial_cT4','target_fact':'high_risk_recurrence','value':True,'when':atom('clinical_t','eq','T4'),'source_pathways':['BINV-M']},
          {'id':'breast_her2_highrisk_initial_cN23','target_fact':'high_risk_recurrence','value':True,'when':atom('clinical_n','in',['N2','N3']),'source_pathways':['BINV-M']},
          {'id':'breast_her2_highrisk_residual_node','target_fact':'high_risk_recurrence','value':True,'when':atom('pathologic_node_status','eq','N_POSITIVE'),'source_pathways':['BINV-M','BINV-16']},
        ]
    # HER2-ultralow is relevant to endocrine-refractory HR+ metastatic T-DXd eligibility in source systemic tables. Add an exact later-line option.
    if 'met_hrpos_later' in p['nodes']:
        add_option(p,'met_hrpos_later','breast_hrlater_tdx_low_ultralow','Fam-trastuzumab deruxtecan-nxki','Source metastatic tables include HER2-low/ultralow eligibility in the applicable HR-positive endocrine-refractory setting.','BINV-Q',app=any_(atom('her2_low','eq',True),atom('her2_ultralow','eq',True)))
    # Prior checkpoint exposure: do not repeat PD-1/PD-L1 after progression when source table excludes reuse. Apply to TNBC checkpoint options.
    if 'tnbc_first_pdl1pos' in p['nodes']:
        for o in p['nodes']['tnbc_first_pdl1pos']['recommendation']['options']:
            and_app(o,atom('prior_pd1_pdl1_inhibitor','eq',False))
    # Prior HER2 exposure is relevant to later-line state; add an explicit consistency/eligibility fact rather than show all later-line catalog blindly.
    if 'met_her2_later' in p['nodes']:
        for o in p['nodes']['met_her2_later']['recommendation']['options']:
            if o.get('option_id') in {'breast_her2_later_tuc','breast_her2_later_tdx','breast_her2_later_tdm1'}:
                and_app(o,atom('prior_her2_targeted_therapy','eq',True))
    save(fn,p)


def patch_cervical(records):
    fn='nexus_cervical_cancer_v2_2026.json'; p=load(fn)
    for nid in ['fert_cons','fert_cons_action','early_ia2','early_cons_action']:
        if nid in p['nodes']:add_src(p,nid,'CERV-2A','CERV-3A')
    for nid in ['fert_cons_action','early_cons_action']:
        if nid in p['nodes']:add_support(p,nid,'CERV-2A','CERV-3A')
    # Conservative surgery criteria are source-defined by tumor size <=2 cm and DOI <=10 mm in addition to existing margin/LVSI/histology/imaging facts.
    # Make the raw numeric facts independently safety-critical; a precomputed conservative_surgery_criteria_met cannot override them.
    add_consistency(p,'cerv_conservative_size_conflict',all_(atom('conservative_surgery_criteria_met','eq',True),atom('tumor_size_cm','gt',2)),'Conservative-surgery flag conflicts with source criterion tumor size <=2 cm.',['CERV-2','CERV-4','CERV-C'])
    add_consistency(p,'cerv_conservative_doi_conflict',all_(atom('conservative_surgery_criteria_met','eq',True),atom('depth_invasion_mm','gt',10)),'Conservative-surgery flag conflicts with source criterion depth of invasion <=10 mm.',['CERV-2','CERV-4','CERV-C'])
    # Replace positive conservative decision with all explicit source criteria that are currently represented.
    for nid in ['fert_cons','early_ia2']:
        if nid in p['nodes']:
            p['nodes'][nid]['expression']=all_(p['nodes'][nid]['expression'],atom('tumor_size_cm','lte',2),atom('depth_invasion_mm','lte',10))
    save(fn,p)


def patch_gastric(records):
    fn='nexus_gastric_cancer_v3_2026.json'; p=load(fn)
    add_src(p,'scope','GAST-1A'); add_src(p,'initial_stage','GAST-1A')
    # clinical N participates in preoperative regimen evidence/preference and initial resectable risk.
    if 'preop' in p['nodes']:
        for o in p['nodes']['preop'].get('recommendation',{}).get('options',[]):
            if 'durvalumab' in o.get('label','').lower():
                # source notes category 2A for clinically node-negative tumor as one subgroup.
                o.setdefault('qualifiers',[])
                q=o['qualifiers']
                txt='Clinical node-negative status is a source-defined evidence/preference qualifier.'
                if txt not in q:q.append(txt)
                if not o.get('applicability'):o['applicability']=atom('clinical_n','in',['N0','N_POS'])
    # path_stage_risk is redundant with explicit pathologic T/N fields; keep provenance only rather than synthetic authority.
    set_role(p,'path_stage_risk','PROVENANCE_ONLY','Postoperative decisions are driven by explicit pathologic T/N/margin facts; summary risk is retained for provenance.')
    # Source does not contain an FGFR2b-directed gastric option in this version's extracted systemic table; do not invent one.
    set_role(p,'fgfr2b_positive','NON_ROUTING_CONTEXT','No FGFR2b-directed treatment branch was identified in the authorized Gastric v3.2026 source extracts; fact retained without inventing therapy.')
    # Prior exposure gates later-line re-use/source sequence.
    if 'pall_later' in p['nodes']:
        for o in p['nodes']['pall_later']['recommendation']['options']:
            lab=o.get('label','').lower(); oid=o.get('option_id','')
            if 'her2' in lab or 'trastuz' in lab: and_app(o,atom('prior_trastuzumab','eq',True))
            if 'checkpoint' in lab or 'immun' in lab: and_app(o,atom('prior_immunotherapy','eq',False))
            if 'cldn' in lab or 'zolbetux' in lab: and_app(o,atom('prior_cldn18_2_therapy','eq',False))
    # Ensure these exposure facts participate even if labels are generic by adding explicit applicability options.
    add_option(p,'pall_later','gastric_later_post_trastuzumab_her2','HER2-directed later-line therapy after trastuzumab exposure','For HER2-positive disease after prior trastuzumab, use source-listed later-line HER2-directed therapy.','GAST-F',app=all_(atom('her2_positive','eq',True),atom('prior_trastuzumab','eq',True)))
    add_option(p,'pall_later','gastric_later_ici_if_naive','Checkpoint inhibitor option when source biomarker-eligible and not previously used','Avoid presenting this as a re-use option after prior immunotherapy unless source specifically supports it.','GAST-F',app=all_(any_(atom('msi_h_dmmr','eq',True),atom('pd_l1_positive','eq',True)),atom('prior_immunotherapy','eq',False)))
    add_option(p,'pall_later','gastric_later_cldn_if_naive','CLDN18.2-directed therapy when source-eligible and not previously used','Only for CLDN18.2-positive disease without prior CLDN18.2-directed therapy.','GAST-F',app=all_(atom('cldn18_2_positive','eq',True),atom('prior_cldn18_2_therapy','eq',False)))
    save(fn,p)


def patch_gist(records):
    fn='nexus_gastrointestinal_stromal_tumors_v1_2026.json'; p=load(fn)
    # Small-gastric-GIST decision must be derived from explicit site and size, not a synthetic opaque flag alone.
    add_consistency(p,'gist_small_gastric_flag_conflict_site',all_(atom('small_gastric_gist_lt2cm','eq',True),atom('primary_site','neq','STOMACH')),'Small gastric GIST flag conflicts with non-stomach primary site.',['GIST-1'])
    add_consistency(p,'gist_small_gastric_flag_conflict_size',all_(atom('small_gastric_gist_lt2cm','eq',True),atom('tumor_size_cm','gte',2)),'Small gastric GIST flag conflicts with tumor size >=2 cm.',['GIST-1'])
    p['nodes']['initial_small']['expression']=all_(atom('primary_site','eq','STOMACH'),atom('tumor_size_cm','lt',2))
    # Recurrence risk is source-derived from site, size, and mitotic rate. We cannot replace detailed risk tables with a guessed numeric formula; require current risk classification but use raw variables for safety and explanation.
    add_consistency(p,'gist_high_mitosis_lowrisk_conflict',all_(atom('mitotic_rate_per_5mm2','gt',5),atom('recurrence_risk','in',['VERY_LOW','LOW'])),'High mitotic rate conflicts with a very-low/low recurrence-risk assignment; re-evaluate source risk table using site and size.',['GIST-A','GIST-3'])
    # Treatment line must agree with prior TKI exposure.
    add_consistency(p,'gist_secondline_without_prior_tki',all_(atom('treatment_line','in',['SECOND','THIRD','FOURTH_PLUS']),atom('prior_tki','eq','NONE')),'Second/later-line GIST cannot be selected with no prior TKI exposure.',['GIST-E','GIST-5'])
    # Prior TKI exact exposure filters standard sequence.
    if 'adv_second' in p['nodes']:
        for o in p['nodes']['adv_second']['recommendation']['options']:
            and_app(o,atom('prior_tki','eq','IMATINIB'))
    if 'adv_third' in p['nodes']:
        for o in p['nodes']['adv_third']['recommendation']['options']:
            and_app(o,atom('prior_tki','in',['SUNITINIB','OTHER']))
    if 'adv_fourth' in p['nodes']:
        # fourth line requires established prior TKI history; keep broad because one scalar cannot represent full sequence.
        for o in p['nodes']['adv_fourth']['recommendation']['options']:
            and_app(o,atom('prior_tki','neq','NONE'))
    save(fn,p)


def patch_hodgkin(records):
    fn='nexus_hodgkin_lymphoma_v2_2026.json'; p=load(fn)
    # Attach continuation primary pages to the decisions/actions they continue.
    mapping={
      'HODG-1A':['scope','hist_nlphl','hist_chl'],
      'HODG-3A':['early_risk_system','early_fav_dec','early_unfav_confirm'],
      'HODG-6A':['early_unfav'], 'HODG-6B':['early_unfav','resp_adv_unfav','resp_45','resp_biopsy'],
      'HODG-7A':['adv_initial','resp_adv_unfav','resp_45','resp_biopsy'],
      'HODG-7B':['adv_initial','resp_adv_unfav','resp_45','resp_biopsy'],
      'HODG-7C':['adv_initial','resp_adv_unfav','resp_45','resp_biopsy'],
      'HODG-7D':['adv_initial','resp_adv_unfav','resp_45','resp_biopsy'],
    }
    for sec,nids in mapping.items():
        for nid in nids:
            if nid in p['nodes']:
                add_src(p,nid,sec)
                if p['nodes'][nid].get('kind')=='action':add_support(p,nid,sec)
    # HODG-2/HODG-3 make bulky mediastinal disease an early unfavorable criterion.
    # Keep the guideline decision as a deterministic `early_favorable` fact rather than introducing an LLM-selected risk-route fact.
    p.setdefault('derived_rules',[])
    for r in p['derived_rules']:
        if r.get('id') in {'hodg_fav_ghsg','hodg_fav_eortc'}:
            w=r.get('when',{})
            if 'all' in w and not any(x.get('fact')=='mediastinal_bulk' for x in w['all'] if isinstance(x,dict)):
                w['all'].append(atom('mediastinal_bulk','eq',False))
        if r.get('id')=='hodg_fav_ghsg':
            w=r.get('when',{})
            if 'all' in w and not any(x.get('fact')=='e_lesion' for x in w['all'] if isinstance(x,dict)):
                w['all'].append(atom('e_lesion','eq',False))
        if r.get('id')=='hodg_fav_eortc':
            w=r.get('when',{})
            if 'all' in w and not any(x.get('fact')=='age_years' for x in w['all'] if isinstance(x,dict)):
                w['all'].append(atom('age_years','lt',50))
    # Remove any prior invalid synthetic target and encode unfavorable mediastinal bulk as early_favorable=False.
    p['derived_rules']=[r for r in p['derived_rules'] if r.get('id')!='hodg_unfav_mediastinal_bulk']
    p['derived_rules'].append({'id':'hodg_unfav_mediastinal_bulk','target_fact':'early_favorable','value':False,'when':atom('mediastinal_bulk','eq',True),'source_pathways':['HODG-2','HODG-3','HODG-3A']})
    # Age changes regimen applicability in source age-stratified pathways; constrain the adult 18-60 regimens represented by HODG-5/6/7.
    for nid in ['ghsg_fav','eortc_fav_action','early_unfav','adv_initial']:
        if nid in p['nodes'] and p['nodes'][nid].get('kind')=='action':
            for o in p['nodes'][nid].get('recommendation',{}).get('options',[]):
                if not o.get('applicability'):
                    o['applicability']=all_(atom('age_years','gte',18),atom('age_years','lte',60))
    # current_response is redundant with Deauville/biopsy response facts in PET-adapted branches.
    set_role(p,'current_response','PROVENANCE_ONLY','PET-adapted CHL decisions use current Deauville and biopsy status; generic current_response is retained for longitudinal provenance.')
    save(fn,p)


def patch_kidney(records):
    fn='nexus_kidney_cancer_v1_2027.json'; p=load(fn)
    # T1a size and cystic phenotype influence active-surveillance option.
    if 'nonsurg_small' in p['nodes']:
        add_option(p,'nonsurg_small','kidney_as_cystic','Active surveillance','Source supports active surveillance for small renal masses, particularly predominantly cystic masses in appropriate patients.','KID-A',app=atom('predominantly_cystic','eq',True),pref='PREFERRED')
        # size is clinically relevant to local-option choice; encode <=3 cm ablation consideration where source details support small masses without inventing broader stage.
        add_option(p,'nonsurg_small','kidney_ablation_small','Percutaneous thermal ablation','For selected small renal masses; use tumor size and anatomy in source-directed selection.','KID-A',app=atom('tumor_size_cm','lte',3))
    # Papillary subtype enables papillary-specific systemic options in non-clear-cell disease.
    for nid,n in p['nodes'].items():
        if n.get('kind')=='action' and ('papillary' in n.get('label','').lower() or 'non-clear' in n.get('label','').lower()):
            add_option(p,nid,'kidney_papillary_specific','Papillary RCC source-specific systemic option set','Apply only when papillary subtype is confirmed.','KID-D',app=atom('papillary_subtype','eq','PAPILLARY'))
    # Prior VEGF-TKI exposure is a later-line selector; use on later-line clear-cell options.
    for nid,n in p['nodes'].items():
        if n.get('kind')=='action' and 'KID-D' in n.get('source_pathways',[]):
            if 'subsequent' in n.get('label','').lower() or 'later' in n.get('label','').lower():
                add_option(p,nid,'kidney_post_vegf_option','Post-VEGF-TKI subsequent-line option set','Use source-listed subsequent-line options appropriate after VEGF-TKI exposure.','KID-D',app=atom('prior_vegf_tki','eq',True))
    save(fn,p)


def patch_mpn(records):
    fn='nexus_myeloproliferative_neoplasms_v2_2026.json'; p=load(fn)
    add_src(p,'workup','MPN-2A'); add_support(p,'workup','MPN-2A')
    for nid in ['mf_risk','mf_high_hct','mf_high_sym','mf_low_sym','mf_jak']:
        if nid in p['nodes']:add_src(p,nid,'MF-2A')
    if 'mf_jak' in p['nodes']:add_support(p,'mf_jak','MF-2A')
    # Accelerated/blast phase source is blast-percentage driven. Use explicit blast threshold rather than only subtype label.
    if 'apbp' in p['nodes']:
        p['nodes']['apbp']['expression']=any_(p['nodes']['apbp']['expression'],atom('blast_percentage','gte',10))
    # MF symptom facts: source combines symptomatic splenomegaly OR constitutional symptoms.
    sym=any_(atom('symptomatic_splenomegaly','eq',True),atom('constitutional_symptoms','eq',True))
    for nid in ['mf_high_sym','mf_low_sym']:
        if nid in p['nodes']:p['nodes'][nid]['expression']=sym
    # JAK inhibitor selection depends on platelet/anemia context; encode conservative thresholds found in MF treatment tables through option applicability rather than a catalog.
    if 'mf_jak' in p['nodes']:
        opts=p['nodes']['mf_jak']['recommendation']['options']
        # preserve existing options and make raw labs decision-relevant via added source-qualified options.
        add_option(p,'mf_jak','mf_jak_platelets_ge50','JAK-inhibitor option set for platelets >=50 x10^9/L','Use source-listed JAK inhibitors appropriate for the platelet count/anemia context.','MF-2',app=atom('platelet_count','gte',50))
        add_option(p,'mf_jak','mf_jak_low_platelets','Pacritinib-context option for severe thrombocytopenia','Source systemic table includes platelet-count-specific JAK inhibitor selection.','MF-2',app=atom('platelet_count','lt',50))
        add_option(p,'mf_jak','mf_anemia_context','Anemia-conscious JAK/symptom strategy','Hemoglobin level and anemia burden alter source therapy selection/supportive management.','MF-2',app=atom('hemoglobin','lt',10))
        add_option(p,'mf_jak','mf_post_jak','Subsequent symptom-directed strategy after prior JAK inhibitor','For persistent/progressive symptoms after prior JAK inhibitor, use source subsequent options/clinical trial.','MF-3',app=atom('jak_inhibitor_prior','eq',True))
    # PV risk: source high risk is age >=60 and/or thrombosis history. Replace opaque risk-only branch with explicit raw criteria while retaining assigned risk as a consistency cross-check.
    if 'pv_risk' in p['nodes']:
        p['nodes']['pv_risk']['expression']=any_(atom('age_years','gte',60),atom('thrombosis_history','eq',True))
        add_consistency(p,'pv_lowrisk_age_thrombosis_conflict',all_(atom('pv_risk','eq','LOWER'),any_(atom('age_years','gte',60),atom('thrombosis_history','eq',True))),'Assigned low PV risk conflicts with age/thrombosis source criteria.',['PV-1','PV-2'])
    # ET risk: use age/thrombosis/driver mutation to affect options; exact 4-tier classification remains in source-derived et_risk where available.
    if 'et_nonhigh' in p['nodes']:
        add_option(p,'et_nonhigh','et_aspirin_jak2','Low-dose aspirin for JAK2-mutated low/intermediate-risk ET when source-indicated','JAK2 driver status is source-relevant to thrombotic-risk management.','ET-2',app=atom('driver_mutation','eq','JAK2'))
    if 'et_first' in p['nodes']:
        add_option(p,'et_first','et_high_thrombosis','Cytoreduction for prior thrombosis/high thrombotic risk','Prior thrombosis is a direct high-risk feature.','ET-2',app=atom('thrombosis_history','eq',True))
        add_option(p,'et_first','et_high_age','Cytoreduction for age-driven high-risk ET','Age contributes to source risk stratification.','ET-2',app=atom('age_years','gte',60))
    save(fn,p)


def main():
    records=[]
    if AMB.exists():
        try: records=json.loads(AMB.read_text())
        except Exception: records=[]
    for fn in [patch_aml,patch_all,patch_breast,patch_bcell,patch_cervical,patch_gastric,patch_biliary,patch_bladder,patch_kidney,patch_hodgkin,patch_bone,patch_mpn,patch_gist,patch_bcc]:
        fn(records)
        print('patched',fn.__name__)
    # Anal currently has no unused pathway-changing facts in the strict audit; leave graph intact.
    AMB.write_text(json.dumps(records,indent=2))

if __name__=='__main__': main()
