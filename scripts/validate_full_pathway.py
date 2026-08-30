from __future__ import annotations
import json,sys
from pathlib import Path

def atoms(expr):
    if not expr:return []
    if "fact" in expr:return [expr]
    if "not" in expr:return atoms(expr["not"])
    out=[]
    for k in ("all","any"):
        for x in expr.get(k,[]):out+=atoms(x)
    return out

def represented_sections(pkg):
    represented=set()
    for n in pkg.get("nodes",{}).values():
        represented.update(n.get("source_pathways",[]))
        represented.update(n.get("recommendation",{}).get("supporting_sections",[]))
    for r in pkg.get("consistency_rules",[]):represented.update(r.get("source_pathways",[]))
    return represented

def validate(pkg):
    errors=[]; warnings=[]
    nodes=pkg.get("nodes",{}); defs={d["key"]:d for d in pkg.get("fact_definitions",[])}
    if pkg.get("entry_point","scope") not in nodes:errors.append("MISSING_ENTRY_POINT")
    for nid,n in nodes.items():
        if n.get("kind")=="decision":
            for a in atoms(n.get("expression",{})):
                if a.get("fact") not in defs:errors.append(f"UNDEFINED_FACT:{nid}:{a.get('fact')}")
            for tgt in n.get("on",{}).values():
                if tgt not in nodes:errors.append(f"MISSING_TARGET:{nid}:{tgt}")
            if "all" in n.get("expression",{}):
                eqs={}
                for a in atoms(n["expression"]):
                    if a.get("op")=="eq":eqs.setdefault(a["fact"],set()).add(json.dumps(a.get("value"),sort_keys=True))
                for f,vs in eqs.items():
                    if len(vs)>1:errors.append(f"MUTUALLY_EXCLUSIVE_ALL:{nid}:{f}")
        elif n.get("kind")=="action":
            if not n.get("source_pathways"):warnings.append(f"ACTION_WITHOUT_SOURCE:{nid}")
        elif n.get("kind")!="status":errors.append(f"UNKNOWN_NODE_KIND:{nid}")
    for r in pkg.get("consistency_rules",[]):
        if not r.get("id") or not r.get("when"):errors.append("BAD_CONSISTENCY_RULE")
        for a in atoms(r.get("when",{})):
            if a.get("fact") not in defs:errors.append(f"CONSISTENCY_UNDEFINED_FACT:{r.get('id')}:{a.get('fact')}")
    # reachability
    seen=set(); stack=[pkg.get("entry_point","scope")]
    while stack:
        x=stack.pop()
        if x in seen or x not in nodes:continue
        seen.add(x); nn=nodes[x]
        if nn.get("kind")=="decision":stack.extend(nn.get("on",{}).values())
    for nid in nodes:
        if nid not in seen:warnings.append(f"UNREACHABLE:{nid}")
    cov=pkg.get("coverage",{}); prim=cov.get("primary_sections",{}); supp=cov.get("supporting_sections",{})
    missing=[c for c,v in prim.items() if not v.get("found")]; missing_s=[c for c,v in supp.items() if not v.get("found")]
    if missing:errors.append("SOURCE_PRIMARY_PAGES_NOT_FOUND:"+','.join(missing))
    if missing_s:warnings.append("SOURCE_SUPPORT_PAGES_NOT_FOUND:"+','.join(missing_s))
    represented=represented_sections(pkg)
    # Reference-only pages do not need executable routing. Algorithm pages do.
    unrepresented=[c for c,v in prim.items() if v.get('kind')!='REFERENCE' and c not in represented]
    if unrepresented:errors.append("PRIMARY_CLINICAL_SECTION_NOT_CONSUMED:"+','.join(unrepresented))
    # Every represented code should exist in coverage (or be explicitly external).
    known=set(prim)|set(supp)
    stale=[c for c in represented if c not in known]
    if stale:warnings.append("REFERENCED_SECTION_NOT_IN_COVERAGE:"+','.join(sorted(stale)))
    return errors,warnings

def validate_page_audit(root):
    p=root/'source_audit'/'ALL_PDF_PAGE_AUDIT_SUMMARY.json'
    if not p.exists():return ["MISSING_ALL_PDF_PAGE_AUDIT_SUMMARY"]
    data=json.loads(p.read_text()); errors=[]
    for slug,x in data.items():
        if x.get('pdf_pages',0)<=0:errors.append(f'BAD_PAGE_COUNT:{slug}')
        # rebuild_source_ledgers classifies every physical page, not only clinical pages.
        led=root/'source_audit'/f'{slug}_page_ledger.json'
        if not led.exists():errors.append(f'MISSING_PAGE_LEDGER:{slug}');continue
        d=json.loads(led.read_text())
        if d.get('classified_pages')!=d.get('pdf_pages'):errors.append(f'PAGE_LEDGER_INCOMPLETE:{slug}:{d.get("classified_pages")}/{d.get("pdf_pages")}')
    return errors

def main(root):
    root=Path(root); total=0; bad=0
    page_errors=validate_page_audit(root)
    if page_errors:
        print('PAGE_AUDIT=FAIL',page_errors);bad+=1
    else:print('PAGE_AUDIT=PASS')
    for p in sorted((root/'backend/nexus/guidelines/encoded').glob('nexus_*.json')):
        pkg=json.loads(p.read_text()); e,w=validate(pkg); total+=1
        print(f"{p.name}: {'PASS' if not e else 'FAIL'} errors={len(e)} warnings={len(w)}")
        for x in e:print('  ERROR',x)
        for x in w[:12]:print('  WARN ',x)
        bad+=bool(e)
    print(f"PACKAGES={total} FAILING={bad}")
    raise SystemExit(1 if bad else 0)

if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else '.')
