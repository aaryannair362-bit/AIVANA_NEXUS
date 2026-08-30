from pathlib import Path
import json,re
import fitz

ROOT=Path(__file__).resolve().parents[1]
PDF_MAP={
'acute_lymphoblastic_leukemia':'all_v2_2026.pdf',
'acute_myeloid_leukemia':'aml_v5_2026.pdf',
'anal_carcinoma':'anal_v2_2026.pdf',
'b_cell_lymphomas':'b_cell_v4_2026.pdf',
'basal_cell_skin_cancer':'basal_v1_2027.pdf',
'biliary_tract_cancers':'biliary_v1_2026.pdf',
'bladder_cancer':'bladder_v3_2026.pdf',
'bone_cancer':'bone_v1_2027.pdf',
'breast_cancer':'breast_v6_2026.pdf',
'cervical_cancer':'cervical_v2_2026.pdf',
'gastric_cancer':'gastric_v3_2026.pdf',
'gastrointestinal_stromal_tumors':'gist_v1_2026.pdf',
'hodgkin_lymphoma':'hodgkin_v2_2026.pdf',
'kidney_cancer':'kidney_v1_2027.pdf',
'myeloproliferative_neoplasms':'mpn_v2_2026.pdf',
}

def slug_from_pkg(pkg):
    m={
      "NCCN_ALL":"acute_lymphoblastic_leukemia",
      "NCCN_AML":"acute_myeloid_leukemia",
      "NCCN_ANAL":"anal_carcinoma",
      "NCCN_B_CELL_LYMPHOMAS":"b_cell_lymphomas",
      "NCCN_BASAL_CELL":"basal_cell_skin_cancer",
      "NCCN_BILIARY":"biliary_tract_cancers",
      "NCCN_BLADDER":"bladder_cancer",
      "NCCN_BONE":"bone_cancer",
      "NCCN_BREAST":"breast_cancer",
      "NCCN_CERVICAL":"cervical_cancer",
      "NCCN_GASTRIC":"gastric_cancer",
      "NCCN_GIST":"gastrointestinal_stromal_tumors",
      "NCCN_HODGKIN":"hodgkin_lymphoma",
      "NCCN_KIDNEY":"kidney_cancer",
      "NCCN_MPN":"myeloproliferative_neoplasms",
    }
    return m.get(pkg.get("guideline_id"))

def clean(text):
    lines=[]
    for ln in text.splitlines():
        s=' '.join(ln.split())
        if not s: continue
        if s.startswith('NCCN Guidelines Version'): continue
        if s.startswith('Version ') and 'All rights reserved' in s: continue
        if 'PLEASE NOTE that use of this NCCN Content' in s: continue
        if s.startswith('Printed by '): continue
        if s in {'NCCN Guidelines Index','Table of Contents','Discussion'}: continue
        lines.append(s)
    return '\n'.join(lines)

def main():
    out=ROOT/'source_extracts'; out.mkdir(exist_ok=True)
    enc=ROOT/'backend/nexus/guidelines/encoded'
    for jf in sorted(enc.glob('nexus_*.json')):
        pkg=json.loads(jf.read_text())
        slug=slug_from_pkg(pkg)
        if not slug: raise RuntimeError(jf)
        pdf=ROOT/'resources/guidelines'/PDF_MAP[slug]
        doc=fitz.open(pdf)
        od=out/slug; od.mkdir(exist_ok=True)
        allsecs={}
        allsecs.update(pkg.get('coverage',{}).get('primary_sections',{}))
        allsecs.update(pkg.get('coverage',{}).get('supporting_sections',{}))
        index={}
        for code,meta in allsecs.items():
            pages=meta.get('pages',[])
            txt=[]
            for p in pages:
                if 1<=p<=len(doc): txt.append(f'=== PHYSICAL PAGE {p} ===\n'+clean(doc[p-1].get_text('text')))
            t='\n'.join(txt)
            (od/f'{code.replace("/","_")}.txt').write_text(t)
            index[code]={'pages':pages,'kind':meta.get('kind'),'chars':len(t)}
        (od/'INDEX.json').write_text(json.dumps(index,indent=2))
        print(slug,len(index))
if __name__=='__main__':main()
