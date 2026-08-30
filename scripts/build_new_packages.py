from __future__ import annotations
from pathlib import Path
import json, hashlib, re
ROOT=Path(__file__).resolve().parents[1]
FULL=ROOT/'source_audit'/'full_sections'
ENC=ROOT/'backend/nexus/guidelines/encoded'

LIFECYCLE={"package_status":"DRAFT","clinical_status":"REQUIRES_CLINICAL_REVIEW","runtime_eligible":False,"engineering_preview_eligible":True,"review_note":"Full source-page ledger and deterministic major-branch implementation. Clinical validation required before activation."}
SAFETY={"three_valued_logic":True,"semantic_unknown_fail_closed":True,"whole_state_schema_validation_required":True,"cross_state_consistency_gate":True,"pathway_transfer_is_non_treatment":True,"clinical_review_required":True}

def fact(key,typ='CODED',vals=None,unknown=None):
 d={'key':key,'value_type':typ}
 if vals is not None:d['allowed_values']=vals
 if unknown:d['semantic_unknown_values']=unknown
 return d

def dec(label,expr,t,f,src=None):
 d={'kind':'decision','label':label,'expression':expr,'on':{'TRUE':t,'FALSE':f}}
 if src:d['source_pathways']=src
 return d

def atom(k,v,op='eq'):return {'fact':k,'op':op,'value':v}
def allx(*xs):return {'all':list(xs)}
def anyx(*xs):return {'any':list(xs)}

def action(label,rid,src,support=(),options=()):
 return {'kind':'action','label':label,'status':'RECOMMENDATION','recommendation_id':rid,'source_pathways':list(src),'recommendation':{'title':label,'options':[{'label':a,'text':b} for a,b in options],'supporting_sections':list(support),'next_steps':[]}}

def status(label,s):return {'kind':'status','label':label,'status':s}

def section_subset(slug,codes,canonical_min,canonical_max):
 allsec=json.loads((FULL/f'{slug}.json').read_text())
 out={}
 for code in codes:
  s=allsec.get(code)
  if not s:
   out[code]={'code':code,'pages':[],'page_count':0,'source_text':'','source_text_sha256':'','kind':'PRIMARY_ALGORITHM','found':False}; continue
  # Filter false positive references outside the canonical guideline algorithm/principles window.
  pages=[p for p in s['pages'] if canonical_min<=p<=canonical_max]
  if not pages:
   out[code]={**s,'pages':[],'page_count':0,'found':False,'source_text':'','source_text_sha256':''}; continue
  # Re-extract exact page chunks from audit text so source_text and hash correspond to filtered pages.
  audit_txt=next((ROOT/'source_audit').glob(slug.split('_')[0]+'*.txt'),None)
  # use already extracted full source_text only when all pages are canonical; otherwise retain section hash and pages without copying unrelated pages
  out[code]={**s,'pages':pages,'page_count':len(pages),'found':True}
 return out

def write_pkg(slug,version,pkg,primary,support,source_filename,source_sha,pdf_pages):
 kdir=ROOT/'knowledge'/slug/version; kdir.mkdir(parents=True,exist_ok=True)
 allsec=json.loads((FULL/f'{slug}.json').read_text())
 # canonical pages are encoded explicitly in supplied section objects from caller
 source_sections={c:pkg['_source_sections'][c] for c in primary+support if c in pkg['_source_sections']}
 pkg.pop('_source_sections')
 pkg['coverage']={'primary_sections':{c:source_sections[c] for c in primary},'supporting_sections':{c:source_sections[c] for c in support},'coverage_semantics':'Every clinically operative primary section in the source algorithm window is source-mapped. Executable major branch routing is separate from clinician validation.'}
 pkg['source']={'filename':source_filename,'sha256':source_sha,'pdf_pages':pdf_pages}
 (ENC/f"nexus_{slug}_v{version.replace('.','_')}.json").write_text(json.dumps(pkg,indent=2))
 (kdir/'source_sections.json').write_text(json.dumps(source_sections,indent=2))
 (kdir/'facts.json').write_text(json.dumps(pkg['fact_definitions'],indent=2))
 manifest={'guideline_id':pkg['guideline_id'],'title':pkg['title'],'version':version,'cancer_type':pkg['cancer_type'],**LIFECYCLE,'pathway_completeness':'FULL_SOURCE_PAGE_MAPPED_MAJOR_BRANCH_EXECUTABLE','source':pkg['source'],'primary_expected':len(primary),'supporting_expected':len(support)}
 (kdir/'manifest.json').write_text(json.dumps(manifest,indent=2))
 represented=set()
 for n in pkg['nodes'].values():
  represented.update(n.get('source_pathways',[])); represented.update(n.get('recommendation',{}).get('supporting_sections',[]))
 lines=[f"# {pkg['title']} {version} - Coverage Map",'',f"- Primary algorithm sections expected: {len(primary)}",f"- Supporting/staging sections expected: {len(support)}",'- Clinical status: REQUIRES_CLINICAL_REVIEW','- Runtime eligible: false (engineering preview only)','', '## Primary algorithms','']
 for c in primary:
  s=source_sections[c]; state='runtime-referenced' if c in represented else 'source-mapped/not-directly-routed'; lines.append(f"- [{'x' if s.get('found') else ' '}] {c} - source page(s) {s.get('pages')} - {state}")
 lines+=['','## Supporting principles / staging','']
 for c in support:
  s=source_sections[c]; state='runtime-referenced' if c in represented else 'source-mapped'; lines.append(f"- [{'x' if s.get('found') else ' '}] {c} - source page(s) {s.get('pages')} - {state}")
 (kdir/'COVERAGE_MAP.md').write_text('\n'.join(lines)+'\n')
 return manifest

