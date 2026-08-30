from __future__ import annotations
import json,sys,itertools
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine.evaluator import evaluate, eval_expr, CONFLICT
from tests.exhaustive_decision_suite import build_node_states, atoms, defs, legal_domain, trace_result_for, fill_applicability_facts
ENC=ROOT/'backend/nexus/guidelines/encoded'
OUT=ROOT/'source_audit'/'PAIRWISE_COMBINATION_TEST_REPORT.json'

def main():
    total=0;fail=[];by={}
    for p in sorted(ENC.glob('*.json')):
        pkg=json.loads(p.read_text()); fdefs=defs(pkg); states=build_node_states(pkg,max_states_per_node=4); pc=0
        for nid,node in pkg['nodes'].items():
            if node.get('kind')!='decision' or nid not in states:continue
            fids=sorted(set(a['fact'] for a in atoms(node.get('expression',{}))))
            if len(fids)<2:continue
            bases=states[nid]
            for a,b in itertools.combinations(fids,2):
                da=legal_domain(fdefs[a])[:8];db=legal_domain(fdefs[b])[:8]
                for va,vb in itertools.product(da,db):
                    # Find a path-compatible base for this pair. If none exists,
                    # this pair is not a legal state at this decision node.
                    checked=False
                    for base in bases:
                        st=dict(base);st[a]=va;st[b]=vb
                        out=evaluate(pkg,st)
                        tr=trace_result_for(out,nid)
                        if tr is None:continue
                        exp=eval_expr(node['expression'],st,fdefs)
                        if exp in (None,CONFLICT):continue
                        checked=True;total+=1;pc+=1
                        if tr is not exp:
                            fail.append({'package':p.name,'node':nid,'facts':[a,b],'values':[va,vb],'expected':exp,'actual':tr,'status':out.get('status')})
                        break
                    # Invalid/cross-state combinations are intentionally skipped;
                    # consistency rules are separately required to block them.
        # Option-applicability pairwise interactions.
        for nid,node in pkg['nodes'].items():
            if node.get('kind')!='action' or nid not in states:continue
            for opt in node.get('recommendation',{}).get('options',[]):
                expr=opt.get('applicability')
                if not expr:continue
                fids=sorted(set(a['fact'] for a in atoms(expr)))
                if len(fids)<2:continue
                for a,b in itertools.combinations(fids,2):
                    for va,vb in itertools.product(legal_domain(fdefs[a])[:8],legal_domain(fdefs[b])[:8]):
                        for base in states[nid]:
                            st=dict(base);st[a]=va;st[b]=vb
                            st=fill_applicability_facts(pkg,st,node)
                            exp=eval_expr(expr,st,fdefs)
                            if exp in (None,CONFLICT):continue
                            out=evaluate(pkg,st)
                            if out.get('current_node')!=nid:continue
                            ids={x.get('option_id') for x in out.get('guideline_concordant_options',[])}
                            act=opt.get('option_id') in ids
                            total+=1;pc+=1
                            if act is not exp:fail.append({'package':p.name,'node':nid,'option':opt.get('option_id'),'facts':[a,b],'values':[va,vb],'expected':exp,'actual':act})
                            break
        by[p.name]=pc
        print(p.name,'PAIRWISE_CASES',pc)
    report={'status':'PASS' if not fail else 'FAIL','cases':total,'failures':len(fail),'by_package':by,'failure_samples':fail[:100]}
    OUT.write_text(json.dumps(report,indent=2))
    print('PAIRWISE_COMBINATION_CASES',total);print('PAIRWISE_COMBINATION_FAILURES',len(fail));print('PAIRWISE_COMBINATION_STATUS',report['status'])
    raise SystemExit(1 if fail else 0)
if __name__=='__main__':main()
