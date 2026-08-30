from __future__ import annotations
import json,re,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ENC=ROOT/'backend/nexus/guidelines/encoded'
PATHWAY_ROLES={'ROUTING','OPTION_APPLICABILITY','DERIVED_DETERMINISTIC'}
SHORTCUT_PATTERNS=[re.compile(x,re.I) for x in [r'\bsource[- ]bundle\b',r'\bpathway bundle\b',r'use the complete .*algorithm bundle',r'complete subtype-specific .*bundle',r'\bPLACEHOLDER\b',r'\bSTUB\b']]
DEFER_PATTERNS=[re.compile(x,re.I) for x in [r'\bDEFERRED\b',r'\bSOURCE_BUNDLE\b',r'\bPLACEHOLDER\b',r'\bSTUB\b']]


def atoms(expr):
    if not expr:return []
    if 'fact' in expr:return [expr]
    if 'not' in expr:return atoms(expr['not'])
    out=[]
    for k in ('all','any'):
        for x in expr.get(k,[]):out+=atoms(x)
    return out


def used_facts(pkg):
    used=set()
    for n in pkg.get('nodes',{}).values():
        if n.get('kind')=='decision':used.update(a.get('fact') for a in atoms(n.get('expression',{})))
        for o in n.get('recommendation',{}).get('options',[]):used.update(a.get('fact') for a in atoms(o.get('applicability',{})))
    for r in pkg.get('derived_rules',[]):
        used.update(a.get('fact') for a in atoms(r.get('when',{})));used.add(r.get('target_fact'))
    for r in pkg.get('consistency_rules',[]):used.update(a.get('fact') for a in atoms(r.get('when',{})))
    return {x for x in used if x}


def find_knowledge(pkg):
    for m in ROOT.glob('knowledge/*/*/manifest.json'):
        try:d=json.loads(m.read_text())
        except:continue
        if d.get('guideline_id')==pkg.get('guideline_id') and d.get('version')==pkg.get('version'):
            return m.parent,m
    return None,None


def primary_sections(pkg):
    return {k:v for k,v in pkg.get('coverage',{}).get('primary_sections',{}).items() if v.get('kind')!='REFERENCE'}


def section_decision_refs(pkg):
    out={}
    for nid,n in pkg.get('nodes',{}).items():
        for s in n.get('source_pathways',[]):out.setdefault(s,[]).append(('node',nid,n.get('kind')))
        for o in n.get('recommendation',{}).get('options',[]):
            sp=o.get('source_provenance') or {}
            if sp.get('section'):out.setdefault(sp['section'],[]).append(('option',o.get('option_id'),'option'))
        for s in n.get('recommendation',{}).get('supporting_sections',[]):out.setdefault(s,[]).append(('support',nid,'support'))
    return out


def internal_deferred(pkg):
    bad=[]
    for nid,n in pkg.get('nodes',{}).items():
        text=' '.join(str(n.get(k,'')) for k in ('label','status','pathway_id'))
        if any(p.search(text) for p in DEFER_PATTERNS):bad.append(nid)
    return bad


def shortcuts(pkg):
    bad=[]
    for nid,n in pkg.get('nodes',{}).items():
        text=' '.join(str(n.get(k,'')) for k in ('label','pathway_id'))
        if any(p.search(text) for p in SHORTCUT_PATTERNS):bad.append(nid)
    return bad


def provenance_errors(pkg):
    cov=set(pkg.get('coverage',{}).get('primary_sections',{}))|set(pkg.get('coverage',{}).get('supporting_sections',{}))
    errs=[]
    for nid,n in pkg.get('nodes',{}).items():
        for s in n.get('source_pathways',[]):
            if s not in cov:errs.append(f'NODE_SOURCE_UNKNOWN:{nid}:{s}')
        if n.get('kind')=='action':
            base=(n.get('recommendation',{}).get('supporting_sections') or n.get('source_pathways') or [None])[0]
            for o in n.get('recommendation',{}).get('options',[]):
                sp=o.get('source_provenance')
                if not sp:
                    errs.append(f'OPTION_NO_PROVENANCE:{nid}:{o.get("option_id")}')
                elif sp.get('section') not in cov:
                    errs.append(f'OPTION_SOURCE_UNKNOWN:{nid}:{o.get("option_id")}:{sp.get("section")}')
    return errs



