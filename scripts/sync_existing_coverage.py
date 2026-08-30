from pathlib import Path
import json, hashlib
ROOT=Path(__file__).resolve().parents[1]
ENC=ROOT/'backend/nexus/guidelines/encoded'
# Map package title slug to knowledge dir via filename/cancer type.
for p in sorted(ENC.glob('nexus_*.json')):
    pkg=json.loads(p.read_text())
    # skip newly generated packages which are already synced
    found=None
    for m in ROOT.glob('knowledge/*/*/manifest.json'):
        try:d=json.loads(m.read_text())
        except:continue
        if d.get('guideline_id')==pkg.get('guideline_id') and d.get('version')==pkg.get('version'):
            found=m.parent;break
    if not found:continue
    sp=found/'source_sections.json'
    if not sp.exists():continue
    ss=json.loads(sp.read_text())
    oldp=list(pkg.get('coverage',{}).get('primary_sections',{}).keys())
    olds=list(pkg.get('coverage',{}).get('supporting_sections',{}).keys())
    # preserve existing intended categorization, but use corrected footer-owned pages/roles.
    pkg.setdefault('coverage',{})['primary_sections']={c:ss[c] for c in oldp if c in ss}
    pkg['coverage']['supporting_sections']={c:ss[c] for c in olds if c in ss}
    # Update source metadata from page ledger when available.
    slug=found.parents[0].name
    led=ROOT/'source_audit'/f'{slug}_page_ledger.json'
    if led.exists():
        a=json.loads(led.read_text()); pkg['source']={'filename':a['filename'],'sha256':a['sha256'],'pdf_pages':a['pdf_pages']}
        man=found/'manifest.json'
        if man.exists():
            md=json.loads(man.read_text()); md['source']=pkg['source']; man.write_text(json.dumps(md,indent=2))
    p.write_text(json.dumps(pkg,indent=2))
print('SYNC_EXISTING_COVERAGE=PASS')