def canon_source(slug,codes,minp,maxp):
 d=json.loads((FULL/f'{slug}.json').read_text()); out={}
 for c in codes:
  s=d.get(c)
  if s is None:
   out[c]={'code':c,'pages':[],'page_count':0,'source_text':'','source_text_sha256':'','kind':'PRIMARY_ALGORITHM','found':False}; continue
  ps=[p for p in s['pages'] if minp<=p<=maxp]
  # For our footer-based extraction, canonical page filter removes front matter/discussion cross references.
  # If filtering changed the pages, do not retain text from unrelated pages; preserve section text only if canonical pages equal all pages.
  ns=dict(s); ns['pages']=ps; ns['page_count']=len(ps); ns['found']=bool(ps)
  if set(ps)!=set(s['pages']):
   # reconstruct from pdftotext corpus for exact canonical pages
   # filename maps are known via source audit ledger
   ledger=json.loads((ROOT/'source_audit'/f'{slug}_page_ledger.json').read_text())
   txtfile=ROOT/'source_audit'/Path(ledger['filename']).stem
   txtfile=txtfile.with_suffix('.txt')
   if not txtfile.exists():
    # rebuild script names by actual PDF stem
    alt=ROOT/'source_audit'/f"{Path(ledger['filename']).stem}.txt"; txtfile=alt
   pages_text=txtfile.read_text(errors='ignore').split('\f') if txtfile.exists() else []
   joined='\n\n--- PAGE BREAK ---\n\n'.join(pages_text[p-1].strip() for p in ps if p-1<len(pages_text))
   ns['source_text']=joined; ns['source_text_sha256']=hashlib.sha256(joined.encode()).hexdigest() if joined else ''
  out[c]=ns
 return out

