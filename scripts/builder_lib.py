from __future__ import annotations
from copy import deepcopy


def atom(f,op='eq',value=True,**kw):
    d={'fact':f,'op':op,'value':value}; d.update(kw); return d

def any_(*xs): return {'any':list(xs)}
def all_(*xs): return {'all':list(xs)}
def not_(x): return {'not':x}

class Graph:
    def __init__(self): self.nodes={}
    def decision(self,nid,label,expr,t,f,src,decision_id=None,pathway_id=None):
        self.nodes[nid]={'kind':'decision','label':label,'expression':expr,'on':{'TRUE':t,'FALSE':f},'source_pathways':list(src),'decision_id':decision_id or nid}
        if pathway_id:self.nodes[nid]['pathway_id']=pathway_id
        return nid
    def action(self,nid,label,src,options=None,support=None,next_steps=None,recommendation_id=None,pathway_id=None,clinical_state=None):
        rec={'title':label,'options':options or [],'supporting_sections':support or [],'next_steps':next_steps or []}
        self.nodes[nid]={'kind':'action','label':label,'status':'RECOMMENDATION','recommendation_id':recommendation_id or nid,'source_pathways':list(src),'recommendation':rec}
        if pathway_id:self.nodes[nid]['pathway_id']=pathway_id
        if clinical_state:self.nodes[nid]['clinical_state']=clinical_state
        return nid
    def status(self,nid,label,status='OUTSIDE_ENCODED_SCOPE',src=None,pathway_id=None):
        self.nodes[nid]={'kind':'status','label':label,'status':status,'source_pathways':list(src or [])}
        if pathway_id:self.nodes[nid]['pathway_id']=pathway_id
        return nid

def opt(option_id,label,text=None,preference=None,evidence=None,app=None,qualifiers=None,src=None,decision_relevant=True):
    d={'option_id':option_id,'label':label,'text':text or label,'decision_relevant':decision_relevant}
    if preference:d['preference_category']=preference
    if evidence:d['evidence_category']=evidence
    if app:d['applicability']=app
    if qualifiers:d['qualifiers']=qualifiers
    if src:d['source_provenance']=src
    return d

def fact(key,value_type='CODED',allowed=None,role='ROUTING',semantic_unknown=None,description=None):
    d={'key':key,'value_type':value_type,'fact_role':role}
    if allowed is not None:d['allowed_values']=allowed
    if semantic_unknown is not None:d['semantic_unknown_values']=semantic_unknown
    if description:d['description']=description
    return d

def upsert_fact(pkg,f):
    arr=pkg.setdefault('fact_definitions',[])
    for i,x in enumerate(arr):
        if x.get('key')==f['key']:
            merged=deepcopy(x); merged.update(f); arr[i]=merged; return
    arr.append(f)

def set_roles(pkg, roles):
    for d in pkg.get('fact_definitions',[]):
        d['fact_role']=roles.get(d['key'],d.get('fact_role','NON_ROUTING_CONTEXT'))

def src_prov(pkg, section):
    cov=pkg.get('coverage',{}); meta=cov.get('primary_sections',{}).get(section) or cov.get('supporting_sections',{}).get(section) or {}
    pages=meta.get('pages',[])
    return {'guideline':pkg.get('title'),'version':pkg.get('version'),'section':section,'page_label':section,'physical_pages':pages,'source_anchor':f'{section}:pages:{",".join(map(str,pages))}'}
