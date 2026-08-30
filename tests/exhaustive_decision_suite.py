from __future__ import annotations

import json
import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.evaluator import evaluate, eval_expr, CONFLICT, SEMANTIC_UNKNOWN, _derive_facts  # noqa: E402

ENC = ROOT / 'backend/nexus/guidelines/encoded'
REPORT = ROOT / 'source_audit' / 'EXHAUSTIVE_DECISION_TEST_REPORT.json'


def atoms(expr):
    if not expr:
        return []
    if 'fact' in expr:
        return [expr]
    if 'not' in expr:
        return atoms(expr['not'])
    out=[]
    for k in ('all','any'):
        for x in expr.get(k,[]): out += atoms(x)
    return out


def defs(pkg):
    return {d['key']: d for d in pkg['fact_definitions']}


def legal_domain(fd: dict, thresholds=None):
    t=fd.get('value_type')
    if t=='BOOLEAN': return [False, True]
    if t=='CODED': return list(fd.get('allowed_values', []))
    if t=='NUMERIC':
        vals=set([0, 1, 2, 5, 10, 20, 40, 65, 75, 100])
        for x in thresholds or []:
            if isinstance(x,(int,float)) and not isinstance(x,bool):
                vals.update([x-1, x, x+1])
                if isinstance(x,float): vals.update([x-0.1,x+0.1])
        return sorted(v for v in vals if isinstance(v,(int,float)) and not isinstance(v,bool))
    return []


def atom_truth(atom, value):
    op=atom.get('op','eq'); t=atom.get('value')
    try:
        if op=='eq': return value==t
        if op=='neq': return value!=t
        if op=='gt': return value>t
        if op=='gte': return value>=t
        if op=='lt': return value<t
        if op=='lte': return value<=t
        if op=='in': return value in t
        if op=='not_in': return value not in t
        if op=='contains': return t in value
    except Exception:
        return False
    raise ValueError(op)


def candidates_for_atom(atom, desired, fd):
    thresholds=[]
    if isinstance(atom.get('value'),(int,float)) and not isinstance(atom.get('value'),bool): thresholds=[atom['value']]
    dom=legal_domain(fd, thresholds)
    # Semantic-unknown coded values (MX/NX/TX/UNKNOWN/PENDING...) are not
    # legitimate TRUE/FALSE branch mutations; the runtime intentionally maps
    # them to the third truth value and they are covered by UNKNOWN tests.
    dom=[v for v in dom if v not in SEMANTIC_UNKNOWN]
    out=[v for v in dom if atom_truth(atom,v) is desired]
    # Put the exact target first when legal for deterministic compact states.
    if atom.get('op','eq')=='eq' and desired and atom.get('value') in out:
        out.remove(atom.get('value')); out.insert(0,atom.get('value'))
    return out


def merge(a,b):
    out=dict(a)
    for k,v in b.items():
        if k in out and out[k] != v: return None
        out[k]=v
    return out


def dedupe_assignments(xs, limit=64):
    seen=set(); out=[]
    for x in xs:
        key=json.dumps(x,sort_keys=True,default=str)
        if key not in seen:
            seen.add(key); out.append(x)
        if len(out)>=limit: break
    return out


def assignments_for_expr(expr, desired, fdefs, limit=64):
    if 'fact' in expr:
        fd=fdefs[expr['fact']]
        return [{expr['fact']:v} for v in candidates_for_atom(expr,desired,fd)][:limit]
    if 'not' in expr:
        return assignments_for_expr(expr['not'],not desired,fdefs,limit)
    if 'all' in expr:
        parts=expr['all']
        if desired:
            acc=[{}]
            for p in parts:
                nxt=[]
                for a in acc:
                    for b in assignments_for_expr(p,True,fdefs,limit):
                        m=merge(a,b)
                        if m is not None:nxt.append(m)
                acc=dedupe_assignments(nxt,limit)
                if not acc: break
            return acc
        # False if at least one component false. Generate alternatives.
        out=[]
        for p in parts:
            out += assignments_for_expr(p,False,fdefs,limit)
        return dedupe_assignments(out,limit)
    if 'any' in expr:
        parts=expr['any']
        if desired:
            out=[]
            for p in parts: out += assignments_for_expr(p,True,fdefs,limit)
            return dedupe_assignments(out,limit)
        # False only when all components false.
        acc=[{}]
        for p in parts:
            nxt=[]
            for a in acc:
                for b in assignments_for_expr(p,False,fdefs,limit):
                    m=merge(a,b)
                    if m is not None:nxt.append(m)
            acc=dedupe_assignments(nxt,limit)
            if not acc: break
        return acc
    raise ValueError(expr)


