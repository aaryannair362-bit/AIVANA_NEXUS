from __future__ import annotations
import json,random,time,threading,statistics,urllib.request,urllib.error
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.evaluator import evaluate
ROOT=Path(__file__).resolve().parents[1]
ENC=ROOT/'backend/nexus/guidelines/encoded'
PACKAGES={p.name:json.loads(p.read_text()) for p in ENC.glob('nexus_*.json')}

class H(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_POST(self):
        if self.path!='/evaluate':self.send_response(404);self.end_headers();return
        n=int(self.headers.get('Content-Length','0')); body=json.loads(self.rfile.read(n) or b'{}')
        pkg=PACKAGES.get(body.get('package'))
        if not pkg:out={'status':'INVALID_INPUT','error':'unknown package'}
        else:out=evaluate(pkg,body.get('state',{}))
        raw=json.dumps(out).encode(); self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

def random_value(d):
    t=d.get('value_type')
    if t=='CODED': return random.choice(d.get('allowed_values',[]))
    if t=='BOOLEAN': return random.choice([True,False])
    if t=='NUMERIC': return random.choice([0,0.5,1,1.5,2,3,4,5,8,10,12,20,40,65,75,100])
    return None

def random_state(pkg):
    st={}
    for d in pkg['fact_definitions']:
        # Cancer type is almost always included; other facts are realistically incomplete sometimes.
        if d['key']=='cancer_type' or random.random()<0.82: st[d['key']]=random_value(d)
    # Bias in-scope to exercise real clinical routing.
    c=next((d for d in pkg['fact_definitions'] if d['key']=='cancer_type'),None)
    if c and random.random()<0.92:
        vals=[v for v in c['allowed_values'] if v!='OTHER'];
        if vals:st['cancer_type']=vals[0]
    return st

def _defs(pkg):
    return {d['key']:d for d in pkg['fact_definitions']}

def _candidate_values(fd, atom, desired=True):
    op=atom.get('op','eq'); target=atom.get('value')
    if fd.get('value_type')=='BOOLEAN': domain=[False,True]
    elif fd.get('value_type')=='CODED': domain=list(fd.get('allowed_values',[]))
    elif fd.get('value_type')=='NUMERIC':
        domain=[0,0.1,0.5,1,1.5,2,3,4,5,8,10,12,20,40,65,75,100]
        if isinstance(target,(int,float)) and not isinstance(target,bool):
            domain += [target-1,target,target+1]
    else: domain=[]
    def truth(v):
        try:
            if op=='eq': return v==target
            if op=='neq': return v!=target
            if op=='gt': return v>target
            if op=='gte': return v>=target
            if op=='lt': return v<target
            if op=='lte': return v<=target
            if op=='in': return v in target
            if op=='not_in': return v not in target
            if op=='contains': return target in v
        except Exception: return False
        return False
    return [v for v in domain if truth(v) is desired]

def _merge(a,b):
    out=dict(a)
    for k,v in b.items():
        if k in out and out[k]!=v:return None
        out[k]=v
    return out

def assignments_for_expr(expr,pkg,desired=True,limit=128):
    defs=_defs(pkg)
    if 'fact' in expr:
        vals=_candidate_values(defs[expr['fact']],expr,desired)
        return [{expr['fact']:v} for v in vals[:limit]]
    if 'not' in expr:
        return assignments_for_expr(expr['not'],pkg,not desired,limit)
    if 'all' in expr:
        if desired:
            acc=[{}]
            for part in expr['all']:
                nxt=[]
                for a in acc:
                    for b in assignments_for_expr(part,pkg,True,limit):
                        m=_merge(a,b)
                        if m is not None:nxt.append(m)
                        if len(nxt)>=limit:break
                    if len(nxt)>=limit:break
                acc=nxt
                if not acc:break
            return acc
        out=[]
        for part in expr['all']:
            out += assignments_for_expr(part,pkg,False,limit)
            if len(out)>=limit:break
        return out[:limit]
    if 'any' in expr:
        if desired:
            out=[]
            for part in expr['any']:
                out += assignments_for_expr(part,pkg,True,limit)
                if len(out)>=limit:break
            return out[:limit]
        acc=[{}]
        for part in expr['any']:
            nxt=[]
            for a in acc:
                for b in assignments_for_expr(part,pkg,False,limit):
                    m=_merge(a,b)
                    if m is not None:nxt.append(m)
                    if len(nxt)>=limit:break
                if len(nxt)>=limit:break
            acc=nxt
            if not acc:break
        return acc
    return []

def assign_expr(expr,state,pkg):
    # Return a satisfying assignment that overwrites only facts required by the consistency expression.
    xs=assignments_for_expr(expr,pkg,True,256)
    if not xs:return False
    # Prefer assignment with fewest facts for minimal perturbation.
    xs.sort(key=lambda x:(len(x),json.dumps(x,sort_keys=True,default=str)))
    state.update(xs[0])
    return True

def post(port,payload):
    raw=json.dumps(payload).encode(); req=urllib.request.Request(f'http://127.0.0.1:{port}/evaluate',data=raw,headers={'Content-Type':'application/json'},method='POST')
    t=time.perf_counter()
    with urllib.request.urlopen(req,timeout=5) as r: out=json.loads(r.read())
    return out,(time.perf_counter()-t)*1000

def main():
    random.seed() # system entropy; intentionally not fixed/golden
    srv=ThreadingHTTPServer(('127.0.0.1',0),H); port=srv.server_port; th=threading.Thread(target=srv.serve_forever,daemon=True);th.start()
    per_pkg=750; lat=[]; total=0; status_counts={}; terminal_counts={}; errors=[]; conflict_checks=[]
    try:
        for name,pkg in sorted(PACKAGES.items()):
            pc={}
            for _ in range(per_pkg):
                state=random_state(pkg); out,ms=post(port,{'package':name,'state':state}); lat.append(ms);total+=1
                s=out.get('status','MISSING_STATUS');status_counts[s]=status_counts.get(s,0)+1;pc[s]=pc.get(s,0)+1
                if s=='RECOMMENDATION':
                    t=out.get('terminal');terminal_counts.setdefault(name,{})[t]=terminal_counts.setdefault(name,{}).get(t,0)+1
                    # A recommendation must carry at least one source section and source metadata must exist.
                    if not out.get('source_pathways'):errors.append(f'{name}: recommendation without source_pathways')
                    if not out.get('relevant_sections'):errors.append(f'{name}: recommendation without relevant_sections')
                    if any(not x.get('found') for x in out.get('relevant_sections',[]) if x.get('code') in out.get('source_pathways',[])):
                        errors.append(f'{name}: recommendation references missing source section')
                if s=='RULE_ENGINE_ERROR':errors.append(f'{name}: {out}')
            print(name,pc)
            # Property-check every declared consistency rule over HTTP, using randomized background facts plus a satisfying assignment.
            for cr in pkg.get('consistency_rules',[]):
                st=random_state(pkg);assign_expr(cr['when'],st,pkg)
                # make sure cancer type remains in-scope
                c=next((d for d in pkg['fact_definitions'] if d['key']=='cancer_type'),None)
                if c:
                    vals=[v for v in c['allowed_values'] if v!='OTHER'];
                    if vals:st['cancer_type']=vals[0]
                out,ms=post(port,{'package':name,'state':st});lat.append(ms);total+=1
                ok=out.get('status')=='REQUIRES_REVIEW'
                conflict_checks.append((name,cr['id'],ok,out.get('status')))
                if not ok:errors.append(f'{name}: consistency rule {cr["id"]} did not block: {out}')
    finally:
        srv.shutdown();srv.server_close()
    lat_sorted=sorted(lat)
    p50=statistics.median(lat_sorted) if lat_sorted else 0
    p95=lat_sorted[int(.95*(len(lat_sorted)-1))] if lat_sorted else 0
    report={'test_kind':'live randomized HTTP fuzz/property test; no golden expected-answer cases','random_seed':'system_entropy','requests':total,'packages':len(PACKAGES),'status_counts':status_counts,'p50_ms':p50,'p95_ms':p95,'rule_engine_errors':sum(1 for e in errors if 'RULE_ENGINE_ERROR' in e),'errors':errors,'consistency_rule_checks':[{'package':a,'rule_id':b,'passed':c,'status':d} for a,b,c,d in conflict_checks],'terminal_counts':terminal_counts}
    outp=ROOT/'source_audit'/'REALTIME_HTTP_FUZZ_REPORT.json';outp.write_text(json.dumps(report,indent=2))
    print('REQUESTS',total);print('STATUS_COUNTS',status_counts);print('P50_MS',round(p50,3));print('P95_MS',round(p95,3));print('CONSISTENCY_RULES',sum(1 for x in conflict_checks if x[2]),'/',len(conflict_checks));print('ERRORS',len(errors));print('REALTIME_HTTP_FUZZ=' + ('PASS' if not errors else 'FAIL'))
    raise SystemExit(1 if errors else 0)
if __name__=='__main__':main()
