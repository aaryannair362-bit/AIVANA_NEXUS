from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ENC=ROOT/'backend/nexus/guidelines/encoded'

def load(name):
    p=ENC/name; return p,json.loads(p.read_text())
def save(p,d): p.write_text(json.dumps(d,indent=2))
def fd(d,key): return next(x for x in d['fact_definitions'] if x['key']==key)
def add_fact(d,obj):
    if not any(x['key']==obj['key'] for x in d['fact_definitions']): d['fact_definitions'].append(obj)
def prov(guideline,version,section,pages):
    return {'guideline':guideline,'version':version,'section':section,'page_label':section,'physical_pages':pages,'source_anchor':f"{section}:pages:{','.join(map(str,pages))}"}

# ---------------------------------------------------------------------------
# Biliary: retire legacy normalization aliases from clinical-routing semantics.
# The canonical postoperative facts are postop_nodes_positive and postop_margin.
# ---------------------------------------------------------------------------
p,d=load('nexus_biliary_tract_cancers_v1_2026.json')
for old,new in [('nodes_positive','postop_nodes_positive'),('margin_status','postop_margin')]:
    x=fd(d,old)
    x['fact_role']='NON_ROUTING_CONTEXT'
    x['deprecated_alias_for']=new
    x['extraction_allowed']=False
    x['fact_role_rationale']=f'Legacy normalization alias only. Canonical executable routing uses {new}; do not extract or route on this alias.'
save(p,d)

# Gastric: explicitly mark obsolete summary/unsupported biomarker context so the
# unused-fact audit cannot mistake them for hidden routing authority.
p,d=load('nexus_gastric_cancer_v3_2026.json')
if any(x['key']=='path_stage_risk' for x in d['fact_definitions']):
    x=fd(d,'path_stage_risk'); x['fact_role']='NON_ROUTING_CONTEXT'; x['extraction_allowed']=False
    x['fact_role_rationale']='Legacy summary only; executable postoperative routing uses explicit pathologic T/N/margin and prior-therapy facts.'
if any(x['key']=='fgfr2b_positive' for x in d['fact_definitions']):
    x=fd(d,'fgfr2b_positive'); x['fact_role']='NON_ROUTING_CONTEXT'
    x['fact_role_rationale']='No patient-specific FGFR2b treatment branch identified in the authorized Gastric v3.2026 source package; retained as non-routing context.'
save(p,d)

