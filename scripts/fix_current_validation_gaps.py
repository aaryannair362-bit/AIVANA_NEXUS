from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
ENC=ROOT/'backend/nexus/guidelines/encoded'

def load(name):
    p=ENC/name
    return p,json.loads(p.read_text())
def save(p,d): p.write_text(json.dumps(d,indent=2))
def fd(pkg,key):
    return next(x for x in pkg['fact_definitions'] if x['key']==key)
def atom(f,op,v): return {'fact':f,'op':op,'value':v}
def all_(*xs): return {'all':list(xs)}
def any_(*xs): return {'any':list(xs)}
def not_(x): return {'not':x}
def prov(pkg,sec):
    meta=(pkg.get('coverage',{}).get('primary_sections',{}).get(sec) or pkg.get('coverage',{}).get('supporting_sections',{}).get(sec) or {})
    return {'guideline':pkg['title'],'version':pkg['version'],'section':sec,'page_label':sec,'physical_pages':meta.get('pages',[]),'source_anchor':f"{sec}:pages:{','.join(map(str,meta.get('pages',[])))}"}
def option(pkg,oid,label,sec,app=None,pref=None,ev=None,text=None):
    o={'option_id':oid,'label':label,'text':text or label,'decision_relevant':True,'source_provenance':prov(pkg,sec)}
    if app:o['applicability']=app
    if pref:o['preference_category']=pref
    if ev:o['evidence_category']=ev
    return o

def action(pkg,nid,label,sec,options,pathway=None,support=None):
    pkg['nodes'][nid]={'kind':'action','label':label,'status':'RECOMMENDATION','recommendation_id':nid,'source_pathways':[sec],
       'recommendation':{'title':label,'options':options,'supporting_sections':support or [],'next_steps':[]},'pathway_id':pathway or nid.upper()}

def decision(pkg,nid,label,expr,t,f,sec):
    pkg['nodes'][nid]={'kind':'decision','label':label,'expression':expr,'on':{'TRUE':t,'FALSE':f},'source_pathways':[sec],'decision_id':nid}

def upsert_consistency(pkg,rule):
    arr=pkg.setdefault('consistency_rules',[])
    arr[:]=[r for r in arr if r.get('id')!=rule['id']]
    arr.append(rule)
def upsert_derived(pkg,rule):
    arr=pkg.setdefault('derived_rules',[])
    arr[:]=[r for r in arr if r.get('id')!=rule['id']]
    arr.append(rule)

# Biliary field name repairs.
p,pkg=load('nexus_biliary_tract_cancers_v1_2026.json')
for r in pkg.get('consistency_rules',[]):
    txt=json.dumps(r).replace('post_resection_margin','postop_margin').replace('treatment_line','systemic_line')
    r.clear(); r.update(json.loads(txt))
save(p,pkg)

# GIST derived very-small-gastric state: deterministic only, never LLM authoritative.
p,pkg=load('nexus_gastrointestinal_stromal_tumors_v1_2026.json')
f=fd(pkg,'very_small_gastric_lt2cm'); f['fact_role']='DERIVED_DETERMINISTIC'; f['extraction_allowed']=False; f['input_authority']='DERIVED_ONLY'
upsert_derived(pkg,{'id':'derive_very_small_gastric_true','target_fact':'very_small_gastric_lt2cm','value':True,
    'when':all_(atom('primary_site','eq','STOMACH'),atom('tumor_size_cm','lt',2)),'source_pathways':['GIST-1']})
upsert_derived(pkg,{'id':'derive_very_small_gastric_false','target_fact':'very_small_gastric_lt2cm','value':False,
    'when':any_(atom('primary_site','neq','STOMACH'),atom('tumor_size_cm','gte',2)),'source_pathways':['GIST-1']})
pkg['nodes']['initial_small']['expression']=atom('very_small_gastric_lt2cm','eq',True)
for r in pkg.get('consistency_rules',[]):
    txt=json.dumps(r).replace('small_gastric_gist_lt2cm','very_small_gastric_lt2cm')
    r.clear(); r.update(json.loads(txt))
