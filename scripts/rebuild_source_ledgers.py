from __future__ import annotations
from pathlib import Path
import subprocess, re, json, hashlib, sys

ROOT=Path(__file__).resolve().parents[1]
PDFS={
 'acute_lymphoblastic_leukemia':('/mnt/data/all(6).pdf',['ALL-']),
 'acute_myeloid_leukemia':('/mnt/data/aml(5).pdf',['EVAL-','APL-','AML-','BPDCN-']),
 'anal_carcinoma':('/mnt/data/anal(5).pdf',['ANAL-','ST-']),
 'b_cell_lymphomas':('/mnt/data/b-cell(6).pdf',['DIAG-','FOLL-','MZL-','EMZLG-','EMZLNG-','NMZL-','SMZL-','MANT-','BCEL-','PMBL-','HTBCEL-','HGBL-','BURK-','HIVLYM-','BLAST-','PTLD-','NHODG-','ST-']),
 'basal_cell_skin_cancer':('/mnt/data/basal(6).pdf',['BCC-']),
 'bladder_cancer':('/mnt/data/bladder(6).pdf',['BL-','UTT-','UCP-','PCU-','ST-']),
 'bone_cancer':('/mnt/data/bone(6).pdf',['TEAM-','BONE-','CHON-','CHOR-','EW-','GCTB-','OSTEO-','ST-']),
 'breast_cancer':('/mnt/data/breast(8).pdf',['DCIS-','BINV-','PHYLL-','PAGET-','PREG-','IBC-','ST-']),
 'biliary_tract_cancers':('/mnt/data/btc(5).pdf',['GALL-','INTRA-','EXTRA-','BIL-','ST-']),
 'cervical_cancer':('/mnt/data/cervical(6).pdf',['CERV-','ST-']),
 'gastric_cancer':('/mnt/data/Gastric(5).pdf',['GAST-','ST-']),
 'gastrointestinal_stromal_tumors':('/mnt/data/gist(4).pdf',['GIST-','ST-']),
 'hodgkin_lymphoma':('/mnt/data/hodgkins(5).pdf',['HODG-','ST-']),
 'kidney_cancer':('/mnt/data/kidney(3).pdf',['KID-','HERED-RCC-','GENE-','ST-']),
 'myeloproliferative_neoplasms':('/mnt/data/mpn(1).pdf',['MPN-','MF-','PV-','ET-']),
}