def schema_semantic_errors(pkg):
    errors=[]
    fdefs={fd.get('key'):fd for fd in pkg.get('fact_definitions',[])}
    referenced=set()
    exprs=[]
    for nid,n in pkg.get('nodes',{}).items():
        if n.get('kind')=='decision': exprs.append((f'NODE:{nid}',n.get('expression',{})))
        for o in n.get('recommendation',{}).get('options',[]):
            if o.get('applicability'): exprs.append((f'OPTION:{nid}:{o.get("option_id")}',o['applicability']))
    for r in pkg.get('derived_rules',[]):
        exprs.append((f'DERIVED:{r.get("id")}',r.get('when',{})))
        tgt=r.get('target_fact')
        if tgt and tgt not in fdefs: errors.append(f'DERIVED_TARGET_UNDEFINED:{r.get("id")}:{tgt}')
    for r in pkg.get('consistency_rules',[]): exprs.append((f'CONSISTENCY:{r.get("id")}',r.get('when',{})))
    for loc,expr in exprs:
        for a in atoms(expr):
            fid=a.get('fact'); referenced.add(fid)
            fd=fdefs.get(fid)
            if fd is None:
                errors.append(f'UNDEFINED_FACT_REFERENCE:{loc}:{fid}'); continue
            if fd.get('value_type')=='CODED':
                allowed=set(fd.get('allowed_values',[])); op=a.get('op','eq'); val=a.get('value')
                vals=val if op in {'in','not_in'} and isinstance(val,list) else [val]
                for v in vals:
                    if v not in allowed:
                        errors.append(f'INVALID_CODED_LITERAL:{loc}:{fid}:{v}')
    for fid,fd in fdefs.items():
        if fd.get('value_type')=='CODED':
            allowed=set(fd.get('allowed_values',[]))
            for v in fd.get('semantic_unknown_values',[]):
                if v not in allowed: errors.append(f'SEMANTIC_UNKNOWN_NOT_ALLOWED:{fid}:{v}')
    return errors