save(p,pkg)

# MPN PV risk is deterministic from age/thrombosis exactly as MPN-2.
p,pkg=load('nexus_myeloproliferative_neoplasms_v2_2026.json')
f=fd(pkg,'pv_high_risk'); f['fact_role']='DERIVED_DETERMINISTIC'; f['extraction_allowed']=False; f['input_authority']='DERIVED_ONLY'
upsert_derived(pkg,{'id':'derive_pv_high_risk_true','target_fact':'pv_high_risk','value':True,
  'when':any_(atom('age_years','gte',60),atom('thrombosis_history','eq',True)),'source_pathways':['MPN-2']})
upsert_derived(pkg,{'id':'derive_pv_high_risk_false','target_fact':'pv_high_risk','value':False,
  'when':all_(atom('age_years','lt',60),atom('thrombosis_history','eq',False)),'source_pathways':['MPN-2']})
pkg['nodes']['pv_risk']['expression']=atom('pv_high_risk','eq',True)
upsert_consistency(pkg,{'id':'pv_lowrisk_age_thrombosis_conflict','when':all_(atom('pv_high_risk','eq',False),any_(atom('age_years','gte',60),atom('thrombosis_history','eq',True))),
 'message':'Assigned low PV risk conflicts with age/thrombosis source criteria.','source_pathways':['MPN-2','PV-1','PV-2']})
upsert_consistency(pkg,{'id':'pv_highrisk_age_thrombosis_conflict','when':all_(atom('pv_high_risk','eq',True),atom('age_years','lt',60),atom('thrombosis_history','eq',False)),
 'message':'Assigned high PV risk conflicts with age <60 and no thrombosis history.','source_pathways':['MPN-2','PV-1','PV-2']})
save(p,pkg)

# Bladder: make BL-5 reachable; enforce adequate BCG for unresponsive state; decompose T2 urethral anatomy.
p,pkg=load('nexus_bladder_cancer_v3_2026.json')
# Bladder initial branch enters positive-cytology gate before NMIBC risk only when current phase is initial NMIBC.
# Existing site_bl TRUE -> bl_care; locate NEW diagnosis NMIBC branch target and splice cytology safely just before nmibc risk.
# Use nmibc_initial TRUE -> cytology_gate instead of directly risk.
pkg['nodes']['nmibc_initial']['on']['TRUE']='cytology_gate'
# Make cytology gate FALSE preserve previous normal risk path.
pkg['nodes']['cytology_gate']['on']['FALSE']='nmibc_risk_decision'
# Require adequate BCG before classifying source-defined BCG-unresponsive state.
pkg['nodes']['high_bcg_state']['expression']=all_(atom('adequate_bcg_received','eq',True), any_(atom('bcg_unresponsive','eq',True),atom('bcg_exposure_state','eq','UNRESPONSIVE')))
upsert_consistency(pkg,{'id':'bladder_unresponsive_requires_adequate_bcg','when':all_(any_(atom('bcg_unresponsive','eq',True),atom('bcg_exposure_state','eq','UNRESPONSIVE')),atom('adequate_bcg_received','eq',False)),
 'message':'BCG-unresponsive state requires adequate BCG exposure per BL-F definition; reconcile BCG course history.','source_pathways':['BL-F','BL-4']})