# ---------------------------------------------------------------------------
# Bone / Chondrosarcoma: CHON-1 explicitly defines atypical cartilaginous tumor
# as low-grade + intracompartmental + appendicular and directs other grade/site/
# compartment presentations to CHON-3. Make those raw facts executable instead
# of preserving them only as provenance.
# ---------------------------------------------------------------------------
p,d=load('nexus_bone_cancer_v1_2027.json')
x=fd(d,'grade_group'); x['fact_role']='ROUTING'; x['allowed_values']=['LOW','HIGH','UNKNOWN']; x['semantic_unknown_values']=['UNKNOWN']; x.pop('fact_role_rationale',None)
x=fd(d,'location'); x['fact_role']='ROUTING'; x.pop('fact_role_rationale',None)
add_fact(d,{'key':'tumor_compartment','value_type':'CODED','allowed_values':['INTRACOMPARTMENTAL','EXTRACOMPARTMENTAL','UNKNOWN'],'semantic_unknown_values':['UNKNOWN'],'fact_role':'ROUTING','description':'Anatomic compartment status used by CHON-1 presentation stratification.'})
# Use raw source variables for conventional chondrosarcoma after special histologies.
d['nodes']['chon_dediff']['on']['FALSE']='chon_clear_cell'
d['nodes']['chon_clear_cell']={
    'kind':'decision','label':'Clear-cell chondrosarcoma?',
    'expression':{'fact':'chondrosarcoma_subtype','op':'eq','value':'CLEAR_CELL'},
    'on':{'TRUE':'chon_conv_resect','FALSE':'chon_conv_high_grade'},
    'source_pathways':['CHON-1','CHON-3'],'decision_id':'chon_clear_cell'
}
d['nodes']['chon_conv_high_grade']={
    'kind':'decision','label':'Conventional chondrosarcoma high grade (grade II/III)?',
    'expression':{'fact':'grade_group','op':'eq','value':'HIGH'},
    'on':{'TRUE':'chon_conv_resect','FALSE':'chon_conv_appendicular'},
    'source_pathways':['CHON-1','CHON-3'],'decision_id':'chon_conventional_grade'
}
d['nodes']['chon_conv_appendicular']={
    'kind':'decision','label':'Low-grade conventional tumor in an appendicular site?',
    'expression':{'all':[{'fact':'grade_group','op':'eq','value':'LOW'},{'fact':'location','op':'eq','value':'APPENDICULAR'}]},
    'on':{'TRUE':'chon_conv_compartment','FALSE':'chon_conv_resect'},
    'source_pathways':['CHON-1','CHON-2','CHON-3'],'decision_id':'chon_conventional_grade_location'
}
d['nodes']['chon_conv_compartment']={
    'kind':'decision','label':'Low-grade appendicular conventional tumor intracompartmental?',
    'expression':{'fact':'tumor_compartment','op':'eq','value':'INTRACOMPARTMENTAL'},
    'on':{'TRUE':'chon_act','FALSE':'chon_conv_resect'},
    'source_pathways':['CHON-1','CHON-2','CHON-3'],'decision_id':'chon_conventional_compartment'
}
# When source already identifies ACT, incompatible raw facts are true conflicts.
cr=d.setdefault('consistency_rules',[])
def add_cr(obj):
    if not any(r.get('id')==obj['id'] for r in cr): cr.append(obj)
add_cr({'id':'chon_act_high_grade_conflict','when':{'all':[{'fact':'chondrosarcoma_subtype','op':'eq','value':'ATYPICAL_CARTILAGINOUS'},{'fact':'grade_group','op':'eq','value':'HIGH'}]},'message':'Atypical cartilaginous tumor classification conflicts with high-grade chondrosarcoma evidence.','source_pathways':['CHON-1']})
add_cr({'id':'chon_act_nonappendicular_conflict','when':{'all':[{'fact':'chondrosarcoma_subtype','op':'eq','value':'ATYPICAL_CARTILAGINOUS'},{'fact':'location','op':'neq','value':'APPENDICULAR'}]},'message':'Atypical cartilaginous tumor classification conflicts with a non-appendicular site.','source_pathways':['CHON-1']})
add_cr({'id':'chon_act_extracompartmental_conflict','when':{'all':[{'fact':'chondrosarcoma_subtype','op':'eq','value':'ATYPICAL_CARTILAGINOUS'},{'fact':'tumor_compartment','op':'eq','value':'EXTRACOMPARTMENTAL'}]},'message':'Atypical cartilaginous tumor classification conflicts with extracompartmental disease.','source_pathways':['CHON-1']})
save(p,d)

# ---------------------------------------------------------------------------
# GIST: GIST-A tables explicitly derive recurrence risk from site x size x
# mitotic rate. Make recurrence_risk DERIVED_ONLY and route tumor rupture/R2 to
# metastatic/residual management as GIST-3 requires.
# ---------------------------------------------------------------------------
p,d=load('nexus_gastrointestinal_stromal_tumors_v1_2026.json')
x=fd(d,'recurrence_risk')
x['allowed_values']=['NONE','VERY_LOW','LOW','MODERATE','HIGH','UNKNOWN']
x['fact_role']='DERIVED_DETERMINISTIC'; x['extraction_allowed']=False; x['input_authority']='DERIVED_ONLY'
x['description']='Deterministically derived from GIST-A site/size/mitotic-rate tables; never selected by the extraction model.'
for key in ['tumor_size_cm','mitotic_rate_per_5mm2']:
    x=fd(d,key); x['fact_role']='ROUTING'
