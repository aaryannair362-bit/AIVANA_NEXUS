from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from builder_lib import src_prov
ROOT=Path(__file__).resolve().parents[1]; ENC=ROOT/'backend/nexus/guidelines/encoded'
for fp in sorted(ENC.glob('*.json')):
    p=json.loads(fp.read_text()); changed=0
    cov=set(p.get('coverage',{}).get('primary_sections',{}))|set(p.get('coverage',{}).get('supporting_sections',{}))
    for nid,n in p.get('nodes',{}).items():
        if n.get('kind')!='action': continue
        rec=n.get('recommendation',{})
        # Prefer a treatment/supporting section when present; otherwise exact action primary section.
        candidates=[x for x in rec.get('supporting_sections',[]) if x in cov] + [x for x in n.get('source_pathways',[]) if x in cov]
        sec=candidates[0] if candidates else None
        for o in rec.get('options',[]):
            if not o.get('option_id'):
                # Stable option id is mandatory for option-level applicability/provenance.
                o['option_id']=f'{nid}_option_{rec.get("options",[]).index(o)+1}'
                changed+=1
            if not o.get('source_provenance') and sec:
                o['source_provenance']=src_prov(p,sec); changed+=1
    if changed:
        fp.write_text(json.dumps(p,indent=2))
    print(fp.name,'CHANGED',changed)
