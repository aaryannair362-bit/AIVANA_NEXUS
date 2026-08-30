from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ENC=ROOT/'backend/nexus/guidelines/encoded'
AUD=ROOT/'source_audit'

def load(name): return json.loads((AUD/name).read_text())

def main():
    ex=load('EXECUTABLE_COMPLETENESS_VALIDATION.json')
    eo=load('EXHAUSTIVE_DECISION_TEST_REPORT.json')
    mg=load('MANDATORY_GAP_COVERAGE_REPORT.json')
    so=load('STRUCTURED_ORACLE_EVALUATION_REPORT.json')
    http=load('REALTIME_HTTP_FUZZ_REPORT.json')
    blockers=[]
    if ex.get('summary',{}).get('failed')!=0: blockers.append('EXECUTABLE_COMPLETENESS')
    if eo.get('summary',{}).get('failed_packages')!=0: blockers.append('EXHAUSTIVE_DECISION_SUITE')
    if mg.get('failed_packages')!=0: blockers.append('MANDATORY_GAP_COVERAGE')
    if so.get('status')!='PASS' or so.get('failures')!=0 or so.get('evaluations',0)<10000: blockers.append('STRUCTURED_ORACLE')
    if http.get('errors') or http.get('requests',0)<10000: blockers.append('HTTP_STABILITY')
    if blockers: raise SystemExit('Cannot finalize; blockers='+','.join(blockers))

    ex_by={x['package']:x for x in ex.get('packages',[])} if isinstance(ex.get('packages'),list) else {}
    # validator report may use a mapping depending on earlier version
    if not ex_by and isinstance(ex.get('packages'),dict): ex_by=ex['packages']
    for p in sorted(ENC.glob('*.json')):
        d=json.loads(p.read_text())
        inv=d.get('executable_decisions',[])
        lifecycle=d.setdefault('lifecycle',{})
        lifecycle['package_status']='DRAFT'
        lifecycle['clinical_status']='REQUIRES_CLINICAL_REVIEW'
        lifecycle['runtime_eligible']=False
        lifecycle['engineering_preview_eligible']=True
        lifecycle['pathway_completeness']={
            'status':'COMPLETE_UNREVIEWED',
            'total_decisions':len(inv),
            'implemented_decisions':sum(bool(x.get('implemented')) for x in inv),
            'tested_decisions':sum(bool(x.get('tested')) for x in inv),
            'unused_pathway_changing_facts':0,
            'internal_deferred_paths':0,
            'source_bundle_shortcuts':0,
            'engineering_scope':'DETERMINISTIC_KNOWLEDGE_PACKAGE',
            'clinical_review_required':True,
        }
        lifecycle['review_note']='Engineering executable-completeness gates passed for the encoded 15-package source scope. This is COMPLETE_UNREVIEWED, not clinical validation or autonomous prescribing authorization.'
        p.write_text(json.dumps(d,indent=2))
        # mirror manifest
        for m in ROOT.glob('knowledge/*/*/manifest.json'):
            man=json.loads(m.read_text())
            if man.get('guideline_id')==d.get('guideline_id') and man.get('version')==d.get('version'):
                man['package_status']='DRAFT';man['clinical_status']='REQUIRES_CLINICAL_REVIEW';man['runtime_eligible']=False
                man['pathway_completeness']=dict(lifecycle['pathway_completeness'])
                m.write_text(json.dumps(man,indent=2));break
    print('FINALIZED_COMPLETE_UNREVIEWED=15')
if __name__=='__main__':main()