def build_all():
 primary=['ALL-1','ALL-1A','ALL-2','ALL-2A','ALL-3','ALL-4','ALL-4A','ALL-5','ALL-6','ALL-7','ALL-8']
 support=['ALL-A','ALL-B','ALL-C','ALL-D','ALL-E','ALL-F','ALL-G']
 src=canon_source('acute_lymphoblastic_leukemia',primary+support,10,70)
 facts=[fact('cancer_type',vals=['ACUTE_LYMPHOBLASTIC_LEUKEMIA','OTHER']),fact('diagnosis_confirmed','BOOLEAN'),fact('lineage',vals=['B_ALL','T_ALL','OTHER','UNKNOWN'],unknown=['UNKNOWN']),fact('ph_status',vals=['POSITIVE','NEGATIVE','UNKNOWN'],unknown=['UNKNOWN']),fact('treatment_phase',vals=['WORKUP','NEW_DIAGNOSIS','POST_INDUCTION','POST_CONSOLIDATION','SURVEILLANCE','RELAPSED_REFRACTORY','UNKNOWN'],unknown=['UNKNOWN']),fact('response_status',vals=['CR','CR_WITH_MRD','REFRACTORY','RELAPSED','UNKNOWN'],unknown=['UNKNOWN']),fact('mrd_status',vals=['NEGATIVE','POSITIVE','UNKNOWN'],unknown=['UNKNOWN']),fact('transplant_candidate','BOOLEAN'),fact('cns_involvement','BOOLEAN')]
 n={}
 n['scope']=dec('Acute lymphoblastic leukemia?',allx(atom('cancer_type','ACUTE_LYMPHOBLASTIC_LEUKEMIA')),'diag','outside',['ALL-1'])
 n['diag']=dec('Diagnosis confirmed?',allx(atom('diagnosis_confirmed',True)),'phase_rr','workup',['ALL-1','ALL-1A','ALL-2','ALL-2A','ALL-3'])
 n['workup']=action('Complete ALL diagnosis, lineage/genomic risk characterization, workup, baseline CNS/MRD assessment, and transplant planning inputs before treatment routing.','all_workup',primary[:5],support,[('Diagnostic workup','Complete the source-defined ALL diagnostic/workup pathway.')])
 n['phase_rr']=dec('Relapsed/refractory episode?',allx(atom('treatment_phase','RELAPSED_REFRACTORY')),'rr','phase_surv',['ALL-8'])
 n['rr']=action('Relapsed/refractory ALL: lineage, prior therapy, target expression/genomics, CNS status, response and transplant candidacy determine salvage and cellular/transplant pathways.','all_relapsed_refractory',['ALL-8'],support,[('Relapsed/refractory pathway','Use ALL-8 with systemic therapy, MRD and HCT principles.')])
 n['phase_surv']=dec('Surveillance episode?',allx(atom('treatment_phase','SURVEILLANCE')),'surv','phase_post',['ALL-7'])
 n['surv']=action('ALL surveillance after therapy: follow the source surveillance pathway and investigate suspected relapse promptly.','all_surveillance',['ALL-7'],['ALL-E','ALL-F','ALL-G'],[('Surveillance','Use ALL-7 and response/MRD/HCT principles as indicated.')])
 n['phase_post']=dec('Post-induction or post-consolidation assessment?',anyx(atom('treatment_phase','POST_INDUCTION'),atom('treatment_phase','POST_CONSOLIDATION')),'post_response','lineage_b',['ALL-4','ALL-5','ALL-6'])
 n['post_response']=dec('Refractory or relapsed response state?',anyx(atom('response_status','REFRACTORY'),atom('response_status','RELAPSED')),'rr','lineage_b',['ALL-E','ALL-F'])
 n['lineage_b']=dec('B-ALL lineage?',allx(atom('lineage','B_ALL')),'b_ph','lineage_t',['ALL-1'])
 n['b_ph']=dec('Philadelphia chromosome/BCR::ABL1 positive?',allx(atom('ph_status','POSITIVE')),'bph','bphneg',['ALL-2','ALL-4','ALL-4A'])
 n['bph']=action('Ph-positive B-ALL: use the current TKI-containing induction/consolidation pathway with MRD-directed escalation and HCT consideration where appropriate.','all_b_ph_positive',['ALL-4','ALL-4A'],['ALL-D','ALL-E','ALL-F','ALL-G'],[('Ph+ B-ALL','Route therapy and subsequent assessment by ALL-4/4A and MRD response.')])
 n['bphneg']=dec('Philadelphia status confirmed negative?',allx(atom('ph_status','NEGATIVE')),'bneg','need_ph',['ALL-2','ALL-5'])
 n['bneg']=action('Ph-negative B-ALL: use the current age/fitness-appropriate induction/consolidation pathway with MRD-directed blinatumomab/HCT decisions.','all_b_ph_negative',['ALL-5'],['ALL-D','ALL-E','ALL-F','ALL-G'],[('Ph- B-ALL','Route by ALL-5 with MRD and HCT principles.')])
 n['need_ph']=status('B-ALL Philadelphia/BCR::ABL1 status is required before a treatment branch can be released.','NEEDS_INFORMATION')
 n['lineage_t']=dec('T-ALL lineage?',allx(atom('lineage','T_ALL')),'tall','lineage_missing',['ALL-1','ALL-6'])
 n['tall']=action('T-ALL: use the source T-ALL induction/consolidation pathway, with MRD/high-risk features and HCT principles determining subsequent management.','all_t_all',['ALL-6'],['ALL-D','ALL-E','ALL-F','ALL-G'],[('T-ALL','Route by ALL-6 with MRD and HCT principles.')])
 n['lineage_missing']=status('ALL lineage is not established or is outside the encoded B-ALL/T-ALL scope.','NEEDS_INFORMATION')
 n['outside']=status('Case is outside the acute lymphoblastic leukemia ruleset.','OUTSIDE_ENCODED_SCOPE')
 pkg={'schema_version':'nexus-full-pathway/2.1','guideline_id':'NCCN_ALL','title':'Acute Lymphoblastic Leukemia','version':'2.2026','cancer_type':'ACUTE_LYMPHOBLASTIC_LEUKEMIA','entry_point':'scope','lifecycle':LIFECYCLE,'fact_definitions':facts,'nodes':n,'consistency_rules':[{'id':'all_surveillance_active_relapse','when':{'all':[atom('treatment_phase','SURVEILLANCE'),{'any':[atom('response_status','RELAPSED'),atom('response_status','REFRACTORY')]}]},'status':'REQUIRES_REVIEW','message':'Surveillance phase conflicts with active relapsed/refractory response status; reconcile current care phase before releasing a pathway.'}], 'safety':SAFETY,'_source_sections':src}
 return write_pkg('acute_lymphoblastic_leukemia','2.2026',pkg,primary,support,'all(6).pdf','e2113144f4c51c4e6600cdef05561d31c94df50e2b84a3a81fa73f8447ad3bb9',170)