def sha256_file(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def extract_pages(pdf:Path):
 txt=ROOT/'source_audit'/f'{pdf.stem}.txt'
 subprocess.run(['pdftotext','-layout',str(pdf),str(txt)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 pages=txt.read_text(errors='ignore').split('\f')
 if pages and not pages[-1].strip():pages.pop()
 return pages

def candidate_pattern(prefixes):
 # section labels may occur as "Continued ST-3". Capture only configured prefixes.
 alts='|'.join(re.escape(x) for x in sorted(prefixes,key=len,reverse=True))
 return re.compile(r'(?<![A-Z0-9])((?:'+alts+r')[A-Z0-9/]+(?:-[A-Z0-9/]+)*)\b')

def footer_code(text,prefixes):
 lines=[x.strip() for x in text.splitlines() if x.strip()]
 pat=candidate_pattern(prefixes)
 # footer labels reside near page end. Reverse scan prevents cross-reference text higher up from winning.
 for x in reversed(lines[-8:]):
  ms=list(pat.finditer(x))
  if ms:
   # Prefer rightmost match on the footer line.
   return ms[-1].group(1)
 return None

def page_role(text,code):
 # NCCN prints navigation text such as "Table of Contents" and "Discussion"
 # in the header of essentially every page.  Those strings therefore MUST NOT
 # be used to classify page identity.  Page identity is taken from the footer
 # marker / explicit page heading instead.
 lines=[x.strip().upper() for x in text.splitlines() if x.strip()]
 head=' '.join(lines[:36])
 tail=lines[-14:]

 # Footer-owned nonclinical identities win over incidental cross-references.
 if any(re.search(r'\bMS-\d+\s*$',x) for x in tail): return 'DISCUSSION'
 if any(x == 'UPDATES' or x.endswith(' UPDATES') for x in tail): return 'UPDATES'
 if any(re.search(r'\bABBR-\d+\s*$',x) for x in tail): return 'ABBREVIATIONS'
 if any(re.search(r'\bCAT-\d+\s*$',x) for x in tail): return 'CATEGORY_REFERENCE'

 if code:
  # Dedicated reference pages keep their clinical code (eg HODG-8/APL-7),
  # but are not decision terminals.
  if any(x == 'REFERENCES' or re.fullmatch(r'[A-Z][A-Z /-]{0,80}REFERENCES', x) for x in lines[:18]): return 'REFERENCE'
  if code.startswith('ST-'): return 'STAGING'
  # Principle/supporting sections conventionally use an alphabetic suffix
  # immediately after the disease prefix (eg BINV-A, HODG-C, MF-A).
  remainder=code.split('-',1)[1] if '-' in code else ''
  if remainder and remainder[0].isalpha(): return 'PRINCIPLE'
  return 'ALGORITHM'

 return 'OTHER_NONCLINICAL'

def build_one(slug,pdf_s,prefixes):
 pdf=Path(pdf_s); pages=extract_pages(pdf); sections={}; ledger=[]
 for i,text in enumerate(pages,1):
  code=footer_code(text,prefixes)
  # Known PDF text-layer footer omission: HODG-5A is the page between HODG-5 and HODG-5B.
  if slug=='hodgkin_lymphoma' and i==15: code='HODG-5A'
  role=page_role(text,code)
  text_hash=hashlib.sha256(text.encode('utf-8','ignore')).hexdigest()
  ledger.append({'physical_page':i,'section_code':code,'role':role,'text_sha256':text_hash})
  if code and role in {'ALGORITHM','PRINCIPLE','STAGING','REFERENCE'}:
   s=sections.setdefault(code,{'code':code,'pages':[],'roles':set(),'page_texts':[]})
   s['pages'].append(i); s['roles'].add(role); s['page_texts'].append(text.strip())
 out={}
 for code,s in sections.items():
  joined='\n\n--- PAGE BREAK ---\n\n'.join(s['page_texts'])
  roles=sorted(s['roles'])
  kind='REFERENCE' if roles==['REFERENCE'] else ('STAGING' if 'STAGING' in roles else ('SUPPORTING_PRINCIPLE' if 'PRINCIPLE' in roles else 'PRIMARY_ALGORITHM'))
  out[code]={'code':code,'pages':s['pages'],'page_count':len(s['pages']),'source_text':joined,'source_text_sha256':hashlib.sha256(joined.encode()).hexdigest(),'kind':kind,'found':True}
 audit={'slug':slug,'filename':pdf.name,'sha256':sha256_file(pdf),'pdf_pages':len(pages),'classified_pages':len(ledger),'clinical_section_pages':sum(1 for x in ledger if x['section_code']),'page_role_counts':{},'ledger':ledger}
 for x in ledger:audit['page_role_counts'][x['role']]=audit['page_role_counts'].get(x['role'],0)+1
 (ROOT/'source_audit'/f'{slug}_page_ledger.json').write_text(json.dumps(audit,indent=2))
 return out,audit

def main():
 summary={}
 for slug,(pdf,prefixes) in PDFS.items():
  sections,audit=build_one(slug,pdf,prefixes)
  summary[slug]={'filename':audit['filename'],'sha256':audit['sha256'],'pdf_pages':audit['pdf_pages'],'clinical_section_pages':audit['clinical_section_pages'],'section_count':len(sections),'page_role_counts':audit['page_role_counts']}
  # Update existing knowledge source map if package exists; new packages are created by build_new_packages.py.
  candidates=list((ROOT/'knowledge'/slug).glob('*/source_sections.json')) if (ROOT/'knowledge'/slug).exists() else []
  for sp in candidates:
   current=json.loads(sp.read_text())
   # Only preserve sections already intentionally in this package; remap to the correct footer-owned page(s).
   remapped={}
   for code in current:
    if code in sections: remapped[code]=sections[code]
    else:
     old=current[code]; old['found']=False; old['pages']=[]; old['page_count']=0; remapped[code]=old
   sp.write_text(json.dumps(remapped,indent=2))
  # Always write the complete detected clinical-section inventory for audit/use by new packages.
  full_dir=ROOT/'source_audit'/'full_sections'; full_dir.mkdir(parents=True,exist_ok=True)
  (full_dir/f'{slug}.json').write_text(json.dumps(sections,indent=2))
 (ROOT/'source_audit'/'ALL_PDF_PAGE_AUDIT_SUMMARY.json').write_text(json.dumps(summary,indent=2))
 print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