# Replace T2 generic action target with anatomy decision chain.
pkg['nodes']['pcu_t2']['on']['TRUE']='pcu_t2_pendulous'
pkg['nodes'].pop('pcu_t2_action',None)  # legacy generic T2 terminal replaced by anatomy-specific PCU-2 branches
decision(pkg,'pcu_t2_pendulous','T2 primary urethral carcinoma in male pendulous urethra?',atom('urethral_location','eq','MALE_PENDULOUS'),'pcu_t2_pendulous_action','pcu_t2_bulbar','PCU-2')
decision(pkg,'pcu_t2_bulbar','T2 primary urethral carcinoma in male bulbar urethra?',atom('urethral_location','eq','MALE_BULBAR'),'pcu_t2_bulbar_action','pcu_t2_female','PCU-2')
decision(pkg,'pcu_t2_female','T2 primary urethral carcinoma in female urethra?',atom('urethral_location','eq','FEMALE'),'pcu_t2_female_action','need_urethral_location','PCU-2')
action(pkg,'pcu_t2_pendulous_action','T2 male pendulous urethral carcinoma: distal urethrectomy or partial penectomy; positive margins require additional local treatment.','PCU-2',[
 option(pkg,'pcu_pend_distal','Distal urethrectomy','PCU-2'),
 option(pkg,'pcu_pend_penectomy','Partial penectomy','PCU-2'),
 option(pkg,'pcu_pend_posmargin','Additional surgery or chemoradiotherapy (preferred) or RT for positive margin','PCU-2',atom('margin_positive','eq',True),pref='PREFERRED')
],pathway='PCU_T2_PENDULOUS',support=['BL-B','BL-G','BL-H'])
action(pkg,'pcu_t2_bulbar_action','T2 male bulbar urethral carcinoma: urethrectomy ± cystoprostatectomy, followed by pathology-directed adjuvant assessment.','PCU-2',[
 option(pkg,'pcu_bulbar_surgery','Urethrectomy ± cystoprostatectomy','PCU-2')
],pathway='PCU_T2_BULBAR',support=['BL-B'])
action(pkg,'pcu_t2_female_action','T2 female urethral carcinoma: chemoradiotherapy or urethrectomy + cystectomy or distal urethrectomy depending on tumor location.','PCU-2',[
 option(pkg,'pcu_female_crt','Chemoradiotherapy','PCU-2'),
 option(pkg,'pcu_female_ureth_cyst','Urethrectomy + cystectomy','PCU-2'),
 option(pkg,'pcu_female_distal','Distal urethrectomy depending on tumor location','PCU-2')
],pathway='PCU_T2_FEMALE',support=['BL-B','BL-G','BL-H'])
pkg['nodes']['need_urethral_location']={'kind':'status','label':'T2 urethral treatment depends on sex-assigned anatomy/tumor location; location is required.','status':'NEEDS_INFORMATION','missing_facts':['urethral_location'],'source_pathways':['PCU-2'],'pathway_id':'PCU_T2_NEEDS_LOCATION'}
save(p,pkg)

# Gastric: cN+ changes staging/laparoscopy workup applicability where source says cT3 and/or cN+.
p,pkg=load('nexus_gastric_cancer_v3_2026.json')
fd(pkg,'clinical_n')['fact_role']='OPTION_APPLICABILITY'
lap_app=any_(atom('clinical_t','in',['T3','T4A','T4B']),atom('clinical_n','eq','N_POS'))
for nid in ('locoreg_standard','locoreg_msi_action'):
    opts=pkg['nodes'][nid]['recommendation']['options']
    if not any(o.get('option_id')=='gastric_staging_laparoscopy_cT3_or_cNpos' for o in opts):
        opts.append(option(pkg,'gastric_staging_laparoscopy_cT3_or_cNpos','Staging laparoscopy with peritoneal washings/cytology for cT3 and/or cN+ potentially resectable disease','GAST-C',lap_app))
save(p,pkg)

# Kidney: belzutifan subsequent-line source footnote requires prior PD-1/PD-L1 inhibitor AND VEGF-TKI.
p,pkg=load('nexus_kidney_cancer_v1_2027.json')
for o in pkg['nodes']['cc_later']['recommendation']['options']:
    if o.get('option_id')=='kid_cc_later_bel':
        o['applicability']=all_(atom('prior_belzutifan','eq',False),atom('prior_io','eq',True),atom('prior_vegf_tki','eq',True))
        o['text']='Belzutifan; source footnote specifies patients previously treated with a PD-1/PD-L1 inhibitor and a VEGF-TKI.'
        o['source_provenance']=prov(pkg,'KID-D')
save(p,pkg)

print('fixed current validation gaps')