add_fact(d,{'key':'tumor_rupture','value_type':'BOOLEAN','fact_role':'ROUTING','description':'Preoperative/intraoperative tumor rupture; GIST-3 treats this as metastatic-disease pathway.'})
# Expand source-defined actionable first-line genotype groups.
x=fd(d,'genotype')
vals=x['allowed_values']
for v in ['NTRK_FUSION','BRAF_V600E']:
    if v not in vals: vals.insert(-1,v)
# Replace any old recurrence-risk derivations if rerun.
d['derived_rules']=[r for r in d.get('derived_rules',[]) if not str(r.get('id','')).startswith('derive_gist_risk_')]
R=[]
def rr(rid,value,when):
    R.append({'id':rid,'target_fact':'recurrence_risk','value':value,'when':when,'source_pathways':['GIST-A']})
# Gastric table (physical page 12). Mitotic cutoff is <=5 vs >5 per 5 mm2.
rr('derive_gist_risk_gastric_le2_lowmit','NONE',{'all':[{'fact':'primary_site','op':'eq','value':'STOMACH'},{'fact':'tumor_size_cm','op':'lte','value':2},{'fact':'mitotic_rate_per_5mm2','op':'lte','value':5}]})
rr('derive_gist_risk_gastric_le2_highmit','NONE',{'all':[{'fact':'primary_site','op':'eq','value':'STOMACH'},{'fact':'tumor_size_cm','op':'lte','value':2},{'fact':'mitotic_rate_per_5mm2','op':'gt','value':5}]})
rr('derive_gist_risk_gastric_2to5_lowmit','VERY_LOW',{'all':[{'fact':'primary_site','op':'eq','value':'STOMACH'},{'fact':'tumor_size_cm','op':'gt','value':2},{'fact':'tumor_size_cm','op':'lte','value':5},{'fact':'mitotic_rate_per_5mm2','op':'lte','value':5}]})
rr('derive_gist_risk_gastric_2to5_highmit','MODERATE',{'all':[{'fact':'primary_site','op':'eq','value':'STOMACH'},{'fact':'tumor_size_cm','op':'gt','value':2},{'fact':'tumor_size_cm','op':'lte','value':5},{'fact':'mitotic_rate_per_5mm2','op':'gt','value':5}]})
rr('derive_gist_risk_gastric_5to10_lowmit','LOW',{'all':[{'fact':'primary_site','op':'eq','value':'STOMACH'},{'fact':'tumor_size_cm','op':'gt','value':5},{'fact':'tumor_size_cm','op':'lte','value':10},{'fact':'mitotic_rate_per_5mm2','op':'lte','value':5}]})
rr('derive_gist_risk_gastric_5to10_highmit','HIGH',{'all':[{'fact':'primary_site','op':'eq','value':'STOMACH'},{'fact':'tumor_size_cm','op':'gt','value':5},{'fact':'tumor_size_cm','op':'lte','value':10},{'fact':'mitotic_rate_per_5mm2','op':'gt','value':5}]})
rr('derive_gist_risk_gastric_gt10_lowmit','MODERATE',{'all':[{'fact':'primary_site','op':'eq','value':'STOMACH'},{'fact':'tumor_size_cm','op':'gt','value':10},{'fact':'mitotic_rate_per_5mm2','op':'lte','value':5}]})
rr('derive_gist_risk_gastric_gt10_highmit','HIGH',{'all':[{'fact':'primary_site','op':'eq','value':'STOMACH'},{'fact':'tumor_size_cm','op':'gt','value':10},{'fact':'mitotic_rate_per_5mm2','op':'gt','value':5}]})
# Non-gastric table (physical page 13); source instructs unlisted non-gastric
# sites to use jejunum/ileum criteria.
non={'fact':'primary_site','op':'neq','value':'STOMACH'}
rr('derive_gist_risk_nongastric_le2_lowmit','NONE',{'all':[non,{'fact':'tumor_size_cm','op':'lte','value':2},{'fact':'mitotic_rate_per_5mm2','op':'lte','value':5}]})
rr('derive_gist_risk_nongastric_le2_highmit','HIGH',{'all':[non,{'fact':'tumor_size_cm','op':'lte','value':2},{'fact':'mitotic_rate_per_5mm2','op':'gt','value':5}]})
rr('derive_gist_risk_nongastric_2to5_lowmit','LOW',{'all':[non,{'fact':'tumor_size_cm','op':'gt','value':2},{'fact':'tumor_size_cm','op':'lte','value':5},{'fact':'mitotic_rate_per_5mm2','op':'lte','value':5}]})
rr('derive_gist_risk_nongastric_2to5_highmit','HIGH',{'all':[non,{'fact':'tumor_size_cm','op':'gt','value':2},{'fact':'tumor_size_cm','op':'lte','value':5},{'fact':'mitotic_rate_per_5mm2','op':'gt','value':5}]})
rr('derive_gist_risk_nongastric_5to10_lowmit','MODERATE',{'all':[non,{'fact':'tumor_size_cm','op':'gt','value':5},{'fact':'tumor_size_cm','op':'lte','value':10},{'fact':'mitotic_rate_per_5mm2','op':'lte','value':5}]})
rr('derive_gist_risk_nongastric_5to10_highmit','HIGH',{'all':[non,{'fact':'tumor_size_cm','op':'gt','value':5},{'fact':'tumor_size_cm','op':'lte','value':10},{'fact':'mitotic_rate_per_5mm2','op':'gt','value':5}]})
rr('derive_gist_risk_nongastric_gt10_lowmit','HIGH',{'all':[non,{'fact':'tumor_size_cm','op':'gt','value':10},{'fact':'mitotic_rate_per_5mm2','op':'lte','value':5}]})
rr('derive_gist_risk_nongastric_gt10_highmit','HIGH',{'all':[non,{'fact':'tumor_size_cm','op':'gt','value':10},{'fact':'mitotic_rate_per_5mm2','op':'gt','value':5}]})
d['derived_rules'].extend(R)
# Tumor rupture is a separate source-defined postoperative transfer.
d['nodes']['post_complete']['on']['TRUE']='post_rupture'
d['nodes']['post_rupture']={
    'kind':'decision','label':'Preoperative or intraoperative tumor rupture?',
    'expression':{'fact':'tumor_rupture','op':'eq','value':True},
    'on':{'TRUE':'post_incomplete','FALSE':'post_risk'},
    'source_pathways':['GIST-3'],'decision_id':'gist_postop_tumor_rupture'
}
# Exact source language for residual/rupture transfer.
d['nodes']['post_incomplete']['label']='Gross residual disease (R2) or tumor rupture: treat through metastatic/unresectable systemic pathway rather than ordinary adjuvant surveillance.'
d['nodes']['post_incomplete']['source_pathways']=['GIST-3','GIST-4']
# Add NTRK/BRAF source-defined first-line options to the genotype-filtered action.
opts=d['nodes']['adv_first']['recommendation']['options']
def addopt(obj):
    if not any(o.get('option_id')==obj['option_id'] for o in opts): opts.append(obj)