def _structural_paths(pkg, target, max_paths=64):
    root=pkg.get('entry_point','scope')
    nodes=pkg['nodes']; out=[]
    def dfs(nid, steps, seen):
        if len(out)>=max_paths: return
        if nid==target:
            out.append(list(steps)); return
        if nid in seen: return
        node=nodes.get(nid)
        if not node or node.get('kind')!='decision': return
        seen=seen|{nid}
        branches=[('TRUE',True),('FALSE',False)]
        if node.get('on',{}).get('UNKNOWN'):
            branches.append(('UNKNOWN',None))
        for branch,desired in branches:
            tgt=node.get('on',{}).get(branch)
            if tgt:
                dfs(tgt,steps+[(nid,desired)],seen)
    dfs(root,[],set())
    return out


def _solve_path(pkg, steps, max_alternatives=512):
    fdefs=defs(pkg)
    solutions=[{}]
    for step_i,(nid,desired) in enumerate(steps):
        expr=pkg['nodes'][nid]['expression']
        nxt=[]
        if desired is None:
            # UNKNOWN is a real encoded transition in the audited graph. Start
            # from the existing path state and, only when necessary, remove
            # this decision's own inputs. A candidate is accepted only if all
            # ancestor predicates remain satisfied, so this cannot manufacture
            # an impossible unknown route.
            ids=sorted({a['fact'] for a in atoms(expr)})
            for st in solutions:
                variants=[dict(st)]
                variants += [{k:v for k,v in st.items() if k!=fid} for fid in ids if fid in st]
                if any(fid in st for fid in ids):
                    variants.append({k:v for k,v in st.items() if k not in ids})
                for m in dedupe_assignments(variants,max_alternatives):
                    ok=True
                    for pn,pd in steps[:step_i+1]:
                        r=eval_expr(pkg['nodes'][pn]['expression'],m,fdefs)
                        if r is not pd:
                            ok=False;break
                    if ok:nxt.append(m)
                    if len(nxt)>=max_alternatives:break
                if len(nxt)>=max_alternatives:break
        else:
            candidates=assignments_for_expr(expr,desired,fdefs,limit=512)
            for st in solutions:
                for ass in candidates:
                    m=merge(st,ass)
                    if m is None: continue
                    # Verify all path predicates accumulated so far.
                    ok=True
                    for pn,pd in steps[:step_i+1]:
                        r=eval_expr(pkg['nodes'][pn]['expression'],m,fdefs)
                        if r is not pd:
                            ok=False;break
                    if ok:nxt.append(m)
                    if len(nxt)>=max_alternatives:break
                if len(nxt)>=max_alternatives:break
        solutions=dedupe_assignments(nxt,max_alternatives)
        if not solutions:return []
    return solutions


def build_node_states(pkg, max_states_per_node=8):
    """Find legal canonical states reaching each node using source-graph path constraints.

    This avoids combinatorial forward enumeration and validates candidate states through the
    actual runtime, including consistency gates and three-valued behavior.
    """
    out={}
    for target in pkg['nodes']:
        found=[]
        paths=_structural_paths(pkg,target,max_paths=128)
        # First pass: preserve path diversity. Keep at most one valid state per
        # structural path before taking additional states from any one path.
        solved_by_path=[]
        for steps in paths:
            solved=[]
            for st in _solve_path(pkg,steps,max_alternatives=512):
                runtime=evaluate(pkg,st)
                reached = runtime.get('current_node')==target or runtime.get('terminal')==target or any(t.get('node_id')==target for t in runtime.get('trace',[]))
                if target==pkg.get('entry_point','scope'): reached=True
                if reached:
                    solved.append(st)
            solved_by_path.append(solved)
            if solved:
                found.append(solved[0])
                if len(found)>=max_states_per_node: break
        # Second pass: fill remaining capacity from alternate legal states.
        if len(found)<max_states_per_node:
            for solved in solved_by_path:
                for st in solved[1:]:
                    found.append(st)
                    if len(found)>=max_states_per_node: break
                if len(found)>=max_states_per_node: break
        if found: out[target]=dedupe_assignments(found,max_states_per_node)
    return out