def build_bcell():
 primary=['DIAG-1']+[f'FOLL-{i}' for i in range(1,7)]+['MZL-1']+[f'EMZLG-{i}' for i in range(1,7)]+[f'EMZLNG-{i}' for i in range(1,4)]+[f'NMZL-{i}' for i in range(1,5)]+[f'SMZL-{i}' for i in range(1,4)]+['MANT-1','MANT-2','MANT-3','MANT-4','MANT-5','MANT-6A','MANT-6B']+[f'BCEL-{i}' for i in range(1,11)]+['PMBL-1']+[f'HTBCEL-{i}' for i in range(1,4)]+['HGBL-1']+[f'BURK-{i}' for i in range(1,4)]+[f'HIVLYM-{i}' for i in range(1,5)]+['BLAST-1']+[f'PTLD-{i}' for i in range(1,4)]
 support=['FOLL-A','FOLL-B','EMZLG-A','MZL-A','MANT-A','BCEL-A','BCEL-B','BCEL-C','PMBL-A','HTBCEL-A','HGBL-A','BURK-A','HIVLYM-A','HIVLYM-B','PTLD-A','NHODG-A','NHODG-B','NHODG-C','NHODG-D']+[f'ST-{i}' for i in range(1,6)]
 src=canon_source('b_cell_lymphomas',primary+support,14,136)
 subtypes=['FOLLICULAR','MZL_GASTRIC','MZL_NONGASTRIC','MZL_NODAL','MZL_SPLENIC','MANTLE_CELL','DLBCL','PMBL','TRANSFORMED_DLBCL','HIGH_GRADE_B_CELL','BURKITT','HIV_RELATED_B_CELL','LYMPHOBLASTIC_LYMPHOMA','PTLD','UNKNOWN']
 facts=[fact('cancer_type',vals=['B_CELL_LYMPHOMA','OTHER']),fact('diagnosis_confirmed','BOOLEAN'),fact('lymphoma_subtype',vals=subtypes,unknown=['UNKNOWN']),fact('treatment_phase',vals=['WORKUP','INITIAL_TREATMENT','RESPONSE_ASSESSMENT','SURVEILLANCE','RELAPSED_REFRACTORY','UNKNOWN'],unknown=['UNKNOWN']),fact('stage_group',vals=['LIMITED','ADVANCED','UNKNOWN'],unknown=['UNKNOWN']),fact('response_status',vals=['CR','PR','SD','PROGRESSIVE','RELAPSED','UNKNOWN'],unknown=['UNKNOWN']),fact('indications_for_treatment','BOOLEAN'),fact('transplant_candidate','BOOLEAN'),fact('car_t_candidate','BOOLEAN')]
 n={'scope':dec('B-cell lymphoma?',allx(atom('cancer_type','B_CELL_LYMPHOMA')),'diag','outside',['DIAG-1']),'diag':dec('Diagnosis and subtype confirmed?',allx(atom('diagnosis_confirmed',True)),'subtype_foll','workup',['DIAG-1']),'workup':action('Complete B-cell lymphoma diagnostic classification, immunophenotyping/molecular differential diagnosis, staging and subtype assignment before treatment routing.','bcell_workup',['DIAG-1'],['NHODG-A','NHODG-B','NHODG-C']+[f'ST-{i}' for i in range(1,6)],[('Diagnostic classification','Establish exact lymphoma entity and stage.')])}
 mapping=[
 ('FOLLICULAR','foll',[f'FOLL-{i}' for i in range(1,7)],['FOLL-A','FOLL-B']),
 ('MZL_GASTRIC','mzlg',[f'EMZLG-{i}' for i in range(1,7)],['MZL-1','EMZLG-A','MZL-A']),
 ('MZL_NONGASTRIC','mzl_ng',[f'EMZLNG-{i}' for i in range(1,4)],['MZL-1','MZL-A']),
 ('MZL_NODAL','nmzl',[f'NMZL-{i}' for i in range(1,5)],['MZL-1','MZL-A']),
 ('MZL_SPLENIC','smzl',[f'SMZL-{i}' for i in range(1,4)],['MZL-1','MZL-A']),
 ('MANTLE_CELL','mant',['MANT-1','MANT-2','MANT-3','MANT-4','MANT-5','MANT-6A','MANT-6B'],['MANT-A']),
 ('DLBCL','dlbcl',[f'BCEL-{i}' for i in range(1,11)],['BCEL-A','BCEL-B','BCEL-C']),
 ('PMBL','pmbl',['PMBL-1'],['PMBL-A','BCEL-C']),
 ('TRANSFORMED_DLBCL','transform',[f'HTBCEL-{i}' for i in range(1,4)],['HTBCEL-A','BCEL-C']),
 ('HIGH_GRADE_B_CELL','hgbl',['HGBL-1'],['HGBL-A','BCEL-C']),
 ('BURKITT','burk',[f'BURK-{i}' for i in range(1,4)],['BURK-A']),
 ('HIV_RELATED_B_CELL','hiv',[f'HIVLYM-{i}' for i in range(1,5)],['HIVLYM-A','HIVLYM-B']),
 ('LYMPHOBLASTIC_LYMPHOMA','blast',['BLAST-1'],['NHODG-B']),
 ('PTLD','ptld',[f'PTLD-{i}' for i in range(1,4)],['PTLD-A']),]
 # subtype chain
 prev='subtype_foll'
 for idx,(value,key,srcs,sups) in enumerate(mapping):
  nodeid='subtype_'+key
  nextid='subtype_'+mapping[idx+1][1] if idx+1<len(mapping) else 'subtype_missing'
  n[nodeid]=dec(f'{value} subtype?',allx(atom('lymphoma_subtype',value)),key+'_phase',nextid,['DIAG-1']+srcs[:1])
  n[key+'_phase']=dec('Relapsed/refractory or progressive disease?',anyx(atom('treatment_phase','RELAPSED_REFRACTORY'),atom('response_status','RELAPSED'),atom('response_status','PROGRESSIVE')),key+'_rr',key+'_main',srcs)
  n[key+'_main']=action(f'{value.replace("_"," ").title()}: use the complete subtype-specific initial/response/surveillance algorithm bundle, with stage and treatment-indication decisions applied from the linked source pages.','bcell_'+key+'_main',srcs,sups+['NHODG-B','NHODG-C','NHODG-D'],[("Subtype pathway","Use all linked primary pages for this lymphoma entity; do not substitute another lymphoma pathway.")])
  n[key+'_rr']=action(f'{value.replace("_"," ").title()} relapsed/refractory/progressive disease: use the subtype-specific later-line pathway bundle with response, cellular therapy/transplant and supportive-care principles as applicable.','bcell_'+key+'_rr',srcs,sups+['NHODG-B','NHODG-C','NHODG-D'],[("Relapsed/refractory pathway","Apply the later-line portions of the linked subtype algorithm and regimen tables.")])
 n['subtype_missing']=status('Exact B-cell lymphoma subtype is required; these entities have different pathways and must not be collapsed.','NEEDS_INFORMATION')
 n['outside']=status('Case is outside the B-cell lymphoma ruleset.','OUTSIDE_ENCODED_SCOPE')
 pkg={'schema_version':'nexus-full-pathway/2.1','guideline_id':'NCCN_B_CELL_LYMPHOMAS','title':'B-Cell Lymphomas','version':'4.2026','cancer_type':'B_CELL_LYMPHOMA','entry_point':'scope','lifecycle':LIFECYCLE,'fact_definitions':facts,'nodes':n,'consistency_rules':[{'id':'bcell_surveillance_progressive','when':{'all':[atom('treatment_phase','SURVEILLANCE'),{'any':[atom('response_status','PROGRESSIVE'),atom('response_status','RELAPSED')]}]},'status':'REQUIRES_REVIEW','message':'Surveillance phase conflicts with progressive/relapsed lymphoma status; current episode must be reconciled before recommendation.'}], 'safety':SAFETY,'_source_sections':src}
 return write_pkg('b_cell_lymphomas','4.2026',pkg,primary,support,'b-cell(6).pdf','3f60b89fe36bfb1fc212a43cff8a25d6d2792a9285df6377c5166a3659bd8003',369)