for oid,label in [('gist_adv1_larotrectinib','Larotrectinib'),('gist_adv1_entrectinib','Entrectinib'),('gist_adv1_repotrectinib','Repotrectinib')]:
    addopt({'option_id':oid,'label':label,'text':'Source-defined first-line NTRK fusion-positive GIST option.','decision_relevant':True,'preference_category':'USEFUL_IN_CERTAIN_CIRCUMSTANCES','applicability':{'fact':'genotype','op':'eq','value':'NTRK_FUSION'},'source_provenance':prov('Gastrointestinal Stromal Tumors','1.2026','GIST-E',[19])})
addopt({'option_id':'gist_adv1_braf_dt','label':'Dabrafenib + trametinib','text':'Source-defined BRAF V600E-mutated GIST option.','decision_relevant':True,'preference_category':'USEFUL_IN_CERTAIN_CIRCUMSTANCES','applicability':{'fact':'genotype','op':'eq','value':'BRAF_V600E'},'source_provenance':prov('Gastrointestinal Stromal Tumors','1.2026','GIST-E',[19])})
# D842V is line-sensitive: first line avapritinib, second line dasatinib, later source-listed alternatives.
d['nodes']['unres_line']['on']['TRUE']='d842_line_first'
d['nodes']['d842_line_first']={'kind':'decision','label':'PDGFRA exon 18/D842V disease in first line?','expression':{'fact':'treatment_line','op':'eq','value':'FIRST'},'on':{'TRUE':'adv_d842v','FALSE':'d842_line_second'},'source_pathways':['GIST-E'],'decision_id':'gist_d842v_first_line'}
d['nodes']['d842_line_second']={'kind':'decision','label':'PDGFRA exon 18/D842V disease in second line?','expression':{'fact':'treatment_line','op':'eq','value':'SECOND'},'on':{'TRUE':'d842_second','FALSE':'d842_later'},'source_pathways':['GIST-E'],'decision_id':'gist_d842v_second_line'}
d['nodes']['d842_second']={'kind':'action','label':'PDGFRA exon 18/D842V GIST after first-line therapy: dasatinib is an other-recommended second-line option.','status':'RECOMMENDATION','recommendation_id':'gist_d842v_second','pathway_id':'GIST_D842V_SECOND_LINE','source_pathways':['GIST-E'],'recommendation':{'title':'PDGFRA D842V second-line therapy','options':[{'option_id':'gist_d842v_dasatinib','label':'Dasatinib','text':'Other recommended second-line option.','decision_relevant':True,'preference_category':'OTHER_RECOMMENDED','source_provenance':prov('Gastrointestinal Stromal Tumors','1.2026','GIST-E',[19])}],'supporting_sections':['GIST-E'],'next_steps':[]}}
d['nodes']['d842_later']={'kind':'action','label':'PDGFRA exon 18/D842V GIST after avapritinib/dasatinib: subsequent therapy must use source-listed later-line options according to prior exposure.','status':'RECOMMENDATION','recommendation_id':'gist_d842v_later','pathway_id':'GIST_D842V_SUBSEQUENT','source_pathways':['GIST-E'],'recommendation':{'title':'PDGFRA D842V subsequent therapy','options':[{'option_id':'gist_d842v_ripretinib','label':'Ripretinib','text':'Useful in certain circumstances after progression on avapritinib and dasatinib.','decision_relevant':True,'preference_category':'USEFUL_IN_CERTAIN_CIRCUMSTANCES','source_provenance':prov('Gastrointestinal Stromal Tumors','1.2026','GIST-E',[19])},{'option_id':'gist_d842v_trial','label':'Clinical trial / source-listed later-line therapy','text':'Use prior-exposure-specific source options.','decision_relevant':True,'source_provenance':prov('Gastrointestinal Stromal Tumors','1.2026','GIST-E',[19])}],'supporting_sections':['GIST-E'],'next_steps':[]}}
# Remove accidental duplicate atoms from line options introduced by earlier repair passes.
for nid in ['adv_second','adv_third']:
    for o in d['nodes'][nid].get('recommendation',{}).get('options',[]):
        e=o.get('applicability')
        if isinstance(e,dict) and 'all' in e:
            unique=[]; seen=set()
            for a in e['all']:
                k=json.dumps(a,sort_keys=True)
                if k not in seen: seen.add(k); unique.append(a)
            o['applicability']=unique[0] if len(unique)==1 else {'all':unique}
save(p,d)

print('FINAL_SOURCE_FIDELITY_REPAIRS_APPLIED')
