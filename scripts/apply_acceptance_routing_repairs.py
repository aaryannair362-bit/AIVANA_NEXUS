from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
ENC=ROOT/'backend/nexus/guidelines/encoded'

# Option-level refinement facts must not suppress an already-established
# treatment pathway when unconditional guideline options are available.
# Unknown modifiers simply withhold the conditional option and remain visible
# in what_could_change_pathway.
def mark_option_refinements_nonblocking(pkg, node_id, option_ids):
    node = pkg["nodes"][node_id]
    for opt in node.get("recommendation", {}).get("options", []):
        if opt.get("option_id") in set(option_ids):
            opt["decision_relevant"] = False



def facts(expr):
    if not expr:return []
    if 'fact' in expr:return [expr['fact']]
    if 'not' in expr:return facts(expr['not'])
    out=[]
    for k in ('all','any'):
        for x in expr.get(k,[]):out += facts(x)
    return sorted(set(out))


def sync_inventory(pkg):
    by_id={d.get('decision_id'):d for d in pkg.get('executable_decisions',[]) if d.get('decision_id')}
    for nid,node in pkg.get('nodes',{}).items():
        did=node.get('decision_id')
        if did and did in by_id:
            by_id[did]['input_fact_ids']=facts(node.get('expression'))
            branches=['TRUE','FALSE','UNKNOWN','CONFLICT']
            # Preserve declared branch vocabulary, but make UNKNOWN explicit when
            # the runtime has a safe refinement fallback.
            if 'possible_branches' in by_id[did]:
                by_id[did]['possible_branches']=branches


def load(fn):
    p=ENC/fn
    return p,json.loads(p.read_text())

def save(p,d):
    sync_inventory(d)
    p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n")

# 1 ALL: a known new/workup phase makes relapse/refractory false even if a
# post-treatment response fact is not applicable yet.
p,d=load('nexus_acute_lymphoblastic_leukemia_v2_2026.json')
n=d['nodes']['care_rr']
orig=n['expression']
n['expression']={'all':[{'fact':'treatment_phase','op':'not_in','value':['NEW_DIAGNOSIS','WORKUP']},orig]}
mark_option_refinements_nonblocking(d,'bph_initial',{'all_bph_hypercvad_tki','all_bph_epoch_tki','all_bph_minihypercvd_tki','all_bph_phallcon'})
save(p,d)

# 2 AML: same care-state guard. If TP53 is not yet available, release only a
# high-level intensive pathway while retaining the missing refinement.
p,d=load('nexus_acute_myeloid_leukemia_v5_2026.json')
n=d['nodes']['aml_care_rr']; orig=n['expression']
n['expression']={'all':[{'fact':'treatment_phase','op':'not_in','value':['NEW_DIAGNOSIS','WORKUP']},orig]}
d['nodes']['intensive_tp53']['on']['UNKNOWN']='adverse_unclassified'
base=d['nodes']['adverse_options']
d['nodes']['adverse_unclassified']={
    'kind':'action',
    'label':'Intensive-eligible non-APL AML: initial intensive-induction pathway established; TP53/MDS-related subtype refinement remains pending. ELN adverse-risk status, when present, supports early transplant planning.',
    'status':'RECOMMENDATION',
    'recommendation_id':'adverse_unclassified',
    'source_pathways':['AML-1','AML-2'],
    'recommendation':{
        'title':'Intensive-eligible non-APL AML with molecular subtype refinement pending.',
        'options':[
            {
                'option_id':'aml_unclassified_intensive',
                'label':'Source-listed intensive induction pathway',
                'text':'Proceed within the intensive-induction pathway while completing missing molecular/risk refinement.',
                'decision_relevant':True,
                'source_provenance':base['recommendation']['options'][1]['source_provenance'],
            },
        ],
        'supporting_sections':['AML-A','AML-E','AML-F'],
        'next_steps':['Complete TP53/MDS-related molecular-risk refinement before subtype-specific regimen and transplant planning.'],
    },
    'pathway_id':'AML_INTENSIVE_INITIAL_REFINEMENT_PENDING',
}
save(p,d)