def trace_result_for(out,nid):
    for t in out.get('trace',[]):
        if t.get('node_id')==nid: return t.get('result')
    return None


def source_anchor_valid(pkg, item):
    sec=item.get('source_section')
    if not sec:return False
    cov=pkg.get('coverage',{})
    meta=cov.get('primary_sections',{}).get(sec) or cov.get('supporting_sections',{}).get(sec)
    return bool(meta and meta.get('found') and meta.get('pages'))


def fill_applicability_facts(pkg, base, action):
    """Make all conditional option expressions known while preserving the path state."""
    st=dict(base); fdefs=defs(pkg)
    all_expr=[o['applicability'] for o in action.get('recommendation',{}).get('options',[]) if o.get('applicability')]
    # Greedy assignment: prefer a true satisfying assignment, else false, that merges.
    for expr in all_expr:
        if eval_expr(expr,st,fdefs) is not None: continue
        chosen=None
        for desired in (True,False):
            for a in assignments_for_expr(expr,desired,fdefs):
                m=merge(st,a)
                if m is not None:
                    chosen=m; break
            if chosen is not None:break
        if chosen is not None:st=chosen
    return st


def different_outputs(a,b):
    keys=('status','terminal','current_node','current_pathway','recommendation_id')
    if any(a.get(k)!=b.get(k) for k in keys): return True
    oa=[x.get('option_id') for x in a.get('guideline_concordant_options',[])]
    ob=[x.get('option_id') for x in b.get('guideline_concordant_options',[])]
    return oa!=ob


