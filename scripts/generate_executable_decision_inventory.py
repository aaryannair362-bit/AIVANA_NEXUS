from __future__ import annotations
import json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ENC=ROOT/'backend/nexus/guidelines/encoded'


def atoms(expr):
    if not expr:return []
    if 'fact' in expr:return [expr]
    if 'not' in expr:return atoms(expr['not'])
    out=[]
    for k in ('all','any'):
        for x in expr.get(k,[]):out+=atoms(x)
    return out


def first_source(node):
    xs=node.get('source_pathways') or []
    return xs[0] if xs else None


def source_anchor(pkg, section):
    if not section:return None
    cov=pkg.get('coverage',{})
    meta=cov.get('primary_sections',{}).get(section) or cov.get('supporting_sections',{}).get(section) or {}
    pages=meta.get('pages',[])
    return f'{section}:pages:{",".join(map(str,pages))}'


def option_set_targets(pkg, node):
    out=[]
    for tgt in node.get('on',{}).values():
        n=pkg.get('nodes',{}).get(tgt,{})
        if n.get('kind')=='action':
            out.extend([o.get('option_id') for o in n.get('recommendation',{}).get('options',[]) if o.get('option_id')])
    return sorted(set(out))


def build_inventory(pkg):
    inv=[]
    derived=pkg.get('derived_rules',[])
    by_target={}
    for r in derived:by_target.setdefault(r.get('target_fact'),[]).append(r.get('id'))

    # Derived guideline classifications are first-class executable source decisions.
    # They must never disappear behind a synthetic route fact that is merely supplied
    # by extraction. The inventory therefore records the source inputs and the exact
    # deterministic rule which materializes the derived fact.
    for r in derived:
        rid=r.get('id')
        sec=(r.get('source_pathways') or [None])[0]
        fids=sorted(set(a['fact'] for a in atoms(r.get('when',{}))))
        inv.append({
            'decision_id':f'derived::{rid}',
            'source_section':sec,
            'source_page_label':sec,
            'source_anchor':source_anchor(pkg,sec),
            'clinical_question':r.get('label') or f"Should {r.get('target_fact')} be deterministically derived as {r.get('value')!r}?",
            'input_fact_ids':fids,
            'derived_rule_ids':[rid] if rid else [],
            'possible_branches':['DERIVE','NO_DERIVE','UNKNOWN','CONFLICT'],
            'option_set_ids':[],
            'internal_transfer_targets':[r.get('target_fact')],
            'external_dependencies':[],
            'implementation_kind':'DERIVED_RULE',
            'implementation_ref':rid,
            'implemented':True,
            'tested':False,
        })

    for nid,node in pkg.get('nodes',{}).items():
        if node.get('kind')!='decision':continue
        sec=first_source(node)
        fids=sorted(set(a['fact'] for a in atoms(node.get('expression',{}))))
        rec={
            'decision_id':node.get('decision_id') or nid,
            'source_section':sec,
            'source_page_label':sec,
            'source_anchor':source_anchor(pkg,sec),
            'clinical_question':node.get('label'),
            'input_fact_ids':fids,
            'derived_rule_ids':sorted({rid for f in fids for rid in by_target.get(f,[]) if rid}),
            'possible_branches':['TRUE','FALSE','UNKNOWN','CONFLICT'],
            'option_set_ids':option_set_targets(pkg,node),
            'internal_transfer_targets':[node.get('on',{}).get('TRUE'),node.get('on',{}).get('FALSE')],
            'external_dependencies':[],
            'implementation_kind':'PATHWAY_DECISION',
            'implementation_ref':nid,
            'implemented':True,
            'tested':False,
        }
        inv.append(rec)
    for nid,node in pkg.get('nodes',{}).items():
        if node.get('kind')!='action':continue
        source=(node.get('recommendation',{}).get('supporting_sections') or node.get('source_pathways') or [None])[0]
        for opt in node.get('recommendation',{}).get('options',[]):
            expr=opt.get('applicability')
            if not expr:continue
            fids=sorted(set(a['fact'] for a in atoms(expr)))
            inv.append({
                'decision_id':f'option::{nid}::{opt.get("option_id")}',
                'source_section':(opt.get('source_provenance') or {}).get('section') or source,
                'source_page_label':(opt.get('source_provenance') or {}).get('page_label') or source,
                'source_anchor':(opt.get('source_provenance') or {}).get('source_anchor') or source_anchor(pkg,source),
                'clinical_question':f'Is option {opt.get("label") or opt.get("option_id")} applicable to the current patient state?',
                'input_fact_ids':fids,
                'derived_rule_ids':sorted({rid for f in fids for rid in by_target.get(f,[]) if rid}),
                'possible_branches':['SHOW','HIDE','UNKNOWN','CONFLICT'],
                'option_set_ids':[opt.get('option_id')],
                'internal_transfer_targets':[nid],
                'external_dependencies':[],
                'implementation_kind':'OPTION_APPLICABILITY',
                'implementation_ref':f'{nid}:{opt.get("option_id")}',
                'implemented':True,
                'tested':False,
            })
    return inv


def find_knowledge(pkg):
    for m in ROOT.glob('knowledge/*/*/manifest.json'):
        try:d=json.loads(m.read_text())
        except:continue
        if d.get('guideline_id')==pkg.get('guideline_id') and d.get('version')==pkg.get('version'):
            return m.parent,m
    return None,None


def main():
    totals=0
    for p in sorted(ENC.glob('*.json')):
        pkg=json.loads(p.read_text())
        inv=build_inventory(pkg); totals+=len(inv)
        pkg['executable_decisions']=inv
        kdir,mpath=find_knowledge(pkg)
        if kdir:
            (kdir/'EXECUTABLE_DECISION_INVENTORY.json').write_text(json.dumps(inv,indent=2))
            if mpath:
                man=json.loads(mpath.read_text())
                pc=man.get('pathway_completeness')
                if not isinstance(pc,dict):pc={}
                pc.update({'status':'IN_PROGRESS','total_decisions':len(inv),'implemented_decisions':len(inv),'tested_decisions':0,'unused_pathway_changing_facts':None,'internal_deferred_paths':None})
                man['pathway_completeness']=pc
                mpath.write_text(json.dumps(man,indent=2))
        p.write_text(json.dumps(pkg,indent=2))
        print(f'{p.name}: DECISIONS={len(inv)}')
    print('TOTAL_DECISIONS',totals)

if __name__=='__main__':main()