# 3 DLBCL: generic DLBCL should not be blocked merely because the rare primary
# cutaneous leg-type qualifier is not mentioned; an explicitly positive value
# still takes its dedicated branch. Also avoid asking relapse response at initial treatment.
p,d=load('nexus_b_cell_lymphomas_v4_2026.json')
d['nodes']['dlbcl_cutaneous_check']['on']['UNKNOWN']='dlbcl_entry'
n=d['nodes']['dlbcl_entry']; orig=n['expression']
n['expression']={'all':[{'fact':'treatment_phase','op':'neq','value':'INITIAL_TREATMENT'},orig]}
mark_option_refinements_nonblocking(d,'dlbcl_full_first',{'dlbcl_pola_rchp','dlbcl_poorlv_regimen','dlbcl_frail_regimen','dlbcl_cns_integrated'})
save(p,d)

# 4 BCC: NEW_DIAGNOSIS explicitly excludes a current recurrence episode; do not
# let an unmentioned local_recurrence boolean block primary-risk routing.
p,d=load('nexus_basal_cell_skin_cancer_v1_2027.json')
d['nodes']['care_recur']['expression']={
    'all':[
        {'fact':'treatment_phase','op':'neq','value':'NEW_DIAGNOSIS'},
        {'any':[{'fact':'treatment_phase','op':'eq','value':'RECURRENCE'},{'fact':'local_recurrence','op':'eq','value':True}]},
    ]
}
save(p,d)

# 5 Biliary first-line action: unknown biomarker/cisplatin suitability changes
# the exact option set but should not erase the already-established first-line
# advanced pathway. Exact options remain hidden until applicable facts are known.
p,d=load('nexus_biliary_tract_cancers_v1_2026.json')
for opt in d['nodes']['sys_first']['recommendation']['options']:
    if opt.get('applicability'):
        opt['decision_relevant']=False
save(p,d)

# 6 Bladder: established post-intravesical recurrence bypasses the historical
# initial-TURBT completeness gate. Unknown cytology special-workup status does
# not block the ordinary risk branch unless explicitly positive.
p,d=load('nexus_bladder_cancer_v3_2026.json')
d['nodes']['nmibc_initial']['label']='Established post-intravesical episode or initial TURBT visually complete?'
d['nodes']['nmibc_initial']['expression']={'any':[{'fact':'treatment_phase','op':'eq','value':'POST_INTRAVESICAL'},{'fact':'visually_complete_turbt','op':'eq','value':True}]}
d['nodes']['cytology_gate']['on']['UNKNOWN']='nmibc_risk_decision'
save(p,d)

# 7 Breast schema cleanup: the old preoperative_systemic_indicated input allowed
# an extractor/LLM to choose a guideline route. Derive the common source-defined
# preoperative route from receptor + clinical T/N criteria instead.
p,d=load('nexus_breast_cancer_v6_2026.json')
d['fact_definitions']=[x for x in d['fact_definitions'] if x.get('key')!='preoperative_systemic_indicated']
d['nodes']['care_preop']['label']='Preoperative systemic therapy selected/planned or source-defined HER2+/TNBC cT2+/cN+ criteria met?'
d['nodes']['care_preop']['expression']={
    'any':[
        {'fact':'treatment_phase','op':'eq','value':'PREOPERATIVE_SYSTEMIC'},
        {'all':[
            {'fact':'her2_status','op':'eq','value':'POSITIVE'},
            {'any':[{'fact':'clinical_t','op':'in','value':['T2','T3','T4']},{'fact':'clinical_n','op':'in','value':['N1','N2','N3']}]},
        ]},
        {'all':[
            {'fact':'hr_status','op':'eq','value':'NEGATIVE'},
            {'fact':'her2_status','op':'eq','value':'NEGATIVE'},
            {'any':[{'fact':'clinical_t','op':'in','value':['T2','T3','T4']},{'fact':'clinical_n','op':'in','value':['N1','N2','N3']}]},
        ]},
    ]
}
save(p,d)
# Mirror schema cleanup in knowledge file if present.
k=ROOT/'knowledge/breast_cancer/6.2026/facts.json'
if k.exists():
    kd=json.loads(k.read_text())
    if isinstance(kd,list):kd=[x for x in kd if x.get('key')!='preoperative_systemic_indicated']
    elif isinstance(kd,dict) and isinstance(kd.get('fact_definitions'),list):kd['fact_definitions']=[x for x in kd['fact_definitions'] if x.get('key')!='preoperative_systemic_indicated']
    k.write_text(json.dumps(kd,indent=2,ensure_ascii=False)+"\n")