def validate_one(path):
    pkg=json.loads(path.read_text()); errors=[];warnings=[]
    errors.extend(schema_semantic_errors(pkg))
    kdir,mpath=find_knowledge(pkg)
    inv_file=kdir/'EXECUTABLE_DECISION_INVENTORY.json' if kdir else None
    inv=pkg.get('executable_decisions',[])
    if not inv_file or not inv_file.exists():errors.append('MISSING_EXECUTABLE_DECISION_INVENTORY')
    else:
        disk=json.loads(inv_file.read_text())
        if len(disk)!=len(inv):errors.append(f'INVENTORY_COUNT_MISMATCH:{len(disk)}!={len(inv)}')
    ids=[x.get('decision_id') for x in inv]
    if len(ids)!=len(set(ids)):errors.append('DUPLICATE_DECISION_ID')
    unimpl=[x.get('decision_id') for x in inv if not x.get('implemented')]
    untested=[x.get('decision_id') for x in inv if not x.get('tested')]
    if unimpl:errors.append(f'UNIMPLEMENTED_SOURCE_DECISIONS:{len(unimpl)}')
    if untested:errors.append(f'UNTESTED_SOURCE_DECISIONS:{len(untested)}')
    inv_by_ref={x.get('implementation_ref') for x in inv}
    for nid,n in pkg.get('nodes',{}).items():
        if n.get('kind')=='decision' and nid not in inv_by_ref:errors.append(f'DECISION_NODE_NOT_IN_INVENTORY:{nid}')
        for o in n.get('recommendation',{}).get('options',[]):
            if o.get('applicability') and f'{nid}:{o.get("option_id")}' not in inv_by_ref:errors.append(f'OPTION_APPLICABILITY_NOT_IN_INVENTORY:{nid}:{o.get("option_id")}')
    used=used_facts(pkg)
    unexpl=[]
    for fd in pkg.get('fact_definitions',[]):
        role=fd.get('fact_role')
        if role in PATHWAY_ROLES and fd.get('key') not in used:unexpl.append(fd.get('key'))
    if unexpl:errors.append('UNUSED_PATHWAY_CHANGING_FACTS:'+','.join(sorted(unexpl)))
    d=internal_deferred(pkg)
    if d:errors.append('INTERNAL_DEFERRED_PATHS:'+','.join(d))
    s=shortcuts(pkg)
    if s:errors.append('SOURCE_BUNDLE_SHORTCUTS:'+','.join(s))
    # Every non-reference primary algorithm section must be attached to at least one node/action/option/supporting reference.
    refs=section_decision_refs(pkg)
    missing=[sec for sec in primary_sections(pkg) if sec not in refs]
    if missing:errors.append('PRIMARY_SECTIONS_WITH_NO_EXECUTABLE_OR_TRANSITION_REF:'+','.join(missing))
    errors.extend(provenance_errors(pkg))
    # Manifest status contract.
    if mpath and mpath.exists():
        man=json.loads(mpath.read_text());pc=man.get('pathway_completeness')
        if not isinstance(pc,dict):errors.append('MANIFEST_PATHWAY_COMPLETENESS_NOT_OBJECT')
        else:
            if pc.get('total_decisions')!=len(inv):errors.append('MANIFEST_TOTAL_DECISIONS_MISMATCH')
            if pc.get('implemented_decisions')!=sum(1 for x in inv if x.get('implemented')):errors.append('MANIFEST_IMPLEMENTED_DECISIONS_MISMATCH')
            if pc.get('tested_decisions')!=sum(1 for x in inv if x.get('tested')):errors.append('MANIFEST_TESTED_DECISIONS_MISMATCH')
    lc=pkg.get('lifecycle',{})
    if lc.get('package_status')!='DRAFT':errors.append('PACKAGE_STATUS_NOT_DRAFT')
    if lc.get('clinical_status')!='REQUIRES_CLINICAL_REVIEW':errors.append('CLINICAL_STATUS_INVALID')
    if lc.get('runtime_eligible') is not False:errors.append('RUNTIME_ELIGIBILITY_MUST_BE_FALSE')
    stats={
        'total_source_decisions':len(inv),
        'implemented_source_decisions':sum(1 for x in inv if x.get('implemented')),
        'tested_source_decisions':sum(1 for x in inv if x.get('tested')),
        'unused_pathway_changing_facts':len(unexpl),
        'internal_deferred_paths':len(d),
        'source_bundle_shortcuts':len(s),
    }
    return errors,warnings,stats


def main():
    total={'packages':0,'failed':0,'decisions':0,'implemented':0,'tested':0,'unused':0,'deferred':0,'shortcuts':0}
    report={}
    for p in sorted(ENC.glob('*.json')):
        e,w,s=validate_one(p);total['packages']+=1;total['failed']+=bool(e);total['decisions']+=s['total_source_decisions'];total['implemented']+=s['implemented_source_decisions'];total['tested']+=s['tested_source_decisions'];total['unused']+=s['unused_pathway_changing_facts'];total['deferred']+=s['internal_deferred_paths'];total['shortcuts']+=s['source_bundle_shortcuts']
        report[p.name]={'errors':e,'warnings':w,**s}
        print(f'{p.name}: {"PASS" if not e else "FAIL"} decisions={s["total_source_decisions"]} implemented={s["implemented_source_decisions"]} tested={s["tested_source_decisions"]} unused={s["unused_pathway_changing_facts"]} deferred={s["internal_deferred_paths"]} shortcuts={s["source_bundle_shortcuts"]}')
        for x in e:print('  ERROR',x)
    (ROOT/'source_audit'/'EXECUTABLE_COMPLETENESS_VALIDATION.json').write_text(json.dumps({'summary':total,'packages':report},indent=2))
    print('SUMMARY',json.dumps(total,sort_keys=True))
    raise SystemExit(1 if total['failed'] else 0)

if __name__=='__main__':main()
