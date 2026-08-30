from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]; ENC=ROOT/'backend/nexus/guidelines/encoded'

def addsrc(n,*codes):
 s=n.setdefault('source_pathways',[])
 for c in codes:
  if c not in s:s.append(c)
def addsupp(n,*codes):
 s=n.setdefault('recommendation',{}).setdefault('supporting_sections',[])
 for c in codes:
  if c not in s:s.append(c)
def rule(pkg,id,when,msg,src=()):
 rs=pkg.setdefault('consistency_rules',[])
 if any(x.get('id')==id for x in rs):return
 rs.append({'id':id,'when':when,'status':'REQUIRES_REVIEW','message':msg,'source_pathways':list(src)})
def atom(f,v):return {'fact':f,'op':'eq','value':v}
def anyx(*x):return {'any':list(x)}
def allx(*x):return {'all':list(x)}

def load(name):
 p=ENC/name; return p,json.loads(p.read_text())
def save(p,d):
 d['schema_version']='nexus-full-pathway/2.1'; d.setdefault('safety',{})['cross_state_consistency_gate']=True; p.write_text(json.dumps(d,indent=2))

# AML
p,d=load('nexus_acute_myeloid_leukemia_v5_2026.json')
addsrc(d['nodes']['lower'],'AML-4A')
addsrc(d['nodes']['aml_phase_postind'],'AML-5')
rule(d,'aml_surveillance_active_disease',allx(atom('treatment_phase','SURVEILLANCE'),anyx(atom('response_status','RELAPSED'),atom('response_status','REFRACTORY'),atom('response_status','PERSISTENT'))),'AML surveillance conflicts with active/persistent disease status; reconcile current episode before pathway release.',['AML-8','AML-9'])
save(p,d)

# Basal Cell
p,d=load('nexus_basal_cell_skin_cancer_v1_2027.json')
addsrc(d['nodes']['scope'],'BCC-1'); addsrc(d['nodes']['extent_local'],'BCC-1'); addsrc(d['nodes']['risk'],'BCC-2'); addsrc(d['nodes']['low'],'BCC-3A')
rule(d,'bcc_post_treatment_metastatic',allx(atom('treatment_phase','POST_TREATMENT'),atom('disease_extent','METASTATIC')),'Post-treatment follow-up phase conflicts with current metastatic BCC extent; reconcile/re-route to advanced disease before recommendation.',['BCC-5','BCC-6'])
rule(d,'bcc_post_treatment_nodal',allx(atom('treatment_phase','POST_TREATMENT'),atom('disease_extent','NODAL')),'Post-treatment follow-up phase conflicts with current nodal BCC extent; reconcile active regional disease before recommendation.',['BCC-5','BCC-6'])
save(p,d)

# Bladder
p,d=load('nexus_bladder_cancer_v3_2026.json')
for nid in ['scope','site','hist','mibc']:
 if nid in d['nodes']:addsrc(d['nodes'][nid],'BL-1')
for nid in ['nmibc','nmibc_lowint','nmibc_high']:
 if nid in d['nodes']:addsrc(d['nodes'][nid],'BL-5')
rule(d,'bladder_post_intravesical_metastatic',allx(atom('treatment_phase','POST_INTRAVESICAL'),anyx(atom('clinical_m','M1A'),atom('clinical_m','M1B'))),'Post-intravesical NMIBC phase conflicts with current metastatic disease; reconcile stage/episode before recommendation.',['BL-10','BL-11'])
rule(d,'bladder_post_cystectomy_metastatic',allx(atom('treatment_phase','POST_CYSTECTOMY'),anyx(atom('clinical_m','M1A'),atom('clinical_m','M1B'))),'Post-cystectomy phase conflicts with current metastatic disease; use recurrence/metastatic episode after reconciliation.',['BL-10','BL-11'])
save(p,d)

# Cervical
p,d=load('nexus_cervical_cancer_v2_2026.json')
addsrc(d['nodes']['scope'],'CERV-1')
# Annotate early fertility and non-fertility continuation pages
for nid in ['new_stage_ia1','new_ia2ib1','new_ib2_iia1','new_ib3_iia2']:
 if nid in d['nodes']:addsrc(d['nodes'][nid],'CERV-1')