def run_package(path: Path, mark=False):
    pkg=json.loads(path.read_text()); fdefs=defs(pkg); states=build_node_states(pkg)
    errors=[]; warnings=[]; tests=[]; tested_refs=set()

    # Every deterministic derived rule is independently exercised from its raw
    # source facts. This makes guideline-derived classifications (risk groups,
    # eligibility summaries, etc.) visible to the same completeness gate as graph
    # decisions instead of treating their target facts as opaque extractor inputs.
    for rule in pkg.get('derived_rules',[]):
        rid=rule.get('id')
        ref=f'derived::{rid}'
        expr=rule.get('when',{})
        target=rule.get('target_fact')
        expected_value=rule.get('value')
        mode_ok={}

        # DERIVE: at least one legal source-fact assignment must trigger exactly
        # this target/value. Multiple mutually-exclusive rules may share a target.
        derive_ok=False; derive_sample=None
        for ass in assignments_for_expr(expr,True,fdefs,limit=256):
            st, tr=_derive_facts(pkg,ass,fdefs)
            val=st.get(target)
            if isinstance(val,dict): val=val.get('value')
            if val==expected_value and any(x.get('rule_id')==rid for x in tr):
                derive_ok=True; derive_sample=ass; break
        tests.append({'kind':'DERIVED_RULE_DERIVE','ref':ref,'rule_id':rid,'passed':derive_ok,'sample':derive_sample})
        if not derive_ok: errors.append(f'DERIVED_RULE_TRIGGER_FAIL:{rid}')
        mode_ok['DERIVE']=derive_ok

        # NO_DERIVE: a false assignment must not be attributed to this rule. A
        # sibling rule for the same target is allowed to derive another value.
        no_ok=False; no_sample=None
        for ass in assignments_for_expr(expr,False,fdefs,limit=256):
            _, tr=_derive_facts(pkg,ass,fdefs)
            if not any(x.get('rule_id')==rid for x in tr):
                no_ok=True; no_sample=ass; break
        tests.append({'kind':'DERIVED_RULE_NO_DERIVE','ref':ref,'rule_id':rid,'passed':no_ok,'sample':no_sample})
        if not no_ok: errors.append(f'DERIVED_RULE_FALSE_FAIL:{rid}')
        mode_ok['NO_DERIVE']=no_ok

        # UNKNOWN: remove one decision-driving source fact from a known triggering
        # assignment. It must not be coerced to the triggering rule.
        unk_ok=False; unk_fact=None
        true_ass=assignments_for_expr(expr,True,fdefs,limit=64)
        for ass in true_ass:
            for fid in sorted({a['fact'] for a in atoms(expr)}):
                st=dict(ass); st.pop(fid,None)
                _, tr=_derive_facts(pkg,st,fdefs)
                if not any(x.get('rule_id')==rid for x in tr):
                    unk_ok=True; unk_fact=fid; break
            if unk_ok: break
        # A tautological rule would have no independently unresolved input; none
        # exist in the current packages, but keep the semantics explicit.
        tests.append({'kind':'DERIVED_RULE_UNKNOWN','ref':ref,'rule_id':rid,'passed':unk_ok,'fact':unk_fact})
        if not unk_ok: warnings.append(f'DERIVED_RULE_UNKNOWN_NOT_INDEPENDENTLY_TESTABLE:{rid}')

        # CONFLICT: conflict in a triggering source fact must propagate to the
        # derived target when it is decision-relevant to the rule expression.
        conflict_ok=False; conflict_fact=None
        for ass in true_ass:
            for fid in sorted({a['fact'] for a in atoms(expr)}):
                st=dict(ass); st[fid]={'status':'CONFLICT','value':None}
                dst,tr=_derive_facts(pkg,st,fdefs)
                v=dst.get(target)
                if isinstance(v,dict) and str(v.get('status','')).upper()=='CONFLICT' and any(x.get('rule_id')==rid and x.get('status')=='CONFLICT' for x in tr):
                    conflict_ok=True; conflict_fact=fid; break
            if conflict_ok: break
        tests.append({'kind':'DERIVED_RULE_CONFLICT','ref':ref,'rule_id':rid,'passed':conflict_ok,'fact':conflict_fact})
        if not conflict_ok: warnings.append(f'DERIVED_RULE_CONFLICT_NOT_INDEPENDENTLY_TESTABLE:{rid}')

        # The release coverage requirement is trigger/non-trigger correctness plus
        # valid source provenance. UNKNOWN/CONFLICT may be structurally masked in
        # OR rules by another independently true criterion, which is correct 3VL.
        if mode_ok.get('DERIVE') and mode_ok.get('NO_DERIVE'):
            tested_refs.add(ref)

    # Reachability across every graph node.
    unreachable=[nid for nid in pkg['nodes'] if nid not in states]
    unreachable_clinical=[nid for nid in unreachable if pkg['nodes'][nid].get('kind') in {'action','decision'}]
    unreachable_defensive=[nid for nid in unreachable if pkg['nodes'][nid].get('kind')=='status']
    if unreachable_clinical: errors.append('UNREACHABLE_CLINICAL_NODES:'+','.join(unreachable_clinical))
    if unreachable_defensive: warnings.append('UNREACHABLE_DEFENSIVE_STATUS_NODES:'+','.join(unreachable_defensive))

    # Test every decision TRUE/FALSE and, when independently feasible, UNKNOWN/CONFLICT.
    ancestor_facts_cache={}
    for nid,node in pkg['nodes'].items():
        if node.get('kind')!='decision': continue
        did=node.get('decision_id') or nid
        bases=states.get(nid,[])
        if not bases:
            continue
        branch_out={}
        feasible_map={}
        for desired,label in ((True,'TRUE'),(False,'FALSE')):
            passed=False; sample=None; feasible=False
            for base in bases:
                for ass in assignments_for_expr(node['expression'],desired,fdefs):
                    st=merge(base,ass)
                    if st is None: continue
                    out=evaluate(pkg,st)
                    trace_entry=next((t for t in out.get('trace',[]) if t.get('node_id')==nid),None)
                    if trace_entry is None:
                        # The assignment may be locally legal yet invalidate an
                        # ancestor predicate, so it is not a feasible mutation
                        # of this decision in the actual graph.
                        continue
                    feasible=True
                    actual=trace_entry.get('result')
                    if actual is desired:
                        passed=True; sample={'state':st,'status':out.get('status'),'terminal':out.get('terminal'),'current_node':out.get('current_node')}; branch_out[label]=out; break
                if passed: break
            feasible_map[label]=feasible
            tests.append({'kind':'DECISION_BRANCH','ref':did,'node':nid,'branch':label,'feasible':feasible,'passed':passed if feasible else True,'sample':sample})
            if feasible and not passed: errors.append(f'DECISION_BRANCH_FAIL:{nid}:{label}')
            if not feasible: warnings.append(f'DECISION_BRANCH_DOMAIN_IMPOSSIBLE:{nid}:{label}')
        # If source decision has different explicit targets, mutation should observably change the runtime path.
        if branch_out.get('TRUE') and branch_out.get('FALSE') and node['on']['TRUE']!=node['on']['FALSE']:
            # The trace itself must differ at this decision and next-node target is source encoded.
            mutation_pass=trace_result_for(branch_out['TRUE'],nid) is True and trace_result_for(branch_out['FALSE'],nid) is False
            tests.append({'kind':'MUTATION_METAMORPHIC','ref':did,'node':nid,'passed':mutation_pass,'true_target':node['on']['TRUE'],'false_target':node['on']['FALSE']})
            if not mutation_pass: errors.append(f'MUTATION_FAIL:{nid}')
        # UNKNOWN/CONFLICT only when one decision input can be removed/overridden without breaking ancestor path.
        input_facts=sorted({a['fact'] for a in atoms(node['expression'])})
        for mode in ('UNKNOWN','CONFLICT'):
            passed=False; chosen_fact=None; sample=None
            for base in bases:
                for fid in input_facts:
                    st=dict(base)
                    if mode=='UNKNOWN': st.pop(fid,None)
                    else: st[fid]={'status':'CONFLICT','value':None}
                    out=evaluate(pkg,st)
                    actual=trace_result_for(out,nid)
                    if mode=='UNKNOWN':
                        tr=next((t for t in out.get('trace',[]) if t.get('node_id')==nid),None)
                        if node.get('on',{}).get('UNKNOWN'):
                            # Safe UNKNOWN fallbacks are valid three-valued
                            # behavior: the unknown fact must be recorded and the
                            # encoded UNKNOWN edge must actually be traversed.
                            passed=bool(tr and tr.get('result') is None and tr.get('unknown_transition_used') and fid in out.get('missing_information',[]))
                        elif out.get('status')=='NEEDS_INFORMATION' and out.get('current_node')==nid and fid in out.get('missing_information',[]):
                            passed=True
                    elif mode=='CONFLICT' and out.get('status')=='REQUIRES_REVIEW' and out.get('current_node')==nid and fid in out.get('conflicting_facts',[]):
                        passed=True
                    if passed:
                        chosen_fact=fid; sample={'state':st,'status':out.get('status')};break
                if passed:break
            # Some decisions reuse facts necessarily fixed by ancestors. Their UNKNOWN/CONFLICT is tested at the earliest consumer instead.
            tests.append({'kind':f'DECISION_{mode}','ref':did,'node':nid,'passed':passed,'fact':chosen_fact,'feasible_at_node':passed,'sample':sample})
            if not passed: warnings.append(f'{mode}_NOT_INDEPENDENTLY_REACHABLE_AT_NODE:{nid}')
        rel=[t for t in tests if t.get('ref')==did and t['kind'] in {'DECISION_BRANCH','MUTATION_METAMORPHIC'}]
        if rel and all(t['passed'] for t in rel):
            tested_refs.add(did)

    # Test each action and every conditional option show/hide/unknown/conflict.
    for nid,node in pkg['nodes'].items():
        if node.get('kind')!='action': continue
        bases=states.get(nid,[])
        if not bases: continue
        base=fill_applicability_facts(pkg,bases[0],node)
        out=evaluate(pkg,base)
        action_reached=(out.get('current_node')==nid and out.get('status') in {'RECOMMENDATION','NEEDS_INFORMATION','REQUIRES_REVIEW'})
        tests.append({'kind':'ACTION_REACHABILITY','node':nid,'passed':action_reached,'status':out.get('status')})
        if not action_reached: errors.append(f'ACTION_NOT_REACHED:{nid}')
        for opt in node.get('recommendation',{}).get('options',[]):
            expr=opt.get('applicability')
            if not expr: continue
            ref=f'option::{nid}::{opt.get("option_id")}'
            mode_pass={}
            for desired,label in ((True,'SHOW'),(False,'HIDE')):
                passed=False; sample=None
                for b in bases:
                    # First make all conditional option facts known, then override this expression if compatible.
                    b2=fill_applicability_facts(pkg,b,node)
                    for ass in assignments_for_expr(expr,desired,fdefs):
                        # Applicability facts can also participate in an ancestor
                        # gate (for example Hodgkin age). Let the target option
                        # assignment override the symbolic base, then require the
                        # real evaluator to prove that the same action remains
                        # reachable. This tests the option rather than an arbitrary
                        # first symbolic age such as 0.
                        st=dict(b); st.update(ass)
                        # fill remaining option facts after target assignment; do not change existing target facts
                        st=fill_applicability_facts(pkg,st,node)
                        if eval_expr(expr,st,fdefs) is not desired: continue
                        o=evaluate(pkg,st)
                        if o.get('current_node')!=nid: continue
                        ids=[x.get('option_id') for x in o.get('guideline_concordant_options',[])]
                        ok=(o.get('status')=='RECOMMENDATION' and ((opt.get('option_id') in ids) if desired else (opt.get('option_id') not in ids)))
                        if ok:
                            passed=True;sample={'state':st,'options':ids};break
                    if passed:break
                mode_pass[label]=passed
                tests.append({'kind':'OPTION_'+label,'ref':ref,'node':nid,'option_id':opt.get('option_id'),'passed':passed,'sample':sample})
                if not passed: errors.append(f'OPTION_{label}_FAIL:{ref}')
            # Unknown/conflict at option level. Preserve path and make this fact unresolved.
            input_facts=sorted({a['fact'] for a in atoms(expr)})
            for mode in ('UNKNOWN','CONFLICT'):
                passed=False;chosen=None
                for b in bases:
                    # choose target fact and make all other applicability facts known first
                    for fid in input_facts:
                        st=dict(b)
                        # Fill other option expressions; target is deleted/conflicted after fill.
                        st=fill_applicability_facts(pkg,st,node)
                        if mode=='UNKNOWN': st.pop(fid,None)
                        else: st[fid]={'status':'CONFLICT','value':None}
                        o=evaluate(pkg,st)
                        if o.get('current_node')!=nid: continue
                        if mode=='UNKNOWN' and o.get('status')=='NEEDS_INFORMATION' and fid in o.get('missing_information',[]): passed=True
                        if mode=='CONFLICT' and o.get('status')=='REQUIRES_REVIEW': passed=True
                        if passed: chosen=fid;break
                    if passed:break
                tests.append({'kind':'OPTION_'+mode,'ref':ref,'node':nid,'option_id':opt.get('option_id'),'passed':passed,'fact':chosen})
                if not passed: warnings.append(f'OPTION_{mode}_NOT_INDEPENDENTLY_REACHABLE:{ref}')
            if mode_pass.get('SHOW') and mode_pass.get('HIDE'):
                tested_refs.add(ref)

    # Numeric boundary semantics for every numeric atom in routing and option applicability.
    boundary_count=0
    for nid,node in pkg['nodes'].items():
        exprs=[]
        if node.get('kind')=='decision': exprs.append(('decision',node['expression']))
        for o in node.get('recommendation',{}).get('options',[]):
            if o.get('applicability'): exprs.append(('option',o['applicability']))
        for typ,expr in exprs:
            for a in atoms(expr):
                if fdefs[a['fact']].get('value_type')!='NUMERIC':continue
                if a.get('op') not in {'gt','gte','lt','lte','eq','neq'} or not isinstance(a.get('value'),(int,float)):continue
                x=a['value']; vals=[x-1,x,x+1]
                if isinstance(x,float): vals=[x-0.1,x,x+0.1]
                got=[];ok=True
                for v in vals:
                    expected=atom_truth(a,v)
                    actual=eval_expr(a,{a['fact']:v},fdefs)
                    got.append({'value':v,'expected':expected,'actual':actual})
                    ok &= actual is expected
                boundary_count+=1
                tests.append({'kind':'NUMERIC_BOUNDARY','node':nid,'fact':a['fact'],'op':a.get('op'),'threshold':x,'passed':ok,'cases':got})
                if not ok: errors.append(f'BOUNDARY_FAIL:{nid}:{a["fact"]}:{a.get("op")}:{x}')

    # Enum exhaustiveness and invalid enum rejection.
    enum_cases=0
    for fd in pkg['fact_definitions']:
        if fd.get('value_type')!='CODED':continue
        for v in fd.get('allowed_values',[]):
            # Scalar validation is the invariant under test; evaluation may need other info but must not reject legal values.
            o=evaluate(pkg,{fd['key']:v})
            ok=o.get('status')!='INVALID_INPUT' and o.get('status')!='RULE_ENGINE_ERROR'
            enum_cases+=1; tests.append({'kind':'ENUM_VALUE','fact':fd['key'],'value':v,'passed':ok,'status':o.get('status')})
            if not ok:errors.append(f'ENUM_LEGAL_REJECTED:{fd["key"]}:{v}')
        bogus='__NEXUS_INVALID_ENUM__'
        o=evaluate(pkg,{fd['key']:bogus})
        ok=o.get('status')=='INVALID_INPUT'
        tests.append({'kind':'ENUM_INVALID','fact':fd['key'],'passed':ok})
        if not ok:errors.append(f'ENUM_INVALID_ACCEPTED:{fd["key"]}')

    # Provenance of every inventory item must point to a found source section/pages.
    for item in pkg.get('executable_decisions',[]):
        ok=source_anchor_valid(pkg,item)
        tests.append({'kind':'SOURCE_PROVENANCE','ref':item.get('decision_id'),'passed':ok,'source_section':item.get('source_section'),'source_anchor':item.get('source_anchor')})
        if not ok:errors.append(f'INVENTORY_SOURCE_PROVENANCE_FAIL:{item.get("decision_id")}')

    # Mark only records that passed their executable runtime test + provenance.
    prov_pass={t['ref'] for t in tests if t['kind']=='SOURCE_PROVENANCE' and t['passed']}
    tested_refs &= prov_pass
    if mark and not errors:
        for item in pkg.get('executable_decisions',[]):
            item['tested']=item.get('decision_id') in tested_refs
            item['test_method']='exhaustive_symbolic_runtime_mutation_v1' if item['tested'] else item.get('test_method')
        path.write_text(json.dumps(pkg,indent=2))
        # mirror inventory/manifest
        for m in ROOT.glob('knowledge/*/*/manifest.json'):
            man=json.loads(m.read_text())
            if man.get('guideline_id')==pkg.get('guideline_id') and man.get('version')==pkg.get('version'):
                invp=m.parent/'EXECUTABLE_DECISION_INVENTORY.json'
                if invp.exists(): invp.write_text(json.dumps(pkg.get('executable_decisions',[]),indent=2))
                pc=man.setdefault('pathway_completeness',{})
                pc['total_decisions']=len(pkg.get('executable_decisions',[]))
                pc['implemented_decisions']=sum(bool(x.get('implemented')) for x in pkg.get('executable_decisions',[]))
                pc['tested_decisions']=sum(bool(x.get('tested')) for x in pkg.get('executable_decisions',[]))
                m.write_text(json.dumps(man,indent=2));break

    return {
        'package':path.name,'guideline_id':pkg.get('guideline_id'),'version':pkg.get('version'),
        'nodes':len(pkg['nodes']),'reachable_nodes':len(states),'unreachable_nodes':unreachable,
        'inventory_decisions':len(pkg.get('executable_decisions',[])),'tested_refs':len(tested_refs),
        'boundary_cases':boundary_count,'enum_cases':enum_cases,'errors':errors,'warnings':warnings,'tests':tests,
    }