def build_breast():
 primary=['DCIS-1','DCIS-2']+[f'BINV-{i}' for i in range(1,29)]+['PHYLL-1','PAGET-1','PAGET-2','PREG-1','PREG-2','IBC-1','IBC-2']
 support=[f'BINV-{c}' for c in list('ABCDEFGHIJKLMNOPQR')]+[f'ST-{i}' for i in range(1,12)]
 src=canon_source('breast_cancer',primary+support,12,125)
 facts=[fact('cancer_type',vals=['BREAST_CANCER','OTHER']),fact('diagnosis_class',vals=['DCIS','INVASIVE','PHYLLODES','PAGET','UNKNOWN'],unknown=['UNKNOWN']),fact('treatment_phase',vals=['WORKUP','NEW_DIAGNOSIS','PREOPERATIVE_SYSTEMIC','POST_PREOPERATIVE','POST_SURGERY','SURVEILLANCE','LOCOREGIONAL_RECURRENCE','METASTATIC','PREGNANCY','UNKNOWN'],unknown=['UNKNOWN']),fact('clinical_m',vals=['M0','M1','MX'],unknown=['MX']),fact('inflammatory','BOOLEAN'),fact('hr_status',vals=['POSITIVE','NEGATIVE','UNKNOWN'],unknown=['UNKNOWN']),fact('her2_status',vals=['POSITIVE','NEGATIVE','EQUIVOCAL','UNKNOWN'],unknown=['EQUIVOCAL','UNKNOWN']),fact('menopause',vals=['PREMENOPAUSAL','POSTMENOPAUSAL','UNKNOWN'],unknown=['UNKNOWN']),fact('pathologic_node_status',vals=['N0','N_POSITIVE','UNKNOWN'],unknown=['UNKNOWN']),fact('residual_invasive_disease','BOOLEAN'),fact('germline_brca_pathogenic','BOOLEAN')]
 n={}
 n['scope']=dec('Breast cancer?',allx(atom('cancer_type','BREAST_CANCER')),'special_phyll','outside',['BINV-1','DCIS-1'])
 n['special_phyll']=dec('Phyllodes tumor?',allx(atom('diagnosis_class','PHYLLODES')),'phyll','special_paget',['PHYLL-1'])
 n['phyll']=action('Phyllodes tumor: use the dedicated phyllodes workup, surgery, margin, recurrence and metastatic pathway rather than invasive breast carcinoma systemic algorithms.','breast_phyllodes',['PHYLL-1'],[],[('Phyllodes pathway','Use PHYLL-1.')])
 n['special_paget']=dec('Paget disease?',allx(atom('diagnosis_class','PAGET')),'paget','phase_preg',['PAGET-1','PAGET-2'])
 n['paget']=action('Paget disease of the breast: use the dedicated imaging/surgery/nodal/radiation pathway and associated underlying-carcinoma management.','breast_paget',['PAGET-1','PAGET-2'],['BINV-D','BINV-I'],[('Paget pathway','Use PAGET-1/2 and underlying carcinoma pathway as applicable.')])
 n['phase_preg']=dec('Breast cancer during pregnancy?',allx(atom('treatment_phase','PREGNANCY')),'preg','class_dcis',['PREG-1','PREG-2'])
 n['preg']=action('Breast cancer during pregnancy: use the dedicated pregnancy-specific diagnostic, surgery, systemic-therapy timing and radiation constraints pathway.','breast_pregnancy',['PREG-1','PREG-2'],['BINV-C','BINV-M'],[('Pregnancy pathway','Use PREG-1/2; treatment timing differs by gestational context.')])
 n['class_dcis']=dec('Ductal carcinoma in situ?',allx(atom('diagnosis_class','DCIS')),'dcis_phase','class_inv',['DCIS-1','DCIS-2'])
 n['dcis_phase']=dec('Postsurgical/surveillance DCIS episode?',anyx(atom('treatment_phase','POST_SURGERY'),atom('treatment_phase','SURVEILLANCE')),'dcis_post','dcis_primary',['DCIS-1','DCIS-2'])
 n['dcis_primary']=action('DCIS: complete the source workup and primary local-treatment pathway, including breast-conserving/mastectomy options and indicated nodal-staging considerations.','breast_dcis_primary',['DCIS-1'],['BINV-D','BINV-F','BINV-I'],[('DCIS primary treatment','Use DCIS-1.')])
 n['dcis_post']=action('DCIS after surgery: apply postsurgical radiation/endocrine risk-reduction decisions and surveillance/follow-up from the dedicated DCIS pathway.','breast_dcis_post',['DCIS-2'],['BINV-I','BINV-K'],[('DCIS postsurgical','Use DCIS-2.')])
 n['class_inv']=dec('Invasive breast cancer?',allx(atom('diagnosis_class','INVASIVE')),'inv_m1','class_missing',['BINV-1'])
 n['inv_m1']=dec('Metastatic or metastatic episode?',anyx(atom('clinical_m','M1'),atom('treatment_phase','METASTATIC')),'met_hr','inv_recur',['BINV-18','BINV-21'])
 n['inv_recur']=dec('Locoregional recurrence episode?',allx(atom('treatment_phase','LOCOREGIONAL_RECURRENCE')),'recur','inv_ibc',['BINV-19','BINV-20'])
 n['recur']=action('Biopsy-proven local/regional breast cancer recurrence without distant disease: use resectability/prior-RT-directed local therapy and receptor-directed systemic treatment pathways.','breast_locoregional_recurrence',['BINV-19','BINV-20'],['BINV-I','BINV-P','BINV-Q'],[('Local/regional recurrence','Use BINV-19/20 and current biomarkers.')])
 n['inv_ibc']=dec('Inflammatory breast cancer?',allx(atom('inflammatory',True)),'ibc','inv_postpre',['IBC-1','IBC-2'])
 n['ibc']=action('Inflammatory breast cancer: use the dedicated multimodality workup and preoperative systemic-therapy -> surgery -> radiation/adjuvant pathway.','breast_ibc',['IBC-1','IBC-2'],['BINV-L','BINV-M','BINV-I'],[('Inflammatory breast cancer','Use IBC-1/2; do not route as routine operable localized disease.')])
 n['inv_postpre']=dec('After preoperative systemic therapy?',allx(atom('treatment_phase','POST_PREOPERATIVE')),'postpre','inv_postop',['BINV-16'])
 n['postpre']=action('After preoperative systemic therapy: use residual-disease/pathologic-response, HR/HER2 and nodal-status-directed adjuvant therapy plus locoregional treatment pathway.','breast_post_preop',['BINV-13','BINV-14','BINV-15','BINV-16'],['BINV-E','BINV-I','BINV-M'],[('Post-neoadjuvant','Use BINV-13 through BINV-16 and receptor-specific regimen principles.')])
 n['inv_postop']=dec('After upfront surgery/adjuvant planning?',allx(atom('treatment_phase','POST_SURGERY')),'postop_her2pos','inv_surv',['BINV-5','BINV-6','BINV-7','BINV-8','BINV-9','BINV-10','BINV-11'])
 n['postop_her2pos']=dec('HER2-positive?',allx(atom('her2_status','POSITIVE')),'postop_hr_her2pos','postop_her2neg',['BINV-5','BINV-9'])
 n['postop_hr_her2pos']=dec('HR-positive?',allx(atom('hr_status','POSITIVE')),'postop_hrpos_her2pos','postop_hrneg_her2pos',['BINV-5','BINV-9'])
 n['postop_hrpos_her2pos']=action('Postoperative HR-positive/HER2-positive invasive breast cancer: use stage/pathology-directed HER2-directed chemotherapy and endocrine therapy pathway.','breast_postop_hrpos_her2pos',['BINV-5'],['BINV-K','BINV-M'],[('Adjuvant systemic therapy','Use BINV-5 with regimen principles.')])
 n['postop_hrneg_her2pos']=action('Postoperative HR-negative/HER2-positive invasive breast cancer: use stage/pathology-directed HER2-directed adjuvant systemic therapy pathway.','breast_postop_hrneg_her2pos',['BINV-9'],['BINV-M'],[('Adjuvant systemic therapy','Use BINV-9 with regimen principles.')])
 n['postop_her2neg']=dec('HER2-negative?',allx(atom('her2_status','NEGATIVE')),'postop_hrpos','need_her2',['BINV-6','BINV-7','BINV-8','BINV-10'])
 n['postop_hrpos']=dec('HR-positive?',allx(atom('hr_status','POSITIVE')),'postop_meno','postop_tnbc',['BINV-6','BINV-7','BINV-8','BINV-10'])
 n['postop_meno']=dec('Postmenopausal?',allx(atom('menopause','POSTMENOPAUSAL')),'postop_hrpos_post','postop_hrpos_pre',['BINV-6','BINV-7','BINV-8'])
 n['postop_hrpos_post']=action('Postmenopausal HR-positive/HER2-negative invasive breast cancer: use pathologic stage/nodal/genomic-risk-directed endocrine +/- chemotherapy pathway.','breast_postop_hrpos_her2neg_postmeno',['BINV-6'],['BINV-K','BINV-N'],[('Adjuvant HR+/HER2-','Use BINV-6 and gene-expression/endocrine principles.')])
 n['postop_hrpos_pre']=dec('Premenopausal status confirmed?',allx(atom('menopause','PREMENOPAUSAL')),'postop_pre_node','need_meno',['BINV-7','BINV-8'])
 n['postop_pre_node']=dec('Pathologic node positive?',allx(atom('pathologic_node_status','N_POSITIVE')),'postop_pre_npos','postop_pre_n0',['BINV-7','BINV-8'])
 n['postop_pre_npos']=action('Premenopausal HR-positive/HER2-negative node-positive invasive breast cancer: use BINV-8 systemic adjuvant pathway.','breast_postop_hrpos_her2neg_premenopausal_npos',['BINV-8'],['BINV-K','BINV-N'],[('Node-positive premenopausal','Use BINV-8.')])
 n['postop_pre_n0']=action('Premenopausal HR-positive/HER2-negative node-negative invasive breast cancer: use BINV-7 genomic-risk/endocrine +/- chemotherapy pathway.','breast_postop_hrpos_her2neg_premenopausal_n0',['BINV-7'],['BINV-K','BINV-N'],[('Node-negative premenopausal','Use BINV-7.')])
 n['postop_tnbc']=action('Postoperative HR-negative/HER2-negative invasive breast cancer: use the pathologic-stage-directed triple-negative adjuvant systemic therapy pathway.','breast_postop_tnbc',['BINV-10'],['BINV-M'],[('Triple-negative adjuvant','Use BINV-10.')])
 n['need_her2']=status('HER2 status must be resolved before receptor-directed postoperative systemic treatment can be released.','NEEDS_INFORMATION')
 n['need_meno']=status('Menopausal status is required for the HR-positive/HER2-negative postoperative branch.','NEEDS_INFORMATION')
 n['inv_surv']=dec('Surveillance/follow-up episode?',allx(atom('treatment_phase','SURVEILLANCE')),'surv','inv_preop',['BINV-17'])
 n['surv']=action('Breast cancer surveillance/follow-up after curative-intent treatment.','breast_surveillance',['BINV-17'],['BINV-R'],[('Surveillance','Use BINV-17; evaluate symptoms/findings for recurrence rather than routine metastatic routing.')])
 n['inv_preop']=dec('Preoperative systemic therapy pathway indicated/planned?',anyx(atom('treatment_phase','PREOPERATIVE_SYSTEMIC'),allx(atom('her2_status','POSITIVE'),anyx(atom('clinical_t','T2'),atom('clinical_t','T3'),atom('clinical_t','T4'),atom('clinical_n','N1'),atom('clinical_n','N2'),atom('clinical_n','N3')))),'preop','localized',['BINV-12','BINV-13','BINV-14','BINV-15'])
 n['preop']=action('Localized invasive breast cancer selected for preoperative systemic therapy: complete pretherapy workup, receptor-specific regimen selection, response assessment and surgery/axillary planning.','breast_preoperative_systemic',['BINV-12','BINV-13','BINV-14','BINV-15'],['BINV-L','BINV-M','BINV-D','BINV-E'],[('Preoperative systemic therapy','Use BINV-12 through BINV-15.')])
 n['localized']=action('Localized invasive breast cancer not routed to preoperative systemic therapy: complete workup and locoregional treatment, then receptor/pathology-directed adjuvant therapy.','breast_localized_primary',['BINV-1','BINV-2','BINV-3','BINV-4'],['BINV-D','BINV-E','BINV-F','BINV-G','BINV-H','BINV-I'],[('Localized primary treatment','Use BINV-1 through BINV-4 before postoperative systemic routing.')])
 n['met_hr']=dec('HR-positive metastatic disease?',allx(atom('hr_status','POSITIVE')),'met_hrpos','met_her2',['BINV-18','BINV-21','BINV-22','BINV-23','BINV-24','BINV-25','BINV-26','BINV-27','BINV-28'])
 n['met_hrpos']=action('Recurrent unresectable/stage IV HR-positive breast cancer: use biomarker/prior-exposure-directed endocrine/targeted therapy sequence and metastatic monitoring principles.','breast_metastatic_hrpos',['BINV-18','BINV-21','BINV-22','BINV-23','BINV-24','BINV-25','BINV-26','BINV-27','BINV-28'],['BINV-P','BINV-Q','BINV-R'],[('Metastatic HR+','Use BINV-18 and BINV-21-28 with BINV-P/Q/R.')])
 n['met_her2']=dec('HER2-positive metastatic disease?',allx(atom('her2_status','POSITIVE')),'met_her2pos','met_tnbc',['BINV-18','BINV-21'])
 n['met_her2pos']=action('Recurrent unresectable/stage IV HER2-positive breast cancer: use prior-exposure- and line-directed HER2-targeted systemic therapy and monitoring pathways.','breast_metastatic_her2pos',['BINV-18','BINV-21','BINV-22','BINV-23','BINV-24','BINV-25','BINV-26','BINV-27','BINV-28'],['BINV-Q','BINV-R'],[('Metastatic HER2+','Use metastatic BINV pages and HER2 systemic-therapy table.')])
 n['met_tnbc']=dec('HER2-negative status confirmed?',allx(atom('her2_status','NEGATIVE')),'met_tnbc_action','need_her2',['BINV-21'])
 n['met_tnbc_action']=action('Recurrent unresectable/stage IV HR-negative/HER2-negative breast cancer: use PD-L1/germline BRCA/other biomarker and prior-exposure-directed cytotoxic/targeted systemic therapy pathways.','breast_metastatic_tnbc',['BINV-18','BINV-21','BINV-22','BINV-23','BINV-24','BINV-25','BINV-26','BINV-27','BINV-28'],['BINV-Q','BINV-R'],[('Metastatic TNBC','Use metastatic BINV pages with BINV-Q/R biomarker/prior-exposure tables.')])
 n['class_missing']=status('Breast diagnosis class is not established.','NEEDS_INFORMATION'); n['outside']=status('Case is outside the breast cancer ruleset.','OUTSIDE_ENCODED_SCOPE')
 rules=[
 {'id':'breast_dcis_metastatic_conflict','when':{'all':[atom('diagnosis_class','DCIS'),atom('clinical_m','M1')]},'status':'REQUIRES_REVIEW','message':'Pure DCIS conflicts with M1 metastatic staging; reconcile pathology/staging before pathway release.'},
 {'id':'breast_dcis_inflammatory_conflict','when':{'all':[atom('diagnosis_class','DCIS'),atom('inflammatory',True)]},'status':'REQUIRES_REVIEW','message':'DCIS classification conflicts with inflammatory invasive breast-cancer state.'},
 {'id':'breast_curative_phase_m1_conflict','when':{'all':[{'any':[atom('treatment_phase','POST_SURGERY'),atom('treatment_phase','POST_PREOPERATIVE'),atom('treatment_phase','SURVEILLANCE')]},atom('clinical_m','M1')]},'status':'REQUIRES_REVIEW','message':'Curative/post-treatment phase conflicts with current M1 disease; reconcile episode before treatment recommendation.'}
 ]
 pkg={'schema_version':'nexus-full-pathway/2.1','guideline_id':'NCCN_BREAST','title':'Breast Cancer','version':'6.2026','cancer_type':'BREAST_CANCER','entry_point':'scope','lifecycle':LIFECYCLE,'fact_definitions':facts,'nodes':n,'consistency_rules':rules,'safety':SAFETY,'_source_sections':src}
 return write_pkg('breast_cancer','6.2026',pkg,primary,support,'breast(8).pdf','d0a79f2f0ae0',278)

def main():
 ms=[build_all(),build_bcell(),build_breast()]
 # replace placeholder breast hash with actual page-audit hash
 summary=json.loads((ROOT/'source_audit'/'ALL_PDF_PAGE_AUDIT_SUMMARY.json').read_text())
 for m in ms:
  if m['cancer_type']=='BREAST_CANCER':m['source']['sha256']=summary['breast_cancer']['sha256'];
 # Update breast source hash in encoded/manifest too
 bp=ENC/'nexus_breast_cancer_v6_2026.json'; b=json.loads(bp.read_text()); b['source']['sha256']=summary['breast_cancer']['sha256']; bp.write_text(json.dumps(b,indent=2))
 km=ROOT/'knowledge/breast_cancer/6.2026/manifest.json'; d=json.loads(km.read_text()); d['source']['sha256']=summary['breast_cancer']['sha256']; km.write_text(json.dumps(d,indent=2))
 print('BUILT_NEW_PACKAGES', [x['cancer_type'] for x in ms])
if __name__=='__main__':main()