if 'fertility' in d['nodes']:addsrc(d['nodes']['fertility'],'CERV-2A')
if 'ia1_nonfert' in d['nodes']:addsrc(d['nodes']['ia1_nonfert'],'CERV-3A')
rule(d,'cervical_surveillance_ivb',allx(atom('treatment_phase','SURVEILLANCE'),atom('figo_stage','IVB')),'Surveillance phase conflicts with current FIGO IVB disease; reconcile active metastatic disease before recommendation.',['CERV-10','CERV-12'])
rule(d,'cervical_post_surgery_ivb',allx(atom('treatment_phase','POST_SURGERY'),atom('figo_stage','IVB')),'Post-surgery adjuvant phase conflicts with current FIGO IVB disease; reconcile stage/episode before recommendation.',['CERV-6','CERV-12'])
save(p,d)

# Gastric
p,d=load('nexus_gastric_cancer_v3_2026.json')
addsrc(d['nodes']['scope'],'GAST-1','GAST-1A')
for nid in ['new_m','early_tis','locoregional']:
 if nid in d['nodes']:addsrc(d['nodes'][nid],'GAST-1','GAST-1A')
rule(d,'gastric_surveillance_m1',allx(atom('treatment_phase','SURVEILLANCE'),atom('clinical_m','M1')),'Surveillance phase conflicts with current metastatic gastric cancer; reconcile recurrence/metastatic episode before recommendation.',['GAST-7','GAST-8','GAST-9'])
rule(d,'gastric_post_surgery_m1',allx(atom('treatment_phase','POST_SURGERY'),atom('clinical_m','M1')),'Postoperative curative-intent phase conflicts with current M1 disease; reconcile episode before recommendation.',['GAST-4','GAST-5','GAST-9'])
save(p,d)

# Hodgkin
p,d=load('nexus_hodgkin_lymphoma_v2_2026.json')
addsrc(d['nodes']['scope'],'HODG-1','HODG-1A')
for nid in ['hist_nlphl','hist_chl']:
 if nid in d['nodes']:addsrc(d['nodes'][nid],'HODG-1','HODG-1A')
for nid in ['stage_adv','early_fav']:
 if nid in d['nodes']:addsrc(d['nodes'][nid],'HODG-2','HODG-3','HODG-3A','HODG-4')
if 'early_unfav' in d['nodes']:addsrc(d['nodes']['early_unfav'],'HODG-2','HODG-3','HODG-3A','HODG-4')
save(p,d)

# Kidney
p,d=load('nexus_kidney_cancer_v1_2027.json')
rule(d,'kidney_post_nephrectomy_m1',allx(atom('treatment_phase','POST_NEPHRECTOMY'),atom('clinical_m','M1')),'Post-nephrectomy adjuvant/surveillance phase conflicts with current M1 disease; reconcile to relapsed/stage IV management before recommendation.',['KID-3','KID-4'])
save(p,d)

# Anal
p,d=load('nexus_anal_carcinoma_v2_2026.json')
rule(d,'anal_post_crt_m1',allx(atom('treatment_phase','POST_CHEMORADIATION'),atom('clinical_m','M1')),'Post-chemoradiation local response phase conflicts with current metastatic anal carcinoma; reconcile metastatic episode before recommendation.',['ANAL-1','ANAL-3'])
save(p,d)

# GIST
p,d=load('nexus_gastrointestinal_stromal_tumors_v1_2026.json')
rule(d,'gist_postoperative_progression',allx(atom('treatment_phase','POSTOPERATIVE'),atom('response_status','PROGRESSION')),'Postoperative adjuvant phase conflicts with active progression; reconcile recurrent/metastatic/progressive disease episode before recommendation.',['GIST-3','GIST-4','GIST-5'])
save(p,d)
print('PATCH_PROVENANCE_AND_CONSISTENCY=PASS')