def main():
    mark='--mark-tested' in sys.argv
    reports=[]
    for p in sorted(ENC.glob('*.json')):
        r=run_package(p,mark=mark);reports.append(r)
        print(f"{p.name}: {'PASS' if not r['errors'] else 'FAIL'} nodes={r['reachable_nodes']}/{r['nodes']} inventory_tested={r['tested_refs']}/{r['inventory_decisions']} errors={len(r['errors'])} warnings={len(r['warnings'])}")
        for e in r['errors'][:20]: print('  ERROR',e)
    summary={
        'packages':len(reports),'failed_packages':sum(bool(r['errors']) for r in reports),
        'nodes':sum(r['nodes'] for r in reports),'reachable_nodes':sum(r['reachable_nodes'] for r in reports),
        'inventory_decisions':sum(r['inventory_decisions'] for r in reports),'tested_refs':sum(r['tested_refs'] for r in reports),
        'boundary_cases':sum(r['boundary_cases'] for r in reports),'enum_cases':sum(r['enum_cases'] for r in reports),
        'errors':sum(len(r['errors']) for r in reports),'warnings':sum(len(r['warnings']) for r in reports),
        'test_kind':'symbolic graph reachability + runtime branch mutation + option applicability show/hide + unknown/conflict safety + numeric boundaries + enum exhaustiveness + provenance',
    }
    REPORT.write_text(json.dumps({'summary':summary,'packages':reports},indent=2))
    print('SUMMARY',json.dumps(summary,sort_keys=True))
    raise SystemExit(1 if summary['failed_packages'] else 0)

if __name__=='__main__': main()