# 8 Cervical: fertility intent is only an early-stage gate. Stage IIB+ must reach
# locally-advanced routing. If para-aortic status is unknown, release the common
# definitive CRT + brachytherapy pathway but keep nodal field refinement missing.
p,d=load('nexus_cervical_cancer_v2_2026.json')
d['nodes']['initial_stage']['label']='Early-stage fertility-sparing pathway selected?'
d['nodes']['initial_stage']['expression']={'all':[{'fact':'figo_stage','op':'in','value':['IA1','IA2','IB1']},{'fact':'fertility_sparing_desired','op':'eq','value':True}]}
d['nodes']['locallyadv_nodes']['on']['UNKNOWN']='la_nodal_pending'
std=d['nodes']['la_standard']
d['nodes']['la_nodal_pending']={
    'kind':'action',
    'label':'Stage IIB-IVA: definitive concurrent platinum-based chemoradiation plus brachytherapy; para-aortic nodal status is still required to finalize radiation field extent.',
    'status':'RECOMMENDATION',
    'recommendation_id':'la_nodal_pending',
    'source_pathways':['CERV-7'],
    'recommendation':{
        'title':'Locally advanced cervical cancer definitive therapy with nodal-field refinement pending.',
        'options':[
            std['recommendation']['options'][0],
            std['recommendation']['options'][1],
        ],
        'supporting_sections':['CERV-D','CERV-F'],
        'next_steps':[],
    },
    'pathway_id':'CERV_LOCALLY_ADVANCED_NODAL_REFINEMENT_PENDING',
}
save(p,d)

# 9 GIST: a known postoperative episode is not progressive simply because a
# response_status fact is not applicable/documented.
p,d=load('nexus_gastrointestinal_stromal_tumors_v1_2026.json')
n=d['nodes']['care_prog']; orig=n['expression']
n['expression']={'all':[{'fact':'treatment_phase','op':'neq','value':'POSTOPERATIVE'},orig]}
save(p,d)

# 10 Hodgkin: use objective age plus explicit unfit flag. When the combined
# special-population flag is absent but age <=60, continue to stage routing while
# retaining the missing refinement in the result.
p,d=load('nexus_hodgkin_lymphoma_v2_2026.json')
d['nodes']['special_old']['expression']={'any':[{'fact':'age_years','op':'gt','value':60},{'fact':'age_over_60_or_unfit','op':'eq','value':True}]}
d['nodes']['special_old']['on']['UNKNOWN']='initial_stage'
save(p,d)

# 11 Kidney: missing a special-phase label should not block a clearly staged
# active renal mass. Explicit hereditary/post-nephrectomy/stage-IV facts still win.
p,d=load('nexus_kidney_cancer_v1_2027.json')
d['nodes']['hered_phase']['on']['UNKNOWN']='care_stage4'
d['nodes']['care_stage4']['on']['UNKNOWN']='care_post'
d['nodes']['care_post']['on']['UNKNOWN']='initial_t'
save(p,d)

# 12 MPN: if AP/BP is not established and the phase is otherwise a standard PV/
# ET/MF episode, allow subtype routing while retaining missing blast quantitation.
p,d=load('nexus_myeloproliferative_neoplasms_v2_2026.json')
d['nodes']['apbp']['on']['UNKNOWN']='workup_phase'
save(p,d)

print('ACCEPTANCE_ROUTING_REPAIRS=APPLIED')
